"""Montage track: Agentic video production platform using OpenMontage (https://github.com/calesthio/OpenMontage).

Invokes OpenMontage production capabilities (backlot, pipelines, tools).
"""
from __future__ import annotations

import argparse
import contextlib
import json
import os
import subprocess
import sys
from pathlib import Path

from . import tools


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

REGISTRY_COMMANDS = ("pipelines", "tools", "envelope", "estimate")
RUNTIMES = ("local", "local_gpu", "api", "hybrid")
_CHILD_TIMEOUT = 300

# Runs inside the child (cwd = checkout, PYTHONPATH = checkout). Upstream chatter on stdout is sent to stderr so the
# single JSON document on the real stdout stays parseable.
_CHILD = r"""
import json, sys
real = sys.stdout
sys.stdout = sys.stderr
op, payload = sys.argv[1], json.loads(sys.argv[2])
def emit(d):
    real.write(json.dumps(d, default=str)); real.flush()
try:
    from tools.tool_registry import registry
    registry.discover()
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


def _require_checkout() -> Path:
    om_dir = find_openmontage_dir()
    if om_dir is None:
        raise MontageError(
            f"OpenMontage não encontrado em {default_openmontage_dir()}. "
            "Rode `simplicio-video montage clone` (ou defina OPENMONTAGE_DIR apontando para um checkout)."
        )
    return om_dir


def list_pipelines(om_dir: Path | None = None) -> list[dict]:
    """Every pipeline_defs/*.yaml of the checkout as {file, doc} (safe loader; the file stem is the fallback name)."""
    import yaml  # lazy: cli imports this module and the install path must work before PyYAML exists

    om_dir = om_dir or _require_checkout()
    out = []
    for f in sorted((om_dir / "pipeline_defs").glob("*.yaml")):
        try:
            doc = yaml.safe_load(f.read_text(encoding="utf8"))
        except (yaml.YAMLError, OSError, UnicodeDecodeError) as e:
            first = (str(e).splitlines() or [type(e).__name__])[0]
            raise MontageError(f"pipeline_defs/{f.name} ilegível: {first}") from None
        if not isinstance(doc, dict):
            raise MontageError(f"pipeline_defs/{f.name} não é um mapa YAML")
        doc.setdefault("name", f.stem)
        out.append({"file": f.name, "doc": doc})
    return out


def pipeline_summary(entry: dict) -> dict:
    d = entry["doc"]
    return {"name": d["name"], "version": d.get("version"), "category": d.get("category"),
            "stability": d.get("stability"), "description": " ".join(str(d.get("description") or "").split()),
            "file": entry["file"]}


def show_pipeline(name: str, om_dir: Path | None = None) -> dict:
    entries = list_pipelines(om_dir)
    for e in entries:  # only names found in the listing match, so `name` never becomes a path
        if name in (e["doc"]["name"], Path(e["file"]).stem):
            return e["doc"]
    raise MontageError(f"pipeline desconhecido: {name!r}. Disponíveis: {', '.join(str(e['doc']['name']) for e in entries) or '(nenhum)'}")


def _child(op: str, payload: dict) -> dict:
    """Run one registry operation of the upstream in a separate process; return its parsed JSON answer."""
    om_dir = _require_checkout()
    env = os.environ.copy()
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = f"{om_dir}{os.pathsep}{existing}" if existing else str(om_dir)
    env["PYTHONIOENCODING"] = "utf-8"
    try:
        p = subprocess.run([sys.executable, "-c", _CHILD, op, json.dumps(payload)], cwd=om_dir, env=env,
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
            f"faltam dependências do OpenMontage no Python do motor ({sys.executable}): {missing}. "
            "`simplicio-video montage setup` (em breve) instala; por ora instale-as com pip nesse Python.", data)
    if kind == "not_found":
        raise _ChildError(f"{data['error']}. Veja `simplicio-video montage tools list`.", data)
    raise _ChildError(f"o OpenMontage falhou: {data.get('error')}", data)


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

    add(sub, "envelope", "support_envelope(): o que cada tool declara e o estado ao vivo", ["envelope --json"])
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
            rows = [pipeline_summary(e) for e in list_pipelines()]
            if ns.json:
                _print({"ok": True, "pipelines": rows}, True)
            else:
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
    elif ns.cmd == "envelope":
        env = _child("envelope", {})["envelope"]
        _print({"ok": True, "envelope": env} if ns.json else env, ns.json)
    else:  # estimate
        try:
            inputs = json.loads(ns.input)
        except ValueError as e:
            raise MontageError(f"--input não é JSON válido: {e}") from None
        if not isinstance(inputs, dict):
            raise MontageError("--input precisa ser um objeto JSON ({...})")
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
    py = sys.executable

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

    env = os.environ.copy()
    existing_pp = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = f"{om_dir}:{existing_pp}" if existing_pp else str(om_dir)

    return subprocess.call(cmd, cwd=workdir, env=env)


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    try:
        return run_montage(args)
    except MontageError as e:
        print(f"montage: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
