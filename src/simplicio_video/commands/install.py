"""`simplicio-video install [--check] [--python X] [--with extras]` (issue #43): ambiente idempotente do checkout.

Cria <checkout>/.venv com Python X (uv venv), instala o pacote em modo editável com os extras (uv pip install -e)
e grava .venv/simplicio-install.json com o que foi instalado. Se Python, extras e pyproject.toml não mudaram desde
o último registro, não chama o uv. --check mostra o plano e sai com 1 se houver mudança pendente. O install.sh
chama este comando, e o update chama de novo depois do git pull. Não usa sudo e só escreve dentro do checkout.

Exemplos:
  simplicio-video install --check
  simplicio-video install
  simplicio-video install --python 3.12 --with server,publish
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

from .. import paths

PYTHON_PADRAO = "3.12"
REGISTRO = "simplicio-install.json"
EXTRA_RE = re.compile(r"^[a-z][a-z0-9-]*$")
PY_RE = re.compile(r"^3\.\d+$")


class InstallError(Exception):
    pass


def parse_extras(texto: str | None) -> list[str] | None:
    """'server, publish' -> ['server', 'publish']. None quando o usuário não passou --with."""
    if texto is None:
        return None
    itens = [x.strip() for x in texto.split(",") if x.strip()]
    for item in itens:
        if not EXTRA_RE.match(item):
            raise InstallError(f"extra inválido {item!r}: use nomes como server,publish")
    return list(dict.fromkeys(itens))


def _alvo(extras: list[str]) -> str:
    return ".[" + ",".join(extras) + "]" if extras else "."


def _sha(caminho: Path) -> str | None:
    return hashlib.sha256(caminho.read_bytes()).hexdigest() if caminho.is_file() else None


def _registro(venv: Path) -> dict | None:
    try:
        dados = json.loads((venv / REGISTRO).read_text(encoding="utf8"))
    except (OSError, ValueError):
        return None
    return dados if isinstance(dados, dict) else None


def _versao_do_venv(venv: Path) -> str | None:
    try:
        texto = (venv / "pyvenv.cfg").read_text(encoding="utf8")
    except OSError:
        return None
    m = re.search(r"^version(?:_info)?\s*=\s*(\d+\.\d+)", texto, re.M)
    return m.group(1) if m else None


def plano(home: Path, python: str, extras: list[str]) -> tuple[list[str], str | None]:
    """(passos pendentes, conflito). Conflito: o .venv existe com outro Python. Nada é trocado sozinho."""
    venv = home / ".venv"
    pendentes: list[str] = []
    conflito = None
    if not venv.is_dir():
        pendentes.append(f"criar .venv com Python {python}: uv venv --python {python} .venv")
    else:
        atual = _versao_do_venv(venv)
        if atual != python:
            conflito = (f".venv usa Python {atual or 'desconhecido'} e o pedido é {python}: "
                        "apague .venv (rm -rf .venv) e rode de novo")
    reg = _registro(venv)
    if reg is None or reg.get("python") != python or reg.get("extras") != extras \
            or reg.get("pyproject_sha256") != _sha(home / "pyproject.toml"):
        pendentes.append(f"instalar o pacote e os extras ({', '.join(extras) or 'nenhum'}): "
                         f"uv pip install -e {_alvo(extras)}")
    return pendentes, conflito


def _executa(argv: list[str], cwd: Path) -> None:
    r = subprocess.run(argv, cwd=str(cwd))
    if r.returncode != 0:
        raise InstallError(f"comando falhou (rc {r.returncode}): {' '.join(argv)}")


def run(a) -> int:
    home = paths.home()
    try:
        pedidos = parse_extras(a.extras)
        reg = _registro(home / ".venv") or {}
        python = a.python or reg.get("python") or PYTHON_PADRAO
        if not PY_RE.match(python):
            raise InstallError(f"versão de Python inválida {python!r}: use algo como 3.12")
        extras = pedidos if pedidos is not None else list(reg.get("extras") or [])
    except InstallError as e:
        print(f"install: {e}", file=sys.stderr)
        return 2

    pendentes, conflito = plano(home, python, extras)
    print(f"simplicio-video install (checkout: {home})")
    print(f"  Python: {python} · extras: {', '.join(extras) or 'nenhum'}")
    if conflito:
        print(f"  conflito: {conflito}")
    for passo in pendentes:
        print(f"  pendente: {passo}")

    if a.check:
        if conflito or pendentes:
            print("  --check: há mudanças pendentes. Rode `simplicio-video install` para aplicar.")
            return 1
        print("  --check: nada a mudar")
        return 0
    if conflito:
        print(f"install: {conflito}", file=sys.stderr)
        return 1
    if not pendentes:
        print("nada a mudar: o ambiente já está em dia. Próximo passo: simplicio-video doctor")
        return 0

    uv = shutil.which("uv")
    if not uv:
        print("install: uv não encontrado. O install.sh oferece instalar; ou veja https://docs.astral.sh/uv/",
              file=sys.stderr)
        return 1
    venv = home / ".venv"
    try:
        if not venv.is_dir():
            _executa([uv, "venv", "--python", python, ".venv"], home)
        _executa([uv, "pip", "install", "--python", str(venv / "bin" / "python"), "-e", _alvo(extras)], home)
    except InstallError as e:
        print(f"install: {e}", file=sys.stderr)
        return 1
    if not venv.is_dir():
        print(f"install: o uv não criou {venv}", file=sys.stderr)
        return 1
    registro = {"python": python, "extras": extras, "pyproject_sha256": _sha(home / "pyproject.toml")}
    (venv / REGISTRO).write_text(json.dumps(registro, indent=2, ensure_ascii=False) + "\n", encoding="utf8")
    print(f"ok: ambiente instalado em {venv}. Próximo passo: simplicio-video doctor")
    return 0
