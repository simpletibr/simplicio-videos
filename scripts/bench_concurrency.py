#!/usr/bin/env python3
"""Benchmark of the asyncio concurrency in `swap` and `voice`, with SIMULATED latency (no network, no key, no cost).

What is measured: wall time of the same job run serially (--concurrency 1) and concurrently, and whether the output is
identical (swap: sha256 of the MP4 and of each chunk; voice: byte-identical timing.lock.json and WAVs).

How the latency is simulated, so the numbers are not mistaken for real provider numbers:
- swap: the `fake` adapter keeps each chunk `running` for `--latency` seconds (real time) and adds a fifth of it for the
  upload and for the download. The real ffmpeg work (cut, normalize, concat, remux) is NOT simulated: it runs for real
  and stays serial in both modes, so it is inside both times.
- voice: `voice._gemini` is replaced by a function that sleeps `--latency` seconds and writes a deterministic WAV. The
  per-line ffmpeg processing (trim, filter chain) runs for real and stays serial in both modes.

Real providers have their own latency, queue and rate limits: run it against them only on purpose and by hand.

Usage:
  scripts/bench_concurrency.py [--chunks 3] [--voice-lines 8] [--latency 1.0] [--repeat 3] [--json]
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import math
import os
import shutil
import statistics
import struct
import subprocess
import sys
import tempfile
import time
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

SWAP_CONCURRENCY = 3
VOICE_CONCURRENCY = 4
NOTES = [
    "Latência SIMULADA (adaptador fake e Gemini de voz trocado): mede só o ganho de sobrepor esperas; não é número de provedor real.",
    "O render (HyperFrames + ffmpeg) continua serial: é CPU, e asyncio não acelera CPU. Mais tarefas em paralelo só disputariam os mesmos núcleos.",
    "O ffmpeg do swap (corte, normalização, emenda, remontagem de áudio) e o da voz (corte de silêncio e cadeia de filtros) continuam seriais e entram nos dois tempos.",
    "Provedor de voz local (CPU) fica serial pelo mesmo motivo; só o provedor de rede (gemini) gera em paralelo.",
]


def _silent(fn, *a, **k):
    with contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
        return fn(*a, **k)


def _median(xs: list[float]) -> float:
    return round(statistics.median(xs), 3)


def _ffmpeg(*args: str) -> None:
    subprocess.run(["ffmpeg", "-y", "-v", "error", *args], check=True)


# -------------------------------------------------------------------------------------------------------------- swap

def bench_swap(chunks: int, latency: float, repeat: int, work: Path) -> dict:
    from simplicio_video import swap
    from simplicio_video.swap_providers import fake

    seg = 5.0
    video = work / "in.mp4"
    _ffmpeg("-f", "lavfi", "-i", f"testsrc=size=160x90:rate=24:duration={seg * chunks - 0.4}",
            "-f", "lavfi", "-i", f"sine=frequency=440:duration={seg * chunks - 0.4}",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(video))
    ref = work / "ref.png"
    _ffmpeg("-f", "lavfi", "-i", "color=c=red:s=32x32:d=0.1", "-frames:v", "1", str(ref))
    caps = fake.FakeAdapter.capabilities
    fake.FakeAdapter.capabilities = caps.__class__(**{**caps.__dict__, "max_input_s": seg})
    times: dict[str, list[float]] = {"serial": [], "parallel": []}
    outputs: dict[str, list[str]] = {"serial": [], "parallel": []}
    timing = None
    try:
        for r in range(repeat):
            for mode, conc in (("serial", 1), ("parallel", SWAP_CONCURRENCY)):
                fake.FakeAdapter.reset()
                fake.FakeAdapter.generation_s = latency
                fake.FakeAdapter.submit_delay_s = latency / 5
                fake.FakeAdapter.fetch_delay_s = latency / 5
                out = work / f"{mode}-{r}" / "out.mp4"
                argv = ["run", "--provider", "fake", "--video", str(video), "--ref", str(ref), "--out", str(out), "--autorizo",
                        "--yes", "--max-usd", "50", "--poll-interval", "0.05", "--concurrency", str(conc)]
                t0 = time.perf_counter()
                rc = _silent(swap.run_swap, argv)
                times[mode].append(time.perf_counter() - t0)
                if rc != 0:
                    raise SystemExit(f"bench: swap {mode} falhou ({rc})")
                man = json.loads((out.parent / swap.MANIFEST_NAME).read_text())
                outputs[mode].append(man["output"]["sha256"] + ":" + ",".join(c["sha256"] for c in man["chunks"]))
                if mode == "parallel":
                    timing = man["timing"]
    finally:
        fake.FakeAdapter.capabilities = caps
        fake.FakeAdapter.reset()
    s, p = _median(times["serial"]), _median(times["parallel"])
    return {"chunks": chunks, "concurrency": SWAP_CONCURRENCY, "latency_s": latency, "repeat": repeat,
            "serial_s": s, "parallel_s": p, "speedup": round(s / p, 3), "saved_s": round(s - p, 3),
            "identical_output": len(set(outputs["serial"] + outputs["parallel"])) == 1,
            "runs": {k: [round(x, 3) for x in v] for k, v in times.items()},
            "manifest_timing_last_parallel_run": timing}


# ------------------------------------------------------------------------------------------------------------- voice

def _wav_bytes(seed: int, seconds: float = 0.3, sr: int = 24000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1), w.setsampwidth(2), w.setframerate(sr)
        f = 300 + 40 * seed
        w.writeframes(b"".join(struct.pack("<h", int(8000 * math.sin(2 * math.pi * f * i / sr))) for i in range(int(seconds * sr))))
    return buf.getvalue()


def _voice_contract(dst: Path, lines: int) -> Path:
    import yaml
    shutil.copytree(ROOT / "tests" / "fixtures" / "mini", dst, ignore=shutil.ignore_patterns("out", "build", "timing.lock.json", "voz"))
    path = dst / "contract.yaml"
    data = yaml.safe_load(path.read_text())
    base = data["cenas"][0]
    cenas = []
    for i in range(lines):
        c = json.loads(json.dumps(base))
        c["id"] = f"s{i + 1}"
        c["fala"] = {"id": f"vo{i + 1}", "texto": f"fala numero {i + 1}", "inicio_s": 0.05, "max_s": 0.9}
        cenas.append(c)
    data["cenas"] = cenas
    data["voz"]["provider"] = "gemini"
    data["voz"]["providers"] = {"file": {"dir": "vo"}, "gemini": {"voice": "Laomedeia", "estilo": "alegre"}}
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False))
    return path


def bench_voice(lines: int, latency: float, repeat: int, work: Path) -> dict:
    from simplicio_video import contract as ct
    from simplicio_video import voice

    def simulated(S, text, dst, retries=4):
        n = int(text.rsplit(" ", 1)[1])
        time.sleep(latency)
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(_wav_bytes(n))
        return {"api": "interactions", "model": S["model"], "voice": S["voice"], "mime": "audio/wav", "chars": len(text),
                "usage": {"total_output_tokens": n}}

    real = voice._gemini
    voice._gemini = simulated
    times: dict[str, list[float]] = {"serial": [], "parallel": []}
    locks: dict[str, list[bytes]] = {"serial": [], "parallel": []}
    try:
        for r in range(repeat):
            for mode, conc in (("serial", 1), ("parallel", VOICE_CONCURRENCY)):
                path = _voice_contract(work / f"voice-{mode}-{r}", lines)
                t0 = time.perf_counter()
                _silent(voice.run, ct.load(path), provider="gemini", log=lambda *_: None, concurrency=conc)
                times[mode].append(time.perf_counter() - t0)
                locks[mode].append((path.parent / "timing.lock.json").read_bytes())
    finally:
        voice._gemini = real
    s, p = _median(times["serial"]), _median(times["parallel"])
    return {"lines": lines, "concurrency": VOICE_CONCURRENCY, "latency_s": latency, "repeat": repeat,
            "serial_s": s, "parallel_s": p, "speedup": round(s / p, 3), "saved_s": round(s - p, 3),
            "identical_lock": len(set(locks["serial"] + locks["parallel"])) == 1,
            "runs": {k: [round(x, 3) for x in v] for k, v in times.items()}}


def run(chunks: int = 3, voice_lines: int = 8, latency: float = 1.0, repeat: int = 3) -> dict:
    os.environ["SIMPLICIO_OFFLINE"] = "1"
    os.environ.pop("GEMINI_API_KEY", None)
    with tempfile.TemporaryDirectory(prefix="simplicio-bench-") as td:
        work = Path(td)
        return {"schema": "simplicio.bench-concurrency/v1", "simulated": True,
                "swap": bench_swap(chunks, latency, repeat, work),
                "voice": bench_voice(voice_lines, latency, repeat, work),
                "notes": NOTES}


def _text(rep: dict) -> str:
    s, v = rep["swap"], rep["voice"]
    rows = [
        "Benchmark de concorrência (latência SIMULADA, sem rede)",
        f"swap  {s['chunks']} pedaços, concurrency {s['concurrency']}, latência {s['latency_s']} s por pedaço, mediana de {s['repeat']}",
        f"      serial {s['serial_s']} s  paralelo {s['parallel_s']} s  ganho {s['speedup']}x  (economiza {s['saved_s']} s)  "
        f"saída idêntica: {s['identical_output']}",
        f"voice {v['lines']} falas, concurrency {v['concurrency']}, latência {v['latency_s']} s por fala, mediana de {v['repeat']}",
        f"      serial {v['serial_s']} s  paralelo {v['parallel_s']} s  ganho {v['speedup']}x  (economiza {v['saved_s']} s)  "
        f"lock idêntico: {v['identical_lock']}",
        "", *[f"- {n}" for n in rep["notes"]],
    ]
    return "\n".join(rows)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--chunks", type=int, default=3, help="pedaços do vídeo no swap (padrão 3)")
    ap.add_argument("--voice-lines", type=int, default=8, help="falas na voz (padrão 8)")
    ap.add_argument("--latency", type=float, default=1.0, help="segundos simulados por pedaço e por fala (padrão 1.0)")
    ap.add_argument("--repeat", type=int, default=3, help="repetições; vale a mediana (padrão 3)")
    ap.add_argument("--json", action="store_true", help="imprime o relatório em JSON")
    a = ap.parse_args(argv)
    if not (shutil.which("ffmpeg") and shutil.which("ffprobe")):
        print("bench: ffmpeg e ffprobe no PATH são necessários", file=sys.stderr)
        return 2
    rep = run(a.chunks, a.voice_lines, a.latency, a.repeat)
    print(json.dumps(rep, ensure_ascii=False, indent=2) if a.json else _text(rep))
    return 0 if rep["swap"]["identical_output"] and rep["voice"]["identical_lock"] else 1


if __name__ == "__main__":
    sys.exit(main())
