"""StubRenderer: grava bytes determinísticos derivados do contrato. Não chama HyperFrames."""

from __future__ import annotations

import hashlib
from pathlib import Path

from simplicio_factory.contracts.models import RenderResult


class StubRenderer:
    def __init__(self, out_dir: Path | str) -> None:
        self.out_dir = Path(out_dir)

    def render(self, contract_path: str, preview: bool) -> RenderResult:
        contract = Path(contract_path).read_bytes()
        digest = hashlib.sha256(contract).hexdigest()
        suffix = "-preview" if preview else ""
        self.out_dir.mkdir(parents=True, exist_ok=True)
        out = self.out_dir / f"{digest[:16]}{suffix}.mp4"
        header = b"STUB-MP4 preview=" + (b"1" if preview else b"0") + b"\n"
        out.write_bytes(header + contract)
        return RenderResult(mp4_path=str(out), content_hash=digest)
