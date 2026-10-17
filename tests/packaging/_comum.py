"""Helpers dos testes do pacote de operação (issue #43): install, update, doctor, setup, install.sh e Docker.

Tudo roda em tmp_path com HOME, SIMPLICIO_WORKSPACE e checkout temporários. Nenhum teste escreve em ~,
no .venv real do repo ou abre socket (pytest-socket). Ferramentas externas (ffmpeg, node) são sempre fakes.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def executa(argv, capsys, main):
    """Roda main(argv) em processo e devolve (rc, stdout, stderr). SystemExit (argparse, --help) vira rc."""
    try:
        rc = main(argv)
    except SystemExit as e:
        rc = e.code if isinstance(e.code, int) else 1
    captured = capsys.readouterr()
    return rc, captured.out, captured.err


def erros_de_schema(nome: str, dados) -> list[str]:
    """Why `dados` does not fit the packaged schema data/schemas/cli/<nome>.schema.json ([] means it fits)."""
    import json

    from jsonschema import Draft202012Validator

    arquivo = ROOT / "src" / "simplicio_video" / "data" / "schemas" / "cli" / f"{nome}.schema.json"
    esquema = json.loads(arquivo.read_text(encoding="utf8"))
    return [e.message for e in Draft202012Validator(esquema).iter_errors(dados)]


def exige_registrado(nome: str, capsys, main) -> None:
    """Falha com motivo claro se o subcomando não existe no CLI (argparse daria rc 2 e uma mensagem confusa)."""
    rc, out, err = executa([nome, "--help"], capsys, main)
    assert rc == 0, f"`{nome}` não está registrado no CLI (cli.py): {err.strip()[:200]}"


def instantanea(pasta: Path) -> list[str]:
    """Lista ordenada de tudo que existe dentro de `pasta` (para provar que nada foi criado ou alterado)."""
    return sorted(str(p.relative_to(pasta)) for p in pasta.rglob("*"))
