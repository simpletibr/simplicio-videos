"""Tests for the functions in docker/entrypoint.sh.

The script starts services only when executed directly, so these tests source it
and call one function at a time under bash. No ComfyUI, no R2, no GPU.
Run from the repo root:  python -m pytest docker/tests -q
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

DOCKER_DIR = Path(__file__).resolve().parents[1]
ENTRYPOINT = DOCKER_DIR / "entrypoint.sh"


def run_bash(snippet: str, tmp_path: Path, **env: str) -> subprocess.CompletedProcess[str]:
    """Source entrypoint.sh and run snippet. A `python` symlink to this interpreter is first on PATH."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    python_link = bin_dir / "python"
    if not python_link.exists():
        python_link.symlink_to(sys.executable)
    base_env = {
        "PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '/usr/bin:/bin')}",
        "HOME": str(tmp_path),
        "NVIDIA_SMI": str(tmp_path / "no-such-nvidia-smi"),
        "MEMINFO_PATH": str(tmp_path / "meminfo"),
    }
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


def write_meminfo(tmp_path: Path, ram_kb: int) -> str:
    path = tmp_path / "meminfo"
    path.write_text(f"MemTotal:       {ram_kb} kB\nMemFree:        1000 kB\n", encoding="utf-8")
    return str(path)


def write_nvidia_smi(tmp_path: Path, lines: str | None) -> str:
    """Stub nvidia-smi: prints `lines` for --query-gpu=name,memory.total, or fails when lines is None."""
    path = tmp_path / "nvidia-smi-stub"
    if lines is None:
        body = "exit 1\n"
    else:
        body = f"cat <<'EOF'\n{lines}EOF\n"
    path.write_text("#!/bin/sh\n" + body, encoding="utf-8")
    path.chmod(0o755)
    return str(path)


# --------------------------------------------------------------------------
# sourcing and the worker command
# --------------------------------------------------------------------------


def test_sourcing_does_not_start_services(tmp_path: Path) -> None:
    result = run_bash("echo sourced", tmp_path, MODELS_MODE="baked")
    assert result.returncode == 0
    assert "sourced" in result.stdout
    assert "[entrypoint]" not in combined(result)


def test_worker_is_started_as_python_m_worker() -> None:
    text = ENTRYPOINT.read_text(encoding="utf-8")
    assert "python -m worker" in text
    assert "worker.runner" not in text


# --------------------------------------------------------------------------
# GPU check: informational, never fails the boot
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("lines", "ram_kb", "expect_warning"),
    [
        # 16 GB card reports ~16311 MiB; 64 GB machine. Nominal 16 GB must not warn.
        ("NVIDIA GeForce RTX 5060 Ti, 16311\n", 67108864, False),
        ("NVIDIA GeForce RTX 5090, 32607\n", 134217728, False),
        ("NVIDIA GeForce RTX 3060, 8192\n", 67108864, True),  # VRAM below 16 GB
        ("NVIDIA GeForce RTX 4090, 24564\n", 33554432, True),  # system RAM 32 GB
    ],
)
def test_gpu_check_prints_info_and_warns_only_below_guide(
    tmp_path: Path, lines: str, ram_kb: int, expect_warning: bool
) -> None:
    result = run_bash(
        "check_gpu",
        tmp_path,
        NVIDIA_SMI=write_nvidia_smi(tmp_path, lines),
        MEMINFO_PATH=write_meminfo(tmp_path, ram_kb),
    )
    output = combined(result)
    assert result.returncode == 0
    assert "GPU: " in output
    assert "VRAM" in output and "system RAM" in output
    assert ("WARNING" in output) is expect_warning
    if expect_warning:
        assert "Offload needs system RAM; speed and VRAM at 768p are unmeasured." in output


def test_gpu_check_with_no_nvidia_smi_is_informational(tmp_path: Path) -> None:
    result = run_bash("check_gpu", tmp_path, MEMINFO_PATH=write_meminfo(tmp_path, 67108864))
    assert result.returncode == 0
    assert "nvidia-smi not found" in combined(result)
    assert "WARNING" not in combined(result)


def test_gpu_check_survives_a_failing_nvidia_smi(tmp_path: Path) -> None:
    result = run_bash(
        "check_gpu",
        tmp_path,
        NVIDIA_SMI=write_nvidia_smi(tmp_path, None),
        MEMINFO_PATH=write_meminfo(tmp_path, 67108864),
    )
    assert result.returncode == 0


def test_gpu_check_never_reports_compute_capability(tmp_path: Path) -> None:
    result = run_bash(
        "check_gpu",
        tmp_path,
        NVIDIA_SMI=write_nvidia_smi(tmp_path, "NVIDIA GeForce RTX 3060, 8192\n"),
        MEMINFO_PATH=write_meminfo(tmp_path, 67108864),
    )
    assert "compute" not in combined(result).lower()


# --------------------------------------------------------------------------
# documentation guard: no remaining claim that the NVFP4 encoder or worker needs Blackwell
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "relative",
    [
        "Dockerfile",
        "entrypoint.sh",
        "build.sh",
        "fetch_models.py",
        "models.manifest.json",
        "README_docker.md",
    ],
)
def test_no_blackwell_requirement_claim_remains(relative: str) -> None:
    text = (DOCKER_DIR / relative).read_text(encoding="utf-8")
    for line in text.splitlines():
        if "Blackwell" in line:
            assert "not require" in line, f"Blackwell requirement claim left in {relative}: {line!r}"
        assert "compute_cap" not in line, f"compute capability check left in {relative}: {line!r}"


# --------------------------------------------------------------------------
# provider and workflow guards
# --------------------------------------------------------------------------


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


# --------------------------------------------------------------------------
# fetch wiring: scope per mode, optional selection passed through
# --------------------------------------------------------------------------


def fetch_stub(tmp_path: Path) -> Path:
    stub = tmp_path / "fetch_stub.py"
    stub.write_text(
        "import os, sys\n"
        "from pathlib import Path\n"
        "Path(os.environ['STUB_OUT']).write_text(' '.join(sys.argv[1:]), encoding='utf-8')\n",
        encoding="utf-8",
    )
    return stub


def run_fetch(tmp_path: Path, **env: str) -> str:
    out = tmp_path / "fetch_args.txt"
    result = run_bash(
        "fetch_models",
        tmp_path,
        FETCH_MODELS_PY=str(fetch_stub(tmp_path)),
        STUB_OUT=str(out),
        **env,
    )
    assert result.returncode == 0, combined(result)
    return out.read_text(encoding="utf-8")


def test_runtime_fetch_uses_scope_all(tmp_path: Path) -> None:
    args = run_fetch(tmp_path, MODELS_MODE="runtime")
    assert "--scope all" in args
    assert "--include-optional" not in args


def test_baked_fetch_uses_scope_config(tmp_path: Path) -> None:
    args = run_fetch(tmp_path, MODELS_MODE="baked")
    assert "--scope config" in args


def test_fetch_passes_optional_selection_through(tmp_path: Path) -> None:
    args = run_fetch(
        tmp_path,
        MODELS_MODE="runtime",
        FETCH_OPTIONAL="loras/minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors",
    )
    assert "--include-optional loras/minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors" in args
