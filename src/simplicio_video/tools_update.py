"""`simplicio-video update` for the external tracks (issue #150): follow each track's upstream, or keep the registry pins (--pin).

* git (openmontage, opencut, toonflow, moneyprinter, matchcut, voicestudio): `git ls-remote --symref <repo> HEAD` gives the
  default branch (main or master) and its commit. The checkout is fetched and moved there, and only when the registry marker of the
  track is still in place; if it is not, the previous commit is put back.
* video-use is pinned in every mode: its pin is VU_REF of the packaged setup.sh, the commit that `edit setup` checks out, so the
  update never moves it to upstream and the lock records the pin (mode "pin").
* npm (hypit, tinyfish): `npm view <package> version` gives the latest version, checked with `npx <package>@<version> --version`.
* pip (yt-dlp): the PyPI JSON gives the latest version and the sha256 of its universal wheel; pip checks that hash (--require-hashes).

A failing track keeps the checkout it has, is reported, and stops neither the other tracks nor the package update. An explicit
override (SIMPLICIO_<NAME>_REF) always wins and is never refreshed. Every command and every network read goes through an `Io`, so the
tests run the whole flow with fakes. The lock (tools_lock.py) records what was resolved and what is in use.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
import urllib.request
from pathlib import Path
from typing import Any, Callable, Optional

from . import hostos, tools, tools_lock

MODES = ("follow", "pin")
PYPI_JSON = "https://pypi.org/pypi/{name}/json"
MAX_JSON = 5 * 1024 * 1024
READ_TIMEOUT_S = 20  # one read of the network (ls-remote, npm view): past it, the track is reported, the doctor goes on
_HEAD_REF = re.compile(r"ref: refs/heads/([A-Za-z0-9._/-]{1,100})\s+HEAD")
_HEAD_SHA = re.compile(r"([0-9a-f]{40})\s+HEAD")
_NPM_VERSION = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z.-]{1,40})?")
_PIP_VERSION = re.compile(r"[0-9]+(?:\.[0-9]+){1,3}")
_SHA256 = re.compile(r"[0-9a-f]{64}")
# what a track failure can raise: the tools errors, the OS (a missing program, a dead network), and bad answers from the network
FAILURES = (tools.ToolError, hostos.SemCasa, OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError)


def _offline() -> bool:
    return os.environ.get("SIMPLICIO_OFFLINE", "").strip().lower() in ("1", "true", "yes", "on")


def _fetch_json(url: str) -> Any:
    """The PyPI document over https, read in full up to MAX_JSON. Nothing else is fetched this way."""
    if not url.startswith("https://"):
        raise ValueError(f"recusando uma url que não é https: {url}")
    request = urllib.request.Request(url, headers={"User-Agent": "simplicio-video-update", "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=READ_TIMEOUT_S) as response:
        raw = response.read(MAX_JSON + 1)
    if len(raw) > MAX_JSON:
        raise ValueError("a resposta do PyPI é grande demais")
    return json.loads(raw.decode("utf-8"))


def _run_leitura(argv, cwd=None):
    """One read of the network (git ls-remote, npm view): bounded in time, and never asking for a password on the terminal.
    A read past READ_TIMEOUT_S raises subprocess.TimeoutExpired, which the callers count as a failure of that track."""
    env = dict(os.environ)
    env["GIT_TERMINAL_PROMPT"] = "0"
    try:
        return hostos.run_limitado(argv, cwd=cwd, env=env, timeout=READ_TIMEOUT_S)  # a timeout kills git AND its git-remote-https
    except OSError as exc:
        return subprocess.CompletedProcess(list(argv), 127, "", str(exc))


class Io:
    """The side effects of an update: the commands (`run`, a subprocess-like runner; `read` for the reads of the upstream, bounded in
    time), the PyPI document (`fetch_json`), the clock, the lookup of a program (`which`), and whether the network may be used at all.
    The tests pass fakes for all of them. A fake `run` also serves the reads, unless `read` is given."""

    def __init__(self, *, network: bool = True, run: Optional[Callable] = None, fetch_json: Optional[Callable] = None,
                 now: Optional[Callable[[], int]] = None, which: Optional[Callable] = None,
                 read: Optional[Callable] = None) -> None:
        self.network = network
        self.run = run or tools._run_subprocess
        self.read = read or (run if run is not None else _run_leitura)
        self.fetch_json = fetch_json or _fetch_json
        self.now = now or (lambda: int(time.time()))
        self.which = which or shutil.which


def live_io() -> Io:
    """The real thing. SIMPLICIO_OFFLINE=1 blocks the network: each read that needs it then fails as a track failure."""
    return Io(network=not _offline())


def _need_network(io: Io, what: str) -> None:
    if not io.network:
        raise OSError(f"SIMPLICIO_OFFLINE=1: rede bloqueada ({what})")


def _must(done, what: str):
    if done.returncode != 0:
        raise tools.ToolError(f"{what}: {tools._motivo(done) or f'código {done.returncode}'}")
    return done


# --- what upstream says is the latest --------------------------------------------------------------------------------


def resolve_git(t: tools.Tool, io: Io) -> dict:
    """{ref: the commit of the default branch, branch: its name} from one read of the remote (no clone)."""
    _need_network(io, f"git ls-remote {t.source}")
    done = _must(io.read(["git", "ls-remote", "--symref", t.source, "HEAD"], None), f"git ls-remote {t.source}")
    branch, sha = None, None
    for line in (done.stdout or "").splitlines():
        line = line.strip()
        found = _HEAD_REF.fullmatch(line)
        if found:
            branch = found.group(1)
        found = _HEAD_SHA.fullmatch(line)
        if found:
            sha = found.group(1)
    if not sha:
        raise tools.ToolError(f"git ls-remote {t.source}: não achei o commit de HEAD")
    return {"ref": sha, "branch": branch or "HEAD"}


def resolve_npm(t: tools.Tool, io: Io) -> dict:
    _need_network(io, f"npm view {t.source}")
    npm = io.which("npm")
    if not npm:
        raise tools.ToolError("npm não encontrado no PATH (Node >= 18)")
    done = _must(io.read([npm, "view", t.source, "version"], None), f"npm view {t.source}")
    version = (done.stdout or "").strip()
    if not _NPM_VERSION.fullmatch(version):
        raise tools.ToolError(f"npm view {t.source} não devolveu uma versão: {version[:40]!r}")
    return {"ref": version}


def resolve_pip(t: tools.Tool, io: Io) -> dict:
    """The latest release of the PyPI project and the sha256 of its universal wheel (`py3-none-any`)."""
    _need_network(io, "PyPI")
    document = io.fetch_json(PYPI_JSON.format(name=t.name))
    if not isinstance(document, dict):
        raise tools.ToolError("a resposta do PyPI não é um objeto JSON")
    version = (document.get("info") or {}).get("version")
    if not isinstance(version, str) or not _PIP_VERSION.fullmatch(version):
        raise tools.ToolError(f"PyPI: versão inválida {str(version)[:40]!r}")
    wheel = f"{t.name.replace('-', '_')}-{version}-py3-none-any.whl"
    for file in document.get("urls") or []:
        if isinstance(file, dict) and file.get("packagetype") == "bdist_wheel" and file.get("filename") == wheel:
            digest = (file.get("digests") or {}).get("sha256")
            if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
                raise tools.ToolError(f"PyPI: o wheel {wheel} não traz um sha256 válido")
            return {"ref": version, "sha256": digest}
    raise tools.ToolError(f"PyPI: não achei o wheel {wheel}")


def pin_only(t: tools.Tool) -> bool:
    """video-use never follows its upstream: the checkout must stay the commit `edit setup` makes (VU_REF of setup.sh)."""
    return t.name == "video-use"


def resolve(t: tools.Tool, io: Io) -> dict:
    if pin_only(t):
        return pin_target(t)
    if t.kind == "git":
        return resolve_git(t, io)
    if t.kind == "npm":
        return resolve_npm(t, io)
    return resolve_pip(t, io)


def pin_target(t: tools.Tool) -> dict:
    """What `--pin` asks for: the registry pin (and its sha256, for a pip track)."""
    if t.kind == "pip":
        return {"ref": t.ref, "sha256": t.sha256}
    return {"ref": t.ref}


def checkout_for(t: tools.Tool) -> Path:
    """Where a git track lives. video-use's checkout is kept by data/tools/video-use/setup.sh (VIDEO_USE_DIR, else ~/.cache), not the
    tools cache: the update moves that one, and the registry marker tells it apart. VIDEO_USE_DIR is taken as it is, as bash takes it
    in setup.sh (no ~ expansion inside a variable's value); the default is ~/.cache/simplicio/video-use under hostos.home_absoluta (HOME
    first), the same home the lock uses; with no usable home it raises hostos.SemCasa (a relative `~` would make a folder in the cwd)."""
    if t.name == "video-use":
        return Path(os.environ.get("VIDEO_USE_DIR") or hostos.home_absoluta("VIDEO_USE_DIR") / ".cache" / "simplicio" / "video-use")
    return tools.checkout_dir(t)


# --- moving a track ---------------------------------------------------------------------------------------------------


def apply_git(t: tools.Tool, sha: str, io: Io) -> None:
    """Fetch `sha` and check it out detached. A missing registry marker after the checkout puts the previous commit back."""
    _need_network(io, f"git fetch {t.source}")
    d = checkout_for(t)
    if not (d / ".git").is_dir():
        d.parent.mkdir(parents=True, exist_ok=True)
        _must(io.run(["git", "clone", "--filter=blob:none", t.source, str(d)], None), f"git clone {t.source}")
    head = io.run(["git", "-C", str(d), "rev-parse", "HEAD"], None)
    before = (head.stdout or "").strip() if head.returncode == 0 else ""
    if len(sha) < 40:  # a registry pin may keep a short commit (video-use): fetch the branches, then name the full commit
        _must(io.run(["git", "-C", str(d), "fetch", "--quiet", "origin"], None), "git fetch")
        sha = _must(io.run(["git", "-C", str(d), "rev-parse", "--verify", "--quiet", f"{sha}^{{commit}}"], None),
                    f"git rev-parse {sha}").stdout.strip()
    else:
        _must(io.run(["git", "-C", str(d), "fetch", "--quiet", "origin", sha], None), f"git fetch {sha[:12]}")
    _must(io.run(["git", "-C", str(d), "checkout", "--quiet", "--detach", sha], None), f"git checkout {sha[:12]}")
    if not (d / t.marker).exists():
        if before:
            io.run(["git", "-C", str(d), "checkout", "--quiet", "--detach", before], None)
        raise tools.ToolError(f"o commit {sha[:12]} não tem {t.marker}: a trilha mudou de layout; mantive o anterior")


def apply_npm(t: tools.Tool, version: str, io: Io) -> None:
    _need_network(io, f"npx {t.source}")
    npx = io.which("npx")
    if not npx:
        raise tools.ToolError("npx não encontrado no PATH (Node >= 18)")
    _must(io.run([npx, "--yes", f"{t.source}@{version}", "--version"], None), f"npx {t.source}@{version}")


def apply_pip(t: tools.Tool, version: str, digest: str, io: Io) -> None:
    _need_network(io, "pip")
    tools.install_pip_version(t, version, digest, run=io.run)


def _in_place(t: tools.Tool, previous: Optional[dict], target: dict, mode: str) -> bool:
    """True when the track is already at the target (same mode, same ref, last attempt ok, and the files are there): nothing moves."""
    if not previous or previous.get("status") != "ok" or previous.get("mode") != mode:
        return False
    if not _same_ref(t, previous.get("ref") or "", target["ref"]):
        return False
    if t.kind == "git":
        d = checkout_for(t)
        return (d / ".git").is_dir() and (d / t.marker).exists()
    if t.kind == "pip":
        return previous.get("sha256") == target.get("sha256") and tools.pip_binary(t.name) is not None
    return True  # npm: the version in the lock is what npx runs; it is verified when it is moved


def refresh(t: tools.Tool, mode: str, previous: Optional[dict], io: Io) -> tuple[dict, str, str]:
    """(lock entry, outcome, the ref before). Outcome: 'updated', 'same' or 'failed'. A failure keeps the checkout that is in place:
    the entry keeps its ref and records the error, so the lock says what is really there."""
    mode = "pin" if pin_only(t) else mode  # video-use: the lock records the pin whatever the mode asked
    now = io.now()
    before = (previous or {}).get("ref") or ""
    try:
        target = pin_target(t) if mode == "pin" else resolve(t, io)
        if _in_place(t, previous, target, mode):
            outcome = "same"
        else:
            if t.kind == "git":
                apply_git(t, target["ref"], io)
            elif t.kind == "npm":
                apply_npm(t, target["ref"], io)
            else:
                apply_pip(t, target["ref"], target["sha256"], io)
            outcome = "updated"
        entry = {"kind": t.kind, "source": t.source, "mode": mode, "status": "ok", "ref": target["ref"], "resolved_at": now}
        if "branch" in target:
            entry["branch"] = target["branch"]
        if "sha256" in target:
            entry["sha256"] = target["sha256"]
        return entry, outcome, before
    except FAILURES as exc:
        entry = {"kind": t.kind, "source": t.source, "mode": mode, "status": "failed", "failed_at": now,
                 "error": (str(exc) or type(exc).__name__)[:tools_lock.MAX_TEXT]}
        if previous and previous.get("ref"):
            entry["ref"] = previous["ref"]
            for key in ("branch", "sha256"):
                if previous.get(key):
                    entry[key] = previous[key]
        return entry, "failed", before


def _override(t: tools.Tool) -> Optional[str]:
    return os.environ.get(f"SIMPLICIO_{t.name.upper()}_REF") or None


def apply_all(doc: dict, mode: str, io: Io, lock_file: Optional[Path] = None) -> tuple[list[str], int]:
    """Moves (follow) or pins every track, then writes the lock. Returns (the lines to show, how many tracks failed)."""
    now = io.now()
    old = doc.get("tools", {})
    tracks: dict = {}
    lines: list[str] = []
    failed = 0
    for t in tools.TOOLS.values():
        override = _override(t)
        if override:
            tracks[t.name] = {"kind": t.kind, "source": t.source, "mode": "override", "status": "ok", "ref": override,
                              "resolved_at": now}
            lines.append(f"  {t.name:<13} fixada por SIMPLICIO_{t.name.upper()}_REF={override}: não mexi")
            continue
        entry, outcome, before = refresh(t, mode, old.get(t.name), io)
        tracks[t.name] = entry
        if outcome == "failed":
            failed += 1
            kept = f"; mantive {entry['ref']}" if entry.get("ref") else ""
            lines.append(f"  {t.name:<13} FALHOU: {entry['error']}{kept}")
        elif outcome == "updated":
            lines.append(f"  {t.name:<13} atualizada: {before or '(nova)'} -> {entry['ref']}")
        else:
            lines.append(f"  {t.name:<13} em dia: {entry['ref']}")
    try:
        tools_lock.write_lock({"schema": tools_lock.SCHEMA, "updated_at": now, "tools": tracks}, lock_file)
    except (OSError, hostos.SemCasa, tools_lock.LockInvalid) as exc:
        lines.append(f"  o lock não foi gravado ({exc}); a saída acima é o que aconteceu")
    return lines, failed


# --- what would happen (--check and --dry-run write nothing) ----------------------------------------------------------


def _same_ref(t: tools.Tool, current: str, target: str) -> bool:
    if t.kind == "git":  # a registry pin may keep the short commit (video-use)
        return current.startswith(target) or target.startswith(current)
    return current == target


def report(mode: str, io: Io, *, dry: bool) -> list[str]:
    """One line per track: in sync, behind, or what it would become (`dry`). Reads the network, writes nothing."""
    lines: list[str] = []
    for t in tools.TOOLS.values():
        override = _override(t)
        if override:
            lines.append(f"  {t.name:<13} fixada por SIMPLICIO_{t.name.upper()}_REF={override}: o update não mexe")
            continue
        current, _ = tools.effective(t)
        mode_t = "pin" if pin_only(t) else mode
        try:
            target = pin_target(t) if mode_t == "pin" else resolve(t, io)
        except FAILURES as exc:
            lines.append(f"  {t.name:<13} não consultado: {exc}")
            continue
        same = _same_ref(t, current, target["ref"])
        if mode_t == "pin":
            if same:
                lines.append(f"  {t.name:<13} no pin: {current}")
            else:
                verb = "voltaria ao pin" if dry else "fora do pin"
                lines.append(f"  {t.name:<13} {verb}: em uso {current}, pin {target['ref']}")
        elif same:
            lines.append(f"  {t.name:<13} em dia: {current}")
        else:
            verb = "seguiria" if dry else "atrás"
            lines.append(f"  {t.name:<13} {verb}: {current} -> {target['ref']}")
    return lines
