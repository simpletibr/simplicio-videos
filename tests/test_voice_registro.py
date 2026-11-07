"""Voice providers: what the registry refactor (U21) must not change, frozen BEFORE the refactor.

`voice.py` used to describe a provider in six parallel places (PROVIDERS, NETWORK_PROVIDERS, GENERATIVE, settings_for,
_generate, keep_path) and the loop of `run()` branched on the provider name. These tests pin what comes out of that
code: the table, the settings of each provider (with the order of their keys, which is the order of the lock), the cache
key of a line, the final audio, `timing.lock.json` byte for byte and every error message of every provider.

Three layers, from the most portable to the most exact:
- exact on any machine: the settings, the cache key, the lock with the audio-dependent numbers masked, the texts;
- exact on any machine with ffmpeg: the final WAV equals the one made by the documented ffmpeg chain, run here by the test;
- exact on ONE ffmpeg build (FROZEN_ON): the sha256 of the lock and of the final WAV. Elsewhere that test is skipped.

No network, no key, no engine: the HTTP layer and the child processes are faked, the takes are made here in integers.
"""
import ast
import atexit
import base64
import dataclasses
import hashlib
import inspect
import io
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import wave
from pathlib import Path
from unittest import mock

import pytest

from conftest import FIXTURE
from simplicio_video import catalog, childio
from simplicio_video import contract as ct
from simplicio_video import voice, voice_clone, voz_catalogo

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None, reason="needs ffmpeg and ffprobe")

FROZEN_ON = "ffmpeg version 6.1.1-3ubuntu5"

DESCRICOES = {
    "file": "WAV/MP3 per line generated elsewhere (Gemini in Google AI Studio). Default dir assets/audio/vo/external, line-01.wav ...",
    "local": "Provisional local TTS: Kokoro-82M (Apache-2.0) via kokoro-onnx; needs SIMPLICIO_TTS_PY with kokoro_onnx + models in ~/.local/share/simplicio-tts",
    "gemini": "Gemini TTS API (GEMINI_API_KEY from aistudio.google.com/apikey; free tier ok): model/voice/estilo from the contract, WAV 24 kHz kept in the file dir so provider=file reproduces it",
    "voxcpm": "VoxCPM2 (Apache-2.0): voice design (control) or cloning from reference_audio via the `voxcpm` CLI; fixed seed",
    "openvoice": "OpenVoice V2 (MIT): Kokoro base take converted to the reference_audio speaker (needs OPENVOICE_PY + checkpoints_v2)",
    "voicestudio": "VoiceStudio (AGPL-3.0, used over local HTTP only): OpenAI-compatible /v1/audio/speech at VOICESTUDIO_URL (default http://localhost:3900); voice = profile id",
    "audio8": "Audio8 TTS (Apache-2.0 code and 0.6B weights): zero-shot cloning from reference_audio via the `audio8-tts` CLI in its own env (AUDIO8_TTS_BIN)",
    "elevenlabs": "stub in v0.2 (generate elsewhere, then use provider=file)",
    "xai": "stub in v0.2 (generate elsewhere, then use provider=file)",
}
# name -> (waits on the network, keeps the raw take)
REDE_E_BRUTO = {"file": (False, False), "local": (False, False), "gemini": (True, True), "voxcpm": (False, True),
                "openvoice": (False, True), "voicestudio": (False, True), "audio8": (False, True),
                "elevenlabs": (False, False), "xai": (False, False)}

TRIM = ("silenceremove=start_periods=1:start_threshold=-55dB:start_silence=0.06,areverse,"
        "silenceremove=start_periods=1:start_threshold=-50dB:start_silence=0.10,areverse")
TRIM_TIGHT = ("silenceremove=start_periods=1:start_threshold=-42dB:start_silence=0.04,areverse,"
              "silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.08,areverse")
DEFAULT_CHAIN = ("highpass=f=85,equalizer=f=320:t=q:w=1.1:g=-2.5,equalizer=f=3400:t=q:w=1.3:g=2.5,"
                 "equalizer=f=9000:t=q:w=1:g=1.5,acompressor=threshold=-20dB:ratio=2.5:attack=8:release=140:makeup=2:knee=4,"
                 "aecho=1.0:1.0:19|31|47:0.09|0.06|0.04")


# ---------------------------------------------------------------- takes made here, in integers (same bytes on every machine)
def _wav(samples: list[int], sr: int = 24000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1), w.setsampwidth(2), w.setframerate(sr)
        w.writeframes(struct.pack(f"<{len(samples)}h", *samples))
    return buf.getvalue()


def _square(seconds: float, period: int = 48, amp: int = 8000, sr: int = 24000) -> list[int]:
    return [amp if (i // (period // 2)) % 2 == 0 else -amp for i in range(int(seconds * sr))]


def _take(kind: str, text: str, seconds: float = 0.3) -> bytes:
    """A take that depends on who made it and on the text, so a line sent to the wrong provider or with the wrong text shows."""
    period = 40 + int.from_bytes(hashlib.sha256(f"{kind}|{text}".encode()).digest()[:2], "big") % 400
    return _wav(_square(seconds, period))


def _take_with_air_leadin(tone_s: float = 0.25) -> bytes:
    """AI Studio-like take: 0.25 s of noise at about -49 dBFS (TRIM keeps it, TRIM_TIGHT cuts it), a tone, then silence."""
    state, noise = 12345, []
    for _ in range(int(0.25 * 24000)):
        state = (state * 1103515245 + 12345) % (1 << 31)
        noise.append(120 if state & 0x10000 else -120)
    return _wav(noise + _square(tone_s) + [0] * int(0.3 * 24000))


# ---------------------------------------------------------------- the contract: the mini fixture with another `voz`
def _contract(dest: Path, provider: str, providers: dict | None = None, voz_extra: str = "", file_dir: str = "ext") -> Path:
    """Copy of tests/fixtures/mini whose voz.provider is `provider`; the `file` provider reads from `file_dir` (also where the
    raw takes of the generative providers are kept)."""
    shutil.copytree(FIXTURE, dest, ignore=shutil.ignore_patterns("out", "build", "timing.lock.json", "render.manifest.json", "voz"))
    path = dest / "contract.yaml"
    txt = path.read_text(encoding="utf8")
    blocks = {"file": {"dir": file_dir}, **(providers or {})}
    txt = txt.replace("providers: { file: { dir: vo } }", "providers: " + json.dumps(blocks))
    txt = txt.replace("  provider: file\n", f"  provider: {provider}\n{voz_extra}")
    path.write_text(txt, encoding="utf8")
    (dest / "ref.wav").write_bytes(_wav(_square(0.5, 56)))
    return path


GEMINI = {"voice": "Laomedeia", "estilo": "alegre"}
CASES = {
    "file": dict(provider="file", file_dir="vo"),
    "file_tight": dict(provider="file", file_dir="vo", take=_take_with_air_leadin()),
    "local": dict(provider="local", providers={"local": {"speed": 1.1, "lang": "pt-br"}}, voz_extra="  voice: pm_alex\n"),
    "gemini": dict(provider="gemini", providers={"gemini": GEMINI}),
    "gemini_generate_content": dict(provider="gemini", providers={"gemini": {**GEMINI, "api": "generate_content"}}),
    "voxcpm": dict(provider="voxcpm", providers={"voxcpm": {"control": "warm", "reference_audio": "ref.wav", "reference_text": "hello",
                                                           "seed": 7}}),
    "audio8": dict(provider="audio8", providers={"audio8": {"reference_audio": "ref.wav", "reference_text": "hello", "device": "cuda:0"}}),
    "openvoice": dict(provider="openvoice", providers={"openvoice": {"reference_audio": "ref.wav"}, "local": {"voice": "pf_dora"}}),
    "voicestudio": dict(provider="voicestudio", providers={"voicestudio": {"model": "omnivoice"}}, voz_extra="  voice: minha-voz\n"),
}

# frozen BEFORE the refactor, on the code of main 0eff833
SETTINGS = {  # json.dumps(settings_for(c, provider)): the ORDER of the keys is the order of `settings` in timing.lock.json
    "file": '{"dir": "vo", "padroes": ["line-{n:02d}.wav", "{id}.wav", "line-{n:02d}.mp3", "line-{n:02d}.m4a"]}',
    "file_tight": '{"dir": "vo", "padroes": ["line-{n:02d}.wav", "{id}.wav", "line-{n:02d}.mp3", "line-{n:02d}.m4a"]}',
    "local": '{"engine": "kokoro", "voice": "pm_alex", "speed": 1.1, "lang": "pt-br"}',
    "gemini": '{"model": "gemini-3.8-flash-tts", "voice": "Laomedeia", "estilo": "alegre"}',
    "gemini_generate_content": '{"model": "gemini-3.8-flash-tts", "voice": "Laomedeia", "estilo": "alegre", "api": "generate_content"}',
    "voxcpm": '{"control": "warm", "reference_audio": "ref.wav", "reference_text": "hello", "seed": 7}',
    "audio8": '{"model": "Edge0/Audio8-TTS-Realistic-0.6b", "reference_audio": "ref.wav", "reference_text": "hello", "device": "cuda:0"}',
    "openvoice": '{"reference_audio": "ref.wav", "base": {"engine": "kokoro", "voice": "pf_dora", "speed": 1.0, "lang": "pt-br"}}',
    "voicestudio": '{"model": "omnivoice", "voice": "minha-voz"}',
}
IDENT = {  # the cache key of the line `vo1`: _digest(_line_ident(...))
    "file": "fd31c6a4abca",
    "file_tight": "46ea2f113b3c",
    "local": "3bf8472f5d2d",
    "gemini": "35fb225fae47",
    "gemini_generate_content": "f25ac13c6a17",
    "voxcpm": "8652b5ef58cf",
    "audio8": "8a4ccc197ae9",
    "openvoice": "64341dc1712f",
    "voicestudio": "d1fd8767289e",
}
LOCK_MASKED = {  # sha256 of the lock with the audio-dependent numbers masked, after the 1st run and after the 2nd (cache hit)
    "file": ("ce1f4cf79a0189266019a3f3810212f0f33bfc16e29b837c64b07dec711a616b", "ce1f4cf79a0189266019a3f3810212f0f33bfc16e29b837c64b07dec711a616b"),
    "file_tight": ("60108a1a040a7b7b9b9a8f17bd699e8441d37845aa6d9996d7c12a23017cad30", "60108a1a040a7b7b9b9a8f17bd699e8441d37845aa6d9996d7c12a23017cad30"),
    "local": ("7f21d5cd8db617c2626e4a2ce18f04768f2572ba82c616cc09c7bccd1a71c254", "7f21d5cd8db617c2626e4a2ce18f04768f2572ba82c616cc09c7bccd1a71c254"),
    "gemini": ("55afedc820895f4a0196ca61c8bf3290c35076a0327421aef0eed38ea7e29884", "c6c443ada272a8b7f586a73889a247a6ceea49bc9f489e5dd20e139b2067f151"),
    "gemini_generate_content": ("36708262a095da72df0affb5ac744e0207a2da1f8e3c5a41652bb95e6b01bc6e", "05c8f3fe2f3195967621f6de694daf27026945c2ad0cb66ce3343c806275fa5e"),
    "voxcpm": ("9c4c6b2fab533f9d6e102d0b20b8cec679a7a8cff64739bfe509b09484dda621", "9c4c6b2fab533f9d6e102d0b20b8cec679a7a8cff64739bfe509b09484dda621"),
    "audio8": ("7fa1e007b6f93342ca888e76cdd70e9d606918c8912f8fa96a0bfeaa517b32be", "7fa1e007b6f93342ca888e76cdd70e9d606918c8912f8fa96a0bfeaa517b32be"),
    "openvoice": ("4d590324e2237bf9f7facf4375033ea4ed6f09c4e11066c78ca609efeb5e19b7", "4d590324e2237bf9f7facf4375033ea4ed6f09c4e11066c78ca609efeb5e19b7"),
    "voicestudio": ("dc56d3323a813e76dfa14bd17d3770e602f034737535692a95824849a4b13732", "dc56d3323a813e76dfa14bd17d3770e602f034737535692a95824849a4b13732"),
}
LOCK_SHA = {  # sha256 of timing.lock.json and of the final WAV of line vo1, on FROZEN_ON, 1st run and 2nd run
    "file": ("d44f7bc44619fd0e5d535d7596ada1eb7e47a93651d36005efb3b64bce5019d3", "6fcfb7960a69f3ac671373891ea0583324d4be3eddd3895577fb711ed7a89ab2", "d44f7bc44619fd0e5d535d7596ada1eb7e47a93651d36005efb3b64bce5019d3"),
    "file_tight": ("7bb2a9231e1e5fec91045faf946cdbda195b4df9feb807a9e7d582879659be94", "aef5a8a346e8ac8a7eca7b6bc0ed7023d6c9896c902e13be92559b4035799e81", "7bb2a9231e1e5fec91045faf946cdbda195b4df9feb807a9e7d582879659be94"),
    "local": ("956643287493f4a737a76ec4a72503f33a9477794939e178726cbb7429b9d0f9", "7a1f68b3a1b72ee926f96064a5a0ff9e8ebdc18c3f0267f4558fea47a5b67a6b", "956643287493f4a737a76ec4a72503f33a9477794939e178726cbb7429b9d0f9"),
    "gemini": ("80bf0c54ae9d96d1196b09f85277059ab109d497b88bd2340e6d58500ed2692d", "c7df9653af711e38bb1ac7b5389656777353dbbf4b362cde37065599079cd55f", "bf8ea9b78e363c05b51ca1dfb4e7dc5d6f0d29009b0dcda690c5390455b4048f"),
    "gemini_generate_content": ("b1870969b345d6389fbbcb202263e7d53bdebd42598bb5839ee301033fcf83ea", "c7df9653af711e38bb1ac7b5389656777353dbbf4b362cde37065599079cd55f", "15584bac0bf1f4081b9768a93bdd2259df7904e791ced432c078c315a1e08606"),
    "voxcpm": ("63a9c8efdfe69c9d9f5072e4f2090dc4ab79714dd4763676b3fe48955b40a373", "ca21a7f871c9c545235009468187a6d53ecee0c9acc9199fa9e622f2408a9859", "63a9c8efdfe69c9d9f5072e4f2090dc4ab79714dd4763676b3fe48955b40a373"),
    "audio8": ("af670578f834b5d47de06563405a31942eb19f1b06b295dad53d7100c836576b", "62d9bca584dd9cf70c685adbefdd631a4dbf34aa19e90c7a1a0541ffa667dc80", "af670578f834b5d47de06563405a31942eb19f1b06b295dad53d7100c836576b"),
    "openvoice": ("dd5fc1d315492fce3bc0911e3dc4f93ca49533f7843c66411a669f45978d6a8b", "fb1c1cd3e78c2afca15228576e79acc233a747ede464dd423cf143ac5cd8e89e", "dd5fc1d315492fce3bc0911e3dc4f93ca49533f7843c66411a669f45978d6a8b"),
    "voicestudio": ("bd33683cc4078c97715071d244e976312451c83c910690255e38354960e67dd4", "24afa82dd24547959d123de119c614d5477c35e5805f3549345f1dcdf8161a7b", "bd33683cc4078c97715071d244e976312451c83c910690255e38354960e67dd4"),
}


# ---------------------------------------------------------------- the fakes of the network and of the engines
class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class Mundo:
    """Everything a provider touches, faked: urlopen (gemini, voicestudio) and the child processes (local, voxcpm, audio8, openvoice)."""

    def __init__(self, root: Path):
        self.root = root
        self.http: list[dict] = []
        self.filhos: list[list[str]] = []
        (root / "ckpt" / "converter").mkdir(parents=True)
        (root / "ckpt" / "converter" / "checkpoint.pth").write_bytes(b"x")

    def urlopen(self, req, timeout=0):
        body = json.loads(req.data)
        self.http.append({"url": req.full_url, "headers": dict(req.header_items()), "body": body, "timeout": timeout})
        if req.full_url.endswith("/v1/audio/speech"):
            return _Resp(_take("voicestudio", body["input"]))
        text = body["input"][0]["content"][0]["text"] if "input" in body else body["contents"][0]["parts"][0]["text"]
        if "generateContent" in req.full_url:  # the legacy shape: raw 16-bit PCM in inlineData
            pcm = _take("gemini", text)[44:]
            res = {"candidates": [{"content": {"parts": [{"inlineData": {"mimeType": "audio/L16;codec=pcm;rate=24000",
                                                                          "data": base64.b64encode(pcm).decode()}}]}}],
                   "usageMetadata": {"totalTokenCount": 11}}
        else:
            res = {"steps": [{"type": "model_output", "content": [{"type": "audio", "mime_type": "audio/wav",
                                                                  "data": base64.b64encode(_take("gemini", text)).decode()}]}],
                   "usage": {"total_tokens": 7}}
        return _Resp(json.dumps(res).encode())

    def check_child(self, argv, **kw):
        cmd = [str(a) for a in argv]
        self.filhos.append(cmd)
        if cmd[1] == "-c":  # the local provider: [py, -c, code, tts_dir, text, voice, speed, lang, dst]
            Path(cmd[-1]).write_bytes(_take("local", cmd[4]))
        elif cmd[0].endswith("openvoice_convert.py") or cmd[1].endswith("openvoice_convert.py"):  # [py, script, ckpt, base, ref, dst]
            assert Path(cmd[3]).is_file(), "the base take is made before the conversion"
            Path(cmd[-1]).write_bytes(_take("openvoice", Path(cmd[3]).read_bytes().hex()[:40]))
        else:  # voxcpm / audio8: --text T ... --output DST
            Path(cmd[cmd.index("--output") + 1]).write_bytes(_take(Path(cmd[0]).name, cmd[cmd.index("--text") + 1]))

    def env(self) -> dict:
        return {"GEMINI_API_KEY": "test-key", "SIMPLICIO_TTS_PY": sys.executable, "KOKORO_DIR": "/kokoro", "VOXCPM_BIN": "/bin/voxcpm",
                "VOXCPM_DEVICE": "", "AUDIO8_TTS_BIN": "/bin/audio8-tts", "OPENVOICE_PY": sys.executable,
                "OPENVOICE_CHECKPOINTS": str(self.root / "ckpt"), "VOICESTUDIO_URL": "http://localhost:3900", "VOICESTUDIO_API_KEY": "",
                "SIMPLICIO_GEMINI_BASE": ""}

    def __enter__(self):
        self._p = [mock.patch.object(urllib.request, "urlopen", self.urlopen), mock.patch.object(childio, "check_child", self.check_child),
                   mock.patch.dict(os.environ, self.env())]
        for p in self._p:
            p.start()
        return self

    def __exit__(self, *a):
        for p in reversed(self._p):
            p.stop()


# ---------------------------------------------------------------- one run of a case, cached (the tests below read it)
_ROOT = Path(tempfile.mkdtemp(prefix="voice-registro-"))
atexit.register(shutil.rmtree, _ROOT, True)
_CACHE: dict[str, dict] = {}


def _mask(lock_text: str) -> str:
    """The lock without what the audio decides (sha256, durations, slack, words): everything else stays, in its order."""
    d = json.loads(lock_text)
    for m in d["lines"].values():
        m["sha256"], m["dur_s"], m["slack_s"], m["words"] = "<sha256>", "<dur>", "<slack>", "<words>"
    return json.dumps(d, indent=2, ensure_ascii=False)


def _sha(data: bytes | str) -> str:
    return hashlib.sha256(data if isinstance(data, bytes) else data.encode()).hexdigest()


def _executa(caso: str) -> dict:
    if caso in _CACHE:
        return _CACHE[caso]
    spec = dict(CASES[caso])
    take = spec.pop("take", None)
    dest = _ROOT / caso
    path = _contract(dest / "p", **spec)
    if take is not None:
        (path.parent / "vo" / "line-01.wav").write_bytes(take)
    out: dict = {"path": path}
    with Mundo(dest) as mundo:
        c = ct.load(path)
        out["settings"] = voice.settings_for(c, c.data["voz"]["provider"])
        line = c.lines()[0]
        chain = c.data["voz"].get("processamento", voice.DEFAULT_CHAIN)
        out["ident"] = voice._digest(voice._line_ident(c, c.data["voz"]["provider"], out["settings"], chain, line, 0))
        logs: list[str] = []
        out["lock1"] = voice.run(ct.load(path), log=logs.append)
        out["text1"] = (path.parent / "timing.lock.json").read_text(encoding="utf8")
        out["final1"] = (path.parent / out["lock1"]["lines"]["vo1"]["file"]).read_bytes()
        out["logs1"] = logs
        out["gastos1"] = (len(mundo.http), len(mundo.filhos))
        out["lock2"] = voice.run(ct.load(path), log=lambda *_: None)
        out["text2"] = (path.parent / "timing.lock.json").read_text(encoding="utf8")
        out["gastos2"] = (len(mundo.http), len(mundo.filhos))
        out["http"], out["filhos"] = mundo.http, mundo.filhos
    _CACHE[caso] = out
    return out


def _ffmpeg_version() -> str:
    return subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True).stdout.splitlines()[0]


# ================================================================ the table of providers
def test_providers_table_is_frozen():
    assert list(voice.PROVIDERS) == list(DESCRICOES)
    assert voice.PROVIDERS == DESCRICOES


def test_network_and_raw_take_flags_are_frozen():
    assert voice.NETWORK_PROVIDERS == tuple(n for n, (rede, _) in REDE_E_BRUTO.items() if rede) == ("gemini",)
    assert voice.GENERATIVE == tuple(n for n, (_, bruto) in REDE_E_BRUTO.items() if bruto)
    assert voice.GENERATIVE == ("gemini", "voxcpm", "openvoice", "voicestudio", "audio8")


def test_catalog_lists_the_voices_in_the_table_order():
    assert catalog.voices() == [{"id": k, "desc": v} for k, v in DESCRICOES.items()]


def test_processing_constants_are_frozen():
    assert (voice.TRIM, voice.TRIM_TIGHT, voice.DEFAULT_CHAIN) == (TRIM, TRIM_TIGHT, DEFAULT_CHAIN)
    assert voice.FILE_PATTERNS == ["line-{n:02d}.wav", "{id}.wav", "line-{n:02d}.mp3", "line-{n:02d}.m4a"]
    assert (voice.GEMINI_MODEL, voice.GEMINI_SR, voice.DEFAULT_CONCURRENCY) == ("gemini-3.8-flash-tts", 24000, 4)
    assert voice.AUDIO8_MODEL == "Edge0/Audio8-TTS-Realistic-0.6b"


@pytest.mark.parametrize("prov", list(DESCRICOES))
def test_keep_path_of_every_provider(tmp_path, prov):
    esperado = tmp_path / "line-03.wav" if prov == "gemini" else tmp_path / prov / "line-03.wav"
    assert voice.keep_path(tmp_path, prov, 2) == esperado


@pytest.mark.parametrize("prov", list(DESCRICOES))
def test_concurrency_only_for_the_providers_that_wait_on_the_network(prov):
    assert voice.effective_concurrency(prov, 8) == (8 if prov == "gemini" else 1)
    assert voice.effective_concurrency(prov, None) == (4 if prov == "gemini" else 1)
    assert voice.effective_concurrency("nao-existe", 8) == 1


# ================================================================ settings and cache key
@pytest.mark.parametrize("caso", list(CASES))
def test_settings_are_frozen_with_the_order_of_their_keys(caso):
    assert json.dumps(_executa(caso)["settings"]) == SETTINGS[caso]


def test_a_gemini_api_other_than_interactions_enters_the_settings_and_the_key(tmp_path):
    """The branch `api != interactions`: `interactions` (the default, spelled out or not) keeps the key of v0.2, anything else changes it."""
    def ident(api):
        blocks = {"gemini": {**GEMINI, **({"api": api} if api else {})}}
        c = ct.load(_contract(tmp_path / f"c-{api}", "gemini", blocks))
        S = voice.settings_for(c, "gemini")
        return S, voice._digest(voice._line_ident(c, "gemini", S, "highpass=f=85", c.lines()[0], 0))
    (s0, k0), (s1, k1), (s2, k2) = ident(None), ident("interactions"), ident("generate_content")
    assert s0 == s1 and "api" not in s0 and k0 == k1
    assert s2["api"] == "generate_content" and k2 != k0


@pytest.mark.parametrize("caso", list(CASES))
def test_cache_key_is_frozen(caso):
    assert _executa(caso)["ident"] == IDENT[caso]


def test_settings_of_the_stubs_and_of_an_unknown_provider_are_their_own_block(tmp_path):
    c = ct.load(_contract(tmp_path / "c", "file", {"elevenlabs": {"voice": "x"}, "xai": {}, "nada": {"a": 1}}))
    assert voice.settings_for(c, "elevenlabs") == {"voice": "x"}
    assert voice.settings_for(c, "xai") == {}
    assert voice.settings_for(c, "nada") == {"a": 1}
    assert voice.settings_for(c, "outro") == {}


def test_local_voice_comes_from_the_block_then_from_voz_only_when_the_provider_is_local(tmp_path):
    def voz(provider, blocks, extra=""):
        return voice.settings_for(ct.load(_contract(tmp_path / f"c{len(list(tmp_path.iterdir()))}", provider, blocks, extra)), "local")
    assert voz("gemini", {}, "  voice: pm_alex\n")["voice"] == "pf_dora"
    assert voz("local", {}, "  voice: pm_alex\n")["voice"] == "pm_alex"
    assert voz("local", {"local": {"voice": "pf_dora"}}, "  voice: pm_alex\n")["voice"] == "pf_dora"


# ================================================================ the lock and the audio
@pytest.mark.parametrize("caso", list(CASES))
def test_lock_masked_is_frozen(caso):
    r = _executa(caso)
    assert (_sha(_mask(r["text1"])), _sha(_mask(r["text2"]))) == LOCK_MASKED[caso], _mask(r["text1"])


@pytest.mark.parametrize("caso", list(CASES))
def test_lock_is_written_with_indent_2_and_a_final_newline(caso):
    r = _executa(caso)
    for t in (r["text1"], r["text2"]):
        assert t == json.dumps(json.loads(t), indent=2, ensure_ascii=False) + "\n"
    assert list(json.loads(r["text1"])) == ["schema", "provider", "settings", "processing", "cache_dir", "lines"] + (
        ["usage"] if CASES[caso]["provider"] == "gemini" else [])


@pytest.mark.parametrize("caso", list(CASES))
def test_final_audio_is_the_one_of_the_documented_chain(caso, tmp_path):
    """The processed take = source -> (48 kHz mono, except the local provider) -> TRIM -> chain + aresample -> pcm_s16le -bitexact."""
    r = _executa(caso)
    m, prov = r["lock1"]["lines"]["vo1"], CASES[caso]["provider"]
    take = r["path"].parent / m["source"] if m["source"] else None
    if prov == "local":
        take = tmp_path / "local-take.wav"
        take.write_bytes(_take("local", "tom de teste"))
    chain = r["lock1"]["processing"]

    def ff(*a):
        subprocess.run(["ffmpeg", "-y", "-v", "error", *a], check=True, stdin=subprocess.DEVNULL)

    raw, cut, final = tmp_path / "raw.wav", tmp_path / "cut.wav", tmp_path / "final.wav"
    if prov == "local":
        raw = take
    else:
        ff("-i", str(take), "-ac", "1", "-ar", "48000", str(raw))
    ff("-i", str(raw), "-af", TRIM_TIGHT if m.get("trim") == "tight" else TRIM, str(cut))
    ff("-i", str(cut), "-af", chain + ",aresample=48000", "-ac", "1", "-c:a", "pcm_s16le", "-bitexact", str(final))
    assert r["final1"] == final.read_bytes()
    assert m["sha256"] == _sha(r["final1"])


def test_the_overlong_take_takes_the_tight_trim_and_the_others_keep_the_normal_one():
    assert _executa("file_tight")["lock1"]["lines"]["vo1"]["trim"] == "tight"
    for caso in CASES:
        if caso != "file_tight":
            assert "trim" not in _executa(caso)["lock1"]["lines"]["vo1"], caso


@pytest.mark.parametrize("caso", list(CASES))
def test_where_each_provider_keeps_its_take_and_what_it_spends(caso):
    r, prov = _executa(caso), CASES[caso]["provider"]
    m = r["lock1"]["lines"]["vo1"]
    fonte = {"file": "vo/line-01.wav", "local": None, "gemini": "ext/line-01.wav"}.get(prov, f"ext/{prov}/line-01.wav")
    assert m["source"] == fonte
    if fonte and prov != "file":
        assert (r["path"].parent / fonte).is_file()  # the raw take stays: provider=file reproduces the run
    assert ("tts" in m) == (prov == "gemini")
    assert ("usage" in r["lock1"]) == (prov == "gemini")
    assert r["gastos1"] != (0, 0) or prov == "file"  # the first run asks the provider...
    assert r["gastos2"] == r["gastos1"]  # ...and the second one is the cache: it asks nobody


def test_gemini_lock_keeps_what_the_first_run_paid_for_when_the_second_run_is_cached():
    r = _executa("gemini")
    m1, m2 = r["lock1"]["lines"]["vo1"], r["lock2"]["lines"]["vo1"]
    assert r["lock1"]["usage"]["tts_chars_this_run"] == len("tom de teste") and r["lock2"]["usage"]["tts_chars_this_run"] == 0
    assert m1["tts"] == {"api": "interactions", "model": "gemini-3.8-flash-tts", "voice": "Laomedeia", "mime": "audio/wav",
                         "chars": len("tom de teste"), "usage": {"total_tokens": 7}}
    assert m2["tts"] == m1["tts"]
    g = _executa("gemini_generate_content")["lock1"]["lines"]["vo1"]["tts"]
    assert g["api"] == "generate_content" and g["mime"] == "audio/L16;codec=pcm;rate=24000" and g["usage"] == {"totalTokenCount": 11}


def test_what_each_provider_asked_of_the_world():
    g = _executa("gemini")["http"][0]
    assert g["url"] == "https://generativelanguage.googleapis.com/v1beta/interactions" and g["headers"]["X-goog-api-key"] == "test-key"
    assert g["body"]["generation_config"]["speech_config"] == [{"voice": "Laomedeia"}] and g["timeout"] == 180
    gc = _executa("gemini_generate_content")["http"][0]
    assert gc["url"] == "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash-tts:generateContent"
    v = _executa("voicestudio")["http"][0]
    assert v["url"] == "http://localhost:3900/v1/audio/speech" and v["timeout"] == 300
    assert v["body"] == {"model": "omnivoice", "voice": "minha-voz", "input": "tom de teste", "response_format": "wav"}
    assert _executa("local")["filhos"][0][1:] == ["-c", mock.ANY, "/kokoro", "tom de teste", "pm_alex", "1.1", "pt-br", mock.ANY]
    ref = str(_executa("voxcpm")["path"].parent / "ref.wav")
    out = str(_executa("voxcpm")["path"].parent / "ext" / "voxcpm" / "line-01.wav")
    assert _executa("voxcpm")["filhos"][0] == ["/bin/voxcpm", "clone", "--text", "tom de teste", "--reference-audio", ref, "--output", out,
                                               "--prompt-audio", ref, "--prompt-text", "hello", "--control", "warm"]
    out8 = str(_executa("audio8")["path"].parent / "ext" / "audio8" / "line-01.wav")
    assert _executa("audio8")["filhos"][0] == ["/bin/audio8-tts", "--model", "Edge0/Audio8-TTS-Realistic-0.6b", "--text", "tom de teste",
                                               "--output", out8, "--reference-audio", str(_executa("audio8")["path"].parent / "ref.wav"),
                                               "--reference-text", "hello", "--device", "cuda:0"]
    ov = _executa("openvoice")["filhos"]  # the base take (Kokoro, voice pf_dora) first, then the conversion
    assert ov[0][1:] == ["-c", mock.ANY, "/kokoro", "tom de teste", "pf_dora", "1.0", "pt-br", mock.ANY]
    assert ov[1][2:3] == [str(_executa("openvoice")["path"].parent.parent / "ckpt")] and ov[1][-2] == str(_executa("openvoice")["path"].parent / "ref.wav")


def test_log_lines_are_frozen():
    assert _executa("file")["logs1"][0].startswith("vo1 rendered 0.") and _executa("file")["logs1"][0].endswith("s / 0.4s  tom de teste")
    assert _executa("file")["logs1"][1] == "voice: file -> " + os.path.relpath(_executa("file")["path"].parent / "timing.lock.json")
    assert _executa("file_tight")["logs1"][0].startswith("vo1 rendered+tight ")


@pytest.mark.parametrize("caso", list(CASES))
def test_lock_and_audio_bytes_are_frozen_on_one_ffmpeg_build(caso):
    if not _ffmpeg_version().startswith(FROZEN_ON):
        pytest.skip(f"the byte hashes were frozen on {FROZEN_ON}")
    r = _executa(caso)
    assert (_sha(r["text1"]), _sha(r["final1"]), _sha(r["text2"])) == LOCK_SHA[caso]


# ================================================================ the errors, provider by provider
def _erro(dest: Path, provider: str, providers: dict | None = None, **kw):
    with pytest.raises(SystemExit) as ei:
        voice.run(ct.load(_contract(dest, provider, providers, **kw)), log=lambda *_: None)
    return ei.value.code


STUB = "provider={}: stub in simplicio-video v0.2 - generate the takes elsewhere, drop them in the file dir and use --provider file"


@pytest.mark.parametrize("prov", ["elevenlabs", "xai"])
def test_stub_providers_say_so_before_touching_anything(tmp_path, prov):
    path = _contract(tmp_path / "c", "file")
    with pytest.raises(SystemExit) as ei:
        voice.run(ct.load(path), provider=prov, log=lambda *_: None)
    assert ei.value.code == STUB.format(prov)
    assert not (path.parent / "assets").exists() and not (path.parent / "timing.lock.json").exists()


def test_an_unknown_provider_is_refused(tmp_path):
    with pytest.raises(SystemExit) as ei:
        voice.run(ct.load(_contract(tmp_path / "c", "file")), provider="nope", log=lambda *_: None)
    assert ei.value.code == "unknown provider nope"


def test_file_without_the_take_says_where_it_looked(tmp_path):
    assert _erro(tmp_path / "c", "file", file_dir="nada") == "provider=file: missing external take for vo1 (expected nada/line-01.wav)"


def test_local_without_its_python_says_how_to_set_it(tmp_path, monkeypatch):
    monkeypatch.setenv("SIMPLICIO_TTS_PY", "/nonexistent/py")
    assert _erro(tmp_path / "c", "local") == "provider=local: python with kokoro_onnx not found at /nonexistent/py (set SIMPLICIO_TTS_PY)"


def test_gemini_without_a_key_says_where_to_get_one(tmp_path, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert _erro(tmp_path / "c", "gemini") == (
        "provider=gemini: GEMINI_API_KEY not set. Create a key at https://aistudio.google.com/apikey (free tier "
        "works; Google AI Pro does NOT include API quota), export it, or generate the lines in Google AI "
        "Studio and use --provider file (assets/audio/vo/external/line-NN.wav).")


def test_gemini_http_error_carries_the_status_the_url_and_the_detail(tmp_path, monkeypatch):
    def bad(req, timeout=0):
        raise urllib.error.HTTPError(req.full_url, 400, "bad", {}, io.BytesIO(b'{"error": "bad voice"}'))
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.setattr(urllib.request, "urlopen", bad)
    assert _erro(tmp_path / "c", "gemini", {"gemini": GEMINI}) == (
        'provider=gemini: HTTP 400 from https://generativelanguage.googleapis.com/v1beta/interactions\n{"error": "bad voice"}')


def test_gemini_quota_error_adds_the_hint_after_the_retries(tmp_path, monkeypatch):
    def quota(req, timeout=0):
        raise urllib.error.HTTPError(req.full_url, 429, "quota", {"Retry-After": "0"}, io.BytesIO(b"{}"))
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.setattr(urllib.request, "urlopen", quota)
    assert _erro(tmp_path / "c", "gemini", {"gemini": GEMINI}) == (
        "provider=gemini: HTTP 429 from https://generativelanguage.googleapis.com/v1beta/interactions"
        " (free-tier rate limit/quota: wait, or enable billing on the AI Studio project)\n{}")


def test_gemini_answer_without_audio_lists_the_keys(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=0: _Resp(b'{"zeta": 1, "alfa": 2}'))
    assert _erro(tmp_path / "c", "gemini", {"gemini": GEMINI}) == "provider=gemini: no audio in response (keys: ['alfa', 'zeta'])"


def test_voxcpm_and_audio8_without_their_cli_say_how_to_get_it(tmp_path, monkeypatch):
    for var in ("VOXCPM_BIN", "AUDIO8_TTS_BIN"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(shutil, "which", lambda name, *a, **k: None)
    assert _erro(tmp_path / "a", "voxcpm", {"voxcpm": {}}) == (
        "provider=voxcpm: `voxcpm` CLI not found. pip install voxcpm (Python 3.10-3.12, PyTorch >= 2.5) or set VOXCPM_BIN.")
    assert _erro(tmp_path / "b", "audio8", {"audio8": {}}) == (
        "provider=audio8: `audio8-tts` CLI not found. Install the audio8_tts repo in its own venv and set AUDIO8_TTS_BIN.")


@pytest.mark.parametrize("prov", ["voxcpm", "audio8", "openvoice"])
def test_a_reference_audio_that_is_not_there_is_named(tmp_path, prov):
    assert _erro(tmp_path / "c", prov, {prov: {"reference_audio": "nada.wav"}}) == f"provider={prov}: reference_audio not found: nada.wav"


def test_openvoice_without_reference_and_without_its_environment(tmp_path, monkeypatch):
    assert _erro(tmp_path / "a", "openvoice", {"openvoice": {}}) == (
        "provider=openvoice: set voz.providers.openvoice.reference_audio (a clean 10-30 s clip of an authorized speaker)")
    monkeypatch.delenv("OPENVOICE_PY", raising=False)
    msg = _erro(tmp_path / "b", "openvoice", {"openvoice": {"reference_audio": "ref.wav"}})
    assert msg.startswith("provider=openvoice: set OPENVOICE_PY to a Python with OpenVoice installed (see https://")
    monkeypatch.setenv("OPENVOICE_PY", sys.executable)
    monkeypatch.setenv("OPENVOICE_CHECKPOINTS", str(tmp_path / "sem-ckpt"))
    msg = _erro(tmp_path / "c", "openvoice", {"openvoice": {"reference_audio": "ref.wav"}})
    assert msg == f"provider=openvoice: checkpoints_v2 not found at {tmp_path / 'sem-ckpt'} (set OPENVOICE_CHECKPOINTS)"


def test_voicestudio_errors_name_the_backend(tmp_path, monkeypatch):
    def down(req, timeout=0):
        raise urllib.error.URLError("refused")

    def boom(req, timeout=0):
        raise urllib.error.HTTPError(req.full_url, 500, "boom", {}, io.BytesIO(b"boom"))
    monkeypatch.delenv("VOICESTUDIO_URL", raising=False)
    monkeypatch.setattr(urllib.request, "urlopen", down)
    assert _erro(tmp_path / "a", "voicestudio", {"voicestudio": {}}) == (
        "provider=voicestudio: backend not reachable at http://localhost:3900 (refused). Start VoiceStudio or set VOICESTUDIO_URL.")
    monkeypatch.setattr(urllib.request, "urlopen", boom)
    assert _erro(tmp_path / "b", "voicestudio", {"voicestudio": {}}) == "provider=voicestudio: HTTP 500: boom"


def test_a_take_longer_than_its_slot_is_an_error_after_the_lock_is_written(tmp_path):
    path = _contract(tmp_path / "c", "file", file_dir="vo")
    (path.parent / "vo" / "line-01.wav").write_bytes(_take_with_air_leadin(tone_s=0.6))
    with pytest.raises(SystemExit) as ei:
        voice.run(ct.load(path), log=lambda *_: None)
    assert ei.value.code.startswith("lines longer than their slot (no time-stretch by design) - shorten text or widen max_s/scene:\n  vo1: ")
    assert ei.value.code.endswith("s > max_s 0.4s")
    lock = json.loads((path.parent / "timing.lock.json").read_text(encoding="utf8"))
    assert lock["lines"]["vo1"]["fits"] is False and lock["lines"]["vo1"]["slack_s"] < 0


# ================================================================ the registry (U21): one Provider per name, one ffmpeg chain
def test_provider_is_a_frozen_dataclass_with_the_six_fields():
    assert [f.name for f in dataclasses.fields(voice.Provider)] == ["nome", "descricao", "rede", "guarda_bruto", "settings", "gerar"]
    with pytest.raises(dataclasses.FrozenInstanceError):
        voice.REGISTRO["file"].rede = True  # type: ignore[misc]


def test_registry_has_the_nine_providers_in_the_order_of_the_table():
    assert list(voice.REGISTRO) == list(DESCRICOES)
    for nome, p in voice.REGISTRO.items():
        assert p.nome == nome and p.descricao == DESCRICOES[nome] and (p.rede, p.guarda_bruto) == REDE_E_BRUTO[nome], nome
        assert callable(p.settings) and callable(p.gerar), nome


def test_the_table_the_catalog_reads_is_the_one_of_the_registry():
    assert [f.nome for f in voz_catalogo.FICHAS] == list(voice.REGISTRO) == list(voice._COMPORTAMENTO)
    assert voz_catalogo.DESCRICOES == voice.PROVIDERS
    assert [(f.rede, f.guarda_bruto) for f in voz_catalogo.FICHAS] == [(p.rede, p.guarda_bruto) for p in voice.REGISTRO.values()]


def test_voz_catalogo_is_only_data():
    tree = ast.parse(Path(voz_catalogo.__file__).read_text(encoding="utf8"))
    imports = [n for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))]
    assert sorted(getattr(n, "module", None) or n.names[0].name for n in imports) == ["__future__", "dataclasses"]
    assert [n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))] == []


def test_the_catalog_does_not_load_the_voice_engine():
    code = ("import sys, simplicio_video.catalog as c; c.voices(); "
            "print(sorted(m for m in sys.modules if m in ('simplicio_video.voice', 'simplicio_video.voice_clone', 'simplicio_video.childio')))")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True).stdout
    assert out.strip() == "[]"


def test_settings_of_the_registry_read_the_voz_block_and_agree_with_settings_for(tmp_path):
    for caso in ("local", "gemini_generate_content", "openvoice", "voicestudio"):
        spec = dict(CASES[caso])
        spec.pop("take", None)
        c = ct.load(_contract(tmp_path / caso, **spec))
        nome = spec["provider"]
        assert voice.REGISTRO[nome].settings(c.data["voz"]) == voice.settings_for(c, nome)


def test_gerar_looks_the_function_up_when_it_is_called(monkeypatch, tmp_path):
    """Tests (and the bench script) replace `voice._gemini`, `voice._local` and `voice_clone.*`: the registry must still reach them."""
    c = ct.load(_contract(tmp_path / "c", "file"))
    dst, seen = tmp_path / "o.wav", []
    monkeypatch.setattr(voice, "_gemini", lambda S, text, d: seen.append(("gemini", S, text, d)) or {"x": 1})
    monkeypatch.setattr(voice, "_local", lambda S, text, d: seen.append(("local", S, text, d)))
    monkeypatch.setattr(voice_clone, "voxcpm", lambda S, text, d, ref: seen.append(("voxcpm", S, text, d, ref)))
    monkeypatch.setattr(voice_clone, "audio8", lambda S, text, d, ref: seen.append(("audio8", S, text, d, ref)))
    monkeypatch.setattr(voice_clone, "voicestudio", lambda S, text, d: seen.append(("voicestudio", S, text, d)))
    monkeypatch.setattr(voice_clone, "openvoice", lambda S, text, d, ref, base: (base("t2", dst), seen.append(("openvoice", S, text, d, ref)))[1])
    S, ref = {"base": {"b": 1}}, tmp_path / "ref.wav"
    assert voice.REGISTRO["gemini"].gerar(c, S, "t", dst, None) == {"x": 1}
    for nome in ("local", "voxcpm", "audio8", "voicestudio", "openvoice"):
        assert voice.REGISTRO[nome].gerar(c, S, "t", dst, ref) is None, nome
    assert seen == [("gemini", S, "t", dst), ("local", S, "t", dst), ("voxcpm", S, "t", dst, ref), ("audio8", S, "t", dst, ref),
                    ("voicestudio", S, "t", dst), ("local", {"b": 1}, "t2", dst), ("openvoice", S, "t", dst, ref)]


def test_file_and_the_stubs_never_generate(tmp_path):
    c = ct.load(_contract(tmp_path / "c", "file"))
    for nome in ("elevenlabs", "xai"):
        with pytest.raises(SystemExit) as ei:
            voice.REGISTRO[nome].gerar(c, {}, "t", tmp_path / "o.wav", None)
        assert ei.value.code == STUB.format(nome)
    with pytest.raises(SystemExit) as ei:
        voice.REGISTRO["file"].gerar(c, {"dir": "vo"}, "t", tmp_path / "o.wav", None)
    assert ei.value.code == "provider=file: nothing to generate, the takes are the files in vo"
    assert not (tmp_path / "o.wav").exists()


def test_the_ffmpeg_chain_lives_in_one_function():
    src = inspect.getsource(voice)
    assert src.count('"-bitexact"') == 1 and src.count("aresample=48000") == 1 and src.count('"-ar", "48000"') == 1
    assert src.count("_cadeia(") == 3 and src.count("_normaliza(") == 4  # the definitions + the normal pass and the tight retry


@pytest.mark.parametrize("trim", [TRIM, TRIM_TIGHT])
def test_cadeia_is_trim_then_chain_then_pcm_bitexact(tmp_path, trim):
    raw, dst, cut, want = tmp_path / "raw.wav", tmp_path / "dst.wav", tmp_path / "cut.wav", tmp_path / "want.wav"
    raw.write_bytes(_take_with_air_leadin())
    voice._cadeia(raw, dst, "highpass=f=85", trim)
    for args in (["-i", str(raw), "-af", trim, str(cut)],
                 ["-i", str(cut), "-af", "highpass=f=85,aresample=48000", "-ac", "1", "-c:a", "pcm_s16le", "-bitexact", str(want)]):
        subprocess.run(["ffmpeg", "-y", "-v", "error", *args], check=True, stdin=subprocess.DEVNULL)
    assert dst.read_bytes() == want.read_bytes()
