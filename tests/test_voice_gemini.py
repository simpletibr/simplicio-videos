"""Gemini TTS provider with the HTTP layer mocked (no key, no network)."""
import base64
import io
import json
import math
import struct
import urllib.error
import wave

import pytest

from simplicio_video import contract as ct
from simplicio_video import voice


def _wav(seconds=0.4, sr=24000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1), w.setsampwidth(2), w.setframerate(sr)
        w.writeframes(b"".join(struct.pack("<h", int(8000 * math.sin(2 * math.pi * 330 * i / sr))) for i in range(int(seconds * sr))))
    return buf.getvalue()


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _set_gemini(mini, **extra):
    txt = mini.read_text().replace("providers: { file: { dir: vo } }",
                                   "providers: { file: { dir: vo }, gemini: " + json.dumps({"voice": "Laomedeia", "estilo": "alegre", **extra}) + " }")
    mini.write_text(txt)


@pytest.fixture
def fake_api(monkeypatch):
    calls = []

    def urlopen(req, timeout=0):
        calls.append({"url": req.full_url, "headers": dict(req.header_items()), "body": json.loads(req.data)})
        if "generateContent" in req.full_url:  # legacy shape: raw PCM L16 in inlineData
            pcm = _wav()[44:]
            res = {"candidates": [{"content": {"parts": [{"inlineData": {"mimeType": "audio/L16;codec=pcm;rate=24000",
                                                                          "data": base64.b64encode(pcm).decode()}}]}}]}
        else:
            res = {"steps": [{"type": "model_output", "content": [{"type": "audio", "mime_type": "audio/wav",
                                                                  "data": base64.b64encode(_wav()).decode()}]}]}
        return _Resp(json.dumps(res).encode())

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(voice.urllib.request, "urlopen", urlopen)
    return calls


def test_interactions_request_shape():
    url, body = voice.gemini_request({"model": "gemini-3.8-flash-tts", "voice": "Puck", "estilo": "animado"}, "Oi!")
    assert url.endswith("/v1beta/interactions")
    assert body["model"] == "gemini-3.8-flash-tts" and body["response_format"]["type"] == "audio"
    assert body["generation_config"]["speech_config"] == [{"voice": "Puck"}]
    c = body["input"][0]["content"][0]
    assert c["text"] == "Oi!" and c["annotations"] == [{"type": "speech_metadata", "style": "animado"}]


def test_generate_content_request_shape():
    url, body = voice.gemini_request({"model": "gemini-3.8-flash-tts", "voice": "Puck", "estilo": "animado", "api": "generate_content"}, "Oi!")
    assert url.endswith("/models/gemini-3.8-flash-tts:generateContent")
    g = body["generationConfig"]
    assert g["responseModalities"] == ["AUDIO"] and g["speechConfig"]["voiceConfig"]["prebuiltVoiceConfig"]["voiceName"] == "Puck"
    assert body["contents"][0]["parts"][0] == {"text": "Oi!", "speech_metadata": {"style": "animado"}}


def test_gemini_provider_writes_wav_and_lock(mini, fake_api):
    _set_gemini(mini)
    lock = voice.run(ct.load(mini), provider="gemini", log=lambda *_: None)
    assert len(fake_api) == 1
    call = fake_api[0]
    assert call["headers"].get("X-goog-api-key") == "test-key"
    assert call["body"]["generation_config"]["speech_config"] == [{"voice": "Laomedeia"}]
    assert call["body"]["input"][0]["content"][0]["annotations"][0]["style"] == "alegre"
    assert lock["provider"] == "gemini" and lock["settings"]["model"] == voice.GEMINI_MODEL
    assert lock["usage"]["tts_chars_this_run"] > 0
    m = lock["lines"]["vo1"]
    assert m["tts"]["voice"] == "Laomedeia" and m["fits"]
    take = mini.parent / m["source"]
    with wave.open(str(take)) as w:  # raw take kept for provider=file, 24 kHz mono 16-bit
        assert (w.getframerate(), w.getnchannels(), w.getsampwidth()) == (24000, 1, 2)
    on_disk = json.loads((mini.parent / "timing.lock.json").read_text())
    assert on_disk["lines"]["vo1"]["sha256"] == m["sha256"]
    again = voice.run(ct.load(mini), provider="gemini", log=lambda *_: None)  # cache hit: no second API call
    assert len(fake_api) == 1 and again["lines"]["vo1"]["sha256"] == m["sha256"] and again["usage"]["tts_chars_this_run"] == 0


def test_gemini_generate_content_raw_pcm(mini, fake_api):
    _set_gemini(mini, api="generate_content")
    lock = voice.run(ct.load(mini), provider="gemini", log=lambda *_: None)
    assert "generateContent" in fake_api[0]["url"] and lock["settings"]["api"] == "generate_content"
    with wave.open(str(mini.parent / lock["lines"]["vo1"]["source"])) as w:
        assert w.getframerate() == 24000


def test_gemini_retries_429(mini, monkeypatch, fake_api):
    _set_gemini(mini)
    ok = voice.urllib.request.urlopen
    state = {"n": 0}

    def flaky(req, timeout=0):
        state["n"] += 1
        if state["n"] == 1:
            raise urllib.error.HTTPError(req.full_url, 429, "quota", {"Retry-After": "0"}, io.BytesIO(b"{}"))
        return ok(req, timeout)

    monkeypatch.setattr(voice.urllib.request, "urlopen", flaky)
    voice.run(ct.load(mini), provider="gemini", log=lambda *_: None)
    assert state["n"] == 2


def test_gemini_http_error_is_clear(mini, monkeypatch, fake_api):
    _set_gemini(mini)

    def bad(req, timeout=0):
        raise urllib.error.HTTPError(req.full_url, 403, "denied", {}, io.BytesIO(b'{"error": "API key not valid"}'))

    monkeypatch.setattr(voice.urllib.request, "urlopen", bad)
    with pytest.raises(SystemExit, match="HTTP 403"):
        voice.run(ct.load(mini), provider="gemini", log=lambda *_: None)
