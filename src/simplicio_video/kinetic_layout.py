"""Layout guard for the kinetic text (motion/patterns/kinetic-words) in headless Chrome.

Measures every word on the real engine (fonts, transforms, panel, logo) every frame: the assembled text per line,
the smallest gap between neighbouring visible words and anything that leaves the 1080x1920 frame.
Used by `simplicio-video intl` before rendering and by the tests. Needs node + puppeteer-core + chrome-headless-shell
(both come with HyperFrames: ~/.npm/_npx/*/node_modules/puppeteer-core and ~/.cache/hyperframes/chrome).
"""
from __future__ import annotations

import glob
import html
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

from . import paths

ENGINE = Path(__file__).parent / "engine"
MIN_GAP_EM = 0.15  # neighbouring words never get closer than this (at 1080 px; the text reads as one word below it)


class LayoutUnavailable(RuntimeError):
    pass


def _first(pats: list[str]) -> str | None:
    for p in pats:
        hits = sorted(glob.glob(os.path.expanduser(p)))
        if hits:
            return hits[-1]
    return None


def tools() -> dict:
    pc = os.environ.get("PUPPETEER_CORE") or _first(["~/.npm/_npx/*/node_modules/puppeteer-core"])
    ch = os.environ.get("CHROME_BIN") or _first(["~/.cache/hyperframes/chrome/chrome-headless-shell/*/chrome-headless-shell-linux64/chrome-headless-shell"])
    gs = ENGINE / "vendor" / "gsap-3.14.2.min.js"
    if not (pc and ch and gs.is_file()):
        raise LayoutUnavailable("layout guard needs puppeteer-core + chrome-headless-shell (run one HyperFrames render first)")
    return {"PUPPETEER_CORE": pc, "CHROME_BIN": ch, "GSAP_JS": str(gs)}


def probe(block: Path, assets_root: Path, jobs: list[dict]) -> list[dict]:
    env = {**paths.node_env(), **tools()}
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(jobs, f)
    try:
        p = subprocess.run(["node", str(ENGINE / "kinetic_probe.mjs"), str(block), str(assets_root), f.name],
                           capture_output=True, text=True, env=env, timeout=600)
    finally:
        os.unlink(f.name)
    if p.returncode != 0:
        raise RuntimeError(f"kinetic probe failed: {p.stderr[-1500:]}")
    return json.loads(p.stdout)


def project_jobs(index_html: Path, step: float = 1 / 30) -> list[dict]:
    """kinetic-words instances of a built HyperFrames project (index.html with resolved variables)."""
    s = index_html.read_text(encoding="utf8")
    jobs = []
    for m in re.finditer(r'<div id="([^"]+)"[^>]*data-composition-id="kinetic-words"[^>]*data-start="([\d.]+)"[^>]*'
                         r'data-duration="([\d.]+)"[^>]*data-variable-values=\'([^\']*)\'', s):
        v = json.loads(html.unescape(m.group(4)))
        v.setdefault("dur", float(m.group(3)))
        jobs.append({"id": m.group(1), "start": float(m.group(2)), "vars": v, "step": step})
    return jobs


def problems(res: list[dict], min_em: float = MIN_GAP_EM) -> list[str]:
    out = []
    for r in res:
        if r.get("min_gap_em") is not None and r["min_gap_em"] < min_em:
            a = r["min_gap_at"]
            out.append(f"{r['id']}: palavras quase coladas ({a['between']}, {a['px']} px = {r['min_gap_em']} em em t={a['t']} s)")
        if r.get("out_of_frame_n"):
            x = r["out_of_frame"][0]
            out.append(f"{r['id']}: texto sai da tela ({x['w']} x={x['l']}..{x['r']} em t={x['t']} s; {r['out_of_frame_n']} medições)")
    return out


def check_project(project: Path, block: Path | None = None, step: float = 1 / 30) -> tuple[list[dict], list[str]]:
    """Probe every kinetic block of a built project with the repo's kinetic-words (or `block`)."""
    block = block or paths.home() / "motion" / "patterns" / "kinetic-words" / "block.html"
    jobs = project_jobs(project / "index.html", step)
    res = probe(block, project, jobs)
    for j, r in zip(jobs, res):
        r["start"] = j["start"]
    return res, problems(res)
