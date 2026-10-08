"""Comandos do studio (#16): `make <item>`, `make preview <item>`, `draft show <item>`, cada um com --help e exemplo."""

from __future__ import annotations

import json

from pathlib import Path

from tests.factory.plugins.studio._studio import cli_module, run_cli

MANIFEST = Path(__file__).resolve().parents[4] / "src" / "simplicio_factory" / "plugins" / "studio" / "plugin.json"


def test_make_help_mostra_exemplo():
    code, out, _ = run_cli(cli_module().make_cmd, ["--help"])

    assert code == 0
    assert "Exemplo" in out
    assert "simplicio-video make" in out


def test_make_preview_help_mostra_exemplo_e_540x960():
    code, out, _ = run_cli(cli_module().make_cmd, ["preview", "--help"])

    assert code == 0
    assert "simplicio-video make preview" in out
    assert "540x960" in out


def test_draft_help_mostra_exemplo():
    code, out, _ = run_cli(cli_module().draft_cmd, ["--help"])

    assert code == 0
    assert "Exemplo" in out
    assert "simplicio-video draft show" in out


def test_draft_show_help_mostra_exemplo():
    code, out, _ = run_cli(cli_module().draft_cmd, ["show", "--help"])

    assert code == 0
    assert "simplicio-video draft show" in out


def test_draft_show_de_item_inexistente_falha_com_o_id(tmp_path, monkeypatch):
    monkeypatch.setenv("SIMPLICIO_FACTORY_HOME", str(tmp_path / "home"))
    missing = "itm_01HZNAOEXISTE000000000000"

    code, out, err = run_cli(cli_module().draft_cmd, ["show", missing])

    assert code != 0
    assert missing in out + err


def test_manifesto_aponta_para_handlers_existentes():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    cli = cli_module()
    names = {c["name"]: c["handler"] for c in manifest["commands"]}

    assert set(names) == {"make", "draft"}
    assert names["make"] == "simplicio_factory.plugins.studio.cli:make_cmd"
    assert names["draft"] == "simplicio_factory.plugins.studio.cli:draft_cmd"
    assert callable(cli.make_cmd)
    assert callable(cli.draft_cmd)
