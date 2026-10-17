"""The Simplicio login file, shared with the Simplicio Runtime. The video CLI only READS it.

Ported from simplicio-loop simplicio_loop/auth.py (2034e2d), the read side only: no write, no refresh, no token application,
no 24/7 watcher path (decision of the owner: `login` is a mirror, it stores no credential and the engine consumes no token).
`login`, `logout`, `auth status` and `doctor` all go through here.

* PATH: env `SIMPLICIO_AUTH_FILE` (the name the Runtime reads), else ~/.simplicio/login.json. Same schema as the Runtime:
  `access_token`, `refresh_token`, `access_expires_at`, `refresh_token_expires_at`, `verification.validated`.
* SAFETY (POSIX): a login file that group or others can read, that is a symlink, a FIFO or a directory, or that belongs to
  another user, is refused, and so is a folder that group or others can write (unless it is sticky and ours) and a
  `login.lock` that is another user's or that others can open. The checks use the descriptor that is read.
* SAFETY (Windows): chmod and uid mean nothing there, so the mode and owner checks are skipped and the ACLs are NOT verified.
  A symlink or any reparse point of the link kind (symlink, junction) is still refused. Windows has no O_NOFOLLOW, so the
  link check and the open are not one atomic step there.
* LOCK: `logout` deletes the file under the exclusive lock on the sidecar `login.lock`, the same file the Runtime locks
  (runtime_auth.rs `auth_lock`: the login file name with the extension changed to `lock`, 20 s). fcntl on POSIX, msvcrt on
  Windows. NOT VERIFIED: that msvcrt.locking and the Runtime's LockFileEx exclude each other on a real Windows host.
"""
from __future__ import annotations

import contextlib
import errno
import json
import os
import re
import stat
import subprocess
import time
from pathlib import Path
from typing import Any, Iterator, Mapping, Optional

from . import hostos

try:
    import fcntl
    msvcrt = None
except ImportError:  # Windows
    fcntl = None
    import msvcrt

RUNTIME_ENV = "SIMPLICIO_AUTH_FILE"
# Windows reparse tags of the link kind (winnt.h). The `stat` module defines them only on Windows builds.
IO_REPARSE_TAG_SYMLINK = 0xA000000C
IO_REPARSE_TAG_MOUNT_POINT = 0xA0000003
RUNTIME_DIR = ".simplicio"
LOCK_WAIT_S = 20.0  # the Runtime waits 20 s for the same lock
LOCK_POLL_S = 0.05

_VERSION = re.compile(r"simplicio\s+v?(\d+\.\d+\.\d+)")
_EMAIL = re.compile(r"([^@\s])[^@\s]*@([^@\s]+\.[^@\s]+)")


class LoginError(Exception):
    """The login file cannot be used. `reason_code` is stable, the message says what to do and never holds a token."""

    def __init__(self, reason_code: str, message: str = "", fix: Optional[str] = None) -> None:
        super().__init__(message or reason_code)
        self.reason_code = reason_code
        self.fix = fix  # the exact command that repairs it, when there is one


# --- where ----------------------------------------------------------------------------------------------------------


def runtime_login_path(environ: Optional[Mapping[str, str]] = None) -> Path:
    """The file the Runtime itself uses: SIMPLICIO_AUTH_FILE, else ~/.simplicio/login.json."""
    environ = os.environ if environ is None else environ
    explicit = (environ.get(RUNTIME_ENV) or "").strip()
    return Path(explicit) if explicit else hostos.home_dir(environ) / RUNTIME_DIR / "login.json"


def login_path(environ: Optional[Mapping[str, str]] = None) -> Path:
    """The file this program uses: the Runtime's file (the video CLI has no login file of its own)."""
    return runtime_login_path(environ)


def lock_path(path: Path) -> Path:
    """`login.json` -> `login.lock`: the sidecar the Runtime locks (the extension is replaced, as Rust does)."""
    return Path(path).with_suffix(".lock")


# --- read -----------------------------------------------------------------------------------------------------------


def is_link(path: Path) -> bool:
    """A symlink, or on Windows a reparse point of the link kind (symlink, junction).

    Other reparse points (a OneDrive placeholder, a dedup stub) are real files and are not refused."""
    try:
        info = os.lstat(path)
    except OSError:
        return False
    if stat.S_ISLNK(info.st_mode):
        return True
    return getattr(info, "st_reparse_tag", 0) in (IO_REPARSE_TAG_SYMLINK, IO_REPARSE_TAG_MOUNT_POINT)


def _symlink_error(path: Path) -> LoginError:
    return LoginError("login_symlink", f"{path} é um link simbólico; remova-o e rode: simplicio-video login")


def _foreign_owner(info: os.stat_result) -> bool:
    """A file of another user, seen by a user who is not root (POSIX only).

    A process with euid 0 is exempt: root can read and replace every file anyway, so the check protects nobody from root."""
    return hasattr(os, "geteuid") and os.geteuid() != 0 and info.st_uid != os.geteuid()


def _check_parent(path: Path) -> None:
    """The folder must not be writable by group or others (they could swap the file), unless it is sticky and ours."""
    if hostos.is_windows():
        return
    try:
        info = os.stat(path.parent)
    except OSError:
        return  # no folder yet: a read says login_missing
    if info.st_mode & 0o022 and not (info.st_mode & stat.S_ISVTX and info.st_uid == os.geteuid()):
        raise LoginError("login_permissions", f"{path.parent} pode ser alterada pelo grupo ou por outros "
                         f"(modo {info.st_mode & 0o777:03o}); rode: chmod 700 {path.parent}", f"chmod 700 {path.parent}")


def read_login(path: Optional[Path] = None) -> dict:
    """The login file as a dict. Raises LoginError: login_missing, login_symlink, login_permissions, login_invalid.

    Only a regular file is read (a FIFO would hang, a directory has no content), through O_NOFOLLOW and O_NONBLOCK where
    they exist, and the checks use the descriptor that is read, so nothing can change between the check and the read.
    """
    path = Path(path) if path else login_path()
    if is_link(path):
        raise _symlink_error(path)
    _check_parent(path)
    flags = (os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NONBLOCK", 0)
             | getattr(os, "O_BINARY", 0))
    try:
        fd = os.open(path, flags)
    except FileNotFoundError:
        raise LoginError("login_missing", f"não há arquivo de login em {path}; rode: simplicio-video login") from None
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            raise _symlink_error(path) from None
        raise LoginError("login_invalid", f"não consegui ler {path}: {exc.strerror}") from None
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise LoginError("login_invalid", f"{path} não é um arquivo comum; remova-o e rode: simplicio-video login")
        if not hostos.is_windows() and _foreign_owner(info):
            raise LoginError("login_permissions", f"{path} pertence a outro usuário; remova-o e rode: simplicio-video login",
                             f"remova {path} e rode: simplicio-video login")
        if not hostos.is_windows() and info.st_mode & 0o077:
            raise LoginError("login_permissions", f"{path} pode ser lido pelo grupo ou por outros "
                             f"(modo {info.st_mode & 0o777:03o}); rode: chmod 600 {path}", f"chmod 600 {path}")
    except BaseException:
        os.close(fd)
        raise
    with os.fdopen(fd, encoding="utf-8") as handle:
        try:
            data = json.loads(handle.read())
        except (ValueError, OSError):  # UnicodeDecodeError is a ValueError
            data = None
    if not isinstance(data, dict):
        raise LoginError("login_invalid", f"{path} não é um arquivo de login (esperava um objeto JSON); "
                         "rode: simplicio-video login")
    return data


# --- the lock -------------------------------------------------------------------------------------------------------


def _try_lock(fd: int) -> bool:
    """One attempt at the exclusive lock; False while another process holds it."""
    if fcntl is not None:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            if exc.errno in (errno.EAGAIN, errno.EACCES, errno.EWOULDBLOCK):
                return False
            raise
        return True
    try:
        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
    except OSError:
        return False
    return True


def _unlock(fd: int) -> None:
    if fcntl is not None:
        fcntl.flock(fd, fcntl.LOCK_UN)
    else:
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)


@contextlib.contextmanager
def file_lock(path: Path, *, wait_s: float = LOCK_WAIT_S, strict: bool = True) -> Iterator[None]:
    """Exclusive advisory lock on the sidecar of `path`. The kernel drops it when the owner dies: a left-over file is no lock.

    `strict` (the login lock) also refuses a loose folder and a lock file that is another user's or that others can open.
    """
    lock = lock_path(Path(path))
    if strict:
        _check_parent(lock)
    lock.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if is_link(lock):  # Windows has no O_NOFOLLOW: look before opening
        raise LoginError("login_symlink", f"{lock} é um link simbólico; remova-o")
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_BINARY", 0)
    try:
        fd = os.open(lock, flags, 0o600)
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            raise LoginError("login_symlink", f"{lock} é um link simbólico; remova-o") from None
        raise LoginError("login_invalid", f"não consegui abrir {lock}: {exc.strerror}") from None
    try:
        info = os.fstat(fd)
        if strict and not hostos.is_windows() and _foreign_owner(info):  # another user's lock file would let it stall us
            raise LoginError("login_permissions", f"{lock} pertence a outro usuário; remova-o")
        if strict and not hostos.is_windows() and info.st_mode & 0o077:
            raise LoginError("login_permissions", f"{lock} pode ser aberto pelo grupo ou por outros "
                             f"(modo {info.st_mode & 0o777:03o}); rode: chmod 600 {lock}")
        deadline = time.monotonic() + wait_s
        while not _try_lock(fd):
            if time.monotonic() >= deadline:
                raise LoginError("login_lock_timeout",
                                 f"outro programa segura {lock} (o Runtime renova o login ali); tente de novo")
            time.sleep(LOCK_POLL_S)
        try:
            yield
        finally:
            _unlock(fd)
    finally:
        os.close(fd)


def clear_login(path: Optional[Path] = None) -> bool:
    """Delete the login file under the lock (this logs the Runtime out too). True if a file was removed.

    A missing file is not an error and creates nothing (no folder, no lock file)."""
    path = Path(path) if path else login_path()
    if not (path.exists() or is_link(path)):
        return False
    if path.is_dir() and not is_link(path):
        raise LoginError("login_invalid", f"{path} é uma pasta, não um arquivo de login; remova-a à mão")
    with file_lock(path):
        try:
            path.unlink()  # unlink never follows a symlink
        except FileNotFoundError:
            return False
    return True


# --- what the file says (never a token) -----------------------------------------------------------------------------


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def mask_email(email: str) -> str:
    """`wesley@gmail.com` -> `w***@gmail.com`; anything that is not an address gives ''."""
    found = _EMAIL.fullmatch(email.strip())
    return f"{found.group(1)}***@{found.group(2)}" if found else ""


def summary(login: Mapping[str, Any], now: Optional[float] = None) -> dict:
    """Public facts of a login: no token, no unmasked e-mail."""
    stamp = time.time() if now is None else now
    verification = login.get("verification")
    validated = verification.get("validated") if isinstance(verification, dict) else None
    validated = validated if isinstance(validated, dict) else {}
    user = validated.get("user") if isinstance(validated.get("user"), dict) else {}
    entitlement = validated.get("entitlement")
    access_expires = _int(login.get("access_expires_at"))
    refresh_expires = _int(login.get("refresh_token_expires_at"))
    return {
        "email": mask_email(str(user.get("email") or "")),
        "access_expires_at": access_expires,
        "access_expired": access_expires <= stamp,
        "refresh_expires_at": refresh_expires,
        "refresh_expired": bool(refresh_expires) and refresh_expires <= stamp,  # 0 = persistent or unknown
        "has_refresh_token": bool(str(login.get("refresh_token") or "").strip()),
        "entitlement": ({key: entitlement.get(key) for key in ("tier", "status", "source", "plan", "active")}
                        if isinstance(entitlement, dict) else None),
    }


# --- the Runtime ----------------------------------------------------------------------------------------------------


def runtime_binary(environ: Optional[Mapping[str, str]] = None) -> Optional[Path]:
    """The Runtime: `simplicio` on PATH (PATHEXT on Windows, never the current directory), else its copy in ~/.simplicio/bin."""
    environ = os.environ if environ is None else environ
    found = hostos.which("simplicio", environ.get("PATH", ""))
    if found:
        return found
    managed = hostos.home_dir(environ) / RUNTIME_DIR / "bin" / hostos.exe_name("simplicio")
    return managed if managed.is_file() and os.access(managed, os.X_OK) else None


def runtime_version(binary: Path, timeout: float = 10) -> Optional[str]:
    """`simplicio --version` -> '3.10.0', or None when it does not answer."""
    try:
        done = subprocess.run([str(binary), "--version"], capture_output=True, text=True, timeout=timeout,
                              stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        return None
    found = _VERSION.search(done.stdout) if done.returncode == 0 else None
    return found.group(1) if found else None


_FIXES = {"login_missing": "simplicio-video login", "login_invalid": "simplicio-video login",
          "login_symlink": "remova o link simbólico e rode: simplicio-video login", "login_expired": "simplicio-video login"}


def describe(environ: Optional[Mapping[str, str]] = None, now: Optional[float] = None) -> dict:
    """The state of the login as a plain dict (used by `auth status`, `login` and `doctor`): never a token.

    `logged_in` is true when the file is valid and either the access token has not expired or a refresh token
    that has not expired can renew it. `reason_code` is `ok` or why not; `fix` is the command that repairs it.
    """
    environ = os.environ if environ is None else environ
    path, runtime_path = login_path(environ), runtime_login_path(environ)
    binary = runtime_binary(environ)
    doc: dict[str, Any] = {
        "schema": "simplicio.auth-status/v1", "logged_in": False, "reason_code": "ok", "fix": None,
        "path": str(path), "runtime_path": str(runtime_path),
        "shared_with_runtime": os.path.normcase(os.path.abspath(path)) == os.path.normcase(os.path.abspath(runtime_path)),
        "runtime": {"found": binary is not None, "path": str(binary) if binary else None,
                    "version": runtime_version(binary) if binary else None},
    }
    try:
        login = read_login(path)
    except LoginError as exc:
        doc.update(reason_code=exc.reason_code, detail=str(exc), fix=exc.fix or _FIXES.get(exc.reason_code))
        return doc
    facts = summary(login, now)
    usable = not facts["access_expired"] or (facts["has_refresh_token"] and not facts["refresh_expired"])
    doc.update(facts)
    doc.update(logged_in=usable, reason_code="ok" if usable else "login_expired",
               fix=None if usable else _FIXES["login_expired"])
    return doc
