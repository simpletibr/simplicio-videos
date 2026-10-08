"""Servidor local do quadro (#89, épico #81): `board serve` em 127.0.0.1, com token por sessão.

Os testes de rede sobem o servidor como o usuário faz: `python -m simplicio_video board serve --port 0`, em
subprocesso, e leem a URL com o token da saída. Só eles têm o marcador `integration` (sockets liberados só ali);
a recusa de host e a ajuda rodam sem socket, pela CLI em processo.

Enquanto `serve` não existe, o argparse sai com código 2 ("invalid choice: 'serve'") e a asserção mostra essa
mensagem: a falha é de funcionalidade ausente, não de import.
"""

from __future__ import annotations

import contextlib
import http.client
import json
import os
import queue
import re
import subprocess
import sys
import threading
import urllib.parse
from pathlib import Path

import pytest

from tests.factory.plugins.board._fixtures import (
    ITEM_ID,
    MANIFEST_PATH,
    ROOT,
    home_de,
    ler_item_cru,
    run_cli,
    salvar_item,
    service_module,
)

LINHA_DA_URL = re.compile(r"Abra no navegador: http://127\.0\.0\.1:(\d+)/\?token=(\S+)")


def _linhas(caminho: Path) -> list[dict]:
    return [json.loads(linha) for linha in caminho.read_text(encoding="utf-8").splitlines() if linha.strip()]


def _arvore(home: Path) -> dict[str, bytes]:
    """Retrato de todos os arquivos de `home`: prova que um pedido não gravou nada."""
    if not home.exists():
        return {}
    return {str(p.relative_to(home)): p.read_bytes() for p in sorted(home.rglob("*")) if p.is_file()}


@contextlib.contextmanager
def servidor(home: Path):
    """Sobe `board serve --port 0` num subprocesso e entrega (porta, token) lidos da saída."""
    env = os.environ.copy()
    env["SIMPLICIO_FACTORY_HOME"] = str(home)
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(ROOT / "src"), env.get("PYTHONPATH", "")]))
    proc = subprocess.Popen(
        [sys.executable, "-m", "simplicio_video", "board", "serve", "--port", "0"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
        cwd=str(home.parent),
    )
    linhas: queue.Queue = queue.Queue()

    def le_saida():
        for linha in proc.stdout:
            linhas.put(linha)
        linhas.put(None)

    threading.Thread(target=le_saida, daemon=True).start()
    achado = None
    while achado is None:
        try:
            linha = linhas.get(timeout=30)
        except queue.Empty:
            break
        if linha is None:
            break
        achado = LINHA_DA_URL.search(linha)

    if achado is None:
        proc.kill()
        proc.wait(timeout=10)
        erro = proc.stderr.read().strip()
        pytest.fail(f"servidor não subiu (código {proc.returncode}): {erro}")

    try:
        yield int(achado.group(1)), achado.group(2)
    finally:
        proc.terminate()
        proc.wait(timeout=10)
        proc.stdout.close()
        proc.stderr.close()


def pede(porta: int, metodo: str, caminho: str, *, corpo: dict | None = None, cabecalhos: dict | None = None):
    """Uma requisição HTTP ao servidor local. Devolve (status, corpo em texto)."""
    conn = http.client.HTTPConnection("127.0.0.1", porta, timeout=15)
    try:
        cab = dict(cabecalhos or {})
        dados = None
        if corpo is not None:
            dados = urllib.parse.urlencode(corpo)
            cab.setdefault("Content-Type", "application/x-www-form-urlencoded")
        conn.request(metodo, caminho, body=dados, headers=cab)
        resposta = conn.getresponse()
        return resposta.status, resposta.read().decode("utf-8", "replace")
    finally:
        conn.close()


# ---------------------------------------------------------------- CLI sem socket (roda no gate padrão)


def test_serve_aparece_na_ajuda_com_exemplo():
    code, out, _ = run_cli(["serve", "--help"])

    assert code == 0, out
    assert "simplicio-video board serve" in out
    assert "Exemplo" in out
    assert "--port" in out


@pytest.mark.parametrize("host", ["0.0.0.0", "::", "192.168.0.10", "example.com"])
def test_recusa_host_que_nao_e_loopback(tmp_path, monkeypatch, host):
    monkeypatch.setenv("SIMPLICIO_FACTORY_HOME", str(home_de(tmp_path)))

    code, _, err = run_cli(["serve", "--host", host])

    assert code == 2, err
    assert "127.0.0.1" in err, err


@pytest.mark.parametrize("porta", ["-1", "65536", "abc"])
def test_porta_invalida_sai_com_2(tmp_path, monkeypatch, porta):
    monkeypatch.setenv("SIMPLICIO_FACTORY_HOME", str(home_de(tmp_path)))

    code, _, err = run_cli(["serve", "--port", porta])

    assert code == 2, err
    assert "--port" in err, err


def test_manifesto_lista_serve_no_help():
    manifesto = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    assert "board serve" in manifesto["commands"][0]["help"]


# ---------------------------------------------------------------- servidor de verdade (marcador integration)


@pytest.mark.integration
def test_serve_sobe_em_127_0_0_1_e_serve_a_pagina_com_o_token(tmp_path):
    home = home_de(tmp_path)
    salvar_item(home, "rendered")

    with servidor(home) as (porta, token):
        status, corpo = pede(porta, "GET", f"/?token={token}")

    assert status == 200
    assert "Quadro da fábrica" in corpo
    assert 'name="token"' in corpo and token in corpo, "o token precisa estar embutido na página"


@pytest.mark.integration
def test_token_muda_a_cada_sessao(tmp_path):
    home = home_de(tmp_path)
    with servidor(home) as (_, primeiro):
        pass
    with servidor(home) as (_, segundo):
        pass

    assert primeiro and segundo and primeiro != segundo


@pytest.mark.integration
def test_sem_token_ou_com_token_errado_da_403(tmp_path):
    home = home_de(tmp_path)
    salvar_item(home, "rendered")
    comentarios = service_module().caminho_comentarios(home, ITEM_ID)
    comentario = {"item": ITEM_ID, "texto": "sem token", "by": "Ana"}

    with servidor(home) as (porta, _):
        assert pede(porta, "GET", "/")[0] == 403
        assert pede(porta, "GET", "/?token=errado")[0] == 403
        assert pede(porta, "POST", "/comment", corpo=comentario)[0] == 403
        assert pede(porta, "POST", "/comment", corpo={**comentario, "token": "errado"})[0] == 403
        revisao = {"item": ITEM_ID, "decisao": "approve", "by": "Ana", "token": "errado"}
        assert pede(porta, "POST", "/review", corpo=revisao)[0] == 403

    assert not comentarios.exists(), "pedido sem token não pode gravar comentário"


@pytest.mark.integration
def test_origin_ou_host_externos_da_403_mesmo_com_token(tmp_path):
    home = home_de(tmp_path)
    salvar_item(home, "rendered")
    comentarios = service_module().caminho_comentarios(home, ITEM_ID)

    with servidor(home) as (porta, token):
        com_token = f"/?token={token}"
        assert pede(porta, "GET", com_token, cabecalhos={"Host": "evil.example"})[0] == 403
        assert pede(porta, "GET", com_token, cabecalhos={"Host": f"evil.example:{porta}"})[0] == 403
        corpo = {"token": token, "item": ITEM_ID, "texto": "de fora", "by": "Ana"}
        assert pede(porta, "POST", "/comment", corpo=corpo, cabecalhos={"Origin": "http://evil.example"})[0] == 403
        assert pede(porta, "POST", "/comment", corpo=corpo, cabecalhos={"Origin": "null"})[0] == 403
        assert not comentarios.exists(), "origem externa não pode gravar comentário"

        local = {"Host": f"localhost:{porta}", "Origin": f"http://localhost:{porta}"}
        assert pede(porta, "GET", com_token, cabecalhos=local)[0] == 200, "controle: localhost com token passa"


@pytest.mark.integration
@pytest.mark.parametrize(
    "metodo,caminho",
    [
        ("POST", "/approve-spend"),
        ("POST", "/generate/approve"),
        ("POST", "/budget"),
        ("POST", "/state"),
        ("POST", f"/items/{ITEM_ID}/state"),
        ("GET", "/approve"),
    ],
)
def test_rota_de_estado_ou_gasto_da_404_e_nada_muda(tmp_path, metodo, caminho):
    home = home_de(tmp_path)
    salvar_item(home, "rendered")
    antes = _arvore(home)

    with servidor(home) as (porta, token):
        dados = {
            "token": token,
            "item": ITEM_ID,
            "decisao": "approve",
            "estado": "approved",
            "gasto": "sim",
            "by": "Ana",
        }
        if metodo == "GET":
            status, _ = pede(porta, metodo, f"{caminho}?token={token}")
        else:
            status, _ = pede(porta, metodo, caminho, corpo=dados)

    assert status == 404
    assert _arvore(home) == antes, "rota inexistente não pode alterar nada em disco"


@pytest.mark.integration
def test_comentario_grava_e_o_build_seguinte_mostra(tmp_path, monkeypatch):
    home = home_de(tmp_path)
    salvar_item(home, "rendered")
    estado_antes = ler_item_cru(home)
    monkeypatch.setenv("SIMPLICIO_FACTORY_HOME", str(home))

    with servidor(home) as (porta, token):
        status, _ = pede(
            porta,
            "POST",
            "/comment",
            corpo={"token": token, "item": ITEM_ID, "texto": "Gancho mais forte", "by": "Ana"},
        )

    assert status == 303
    (linha,) = _linhas(service_module().caminho_comentarios(home, ITEM_ID))
    assert linha["kind"] == "comment"
    assert linha["by"] == "Ana"
    assert linha["text"] == "Gancho mais forte"
    assert ler_item_cru(home) == estado_antes, "comentário não muda o item"

    destino = tmp_path / "board.html"
    code, _, err = run_cli(["build", "--out", str(destino)])

    assert code == 0, err
    assert "Gancho mais forte" in destino.read_text(encoding="utf-8")


@pytest.mark.integration
@pytest.mark.parametrize(
    "decisao,coluna_esperada,review_gravado",
    [("approve", "pronto", "approved"), ("changes", "revisao", "changes_requested")],
)
def test_revisao_grava_e_o_build_seguinte_mostra_a_coluna(
    tmp_path, monkeypatch, decisao, coluna_esperada, review_gravado
):
    home = home_de(tmp_path)
    salvar_item(home, "rendered")
    monkeypatch.setenv("SIMPLICIO_FACTORY_HOME", str(home))

    with servidor(home) as (porta, token):
        status, _ = pede(
            porta,
            "POST",
            "/review",
            corpo={"token": token, "item": ITEM_ID, "decisao": decisao, "by": "Ana", "note": "vista no navegador"},
        )

    assert status == 303
    assert ler_item_cru(home)["review"] == review_gravado
    (linha,) = _linhas(service_module().caminho_comentarios(home, ITEM_ID))
    assert linha["kind"] == "review" and linha["text"] == "vista no navegador"

    destino = tmp_path / "board.html"
    code, _, err = run_cli(["build", "--out", str(destino)])

    assert code == 0, err
    html = destino.read_text(encoding="utf-8")
    casa = re.search(rf'<section data-coluna="{coluna_esperada}"[\s\S]*?</section>', html)
    assert casa and ITEM_ID in casa.group(0), f"{ITEM_ID} deveria estar em {coluna_esperada}"


@pytest.mark.integration
def test_texto_recebido_e_escapado_na_pagina(tmp_path):
    home = home_de(tmp_path)
    salvar_item(home, "rendered")
    payload = "<script>alert(1)</script>"

    with servidor(home) as (porta, token):
        pede(porta, "POST", "/comment", corpo={"token": token, "item": ITEM_ID, "texto": payload, "by": "Ana"})
        status, corpo = pede(porta, "GET", f"/?token={token}")

    assert status == 200
    assert payload not in corpo, "o script do comentário não pode chegar à página crua"
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in corpo


@pytest.mark.integration
def test_comentarios_simultaneos_nao_se_atropelam(tmp_path):
    home = home_de(tmp_path)
    salvar_item(home, "rendered")
    resultados: list[int] = []

    def comenta(porta: int, token: str, i: int):
        status, _ = pede(
            porta, "POST", "/comment", corpo={"token": token, "item": ITEM_ID, "texto": f"c{i}", "by": "Ana"}
        )
        resultados.append(status)

    with servidor(home) as (porta, token):
        pedidos = [threading.Thread(target=comenta, args=(porta, token, i)) for i in range(20)]
        for t in pedidos:
            t.start()
        for t in pedidos:
            t.join(timeout=60)

    assert resultados == [303] * 20
    linhas = _linhas(service_module().caminho_comentarios(home, ITEM_ID))
    assert [linha["id"] for linha in linhas] == list(range(1, 21)), "ids repetidos ou fora de ordem"
    assert sorted(linha["text"] for linha in linhas) == sorted(f"c{i}" for i in range(20))


@pytest.mark.integration
def test_pagina_servida_tem_formulario_e_botoes_sem_rede_externa(tmp_path):
    home = home_de(tmp_path)
    salvar_item(home, "rendered")

    with servidor(home) as (porta, token):
        status, corpo = pede(porta, "GET", f"/?token={token}")

    assert status == 200
    assert 'action="/comment"' in corpo
    assert 'action="/review"' in corpo
    assert re.search(r'name="decisao"\s+value="approve"', corpo)
    assert re.search(r'name="decisao"\s+value="changes"', corpo)
    assert re.search(r"https?://", corpo) is None
    assert re.search(r"<script[^>]*\ssrc=", corpo) is None


# ---------------------------------------------------------------- regras puras (sem socket; rodam no gate padrão)


def test_host_e_origem_so_aceitam_localhost_e_127_0_0_1_na_porta_do_servidor():
    from simplicio_factory.plugins.board import serve

    assert serve._host_local("127.0.0.1:8765", 8765)
    assert serve._host_local("localhost", 8765)
    assert not serve._host_local("evil.example:8765", 8765)
    assert not serve._host_local("127.0.0.1:9999", 8765), "outra porta não é este servidor"
    assert serve._origem_local("http://localhost:8765", 8765)
    assert not serve._origem_local("http://evil.example", 8765)
    assert not serve._origem_local("null", 8765)
    assert not serve._origem_local("https://127.0.0.1:8765", 8765), "o servidor só fala http"


def test_checa_host_recusa_tudo_que_nao_e_loopback():
    from simplicio_factory.plugins.board import serve
    from simplicio_factory.plugins.board.service import BoardError

    assert serve.checa_host("localhost") == "127.0.0.1"
    for host in ("0.0.0.0", "::", "192.168.0.10"):
        with pytest.raises(BoardError):
            serve.checa_host(host)


def test_decodifica_formulario_com_utf8_mais_e_percent():
    from simplicio_factory.plugins.board import serve

    assert serve._campos("by=Ana+J%C3%BAlia&texto=50%25+%2B+1") == {"by": "Ana Júlia", "texto": "50% + 1"}


def test_pagina_servida_escapa_comentario_e_o_estatico_nao_tem_formulario(tmp_path):
    from simplicio_factory.plugins.board import html as quadro_html
    from simplicio_factory.plugins.board import serve

    home = home_de(tmp_path)
    salvar_item(home, "rendered")
    service_module().comentar(home, ITEM_ID, "<script>x()</script>", "Ana", relogio=lambda: "2026-10-08T10:00:00-03:00")

    servida = serve.pagina(home, "tok123")
    estatica = quadro_html.construir(home, home.resolve())

    assert "<script>x()</script>" not in servida
    assert "&lt;script&gt;x()&lt;/script&gt;" in servida
    assert 'name="token" value="tok123"' in servida
    assert "<form" not in estatica, "o build estático não ganha formulário"
