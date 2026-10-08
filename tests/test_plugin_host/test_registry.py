"""Registro e manifesto de plugins (#32, M0a, fase 1: testes vermelhos).

Contrato: src/simplicio_factory/plugins/<id>/plugin.json, lido por registry.load_manifest; discover varre as pastas.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from simplicio_video.registry import ManifestError, commands_index, discover, load_manifest
from _host_fixtures import escreve_manifesto, manifesto  # noqa: F401 (fixtures do host de plugins)

ROOT = Path(__file__).resolve().parents[2]
PLUGINS_REAIS = ROOT / "src" / "simplicio_factory" / "plugins"


def test_load_manifest_aceita_manifesto_valido(tmp_path, escreve_manifesto, manifesto):  # noqa: F811 (fixture importada, redefinida como parâmetro)
    path = escreve_manifesto(tmp_path / "demo", manifesto(id="demo"))
    m = load_manifest(path)
    assert m.id == "demo"
    assert [c.name for c in m.commands] == ["fakecmd"]
    assert m.commands[0].handler == "pluginfake_hosttest:run"


def test_load_manifest_rejeita_sem_id(tmp_path, escreve_manifesto, manifesto):  # noqa: F811 (fixture importada, redefinida como parâmetro)
    dados = manifesto()
    del dados["id"]
    path = escreve_manifesto(tmp_path / "semid", dados)
    with pytest.raises(ManifestError, match="id"):
        load_manifest(path)


def test_load_manifest_rejeita_handler_sem_dois_pontos(tmp_path, escreve_manifesto, manifesto):  # noqa: F811 (fixture importada, redefinida como parâmetro)
    comandos = [{"name": "fakecmd", "handler": "pluginfake_hosttest.run", "help": "x", "example": "x"}]
    path = escreve_manifesto(tmp_path / "handler", manifesto(commands=comandos))
    with pytest.raises(ManifestError, match="handler"):
        load_manifest(path)


def test_discover_encontra_plugin_de_teste_e_ignora_pasta_sem_manifesto(tmp_path, escreve_manifesto, manifesto):  # noqa: F811 (fixture importada, redefinida como parâmetro)
    escreve_manifesto(tmp_path / "demo", manifesto(id="demo"))
    (tmp_path / "sem_manifesto").mkdir()
    achados = discover(tmp_path)
    assert [m.id for m in achados] == ["demo"]


# Fase 2 do #16 cria src/simplicio_factory/plugins/studio/plugin.json. Até lá este teste FALHA de propósito.
def test_manifesto_real_do_studio():
    path = PLUGINS_REAIS / "studio" / "plugin.json"
    assert path.is_file(), "studio/plugin.json ainda não existe (criado pela fase 2 do #16)"
    assert "studio" in [m.id for m in discover(PLUGINS_REAIS)]
    m = load_manifest(path)
    assert m.id == "studio"
    assert {"make", "draft"} <= {c.name for c in m.commands}


def test_commands_index_levanta_erro_em_nome_duplicado(tmp_path, escreve_manifesto, manifesto):  # noqa: F811 (fixture importada, redefinida como parâmetro)
    a = load_manifest(escreve_manifesto(tmp_path / "a", manifesto(id="a")))
    b = load_manifest(escreve_manifesto(tmp_path / "b", manifesto(id="b")))
    with pytest.raises(ManifestError, match="fakecmd"):
        commands_index([a, b])


def test_commands_index_indexa_nomes_unicos(tmp_path, escreve_manifesto, manifesto):  # noqa: F811 (fixture importada, redefinida como parâmetro)
    def com_comando(nome):
        return [{"name": nome, "handler": "pluginfake_hosttest:run", "help": "x", "example": "x"}]

    a = load_manifest(escreve_manifesto(tmp_path / "a", manifesto(id="a", commands=com_comando("alpha"))))
    b = load_manifest(escreve_manifesto(tmp_path / "b", manifesto(id="b", commands=com_comando("beta"))))
    assert set(commands_index([a, b])) == {"alpha", "beta"}
