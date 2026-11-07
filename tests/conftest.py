import os
import shutil

import pytest

# The helpers live in tests/helpers; the names that used to be defined here stay importable from `conftest`
# (tests/test_scripts/test_socket_guard.py and the imports inside test bodies still read them from this module).
pytest.register_assert_rewrite("helpers")  # before the first import of the package, so the asserts inside helpers keep pytest's detail
from helpers import (  # noqa: E402,F401
    CLIENT_DATA_REASON,
    FIXTURE,
    LOTHUS,
    ROOT,
    WJR,
    contract_with_coleta_placeholders,
    have_render_tools,
    needs_client,
    offline_env,
    run_cli,
)


# Marker taxonomy (registered in pyproject.toml). `slow` is orthogonal to the kind markers.
KIND_MARKERS = {"unit", "contract", "e2e", "integration", "render", "ui"}
NETWORK_MARKERS = {"render", "integration", "ui"}  # these may use the network; every other test runs with sockets blocked

# Unit tests that start a throwaway server on 127.0.0.1 (tests we do not own): loopback only, never the network.
LOOPBACK_TESTS = (
    "test_voice_clone.py::test_voicestudio_http",
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
    monkeypatch.setenv("VIDEO_USE_DIR", str(tmp_path_factory.mktemp("video-use-cache") / "video-use"))  # not the real ~/.cache checkout
    for var in ("OPENMONTAGE_DIR", "SIMPLICIO_OPENMONTAGE_DIR", "SIMPLICIO_TOOLS_DIR", "TINYFISH_API_KEY", "SIMPLICIO_BUSCA_MAX_DIA"):
        monkeypatch.delenv(var, raising=False)  # a real TinyFish key or cap in the developer's shell never reaches a test
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
