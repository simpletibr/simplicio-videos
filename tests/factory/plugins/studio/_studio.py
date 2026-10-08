"""Helpers dos testes do studio (#16). Importados explicitamente, como tests/factory/_fixtures.py (#33).

Os imports de `simplicio_factory.plugins.studio` ficam dentro das funções: um módulo ainda ausente falha o
teste que o usa, e não a coleta da suíte inteira.

Interface que a fase 2 precisa cumprir (usada por estes testes):
- `plugins/studio/stage.py`: `StudioStage(brand, renderer, drafts, work_dir)`, `name == "studio"`,
  `run(item, store)`; módulo importa `transition` no nível do módulo.
- `plugins/studio/composer.py`: `compose_contract(draft, brand, *, preview=False) -> str` (YAML do motor).
- `plugins/studio/claims.py`: `check_claims(draft, brand) -> None` e `ClaimError`.
- `plugins/studio/hashing.py`: `content_hash(contract_path, draft) -> str`.
- `plugins/studio/renderer.py`: `EngineRenderer(out_dir)`, `render(contract_path, preview) -> RenderResult`.
- `plugins/studio/cli.py`: `make_cmd(argv) -> int`, `draft_cmd(argv) -> int`.
"""

from __future__ import annotations

import importlib
import json
from dataclasses import replace
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIXTURES = HERE / "fixtures"
GOLDEN = HERE / "golden" / "contract.yaml"
ITEM_ID = "itm_01HZGOLDEN0000000000001"
BRAND_ID = "clinica-exemplo"


def _studio(name: str):
    return importlib.import_module(f"simplicio_factory.plugins.studio.{name}")


def stage_module():
    return _studio("stage")


def composer_module():
    return _studio("composer")


def claims_module():
    return _studio("claims")


def cli_module():
    return _studio("cli")


def hashing_module():
    return _studio("hashing")


def renderer_module():
    return _studio("renderer")


def load_draft():
    from simplicio_factory.contracts import Draft

    return Draft(**json.loads((FIXTURES / "draft.json").read_text(encoding="utf-8")))


def load_brand():
    from simplicio_factory.contracts import Brand

    data = json.loads((FIXTURES / "brand.json").read_text(encoding="utf-8"))
    return Brand(name=data["name"], colors=data["colors"], logo=str(FIXTURES / data["logo"]), facts=data["facts"])


def draft_with(**changes):
    return replace(load_draft(), **changes)


def make_item(item_id: str = ITEM_ID, state: str = "idea"):
    from simplicio_factory.contracts import Item

    return Item(id=item_id, brand=BRAND_ID, state=state)


def json_store(root: Path):
    from simplicio_factory.contracts.json_store import JsonStore

    return JsonStore(root)


class CountingRenderer:
    """Envolve um Renderer e conta as chamadas (o render real não roda nos testes unitários)."""

    def __init__(self, inner) -> None:
        self.inner = inner
        self.calls: list[tuple[str, bool]] = []

    def render(self, contract_path, preview):
        self.calls.append((str(contract_path), preview))
        return self.inner.render(contract_path, preview=preview)


def stub_renderer(tmp_path: Path) -> CountingRenderer:
    from simplicio_factory.testkit import StubRenderer

    return CountingRenderer(StubRenderer(tmp_path / "renders"))


def make_stage(tmp_path: Path, renderer=None, draft=None, brand=None):
    """Estágio com um Draft no dicionário de drafts (o `make` real lê de SIMPLICIO_FACTORY_HOME)."""
    draft = draft or load_draft()
    return stage_module().StudioStage(
        brand=brand or load_brand(),
        renderer=renderer if renderer is not None else stub_renderer(tmp_path),
        drafts={draft.item_id: draft},
        work_dir=tmp_path / "items",
    )


def run_cli(fn, argv: list[str]) -> tuple[int, str, str]:
    """Roda um handler de CLI e devolve (código, stdout, stderr); SystemExit do argparse vira código."""
    import contextlib
    import io

    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = fn(argv)
        except SystemExit as exc:
            code = exc.code if isinstance(exc.code, int) else 1
    return code, out.getvalue(), err.getvalue()
