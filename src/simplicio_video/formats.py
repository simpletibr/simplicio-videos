"""Formatos de anúncio: a biblioteca de 50 exemplos (pasta "Swipe File - 50 Formatos", no Drive) e a montagem do pedido
para adaptar uma copy a um formato.

O CLI não chama modelo nenhum: monta o pedido, e quem adapta é o LLM que o recebe. O repositório guarda os links e a
descrição estrutural; os arquivos de exemplo ficam no Drive.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import paths

OBJETIVOS = ("clique", "lead", "venda", "engajamento")


class FormatError(Exception):
    pass


def _doc(data: Path | None = None) -> dict:
    base = data or paths.data_dir()
    return json.loads((base / "formats" / "formats.json").read_text(encoding="utf8"))


def formatos(objetivo: str | None = None, data: Path | None = None) -> list[dict]:
    return [f for f in _doc(data)["formatos"] if objetivo is None or f["objetivo"] == objetivo]


def formato(id_: str, data: Path | None = None) -> dict:
    for f in _doc(data)["formatos"]:
        if f["id"] == id_:
            return f
    raise FormatError(f"formato desconhecido: {id_} (use `simplicio-video formats list`)")


def instrucoes(data: Path | None = None) -> str:
    base = data or paths.data_dir()
    return (base / "formats" / "instrucoes.md").read_text(encoding="utf8").strip()


def pedido(id_: str, copia: str, data: Path | None = None) -> str:
    """O pedido completo: as instruções, a copy e o formato. Copy vazia é erro, não um pedido sem texto."""
    copia = (copia or "").strip()
    if not copia:
        raise FormatError("copia vazia: passe o texto com --copia <arquivo> ou --copia -")
    f = formato(id_, data)
    bloco = (
        f"Agora adapte a copy abaixo:\n\n{copia}\n\n"
        f"Para o formato {f['nome']} que consiste em {f['descricao']}\n\n"
        f"Estrutura do formato: {' > '.join(f['estrutura'])}.\n"
        f"Limites: {f['limites']}.\n"
        f"Objetivo do formato: {f['objetivo']}.\n\n"
        "Lembre-se: mantenha a mensagem central, a promessa e o mecanismo da copy original; ajuste estrutura, "
        "ordem, linguagem e ritmo ao formato; use linguagem clara e orientada à ação; priorize clareza, impacto e "
        "conversão; condense ou expanda trechos quando o formato pedir."
    )
    return instrucoes(data) + "\n\n---\n\n" + bloco


def run_formats(args: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="simplicio-video formats")
    sub = ap.add_subparsers(dest="acao", required=True)
    pl = sub.add_parser("list", help="lista os 50 formatos (ou os de um objetivo)")
    pl.add_argument("--objetivo", choices=OBJETIVOS)
    pl.add_argument("--json", action="store_true")
    ps = sub.add_parser("show", help="mostra um formato, com o link da pasta e o nome do arquivo de exemplo")
    ps.add_argument("id")
    ps.add_argument("--json", action="store_true")
    pp = sub.add_parser("prompt", help="monta o pedido para adaptar uma copy ao formato (não chama modelo)")
    pp.add_argument("id")
    pp.add_argument("--copia", required=True, help="arquivo com a copy, ou - para ler da entrada padrão")
    a = ap.parse_args(args)

    if a.acao == "list":
        rows = formatos(a.objetivo)
        if a.json:
            print(json.dumps(rows, indent=2, ensure_ascii=False))
        else:
            for r in rows:
                print(f"{r['id']:24s} {r['objetivo']:12s} {r['nome']}")
        return 0
    if a.acao == "show":
        f = formato(a.id)
        if a.json:
            print(json.dumps(f, indent=2, ensure_ascii=False))
        else:
            print(f"{f['nome']} ({f['objetivo']})\n{f['descricao']}\nestrutura: {' > '.join(f['estrutura'])}\n"
                  f"limites: {f['limites']}\nexemplo: {f['exemplo']['arquivo']} em {f['exemplo']['pasta']}")
        return 0
    if a.copia == "-":
        copia = sys.stdin.read()
    else:
        p = Path(a.copia)
        if not p.is_file():
            raise FormatError(f"arquivo não encontrado: {a.copia}")
        copia = p.read_text(encoding="utf8")
    print(pedido(a.id, copia))
    return 0
