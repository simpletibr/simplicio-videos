#!/usr/bin/env python3
"""Fetch ComfyUI model weights and workflow config from Cloudflare R2 (S3 API).

Usage:
    python fetch_models.py --manifest /app/models.manifest.json \
        --models-dir /opt/ComfyUI/models [--scope all|models|config] \
        [--only-missing | --no-only-missing] [--workers 4]

Manifest entries (JSON list of objects):
    r2_key            "models/<dest>" for model files, "config/<dest>" when dest_root is set
    dest              path relative to the target directory
    dest_root         optional absolute directory; default is --models-dir
    size_bytes        null, or expected size (skip check when a present file matches)
    sha256            null, or expected lowercase hex digest
    required          true = failure aborts the run
    always_download   optional bool; true = fetched at every run, never skipped
    optional_if_env   optional env name; when it is set to "1" a file that is
                      missing in R2 (404) is only a warning, not a failure

Env (only required when something must be downloaded):
    R2_ENDPOINT, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET

Exit codes: 0 = no fatal failure, 1 = a required file failed,
2 = bad manifest or missing configuration.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Final, Literal, Protocol

MAX_WORKERS: Final[int] = 4
MAX_ATTEMPTS: Final[int] = 3
BACKOFF_BASE_S: Final[float] = 2.0
MULTIPART_BYTES: Final[int] = 64 * 1024 * 1024
PROGRESS_STEP_BYTES: Final[int] = 512 * 1024 * 1024
HASH_CHUNK_BYTES: Final[int] = 8 * 1024 * 1024
MODEL_PREFIX: Final[str] = "models/"
CONFIG_PREFIX: Final[str] = "config/"
REQUIRED_ENV: Final[tuple[str, ...]] = (
    "R2_ENDPOINT",
    "R2_ACCESS_KEY_ID",
    "R2_SECRET_ACCESS_KEY",
    "R2_BUCKET",
)
MISSING_ERROR_CODES: Final[frozenset[str]] = frozenset({"404", "NoSuchKey", "NotFound"})
# Errors that will not change on retry: missing key or rejected credentials.
PERMANENT_ERROR_CODES: Final[frozenset[str]] = MISSING_ERROR_CODES | frozenset(
    {"AccessDenied", "InvalidAccessKeyId", "SignatureDoesNotMatch"}
)
ENV_NAME_RE: Final[re.Pattern[str]] = re.compile(r"^[A-Z_][A-Z0-9_]*$")

Scope = Literal["all", "models", "config"]
SCOPES: Final[tuple[str, ...]] = ("all", "models", "config")

PlanItem = dict[str, Any]


class DownloadError(RuntimeError):
    """A file could not be fetched and verified after all attempts."""

    def __init__(self, message: str, *, missing: bool = False) -> None:
        super().__init__(message)
        self.missing = missing


class IntegrityError(ValueError):
    """A downloaded file does not match its manifest size or sha256."""


class S3Downloader(Protocol):
    """The subset of a boto3 S3 client this module uses."""

    def download_file(
        self,
        *,
        Bucket: str,
        Key: str,
        Filename: str,
        Config: object = None,
        Callback: Callable[[int], None] | None = None,
    ) -> None: ...


@dataclass(frozen=True)
class FetchResult:
    target: str
    required: bool
    ok: bool
    missing: bool
    waivable: bool
    error: str | None


def _log(message: str) -> None:
    print(f"[fetch] {message}", flush=True)


def _gib(num_bytes: int) -> str:
    return f"{num_bytes / 2**30:.2f} GiB"


# --------------------------------------------------------------------------
# Manifest handling (pure)
# --------------------------------------------------------------------------


def validate_entry(entry: Mapping[str, Any]) -> None:
    """Raise ValueError if a manifest entry breaks the layout in CONTRACT.md section 3."""
    for field in ("r2_key", "dest", "required"):
        if field not in entry:
            raise ValueError(f"manifest entry lacks '{field}': {dict(entry)!r}")

    dest = entry["dest"]
    if not isinstance(dest, str) or not dest:
        raise ValueError(f"'dest' must be a non-empty string: {dest!r}")
    posix = PurePosixPath(dest)
    if posix.is_absolute() or ".." in posix.parts:
        raise ValueError(f"'dest' must be relative and stay inside its directory: {dest!r}")

    root = entry.get("dest_root")
    if root is None:
        expected_key = MODEL_PREFIX + dest
    else:
        if not isinstance(root, str) or not PurePosixPath(root).is_absolute():
            raise ValueError(f"'dest_root' must be an absolute directory: {root!r}")
        expected_key = CONFIG_PREFIX + dest
    if entry["r2_key"] != expected_key:
        raise ValueError(f"r2_key must be {expected_key!r}, got {entry['r2_key']!r}")

    if not isinstance(entry["required"], bool):
        raise ValueError(f"'required' must be true or false for {dest!r}")

    size = entry.get("size_bytes")
    if size is not None and (isinstance(size, bool) or not isinstance(size, int) or size < 0):
        raise ValueError(f"'size_bytes' must be null or a non-negative int for {dest!r}")

    always = entry.get("always_download", False)
    if not isinstance(always, bool):
        raise ValueError(f"'always_download' must be a boolean for {dest!r}")

    env_name = entry.get("optional_if_env")
    if env_name is not None and (not isinstance(env_name, str) or not ENV_NAME_RE.match(env_name)):
        raise ValueError(f"'optional_if_env' must be an environment variable name for {dest!r}")


def load_manifest(path: Path) -> list[dict[str, Any]]:
    """Read the manifest JSON. Entry-level checks happen in plan_downloads."""
    data: Any = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list) or not all(isinstance(entry, dict) for entry in data):
        raise ValueError(f"{path}: manifest must be a JSON list of objects")
    return data


def target_path(entry: Mapping[str, Any], models_dir: str) -> Path:
    """Where an entry lands: its dest_root if set, otherwise models_dir."""
    root = entry.get("dest_root") or models_dir
    return Path(str(root)) / str(entry["dest"])


def waiver_active(entry: Mapping[str, Any], env: Mapping[str, str]) -> bool:
    """True when the entry names an env flag and that flag is set to exactly "1"."""
    name = entry.get("optional_if_env")
    return isinstance(name, str) and env.get(name) == "1"


def _probe_sizes(manifest: Sequence[Mapping[str, Any]], models_dir: str) -> dict[str, int]:
    sizes: dict[str, int] = {}
    for entry in manifest:
        path = target_path(entry, models_dir)
        if path.is_file():
            sizes[str(path)] = path.stat().st_size
    return sizes


def plan_downloads(
    manifest: list[dict[str, Any]],
    models_dir: str,
    existing_sizes: dict[str, int] | None = None,
    *,
    only_missing: bool = True,
    scope: Scope = "all",
) -> list[dict[str, Any]]:
    """Return the manifest entries that must be fetched, each annotated.

    Each returned item is the manifest entry plus ``target`` (absolute path) and
    ``reason``: ``always`` (always_download), ``missing``, ``size_mismatch`` or
    ``forced`` (only_missing disabled).

    ``existing_sizes`` maps target path -> size in bytes for files already on disk.
    When it is None the sizes are probed on disk; that is the only filesystem read
    here. With a given mapping the function is pure.

    A present file is skipped when its size matches ``size_bytes``, or when
    ``size_bytes`` is null (cannot verify, so it is trusted). Entries with
    always_download are never skipped.

    ``scope`` selects "models" (no always_download), "config" (only always_download)
    or "all".
    """
    if scope not in SCOPES:
        raise ValueError(f"scope must be one of {SCOPES}, got {scope!r}")

    for entry in manifest:
        validate_entry(entry)
    targets = [str(target_path(entry, models_dir)) for entry in manifest]
    if len(set(targets)) != len(targets):
        raise ValueError("two manifest entries write to the same file")

    sizes = _probe_sizes(manifest, models_dir) if existing_sizes is None else existing_sizes

    plan: list[dict[str, Any]] = []
    for entry, target in zip(manifest, targets):
        always = bool(entry.get("always_download", False))
        if scope == "models" and always:
            continue
        if scope == "config" and not always:
            continue

        expected = entry.get("size_bytes")
        if always:
            reason = "always"
        elif not only_missing:
            reason = "forced"
        elif target not in sizes:
            reason = "missing"
        elif expected is None or sizes[target] == expected:
            continue
        else:
            reason = "size_mismatch"
        plan.append({**entry, "target": target, "reason": reason})
    return plan


def is_fatal(result: FetchResult) -> bool:
    """A failed required file is fatal, except a 404 on a file the env flag waives."""
    if result.ok or not result.required:
        return False
    return not (result.missing and result.waivable)


# --------------------------------------------------------------------------
# Download with verification (I/O, but injectable)
# --------------------------------------------------------------------------


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(HASH_CHUNK_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verify(part: Path, item: Mapping[str, Any]) -> None:
    expected_size = item.get("size_bytes")
    actual_size = part.stat().st_size
    if expected_size is not None and actual_size != expected_size:
        raise IntegrityError(f"size {actual_size} != expected {expected_size}")
    expected_sha = item.get("sha256")
    if expected_sha is not None:
        actual_sha = _sha256_file(part)
        if actual_sha != str(expected_sha).lower():
            raise IntegrityError(f"sha256 {actual_sha} != expected {expected_sha}")


def _error_code(exc: BaseException) -> str | None:
    response = getattr(exc, "response", None)
    if not isinstance(response, dict):
        return None
    error = response.get("Error")
    code = error.get("Code") if isinstance(error, dict) else None
    return None if code is None else str(code)


def _is_permanent(exc: BaseException) -> bool:
    return _error_code(exc) in PERMANENT_ERROR_CODES


def _is_missing(exc: BaseException) -> bool:
    return _error_code(exc) in MISSING_ERROR_CODES


class _Progress:
    """Thread-safe byte counter that logs every PROGRESS_STEP_BYTES."""

    def __init__(self, label: str, total: int | None) -> None:
        self._label = label
        self._total = total
        self._seen = 0
        self._next_mark = PROGRESS_STEP_BYTES
        self._lock = threading.Lock()

    def __call__(self, num_bytes: int) -> None:
        with self._lock:
            self._seen += num_bytes
            if self._seen < self._next_mark:
                return
            self._next_mark += PROGRESS_STEP_BYTES
            seen = self._seen
        suffix = f" / {_gib(self._total)}" if self._total else ""
        _log(f"{self._label}: {_gib(seen)}{suffix}")


def download_one(
    client: S3Downloader,
    bucket: str,
    item: Mapping[str, Any],
    *,
    transfer_config: object = None,
    sleep: Callable[[float], None] | None = None,
) -> None:
    """Download one planned item to ``<target>.part``, verify, then rename into place.

    Transient failures are retried up to MAX_ATTEMPTS with exponential backoff.
    Permanent failures (404, auth) stop at once. A missing always_download file
    also removes any stale copy, so an old config can never be served.
    Raises DownloadError when giving up; its ``missing`` flag is True for a 404.
    """
    target = Path(str(item["target"]))
    part = target.with_name(target.name + ".part")
    label = str(item["target"])
    target.parent.mkdir(parents=True, exist_ok=True)
    pause = sleep if sleep is not None else time.sleep

    last_error: Exception | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        part.unlink(missing_ok=True)
        try:
            client.download_file(
                Bucket=bucket,
                Key=str(item["r2_key"]),
                Filename=str(part),
                Config=transfer_config,
                Callback=_Progress(label, item.get("size_bytes")),
            )
            _verify(part, item)
            os.replace(part, target)
            _log(f"done {label}")
            return
        except Exception as exc:  # transport, I/O and integrity failures are all retryable
            last_error = exc
            _log(f"{label}: attempt {attempt}/{MAX_ATTEMPTS} failed: {exc}")
            if _is_permanent(exc):
                break
            if attempt < MAX_ATTEMPTS:
                pause(BACKOFF_BASE_S * 2 ** (attempt - 1))

    part.unlink(missing_ok=True)
    missing = last_error is not None and _is_missing(last_error)
    if missing and item.get("always_download"):
        target.unlink(missing_ok=True)
    raise DownloadError(f"{label}: {last_error}", missing=missing) from last_error


def fetch_all(
    client: S3Downloader,
    bucket: str,
    plan: Sequence[Mapping[str, Any]],
    *,
    env: Mapping[str, str],
    transfer_config: object = None,
    workers: int = MAX_WORKERS,
) -> list[FetchResult]:
    """Download every planned item in parallel. Results keep the plan's order."""

    def run(item: Mapping[str, Any]) -> FetchResult:
        target = str(item["target"])
        required = bool(item["required"])
        waivable = waiver_active(item, env)
        try:
            download_one(client, bucket, item, transfer_config=transfer_config)
        except DownloadError as exc:
            return FetchResult(target, required, ok=False, missing=exc.missing, waivable=waivable, error=str(exc))
        return FetchResult(target, required, ok=True, missing=False, waivable=waivable, error=None)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(run, plan))


# --------------------------------------------------------------------------
# boto3 wiring (imported lazily so the pure functions need no boto3)
# --------------------------------------------------------------------------


def make_client(env: Mapping[str, str]) -> S3Downloader:
    import boto3
    from botocore.config import Config

    client = boto3.client(
        "s3",
        endpoint_url=env["R2_ENDPOINT"],
        aws_access_key_id=env["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=env["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
        config=Config(
            signature_version="s3v4",
            max_pool_connections=16,
            retries={"max_attempts": 5, "mode": "standard"},
        ),
    )
    return client  # type: ignore[no-any-return]


def _transfer_config() -> object:
    from boto3.s3.transfer import TransferConfig

    return TransferConfig(
        multipart_threshold=MULTIPART_BYTES,
        multipart_chunksize=MULTIPART_BYTES,
        max_concurrency=4,
        use_threads=True,
    )


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch ComfyUI models and workflow config from R2.")
    parser.add_argument("--manifest", type=Path, required=True, help="models.manifest.json")
    parser.add_argument("--models-dir", type=Path, required=True, help="ComfyUI models directory")
    parser.add_argument(
        "--scope",
        choices=SCOPES,
        default="all",
        help="all (default), models (weights only), or config (always_download entries only)",
    )
    parser.add_argument(
        "--only-missing",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="skip model files already present with a matching size (default: on)",
    )
    parser.add_argument("--workers", type=int, default=MAX_WORKERS, help="parallel downloads")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        manifest = load_manifest(args.manifest)
        plan = plan_downloads(
            manifest,
            str(args.models_dir),
            only_missing=args.only_missing,
            scope=args.scope,
        )
    except (OSError, ValueError) as exc:
        _log(f"manifest error: {exc}")
        return 2

    if not plan:
        _log("everything in scope is present; nothing to download")
        return 0

    missing_env = [name for name in REQUIRED_ENV if not os.environ.get(name)]
    if missing_env:
        _log(f"missing environment variables: {', '.join(missing_env)}")
        return 2

    known_total = sum(int(item["size_bytes"] or 0) for item in plan)
    _log(f"{len(plan)} file(s) to fetch, {_gib(known_total)} of known size")
    for item in plan:
        always = " always" if item.get("always_download") else ""
        _log(f"  {item['reason']:<13} {item['target']} (required={item['required']}{always})")

    client = make_client(os.environ)
    results = fetch_all(
        client,
        os.environ["R2_BUCKET"],
        plan,
        env=os.environ,
        transfer_config=_transfer_config(),
        workers=args.workers,
    )

    for result in results:
        if result.ok:
            continue
        if is_fatal(result):
            _log(f"FAILED {result.target}: {result.error}")
        elif result.missing and result.waivable:
            _log(f"WARNING {result.target} is missing in R2; continuing because WORKFLOW_OPTIONAL=1")
        else:
            _log(f"WARNING (optional, skipped) {result.target}: {result.error}")

    fatal = [result for result in results if is_fatal(result)]
    downloaded = sum(1 for result in results if result.ok)
    _log(f"{downloaded}/{len(results)} fetched, {len(fatal)} fatal failure(s)")
    return 1 if fatal else 0


if __name__ == "__main__":
    sys.exit(main())
