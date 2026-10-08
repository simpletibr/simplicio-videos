"""Helpers dos testes do `media attach` e do `generate start` (#87, épico #81), e do asset anexado do studio.

Importados explicitamente, como tests/factory/plugins/media/_fixtures.py. Não há conftest.py em subpasta de tests (#43).
Os imports de `simplicio_factory` e de `simplicio_video` ficam dentro das funções: enquanto a fase 2 não existe, cada
teste falha no próprio corpo, e não a coleta da suíte inteira.

Interface que a fase 2 precisa cumprir (usada por estes testes):
- `plugins/media/cli.py`: `media_cmd(argv) -> int` (subcomando `attach`), `generate_cmd` com `start`, e o manifesto
  `plugins/media/plugin.json` com o comando `media` (handler `simplicio_factory.plugins.media.cli:media_cmd`).
- Pasta do item: `$SIMPLICIO_FACTORY_HOME/studio/<item_id>/` (a mesma do StudioStage). Dentro dela: `media/<nome>` (cópia
  imutável) e `media.json` (recibo, schema `simplicio.media-receipt/v1`).
- Brand: `$SIMPLICIO_FACTORY_HOME/brand.json` (ou `--brand`), usado pelo claim guard do prompt.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from tests.factory.plugins.media._fixtures import (
    AGORA,
    ESTIMATIVA,
    ITEM_ID,
    gera,
    grava_item,
    le_item,
    run_cli,
)

MEDIA_ID = "med_01HZREALOFICIAL0001"
ARQUIVO_NOME = "video-real-oficial.mp4"
CONTEUDO = b"MP4-DE-TESTE-REAL-OFICIAL"
PROMPT = "Clínica sorridente, ambiente acolhedor, personagem sintético."
FATOS_MARCA = {
    "experiencia": "15 anos de atendimento",
    "sessao": "sessão de 45 minutos",
}
RECIBO_SCHEMA = "simplicio.media-receipt/v1"


def sha256(dados: bytes) -> str:
    return hashlib.sha256(dados).hexdigest()


def passo_aprovado(credits: int = 120, by: str = "Wesley") -> dict:
    """Passo ai_media como `generate approve` o deixa: com confirmed_by e confirmed_at."""
    return {
        "kind": "ai_media",
        "provider": "real-oficial",
        "estimate_ref": ESTIMATIVA,
        "credits": credits,
        "confirmed_by": by,
        "confirmed_at": AGORA.isoformat(),
    }


def pasta_item(home: Path, item_id: str = ITEM_ID) -> Path:
    """Pasta do item no studio: o que `media attach` e o StudioStage compartilham."""
    return Path(home) / "studio" / item_id


def grava_generating(
    home: Path,
    *,
    state: str = "generating",
    steps=None,
    route: str = "ai_assisted",
    item_id: str = ITEM_ID,
):
    """Item na rota ai_assisted com passo aprovado (padrão), no estado dado."""
    return grava_item(
        home,
        state=state,
        route=route,
        steps=[passo_aprovado()] if steps is None else steps,
        item_id=item_id,
    )


def escreve_brand(home: Path, facts: dict | None = None) -> Path:
    """brand.json do workspace de teste, com fatos que o prompt pode citar sem violar o claim guard."""
    home.mkdir(parents=True, exist_ok=True)
    caminho = home / "brand.json"
    dados = {
        "name": "Clínica Exemplo",
        "colors": {"primary": "#0b5d3b", "accent": "#f2b705", "ink": "#1d1d1b"},
        "logo": None,
        "facts": dict(FATOS_MARCA) if facts is None else facts,
    }
    caminho.write_text(
        json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return caminho


def arquivo_gerado(
    tmp_path: Path, nome: str = ARQUIVO_NOME, conteudo: bytes = CONTEUDO
) -> Path:
    """Arquivo que o usuário baixou do Real Oficial (fora do repositório, em tmp_path)."""
    caminho = tmp_path / "baixados" / nome
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_bytes(conteudo)
    return caminho


def prompt_file(tmp_path: Path, texto: str = PROMPT, nome: str = "prompt.txt") -> Path:
    caminho = tmp_path / "prompts" / nome
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(texto, encoding="utf-8")
    return caminho


def attach(*argv: str) -> tuple[int, str, str]:
    """Roda `simplicio-video media attach ...` pela CLI principal (despacho de plugin), como o usuário faz."""
    from simplicio_video import cli as principal

    return run_cli(principal.main, ["media", "attach", *argv])


def start(item_id: str = ITEM_ID) -> tuple[int, str, str]:
    """Roda `generate start` pelo handler do plugin media."""
    return gera("start", item_id)


def estado(home: Path, item_id: str = ITEM_ID) -> str:
    return le_item(home, item_id).state
