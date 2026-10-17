"""`simplicio-video update [--check] [--dry-run] [--force]`: update this installation, with the loop's exit codes.

Ported from simplicio-loop simplicio_loop/self_update.py (2034e2d). Two distributions (see distribution.py):

* pip (an installed package): `python -m pip install --upgrade "simplicio-video==<latest>"` (PyPI), then
  `simplicio-video install --global` to reinstall the skills in the agent hosts, as the loop does; the latest release comes from
  GitHub Releases (`gh release view`, else the API). A PEP 668 environment is refused with the four ways out, and so is a Python
  without pip (a `uv tool install` venv): `uv tool upgrade` or `pipx upgrade` is what updates that one. `--force` on a release that
  is not newer reinstalls only our package (`--force-reinstall --no-deps`); on a newer one it is a plain `--upgrade`.
* source (a checkout, or an editable install): REFUSED, exit 2, printing `git pull` and `bash scripts/dev_install.sh` (Windows:
  `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\\dev_install.ps1`: the policy of a client Windows is Restricted, and
  the Bypass is for that one process; UNVERIFIED without a real Windows). Breaking change (direct owner request, ADR-0020): the update used to pull there;
  the loop never does, so nothing is pulled, rebuilt or discarded. `--check` still asks git how many commits are new.

Exit codes (as the loop): `--check` 0 up to date, 10 update available, 2 error; a refusal (a checkout, PEP 668) 2; a network failure
`2 if --check else 1`. An installed version NEWER than the latest release (PyPI is published before the GitHub Release) is up to
date: 0, as in the loop. `--force` reinstalls the pip release even when up to date and allows a downgrade. `--dry-run` prints the
plan, records nothing and exits 0 for a pip package, with or without `--check` (which alone answers 10); for a checkout it prints the
refusal (2) and runs no git at all (a fetch rewrites FETCH_HEAD, the remote-tracking refs and the reflog, so it is not a read-only
step). `--check` records the answer in update-check.json (in $SIMPLICIO_VIDEO_DATA, default ~/.simplicio-video) so that `doctor`
can show it without the network. SIMPLICIO_OFFLINE=1 blocks ALL the network: the GitHub release lookup (no `gh`, no API call) and the
`git fetch` of a checkout's `--check`. The network, git and the subprocesses are parameters of run_update, so the tests use fakes.

Exemplos:
  simplicio-video update --check
  simplicio-video update --dry-run
  simplicio-video update
"""
from __future__ import annotations

import contextlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import sysconfig
import tempfile
import textwrap
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Callable, Mapping, Optional, Sequence, Tuple

from .. import __version__, distribution, hostos, paths

REPO = "simpletibr/simplicio-videos"
PYPI_NAME = "simplicio-video"
LATEST_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
EXIT_UPDATE_AVAILABLE = 10
CHECK_FILE = "update-check.json"
_API = "https://api.github.com/"

Runner = Callable[..., int]
Git = Callable[..., "subprocess.CompletedProcess"]


def _offline() -> bool:
    return os.environ.get("SIMPLICIO_OFFLINE", "").strip().lower() in ("1", "true", "yes", "on")


# --- PEP 668 (a pip install into the system Python) -------------------------------------------------------------------


def is_pep668_environment(
    *,
    prefix: Optional[str] = None,
    base_prefix: Optional[str] = None,
    environ: Optional[Mapping[str, str]] = None,
) -> Tuple[bool, Optional[str]]:
    """(True, the manager's explanation) when this Python is externally managed (PEP 668); (False, None) otherwise."""
    environ = os.environ if environ is None else environ
    if environ.get("PIP_BREAK_SYSTEM_PACKAGES") == "1":
        return False, None
    pfx = sys.prefix if prefix is None else prefix
    bpfx = getattr(sys, "base_prefix", sys.prefix) if base_prefix is None else base_prefix
    if pfx != bpfx or (prefix is None and hasattr(sys, "real_prefix")):  # inside a virtual environment
        return False, None
    candidates: list = []
    if prefix is None:
        try:
            stdlib = sysconfig.get_path("stdlib")
            if stdlib:
                candidates.append(Path(stdlib) / "EXTERNALLY-MANAGED")
        except Exception:  # noqa: BLE001 - a broken sysconfig must not stop the update
            pass
    candidates.append(Path(pfx) / "lib" / f"python{sys.version_info.major}.{sys.version_info.minor}" / "EXTERNALLY-MANAGED")
    for candidate in candidates:
        try:
            if candidate.is_file():
                try:
                    return True, candidate.read_text(encoding="utf-8")
                except OSError:
                    return True, ""
        except OSError:
            continue
    return False, None


POWERSHELL_DEV_INSTALL = "powershell -NoProfile -ExecutionPolicy Bypass -File scripts\\dev_install.ps1"


def _has_pip() -> bool:
    """Whether this interpreter can run `python -m pip` (the venv of a `uv tool install` has none)."""
    return importlib.util.find_spec("pip") is not None


def no_pip_message() -> str:
    return "\n".join([
        "update: este Python não tem o pip (um `uv tool install` ou um venv sem pip): `python -m pip install` falharia.",
        "O jeito de atualizar essa instalação é a ferramenta que a criou:",
        f"       uv tool upgrade {PYPI_NAME}",
        f"       pipx upgrade {PYPI_NAME}",
        f"  e depois: {PYPI_NAME} install --global   (reinstala as skills nos hosts)",
    ])


def pep668_message(details: Optional[str] = None) -> str:
    lines = [
        "update: ambiente gerenciado externamente (PEP 668).",
        "O pip neste Python do sistema é restrito para proteger os pacotes do sistema.",
    ]
    if details and details.strip():
        lines.append(f"\nExplicação do gerenciador do sistema:\n{details.strip()}\n")
    lines += [
        "Saídas recomendadas:",
        "  1. Use um ambiente virtual (recomendado):",
        f"       python3 -m venv ~/.venvs/{PYPI_NAME}",
        f"       source ~/.venvs/{PYPI_NAME}/bin/activate",
        f"       pip install -U {PYPI_NAME}",
        "  2. Use o uv:",
        f"       uv tool install {PYPI_NAME} (ou: uv pip install --system -U {PYPI_NAME})",
        "  3. Use o pipx:",
        f"       pipx install {PYPI_NAME} (ou: pipx upgrade {PYPI_NAME})",
        "  4. Se você autoriza, passe por cima da proteção PEP 668:",
        "       PIP_BREAK_SYSTEM_PACKAGES=1 simplicio-video update",
    ]
    return "\n".join(lines)


# A release tag: `v` optional, 2 to 4 numbers, and the post-release suffix of PEP 440; nothing else. ASCII digits only (`\d` would
# also match full-width digits), and the whole text must match: `v0.5.0 --index-url=...` or `0.5.0 @ git+https://...` are not versions.
_VERSION = re.compile(r"v?(\d+(?:\.\d+){1,3})(?:\.post(\d+))?", re.ASCII)
# The INSTALLED version is our own `__version__`: it may be a development or pre-release one (PEP 440: dev < a < b < rc < final < post).
_INSTALLED = re.compile(r"\s*v?(\d+(?:\.\d+){0,3})(?:[-_.]?(dev|alpha|a|beta|b|preview|pre|rc|c)[-_.]?(\d*))?"
                        r"(?:[-_.]?post[-_.]?(\d*))?", re.ASCII | re.IGNORECASE)
_PHASES = {"dev": 0, "a": 1, "alpha": 1, "b": 2, "beta": 2, "c": 3, "rc": 3, "pre": 3, "preview": 3}
FINAL = 4  # the phase of a final release, above every pre-release


def parse_version(text: str) -> Tuple[int, ...]:
    """A release as a tuple of integers that compares like PEP 440: four release numbers, the phase, its number, the post number.

    STRICT on purpose. The tag comes from the network and ends up in pip's argv, so only a final release is read (`X.Y`,
    `X.Y.Z`, `X.Y.Z.W`, optional `v`, optional `.postN`) and the argv is rebuilt from the integers (`format_version`), never from
    the text. A pre-release, a local version, an epoch or any extra text raises ValueError: a pre-release is never a TARGET."""
    found = _VERSION.fullmatch(text.strip()) if isinstance(text, str) else None
    if not found:
        raise ValueError(f"não é uma versão de release (esperava algo como 1.2.3 ou v1.2.3): {str(text)[:60]!r}")
    release = [int(part) for part in found.group(1).split(".")]
    return (*release, *([0] * (4 - len(release))), FINAL, 0, int(found.group(2) or 0))


def format_version(parts: Tuple[int, ...]) -> str:
    """`(1, 2, 0, 0, 4, 0, 0)` -> `1.2.0`: three release numbers at least, the fourth only when it is not zero, then `.postN`.

    Only final releases are ever printed (a pre-release is a source of a comparison, never a target)."""
    release, post = list(parts[:4]), parts[6]
    while len(release) > 3 and release[-1] == 0:
        release.pop()
    return ".".join(str(part) for part in release) + (f".post{post}" if post else "")


def release_tuple(text: str) -> Tuple[int, ...]:
    """The INSTALLED version in the order of PEP 440, never an error: `0.5.0.dev1` < `0.5.0a1` < `0.5.0b1` < `0.5.0rc1` <
    `0.5.0` < `0.5.0.post1`, and a local label (`+local`) does not count. Text with no number at all reads as 0.0.0."""
    try:
        return parse_version(text)
    except ValueError:
        pass
    found = _INSTALLED.match(str(text))
    try:
        numbers = [int(n) for n in found.group(1).split(".")] if found else []
    except ValueError:
        numbers = []
    release = (*numbers, *([0] * (4 - len(numbers))))
    if not found:
        return (*release, FINAL, 0, 0)
    phase, number, post = found.group(2), found.group(3), found.group(4)
    if phase:
        return (*release, _PHASES[phase.lower()], int(number or 0), 0)
    return (*release, FINAL, 0, int(post or 0) if post is not None else 0)


def _clean_latest(text: Optional[str], installed: str) -> str:
    """The version a checkout reports as the latest, as a plain release: whatever the upstream pyproject.toml says is somebody
    else's text, so it is read strictly, and when it is not a release the installed one stands in."""
    try:
        return format_version(parse_version(text or ""))
    except ValueError:
        return format_version(release_tuple(installed))


# --- the latest release (gh, then the GitHub API) ---------------------------------------------------------------------


def _request(url: str) -> urllib.request.Request:
    """The GitHub token goes to the API only: a download can redirect to another host, which must never see it."""
    headers = {"User-Agent": "simplicio-video-update",
               "Accept": "application/vnd.github+json" if url.startswith(_API) else "application/octet-stream"}
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token and url.startswith(_API):
        headers["Authorization"] = f"Bearer {token}"
    return urllib.request.Request(url, headers=headers)


class _SameHostRedirect(urllib.request.HTTPRedirectHandler):
    """urllib copies every header into a redirected request: this handler removes the GitHub token when the redirect
    leaves the host, and refuses a redirect from https to plain http."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        old, new = urllib.parse.urlsplit(req.full_url), urllib.parse.urlsplit(newurl)
        if old.scheme == "https" and new.scheme != "https":
            raise urllib.error.HTTPError(req.full_url, code, "a redirect from https to plain http is refused", headers, fp)
        moved = super().redirect_request(req, fp, code, msg, headers, newurl)
        if moved is not None and old.netloc != new.netloc:
            moved.remove_header("Authorization")
        return moved


_OPENER = urllib.request.build_opener(_SameHostRedirect)


def _open(url: str):
    if not url.startswith("https://"):
        raise ValueError(f"recusando uma url que não é https: {url}")
    return _OPENER.open(_request(url), timeout=60)  # https only, checked above


def fetch_latest_tag() -> str:
    """The tag of the latest GitHub release. SIMPLICIO_OFFLINE=1 blocks it: no `gh`, no API call."""
    if _offline():
        raise OSError("SIMPLICIO_OFFLINE=1: rede bloqueada")
    gh = hostos.find_tool("gh")
    if gh:
        try:
            done = subprocess.run([gh, "release", "view", "-R", REPO, "--json", "tagName", "-q", ".tagName"],
                                  capture_output=True, encoding="utf-8", errors="replace", timeout=30)
        except (OSError, subprocess.SubprocessError):  # a gh that hangs or cannot start: the API is the other way
            done = None
        if done is not None and done.returncode == 0 and done.stdout.strip():
            return done.stdout.strip()
    with _open(LATEST_URL) as response:
        raw = response.read(1 << 20)  # a release document is a few KiB: a megabyte is the cap
    try:
        document = json.loads(raw.decode("utf-8"))
    except (ValueError, RecursionError):
        raise ValueError("a resposta da API do GitHub não é JSON") from None
    tag = document.get("tag_name") if isinstance(document, dict) else None
    if not isinstance(tag, str):
        raise ValueError("a resposta da API do GitHub não tem tag_name")
    return tag


def _run(argv: Sequence[str], cwd: Optional[Path] = None) -> int:
    return subprocess.call(list(argv), cwd=str(cwd) if cwd else None)


def _dry_runner(argv: Sequence[str], cwd: Optional[Path] = None) -> int:
    print("  executaria: " + " ".join(str(item) for item in argv))
    return 0


def _git(checkout: Path, *args: str) -> "subprocess.CompletedProcess":
    """git inside `checkout`. A missing git or a timeout is a failed command (rc 127), never a traceback.

    `--no-optional-locks`: a plain `git status` or `git diff` also refreshes the stat cache in .git/index, a write that a
    read-only step (the dry-run, the doctor) must not do. git before 2.15 does not know the option (`Unknown option`, exit
    129): that call is repeated ONCE without it, so an old git still works (and still writes the index, as it always did)."""
    for options in (["--no-optional-locks"], []):
        argv = ["git", "-C", str(checkout), *options, *args]
        try:
            # UTF-8 with `replace`: the Windows default is the console codec (cp1252 cannot read the 0x8D of an `Í`), and a diff
            # of the CHANGELOG must never be the reason for a UnicodeDecodeError
            done = subprocess.run(argv, capture_output=True, encoding="utf-8", errors="replace",
                                  env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})
        except OSError as exc:
            return subprocess.CompletedProcess(argv, 127, "", str(exc))
        if options and done.returncode != 0 and "unknown option" in (done.stderr or "").lower() \
                and "no-optional-locks" in (done.stderr or ""):
            continue
        return done
    return done  # pragma: no cover - the loop always returns


def _motivo(done: "subprocess.CompletedProcess") -> str:
    """What git said (stderr, else stdout), for a person: one line, no terminal escape, at most 300 characters."""
    texto = (getattr(done, "stderr", "") or getattr(done, "stdout", "") or "").strip()
    texto = " ".join("".join(c if c.isprintable() else " " for c in texto).split())
    return texto if len(texto) <= 300 else texto[:297] + "..."


# --- the last check, for `doctor` to show offline ---------------------------------------------------------------------


def default_state_dir() -> Path:
    """$SIMPLICIO_VIDEO_DATA, else ~/.simplicio-video (the same folder the other tracks use)."""
    explicit = os.environ.get("SIMPLICIO_VIDEO_DATA")
    return Path(explicit) if explicit else hostos.home_dir() / ".simplicio-video"


class CheckInvalid(ValueError):
    """update-check.json is there but is not a usable answer: corrupt, hostile or written by something else."""


MAX_CHECK_BYTES = 64 * 1024  # the file is a few hundred bytes


def _clean_check(raw: object) -> dict:
    """Only the keys of the schema, each with its type; `latest` as a normalized release and `checked_at` as a real instant."""
    if not isinstance(raw, dict):
        raise CheckInvalid("não é um objeto JSON")
    stamp = raw.get("checked_at")
    if isinstance(stamp, bool) or not isinstance(stamp, int) or not 0 <= stamp <= hostos.MAX_TIMESTAMP:
        raise CheckInvalid("checked_at não é um instante válido")
    try:
        latest = format_version(parse_version(raw.get("latest")))
    except ValueError:
        raise CheckInvalid("latest não é uma versão de release") from None
    clean: dict = {"latest": latest, "checked_at": stamp}
    installed = raw.get("installed")
    if isinstance(installed, str) and 0 < len(installed) <= 64 and installed.isprintable():
        clean["installed"] = installed
    if isinstance(raw.get("update_available"), bool):
        clean["update_available"] = raw["update_available"]
    kind = raw.get("kind")
    if kind in (distribution.SOURCE, distribution.PIP):
        clean["kind"] = kind
    behind = raw.get("commits_behind")
    if kind == distribution.SOURCE and isinstance(behind, int) and not isinstance(behind, bool) and 0 <= behind <= 10**9:
        clean["commits_behind"] = behind
    return clean


def read_check(state_dir: Optional[Path] = None) -> Optional[dict]:
    """The answer of the last `update --check` (only the keys of the schema, validated), or None when there is none.

    Raises CheckInvalid when the file is there and is not usable: the `doctor` shows that as a warning, never as a traceback."""
    path = (state_dir or default_state_dir()) / CHECK_FILE
    try:
        raw = hostos.read_regular(path, MAX_CHECK_BYTES)  # O_NONBLOCK and fstat: a FIFO there must not hang the doctor
    except (FileNotFoundError, NotADirectoryError):
        return None
    except hostos.NotARegularFile:
        raise CheckInvalid("não é um arquivo comum (pasta, fifo, dispositivo...)") from None
    except OSError as exc:
        raise CheckInvalid(f"não consegui ler: {exc.strerror or exc}") from None
    if len(raw) > MAX_CHECK_BYTES:
        raise CheckInvalid("grande demais")
    try:
        data = json.loads(raw.decode("utf-8"))
    except (ValueError, RecursionError):
        raise CheckInvalid("não é JSON") from None
    return _clean_check(data)


def write_check(info: dict, state_dir: Optional[Path] = None) -> None:
    """Best effort and atomic: a temp file in the same folder, then os.replace. A cache that cannot be written never fails an
    update, never leaves a half-written file where the doctor reads, and never leaves its temp file behind."""
    directory = state_dir or default_state_dir()
    tmp = None
    try:
        directory.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=directory, prefix=CHECK_FILE + ".", suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump({**info, "checked_at": int(time.time())}, handle, sort_keys=True)
        os.replace(tmp, directory / CHECK_FILE)
    except (OSError, TypeError, ValueError):
        if tmp is not None:
            with contextlib.suppress(OSError):
                os.unlink(tmp)


# --- asking what is latest --------------------------------------------------------------------------------------------


class Refused(Exception):
    """The update stops before it changes anything."""


def _upstream_version(git: Git, checkout: Path) -> Optional[str]:
    shown = git(checkout, "show", "@{u}:pyproject.toml")
    found = re.search(r'^version\s*=\s*"([^"]+)"', shown.stdout or "", re.M) if shown.returncode == 0 else None
    return found.group(1) if found else None


def _source_state(git: Git, checkout: Path, installed: str, *, fetch_remote: bool = True) -> dict:
    """Answer for `--check` and `doctor --online`: is `checkout` a git work tree with an upstream? Then fetch and count the new commits.

    Nothing is pulled, so local changes do not matter. `fetch_remote=False` does not fetch: the count then comes from the refs the
    last fetch left. Returns {upstream, head, behind, new, latest}. Raises Refused (exit 2) or OSError (the fetch failed, or
    SIMPLICIO_OFFLINE=1)."""
    inside = git(checkout, "rev-parse", "--is-inside-work-tree")
    if inside.returncode != 0:
        why = _motivo(inside)
        raise Refused(f"{checkout} não é um repositório git" + (f" (o git disse: {why})" if why else "")
                      + ". O update de um checkout é `git pull` e `bash scripts/dev_install.sh` (veja `simplicio-video update --help`).")
    head = git(checkout, "rev-parse", "HEAD").stdout.strip()
    if fetch_remote:
        if _offline():  # `git fetch` is network: SIMPLICIO_OFFLINE=1 blocks it like the release lookup of the pip package
            raise OSError("SIMPLICIO_OFFLINE=1: rede bloqueada (o `git fetch` do checkout não roda)")
        fetched = git(checkout, "fetch", "--quiet")
        if fetched.returncode != 0:
            raise OSError(f"git fetch falhou: {(fetched.stderr or '').strip()}")
    if git(checkout, "rev-parse", "--verify", "-q", "@{u}").returncode != 0:
        raise Refused("a branch atual não tem upstream. Configure com `git branch --set-upstream-to`.")
    upstream = git(checkout, "rev-parse", "--abbrev-ref", "@{u}").stdout.strip()
    new = git(checkout, "log", "--oneline", "HEAD..@{u}").stdout.strip()
    behind = len(new.splitlines()) if new else 0
    return {"upstream": upstream, "head": head, "behind": behind, "new": new,
            "latest": _clean_latest(_upstream_version(git, checkout), installed)}


def check_latest(kind: str, installed: str, *, fetch: Callable[[], str] = fetch_latest_tag, git: Git = _git,
                 checkout: Optional[Path] = None) -> dict:
    """The update-check.json document for `kind`, asking the network (pip: GitHub Releases; source: git fetch).

    Used by `update --check` and by `doctor --online`. Raises OSError, ValueError, KeyError or Refused."""
    if kind == distribution.SOURCE:
        state = _source_state(git, checkout or paths.home(), installed)
        return {"installed": installed, "latest": state["latest"], "update_available": state["behind"] > 0,
                "kind": kind, "commits_behind": state["behind"]}
    latest = format_version(parse_version(fetch()))
    return {"installed": installed, "latest": latest, "update_available": parse_version(latest) > release_tuple(installed),
            "kind": kind}


# --- the command ------------------------------------------------------------------------------------------------------


def run_update(
    check: bool = False,
    force: bool = False,
    dry_run: bool = False,
    *,
    installed: Optional[str] = None,
    fetch: Callable[[], str] = fetch_latest_tag,
    runner: Runner = _run,
    git: Git = _git,
    kind: Optional[str] = None,
    record: Optional[Callable[[dict], None]] = None,
    externally_managed: Optional[bool] = None,
    checkout: Optional[Path] = None,
) -> int:
    installed = installed or __version__
    record = record or (lambda info: None)
    kind = kind or distribution.kind()
    if dry_run:
        runner = _dry_runner
        check = False  # ONE rule: the dry-run only shows the plan (`--check` alone answers 10)
    if kind == distribution.SOURCE:
        return _update_source(check=check, installed=installed, git=git, record=record, checkout=checkout or paths.home())
    return _update_pip(check=check, force=force, dry_run=dry_run, installed=installed, fetch=fetch, runner=runner,
                       record=record, externally_managed=externally_managed)


def _update_pip(*, check, force, dry_run, installed, fetch, runner, record, externally_managed) -> int:
    try:
        tag = fetch()
        latest = parse_version(tag)
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        print(f"update: não consegui ler a última release de {REPO}: {exc}")
        return 2 if check else 1
    current = release_tuple(installed)
    label = format_version(latest)
    available = latest > current
    info = {"installed": installed, "latest": label, "update_available": available, "kind": distribution.PIP}
    if not dry_run:
        record(info)
    if latest <= current and not force:
        if latest < current:  # PyPI is published before the GitHub Release: not an error, and not a downgrade to offer
            print(f"simplicio-video {installed} é mais novo que a última release {label}; nada a atualizar "
                  "(--force instala a release mesmo assim)")
        else:
            print(f"simplicio-video {installed} em dia (última release {label})")
        return 0
    print(f"simplicio-video {installed} -> {label}")
    if check:
        return EXIT_UPDATE_AVAILABLE if available else 0
    managed, details = (bool(externally_managed), None) if externally_managed is not None else is_pep668_environment()
    if managed:
        print(pep668_message(details))
        return 2
    if not dry_run and not _has_pip():
        print(no_pip_message())
        return 2
    # the argv is a list (no shell) rebuilt from integers: a fixed `==`, one version, nothing from the tag's text. `--force` only
    # reinstalls when nothing is newer, and only our package: `--no-deps` on a NEWER release would skip a dependency it adds
    reinstall = force and not available
    command = [sys.executable, "-m", "pip", "install", "--upgrade", *(["--force-reinstall", "--no-deps"] if reinstall else []),
               f"{PYPI_NAME}=={label}"]
    rc = runner(command)
    if rc != 0:
        print("update: o pip install falhou; rode `simplicio-video update` de novo quando o acesso ao PyPI voltar.")
        return rc
    # as the loop: the skills that the hosts hold are the old release's until `install --global` runs, and it must be the NEW code
    rc = runner([sys.executable, "-m", "simplicio_video", "install", "--global"])
    if rc != 0:
        print(f"update: o pip instalou a release, mas `simplicio-video install --global` falhou (código {rc}); rode "
              "`simplicio-video install --global` à mão para reinstalar as skills.")
        return rc
    if dry_run:
        print("update: simulação, nada foi alterado.")
        return 0
    record({**info, "installed": label, "update_available": False})
    print(f"update: atualizado {installed} -> {label}. Rode: simplicio-video doctor")
    return 0


def refusal_text(checkout: Path) -> str:
    """What a checkout is told instead of an update: the two commands, with the dev install of this system. On Windows the script
    is run with the policy of that process only: the client Windows is Restricted and `powershell -File x.ps1` would refuse it."""
    dev_install = (POWERSHELL_DEV_INSTALL if hostos.is_windows() else "bash scripts/dev_install.sh")
    return (f"update: este é um checkout git (ou uma instalação editável): o update não mexe nele e recusa (exit 2).\n"
            f"Para atualizar, rode dentro do checkout ({checkout}):\n  git pull\n  {dev_install}")


def _update_source(*, check, installed, git, record, checkout) -> int:
    if not check:  # a plain update, `--force` and `--dry-run` (which turned `check` off): the refusal, no git, no network
        print(refusal_text(checkout), file=sys.stderr)
        return 2
    try:
        state = _source_state(git, checkout, installed)
    except Refused as exc:
        print(f"update: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"update: {exc}", file=sys.stderr)
        return 2
    behind, upstream, head = state["behind"], state["upstream"], state["head"]
    record({"installed": installed, "latest": state["latest"], "update_available": behind > 0,
            "kind": distribution.SOURCE, "commits_behind": behind})
    if not behind:
        print(f"já está atualizado com {upstream} ({head[:7]}): nada a fazer.")
        return 0
    print(f"simplicio-video {installed} -> {state['latest']} ({behind} commit(s) novo(s) em {upstream})")
    print(f"commits novos em {upstream}:")
    print(textwrap.indent(state["new"], "  "))
    diff = git(checkout, "diff", "HEAD", "@{u}", "--", "CHANGELOG.md").stdout.rstrip()
    print("CHANGELOG.md (diff):")
    print(diff or "  (sem mudanças no CHANGELOG neste intervalo)")
    return EXIT_UPDATE_AVAILABLE


def run(a) -> int:
    """The `update` command: the names below are looked up at call time, so the tests can replace them."""
    return run_update(check=a.check, force=a.force, dry_run=a.dry_run, fetch=fetch_latest_tag, runner=_run, git=_git,
                      record=write_check)
