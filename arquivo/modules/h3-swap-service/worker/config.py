"""Worker configuration from environment variables (CONTRACT section 6)."""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import TypeVar

_REQUIRED: tuple[str, ...] = (
    "CF_ACCOUNT_ID",
    "CF_QUEUE_ID",
    "CF_API_TOKEN",
    "R2_ENDPOINT",
    "R2_ACCESS_KEY_ID",
    "R2_SECRET_ACCESS_KEY",
    "R2_BUCKET",
    "API_BASE_URL",
    "WORKER_SECRET",
)

_T = TypeVar("_T", int, float)


@dataclass(frozen=True)
class Config:
    cf_account_id: str
    cf_queue_id: str
    cf_api_token: str = field(repr=False)
    r2_endpoint: str
    r2_access_key_id: str = field(repr=False)
    r2_secret_access_key: str = field(repr=False)
    r2_bucket: str
    api_base_url: str
    worker_secret: str = field(repr=False)
    instance_id: str = "local"
    provider: str = "vast"
    comfy_url: str = "http://127.0.0.1:8188"
    comfy_input_dir: str = "/opt/ComfyUI/input"
    workflow_template: str = "/app/workflow_api.json"
    workflow_map: str = "/app/workflow_map.json"
    visibility_timeout_ms: int = 2_700_000
    poll_interval_s: float = 5.0
    job_timeout_s: int = 2400
    heartbeat_interval_s: float = 30.0
    max_attempts: int = 3

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Config:
        """Build the config from `env` (defaults to os.environ).

        Empty or whitespace-only values count as unset. Raises ValueError naming
        every missing required variable, or the offending variable for bad numbers.
        """
        source: Mapping[str, str] = os.environ if env is None else env

        def read(name: str) -> str | None:
            raw = source.get(name)
            if raw is None or not raw.strip():
                return None
            return raw.strip()

        missing = [name for name in _REQUIRED if read(name) is None]
        if missing:
            raise ValueError("missing required environment variables: " + ", ".join(missing))

        def text(name: str, default: str) -> str:
            value = read(name)
            return default if value is None else value

        def number(name: str, default: _T, parse: Callable[[str], _T]) -> _T:
            value = read(name)
            if value is None:
                return default
            try:
                parsed = parse(value)
            except ValueError as exc:
                kind = "an integer" if parse is int else "a number"
                raise ValueError(f"{name} must be {kind}, got {value!r}") from exc
            if parsed <= 0:
                raise ValueError(f"{name} must be positive, got {parsed}")
            return parsed

        return cls(
            cf_account_id=read("CF_ACCOUNT_ID") or "",
            cf_queue_id=read("CF_QUEUE_ID") or "",
            cf_api_token=read("CF_API_TOKEN") or "",
            r2_endpoint=read("R2_ENDPOINT") or "",
            r2_access_key_id=read("R2_ACCESS_KEY_ID") or "",
            r2_secret_access_key=read("R2_SECRET_ACCESS_KEY") or "",
            r2_bucket=read("R2_BUCKET") or "",
            api_base_url=read("API_BASE_URL") or "",
            worker_secret=read("WORKER_SECRET") or "",
            instance_id=text("INSTANCE_ID", "local"),
            provider=text("PROVIDER", "vast"),
            comfy_url=text("COMFY_URL", "http://127.0.0.1:8188"),
            comfy_input_dir=text("COMFY_INPUT_DIR", "/opt/ComfyUI/input"),
            workflow_template=text("WORKFLOW_TEMPLATE", "/app/workflow_api.json"),
            workflow_map=text("WORKFLOW_MAP", "/app/workflow_map.json"),
            visibility_timeout_ms=number("VISIBILITY_TIMEOUT_MS", 2_700_000, int),
            poll_interval_s=number("POLL_INTERVAL_S", 5.0, float),
            job_timeout_s=number("JOB_TIMEOUT_S", 2400, int),
            heartbeat_interval_s=number("HEARTBEAT_INTERVAL_S", 30.0, float),
            max_attempts=number("MAX_ATTEMPTS", 3, int),
        )
