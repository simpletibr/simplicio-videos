"""U08.1, the `trilha_base` module: what every external track repeats today, in one place and without touching `os.environ`.

Seven track modules carry their own copy of the same code: find the checkout, clone it (pointing `tools.install` at a folder by WRITING
`<NAME>_DIR` into the environment of the whole process), the data folder, `rev-parse HEAD`, the private cwd of a job, and the stop of
a process group. This module only ADDS the interface (the tracks migrate in wave 2 and 3), so the tests run the same table over the
copies that exist today (green) and over `trilha_base` (red until it exists): that is how "same answer" is proved.

Depends on U08.0 (`tools.install(dir=)`, `tools.git_head`) and U07.0 (`rede.offline`, `rede.motivo_offline`).
"""
from __future__ import annotations

import dataclasses
import importlib
import inspect
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

from simplicio_video import hostos, tools

PREFIXO = "modo offline (SIMPLICIO_OFFLINE=1): não vou "
_GIT_REAL = tools._git  # the hermetic fixture swaps tools._git for a refusal in every test: this is the real runner
SEM_GIT = shutil.which("git") is None
POSIX = pytest.mark.skipif(os.name != "posix", reason="POSIX")
COM_PROC = pytest.mark.skipif(not Path("/proc").is_dir(), reason="o teste lê /proc (Linux)")

# the tracks that have a data folder today: (tools name, variable of the checkout, variable of the data, folder under the data root)
COM_DADOS = {
    "toonflow": ("TOONFLOW_DIR", "TOONFLOW_DATA_DIR", "toonflow-data"),
    "moneyprinter": ("MONEYPRINTER_DIR", "MONEYPRINTER_DATA_DIR", "moneyprinter-data"),
    "rea_video": ("REA_VIDEO_DIR", "REA_VIDEO_DATA_DIR", "rea-video-data"),
    "matchcut": ("MATCHCUT_DIR", "MATCHCUT_DATA_DIR", "matchcut-data"),
    "openmontage": ("OPENMONTAGE_DIR", "OPENMONTAGE_DATA_DIR", "openmontage-data"),
}
# the module function that is the copy of today
DATA_DIR_DE_HOJE = {"toonflow": "toonflow", "moneyprinter": "moneyprinter", "rea_video": "rea_video", "matchcut": "matchcut",
                    "openmontage": "montage"}
TRILHAS_GIT = [t.name for t in tools.TOOLS.values() if t.kind == "git" and t.name != "video-use"]


def _tb():
    return importlib.import_module("simplicio_video.trilha_base")  # red until U08.1 adds the module


def _trilha(nome: str):
    env_dir, env_data, _ = COM_DADOS.get(nome, (f"{nome.upper()}_DIR", None, None))
    return _tb().Trilha(nome, env_dir, env_data)


@pytest.fixture(autouse=True)
def _ambiente(monkeypatch, tmp_path):
    """No real home, tools folder or data folder reaches a test; no variable of a track is set."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "home"))
    monkeypatch.setenv("SIMPLICIO_TOOLS_DIR", str(tmp_path / "tools"))
    monkeypatch.setenv("SIMPLICIO_VIDEO_DATA", str(tmp_path / "data"))
    for env_dir, env_data, _ in COM_DADOS.values():
        monkeypatch.delenv(env_dir, raising=False)
        monkeypatch.delenv(env_data, raising=False)
    for t in tools.TOOLS.values():
        monkeypatch.delenv(f"{t.name.upper()}_DIR", raising=False)
        monkeypatch.delenv(f"SIMPLICIO_{t.name.upper()}_DIR", raising=False)


# ---- Trilha: the declaration -----------------------------------------------------------------------------------------------


def test_trilha_e_um_dataclass_congelado_com_tres_campos():
    tb = _tb()
    t = tb.Trilha("toonflow", "TOONFLOW_DIR")
    assert dataclasses.is_dataclass(t) and t.env_data is None
    assert [f.name for f in dataclasses.fields(tb.Trilha)] == ["nome", "env_dir", "env_data"]
    with pytest.raises(dataclasses.FrozenInstanceError):
        t.nome = "outra"
    assert tb.Trilha("toonflow", "TOONFLOW_DIR", "TOONFLOW_DATA_DIR") == tb.Trilha("toonflow", "TOONFLOW_DIR", "TOONFLOW_DATA_DIR")
    hash(t)


@pytest.mark.parametrize("nome", TRILHAS_GIT)
def test_o_env_dir_declarado_e_o_que_tools_le_para_a_trilha(monkeypatch, tmp_path, nome):
    """The variable that `tools.checkout_dir` reads for a track is {NAME}_DIR: what a Trilha declares as `env_dir` must be that one."""
    t = tools.get(nome)
    d = tmp_path / "ali"
    (d / t.marker).parent.mkdir(parents=True)
    (d / t.marker).write_text("{}\n", encoding="utf-8")
    monkeypatch.setenv(f"{nome.upper()}_DIR", str(d))
    assert _tb().Trilha(nome, f"{nome.upper()}_DIR").find() == d.resolve()


# ---- find() ------------------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("nome", TRILHAS_GIT)
def test_find_e_tools_find(monkeypatch, tmp_path, nome):
    t = tools.get(nome)
    trilha = _trilha(nome)
    assert trilha.find() is None and tools.find(nome) is None  # nothing installed
    d = tmp_path / "lugar"
    d.mkdir()
    monkeypatch.setenv(f"{nome.upper()}_DIR", str(d))
    assert trilha.find() is None  # the folder exists but has no marker
    (d / t.marker).parent.mkdir(parents=True, exist_ok=True)
    (d / t.marker).write_text("{}\n", encoding="utf-8")
    assert trilha.find() == tools.find(nome) == d.resolve()


def test_find_acha_o_checkout_do_cache_de_tools(monkeypatch, tmp_path):
    t = tools.get("toonflow")
    d = tmp_path / "tools" / "toonflow"
    d.mkdir(parents=True)
    (d / t.marker).write_text("{}\n", encoding="utf-8")
    assert _trilha("toonflow").find() == d.resolve()


def _finders_de_hoje():
    from simplicio_video import matchcut, moneyprinter, rea_video, toonflow
    return {"toonflow": toonflow.find_toonflow_dir, "moneyprinter": moneyprinter.find_moneyprinter_dir,
            "rea_video": rea_video.find_rea_video_dir, "matchcut": matchcut.find_matchcut_dir}


def _checkout_falso(monkeypatch, tmp_path, nome: str) -> Path:
    d = tmp_path / nome
    d.mkdir()
    marca = d / tools.get(nome).marker
    marca.parent.mkdir(parents=True, exist_ok=True)
    marca.write_text("{}\n", encoding="utf-8")
    monkeypatch.setenv(f"{nome.upper()}_DIR", str(d))
    return d


@pytest.mark.parametrize("nome", ["toonflow", "moneyprinter", "rea_video", "matchcut"])
def test_find_de_hoje_dos_modulos_e_tools_find(monkeypatch, tmp_path, nome):
    """Green today: the module finders are `tools.find(<name>)`."""
    finder = _finders_de_hoje()[nome]
    assert finder() is None
    d = _checkout_falso(monkeypatch, tmp_path, nome)
    assert finder() == tools.find(nome) == d.resolve()


@pytest.mark.parametrize("nome", ["toonflow", "moneyprinter", "rea_video", "matchcut"])
def test_find_da_trilha_responde_o_que_o_modulo_responde(monkeypatch, tmp_path, nome):
    finder = _finders_de_hoje()[nome]
    assert _trilha(nome).find() is None and finder() is None
    _checkout_falso(monkeypatch, tmp_path, nome)
    assert _trilha(nome).find() == finder()


# ---- data_dir() --------------------------------------------------------------------------------------------------------------


def _data_dir_de_hoje(nome: str):
    return importlib.import_module(f"simplicio_video.{DATA_DIR_DE_HOJE[nome]}").data_dir


def _sem_casa(monkeypatch):
    for var in ("HOME", "USERPROFILE", "SIMPLICIO_VIDEO_DATA", "SIMPLICIO_TOOLS_DIR"):
        monkeypatch.delenv(var, raising=False)

    def sem(cls):
        raise RuntimeError("Could not determine home directory.")

    monkeypatch.setattr(Path, "home", classmethod(sem))


def _cenarios_de_dados(monkeypatch, tmp_path, env_data: str):
    """The environments the data folder is read from, as (name, how to set it up); each returns nothing, the caller reads the folder."""
    casa = tmp_path / "home"
    casa.mkdir(exist_ok=True)

    def explicita():
        monkeypatch.setenv(env_data, str(tmp_path / "explicita"))

    def explicita_com_til():
        monkeypatch.setenv(env_data, "~/dados-do-modulo")

    def explicita_relativa():
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv(env_data, "relativa/aqui")

    def explicita_vazia_cai_no_resto():
        monkeypatch.setenv(env_data, "")

    def raiz_de_dados():
        monkeypatch.setenv("SIMPLICIO_VIDEO_DATA", str(tmp_path / "raiz"))

    def raiz_de_dados_com_til():
        monkeypatch.setenv("SIMPLICIO_VIDEO_DATA", "~/raiz-com-til")

    def raiz_de_dados_relativa():
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("SIMPLICIO_VIDEO_DATA", "raiz/relativa")

    def so_o_home():
        monkeypatch.delenv("SIMPLICIO_VIDEO_DATA", raising=False)

    def a_explicita_vence_a_raiz():
        monkeypatch.setenv(env_data, str(tmp_path / "explicita"))
        monkeypatch.setenv("SIMPLICIO_VIDEO_DATA", str(tmp_path / "raiz"))

    return {"explicita": explicita, "explicita_com_til": explicita_com_til, "explicita_relativa": explicita_relativa,
            "explicita_vazia": explicita_vazia_cai_no_resto, "raiz": raiz_de_dados, "raiz_com_til": raiz_de_dados_com_til,
            "raiz_relativa": raiz_de_dados_relativa, "so_o_home": so_o_home, "explicita_vence": a_explicita_vence_a_raiz}


CENARIOS = ["explicita", "explicita_com_til", "explicita_relativa", "explicita_vazia", "raiz", "raiz_com_til", "raiz_relativa",
            "so_o_home", "explicita_vence"]


def _esperado_dados(env_data: str, sub: str) -> Path:
    """The rule every copy implements: the track's own variable, else <SIMPLICIO_VIDEO_DATA or ~/.simplicio-video>/<sub>; absolute."""
    explicita = os.environ.get(env_data)
    if explicita:
        return Path(explicita).expanduser().resolve()
    raiz = os.environ.get("SIMPLICIO_VIDEO_DATA")
    base = Path(raiz).expanduser() if raiz else Path(os.environ["HOME"]) / ".simplicio-video"
    return (base / sub).resolve()


def _data_dir_de(quem: str, nome: str):
    return _data_dir_de_hoje(nome) if quem == "modulo" else _trilha(nome).data_dir


@pytest.mark.parametrize("cenario", CENARIOS)
@pytest.mark.parametrize("nome", sorted(COM_DADOS))
@pytest.mark.parametrize("quem", ["modulo", "trilha"])
def test_data_dir_e_a_pasta_absoluta_de_sempre_em_cada_ambiente(monkeypatch, tmp_path, quem, nome, cenario):
    """`modulo` = the `data_dir` each track module has today (green); `trilha` = `Trilha.data_dir` (red until it exists)."""
    _, env_data, sub = COM_DADOS[nome]
    _cenarios_de_dados(monkeypatch, tmp_path, env_data)[cenario]()
    achado = _data_dir_de(quem, nome)()
    assert achado.is_absolute()
    assert achado == _esperado_dados(env_data, sub)


@pytest.mark.parametrize("nome", sorted(COM_DADOS))
def test_data_dir_sem_variavel_fica_numa_pasta_da_trilha_fora_do_checkout(monkeypatch, tmp_path, nome):
    _, _, sub = COM_DADOS[nome]
    assert _trilha(nome).data_dir() == (tmp_path / "data" / sub).resolve()
    monkeypatch.delenv("SIMPLICIO_VIDEO_DATA")
    assert _trilha(nome).data_dir() == (tmp_path / "home" / ".simplicio-video" / sub).resolve()


def test_data_dir_a_pasta_vem_do_nome_da_trilha_sem_sublinhado():
    """`rea_video` (the name in tools.TOOLS) keeps its data in `rea-video-data`: the folder is `<name with hyphens>-data`."""
    assert _tb().Trilha("rea_video", "REA_VIDEO_DIR").data_dir().name == "rea-video-data"
    assert _tb().Trilha("matchcut", "MATCHCUT_DIR").data_dir().name == "matchcut-data"


def test_data_dir_sem_env_data_nao_le_variavel_nenhuma_de_trilha(monkeypatch, tmp_path):
    monkeypatch.setenv("TOONFLOW_DATA_DIR", str(tmp_path / "nao-deve-valer"))
    assert _tb().Trilha("toonflow", "TOONFLOW_DIR").data_dir() == (tmp_path / "data" / "toonflow-data").resolve()


@pytest.mark.parametrize("nome", sorted(COM_DADOS))
@pytest.mark.parametrize("quem", ["modulo", "trilha"])
def test_data_dir_sem_home_e_a_recusa_que_diz_qual_variavel_escolhe_a_pasta(monkeypatch, quem, nome):
    _sem_casa(monkeypatch)
    with pytest.raises(hostos.SemCasa, match="SIMPLICIO_VIDEO_DATA") as caught:
        _data_dir_de(quem, nome)()
    assert "HOME" in str(caught.value)


@pytest.mark.parametrize("nome", sorted(COM_DADOS))
def test_data_dir_sem_home_a_recusa_da_trilha_e_a_do_modulo_palavra_por_palavra(monkeypatch, nome):
    _sem_casa(monkeypatch)
    with pytest.raises(hostos.SemCasa) as hoje:
        _data_dir_de_hoje(nome)()
    with pytest.raises(hostos.SemCasa) as novo:
        _trilha(nome).data_dir()
    assert str(novo.value) == str(hoje.value)


# ---- head() ------------------------------------------------------------------------------------------------------------------


def _checkout_head_de_hoje():
    from simplicio_video import moneyprinter, rea_video, video_to_skill
    return {"moneyprinter": moneyprinter._checkout_head, "rea_video": rea_video._checkout_head, "video_to_skill": video_to_skill._checkout_head}


def _head(n: str):
    return _checkout_head_de_hoje()[n]


@pytest.mark.parametrize("copia", ["moneyprinter", "rea_video", "video_to_skill", "trilha_base"])
def test_head_e_o_rev_parse_head_do_checkout(monkeypatch, tmp_path, copia):
    func = (lambda d: _trilha("toonflow").head(d)) if copia == "trilha_base" else _head(copia)
    vistos: list = []
    monkeypatch.setattr(tools, "_git", lambda *a, cwd=None: vistos.append((a, cwd)) or "a" * 40)
    assert func(tmp_path) is None and vistos == []  # without `.git` git would answer with the parent repository: never asked
    (tmp_path / ".git").mkdir()
    assert func(tmp_path) == "a" * 40
    assert vistos == [(("rev-parse", "HEAD"), tmp_path)]

    def quebrado(*a, cwd=None):
        raise tools.ToolError("git rev-parse: fatal")

    monkeypatch.setattr(tools, "_git", quebrado)
    assert func(tmp_path) is None


# ---- venv_python() -----------------------------------------------------------------------------------------------------------


def _venv_de(quem: str, nome: str):
    from simplicio_video import matchcut, moneyprinter, montage
    return {"matchcut": matchcut.venv_python, "moneyprinter": moneyprinter.venv_python, "openmontage": montage.venv_python}[nome] \
        if quem == "modulo" else _trilha(nome).venv_python


@pytest.mark.parametrize("nome", ["matchcut", "moneyprinter", "openmontage"])
@pytest.mark.parametrize("quem", ["modulo", "trilha"])
def test_venv_python_fica_no_venv_da_pasta_de_dados_da_trilha(monkeypatch, tmp_path, quem, nome):
    """`modulo` = the `venv_python` that matchcut, moneyprinter and montage have today (green); `trilha` = `Trilha.venv_python`."""
    monkeypatch.setenv(COM_DADOS[nome][1], str(tmp_path / "dados"))
    sub = ("Scripts", "python.exe") if os.name == "nt" else ("bin", "python")
    assert _venv_de(quem, nome)() == (tmp_path / "dados").resolve() / "venv" / sub[0] / sub[1]


def test_venv_python_esta_no_venv_da_pasta_de_dados():
    t = _trilha("moneyprinter")
    esperado = t.data_dir() / "venv" / ("Scripts" if os.name == "nt" else "bin") / ("python.exe" if os.name == "nt" else "python")
    assert t.venv_python() == esperado
    assert t.venv_python(Path("/algum/lugar")) == Path("/algum/lugar") / "venv" / esperado.parent.name / esperado.name


def test_venv_python_no_windows(monkeypatch):
    trilha, pasta = _trilha("toonflow"), Path("/d")  # built first: pathlib picks its flavour from os.name when a Path is made
    with monkeypatch.context() as m:
        m.setattr(_tb().os, "name", "nt")
        achado = trilha.venv_python(pasta)
    assert achado.parts[-3:] == ("venv", "Scripts", "python.exe")


# ---- clone() ----------------------------------------------------------------------------------------------------------------


class _Erro(Exception):
    pass


@pytest.fixture
def instalacoes(monkeypatch):
    """`tools.install` replaced: records (name, dir) and the environment it saw; the clone is online."""
    monkeypatch.delenv("SIMPLICIO_OFFLINE", raising=False)
    vistas: list = []

    def instala(name, **kw):
        vistas.append((name, kw.get("dir"), dict(os.environ)))
        return str(kw["dir"]) if kw.get("dir") is not None else f"/padrao/{name}"

    monkeypatch.setattr(tools, "install", instala)
    return vistas


def test_clone_offline_recusa_com_a_frase_unica_e_nao_instala(monkeypatch, instalacoes):
    monkeypatch.setenv("SIMPLICIO_OFFLINE", "1")
    with pytest.raises(_Erro) as caught:
        _trilha("toonflow").clone(None, erro=_Erro, acao="clonar o Toonflow. Instale fora do modo offline.")
    assert str(caught.value) == f"{PREFIXO}clonar o Toonflow. Instale fora do modo offline."
    assert instalacoes == []


def test_clone_offline_sem_acao_diz_qual_trilha_e_qual_variavel(monkeypatch, instalacoes):
    monkeypatch.setenv("SIMPLICIO_OFFLINE", "yes")
    with pytest.raises(_Erro) as caught:
        _trilha("rea_video").clone(erro=_Erro)
    mensagem = str(caught.value)
    assert mensagem.startswith(PREFIXO) and "rea_video" in mensagem and "REA_VIDEO_DIR" in mensagem
    assert instalacoes == []


def test_clone_pergunta_pelo_offline_que_o_chamador_passou(monkeypatch, instalacoes):
    """A track keeps its `_offline` name (tests replace it): it hands that function in, and it is the one that decides."""
    t = _trilha("toonflow")
    with pytest.raises(_Erro) as caught:
        t.clone(None, erro=_Erro, acao="clonar.", offline=lambda: True)  # the environment says online
    assert str(caught.value) == f"{PREFIXO}clonar." and instalacoes == []
    monkeypatch.setenv("SIMPLICIO_OFFLINE", "1")
    assert t.clone(None, erro=_Erro, acao="clonar.", offline=lambda: False) == Path("/padrao/toonflow")  # and the other way round


def test_clone_sem_pasta_instala_no_lugar_de_sempre(instalacoes):
    assert _trilha("toonflow").clone(erro=_Erro) == Path("/padrao/toonflow")
    assert instalacoes[0][:2] == ("toonflow", None)


def test_clone_com_pasta_instala_nela_e_nao_mexe_no_ambiente(monkeypatch, tmp_path, instalacoes):
    antes = dict(os.environ)
    alvo = tmp_path / "meu-checkout"
    assert _trilha("toonflow").clone(alvo, erro=_Erro) == alvo
    assert instalacoes[0][:2] == ("toonflow", alvo)
    assert instalacoes[0][2] == antes  # not even while tools.install runs
    assert dict(os.environ) == antes and "TOONFLOW_DIR" not in os.environ


def test_clone_expande_o_til_da_pasta(tmp_path, instalacoes):
    assert _trilha("toonflow").clone(Path("~/meu"), erro=_Erro) == tmp_path / "home" / "meu"
    assert instalacoes[0][1] == tmp_path / "home" / "meu"


def test_clone_trata_o_nome_da_trilha_como_o_nome_em_tools(instalacoes):
    _trilha("rea_video").clone(erro=_Erro)
    assert instalacoes[0][0] == "rea_video"


def test_clone_devolve_o_erro_da_trilha_com_a_mensagem_do_tools(monkeypatch, instalacoes):
    def falha(name, **kw):
        raise tools.ToolError("git clone --filter=blob:none: fatal: sem rede")

    monkeypatch.setattr(tools, "install", falha)
    with pytest.raises(_Erro) as caught:
        _trilha("toonflow").clone(erro=_Erro)
    assert str(caught.value) == "git clone --filter=blob:none: fatal: sem rede" and caught.value.__cause__ is None


@pytest.mark.skipif(SEM_GIT, reason="git is not installed on this machine")
def test_clone_de_verdade_de_um_upstream_falso(monkeypatch, tmp_path):
    """A local repository as the upstream: the checkout lands where it was asked, at the pinned commit, and the environment is intact."""
    ambiente = {"GIT_AUTHOR_NAME": "t", "GIT_COMMITTER_NAME": "t", "GIT_AUTHOR_EMAIL": "t@invalido.example",
                "GIT_COMMITTER_EMAIL": "t@invalido.example", "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull}
    for nome, valor in ambiente.items():
        monkeypatch.setenv(nome, valor)
    origem = tmp_path / "origem"
    origem.mkdir()
    (origem / "package.json").write_text("{}\n", encoding="utf-8")

    def git(pasta, *args):
        return subprocess.run(["git", *args], cwd=pasta, check=True, capture_output=True, text=True).stdout.strip()

    git(origem, "init", "-q")
    git(origem, "add", "-A")
    git(origem, "commit", "-q", "-m", "origem")
    commit = git(origem, "rev-parse", "HEAD")
    monkeypatch.setitem(tools.TOOLS, "opencut", dataclasses.replace(tools.get("opencut"), source=str(origem), ref=commit))
    monkeypatch.setattr(tools, "_git", _GIT_REAL)
    monkeypatch.delenv("SIMPLICIO_OFFLINE", raising=False)
    antes = dict(os.environ)
    trilha = _tb().Trilha("opencut", "OPENCUT_DIR")
    destino = tmp_path / "x" / "opencut"
    assert trilha.clone(destino, erro=_Erro) == destino
    assert (destino / "package.json").is_file() and trilha.head(destino) == commit
    assert dict(os.environ) == antes
    assert trilha.find() is None  # `find` follows the environment/cache, not the folder it was cloned to
    monkeypatch.setenv("OPENCUT_DIR", str(destino))
    assert trilha.find() == destino.resolve()


# ---- job_cwd() and drop_job_cwd() ---------------------------------------------------------------------------------------------


def _implementacoes_de_job():
    from simplicio_video import rea_video, video_to_skill
    return {
        "rea_video": (lambda: Path(rea_video.make_job_cwd()), rea_video.drop_job_cwd, rea_video.JOB_CWD_PREFIX),
        "video_to_skill": (lambda: Path(video_to_skill.make_job_cwd()), video_to_skill.drop_job_cwd, video_to_skill.JOB_CWD_PREFIX),
    }


def _job(quem: str):
    """(make, drop, prefix) of an implementation: the two copies of today, or trilha_base (with the prefix of rea-video)."""
    if quem == "trilha_base":
        tb = _tb()
        prefixo = "rea-video-job-"
        return (lambda: tb.job_cwd(prefixo)), (lambda p: tb.drop_job_cwd(p, prefixo)), prefixo
    return _implementacoes_de_job()[quem]


QUEM = ["rea_video", "video_to_skill", "trilha_base"]


@pytest.fixture
def temporaria(monkeypatch, tmp_path):
    base = tmp_path / "tmp"
    base.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(base))
    return base


def _velho(p: Path, dias: float) -> None:
    quando = time.time() - dias * 86400
    os.utime(p, (quando, quando))


@pytest.mark.parametrize("quem", QUEM)
def test_job_cwd_cria_uma_pasta_privada_vazia_com_o_prefixo_na_pasta_temporaria(temporaria, quem):
    make, _, prefixo = _job(quem)
    p = make()
    assert isinstance(p, Path) and p.is_dir() and p.parent == temporaria and p.name.startswith(prefixo)
    assert list(p.iterdir()) == []
    if os.name == "posix":
        assert p.stat().st_mode & 0o777 == 0o700


@pytest.mark.parametrize("quem", QUEM)
def test_job_cwd_varre_so_as_pastas_vazias_antigas_com_o_prefixo(temporaria, quem):
    make, _, prefixo = _job(quem)
    velha = temporaria / f"{prefixo}velha"
    velha.mkdir()
    recente = temporaria / f"{prefixo}recente"
    recente.mkdir()
    velha_cheia = temporaria / f"{prefixo}velha-cheia"
    velha_cheia.mkdir()
    (velha_cheia / "resultado.json").write_text("{}", encoding="utf-8")
    de_outro = temporaria / "outro-prefixo-velha"
    de_outro.mkdir()
    arquivo_velho = temporaria / f"{prefixo}arquivo"
    arquivo_velho.write_text("x", encoding="utf-8")
    for p in (velha, velha_cheia, de_outro, arquivo_velho):
        _velho(p, 8)
    _velho(recente, 6)
    nova = make()
    assert not velha.exists()  # old and empty: swept
    assert recente.exists() and velha_cheia.exists() and de_outro.exists() and arquivo_velho.exists()
    assert nova.exists() and nova not in (velha, recente)


def test_job_cwd_a_idade_maxima_e_um_parametro_com_padrao_de_sete_dias(temporaria):
    tb = _tb()
    assert inspect.signature(tb.job_cwd).parameters["idade_max_s"].default == 7 * 86400
    prefixo = "x-job-"
    meia_hora = temporaria / f"{prefixo}meia-hora"
    meia_hora.mkdir()
    _velho(meia_hora, 1 / 48)
    tb.job_cwd(prefixo)
    assert meia_hora.exists()  # younger than a week: kept by the default
    tb.job_cwd(prefixo, idade_max_s=60)
    assert not meia_hora.exists()  # older than a minute: swept


@pytest.mark.parametrize("quem", QUEM)
def test_drop_job_cwd_so_remove_a_pasta_vazia_nossa_direto_na_temporaria(temporaria, quem):
    make, drop, prefixo = _job(quem)
    p = make()
    drop(p)
    assert not p.exists()
    cheia = make()
    (cheia / "x").write_text("x", encoding="utf-8")
    drop(cheia)
    assert cheia.exists()  # not empty: kept
    de_outro = temporaria / "outro-prefixo-x"
    de_outro.mkdir()
    drop(de_outro)
    assert de_outro.exists()
    aninhada = temporaria / "sub" / f"{prefixo}x"
    aninhada.mkdir(parents=True)
    drop(aninhada)
    assert aninhada.exists()  # its parent is not the temp folder: not ours
    p2 = make()
    drop(str(p2))  # a str is accepted
    assert not p2.exists()


@pytest.mark.parametrize("quem", QUEM)
@pytest.mark.parametrize("nada", [None, "", "nao/existe/e-nem-tem-o-prefixo"])
def test_drop_job_cwd_de_nada_nao_faz_nada_e_nao_levanta(temporaria, quem, nada):
    _, drop, _ = _job(quem)
    drop(nada)


@pytest.mark.parametrize("quem", QUEM)
def test_drop_job_cwd_de_pasta_que_ja_foi_nao_levanta(temporaria, quem):
    make, drop, _ = _job(quem)
    p = make()
    p.rmdir()
    drop(p)


@pytest.mark.parametrize("prefixo", ["", "a/b-", "a\\b-", "x*", "x?", "[x]-"])
def test_o_prefixo_da_pasta_de_tarefa_nao_pode_ser_vazio_nem_ter_separador_nem_curinga(temporaria, prefixo):
    """The sweep removes empty folders under the temp folder by prefix: an empty or glob-like prefix would reach folders that are not ours."""
    tb = _tb()
    velha = temporaria / "qualquer-coisa"
    velha.mkdir()
    _velho(velha, 30)
    with pytest.raises(ValueError):
        tb.job_cwd(prefixo)
    with pytest.raises(ValueError):
        tb.drop_job_cwd(velha, prefixo)
    assert velha.exists()


# ---- stop_group() and on_term() ---------------------------------------------------------------------------------------------


def _implementacoes_de_parada():
    from simplicio_video import toonflow
    return {"toonflow": toonflow._stop_group, "trilha_base": lambda proc: _tb().stop_group(proc, 15)}


def _espera(cond, segundos=20.0):
    fim = time.time() + segundos
    while time.time() < fim:
        if cond():
            return True
        time.sleep(0.05)
    return False


def _viva(pid: int) -> bool:
    """Linux: a zombie counts as gone, since it no longer runs and no longer holds the port."""
    try:
        estado = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0]
    except (FileNotFoundError, ProcessLookupError):
        return False
    return estado != "Z"


def _lanca(tmp_path, codigo: str):
    """A child in its own session (so its own process group), and the pid it writes once it is ready."""
    pronto = tmp_path / "pronto"
    proc = subprocess.Popen([sys.executable, "-c", codigo, str(pronto)], start_new_session=True,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    assert _espera(lambda: pronto.exists() and pronto.read_text().strip()), "o filho não ficou pronto"
    return proc, int(pronto.read_text())


SO_DORME = ("import signal, sys, time\n"
            "signal.signal(signal.SIGINT, signal.default_int_handler)\n"  # whatever the parent's disposition was
            "open(sys.argv[1], 'w').write('1')\n"
            "time.sleep(600)\n")
TEIMOSO = ("import signal, sys, time\n"
           "signal.signal(signal.SIGINT, signal.SIG_IGN)\n"
           "open(sys.argv[1], 'w').write('1')\n"
           "time.sleep(600)\n")
COM_NETO = '''import pathlib, signal, subprocess, sys, time
signal.signal(signal.SIGINT, signal.default_int_handler)
neto_pronto = sys.argv[1] + ".neto"
NETO = "import signal, sys, time\\nsignal.signal(signal.SIGINT, signal.SIG_IGN)\\nopen(sys.argv[1], 'w').write('1')\\ntime.sleep(600)"
neto = subprocess.Popen([sys.executable, "-c", NETO, neto_pronto])
while not pathlib.Path(neto_pronto).exists():
    time.sleep(0.02)
open(sys.argv[1], 'w').write(str(neto.pid))
time.sleep(600)
'''


@POSIX
@COM_PROC
@pytest.mark.parametrize("quem", ["toonflow", "trilha_base"])
def test_stop_group_mata_tambem_o_neto_que_ignora_o_sigint(tmp_path, quem):
    parar = _implementacoes_de_parada()[quem]
    proc, neto = _lanca(tmp_path, COM_NETO)
    try:
        assert _viva(neto)
        parar(proc)
        assert proc.poll() is not None
        assert _espera(lambda: not _viva(neto), 5), "the helper of the group outlived the stop"
    finally:
        if proc.poll() is None:
            proc.kill()


@POSIX
@pytest.mark.parametrize("quem", ["toonflow", "trilha_base"])
def test_stop_group_para_quem_atende_o_sigint_sem_esperar_o_prazo(tmp_path, quem):
    parar = _implementacoes_de_parada()[quem]
    proc, _ = _lanca(tmp_path, SO_DORME)
    try:
        t0 = time.time()
        parar(proc)
        assert proc.poll() is not None and time.time() - t0 < 10
        assert proc.returncode != 0
    finally:
        if proc.poll() is None:
            proc.kill()


@POSIX
def test_stop_group_passado_o_prazo_vai_para_o_sigkill(tmp_path):
    proc, _ = _lanca(tmp_path, TEIMOSO)
    try:
        t0 = time.time()
        _tb().stop_group(proc, 0.5)
        assert proc.returncode == -signal.SIGKILL
        assert 0.4 <= time.time() - t0 < 10
    finally:
        if proc.poll() is None:
            proc.kill()


@POSIX
@pytest.mark.parametrize("quem", ["toonflow", "trilha_base"])
def test_stop_group_de_um_grupo_que_ja_acabou_nao_levanta(tmp_path, quem):
    parar = _implementacoes_de_parada()[quem]
    proc, _ = _lanca(tmp_path, SO_DORME)
    proc.kill()
    proc.wait()
    parar(proc)


def test_stop_group_tem_prazo_padrao_de_15_segundos():
    """The `_stop_group` of toonflow waited 15 s for the group: the default keeps it."""
    assert inspect.signature(_tb().stop_group).parameters["grace_s"].default == 15


@pytest.mark.parametrize("quem", ["toonflow", "trilha_base"])
def test_on_term_levanta_keyboardinterrupt_como_o_ctrl_c(quem):
    from simplicio_video import toonflow
    funcao = toonflow._on_term if quem == "toonflow" else _tb().on_term
    with pytest.raises(KeyboardInterrupt):
        funcao(signal.SIGTERM, None)
    with pytest.raises(KeyboardInterrupt):
        funcao(signal.SIGHUP if hasattr(signal, "SIGHUP") else signal.SIGTERM, object())


def test_trilha_base_nao_importa_nenhuma_trilha():
    """The base is below the tracks: it imports `tools`, `rede` and `paths` (and the standard library), never a track. `paths` since V1: the
    data folder rule is `paths.data_root()` (it was `hostos.home_absoluta`, called here)."""
    import ast
    fonte = Path(_tb().__file__).read_text(encoding="utf-8")
    importados = set()
    for no in ast.walk(ast.parse(fonte)):
        if isinstance(no, ast.ImportFrom) and no.level == 1:
            importados.update(a.name if not no.module else no.module for a in no.names)
        elif isinstance(no, ast.Import):
            importados.update(a.name for a in no.names)
    trilhas = {"toonflow", "moneyprinter", "rea_video", "opencut", "matchcut", "instagram", "montage", "video_to_skill", "busca",
               "voicestudio", "download", "clone", "jobs", "cli", "mcp_server"}
    assert not importados & trilhas, importados & trilhas
    assert importados & {"tools", "rede", "paths"} == {"tools", "rede", "paths"}
