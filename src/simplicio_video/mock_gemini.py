"""Local MOCK of the Gemini TTS API for dry runs of the batch runner (no network, no key, no cost).

Serves POST /v1beta/interactions and /v1beta/models/<m>:generateContent with a synthetic WAV (24 kHz mono 16-bit:
a buzzy tone shaped like syllables, ~60 ms per character). NOT a voice: output of a mock run is for plumbing tests only.
  python -m simplicio_video.mock_gemini --port 8765 [--overlong-first N] [--log /tmp/mock-gemini-tts.jsonl]
  SIMPLICIO_GEMINI_BASE=http://127.0.0.1:8765/v1beta GEMINI_API_KEY=mock simplicio-video prospect ...
--overlong-first N: the first N requests return a take 2.5x too long (exercises "regenerate, never speed up").
Every request is appended to --log (JSON lines: path, model, voice, style, text) so a dry run can assert on it.
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import math
import struct
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SR = 24000


def take(text: str, stretch: float = 1.0) -> bytes:
    n = int(SR * max(0.4, 0.06 * len(text)) * stretch)
    frames = bytearray()
    for i in range(n):
        t = i / SR
        env = 0.5 + 0.5 * math.sin(2 * math.pi * 4.5 * t)  # ~4.5 "syllables" per second
        v = env * 0.35 * (math.sin(2 * math.pi * 220 * t) + 0.3 * math.sin(2 * math.pi * 660 * t))
        frames += struct.pack("<h", int(max(-1.0, min(1.0, v)) * 32767))
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(bytes(frames))
    return buf.getvalue()


def parse(path: str, body: dict) -> dict:
    if "interactions" in path:
        c = body["input"][0]["content"][0]
        style = next((x.get("style") for x in c.get("annotations", []) if x.get("type") == "speech_metadata"), "")
        return {"text": c["text"], "style": style, "voice": body["generation_config"]["speech_config"][0]["voice"],
                "model": body["model"]}
    p = body["contents"][0]["parts"][0]
    return {"text": p["text"], "style": (p.get("speech_metadata") or {}).get("style", ""),
            "voice": body["generationConfig"]["speechConfig"]["voiceConfig"]["prebuiltVoiceConfig"]["voiceName"],
            "model": path.split("/models/")[-1].split(":")[0]}


def serve(port: int = 8765, overlong_first: int = 0, log: str = "/tmp/mock-gemini-tts.jsonl"):
    state = {"n": 0}

    class H(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
            if not self.headers.get("x-goog-api-key"):
                self.send_response(401)
                self.end_headers()
                return
            req = parse(self.path, body)
            state["n"] += 1
            stretch = 2.5 if state["n"] <= overlong_first else 1.0
            b64 = base64.b64encode(take(req["text"], stretch)).decode()
            with open(log, "a", encoding="utf8") as f:
                f.write(json.dumps({"path": self.path, **req, "overlong": stretch > 1}, ensure_ascii=False) + "\n")
            if "interactions" in self.path:
                res = {"steps": [{"type": "model_output", "content": [{"type": "audio", "data": b64, "mime_type": "audio/wav"}]}],
                       "usage": {"mock": True}}
            else:
                res = {"candidates": [{"content": {"parts": [{"inlineData": {"mimeType": "audio/wav", "data": b64}}]}}]}
            out = json.dumps(res).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(out)))
            self.end_headers()
            self.wfile.write(out)

    ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--overlong-first", type=int, default=0)
    ap.add_argument("--log", default="/tmp/mock-gemini-tts.jsonl")
    a = ap.parse_args()
    serve(a.port, a.overlong_first, a.log)
