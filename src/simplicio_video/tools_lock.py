"""The lock file of the external tracks (issue #150): what `simplicio-video update` resolved for each one, in the data folder.

One JSON document, `$SIMPLICIO_VIDEO_DATA/tools.lock.json` (default `~/.simplicio-video`): the schema, when it was written and,
for each track, its mode (`follow` the upstream, `pin` the registry commit or version, `override` by SIMPLICIO_<NAME>_REF), the
ref in use (commit sha, npm version or PyPI version), the sha256 of a PyPI wheel, and the outcome of the last attempt. A failed
attempt keeps the ref of the checkout that is still in place and records the error, so the file says what is really installed.

Reading is strict and never trusts the file: only the keys of the schema are kept, each with its type and its pattern, and a corrupt
file raises LockInvalid. The callers say so (doctor warns, the installs fall back to the registry pins). This module imports nothing
from tools.py: tools.py imports it.
"""
from __future__ import annotations

import contextlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Optional

from . import hostos

LOCK_FILE = "tools.lock.json"
SCHEMA = "simplicio.tools-lock/v1"
MODES = ("follow", "pin", "override")
STATUSES = ("ok", "failed")
KINDS = ("git", "npm", "pip")
MAX_BYTES = 256 * 1024
MAX_TEXT = 300
_NAME = re.compile(r"[a-z0-9][a-z0-9-]{0,39}")
_GIT_REF = re.compile(r"[0-9a-f]{7,40}")  # a full commit, or the short one a registry pin may keep (video-use)
_VERSION = re.compile(r"[0-9]+(?:\.[0-9]+){0,3}(?:[-+.][0-9A-Za-z.]{1,40})?")
_OVERRIDE = re.compile(r"[\x21-\x7e]{1,200}")  # an override is a ref the user typed: printable, no spaces
_BRANCH = re.compile(r"[A-Za-z0-9._/-]{1,100}")
_NPM_PACKAGE = re.compile(r"(?:@[a-z0-9][a-z0-9._-]{0,213}/)?[a-z0-9][a-z0-9._-]{0,213}")  # the npm name of an npm track
_SHA256 = re.compile(r"[0-9a-f]{64}")
_KEYS = ("kind", "source", "mode", "ref", "branch", "sha256", "status", "error", "resolved_at", "failed_at")


class LockInvalid(ValueError):
    """The lock file is there but is not a usable record: corrupt, hostile or written by something else."""


def default_data_dir() -> Path:
    """The same folder `update --check` uses for its cache: $SIMPLICIO_VIDEO_DATA, else ~/.simplicio-video."""
    explicit = os.environ.get("SIMPLICIO_VIDEO_DATA")
    return Path(explicit) if explicit else hostos.home_dir() / ".simplicio-video"


def lock_path(data_dir: Optional[Path] = None) -> Path:
    return (data_dir or default_data_dir()) / LOCK_FILE


def empty() -> dict:
    return {"schema": SCHEMA, "updated_at": 0, "tools": {}}


def _text(value: Any, limit: int = MAX_TEXT) -> Optional[str]:
    if not isinstance(value, str) or not 0 < len(value) <= limit or not value.isprintable():
        return None
    return value


def _stamp(value: Any) -> Optional[int]:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= hostos.MAX_TIMESTAMP:
        return None
    return value


def _ref_ok(kind: str, mode: str, ref: str) -> bool:
    if mode == "override":
        return bool(_OVERRIDE.fullmatch(ref))
    if kind == "git":
        return bool(_GIT_REF.fullmatch(ref))
    return bool(_VERSION.fullmatch(ref))


def _clean_entry(name: str, raw: Any) -> dict:
    if not isinstance(raw, dict):
        raise LockInvalid(f"{name}: a entrada não é um objeto")
    kind, mode, status = raw.get("kind"), raw.get("mode"), raw.get("status")
    if kind not in KINDS or mode not in MODES or status not in STATUSES:
        raise LockInvalid(f"{name}: kind, mode ou status fora do esperado")
    source = _text(raw.get("source"), 300)
    if source is None or (kind == "npm" and not _NPM_PACKAGE.fullmatch(source)) or (kind != "npm" and not source.startswith("https://")):
        raise LockInvalid(f"{name}: source inválido para uma trilha {kind} (url https, ou o nome do pacote npm)")
    entry: dict = {"kind": kind, "source": source, "mode": mode, "status": status}
    if raw.get("ref") is not None:
        ref = _text(raw.get("ref"), 200)
        if ref is None or not _ref_ok(kind, mode, ref):
            raise LockInvalid(f"{name}: ref com formato inválido")
        entry["ref"] = ref
    if status == "ok" and mode != "override" and "ref" not in entry:
        raise LockInvalid(f"{name}: uma entrada ok sem ref")
    if raw.get("branch") is not None:
        branch = raw.get("branch")
        if not isinstance(branch, str) or not _BRANCH.fullmatch(branch):
            raise LockInvalid(f"{name}: branch inválido")
        entry["branch"] = branch
    if raw.get("sha256") is not None:
        digest = raw.get("sha256")
        if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
            raise LockInvalid(f"{name}: sha256 inválido")
        entry["sha256"] = digest
    if raw.get("error") is not None:
        error = _text(raw.get("error"))
        if error is None:
            raise LockInvalid(f"{name}: error inválido")
        entry["error"] = error
    for key in ("resolved_at", "failed_at"):
        if raw.get(key) is not None:
            when = _stamp(raw.get(key))
            if when is None:
                raise LockInvalid(f"{name}: {key} inválido")
            entry[key] = when
    return entry


def clean(data: Any) -> dict:
    """The document with only the keys of the schema, each checked. Raises LockInvalid on anything else."""
    if not isinstance(data, dict) or data.get("schema") != SCHEMA:
        raise LockInvalid("não é um lock de trilhas (schema desconhecido)")
    stamp = _stamp(data.get("updated_at"))
    if stamp is None:
        raise LockInvalid("updated_at inválido")
    tools = data.get("tools")
    if not isinstance(tools, dict):
        raise LockInvalid("tools precisa ser um objeto")
    cleaned: dict = {}
    for name, raw in tools.items():
        if not isinstance(name, str) or not _NAME.fullmatch(name):
            raise LockInvalid("nome de trilha inválido")
        cleaned[name] = _clean_entry(name, raw)
    return {"schema": SCHEMA, "updated_at": stamp, "tools": cleaned}


def read_lock(path: Optional[Path] = None) -> dict:
    """The lock document, or `empty()` when there is none. Raises LockInvalid when the file is there and is not usable."""
    path = path or lock_path()
    try:
        raw = hostos.read_regular(path, MAX_BYTES)  # O_NONBLOCK and fstat: a FIFO there must not hang anything
    except (FileNotFoundError, NotADirectoryError):
        return empty()
    except hostos.NotARegularFile:
        raise LockInvalid("não é um arquivo comum") from None
    except OSError as exc:
        raise LockInvalid(f"não consegui ler: {exc.strerror or exc}") from None
    if len(raw) > MAX_BYTES:
        raise LockInvalid("grande demais")
    try:
        data = json.loads(raw.decode("utf-8"))
    except (ValueError, RecursionError):
        raise LockInvalid("não é JSON") from None
    return clean(data)


def write_lock(doc: dict, path: Optional[Path] = None) -> None:
    """Atomic: a temp file in the same folder, then os.replace. Only what `clean` accepts is written. Raises OSError (the caller
    reports it: a lock that cannot be written never stops the update) and leaves no temp file behind."""
    path = path or lock_path()
    checked = clean(doc)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=LOCK_FILE + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(checked, handle, sort_keys=True, ensure_ascii=False, indent=1)
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise
