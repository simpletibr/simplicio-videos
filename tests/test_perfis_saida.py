"""Perfis de saída: `saida.qualidade` com os valores master, lite e thumb (critério A do BRASA, etapa 1).

- os argumentos do ffmpeg por perfil são uma função pura (nada roda aqui);
- o enum do schema aceita exatamente os três perfis e recusa o resto;
- thumb gera PNG do quadro 0 e nunca um MP4 (com ffmpeg real; pula com motivo explícito sem ffmpeg).
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from conftest import FIXTURE, have_render_tools
from simplicio_video import contract as ct
from simplicio_video import perfis, render, voice
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

def _contrato_com(valor):
    d = yaml.safe_load((FIXTURE / "contract.yaml").read_text(encoding="utf8"))
    d["saida"]["qualidade"] = valor
    return d


@pytest.mark.parametrize("valor", ["master", "lite", "thumb"])
def test_schema_aceita_cada_perfil(valor):
    assert schema_errors(_contrato_com(valor)) == []


@pytest.mark.parametrize("valor", ["delivery", "looks", "draft", "ultra", "MASTER", ""])
def test_schema_rejeita_qualquer_outro_valor(valor):
    errs = schema_errors(_contrato_com(valor))
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


# ---------------------------------------------------------------- A aplicado de ponta a ponta: master.sh no MP4 final

ROOT = Path(__file__).resolve().parents[1]
MASTER_SH = ROOT / "src" / "simplicio_video" / "engine" / "master.sh"


def _node_e_ffmpeg_ou_pula():
    if not (shutil.which("node") and shutil.which("ffmpeg") and shutil.which("ffprobe")):
        pytest.skip("node/ffmpeg/ffprobe ausentes: o master.sh lê o spec.json com node e encoda com ffmpeg")


def _workdir_com_raw(tmp_path, perfil_args):
    """Pasta de trabalho mínima que o master.sh espera: scripts/master.sh, spec.json, out/raw.mp4 (3 s, vídeo + áudio)."""
    wd = tmp_path / "wd"
    (wd / "scripts").mkdir(parents=True)
    (wd / "out").mkdir()
    shutil.copy2(MASTER_SH, wd / "scripts" / "master.sh")
    (wd / "spec.json").write_text('{"audio": {"master": {"target_lufs": -14, "true_peak_db": -1.5}}}', encoding="utf8")
    subprocess.run(["ffmpeg", "-v", "error", "-y",
                    "-f", "lavfi", "-i", "testsrc=s=180x320:r=30:d=3",
                    "-f", "lavfi", "-i", "anoisesrc=color=pink:seed=7:sample_rate=48000:duration=3",
                    "-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-crf", "23", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "128k", "-shortest", str(wd / "out" / "raw.mp4")], check=True)
    if perfil_args is not None:
        (wd / "perfil.args").write_text("\n".join(perfil_args) + "\n", encoding="utf8")
    return wd


def _rodar_master(wd, *extra):
    p = subprocess.run(["bash", "scripts/master.sh", "out/raw.mp4", "out/final.mp4", *extra], cwd=wd, capture_output=True, text=True)
    assert p.returncode == 0, p.stderr[-2000:]
    return wd / "out" / "final.mp4"


def _sondar(mp4):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,codec_name,color_primaries,color_transfer,color_space",
                          "-of", "json", str(mp4)], capture_output=True, text=True, check=True).stdout
    return {f["codec_type"]: f for f in json.loads(out)["streams"]}


def _kbps_audio(mp4):
    """Taxa média real do áudio: bytes dos pacotes AAC sobre a duração (o bit_rate do cabeçalho não é confiável em clipes curtos)."""
    tam = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries", "packet=size",
                          "-of", "default=noprint_wrappers=1:nokey=1", str(mp4)], capture_output=True, text=True, check=True).stdout.split()
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries", "format=duration",
                                "-of", "csv=p=0", str(mp4)], capture_output=True, text=True, check=True).stdout)
    return sum(int(x) for x in tam) * 8 / dur / 1000


def _tamanhos_video(mp4):
    """Tamanho de cada pacote de vídeo: igual ao do raw quando o vídeo foi copiado, diferente quando foi recodificado."""
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "packet=size",
                          "-of", "default=noprint_wrappers=1:nokey=1", str(mp4)], capture_output=True, text=True, check=True).stdout
    return [int(x) for x in out.split()]


def test_master_sh_aplica_o_perfil_master_no_mp4_final(tmp_path):
    _node_e_ffmpeg_ou_pula()
    mp4 = _rodar_master(_workdir_com_raw(tmp_path, perfis.args_saida("master")), "perfil.args")
    s = _sondar(mp4)
    assert s["video"]["codec_name"] == "h264"
    assert (s["video"]["color_primaries"], s["video"]["color_transfer"], s["video"]["color_space"]) == ("bt709", "bt709", "bt709")
    assert s["audio"]["codec_name"] == "aac"
    # o pedido `-b:a 320k` está nos argumentos (teste puro acima). O encoder AAC nativo do ffmpeg entrega ~241 kbps em estéreo
    # mesmo com 320k pedidos (medido em 3, 10 e 30 s), então o teste exige só que o áudio saia bem acima do caminho de 192k.
    assert _kbps_audio(mp4) > 1.2 * 192, _kbps_audio(mp4)
    dados = mp4.read_bytes()
    assert dados.index(b"moov") < dados.index(b"mdat"), "+faststart: moov antes de mdat"


def test_master_sh_aplica_o_perfil_lite_no_mp4_final(tmp_path):
    _node_e_ffmpeg_ou_pula()
    wd = _workdir_com_raw(tmp_path, perfis.args_saida("lite"))
    mp4 = _rodar_master(wd, "perfil.args")
    assert _tamanhos_video(mp4) != _tamanhos_video(wd / "out" / "raw.mp4"), "o perfil lite recodifica o vídeo"
    s = _sondar(mp4)
    assert s["video"]["codec_name"] == "h264"
    assert s["audio"]["codec_name"] == "aac"
    assert 0.9 * 192 <= _kbps_audio(mp4) <= 1.1 * 192


def test_master_sh_sem_perfil_mantem_o_caminho_anterior(tmp_path):
    """Sem o terceiro argumento o master.sh faz o que fazia antes: vídeo copiado e AAC 192k (bundles antigos)."""
    _node_e_ffmpeg_ou_pula()
    wd = _workdir_com_raw(tmp_path, None)
    mp4 = _rodar_master(wd)
    assert _tamanhos_video(mp4) == _tamanhos_video(wd / "out" / "raw.mp4"), "sem perfil o vídeo é copiado"
    s = _sondar(mp4)
    assert s["video"]["codec_name"] == "h264"
    assert s["audio"]["codec_name"] == "aac"
    assert 0.9 * 192 <= _kbps_audio(mp4) <= 1.1 * 192


# ---------------------------------------------------------------- thumb no render real (HyperFrames + ffmpeg; marcador render)

@pytest.mark.render
@pytest.mark.skipif(not have_render_tools(), reason="precisa de node, npx e ffmpeg")
def test_render_thumb_do_mini_gera_png_e_nenhum_mp4(mini):
    d = yaml.safe_load(mini.read_text(encoding="utf8"))
    d["saida"]["qualidade"] = "thumb"
    mini.write_text(yaml.safe_dump(d, allow_unicode=True, sort_keys=False), encoding="utf8")
    c = ct.load(mini)
    voice.run(c, log=lambda *_: None)
    out = mini.parent / "out" / "mini.mp4"
    res = render.render_local(ct.load(mini), out=out, log=lambda *_: None)
    assert res["perfil"] == "thumb"
    png = out.with_suffix(".png")
    assert png.read_bytes()[:8] == PNG_MAGIC
    assert not out.exists(), "thumb não grava MP4"
    assert not (mini.parent / "render.manifest.json").exists(), "thumb não grava manifesto de entrega"
