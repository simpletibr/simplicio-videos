"""MCP server (stdio) exposing the simplicio-video CLI to the Simplicio Runtime / any MCP client.

Tools: video.init, video.validate, video.voice, video.render, video.publish, video.run, video.list.
Each tool calls the same Python functions as the CLI and returns JSON ({ok, ..., log}). Long steps (render on
kaggle/colab-cli) block until done. video.publish / video.run upload only with publish=true (explicit request).

Run: `simplicio-video mcp` or `simplicio-video-mcp` (needs `pip install -e .[mcp]`).
"""
from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
from typing import Any

INSTRUCTIONS = ("simplicio-video: short marketing videos from a simplicio.video-contract/v1 YAML "
                "(schema/contract.schema.json; how to write it: skills/simplicio-video/SKILL.md). "
                "Flow: video.init -> fill TODOs from clients/<slug>/coleta -> video.validate -> video.voice -> "
                "video.render -> video.publish (or video.run for voice->render->publish). Never invent client facts, "
                "never speed up the voice; publish=true only when the user explicitly asked to upload.")


def _capture(fn, *a, **k) -> dict[str, Any]:
    """Run fn with a log collector; SystemExit from the CLI layer becomes {ok: false, error}."""
    lines: list[str] = []
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            res = fn(*a, log=lambda *m: lines.append(" ".join(str(x) for x in m)), **k)
        out = {"ok": True, "result": json.loads(json.dumps(res, default=str)) if res is not None else None}
    except SystemExit as e:
        out = {"ok": False, "error": str(e.code if e.code is not None else e)}
    except Exception as e:  # noqa: BLE001 - report, don't kill the server
        out = {"ok": False, "error": f"{type(e).__name__}: {e}"}
    extra = buf.getvalue().strip()
    out["log"] = "\n".join(lines + ([extra] if extra else []))[-8000:]
    return out


# ---- plain functions (testable without the SDK) ----
def video_init(cliente: str, campanha: str, template: str, nome: str | None = None, ano: int | None = None,
               out: str | None = None, force: bool = False) -> dict:
    from . import paths, scaffold

    def _do(log):
        h = paths.home()
        data = scaffold.skeleton(h, cliente, campanha, template, ano, nome, None)
        dst = Path(out) if out else h / "clients" / cliente / data["campanha"]["id"].lower().replace("_", "-") / "contract.yaml"
        scaffold.write(dst, data, force)
        log(f"contrato: {dst}")
        return {"contrato": str(dst)}
    return _capture(_do)


def video_validate(contrato: str, need_lock: bool = False) -> dict:
    from . import contract as ct
    c = ct.load(contrato)
    rep = ct.validate(c, need_lock=need_lock)
    return {"ok": rep.ok, "errors": rep.errors, "warnings": rep.warnings}


def video_voice(contrato: str, provider: str | None = None, force: bool = False, only: list[str] | None = None) -> dict:
    from . import contract as ct
    from . import voice

    def _do(log):
        lock = voice.run(ct.load(contrato), provider=provider, force=force, only=only or [], log=log)
        return {"provider": lock["provider"], "usage": lock.get("usage"),
                "lines": {k: {"dur_s": v["dur_s"], "max_s": v["max_s"], "fits": v["fits"]} for k, v in lock["lines"].items()}}
    return _capture(_do)


def video_render(contrato: str, backend: str = "local", accelerator: str | None = None, quality: str | None = None,
                 out: str | None = None, timeout: int = 3600) -> dict:
    from . import contract as ct
    from .cli import do_render

    def _do(log):
        r = do_render(ct.load(contrato), backend, out=Path(out) if out else None, quality=quality, accelerator=accelerator,
                      timeout=timeout, log=log)
        return {k: r.get(k) for k in ("backend", "output", "loudness", "usage", "inputs_sha256", "bundle", "notebook", "timings_s") if k in r}
    return _capture(_do)


def video_publish(contrato: str, publish: bool = False, remote: str | None = None, file: str | None = None) -> dict:
    from . import contract as ct
    from . import publish as pub
    return _capture(pub.publish, ct.load(contrato), file=Path(file) if file else None, remote=remote, dry_run=not publish)


def video_run(contrato: str, provider: str | None = None, backend: str = "local", accelerator: str | None = None,
              quality: str | None = None, publish: bool = False, remote: str | None = None, timeout: int = 3600) -> dict:
    from . import pipeline
    return _capture(pipeline.run_all, contrato, provider=provider, backend=backend, accelerator=accelerator, quality=quality,
                    publish=publish, remote=remote, timeout=timeout)


def video_list(what: str = "templates") -> dict:
    from . import catalog, paths
    h = paths.home()
    rows = {"templates": lambda: catalog.templates(h), "motion": lambda: catalog.motion(h), "voices": catalog.voices}[what]()
    return {"ok": True, "items": rows}


TOOLS = [
    ("video.init", video_init, "Write a contract skeleton for <cliente> <campanha> from a sector template (fill the TODOs with coleta facts)."),
    ("video.validate", video_validate, "Validate a contract: JSON Schema, assets, scene durations, every line fits (need_lock before render)."),
    ("video.voice", video_voice, "Generate/cache narration (provider file|local|gemini) and write timing.lock.json with real durations."),
    ("video.render", video_render, "Render the contract: backend local | kaggle (GPU T4) | colab-cli | colab (bundle only). Returns manifest summary."),
    ("video.publish", video_publish, "Upload the MP4 to Google Drive at drive.caminho (rclone) and write the link in the client README. "
                                     "Dry-run unless publish=true (only when the user explicitly asked)."),
    ("video.run", video_run, "voice -> validate -> render -> publish in one call (publish dry-run unless publish=true)."),
    ("video.list", video_list, "List templates, motion patterns or voice providers (what = templates|motion|voices)."),
]


def build_server():
    try:  # mcp >= 2
        from mcp.server.mcpserver import MCPServer as Server
    except ImportError:  # mcp 1.x
        try:
            from mcp.server.fastmcp import FastMCP as Server
        except ImportError as e:
            raise SystemExit("simplicio-video mcp: install the MCP SDK first: pip install -e '.[mcp]'") from e
    srv = Server("simplicio-video", instructions=INSTRUCTIONS)
    for name, fn, desc in TOOLS:
        srv.tool(name=name, description=desc)(fn)
    return srv


def main() -> None:
    build_server().run("stdio")


if __name__ == "__main__":
    main()
