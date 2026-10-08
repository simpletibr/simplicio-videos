"""Comentários do quadro (#86, épico #81): append-only, um JSON por linha, `--by` obrigatório, sem rede."""

from __future__ import annotations

import ast
import json

import pytest

from tests.factory.plugins.board._fixtures import (
    ITEM_ID,
    PLUGIN_DIR,
    RELOGIO_FIXO,
    fixed_clock,
    home_de,
    ler_item_cru,
    run_cli,
    salvar_item,
    service_module,
)

CAMPOS_DA_LINHA = {"id", "at", "by", "kind", "text"}
PROIBIDOS_NO_PLUGIN = {
    "socket",
    "urllib",
    "http",
    "requests",
    "httpx",
    "ssl",
    "aiohttp",
    "urllib3",
    "anthropic",
    "openai",
}


def _linhas(caminho):
    return [json.loads(linha) for linha in caminho.read_text(encoding="utf-8").splitlines() if linha.strip()]


def test_comentarios_sao_append_only_e_seguem_a_ordem(tmp_path):
    home = home_de(tmp_path)
    salvar_item(home, "rendered")
    svc = service_module()
    arquivo = svc.caminho_comentarios(home, ITEM_ID)

    svc.comentar(home, ITEM_ID, "primeiro", "Ana", relogio=fixed_clock())
    depois_do_primeiro = arquivo.read_bytes()
    svc.comentar(home, ITEM_ID, "segundo", "Bruno", relogio=fixed_clock())
    svc.revisar(home, ITEM_ID, "changes", "Ana", note="ajustar o gancho", relogio=fixed_clock())
    svc.comentar(home, ITEM_ID, "terceiro", "Bruno", relogio=fixed_clock())

    assert arquivo.read_bytes().startswith(depois_do_primeiro), "comments.jsonl foi reescrito, não só acrescido"
    linhas = _linhas(arquivo)
    assert [linha["id"] for linha in linhas] == [1, 2, 3, 4]
    assert [linha["kind"] for linha in linhas] == ["comment", "comment", "review", "comment"]
    assert [linha["text"] for linha in linhas] == ["primeiro", "segundo", "ajustar o gancho", "terceiro"]
    assert [linha["by"] for linha in linhas] == ["Ana", "Bruno", "Ana", "Bruno"]


def test_linha_do_comentario_tem_os_campos_pedidos_e_at_do_relogio(tmp_path):
    home = home_de(tmp_path)
    salvar_item(home, "rendered")

    service_module().comentar(home, ITEM_ID, "Gancho forte", "Ana", relogio=fixed_clock())

    (linha,) = _linhas(service_module().caminho_comentarios(home, ITEM_ID))
    assert set(linha) == CAMPOS_DA_LINHA
    assert linha["at"] == RELOGIO_FIXO
    assert linha["kind"] == "comment"
    assert linha["by"] == "Ana"
    assert linha["text"] == "Gancho forte"


def test_comentario_nao_muda_estado_nem_review_do_item(tmp_path):
    home = home_de(tmp_path)
    salvar_item(home, "rendered")
    antes = ler_item_cru(home)

    service_module().comentar(home, ITEM_ID, "só um comentário", "Ana", relogio=fixed_clock())

    assert ler_item_cru(home) == antes


def test_by_e_obrigatorio_no_comment(tmp_path):
    home = home_de(tmp_path)
    salvar_item(home, "rendered")

    code, _, _ = run_cli(["comment", ITEM_ID, "texto sem autor"])

    assert code == 2, "comment sem --by deveria ser rejeitado pelo argparse"
    assert not service_module().caminho_comentarios(home, ITEM_ID).exists()


def test_by_e_obrigatorio_no_review(tmp_path):
    home = home_de(tmp_path)
    salvar_item(home, "rendered")
    antes = ler_item_cru(home)

    code, _, _ = run_cli(["review", ITEM_ID, "approve"])

    assert code == 2, "review sem --by deveria ser rejeitado pelo argparse"
    assert ler_item_cru(home) == antes


def test_by_vazio_e_recusado_pelo_servico(tmp_path):
    home = home_de(tmp_path)
    salvar_item(home, "rendered")
    svc = service_module()

    with pytest.raises(svc.BoardError):
        svc.comentar(home, ITEM_ID, "texto", "   ", relogio=fixed_clock())
    assert not svc.caminho_comentarios(home, ITEM_ID).exists()


def test_texto_vazio_e_recusado(tmp_path):
    home = home_de(tmp_path)
    salvar_item(home, "rendered")
    svc = service_module()

    with pytest.raises(svc.BoardError):
        svc.comentar(home, ITEM_ID, "   ", "Ana", relogio=fixed_clock())
    assert not svc.caminho_comentarios(home, ITEM_ID).exists()


def test_comentario_em_item_inexistente_e_recusado(tmp_path):
    home = home_de(tmp_path)
    svc = service_module()

    with pytest.raises(svc.BoardError, match="não encontrado"):
        svc.comentar(home, "itm_NAOEXISTE0000000000001", "texto", "Ana", relogio=fixed_clock())


def test_comment_pela_cli_grava_uma_linha(tmp_path, monkeypatch):
    home = home_de(tmp_path)
    monkeypatch.setenv("SIMPLICIO_FACTORY_HOME", str(home))
    salvar_item(home, "rendered")

    code, out, _ = run_cli(["comment", ITEM_ID, "Gancho fraco", "--by", "Ana"])

    assert code == 0
    assert ITEM_ID in out
    (linha,) = _linhas(service_module().caminho_comentarios(home, ITEM_ID))
    assert linha["text"] == "Gancho fraco" and linha["by"] == "Ana"


def _proibido(arquivo, modulo: str) -> bool:
    raiz = modulo.split(".")[0]
    if raiz not in PROIBIDOS_NO_PLUGIN:
        return False
    # #89: o servidor local (serve.py) usa http.server, escuta só em 127.0.0.1 e não importa cliente de rede.
    return not (arquivo.name == "serve.py" and modulo.startswith("http.server"))


def test_plugin_nao_importa_modulos_de_rede_nem_llm():
    arquivos = sorted(PLUGIN_DIR.rglob("*.py"))
    assert arquivos, "src/simplicio_factory/plugins/board/ ausente: nada para checar (#86)"

    ruins = []
    for arquivo in arquivos:
        for no in ast.walk(ast.parse(arquivo.read_text(encoding="utf-8"), filename=str(arquivo))):
            if isinstance(no, ast.Import):
                modulos = [alias.name for alias in no.names]
            elif isinstance(no, ast.ImportFrom) and not no.level:
                modulos = [no.module or ""]
            else:
                continue
            ruins += [f"{arquivo.name}: {m}" for m in modulos if _proibido(arquivo, m)]

    assert not ruins, "o plugin do quadro não pode usar rede nem LLM:\n" + "\n".join(ruins)
