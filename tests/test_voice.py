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
