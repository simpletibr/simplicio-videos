"""`generate start` (approved -> generating) e `media attach` (generating -> generated, com recibo) (#87, épico #81)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.factory.plugins.media._attach_fixtures import (
    ARQUIVO_NOME,
    CONTEUDO,
    MEDIA_ID,
    PROMPT,
    RECIBO_SCHEMA,
    arquivo_gerado,
    attach,
    escreve_brand,
    estado,
    grava_generating,
    passo_aprovado,
    pasta_item,
    prompt_file,
    sha256,
    start,
)
from tests.factory.plugins.media._fixtures import (
    ESTIMATIVA,
    ITEM_ID,
    ambiente,
    eventos,
    passo_ai,
)

MANIFEST = (
    Path(__file__).resolve().parents[4]
    / "src"
    / "simplicio_factory"
    / "plugins"
    / "media"
    / "plugin.json"
)


def _anexa_padrao(
    tmp_path: Path, arquivo: Path | None = None, prompt: Path | None = None
):
    """`media attach` com os argumentos válidos do teste; cada teste troca só o que quer provar."""
    return attach(
        ITEM_ID,
        str(arquivo or arquivo_gerado(tmp_path)),
        "--source",
        "real-oficial",
        "--media-id",
        MEDIA_ID,
        "--prompt-file",
        str(prompt or prompt_file(tmp_path)),
    )


# ---------------------------------------------------------------- generate start


def test_start_help_com_exemplo(monkeypatch, tmp_path):
    ambiente(monkeypatch, tmp_path)

    code, out, _ = start("--help")

    assert code == 0
    assert "simplicio-video generate start" in out
    assert "Exemplo" in out


def test_start_leva_approved_a_generating_e_registra_a_mudanca(monkeypatch, tmp_path):
    home, _ = ambiente(monkeypatch, tmp_path)
    grava_generating(home, state="approved")

    code, out, err = start()

    assert code == 0, err
    assert estado(home) == "generating"
    mudancas = [
        (e.data["from"], e.data["to"]) for e in eventos(home, "item.state_changed")
    ]
    assert ("approved", "generating") in mudancas
    assert "generating" in out


def test_start_sem_aprovacao_registrada_falha_sem_mudar_o_item(monkeypatch, tmp_path):
    home, _ = ambiente(monkeypatch, tmp_path)
    sem_confirmacao = {
        k: v
        for k, v in passo_aprovado().items()
        if k not in ("confirmed_by", "confirmed_at")
    }
    grava_generating(home, state="approved", steps=[sem_confirmacao])

    code, _, err = start()

    assert code != 0
    assert "aprovação registrada" in err
    assert estado(home) == "approved"


def test_start_sem_passo_ai_falha(monkeypatch, tmp_path):
    home, _ = ambiente(monkeypatch, tmp_path)
    grava_generating(home, state="approved", steps=[])

    code, _, err = start()

    assert code != 0
    assert "aprovação registrada" in err
    assert estado(home) == "approved"


@pytest.mark.parametrize("estado_inicial", ["quoted", "generating", "generated"])
def test_start_fora_de_approved_falha(monkeypatch, tmp_path, estado_inicial):
    home, _ = ambiente(monkeypatch, tmp_path)
    grava_generating(home, state=estado_inicial, steps=[passo_ai()])

    code, _, err = start()

    assert code != 0
    assert "exige o estado approved" in err
    assert estado(home) == estado_inicial


def test_start_na_rota_deterministica_falha_com_a_transicao_recusada(
    monkeypatch, tmp_path
):
    home, _ = ambiente(monkeypatch, tmp_path)
    grava_generating(home, state="approved", route="deterministic")

    code, _, err = start()

    assert code != 0
    assert "transição inválida" in err
    assert estado(home) == "approved"


def test_start_de_item_inexistente_falha(monkeypatch, tmp_path):
    ambiente(monkeypatch, tmp_path)

    code, _, err = start("itm_01HZINEXISTENTE000000001")

    assert code != 0
    assert "não encontrado" in err


# ---------------------------------------------------------------- media attach: ajuda e registro


def test_manifesto_declara_media_com_handler_existente():
    from simplicio_factory.plugins.media import cli

    manifesto = json.loads(MANIFEST.read_text(encoding="utf-8"))
    comandos = {c["name"]: c for c in manifesto["commands"]}

    assert "media" in comandos
    assert (
        comandos["media"]["handler"] == "simplicio_factory.plugins.media.cli:media_cmd"
    )
    assert callable(cli.media_cmd)


def test_attach_help_com_exemplo_e_opcoes(monkeypatch, tmp_path):
    ambiente(monkeypatch, tmp_path)

    code, out, _ = attach("--help")

    assert code == 0
    assert "simplicio-video media attach" in out
    assert "Exemplo" in out
    for opcao in ("--source", "--media-id", "--prompt-file", "--brand"):
        assert opcao in out, opcao


# ---------------------------------------------------------------- media attach: caminho feliz


def test_attach_copia_o_arquivo_grava_o_recibo_e_leva_a_generated(
    monkeypatch, tmp_path
):
    home, _ = ambiente(monkeypatch, tmp_path)
    escreve_brand(home)
    grava_generating(home)

    code, _, err = _anexa_padrao(tmp_path)

    assert code == 0, err
    pasta = pasta_item(home)
    assert (pasta / "media" / ARQUIVO_NOME).read_bytes() == CONTEUDO
    recibo = json.loads((pasta / "media.json").read_text(encoding="utf-8"))
    assert recibo == {
        "schema": RECIBO_SCHEMA,
        "arquivo": ARQUIVO_NOME,
        "sha256": sha256(CONTEUDO),
        "origem": "real-oficial",
        "media_id": MEDIA_ID,
        "estimate_ref": ESTIMATIVA,
        "credits": 120,
        "confirmed_by": "Wesley",
        "prompt_sha256": sha256(PROMPT.encode("utf-8")),
    }
    assert estado(home) == "generated"


def test_attach_grava_evento_media_attached(monkeypatch, tmp_path):
    home, _ = ambiente(monkeypatch, tmp_path)
    escreve_brand(home)
    grava_generating(home)

    code, _, err = _anexa_padrao(tmp_path)

    assert code == 0, err
    anexados = eventos(home, "media.attached")
    assert len(anexados) == 1
    assert anexados[0].item_id == ITEM_ID
    assert anexados[0].data["media_id"] == MEDIA_ID
    assert anexados[0].data["sha256"] == sha256(CONTEUDO)


def test_attach_recibo_nao_guarda_o_texto_do_prompt(monkeypatch, tmp_path):
    home, _ = ambiente(monkeypatch, tmp_path)
    escreve_brand(home)
    grava_generating(home)

    code, _, err = _anexa_padrao(tmp_path)

    assert code == 0, err
    assert PROMPT not in (pasta_item(home) / "media.json").read_text(encoding="utf-8")


def test_fluxo_completo_start_e_attach_leva_de_approved_a_generated(
    monkeypatch, tmp_path
):
    home, _ = ambiente(monkeypatch, tmp_path)
    escreve_brand(home)
    grava_generating(home, state="approved")

    assert start()[0] == 0
    code, _, err = _anexa_padrao(tmp_path)

    assert code == 0, err
    assert estado(home) == "generated"
    mudancas = [
        (e.data["from"], e.data["to"]) for e in eventos(home, "item.state_changed")
    ]
    assert mudancas[-2:] == [("approved", "generating"), ("generating", "generated")]


# ---------------------------------------------------------------- media attach: recusas


@pytest.mark.parametrize("estado_inicial", ["approved", "quoted", "generated"])
def test_attach_fora_de_generating_falha_sem_copiar_nem_gravar(
    monkeypatch, tmp_path, estado_inicial
):
    home, _ = ambiente(monkeypatch, tmp_path)
    escreve_brand(home)
    grava_generating(home, state=estado_inicial)

    code, _, err = _anexa_padrao(tmp_path)

    assert code != 0
    assert "exige o estado generating" in err
    assert not (pasta_item(home) / "media").exists()
    assert not (pasta_item(home) / "media.json").exists()
    assert estado(home) == estado_inicial


def test_attach_sem_aprovacao_registrada_falha(monkeypatch, tmp_path):
    home, _ = ambiente(monkeypatch, tmp_path)
    escreve_brand(home)
    grava_generating(home, steps=[passo_ai()])

    code, _, err = _anexa_padrao(tmp_path)

    assert code != 0
    assert "aprovação registrada" in err
    assert not (pasta_item(home) / "media.json").exists()
    assert estado(home) == "generating"


def test_attach_de_item_inexistente_falha(monkeypatch, tmp_path):
    home, _ = ambiente(monkeypatch, tmp_path)
    escreve_brand(home)

    code, _, err = attach(
        "itm_01HZINEXISTENTE000000001",
        str(arquivo_gerado(tmp_path)),
        "--source",
        "real-oficial",
        "--media-id",
        MEDIA_ID,
        "--prompt-file",
        str(prompt_file(tmp_path)),
    )

    assert code != 0
    assert "não encontrado" in err


def test_attach_arquivo_inexistente_falha_sem_recibo(monkeypatch, tmp_path):
    home, _ = ambiente(monkeypatch, tmp_path)
    escreve_brand(home)
    grava_generating(home)

    code, _, err = _anexa_padrao(tmp_path, arquivo=tmp_path / "nao-existe.mp4")

    assert code != 0
    assert "arquivo não encontrado" in err
    assert not (pasta_item(home) / "media.json").exists()
    assert estado(home) == "generating"


def test_attach_prompt_inexistente_falha(monkeypatch, tmp_path):
    home, _ = ambiente(monkeypatch, tmp_path)
    escreve_brand(home)
    grava_generating(home)

    code, _, err = _anexa_padrao(tmp_path, prompt=tmp_path / "sem-prompt.txt")

    assert code != 0
    assert "prompt não encontrado" in err
    assert estado(home) == "generating"


def test_attach_prompt_com_preco_inventado_e_recusado_pelo_claim_guard(
    monkeypatch, tmp_path
):
    home, _ = ambiente(monkeypatch, tmp_path)
    escreve_brand(home)
    grava_generating(home)
    prompt = prompt_file(
        tmp_path, texto="Oferta de R$ 99 só hoje, personagem sintético."
    )

    code, _, err = _anexa_padrao(tmp_path, prompt=prompt)

    assert code != 0
    assert "claim guard" in err
    assert "R$ 99" in err
    assert not (pasta_item(home) / "media").exists()
    assert not (pasta_item(home) / "media.json").exists()
    assert estado(home) == "generating"


def test_attach_prompt_com_fato_da_marca_passa_no_claim_guard(monkeypatch, tmp_path):
    home, _ = ambiente(monkeypatch, tmp_path)
    escreve_brand(home)
    grava_generating(home)
    prompt = prompt_file(
        tmp_path, texto="Clínica com 15 anos de atendimento, personagem sintético."
    )

    code, _, err = _anexa_padrao(tmp_path, prompt=prompt)

    assert code == 0, err
    assert estado(home) == "generated"


def test_attach_sem_brand_falha_fechado(monkeypatch, tmp_path):
    home, _ = ambiente(monkeypatch, tmp_path)
    grava_generating(home)

    code, _, err = _anexa_padrao(tmp_path)

    assert code != 0
    assert "brand" in err
    assert not (pasta_item(home) / "media.json").exists()
    assert estado(home) == "generating"


def test_attach_media_id_vazio_falha(monkeypatch, tmp_path):
    home, _ = ambiente(monkeypatch, tmp_path)
    escreve_brand(home)
    grava_generating(home)

    code, _, err = attach(
        ITEM_ID,
        str(arquivo_gerado(tmp_path)),
        "--source",
        "real-oficial",
        "--media-id",
        "   ",
        "--prompt-file",
        str(prompt_file(tmp_path)),
    )

    assert code != 0
    assert "--media-id" in err
    assert estado(home) == "generating"


def test_attach_source_so_aceita_real_oficial(monkeypatch, tmp_path):
    home, _ = ambiente(monkeypatch, tmp_path)
    escreve_brand(home)
    grava_generating(home)

    code, _, err = attach(
        ITEM_ID,
        str(arquivo_gerado(tmp_path)),
        "--source",
        "outro",
        "--media-id",
        MEDIA_ID,
        "--prompt-file",
        str(prompt_file(tmp_path)),
    )

    assert code != 0
    assert "real-oficial" in err
    assert estado(home) == "generating"
