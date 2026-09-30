"""`simplicio-video render`: contract -> workdir (compiler) -> engine build (music/SFX/VO mix) -> HyperFrames frames
-> ffmpeg master (-14 LUFS). Backends: local (this machine) or colab (bundle + notebook, GPU encode there).
Determinism: seeded engine, pinned HyperFrames, pinned inputs; render.manifest.json records the contract hash,
the hash of every compiled input and the decoded video/audio hashes of the output.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import time
import zipfile
from pathlib import Path

from . import HYPERFRAMES, __version__, paths
from .compiler import compile_project
from .contract import Contract, load_lock, validate
from .voice import sha256_file

SKIP_DIRS = {"out", "renders", ".debug", "node_modules"}
BUNDLE_SCRIPT = r"""#!/usr/bin/env bash
# Render a simplicio-video bundle (GPU encode when NVENC is available). Prints per-stage timings as JSON.
set -euo pipefail
cd "$(dirname "$0")"
Q="${1:-__QUALITY__}"
GPU=""; if command -v nvidia-smi >/dev/null 2>&1 && ffmpeg -hide_banner -encoders 2>/dev/null | grep -q h264_nvenc; then GPU="--gpu"; fi
mkdir -p out
t0=$(date +%s.%N)
npx --yes __HF__ render --quality "$Q" --strict-variables --variables-file build/variables.json --output out/raw.mp4 $GPU 2>&1 | tee out/render.log
t1=$(date +%s.%N)
bash scripts/master.sh out/raw.mp4 out/final.mp4
t2=$(date +%s.%N)
python3 - "$t0" "$t1" "$t2" "$GPU" <<'PY'
import json, re, sys
t0, t1, t2, gpu = float(sys.argv[1]), float(sys.argv[2]), float(sys.argv[3]), sys.argv[4]
log = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", open("out/render.log", encoding="utf8", errors="ignore").read())
def g(k):
    m = re.search(k + r" (?:([0-9]+)m ?)?([0-9.]+)s\b", log)
    return round(int(m.group(1) or 0) * 60 + float(m.group(2)), 2) if m else None
print("TIMINGS " + json.dumps({"render_s": round(t1 - t0, 2), "capture_s": g("capture"), "encode_s": g(r"encode(?: \(during capture\))?"),
    "master_s": round(t2 - t1, 2), "gpu_encode": bool(gpu)}))
PY
"""


def _run(cmd: list[str], cwd: Path, log) -> str:
    log("$ " + " ".join(cmd))
    p = subprocess.run(cmd, cwd=cwd, env=paths.node_env(), capture_output=True, text=True)
    out = (p.stdout or "") + (p.stderr or "")
    if p.returncode != 0:
        raise SystemExit(f"command failed ({p.returncode}): {' '.join(cmd)}\n{out[-4000:]}")
    return out


def _secs(log: str, key: str) -> float | None:
    """Parse HyperFrames summary durations like 'capture 21.1s' or 'capture 1m 5.2s'."""
    m = re.search(key + r" (?:([0-9]+)m ?)?([0-9.]+)s\b", log)
    return round(int(m.group(1) or 0) * 60 + float(m.group(2)), 2) if m else None


def tree_hash(root: Path) -> tuple[str, dict]:
    files = {}
    for p in sorted(root.rglob("*")):
        rel = p.relative_to(root)
        if p.is_file() and not (set(rel.parts[:-1]) & SKIP_DIRS) and rel.parts[0] not in SKIP_DIRS:
            files[str(rel)] = sha256_file(p)
    h = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()
    return h, files


def tool_versions() -> dict:
    def first(cmd):
        try:
            return subprocess.run(cmd, capture_output=True, text=True, env=paths.node_env()).stdout.splitlines()[0].strip()
        except Exception:  # noqa: BLE001 - informational only
            return None
    return {"simplicio_video": __version__, "hyperframes": HYPERFRAMES, "node": first(["node", "--version"]),
            "ffmpeg": first(["ffmpeg", "-version"]), "python": platform.python_version()}


def media_hashes(mp4: Path) -> dict:
    def dec(args):
        p = subprocess.run(["ffmpeg", "-v", "error", "-i", str(mp4), *args, "-"], capture_output=True, check=True)
        return p.stdout
    fmd5 = dec(["-map", "0:v:0", "-f", "framemd5"]).decode()
    frames = [ln.rsplit(",", 1)[-1].strip() for ln in fmd5.splitlines() if ln and not ln.startswith("#")]
    pcm = dec(["-map", "0:a:0", "-f", "s16le", "-ac", "2", "-ar", "48000"])
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(mp4)],
                               capture_output=True, text=True).stdout.strip())
    return {"sha256": sha256_file(mp4), "duration_s": round(dur, 3), "frames": len(frames),
            "video_frames_sha256": hashlib.sha256("\n".join(frames).encode()).hexdigest(),
            "audio_pcm_sha256": hashlib.sha256(pcm).hexdigest(), "frame_md5": frames}


def loudness(mp4: Path) -> dict:
    p = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(mp4), "-af", "ebur128=peak=true", "-f", "null", "-"],
                       capture_output=True, text=True)
    s = p.stderr[p.stderr.rfind("Summary:"):]
    i = re.search(r"I:\s+(-?[0-9.]+) LUFS", s)
    tp = re.search(r"Peak:\s+(-?[0-9.]+) dBFS", s)
    return {"integrated_lufs": float(i.group(1)) if i else None, "true_peak_dbfs": float(tp.group(1)) if tp else None}


def prepare(c: Contract, workdir: Path, log) -> tuple[dict, dict]:
    rep = validate(c, need_lock=True)
    for w in rep.warnings:
        log(f"warning: {w}")
    if not rep.ok:
        raise SystemExit("contract invalid:\n  " + "\n  ".join(rep.errors))
    lock = load_lock(c)
    t0 = time.time()
    compile_project(c, workdir, lock)
    _run(["node", "scripts/build.mjs"], workdir, log)
    inputs_sha, files = tree_hash(workdir)
    return {"inputs_sha256": inputs_sha, "files": files, "compile_build_s": round(time.time() - t0, 2)}, lock or {}


def render_local(c: Contract, out: Path | None = None, quality: str | None = None, workdir: Path | None = None,
                 gpu: bool = False, log=print) -> dict:
    wd = workdir or (c.dir / "build" / "simplicio-video")
    q = quality or c.data["saida"].get("qualidade", "delivery")
    info, lock = prepare(c, wd, log)
    dst = (out or c.rel(c.data["saida"]["arquivo"])).resolve()
    dst.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    cmd = ["npx", "--yes", HYPERFRAMES, "render", "--quality", q, "--strict-variables", "--variables-file", "build/variables.json",
           "--output", "out/raw.mp4"] + (["--gpu"] if gpu else [])
    rlog = _run(cmd, wd, log)
    t1 = time.time()
    mlog = _run(["bash", "scripts/master.sh", "out/raw.mp4", str(dst)], wd, log)
    t2 = time.time()
    rlog = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", rlog)
    (wd / "out" / "render.log").write_text(rlog)
    cap, enc = _secs(rlog, "capture"), _secs(rlog, r"encode(?: \(during capture\))?")
    media = media_hashes(dst)
    manifest = {
        "schema": "simplicio.render-manifest/v1",
        "contract": os.path.relpath(c.path, c.home), "contract_sha256": c.sha256(),
        "timing_lock_sha256": sha256_file(c.dir / "timing.lock.json") if (c.dir / "timing.lock.json").is_file() else None,
        "template": c.data["template"], "backend": "local", "quality": q, "gpu_encode": gpu,
        "inputs_sha256": info["inputs_sha256"], "inputs": info["files"], "tools": tool_versions(),
        "output": {"path": os.path.relpath(dst, c.dir), **{k: v for k, v in media.items() if k != "frame_md5"}},
        "loudness": loudness(dst),
        "drive": c.data["drive"],
        "timings_s": {"compile_build": info["compile_build_s"], "render": round(t1 - t0, 2),
                      "capture": cap, "encode": enc,
                      "master": round(t2 - t1, 2)},
    }
    (c.dir / "render.manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf8")
    (dst.parent / (dst.stem + ".frames.md5")).write_text("\n".join(media["frame_md5"]) + "\n")
    log(mlog.strip().splitlines()[-1] if mlog.strip() else "")
    log(f"render: {dst} ({media['duration_s']} s, {media['frames']} frames) · inputs {info['inputs_sha256'][:12]} · "
        f"frames {media['video_frames_sha256'][:12]} · audio {media['audio_pcm_sha256'][:12]}")
    return manifest


def render_colab(c: Contract, out: Path | None = None, quality: str | None = None, log=print) -> dict:
    wd = c.dir / "build" / "simplicio-video"
    q = quality or c.data["saida"].get("qualidade", "delivery")
    info, _ = prepare(c, wd, log)
    (wd / "render_bundle.sh").write_text(BUNDLE_SCRIPT.replace("__QUALITY__", q).replace("__HF__", HYPERFRAMES))
    bundle_meta = {"schema": "simplicio.render-bundle/v1", "contract": os.path.relpath(c.path, c.home), "contract_sha256": c.sha256(),
                   "inputs_sha256": info["inputs_sha256"], "quality": q, "tools": tool_versions(),
                   "output_name": Path(c.data["saida"]["arquivo"]).name, "drive": c.data["drive"],
                   "run": "bash render_bundle.sh  # -> out/final.mp4"}
    ref = c.dir / "render.manifest.json"
    if ref.is_file():
        m = json.loads(ref.read_text(encoding="utf8"))
        if m.get("inputs_sha256") == info["inputs_sha256"]:  # same compiled inputs -> local render is a valid reference
            bundle_meta["reference_local"] = {k: m["output"][k] for k in ("sha256", "video_frames_sha256", "audio_pcm_sha256", "frames", "duration_s")}
            bundle_meta["reference_local"]["timings_s"] = m.get("timings_s")
            bundle_meta["reference_local"]["tools"] = m.get("tools")
    (wd / "bundle.json").write_text(json.dumps(bundle_meta, indent=2, ensure_ascii=False) + "\n", encoding="utf8")
    dst = (out or c.rel(str(Path(c.data["saida"]["arquivo"]).with_suffix("")) + ".colab-bundle.zip")).resolve()
    if dst.suffix != ".zip":
        dst = dst / (Path(c.data["saida"]["arquivo"]).stem + ".colab-bundle.zip")
    dst.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(wd.rglob("*")):
            rel = p.relative_to(wd)
            if p.is_file() and rel.parts[0] not in SKIP_DIRS:
                zi = zipfile.ZipInfo(str(rel), date_time=(2026, 1, 1, 0, 0, 0))  # fixed timestamps -> reproducible zip
                zi.compress_type = zipfile.ZIP_DEFLATED
                zi.external_attr = (0o755 if p.suffix == ".sh" else 0o644) << 16
                z.writestr(zi, p.read_bytes())
    nb = c.home / "colab" / "render.ipynb"
    log(f"colab bundle: {dst} ({dst.stat().st_size / 1e6:.1f} MB, inputs {info['inputs_sha256'][:12]})")
    log(f"notebook: {nb} - open in Colab (GPU runtime), upload the bundle, run all cells")
    return {**bundle_meta, "bundle": str(dst), "bundle_sha256": sha256_file(dst), "notebook": str(nb)}
