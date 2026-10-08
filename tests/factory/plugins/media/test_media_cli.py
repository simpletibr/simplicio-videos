"""Comandos do media (#85): `generate quote`, `generate approve` e `generate show`, com --help e exemplo."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from tests.factory.plugins.media._fixtures import (
    AGORA,
    ESTIMATIVA,
    ITEM_ID,
    OUTRO_ID,
    ambiente,
    com_terminal,
    escreve_policy,
    eventos,
    gera,
    grava_item,
    grava_quoted,
    le_item,
    passo_ai,
    sem_terminal,
)

MANIFEST = (
    Path(__file__).resolve().parents[4]
    / "src"
    / "simplicio_factory"
    / "plugins"
    / "media"
    / "plugin.json"
)


# ---------------------------------------------------------------- ajuda e registro


def test_generate_help_lista_os_subcomandos_e_exemplo(monkeypatch, tmp_path):
    ambiente(monkeypatch, tmp_path)

    code, out, _ = gera("--help")

    assert code == 0
    assert "Exemplo" in out
    assert "simplicio-video generate" in out
    for sub in ("quote", "approve", "show"):
        assert sub in out


def test_cada_subcomando_tem_help_com_exemplo(monkeypatch, tmp_path):
    ambiente(monkeypatch, tmp_path)

    for sub in ("quote", "approve", "show"):
        code, out, _ = gera(sub, "--help")
        assert code == 0, sub
        assert f"simplicio-video generate {sub}" in out, sub
        assert "Exemplo" in out, sub


def test_help_dos_subcomandos_cita_as_opcoes_novas(monkeypatch, tmp_path):
    ambiente(monkeypatch, tmp_path)

    _, quote, _ = gera("quote", "--help")
    _, approve, _ = gera("approve", "--help")
    _, show, _ = gera("show", "--help")

    for opcao in ("--provider", "--estimate-ref", "--credits", "--daily-cap"):
        assert opcao in quote, opcao
    for opcao in ("--by", "--yes", "--daily-cap"):
        assert opcao in approve, opcao
    assert "--json" in show


def test_generate_sem_subcomando_mostra_ajuda_e_falha(monkeypatch, tmp_path):
    ambiente(monkeypatch, tmp_path)

    code, out, err = gera()

    assert code == 2
    assert "quote" in out + err


def test_manifesto_declara_generate_com_handler_existente():
    from simplicio_factory.plugins.media import cli

    manifesto = json.loads(MANIFEST.read_text(encoding="utf-8"))

    assert manifesto["id"] == "media"
    assert [c["name"] for c in manifesto["commands"]] == ["generate"]
    assert (
        manifesto["commands"][0]["handler"]
        == "simplicio_factory.plugins.media.cli:generate_cmd"
    )
    assert callable(cli.generate_cmd)


def test_plugin_list_mostra_o_plugin_media(capsys):
    from simplicio_video import cli as principal

    codigo = principal.main(["plugin", "list"])

    assert codigo == 0
    linha = [
        ln for ln in capsys.readouterr().out.splitlines() if ln.startswith("media")
    ]
    assert linha and "generate" in linha[0]


def test_generate_e_despachado_pela_cli_principal(monkeypatch, tmp_path):
    from simplicio_video import cli as principal

    home, _ = ambiente(monkeypatch, tmp_path)
    grava_quoted(home)

    assert principal.main(["generate", "show", ITEM_ID]) == 0


# ---------------------------------------------------------------- generate quote


def test_quote_registra_o_passo_e_leva_a_quoted(monkeypatch, tmp_path):
    home, _ = ambiente(monkeypatch, tmp_path)
    grava_item(home, state="drafted")

    code, _, err = gera(
        "quote",
        ITEM_ID,
        "--provider",
        "real-oficial",
        "--estimate-ref",
        ESTIMATIVA,
        "--credits",
        "120",
    )

    assert code == 0, err
    item = le_item(home)
    assert item.state == "quoted"
    assert item.production["steps"] == [passo_ai(120)]


def test_quote_grava_evento_spend_quoted(monkeypatch, tmp_path):
    home, _ = ambiente(monkeypatch, tmp_path)
    grava_item(home, state="drafted")

    gera(
        "quote",
        ITEM_ID,
        "--provider",
        "real-oficial",
        "--estimate-ref",
        ESTIMATIVA,
        "--credits",
        "120",
    )

    eventos_quoted = eventos(home, "spend.quoted")
    assert len(eventos_quoted) == 1
    assert eventos_quoted[0].item_id == ITEM_ID
    assert eventos_quoted[0].data["credits"] == 120
    assert eventos_quoted[0].data["estimate_ref"] == ESTIMATIVA


def test_quote_na_rota_deterministica_recusa_sem_mudar_nada(monkeypatch, tmp_path):
    home, _ = ambiente(monkeypatch, tmp_path)
    grava_item(home, state="drafted", route="deterministic")

    code, _, err = gera(
        "quote",
        ITEM_ID,
        "--provider",
        "real-oficial",
        "--estimate-ref",
        ESTIMATIVA,
        "--credits",
        "120",
    )

    assert code == 1
    assert "ai_assisted" in err
    item = le_item(home)
    assert item.state == "drafted"
    assert item.production["steps"] == []
    assert eventos(home, "spend.quoted") == []


def test_quote_fora_de_drafted_recusa_sem_gravar_o_passo(monkeypatch, tmp_path):
    home, _ = ambiente(monkeypatch, tmp_path)
    grava_item(home, state="idea")

    code, _, _ = gera(
        "quote",
        ITEM_ID,
        "--provider",
        "real-oficial",
        "--estimate-ref",
        ESTIMATIVA,
        "--credits",
        "120",
    )

    assert code == 1
    item = le_item(home)
    assert item.state == "idea"
    assert item.production["steps"] == []
    assert eventos(home, "spend.quoted") == []


def test_quote_acima_de_media_credits_recusa(monkeypatch, tmp_path):
    home, _ = ambiente(monkeypatch, tmp_path, media_credits=100)
    grava_item(home, state="drafted")

    code, _, err = gera(
        "quote",
        ITEM_ID,
        "--provider",
        "real-oficial",
        "--estimate-ref",
        ESTIMATIVA,
        "--credits",
        "120",
    )

    assert code == 1
    assert "media_credits" in err
    assert le_item(home).state == "drafted"


def test_quote_acima_do_teto_diario_recusa(monkeypatch, tmp_path):
    home, _ = ambiente(monkeypatch, tmp_path)
    grava_item(home, state="drafted")

    code, _, err = gera(
        "quote",
        ITEM_ID,
        "--provider",
        "real-oficial",
        "--estimate-ref",
        ESTIMATIVA,
        "--credits",
        "120",
        "--daily-cap",
        "100",
    )

    assert code == 1
    assert "teto diário" in err
    assert le_item(home).state == "drafted"


def test_quote_sem_estimate_ref_falha_sem_gravar(monkeypatch, tmp_path):
    home, _ = ambiente(monkeypatch, tmp_path)
    grava_item(home, state="drafted")

    code, _, _ = gera(
        "quote", ITEM_ID, "--provider", "real-oficial", "--credits", "120"
    )

    assert code != 0
    assert le_item(home).state == "drafted"


def test_quote_com_credits_nao_positivo_falha(monkeypatch, tmp_path):
    home, _ = ambiente(monkeypatch, tmp_path)
    grava_item(home, state="drafted")

    code, _, _ = gera(
        "quote",
        ITEM_ID,
        "--provider",
        "real-oficial",
        "--estimate-ref",
        ESTIMATIVA,
        "--credits",
        "0",
    )

    assert code != 0
    assert le_item(home).state == "drafted"


def test_quote_com_provider_desconhecido_falha(monkeypatch, tmp_path):
    home, _ = ambiente(monkeypatch, tmp_path)
    grava_item(home, state="drafted")

    code, _, _ = gera(
        "quote",
        ITEM_ID,
        "--provider",
        "outro",
        "--estimate-ref",
        ESTIMATIVA,
        "--credits",
        "120",
    )

    assert code != 0
    assert le_item(home).state == "drafted"


# ---------------------------------------------------------------- generate approve


def test_approve_com_yes_leva_a_approved_e_preenche_a_confirmacao(
    monkeypatch, tmp_path
):
    home, _ = ambiente(monkeypatch, tmp_path)
    grava_quoted(home, credits=120)

    code, _, err = gera("approve", ITEM_ID, "--by", "Wesley", "--yes")

    assert code == 0, err
    item = le_item(home)
    assert item.state == "approved"
    passo = item.production["steps"][-1]
    assert passo["confirmed_by"] == "Wesley"
    assert datetime.fromisoformat(passo["confirmed_at"]) == AGORA


def test_approve_grava_evento_spend_approved(monkeypatch, tmp_path):
    home, _ = ambiente(monkeypatch, tmp_path)
    grava_quoted(home, credits=120)

    gera("approve", ITEM_ID, "--by", "Wesley", "--yes")

    aprovados = eventos(home, "spend.approved")
    assert len(aprovados) == 1
    assert aprovados[0].data["credits"] == 120
    assert aprovados[0].data["confirmed_by"] == "Wesley"


def test_approve_sem_yes_e_sem_terminal_falha_sem_aprovar(monkeypatch, tmp_path):
    home, _ = ambiente(monkeypatch, tmp_path)
    grava_quoted(home)
    sem_terminal(monkeypatch)

    code, _, err = gera("approve", ITEM_ID, "--by", "Wesley")

    assert code != 0
    assert "--yes" in err
    assert le_item(home).state == "quoted"
    assert eventos(home, "spend.approved") == []


def test_approve_com_terminal_e_resposta_s_aprova(monkeypatch, tmp_path):
    home, _ = ambiente(monkeypatch, tmp_path)
    grava_quoted(home)
    com_terminal(monkeypatch, "s")

    code, _, err = gera("approve", ITEM_ID, "--by", "Wesley")

    assert code == 0, err
    assert le_item(home).state == "approved"


def test_approve_com_terminal_e_resposta_n_nao_aprova(monkeypatch, tmp_path):
    home, _ = ambiente(monkeypatch, tmp_path)
    grava_quoted(home)
    com_terminal(monkeypatch, "n")

    code, _, _ = gera("approve", ITEM_ID, "--by", "Wesley")

    assert code != 0
    item = le_item(home)
    assert item.state == "quoted"
    assert "confirmed_by" not in item.production["steps"][-1]
    assert eventos(home, "spend.approved") == []


def test_approve_duas_vezes_e_idempotente_sem_evento_duplicado(monkeypatch, tmp_path):
    home, _ = ambiente(monkeypatch, tmp_path)
    grava_quoted(home)
    assert gera("approve", ITEM_ID, "--by", "Wesley", "--yes")[0] == 0
    sem_terminal(monkeypatch)

    code, _, err = gera("approve", ITEM_ID, "--by", "Outra Pessoa")

    assert code == 0, err
    item = le_item(home)
    assert item.state == "approved"
    assert item.production["steps"][-1]["confirmed_by"] == "Wesley"
    assert len(eventos(home, "spend.approved")) == 1


def test_approve_exige_by(monkeypatch, tmp_path):
    home, _ = ambiente(monkeypatch, tmp_path)
    grava_quoted(home)

    code, _, _ = gera("approve", ITEM_ID, "--yes")

    assert code != 0
    assert le_item(home).state == "quoted"
    assert eventos(home, "spend.approved") == []


def test_approve_com_by_so_de_espacos_recusa(monkeypatch, tmp_path):
    home, _ = ambiente(monkeypatch, tmp_path)
    grava_quoted(home)

    code, _, _ = gera("approve", ITEM_ID, "--by", "   ", "--yes")

    assert code != 0
    item = le_item(home)
    assert item.state == "quoted"
    assert not item.production["steps"][-1].get("confirmed_by")
    assert eventos(home, "spend.approved") == []


def test_approve_com_orcamento_zero_recusa(monkeypatch, tmp_path):
    home, ws = ambiente(monkeypatch, tmp_path, media_credits=500)
    grava_quoted(home, credits=120)
    escreve_policy(ws, media_credits=0)

    code, _, err = gera("approve", ITEM_ID, "--by", "Wesley", "--yes")

    assert code == 1
    assert "orçamento" in err
    assert le_item(home).state == "quoted"
    assert eventos(home, "spend.approved") == []


def test_approve_acima_do_teto_diario_recusa_no_momento_da_aprovacao(
    monkeypatch, tmp_path
):
    home, _ = ambiente(monkeypatch, tmp_path)
    grava_quoted(home, credits=120)

    code, _, err = gera(
        "approve", ITEM_ID, "--by", "Wesley", "--yes", "--daily-cap", "100"
    )

    assert code == 1
    assert "teto diário" in err
    assert le_item(home).state == "quoted"


def test_teto_diario_conta_as_aprovacoes_ja_feitas_no_dia(monkeypatch, tmp_path):
    home, _ = ambiente(monkeypatch, tmp_path, media_credits=1000)
    grava_quoted(home, credits=600, item_id=ITEM_ID)
    grava_quoted(home, credits=500, item_id=OUTRO_ID)
    assert gera("approve", ITEM_ID, "--by", "Wesley", "--yes")[0] == 0

    code, _, err = gera("approve", OUTRO_ID, "--by", "Wesley", "--yes")

    assert code == 1
    assert "teto diário" in err
    assert le_item(home, OUTRO_ID).state == "quoted"


def test_approve_de_item_fora_de_quoted_recusa(monkeypatch, tmp_path):
    home, _ = ambiente(monkeypatch, tmp_path)
    grava_item(home, state="drafted", steps=[passo_ai(120)])

    code, _, _ = gera("approve", ITEM_ID, "--by", "Wesley", "--yes")

    assert code == 1
    item = le_item(home)
    assert item.state == "drafted"
    assert "confirmed_by" not in item.production["steps"][-1]
    assert eventos(home, "spend.approved") == []


def test_approve_de_item_inexistente_falha(monkeypatch, tmp_path):
    ambiente(monkeypatch, tmp_path)

    code, _, err = gera(
        "approve", "itm_01HZNAOEXISTE000000000000", "--by", "Wesley", "--yes"
    )

    assert code == 1
    assert "itm_01HZNAOEXISTE000000000000" in err


# ---------------------------------------------------------------- generate show


def test_show_mostra_passo_custo_e_quem_aprovou(monkeypatch, tmp_path):
    home, _ = ambiente(monkeypatch, tmp_path)
    grava_quoted(home, credits=120)
    gera("approve", ITEM_ID, "--by", "Wesley", "--yes")

    code, out, err = gera("show", ITEM_ID)

    assert code == 0, err
    assert "real-oficial" in out
    assert ESTIMATIVA in out
    assert "120" in out
    assert "Wesley" in out


def test_show_json_traz_passo_custo_e_aprovador(monkeypatch, tmp_path):
    home, _ = ambiente(monkeypatch, tmp_path)
    grava_quoted(home, credits=120)
    gera("approve", ITEM_ID, "--by", "Wesley", "--yes")

    code, out, _ = gera("show", ITEM_ID, "--json")

    assert code == 0
    dados = json.loads(out)
    assert dados["item"] == ITEM_ID
    assert dados["state"] == "approved"
    assert dados["credits"] == 120
    assert dados["confirmed_by"] == "Wesley"
    assert dados["step"]["provider"] == "real-oficial"
    assert dados["step"]["estimate_ref"] == ESTIMATIVA


def test_show_de_item_sem_passo_mostra_sem_custo(monkeypatch, tmp_path):
    home, _ = ambiente(monkeypatch, tmp_path)
    grava_item(home, state="drafted", steps=[])

    code, out, _ = gera("show", ITEM_ID, "--json")

    assert code == 0
    dados = json.loads(out)
    assert dados["step"] is None
    assert dados["credits"] is None
    assert dados["confirmed_by"] is None


def test_show_de_item_inexistente_falha(monkeypatch, tmp_path):
    ambiente(monkeypatch, tmp_path)

    code, _, err = gera("show", "itm_01HZNAOEXISTE000000000000")

    assert code == 1
    assert "itm_01HZNAOEXISTE000000000000" in err
