"""Helpers dos testes do plugin media (#85, épico #81). Importados explicitamente, como tests/factory/_fixtures.py.

Não há conftest.py em subpasta de tests (#43). Os imports de `simplicio_factory.plugins.media` ficam dentro das
funções: enquanto o plugin não existe, cada teste falha no próprio corpo (ModuleNotFoundError do media), e não
a coleta da suíte inteira.

Interface que a fase 2 precisa cumprir (usada por estes testes):
- `plugins/media/budget.py`: `DEFAULT_DAILY_CAP == 1000`, `BudgetError`, `agora() -> datetime` (aware, BRT),
  `media_credits(workspace=None) -> int` (lê budgets.media_credits do policy.yaml; 0 se ausente),
  `gasto_do_dia(events, dia) -> int` (soma credits de spend.approved cujo `at` cai em `dia` no fuso BRT),
  `verifica_aprovacao(credits, media, daily_cap=DEFAULT_DAILY_CAP, gasto_hoje=0) -> None`.
- `plugins/media/cli.py`: `generate_cmd(argv) -> int` com os subcomandos `quote`, `approve` e `show`.
- `plugins/media/plugin.json`: id `media`, comando `generate`.
"""

from __future__ import annotations

import contextlib
import importlib
import io
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

BRT = timezone(timedelta(hours=-3))
ITEM_ID = "itm_01HZMEDIA0000000000001"
OUTRO_ID = "itm_01HZMEDIA0000000000002"
ESTIMATIVA = "est_01HZREALOFICIAL0001"
AGORA = datetime(2026, 10, 8, 10, 0, tzinfo=BRT)


def _media(name: str):
    return importlib.import_module(f"simplicio_factory.plugins.media.{name}")


def cli_module():
    return _media("cli")


def budget_module():
    return _media("budget")


def escreve_policy(workspace: Path, media_credits: int | None) -> None:
    """policy.yaml no formato que `simplicio-video setup` grava (budgets.media_credits)."""
    budgets = {"llm_tokens": 0, "llm_usd": 0}
    if media_credits is not None:
        budgets["media_credits"] = media_credits
    workspace.mkdir(parents=True, exist_ok=True)
    dados = {
        "schema": "simplicio.policy/v1",
        "autonomy": {"default": "L1"},
        "budgets": budgets,
    }
    (workspace / "policy.yaml").write_text(
        yaml.safe_dump(dados, sort_keys=False), encoding="utf-8"
    )


def ambiente(monkeypatch, tmp_path: Path, media_credits: int = 500):
    """Isola o store do kernel e o workspace; relógio fixo em AGORA. Devolve (home, workspace)."""
    home = tmp_path / "home"
    workspace = tmp_path / "ws"
    monkeypatch.setenv("SIMPLICIO_FACTORY_HOME", str(home))
    monkeypatch.setenv("SIMPLICIO_WORKSPACE", str(workspace))
    escreve_policy(workspace, media_credits)
    monkeypatch.setattr(budget_module(), "agora", lambda: AGORA)
    return home, workspace


def passo_ai(credits: int = 120, provider: str = "real-oficial") -> dict:
    return {
        "kind": "ai_media",
        "provider": provider,
        "estimate_ref": ESTIMATIVA,
        "credits": credits,
    }


def grava_item(
    home: Path,
    state: str = "drafted",
    route: str = "ai_assisted",
    steps=None,
    item_id: str = ITEM_ID,
):
    from simplicio_factory.contracts import Item
    from simplicio_factory.contracts.json_store import JsonStore

    production = {"route": route, "steps": [] if steps is None else steps}
    item = Item(id=item_id, brand="acme", state=state, production=production)
    JsonStore(home).save_item(item)
    return item


def grava_quoted(home: Path, credits: int = 120, item_id: str = ITEM_ID):
    return grava_item(home, state="quoted", steps=[passo_ai(credits)], item_id=item_id)


def le_item(home: Path, item_id: str = ITEM_ID):
    from simplicio_factory.contracts.json_store import JsonStore

    return JsonStore(home).get_item(item_id)


def eventos(home: Path, kind: str | None = None) -> list:
    from simplicio_factory.contracts.json_store import JsonStore

    todos = JsonStore(home).read()
    return [e for e in todos if kind is None or e.kind == kind]


class Terminal:
    """Stdin falso: `tty` diz se é terminal; `resposta` é a linha que o usuário digita."""

    def __init__(self, resposta: str = "", tty: bool = True) -> None:
        self.resposta = resposta
        self.tty = tty

    def isatty(self) -> bool:
        return self.tty

    def readline(self) -> str:
        return self.resposta + "\n"


def com_terminal(monkeypatch, resposta: str) -> None:
    import sys

    monkeypatch.setattr(sys, "stdin", Terminal(resposta, tty=True))


def sem_terminal(monkeypatch) -> None:
    import sys

    monkeypatch.setattr(sys, "stdin", Terminal("", tty=False))


def run_cli(fn, argv: list[str]) -> tuple[int, str, str]:
    """Roda um handler de CLI e devolve (código, stdout, stderr); SystemExit do argparse vira código."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = fn(argv)
        except SystemExit as exc:
            code = exc.code if isinstance(exc.code, int) else 1
    return code, out.getvalue(), err.getvalue()


def gera(*argv: str) -> tuple[int, str, str]:
    return run_cli(cli_module().generate_cmd, list(argv))
