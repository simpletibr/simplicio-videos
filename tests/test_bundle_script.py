"""render_bundle.sh (Kaggle / Colab CLI / Colab notebook): NVENC detection, deterministic browser flags, env record.

Runs the real script with fake npx/ffmpeg/nvidia-smi on PATH (no GPU, no network)."""
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from simplicio_video import render

pytestmark = pytest.mark.skipif(not shutil.which("bash") or not shutil.which("python3"), reason="needs bash + python3")

FAKE_FFMPEG = r"""#!/usr/bin/env bash
if [[ " $* " == *" -encoders "* ]]; then
  echo " V....D h264_nvenc           NVIDIA NVENC H.264 encoder (codec h264)"
  for i in $(seq 1 3000); do echo " V....D fake_encoder_$i"; done   # match early + long tail: a grep -q pipe gets SIGPIPE
  exit 0
fi
if [[ " $* " == *" h264_nvenc "* ]]; then exit "${FAKE_NVENC_RC:-0}"; fi
echo "ffmpeg version 9.9-fake"
"""


def _setup(tmp_path: Path, gpu_encode="auto", nvidia=True):
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    (bin_ / "ffmpeg").write_text(FAKE_FFMPEG)
    (bin_ / "npx").write_text('#!/usr/bin/env bash\necho "$@" > out/npx_args\ntouch out/raw.mp4\n'
                              'echo "  capture 12.5s · encode (during capture) 12.5s"\n')
    if nvidia:
        (bin_ / "nvidia-smi").write_text('#!/usr/bin/env bash\necho "Tesla T4, 550.54"\n')
    for f in bin_.iterdir():
        f.chmod(0o755)
    b = tmp_path / "bundle"
    (b / "scripts").mkdir(parents=True)
    (b / "scripts" / "master.sh").write_text('cp "$1" "$2"\n')
    (b / "render_bundle.sh").write_text(render.bundle_script("draft", gpu_encode))
    return bin_, b


def _run(tmp_path, bin_, b, **env):
    e = {**os.environ, "PATH": f"{bin_}{os.pathsep}{os.environ['PATH']}", **env}
    p = subprocess.run(["bash", "render_bundle.sh"], cwd=b, env=e, capture_output=True, text=True)
    assert p.returncode == 0, p.stdout + p.stderr
    t = json.loads(re.search(r"TIMINGS (\{.*\})", p.stdout).group(1))
    return t, (b / "out" / "npx_args").read_text().split()


def test_script_has_no_sigpipe_grep_and_is_deterministic_by_default():
    s = render.bundle_script("delivery")
    assert "| grep -q" not in s                       # the pipefail+SIGPIPE bug that kept gpu_encode=false on Colab
    assert "h264_nvenc -f null" in s                  # real test encode, not just the encoder list
    assert "--no-browser-gpu" in s and "PRODUCER_FORCE_SCREENSHOT" in s
    assert "__" not in s.replace("__file__", "")      # all placeholders filled
    with pytest.raises(ValueError):
        render.bundle_script("draft", "yes")


def test_nvenc_is_used_when_it_really_works(tmp_path):
    bin_, b = _setup(tmp_path)
    t, args = _run(tmp_path, bin_, b)
    assert t["gpu_encode"] is True and t["gpu_encode_reason"] == "nvenc ok"
    assert "--gpu" in args and "--no-browser-gpu" in args and "--workers" not in args
    assert t["capture_s"] == 12.5 and t["env"]["nproc"] >= 1 and t["env"]["gpu"] == "Tesla T4, 550.54"


def test_nvenc_opt_out_and_failed_probe(tmp_path):
    bin_, b = _setup(tmp_path, gpu_encode="0")
    t, args = _run(tmp_path, bin_, b)
    assert t["gpu_encode"] is False and "--gpu" not in args
    t, args = _run(tmp_path, bin_, b, SV_GPU_ENCODE="1", FAKE_NVENC_RC="1", SV_WORKERS="2", SV_BROWSER_GPU="1")
    assert t["gpu_encode"] is False and "test encode failed" in t["gpu_encode_reason"]
    assert args[args.index("--workers") + 1] == "2" and "--browser-gpu" in args


def test_no_driver_means_cpu(tmp_path):
    bin_, b = _setup(tmp_path, nvidia=False)
    if shutil.which("nvidia-smi"):
        pytest.skip("host has a real nvidia-smi")
    t, args = _run(tmp_path, bin_, b)
    assert t["gpu_encode"] is False and t["gpu_encode_reason"] == "no nvidia-smi/driver" and "--gpu" not in args
