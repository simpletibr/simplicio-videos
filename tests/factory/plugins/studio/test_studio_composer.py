"""Composer determinístico (#16): mesmo Draft + brand = mesmos bytes; cores, logo, fatos e preset 9:16 (<= 20 s)."""

from __future__ import annotations

import copy
from dataclasses import replace

import pytest
import yaml

from tests.factory.plugins.studio._studio import composer_module, draft_with, load_brand, load_draft


def _compose(draft=None, brand=None, **kwargs) -> str:
    return composer_module().compose_contract(draft or load_draft(), brand or load_brand(), **kwargs)


def test_mesma_entrada_gera_os_mesmos_bytes():
    assert _compose().encode("utf-8") == _compose().encode("utf-8")


def test_objetos_copiados_geram_os_mesmos_bytes():
    assert _compose(copy.deepcopy(load_draft()), copy.deepcopy(load_brand())) == _compose()


def test_ordem_das_chaves_da_marca_nao_muda_os_bytes():
    brand = load_brand()
    reordered = replace(brand, colors=dict(reversed(list(brand.colors.items()))), facts=dict(reversed(list(brand.facts.items()))))

    assert _compose(brand=reordered) == _compose()


def test_usa_cores_da_marca_logo_e_fatos():
    text = _compose()
    data = yaml.safe_load(text)

    for hex_value in load_brand().colors.values():
        assert hex_value in text
    assert data["marca"]["logo"]["arquivo"] == "assets/logo.svg"
    assert data["marca"]["logo"]["destino"] == "assets/logo.svg"
    assert "Um sorriso mais leve" in text


def test_preset_padrao_e_9_16_1080x1920():
    formato = yaml.safe_load(_compose())["formato"]

    assert formato["aspect"] == "9:16"
    assert (formato["width"], formato["height"]) == (1080, 1920)


def test_preview_renderiza_em_540x960():
    formato = yaml.safe_load(_compose(preview=True))["formato"]

    assert (formato["width"], formato["height"]) == (540, 960)


def test_duracao_acima_de_20_s_e_rejeitada():
    with pytest.raises(ValueError, match="20 s"):
        _compose(draft_with(duration_s=25))


def test_duracao_do_formato_bate_com_a_soma_das_cenas():
    data = yaml.safe_load(_compose())

    assert sum(c["duracao_s"] for c in data["cenas"]) == data["formato"]["duracao_s"] == load_draft().duration_s
