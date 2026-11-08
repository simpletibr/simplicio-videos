import json
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from simplicio_video import voice, voice_clone


def test_new_providers_registered():
    for p in ("voxcpm", "openvoice", "voicestudio", "audio8"):
        assert p in voice.PROVIDERS and p in voice.GENERATIVE


def test_keep_path_isolated_per_provider(tmp_path):
    assert voice.keep_path(tmp_path, "gemini", 0) == tmp_path / "line-01.wav"
    assert voice.keep_path(tmp_path, "voxcpm", 1) == tmp_path / "voxcpm" / "line-02.wav"


def test_voxcpm_cli_args(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setenv("VOXCPM_BIN", "/bin/voxcpm")
    monkeypatch.setattr("simplicio_video.childio.run_child", lambda cmd, **kw: calls.append(cmd) or 0)
    S = {"control": "warm", "reference_audio": "r.wav", "reference_text": "hello", "seed": 7}
    voice_clone.voxcpm(S, "hi", tmp_path / "o.wav", tmp_path / "r.wav")
    cmd = calls[0]
    assert cmd[:2] == ["/bin/voxcpm", "clone"] and "--prompt-text" in cmd and "--seed" not in cmd
    voice_clone.voxcpm({"control": "warm", "seed": 1}, "hi", tmp_path / "o.wav", None)
    assert calls[1][1] == "design"


def test_audio8_cli_args(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setenv("AUDIO8_TTS_BIN", "/bin/audio8-tts")
    monkeypatch.setattr("simplicio_video.childio.run_child", lambda cmd, **kw: calls.append(cmd) or 0)
    S = {"model": "Edge0/Audio8-TTS-Realistic-0.6b", "reference_text": "hello", "device": "cuda:0"}
    voice_clone.audio8(S, "hi", tmp_path / "o.wav", tmp_path / "r.wav")
    cmd = calls[0]
    assert cmd[0] == "/bin/audio8-tts" and cmd[cmd.index("--output") + 1] == str(tmp_path / "o.wav")
    assert cmd[cmd.index("--reference-audio") + 1] == str(tmp_path / "r.wav")
    assert cmd[cmd.index("--reference-text") + 1] == "hello" and cmd[cmd.index("--device") + 1] == "cuda:0"
    voice_clone.audio8({"model": S["model"]}, "hi", tmp_path / "o.wav", None)
    assert "--reference-audio" not in calls[1] and "--device" not in calls[1]


def test_audio8_missing_cli_is_clear(monkeypatch, tmp_path):
    monkeypatch.delenv("AUDIO8_TTS_BIN", raising=False)
    monkeypatch.setattr("shutil.which", lambda name: None)
    with pytest.raises(voice_clone.CloneVoiceError, match="AUDIO8_TTS_BIN"):
        voice_clone.audio8({"model": "x"}, "hi", tmp_path / "o.wav", None)


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


# ---- U22j: the local app is reached even when the environment has a proxy ---------------------------------------------------------------


def _quem_ouviu(monkeypatch):
    """A local app and a local PROXY, both recording what they are asked, and an environment whose only proxy is that one (no `no_proxy` at all:
    what urllib would send to a proxy, it sends to this one). Returns (app port, what the app heard, what the proxy heard, stop)."""
    app_ouviu, proxy_ouviu = [], []

    class App(BaseHTTPRequestHandler):
        def do_POST(self):
            app_ouviu.append((self.path, self.headers.get("Authorization"), json.loads(self.rfile.read(int(self.headers["Content-Length"])))))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"RIFFdata")

        def log_message(self, *a):
            pass

    class Proxy(BaseHTTPRequestHandler):
        def do_POST(self):  # a proxy that is handed a call to the loopback of its client: it cannot make it, and it has read it all
            corpo = self.rfile.read(int(self.headers.get("Content-Length") or 0)).decode()
            proxy_ouviu.append((self.path, self.headers.get("Authorization"), corpo))
            self.send_response(403)
            self.end_headers()

        def log_message(self, *a):
            pass

    app, proxy = HTTPServer(("127.0.0.1", 0), App), HTTPServer(("127.0.0.1", 0), Proxy)
    for srv in (app, proxy):
        threading.Thread(target=srv.serve_forever, daemon=True).start()
    for nome in list(os.environ):
        if nome.lower().endswith("_proxy"):
            monkeypatch.delenv(nome)
    monkeypatch.setenv("http_proxy", f"http://127.0.0.1:{proxy.server_port}")
    monkeypatch.setenv("VOICESTUDIO_API_KEY", "S3CR3T-vs")

    def parar():
        app.shutdown()
        proxy.shutdown()

    return app.server_port, app_ouviu, proxy_ouviu, parar


@pytest.mark.allow_hosts(["127.0.0.1", "::1", "localhost"])
@pytest.mark.parametrize("host", ["127.0.0.1", "localhost"])
def test_voicestudio_reaches_the_local_app_and_not_the_proxy_of_the_environment(monkeypatch, tmp_path, host):
    """RED before U22j: with `http_proxy` in the environment the call went to the proxy, with the Bearer key and the text of the speech in the
    clear, and the app heard nothing (`localhost` too: `no_proxy` was not set, and a `no_proxy` that does not list the host does not help)."""
    porta, app_ouviu, proxy_ouviu, parar = _quem_ouviu(monkeypatch)
    monkeypatch.setenv("VOICESTUDIO_URL", f"http://{host}:{porta}")
    out = tmp_path / "o.wav"
    try:
        voice_clone.voicestudio({"model": "omnivoice", "voice": "me"}, "fala confidencial", out)
    finally:
        parar()
    assert proxy_ouviu == []
    assert [(c, a, b["input"]) for c, a, b in app_ouviu] == [("/v1/audio/speech", "Bearer S3CR3T-vs", "fala confidencial")]
    assert out.read_bytes() == b"RIFFdata"
