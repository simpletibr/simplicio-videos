"""Toonflow track: open-source AI studio for short dramas, comic dramas and videos
(https://github.com/HBAI-Ltd/Toonflow-app, MIT).

The checkout is pinned in tools.TOOLS['toonflow'] and runs as a separate program: one Bun process that serves the
API and the web UI. It is a human-in-the-loop creation tool outside the deterministic render. Whatever it produces
enters a contract as a file with a hash, so the render stays reproducible.
"""
from __future__ import annotations

import contextlib
import json
import os
import re
import shutil
import signal
import stat
import subprocess
import sys
from pathlib import Path

from . import tools

TOONFLOW_REPO = tools.get("toonflow").source
# Fixed in the Toonflow server (apps/server/src/index.ts). The server listens on every interface with no login,
# so `serve` only starts when the caller says LAN_FLAG on purpose.
PORT = 3000
LAN_FLAG = "--lan"
DOCKER_FLAG = "--docker"
LOCAL_FLAG = "--local"
# Upstream MCP (packages/mcp, apps/server/src/utils/mcp/runtime.ts at the pin): off by default, enabled in Settings > MCP; while
# enabled the server writes <data dir>/mcpRuntime<port>.json ({pid,url,token}, mode 0600) and build/mcp/stdio.js reads it.
RUNTIME_RE = re.compile(r"^mcpRuntime([0-9]+)\.json$")
STDIO_ENTRY = Path("build") / "mcp" / "stdio.js"
SERVER_ENTRY = Path("build") / "server" / "index.js"

USAGE = (
    f"Toonflow ({TOONFLOW_REPO}, MIT)\n"
    "  simplicio-video toonflow clone [dir]   # clona o Toonflow no commit fixado (TOONFLOW_DIR ou ~/.simplicio-video/tools)\n"
    f"  simplicio-video toonflow serve {LAN_FLAG}   # bun install --frozen-lockfile, build e start: http://localhost:{PORT}\n"
    f"  simplicio-video toonflow serve {DOCKER_FLAG}   # alternativa só em 127.0.0.1:{PORT}: docker compose up --build do próprio Toonflow\n"
    f"{DOCKER_FLAG} e `toonflow mcp` não funcionam juntos: o arquivo de runtime do MCP fica no volume do container e a porta do MCP não é publicada.\n"
    "  simplicio-video toonflow where         # imprime o checkout\n"
    "  simplicio-video toonflow status [--json]   # checkout e pin, bun, build e arquivo de runtime do MCP (nunca o token)\n"
    "  simplicio-video toonflow mcp [--port N] [--json]   # bloco de config MCP stdio para colar no agente host\n"
    f"Sem {LAN_FLAG}, serve não sobe: o Toonflow escuta em 0.0.0.0:{PORT} (todas as interfaces) e não tem login.\n"
    f"Para ficar só no seu computador, use `serve {DOCKER_FLAG}` (docker compose do próprio Toonflow, 127.0.0.1:{PORT}) ou bloqueie a porta no firewall.\n"
    f"{LOCAL_FLAG} não existe: o servidor fixa a porta e chama listen({PORT}) sem host, sem variável para trocar a interface.\n"
    "O MCP do Toonflow vem desligado: ligue em Configurações > MCP na interface e rode `toonflow mcp`.\n"
    "Dados em TOONFLOW_DATA_DIR (padrão ~/.simplicio-video/toonflow-data), fora do checkout.\n"
    "O Toonflow fica fora do render determinístico: o que ele gera entra num contrato como arquivo com hash.\n"
)


class ToonflowError(Exception):
    pass


def _offline() -> bool:
    return os.environ.get("SIMPLICIO_OFFLINE", "").strip().lower() in ("1", "true", "yes", "on")


def find_toonflow_dir() -> Path | None:
    """The pinned checkout (TOONFLOW_DIR, else SIMPLICIO_TOOLS_DIR/toonflow, else ~/.simplicio-video/tools/toonflow)."""
    return tools.find("toonflow")


def data_dir() -> Path:
    """Where the server keeps its data, absolute: the server runs inside the checkout, so a relative path would
    point somewhere else. Outside the checkout by default, so a re-clone never wipes it."""
    explicit = os.environ.get("TOONFLOW_DATA_DIR")
    if explicit:
        return Path(explicit).expanduser().resolve()
    data = os.environ.get("SIMPLICIO_VIDEO_DATA")
    base = Path(data).expanduser() if data else Path.home() / ".simplicio-video"
    return (base / "toonflow-data").resolve()


@contextlib.contextmanager
def _checkout_at(target: Path):
    """Point tools.install at `target` for the duration of the block, then restore the environment."""
    previous = os.environ.get("TOONFLOW_DIR")
    os.environ["TOONFLOW_DIR"] = str(target)
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("TOONFLOW_DIR", None)
        else:
            os.environ["TOONFLOW_DIR"] = previous


def clone_toonflow(target: Path | None = None) -> Path:
    """Install Toonflow at its pinned commit (target overrides the location). Never in offline mode."""
    if _offline():
        raise ToonflowError(
            "modo offline (SIMPLICIO_OFFLINE=1): não vou clonar o Toonflow. "
            "Instale fora do modo offline com `simplicio-video toonflow clone` ou aponte TOONFLOW_DIR para um checkout."
        )
    try:
        if target is None:
            return Path(tools.install("toonflow"))
        with _checkout_at(Path(target).expanduser()):
            return Path(tools.install("toonflow"))
    except tools.ToolError as e:
        raise ToonflowError(str(e)) from None


def _bun() -> str:
    bun = shutil.which("bun")
    if not bun:
        raise ToonflowError("bun não encontrado (https://bun.sh); a versão exigida está no campo packageManager do package.json do checkout.")
    return bun


def _on_term(signum, frame):
    raise KeyboardInterrupt  # `kill <this process>` stops the server the same way Ctrl+C does


def _stop_group(proc: subprocess.Popen) -> None:
    """SIGINT to the server's whole process group; SIGKILL if it outlives 15 s; then a SIGKILL sweep of the group.
    The sweep matters: a helper the server started may still be finishing after the server exited, and it must not
    keep running (or keep port 3000 open without login) once this returns."""
    with contextlib.suppress(ProcessLookupError):
        os.killpg(proc.pid, signal.SIGINT)
    try:
        proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(proc.pid, signal.SIGKILL)
        proc.wait()
    with contextlib.suppress(ProcessLookupError):
        os.killpg(proc.pid, signal.SIGKILL)


def _sinais_de_parada() -> list[int]:
    """SIGTERM, and SIGHUP (terminal closed, ssh dropped) where the platform has it."""
    return [n for n in (getattr(signal, "SIGTERM", None), getattr(signal, "SIGHUP", None)) if n is not None]


def _parar(proc: subprocess.Popen) -> None:
    # The stop signals are ignored from here on: a second Ctrl+C or SIGTERM must not abort the stop and leave the group listening
    # (the same rule as moneyprinter's _stop_all). The handlers are put back by _serve.
    for n in _sinais_de_parada():
        signal.signal(n, signal.SIG_IGN)
    _stop_group(proc)


def _run_server(bun: str, d: Path, data: Path) -> int:
    """`bun build/server/index.js`, the command upstream's Dockerfile runs: one process, in its own group."""
    proc = subprocess.Popen([bun, "build/server/index.js"], cwd=d,
                            env={**os.environ, "TOONFLOW_DATA_DIR": str(data)}, start_new_session=True)
    try:
        return proc.wait()
    except KeyboardInterrupt:  # Ctrl+C or a stop signal is how the user stops the server: not an error
        _parar(proc)
        return 0
    finally:
        if proc.poll() is None:  # the wait was cut short by something else: never leave the server running
            _parar(proc)


def _serve(d: Path, args: list[str]) -> int:
    if LOCAL_FLAG in args:
        raise ToonflowError(
            f"serve {LOCAL_FLAG} não é possível: no commit fixado o servidor chama listen({PORT}) sem host (apps/server/src/index.ts) "
            f"e não lê variável de host ou porta, então escuta em todas as interfaces. Use `serve {DOCKER_FLAG}` (127.0.0.1:{PORT}) ou bloqueie a porta no firewall."
        )
    if DOCKER_FLAG in args:
        if args != [DOCKER_FLAG]:
            raise ToonflowError(f"serve {DOCKER_FLAG} não combina com outras opções: o compose do Toonflow já publica só em 127.0.0.1:{PORT}.")
        up = _docker_up(d)
        env = {k: v for k, v in os.environ.items() if not k.startswith("COMPOSE_")}
        print(f"Toonflow (docker compose) em http://127.0.0.1:{PORT}, só neste computador e sem login. Ctrl+C para parar.")
        try:
            return subprocess.call(up, cwd=d, env=env)  # in _serve on purpose: terminal-only, like the bun path (tests/test_childio.py ALLOW)
        except KeyboardInterrupt:
            print("toonflow: interrompido", file=sys.stderr)
            return 0
    if [a for a in args if a != LAN_FLAG]:
        raise ToonflowError(f"serve aceita só {LAN_FLAG} ou {DOCKER_FLAG}: a porta é fixa no Toonflow ({PORT}).")
    if LAN_FLAG not in args:
        raise ToonflowError(
            f"serve não sobe sem {LAN_FLAG}: o Toonflow escuta em 0.0.0.0:{PORT} (todas as interfaces) e não tem login, "
            "então qualquer máquina da mesma rede alcança a API e os arquivos. "
            f"Para ficar só no seu computador, use `simplicio-video toonflow serve {DOCKER_FLAG}` (127.0.0.1:{PORT}) ou bloqueie a porta no firewall. "
            f"Para aceitar a exposição, rode `simplicio-video toonflow serve {LAN_FLAG}`."
        )
    bun = _bun()
    data = data_dir()
    try:
        for step in ([bun, "install", "--frozen-lockfile"], [bun, "run", "build:server"]):
            if subprocess.call(step, cwd=d) != 0:
                return 1
    except KeyboardInterrupt:
        print("toonflow: interrompido durante a instalação ou o build", file=sys.stderr)
        return 130
    (data / "workspaces" / "myProject").mkdir(parents=True, exist_ok=True)
    print(f"Toonflow em http://localhost:{PORT}, também em todas as interfaces e sem login (dados: {data}). Ctrl+C para parar.")
    previous = {n: signal.signal(n, _on_term) for n in _sinais_de_parada()}
    try:
        return _run_server(bun, d, data)
    finally:
        for n, handler in previous.items():
            signal.signal(n, handler)


def _compose_cmd() -> list[str] | None:
    """`docker compose` (plugin) or the standalone `docker-compose`; None when neither works."""
    docker = shutil.which("docker")
    if docker:
        with contextlib.suppress(OSError, subprocess.SubprocessError):
            if subprocess.run([docker, "compose", "version"], stdin=subprocess.DEVNULL, capture_output=True, timeout=15).returncode == 0:
                return [docker, "compose"]
    legacy = shutil.which("docker-compose")
    return [legacy] if legacy else None


def _docker_up(d: Path) -> list[str]:
    """The loopback alternative: upstream's compose.yaml publishes 127.0.0.1:3000:3000 and keeps the data in a volume."""
    compose = _compose_cmd()
    if compose is None:
        raise ToonflowError("docker compose não encontrado (https://docs.docker.com/compose/install/): instale o Docker, "
                            f"ou use `serve {LAN_FLAG}` aceitando a exposição em todas as interfaces.")
    # -f pins upstream's own file: neither COMPOSE_FILE nor an untracked compose.override.yaml may change the binding.
    return [*compose, "-f", str(d.resolve() / "compose.yaml"), "up", "--build"]


def _bun_version(bun: str) -> str | None:
    try:
        r = subprocess.run([bun, "--version"], stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    return (r.stdout.strip() or None) if r.returncode == 0 else None


def _port_of(f: Path) -> int:
    return int(RUNTIME_RE.match(f.name).group(1))


def _runtime_files() -> list[Path]:
    d = data_dir()
    if not d.is_dir():
        return []
    return sorted((f for f in d.iterdir() if RUNTIME_RE.match(f.name)), key=_port_of)  # lstat-based checks decide if it is usable


def _mode(f: Path) -> str:
    return format(stat.S_IMODE(f.lstat().st_mode), "04o")


def _problem(f: Path) -> str | None:
    """Why the runtime file is not usable, or None. lstat, never stat: a symlink must not make another file (a key, say) pass,
    because upstream's stdio.js would then echo the target's contents in an error. Exactly 0600, owned by the user."""
    if os.name == "nt":
        return None
    st = f.lstat()
    if stat.S_ISLNK(st.st_mode) or not stat.S_ISREG(st.st_mode):
        return (f"{f} é um link simbólico ou não é um arquivo regular; o MCP só aceita o arquivo que o próprio Toonflow escreveu. "
                "Apague-o e ligue o MCP de novo.")
    if st.st_uid != os.getuid():
        return (f"{f} é de outro dono (uid {st.st_uid}); o Toonflow só aceita o arquivo do seu usuário. "
                f"Apague-o ou corrija com `chown $USER {f}`, e depois confira o modo 0600.")
    if stat.S_IMODE(st.st_mode) != 0o600:
        return f"{f} está com modo {_mode(f)}; o Toonflow só aceita 0600. Corrija com `chmod 600 {f}`."
    return None


def _private(f: Path) -> bool:
    return _problem(f) is None


def status() -> dict:
    """What is installed and what the MCP bridge needs. The runtime files are only stat()ed: the token inside is never read."""
    t = tools.get("toonflow")
    try:
        pin = tools.effective_ref(t)
    except tools.ToolError:
        pin = t.ref
    d = find_toonflow_dir()
    head = None
    if d is not None:
        try:
            head = tools._git("rev-parse", "HEAD", cwd=d)
        except tools.ToolError:
            head = None
    bun = shutil.which("bun")
    return {
        "checkout": str(d) if d else None,
        "pin": pin,
        "head": head,
        "pin_match": (head == pin) if head else None,
        "bun": {"found": bool(bun), "path": bun, "version": _bun_version(bun) if bun else None},
        "build": {"server": bool(d and (d / SERVER_ENTRY).is_file()), "mcp_stdio": bool(d and (d / STDIO_ENTRY).is_file())},
        "mcp_runtime": [{"path": str(f), "port": _port_of(f), "mode": _mode(f), "ok": _private(f)} for f in _runtime_files()],
    }


def _print_status(s: dict) -> None:
    b = s["bun"]
    match = "confere com o pin" if s["pin_match"] else "DIFERE do pin" if s["pin_match"] is False else "sem checkout"
    print(f"checkout: {s['checkout'] or 'não encontrado (rode `toonflow clone`)'}")
    print(f"pin:      {s['pin']}")
    print(f"head:     {s['head'] or '-'}  ({match})")
    print(f"bun:      {(b['path'] + ' ' + (b['version'] or '?')) if b['found'] else 'não encontrado (https://bun.sh)'}")
    print(f"build:    server={'ok' if s['build']['server'] else 'falta'}  mcp/stdio={'ok' if s['build']['mcp_stdio'] else 'falta'}  (bun run build:server)")
    if not s["mcp_runtime"]:
        print("mcp:      nenhum mcpRuntime<porta>.json (o MCP do Toonflow vem desligado: Configurações > MCP, com o servidor no ar)")
    for r in s["mcp_runtime"]:
        print(f"mcp:      {r['path']}  modo {r['mode']}  {'ok' if r['ok'] else 'ABERTO: chmod 600 ' + r['path']}")


def mcp_config(port: int | None = None) -> dict:
    """The stdio block for a host agent: `<node|bun> <checkout>/build/mcp/stdio.js --runtime <data>/mcpRuntime<port>.json`.
    Refuses an open runtime file (upstream would too). The token is never read."""
    d = find_toonflow_dir()
    if d is None:
        raise ToonflowError("Toonflow não encontrado: rode `simplicio-video toonflow clone` ou defina TOONFLOW_DIR.")
    stdio = d / STDIO_ENTRY
    if not stdio.is_file():
        raise ToonflowError(f"falta {stdio}: rode `bun install --frozen-lockfile && bun run build:server` em {d} "
                            f"(o `simplicio-video toonflow serve {LAN_FLAG}` também faz isso).")
    files = _runtime_files()
    if not files:
        raise ToonflowError(f"nenhum mcpRuntime<porta>.json em {data_dir()}: o MCP do Toonflow vem desligado. Suba o servidor, ligue em "
                            "Configurações > MCP (o arquivo só existe enquanto o MCP está ligado) e rode de novo. "
                            f"Com `serve {DOCKER_FLAG}` isto não funciona: o arquivo fica no volume do container e a porta do MCP não é publicada.")
    if port is None:
        if len(files) > 1:
            raise ToonflowError("há mais de um arquivo de runtime (" + ", ".join(f.name for f in files) + "): escolha com --port N.")
        f = files[0]
    else:
        f = next((x for x in files if x.name == f"mcpRuntime{port}.json"), None)
        if f is None:
            raise ToonflowError(f"não há mcpRuntime{port}.json em {data_dir()} (existem: {', '.join(x.name for x in files)}).")
    problem = _problem(f)
    if problem:
        raise ToonflowError(problem)
    runner = shutil.which("node") or shutil.which("bun")
    if not runner:
        raise ToonflowError("node (20 ou mais novo) ou bun não encontrado: o build/mcp/stdio.js roda em um dos dois.")
    return {"mcpServers": {"toonflow": {"command": runner, "args": [str(stdio.resolve()), "--runtime", str(f)]}}}


def _flags(args: list[str], allow_port: bool) -> tuple[bool, int | None]:
    as_json, port, i = False, None, 0
    while i < len(args):
        a = args[i]
        if a == "--json":
            as_json = True
        elif a == "--port" and allow_port:
            v = args[i + 1] if i + 1 < len(args) else ""
            if not re.fullmatch(r"[0-9]{1,5}", v) or not 1 <= int(v) <= 65535:
                raise ToonflowError("--port precisa de um número de 1 a 65535 (ASCII).")
            port, i = int(v), i + 1
        else:
            raise ToonflowError(f"opção desconhecida: {a} (aceita --json{' e --port N' if allow_port else ''})")
        i += 1
    return as_json, port


def run_toonflow(args: list[str]) -> int:
    first = args[0] if args else "help"
    if first in ("-h", "--help", "help"):
        print(USAGE)
        return 0
    if first not in ("clone", "serve", "where", "status", "mcp"):
        raise ToonflowError(f"subcomando desconhecido: {first} (clone|serve|where|status|mcp)")
    if first == "status":
        as_json, _ = _flags(args[1:], False)
        s = status()
        if as_json:
            print(json.dumps(s, indent=2, ensure_ascii=False))
        else:
            _print_status(s)
        return 0
    if first == "mcp":
        _, port = _flags(args[1:], True)
        print(json.dumps(mcp_config(port), indent=2))
        return 0
    if first == "clone":
        print(clone_toonflow(Path(args[1]) if len(args) > 1 else None))
        return 0
    d = find_toonflow_dir()
    if d is None:
        raise ToonflowError("Toonflow não encontrado: rode `simplicio-video toonflow clone` ou defina TOONFLOW_DIR.")
    if first == "where":
        print(d)
        return 0
    return _serve(d, args[1:])
