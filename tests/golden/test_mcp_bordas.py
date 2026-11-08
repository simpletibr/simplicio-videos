"""G0 (golden, caracterização): o que o MCP (e o terminal) devolve nas bordas que a onda MUDA CONTRATO (U22) altera.

Cada bloco é uma letra de U22 e escreve, como valor de HOJE, o que um chamador vê: a mensagem de recusa de cada módulo (a), o que fica no
texto devolvido ao agente (a), o que cada erro e cada arquivo de job deixa passar de uma chave (b), o que `voice` aceita como base do
Gemini (c), a URL do VoiceStudio (d), as opções `--provider` (e) e o mecanismo de limite de recursos do filho (f). Cada divergência é um
assert do valor atual com o comentário "U22 decide"; U22 só pode mudar linhas daqui, e o diff é o que o dono aprova.

Privados exercitados por import direto (caracterização; são as funções que os wrappers MCP/CLI chamam):
  (a) matchcut._confere_saida, instagram._checa_saida, montage._output_refusal, video_to_skill._new_dir, voicestudio._guard_out;
      matchcut.resposta_mcp, instagram.resposta_mcp. (b) busca.BuscaError, openverse.OpenverseError, swap_providers.base.SwapError,
      jobs.write_json_atomic (-> jobs._scrub). (c) voice.gemini_base, swap_providers.gemini.GeminiAdapter._base.
  (d) voice_clone.voicestudio_url, voicestudio.base_url. (e) cli.build_parser, voice.PROVIDERS. (f) instagram._executa/_limites_do_filho,
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
    ("{home}/Library/LaunchAgents/x.plist", {**mensagens("{home}/Library/LaunchAgents/x.plist", INICIO),
                                              "voicestudio": ("ok", "{home}/Library/LaunchAgents/x.plist")}),
    ("{work}/.git/hooks/x.txt", {**mensagens("{work}/.git/hooks/x.txt", "dentro de uma pasta .git"),
                                  "voicestudio": ("ok", "{work}/.git/hooks/x.txt")}),
], ids=["livre", "home-oculto", "sistema", "inicio-automatico", "git"])
def test_the_refusal_each_module_gives_for_an_output_path(mundo, caminho, esperado):
    p = pasta(mundo, caminho)
    assert {m: recusa(m, mundo, p) for m in esperado} == esperado


RES_MATCHCUT = {"resultado": True, "script": "s", "codigo_saida": 0, "avisos": []}
RES_INSTAGRAM = {"resultado": True, "ferramenta": "f", "codigo_saida": 0, "avisos": []}
TEXTO_COM_SELETORES = "a️b\U000e0100c​d\x1b[31m"


def test_the_text_an_agent_gets_keeps_variation_selectors_in_matchcut_and_not_in_instagram():
    # U22 decide: o seletor de variação (U+FE0F, U+E0100) pode carregar dado escondido; só o instagram o tira da saída entregue ao agente
    m = matchcut.resposta_mcp({**RES_MATCHCUT, "stdout": TEXTO_COM_SELETORES, "stderr": "e️"})
    i = instagram.resposta_mcp({**RES_INSTAGRAM, "stdout": TEXTO_COM_SELETORES, "stderr": "e️"})
    assert m["saida"] == "a️b\U000e0100cd[31m" and m["erros"] == "e️"
    assert i["saida"] == "abcd[31m" and i["erros"] == "e"
    assert video_to_skill.limpa_mcp(TEXTO_COM_SELETORES) == "a️b\U000e0100cd[31m"  # o video_to_skill (mcp_run) faz como o matchcut


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
    # U22 decide: voice.gemini_base() não valida nada, e `voice` manda a chave GEMINI_API_KEY em x-goog-api-key para essa base
    ("http://example.com/v1beta", "http://example.com/v1beta", "SwapError"),
    ("http://10.0.0.5:9000", "http://10.0.0.5:9000", "SwapError"),
    ("ftp://example.com/x", "ftp://example.com/x", "SwapError"),
    ("file:///tmp/mock", "file:///tmp/mock", "SwapError"),
])
def test_voice_gemini_base_accepts_what_the_swap_adapter_refuses(monkeypatch, valor, voice_devolve, swap_devolve):
    monkeypatch.setenv("SIMPLICIO_GEMINI_BASE", valor)
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
    assert callable(visto["instagram"].kw["preexec_fn"]) and "preexec_fn" not in visto["matchcut"].kw
    assert visto["instagram"].argv == [sys.executable, "-c", "pass"] and visto["matchcut"].argv == [sys.executable, "-c", "pass"]


@LINUX
def test_what_each_mechanism_really_sets_in_the_child(tmp_path):
    import resource

    sonda = ("import resource, json; print(json.dumps({n: resource.getrlimit(getattr(resource, n)) for n in "
             "('RLIMIT_CPU', 'RLIMIT_AS', 'RLIMIT_CORE')}))")
    pai = {n: list(resource.getrlimit(getattr(resource, n))) for n in ("RLIMIT_CPU", "RLIMIT_AS", "RLIMIT_CORE")}
    quatro_gib = 4 * 1024 ** 3
    r_ig = subprocess.run([sys.executable, "-c", sonda], capture_output=True, text=True, check=True, cwd=tmp_path,
                          preexec_fn=instagram._limites_do_filho(max(1, int(instagram.TIMEOUT_S) + instagram.CPU_FOLGA_S)))
    r_mc = subprocess.run([sys.executable, "-I", "-B", "-X", "utf8", "-c", matchcut._WRAPPER, str(quatro_gib), "-c", sonda],
                          capture_output=True, text=True, check=True, cwd=tmp_path)
    ig, mc = json.loads(r_ig.stdout), json.loads(r_mc.stdout)
    if pai["RLIMIT_CPU"][1] != resource.RLIM_INFINITY:
        pytest.skip("o pai já tem um limite de CPU: um hard menor herdado vence o do instagram")
    assert ig["RLIMIT_CPU"] == [35, 40]  # TIMEOUT_S (30) + CPU_FOLGA_S (5) de CPU, hard +5
    assert ig["RLIMIT_AS"] == pai["RLIMIT_AS"]  # U22 decide: o instagram não limita memória
    assert ig["RLIMIT_CORE"] == [0, 0]
    assert mc["RLIMIT_AS"] == [quatro_gib, quatro_gib]  # U22 decide: o matchcut limita memória (RLIMIT_AS), não CPU
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
