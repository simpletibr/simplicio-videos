"""Asset anexado no studio (#87, épico #81): a mídia do `media attach` entra no contrato como asset opcional.

Sem mídia, a saída do composer não muda (os goldens continuam os mesmos). Com mídia, o contrato é determinístico, passa
no validador do motor e o render confere o sha256 do recibo antes de copiar a mídia para assets/.
"""

from __future__ import annotations

import hashlib
import json
import shutil

import pytest
import yaml

from tests.factory.plugins.media._attach_fixtures import (
    ARQUIVO_NOME,
    CONTEUDO,
    MEDIA_ID,
    RECIBO_SCHEMA,
    arquivo_gerado,
    attach,
    escreve_brand,
    grava_generating,
    prompt_file,
)
from tests.factory.plugins.media._fixtures import ITEM_ID, ambiente
from tests.factory.plugins.studio._studio import (
    FIXTURES,
    GOLDEN,
    composer_module,
    draft_with,
    json_store,
    load_brand,
    load_draft,
    make_item,
    make_stage,
    stage_module,
    stub_renderer,
)

MIDIA = "midia.mp4"
ASSET = {"arquivo": f"assets/{MIDIA}", "destino": f"assets/{MIDIA}"}


def _compose(midia: str | None = None) -> str:
    if midia is None:
        return composer_module().compose_contract(load_draft(), load_brand())
    return composer_module().compose_contract(load_draft(), load_brand(), midia=midia)


def _grava_recibo(pasta, nome: str, conteudo: bytes) -> None:
    """Pasta do item com media/<nome> e media.json no formato do recibo (o mesmo que `media attach` grava)."""
    (pasta / "media").mkdir(parents=True, exist_ok=True)
    (pasta / "media" / nome).write_bytes(conteudo)
    recibo = {
        "schema": RECIBO_SCHEMA,
        "arquivo": nome,
        "sha256": hashlib.sha256(conteudo).hexdigest(),
        "origem": "real-oficial",
        "media_id": MEDIA_ID,
        "estimate_ref": "est_01HZREALOFICIAL0001",
        "credits": 120,
        "confirmed_by": "Wesley",
        "prompt_sha256": "0" * 64,
    }
    (pasta / "media.json").write_text(
        json.dumps(recibo, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# ---------------------------------------------------------------- composer


def test_sem_midia_o_contrato_nao_tem_assets_e_segue_o_golden():
    texto = _compose()

    assert "assets" not in yaml.safe_load(texto)
    assert texto.encode("utf-8") == GOLDEN.read_bytes()


def test_com_midia_ela_entra_como_asset_do_contrato():
    texto = _compose(midia=MIDIA)

    assert yaml.safe_load(texto)["assets"] == [ASSET]


def test_com_midia_os_bytes_sao_iguais_em_duas_execucoes():
    assert _compose(midia=MIDIA).encode("utf-8") == _compose(midia=MIDIA).encode(
        "utf-8"
    )


def test_com_midia_o_contrato_passa_no_validador_do_motor(tmp_path):
    from simplicio_video.contract import load, validate

    pasta = tmp_path / "item"
    (pasta / "assets").mkdir(parents=True)
    (pasta / "contract.yaml").write_text(_compose(midia=MIDIA), encoding="utf-8")
    shutil.copy(FIXTURES / "logo.svg", pasta / "assets" / "logo.svg")
    (pasta / "assets" / MIDIA).write_bytes(CONTEUDO)

    report = validate(load(pasta / "contract.yaml"))

    assert report.errors == []
    assert report.ok


@pytest.mark.parametrize("midia", ["../fora.mp4", "pasta/midia.mp4", ""])
def test_midia_que_nao_e_so_um_nome_de_arquivo_e_recusada(midia):
    with pytest.raises(ValueError, match="nome de arquivo"):
        _compose(midia=midia)


def test_midia_com_o_nome_do_logo_e_recusada_para_nao_sobrescrever_a_marca():
    with pytest.raises(ValueError, match="logo"):
        _compose(midia="logo.svg")


# ---------------------------------------------------------------- stage: copia e confere o hash


def test_stage_copia_a_midia_para_assets_e_o_contrato_a_referencia(tmp_path):
    store = json_store(tmp_path / "factory")
    item = make_item()
    store.save_item(item)
    pasta = tmp_path / "items" / item.id
    _grava_recibo(pasta, MIDIA, CONTEUDO)

    make_stage(tmp_path).run(item, store)

    assert (pasta / "assets" / MIDIA).read_bytes() == CONTEUDO
    contrato = yaml.safe_load((pasta / "contract.yaml").read_text(encoding="utf-8"))
    assert contrato["assets"] == [ASSET]


def test_stage_recusa_midia_alterada_depois_do_attach_sem_renderizar(tmp_path):
    store = json_store(tmp_path / "factory")
    item = make_item()
    store.save_item(item)
    pasta = tmp_path / "items" / item.id
    _grava_recibo(pasta, MIDIA, CONTEUDO)
    (pasta / "media" / MIDIA).write_bytes(b"ALTERADO DEPOIS DO ATTACH")
    renderer = stub_renderer(tmp_path)

    with pytest.raises(ValueError, match="alterada"):
        make_stage(tmp_path, renderer=renderer).run(item, store)

    assert renderer.calls == []
    assert store.get_item(item.id).state == "idea"


def test_stage_sem_recibo_nao_copia_midia_nenhuma(tmp_path):
    store = json_store(tmp_path / "factory")
    item = make_item()
    store.save_item(item)

    make_stage(tmp_path).run(item, store)

    pasta = tmp_path / "items" / item.id
    assert not (pasta / "assets" / MIDIA).exists()
    assert "assets" not in yaml.safe_load(
        (pasta / "contract.yaml").read_text(encoding="utf-8")
    )


# ---------------------------------------------------------------- ponta a ponta: attach e render


def test_attach_e_render_usam_o_mesmo_recibo_e_o_contrato_valida(monkeypatch, tmp_path):
    from simplicio_video.contract import load, validate

    home, _ = ambiente(monkeypatch, tmp_path)
    escreve_brand(home)
    grava_generating(home)
    code, _, err = attach(
        ITEM_ID,
        str(arquivo_gerado(tmp_path)),
        "--source",
        "real-oficial",
        "--media-id",
        MEDIA_ID,
        "--prompt-file",
        str(prompt_file(tmp_path)),
    )
    assert code == 0, err
    store = json_store(home)
    stage = stage_module().StudioStage(
        brand=load_brand(),
        renderer=stub_renderer(tmp_path),
        drafts={ITEM_ID: draft_with(item_id=ITEM_ID)},
        work_dir=home / "studio",
    )

    stage.run(store.get_item(ITEM_ID), store)

    pasta = home / "studio" / ITEM_ID
    assert store.get_item(ITEM_ID).state == "rendered"
    assert (pasta / "assets" / ARQUIVO_NOME).read_bytes() == CONTEUDO
    contrato = yaml.safe_load((pasta / "contract.yaml").read_text(encoding="utf-8"))
    assert contrato["assets"] == [
        {"arquivo": f"assets/{ARQUIVO_NOME}", "destino": f"assets/{ARQUIVO_NOME}"}
    ]
    assert validate(load(pasta / "contract.yaml")).errors == []
