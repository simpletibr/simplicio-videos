"""`simplicio-video login | logout | auth status`: ONE Simplicio login, shared with the Simplicio Runtime.

Ported from simplicio-loop simplicio_loop/auth_cli.py (2034e2d). The login file, its checks and its lock live in
`simplicio_video.auth`; this module is the command line:

* login: with the Runtime installed, run its flow (`simplicio login google`, terminal attached) and then check the shared
  file. WITHOUT the Runtime the login is UNVERIFIED: no authorize or device endpoint is documented in THIS repository, so
  none is invented; the command prints how to install the Runtime (and does not run those commands).
* logout: delete the shared file. It logs the Runtime out too, so it needs --yes. It only deletes a file that has the shape of
  a login (SIMPLICIO_AUTH_FILE can point anywhere, an ssh key included): anything else is refused, exit 2, `not_a_login_file`.
* auth status: what the file says. Never a token, the e-mail is masked.

Decision of the owner: this is a mirror. It stores no credential, takes no token by argument, unlocks nothing and charges
nothing; no engine command depends on it, and it is not in plugin.json or the MCP server. The Runtime child gets a minimal
environment (no GH_TOKEN, API keys or SIMPLICIO_LOGIN_TOKEN of the developer's shell).

Exit codes: 0 done / logged in, 1 not logged in or not verified, 2 refused (logout without --yes, logout of a file that is not a
login, --no-browser impossible).

Exemplos:
  simplicio-video login
  simplicio-video auth status --json
  simplicio-video logout --yes
"""
from __future__ import annotations

import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from typing import Any, Callable, Optional
from urllib.parse import parse_qs, urlsplit

from .. import auth, hostos

# Printed by the UNVERIFIED answer; this command never runs them. The commands are the ones in the Runtime's own INSTALL.md
# (simplicio-runtime 1c7919a). simplicio-loop 2034e2d still prints the Runtime's old organisation name.
RUNTIME_INSTALL = {
    "macOS / Linux": "curl -fsSL https://raw.githubusercontent.com/simpletibr/simplicio/master/install.sh | sh",
    "Windows (PowerShell)": "irm https://raw.githubusercontent.com/simpletibr/simplicio/master/install.ps1 | iex",
}
RUNTIME_INSTALL_DOC = "https://github.com/simpletibr/simplicio-runtime/blob/main/INSTALL.md"
STANDALONE_UNVERIFIED = (
    "O login próprio é UNVERIFIED: nenhum endpoint de autorização ou de dispositivo está documentado neste repositório, "
    "então o simplicio-video não inicia um login por conta própria. Instale o Simplicio Runtime (ele entra com o Google) "
    "e rode: simplicio-video login"
)

# What `simplicio login google` is given: a closed list of EXACT names. Everything else is left out on purpose, because the shell
# of a developer holds other programs' credentials (GH_TOKEN, API keys, SIMPLICIO_LOGIN_TOKEN) and a sign-in needs none of
# them. No prefix is let through (`LC_*` and `XDG_*` used to be): `LC_TOKEN` or `XDG_SECRET` would have gone along. Why each group:
#   locale       LANG, LANGUAGE, LC_ALL, LC_CTYPE, LC_MESSAGES: the Runtime prints accents
#   desktop      XDG_RUNTIME_DIR (the sockets of the session bus and the display), XDG_CURRENT_DESKTOP, XDG_SESSION_TYPE and
#                XDG_SESSION_DESKTOP (what xdg-open reads to pick the opener), XDG_CONFIG_HOME, XDG_CONFIG_DIRS, XDG_DATA_HOME
#                and XDG_DATA_DIRS (where it finds mimeapps.list and the browser's .desktop file): the browser has to open
_CHILD_ENV = frozenset({
    "PATH", "HOME", "USERPROFILE", "HOMEDRIVE", "HOMEPATH", "USER", "LOGNAME", "SHELL", "TERM", "COLORTERM", "LANG", "LANGUAGE",
    "LC_ALL", "LC_CTYPE", "LC_MESSAGES", "XDG_RUNTIME_DIR", "XDG_CURRENT_DESKTOP", "XDG_SESSION_TYPE", "XDG_SESSION_DESKTOP",
    "XDG_CONFIG_HOME", "XDG_CONFIG_DIRS", "XDG_DATA_HOME", "XDG_DATA_DIRS",
    "TZ", "TMPDIR", "TEMP", "TMP", "DISPLAY", "WAYLAND_DISPLAY", "DBUS_SESSION_BUS_ADDRESS", "BROWSER", "SYSTEMROOT", "WINDIR",
    "COMSPEC", "PATHEXT", "APPDATA", "LOCALAPPDATA", "PROGRAMDATA", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY",
    "http_proxy", "https_proxy", "all_proxy", "no_proxy", "SSL_CERT_FILE", "SSL_CERT_DIR", auth.RUNTIME_ENV,
    "SIMPLICIO_AUTH_BASE_URL", "SIMPLICIO_HOME",
})


def _runtime_env(env: dict) -> dict:
    return {name: value for name, value in env.items() if name in _CHILD_ENV}


def _print(doc: dict, as_json: bool, lines: list) -> None:
    # ensure_ascii: the JSON is valid on any console and any codec, whatever the accents and the folder names
    hostos.say(json.dumps(doc, sort_keys=True) if as_json else "\n".join(lines))


def _when(timestamp: int, now: float) -> str:
    stamp = hostos.utc_stamp(timestamp)  # the date is plain arithmetic: no OSError past year 3000 on Windows
    seconds = int(abs(timestamp - now))
    span = (f"{seconds // 86400} d" if seconds >= 2 * 86400 else f"{seconds // 3600} h" if seconds >= 2 * 3600
            else f"{seconds // 60} min" if seconds >= 120 else f"{seconds} s")
    return f"{'em ' + span if timestamp > now else 'há ' + span} ({stamp})"


def _status_lines(doc: dict, now: float) -> list:
    runtime = doc["runtime"]
    rt = f"{runtime['version'] or 'versão desconhecida'} em {runtime['path']}" if runtime["found"] else "não encontrado"
    if not doc.get("logged_in"):
        lines = [f"login: não logado ({doc['reason_code']})", f"  arquivo             {doc['path']}"]
        if doc.get("detail"):
            lines.append(f"  detalhe             {doc['detail']}")
        lines += [f"  correção            {doc['fix']}", f"  runtime             {rt}"]
    else:
        access = doc["access_expires_at"]
        lines = [
            "login: logado" + (" (compartilhado com o Simplicio Runtime)" if runtime["found"] else ""),
            f"  arquivo             {doc['path']}",
            f"  conta               {doc['email'] or 'desconhecida'}",
            f"  token de acesso     {'expirou ' if doc['access_expired'] else 'expira '}{_when(access, now)}",
            "  token de renovação  " + ("nenhum" if not doc["has_refresh_token"] else
                                       "expirado" if doc["refresh_expired"] else
                                       f"válido até {_when(doc['refresh_expires_at'], now)}" if doc["refresh_expires_at"]
                                       else "válido, sem data de validade"),
        ]
        ent = doc.get("entitlement")
        if ent:
            lines.append(f"  direitos            {ent.get('tier')}, {ent.get('status')}, {ent.get('source')} "
                         "(em cache no arquivo; o motor não decide nada com isto)")
        lines.append(f"  runtime             {rt}")
    if not doc["shared_with_runtime"]:
        lines.append(f"AVISO: o simplicio-video usa um arquivo de login DIFERENTE do Runtime ({doc['runtime_path']})")
    return lines


# --- auth status -----------------------------------------------------------------------------------------------------


def status(*, as_json: bool = False, environ: Optional[dict] = None) -> int:
    now = time.time()
    doc = auth.describe(environ, now)
    _print(doc, as_json, _status_lines(doc, now))
    return 0 if doc["logged_in"] else 1


# --- login -----------------------------------------------------------------------------------------------------------


def _run_runtime(command: list, env: dict, stdout: Optional[int]) -> int:
    return subprocess.call(command, env=env, stdout=stdout)


# --no-browser: Runtime 3.10.0 ignores BROWSER and runs the system opener, so the child gets opener stand-ins first on its
# PATH. They open nothing: they keep the sign-in address and print it, so the user can open it by hand. `open` is the macOS
# opener (UNVERIFIED on a real macOS: a Runtime that runs /usr/bin/open by its absolute path is not stopped by a stand-in).
_BROWSER_OPENERS = ("xdg-open", "open", "gio", "gnome-open", "kde-open", "sensible-browser", "x-www-browser", "wslview")
# The stand-in records only an http(s) address made of printable ASCII, and only the FIRST one: `gio trash` or `gio mount -l`
# must not become the sign-in address. It runs no external program (`${0%/*}`, not `dirname`).
_OPENER_SHIM = r"""#!/bin/sh
LC_ALL=C
for url; do
  case $url in http://*|https://*) ;; *) continue ;; esac
  case $url in *[![:graph:]]*) continue ;; esac
  file=${0%/*}/sign-in-url
  [ -e "$file" ] && exit 0
  printf '%s\n' "$url" > "$file"
  printf 'Open this address in a browser to sign in:\n  %s\n' "$url" >&2
  exit 0
done
"""
_DISPLAY_ENV = ("DISPLAY", "WAYLAND_DISPLAY", "DBUS_SESSION_BUS_ADDRESS")
_PRINTABLE_ASCII = re.compile(r"[!-~]+")  # no space, no control character, no newline, nothing above ASCII


def _can_block_browser() -> bool:
    return not hostos.is_windows()  # Windows opens the address with no program on PATH that could stand in


def _install_browser_shim(child: dict) -> str:
    for name in _DISPLAY_ENV:  # without them a Runtime that calls the opener by its absolute path opens no window
        child.pop(name, None)
    shim_dir = tempfile.mkdtemp(prefix="simplicio-no-browser-")
    try:
        for name in _BROWSER_OPENERS:
            opener = os.path.join(shim_dir, name)
            with open(opener, "w", encoding="utf-8") as handle:
                handle.write(_OPENER_SHIM)
            os.chmod(opener, 0o755)
    except BaseException:
        shutil.rmtree(shim_dir, ignore_errors=True)
        raise
    inherited = child.get("PATH", "")
    child["PATH"] = shim_dir + (os.pathsep + inherited if inherited else "")  # an empty entry would mean the cwd
    child["BROWSER"] = "true"
    return shim_dir


def _printable(text: str) -> bool:
    return _PRINTABLE_ASCII.fullmatch(text) is not None


def _read_sign_in(shim_dir: Optional[str]) -> dict:
    if shim_dir is None:
        return {}
    try:
        with open(os.path.join(shim_dir, "sign-in-url"), encoding="utf-8", errors="replace") as handle:
            url = handle.read().strip()
        if not url.startswith(("http://", "https://")) or not _printable(url):
            return {}  # it is printed on the terminal: no escape sequence, no newline
        codes = [code for code in parse_qs(urlsplit(url).query).get("user_code", []) if _printable(code)]
    except (OSError, ValueError):  # an address like http://[::1/ is a ValueError (so is UnicodeDecodeError)
        return {}
    return {"sign_in_url": url, **({"user_code": codes[0]} if codes else {})}


# SIGTERM and SIGHUP end the login like Ctrl-C does, so the `finally` of login() removes the temp dir (it holds the user code).
def _stop_on_signal(signum: int, frame: Any) -> None:
    raise SystemExit(128 + signum)


def _trap_signals() -> dict:
    if threading.current_thread() is not threading.main_thread():
        return {}  # signal.signal() works in the main thread only
    wanted = [getattr(signal, name) for name in ("SIGTERM", "SIGHUP") if hasattr(signal, name)]  # Windows has no SIGHUP
    return {sig: signal.signal(sig, _stop_on_signal) for sig in wanted}


def _sign_in_lines(sign_in: dict) -> list:
    if not sign_in:
        return []
    lines = ["", f"Abra este endereço no navegador para entrar: {sign_in['sign_in_url']}"]
    if sign_in.get("user_code"):
        lines.append(f"Código: {sign_in['user_code']}")
    return lines


def _refuse_no_browser(env: dict, as_json: bool, why: str) -> int:
    doc = auth.describe(env)
    version = doc["runtime"]["version"] or "desconhecida"
    detail = (f"--no-browser não é suportado neste sistema: o Simplicio Runtime {version} {why}. "
              "Rode: simplicio-video login")
    doc.update(schema="simplicio.login/v1", status="REFUSED", reason_code="no_browser_unsupported", detail=detail)
    _print(doc, as_json, [f"login: {detail}"])
    return 2


def login(*, as_json: bool = False, no_browser: bool = False, environ: Optional[dict] = None,
          run: Callable[[list, dict, Optional[int]], int] = _run_runtime) -> int:
    env = dict(os.environ if environ is None else environ)
    runtime = auth.runtime_binary(env)
    if runtime is None:
        doc = auth.describe(env)
        doc.update(schema="simplicio.login/v1", status="UNVERIFIED", reason_code="standalone_login_unverified",
                   detail=STANDALONE_UNVERIFIED, install=RUNTIME_INSTALL, install_doc=RUNTIME_INSTALL_DOC)
        lines = ["login: Simplicio Runtime não encontrado", STANDALONE_UNVERIFIED, ""]
        lines += [f"  {name}: {command}" for name, command in RUNTIME_INSTALL.items()]
        lines += [f"  (documentado em {RUNTIME_INSTALL_DOC}; este comando não os executa)"]
        if doc["logged_in"]:
            lines += ["", f"(já existe um login utilizável em {doc['path']}; rode: simplicio-video auth status)"]
        _print(doc, as_json, lines)
        return 1
    child = _runtime_env(env)
    if no_browser and not _can_block_browser():
        return _refuse_no_browser(env, as_json, "abre o navegador sozinho e não tem opção para impedir")
    shim_dir = None
    if no_browser:
        try:
            shim_dir = _install_browser_shim(child)
        except OSError as exc:
            return _refuse_no_browser(env, as_json, "abre o navegador sozinho, e os substitutos que o impedem "
                                                    f"não puderam ser instalados ({exc})")
    previous = _trap_signals() if no_browser else {}
    sys.stdout.flush()
    start_error = ""
    try:
        # --json: the Runtime's own output goes to stderr, so stdout stays one document. Nothing but `login google` is passed.
        try:
            code = run([str(runtime), "login", "google"], child, 2 if as_json else None)
        except OSError as exc:  # a file called `simplicio` that cannot be executed (a bad download, the wrong architecture)
            code, start_error = 127, str(exc.strerror or exc)
        sign_in = _read_sign_in(shim_dir)
    finally:
        if shim_dir is not None:
            shutil.rmtree(shim_dir, ignore_errors=True)
        for sig, handler in previous.items():
            signal.signal(sig, handler)
    doc = auth.describe(env)
    doc.update(schema="simplicio.login/v1", runtime_exit_code=code)
    doc.update(sign_in)
    if code != 0:
        doc.update(status="NOT_VERIFIED", reason_code="runtime_login_failed", logged_in=False, fix="simplicio-video login")
        if start_error:
            doc["detail"] = f"não consegui iniciar o Runtime ({runtime}): {start_error}"
        why = (f"não consegui iniciar o Runtime ({start_error}); o login não foi verificado" if start_error else
               f"o login do Runtime terminou com o código {code}; o login não foi verificado")
        _print(doc, as_json, [f"login: {why}"] + _sign_in_lines(sign_in))
        return 1
    if not doc["logged_in"]:
        doc["status"] = "NOT_VERIFIED"
        _print(doc, as_json, ["login: o Runtime terminou, mas o arquivo de login compartilhado não serve"]
               + _status_lines(doc, time.time()) + _sign_in_lines(sign_in))
        return 1
    doc["status"] = "VERIFIED"
    _print(doc, as_json, ["login: verificado no arquivo de login compartilhado"] + _status_lines(doc, time.time())[1:])
    return 0


# --- logout ----------------------------------------------------------------------------------------------------------


def logout(*, yes: bool = False, as_json: bool = False, environ: Optional[dict] = None) -> int:
    path, runtime_path = auth.login_path(environ), auth.runtime_login_path(environ)
    shared = path == runtime_path  # the Runtime is logged out too only when it reads this very file
    doc: dict[str, Any] = {"schema": "simplicio.logout/v1", "path": str(path), "runtime_path": str(runtime_path),
                           "also_logs_out_runtime": shared}
    if not yes:
        doc.update(status="REFUSED", reason_code="confirmation_required")
        about = (f"{path} é compartilhado com o Simplicio Runtime: sair aqui também desloga o Runtime." if shared else
                 f"{path} é o login só do simplicio-video. O Runtime lê {runtime_path} e continua logado.")
        _print(doc, as_json, [f"logout: {about}", "Nada foi apagado. Rode de novo com --yes para sair."])
        return 2
    try:
        removed = auth.clear_login(path)
    except auth.LoginError as exc:
        refused = exc.reason_code == "not_a_login_file"  # not a login: a refusal (exit 2), nothing was tried
        doc.update(status="REFUSED" if refused else "FAILED", reason_code=exc.reason_code, detail=str(exc))
        _print(doc, as_json, [f"logout: {exc}"])
        return 2 if refused else 1
    doc["status"] = "LOGGED_OUT" if removed else "NO_LOGIN"
    lines = [f"logout: removido {path}. " + ("O Runtime também foi deslogado (arquivo compartilhado)." if shared else
                                             f"O Runtime lê {runtime_path}, então continua logado."),
             "O token de renovação não é revogado no servidor: nenhum endpoint de revogação está documentado neste repositório."]
    if not removed:
        lines = [f"logout: não há arquivo de login em {path}; nada a remover"]
    _print(doc, as_json, lines)
    return 0


# --- the command line ------------------------------------------------------------------------------------------------


def run(a) -> int:
    """Dispatch of the parsed arguments (cli.py): `login`, `logout` and `auth status`."""
    if a.cmd == "login":
        return login(as_json=a.json, no_browser=a.no_browser)
    if a.cmd == "logout":
        return logout(yes=a.yes, as_json=a.json)
    return status(as_json=a.json)
