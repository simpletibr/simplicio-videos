"""Modelo do quadro (#86, épico #81): colunas derivadas de `state` e `review`, nunca guardadas.

Puro, sem I/O. O quadro é uma projeção dos itens do JsonStore: nenhum cartão tem coluna gravada, e mover um
item de etapa é `transition()` (este módulo nunca escreve estado).
"""

from __future__ import annotations

from simplicio_factory.contracts.models import DEFAULT_ROUTE
from simplicio_factory.contracts.transitions import transitions_for

SCHEMA = "simplicio.board/v1"
REVIEW_APROVADA = "approved"

# Ordem do quadro: (chave estável, título exibido).
COLUNAS = (
    ("ideia", "Ideia"),
    ("roteiro", "Roteiro"),
    ("orcamento", "Orçamento"),
    ("aprovado", "Aprovado"),
    ("gerando", "Gerando"),
    ("revisao", "Revisão"),
    ("pronto", "Pronto"),
    ("falhou", "Falhou"),
)
CHAVES_DE_COLUNA = tuple(chave for chave, _ in COLUNAS)

# Estados cuja coluna não depende de `review`. `rendered` é tratado em coluna_de().
_COLUNA_POR_ESTADO = {
    "idea": "ideia",
    "drafted": "roteiro",
    "quoted": "orcamento",
    "approved": "aprovado",
    "generating": "gerando",
    "generated": "gerando",
    "rendering": "gerando",
    "failed": "falhou",
}


def coluna_de(state: str, review: str | None) -> str:
    """Chave da coluna de um item. Só `rendered` olha o `review`: aprovado vai a Pronto, o resto a Revisão."""
    if state == "rendered":
        return "pronto" if review == REVIEW_APROVADA else "revisao"
    try:
        return _COLUNA_POR_ESTADO[state]
    except KeyError:
        raise ValueError(f"estado sem coluna no quadro: {state!r}") from None


def colunas_da_rota(route: str) -> frozenset[str]:
    """Colunas que os itens de uma rota podem ocupar, pelos estados do grafo de transições da rota."""
    estados = {estado for par in transitions_for(route) for estado in par}
    colunas = {coluna_de(estado, None) for estado in estados}
    if "rendered" in estados:
        colunas.add(coluna_de("rendered", REVIEW_APROVADA))
    return frozenset(colunas)


def rota_de(production) -> str:
    return (production or {}).get("route", DEFAULT_ROUTE)


def cartao(item, comentarios: int) -> dict:
    """Cartão de um item: só o que o quadro mostra. Não inclui a coluna, que é derivada."""
    return {
        "id": item.id,
        "brand": item.brand,
        "state": item.state,
        "route": rota_de(item.production),
        "review": item.review,
        "failed_from": item.failed_from,
        "comments": comentarios,
    }


def montar_quadro(cartoes: list[dict]) -> dict:
    """Agrupa cartões nas colunas, na ordem fixa do quadro, com os cartões de cada coluna ordenados por id."""
    por_coluna: dict[str, list[dict]] = {chave: [] for chave in CHAVES_DE_COLUNA}
    for c in cartoes:
        por_coluna[coluna_de(c["state"], c["review"])].append(c)
    return {
        "schema": SCHEMA,
        "columns": [
            {"id": chave, "title": titulo, "cards": sorted(por_coluna[chave], key=lambda c: c["id"])}
            for chave, titulo in COLUNAS
        ],
    }
