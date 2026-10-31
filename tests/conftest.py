import atexit
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "mini"
WJR = ROOT / "clients" / "wjr-informatica-games" / "video-01" / "contract.yaml"
LOTHUS = ROOT / "clients" / "lothus-odontologia" / "video-01-dia-das-criancas" / "contract.yaml"
CLIENT_DATA_REASON = "contrato real de cliente fora do git (clients/ não é rastreado)"


def needs_client(*paths: Path):
    """skipif marker for a test that only makes sense with the real client contract(s): clients/ is not tracked by git."""
    return pytest.mark.skipif(not all(p.exists() for p in paths), reason=CLIENT_DATA_REASON)


def contract_with_coleta_placeholders(contract: Path, dest: Path) -> Path:
    """A copy of a client contract in `dest` whose assets under `coleta/` exist as placeholders.

    `clients/*/coleta/` is gitignored (client data never goes to git), so a clean checkout has none of those files."""
    copia = dest / "a" / "video"
    shutil.copytree(contract.parent, copia, ignore=shutil.ignore_patterns("preview", "node_modules"))
    d = yaml.safe_load(contract.read_text(encoding="utf8"))
    refs = [a["arquivo"] for a in d.get("assets") or []] + [s["file"] for s in d.get("placas_video") or []]
    if (d.get("marca") or {}).get("logo"):
        refs.append(d["marca"]["logo"]["arquivo"])
    for ref in refs:
        alvo = (copia / ref).resolve()
        assert (dest / "a") in alvo.parents, ref  # the copy never writes outside the temporary folder
        if not alvo.exists():
            alvo.parent.mkdir(parents=True, exist_ok=True)
            alvo.write_bytes(b"\x89PNG\r\n\x1a\n" + ref.encode())
    return copia / contract.name


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
