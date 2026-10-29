import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from simplicio_video import voice, voice_clone


def test_new_providers_registered():
    for p in ("voxcpm", "openvoice", "voicestudio"):
        assert p in voice.PROVIDERS and p in voice.GENERATIVE


def test_keep_path_isolated_per_provider(tmp_path):
    assert voice.keep_path(tmp_path, "gemini", 0) == tmp_path / "line-01.wav"
    assert voice.keep_path(tmp_path, "voxcpm", 1) == tmp_path / "voxcpm" / "line-02.wav"


def test_voxcpm_cli_args(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setenv("VOXCPM_BIN", "/bin/voxcpm")
    monkeypatch.setattr("subprocess.run", lambda cmd, check: calls.append(cmd))
    S = {"control": "warm", "reference_audio": "r.wav", "reference_text": "hello", "seed": 7}
    voice_clone.voxcpm(S, "hi", tmp_path / "o.wav", tmp_path / "r.wav")
    cmd = calls[0]
    assert cmd[:2] == ["/bin/voxcpm", "clone"] and "--prompt-text" in cmd and "--seed" not in cmd
    voice_clone.voxcpm({"control": "warm", "seed": 1}, "hi", tmp_path / "o.wav", None)
    assert calls[1][1] == "design"


def test_openvoice_requires_reference_and_env(monkeypatch, tmp_path):
    with pytest.raises(SystemExit, match="reference_audio"):
        voice_clone.openvoice({}, "hi", tmp_path / "o.wav", None, lambda t, p: None)
    monkeypatch.delenv("OPENVOICE_PY", raising=False)
    with pytest.raises(SystemExit, match="OPENVOICE_PY"):
        voice_clone.openvoice({}, "hi", tmp_path / "o.wav", tmp_path / "r.wav", lambda t, p: None)


def test_voicestudio_http(monkeypatch, tmp_path):
    seen = {}

    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            seen["path"] = self.path
            seen["body"] = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"RIFFdata")

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.setenv("VOICESTUDIO_URL", f"http://127.0.0.1:{srv.server_port}")
    out = tmp_path / "o.wav"
    voice_clone.voicestudio({"model": "omnivoice", "voice": "me"}, "hello", out)
    srv.shutdown()
    assert seen["path"] == "/v1/audio/speech" and seen["body"]["voice"] == "me" and out.read_bytes() == b"RIFFdata"
