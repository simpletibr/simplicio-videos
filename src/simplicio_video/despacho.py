"""Dispatch of one render to its backend, and the rule of what each backend delivers.

`simplicio-video render|run`, `pipeline.run_all` and the MCP tool `video.render` all send a render here. It lives in a module of its
own, not in `cli.py`, so that the domain (`pipeline`, `mcp_server`) does not import the CLI to render: the CLI is the volatile side
and the domain the stable one. `cli.do_render` is still there, a lazy re-export of this very function.

This module imports nothing of the package at the top: the backends (`render`, `remote`) are read when a render is dispatched, so
importing it is as light as it was to import the function from the CLI.
"""
from __future__ import annotations

from pathlib import Path


def do_render(c, backend: str, out=None, quality=None, workdir=None, gpu=False, accelerator=None, timeout=3600,
              gpu_encode="auto", log=print) -> dict:
    """Dispatch one render to a backend (shared by render, run and the MCP server)."""
    from . import remote, render
    acc = None if (accelerator or "").lower() in ("none", "cpu") else accelerator
    if backend == "colab":
        return render.render_colab(c, out=out, quality=quality, gpu_encode=gpu_encode, log=log)
    if backend == "kaggle":
        return remote.render_kaggle(c, out=out, quality=quality, timeout_s=timeout, gpu_encode=gpu_encode, log=log,
                                    accelerator="NvidiaTeslaT4" if accelerator is None else acc)
    if backend == "colab-cli":
        return remote.render_colab_cli(c, out=out, quality=quality, timeout_s=timeout, gpu_encode=gpu_encode, log=log,
                                       gpu="T4" if accelerator is None else acc)
    return render.render_local(c, out=out, quality=quality, workdir=workdir, gpu=gpu, log=log)


def saida_do_render(c, r: dict) -> tuple[Path | str | None, Path | None]:
    """What the result `r` of `do_render` delivered: (the file, the manifest next to the contract).

    local, kaggle and colab-cli deliver the MP4 (`r["output"]` is the manifest's `output` block, its path relative to the contract)
    and write `render.manifest.json` next to the contract. The colab backend does not render: it delivers only the bundle `.zip`
    (`r["bundle"]`, the path as the backend returned it) and no manifest. Nothing delivered is (None, None)."""
    if isinstance(r.get("output"), dict):
        return c.dir / r["output"]["path"], c.dir / "render.manifest.json"
    return r.get("bundle"), None
