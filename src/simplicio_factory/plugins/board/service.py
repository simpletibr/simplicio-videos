"""Serviço do quadro (#86, épico #81): listar, comentar e revisar sobre o JsonStore.

Estado: `<home>/items/<id>.json` (o JsonStore do kernel) e `<home>/items/<id>/comments.jsonl` (comentários, append-only,
uma linha JSON por comentário). O quadro não grava coluna; `review` é o único campo que este módulo altera no item.

Concorrência: um escritor por vez. A CLI não tem trava de arquivo; o servidor (#89) serializa as escritas.
Sem rede e sem LLM.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from simplicio_factory.contracts.json_store import JsonStore
from simplicio_factory.plugins.board import model

COMENTARIOS = "comments.jsonl"
TIPO_COMENTARIO = "comment"
TIPO_REVISAO = "review"
# decisão da CLI -> (valor de item.review, texto padrão da linha de revisão)
DECISOES = {
    "approve": ("approved", "aprovado"),
    "changes": ("changes_requested", "alterações solicitadas"),
}
_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")
_FUSO_BRT = timezone(timedelta(hours=-3))


class BoardError(ValueError):
    """Erro de uso do quadro (item inexistente, texto ou autor vazio, revisão fora de um item renderizado)."""


def agora_brt() -> str:
    """Relógio de produção: horário de Brasília, em ISO 8601. Os testes injetam outro `relogio`."""
    return datetime.now(_FUSO_BRT).isoformat(timespec="seconds")


def _checa_id(item_id: str) -> str:
    if not isinstance(item_id, str) or not _ID_RE.match(item_id):
        raise BoardError(f"id de item inválido: {item_id!r}")
    return item_id


def caminho_comentarios(home, item_id: str) -> Path:
    return Path(home) / "items" / _checa_id(item_id) / COMENTARIOS


def ler_comentarios(home, item_id: str) -> list[dict]:
    arquivo = caminho_comentarios(home, item_id)
    if not arquivo.is_file():
        return []
    return [json.loads(linha) for linha in arquivo.read_text(encoding="utf-8").splitlines() if linha.strip()]


def _item(store: JsonStore, item_id: str):
    _checa_id(item_id)
    item = store.get_item(item_id)
    if item is None:
        raise BoardError(f"item não encontrado: {item_id}")
    return item


def _autor(by) -> str:
    if not isinstance(by, str) or not by.strip():
        raise BoardError("--by é obrigatório: informe quem escreve")
    return by.strip()


def _texto(texto) -> str:
    if not isinstance(texto, str) or not texto.strip():
        raise BoardError("o texto não pode ser vazio")
    return texto.strip()


def _anexa(home, item_id: str, kind: str, by: str, text: str, relogio: Callable[[], str]) -> dict:
    """Acrescenta uma linha a comments.jsonl. O id é a posição da linha no arquivo (1, 2, 3...)."""
    arquivo = caminho_comentarios(home, item_id)
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    linha = {"id": len(ler_comentarios(home, item_id)) + 1, "at": relogio(), "by": by, "kind": kind, "text": text}
    with arquivo.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(linha, ensure_ascii=False) + "\n")
    return linha


def comentar(home, item_id: str, texto: str, by: str, *, relogio: Callable[[], str] = agora_brt) -> dict:
    """Grava um comentário (kind=comment) no item. Não muda estado nem review."""
    autor = _autor(by)
    corpo = _texto(texto)
    _item(JsonStore(home), item_id)
    return _anexa(home, item_id, TIPO_COMENTARIO, autor, corpo, relogio)


def revisar(
    home, item_id: str, decisao: str, by: str, note: str | None = None, *, relogio: Callable[[], str] = agora_brt
) -> dict:
    """Define item.review (approved ou changes_requested) e grava a linha kind=review.

    Só vale para item `rendered`: a revisão é do vídeo pronto. `approved` leva o cartão a Pronto; o resto fica em Revisão.
    """
    if decisao not in DECISOES:
        raise BoardError(f"decisão inválida: {decisao!r} (use approve ou changes)")
    autor = _autor(by)
    store = JsonStore(home)
    item = _item(store, item_id)
    if item.state != "rendered":
        raise BoardError(f"revisão só vale para item rendered (estado atual: {item.state})")
    review, padrao = DECISOES[decisao]
    texto = (note or "").strip() or padrao
    item.review = review
    store.save_item(item)
    return _anexa(home, item_id, TIPO_REVISAO, autor, texto, relogio)


def listar(home) -> dict:
    """Quadro determinístico: colunas fixas, cartões ordenados por id, nada com horário."""
    store = JsonStore(home)
    cartoes = [
        model.cartao(item, len(ler_comentarios(home, item.id)))
        for item in sorted(store.list_items(), key=lambda i: i.id)
    ]
    return model.montar_quadro(cartoes)
