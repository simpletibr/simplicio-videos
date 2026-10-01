import json

import pytest

from simplicio_video import contract as ct
from simplicio_video import voice


def test_file_provider_writes_lock(mini):
    lock = voice.run(ct.load(mini), log=lambda *_: None)
    m = lock["lines"]["vo1"]
    assert lock["provider"] == "file" and m["fits"] and abs(m["dur_s"] - 0.3) < 0.02
    assert (mini.parent / m["file"]).is_file()
    again = voice.run(ct.load(mini), log=lambda *_: None)  # cache hit -> same bytes
    assert again["lines"]["vo1"]["sha256"] == m["sha256"]


def test_gemini_without_key_is_clear_error(mini, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(SystemExit, match="GEMINI_API_KEY not set"):
        voice.run(ct.load(mini), provider="gemini", log=lambda *_: None)


@pytest.mark.parametrize("prov", ["elevenlabs", "xai"])
def test_stub_providers(mini, prov):
    with pytest.raises(SystemExit, match="stub"):
        voice.run(ct.load(mini), provider=prov, log=lambda *_: None)


def _take_with_air_leadin(dst, air_s=0.25, tone_s=0.25):
    """AI Studio-like take: noise/breath lead-in around -50 dBFS, then speech (a tone), then true silence."""
    import subprocess
    subprocess.run(["ffmpeg", "-y", "-v", "error",
                    "-f", "lavfi", "-i", f"anoisesrc=color=white:amplitude=0.005:seed=7:duration={air_s}:sample_rate=24000",
                    "-f", "lavfi", "-i", f"sine=frequency=440:duration={tone_s}:sample_rate=24000",
                    "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono:d=0.3",
                    "-filter_complex", "[1]volume=0.5[t];[0][t][2]concat=n=3:v=0:a=1,aformat=channel_layouts=mono",
                    "-ac", "1", str(dst)], check=True)


def test_overlong_take_retries_tight_trim_without_time_stretch(mini):
    """Lead-in air made the take overflow its slot: the tight trim removes only the air (speech intact, no speed-up)."""
    take = mini.parent / "vo" / "line-01.wav"
    _take_with_air_leadin(take)
    lock = voice.run(ct.load(mini), log=lambda *_: None)
    m = lock["lines"]["vo1"]
    assert m["fits"] and m["trim"] == "tight" and m["dur_s"] <= 0.4
    assert 0.25 <= m["dur_s"] <= 0.25 + 0.04 + 0.08 + 0.02  # tone kept whole, only <= 40 ms pre-roll + 80 ms tail left
    again = voice.run(ct.load(mini), log=lambda *_: None)
    assert again["lines"]["vo1"]["sha256"] == m["sha256"] and again["lines"]["vo1"]["trim"] == "tight"


def test_take_that_fits_keeps_the_normal_trim(mini):
    lock = voice.run(ct.load(mini), log=lambda *_: None)
    assert "trim" not in lock["lines"]["vo1"]
