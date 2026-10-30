"""Pinned versions and install location for the external tracks: `montage` (OpenMontage), `opencut` (OpenCut),
`clone` (Hypit), `toonflow` (Toonflow), `moneyprinter` (MoneyPrinterTurbo), `matchcut` (match-cut), `busca` (TinyFish CLI) and
`voicestudio` (VoiceStudio) and `media fetch` (yt-dlp). `simplicio-video tools` lists the whole registry (text or --json).

The engine drives: OpenMontage, OpenCut, Hypit, Toonflow, MoneyPrinterTurbo, VoiceStudio and yt-dlp, each pinned to a known
version.

The deterministic render (contract -> MP4) never depends on them. They are optional tracks: an agentic
producer (OpenMontage), a manual editor (OpenCut), an agentic cloner (Hypit) and a creation studio for
short dramas and comics (Toonflow), a topic-to-short-video generator (MoneyPrinterTurbo) and a local voice studio
for TTS, voice cloning and transcription (VoiceStudio). Whatever they produce enters a contract as a file with a hash,
so the final render stays reproducible.

Install location: $SIMPLICIO_TOOLS_DIR (default ~/.simplicio-video/tools/<name>).
Pins: $SIMPLICIO_<NAME>_REF overrides the commit (git tools) or version (npm tools). A pip tool has no override:
its wheel is pinned by version and sha256 here, and pip refuses anything else (--require-hashes).
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


class ToolError(Exception):
    pass


@dataclass(frozen=True)
class Tool:
    name: str
    kind: str          # "git", "npm" or "pip" (a wheel in its own venv)
    source: str        # git URL, npm package, or the home page of a pip project (its PyPI name is the tool name)
    ref: str           # pinned commit or version
    license: str
    role: str
    marker: str = ""   # a file or folder that proves a git checkout is the right one
    note: str = ""
    sha256: str = ""   # pip tools: the sha256 of the pinned wheel, checked by pip --require-hashes


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
    "matchcut": Tool("matchcut", "git", "https://github.com/Sac-Y/match-cut",
                     "b51c98f5c795b046ceb1c69396368dbabd88d5d9", "MIT",
                     "agent skill (SKILL.md, scripts, references) for product films in the match-cut relay style; "
                     "the engine only downloads the pinned commit and points at it, it never runs the skill",
                     marker="SKILL.md",
                     note="the skill is used from Claude Code or Codex and needs a Renoise sign-in (the user's own "
                          "account) and paid Renoise credits; the engine never calls Renoise and never asks for a secret"),
    "voicestudio": Tool("voicestudio", "git", "https://github.com/debpalash/VoiceStudio",
                         "beeaae08204f0de5f49d4a087ef2b0ea8fecfcb9", "AGPL-3.0",
                         "local voice studio: cloned/designed voice profiles, TTS and transcription over a loopback "
                         "OpenAI-compatible API and an MCP server on :3900; runs as a separate program, never imported",
                         marker="package.json",
                         note="pin = release v0.5.7 (published 2026-10-26), commit beaae08 read from the GitHub API on "
                              "2026-10-27. The desktop app is installed with "
                              "`curl -fsSL https://voicestudio.sh/install | sh`; from source the alternative is "
                              "`bun install && bun run dev` (this pin clones that source checkout). Loopback needs no "
                              "credential; the app is only reached over local HTTP (AGPL-3.0, never vendored)"),
    "video-use": Tool("video-use", "git", "https://github.com/browser-use/video-use",
                        "b877063", "MIT",
                        "EDL editing over any MP4: word-accurate cuts, subtitles, overlays and filmstrip review; "
                        "the agent decides the EDL, ffmpeg executes it", marker="render.py",
                        note="pinned by tools/video-use/setup.sh (23/09/2026); the checkout lives in "
                             "~/.cache/simplicio/video-use, not in the tools cache"),
    "tinyfish": Tool("tinyfish", "npm", "@tiny-fish/cli", "0.50.1", "not declared in the npm package (no license field, no LICENSE file; read 2026-10-16)",
                     "web search and page fetch for research (`simplicio-video busca`); installed by the user, never bundled and never installed by the engine",
                     note="the engine uses only `search query`, `fetch content get`, `auth status` and `--version`: agent, browser and monitor (browser "
                          "automation, metered by step or minute) are out of scope. The package declares Node >= 24. The query or URL goes to a third "
                          "party (TinyFish): the engine refuses secrets and, unless told otherwise, personal data"),
    "yt-dlp": Tool("yt-dlp", "pip", "https://github.com/yt-dlp/yt-dlp", "2026.10.26", "Unlicense",
                   "downloads one public video page to a local MP4 (`simplicio-video media fetch`); the engine never logs in, "
                   "never reads browser cookies and never downloads a playlist",
                   note="installed in its own venv under the tools cache, never on the global PATH; the wheel has no required "
                        "dependencies and is checked by sha256 (pip --require-hashes). The download needs --autorizo: the user "
                        "confirms the right to use the file, and the engine does not verify it. Platforms such as Instagram "
                        "restrict downloads in their own terms; that responsibility is the user's",
                   sha256="a05c5b5d8562f7e8a62f5334348b406af4930d56d3a65f8021d14af0e22339ae"),
}


# CLI command that fronts each track (the `tools` listing reads this, never a second table).
COMMANDS: dict[str, str] = {
    "video-use": "edit",
    "openmontage": "montage",
    "opencut": "opencut",
    "hypit": "clone",
    "toonflow": "toonflow",
    "moneyprinter": "moneyprinter",
    "matchcut": "matchcut",
    "tinyfish": "busca",
    "voicestudio": "voicestudio",
    "yt-dlp": "media fetch",
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


PIP_BIN_DIR = "Scripts" if os.name == "nt" else "bin"


def _venv_python(venv: Path) -> Path:
    return venv / PIP_BIN_DIR / ("python.exe" if os.name == "nt" else "python")


def pip_binary(name: str) -> Path | None:
    """The executable of a pip tool inside its venv, or None when it is not installed."""
    t = get(name)
    if t.kind != "pip":
        return None
    exe = checkout_dir(t) / "venv" / PIP_BIN_DIR / (f"{t.name}.exe" if os.name == "nt" else t.name)
    return exe if exe.is_file() else None


def _install_pip(t: Tool) -> str:
    """A pip tool: a venv of its own under the tools cache, and the pinned wheel installed with its sha256 checked."""
    ref = pinned_ref(t)
    if ref != t.ref:
        raise ToolError(f"{t.name}: o override de versão ({ref}) não tem hash neste registro; a versão e o sha256 andam juntos em tools.py")
    d = checkout_dir(t)
    d.mkdir(parents=True, exist_ok=True)
    venv = d / "venv"
    if not _venv_python(venv).is_file():
        r = subprocess.run([sys.executable, "-m", "venv", str(venv)], capture_output=True, text=True)
        if r.returncode:
            raise ToolError(f"venv de {t.name}: {r.stderr.strip()[-300:]}")
    requisitos = d / "requirements.txt"
    requisitos.write_text(f"{t.name}=={ref} --hash=sha256:{t.sha256}\n", encoding="utf8")
    r = subprocess.run([str(_venv_python(venv)), "-m", "pip", "install", "--quiet", "--disable-pip-version-check",
                        "--require-hashes", "-r", str(requisitos)], capture_output=True, text=True)
    if r.returncode:
        raise ToolError(f"pip install {t.name}=={ref}: {r.stderr.strip()[-300:]}")
    exe = pip_binary(t.name)
    if exe is None:
        raise ToolError(f"{t.name}: o pip terminou, mas o executável não apareceu em {venv}")
    return str(exe)


def install(name: str) -> str:
    """Install a tool at its pinned version. Git tools are cloned and checked out at the pinned commit; npm tools are
    fetched into the npx cache; pip tools get a venv with the pinned wheel. Returns where it lives."""
    t = get(name)
    ref = pinned_ref(t)
    if t.kind == "pip":
        return _install_pip(t)
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

def command(t: Tool) -> str:
    """The CLI command that fronts a track (COMMANDS, defaulting to the tool name)."""
    return f"simplicio-video {COMMANDS.get(t.name, t.name)}"


def is_installed(t: Tool) -> bool:
    """Git tools: the pinned checkout in the tools cache. pip tools: the executable in their venv. npm tools: the binary
    on PATH (as `status` does)."""
    if t.kind == "git":
        return find(t.name) is not None
    if t.kind == "pip":
        return pip_binary(t.name) is not None
    return shutil.which(t.name) is not None


def listing() -> list[dict]:
    """Every pinned external track, read from TOOLS (never a second table). Offline: only the filesystem is checked."""
    return [{"name": t.name, "command": command(t), "repo": t.source, "version": pinned_ref(t),
             "installed": is_installed(t), "license": t.license, "produces": t.role}
            for t in TOOLS.values()]


def text_listing(rows: list[dict]) -> str:
    lines = ["trilhas externas (versão fixada em tools.py; o render determinístico não depende de nenhuma delas):"]
    for r in rows:
        estado = "sim" if r["installed"] else "não"
        lines.append(f"  {r['name']:<13} instalada: {estado:<4} versão fixada: {r['version']}")
        lines.append(f"    comando: {r['command']}  ({r['license']})")
        lines.append(f"    repo: {r['repo']}")
        lines.append(f"    produz: {r['produces']}")
    lines.append("instalada = checkout no cache de tools ($SIMPLICIO_TOOLS_DIR, padrão ~/.simplicio-video/tools); para trilhas npm, "
                 "o binário no PATH; para trilhas pip, o executável no venv da trilha.")
    return "\n".join(lines)

