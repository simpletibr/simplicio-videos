"""scripts/bench_concurrency.py: benchmark com latência SIMULADA (adaptador fake e Gemini de voz trocado), sem rede."""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "bench_concurrency.py"
needs_ffmpeg = pytest.mark.skipif(not (shutil.which("ffmpeg") and shutil.which("ffprobe")), reason="ffmpeg ausente")


def load():
    spec = importlib.util.spec_from_file_location("bench_concurrency", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["bench_concurrency"] = mod
    spec.loader.exec_module(mod)
    return mod


@needs_ffmpeg
def test_bench_mede_serial_contra_paralelo_com_saida_identica():
    bench = load()
    rep = bench.run(chunks=3, voice_lines=4, latency=0.15, repeat=1)
    assert rep["schema"] == "simplicio.bench-concurrency/v1" and rep["simulated"] is True
    s, v = rep["swap"], rep["voice"]
    assert s["chunks"] == 3 and s["concurrency"] == 3 and v["lines"] == 4 and v["concurrency"] == 4
    assert s["identical_output"] is True and v["identical_lock"] is True
    for r in (s, v):
        # the time gain is only a number the script reports: a clock assertion is flaky under CPU load (it failed 4 of 5 runs
        # with 8 busy loops on 4 cores). The proof of parallelism is deterministic: the most calls in flight at once.
        assert set(r) >= {"serial_s", "parallel_s", "speedup"} and r["serial_s"] > 0 and r["parallel_s"] > 0
    assert s["max_in_flight"] == {"serial": 1, "parallel": 3}
    assert v["max_in_flight"] == {"serial": 1, "parallel": 4}
    assert any("render" in n and "serial" in n for n in rep["notes"])


def test_bench_nao_toca_a_rede():
    src = SCRIPT.read_text()
    for termo in ("urlopen", "requests", "socket", "http.client"):
        assert termo not in src, termo


@needs_ffmpeg
def test_bench_cli_json():
    r = subprocess.run([sys.executable, str(SCRIPT), "--chunks", "3", "--voice-lines", "3", "--latency", "0.1", "--repeat", "1",
                        "--json"], capture_output=True, text=True, cwd=ROOT, env={**os.environ, "SIMPLICIO_OFFLINE": "1"})
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout)["simulated"] is True
