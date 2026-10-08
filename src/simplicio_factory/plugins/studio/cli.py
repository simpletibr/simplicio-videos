"""Comandos do studio (#16): handlers de src/simplicio_factory/plugins/studio/plugin.json (#32).

    simplicio-video make [ITEM] [--from DRAFT.JSON] [--brand BRAND.JSON]   roda o estágio até rendered
    simplicio-video make preview ITEM                                       prévia 540x960 com marca d'água
    simplicio-video draft show ITEM                                         imprime o Draft do item em JSON

Pasta do item: $SIMPLICIO_FACTORY_HOME/studio/<item_id>/ (padrão .simplicio-factory/, gitignored).
Brand: $SIMPLICIO_FACTORY_HOME/brand.json, ou --brand.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import re
import sys
import unicodedata
from pathlib import Path

from simplicio_factory.contracts import Brand, Draft, Item
from simplicio_factory.contracts.json_store import JsonStore

EXEMPLO_MAKE = """Exemplo:
  simplicio-video make --from draft.json --brand brand.json   importa o Draft e roda até rendered
  simplicio-video make itm_01HZEXEMPLO0000000000001          roda um item que já tem Draft na pasta
"""
EXEMPLO_PREVIEW = """Exemplo:
  simplicio-video make preview itm_01HZEXEMPLO0000000000001   prévia 540x960 em <pasta>/preview/
"""
EXEMPLO_DRAFT = """Exemplo:
  simplicio-video draft show itm_01HZEXEMPLO0000000000001
"""
EXEMPLO_DRAFT_SHOW = """Exemplo:
  simplicio-video draft show itm_01HZEXEMPLO0000000000001 > draft.json
"""


def _home() -> Path:
    return Path(os.environ.get("SIMPLICIO_FACTORY_HOME") or ".simplicio-factory")


def _erro(mensagem: str) -> int:
    print(f"erro: {mensagem}", file=sys.stderr)
    return 1


def _slug(nome: str) -> str:
    sem_acento = "".join(c for c in unicodedata.normalize("NFKD", nome) if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "-", sem_acento.lower()).strip("-")


def _ler_draft(caminho: Path) -> Draft:
    return Draft(**json.loads(caminho.read_text(encoding="utf-8")))


def _ler_brand(caminho: Path) -> Brand:
    dados = json.loads(caminho.read_text(encoding="utf-8"))
    logo = str((caminho.parent / dados["logo"]).resolve()) if dados.get("logo") else None
    return Brand(name=dados["name"], colors=dados["colors"], logo=logo, facts=dados.get("facts", {}))


def _pasta_estudio(home: Path) -> Path:
    return home / "studio"


def _montar_stage(brand: Brand, raiz: Path, drafts: dict):
    from simplicio_factory.plugins.studio.renderer import EngineRenderer
    from simplicio_factory.plugins.studio.stage import StudioStage

    return StudioStage(brand=brand, renderer=EngineRenderer(raiz / "renders"), drafts=drafts, work_dir=raiz)


def make_cmd(argv: list[str]) -> int:
    if argv[:1] == ["preview"]:
        return _make_preview(argv[1:])
    parser = argparse.ArgumentParser(
        prog="simplicio-video make",
        description="Roda o estágio studio do item até rendered: Draft -> contract.yaml (determinístico) -> render.",
        epilog=EXEMPLO_MAKE,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("item", nargs="?", help="id do item (itm_...)")
    parser.add_argument("--from", dest="origem", metavar="DRAFT.JSON", help="copia este Draft para a pasta do item antes de compor")
    parser.add_argument("--brand", metavar="BRAND.JSON", help="brand.json (padrão: SIMPLICIO_FACTORY_HOME/brand.json)")
    args = parser.parse_args(argv)

    home = _home()
    store = JsonStore(home)
    pasta_raiz = _pasta_estudio(home)
    brand_path = Path(args.brand) if args.brand else home / "brand.json"
    if not brand_path.is_file():
        return _erro(f"brand não encontrado: {brand_path} (use --brand ou SIMPLICIO_FACTORY_HOME/brand.json)")
    try:
        brand = _ler_brand(brand_path)
    except (KeyError, TypeError, ValueError) as exc:
        return _erro(f"brand inválido em {brand_path}: {exc}")

    if args.origem:
        try:
            draft = _ler_draft(Path(args.origem))
        except (TypeError, ValueError, KeyError) as exc:
            return _erro(f"Draft inválido em {args.origem}: {exc}")
        if args.item and args.item != draft.item_id:
            return _erro(f"o Draft é do item {draft.item_id}, não de {args.item}")
        item_id = draft.item_id
        pasta = pasta_raiz / item_id
        pasta.mkdir(parents=True, exist_ok=True)
        (pasta / "draft.json").write_text(json.dumps(dataclasses.asdict(draft), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if store.get_item(item_id) is None:
            store.save_item(Item(id=item_id, brand=_slug(brand.name)))
    elif args.item:
        item_id = args.item
        pasta = pasta_raiz / item_id
    else:
        parser.error("informe o ITEM ou --from DRAFT.JSON")

    item = store.get_item(item_id)
    if item is None:
        return _erro(f"item não encontrado: {item_id} (crie com --from DRAFT.JSON)")
    draft_path = pasta / "draft.json"
    if not draft_path.is_file():
        return _erro(f"sem Draft para {item_id}: rode make --from DRAFT.JSON")
    try:
        draft = _ler_draft(draft_path)
        stage = _montar_stage(brand, pasta_raiz, {item_id: draft})
        stage.run(item, store)
    except Exception as exc:  # ClaimError, ValueError do composer, InvalidTransition, falha do render
        return _erro(f"{item_id}: {exc}")
    estado = json.loads((pasta / "studio.json").read_text(encoding="utf-8"))
    print(f"{item_id}: rendered")
    print(f"mp4: {estado['stages']['studio']['mp4']}")
    return 0


def _make_preview(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="simplicio-video make preview",
        description="Renderiza a prévia 540x960 com marca d'água do item (não muda o estado do item).",
        epilog=EXEMPLO_PREVIEW,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("item", help="id do item (itm_...)")
    parser.add_argument("--brand", metavar="BRAND.JSON", help="brand.json (padrão: SIMPLICIO_FACTORY_HOME/brand.json)")
    args = parser.parse_args(argv)

    home = _home()
    pasta_raiz = _pasta_estudio(home)
    pasta = pasta_raiz / args.item
    draft_path = pasta / "draft.json"
    if not draft_path.is_file():
        return _erro(f"sem Draft para {args.item}: rode make --from DRAFT.JSON antes da prévia")
    brand_path = Path(args.brand) if args.brand else home / "brand.json"
    if not brand_path.is_file():
        return _erro(f"brand não encontrado: {brand_path}")
    try:
        brand = _ler_brand(brand_path)
        draft = _ler_draft(draft_path)
        resultado = _montar_stage(brand, pasta_raiz, {args.item: draft}).previa(args.item)
    except Exception as exc:
        return _erro(f"{args.item}: {exc}")
    print(f"previa: {resultado.mp4_path}")
    return 0


def draft_cmd(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="simplicio-video draft",
        description="Consulta o Draft de um item do studio.",
        epilog=EXEMPLO_DRAFT,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    acoes = parser.add_subparsers(dest="acao", metavar="{show}")
    show = acoes.add_parser(
        "show",
        prog="simplicio-video draft show",
        help="imprime o Draft do item em JSON",
        description="Imprime o Draft do item em JSON (lido de <pasta>/draft.json).",
        epilog=EXEMPLO_DRAFT_SHOW,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    show.add_argument("item", help="id do item (itm_...)")
    args = parser.parse_args(argv)
    if args.acao is None:
        parser.print_help()
        return 2

    home = _home()
    caminho = _pasta_estudio(home) / args.item / "draft.json"
    if not caminho.is_file():
        if JsonStore(home).get_item(args.item) is None:
            return _erro(f"item não encontrado: {args.item}")
        return _erro(f"sem Draft para o item {args.item}")
    print(json.dumps(json.loads(caminho.read_text(encoding="utf-8")), ensure_ascii=False, indent=2))
    return 0
