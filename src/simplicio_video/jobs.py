"""`simplicio-video jobs`: long tasks in the background, in a separate process, with no daemon and no network port.

Why: the MCP server (and a terminal) used to block until `swap run` or `voice` finished. `jobs submit` returns at once;
a small runner process (one asyncio event loop per task, its own process group) runs the task and writes its state.

How it works, in a few rules:
- One folder per task in `<data>/jobs/<id>/` (data = $SIMPLICIO_VIDEO_DATA, default ~/.simplicio-video): `job.json`
  (the state, written atomically: temp file + fsync + os.replace, under an flock), `output.log` (the task output).
- The runner is detached (`start_new_session`), runs the task as a child in ANOTHER process group (like toonflow's
  `_stop_group`): cancel = SIGTERM to the runner, which sends SIGINT to the task group, waits a grace period, then
  SIGKILL, then sweeps the group. No port is opened and nothing stays running after the task ends.
- A closed list of tasks (`KINDS`): `swap-run` and `voice`. `swap-run` spends money, so it is confirmed at submission
  (`--yes` and `--autorizo`, after the same checks as `swap run`) and can only be submitted from the terminal. Over MCP
  only `voice` with a LOCAL provider can be submitted; status, list, result and cancel work for every task.
- If the runner dies without writing a final state, the next status/list marks the task `lost` and kills what it left
  (orphan recovery). Finished tasks older than a week are removed on submit and by `jobs clean`.
- No API key is ever written: the key stays in the environment of the runner and the task. Submitting arguments that
  contain a key is refused, and every state write and every output line is scrubbed with the swap redaction filter.
"""
from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .aio import positive_int
from .swap import scrub

try:  # POSIX only; without it the state is still written atomically, just not serialized between processes
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None

SCHEMA = "simplicio.job/v1"
STATES = ("queued", "running", "done", "failed", "cancelled", "lost")
FINAL = ("done", "failed", "cancelled", "lost")
# Voice providers that run on this machine: they spend no money, so MCP may submit them.
LOCAL_VOICE = ("file", "local", "voxcpm", "openvoice")
PRUNE_DAYS = 7
GRACE_S = 15.0
HEARTBEAT_S = 5.0
LOG_CAP = 1 << 20
ID_RE = re.compile(r"^\d{8}-\d{6}-[0-9a-f]{8}$")
SWAP_KEYS = {"provider", "video", "refs", "out", "resolution", "max_usd", "prompt", "timeout", "poll_interval", "concurrency",
             "aceito_unverified", "force", "autorizo"}
VOICE_KEYS = {"contrato", "provider", "force", "only", "concurrency"}


class JobError(Exception):
    code = 1

    def __init__(self, message: str, code: int = 1):
        super().__init__(message)
        self.code = code


# ---------------------------------------------------------------------------------------------------------- storage

def data_root() -> Path:
    data = os.environ.get("SIMPLICIO_VIDEO_DATA")
    return Path(data).expanduser() if data else Path.home() / ".simplicio-video"


def jobs_dir() -> Path:
    return data_root() / "jobs"


def job_dir(jid: str) -> Path:
    if not isinstance(jid, str) or not ID_RE.match(jid):
        raise JobError(f"id de tarefa inválido: {jid!r} (use o id que `jobs list` mostra)")
    return jobs_dir() / jid


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _secrets() -> list[str]:
    from .swap import _secrets as swap_secrets
    vals = list(swap_secrets())
    for name in ("ELEVENLABS_API_KEY", "XAI_API_KEY"):
        v = os.environ.get(name, "").strip()
        if len(v) >= 6:
            vals.append(v)
    return vals


def _scrub(text: str) -> str:
    text = scrub(text)
    for v in _secrets():
        text = text.replace(v, "***")
    return text


def write_json_atomic(path: Path, obj: dict) -> None:
    """Temp file in the same folder, fsync, then os.replace: a reader sees the old file or the new one, never half."""
    text = _scrub(json.dumps(obj, indent=2, ensure_ascii=False) + "\n")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    try:
        with open(tmp, "w", encoding="utf8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        with contextlib.suppress(OSError):
            tmp.unlink()


@contextlib.contextmanager
def _locked(jid: str):
    d = job_dir(jid)
    if fcntl is None or not d.is_dir():
        yield
        return
    with open(d / ".lock", "a") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def read_state(jid: str) -> dict:
    path = job_dir(jid) / "job.json"
    try:
        return json.loads(path.read_text(encoding="utf8"))
    except FileNotFoundError:
        raise JobError(f"tarefa não encontrada: {jid}") from None
    except ValueError:
        raise JobError(f"estado da tarefa ilegível: {path}") from None


def _write(jid: str, st: dict, fields: dict) -> dict:
    st.update(fields)
    write_json_atomic(job_dir(jid) / "job.json", st)
    return st


def update(jid: str, **fields) -> dict:
    with _locked(jid):
        return _write(jid, read_state(jid), fields)


def read_log(jid: str, tail: int | None = None) -> str:
    try:
        text = (job_dir(jid) / "output.log").read_text(encoding="utf8", errors="replace")
    except FileNotFoundError:
        return ""
    return "\n".join(text.splitlines()[-tail:]) + "\n" if tail else text


# --------------------------------------------------------------------------------------------------- liveness, lost

def proc_start(pid: int) -> str | None:
    """Start time of `pid` in clock ticks (/proc, Linux), to tell a reused pid from the original process."""
    try:
        stat = Path(f"/proc/{pid}/stat").read_text()
    except OSError:
        return None
    return stat[stat.rindex(")") + 2:].split()[19]


def _is_zombie(pid: int) -> bool:
    try:
        stat = Path(f"/proc/{pid}/stat").read_text()
    except OSError:
        return False
    return stat[stat.rindex(")") + 2:].split()[0] == "Z"


def is_alive(pid: int | None, start: str | None = None) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    if _is_zombie(pid):
        return False
    now = proc_start(pid)
    return not (start and now and start != now)


def _kill_group(pgid: int | None, sig: int = signal.SIGKILL) -> None:
    if pgid and pgid > 1:
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(pgid, sig)


LOST_MSG = "o runner morreu sem gravar o estado final (processo encerrado ou máquina reiniciada)"


def status(jid: str) -> dict:
    """The state of one task. A queued/running task whose runner is gone becomes `lost` here (orphan recovery)."""
    st = read_state(jid)
    if st["state"] not in ("queued", "running"):
        return st
    pid = st.get("runner_pid")
    if pid:
        dead = not is_alive(pid, st.get("runner_start"))
    else:  # the runner pid is written right after the spawn: no pid for 30 s means the spawn never happened
        created = _parse(st.get("created_at"))
        dead = bool(created and datetime.now(timezone.utc) - created > timedelta(seconds=30))
    if not dead:
        return st
    with _locked(jid):
        fresh = read_state(jid)  # the runner may have written the final state between the read and now
        if fresh["state"] not in ("queued", "running"):
            return fresh
        _kill_group(fresh.get("task_pgid"))  # what the dead runner left behind must not keep running
        return _write(jid, fresh, {"state": "lost", "finished_at": now_iso(), "error": LOST_MSG})


def list_jobs(state: str | None = None) -> list[dict]:
    if state is not None and state not in STATES:
        raise JobError(f"estado desconhecido: {state} (use: {', '.join(STATES)})")
    root = jobs_dir()
    if not root.is_dir():
        return []
    out = []
    for d in sorted((p for p in root.iterdir() if p.is_dir() and ID_RE.match(p.name)), reverse=True):
        try:
            st = status(d.name)
        except JobError:
            continue
        if state is None or st["state"] == state:
            out.append(st)
    return out


def _parse(text: str | None) -> datetime | None:
    try:
        return datetime.fromisoformat(text) if text else None
    except ValueError:
        return None


def clean(older_than_days: float = PRUNE_DAYS) -> list[str]:
    """Remove finished tasks older than the limit (running and queued tasks are never removed). Returns the removed ids."""
    root = jobs_dir()
    if not root.is_dir():
        return []
    cutoff = datetime.now(timezone.utc) - timedelta(days=older_than_days)
    removed = []
    for d in sorted(p for p in root.iterdir() if p.is_dir() and ID_RE.match(p.name)):
        try:
            st = status(d.name)
        except JobError:
            continue
        if st["state"] not in FINAL:
            continue
        when = _parse(st.get("finished_at")) or datetime.fromtimestamp(d.stat().st_mtime, timezone.utc)
        if when <= cutoff:
            shutil.rmtree(d, ignore_errors=True)
            removed.append(d.name)
    return removed


# ----------------------------------------------------------------------------------------------------- the closed list

def _no_secret(params: dict) -> None:
    text = json.dumps(params, ensure_ascii=False)
    if any(v in text for v in _secrets()):
        raise JobError("recusado: os argumentos contêm uma chave de API. A chave só entra pela variável de ambiente do provedor.")


def _check_keys(params: dict, allowed: set[str]) -> None:
    extra = sorted(set(params) - allowed)
    if extra:
        raise JobError(f"parâmetros desconhecidos: {', '.join(extra)} (aceitos: {', '.join(sorted(allowed))})")


def _prepare_swap(params: dict, confirm_yes: bool, origin: str) -> tuple[dict, bool, dict]:
    """swap run, confirmed here: the same checks `swap run` does before spending, so a refusal is immediate and visible."""
    from . import swap, swap_providers
    _check_keys(params, SWAP_KEYS)
    if origin != "terminal":
        raise JobError("swap-run gasta dinheiro: só se submete pelo terminal (simplicio-video jobs submit swap-run ... --autorizo --yes)")
    if not confirm_yes:
        raise JobError("swap-run gasta dinheiro: confirme o gasto na submissão com --yes (ele é decidido aqui, não depois)")
    if not params.get("autorizo"):
        raise JobError("recusado: falta --autorizo. Ele confirma que você tem direito sobre as imagens e o vídeo "
                       "(texto completo em `simplicio-video swap run --help`)")
    p = {"provider": "gemini", "resolution": "720p", "max_usd": swap.DEFAULT_MAX_USD, **{k: v for k, v in params.items() if v is not None}}
    for need in ("video", "out"):
        if not p.get(need):
            raise JobError(f"falta {need}")
    p["refs"] = list(p.get("refs") or [])
    p["video"] = str(Path(p["video"]).resolve())
    p["refs"] = [str(Path(r).resolve()) for r in p["refs"]]
    p["out"] = str(Path(p["out"]).resolve())
    try:
        plan = swap.prepare(p["provider"], p["video"], p["refs"], p["resolution"])
        plan.adapter.api_key()
    except swap.SwapError as e:
        raise JobError(str(e)) from None
    if plan.estimate.usd > float(p["max_usd"]):
        raise JobError(f"estimativa US$ {plan.estimate.usd:.2f} passa do teto --max-usd {float(p['max_usd']):.2f}: nada foi enviado")
    if not plan.adapter.verified and not p.get("aceito_unverified"):
        raise JobError(f"o adaptador {p['provider']} está UNVERIFIED (não conferido na API real): repita com --aceito-unverified")
    if Path(p["out"]).exists() and not p.get("force"):
        raise JobError(f"a saída já existe: {p['out']} (use --force para sobrescrever)")
    p["max_usd"] = float(p["max_usd"])
    extra = {"estimate_usd": round(plan.estimate.usd, 6), "confirmed": {"yes": True, "autorizo": True, "max_usd": p["max_usd"],
                                                                         "at": now_iso()}}
    return p, True, extra


def _prepare_voice(params: dict, confirm_yes: bool, origin: str) -> tuple[dict, bool, dict]:
    from . import contract as ct
    from . import voice
    _check_keys(params, VOICE_KEYS)
    if not params.get("contrato"):
        raise JobError("falta o contrato (CONTRATO.yaml)")
    path = Path(params["contrato"]).resolve()
    if not path.is_file():
        raise JobError(f"contrato não encontrado: {params['contrato']}")
    provider = params.get("provider")
    if origin != "terminal":
        if not provider:
            raise JobError(f"informe o provider da voz (local: {', '.join(LOCAL_VOICE)}): pelo MCP só se submete voz com provedor local")
        if provider not in LOCAL_VOICE:
            raise JobError(f"pelo MCP só se submete voz com provedor local ({', '.join(LOCAL_VOICE)}); {provider} usa rede e pode gastar: "
                           "submeta pelo terminal com --yes")
    if not provider:
        try:
            provider = ct.load(path).data["voz"]["provider"]
        except (SystemExit, Exception) as e:  # noqa: BLE001 (any load failure is a refusal, not a crash)
            raise JobError(f"contrato ilegível: {e}") from None
    if provider not in voice.PROVIDERS or provider in ("elevenlabs", "xai"):
        raise JobError(f"provider de voz sem suporte para tarefa: {provider}")
    spends = provider not in LOCAL_VOICE
    if spends and not confirm_yes:
        raise JobError(f"a voz {provider} usa a API do provedor e pode gastar: confirme na submissão com --yes")
    p = {"contrato": str(path), "provider": provider, "force": bool(params.get("force")), "only": list(params.get("only") or []),
         "concurrency": params.get("concurrency")}
    extra = {"estimate_usd": None, "confirmed": {"yes": True, "at": now_iso()} if spends else None}
    return p, spends, extra


def _argv_swap(p: dict) -> list[str]:
    a = ["swap", "run", "--provider", p["provider"], "--video", p["video"]]
    for r in p.get("refs") or []:
        a += ["--ref", r]
    a += ["--out", p["out"], "--resolution", p.get("resolution", "720p"), "--autorizo", "--yes", "--json",
          "--max-usd", str(p["max_usd"])]
    for flag, key in (("--timeout", "timeout"), ("--poll-interval", "poll_interval"), ("--concurrency", "concurrency"),
                      ("--prompt", "prompt")):
        if p.get(key) not in (None, ""):
            a += [flag, str(p[key])]
    return a + (["--aceito-unverified"] if p.get("aceito_unverified") else []) + (["--force"] if p.get("force") else [])


def _argv_voice(p: dict) -> list[str]:
    a = ["voice", p["contrato"], *p.get("only", []), "--provider", p["provider"]]
    if p.get("force"):
        a.append("--force")
    if p.get("concurrency"):
        a += ["--concurrency", str(p["concurrency"])]
    return a


def _result_swap(p: dict, last_json: dict | None) -> dict | None:
    return last_json


def _result_voice(p: dict, last_json: dict | None) -> dict | None:
    lock = Path(p["contrato"]).parent / "timing.lock.json"
    try:
        data = json.loads(lock.read_text(encoding="utf8"))
    except (OSError, ValueError):
        return None
    import hashlib
    return {"provider": data.get("provider"), "lines": len(data.get("lines") or {}), "lock": str(lock),
            "lock_sha256": hashlib.sha256(lock.read_bytes()).hexdigest()}


KINDS = {
    "swap-run": {"prepare": _prepare_swap, "argv": _argv_swap, "result": _result_swap},
    "voice": {"prepare": _prepare_voice, "argv": _argv_voice, "result": _result_voice},
}


def build_argv(kind: str, params: dict) -> list[str]:
    return KINDS[kind]["argv"](params)


# -------------------------------------------------------------------------------------------------------------- submit

def _new_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8]


def _spawn_runner(jid: str) -> int:
    """Start the runner detached (own session = own process group), with no stdio and no port. Returns its pid."""
    proc = subprocess.Popen([sys.executable, "-m", "simplicio_video", "jobs", "_run", jid], stdin=subprocess.DEVNULL,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True, close_fds=True,
                            env=os.environ.copy())
    threading.Thread(target=proc.wait, daemon=True, name="jobs-reaper").start()  # no zombie in a long-lived parent (MCP)
    return proc.pid


def submit(kind: str, params: dict, *, confirm_yes: bool = False, origin: str = "terminal") -> dict:
    if kind not in KINDS:
        raise JobError(f"tipo de tarefa desconhecido: {kind} (lista fechada: {', '.join(KINDS)})")
    _no_secret(params)
    clean_params, spends, extra = KINDS[kind]["prepare"](dict(params), confirm_yes, origin)
    with contextlib.suppress(Exception):
        clean()
    jid = _new_id()
    st = {"schema": SCHEMA, "id": jid, "kind": kind, "state": "queued", "origin": origin, "spends": spends,
          "created_at": now_iso(), "started_at": None, "finished_at": None, "heartbeat_at": None, "runner_pid": None,
          "runner_start": None, "task_pid": None, "task_pgid": None, "exit_code": None, "error": None, "result": None,
          "cancel_requested_at": None, "cwd": str(Path.cwd()), "params": clean_params, **extra}
    write_json_atomic(job_dir(jid) / "job.json", st)
    try:
        pid = _spawn_runner(jid)
    except OSError as e:
        update(jid, state="failed", finished_at=now_iso(), error=f"não consegui iniciar o runner: {e}")
        raise JobError(f"não consegui iniciar o runner: {e}") from None
    return update(jid, runner_pid=pid, runner_start=proc_start(pid))


# --------------------------------------------------------------------------------------------------------------- cancel

def cancel(jid: str, wait_s: float | None = None) -> dict:
    """Ask the runner to stop the task (SIGINT to the task group, SIGKILL after the grace period) and wait for the final state."""
    st = status(jid)
    if st["state"] in FINAL:
        return st
    update(jid, cancel_requested_at=now_iso())
    pid = st.get("runner_pid")
    budget = (grace() + 10.0) if wait_s is None else wait_s
    if is_alive(pid, st.get("runner_start")):
        with contextlib.suppress(ProcessLookupError):
            os.kill(pid, signal.SIGTERM)
        deadline = datetime.now(timezone.utc) + timedelta(seconds=budget)
        while datetime.now(timezone.utc) < deadline:
            st = status(jid)
            if st["state"] in FINAL:
                break
            _sleep(0.05)
        else:
            st = read_state(jid)
            if st["state"] not in FINAL:  # the runner did not answer in time: stop everything by force
                _kill_group(st.get("task_pgid"))
                with contextlib.suppress(ProcessLookupError):
                    os.kill(pid, signal.SIGKILL)
                return update(jid, state="cancelled", finished_at=now_iso(), error="cancelado à força (o runner não respondeu)")
    else:
        _kill_group(st.get("task_pgid"))
    st = status(jid)
    if st["state"] == "lost" or st["state"] in ("queued", "running"):  # the runner died while we cancelled: it was cancelled
        st = update(jid, state="cancelled", finished_at=st.get("finished_at") or now_iso(), error=None)
    return st


def _sleep(s: float) -> None:
    import time
    time.sleep(s)


def grace() -> float:
    try:
        return float(os.environ.get("SIMPLICIO_JOBS_GRACE_S", "") or GRACE_S)
    except ValueError:
        return GRACE_S


def result(jid: str) -> dict:
    st = status(jid)
    if st["state"] not in FINAL:
        raise JobError(f"a tarefa {jid} ainda não terminou (estado: {st['state']}); veja `jobs status {jid}`", code=2)
    return {"id": jid, "kind": st["kind"], "state": st["state"], "exit_code": st.get("exit_code"), "error": st.get("error"),
            "result": st.get("result"), "finished_at": st.get("finished_at")}


def summary(st: dict) -> dict:
    """The state without the runner internals, for MCP and for lists."""
    keys = ("id", "kind", "state", "spends", "origin", "created_at", "started_at", "finished_at", "exit_code", "error",
            "estimate_usd", "confirmed", "result", "params")
    return {k: st.get(k) for k in keys}


# --------------------------------------------------------------------------------------------------------------- runner

async def _stop_group(proc, grace_s: float) -> None:
    """SIGINT to the task group; SIGKILL if it outlives the grace period; then a SIGKILL sweep of the group."""
    _kill_group(proc.pid, signal.SIGINT)
    try:
        await asyncio.wait_for(proc.wait(), timeout=grace_s)
    except asyncio.TimeoutError:
        _kill_group(proc.pid, signal.SIGKILL)
        await proc.wait()
    _kill_group(proc.pid, signal.SIGKILL)


async def _pump(stream, jid: str, box: dict) -> None:
    """Task output -> scrubbed log file (capped) and the last JSON line (the task result)."""
    log = job_dir(jid) / "output.log"
    size = 0
    with open(log, "a", encoding="utf8") as f:
        while True:
            raw = await stream.readline()
            if not raw:
                return
            line = _scrub(raw.decode("utf8", "replace").rstrip("\r\n"))
            box["tail"].append(line)
            del box["tail"][:-30]
            s = line.strip()
            if s.startswith("{") and s.endswith("}"):
                with contextlib.suppress(ValueError):
                    box["json"] = json.loads(s)
            if size < LOG_CAP:
                f.write(line + "\n")
                f.flush()
                size += len(line) + 1
                if size >= LOG_CAP:
                    f.write("[... saída cortada em 1 MB]\n")


async def _heartbeat(jid: str) -> None:
    while True:
        await asyncio.sleep(HEARTBEAT_S)
        with contextlib.suppress(JobError, OSError):
            update(jid, heartbeat_at=now_iso())


async def _runner(jid: str) -> int:
    st = read_state(jid)
    kind, params = st["kind"], st["params"]
    loop = asyncio.get_running_loop()
    stop = asyncio.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)
    pid = os.getpid()
    update(jid, state="running", started_at=now_iso(), heartbeat_at=now_iso(), runner_pid=pid, runner_start=proc_start(pid))
    box: dict = {"tail": [], "json": None}
    cancelled = False
    rc: int | None = None
    error: str | None = None
    try:
        argv = [sys.executable, "-m", "simplicio_video", *build_argv(kind, params)]
        proc = await asyncio.create_subprocess_exec(*argv, stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE,
                                                    stderr=asyncio.subprocess.STDOUT, start_new_session=True, cwd=st.get("cwd"),
                                                    env=os.environ.copy())
        update(jid, task_pid=proc.pid, task_pgid=proc.pid)
        pump = asyncio.create_task(_pump(proc.stdout, jid, box))
        beat = asyncio.create_task(_heartbeat(jid))
        waiter = asyncio.create_task(proc.wait())
        asker = asyncio.create_task(stop.wait())
        try:
            await asyncio.wait({waiter, asker}, return_when=asyncio.FIRST_COMPLETED)
            if not waiter.done():
                cancelled = True
                await _stop_group(proc, grace())
            rc = await waiter
            await pump
        finally:
            beat.cancel()
            asker.cancel()
            _kill_group(proc.pid)  # sweep: nothing the task started may outlive it
    except Exception as e:  # noqa: BLE001 (the runner reports, it never crashes without a final state)
        error = f"{type(e).__name__}: {e}"
    final = "cancelled" if cancelled else ("done" if rc == 0 and error is None else "failed")
    res = None
    if final == "done":
        with contextlib.suppress(Exception):
            res = KINDS[kind]["result"](params, box["json"])
    elif final == "failed" and error is None:
        lines = [s for s in box["tail"] if s.strip()][-3:]
        error = _scrub(" | ".join(lines))[-600:] or f"a tarefa terminou com código {rc}"
    update(jid, state=final, finished_at=now_iso(), exit_code=rc, error=error, result=res)
    return 0


def run_runner(jid: str) -> int:
    signal.signal(signal.SIGINT, signal.SIG_DFL)  # a runner started from a shell with SIGINT ignored must not pass that on
    try:
        return asyncio.run(_runner(jid))
    except Exception as e:  # noqa: BLE001
        with contextlib.suppress(Exception):
            update(jid, state="failed", finished_at=now_iso(), error=_scrub(f"{type(e).__name__}: {e}"))
        return 1


# ------------------------------------------------------------------------------------------------------------------ CLI

HELP_DESC = (
    "Tarefas em segundo plano: `submit` volta na hora e a tarefa roda num processo separado (grupo de processos próprio,\n"
    "um loop asyncio por tarefa), sem daemon e sem abrir porta. O estado fica em JSON em <dados>/jobs/<id>/job.json\n"
    "($SIMPLICIO_VIDEO_DATA, padrão ~/.simplicio-video), com escrita atômica.\n\n"
    "Lista fechada de tarefas:\n"
    "  swap-run    swap run em segundo plano. Gasta dinheiro: confirmado AQUI, com --autorizo e --yes (as mesmas checagens\n"
    "              do swap run: estimativa abaixo de --max-usd, chave no ambiente, saída livre). Só pelo terminal\n"
    "  voice       voice em segundo plano. Provedor local (file, local, voxcpm, openvoice) não gasta; provedor de rede\n"
    "              (gemini) pede --yes\n\n"
    "Subcomandos:\n"
    "  submit TIPO ...   cria a tarefa e devolve o id\n"
    "  status ID         estado, tempos, pids e erro (estado lost = o runner morreu; a tarefa que sobrou é encerrada)\n"
    "  list              tarefas, da mais nova para a mais antiga (--state filtra)\n"
    "  result ID         o resultado de uma tarefa terminada (sai com 2 se ainda roda)\n"
    "  cancel ID         SIGINT no grupo da tarefa, SIGKILL depois da tolerância; o swap cancela limpo e grava o manifesto\n"
    "  clean             remove tarefas terminadas há mais de 7 dias (--older-than-days); `submit` também limpa\n\n"
    "Pelo MCP (tool video.jobs): list, status, result, cancel e submit só de voz com provedor local. swap-run nunca.\n"
    "A chave de API fica só no ambiente: argumentos com chave são recusados e nada vai para o estado nem para o log."
)
HELP_EPILOG = (
    "exemplos:\n"
    "  simplicio-video jobs submit voice clients/x/video-01/contract.yaml --provider local\n"
    "  simplicio-video jobs submit swap-run --provider gemini --video in.mp4 --ref avatar.png --out out/swap.mp4 --autorizo --yes\n"
    "  simplicio-video jobs status 20261016-120000-1a2b3c4d --json\n"
    "  simplicio-video jobs list --state running\n"
    "  simplicio-video jobs result 20261016-120000-1a2b3c4d\n"
    "  simplicio-video jobs cancel 20261016-120000-1a2b3c4d"
)


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="simplicio-video jobs", description=HELP_DESC, epilog=HELP_EPILOG,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("submit", help="cria uma tarefa (swap-run | voice)")
    ks = p.add_subparsers(dest="kind")
    s = ks.add_parser("swap-run", help="swap run em segundo plano (gasta: --autorizo e --yes)")
    s.add_argument("--provider", default="gemini")
    s.add_argument("--video")
    s.add_argument("--ref", action="append", default=[], dest="refs")
    s.add_argument("--out")
    s.add_argument("--resolution", default="720p")
    s.add_argument("--autorizo", action="store_true")
    s.add_argument("--yes", action="store_true", help="confirma o gasto (obrigatório)")
    s.add_argument("--max-usd", type=float, default=None, dest="max_usd")
    s.add_argument("--prompt", default="")
    s.add_argument("--timeout", type=float, default=None)
    s.add_argument("--poll-interval", type=float, default=None, dest="poll_interval")
    s.add_argument("--concurrency", type=positive_int, default=None)
    s.add_argument("--aceito-unverified", action="store_true", dest="aceito_unverified")
    s.add_argument("--force", action="store_true")
    s.add_argument("--json", action="store_true")
    v = ks.add_parser("voice", help="voice em segundo plano (provedor de rede pede --yes)")
    v.add_argument("contrato", metavar="CONTRATO.yaml")
    v.add_argument("only", nargs="*", metavar="FALA_ID")
    v.add_argument("--provider", "-p", default=None)
    v.add_argument("--force", action="store_true")
    v.add_argument("--concurrency", type=positive_int, default=None)
    v.add_argument("--yes", action="store_true", help="confirma o gasto de um provedor de rede")
    v.add_argument("--json", action="store_true")
    for name, hlp in (("status", "estado de uma tarefa"), ("result", "resultado de uma tarefa terminada"),
                      ("cancel", "cancela uma tarefa")):
        q = sub.add_parser(name, help=hlp)
        q.add_argument("id")
        q.add_argument("--json", action="store_true")
    q = sub.add_parser("list", help="lista as tarefas")
    q.add_argument("--state", choices=STATES)
    q.add_argument("--json", action="store_true")
    q = sub.add_parser("clean", help="remove tarefas terminadas antigas")
    q.add_argument("--older-than-days", type=float, default=PRUNE_DAYS, dest="days")
    q.add_argument("--json", action="store_true")
    r = sub.add_parser("_run")  # internal: the runner process
    r.add_argument("id")
    return ap


def _emit(obj, as_json: bool, text: str) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2) if as_json else text)


def _line(st: dict) -> str:
    when = st.get("finished_at") or st.get("started_at") or st.get("created_at")
    return f"{st['id']}  {st['state']:<9} {st['kind']:<9} {when}" + (f"  {st['error'][:80]}" if st.get("error") else "")


def _text(st: dict) -> str:
    lines = [f"tarefa {st['id']}: {st['state']}  ({st['kind']}{', gasta dinheiro' if st.get('spends') else ''})",
             f"  criada {st.get('created_at')}  iniciada {st.get('started_at') or '-'}  terminada {st.get('finished_at') or '-'}"]
    if st.get("runner_pid"):
        lines.append(f"  runner pid {st['runner_pid']}, tarefa pid {st.get('task_pid') or '-'} (grupo {st.get('task_pgid') or '-'})")
    if st.get("estimate_usd") is not None:
        lines.append(f"  custo previsto US$ {st['estimate_usd']}")
    if st.get("error"):
        lines.append(f"  erro: {st['error']}")
    if st.get("result"):
        lines.append(f"  resultado: {json.dumps(st['result'], ensure_ascii=False)}")
    lines.append(f"  log: {job_dir(st['id']) / 'output.log'}")
    return "\n".join(lines)


def run_jobs(argv: list[str]) -> int:
    ap = _parser()
    a = ap.parse_args(argv)
    if not a.cmd:
        ap.print_help(sys.stderr)
        return 1
    try:
        if a.cmd == "_run":
            return run_runner(a.id)
        if a.cmd == "submit":
            if not a.kind:
                raise JobError("falta o tipo da tarefa: swap-run | voice")
            if a.kind == "swap-run":
                params = {"provider": a.provider, "video": a.video, "refs": a.refs, "out": a.out, "resolution": a.resolution,
                          "autorizo": a.autorizo, "max_usd": a.max_usd, "prompt": a.prompt, "timeout": a.timeout,
                          "poll_interval": a.poll_interval, "concurrency": a.concurrency,
                          "aceito_unverified": a.aceito_unverified, "force": a.force}
                st = submit("swap-run", params, confirm_yes=a.yes)
            else:
                params = {"contrato": a.contrato, "provider": a.provider, "force": a.force, "only": a.only,
                          "concurrency": a.concurrency}
                st = submit("voice", params, confirm_yes=a.yes)
            _emit(summary(st), a.json, f"tarefa {st['id']} enviada ({st['state']}).\nacompanhe: simplicio-video jobs status {st['id']}")
            return 0
        if a.cmd == "status":
            st = status(a.id)
            _emit(summary(st), a.json, _text(st))
            return 0
        if a.cmd == "list":
            rows = list_jobs(a.state)
            _emit({"jobs": [summary(r) for r in rows]}, a.json, "\n".join(_line(r) for r in rows) or "nenhuma tarefa")
            return 0
        if a.cmd == "result":
            r = result(a.id)
            _emit(r, a.json, _text(status(a.id)))
            return 0 if r["state"] == "done" else 1
        if a.cmd == "cancel":
            st = cancel(a.id)
            _emit(summary(st), a.json, _text(st))
            return 0
        if a.cmd == "clean":
            removed = clean(a.days)
            _emit({"removed": removed}, a.json, f"{len(removed)} tarefa(s) removida(s)")
            return 0
    except JobError as e:
        print(f"jobs: {_scrub(str(e))}", file=sys.stderr)
        return e.code
    return 1
