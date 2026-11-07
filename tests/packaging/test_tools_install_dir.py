"""U08.0, public API of `tools`: `install(name, dir=)`, the public `git` and `git_head`, and the `--` of `git clone`.

* `install(name, dir=...)` puts the checkout of a git track at `dir` and neither reads nor writes `os.environ` for the location (today
  seven track modules point `tools.install` at a folder by writing `<NAME>_DIR` into the environment of the whole process).
* `git clone --filter=blob:none -- <source> <dir>` (tools.install and the update's apply_git): a relative `dir` that starts with `-`
  was read by git as an option.
* `tools.git(...)` is the public name of the one git runner and `tools.git_head(d)` the one `rev-parse HEAD` of a checkout. The
  hermetic fixture replaces `tools._git` in every unit test: that name stays, and the public one goes through it.

The unit tests record the arguments of a fake git (the hermetic suite refuses a real one); two tests use the real git on a local
repository (skipped without git).
"""
from __future__ import annotations

import dataclasses
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from simplicio_video import tools, tools_update

REAL_GIT = tools._git  # the hermetic fixture swaps tools._git for a refusal in every test: this is the one the module defines

GIT_TRACKS = [t.name for t in tools.TOOLS.values() if t.kind == "git" and t.name != "video-use"]
SEM_GIT = shutil.which("git") is None


def _gravador(chamadas: list, ambientes: list | None = None, devolve: str = ""):
    def git(*args, cwd=None):
        chamadas.append((args, cwd))
        if ambientes is not None:
            ambientes.append(dict(os.environ))
        return devolve
    return git


# ---- the `--` before the folder (the defect: red before U08.0) -------------------------------------------------------------


@pytest.mark.parametrize("nome", GIT_TRACKS)
def test_o_clone_do_install_separa_o_diretorio_com_dois_tracos(monkeypatch, tmp_path, nome):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SIMPLICIO_TOOLS_DIR", "-x")
    chamadas: list = []
    monkeypatch.setattr(tools, "_git", _gravador(chamadas))
    tools.install(nome)
    clone = chamadas[0][0]
    assert clone == ("clone", "--filter=blob:none", "--", tools.get(nome).source, str(Path("-x") / nome)), clone


def test_o_clone_do_install_de_video_use_tambem_tem_os_dois_tracos(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("VIDEO_USE_DIR", "-x/video-use")
    chamadas: list = []
    monkeypatch.setattr(tools, "_git", _gravador(chamadas))
    tools.install("video-use")
    assert chamadas[0][0] == ("clone", "--filter=blob:none", "--", tools.get("video-use").source, "-x/video-use"), chamadas[0][0]


def test_o_clone_do_update_separa_o_diretorio_com_dois_tracos(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SIMPLICIO_TOOLS_DIR", "-x")
    t = tools.get("opencut")
    comandos: list = []

    def run(argv, cwd=None):
        argv = [str(a) for a in argv]
        comandos.append(argv)
        if argv[:2] == ["git", "clone"]:  # the clone leaves a checkout that has the registry marker
            alvo = Path(argv[-1])
            (alvo / ".git").mkdir(parents=True)
            (alvo / t.marker).write_text("{}\n", encoding="utf-8")
        return subprocess.CompletedProcess(argv, 0, "a" * 40 + "\n", "")

    tools_update.apply_git(t, "b" * 40, tools_update.Io(network=True, run=run, which=lambda n: f"/fake/{n}"))
    assert comandos[0] == ["git", "clone", "--filter=blob:none", "--", t.source, str(Path("-x") / "opencut")], comandos[0]


@pytest.mark.skipif(SEM_GIT, reason="git is not installed on this machine")
def test_um_diretorio_relativo_que_comeca_com_traco_clona_de_verdade(monkeypatch, tmp_path):
    """The real git: before the `--`, `-x/opencut` was an option and the clone died with `unknown switch`."""
    origem = tmp_path / "origem"
    origem.mkdir()
    (origem / "package.json").write_text("{}\n", encoding="utf-8")
    ambiente = {"GIT_AUTHOR_NAME": "t", "GIT_COMMITTER_NAME": "t", "GIT_AUTHOR_EMAIL": "t@invalido.example",
                "GIT_COMMITTER_EMAIL": "t@invalido.example", "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull}

    def git(pasta, *args):
        return subprocess.run(["git", *args], cwd=pasta, check=True, capture_output=True, text=True,
                              env={**os.environ, **ambiente}).stdout.strip()

    git(origem, "init", "-q")
    git(origem, "add", "-A")
    git(origem, "commit", "-q", "-m", "origem")
    commit = git(origem, "rev-parse", "HEAD")
    monkeypatch.setitem(tools.TOOLS, "opencut", dataclasses.replace(tools.get("opencut"), source=str(origem), ref=commit))
    for nome, valor in ambiente.items():
        monkeypatch.setenv(nome, valor)
    monkeypatch.setattr(tools, "_git", REAL_GIT)
    monkeypatch.setenv("SIMPLICIO_TOOLS_DIR", "-x")
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    monkeypatch.chdir(cwd)
    assert tools.install("opencut") == str(Path("-x") / "opencut")
    assert (cwd / "-x" / "opencut" / "package.json").is_file()
    assert git(cwd / "-x" / "opencut", "rev-parse", "HEAD") == commit


# ---- install(name, dir=) ---------------------------------------------------------------------------------------------------


def test_install_com_dir_instala_ali_e_nao_le_nem_escreve_o_ambiente(monkeypatch, tmp_path):
    destino = tmp_path / "meu" / "opencut"
    outro = tmp_path / "outro"
    monkeypatch.setenv("OPENCUT_DIR", str(outro / "a"))
    monkeypatch.setenv("SIMPLICIO_OPENCUT_DIR", str(outro / "b"))
    monkeypatch.setenv("SIMPLICIO_TOOLS_DIR", str(outro / "tools"))
    antes = dict(os.environ)
    chamadas: list = []
    ambientes: list = []
    monkeypatch.setattr(tools, "_git", _gravador(chamadas, ambientes))
    assert tools.install("opencut", dir=destino) == str(destino)
    assert dict(os.environ) == antes
    assert ambientes and all(env == antes for env in ambientes)  # not even while the commands run
    assert chamadas[0][0][0] == "clone" and chamadas[0][0][-1] == str(destino)
    assert [c for _, c in chamadas[1:]] == [destino, destino]  # fetch and checkout run inside it
    assert not outro.exists() and (tmp_path / "meu").is_dir()


@pytest.mark.parametrize("nome", GIT_TRACKS)
def test_install_com_dir_vale_para_toda_trilha_git(monkeypatch, tmp_path, nome):
    destino = tmp_path / "x" / nome
    chamadas: list = []
    monkeypatch.setattr(tools, "_git", _gravador(chamadas))
    antes = dict(os.environ)
    assert tools.install(nome, dir=destino) == str(destino)
    assert chamadas[0][0][-2:] == (tools.get(nome).source, str(destino))
    assert chamadas[-1][0] == ("checkout", "--quiet", "--detach", tools.effective_ref(tools.get(nome)))
    assert dict(os.environ) == antes


def test_install_de_video_use_com_dir_nao_le_o_video_use_dir(monkeypatch, tmp_path):
    destino = tmp_path / "vu"
    chamadas: list = []
    monkeypatch.setattr(tools, "_git", _gravador(chamadas))
    assert tools.install("video-use", dir=destino) == str(destino)  # conftest points VIDEO_USE_DIR somewhere else
    assert chamadas[0][0][-1] == str(destino)


def test_install_com_dir_expande_o_til_como_o_checkout_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    chamadas: list = []
    monkeypatch.setattr(tools, "_git", _gravador(chamadas))
    assert tools.install("opencut", dir=Path("~/pasta")) == str(tmp_path / "pasta")


def test_install_com_dir_continua_recusando_o_override_que_e_uma_opcao(monkeypatch, tmp_path):
    monkeypatch.setenv("SIMPLICIO_OPENCUT_REF", "--force")
    chamadas: list = []
    monkeypatch.setattr(tools, "_git", _gravador(chamadas))
    with pytest.raises(tools.ToolError):
        tools.install("opencut", dir=tmp_path / "x")
    assert chamadas == [] and not (tmp_path / "x").exists()


def test_install_com_dir_usa_o_override_de_commit(monkeypatch, tmp_path):
    monkeypatch.setenv("SIMPLICIO_OPENCUT_REF", "abc1234")
    chamadas: list = []
    monkeypatch.setattr(tools, "_git", _gravador(chamadas))
    tools.install("opencut", dir=tmp_path / "x")
    assert chamadas[-1][0] == ("checkout", "--quiet", "--detach", "abc1234")


@pytest.mark.parametrize("nome", ["hypit", "tinyfish", "yt-dlp"])
def test_dir_so_vale_para_trilha_git(monkeypatch, tmp_path, nome):
    """An npm track has no checkout and a pip track keeps its venv in the tools cache: `dir` there is an error, never ignored."""
    chamadas: list = []
    monkeypatch.setattr(tools, "_git", _gravador(chamadas))
    monkeypatch.setattr(tools.subprocess, "run", lambda *a, **k: pytest.fail("nothing may run"))
    with pytest.raises(tools.ToolError, match="dir"):
        tools.install(nome, dir=tmp_path / "x")
    assert chamadas == [] and not (tmp_path / "x").exists()


# ---- install(name) without dir: what it does today (green before and after) ---------------------------------------------


def test_install_sem_dir_usa_o_ambiente_como_sempre(monkeypatch, tmp_path):
    """Without `dir` the location is still: {NAME}_DIR, else SIMPLICIO_{NAME}_DIR, else SIMPLICIO_TOOLS_DIR/<name>."""
    chamadas: list = []
    monkeypatch.setattr(tools, "_git", _gravador(chamadas))
    monkeypatch.setenv("SIMPLICIO_TOOLS_DIR", str(tmp_path / "tools"))
    assert tools.install("opencut") == str(tmp_path / "tools" / "opencut")
    monkeypatch.setenv("SIMPLICIO_OPENCUT_DIR", str(tmp_path / "simplicio"))
    assert tools.install("opencut") == str(tmp_path / "simplicio")
    monkeypatch.setenv("OPENCUT_DIR", str(tmp_path / "direto"))
    assert tools.install("opencut") == str(tmp_path / "direto")


def test_dir_none_e_o_comportamento_de_hoje(monkeypatch, tmp_path):
    chamadas: list = []
    monkeypatch.setattr(tools, "_git", _gravador(chamadas))
    monkeypatch.setenv("OPENCUT_DIR", str(tmp_path / "direto"))
    assert tools.install("opencut", dir=None) == str(tmp_path / "direto")


def test_install_sem_dir_nao_clona_de_novo_um_checkout_existente(monkeypatch, tmp_path):
    destino = tmp_path / "tools" / "opencut"
    (destino / ".git").mkdir(parents=True)
    chamadas: list = []
    monkeypatch.setattr(tools, "_git", _gravador(chamadas))
    monkeypatch.setenv("SIMPLICIO_TOOLS_DIR", str(tmp_path / "tools"))
    ref = tools.get("opencut").ref
    tools.install("opencut")
    assert [a for a, _ in chamadas] == [("fetch", "--quiet", "origin", ref), ("checkout", "--quiet", "--detach", ref)]
    assert [c for _, c in chamadas] == [destino, destino]


def test_install_com_dir_nao_clona_de_novo_um_checkout_existente(monkeypatch, tmp_path):
    destino = tmp_path / "meu"
    (destino / ".git").mkdir(parents=True)
    chamadas: list = []
    monkeypatch.setattr(tools, "_git", _gravador(chamadas))
    ref = tools.get("opencut").ref
    tools.install("opencut", dir=destino)
    assert [a for a, _ in chamadas] == [("fetch", "--quiet", "origin", ref), ("checkout", "--quiet", "--detach", ref)]


# ---- the public git and git_head -------------------------------------------------------------------------------------------


def test_git_e_o_nome_publico_e_o_nome_antigo_continua_no_modulo():
    assert callable(tools.git)
    assert callable(REAL_GIT)  # `_git` is still a module name (the hermetic fixture and many tests replace it)


def test_o_git_publico_passa_pelo_nome_que_os_testes_trocam(monkeypatch, tmp_path):
    """The hermetic fixture replaces `tools._git`: a caller of the public `git` must be covered by it, not run a real git."""
    vistos: list = []

    def falso(*args, cwd=None):  # a narrow signature (as many fakes of the suite): only what the caller gave is passed on
        vistos.append((args, cwd))
        return "resposta"

    monkeypatch.setattr(tools, "_git", falso)
    assert tools.git("rev-parse", "HEAD") == "resposta"
    assert tools.git("rev-parse", "HEAD", cwd=tmp_path) == "resposta"
    assert vistos == [(("rev-parse", "HEAD"), None), (("rev-parse", "HEAD"), tmp_path)]


def test_o_git_publico_repassa_o_timeout_quando_ha(monkeypatch):
    vistos: list = []
    monkeypatch.setattr(tools, "_git", lambda *args, cwd=None, timeout=None: vistos.append((args, cwd, timeout)) or "")
    tools.git("ls-remote", timeout=5)
    assert vistos == [(("ls-remote",), None, 5)]


@pytest.mark.skipif(SEM_GIT, reason="git is not installed on this machine")
def test_o_git_publico_roda_o_git_de_verdade_e_falha_como_toolerror(monkeypatch):
    monkeypatch.setattr(tools, "_git", REAL_GIT)
    assert tools.git("--version").startswith("git version")
    with pytest.raises(tools.ToolError, match="git"):
        tools.git("este-subcomando-nao-existe")


def test_git_head_sem_dot_git_e_none_e_nao_roda_o_git(monkeypatch, tmp_path):
    """Without `.git` git would answer with the parent repository: not this checkout."""
    monkeypatch.setattr(tools, "_git", lambda *a, **k: pytest.fail("git must not run"))
    assert tools.git_head(tmp_path) is None


def test_git_head_devolve_o_commit_do_checkout(monkeypatch, tmp_path):
    (tmp_path / ".git").mkdir()
    chamadas: list = []
    monkeypatch.setattr(tools, "_git", _gravador(chamadas, devolve="f" * 40))
    assert tools.git_head(tmp_path) == "f" * 40
    assert chamadas == [(("rev-parse", "HEAD"), tmp_path)]


def test_git_head_com_dot_git_arquivo_de_worktree_tambem_vale(monkeypatch, tmp_path):
    (tmp_path / ".git").write_text("gitdir: /algum/lugar\n", encoding="utf-8")
    monkeypatch.setattr(tools, "_git", _gravador([], devolve="e" * 40))
    assert tools.git_head(tmp_path) == "e" * 40


def test_git_head_de_um_git_que_falha_e_none(monkeypatch, tmp_path):
    (tmp_path / ".git").mkdir()

    def quebrado(*args, cwd=None):
        raise tools.ToolError("git rev-parse: fatal")

    monkeypatch.setattr(tools, "_git", quebrado)
    assert tools.git_head(tmp_path) is None


@pytest.mark.skipif(SEM_GIT, reason="git is not installed on this machine")
def test_git_head_de_um_repositorio_de_verdade(monkeypatch, tmp_path):
    ambiente = {"GIT_AUTHOR_NAME": "t", "GIT_COMMITTER_NAME": "t", "GIT_AUTHOR_EMAIL": "t@invalido.example",
                "GIT_COMMITTER_EMAIL": "t@invalido.example", "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull}
    for nome, valor in ambiente.items():
        monkeypatch.setenv(nome, valor)
    monkeypatch.setattr(tools, "_git", REAL_GIT)
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-q", "--allow-empty", "-m", "c"], cwd=tmp_path, check=True, capture_output=True)
    esperado = subprocess.run(["git", "rev-parse", "HEAD"], cwd=tmp_path, check=True, capture_output=True, text=True).stdout.strip()
    assert tools.git_head(tmp_path) == esperado and len(esperado) == 40
