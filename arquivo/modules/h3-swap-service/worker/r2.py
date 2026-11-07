"""Cloudflare R2 access over the S3 API (CONTRACT section 3)."""

from __future__ import annotations

from typing import Any

import boto3
from botocore.exceptions import BotoCoreError, ClientError

_MISSING_CODES = frozenset({"404", "NoSuchKey", "NotFound"})


class R2Error(RuntimeError):
    """A failed R2 transfer or lookup."""


class R2:
    def __init__(self, endpoint: str, access_key_id: str, secret_access_key: str, bucket: str) -> None:
        self._bucket = bucket
        self._s3 = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            region_name="auto",
        )

    def download(self, key: str, dest_path: str) -> None:
        try:
            self._s3.download_file(self._bucket, key, dest_path)
        except (ClientError, BotoCoreError) as exc:
            raise R2Error(f"download of {key} failed: {exc}") from exc

    def upload(self, src_path: str, key: str, content_type: str | None = None) -> None:
        kwargs: dict[str, Any] = {}
        if content_type:
            kwargs["ExtraArgs"] = {"ContentType": content_type}
        try:
            self._s3.upload_file(src_path, self._bucket, key, **kwargs)
        except (ClientError, BotoCoreError) as exc:
            raise R2Error(f"upload to {key} failed: {exc}") from exc

    def exists(self, key: str) -> bool:
        try:
            self._s3.head_object(Bucket=self._bucket, Key=key)
        except ClientError as exc:
            if _is_missing(exc):
                return False
            raise R2Error(f"head of {key} failed: {exc}") from exc
        except BotoCoreError as exc:
            raise R2Error(f"head of {key} failed: {exc}") from exc
        return True


def _is_missing(exc: ClientError) -> bool:
    error = exc.response.get("Error", {})
    status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
    return str(error.get("Code", "")) in _MISSING_CODES or status == 404
