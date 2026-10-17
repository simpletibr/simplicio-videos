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
* HOSTILE OR CORRUPT FILE: the read is capped at 1 MiB, deep nesting, a number that is no date (`1e999`, year 33658) and a
  folder or file this user cannot open are all a `reason_code` (`login_invalid`, `login_permissions`), never an exception.
* LOCK: `logout` deletes the file under the exclusive lock on the sidecar `login.lock`, the same file the Runtime locks
  (runtime_auth.rs `auth_lock`: the login file name with the extension changed to `lock`, 20 s). fcntl on POSIX, msvcrt on
  Windows. NOT VERIFIED: that msvcrt.locking and the Runtime's LockFileEx exclude each other on a real Windows host.
* LOGOUT ONLY DELETES A LOGIN: `SIMPLICIO_AUTH_FILE` can point anywhere, so `logout --yes` first checks that the target is a
  small regular file holding a JSON object with a login's keys, and refuses (`not_a_login_file`) anything else.
"""
from __future__ import annotations

import contextlib
import errno
import json
import math
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
MAX_LOGIN_BYTES = 1 << 20  # a real login is about 2 KiB: a megabyte is already absurd, and bounds what a hostile file costs
LOGIN_KEYS = ("access_token", "refresh_token", "verification")  # what a login written by the Runtime (or the loop) has

_VERSION = re.compile(r"simplicio\s+v?(\d+\.\d+\.\d+)")
_EMAIL = re.compile(r"([^@\s])[^@\s]*@([^@\s]+\.[^@\s]+)")
_DIGITS = re.compile(r"[0-9]{1,13}")


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


# --- errors that are a reason_code, not a traceback ---------------------------------------------------------------------


def _link_info(info: os.stat_result) -> bool:
    if stat.S_ISLNK(info.st_mode):
        return True
    return getattr(info, "st_reparse_tag", 0) in (IO_REPARSE_TAG_SYMLINK, IO_REPARSE_TAG_MOUNT_POINT)


def is_link(path: Path) -> bool:
    """A symlink, or on Windows a reparse point of the link kind (symlink, junction).

    Other reparse points (a OneDrive placeholder, a dedup stub) are real files and are not refused."""
    try:
        return _link_info(os.lstat(path))
    except OSError:
        return False


def _symlink_error(path: Path) -> LoginError:
    return LoginError("login_symlink", f"{path} é um link simbólico; remova-o e rode: simplicio-video login")


def _denied(path: Path, verb: str = "ler", folder: Optional[Path] = None) -> LoginError:
    """The OS said no (EACCES, EPERM): a folder or file of another user, often left by a `sudo`, or a mode that closes it."""
    where = folder or Path(path).parent
    fix = (f"ajuste o dono e as permissões de {where}" if hostos.is_windows()
           else f'sudo chown -R "$USER" "{where}" (e rode de novo; o login só funciona numa pasta sua)')
    return LoginError("login_permissions", f"sem permissão para {verb} {path} (a pasta ou o arquivo é de outro usuário? "
                      "depois de um `sudo` é comum)", fix)


def _os_error(path: Path, exc: OSError, verb: str, folder: Optional[Path] = None) -> LoginError:
    """An OSError of one step on `path` as a LoginError: permission denied is `login_permissions`, anything else `login_invalid`."""
    if exc.errno in (errno.EACCES, errno.EPERM):
        return _denied(path, verb, folder)
    return LoginError("login_invalid", f"não consegui {verb} {path}: {exc.strerror or exc}")


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
        return  # no folder yet, or one that cannot be looked at: the open that follows says which
    if info.st_mode & 0o022 and not (info.st_mode & stat.S_ISVTX and info.st_uid == os.geteuid()):
        raise LoginError("login_permissions", f"{path.parent} pode ser alterada pelo grupo ou por outros "
                         f"(modo {info.st_mode & 0o777:03o}); rode: chmod 700 {path.parent}", f"chmod 700 {path.parent}")


# --- read -----------------------------------------------------------------------------------------------------------


def _open_for_read(path: Path) -> int:
    """A descriptor for `path`, opened without following a symlink and without blocking on a FIFO.

    LoginError: login_missing (also when a parent is a file), login_symlink, login_permissions, login_invalid."""
    flags = (os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NONBLOCK", 0)
             | getattr(os, "O_BINARY", 0))
    try:
        return os.open(path, flags)
    except (FileNotFoundError, NotADirectoryError):
        raise LoginError("login_missing", f"não há arquivo de login em {path}; rode: simplicio-video login") from None
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            raise _symlink_error(path) from None
        raise _os_error(path, exc, "ler") from None


def _read_bounded(fd: int, path: Path) -> bytes:
    """At most MAX_LOGIN_BYTES + 1 bytes, so a file over the cap is told apart without loading it."""
    chunks: list = []
    total = 0
    try:
        while total <= MAX_LOGIN_BYTES:
            chunk = os.read(fd, min(65536, MAX_LOGIN_BYTES + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
    except OSError as exc:
        raise _os_error(path, exc, "ler") from None
    return b"".join(chunks)


def _parse(raw: bytes) -> Any:
    """The JSON in `raw`, or None when it is not UTF-8 JSON: a corrupt or hostile file (deep nesting included)."""
    try:
        return json.loads(raw.decode("utf-8"))
    except (ValueError, RecursionError):  # UnicodeDecodeError is a ValueError
        return None


def read_login(path: Optional[Path] = None) -> dict:
    """The login file as a dict. Raises LoginError: login_missing, login_symlink, login_permissions, login_invalid.

    Only a regular file is read (a FIFO would hang, a directory has no content), through O_NOFOLLOW and O_NONBLOCK where
    they exist, and the checks use the descriptor that is read, so nothing can change between the check and the read.
    """
    path = Path(path) if path else login_path()
    if is_link(path):
        raise _symlink_error(path)
    _check_parent(path)
    fd = _open_for_read(path)
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
        raw = _read_bounded(fd, path)
    finally:
        os.close(fd)
    if len(raw) > MAX_LOGIN_BYTES:
        raise LoginError("login_invalid", f"{path} é grande demais para ser um login (mais de {MAX_LOGIN_BYTES // 1024} KiB); "
                         "rode: simplicio-video login")
    data = _parse(raw)
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
    try:
        lock.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    except OSError as exc:
        raise _os_error(lock.parent, exc, "criar a pasta", folder=lock.parent) from None
    if is_link(lock):  # Windows has no O_NOFOLLOW: look before opening
        raise LoginError("login_symlink", f"{lock} é um link simbólico; remova-o")
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_BINARY", 0)
    try:
        fd = os.open(lock, flags, 0o600)
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            raise LoginError("login_symlink", f"{lock} é um link simbólico; remova-o") from None
        raise _os_error(lock, exc, "abrir") from None
    try:
        info = os.fstat(fd)
        if strict and not hostos.is_windows() and _foreign_owner(info):  # another user's lock file would let it stall us
            raise LoginError("login_permissions", f"{lock} pertence a outro usuário; remova-o")
        if strict and not hostos.is_windows() and info.st_mode & 0o077:
            raise LoginError("login_permissions", f"{lock} pode ser aberto pelo grupo ou por outros "
                             f"(modo {info.st_mode & 0o777:03o}); rode: chmod 600 {lock}")
        deadline = time.monotonic() + wait_s
        while True:
            try:
                taken = _try_lock(fd)
            except OSError as exc:  # a file system without locks (some network mounts): not a busy lock, not a traceback
                raise LoginError("login_invalid", f"não consegui travar {lock}: {exc.strerror or exc}") from None
            if taken:
                break
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


# --- logout: delete the file, but only a login ------------------------------------------------------------------------


def _not_a_login(path: Path, why: str) -> LoginError:
    return LoginError("not_a_login_file", f"{path} {why}, então nada foi apagado. Se for mesmo um login estragado, "
                      "remova-o à mão.")


def _require_login_shape(path: Path) -> None:
    """Raise `not_a_login_file` unless `path` is a small regular file with a JSON object that has a login's keys.

    The MODE is not checked on purpose: a login that others can read is exactly the one to get rid of. LoginError of the
    open (login_missing: it is already gone; login_permissions; login_symlink: swapped for a link meanwhile) pass through."""
    fd = _open_for_read(path)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise _not_a_login(path, "não é um arquivo comum (pasta, fifo, dispositivo...)")
        raw = _read_bounded(fd, path)
    finally:
        os.close(fd)
    if len(raw) > MAX_LOGIN_BYTES:
        raise _not_a_login(path, f"é grande demais para ser um login (mais de {MAX_LOGIN_BYTES // 1024} KiB)")
    data = _parse(raw)
    if not isinstance(data, dict) or not any(key in data for key in LOGIN_KEYS):
        raise _not_a_login(path, "não é um JSON com access_token, refresh_token ou verification (a forma de um login)")


def _still_there(path: Path) -> bool:
    """True when `path` is a login that can go; False when it is already gone. Raises `not_a_login_file` for a stranger."""
    try:
        _require_login_shape(path)
    except LoginError as exc:
        if exc.reason_code == "login_missing":
            return False
        raise
    return True


def clear_login(path: Optional[Path] = None) -> bool:
    """Delete the login file under the lock (this logs the Runtime out too). True if a file was removed.

    A missing file is not an error and creates nothing (no folder, no lock file). Anything that is not a login file (a folder, a
    FIFO, an ssh key that SIMPLICIO_AUTH_FILE points at...) is refused with `not_a_login_file` and left alone, without even a
    lock file next to it. A symlink is removed (never what it points to). The shape is checked once before the lock and again
    under it, because the file can change while this waits for the Runtime."""
    path = Path(path) if path else login_path()
    try:
        info = os.lstat(path)
    except (FileNotFoundError, NotADirectoryError):
        return False
    except OSError as exc:
        raise _os_error(path, exc, "examinar") from None
    link = _link_info(info)
    if stat.S_ISDIR(info.st_mode) and not link:
        raise _not_a_login(path, "é uma pasta")
    if not link and not _still_there(path):
        return False
    with file_lock(path):
        if not link and not _still_there(path):
            return False
        try:
            os.unlink(path)  # never follows a symlink
        except FileNotFoundError:
            return False
        except OSError as exc:
            raise _os_error(path, exc, "apagar") from None
    return True


# --- what the file says (never a token) -----------------------------------------------------------------------------


def _timestamp(value: Any, name: str) -> int:
    """A login's `*_expires_at`: seconds since the epoch, 0 for none or unknown. Anything else is `login_invalid`.

    `1e999` (OverflowError in `int`), NaN, a negative number, a bool, a list, a long string and `999999999999` (year 33658:
    a valid i64 for the Runtime, an instant no date can hold) all land here instead of in a traceback."""
    if value is None or value == "":
        return 0
    seconds: Optional[int] = None
    if isinstance(value, bool):
        pass
    elif isinstance(value, int):
        seconds = value
    elif isinstance(value, float):
        seconds = int(value) if math.isfinite(value) else None
    elif isinstance(value, str) and _DIGITS.fullmatch(value.strip()):
        seconds = int(value)
    if seconds is None or not 0 <= seconds <= hostos.MAX_TIMESTAMP:
        raise LoginError("login_invalid", f"o campo {name} do arquivo de login não é um instante válido (segundos desde 1970, "
                         "até o ano 9999); rode: simplicio-video login")
    return seconds


def mask_email(email: str) -> str:
    """`wesley@gmail.com` -> `w***@gmail.com`; anything that is not an address gives ''."""
    found = _EMAIL.fullmatch(email.strip())
    return f"{found.group(1)}***@{found.group(2)}" if found else ""


def summary(login: Mapping[str, Any], now: Optional[float] = None) -> dict:
    """Public facts of a login: no token, no unmasked e-mail. Raises LoginError (login_invalid) for a date that is no instant."""
    stamp = time.time() if now is None else now
    verification = login.get("verification")
    validated = verification.get("validated") if isinstance(verification, dict) else None
    validated = validated if isinstance(validated, dict) else {}
    user = validated.get("user") if isinstance(validated.get("user"), dict) else {}
    entitlement = validated.get("entitlement")
    access_expires = _timestamp(login.get("access_expires_at"), "access_expires_at")
    refresh_expires = _timestamp(login.get("refresh_token_expires_at"), "refresh_token_expires_at")
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
    found = hostos.which("simplicio", environ.get("PATH", ""), environ)
    if found:
        return found
    managed = hostos.home_dir(environ) / RUNTIME_DIR / "bin" / hostos.exe_name("simplicio")
    return managed if hostos.is_file(managed) and os.access(managed, os.X_OK) else None


def runtime_version(binary: Path, timeout: float = 10) -> Optional[str]:
    """`simplicio --version` -> '3.10.0', or None when it does not answer. Its output is read as UTF-8 with `replace`."""
    try:
        done = subprocess.run([str(binary), "--version"], capture_output=True, encoding="utf-8", errors="replace",
                              timeout=timeout, stdin=subprocess.DEVNULL)
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
        facts = summary(login, now)
    except LoginError as exc:
        doc.update(reason_code=exc.reason_code, detail=str(exc), fix=exc.fix or _FIXES.get(exc.reason_code))
        return doc
    usable = not facts["access_expired"] or (facts["has_refresh_token"] and not facts["refresh_expired"])
    doc.update(facts)
    doc.update(logged_in=usable, reason_code="ok" if usable else "login_expired",
               fix=None if usable else _FIXES["login_expired"])
    return doc
