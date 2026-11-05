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
import errno
import hashlib
import http.client
import ipaddress
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from urllib.parse import unquote

from . import tools
from .childio import run_child
from .toonflow import _offline, _on_term, _stop_group  # same process-group handling as the toonflow track

MONEYPRINTER_REPO = tools.get("moneyprinter").source
WEBUI_PORT = 8501
API_PORT = 8080
LOOPBACK = "127.0.0.1"
LAN_FLAG = "--lan"
MIN_PYTHON = (3, 11)  # .python-version is 3.11 and pyproject.toml says >=3.11 at the pinned commit
SUBCOMMANDS = "clone|setup|serve|generate|run|where|status"
PORT_MIN, PORT_MAX = 1024, 65535  # --api-port: portas sem privilégio de root
DEFAULT_VOICE = "pt-BR-FranciscaNeural-Female"  # voz Edge: não exige chave
ASPECTS = ("9:16", "16:9", "1:1")
TASK_STATE_COMPLETE, TASK_STATE_FAILED = 1, -1  # app/models/const.py no commit fixado
POLL_SECONDS = 2.0
TASK_TIMEOUT_SECONDS = 1800
READY_TIMEOUT_SECONDS = 120

USAGE = (
    f"MoneyPrinterTurbo ({MONEYPRINTER_REPO}, MIT)\n"
    "  simplicio-video moneyprinter clone [dir]   # clona no commit fixado (MONEYPRINTER_DIR ou ~/.simplicio-video/tools)\n"
    "  simplicio-video moneyprinter setup         # venv isolado, pip install -r requirements.txt, config.toml a partir do exemplo\n"
    f"  simplicio-video moneyprinter serve [--webui] [--api] [--api-port N] [{LAN_FLAG}] [--host H]\n"
    f"                                             # WebUI em http://localhost:{WEBUI_PORT} (padrão) e/ou API em http://localhost:{API_PORT}/docs\n"
    "  simplicio-video moneyprinter generate --script roteiro.txt --material clip.mp4 [--material ...] --out DIR\n"
    "                                             # [--voice V] [--aspect 9:16|16:9|1:1] [--subject S] [--api-port N] [--json]\n"
    "                                             # sobe a API em loopback, envia o material, gera o vídeo, baixa o MP4 e grava o manifesto\n"
    "  simplicio-video moneyprinter run [--yes] [--json] --out DIR -- <flags do cli.py do upstream>\n"
    "                                             # roda o cli.py do MoneyPrinterTurbo (etapas com --stop-at, legendas, música, --batch-file de até 100 tarefas) e copia o MP4 para DIR com sha256 e manifesto\n"
    "                                             # exemplo (roteiro seu, material local, voz Edge: grátis, sem --yes):\n"
    "                                             #   simplicio-video moneyprinter run --out out/ -- --video-script \"Texto do vídeo.\" \\\n"
    "                                             #     --video-source local --video-materials clip1.mp4,clip2.mp4 --voice-name pt-BR-FranciscaNeural-Female\n"
    "                                             # só o roteiro (cai no LLM: precisa de --yes): run --yes --out out/ -- --video-subject tema --stop-at script\n"
    "                                             # em lote: run --out out/ -- --batch-file tarefas.jsonl --voice-name no-voice\n"
    "  simplicio-video moneyprinter where         # imprime o checkout\n"
    "  simplicio-video moneyprinter status        # config.toml existe? quais chaves estão preenchidas (sim; o valor nunca aparece)\n"
    "run: lista FECHADA de flags (derivada do cli.py do upstream; qualquer outra é recusada). Gastar só no terminal e só com --yes: "
    "roteiro por LLM (sem --video-script), fonte de material paga (wavespeed, volcengine_seedance, ofox, metaso_minimax, muapi, openai_image) "
    "com a --confirm-...-charge dela, voz fora do Edge, música de IA (sonilo, elevenlabs). Caminhos relativos valem a partir de onde você roda. "
    "Recusa rodar se o config.toml liga a publicação (upload_post_auto_upload): este motor não publica.\n"
    "Pelo MCP (video.moneyprinter): generate e run só viram uma tarefa em segundo plano (video.jobs) com roteiro seu, material local, voz Edge e --out absoluto.\n"
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

_KEY_NAME = re.compile(r"(^|_)(key|keys|token|tokens|secret|password|key_id)$", re.I)
_ASSIGN = re.compile(r"^\s*([A-Za-z0-9_-]+)\s*=\s*(.*)$")
_SECTION = re.compile(r"^\s*\[\[?([^\[\]]+)\]\]?\s*(#.*)?$")
_NEW_ASSIGN = re.compile(r"^\s*[A-Za-z0-9_-]+\s*=")
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
    for q in ('"""', "'''"):
        if value.startswith(q) and value.endswith(q) and len(value) >= 6:
            return value[3:-3].strip() != ""
    if value[:1] in ("'", '"'):
        return len(value) > 2 and value[0] == value[-1] and value[1:-1].strip() != ""
    return value != ""


def _value_filled(value) -> bool:
    if isinstance(value, str):
        return value.strip() != ""
    if isinstance(value, (list, tuple)):
        return any(_value_filled(v) for v in value)
    if isinstance(value, dict):
        return any(_value_filled(v) for v in value.values())
    return value is not None and not isinstance(value, bool)


def _walk(node: dict, prefix: str, keys: dict[str, bool]) -> None:
    for k, v in node.items():
        name = f"{prefix}.{k}" if prefix else str(k)
        if isinstance(v, dict):
            _walk(v, name, keys)
        elif _KEY_NAME.search(str(k)):
            keys[name] = keys.get(name, False) or _value_filled(v)
        elif isinstance(v, list):
            for item in v:  # [[array of tables]]: the name does not carry an index
                if isinstance(item, dict):
                    _walk(item, name, keys)


def config_report(path: Path) -> dict:
    """{'exists': bool, 'keys': {'section.name': filled}} for every secret-looking setting (key, token, secret,
    password, key id; any case, dotted, quoted, inline table or array of tables). Only the yes/no of each one is kept:
    the values are read, tested and dropped, never stored. tomllib (Python 3.11+) parses the file; the line reader
    below is the fallback for Python 3.10 and for a file that is not valid TOML."""
    if not path.is_file():
        return {"exists": False, "keys": {}}
    text = path.read_text(encoding="utf-8", errors="replace")
    try:
        import tomllib
        data = tomllib.loads(text)
    except Exception:  # no tomllib (3.10) or invalid TOML: read it line by line
        return {"exists": True, "keys": _report_by_lines(text)}
    keys: dict[str, bool] = {}
    _walk(data, "", keys)
    return {"exists": True, "keys": keys}


def _report_by_lines(text: str) -> dict[str, bool]:
    keys: dict[str, bool] = {}
    section = ""
    lines = text.splitlines()
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
                if _NEW_ASSIGN.match(lines[i]) or _SECTION.match(_strip_comment(lines[i])):
                    break  # the list was never closed: do not swallow the next settings
                more = _strip_comment(lines[i])
                i += 1
                value += " " + more
                if "]" in _QUOTED.sub("", more):
                    break
        name = f"{section}.{m.group(1)}" if section else m.group(1)
        keys[name] = _is_filled(value)
    return keys


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
    """The interpreter that builds the venv (only needed when the venv does not exist yet)."""
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


def _warn_if_not_pinned(d: Path) -> None:
    """pip installs the requirements.txt of whatever commit is checked out: say so when it is not the pinned one."""
    ref = tools.effective_ref(tools.get("moneyprinter"))  # the commit in use: the lock's when `update` followed MoneyPrinter, else the pin
    try:
        head = tools._git("rev-parse", "HEAD", cwd=d)
    except tools.ToolError:
        return  # not a git checkout (a copy, or a test stand-in): nothing to compare
    if head != ref:
        print(f"aviso: o checkout {d} está em {head[:12]}, não no commit fixado {ref[:12]}; o pip vai instalar o "
              "requirements.txt desse outro commit. Rode `simplicio-video moneyprinter clone` para voltar ao pino.",
              file=sys.stderr)


def _step(i: int, n: int, label: str) -> float:
    print(f"[{i}/{n}] {label} ...", flush=True)
    return time.monotonic()


def _done(t0: float, failed_rc: int | None = None) -> None:
    secs = int(round(time.monotonic() - t0))
    print(f"    ok ({secs}s)" if failed_rc is None else f"    falhou (código {failed_rc}, {secs}s)", flush=True)


def _setup(d: Path, args: list[str]) -> int:
    if args:
        raise MoneyPrinterError("setup não recebe argumentos.")
    data = data_dir()
    _warn_if_not_pinned(d)
    steps = []  # (what is printed before it runs, command)
    if not venv_python().exists():
        steps.append((f"criando o venv isolado em {data / 'venv'} (python -m venv)", [_python(), "-m", "venv", str(data / "venv")]))
    steps.append(("pip install -r requirements.txt (na primeira vez baixa centenas de MB e leva vários minutos; "
                  "o pip imprime o andamento abaixo)", [str(venv_python()), "-m", "pip", "install", "-r", "requirements.txt"]))
    total = len(steps) + 2  # + config.toml + storage
    try:
        data.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise MoneyPrinterError(f"não consegui criar a pasta de dados {data}: {e}") from None
    try:
        for i, (label, step) in enumerate(steps, start=1):
            t0 = _step(i, total, label)
            rc = run_child(step, cwd=d)
            if rc != 0:
                _done(t0, rc)
                return 1
            _done(t0)
    except OSError as e:
        raise MoneyPrinterError(f"não consegui rodar {step[0]}: {e}") from None
    except KeyboardInterrupt:
        print("moneyprinter: interrompido durante o setup", file=sys.stderr)
        return 130
    t0 = _step(len(steps) + 1, total, "config.toml a partir do exemplo (sem nenhuma chave)")
    config = d / "config.toml"
    if config.exists():
        print(f"config.toml já existe e não foi alterado: {config}")
    else:
        try:
            shutil.copyfile(d / "config.example.toml", config)
            if os.name != "nt":
                os.chmod(config, 0o600)  # the user will put paid API keys here: nobody else on the machine reads them
        except OSError as e:
            raise MoneyPrinterError(f"não consegui criar o config.toml a partir de config.example.toml: {e}") from None
        print(f"config.toml criado a partir do exemplo, sem nenhuma chave: {config}")
    _done(t0)
    t0 = _step(total, total, f"storage/ (vídeos gerados) ligado a {data / 'storage'}")
    try:
        _link_storage(d, data)
    except OSError as e:
        raise MoneyPrinterError(f"não consegui preparar o storage em {data}: {e}") from None
    _done(t0)
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


def _parse_serve(args: list[str]) -> tuple[bool, bool, bool, str | None, int]:
    webui = api = lan = port_given = False
    host = None
    api_port = API_PORT
    it = iter(args)
    for a in it:
        if a == "--webui":
            webui = True
        elif a == "--api":
            api = True
        elif a == LAN_FLAG:
            lan = True
        elif a == "--api-port":
            api_port = _port(next(it, None))
            port_given = True
        elif a == "--host":
            host = next(it, None)
            if not host:
                raise MoneyPrinterError("--host pede um endereço.")
        else:
            raise MoneyPrinterError(f"serve aceita só --webui, --api, --api-port, {LAN_FLAG} e --host (a WebUI usa a "
                                    f"porta {WEBUI_PORT}; a API, {API_PORT} ou a de --api-port); recebi: {a}")
    if not webui and not api:
        webui = True
    if port_given and not api:
        raise MoneyPrinterError("--api-port só vale com --api.")
    if webui and api and api_port == WEBUI_PORT:
        raise MoneyPrinterError(f"--api-port não pode ser {WEBUI_PORT}: essa é a porta da WebUI.")
    return webui, api, lan, host, api_port


def _commands(d: Path, host: str, webui: bool, api: bool, api_port: int = API_PORT) -> list[list[str]]:
    py = str(venv_python())
    shown = "localhost" if host in ("0.0.0.0", "::") else host
    cmds = []
    if webui:
        cmds.append([py, "-m", "streamlit", "run", str(d / "webui" / "Main.py"),
                     f"--server.address={host}", f"--server.port={WEBUI_PORT}", f"--browser.serverAddress={shown}",
                     "--server.headless=true", "--browser.gatherUsageStats=False", "--client.toolbarMode=minimal",
                     "--logger.hideWelcomeMessage=True", "--server.showEmailPrompt=False", "--server.enableCORS=True"])
    if api:  # what main.py runs, but with the host as an argument instead of config listen_host
        cmds.append([py, "-m", "uvicorn", "app.asgi:app", "--host", host, "--port", str(api_port), "--log-level", "warning"])
    return cmds


def _check_api_key(d: Path, port: int = API_PORT) -> None:
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
          f"{port} cria vídeos com as suas chaves de LLM e voz. Preencha app.api_key e envie o cabeçalho x-api-key.",
          file=sys.stderr)


def _serve(d: Path, args: list[str]) -> int:
    webui, api, lan, host, api_port = _parse_serve(args)
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
        _check_api_key(d, api_port)
    cmds = _commands(d, host, webui, api, api_port)
    existing = os.environ.get("PYTHONPATH")
    env = {**os.environ, "PYTHONPATH": str(d) + (os.pathsep + existing if existing else "")}
    shown = "localhost" if host in ("0.0.0.0", "::") else host
    where = []
    if webui:
        where.append(f"WebUI http://{shown}:{WEBUI_PORT}")
    if api:
        where.append(f"API http://{shown}:{api_port}/docs")
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
            try:
                procs.append(subprocess.Popen(cmd, cwd=d, env=env, start_new_session=True))
            except OSError as e:
                raise MoneyPrinterError(f"não consegui iniciar {cmd[0]}: {e}") from None
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


# ---- generate: a API sobe por trás, o MP4 volta com hash e manifesto (#144) ---------------------------------------

GENERATE_FLAGS = ("--script", "--material", "--out", "--voice", "--aspect", "--subject", "--api-port")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Loopback não segue redirect: um Location para outro host levaria o x-api-key junto."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())  # nunca pelo proxy do ambiente


def _json_or_none(raw: bytes) -> dict | None:
    if not raw:
        return None
    try:
        value = json.loads(raw)
    except ValueError:
        return None
    return value if isinstance(value, dict) else None


def _request(method: str, url: str, body: bytes | None = None, headers: dict | None = None,
             timeout: float = 30) -> tuple[int, dict | None]:
    """HTTP com a biblioteca padrão, só para a API em loopback. Devolve (status, JSON ou None); status 0 = sem conexão."""
    req = urllib.request.Request(url, data=body, method=method, headers=headers or {})
    try:
        with _OPENER.open(req, timeout=timeout) as resp:
            return resp.status, _json_or_none(resp.read())
    except urllib.error.HTTPError as e:
        try:
            raw = e.read()
        except (http.client.HTTPException, OSError):  # o status é o que importa; o corpo pode vir quebrado
            raw = b""
        return e.code, _json_or_none(raw)
    except (urllib.error.URLError, OSError, http.client.HTTPException):
        return 0, None


def _port(value: str | None) -> int:
    if value is None or not re.fullmatch(r"[0-9]{1,5}", value) or not PORT_MIN <= int(value) <= PORT_MAX:
        raise MoneyPrinterError(f"--api-port pede um número de porta entre {PORT_MIN} e {PORT_MAX}.")
    return int(value)


def _listen_socket(port: int) -> socket.socket:
    """Socket de loopback já em escuta, que vai para a API (uvicorn --fd). Porta 0: uma livre agora, sem corrida."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((LOOPBACK, port))
        sock.listen(128)
    except BaseException:
        sock.close()
        raise
    return sock


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_video_request(script: str, voice: str, aspect: str, materials: list[str], subject: str) -> dict:
    """Corpo do POST /api/v1/videos: roteiro pronto e material local, sem chave de LLM nem de fonte de vídeo."""
    return {
        "video_subject": subject,
        "video_script": script,
        "video_source": "local",
        "video_materials": [{"provider": "local", "url": name} for name in materials],
        "video_aspect": aspect,
        "voice_name": voice,
        "subtitle_enabled": False,
    }


MAX_TRANSIENT_ERRORS = 5  # erros seguidos que a espera tolera (sem conexão, 429, 5xx) antes de desistir


def wait_for_task(base: str, task_id: str, get, sleep=time.sleep, max_polls: int = 900,
                  poll: float = POLL_SECONDS) -> dict:
    """Consulta a tarefa até completar (state 1) ou falhar (state -1). `get(url)` devolve (status, JSON).
    Erro transitório (sem conexão, 429, 5xx) tenta de novo até MAX_TRANSIENT_ERRORS seguidos. Qualquer outro
    status que não seja 200 (404 incluído) para na hora, e 200 sem dados também."""
    task: dict = {}
    transient = 0
    for _ in range(max_polls):
        status, data = get(f"{base}/api/v1/tasks/{task_id}")
        if status == 404:
            raise MoneyPrinterError(f"a tarefa {task_id} não encontrada na API.")
        if status == 0 or status == 429 or status >= 500:
            transient += 1
            if transient > MAX_TRANSIENT_ERRORS:
                raise MoneyPrinterError(f"a API falhou em {transient} tentativas seguidas ao consultar a tarefa "
                                        f"{task_id} (último: {'sem conexão' if status == 0 else f'HTTP {status}'}).")
            sleep(poll)
            continue
        if status != 200:
            raise MoneyPrinterError(f"a API respondeu HTTP {status} ao consultar a tarefa {task_id}.")
        task = (data or {}).get("data")
        if not isinstance(task, dict):
            raise MoneyPrinterError(f"a API respondeu sem dados ao consultar a tarefa {task_id}.")
        transient = 0
        if task.get("state") == TASK_STATE_COMPLETE:
            return task
        if task.get("state") == TASK_STATE_FAILED:
            raise MoneyPrinterError(
                f"a tarefa {task_id} falhou em {task.get('failed_stage') or 'etapa desconhecida'}: "
                f"{task.get('error') or 'sem detalhe'}")
        sleep(poll)
    raise MoneyPrinterError(f"tempo esgotado esperando a tarefa {task_id} (último estado: {task.get('state')}).")


def _upload_material(base: str, path: Path, auth: dict) -> tuple[str, str]:
    """Envia um material ao diretório de vídeos locais da API. Devolve (nome guardado, sha256 dos bytes enviados)."""
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()  # o hash é dos bytes que foram enviados, não do arquivo depois
    boundary = uuid.uuid4().hex
    head = (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{path.name}"\r\n'
            "Content-Type: application/octet-stream\r\n\r\n").encode()
    body = head + data + f"\r\n--{boundary}--\r\n".encode()
    status, reply = _request("POST", f"{base}/api/v1/video_materials", body,
                             {"Content-Type": f"multipart/form-data; boundary={boundary}", **auth}, timeout=600)
    if status != 200:
        raise MoneyPrinterError(f"o envio do material {path.name} falhou (HTTP {status}).")
    data = (reply or {}).get("data")
    if not isinstance(data, dict) or not isinstance(data.get("file"), str):
        raise MoneyPrinterError(f"o envio do material {path.name} devolveu resposta sem nome de arquivo.")
    return data["file"], digest


def _task_file(checkout: Path, uri: str) -> Path:
    """A API devolve a saída como /tasks/<relativo>; o upstream grava em <checkout>/storage/tasks (storage/ é ligado
    à pasta de dados pelo setup), e nada fora dali é lido."""
    prefix = "/tasks/"
    tasks = (checkout / "storage" / "tasks").resolve()
    try:
        path = (tasks / unquote(uri[len(prefix):])).resolve() if uri.startswith(prefix) else tasks.parent
    except (ValueError, OSError):  # ex.: byte nulo no caminho
        path = tasks.parent
    if tasks not in path.parents:
        raise MoneyPrinterError(f"a API devolveu uma saída fora da pasta de tarefas: {uri}")
    return path


def write_result(out: Path, task_id: str, video: Path, request: dict, materials: list[dict],
                 elapsed: float, checkout_head: str | None = None) -> dict:
    """Copia o MP4 para a pasta de saída e grava o manifesto: sha256 do vídeo e de cada material, pino e tempo."""
    out.mkdir(parents=True, exist_ok=True)
    stem = f"moneyprinter-{task_id}"
    target = out / f"{stem}.mp4"
    shutil.copyfile(video, target)
    meta = {
        "schema": "simplicio.moneyprinter-result/v1",
        "task_id": task_id,
        "video": target.name,
        "bytes": target.stat().st_size,
        "sha256": _sha256(target),
        "pinned_commit": tools.pinned_ref(tools.get("moneyprinter")),
        "voice": request.get("voice_name"),
        "aspect": request.get("video_aspect"),
        "checkout_head": checkout_head,
        "materials": materials,
        "elapsed_seconds": round(elapsed, 1),
    }
    (out / f"{stem}.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return meta


def _parse_generate(args: list[str]) -> dict:
    opts: dict = {"script": None, "materials": [], "out": None, "voice": DEFAULT_VOICE, "aspect": "9:16",
                  "subject": None, "api_port": None, "json": False}
    it = iter(args)
    for a in it:
        if a == "--json":
            opts["json"] = True
        elif a in GENERATE_FLAGS:
            value = next(it, None)
            if value is None:
                raise MoneyPrinterError(f"{a} pede um valor.")
            if a == "--material":
                opts["materials"].append(value)
            elif a == "--api-port":
                opts["api_port"] = _port(value)
            else:
                opts[a[2:]] = value
        else:
            raise MoneyPrinterError("generate aceita --script, --material (repetível), --out, --voice, --aspect, "
                                    f"--subject, --api-port e --json; recebi: {a}")
    if not opts["script"] or not opts["materials"] or not opts["out"]:
        raise MoneyPrinterError("generate precisa de --script, --material e --out.")
    if opts["aspect"] not in ASPECTS:
        raise MoneyPrinterError(f"--aspect pede um de: {', '.join(ASPECTS)}.")
    return opts


def _wait_ready(base: str, proc: subprocess.Popen, auth: dict) -> None:
    """Espera a API responder como MoneyPrinterTurbo (não qualquer coisa que esteja nessa porta)."""
    deadline = time.monotonic() + READY_TIMEOUT_SECONDS
    while True:
        if proc.poll() is not None:
            raise MoneyPrinterError(f"a API saiu com código {proc.returncode} antes de responder; veja a saída acima.")
        status, data = _request("GET", f"{base}/openapi.json", headers=auth, timeout=5)
        if status == 200 and ((data or {}).get("info") or {}).get("title") == "MoneyPrinterTurbo":
            return
        if time.monotonic() > deadline:
            raise MoneyPrinterError(f"a API não respondeu como MoneyPrinterTurbo em {READY_TIMEOUT_SECONDS} s.")
        time.sleep(0.5)


def _checkout_head(d: Path) -> str | None:
    """O commit que realmente está no checkout (o manifesto registra esse, não só o pino)."""
    if not (d / ".git").exists():  # sem .git aqui, o git acharia o repositório pai: não é o checkout
        return None
    try:
        return tools._git("rev-parse", "HEAD", cwd=d)
    except tools.ToolError:
        return None


def _can_read_toml() -> bool:
    """tomllib (3.11+) é o único leitor de TOML que o generate usa para a chave: sem ele, não há como saber se a API exige uma."""
    try:
        import tomllib  # noqa: F401
    except ImportError:
        return False
    return True


def _api_key(d: Path) -> str | None:
    """app.api_key do config.toml, lido só para o cabeçalho x-api-key das chamadas de loopback. Nunca impresso nem gravado."""
    path = d / "config.toml"
    if not path.is_file():
        return None
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        raise MoneyPrinterError(f"não consegui ler {path}: {e.strerror or e}.") from None
    import tomllib
    try:
        data = tomllib.loads(text)
    except (ValueError, RecursionError):  # TOML inválido ou aninhado demais: se a chave é mencionada, não dá para saber se a API a exige
        if "api_key" in text:
            raise MoneyPrinterError("config.toml não é TOML válido; não consigo ler app.api_key, que a API exige "
                                    "quando está preenchido. Corrija o arquivo.") from None
        return None
    app = data.get("app")
    if app is None:
        return None
    if not isinstance(app, dict):
        raise MoneyPrinterError("[app] no config.toml precisa ser uma tabela, não uma lista ou um valor.")
    value = app.get("api_key")
    if value is None:
        return None
    if not isinstance(value, str):
        raise MoneyPrinterError("app.api_key precisa ser texto no config.toml.")
    key = value.strip()
    if not key:
        return None
    if not key.isprintable():
        raise MoneyPrinterError("app.api_key tem caractere de controle (quebra de linha, por exemplo); corrija o config.toml.")
    try:
        key.encode("latin-1")
    except UnicodeEncodeError:
        raise MoneyPrinterError("app.api_key tem caractere fora de latin-1, que o cabeçalho HTTP não aceita; "
                                "corrija o config.toml.") from None
    return key


def _generate(d: Path, args: list[str]) -> int:
    opts = _parse_generate(args)
    if not _can_read_toml():
        raise MoneyPrinterError("generate precisa de Python 3.11 ou mais novo, para ler app.api_key do config.toml.")
    script = Path(opts["script"]).expanduser()
    if not script.is_file():
        raise MoneyPrinterError(f"roteiro não encontrado: {script}")
    text = script.read_text(encoding="utf-8").strip()
    if not text:
        raise MoneyPrinterError("o roteiro está vazio.")
    materials = [Path(m).expanduser() for m in opts["materials"]]
    for m in materials:
        if not m.is_file():
            raise MoneyPrinterError(f"material não encontrado: {m}")
    if not venv_python().exists():
        raise MoneyPrinterError("ambiente não preparado: rode `simplicio-video moneyprinter setup`.")
    out_dir = Path(opts["out"]).expanduser()
    started = time.monotonic()
    procs: list[subprocess.Popen] = []
    catch = [n for n in (getattr(signal, "SIGTERM", None), getattr(signal, "SIGHUP", None)) if n is not None]
    original = {n: signal.getsignal(n) for n in (signal.SIGINT, *catch)}
    for n in catch:
        signal.signal(n, _on_term)
    meta: dict = {}
    listener: socket.socket | None = None
    try:
        # tudo que pode falhar antes de gastar (pasta, porta, chave) acontece antes de subir a API
        try:
            out_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            raise MoneyPrinterError(f"a pasta de saída não pode ser criada: {out_dir} ({e})") from None
        # a porta é reservada aqui e o socket vai para a API: nenhuma outra instância atende nela, nem por um instante
        try:
            listener = _listen_socket(opts["api_port"] or 0)
        except OSError as e:
            if e.errno == errno.EADDRINUSE:
                where = f"a porta {opts['api_port']}" if opts["api_port"] else "a porta que o sistema ofereceu"
                raise MoneyPrinterError(f"{where} já está em uso; escolha outra com --api-port.") from None
            raise
        port = listener.getsockname()[1]
        base = f"http://{LOOPBACK}:{port}"
        key = _api_key(d)
        auth = {"x-api-key": key} if key else {}
        _check_api_key(d, port)
        _warn_if_not_pinned(d)
        existing = os.environ.get("PYTHONPATH")
        env = {**os.environ, "PYTHONPATH": str(d) + (os.pathsep + existing if existing else "")}
        fd = listener.fileno()
        # o log do servidor vai para o stderr (fd 2): o stdout fica só com o resultado, que pode ser JSON
        procs.append(subprocess.Popen([str(venv_python()), "-m", "uvicorn", "app.asgi:app", "--fd", str(fd),
                                       "--log-level", "warning"],
                                      cwd=d, env=env, start_new_session=True, stdout=2, pass_fds=(fd,)))
        listener.close()  # o filho tem a sua cópia do socket
        listener = None
        proc = procs[0]
        _wait_ready(base, proc, auth)
        uploaded = [_upload_material(base, m, auth) for m in materials]
        records = [{"name": m.name, "sha256": digest} for m, (_, digest) in zip(materials, uploaded)]
        body = build_video_request(text, opts["voice"], opts["aspect"], [name for name, _ in uploaded],
                                   opts["subject"] or text[:40])
        if proc.poll() is not None:
            raise MoneyPrinterError(f"a API saiu com código {proc.returncode} antes de receber o pedido.")
        status, data = _request("POST", f"{base}/api/v1/videos", json.dumps(body).encode("utf-8"),
                                {"Content-Type": "application/json", **auth}, timeout=60)
        task_id = ((data or {}).get("data") or {}).get("task_id")
        if status != 200 or not task_id:
            raise MoneyPrinterError(f"a API recusou o pedido (HTTP {status}): "
                                    f"{(data or {}).get('message', 'sem detalhe')}")

        def get(url: str) -> tuple[int, dict | None]:
            if proc.poll() is not None:
                raise MoneyPrinterError(f"a API saiu com código {proc.returncode} antes de terminar a tarefa {task_id}.")
            return _request("GET", url, headers=auth)

        task = wait_for_task(base, task_id, get=get, max_polls=int(TASK_TIMEOUT_SECONDS / POLL_SECONDS))
        videos = task.get("videos")
        if not isinstance(videos, list) or not videos:
            raise MoneyPrinterError(f"a tarefa {task_id} terminou sem vídeo.")
        if not isinstance(videos[0], str):
            raise MoneyPrinterError(f"a tarefa {task_id} devolveu uma saída inválida.")
        src = _task_file(d, videos[0])
        if not src.is_file():
            raise MoneyPrinterError(f"o MP4 da tarefa {task_id} não está em {src}.")
        meta = write_result(out_dir, task_id, src, body, records, time.monotonic() - started,
                            checkout_head=_checkout_head(d))
    except MoneyPrinterError as e:
        print(f"moneyprinter: {e}", file=sys.stderr)
        return 1
    except OSError as e:
        print(f"moneyprinter: não consegui iniciar a API: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("moneyprinter: interrompido; a API foi parada.", file=sys.stderr)
        return 130
    finally:
        if listener is not None:
            listener.close()
        _stop_all(procs, original)
    if opts["json"]:
        print(json.dumps(meta, ensure_ascii=False, indent=2))
    else:
        print(f"MP4: {out_dir / meta['video']}\nsha256: {meta['sha256']}\n"
              f"manifesto: {out_dir / ('moneyprinter-' + meta['task_id'] + '.json')}")
    return 0

# ---- run: o cli.py headless do upstream, com lista fechada de flags (T4) ------------------------------------------
#
# Lido no commit fixado (cli.py, parse_args). Cada flag do upstream que este comando repassa está em RUN_FLAGS; tudo o mais
# é recusado antes de rodar. O que gasta (LLM, fonte de material paga, voz de rede, música por IA, --confirm-*-charge)
# só passa no terminal e só com o --yes do motor. Nenhum endpoint de publicação é chamado, e um config.toml que liga a
# publicação automática (upload_post_auto_upload) faz o run recusar: este motor não publica.

_VAL, _FLAG, _NEG, _PATH, _PATHS = "value", "flag", "neg", "path", "paths"
RUN_STAGES = ("script", "terms", "audio", "subtitle", "materials", "video")
RUN_SOURCES = ("pexels", "pixabay", "coverr", "wavespeed", "volcengine_seedance", "ofox", "metaso_minimax", "muapi",
               "openai_image", "local")
PAID_SOURCES = {"wavespeed": "--confirm-wavespeed-charge", "volcengine_seedance": "--confirm-seedance-charge",
                "ofox": "--confirm-ofox-charge", "metaso_minimax": "--confirm-metaso-minimax-charge",
                "muapi": "--confirm-muapi-charge", "openai_image": None}  # openai_image: o upstream não tem flag de confirmação
AI_MUSIC = ("sonilo", "elevenlabs")
FREE_VOICE = re.compile(r"^[a-z]{2,3}-[A-Za-z]{2,4}-[A-Za-z0-9]+Neural(-Male|-Female)?$")  # vozes Edge: sem chave
NO_VOICE = "no-voice"
RUN_FLAGS: dict[str, str] = {
    # script and content
    "--video-subject": _VAL, "--video-script": _VAL, "--video-terms": _VAL, "--video-language": _VAL,
    "--paragraph-number": _VAL, "--video-script-prompt": _VAL, "--custom-system-prompt": _VAL,
    # materials and pipeline
    "--video-source": _VAL, "--video-materials": _PATHS, "--stop-at": _VAL,
    "--confirm-wavespeed-charge": _FLAG, "--confirm-seedance-charge": _FLAG, "--confirm-ofox-charge": _FLAG,
    "--confirm-metaso-minimax-charge": _FLAG, "--confirm-muapi-charge": _FLAG,
    # video output
    "--video-count": _VAL, "--video-aspect": _VAL, "--video-fit-mode": _VAL, "--video-concat-mode": _VAL,
    "--video-transition-mode": _VAL, "--video-clip-duration": _VAL, "--video-clip-speed": _VAL,
    "--match-materials-to-script": _NEG, "--n-threads": _VAL,
    # voiceover and background music
    "--voice-name": _VAL, "--voice-volume": _VAL, "--voice-rate": _VAL, "--custom-audio-file": _PATH,
    "--bgm-type": _VAL, "--sonilo-bgm-prompt": _VAL, "--video-music-prompt": _VAL, "--bgm-file": _VAL,
    "--bgm-volume": _VAL,
    # subtitles
    "--subtitle-enabled": _NEG, "--font-name": _VAL, "--subtitle-position": _VAL, "--subtitle-display-mode": _VAL,
    "--subtitle-animation": _VAL, "--custom-position": _VAL, "--text-fore-color": _VAL, "--font-size": _VAL,
    "--stroke-color": _VAL, "--stroke-width": _VAL, "--subtitle-background-enabled": _NEG,
    "--subtitle-background-color": _VAL, "--rounded-subtitle-background": _NEG,
    # execution
    "--task-id": _VAL, "--batch-file": _PATH,
}
# Over MCP: a supplied script, local material, a free voice. No LLM prompts, no AI music, no confirmations, no custom
# audio path, no task id, no batch.
MCP_FLAGS = frozenset(f for f in RUN_FLAGS if not f.startswith("--confirm-")) - {
    "--video-terms", "--paragraph-number", "--video-script-prompt", "--custom-system-prompt", "--custom-audio-file",
    "--sonilo-bgm-prompt", "--video-music-prompt", "--task-id", "--batch-file"}
MCP_BGM = ("none", "random", "custom")
BATCH_KEYS = (("video_script", "script"), ("video_source", "source"), ("video_terms", "terms"), ("voice_name", "voice"),
              ("bgm_type", "bgm"), ("sonilo_bgm_prompt", "music_prompt"), ("video_music_prompt", "music_prompt"))
PUBLISH_KEYS = ("upload_post_auto_upload",)  # task.py cross-posts a finished video when this is true


def _terminal_only(what: str) -> MoneyPrinterError:
    return MoneyPrinterError(f"{what}: só pelo terminal, com `simplicio-video moneyprinter run --yes ...`; o MCP não faz isso")


def _absolute(path: str, mcp: bool) -> str:
    p = Path(path.strip()).expanduser()
    if p.is_absolute():
        return str(p)
    if mcp:
        raise MoneyPrinterError(f"caminho relativo não vale pelo MCP (a pasta de trabalho do servidor não é a sua): {path}")
    return os.path.abspath(p)


def _flag_value(flag: str, tokens: list[str], i: int, inline: str | None) -> tuple[str, int]:
    if inline is not None:
        return inline, i
    if i >= len(tokens) or tokens[i].split("=", 1)[0] in RUN_FLAGS:
        raise MoneyPrinterError(f"{flag} pede um valor.")
    return tokens[i], i + 1


def parse_upstream(tokens: list[str], mcp: bool = False) -> dict[str, object]:
    """The flags after `--`, checked against RUN_FLAGS. Returns {flag: value} (True/False for switches). Relative paths
    become absolute from the caller's folder (the upstream runs inside the checkout); over MCP they are refused."""
    flags: dict[str, object] = {}
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        i += 1
        if not tok.startswith("--"):
            raise MoneyPrinterError(f"argumento fora da lista de flags do run: {tok}")
        name, eq, inline = tok.partition("=")
        base, off = name, False
        if name not in RUN_FLAGS and name.startswith("--no-") and RUN_FLAGS.get("--" + name[5:]) == _NEG:
            base, off = "--" + name[5:], True
        if base not in RUN_FLAGS:
            if mcp:
                raise _terminal_only(f"{name} pelo MCP (fora da lista)")
            raise MoneyPrinterError(f"flag fora da lista do run: {name} (lista fechada, derivada do cli.py do upstream: "
                                    f"{', '.join(sorted(RUN_FLAGS))})")
        if mcp and base not in MCP_FLAGS:
            raise _terminal_only(f"{base} pelo MCP")
        kind = RUN_FLAGS[base]
        if kind in (_FLAG, _NEG):
            if eq:
                raise MoneyPrinterError(f"{name} não recebe valor.")
            flags[base] = not off
            continue
        raw, i = _flag_value(base, tokens, i, inline if eq else None)
        if kind == _PATH:
            raw = _absolute(raw, mcp)
        elif kind == _PATHS:
            raw = ",".join(_absolute(p, mcp) for p in raw.split(",") if p.strip())
        flags[base] = raw
    return flags


def _voice_is_free(voice: str | None) -> bool:
    return voice == NO_VOICE or bool(voice and FREE_VOICE.match(voice))


def _task_reasons(task: dict, stop_at: str) -> list[str]:
    """Why one task needs the engine's --yes (none = free: supplied script, local material, Edge or silent voice)."""
    reasons = []
    source = str(task.get("source") or "pexels")  # pexels is the upstream default
    if not str(task.get("script") or "").strip():
        reasons.append("roteiro gerado por LLM (sem --video-script)")
    if source in PAID_SOURCES:
        reasons.append(f"fonte de material paga ({source})")
    elif source != "local" and not task.get("terms") and stop_at != "script":
        reasons.append(f"termos de busca gerados por LLM (fonte {source} sem --video-terms)")
    voice = task.get("voice")
    if voice and not _voice_is_free(str(voice)):
        reasons.append(f"voz fora do Edge ({str(voice).split(':', 1)[0]}): TTS por chave")
    if task.get("bgm") in AI_MUSIC or task.get("music_prompt"):
        reasons.append("música de fundo por IA (sonilo/elevenlabs)")
    return reasons


def _batch_entries(path: str) -> list[dict]:
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as e:
        raise MoneyPrinterError(f"não consegui ler o manifesto {path}: {e.strerror or e}") from None
    try:
        data = json.loads(text)
        entries = data if isinstance(data, list) else [data]
    except ValueError:
        entries = []
        for line in text.splitlines():
            if line.strip():
                try:
                    entries.append(json.loads(line))
                except ValueError:
                    raise MoneyPrinterError(f"o manifesto {path} não é JSON nem JSONL válido.") from None
    return [e for e in entries if isinstance(e, dict)]


class RunPlan:
    """What `run` will do: the normalized flags, the reasons it needs --yes and the local material files."""

    def __init__(self, flags: dict[str, object], reasons: list[str], local_materials: list[str]):
        self.flags, self.reasons, self.local_materials = flags, reasons, local_materials

    def argv(self) -> list[str]:
        """Every flag as --flag=value, so a value that starts with a dash (a script) is never taken for a flag."""
        out = []
        for flag, value in self.flags.items():
            if RUN_FLAGS[flag] == _FLAG:
                out.append(flag)
            elif RUN_FLAGS[flag] == _NEG:
                out.append(flag if value else "--no-" + flag[2:])
            else:
                out.append(f"{flag}={value}")
        return out


def plan_run(tokens: list[str], yes: bool = False, mcp: bool = False) -> RunPlan:
    """Parse and classify the flags after `--`. Raises MoneyPrinterError for anything the run may not do: a flag outside
    the list, a spend without --yes, or (mcp) anything that is not a supplied script on local material with a free voice."""
    flags = parse_upstream(tokens, mcp)
    stop_at = str(flags.get("--stop-at", "video"))
    if stop_at not in RUN_STAGES:
        raise MoneyPrinterError(f"--stop-at pede um de: {', '.join(RUN_STAGES)}.")
    if mcp:
        flags.setdefault("--video-source", "local")
    source = str(flags.get("--video-source", "pexels"))
    if source not in RUN_SOURCES:
        raise MoneyPrinterError(f"--video-source pede um de: {', '.join(RUN_SOURCES)}.")
    base = {"script": flags.get("--video-script", ""), "source": source, "terms": flags.get("--video-terms"),
            "voice": flags.get("--voice-name"), "bgm": flags.get("--bgm-type"),
            "music_prompt": flags.get("--sonilo-bgm-prompt") or flags.get("--video-music-prompt")}
    tasks = [base]
    batch = flags.get("--batch-file")
    if batch:
        if not Path(str(batch)).is_file():
            raise MoneyPrinterError(f"manifesto não encontrado: {batch}")
        tasks = [{**base, **{name: e[key] for key, name in BATCH_KEYS if key in e}}
                 for e in _batch_entries(str(batch))] or [base]
    reasons: list[str] = []
    for t in tasks:
        for r in _task_reasons(t, stop_at):
            if r not in reasons:
                reasons.append(r)
    confirms = [f for f in flags if f.startswith("--confirm-")]
    if confirms:
        reasons.append(f"{', '.join(confirms)} confirma a cobrança de um serviço pago")
    if mcp:
        if reasons:
            raise _terminal_only("isto gasta ou chama um serviço externo (" + "; ".join(reasons) + ")")
        _check_mcp(flags, stop_at)
    elif reasons and not yes:
        raise MoneyPrinterError("este run gasta ou chama um serviço externo: " + "; ".join(reasons)
                                + ". Confirme com --yes (antes do `--`), só no terminal.")
    if yes and stop_at in ("materials", "video"):
        for t in tasks:
            flag = PAID_SOURCES.get(str(t.get("source") or ""))
            if flag and flag not in flags:
                raise MoneyPrinterError(f"a fonte {t['source']} cobra por vídeo: o upstream também pede {flag}.")
    return RunPlan(flags, reasons, [m for m in str(flags.get("--video-materials", "")).split(",") if m])


def _check_mcp(flags: dict, stop_at: str) -> None:
    if not str(flags.get("--video-script", "")).strip():
        raise _terminal_only("roteiro por LLM (sem --video-script)")
    if flags.get("--video-source") != "local":
        raise _terminal_only(f"fonte de material {flags.get('--video-source')}")
    if stop_at != "video":
        raise _terminal_only(f"--stop-at {stop_at}")
    materials = [m for m in str(flags.get("--video-materials", "")).split(",") if m]
    if not materials:
        raise MoneyPrinterError("falta --video-materials (caminhos absolutos de vídeos ou imagens locais).")
    for m in materials:
        if not Path(m).is_file():
            raise MoneyPrinterError(f"material não encontrado: {m}")
    if "--voice-name" not in flags:
        raise MoneyPrinterError(f"falta --voice-name (uma voz Edge, como {DEFAULT_VOICE}, ou no-voice): o MCP não herda a "
                                "voz do config.toml, que poderia ser de um serviço pago.")
    bgm = flags.get("--bgm-type")
    if bgm is not None and str(bgm).lower() not in MCP_BGM:
        raise _terminal_only(f"--bgm-type {bgm}")
    bgm_file = str(flags.get("--bgm-file", ""))
    if "/" in bgm_file or "\\" in bgm_file or bgm_file.startswith("."):
        raise MoneyPrinterError("--bgm-file pelo MCP é só o nome de um arquivo de storage/bgm ou resource/songs.")


def _publishing_enabled(d: Path) -> str | None:
    """The config.toml key that would make the upstream cross-post a finished video, when it is on."""
    try:
        text = (d / "config.toml").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    for line in text.splitlines():
        m = _ASSIGN.match(_strip_comment(line))
        if m and m.group(1) in PUBLISH_KEYS and m.group(2).strip().lower() == "true":
            return m.group(1)
    return None


def _spawn_cli(argv: list[str], cwd: Path, env: dict) -> tuple[int, str]:
    """Run the upstream cli.py to the end and return (exit code, the JSON lines it printed). The upstream logs to STDOUT
    (its loguru sink is sys.stdout, despite the --help text) and prints the result there too, so stdout and stderr are
    read as one stream: every line that is not a JSON document is relayed at once to our stderr (the user sees the stages
    as they happen, and fd 1 stays free for our own JSON), and the JSON lines come back. It runs in its own process group
    so a stop reaches all of it."""
    proc = subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
                            start_new_session=True)
    documents = []
    try:
        for line in proc.stdout:
            if line.lstrip().startswith("{"):
                documents.append(line)
            else:
                sys.stderr.write(line)
                sys.stderr.flush()
        proc.wait()
    except BaseException:  # Ctrl+C / SIGTERM: the upstream group goes down with us
        _stop_group(proc)
        raise
    return proc.returncode, "".join(documents)


def _json_document(text: str) -> dict | None:
    text = text.strip()
    for candidate in (text, *(line for line in reversed(text.splitlines()) if line.strip().startswith("{"))):
        try:
            value = json.loads(candidate)
        except ValueError:
            continue
        if isinstance(value, dict):
            return value
    return None


def _video_file(checkout: Path, ref: str) -> Path:
    """A video the upstream says it made: only a file inside <checkout>/storage/tasks is ever read."""
    tasks = (checkout / "storage" / "tasks").resolve()
    if ref.startswith("/tasks/") and not Path(ref).exists():
        return _task_file(checkout, ref)
    try:
        path = Path(ref).resolve() if Path(ref).is_absolute() else (tasks / ref).resolve()
    except (ValueError, OSError):
        path = tasks.parent
    if tasks not in path.parents:
        raise MoneyPrinterError(f"o upstream devolveu uma saída fora da pasta de tarefas: {ref}")
    return path


def _collect(d: Path, out_dir: Path, doc: dict, rc: int, request: dict, materials: list[dict], elapsed: float) -> dict:
    """The upstream JSON (one task, or a batch summary) -> a summary with every video copied out and hashed."""
    if isinstance(doc.get("tasks"), list):
        raw = [t for t in doc["tasks"] if isinstance(t, dict)]
    else:
        raw = [{"index": 1, "task_id": doc.get("task_id"), "status": "succeeded" if rc == 0 else "failed",
                "result": doc.get("result"), "failed_stage": None, "error": None}]
    head = _checkout_head(d)
    tasks = []
    for t in raw:
        result = t.get("result") if isinstance(t.get("result"), dict) else None
        refs = result.get("videos") if result and t.get("status") == "succeeded" else None
        videos = []
        for n, ref in enumerate(refs if isinstance(refs, list) else [], start=1):
            if not isinstance(ref, str):
                raise MoneyPrinterError("o upstream devolveu uma saída de vídeo inválida.")
            src = _video_file(d, ref)
            if not src.is_file():
                raise MoneyPrinterError(f"o MP4 da tarefa {t.get('task_id')} não está em {src}.")
            name = str(t.get("task_id") or uuid.uuid4().hex) + ("" if n == 1 else f"-{n}")
            meta = write_result(out_dir, name, src, request, materials, elapsed, checkout_head=head)
            videos.append({"video": meta["video"], "path": str(out_dir / meta["video"]), "sha256": meta["sha256"],
                           "bytes": meta["bytes"], "manifest": f"moneyprinter-{name}.json"})
        tasks.append({"index": t.get("index"), "task_id": t.get("task_id"), "status": t.get("status"),
                      "failed_stage": t.get("failed_stage"), "error": t.get("error"), "videos": videos,
                      "result": result if not videos else None})
    failed = sum(1 for t in tasks if t["status"] != "succeeded")
    return {"schema": "simplicio.moneyprinter-run/v1", "out": str(out_dir), "total": len(tasks),
            "succeeded": len(tasks) - failed, "failed": failed, "elapsed_seconds": round(elapsed, 1), "tasks": tasks}


def _split_run_args(args: list[str]) -> tuple[dict, list[str]]:
    if "--" not in args:
        raise MoneyPrinterError("run pede `--` antes das flags do upstream: simplicio-video moneyprinter run --out DIR -- "
                                "--video-script \"...\" --video-source local --video-materials clip.mp4 --voice-name V")
    cut = args.index("--")
    mine, upstream = args[:cut], args[cut + 1:]
    if not upstream:
        raise MoneyPrinterError("run pede as flags do upstream depois do `--` (por exemplo --video-script).")
    opts: dict = {"out": None, "json": False, "yes": False}
    it = iter(mine)
    for a in it:
        name, eq, inline = a.partition("=")
        if name == "--out":
            opts["out"] = inline if eq else next(it, None)
            if not opts["out"]:
                raise MoneyPrinterError("--out pede uma pasta.")
        elif a in ("--json", "--yes"):
            opts[a[2:]] = True
        else:
            raise MoneyPrinterError(f"antes do `--` o run aceita só --out, --json e --yes; recebi: {a}")
    if not opts["out"]:
        raise MoneyPrinterError("run precisa de --out (a pasta onde o MP4 e o manifesto são copiados).")
    return opts, upstream


def _run(d: Path, args: list[str]) -> int:
    opts, upstream = _split_run_args(args)
    plan = plan_run(upstream, yes=opts["yes"])
    if not venv_python().exists():
        raise MoneyPrinterError("ambiente não preparado: rode `simplicio-video moneyprinter setup`.")
    key = _publishing_enabled(d)
    if key:
        raise MoneyPrinterError(f"o config.toml liga a publicação automática ({key} = true): este motor não publica. "
                                "Desligue (= false) para gerar vídeos.")
    out_dir = Path(_absolute(opts["out"], False))
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise MoneyPrinterError(f"a pasta de saída não pode ser criada: {out_dir} ({e})") from None
    if plan.reasons:
        print("aviso: --yes confirma: " + "; ".join(plan.reasons), file=sys.stderr)
    _warn_if_not_pinned(d)
    existing = os.environ.get("PYTHONPATH")
    env = {**os.environ, "PYTHONPATH": str(d) + (os.pathsep + existing if existing else ""), "PYTHONUNBUFFERED": "1",
           "PYTHONUTF8": "1"}
    argv = [str(venv_python()), "cli.py", *plan.argv()]
    catch = [n for n in (getattr(signal, "SIGTERM", None), getattr(signal, "SIGHUP", None)) if n is not None]
    original = {n: signal.getsignal(n) for n in (signal.SIGINT, *catch)}
    for n in catch:
        signal.signal(n, _on_term)
    started = time.monotonic()
    summary = None
    try:
        rc, stdout = _spawn_cli(argv, d, env)
        doc = _json_document(stdout)
        if doc is not None:
            request = {"voice_name": plan.flags.get("--voice-name"), "video_aspect": plan.flags.get("--video-aspect", "9:16")}
            materials = [{"name": Path(m).name, "sha256": _sha256(Path(m))} for m in plan.local_materials
                         if Path(m).is_file()]
            summary = _collect(d, out_dir, doc, rc, request, materials, time.monotonic() - started)
        elif rc == 0:
            raise MoneyPrinterError("o upstream terminou sem imprimir o JSON do resultado.")
    except MoneyPrinterError as e:
        print(f"moneyprinter: {e}", file=sys.stderr)
        return 1
    except OSError as e:
        print(f"moneyprinter: não consegui iniciar o cli.py do upstream: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("moneyprinter: interrompido; o cli.py foi parado.", file=sys.stderr)
        return 130
    finally:
        for n, handler in original.items():
            signal.signal(n, handler)
    if summary is not None:
        if opts["json"]:
            print(json.dumps(summary, ensure_ascii=False))  # one line: jobs keeps the last JSON line as the result
        else:
            for t in summary["tasks"]:
                for v in t["videos"]:
                    print(f"MP4: {v['path']}\nsha256: {v['sha256']}\nmanifesto: {out_dir / v['manifest']}")
                if not t["videos"] and t["status"] == "succeeded":
                    print(f"tarefa {t['task_id']}: {json.dumps(t['result'], ensure_ascii=False)}")
                if t["error"]:
                    print(f"tarefa {t['task_id']} falhou em {t['failed_stage']}: {t['error']}", file=sys.stderr)
    return rc


# ---- MCP: generate e run viram uma tarefa em segundo plano (jobs, tipo moneyprinter) ---------------------------------

MCP_GENERATE_FLAGS = ("--script", "--material", "--out", "--voice", "--aspect", "--subject")


def _mcp_generate_tokens(args: list[str]) -> tuple[str, list[str]]:
    opts: dict = {"materials": [], "voice": DEFAULT_VOICE, "aspect": "9:16", "subject": None, "script": None, "out": None}
    it = iter(args)
    for a in it:
        name, eq, inline = a.partition("=")
        if name not in MCP_GENERATE_FLAGS:
            raise _terminal_only(f"generate {a} pelo MCP (o MCP aceita {', '.join(MCP_GENERATE_FLAGS)})")
        value = inline if eq else next(it, None)
        if value is None:
            raise MoneyPrinterError(f"{name} pede um valor.")
        if name == "--material":
            opts["materials"].append(value)
        else:
            opts[name[2:]] = value
    if not opts["script"] or not opts["materials"] or not opts["out"]:
        raise MoneyPrinterError("generate precisa de --script, --material e --out.")
    if opts["aspect"] not in ASPECTS:
        raise MoneyPrinterError(f"--aspect pede um de: {', '.join(ASPECTS)}.")
    script = Path(_absolute(opts["script"], True))
    if not script.is_file():
        raise MoneyPrinterError(f"roteiro não encontrado: {script}")
    text = script.read_text(encoding="utf-8").strip()
    materials = [_absolute(m, True) for m in opts["materials"]]
    if any("," in m for m in materials):
        raise MoneyPrinterError("o caminho de um material não pode ter vírgula.")
    tokens = ["--video-script", text, "--video-source", "local", "--video-materials", ",".join(materials),
              "--voice-name", opts["voice"], "--video-aspect", opts["aspect"], "--no-subtitle-enabled"]
    if opts["subject"]:
        tokens += ["--video-subject", opts["subject"]]
    return _absolute(opts["out"], True), tokens


def job_params(params: dict) -> dict:
    """The one shape a moneyprinter job takes: {out: absolute folder, upstream: flags}. The MCP builds it and jobs.submit
    checks it again, so a job can never hold more than a free run."""
    out, upstream = params.get("out"), params.get("upstream")
    if not isinstance(out, str) or not isinstance(upstream, list) or not all(isinstance(t, str) for t in upstream):
        raise MoneyPrinterError("a tarefa moneyprinter pede out (pasta absoluta) e upstream (lista de flags).")
    plan = plan_run(upstream, mcp=True)
    return {"out": _absolute(out, True), "upstream": plan.argv()}


def mcp_job_params(argv: list[str]) -> dict:
    """`generate ...` or `run --out DIR -- <flags>` over MCP -> the params of a moneyprinter job, or a refusal that says
    the terminal does it."""
    if argv[0] == "generate":
        out, tokens = _mcp_generate_tokens(argv[1:])
        return job_params({"out": out, "upstream": tokens})
    opts, upstream = _split_run_args(argv[1:])
    if opts["yes"]:
        raise _terminal_only("--yes")
    return job_params({"out": opts["out"], "upstream": upstream})


def job_argv(params: dict) -> list[str]:
    return ["moneyprinter", "run", "--out", params["out"], "--json", "--", *params["upstream"]]


def job_result(params: dict, last_json: dict | None) -> dict | None:
    if not isinstance(last_json, dict) or not isinstance(last_json.get("tasks"), list):
        return None
    out = Path(params["out"])
    videos = [{"path": str(out / v["video"]), "sha256": v.get("sha256"), "bytes": v.get("bytes")}
              for t in last_json["tasks"] if isinstance(t, dict) for v in t.get("videos") or [] if isinstance(v, dict)]
    return {"out": str(out), "total": last_json.get("total"), "failed": last_json.get("failed"), "videos": videos}


def run_moneyprinter(args: list[str]) -> int:
    first = args[0] if args else "help"
    if first in ("-h", "--help", "help"):
        print(USAGE)
        return 0
    if first not in SUBCOMMANDS.split("|"):
        raise MoneyPrinterError(f"subcomando desconhecido: {first} ({SUBCOMMANDS})")
    if first == "clone":
        if len(args) > 2:
            raise MoneyPrinterError(f"clone recebe no máximo uma pasta; argumento a mais: {args[2]}")
        print(clone_moneyprinter(Path(args[1]) if len(args) > 1 else None))
        return 0
    d = find_moneyprinter_dir()
    if d is None:
        raise MoneyPrinterError("MoneyPrinterTurbo não encontrado: rode `simplicio-video moneyprinter clone` ou defina MONEYPRINTER_DIR.")
    if first in ("where", "status") and len(args) > 1:
        raise MoneyPrinterError(f"{first} não recebe argumentos; argumento a mais: {args[1]}")
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
    if first == "generate":
        return _generate(d, args[1:])
    if first == "run":
        return _run(d, args[1:])
    return _serve(d, args[1:])
