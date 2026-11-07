"""File and JSON helpers shared by the whole package: one sha256 of a file and one canonical JSON.

Standard library only, and nothing else of the package is imported: any module (even a leaf one) may use it.
The copies that exist today in openverse, social, swap, voice, shorts, download, moneyprinter, doctor_trilhas, contract,
busca and installer move here one by one (U05); this module only adds the interface.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

BLOCK = 1 << 20  # sha256_file reads 1 MiB at a time: a big MP4 is never held in memory


def sha256_file(path: Path | str, *, limit: int | None = None) -> str:
    """Hex sha256 of the bytes of `path`, streamed in 1 MiB blocks.

    An OSError (missing file, a folder, permissions) propagates as it is. With `limit` (bytes), a file with more than
    `limit` bytes raises ValueError (so does a negative `limit`), and no more than `limit + 1` bytes are ever hashed:
    a huge file is refused, it never gets a digest of its first bytes. A file of exactly `limit` bytes is fine.
    """
    if limit is not None and limit < 0:
        raise ValueError(f"limit negativo: {limit}")
    h = hashlib.sha256()
    total = 0
    with open(path, "rb") as f:
        while True:
            want = BLOCK if limit is None else min(BLOCK, limit + 1 - total)
            block = f.read(want)
            if not block:
                break
            total += len(block)
            if limit is not None and total > limit:
                raise ValueError(f"{path}: mais de {limit} bytes")
            h.update(block)
    return h.hexdigest()


def canonical_json(obj: Any) -> str:
    """The one canonical text of a JSON value: sorted keys, no spaces, non-ASCII kept as it is (never `\\uXXXX`).

    Hashes of contracts, plans and caches are taken over this exact string: a different separator changes every digest.
    """
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
