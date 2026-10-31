"""An exclusive file lock with a wait, for the installer: `install`, `uninstall` and `prune` hold it in the target folder, so two of
them never read the same receipt and each writes its own. fcntl on POSIX, msvcrt on Windows.

* The lock is taken on the sidecar of the given file: `install.json` -> `install.lock` (the extension is replaced).
* The lock file is created 0600 and is never deleted here: the caller decides what happens to it.
* The kernel drops the lock when its owner dies, so a left-over lock file is not a lock.
* A symlink at the lock path is refused (`lock_symlink`), before the file is opened. Windows has no O_NOFOLLOW, so the link check
  is a look before the open there, and the two are not one atomic step.
"""
from __future__ import annotations

import contextlib
import errno
import os
import stat
import time
from pathlib import Path
from typing import Iterator

try:
    import fcntl
    msvcrt = None
except ImportError:  # Windows
    fcntl = None
    import msvcrt

# Windows reparse tags of the link kind (winnt.h). The `stat` module defines them only on Windows builds.
IO_REPARSE_TAG_SYMLINK = 0xA000000C
IO_REPARSE_TAG_MOUNT_POINT = 0xA0000003
LOCK_POLL_S = 0.05


class LockError(Exception):
    """The lock cannot be taken. `reason_code` is stable: `lock_timeout` means another process holds it past `wait_s`; the
    others mean the lock file cannot be used at all."""

    def __init__(self, reason_code: str, message: str) -> None:
        super().__init__(message)
        self.reason_code = reason_code


def lock_path(path: Path) -> Path:
    """`install.json` -> `install.lock`: the sidecar that is locked."""
    return Path(path).with_suffix(".lock")


def _link_info(info: os.stat_result) -> bool:
    if stat.S_ISLNK(info.st_mode):
        return True
    return getattr(info, "st_reparse_tag", 0) in (IO_REPARSE_TAG_SYMLINK, IO_REPARSE_TAG_MOUNT_POINT)


def is_link(path: Path) -> bool:
    """A symlink, or on Windows a reparse point of the link kind (symlink, junction). Other reparse points are real files."""
    try:
        return _link_info(os.lstat(path))
    except OSError:
        return False


def _os_error(path: Path, exc: OSError, verb: str) -> LockError:
    """An OSError of one step on `path`: permission denied is `lock_permissions`, anything else `lock_invalid`."""
    if exc.errno in (errno.EACCES, errno.EPERM):
        return LockError("lock_permissions", f"sem permissão para {verb} {path} (a pasta ou o arquivo é de outro usuário? "
                         "depois de um `sudo` é comum)")
    return LockError("lock_invalid", f"não consegui {verb} {path}: {exc.strerror or exc}")


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
def file_lock(path: Path, *, wait_s: float) -> Iterator[None]:
    """Hold the exclusive lock on the sidecar of `path` for the body of the `with`, waiting up to `wait_s` seconds for it.

    Raises LockError: lock_timeout (busy past the wait), lock_symlink, lock_permissions, lock_invalid."""
    lock = lock_path(Path(path))
    try:
        lock.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    except OSError as exc:
        raise _os_error(lock.parent, exc, "criar a pasta") from None
    if is_link(lock):  # Windows has no O_NOFOLLOW: look before opening
        raise LockError("lock_symlink", f"{lock} é um link simbólico; remova-o")
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_BINARY", 0)
    try:
        fd = os.open(lock, flags, 0o600)
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            raise LockError("lock_symlink", f"{lock} é um link simbólico; remova-o") from None
        raise _os_error(lock, exc, "abrir") from None
    try:
        deadline = time.monotonic() + wait_s
        while True:
            try:
                taken = _try_lock(fd)
            except OSError as exc:  # a file system without locks (some network mounts): not a busy lock, not a traceback
                raise LockError("lock_invalid", f"não consegui travar {lock}: {exc.strerror or exc}") from None
            if taken:
                break
            if time.monotonic() >= deadline:
                raise LockError("lock_timeout", f"outro programa segura {lock}; tente de novo")
            time.sleep(LOCK_POLL_S)
        try:
            yield
        finally:
            _unlock(fd)
    finally:
        os.close(fd)
