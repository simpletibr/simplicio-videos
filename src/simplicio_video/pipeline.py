"""`simplicio-video run`: validate -> voice -> validate --need-lock -> render(backend) -> publish (Drive).

publish is a dry-run (prints the destination) unless publish=True: uploading a delivery needs an explicit request.
"""
from __future__ import annotations

from pathlib import Path

from . import contract as ct


def run_all(contrato: str | Path, provider: str | None = None, backend: str = "local", accelerator: str | None = None,
            quality: str | None = None, timeout: int = 3600, publish: bool = False, remote: str | None = None,
            force_voice: bool = False, log=print) -> dict:
    from . import publish as pub
    from . import voice
    from .cli import do_render
    steps: dict = {}
    c = ct.load(contrato)
    rep = ct.validate(c)
    bad = [e for e in rep.errors if not e.startswith("voice:")]
    if bad:
        raise SystemExit("contract invalid:\n  " + "\n  ".join(bad))
    log(f"[1/4] voice ({provider or c.data['voz']['provider']})")
    lock = voice.run(c, provider=provider, force=force_voice, log=log)
    steps["voice"] = {"provider": lock["provider"], "lines": {k: v["dur_s"] for k, v in lock["lines"].items()},
                      "usage": lock.get("usage")}
    c = ct.load(contrato)
    rep = ct.validate(c, need_lock=True)
    if not rep.ok:
        raise SystemExit("contract invalid after voice:\n  " + "\n  ".join(rep.errors))
    log(f"[2/4] validate --need-lock: ok")
    log(f"[3/4] render --backend {backend}")
    r = do_render(c, backend, quality=quality, accelerator=accelerator, timeout=timeout, log=log)
    steps["render"] = {"backend": backend, "output": (r.get("output") or {}).get("path") or r.get("bundle"),
                       "loudness": r.get("loudness"), "usage": r.get("usage")}
    if backend == "colab":
        log("[4/4] publish: skipped (backend colab only builds the bundle; render it, then `simplicio-video publish`)")
        steps["publish"] = {"skipped": "colab bundle"}
        return steps
    log(f"[4/4] publish ({'upload' if publish else 'dry-run; pass --publish to upload'})")
    steps["publish"] = pub.publish(c, remote=remote, dry_run=not publish, log=log)
    return steps
