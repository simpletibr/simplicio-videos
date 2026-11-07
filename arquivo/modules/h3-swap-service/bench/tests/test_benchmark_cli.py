"""Tests for bench/benchmark.py. Never imports worker/: the live loop gets a fake backend."""

from __future__ import annotations

import csv
import json
import math
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from bench import benchmark
from bench.benchmark import Backend, GpuInfo

BENCH_DIR = Path(__file__).resolve().parents[1]
EXAMPLE_MAP = BENCH_DIR / "workflow_map.example.json"
CONTRACT_MAP = {
    "inputs": {
        "source_video": {"node": "12", "field": "video"},
        "character_images": [
            {"node": "20", "field": "image"},
            {"node": "21", "field": "image"},
            {"node": "22", "field": "image"},
        ],
        "prompt": {"node": "30", "field": "text"},
        "seed": {"node": "40", "field": "seed"},
        "length_frames": {"node": "41", "field": "length"},
        "chunk_count": {"node": "42", "field": "chunks"},
    },
    "output": {"node": "90", "kind": "videos"},
}
WORKFLOW_NODES = ("12", "20", "21", "22", "30", "40", "41", "42", "90")
DESC_1 = "o homem de boné, à esquerda"
DESC_2 = "a mulher de vestido vermelho"


@pytest.fixture
def files(tmp_path: Path) -> dict[str, Path]:
    workflow = {node: {"class_type": "Stub", "inputs": {}} for node in WORKFLOW_NODES}
    paths = {
        "workflow": tmp_path / "workflow_api.json",
        "source": tmp_path / "source.mp4",
        "char1": tmp_path / "char1.png",
        "char2": tmp_path / "char2.jpg",
        "input": tmp_path / "input",
        "out": tmp_path / "out",
    }
    paths["workflow"].write_text(json.dumps(workflow), encoding="utf-8")
    paths["source"].write_bytes(b"stub source bytes")
    paths["char1"].write_bytes(b"stub png bytes")
    paths["char2"].write_bytes(b"stub jpg bytes")
    paths["input"].mkdir()
    return paths


def argv_for(files: dict[str, Path], *extra: str) -> list[str]:
    return [
        "--workflow", str(files["workflow"]),
        "--map", str(EXAMPLE_MAP),
        "--source-video", str(files["source"]),
        "--character-image", str(files["char1"]),
        "--character-image", str(files["char2"]),
        "--replace-description", DESC_1,
        "--replace-description", DESC_2,
        "--input-dir", str(files["input"]),
        "--out-dir", str(files["out"]),
        *extra,
    ]


def load(files: dict[str, Path], *extra: str) -> benchmark.BenchConfig:
    args = benchmark.build_parser().parse_args(argv_for(files, *extra))
    return benchmark.load_config(args)


# --- provider prices and rates -------------------------------------------------


def test_parse_provider_prices_default_string():
    assert benchmark.parse_provider_prices("vast=0.767,salad=0.50") == {"vast": 0.767, "salad": 0.5}


def test_parse_provider_prices_tolerates_spaces_and_case():
    assert benchmark.parse_provider_prices(" Vast = 0.767 , salad=0.5 ") == {"vast": 0.767, "salad": 0.5}


@pytest.mark.parametrize("text", ["", "vast", "vast=", "vast=abc", "vast=-1", "vast=0", "vast=nan", "vast=1,vast=2"])
def test_parse_provider_prices_rejects_bad_text(text: str):
    with pytest.raises(benchmark.ConfigError):
        benchmark.parse_provider_prices(text)


def test_failure_rate_counts_non_ok_runs():
    runs = [{"ok": True}, {"ok": False}, {"ok": True}, {"ok": False}]
    assert benchmark.failure_rate(runs) == pytest.approx(0.5)
    assert benchmark.failure_rate([]) == 0.0


# --- CLI validation (dry run) ----------------------------------------------------


def test_example_map_matches_contract_section_7():
    assert json.loads(EXAMPLE_MAP.read_text(encoding="utf-8")) == CONTRACT_MAP


def test_dry_run_prints_plan_and_writes_nothing(files: dict[str, Path], capsys: pytest.CaptureFixture[str]):
    code = benchmark.main(argv_for(files, "--dry-run"))
    out = capsys.readouterr().out
    assert code == 0
    assert "DRY RUN" in out
    assert "10s repeat 1/3" in out
    assert "30s repeat 3/3" in out
    assert "vast=0.767 USD/h" in out
    assert not files["out"].exists()
    assert list(files["input"].iterdir()) == []


def test_rejects_description_count_mismatch(files: dict[str, Path], capsys: pytest.CaptureFixture[str]):
    argv = [
        "--workflow", str(files["workflow"]),
        "--map", str(EXAMPLE_MAP),
        "--source-video", str(files["source"]),
        "--character-image", str(files["char1"]),
        "--character-image", str(files["char2"]),
        "--replace-description", DESC_1,
        "--input-dir", str(files["input"]),
        "--out-dir", str(files["out"]),
        "--dry-run",
    ]
    assert benchmark.main(argv) == 2
    assert "replace-description" in capsys.readouterr().err


def test_rejects_missing_source_video(files: dict[str, Path], capsys: pytest.CaptureFixture[str]):
    files["source"].unlink()
    assert benchmark.main(argv_for(files, "--dry-run")) == 2
    assert "source" in capsys.readouterr().err.lower()


def test_rejects_duration_above_max(files: dict[str, Path]):
    assert benchmark.main(argv_for(files, "--dry-run", "--durations", "10", "31")) == 2


def test_rejects_map_pointing_at_missing_node(files: dict[str, Path], capsys: pytest.CaptureFixture[str]):
    nodes = [n for n in WORKFLOW_NODES if n != "90"]
    files["workflow"].write_text(json.dumps({n: {"inputs": {}} for n in nodes}), encoding="utf-8")
    assert benchmark.main(argv_for(files, "--dry-run")) == 2
    assert "node 90" in capsys.readouterr().err


def test_rejects_more_than_three_characters(files: dict[str, Path]):
    extra = []
    for _ in range(2):
        extra += ["--character-image", str(files["char1"]), "--replace-description", DESC_1]
    argv = argv_for(files, "--dry-run", *extra)
    assert benchmark.main(argv) == 2


def test_rejects_non_positive_price(files: dict[str, Path]):
    assert benchmark.main(argv_for(files, "--dry-run", "--price-brl-per-second", "0")) == 2


def test_rejects_retry_factor_below_one(files: dict[str, Path]):
    assert benchmark.main(argv_for(files, "--dry-run", "--retry-factor", "0.9")) == 2


# --- live loop with a fake backend (no ComfyUI, no worker/) -----------------------


class FakeClient:
    """Stands in for worker.comfy_client.ComfyClient. Fails the queue calls listed in fail_on."""

    def __init__(self, input_dir: Path, fail_on: frozenset[int]) -> None:
        self.input_dir = input_dir
        self.fail_on = fail_on
        self.queued: list[dict[str, Any]] = []
        self.inputs_present_at_queue: list[bool] = []

    def queue_prompt(self, workflow: dict[str, Any]) -> str:
        self.queued.append(workflow)
        self.inputs_present_at_queue.append((self.input_dir / workflow["source_video"]).is_file())
        return f"pid-{len(self.queued)}"

    def wait_for_outputs(self, prompt_id: str, output_node: str, kind: str, poll_s: float = 2.0) -> list[dict]:
        number = int(prompt_id.split("-")[1])
        if number in self.fail_on:
            raise TimeoutError("comfy did not finish in time")
        assert (output_node, kind) == ("90", "videos")
        return [{"filename": f"{prompt_id}.mp4", "subfolder": "", "type": "output"}]

    def download_output(self, item: dict[str, Any]) -> bytes:
        return b"fake mp4 bytes"


def fake_backend(input_dir: Path, fail_on: frozenset[int] = frozenset()) -> Backend:
    client = FakeClient(input_dir, fail_on)

    def build_prompt(characters: list[dict], prompt_extra: str | None) -> str:
        parts = [
            f"Replace {c['replace_description']} in <Video 1> with the person from <Picture {i}>."
            for i, c in enumerate(characters, 1)
        ]
        return " ".join(parts) + " Keep the original motion, camera, background and audio."

    def apply_workflow(template: dict, mapping: dict, **kwargs: Any) -> dict[str, Any]:
        return {
            "source_video": kwargs["source_video"],
            "character_images": kwargs["character_images"],
            "prompt": kwargs["prompt"],
            "length_frames": kwargs["length_frames"],
            "chunk_count": kwargs["chunk_count"],
        }

    return Backend(
        client=client,
        build_prompt=build_prompt,
        apply_workflow=apply_workflow,
        frames_for_duration=lambda seconds, fps=24: seconds * fps,
        chunk_count=lambda seconds: math.ceil(seconds / 15),
        probe=lambda path: {"duration_s": 10.0, "width": 768, "height": 1382, "fps": 24, "has_audio": True},
    )


def test_live_loop_records_failures_stages_cleans_up_and_reports(files: dict[str, Path]):
    cfg = load(files, "--durations", "10", "--repeats", "2")
    backend = fake_backend(files["input"], fail_on=frozenset({2}))
    gpu = GpuInfo("Fake GPU", "24576 MiB")

    runs = benchmark.execute_runs(cfg, backend, gpu=gpu)

    assert [r["ok"] for r in runs] == [True, False]
    assert "TimeoutError" in runs[1]["error"]
    assert runs[0]["gpu_name"] == "Fake GPU"
    assert runs[0]["length_frames"] == 240 and runs[0]["chunk_count"] == 1

    client = backend.client
    assert client.inputs_present_at_queue == [True, True]  # staged before queueing
    first_workflow = client.queued[0]
    assert first_workflow["source_video"].endswith("_source.mp4")
    assert first_workflow["character_images"][0].endswith("_char1.png")
    assert first_workflow["character_images"][1].endswith("_char2.jpg")
    assert "Replace o homem de boné, à esquerda in <Video 1> with the person from <Picture 1>." in first_workflow["prompt"]
    assert "<Picture 2>" in first_workflow["prompt"]
    assert list(files["input"].iterdir()) == []  # copies removed afterwards

    videos = sorted((files["out"] / "videos").iterdir())
    assert len(videos) == 1 and runs[0]["output_path"] == str(videos[0])

    meta = benchmark.build_meta(cfg, gpu, datetime.now(timezone.utc).isoformat())
    code = benchmark.report(cfg, runs, meta)
    assert code == 0  # at least one run succeeded

    summary_md = (files["out"] / "summary.md").read_text(encoding="utf-8")
    assert "| 10s | vast |" in summary_md
    assert "Falhas: 1 de 2" in summary_md
    assert "## Estresse: GPU 3x pior" in summary_md

    results = json.loads((files["out"] / "results.json").read_text(encoding="utf-8"))
    assert len(results["runs"]) == 2 and len(results["summary"]) == 2 and len(results["stress"]) == 2
    rows = list(csv.DictReader((files["out"] / "results.csv").open(encoding="utf-8")))
    assert rows[1]["ok"] == "False" and rows[1]["wall_seconds"] == ""
    assert "TimeoutError" in rows[1]["error"]


def test_report_returns_failure_when_no_run_succeeded(files: dict[str, Path]):
    cfg = load(files, "--durations", "10", "--repeats", "1")
    backend = fake_backend(files["input"], fail_on=frozenset({1}))
    runs = benchmark.execute_runs(cfg, backend, gpu=GpuInfo(None, None))
    meta = benchmark.build_meta(cfg, GpuInfo(None, None), datetime.now(timezone.utc).isoformat())
    assert benchmark.report(cfg, runs, meta) == 1


# --- small helpers ------------------------------------------------------------------


def test_detect_gpu_parses_first_line(monkeypatch: pytest.MonkeyPatch):
    def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess:
        return subprocess.CompletedProcess(args, 0, stdout="NVIDIA GeForce RTX 5090, 32607 MiB\n", stderr="")

    monkeypatch.setattr(benchmark.subprocess, "run", fake_run)
    assert benchmark.detect_gpu() == GpuInfo("NVIDIA GeForce RTX 5090", "32607 MiB")


def test_detect_gpu_never_raises(monkeypatch: pytest.MonkeyPatch):
    def missing(*args: Any, **kwargs: Any) -> None:
        raise FileNotFoundError("nvidia-smi")

    monkeypatch.setattr(benchmark.subprocess, "run", missing)
    assert benchmark.detect_gpu() == GpuInfo(None, None)


def test_write_results_csv_leaves_missing_fields_blank(tmp_path: Path):
    runs = [
        {"duration_requested": 10, "repeat": 1, "ok": True, "wall_seconds": 500.0, "output_duration_s": 10.0},
        {"duration_requested": 10, "repeat": 2, "ok": False, "error": "boom"},
    ]
    path = tmp_path / "results.csv"
    benchmark.write_results_csv(path, runs)
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    assert rows[0]["wall_seconds"] == "500.0"
    assert rows[1]["wall_seconds"] == "" and rows[1]["error"] == "boom"
