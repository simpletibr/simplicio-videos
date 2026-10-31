"""Single host-aware install planner of simplicio-video: copy the bundled skills INTO the agent host.

Ported from simplicio-loop (`simplicio_loop/install/planner.py`, 2034e2d) with the names swapped (`simplicio-loop` ->
`simplicio-video`, `.simplicio-loop` -> `.simplicio-video`, `simplicio.loop-install-plan/v1` -> `simplicio.video-install-plan/v1`).
The video has no hooks, so only skills (and the entry file of the host, when it needs one) are written.

What it guarantees, as the loop's does: idempotent (a file that is already identical is not rewritten) and an ownership receipt
`.simplicio-video/install-ownership.json` that registers what was written. Where it goes beyond the loop (ADR-0020, review of #117),
because the receipt is a file in the user's repository and a repository can be hostile:

* the receipt keeps the sha256 of every file. A file is deleted (uninstall, prune) or overwritten (a later install) only when it is in
  the receipt AND its sha256 still matches what was written: a file the user edited is `left_alone`, with a warning;
* a path in the receipt must be one the registry (hosts x skills) can produce: the skill folders, the entry files of the hosts and
  the receipt itself. Anything else makes the uninstall and the prune refuse the whole receipt; an install ignores it and says so;
* a file that already existed before the first install is never overwritten and never becomes "ours", identical or not;
* the folders the install CREATES (`skills`, `simplicio-video`, `.simplicio-video`) are never links (refused, nothing written);
  the host base folder (`~/.claude`) may be one (dotfiles): it is resolved once and recorded in the receipt, and the uninstall
  refuses if the link now points elsewhere;
* writes are atomic, `--verify` compares the files with the receipt and with the package, and installs in the same target at the
  same time are serialized by `.simplicio-video/install.lock`.

The bundle can be any `importlib.resources` Traversable (a wheel, a checkout, a zip). Standard library only: `simplicio-video install`
also runs under the SYSTEM python of a checkout, which has no PyYAML.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import secrets
import stat
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Iterator, Mapping

from . import __version__, distribution, hostos
from .skill_sync import HOST_SKILL_ROOTS, SKILLS

SCHEMA = "simplicio.video-install-plan/v1"
OWNERSHIP_SCHEMA = "simplicio.video-install-ownership/v1"
OWNER = "simplicio-video"
RECEIPT = Path(".simplicio-video") / "install-ownership.json"
RECEIPT_REL = RECEIPT.as_posix()
LOCK_FILE = "install.json"  # `lockfile.file_lock` swaps the extension: the lock file is `.simplicio-video/install.lock`
LOCK_REL = (RECEIPT.parent / "install.lock").as_posix()
LOCK_WAIT_S = 10.0  # a normal install takes milliseconds: waiting this long means another one is stuck
SKILLS_DEST = HOST_SKILL_ROOTS["claude"]  # where every install lands, and what `--verify` is anchored to
GLOBAL_ROOTS = tuple(HOST_SKILL_ROOTS.values())  # the 11 folders of the loop's skill_sync: `--global` puts the skills in all of them
MAX_RECEIPT_BYTES = 1024 * 1024  # a receipt of a few skills is a few KiB
MAX_FILE_BYTES = 16 * 1024 * 1024  # compared and digested files are SKILL.md and its references
MAX_REL = 512  # a path of the receipt; longer is not something the registry can produce
_HEX = re.compile(r"[0-9a-f]{64}")

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

# What the registry can produce, derived from it: nothing in a receipt is trusted outside these.
ENTRY_FILES = frozenset(entry for entry in HOST_ENTRY.values() if entry)
# The first folder of a destination that has more than one component (`.claude`, `.codex`, `.config`, `.github`, `.kiro`...). The user owns
# it (it may be a link into a dotfiles repository); everything the install creates below it, and `.simplicio-video`, may never be a link.
_DESTINATIONS = [*GLOBAL_ROOTS, *(dest for layout in HOST_LAYOUT.values() for dest in layout)]
HOST_BASES = tuple(sorted({PurePosixPath(dest).parts[0] for dest in _DESTINATIONS if len(PurePosixPath(dest).parts) > 1}))
_KNOWN_DIRS = frozenset({RECEIPT.parent.as_posix(),
                         *(str(parent) for dest in [*GLOBAL_ROOTS, *ENTRY_FILES] for parent in PurePosixPath(dest).parents
                           if str(parent) != "."),
                         *GLOBAL_ROOTS})
_ROOT_PARTS = tuple(tuple(root.split("/")) for root in GLOBAL_ROOTS)


class InstallError(RuntimeError):
    """Host unknown, version drift, a receipt that cannot be trusted, or nothing to install."""


class InstallRefused(InstallError):
    """A folder the install creates is a link (or the base folder is a broken one): nothing was written; the command says exit 2.

    `detail` is the reason without the closing sentence (the `--verify` writes nothing, ever, and does not say so), `path` the folder."""

    def __init__(self, detail: str, path: str = "") -> None:
        super().__init__(f"{detail}. Nada foi escrito.")
        self.detail, self.path = detail, path


class NoReceipt(InstallError):
    """There is no ownership receipt in the target (never installed, or the receipt was deleted)."""


def _digest(value: Any) -> str:
    blob = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(blob.encode("utf-8")).hexdigest()


def bundle_root():
    """The package data as a Traversable (looked up at call time, so a test can swap it)."""
    return distribution.bundle_root()


# --- the registry: which paths a receipt may name -----------------------------------------------------------------------------


def _plain_parts(rel: Any) -> list | None:
    """`rel` split on `/` when it is a plain relative path of ordinary names, else None (a NUL, a backslash, a colon, `..`)."""
    if not isinstance(rel, str) or not rel or len(rel) > MAX_REL or any(char in rel for char in "\0\\:"):
        return None
    parts = rel.split("/")
    return None if any(part in ("", ".", "..") for part in parts) else parts


def known_file(rel: Any) -> bool:
    """True when the registry can produce `rel` as a FILE: inside a skill folder of one of the 11 host roots, an entry file of a host, or
    the receipt."""
    parts = _plain_parts(rel)
    if parts is None:
        return False
    if rel == RECEIPT_REL or rel in ENTRY_FILES:
        return True
    return any(tuple(parts[:len(root)]) == root and len(parts) >= len(root) + 2 and parts[len(root)] in SKILLS for root in _ROOT_PARTS)


def known_dir(rel: Any) -> bool:
    """True when the registry can produce `rel` as a FOLDER the install creates."""
    parts = _plain_parts(rel)
    if parts is None:
        return False
    if rel in _KNOWN_DIRS:
        return True
    return any(tuple(parts[:len(root)]) == root and len(parts) >= len(root) + 1 and parts[len(root)] in SKILLS for root in _ROOT_PARTS)


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


FILE_ATTRIBUTE_REPARSE_POINT = 0x400
_REPARSE_LINK_TAGS = (0xA000000C, 0xA0000003)  # IO_REPARSE_TAG_SYMLINK and IO_REPARSE_TAG_MOUNT_POINT (a junction), winnt.h


def _reparse_link(info) -> bool:
    """A Windows reparse point of the link kind. Python 3.10 and 3.11 have no `os.path.isjunction`: the attributes of `lstat` say it.
    A reparse point whose tag is something else (a OneDrive placeholder) is a real folder; without a tag, it is not trusted."""
    if not getattr(info, "st_file_attributes", 0) & FILE_ATTRIBUTE_REPARSE_POINT:
        return False
    tag = getattr(info, "st_reparse_tag", None)
    return tag is None or tag in _REPARSE_LINK_TAGS


def is_link(path) -> bool:
    """A symlink, or on Windows a junction (a reparse point that `os.path.islink` does not call a link): both lead somewhere else.
    Never raises: a folder that cannot be searched is not a link."""
    try:
        info = os.lstat(path)
    except (OSError, ValueError):
        return False
    if stat.S_ISLNK(info.st_mode) or _reparse_link(info):
        return True
    isjunction = getattr(os.path, "isjunction", None)  # 3.12+
    return bool(isjunction and isjunction(path))


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
    except (OSError, ValueError):
        return False


def sha256_of(path: Path) -> str | None:
    """The sha256 of the bytes of the REGULAR file `path`, or None when it cannot be read as one. `read_regular` hands back at most
    `MAX_FILE_BYTES + 1` bytes: a file over the cap has no digest (the digest of its first bytes would be one a planted receipt could
    carry for a victim's huge file), so it is never "ours"."""
    try:
        data = hostos.read_regular(path, MAX_FILE_BYTES)
    except (OSError, ValueError):
        return None
    return None if len(data) > MAX_FILE_BYTES else hashlib.sha256(data).hexdigest()


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _first_link(base: Path, parts) -> Path | None:
    """The first link among `base/parts[0]`, `base/parts[0]/parts[1]`..., or None."""
    current = base
    for part in parts:
        current = current / part
        if is_link(current):
            return current
    return None


def _phys(root: Path, rel: str, bases: Mapping[str, str]) -> Path:
    """Where the logical path `rel` (relative to the target) really is: under the resolved base folder when that one is a link."""
    parts = rel.split("/")
    if parts[0] in bases:
        return Path(bases[parts[0]]).joinpath(*parts[1:])
    return root.joinpath(*parts)


# --- the lock -----------------------------------------------------------------------------------------------------------------


@contextlib.contextmanager
def _locked(root: Path, dry_run: bool):
    """An exclusive lock on `.simplicio-video/install.lock` (0600, the kernel drops it when the owner dies) for a real install,
    uninstall or prune, so two of them in the same target never read the same receipt and each write its own. A dry run takes none:
    it creates nothing, not even the folder."""
    if dry_run:
        yield
        return
    from . import lockfile

    lock = root / RECEIPT.parent / "install.lock"
    with contextlib.ExitStack() as stack:
        try:
            stack.enter_context(lockfile.file_lock(root / RECEIPT.parent / LOCK_FILE, wait_s=LOCK_WAIT_S))
        except lockfile.LockError as exc:
            if exc.reason_code == "lock_timeout":
                raise InstallError(f"outro `simplicio-video install` está rodando neste alvo (segura {lock}); espere ele terminar "
                                   "e rode de novo") from None
            raise InstallError(f"não consegui travar {lock}: {exc}") from None
        yield


def _drop_lock(root: Path) -> None:
    """The uninstall removes the lock file it was holding (after releasing it), like every other file of the install."""
    with contextlib.suppress(OSError):
        (root / RECEIPT.parent / "install.lock").unlink()


# --- the receipt: reading it, and what is trusted in it ------------------------------------------------------------------------


def _listed(receipt: dict[str, Any], key: str) -> list[str]:
    value = receipt.get(key)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise InstallError(f"o recibo de posse está malformado: `{key}` deve ser uma lista de caminhos")
    return value


def _check_rel(rel: Any, *, directory: bool) -> str:
    """A path of the receipt, or InstallError. It is read as BOTH a POSIX and a Windows path (a receipt written on one system cannot
    name, on another, a drive letter, a rooted path or a `..` that its own system would not see), then against the registry."""
    if not isinstance(rel, str):
        raise InstallError(f"o recibo de posse está malformado: caminho que não é texto: {rel!r}")
    if "\0" in rel or len(rel) > MAX_REL:
        raise InstallError("o recibo de posse tem um caminho inválido (byte nulo ou longo demais): recusado")
    for flavor in (PurePosixPath, PureWindowsPath):
        pure = flavor(rel)
        if not pure.parts or pure.anchor or pure.drive or ".." in pure.parts:
            raise InstallError(f"o caminho do recibo de posse sai do alvo: {rel!r}")
    if not (known_dir(rel) if directory else known_file(rel)):
        raise InstallError(f"o recibo de posse lista um caminho que o simplicio-video nunca instala: {rel!r}")
    return rel


def _read_receipt(root: Path) -> dict[str, Any]:
    marker = root / RECEIPT
    if is_link(marker):  # a repository could point it at the receipt of the victim's own home
        raise InstallError(f"o recibo de posse é um link ({marker}): recuso lê-lo; apague o link e rode `simplicio-video install` de novo")
    try:
        raw = hostos.read_regular(marker, MAX_RECEIPT_BYTES)
    except (FileNotFoundError, NotADirectoryError):
        raise NoReceipt("sem recibo de posse do simplicio-video; recuso desinstalar arquivos que não são meus") from None
    except hostos.NotARegularFile as exc:
        raise InstallError(f"o recibo de posse está ilegível: {exc}") from None
    except (OSError, ValueError) as exc:
        raise InstallError(f"o recibo de posse está ilegível: {getattr(exc, 'strerror', None) or exc}") from None
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


def _parse_receipt(payload: dict[str, Any]) -> dict[str, Any]:
    """`{"files": {rel: sha256 | None}, "dirs": [...], "bases": {...}}`, or InstallError when anything is not what the registry can
    produce. A file without a digest is kept as None: it is listed, and never deleted."""
    digests = payload.get("sha256")
    if digests is None:
        raise InstallError("o recibo de posse é de uma versão sem `sha256` (ou foi adulterado): sem o digest de cada arquivo eu não sei o que "
                           "ainda é meu, então recuso apagar; apague à mão os arquivos do simplicio-video que ele lista e o recibo, e rode "
                           "`simplicio-video install` de novo")
    if not isinstance(digests, dict):
        raise InstallError("o recibo de posse está malformado: `sha256` deve ser um objeto")
    files: dict[str, str | None] = {}
    for rel in _listed(payload, "paths"):
        _check_rel(rel, directory=False)
        value = digests.get(rel)
        files[rel] = value if isinstance(value, str) and _HEX.fullmatch(value) else None
    dirs = [_check_rel(rel, directory=True) for rel in _listed(payload, "dirs")]
    raw = payload.get("bases", {})
    if not isinstance(raw, dict):
        raise InstallError("o recibo de posse está malformado: `bases` deve ser um objeto")
    bases: dict[str, str] = {}
    for name, real in raw.items():
        if name not in HOST_BASES or not isinstance(real, str) or not real or "\0" in real or len(real) > 4096 or not os.path.isabs(real):
            raise InstallError(f"o recibo de posse tem uma pasta base inválida: {name!r}")
        bases[name] = real
    return {"files": files, "dirs": list(dict.fromkeys(dirs)), "bases": bases}


def _confirm_bases(root: Path, bases: Mapping[str, str]) -> None:
    """A base folder that the receipt says was a link must still be that link: the files are where the receipt says only then."""
    for name, recorded in bases.items():
        if os.path.realpath(root / name) != os.path.realpath(recorded):
            raise InstallError(f"o link `{name}` não aponta mais para onde apontava no install (o recibo de posse diz {recorded}); "
                               "recoloque o link, ou apague os arquivos do simplicio-video à mão e o recibo")


def _inside_problem(root: Path, bases: Mapping[str, str], rel: str) -> str | None:
    """Why `rel` cannot be touched through the folders above it, or None. The folders above `rel` are not links, except the base folder the
    receipt recorded; and nothing leaves the target by a link."""
    parts = rel.split("/")
    if parts[0] in bases:
        link = _first_link(Path(bases[parts[0]]), parts[1:-1])
    else:
        if not Path(os.path.realpath(root.joinpath(*parts[:-1]) if len(parts) > 1 else root)).is_relative_to(root):
            return f"o caminho do recibo de posse sai do alvo por um link simbólico: {rel!r}"
        link = _first_link(root, parts[:-1])
    return None if link is None else f"o recibo de posse passa por um link ({link}) que o install nunca cria: {rel!r}"


def _load_receipt(root: Path, *, strict_links: bool = True) -> dict[str, Any]:
    """The receipt of `root`, fully checked: the owner and schema, every path against the registry, the recorded base links against
    the live ones. InstallError (NoReceipt when there is none) before anything is touched.

    A path whose folders above it are now a link (the user moved `~/.config/opencode` into a dotfiles repository after the install) is
    `unsafe`: with `strict_links` the whole receipt is refused; without it, the path is only set aside (`receipt["unsafe"]`, path ->
    reason) so that the others stay ours. Nothing is ever touched through it either way."""
    receipt = _parse_receipt(_read_receipt(root))
    _confirm_bases(root, receipt["bases"])
    unsafe: dict[str, str] = {}
    for rel in [*receipt["files"], *receipt["dirs"]]:
        problem = _inside_problem(root, receipt["bases"], rel)
        if problem is not None:
            if strict_links:
                raise InstallError(problem)
            unsafe[rel] = problem
    receipt["unsafe"] = unsafe
    return receipt


def _previous_receipt(root: Path) -> dict[str, Any]:
    """What an earlier install registered, so a second host installed later does not drop the first one's files.

    Everything it lists passes the same checks as the uninstall's. A receipt that does not (planted in a cloned repository, edited,
    from another owner or schema) is NOT inherited: it is ignored with a warning and this install writes a new one. A single path whose
    folders became a link is dropped, with a warning, and the others stay."""
    empty: dict[str, Any] = {"files": {}, "dirs": [], "bases": {}, "warnings": []}
    try:
        receipt = _load_receipt(root, strict_links=False)
    except NoReceipt:
        return empty
    except InstallError as exc:
        return {**empty, "warnings": [f"o recibo de posse anterior foi ignorado e será regravado: {exc}"]}
    unsafe = receipt.pop("unsafe")
    receipt["files"] = {rel: digest for rel, digest in receipt["files"].items() if rel not in unsafe}
    receipt["dirs"] = [rel for rel in receipt["dirs"] if rel not in unsafe]
    receipt["warnings"] = sorted({_folder_of(rel) + ": um link no caminho; esses arquivos saíram do recibo e não foram tocados"
                                  for rel in unsafe})
    return receipt


def _folder_of(rel: str) -> str:
    """The skills root a path of the receipt lives under (`.config/opencode/skills`), else the path itself."""
    for dest in GLOBAL_ROOTS:
        if rel.startswith(dest + "/"):
            return dest
    return rel


# --- plan ---------------------------------------------------------------------------------------------------------------------


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
    if globally:  # the skills in all the 11 folders of the loop, whatever `--host` says (it is ignored, as in the loop)
        actions = [{"host": key, "kind": "skills", "destination": dest, "owner": OWNER} for key, dest in HOST_SKILL_ROOTS.items()]
    else:
        for item in hosts:
            for dest, kind in HOST_LAYOUT[item].items():
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


def _entry_body(host: str) -> bytes:
    """The entry file of a host. No version in it: a later install of the same host finds it identical (`unchanged`), not stale."""
    text = (f"# simplicio-video ({host})\n"
            f"Load `{SKILLS_DEST}/simplicio-video/SKILL.md` (you write the contract; the `simplicio-video` CLI executes).\n")
    return text.encode("utf-8")


def _unique_actions(plan: Mapping[str, Any]) -> list:
    """`all` repeats `.claude/skills` and AGENTS.md for several hosts: once is enough."""
    seen: set[tuple] = set()
    out = []
    for action in plan.get("actions") or []:
        key = (action["destination"], action["kind"])
        if key not in seen:
            seen.add(key)
            out.append(action)
    return out


def _resolve_bases(root: Path, actions: list, skill_files: list) -> tuple[dict[str, str], dict[str, str]]:
    """Before anything is written: the folders the install creates must not be links, and a host base folder that is one (`~/.claude`
    into a dotfiles repository) is resolved ONCE here; the install operates on that real path and records it. Returns
    `(bases, skipped)`.

    A link in the PRIMARY destination (`.claude/skills`) or in an entry file's folders refuses the whole install (InstallRefused, nothing
    written). In one of the other 10 skill folders of `--global` it only skips that folder (`skipped`: destination -> reason): a symlinked
    `~/.config/opencode` must not stop the install into `~/.claude/skills`."""
    bases: dict[str, str] = {}
    skipped: dict[str, str] = {}
    receipt_dir = root / RECEIPT.parent
    if is_link(receipt_dir):
        raise InstallRefused(f"{RECEIPT.parent.as_posix()} é um link ({os.path.realpath(receipt_dir)}): o install cria essa pasta e não "
                             "escreve por dentro de link; apague o link ou use outro --target", RECEIPT.parent.as_posix())
    for action in actions:
        destination = action["destination"]
        dest = destination.split("/")
        if action["kind"] == "skills":  # every component of the root and of the folders inside the skills is created by us
            folders, below = dest[1:], [tuple(parts[:-1]) for parts, _node in skill_files]
        else:  # an entry file: the folders above it; the file itself (a link to CLAUDE.md, say) is the user's and `_kind` leaves it alone
            folders, below = dest[1:-1], [()]
            if len(dest) == 1:
                continue
        base = dest[0]
        base_dir = root / base
        real_base, new_base, problem = base_dir, None, None
        if is_link(base_dir):
            real = Path(os.path.realpath(base_dir))
            if hostos.is_dir(real):
                new_base, real_base = str(real), real
            else:
                problem = f"{base} é um link que não leva a uma pasta ({real}): conserte o link ou use outro --target"
        for extra in below:
            if problem is not None:
                break
            link = _first_link(real_base, [*folders, *extra])
            if link is not None:
                shown = link.relative_to(real_base).as_posix() if link.is_relative_to(real_base) else str(link)
                problem = (f"{base}/{shown} é um link: o install cria essa pasta e não escreve por dentro de link (o uninstall não "
                           "saberia depois onde os arquivos foram parar); apague o link ou use outro --target")
        if problem is None:
            if new_base is not None:
                bases[base] = new_base
        elif destination == SKILLS_DEST or action["kind"] != "skills":
            raise InstallRefused(problem, destination)
        else:
            skipped[destination] = problem
    return bases, skipped


class _Run:
    """The state of one apply: what is ours now (`owned`: path -> sha256), what was decided, the folders created, the report."""

    def __init__(self, root: Path, bases: dict[str, str], previous: dict[str, Any], dry_run: bool) -> None:
        self.root, self.bases, self.previous, self.dry_run = root, bases, previous, dry_run
        self.owned: dict[str, str] = {}
        self.decided: set[str] = set()
        self.made: set[str] = set()
        self.changes: dict[str, Any] = {"created": [], "updated": [], "unchanged": 0, "left_alone": []}

    def phys(self, rel: str) -> Path:
        return _phys(self.root, rel, self.bases)

    def leave(self, rel: str) -> bool:
        if rel not in self.changes["left_alone"]:
            self.changes["left_alone"].append(rel)
        self.decided.add(rel)
        return False

    def _make_parents(self, rel: str) -> None:
        """Create the missing folders above `rel`, outermost first, and remember each one the install made."""
        parts = rel.split("/")
        missing = []
        for i in range(len(parts) - 1, 0, -1):
            folder = "/".join(parts[:i])
            if os.path.lexists(self.phys(folder)):
                break
            missing.append(folder)
        for folder in reversed(missing):
            try:
                self.phys(folder).mkdir()
            except FileExistsError:
                continue
            self.made.add(folder)

    def put(self, rel: str, data: bytes) -> bool:
        """Classify one file and write it only when it is ours to write. True = the file is ours now.

        Nothing that was already there is taken: a file that is in the receipt with the sha256 it was written with is ours and is
        updated; one that the user edited since, or that no receipt registers, is left alone (identical to the package, it is only
        counted as unchanged: it is not ours and the uninstall never deletes it); a folder, a FIFO or a link is left alone."""
        path = self.phys(rel)
        kind = _kind(path)
        self.decided.add(rel)
        if kind == "other":
            return self.leave(rel)
        want = _sha(data)
        recorded = self.previous["files"].get(rel)
        if kind == "file":
            have = sha256_of(path)
            if have == want:
                self.changes["unchanged"] += 1
                if rel in self.previous["files"]:
                    self.owned[rel] = want
                    return True
                return False
            if recorded is None or have != recorded:
                return self.leave(rel)
            self.changes["updated"].append(rel)
        else:
            self.changes["created"].append(rel)
        if not self.dry_run:
            self._make_parents(rel)
            atomic_write(path, data)
        self.owned[rel] = want
        return True

    def entry(self, rel: str, body: bytes) -> None:
        """An entry file (AGENTS.md ...): written once, never overwritten. The one an earlier install wrote and nobody edited is ours."""
        path = self.phys(rel)
        if os.path.lexists(path):
            recorded = self.previous["files"].get(rel)
            self.decided.add(rel)
            if recorded is not None and _kind(path) == "file" and sha256_of(path) == recorded:
                self.changes["unchanged"] += 1
                self.owned[rel] = recorded
            else:
                self.leave(rel)
            return
        self.put(rel, body)

    def skills(self, dest: str, skill_files: list) -> None:
        """The skills into one skill folder: create what is missing, update ours, leave alone the rest, delete nothing."""
        dest_parts = dest.split("/")
        top = set()
        for parts, node in skill_files:
            top.add(parts[0])
            self.put("/".join((*dest_parts, *parts)), node.read_bytes())
        folder = self.phys(dest)
        for name in sorted(top):  # a user's file inside OUR folder is never touched: it is reported
            inside = folder / name
            if is_link(inside) or not hostos.is_dir(inside):
                continue
            for parts, _node in iter_files(inside):
                rel = "/".join((*dest_parts, name, *parts))
                if rel not in self.decided and rel not in self.previous["files"]:
                    self.leave(rel)
        if dest == SKILLS_DEST and hostos.is_dir(folder):  # the user's other skills; in the other hosts' folders they are none of our business
            try:
                children = sorted(os.listdir(folder))
            except OSError:
                children = []
            for child in children:
                if child not in top and child != "__pycache__":
                    self.leave("/".join((*dest_parts, child)))

    def carry_forward(self) -> None:
        """What an earlier install owned and this run did not make ours again stays in the receipt while it still has the sha256 that was
        written: the entry file of another host, and a file whose update FAILED (disk full, permission denied: the old file is still there,
        intact, and still ours). One the user edited, or deleted, or turned into a link, is not ours any more and leaves the receipt."""
        for rel, digest in self.previous["files"].items():
            if rel in self.owned or digest is None:  # `owned` is what this run really wrote or found ours; a failed write is not in it
                continue
            path = self.phys(rel)
            if _kind(path) == "file" and sha256_of(path) == digest:
                self.owned[rel] = digest

    def ownership(self, plan: Mapping[str, Any], receipt_dir_new: bool) -> dict[str, Any]:
        dirs = set(self.made)
        if receipt_dir_new:
            dirs.add(RECEIPT.parent.as_posix())
        for rel in self.previous["dirs"]:
            path = self.phys(rel)
            if hostos.is_dir(path) and not is_link(path):
                dirs.add(rel)
        used = {rel.split("/")[0] for rel in [*self.owned, *dirs]}
        bases = {name: real for name, real in sorted({**self.previous["bases"], **self.bases}.items()) if name in used}
        receipt: dict[str, Any] = {
            "schema": OWNERSHIP_SCHEMA,
            "owner": OWNER,
            "version": plan["version"],
            "digest": plan["digest"],
            "paths": sorted(self.owned),
            "dirs": sorted(dirs),
            "sha256": {rel: self.owned[rel] for rel in sorted(self.owned)},
        }
        if bases:
            receipt["bases"] = bases
        return receipt

    def write_receipt(self, receipt: dict[str, Any]) -> None:
        body = (json.dumps(receipt, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        path = self.root / RECEIPT
        kind = _kind(path)
        if kind == "file" and same_bytes(path, body):
            self.changes["unchanged"] += 1
            return
        self.changes["updated" if kind == "file" else "created"].append(RECEIPT_REL)
        if not self.dry_run:
            path.parent.mkdir(parents=True, exist_ok=True)
            atomic_write(path, body)

    def cleanup(self) -> None:
        """Last resort when not even the receipt could be written: take away the folders this run made, if they are empty."""
        for rel in sorted(self.made, key=lambda item: item.count("/"), reverse=True):
            with contextlib.suppress(OSError):
                self.phys(rel).rmdir()


def apply_plan(
    plan: Mapping[str, Any],
    *,
    dry_run: bool = False,
    bundle: Any = None,  # a path, or any importlib.resources Traversable; None = the bundle of this package
) -> dict[str, Any]:
    """Copy the bundled skills into the plan's target. Idempotent: a file that is already identical is not rewritten.
    `changes` says what was created, what was updated, how many were unchanged and what was left alone (files in the target that
    simplicio-video does not own, entry files that already exist, files the user edited).

    The ownership receipt registers exactly the files simplicio-video wrote (or an earlier install wrote and nobody edited), with
    their sha256, and the folders it created. Raises InstallError (nothing to install, a receipt that is not a plain file,
    another install holds the lock), InstallRefused (a folder the install creates is a link: nothing is written) and lets an OSError
    of the disk through after leaving a receipt that matches what was written: the caller reports it."""
    root = Path(plan["target"])
    source = Path(bundle) if isinstance(bundle, str) else bundle if bundle is not None else bundle_root()
    skills_src = source.joinpath("skills")
    if not skills_src.is_dir():
        raise InstallError("skills empacotadas não encontradas no pacote instalado.")
    skill_files = list(iter_files(skills_src))
    actions = _unique_actions(plan)
    if _kind(root / RECEIPT) == "other":
        raise InstallError(f"{root / RECEIPT} existe e não é um arquivo comum; apague-o à mão (ou aponte outro --target) e rode de novo")
    bases, skipped = _resolve_bases(root, actions, skill_files)
    receipt_dir_new = not os.path.lexists(root / RECEIPT.parent)
    with _locked(root, dry_run):
        previous = _previous_receipt(root)  # read AFTER the lock: the receipt another install just wrote is the one to extend
        run = _Run(root, bases, previous, dry_run)
        failure: OSError | None = None
        try:
            for action in actions:
                if action["destination"] in skipped:
                    run.leave(action["destination"])
                elif action["kind"] == "entry":
                    run.entry(action["destination"], _entry_body(action["host"]))
                else:
                    run.skills(action["destination"], skill_files)
        except OSError as exc:
            failure = exc
        run.carry_forward()
        ownership = run.ownership(plan, receipt_dir_new)
        if failure is None:
            run.write_receipt(ownership)
        else:  # the receipt matches what was written, so the uninstall can still remove it; then the original error goes up
            try:
                run.write_receipt(ownership)
            except OSError:
                run.cleanup()
            raise failure
    changes = run.changes
    pending = len(changes["created"]) + len(changes["updated"])
    return {
        "schema": SCHEMA,
        "status": "dry_run" if dry_run else "applied",
        "written": 0 if dry_run else pending,
        "up_to_date": pending == 0,
        "changes": changes,
        "owned": sorted(run.owned),
        "ownership": ownership,
        "digest": plan["digest"],
        "warnings": [*previous["warnings"], *(f"{dest}: pulada, {why}" for dest, why in skipped.items())],
    }


# --- uninstall and prune: only what is registered, only with the digest it was written with --------------------------------------


def _protected(path: Path, protect: list) -> bool:
    real = os.path.realpath(path)
    return any(real == fence or real.startswith(fence + os.sep) for fence in protect)


def _remove_owned(root: Path, *, dry_run: bool, protect: tuple = ()) -> dict[str, Any]:
    """Remove the files the receipt registers that still have the sha256 they were written with, then the registered folders that
    are empty by then. A file the user edited is `left_alone` (with a warning), a folder where a file was registered is `skipped`, a
    folder that holds anything not registered is `kept`. `protect`: real folders whose files are never removed (the global install)."""
    _load_receipt(root, strict_links=False)  # refuses a receipt that cannot be trusted BEFORE the lock creates anything
    fences = [os.path.realpath(item) for item in protect]
    removed: list[str] = []
    left_alone: list[str] = []
    skipped: list[str] = []
    warnings: list[str] = []
    gone: set[str] = {RECEIPT_REL, LOCK_REL}
    removed_dirs: list[str] = []
    kept: list[str] = []
    with _locked(root, dry_run):
        receipt = _load_receipt(root, strict_links=False)  # again, now that no other install can change it
        files, dirs, bases, unsafe = receipt["files"], receipt["dirs"], receipt["bases"], receipt["unsafe"]
        for rel in sorted(files):
            path = _phys(root, rel, bases)
            if rel in unsafe:  # a link above it now: never touched through it
                left_alone.append(rel)
                warnings.append(f"{_folder_of(rel)}: virou um link depois do install; {rel} ficou como está")
            elif _protected(path, fences):
                left_alone.append(rel)
                warnings.append(f"{rel}: é a instalação global (este recibo é de um projeto); não removi")
            elif is_link(path):  # a registered file that became a link is the user's now, whatever it points at
                left_alone.append(rel)
                warnings.append(f"{rel}: virou um link depois do install; deixei como está")
            elif hostos.is_file(path):
                if files[rel] is None:
                    left_alone.append(rel)
                    warnings.append(f"{rel}: o recibo não tem o sha256 deste arquivo; deixei como está")
                elif sha256_of(path) == files[rel]:
                    removed.append(rel)
                    gone.add(rel)
                else:
                    left_alone.append(rel)
                    warnings.append(f"{rel}: foi editado depois do install (o sha256 mudou); deixei como está")
            elif os.path.lexists(path):  # a folder where a file was registered: not ours to delete
                skipped.append(rel)
        if hostos.is_file(root / RECEIPT):
            removed.append(RECEIPT_REL)
        for rel in sorted(set(dirs), key=lambda item: item.count("/"), reverse=True):
            path = _phys(root, rel, bases)
            if rel in unsafe or is_link(path) or not hostos.is_dir(path):  # a link is the user's, whatever it points at
                continue
            try:
                children = [f"{rel}/{name}" for name in os.listdir(path)]
            except OSError:
                kept.append(rel)
                continue
            if all(child in gone for child in children):
                removed_dirs.append(rel)
                gone.add(rel)
            else:
                kept.append(rel)
        if not dry_run:
            for rel in removed:
                _phys(root, rel, bases).unlink()
            for rel in removed_dirs:
                if rel != RECEIPT.parent.as_posix():  # still holds the lock file: it goes after the lock is released
                    _phys(root, rel, bases).rmdir()
    if not dry_run:
        _drop_lock(root)
        if RECEIPT.parent.as_posix() in removed_dirs:
            with contextlib.suppress(OSError):
                (root / RECEIPT.parent).rmdir()
    return {
        "status": "dry_run" if dry_run else "removed",
        "removed": sorted(removed),
        "removed_dirs": sorted(removed_dirs),
        "kept": sorted(kept),
        "skipped": sorted(skipped),
        "left_alone": sorted(left_alone),
        "warnings": warnings,
    }


def uninstall(target: str | Path, *, dry_run: bool = False, protect: tuple | list = ()) -> dict[str, Any]:
    """Remove what the receipt registers, with the digest it was written with; keep everything else (see `_remove_owned`).
    A receipt that names anything the registry cannot produce is refused whole, before anything is touched. `dry_run` returns the
    same lists and touches nothing; then `removed` is what would go. `protect`: real folders whose files are never removed. The command
    gives a PROJECT uninstall the folders of the global install: a cloned repository whose `.claude` is a link to `~/.claude` and whose
    receipt records that real path as its base must not be able to take the global install away."""
    return {"schema": SCHEMA, **_remove_owned(Path(target).resolve(), dry_run=dry_run, protect=tuple(protect))}


def prune_project_copies(target: str | Path, *, dry_run: bool = False, protect: tuple | list = ()) -> dict[str, Any]:
    """Remove the project-scope copy that `install` made in `target`, when simplicio-video is installed globally.

    Only what the PROJECT's own receipt registers, with the sha256 it was written with: a copy in `.cursor/skills`, an old skill that
    no receipt knows, a file the user edited, a folder it only passes through and a link are never touched (the loop scans for them;
    here that is how a hostile repository deletes its victim's files). `protect` holds the real folders of the global install: if the
    project's `.claude` is a link into the home's, the "copy" IS the global install, and it stays. No receipt, nothing to prune."""
    try:
        result = _remove_owned(Path(target).resolve(), dry_run=dry_run, protect=tuple(protect))
    except NoReceipt:
        result = {"status": "dry_run" if dry_run else "removed", "removed": [], "removed_dirs": [], "kept": [], "skipped": [],
                  "left_alone": [], "warnings": []}
    result["left_alone"] = sorted({*result["left_alone"], *result.pop("skipped")})
    return {"schema": SCHEMA, **result}


# --- verify -------------------------------------------------------------------------------------------------------------------


def verify_plan(plan: Mapping[str, Any], expected_version: str = __version__) -> dict[str, Any]:
    """The loop's check: the descriptor is the version of the installed package. (`verify_install` looks at the files too.)"""
    if plan.get("version") != expected_version:
        raise InstallError(f"versão do descritor diverge: plano={plan.get('version')} pacote={expected_version}")
    return {"ok": True, "version": expected_version, "digest": plan.get("digest")}


def verify_install(plan: Mapping[str, Any], *, bundle: Any = None, expected_version: str = __version__) -> dict[str, Any]:
    """Compare what is on disk with the receipt and with the package, and say what differs. Writes nothing.

    `{"ok", "version", "digest", "problems": [{"path", "problem", "detail"}]}`, the loop's keys plus the list. `problem` is one of:
    `no_receipt`, `bad_receipt`, `missing`, `not_a_file`, `modified` (the user changed a file we wrote), `outdated` (a file we wrote,
    older than the package: run `install`), `foreign` (a file that was there before, differs from the package and is not ours)."""
    verify_plan(plan, expected_version)
    root = Path(plan["target"])
    source = Path(bundle) if isinstance(bundle, str) else bundle if bundle is not None else bundle_root()
    problems: list[dict[str, str]] = []

    def problem(path: str, code: str, detail: str) -> None:
        problems.append({"path": path, "problem": code, "detail": detail})

    receipt: dict[str, Any] = {"files": {}, "dirs": [], "bases": {}, "unsafe": {}}
    try:
        receipt = _load_receipt(root, strict_links=False)
    except NoReceipt:
        problem(RECEIPT_REL, "no_receipt", "sem recibo de posse (rode `simplicio-video install`): o uninstall não saberia o que remover")
    except InstallError as exc:
        problem(RECEIPT_REL, "bad_receipt", str(exc))
    files, bases, unsafe = receipt["files"], receipt["bases"], receipt["unsafe"]
    checked: set[str] = set()
    skills_src = source.joinpath("skills")
    skill_files = list(iter_files(skills_src)) if skills_src.is_dir() else []
    actions = _unique_actions(plan)
    try:  # the folders the install skips (a symlinked `~/.config/opencode`) are not expected to hold the skills
        skipped = _resolve_bases(root, actions, skill_files)[1]
    except InstallRefused as exc:
        problem(exc.path or SKILLS_DEST, "not_a_file", exc.detail)
        skipped = {}
    for rel, why in sorted(unsafe.items()):
        if rel in files:
            problem(rel, "not_a_file", why)
    for action in actions:
        if action["destination"] in skipped:
            continue
        if action["kind"] == "entry":
            rel = action["destination"]
            if rel not in files and not os.path.lexists(_phys(root, rel, bases)):
                problem(rel, "missing", "falta o arquivo de entrada do host (rode `simplicio-video install`)")
            continue
        for parts, node in skill_files:
            rel = "/".join((*action["destination"].split("/"), *parts))
            checked.add(rel)
            if rel in unsafe:
                continue
            path = _phys(root, rel, bases)
            kind = _kind(path)
            if kind == "missing":
                problem(rel, "missing", "falta o arquivo (rode `simplicio-video install`)")
            elif kind == "other":
                problem(rel, "not_a_file", "não é um arquivo comum (pasta, link, fifo...)")
            else:
                have, want = sha256_of(path), _sha(node.read_bytes())
                if have == want:
                    continue
                if rel in files and files[rel] == have:
                    problem(rel, "outdated", "desatualizado: o pacote mudou; rode `simplicio-video install`")
                elif rel in files:
                    problem(rel, "modified", "modificado depois do install: difere do que o recibo gravou e do pacote")
                else:
                    problem(rel, "foreign", "já existia, difere do pacote e não é do simplicio-video (o install o deixa em paz); "
                            "apague-o ou renomeie e rode `simplicio-video install`")
    for rel, recorded in sorted(files.items()):
        if rel in checked or rel in unsafe:
            continue
        path = _phys(root, rel, bases)
        kind = _kind(path)
        if kind == "missing":
            problem(rel, "missing", "falta o arquivo que o recibo registra")
        elif kind == "other":
            problem(rel, "not_a_file", "não é um arquivo comum (pasta, link, fifo...)")
        elif recorded is None or sha256_of(path) != recorded:
            problem(rel, "modified", "modificado depois do install: difere do que o recibo gravou")
    return {"ok": not problems, "version": expected_version, "digest": plan.get("digest"), "problems": problems}
