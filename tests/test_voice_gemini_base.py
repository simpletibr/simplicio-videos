"""U22c: `voice` sends the Gemini key (`x-goog-api-key`) only to an https base, or to http on this machine.

`SIMPLICIO_GEMINI_BASE` is where `voice --provider gemini` POSTs, with `GEMINI_API_KEY` in a header. Until U22c `voice.gemini_base()` took any
text, so an `http://` base on the internet (a LAN address, `ftp:`, `file:`) got the key in clear; the swap adapter (`swap_providers/gemini.py`,
`GeminiAdapter._base`) already refused all of those. Now `voice` has the same rule and the same words, behind the `provider=gemini:` prefix
that every other error of voice.py has. The rule is written twice (voice.py and the adapter) until it moves to a module of its own, so the
parity test below fails when one copy changes and the other does not.

tests/golden/test_mcp_bordas.py (c) holds the golden rows (what `gemini_base()` gives for a value). This file holds the rest: what leaves
the machine, what the user sees on each surface, and what must NOT change (https, loopback, a run that needs no request).
"""
import base64
import io
import json

import pytest

from helpers import run_main, sine_wav
from simplicio_video import cli, mcp_server, voice
from simplicio_video import contract as ct
from simplicio_video.swap_providers import base as swap_base
from simplicio_video.swap_providers import gemini as swap_gemini

ENV = "SIMPLICIO_GEMINI_BASE"
OFFICIAL = "https://generativelanguage.googleapis.com/v1beta"
REFUSAL = "provider=gemini: SIMPLICIO_GEMINI_BASE precisa ser https (http só em localhost): a chave não vai em texto claro"
SETTINGS = {"model": voice.GEMINI_MODEL, "voice": "Puck", "estilo": ""}

ACCEPTED = [  # (the variable, what gemini_base() returns: the same text without the trailing slash)
    (OFFICIAL, OFFICIAL),
    ("https://proxy.example.com/v1beta/", "https://proxy.example.com/v1beta"),
    ("HTTPS://Proxy.Example.com/v1beta", "HTTPS://Proxy.Example.com/v1beta"),  # scheme and host are not case sensitive
    ("http://localhost:8080/v1beta", "http://localhost:8080/v1beta"),
    ("http://localhost", "http://localhost"),
    ("http://127.0.0.1:8765/v1beta", "http://127.0.0.1:8765/v1beta"),  # the mock of tests/tools/mock_gemini.py
    ("http://[::1]:8080/v1beta", "http://[::1]:8080/v1beta"),
    ("HTTP://LOCALHOST:8080/v1beta", "HTTP://LOCALHOST:8080/v1beta"),
]
REFUSED = [
    "http://example.com/v1beta",  # the internet, in clear
    "http://generativelanguage.googleapis.com/v1beta",  # the official host, but without TLS
    "http://10.0.0.5:9000",  # a LAN address
    "http://0.0.0.0:8080",  # the rule is a short list of names, not "anything that reaches this machine"
    "http://127.0.0.2:8080",
    "http://localhost.evil.com/v1beta",  # names that only start like a loopback
    "http://127.0.0.1.evil.com/v1beta",
    "http://evil.localhost",  # names that only END like a loopback: a suffix match (endswith) would take them
    "http://notlocalhost",
    "http://127.0.0.1@evil.com/v1beta",  # the host is what comes after the @
    "http://localhost:80@evil.com/v1beta",
    "http://user:secret@example.com/v1beta",  # credentials in the URL: the fixed text never repeats the value
    "ftp://example.com/x",
    "file:///tmp/mock",
    "ws://localhost:8080",  # only http and https count, even on this machine
    "example.com/v1beta",  # no scheme
    "localhost:8080/v1beta",
    "//example.com/v1beta",
    "http://",
]
PADDED = [  # the adapter judges the text without the spaces around it: so does voice
    "  http://127.0.0.1:8765/v1beta",
    "http://127.0.0.1:8765/v1beta  ",
    " https://proxy.example.com/v1beta",
    " http://example.com/v1beta ",
    "http://localhost ",
    "http://127.0.0.1 ",
    "http://example.com ",
]


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.delenv(ENV, raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.fixture
def sent(monkeypatch):
    """What left the machine: `urlopen` of voice replaced by a recorder that answers like the API. [{url, key}] in order."""
    calls = []

    def urlopen(req, timeout=0):
        calls.append({"url": req.full_url, "key": dict(req.header_items()).get("X-goog-api-key")})
        res = {"steps": [{"type": "model_output", "content": [{"type": "audio", "mime_type": "audio/wav",
                                                              "data": base64.b64encode(sine_wav()).decode()}]}]}
        return _Resp(json.dumps(res).encode())

    monkeypatch.setattr(voice.urllib.request, "urlopen", urlopen)
    return calls


def _outcome(call):
    """("ok", the base) or ("refused", the text of the refusal), whichever of the two exception types it is."""
    try:
        return "ok", call()
    except voice.VoiceError as e:
        return "refused", e.code
    except swap_base.SwapError as e:
        return "refused", str(e)


# ---------------------------------------------------------------------------------------------- the rule

def test_the_default_base_is_the_official_https_one(monkeypatch):
    assert voice.gemini_base() == OFFICIAL
    monkeypatch.setenv(ENV, "")
    assert voice.gemini_base() == OFFICIAL  # empty is the same as not set


@pytest.mark.parametrize("value,expected", ACCEPTED)
def test_the_bases_that_may_carry_the_key(monkeypatch, value, expected):
    monkeypatch.setenv(ENV, value)
    assert voice.gemini_base() == expected


@pytest.mark.parametrize("value", REFUSED)
def test_a_base_that_would_send_the_key_in_clear_is_refused(monkeypatch, value):
    monkeypatch.setenv(ENV, value)
    with pytest.raises(voice.VoiceError) as e:
        voice.gemini_base()
    assert e.value.code == REFUSAL  # a fixed text: it never repeats the value, which may carry user:password@


@pytest.mark.parametrize("value", [v for v, _ in ACCEPTED] + REFUSED + PADDED)
def test_voice_and_the_swap_adapter_judge_a_base_the_same_way(monkeypatch, value):
    monkeypatch.setenv(ENV, value)
    mine = _outcome(voice.gemini_base)
    theirs = _outcome(swap_gemini.GeminiAdapter()._base)
    assert mine[0] == theirs[0]
    if theirs[0] == "refused":
        assert mine[1] == "provider=gemini: " + theirs[1]  # the words of the adapter, behind the prefix of voice
        assert mine[1] == REFUSAL
    elif value == value.strip():
        assert mine[1] == theirs[1]  # (with spaces around it the adapter returns the text trimmed, voice as it always did)


def test_a_blank_base_is_refused_where_the_adapter_reads_it_as_not_set(monkeypatch):
    # The one place where voice is stricter than the adapter. The adapter trims first, so "   " is "not set" and it takes the official base;
    # voice never trimmed what it returns, and "   " is not a URL (before U22c: a ValueError in the middle of the request).
    monkeypatch.setenv(ENV, "   ")
    with pytest.raises(voice.VoiceError) as e:
        voice.gemini_base()
    assert e.value.code == REFUSAL
    assert swap_gemini.GeminiAdapter()._base() == OFFICIAL


@pytest.mark.parametrize("api,tail", [("interactions", "/interactions"), ("generate_content", "/models/gemini-3.8-flash-tts:generateContent")])
def test_the_request_of_each_api_is_built_on_the_checked_base(monkeypatch, api, tail):
    settings = {**SETTINGS, "api": api}
    monkeypatch.setenv(ENV, "http://127.0.0.1:8765/v1beta/")
    assert voice.gemini_request(settings, "Oi!")[0] == "http://127.0.0.1:8765/v1beta" + tail
    monkeypatch.setenv(ENV, "http://example.com/v1beta")
    with pytest.raises(voice.VoiceError) as e:
        voice.gemini_request(settings, "Oi!")
    assert e.value.code == REFUSAL


# ---------------------------------------------------------------------------------------------- what leaves the machine

@pytest.mark.parametrize("value", ["http://example.com/v1beta", "http://generativelanguage.googleapis.com/v1beta", "http://10.0.0.5:9000"])
def test_the_key_is_not_sent_to_a_base_in_clear(monkeypatch, sent, tmp_path, value):
    monkeypatch.setenv(ENV, value)
    take = tmp_path / "take.wav"
    try:
        voice._gemini(SETTINGS, "Oi!", take)
        refusal = None
    except voice.VoiceError as e:
        refusal = e.code
    assert sent == []  # nothing left the machine: no request, so no header with the key
    assert refusal == REFUSAL and not take.exists()


def test_without_a_key_the_missing_key_message_still_comes_first(monkeypatch, sent, tmp_path):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv(ENV, "http://example.com/v1beta")
    with pytest.raises(voice.VoiceError, match=r"^provider=gemini: GEMINI_API_KEY not set\."):  # the message that was already there, as before
        voice._gemini(SETTINGS, "Oi!", tmp_path / "take.wav")
    assert sent == []


def test_a_run_stops_before_the_first_request_and_writes_nothing(monkeypatch, mini, sent):
    monkeypatch.setenv(ENV, "http://example.com/v1beta")
    try:
        voice.run(ct.load(mini), provider="gemini", log=lambda *_: None)
        refusal = None
    except SystemExit as e:
        refusal = e.code
    assert sent == []
    assert refusal == REFUSAL
    assert not (mini.parent / "timing.lock.json").exists()


def test_a_mock_on_this_machine_still_gets_the_key(monkeypatch, mini, sent):
    monkeypatch.setenv(ENV, "http://127.0.0.1:8765/v1beta/")
    lock = voice.run(ct.load(mini), provider="gemini", log=lambda *_: None)
    assert sent == [{"url": "http://127.0.0.1:8765/v1beta/interactions", "key": "test-key"}]
    assert lock["provider"] == "gemini" and lock["lines"]["vo1"]["fits"]


def test_a_run_that_needs_no_request_does_not_look_at_the_base(monkeypatch, mini, sent):
    first = voice.run(ct.load(mini), provider="gemini", log=lambda *_: None)  # the official base, one request
    assert [c["url"] for c in sent] == [OFFICIAL + "/interactions"]
    monkeypatch.setenv(ENV, "http://example.com/v1beta")  # a base that would be refused...
    again = voice.run(ct.load(mini), provider="gemini", log=lambda *_: None)  # ...is not asked about when the take is in the cache
    assert len(sent) == 1 and again["lines"]["vo1"]["sha256"] == first["lines"]["vo1"]["sha256"]


# ---------------------------------------------------------------------------------------------- what the caller sees

def test_the_voice_command_exits_with_1_and_the_refusal(monkeypatch, mini, sent, capsys):
    monkeypatch.setenv(ENV, "http://example.com/v1beta")
    rc, out, err = run_main(cli.main, ["voice", str(mini), "--provider", "gemini"], capsys, text_exit=True)
    assert sent == []
    assert (rc, out, err) == (1, "", REFUSAL + "\n")
    assert not (mini.parent / "timing.lock.json").exists()


def test_the_mcp_voice_tool_reports_the_refusal(monkeypatch, mini, sent):
    monkeypatch.setenv(ENV, "http://example.com/v1beta")
    res = mcp_server.video_voice(str(mini), provider="gemini")
    assert sent == []
    assert res["ok"] is False and res["error"] == REFUSAL
