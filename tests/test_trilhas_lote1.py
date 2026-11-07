"""U08a, tracks of the first batch (toonflow, moneyprinter, rea_video, opencut) on top of `trilha_base`.

Each of the four modules carries its own copy of what `trilha_base.Trilha` now does: find the checkout, clone it, the data folder, the
commit really in the checkout, the private cwd of a job and the stop of a process group. Three of them clone by WRITING `<NAME>_DIR` into
the environment of the whole process and putting it back (`_checkout_at`); opencut writes it and never puts it back, so the variable
leaks into the MCP server, which runs tools in threads.

Green today (and it has to stay green): what the tracks answer, byte for byte (the offline refusal of each, the errors, the names a
test replaces, the private folder of a rea-video job). Red until the migration: the declaration `T`, `_checkout_at` gone, the folder
handed to `tools.install(dir=)` with the environment untouched, and the aliases that now come from `rede` and `trilha_base`.
"""
from __future__ import annotations

import importlib
import os
import tempfile
import time
from pathlib import Path

import pytest

from simplicio_video import rede, tools, trilha_base

# the track, its module, the clone function, its error, the variable of the checkout, of the data and the function that finds it
TRILHAS = {
    "toonflow": ("toonflow", "clone_toonflow", "ToonflowError", "TOONFLOW_DIR", "TOONFLOW_DATA_DIR", "find_toonflow_dir"),
    "moneyprinter": ("moneyprinter", "clone_moneyprinter", "MoneyPrinterError", "MONEYPRINTER_DIR", "MONEYPRINTER_DATA_DIR",
                     "find_moneyprinter_dir"),
    "rea_video": ("rea_video", "clone_rea_video", "ReaVideoError", "REA_VIDEO_DIR", "REA_VIDEO_DATA_DIR", "find_rea_video_dir"),
    "opencut": ("opencut", "clone_opencut", "OpenCutError", "OPENCUT_DIR", None, "find_opencut_dir"),
}
COM_RECUSA_OFFLINE = ["toonflow", "moneyprinter", "rea_video"]  # opencut never refused: its clone goes to tools.install offline too

# what each clone says in offline mode, byte for byte (the opening is rede.PREFIXO_OFFLINE; the rest is the track's own)
RECUSA_OFFLINE = {
    "toonflow": ("modo offline (SIMPLICIO_OFFLINE=1): não vou clonar o Toonflow. "
                 "Instale fora do modo offline com `simplicio-video toonflow clone` ou aponte TOONFLOW_DIR para um checkout."),
    "moneyprinter": ("modo offline (SIMPLICIO_OFFLINE=1): não vou clonar o MoneyPrinterTurbo. "
                     "Instale fora do modo offline com `simplicio-video moneyprinter clone` ou aponte MONEYPRINTER_DIR para um checkout."),
    "rea_video": ("modo offline (SIMPLICIO_OFFLINE=1): não vou clonar o rea-video. "
                  "Rode `simplicio-video rea-video clone` fora do modo offline ou aponte REA_VIDEO_DIR para um checkout."),
}


def _modulo(nome: str):
    return importlib.import_module(f"simplicio_video.{TRILHAS[nome][0]}")


def _clone(nome: str):
    return getattr(_modulo(nome), TRILHAS[nome][1])


def _erro(nome: str):
    return getattr(_modulo(nome), TRILHAS[nome][2])


@pytest.fixture(autouse=True)
def _ambiente(monkeypatch, tmp_path):
    """No real home, tools folder or data folder reaches a test, and no variable of a track or of the network policy is set."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "home"))
    monkeypatch.setenv("SIMPLICIO_TOOLS_DIR", str(tmp_path / "tools"))
    monkeypatch.setenv("SIMPLICIO_VIDEO_DATA", str(tmp_path / "data"))
    monkeypatch.delenv("SIMPLICIO_OFFLINE", raising=False)
    for _, _, _, env_dir, env_data, _ in TRILHAS.values():
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


# ---- the declaration -------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("nome", sorted(TRILHAS))
def test_cada_modulo_declara_a_sua_trilha_em_T(nome):
    _, _, _, env_dir, env_data, _ = TRILHAS[nome]
    assert _modulo(nome).T == trilha_base.Trilha(nome, env_dir, env_data)


@pytest.mark.parametrize("nome", sorted(TRILHAS))
def test_o_checkout_at_que_mutava_o_ambiente_nao_existe_mais(nome):
    assert not hasattr(_modulo(nome), "_checkout_at")


# ---- clone: the environment of the process is never written ---------------------------------------------------------------


@pytest.mark.parametrize("nome", sorted(TRILHAS))
def test_depois_do_clone_o_ambiente_e_o_que_era(monkeypatch, tmp_path, nome):
    """Red for opencut today: `clone_opencut(target)` sets OPENCUT_DIR and never puts it back."""
    _pouso(monkeypatch, tmp_path)
    antes = dict(os.environ)
    _clone(nome)(tmp_path / "meu")
    assert dict(os.environ) == antes
    assert os.environ.get(TRILHAS[nome][3]) is None


@pytest.mark.parametrize("nome", sorted(TRILHAS))
def test_o_clone_numa_pasta_passa_a_pasta_a_tools_install_e_nao_escreve_variavel_nenhuma(monkeypatch, tmp_path, nome):
    """The folder reaches `tools.install` as `dir=`, and at that moment the environment is what it was: another thread that reads
    `<NAME>_DIR` while the clone runs must not see the target."""
    falso = _pouso(monkeypatch, tmp_path)
    antes = dict(os.environ)
    alvo = tmp_path / "meu"
    assert _clone(nome)(alvo) == alvo
    assert [(n, d) for n, d, _ in falso.chamadas] == [(nome, alvo)]
    assert falso.chamadas[0][2] == antes


@pytest.mark.parametrize("nome", sorted(TRILHAS))
def test_o_clone_expande_o_til_da_pasta(monkeypatch, tmp_path, nome):
    falso = _pouso(monkeypatch, tmp_path)
    assert _clone(nome)(Path("~/lote1")) == tmp_path / "home" / "lote1"
    assert [(n, d) for n, d, _ in falso.chamadas] == [(nome, tmp_path / "home" / "lote1")]


@pytest.mark.parametrize("nome", sorted(TRILHAS))
def test_o_clone_sem_pasta_chama_tools_install_so_com_o_nome(monkeypatch, tmp_path, nome):
    """Green: no folder, the location is the one `tools.checkout_dir` decides, so `tools.install` gets the name and nothing else."""
    vistas = []

    def falso(name, **kw):
        vistas.append((name, kw))
        return str(tmp_path / "padrao")

    monkeypatch.setattr(tools, "install", falso)
    assert _clone(nome)() == tmp_path / "padrao"
    assert vistas == [(nome, {})]


@pytest.mark.parametrize("nome", sorted(TRILHAS))
@pytest.mark.parametrize("alvo", [None, "meu"])
def test_um_tool_error_do_install_vira_o_erro_da_trilha_com_a_mesma_mensagem(monkeypatch, tmp_path, nome, alvo):
    def falho(name, **kw):
        raise tools.ToolError("git clone: sem espaço no disco")

    monkeypatch.setattr(tools, "install", falho)
    with pytest.raises(_erro(nome)) as caught:
        _clone(nome)(tmp_path / alvo if alvo else None)
    assert str(caught.value) == "git clone: sem espaço no disco"
    assert caught.value.__suppress_context__ is True  # `from None`: the user reads the message, not a chain


@pytest.mark.parametrize("nome", sorted(TRILHAS))
def test_outro_erro_do_install_passa_sem_virar_erro_da_trilha(monkeypatch, tmp_path, nome):
    """Only ToolError is caught, today and after: an OSError is not turned into the track's error."""
    def falho(name, **kw):
        raise OSError("disco cheio")

    monkeypatch.setattr(tools, "install", falho)
    with pytest.raises(OSError, match="disco cheio"):
        _clone(nome)(tmp_path / "meu")


# ---- clone: offline --------------------------------------------------------------------------------------------------------


def _nao_chama(*a, **k):
    pytest.fail("tools.install não devia ser chamado neste caso")


@pytest.mark.parametrize("valor", ["1", "true", "YES", " On "])
@pytest.mark.parametrize("nome", COM_RECUSA_OFFLINE)
def test_a_recusa_offline_do_clone_e_a_mesma_byte_a_byte(monkeypatch, nome, valor):
    monkeypatch.setenv("SIMPLICIO_OFFLINE", valor)
    monkeypatch.setattr(tools, "install", _nao_chama)
    with pytest.raises(_erro(nome)) as caught:
        _clone(nome)()
    assert str(caught.value) == RECUSA_OFFLINE[nome]
    assert str(caught.value).startswith(rede.PREFIXO_OFFLINE)


@pytest.mark.parametrize("nome", COM_RECUSA_OFFLINE)
def test_a_recusa_offline_vale_tambem_para_o_clone_numa_pasta(monkeypatch, tmp_path, nome):
    monkeypatch.setenv("SIMPLICIO_OFFLINE", "1")
    monkeypatch.setattr(tools, "install", _nao_chama)
    with pytest.raises(_erro(nome)) as caught:
        _clone(nome)(tmp_path / "meu")
    assert str(caught.value) == RECUSA_OFFLINE[nome]


@pytest.mark.parametrize("valor", ["0", "false", "no", "off", "", "talvez"])
@pytest.mark.parametrize("nome", COM_RECUSA_OFFLINE)
def test_fora_do_modo_offline_o_clone_segue_para_o_install(monkeypatch, tmp_path, nome, valor):
    monkeypatch.setenv("SIMPLICIO_OFFLINE", valor)
    falso = _pouso(monkeypatch, tmp_path)
    _clone(nome)()
    assert [n for n, _, _ in falso.chamadas] == [nome]


@pytest.mark.parametrize("nome", COM_RECUSA_OFFLINE)
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
    assert [n for n, _, _ in falso.chamadas] == [nome]


def test_o_clone_do_opencut_nunca_recusou_offline_e_continua_assim(monkeypatch, tmp_path):
    """The opencut clone has no offline check today: it goes to `tools.install` (git decides). The migration keeps it exactly so."""
    monkeypatch.setenv("SIMPLICIO_OFFLINE", "1")
    falso = _pouso(monkeypatch, tmp_path)
    _clone("opencut")(tmp_path / "meu")
    assert [n for n, _, _ in falso.chamadas] == ["opencut"]


# ---- the names a test replaces stay names of the module, and the code calls them -------------------------------------------

ALIASES = {
    "toonflow": ("_offline", "_on_term", "_stop_group", "find_toonflow_dir", "data_dir", "clone_toonflow"),
    "moneyprinter": ("_offline", "_on_term", "_stop_group", "_checkout_head", "venv_python", "find_moneyprinter_dir", "data_dir",
                     "clone_moneyprinter"),
    "rea_video": ("_offline", "_checkout_head", "find_rea_video_dir", "data_dir", "venv_bin", "make_job_cwd", "drop_job_cwd",
                  "clone_rea_video"),
    "opencut": ("find_opencut_dir", "clone_opencut"),
}


@pytest.mark.parametrize("nome", sorted(ALIASES))
def test_os_nomes_que_os_testes_trocam_continuam_no_modulo(nome):
    for alias in ALIASES[nome]:
        assert callable(getattr(_modulo(nome), alias, None)), f"{nome}.{alias}"


@pytest.mark.parametrize("nome", ["toonflow", "moneyprinter", "rea_video"])
def test_offline_vem_de_rede_e_nao_do_toonflow(nome):
    assert _modulo(nome)._offline is rede.offline


@pytest.mark.parametrize("nome", ["toonflow", "moneyprinter"])
def test_a_parada_do_grupo_e_o_sinal_de_termino_vem_de_trilha_base(nome):
    """toonflow keeps `_on_term` and `_stop_group` as names (matchcut and video_to_skill still import them from there until the
    second batch); moneyprinter no longer reaches into toonflow for them."""
    assert _modulo(nome)._on_term is trilha_base.on_term
    assert _modulo(nome)._stop_group is trilha_base.stop_group


def test_moneyprinter_e_rea_video_nao_importam_nomes_privados_do_toonflow():
    for nome in ("moneyprinter", "rea_video"):
        fonte = Path(_modulo(nome).__file__).read_text(encoding="utf-8")
        assert "from .toonflow" not in fonte, nome


@pytest.mark.parametrize("nome", sorted(TRILHAS))
def test_o_alias_de_find_e_chamado_pelo_where(monkeypatch, tmp_path, nome, capsys):
    mod = _modulo(nome)
    onde = tmp_path / "meu-checkout"
    onde.mkdir()
    monkeypatch.setattr(mod, TRILHAS[nome][5], lambda: onde)
    assert getattr(mod, f"run_{TRILHAS[nome][0]}")(["where"]) == 0
    assert capsys.readouterr().out.strip() == str(onde)


@pytest.mark.parametrize("nome", ["toonflow", "moneyprinter", "rea_video"])
def test_find_acha_o_checkout_de_tools_find(monkeypatch, tmp_path, nome):
    t = tools.get(nome)
    d = tmp_path / "tools" / nome
    (d / t.marker).parent.mkdir(parents=True)
    (d / t.marker).write_text("{}\n", encoding="utf-8")
    assert getattr(_modulo(nome), TRILHAS[nome][5])() == tools.find(nome) == d.resolve()


def test_venv_python_do_moneyprinter_segue_o_data_dir_do_modulo(monkeypatch, tmp_path):
    """`venv_python()` asks the module's `data_dir` (a test that replaces it moves the venv too)."""
    from simplicio_video import moneyprinter
    monkeypatch.setattr(moneyprinter, "data_dir", lambda: tmp_path / "outro")
    sub = ("Scripts", "python.exe") if os.name == "nt" else ("bin", "python")
    assert moneyprinter.venv_python() == tmp_path / "outro" / "venv" / sub[0] / sub[1]


def test_venv_python_do_moneyprinter_fica_na_pasta_de_dados_por_padrao(tmp_path):
    from simplicio_video import moneyprinter
    sub = ("Scripts", "python.exe") if os.name == "nt" else ("bin", "python")
    assert moneyprinter.venv_python() == (tmp_path / "data" / "moneyprinter-data").resolve() / "venv" / sub[0] / sub[1]


# ---- the commit really in the checkout ------------------------------------------------------------------------------------


@pytest.mark.parametrize("nome", ["moneyprinter", "rea_video"])
def test_checkout_head_pergunta_ao_git_so_quando_ha_dot_git(monkeypatch, tmp_path, nome):
    chamadas = []
    monkeypatch.setattr(tools, "_git", lambda *a, cwd=None: chamadas.append((a, cwd)) or "deadbeef")
    mod = _modulo(nome)
    assert mod._checkout_head(tmp_path) is None  # no .git: git would answer with the parent repository
    assert chamadas == []
    (tmp_path / ".git").mkdir()
    assert mod._checkout_head(tmp_path) == "deadbeef"
    assert chamadas == [(("rev-parse", "HEAD"), tmp_path)]


@pytest.mark.parametrize("nome", ["moneyprinter", "rea_video"])
def test_checkout_head_e_none_quando_o_git_falha(monkeypatch, tmp_path, nome):
    (tmp_path / ".git").mkdir()

    def falha(*a, cwd=None):
        raise tools.ToolError("git rev-parse: fatal")

    monkeypatch.setattr(tools, "_git", falha)
    assert _modulo(nome)._checkout_head(tmp_path) is None


def test_o_alias_checkout_head_do_rea_video_e_o_que_o_status_e_o_aviso_usam(monkeypatch, tmp_path, capsys):
    from simplicio_video import rea_video
    ref = tools.pinned_ref(tools.get("rea_video"))
    monkeypatch.setattr(rea_video, "_checkout_head", lambda d: "a" * 40)
    rea_video._status(tmp_path)
    assert f"commit do checkout: {'a' * 40} (diferente do fixado)" in capsys.readouterr().out
    rea_video._warn_if_not_pinned(tmp_path)
    err = capsys.readouterr().err
    assert f"está em {'a' * 12}, não no commit fixado {ref[:12]}" in err
    monkeypatch.setattr(rea_video, "_checkout_head", lambda d: None)
    rea_video._status(tmp_path)
    assert "commit do checkout: desconhecido" in capsys.readouterr().out
    rea_video._warn_if_not_pinned(tmp_path)
    assert capsys.readouterr().err == ""


# ---- the private cwd of a rea-video job -----------------------------------------------------------------------------------

PREFIXO_DA_TAREFA = "rea-video-job-"


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
    from simplicio_video import rea_video
    cwd = rea_video.make_job_cwd()
    assert isinstance(cwd, str)  # it goes into the job's JSON as it is
    p = Path(cwd)
    assert p.is_dir() and list(p.iterdir()) == [] and p.parent == temp and p.name.startswith(PREFIXO_DA_TAREFA)
    assert rea_video.make_job_cwd() != cwd


def test_make_job_cwd_varre_as_pastas_vazias_de_mais_de_uma_semana_e_so_elas(temp):
    from simplicio_video import rea_video
    velha_vazia = temp / (PREFIXO_DA_TAREFA + "velha")
    nova_vazia = temp / (PREFIXO_DA_TAREFA + "nova")
    velha_cheia = temp / (PREFIXO_DA_TAREFA + "cheia")
    de_outro = temp / "outra-coisa-job"
    for p in (velha_vazia, nova_vazia, velha_cheia, de_outro):
        p.mkdir()
    (velha_cheia / "resultado.json").write_text("{}", encoding="utf-8")
    for p in (velha_vazia, velha_cheia, de_outro):
        _velha(p)
    rea_video.make_job_cwd()
    assert not velha_vazia.exists()
    assert nova_vazia.exists() and velha_cheia.exists() and de_outro.exists()  # young, not empty, not ours


def test_drop_job_cwd_remove_so_a_pasta_vazia_nossa_direto_na_temporaria(temp, tmp_path):
    from simplicio_video import rea_video
    nossa = Path(rea_video.make_job_cwd())
    rea_video.drop_job_cwd(str(nossa))
    assert not nossa.exists()
    cheia = Path(rea_video.make_job_cwd())
    (cheia / "x").write_text("x", encoding="utf-8")
    rea_video.drop_job_cwd(str(cheia))
    assert cheia.exists()  # rmdir only removes an empty one
    de_outro = temp / "outra-coisa"
    de_outro.mkdir()
    rea_video.drop_job_cwd(str(de_outro))
    assert de_outro.exists()  # not our prefix
    fora = tmp_path / (PREFIXO_DA_TAREFA + "fora")
    fora.mkdir()
    rea_video.drop_job_cwd(str(fora))
    assert fora.exists()  # our prefix, but not directly under the temp folder
    fundo = temp / "sub"
    fundo.mkdir()
    (fundo / (PREFIXO_DA_TAREFA + "fundo")).mkdir()
    rea_video.drop_job_cwd(str(fundo / (PREFIXO_DA_TAREFA + "fundo")))
    assert (fundo / (PREFIXO_DA_TAREFA + "fundo")).exists()


@pytest.mark.parametrize("valor", [None, "", 0])
def test_drop_job_cwd_ignora_o_que_nao_e_caminho(temp, valor):
    from simplicio_video import rea_video
    rea_video.drop_job_cwd(valor)  # nothing to remove, nothing raised
    assert list(temp.iterdir()) == []
