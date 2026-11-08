"""U22d: the `voicestudio` voice provider reaches the app at the base of `voicestudio.base_url()`, the ONE reading of it.

Before: `voice_clone.voicestudio_url()` (voice_clone.py:64) read only VOICESTUDIO_URL and defaulted to http://localhost:3900, while
`voicestudio.base_url()` (voicestudio.py:104) also reads OMNIVOICE_URL, VOICESTUDIO_PORT and OMNIVOICE_PORT and defaults to
http://127.0.0.1:3900. So `voice --provider voicestudio` and `voicestudio tts` could talk to two different apps of the same machine.
The owner approved ("Ok U22") that the provider follows `voicestudio.base_url()`; the local name `voicestudio_url` stays (tests patch it)
and delegates. The golden block (d) of tests/golden/test_mcp_bordas.py holds the table of the four variables; this file holds the rest.

Three kinds of test:

* CHANGE (red before): the request of `voicestudio()` and the message of the unreachable app follow OMNIVOICE_URL and the ports and the
  default host is 127.0.0.1; an empty VOICESTUDIO_URL is "not set" (it was a request to the path alone, "/v1/audio/speech"); a bad
  port is `CloneVoiceError` (a SystemExit with the `provider=voicestudio:` prefix of every error of this module), never a traceback and
  never a request; `voicestudio_url` follows `voicestudio.base_url` when it is called, not when the module is imported;
* UNCHANGED (green before and after): an explicit VOICESTUDIO_URL, the text of the messages that already exist, the body and the headers
  of the request, the key (still VOICESTUDIO_API_KEY only: OMNIVOICE_API_KEY stays out of U22d), the local name patched by tests, the
  name `voice_clone.voicestudio` (the registry looks it up) and `voicestudio.py` free of imports of the package (no cycle);
* PRECEDENCE: which variable wins when several are set (it is the one of `base_url()`).
"""
from __future__ import annotations

import ast
import inspect
import io
import json
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from simplicio_video import voice_clone, voicestudio

S = {"model": "omnivoice", "voice": "me"}
VARIAVEIS_DA_BASE = ("VOICESTUDIO_URL", "OMNIVOICE_URL", "VOICESTUDIO_PORT", "OMNIVOICE_PORT")
FALHA = "provider=voicestudio: backend not reachable at {onde} (refused). Start VoiceStudio or set VOICESTUDIO_URL."
PORTA_RUIM = "provider=voicestudio: porta inválida em VOICESTUDIO_PORT/OMNIVOICE_PORT: {valor!r} (esperava 1-65535)"


@pytest.fixture(autouse=True)
def _sem_ambiente(monkeypatch):
    """The variables that decide the base, and the keys, belong to each test: nothing of the developer's shell leaks in."""
    for var in (*VARIAVEIS_DA_BASE, "VOICESTUDIO_API_KEY", "OMNIVOICE_API_KEY"):
        monkeypatch.delenv(var, raising=False)


class _Resposta:
    def __init__(self, dados: bytes = b"RIFFdata"):
        self.dados = dados

    def read(self) -> bytes:
        return self.dados

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _Rede:
    """`urllib.request.urlopen` replaced: each Request the provider sends is kept in `pedidos`; `falha`, when set, is raised instead of answering."""

    def __init__(self):
        self.pedidos: list = []
        self.falha: BaseException | None = None

    def urlopen(self, req, timeout=0):
        self.pedidos.append(req)
        if self.falha is not None:
            raise self.falha
        return _Resposta()


@pytest.fixture
def rede(monkeypatch):
    r = _Rede()
    monkeypatch.setattr(urllib.request, "urlopen", r.urlopen)
    return r


def com(monkeypatch, env: dict) -> None:
    for nome, valor in env.items():
        monkeypatch.setenv(nome, valor)


def falha_de(rede: _Rede, tmp_path, erro: BaseException) -> str:
    """The message `voicestudio()` dies with when the transport raises `erro`."""
    rede.falha = erro
    with pytest.raises(voice_clone.CloneVoiceError) as e:
        voice_clone.voicestudio(S, "hello", tmp_path / "o.wav")
    return e.value.code


# ============================================================================================ CHANGE: the request follows the base of the voicestudio module

@pytest.mark.parametrize("env,url", [
    ({}, "http://127.0.0.1:3900/v1/audio/speech"),  # was http://localhost:3900
    ({"VOICESTUDIO_URL": "http://studio.local:4000/"}, "http://studio.local:4000/v1/audio/speech"),  # as today
    ({"OMNIVOICE_URL": "http://omni.local:5000/"}, "http://omni.local:5000/v1/audio/speech"),  # was ignored: went to localhost:3900
    ({"VOICESTUDIO_PORT": "4001"}, "http://127.0.0.1:4001/v1/audio/speech"),  # was ignored
    ({"OMNIVOICE_PORT": "4002"}, "http://127.0.0.1:4002/v1/audio/speech"),  # was ignored
], ids=["padrao", "VOICESTUDIO_URL", "OMNIVOICE_URL", "VOICESTUDIO_PORT", "OMNIVOICE_PORT"])
def test_the_speech_request_goes_to_the_base_of_the_voicestudio_module(monkeypatch, tmp_path, rede, env, url):
    com(monkeypatch, env)
    dst = tmp_path / "sub" / "o.wav"
    voice_clone.voicestudio(S, "hello", dst)
    (req,) = rede.pedidos
    assert (req.get_method(), req.full_url) == ("POST", url)
    assert dst.read_bytes() == b"RIFFdata"


@pytest.mark.parametrize("env,onde", [
    ({}, "http://127.0.0.1:3900"),  # was http://localhost:3900
    ({"VOICESTUDIO_URL": "http://studio.local:4000/"}, "http://studio.local:4000"),  # as today
    ({"OMNIVOICE_URL": "http://omni.local:5000"}, "http://omni.local:5000"),  # was http://localhost:3900
    ({"OMNIVOICE_PORT": "4002"}, "http://127.0.0.1:4002"),  # was http://localhost:3900
], ids=["padrao", "VOICESTUDIO_URL", "OMNIVOICE_URL", "OMNIVOICE_PORT"])
def test_the_unreachable_message_names_the_base_in_use_with_the_same_text(monkeypatch, tmp_path, rede, env, onde):
    com(monkeypatch, env)
    assert falha_de(rede, tmp_path, urllib.error.URLError("refused")) == FALHA.format(onde=onde)


# ============================================================================================ PRECEDENCE: the one of voicestudio.base_url()

@pytest.mark.parametrize("env,esperado", [
    ({"VOICESTUDIO_URL": "http://a.local:1", "OMNIVOICE_URL": "http://b.local:2"}, "http://a.local:1"),  # as today
    ({"VOICESTUDIO_URL": "http://a.local:1", "VOICESTUDIO_PORT": "4001"}, "http://a.local:1"),  # a base beats a port
    ({"VOICESTUDIO_URL": "http://a.local:1", "VOICESTUDIO_PORT": "abc"}, "http://a.local:1"),  # ...and the port is not even read
    ({"OMNIVOICE_URL": "http://b.local:2", "VOICESTUDIO_PORT": "4001"}, "http://b.local:2"),
    ({"OMNIVOICE_URL": "http://b.local:2", "OMNIVOICE_PORT": "4002"}, "http://b.local:2"),
    ({"VOICESTUDIO_PORT": "4001", "OMNIVOICE_PORT": "4002"}, "http://127.0.0.1:4001"),  # VOICESTUDIO_PORT before OMNIVOICE_PORT
    ({"VOICESTUDIO_PORT": "4001", "OMNIVOICE_PORT": "abc"}, "http://127.0.0.1:4001"),  # ...and the second is not even read
    ({"VOICESTUDIO_URL": "http://a.local:1///"}, "http://a.local:1"),  # every trailing slash goes, as today
    ({"OMNIVOICE_URL": "http://b.local:2///"}, "http://b.local:2"),
    ({"VOICESTUDIO_PORT": " 4001 "}, "http://127.0.0.1:4001"),  # the port is trimmed
], ids=["as-duas-URLs", "URL-e-porta", "URL-e-porta-ruim", "OMNIVOICE_URL-e-VOICESTUDIO_PORT", "OMNIVOICE_URL-e-OMNIVOICE_PORT",
        "as-duas-portas", "porta-e-porta-ruim", "barras-VOICESTUDIO_URL", "barras-OMNIVOICE_URL", "porta-com-espacos"])
def test_which_variable_wins_when_several_are_set(monkeypatch, env, esperado):
    com(monkeypatch, env)
    assert voice_clone.voicestudio_url() == esperado


@pytest.mark.parametrize("env,esperado", [
    ({"VOICESTUDIO_URL": ""}, "http://127.0.0.1:3900"),  # was "": the request went to the path alone and died in urllib
    ({"VOICESTUDIO_URL": "", "OMNIVOICE_URL": "http://b.local:2"}, "http://b.local:2"),
    ({"VOICESTUDIO_PORT": "", "OMNIVOICE_PORT": "4002"}, "http://127.0.0.1:4002"),
], ids=["URL-vazia", "URL-vazia-e-OMNIVOICE_URL", "porta-vazia-e-OMNIVOICE_PORT"])
def test_an_empty_variable_is_a_variable_that_is_not_set(monkeypatch, env, esperado):
    com(monkeypatch, env)
    assert voice_clone.voicestudio_url() == esperado


# ============================================================================================ CHANGE: a bad port is this module's error

@pytest.mark.parametrize("var,valor", [
    ("VOICESTUDIO_PORT", "abc"), ("OMNIVOICE_PORT", "abc"), ("VOICESTUDIO_PORT", "0"), ("VOICESTUDIO_PORT", "65536"),
    ("OMNIVOICE_PORT", "-1"), ("VOICESTUDIO_PORT", "39 00"),
], ids=["VOICESTUDIO_PORT-abc", "OMNIVOICE_PORT-abc", "zero", "65536", "negativa", "espaco-no-meio"])
def test_a_bad_port_is_a_clone_voice_error_with_the_text_of_the_voicestudio_module(monkeypatch, var, valor):
    com(monkeypatch, {var: valor})
    with pytest.raises(voice_clone.CloneVoiceError) as e:
        voice_clone.voicestudio_url()
    assert isinstance(e.value, SystemExit)  # the CLI, `--json` and the jobs catch SystemExit: a VoiceStudioError would be a traceback
    assert e.value.code == PORTA_RUIM.format(valor=valor)
    with pytest.raises(voicestudio.VoiceStudioError, match="porta inválida") as origem:  # the message is the one `voicestudio` always had
        voicestudio.base_url()
    assert PORTA_RUIM.format(valor=valor) == "provider=voicestudio: " + str(origem.value)


def test_a_bad_port_stops_before_any_request(monkeypatch, tmp_path, rede):
    com(monkeypatch, {"VOICESTUDIO_PORT": "abc"})
    dst = tmp_path / "sub" / "o.wav"
    with pytest.raises(SystemExit) as e:
        voice_clone.voicestudio(S, "hello", dst)
    assert e.value.code == PORTA_RUIM.format(valor="abc")
    assert rede.pedidos == [] and not dst.parent.exists()


# ============================================================================================ CHANGE: the delegation is by name, when it is called

def test_voicestudio_url_asks_the_voicestudio_module_each_time_it_is_called(monkeypatch):
    respostas = iter(["http://um.example:1", "http://dois.example:2"])
    monkeypatch.setattr(voicestudio, "base_url", lambda: next(respostas))  # a copy of the logic, or a name bound at import, would not follow
    assert (voice_clone.voicestudio_url(), voice_clone.voicestudio_url()) == ("http://um.example:1", "http://dois.example:2")


def test_a_voicestudio_error_of_base_url_becomes_the_error_of_the_provider(monkeypatch):
    def quebra():
        raise voicestudio.VoiceStudioError("sem base")
    monkeypatch.setattr(voicestudio, "base_url", quebra)
    with pytest.raises(voice_clone.CloneVoiceError) as e:
        voice_clone.voicestudio_url()
    assert e.value.code == "provider=voicestudio: sem base"


# ============================================================================================ UNCHANGED (green before and after)

def test_the_local_name_stays_patchable_and_the_provider_calls_it(monkeypatch, tmp_path, rede):
    monkeypatch.setattr(voice_clone, "voicestudio_url", lambda: "http://patched.example:9")
    voice_clone.voicestudio(S, "hello", tmp_path / "o.wav")
    (req,) = rede.pedidos
    assert req.full_url == "http://patched.example:9/v1/audio/speech"
    assert falha_de(rede, tmp_path, urllib.error.URLError("refused")) == FALHA.format(onde="http://patched.example:9")


def test_the_body_and_the_headers_of_the_request_do_not_change(monkeypatch, tmp_path, rede):
    com(monkeypatch, {"VOICESTUDIO_URL": "http://studio.local:4000"})
    voice_clone.voicestudio(S, "olá", tmp_path / "o.wav")
    (req,) = rede.pedidos
    assert json.loads(req.data) == {"model": "omnivoice", "voice": "me", "input": "olá", "response_format": "wav"}
    assert req.get_header("Content-type") == "application/json" and req.get_header("Authorization") is None


def test_the_key_is_still_VOICESTUDIO_API_KEY_only_and_the_alias_stays_out_of_u22d(monkeypatch, tmp_path, rede):
    # voicestudio.py:249 reads VOICESTUDIO_API_KEY and OMNIVOICE_API_KEY; the provider (voice_clone.py:72) reads the first only. Not in the ficha.
    com(monkeypatch, {"OMNIVOICE_API_KEY": "so-o-alias"})
    voice_clone.voicestudio(S, "hello", tmp_path / "o.wav")
    com(monkeypatch, {"VOICESTUDIO_API_KEY": "a-chave"})
    voice_clone.voicestudio(S, "hello", tmp_path / "o.wav")
    sem_chave, com_chave = rede.pedidos
    assert sem_chave.get_header("Authorization") is None and com_chave.get_header("Authorization") == "Bearer a-chave"


def test_an_http_error_keeps_its_text(monkeypatch, tmp_path, rede):
    com(monkeypatch, {"OMNIVOICE_URL": "http://omni.local:5000"})
    erro = urllib.error.HTTPError("http://omni.local:5000/v1/audio/speech", 500, "boom", {}, io.BytesIO(b"boom"))
    assert falha_de(rede, tmp_path, erro) == "provider=voicestudio: HTTP 500: boom"


def test_the_provider_function_keeps_its_name_and_voicestudio_never_imports_the_package():
    # the registry (voice._gerar_voicestudio) looks `voice_clone.voicestudio` up by name when it is CALLED: the import of the module under
    # that same name would shadow it (or be shadowed by it)
    assert inspect.isfunction(voice_clone.voicestudio) and list(inspect.signature(voice_clone.voicestudio).parameters) == ["S", "text", "dst"]
    assert inspect.isfunction(voice_clone.voicestudio_url) and list(inspect.signature(voice_clone.voicestudio_url).parameters) == []
    # voice_clone may import voicestudio (stdlib only); the other way round would be a cycle
    tree = ast.parse(Path(voicestudio.__file__).read_text(encoding="utf8"))
    do_pacote = [n.lineno for n in ast.walk(tree)
                 if (isinstance(n, ast.ImportFrom) and (n.level > 0 or (n.module or "").split(".")[0] == "simplicio_video"))
                 or (isinstance(n, ast.Import) and any(a.name.split(".")[0] == "simplicio_video" for a in n.names))]
    assert do_pacote == []
