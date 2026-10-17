"""`simplicio-video update [--check] [--dry-run] [--force]`: update this installation, with the loop's exit codes.

Ported from simplicio-loop simplicio_loop/self_update.py (2034e2d). Two distributions (see distribution.py):

* pip (an installed package): `python -m pip install --upgrade "simplicio-video==<latest>"` (PyPI); the latest release comes
  from GitHub Releases (`gh release view`, else the API). A PEP 668 environment is refused with the four ways out.
* source (a checkout, or an editable install): refuse a dirty tree, `git fetch`, show the new commits and the CHANGELOG diff,
  `git pull --ff-only`, then install, the web/ build and doctor, with the commit to go back to. Nothing is ever discarded.

Exit codes (as the loop): `--check` 0 up to date, 10 update available, 2 error; a refusal (dirty tree, no upstream, not a
fast-forward, PEP 668, a downgrade without --force) 2; a network failure `2 if --check else 1`.
`--force` reinstalls even when up to date and allows a downgrade; it never skips the dirty-tree refusal.
`--dry-run` prints what would run and records nothing. `--check` records the answer in update-check.json (in
$SIMPLICIO_VIDEO_DATA, default ~/.simplicio-video) so that `doctor` can show it without the network.
The network, git and the subprocesses are parameters of run_update, so the tests use fakes.

Exemplos:
  simplicio-video update --check
  simplicio-video update --dry-run
  simplicio-video update
"""
from __future__ import annotations

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


def parse_version(text: str) -> Tuple[int, ...]:
    match = re.search(r"(\d+)\.(\d+)\.(\d+)", text)
    if not match:
        raise ValueError(f"nenhuma versão em {text!r}")
    return tuple(int(part) for part in match.groups())


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
        done = subprocess.run([gh, "release", "view", "-R", REPO, "--json", "tagName", "-q", ".tagName"],
                              capture_output=True, text=True, timeout=30)
        if done.returncode == 0 and done.stdout.strip():
            return done.stdout.strip()
    with _open(LATEST_URL) as response:
        return str(json.loads(response.read().decode("utf-8"))["tag_name"])


def _run(argv: Sequence[str], cwd: Optional[Path] = None) -> int:
    return subprocess.call(list(argv), cwd=str(cwd) if cwd else None)


def _dry_runner(argv: Sequence[str], cwd: Optional[Path] = None) -> int:
    print("  executaria: " + " ".join(str(item) for item in argv))
    return 0


def _git(checkout: Path, *args: str) -> "subprocess.CompletedProcess":
    """git inside `checkout`. A missing git or a timeout is a failed command (rc 127), never a traceback."""
    argv = ["git", "-C", str(checkout), *args]
    try:
        return subprocess.run(argv, capture_output=True, text=True, env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})
    except OSError as exc:
        return subprocess.CompletedProcess(argv, 127, "", str(exc))


# --- the last check, for `doctor` to show offline ---------------------------------------------------------------------


def default_state_dir() -> Path:
    """$SIMPLICIO_VIDEO_DATA, else ~/.simplicio-video (the same folder the other tracks use)."""
    explicit = os.environ.get("SIMPLICIO_VIDEO_DATA")
    return Path(explicit) if explicit else hostos.home_dir() / ".simplicio-video"


def read_check(state_dir: Optional[Path] = None) -> Optional[dict]:
    """The answer of the last `update --check`: installed, latest, update_available, kind, checked_at. None if none."""
    try:
        data = json.loads(((state_dir or default_state_dir()) / CHECK_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def write_check(info: dict, state_dir: Optional[Path] = None) -> None:
    """Best effort and atomic: a cache that cannot be written never fails an update."""
    directory = state_dir or default_state_dir()
    try:
        directory.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=directory, prefix=CHECK_FILE + ".", suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump({**info, "checked_at": int(time.time())}, handle, sort_keys=True)
        os.replace(tmp, directory / CHECK_FILE)
    except OSError:
        pass


# --- asking what is latest --------------------------------------------------------------------------------------------


class Refused(Exception):
    """The update stops before it changes anything."""


def _upstream_version(git: Git, checkout: Path) -> Optional[str]:
    shown = git(checkout, "show", "@{u}:pyproject.toml")
    found = re.search(r'^version\s*=\s*"([^"]+)"', shown.stdout or "", re.M) if shown.returncode == 0 else None
    return found.group(1) if found else None


def _source_state(git: Git, checkout: Path, installed: str, *, fetch_remote: bool = True) -> dict:
    """Refuse or answer: is `checkout` a git work tree, clean, with an upstream? Then fetch and count the new commits.

    Returns {upstream, head, behind, new, latest}. Raises Refused (exit 2) or OSError (the fetch failed)."""
    if git(checkout, "rev-parse", "--is-inside-work-tree").returncode != 0:
        raise Refused(f"{checkout} não é um repositório git. O update de um checkout usa git pull --ff-only.")
    dirty = git(checkout, "status", "--porcelain", "--untracked-files=no").stdout.strip()
    if dirty:
        raise Refused("update recusado: a árvore está suja (alterações não commitadas em arquivos rastreados):\n"
                      + textwrap.indent(dirty, "  ")
                      + "\nGuarde as mudanças com `git stash` (ou faça commit) e rode o update de novo. "
                        "O --force não ignora isso: nada é descartado.")
    head = git(checkout, "rev-parse", "HEAD").stdout.strip()
    if fetch_remote:
        fetched = git(checkout, "fetch", "--quiet")
        if fetched.returncode != 0:
            raise OSError(f"git fetch falhou: {(fetched.stderr or '').strip()}")
    if git(checkout, "rev-parse", "--verify", "-q", "@{u}").returncode != 0:
        raise Refused("a branch atual não tem upstream. Configure com `git branch --set-upstream-to`.")
    upstream = git(checkout, "rev-parse", "--abbrev-ref", "@{u}").stdout.strip()
    new = git(checkout, "log", "--oneline", "HEAD..@{u}").stdout.strip()
    behind = len(new.splitlines()) if new else 0
    return {"upstream": upstream, "head": head, "behind": behind, "new": new,
            "latest": _upstream_version(git, checkout) or installed}


def check_latest(kind: str, installed: str, *, fetch: Callable[[], str] = fetch_latest_tag, git: Git = _git,
                 checkout: Optional[Path] = None) -> dict:
    """The update-check.json document for `kind`, asking the network (pip: GitHub Releases; source: git fetch).

    Used by `update --check` and by `doctor --online`. Raises OSError, ValueError, KeyError or Refused."""
    if kind == distribution.SOURCE:
        state = _source_state(git, checkout or paths.home(), installed)
        return {"installed": installed, "latest": state["latest"], "update_available": state["behind"] > 0,
                "kind": kind, "commits_behind": state["behind"]}
    latest = ".".join(map(str, parse_version(fetch())))
    return {"installed": installed, "latest": latest, "update_available": parse_version(latest) > parse_version(installed),
            "kind": kind}


# --- the web/ build ---------------------------------------------------------------------------------------------------


def _web_steps(checkout: Path) -> list:
    """The npm commands that rebuild web/ (none while web/ does not exist: it arrives with #34)."""
    if not (checkout / "web" / "package.json").is_file():
        return []
    npm = hostos.find_tool("npm")
    if npm is None:
        raise Refused("web/ existe, mas o npm não foi encontrado no PATH; instale o Node 22 e rode o update de novo")
    return [[npm, "--prefix", "web", "ci"], [npm, "--prefix", "web", "run", "build"]]


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
    if kind == distribution.SOURCE:
        return _update_source(check=check, force=force, dry_run=dry_run, installed=installed, runner=runner, git=git,
                              record=record, checkout=checkout or paths.home())
    return _update_pip(check=check, force=force, dry_run=dry_run, installed=installed, fetch=fetch, runner=runner,
                       record=record, externally_managed=externally_managed)


def _update_pip(*, check, force, dry_run, installed, fetch, runner, record, externally_managed) -> int:
    try:
        tag = fetch()
        latest = parse_version(tag)
    except (OSError, ValueError, KeyError) as exc:
        print(f"update: não consegui ler a última release de {REPO}: {exc}")
        return 2 if check else 1
    current = parse_version(installed)
    label = ".".join(map(str, latest))
    available = latest > current
    info = {"installed": installed, "latest": label, "update_available": available, "kind": distribution.PIP}
    if not dry_run:
        record(info)
    if latest <= current and not force:
        if latest < current and not check:
            print(f"update: a última release {label} é mais antiga que a instalada {installed}; "
                  "recusando um downgrade (use --force para instalá-la mesmo assim)")
            return 2
        print(f"simplicio-video {installed} em dia (última release {label})")
        return 0
    print(f"simplicio-video {installed} -> {label}")
    if check:
        return EXIT_UPDATE_AVAILABLE if available else 0
    managed, details = (bool(externally_managed), None) if externally_managed is not None else is_pep668_environment()
    if managed:
        print(pep668_message(details))
        return 2
    command = [sys.executable, "-m", "pip", "install", "--upgrade", *(["--force-reinstall"] if force else []),
               f"{PYPI_NAME}=={label}"]
    rc = runner(command)
    if rc != 0:
        print("update: o pip install falhou; rode `simplicio-video update` de novo quando o acesso ao PyPI voltar.")
        return rc
    if dry_run:
        print("update: simulação, nada foi alterado.")
        return 0
    record({**info, "installed": label, "update_available": False})
    print(f"update: atualizado {installed} -> {label}. Rode: simplicio-video doctor")
    return 0


def _update_source(*, check, force, dry_run, installed, runner, git, record, checkout) -> int:
    try:
        state = _source_state(git, checkout, installed)
    except Refused as exc:
        print(f"update: {exc}" if not str(exc).startswith("update") else str(exc), file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"update: {exc}", file=sys.stderr)
        return 2 if check else 1
    behind, upstream, head = state["behind"], state["upstream"], state["head"]
    info = {"installed": installed, "latest": state["latest"], "update_available": behind > 0,
            "kind": distribution.SOURCE, "commits_behind": behind}
    if not dry_run:
        record(info)
    if not behind and not force:
        print(f"já está atualizado com {upstream} ({head[:7]}): nada a fazer.")
        return 0
    if behind:
        print(f"simplicio-video {installed} -> {state['latest']} ({behind} commit(s) novo(s) em {upstream})")
        print(f"commits novos em {upstream}:")
        print(textwrap.indent(state["new"], "  "))
        diff = git(checkout, "diff", "HEAD", "@{u}", "--", "CHANGELOG.md").stdout.rstrip()
        print("CHANGELOG.md (diff):")
        print(diff or "  (sem mudanças no CHANGELOG neste intervalo)")
    else:
        print(f"--force: {upstream} não tem commits novos; reinstalando mesmo assim.")
    if check:
        return EXIT_UPDATE_AVAILABLE if behind else 0
    try:
        web = _web_steps(checkout)
    except Refused as exc:
        print(f"update: {exc}", file=sys.stderr)
        return 2
    if dry_run:
        print("update: simulação, nada foi alterado. Rodaria, nesta ordem:")
    if behind:
        if dry_run:
            print("  executaria: git pull --ff-only")
        else:
            pull = git(checkout, "pull", "--ff-only", "--quiet")
            if pull.returncode != 0:
                print("update: o pull não é fast-forward (há commits locais). Nada foi alterado; veja git status e git log.",
                      file=sys.stderr)
                print((pull.stderr or "").strip(), file=sys.stderr)
                return 2
            novo = git(checkout, "rev-parse", "HEAD").stdout.strip()
            print(f"atualizado: {head[:7]} -> {novo[:7]}")
            print("para voltar à versão anterior (rollback):")
            print(f"  git -C {checkout} reset --keep {head}")
            print("  depois: simplicio-video install && simplicio-video doctor")
    py = sys.executable
    steps = [("instalar dependências (simplicio-video install)", [[py, "-m", "simplicio_video", "install"]])]
    steps.append(("reconstruir web/", web))
    for title, commands in steps:
        print(f"> {title}")
        if not commands and title == "reconstruir web/":
            print("web/ chega com a #34: nada a construir")
        for command in commands:
            rc = runner(command, checkout)
            if rc != 0:
                print(f"update: falhou em '{title}' (código {rc}). Para voltar: git -C {checkout} reset --keep {head}",
                      file=sys.stderr)
                return rc
    print("> checar o ambiente (simplicio-video doctor)")
    rc = runner([py, "-m", "simplicio_video", "doctor"], checkout)
    return rc


def run(a) -> int:
    """The `update` command: the names below are looked up at call time, so the tests can replace them."""
    return run_update(check=a.check, force=a.force, dry_run=a.dry_run, fetch=fetch_latest_tag, runner=_run, git=_git,
                      record=write_check)
