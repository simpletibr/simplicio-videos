"""`simplicio-video doctor [all|login] [--json] [--online]`: the environment overview, in the loop's `simplicio.doctor/v1`.

Ported from simplicio-loop simplicio_loop/doctor_overview.py (2034e2d). Twelve checks, each `ok`, `warn` or `fail` with the
command that fixes it, in this order:

  login          the shared login file (never fails for a missing or expired login: it is a warning)
  update         offline by default (the cached answer of the last `update --check`); --online asks GitHub or git
  distribution   source (a checkout) or pip (an installed package)
  runtime        the Simplicio Runtime (optional, always ok)
  python, node, ffmpeg, ffmpeg-libass, disk, ports, GEMINI_API_KEY (presence only, never the value)
  setup          the workspace: a warning when `simplicio-video setup` never ran, a failure when it is there and invalid

Output: `simplicio-video doctor: <status>`, then one line per check (`  ok    name   summary` and `        fix: ...`);
with --json, {"schema": "simplicio.doctor/v1", "status", "version", "checks": [{name, status, summary, fix, detail}]}.
Exit code 1 only when a check is `fail`. Nothing here installs, changes or prints a token. Breaking change: the old JSON was
{"ok", "checks": [{name, status, detail (a string), fix}]}.

Exemplos:
  simplicio-video doctor
  simplicio-video doctor --json
  simplicio-video doctor login
  docker compose run --rm simplicio doctor
"""
from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

import yaml

from .. import __version__, auth, distribution, hostos, paths
from . import update
from .setup import POL_SCHEMA, WS_LAYOUT, WS_SCHEMA, workspace_dir

SCHEMA = "simplicio.doctor/v1"
SECTIONS = ("login", "update", "distribution", "runtime", "python", "node", "ffmpeg", "ffmpeg-libass", "disk", "ports",
            "GEMINI_API_KEY", "setup")
_RANK = {"ok": 0, "warn": 1, "fail": 2}
GB = 1024**3
MIN_DISCO_GB = 5
NODE_MIN = 22
PY_MIN = (3, 12)
PY_MAX_EXCLUSIVO = (3, 14)  # the CrewAI extras need Python < 3.14
PORTAS = {3000: "opencut dev", 8000: "montage serve"}
SETUP_FIX = "rode `simplicio-video setup` para criar o workspace"
SETUP_FORCE_FIX = "rode `simplicio-video setup --force` para regravar o workspace"


def _row(name: str, status: str, summary: str, fix: Optional[str] = None, detail: Optional[dict] = None) -> dict:
    return {"name": name, "status": status, "summary": summary, "fix": fix, "detail": detail or {}}


def _stamp(seconds: float) -> str:
    return datetime.fromtimestamp(seconds, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def porta_livre(porta: int, host: str = "127.0.0.1") -> bool:
    """True if a bind on the port works. Kept as a function of its own: the tests replace it (sockets are blocked)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind((host, porta))
        except OSError:
            return False
    return True


def python_version() -> tuple:
    """(major, minor, micro) of the running Python. A function of its own so that the tests can say another one."""
    return tuple(sys.version_info[:3])


# --- login, update, distribution, runtime ------------------------------------------------------------------------------


def _login(environ: Optional[dict], now: float) -> dict:
    doc = auth.describe(environ, now)
    runtime = doc["runtime"]
    rt = f"Runtime {runtime['version'] or 'de versão desconhecida'}" if runtime["found"] else "Runtime não instalado"
    if not doc["logged_in"]:
        status = "warn" if doc["reason_code"] in {"login_missing", "login_expired"} else "fail"
        detail = f": {doc['detail']}" if doc.get("detail") else ""
        return _row("login", status, f"não logado ({doc['reason_code']}); arquivo {doc['path']}; {rt}{detail}", doc["fix"], doc)
    ent = doc.get("entitlement") or {}
    tier = f"direitos {ent.get('tier')} ({ent.get('status')}, em cache)" if ent else "direitos ainda não estão em cache"
    expiry = "expirou" if doc["access_expired"] else f"expira {_stamp(doc['access_expires_at'])}"
    summary = (f"logado como {doc['email'] or 'uma conta desconhecida'}; token de acesso {expiry}; {tier}; {rt}; "
               f"arquivo {doc['path']}")
    return _row("login", "ok", summary, None, doc)


def _update(online: bool, installed: str, fetch: Callable[[], str], state_dir: Path, kind: str, git: Callable) -> dict:
    fix = "simplicio-video update"
    if online:
        try:
            info = update.check_latest(kind, installed, fetch=fetch, git=git)
        except (OSError, ValueError, KeyError, update.Refused) as exc:
            return _row("update", "warn", f"não consegui consultar a última versão de {update.REPO}: {exc}")
        update.write_check(info, state_dir)
        detail = {**info, "checked_at": int(time.time())}
        if info["update_available"]:
            return _row("update", "warn", f"atualização disponível: {installed} -> {info['latest']} (consultado agora)", fix, detail)
        return _row("update", "ok", f"em dia: {installed} (última versão {info['latest']}, consultado agora)", None, detail)
    cached = update.read_check(state_dir)
    if not cached or not cached.get("latest"):
        return _row("update", "ok", "nenhuma checagem em cache; rode `simplicio-video update --check` ou "
                                    "`simplicio-video doctor --online`")
    try:
        available = update.parse_version(str(cached["latest"])) > update.parse_version(installed)
    except ValueError:
        return _row("update", "ok", "a checagem em cache está ilegível; rode `simplicio-video doctor --online`")
    when = _stamp(float(cached.get("checked_at") or 0))
    detail = {**cached, "installed": installed, "update_available": available}
    if available:
        return _row("update", "warn", f"atualização disponível: {installed} -> {cached['latest']} "
                                      f"(checagem em cache de {when}; `doctor --online` consulta agora)", fix, detail)
    return _row("update", "ok", f"em dia: {installed} (última versão {cached['latest']}, checagem em cache de {when})", None, detail)


def _distribution(kind: str, installed: str) -> dict:
    what = {distribution.PIP: f"pip: pacote instalado {installed} (sem checkout)",
            distribution.SOURCE: f"source: checkout git ou instalação editável, versão {installed}"}[kind]
    return _row("distribution", "ok", what, None, {"kind": kind, "version": installed})


def _runtime(environ: Optional[dict]) -> dict:
    binary = auth.runtime_binary(environ)
    if binary is None:
        return _row("runtime", "ok", "Simplicio Runtime não instalado (opcional: só o `simplicio-video login` precisa dele)",
                    None, {"found": False})
    version = auth.runtime_version(binary)
    return _row("runtime", "ok", f"Simplicio Runtime {version or '(versão desconhecida)'} em {binary}; "
                "compartilha o arquivo de login com o simplicio-video", None,
                {"found": True, "path": str(binary), "version": version, "shared_login": True})


# --- python, node, ffmpeg, disk, ports, credentials ----------------------------------------------------------------------


def _checa_python() -> dict:
    v = python_version()
    nome = ".".join(str(x) for x in v)
    detail = {"version": nome}
    if v[:2] < PY_MIN:
        return _row("python", "fail", f"Python {nome}",
                    f"instale Python {PY_MIN[0]}.{PY_MIN[1]} (`./install.sh --python 3.12`) e rode o doctor de novo", detail)
    if v[:2] >= PY_MAX_EXCLUSIVO:
        return _row("python", "warn", f"Python {nome}",
                    "os extras do CrewAI exigem Python < 3.14; use `./install.sh --python 3.12`", detail)
    return _row("python", "ok", f"Python {nome}", None, detail)


def _checa_node(environ: Optional[dict]) -> dict:
    fix = f"instale Node {NODE_MIN} ou superior ({hostos.hint('node')}) e rode o doctor de novo"
    caminho = hostos.find_tool("node", environ)
    if not caminho:
        return _row("node", "fail", "node não encontrado no PATH", fix)
    detail = {"path": caminho}
    try:
        r = subprocess.run([caminho, "--version"], capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.SubprocessError) as e:
        return _row("node", "fail", f"node não executa: {e}", fix, detail)
    m = re.match(r"\s*v?(\d+)", r.stdout or "")
    if r.returncode != 0 or not m:
        return _row("node", "fail", "node não respondeu à versão", fix, detail)
    major = int(m.group(1))
    detail["version"] = r.stdout.strip()
    if major < NODE_MIN:
        return _row("node", "fail", f"node v{major} (exigido: {NODE_MIN} ou superior)", fix, detail)
    return _row("node", "ok", f"node {r.stdout.strip()}", None, detail)


def _checa_ffmpeg(environ: Optional[dict]) -> list[dict]:
    fix = f"instale ffmpeg com libass ({hostos.hint('ffmpeg')}) e rode o doctor de novo"
    libass_fix = ("reinstale o ffmpeg com libass: o do Homebrew (`brew install ffmpeg`) e o Gyan.FFmpeg do winget já trazem; "
                  "no Linux, use um pacote compilado com --enable-libass")
    caminho = hostos.find_tool("ffmpeg", environ)
    if not caminho:
        return [_row("ffmpeg", "fail", "ffmpeg não encontrado no PATH", fix)]
    detail = {"path": caminho}
    try:
        r = subprocess.run([caminho, "-version"], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError) as e:
        return [_row("ffmpeg", "fail", f"ffmpeg não executa: {e}", fix, detail)]
    saida = (r.stdout or "") + (r.stderr or "")
    if r.returncode != 0 or not saida.strip():
        return [_row("ffmpeg", "fail", "ffmpeg não respondeu à versão", fix, detail)]
    primeira = saida.strip().splitlines()[0]
    achados = [_row("ffmpeg", "ok", primeira, None, detail)]
    if "--enable-libass" in saida:
        achados.append(_row("ffmpeg-libass", "ok", "compilado com --enable-libass", None, detail))
    else:
        achados.append(_row("ffmpeg-libass", "fail", "ffmpeg sem libass (legendas e textos do render exigem libass)",
                            libass_fix, detail))
    return achados


def _checa_disco(anchor: Path, usage: Callable[[Any], Any]) -> dict:
    where = anchor
    while not where.exists() and where != where.parent:
        where = where.parent
    try:
        free = int(usage(where).free)
    except OSError as e:
        return _row("disk", "warn", f"não consegui medir o disco em {where}: {e}")
    livre_gb = free / GB
    detail = {"dir": str(where), "free_bytes": free, "floor_bytes": MIN_DISCO_GB * GB}
    resumo = f"{livre_gb:.1f} GB livres em {where}"
    if livre_gb < MIN_DISCO_GB:
        return _row("disk", "fail", resumo, f"libere pelo menos {MIN_DISCO_GB} GB em {where} (hoje: {livre_gb:.1f} GB); "
                    "o .venv e o render precisam de espaço", detail)
    return _row("disk", "ok", resumo, None, detail)


def _checa_portas() -> dict:
    busy = [p for p in PORTAS if not porta_livre(p)]
    detail = {"ports": sorted(PORTAS), "busy": busy}
    if busy:
        return _row("ports", "warn", "em uso: " + ", ".join(f"{p} ({PORTAS[p]})" for p in busy),
                    "pare o processo que usa a porta, ou ignore se for o seu servidor (opencut dev e montage serve "
                    "usam essas portas)", detail)
    return _row("ports", "ok", ", ".join(str(p) for p in PORTAS) + " livres", None, detail)


def _checa_credencial(environ: dict) -> dict:
    nome = "GEMINI_API_KEY"
    if environ.get(nome):
        return _row(nome, "ok", f"{nome} definida (valor oculto)", None, {"set": True})
    return _row(nome, "warn", f"{nome} não definida",
                f"defina {nome} para voz via Gemini (aistudio.google.com/apikey). Sem ela, o MVP usa a voz local, sem custo",
                {"set": False})


def _carrega(caminho: Path):
    """(data, error). data is None when the file does not read or is not a YAML mapping."""
    try:
        dados = yaml.safe_load(caminho.read_text(encoding="utf8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as e:
        return None, f"ilegível: {e}"
    if not isinstance(dados, dict):
        return None, "não é um mapa YAML"
    return dados, None


def _checa_setup() -> dict:
    """warn when `setup` never ran (a file is missing); fail when a file is there and invalid."""
    ws = workspace_dir()
    wsp, pol = ws / "workspace.yaml", ws / "policy.yaml"
    detail = {"workspace": str(ws), "workspace_yaml": wsp.is_file(), "policy_yaml": pol.is_file()}
    invalidos, ausentes = [], []
    dados = None
    if not wsp.is_file():
        ausentes.append("workspace.yaml")
    else:
        dados, erro = _carrega(wsp)
        if erro:
            invalidos.append(f"workspace.yaml {erro}")
        elif dados.get("schema") != WS_SCHEMA or dados.get("workspace") != WS_LAYOUT:
            invalidos.append(f"workspace.yaml com schema {dados.get('schema')!r} e layout {dados.get('workspace')!r} "
                             f"(esperado {WS_SCHEMA} e {WS_LAYOUT})")
    autonomia = None
    if not pol.is_file():
        ausentes.append("policy.yaml")
    else:
        pdados, perro = _carrega(pol)
        autonomia = (pdados or {}).get("autonomy") if not perro else None
        if perro or (pdados or {}).get("schema") != POL_SCHEMA or not isinstance(autonomia, dict):
            invalidos.append(f"policy.yaml {perro or 'sem schema ou autonomia válidos'}")
    if invalidos:
        return _row("setup", "fail", f"workspace em {ws} inválido: " + "; ".join(invalidos), SETUP_FORCE_FIX, detail)
    if ausentes:
        return _row("setup", "warn", f"o setup ainda não rodou (falta {' e '.join(ausentes)} em {ws}); "
                    "nenhum comando do motor lê o workspace", SETUP_FIX, detail)
    return _row("setup", "ok", f"{ws} (layout {WS_LAYOUT}, idioma {dados.get('language')}, autonomia {autonomia.get('default')})",
                None, detail)


# --- the overview -------------------------------------------------------------------------------------------------------


def collect(*, online: bool = False, environ: Optional[dict] = None, now: Optional[float] = None,
            fetch: Optional[Callable[[], str]] = None, only: Optional[str] = None, installed: Optional[str] = None,
            kind: Optional[str] = None, state_dir: Optional[Path] = None, usage: Optional[Callable[[Any], Any]] = None,
            git: Optional[Callable] = None) -> dict:
    stamp = time.time() if now is None else now
    env = dict(os.environ) if environ is None else environ
    installed = installed or __version__
    state_dir = state_dir or update.default_state_dir()
    wanted = [only] if only else list(SECTIONS)
    kind = kind or distribution.kind()
    fetch = fetch or update.fetch_latest_tag
    git = git or update._git
    usage = usage or shutil.disk_usage
    # a package has no checkout: measure the folder where the venvs, tools and renders go, never site-packages
    anchor = paths.home() if kind == distribution.SOURCE else state_dir
    cache: dict = {}

    def ffmpeg() -> list:
        if "ffmpeg" not in cache:
            cache["ffmpeg"] = _checa_ffmpeg(env)
        return cache["ffmpeg"]

    makers: dict[str, Callable[[], dict]] = {
        "login": lambda: _login(env, stamp),
        "update": lambda: _update(online, installed, fetch, state_dir, kind, git),
        "distribution": lambda: _distribution(kind, installed),
        "runtime": lambda: _runtime(env),
        "python": _checa_python,
        "node": lambda: _checa_node(env),
        "ffmpeg": lambda: ffmpeg()[0],
        "ffmpeg-libass": lambda: ffmpeg()[1] if len(ffmpeg()) > 1 else _row(
            "ffmpeg-libass", "warn", "sem ffmpeg não há como checar o libass", ffmpeg()[0]["fix"]),
        "disk": lambda: _checa_disco(anchor, usage),
        "ports": _checa_portas,
        "GEMINI_API_KEY": lambda: _checa_credencial(env),
        "setup": _checa_setup,
    }
    checks = [makers[name]() for name in wanted]
    worst = max((check["status"] for check in checks), key=_RANK.__getitem__, default="ok")
    return {"schema": SCHEMA, "status": worst, "version": installed, "checks": checks}


def _texto(doc: dict) -> str:
    lines = [f"simplicio-video doctor: {doc['status']}"]
    for check in doc["checks"]:
        lines.append(f"  {check['status']:<5} {check['name']:<14} {check['summary']}")
        if check["fix"]:
            lines.append(f"        fix: {check['fix']}")
    return "\n".join(lines)


def run(a) -> int:
    only = None if a.what == "all" else a.what
    doc = collect(online=a.online, only=only)
    hostos.say(json.dumps(doc, sort_keys=True) if a.json else _texto(doc))  # ensure_ascii: valid on any console
    return 1 if doc["status"] == "fail" else 0
