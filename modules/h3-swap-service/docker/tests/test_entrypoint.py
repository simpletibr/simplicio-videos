"""Tests for the guard functions in docker/entrypoint.sh.

The script starts services only when executed directly, so these tests source it
and call one function at a time under bash. No ComfyUI, no R2, no GPU.
Run from the repo root:  python -m pytest docker/tests -q
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

DOCKER_DIR = Path(__file__).resolve().parents[1]
ENTRYPOINT = DOCKER_DIR / "entrypoint.sh"


def run_bash(snippet: str, tmp_path: Path, **env: str) -> subprocess.CompletedProcess[str]:
    base_env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(tmp_path)}
    base_env.update(env)
    script = f'source "{ENTRYPOINT}"\n{snippet}\n'
    return subprocess.run(
        ["bash", "-c", script],
        env=base_env,
        capture_output=True,
        text=True,
        timeout=30,
    )


def combined(result: subprocess.CompletedProcess[str]) -> str:
    return result.stdout + result.stderr


def test_sourcing_does_not_start_services(tmp_path: Path) -> None:
    result = run_bash("echo sourced", tmp_path, MODELS_MODE="baked")
    assert result.returncode == 0
    assert "sourced" in result.stdout
    assert "[entrypoint]" not in combined(result)


def test_worker_is_started_as_python_m_worker() -> None:
    text = ENTRYPOINT.read_text(encoding="utf-8")
    assert "python -m worker" in text
    assert "worker.runner" not in text


def test_salad_with_baked_warns_without_failing(tmp_path: Path) -> None:
    result = run_bash("check_provider_mode", tmp_path, PROVIDER="salad", MODELS_MODE="baked")
    assert result.returncode == 0
    assert "WARNING" in combined(result)
    assert "salad" in combined(result).lower()


@pytest.mark.parametrize(
    "env",
    [
        {"PROVIDER": "vast", "MODELS_MODE": "baked"},
        {"PROVIDER": "salad", "MODELS_MODE": "runtime"},
        {"MODELS_MODE": "baked"},  # PROVIDER unset means vast
        {"PROVIDER": "salad"},  # MODELS_MODE unset means runtime
    ],
)
def test_no_provider_warning_outside_salad_baked(tmp_path: Path, env: dict[str, str]) -> None:
    result = run_bash("check_provider_mode", tmp_path, **env)
    assert result.returncode == 0
    assert "WARNING" not in combined(result)


def workflow_env(tmp_path: Path, present: bool) -> dict[str, str]:
    api = tmp_path / "workflow_api.json"
    mapping = tmp_path / "workflow_map.json"
    if present:
        api.write_text("{}", encoding="utf-8")
        mapping.write_text("{}", encoding="utf-8")
    return {"WORKFLOW_TEMPLATE": str(api), "WORKFLOW_MAP": str(mapping)}


def test_workflow_files_present_is_quiet(tmp_path: Path) -> None:
    result = run_bash("check_workflow_files", tmp_path, **workflow_env(tmp_path, present=True))
    assert result.returncode == 0
    assert "WARNING" not in combined(result)


def test_missing_workflow_with_optional_warns_loudly_and_continues(tmp_path: Path) -> None:
    result = run_bash(
        "check_workflow_files",
        tmp_path,
        WORKFLOW_OPTIONAL="1",
        **workflow_env(tmp_path, present=False),
    )
    assert result.returncode == 0
    assert "WARNING" in combined(result)
    assert "will fail every job" in combined(result).lower()


def test_missing_workflow_without_optional_fails(tmp_path: Path) -> None:
    result = run_bash("check_workflow_files", tmp_path, **workflow_env(tmp_path, present=False))
    assert result.returncode != 0
