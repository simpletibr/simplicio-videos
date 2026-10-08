"""Comandos do media (#85 e #87, épico #81): gasto por item na rota ai_assisted e a mídia gerada que volta ao item.

    simplicio-video generate quote ITEM --provider real-oficial --estimate-ref REF --credits N [--daily-cap N]
    simplicio-video generate approve ITEM --by NOME [--yes] [--daily-cap N]
    simplicio-video generate start ITEM                  (approved -> generating; exige aprovação registrada)
    simplicio-video generate show ITEM [--json]
    simplicio-video media attach ITEM ARQUIVO --source real-oficial --media-id ID --prompt-file ARQ [--brand BRAND.JSON]

Estado: só `transition()` muda o item (drafted -> quoted -> approved -> generating -> generated). O passo `ai_media` de
`item.production["steps"]` guarda provider, estimate_ref, credits e, na aprovação, confirmed_by e confirmed_at.
Eventos no log do store: spend.quoted (na cotação), spend.approved (na aprovação) e media.attached (no attach).
Sem rede e sem LLM.

Quem pode aprovar: quem executa o comando com `--by` e confirma no terminal. O registro é auditoria, não prova
que `--by` é humano. O controle real do gasto é a confirmação do Real Oficial (`ro_confirm_spend`).

O attach copia o arquivo para <pasta do item no studio>/media/ e grava o recibo media.json (sha256, origem, media_id,
estimate_ref, credits, confirmed_by e sha256 do prompt; o texto do prompt não entra no recibo). O studio confere o
sha256 de novo no render.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from simplicio_factory.contracts.errors import InvalidTransition
from simplicio_factory.contracts.json_store import JsonStore
from simplicio_factory.contracts.models import DEFAULT_ROUTE
from simplicio_factory.contracts.transitions import transition
from simplicio_factory.plugins.media import attach, budget

PROVIDERS = ("real-oficial",)
ORIGENS = ("real-oficial",)
ROTA = "ai_assisted"
PASSO = "ai_media"
EVENTO_COTADO = "spend.quoted"
EVENTO_APROVADO = "spend.approved"
RESPOSTAS_SIM = ("s", "sim", "y", "yes")

EXEMPLO_GERAL = """Exemplo:
  simplicio-video generate quote itm_01HZEXEMPLO0000000000001 --provider real-oficial --estimate-ref est_01 --credits 120
  simplicio-video generate approve itm_01HZEXEMPLO0000000000001 --by "Wesley"
  simplicio-video generate start itm_01HZEXEMPLO0000000000001
  simplicio-video generate show itm_01HZEXEMPLO0000000000001
"""
EXEMPLO_START = """Exemplo:
  simplicio-video generate start itm_01HZEXEMPLO0000000000001
"""
EXEMPLO_MEDIA = """Exemplo:
  simplicio-video media attach itm_01HZEXEMPLO0000000000001 ~/Downloads/video.mp4 --source real-oficial --media-id med_01 --prompt-file prompt.txt
"""
EXEMPLO_ATTACH = """Exemplo:
  simplicio-video media attach itm_01HZEXEMPLO0000000000001 ~/Downloads/video.mp4 --source real-oficial --media-id med_01 --prompt-file prompt.txt
  simplicio-video media attach itm_01HZEXEMPLO0000000000001 ~/Downloads/video.mp4 --source real-oficial --media-id med_01 --prompt-file prompt.txt --brand brand.json
"""
EXEMPLO_QUOTE = """Exemplo:
  simplicio-video generate quote itm_01HZEXEMPLO0000000000001 --provider real-oficial --estimate-ref est_01 --credits 120
  simplicio-video generate quote itm_01HZEXEMPLO0000000000001 --provider real-oficial --estimate-ref est_01 --credits 120 --daily-cap 500
"""
EXEMPLO_APPROVE = """Exemplo:
  simplicio-video generate approve itm_01HZEXEMPLO0000000000001 --by "Wesley"
  simplicio-video generate approve itm_01HZEXEMPLO0000000000001 --by "Wesley" --yes
"""
EXEMPLO_SHOW = """Exemplo:
  simplicio-video generate show itm_01HZEXEMPLO0000000000001
  simplicio-video generate show itm_01HZEXEMPLO0000000000001 --json
"""


def _erro(mensagem: str) -> int:
    print(f"erro: {mensagem}", file=sys.stderr)
    return 1


def _positivo(texto: str) -> int:
    try:
        valor = int(texto)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"esperado um inteiro, recebeu {texto!r}"
        ) from exc
    if valor <= 0:
        raise argparse.ArgumentTypeError(
            f"esperado um inteiro maior que zero, recebeu {valor}"
        )
    return valor


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="simplicio-video generate",
        description="Orçamento e aprovação humana de geração por IA (rota ai_assisted). Cada gasto é cotado, "
        "depois aprovado por uma pessoa; o orçamento vem de budgets.media_credits do workspace.",
        epilog=EXEMPLO_GERAL,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    acoes = ap.add_subparsers(dest="acao", metavar="{quote,approve,start,show}")

    q = acoes.add_parser(
        "quote",
        prog="simplicio-video generate quote",
        help="registra o custo estimado do item (drafted -> quoted)",
        description="Registra o passo ai_media com o custo estimado e leva o item de drafted para quoted. "
        "Recusa se o item não estiver na rota ai_assisted, se o custo passar do orçamento ou do teto diário.",
        epilog=EXEMPLO_QUOTE,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    q.add_argument("item", help="id do item (itm_...)")
    q.add_argument(
        "--provider", required=True, choices=PROVIDERS, help="provedor da geração"
    )
    q.add_argument(
        "--estimate-ref",
        required=True,
        metavar="REF",
        help="referência da estimativa no provedor",
    )
    q.add_argument(
        "--credits",
        required=True,
        type=_positivo,
        metavar="N",
        help="créditos estimados (inteiro > 0)",
    )
    q.add_argument(
        "--daily-cap",
        type=_positivo,
        default=budget.DEFAULT_DAILY_CAP,
        metavar="N",
        help=f"teto diário de créditos aprovados (padrão {budget.DEFAULT_DAILY_CAP})",
    )

    a = acoes.add_parser(
        "approve",
        prog="simplicio-video generate approve",
        help="aprova o gasto cotado (quoted -> approved), com confirmação no terminal",
        description="Aprova o custo cotado. Pede confirmação no terminal; sem terminal, exige --yes. "
        "Aprovar de novo um item já aprovado não faz nada e não grava outro evento.",
        epilog=EXEMPLO_APPROVE,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    a.add_argument("item", help="id do item (itm_...)")
    a.add_argument(
        "--by",
        required=True,
        metavar="NOME",
        help="quem aprova (fica no passo e no evento)",
    )
    a.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="confirma sem perguntar (exigido sem terminal)",
    )
    a.add_argument(
        "--daily-cap",
        type=_positivo,
        default=budget.DEFAULT_DAILY_CAP,
        metavar="N",
        help=f"teto diário de créditos aprovados (padrão {budget.DEFAULT_DAILY_CAP})",
    )

    st = acoes.add_parser(
        "start",
        prog="simplicio-video generate start",
        help="inicia a geração (approved -> generating); exige aprovação registrada",
        description="Leva o item de approved para generating, depois da aprovação registrada por generate approve "
        "(passo ai_media com confirmed_by). Sem aprovação registrada, recusa e não muda nada. A geração em si "
        "é feita no Real Oficial, depois do ro_confirm_spend.",
        epilog=EXEMPLO_START,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    st.add_argument("item", help="id do item (itm_...)")

    s = acoes.add_parser(
        "show",
        prog="simplicio-video generate show",
        help="mostra o passo, o custo e quem aprovou",
        description="Mostra o último passo ai_media do item, o custo em créditos e quem aprovou e quando.",
        epilog=EXEMPLO_SHOW,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    s.add_argument("item", help="id do item (itm_...)")
    s.add_argument("--json", action="store_true", help="imprime o resultado em JSON")
    return ap


def _ultimo_passo_ai(item) -> dict | None:
    passos = [
        p
        for p in (item.production or {}).get("steps") or []
        if isinstance(p, dict) and p.get("kind") == PASSO
    ]
    return passos[-1] if passos else None


def _rota(item) -> str:
    return (item.production or {}).get("route", DEFAULT_ROUTE)


def generate_cmd(argv: list[str]) -> int:
    ap = _parser()
    if not argv:
        ap.print_help()
        return 2
    args = ap.parse_args(argv)
    if args.acao is None:
        ap.print_help()
        return 2
    if args.acao == "quote":
        return _quote(args)
    if args.acao == "approve":
        return _approve(args)
    if args.acao == "start":
        return _start(args)
    return _show(args)


def _quote(args) -> int:
    store = JsonStore()
    item = store.get_item(args.item)
    if item is None:
        return _erro(f"item não encontrado: {args.item}")
    if _rota(item) != ROTA:
        return _erro(
            f"{item.id}: generate quote exige a rota {ROTA} (rota atual: {_rota(item)})"
        )
    try:
        verifica = budget.media_credits()
        gasto = budget.gasto_do_dia(store.read(), budget.agora().date())
        budget.verifica_aprovacao(args.credits, verifica, args.daily_cap, gasto)
    except budget.BudgetError as exc:
        return _erro(f"{item.id}: {exc}")

    passo = {
        "kind": PASSO,
        "provider": args.provider,
        "estimate_ref": args.estimate_ref,
        "credits": args.credits,
    }
    item.production = {
        **item.production,
        "steps": [*(item.production.get("steps") or []), passo],
    }
    try:
        transition(item, "quoted", store)
    except InvalidTransition as exc:
        return _erro(f"{item.id}: {exc}")
    store.append_event(
        EVENTO_COTADO,
        item.id,
        {
            "provider": args.provider,
            "estimate_ref": args.estimate_ref,
            "credits": args.credits,
        },
    )
    print(f"{item.id}: quoted")
    print(f"custo: {args.credits} créditos ({args.provider}, ref {args.estimate_ref})")
    return 0


def _start(args) -> int:
    store = JsonStore()
    item = store.get_item(args.item)
    if item is None:
        return _erro(f"item não encontrado: {args.item}")
    if item.state != "approved":
        return _erro(
            f"{item.id}: generate start exige o estado approved (estado atual: {item.state})"
        )
    passo = _ultimo_passo_ai(item)
    if passo is None or not passo.get("confirmed_by"):
        return _erro(
            f"{item.id}: sem aprovação registrada (passo ai_media com confirmed_by): rode generate approve antes"
        )
    try:
        transition(item, "generating", store)
    except InvalidTransition as exc:
        return _erro(f"{item.id}: {exc}")
    print(f"{item.id}: generating")
    return 0


def _parser_media() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="simplicio-video media",
        description="Mídia gerada por IA que volta ao item (rota ai_assisted). `attach` copia o arquivo baixado do "
        "Real Oficial para a pasta do item, grava o recibo e leva o item de generating para generated.",
        epilog=EXEMPLO_MEDIA,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    acoes = ap.add_subparsers(dest="acao", metavar="{attach}")

    a = acoes.add_parser(
        "attach",
        prog="simplicio-video media attach",
        help="anexa o arquivo gerado ao item (generating -> generated) e grava o recibo",
        description="Confere o estado generating, a aprovação registrada e o claim guard do prompt; copia o arquivo "
        "para <item>/media/ e grava <item>/media.json. Recusa sem gravar nada se algo falhar. O arquivo não é movido.",
        epilog=EXEMPLO_ATTACH,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    a.add_argument("item", help="id do item (itm_...)")
    a.add_argument(
        "arquivo",
        metavar="ARQUIVO",
        help="arquivo baixado do Real Oficial (MP4); é copiado, nunca movido",
    )
    a.add_argument("--source", required=True, choices=ORIGENS, help="origem da mídia")
    a.add_argument(
        "--media-id",
        required=True,
        metavar="ID",
        help="id da mídia no Real Oficial (fica no recibo)",
    )
    a.add_argument(
        "--prompt-file",
        required=True,
        metavar="ARQ",
        help="arquivo com o prompt usado na geração (o recibo guarda só o sha256)",
    )
    a.add_argument(
        "--brand",
        metavar="BRAND.JSON",
        help="brand.json com os fatos do claim guard (padrão: SIMPLICIO_FACTORY_HOME/brand.json)",
    )
    return ap


def media_cmd(argv: list[str]) -> int:
    ap = _parser_media()
    if not argv:
        ap.print_help()
        return 2
    args = ap.parse_args(argv)
    if args.acao is None:
        ap.print_help()
        return 2
    return _attach(args)


def _attach(args) -> int:
    if not args.media_id.strip():
        return _erro(
            "--media-id não pode ser vazio: informe o id da mídia no Real Oficial"
        )
    store = JsonStore()
    brand = Path(args.brand) if args.brand else store.root / "brand.json"
    try:
        recibo = attach.anexa(
            store,
            item_id=args.item,
            arquivo=Path(args.arquivo),
            origem=args.source,
            media_id=args.media_id.strip(),
            prompt_file=Path(args.prompt_file),
            brand_path=brand,
        )
    except (attach.AttachError, InvalidTransition) as exc:
        return _erro(str(exc))
    print(f"{args.item}: generated")
    print(f"media: {store.root / 'studio' / args.item / 'media' / recibo['arquivo']}")
    print(f"sha256: {recibo['sha256']}")
    return 0


def _confirma(item_id: str, passo: dict, by: str) -> bool:
    if not sys.stdin.isatty():
        raise PermissionError(f"{item_id}: aprovação sem terminal exige --yes")
    pergunta = (
        f"Aprovar o gasto de {passo['credits']} créditos ({passo['provider']}, ref {passo['estimate_ref']}) "
        f"no item {item_id}, por {by}? [s/N] "
    )
    try:
        resposta = input(pergunta)
    except EOFError:
        resposta = ""
    return resposta.strip().lower() in RESPOSTAS_SIM


def _approve(args) -> int:
    by = args.by.strip()
    if not by:
        return _erro("--by não pode ser vazio: diga quem aprova")
    store = JsonStore()
    item = store.get_item(args.item)
    if item is None:
        return _erro(f"item não encontrado: {args.item}")
    passo = _ultimo_passo_ai(item)
    if item.state == "approved" and passo is not None:
        print(
            f"{item.id}: já aprovado por {passo.get('confirmed_by')} em {passo.get('confirmed_at')}; nada alterado"
        )
        return 0
    if item.state != "quoted":
        return _erro(
            f"{item.id}: aprovação exige o estado quoted (estado atual: {item.state})"
        )
    if passo is None:
        return _erro(
            f"{item.id}: sem passo {PASSO} para aprovar: rode generate quote antes"
        )
    try:
        verifica = budget.media_credits()
        gasto = budget.gasto_do_dia(store.read(), budget.agora().date())
        budget.verifica_aprovacao(passo["credits"], verifica, args.daily_cap, gasto)
    except budget.BudgetError as exc:
        return _erro(f"{item.id}: {exc}")
    if not args.yes:
        try:
            confirmado = _confirma(item.id, passo, by)
        except PermissionError as exc:
            return _erro(str(exc))
        if not confirmado:
            return _erro(f"{item.id}: aprovação não confirmada; nada foi alterado")

    agora = budget.agora()
    passo["confirmed_by"] = by
    passo["confirmed_at"] = agora.isoformat()
    try:
        transition(item, "approved", store)
    except InvalidTransition as exc:
        return _erro(f"{item.id}: {exc}")
    store.append_event(
        EVENTO_APROVADO,
        item.id,
        {
            "provider": passo["provider"],
            "estimate_ref": passo["estimate_ref"],
            "credits": passo["credits"],
            "confirmed_by": by,
            "at": agora.isoformat(),
        },
    )
    print(f"{item.id}: approved (por {by}, {passo['credits']} créditos)")
    return 0


def _show(args) -> int:
    item = JsonStore().get_item(args.item)
    if item is None:
        return _erro(f"item não encontrado: {args.item}")
    passo = _ultimo_passo_ai(item)
    dados = {
        "item": item.id,
        "state": item.state,
        "step": passo,
        "credits": passo["credits"] if passo else None,
        "confirmed_by": passo.get("confirmed_by") if passo else None,
        "confirmed_at": passo.get("confirmed_at") if passo else None,
    }
    if args.json:
        print(json.dumps(dados, ensure_ascii=False, indent=2))
        return 0
    print(f"{item.id}: {item.state}")
    if passo is None:
        print(f"sem passo {PASSO}: rode generate quote")
        return 0
    print(f"provider: {passo['provider']}")
    print(f"estimate_ref: {passo['estimate_ref']}")
    print(f"custo: {passo['credits']} créditos")
    print(
        f"aprovado por: {passo.get('confirmed_by') or '-'} em {passo.get('confirmed_at') or '-'}"
    )
    return 0
