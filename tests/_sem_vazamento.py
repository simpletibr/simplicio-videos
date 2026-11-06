"""Guard for the video-to-skill test files: no test may leave a private job folder (`video-to-skill-job-*`) in the real temp folder.

Autouse: import `sem_vazamento_de_pastas` in a test module and every test of it is checked. A test that makes a job folder
(`video_to_skill.make_job_cwd`, or a job submit) redirects `tempfile.tempdir` to its own `tmp_path` (the `env` fixture does)."""
from __future__ import annotations

import glob
import os
import tempfile

import pytest

PADRAO = "video-to-skill-job-*"
TMP_REAL = tempfile.gettempdir()  # taken at import, before any test redirects tempfile.tempdir to its own folder


def _pastas() -> set:
    return set(glob.glob(os.path.join(TMP_REAL, PADRAO)))


@pytest.fixture(autouse=True)
def sem_vazamento_de_pastas():
    antes = _pastas()
    yield
    novas = _pastas() - antes
    assert not novas, f"o teste deixou pasta(s) privada(s) de tarefa no tmp real: {sorted(novas)}"
