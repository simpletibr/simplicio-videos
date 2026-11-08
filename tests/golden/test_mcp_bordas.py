"""G0 (golden, caracterização): o que o MCP (e o terminal) devolve nas bordas que a onda MUDA CONTRATO (U22) altera.

Cada bloco é uma letra de U22 e escreve, como valor de HOJE, o que um chamador vê: a mensagem de recusa de cada módulo (a), o que fica no
texto devolvido ao agente (a), o que cada erro e cada arquivo de job deixa passar de uma chave (b), o que `voice` aceita como base do
Gemini (c), a URL do VoiceStudio (d), as opções `--provider` (e) e o mecanismo de limite de recursos do filho (f). Cada divergência é um
assert do valor atual com o comentário "U22 decide"; U22 só pode mudar linhas daqui, e o diff é o que o dono aprova.

Privados exercitados por import direto (caracterização; são as funções que os wrappers MCP/CLI chamam):
  (a) matchcut._confere_saida, instagram._checa_saida, montage._output_refusal, video_to_skill._new_dir, voicestudio._guard_out;
      matchcut.resposta_mcp, instagram.resposta_mcp; U22h: as tools do MCP mcp_server.video_media, video_shorts, video_edit, video_clone,
      video_install (as chamadas, com o CLI trocado por um gravador; a matriz inteira está em tests/golden/test_mcp_caminhos.py). (b) busca.BuscaError, openverse.OpenverseError, swap_providers.base.SwapError,
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

from simplicio_video import busca, cli, instagram, jobs, matchcut, mcp_server, montage, openverse, video_to_skill, voice, voice_clone, voicestudio
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


# ---- U22h: o mesmo para as TOOLS do MCP que gravam por um caminho que o chamador escolhe (media, shorts, edit, clone/Hypit, install)
# U22 decide: o MCP só exigia caminho absoluto sem `..` (o install --target, só absoluto) e entregava o resto ao CLI: `-o /etc/x`, `-o` por um link para
#   `.ssh`, `--to /etc/x` do Hypit, `install --target {w}/../etc`. Só o voicestudio (acima) recusava.
#   U22h decidiu: o caminho que o CLI vai GRAVAR passa pela regra única (terceiros.lugar_proibido) e não pode ter link em nenhum nome (mcp_policy.escrita_recusada).
#   Cada linha abaixo é um fato da tabela "antes -> depois" do PR: hoje a chamada chega ao CLI ("ACEITA"); passa a ser recusada com o texto escrito aqui.

FONTE = "{work}/a.mp4"
DICA = "escolha uma pasta sua (a do projeto, /tmp ou o home fora das pastas ocultas)"
SEM_LINK = "o MCP só grava em caminho real, sem link em nenhuma pasta do caminho"
LUGAR_SISTEMA = f"o MCP não grava em pasta do sistema; {DICA}"
LUGAR_OCULTA = f"o MCP não grava em pasta oculta do home (.ssh, .config, .claude...); {DICA}"
FERRAMENTAS_DO_MCP = {"media": mcp_server.video_media, "shorts": mcp_server.video_shorts, "edit": mcp_server.video_edit, "clone": mcp_server.video_clone,
                      "install": mcp_server.video_install}


def mcp(w, monkeypatch, ferramenta: str, argv: list[str]):
    """("aceita", o argv que chegou ao CLI) ou ("recusa", o texto), com a pasta de teste trocada por {home}/{work}."""
    monkeypatch.setattr(mcp_server, "_cli", lambda argv, codigos_ok=(0,): {"ok": True, "cli": list(argv)})
    sub = lambda t: t.replace("{home}", str(w.home)).replace("{work}", str(w.work)).replace("{data}", str(w.data)).replace("{tools}", str(w.tools))  # noqa: E731
    r = FERRAMENTAS_DO_MCP[ferramenta](argv=[sub(a) for a in argv])
    norma = lambda t: str(t).replace(str(w.home), "{home}").replace(str(w.work), "{work}").replace(str(w.data), "{data}").replace(str(w.tools), "{tools}")  # noqa: E731
    return ("aceita", [norma(a) for a in r["cli"]]) if r["ok"] else ("recusa", norma(r["error"]))


# (id do fato, tool, argv, o que passa a ser devolvido), com a pasta de teste trocada por {home}, {work}, {data} e {tools}.
FATOS_DO_MCP = [
    ("edit-render-etc", "edit", ["render", "{work}/edl.json", "-o", "/etc/novo.mp4"], f"edit render: saída '/etc/novo.mp4': {LUGAR_SISTEMA}"),
    ("edit-transcribe-colado", "edit", ["transcribe", FONTE, "-o/etc/novo.json"], f"edit transcribe: saída '/etc/novo.json': {LUGAR_SISTEMA}"),
    ("edit-verify-ssh", "edit", ["verify", FONTE, "1", "2", "--output={home}/.ssh/novo.png"],
     f"edit verify: saída '{{home}}/.ssh/novo.png': {LUGAR_OCULTA}"),
    ("edit-grade-inicio", "edit", ["grade", FONTE, "-o", "{home}/Library/LaunchAgents/x.mp4"],
     "edit grade: saída '{home}/Library/LaunchAgents/x.mp4': o MCP não grava em pasta de início automático (LaunchAgents, LaunchDaemons, Startup); " + DICA),
    ("media-probe-git", "media", ["probe", FONTE, "-o", "{work}/.git/hooks/x.json"],
     "media: saída '{work}/.git/hooks/x.json': o MCP não grava dentro de uma pasta .git; " + DICA),
    ("media-audio-dados", "media", ["audio", FONTE, "-o", "{data}/x.wav"],
     "media: saída '{data}/x.wav': o MCP não grava dentro da pasta de dados do motor (jobs, tools, openmontage-data); " + DICA),
    ("shorts-plan-ferramentas", "shorts", ["plan", FONTE, "--transcript", "{work}/words.json", "-o", "{tools}/p.json"],
     "shorts: saída '{tools}/p.json': o MCP não grava dentro da pasta de ferramentas do motor; " + DICA),
    ("shorts-cut-barra-dupla", "shorts", ["cut", FONTE, "{work}/plan.json", "-o", "//etc/novo"],
     f"shorts: saída '//etc/novo': o MCP não grava em pasta do sistema (o caminho real é '/etc/novo'); {DICA}"),
    ("media-por-link-para-ssh", "media", ["probe", FONTE, "-o", "{work}/lnk_ssh/x.json"],
     "media: saída '{work}/lnk_ssh/x.json': o MCP não grava em pasta oculta do home (.ssh, .config, .claude...) (o caminho real é '{home}/.ssh/x.json'); " + DICA),
    ("shorts-por-link-inofensivo", "shorts", ["inspect", FONTE, "-o", "{work}/lnk_ok/x.json"],
     f"shorts: saída '{{work}}/lnk_ok/x.json': '{{work}}/lnk_ok' é um link simbólico; {SEM_LINK} (o caminho real seria '{{work}}/out/x.json')"),
    ("edit-render-pasta-do-edl-por-link", "edit", ["render", "{work}/lnk_ssh/edl.json", "-o", "{work}/out/f.mp4"],
     "edit render: a pasta do EDL '{work}/lnk_ssh/edl.json': o MCP não grava em pasta oculta do home (.ssh, .config, .claude...) "
     "(o caminho real é '{home}/.ssh/edl.json'); " + DICA),
    ("edit-pack-edit-dir-link", "edit", ["pack", "{work}/lnk_ok"],
     f"edit pack: a pasta EDIT_DIR '{{work}}/lnk_ok': é um link simbólico; {SEM_LINK} (o caminho real seria '{{work}}/out')"),
    ("clone-get-etc", "clone", ["get", "b1", "--output", "n", "--to", "/etc/novo.mp4"], f"clone get: o destino --to '/etc/novo.mp4': {LUGAR_SISTEMA}"),
    ("clone-media-cut-ssh", "clone", ["media", "cut", FONTE, "--start", "0", "--end", "1", "--to", "{home}/.ssh/x.mp4"],
     f"clone media cut: o destino --to '{{home}}/.ssh/x.mp4': {LUGAR_OCULTA}"),
    ("install-etc", "install", ["--target", "/etc"], f"install: a pasta de --target '/etc': {LUGAR_SISTEMA}"),
    ("install-ssh", "install", ["--target", "{home}/.ssh"], f"install: a pasta de --target '{{home}}/.ssh': {LUGAR_OCULTA}"),
    ("install-por-link", "install", ["--target", "{work}/lnk_ok"],
     f"install: a pasta de --target '{{work}}/lnk_ok': é um link simbólico; {SEM_LINK} (o caminho real seria '{{work}}/out')"),
    ("install-com-dotdot", "install", ["--target", "{work}/../etc"],
     "install: a pasta de --target '{work}/../etc': precisa ser um caminho absoluto, sem `..` (o MCP não grava em caminho relativo nem com `..`)"),
    # os dois jeitos de o CLI ler um -o que a política não via (achados na caça a bypass; valiam na main)
    ("media-opcao-depois-do-traco", "media", ["probe", FONTE, "--", "x", "-o", "/etc/novo.json"], f"media: saída '/etc/novo.json': {LUGAR_SISTEMA}"),
    ("shorts-opcao-depois-do-traco", "shorts", ["inspect", FONTE, "--", "x", "-o", "rel/novo.json"],
     "shorts: saída 'rel/novo.json': precisa ser um caminho absoluto, sem `..` (o MCP não grava em caminho relativo nem com `..`)"),
    ("media-ajuda-depois-do-traco", "media", ["probe", FONTE, "-o", "/etc/novo.json", "--", "-h"], f"media: saída '/etc/novo.json': {LUGAR_SISTEMA}"),
]


@LINUX
@pytest.mark.parametrize("fato,ferramenta,argv,depois", FATOS_DO_MCP, ids=[f[0] for f in FATOS_DO_MCP])
def test_the_mcp_tools_that_write_refuse_what_the_one_rule_of_places_refuses(mundo, monkeypatch, fato, ferramenta, argv, depois):
    for pasta in (mundo.home / ".ssh", mundo.work / "out"):
        pasta.mkdir(parents=True, exist_ok=True)
    (mundo.work / "lnk_ssh").symlink_to(mundo.home / ".ssh")
    (mundo.work / "lnk_ok").symlink_to(mundo.work / "out")
    assert mcp(mundo, monkeypatch, ferramenta, argv) == ("recusa", depois)  # U22 decide: hoje ("aceita", [<tool>, *argv]); passa a ser recusada


@LINUX
@pytest.mark.parametrize("ferramenta,argv", [
    ("edit", ["render", "{work}/edl.json", "-o", "{work}/out/novo.mp4"]),
    ("media", ["probe", FONTE, "-o", "{home}/docs/novo.json"]),
    ("shorts", ["cut", FONTE, "{work}/plan.json", "-o", "{work}/data/cortes"]),  # uma pasta `data` do PROJETO (a do motor é a recusada acima)
    ("clone", ["get", "b1", "--output", "n", "--to", "/tmp/u22h-nao-existe/v.mp4"]),
    ("install", ["--target", "{work}/projeto"]),
    ("install", ["--check", "--target", "/etc"]),  # só lê
    ("media", ["probe", "/etc/novo.mp4"]),  # a fonte é lida
], ids=["edit-pasta-de-trabalho", "media-home-fora-das-ocultas", "shorts-pasta-data-do-projeto", "clone-tmp", "install-projeto", "install-check-so-le",
        "media-fonte-em-etc"])
def test_the_mcp_tools_still_run_what_writes_at_the_places_of_the_user_and_what_only_reads(mundo, monkeypatch, ferramenta, argv):
    status, cli_argv = mcp(mundo, monkeypatch, ferramenta, argv)
    assert status == "aceita" and cli_argv[0] in ("edit", "media", "shorts", "clone", "install")


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
    # U22 decide: nenhuma das duas CLIs aceita audio8, que o contrato e o registro aceitam
    assert opcoes_provider("voice") == ["file", "local", "gemini", "voxcpm", "openvoice", "voicestudio", "elevenlabs", "xai"]
    assert opcoes_provider("run") == ["file", "local", "gemini", "voxcpm", "openvoice", "voicestudio"]
    assert "audio8" not in opcoes_provider("voice") and "audio8" not in opcoes_provider("run")
    assert set(opcoes_provider("voice")) - set(opcoes_provider("run")) == {"elevenlabs", "xai"}  # `voice` aceita os dois stubs que sempre falham


@pytest.mark.parametrize("prov", ["elevenlabs", "xai"])
def test_the_two_stub_providers_voice_accepts_always_fail(prov):
    contrato = SimpleNamespace(data={"voz": {"provider": "file"}})
    with pytest.raises(voice.VoiceError, match=f"provider={prov}: stub in simplicio-video v0.2"):
        voice.run(contrato, provider=prov)


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
