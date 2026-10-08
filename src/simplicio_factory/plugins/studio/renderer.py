"""Renderer real do studio (#16): delega ao motor, sem mecanismo de render novo.

- preview=False: `simplicio_video.render.render_local` (render de entrega do contrato).
- preview=True: `simplicio_video.render.render_preview` (prévia com marca d'água, a função de prévia já existente).
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

from simplicio_factory.contracts.models import RenderResult


def _log(mensagem: str) -> None:
    print(mensagem, file=sys.stderr)


class EngineRenderer:
    def __init__(self, out_dir: Path | str) -> None:
        self.out_dir = Path(out_dir)

    def render(self, contract_path: str, preview: bool) -> RenderResult:
        from simplicio_video import contract as motor_contract
        from simplicio_video import render as motor_render
        from simplicio_video import voice as motor_voice

        contrato = motor_contract.load(contract_path)
        if contrato.data["voz"].get("habilitada", True) and contrato.lines() and motor_contract.load_lock(contrato) is None:
            motor_voice.run(contrato, log=_log)  # mesmo passo de `simplicio-video run`: voz antes do render
            contrato = motor_contract.load(contract_path)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        nome = Path(contract_path).parent.name + ("-previa" if preview else "")
        destino = self.out_dir / f"{nome}.mp4"
        if preview:
            motor_render.render_preview(contrato, out=destino, log=_log)
        else:
            motor_render.render_local(contrato, out=destino, log=_log)  # o manifesto guarda o caminho relativo ao contrato
        digest = hashlib.sha256(destino.read_bytes()).hexdigest()
        return RenderResult(mp4_path=str(destino.resolve()), content_hash=digest)
