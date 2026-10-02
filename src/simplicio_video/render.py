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
# Render a simplicio-video bundle. Prints per-stage timings + environment as JSON (TIMINGS {...}).
# env: SV_GPU_ENCODE=auto|1|0 (NVENC encode; default __GPU_ENCODE__), SV_BROWSER_GPU=0|1 (Chrome GPU raster; default 0 =
#      deterministic SwiftShader), SV_WORKERS=auto|N (parallel Chrome capture workers; HyperFrames auto = cores-2).
set -euo pipefail
cd "$(dirname "$0")"
Q="${1:-__QUALITY__}"
GPU_ENCODE="${SV_GPU_ENCODE:-__GPU_ENCODE__}"
GPU=""; GPU_WHY="off"
if [ "$GPU_ENCODE" != "0" ]; then
  # never pipe ffmpeg into grep -q here: with pipefail, grep -q exits early, ffmpeg gets SIGPIPE (141) and the test is false
  # even when h264_nvenc exists (the bug that left gpu_encode=false on the Colab T4).
  ENC="$(ffmpeg -hide_banner -encoders 2>/dev/null || true)"
  if ! command -v nvidia-smi >/dev/null 2>&1 || ! nvidia-smi >/dev/null 2>&1; then GPU_WHY="no nvidia-smi/driver"
  elif ! grep -q h264_nvenc <<<"$ENC"; then GPU_WHY="ffmpeg without h264_nvenc"
  elif ! ffmpeg -hide_banner -v error -f lavfi -i color=c=black:s=256x256:d=0.2 -c:v h264_nvenc -f null - >/dev/null 2>&1; then
    GPU_WHY="h264_nvenc present but test encode failed (driver/libnvidia-encode)"
  else GPU="--gpu"; GPU_WHY="nvenc ok"; fi
fi
BROWSER="--no-browser-gpu"; if [ "${SV_BROWSER_GPU:-__BROWSER_GPU__}" = "1" ]; then BROWSER="--browser-gpu"; fi
# keep BeginFrame capture with the software (SwiftShader) raster: same pixels as the local reference
export PRODUCER_FORCE_SCREENSHOT="${PRODUCER_FORCE_SCREENSHOT:-false}"
SV_WORKERS="${SV_WORKERS:-__WORKERS__}"
WORKERS=""; if [ "${SV_WORKERS}" != "auto" ]; then WORKERS="--workers ${SV_WORKERS}"; fi
echo "render_bundle: gpu_encode=${GPU:-no} (${GPU_WHY}) browser=${BROWSER} workers=${SV_WORKERS} nproc=$(nproc)"
mkdir -p out
t0=$(date +%s.%N)
npx --yes __HF__ render --quality "$Q" --strict-variables --variables-file build/variables.json --output out/raw.mp4 $GPU $BROWSER $WORKERS 2>&1 | tee out/render.log
t1=$(date +%s.%N)
bash scripts/master.sh out/raw.mp4 out/final.mp4
t2=$(date +%s.%N)
python3 - "$t0" "$t1" "$t2" "$GPU" "$GPU_WHY" "$BROWSER" <<'PY'
import json, os, re, shutil, subprocess, sys
t0, t1, t2, gpu, why, browser = float(sys.argv[1]), float(sys.argv[2]), float(sys.argv[3]), sys.argv[4], sys.argv[5], sys.argv[6]
log = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", open("out/render.log", encoding="utf8", errors="ignore").read())
def g(k):
    m = re.search(k + r" (?:([0-9]+)m ?)?([0-9.]+)s\b", log)
    return round(int(m.group(1) or 0) * 60 + float(m.group(2)), 2) if m else None
def first(cmd):
    try:
        return (subprocess.run(cmd, capture_output=True, text=True, timeout=30).stdout.strip().splitlines() or [None])[0]
    except Exception:
        return None
def mem_gb():
    try:
        return round(int(open("/proc/meminfo").read().split()[1]) / 1048576, 1)
    except Exception:
        return None
w = re.findall(r'"workerCount":\s*([0-9]+)', log) or re.findall(r"\(([0-9]+) workers?\)", log)
chrome = os.environ.get("HYPERFRAMES_BROWSER_PATH") or shutil.which("chrome-headless-shell") or shutil.which("google-chrome")
fonts = subprocess.run("fc-list 2>/dev/null | wc -l", shell=True, capture_output=True, text=True).stdout.strip()
env = {"nproc": os.cpu_count(), "mem_gb": mem_gb(), "workers": int(w[-1]) if w else None, "browser": browser,
       "chrome": first([chrome, "--version"]) if chrome else None, "ffmpeg": first(["ffmpeg", "-version"]),
       "node": first(["node", "--version"]), "system_fonts": int(fonts) if fonts.isdigit() else None,
       "gpu": first(["nvidia-smi", "--query-gpu=name,driver_version", "--format=csv,noheader"]) if shutil.which("nvidia-smi") else None}
print("TIMINGS " + json.dumps({"render_s": round(t1 - t0, 2), "capture_s": g("capture"), "encode_s": g(r"encode(?: \(during capture\))?"),
    "master_s": round(t2 - t1, 2), "gpu_encode": bool(gpu), "gpu_encode_reason": why, "env": env}))
PY
"""


def bundle_script(quality: str, gpu_encode: str = "auto") -> str:
    """render_bundle.sh with the defaults baked in. SV_WORKERS / SV_BROWSER_GPU set when the bundle is built become the
    remote defaults (Kaggle and colab-cli can't receive arbitrary env); the remote env still overrides them."""
    if gpu_encode not in ("auto", "1", "0"):
        raise ValueError("gpu_encode must be auto|1|0")
    workers = os.environ.get("SV_WORKERS", "auto") or "auto"
    if workers != "auto" and not workers.isdigit():
        raise ValueError("SV_WORKERS must be auto or an integer")
    browser_gpu = "1" if os.environ.get("SV_BROWSER_GPU") == "1" else "0"
    return (BUNDLE_SCRIPT.replace("__QUALITY__", quality).replace("__HF__", HYPERFRAMES).replace("__GPU_ENCODE__", gpu_encode)
            .replace("__WORKERS__", workers).replace("__BROWSER_GPU__", browser_gpu))


def _run(cmd: list[str], cwd: Path, log, extra_env: dict | None = None) -> str:
    log("$ " + " ".join(cmd))
    p = subprocess.run(cmd, cwd=cwd, env={**paths.node_env(), **(extra_env or {})}, capture_output=True, text=True)
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
                 gpu: bool = False, log=print, manifest: bool = True) -> dict:
    wd = workdir or (c.dir / "build" / "simplicio-video")
    q = quality or c.data["saida"].get("qualidade", "delivery")
    info, lock = prepare(c, wd, log)
    dst = (out or c.rel(c.data["saida"]["arquivo"])).resolve()
    dst.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    cmd = ["npx", "--yes", HYPERFRAMES, "render", "--quality", q, "--strict-variables", "--variables-file", "build/variables.json",
           "--output", "out/raw.mp4", "--browser-gpu" if os.environ.get("SV_BROWSER_GPU") == "1" else "--no-browser-gpu"]
    cmd += (["--gpu"] if gpu else []) + (["--workers", os.environ["SV_WORKERS"]] if os.environ.get("SV_WORKERS", "auto") != "auto" else [])
    # software raster + BeginFrame capture, pinned explicitly (same pixels as the remote bundles, see ADR-0003)
    rlog = _run(cmd, wd, log, {"PRODUCER_FORCE_SCREENSHOT": "false"})
    t1 = time.time()
    mlog = _run(["bash", "scripts/master.sh", "out/raw.mp4", str(dst)], wd, log)
    t2 = time.time()
    rlog = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", rlog)
    (wd / "out" / "render.log").write_text(rlog)
    cap, enc = _secs(rlog, "capture"), _secs(rlog, r"encode(?: \(during capture\))?")
    timings = {"compile_build": info["compile_build_s"], "render": round(t1 - t0, 2), "capture": cap, "encode": enc,
               "master": round(t2 - t1, 2)}
    log(mlog.strip().splitlines()[-1] if mlog.strip() else "")
    if not manifest:  # render --preview: never overwrite the delivery render.manifest.json
        return {"output": str(dst), "inputs_sha256": info["inputs_sha256"], "quality": q, "timings_s": timings}
    return write_manifest(c, dst, backend="local", quality=q, gpu=gpu, info=info, timings=timings, log=log)


def write_manifest(c: Contract, dst: Path, backend: str, quality: str, gpu: bool, info: dict, timings: dict,
                   tools: dict | None = None, usage: dict | None = None, log=print) -> dict:
    """render.manifest.json next to the contract (same schema for every backend) + <out>.frames.md5."""
    media = media_hashes(dst)
    manifest = {
        "schema": "simplicio.render-manifest/v1",
        "contract": os.path.relpath(c.path, c.home), "contract_sha256": c.sha256(),
        "timing_lock_sha256": sha256_file(c.dir / "timing.lock.json") if (c.dir / "timing.lock.json").is_file() else None,
        "template": c.data["template"], "backend": backend, "quality": quality, "gpu_encode": gpu,
        "inputs_sha256": info["inputs_sha256"], "inputs": info["files"], "tools": tools or tool_versions(),
        "output": {"path": os.path.relpath(dst, c.dir), **{k: v for k, v in media.items() if k != "frame_md5"}},
        "loudness": loudness(dst),
        "drive": c.data["drive"],
        "timings_s": timings,
    }
    if usage:
        manifest["usage"] = usage
    (c.dir / "render.manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf8")
    (dst.parent / (dst.stem + ".frames.md5")).write_text("\n".join(media["frame_md5"]) + "\n")
    log(f"render[{backend}]: {dst} ({media['duration_s']} s, {media['frames']} frames) · inputs {info['inputs_sha256'][:12]} · "
        f"frames {media['video_frames_sha256'][:12]} · audio {media['audio_pcm_sha256'][:12]}")
    return manifest


def build_bundle(c: Contract, out: Path | None = None, quality: str | None = None, gpu_encode: str = "auto",
                 log=print) -> dict:
    """Compile + engine build, then zip the workdir into a reproducible bundle (fixed timestamps) with
    render_bundle.sh and bundle.json. Shared by the colab, colab-cli and kaggle backends."""
    wd = c.dir / "build" / "simplicio-video"
    q = quality or c.data["saida"].get("qualidade", "delivery")
    info, _ = prepare(c, wd, log)
    (wd / "render_bundle.sh").write_text(bundle_script(q, gpu_encode))
    bundle_meta = {"schema": "simplicio.render-bundle/v1", "contract": os.path.relpath(c.path, c.home), "contract_sha256": c.sha256(),
                   "inputs_sha256": info["inputs_sha256"], "quality": q, "tools": tool_versions(),
                   "output_name": Path(c.data["saida"]["arquivo"]).name, "drive": c.data["drive"],
                   "run": "bash render_bundle.sh  # -> out/final.mp4"}
    if os.environ.get("SIMPLICIO_FFMPEG_URL"):  # pinned static ffmpeg: remote_render.py downloads + verifies the same build
        bundle_meta["toolchain"] = {"ffmpeg_url": os.environ["SIMPLICIO_FFMPEG_URL"],
                                    "ffmpeg_sha256": os.environ.get("SIMPLICIO_FFMPEG_SHA256")}
    ref = c.dir / "render.manifest.json"
    if ref.is_file():
        m = json.loads(ref.read_text(encoding="utf8"))
        if m.get("inputs_sha256") == info["inputs_sha256"] and m.get("backend", "local") == "local":
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
    log(f"bundle: {dst} ({dst.stat().st_size / 1e6:.1f} MB, inputs {info['inputs_sha256'][:12]})")
    return {**bundle_meta, "bundle": str(dst), "bundle_sha256": sha256_file(dst), "files": info["files"],
            "compile_build_s": info["compile_build_s"]}


def render_colab(c: Contract, out: Path | None = None, quality: str | None = None, gpu_encode: str = "auto",
                 log=print) -> dict:
    """Manual Colab: bundle + colab/render.ipynb opened in the browser (use --backend colab-cli for no browser)."""
    res = build_bundle(c, out, quality, gpu_encode=gpu_encode, log=log)
    nb = c.home / "colab" / "render.ipynb"
    log(f"notebook: {nb} - open in Colab (GPU runtime), upload the bundle, run all cells "
        "(no browser: `simplicio-video render <contrato> --backend colab-cli`)")
    return {**{k: v for k, v in res.items() if k not in ("files", "compile_build_s")}, "notebook": str(nb)}


# ---------------------------------------------------------------------------------------------------------------------
# render --preview: low-res watermarked sales preview (simplicio-video prospect). Deterministic ffmpeg post-process of a
# draft local render: 540x960 @30 fps, x264 crf 30, diagonal tiled watermark + corner badge + end card.
# Branding (Wesley, 30/09/2026): Wesley Simplicio + Instagram @wesleysimplicio; never SimpleTI/simpleti.com.br on previews.
PREVIEW = {"width": 540, "height": 960, "fps": 30, "crf": 30, "end_card_s": 2.5,
           "watermark": "Prévia • Wesley Simplicio • @wesleysimplicio", "badge": "PRÉVIA · @wesleysimplicio",
           "end_title": "Vídeo feito por Wesley Simplicio", "end_url": "@wesleysimplicio", "end_note": "Prévia em baixa resolução"}
# Same branding in the language of the video (INT-1, 01/10/2026): the language comes from voz.idioma (en-US, de-CH, fr-CH...).
PREVIEW_I18N = {
    "pt": {k: PREVIEW[k] for k in ("watermark", "badge", "end_title", "end_url", "end_note")},
    "en": {"watermark": "Preview • Wesley Simplicio • @wesleysimplicio", "badge": "PREVIEW · @wesleysimplicio",
           "end_title": "Video by Wesley Simplicio", "end_url": "@wesleysimplicio", "end_note": "Low-resolution preview"},
    "de": {"watermark": "Vorschau • Wesley Simplicio • @wesleysimplicio", "badge": "VORSCHAU · @wesleysimplicio",
           "end_title": "Video von Wesley Simplicio", "end_url": "@wesleysimplicio", "end_note": "Vorschau in niedriger Auflösung"},
    "fr": {"watermark": "Aperçu • Wesley Simplicio • @wesleysimplicio", "badge": "APERÇU · @wesleysimplicio",
           "end_title": "Vidéo réalisée par Wesley Simplicio", "end_url": "@wesleysimplicio", "end_note": "Aperçu en basse résolution"},
}


def preview_lang(idioma: str | None) -> str:
    """'en-US' -> 'en'; unknown or empty -> 'pt' (the Brazilian default)."""
    lang = (idioma or "pt").split("-")[0].split("_")[0].lower()
    return lang if lang in PREVIEW_I18N else "pt"


def preview_texts(lang: str = "pt") -> dict:
    """PREVIEW spec with the watermark/badge/end-card texts in `lang` (pt, en, de, fr)."""
    return {**PREVIEW, **PREVIEW_I18N[preview_lang(lang)]}


def preview_font(home: Path) -> Path:
    for t in ("assistencia-tecnica-games", "saude-odontologia"):
        f = home / "templates" / t / "composition" / "assets" / "fonts" / "Inter.ttf"
        if f.is_file():
            return f
    hits = sorted((home / "templates").rglob("Inter*.ttf"))
    if not hits:
        raise SystemExit("render --preview: no Inter.ttf under templates/*/composition/assets/fonts")
    return hits[0]


def preview_logo(home: Path) -> Path | None:
    """Wesley Simplicio logo, only if one is versioned in the repo (assets/brand/wesley-simplicio-logo.png); else text-only."""
    for name in ("wesley-simplicio-logo.png",):
        f = home / "assets" / "brand" / name
        if f.is_file():
            return f
    return None


WATERMARK_STYLES = {  # rows, spacing (px on the 1000x1000 canvas), font size, alpha
    "padrao": {"rows": 10, "step": 100, "size": 30, "alpha": 0.2, "border": 2},
    "sutil": {"rows": 5, "step": 200, "size": 26, "alpha": 0.11, "border": 1},
}


def preview_filter(dur_s: float, font: Path, tmp: Path, logo: bool = False, lang: str = "pt", note: str | None = None,
                   wm: str = "padrao") -> str:
    """filter_complex for: [0] draft render, [1] logo (optional). Output labels [v] [a].
    lang = language of the watermark/badge/end card; note = extra top-centre label (e.g. provisional audio), never on finals."""
    P = preview_texts(lang)
    W, H, fps = P["width"], P["height"], P["fps"]
    def tf(name: str, text: str) -> str:
        f = tmp / f"{name}.txt"
        f.write_text(text, encoding="utf8")
        return str(f).replace("\\", "/").replace(":", "\\:")
    ff = str(font).replace(":", "\\:")
    S = WATERMARK_STYLES.get(wm, WATERMARK_STYLES["padrao"])
    row = tf("wm", ("   " + P["watermark"]) * (3 if wm == "padrao" else 2))
    # diagonal tiled rows on a transparent 1000x1000 canvas, rotated -30° and centred over the 540x960 frame
    rows = []
    for i in range(S["rows"]):
        y = 30 + i * S["step"] + (0 if wm == "padrao" else 60)
        x = -((i * 137) % 260)
        rows.append(f"drawtext=fontfile='{ff}':textfile='{row}':x={x}:y={y}:fontsize={S['size']}:fontcolor=white:"
                    f"borderw={S['border']}:bordercolor=black")
    wmf = (f"color=c=black@0.0:s=1000x1000:r={fps}:d={dur_s:.3f},format=rgba," + ",".join(rows) +
           f",rotate=-30*PI/180:c=none:ow=1000:oh=1000,colorchannelmixer=aa={S['alpha']}[wm]")
    badge = tf("badge", P["badge"])
    main = (f"[0:v]scale={W}:{H}:flags=lanczos,fps={fps},setsar=1,format=yuv420p[m0];"
            f"{wmf};[m0][wm]overlay=x=(W-w)/2:y=(H-h)/2:shortest=1,"
            f"drawtext=fontfile='{ff}':textfile='{badge}':x=w-tw-18:y=18:fontsize=18:fontcolor=white@0.85:"
            f"box=1:boxcolor=black@0.45:boxborderw=8,"
            f"drawtext=fontfile='{ff}':textfile='{badge}':x=18:y=h-th-22:fontsize=18:fontcolor=white@0.85:"
            f"box=1:boxcolor=black@0.45:boxborderw=8")
    if note:
        nt = tf("note", note)
        main += (f",drawtext=fontfile='{ff}':textfile='{nt}':x=(w-tw)/2:y=64:fontsize=20:fontcolor=white:"
                 f"box=1:boxcolor=0xc0392b@0.85:boxborderw=10")
    if logo:
        main += f"[m1];[1:v]scale=90:-1,format=rgba,colorchannelmixer=aa=0.55[lg];[m1][lg]overlay=x=18:y=18"
    main += "[mv];"
    t1, t2, t3 = tf("end1", P["end_title"]), tf("end2", P["end_url"]), tf("end3", P["end_note"])
    e = P["end_card_s"]
    end = (f"color=c=0x0b0b10:s={W}x{H}:r={fps}:d={e},format=yuv420p,"
           f"drawtext=fontfile='{ff}':textfile='{t1}':x=(w-tw)/2:y=h/2-70:fontsize=34:fontcolor=white,"
           f"drawtext=fontfile='{ff}':textfile='{t2}':x=(w-tw)/2:y=h/2:fontsize=44:fontcolor=0x4fa3ff,"
           f"drawtext=fontfile='{ff}':textfile='{t3}':x=(w-tw)/2:y=h/2+80:fontsize=20:fontcolor=white@0.6,"
           f"fade=t=in:st=0:d=0.35[ev];")
    audio = (f"[0:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,"
             f"afade=t=out:st={max(dur_s - 0.4, 0):.3f}:d=0.4[ma];"
             f"anullsrc=r=48000:cl=stereo,atrim=duration={e},aformat=sample_fmts=fltp:channel_layouts=stereo[ea];"
             f"[mv][ma][ev][ea]concat=n=2:v=1:a=1[v][a]")
    return main + end + audio


def make_preview(src: Path, dst: Path, home: Path, log=print, lang: str = "pt", note: str | None = None, wm: str = "padrao") -> dict:
    """Draft render -> watermarked 540x960 preview (+ end card). Returns {path, sha256, duration_s, bytes}.
    lang picks the watermark/end-card language (pt default); note adds a top label (provisional/mute layout checks)."""
    import tempfile
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(src)],
                               capture_output=True, text=True, env=paths.node_env()).stdout.strip())
    logo = preview_logo(home)
    dst.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as td:
        fc = preview_filter(dur, preview_font(home), Path(td), logo=bool(logo), lang=lang, note=note, wm=wm)
        cmd = ["ffmpeg", "-y", "-v", "error", "-i", str(src)] + (["-i", str(logo)] if logo else []) + [
            "-filter_complex", fc, "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "medium",
            "-crf", str(PREVIEW["crf"]), "-pix_fmt", "yuv420p", "-r", str(PREVIEW["fps"]), "-threads", "4",
            "-c:a", "aac", "-b:a", "96k", "-ar", "48000", "-movflags", "+faststart", "-map_metadata", "-1",
            "-fflags", "+bitexact", "-flags:v", "+bitexact", "-flags:a", "+bitexact", str(dst)]
        log(f"$ ffmpeg (prévia {PREVIEW['width']}x{PREVIEW['height']} crf {PREVIEW['crf']}, marca d'água + cartão final) -> {dst}")
        p = subprocess.run(cmd, cwd=dst.parent, env=paths.node_env(), capture_output=True, text=True)
        if p.returncode != 0:
            raise SystemExit(f"render --preview: ffmpeg failed ({p.returncode})\n{(p.stderr or '')[-3000:]}")
    out_dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(dst)],
                                   capture_output=True, text=True, env=paths.node_env()).stdout.strip())
    return {"path": str(dst), "sha256": sha256_file(dst), "duration_s": round(out_dur, 3), "bytes": dst.stat().st_size,
            "watermark": preview_texts(lang)["watermark"], "lang": preview_lang(lang), "logo": str(logo) if logo else None,
            "marca_dagua": wm, **({"note": note} if note else {})}


def render_preview(c: Contract, out: Path | None = None, workdir: Path | None = None, log=print, note: str | None = None) -> dict:
    """`render --preview`: draft local render (no delivery manifest) -> make_preview. Writes preview.manifest.json.
    The watermark/end-card language follows voz.idioma (pt-BR default; en/de/fr for the international previews)."""
    t0 = time.time()
    raw = c.dir / "out" / "draft-full.mp4"
    info = render_local(c, out=raw, quality="draft", workdir=workdir, log=log, manifest=False)
    t1 = time.time()
    s = c.data["saida"]["arquivo"]
    dst = (out or c.rel(str(Path(s).with_name(Path(s).stem + "-previa.mp4")))).resolve()
    lang = preview_lang((c.data.get("voz") or {}).get("idioma"))
    res = make_preview(raw, dst, c.home, log=log, lang=lang, note=note, wm=(c.data.get("saida") or {}).get("marca_dagua", "padrao"))
    t2 = time.time()
    man = {"schema": "simplicio.preview-manifest/v1", "contract_sha256": c.sha256(), "inputs_sha256": info["inputs_sha256"],
           "preview": {**res, "path": os.path.relpath(dst, c.dir)}, "spec": dict(preview_texts(lang)),
           "timings_s": {**info["timings_s"], "render_total": round(t1 - t0, 2), "preview_post": round(t2 - t1, 2),
                         "total": round(t2 - t0, 2)}}
    (c.dir / "preview.manifest.json").write_text(json.dumps(man, indent=2, ensure_ascii=False) + "\n", encoding="utf8")
    log(f"preview: {dst} ({res['duration_s']} s, {res['bytes'] // 1024} KiB) · render {t1 - t0:.1f}s + pós {t2 - t1:.1f}s")
    return man

