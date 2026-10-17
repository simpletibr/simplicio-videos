#!/usr/bin/env python3
"""Fumaça multiplataforma do simplicio-video: roda os comandos de operação num ambiente isolado e imprime uma tabela.

Para rodar de verdade em Windows e macOS (Python 3.10 ou superior; só a biblioteca padrão no topo do script). O script
roda o CLI com HOME, USERPROFILE, PATH e as pastas de dados dentro de uma pasta temporária: nunca toca no ~ real e nunca
dispara um login de verdade, porque o PATH do filho não tem `simplicio`. Sem rede (SIMPLICIO_OFFLINE=1). HOME e USERPROFILE
apontam para pastas DIFERENTES de propósito: o Runtime lê o login de HOME e só depois de USERPROFILE (em todo sistema), e com
as duas iguais um erro de ordem passaria sem ninguém ver.

Comandos (exit esperado entre parênteses): --version (0), doctor --json (0 ou 1), install --check num alvo temporário (10: a skill está
pendente), install --dry-run --json (0), install --verify (0), install de verdade no alvo temporário (0), install --check --json
(0: em dia), install --uninstall (0: o alvo volta a ficar vazio), update --dry-run (1 sem rede num pacote, 2 num checkout, que recusa),
auth status --json (1, login_missing), login --json (1, UNVERIFIED), logout (2, REFUSED), logout --yes --json (0, NO_LOGIN). O alvo
do install é uma pasta da própria pasta temporária (`alvo`): nunca `--global`, nunca o ~ real. Cada JSON é validado contra o schema
empacotado (src/simplicio_video/data/schemas/cli/). Sai com 0 se tudo bateu e com 1 se algo falhou.

Windows e macOS reais continuam UNVERIFIED até alguém rodar este script lá e colar a tabela (docs/how-to/testar-em-windows-e-macos.md).

Exemplos:
  python scripts/smoke_so.py
  python scripts/smoke_so.py --manter
  python scripts/smoke_so.py --pasta C:\\Temp\\fumaca-simplicio
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parent.parent
TIMEOUT_S = 180
# Windows needs these to start Python at all; nothing else of the real environment reaches the child.
PASSA_DO_AMBIENTE = ("SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT")
PASTAS = ("home", "profile", "bin", "tmp", "data", "workspace", "checkout", "alvo")  # `profile` is USERPROFILE, `home` is HOME, `alvo` the install target


@dataclass
class Passo:
    argv: list  # `{alvo}` is the `alvo` folder of the temporary base (see resolve_argv)
    esperado: set
    schema: Optional[str] = None  # a packaged schema in data/schemas/cli/ (`doctor` -> doctor.schema.json)
    status: Optional[str] = None  # the expected value of the JSON key `status`
    reason: Optional[str] = None  # the expected value of the JSON key `reason_code`


@dataclass
class Resultado:
    passo: Passo
    obtido: Optional[int]
    ok: bool
    motivo: str = ""
    saida: str = field(default="", repr=False)


PASSOS = [
    Passo(["--version"], {0}),
    Passo(["doctor", "--json"], {0, 1}, schema="doctor"),
    Passo(["install", "--check", "--target", "{alvo}"], {10}),
    Passo(["install", "--dry-run", "--json", "--target", "{alvo}"], {0}, schema="install-plan", status="dry_run"),
    Passo(["install", "--verify", "--target", "{alvo}"], {0}),
    Passo(["install", "--target", "{alvo}"], {0}),
    Passo(["install", "--check", "--json", "--target", "{alvo}"], {0}, schema="install-plan", status="dry_run"),
    Passo(["install", "--uninstall", "--target", "{alvo}"], {0}),
    Passo(["update", "--dry-run"], {1, 2}),
    Passo(["auth", "status", "--json"], {1}, schema="auth-status", reason="login_missing"),
    Passo(["login", "--json"], {1}, schema="login", status="UNVERIFIED"),
    Passo(["logout"], {2}),
    Passo(["logout", "--yes", "--json"], {0}, schema="logout", status="NO_LOGIN"),
]


def resolve_argv(passo: Passo, base: Path) -> list:
    """The argv of a step with `{alvo}` replaced by the `alvo` folder of the temporary base."""
    return [arg.replace("{alvo}", str(Path(base) / "alvo")) for arg in passo.argv]


def build_env(base: Path, environ: Optional[dict] = None) -> dict:
    """The child environment: everything under `base`, an empty PATH folder (no `simplicio`, no git, no node), no credential."""
    base = Path(base)
    real = dict(os.environ if environ is None else environ)
    home = base / "home"
    env = {
        # DIFFERENT folders: the Runtime (and this CLI) read HOME first on every system, and USERPROFILE only without HOME
        "HOME": str(home), "USERPROFILE": str(base / "profile"),
        "APPDATA": str(home / "AppData" / "Roaming"), "LOCALAPPDATA": str(home / "AppData" / "Local"),
        "TMP": str(base / "tmp"), "TEMP": str(base / "tmp"), "TMPDIR": str(base / "tmp"),
        "PATH": str(base / "bin"),
        "SIMPLICIO_OFFLINE": "1",
        "SIMPLICIO_VIDEO_DATA": str(base / "data"), "SIMPLICIO_WORKSPACE": str(base / "workspace"),
        "SIMPLICIO_VIDEO_HOME": str(base / "checkout"),  # an empty folder: never the real checkout, never a real git remote
        "PYTHONIOENCODING": "utf-8", "PYTHONDONTWRITEBYTECODE": "1",
    }
    for nome in PASSA_DO_AMBIENTE:
        if real.get(nome):
            env[nome] = real[nome]
    src = REPO / "src"
    if (src / "simplicio_video").is_dir():  # a plain checkout, not installed: the child finds the package anyway
        env["PYTHONPATH"] = str(src)
    return env


def preparar(base: Path) -> None:
    for nome in PASTAS:
        (Path(base) / nome).mkdir(parents=True, exist_ok=True)


def schema_dir() -> Optional[Path]:
    src = REPO / "src" / "simplicio_video" / "data" / "schemas" / "cli"
    if src.is_dir():
        return src
    if str(REPO / "src") not in sys.path:
        spec = importlib.util.find_spec("simplicio_video")  # finds the package without importing it
        if spec and spec.submodule_search_locations:
            return Path(list(spec.submodule_search_locations)[0]) / "data" / "schemas" / "cli"
    return None


def valida_schema(nome: str, documento: object) -> str:
    """'' when `documento` fits the packaged schema `nome`, else why not. jsonschema is a dependency of the package."""
    pasta = schema_dir()
    arquivo = pasta / f"{nome}.schema.json" if pasta else None
    if arquivo is None or not arquivo.is_file():
        return f"schema {nome}: arquivo não encontrado (o pacote está instalado?)"
    try:
        from jsonschema import Draft202012Validator
    except ImportError:
        return "schema: o módulo jsonschema não está instalado (o pacote o exige: python -m pip install -e .)"
    erros = [e.message for e in Draft202012Validator(json.loads(arquivo.read_text(encoding="utf-8"))).iter_errors(documento)]
    return f"schema {nome}: " + "; ".join(erros[:3]) if erros else ""


def executar_passo(passo: Passo, env: dict, base: Path) -> Resultado:
    try:
        # stdin is never the terminal: the end of a real `install` would start the interactive `setup` on it
        done = subprocess.run([sys.executable, "-m", "simplicio_video", *resolve_argv(passo, base)], cwd=str(base), env=env,
                              stdin=subprocess.DEVNULL, capture_output=True, text=True, encoding="utf-8", errors="replace",
                              timeout=TIMEOUT_S)
    except (OSError, subprocess.SubprocessError) as exc:
        return Resultado(passo, None, False, f"não consegui rodar: {exc}")
    saida = (done.stdout or "") + (done.stderr or "")
    problemas = []
    if done.returncode not in passo.esperado:
        problemas.append(f"exit {done.returncode} fora de {sorted(passo.esperado)}")
    if "Traceback" in saida:
        problemas.append("traceback na saída")
    if "access_token" in saida or "refresh_token" in saida:
        problemas.append("a saída cita um token")
    if passo.schema:
        try:
            documento = json.loads(done.stdout)
        except ValueError:
            problemas.append("o stdout não é um único documento JSON")
        else:
            motivo = valida_schema(passo.schema, documento)
            if motivo:
                problemas.append(motivo)
            if passo.status and documento.get("status") != passo.status:
                problemas.append(f"status {documento.get('status')!r}, esperado {passo.status!r}")
            if passo.reason and documento.get("reason_code") != passo.reason:
                problemas.append(f"reason_code {documento.get('reason_code')!r}, esperado {passo.reason!r}")
    return Resultado(passo, done.returncode, not problemas, "; ".join(problemas), saida)


def executar(passos: list, base: Path) -> list:
    preparar(base)
    env = build_env(base)
    return [executar_passo(passo, env, Path(base)) for passo in passos]


def _celula(texto: str) -> str:
    return texto.replace("|", "\\|").replace("\n", " ")


def tabela(resultados: list) -> str:
    so = f"{platform.system()} {platform.release()}".strip()
    py = platform.python_version()
    linhas = ["| SO | Python | Comando | Esperado | Obtido | Resultado |", "|---|---|---|---|---|---|"]
    for r in resultados:
        comando = "simplicio-video " + " ".join(r.passo.argv)
        esperado = " ou ".join(str(c) for c in sorted(r.passo.esperado))
        obtido = "-" if r.obtido is None else str(r.obtido)
        veredito = "ok" if r.ok else "falhou: " + r.motivo
        linhas.append("| " + " | ".join(_celula(c) for c in (so, py, f"`{comando}`", esperado, obtido, veredito)) + " |")
    return "\n".join(linhas)


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(
        prog="smoke_so.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pasta", metavar="DIR", help="pasta temporária isolada (padrão: uma nova no temp do sistema); "
                    "tem de não existir ou estar vazia")
    ap.add_argument("--manter", action="store_true", help="não apaga a pasta temporária no fim (para ver o que sobrou)")
    args = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")  # a cp1252 console must not crash the table

    criada_aqui = False
    if args.pasta:
        base = Path(args.pasta).resolve()
        if base.exists() and any(base.iterdir()):
            print(f"smoke_so: {base} já existe e não está vazia; escolha outra pasta.", file=sys.stderr)
            return 2
        criada_aqui = not base.exists()
        base.mkdir(parents=True, exist_ok=True)
    else:
        base = Path(tempfile.mkdtemp(prefix="simplicio-fumaca-")).resolve()
        criada_aqui = True

    try:
        print("# Fumaça multiplataforma do simplicio-video")
        print(f"- SO: {platform.platform()}")
        print(f"- Python: {platform.python_version()} ({sys.executable})")
        print(f"- Pasta temporária isolada (HOME, USERPROFILE e PATH, cada um numa pasta diferente): {base}")
        print()
        resultados = executar(PASSOS, base)
        print(tabela(resultados))
        falhas = [r for r in resultados if not r.ok]
        print()
        if falhas:
            print(f"falhou: {len(falhas)} de {len(resultados)} comando(s). Cole esta tabela na issue ou no PR.")
        else:
            print(f"ok: {len(resultados)} de {len(resultados)} comando(s) como esperado neste sistema.")
        return 1 if falhas else 0
    finally:
        if not args.manter and criada_aqui:
            shutil.rmtree(base, ignore_errors=True)
        elif not args.manter:
            for nome in PASTAS:
                shutil.rmtree(base / nome, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
