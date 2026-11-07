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
from helpers import run_main

WAV = b"RIFF-fake-wav-bytes"
MP4 = b"\x00\x00\x00\x18ftypmp42-fake-dubbed-video"


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
        self.rest_raw = None
        self.rest_response = {"text": "transcrição pela API REST", "language": "pt"}
        self.well_known = {"version": "0.5.7", "tts": True}
        self.well_known_status = 200
        self.sse = False
        self.dub_calls = []
        self.dub_response = (200, {"Content-Type": "video/mp4"}, MP4)
        self.upload_calls = []
        self.upload_response = (202, {"Content-Type": "application/json"},
                                json.dumps({"job_id": "ab12cd34", "task_id": "prep_ab12cd34", "filename": "clip.mp4"}).encode())

    def __call__(self, method, url, body, headers, timeout):
        # Only the MCP lane is JSON-RPC: the REST lane carries multipart bytes.
        raw_body = body
        if body is not None and not isinstance(body, bytes):  # a streamed multipart body: read it the way the socket would
            body = body.read()
        payload = json.loads(body) if body and "application/json" in headers.get("Content-Type", "") else None
        self.calls.append({"method": method, "url": url, "payload": payload, "headers": dict(headers), "timeout": timeout})
        assert timeout > 0
        if url.endswith(vs.WELL_KNOWN):
            if self.well_known_status != 200:
                return self.well_known_status, {}, b"not found"
            return 200, {"Content-Type": "application/json"}, json.dumps(self.well_known).encode()
        if url.endswith(getattr(vs, "DUB_UPLOAD_PATH", "/dub/upload")):  # POST /dub/upload: multipart, the app answers 202 {job_id, task_id, filename}
            self.upload_calls.append({"method": method, "url": url, "body": body, "raw_body": raw_body, "headers": dict(headers), "timeout": timeout})
            return self.upload_response
        if vs.DUB_DOWNLOAD_PATH in url:
            self.dub_calls.append({"method": method, "url": url, "headers": dict(headers), "timeout": timeout})
            return self.dub_response
        if url.endswith(vs.TRANSCRIPTIONS_PATH):
            self.rest_body = body
            self.rest_raw = raw_body
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
    return run_main(vs.run_voicestudio, argv, capsys)


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


# ---- dub-export: a dubbing job that already exists in the app, with the background kept ------------------------------

def _query(url: str) -> dict:
    from urllib.parse import parse_qs, urlsplit
    return {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}


def test_dub_export_writes_the_mp4_and_asks_for_the_preserved_background(fake, tmp_path):
    out = tmp_path / "sub" / "dublado.mp4"
    r = vs.VoiceStudio().dub_export("a1b2c3d4", "pl", out)
    assert out.read_bytes() == MP4 and not (tmp_path / "sub" / "dublado.mp4.part").exists()
    assert r == {"out": str(out), "bytes": len(MP4), "job": "a1b2c3d4", "lang": "pl", "bed_level": 1.0, "preserve_bg": True, "warning": None}
    call = fake.dub_calls[0]
    assert call["method"] == "GET" and call["url"].startswith("http://127.0.0.1:3900/dub/download/a1b2c3d4?")
    assert _query(call["url"]) == {"preserve_bg": "true", "bed_level": "1.0", "default_track": "pl", "include_tracks": "pl"}
    assert call["timeout"] >= 600  # the app remuxes the video before it answers
    assert fake.tools == []  # nothing is generated: no MCP tool is called


def test_dub_export_passes_the_bed_level_and_the_api_key(fake, tmp_path, monkeypatch):
    monkeypatch.setenv("VOICESTUDIO_API_KEY", "chave-falsa")
    vs.VoiceStudio().dub_export("job_1", "pt", tmp_path / "o.mp4", bed_level=0.6)
    call = fake.dub_calls[0]
    assert _query(call["url"])["bed_level"] == "0.6" and call["headers"]["Authorization"] == "Bearer chave-falsa"


@pytest.mark.parametrize("level", [-0.1, 4.01, float("nan"), "alto"])
def test_dub_export_rejects_a_bed_level_the_app_would_refuse(fake, tmp_path, level):
    with pytest.raises(vs.VoiceStudioError, match="bed-level"):
        vs.VoiceStudio().dub_export("job1", "pl", tmp_path / "o.mp4", bed_level=level)
    assert fake.dub_calls == [] and not (tmp_path / "o.mp4").exists()


@pytest.mark.parametrize("job,lang", [("../etc", "pl"), ("a/b", "pl"), ("", "pl"), ("job1", ""), ("job1", "pl&x=1")])
def test_dub_export_validates_job_and_language_before_any_call(fake, tmp_path, job, lang):
    with pytest.raises(vs.VoiceStudioError, match="inválido"):
        vs.VoiceStudio().dub_export(job, lang, tmp_path / "o.mp4")
    assert fake.dub_calls == []


@pytest.mark.parametrize("status,detail,expect", [
    (404, {"detail": "Job not found"}, "não tem o job"),
    (400, {"detail": "No dubbed tracks generated yet"}, "faixa dublada pronta"),
    (409, {"detail": {"code": "dub_background_unavailable", "message": "Original audio and background separation are required"}},
     "preservar o fundo"),
    (403, {"detail": "forbidden"}, "VOICESTUDIO_API_KEY"),
])
def test_dub_export_turns_an_app_error_into_a_clear_message(fake, tmp_path, status, detail, expect):
    fake.dub_response = (status, {"Content-Type": "application/json"}, json.dumps(detail).encode())
    with pytest.raises(vs.VoiceStudioError, match=expect):
        vs.VoiceStudio().dub_export("job1", "pl", tmp_path / "o.mp4")
    assert not (tmp_path / "o.mp4").exists()


def test_dub_export_refuses_a_json_or_empty_answer_as_a_video(fake, tmp_path):
    fake.dub_response = (200, {"Content-Type": "application/json"}, b'{"saved": true}')
    with pytest.raises(vs.VoiceStudioError, match="não devolveu um vídeo"):
        vs.VoiceStudio().dub_export("job1", "pl", tmp_path / "o.mp4")
    fake.dub_response = (200, {"Content-Type": "video/mp4"}, b"")
    with pytest.raises(vs.VoiceStudioError, match="não devolveu um vídeo"):
        vs.VoiceStudio().dub_export("job1", "pl", tmp_path / "o.mp4")
    assert not (tmp_path / "o.mp4").exists()


def test_dub_export_reports_the_apps_fallback_warning(fake, tmp_path):
    fake.dub_response = (200, {"Content-Type": "video/mp4", "X-Dub-Export-Warning": "video-retime-fallback"}, MP4)
    assert vs.VoiceStudio().dub_export("job1", "pl", tmp_path / "o.mp4")["warning"] == "video-retime-fallback"


def test_cli_dub_export_json_writes_the_video(fake, tmp_path, capsys):
    out = tmp_path / "d.mp4"
    rc, stdout, _ = _run(["dub-export", "--job", "j9", "--lang", "pl", "--bed-level", "1.5", "-o", str(out), "--json"], capsys)
    assert rc == 0 and out.read_bytes() == MP4
    assert json.loads(stdout)["bed_level"] == 1.5 and _query(fake.dub_calls[0]["url"])["bed_level"] == "1.5"


def test_cli_dub_export_app_error_is_exit_1_with_the_message(fake, tmp_path, capsys):
    fake.dub_response = (404, {"Content-Type": "application/json"}, b'{"detail": "Job not found"}')
    rc, _, err = _run(["dub-export", "--job", "nao-existe", "--lang", "pl", "-o", str(tmp_path / "d.mp4")], capsys)
    assert rc == 1 and err.startswith("voicestudio: ") and "nao-existe" in err and not (tmp_path / "d.mp4").exists()


def test_cli_dub_export_needs_job_lang_and_output(fake, capsys):
    rc, _, err = _run(["dub-export", "--job", "j9"], capsys)
    assert rc == 2 and "--lang" in err and fake.dub_calls == []


# ---- dub create (spike: POST /dub/upload at the pinned release; the app has no MCP/HTTP "one call" dub) ---------------

def _clip(tmp_path, name="clip.mp4", data=b"fake-video-bytes"):
    f = tmp_path / name
    f.write_bytes(data)
    return f


def test_dub_create_uploads_multipart_and_returns_the_job(fake, tmp_path):
    clip = _clip(tmp_path)
    r = vs.VoiceStudio().dub_create(clip, source_lang="pt")
    call = fake.upload_calls[0]
    assert call["method"] == "POST" and call["url"] == "http://127.0.0.1:3900/dub/upload"
    assert call["headers"]["Content-Type"].startswith("multipart/form-data; boundary=")
    assert call["headers"]["X-OmniVoice-Client-Id"] == vs.CLIENT_ID
    body = call["body"]
    assert b'name="video"; filename="clip.mp4"' in body and b"fake-video-bytes" in body
    assert b'name="input_type"\r\n\r\nvideo' in body and b'name="source_lang"\r\n\r\npt' in body
    assert r["job"] == "ab12cd34" and r["task"] == "prep_ab12cd34" and r["filename"] == "clip.mp4" and r["input_type"] == "video"
    assert fake.tools == []  # the upload is plain HTTP; the MCP session is never opened


def test_dub_create_audio_and_explicit_job_id(fake, tmp_path):
    clip = _clip(tmp_path, "fala.wav")
    vs.VoiceStudio().dub_create(clip, input_type="audio", job_id="meu-job_1")
    body = fake.upload_calls[0]["body"]
    assert b'name="input_type"\r\n\r\naudio' in body and b'name="job_id"\r\n\r\nmeu-job_1' in body
    assert b"source_lang" not in body


def test_dub_create_sends_the_api_key(fake, tmp_path, monkeypatch):
    monkeypatch.setenv("VOICESTUDIO_API_KEY", "k-123")
    vs.VoiceStudio().dub_create(_clip(tmp_path))
    assert fake.upload_calls[0]["headers"]["Authorization"] == "Bearer k-123"


@pytest.mark.parametrize("kwargs", [{"job_id": "../x"}, {"job_id": "a b"}, {"job_id": "x" * 65}, {"source_lang": "pt br"},
                                    {"input_type": "gif"}])
def test_dub_create_validates_before_any_call(fake, tmp_path, kwargs):
    with pytest.raises(vs.VoiceStudioError):
        vs.VoiceStudio().dub_create(_clip(tmp_path), **kwargs)
    assert fake.calls == []


def test_dub_create_missing_or_empty_file_is_an_error(fake, tmp_path):
    with pytest.raises(vs.VoiceStudioError, match="não encontrado"):
        vs.VoiceStudio().dub_create(tmp_path / "nao-existe.mp4")
    with pytest.raises(vs.VoiceStudioError, match="vazio"):
        vs.VoiceStudio().dub_create(_clip(tmp_path, "vazio.mp4", b""))
    assert fake.calls == []


def test_dub_create_refuses_a_file_over_the_cap_without_reading_it(fake, tmp_path, monkeypatch):
    monkeypatch.setattr(vs, "MAX_DUB_UPLOAD_BYTES", 4)
    with pytest.raises(vs.VoiceStudioError, match="grande"):
        vs.VoiceStudio().dub_create(_clip(tmp_path, data=b"12345"))
    assert fake.calls == []


@pytest.mark.parametrize("status,detail,expect", [
    (409, "This job ID is already in use.", "já existe"),
    (415, "Unsupported video type", "formato"),
    (400, "Invalid job_id", "recusou"),
    (403, "forbidden", "VOICESTUDIO_API_KEY"),
])
def test_dub_create_turns_an_app_error_into_a_clear_message(fake, tmp_path, status, detail, expect):
    fake.upload_response = (status, {"Content-Type": "application/json"}, json.dumps({"detail": detail}).encode())
    with pytest.raises(vs.VoiceStudioError, match=expect):
        vs.VoiceStudio().dub_create(_clip(tmp_path), job_id="j1")


def test_dub_create_refuses_an_answer_without_a_job_id(fake, tmp_path):
    fake.upload_response = (202, {"Content-Type": "application/json"}, b'{"ok": true}')
    with pytest.raises(vs.VoiceStudioError, match="job_id"):
        vs.VoiceStudio().dub_create(_clip(tmp_path))


def test_cli_dub_create_json(fake, tmp_path, capsys):
    clip = _clip(tmp_path)
    rc, out, _ = _run(["dub", "create", str(clip), "--source-lang", "en", "--json"], capsys)
    data = json.loads(out)
    assert rc == 0 and data["job"] == "ab12cd34" and data["task"] == "prep_ab12cd34"
    assert "dub-export" in data["next"]  # tells where the job goes from here (the rest happens in the app)


def test_cli_dub_create_text_and_audio_flag(fake, tmp_path, capsys):
    rc, out, _ = _run(["dub", "create", str(_clip(tmp_path, "a.wav")), "--audio"], capsys)
    assert rc == 0 and "ab12cd34" in out and b'name="input_type"\r\n\r\naudio' in fake.upload_calls[0]["body"]


def test_cli_dub_create_app_closed_is_exit_1(monkeypatch, tmp_path, capsys):
    def closed(*a, **k):
        raise vs.VoiceStudioError("não consegui falar com o VoiceStudio")
    monkeypatch.setattr(vs, "default_transport", closed)
    rc, _, err = _run(["dub", "create", str(_clip(tmp_path))], capsys)
    assert rc == 1 and err.startswith("voicestudio: ")


def test_cli_dub_needs_a_subcommand_and_help_mentions_create(fake, capsys):
    rc, _, _ = _run(["dub"], capsys)
    assert rc == 1
    rc, out, _ = _run(["--help"], capsys)
    assert "dub create" in out and "dub" in vs.SUBCOMMANDS


# ---- MCP tool: absolute --out, parsed JSON ---------------------------------------------------------------------------

@pytest.fixture
def mcp_tool():
    from simplicio_video import mcp_server
    return mcp_server.video_voicestudio


@pytest.fixture
def served(fake):
    fake.results["check_health"] = _text({"status": "ok", "gpu": "cuda:0"})
    fake.results["list_voices"] = _text([{"id": "v1", "name": "Ana"}])
    fake.results["list_languages"] = _text({"total": 2, "popular": ["pt-BR", "en"]})
    fake.results["generate_speech"] = _text({"wav_base64": base64.b64encode(WAV).decode(), "audio_id": "a1"})
    return fake


@pytest.mark.parametrize("args", ["tts oi --out fala.wav", "tts oi -o fala.wav", "tts oi --out=fala.wav", "tts oi --out ./fala.wav",
                                  "tts oi --out ../fala.wav", "tts oi --out ~/fala.wav", "dub-export --job j1 --lang pl -o d.mp4"])
def test_mcp_refuses_a_relative_out_before_any_call(served, mcp_tool, args, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    r = mcp_tool(args)
    assert r["ok"] is False and "absolut" in r["error"] and "--out" in r["error"]
    assert served.calls == [] and list(tmp_path.iterdir()) == []


def test_mcp_accepts_an_absolute_out_and_returns_the_parsed_json(served, mcp_tool, tmp_path):
    out = tmp_path / "fala.wav"
    r = mcp_tool(f"tts oi --out {out}")
    assert r["ok"] is True and r["rc"] == 0
    assert isinstance(r["result"], dict) and r["result"]["out"] == str(out.resolve()) and r["result"]["audio_id"] == "a1"
    assert out.read_bytes() == WAV


def test_mcp_returns_parsed_json_without_asking_for_it(served, mcp_tool):
    r = mcp_tool("voices")
    assert r["ok"] is True and r["result"] == [{"id": "v1", "name": "Ana"}]
    r = mcp_tool("status")
    assert r["result"]["health"]["gpu"] == "cuda:0" and r["result"]["url"] == "http://127.0.0.1:3900"
    assert mcp_tool("languages --json")["result"]["total"] == 2  # an explicit --json is not doubled


def test_mcp_mcp_subcommand_returns_the_config_block(served, mcp_tool):
    r = mcp_tool("mcp")
    assert r["ok"] is True and r["result"]["mcpServers"]["voicestudio"]["url"].endswith("/mcp/")


def test_mcp_failure_carries_the_cli_error_message(fake, mcp_tool, monkeypatch):
    def closed(*a, **k):
        raise vs.VoiceStudioError("não consegui falar com o VoiceStudio")
    monkeypatch.setattr(vs, "default_transport", closed)
    r = mcp_tool("status")
    assert r["ok"] is False and r["rc"] == 1 and r["result"] is None
    assert "não consegui falar com o VoiceStudio" in r["error"]


def test_mcp_argparse_error_is_a_result_not_an_exception(served, mcp_tool):
    r = mcp_tool("tts")
    assert r["ok"] is False and r["rc"] == 2 and "texto" in r["error"]


def test_mcp_keeps_quoted_arguments_together(served, mcp_tool, tmp_path):
    mcp_tool(f'tts "olá mundo cruel" --out {tmp_path / "a.wav"}')
    assert served.tools[0][1]["text"] == "olá mundo cruel"
    r = mcp_tool("tts 'aspas abertas")
    assert r["ok"] is False and "aspas" in r["error"].lower()


def test_mcp_dub_create_and_dub_export_over_the_tool(served, mcp_tool, tmp_path):
    clip = _clip(tmp_path)
    r = mcp_tool(f"dub create {clip} --source-lang pt")
    assert r["ok"] is True and r["result"]["job"] == "ab12cd34"
    out = tmp_path / "d.mp4"
    r = mcp_tool(f"dub-export --job ab12cd34 --lang pl -o {out}")
    assert r["ok"] is True and r["result"]["bytes"] == len(MP4) and out.read_bytes() == MP4


def test_mcp_description_names_dub_create_and_the_absolute_out():
    from simplicio_video import mcp_server
    d = mcp_server.DESC_video_voicestudio
    assert "dub create" in d and "absolut" in d.lower()


# ---- review round: loopback only for file bytes, MCP path guards, streaming, Windows args -----------------------------

REMOTE = ["http://evil.example:3900", "https://evil.example", "http://127.0.0.1.evil.example:3900", "http://localhost.evil.example",
          "http://10.0.0.5:3900", "http://0.0.0.0:3900", "http://user@evil.example:3900", "ftp://127.0.0.1"]
LOCAL = ["http://127.0.0.1:1234", "http://[::1]:3900", "http://localhost:3900", "http://127.1.2.3:3900"]


def _sender(kind, client, tmp_path):
    a = _clip(tmp_path, "a.wav")
    return {"dub": lambda: client.dub_create(a), "transcribe": lambda: client.transcribe(a),
            "transcribe-rest": lambda: client.transcribe(a, via="rest"), "clone": lambda: client.clone_voice(a, "Voz")}[kind]


@pytest.mark.parametrize("kind", ["dub", "transcribe", "transcribe-rest", "clone"])
@pytest.mark.parametrize("base", REMOTE)
def test_calls_that_send_file_bytes_refuse_a_non_loopback_base(fake, tmp_path, kind, base):
    with pytest.raises(vs.VoiceStudioError, match="loopback"):
        _sender(kind, vs.VoiceStudio(base=base), tmp_path)()
    assert fake.calls == []


@pytest.mark.parametrize("base", LOCAL)
def test_loopback_bases_may_receive_files(fake, tmp_path, base):
    assert vs.VoiceStudio(base=base).dub_create(_clip(tmp_path))["job"] == "ab12cd34"


def test_open_app_text_states_the_loopback_rule():
    assert "loopback" in vs.OPEN_APP.lower()


def test_the_env_url_cannot_make_dub_create_leave_the_machine(fake, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("VOICESTUDIO_URL", "http://evil.example:3900")
    rc, _, err = _run(["dub", "create", str(_clip(tmp_path))], capsys)
    assert rc == 1 and "loopback" in err and fake.calls == []


def test_dub_create_streams_the_body_and_sets_content_length(fake, tmp_path):
    vs.VoiceStudio().dub_create(_clip(tmp_path, data=b"x" * 5000))
    call = fake.upload_calls[0]
    assert not isinstance(call["raw_body"], (bytes, bytearray)) and hasattr(call["raw_body"], "read")
    assert call["headers"]["Content-Length"] == str(len(call["body"])) and b"x" * 5000 in call["body"]


def test_transcribe_rest_streams_the_body_too(fake, tmp_path):
    vs.VoiceStudio().transcribe(_clip(tmp_path, "a.wav", b"y" * 3000), via="rest")
    assert hasattr(fake.rest_raw, "read") and b"y" * 3000 in fake.rest_body


# MCP guards

@pytest.fixture
def home(tmp_path, monkeypatch):
    h = tmp_path / "home"
    h.mkdir()
    monkeypatch.setenv("HOME", str(h))
    monkeypatch.setenv("USERPROFILE", str(h))
    return h


@pytest.mark.parametrize("cmd", ["dub create {p}", "transcribe {p}", "clone {p} --name Voz"])
def test_mcp_input_paths_must_be_absolute(served, mcp_tool, tmp_path, monkeypatch, cmd):
    monkeypatch.chdir(tmp_path)
    ext = "mp4" if cmd.startswith("dub") else "wav"
    _clip(tmp_path, f"a.{ext}")
    for p in (f"a.{ext}", f"./a.{ext}", f"~/a.{ext}", f"../{tmp_path.name}/a.{ext}"):
        r = mcp_tool(cmd.format(p=p))
        assert r["ok"] is False and "absolut" in r["error"], p
    assert served.calls == [] and served.upload_calls == []


def test_mcp_input_must_be_a_regular_file_with_a_media_extension(served, mcp_tool, tmp_path):
    (tmp_path / "d.mp4").mkdir()
    _clip(tmp_path, "nota.txt")
    _clip(tmp_path, "segredo")
    for cmd in (f"dub create {tmp_path / 'd.mp4'}", f"dub create {tmp_path / 'nota.txt'}", f"transcribe {tmp_path / 'segredo'}",
                f"clone {tmp_path / 'nota.txt'} --name V", f"transcribe {tmp_path / 'a.mp4'}", f"transcribe {tmp_path / 'nao-existe.wav'}"):
        assert mcp_tool(cmd)["ok"] is False, cmd
    assert served.calls == [] and served.upload_calls == []


def test_mcp_symlink_to_a_non_media_target_is_refused_and_a_media_one_is_resolved(served, mcp_tool, tmp_path):
    secret = _clip(tmp_path, "id_rsa", b"-----BEGIN KEY-----")
    (tmp_path / "foto.mp4").symlink_to(secret)
    r = mcp_tool(f"dub create {tmp_path / 'foto.mp4'}")
    assert r["ok"] is False and served.upload_calls == []
    real = _clip(tmp_path, "real.mp4", b"video!")
    (tmp_path / "atalho.mp4").symlink_to(real)
    r = mcp_tool(f"dub create {tmp_path / 'atalho.mp4'}")
    assert r["ok"] is True and b'filename="real.mp4"' in served.upload_calls[0]["body"]  # the resolved file is what is sent


def test_mcp_input_inside_a_hidden_home_folder_or_a_system_folder_is_refused(served, mcp_tool, home):
    (home / ".ssh").mkdir()
    secret = home / ".ssh" / "voz.wav"
    secret.write_bytes(b"RIFF")
    r = mcp_tool(f"transcribe {secret}")
    assert r["ok"] is False and served.calls == []
    assert mcp_tool("transcribe /etc/voz.wav")["ok"] is False


def test_mcp_tts_needs_an_explicit_absolute_out(served, mcp_tool, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    r = mcp_tool("tts oi")
    assert r["ok"] is False and "--out" in r["error"] and served.calls == [] and list(tmp_path.iterdir()) == []


def test_terminal_tts_keeps_its_default_file_name(served, tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    rc, _, _ = _run(["tts", "oi"], capsys)
    assert rc == 0 and (tmp_path / "voicestudio.wav").read_bytes() == WAV


def test_mcp_refuses_to_overwrite_an_existing_target(served, mcp_tool, tmp_path):
    out = tmp_path / "fala.wav"
    out.write_bytes(b"MINHA")
    r = mcp_tool(f"tts oi --out {out}")
    assert r["ok"] is False and "já existe" in r["error"] and out.read_bytes() == b"MINHA" and served.calls == []
    mp4 = tmp_path / "d.mp4"
    mp4.write_bytes(b"MINHA")
    r = mcp_tool(f"dub-export --job j1 --lang pl -o {mp4}")
    assert r["ok"] is False and "já existe" in r["error"] and mp4.read_bytes() == b"MINHA" and served.dub_calls == []


def test_the_terminal_still_overwrites(served, tmp_path, capsys):
    out = tmp_path / "fala.wav"
    out.write_bytes(b"VELHO")
    rc, _, _ = _run(["tts", "oi", "--out", str(out)], capsys)
    assert rc == 0 and out.read_bytes() == WAV


def test_mcp_does_not_create_missing_parent_folders(served, mcp_tool, tmp_path):
    r = mcp_tool(f"tts oi --out {tmp_path / 'nova' / 'sub' / 'a.wav'}")
    assert r["ok"] is False and not (tmp_path / "nova").exists() and served.calls == []


def test_mcp_refuses_system_folders_hidden_home_folders_and_symlinked_targets(served, mcp_tool, tmp_path, home):
    assert mcp_tool("tts oi --out /etc/fala.wav")["ok"] is False
    (home / ".config").mkdir()
    assert mcp_tool(f"tts oi --out {home / '.config' / 'fala.wav'}")["ok"] is False
    alvo = tmp_path / "alvo.wav"
    link = tmp_path / "link.wav"
    link.symlink_to(alvo)
    assert mcp_tool(f"tts oi --out {link}")["ok"] is False and not alvo.exists()
    assert served.calls == []


def test_split_args_keeps_windows_backslashes():
    from simplicio_video import mcp_server
    assert mcp_server._split_args(r"tts oi --out C:\tmp\a.wav", windows=True) == ["tts", "oi", "--out", r"C:\tmp\a.wav"]
    assert mcp_server._split_args('tts "olá mundo" -o "C:\\a b\\x.wav"', windows=True) == ["tts", "olá mundo", "-o", "C:\\a b\\x.wav"]
    # sem aspas a linha é só separada em espaços (review rev177, F4): a barra não escapa o espaço; para um espaço, use aspas ou argv
    assert mcp_server._split_args(r"tts a\ b", windows=False) == ["tts", "a\\", "b"]
    assert mcp_server._split_args(r'tts "a b"', windows=False) == ["tts", "a b"]


def test_mcp_none_and_a_job_value_that_looks_like_an_option_do_not_crash_or_misparse(served, mcp_tool, tmp_path):
    r = mcp_tool(None)
    assert isinstance(r, dict) and r["ok"] is False
    r = mcp_tool(f"dub-export --job -oabc --lang pl -o {tmp_path / 'd.mp4'}")
    assert r["ok"] is False and "absolut" not in r["error"] and served.dub_calls == []


def test_mcp_description_states_the_new_rules_and_the_result_contract():
    from simplicio_video import mcp_server
    d = mcp_server.DESC_video_voicestudio
    for word in ("loopback", "rc", "já existe", "absolut"):
        assert word in d, word
