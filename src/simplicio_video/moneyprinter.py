"""MoneyPrinterTurbo track: topic-to-short-video generator (LLM script, synthesized voice, stock footage)
(https://github.com/harry0703/MoneyPrinterTurbo, MIT).

The checkout is pinned in tools.TOOLS['moneyprinter'] and runs as a separate program: a Streamlit WebUI and a
FastAPI service, both from one Python 3.11+ environment that `setup` builds inside the simplicio-video data folder.
It is a human-in-the-loop support track outside the deterministic render, like toonflow and opencut. Whatever it
produces enters a contract as a file with a hash, so the render stays reproducible.

Facts read from the pinned commit (see tools.py for the pin):
- WebUI: `streamlit run webui/Main.py`, port 8501 (webui.sh binds 127.0.0.1 by default).
- API: main.py runs uvicorn on config `listen_host` / `listen_port`; both default to 0.0.0.0:8080 in the code and in
  config.example.toml. There is no override by environment, so `serve` skips main.py and starts the same ASGI app
  (`app.asgi:app`) with uvicorn and the host as an argument.
- config.toml and storage/ live inside the checkout (the root is derived from the file location). The API checks an
  `x-api-key` header only when `app.api_key` is filled; the WebUI has no login.
Nothing here ever prints or logs a value from config.toml: only the key names and whether each one is filled.
"""
from __future__ import annotations

import contextlib
import ipaddress
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

from . import tools
from .toonflow import _offline, _on_term, _stop_group  # same process-group handling as the toonflow track

MONEYPRINTER_REPO = tools.get("moneyprinter").source
WEBUI_PORT = 8501
API_PORT = 8080
LOOPBACK = "127.0.0.1"
LAN_FLAG = "--lan"
MIN_PYTHON = (3, 11)  # .python-version is 3.11 and pyproject.toml says >=3.11 at the pinned commit
SUBCOMMANDS = "clone|setup|serve|where|status"

USAGE = (
    f"MoneyPrinterTurbo ({MONEYPRINTER_REPO}, MIT)\n"
    "  simplicio-video moneyprinter clone [dir]   # clona no commit fixado (MONEYPRINTER_DIR ou ~/.simplicio-video/tools)\n"
    "  simplicio-video moneyprinter setup         # venv isolado, pip install -r requirements.txt, config.toml a partir do exemplo\n"
    f"  simplicio-video moneyprinter serve [--webui] [--api] [{LAN_FLAG}] [--host H]\n"
    f"                                             # WebUI em http://localhost:{WEBUI_PORT} (padrão) e/ou API em http://localhost:{API_PORT}/docs\n"
    "  simplicio-video moneyprinter where         # imprime o checkout\n"
    "  simplicio-video moneyprinter status        # config.toml existe? quais chaves estão preenchidas (sim; o valor nunca aparece)\n"
    "Exige Python 3.11 ou mais novo (setup procura python3.11 a python3.13) e usa ffmpeg (o upstream tenta baixar um sozinho).\n"
    f"O serve escuta só em {LOOPBACK}, forçado por argumento: o upstream escuta em 0.0.0.0 por padrão na API (config listen_host).\n"
    f"Para escutar em todas as interfaces use {LAN_FLAG}; a WebUI não tem login e a API só pede chave se app.api_key estiver preenchida.\n"
    "A API sem app.api_key sobe com um aviso (sem chave, qualquer programa que alcance a porta a usa); o CORS do upstream vem fechado, "
    "e o serve recusa CORS_ALLOWED_ORIGINS com `*` enquanto app.api_key estiver vazio.\n"
    "Pasta de dados em MONEYPRINTER_DATA_DIR (padrão ~/.simplicio-video/moneyprinter-data): venv e storage (vídeos gerados). "
    "O config.toml fica dentro do checkout (o upstream não permite outro lugar).\n"
    "Chaves de API (LLM, TTS, Pexels, Pixabay...) são suas, entram na WebUI ou no config.toml, e este comando nunca as imprime.\n"
    "Fica fora do render determinístico: o que ele gera entra num contrato como arquivo com hash.\n"
)


class MoneyPrinterError(Exception):
    pass


def find_moneyprinter_dir() -> Path | None:
    """The pinned checkout (MONEYPRINTER_DIR, else SIMPLICIO_TOOLS_DIR/moneyprinter, else ~/.simplicio-video/tools/moneyprinter)."""
    return tools.find("moneyprinter")


def data_dir() -> Path:
    """Where the venv and the generated videos (storage/) live, absolute and outside the checkout, so a re-clone
    never wipes them."""
    explicit = os.environ.get("MONEYPRINTER_DATA_DIR")
    if explicit:
        return Path(explicit).expanduser().resolve()
    data = os.environ.get("SIMPLICIO_VIDEO_DATA")
    base = Path(data).expanduser() if data else Path.home() / ".simplicio-video"
    return (base / "moneyprinter-data").resolve()


def venv_python() -> Path:
    sub = ("Scripts", "python.exe") if os.name == "nt" else ("bin", "python")
    return data_dir() / "venv" / sub[0] / sub[1]


@contextlib.contextmanager
def _checkout_at(target: Path):
    """Point tools.install at `target` for the duration of the block, then restore the environment."""
    previous = os.environ.get("MONEYPRINTER_DIR")
    os.environ["MONEYPRINTER_DIR"] = str(target)
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("MONEYPRINTER_DIR", None)
        else:
            os.environ["MONEYPRINTER_DIR"] = previous


def clone_moneyprinter(target: Path | None = None) -> Path:
    """Install MoneyPrinterTurbo at its pinned commit (target overrides the location). Never in offline mode."""
    if _offline():
        raise MoneyPrinterError(
            "modo offline (SIMPLICIO_OFFLINE=1): não vou clonar o MoneyPrinterTurbo. "
            "Instale fora do modo offline com `simplicio-video moneyprinter clone` ou aponte MONEYPRINTER_DIR para um checkout."
        )
    try:
        if target is None:
            return Path(tools.install("moneyprinter"))
        with _checkout_at(Path(target).expanduser()):
            return Path(tools.install("moneyprinter"))
    except tools.ToolError as e:
        raise MoneyPrinterError(str(e)) from None


# ---- config.toml: key names and yes/no only -----------------------------------------------------------------------

_KEY_NAME = re.compile(r"(^|_)(key|keys|token|tokens|secret|password)$")
_ASSIGN = re.compile(r"^\s*([A-Za-z0-9_-]+)\s*=\s*(.*)$")
_SECTION = re.compile(r"^\s*\[([^\[\]]+)\]\s*(#.*)?$")
_QUOTED = re.compile(r'"[^"]+"|\'[^\']+\'')


def _strip_comment(line: str) -> str:
    """Drop a trailing `# comment`, keeping any `#` that sits inside a quoted string."""
    quote = ""
    i = 0
    while i < len(line):
        ch = line[i]
        if quote:
            if ch == "\\" and quote == '"':
                i += 1  # the escaped character cannot close the string
            elif ch == quote:
                quote = ""
        elif ch in "\"'":
            quote = ch
        elif ch == "#":
            return line[:i]
        i += 1
    return line


def _is_filled(value: str) -> bool:
    value = value.strip()
    if value.startswith("["):
        return bool(_QUOTED.search(value))
    if value[:1] in ("'", '"'):
        return len(value) > 2 and value[0] == value[-1] and value[1:-1] != ""
    return value != ""


def config_report(path: Path) -> dict:
    """{'exists': bool, 'keys': {'section.name': filled}} for every secret-looking setting (key, token, secret,
    password). Only the yes/no of each one is kept: the values are read, tested and dropped, never stored."""
    if not path.is_file():
        return {"exists": False, "keys": {}}
    keys: dict[str, bool] = {}
    section = ""
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    i = 0
    while i < len(lines):
        line = _strip_comment(lines[i])
        i += 1
        m = _SECTION.match(line)
        if m:
            section = m.group(1).strip()
            continue
        m = _ASSIGN.match(line)
        if not m or not _KEY_NAME.search(m.group(1)):
            continue
        value = m.group(2)
        if value.lstrip().startswith("[") and "]" not in _QUOTED.sub("", value):  # list continues on the next lines
            while i < len(lines):
                more = _strip_comment(lines[i])
                i += 1
                value += " " + more
                if "]" in _QUOTED.sub("", more):
                    break
        name = f"{section}.{m.group(1)}" if section else m.group(1)
        keys[name] = _is_filled(value)
    return {"exists": True, "keys": keys}


def _print_report(d: Path) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        print("ffmpeg: encontrado no PATH")
    else:
        print("ffmpeg: não encontrado no PATH (o README do upstream diz que ele costuma baixar um sozinho; "
              "se falhar, instale o ffmpeg ou aponte app.ffmpeg_path no config.toml)")
    print("ImageMagick: não exigido pelo upstream (nenhuma referência no README nem no código lidos no commit fixado)")
    rep = config_report(d / "config.toml")
    if not rep["exists"]:
        print("config.toml: não existe (rode `simplicio-video moneyprinter setup`)")
        return
    print("config.toml: existe")
    filled = [k for k, v in rep["keys"].items() if v]
    for k in filled:
        print(f"  {k}: sim")
    empty = len(rep["keys"]) - len(filled)
    if not filled:
        print("nenhuma chave preenchida: o gerador precisa de ao menos um provedor de LLM e uma fonte de vídeo "
              "(WebUI, Configurações básicas, ou o config.toml)")
    print(f"chaves vazias: {empty}")


# ---- setup --------------------------------------------------------------------------------------------------------

def _python() -> str:
    if sys.version_info >= MIN_PYTHON:
        return sys.executable
    for name in ("python3.13", "python3.12", "python3.11"):
        found = shutil.which(name)
        if found:
            return found
    raise MoneyPrinterError("o MoneyPrinterTurbo exige Python 3.11 ou mais novo e não achei python3.11 a python3.13 no PATH.")


def _link_storage(d: Path, data: Path) -> None:
    """storage/ (generated videos) goes to the data folder; a folder that is already there is never touched."""
    storage = d / "storage"
    if storage.exists() or storage.is_symlink():
        return
    target = data / "storage"
    target.mkdir(parents=True, exist_ok=True)
    try:
        os.symlink(target, storage, target_is_directory=True)
    except OSError as e:
        print(f"aviso: não consegui ligar {storage} a {target} ({e}); os vídeos ficam dentro do checkout.", file=sys.stderr)


def _setup(d: Path, args: list[str]) -> int:
    if args:
        raise MoneyPrinterError("setup não recebe argumentos.")
    py = _python()
    data = data_dir()
    steps = []
    if not venv_python().exists():
        steps.append([py, "-m", "venv", str(data / "venv")])
    steps.append([str(venv_python()), "-m", "pip", "install", "-r", "requirements.txt"])
    data.mkdir(parents=True, exist_ok=True)
    try:
        for step in steps:
            if subprocess.call(step, cwd=d) != 0:
                return 1
    except KeyboardInterrupt:
        print("moneyprinter: interrompido durante o setup", file=sys.stderr)
        return 130
    config = d / "config.toml"
    if config.exists():
        print(f"config.toml já existe e não foi alterado: {config}")
    else:
        shutil.copyfile(d / "config.example.toml", config)
        print(f"config.toml criado a partir do exemplo, sem nenhuma chave: {config}")
    _link_storage(d, data)
    print(f"venv em {data / 'venv'}; vídeos gerados em {data / 'storage'}")
    _print_report(d)
    return 0


# ---- serve --------------------------------------------------------------------------------------------------------

def _is_loopback(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _parse_serve(args: list[str]) -> tuple[bool, bool, bool, str | None]:
    webui = api = lan = False
    host = None
    it = iter(args)
    for a in it:
        if a == "--webui":
            webui = True
        elif a == "--api":
            api = True
        elif a == LAN_FLAG:
            lan = True
        elif a == "--host":
            host = next(it, None)
            if not host:
                raise MoneyPrinterError("--host pede um endereço.")
        else:
            raise MoneyPrinterError(f"serve aceita só --webui, --api, {LAN_FLAG} e --host (as portas são fixas: "
                                    f"{WEBUI_PORT} e {API_PORT}); recebi: {a}")
    if not webui and not api:
        webui = True
    return webui, api, lan, host


def _commands(d: Path, host: str, webui: bool, api: bool) -> list[list[str]]:
    py = str(venv_python())
    shown = "localhost" if host in ("0.0.0.0", "::") else host
    cmds = []
    if webui:
        cmds.append([py, "-m", "streamlit", "run", str(d / "webui" / "Main.py"),
                     f"--server.address={host}", f"--server.port={WEBUI_PORT}", f"--browser.serverAddress={shown}",
                     "--server.headless=true", "--browser.gatherUsageStats=False", "--client.toolbarMode=minimal",
                     "--logger.hideWelcomeMessage=True", "--server.showEmailPrompt=False", "--server.enableCORS=True"])
    if api:  # what main.py runs, but with the host as an argument instead of config listen_host
        cmds.append([py, "-m", "uvicorn", "app.asgi:app", "--host", host, "--port", str(API_PORT), "--log-level", "warning"])
    return cmds


def _check_api_key(d: Path) -> None:
    """Read at the pinned commit (app/asgi.py, app/controllers/base.py): the API has no login while app.api_key is empty,
    and CORS is closed unless CORS_ALLOWED_ORIGINS says otherwise. So the browser cannot read it from another site by
    default, but any other program on this computer can use it (and with --lan, anyone on the network), spending the
    LLM and TTS keys of config.toml. `*` in CORS_ALLOWED_ORIGINS without a key lets any web page do the same: refused."""
    if config_report(d / "config.toml")["keys"].get("app.api_key"):
        return
    origins = [o.strip() for o in os.environ.get("CORS_ALLOWED_ORIGINS", "").split(",")]
    if "*" in origins:
        raise MoneyPrinterError(
            "CORS_ALLOWED_ORIGINS tem `*` e app.api_key está vazio: qualquer página aberta no navegador chamaria a API "
            "com as suas chaves de LLM e voz. Preencha app.api_key no config.toml ou tire o `*` de CORS_ALLOWED_ORIGINS."
        )
    print("aviso: a API sobe sem chave (app.api_key vazio no config.toml): qualquer programa que alcance a porta "
          f"{API_PORT} cria vídeos com as suas chaves de LLM e voz. Preencha app.api_key e envie o cabeçalho x-api-key.",
          file=sys.stderr)


def _serve(d: Path, args: list[str]) -> int:
    webui, api, lan, host = _parse_serve(args)
    host = host or ("0.0.0.0" if lan else LOOPBACK)
    if not _is_loopback(host) and not lan:
        raise MoneyPrinterError(
            f"serve não escuta em {host} sem {LAN_FLAG}: a WebUI não tem login e a API só pede chave se app.api_key estiver "
            f"preenchida, então qualquer máquina da mesma rede alcançaria os dois. Sem {LAN_FLAG} o serve usa só {LOOPBACK}. "
            f"Para aceitar a exposição, rode `simplicio-video moneyprinter serve {LAN_FLAG}`."
        )
    if not venv_python().exists():
        raise MoneyPrinterError("ambiente não preparado: rode `simplicio-video moneyprinter setup`.")
    if api:
        _check_api_key(d)
    cmds = _commands(d, host, webui, api)
    existing = os.environ.get("PYTHONPATH")
    env = {**os.environ, "PYTHONPATH": str(d) + (os.pathsep + existing if existing else "")}
    shown = "localhost" if host in ("0.0.0.0", "::") else host
    where = []
    if webui:
        where.append(f"WebUI http://{shown}:{WEBUI_PORT}")
    if api:
        where.append(f"API http://{shown}:{API_PORT}/docs")
    if _is_loopback(host):
        print(f"MoneyPrinterTurbo: {' e '.join(where)} (só neste computador). Ctrl+C para parar.")
    else:
        reach = "todas as interfaces" if host in ("0.0.0.0", "::") else host
        print(f"MoneyPrinterTurbo: {' e '.join(where)}, escutando em {reach}: alcançável pela rede e sem login "
              "(a API só pede chave se app.api_key estiver preenchida). Ctrl+C para parar.")
    labels = (["WebUI"] if webui else []) + (["API"] if api else [])
    # SIGTERM and SIGHUP (terminal closed, ssh dropped) stop the servers like Ctrl+C. Their default action would end
    # this process and leave both servers, which live in their own sessions, listening with nobody to stop them.
    catch = [n for n in (getattr(signal, "SIGTERM", None), getattr(signal, "SIGHUP", None)) if n is not None]
    original = {n: signal.getsignal(n) for n in (signal.SIGINT, *catch)}
    for n in catch:
        signal.signal(n, _on_term)
    procs: list[subprocess.Popen] = []
    try:
        for cmd in cmds:
            procs.append(subprocess.Popen(cmd, cwd=d, env=env, start_new_session=True))
        while True:
            for p, label in zip(procs, labels):
                rc = p.poll()
                if rc is not None:  # one server ended: the other one is stopped below, never left running
                    print(f"moneyprinter: {label} saiu com código {rc}; parando o outro servidor. "
                          "Veja o log acima (porta ocupada?).", file=sys.stderr)
                    return rc if rc > 0 else (128 - rc if rc < 0 else 1)
            time.sleep(0.5)
    except KeyboardInterrupt:  # Ctrl+C is how the user stops the servers: not an error
        return 0
    finally:
        _stop_all(procs, original)


def _stop_all(procs: list, original: dict) -> None:
    """Stop every server group, then put the signal handlers back. A further Ctrl+C or SIGTERM while this runs must
    not abort it (that is what left the second server running), so the signals are ignored here and the stop of each
    group is repeated if one gets through anyway. Each group also gets the final SIGKILL sweep when its leader had
    already exited: a helper it left behind must not keep a port open."""
    for n in original:
        signal.signal(n, signal.SIG_IGN)
    try:
        for p in procs:
            while True:
                try:
                    if p.poll() is None:
                        _stop_group(p)
                    else:
                        with contextlib.suppress(ProcessLookupError):
                            os.killpg(p.pid, signal.SIGKILL)
                    break
                except KeyboardInterrupt:
                    continue
    finally:
        for n, handler in original.items():
            signal.signal(n, handler)


def run_moneyprinter(args: list[str]) -> int:
    first = args[0] if args else "help"
    if first in ("-h", "--help", "help"):
        print(USAGE)
        return 0
    if first not in SUBCOMMANDS.split("|"):
        raise MoneyPrinterError(f"subcomando desconhecido: {first} ({SUBCOMMANDS})")
    if first == "clone":
        print(clone_moneyprinter(Path(args[1]) if len(args) > 1 else None))
        return 0
    d = find_moneyprinter_dir()
    if d is None:
        raise MoneyPrinterError("MoneyPrinterTurbo não encontrado: rode `simplicio-video moneyprinter clone` ou defina MONEYPRINTER_DIR.")
    if first == "where":
        print(d)
        return 0
    if first == "status":
        print(f"checkout: {d}")
        print(f"venv: {'existe' if venv_python().exists() else 'não existe (rode setup)'} ({venv_python().parent.parent})")
        _print_report(d)
        return 0
    if first == "setup":
        return _setup(d, args[1:])
    return _serve(d, args[1:])
