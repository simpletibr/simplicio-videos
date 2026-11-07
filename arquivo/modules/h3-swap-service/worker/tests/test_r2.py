from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from unittest.mock import MagicMock

import boto3
import pytest
from botocore.exceptions import ClientError

from worker.r2 import R2, R2Error


@dataclass
class FakeS3:
    client: MagicMock
    factory: MagicMock


@pytest.fixture
def s3(monkeypatch: pytest.MonkeyPatch) -> FakeS3:
    client = MagicMock(name="s3-client")
    factory = MagicMock(name="boto3.client", return_value=client)
    monkeypatch.setattr(boto3, "client", factory)
    return FakeS3(client=client, factory=factory)


def _client_error(code: str, status: int) -> ClientError:
    return ClientError(
        {"Error": {"Code": code, "Message": "test"}, "ResponseMetadata": {"HTTPStatusCode": status}},
        "HeadObject",
    )


def make_r2() -> R2:
    return R2("https://acct.r2.example.com", "AK", "SK", "bkt")


def test_client_targets_endpoint_with_auto_region(s3: FakeS3) -> None:
    make_r2()
    s3.factory.assert_called_once_with(
        "s3",
        endpoint_url="https://acct.r2.example.com",
        aws_access_key_id="AK",
        aws_secret_access_key="SK",
        region_name="auto",
    )


def test_download_fetches_key_to_destination(s3: FakeS3, tmp_path: Path) -> None:
    dest = str(tmp_path / "source.mp4")
    make_r2().download("uploads/j/source.mp4", dest)
    s3.client.download_file.assert_called_once_with("bkt", "uploads/j/source.mp4", dest)


def test_download_missing_key_raises_r2_error(s3: FakeS3, tmp_path: Path) -> None:
    s3.client.download_file.side_effect = _client_error("404", 404)
    with pytest.raises(R2Error):
        make_r2().download("uploads/j/none.mp4", str(tmp_path / "x"))


def test_upload_sets_content_type(s3: FakeS3) -> None:
    make_r2().upload("/work/result.mp4", "outputs/j/result.mp4", "video/mp4")
    s3.client.upload_file.assert_called_once_with(
        "/work/result.mp4", "bkt", "outputs/j/result.mp4", ExtraArgs={"ContentType": "video/mp4"}
    )


def test_upload_without_content_type_passes_no_extra_args(s3: FakeS3) -> None:
    make_r2().upload("/work/blob.bin", "k")
    args, kwargs = s3.client.upload_file.call_args
    assert args == ("/work/blob.bin", "bkt", "k")
    assert "ExtraArgs" not in kwargs


def test_upload_failure_raises_r2_error(s3: FakeS3) -> None:
    s3.client.upload_file.side_effect = _client_error("AccessDenied", 403)
    with pytest.raises(R2Error):
        make_r2().upload("/work/result.mp4", "outputs/j/result.mp4", "video/mp4")


def test_exists_true_when_head_succeeds(s3: FakeS3) -> None:
    s3.client.head_object.return_value = {}
    assert make_r2().exists("models/x.safetensors") is True
    s3.client.head_object.assert_called_once_with(Bucket="bkt", Key="models/x.safetensors")


def test_exists_false_on_404(s3: FakeS3) -> None:
    s3.client.head_object.side_effect = _client_error("404", 404)
    assert make_r2().exists("missing") is False


def test_exists_false_on_no_such_key(s3: FakeS3) -> None:
    s3.client.head_object.side_effect = _client_error("NoSuchKey", 404)
    assert make_r2().exists("missing") is False


def test_exists_raises_on_other_errors(s3: FakeS3) -> None:
    s3.client.head_object.side_effect = _client_error("AccessDenied", 403)
    with pytest.raises(R2Error):
        make_r2().exists("secret")
