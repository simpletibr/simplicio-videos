"""Montage track: Agentic video production platform using OpenMontage (https://github.com/calesthio/OpenMontage).

Invokes OpenMontage production capabilities (backlot, pipelines, tools).
"""
from __future__ import annotations

import argparse
import contextlib
import json
import os
import shutil
import subprocess
import sys
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

REGISTRY_COMMANDS = ("pipelines", "tools", "envelope", "estimate", "setup", "status")
READ_ONLY_COMMANDS = ("pipelines", "tools", "envelope", "estimate", "status")  # what the MCP tool may run
RUNTIMES = ("local", "local_gpu", "api", "hybrid")
_CHILD_TIMEOUT = 300
_OPEN_DIAG_TIMEOUT = 8
_WARNED_RELATIVE: set[str] = set()

# Runs inside the child (cwd = checkout, PYTHONPATH = checkout). Upstream chatter on stdout is sent to stderr so the
# single JSON document on the real stdout stays parseable.
_CHILD = r"""
import json, os, sys
real = os.fdopen(os.dup(1), "w", encoding="utf-8")  # the result goes here; fd 1 now belongs to stderr, so grandchildren and C code cannot corrupt it
os.dup2(2, 1)
sys.stdout = sys.stderr
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
    env = _upstream_env(om_dir)
    env["PYTHONIOENCODING"] = "utf-8"
    skip = _offline() or under_mcp()  # no network probes offline or under the MCP server; the terminal keeps the live ones
    if skip:
        env["npm_config_offline"] = "true"
        payload = {**payload, "skip_probes": True}
    try:
        p = subprocess.run([py, "-c", _CHILD, op, json.dumps(payload)], cwd=om_dir, env=env, stdin=subprocess.DEVNULL,
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=_CHILD_TIMEOUT)
    except subprocess.TimeoutExpired:
        raise MontageError(f"o OpenMontage não respondeu em {_CHILD_TIMEOUT}s") from None
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


def run_montage(args: list[str], cwd: Path | None = None) -> int:
    """Execute OpenMontage with arguments."""
    if args and args[0] in REGISTRY_COMMANDS:
        return run_registry(args)

    if args and args[0] in ("clone", "--clone"):
        target = Path(args[1]) if len(args) > 1 else None
        clone_openmontage(target)
        return 0

    om_dir = find_openmontage_dir()
    if om_dir is None:
        if not args or args[0] in ("-h", "--help", "help"):
            print(
                f"OpenMontage ({OPENMONTAGE_REPO})\n\n"
                "OpenMontage não foi encontrado localmente.\n"
                "Para clonar e inicializar, execute:\n"
                "  simplicio-video montage clone [diretório]\n"
                "  ou defina OPENMONTAGE_DIR apontando para o checkout.\n"
                f"Local padrão: {default_openmontage_dir()} ($SIMPLICIO_VIDEO_DATA/tools/openmontage).\n"
            )
            return 0
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


if __name__ == "__main__":
    sys.exit(main())
