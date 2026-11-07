"""Pinned versions and install location for the external tracks: `montage` (OpenMontage), `opencut` (OpenCut),
`clone` (Hypit), `toonflow` (Toonflow), `moneyprinter` (MoneyPrinterTurbo), `matchcut` (match-cut), `instagram` (instagram-agent-skill), `busca` (TinyFish CLI) and
`voicestudio` (VoiceStudio), `rea-video` (rea-video), `video-to-skill` (video-to-skill) and `media fetch` (yt-dlp). `simplicio-video tools` lists the whole registry (text or --json).

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

The registry is the one place that names the tracks. Each `Tool` declares everything the other doors need to know about its track (the CLI
command, the verb that installs it, the system dependencies, whether `update` follows it, where its checkout lives, which sha256 table pins
its files, which setup the doctor judges, the read-only MCP call the smoke makes); `COMMANDS`, the doctor's `CLONE` and `DEPS`, its setup and
integrity checks and the smoke's `MCP_LEITURA` are derived from it, and tests/packaging/test_registro_trilhas.py walks TOOLS to prove that
every track is known to every door.
"""
from __future__ import annotations

import functools
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from . import hostos, paths, tools_lock


class ToolError(Exception):
    pass


class GitTimeout(ToolError):
    """A git that did not answer in time: it says nothing about the repository (a hang is transient)."""


@functools.lru_cache(maxsize=None)
def _video_use_pin() -> str:
    """The pin of video-use: VU_REF of the packaged setup.sh, the file that `edit setup` runs (the single source of it). Read when the
    pin of video-use is first asked for (`Tool.ref` runs it) and then kept: importing this module no longer reads the file, so a broken
    or missing setup.sh fails only what uses video-use, not `--help` and the other tracks. A failure is not kept: the next read tries again."""
    text = (paths.DATA_DIR / "tools" / "video-use" / "setup.sh").read_text(encoding="utf8")
    found = re.search(r"^VU_REF=([0-9a-f]{40})\b", text, re.MULTILINE)
    if not found:
        raise RuntimeError("data/tools/video-use/setup.sh sem VU_REF de 40 caracteres")
    return found.group(1)


NODE_MIN = (22, 15)  # @hypit/hypit "engines": node >= 22.15.0 (also the minimum of the hypit dependency in TOOLS)

_DEP = re.compile(r"(?P<name>[A-Za-z_][A-Za-z0-9_]*)(?:>=(?P<minimum>[0-9]+(?:\.[0-9]+)*))?(?P<optional>\?)?")


def parse_dep(spec: str) -> tuple[str, bool, tuple[int, ...] | None]:
    """(name, required, minimum version or None) of a dependency written as `name[>=a.b][?]`: `ffmpeg`, `docker?` (optional),
    `node>=22.15`. The name is a program on PATH (or a variable, SIMPLICIO_TTS_PY); the doctor decides how to look for it."""
    found = _DEP.fullmatch(spec)
    if not found:
        raise ValueError(f"dependência ilegível: {spec!r} (o formato é nome[>=a.b][?])")
    minimum = found.group("minimum")
    return found.group("name"), not found.group("optional"), tuple(int(x) for x in minimum.split(".")) if minimum else None


class _RefOrFunction:
    """The `ref` of a `Tool`: a string, or a function with no arguments that returns it (video-use reads its pin from setup.sh). The
    function runs each time `ref` is read (the one video-use uses, `_video_use_pin`, keeps its own cache). `ref` stays an ordinary field (`dataclasses.replace(t, ref=...)`)."""

    def __set_name__(self, owner, name):
        self._key = f"_{name}"

    def __get__(self, obj, owner=None):
        if obj is None:
            raise AttributeError("ref")  # no class-level default: the dataclass keeps `ref` a required field
        value = obj.__dict__[self._key]
        return value() if callable(value) else value

    def __set__(self, obj, value):
        obj.__dict__[self._key] = value


@dataclass(frozen=True)
class McpRead:
    """The one read-only call of the MCP tool of a track that scripts/smoke_trilhas.py makes (the smoke derives its table from this)."""
    param: str                       # the argument of the MCP function that carries the command ("args" or "acao")
    value: str | tuple[str, ...]     # what it carries: "status", "where", "--help"; a tuple is the list ("fetch",)
    needs_checkout: bool = True      # it reads the checkout: the smoke makes it only when the track is installed
    expect: str = "ok"               # "ok": the answer has ok true; "recusa": it must refuse (fetch with no URL: nothing is downloaded)


@dataclass(frozen=True)
class Tool:
    name: str
    kind: str          # "git", "npm" or "pip" (a wheel in its own venv)
    source: str        # git URL, npm package, or the home page of a pip project (its PyPI name is the tool name)
    ref: str = _RefOrFunction()  # pinned commit or version (a function with no arguments is called when it is read: see _RefOrFunction)
    license: str
    role: str
    command: str       # the CLI command that fronts the track: `simplicio-video <command>` (the first word is the parser's command and the MCP tool is `video.<it>`)
    marker: str = ""   # a file or folder that proves a git checkout is the right one
    note: str = ""
    sha256: str = ""   # pip tools: the sha256 of the pinned wheel, checked by pip --require-hashes
    pin_only: bool = False  # `update` never follows its upstream: the lock records the registry pin (video-use, video_to_skill)
    checkout_env: str | None = None  # the variable that holds a checkout kept OUTSIDE the tools cache (video-use: setup.sh), else ~/.cache/simplicio/<name>
    deps: tuple[str, ...] = ()  # system dependencies the doctor checks, `name[>=a.b][?]` (parse_dep): `ffmpeg`, `docker?` (optional), `node>=24`
    clone_verb: str | None = None  # the verb of `<command>` that installs a git track (`clone`, `setup`); None: the doctor shows the git commands
    setup_probe: tuple[str, str] | None = None  # (module, function) the doctor calls as function(tool, checkout) for the rows of the track's own setup
    integrity: tuple[str, str] | None = None  # (module, attribute) that holds {file: sha256} of the pinned files, read by the doctor (doctor_trilhas.lookup)
    checkout_probe: tuple[str, str] | None = None  # (module, function with no arguments) that says where the track looks for its checkout, when
    #                                                it is not `checkout_dir` (montage has its own search order)
    mcp_read: McpRead | None = None  # the read-only MCP call of the smoke

    def __post_init__(self) -> None:
        for spec in self.deps:
            parse_dep(spec)  # a dependency that does not parse is refused when the registry is built, not when the doctor runs


# The registry. The order is the order of `tools --json` and of the doctor's tracks. A pointer `(module, name)` (setup_probe, integrity,
# checkout_probe) names something in a module of this package that the doctor reads when it needs it (doctor_trilhas.lookup), so this module
# imports no track, not even lazily (the track modules import this one): the setup probes still live in doctor_trilhas, because the track
# modules are not ready to carry them yet, and move with their track.
TOOLS: dict[str, Tool] = {
    "openmontage": Tool("openmontage", "git", "https://github.com/calesthio/OpenMontage",
                        "9327439db69021ab4b0e2776729bf3b58fdb5a87", "AGPL-3.0",
                        "agentic production (Backlot, pipelines); runs as a separate program, never imported",
                        command="montage", marker="backlot", clone_verb="clone", deps=("ffmpeg",),
                        setup_probe=("doctor_trilhas", "setup_openmontage"), checkout_probe=("montage", "default_openmontage_dir"),
                        mcp_read=McpRead("args", "status --json")),
    "opencut": Tool("opencut", "git", "https://github.com/OpenCut-app/opencut-classic",
                    "cf5e79e919144200294fb9fed22a222592a0aeea", "MIT",
                    "manual finishing editor (web app on localhost)", command="opencut", marker="package.json",
                    note="opencut-classic is archived upstream; the OpenCut rewrite has no headless API yet",
                    clone_verb="clone", deps=("bun", "docker?"), setup_probe=("doctor_trilhas", "setup_opencut"),
                    mcp_read=McpRead("args", "where")),
    "hypit": Tool("hypit", "npm", "@hypit/hypit", "0.3.1", "Hypit license (modified Apache-2.0)",
                  "agentic video cloning; user-installed, never bundled or offered as a hosted service",
                  command="clone", note="its license forbids commercial redistribution and multi-tenant service without permission",
                  deps=(f"node>={'.'.join(map(str, NODE_MIN))}",),
                  # `clone --help` would pass through to Hypit (npx when it is not installed): the read-only status of the engine is asked instead
                  mcp_read=McpRead("args", "status --json")),
    "toonflow": Tool("toonflow", "git", "https://github.com/HBAI-Ltd/Toonflow-app",
                     "d2e94aca7b59659ff6b4ca15f03cf134ec7f0e1d", "MIT",
                     "open-source AI studio for short dramas, comic dramas and videos (Bun, web app on localhost); "
                     "runs as a separate program, never imported", command="toonflow", marker="package.json",
                     note="its server has no login and listens on 0.0.0.0:3000 (every interface): serve needs --lan",
                     clone_verb="clone", deps=("bun", "docker?"), setup_probe=("doctor_trilhas", "setup_toonflow"),
                     mcp_read=McpRead("args", "where")),
    "moneyprinter": Tool("moneyprinter", "git", "https://github.com/harry0703/MoneyPrinterTurbo",
                         "4b7b9657647bdb149715354269eec7e4dbad4a7a", "MIT",
                         "topic-to-short-video generator (LLM script, synthesized voice, stock footage; Python 3.11+, "
                         "Streamlit WebUI and FastAPI); runs as a separate program, never imported",
                         command="moneyprinter", marker="config.example.toml",
                         clone_verb="clone", deps=("ffmpeg",), setup_probe=("doctor_trilhas", "setup_moneyprinter"),
                         mcp_read=McpRead("args", "status"),
                         note="it calls third-party services with their own terms (LLM providers, TTS, stock footage such as "
                              "Pexels, Pixabay and Coverr) and needs your own API keys in its config.toml; the terms were not "
                              "reviewed here. Its API config listens on 0.0.0.0 by default and the WebUI has no login: serve "
                              "forces 127.0.0.1 unless --lan"),
    "matchcut": Tool("matchcut", "git", "https://github.com/Sac-Y/match-cut",
                     "b51c98f5c795b046ceb1c69396368dbabd88d5d9", "MIT",
                     "agent skill (SKILL.md, scripts, references) for product films in the match-cut relay style; "
                     "the engine only downloads the pinned commit and points at it, it never runs the skill",
                     command="matchcut", marker="SKILL.md",
                     clone_verb="clone", deps=("ffmpeg",), integrity=("matchcut", "PINNED_SHA256"),
                     setup_probe=("doctor_trilhas", "setup_matchcut"), mcp_read=McpRead("args", "status"),
                     note="the skill is used from Claude Code or Codex and needs a Renoise sign-in (the user's own "
                          "account) and paid Renoise credits; the engine never calls Renoise and never asks for a secret"),
    "instagram": Tool("instagram", "git", "https://github.com/Jakeschincariol/instagram-agent-skill",
                      "d03c56bb598be770c60b201f94237e5d1a4268a6", "MIT",
                      "thirteen agent skills (SKILL.md prompts) and six local standard-library scripts for Instagram Reels, captions and "
                      "drafts; the engine downloads the pinned commit, lists the skills and runs only those six scripts, after checking "
                      "the sha256 of each one", command="instagram", marker="skills/ig-reel/hookscore.py",
                      clone_verb="clone", mcp_read=McpRead("acao", "status"),
                      # no `deps`, no `setup_probe` and no `integrity` on purpose: it runs six scripts with the system Python, there is nothing to
                      # set up, and the doctor must not import its module (`simplicio-video instagram status` checks the sha256 of its scripts)
                      note="the heuristics (regexes, word lexicon, 26 hook formulas) are in English and were measured by the author on 74 "
                           "YouTube Shorts hooks (AUC 0.83 to catch bad hooks, 0.56 to pick winners): in Portuguese they score badly or "
                           "are ignored. The skills are prompts for an agent, not code. Nothing here posts or publishes: the engine never "
                           "posts, the skills write and the user posts"),
    "voicestudio": Tool("voicestudio", "git", "https://github.com/debpalash/VoiceStudio",
                         "beeaae08204f0de5f49d4a087ef2b0ea8fecfcb9", "AGPL-3.0",
                         "local voice studio: cloned/designed voice profiles, TTS and transcription over a loopback "
                         "OpenAI-compatible API and an MCP server on :3900; runs as a separate program, never imported",
                         command="voicestudio", marker="package.json", deps=("bun?",),
                         mcp_read=McpRead("args", "status", needs_checkout=False),
                         # no `clone_verb` and no `setup_probe`: the app is installed by its own installer, the doctor shows the git commands
                         note="pin = release v0.5.7 (published 2026-10-26), commit beaae08 read from the GitHub API on "
                              "2026-10-27. The desktop app is installed with "
                              "`curl -fsSL https://voicestudio.sh/install | sh`; from source the alternative is "
                              "`bun install && bun run dev` (this pin clones that source checkout). Loopback needs no "
                              "credential; the app is only reached over local HTTP (AGPL-3.0, never vendored)"),
    "video-use": Tool("video-use", "git", "https://github.com/browser-use/video-use",
                        _video_use_pin, "MIT",  # read when asked for (Tool.ref), not at import
                        "EDL editing over any MP4: word-accurate cuts, subtitles, overlays and filmstrip review; "
                        "the agent decides the EDL, ffmpeg executes it", command="edit", marker="helpers/render.py",
                        clone_verb="setup", deps=("ffmpeg", "SIMPLICIO_TTS_PY"), pin_only=True, checkout_env="VIDEO_USE_DIR",
                        mcp_read=McpRead("args", "--help", needs_checkout=False),
                        note="pinned by the video-use setup.sh (data/tools/video-use) (23/09/2026); the checkout lives in "
                             "~/.cache/simplicio/video-use, not in the tools cache"),
    "tinyfish": Tool("tinyfish", "npm", "@tiny-fish/cli", "0.57.0", "not declared in the npm package (no license field, no LICENSE file; read 2026-11-05 on 0.57.0)",
                     "web search and page fetch for research (`simplicio-video busca`); installed by the user, never bundled and never installed by the engine",
                     command="busca", deps=("node>=24", "npm"),  # the @tiny-fish/cli package declares Node >= 24
                     mcp_read=McpRead("acao", "status"),
                     note="the engine uses only `search query`, `fetch content get`, `auth status` and `--version`: agent, browser and monitor (browser "
                          "automation, metered by step or minute) are out of scope. The package declares Node >= 24. The query or URL goes to a third "
                          "party (TinyFish): the engine refuses secrets and, unless told otherwise, personal data"),
    "yt-dlp": Tool("yt-dlp", "pip", "https://github.com/yt-dlp/yt-dlp", "2026.10.26", "Unlicense",
                   "downloads one public video page to a local MP4 (`simplicio-video media fetch`); the engine never logs in, "
                   "never reads browser cookies and never downloads a playlist",
                   command="media fetch", deps=("ffmpeg?",), mcp_read=McpRead("args", ("fetch",), needs_checkout=False, expect="recusa"),
                   note="installed in its own venv under the tools cache, never on the global PATH; the wheel has no required "
                        "dependencies and is checked by sha256 (pip --require-hashes). The download needs --autorizo: the user "
                        "confirms the right to use the file, and the engine does not verify it. Platforms such as Instagram "
                        "restrict downloads in their own terms; that responsibility is the user's",
                   sha256="a05c5b5d8562f7e8a62f5334348b406af4930d56d3a65f8021d14af0e22339ae"),
    "rea_video": Tool("rea_video", "git", "https://github.com/JuneYaooo/rea-video",
                      "36e02ddf1ffc287bd760d816c132027598f2e4c0",
                      "MIT, declarada no pyproject.toml; o commit fixado não traz arquivo LICENSE",
                      "reverse-engineers a video shot by shot (live action, AI, 3D, code render, mixed) and plans a remake; "
                      "runs as a separate program in a venv of its own, never imported", command="rea-video", marker="rea_video/cli.py",
                      clone_verb="clone", deps=("ffmpeg",), setup_probe=("doctor_trilhas", "setup_rea_video"),
                      mcp_read=McpRead("args", "where"),
                      note="the pin is the default branch of the upstream repository as read on 2026-11-04. Without --vlm nothing "
                           "leaves the machine; with --vlm the frames go to the vision model provider the user configures (a third "
                           "party). The first analysis downloads about 67 MB of voice model. `setup` installs with pip without "
                           "hashes: the upstream has no lock file"),
    "video_to_skill": Tool("video_to_skill", "git", "https://github.com/brenoepics/video-to-skill",
                           "c1a1b905da6a252077ace0657e8ea49cb785e7c3", "MIT",
                           "turns a video into an installable agent skill (by Breno Epics): an agent SKILL.md plus a local Rust extractor (`vts-extract`: "
                           "transcript, shots, keyframes, skill package); the engine pins the commit and the extractor "
                           "release, and runs the extractor only as a separate program", command="video-to-skill", marker="SKILL.md",
                           clone_verb="clone", pin_only=True, integrity=("video_to_skill", "PINS.files"),
                           deps=("ffmpeg?",),  # the upstream brings its own with `check --fix --yes`, typed by the user
                           setup_probe=("doctor_trilhas", "setup_video_to_skill"), mcp_read=McpRead("args", "status"),
                           note="pin = tag v0.3.0 (commit c1a1b90), read on 2026-11-06. The extractor binary comes from the upstream release "
                                "(sha256 pinned per platform in data/video_to_skill/pins.json, checked before it runs); its own dependencies "
                                "(ffmpeg, yt-dlp, whisper and VAD models) are downloaded by the upstream `check --fix --yes`, which only you "
                                "run in a terminal, never the engine. Verifying a generated skill runs video-derived commands: that is the "
                                "agent's job under the upstream's OS sandbox, outside the engine's guarantees. Never followed by `update`: the "
                                "binary and SKILL.md are pinned together"),
}


# CLI command that fronts each track, by track name: derived from TOOLS (the `command` field), never a second table.
COMMANDS: dict[str, str] = {name: t.command for name, t in TOOLS.items()}


def get(name: str) -> Tool:
    try:
        return TOOLS[name]
    except KeyError:
        raise ToolError(f"ferramenta desconhecida: {name} ({', '.join(TOOLS)})") from None


def override_var(t: Tool) -> str:
    """The variable that overrides the pin of a track: SIMPLICIO_<NAME>_REF, the name upper-cased as it is (`SIMPLICIO_YT-DLP_REF`)."""
    return f"SIMPLICIO_{t.name.upper()}_REF"


def pinned_ref(t: Tool) -> str:
    return os.environ.get(override_var(t)) or t.ref


def lock_entry(name: str) -> dict:
    """The lock entry of a track, or {} when there is none (a lock that is not usable is reported by `doctor`, not here)."""
    try:
        return tools_lock.read_lock()["tools"].get(name, {})
    except tools_lock.LockInvalid:
        return {}


def effective(t: Tool) -> tuple[str, str]:
    """(ref, source) of what the track really uses: the override SIMPLICIO_<NAME>_REF, else the ref `update` resolved for a
    followed track (the lock keeps the ref in place even after a failed update), else the registry pin."""
    override = os.environ.get(override_var(t))
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
    """$SIMPLICIO_TOOLS_DIR, else ~/.simplicio-video/tools under hostos.home_absoluta() (HOME, then USERPROFILE). Without a usable
    home it raises hostos.SemCasa: the clones never land in the folder you are in."""
    explicito = os.environ.get("SIMPLICIO_TOOLS_DIR")
    return Path(explicito).expanduser() if explicito else hostos.home_absoluta() / ".simplicio-video" / "tools"


def checkout_dir(t: Tool) -> Path:
    """Where a git track lives. A track with `checkout_env` (video-use: data/tools/video-use/setup.sh keeps its checkout outside the tools
    cache, and the update moves that one) lives where that variable says, taken as it is, as bash takes it in setup.sh (no ~ expansion inside a
    variable's value); the default is ~/.cache/simplicio/<name> under hostos.home_absoluta (HOME first), the same home the lock uses; with no
    usable home it raises hostos.SemCasa (a relative `~` would make a folder in the cwd)."""
    if t.checkout_env:
        return Path(os.environ.get(t.checkout_env) or hostos.home_absoluta(t.checkout_env) / ".cache" / "simplicio" / t.name)
    env = os.environ.get(f"{t.name.upper()}_DIR") or os.environ.get(f"SIMPLICIO_{t.name.upper()}_DIR")
    return Path(env).expanduser() if env else tools_dir() / t.name


def _git(*args: str, cwd: Path | None = None, timeout: float | None = None) -> str:
    """The implementation of `git`, and the name the tests replace (tests/conftest.py makes it refuse a real git in every unit test)."""
    exe = shutil.which("git")
    if not exe:
        raise ToolError("git não encontrado no PATH")
    if timeout is None:
        r = subprocess.run([exe, *args], cwd=cwd, stdin=subprocess.DEVNULL, capture_output=True, text=True)
    else:
        try:
            r = hostos.run_limitado([exe, *args], cwd=cwd, timeout=timeout)
        except subprocess.TimeoutExpired:
            raise GitTimeout(f"git {' '.join(args[:2])}: tempo esgotado ({timeout:g} s)") from None
    if r.returncode:
        raise ToolError(f"git {' '.join(args[:2])}: {r.stderr.strip()[-300:]}")
    return r.stdout.strip()


def git(*args: str, cwd: Path | None = None, timeout: float | None = None) -> str:
    """One git command (the public name: other modules call this, not `_git`). With `timeout` (seconds) a git that hangs is a
    GitTimeout and its whole process tree is killed; without it the command runs as long as it takes (a clone). A failing git is a
    ToolError.

    It goes through the module-level `_git` at call time, so a test that replaces `tools._git` also covers every caller of this one;
    only the options the caller gave are passed on, so a fake with a narrower signature keeps working."""
    options: dict = {}
    if cwd is not None:
        options["cwd"] = cwd
    if timeout is not None:
        options["timeout"] = timeout
    return _git(*args, **options)


def git_head(d: Path) -> str | None:
    """The commit that is really in the checkout `d` (the pin is only what it should be), or None: no `.git` there (git would answer
    with the parent repository: not this checkout) or a git that fails."""
    if not (d / ".git").exists():
        return None
    try:
        return git("rev-parse", "HEAD", cwd=d)
    except ToolError:
        return None


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


def pip_version(name: str) -> str | None:
    """The version pip installed in the venv of a pip tool: the Version of its dist-info, read as a file (no process starts)."""
    t = get(name)
    venv = checkout_dir(t) / "venv"
    if t.kind != "pip" or not venv.is_dir():
        return None
    sites = [venv / "Lib" / "site-packages"] if os.name == "nt" else sorted((venv / "lib").glob("python*/site-packages"))
    stem = t.name.replace("-", "_")
    for site in sites:
        for info in sorted(site.glob(f"{stem}-*.dist-info")):
            try:
                metadata = (info / "METADATA").read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for line in metadata.splitlines():
                if line.startswith("Version:"):
                    return line.partition(":")[2].strip() or None
    return None


def run_subprocess(argv, cwd=None) -> "subprocess.CompletedProcess":
    """The default runner: a missing program is a failed command (rc 127), never an OSError out of here."""
    try:
        return subprocess.run([str(a) for a in argv], cwd=str(cwd) if cwd else None, stdin=subprocess.DEVNULL, capture_output=True, text=True,
                              encoding="utf-8", errors="replace")
    except OSError as exc:
        return subprocess.CompletedProcess(list(argv), 127, "", str(exc))


def motivo(done) -> str:
    return (done.stderr or done.stdout or "").strip()[-300:]


def install_pip_version(t: Tool, version: str, sha256: str, run=None) -> str:
    """A pip tool at `version`: a venv of its own under the tools cache, and the wheel installed with its sha256 checked
    (--require-hashes: pip refuses anything else). `run(argv, cwd)` runs the commands; the update passes its own (tests: fakes)."""
    run = run or run_subprocess
    d = checkout_dir(t)
    d.mkdir(parents=True, exist_ok=True)
    venv = d / "venv"
    if not _venv_python(venv).is_file():
        r = run([sys.executable, "-m", "venv", str(venv)], None)
        if r.returncode:
            raise ToolError(f"venv de {t.name}: {motivo(r)}")
    requisitos = d / "requirements.txt"
    requisitos.write_text(f"{t.name}=={version} --hash=sha256:{sha256}\n", encoding="utf8")
    r = run([str(_venv_python(venv)), "-m", "pip", "install", "--quiet", "--disable-pip-version-check",
             "--require-hashes", "-r", str(requisitos)], None)
    if r.returncode:
        raise ToolError(f"pip install {t.name}=={version}: {motivo(r)}")
    exe = pip_binary(t.name)
    if exe is None:
        raise ToolError(f"{t.name}: o pip terminou, mas o executável não apareceu em {venv}")
    return str(exe)


def _install_pip(t: Tool) -> str:
    """A pip tool at the version in use (the lock's, when followed; the registry's otherwise), with its sha256 checked."""
    version, digest, source = effective_pip(t)
    if source == "override" and version != t.ref:
        raise ToolError(f"{t.name}: o override de versão ({override_var(t)}) não tem hash neste registro; a versão e o sha256 andam juntos em tools.py")
    return install_pip_version(t, version, digest)


def _ref_de_instalacao(t: Tool) -> str:
    """The commit (git) or the version (npm) that install() passes to the program. It is checked first, with the pattern the lock uses,
    so that an override such as `--force` never reaches git or npx as an option (a checkout with it would discard local edits). The
    message does not show the value: it may be a token typed by mistake."""
    ref = effective_ref(t)
    if t.kind == "git":
        valido = tools_lock.GIT_REF.fullmatch(ref)
    elif t.kind == "npm":
        valido = tools_lock.NPM_VERSION.fullmatch(ref)
    else:
        return ref  # pip: effective_pip checks the version against the registry before anything runs
    if not valido:
        raise ToolError(f"{t.name}: o commit ou a versão em uso não é válido ({override_var(t)} ou o lock); "
                        "recuso sem rodar o git nem o npm")
    return ref


def install(name: str, *, dir: Path | None = None) -> str:
    """Install a tool at its pinned version. Git tools are cloned and checked out at the pinned commit; npm tools are
    fetched into the npx cache; pip tools get a venv with the pinned wheel. Returns where it lives. Without a usable home
    there is nowhere to put a checkout: a refusal (ToolError), before any folder is made.

    `dir` (git tools only) is where the checkout goes, `~` expanded like the variables are: the location then comes from it alone,
    and `{NAME}_DIR`, `SIMPLICIO_{NAME}_DIR`, `SIMPLICIO_TOOLS_DIR` (and video-use's VIDEO_USE_DIR) are neither read nor written.
    The pin override (SIMPLICIO_{NAME}_REF) still applies. Without `dir`, the location is `checkout_dir`, as it always was."""
    try:
        return _install(name, dir)
    except hostos.SemCasa as exc:
        raise ToolError(str(exc)) from None


def _install(name: str, dir: Path | None = None) -> str:
    t = get(name)
    if dir is not None and t.kind != "git":
        raise ToolError(f"{t.name}: `dir` só vale para trilhas git (uma trilha {t.kind} não tem checkout para pôr ali)")
    if t.kind == "pip":
        return _install_pip(t)
    ref = _ref_de_instalacao(t)
    if t.kind == "npm":
        npx = shutil.which("npx")
        if not npx:
            raise ToolError("npx não encontrado no PATH (Node >= 18)")
        r = subprocess.run([npx, "--yes", f"{t.source}@{ref}", "--version"], stdin=subprocess.DEVNULL, capture_output=True, text=True)
        if r.returncode:
            raise ToolError(f"{t.source}@{ref}: {r.stderr.strip()[-300:]}")
        return f"npx {t.source}@{ref}"
    d = Path(dir).expanduser() if dir is not None else checkout_dir(t)
    if not (d / ".git").is_dir():
        d.parent.mkdir(parents=True, exist_ok=True)
        _git("clone", "--filter=blob:none", "--", t.source, str(d))  # `--`: a relative folder that starts with `-` is not an option
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
        raise ToolError(f"nem `{t.name}` nem `npx` foram encontrados no PATH. Instale o Node (>= 22.15).")
    ref = _ref_de_instalacao(t)
    return [npx, "--yes", f"{t.source}@{ref}"]

def command(t: Tool) -> str:
    """The CLI command that fronts a track (its `command` field)."""
    return f"simplicio-video {t.command}"


NPX_TRACKS = ("hypit",)  # npm tracks that run through `npm_command` (a PATH binary, else npx at the pin); the others need a binary


def node_version() -> tuple[int, ...] | None:
    """The version of the `node` on PATH, e.g. (22, 15, 0). Local only: runs `node --version`, no network."""
    exe = shutil.which("node")
    if not exe:
        return None
    try:
        r = subprocess.run([exe, "--version"], stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=15,
                           env={"PATH": os.environ.get("PATH", "")})
    except (OSError, subprocess.SubprocessError):
        return None
    m = re.match(r"v?(\d+)\.(\d+)\.(\d+)", (r.stdout or "").strip())
    return tuple(int(x) for x in m.groups()) if r.returncode == 0 and m else None


def npx_ready() -> bool:
    """Can npx run an npm track? npx on PATH and Node >= NODE_MIN. Offline-safe: nothing is downloaded or run."""
    v = node_version()
    return shutil.which("npx") is not None and v is not None and v[:2] >= NODE_MIN


def install_source(t: Tool) -> str | None:
    """For an npm track: "path" (a binary on PATH), "npx" (runnable through npx at the pin) or None. Other kinds: None."""
    if t.kind != "npm":
        return None
    if shutil.which(t.name):
        return "path"
    return "npx" if t.name in NPX_TRACKS and npx_ready() else None


def is_installed(t: Tool) -> bool:
    """Git tools: the pinned checkout in the tools cache. pip tools: the executable in their venv. npm tools: the binary
    on PATH, or npx at the pinned version when npx and Node >= 22.15 are there (as `status` does)."""
    if t.kind == "git":
        return find(t.name) is not None
    if t.kind == "pip":
        return pip_binary(t.name) is not None
    return install_source(t) is not None


def listing() -> list[dict]:
    """Every pinned external track, read from TOOLS (never a second table). Offline: only the filesystem and the lock are read.
    `version` is the registry pin; `effective_version` is what is in use (the lock's ref when followed, the override if set)."""
    rows = []
    for t in TOOLS.values():
        ref, source = effective(t)
        entry = lock_entry(t.name)
        rows.append({"name": t.name, "command": command(t), "repo": t.source, "version": pinned_ref(t),
                     "installed": is_installed(t), "source": install_source(t), "license": t.license, "produces": t.role,
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
