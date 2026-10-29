"""`simplicio-video media`: the pure parts (cues, subtitles, filter graphs, timing plan) and one real ffmpeg run on a tiny clip."""

from __future__ import annotations

import json
import shutil
import subprocess

import pytest

from simplicio_video import media


def _cues(tmp_path, cues, name="cues.json"):
    p = tmp_path / name
    p.write_text(json.dumps({"schema": media.CUES_SCHEMA, "cues": cues}), encoding="utf8")
    return p


def test_read_cues_ordena_e_recusa_schema_errado(tmp_path):
    p = _cues(tmp_path, [{"start": 2, "end": 3, "text": "b"}, {"start": 0, "end": 1, "text": "a"}])
    assert [c["text"] for c in media.read_cues(p)] == ["a", "b"]
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"schema": "outro", "cues": []}), encoding="utf8")
    with pytest.raises(media.MediaError, match="schema"):
        media.read_cues(bad)


@pytest.mark.parametrize("cue", [{"start": 3, "end": 3, "text": "x"}, {"start": -1, "end": 2, "text": "x"}, {"start": "a", "end": 2}])
def test_read_cues_recusa_tempo_invalido(tmp_path, cue):
    with pytest.raises(media.MediaError):
        media.read_cues(_cues(tmp_path, [cue]))


def test_write_subs_srt_tem_virgula_no_tempo_e_quebra_linha(tmp_path):
    dest = media.write_subs([{"start": 1.5, "end": 3.25, "text": "uma frase bem longa para quebrar em duas linhas"}],
                            tmp_path / "s.srt", "band", wrap=20)
    txt = dest.read_text(encoding="utf8")
    assert "00:00:01,500 --> 00:00:03,250" in txt
    assert "\n" in txt.split("\n\n")[0].split("-->")[1]  # text has more than one line


def test_write_subs_ass_usa_estilo_e_quebra_com_N(tmp_path):
    dest = media.write_subs([{"start": 0, "end": 2, "text": "um dois tres quatro cinco seis sete oito nove dez onze"}],
                            tmp_path / "s.ass", "band", wrap=12)
    txt = dest.read_text(encoding="utf8")
    assert "Style: Media," in txt and ",5," in txt  # alignment 5 = centre, the band style
    assert r"\N" in txt
    assert "0:00:00.00,0:00:02.00" in txt


def test_write_subs_recusa_estilo_e_extensao(tmp_path):
    with pytest.raises(media.MediaError, match="style"):
        media.write_subs([], tmp_path / "s.ass", "neon")
    with pytest.raises(media.MediaError, match=".srt ou .ass"):
        media.write_subs([], tmp_path / "s.vtt", "band")


def test_parse_box_e_mask_filter():
    assert media.parse_box("150,622,430,104") == (150, 622, 430, 104)
    with pytest.raises(media.MediaError):
        media.parse_box("150,622,430")
    with pytest.raises(media.MediaError):
        media.parse_box("a,b,c,d")
    assert media.mask_filter((1, 2, 3, 4)) == "delogo=x=1:y=2:w=3:h=4:show=0"
    assert "enable='between(t,1,2.5)'" in media.mask_filter((1, 2, 3, 4), 1, 2.5)


def test_atempo_chain_divide_fator_acima_de_dois():
    assert media.atempo_chain(1.25) == ["atempo=1.250000"]
    assert media.atempo_chain(3.0)[0] == "atempo=2.0"
    assert len(media.atempo_chain(3.0)) == 2
    assert media.atempo_chain(0.25)[0] == "atempo=0.5"
    with pytest.raises(media.MediaError):
        media.atempo_chain(0)


def test_voice_plan_acelera_so_ate_o_limite_e_reporta_o_resto():
    cues = [{"start": 0.0, "end": 2.0, "audio": "a.wav"}, {"start": 3.0, "end": 4.0, "audio": "b.wav"}, {"start": 5.0, "end": 6.0}]
    plano = media.voice_plan(cues, {0: 2.2, 1: 5.0}, max_stretch=1.25)
    assert [p["index"] for p in plano] == [0, 1]  # the cue without audio is skipped
    assert plano[0]["speed"] == pytest.approx(1.1)
    assert plano[0]["overflow_seconds"] == 0.0
    assert plano[1]["speed"] == 1.25
    assert plano[1]["overflow_seconds"] == pytest.approx(5.0 / 1.25 - 1.0)


def test_voice_filter_atrasa_cada_clipe_no_inicio_certo():
    plano = [{"index": 0, "start": 1.5, "clip": "a.wav", "speed": 1.0},
             {"index": 1, "start": 4.0, "clip": "b.wav", "speed": 1.2}]
    filtro = media.voice_filter(plano, 6.0)
    assert "adelay=1500|1500" in filtro and "adelay=4000|4000" in filtro
    assert "atempo=1.200000" in filtro and filtro.count("atempo") == 1
    assert "amix=inputs=2" in filtro and filtro.endswith("[out]")


def test_parse_separa_posicionais_e_valores():
    pos, vals = media._parse(["reel.mp4", "--box", "1,2,3,4", "-o", "x.mp4", "--keep-length"])
    assert pos == ["reel.mp4"]
    assert vals == {"--box": "1,2,3,4", "-o": "x.mp4", "--keep-length": "1"}


def _ffmpeg_roda() -> bool:
    """A binary on the PATH is not enough: a broken build (missing dylib) is found and then aborts."""
    try:
        return subprocess.run(["ffmpeg", "-version"], capture_output=True).returncode == 0 and bool(shutil.which("ffprobe"))
    except OSError:
        return False


@pytest.mark.skipif(not _ffmpeg_roda(), reason="precisa de um ffmpeg e ffprobe que rodem")
def test_mask_e_subs_com_ffmpeg_real(tmp_path):
    src = tmp_path / "src.mp4"
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=240x320:rate=10:duration=2",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=2", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
                    "-shortest", str(src)], check=True)
    out = tmp_path / "masked.mp4"
    media.run_media(["mask", str(src), "--box", "10,200,100,40", "-o", str(out)])
    info = media.shorts.probe(out)
    assert info["width"] == 240 and info["has_audio"] is True
