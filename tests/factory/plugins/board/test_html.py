"""Dashboard HTML estático do quadro (#88, épico #81): `simplicio-video board build [--out board.html]`.

Os testes geram o arquivo pela CLI, como o usuário. Enquanto `build` não existe, o argparse sai com código 2 e a
asserção mostra a mensagem dele: a falha é de funcionalidade ausente, não de import.

Contrato de marcação que os testes leem (o template é o dono dele):
- `<section data-coluna="CHAVE">`, uma por coluna, na ordem do quadro; `data-restantes="N"` com o que ficou de fora.
- `<article class="card" data-item="ID" data-ultimo-evento="SEQ" data-comentarios="N">` por cartão mostrado.
- `<article id="item-ID" class="detalhe">` com o detalhe do cartão (linha do tempo, prévia, MP4, recibo, comentários).

Fixture de 4 itens: pronto (determinístico), em revisão (determinístico), gerando (generativo) e falhou.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.factory.plugins.board._fixtures import ROOT, home_de, run_cli, service_module

PRONTO = "itm_01HZHTML0000000000000001"
REVISAO = "itm_01HZHTML0000000000000002"
GERANDO = "itm_01HZHTML0000000000000003"
FALHOU = "itm_01HZHTML0000000000000004"
RELOGIO = "2026-10-08T10:00:00-03:00"
GOLDEN = Path(__file__).resolve().parent / "golden" / "board.html"
LIMITE_BYTES = 60_000
TITULOS = ("Ideia", "Roteiro", "Orçamento", "Aprovado", "Gerando", "Revisão", "Pronto", "Falhou")
CHAVES = ("ideia", "roteiro", "orcamento", "aprovado", "gerando", "revisao", "pronto", "falhou")


def _relogio() -> str:
    return RELOGIO


def monta_quatro_itens(home: Path) -> None:
    """Quatro itens com eventos reais (transition), revisão, comentário, Draft, studio.json, prévia, MP4 e recibo."""
    from simplicio_factory.contracts import transition
    from simplicio_factory.contracts.json_store import JsonStore
    from tests.factory._fixtures import ai_production, make_routed_item

    store = JsonStore(home)
    service = service_module()

    pronto = make_routed_item(state="idea", item_id=PRONTO, brand="acme")
    store.save_item(pronto)
    for para in ("drafted", "rendering", "rendered"):
        transition(pronto, para, store)
    service.revisar(home, PRONTO, "approve", "Ana", "pode publicar", relogio=_relogio)

    revisao = make_routed_item(state="idea", item_id=REVISAO, brand="acme")
    store.save_item(revisao)
    for para in ("drafted", "rendering", "rendered"):
        transition(revisao, para, store)
    service.comentar(home, REVISAO, "Trocar a cor do logo", "Bruno", relogio=_relogio)

    passos = [{"kind": "ai_media", "provider": "provedor-teste", "estimate_ref": "cot-001", "credits": 120}]
    gerando = make_routed_item(state="idea", production=ai_production(passos), item_id=GERANDO, brand="acme")
    store.save_item(gerando)
    for para in ("drafted", "quoted", "approved", "generating"):
        transition(gerando, para, store)

    falhou = make_routed_item(state="idea", item_id=FALHOU, brand="acme")
    store.save_item(falhou)
    for para in ("drafted", "rendering", "failed"):
        transition(falhou, para, store)

    ideias = {
        PRONTO: "Dica de higiene bucal para o Dia das Crianças",
        REVISAO: "Apresentação da equipe da clínica",
        GERANDO: "Vídeo de boas-vindas gerado por IA",
        FALHOU: "Oferta de consulta de avaliação",
    }
    for item_id, idea in ideias.items():
        pasta = home / "studio" / item_id
        pasta.mkdir(parents=True, exist_ok=True)
        draft = {
            "item_id": item_id,
            "idea": idea,
            "facts": {},
            "claims": [],
            "platform": "instagram",
            "duration_s": 15,
        }
        (pasta / "draft.json").write_text(json.dumps(draft, ensure_ascii=False, indent=2), encoding="utf-8")

    mp4 = home / "studio" / "renders" / f"{PRONTO}.mp4"
    mp4.parent.mkdir(parents=True, exist_ok=True)
    mp4.write_bytes(b"mp4 de teste")
    (home / "studio" / "renders" / f"{PRONTO}-previa.mp4").write_bytes(b"previa de teste")
    estado = {
        "content_hash": "hash-de-teste",
        "production": {"route": "deterministic", "steps": []},
        "stages": {"studio": {"state": "rendered", "mp4": str(mp4.resolve()), "render_sha256": "abc123"}},
    }
    (home / "studio" / PRONTO / "studio.json").write_text(json.dumps(estado, indent=2), encoding="utf-8")

    recibo = {"provider": "provedor-teste", "estimate_ref": "cot-001", "credits": 120, "status": "gerando"}
    (home / "media" / GERANDO).mkdir(parents=True, exist_ok=True)
    (home / "media" / GERANDO / "media.json").write_text(json.dumps(recibo, indent=2), encoding="utf-8")


def _gera(home: Path, out: Path, monkeypatch) -> bytes:
    monkeypatch.setenv("SIMPLICIO_FACTORY_HOME", str(home))
    code, _, err = run_cli(["build", "--out", str(out)])
    assert code == 0, f"board build falhou (código {code}): {err}"
    return out.read_bytes()


def _html_de_quatro_itens(tmp_path: Path, monkeypatch) -> str:
    home = home_de(tmp_path)
    monta_quatro_itens(home)
    return _gera(home, tmp_path / "board.html", monkeypatch).decode("utf-8")


def _coluna(html: str, chave: str) -> str:
    casa = re.search(rf'<section data-coluna="{chave}"[\s\S]*?</section>', html)
    assert casa, f"coluna {chave} ausente no HTML"
    return casa.group(0)


def _detalhe(html: str, item_id: str) -> str:
    casa = re.search(rf'<article id="item-{item_id}"[\s\S]*?</article>', html)
    assert casa, f"detalhe de {item_id} ausente no HTML"
    return casa.group(0)


def _cartao(html: str, item_id: str) -> str:
    casa = re.search(rf'<article class="card" data-item="{item_id}"[^>]*>[\s\S]*?</article>', html)
    assert casa, f"cartão de {item_id} ausente no HTML"
    return casa.group(0)


def test_build_aparece_na_ajuda_com_exemplo():
    code, out, _ = run_cli(["build", "--help"])

    assert code == 0
    assert "simplicio-video board build" in out
    assert "Exemplo" in out
    assert "--out" in out


def test_build_grava_html_com_as_oito_colunas_e_os_cartoes(tmp_path, monkeypatch):
    html = _html_de_quatro_itens(tmp_path, monkeypatch)

    assert html.startswith("<!doctype html>")
    for chave, titulo in zip(CHAVES, TITULOS):
        assert f'data-coluna="{chave}"' in html
        assert titulo in html
    for item_id in (PRONTO, REVISAO, GERANDO, FALHOU):
        assert f'data-item="{item_id}"' in html


def test_cada_item_cai_na_coluna_certa(tmp_path, monkeypatch):
    html = _html_de_quatro_itens(tmp_path, monkeypatch)

    assert PRONTO in _coluna(html, "pronto")
    assert REVISAO in _coluna(html, "revisao")
    assert GERANDO in _coluna(html, "gerando")
    assert FALHOU in _coluna(html, "falhou")


def test_golden_do_html_com_quatro_itens(tmp_path, monkeypatch):
    assert GOLDEN.is_file(), "golden ausente: é gerado depois do verde, no commit feat (#88)"
    home = home_de(tmp_path)
    monta_quatro_itens(home)

    gerado = _gera(home, tmp_path / "board.html", monkeypatch)

    assert gerado == GOLDEN.read_bytes()


def test_sem_url_http_ou_https_externa(tmp_path, monkeypatch):
    html = _html_de_quatro_itens(tmp_path, monkeypatch)

    assert re.search(r"https?://", html) is None
    assert re.search(r"<script[^>]*\ssrc=", html) is None
    assert "<link" not in html


def test_leitura_apenas_sem_formularios_nem_controles(tmp_path, monkeypatch):
    html = _html_de_quatro_itens(tmp_path, monkeypatch)

    for marca in ("<form", "<input", "<textarea", "<button", "<select"):
        assert marca not in html, marca


def test_mesma_entrada_mesmos_bytes(tmp_path, monkeypatch):
    home = home_de(tmp_path)
    monta_quatro_itens(home)

    primeiro = _gera(home, tmp_path / "um.html", monkeypatch)
    segundo = _gera(home, tmp_path / "dois.html", monkeypatch)

    assert primeiro == segundo


def test_texto_de_comentario_e_titulo_sao_escapados(tmp_path, monkeypatch):
    home = home_de(tmp_path)
    monta_quatro_itens(home)
    service_module().comentar(home, REVISAO, '<script>alert("x")</script>', "Bruno", relogio=_relogio)
    draft = home / "studio" / PRONTO / "draft.json"
    dados = json.loads(draft.read_text(encoding="utf-8"))
    dados["idea"] = '<img src=x onerror="alert(1)">'
    draft.write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")

    html = _gera(home, tmp_path / "board.html", monkeypatch).decode("utf-8")

    assert '<script>alert("x")' not in html
    assert "&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;" in html
    assert "<img src=x" not in html
    assert "&lt;img src=x" in html


def test_tamanho_do_arquivo_abaixo_do_limite(tmp_path, monkeypatch):
    html = _html_de_quatro_itens(tmp_path, monkeypatch)

    assert len(html.encode("utf-8")) < LIMITE_BYTES


def test_limite_de_50_cartoes_por_coluna_com_os_mais_recentes(tmp_path, monkeypatch):
    from simplicio_factory.contracts import transition
    from simplicio_factory.contracts.json_store import JsonStore
    from tests.factory._fixtures import make_routed_item

    home = home_de(tmp_path)
    store = JsonStore(home)
    ids = [f"itm_01HZLIMITE{n:014d}" for n in range(55)]
    for item_id in ids:
        item = make_routed_item(state="idea", item_id=item_id, brand="acme")
        store.save_item(item)
        transition(item, "drafted", store)

    html = _gera(home, tmp_path / "board.html", monkeypatch).decode("utf-8")
    roteiro = _coluna(html, "roteiro")

    assert roteiro.count("data-item=") == 50
    assert 'data-restantes="5"' in roteiro
    assert ids[0] not in roteiro
    assert ids[4] not in roteiro
    assert ids[5] in roteiro
    assert ids[-1] in roteiro


def test_cartao_mostra_rota_estado_custo_e_comentarios(tmp_path, monkeypatch):
    html = _html_de_quatro_itens(tmp_path, monkeypatch)

    gerando = _cartao(html, GERANDO)
    assert "generativa" in gerando
    assert "120 créditos" in gerando
    assert "generating" in gerando
    revisao = _cartao(html, REVISAO)
    assert "determinística" in revisao
    assert 'data-comentarios="1"' in revisao
    falhou = _cartao(html, FALHOU)
    assert "failed" in falhou
    assert "rendering" in falhou


def test_ultima_atividade_vem_do_ultimo_evento(tmp_path, monkeypatch):
    from simplicio_factory.contracts.json_store import JsonStore

    home = home_de(tmp_path)
    monta_quatro_itens(home)
    eventos = [e for e in JsonStore(home).read() if e.item_id == PRONTO]
    ultimo = max(e.seq for e in eventos)

    html = _gera(home, tmp_path / "board.html", monkeypatch).decode("utf-8")

    assert f'data-ultimo-evento="{ultimo}"' in _cartao(html, PRONTO)


def test_detalhe_tem_linha_do_tempo_links_e_recibo(tmp_path, monkeypatch):
    html = _html_de_quatro_itens(tmp_path, monkeypatch)

    pronto = _detalhe(html, PRONTO)
    assert f"home/studio/renders/{PRONTO}.mp4" in pronto
    assert f"home/studio/renders/{PRONTO}-previa.mp4" in pronto
    assert "item.state_changed" in pronto
    assert "Ana" in pronto
    gerando = _detalhe(html, GERANDO)
    assert "provedor-teste" in gerando
    assert "cot-001" in gerando
    assert "<pre" in gerando


def test_detalhe_sem_mp4_nao_inventa_link(tmp_path, monkeypatch):
    html = _html_de_quatro_itens(tmp_path, monkeypatch)

    revisao = _detalhe(html, REVISAO)

    assert "Bruno" in revisao
    assert "Trocar a cor do logo" in revisao
    assert ".mp4" not in revisao


def test_build_sem_itens_mostra_as_oito_colunas_vazias(tmp_path, monkeypatch):
    html = _gera(home_de(tmp_path), tmp_path / "board.html", monkeypatch).decode("utf-8")

    for chave in CHAVES:
        assert f'data-coluna="{chave}"' in html
    assert "(vazia)" in html


def test_out_padrao_grava_board_html_no_diretorio_atual(tmp_path, monkeypatch):
    monkeypatch.setenv("SIMPLICIO_FACTORY_HOME", str(home_de(tmp_path)))
    monkeypatch.chdir(tmp_path)

    code, _, err = run_cli(["build"])

    assert code == 0, err
    assert (tmp_path / "board.html").is_file()


def test_template_vai_no_pacote():
    import importlib.resources as recursos

    template = recursos.files("simplicio_factory.plugins.board").joinpath("templates/board.html.tpl")
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert template.is_file()
    assert "plugins/board/templates/*.tpl" in pyproject


UI_JS = r"""
const path = require('path');
const fs = require('fs');
let chromium;
try {
  ({ chromium } = require('playwright'));
} catch (e) {
  console.log('SKIP: módulo playwright indisponível para o node');
  process.exit(3);
}
const [html, outDir] = process.argv.slice(2);
(async () => {
  const exe = chromium.executablePath();
  if (!exe || !fs.existsSync(exe)) {
    console.log('SKIP: navegador Chromium ausente em ' + exe);
    process.exit(3);
  }
  const browser = await chromium.launch();
  const resultados = [];
  for (const largura of [375, 1440]) {
    const page = await browser.newPage({ viewport: { width: largura, height: 800 } });
    await page.goto('file://' + html);
    const medidas = await page.evaluate(() => ({
      rolagem: document.documentElement.scrollWidth,
      janela: document.documentElement.clientWidth,
    }));
    await page.screenshot({ path: path.join(outDir, 'board-' + largura + '.png'), fullPage: true });
    resultados.push({ largura, ...medidas });
    await page.close();
  }
  await browser.close();
  console.log(JSON.stringify(resultados));
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
"""


@pytest.mark.ui
def test_ui_sem_rolagem_horizontal_em_375_e_1440(tmp_path, monkeypatch):
    node = shutil.which("node")
    if node is None:
        pytest.skip("node ausente: o teste ui precisa de node com o pacote playwright")
    js = tmp_path / "medir_board.js"
    js.write_text(UI_JS, encoding="utf-8")
    home = home_de(tmp_path)
    monta_quatro_itens(home)
    html = tmp_path / "board.html"
    _gera(home, html, monkeypatch)
    lib = Path(node).resolve().parents[1] / "lib" / "node_modules"
    env = {**os.environ, "NODE_PATH": str(lib)}

    proc = subprocess.run(
        [node, str(js), str(html), str(tmp_path)],
        capture_output=True,
        text=True,
        env=env,
        timeout=180,
    )

    if proc.returncode == 3:
        pytest.skip(proc.stdout.strip() or "navegador indisponível")
    assert proc.returncode == 0, proc.stderr
    medidas = json.loads(proc.stdout.strip().splitlines()[-1])
    assert [m["largura"] for m in medidas] == [375, 1440]
    for m in medidas:
        assert m["rolagem"] <= m["janela"], f"rolagem horizontal em {m['largura']} px: {m}"
    assert (tmp_path / "board-375.png").is_file()
    assert (tmp_path / "board-1440.png").is_file()
