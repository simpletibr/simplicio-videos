"""Comandos do quadro (#86, épico #81): handler de src/simplicio_factory/plugins/board/plugin.json.

    simplicio-video board list [--json]                                  colunas e cartões
    simplicio-video board comment ITEM "texto" --by NOME                 comentário append-only
    simplicio-video board review ITEM approve|changes --by NOME [--note]  revisão humana
    simplicio-video board build [--out ARQUIVO]                          quadro em HTML estático (#88)
    simplicio-video board serve [--port N]                               servidor local em 127.0.0.1 com token (#89)

Estado: $SIMPLICIO_FACTORY_HOME (padrão .simplicio-factory/). As colunas são derivadas; o quadro não move cartão de etapa.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from simplicio_factory.plugins.board import html as quadro_html
from simplicio_factory.plugins.board import serve as servidor
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
EXEMPLO_BUILD = """Exemplo:
  simplicio-video board build
  simplicio-video board build --out quadro/board.html
"""
EXEMPLO_SERVE = """Exemplo:
  simplicio-video board serve
  simplicio-video board serve --port 9000
"""


def _home() -> Path:
    return Path(os.environ.get("SIMPLICIO_FACTORY_HOME") or ".simplicio-factory")


def _erro(mensagem: str) -> int:
    print(f"erro: {mensagem}", file=sys.stderr)
    return 1


def _porta(valor: str) -> int:
    try:
        porta = int(valor)
    except ValueError:
        raise argparse.ArgumentTypeError(f"porta inválida: {valor!r} (use um número de 0 a 65535)") from None
    if not 0 <= porta <= 65535:
        raise argparse.ArgumentTypeError(f"porta fora da faixa: {porta} (use de 0 a 65535; 0 escolhe uma livre)")
    return porta


def _host_local(valor: str) -> str:
    try:
        return servidor.checa_host(valor)
    except BoardError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from None


def _sobe(args, home: Path) -> int:
    """Liga o servidor, imprime a URL com o token e atende até Ctrl+C."""
    try:
        srv = servidor.criar(home, args.host, args.port)
    except BoardError as exc:
        return _erro(str(exc))
    except OSError as exc:
        return _erro(f"não foi possível escutar em {args.host}:{args.port}: {exc}")
    porta = srv.server_address[1]
    print(f"Quadro em http://127.0.0.1:{porta}/ (Ctrl+C para parar)", flush=True)
    print(f"Token desta sessão: {srv.token}", flush=True)
    print(f"Abra no navegador: http://127.0.0.1:{porta}/?token={srv.token}", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("servidor parado", flush=True)
    finally:
        srv.server_close()
    return 0


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
    acoes = parser.add_subparsers(dest="acao", metavar="{list,comment,review,build,serve}")

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

    constroi = _subparser(
        acoes,
        "build",
        "grava o quadro em um HTML estático",
        "Grava um arquivo HTML autocontido (CSS e JS inline, sem rede) com uma coluna por etapa e um cartão por item. "
        "Só leitura: o navegador não escreve comentário nem move cartão.",
        EXEMPLO_BUILD,
    )
    constroi.add_argument(
        "--out", default="board.html", metavar="ARQUIVO", help="arquivo HTML de saída (padrão: board.html)"
    )

    sobe = _subparser(
        acoes,
        "serve",
        "sobe o quadro num servidor local (127.0.0.1) com token",
        "Serve a mesma página do build, com formulário para comentar e botões para aprovar ou pedir alterações. "
        "Escuta só em 127.0.0.1: o token impresso no terminal vale só nesta sessão. Aprovar gasto não passa pelo "
        "navegador: continua no comando generate approve, no terminal.",
        EXEMPLO_SERVE,
    )
    sobe.add_argument(
        "--port",
        type=_porta,
        default=servidor.PORTA_PADRAO,
        metavar="N",
        help="porta (padrão: 8765; 0 escolhe uma livre)",
    )
    sobe.add_argument(
        "--host",
        type=_host_local,
        default=servidor.HOST,
        metavar="HOST",
        help="só 127.0.0.1 ou localhost; qualquer outro endereço é recusado",
    )

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
        if args.acao == "build":
            destino = Path(args.out)
            try:
                destino.parent.mkdir(parents=True, exist_ok=True)
                destino.write_bytes(quadro_html.construir(home, destino.resolve().parent).encode("utf-8"))
            except OSError as exc:
                return _erro(f"não foi possível gravar {destino}: {exc}")
            print(f"{destino}: quadro gravado")
            return 0
        if args.acao == "serve":
            return _sobe(args, home)
        if args.acao == "comment":
            linha = service.comentar(home, args.item, args.texto, args.by)
            print(f"{args.item}: comentário {linha['id']} registrado")
            return 0
        linha = service.revisar(home, args.item, args.decisao, args.by, args.note)
        print(f"{args.item}: revisão {args.decisao} registrada por {linha['by']}")
        return 0
    except BoardError as exc:
        return _erro(str(exc))
