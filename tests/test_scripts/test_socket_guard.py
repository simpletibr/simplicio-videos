"""Unit tests run with sockets disabled; render tests may use the network; subprocess tests are offline too."""
from __future__ import annotations

import os
import subprocess
import sys

import pytest
from gitfixture import ROOT

import conftest

PROBE = ROOT / "tests" / "test_scripts" / "probe_socket.py"


def nested(*args):
    env = {k: v for k, v in os.environ.items() if not k.startswith(("PYTEST_", "SIMPLICIO_"))}
    return subprocess.run([sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "-rA", "--tb=line", *args, str(PROBE)],
                          cwd=ROOT, capture_output=True, text=True, env=env, timeout=120)


def test_a_unit_test_that_opens_a_socket_fails_under_the_guard():
    r = nested()
    assert "FAILED" in r.stdout and "test_unit_cannot_open_a_socket" in r.stdout.split("FAILED", 1)[1], r.stdout
    assert "SocketBlockedError" in r.stdout


def test_render_tests_are_allowed_to_open_sockets():
    out = nested().stdout
    assert "PASSED" in out and "PASSED tests/test_scripts/probe_socket.py::test_render_may_open_a_socket" in out, out


def test_unix_socketpairs_stay_available_for_asyncio():
    assert "PASSED tests/test_scripts/probe_socket.py::test_unit_may_use_a_unix_socketpair" in nested().stdout


def test_unmarked_tests_count_as_unit_tests():
    r = nested("-m", "unit")
    assert "1 deselected" in r.stdout, r.stdout
    assert "test_unit_may_use_a_unix_socketpair" in r.stdout
    assert "PASSED tests/test_scripts/probe_socket.py::test_render_may_open_a_socket" not in r.stdout


# ------------------------------------------------------------------ subprocess tests are offline too

def test_conftest_offers_an_offline_env_for_subprocesses():
    assert hasattr(conftest, "offline_env"), "conftest.offline_env() is missing"
    env = conftest.offline_env()
    assert env["SIMPLICIO_OFFLINE"] == "1"
    r = subprocess.run([sys.executable, "-c", "import socket; socket.socket(socket.AF_INET, socket.SOCK_STREAM)"],
                       env=env, capture_output=True, text=True)
    assert r.returncode != 0 and "SocketBlockedError" in r.stderr


def test_the_offline_env_still_lets_the_cli_run():
    r = subprocess.run([sys.executable, "-m", "simplicio_video", "--help"], env=conftest.offline_env(), capture_output=True, text=True)
    assert r.returncode == 0 and "simplicio-video" in r.stdout


def test_run_cli_runs_the_cli_offline(monkeypatch):
    seen = {}

    def fake_run(cmd, **kw):
        seen.update(kw)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    conftest.run_cli("--help")
    assert seen["env"]["SIMPLICIO_OFFLINE"] == "1"


# ------------------------------------------------------------------ unit tests are hermetic

def test_conftest_isolates_the_data_dir(tmp_path_factory):
    data = os.environ.get("SIMPLICIO_VIDEO_DATA")
    assert data, "conftest must point SIMPLICIO_VIDEO_DATA at a throwaway directory"
    assert os.path.realpath(data).startswith(os.path.realpath(tmp_path_factory.getbasetemp()))
    assert os.environ.get("SIMPLICIO_OFFLINE") == "1"
    for var in ("OPENMONTAGE_DIR", "SIMPLICIO_OPENMONTAGE_DIR", "SIMPLICIO_TOOLS_DIR"):
        assert var not in os.environ, var


def test_unit_tests_cannot_run_git_for_real():
    from simplicio_video import tools
    with pytest.raises(AssertionError, match="hermetic"):
        tools._git("clone", "https://example.invalid/x.git", "/nonexistent")
