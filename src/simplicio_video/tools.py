"""Pinned versions and install location for the external tools behind the existing commands
`montage` (OpenMontage), `opencut` (OpenCut), `clone` (Hypit), `toonflow` (Toonflow) and `moneyprinter`
(MoneyPrinterTurbo). No command of its own.

The engine drives: OpenMontage, OpenCut, Hypit, Toonflow and MoneyPrinterTurbo, each pinned to a known version.

The deterministic render (contract -> MP4) never depends on them. They are optional tracks: an agentic
producer (OpenMontage), a manual editor (OpenCut), an agentic cloner (Hypit) and a creation studio for
short dramas and comics (Toonflow) and a topic-to-short-video generator (MoneyPrinterTurbo). Whatever they produce enters a contract as a file with a hash, so the
final render stays reproducible.

Install location: $SIMPLICIO_TOOLS_DIR (default ~/.simplicio-video/tools/<name>).
Pins: $SIMPLICIO_<NAME>_REF overrides the commit (git tools) or version (npm tools).
"""
from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


class ToolError(Exception):
    pass


@dataclass(frozen=True)
class Tool:
    name: str
    kind: str          # "git" or "npm"
    source: str        # git URL or npm package
    ref: str           # pinned commit or version
    license: str
    role: str
    marker: str = ""   # a file or folder that proves a git checkout is the right one
    note: str = ""


TOOLS: dict[str, Tool] = {
    "openmontage": Tool("openmontage", "git", "https://github.com/calesthio/OpenMontage",
                        "9327439db69021ab4b0e2776729bf3b58fdb5a87", "AGPL-3.0",
                        "agentic production (Backlot, pipelines); runs as a separate program, never imported",
                        marker="backlot"),
    "opencut": Tool("opencut", "git", "https://github.com/OpenCut-app/opencut-classic",
                    "cf5e79e919144200294fb9fed22a222592a0aeea", "MIT",
                    "manual finishing editor (web app on localhost)", marker="package.json",
                    note="opencut-classic is archived upstream; the OpenCut rewrite has no headless API yet"),
    "hypit": Tool("hypit", "npm", "@hypit/hypit", "0.2.17", "Hypit license (modified Apache-2.0)",
                  "agentic video cloning; user-installed, never bundled or offered as a hosted service",
                  note="its license forbids commercial redistribution and multi-tenant service without permission"),
    "toonflow": Tool("toonflow", "git", "https://github.com/HBAI-Ltd/Toonflow-app",
                     "d2e94aca7b59659ff6b4ca15f03cf134ec7f0e1d", "MIT",
                     "open-source AI studio for short dramas, comic dramas and videos (Bun, web app on localhost); "
                     "runs as a separate program, never imported", marker="package.json",
                     note="its server has no login and listens on 0.0.0.0:3000 (every interface): serve needs --lan"),
    "moneyprinter": Tool("moneyprinter", "git", "https://github.com/harry0703/MoneyPrinterTurbo",
                         "4b7b9657647bdb149715354269eec7e4dbad4a7a", "MIT",
                         "topic-to-short-video generator (LLM script, synthesized voice, stock footage; Python 3.11+, "
                         "Streamlit WebUI and FastAPI); runs as a separate program, never imported",
                         marker="config.example.toml",
                         note="it calls third-party services with their own terms (LLM providers, TTS, stock footage such as "
                              "Pexels, Pixabay and Coverr) and needs your own API keys in its config.toml; the terms were not "
                              "reviewed here. Its API config listens on 0.0.0.0 by default and the WebUI has no login: serve "
                              "forces 127.0.0.1 unless --lan"),
}


def get(name: str) -> Tool:
    try:
        return TOOLS[name]
    except KeyError:
        raise ToolError(f"ferramenta desconhecida: {name} ({', '.join(TOOLS)})") from None


def pinned_ref(t: Tool) -> str:
    return os.environ.get(f"SIMPLICIO_{t.name.upper()}_REF") or t.ref


def tools_dir() -> Path:
    return Path(os.environ.get("SIMPLICIO_TOOLS_DIR") or Path.home() / ".simplicio-video" / "tools").expanduser()


def checkout_dir(t: Tool) -> Path:
    env = os.environ.get(f"{t.name.upper()}_DIR") or os.environ.get(f"SIMPLICIO_{t.name.upper()}_DIR")
    return Path(env).expanduser() if env else tools_dir() / t.name


def _git(*args: str, cwd: Path | None = None) -> str:
    git = shutil.which("git")
    if not git:
        raise ToolError("git não encontrado no PATH")
    r = subprocess.run([git, *args], cwd=cwd, capture_output=True, text=True)
    if r.returncode:
        raise ToolError(f"git {' '.join(args[:2])}: {r.stderr.strip()[-300:]}")
    return r.stdout.strip()


def find(name: str) -> Path | None:
    """The checkout of a git tool, or None when it is not installed."""
    t = get(name)
    if t.kind != "git":
        return None
    d = checkout_dir(t)
    return d.resolve() if d.is_dir() and (d / t.marker).exists() else None


def install(name: str) -> str:
    """Install a tool at its pinned version. Git tools are cloned and checked out at the pinned commit;
    npm tools are fetched into the npx cache. Returns where it lives."""
    t = get(name)
    ref = pinned_ref(t)
    if t.kind == "npm":
        npx = shutil.which("npx")
        if not npx:
            raise ToolError("npx não encontrado no PATH (Node >= 18)")
        r = subprocess.run([npx, "--yes", f"{t.source}@{ref}", "--version"], capture_output=True, text=True)
        if r.returncode:
            raise ToolError(f"{t.source}@{ref}: {r.stderr.strip()[-300:]}")
        return f"npx {t.source}@{ref}"
    d = checkout_dir(t)
    if not (d / ".git").is_dir():
        d.parent.mkdir(parents=True, exist_ok=True)
        _git("clone", "--filter=blob:none", t.source, str(d))
    _git("fetch", "--quiet", "origin", ref, cwd=d)
    _git("checkout", "--quiet", "--detach", ref, cwd=d)
    return str(d)


def npm_command(name: str) -> list[str]:
    """Command prefix for an npm tool: a local binary on PATH wins, else npx at the pinned version."""
    t = get(name)
    local = shutil.which(t.name)
    if local:
        return [local]
    npx = shutil.which("npx")
    if not npx:
        raise ToolError(f"nem `{t.name}` nem `npx` foram encontrados no PATH. Instale o Node (>= 18).")
    return [npx, "--yes", f"{t.source}@{pinned_ref(t)}"]
