"""Comandos do quadro (#86, épico #81): handler de src/simplicio_factory/plugins/board/plugin.json.

    simplicio-video board list [--json]                                  colunas e cartões
    simplicio-video board comment ITEM "texto" --by NOME                 comentário append-only
    simplicio-video board review ITEM approve|changes --by NOME [--note]  revisão humana

Estado: $SIMPLICIO_FACTORY_HOME (padrão .simplicio-factory/). As colunas são derivadas; o quadro não move cartão de etapa.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from simplicio_factory.plugins.board import service
from simplicio_factory.plugins.board.service import BoardError

EXEMPLO_BOARD = """Exemplo:
  simplicio-video board list
  simplicio-video board comment itm_01HZEXEMPLO0000000000001 "Gancho fraco" --by Ana
  simplicio-video board review itm_01HZEXEMPLO0000000000001 approve --by Ana --note "pode publicar"
"""
EXEMPLO_LIST = """Exemplo:
  simplicio-video board list
  simplicio-video board list --json > quadro.json
"""
EXEMPLO_COMMENT = """Exemplo:
  simplicio-video board comment itm_01HZEXEMPLO0000000000001 "Trocar a cor do logo" --by Bruno
"""
EXEMPLO_REVIEW = """Exemplo:
  simplicio-video board review itm_01HZEXEMPLO0000000000001 approve --by Ana
  simplicio-video board review itm_01HZEXEMPLO0000000000001 changes --by Ana --note "refazer o final"
"""


def _home() -> Path:
    return Path(os.environ.get("SIMPLICIO_FACTORY_HOME") or ".simplicio-factory")


def _erro(mensagem: str) -> int:
    print(f"erro: {mensagem}", file=sys.stderr)
    return 1


def _subparser(acoes, nome: str, ajuda: str, descricao: str, exemplo: str):
    return acoes.add_parser(
        nome,
        prog=f"simplicio-video board {nome}",
        help=ajuda,
        description=descricao,
        epilog=exemplo,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )


def _imprime_texto(quadro: dict) -> None:
    for coluna in quadro["columns"]:
        cartoes = coluna["cards"]
        print(f"{coluna['title']} ({len(cartoes)})")
        if not cartoes:
            print("  (vazia)")
        for c in cartoes:
            revisao = f"  review={c['review']}" if c["review"] else ""
            print(f"  {c['id']}  {c['brand']}  [{c['state']}]  rota={c['route']}  comentários={c['comments']}{revisao}")


def board_cmd(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="simplicio-video board",
        description="Quadro kanban dos itens: colunas derivadas de state e review; comentários e revisão humana.",
        epilog=EXEMPLO_BOARD,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    acoes = parser.add_subparsers(dest="acao", metavar="{list,comment,review}")

    lista = _subparser(
        acoes,
        "list",
        "mostra as colunas e os cartões",
        "Mostra as oito colunas, na ordem do quadro, com os cartões de cada uma.",
        EXEMPLO_LIST,
    )
    lista.add_argument("--json", action="store_true", help="imprime o quadro em JSON (schema simplicio.board/v1)")

    comenta = _subparser(
        acoes,
        "comment",
        "grava um comentário no item",
        "Acrescenta um comentário ao item. O arquivo de comentários só recebe linhas novas.",
        EXEMPLO_COMMENT,
    )
    comenta.add_argument("item", help="id do item (itm_...)")
    comenta.add_argument("texto", help="texto do comentário")
    comenta.add_argument("--by", required=True, metavar="NOME", help="quem escreve (obrigatório)")

    revisa = _subparser(
        acoes,
        "review",
        "aprova ou pede alterações num item renderizado",
        "approve leva o cartão de Revisão para Pronto; changes mantém em Revisão.",
        EXEMPLO_REVIEW,
    )
    revisa.add_argument("item", help="id do item (itm_...), em estado rendered")
    revisa.add_argument("decisao", choices=["approve", "changes"], help="approve ou changes")
    revisa.add_argument("--by", required=True, metavar="NOME", help="quem revisa (obrigatório)")
    revisa.add_argument("--note", metavar="TEXTO", help="texto da revisão (padrão: aprovado ou alterações solicitadas)")

    args = parser.parse_args(argv)
    if args.acao is None:
        parser.print_help()
        return 2

    home = _home()
    try:
        if args.acao == "list":
            quadro = service.listar(home)
            if args.json:
                print(json.dumps(quadro, ensure_ascii=False, indent=2))
            else:
                _imprime_texto(quadro)
            return 0
        if args.acao == "comment":
            linha = service.comentar(home, args.item, args.texto, args.by)
            print(f"{args.item}: comentário {linha['id']} registrado")
            return 0
        linha = service.revisar(home, args.item, args.decisao, args.by, args.note)
        print(f"{args.item}: revisão {args.decisao} registrada por {linha['by']}")
        return 0
    except BoardError as exc:
        return _erro(str(exc))
