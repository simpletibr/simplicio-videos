"""Character swap: replace the character of an existing video with a reference avatar, provider-agnostic.

One orchestration for every provider (the adapters live in `swap_providers/`): validate the inputs, `ffprobe`, cut the
video in chunks no longer than the provider accepts, ask for the authorization flag, estimate the cost, spend only with
`--yes` and under `--max-usd`, submit, poll with timeout and backoff, download, remount the original audio when the
provider does not keep it, normalize fps and duration, join the chunks and write `swap.manifest.json` next to the output.

Rules that do not bend:
- The API key comes only from the provider's environment variable. Never an argument, file, log or manifest.
- Without `--autorizo` the command refuses. Without `--yes` it only estimates (dry run) and never touches the network.
- The default prompt keeps every other person, the scenery, the camera and the audio untouched.
- Spending happens only in the terminal: the MCP tool `video.swap` offers `providers` and `estimate` and nothing else.
"""
from __future__ import annotations

import argparse
import asyncio
import contextlib
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from . import swap_providers
from .aio import athread, clamp, positive_int, run_sync
from .swap_providers.base import FX, UNVERIFIED, Estimate, Job, ProviderError, SwapError, redact

__all__ = ["Job", "SwapError", "SwapTimeout", "run_swap", "plan_chunks", "estimate_report", "providers_report"]

MANIFEST_NAME = "swap.manifest.json"
MANIFEST_SCHEMA = "simplicio.swap-manifest/v1"
DEFAULT_MAX_USD = 2.0
POLL_MAX_S = 30.0
SUBMIT_DRAIN_S = 10.0  # how long a cancelled chunk waits for its in-flight submit, so a charged handle is not lost
DEFAULT_TIMEOUT_S = 900.0
DEFAULT_POLL_S = 5.0
DEFAULT_CONCURRENCY = 3  # chunks of one video in flight at once (--concurrency); the adapter can lower it
MAX_TRIES = 3
IMAGE_EXT = (".png", ".jpg", ".jpeg", ".webp")
AUTORIZACAO_TEXTO = (
    "Declaro que tenho direito de uso sobre o vídeo e sobre as imagens de referência enviados, inclusive sobre a imagem "
    "e a voz das pessoas que aparecem neles, e que a troca de personagem não será usada para enganar, difamar ou imitar "
    "alguém sem o seu consentimento."
)
DEFAULT_PROMPT = (
    "Replace only the main character (the target person) of the video with the person shown in <IMAGE_REF_0>. "
    "Keep every other person exactly as they are: do not change, remove, add or restyle anyone else. "
    "Keep the scenery, the camera movement, the framing, the lighting, the timing and the original audio unchanged. "
    "Match the movement, expression and lip movement of the original character."
)

_sleep = time.sleep
_now = time.monotonic


class SwapTimeout(SwapError):
    pass


class SpendCapExceeded(SwapError):
    code = 2


# ---------------------------------------------------------------------------------------------------------- helpers

def brl(usd: float) -> float:
    return usd * FX["brl_per_usd"]


def _log(msg: str) -> None:
    print(scrub(msg), file=sys.stderr)


def _secrets() -> list[str]:
    vals = []
    for cls in swap_providers.REGISTRY.values():
        v = os.environ.get(cls.env_var, "").strip() if cls.env_var else ""
        if len(v) >= 6:
            vals.append(v)
    return vals


def scrub(text: str) -> str:
    for v in _secrets():
        text = text.replace(v, "***")
    return redact(text)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _bin(name: str) -> str:
    d = os.environ.get("SIMPLICIO_FFMPEG_DIR")
    if d and (Path(d) / name).exists():
        return str(Path(d) / name)
    return name


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True)
    except FileNotFoundError:
        raise SwapError(f"{Path(cmd[0]).name} não encontrado: instale o ffmpeg (ffmpeg e ffprobe no PATH)") from None
    if r.returncode != 0:
        raise SwapError(f"{Path(cmd[0]).name} falhou ({r.returncode}): {(r.stderr or '')[-600:].strip()}")
    return r


def probe(path: Path) -> dict:
    r = _run([_bin("ffprobe"), "-v", "error", "-show_entries",
              "stream=codec_type,avg_frame_rate,r_frame_rate,width,height:format=duration", "-of", "json", str(path)])
    data = json.loads(r.stdout or "{}")
    streams = data.get("streams") or []
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    if not video:
        raise SwapError(f"sem trilha de vídeo: {path}")

    def rate(txt):
        try:
            a, _, b = str(txt).partition("/")
            return float(a) / float(b or 1)
        except (ValueError, ZeroDivisionError):
            return 0.0

    fps = rate(video.get("avg_frame_rate")) or rate(video.get("r_frame_rate")) or 24.0
    try:
        duration = float((data.get("format") or {}).get("duration"))
    except (TypeError, ValueError):
        raise SwapError(f"não consegui ler a duração de {path}") from None
    return {"duration_s": duration, "fps": fps, "width": int(video.get("width") or 0), "height": int(video.get("height") or 0),
            "has_audio": any(s.get("codec_type") == "audio" for s in streams)}


def plan_chunks(total_s: float, max_s: float, min_s: float = 0.0) -> list[tuple[float, float]]:
    """Equal chunks of at most max_s that cover the video; fewer chunks when equal ones would be shorter than min_s."""
    n = max(1, math.ceil(total_s / max_s - 1e-9))
    while n > 1 and min_s and total_s / n < min_s:
        n -= 1
    length = total_s / n
    return [(total_s * i / n, length) for i in range(n)]


def _com_tentativas(fn, tentativas: list, max_tries: int = MAX_TRIES, retry_network: bool = True):
    """Call fn, retrying only transient provider errors with exponential backoff. tentativas[0] counts the calls.
    With retry_network=False (submit) a network failure is never retried: the provider may have accepted and charged the
    request without answering, and no provider supports an idempotency key here, so a retry could charge twice."""
    for i in range(max_tries):
        tentativas[0] += 1
        try:
            return fn()
        except ProviderError as e:
            if e.network and not retry_network:
                e.retryable, e.possibly_charged = False, True
                e.args = (f"{e} A requisição pode ter sido aceita e cobrada sem resposta; o envio não foi repetido para não "
                          "cobrar em dobro. Confira o painel do provedor antes de rodar de novo.",)
                raise
            if not e.retryable or i == max_tries - 1:
                raise
            _sleep(min(2.0 ** (i + 1), 30.0))
    raise AssertionError("unreachable")


def write_manifest(path: Path, data: dict) -> None:
    text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    for v in _secrets():
        if v in text:
            raise SwapError("segredo (chave de API) encontrado no manifesto: não gravado")
    text = redact(text)  # a key-shaped string (e.g. pasted in --prompt) is hidden even when it is not in the environment
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf8")


def build_prompt(extra: str = "") -> str:
    return DEFAULT_PROMPT + (f" Additional instruction: {extra.strip()}" if extra and extra.strip() else "")


# -------------------------------------------------------------------------------------------------------- planning

@dataclass
class Plan:
    adapter: object
    video: Path
    refs: list
    info: dict
    job: Job
    chunks: list
    estimate: Estimate


def prepare(provider: str, video: str, refs: list[str], resolution: str = "720p") -> Plan:
    adapter = swap_providers.get(provider)
    caps = adapter.capabilities
    vpath = Path(video)
    if not vpath.is_file():
        raise SwapError(f"vídeo não encontrado: {video}")
    if not refs:
        raise SwapError("falta a imagem do avatar: passe --ref <imagem> (pode repetir)")
    if len(refs) > caps.max_ref_images:
        raise SwapError(f"{provider} aceita no máximo {caps.max_ref_images} imagens de referência (recebi {len(refs)})")
    rpaths = []
    for r in refs:
        p = Path(r)
        if not p.is_file():
            raise SwapError(f"imagem de referência não encontrada: {r}")
        if p.suffix.lower() not in IMAGE_EXT:
            raise SwapError(f"a referência precisa ser uma imagem ({', '.join(IMAGE_EXT)}): {r}")
        rpaths.append(p)
    if resolution not in caps.resolutions:
        raise SwapError(f"{provider}: resolução {resolution} não suportada (use: {', '.join(caps.resolutions)})")
    info = probe(vpath)
    if info["duration_s"] < caps.min_input_s:
        raise SwapError(f"vídeo curto demais para {provider}: {info['duration_s']:.1f} s, mínimo {caps.min_input_s:g} s")
    chunks = plan_chunks(info["duration_s"], caps.max_input_s, caps.min_input_s)
    job = Job(video=vpath, refs=rpaths, prompt="", resolution=resolution, duration_s=info["duration_s"], fps=info["fps"],
              width=info["width"], height=info["height"], has_audio=info["has_audio"])
    return Plan(adapter, vpath, rpaths, info, job, chunks, adapter.estimate(job))


def estimate_report(provider: str, video: str, refs: list[str], resolution: str = "720p", plan: Plan | None = None) -> dict:
    p = plan or prepare(provider, video, refs, resolution)
    return {"provider": provider, "model": p.adapter.model, "verified": p.adapter.verified, "resolution": resolution,
            "duration_s": round(p.info["duration_s"], 3), "fps": round(p.info["fps"], 3), "chunks": len(p.chunks),
            "chunk_plan": [{"start_s": round(s, 3), "length_s": round(l, 3)} for s, l in p.chunks],
            "estimate": p.estimate.as_dict(), "fx": dict(FX)}


def providers_report() -> dict:
    return {"providers": [swap_providers.REGISTRY[n]().describe() for n in swap_providers.names()], "fx": dict(FX),
            "default_max_usd": DEFAULT_MAX_USD}


def status_summary() -> list[dict]:
    """For `status`: which providers have a key set in the environment (never the value)."""
    out = []
    for n in swap_providers.names():
        a = swap_providers.REGISTRY[n]()
        out.append({"name": n, "env_var": a.env_var or None, "configured": (not a.env_var) or bool(os.environ.get(a.env_var)),
                    "verified": a.verified})
    return out


# ------------------------------------------------------------------------------------------------------ execution

def _normalize(raw: Path, dst: Path, info: dict, length: float, keep_audio: bool) -> None:
    w, h = (info["width"] // 2 * 2) or 640, (info["height"] // 2 * 2) or 360
    vf = (f"fps={info['fps']:.3f},tpad=stop_mode=clone:stop_duration={length:.3f},"
          f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1")
    audio = ["-c:a", "aac", "-ar", "48000", "-ac", "2"] if keep_audio else ["-an"]
    _run([_bin("ffmpeg"), "-y", "-v", "error", "-i", str(raw), "-t", f"{length:.3f}", "-vf", vf,
          "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", *audio, str(dst)])


def _concat_escape(name: str) -> str:
    """Escape a name for the ffmpeg concat list (inside single quotes a `'` is written as `'\\''`)."""
    return name.replace("'", "'\\''")


def _preserve_paid(work: Path, out: Path, recs: list[dict], manifest: dict) -> str | None:
    """On failure, keep the chunks already generated (and paid) in a recovery folder next to the output."""
    raws = sorted(work.glob("raw-*.mp4"))
    if not raws:
        return None
    dest = out.parent / f"{out.stem}.swap-recovery"
    if dest.exists():
        dest = out.parent / f"{out.stem}.swap-recovery-{os.getpid()}"
    shutil.move(str(work), str(dest))
    for f in dest.iterdir():
        if not f.name.startswith("raw-"):
            f.unlink(missing_ok=True)
    for r in recs:
        if r.get("raw_path"):
            r["raw_path"] = str(dest / Path(r["raw_path"]).name)
    manifest["recovery_dir"] = str(dest)
    return str(dest)


def _save_partial(path: Path, manifest: dict) -> None:
    """Best effort: a partial manifest must never hide the error that is being handled."""
    try:
        write_manifest(path, manifest)
    except (SwapError, OSError):
        pass


async def _asleep(seconds: float) -> None:
    """Sleep without blocking the loop. Tests replace `_sleep` with a fake clock: then honour it and only yield."""
    if _sleep is time.sleep:
        await asyncio.sleep(seconds)
    else:
        _sleep(seconds)
        await asyncio.sleep(0)


async def _arun(cmd: list[str]) -> None:
    """`_run` for the event loop: the subprocess dies with the task when it is cancelled (Ctrl+C, another chunk failed)."""
    try:
        proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    except FileNotFoundError:
        raise SwapError(f"{Path(cmd[0]).name} não encontrado: instale o ffmpeg (ffmpeg e ffprobe no PATH)") from None
    try:
        _, err = await proc.communicate()
    except BaseException:
        with contextlib.suppress(ProcessLookupError):
            proc.kill()
        await asyncio.shield(proc.wait())
        raise
    if proc.returncode != 0:
        raise SwapError(f"{Path(cmd[0]).name} falhou ({proc.returncode}): {(err or b'').decode('utf8', 'replace')[-600:].strip()}")


async def _acom_tentativas(fn, counter: list, max_tries: int = MAX_TRIES, retry_network: bool = True):
    """`_com_tentativas` for the event loop: the blocking call runs in a thread, the backoff does not block the others.
    Same rule for submit: a network failure is never retried (the provider may have accepted and charged the request)."""
    for i in range(max_tries):
        counter[0] += 1
        try:
            return await athread(fn)
        except ProviderError as e:
            if e.network and not retry_network:
                e.retryable, e.possibly_charged = False, True
                e.args = (f"{e} A requisição pode ter sido aceita e cobrada sem resposta; o envio não foi repetido para não "
                          "cobrar em dobro. Confira o painel do provedor antes de rodar de novo.",)
                raise
            if not e.retryable or i == max_tries - 1:
                raise
            await _asleep(min(2.0 ** (i + 1), 30.0))
    raise AssertionError("unreachable")


async def _apoll_until_done(adapter, handle: dict, rec: dict, timeout: float, interval: float) -> None:
    """Polling with exponential backoff for ONE chunk; every chunk runs its own loop, so the waits overlap."""
    t0 = _now()
    wait = interval
    errors = 0
    running_at = None
    while True:
        try:
            st = await athread(adapter.poll, handle)
            errors = 0
        except ProviderError as e:
            errors += 1
            if not e.retryable or errors > MAX_TRIES:
                raise
            st = None
        if st is not None:
            if st.state in ("running", "done") and running_at is None:
                running_at = _now()
                rec["latency"]["queue_s"] = round(running_at - t0, 3)
            if st.state == "done":
                rec["latency"]["generation_s"] = round(_now() - running_at, 3)
                return
            if st.state == "failed":
                raise ProviderError(f"{adapter.name}: a geração falhou: {st.error or 'sem detalhe'}", retryable=False)
        if _now() - t0 > timeout:
            raise SwapTimeout(f"timeout de {timeout:g} s esperando o provedor ({adapter.name}); "
                              f"o manifesto guarda o handle para conferir depois")
        await _asleep(wait)
        wait = min(wait * 1.5, POLL_MAX_S)


async def _submit_protected(adapter, job, counter: list, rec: dict, save):
    """Submit shielded from cancellation: the provider may accept (and charge) a request whose task was cancelled because
    another chunk failed or the user pressed Ctrl+C. On cancel, wait a bounded time for the in-flight submit and record the
    handle it returns; if it does not finish, the chunk is marked possibly charged."""
    sub = asyncio.ensure_future(_acom_tentativas(lambda: adapter.submit(job), counter, retry_network=False))
    try:
        return await asyncio.shield(sub)
    except asyncio.CancelledError:
        if sub.done() and sub.cancelled():
            raise
        finished = sub.done()
        if not finished:
            try:
                done, _ = await asyncio.wait({sub}, timeout=SUBMIT_DRAIN_S)
                finished = bool(done)
            except asyncio.CancelledError:  # cancelled again while draining: give up waiting
                finished = sub.done()
        if finished and not sub.cancelled() and sub.exception() is None:
            rec["handle"], rec["state"] = sub.result(), "submitted"
            save()
        elif finished and not sub.cancelled():
            exc = sub.exception()
            rec["possibly_charged"] = bool(getattr(exc, "possibly_charged", False))
        else:
            rec["possibly_charged"] = True
            rec["state"] = "cancelled_during_submit"
            sub.add_done_callback(lambda f: f.cancelled() or f.exception())  # consume a late error
            sub.cancel()
            save()
        raise


async def _chunk(i: int, p: "Plan", prompt: str, work: Path, rec: dict, counters: dict, gate: dict, timeout: float,
                 poll_interval: float, save) -> Path:
    """One chunk, from the cut to the downloaded bytes. The semaphore bounds how many chunks are in flight; the cut lock
    keeps ffmpeg serial (CPU) while the waits of the other chunks overlap with it."""
    adapter, info = p.adapter, p.info
    start, length = p.chunks[i]
    n = len(p.chunks)
    try:
        async with gate["sem"]:
            t_chunk = _now()
            if n == 1:
                clip = p.video
            else:
                clip = work / f"chunk-{i:02d}.mp4"
                async with gate["cut"]:
                    await _arun([_bin("ffmpeg"), "-y", "-v", "error", "-ss", f"{start:.3f}", "-i", str(p.video), "-t",
                                 f"{length:.3f}", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p",
                                 "-c:a", "aac", str(clip)])
            job = Job(video=clip, refs=p.refs, prompt=prompt, resolution=p.job.resolution, duration_s=length, fps=info["fps"],
                      width=info["width"], height=info["height"], has_audio=info["has_audio"], index=i)
            _log(f"swap: pedaço {i + 1}/{n} ({length:.1f} s): enviando para {adapter.name}")
            t = _now()
            try:
                handle = await _submit_protected(adapter, job, counters["submit"][i], rec, save)
            except ProviderError as e:
                rec["possibly_charged"] = e.possibly_charged
                raise
            finally:
                rec["attempts"] = counters["submit"][i][0]
            rec["latency"]["upload_s"] = round(_now() - t, 3)
            rec["handle"], rec["state"] = handle, "submitted"
            save()  # the paid handle reaches the disk before the long wait
            await _apoll_until_done(adapter, handle, rec, timeout, poll_interval)
            t = _now()
            data = await _acom_tentativas(lambda: adapter.fetch(handle), counters["fetch"][i])
            rec["latency"]["download_s"] = round(_now() - t, 3)
            raw = work / f"raw-{i:02d}.mp4"
            raw.write_bytes(data)
            rec["raw_path"] = str(raw)
            rec["state"] = "done"
            try:
                rec["measured_usd"] = adapter.measured_usd(handle)
            except Exception:  # noqa: BLE001 (a usage field the adapter cannot read must not fail a paid job)
                rec["measured_usd"] = None
            rec["latency"]["total_s"] = round(_now() - t_chunk, 3)
            return raw
    except asyncio.CancelledError:
        if rec["state"] not in ("done", "cancelled_during_submit"):
            rec["state"] = "cancelled"
        raise
    except SwapError as e:
        rec["state"] = "timeout" if isinstance(e, SwapTimeout) else "failed"
        e.args = (f"pedaço {i + 1}/{n}: {e}",)  # which chunk, in the message and in the manifest
        rec["error"] = scrub(str(e))
        raise
    except Exception as e:  # noqa: BLE001 (unexpected: the chunk is failed, the handle stays in the manifest)
        rec["state"] = "failed"
        rec["error"] = scrub(f"pedaço {i + 1}/{n}: {type(e).__name__}: {e}")
        raise


async def _run_chunks(p: "Plan", prompt: str, work: Path, recs: list[dict], counters: dict, effective: int, timeout: float,
                      poll_interval: float, save) -> list[Path]:
    """Submit every chunk (at most `effective` in flight), poll them concurrently and return the raw files in chunk order.
    The first failure cancels the others and is the error reported (the lowest chunk index when several fail together)."""
    gate = {"sem": asyncio.Semaphore(effective), "cut": asyncio.Lock()}
    tasks = [asyncio.create_task(_chunk(i, p, prompt, work, recs[i], counters, gate, timeout, poll_interval, save),
                                 name=f"swap-chunk-{i}") for i in range(len(p.chunks))]
    try:
        await asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION)
        failed = [t for t in tasks if t.done() and not t.cancelled() and t.exception() is not None]
        if failed:
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            raise failed[0].exception()  # tasks are in chunk order: the lowest index first
        return [t.result() for t in tasks]
    except asyncio.CancelledError:
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise


def execute(p: Plan, out: Path, *, extra_prompt: str = "", timeout: float = DEFAULT_TIMEOUT_S,
            poll_interval: float = DEFAULT_POLL_S, max_usd: float = DEFAULT_MAX_USD,
            concurrency: int | None = None) -> dict:
    adapter, info = p.adapter, p.info
    manifest_path = out.parent / MANIFEST_NAME
    prompt = build_prompt(extra_prompt)
    caps = adapter.capabilities
    effective = clamp(concurrency, DEFAULT_CONCURRENCY, min(caps.max_concurrency, len(p.chunks)))
    work = out.parent / f".swap-work-{os.getpid()}"
    work.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema": MANIFEST_SCHEMA, "state": "running", "provider": adapter.name, "model": adapter.model,
        "resolution": p.job.resolution, "adapter_version": adapter.version, "adapter_verified": adapter.verified,
        "prompt": prompt, "max_usd": max_usd,
        "concurrency": {"requested": DEFAULT_CONCURRENCY if concurrency is None else int(concurrency),
                        "effective": effective, "adapter_max": caps.max_concurrency},
        "authorization": {"flag": "--autorizo", "text": AUTORIZACAO_TEXTO,
                          "confirmed_at": datetime.now(timezone.utc).isoformat(timespec="seconds")},
        "inputs": {"video": {"path": str(p.video), "sha256": sha256_file(p.video), "duration_s": round(info["duration_s"], 3),
                             "fps": round(info["fps"], 3), "width": info["width"], "height": info["height"],
                             "has_audio": info["has_audio"]},
                   "refs": [{"path": str(r), "sha256": sha256_file(r)} for r in p.refs]},
        "estimate": p.estimate.as_dict(), "price_confidence": p.estimate.confidence, "measured_usd": None,
        "attempts": 0, "fetch_attempts": 0, "timing": None, "chunks": [], "output": None, "error": None,
    }
    recs = [{"index": i, "start_s": round(start, 3), "length_s": round(length, 3), "state": "pending", "handle": None,
             "attempts": 0, "error": None, "measured_usd": None, "possibly_charged": False,
             "latency": {"upload_s": None, "queue_s": None, "generation_s": None, "download_s": None, "total_s": None}}
            for i, (start, length) in enumerate(p.chunks)]
    manifest["chunks"] = recs
    counters = {"submit": [[0] for _ in recs], "fetch": [[0] for _ in recs]}  # calls per chunk, retries included

    def tally() -> None:
        manifest["attempts"] = sum(c[0] for c in counters["submit"])
        manifest["fetch_attempts"] = sum(c[0] for c in counters["fetch"])

    def save() -> None:
        tally()
        _save_partial(manifest_path, manifest)

    try:
        t_wall = _now()
        raws = run_sync(_run_chunks(p, prompt, work, recs, counters, effective, timeout, poll_interval, save))
        wall = _now() - t_wall
        tally()
        sum_chunks = sum(r["latency"]["total_s"] or 0.0 for r in recs)
        manifest["timing"] = {"wall_s": round(wall, 3), "sum_chunks_s": round(sum_chunks, 3),
                              "speedup": round(sum_chunks / wall, 3) if wall > 0 else None,
                              "saved_s": round(sum_chunks - wall, 3)}
        known = [r["measured_usd"] for r in recs if r["measured_usd"] is not None]
        manifest["measured_usd"] = round(sum(known), 6) if known else None
        keep = adapter.capabilities.keeps_audio and all(probe(r)["has_audio"] for r in raws)
        norm = []
        for i, raw in enumerate(raws):
            dst = work / f"norm-{i:02d}.mp4"
            _normalize(raw, dst, info, p.chunks[i][1], keep)
            norm.append(dst)
            recs[i]["sha256"] = sha256_file(raw)
        joined = norm[0]
        if len(norm) > 1:
            lst = work / "list.txt"
            lst.write_text("".join(f"file '{_concat_escape(n.name)}'\n" for n in norm), encoding="utf8")  # relative: ffmpeg resolves it next to list.txt
            joined = work / "joined.mp4"
            _run([_bin("ffmpeg"), "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(joined)])
        out.parent.mkdir(parents=True, exist_ok=True)
        if not keep and info["has_audio"]:
            _run([_bin("ffmpeg"), "-y", "-v", "error", "-i", str(joined), "-i", str(p.video), "-map", "0:v:0", "-map", "1:a:0",
                  "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", str(out)])
        else:
            shutil.copyfile(joined, out)
        res = probe(out)
        manifest["output"] = {"path": str(out), "sha256": sha256_file(out), "duration_s": round(res["duration_s"], 3),
                              "fps": round(res["fps"], 3), "audio": "original remontado" if not keep and info["has_audio"]
                              else ("do provedor" if keep else "sem áudio")}
        manifest["state"] = "done"
        write_manifest(manifest_path, manifest)
        return manifest
    except BaseException as e:  # noqa: BLE001 (Ctrl+C and unexpected errors must keep the paid handles too)
        tally()
        kept = _preserve_paid(work, out, recs, manifest)
        if kept:
            e.args = (f"{e} Os pedaços já gerados e pagos ficaram em {kept} (nada foi apagado).",)
        interrupted = isinstance(e, (KeyboardInterrupt, asyncio.CancelledError))
        if interrupted:
            manifest["state"] = "interrupted"
        elif isinstance(e, SwapTimeout):
            manifest["state"] = "timeout"
        else:
            manifest["state"] = "failed"
        manifest["error"] = scrub(str(e) or type(e).__name__) if isinstance(e, SwapError) else scrub(f"{type(e).__name__}: {e}")
        for r in recs:
            if r["state"] == "pending" or (interrupted and r["state"] not in ("done", "cancelled_during_submit")):
                r["state"] = "interrupted" if interrupted else "cancelled"  # never started / stopped before the end
            if r["state"] == "interrupted":
                r["error"] = manifest["error"]
        _save_partial(manifest_path, manifest)
        raise
    finally:
        shutil.rmtree(work, ignore_errors=True)


# ----------------------------------------------------------------------------------------------------------- CLI

def _money(usd: float) -> str:
    return f"US$ {usd:.2f} (R$ {brl(usd):.2f})"


def _estimate_text(p: Plan, max_usd: float | None = None) -> str:
    e = p.estimate
    lines = [f"swap: {p.adapter.name} ({e.model}, {e.resolution})" + (f"  [{UNVERIFIED}]" if not p.adapter.verified else ""),
             f"  vídeo: {p.info['duration_s']:.1f} s, {p.info['fps']:.1f} fps, {p.info['width']}x{p.info['height']}, "
             f"{len(p.chunks)} pedaço(s) de até {p.adapter.capabilities.max_input_s:g} s",
             f"  custo previsto: {_money(e.usd)}  confiança {e.confidence}, lido em {e.read_on}",
             f"  cálculo: {e.detail}"]
    if e.note:
        lines.append(f"  nota: {e.note}")
    lines.append(f"  fonte do preço: {e.source_url}")
    lines.append(f"  câmbio de referência: 1 US$ = R$ {FX['brl_per_usd']} ({FX['source']})")
    if max_usd is not None:
        lines.append(f"  teto: US$ {max_usd:.2f} (--max-usd)")
    return "\n".join(lines)


def _providers_text(rep: dict) -> str:
    lines = [f"Provedores de troca de personagem (câmbio 1 US$ = R$ {rep['fx']['brl_per_usd']}, {rep['fx']['source']})", ""]
    for p in rep["providers"]:
        c = p["capabilities"]
        flag = "verificado" if p["verified"] else UNVERIFIED
        lines.append(f"{p['name']}  [{flag}]  modelo {p['model']}  chave: {p['env_var'] or '-'}")
        lines.append(f"  resolução {', '.join(c['resolutions'])}; entrada {c['min_input_s']:g} a {c['max_input_s']:g} s; "
                     f"saída até {c['max_output_s']:g} s; {c['max_ref_images']} imagem(ns); "
                     f"áudio {'preservado' if c['keeps_audio'] else 'remontado'}; cobra entrada: {'sim' if c['bills_input'] else 'não'}")
        for r in p["prices"]:
            extra = f" + US$ {r['usd_per_s_in']}/s de entrada" if r["usd_per_s_in"] else ""
            lines.append(f"  {r['resolution']}: US$ {r['usd_per_s_out']}/s (R$ {r['brl_per_s_out']}/s){extra}  "
                         f"confiança {r['confidence']}, lido em {r['read_on']}  {r['source_url']}")
            if r["note"]:
                lines.append(f"    {r['note']}")
        if p["notes"]:
            lines.append(f"  {p['notes']}")
        lines.append("")
    lines.append("Só o gemini foi conferido contra a documentação real. Os marcados UNVERIFIED exigem --aceito-unverified para gastar.")
    return "\n".join(lines)


HELP_DESC = (
    "Troca o personagem de um vídeo existente por um avatar de referência. Agnóstico de fornecedor: cada provedor entra por\n"
    "um adaptador (gemini, fal, wavespeed, kie, alibaba e fake para testes). Os adaptadores fal, wavespeed, kie e alibaba\n"
    "estão UNVERIFIED: escritos da documentação pública, sem conferência na API real; `run` só gasta neles com\n"
    "--aceito-unverified.\n\n"
    "Subcomandos:\n"
    "  providers             lista adaptadores, capacidades, preço (US$ e R$) e confiança\n"
    "  estimate              custo previsto, sem rede (precisa de ffprobe)\n"
    "  run                   executa; exige --autorizo; sem --yes só estima (dry-run); --max-usd é o teto de gasto\n"
    "  status <manifesto>    lê o swap.manifest.json de uma execução\n\n"
    "Os pedaços do vídeo vão em paralelo (asyncio sobre o cliente HTTP da biblioteca padrão): --concurrency N (padrão 3, o\n"
    "adaptador pode limitar a menos; 1 = serial). A emenda e o manifesto seguem a ordem do vídeo; se um pedaço falhar, os outros\n"
    "são cancelados e o erro diz qual foi; Ctrl+C cancela limpo. O ffmpeg (corte, normalização, emenda) segue serial.\n\n"
    "A chave de API entra só pela variável de ambiente do provedor (GEMINI_API_KEY, FAL_KEY, WAVESPEED_API_KEY, KIE_API_KEY,\n"
    "DASHSCOPE_API_KEY), nunca por argumento. Use só vídeo e imagens sobre os quais você tem direito. O prompt padrão mantém\n"
    "todas as outras pessoas, o cenário, a câmera e o áudio."
)
HELP_EPILOG = (
    "exemplos:\n"
    "  simplicio-video swap providers\n"
    "  simplicio-video swap estimate --provider gemini --video in.mp4 --ref avatar.png\n"
    "  simplicio-video swap run --provider gemini --video in.mp4 --ref avatar.png --out out/swap.mp4 --autorizo\n"
    "  simplicio-video swap run --provider gemini --video in.mp4 --ref avatar.png --out out/swap.mp4 --autorizo --yes --max-usd 2\n"
    "  simplicio-video swap status out/swap.manifest.json --json"
)


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="simplicio-video swap", description=HELP_DESC, epilog=HELP_EPILOG,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("providers", help="lista adaptadores, capacidades, preço e confiança")
    p.add_argument("--json", action="store_true")

    def common(p):
        p.add_argument("--provider", default="gemini", help="adaptador (padrão: gemini)")
        p.add_argument("--video", required=False, help="vídeo de entrada")
        p.add_argument("--ref", action="append", default=[], help="imagem do avatar (repita para mais de uma)")
        p.add_argument("--resolution", default="720p")
        p.add_argument("--json", action="store_true")

    p = sub.add_parser("estimate", help="custo previsto, sem rede")
    common(p)
    p = sub.add_parser("run", help="executa a troca (--autorizo; --yes para gastar)")
    common(p)
    p.add_argument("--out", required=True, help="MP4 de saída; o swap.manifest.json fica ao lado")
    p.add_argument("--autorizo", action="store_true", help="confirma que você tem direito sobre as imagens e o vídeo (obrigatório)")
    p.add_argument("--yes", action="store_true", help="autoriza o gasto; sem ele só estima (dry-run)")
    p.add_argument("--max-usd", type=float, default=DEFAULT_MAX_USD, help=f"teto de gasto em US$ (padrão {DEFAULT_MAX_USD})")
    p.add_argument("--prompt", default="", help="instrução extra, somada ao prompt padrão que protege as outras pessoas")
    p.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_S, help="segundos de espera por pedaço")
    p.add_argument("--poll-interval", type=float, default=DEFAULT_POLL_S, help="segundos entre consultas (cresce até 30)")
    p.add_argument("--concurrency", type=positive_int, default=DEFAULT_CONCURRENCY, metavar="N",
                   help=f"pedaços em voo ao mesmo tempo (padrão {DEFAULT_CONCURRENCY}; o adaptador pode limitar a menos; 1 = serial)")
    p.add_argument("--aceito-unverified", action="store_true", help="aceita gastar em adaptador UNVERIFIED")
    p.add_argument("--force", action="store_true", help="sobrescreve a saída se já existir")
    p = sub.add_parser("status", help="lê o swap.manifest.json")
    p.add_argument("manifest")
    p.add_argument("--json", action="store_true")
    return ap


def _emit(obj, as_json: bool, text: str, indent: int | None = 2) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=indent) if as_json else text)


def _cmd_status(a) -> int:
    path = Path(a.manifest)
    if not path.is_file():
        raise SwapError(f"manifesto não encontrado: {a.manifest}")
    try:
        m = json.loads(path.read_text(encoding="utf8"))
    except ValueError:
        raise SwapError(f"manifesto inválido: {a.manifest}") from None
    chunks = m.get("chunks") or []
    lines = [f"estado: {m.get('state')}  provedor {m.get('provider')} ({m.get('model')}, {m.get('resolution')})",
             f"pedaços: {sum(1 for c in chunks if c.get('state') == 'done')}/{len(chunks)} prontos; tentativas {m.get('attempts')}"]
    est = m.get("estimate") or {}
    lines.append(f"custo previsto US$ {est.get('usd')}; medido {m.get('measured_usd') if m.get('measured_usd') is not None else '-'}")
    if m.get("output"):
        lines.append(f"saída: {m['output']['path']} ({m['output']['duration_s']} s, sha256 {m['output']['sha256'][:12]})")
    if m.get("error"):
        lines.append(f"erro: {m['error']}")
    _emit(m, a.json, "\n".join(lines))
    return 0


def _cmd_run(a) -> int:
    if not a.autorizo:
        raise SwapError("recusado: falta --autorizo. Ele confirma que você tem direito sobre as imagens e o vídeo, "
                        f"e que não vai usar a troca para enganar ou imitar alguém. Texto registrado: \"{AUTORIZACAO_TEXTO}\"")
    if not a.video:
        raise SwapError("falta --video <arquivo>")
    if not (math.isfinite(a.max_usd) and a.max_usd >= 0):
        raise SwapError("--max-usd precisa ser um número finito, 0 ou maior")
    p = prepare(a.provider, a.video, a.ref, a.resolution)
    out = Path(a.out)
    over = p.estimate.usd > a.max_usd
    if not a.yes:
        rep = {"dry_run": True, "provider": a.provider, "chunks": len(p.chunks), "duration_s": round(p.info["duration_s"], 3),
               "estimate": p.estimate.as_dict(), "max_usd": a.max_usd, "exceeds_max_usd": over}
        text = _estimate_text(p, a.max_usd) + ("\n  AVISO: a estimativa passa do teto --max-usd.\n" if over else "\n") + (
            "dry-run: nada foi enviado. Para gerar de verdade, repita com --yes.")
        _emit(rep, a.json, text)
        return 0
    if over:
        raise SpendCapExceeded(f"estimativa {_money(p.estimate.usd)} passa do teto --max-usd {a.max_usd:.2f}: nada foi enviado. "
                        "Suba o teto de propósito ou reduza o vídeo.")
    if not p.adapter.verified and not a.aceito_unverified:
        raise SwapError(f"o adaptador {a.provider} está {UNVERIFIED} (não conferido na API real). Para gastar nele mesmo assim, "
                        "repita com --aceito-unverified.")
    p.adapter.api_key()  # fails before any network call when the variable is missing
    if out.exists() and not a.force:
        raise SwapError(f"a saída já existe: {out} (use --force para sobrescrever)")
    if not a.json:
        print(_estimate_text(p, a.max_usd), file=sys.stderr)
    m = execute(p, out, extra_prompt=a.prompt, timeout=a.timeout, poll_interval=a.poll_interval, max_usd=a.max_usd,
                concurrency=a.concurrency)
    res = {"state": m["state"], "output": m["output"]["path"], "manifest": str(out.parent / MANIFEST_NAME),
           "estimate_usd": m["estimate"]["usd"], "measured_usd": m["measured_usd"], "attempts": m["attempts"],
           "concurrency": m["concurrency"]["effective"], "speedup": (m["timing"] or {}).get("speedup")}
    _emit(res, a.json, f"pronto: {res['output']}\nmanifesto: {res['manifest']}", indent=None)
    return 0


def run_swap(argv: list[str]) -> int:
    ap = _parser()
    a = ap.parse_args(argv)
    if not a.cmd:
        ap.print_help(sys.stderr)
        return 1
    try:
        if a.cmd == "providers":
            rep = providers_report()
            _emit(rep, a.json, _providers_text(rep))
            return 0
        if a.cmd == "estimate":
            if not a.video:
                raise SwapError("falta --video <arquivo>")
            p = prepare(a.provider, a.video, a.ref, a.resolution)
            rep = estimate_report(a.provider, a.video, a.ref, a.resolution, plan=p)
            _emit(rep, a.json, _estimate_text(p))
            return 0
        if a.cmd == "status":
            return _cmd_status(a)
        return _cmd_run(a)
    except SwapError as e:
        print(f"swap: {scrub(str(e))}", file=sys.stderr)
        return getattr(e, "code", 1)
    except KeyboardInterrupt:
        print("swap: interrompido (Ctrl+C); o manifesto guarda os handles já pagos", file=sys.stderr)
        return 130
    except Exception as e:  # noqa: BLE001 (no traceback: it could carry a key; the manifest has the state)
        print(f"swap: erro inesperado: {scrub(f'{type(e).__name__}: {e}')}", file=sys.stderr)
        return 1
