"""Montage track: Agentic video production platform using OpenMontage (https://github.com/calesthio/OpenMontage).

Invokes OpenMontage production capabilities (backlot, pipelines, tools).
"""
from __future__ import annotations

import argparse
import contextlib
import errno
import hashlib
import json
import math
import os
import re
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from . import tools
from .childio import run_child, under_mcp


class MontageError(Exception):
    pass


OPENMONTAGE_REPO = tools.get("openmontage").source


def _offline() -> bool:
    return os.environ.get("SIMPLICIO_OFFLINE", "").strip().lower() in ("1", "true", "yes", "on")


def default_openmontage_dir() -> Path:
    """Where the pinned checkout lives. First hit wins:
    $OPENMONTAGE_DIR, $SIMPLICIO_OPENMONTAGE_DIR, $SIMPLICIO_TOOLS_DIR/openmontage,
    $SIMPLICIO_VIDEO_DATA/tools/openmontage, ~/.simplicio-video/tools/openmontage."""
    name = tools.get("openmontage").name
    explicit = os.environ.get("OPENMONTAGE_DIR") or os.environ.get("SIMPLICIO_OPENMONTAGE_DIR")
    if explicit:
        return Path(explicit).expanduser()
    if os.environ.get("SIMPLICIO_TOOLS_DIR"):
        return tools.tools_dir() / name
    data = os.environ.get("SIMPLICIO_VIDEO_DATA")
    base = Path(data).expanduser() if data else Path.home() / ".simplicio-video"
    return base / "tools" / name


def find_openmontage_dir() -> Path | None:
    """The pinned OpenMontage checkout (see default_openmontage_dir), or None when not installed."""
    d = default_openmontage_dir()
    return d.resolve() if d.is_dir() and (d / tools.get("openmontage").marker).exists() else None


@contextlib.contextmanager
def _checkout_at(target: Path):
    """Point tools.install at `target` for the duration of the block, then restore the environment."""
    previous = os.environ.get("OPENMONTAGE_DIR")
    os.environ["OPENMONTAGE_DIR"] = str(target)
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("OPENMONTAGE_DIR", None)
        else:
            os.environ["OPENMONTAGE_DIR"] = previous


def clone_openmontage(target_dir: Path | None = None) -> Path:
    """Install OpenMontage at its pinned commit (target_dir overrides the location). Never in offline mode."""
    if _offline():
        raise MontageError(
            "modo offline (SIMPLICIO_OFFLINE=1): não vou clonar o OpenMontage. "
            "Instale fora do modo offline com `simplicio-video montage clone` ou aponte OPENMONTAGE_DIR para um checkout."
        )
    target = Path(target_dir).expanduser() if target_dir is not None else default_openmontage_dir()
    try:
        with _checkout_at(target):
            return Path(tools.install("openmontage"))
    except tools.ToolError as e:
        raise MontageError(str(e)) from None


def ensure_openmontage_dir(target_dir: Path | None = None) -> Path:
    """Find or install OpenMontage."""
    d = find_openmontage_dir()
    if d is not None:
        return d
    return clone_openmontage(target_dir)


# ---------------------------------------------------------------------------------------------------------------------
# Registry / pipelines (read-only). Pipelines are YAML data read here with a safe loader; tools/envelope/estimate need
# upstream code (AGPL), so they run in a child process and only parsed JSON comes back. Never imported by the engine.
# ---------------------------------------------------------------------------------------------------------------------

REGISTRY_COMMANDS = ("pipelines", "tools", "envelope", "estimate", "setup", "status", "run-tool")  # run-tool: see the run-tool section
READ_ONLY_COMMANDS = ("pipelines", "tools", "envelope", "estimate", "status")  # what the MCP tool may run (run-tool is a job there)
RUNTIMES = ("local", "local_gpu", "api", "hybrid")
_CHILD_TIMEOUT = 300
_OPEN_DIAG_TIMEOUT = 8
_WARNED_RELATIVE: set[str] = set()
_HELP_WORDS = ("help", "-h", "--help")  # the engine's own help: never the upstream (`python -m help` was the bug)

# What `montage help` prints, in the terminal and over MCP. Each registry command has its own help: `montage help <comando>`.
USAGE = "\n".join([
    f"OpenMontage ({OPENMONTAGE_REPO})",
    "uso: simplicio-video montage <comando> [args]",
    "",
    "registro (só leitura; `simplicio-video montage help <comando>` mostra a ajuda do comando):",
    "  simplicio-video montage pipelines list|show NOME [--json]     pipelines de pipeline_defs/*.yaml",
    "  simplicio-video montage tools list [--runtime R] [--json]     tools do registro; `tools info NOME` mostra o contrato",
    "  simplicio-video montage envelope [--json] [--full]            o que cada tool declara e o estado ao vivo",
    "  simplicio-video montage estimate NOME --input JSON [--json]   custo e tempo estimados (não executa a tool)",
    "  simplicio-video montage status [--json]                       checkout, pino, venv, módulos que faltam",
    "  simplicio-video montage run-tool NOME --input JSON [--yes]    roda uma tool como tarefa (`run-tool --help`)",
    "instalação (precisa de rede):",
    "  simplicio-video montage clone [dir]                           clona o checkout no commit fixado",
    "  simplicio-video montage setup [--remotion] [--piper]          cria o venv e instala as dependências",
    "outros (open, serve e demo só no terminal):",
    "  simplicio-video montage open | serve [args]                   sobe o board (backlot); não termina sozinho",
    "  simplicio-video montage demo [args]                           render_demo.py do checkout",
    "  simplicio-video montage doctor | preflight                    checagens do checkout",
    "outro argumento vai ao Python do venv (`-m MÓDULO` ou ARQUIVO.py), com o checkout como pasta de trabalho; só no terminal.",
])

# Runs inside the child (cwd = checkout, PYTHONPATH = checkout). Upstream chatter on stdout is sent to stderr so the
# single JSON document on the real stdout stays parseable.
_CHILD = r"""
import json, os, sys
real = os.fdopen(os.dup(1), "w", encoding="utf-8")  # the result goes here; fd 1 now belongs to stderr, so grandchildren and C code cannot corrupt it
os.dup2(2, 1)
sys.stdout = sys.stderr
sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")
sys.path.insert(0, sys.argv[3])  # the checkout: -I ignores PYTHONPATH, so the child puts it first itself
op, payload = sys.argv[1], json.loads(sys.argv[2])
def emit(d):
    real.write(json.dumps(d, default=str)); real.flush()
class _Skipped:
    value = "unknown (probe skipped)"
try:
    from tools.tool_registry import registry
    registry.discover()
    if payload.get("skip_probes"):  # get_status() shells out to npm/npx and calls networks: do not call it at all
        for _n in registry.list_all():
            _t = registry.get(_n)
            if _t is not None:
                _t.get_status = lambda: _Skipped()
except ImportError as e:
    emit({"ok": False, "kind": "import", "missing": [e.name or str(e)], "error": str(e)}); sys.exit(0)
except Exception as e:
    emit({"ok": False, "kind": "upstream", "error": f"{type(e).__name__}: {e}"}); sys.exit(0)
try:
    if op == "envelope":
        emit({"ok": True, "envelope": registry.support_envelope()})
    elif op == "list":
        rows = []
        for name, info in registry.support_envelope().items():
            rows.append({k: info.get(k) for k in ("name", "runtime", "tier", "capability", "provider", "status", "stability")})
        emit({"ok": True, "tools": rows})
    else:
        tool = registry.get(payload["name"])
        if tool is None:
            emit({"ok": False, "kind": "not_found", "error": "tool desconhecido: " + payload["name"], "available": sorted(registry.list_all())})
        elif op == "info":
            emit({"ok": True, "info": tool.get_info()})
        else:
            emit({"ok": True, "estimate": tool.dry_run(payload["input"])})
except Exception as e:
    emit({"ok": False, "kind": "upstream", "error": f"{type(e).__name__}: {e}"})
"""


class _ChildError(MontageError):
    def __init__(self, msg: str, data: dict):
        super().__init__(msg)
        self.data = data


# ---- the OpenMontage venv (outside the checkout, so a re-clone never wipes it) -------------------------------------------

def data_dir() -> Path:
    """Where the venv lives: $OPENMONTAGE_DATA_DIR, else $SIMPLICIO_VIDEO_DATA/openmontage-data (~/.simplicio-video/openmontage-data)."""
    explicit = os.environ.get("OPENMONTAGE_DATA_DIR")
    if explicit:
        path = Path(explicit).expanduser()
        if not path.is_absolute() and explicit not in _WARNED_RELATIVE:
            _WARNED_RELATIVE.add(explicit)
            print(f"montage: aviso: OPENMONTAGE_DATA_DIR relativo ({explicit}) vira {path.resolve()} a partir da pasta atual; "
                  "use um caminho absoluto.", file=sys.stderr)
        return path.resolve()
    data = os.environ.get("SIMPLICIO_VIDEO_DATA")
    base = Path(data).expanduser() if data else Path.home() / ".simplicio-video"
    return (base / "openmontage-data").resolve()


def venv_python() -> Path:
    sub = ("Scripts", "python.exe") if os.name == "nt" else ("bin", "python")
    return data_dir() / "venv" / sub[0] / sub[1]


def upstream_python() -> str:
    """The interpreter every upstream command runs in: the venv's, or a clean error that points at `montage setup`."""
    py = venv_python()
    if not py.is_file():
        raise MontageError(
            f"o venv do OpenMontage não existe ({py.parent.parent}). Rode `simplicio-video montage setup` "
            "(precisa de rede) para criá-lo e instalar as dependências."
        )
    return str(py)


def _upstream_env(om_dir: Path) -> dict:
    env = os.environ.copy()
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = f"{om_dir}{os.pathsep}{existing}" if existing else str(om_dir)
    return env


def _run_step(cmd: list[str], cwd: Path | None = None) -> int:
    env = os.environ.copy()
    env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
    try:
        return run_child(cmd, cwd=cwd, env=env)
    except OSError as e:
        print(f"montage: não consegui rodar {cmd[0]}: {e}", file=sys.stderr)
        return 127
    except KeyboardInterrupt:
        print("montage: interrompido durante o setup", file=sys.stderr)
        return 130


def run_setup(remotion: bool = False, piper: bool = False) -> int:
    """Create the venv, install the upstream requirements.txt (and optionally Remotion / Piper), saying what runs before each step."""
    om_dir = find_openmontage_dir()
    if om_dir is None:
        raise MontageError(f"OpenMontage não encontrado em {default_openmontage_dir()}. Rode `simplicio-video montage clone` primeiro.")
    if _offline():
        raise MontageError("modo offline (SIMPLICIO_OFFLINE=1): não vou instalar o OpenMontage, porque o pip e o npm precisam de rede. "
                           "Rode `simplicio-video montage setup` fora do modo offline.")
    npm = None
    if remotion:
        npm = shutil.which("npm")
        if npm is None:
            raise MontageError("--remotion precisa do npm (Node.js) no PATH e não achei. Instale o Node.js e rode de novo.")
    venv = data_dir() / "venv"
    py = str(venv_python())
    plan: list[tuple[str, list[str], Path | None]] = []
    if not venv_python().is_file():
        plan.append((f"criando o venv em {venv}", [sys.executable, "-m", "venv", str(venv)], None))
    plan.append(("instalando o requirements.txt do OpenMontage com o pip (pode levar vários minutos; o pip mostra o andamento)",
                 [py, "-m", "pip", "install", "-r", str(om_dir / "requirements.txt")], om_dir))
    if remotion:
        plan.append(("npm install em remotion-composer (pode levar alguns minutos)", [npm, "install"], om_dir / "remotion-composer"))
    if piper:
        plan.append(("instalando o piper-tts (voz local) com o pip", [py, "-m", "pip", "install", "piper-tts"], om_dir))
    try:
        data_dir().mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise MontageError(f"não consegui criar a pasta de dados {data_dir()}: {e}") from None
    total = len(plan)
    for i, (what, cmd, cwd) in enumerate(plan, 1):
        print(f"[{i}/{total}] {what}", flush=True)
        t0 = time.monotonic()
        rc = _run_step(cmd, cwd)
        if rc != 0:
            raise MontageError(f"passo {i}/{total} falhou (código {rc}): {' '.join(str(c) for c in cmd[:4])}. A saída acima diz por quê.")
        print(f"[{i}/{total}] ok ({time.monotonic() - t0:.0f}s)", flush=True)
    print(f"OpenMontage pronto: venv em {venv}. Próximo passo: `simplicio-video montage tools list` ou `simplicio-video montage status`.")
    return 0


_STATUS_PROBE = r"""
import importlib.metadata as m, json, re, sys
missing = []
for line in open(sys.argv[1], encoding="utf-8"):
    name = re.split(r"[\s<>=!~;\[#]", line.strip(), maxsplit=1)[0]
    if not name:
        continue
    try:
        m.version(name)
    except m.PackageNotFoundError:
        missing.append(name)
try:
    m.version("piper-tts"); piper = True
except m.PackageNotFoundError:
    piper = False
print(json.dumps({"missing": missing, "piper": piper}))
"""


def status_report() -> dict:
    """Checkout, pin, venv, missing requirements, Remotion and Piper: read-only, asks the venv's own Python."""
    d = find_openmontage_dir()
    pin = tools.effective_ref(tools.get("openmontage"))
    head = None
    if d is not None:
        try:
            head = tools._git("rev-parse", "HEAD", cwd=d)
        except tools.ToolError:
            head = None
    py = venv_python()
    rep = {"ok": True,
           "checkout": {"found": d is not None, "path": str(d or default_openmontage_dir()), "pin": pin, "head": head,
                        "pin_match": (head == pin) if head else None},
           "venv": {"present": py.is_file(), "path": str(py.parent.parent), "python": str(py) if py.is_file() else None},
           "missing_modules": None, "remotion": bool(d and (d / "remotion-composer" / "node_modules").is_dir()), "piper": False}
    if d is not None and py.is_file() and (d / "requirements.txt").is_file():
        try:
            p = subprocess.run([str(py), "-c", _STATUS_PROBE, str(d / "requirements.txt")], capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL)
            probe = json.loads(p.stdout)
            rep["missing_modules"], rep["piper"] = probe["missing"], probe["piper"]
        except (OSError, subprocess.SubprocessError, ValueError, KeyError):
            rep["probe_error"] = "o Python do venv não respondeu"
    return rep


def _run_open(cmd: list[str], cwd: Path, env: dict) -> int:
    """`backlot open` spawns its server with stderr discarded, so when the upstream says it did not come up, run the server
    in the foreground for a few seconds and show why it exits (e.g. ModuleNotFoundError: fastapi)."""
    seen: list[str] = []
    p = subprocess.Popen(cmd, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace", stdin=subprocess.DEVNULL)
    assert p.stdout is not None
    for line in p.stdout:
        seen.append(line)
        sys.stdout.write(line)
        sys.stdout.flush()
    rc = p.wait()
    if "did not come up" in "".join(seen):
        serve = [cmd[0], "-m", "backlot", "serve"] + (["--port", os.environ["BACKLOT_PORT"]] if os.environ.get("BACKLOT_PORT") else [])
        s = subprocess.Popen(serve, cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                             text=True, errors="replace")
        try:
            _, err = s.communicate(timeout=_OPEN_DIAG_TIMEOUT)
            low = (err or "").lower()
            if "address already in use" in low or "errno 98" in low or "10048" in low:
                print("montage: o backlot subiu tarde: a porta já em uso é o servidor que o `open` iniciou. Abra a URL do board no "
                      "navegador ou rode `simplicio-video montage open` de novo.", file=sys.stderr)
            else:
                tail = "\n".join((err or "").strip().splitlines()[-8:]) or f"saiu com código {s.returncode} sem mensagem"
                print(f"montage: o backlot não subiu. Motivo (fim do stderr do servidor):\n{tail}\n"
                      "Se faltam módulos, rode `simplicio-video montage setup`.", file=sys.stderr)
        except subprocess.TimeoutExpired:
            s.kill()
            s.communicate()
            print("montage: o backlot subiu quando rodado em primeiro plano (encerrei o teste); o início pode ter sido lento. "
                  "Tente `simplicio-video montage serve`.", file=sys.stderr)
    return rc


def _require_checkout() -> Path:
    om_dir = find_openmontage_dir()
    if om_dir is None:
        raise MontageError(
            f"OpenMontage não encontrado em {default_openmontage_dir()}. "
            "Rode `simplicio-video montage clone` (ou defina OPENMONTAGE_DIR apontando para um checkout)."
        )
    return om_dir


def list_pipelines(om_dir: Path | None = None) -> tuple[list[dict], list[dict]]:
    """(entries, erros): every pipeline_defs/*.yaml as {file, doc} (safe loader; the file stem is the fallback name),
    and the files that could not be read as {arquivo, motivo}. A broken file never hides the others."""
    import yaml  # lazy: cli imports this module and the install path must work before PyYAML exists

    om_dir = om_dir or _require_checkout()
    out: list[dict] = []
    erros: list[dict] = []
    for f in sorted((om_dir / "pipeline_defs").glob("*.yaml")):
        try:
            doc = yaml.safe_load(f.read_text(encoding="utf8"))
        except (yaml.YAMLError, OSError, UnicodeDecodeError) as e:
            erros.append({"arquivo": f.name, "motivo": (str(e).splitlines() or [type(e).__name__])[0]})
            continue
        if not isinstance(doc, dict):
            erros.append({"arquivo": f.name, "motivo": "não é um mapa YAML"})
            continue
        doc.setdefault("name", f.stem)
        out.append({"file": f.name, "doc": doc})
    return out, erros


def pipeline_summary(entry: dict) -> dict:
    d = entry["doc"]
    return {"name": d["name"], "version": d.get("version"), "category": d.get("category"),
            "stability": d.get("stability"), "description": " ".join(str(d.get("description") or "").split()),
            "file": entry["file"]}


def show_pipeline(name: str, om_dir: Path | None = None) -> dict:
    entries, erros = list_pipelines(om_dir)
    for e in entries:  # only names found in the listing match, so `name` never becomes a path
        if name in (e["doc"]["name"], Path(e["file"]).stem):
            return e["doc"]
    for er in erros:
        if name == Path(er["arquivo"]).stem:
            raise MontageError(f"pipeline_defs/{er['arquivo']} ilegível: {er['motivo']}")
    raise MontageError(f"pipeline desconhecido: {name!r}. Disponíveis: {', '.join(str(e['doc']['name']) for e in entries) or '(nenhum)'}")


def _child(op: str, payload: dict) -> dict:
    """Run one registry operation of the upstream in a separate process; return its parsed JSON answer."""
    om_dir = _require_checkout()
    py = upstream_python()
    env = _child_env(_registry_keys(), neutral=_neutral_keys(om_dir) if under_mcp() else ())  # minimal; under MCP no .env keys
    skip = _offline() or under_mcp()  # no network probes offline or under the MCP server; the terminal keeps the live ones
    if skip:
        env["npm_config_offline"] = "true"
        payload = {**payload, "skip_probes": True}
    try:
        p = subprocess.run([py, "-I", "-c", _CHILD, op, json.dumps(payload), str(om_dir)], cwd=om_dir, env=env,
                           stdin=subprocess.DEVNULL, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=_CHILD_TIMEOUT)
    except subprocess.TimeoutExpired:
        raise MontageError(f"o OpenMontage não respondeu em {_CHILD_TIMEOUT}s") from None
    except OSError as e:
        raise _spawn_error(e, py) from None
    try:
        data = json.loads(p.stdout)
    except ValueError:
        tail = (p.stderr or "").strip().splitlines()[-1:] or ["sem saída"]
        raise MontageError(f"o OpenMontage terminou sem JSON (código {p.returncode}): {tail[0]}") from None
    if data.get("ok"):
        return data
    kind = data.get("kind")
    if kind == "import":
        missing = ", ".join(data.get("missing") or ["?"])
        raise _ChildError(
            f"faltam dependências do OpenMontage no venv ({py}): {missing}. Rode `simplicio-video montage setup` para instalá-las.", data)
    if kind == "not_found":
        raise _ChildError(f"{data['error']}. Veja `simplicio-video montage tools list`.", data)
    raise _ChildError(f"o OpenMontage falhou: {data.get('error')}", data)


def _envelope_summary(env: dict) -> dict:
    def count(key):
        out: dict = {}
        for info in env.values():
            out[str(info.get(key))] = out.get(str(info.get(key)), 0) + 1
        return dict(sorted(out.items()))
    return {"count": len(env), "by_runtime": count("runtime"), "by_tier": count("tier"), "tools": sorted(env)}


def _relative_paths(value) -> list[str]:
    """Strings in `value` that look like a relative path (a slash, no spaces, not a URL, not absolute)."""
    if isinstance(value, str):
        looks = ("/" in value or "\\" in value) and not any(c.isspace() for c in value) and "://" not in value
        return [value] if looks and not os.path.isabs(value) else []
    if isinstance(value, dict):
        return [x for v in value.values() for x in _relative_paths(v)]
    if isinstance(value, list):
        return [x for v in value for x in _relative_paths(v)]
    return []


def _registry_parser() -> argparse.ArgumentParser:
    fmt = argparse.RawDescriptionHelpFormatter
    prog = "simplicio-video montage"
    ap = argparse.ArgumentParser(prog=prog, formatter_class=fmt,
                                 description="Registro do OpenMontage (somente leitura): pipelines, tools, envelope, estimativa.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def examples(lines):
        return "exemplos:\n" + "\n".join(f"  {prog} {x}" for x in lines)

    def add(parent, name, help_, ex):
        p = parent.add_parser(name, formatter_class=fmt, help=help_, description=help_, epilog=examples(ex))
        p.add_argument("--json", action="store_true", help="saída JSON para máquinas")
        return p

    pl = sub.add_parser("pipelines", formatter_class=fmt, help="pipelines (pipeline_defs/*.yaml)",
                        description="Pipelines do OpenMontage, lidos do YAML do checkout.",
                        epilog=examples(["pipelines list --json", "pipelines show cinematic --json"]))
    pls = pl.add_subparsers(dest="sub", required=True)
    add(pls, "list", "lista os pipelines", ["pipelines list", "pipelines list --json"])
    add(pls, "show", "mostra a definição de um pipeline", ["pipelines show cinematic", "pipelines show cinematic --json"]).add_argument("name")

    tl = sub.add_parser("tools", formatter_class=fmt, help="tools do registro",
                        description="Tools do OpenMontage (runtime local, local_gpu, api ou hybrid).",
                        epilog=examples(["tools list --runtime api --json", "tools info NOME --json"]))
    tls = tl.add_subparsers(dest="sub", required=True)
    add(tls, "list", "lista as tools", ["tools list", "tools list --runtime local_gpu --json"]).add_argument(
        "--runtime", choices=RUNTIMES, help="filtra pelo runtime declarado")
    add(tls, "info", "contrato completo de uma tool (get_info, input_schema)", ["tools info NOME --json"]).add_argument("name")

    st = add(sub, "setup", "cria o venv do OpenMontage e instala as dependências (precisa de rede; só no terminal)",
             ["setup", "setup --remotion --piper"])
    st.add_argument("--remotion", action="store_true", help="também roda npm install em remotion-composer")
    st.add_argument("--piper", action="store_true", help="também instala o piper-tts (voz local)")
    add(sub, "status", "checkout, pino, venv, módulos que faltam, Remotion e Piper", ["status --json"])
    en = add(sub, "envelope", "support_envelope(): o que cada tool declara e o estado ao vivo", ["envelope --json", "envelope --json --full"])
    en.add_argument("--full", action="store_true", help="o envelope inteiro (sob o servidor MCP o padrão é um resumo)")
    e = add(sub, "estimate", "custo e tempo estimados (dry_run do upstream; não executa a tool)",
            ['estimate NOME --input \'{"prompt": "um gato"}\' --json'])
    e.add_argument("name")
    e.add_argument("--input", default="{}", metavar="JSON", help="entradas da tool, um objeto JSON (padrão: {})")
    return ap


def _print(data, as_json: bool) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=None if as_json else 2))


def run_registry(args: list[str]) -> int:
    ns = _registry_parser().parse_args(args)
    try:
        return _run_registry(ns)
    except MontageError as e:
        if getattr(ns, "json", False):
            extra = {k: v for k, v in getattr(e, "data", {}).items() if k in ("missing", "available")}
            _print({"ok": False, "error": str(e), **extra}, True)
        raise


def _run_registry(ns: argparse.Namespace) -> int:
    if ns.cmd == "pipelines":
        if ns.sub == "list":
            entries, erros = list_pipelines()
            rows = [pipeline_summary(e) for e in entries]
            if ns.json:
                _print({"ok": True, "pipelines": rows, "erros": erros}, True)
            else:
                for er in erros:
                    print(f"montage: aviso: pipeline_defs/{er['arquivo']} ignorado: {er['motivo']}", file=sys.stderr)
                for r in rows:
                    print(f"{r['name']:<24} {r['category'] or '-':<12} {r['stability'] or '-':<12} {r['description'][:70]}")
        else:
            _print(show_pipeline(ns.name), ns.json)
    elif ns.cmd == "tools" and ns.sub == "list":
        rows = _child("list", {})["tools"]
        if ns.runtime:
            rows = [r for r in rows if r.get("runtime") == ns.runtime]
        if ns.json:
            _print({"ok": True, "tools": rows}, True)
        else:
            for r in rows:
                print(f"{r['name']:<28} {r['runtime']:<10} {r['status']:<12} {r['capability']}")
    elif ns.cmd == "tools":
        _print(_child("info", {"name": ns.name})["info"], ns.json)
    elif ns.cmd == "setup":
        return run_setup(ns.remotion, ns.piper)
    elif ns.cmd == "status":
        rep = status_report()
        if ns.json:
            _print(rep, True)
        else:
            c, v = rep["checkout"], rep["venv"]
            pin = "confere" if c["pin_match"] else "NÃO confere" if c["pin_match"] is False else "?"
            print(f"checkout: {c['path']} ({'encontrado' if c['found'] else 'ausente: rode montage clone'}; pino {pin})")
            print(f"venv: {v['path']} ({'presente' if v['present'] else 'ausente: rode montage setup'})")
            print(f"módulos que faltam: {rep['missing_modules'] if rep['missing_modules'] is not None else '?'}")
            print(f"remotion: {'sim' if rep['remotion'] else 'não'}; piper: {'sim' if rep['piper'] else 'não'}")
    elif ns.cmd == "envelope":
        env = _child("envelope", {})["envelope"]
        if under_mcp() and not ns.full:
            _print({"ok": True, "summary": _envelope_summary(env), "note": "resumo; passe --full para o envelope inteiro (centenas de KB)"}, True)
        else:
            _print({"ok": True, "envelope": env} if ns.json else env, ns.json)
    else:  # estimate
        try:
            inputs = json.loads(ns.input)
        except ValueError as e:
            raise MontageError(f"--input não é JSON válido: {e}") from None
        if not isinstance(inputs, dict):
            raise MontageError("--input precisa ser um objeto JSON ({...})")
        rel = _relative_paths(inputs) if under_mcp() else []
        if rel:  # a relative path would resolve against the server's cwd, and estimate would probe whether it exists
            raise MontageError(f"sob o MCP os caminhos em --input precisam ser absolutos; recebi: {', '.join(rel[:3])}")
        _print(_child("estimate", {"name": ns.name, "input": inputs})["estimate"], ns.json)
    return 0


def _help(topic: list[str]) -> int:
    """`montage help [comando]`: the engine's own help, read-only, and never the upstream. run-tool and the registry commands
    print the help of their own parser (the same text as `montage <comando> --help`); anything else prints USAGE. Without the
    checkout, USAGE is followed by how to get it."""
    try:
        if topic and topic[0] == "run-tool":
            run_tool_cli(["--help"])
        elif topic and topic[0] in REGISTRY_COMMANDS:
            run_registry([*topic, "--help"])
        else:
            print(USAGE)
            if find_openmontage_dir() is None:
                print("\nOpenMontage não foi encontrado localmente.\n"
                      "Para clonar e inicializar, execute:\n"
                      "  simplicio-video montage clone [diretório]\n"
                      "  ou defina OPENMONTAGE_DIR apontando para o checkout.\n"
                      f"Local padrão: {default_openmontage_dir()} ($SIMPLICIO_VIDEO_DATA/tools/openmontage).")
    except SystemExit as e:  # argparse printed the help and ends with its code (0; 2 for a word it does not know)
        return e.code if isinstance(e.code, int) else 0
    return 0


def run_montage(args: list[str], cwd: Path | None = None) -> int:
    """Execute OpenMontage with arguments."""
    if args and args[0] in _HELP_WORDS:
        return _help(args[1:])
    if args and args[0] == "run-tool":
        return run_tool_cli(args[1:])
    if args and args[0] in REGISTRY_COMMANDS:
        return run_registry(args)

    if args and args[0] in ("clone", "--clone"):
        target = Path(args[1]) if len(args) > 1 else None
        clone_openmontage(target)
        return 0

    om_dir = find_openmontage_dir()
    if om_dir is None:
        if not args:
            return _help([])  # sem checkout, `montage` sozinho mostra a ajuda e diz como obter o checkout
        om_dir = ensure_openmontage_dir()

    workdir = cwd or om_dir
    py = upstream_python()

    first = args[0] if args else "open"
    if first == "open":
        cmd = [py, "-m", "backlot", "open"] + args[1:]
    elif first == "serve":
        cmd = [py, "-m", "backlot", "serve"] + args[1:]
    elif first == "demo":
        cmd = [py, "render_demo.py"] + args[1:]
    elif first in ("doctor", "hyperframes-doctor"):
        cmd = [
            py, "-c",
            "from tools.video.hyperframes_compose import HyperFramesCompose; "
            "r=HyperFramesCompose().execute({'operation':'doctor'}); "
            "import json; print(json.dumps(r.data, indent=2)); "
            "print('OK' if r.success else f'FAIL: {r.error}')"
        ]
    elif first == "preflight":
        cmd = [
            py, "-c",
            "from tools.tool_registry import registry; import json; "
            "registry.discover(); print(json.dumps(registry.provider_menu(), indent=2))"
        ]
    else:
        if args and args[0].endswith(".py"):
            cmd = [py] + args
        elif args and args[0] in ("-m", "-c"):
            cmd = [py] + args
        elif args:
            cmd = [py, "-m"] + args
        else:
            cmd = [py, "-m", "backlot", "open"]

    env = _upstream_env(om_dir)
    if first == "open":
        return _run_open(cmd, cwd=workdir, env=env)
    return run_child(cmd, cwd=workdir, env=env)


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    try:
        return run_montage(args)
    except MontageError as e:
        print(f"montage: {e}", file=sys.stderr)
        return 1


# ---------------------------------------------------------------------------------------------------------------------
# run-tool (T2c): ONE upstream tool through the bridge. The gate reads the upstream metadata (tier, runtime,
# resource_profile.network_required, the declared env keys) and the estimate; what the metadata does not say counts as
# the riskier case. Over MCP a tool must also be on MCP_ALLOWLIST, which was read by hand in the pinned checkout.
#   terminal: any tool. A runtime other than local, a cost above zero, an unknown or non-finite cost, or a network need run
#             only with --yes, after the estimate is printed. The publish tier never runs.
#   MCP (strict): a reviewed tool, local, free, offline, with absolute paths and new outputs (no link on the way, not under
#             the run folder or the checkout), and no URL or scheme anywhere in the input. It runs as the job `montage-tool`,
#             in its own process, with --sob-mcp, so the strict gate runs again right before the tool.
# The upstream code runs only in the venv's Python, with -I (no PYTHONPATH and no cwd on sys.path; the child inserts the
# checkout itself), with a minimal environment, and under a timeout that kills the whole process group.
# ---------------------------------------------------------------------------------------------------------------------

RUN_TOOL_MAX_INPUT = 100_000  # bytes of the serialized --input as it is passed in argv (ensure_ascii: é is six bytes)
RUN_TIMEOUT_DEFAULT = 1800.0  # seconds; SIMPLICIO_MONTAGE_TIMEOUT or --timeout change it

# The tools an MCP run may execute. Each was read by hand in the pinned checkout: its subprocess calls are ffmpeg or ffprobe
# only, it opens no URL, runs no code or template from the input, downloads no model and captures nothing. `outputs` names
# the input keys that are written files or folders: they get the output checks even when their names do not look like outputs.
MCP_ALLOWLIST: dict[str, dict] = {
    # operations: the only ones that run over MCP. concat writes and deletes the side folder .concat_tmp next to the output,
    # so it stays on the terminal. Side folders checked: cut and speed create none.
    "video_trimmer": {"outputs": ("output_path",), "operations": ("cut", "speed"),
                      "why": "ffmpeg apenas (cut e speed; concat fica no terminal: usa a pasta lateral .concat_tmp, que apaga "
                             "arquivos). Pastas laterais conferidas: cut e speed não criam nenhuma; a saída é um arquivo novo"},
    # Side folders checked: none, it reads the input and prints.
    "audio_probe": {"outputs": (), "why": "ffprobe apenas; só lê o arquivo de entrada e não cria nada ao lado (pasta lateral conferida: "
                                          "nenhuma)"},
    # Side folders checked: writes the frames into the output folder only, and only lists it (no delete, no rename).
    "frame_sampler": {"outputs": ("output_dir",), "why": "ffmpeg e ffprobe apenas; grava os quadros na pasta de saída e só a lista "
                                                         "(pasta lateral conferida: nenhuma)"},
    # Side folders checked: writes the scene list to the output file, no temporary folder (pastas laterais conferidas).
    "scene_detect": {"outputs": ("output_path",), "why": "ffmpeg e ffprobe apenas; grava a lista de cenas num arquivo novo, sem "
                                                         "pasta lateral (conferido)"},
}

_TOOL_NAME = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,79}$")
_PATH_KEY = re.compile(r"(^|_)(path|paths|file|files|dir|dirs|folder|folders|src|source|dst|dest|destination|input|output|out|"
                       r"video|videos|audio|image|images|clip|clips)$", re.I)
_OUT_KEY = re.compile(r"(^|_)(output|out|dest|destination|dst)(s|_path|_paths|_dir|_file|_folder)?$", re.I)
# A URI scheme (file:, data:, pipe:, https:...) at the start of a value. Colons inside an absolute path are not schemes.
_SCHEME = re.compile(r"\s*[A-Za-z][A-Za-z0-9+.\-]*:")
# A Windows drive (C:\ or C:/): a single letter, a colon and a separator, which the scheme rule must not take for a scheme.
_DRIVE = re.compile(r"\s*[A-Za-z]:[\\/]")
# ffmpeg protocol prefixes that take commas instead of a colon (subfile,,start,0,...:/x), at the start of a value.
_FF_PROTO = re.compile(r"\s*(subfile|concat|pipe|fd|tcp|udp|http|https|rtmp|file|data|crypto|async|cache|hls)(?=[,:|])", re.I)
# What a child's variable is set to when the checkout's .env would set it (upstream keeps a key already present, even empty).
# FFREPORT=\"\" would still make ffmpeg write a report file: a log to /dev/null writes nothing.
_NEUTRAL = {"FFREPORT": "file=/dev/null"}
_RUN_DIR = "run"  # under data_dir(): the working folder of the strict runs, never the caller's cwd
_RESULT_DIR = ".resultados"  # under jobs_dir(): one result file per MCP job (the job id is made after the spec)
_ENV_KEEP = ("PATH", "HOME", "LANG", "LC_ALL", "LC_CTYPE", "TMPDIR", "TEMP", "TMP", "USER", "SYSTEMROOT", "PATHEXT",
             "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "no_proxy", "all_proxy",
             "SSL_CERT_FILE", "SSL_CERT_DIR", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE", "NODE_EXTRA_CA_CERTS", "PIP_CERT")

# Runs with the venv's Python (-I). The checkout is inserted in sys.path by the child. Same stdout trick as _CHILD: the
# result is written to the real fd 1 (ASCII JSON) and everything the upstream prints goes to stderr.
_RUN_CHILD = r"""
import json, os, sys
real = os.fdopen(os.dup(1), "w", encoding="utf-8")
os.dup2(2, 1)
sys.stdout = sys.stderr
sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")
sys.path.insert(0, sys.argv[1])
name, inputs = sys.argv[2], json.loads(sys.argv[3])
def emit(d):
    real.write(json.dumps(d, default=str)); real.flush()
try:
    from tools.tool_registry import registry
    registry.discover()
    tool = registry.get(name)
    if tool is None:
        emit({"ok": False, "kind": "not_found", "error": "tool desconhecido: " + name}); sys.exit(0)
    try:
        res = tool.execute(inputs)
        if hasattr(res, "success"):
            data = {"success": bool(res.success), "data": res.data, "artifacts": [str(a) for a in (res.artifacts or [])],
                    "error": res.error, "cost_usd": res.cost_usd, "duration_seconds": res.duration_seconds,
                    "seed": res.seed, "model": res.model}
        else:
            data = {"success": False, "error": "a tool não devolveu um ToolResult (devolveu " + type(res).__name__ + ")",
                    "data": {}, "artifacts": []}
    except Exception as e:  # the tool failed: that is a failed result, not a crash of the bridge
        data = {"success": False, "error": f"{type(e).__name__}: {e}", "data": {}, "artifacts": []}
    emit({"ok": True, "result": data})
except ImportError as e:
    emit({"ok": False, "kind": "import", "missing": [e.name or str(e)], "error": str(e)})
except Exception as e:
    emit({"ok": False, "kind": "upstream", "error": f"{type(e).__name__}: {e}"})
"""


def input_json(inputs: dict) -> str:
    """The --input text as it travels in argv: ASCII only, so its length is the number of bytes the argv limit counts."""
    return json.dumps(inputs, ensure_ascii=True, separators=(",", ":"))


def _run_timeout(explicit: float | None = None) -> float:
    if explicit is not None:
        return float(explicit)
    raw = os.environ.get("SIMPLICIO_MONTAGE_TIMEOUT", "").strip()
    try:
        v = float(raw) if raw else RUN_TIMEOUT_DEFAULT
    except ValueError:
        v = RUN_TIMEOUT_DEFAULT
    return v if v > 0 and math.isfinite(v) else RUN_TIMEOUT_DEFAULT


def _dotenv_keys(om_dir: Path) -> list[str]:
    """The names the checkout's .env sets, read the way the upstream base_tool reads it (only the names are used here)."""
    try:
        text = (Path(om_dir) / ".env").read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []
    keys = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key = line.partition("=")[0].strip()
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            keys.append(key)
    return keys


def _neutral_keys(om_dir: Path) -> list[str]:
    """Under MCP the checkout's .env keys are set in the child first, so the upstream does not load them (FFREPORT always)."""
    return sorted(set(_dotenv_keys(om_dir)) | {"FFREPORT"})


def _child_env(keys=(), neutral=()) -> dict:
    """The environment of a child: what it needs to run, the named provider keys, and the neutral values for the names in
    `neutral` that the child does not already have (nothing else)."""
    env = {k: os.environ[k] for k in _ENV_KEEP if k in os.environ}
    env.update({k: os.environ[k] for k in keys if k in os.environ})
    for k in neutral:
        if k not in env:
            env[k] = _NEUTRAL.get(k, "")
    return env


def _registry_keys() -> list[str]:
    """The registry child (info, estimate) keeps the provider keys the terminal has, because their status reads them;
    under MCP it gets none."""
    if under_mcp():
        return []
    return [k for k in os.environ if re.search(r"(_API_KEY|_TOKEN|_KEY)$", k)]


def _spawn_error(e: OSError, py) -> MontageError:
    if e.errno == errno.E2BIG:
        return MontageError("o input é grande demais para o sistema operacional (E2BIG): use caminhos em vez de conteúdo, "
                            "ou um input menor")
    return MontageError(f"não consegui rodar o Python do venv ({py}): {e}")


# How often the descendants of a running tool are looked for (POSIX with /proc). A descendant that starts and reparents
# between two looks is missed: this bounds the gap, it does not close it.
_POLL_S = 0.05


def _proc_stat(pid: int):
    """(state, ppid, starttime) from /proc/<pid>/stat, or None when the process is gone (POSIX with /proc only)."""
    try:
        with open(f"/proc/{pid}/stat", encoding="ascii", errors="replace") as f:
            rest = f.read().rsplit(")", 1)[1].split()
        return rest[0], int(rest[1]), rest[19]  # the fields after the command name: state, ppid, ..., starttime (22nd field)
    except (OSError, ValueError, IndexError):
        return None


def _descendants(root: int) -> dict[int, str]:
    """pid -> start time of every live descendant of `root`, found by walking the PPID links in /proc. Without /proc (macOS,
    Windows) nothing is found: a grandchild that left the process group is then not seen, and only the child is killed."""
    if not os.path.isdir("/proc/self"):
        return {}
    children: dict[int, list[int]] = {}
    starts: dict[int, str] = {}
    for name in os.listdir("/proc"):
        if not name.isdigit():
            continue
        st = _proc_stat(int(name))
        if st is None:
            continue
        _state, ppid, start = st
        children.setdefault(ppid, []).append(int(name))
        starts[int(name)] = start
    found: dict[int, str] = {}
    frontier = [root]
    while frontier:
        parent = frontier.pop()
        for pid in children.get(parent, ()):
            if pid not in found and pid != root:
                found[pid] = starts[pid]
                frontier.append(pid)
    return found


def _wait_watching(proc, limit: float, seen: dict) -> None:
    """Waits for the child up to `limit` s, recording its descendants in `seen` on the way, every _POLL_S."""
    t_end = time.monotonic() + limit
    while True:
        seen.update(_descendants(proc.pid))
        remaining = t_end - time.monotonic()
        if remaining <= 0:
            raise subprocess.TimeoutExpired(proc.args, limit)
        try:
            proc.wait(timeout=min(_POLL_S, remaining))
            return
        except subprocess.TimeoutExpired:
            continue


def _kill_survivors(seen: dict) -> None:
    """Kills the descendants recorded while the tool ran that are still the same process (same start time, not a zombie).
    A descendant that left the group and outlived its parent is reparented, so it is found only through this record."""
    for pid, start in seen.items():
        st = _proc_stat(pid)
        if st is None or st[2] != start or st[0] == "Z":
            continue
        with contextlib.suppress(ProcessLookupError, PermissionError, OSError):
            os.kill(pid, getattr(signal, "SIGKILL", signal.SIGTERM))


def _read_text(f) -> str:
    f.seek(0)
    return f.read().decode("utf-8", "replace")


def _kill_group(proc) -> None:
    with contextlib.suppress(ProcessLookupError, PermissionError, OSError):
        if hasattr(os, "killpg"):
            os.killpg(proc.pid, signal.SIGKILL)  # the child started its own session: its pid is the group id
        else:
            proc.kill()


def _network_flag(info: dict) -> bool | None:
    net = (info.get("resource_profile") or {}).get("network_required")
    return net if isinstance(net, bool) else None  # None: the metadata does not say


def _cost(estimate: dict | None) -> float | None:
    c = (estimate or {}).get("estimated_cost_usd")
    if isinstance(c, bool) or not isinstance(c, (int, float)) or not math.isfinite(c):
        return None  # quote required, unknown, NaN or infinite: all of them count as unknown
    return float(c)


def _declared_env_keys(info: dict) -> list[str]:
    return [d[4:] for d in info.get("dependencies") or [] if isinstance(d, str) and d.startswith("env:")]


def _all_strings(value, key: str = ""):
    """(key, text) for every string in `value`, at any depth."""
    if isinstance(value, dict):
        for k, v in value.items():
            yield from _all_strings(v, str(k))
    elif isinstance(value, list):
        for v in value:
            yield from _all_strings(v, key)
    elif isinstance(value, str):
        yield key, value


def _path_values(value, key: str = ""):
    """(key, text) for each string that looks like a path: under a path-named key (`input_path: "clip.mp4"` has no slash,
    so the estimate check alone would let it through) or with a slash, no spaces and no URL (`_relative_paths`)."""
    if isinstance(value, dict):
        for k, v in value.items():
            yield from _path_values(v, str(k))
    elif isinstance(value, list):
        for v in value:
            yield from _path_values(v, key)
    elif isinstance(value, str) and value and "://" not in value:
        if (key and _PATH_KEY.search(key)) or _relative_paths(value):
            yield key, value


_SISTEMA_POSIX = ("/etc", "/usr", "/bin", "/sbin", "/lib", "/lib32", "/lib64", "/libx32", "/boot", "/dev", "/proc", "/sys",
                  "/run", "/opt", "/srv", "/snap", "/System", "/Library", "/Applications", "/private/etc", "/var/lib",
                  "/var/log", "/var/spool", "/var/run", "/var/db")  # /var as a whole is refused too, except /var/tmp
_SISTEMA_WINDOWS = ("SYSTEMROOT", "PROGRAMFILES", "PROGRAMFILES(X86)", "PROGRAMDATA")
_INICIO_AUTOMATICO = (("Library", "LaunchAgents"), ("Library", "LaunchDaemons"),
                      ("AppData", "Roaming", "Microsoft", "Windows", "Start Menu", "Programs", "Startup"))


def _dentro(caminho: Path, pasta) -> bool:
    """True when `caminho` is `pasta` or lies under it; both are real paths (links resolved), compared part by part."""
    b = Path(os.path.realpath(pasta)).parts
    return Path(caminho).parts[:len(b)] == b


def _lugar_proibido(real: Path) -> str:
    """Why an MCP output may not be written at `real` (links already resolved), or ''. It mirrors instagram._lugar_proibido and
    adds the engine's own places: its data (jobs, tools, the venv), its code, the checkout, any venv and any site-packages."""
    from . import jobs
    if _dentro(real, Path(__file__).resolve().parent):
        return "dentro do código do motor"
    if _dentro(real, find_openmontage_dir() or default_openmontage_dir()):
        return "dentro do checkout do OpenMontage"
    if any(_dentro(real, pasta) for pasta in (jobs.data_root(), data_dir(), tools.tools_dir())):
        return "dentro da pasta de dados do motor (jobs, tools, openmontage-data)"
    if "site-packages" in real.parts:
        return "dentro de site-packages (pacotes de um venv)"
    if any((a / "pyvenv.cfg").is_file() for a in real.parents):
        return "dentro de um venv (pyvenv.cfg)"
    raizes = [Path(r) for r in _SISTEMA_POSIX] + [Path(v) for v in (os.environ.get(n) for n in _SISTEMA_WINDOWS) if v]
    if any(_dentro(real, r) for r in raizes) or (_dentro(real, "/var") and not _dentro(real, "/var/tmp")):
        return "em pasta do sistema"
    home = Path(os.path.realpath(os.path.expanduser("~")))
    if any(_dentro(real, home.joinpath(*partes)) for partes in _INICIO_AUTOMATICO):
        return "em pasta de início automático (LaunchAgents, LaunchDaemons, Startup)"
    if _dentro(real, home):
        partes = real.parts[len(home.parts):]
        if partes and partes[0].startswith("."):
            return "em pasta oculta do home (.ssh, .config, .claude...)"
    if ".git" in real.parts:
        return "dentro de uma pasta .git"
    return ""


def _output_refusal(key: str, text: str) -> str | None:
    """An output the tool writes: a new name, reached only through real folders (no link on the way), in a place the engine
    may write. The side folders of the allowlisted tools were checked (see MCP_ALLOWLIST)."""
    p = Path(text)
    for a in [p.parent, *p.parent.parents]:  # every folder on the way, the first one included
        if os.path.islink(a):
            return f"a saída {key} passa por um link simbólico ({a}); escreva em pasta real, sem link no caminho"
    if os.path.realpath(p.parent) != str(p.parent):
        return f"a saída {key} não é um caminho limpo ({text}): sem .. nem link no caminho"
    if os.path.lexists(p):
        return f"a saída {key} já existe ou é um link ({text}); a saída tem que ser um arquivo novo"
    motivo = _lugar_proibido(Path(os.path.realpath(p.parent)) / p.name)
    if motivo:
        return f"a saída {key} cai {motivo} ({text}); pelo MCP o motor não grava aí"
    return None


def _input_refusal(key: str, text: str) -> str | None:
    """An input file: a regular file (or a name that does not exist yet, which the tool reports itself). A device, a pipe,
    a socket or a folder would block or read something else."""
    try:
        mode = os.stat(text).st_mode
    except FileNotFoundError:
        return None
    except OSError:
        return f"a entrada {key} não pode ser lida ({text})"
    if not stat.S_ISREG(mode):
        return (f"a entrada {key} não é um arquivo comum ({text}): dispositivo, pipe, soquete ou pasta não entram pelo MCP")
    return None


def _strict_input_refusal(inputs: dict, schema: dict | None, declared: tuple) -> str | None:
    """Over MCP: no URL, no URI scheme and no protocol prefix anywhere (a colon inside an absolute path is fine); every path
    absolute; every input a regular file; every output new and reached through real folders, in a place the engine may
    write; an output the tool takes (in its schema or declared on the allowlist) must be given."""
    for key, text in _all_strings(inputs):
        if "://" in text or (_SCHEME.match(text) and not _DRIVE.match(text)) or _FF_PROTO.match(text):
            return (f"o MCP não busca endereços nem usa esquemas e prefixos de protocolo ({key}: {text[:60]!r}); "
                    "dê um caminho absoluto de arquivo")
    for key, text in _all_strings(inputs):
        if key in declared or _OUT_KEY.search(key):
            if not os.path.isabs(text):
                return f"os caminhos precisam ser absolutos ({key}: {text!r})"
            msg = _output_refusal(key, text)
            if msg:
                return msg
    for key, text in _path_values(inputs):
        if not os.path.isabs(text):
            return f"os caminhos precisam ser absolutos ({key}: {text!r})"
        if key in declared or _OUT_KEY.search(key):
            continue
        msg = _input_refusal(key, text)
        if msg:
            return msg
    for prop in set((schema or {}).get("properties") or {}) | set(declared):
        if (_OUT_KEY.search(prop) or prop in declared) and not inputs.get(prop):
            return f"a tool tem uma saída ({prop}) e, sem ela, escolhe o destino; dê um caminho absoluto e novo em {prop}"
    return None


def _schema_errors(name: str, schema: dict, inputs: dict) -> list[str]:
    """The input against the upstream input_schema (jsonschema is a core dependency). A schema that does not check is an error:
    without it the input cannot be validated, so nothing runs."""
    import jsonschema

    if not schema:
        return []
    try:
        cls = jsonschema.validators.validator_for(schema)
        cls.check_schema(schema)
    except jsonschema.exceptions.SchemaError as e:
        raise MontageError(f"o schema de entrada de {name} é inválido ({e.message}); sem ele não valido a entrada, então não rodo")
    errs = sorted(cls(schema).iter_errors(inputs), key=lambda e: [str(p) for p in e.path])
    return [f"{'.'.join(str(p) for p in e.path) or 'entrada'}: {e.message}" for e in errs]


def _spend_reasons(runtime, network: bool | None, cost: float | None) -> list[str]:
    """Why a run needs --yes; empty means local, offline and free. What the metadata does not say counts as the riskier case.
    The early MCP check passes cost=0.0, so only the runtime and network reasons come back there."""
    out = []
    if runtime != "local":
        out.append(f"runtime {runtime}")
    if network is not False:
        out.append("rede" if network else "rede (o metadado não diz)")
    if cost is None:
        out.append("custo não estimado")
    elif cost > 0:
        out.append(f"custa US$ {cost:.2f}")
    return out


def _refuse(plan: dict, msg: str, *, yes_hint: bool = False, hint: bool = True) -> dict:
    """Sets the refusal. Over MCP it names the terminal command that does the same run, except for the publish tier."""
    if plan["strict"] and hint:
        cmd = f"simplicio-video montage run-tool {plan['tool']} --input JSON" + (" --yes" if yes_hint else "")
        msg = f"{msg}. Pelo MCP esta tool não roda; no terminal: `{cmd}`"
    plan["refusal"] = msg
    return plan


def run_tool_plan(name, inputs, *, strict: bool, yes: bool) -> dict:
    """Read-only: what `run-tool` would do. {tool, tier, runtime, network, estimate, cost, needs_yes, spends, refusal, strict,
    env_keys}. A `refusal` is the gate's decision and its reason; a bad name or input, and an upstream failure, raise MontageError."""
    if not isinstance(name, str) or not _TOOL_NAME.match(name):
        raise MontageError(f"nome de tool inválido: {name!r} (veja `simplicio-video montage tools list`)")
    if not isinstance(inputs, dict):
        raise MontageError("o input precisa ser um objeto JSON ({...})")
    try:
        json.dumps(inputs, ensure_ascii=False).encode("utf-8")
    except (UnicodeEncodeError, TypeError, ValueError):
        raise MontageError("o input tem caracteres que não são UTF-8 válido (surrogates, por exemplo); corrija o texto") from None
    size = len(input_json(inputs).encode("ascii"))  # the serialized argv bytes: the number the argv limit counts
    if size > RUN_TOOL_MAX_INPUT:
        raise MontageError(f"o input tem {size} bytes na linha de comando (os escapes \\uXXXX contam) e passa do limite de "
                           f"{RUN_TOOL_MAX_INPUT // 1000} KB")
    info = _child("info", {"name": name})["info"]  # an unknown name raises here, with the way to list the tools
    tier, runtime, network = info.get("tier"), info.get("runtime"), _network_flag(info)
    plan = {"tool": name, "tier": tier, "runtime": runtime, "network": network, "estimate": None, "cost": None,
            "needs_yes": False, "spends": False, "refusal": None, "strict": strict,
            "env_keys": [] if strict else _declared_env_keys(info)}
    if tier == "publish":
        return _refuse(plan, f"a tool {name} é de publicação (tier publish): o simplicio-video não publica, nem no terminal e "
                             "nem com --yes", hint=False)
    if _offline() and network is not False:
        return _refuse(plan, f"modo offline (SIMPLICIO_OFFLINE=1): {name} precisa de rede, ou o metadado não diz")
    if strict:
        if name not in MCP_ALLOWLIST:
            return _refuse(plan, f"{name} não está na lista de tools revisadas para o MCP (MCP_ALLOWLIST, lida à mão no checkout)")
        declared = tuple(MCP_ALLOWLIST[name].get("outputs") or ())
        ops = MCP_ALLOWLIST[name].get("operations")
        if ops is not None and inputs.get("operation") not in ops:
            return _refuse(plan, f"{name}: a operação {inputs.get('operation')!r} não entra pelo MCP (só {', '.join(ops)}; as outras "
                                 "usam pastas laterais, como o concat, que usa .concat_tmp)")
        msg = _strict_input_refusal(inputs, info.get("input_schema"), declared)
        if msg:
            return _refuse(plan, msg)
        early = _spend_reasons(runtime, network, cost=0.0)  # runtime and network need no estimate: no upstream call for them
        if early:
            return _refuse(plan, f"{name}: {', '.join(early)}; pelo MCP só roda tool local, sem rede e sem custo", yes_hint=True)
    errs = _schema_errors(name, info.get("input_schema") or {}, inputs)
    if errs:
        raise MontageError(f"entrada inválida para {name}: " + "; ".join(errs[:5]))
    estimate = _child("estimate", {"name": name, "input": inputs})["estimate"]
    cost = _cost(estimate)
    estimate = {**(estimate or {}), "estimated_cost_usd": cost}  # a NaN or infinite cost is not JSON: it is unknown
    reasons = _spend_reasons(runtime, network, cost)
    plan.update(estimate=estimate, cost=cost, needs_yes=bool(reasons), spends=bool(reasons))
    if strict:
        if reasons:
            return _refuse(plan, f"{name}: {', '.join(reasons)}; pelo MCP só roda tool local, sem rede e sem custo", yes_hint=True)
        return plan
    if reasons and not yes:
        plan["refusal"] = (f"{name} precisa de --yes ({', '.join(reasons)}): a estimativa acima mostra o custo; "
                           "rode de novo com --yes para executar")
    return plan


def _output_entry(path: str, base: Path) -> dict:
    p = Path(path) if os.path.isabs(path) else base / path
    entry: dict = {"path": str(p), "bytes": None, "sha256": None}
    if p.is_file():
        h = hashlib.sha256()
        with p.open("rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        entry.update(bytes=p.stat().st_size, sha256=h.hexdigest())
    return entry


def run_tool_execute(plan: dict, inputs: dict, cwd: Path, *, timeout: float | None = None) -> dict:
    """Runs the tool (the caller has checked the plan). Returns {ok, tool, status (done|failed), outputs, duration_s, ...}.
    The upstream gets the minimal environment and the plan's declared provider keys, and is killed with its whole group
    when the time limit passes."""
    t0 = time.monotonic()
    om_dir = _require_checkout()
    py = upstream_python()
    env = _child_env(plan.get("env_keys") or [], neutral=_neutral_keys(om_dir) if plan["strict"] else ())
    if plan["strict"]:
        env["npm_config_offline"] = "true"
    stream = not under_mcp()  # in a terminal the upstream's progress is shown; under the MCP server it goes to stderr, captured
    limit = _run_timeout(timeout)
    cmd = [py, "-I", "-c", _RUN_CHILD, str(om_dir), plan["tool"], input_json(inputs)]
    # The output goes to files, not pipes: a grandchild that left the process group can keep a pipe open for ever, and waiting
    # on the pipe would outlive the time limit. Only the child itself is waited for; its files are read once it has ended.
    with tempfile.TemporaryFile() as out_f, (tempfile.TemporaryFile() if not stream else contextlib.nullcontext()) as err_f:
        try:
            proc = subprocess.Popen(cmd, cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=out_f,
                                    stderr=None if stream else err_f, start_new_session=True)
        except OSError as e:
            raise _spawn_error(e, py) from None
        seen: dict[int, str] = {}  # the descendants of the child, as they were while it ran (see _descendants)
        try:
            _wait_watching(proc, limit, seen)
        except subprocess.TimeoutExpired:
            seen.update(_descendants(proc.pid))  # the last look, before the group is killed
            _kill_group(proc)
            proc.wait()
            _kill_survivors(seen)  # what left the group is not in the group any more
            raise MontageError(f"{plan['tool']} passou de {limit:g} s e foi encerrado por tempo limite "
                               "(mude com --timeout ou SIMPLICIO_MONTAGE_TIMEOUT)") from None
        except BaseException:  # Ctrl-C and the like: the upstream does not outlive the command
            seen.update(_descendants(proc.pid))
            _kill_group(proc)
            proc.wait()
            _kill_survivors(seen)
            raise
        _kill_survivors(seen)  # the tool may have returned while its descendants were still alive
        out = _read_text(out_f)
        err = "" if stream else _read_text(err_f)
    if err:
        sys.stderr.write(err)
    try:
        data = json.loads(out)
    except ValueError:
        raise MontageError(f"o OpenMontage terminou sem resultado ao rodar {plan['tool']} (código {proc.returncode})") from None
    if not data.get("ok"):
        if data.get("kind") == "import":
            missing = ", ".join(data.get("missing") or ["?"])
            raise MontageError(f"faltam dependências do OpenMontage no venv ({py}): {missing}. Rode `simplicio-video montage setup`.")
        raise MontageError(f"o OpenMontage falhou: {data.get('error')}")
    res = data["result"]
    ok = bool(res.get("success"))
    return {"ok": ok, "tool": plan["tool"], "status": "done" if ok else "failed",
            "outputs": [_output_entry(a, cwd) for a in res.get("artifacts") or []],
            "duration_s": round(time.monotonic() - t0, 2), "tool_duration_s": res.get("duration_seconds"),
            "cost_usd": res.get("cost_usd"), "estimate": plan["estimate"], "data": res.get("data") or {},
            "error": None if ok else (res.get("error") or "a tool falhou sem mensagem")}


def _run_dir() -> Path:
    d = data_dir() / _RUN_DIR
    d.mkdir(parents=True, exist_ok=True)
    return d


def _write_result(path: str, res: dict) -> None:
    """The result as a whole file (ASCII JSON, written beside and then renamed): the job reads it back in its own step."""
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".tmp")
    tmp.write_text(json.dumps(res, ensure_ascii=True), encoding="utf-8")
    os.replace(tmp, dest)


def _run_tool_parser() -> argparse.ArgumentParser:
    fmt = argparse.RawDescriptionHelpFormatter
    prog = "simplicio-video montage run-tool"
    ap = argparse.ArgumentParser(
        prog=prog, formatter_class=fmt,
        description=("Roda UMA tool do OpenMontage (os nomes estão em `montage tools list`). No terminal: qualquer tool; o que não "
                     "é local, custa dinheiro, tem custo não estimado ou usa rede pede --yes, depois da estimativa. A tool de "
                     "publicação nunca roda. Pelo MCP (video.montage run-tool) só roda uma tool revisada (video_trimmer, "
                     "audio_probe, frame_sampler, scene_detect, silence_cutter), local, gratuita e sem rede, como tarefa em segundo "
                     "plano."),
        epilog=("exemplos:\n"
                f"  {prog} audio_probe --input '{{\"input_path\": \"/abs/clip.mp4\"}}' --json\n"
                f"  {prog} video_trimmer --input "
                "'{\"operation\": \"cut\", \"input_path\": \"/abs/in.mp4\", \"output_path\": \"/abs/out.mp4\", \"start_seconds\": 0, "
                "\"end_seconds\": 2}' --json\n"
                f"  {prog} NOME --input '{{...}}' --yes      (tool que custa, usa rede ou não é local)\n"
                f"  {prog} NOME --input '{{...}}' --timeout 600 --yes      (tempo máximo em segundos)"))
    ap.add_argument("name", metavar="NOME", help="o nome da tool (montage tools list)")
    ap.add_argument("--input", default="{}", metavar="JSON", help="entradas da tool, um objeto JSON (padrão: {}); caminhos absolutos")
    ap.add_argument("--yes", action="store_true", help="confirma o que custa, usa rede ou não é local (depois da estimativa)")
    ap.add_argument("--json", action="store_true", help="saída JSON para máquinas")
    ap.add_argument("--timeout", type=float, default=None, metavar="SEG",
                    help=f"tempo máximo da execução (padrão {RUN_TIMEOUT_DEFAULT:g} s, ou SIMPLICIO_MONTAGE_TIMEOUT)")
    ap.add_argument("--sob-mcp", action="store_true", dest="sob_mcp", help=argparse.SUPPRESS)  # the MCP job passes it: strict gate
    ap.add_argument("--resultado-em", default=None, dest="resultado_em", help=argparse.SUPPRESS)  # the MCP job's result file
    return ap


def _parse_input(text: str) -> dict:
    try:
        inputs = json.loads(text)
    except ValueError as e:
        raise MontageError(f"--input não é JSON válido: {e}") from None
    if not isinstance(inputs, dict):
        raise MontageError("--input precisa ser um objeto JSON ({...})")
    return inputs


def _say_estimate(plan: dict) -> None:
    e = plan["estimate"]
    cost = e.get("estimated_cost_usd")
    custo = f"US$ {cost}" if cost is not None else "não estimado (cota, ou valor que não é finito)"
    rede = "não" if plan["network"] is False else ("sim" if plan["network"] else "o metadado não diz")
    print(f"estimativa de {plan['tool']}: custo {custo}, runtime {plan['runtime']}, tier {plan['tier']}, rede {rede}",
          file=sys.stderr, flush=True)


def _say_result(res: dict) -> None:
    if res["status"] == "refused":
        print(f"montage run-tool: {res['error']}", file=sys.stderr)
    elif not res["ok"]:
        print(f"montage run-tool: {res['tool']} falhou: {res['error']}", file=sys.stderr)
    else:
        print(f"{res['tool']}: done em {res['duration_s']} s")
        for o in res["outputs"]:
            print(f"saída: {o['path']}  {o['bytes']} bytes  sha256 {o['sha256']}")


def run_tool_cli(args: list[str]) -> int:
    """`simplicio-video montage run-tool NOME --input JSON [--yes] [--json] [--timeout SEG]`. Exit 0 only when the tool ran and
    succeeded."""
    ns = _run_tool_parser().parse_args(args)
    try:
        inputs = _parse_input(ns.input)
        strict = bool(ns.sob_mcp) or under_mcp()
        plan = run_tool_plan(ns.name, inputs, strict=strict, yes=ns.yes)
        if plan["estimate"] is not None:
            _say_estimate(plan)
        if plan["refusal"]:
            res = {"ok": False, "tool": plan["tool"], "status": "refused", "error": plan["refusal"], "outputs": [],
                   "estimate": plan["estimate"]}
        else:
            res = run_tool_execute(plan, inputs, _run_dir() if strict else Path.cwd(), timeout=ns.timeout)
    except MontageError as e:
        if ns.json:
            _print({"ok": False, "tool": ns.name, "status": "failed", "error": str(e), "outputs": []}, True)
        raise
    if ns.resultado_em and res["ok"]:
        _write_result(ns.resultado_em, res)
        _print({"ok": True, "tool": res["tool"], "status": res["status"], "resultado": ns.resultado_em}, True)
    elif ns.json:
        _print(res, True)
    else:
        _say_result(res)
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
