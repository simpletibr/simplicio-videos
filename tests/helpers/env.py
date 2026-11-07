"""The environment a test (or the child process it starts) runs in."""

import atexit
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

_OFFLINE_DIR: list[str] = []

_SITECUSTOMIZE = """\
# written by tests/helpers/env.py: subprocess tests are offline too (same guard as the in-process one)
from pytest_socket import disable_socket

disable_socket(allow_unix_socket=True)
"""


def have_render_tools() -> bool:
    from simplicio_video import paths
    env = paths.node_env()
    return all(shutil.which(t, path=env["PATH"]) for t in ("node", "npx", "ffmpeg"))


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


def isolate_tools(monkeypatch, tmp_path, *, home: bool = True, data: str | None = None, drop=()):
    """What every track's `_isolated` fixture does first: a real checkout under ~/.simplicio-video (or a tool on the developer's
    machine) must never be found by a test. HOME and the tools dir point into `tmp_path` (not created), `data` names the
    SIMPLICIO_VIDEO_DATA folder under it, and `drop` lists the variables of that track to remove. What a track needs beyond
    this (a chdir, a patched platform, PATH) stays in its own fixture. Returns `tmp_path`."""
    for var in drop:
        monkeypatch.delenv(var, raising=False)
    if home:
        monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("SIMPLICIO_TOOLS_DIR", str(tmp_path / "tools"))
    if data is not None:
        monkeypatch.setenv("SIMPLICIO_VIDEO_DATA", str(tmp_path / data))
    return tmp_path
