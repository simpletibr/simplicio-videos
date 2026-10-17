"""`simplicio-video install [--check] [--dry-run] [--json] [--python X] [--with extras]`: the checkout environment.

Creates <checkout>/.venv with Python X (uv venv), installs the package in editable mode with the extras (uv pip install -e) and
writes .venv/simplicio-install.json with what was installed. If Python, extras and pyproject.toml did not change since the last
record, it does not call uv. It does NOT copy skills into an agent host (the simplicio-loop `install` does that). No sudo; it
writes only inside the checkout. The install.sh calls this command, and the update calls it again after the git pull.

An installed package (pip) has no checkout and no .venv to create: `--check` and `--dry-run` say so and exit 0, a real install
exits 2, and nothing is ever created inside site-packages.

Exit codes (as the loop): `--check` 0 up to date, 10 something pending; `--dry-run` 0 (it writes nothing); 1 a failed install or a
.venv with another Python; 2 an invalid argument, or a pip-installed package. With --json, stdout is ONE
`simplicio.video-install/v1` document and every message goes to stderr; an error also prints a document (the same keys the
install already knew, plus `error`), so a program reading stdout never has to guess.

Standard library only, and so is everything it imports at the top: `./install.sh` runs this under the SYSTEM python, before the
`.venv` exists, and that python has no PyYAML (macOS with the Xcode tools, a minimal Debian). Do not import `setup` here.

Exemplos:
  simplicio-video install --check
  simplicio-video install --dry-run --json
  simplicio-video install --python 3.12 --with local-tts
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

from .. import __version__, distribution, hostos, paths

PYTHON_PADRAO = "3.12"
REGISTRO = "simplicio-install.json"
SCHEMA = "simplicio.video-install/v1"
EXIT_PENDING = 10
EXTRA_RE = re.compile(r"^[a-z][a-z0-9-]*$")
PY_RE = re.compile(r"^3\.\d+$")
PIP_MESSAGE = "instalado por pip: não há .venv a criar; use pip install --upgrade simplicio-video"


class InstallError(Exception):
    pass


def parse_extras(texto: str | None) -> list[str] | None:
    """'local-tts, mcp' -> ['local-tts', 'mcp']. None when the user did not pass --with."""
    if texto is None:
        return None
    itens = [x.strip() for x in texto.split(",") if x.strip()]
    for item in itens:
        if not EXTRA_RE.match(item):
            raise InstallError(f"extra inválido {item!r}: use nomes como local-tts,mcp")
    return list(dict.fromkeys(itens))


def _alvo(extras: list[str]) -> str:
    return ".[" + ",".join(extras) + "]" if extras else "."


def _sha(caminho: Path) -> str | None:
    try:
        return hashlib.sha256(caminho.read_bytes()).hexdigest() if hostos.is_file(caminho) else None
    except OSError:  # a file that cannot be read counts as a file that is not there: the plan says to install
        return None


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
    """(pending steps, conflict). Conflict: the .venv exists with another Python. Nothing is replaced on its own."""
    venv = home / ".venv"
    pendentes: list[str] = []
    conflito = None
    if not hostos.is_dir(venv):
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


def _doc(python: str, extras: list[str], pendentes: list[str], conflito: str | None, kind: str) -> dict:
    return {"schema": SCHEMA, "version": __version__, "up_to_date": not pendentes and not conflito, "pending": pendentes,
            "conflict": conflito, "python": python, "extras": extras, "distribution": kind}


def _executa(argv: list[str], cwd: Path, para_stderr: bool) -> None:
    # --json: whatever uv prints goes to stderr (fd 2), so that stdout stays one JSON document
    r = subprocess.run(argv, cwd=str(cwd), stdout=2 if para_stderr else None)
    if r.returncode != 0:
        raise InstallError(f"comando falhou (código {r.returncode}): {' '.join(argv)}")


def _erro(a, mensagem: str, codigo: int, kind: str, **campos) -> int:
    """The message on stderr and, with --json, ONE document on stdout: `error` plus whatever the install already knew."""
    print(f"install: {mensagem}", file=sys.stderr)
    if a.json:
        hostos.say(json.dumps({"schema": SCHEMA, "version": __version__, "distribution": kind, "error": mensagem, **campos},
                              sort_keys=True))
    return codigo


def _run_pip(a) -> int:
    """A package installed by pip: no checkout, no .venv. Never touch site-packages."""
    python = f"{sys.version_info.major}.{sys.version_info.minor}"
    if not (a.check or a.dry_run):
        return _erro(a, PIP_MESSAGE, 2, distribution.PIP, python=python, extras=[], pending=[], conflict=None, up_to_date=False)
    if a.json:
        print(f"install: {PIP_MESSAGE}", file=sys.stderr)
        hostos.say(json.dumps(_doc(python, [], [], None, distribution.PIP), sort_keys=True))
    else:
        hostos.say(f"simplicio-video install\n  {PIP_MESSAGE}")
    return 0


def run(a) -> int:
    kind = distribution.kind()
    if kind == distribution.PIP:
        return _run_pip(a)
    home = paths.home()
    try:
        pedidos = parse_extras(a.extras)
        reg = _registro(home / ".venv") or {}
        python = a.python or reg.get("python") or PYTHON_PADRAO
        if not PY_RE.match(python):
            raise InstallError(f"versão de Python inválida {python!r}: use algo como 3.12")
        extras = pedidos if pedidos is not None else list(reg.get("extras") or [])
    except InstallError as e:
        return _erro(a, str(e), 2, kind)

    def say(texto: str) -> None:
        if a.json:
            print(texto, file=sys.stderr)
        else:
            hostos.say(texto)

    pendentes, conflito = plano(home, python, extras)
    say(f"simplicio-video install (checkout: {home})")
    say(f"  Python: {python} · extras: {', '.join(extras) or 'nenhum'}")
    if conflito:
        say(f"  conflito: {conflito}")
    for passo in pendentes:
        say(f"  pendente: {passo}")

    def emite(doc: dict) -> None:
        if a.json:
            hostos.say(json.dumps(doc, sort_keys=True))

    def falha(mensagem: str) -> int:  # a failure of the real install: the plan that was known, plus `error`
        return _erro(a, mensagem, 1, kind, python=python, extras=extras, pending=pendentes, conflict=conflito, up_to_date=False)

    if a.check:
        emite(_doc(python, extras, pendentes, conflito, kind))
        if conflito or pendentes:
            say("  --check: há mudanças pendentes. Rode `simplicio-video install` para aplicar.")
            return EXIT_PENDING
        say("  --check: nada a mudar")
        return 0
    if a.dry_run:
        emite(_doc(python, extras, pendentes, conflito, kind))
        say("  dry-run: nada foi criado nem alterado.")
        return 0
    if conflito:
        return falha(f"conflito: {conflito}")
    proximo = "simplicio-video doctor" + ("" if hostos.is_file(paths.workspace_dir() / "workspace.yaml")
                                          else " e, depois, simplicio-video setup")
    if not pendentes:
        say(f"nada a mudar: o ambiente já está em dia. Próximo passo: {proximo}")
        emite(_doc(python, extras, [], None, kind))
        return 0

    uv = hostos.find_uv()
    if not uv:
        return falha("uv não encontrado. O install.sh oferece instalar; ou instale com:\n"
                     f"  {hostos.hint('uv')}\n(veja https://docs.astral.sh/uv/)")
    venv = home / ".venv"
    try:
        if not hostos.is_dir(venv):
            _executa([uv, "venv", "--python", python, ".venv"], home, a.json)
        _executa([uv, "pip", "install", "--python", str(hostos.venv_python(venv)), "-e", _alvo(extras)], home, a.json)
    except InstallError as e:
        return falha(str(e))
    if not hostos.is_dir(venv):
        return falha(f"o uv não criou {venv}")
    registro = {"python": python, "extras": extras, "pyproject_sha256": _sha(home / "pyproject.toml")}
    (venv / REGISTRO).write_text(json.dumps(registro, indent=2, ensure_ascii=False) + "\n", encoding="utf8")
    say(f"ok: ambiente instalado em {venv}. Próximo passo: {proximo}")
    emite(_doc(python, extras, [], None, kind))
    return 0
