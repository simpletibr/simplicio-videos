"""Tests for docker/fetch_models.py.

Run from the repo root:  python -m pytest docker/tests -q
No network. S3 is faked; no boto3 client is created.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import pytest

DOCKER_DIR = Path(__file__).resolve().parents[1]
if str(DOCKER_DIR) not in sys.path:
    sys.path.insert(0, str(DOCKER_DIR))

import fetch_models as fm  # noqa: E402

PAYLOAD = b"model-bytes-0123456789"
WAIVER_ENV = "WORKFLOW_OPTIONAL"

KNOWN_MODELS = {
    "diffusion_models/minimax_h3_fl2va_pruned_int8_convrot.safetensors",
    "text_encoders/qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors",
    "vae/minimax_h3_video_vae_int8_convrot.safetensors",
    "vae/minimax_h3_audio_vae_fp32.safetensors",
    "loras/h3_character_swap_v1.5.safetensors",
}
TODO_OPTIONAL = {
    "diffusion_models/TODO_VERIFY_ref2va_base.safetensors",
    "loras/TODO_VERIFY_turbo_lora.safetensors",
}
CONFIG_FILES = {"workflow_api.json", "workflow_map.json"}

R2_ENV = {
    "R2_ENDPOINT": "https://example.invalid",
    "R2_ACCESS_KEY_ID": "test-access-key-id",
    "R2_SECRET_ACCESS_KEY": "test-secret-access-key",
    "R2_BUCKET": "test-bucket",
}


def make_entry(
    dest: str,
    *,
    size: int | None = None,
    sha256: str | None = None,
    required: bool = True,
    dest_root: str | None = None,
    always_download: Any = None,
    optional_if_env: Any = None,
) -> dict[str, Any]:
    """Models use models/<dest>; entries with dest_root use config/<dest>."""
    entry: dict[str, Any] = {
        "r2_key": ("config/" if dest_root is not None else "models/") + dest,
        "dest": dest,
        "size_bytes": size,
        "sha256": sha256,
        "required": required,
        "note": "test entry",
    }
    if dest_root is not None:
        entry["dest_root"] = dest_root
    if always_download is not None:
        entry["always_download"] = always_download
    if optional_if_env is not None:
        entry["optional_if_env"] = optional_if_env
    return entry


def config_entry(dest: str, root: Path, *, required: bool = True) -> dict[str, Any]:
    return make_entry(
        dest,
        dest_root=str(root),
        always_download=True,
        optional_if_env=WAIVER_ENV,
        required=required,
    )


def plan_one(tmp_path: Path, dest: str = "vae/a.safetensors", **kwargs: Any) -> dict[str, Any]:
    plans = fm.plan_downloads([make_entry(dest, **kwargs)], str(tmp_path), existing_sizes={})
    assert len(plans) == 1
    return plans[0]


class FakeClientError(Exception):
    """Mimics botocore.exceptions.ClientError: carries a response dict."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.response = {"Error": {"Code": code}}


class FakeS3:
    """Stands in for a boto3 S3 client.

    objects: key -> bytes. A missing key raises a 404 ClientError.
    fail_first: the first N calls raise a transient ConnectionError.
    """

    def __init__(self, objects: dict[str, bytes], fail_first: int = 0) -> None:
        self.objects = objects
        self.fail_first = fail_first
        self.calls: list[str] = []

    def download_file(
        self,
        *,
        Bucket: str,
        Key: str,
        Filename: str,
        Config: object = None,
        Callback: object = None,
    ) -> None:
        assert Bucket == "test-bucket"
        self.calls.append(Key)
        if len(self.calls) <= self.fail_first:
            raise ConnectionError("connection reset by peer")
        if Key not in self.objects:
            raise FakeClientError("404")
        Path(Filename).write_bytes(self.objects[Key])


# --------------------------------------------------------------------------
# plan_downloads: pure decision logic (existing_sizes is keyed by target path)
# --------------------------------------------------------------------------


def test_missing_file_is_planned(tmp_path: Path) -> None:
    plan = fm.plan_downloads(
        [make_entry("vae/a.safetensors", size=10)], str(tmp_path), existing_sizes={}
    )
    assert [p["dest"] for p in plan] == ["vae/a.safetensors"]
    assert plan[0]["reason"] == "missing"
    assert plan[0]["target"] == str(tmp_path / "vae" / "a.safetensors")


def test_present_file_with_unknown_size_is_skipped(tmp_path: Path) -> None:
    target = str(tmp_path / "vae" / "a.safetensors")
    plan = fm.plan_downloads(
        [make_entry("vae/a.safetensors", size=None)],
        str(tmp_path),
        existing_sizes={target: 123},
    )
    assert plan == []


def test_present_file_with_matching_size_is_skipped(tmp_path: Path) -> None:
    target = str(tmp_path / "vae" / "a.safetensors")
    plan = fm.plan_downloads(
        [make_entry("vae/a.safetensors", size=10)],
        str(tmp_path),
        existing_sizes={target: 10},
    )
    assert plan == []


def test_present_file_with_wrong_size_is_redownloaded(tmp_path: Path) -> None:
    target = str(tmp_path / "vae" / "a.safetensors")
    plan = fm.plan_downloads(
        [make_entry("vae/a.safetensors", size=10)],
        str(tmp_path),
        existing_sizes={target: 9},
    )
    assert [p["reason"] for p in plan] == ["size_mismatch"]


def test_required_flag_is_carried_into_plan(tmp_path: Path) -> None:
    manifest = [
        make_entry("vae/a.safetensors", required=True),
        make_entry("loras/b.safetensors", required=False),
    ]
    plan = fm.plan_downloads(manifest, str(tmp_path), existing_sizes={})
    assert {p["dest"]: p["required"] for p in plan} == {
        "vae/a.safetensors": True,
        "loras/b.safetensors": False,
    }


def test_only_missing_false_plans_present_files_too(tmp_path: Path) -> None:
    target = str(tmp_path / "vae" / "a.safetensors")
    plan = fm.plan_downloads(
        [make_entry("vae/a.safetensors", size=10)],
        str(tmp_path),
        existing_sizes={target: 10},
        only_missing=False,
    )
    assert [p["reason"] for p in plan] == ["forced"]


def test_probes_disk_when_existing_sizes_not_given(tmp_path: Path) -> None:
    (tmp_path / "vae").mkdir()
    (tmp_path / "vae" / "a.safetensors").write_bytes(b"0123456789")
    manifest = [
        make_entry("vae/a.safetensors", size=10),
        make_entry("vae/b.safetensors", size=10),
    ]
    plan = fm.plan_downloads(manifest, str(tmp_path))
    assert [p["dest"] for p in plan] == ["vae/b.safetensors"]


def test_partial_file_does_not_count_as_present(tmp_path: Path) -> None:
    (tmp_path / "vae").mkdir()
    (tmp_path / "vae" / "a.safetensors.part").write_bytes(b"0123")
    plan = fm.plan_downloads([make_entry("vae/a.safetensors", size=None)], str(tmp_path))
    assert [p["reason"] for p in plan] == ["missing"]


@pytest.mark.parametrize(
    "dest",
    ["../escape.safetensors", "/abs/path.safetensors", "vae/../../x.safetensors", ""],
)
def test_rejects_unsafe_dest(tmp_path: Path, dest: str) -> None:
    with pytest.raises(ValueError):
        fm.plan_downloads([make_entry(dest)], str(tmp_path), existing_sizes={})


def test_rejects_r2_key_outside_contract_layout(tmp_path: Path) -> None:
    bad = make_entry("vae/a.safetensors")
    bad["r2_key"] = "other/vae/a.safetensors"
    with pytest.raises(ValueError):
        fm.plan_downloads([bad], str(tmp_path), existing_sizes={})


def test_rejects_two_entries_writing_the_same_file(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        fm.plan_downloads(
            [make_entry("vae/a.safetensors"), make_entry("vae/a.safetensors")],
            str(tmp_path),
            existing_sizes={},
        )


def test_dest_root_sets_target_directory(tmp_path: Path) -> None:
    root = tmp_path / "app"
    plan = fm.plan_downloads(
        [config_entry("workflow_api.json", root)],
        str(tmp_path / "models"),
        existing_sizes={},
    )
    assert plan[0]["target"] == str(root / "workflow_api.json")
    assert plan[0]["reason"] == "always"
    assert plan[0]["required"] is True


def test_dest_root_must_be_absolute(tmp_path: Path) -> None:
    entry = make_entry("workflow_api.json", dest_root="app", always_download=True)
    with pytest.raises(ValueError):
        fm.plan_downloads([entry], str(tmp_path), existing_sizes={})


def test_config_entry_needs_config_prefix(tmp_path: Path) -> None:
    entry = config_entry("workflow_api.json", tmp_path / "app")
    entry["r2_key"] = "models/workflow_api.json"
    with pytest.raises(ValueError):
        fm.plan_downloads([entry], str(tmp_path), existing_sizes={})


def test_always_download_is_planned_even_when_present(tmp_path: Path) -> None:
    root = tmp_path / "app"
    root.mkdir()
    (root / "workflow_api.json").write_bytes(PAYLOAD)
    plan = fm.plan_downloads(
        [config_entry("workflow_api.json", root)],
        str(tmp_path),
        existing_sizes={str(root / "workflow_api.json"): len(PAYLOAD)},
    )
    assert [p["reason"] for p in plan] == ["always"]


def test_always_download_must_be_boolean(tmp_path: Path) -> None:
    entry = make_entry("workflow_api.json", dest_root="/app", always_download="yes")
    with pytest.raises(ValueError):
        fm.plan_downloads([entry], str(tmp_path), existing_sizes={})


def test_optional_if_env_must_look_like_an_env_name(tmp_path: Path) -> None:
    entry = make_entry("workflow_api.json", dest_root="/app", always_download=True, optional_if_env="not valid")
    with pytest.raises(ValueError):
        fm.plan_downloads([entry], str(tmp_path), existing_sizes={})


@pytest.mark.parametrize(
    ("scope", "expected"),
    [
        ("all", {"vae/a.safetensors", "workflow_api.json"}),
        ("models", {"vae/a.safetensors"}),
        ("config", {"workflow_api.json"}),
    ],
)
def test_scope_selects_model_or_config_entries(tmp_path: Path, scope: str, expected: set[str]) -> None:
    manifest = [
        make_entry("vae/a.safetensors"),
        config_entry("workflow_api.json", tmp_path / "app"),
    ]
    plan = fm.plan_downloads(manifest, str(tmp_path), existing_sizes={}, scope=scope)
    assert {p["dest"] for p in plan} == expected


def test_unknown_scope_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        fm.plan_downloads([make_entry("vae/a.safetensors")], str(tmp_path), existing_sizes={}, scope="bogus")  # type: ignore[arg-type]


# --------------------------------------------------------------------------
# waiver (WORKFLOW_OPTIONAL) and fatal-failure rules
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("entry_flag", "env_value", "expected"),
    [
        (WAIVER_ENV, "1", True),
        (WAIVER_ENV, "0", False),
        (WAIVER_ENV, "true", False),
        (WAIVER_ENV, None, False),
        (None, "1", False),
    ],
)
def test_waiver_needs_entry_flag_and_env_value_one(entry_flag: str | None, env_value: str | None, expected: bool) -> None:
    entry = make_entry("workflow_api.json", dest_root="/app", always_download=True, optional_if_env=entry_flag)
    env = {} if env_value is None else {WAIVER_ENV: env_value}
    assert fm.waiver_active(entry, env) is expected


@pytest.mark.parametrize(
    ("ok", "required", "missing", "waivable", "fatal"),
    [
        (True, True, False, False, False),
        (False, False, False, False, False),  # optional model failed: warning only
        (False, True, False, False, True),  # required model failed: fatal
        (False, True, True, False, True),  # required and missing, not waivable: fatal
        (False, True, True, True, False),  # missing but waived by env: warning only
        (False, True, False, True, True),  # network error is never waived
    ],
)
def test_is_fatal_rules(ok: bool, required: bool, missing: bool, waivable: bool, fatal: bool) -> None:
    result = fm.FetchResult(
        target="/x",
        required=required,
        ok=ok,
        missing=missing,
        waivable=waivable,
        error=None if ok else "boom",
    )
    assert fm.is_fatal(result) is fatal


# --------------------------------------------------------------------------
# download_one: retries, verification, atomic rename, stale config removal
# --------------------------------------------------------------------------


def test_download_retries_then_succeeds(tmp_path: Path) -> None:
    item = plan_one(tmp_path, size=len(PAYLOAD))
    s3 = FakeS3({"models/vae/a.safetensors": PAYLOAD}, fail_first=2)
    sleeps: list[float] = []

    fm.download_one(s3, "test-bucket", item, sleep=sleeps.append)

    assert s3.calls == ["models/vae/a.safetensors"] * 3
    assert sleeps == [2.0, 4.0]
    assert Path(item["target"]).read_bytes() == PAYLOAD
    assert not Path(item["target"] + ".part").exists()


def test_download_gives_up_after_three_attempts(tmp_path: Path) -> None:
    item = plan_one(tmp_path)
    s3 = FakeS3({}, fail_first=99)
    sleeps: list[float] = []

    with pytest.raises(fm.DownloadError) as info:
        fm.download_one(s3, "test-bucket", item, sleep=sleeps.append)

    assert info.value.missing is False
    assert len(s3.calls) == 3
    assert len(sleeps) == 2
    assert not Path(item["target"]).exists()
    assert not Path(item["target"] + ".part").exists()


def test_permanent_404_is_not_retried_and_is_reported_as_missing(tmp_path: Path) -> None:
    item = plan_one(tmp_path)
    s3 = FakeS3({})
    sleeps: list[float] = []

    with pytest.raises(fm.DownloadError) as info:
        fm.download_one(s3, "test-bucket", item, sleep=sleeps.append)

    assert info.value.missing is True
    assert len(s3.calls) == 1
    assert sleeps == []


def test_missing_always_download_removes_stale_copy(tmp_path: Path) -> None:
    root = tmp_path / "app"
    root.mkdir()
    stale = root / "workflow_api.json"
    stale.write_bytes(b"old workflow from an earlier boot")
    item = fm.plan_downloads([config_entry("workflow_api.json", root)], str(tmp_path), existing_sizes={})[0]

    with pytest.raises(fm.DownloadError) as info:
        fm.download_one(FakeS3({}), "test-bucket", item, sleep=lambda s: None)

    assert info.value.missing is True
    assert not stale.exists()


def test_sha256_match_is_accepted(tmp_path: Path) -> None:
    item = plan_one(tmp_path, sha256=hashlib.sha256(PAYLOAD).hexdigest())
    fm.download_one(
        FakeS3({"models/vae/a.safetensors": PAYLOAD}), "test-bucket", item, sleep=lambda s: None
    )
    assert Path(item["target"]).read_bytes() == PAYLOAD


def test_sha256_mismatch_is_retried_then_fails(tmp_path: Path) -> None:
    item = plan_one(tmp_path, sha256=hashlib.sha256(b"something else").hexdigest())
    s3 = FakeS3({"models/vae/a.safetensors": PAYLOAD})

    with pytest.raises(fm.DownloadError):
        fm.download_one(s3, "test-bucket", item, sleep=lambda s: None)

    assert len(s3.calls) == 3
    assert not Path(item["target"]).exists()
    assert not Path(item["target"] + ".part").exists()


def test_size_mismatch_after_download_fails(tmp_path: Path) -> None:
    item = plan_one(tmp_path, size=len(PAYLOAD) + 1)
    s3 = FakeS3({"models/vae/a.safetensors": PAYLOAD})

    with pytest.raises(fm.DownloadError):
        fm.download_one(s3, "test-bucket", item, sleep=lambda s: None)

    assert not Path(item["target"]).exists()


# --------------------------------------------------------------------------
# the real manifest file
# --------------------------------------------------------------------------


def load_real_manifest() -> list[dict[str, Any]]:
    return fm.load_manifest(DOCKER_DIR / "models.manifest.json")


def test_real_manifest_model_entries() -> None:
    models = [e for e in load_real_manifest() if not e.get("always_download")]
    assert {e["dest"] for e in models if e["required"]} == KNOWN_MODELS
    assert {e["dest"] for e in models if not e["required"]} == TODO_OPTIONAL
    assert all(e["r2_key"] == "models/" + e["dest"] for e in models)


def test_real_manifest_workflow_entries() -> None:
    config = [e for e in load_real_manifest() if e.get("always_download")]
    assert {e["dest"] for e in config} == CONFIG_FILES
    for entry in config:
        assert entry["dest_root"] == "/app"
        assert entry["r2_key"] == "config/" + entry["dest"]
        assert entry["required"] is True
        assert entry["optional_if_env"] == WAIVER_ENV


def test_real_manifest_plan_by_scope(tmp_path: Path) -> None:
    manifest = load_real_manifest()
    assert len(fm.plan_downloads(manifest, str(tmp_path), existing_sizes={})) == 9
    assert len(fm.plan_downloads(manifest, str(tmp_path), existing_sizes={}, scope="models")) == 7
    config_plan = fm.plan_downloads(manifest, str(tmp_path), existing_sizes={}, scope="config")
    assert {p["target"] for p in config_plan} == {"/app/workflow_api.json", "/app/workflow_map.json"}


# --------------------------------------------------------------------------
# main(): exit codes and boot-time behaviour
# --------------------------------------------------------------------------


def write_manifest(tmp_path: Path, entries: list[dict[str, Any]]) -> Path:
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(entries), encoding="utf-8")
    return path


@pytest.fixture
def r2_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in R2_ENV.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv(WAIVER_ENV, raising=False)
    monkeypatch.setattr(fm, "BACKOFF_BASE_S", 0.0)
    monkeypatch.setattr(fm, "_transfer_config", lambda: None)


def test_main_exit_zero_when_only_optional_model_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, r2_env: None
) -> None:
    s3 = FakeS3({"models/vae/req.safetensors": PAYLOAD})
    monkeypatch.setattr(fm, "make_client", lambda env: s3)
    manifest = write_manifest(
        tmp_path,
        [make_entry("vae/req.safetensors"), make_entry("loras/opt.safetensors", required=False)],
    )
    models = tmp_path / "models"

    rc = fm.main(["--manifest", str(manifest), "--models-dir", str(models)])

    assert rc == 0
    assert (models / "vae" / "req.safetensors").read_bytes() == PAYLOAD
    assert not (models / "loras" / "opt.safetensors").exists()


def test_main_exit_one_when_required_model_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, r2_env: None
) -> None:
    monkeypatch.setattr(fm, "make_client", lambda env: FakeS3({}))
    manifest = write_manifest(tmp_path, [make_entry("vae/req.safetensors")])

    rc = fm.main(["--manifest", str(manifest), "--models-dir", str(tmp_path / "models")])

    assert rc == 1


def test_main_exit_two_when_r2_env_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for name in R2_ENV:
        monkeypatch.delenv(name, raising=False)
    manifest = write_manifest(tmp_path, [make_entry("vae/req.safetensors")])

    rc = fm.main(["--manifest", str(manifest), "--models-dir", str(tmp_path / "models")])

    assert rc == 2


def test_main_skips_client_when_nothing_to_download(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for name in R2_ENV:
        monkeypatch.delenv(name, raising=False)
    models = tmp_path / "models"
    (models / "vae").mkdir(parents=True)
    (models / "vae" / "req.safetensors").write_bytes(PAYLOAD)

    def no_client(env: object) -> None:
        raise AssertionError("no S3 client should be created when nothing is missing")

    monkeypatch.setattr(fm, "make_client", no_client)
    manifest = write_manifest(tmp_path, [make_entry("vae/req.safetensors", size=len(PAYLOAD))])

    rc = fm.main(["--manifest", str(manifest), "--models-dir", str(models)])

    assert rc == 0


def test_main_refetches_config_even_when_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, r2_env: None
) -> None:
    root = tmp_path / "app"
    root.mkdir()
    (root / "workflow_api.json").write_bytes(b"old")
    s3 = FakeS3({"config/workflow_api.json": b"new"})
    monkeypatch.setattr(fm, "make_client", lambda env: s3)
    manifest = write_manifest(tmp_path, [config_entry("workflow_api.json", root)])

    rc = fm.main(["--manifest", str(manifest), "--models-dir", str(tmp_path / "models")])

    assert rc == 0
    assert (root / "workflow_api.json").read_bytes() == b"new"
    assert s3.calls == ["config/workflow_api.json"]


def test_main_missing_workflow_is_fatal_without_waiver(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, r2_env: None
) -> None:
    root = tmp_path / "app"
    monkeypatch.setattr(fm, "make_client", lambda env: FakeS3({}))
    manifest = write_manifest(tmp_path, [config_entry("workflow_map.json", root)])

    rc = fm.main(["--manifest", str(manifest), "--models-dir", str(tmp_path / "models")])

    assert rc == 1


def test_main_missing_workflow_is_waived_with_env_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, r2_env: None
) -> None:
    root = tmp_path / "app"
    root.mkdir()
    stale = root / "workflow_map.json"
    stale.write_bytes(b"stale map")
    monkeypatch.setenv(WAIVER_ENV, "1")
    monkeypatch.setattr(fm, "make_client", lambda env: FakeS3({}))
    manifest = write_manifest(tmp_path, [config_entry("workflow_map.json", root)])

    rc = fm.main(["--manifest", str(manifest), "--models-dir", str(tmp_path / "models")])

    assert rc == 0
    assert not stale.exists()


def test_main_network_error_on_workflow_stays_fatal_with_waiver(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, r2_env: None
) -> None:
    root = tmp_path / "app"
    monkeypatch.setenv(WAIVER_ENV, "1")
    monkeypatch.setattr(fm, "make_client", lambda env: FakeS3({}, fail_first=99))
    manifest = write_manifest(tmp_path, [config_entry("workflow_api.json", root)])

    rc = fm.main(["--manifest", str(manifest), "--models-dir", str(tmp_path / "models")])

    assert rc == 1


def test_main_scope_config_fetches_only_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, r2_env: None
) -> None:
    root = tmp_path / "app"
    s3 = FakeS3({"config/workflow_api.json": b"{}", "models/vae/req.safetensors": PAYLOAD})
    monkeypatch.setattr(fm, "make_client", lambda env: s3)
    manifest = write_manifest(
        tmp_path,
        [make_entry("vae/req.safetensors"), config_entry("workflow_api.json", root)],
    )
    models = tmp_path / "models"

    rc = fm.main(["--manifest", str(manifest), "--models-dir", str(models), "--scope", "config"])

    assert rc == 0
    assert s3.calls == ["config/workflow_api.json"]
    assert not (models / "vae" / "req.safetensors").exists()
