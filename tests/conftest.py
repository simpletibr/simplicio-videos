import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "mini"
WJR = ROOT / "clients" / "wjr-informatica-games" / "video-01" / "contract.yaml"
LOTHUS = ROOT / "clients" / "lothus-odontologia" / "video-01-dia-das-criancas" / "contract.yaml"


@pytest.fixture(autouse=True)
def _home(monkeypatch):
    monkeypatch.setenv("SIMPLICIO_VIDEO_HOME", str(ROOT))


@pytest.fixture
def mini(tmp_path):
    """Fresh copy of the 1 s fixture project (contract + template + synthetic VO take)."""
    dst = tmp_path / "mini"
    shutil.copytree(FIXTURE, dst, ignore=shutil.ignore_patterns("out", "build", "timing.lock.json", "render.manifest.json", "voz"))
    return dst / "contract.yaml"


def have_render_tools() -> bool:
    from simplicio_video import paths
    env = paths.node_env()
    return all(shutil.which(t, path=env["PATH"]) for t in ("node", "npx", "ffmpeg"))


def run_cli(*args, cwd=None):
    import sys
    return subprocess.run([sys.executable, "-m", "simplicio_video", *map(str, args)], capture_output=True, text=True, cwd=cwd)
