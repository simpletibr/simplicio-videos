"""Biblioteca de formatos (pasta "Swipe File - 50 Formatos" no Drive): 50 exemplos para trocar o formato de um vídeo
ou de uma copy. O repositório guarda os links e a descrição estrutural, nunca os arquivos de vídeo."""
from __future__ import annotations

import json
import re

import pytest

from simplicio_video import cli, mcp_server, paths

PASTA = "https://drive.google.com/drive/folders/1RhmMHVcjFft9yS-DgZedqzXZE9SXk_Ms"
OBJETIVOS = {"clique", "lead", "venda", "engajamento"}
NOMES_NA_PASTA = {
    "Caixinha", "POV", "Diálogo", "Choquei", "Notícia", "Meme", "UGC em 1ª Pessoa", "Tela Dividida", "Fofoca", "React",
    "UGC em 3ª Pessoa", "Esquete", "Fala e Faz", "Depoimento", "Experimento Social", "Tela Verde", "Palestrinha",
    "Telepatia", "Análise", "Google Meet", "Telemarketing", "POV + Meme", "LO-FI", "Corte de Podcast", "Top 5 (ranking)",
    "Conversa no Carro", "Diálogo de Gêmeos", "Mensagem", "Passo a passo", "Copy no Papel", "Cinema", "ASMR", "Live",
    "Analogia", "Receita", "Tweet", "Oferta Direta", "Story", "Série", "Edit", "Rotina", "POV + Depoimento",
    "Certo VS Errado", "Trivial", "The Office", "TikTok", "Leia a Legenda", "Entrevista", "Jornal Nacional",
    "Anjinho VS Diabinho",
}


@pytest.fixture
def dados():
    return json.loads((paths.data_dir() / "formats" / "formats.json").read_text(encoding="utf8"))


@pytest.fixture
def copia_txt(tmp_path):
    p = tmp_path / "copia.txt"
    p.write_text("Roteiro de teste: o problema que o público vive e o caminho para resolver.", encoding="utf8")
    return p


def test_arquivo_tem_schema_pasta_e_50_formatos(dados):
    assert dados["schema"] == "simplicio.ad-formats/v1"
    assert dados["pasta_drive"] == PASTA
    assert len(dados["formatos"]) == 50


def test_os_50_nomes_batem_com_a_pasta_do_drive(dados):
    assert {f["fonte_drive"] for f in dados["formatos"]} == NOMES_NA_PASTA


def test_ids_unicos_e_campos_completos(dados):
    ids = [f["id"] for f in dados["formatos"]]
    assert len(set(ids)) == 50
    for f in dados["formatos"]:
        assert {"id", "nome", "descricao", "estrutura", "limites", "objetivo", "suposicao", "fonte_drive",
                "verificado", "exemplo"} <= set(f), f.get("id")
        assert f["objetivo"] in OBJETIVOS, f["id"]
        assert 3 <= len(f["estrutura"]) <= 6, f["id"]
        assert all(isinstance(b, str) and b.strip() for b in f["estrutura"]), f["id"]
        assert isinstance(f["verificado"], bool), f["id"]


def test_cada_exemplo_aponta_para_a_pasta_e_para_o_arquivo_do_nome(dados):
    for f in dados["formatos"]:
        assert f["exemplo"]["pasta"] == PASTA, f["id"]
        assert f["exemplo"]["arquivo"] == f["fonte_drive"], f["id"]
        assert f["exemplo"]["link"] is None or f["exemplo"]["link"].startswith("https://drive.google.com/"), f["id"]


def test_nao_ha_emoji_nem_numero_de_resultado_nas_descricoes(dados):
    texto = json.dumps(dados, ensure_ascii=False)
    assert not re.search(r"[\U0001F300-\U0001FAFF☀-➿]", texto)
    for f in dados["formatos"]:
        assert "R$" not in f["descricao"] and "%" not in f["descricao"], f["id"]


def test_cli_formats_list_json(capsys):
    assert cli.main(["formats", "list", "--json"]) == 0
    rows = json.loads(capsys.readouterr().out)
    assert len(rows) == 50 and rows[0]["id"]


def test_cli_formats_list_filtra_por_objetivo(capsys):
    assert cli.main(["formats", "list", "--objetivo", "venda", "--json"]) == 0
    rows = json.loads(capsys.readouterr().out)
    assert rows and {r["objetivo"] for r in rows} == {"venda"}


def test_cli_formats_list_texto_mostra_id_e_nome(capsys):
    assert cli.main(["formats", "list"]) == 0
    out = capsys.readouterr().out
    assert "caixinha" in out and "Caixinha" in out


def test_cli_formats_show_traz_o_exemplo_no_drive(capsys):
    assert cli.main(["formats", "show", "caixinha", "--json"]) == 0
    f = json.loads(capsys.readouterr().out)
    assert f["id"] == "caixinha" and f["exemplo"]["pasta"] == PASTA and f["exemplo"]["arquivo"] == "Caixinha"


def test_cli_formats_show_desconhecido_e_erro(capsys):
    assert cli.main(["formats", "show", "inventado"]) == 1
    assert "formato desconhecido" in capsys.readouterr().err


def test_cli_formats_prompt_monta_o_pedido_com_a_copia(copia_txt, capsys):
    assert cli.main(["formats", "prompt", "caixinha", "--copia", str(copia_txt)]) == 0
    out = capsys.readouterr().out
    assert "Para o formato Caixinha que consiste em " in out
    assert "Roteiro de teste" in out
    assert "Mantenha a mensagem central" in out


def test_cli_formats_prompt_le_a_copia_da_entrada_padrao(monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", __import__("io").StringIO("Copia vinda do stdin."))
    assert cli.main(["formats", "prompt", "pov", "--copia", "-"]) == 0
    assert "Copia vinda do stdin." in capsys.readouterr().out


def test_cli_formats_prompt_sem_copia_nao_monta_nada(capsys):
    with pytest.raises(SystemExit) as e:  # erro de uso do argparse
        cli.main(["formats", "prompt", "caixinha"])
    assert e.value.code == 2
    assert "--copia" in capsys.readouterr().err


def test_cli_formats_prompt_recusa_o_modelo_vazio(tmp_path, capsys):
    vazio = tmp_path / "vazio.txt"
    vazio.write_text("   \n", encoding="utf8")
    assert cli.main(["formats", "prompt", "caixinha", "--copia", str(vazio)]) == 1
    assert "copia vazia" in capsys.readouterr().err


def test_mcp_formats_list_show_prompt(copia_txt):
    r = mcp_server.video_formats("list")
    assert r["ok"] is True and len(r["items"]) == 50
    r = mcp_server.video_formats("show", id="caixinha")
    assert r["ok"] is True and r["item"]["exemplo"]["pasta"] == PASTA
    r = mcp_server.video_formats("prompt", id="caixinha", copia="Copia de teste.")
    assert r["ok"] is True and "Copia de teste." in r["prompt"]
