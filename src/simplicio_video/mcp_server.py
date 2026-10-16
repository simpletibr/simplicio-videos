"""MCP server (stdio) exposing the simplicio-video CLI to the Simplicio Runtime / any MCP client.

Tools: video.init, video.validate, video.voice, video.render, video.run, video.list, video.clone, video.montage,
video.edit, video.opencut, video.toonflow, video.moneyprinter, video.swap, video.formats, video.jobs, video.social (providers|plan|check|recipe, never publish), video.openverse (search|list|show|folha|review; never download or export). Each tool calls the same Python functions as the CLI and returns JSON ({ok, ..., log}).
Long steps (render on kaggle/colab-cli) block until done; video.jobs runs a local voice task in the background instead. O upload no Drive não é tool deste servidor.

Run: `simplicio-video mcp` or `simplicio-video-mcp` (needs `pip install -e .[mcp]`).
"""
from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
from typing import Any

INSTRUCTIONS = ("simplicio-video: short marketing videos from a simplicio.video-contract/v1 YAML "
                "(src/simplicio_video/data/schema/contract.schema.json; how to write it: skills/simplicio-video/SKILL.md). "
                "Flow: video.init -> fill TODOs from clients/<slug>/coleta -> video.validate -> video.voice -> "
                "video.render (or video.run for voice->render). Never invent client facts, never speed up the voice. "
                "The upload is not a tool here: it is done by the operation tool.")


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


def video_run(contrato: str, provider: str | None = None, backend: str = "local", accelerator: str | None = None,
              quality: str | None = None, timeout: int = 3600) -> dict:
    from . import pipeline
    return _capture(pipeline.run_all, contrato, provider=provider, backend=backend, accelerator=accelerator, quality=quality,
                    timeout=timeout)


def video_list(what: str = "templates", grupo: str | None = None) -> dict:
    from . import catalog, paths
    d = paths.data_dir()
    rows = {"templates": lambda: catalog.templates(d), "motion": lambda: catalog.motion(d), "voices": catalog.voices,
            "angles": lambda: catalog.angles(d, grupo=grupo)}[what]()
    return {"ok": True, "items": rows}


def video_clone(args: str = "") -> dict:
    from . import clone
    argv = args.split() if isinstance(args, str) else list(args)
    return _capture(clone.run_hypit, argv)


def video_montage(args: str = "") -> dict:
    from . import montage
    argv = args.split() if isinstance(args, str) else list(args)
    return _capture(montage.run_montage, argv)


def video_opencut(args: str = "") -> dict:
    from . import opencut
    argv = args.split() if isinstance(args, str) else list(args)
    return _capture(opencut.run_opencut, argv)


def video_edit(args: str = "") -> dict:
    from . import edit
    argv = args.split() if isinstance(args, str) else list(args)
    return _capture(edit.run_edit, argv)


def video_formats(acao: str = "list", id: str | None = None, copia: str = "", objetivo: str | None = None) -> dict:
    """Biblioteca de formatos: list (todos ou de um objetivo), show (um formato) e prompt (pedido de adaptação)."""
    from . import formats
    try:
        if acao == "list":
            return {"ok": True, "items": formats.formatos(objetivo)}
        if acao == "show":
            return {"ok": True, "item": formats.formato(id)}
        if acao == "prompt":
            return {"ok": True, "prompt": formats.pedido(id, copia)}
        return {"ok": False, "error": f"acao desconhecida: {acao} (list|show|prompt)"}
    except formats.FormatError as e:
        return {"ok": False, "error": str(e)}


def video_swap(acao: str = "providers", provider: str | None = None, video: str | None = None,
               refs: list[str] | None = None, resolution: str = "720p") -> dict:
    """Character swap, read-only over MCP: `providers` and `estimate`. It never spends money here: `run` exists only in
    the terminal (`simplicio-video swap run --autorizo --yes`)."""
    from . import swap
    try:
        if acao == "providers":
            return {"ok": True, **swap.providers_report()}
        if acao == "estimate":
            if not provider or not video:
                return {"ok": False, "error": "estimate precisa de provider, video e refs"}
            return {"ok": True, **swap.estimate_report(provider, video, list(refs or []), resolution)}
        if acao == "run":
            return {"ok": False, "error": "run não existe pelo MCP: gastar dinheiro só pelo terminal "
                                         "(simplicio-video swap run --autorizo --yes)"}
        return {"ok": False, "error": f"acao desconhecida: {acao} (providers|estimate)"}
    except swap.SwapError as e:
        return {"ok": False, "error": str(e)}


def video_jobs(acao: str = "list", id: str | None = None, kind: str | None = None, params: dict | None = None,
               state: str | None = None) -> dict:
    """Background tasks over MCP: `list`, `status`, `result`, `cancel` for any task, and `submit` ONLY for `voice` with a
    local provider (no money). There is no way to confirm a spend here: `swap-run` and network voice are submitted in the
    terminal (`simplicio-video jobs submit ... --yes`). The function has no `yes` argument on purpose."""
    from . import jobs
    try:
        if acao == "list":
            return {"ok": True, "jobs": [jobs.summary(s) for s in jobs.list_jobs(state)]}
        if acao == "status":
            return {"ok": True, "job": jobs.summary(jobs.status(id or ""))}
        if acao == "result":
            return {"ok": True, **jobs.result(id or "")}
        if acao == "cancel":
            return {"ok": True, "job": jobs.summary(jobs.cancel(id or "", block=False))}
        if acao == "submit":
            return {"ok": True, "job": jobs.summary(jobs.submit(kind or "", dict(params or {}), confirm_yes=False, origin="mcp"))}
        return {"ok": False, "error": f"acao desconhecida: {acao} (list|status|result|cancel|submit)"}
    except jobs.JobError as e:
        return {"ok": False, "error": str(e)}


def video_social(acao: str = "providers", plano: str | None = None, video: str | None = None, caption: str = "",
                 targets: list[str] | None = None, title: str | None = None, at: str | None = None, timezone: str | None = None,
                 ai_generated: bool = False, provider: str | None = None, clip_id: str | None = None) -> dict:
    """Social, local and read-only over MCP: `providers`, `plan` (writes social.plan.json next to the video, never over an
    existing one), `check` and `recipe`. There is no publish here: the agent posts with the provider's own MCP tools, after
    the explicit yes of the user for each post. No overwrite, no custom output path, no --aceito-unverified over MCP."""
    from . import social
    try:
        if acao == "providers":
            return {"ok": True, **social.providers_report()}
        if acao == "plan":
            if not video:
                return {"ok": False, "error": "plan precisa de video, caption e targets"}
            res = social.make_plan(video, list(targets or []), caption=caption, title=title, at=at, timezone=timezone, ai_generated=ai_generated)
            return {"ok": True, "path": res["path"], "plan": res["plan"]}
        if acao in ("check", "recipe") and not plano:
            return {"ok": False, "error": f"{acao} precisa de plano (caminho do social.plan.json)"}
        if acao == "check":
            return social.check_plan(plano)
        if acao == "recipe":
            rec = social.recipe(plano, provider=provider, clip_id=clip_id)
            if rec["blocked"]:
                return {**rec, "ok": False, "error": "BLOQUEADO: " + rec["blocked_reason"]}
            return {"ok": True, **rec}
        if acao in social.PUBLISH_WORDS:
            return {"ok": False, "error": "publicar não existe pelo MCP do motor: o motor só planeja. Poste com as ferramentas MCP do "
                                         "provedor (veja a receita: acao=recipe), com o sim explícito do usuário para cada postagem"}
        return {"ok": False, "error": f"acao desconhecida: {acao} (providers|plan|check|recipe)"}
    except social.SocialError as e:
        return {"ok": False, "error": str(e)}


def video_openverse(acao: str = "list", tipo: str | None = None, consulta: str | None = None, licencas: str = "cc0,pdm,by",
                    limite: int = 10, pagina: int = 1, minimo_largura: int | None = None, duracao_min: float | None = None,
                    duracao_max: float | None = None, id: str | None = None, pedido: str | None = None,
                    veredito: str | None = None, motivo: str = "", por: str = "") -> dict:
    """Openverse library over MCP: `search` (cached, default licenses cc0/pdm/by), `list`, `show`, `folha` (the deterministic
    review sheet for a pair asset+request: objective signals, thumbnail or spectrogram) and `review` (records the verdict of the
    reviewer for that pair). There is no download and no export here: the agent does not choose what is fetched or where files
    are written; `get` and `library export` run in the terminal. The engine never decides whether an asset matches a request."""
    from . import openverse
    try:
        if acao == "search":
            return {"ok": True, **openverse.search(tipo, consulta, licencas, minimo_largura, duracao_min, duracao_max, limite, pagina)}
        if acao == "list":
            return {"ok": True, "itens": openverse.library_list(tipo)}
        if acao == "show":
            return {"ok": True, **openverse.library_show(id, pedido)}
        if acao == "folha":
            return {"ok": True, **openverse.review_sheet(id, pedido)}
        if acao == "review":
            return {"ok": True, **openverse.review(id, pedido, veredito, motivo, por, canal="mcp")}
        if acao in ("get", "download", "baixar", "export", "exportar"):
            return {"ok": False, "error": "baixar e exportar só pelo terminal (simplicio-video openverse get <id> / library export): "
                                         "o agente não escolhe o que é baixado nem onde se grava"}
        return {"ok": False, "error": f"acao desconhecida: {acao} (search|list|show|folha|review)"}
    except openverse.OpenverseError as e:
        return {"ok": False, "error": str(e)}


def video_toonflow(args: str = "") -> dict:
    """Toonflow over MCP: `where` and `clone` into the default folder only. `serve` runs a server that never ends, and
    `clone <dir>` is refused because an agent does not choose where a git checkout is written. Captures its own output
    instead of using _capture: the clone runs git with captured output, so nothing reaches the MCP stdio channel."""
    from . import toonflow
    argv = args.split() if isinstance(args, str) else list(args)
    if argv[:1] == ["serve"]:
        return {"ok": False, "error": f"toonflow serve sobe um servidor local que não termina; rode `simplicio-video toonflow serve {toonflow.LAN_FLAG}` no terminal"}
    if argv[:1] == ["clone"] and len(argv) > 1:
        return {"ok": False, "error": "toonflow clone com pasta só pelo terminal; pelo MCP o checkout vai para a pasta padrão"}
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            rc = toonflow.run_toonflow(argv)
        out = {"ok": rc == 0, "result": rc}
    except Exception as e:  # noqa: BLE001 - report, don't kill the server
        out = {"ok": False, "error": f"{type(e).__name__}: {e}"}
    out["log"] = buf.getvalue().strip()[-8000:]
    return out


def video_moneyprinter(args: str = "") -> dict:
    """MoneyPrinterTurbo over MCP: `where` and `clone` into the default folder only. Everything else is refused:
    `serve` runs servers that never end, `setup` installs packages and writes config.toml, and `clone <dir>` picks where
    a checkout is written. An agent does none of that; the person does it in the terminal."""
    from . import moneyprinter
    argv = args.split() if isinstance(args, str) else list(args)
    if argv[:1] not in (["where"], ["clone"]):
        return {"ok": False, "error": "moneyprinter pelo MCP aceita só `where` e `clone` (na pasta padrão); "
                                      "setup, serve e status são pelo terminal: `simplicio-video moneyprinter setup|serve|status`"}
    if argv[:1] == ["clone"] and len(argv) > 1:
        return {"ok": False, "error": "moneyprinter clone com pasta só pelo terminal; pelo MCP o checkout vai para a pasta padrão"}
    if argv[:1] == ["where"] and len(argv) > 1:
        return {"ok": False, "error": "moneyprinter where não recebe argumentos"}
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            rc = moneyprinter.run_moneyprinter(argv)
        out = {"ok": rc == 0, "result": rc}
    except Exception as e:  # noqa: BLE001 - report, don't kill the server
        out = {"ok": False, "error": f"{type(e).__name__}: {e}"}
    out["log"] = buf.getvalue().strip()[-8000:]
    return out


TOOLS = [
    ("video.init", video_init, "Write a contract skeleton for <cliente> <campanha> from a sector template (fill the TODOs with coleta facts)."),
    ("video.validate", video_validate, "Validate a contract: JSON Schema, assets, scene durations, every line fits (need_lock before render)."),
    ("video.voice", video_voice, "Generate/cache narration (provider file|local|gemini) and write timing.lock.json with real durations."),
    ("video.render", video_render, "Render the contract: backend local | kaggle (GPU T4) | colab-cli | colab (bundle only). Returns manifest summary."),
    ("video.run", video_run, "voice -> validate -> render in one call (stops at the MP4; no upload)."),
    ("video.list", video_list, "List templates, motion patterns, voice providers or ad angles (what = templates|motion|voices|angles; angles accepts grupo)."),
    ("video.clone", video_clone, "Clone videos using Hypit AI (https://github.com/hypit-ai/hypit)."),
    ("video.montage", video_montage, "Agentic video production using OpenMontage (https://github.com/calesthio/OpenMontage)."),
    ("video.edit", video_edit, "video-use EDL editing over any MP4 (setup|transcribe|pack|render|verify)."),
    ("video.opencut", video_opencut, "OpenCut editor (clone|dev|where) for manual finishing (https://github.com/OpenCut-app/OpenCut)."),
    ("video.formats", video_formats, "Library of 50 ad formats from the Drive swipe file: list (objetivo), show (id), prompt (id + copia) to adapt a copy to a format."),
    ("video.swap", video_swap, "Character swap, read-only: providers (adapters, capabilities, price, confidence) and estimate (cost before spending). Never runs a paid swap; run is terminal-only."),
    ("video.jobs", video_jobs, "Background tasks: list, status, result, cancel; submit only for voice with a LOCAL provider (kind=voice, params={contrato, provider: file|local|voxcpm|openvoice}). Never spends: swap-run and network voice are submitted in the terminal (jobs submit ... --yes)."),
    ("video.social", video_social, "Social, local and read-only: providers (Real Oficial default, Zernio; their MCP tools and limits), plan (validate an MP4 against per-network limits, write social.plan.json), check (plan still matches the file) and recipe (the exact MCP call sequence for the provider: quote/preview, show the user, explicit consent, then publish). Never publishes: the agent posts with the provider's own tools after the user's explicit yes per post."),
    ("video.openverse", video_openverse, "Openverse image and audio library with per-request review: search (cached; licenses cc0,pdm,by by default), list, show, folha (deterministic review sheet for an asset+request pair: dimensions, sharpness, brightness, thumbnail for images; duration, loudness, silence, clipping, spectrogram for audio; a text hint) and review (records the reviewer's verdict for that pair). Never downloads or exports: get and library export are terminal-only. The license comes from the sources: check the origin, this is not legal advice."),
    ("video.toonflow", video_toonflow, "Toonflow open-source AI studio for short dramas and videos: clone into the default folder, where (serve runs in the terminal with --lan) (https://github.com/HBAI-Ltd/Toonflow-app)."),
    ("video.moneyprinter", video_moneyprinter, "MoneyPrinterTurbo topic-to-short-video generator: clone into the default folder and where only (setup and serve run in the terminal) (https://github.com/harry0703/MoneyPrinterTurbo)."),
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
