"""media attach (#87, épico #81): anexa o arquivo gerado pelo Real Oficial ao item que está em `generating`.

    simplicio-video media attach ITEM ARQUIVO --source real-oficial --media-id ID --prompt-file ARQ [--brand BRAND.JSON]

Ordem: item em generating; passo ai_media aprovado (confirmed_by); arquivo e prompt existentes; claim guard do prompt
contra os fatos do brand.json (sem preço, número ou promessa inventados); sha256 do arquivo; cópia em
<item>/media/<nome>; recibo <item>/media.json; evento media.attached; transição generating -> generated.
Sem rede, sem LLM, sem gasto: o arquivo já foi baixado pelo usuário.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from simplicio_factory.contracts import Brand, Draft
from simplicio_factory.contracts.transitions import transition
from simplicio_factory.plugins.media import receipt

ORIGEM = "real-oficial"
EVENTO = "media.attached"
PASSO = "ai_media"
ESTADO_ESPERADO = "generating"


class AttachError(Exception):
    """Attach recusado. A mensagem diz o que faltou; nada foi gravado quando ela sai."""


def ultimo_passo_ai(item) -> dict | None:
    passos = [
        p
        for p in (item.production or {}).get("steps") or []
        if isinstance(p, dict) and p.get("kind") == PASSO
    ]
    return passos[-1] if passos else None


def ler_marca(caminho: Path) -> Brand:
    """Brand com os fatos para o claim guard. Sem brand.json o attach falha: não há como conferir o prompt."""
    if not caminho.is_file():
        raise AttachError(
            f"brand não encontrado: {caminho} (use --brand ou SIMPLICIO_FACTORY_HOME/brand.json; "
            "o claim guard do prompt precisa dos fatos)"
        )
    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
        return Brand(
            name=str(dados["name"]),
            colors=dict(dados.get("colors") or {}),
            logo=None,
            facts=dict(dados.get("facts") or {}),
        )
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise AttachError(f"brand inválido em {caminho}: {exc}") from None


def confere_prompt(texto: str, marca: Brand, item_id: str) -> None:
    """Claim guard do studio aplicado ao prompt: o prompt entra como ideia de um Draft sem claims."""
    from simplicio_factory.plugins.studio.claims import ClaimError, check_claims

    rascunho = Draft(
        item_id=item_id, idea=texto, facts={}, claims=[], platform="9:16", duration_s=1
    )
    try:
        check_claims(rascunho, marca)
    except ClaimError as exc:
        raise AttachError(f"prompt recusado pelo claim guard: {exc}") from None


def anexa(
    store,
    *,
    item_id: str,
    arquivo: Path,
    origem: str,
    media_id: str,
    prompt_file: Path,
    brand_path: Path,
) -> dict:
    """Anexa o arquivo ao item e devolve o recibo gravado. Qualquer recusa levanta AttachError antes de gravar."""
    item = store.get_item(item_id)
    if item is None:
        raise AttachError(f"item não encontrado: {item_id}")
    if item.state != ESTADO_ESPERADO:
        raise AttachError(
            f"{item_id}: media attach exige o estado generating (estado atual: {item.state})"
        )
    passo = ultimo_passo_ai(item)
    if passo is None or not passo.get("confirmed_by"):
        raise AttachError(
            f"{item_id}: sem aprovação registrada (passo ai_media com confirmed_by): rode generate approve antes"
        )
    if not arquivo.is_file():
        raise AttachError(f"arquivo não encontrado: {arquivo}")
    if not prompt_file.is_file():
        raise AttachError(f"prompt não encontrado: {prompt_file}")
    prompt_bytes = prompt_file.read_bytes()
    try:
        texto = prompt_bytes.decode("utf-8")
    except UnicodeDecodeError:
        raise AttachError(f"prompt não é UTF-8: {prompt_file}") from None
    if not texto.strip():
        raise AttachError(f"prompt vazio: {prompt_file}")
    confere_prompt(texto, ler_marca(brand_path), item_id)

    pasta = store.root / "studio" / item_id
    destino = pasta / receipt.PASTA_MIDIA / arquivo.name
    digest = receipt.sha256_de(arquivo)
    destino.parent.mkdir(parents=True, exist_ok=True)
    if destino.resolve() != arquivo.resolve():
        shutil.copyfile(arquivo, destino)
    if receipt.sha256_de(destino) != digest:
        destino.unlink()
        raise AttachError(
            "a cópia não confere com o arquivo original; nada foi gravado"
        )

    recibo = {
        "schema": receipt.SCHEMA,
        "arquivo": arquivo.name,
        "sha256": digest,
        "origem": origem,
        "media_id": media_id,
        "estimate_ref": passo.get("estimate_ref"),
        "credits": passo.get("credits"),
        "confirmed_by": passo["confirmed_by"],
        "prompt_sha256": receipt.sha256_bytes(prompt_bytes),
    }
    receipt.gravar(pasta, recibo)
    store.append_event(
        EVENTO,
        item_id,
        {
            "media_id": media_id,
            "origem": origem,
            "arquivo": arquivo.name,
            "sha256": digest,
        },
    )
    transition(item, "generated", store)
    return recibo
