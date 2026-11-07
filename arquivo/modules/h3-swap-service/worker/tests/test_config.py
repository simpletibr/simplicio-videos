from __future__ import annotations

import dataclasses

import pytest

from worker.config import Config

REQUIRED: dict[str, str] = {
    "CF_ACCOUNT_ID": "acct-1",
    "CF_QUEUE_ID": "queue-1",
    "CF_API_TOKEN": "SECRET-CF-TOKEN",
    "R2_ENDPOINT": "https://r2.example.com",
    "R2_ACCESS_KEY_ID": "r2-access",
    "R2_SECRET_ACCESS_KEY": "SECRET-R2-KEY",
    "R2_BUCKET": "h3-swap",
    "API_BASE_URL": "https://api.example.com",
    "WORKER_SECRET": "SECRET-WORKER",
}


def test_optional_vars_fall_back_to_contract_defaults() -> None:
    cfg = Config.from_env(REQUIRED)
    assert cfg.instance_id == "local"
    assert cfg.provider == "vast"
    assert cfg.comfy_url == "http://127.0.0.1:8188"
    assert cfg.comfy_input_dir == "/opt/ComfyUI/input"
    assert cfg.workflow_template == "/app/workflow_api.json"
    assert cfg.workflow_map == "/app/workflow_map.json"
    assert cfg.visibility_timeout_ms == 2_700_000
    assert cfg.poll_interval_s == 5
    assert cfg.job_timeout_s == 2400
    assert cfg.heartbeat_interval_s == 30
    assert cfg.max_attempts == 3


def test_required_vars_are_mapped() -> None:
    cfg = Config.from_env(REQUIRED)
    assert cfg.cf_account_id == "acct-1"
    assert cfg.cf_queue_id == "queue-1"
    assert cfg.cf_api_token == "SECRET-CF-TOKEN"
    assert cfg.r2_endpoint == "https://r2.example.com"
    assert cfg.r2_access_key_id == "r2-access"
    assert cfg.r2_secret_access_key == "SECRET-R2-KEY"
    assert cfg.r2_bucket == "h3-swap"
    assert cfg.api_base_url == "https://api.example.com"
    assert cfg.worker_secret == "SECRET-WORKER"


def test_optional_overrides_are_parsed() -> None:
    env = {
        **REQUIRED,
        "INSTANCE_ID": "vast-42",
        "PROVIDER": "salad",
        "COMFY_URL": "http://gpu:8188",
        "POLL_INTERVAL_S": "2.5",
        "JOB_TIMEOUT_S": "600",
        "HEARTBEAT_INTERVAL_S": "10",
        "MAX_ATTEMPTS": "5",
        "VISIBILITY_TIMEOUT_MS": "1000",
    }
    cfg = Config.from_env(env)
    assert cfg.instance_id == "vast-42"
    assert cfg.provider == "salad"
    assert cfg.comfy_url == "http://gpu:8188"
    assert cfg.poll_interval_s == 2.5
    assert cfg.job_timeout_s == 600
    assert cfg.heartbeat_interval_s == 10
    assert cfg.max_attempts == 5
    assert cfg.visibility_timeout_ms == 1000


def test_missing_required_vars_are_all_named() -> None:
    env = {k: v for k, v in REQUIRED.items() if k not in ("CF_API_TOKEN", "R2_BUCKET")}
    env["WORKER_SECRET"] = "   "
    with pytest.raises(ValueError) as info:
        Config.from_env(env)
    message = str(info.value)
    assert "CF_API_TOKEN" in message
    assert "R2_BUCKET" in message
    assert "WORKER_SECRET" in message
    assert "CF_ACCOUNT_ID" not in message


@pytest.mark.parametrize(
    "name, value",
    [("MAX_ATTEMPTS", "three"), ("JOB_TIMEOUT_S", "1.5"), ("POLL_INTERVAL_S", "fast")],
)
def test_unparseable_numbers_name_the_variable(name: str, value: str) -> None:
    with pytest.raises(ValueError, match=name):
        Config.from_env({**REQUIRED, name: value})


@pytest.mark.parametrize(
    "name, value",
    [("MAX_ATTEMPTS", "0"), ("JOB_TIMEOUT_S", "-5"), ("POLL_INTERVAL_S", "0"), ("VISIBILITY_TIMEOUT_MS", "0")],
)
def test_non_positive_numbers_are_rejected(name: str, value: str) -> None:
    with pytest.raises(ValueError, match=name):
        Config.from_env({**REQUIRED, name: value})


def test_from_env_reads_process_environment_when_no_mapping(monkeypatch: pytest.MonkeyPatch) -> None:
    for key, value in REQUIRED.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("INSTANCE_ID", raising=False)
    cfg = Config.from_env()
    assert cfg.cf_queue_id == "queue-1"
    assert cfg.instance_id == "local"


def test_secrets_do_not_appear_in_repr() -> None:
    text = repr(Config.from_env(REQUIRED))
    for secret in ("SECRET-CF-TOKEN", "SECRET-R2-KEY", "SECRET-WORKER"):
        assert secret not in text


def test_config_is_frozen() -> None:
    cfg = Config.from_env(REQUIRED)
    with pytest.raises(dataclasses.FrozenInstanceError):
        cfg.max_attempts = 9  # type: ignore[misc]
