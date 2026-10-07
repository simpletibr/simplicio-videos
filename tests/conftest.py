import atexit
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "mini"
WJR = ROOT / "clients" / "wjr-informatica-games" / "video-01" / "contract.yaml"
LOTHUS = ROOT / "clients" / "lothus-odontologia" / "video-01-dia-das-criancas" / "contract.yaml"


# Marker taxonomy (registered in pyproject.toml). `slow` is orthogonal to the kind markers.
KIND_MARKERS = {"unit", "contract", "e2e", "integration", "render", "ui"}
NETWORK_MARKERS = {"render", "integration", "ui"}  # these may use the network; every other test runs with sockets blocked

# Unit tests that start a throwaway server on 127.0.0.1 (tests we do not own): loopback only, never the network.
LOOPBACK_TESTS = (
    "test_venda.py::test_servidor_http_ponta_a_ponta",
    "test_voice_clone.py::test_voicestudio_http",
    "test_prospect_institucional.py::test_gemini_overlong_take_is_regenerated_not_sped_up",
)


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(items):
    """Untagged tests are unit tests; render/integration/ui tests may open sockets, the rest may not."""
    for item in items:
        names = {m.name for m in item.iter_markers()}
        if not names & KIND_MARKERS:
            item.add_marker(pytest.mark.unit)
        if names & NETWORK_MARKERS:
            item.add_marker(pytest.mark.enable_socket)
        elif item.nodeid.endswith(LOOPBACK_TESTS):
            item.add_marker(pytest.mark.allow_hosts(["127.0.0.1", "::1", "localhost"]))


@pytest.fixture(autouse=True)
def _home(monkeypatch):
    monkeypatch.setenv("SIMPLICIO_VIDEO_HOME", str(ROOT))


def _no_git(*args, **kwargs):
    raise AssertionError(f"hermetic: unit tests must not run git ({' '.join(map(str, args[:2]))}); patch tools._git in the test")


@pytest.fixture(autouse=True)
def _hermetic(request, monkeypatch, tmp_path_factory):
    """No test touches the real home, a real tool checkout or the network by accident."""
    monkeypatch.setenv("SIMPLICIO_VIDEO_DATA", str(tmp_path_factory.mktemp("simplicio-data")))
    for var in ("OPENMONTAGE_DIR", "SIMPLICIO_OPENMONTAGE_DIR", "SIMPLICIO_TOOLS_DIR"):
        monkeypatch.delenv(var, raising=False)
    if request.node.get_closest_marker("render") or request.node.get_closest_marker("integration") or request.node.get_closest_marker("ui"):
        monkeypatch.delenv("SIMPLICIO_OFFLINE", raising=False)
    else:
        monkeypatch.setenv("SIMPLICIO_OFFLINE", "1")
    from simplicio_video import tools
    monkeypatch.setattr(tools, "_git", _no_git)


@pytest.fixture
def mini(tmp_path):
    """Fresh copy of the 1 s fixture project (contract + template + synthetic VO take)."""
    dst = tmp_path / "mini"
    shutil.copytree(FIXTURE, dst, ignore=shutil.ignore_patterns("out", "build", "timing.lock.json", "render.manifest.json", "voz"))
    return dst / "contract.yaml"


# hermetic tests: no speech-to-text subprocess (word timings fall back to proportional)
os.environ.setdefault("SIMPLICIO_STT_PY", "/nonexistent/stt-python")


def have_render_tools() -> bool:
    from simplicio_video import paths
    env = paths.node_env()
    return all(shutil.which(t, path=env["PATH"]) for t in ("node", "npx", "ffmpeg"))


_OFFLINE_DIR: list[str] = []

_SITECUSTOMIZE = """\
# written by tests/conftest.py: subprocess tests are offline too (same guard as the in-process one)
from pytest_socket import disable_socket

disable_socket(allow_unix_socket=True)
"""


def offline_env(**extra: str) -> dict[str, str]:
    """Environment for subprocess tests: SIMPLICIO_OFFLINE=1 (the engine refuses to download) plus the
    pytest-socket guard injected through sitecustomize, which the in-process guard cannot reach."""
    if not _OFFLINE_DIR:
        d = tempfile.mkdtemp(prefix="simplicio-offline-")
        (Path(d) / "sitecustomize.py").write_text(_SITECUSTOMIZE)
        atexit.register(shutil.rmtree, d, True)
        _OFFLINE_DIR.append(d)
    env = os.environ.copy()
    env["SIMPLICIO_OFFLINE"] = "1"
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [_OFFLINE_DIR[0], env.get("PYTHONPATH", "")]))
    env.update(extra)
    return env


def run_cli(*args, cwd=None):
    import sys
    return subprocess.run([sys.executable, "-m", "simplicio_video", *map(str, args)], capture_output=True, text=True, cwd=cwd,
                          env=offline_env())
