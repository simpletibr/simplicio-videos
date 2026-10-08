"""schemas/factory/board.schema.json (#86, épico #81): gerado por `make factory-schema`, Draft 2020-12, rejeita o fora do contrato."""

from __future__ import annotations

import copy
import json
import subprocess
import sys

import jsonschema

from tests.factory.plugins.board._fixtures import (
    ITEM_ID,
    ROOT,
    SCHEMA,
    carregar_validador,
    home_de,
    salvar_item,
    service_module,
)


def test_schema_commitado_e_draft_2020_12_com_titulo_do_quadro():
    assert SCHEMA.is_file(), "schemas/factory/board.schema.json ausente: gerado pelo make factory-schema (#86)"
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))

    jsonschema.Draft202012Validator.check_schema(schema)
    assert schema["title"] == "simplicio.board/v1"


def test_schema_commitado_igual_ao_que_make_factory_schema_grava(tmp_path):
    committed = SCHEMA.read_bytes()
    item_saida = tmp_path / "item.schema.json"

    subprocess.run(
        ["make", "-s", "factory-schema", f"PYTHON={sys.executable}", f"FACTORY_SCHEMA_OUT={item_saida}"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    gerado = tmp_path / "board.schema.json"
    assert gerado.is_file(), (
        "make factory-schema não gravou board.schema.json ao lado do item (gerador da #86 pendente)"
    )
    assert gerado.read_bytes() == committed


def test_quadro_real_valida_e_card_fora_do_contrato_e_rejeitado(tmp_path):
    home = home_de(tmp_path)
    salvar_item(home, "rendered", review="approved", item_id=ITEM_ID)
    quadro = service_module().listar(home)
    validador = carregar_validador()
    assert list(validador.iter_errors(quadro)) == []

    estado_invalido = copy.deepcopy(quadro)
    card = next(c for col in estado_invalido["columns"] for c in col["cards"])
    card["state"] = "publicado"
    assert list(validador.iter_errors(estado_invalido)), "estado fora da lista de estados deveria ser rejeitado"

    coluna_invalida = copy.deepcopy(quadro)
    coluna_invalida["columns"][0]["id"] = "coluna-inventada"
    assert list(validador.iter_errors(coluna_invalida)), "coluna fora das oito chaves deveria ser rejeitada"
