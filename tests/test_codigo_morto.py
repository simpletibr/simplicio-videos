"""U14: code with no reader in `src/`, and pointers to files and commands that do not exist.

What was found (areas A and C of the untangle review, re-checked with a grep over src, tests, scripts, docs, skills, plugin.json,
modules and pyproject before anything was deleted; no dispatch by name, `getattr` or MCP tool reaches any of them):

* `social.DEFAULT_PROVIDER` and `swap_providers.base.PRICES_READ_ON`: module constants nobody reads; `social._context(plan, provider,
  clip_id, step)`: its `provider` is never used (both callers pass the same value they already used for something else);
* `simplicio_video/mock_gemini.py`: a local mock of the Gemini TTS API with no importer and no test, shipped in the wheel. It is a tool
  for the tests, so it lives in `tests/tools/mock_gemini.py` (the wheel loses that one file: declared in the PR);
* `voice.py` pointed at `scripts/mock_gemini_tts.py` (never existed) and at the "legacy scripts/voice.py" without saying it is gone;
  `engine/build.mjs` told the user to run `npm run voice` and cited `scripts/voice.py`: the compiled project has no package.json and
  the command that renders the voice is `simplicio-video voice <contrato>`;
* `scripts/smoke_trilhas.py::_checar_mcp` had a SKIP for a track with no MCP call, which cannot happen since `MCP_LEITURA` is made
  from `tools.TOOLS` (and `tests/packaging/test_registro_trilhas.py` says every track has an `mcp_read`).

CHARACTERIZATION (green before and after): the mock behaves as documented, from where it is. STRUCTURE (red before): each of the above.
What is NOT here, on purpose: `tools.COMMANDS`, `doctor_trilhas.CLONE` and `DEPS` are read only by tests, and `DEP_NOMES` and the
`t.name == "video_to_skill"` of `doctor_trilhas._upstream` are read by production code: the review did not confirm them dead.
"""
from __future__ import annotations

import ast
import base64
import importlib
import importlib.util
import inspect
import io
import json
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import wave
from pathlib import Path

import pytest

from simplicio_video import social, voice
from simplicio_video.swap_providers import base
from helpers import ROOT, SRC

MOCK = ROOT / "tests" / "tools" / "mock_gemini.py"


# ------------------------------------------------------------------------------------------------ the mock leaves the package

def test_the_gemini_mock_is_not_part_of_the_package():
    assert not (SRC / "mock_gemini.py").exists()
    assert importlib.util.find_spec("simplicio_video.mock_gemini") is None
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("simplicio_video.mock_gemini")


def test_nothing_in_the_package_or_the_scripts_names_the_old_module():
    for pasta in (SRC, ROOT / "scripts", ROOT / "tests"):
        for arquivo in pasta.rglob("*.py"):
            if arquivo == Path(__file__).resolve():
                continue
            texto = arquivo.read_text(encoding="utf-8", errors="replace")
            assert "simplicio_video.mock_gemini" not in texto, arquivo
            assert "from simplicio_video import mock_gemini" not in texto, arquivo


def _livre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _espera(porta: int, processo: subprocess.Popen) -> None:
    fim = time.monotonic() + 15
    while time.monotonic() < fim:
        assert processo.poll() is None, processo.stderr.read().decode() if processo.stderr else "the mock ended"
        try:
            socket.create_connection(("127.0.0.1", porta), timeout=0.5).close()
            return
        except OSError:
            time.sleep(0.05)
    raise AssertionError("the mock did not listen")


def _post(url: str, corpo: dict, chave: str | None = "mock") -> dict:
    cabecalhos = {"Content-Type": "application/json", **({"x-goog-api-key": chave} if chave else {})}
    pedido = urllib.request.Request(url, data=json.dumps(corpo).encode(), headers=cabecalhos, method="POST")
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(pedido, timeout=20) as r:
        return json.loads(r.read())


def _wav(dados: bytes) -> tuple[int, int, int, int]:
    with wave.open(io.BytesIO(dados)) as w:
        return w.getframerate(), w.getnchannels(), w.getsampwidth(), w.getnframes()


@pytest.mark.allow_hosts(["127.0.0.1", "::1", "localhost"])  # a throwaway server on loopback, never the network
def test_the_mock_serves_both_gemini_apis_from_tests_tools(tmp_path, monkeypatch):
    """`python tests/tools/mock_gemini.py --port N --overlong-first 1 --log F`: what its own docstring promises."""
    assert MOCK.is_file(), "the mock moved to tests/tools/mock_gemini.py"
    porta, log = _livre(), tmp_path / "mock.jsonl"
    p = subprocess.Popen([sys.executable, str(MOCK), "--port", str(porta), "--overlong-first", "1", "--log", str(log)],
                         stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, cwd=tmp_path)
    try:
        _espera(porta, p)
        monkeypatch.setenv("SIMPLICIO_GEMINI_BASE", f"http://127.0.0.1:{porta}/v1beta")
        texto = "uma frase de teste"  # 18 characters: 60 ms each = 1.08 s of tone
        interactions = {"api": "interactions", "model": "gemini-mock", "voice": "Kore", "estilo": "calmo"}
        generate = {"api": "generate_content", "model": "gemini-mock", "voice": "Puck", "estilo": ""}

        url, corpo = voice.gemini_request(interactions, texto)
        longa, mime = voice.gemini_audio(_post(url, corpo))  # the first request: a take 2.5x too long
        assert mime == "audio/wav"
        taxa, canais, largura, quadros = _wav(longa)
        assert (taxa, canais, largura) == (24000, 1, 2) and quadros == int(24000 * max(0.4, 0.06 * len(texto)) * 2.5)

        curta, _ = voice.gemini_audio(_post(*voice.gemini_request(interactions, texto)))
        assert _wav(curta)[3] == int(24000 * max(0.4, 0.06 * len(texto)))  # then the normal one

        url, corpo = voice.gemini_request(generate, texto)
        assert "generateContent" in url
        outra, _ = voice.gemini_audio(_post(url, corpo))
        assert _wav(outra)[:3] == (24000, 1, 2) and _wav(outra)[3] == _wav(curta)[3]

        with pytest.raises(urllib.error.HTTPError) as sem_chave:
            _post(*voice.gemini_request(interactions, texto), chave=None)
        assert sem_chave.value.code == 401

        linhas = [json.loads(ln) for ln in log.read_text(encoding="utf8").splitlines()]
        assert [(r["voice"], r["style"], r["text"], r["overlong"]) for r in linhas] == [
            ("Kore", "calmo", texto, True), ("Kore", "calmo", texto, False), ("Puck", "", texto, False)]
        assert linhas[0]["path"].endswith("/interactions") and linhas[2]["path"].endswith(":generateContent")
        assert linhas[2]["model"] == "gemini-mock"
    finally:
        p.terminate()
        p.wait(10)


def test_the_mock_tone_is_a_valid_wav_and_the_module_needs_nothing_of_the_package():
    """Loaded by path: it imports only the standard library, so it works from tests/tools with nothing of the package."""
    spec = importlib.util.spec_from_file_location("mock_gemini_de_teste", MOCK)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    dados = modulo.take("oi")
    assert dados[:4] == b"RIFF" and _wav(dados) == (24000, 1, 2, int(24000 * 0.4))  # the floor of 0.4 s for a short text
    assert base64.b64decode(base64.b64encode(dados)) == dados


# ------------------------------------------------------------------------------------------------ pointers to what is not there

def test_voice_py_points_to_the_mock_where_it_is_and_says_the_legacy_script_is_gone():
    texto = (SRC / "voice.py").read_text(encoding="utf-8")
    assert "scripts/mock_gemini_tts.py" not in texto  # never existed
    assert "tests/tools/mock_gemini.py" in texto and MOCK.is_file()
    cabeca = texto.split('"""')[1]
    # `scripts/voice.py` was the script of the per-video projects (clients/ left the repository): the docstring says so
    assert (ROOT / "scripts" / "voice.py").exists() or "scripts/voice.py" not in cabeca or "no longer in this repository" in cabeca


def test_build_mjs_cites_no_command_that_does_not_exist():
    texto = (SRC / "engine" / "build.mjs").read_text(encoding="utf-8")
    assert "npm run" not in texto, "the compiled project has no package.json: there is no `npm run` to cite"
    assert "scripts/voice.py" not in texto
    from simplicio_video import cli
    registrados = set(next(a for a in cli.build_parser()._actions if a.__class__.__name__ == "_SubParsersAction").choices)
    citados = set(re.findall(r"`simplicio-video ([a-z][a-z-]*)", texto))
    assert citados and citados <= registrados, sorted(citados - registrados)
    assert "voice" in citados
    assert texto.count("simplicio-video voice <contrato>") >= 3  # the three messages of a voice that was not rendered


# ------------------------------------------------------------------------------------------------ names with no reader

def test_social_has_no_default_provider_constant():
    assert not hasattr(social, "DEFAULT_PROVIDER")


def test_the_context_of_a_recipe_takes_no_provider_it_never_used():
    assert list(inspect.signature(social._context).parameters) == ["plan", "clip_id", "step"]


def test_swap_providers_base_has_no_prices_read_on_constant():
    assert not hasattr(base, "PRICES_READ_ON")
    assert base.FX["brl_per_usd"] > 0 and "2026-10-15" in base.FX["source"]  # the date that is read lives in the exchange rate


def test_the_smoke_has_no_skip_for_a_track_with_no_mcp_call():
    """`MCP_LEITURA` is made from `tools.TOOLS`, so `.get(nome)` is never None: the branch (and its SKIP) could not run."""
    arvore = ast.parse((ROOT / "scripts" / "smoke_trilhas.py").read_text(encoding="utf-8"))
    funcao = next(n for n in ast.walk(arvore) if isinstance(n, ast.FunctionDef) and n.name == "_checar_mcp")
    sem_chamada = [n for n in ast.walk(funcao) if isinstance(n, ast.Compare) and any(isinstance(op, ast.Is) for op in n.ops)
                   and isinstance(n.left, ast.Name) and n.left.id == "chamada"]
    assert not sem_chamada, "`_checar_mcp` still tests `chamada is None`"
    assert "sem chamada MCP de leitura no smoke" not in (ROOT / "scripts" / "smoke_trilhas.py").read_text(encoding="utf-8")
