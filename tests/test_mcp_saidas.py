"""Revisão final do #177 (rodada 4): o que as tools que gravam (shorts, media, edit) aceitam como saída e como entrada do pipeline.

Cada cenário foi provado com o CLI real nos probes da revisão (rev177_final/probe_*.py): o -o era engolido por outra opção e o
arquivo ia para o default relativo, o EDL relativo gravava os intermediários no cwd do servidor, e o `..` passava. Os testes
recusam antes de chegar ao CLI (o _cli é gravado, não roda) e os controles mostram que o caso certo continua valendo."""
import pytest

from simplicio_video import mcp_server

FONTE = "/abs/fonte.mp4"
WORDS = "/abs/words.json"
PLANO = "/abs/plano.json"
DESCRICOES = {nome: desc for nome, _, desc in mcp_server.TOOLS}


@pytest.fixture
def cli(monkeypatch):
    chamadas = []

    def falso(argv, codigos_ok=(0,)):
        chamadas.append(list(argv))
        return {"ok": True, "rc": 0, "result": None, "log": ""}

    monkeypatch.setattr(mcp_server, "_cli", falso)
    return chamadas


# ---------------------------------------------------------------------------------- F1: shorts, -o engolido e default relativo

@pytest.mark.parametrize("argv", [
    ["plan", FONTE, "--transcript", WORDS, "--ou", "-o", "/abs/ok.json"],       # --ou engole o -o: gravava shorts/plan.json
    ["plan", FONTE, "--transcript", WORDS, "--fit", "-o", "/abs/ok.json"],      # idem com uma opção genérica
    ["plan", FONTE, "--transcript", WORDS, "--out=/abs/x", "-o", "/abs/ok.json"],
    ["cut", FONTE, PLANO, "--transcript", "-o", "/abs/y"],                      # gravava shorts/c01.mp4 e manifest.json
])
def test_shorts_recusa_o_o_engolido(cli, argv):
    r = mcp_server.video_shorts(argv=argv)
    assert r["ok"] is False and cli == [], r


# ---------------------------------------------------------------------------------- F2 e F3: edit, EDL e pasta de pack absolutos

@pytest.mark.parametrize("argv", [
    ["render", "edit/edl.json", "-o", "/abs/out/final.mp4"],    # o render grava os intermediários na pasta do EDL
    ["render", "../edl.json", "-o", "/abs/out/final.mp4"],
    ["pack", "rel_edit"],                                       # o pack grava takes_packed.md na pasta dele
    ["pack", "/abs/../edit"],
])
def test_edit_render_e_pack_exigem_entrada_absoluta_e_sem_pai(cli, argv):
    r = mcp_server.video_edit(argv=argv)
    assert r["ok"] is False and cli == [], r


# ---------------------------------------------------------------------------------- F5 e F6: media, todas as grafias de -o

@pytest.mark.parametrize("argv", [
    ["sheet", "/abs/x.mp4", "-o=/abs/../x.png"],                 # -o=X
    ["sheet", "/abs/x.mp4", "-orel.png"],                        # -oX colado
    ["sheet", "/abs/x.mp4", "--out=rel.png"],                    # --out=X
    ["sheet", "/abs/x.mp4", "--output", "rel.png"],              # --output
    ["sheet", "/abs/x.mp4", "--ou", "/abs/../x.png", "-o", "/abs/ok.png"],   # abreviação com .. e um -o bom
    ["sheet", "/abs/x.mp4", "--every=4", "-o", "/abs/ok.png"],   # --x=valor engole o -o
    ["sheet", "/abs/x.mp4", "--mystery", "-o", "/abs/ok.png"],   # opção desconhecida engole o -o
])
def test_media_recusa_todas_as_grafias_de_saida_e_o_o_engolido(cli, argv):
    r = mcp_server.video_media(argv=argv)
    assert r["ok"] is False and cli == [], r


# ---------------------------------------------------------------------------------- F7: o texto diz que o -o existente é sobrescrito

def test_media_e_shorts_dizem_que_o_o_existente_e_sobrescrito_e_nao_so_arquivos_novos():
    for nome in ("video.media", "video.shorts"):
        assert "overwritten" in DESCRICOES[nome], nome
        assert "new files" not in DESCRICOES[nome] and "new file" not in DESCRICOES[nome], nome
    assert "new file" not in (mcp_server.video_media.__doc__ or "")
    assert "new file" not in (mcp_server.video_shorts.__doc__ or "")


# ---------------------------------------------------------------------------------- regressões e controles (já valiam antes)

@pytest.mark.parametrize("argv", [
    ["plan", FONTE, "--transcript", WORDS],        # sem -o: nada de default relativo
    ["cut", FONTE, PLANO],
    ["run", FONTE, "--transcript", WORDS],
])
def test_shorts_sem_o_e_recusado_e_o_inspect_sem_o_so_imprime(cli, argv):
    assert mcp_server.video_shorts(argv=argv)["ok"] is False and cli == []
    assert mcp_server.video_shorts(argv=["inspect", FONTE])["ok"] is True and cli == [["shorts", "inspect", FONTE]]


def test_controles_com_o_absoluto_seguem_valendo(cli):
    mcp_server.video_shorts(argv=["plan", FONTE, "--transcript", WORDS, "-o", "/abs/out/plan.json"])
    mcp_server.video_shorts(argv=["cut", FONTE, PLANO, "-o", "/abs/out/cortes"])
    mcp_server.video_edit(argv=["render", "/abs/out/edl.json", "-o", "/abs/out/final.mp4"])
    mcp_server.video_edit(argv=["pack", "/abs/out/edit"])
    mcp_server.video_media(argv=["sheet", "/abs/x.mp4", "-o", "/abs/ok.png", "--every", "4"])
    assert cli == [
        ["shorts", "plan", FONTE, "--transcript", WORDS, "-o", "/abs/out/plan.json"],
        ["shorts", "cut", FONTE, PLANO, "-o", "/abs/out/cortes"],
        ["edit", "render", "/abs/out/edl.json", "-o", "/abs/out/final.mp4"],
        ["edit", "pack", "/abs/out/edit"],
        ["media", "sheet", "/abs/x.mp4", "-o", "/abs/ok.png", "--every", "4"],
    ]


def test_edit_help_nao_e_barrado_pela_regra_do_edl(cli):
    mcp_server.video_edit(argv=["render", "--help"])
    mcp_server.video_edit(argv=["pack", "-h"])
    assert cli == [["edit", "render", "--help"], ["edit", "pack", "-h"]]


# ---------------------------------------------------------------------------------- F8: `..` nos caminhos do Hypit (já era recusado)

@pytest.mark.parametrize("argv", [
    ["media", "frames", "/abs/../x.mp4"],
    ["media", "cut", "/abs/a.mp4", "--to", "/abs/../x.mp4"],
    ["media", "cut", "/abs/a.mp4", "--to=/abs/../x.mp4"],
    ["get", "b", "--to", "/abs/../x.mp4"],
    ["get", "b", "--to=/abs/../x.mp4"],
])
def test_hypit_recusa_o_segmento_pai_em_qualquer_caminho(cli, argv):
    r = mcp_server.video_clone(argv=argv)
    assert r["ok"] is False and cli == [], r


def test_hypit_aceita_caminho_absoluto_sem_pai(cli):
    mcp_server.video_clone(argv=["get", "b", "--to", "/abs/ok.mp4"])
    assert cli == [["clone", "get", "b", "--to", "/abs/ok.mp4"]]
