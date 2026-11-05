"""Pinned versions and install location for the external tracks: `montage` (OpenMontage), `opencut` (OpenCut),
`clone` (Hypit), `toonflow` (Toonflow), `moneyprinter` (MoneyPrinterTurbo), `matchcut` (match-cut), `instagram` (instagram-agent-skill), `busca` (TinyFish CLI) and
`voicestudio` (VoiceStudio), `rea-video` (rea-video) and `media fetch` (yt-dlp). `simplicio-video tools` lists the whole registry (text or --json).

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
Lock: `simplicio-video update` follows the upstream of each track (git default branch, npm and PyPI latest) and records what it
resolved in tools.lock.json (tools_lock.py). effective() reads that lock; pinned_ref() stays the registry pin (or the override).
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from . import hostos, tools_lock


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
    "instagram": Tool("instagram", "git", "https://github.com/Jakeschincariol/instagram-agent-skill",
                      "d03c56bb598be770c60b201f94237e5d1a4268a6", "MIT",
                      "thirteen agent skills (SKILL.md prompts) and six local standard-library scripts for Instagram Reels, captions and "
                      "drafts; the engine downloads the pinned commit, lists the skills and runs only those six scripts, after checking "
                      "the sha256 of each one", marker="skills/ig-reel/hookscore.py",
                      note="the heuristics (regexes, word lexicon, 26 hook formulas) are in English and were measured by the author on 74 "
                           "YouTube Shorts hooks (AUC 0.83 to catch bad hooks, 0.56 to pick winners): in Portuguese they score badly or "
                           "are ignored. The skills are prompts for an agent, not code. Nothing here posts or publishes: the engine never "
                           "posts, the skills write and the user posts"),
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
                        note="pinned by the video-use setup.sh (data/tools/video-use) (23/09/2026); the checkout lives in "
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
    "rea_video": Tool("rea_video", "git", "https://github.com/JuneYaooo/rea-video",
                      "36e02ddf1ffc287bd760d816c132027598f2e4c0",
                      "MIT, declarada no pyproject.toml; o commit fixado não traz arquivo LICENSE",
                      "reverse-engineers a video shot by shot (live action, AI, 3D, code render, mixed) and plans a remake; "
                      "runs as a separate program in a venv of its own, never imported", marker="rea_video/cli.py",
                      note="the pin is the default branch of the upstream repository as read on 2026-11-04. Without --vlm nothing "
                           "leaves the machine; with --vlm the frames go to the vision model provider the user configures (a third "
                           "party). The first analysis downloads about 67 MB of voice model. `setup` installs with pip without "
                           "hashes: the upstream has no lock file"),
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
    "instagram": "instagram",
    "tinyfish": "busca",
    "voicestudio": "voicestudio",
    "rea_video": "rea-video",
    "yt-dlp": "media fetch",
}


def get(name: str) -> Tool:
    try:
        return TOOLS[name]
    except KeyError:
        raise ToolError(f"ferramenta desconhecida: {name} ({', '.join(TOOLS)})") from None


def pinned_ref(t: Tool) -> str:
    return os.environ.get(f"SIMPLICIO_{t.name.upper()}_REF") or t.ref


def lock_entry(name: str) -> dict:
    """The lock entry of a track, or {} when there is none (a lock that is not usable is reported by `doctor`, not here)."""
    try:
        return tools_lock.read_lock()["tools"].get(name, {})
    except tools_lock.LockInvalid:
        return {}


def effective(t: Tool) -> tuple[str, str]:
    """(ref, source) of what the track really uses: the override SIMPLICIO_<NAME>_REF, else the ref `update` resolved for a
    followed track (the lock keeps the ref in place even after a failed update), else the registry pin."""
    override = os.environ.get(f"SIMPLICIO_{t.name.upper()}_REF")
    if override:
        return override, "override"
    entry = lock_entry(t.name)
    if entry.get("mode") == "follow" and entry.get("ref"):
        return entry["ref"], "lock"
    return t.ref, "pin"


def effective_ref(t: Tool) -> str:
    return effective(t)[0]


def effective_pip(t: Tool) -> tuple[str, str, str]:
    """(version, sha256, source) of a pip track. A followed version carries its own sha256 in the lock; otherwise the registry
    pair stands (an override is refused by _install_pip unless it is the pinned version)."""
    ref, source = effective(t)
    if source == "lock":
        digest = lock_entry(t.name).get("sha256")
        if not digest:
            raise ToolError(f"{t.name}: o lock não tem o sha256 da versão {ref}; rode `simplicio-video update` de novo")
        return ref, digest, source
    return ref, t.sha256, source


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


def _run_subprocess(argv, cwd=None) -> "subprocess.CompletedProcess":
    """The default runner: a missing program is a failed command (rc 127), never an OSError out of here."""
    try:
        return subprocess.run([str(a) for a in argv], cwd=str(cwd) if cwd else None, capture_output=True, text=True,
                              encoding="utf-8", errors="replace")
    except OSError as exc:
        return subprocess.CompletedProcess(list(argv), 127, "", str(exc))


def _motivo(done) -> str:
    return (done.stderr or done.stdout or "").strip()[-300:]


def install_pip_version(t: Tool, version: str, sha256: str, run=None) -> str:
    """A pip tool at `version`: a venv of its own under the tools cache, and the wheel installed with its sha256 checked
    (--require-hashes: pip refuses anything else). `run(argv, cwd)` runs the commands; the update passes its own (tests: fakes)."""
    run = run or _run_subprocess
    d = checkout_dir(t)
    d.mkdir(parents=True, exist_ok=True)
    venv = d / "venv"
    if not _venv_python(venv).is_file():
        r = run([sys.executable, "-m", "venv", str(venv)], None)
        if r.returncode:
            raise ToolError(f"venv de {t.name}: {_motivo(r)}")
    requisitos = d / "requirements.txt"
    requisitos.write_text(f"{t.name}=={version} --hash=sha256:{sha256}\n", encoding="utf8")
    r = run([str(_venv_python(venv)), "-m", "pip", "install", "--quiet", "--disable-pip-version-check",
             "--require-hashes", "-r", str(requisitos)], None)
    if r.returncode:
        raise ToolError(f"pip install {t.name}=={version}: {_motivo(r)}")
    exe = pip_binary(t.name)
    if exe is None:
        raise ToolError(f"{t.name}: o pip terminou, mas o executável não apareceu em {venv}")
    return str(exe)


def _install_pip(t: Tool) -> str:
    """A pip tool at the version in use (the lock's, when followed; the registry's otherwise), with its sha256 checked."""
    version, digest, source = effective_pip(t)
    if source == "override" and version != t.ref:
        raise ToolError(f"{t.name}: o override de versão ({version}) não tem hash neste registro; a versão e o sha256 andam juntos em tools.py")
    return install_pip_version(t, version, digest)


def install(name: str) -> str:
    """Install a tool at its pinned version. Git tools are cloned and checked out at the pinned commit; npm tools are
    fetched into the npx cache; pip tools get a venv with the pinned wheel. Returns where it lives."""
    t = get(name)
    ref = effective_ref(t)
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
    return [npx, "--yes", f"{t.source}@{effective_ref(t)}"]

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
    """Every pinned external track, read from TOOLS (never a second table). Offline: only the filesystem and the lock are read.
    `version` is the registry pin; `effective_version` is what is in use (the lock's ref when followed, the override if set)."""
    rows = []
    for t in TOOLS.values():
        ref, source = effective(t)
        entry = lock_entry(t.name)
        rows.append({"name": t.name, "command": command(t), "repo": t.source, "version": pinned_ref(t),
                     "installed": is_installed(t), "license": t.license, "produces": t.role,
                     "effective_version": ref, "effective_source": source, "lock": dict(entry) or None})
    return rows


def text_listing(rows: list[dict]) -> str:
    lines = ["trilhas externas (versão fixada em tools.py; o render determinístico não depende de nenhuma delas):"]
    for r in rows:
        estado = "sim" if r["installed"] else "não"
        lines.append(f"  {r['name']:<13} instalada: {estado:<4} versão fixada: {r['version']}")
        lines.append(f"    comando: {r['command']}  ({r['license']})")
        lines.append(f"    repo: {r['repo']}")
        lines.append(f"    produz: {r['produces']}")
        if r.get("effective_source") != "pin":
            lines.append(f"    em uso: {r['effective_version']} ({r['effective_source']})")
        lock = r.get("lock")
        if lock:
            quando = hostos.utc_stamp(lock["resolved_at"]) if lock.get("resolved_at") else "-"
            falha = (f", última tentativa falhou em {hostos.utc_stamp(lock['failed_at'])}"
                     if lock.get("status") == "failed" and lock.get("failed_at") else "")
            lines.append(f"    lock: {lock.get('mode')} {lock.get('ref', '-')} ({lock.get('status')}, {quando}{falha})")
    lines.append("instalada = checkout no cache de tools ($SIMPLICIO_TOOLS_DIR, padrão ~/.simplicio-video/tools); para trilhas npm, "
                 "o binário no PATH; para trilhas pip, o executável no venv da trilha. O lock (tools.lock.json, em "
                 "$SIMPLICIO_VIDEO_DATA) é o que `update` resolveu para cada trilha.")
    return "\n".join(lines)
