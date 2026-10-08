"""Helpers dos testes do quadro (#86, épico #81). Importados explicitamente, como tests/factory/_fixtures.py (#33).

Os imports de `simplicio_factory.plugins.board` ficam dentro das funções: um módulo ausente falha o teste que o
usa, e não a coleta da suíte inteira.

Interface que a fase 2 precisa cumprir (usada por estes testes):
- `plugins/board/model.py`: `COLUNAS` (pares (chave, título) na ordem do quadro), `coluna_de(state, review) -> chave`,
  `colunas_da_rota(route) -> frozenset de chaves`.
- `plugins/board/service.py`: `listar(home) -> dict` (schema, columns), `comentar(home, item_id, texto, by, *, relogio)`,
  `revisar(home, item_id, decisao, by, note=None, *, relogio)`, `ler_comentarios(home, item_id) -> list[dict]`,
  `caminho_comentarios(home, item_id) -> Path`, exceção `BoardError`. `relogio` é um callable que devolve o `at`.
- `plugins/board/cli.py`: `board_cmd(argv) -> int`.
- `plugins/board/schema.py`: `build_schema() -> dict` (o gerador lê o mesmo dicionário que `make factory-schema` grava).
- `schemas/factory/board.schema.json`: gerado; lido pelos testes a partir da raiz do repo.
"""

from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path

from tests.factory._fixtures import ai_production, json_store, make_routed_item

ROOT = Path(__file__).resolve().parents[4]
PLUGIN_DIR = ROOT / "src" / "simplicio_factory" / "plugins" / "board"
MANIFEST_PATH = PLUGIN_DIR / "plugin.json"
SCHEMA = ROOT / "schemas" / "factory" / "board.schema.json"
ITEM_ID = "itm_01HZBOARD00000000000001"
RELOGIO_FIXO = "2026-10-08T10:00:00-03:00"

CHAVES_DE_COLUNA = ("ideia", "roteiro", "orcamento", "aprovado", "gerando", "revisao", "pronto", "falhou")
TITULOS_DE_COLUNA = ("Ideia", "Roteiro", "Orçamento", "Aprovado", "Gerando", "Revisão", "Pronto", "Falhou")


def _modulo(name: str):
    import importlib

    return importlib.import_module(f"simplicio_factory.plugins.board.{name}")


def model_module():
    return _modulo("model")


def service_module():
    return _modulo("service")


def cli_module():
    return _modulo("cli")


def fixed_clock():
    return lambda: RELOGIO_FIXO


def home_de(tmp_path: Path) -> Path:
    return tmp_path / "home"


def salvar_item(
    home: Path, state: str, *, route: str = "deterministic", review=None, item_id: str = ITEM_ID, brand: str = "acme"
):
    """Grava um item no JsonStore de `home`. A rota `ai_assisted` leva um passo ai_media com provider (fixture da #82)."""
    production = ai_production() if route == "ai_assisted" else {"route": "deterministic", "steps": []}
    item = make_routed_item(state=state, production=production, review=review, item_id=item_id, brand=brand)
    json_store(home).save_item(item)
    return item


def ler_item_cru(home: Path, item_id: str = ITEM_ID) -> dict:
    return json.loads((home / "items" / f"{item_id}.json").read_text(encoding="utf-8"))


def run_cli(argv: list[str]) -> tuple[int, str, str]:
    """Roda `board_cmd` e devolve (código, stdout, stderr). SystemExit do argparse vira código."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = cli_module().board_cmd(argv)
        except SystemExit as exc:
            code = exc.code if isinstance(exc.code, int) else 1
    return code, out.getvalue(), err.getvalue()


def carregar_validador():
    """Validador Draft 2020-12 do schema commitado. Falha com a causa se o arquivo ainda não existe."""
    import jsonschema

    assert SCHEMA.is_file(), "schemas/factory/board.schema.json ausente: gerado pelo make factory-schema (#86)"
    return jsonschema.Draft202012Validator(json.loads(SCHEMA.read_text(encoding="utf-8")))


def cartao_em(quadro: dict, item_id: str):
    """Devolve (chave da coluna, cartão) do item no quadro, ou (None, None) se ele não aparece."""
    for coluna in quadro["columns"]:
        for cartao in coluna["cards"]:
            if cartao["id"] == item_id:
                return coluna["id"], cartao
    return None, None
