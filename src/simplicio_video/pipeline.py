"""`simplicio-video run`: validate -> voice -> validate --need-lock -> render(backend).

O motor termina no render. O upload no Drive não é feito aqui: é feito pela ferramenta de operação (fora deste repo).
"""
from __future__ import annotations

from pathlib import Path

from . import contract as ct

NOTA_UPLOAD = "upload: não é feito pelo motor; o MP4 fica em saida.arquivo e sobe pela ferramenta de operação"


def run_all(contrato: str | Path, provider: str | None = None, backend: str = "local", accelerator: str | None = None,
            quality: str | None = None, timeout: int = 3600, force_voice: bool = False, log=print) -> dict:
    from . import voice
    from .cli import do_render
    steps: dict = {}
    c = ct.load(contrato)
    rep = ct.validate(c)
    bad = [e for e in rep.errors if not e.startswith("voice:")]
    if bad:
        raise SystemExit("contract invalid:\n  " + "\n  ".join(bad))
    log(f"[1/3] voice ({provider or c.data['voz']['provider']})")
    lock = voice.run(c, provider=provider, force=force_voice, log=log)
    steps["voice"] = {"provider": lock["provider"], "lines": {k: v["dur_s"] for k, v in lock["lines"].items()},
                      "usage": lock.get("usage")}
    c = ct.load(contrato)
    rep = ct.validate(c, need_lock=True)
    if not rep.ok:
        raise SystemExit("contract invalid after voice:\n  " + "\n  ".join(rep.errors))
    log("[2/3] validate --need-lock: ok")
    log(f"[3/3] render --backend {backend}")
    r = do_render(c, backend, quality=quality, accelerator=accelerator, timeout=timeout, log=log)
    steps["render"] = {"backend": backend, "output": (r.get("output") or {}).get("path") or r.get("bundle"),
                       "loudness": r.get("loudness"), "usage": r.get("usage")}
    log(NOTA_UPLOAD)
    return steps
