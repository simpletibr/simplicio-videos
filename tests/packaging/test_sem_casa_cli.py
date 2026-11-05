"""No home folder (no HOME, no USERPROFILE, no passwd entry), and the guarantees of the whole CLI (review of PR #182, round 4).

`hostos.home_dir()` hands back the relative `~` when nothing resolves a home, and a mkdir on it makes a folder literally named `~`
in the cwd. So: every command that needs the home refuses with ONE clean message (exit 2, no traceback), the ones that only look
do not crash, and none of them creates anything. A blank HOME is no home either (Python answers `/` for it), and `home_dir()`
without an argument reads the environment like the code that passes it (a Windows USERPROFILE).
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from simplicio_video import hostos, paths, tools
from simplicio_video.cli import main


def _sem_casa(monkeypatch):
    for nome in list(os.environ):
        if nome in ("HOME", "USERPROFILE", "OPENMONTAGE_DIR") or nome.endswith("_DIR") or nome.startswith("SIMPLICIO_"):
            monkeypatch.delenv(nome, raising=False)

    def sem(cls):
        raise RuntimeError("Could not determine home directory.")

    monkeypatch.setattr(Path, "home", classmethod(sem))


RECUSAM = [
    ["status"], ["status", "--json"], ["tools"], ["setup", "--yes"], ["jobs", "list"],
    ["toonflow", "status"], ["toonflow", "where"], ["moneyprinter", "status"], ["moneyprinter", "where"],
    ["opencut", "where"], ["opencut", "status"], ["instagram", "status"], ["instagram", "where"],
    ["matchcut", "status"], ["matchcut", "where"], ["rea-video", "status"], ["rea-video", "where"],
    ["montage", "where"], ["montage", "status"],
    ["media", "fetch", "http://example.invalid/x", "-o", "x.mp4", "--autorizo"],
]
SO_OLHAM = [
    ["doctor", "update"], ["doctor", "tools"], ["doctor", "disk"], ["doctor", "trilhas"], ["doctor", "trilhas", "--json"], ["update", "--check"], ["install", "--check"],
    ["busca", "status"], ["openverse", "library", "list"], ["social", "providers"], ["clone", "status"],
]


@pytest.mark.parametrize("argv", RECUSAM, ids=lambda a: " ".join(a[:3]))
def test_sem_HOME_o_comando_recusa_com_uma_mensagem_sem_traceback_e_sem_criar_nada(monkeypatch, tmp_path, capsys, argv):
    _sem_casa(monkeypatch)
    monkeypatch.chdir(tmp_path)
    rc = main(list(argv))  # an exception here is the traceback
    saida = capsys.readouterr()
    assert rc == 2, (rc, saida.out[-300:], saida.err[-300:])
    assert "HOME" in saida.err and "Traceback" not in saida.err + saida.out
    assert list(tmp_path.iterdir()) == [], [p.name for p in tmp_path.iterdir()]


@pytest.mark.parametrize("argv", SO_OLHAM, ids=lambda a: " ".join(a[:3]))
def test_sem_HOME_o_que_so_olha_nao_quebra_e_nao_cria_nada(monkeypatch, tmp_path, capsys, argv):
    _sem_casa(monkeypatch)
    monkeypatch.setenv("SIMPLICIO_OFFLINE", "1")
    monkeypatch.chdir(tmp_path)
    try:
        main(list(argv))
    except SystemExit:
        pass
    assert "Traceback" not in capsys.readouterr().err
    assert list(tmp_path.iterdir()) == [], [p.name for p in tmp_path.iterdir()]


def test_HOME_vazio_nao_e_um_home(monkeypatch):
    """HOME="" makes Python answer `/` (a folder `/.simplicio-video` at the root of the disk): it is no home, and USERPROFILE wins."""
    _sem = [n for n in os.environ if n.startswith("SIMPLICIO_") or n.endswith("_DIR") or n == "USERPROFILE"]
    for nome in _sem:
        monkeypatch.delenv(nome, raising=False)
    monkeypatch.setenv("HOME", "")
    with pytest.raises(hostos.SemCasa):
        hostos.home_absoluta()
    with pytest.raises(hostos.SemCasa):
        paths.workspace_dir()
    assert hostos.home_dir() == Path("~")  # nothing that can be written to: a read finds nothing


def test_HOME_vazio_com_USERPROFILE_usa_o_perfil(monkeypatch, tmp_path):
    for nome in [n for n in os.environ if n.startswith("SIMPLICIO_") or n.endswith("_DIR")]:
        monkeypatch.delenv(nome, raising=False)
    monkeypatch.setenv("HOME", "")
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "perfil"))
    assert paths.workspace_dir() == tmp_path / "perfil" / ".simplicio-video" / "workspaces" / "default"
    assert hostos.home_absoluta() == tmp_path / "perfil"


def test_home_dir_sem_argumento_le_o_ambiente(monkeypatch, tmp_path):
    """`hostos.home_dir()` without an environment is home_dir(os.environ): the workspace, the data folders and the doctor agree."""
    for nome in [n for n in os.environ if n.startswith("SIMPLICIO_") or n.endswith("_DIR") or n == "HOME"]:
        monkeypatch.delenv(nome, raising=False)
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "perfil"))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "outro"))
    assert hostos.home_dir() == tmp_path / "perfil"
    assert paths.workspace_dir() == tmp_path / "perfil" / ".simplicio-video" / "workspaces" / "default"


def test_a_mensagem_cita_a_variavel_que_resolve_aquela_pasta(monkeypatch, tmp_path):
    """SIMPLICIO_TOOLS_DIR does not choose the video-use checkout (VIDEO_USE_DIR does): each refusal names what really helps."""
    _sem_casa(monkeypatch)
    monkeypatch.chdir(tmp_path)
    with pytest.raises(tools.ToolError) as video_use:
        tools.install("video-use")
    assert "VIDEO_USE_DIR" in str(video_use.value) and "SIMPLICIO_TOOLS_DIR" not in str(video_use.value)
    with pytest.raises(tools.ToolError) as opencut:
        tools.install("opencut")
    assert "SIMPLICIO_TOOLS_DIR" in str(opencut.value)
    with pytest.raises(hostos.SemCasa) as dados:
        paths.workspace_dir()
    assert "SIMPLICIO_WORKSPACE" in str(dados.value)


def test_o_cache_do_update_sem_HOME_nao_cria_pasta_e_nao_quebra(monkeypatch, tmp_path):
    """`update --check` and `doctor --online` write update-check.json: with no home that is a best-effort cache that is not written
    (and never a `~` folder); reading it answers "no check yet"."""
    from simplicio_video.commands import update
    _sem_casa(monkeypatch)
    monkeypatch.chdir(tmp_path)
    update.write_check({"installed": "0.6.0", "latest": "0.7.0", "update_available": True, "kind": "pip"})
    assert list(tmp_path.iterdir()) == []
    assert update.read_check() is None
    with pytest.raises(hostos.SemCasa):
        update.default_state_dir()
