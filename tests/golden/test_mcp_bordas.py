"""G0 (golden, caracterização): o que o MCP (e o terminal) devolve nas bordas que a onda MUDA CONTRATO (U22) altera.

Cada bloco é uma letra de U22 e escreve, como valor de HOJE, o que um chamador vê: a mensagem de recusa de cada módulo (a), o que fica no
texto devolvido ao agente (a), o que cada erro e cada arquivo de job deixa passar de uma chave (b), o que `voice` aceita como base do
Gemini (c), a URL do VoiceStudio (d), as opções `--provider` (e) e o mecanismo de limite de recursos do filho (f). Cada divergência é um
assert do valor atual com o comentário "U22 decide"; U22 só pode mudar linhas daqui, e o diff é o que o dono aprova.

Privados exercitados por import direto (caracterização; são as funções que os wrappers MCP/CLI chamam):
  (a) matchcut._confere_saida, instagram._checa_saida, montage._output_refusal, video_to_skill._new_dir, voicestudio._guard_out;
      matchcut.resposta_mcp, instagram.resposta_mcp. (b) busca.BuscaError, openverse.OpenverseError, swap_providers.base.SwapError,
      jobs.write_json_atomic (-> jobs._scrub). (c) voice.gemini_base, swap_providers.gemini.GeminiAdapter._base.
  (d) voice_clone.voicestudio_url, voicestudio.base_url. (e) cli.build_parser, voice.PROVIDERS. (f) instagram._executa/run_tool,
  matchcut._executa/_WRAPPER/_limite_de_memoria."""
from __future__ import annotations

import argparse
import contextlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from simplicio_video import busca, cli, instagram, jobs, matchcut, montage, openverse, video_to_skill, voice, voice_clone, voicestudio
from simplicio_video.swap_providers import base as swap_base
from simplicio_video.swap_providers import gemini as swap_gemini

LINUX = pytest.mark.skipif(sys.platform != "linux", reason="congelado no Linux (CASE_INSENSITIVE falso, /tmp fora de /var, /proc)")


def real(p) -> Path:
    return Path(os.path.realpath(p))


def corpo(n: int, alfabeto: str = "Xy1Zq9") -> str:
    return (alfabeto * n)[:n]


@pytest.fixture
def mundo(monkeypatch):
    """Pastas num diretório CURTO de /tmp: as mensagens de recusa cortam o caminho em 60 caracteres (`_ascii`), e o tmp_path do pytest passa disso."""
    base = real(tempfile.mkdtemp(prefix="g0-", dir="/tmp"))
    nomes = ("home", "work", "tools", "data")
    w = SimpleNamespace(**{n: base / n for n in nomes})
    for n in nomes:
        getattr(w, n).mkdir()
    monkeypatch.setenv("HOME", str(w.home))
    monkeypatch.setenv("SIMPLICIO_TOOLS_DIR", str(w.tools))
    monkeypatch.setenv("SIMPLICIO_VIDEO_DATA", str(w.data))
    for var in ("USERPROFILE", "SYSTEMROOT", "PROGRAMFILES", "PROGRAMFILES(X86)", "PROGRAMDATA", "APPDATA", "INSTAGRAM_DIR",
                "SIMPLICIO_INSTAGRAM_DIR", "MATCHCUT_DIR", "SIMPLICIO_MATCHCUT_DIR", "MATCHCUT_DATA_DIR", "VIDEO_TO_SKILL_DIR",
                "SIMPLICIO_VIDEO_TO_SKILL_DIR", "OPENMONTAGE_DIR", "SIMPLICIO_OPENMONTAGE_DIR", "OPENMONTAGE_DATA_DIR"):
        monkeypatch.delenv(var, raising=False)
    yield w
    shutil.rmtree(base, ignore_errors=True)


# ============================================================================================ (a) a recusa de gravação vista por quem chama

def recusa(modulo: str, mundo, caminho: Path):
    """("ok", caminho que o módulo devolve) ou ("recusa", mensagem), com a pasta de teste trocada por {home}/{work}."""
    def norma(texto) -> str:
        return str(texto).replace(str(mundo.home), "{home}").replace(str(mundo.work), "{work}")

    try:
        if modulo == "matchcut":
            r = matchcut._confere_saida(str(caminho), "mcp", False)
        elif modulo == "instagram":
            r = instagram._checa_saida(str(caminho), False)
        elif modulo == "montage":
            motivo = montage._output_refusal("output_path", str(caminho))
            if motivo:
                return "recusa", norma(motivo)
            r = caminho
        elif modulo == "video_to_skill":
            r = video_to_skill._new_dir(str(caminho), "mcp", "--out")
        else:
            r = voicestudio._guard_out(str(caminho))
    except (matchcut.MatchcutError, instagram.InstagramError, video_to_skill.VideoToSkillError, voicestudio.VoiceStudioError) as e:
        return "recusa", norma(e)
    return "ok", norma(r)


def pasta(w, modelo: str) -> Path:
    p = Path(modelo.format(home=w.home, work=w.work))
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


INICIO = "em pasta de início automático (LaunchAgents, LaunchDaemons, Startup)"
OCULTA = "em pasta oculta do home (.ssh, .config, .claude...)"
MODULOS_QUE_RECUSAM = ("matchcut", "instagram", "montage", "video_to_skill")


def mensagens(caminho: str, motivo: str) -> dict:
    """A mensagem de recusa de cada módulo para `caminho` (modelo com {home}/{work}); a do montage tem o formato próprio dele."""
    return {"matchcut": ("recusa", f"saída '{caminho}': o motor não grava {motivo}"),
            "instagram": ("recusa", f"--out '{caminho}': o motor não grava {motivo}"),
            "montage": ("recusa", f"a saída output_path cai {motivo} ({caminho}); pelo MCP o motor não grava aí"),
            "video_to_skill": ("recusa", f"--out '{caminho}': o motor não grava {motivo}")}


@LINUX
@pytest.mark.parametrize("caminho,esperado", [
    ("{work}/ok.txt", {m: ("ok", "{work}/ok.txt") for m in (*MODULOS_QUE_RECUSAM, "voicestudio")}),
    ("{home}/.ssh/x.txt", {**mensagens("{home}/.ssh/x.txt", OCULTA), "voicestudio": ("recusa", "--out: o MCP não grava em pasta oculta do home ({home}/.ssh)")}),
    ("/etc/x.txt", {**mensagens("/etc/x.txt", "em pasta do sistema"), "voicestudio": ("recusa", "--out: o MCP não grava em pasta do sistema (/etc)")}),
    # U22 decide: o voicestudio deixa gravar nas pastas de início automático e dentro de .git; os outros 4 recusam
    # U22a decidiu: o voicestudio recusa as duas, com as palavras que as outras quatro já tinham (as da regra única)
    ("{home}/Library/LaunchAgents/x.plist", {**mensagens("{home}/Library/LaunchAgents/x.plist", INICIO),
                                              "voicestudio": ("recusa", f"--out: o MCP não grava {INICIO}")}),
    ("{work}/.git/hooks/x.txt", {**mensagens("{work}/.git/hooks/x.txt", "dentro de uma pasta .git"),
                                  "voicestudio": ("recusa", "--out: o MCP não grava dentro de uma pasta .git")}),
], ids=["livre", "home-oculto", "sistema", "inicio-automatico", "git"])
def test_the_refusal_each_module_gives_for_an_output_path(mundo, caminho, esperado):
    p = pasta(mundo, caminho)
    assert {m: recusa(m, mundo, p) for m in esperado} == esperado


DADOS = "dentro da pasta de dados do motor (jobs, tools, openmontage-data)"
FERRAMENTAS = "dentro da pasta de ferramentas do motor"
SITE_PACKAGES = "dentro de site-packages (pacotes de um venv)"
VENV = "dentro de um venv (pyvenv.cfg)"


@LINUX
@pytest.mark.parametrize("modelo,motivo,excecoes", [
    # (caminho, o motivo dito; `excecoes` diz o de um módulo que usa outras palavras para o mesmo lugar)
    ("{data}/x.txt", DADOS, {}),  # a raiz de dados inteira: matchcut, instagram, video_to_skill e voicestudio não a recusavam
    ("{tools}/x.txt", FERRAMENTAS, {"montage": DADOS}),  # o voicestudio não recusava; o montage conta a pasta de ferramentas como "dados"
    ("{work}/lib/python3/site-packages/x.txt", SITE_PACKAGES, {}),  # só o montage recusava
    ("{work}/meuvenv/x.txt", VENV, {}),  # só o montage recusava (o teste cria o pyvenv.cfg)
], ids=["raiz-de-dados", "ferramentas", "site-packages", "venv"])
def test_the_places_a_module_did_not_refuse_before_are_refused_in_the_words_some_module_already_had(mundo, modelo, motivo, excecoes):
    """U22a, linhas novas (a tabela do PR): a regra única acrescenta recusas a cada trilha, e cada uma tem um texto que alguma trilha já dizia."""
    (mundo.work / "meuvenv").mkdir()
    (mundo.work / "meuvenv" / "pyvenv.cfg").write_text("home = /usr/bin\n")
    caminho = modelo.replace("{data}", str(mundo.data)).replace("{tools}", str(mundo.tools))  # as pastas de dados e de ferramentas não são trocadas na mensagem
    p = pasta(mundo, caminho)
    esperado = {m: mensagens(caminho, excecoes.get(m, motivo))[m] for m in MODULOS_QUE_RECUSAM}
    esperado["voicestudio"] = ("recusa", f"--out: o MCP não grava {excecoes.get('voicestudio', motivo)}")
    assert {m: recusa(m, mundo, p) for m in esperado} == esperado


@LINUX
def test_the_startup_folder_found_by_appdata_is_refused_by_every_module_in_the_words_matchcut_and_instagram_had(mundo, monkeypatch):
    """O mesmo, para o Startup achado por $APPDATA (só matchcut e instagram o recusavam). O caminho passa dos 60 caracteres que as mensagens
    mostram (`_ascii`), então aqui confere-se o começo e o fim de cada mensagem, que não dependem do tamanho da pasta de teste."""
    monkeypatch.setenv("APPDATA", str(mundo.work / "appdata"))
    p = pasta(mundo, "{work}/appdata/Microsoft/Windows/Start Menu/Programs/Startup/x.bat")
    r = {m: recusa(m, mundo, p) for m in (*MODULOS_QUE_RECUSAM, "voicestudio")}
    assert all(status == "recusa" for status, _ in r.values()), r
    assert r["matchcut"][1].startswith("saída '{work}/appdata/Microsoft/") and r["matchcut"][1].endswith(f": o motor não grava {INICIO}")
    assert r["instagram"][1].startswith("--out '{work}/appdata/Microsoft/") and r["instagram"][1].endswith(f": o motor não grava {INICIO}")
    assert r["video_to_skill"][1].startswith("--out '{work}/appdata/Microsoft/") and r["video_to_skill"][1].endswith(f": o motor não grava {INICIO}")
    assert r["montage"][1] == (f"a saída output_path cai {INICIO} ({{work}}/appdata/Microsoft/Windows/Start Menu/Programs/Startup/x.bat); "
                               "pelo MCP o motor não grava aí")
    assert r["voicestudio"][1] == f"--out: o MCP não grava {INICIO}"


@LINUX
def test_the_voicestudio_read_guard_keeps_the_narrow_rule_it_always_had(mundo, monkeypatch):
    """U22a só muda o `--out` (a gravação): o que o MCP LÊ (`_guard_input`: transcribe, clone, dub create) segue recusando só pasta do sistema
    (as 16 raízes) e pasta oculta do home, com o mesmo texto. Ler de .git, da pasta de dados, de ferramentas, de início automático, de
    site-packages ou de um venv continua aceito: nenhuma das outras quatro trilhas tem regra de lugar para ENTRADA, e o diretório temporário do
    macOS (/private/var/folders) cai em /var, que a gravação passa a recusar."""
    monkeypatch.setenv("PROGRAMDATA", str(mundo.work / "pd"))  # uma das 4 raízes do Windows, apontada para uma pasta daqui
    (mundo.work / "meuvenv").mkdir()
    (mundo.work / "meuvenv" / "pyvenv.cfg").write_text("home = /usr/bin\n")

    def le(caminho: str):
        p = pasta(mundo, caminho)
        p.write_bytes(b"RIFF")
        try:
            return "ok", voicestudio._guard_input(str(p), voicestudio.AUDIO_EXTS, "AUDIO")
        except voicestudio.VoiceStudioError as e:
            return "recusa", str(e)

    for caminho in (f"{mundo.work}/.git/x.wav", f"{mundo.data}/x.wav", f"{mundo.tools}/x.wav", f"{mundo.home}/Library/LaunchAgents/x.wav",
                    f"{mundo.work}/lib/python3/site-packages/x.wav", f"{mundo.work}/meuvenv/x.wav"):
        assert le(caminho) == ("ok", caminho), caminho
    assert le(f"{mundo.home}/.ssh/x.wav") == ("recusa", f"AUDIO: o MCP não lê de pasta oculta do home ({mundo.home}/.ssh)")
    assert le(f"{mundo.work}/pd/x.wav") == ("recusa", f"AUDIO: o MCP não lê de pasta do sistema ({mundo.work}/pd)")


RES_MATCHCUT = {"resultado": True, "script": "s", "codigo_saida": 0, "avisos": []}
RES_INSTAGRAM = {"resultado": True, "ferramenta": "f", "codigo_saida": 0, "avisos": []}
TEXTO_COM_SELETORES = "a️b\U000e0100c​d\x1b[31m"


def test_the_text_an_agent_gets_keeps_variation_selectors_in_matchcut_and_not_in_instagram():
    # U22 decide: o seletor de variação (U+FE0F, U+E0100) pode carregar dado escondido; só o instagram o tira da saída entregue ao agente
    # U22a decidiu: os três o tiram (o nome deste teste é histórico: o id não muda)
    m = matchcut.resposta_mcp({**RES_MATCHCUT, "stdout": TEXTO_COM_SELETORES, "stderr": "e️"})
    i = instagram.resposta_mcp({**RES_INSTAGRAM, "stdout": TEXTO_COM_SELETORES, "stderr": "e️"})
    assert m["saida"] == "abcd[31m" and m["erros"] == "e"  # era "a\ufe0fb\U000e0100cd[31m" e "e\ufe0f"
    assert i["saida"] == "abcd[31m" and i["erros"] == "e"
    assert video_to_skill.limpa_mcp(TEXTO_COM_SELETORES) == "abcd[31m"  # o video_to_skill (mcp_run) faz como o matchcut; era "a\ufe0fb\U000e0100cd[31m"


# ============================================================================================ (b) segredo em erro e em arquivo de job

@pytest.fixture
def sem_credencial(monkeypatch):
    for nome in list(os.environ):
        if any(p in nome for p in ("KEY", "TOKEN", "SECRET", "PASSWORD", "PASSWD", "PROXY", "proxy", "OPENVERSE")):
            monkeypatch.delenv(nome)
    monkeypatch.setattr(openverse, "_TOKEN", {})


@pytest.mark.parametrize("amostra,escondem", [
    ("AIzaSy" + corpo(25), (True, True, False)),
    ("AIza" + corpo(12, "Qz7"), (True, False, False)),
    ("ghp_" + corpo(8), (True, False, False)),
], ids=["AIzaSy+25", "AIza+12", "ghp_+8"])
def test_which_error_classes_hide_a_key_shaped_text_when_they_are_created(sem_credencial, amostra, escondem):
    # U22 decide: BuscaError e OpenverseError passam a mensagem pelo redator ao nascer, cada um com o seu; SwapError não passa por nenhum
    msg = f"falhou com {amostra} no meio"
    obtido = (str(busca.BuscaError(msg)), str(openverse.OpenverseError(msg)), str(swap_base.SwapError(msg)))
    assert obtido == tuple(msg.replace(amostra, "***") if esconde else msg for esconde in escondem)


def test_what_a_job_result_file_hides_of_the_environment_and_of_key_shapes(sem_credencial, monkeypatch, tmp_path):
    # U22 decide: jobs._scrub = swap.scrub (chaves dos provedores do swap e 2 formatos do Google) + ELEVENLABS_API_KEY + XAI_API_KEY, escritos à mão
    monkeypatch.setenv("GEMINI_API_KEY", "valor-gemini-1234")
    monkeypatch.setenv("ELEVENLABS_API_KEY", "valor-eleven-1234")
    monkeypatch.setenv("XAI_API_KEY", "valor-xai-123456")
    monkeypatch.setenv("OPENAI_API_KEY", "valor-openai-1234")
    google25, google12 = "AIzaSy" + corpo(25), "AIza" + corpo(12, "Qz7")
    obj = {"msg": f"{google25} {google12} valor-gemini-1234 valor-eleven-1234 valor-xai-123456 valor-openai-1234"}
    destino = tmp_path / "res.json"
    jobs.write_json_atomic(destino, obj)
    assert json.loads(destino.read_text(encoding="utf8")) == {"msg": f"*** {google12} *** *** *** valor-openai-1234"}


# ============================================================================================ (c) a base do Gemini em voice x provedor do swap

@pytest.mark.parametrize("valor,voice_devolve,swap_devolve", [
    ("https://generativelanguage.googleapis.com/v1beta", "https://generativelanguage.googleapis.com/v1beta", "https://generativelanguage.googleapis.com/v1beta"),
    ("https://proxy.example.com/v1beta/", "https://proxy.example.com/v1beta", "https://proxy.example.com/v1beta"),
    ("http://localhost:8080/v1beta", "http://localhost:8080/v1beta", "http://localhost:8080/v1beta"),
    ("http://127.0.0.1:8080", "http://127.0.0.1:8080", "http://127.0.0.1:8080"),
    ("http://[::1]:8080", "http://[::1]:8080", "http://[::1]:8080"),
    # U22 decide (feito em U22c): antes voice.gemini_base() não validava nada, e `voice` mandava a chave GEMINI_API_KEY em x-goog-api-key para essa
    # base; agora recusa o que o adaptador recusa (VoiceError). O id de cada caso fica o de antes (a base na 2ª coluna): nenhum id some do coletor.
    pytest.param("http://example.com/v1beta", "VoiceError", "SwapError", id="http://example.com/v1beta-http://example.com/v1beta-SwapError"),
    pytest.param("http://10.0.0.5:9000", "VoiceError", "SwapError", id="http://10.0.0.5:9000-http://10.0.0.5:9000-SwapError"),
    pytest.param("ftp://example.com/x", "VoiceError", "SwapError", id="ftp://example.com/x-ftp://example.com/x-SwapError"),
    pytest.param("file:///tmp/mock", "VoiceError", "SwapError", id="file:///tmp/mock-file:///tmp/mock-SwapError"),
])
def test_voice_gemini_base_accepts_what_the_swap_adapter_refuses(monkeypatch, valor, voice_devolve, swap_devolve):
    # o nome é de antes de U22c (voice aceitava o que o adaptador recusa); fica, para o id do teste não mudar
    monkeypatch.setenv("SIMPLICIO_GEMINI_BASE", valor)
    if voice_devolve == "VoiceError":
        with pytest.raises(voice.VoiceError, match=r"^provider=gemini: SIMPLICIO_GEMINI_BASE precisa ser https \(http só em localhost\): a chave não vai em texto claro$"):
            voice.gemini_base()
    else:
        assert voice.gemini_base() == voice_devolve
    adaptador = swap_gemini.GeminiAdapter()
    if swap_devolve == "SwapError":
        with pytest.raises(swap_base.SwapError, match=r"^SIMPLICIO_GEMINI_BASE precisa ser https \(http só em localhost\): a chave não vai em texto claro$"):
            adaptador._base()
    else:
        assert adaptador._base() == swap_devolve


def test_the_default_gemini_base_is_the_same_https_url_in_both(monkeypatch):
    monkeypatch.delenv("SIMPLICIO_GEMINI_BASE", raising=False)
    assert voice.gemini_base() == voice.GEMINI_BASE == swap_gemini.GeminiAdapter()._base() == "https://generativelanguage.googleapis.com/v1beta"


# ============================================================================================ (d) a URL do VoiceStudio em voice_clone x voicestudio

@pytest.mark.parametrize("ambiente,clone,estudio", [
    ({}, "http://localhost:3900", "http://127.0.0.1:3900"),
    ({"VOICESTUDIO_URL": "http://studio.local:4000/"}, "http://studio.local:4000", "http://studio.local:4000"),
    # U22 decide: voice_clone só lê VOICESTUDIO_URL; voicestudio.base_url() lê também OMNIVOICE_URL e as portas, e usa 127.0.0.1
    ({"OMNIVOICE_URL": "http://omni.local:5000/"}, "http://localhost:3900", "http://omni.local:5000"),
    ({"VOICESTUDIO_PORT": "4001"}, "http://localhost:3900", "http://127.0.0.1:4001"),
    ({"OMNIVOICE_PORT": "4002"}, "http://localhost:3900", "http://127.0.0.1:4002"),
    ({"VOICESTUDIO_URL": "http://a.local:1", "OMNIVOICE_URL": "http://b.local:2"}, "http://a.local:1", "http://a.local:1"),
], ids=["padrao", "VOICESTUDIO_URL", "OMNIVOICE_URL", "VOICESTUDIO_PORT", "OMNIVOICE_PORT", "as-duas-URLs"])
def test_the_voicestudio_url_of_voice_clone_and_of_the_voicestudio_module(monkeypatch, ambiente, clone, estudio):
    for var in ("VOICESTUDIO_URL", "OMNIVOICE_URL", "VOICESTUDIO_PORT", "OMNIVOICE_PORT"):
        monkeypatch.delenv(var, raising=False)
    for k, v in ambiente.items():
        monkeypatch.setenv(k, v)
    assert voice_clone.voicestudio_url() == clone
    assert voicestudio.base_url() == estudio


# ============================================================================================ (e) as opções --provider

def opcoes_provider(nome: str) -> list:
    sub = next(a for a in cli.build_parser()._actions if isinstance(a, argparse._SubParsersAction))
    return next(list(a.choices) for a in sub.choices[nome]._actions if "--provider" in a.option_strings)


def test_the_provider_choices_of_voice_and_run_and_the_registry_and_the_schema_disagree():
    esquema = json.loads((Path(cli.__file__).parent / "data" / "schema" / "contract.schema.json").read_text(encoding="utf8"))
    enum_do_contrato = esquema["properties"]["voz"]["properties"]["provider"]["enum"]
    registro = list(voice.PROVIDERS)
    assert registro == enum_do_contrato == ["file", "local", "gemini", "voxcpm", "openvoice", "voicestudio", "audio8", "elevenlabs", "xai"]
    # U22e decidiu (OK do dono): as duas aceitam o registro inteiro, na ordem dele (a de `list voices` e a do schema). Os stubs ficam nas duas: `voice.run` os recusa, com o motivo de sempre
    # (o G0 registrava aqui, antes da U22e: "U22 decide: nenhuma das duas CLIs aceita audio8, que o contrato e o registro aceitam")
    assert opcoes_provider("voice") == ["file", "local", "gemini", "voxcpm", "openvoice", "voicestudio", "audio8", "elevenlabs", "xai"]
    assert opcoes_provider("run") == ["file", "local", "gemini", "voxcpm", "openvoice", "voicestudio", "audio8", "elevenlabs", "xai"]
    assert "audio8" in opcoes_provider("voice") and "audio8" in opcoes_provider("run")
    assert set(opcoes_provider("voice")) - set(opcoes_provider("run")) == set()  # era {"elevenlabs", "xai"}: `voice` aceitava os dois stubs que sempre falham e `run` não
    assert opcoes_provider("voice") == opcoes_provider("run") == registro == enum_do_contrato  # o nome do teste é do G0, que registrou a divergência: hoje as quatro fontes concordam


# (o nome é do G0: hoje `voice` e `run` aceitam os dois; o teste prende o que `voice.run` faz com eles, a recusa de sempre)
@pytest.mark.parametrize("prov", ["elevenlabs", "xai"])
def test_the_two_stub_providers_voice_accepts_always_fail(prov):
    contrato = SimpleNamespace(data={"voz": {"provider": "file"}})
    with pytest.raises(voice.VoiceError, match=f"provider={prov}: stub in simplicio-video v0.2"):
        voice.run(contrato, provider=prov)


# U22e: o que o parser e o motor fazem com cada nome do registro depois que as duas CLIs o aceitam inteiro
NOMES_DO_REGISTRO = ["file", "local", "gemini", "voxcpm", "openvoice", "voicestudio", "audio8", "elevenlabs", "xai"]
STUB = "provider={}: stub in simplicio-video v0.2 - generate the takes elsewhere, drop them in the file dir and use --provider file"


def le_provider(comando: str, valor: str, flag: str = "--provider"):
    """O que o parser entende de `<comando> contract.yaml <flag> <valor>` (SystemExit(2) quando recusa)."""
    return cli.build_parser().parse_args([comando, "contract.yaml", flag, valor])


@pytest.mark.parametrize("comando", ["voice", "run"])
@pytest.mark.parametrize("prov", NOMES_DO_REGISTRO)
def test_the_parser_of_voice_and_of_run_takes_every_provider_of_the_registry(comando, prov):
    # U22e: antes nenhuma das duas aceitava audio8, e `run` recusava também os dois stubs
    assert le_provider(comando, prov).provider == prov


@pytest.mark.parametrize("comando", ["voice", "run"])
def test_the_short_flag_takes_the_same_providers(comando):
    assert le_provider(comando, "audio8", "-p").provider == "audio8"


@pytest.mark.parametrize("comando", ["voice", "run"])
def test_the_parser_refuses_a_provider_outside_the_registry_and_gives_the_whole_registry(comando, capsys):
    with pytest.raises(SystemExit) as e:
        le_provider(comando, "nope")
    assert e.value.code == 2
    err = capsys.readouterr().err
    assert "argument --provider/-p: invalid choice: 'nope'" in err
    assert "{" + ",".join(NOMES_DO_REGISTRO) + "}" in err  # a linha de uso dá a lista inteira, na ordem do registro


def test_the_flag_the_catalog_of_voices_and_the_registry_are_one_list():
    from simplicio_video import catalog

    assert [v["id"] for v in catalog.voices()] == opcoes_provider("voice") == opcoes_provider("run") == list(voice.PROVIDERS)


@pytest.mark.parametrize("comando", ["voice", "run"])
@pytest.mark.parametrize("prov", ["elevenlabs", "xai"])
def test_a_stub_provider_passes_the_parser_of_both_and_is_refused_by_voice_with_todays_reason(mini, comando, prov):
    with pytest.raises(SystemExit) as e:
        cli.main([comando, str(mini), "--provider", prov])
    assert e.value.code == STUB.format(prov)
    assert not (mini.parent / "timing.lock.json").exists()


@pytest.mark.parametrize("prov", ["elevenlabs", "xai"])
def test_run_json_tells_a_stub_like_any_other_voice_failure(mini, prov, capsys):
    assert cli.main(["run", str(mini), "--provider", prov, "--json"]) == 1
    saida = json.loads(capsys.readouterr().out)
    assert saida["ok"] is False and saida["error"] == {"code": "RENDER_FALHOU", "message": STUB.format(prov)}


def test_audio8_goes_from_the_voice_command_to_voice_run(mini, monkeypatch):
    visto: dict = {}
    monkeypatch.setattr(voice, "run", lambda c, **kw: visto.update(kw))
    assert cli.main(["voice", str(mini), "--provider", "audio8"]) == 0
    assert visto["provider"] == "audio8"


def test_audio8_goes_from_the_run_command_to_the_pipeline(mini, monkeypatch):
    from simplicio_video import pipeline

    visto: dict = {}
    monkeypatch.setattr(pipeline, "run_all", lambda contrato, **kw: visto.update(kw))
    assert cli.main(["run", str(mini), "--provider", "audio8"]) == 0
    assert visto["provider"] == "audio8"


@pytest.mark.parametrize("comando", ["voice", "run"])
def test_without_the_flag_the_provider_stays_with_the_contract(mini, monkeypatch, comando):
    from simplicio_video import pipeline

    visto: dict = {}
    monkeypatch.setattr(voice, "run", lambda c, **kw: visto.update(kw))
    monkeypatch.setattr(pipeline, "run_all", lambda contrato, **kw: visto.update(kw))
    assert cli.build_parser().parse_args([comando, "contract.yaml"]).provider is None
    assert cli.main([comando, str(mini)]) == 0
    assert visto["provider"] is None  # `voice.run` e `run_all` resolvem pelo `voz.provider` do contrato


@pytest.mark.parametrize("comando", ["voice", "run"])
@pytest.mark.parametrize("nome", ["Gemini", "GEMINI", "audio-8", "audio8 ", "", "all"])
def test_the_parser_matches_the_names_of_the_registry_exactly(comando, nome):
    with pytest.raises(SystemExit) as e:
        le_provider(comando, nome)
    assert e.value.code == 2


# ============================================================================================ (f) o limite de recursos do filho

@LINUX
def test_instagram_limits_the_cpu_of_the_child_with_a_preexec_fn_and_matchcut_limits_its_memory_with_a_wrapper(tmp_path, monkeypatch):
    visto: dict = {}

    class Filho:
        returncode = 0

        def wait(self, timeout=None):
            return 0

    def espia(nome):
        @contextlib.contextmanager
        def guarded_child(argv, **kw):
            visto[nome] = SimpleNamespace(argv=list(argv), kw=kw)
            yield Filho()
        return guarded_child

    monkeypatch.setattr(instagram, "_matar", lambda proc: None)  # o Filho falso não tem pid: nada de killpg
    monkeypatch.setattr(matchcut, "_matar", lambda proc: None)
    monkeypatch.setattr(instagram.childio, "guarded_child", espia("instagram"))
    instagram._executa([sys.executable, "-c", "pass"], None, str(tmp_path))
    monkeypatch.setattr(matchcut.childio, "guarded_child", espia("matchcut"))
    matchcut._executa([sys.executable, "-c", "pass"], str(tmp_path), {}, "qc")
    # U22 decide: dois mecanismos para o mesmo fim; sob as threads do MCP o preexec_fn do instagram não é seguro, o wrapper do matchcut é
    # U22f decidiu: um mecanismo só, o wrapper (os limites são postos dentro do filho, que depois faz exec); o nome deste teste é histórico: o id não muda
    assert "preexec_fn" not in visto["instagram"].kw and "preexec_fn" not in visto["matchcut"].kw  # era callable(visto["instagram"].kw["preexec_fn"])
    assert visto["instagram"].argv == [sys.executable, "-c", "pass"] and visto["matchcut"].argv == [sys.executable, "-c", "pass"]


@LINUX
def test_what_each_mechanism_really_sets_in_the_child(tmp_path, monkeypatch):
    import resource

    sonda = ("import resource, json; print(json.dumps({n: resource.getrlimit(getattr(resource, n)) for n in "
             "('RLIMIT_CPU', 'RLIMIT_AS', 'RLIMIT_CORE')}))")
    pai = {n: list(resource.getrlimit(getattr(resource, n))) for n in ("RLIMIT_CPU", "RLIMIT_AS", "RLIMIT_CORE")}
    quatro_gib = 4 * 1024 ** 3
    sonda_do_instagram = tmp_path / "sonda.py"
    sonda_do_instagram.write_text(sonda, encoding="utf8")
    monkeypatch.setattr(instagram, "_prepara", lambda f, destino: (sonda_do_instagram, []))  # sem checkout: o "script" é a sonda
    r_ig = instagram.run_tool("hookscore", ["--hook", "x"])  # U22f: pelo run_tool, o caminho do CLI e do MCP (era subprocess.run com o preexec_fn)
    r_mc = subprocess.run([sys.executable, "-I", "-B", "-X", "utf8", "-c", matchcut._WRAPPER, str(quatro_gib), "-c", sonda],
                          capture_output=True, text=True, check=True, cwd=tmp_path)
    assert r_ig["codigo_saida"] == 0, r_ig["stderr"]
    ig, mc = json.loads(r_ig["stdout"]), json.loads(r_mc.stdout)
    if pai["RLIMIT_CPU"][1] != resource.RLIM_INFINITY:
        pytest.skip("o pai já tem um limite de CPU: um hard menor herdado vence o do instagram")
    assert ig["RLIMIT_CPU"] == [35, 40]  # TIMEOUT_S (30) + CPU_FOLGA_S (5) de CPU, hard +5
    # U22 decide: o instagram não limita memória
    # U22f decidiu: limita, como o matchcut (4 GiB de espaço de endereço): as execuções que terminam, nos 6 scripts reais com a entrada máxima de 1 MiB, pedem 45-140 MiB;
    # o pior caso achado (1 MiB de 524.288 linhas de 1 caractere em hookscore --json) chega a 1,74 GiB e morre no teto de saída de 2 MiB com ou sem o limite
    assert ig["RLIMIT_AS"] == [quatro_gib, quatro_gib]  # era pai["RLIMIT_AS"]: sem limite
    assert ig["RLIMIT_CORE"] == [0, 0]
    assert mc["RLIMIT_AS"] == [quatro_gib, quatro_gib]  # U22 decide: o matchcut limita memória (RLIMIT_AS), não CPU
    # U22f decidiu: o matchcut segue sem limite de CPU (matchcut.py não é da posse da U22f e os scripts dele rodam de 300 s a 7200 s: matchcut.TIMEOUT_S)
    assert mc["RLIMIT_CPU"] == pai["RLIMIT_CPU"]
    assert mc["RLIMIT_CORE"] == [0, 0]


def test_the_matchcut_memory_limit_default_and_override(monkeypatch):
    monkeypatch.delenv("MATCHCUT_MEM_GIB", raising=False)
    assert matchcut._limite_de_memoria() == 8 * 1024 ** 3 == matchcut.DEFAULT_MEM_GIB * 1024 ** 3
    monkeypatch.setenv("MATCHCUT_MEM_GIB", "0")
    assert matchcut._limite_de_memoria() == 0  # 0 desliga o limite (o wrapper pula RLIMIT_AS)
    monkeypatch.setenv("MATCHCUT_MEM_GIB", "2")
    assert matchcut._limite_de_memoria() == 2 * 1024 ** 3
    assert "RLIMIT_AS" in matchcut._WRAPPER and "RLIMIT_CPU" not in matchcut._WRAPPER
