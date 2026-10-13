"""`simplicio-video doctor [--json]` (issue #43): diagnóstico do ambiente, com a correção exata de cada falha.

Checa: Python, Node 22 ou superior, ffmpeg com libass, 5 GB livres, portas de desenvolvimento, presença de
credenciais (nunca o valor) e workspace. Não instala, não altera e não grava nada. Ferramentas são
chamadas com subprocess.run (com timeout).

Contrato de saída:
  {"ok": bool, "checks": [{"name": str, "status": "ok"|"warn"|"fail", "detail": str, "fix": str|null}, ...]}
  Exit code 0 se nenhuma checagem falhou (aviso não reprova); 1 se alguma falhou.

Exemplos:
  simplicio-video doctor
  simplicio-video doctor --json
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
from pathlib import Path

import yaml

from .. import __version__, paths
from .setup import POL_SCHEMA, WS_LAYOUT, WS_SCHEMA, workspace_dir

GB = 1024**3
MIN_DISCO_GB = 5
NODE_MIN = 22
PY_MIN = (3, 12)
PY_MAX_EXCLUSIVO = (3, 14)  # os extras do CrewAI exigem Python < 3.14
PORTAS = {3000: "opencut dev", 8000: "montage serve"}
CREDENCIAIS = ("GEMINI_API_KEY",)  # só presença; o valor nunca entra na saída

NODE_FIX = "instale Node 22 ou superior (ex.: `nvm install 22`) e rode o doctor de novo"
FFMPEG_FIX = ("instale ffmpeg com libass (macOS: `brew install ffmpeg`; Debian/Ubuntu: `apt install ffmpeg`) "
              "e rode o doctor de novo")
LIBASS_FIX = ("reinstale o ffmpeg com libass: no macOS, `brew install ffmpeg` já inclui libass; no Linux, use um "
              "pacote compilado com --enable-libass")
SETUP_FIX = "rode `simplicio-video setup` para criar o workspace"
ROTULO = {"ok": "ok", "warn": "aviso", "fail": "falha"}


def _c(name: str, status: str, detail: str, fix: str | None = None) -> dict:
    return {"name": name, "status": status, "detail": detail, "fix": fix}


def porta_livre(porta: int, host: str = "127.0.0.1") -> bool:
    """True se um bind na porta funciona. Função isolada: os testes a trocam, porque sockets são bloqueados."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind((host, porta))
        except OSError:
            return False
    return True


def _checa_python() -> dict:
    v = sys.version_info
    nome = f"{v.major}.{v.minor}.{v.micro}"
    if (v.major, v.minor) < PY_MIN:
        return _c("python", "fail", f"Python {nome}",
                  f"instale Python {PY_MIN[0]}.{PY_MIN[1]} (`./install.sh --python 3.12`) e rode o doctor de novo")
    if (v.major, v.minor) >= PY_MAX_EXCLUSIVO:
        return _c("python", "warn", f"Python {nome}",
                  "os extras do CrewAI exigem Python < 3.14; use `./install.sh --python 3.12`")
    return _c("python", "ok", f"Python {nome}")


def _checa_node() -> dict:
    caminho = shutil.which("node")
    if not caminho:
        return _c("node", "fail", "node não encontrado no PATH", NODE_FIX)
    try:
        r = subprocess.run([caminho, "--version"], capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.SubprocessError) as e:
        return _c("node", "fail", f"node não executa: {e}", NODE_FIX)
    m = re.match(r"\s*v?(\d+)", r.stdout or "")
    if r.returncode != 0 or not m:
        return _c("node", "fail", "node não respondeu à versão", NODE_FIX)
    major = int(m.group(1))
    if major < NODE_MIN:
        return _c("node", "fail", f"node v{major} (exigido: {NODE_MIN} ou superior)", NODE_FIX)
    return _c("node", "ok", f"node {r.stdout.strip()}")


def _checa_ffmpeg() -> list[dict]:
    caminho = shutil.which("ffmpeg")
    if not caminho:
        return [_c("ffmpeg", "fail", "ffmpeg não encontrado no PATH", FFMPEG_FIX)]
    try:
        r = subprocess.run([caminho, "-version"], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError) as e:
        return [_c("ffmpeg", "fail", f"ffmpeg não executa: {e}", FFMPEG_FIX)]
    saida = (r.stdout or "") + (r.stderr or "")
    if r.returncode != 0 or not saida.strip():
        return [_c("ffmpeg", "fail", "ffmpeg não respondeu à versão", FFMPEG_FIX)]
    primeira = saida.strip().splitlines()[0]
    achados = [_c("ffmpeg", "ok", primeira)]
    if "--enable-libass" in saida:
        achados.append(_c("ffmpeg libass", "ok", "compilado com --enable-libass"))
    else:
        achados.append(_c("ffmpeg libass", "fail", "ffmpeg sem libass (legendas e textos do render exigem libass)",
                          LIBASS_FIX))
    return achados


def _checa_disco() -> dict:
    ancora = paths.home()
    if not ancora.exists():
        ancora = Path.cwd()
    try:
        st = os.statvfs(str(ancora))
    except OSError as e:
        return _c("disco livre", "warn", f"não consegui medir o disco em {ancora}: {e}")
    livre_gb = st.f_bavail * st.f_frsize / GB
    detalhe = f"{livre_gb:.1f} GB livres em {ancora}"
    if livre_gb < MIN_DISCO_GB:
        return _c("disco livre", "fail", detalhe,
                  f"libere pelo menos {MIN_DISCO_GB} GB em {ancora} (hoje: {livre_gb:.1f} GB); o .venv e o render "
                  "precisam de espaço")
    return _c("disco livre", "ok", detalhe)


def _checa_portas() -> dict:
    ocupadas = [f"{p} ({uso})" for p, uso in PORTAS.items() if not porta_livre(p)]
    if ocupadas:
        return _c("portas", "warn", "em uso: " + ", ".join(ocupadas),
                  "pare o processo que usa a porta, ou ignore se for o seu servidor (opencut dev e montage serve "
                  "usam essas portas)")
    return _c("portas", "ok", ", ".join(str(p) for p in PORTAS) + " livres")


def _checa_credenciais() -> list[dict]:
    achados = []
    for nome in CREDENCIAIS:
        if os.environ.get(nome):
            achados.append(_c(nome, "ok", f"{nome} definida (valor oculto)"))
        else:
            achados.append(_c(nome, "warn", f"{nome} não definida",
                              f"defina {nome} para voz via Gemini (aistudio.google.com/apikey). Sem ela, o MVP usa a "
                              "voz local, sem custo"))
    return achados


def _carrega(caminho: Path):
    """(dados, erro). dados é None quando o arquivo não existe, não lê ou não é um mapa YAML."""
    try:
        dados = yaml.safe_load(caminho.read_text(encoding="utf8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as e:
        return None, f"ilegível: {e}"
    if not isinstance(dados, dict):
        return None, "não é um mapa YAML"
    return dados, None


def _checa_workspace() -> list[dict]:
    ws = workspace_dir()
    achados = []
    wsp = ws / "workspace.yaml"
    if not wsp.is_file():
        achados.append(_c("workspace", "fail", f"sem workspace.yaml em {ws}", SETUP_FIX))
    else:
        dados, erro = _carrega(wsp)
        if erro:
            achados.append(_c("workspace", "fail", f"workspace.yaml {erro}",
                              "rode `simplicio-video setup --force` para regravar o workspace"))
        elif dados.get("schema") != WS_SCHEMA or dados.get("workspace") != WS_LAYOUT:
            achados.append(_c("workspace", "fail",
                              f"workspace.yaml com schema {dados.get('schema')!r} e layout {dados.get('workspace')!r} "
                              f"(esperado {WS_SCHEMA} e {WS_LAYOUT})",
                              "rode `simplicio-video setup --force` para regravar o workspace"))
        else:
            achados.append(_c("workspace", "ok", f"{ws} (layout {WS_LAYOUT}, idioma {dados.get('language')})"))
    pol = ws / "policy.yaml"
    if not pol.is_file():
        achados.append(_c("workspace policy", "fail", f"sem policy.yaml em {ws}", SETUP_FIX))
    else:
        dados, erro = _carrega(pol)
        autonomia = (dados or {}).get("autonomy") if not erro else None
        if erro or (dados or {}).get("schema") != POL_SCHEMA or not isinstance(autonomia, dict):
            achados.append(_c("workspace policy", "fail", f"policy.yaml {erro or 'sem schema ou autonomia válidos'}",
                              "rode `simplicio-video setup --force` para regravar a política"))
        else:
            achados.append(_c("workspace policy", "ok", f"autonomia {autonomia.get('default')}"))
    return achados


def relatorio() -> dict:
    checks = [
        _checa_python(),
        _checa_node(),
        *_checa_ffmpeg(),
        _checa_disco(),
        _checa_portas(),
        *_checa_credenciais(),
        *_checa_workspace(),
    ]
    return {"ok": not any(c["status"] == "fail" for c in checks), "checks": checks}


def _texto(rel: dict) -> str:
    linhas = [f"simplicio-video doctor ({__version__})"]
    for c in rel["checks"]:
        linhas.append(f"  [{ROTULO[c['status']]:<5}] {c['name']}: {c['detail']}")
        if c["status"] != "ok" and c["fix"]:
            linhas.append(f"           correção: {c['fix']}")
    if rel["ok"]:
        linhas.append("ok: nenhuma falha")
    else:
        n = sum(1 for c in rel["checks"] if c["status"] == "fail")
        linhas.append(f"falhou: {n} checagem(ns). Corrija as correções acima e rode o doctor de novo.")
    return "\n".join(linhas)


def run(a) -> int:
    rel = relatorio()
    print(json.dumps(rel, indent=2, ensure_ascii=False) if a.json else _texto(rel))
    return 0 if rel["ok"] else 1
