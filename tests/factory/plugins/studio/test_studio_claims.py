"""Claim guard (#16): número, preço, percentual ou promessa em Draft.idea/claims precisa estar em Brand.facts."""

from __future__ import annotations

import pytest

from tests.factory.plugins.studio._studio import (
    claims_module,
    composer_module,
    draft_with,
    load_brand,
    load_draft,
)


def test_preco_inventado_e_rejeitado_com_o_trecho():
    draft = draft_with(idea="Clareamento por R$ 99 nesta semana.")

    with pytest.raises(claims_module().ClaimError) as exc:
        claims_module().check_claims(draft, load_brand())

    assert "R$ 99" in str(exc.value)


def test_percentual_inventado_em_claims_e_rejeitado():
    draft = draft_with(claims=["30% de desconto no primeiro mês."])

    with pytest.raises(claims_module().ClaimError, match="30%"):
        claims_module().check_claims(draft, load_brand())


def test_promessa_inventada_e_rejeitada():
    draft = draft_with(claims=["Clareamento grátis para todos."])

    with pytest.raises(claims_module().ClaimError, match="grátis"):
        claims_module().check_claims(draft, load_brand())


def test_fatos_da_marca_passam_no_guard():
    claims_module().check_claims(load_draft(), load_brand())


def test_composer_tambem_rejeita_preco_inventado():
    draft = draft_with(idea="Clareamento por R$ 99 nesta semana.")

    with pytest.raises(claims_module().ClaimError):
        composer_module().compose_contract(draft, load_brand())
