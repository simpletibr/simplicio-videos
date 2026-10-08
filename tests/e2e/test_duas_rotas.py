"""Fluxo ponta a ponta das duas rotas de produção (#90, épico #81).

Roda pelo CLI principal (`simplicio-video`), como a pessoa roda, com um único desvio: o renderer do studio
é trocado pelo StubRenderer (o HyperFrames não roda nos testes). Sem rede: o conftest bloqueia sockets em
testes sem marcador de rede. Sem modelo: o fluxo não recebe cliente de LLM (ver o teste de NoLLM).

Reaproveita os helpers de tests/factory/plugins/media (_fixtures.py e _attach_fixtures.py) sem editá-los.
Não há conftest.py nesta pasta (#43).
"""

from __future__ import annotations

import json
import re
import socket
import sys
import time
from html.parser import HTMLParser
from pathlib import Path

import pytest
import yaml
from pytest_socket import SocketBlockedError

from tests.factory.plugins.media._attach_fixtures import (
    CONTEUDO,
    MEDIA_ID,
    arquivo_gerado,
    escreve_brand,
    prompt_file,
    sha256,
)
from tests.factory.plugins.media._fixtures import (
    ESTIMATIVA,
    ambiente,
    eventos,
    le_item,
    run_cli,
)

ROOT = Path(__file__).resolve().parents[2]
DOC = ROOT / "docs" / "host" / "duas-rotas.md"
DRAFT_MODELO = (
    ROOT / "tests" / "factory" / "plugins" / "studio" / "fixtures" / "draft.json"
)
BRAND_MODELO = (
    ROOT / "tests" / "factory" / "plugins" / "studio" / "fixtures" / "brand.json"
)

DET_ID = "itm_01HZE2EDET000000000001"
AI_ID = "itm_01HZE2EAI0000000000001"
# Fatos da marca de teste: os mesmos do brand.json do studio, para o claim guard aceitar as claims do Draft.
FATOS = json.loads(BRAND_MODELO.read_text(encoding="utf-8"))["facts"]

# Comandos que o doc de duas rotas precisa citar; cada um tem de existir no CLI real.
COMANDOS_OBRIGATORIOS = (
    "generate quote",
    "generate approve",
    "generate start",
    "generate show",
    "media attach",
    "board list",
    "board comment",
    "board review",
    "board build",
    "make",
    "make preview",
)
# SDKs de modelo: se o fluxo importar algum, o import falha e o teste de NoLLM quebra.
SDKS_DE_MODELO = (
    "anthropic",
    "openai",
    "google.generativeai",
    "google.genai",
    "mistralai",
    "cohere",
    "ollama",
    "langchain_openai",
)


@pytest.fixture
def fluxo(monkeypatch, tmp_path):
    """Store e workspace isolados, orçamento de 500 créditos, relógio fixo, marca com os fatos do Draft e o
    StubRenderer no lugar do EngineRenderer. Devolve a pasta SIMPLICIO_FACTORY_HOME."""
    from simplicio_factory.plugins.studio import renderer
    from simplicio_factory.testkit import StubRenderer

    home, _workspace = ambiente(monkeypatch, tmp_path, media_credits=500)
    escreve_brand(home, facts=FATOS)
    monkeypatch.setattr(
        renderer, "EngineRenderer", lambda out_dir: StubRenderer(out_dir)
    )
    return home


def cli(*argv: str) -> tuple[int, str, str]:
    """Roda `simplicio-video <argv>` pelo despacho principal e devolve (código, stdout, stderr)."""
    from simplicio_video import cli as principal

    return run_cli(principal.main, list(argv))


def draft_para(caminho: Path, item_id: str) -> Path:
    """Draft do modelo do studio, com o item_id dado. Escrito em `caminho`."""
    dados = json.loads(DRAFT_MODELO.read_text(encoding="utf-8"))
    dados["item_id"] = item_id
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(
        json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return caminho


def transicoes(home: Path, item_id: str) -> list[tuple[str, str, str]]:
    """(de, para, rota) de cada item.state_changed do item, na ordem do log."""
    return [
        (e.data["from"], e.data["to"], e.data["route"])
        for e in eventos(home, "item.state_changed")
        if e.item_id == item_id
    ]


def roda_determinista(home: Path, tmp_path: Path) -> None:
    """Rota determinística: `make --from` cria o item e roda o estágio até rendered (sem orçamento)."""
    draft = draft_para(tmp_path / "draft-det.json", DET_ID)
    code, out, err = cli("make", "--from", str(draft))
    assert code == 0, err
    assert f"{DET_ID}: rendered" in out


def roda_ai(home: Path, tmp_path: Path) -> None:
    """Rota ai_assisted: idea -> drafted (o kernel), orçamento e aprovação, geração, anexo com recibo e render."""
    from simplicio_factory.contracts import Item, transition
    from simplicio_factory.contracts.json_store import JsonStore

    store = JsonStore(home)
    item = Item(
        id=AI_ID,
        brand="clinica-exemplo",
        state="idea",
        production={"route": "ai_assisted", "steps": []},
    )
    store.save_item(item)
    transition(item, "drafted", store)
    draft_para(
        home / "studio" / AI_ID / "draft.json", AI_ID
    )  # o Draft fica na pasta do item (runbook, passo 9)

    code, _, err = cli(
        "generate",
        "quote",
        AI_ID,
        "--provider",
        "real-oficial",
        "--estimate-ref",
        ESTIMATIVA,
        "--credits",
        "120",
    )
    assert code == 0, err
    code, _, err = cli("generate", "approve", AI_ID, "--by", "Wesley", "--yes")
    assert code == 0, err
    code, _, err = cli("generate", "start", AI_ID)
    assert code == 0, err
    midia = arquivo_gerado(tmp_path)
    code, _, err = cli(
        "media",
        "attach",
        AI_ID,
        str(midia),
        "--source",
        "real-oficial",
        "--media-id",
        MEDIA_ID,
        "--prompt-file",
        str(prompt_file(tmp_path)),
    )
    assert code == 0, err
    assert le_item(home, AI_ID).state == "generated"
    code, out, err = cli("make", AI_ID)
    assert code == 0, err
    assert f"{AI_ID}: rendered" in out


def test_rota_deterministica_chega_a_rendered(fluxo, tmp_path):
    """Regressão da #33: a rota padrão segue idea -> drafted -> rendering -> rendered, sem orçamento."""
    roda_determinista(fluxo, tmp_path)

    assert le_item(fluxo, DET_ID).state == "rendered"
    assert transicoes(fluxo, DET_ID) == [
        ("idea", "drafted", "deterministic"),
        ("drafted", "rendering", "deterministic"),
        ("rendering", "rendered", "deterministic"),
    ]
    estado = json.loads(
        (fluxo / "studio" / DET_ID / "studio.json").read_text(encoding="utf-8")
    )
    assert Path(estado["stages"]["studio"]["mp4"]).is_file()


def test_rota_ai_assisted_de_idea_a_rendered(fluxo, tmp_path):
    """Rota ai_assisted: orçamento aprovado, geração, anexo com recibo e render final, em menos de 5 s."""
    inicio = time.perf_counter()
    roda_ai(fluxo, tmp_path)
    decorrido = time.perf_counter() - inicio

    assert decorrido < 5, f"fluxo ai_assisted levou {decorrido:.2f} s (limite 5 s)"
    assert le_item(fluxo, AI_ID).state == "rendered"
    assert transicoes(fluxo, AI_ID) == [
        ("idea", "drafted", "ai_assisted"),
        ("drafted", "quoted", "ai_assisted"),
        ("quoted", "approved", "ai_assisted"),
        ("approved", "generating", "ai_assisted"),
        ("generating", "generated", "ai_assisted"),
        ("generated", "rendering", "ai_assisted"),
        ("rendering", "rendered", "ai_assisted"),
    ]
    recibo = json.loads(
        (fluxo / "studio" / AI_ID / "media.json").read_text(encoding="utf-8")
    )
    assert recibo["sha256"] == sha256(CONTEUDO)
    assert recibo["media_id"] == MEDIA_ID


class _CartoesPorColuna(HTMLParser):
    """Para cada cartão (<article class="card" data-item=ID>), guarda a coluna (<section data-coluna=CHAVE>) em que ele está."""

    def __init__(self) -> None:
        super().__init__()
        self.coluna: str | None = None
        self.cartoes: dict[str, list[str]] = {}

    def handle_starttag(self, tag, attrs):
        atributos = dict(attrs)
        if tag == "section" and atributos.get("data-coluna"):
            self.coluna = atributos["data-coluna"]
        if (
            tag == "article"
            and "card" in (atributos.get("class") or "").split()
            and atributos.get("data-item")
        ):
            self.cartoes.setdefault(atributos["data-item"], []).append(self.coluna)

    def handle_endtag(self, tag):
        if tag == "section":
            self.coluna = None


def test_board_html_tem_os_dois_cartoes_nas_colunas_certas(fluxo, tmp_path):
    """Depois das duas rotas, o board.html põe o determinístico aprovado em Pronto e o ai_assisted com
    alterações pedidas em Revisão."""
    roda_determinista(fluxo, tmp_path)
    roda_ai(fluxo, tmp_path)
    code, _, err = cli(
        "board", "review", DET_ID, "approve", "--by", "Ana", "--note", "pode publicar"
    )
    assert code == 0, err
    code, _, err = cli(
        "board", "review", AI_ID, "changes", "--by", "Ana", "--note", "refazer o final"
    )
    assert code == 0, err

    saida = tmp_path / "board.html"
    code, _, err = cli("board", "build", "--out", str(saida))
    assert code == 0, err

    parser = _CartoesPorColuna()
    parser.feed(saida.read_text(encoding="utf-8"))
    assert parser.cartoes == {DET_ID: ["pronto"], AI_ID: ["revisao"]}


@pytest.mark.filterwarnings("ignore:A test tried to use socket.socket:UserWarning")
def test_fluxo_completo_sem_llm_e_sem_rede(fluxo, tmp_path, monkeypatch):
    """Sem modelo e sem rede: os SDKs de modelo ficam bloqueados (importar falha) e o socket está bloqueado.

    O fluxo não tem ponto de injeção de LLM (nenhum plugin recebe um cliente de modelo), então a garantia vem
    do bloqueio dos SDKs, e não de um ForbiddenLLM injetado: se algum caminho tentar importar um SDK, o teste quebra.
    """
    with pytest.raises(SocketBlockedError):
        socket.socket()
    for nome in SDKS_DE_MODELO:
        monkeypatch.setitem(sys.modules, nome, None)

    roda_determinista(fluxo, tmp_path)
    roda_ai(fluxo, tmp_path)

    assert le_item(fluxo, DET_ID).state == "rendered"
    assert le_item(fluxo, AI_ID).state == "rendered"


def _comandos_citados(texto: str) -> set[tuple[str, ...]]:
    """Cada `simplicio-video <palavras>` do texto, até o primeiro token que não é palavra minúscula (opção, ITEM, arquivo)."""
    achados: set[tuple[str, ...]] = set()
    for casamento in re.finditer(r"simplicio-video((?: +[a-z][a-z-]*(?!\w))+)", texto):
        achados.add(tuple(casamento.group(1).split()))
    return achados


def test_doc_duas_rotas_existe_com_front_matter_da_issue():
    assert DOC.is_file(), "docs/host/duas-rotas.md ausente (issue #90)"
    casamento = re.match(r"^---\n(.*?)\n---\n", DOC.read_text(encoding="utf-8"), re.S)
    assert casamento, "docs/host/duas-rotas.md sem front matter"
    meta = yaml.safe_load(casamento.group(1))
    for chave in ("title", "summary", "commands", "issue", "last_verified"):
        assert chave in meta, f"front matter sem {chave}"
    assert meta["issue"] == 90
    assert str(meta["last_verified"]) == "2026-10-08"


def test_doc_duas_rotas_cita_so_comandos_reais():
    """Todo `simplicio-video <comando>` do doc existe no CLI (o --help responde 0), e os comandos da rota estão lá."""
    assert DOC.is_file(), "docs/host/duas-rotas.md ausente (issue #90)"
    texto = DOC.read_text(encoding="utf-8")
    citados = _comandos_citados(texto)

    faltando = [c for c in COMANDOS_OBRIGATORIOS if tuple(c.split()) not in citados]
    assert not faltando, f"doc sem os comandos da rota: {faltando}"

    invalidos = []
    for palavras in sorted(citados):
        code, out, _err = cli(*palavras, "--help")
        if code != 0 or "usage" not in out.lower():
            invalidos.append(" ".join(palavras))
    assert not invalidos, f"doc cita comando que o CLI não tem: {invalidos}"
