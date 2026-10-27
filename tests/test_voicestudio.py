"""VoiceStudio track, hermetic: the HTTP transport is faked, so no socket, no app and no network.

The fake follows the real contract read at the pinned release (v0.5.7): POST /mcp/ with initialize ->
notifications/initialized -> tools/call (JSON-RPC 2.0, Streamable HTTP), the tool payloads as JSON text inside the MCP
result, and POST /v1/audio/transcriptions as the OpenAI-compatible multipart alternative.
"""
from __future__ import annotations

import base64
import json

import pytest

from simplicio_video import voicestudio as vs

WAV = b"RIFF-fake-wav-bytes"


def _text(payload) -> dict:
    """An MCP tool result carrying JSON text, the shape list_*/transcribe/check_health return."""
    return {"content": [{"type": "text", "text": json.dumps(payload)}]}


class Fake:
    def __init__(self):
        self.calls = []
        self.tools = []
        self.session = "sess-abc"
        self.results = {}
        self.rest_body = None
        self.rest_response = {"text": "transcrição pela API REST", "language": "pt"}
        self.well_known = {"version": "0.5.7", "tts": True}
        self.well_known_status = 200
        self.sse = False

    def __call__(self, method, url, body, headers, timeout):
        # Only the MCP lane is JSON-RPC: the REST lane carries multipart bytes.
        payload = json.loads(body) if body and "application/json" in headers.get("Content-Type", "") else None
        self.calls.append({"method": method, "url": url, "payload": payload, "headers": dict(headers), "timeout": timeout})
        assert timeout > 0
        if url.endswith(vs.WELL_KNOWN):
            if self.well_known_status != 200:
                return self.well_known_status, {}, b"not found"
            return 200, {"Content-Type": "application/json"}, json.dumps(self.well_known).encode()
        if url.endswith(vs.TRANSCRIPTIONS_PATH):
            self.rest_body = body
            return 200, {"Content-Type": "application/json"}, json.dumps(self.rest_response).encode()
        assert url == "http://127.0.0.1:3900" + vs.MCP_PATH, url
        assert headers.get("X-OmniVoice-Client-Id") == vs.CLIENT_ID  # the client id identifies this agent
        method_name = payload["method"]
        if method_name == "initialize":
            return 200, {"Mcp-Session-Id": self.session}, json.dumps(
                {"jsonrpc": "2.0", "id": payload["id"], "result": {"protocolVersion": vs.PROTOCOL_VERSION}}).encode()
        if method_name == "notifications/initialized":
            return 202, {}, b""
        assert method_name == "tools/call"
        name = payload["params"]["name"]
        arguments = payload["params"]["arguments"]
        self.tools.append((name, arguments))
        result = self.results[name](arguments) if callable(self.results.get(name)) else self.results[name]
        message = json.dumps({"jsonrpc": "2.0", "id": payload["id"], "result": result})
        if self.sse:
            return 200, {"Content-Type": "text/event-stream"}, f"event: message\ndata: {message}\n\n".encode()
        return 200, {"Content-Type": "application/json"}, message.encode()


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    for var in ("VOICESTUDIO_URL", "OMNIVOICE_URL", "VOICESTUDIO_PORT", "OMNIVOICE_PORT",
                "VOICESTUDIO_API_KEY", "OMNIVOICE_API_KEY"):
        monkeypatch.delenv(var, raising=False)


@pytest.fixture
def fake(monkeypatch):
    f = Fake()
    monkeypatch.setattr(vs, "default_transport", f)
    return f


def _run(argv, capsys):
    try:
        rc = vs.run_voicestudio(argv)
    except SystemExit as e:
        rc = e.code
    out, err = capsys.readouterr()
    return rc, out, err


# ---- base URL ----------------------------------------------------------------------------------------------------

def test_base_url_default_is_loopback_3900():
    assert vs.base_url() == "http://127.0.0.1:3900"


def test_base_url_respects_both_env_families(monkeypatch):
    monkeypatch.setenv("OMNIVOICE_PORT", "4100")
    assert vs.base_url() == "http://127.0.0.1:4100"
    monkeypatch.setenv("VOICESTUDIO_PORT", "4200")
    assert vs.base_url() == "http://127.0.0.1:4200"
    monkeypatch.setenv("OMNIVOICE_URL", "http://gpu-box:5555/")
    assert vs.base_url() == "http://gpu-box:5555"
    monkeypatch.setenv("VOICESTUDIO_URL", "http://127.0.0.1:9999/")
    assert vs.base_url() == "http://127.0.0.1:9999"


def test_base_url_rejects_a_bad_port(monkeypatch):
    monkeypatch.setenv("VOICESTUDIO_PORT", "abc")
    with pytest.raises(vs.VoiceStudioError, match="porta inválida"):
        vs.base_url()


# ---- MCP handshake and typed tools -------------------------------------------------------------------------------

def test_status_initializes_the_session_and_parses_json_text(fake):
    fake.results["check_health"] = _text({"status": "ok", "gpu": "Apple M3 Pro"})
    report = vs.status()
    assert report["url"] == "http://127.0.0.1:3900"
    assert report["health"]["gpu"] == "Apple M3 Pro"
    assert report["discovery"] == fake.well_known
    assert [c["payload"]["method"] for c in fake.calls if c["payload"]] == [
        "initialize", "notifications/initialized", "tools/call"]
    call = next(c for c in fake.calls if c["payload"] and c["payload"]["method"] == "tools/call")
    assert call["headers"]["Mcp-Session-Id"] == fake.session  # the session id travels on every later MCP call
    assert call["payload"]["params"] == {"name": "check_health", "arguments": {}}


def test_status_survives_an_unknown_well_known(fake):
    fake.results["check_health"] = _text({"status": "ok"})
    fake.well_known_status = 404
    assert vs.status()["discovery"] is None


def test_voices_accepts_an_array_or_an_object(fake):
    fake.results["list_voices"] = _text([{"id": "v1", "name": "Morgan", "kind": "clone"}])
    assert vs.voices() == [{"id": "v1", "name": "Morgan", "kind": "clone"}]
    fake.results["list_voices"] = _text({"voices": [{"id": "v2"}]})
    assert vs.voices() == [{"id": "v2"}]


def test_languages_and_personalities(fake):
    fake.results["list_languages"] = _text({"total": 646, "popular": ["pt", "en"]})
    fake.results["list_personalities"] = _text([{"name": "Narrator", "instruct": "calm"}])
    assert vs.languages()["popular"] == ["pt", "en"]
    assert vs.VoiceStudio().list_personalities()[0]["name"] == "Narrator"


def test_tool_error_payload_raises_a_clear_error(fake):
    fake.results["list_voices"] = _text({"error": "no profiles yet"})
    with pytest.raises(vs.VoiceStudioError, match="no profiles yet"):
        vs.voices()


def test_sse_responses_are_parsed(fake):
    fake.sse = True
    fake.results["check_health"] = _text({"status": "ok"})
    assert vs.VoiceStudio().check_health() == {"status": "ok"}


# ---- speech ------------------------------------------------------------------------------------------------------

def test_speak_decodes_wav_base64_and_writes_the_file(fake, tmp_path):
    fake.results["generate_speech"] = _text({"audio_id": "a1", "audio_duration_s": 1.5,
                                            "wav_base64": base64.b64encode(WAV).decode()})
    out = tmp_path / "voz" / "fala.wav"
    report = vs.speak("olá", out, profile_id="p1", language="pt-BR")
    assert out.read_bytes() == WAV
    assert report["out"] == str(out.resolve()) and report["bytes"] == len(WAV)
    assert report["audio_id"] == "a1" and report["duration_s"] == 1.5
    name, arguments = fake.tools[-1]
    assert name == "generate_speech"
    assert arguments == {"text": "olá", "format": "wav", "profile_id": "p1", "language": "pt-BR"}


def test_speak_prefers_the_files_mode_url(fake, tmp_path):
    fake.results["generate_speech"] = _text({"audio_id": "a2", "audio_url": "/audio/a2.ogg"})
    original = fake.__call__
    def transport(method, url, body, headers, timeout):
        if method == "GET" and url.endswith("/audio/a2.ogg"):
            return 200, {"Content-Type": "audio/ogg"}, b"OGG"
        return original(method, url, body, headers, timeout)
    import simplicio_video.voicestudio as module
    module.default_transport = transport
    out = tmp_path / "fala.ogg"
    vs.VoiceStudio().speak("olá", out, fmt="ogg")
    assert out.read_bytes() == b"OGG"


def test_speak_refuses_an_empty_text(fake, tmp_path):
    with pytest.raises(vs.VoiceStudioError, match="texto está vazio"):
        vs.speak("   ", tmp_path / "x.wav")


def test_describe_and_design_send_the_documented_arguments(fake):
    fake.results["describe_voice"] = _text({"matched": ["gender"]})
    fake.results["design_voice"] = _text({"profile_id": "p9", "name": "Nina", "kind": "design"})
    assert vs.VoiceStudio().describe_voice("mulher jovem")["matched"] == ["gender"]
    made = vs.VoiceStudio().design_voice("Nina", "mulher jovem", language="pt-BR")
    assert made["profile_id"] == "p9"
    assert fake.tools[-1] == ("design_voice", {"name": "Nina", "description": "mulher jovem", "language": "pt-BR"})


# ---- transcription and cloning -----------------------------------------------------------------------------------

def test_transcribe_sends_the_audio_as_base64(fake, tmp_path):
    audio = tmp_path / "fala.m4a"
    audio.write_bytes(b"audio-bytes")
    fake.results["transcribe"] = _text({"text": "bom dia", "language": "pt"})
    assert vs.transcribe(audio)["text"] == "bom dia"
    name, arguments = fake.tools[-1]
    assert name == "transcribe"
    assert base64.b64decode(arguments["audio_base64"]) == b"audio-bytes"


def test_transcribe_rest_uses_multipart_field_file(fake, tmp_path):
    audio = tmp_path / "fala.m4a"
    audio.write_bytes(b"audio-bytes")
    data = vs.transcribe(audio, language="pt", via="rest")
    assert data["text"] == "transcrição pela API REST"
    body = fake.rest_body
    assert b'name="file"; filename="fala.m4a"' in body
    assert b"audio-bytes" in body
    assert b'name="language"' in body and b"\r\npt\r\n" in body
    assert fake.tools == []  # the REST lane never touches the MCP


def test_transcribe_missing_file_is_an_error(fake, tmp_path):
    with pytest.raises(vs.VoiceStudioError, match="não encontrado"):
        vs.transcribe(tmp_path / "nao-existe.wav")


def test_clone_voice_sends_the_reference_as_base64(fake, tmp_path):
    ref = tmp_path / "ref.wav"
    ref.write_bytes(WAV)
    fake.results["clone_voice"] = _text({"profile_id": "p7", "name": "Minha voz", "kind": "clone"})
    made = vs.clone_voice(ref, "Minha voz", language="pt-BR")
    assert made["profile_id"] == "p7"
    name, arguments = fake.tools[-1]
    assert name == "clone_voice"
    assert arguments["name"] == "Minha voz" and arguments["language"] == "pt-BR"
    assert base64.b64decode(arguments["ref_audio_base64"]) == WAV


# ---- MCP config and CLI ------------------------------------------------------------------------------------------

def test_mcp_config_is_the_streamable_http_block():
    assert vs.mcp_config() == {"mcpServers": {"voicestudio": {"url": "http://127.0.0.1:3900/mcp/"}}}


def test_mcp_command_prints_the_block(fake, capsys):
    rc, out, _ = _run(["mcp"], capsys)
    assert rc == 0
    assert json.loads(out)["mcpServers"]["voicestudio"]["url"] == "http://127.0.0.1:3900/mcp/"
    assert fake.calls == []


def test_cli_tts_json_writes_the_audio(fake, tmp_path, capsys):
    fake.results["generate_speech"] = _text({"audio_id": "a1", "wav_base64": base64.b64encode(WAV).decode()})
    out_file = tmp_path / "cli.wav"
    rc, out, _ = _run(["tts", "bom dia", "--out", str(out_file), "--json"], capsys)
    assert rc == 0 and out_file.read_bytes() == WAV
    assert json.loads(out)["format"] == "wav"


def test_cli_transcribe_rest_and_text_output(fake, tmp_path, capsys):
    audio = tmp_path / "fala.m4a"
    audio.write_bytes(b"x")
    rc, out, _ = _run(["transcribe", str(audio), "--rest"], capsys)
    assert rc == 0 and "transcrição pela API REST" in out


def test_cli_status_json(fake, capsys):
    fake.results["check_health"] = _text({"status": "ok", "gpu": "cuda:0"})
    rc, out, _ = _run(["status", "--json"], capsys)
    assert rc == 0 and json.loads(out)["health"]["gpu"] == "cuda:0"


def test_cli_help_lists_every_subcommand_and_the_environment(fake, capsys):
    rc, out, _ = _run(["--help"], capsys)
    assert rc == 0
    for word in ("status", "voices", "languages", "personalities", "tts", "transcribe", "clone", "describe",
                 "design", "mcp", "VOICESTUDIO_URL", "OMNIVOICE_URL", "exemplos:"):
        assert word in out, word


def test_app_closed_is_an_actionable_error_and_exit_1(monkeypatch, capsys):
    def down(method, url, body, headers, timeout):
        raise vs.VoiceStudioError(f"não consegui falar com o VoiceStudio em {url} (Connection refused). " + vs.OPEN_APP)
    monkeypatch.setattr(vs, "default_transport", down)
    rc, out, err = _run(["status"], capsys)
    assert rc == 1 and out == ""
    assert "voicestudio:" in err and "Abra o VoiceStudio" in err and ":3900" in err


def test_default_transport_reports_a_closed_app_without_hanging(monkeypatch):
    def refused(*a, **k):
        raise __import__("urllib.error", fromlist=["error"]).URLError(ConnectionRefusedError(61, "Connection refused"))
    monkeypatch.setattr("urllib.request.urlopen", refused)
    with pytest.raises(vs.VoiceStudioError, match="Abra o VoiceStudio"):
        vs.default_transport("GET", "http://127.0.0.1:3900/x", None, {}, 5)
