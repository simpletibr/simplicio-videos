#!/usr/bin/env python3
"""Headless render of a simplicio-video bundle on a remote GPU box (Kaggle kernel or Colab CLI session).

Self-contained (stdlib only). Same setup as colab/render.ipynb: Node 22, ffmpeg, the Chrome pinned by HyperFrames
(+ system libs), then `bash render_bundle.sh` (NVENC when available) -> final.mp4 + timings.json + render.log.

env:
  SV_BUNDLE      bundle .zip or extracted dir (default: search /content/sv, /kaggle/input, cwd for *.colab-bundle.zip/bundle.json)
  SV_OUT         output dir (default: /kaggle/working on Kaggle, else ./sv-out)
  SV_QUALITY     draft|looks|delivery (default: the bundle's quality)
  SV_SKIP_SETUP  1 = assume node/ffmpeg/chrome already present (local smoke test)
  SV_FFMPEG_URL / SV_FFMPEG_SHA256  pinned static ffmpeg (.tar.xz); default: bundle.json toolchain (SIMPLICIO_FFMPEG_URL at
                 bundle time). Same ffmpeg build as the local reference = same x264/aac/loudnorm bytes (ADR-0003).
  SV_GPU_ENCODE / SV_BROWSER_GPU / SV_WORKERS  passed to render_bundle.sh (see its header)
"""
import hashlib
import lzma
import tarfile
import urllib.request
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import zipfile

NODE = "v22.23.3"
HF = "hyperframes@0.8.97"
PB = "@puppeteer/browsers@3.2.3"
CHROME_FALLBACK = "152.0.7977.30"
APT_ENV = {**os.environ, "DEBIAN_FRONTEND": "noninteractive"}
T0 = time.time()
T = {}


def log(*a):
    print("[sv]", *a, flush=True)


def run(cmd, env=None):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True, env=env)


def sh(cmd, env=None):
    p = run(cmd, env)
    if p.returncode != 0:
        raise RuntimeError(f"failed (exit {p.returncode}): {cmd}\n--- stdout ---\n{p.stdout[-3000:]}\n--- stderr ---\n{p.stderr[-3000:]}")
    return p.stdout


def stream(cmd, cwd, env, logfile):
    """Run cmd streaming output (keeps remote kernels/CLI sessions alive) with a heartbeat every 20 s."""
    done = threading.Event()

    def beat():
        while not done.wait(20):
            print(f"[sv] ... still running ({time.time() - T0:.0f}s)", flush=True)
    threading.Thread(target=beat, daemon=True).start()
    with open(logfile, "a", encoding="utf8") as lf:
        p = subprocess.Popen(cmd, shell=True, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        out = []
        for line in p.stdout:
            print(line, end="", flush=True)
            lf.write(line)
            out.append(line)
        rc = p.wait()
    done.set()
    if rc != 0:
        raise RuntimeError(f"failed (exit {rc}): {cmd}\n{''.join(out)[-3000:]}")
    return "".join(out)


# ---------------- setup (same logic as colab/render.ipynb cell 2) ----------------
def _installed(pkg):
    return "install ok installed" in run(f"dpkg-query -W -f='${{Status}}' {pkg}").stdout


def _candidate(pkg):
    m = re.search(r"Candidate:\s*(\S+)", run(f"apt-cache policy {pkg}").stdout)
    return bool(m) and m.group(1) != "(none)"


_apt = {"updated": False}


def apt_install_any(groups, ubu_major):
    if not shutil.which("apt-get"):
        log("warning: no apt-get; skipping", groups)
        return
    if not _apt["updated"]:
        p = run("apt-get update", APT_ENV)
        if p.returncode != 0:
            log(f"warning: apt-get update exit {p.returncode}\n{p.stderr[-1000:]}")
        _apt["updated"] = True
    todo = []
    for alts in groups:
        alts = sorted(alts, key=lambda x: (ubu_major >= 24) != x.endswith("t64"))
        if any(_installed(x) for x in alts):
            continue
        pick = next((x for x in alts if _candidate(x)), None)
        if pick:
            todo.append(pick)
    if todo:
        p = run("apt-get install -y --no-install-recommends " + " ".join(todo), APT_ENV)
        if p.returncode != 0:
            for pkg in todo:
                run(f"apt-get install -y --no-install-recommends {pkg}", APT_ENV)


CHROME_DEPS = [["libasound2t64", "libasound2"], ["libatk-bridge2.0-0t64", "libatk-bridge2.0-0"], ["libatk1.0-0t64", "libatk1.0-0"],
               ["libatspi2.0-0t64", "libatspi2.0-0"], ["libcups2t64", "libcups2"], ["libglib2.0-0t64", "libglib2.0-0"],
               ["libgtk-3-0t64", "libgtk-3-0"], ["libgbm1"], ["libnss3"], ["libnspr4"], ["libpango-1.0-0"], ["libcairo2"],
               ["libxkbcommon0"], ["libxcomposite1"], ["libxdamage1"], ["libxrandr2"], ["libxfixes3"], ["libxext6"], ["libx11-6"],
               ["libxcb1"], ["libdbus-1-3"], ["libexpat1"], ["libudev1"], ["libvulkan1"], ["fonts-liberation"], ["ca-certificates"]]


def setup():
    t = time.time()
    osr = {}
    if os.path.exists("/etc/os-release"):
        osr = dict(ln.split("=", 1) for ln in open("/etc/os-release").read().splitlines() if "=" in ln)
    ubu_major = int((osr.get("VERSION_ID", "0").strip('"').split(".")[0]) or 0)
    log("os:", osr.get("PRETTY_NAME", "?").strip('"'), "| root:", os.geteuid() == 0)
    if not run("node --version").stdout.startswith("v22"):
        sh(f"curl -fsSL https://nodejs.org/dist/{NODE}/node-{NODE}-linux-x64.tar.xz | tar -xJ -C /usr/local --strip-components=1")
    log("node", sh("node --version").strip())
    if not shutil.which("ffmpeg"):
        apt_install_any([["ffmpeg"]], ubu_major)
    log(sh("ffmpeg -version").splitlines()[0])
    sh(f"npx --yes {HF} --version")
    ver = CHROME_FALLBACK
    for f in glob.glob(os.path.expanduser("~/.npm/_npx/*/node_modules/hyperframes/dist/*.js")):
        m = re.search(r'var CHROME_VERSION = "([0-9.]+)"', open(f, encoding="utf8", errors="ignore").read())
        if m:
            ver = m.group(1)
            break
    cache = os.path.expanduser("~/.cache/hyperframes/chrome")
    p = run(f"npx --yes {PB} install chrome-headless-shell@{ver} --path {cache} --install-deps --format '{{{{path}}}}'")
    if p.returncode == 0:
        chrome = p.stdout.strip().splitlines()[-1]
    else:
        log(f"warning: --install-deps failed (exit {p.returncode}); installing libs one by one")
        chrome = sh(f"npx --yes {PB} install chrome-headless-shell@{ver} --path {cache} --format '{{{{path}}}}'").strip().splitlines()[-1]

    def missing():
        return sorted(set(re.findall(r"^\s*(\S+) => not found", run(f"ldd '{chrome}'").stdout, re.M)))
    if missing():
        apt_install_any(CHROME_DEPS, ubu_major)
    if missing():
        raise RuntimeError(f"chrome still missing libs: {missing()}")
    os.environ["HYPERFRAMES_BROWSER_PATH"] = chrome
    log("chrome", ver, chrome)
    T["setup_s"] = round(time.time() - t, 1)


def pin_ffmpeg(url, sha256=None):
    """Download + verify + unpack a static ffmpeg build and put it first on PATH (HyperFrames + master.sh use it)."""
    t = time.time()
    dst = "/tmp/sv-ffmpeg"
    tarball = dst + ".tar.xz"
    if not os.path.exists(tarball):
        urllib.request.urlretrieve(url, tarball)
    got = hashlib.sha256(open(tarball, "rb").read()).hexdigest()
    if sha256 and got != sha256:
        raise RuntimeError(f"ffmpeg sha256 mismatch: {got} != {sha256} ({url})")
    if not os.path.isdir(dst):
        with lzma.open(tarball) as f:
            tarfile.open(fileobj=f).extractall(dst)
    ff = next(iter(sorted(glob.glob(dst + "/**/ffmpeg", recursive=True))), None)
    if not ff:
        raise RuntimeError(f"no ffmpeg binary inside {url}")
    os.chmod(ff, 0o755)
    d = os.path.dirname(ff)
    os.environ["PATH"] = d + os.pathsep + os.environ.get("PATH", "")
    os.environ["HYPERFRAMES_FFMPEG_PATH"] = ff
    if os.path.exists(os.path.join(d, "ffprobe")):
        os.chmod(os.path.join(d, "ffprobe"), 0o755)
        os.environ["HYPERFRAMES_FFPROBE_PATH"] = os.path.join(d, "ffprobe")
    log("ffmpeg pinned:", run(f"'{ff}' -version").stdout.splitlines()[0], "| sha256", got[:12])
    T["ffmpeg_pin_s"] = round(time.time() - t, 1)
    return got


# ---------------- bundle ----------------
def find_bundle():
    env = os.environ.get("SV_BUNDLE")
    if env:
        return env
    for pat in ["/content/sv/*.zip", "/kaggle/input/**/bundle.json", "/kaggle/input/**/*.zip", "./*.colab-bundle.zip", "./bundle.json"]:
        hits = sorted(glob.glob(pat, recursive=True))
        if hits:
            return os.path.dirname(hits[0]) if hits[0].endswith("bundle.json") else hits[0]
    raise FileNotFoundError("bundle not found (set SV_BUNDLE)")


def main():
    out = os.path.abspath(os.environ.get("SV_OUT") or ("/kaggle/working" if os.path.isdir("/kaggle/working") else "sv-out"))
    os.makedirs(out, exist_ok=True)
    gpu = run("nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader").stdout.strip()
    log("gpu:", gpu or "none (cpu)")
    if os.environ.get("SV_SKIP_SETUP") != "1":
        setup()
    src = find_bundle()
    work = os.path.join(out, "_bundle") if not os.path.isdir("/kaggle/working") else "/tmp/sv-bundle"
    shutil.rmtree(work, ignore_errors=True)
    if os.path.isdir(src):
        shutil.copytree(src, work)
    else:
        with zipfile.ZipFile(src) as z:
            z.extractall(work)
    for sh_file in glob.glob(os.path.join(work, "**/*.sh"), recursive=True):
        os.chmod(sh_file, 0o755)
    meta = json.load(open(os.path.join(work, "bundle.json"), encoding="utf8"))
    log("bundle:", src, "| inputs", meta.get("inputs_sha256", "")[:12], "| quality", meta.get("quality"))
    pin = {"url": os.environ.get("SV_FFMPEG_URL") or (meta.get("toolchain") or {}).get("ffmpeg_url"),
           "sha256": os.environ.get("SV_FFMPEG_SHA256") or (meta.get("toolchain") or {}).get("ffmpeg_sha256")}
    if pin["url"]:
        pin["sha256"] = pin_ffmpeg(pin["url"], pin["sha256"])
    q = os.environ.get("SV_QUALITY") or meta.get("quality") or "delivery"
    logfile = os.path.join(out, "render.log")
    res = stream(f"bash render_bundle.sh {q}", work, dict(os.environ), logfile)
    m = re.search(r"TIMINGS (\{.*\})", res)
    tim = json.loads(m.group(1)) if m else {}
    shutil.copyfile(os.path.join(work, "out", "final.mp4"), os.path.join(out, "final.mp4"))
    T.update(tim)
    T["total_s"] = round(time.time() - T0, 1)
    info = {"gpu": gpu or None, "inputs_sha256": meta.get("inputs_sha256"), "quality": q, "timings_s": T,
            "ffmpeg_pin": pin if pin["url"] else None,
            "host": "kaggle" if os.path.isdir("/kaggle/working") else ("colab" if os.path.isdir("/content") else "other")}
    with open(os.path.join(out, "timings.json"), "w", encoding="utf8") as f:
        json.dump(info, f, indent=1)
    if os.path.isdir("/kaggle/working"):
        shutil.rmtree(work, ignore_errors=True)  # only final.mp4/timings.json/render.log become kernel output
    print("SV_RESULT " + json.dumps(info), flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # noqa: BLE001 - surface the real error in the remote log
        print(f"SV_ERROR {e}", flush=True)
        sys.exit(1)
