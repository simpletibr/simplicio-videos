"""U09, registro único de trilha: `tools.TOOLS` declara tudo e o resto é derivado.

Hoje cada trilha é repetida em tabelas paralelas por nome (tools.COMMANDS, doctor_trilhas.CLONE e DEPS, o `_setup` e o `_tabela_fixada` do
doctor, scripts/smoke_trilhas.MCP_LEITURA, o `pin_only` do update, o checkout especial do video-use): trilha nova esquece uma delas e nada
falha (`DEPS.get(t.name, [])`). Este arquivo tem cinco partes:

1. CARACTERIZAÇÃO (verde antes e depois): o que o usuário vê não muda. `tools --json`, `status --json`, `doctor trilhas --json` e os textos,
   o `--online`, os overrides, o relatório e o lock do `update`, byte a byte (sha256 do texto normalizado) numa caixa selada; e as tabelas de
   hoje (comando, clone, deps, setup, integridade, chamada MCP do smoke, pin_only) congeladas como fatos por trilha.
   Normalização: a pasta temporária vira `<TMP>`, o commit de um checkout falso vira `<HEAD:pasta>` e o pin do registro vira `<PIN:trilha>`:
   um bump de pin não quebra o teste, uma trilha com o pin da outra quebra. REGISTRO_TRILHAS_DUMP=<pasta> grava o texto normalizado de cada
   captura (e não confere), para comparar com o de origin/main quando o hash muda.
2. O REGISTRO (vermelho antes): `Tool` ganha command, pin_only, checkout_env, deps, clone_verb, setup_probe, integrity (e mcp_read,
   checkout_probe), e cada trilha declara o que as tabelas diziam.
3. A DERIVAÇÃO (vermelho antes): trocar um campo do registro muda o que o doctor, o `tools` e o update mostram; nenhuma tabela por nome sobra.
4. A PARIDADE: um teste percorre TOOLS e exige comando no parser da CLI, tool MCP no snapshot, linha na skill de trilhas, entrada no doctor e no
   smoke. `lacunas()` diz o que falta a uma trilha; o teste prova que ela pega uma trilha incompleta (não é vácuo).
5. O que mais a ficha pede: `_video_use_pin()` só quando o video-use é usado (hoje roda no import e derruba até o `--help`), o ciclo
   tools <-> tools_update, regex públicos, nenhum privado de outro módulo, `--` nos dois `git clone` que ainda não têm (texto do doctor e
   data/tools/video-use/setup.sh).
"""
from __future__ import annotations

import ast
import dataclasses
import hashlib
import importlib.util
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

import _caixa
from _caixa import _Lazy, posix_real, roda
from helpers import ROOT, SRC
from simplicio_video import HYPERFRAMES, __version__, hostos, mcp_server, status, terceiros, tools, tools_lock, tools_update
from simplicio_video.cli import build_parser
from test_doctor_trilhas import _rede_em_dia, monta_saudavel
from test_doctor_trilhas import ambiente as _ambiente_do_doctor
from test_tools_update import Fake
from test_tools_update import ambiente as _ambiente_do_update

dt = _Lazy("simplicio_video.doctor_trilhas")
saude = _caixa.saude  # fixtures of the doctor's `ambiente`, assigned (not imported under their own name) so pytest finds them here
caixa = _caixa.caixa
ambiente = _ambiente_do_doctor  # the doctor's machine: sealed PATH, nothing installed, fake git
ambiente_update = _ambiente_do_update  # the update's machine: a checkout with .git and its marker per git track

SMOKE = ROOT / "scripts" / "smoke_trilhas.py"
SETUP_SH = SRC / "data" / "tools" / "video-use" / "setup.sh"
SKILL = SRC / "data" / "skills" / "simplicio-video-trilhas" / "SKILL.md"
SNAPSHOT = json.loads((ROOT / "tests" / "data" / "mcp_tools_list.snapshot.json").read_text(encoding="utf-8"))

# --- o que as tabelas paralelas diziam em origin/main (a7ac9e3), por trilha ----------------------------------------------------

COMANDOS = {"video-use": "edit", "openmontage": "montage", "opencut": "opencut", "hypit": "clone", "toonflow": "toonflow",
            "moneyprinter": "moneyprinter", "matchcut": "matchcut", "instagram": "instagram", "tinyfish": "busca",
            "voicestudio": "voicestudio", "rea_video": "rea-video", "video_to_skill": "video-to-skill", "yt-dlp": "media fetch"}
CLONE = {"openmontage": "simplicio-video montage clone", "opencut": "simplicio-video opencut clone",
         "toonflow": "simplicio-video toonflow clone", "moneyprinter": "simplicio-video moneyprinter clone",
         "matchcut": "simplicio-video matchcut clone", "instagram": "simplicio-video instagram clone",
         "rea_video": "simplicio-video rea-video clone", "video_to_skill": "simplicio-video video-to-skill clone",
         "video-use": "simplicio-video edit setup"}
# (name, required, minimum version or None), the form doctor_trilhas.DEPS had
DEPS = {"openmontage": [("ffmpeg", True, None)], "opencut": [("bun", True, None), ("docker", False, None)],
        "hypit": [("node", True, (22, 15))], "toonflow": [("bun", True, None), ("docker", False, None)],
        "moneyprinter": [("ffmpeg", True, None)], "matchcut": [("ffmpeg", True, None)], "instagram": [],
        "rea_video": [("ffmpeg", True, None)], "video_to_skill": [("ffmpeg", False, None)], "voicestudio": [("bun", False, None)],
        "video-use": [("ffmpeg", True, None), ("SIMPLICIO_TTS_PY", True, None)],
        "tinyfish": [("node", True, (24,)), ("npm", True, None)], "yt-dlp": [("ffmpeg", False, None)]}
PIN_ONLY = {"video-use", "video_to_skill"}  # tools_update.pin_only: the update never follows their upstream
SETUP = {"openmontage", "moneyprinter", "matchcut", "rea_video", "video_to_skill", "opencut", "toonflow"}  # `_setup` had a branch
INTEGRIDADE = {"matchcut", "video_to_skill"}  # `_tabela_fixada` had a table (instagram is left out on purpose: the doctor must not import it)
GIT_SEM_VERBO = {"voicestudio"}  # a git track with no `clone` in the CLI: the doctor shows the git commands tools.install runs
CHECKOUT_PROPRIO = {"openmontage"}  # doctor_trilhas._pasta_do_checkout asked montage.default_openmontage_dir()
# the read-only MCP call of scripts/smoke_trilhas.py: (function, kwargs, needs the checkout, expectation)
MCP_LEITURA = {
    "openmontage": ("video_montage", {"args": "status --json"}, True, "ok"),
    "opencut": ("video_opencut", {"args": "where"}, True, "ok"),
    "hypit": ("video_clone", {"args": "status --json"}, True, "ok"),
    "toonflow": ("video_toonflow", {"args": "where"}, True, "ok"),
    "moneyprinter": ("video_moneyprinter", {"args": "status"}, True, "ok"),
    "matchcut": ("video_matchcut", {"args": "status"}, True, "ok"),
    "instagram": ("video_instagram", {"acao": "status"}, True, "ok"),
    "voicestudio": ("video_voicestudio", {"args": "status"}, False, "ok"),
    "video-use": ("video_edit", {"args": "--help"}, False, "ok"),
    "tinyfish": ("video_busca", {"acao": "status"}, True, "ok"),
    "yt-dlp": ("video_media", {"args": ["fetch"]}, False, "recusa"),
    "rea_video": ("video_rea_video", {"args": "where"}, True, "ok"),
    "video_to_skill": ("video_video_to_skill", {"args": "status"}, True, "ok"),
}

# --- parte 1: o que o usuário vê, byte a byte (sha256 do texto normalizado) ---------------------------------------------------

GOLDEN = {
    "vazia/tools-json": "5ab7ad3d57ac81fc8d04a9f6aced1e95d10135ecb51a7f3aa32316c238cbe0ee",
    "vazia/tools-texto": "7694f930813c81d18afc82c691e193df2a8490ce94e18570fcd645b15c90ab1d",
    "vazia/status-json": "3f640390d1997d7142c26231854c6f4bb5504d9d803419276af654bbbe7cc7dc",
    "vazia/doctor-trilhas-json": "dccc09c629c7774b6cf433c1eafe4bafdc45f27f547dc3d3999431d97b8d8a4d",
    "vazia/doctor-trilhas-texto": "d08b034267e06cdee317cd8bf102ee7973ab67bbaaf51de0e2a8a7c68577486f",
    "saudavel/tools-json": "1d156af0e6735c2364c2eb5cacf92494a6f6773ad518ca7fbf802a0767b3b842",
    "saudavel/status-json": "5313491d7532774214213cb2dc6fa35f11d014a9d04e253f5376442ad3f6ea86",
    "saudavel/doctor-trilhas-json": "6e1f47f93ac07d964d0f1337862864f3785a9b42e4d12f3677eaaa612e1d5794",
    "saudavel/doctor-trilhas-texto": "a8278bf5ee864492f3c95462c70fd33d52eb4dbe3234c242e5c74cb7f331656a",
    "saudavel/doctor-trilhas-online": "e4e3a25ca5e07355acedb4c7b8fa7929186f7f898834d4f6b4352156acbbbe65",
    "saudavel/doctor-json-linha-trilhas": "2368f669a042b7cdd92ae064359e64305a74b3af52c9bfd9e0bc9d0e89c87ebe",
    "overrides/tools-json": "aadcf3e1b079ea144c1e5bfdbe3e960dcab9156badb49b5e258f9fd1e244295a",
    "overrides/tools-texto": "e458ad20b245d1d10f6d335dcb3c9d19a8f024a3c515ccc5de460fc3e4547fc8",
    "overrides/doctor-trilhas-json": "a776bc2f71b2301db41e2030d106269bd66cbcb8399c7b2c2201529967f0a67e",
    "overrides/doctor-trilhas-online": "88715ff3a22309121d336d5f50195f289e8a24f93f00717ef1b0e124d0df4791",
    "update/seguir": "bef9d26ca5cccb507cb07e69815caf2e6fd885bf528e3fa38a2d482b9fc7e74d",
    "update/fixar": "9052dda829183872612f1e29e8f912e5810b29c4845b400b94b2db2cebc8bb18",
    "update/relatorio-seguir": "09ce2303adb9224f85799ddd5fd07332cf075be8383f15360ff90c2ee2c952b9",
    "update/relatorio-fixar": "be144c3cb274b68ff7aa3db4209b1d4542018c472ec104e9329c109e734fe641",
    "update/relatorio-simulado": "1b243ae0c2e83157d3d737236898a3e13e5eb15909fa584aec8d38320490e028",
    "update/overrides": "1d93349a17ae9de6085ceacc4894f5ff059654d5927dcd6bfd84d2a9143fbcaa",
}


def _normaliza(texto: str, tmp_path: Path) -> str:
    """A pasta temporária, os commits dos checkouts falsos e os pins do registro viram marcas que não mudam entre execuções."""
    for base in sorted({str(tmp_path), str(tmp_path.resolve())}, key=len, reverse=True):
        texto = texto.replace(base, "<TMP>")
    for marca in tmp_path.rglob(".fake-head"):
        sha, pasta = marca.read_text(encoding="utf-8").strip(), marca.parent.relative_to(tmp_path).as_posix()
        texto = texto.replace(sha, f"<HEAD:{pasta}>").replace(sha[:12], f"<HEAD12:{pasta}>")
    for nome, t in tools.TOOLS.items():
        texto = re.sub(rf"(?<![0-9A-Za-z.]){re.escape(t.ref)}(?![0-9A-Za-z.])", f"<PIN:{nome}>", texto)
        texto = re.sub(rf"(?<![0-9A-Za-z.]){re.escape(t.ref[:12])}(?![0-9A-Za-z])", f"<PIN12:{nome}>", texto) if len(t.ref) == 40 else texto
    texto = re.sub(rf"(?<![0-9A-Za-z.]){re.escape(__version__)}(?![0-9A-Za-z.])", "<VERSION>", texto)
    # the one deliberate change of U09 in what the user sees: the doctor's clone of the voicestudio ends the options with `--`, as tools.install
    # does (the tests of that text are test_o_doctor_mostra_o_clone_do_voicestudio_*); everything else here is byte for byte what main prints
    texto = texto.replace("git clone --filter=blob:none -- ", "git clone --filter=blob:none ")
    return texto.replace(HYPERFRAMES, "<ENGINE>")


def _confere(nome: str, texto: str, tmp_path: Path) -> None:
    texto = _normaliza(texto, tmp_path)
    pasta = os.environ.get("REGISTRO_TRILHAS_DUMP")
    if pasta:  # modo de captura: grava o texto normalizado e o sha256 e não confere (para comparar duas versões do código)
        alvo = Path(pasta) / (nome.replace("/", "__") + ".txt")
        alvo.parent.mkdir(parents=True, exist_ok=True)
        alvo.write_text(texto, encoding="utf-8")
        return
    achado = hashlib.sha256(texto.encode("utf-8")).hexdigest()
    assert achado == GOLDEN[nome], (f"{nome}: a saída mudou (sha256 {achado}). A de origin/main é {GOLDEN[nome]}; "
                                    "REGISTRO_TRILHAS_DUMP=<pasta> grava o texto normalizado para comparar")


def _cli(argv: list[str], capsys) -> str:
    rc, out, err = roda(argv, capsys)
    return f"rc={rc}\n--- stdout\n{out}--- stderr\n{err}"


def _json(doc) -> str:
    return json.dumps(doc, indent=1, ensure_ascii=False)


@posix_real
def test_a_maquina_vazia_mostra_o_mesmo_de_sempre(ambiente, capsys):
    tmp = ambiente.caixa.tmp
    _confere("vazia/tools-json", _cli(["tools", "--json"], capsys), tmp)
    _confere("vazia/tools-texto", _cli(["tools"], capsys), tmp)
    _confere("vazia/status-json", _cli(["status", "--json"], capsys), tmp)
    _confere("vazia/doctor-trilhas-json", _cli(["doctor", "trilhas", "--json"], capsys), tmp)
    _confere("vazia/doctor-trilhas-texto", _cli(["doctor", "trilhas"], capsys), tmp)


@posix_real
def test_a_maquina_saudavel_mostra_o_mesmo_de_sempre(ambiente, monkeypatch, capsys):
    monta_saudavel(ambiente, monkeypatch)
    tmp = ambiente.caixa.tmp
    _confere("saudavel/tools-json", _cli(["tools", "--json"], capsys), tmp)
    _confere("saudavel/status-json", _cli(["status", "--json"], capsys), tmp)
    _confere("saudavel/doctor-trilhas-json", _cli(["doctor", "trilhas", "--json"], capsys), tmp)
    _confere("saudavel/doctor-trilhas-texto", _cli(["doctor", "trilhas"], capsys), tmp)
    _confere("saudavel/doctor-trilhas-online", _json(dt.collect(online=True, io=_rede_em_dia().io())), tmp)
    rc, out, err = roda(["doctor", "--json"], capsys)
    linha = next(c for c in json.loads(out)["checks"] if c["name"] == "trilhas")
    _confere("saudavel/doctor-json-linha-trilhas", _json(linha), tmp)


@posix_real
def test_com_overrides_de_pin_mostra_o_mesmo_de_sempre(ambiente, monkeypatch, capsys):
    monta_saudavel(ambiente, monkeypatch)
    for var, valor in (("SIMPLICIO_OPENCUT_REF", "abcdef1"), ("SIMPLICIO_TOONFLOW_REF", "--force"), ("SIMPLICIO_HYPIT_REF", "9.9.9"),
                       ("SIMPLICIO_TINYFISH_REF", "latest"), ("SIMPLICIO_YT-DLP_REF", "2099.1.1"), ("SIMPLICIO_REA_VIDEO_REF", "1234567")):
        monkeypatch.setenv(var, valor)
    tmp = ambiente.caixa.tmp
    _confere("overrides/tools-json", _cli(["tools", "--json"], capsys), tmp)
    _confere("overrides/tools-texto", _cli(["tools"], capsys), tmp)
    _confere("overrides/doctor-trilhas-json", _cli(["doctor", "trilhas", "--json"], capsys), tmp)
    _confere("overrides/doctor-trilhas-online", _json(dt.collect(online=True, io=_rede_em_dia().io())), tmp)


@posix_real
def test_o_update_mostra_e_grava_o_mesmo_de_sempre(ambiente_update, monkeypatch):
    tmp = ambiente_update

    def captura(modo: str, nome: str, doc=None) -> None:
        lock = tmp / f"lock-{nome.replace('/', '-')}.json"
        linhas, falhas = tools_update.apply_all(doc or {"tools": {}}, modo, Fake().io(), lock)
        _confere(nome, f"falhas={falhas}\n" + "\n".join(linhas) + "\n--- lock\n" + lock.read_text(encoding="utf-8"), tmp)

    captura("follow", "update/seguir")
    captura("pin", "update/fixar")
    for modo, nome, seco in (("follow", "update/relatorio-seguir", False), ("pin", "update/relatorio-fixar", False),
                             ("follow", "update/relatorio-simulado", True)):
        _confere(nome, "\n".join(tools_update.report(modo, Fake().io(), dry=seco)), tmp)
    for var, valor in (("SIMPLICIO_OPENCUT_REF", "abcdef1"), ("SIMPLICIO_YT-DLP_REF", "2099.1.1"), ("SIMPLICIO_VIDEO-USE_REF", "x")):
        monkeypatch.setenv(var, valor)
    captura("follow", "update/overrides")


# --- parte 1b: as tabelas de hoje, congeladas por trilha ---------------------------------------------------------------------


def test_os_treze_nomes_e_a_ordem_do_registro_nao_mudam():
    assert list(tools.TOOLS) == ["openmontage", "opencut", "hypit", "toonflow", "moneyprinter", "matchcut", "instagram", "voicestudio",
                                 "video-use", "tinyfish", "yt-dlp", "rea_video", "video_to_skill"]  # the order of the JSON and of the doctor


def test_tools_commands_diz_o_comando_de_cada_trilha():
    assert tools.COMMANDS == COMANDOS
    for t in tools.TOOLS.values():
        assert tools.command(t) == f"simplicio-video {COMANDOS[t.name]}"


def test_doctor_clone_e_deps_dizem_o_que_diziam():
    assert dt.CLONE == CLONE
    assert dt.DEPS == DEPS


def test_o_pin_only_do_update_e_o_de_hoje():
    assert {n for n, t in tools.TOOLS.items() if tools_update.pin_only(t)} == PIN_ONLY


@posix_real
def test_o_smoke_so_le_o_que_lia():
    smoke = _carrega_smoke()
    assert {n: (c.funcao, c.kwargs, c.precisa, c.espera) for n, c in smoke.MCP_LEITURA.items()} == MCP_LEITURA
    assert list(smoke.MCP_LEITURA) == list(tools.TOOLS)


def _carrega_smoke():
    spec = importlib.util.spec_from_file_location("smoke_trilhas_u09", SMOKE)
    modulo = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = modulo  # dataclasses look the module up by name while the script runs
    try:
        spec.loader.exec_module(modulo)
    finally:
        sys.modules.pop(spec.name, None)
    return modulo


def test_o_ambiente_da_sonda_do_doctor_e_o_conjunto_de_hoje(monkeypatch):
    """O doctor passa à sonda `--version` o ambiente fechado do `status`: o mesmo conjunto, agora montado por `terceiros`."""
    monkeypatch.setattr(os, "environ", {n: "v:" + n for n in (*status.ENV_FERRAMENTA, "GEMINI_API_KEY", "GITHUB_TOKEN", "PYTHONPATH")})
    assert dt._ambiente() == {n: "v:" + n for n in status.ENV_FERRAMENTA}
    assert dt._ambiente() == terceiros.env_para_terceiro(status.ENV_FERRAMENTA, base=os.environ)
    assert dt.ENV_FERRAMENTA is status.ENV_FERRAMENTA  # not a ninth copy of the list


# --- parte 1c: o update nunca segue o upstream de trilha pin_only (caracterização por trilha) ---------------------------------


@pytest.mark.parametrize("nome", list(tools.TOOLS))
def test_o_update_nunca_segue_a_trilha_pin_only(nome, ambiente_update):
    t = tools.get(nome)
    fake = Fake()
    lock = ambiente_update / "lock.json"
    tools_update.apply_all({"tools": {}}, "follow", fake.io(), lock)
    entrada = tools_lock.read_lock(lock)["tools"][nome]
    consultas = fake.ran("ls-remote", t.source) + fake.ran("view", t.source)
    if nome in PIN_ONLY:
        assert entrada["mode"] == "pin" and entrada["ref"] == t.ref and entrada["status"] == "ok", entrada
        assert not consultas, "o update perguntou ao upstream de uma trilha pin-only"
    else:
        assert entrada["mode"] == "follow" and entrada["status"] == "ok", entrada
        assert consultas or (t.kind == "pip" and fake.urls), "o update não perguntou ao upstream de uma trilha que ele segue"


@pytest.mark.parametrize("nome", sorted(PIN_ONLY))
def test_o_relatorio_do_update_mantem_a_trilha_pin_only_no_pin(nome, ambiente_update):
    linha = next(x for x in tools_update.report("follow", Fake().io(), dry=False) if x.split()[0] == nome)
    assert "no pin" in linha or "fora do pin" in linha, linha
    assert "atrás" not in linha and "seguiria" not in linha


# --- parte 2: o registro ------------------------------------------------------------------------------------------------------


def test_tool_ganha_os_campos_do_registro():
    campos = {f.name: f for f in dataclasses.fields(tools.Tool)}
    for nome in ("command", "pin_only", "checkout_env", "deps", "clone_verb", "setup_probe", "integrity", "mcp_read", "checkout_probe"):
        assert nome in campos, f"Tool não tem o campo {nome}"
    assert campos["command"].default is dataclasses.MISSING, "o comando é obrigatório: trilha nova sem comando não nasce"
    assert (campos["pin_only"].default, campos["checkout_env"].default, campos["deps"].default, campos["clone_verb"].default,
            campos["setup_probe"].default, campos["integrity"].default) == (False, None, (), None, None, None)


@pytest.mark.parametrize("nome", list(tools.TOOLS))
def test_cada_trilha_declara_no_registro_o_que_as_tabelas_diziam(nome):
    t = tools.get(nome)
    assert t.command == COMANDOS[nome]
    assert t.clone_verb == (CLONE[nome].removeprefix(f"simplicio-video {COMANDOS[nome]} ") if nome in CLONE else None)
    assert [tools.parse_dep(spec) for spec in t.deps] == DEPS[nome]
    assert t.pin_only == (nome in PIN_ONLY)
    assert t.checkout_env == ("VIDEO_USE_DIR" if nome == "video-use" else None)
    assert bool(t.setup_probe) == (nome in SETUP)
    assert bool(t.integrity) == (nome in INTEGRIDADE)
    assert bool(t.checkout_probe) == (nome in CHECKOUT_PROPRIO)
    assert t.mcp_read is not None
    assert (t.kind == "git" and t.clone_verb is None) == (nome in GIT_SEM_VERBO)


def test_a_integridade_e_a_tabela_de_sha256_que_o_doctor_lia():
    from simplicio_video import matchcut, video_to_skill

    assert dt.lookup(tools.get("matchcut").integrity) is matchcut.PINNED_SHA256
    assert dt.lookup(tools.get("video_to_skill").integrity) == video_to_skill.PINS["files"]
    assert tools.get("instagram").integrity is None  # de propósito: o doctor não importa o módulo (o `instagram status` confere os scripts)


def test_lookup_le_o_atributo_na_hora_da_chamada_e_anda_por_dicionarios(monkeypatch):
    from simplicio_video import matchcut, montage

    monkeypatch.setattr(matchcut, "PINNED_SHA256", {"x": {"y": 7}})
    assert dt.lookup(("matchcut", "PINNED_SHA256")) == {"x": {"y": 7}}  # a test that replaces the table is seen
    assert dt.lookup(("matchcut", "PINNED_SHA256.x.y")) == 7
    assert dt.lookup(("montage", "default_openmontage_dir")) is montage.default_openmontage_dir
    assert dt.lookup(("doctor_trilhas", "setup_opencut")) is dt.setup_opencut
    with pytest.raises(AttributeError):
        dt.lookup(("matchcut", "NAO_EXISTE"))
    with pytest.raises(KeyError):
        dt.lookup(("matchcut", "PINNED_SHA256.x.z"))
    with pytest.raises(ImportError):
        dt.lookup(("tools_lock", "GIT_REF"))  # the doctor opens only the modules a track points to, spelled out one by one


@pytest.mark.parametrize("spec, esperado", [("ffmpeg", ("ffmpeg", True, None)), ("docker?", ("docker", False, None)),
                                            ("node>=22.15", ("node", True, (22, 15))), ("node>=24", ("node", True, (24,))),
                                            ("SIMPLICIO_TTS_PY", ("SIMPLICIO_TTS_PY", True, None)), ("ffmpeg>=6?", ("ffmpeg", False, (6,)))])
def test_parse_dep_le_nome_minimo_e_opcional(spec, esperado):
    assert tools.parse_dep(spec) == esperado


@pytest.mark.parametrize("ruim", ["", "node>=", ">=22", "node>=22.x", "no de", "node>=22>=23", "bun??", "?bun"])
def test_parse_dep_recusa_o_que_nao_e_uma_dependencia(ruim):
    with pytest.raises(ValueError):
        tools.parse_dep(ruim)


def test_uma_trilha_com_dep_mal_escrita_nao_nasce():
    t = tools.get("opencut")
    with pytest.raises(ValueError):
        dataclasses.replace(t, deps=("bun", "docker ?"))


def test_o_ref_do_registro_continua_sendo_um_campo_trocavel():
    """Os testes trocam o pin com dataclasses.replace(t, ref=...): `ref` segue sendo campo, também no video-use (cujo pin é lido sob demanda)."""
    for nome in ("opencut", "video-use"):
        t = tools.get(nome)
        outro = dataclasses.replace(t, ref="f" * 40)
        assert outro.ref == "f" * 40 and t.ref != "f" * 40 and outro.name == nome


def test_override_var_diz_o_nome_da_variavel_do_pin():
    for nome, t in tools.TOOLS.items():
        assert tools.override_var(t) == f"SIMPLICIO_{nome.upper()}_REF"
    assert tools.override_var(tools.get("yt-dlp")) == "SIMPLICIO_YT-DLP_REF"  # the hyphen stays: the variable of today


def test_os_regex_de_ref_sao_publicos_e_sao_os_de_hoje():
    assert tools_lock.GIT_REF.pattern == "[0-9a-f]{7,40}"
    assert tools_lock.VERSION.pattern == r"[0-9]+(?:\.[0-9]+){0,3}(?:[-+.][0-9A-Za-z.]{1,40})?"
    assert tools_lock.NPM_VERSION.pattern == r"[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z.-]{1,40})?"
    assert tools_lock.SHA256.pattern == "[0-9a-f]{64}"
    for nome in ("_GIT_REF", "_VERSION", "_SHA256"):
        assert not hasattr(tools_lock, nome), f"tools_lock.{nome} ficou ao lado do público"
    assert not hasattr(tools_update, "_NPM_VERSION") and not hasattr(tools_update, "_SHA256") and not hasattr(tools, "_NPM_VERSION")


# --- parte 3: a derivação -----------------------------------------------------------------------------------------------------


def _troca(monkeypatch, nome: str, **campos) -> None:
    monkeypatch.setitem(tools.TOOLS, nome, dataclasses.replace(tools.TOOLS[nome], **campos))


def test_o_comando_vem_do_campo_command(ambiente, monkeypatch):
    _troca(monkeypatch, "opencut", command="oc novo")
    assert tools.command(tools.get("opencut")) == "simplicio-video oc novo"
    assert next(r for r in tools.listing() if r["name"] == "opencut")["command"] == "simplicio-video oc novo"
    assert _trilha(dt.collect(), "opencut")["command"] == "simplicio-video oc novo"


def test_o_comando_de_clone_vem_do_campo_clone_verb(ambiente, monkeypatch):
    _troca(monkeypatch, "opencut", clone_verb="baixar")
    assert _c(_trilha(dt.collect(), "opencut"), "instalada")["fix"] == "simplicio-video opencut baixar"
    _troca(monkeypatch, "opencut", clone_verb=None)  # a git track with no verb: the git commands tools.install runs
    fix = _c(_trilha(dt.collect(), "opencut"), "instalada")["fix"]
    assert fix.startswith("git clone --filter=blob:none -- ") and f"checkout --detach {tools.pinned_ref(tools.get('opencut'))}" in fix


def test_as_dependencias_vem_do_campo_deps(ambiente, monkeypatch):
    _troca(monkeypatch, "yt-dlp", deps=("bun", "docker?", "node>=18"))
    assert [c["name"] for c in _trilha(dt.collect(), "yt-dlp")["checks"] if c["name"].startswith("dep:")] == ["dep:bun", "dep:docker", "dep:node"]
    _troca(monkeypatch, "opencut", deps=())
    assert [c["name"] for c in _trilha(dt.collect(), "opencut")["checks"] if c["name"].startswith("dep:")] == ["dep:git"]


def test_uma_dep_que_o_doctor_nao_sabe_julgar_nao_passa_calada(ambiente, monkeypatch):
    _troca(monkeypatch, "yt-dlp", deps=("lua",))
    c = _c(_trilha(dt.collect(), "yt-dlp"), "instalada")
    assert c["status"] == "warn" and "lua" in c["summary"], c  # `_avalia_seguro`: the track names the problem, the doctor goes on


def test_a_integridade_vem_do_campo_integrity(ambiente, monkeypatch):
    monta_saudavel(ambiente, monkeypatch)
    assert not [c for c in _trilha(dt.collect(), "opencut")["checks"] if c["name"] == "integridade"]
    _troca(monkeypatch, "opencut", integrity=("matchcut", "PINNED_SHA256"))  # opencut's folder has none of matchcut's files
    assert _c(_trilha(dt.collect(), "opencut"), "integridade")["status"] == "fail"
    _troca(monkeypatch, "matchcut", integrity=None)
    assert not [c for c in _trilha(dt.collect(), "matchcut")["checks"] if c["name"] == "integridade"]


def test_o_setup_vem_do_campo_setup_probe(ambiente, monkeypatch):
    monta_saudavel(ambiente, monkeypatch)
    visto = []

    def sonda(t, pasta):
        visto.append((t.name, pasta))
        return [dt._row("setup:teste", "ok", "setup de teste")]

    monkeypatch.setattr(dt, "sonda_de_teste", sonda, raising=False)
    _troca(monkeypatch, "instagram", setup_probe=("doctor_trilhas", "sonda_de_teste"))
    assert [c["name"] for c in _trilha(dt.collect(), "instagram")["checks"] if c["name"].startswith("setup:")] == ["setup:teste"]
    assert visto == [("instagram", tools.checkout_dir(tools.get("instagram")))]
    _troca(monkeypatch, "opencut", setup_probe=None)
    assert not [c for c in _trilha(dt.collect(), "opencut")["checks"] if c["name"].startswith("setup:")]


def test_a_pasta_do_checkout_vem_do_campo_checkout_probe(ambiente, monkeypatch):
    destino = tools.tools_dir()
    _troca(monkeypatch, "opencut", checkout_probe=("montage", "default_openmontage_dir"))  # montage's own search order: tools/openmontage
    assert _c(_trilha(dt.collect(), "opencut"), "instalada")["detail"]["path"] == str(destino / "openmontage")
    _troca(monkeypatch, "opencut", checkout_probe=None)
    assert _c(_trilha(dt.collect(), "opencut"), "instalada")["detail"]["path"] == str(destino / "opencut")


def test_o_pin_only_vem_do_campo_pin_only(ambiente_update, monkeypatch):
    _troca(monkeypatch, "opencut", pin_only=True)
    _troca(monkeypatch, "video_to_skill", pin_only=False)
    assert tools_update.pin_only(tools.get("opencut")) and not tools_update.pin_only(tools.get("video_to_skill"))
    fake = Fake()
    tools_update.apply_all({"tools": {}}, "follow", fake.io(), ambiente_update / "lock.json")
    lock = tools_lock.read_lock(ambiente_update / "lock.json")["tools"]
    assert lock["opencut"]["mode"] == "pin" and not fake.ran("ls-remote", tools.get("opencut").source)
    assert lock["video_to_skill"]["mode"] == "follow" and fake.ran("ls-remote", tools.get("video_to_skill").source)


@posix_real
def test_o_checkout_fora_do_cache_vem_do_campo_checkout_env(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("OPENCUT_ELSEWHERE", raising=False)
    _troca(monkeypatch, "opencut", checkout_env="OPENCUT_ELSEWHERE")
    assert tools.checkout_dir(tools.get("opencut")) == tmp_path / ".cache" / "simplicio" / "opencut"
    monkeypatch.setenv("OPENCUT_ELSEWHERE", "~/em/outro/lugar")
    assert tools.checkout_dir(tools.get("opencut")) == Path("~/em/outro/lugar")  # as bash takes it in setup.sh: no `~` expansion


def test_o_video_use_continua_fora_do_cache_de_tools(tmp_path, monkeypatch):
    monkeypatch.setenv("SIMPLICIO_TOOLS_DIR", str(tmp_path / "tools"))
    monkeypatch.setenv("VIDEO_USE_DIR", str(tmp_path / "vu"))
    t = tools.get("video-use")
    assert tools.checkout_dir(t) == tmp_path / "vu"
    monkeypatch.delenv("VIDEO_USE_DIR")
    assert tools.checkout_dir(t) == hostos.home_absoluta("VIDEO_USE_DIR") / ".cache" / "simplicio" / "video-use"


@posix_real
def test_o_smoke_deriva_a_chamada_mcp_do_campo_mcp_read(monkeypatch):
    _troca(monkeypatch, "opencut", mcp_read=tools.McpRead("args", "status", needs_checkout=False))
    _troca(monkeypatch, "yt-dlp", mcp_read=tools.McpRead("args", ("fetch", "--info"), needs_checkout=False, expect="recusa"))
    smoke = _carrega_smoke()
    c = smoke.MCP_LEITURA["opencut"]
    assert (c.funcao, c.kwargs, c.precisa, c.espera) == ("video_opencut", {"args": "status"}, False, "ok")
    assert smoke.MCP_LEITURA["yt-dlp"].kwargs == {"args": ["fetch", "--info"]} and smoke.MCP_LEITURA["yt-dlp"].espera == "recusa"


@posix_real
def test_o_smoke_recusa_trilha_sem_chamada_declarada(monkeypatch):
    _troca(monkeypatch, "opencut", mcp_read=None)
    with pytest.raises((ValueError, KeyError, SystemExit)) as erro:
        _carrega_smoke()
    assert "opencut" in str(erro.value) and "mcp_read" in str(erro.value)


def test_o_smoke_pega_o_comando_do_registro(monkeypatch):
    smoke = _carrega_smoke()
    assert tools.TOOLS["yt-dlp"].command.split()[0] == "media"
    assert smoke.tools.TOOLS is tools.TOOLS


def _trilha(doc: dict, nome: str) -> dict:
    achadas = [t for t in doc["tracks"] if t["name"] == nome]
    assert len(achadas) == 1, [t["name"] for t in doc["tracks"]]
    return achadas[0]


def _c(track: dict, nome: str) -> dict:
    achadas = [c for c in track["checks"] if c["name"] == nome]
    assert len(achadas) == 1, f"{track['name']}: {[c['name'] for c in track['checks']]}"
    return achadas[0]


# --- parte 4: paridade, um teste percorre TOOLS -------------------------------------------------------------------------------


def _grupos_do_cli() -> set:
    import argparse

    return {nome for acao in build_parser()._actions if isinstance(acao, argparse._SubParsersAction) for nome in acao.choices}


def _linhas_da_skill() -> list:
    texto = SKILL.read_text(encoding="utf-8").splitlines()
    inicio = next(i for i, linha in enumerate(texto) if linha.startswith("| Pedido"))
    corpo = []
    for linha in texto[inicio + 2:]:
        if not linha.startswith("|"):
            break
        corpo.append([c.strip() for c in linha.strip().strip("|").split("|")])
    return corpo


def lacunas(t: tools.Tool, *, so_o_registro: bool = False) -> list[str]:
    """O que falta a uma trilha de `tools.TOOLS` para que cada porta da frente a conheça (lista vazia: nada falta)."""
    faltas = []
    palavra = t.command.split()[0]
    if palavra not in _grupos_do_cli():
        faltas.append(f"o CLI não tem o comando `{palavra}`")
    mcp = f"video.{palavra}"
    if mcp not in {x["name"] for x in SNAPSHOT["tools"]}:
        faltas.append(f"o snapshot do MCP não tem a tool {mcp}")
    if mcp not in {n for n, _, _ in mcp_server.TOOLS}:
        faltas.append(f"mcp_server.TOOLS não tem a tool {mcp}")
    if not any(mcp in linha[3] and re.search(rf"\b{re.escape(t.command)}\b", linha[2]) for linha in _linhas_da_skill()):
        faltas.append(f"a skill de trilhas não tem uma linha com `{t.command}` e {mcp}")
    for spec in t.deps:
        try:
            nome = tools.parse_dep(spec)[0]
        except ValueError:
            faltas.append(f"dep ilegível: {spec!r}")
            continue
        if nome not in dt.DEP_NOMES:
            faltas.append(f"o doctor não sabe julgar a dep {nome!r}")
    if t.kind == "git" and t.clone_verb is None and t.name not in GIT_SEM_VERBO:
        faltas.append("trilha git sem clone_verb: o doctor mostraria os comandos do git; diga o verbo ou declare a exceção")
    if t.kind != "git" and t.clone_verb is not None:
        faltas.append("clone_verb só vale para trilha git")
    if t.mcp_read is None:
        faltas.append("sem mcp_read: o smoke não tem a chamada MCP de leitura")
    elif not hasattr(mcp_server, f"video_{palavra.replace('-', '_')}"):
        faltas.append(f"mcp_server não tem video_{palavra.replace('-', '_')} (a função que o smoke chama)")
    for rotulo, ponteiro in (("setup_probe", t.setup_probe), ("integrity", t.integrity), ("checkout_probe", t.checkout_probe)):
        if ponteiro is not None:
            try:
                dt.lookup(ponteiro)
            except (ImportError, AttributeError, KeyError) as exc:
                faltas.append(f"{rotulo} {ponteiro} não resolve: {exc}")
    if t.pin_only and t.kind == "pip":
        faltas.append("pin_only em trilha pip: o pin_target já leva o sha256, mas nenhuma trilha pip é pin-only hoje")
    if not so_o_registro and not isinstance(t.deps, tuple):
        faltas.append("deps precisa ser uma tupla")
    return faltas


@pytest.mark.parametrize("nome", list(tools.TOOLS))
def test_toda_trilha_do_registro_e_conhecida_por_todas_as_portas(nome):
    assert lacunas(tools.get(nome)) == []


@pytest.mark.parametrize("nome", list(tools.TOOLS))
def test_o_doctor_conhece_cada_trilha_do_registro(nome, ambiente):
    t = tools.get(nome)
    track = _trilha(dt.collect(), nome)
    assert track["command"] == f"simplicio-video {t.command}"
    assert _c(track, "instalada")["fix"] == (dt._clone_de(t, tools.pinned_ref(t)))
    assert [c["name"] for c in track["checks"] if c["name"].startswith("dep:")] == [
        *(["dep:git"] if t.kind == "git" else []), *(f"dep:{tools.parse_dep(s)[0]}" for s in t.deps),
        *(["dep:npx"] if t.npx else [])]


def test_o_teste_de_paridade_pega_uma_trilha_incompleta():
    """Sem este teste a paridade poderia passar vazia: uma trilha nova que só declarou o mínimo tem de aparecer cheia de lacunas."""
    novo = tools.Tool("novo", "git", "https://github.com/x/novo", "a" * 40, "MIT", "faz coisas", command="novo", deps=("zzz",))
    achadas = " | ".join(lacunas(novo))
    for esperado in ("o CLI não tem o comando `novo`", "o snapshot do MCP não tem a tool video.novo", "mcp_server.TOOLS não tem a tool video.novo",
                     "a skill de trilhas não tem uma linha", "o doctor não sabe julgar a dep 'zzz'", "trilha git sem clone_verb",
                     "sem mcp_read"):
        assert esperado in achadas, (esperado, achadas)


def test_os_defaults_silenciosos_de_hoje_estao_declarados_no_registro():
    """Defaults que deixavam passar (achados em origin/main): o `else` de `_clone_de` (mensagem do yt-dlp para qualquer trilha sem clone),
    o `return []` de `_setup`, o `None` de `_tabela_fixada`, `DEPS.get(t.name, [])`, `COMMANDS.get(nome, nome)`, o SKIP 'sem chamada
    MCP' do smoke. Agora cada um é um campo do registro; os que ficam vazios são exceções ESCRITAS aqui."""
    git = {n for n, t in tools.TOOLS.items() if t.kind == "git"}
    assert {n for n in git if tools.get(n).clone_verb is None} == GIT_SEM_VERBO
    assert {n for n in git if tools.get(n).setup_probe is None} == git - SETUP == {"instagram", "voicestudio", "video-use"}
    assert {n for n in git if tools.get(n).integrity is None} == git - INTEGRIDADE
    assert {n for n, t in tools.TOOLS.items() if not t.deps} == {"instagram"}
    assert {n for n, t in tools.TOOLS.items() if t.kind == "pip"} == {"yt-dlp"}  # `_clone_de` ends in the message of the only pip track
    assert {n for n, t in tools.TOOLS.items() if t.kind == "npm"} == {"hypit", "tinyfish"}
    assert {n for n, t in tools.TOOLS.items() if t.mcp_read is None} == set()


# --- parte 5: o resto da ficha ------------------------------------------------------------------------------------------------


def test_importar_tools_nao_le_o_setup_sh_do_video_use(tmp_path):
    """Hoje `_video_use_pin()` roda no import de tools: sem o setup.sh nem o `--help` funciona. Agora só o video-use usado falha."""
    codigo = textwrap.dedent("""
        import sys, tempfile, pathlib
        from simplicio_video import paths
        paths.DATA_DIR = pathlib.Path(tempfile.mkdtemp())          # nenhum tools/video-use/setup.sh aqui
        from simplicio_video import cli, tools
        try:
            cli.main(["--help"])
        except SystemExit as exc:
            print("help rc", exc.code)
        print("opencut", tools.get("opencut").ref)
        print("lista", [t.name for t in tools.TOOLS.values()][-5:])
        try:
            tools.get("video-use").ref
        except Exception as exc:
            print("video-use", type(exc).__name__)
        else:
            print("video-use leu o pin sem o setup.sh")
    """)
    r = subprocess.run([sys.executable, "-c", codigo], capture_output=True, text=True, timeout=60,
                       env={**os.environ, "SIMPLICIO_OFFLINE": "1"})
    assert r.returncode == 0, r.stderr[-800:]
    assert "help rc 0" in r.stdout and f"opencut {tools.get('opencut').ref}" in r.stdout, r.stdout + r.stderr[-400:]
    assert re.search(r"video-use (FileNotFoundError|RuntimeError|OSError)", r.stdout), r.stdout


def test_o_pin_do_video_use_e_lido_uma_vez_e_fica_em_cache(monkeypatch):
    tools._video_use_pin.cache_clear()
    lidas = []
    original = Path.read_text

    def le(self, *a, **kw):
        if self.name == "setup.sh":
            lidas.append(self)
        return original(self, *a, **kw)

    monkeypatch.setattr(Path, "read_text", le)
    ref = tools.get("video-use").ref
    assert tools.get("video-use").ref == ref == tools._video_use_pin() and len(lidas) == 1, lidas
    tools._video_use_pin.cache_clear()


def test_o_ref_do_video_use_continua_sendo_o_vu_ref_do_setup_sh():
    vu = re.search(r"^VU_REF=([0-9a-f]{40})\b", SETUP_SH.read_text(encoding="utf-8"), re.MULTILINE).group(1)
    assert tools.get("video-use").ref == vu == tools.pinned_ref(tools.get("video-use"))


def _importados(arquivo: Path) -> set:
    achados = set()
    for no in ast.walk(ast.parse(arquivo.read_text(encoding="utf-8"))):
        if isinstance(no, ast.ImportFrom):
            achados |= {a.name for a in no.names} | ({no.module} if no.module else set())
        elif isinstance(no, ast.Import):
            achados |= {a.name for a in no.names}
    return achados


def test_tools_nao_importa_tools_update_o_ciclo_acabou():
    assert "tools_update" not in _importados(SRC / "tools.py")
    assert "tools" in _importados(SRC / "tools_update.py")  # the one direction left
    assert "tools_update" not in _importados(SRC / "tools_lock.py") and "tools" not in _importados(SRC / "tools_lock.py")


def _privados_de_outros(arquivo: Path, modulos=("tools", "tools_lock", "tools_update")) -> list:
    return sorted({f"{no.value.id}.{no.attr}" for no in ast.walk(ast.parse(arquivo.read_text(encoding="utf-8")))
                   if isinstance(no, ast.Attribute) and no.attr.startswith("_") and not no.attr.startswith("__")
                   and isinstance(no.value, ast.Name) and no.value.id in modulos and no.value.id != arquivo.stem})


@pytest.mark.parametrize("modulo", ["tools", "tools_update", "tools_lock", "doctor_trilhas"])
def test_nenhum_privado_de_tools_tools_lock_ou_tools_update_e_usado_de_fora(modulo):
    assert _privados_de_outros(SRC / f"{modulo}.py") == []


def test_o_doctor_monta_o_ambiente_com_terceiros_e_roda_o_git_pelo_nome_publico():
    texto = (SRC / "doctor_trilhas.py").read_text(encoding="utf-8")
    assert "env_para_terceiro" in _importados(SRC / "doctor_trilhas.py") or "terceiros" in _importados(SRC / "doctor_trilhas.py")
    assert "tools._git" not in texto and "ENV_FERRAMENTA if k in os.environ" not in texto


def _tabelas_por_trilha() -> list:
    """O que `metrics.py` do plano mede: coleção literal no topo de um módulo (src e scripts) que nomeia 4 trilhas ou mais."""
    nomes = {*tools.TOOLS, "rea-video", "video-to-skill", "montage", "match-cut", "clone", "busca", "edit", "media"}
    achadas = []
    for base in (SRC, ROOT / "scripts"):
        for arquivo in sorted(base.rglob("*.py")):
            if "__pycache__" in arquivo.parts or "kit_gpu" in arquivo.parts:
                continue
            for no in ast.parse(arquivo.read_text(encoding="utf-8")).body:
                if isinstance(no, (ast.Assign, ast.AnnAssign)) and isinstance(no.value, (ast.Dict, ast.Tuple, ast.List, ast.Set)):
                    textos = {c.value for c in ast.walk(no.value) if isinstance(c, ast.Constant) and isinstance(c.value, str)}
                    if len(textos & nomes) >= 4:
                        alvo = no.targets[0] if isinstance(no, ast.Assign) else no.target
                        achadas.append(f"{arquivo.relative_to(ROOT).as_posix()} {getattr(alvo, 'id', '?')}")
    return achadas


def test_so_o_registro_lista_as_trilhas_por_nome():
    """Hoje são 5 (TOOLS, COMMANDS, CLONE, DEPS, MCP_LEITURA); o resto é derivado (dict por compreensão, que não conta)."""
    assert _tabelas_por_trilha() == ["src/simplicio_video/tools.py TOOLS"]


# --- o `git clone` sem `--` que ainda sobrava ---------------------------------------------------------------------------------


def test_o_doctor_mostra_o_clone_do_voicestudio_com_dois_tracos(ambiente):
    """`doctor_trilhas.py:203` imprimia `git clone --filter=blob:none <src> <dir>`: uma pasta relativa que começa com `-` virava opção."""
    t = tools.get("voicestudio")
    fix = _c(_trilha(dt.collect(), "voicestudio"), "instalada")["fix"]
    destino = shlex.quote(str(tools.checkout_dir(t)))
    assert fix == (f"git clone --filter=blob:none -- {t.source} {destino} && git -C {destino} checkout --detach {tools.pinned_ref(t)}")


def test_o_doctor_mostra_o_clone_do_voicestudio_certo_ate_numa_pasta_que_comeca_com_traco(ambiente, monkeypatch):
    monkeypatch.setenv("SIMPLICIO_TOOLS_DIR", "-x")
    fix = _c(_trilha(dt.collect(), "voicestudio"), "instalada")["fix"]
    assert " -- " in fix.split(" && ")[0] and fix.split(" && ")[0].endswith(" -x/voicestudio"), fix


def _script_com_git_falso(tmp_path: Path, vu_dir: str) -> subprocess.CompletedProcess:
    """Roda o setup.sh de verdade com um `git` que só anota os argumentos (nenhuma rede), um ffmpeg e um python falsos."""
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    (bin_ / "git").write_text(f'#!/bin/sh\nprintf "%s\\n" "$*" >> "{tmp_path / "git.log"}"\nexit 0\n', encoding="utf-8")
    (bin_ / "ffmpeg").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    python = tmp_path / "python"
    python.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    for arquivo in (bin_ / "git", bin_ / "ffmpeg", python):
        arquivo.chmod(0o755)
    env = {"PATH": f"{bin_}{os.pathsep}{os.environ['PATH']}", "HOME": str(tmp_path / "home"), "VIDEO_USE_DIR": vu_dir,
           "SIMPLICIO_TTS_PY": str(python)}
    bash = shutil.which("bash")
    assert bash
    return subprocess.run([bash, str(SETUP_SH), "--quiet"], cwd=cwd, env=env, capture_output=True, text=True, timeout=60)


@posix_real
def test_o_setup_sh_clona_com_dois_tracos_e_aguenta_uma_pasta_que_comeca_com_traco(tmp_path):
    """`git clone -q "$VU_REPO" "$VU_DIR"` (setup.sh:27) sem `--`; e `mkdir -p "$(dirname "$VU_DIR")"` na mesma linha lia `-vu` como opção."""
    r = _script_com_git_falso(tmp_path, "-vu/checkout")
    assert r.returncode == 0, r.stderr
    comandos = (tmp_path / "git.log").read_text(encoding="utf-8").splitlines()
    assert comandos[0] == "clone -q -- https://github.com/browser-use/video-use -vu/checkout", comandos
    assert (tmp_path / "cwd" / "-vu").is_dir()


@posix_real
def test_o_setup_sh_todo_git_clone_separa_as_opcoes_dos_argumentos():
    linhas = [linha for linha in SETUP_SH.read_text(encoding="utf-8").splitlines() if re.search(r"\bgit clone\b", linha) and not linha.lstrip().startswith("#")]
    assert linhas and all(re.search(r"git clone (?:-\S+ )* ?-- ", linha) for linha in linhas), linhas


@posix_real
def test_o_setup_sh_com_pasta_comum_faz_o_mesmo_de_sempre(tmp_path):
    r = _script_com_git_falso(tmp_path, str(tmp_path / "vu"))
    assert r.returncode == 0, r.stderr
    comandos = (tmp_path / "git.log").read_text(encoding="utf-8").splitlines()
    assert comandos[0] == f"clone -q -- https://github.com/browser-use/video-use {tmp_path / 'vu'}"
    assert r.stdout.strip() == f"{tmp_path / 'vu'}/helpers"
