from __future__ import annotations

import os
import re
import signal
from pathlib import Path

import pytest

from simplicio_video import cli, clone, mcp_server, montage


def test_clone_find_hypit_bin_fallback(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda cmd: "/usr/bin/npx" if cmd == "npx" else None)
    bin_cmd = clone.find_hypit_bin()
    assert bin_cmd == ["/usr/bin/npx", "--yes", "@hypit/hypit@0.3.1"]  # pinned in tools.TOOLS


def test_clone_find_hypit_bin_local(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda cmd: "/usr/local/bin/hypit" if cmd == "hypit" else None)
    bin_cmd = clone.find_hypit_bin()
    assert bin_cmd == ["/usr/local/bin/hypit"]


def test_clone_find_hypit_bin_missing(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda cmd: None)
    with pytest.raises(clone.CloneError, match="Nem `hypit` nem `npx` foram encontrados"):
        clone.find_hypit_bin()


def test_clone_run_hypit_invokes_subprocess(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda cmd: "/usr/local/bin/hypit" if cmd == "hypit" else None)
    recorded = []
    monkeypatch.setattr("subprocess.call", lambda cmd, cwd=None: recorded.append((cmd, cwd)) or 0)
    ret = clone.run_hypit(["video.mp4"])
    assert ret == 0
    assert recorded == [(["/usr/local/bin/hypit", "video.mp4"], None)]


def test_clone_main_error_handling(monkeypatch, capsys):
    monkeypatch.setattr(clone, "run_hypit", lambda args: (_ for _ in ()).throw(clone.CloneError("falha teste")))
    ret = clone.main([])
    assert ret == 1
    assert "clone: falha teste" in capsys.readouterr().err


def test_montage_find_openmontage_dir_env(monkeypatch, tmp_path):
    d = tmp_path / "custom_openmontage"
    (d / "backlot").mkdir(parents=True)
    monkeypatch.setenv("OPENMONTAGE_DIR", str(d))
    found = montage.find_openmontage_dir()
    assert found == d.resolve()


def test_montage_find_openmontage_dir_default(monkeypatch, tmp_path):
    monkeypatch.delenv("OPENMONTAGE_DIR", raising=False)
    monkeypatch.delenv("SIMPLICIO_OPENMONTAGE_DIR", raising=False)
    monkeypatch.setenv("SIMPLICIO_TOOLS_DIR", str(tmp_path))
    assert montage.find_openmontage_dir() is None  # no hardcoded machine paths
    (tmp_path / "openmontage" / "backlot").mkdir(parents=True)
    assert montage.find_openmontage_dir() == (tmp_path / "openmontage").resolve()


def test_tools_install_checks_out_the_pinned_commit(monkeypatch, tmp_path):
    from simplicio_video import tools
    monkeypatch.delenv("OPENMONTAGE_DIR", raising=False)
    monkeypatch.setenv("SIMPLICIO_TOOLS_DIR", str(tmp_path))
    calls = []
    monkeypatch.setattr(tools, "_git", lambda *a, cwd=None: calls.append(a) or "")
    assert tools.install("openmontage") == str(tmp_path / "openmontage")
    ref = tools.TOOLS["openmontage"].ref
    assert calls[0][0] == "clone" and calls[-1] == ("checkout", "--quiet", "--detach", ref)
    monkeypatch.setenv("SIMPLICIO_OPENMONTAGE_REF", "abc1234")
    calls.clear()
    tools.install("openmontage")
    assert calls[-1][-1] == "abc1234"


@pytest.fixture
def fake_checkout(monkeypatch, tmp_path):
    """A stand-in OpenMontage checkout: the run tests never clone anything."""
    d = tmp_path / "openmontage"
    (d / "backlot").mkdir(parents=True)
    monkeypatch.setenv("OPENMONTAGE_DIR", str(d))
    monkeypatch.setenv("OPENMONTAGE_DATA_DIR", str(tmp_path / "omdata"))
    py = montage.venv_python()  # upstream commands run in the OpenMontage venv; a stand-in file is enough here
    py.parent.mkdir(parents=True)
    py.write_text("", encoding="utf8")
    return d


def test_montage_run_demo_list(monkeypatch, fake_checkout):
    recorded = []
    monkeypatch.setattr("subprocess.call", lambda cmd, cwd=None, env=None: recorded.append((cmd, cwd)) or 0)
    ret = montage.run_montage(["demo", "--list"])
    assert ret == 0
    assert len(recorded) == 1
    cmd, cwd = recorded[0]
    assert cmd[1] == "render_demo.py"
    assert cmd[2] == "--list"
    assert cwd == fake_checkout.resolve()


def test_montage_run_open_subcommand(monkeypatch, fake_checkout):
    recorded = []
    monkeypatch.setattr(montage, "_run_open", lambda cmd, cwd=None, env=None: recorded.append((cmd, cwd)) or 0)  # open streams its output
    ret = montage.run_montage(["open", "proj-123"])
    assert ret == 0
    assert len(recorded) == 1
    cmd, cwd = recorded[0]
    assert cmd[1:4] == ["-m", "backlot", "open"]
    assert cmd[4] == "proj-123"
    assert cwd == fake_checkout.resolve()


def test_cli_dispatch_clone(monkeypatch):
    recorded = []
    monkeypatch.setattr(clone, "run_hypit", lambda args: recorded.append(args) or 0)
    ret = cli.main(["clone", "--test", "arg"])
    assert ret == 0
    assert recorded == [["--test", "arg"]]


def test_cli_dispatch_montage(monkeypatch):
    recorded = []
    monkeypatch.setattr(montage, "run_montage", lambda args: recorded.append(args) or 0)
    ret = cli.main(["montage", "demo", "--list"])
    assert ret == 0
    assert recorded == [["demo", "--list"]]


def test_mcp_tools_include_clone_and_montage():
    tool_names = [name for name, fn, desc in mcp_server.TOOLS]
    assert "video.clone" in tool_names
    assert "video.montage" in tool_names


def test_realoficial_config_is_mcp_remote(capsys):
    from simplicio_video import realoficial
    assert realoficial.run_realoficial(["config"]) == 0
    cfg = __import__("json").loads(capsys.readouterr().out)
    assert cfg["mcpServers"]["realoficial"]["args"] == ["-y", "mcp-remote", "https://api.realoficial.com.br/mcp"]


def test_opencut_dispatch_and_missing(monkeypatch):
    from simplicio_video import opencut
    monkeypatch.setattr(opencut, "find_opencut_dir", lambda: None)
    assert cli.main(["opencut", "dev"]) == 1


# ------------------------------------------------------------------ default checkout dir ($SIMPLICIO_VIDEO_DATA/tools/openmontage)

def _no_overrides(monkeypatch):
    for var in ("OPENMONTAGE_DIR", "SIMPLICIO_OPENMONTAGE_DIR", "SIMPLICIO_TOOLS_DIR", "SIMPLICIO_VIDEO_DATA", "SIMPLICIO_OFFLINE"):
        monkeypatch.delenv(var, raising=False)


def test_montage_default_dir_lives_under_simplicio_video_data(monkeypatch, tmp_path):
    _no_overrides(monkeypatch)
    monkeypatch.setenv("SIMPLICIO_VIDEO_DATA", str(tmp_path))
    assert montage.default_openmontage_dir() == tmp_path / "tools" / "openmontage"
    assert montage.find_openmontage_dir() is None  # nothing installed yet, and no machine-specific fallback
    (tmp_path / "tools" / "openmontage" / "backlot").mkdir(parents=True)
    assert montage.find_openmontage_dir() == (tmp_path / "tools" / "openmontage").resolve()


def test_montage_default_dir_falls_back_to_the_home_data_dir(monkeypatch, tmp_path):
    _no_overrides(monkeypatch)
    monkeypatch.setenv("HOME", str(tmp_path))
    assert montage.default_openmontage_dir() == tmp_path / ".simplicio-video" / "tools" / "openmontage"


def test_montage_explicit_dirs_win_over_the_data_dir(monkeypatch, tmp_path):
    _no_overrides(monkeypatch)
    monkeypatch.setenv("SIMPLICIO_VIDEO_DATA", str(tmp_path / "data"))
    monkeypatch.setenv("SIMPLICIO_TOOLS_DIR", str(tmp_path / "tools"))
    assert montage.default_openmontage_dir() == tmp_path / "tools" / "openmontage"
    monkeypatch.setenv("OPENMONTAGE_DIR", str(tmp_path / "mine"))
    assert montage.default_openmontage_dir() == tmp_path / "mine"


def test_montage_install_goes_to_the_data_dir_and_leaves_the_environment_alone(monkeypatch, tmp_path):
    from simplicio_video import tools
    _no_overrides(monkeypatch)
    monkeypatch.setenv("SIMPLICIO_VIDEO_DATA", str(tmp_path))
    calls = []
    monkeypatch.setattr(tools, "_git", lambda *a, cwd=None: calls.append(a) or "")
    assert montage.clone_openmontage() == tmp_path / "tools" / "openmontage"
    assert calls[0][0] == "clone" and calls[0][-1] == str(tmp_path / "tools" / "openmontage")
    other = tmp_path / "custom"
    assert montage.clone_openmontage(other) == other
    assert calls[-3][-1] == str(other)
    assert "OPENMONTAGE_DIR" not in os.environ  # an explicit target must not leak into later calls


def test_montage_never_clones_when_offline(monkeypatch, tmp_path):
    from simplicio_video import tools
    _no_overrides(monkeypatch)
    monkeypatch.setenv("SIMPLICIO_VIDEO_DATA", str(tmp_path))
    monkeypatch.setenv("SIMPLICIO_OFFLINE", "1")
    calls = []
    monkeypatch.setattr(tools, "_git", lambda *a, cwd=None: calls.append(a) or "")
    with pytest.raises(montage.MontageError, match="offline"):
        montage.clone_openmontage()
    assert calls == []
    assert montage.main(["demo", "--list"]) == 1  # no checkout + offline = a clear error, not a clone


def test_montage_source_has_no_machine_specific_path():
    src = Path(montage.__file__).read_text()
    assert not re.search(r"""["'](/projetos|/home/|/Users/|[A-Za-z]:\\)""", src)


# ---- a stop signal must not orphan the child (SIGTERM/SIGHUP/Ctrl+C, in the gap of Popen or while waiting) ----

_PARADA = pytest.mark.skipif(os.name != "posix", reason="POSIX signals")


def _afirma_sem_orfao(res, pidfile, nome):
    from _orfao import espera, espera_pid, vivo

    assert espera(lambda: not vivo(espera_pid(pidfile)), 8), f"the child outlived the engine (rc {res.returncode})\n{res.stderr[-400:]}"
    assert res.returncode in (128 + getattr(signal, nome), -getattr(signal, nome), 1), res.returncode


@_PARADA
@pytest.mark.parametrize("quando", ["popen", "espera"])
@pytest.mark.parametrize("nome", ["SIGTERM", "SIGHUP", "SIGINT"])
def test_run_tool_execute_stop_signal_kills_the_upstream(tmp_path, nome, quando):
    """run-tool: the upstream (own session) was armed for the kill only after Popen returned and SIGTERM/SIGHUP had no handler at
    all (the default action ended the engine and left the tool running, possibly spending money)."""
    from _orfao import mata_o_que_sobrou, roda_motor

    pidfile = tmp_path / "pid"
    corpo = ("import os, sys\nfrom pathlib import Path\nfrom simplicio_video import montage\n"
             f"montage._RUN_CHILD = \"import os, time; open({str(pidfile)!r}, 'w').write(str(os.getpid())); time.sleep(120)\"\n"
             "montage._require_checkout = lambda: Path('.').resolve()\nmontage.upstream_python = lambda: sys.executable\n"
             "montage._child_env = lambda *a, **k: dict(os.environ)\n"
             "plan = {'tool': 'x', 'strict': False, 'env_keys': [], 'estimate': {}}\n"
             "montage.run_tool_execute(plan, {}, Path('.').resolve())\n")
    try:
        _afirma_sem_orfao(roda_motor(tmp_path, corpo, pidfile, nome, quando), pidfile, nome)
    finally:
        mata_o_que_sobrou(pidfile)


@_PARADA
@pytest.mark.parametrize("quando", ["popen", "espera"])
@pytest.mark.parametrize("nome", ["SIGTERM", "SIGHUP", "SIGINT"])
def test_run_open_stop_signal_kills_the_backlot_open_child(tmp_path, nome, quando):
    """`montage open` ran the upstream with no kill at all: any stop left `backlot open` (and the server it starts) running."""
    from _orfao import mata_o_que_sobrou, roda_motor

    pidfile = tmp_path / "pid"
    code = f"import os, time; open({str(pidfile)!r}, 'w').write(str(os.getpid())); time.sleep(120)"
    corpo = ("import os, sys\nfrom pathlib import Path\nfrom simplicio_video import montage\n"
             f"montage._run_open([sys.executable, '-c', {code!r}], Path('.').resolve(), dict(os.environ))\n")
    try:
        _afirma_sem_orfao(roda_motor(tmp_path, corpo, pidfile, nome, quando), pidfile, nome)
    finally:
        mata_o_que_sobrou(pidfile)


@_PARADA
@pytest.mark.parametrize("quando", ["popen", "espera"])
@pytest.mark.parametrize("nome", ["SIGTERM", "SIGHUP", "SIGINT"])
def test_run_open_stop_signal_kills_the_diagnostic_server_too(tmp_path, nome, quando):
    """When `open` says it did not come up, the engine runs `backlot serve` for a few seconds to show why: that child too."""
    from _orfao import mata_o_que_sobrou, roda_motor

    pidfile = tmp_path / "pid"
    (tmp_path / "backlot.py").write_text(f"import os, time\nopen({str(pidfile)!r}, 'w').write(str(os.getpid()))\ntime.sleep(120)\n")
    corpo = ("import os, sys\nfrom pathlib import Path\nfrom simplicio_video import montage\n"
             "montage._run_open([sys.executable, '-c', 'print(\"did not come up\")'], Path('.').resolve(), dict(os.environ))\n")
    try:
        _afirma_sem_orfao(roda_motor(tmp_path, corpo, pidfile, nome, quando, so_se="backlot"), pidfile, nome)
    finally:
        mata_o_que_sobrou(pidfile)
