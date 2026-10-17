"""Single host-aware install planner of simplicio-video: copy the bundled skills INTO the agent host.

Ported from simplicio-loop (`simplicio_loop/install/planner.py`, 2034e2d) with the names swapped (`simplicio-loop` ->
`simplicio-video`, `.simplicio-loop` -> `.simplicio-video`, `simplicio.loop-install-plan/v1` -> `simplicio.video-install-plan/v1`).
The video has no hooks, so only skills (and the entry file of the host, when it needs one) are written.

What it guarantees, as the loop's does:

* idempotent: a file that is already identical is not rewritten, and `changes` says what was created, updated, left alone;
* every file it writes (and every directory it creates) is registered in the ownership receipt
  `.simplicio-video/install-ownership.json`; `uninstall` removes exactly that and nothing outside the target, whatever the
  receipt says (an absolute path, `..`, a drive letter, a link that leaves the target: the receipt is refused);
* a file that is not its own is never overwritten (`left_alone`): other skills, an entry file that already exists, a link.

Where it goes beyond the loop (see ADR-0020): writes are atomic (a temporary file in the same folder, then `os.replace`), a
symlink in the way is not written through (the owner's skills are often links into a clone), and looking at a folder that
cannot be searched never raises. The bundle can be any `importlib.resources` Traversable (a wheel, a checkout, a zip).

Standard library only: `simplicio-video install` also runs under the SYSTEM python of a checkout, which has no PyYAML.
"""
from __future__ import annotations

import hashlib
import json
import os
import secrets
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Iterator, Mapping

from . import __version__, distribution, hostos

SCHEMA = "simplicio.video-install-plan/v1"
OWNERSHIP_SCHEMA = "simplicio.video-install-ownership/v1"
OWNER = "simplicio-video"
RECEIPT = Path(".simplicio-video") / "install-ownership.json"
RECEIPT_REL = RECEIPT.as_posix()
SKILLS_DEST = ".claude/skills"
MAX_RECEIPT_BYTES = 1024 * 1024  # a receipt of a few skills is a few KiB
MAX_FILE_BYTES = 16 * 1024 * 1024  # compared and digested files are SKILL.md and its references

# The entry file each host reads, from the loop's own table (scripts/install_lib.py RUNTIMES); None = the host needs none.
# The skills always land in `.claude/skills` (as in the loop's planner): Claude Code, Cursor and the others read it.
HOST_ENTRY = {
    "claude": None,
    "codex": "AGENTS.md",
    "cursor": None,
    "vscode": ".github/copilot-instructions.md",
    "grok": "AGENTS.md",
    "kiro": ".kiro/steering/simplicio-video.md",
    "antigravity": "AGENTS.md",
    "opencode": "AGENTS.md",
    "gemini": "GEMINI.md",
    "aider": "CONVENTIONS.md",
    "simplicio_agent": None,
    "openclaw": None,
}
HOSTS = tuple(HOST_ENTRY)
HOST_LAYOUT = {host: {SKILLS_DEST: "skills", **({entry: "entry"} if entry else {})} for host, entry in HOST_ENTRY.items()}


class InstallError(RuntimeError):
    """Host unknown, version drift, a receipt that cannot be trusted, or nothing to install."""


def _digest(value: Any) -> str:
    blob = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(blob.encode("utf-8")).hexdigest()


def bundle_root():
    """The package data as a Traversable (looked up at call time, so a test can swap it)."""
    return distribution.bundle_root()


# --- files: listing, comparing, writing ---------------------------------------------------------------------------------------


def iter_files(node, prefix: tuple = ()) -> Iterator[tuple]:
    """(path parts, node) of every regular file under `node`, sorted. Compiled caches are never shipped.

    `node` is a Traversable (the package) or a Path (an installed copy): in a Path, a symlink and anything that is not a regular
    file (a FIFO that would block a read, a socket) is skipped, and a folder that cannot be listed is empty."""
    try:
        children = sorted(node.iterdir(), key=lambda item: item.name)
    except OSError:
        return
    for child in children:
        if child.name == "__pycache__" or child.name.endswith(".pyc"):
            continue
        if isinstance(child, Path):
            if is_link(child):
                continue
            if hostos.is_dir(child):
                yield from iter_files(child, prefix + (child.name,))
            elif hostos.is_file(child):
                yield prefix + (child.name,), child
        elif child.is_dir():
            yield from iter_files(child, prefix + (child.name,))
        else:
            yield prefix + (child.name,), child


def read_node(node) -> bytes:
    """The bytes of a file of the package or of the host (a host file is opened O_NONBLOCK and checked with fstat)."""
    if isinstance(node, Path):
        return hostos.read_regular(node, MAX_FILE_BYTES)
    return node.read_bytes()


def atomic_write(path: Path, data: bytes) -> None:
    """Write `data` to `path` all or nothing: a temporary file in the same folder (with the mode the umask gives a normal file,
    not the 0600 of `tempfile`), flushed to disk, then `os.replace`. A failure leaves the old file and no temporary file."""
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{secrets.token_hex(4)}.tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0) | getattr(os, "O_CLOEXEC", 0)
    fd = os.open(tmp, flags, 0o666)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def is_link(path) -> bool:
    """A symlink, or on Windows a junction (a reparse point that `os.path.islink` does not call a link): both lead somewhere else."""
    return os.path.islink(path) or getattr(os.path, "isjunction", lambda _p: False)(path)


def _kind(path: Path) -> str:
    """`missing`, `file` (a regular one) or `other` (a folder, a FIFO, a link, whatever is not a plain file: not ours to replace)."""
    if is_link(path):
        return "other"
    if hostos.is_file(path):
        return "file"
    return "other" if os.path.lexists(path) else "missing"


def same_bytes(path: Path, data: bytes) -> bool:
    """True when `path` is a regular file with exactly these bytes (never reads more than `len(data) + 1` bytes of it)."""
    try:
        return hostos.read_regular(path, len(data)) == data
    except OSError:
        return False


def _first_link(base: Path, parts: tuple) -> Path | None:
    """The first symlink among `base/parts[0]`, `base/parts[0]/parts[1]`... (the file itself included), or None."""
    current = base
    for part in parts:
        current = current / part
        if is_link(current):
            return current
    return None


def _put(path: Path, data: bytes, changes: dict, root: Path, dry_run: bool, made: set) -> bool:
    """Classify one file (created, updated or unchanged) and write it only when it differs. True = the file is ours now.

    `made` collects the directories this write creates, so uninstall can remove exactly those again. Something that is not a plain
    file where ours should be (a folder, a FIFO, a link) is left alone and is not ours."""
    rel = path.relative_to(root).as_posix()
    kind = _kind(path)
    if kind == "other":
        changes["left_alone"].append(rel)
        return False
    if kind == "file" and same_bytes(path, data):
        changes["unchanged"] += 1
        return True
    changes["updated" if kind == "file" else "created"].append(rel)
    if dry_run:
        return True
    parent = path.parent
    while parent != root and not os.path.lexists(parent):
        made.add(parent.relative_to(root).as_posix())
        parent = parent.parent
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(path, data)
    return True


# --- plan ------------------------------------------------------------------------------------------------------------------------


def plan_install(
    target: str | Path,
    *,
    host: str = "claude",
    globally: bool = False,
    version: str = __version__,
) -> dict[str, Any]:
    if host not in HOSTS and host != "all":
        raise InstallError(f"host desconhecido: {host}")
    hosts = list(HOSTS) if host == "all" else [host]
    root = Path(target).resolve()
    actions = []
    for item in hosts:
        layout = {SKILLS_DEST: "skills"} if globally else HOST_LAYOUT[item]
        for dest, kind in layout.items():
            actions.append({"host": item, "kind": kind, "destination": dest, "owner": OWNER})
    plan = {
        "schema": SCHEMA,
        "version": version,
        "target": str(root),
        "scope": "global" if globally else "project",
        "hosts": hosts,
        "actions": actions,
        "entrypoint": "simplicio-video=simplicio_video.cli:main",
    }
    plan["digest"] = _digest({key: plan[key] for key in ("schema", "version", "hosts", "actions", "scope")})
    return plan


def _previous_receipt(root: Path) -> dict[str, list[str]]:
    """What an earlier install registered, so a second host installed later does not drop the first one's files.
    A receipt of another owner or schema is not read: install rewrites it, and its paths are not trusted."""
    empty = {"paths": [], "dirs": []}
    try:
        payload = json.loads(hostos.read_regular(root / RECEIPT, MAX_RECEIPT_BYTES).decode("utf-8"))
    except (OSError, ValueError, RecursionError):
        return empty
    if not isinstance(payload, dict) or payload.get("owner") != OWNER or payload.get("schema") != OWNERSHIP_SCHEMA:
        return empty
    paths, dirs = payload.get("paths"), payload.get("dirs")
    return {"paths": [p for p in paths if isinstance(p, str)] if isinstance(paths, list) else [],
            "dirs": [d for d in dirs if isinstance(d, str)] if isinstance(dirs, list) else []}


def _entry_body(host: str) -> bytes:
    """The entry file of a host. No version in it: a later install of the same host finds it identical (`unchanged`), not stale."""
    text = (f"# simplicio-video ({host})\n"
            f"Load `{SKILLS_DEST}/simplicio-video/SKILL.md` (you write the contract; the `simplicio-video` CLI executes).\n")
    return text.encode("utf-8")


def apply_plan(
    plan: Mapping[str, Any],
    *,
    dry_run: bool = False,
    bundle: Any = None,  # a path, or any importlib.resources Traversable; None = the bundle of this package
) -> dict[str, Any]:
    """Copy the bundled skills into the plan's target. Idempotent: a file that is already identical is not rewritten.
    `changes` says what was created, what was updated, how many were unchanged and what was left alone (files in the target that
    simplicio-video does not own, entry files that already exist, links).

    The ownership receipt registers exactly the files simplicio-video wrote or found identical, the entry files it created, and the
    directories it created. uninstall removes only those. Raises InstallError (nothing to install, a receipt that is not a plain
    file) and lets an OSError of the disk through: the caller reports it."""
    root = Path(plan["target"])
    owned: list[str] = []
    made: set[str] = set()
    changes: dict[str, Any] = {"created": [], "updated": [], "unchanged": 0, "left_alone": []}
    source = Path(bundle) if isinstance(bundle, str) else bundle if bundle is not None else bundle_root()
    skills_src = source.joinpath("skills")
    if not skills_src.is_dir():
        raise InstallError("skills empacotadas não encontradas no pacote instalado.")
    if _kind(root / RECEIPT) == "other":
        raise InstallError(f"{root / RECEIPT} existe e não é um arquivo comum; apague-o à mão (ou aponte outro --target) e rode de novo")
    previous = _previous_receipt(root)
    seen: set[tuple] = set()
    for action in plan.get("actions") or []:  # `all` repeats `.claude/skills` and AGENTS.md for several hosts: once is enough
        key = (action["destination"], action["kind"])
        if key in seen:
            continue
        seen.add(key)
        dest = root / action["destination"]
        if action["kind"] == "entry":  # an entry file (AGENTS.md ...): written once, never overwritten
            rel, body = dest.relative_to(root).as_posix(), _entry_body(action["host"])
            if os.path.lexists(dest):
                if rel in previous["paths"] and _kind(dest) == "file" and same_bytes(dest, body):  # the one an earlier install wrote
                    changes["unchanged"] += 1
                    owned.append(rel)
                else:
                    changes["left_alone"].append(rel)
            elif _put(dest, body, changes, root, dry_run, made):
                owned.append(rel)
            continue
        top = set()
        for parts, node in iter_files(skills_src):
            top.add(parts[0])
            link = _first_link(dest, parts)  # the owner's skill folder may be a link into a clone: never write through it
            if link is not None:
                rel = link.relative_to(root).as_posix()
                if rel not in changes["left_alone"]:
                    changes["left_alone"].append(rel)
                continue
            file_path = dest.joinpath(*parts)
            if _put(file_path, node.read_bytes(), changes, root, dry_run, made):
                owned.append(file_path.relative_to(root).as_posix())
        if hostos.is_dir(dest):
            try:
                children = sorted(os.listdir(dest))
            except OSError:
                children = []
            changes["left_alone"] += [(dest / child).relative_to(root).as_posix() for child in children
                                      if child not in top and child != "__pycache__"
                                      and (dest / child).relative_to(root).as_posix() not in changes["left_alone"]]
    if not os.path.lexists(root / RECEIPT.parent):  # the receipt's own directory is one more thing install creates
        made.add(RECEIPT.parent.as_posix())
    ownership = {
        "schema": OWNERSHIP_SCHEMA,
        "owner": OWNER,
        "version": plan["version"],
        "digest": plan["digest"],
        "paths": sorted(set(owned) | set(previous["paths"])),
        "dirs": sorted(made | set(previous["dirs"])),
    }
    body = (json.dumps(ownership, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    _put(root / RECEIPT, body, changes, root, dry_run, made)
    pending = len(changes["created"]) + len(changes["updated"])
    return {
        "schema": SCHEMA,
        "status": "dry_run" if dry_run else "applied",
        "written": 0 if dry_run else pending,
        "up_to_date": pending == 0,
        "changes": changes,
        "owned": sorted(set(owned)),
        "ownership": ownership,
        "digest": plan["digest"],
    }


# --- uninstall -------------------------------------------------------------------------------------------------------------------


def _receipt_path(root: Path, rel: str) -> Path:
    """A receipt path is relative and stays under the target, symlinks included (`root` is resolved); anything else is a receipt
    that cannot be trusted. It is read as BOTH a POSIX and a Windows path, so a receipt written on one system cannot name, on
    another, a drive letter, a rooted path (`\\x`, `//server/share`) or a `..` that its own system would not see."""
    for flavor in (PurePosixPath, PureWindowsPath):
        pure = flavor(rel)
        if not pure.parts or pure.anchor or pure.drive or ".." in pure.parts:
            raise InstallError(f"o caminho do recibo de posse sai do alvo: {rel!r}")
    path = root.joinpath(*PurePosixPath(rel).parts)
    if not Path(os.path.realpath(path.parent)).is_relative_to(root):
        raise InstallError(f"o caminho do recibo de posse sai do alvo por um link simbólico: {rel!r}")
    return path


def _listed(receipt: dict[str, Any], key: str) -> list[str]:
    value = receipt.get(key)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise InstallError(f"o recibo de posse está malformado: `{key}` deve ser uma lista de caminhos")
    return value


def _read_receipt(root: Path) -> dict[str, Any]:
    marker = root / RECEIPT
    try:
        raw = hostos.read_regular(marker, MAX_RECEIPT_BYTES)
    except (FileNotFoundError, NotADirectoryError):
        raise InstallError("sem recibo de posse do simplicio-video; recuso desinstalar arquivos que não são meus") from None
    except hostos.NotARegularFile as exc:
        raise InstallError(f"o recibo de posse está ilegível: {exc}") from None
    except OSError as exc:
        raise InstallError(f"o recibo de posse está ilegível: {exc.strerror or exc}") from None
    if len(raw) > MAX_RECEIPT_BYTES:
        raise InstallError("o recibo de posse está ilegível: grande demais")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (ValueError, RecursionError) as exc:
        raise InstallError(f"o recibo de posse está ilegível: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("owner") != OWNER:
        raise InstallError("o recibo de posse não é do simplicio-video")
    if payload.get("schema") != OWNERSHIP_SCHEMA:
        raise InstallError(f"o recibo de posse usa um esquema desconhecido ({payload.get('schema')}); rode "
                           "`simplicio-video install` uma vez para regravá-lo e desinstale em seguida")
    return payload


def uninstall(target: str | Path, *, dry_run: bool = False) -> dict[str, Any]:
    """Remove the files the receipt registers, then the registered directories that are empty by then. A directory that holds
    anything simplicio-video did not register (a user's skill, rule or hook) is kept, and so is every directory that install did
    not create. `dry_run` returns the same lists and touches nothing; then `removed` is what would go."""
    root = Path(target).resolve()
    receipt = _read_receipt(root)
    files = sorted({RECEIPT_REL, *_listed(receipt, "paths")})
    gone: set[str] = set()
    removed: list[str] = []
    skipped: list[str] = []
    for rel in files:
        path = _receipt_path(root, rel)
        if is_link(path) or hostos.is_file(path):  # a registered file that became a link loses only the link
            removed.append(rel)
            gone.add(rel)
        elif os.path.lexists(path):  # a directory where a file was registered: not ours to delete
            skipped.append(rel)
    removed_dirs: list[str] = []
    kept: list[str] = []
    for rel in sorted(set(_listed(receipt, "dirs")), key=lambda item: item.count("/"), reverse=True):
        path = _receipt_path(root, rel)
        if is_link(path) or not hostos.is_dir(path):  # a link is the user's, whatever it points at
            continue
        if all(child.relative_to(root).as_posix() in gone for child in path.iterdir()):
            removed_dirs.append(rel)
            gone.add(rel)
        else:
            kept.append(rel)
    if not dry_run:
        for rel in removed:
            _receipt_path(root, rel).unlink()
        for rel in removed_dirs:
            _receipt_path(root, rel).rmdir()
    return {
        "schema": SCHEMA,
        "status": "dry_run" if dry_run else "removed",
        "removed": removed,
        "removed_dirs": removed_dirs,
        "kept": kept,
        "skipped": skipped,
    }


def verify_plan(plan: Mapping[str, Any], expected_version: str = __version__) -> dict[str, Any]:
    if plan.get("version") != expected_version:
        raise InstallError(f"versão do descritor diverge: plano={plan.get('version')} pacote={expected_version}")
    return {"ok": True, "version": expected_version, "digest": plan.get("digest")}


# --- --prune-project-copies --------------------------------------------------------------------------------------------------------


def prune_project_copies(target: str | Path, *, dry_run: bool = False) -> dict[str, Any]:
    """Detect and remove stale project-scope copies when simplicio-video is installed globally.

    Scans the project target for: the files registered in `.simplicio-video/install-ownership.json` (if there is one), the
    simplicio-video skills in `.claude/skills` and `.cursor/skills`, and the Kiro entry file. Never deletes a foreign user file,
    a folder it only passes through, a skill folder that is a symlink (the owner's link into a clone), or anything a tampered
    receipt names outside the target (that is refused, as in the uninstall)."""
    from . import skill_sync

    root = Path(target).resolve()
    removed: list[str] = []
    removed_dirs: list[str] = []
    kept: list[str] = []
    candidates: set[Path] = set()
    dirs_to_check: set[Path] = set()

    marker = root / RECEIPT
    try:
        payload = json.loads(hostos.read_regular(marker, MAX_RECEIPT_BYTES).decode("utf-8"))
    except (OSError, ValueError, RecursionError):
        payload = None
    if isinstance(payload, dict) and payload.get("owner") == OWNER:
        for rel in _listed(payload, "paths"):
            path = _receipt_path(root, rel)
            if hostos.is_file(path):
                candidates.add(path)
        for rel in _listed(payload, "dirs"):
            dirs_to_check.add(_receipt_path(root, rel))
        candidates.add(marker)
        dirs_to_check.add(marker.parent)

    entry = root / ".kiro" / "steering" / "simplicio-video.md"
    if hostos.is_file(entry):
        candidates.add(entry)
        dirs_to_check.add(entry.parent)

    for skill_parent in (root / ".claude" / "skills", root / ".cursor" / "skills"):
        if not hostos.is_dir(skill_parent):
            continue
        for skill in skill_sync.SKILLS:
            skill_dir = skill_parent / skill
            if is_link(skill_dir) or not hostos.is_dir(skill_dir):
                continue
            candidates.update(node for _parts, node in iter_files(skill_dir))
            dirs_to_check.add(skill_dir)
        dirs_to_check.add(skill_parent)

    gone: set[Path] = set()
    for file_path in sorted(candidates):
        if is_link(file_path) or hostos.is_file(file_path):
            removed.append(file_path.relative_to(root).as_posix())
            gone.add(file_path)
            if not dry_run:
                try:
                    file_path.unlink()
                except OSError:
                    pass

    all_dirs: set[Path] = set()
    for directory in dirs_to_check:
        current = directory
        while current != root and current.parent != current:
            all_dirs.add(current)
            current = current.parent

    for dir_path in sorted(all_dirs, key=lambda d: len(d.parts), reverse=True):
        if is_link(dir_path) or not hostos.is_dir(dir_path):
            continue
        try:
            remaining = [child for child in dir_path.iterdir() if child not in gone]
            rel = dir_path.relative_to(root).as_posix()
            if not remaining:
                removed_dirs.append(rel)
                gone.add(dir_path)
                if not dry_run:
                    dir_path.rmdir()
            elif rel not in kept:
                kept.append(rel)
        except OSError:
            pass

    return {
        "schema": SCHEMA,
        "status": "dry_run" if dry_run else "removed",
        "removed": sorted(removed),
        "removed_dirs": sorted(removed_dirs),
        "kept": sorted(kept),
    }
