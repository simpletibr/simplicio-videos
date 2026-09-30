"""Remote render backends driven 100% by CLI (no browser): Kaggle Notebooks (`kaggle` CLI) and Google Colab (`colab` CLI).

Both reuse the reproducible bundle (render.build_bundle) and the same headless script (engine/remote_render.py),
download final.mp4 and write the same render.manifest.json as the local backend (+ `usage` for credits).

Credentials (one-time, never in the repo):
  kaggle     ~/.kaggle/access_token or KAGGLE_API_TOKEN (kaggle.com/settings/api -> Generate New Token), or legacy
             ~/.kaggle/kaggle.json; KAGGLE_USERNAME (or the username in kaggle.json). Internet in kernels needs a
             phone-verified Kaggle account (the render downloads Node/Chrome/HyperFrames).
  colab-cli  `pip install google-colab-cli`; first `colab new` prints a Google sign-in URL, paste the code once
             (token cached in ~/.config/colab-cli/token.json). Uses the account's Colab quota/compute units.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Callable

from . import paths
from .contract import Contract
from .render import build_bundle, write_manifest

REMOTE_SCRIPT = paths.ENGINE_DIR / "remote_render.py"
Runner = Callable[[list[str]], subprocess.CompletedProcess]


def _default_runner(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True)


def _bin(env: str, name: str) -> str:
    b = os.environ.get(env) or shutil.which(name)
    if not b:
        raise SystemExit(f"`{name}` not found on PATH (install it or set {env}); see docs/decisoes/ADR-0003-fluxo-100-script.md")
    return b


def _call(run: Runner, cmd: list[str], log, what: str, ok_codes=(0,)) -> str:
    log("$ " + " ".join(cmd))
    p = run(cmd)
    out = (p.stdout or "") + (p.stderr or "")
    if p.returncode not in ok_codes:
        raise SystemExit(f"{what} failed (exit {p.returncode}): {' '.join(cmd)}\n{out[-3000:]}")
    return out


# ---------------------------------------------------------------- Kaggle
KAGGLE_DONE = re.compile(r"\bCOMPLETE\b", re.I)
KAGGLE_FAIL = re.compile(r"\b(ERROR|CANCEL_REQUESTED|CANCEL_ACKNOWLEDGED|CANCELLED|CANCELED|FAILED)\b", re.I)


def kaggle_username(explicit: str | None = None) -> str:
    """KAGGLE_USERNAME, else the `username` field of ~/.kaggle/kaggle.json (the key itself is never read here)."""
    if explicit or os.environ.get("KAGGLE_USERNAME"):
        return explicit or os.environ["KAGGLE_USERNAME"]
    cfg = Path(os.environ.get("KAGGLE_CONFIG_DIR", Path.home() / ".kaggle")) / "kaggle.json"
    if cfg.is_file():
        try:
            u = json.loads(cfg.read_text()).get("username")
            if u:
                return u
        except ValueError:
            pass
    raise SystemExit("kaggle: set KAGGLE_USERNAME=<seu usuário Kaggle> (and the token: KAGGLE_API_TOKEN or ~/.kaggle/access_token, "
                     "from kaggle.com/settings/api)")


def kaggle_slugs(inputs_sha: str) -> tuple[str, str]:
    """Deterministic ids: same compiled inputs -> same dataset/kernel (re-run = cache hit, no GPU spent)."""
    h = inputs_sha[:12]
    return f"sv-bundle-{h}", f"sv-render-{h}"


def kaggle_metadata(user: str, kernel_slug: str, dataset_slug: str, accelerator: str | None) -> dict:
    meta = {"id": f"{user}/{kernel_slug}", "title": kernel_slug, "code_file": "sv_render.py", "language": "python",
            "kernel_type": "script", "is_private": True, "enable_gpu": bool(accelerator), "enable_internet": True,
            "dataset_sources": [f"{user}/{dataset_slug}"], "competition_sources": [], "kernel_sources": [], "model_sources": []}
    if accelerator:
        meta["machine_shape"] = accelerator  # must be in the metadata on every push (CLI flag alone lands on the default GPU)
    return meta


def render_kaggle(c: Contract, out: Path | None = None, quality: str | None = None, accelerator: str | None = "NvidiaTeslaT4",
                  timeout_s: int = 3600, poll_s: int = 20, user: str | None = None, run: Runner | None = None,
                  sleep=time.sleep, gpu_encode: str = "auto", log=print) -> dict:
    run = run or _default_runner
    kg = _bin("SIMPLICIO_KAGGLE_BIN", "kaggle")
    user = kaggle_username(user)
    b = build_bundle(c, None, quality, gpu_encode=gpu_encode, log=log)
    ds_slug, k_slug = kaggle_slugs(b["inputs_sha256"])
    kref, dref = f"{user}/{k_slug}", f"{user}/{ds_slug}"
    base = c.dir / "build" / "kaggle"
    shutil.rmtree(base, ignore_errors=True)
    ds_dir, k_dir, dl = base / "dataset", base / "kernel", base / "output"
    for d in (ds_dir, k_dir, dl):
        d.mkdir(parents=True)
    t_start = time.time()

    # 1) bundle -> private dataset (skip when the same inputs were uploaded before)
    st = run([kg, "datasets", "status", dref])
    if st.returncode == 0 and "ready" in (st.stdout or "").lower():
        log(f"kaggle: dataset {dref} already uploaded (same inputs)")
    else:
        shutil.copyfile(b["bundle"], ds_dir / Path(b["bundle"]).name)
        (ds_dir / "dataset-metadata.json").write_text(json.dumps(
            {"title": ds_slug, "id": dref, "licenses": [{"name": "other"}]}, indent=1))
        _call(run, [kg, "datasets", "create", "-p", str(ds_dir), "-q"], log, "kaggle datasets create")
        for _ in range(max(1, timeout_s // max(poll_s, 1))):
            st = run([kg, "datasets", "status", dref])
            s = (st.stdout or "").lower()
            if "ready" in s:
                break
            if "error" in s or "fail" in s:
                raise SystemExit(f"kaggle: dataset {dref} failed: {st.stdout}{st.stderr}")
            sleep(poll_s)
        else:
            raise SystemExit(f"kaggle: dataset {dref} not ready after {timeout_s}s")

    # 2) kernel (script) with GPU + internet, bundle mounted from the dataset
    status = run([kg, "kernels", "status", kref])
    reuse = status.returncode == 0 and KAGGLE_DONE.search(status.stdout or "")
    if reuse:
        log(f"kaggle: kernel {kref} already COMPLETE for these inputs - downloading its output")
    else:
        shutil.copyfile(REMOTE_SCRIPT, k_dir / "sv_render.py")
        meta = kaggle_metadata(user, k_slug, ds_slug, accelerator)
        (k_dir / "kernel-metadata.json").write_text(json.dumps(meta, indent=1))
        push = [kg, "kernels", "push", "-p", str(k_dir), "-t", str(timeout_s)] + (["--accelerator", accelerator] if accelerator else [])
        _call(run, push, log, "kaggle kernels push")
        deadline = time.time() + timeout_s
        while True:
            sleep(poll_s)
            st = run([kg, "kernels", "status", kref])
            s = (st.stdout or "") + (st.stderr or "")
            log(f"kaggle: {s.strip().splitlines()[-1] if s.strip() else '?'}")
            if KAGGLE_DONE.search(s):
                break
            if KAGGLE_FAIL.search(s):
                logs = run([kg, "kernels", "logs", kref])
                raise SystemExit(f"kaggle: kernel {kref} failed:\n{s}\n--- log (tail) ---\n{(logs.stdout or '')[-3000:]}")
            if time.time() > deadline:
                raise SystemExit(f"kaggle: kernel {kref} still running after {timeout_s}s (see https://www.kaggle.com/code/{kref})")

    # 3) output -> MP4 + manifest
    _call(run, [kg, "kernels", "output", kref, "-p", str(dl), "-o"], log, "kaggle kernels output")
    mp4 = next(iter(sorted(dl.rglob("final.mp4"))), None)
    if not mp4:
        raise SystemExit(f"kaggle: final.mp4 not in the kernel output ({[p.name for p in dl.rglob('*')]})")
    remote = json.loads(next(iter(sorted(dl.rglob("timings.json")))).read_text()) if list(dl.rglob("timings.json")) else {}
    dst = (out or c.rel(c.data["saida"]["arquivo"])).resolve()
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(mp4, dst)
    rt = remote.get("timings_s", {})
    usage = {"backend": "kaggle", "accelerator": accelerator or "cpu", "gpu": remote.get("gpu"), "kernel": kref,
             "remote_total_s": rt.get("total_s"), "wall_s": round(time.time() - t_start, 1), "cache_hit": bool(reuse)}
    return write_manifest(c, dst, backend="kaggle", quality=b["quality"], gpu=bool(rt.get("gpu_encode")),
                          info={"inputs_sha256": b["inputs_sha256"], "files": b["files"]},
                          timings={"compile_build": b["compile_build_s"], "remote": rt}, tools=b["tools"], usage=usage, log=log)


# ---------------------------------------------------------------- Colab CLI
def render_colab_cli(c: Contract, out: Path | None = None, quality: str | None = None, gpu: str | None = "T4",
                     timeout_s: int = 3600, run: Runner | None = None, gpu_encode: str = "auto", log=print) -> dict:
    """Official Google Colab CLI (github.com/googlecolab/google-colab-cli): new -> upload -> exec -> download -> stop."""
    run = run or _default_runner
    cb = [_bin("SIMPLICIO_COLAB_BIN", "colab")]
    if os.environ.get("SIMPLICIO_COLAB_AUTH"):
        cb += ["--auth", os.environ["SIMPLICIO_COLAB_AUTH"]]
    b = build_bundle(c, None, quality, gpu_encode=gpu_encode, log=log)
    sess = f"sv-{b['inputs_sha256'][:10]}"
    rb, ro = "/content/sv/bundle.zip", "/content/sv/out"
    t_start = time.time()
    _call(run, cb + ["new", "-s", sess] + (["--gpu", gpu] if gpu else []), log, "colab new")
    try:
        _call(run, cb + ["upload", "-s", sess, b["bundle"], rb], log, "colab upload")
        res = _call(run, cb + ["exec", "-s", sess, "-f", str(REMOTE_SCRIPT), "--timeout", str(timeout_s),
                              "--env", f"SV_BUNDLE={rb}", "--env", f"SV_OUT={ro}"], log, "colab exec")
        if "SV_ERROR" in res:
            raise SystemExit("colab: remote render failed:\n" + res[-3000:])
        m = re.search(r"SV_RESULT (\{.*\})", res)
        remote = json.loads(m.group(1)) if m else {}
        dst = (out or c.rel(c.data["saida"]["arquivo"])).resolve()
        dst.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td) / "final.mp4"
            _call(run, cb + ["download", "-s", sess, f"{ro}/final.mp4", str(tmp)], log, "colab download")
            shutil.copyfile(tmp, dst)
    finally:
        p = run(cb + ["stop", "-s", sess])  # always release the VM (quota / compute units)
        log(f"colab stop -s {sess}: exit {p.returncode}")
    rt = remote.get("timings_s", {})
    usage = {"backend": "colab-cli", "accelerator": gpu or "cpu", "gpu": remote.get("gpu"), "session": sess,
             "remote_total_s": rt.get("total_s"), "wall_s": round(time.time() - t_start, 1), "cache_hit": False}
    return write_manifest(c, dst, backend="colab-cli", quality=b["quality"], gpu=bool(rt.get("gpu_encode")),
                          info={"inputs_sha256": b["inputs_sha256"], "files": b["files"]},
                          timings={"compile_build": b["compile_build_s"], "remote": rt}, tools=b["tools"], usage=usage, log=log)
