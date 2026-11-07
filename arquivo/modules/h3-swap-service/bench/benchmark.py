"""Measure real GPU cost per video second on a rented ComfyUI box and print the BRL table.

Run from the repo root:
    python -m bench.benchmark --help
    python -m bench.benchmark --dry-run ...   # validates arguments and files only
    python -m bench.benchmark ...             # live: needs ComfyUI up and worker/ importable

The live path (queue, wait, download, probe) uses worker/. It is imported lazily,
so --dry-run and the unit tests run without worker/.
"""

from __future__ import annotations

import argparse
import contextlib
import csv
import hashlib
import json
import math
import shutil
import subprocess
import sys
import time
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from bench import cost

BENCH_DIR = Path(__file__).resolve().parent
MAX_DURATION_S = 30  # CONTRACT section 2
FPS = 24  # CONTRACT section 2
MAX_CHARACTERS = 3  # CONTRACT section 4
DESCRIPTION_MIN = 3  # CONTRACT section 4
DESCRIPTION_MAX = 200  # CONTRACT section 4
SOURCE_SUFFIXES = frozenset({".mp4", ".mov", ".webm", ".mkv"})
IMAGE_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".webp"})
OUTPUT_KINDS = frozenset({"videos", "gifs", "images"})
DEFAULT_COMFY_URL = "http://127.0.0.1:8188"
DEFAULT_INPUT_DIR = "/opt/ComfyUI/input"  # CONTRACT section 6 default
DEFAULT_OUT_DIR = BENCH_DIR / "results"
DEFAULT_DURATIONS = (10, 30)
DEFAULT_REPEATS = 3
DEFAULT_PROVIDER_PRICES = "vast=0.767,salad=0.50"
DEFAULT_USD_BRL = 5.07
DEFAULT_PRICE_BRL_PER_SECOND = 0.16  # CONTRACT section 2: 16 centavos
DEFAULT_RETRY_FACTOR = 2.0
STRESS_FACTOR = 3.0

RUN_CSV_FIELDS = (
    "duration_requested",
    "repeat",
    "job_id",
    "ok",
    "wall_seconds",
    "output_duration_s",
    "width",
    "height",
    "has_audio",
    "length_frames",
    "chunk_count",
    "gpu_name",
    "gpu_memory",
    "output_path",
    "error",
)


class ConfigError(ValueError):
    """Bad arguments or files. Raised before anything is copied, queued or written."""


class BackendError(RuntimeError):
    """worker/ cannot be imported for a live run."""


@dataclass(frozen=True)
class GpuInfo:
    name: str | None
    memory: str | None


@dataclass(frozen=True)
class Backend:
    """The worker/ functions the live loop uses. Injected so tests can use fakes."""

    client: Any  # worker.comfy_client.ComfyClient
    build_prompt: Callable[..., str]
    apply_workflow: Callable[..., dict[str, Any]]
    frames_for_duration: Callable[..., int]
    chunk_count: Callable[..., int]
    probe: Callable[[str], dict[str, Any]]


@dataclass(frozen=True)
class BenchConfig:
    comfy_url: str
    workflow: Path
    map_path: Path
    source_video: Path
    character_images: tuple[Path, ...]
    descriptions: tuple[str, ...]
    durations: tuple[int, ...]
    repeats: int
    provider_prices: dict[str, float]
    usd_brl: float
    price_brl_per_second: float
    retry_factor: float
    input_dir: Path
    out_dir: Path
    dry_run: bool
    template: dict[str, Any] = field(repr=False)
    mapping: dict[str, Any] = field(repr=False)


# --- argument parsing and validation -----------------------------------------------


def _positive(value: float, label: str) -> None:
    if not math.isfinite(value) or value <= 0:
        raise ConfigError(f"{label} must be a number > 0, got {value!r}")


def parse_provider_prices(text: str) -> dict[str, float]:
    """'vast=0.767,salad=0.50' -> {'vast': 0.767, 'salad': 0.5} (USD per hour)."""
    prices: dict[str, float] = {}
    for item in text.split(","):
        name, sep, value = item.partition("=")
        name = name.strip().lower()
        if not sep or not name:
            raise ConfigError(f"--provider-prices: expected name=usd_per_hour, got {item.strip()!r}")
        if name in prices:
            raise ConfigError(f"--provider-prices: provider {name!r} given twice")
        try:
            usd_per_hour = float(value)
        except ValueError as exc:
            raise ConfigError(f"--provider-prices: {name} USD/h must be a number, got {value.strip()!r}") from exc
        _positive(usd_per_hour, f"--provider-prices {name} USD/h")
        prices[name] = usd_per_hour
    return prices


def failure_rate(runs: Sequence[dict[str, Any]]) -> float:
    if not runs:
        return 0.0
    return sum(1 for run in runs if run.get("ok") is not True) / len(runs)


def _existing_file(path: Path, label: str, suffixes: frozenset[str] | None = None) -> None:
    if not path.is_file():
        raise ConfigError(f"{label}: file not found: {path}")
    if suffixes is not None and path.suffix.lower() not in suffixes:
        raise ConfigError(f"{label}: expected one of {sorted(suffixes)}, got {path.suffix or 'no extension'}")


def _load_json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigError(f"{label}: cannot read JSON from {path}: {exc}") from exc
    if not isinstance(data, dict) or not data:
        raise ConfigError(f"{label}: expected a non-empty JSON object in {path}")
    return data


def check_map(mapping: dict[str, Any], workflow: dict[str, Any], *, n_chars: int) -> list[str]:
    """Every node the map points at must exist in the exported workflow."""
    errors: list[str] = []

    def check_ref(ref: Any, label: str) -> None:
        if not isinstance(ref, dict) or "node" not in ref or "field" not in ref:
            errors.append(f"map {label}: needs node and field")
        elif str(ref["node"]) not in workflow:
            errors.append(f"map {label}: node {ref['node']} is not in the workflow")

    inputs = mapping.get("inputs")
    if not isinstance(inputs, dict):
        return ["map: missing 'inputs' object"]
    for key in ("source_video", "prompt"):
        if key not in inputs:
            errors.append(f"map inputs: missing '{key}'")
        else:
            check_ref(inputs[key], f"inputs.{key}")
    slots = inputs.get("character_images")
    if not isinstance(slots, list) or len(slots) < n_chars:
        errors.append(f"map inputs.character_images: needs at least {n_chars} slot(s) for {n_chars} character(s)")
    else:
        for index, ref in enumerate(slots[:n_chars]):
            check_ref(ref, f"inputs.character_images[{index}]")
    for key in ("seed", "length_frames", "chunk_count"):
        if key in inputs:
            check_ref(inputs[key], f"inputs.{key}")
    output = mapping.get("output")
    if not isinstance(output, dict):
        errors.append("map: missing 'output' object")
    else:
        if output.get("kind") not in OUTPUT_KINDS:
            errors.append(f"map output.kind must be one of {sorted(OUTPUT_KINDS)}")
        if str(output.get("node")) not in workflow:
            errors.append(f"map output.node {output.get('node')} is not in the workflow")
    return errors


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m bench.benchmark",
        description="Measure GPU seconds per video second on a ComfyUI box and print the BRL business table.",
    )
    parser.add_argument("--comfy-url", default=DEFAULT_COMFY_URL, help="ComfyUI base URL (default %(default)s)")
    parser.add_argument("--workflow", required=True, type=Path, help="workflow exported from ComfyUI in API format")
    parser.add_argument("--map", dest="map_path", required=True, type=Path, help="workflow_map.json")
    parser.add_argument("--source-video", required=True, type=Path, help="source video to swap")
    parser.add_argument(
        "--character-image", action="append", type=Path, dest="character_images", metavar="PATH",
        help="character image, repeat 1 to 3 times",
    )
    parser.add_argument(
        "--replace-description", action="append", dest="descriptions", metavar="TEXT",
        help="who to replace, one per --character-image, 3 to 200 characters, never a name",
    )
    parser.add_argument(
        "--durations", nargs="+", type=int, default=list(DEFAULT_DURATIONS),
        help="requested video lengths in seconds, each 1 to 30 (default: 10 30)",
    )
    parser.add_argument("--repeats", type=int, default=DEFAULT_REPEATS, help="runs per duration (default %(default)s)")
    parser.add_argument(
        "--provider-prices", default=DEFAULT_PROVIDER_PRICES,
        help="name=USD_per_hour pairs, comma separated (default %(default)s)",
    )
    parser.add_argument("--usd-brl", type=float, default=DEFAULT_USD_BRL, help="BRL per USD (default %(default)s)")
    parser.add_argument(
        "--price-brl-per-second", type=float, default=DEFAULT_PRICE_BRL_PER_SECOND,
        help="client price in BRL per second of video (default %(default)s)",
    )
    parser.add_argument(
        "--retry-factor", type=float, default=DEFAULT_RETRY_FACTOR,
        help="GPU-time multiplier for retries and failures, >= 1.0 (default %(default)s)",
    )
    parser.add_argument(
        "--input-dir", type=Path, default=Path(DEFAULT_INPUT_DIR),
        help="ComfyUI input directory where inputs are staged (default %(default)s)",
    )
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR, help="results directory (default %(default)s)")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="validate arguments and files, print the plan; copies, queues and writes nothing",
    )
    return parser


def load_config(args: argparse.Namespace) -> BenchConfig:
    comfy_url = str(args.comfy_url).rstrip("/")
    if not comfy_url.startswith(("http://", "https://")):
        raise ConfigError("--comfy-url must start with http:// or https://")

    images = tuple(Path(p).resolve() for p in (args.character_images or []))
    descriptions = tuple(d.strip() for d in (args.descriptions or []))
    if not 1 <= len(images) <= MAX_CHARACTERS:
        raise ConfigError(f"--character-image: give 1 to {MAX_CHARACTERS}, got {len(images)}")
    if len(descriptions) != len(images):
        raise ConfigError(
            f"--replace-description: {len(descriptions)} given for {len(images)} --character-image"
        )
    for index, text in enumerate(descriptions, 1):
        if not DESCRIPTION_MIN <= len(text) <= DESCRIPTION_MAX:
            raise ConfigError(
                f"--replace-description #{index}: must be {DESCRIPTION_MIN} to {DESCRIPTION_MAX} characters"
            )
    for path in images:
        _existing_file(path, "--character-image", IMAGE_SUFFIXES)

    durations = tuple(args.durations)
    if not durations:
        raise ConfigError("--durations: give at least one value")
    for duration in durations:
        if not 1 <= duration <= MAX_DURATION_S:
            raise ConfigError(f"--durations: each value must be 1 to {MAX_DURATION_S}, got {duration}")
    if len(set(durations)) != len(durations):
        raise ConfigError("--durations: repeated values")
    if args.repeats < 1:
        raise ConfigError("--repeats must be >= 1")

    _positive(args.usd_brl, "--usd-brl")
    _positive(args.price_brl_per_second, "--price-brl-per-second")
    if not math.isfinite(args.retry_factor) or args.retry_factor < 1.0:
        raise ConfigError("--retry-factor must be >= 1.0")
    prices = parse_provider_prices(args.provider_prices)

    source = Path(args.source_video).resolve()
    _existing_file(source, "--source-video", SOURCE_SUFFIXES)
    workflow_path = Path(args.workflow).resolve()
    _existing_file(workflow_path, "--workflow")
    map_path = Path(args.map_path).resolve()
    _existing_file(map_path, "--map")
    template = _load_json_object(workflow_path, "--workflow")
    mapping = _load_json_object(map_path, "--map")
    map_errors = check_map(mapping, template, n_chars=len(images))
    if map_errors:
        raise ConfigError("; ".join(map_errors))

    input_dir = Path(args.input_dir)
    if not input_dir.is_dir():
        raise ConfigError(f"--input-dir: not a directory: {input_dir} (ComfyUI input folder)")
    out_dir = Path(args.out_dir)
    if out_dir.exists() and not out_dir.is_dir():
        raise ConfigError(f"--out-dir: exists and is not a directory: {out_dir}")

    return BenchConfig(
        comfy_url=comfy_url,
        workflow=workflow_path,
        map_path=map_path,
        source_video=source,
        character_images=images,
        descriptions=descriptions,
        durations=durations,
        repeats=int(args.repeats),
        provider_prices=prices,
        usd_brl=float(args.usd_brl),
        price_brl_per_second=float(args.price_brl_per_second),
        retry_factor=float(args.retry_factor),
        input_dir=input_dir.resolve(),
        out_dir=out_dir.resolve(),
        dry_run=bool(args.dry_run),
        template=template,
        mapping=mapping,
    )


def describe_plan(cfg: BenchConfig) -> str:
    output = cfg.mapping["output"]
    plan = [(d, r) for d in cfg.durations for r in range(1, cfg.repeats + 1)]
    lines = [
        "DRY RUN: nothing is copied, queued or written. No numbers are produced.",
        f"ComfyUI:     {cfg.comfy_url}",
        f"Workflow:    {cfg.workflow} ({len(cfg.template)} nodes)",
        f"Map:         {cfg.map_path} (output node {output['node']}, kind {output['kind']})",
        f"Source:      {cfg.source_video}",
    ]
    for index, (image, text) in enumerate(zip(cfg.character_images, cfg.descriptions), 1):
        lines.append(f"Character {index}: {image}  replace: {text!r}")
    lines += [
        f"Input dir:   {cfg.input_dir} (exists)",
        f"Out dir:     {cfg.out_dir} (not written)",
        "Providers:   " + ", ".join(f"{name}={value} USD/h" for name, value in cfg.provider_prices.items()),
        f"Prices:      USD/BRL {cfg.usd_brl}, R$ {cfg.price_brl_per_second}/s, retry-factor {cfg.retry_factor}",
        f"Plan: {len(plan)} runs",
    ]
    for index, (duration, repeat) in enumerate(plan, 1):
        lines.append(
            f"  {index}. {duration}s repeat {repeat}/{cfg.repeats}: stage inputs as <job_id>_*, "
            "queue, wait, download, probe"
        )
    lines.append("Prompt, frame count and chunk count are computed by worker/ at run time.")
    return "\n".join(lines)


# --- live path ----------------------------------------------------------------------


def load_worker_backend(comfy_url: str) -> Backend:
    try:
        from worker.comfy_client import ComfyClient
        from worker.media import probe
        from worker.workflow import (
            apply_workflow,
            build_prompt,
            chunk_count,
            frames_for_duration,
        )
    except ImportError as exc:
        raise BackendError(f"cannot import worker/ ({exc}). Run from the repo root with worker/ present.") from exc
    return Backend(
        client=ComfyClient(base_url=comfy_url),
        build_prompt=build_prompt,
        apply_workflow=apply_workflow,
        frames_for_duration=frames_for_duration,
        chunk_count=chunk_count,
        probe=probe,
    )


def detect_gpu() -> GpuInfo:
    """Best effort: first GPU reported by nvidia-smi. Never raises."""
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return GpuInfo(None, None)
    lines = out.strip().splitlines()
    name, _, memory = (lines[0] if lines else "").partition(",")
    return GpuInfo(name.strip() or None, memory.strip() or None)


def _stage_inputs(cfg: BenchConfig, job_id: str, staged: list[Path]) -> tuple[str, list[str]]:
    """Copy source and characters into ComfyUI's input dir. Each copy is appended to `staged`."""
    source_name = f"{job_id}_source{cfg.source_video.suffix.lower()}"
    destination = cfg.input_dir / source_name
    shutil.copyfile(cfg.source_video, destination)
    staged.append(destination)
    names: list[str] = []
    for index, image in enumerate(cfg.character_images, 1):
        name = f"{job_id}_char{index}{image.suffix.lower()}"
        destination = cfg.input_dir / name
        shutil.copyfile(image, destination)
        staged.append(destination)
        names.append(name)
    return source_name, names


def run_one(
    cfg: BenchConfig,
    backend: Backend,
    *,
    duration: int,
    repeat: int,
    gpu: GpuInfo,
    videos_dir: Path,
) -> dict[str, Any]:
    """One measured job. Failures are recorded in the returned dict, never raised."""
    job_id = uuid.uuid4().hex
    record: dict[str, Any] = {
        "duration_requested": duration,
        "repeat": repeat,
        "job_id": job_id,
        "ok": False,
        "error": None,
        "wall_seconds": None,
        "output_duration_s": None,
        "width": None,
        "height": None,
        "has_audio": None,
        "length_frames": None,
        "chunk_count": None,
        "gpu_name": gpu.name,
        "gpu_memory": gpu.memory,
        "output_path": None,
    }
    staged: list[Path] = []
    try:
        source_name, character_names = _stage_inputs(cfg, job_id, staged)
        length_frames = backend.frames_for_duration(duration, fps=FPS)
        chunks = backend.chunk_count(duration)
        record.update(length_frames=length_frames, chunk_count=chunks)
        prompt = backend.build_prompt(
            characters=[{"replace_description": text} for text in cfg.descriptions],
            prompt_extra=None,
        )
        workflow = backend.apply_workflow(
            cfg.template,
            cfg.mapping,
            source_video=source_name,
            character_images=character_names,
            prompt=prompt,
            seed=None,
            length_frames=length_frames,
            chunk_count=chunks,
        )
        output_node = str(cfg.mapping["output"]["node"])
        kind = str(cfg.mapping["output"]["kind"])

        started = time.monotonic()
        prompt_id = backend.client.queue_prompt(workflow)
        items = backend.client.wait_for_outputs(prompt_id, output_node, kind)
        record["wall_seconds"] = round(time.monotonic() - started, 3)  # queue -> outputs ready

        if not items:
            raise RuntimeError(f"no '{kind}' output on node {output_node}")
        item = items[0]
        data = backend.client.download_output(item)
        suffix = Path(str(item.get("filename", ""))).suffix or ".mp4"
        out_path = videos_dir / f"{duration}s_r{repeat}_{job_id}{suffix}"
        out_path.write_bytes(data)
        info = backend.probe(str(out_path))
        record.update(
            ok=True,
            output_path=str(out_path),
            output_duration_s=float(info["duration_s"]),
            width=int(info["width"]),
            height=int(info["height"]),
            has_audio=bool(info.get("has_audio")),
        )
    except Exception as exc:  # noqa: BLE001 - a failed run is recorded as data, never a crash
        record["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        for path in staged:
            with contextlib.suppress(OSError):
                path.unlink()
    return record


def execute_runs(cfg: BenchConfig, backend: Backend, *, gpu: GpuInfo) -> list[dict[str, Any]]:
    videos_dir = cfg.out_dir / "videos"
    videos_dir.mkdir(parents=True, exist_ok=True)
    total = len(cfg.durations) * cfg.repeats
    runs: list[dict[str, Any]] = []
    for duration in cfg.durations:
        for repeat in range(1, cfg.repeats + 1):
            record = run_one(cfg, backend, duration=duration, repeat=repeat, gpu=gpu, videos_dir=videos_dir)
            runs.append(record)
            status = "ok" if record["ok"] else f"FALHOU ({record['error']})"
            print(
                f"[{len(runs)}/{total}] {duration}s repeat {repeat}: {status}, wall={record['wall_seconds']}s",
                file=sys.stderr,
                flush=True,
            )
    return runs


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_meta(cfg: BenchConfig, gpu: GpuInfo, started_at: str) -> dict[str, Any]:
    return {
        "started_at": started_at,
        "finished_at": None,
        "comfy_url": cfg.comfy_url,
        "workflow": cfg.workflow.name,
        "workflow_sha256": _sha256(cfg.workflow),
        "map": cfg.map_path.name,
        "source_video": cfg.source_video.name,
        "characters": len(cfg.character_images),
        "durations": list(cfg.durations),
        "repeats": cfg.repeats,
        "provider_prices": dict(cfg.provider_prices),
        "usd_brl": cfg.usd_brl,
        "price_brl_per_second": cfg.price_brl_per_second,
        "retry_factor": cfg.retry_factor,
        "gpu_name": gpu.name,
        "gpu_memory": gpu.memory,
    }


def write_results_csv(path: Path, runs: Sequence[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=RUN_CSV_FIELDS, extrasaction="ignore", restval="")
        writer.writeheader()
        for run in runs:
            writer.writerow(run)


def render_summary_md(
    meta: dict[str, Any],
    runs: Sequence[dict[str, Any]],
    summary: Sequence[dict[str, Any]],
    stressed: Sequence[dict[str, Any]],
) -> str:
    total = len(runs)
    failed = sum(1 for run in runs if run.get("ok") is not True)
    rate = failure_rate(runs) * 100
    prices = ", ".join(f"{name} {value} USD/h" for name, value in meta["provider_prices"].items())
    lines = [
        "# Benchmark H3 swap: custo medido",
        "",
        f"- Início: {meta['started_at']} | Fim: {meta['finished_at']}",
        f"- GPU: {meta['gpu_name'] or 'desconhecida'} ({meta['gpu_memory'] or 'memória desconhecida'})",
        f"- ComfyUI: {meta['comfy_url']}",
        f"- Workflow: {meta['workflow']} (sha256 {meta['workflow_sha256'][:12]})",
        (
            f"- Premissas: USD/BRL {meta['usd_brl']}; preço R$ {meta['price_brl_per_second']}/s; "
            f"retry-factor {meta['retry_factor']}; provedores {prices}"
        ),
        "",
        "Custo = segundos de GPU medidos (da fila até o output) / 3600 x USD/h x USD/BRL x retry-factor.",
        "Cliente paga = ceil(duração gerada), no máximo o pedido, x R$/s.",
        "",
        "## Resultado",
        "",
        cost.render_markdown(summary).rstrip(),
        "",
        (
            f"Falhas: {failed} de {total} execuções ({cost.fmt_number(rate, 1)}%). "
            "Falhas não entram nas médias."
        ),
        "",
        f"## Estresse: GPU {STRESS_FACTOR:g}x pior",
        "",
        cost.render_markdown(stressed).rstrip(),
        "",
    ]
    return "\n".join(lines)


def write_outputs(
    out_dir: Path,
    meta: dict[str, Any],
    runs: Sequence[dict[str, Any]],
    summary: Sequence[dict[str, Any]],
    stressed: Sequence[dict[str, Any]],
) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "json": out_dir / "results.json",
        "csv": out_dir / "results.csv",
        "md": out_dir / "summary.md",
    }
    payload = {"meta": meta, "runs": list(runs), "summary": list(summary), "stress": list(stressed)}
    paths["json"].write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    write_results_csv(paths["csv"], runs)
    paths["md"].write_text(render_summary_md(meta, runs, summary, stressed), encoding="utf-8")
    return paths


def report(cfg: BenchConfig, runs: Sequence[dict[str, Any]], meta: dict[str, Any]) -> int:
    """Summarize, write results and print the table. Returns 0 if at least one run succeeded."""
    summary = cost.summarize(
        runs,
        usd_per_hour_by_provider=cfg.provider_prices,
        usd_brl=cfg.usd_brl,
        price_brl_per_second=cfg.price_brl_per_second,
        retry_factor=cfg.retry_factor,
    )
    stressed = cost.stress(summary, factor=STRESS_FACTOR)
    meta["finished_at"] = _now_iso()
    paths = write_outputs(cfg.out_dir, meta, runs, summary, stressed)

    failed = sum(1 for run in runs if run.get("ok") is not True)
    print(cost.render_markdown(summary))
    print(f"Falhas: {failed} de {len(runs)} execuções ({failure_rate(runs) * 100:.1f}%)")
    print(f"Estresse GPU {STRESS_FACTOR:g}x pior:")
    print(cost.render_markdown(stressed))
    print("Arquivos: " + ", ".join(str(p) for p in paths.values()))
    return 0 if any(run.get("ok") is True for run in runs) else 1


def run_benchmark(cfg: BenchConfig) -> int:
    try:
        backend = load_worker_backend(cfg.comfy_url)
    except BackendError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    started_at = _now_iso()
    gpu = detect_gpu()
    runs = execute_runs(cfg, backend, gpu=gpu)
    return report(cfg, runs, build_meta(cfg, gpu, started_at))


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        cfg = load_config(args)
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if cfg.dry_run:
        print(describe_plan(cfg))
        return 0
    return run_benchmark(cfg)


if __name__ == "__main__":
    raise SystemExit(main())
