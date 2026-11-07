"""U08b, tracks of the second batch (matchcut, instagram, montage, video_to_skill) on top of `trilha_base`.

Same story as the first batch (tests/test_trilhas_lote1.py): each module carries its own copy of what `trilha_base.Trilha` does (find the
checkout, clone it, the data folder, the commit really in the checkout, the private cwd of a job) and clones by WRITING `<NAME>_DIR` into
the environment of the whole process and putting it back (`_checkout_at`). matchcut and video_to_skill take `_offline` from toonflow;
montage and instagram parse SIMPLICIO_OFFLINE on their own.

Green today (and it has to stay green): what the tracks answer, byte for byte (the offline refusal of each, the errors, the names a test
replaces, the private folder of a video-to-skill job, the warning of montage for a relative data folder, the whole order in which montage
looks for the OpenMontage folder). Red until the migration: the declaration `T`, `_checkout_at` gone, the folder handed to
`tools.install(dir=)` with the environment untouched, the aliases that now come from `rede`, the helpers that now come from
`terceiros`, no write to `os.environ` and no call to the private `tools._git`, the dead `montage._RESULT_DIR` and the unused `nome`
argument of matchcut's `_confere_entrada`.

NOT migrated here, on purpose: `chave` and `dentro` (the AST copies of instagram, matchcut and video_to_skill). The tests of
tests/test_terceiros.py and tests/test_instagram.py replace the `CASE_INSENSITIVE` of each module and call that module's `_chave` and
`_dentro`: a shared function reads one flag only. They move to `terceiros` together with `_lugar_proibido` (U22a).
"""
from __future__ import annotations

import ast
import importlib
import inspect
import os
import re
import tempfile
import time
from pathlib import Path

import pytest

from simplicio_video import hostos, rede, terceiros, tools, trilha_base

# the module, the clone function, its error, the variable of the checkout, of the data, the function that finds the checkout and the
# name of the track in tools.TOOLS (it is not always the module's: montage is "openmontage")
TRILHAS = {
    "matchcut": ("matchcut", "clone_matchcut", "MatchcutError", "MATCHCUT_DIR", "MATCHCUT_DATA_DIR", "find_matchcut_dir", "matchcut"),
    "instagram": ("instagram", "clone_instagram", "InstagramError", "INSTAGRAM_DIR", None, "find_instagram_dir", "instagram"),
    "montage": ("montage", "clone_openmontage", "MontageError", "OPENMONTAGE_DIR", "OPENMONTAGE_DATA_DIR", "find_openmontage_dir",
                "openmontage"),
    "video_to_skill": ("video_to_skill", "clone", "VideoToSkillError", "VIDEO_TO_SKILL_DIR", None, "checkout", "video_to_skill"),
}

# what each clone says in offline mode, byte for byte (the opening is rede.PREFIXO_OFFLINE; the rest is the track's own)
RECUSA_OFFLINE = {
    "matchcut": ("modo offline (SIMPLICIO_OFFLINE=1): não vou clonar o match-cut. "
                 "Rode `simplicio-video matchcut clone` fora do modo offline ou aponte MATCHCUT_DIR para um checkout."),
    "instagram": ("modo offline (SIMPLICIO_OFFLINE=1): não vou clonar o instagram-agent-skill. "
                  "Rode `simplicio-video instagram clone` fora do modo offline ou aponte INSTAGRAM_DIR para um checkout."),
    "montage": ("modo offline (SIMPLICIO_OFFLINE=1): não vou clonar o OpenMontage. "
                "Instale fora do modo offline com `simplicio-video montage clone` ou aponte OPENMONTAGE_DIR para um checkout."),
    "video_to_skill": ("modo offline (SIMPLICIO_OFFLINE=1): não vou clonar o video-to-skill. "
                       "Rode `simplicio-video video-to-skill clone` fora do modo offline ou aponte VIDEO_TO_SKILL_DIR para um checkout."),
}
FONTES = {nome: Path(importlib.import_module(f"simplicio_video.{TRILHAS[nome][0]}").__file__) for nome in TRILHAS}


def _modulo(nome: str):
    return importlib.import_module(f"simplicio_video.{TRILHAS[nome][0]}")


def _clone(nome: str):
    return getattr(_modulo(nome), TRILHAS[nome][1])


def _erro(nome: str):
    return getattr(_modulo(nome), TRILHAS[nome][2])


def _tool(nome: str) -> str:
    return TRILHAS[nome][6]


@pytest.fixture(autouse=True)
def _ambiente(monkeypatch, tmp_path):
    """No real home, tools folder or data folder reaches a test, and no variable of a track or of the network policy is set."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "home"))
    monkeypatch.setenv("SIMPLICIO_TOOLS_DIR", str(tmp_path / "tools"))
    monkeypatch.setenv("SIMPLICIO_VIDEO_DATA", str(tmp_path / "data"))
    monkeypatch.delenv("SIMPLICIO_OFFLINE", raising=False)
    for _, _, _, env_dir, env_data, _, _ in TRILHAS.values():
        monkeypatch.delenv(env_dir, raising=False)
        monkeypatch.delenv(f"SIMPLICIO_{env_dir}", raising=False)
        if env_data:
            monkeypatch.delenv(env_data, raising=False)


class _Install:
    """A stand-in for `tools.install` that takes the folder the way the new interface does, and records what it saw: the name, the
    `dir` (None when the caller gave none), the variables of the environment that moment, and whether it was given anything else."""

    def __init__(self, devolve: str):
        self.devolve = devolve
        self.chamadas: list[tuple[str, object, dict]] = []

    def __call__(self, name, **kw):
        assert set(kw) <= {"dir"}, kw
        self.chamadas.append((name, kw.get("dir"), dict(os.environ)))
        return str(kw["dir"]) if kw.get("dir") is not None else self.devolve


def _pouso(monkeypatch, tmp_path) -> _Install:
    falso = _Install(str(tmp_path / "padrao"))
    monkeypatch.setattr(tools, "install", falso)
    return falso


def _nao_chama(*a, **k):
    pytest.fail("tools.install não devia ser chamado neste caso")


# ---- the declaration -------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("nome", sorted(TRILHAS))
def test_cada_modulo_declara_a_sua_trilha_em_T(nome):
    _, _, _, env_dir, env_data, _, tool = TRILHAS[nome]
    assert _modulo(nome).T == trilha_base.Trilha(tool, env_dir, env_data)


@pytest.mark.parametrize("nome", sorted(TRILHAS))
def test_o_checkout_at_que_mutava_o_ambiente_nao_existe_mais(nome):
    assert not hasattr(_modulo(nome), "_checkout_at")


# ---- clone: the environment of the process is never written ---------------------------------------------------------------


@pytest.mark.parametrize("nome", sorted(TRILHAS))
def test_depois_do_clone_o_ambiente_e_o_que_era(monkeypatch, tmp_path, nome):
    """Green today: the old `_checkout_at` puts the variable back. What it never did is stay out of the environment while it ran."""
    _pouso(monkeypatch, tmp_path)
    antes = dict(os.environ)
    _clone(nome)(tmp_path / "meu")
    assert dict(os.environ) == antes
    assert os.environ.get(TRILHAS[nome][3]) is None


@pytest.mark.parametrize("nome", sorted(TRILHAS))
def test_o_clone_de_verdade_numa_pasta_clona_nela_e_deixa_o_ambiente_como_estava(monkeypatch, tmp_path, nome):
    """The real `tools.install` (only git is replaced): the clone lands in the folder asked for and nothing is left in the environment."""
    comandos = []
    monkeypatch.setattr(tools, "_git", lambda *a, cwd=None: comandos.append((a, cwd)) or "")
    antes = dict(os.environ)
    alvo = tmp_path / "meu"
    assert _clone(nome)(alvo) == alvo
    assert comandos[0][0][:3] == ("clone", "--filter=blob:none", "--") and comandos[0][0][-1] == str(alvo)
    assert comandos[-1][0][:3] == ("checkout", "--quiet", "--detach") and comandos[-1][1] == alvo
    assert dict(os.environ) == antes


@pytest.mark.parametrize("nome", sorted(TRILHAS))
def test_o_clone_numa_pasta_passa_a_pasta_a_tools_install_e_nao_escreve_variavel_nenhuma(monkeypatch, tmp_path, nome):
    """The folder reaches `tools.install` as `dir=`, and at that moment the environment is what it was: another thread that reads
    `<NAME>_DIR` while the clone runs must not see the target."""
    falso = _pouso(monkeypatch, tmp_path)
    antes = dict(os.environ)
    alvo = tmp_path / "meu"
    assert _clone(nome)(alvo) == alvo
    assert [(n, d) for n, d, _ in falso.chamadas] == [(_tool(nome), alvo)]
    assert falso.chamadas[0][2] == antes


@pytest.mark.parametrize("nome", sorted(TRILHAS))
def test_o_clone_expande_o_til_da_pasta(monkeypatch, tmp_path, nome):
    falso = _pouso(monkeypatch, tmp_path)
    assert _clone(nome)(Path("~/lote2")) == tmp_path / "home" / "lote2"
    assert [(n, d) for n, d, _ in falso.chamadas] == [(_tool(nome), tmp_path / "home" / "lote2")]


@pytest.mark.parametrize("nome", ["matchcut", "instagram", "video_to_skill"])
def test_o_clone_sem_pasta_chama_tools_install_so_com_o_nome(monkeypatch, tmp_path, nome):
    """Green: no folder, the location is the one `tools.checkout_dir` decides, so `tools.install` gets the name and nothing else."""
    vistas = []

    def falso(name, **kw):
        vistas.append((name, kw))
        return str(tmp_path / "padrao")

    monkeypatch.setattr(tools, "install", falso)
    assert _clone(nome)() == tmp_path / "padrao"
    assert vistas == [(_tool(nome), {})]


def test_o_clone_do_montage_sem_pasta_leva_a_pasta_que_o_montage_procura(monkeypatch, tmp_path):
    """montage looks for the OpenMontage folder in its own order (`default_openmontage_dir`, see below), which is not the one of
    `tools.checkout_dir`: with only SIMPLICIO_VIDEO_DATA set, the clone goes there. Today it is told through the environment; after, as `dir=`."""
    monkeypatch.delenv("SIMPLICIO_TOOLS_DIR")
    falso = _pouso(monkeypatch, tmp_path)
    esperado = tmp_path / "data" / "tools" / "openmontage"
    assert _modulo("montage").default_openmontage_dir() == esperado
    assert _clone("montage")() == esperado
    assert [(n, d) for n, d, _ in falso.chamadas] == [("openmontage", esperado)]


@pytest.mark.parametrize("alvo", [None, "meu"])
@pytest.mark.parametrize("nome", sorted(TRILHAS))
def test_um_tool_error_do_install_vira_o_erro_da_trilha_com_a_mesma_mensagem(monkeypatch, tmp_path, nome, alvo):
    def falho(name, **kw):
        raise tools.ToolError("git clone: sem espaço no disco")

    monkeypatch.setattr(tools, "install", falho)
    with pytest.raises(_erro(nome)) as caught:
        _clone(nome)(tmp_path / alvo if alvo else None)
    assert str(caught.value) == "git clone: sem espaço no disco"
    assert caught.value.__suppress_context__ is True  # `from None`: the user reads the message, not a chain


@pytest.mark.parametrize("nome", ["matchcut", "instagram", "montage"])
def test_outro_erro_do_install_passa_sem_virar_erro_da_trilha(monkeypatch, tmp_path, nome):
    """Only ToolError is caught, today and after: an OSError is not turned into the track's error (video_to_skill is the exception)."""
    def falho(name, **kw):
        raise OSError("disco cheio")

    monkeypatch.setattr(tools, "install", falho)
    with pytest.raises(OSError, match="disco cheio"):
        _clone(nome)(tmp_path / "meu")


def test_o_montage_sem_casa_para_clonar_deixa_a_recusa_do_hostos_subir_ao_cli(monkeypatch):
    """`hostos.SemCasa` is not a ToolError: it goes up to cli.main (one clean message, exit 2), as the comment in the code says."""
    for var in ("HOME", "USERPROFILE", "SIMPLICIO_VIDEO_DATA", "SIMPLICIO_TOOLS_DIR"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: (_ for _ in ()).throw(RuntimeError("Could not determine home directory."))))
    monkeypatch.setattr(tools, "install", _nao_chama)
    with pytest.raises(hostos.SemCasa, match="SIMPLICIO_VIDEO_DATA"):
        _clone("montage")()


# ---- video_to_skill: the clone also catches an OSError ---------------------------------------------------------------------


@pytest.mark.parametrize("alvo", [None, "meu"])
def test_video_to_skill_clone_transforma_oserror_do_install_na_recusa_limpa(monkeypatch, tmp_path, alvo):
    def sem_git(name, **kw):
        raise FileNotFoundError(2, "No such file or directory", "git")

    monkeypatch.setattr(tools, "install", sem_git)
    with pytest.raises(_erro("video_to_skill")) as caught:
        _clone("video_to_skill")(tmp_path / alvo if alvo else None)
    assert str(caught.value) == "clone: não consegui rodar o git ou gravar o checkout: No such file or directory"
    assert caught.value.__suppress_context__ is True


def test_video_to_skill_clone_sem_strerror_diz_o_nome_da_excecao(monkeypatch):
    def quebrado(name, **kw):
        raise OSError()

    monkeypatch.setattr(tools, "install", quebrado)
    with pytest.raises(_erro("video_to_skill")) as caught:
        _clone("video_to_skill")()
    assert str(caught.value) == "clone: não consegui rodar o git ou gravar o checkout: OSError"


# ---- clone: offline --------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("valor", ["1", "true", "YES", " On "])
@pytest.mark.parametrize("nome", sorted(TRILHAS))
def test_a_recusa_offline_do_clone_e_a_mesma_byte_a_byte(monkeypatch, nome, valor):
    monkeypatch.setenv("SIMPLICIO_OFFLINE", valor)
    monkeypatch.setattr(tools, "install", _nao_chama)
    with pytest.raises(_erro(nome)) as caught:
        _clone(nome)()
    assert str(caught.value) == RECUSA_OFFLINE[nome]
    assert str(caught.value).startswith(rede.PREFIXO_OFFLINE)


@pytest.mark.parametrize("nome", sorted(TRILHAS))
def test_a_recusa_offline_vale_tambem_para_o_clone_numa_pasta(monkeypatch, tmp_path, nome):
    monkeypatch.setenv("SIMPLICIO_OFFLINE", "1")
    monkeypatch.setattr(tools, "install", _nao_chama)
    with pytest.raises(_erro(nome)) as caught:
        _clone(nome)(tmp_path / "meu")
    assert str(caught.value) == RECUSA_OFFLINE[nome]


@pytest.mark.parametrize("valor", ["0", "false", "no", "off", "", "talvez"])
@pytest.mark.parametrize("nome", sorted(TRILHAS))
def test_fora_do_modo_offline_o_clone_segue_para_o_install(monkeypatch, tmp_path, nome, valor):
    monkeypatch.setenv("SIMPLICIO_OFFLINE", valor)
    falso = _pouso(monkeypatch, tmp_path)
    _clone(nome)()
    assert [n for n, _, _ in falso.chamadas] == [_tool(nome)]


@pytest.mark.parametrize("nome", sorted(TRILHAS))
def test_o_codigo_chama_o_alias_offline_do_modulo_e_o_monkeypatch_vale(monkeypatch, tmp_path, nome):
    """`_offline` stays a name of the module and the clone calls THAT name, so a test that replaces it still decides (both ways)."""
    mod = _modulo(nome)
    monkeypatch.setattr(mod, "_offline", lambda: True)
    monkeypatch.setattr(tools, "install", _nao_chama)
    with pytest.raises(_erro(nome)) as caught:
        _clone(nome)()
    assert str(caught.value) == RECUSA_OFFLINE[nome]
    monkeypatch.setenv("SIMPLICIO_OFFLINE", "1")
    monkeypatch.setattr(mod, "_offline", lambda: False)
    falso = _pouso(monkeypatch, tmp_path)
    _clone(nome)()
    assert [n for n, _, _ in falso.chamadas] == [_tool(nome)]


@pytest.mark.parametrize("valor,esperado", [("1", True), (" On ", True), ("TRUE", True), ("yes", True), ("0", False), ("", False),
                                            ("talvez", False)])
@pytest.mark.parametrize("nome", sorted(TRILHAS))
def test_offline_le_a_variavel_sem_ligar_para_espaco_e_caixa(monkeypatch, nome, valor, esperado):
    monkeypatch.setenv("SIMPLICIO_OFFLINE", valor)
    assert _modulo(nome)._offline() is esperado


@pytest.mark.parametrize("nome", sorted(TRILHAS))
def test_offline_vem_de_rede_e_nao_do_toonflow(nome):
    assert _modulo(nome)._offline is rede.offline


@pytest.mark.parametrize("nome", ["matchcut", "video_to_skill"])
def test_matchcut_e_video_to_skill_nao_importam_nomes_privados_do_toonflow(nome):
    assert "from .toonflow" not in FONTES[nome].read_text(encoding="utf-8")


def test_a_recusa_offline_do_setup_de_cada_trilha_continua_a_mesma(monkeypatch, tmp_path):
    """The other refusals that the alias `_offline` decides (their text is the track's own and does not move)."""
    monkeypatch.setenv("SIMPLICIO_OFFLINE", "1")
    from simplicio_video import matchcut, video_to_skill
    with pytest.raises(matchcut.MatchcutError) as mc:
        matchcut._setup([])
    assert str(mc.value) == ("modo offline (SIMPLICIO_OFFLINE=1): não vou criar o venv do match-cut, porque o pip precisa de rede. "
                             "Rode `simplicio-video matchcut setup` fora do modo offline.")
    monkeypatch.setattr(video_to_skill, "find_binary", lambda: None)
    monkeypatch.setattr(video_to_skill, "platform_asset", lambda *a: {"platform": "linux-x86_64"})
    with pytest.raises(video_to_skill.VideoToSkillError) as vts:
        video_to_skill._setup([])
    assert str(vts.value) == ("modo offline (SIMPLICIO_OFFLINE=1): não vou baixar o vts-extract. "
                              "Rode `simplicio-video video-to-skill setup` fora do modo offline.")


# ---- the names a test replaces stay names of the module, and the code calls them -------------------------------------------

ALIASES = {
    "matchcut": ("_offline", "find_matchcut_dir", "data_dir", "venv_python", "clone_matchcut", "_call", "_matar", "_real",
                 "_commit_do_checkout"),
    "instagram": ("_offline", "find_instagram_dir", "clone_instagram", "_matar", "_commit_do_checkout"),
    "montage": ("_offline", "find_openmontage_dir", "default_openmontage_dir", "ensure_openmontage_dir", "data_dir", "venv_python",
                "clone_openmontage", "_run_open", "_run_step"),
    "video_to_skill": ("_offline", "checkout", "_checkout_head", "clone", "make_job_cwd", "drop_job_cwd", "_platform", "_download",
                       "_urlopen", "_real"),
}


@pytest.mark.parametrize("nome", sorted(ALIASES))
def test_os_nomes_que_os_testes_trocam_continuam_no_modulo(nome):
    for alias in ALIASES[nome]:
        assert callable(getattr(_modulo(nome), alias, None)), f"{nome}.{alias}"


def test_o_alias_de_find_do_matchcut_e_chamado_pelo_where(monkeypatch, tmp_path, capsys):
    from simplicio_video import matchcut
    onde = tmp_path / "meu-checkout"
    onde.mkdir()
    monkeypatch.setattr(matchcut, "find_matchcut_dir", lambda: onde)
    assert matchcut.run_matchcut(["where"]) == 0
    assert capsys.readouterr().out.strip() == str(onde / "SKILL.md")


def test_o_alias_de_find_do_instagram_e_chamado_pelo_where(monkeypatch, tmp_path):
    from simplicio_video import instagram
    onde = tmp_path / "meu-checkout"
    monkeypatch.setattr(instagram, "find_instagram_dir", lambda: onde)
    assert instagram.where_info() == {"checkout": str(onde), "skills": str(onde / "skills")}


def test_o_alias_de_find_do_montage_e_chamado_pelo_ensure(monkeypatch, tmp_path):
    from simplicio_video import montage
    onde = tmp_path / "meu-checkout"
    monkeypatch.setattr(montage, "find_openmontage_dir", lambda: onde)
    monkeypatch.setattr(montage, "clone_openmontage", lambda *a: pytest.fail("há checkout: não clona"))
    assert montage.ensure_openmontage_dir() == onde


def test_o_alias_de_find_e_de_checkout_head_do_video_to_skill_sao_os_que_o_status_usa(monkeypatch, tmp_path):
    from simplicio_video import video_to_skill
    onde = tmp_path / "meu-checkout"
    monkeypatch.setattr(video_to_skill, "checkout", lambda: onde)
    monkeypatch.setattr(video_to_skill, "_checkout_head", lambda d: "a" * 40)
    info = video_to_skill._checkout_info()
    assert info["installed"] is True and info["path"] == str(onde) and info["commit"] == "a" * 40
    assert info["matches_pin"] is False
    monkeypatch.setattr(video_to_skill, "_checkout_head", lambda d: None)
    assert video_to_skill._checkout_info()["matches_pin"] is None
    monkeypatch.setattr(video_to_skill, "checkout", lambda: None)
    assert video_to_skill._checkout_info()["installed"] is False


@pytest.mark.parametrize("nome", ["matchcut", "instagram", "video_to_skill"])
def test_find_acha_o_checkout_de_tools_find(tmp_path, nome):
    t = tools.get(_tool(nome))
    d = tmp_path / "tools" / _tool(nome)
    (d / t.marker).parent.mkdir(parents=True)
    (d / t.marker).write_text("{}\n", encoding="utf-8")
    assert getattr(_modulo(nome), TRILHAS[nome][5])() == tools.find(_tool(nome)) == d.resolve()


# ---- montage: where it looks for the OpenMontage folder, in this order ----------------------------------------------------
# (`find_openmontage_dir` is NOT `tools.find`: with only SIMPLICIO_VIDEO_DATA set it looks in $SIMPLICIO_VIDEO_DATA/tools/openmontage,
# where tools.checkout_dir would look in ~/.simplicio-video/tools. So it does not become `T.find()`; this table is what any rewrite keeps.)

MARCADOR = tools.get("openmontage").marker


def _com_marcador(pasta: Path) -> Path:
    (pasta / MARCADOR).mkdir(parents=True, exist_ok=True)
    return pasta


def _om():
    return _modulo("montage")


@pytest.fixture
def ordem(monkeypatch, tmp_path):
    """The five places, each one with a real OpenMontage in it, and none of the five variables set: a test sets what it needs."""
    for var in ("OPENMONTAGE_DIR", "SIMPLICIO_OPENMONTAGE_DIR", "SIMPLICIO_TOOLS_DIR", "SIMPLICIO_VIDEO_DATA"):
        monkeypatch.delenv(var, raising=False)
    lugares = {
        "OPENMONTAGE_DIR": _com_marcador(tmp_path / "1-explicita"),
        "SIMPLICIO_OPENMONTAGE_DIR": _com_marcador(tmp_path / "2-simplicio"),
        "SIMPLICIO_TOOLS_DIR": _com_marcador(tmp_path / "3-tools" / "openmontage"),
        "SIMPLICIO_VIDEO_DATA": _com_marcador(tmp_path / "4-dados" / "tools" / "openmontage"),
        "HOME": _com_marcador(tmp_path / "home" / ".simplicio-video" / "tools" / "openmontage"),
    }
    return lugares


def _poe(monkeypatch, lugares: dict, *nomes: str) -> None:
    for nome in nomes:
        valor = lugares[nome]
        monkeypatch.setenv(nome, str(valor.parent if nome == "SIMPLICIO_TOOLS_DIR" else valor.parent.parent if nome == "SIMPLICIO_VIDEO_DATA"
                                     else valor))


ORDEM = ["OPENMONTAGE_DIR", "SIMPLICIO_OPENMONTAGE_DIR", "SIMPLICIO_TOOLS_DIR", "SIMPLICIO_VIDEO_DATA", "HOME"]


@pytest.mark.parametrize("i", range(len(ORDEM)))
def test_a_primeira_variavel_posta_da_lista_decide_a_pasta(monkeypatch, ordem, i):
    """With variables i..4 set, the winner is i (the variable, not the first folder that exists: all five have a checkout)."""
    _poe(monkeypatch, ordem, *[n for n in ORDEM[i:] if n != "HOME"])
    esperado = ordem[ORDEM[i]]
    assert _om().default_openmontage_dir() == esperado
    assert _om().find_openmontage_dir() == esperado.resolve()


@pytest.mark.parametrize("i", range(len(ORDEM) - 1))
def test_a_variavel_que_decide_vale_mesmo_sem_checkout_nela(monkeypatch, tmp_path, ordem, i):
    """The folder is decided by the variable that is set; a checkout further down the list is not used instead."""
    _poe(monkeypatch, ordem, *[n for n in ORDEM[i + 1:] if n != "HOME"])
    vazia = tmp_path / "vazia"
    vazia.mkdir()
    monkeypatch.setenv(ORDEM[i], str(vazia if ORDEM[i] != "SIMPLICIO_TOOLS_DIR" and ORDEM[i] != "SIMPLICIO_VIDEO_DATA" else tmp_path / "x"))
    assert _om().find_openmontage_dir() is None


def test_as_duas_variaveis_de_pasta_valem_igual_e_a_primeira_ganha(monkeypatch, tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    monkeypatch.setenv("SIMPLICIO_OPENMONTAGE_DIR", str(b))
    assert _om().default_openmontage_dir() == b
    monkeypatch.setenv("OPENMONTAGE_DIR", str(a))
    assert _om().default_openmontage_dir() == a


@pytest.mark.parametrize("var", ["OPENMONTAGE_DIR", "SIMPLICIO_OPENMONTAGE_DIR", "SIMPLICIO_TOOLS_DIR", "SIMPLICIO_VIDEO_DATA"])
def test_variavel_vazia_e_variavel_que_nao_foi_posta(monkeypatch, ordem, var):
    _poe(monkeypatch, ordem, *[n for n in ORDEM[ORDEM.index(var) + 1:] if n != "HOME"])
    monkeypatch.setenv(var, "")
    seguinte = ORDEM[ORDEM.index(var) + 1] if var != "SIMPLICIO_VIDEO_DATA" else "HOME"
    assert _om().default_openmontage_dir() == ordem[seguinte]


def test_o_til_da_variavel_expande_e_o_caminho_relativo_fica_como_veio(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENMONTAGE_DIR", "~/om")
    assert _om().default_openmontage_dir() == tmp_path / "home" / "om"
    monkeypatch.setenv("OPENMONTAGE_DIR", "relativa/om")
    assert _om().default_openmontage_dir() == Path("relativa/om")  # not resolved here...
    monkeypatch.chdir(tmp_path)
    _com_marcador(tmp_path / "relativa" / "om")
    assert _om().find_openmontage_dir() == (tmp_path / "relativa" / "om").resolve()  # ...but find answers an absolute path


def test_o_til_de_simplicio_video_data_expande(monkeypatch, tmp_path):
    monkeypatch.delenv("SIMPLICIO_TOOLS_DIR")
    monkeypatch.setenv("SIMPLICIO_VIDEO_DATA", "~/dados")
    assert _om().default_openmontage_dir() == tmp_path / "home" / "dados" / "tools" / "openmontage"


def test_find_exige_o_marcador_dentro_da_pasta(monkeypatch, tmp_path):
    pasta = tmp_path / "om"
    pasta.mkdir()
    monkeypatch.setenv("OPENMONTAGE_DIR", str(pasta))
    assert _om().find_openmontage_dir() is None  # a folder without the marker is not a checkout
    (pasta / MARCADOR).write_text("", encoding="utf-8")
    assert _om().find_openmontage_dir() == pasta.resolve()  # a file named like the marker counts too: `.exists()`
    monkeypatch.setenv("OPENMONTAGE_DIR", str(tmp_path / "nao-existe"))
    assert _om().find_openmontage_dir() is None


@pytest.mark.skipif(os.name != "posix", reason="symlink")
def test_find_devolve_o_lugar_real_do_link(monkeypatch, tmp_path):
    real = _com_marcador(tmp_path / "real")
    (tmp_path / "link").symlink_to(real, target_is_directory=True)
    monkeypatch.setenv("OPENMONTAGE_DIR", str(tmp_path / "link"))
    assert _om().default_openmontage_dir() == tmp_path / "link"
    assert _om().find_openmontage_dir() == real.resolve()


def test_sem_nenhuma_variavel_e_sem_casa_a_recusa_diz_que_simplicio_video_data_escolhe_a_pasta(monkeypatch):
    """The last place needs a home, and the refusal names SIMPLICIO_VIDEO_DATA (tools.checkout_dir would name SIMPLICIO_TOOLS_DIR)."""
    for var in ("HOME", "USERPROFILE", "SIMPLICIO_VIDEO_DATA", "SIMPLICIO_TOOLS_DIR"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: (_ for _ in ()).throw(RuntimeError("Could not determine home directory."))))
    with pytest.raises(hostos.SemCasa) as caught:
        _om().default_openmontage_dir()
    assert "SIMPLICIO_VIDEO_DATA (a pasta escolhida direto)" in str(caught.value)
    with pytest.raises(hostos.SemCasa):
        _om().find_openmontage_dir()
    monkeypatch.setenv("SIMPLICIO_TOOLS_DIR", "/x")  # one variable is enough: no home is asked
    assert _om().default_openmontage_dir() == Path("/x/openmontage")


def test_o_clone_do_montage_recusa_o_offline_antes_de_decidir_a_pasta(monkeypatch):
    """Without a home, deciding the folder raises SemCasa; offline, the refusal comes first (and is the track's own error)."""
    for var in ("HOME", "USERPROFILE", "SIMPLICIO_VIDEO_DATA", "SIMPLICIO_TOOLS_DIR"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: (_ for _ in ()).throw(RuntimeError("Could not determine home directory."))))
    monkeypatch.setenv("SIMPLICIO_OFFLINE", "1")
    monkeypatch.setattr(tools, "install", _nao_chama)
    with pytest.raises(_om().MontageError) as caught:
        _clone("montage")()
    assert str(caught.value) == RECUSA_OFFLINE["montage"]


# ---- the data folder and the venv ------------------------------------------------------------------------------------------


@pytest.mark.parametrize("nome", ["matchcut", "montage"])
def test_data_dir_de_cada_trilha_segue_a_regra_de_sempre(monkeypatch, tmp_path, nome):
    _, _, _, _, env_data, _, tool = TRILHAS[nome]
    sub = f"{tool}-data"
    mod = _modulo(nome)
    assert mod.data_dir() == (tmp_path / "data" / sub).resolve()  # SIMPLICIO_VIDEO_DATA
    monkeypatch.setenv(env_data, str(tmp_path / "meus-dados"))
    assert mod.data_dir() == (tmp_path / "meus-dados").resolve()  # its own variable wins
    monkeypatch.setenv(env_data, "~/dados")
    assert mod.data_dir() == (tmp_path / "home" / "dados").resolve()
    monkeypatch.delenv(env_data)
    monkeypatch.delenv("SIMPLICIO_VIDEO_DATA")
    assert mod.data_dir() == (tmp_path / "home" / ".simplicio-video" / sub).resolve()  # no variable: under the home
    monkeypatch.setenv("SIMPLICIO_VIDEO_DATA", "raiz/relativa")
    monkeypatch.chdir(tmp_path)
    assert mod.data_dir() == (tmp_path / "raiz" / "relativa" / sub).resolve()  # a relative root is made absolute


@pytest.mark.parametrize("nome", ["matchcut", "montage"])
def test_venv_python_segue_o_data_dir_do_modulo(monkeypatch, tmp_path, nome):
    """`venv_python()` asks the module's `data_dir` (a test that replaces it moves the venv too)."""
    mod = _modulo(nome)
    sub = ("Scripts", "python.exe") if os.name == "nt" else ("bin", "python")
    assert mod.venv_python() == (tmp_path / "data" / f"{_tool(nome)}-data").resolve() / "venv" / sub[0] / sub[1]
    monkeypatch.setattr(mod, "data_dir", lambda: tmp_path / "outro")
    assert mod.venv_python() == tmp_path / "outro" / "venv" / sub[0] / sub[1]


def test_o_montage_avisa_em_stderr_do_data_dir_relativo_uma_vez_por_valor(monkeypatch, tmp_path, capsys):
    """The warning is the module's (Trilha.data_dir does not give one) and it has to survive the migration: same text, stderr, once."""
    from simplicio_video import montage
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(montage, "_WARNED_RELATIVE", set())
    monkeypatch.setenv("OPENMONTAGE_DATA_DIR", "dados/rel")
    esperado = (tmp_path / "dados" / "rel").resolve()
    assert montage.data_dir() == esperado
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == (f"montage: aviso: OPENMONTAGE_DATA_DIR relativo (dados/rel) vira {esperado} a partir da pasta atual; "
                            "use um caminho absoluto.\n")
    assert montage.venv_python().parent.parent.parent == esperado  # asks data_dir again...
    assert capsys.readouterr().err == ""  # ...and the same value is not warned twice
    monkeypatch.setenv("OPENMONTAGE_DATA_DIR", "outra/rel")
    montage.data_dir()
    assert "relativo (outra/rel)" in capsys.readouterr().err  # another value is a new warning


@pytest.mark.parametrize("valor", ["", "~/dados-om", "ABS"])
def test_o_montage_nao_avisa_quando_o_caminho_e_absoluto_ou_vazio(monkeypatch, tmp_path, capsys, valor):
    from simplicio_video import montage
    monkeypatch.setattr(montage, "_WARNED_RELATIVE", set())
    monkeypatch.setenv("OPENMONTAGE_DATA_DIR", str(tmp_path / "abs") if valor == "ABS" else valor)
    montage.data_dir()
    assert capsys.readouterr().err == ""


def test_o_matchcut_nunca_avisou_de_data_dir_relativo(monkeypatch, tmp_path, capsys):
    from simplicio_video import matchcut
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MATCHCUT_DATA_DIR", "dados/rel")
    assert matchcut.data_dir() == (tmp_path / "dados" / "rel").resolve()
    assert capsys.readouterr().err == ""


# ---- the commit really in the checkout -------------------------------------------------------------------------------------


def test_checkout_head_do_video_to_skill_pergunta_ao_git_so_quando_ha_dot_git(monkeypatch, tmp_path):
    from simplicio_video import video_to_skill
    chamadas = []
    monkeypatch.setattr(tools, "_git", lambda *a, cwd=None: chamadas.append((a, cwd)) or "deadbeef")
    assert video_to_skill._checkout_head(tmp_path) is None  # no .git: git would answer with the parent repository
    assert chamadas == []
    (tmp_path / ".git").mkdir()
    assert video_to_skill._checkout_head(tmp_path) == "deadbeef"
    assert chamadas == [(("rev-parse", "HEAD"), tmp_path)]


def test_checkout_head_do_video_to_skill_e_none_quando_o_git_falha(monkeypatch, tmp_path):
    from simplicio_video import video_to_skill
    (tmp_path / ".git").mkdir()

    def falha(*a, cwd=None):
        raise tools.ToolError("git rev-parse: fatal")

    monkeypatch.setattr(tools, "_git", falha)
    assert video_to_skill._checkout_head(tmp_path) is None


@pytest.mark.parametrize("nome", ["matchcut", "instagram"])
def test_commit_do_checkout_de_matchcut_e_instagram_e_o_rev_parse_sem_olhar_o_dot_git(monkeypatch, tmp_path, nome):
    """Another rule than `_checkout_head`: no `.git` test, and a failing git is the empty text (the callers compare with the pin)."""
    chamadas = []
    monkeypatch.setattr(tools, "_git", lambda *a, cwd=None: chamadas.append((a, cwd)) or "f" * 40)
    assert _modulo(nome)._commit_do_checkout(tmp_path) == "f" * 40
    assert chamadas == [(("rev-parse", "HEAD"), tmp_path)]

    def falha(*a, cwd=None):
        raise tools.ToolError("git rev-parse: fatal")

    monkeypatch.setattr(tools, "_git", falha)
    assert _modulo(nome)._commit_do_checkout(tmp_path) == ""


def test_o_status_do_matchcut_e_do_montage_perguntam_o_commit_ao_git_do_checkout(monkeypatch, tmp_path, capsys):
    from simplicio_video import matchcut, montage
    d = _com_marcador(tmp_path / "om")
    (d / "SKILL.md").write_text("x", encoding="utf-8")
    chamadas = []
    monkeypatch.setattr(tools, "_git", lambda *a, cwd=None: chamadas.append((a, cwd)) or "c" * 40)
    monkeypatch.setattr(montage, "find_openmontage_dir", lambda: d)
    monkeypatch.setattr(montage, "venv_python", lambda: tmp_path / "sem-venv")
    assert montage.status_report()["checkout"]["head"] == "c" * 40
    assert chamadas == [(("rev-parse", "HEAD"), d)]
    m = _com_marcador(tmp_path / "mc")
    (m / "SKILL.md").write_text("x", encoding="utf-8")
    chamadas.clear()
    monkeypatch.setattr(matchcut, "find_matchcut_dir", lambda: m)
    assert matchcut.run_matchcut(["status"]) == 0
    assert f"commit do checkout: {'c' * 40}" in capsys.readouterr().out
    assert chamadas == [(("rev-parse", "HEAD"), m)]


# ---- the helpers that were copies, now one in `terceiros` -------------------------------------------------------------------


def test_real_e_commit_do_checkout_vem_de_terceiros():
    from simplicio_video import instagram, matchcut, video_to_skill
    assert matchcut._real is terceiros.real and video_to_skill._real is terceiros.real
    assert matchcut._commit_do_checkout is terceiros.commit_do_checkout
    assert instagram._commit_do_checkout is terceiros.commit_do_checkout


def test_chave_e_dentro_ficam_no_modulo_porque_os_testes_trocam_o_case_insensitive_dele():
    """Green and meant to stay until U22a: the copies of `_chave` and `_dentro` follow the flag of THEIR module."""
    from simplicio_video import instagram, matchcut, video_to_skill
    for mod in (instagram, matchcut, video_to_skill):
        assert callable(mod._chave) and callable(mod._dentro) and isinstance(mod.CASE_INSENSITIVE, bool), mod.__name__
        assert mod._chave.__module__ == mod.__name__ and mod._dentro.__module__ == mod.__name__


# ---- nothing writes the process environment, nothing calls the private git runner --------------------------------------------


def _escritas_no_ambiente(fonte: str) -> list[int]:
    """Lines where the source writes `os.environ` (assign, delete, pop, setdefault, update, clear) or calls os.putenv/os.unsetenv."""
    def e_environ(no) -> bool:
        return isinstance(no, ast.Attribute) and no.attr == "environ" and isinstance(no.value, ast.Name) and no.value.id == "os"

    linhas = set()
    for no in ast.walk(ast.parse(fonte)):
        if isinstance(no, (ast.Assign, ast.AugAssign, ast.Delete)):
            for alvo in (no.targets if hasattr(no, "targets") else [no.target]):
                if isinstance(alvo, ast.Subscript) and e_environ(alvo.value):
                    linhas.add(no.lineno)
        elif isinstance(no, ast.Call) and isinstance(no.func, ast.Attribute):
            if e_environ(no.func.value) and no.func.attr in {"pop", "setdefault", "update", "clear", "popitem"}:
                linhas.add(no.lineno)
            if isinstance(no.func.value, ast.Name) and no.func.value.id == "os" and no.func.attr in {"putenv", "unsetenv"}:
                linhas.add(no.lineno)
    return sorted(linhas)


@pytest.mark.parametrize("nome", sorted(TRILHAS))
def test_o_modulo_nao_escreve_em_os_environ(nome):
    assert _escritas_no_ambiente(FONTES[nome].read_text(encoding="utf-8")) == []


def test_o_detector_de_escrita_no_ambiente_enxerga_cada_forma():
    fonte = ("import os\n"
             "os.environ['A'] = '1'\n"            # 2
             "del os.environ['A']\n"              # 3
             "os.environ.pop('A', None)\n"        # 4
             "os.environ.setdefault('A', '1')\n"  # 5
             "os.putenv('A', '1')\n"              # 6
             "x = os.environ.get('A')\n"
             "y = os.environ.copy()\n"
             "z = {k: os.environ[k] for k in ('A',)}\n")
    assert _escritas_no_ambiente(fonte) == [2, 3, 4, 5, 6]


@pytest.mark.parametrize("nome", sorted(TRILHAS))
def test_o_modulo_nao_chama_o_tools_git_privado(nome):
    """`tools.git` is the public name (it goes through `_git` at call time, so a test that replaces `tools._git` still covers it)."""
    assert not re.search(r"\btools\._git\b", FONTES[nome].read_text(encoding="utf-8"))


# ---- dead code the migration takes out ------------------------------------------------------------------------------------


def test_o_montage_nao_tem_mais_o_result_dir_que_ninguem_lia():
    from simplicio_video import jobs, montage
    assert not hasattr(montage, "_RESULT_DIR")
    assert jobs._MONTAGE_RESULT_DIR == ".resultados"  # the one that is read lives in jobs.py


def test_confere_entrada_do_matchcut_nao_recebe_o_nome_que_nao_usava():
    from simplicio_video import matchcut
    assert list(inspect.signature(matchcut._confere_entrada).parameters) == ["caminho"]


def _confere_entrada(caminho: str):
    """`_confere_entrada` with the argument list it has (green before and after: only the unused `nome` goes away)."""
    from simplicio_video import matchcut
    if "nome" in inspect.signature(matchcut._confere_entrada).parameters:
        return matchcut._confere_entrada(caminho, "config")
    return matchcut._confere_entrada(caminho)


def test_confere_entrada_do_matchcut_diz_o_que_dizia(tmp_path):
    from simplicio_video import matchcut
    arquivo = tmp_path / "a.json"
    arquivo.write_text("{}", encoding="utf-8")
    assert _confere_entrada(str(arquivo)) == str(arquivo)
    with pytest.raises(matchcut.MatchcutError) as faltando:
        _confere_entrada(str(tmp_path / "nao-existe.json"))
    assert str(faltando.value) == f"arquivo de entrada não encontrado: {ascii(str(tmp_path / 'nao-existe.json'))[:60]}"
    with pytest.raises(matchcut.MatchcutError) as pasta:
        _confere_entrada(str(tmp_path))
    assert str(pasta.value) == f"a entrada precisa ser um arquivo comum: {ascii(str(tmp_path))[:60]}"


# ---- the private cwd of a video-to-skill job -----------------------------------------------------------------------------

PREFIXO_DA_TAREFA = "video-to-skill-job-"


@pytest.fixture
def temp(monkeypatch, tmp_path):
    pasta = tmp_path / "temp"
    pasta.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(pasta))
    return pasta


def _velha(p: Path, dias: float = 8) -> Path:
    t = time.time() - dias * 86400
    os.utime(p, (t, t))
    return p


def test_make_job_cwd_devolve_str_de_uma_pasta_vazia_e_nova_na_pasta_temporaria(temp):
    from simplicio_video import video_to_skill
    assert video_to_skill.JOB_CWD_PREFIX == PREFIXO_DA_TAREFA
    cwd = video_to_skill.make_job_cwd()
    assert isinstance(cwd, str)  # it goes into the job's JSON as it is
    p = Path(cwd)
    assert p.is_dir() and list(p.iterdir()) == [] and p.parent == temp and p.name.startswith(PREFIXO_DA_TAREFA)
    assert video_to_skill.make_job_cwd() != cwd


def test_make_job_cwd_varre_as_pastas_vazias_de_mais_de_uma_semana_e_so_elas(temp):
    from simplicio_video import video_to_skill
    velha_vazia = temp / (PREFIXO_DA_TAREFA + "velha")
    nova_vazia = temp / (PREFIXO_DA_TAREFA + "nova")
    velha_cheia = temp / (PREFIXO_DA_TAREFA + "cheia")
    de_outro = temp / "outra-coisa-job"
    de_rea_video = temp / "rea-video-job-velha"
    for p in (velha_vazia, nova_vazia, velha_cheia, de_outro, de_rea_video):
        p.mkdir()
    (velha_cheia / "resultado.json").write_text("{}", encoding="utf-8")
    for p in (velha_vazia, velha_cheia, de_outro, de_rea_video):
        _velha(p)
    video_to_skill.make_job_cwd()
    assert not velha_vazia.exists()
    assert nova_vazia.exists() and velha_cheia.exists() and de_outro.exists() and de_rea_video.exists()  # young, not empty, not ours


def test_make_job_cwd_deixa_a_pasta_de_seis_dias_e_varre_a_de_oito(temp):
    from simplicio_video import video_to_skill
    seis, oito = temp / (PREFIXO_DA_TAREFA + "seis"), temp / (PREFIXO_DA_TAREFA + "oito")
    seis.mkdir()
    oito.mkdir()
    _velha(seis, 6)
    _velha(oito, 8)
    video_to_skill.make_job_cwd()
    assert seis.exists() and not oito.exists()


def test_drop_job_cwd_remove_so_a_pasta_vazia_nossa_direto_na_temporaria(temp, tmp_path):
    from simplicio_video import video_to_skill
    nossa = Path(video_to_skill.make_job_cwd())
    video_to_skill.drop_job_cwd(str(nossa))
    assert not nossa.exists()
    cheia = Path(video_to_skill.make_job_cwd())
    (cheia / "x").write_text("x", encoding="utf-8")
    video_to_skill.drop_job_cwd(str(cheia))
    assert cheia.exists()  # rmdir only removes an empty one
    de_outro = temp / "outra-coisa"
    de_outro.mkdir()
    video_to_skill.drop_job_cwd(str(de_outro))
    assert de_outro.exists()  # not our prefix
    fora = tmp_path / (PREFIXO_DA_TAREFA + "fora")
    fora.mkdir()
    video_to_skill.drop_job_cwd(str(fora))
    assert fora.exists()  # our prefix, but not directly under the temp folder
    fundo = temp / "sub"
    fundo.mkdir()
    (fundo / (PREFIXO_DA_TAREFA + "fundo")).mkdir()
    video_to_skill.drop_job_cwd(str(fundo / (PREFIXO_DA_TAREFA + "fundo")))
    assert (fundo / (PREFIXO_DA_TAREFA + "fundo")).exists()


@pytest.mark.parametrize("valor", [None, "", 0])
def test_drop_job_cwd_ignora_o_que_nao_e_caminho(temp, valor):
    from simplicio_video import video_to_skill
    video_to_skill.drop_job_cwd(valor)  # nothing to remove, nothing raised
    assert list(temp.iterdir()) == []


# ---- the variables of the four tracks stay in the reference ---------------------------------------------------------------


def test_as_variaveis_das_quatro_trilhas_continuam_em_config_md():
    """Today they come from the reads and writes of `_checkout_at` and `data_dir`; after, from the arguments of `Trilha(...)` that
    scripts/gen_reference.py reads. Either way, each is a row of docs/reference/config.md."""
    raiz = Path(__file__).resolve().parents[1]
    linhas = (raiz / "docs" / "reference" / "config.md").read_text(encoding="utf-8")
    for _, _, _, env_dir, env_data, _, _ in TRILHAS.values():
        for nome in filter(None, (env_dir, env_data)):
            assert f"| `{nome}` |" in linhas, f"{nome} falta em config.md"
