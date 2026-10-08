"""Orçamento de geração por IA (#85, épico #81): media_credits do workspace e o teto diário.

Chave: `budgets.media_credits` no `policy.yaml` do workspace, o arquivo que `simplicio-video setup` grava em
$SIMPLICIO_WORKSPACE (padrão ~/.simplicio-video/workspaces/default). Ausente = 0, ou seja, nenhuma aprovação.

`media_credits` é o teto de cada aprovação (um item não pode custar mais do que ele). O saldo não é debitado
aqui: quem sabe o saldo real é o Real Oficial (`ro_confirm_spend`). O teto diário é a soma dos créditos aprovados
no dia (horário de Brasília, UTC-3, sem horário de verão desde 2019) mais o da aprovação nova.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import yaml

DEFAULT_DAILY_CAP = 1000
BRT = timezone(timedelta(hours=-3))
SPEND_APPROVED = "spend.approved"


class BudgetError(Exception):
    """Aprovação ou cotação recusada pelo orçamento. A mensagem diz o limite que foi passado."""


def agora() -> datetime:
    """Instante atual em horário de Brasília. Os testes trocam esta função por um relógio fixo."""
    return datetime.now(BRT)


def workspace_dir() -> Path:
    """Mesma pasta que `simplicio-video setup` grava (importada de lá, para não haver duas fontes)."""
    from simplicio_video.commands.setup import workspace_dir as _workspace_dir

    return _workspace_dir()


def media_credits(workspace: Path | None = None) -> int:
    """budgets.media_credits do policy.yaml; 0 se o arquivo, a seção ou a chave não existirem."""
    caminho = (workspace or workspace_dir()) / "policy.yaml"
    if not caminho.is_file():
        return 0
    dados = yaml.safe_load(caminho.read_text(encoding="utf-8")) or {}
    if not isinstance(dados, dict):
        raise BudgetError(f"policy.yaml inválido em {caminho}: esperado um objeto YAML")
    budgets = dados.get("budgets") or {}
    if not isinstance(budgets, dict):
        raise BudgetError(
            f"policy.yaml inválido em {caminho}: budgets deve ser um objeto"
        )
    valor = budgets.get("media_credits", 0)
    if valor is None:
        return 0
    if isinstance(valor, bool) or not isinstance(valor, int) or valor < 0:
        raise BudgetError(
            f"budgets.media_credits inválido em {caminho}: {valor!r} (use um inteiro maior ou igual a 0)"
        )
    return valor


def gasto_do_dia(events, dia: date) -> int:
    """Soma de `credits` dos eventos spend.approved cujo `at` cai em `dia`, no fuso de Brasília.

    `at` sem fuso é lido como horário de Brasília. Evento sem `at` legível não entra na conta.
    """
    total = 0
    for evento in events:
        if evento.kind != SPEND_APPROVED:
            continue
        at = evento.data.get("at")
        if not isinstance(at, str):
            continue
        try:
            quando = datetime.fromisoformat(at)
        except ValueError:
            continue
        if quando.tzinfo is None:
            quando = quando.replace(tzinfo=BRT)
        if quando.astimezone(BRT).date() == dia:
            total += int(evento.data.get("credits", 0))
    return total


def verifica_aprovacao(
    credits: int, media: int, daily_cap: int = DEFAULT_DAILY_CAP, gasto_hoje: int = 0
) -> None:
    """Levanta BudgetError se o gasto não cabe. Orçamento zero recusa qualquer gasto."""
    if media <= 0:
        raise BudgetError(
            "orçamento de mídia zero (budgets.media_credits = 0): nenhuma cotação ou aprovação é possível. "
            "Ajuste o policy.yaml do workspace"
        )
    if credits > media:
        raise BudgetError(f"credits ({credits}) acima de media_credits ({media})")
    if credits > daily_cap:
        raise BudgetError(f"credits ({credits}) acima do teto diário ({daily_cap})")
    if gasto_hoje + credits > daily_cap:
        raise BudgetError(
            f"gasto de hoje ({gasto_hoje}) mais {credits} passa do teto diário ({daily_cap}); "
            "aprove amanhã ou use --daily-cap"
        )
