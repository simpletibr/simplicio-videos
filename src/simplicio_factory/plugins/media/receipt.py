"""Recibo da mídia anexada (#87, épico #81): `<item>/media.json` e a cópia imutável em `<item>/media/<nome>`.

A pasta do item é a do studio: $SIMPLICIO_FACTORY_HOME/studio/<item_id>/ (a mesma de StudioStage.pasta). O recibo
guarda o sha256 do arquivo, a origem, o media_id, a referência da estimativa, o custo, quem aprovou e o sha256 do
prompt (o texto do prompt não é gravado). O studio chama `copia_verificada` na hora do render: se o arquivo mudou
desde o attach, o render não começa.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path

SCHEMA = "simplicio.media-receipt/v1"
RECIBO = "media.json"
PASTA_MIDIA = "media"


class ReceiptError(ValueError):
    """Recibo ausente, malformado ou com mídia alterada desde o attach."""


def sha256_de(caminho: Path) -> str:
    h = hashlib.sha256()
    with caminho.open("rb") as arquivo:
        for bloco in iter(lambda: arquivo.read(1024 * 1024), b""):
            h.update(bloco)
    return h.hexdigest()


def sha256_bytes(dados: bytes) -> str:
    return hashlib.sha256(dados).hexdigest()


def ler(pasta_item: Path) -> dict | None:
    """Recibo do item, ou None se nunca houve attach. Recibo malformado levanta ReceiptError."""
    caminho = pasta_item / RECIBO
    if not caminho.is_file():
        return None
    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ReceiptError(f"recibo ilegível em {caminho}: {exc}") from None
    if not isinstance(dados, dict) or dados.get("schema") != SCHEMA:
        raise ReceiptError(f"recibo em {caminho} não é do schema {SCHEMA}")
    arquivo = dados.get("arquivo")
    if not isinstance(arquivo, str) or not arquivo or Path(arquivo).name != arquivo:
        raise ReceiptError(
            f"recibo em {caminho}: 'arquivo' precisa ser só um nome de arquivo"
        )
    if not isinstance(dados.get("sha256"), str):
        raise ReceiptError(f"recibo em {caminho}: falta o sha256 do arquivo")
    return dados


def gravar(pasta_item: Path, recibo: dict) -> Path:
    """Grava o recibo de forma atômica (arquivo temporário e os replace)."""
    pasta_item.mkdir(parents=True, exist_ok=True)
    destino = pasta_item / RECIBO
    tmp = destino.with_name(destino.name + ".tmp")
    tmp.write_text(
        json.dumps(recibo, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(tmp, destino)
    return destino


def copia_verificada(pasta_item: Path, recibo: dict, assets_dir: Path) -> Path:
    """Confere o sha256 da mídia anexada e copia para assets_dir/<nome>. Mídia alterada levanta ReceiptError."""
    origem = pasta_item / PASTA_MIDIA / recibo["arquivo"]
    if not origem.is_file():
        raise ReceiptError(
            f"mídia anexada não encontrada: {origem} (rode media attach de novo)"
        )
    if sha256_de(origem) != recibo["sha256"]:
        raise ReceiptError(
            f"mídia anexada foi alterada depois do attach (sha256 não confere): {origem}"
        )
    assets_dir.mkdir(parents=True, exist_ok=True)
    destino = assets_dir / recibo["arquivo"]
    shutil.copyfile(origem, destino)
    return destino
