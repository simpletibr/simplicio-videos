"""content_hash do studio (#16): sha256 sobre contract.yaml, o Draft (JSON canônico) e os bytes de assets/.

Cada parte entra com nome e tamanho (prefixo de 8 bytes), então partes diferentes não se confundem.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from pathlib import Path


def _parte(h, nome: bytes, dados: bytes) -> None:
    h.update(len(nome).to_bytes(8, "big"))
    h.update(nome)
    h.update(len(dados).to_bytes(8, "big"))
    h.update(dados)


def _draft_json(draft) -> bytes:
    dados = dataclasses.asdict(draft) if dataclasses.is_dataclass(draft) else dict(draft)
    return json.dumps(dados, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def content_hash(contract_path, draft) -> str:
    contrato = Path(contract_path)
    h = hashlib.sha256()
    _parte(h, b"contract.yaml", contrato.read_bytes())
    _parte(h, b"draft.json", _draft_json(draft))
    assets = contrato.parent / "assets"
    if assets.is_dir():
        for arquivo in sorted(p for p in assets.rglob("*") if p.is_file()):
            _parte(h, b"assets/" + arquivo.relative_to(assets).as_posix().encode("utf-8"), arquivo.read_bytes())
    return h.hexdigest()
