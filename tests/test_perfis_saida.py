"""Perfis de saída: `saida.qualidade` com os valores master, lite e thumb (critério A do BRASA, etapa 1).

- os argumentos do ffmpeg por perfil são uma função pura (nada roda aqui);
- o enum do schema aceita exatamente os três perfis e recusa o resto;
- thumb gera PNG do quadro 0 e nunca um MP4 (com ffmpeg real; pula com motivo explícito sem ffmpeg).
"""
import shutil
import subprocess

import pytest
import yaml

from conftest import LOTHUS
from simplicio_video import perfis
from simplicio_video.contract import schema_errors

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def _tem(args, opcao, valor):
    """`opcao valor` aparece como par consecutivo na lista de argumentos."""
    return any(args[i] == opcao and args[i + 1] == valor for i in range(len(args) - 1))


def _valor(args, opcao):
    i = args.index(opcao)
    return args[i + 1]


def _ffmpeg_ou_pula():
    if not (shutil.which("ffmpeg") and shutil.which("ffprobe")):
        pytest.skip("ffmpeg/ffprobe ausentes neste ambiente: o teste do thumb precisa deles para gerar o quadro")


# ---------------------------------------------------------------- (1) argumentos por perfil, sem ffmpeg

def test_master_h264_crf16_maxrate_bufsize_bt709_aac320_faststart():
    a = perfis.args_saida("master")
    assert _tem(a, "-c:v", "libx264")
    assert _tem(a, "-crf", "16")
    assert _tem(a, "-maxrate", "32M")
    assert _tem(a, "-bufsize", "64M")
    tags = set(_valor(a, "-x264-params").split(":"))
    assert {"colorprim=bt709", "transfer=bt709", "colormatrix=bt709"} <= tags
    assert _tem(a, "-c:a", "aac")
    assert _tem(a, "-b:a", "320k")
    assert _tem(a, "-movflags", "+faststart")


def test_lite_h264_maxrate_10m_aac_192k():
    a = perfis.args_saida("lite")
    assert _tem(a, "-c:v", "libx264")
    assert _tem(a, "-maxrate", "10M")
    assert _tem(a, "-c:a", "aac")
    assert _tem(a, "-b:a", "192k")
    assert "32M" not in a and "320k" not in a  # o lite não herda os números do master


def test_master_e_lite_sao_perfis_diferentes():
    assert perfis.args_saida("master") != perfis.args_saida("lite")


def test_thumb_nao_tem_argumentos_de_video_nem_fade():
    a = perfis.args_thumb()
    assert "libx264" not in a
    assert _tem(a, "-frames:v", "1")
    assert not any("fade" in x for x in a)


def test_args_saida_recusa_thumb_e_perfil_desconhecido():
    with pytest.raises(ValueError, match="thumb"):
        perfis.args_saida("thumb")
    with pytest.raises(ValueError, match="ultra"):
        perfis.args_saida("ultra")


def test_perfil_de_render_do_hyperframes():
    """master e lite pedem o render `delivery` ao HyperFrames; thumb pede `draft` (só o quadro 0 importa)."""
    assert perfis.qualidade_render("master") == "delivery"
    assert perfis.qualidade_render("lite") == "delivery"
    assert perfis.qualidade_render("thumb") == "draft"


# ---------------------------------------------------------------- (2) enum do schema

def _lothus_com(valor):
    d = yaml.safe_load(LOTHUS.read_text(encoding="utf8"))
    d["saida"]["qualidade"] = valor
    return d


@pytest.mark.parametrize("valor", ["master", "lite", "thumb"])
def test_schema_aceita_cada_perfil(valor):
    assert schema_errors(_lothus_com(valor)) == []


@pytest.mark.parametrize("valor", ["delivery", "looks", "draft", "ultra", "MASTER", ""])
def test_schema_rejeita_qualquer_outro_valor(valor):
    errs = schema_errors(_lothus_com(valor))
    assert errs and any("qualidade" in e for e in errs), errs


# ---------------------------------------------------------------- (3) thumb não produz MP4 (ffmpeg real)

@pytest.fixture
def raw_vermelho_depois_azul(tmp_path):
    _ffmpeg_ou_pula()
    raw = tmp_path / "raw.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y",
                    "-f", "lavfi", "-i", "color=c=red:s=160x90:r=10:d=0.5",
                    "-f", "lavfi", "-i", "color=c=blue:s=160x90:r=10:d=0.5",
                    "-filter_complex", "[0][1]concat=n=2:v=1:a=0[v]", "-map", "[v]",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(raw)], check=True)
    return raw


def _rgb(path):
    return subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                          capture_output=True, check=True).stdout


def test_thumb_gera_png_do_quadro_zero_sem_fade_e_nao_gera_mp4(raw_vermelho_depois_azul, tmp_path):
    raw = raw_vermelho_depois_azul
    png = tmp_path / "capa.png"
    perfis.encerra_thumb(raw, png)
    assert png.read_bytes()[:8] == PNG_MAGIC
    # nenhum MP4 novo: só o raw que já existia
    assert sorted(p.name for p in tmp_path.glob("*.mp4")) == ["raw.mp4"]
    # é o quadro 0 (vermelho) e não fica escurecido por fade: pixel igual ao do próprio ffmpeg no quadro 0
    ref = tmp_path / "ref.png"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(raw), "-frames:v", "1", str(ref)], check=True)
    assert _rgb(png) == _rgb(ref)
    r, g, b = _rgb(png)[:3]
    assert r >= 240 and g <= 20 and b <= 20, (r, g, b)


def test_thumb_nao_grava_video_quando_o_destino_e_mp4(raw_vermelho_depois_azul, tmp_path):
    """Pedir thumb não pode deixar um MP4 de saída no lugar: o destino vira PNG e o raw fica intocado."""
    raw = raw_vermelho_depois_azul
    antes = raw.read_bytes()
    destino = tmp_path / "capa.mp4"
    res = perfis.encerra_thumb(raw, destino)
    assert res["saida"].suffix == ".png" and res["saida"].name == "capa.png"
    assert not destino.exists()
    assert raw.read_bytes() == antes
