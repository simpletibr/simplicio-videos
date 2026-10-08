"""StudioStage (#16): estágio `studio` sob o contrato de estágio do kernel.

Draft -> contract.yaml (composer) -> render (Renderer) -> rendered. Cada mudança de estado passa por `transition()`.
Estado do estúdio por item: `<work_dir>/<item_id>/studio.json` (content_hash, production, estado por estágio).
O kernel guarda só o estado do item (JsonStore); este módulo não altera o schema dele.

Idempotente por (item_id, stage): item já `rendered` é devolvido sem re-render nem evento novo.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from simplicio_factory.contracts import Brand, Draft, Renderer, Stage, Store, transition
from simplicio_factory.plugins.media import receipt
from simplicio_factory.plugins.studio.composer import compose_contract
from simplicio_factory.plugins.studio.hashing import content_hash

NAME = "studio"
ESTADO_ARQUIVO = "studio.json"
CONTRATO_ARQUIVO = "contract.yaml"


class StudioStage(Stage):
    name = NAME

    def __init__(self, brand: Brand, renderer: Renderer, drafts: dict[str, Draft], work_dir: Path | str) -> None:
        self.brand = brand
        self.renderer = renderer
        self.drafts = drafts
        self.work_dir = Path(work_dir)

    def pasta(self, item_id: str) -> Path:
        return self.work_dir / item_id

    def run(self, item, store: Store) -> None:
        if item.state == "rendered":
            return
        draft = self._draft(item.id)
        contrato = self._materializar(self.pasta(item.id), draft)  # claim guard: falha antes de qualquer transição
        if item.state == "idea":
            transition(item, "drafted", store)
        transition(item, "rendering", store)
        try:
            resultado = self.renderer.render(str(contrato), preview=False)
        except Exception:
            transition(item, "failed", store)
            raise
        self._gravar_estado(item.id, content_hash(contrato, draft), resultado.mp4_path, resultado.content_hash)
        transition(item, "rendered", store)

    def previa(self, item_id: str):
        """Renderiza a prévia 540x960 com marca d'água. Não muda o estado do item."""
        draft = self._draft(item_id)
        contrato = self._materializar(self.pasta(item_id) / "preview", draft, preview=True)
        return self.renderer.render(str(contrato), preview=True)

    def _draft(self, item_id: str) -> Draft:
        if item_id not in self.drafts:
            raise LookupError(f"sem Draft para o item {item_id}")
        return self.drafts[item_id]

    def _materializar(self, pasta: Path, draft: Draft, preview: bool = False) -> Path:
        # Mídia anexada pelo `media attach` (#87): o recibo fica na pasta do item, não na da prévia.
        recibo = receipt.ler(self.pasta(draft.item_id))
        texto = compose_contract(draft, self.brand, preview=preview, midia=recibo["arquivo"] if recibo else None)
        pasta.mkdir(parents=True, exist_ok=True)
        if self.brand.logo:
            (pasta / "assets").mkdir(exist_ok=True)
            shutil.copy2(self.brand.logo, pasta / "assets" / Path(self.brand.logo).name)
        if recibo:
            receipt.copia_verificada(self.pasta(draft.item_id), recibo, pasta / "assets")  # confere o sha256 antes do render
        contrato = pasta / CONTRATO_ARQUIVO
        _escrever(contrato, texto)
        return contrato

    def _gravar_estado(self, item_id: str, digest: str, mp4: str, render_hash: str) -> None:
        estado = {
            "content_hash": digest,
            "production": {"route": "deterministic", "steps": []},
            "stages": {NAME: {"state": "rendered", "mp4": mp4, "render_sha256": render_hash}},
        }
        _escrever(self.pasta(item_id) / ESTADO_ARQUIVO, json.dumps(estado, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def _escrever(destino: Path, texto: str) -> None:
    tmp = destino.with_name(destino.name + ".tmp")
    tmp.write_text(texto, encoding="utf-8")
    os.replace(tmp, destino)
