"""Cloudflare Queues HTTP pull consumer (CONTRACT section 4)."""

from __future__ import annotations

import base64
import binascii
import json
from dataclasses import dataclass
from typing import Any

import requests

API_BASE = "https://api.cloudflare.com/client/v4"
_HTTP_TIMEOUT_S = 30


class QueueError(RuntimeError):
    """Any failure talking to the Cloudflare Queue or decoding a message."""


@dataclass(frozen=True)
class QueueMessage:
    id: str
    lease_id: str
    attempts: int
    body: dict[str, Any]


class QueueClient:
    def __init__(
        self,
        account_id: str,
        queue_id: str,
        api_token: str,
        session: requests.Session | None = None,
    ) -> None:
        self._base = f"{API_BASE}/accounts/{account_id}/queues/{queue_id}/messages"
        self._headers = {"Authorization": f"Bearer {api_token}", "Content-Type": "application/json"}
        self._session = session if session is not None else requests.Session()

    def pull(self, batch_size: int = 1, visibility_timeout_ms: int = 2700000) -> list[QueueMessage]:
        result = self._post(
            "pull",
            {"visibility_timeout_ms": visibility_timeout_ms, "batch_size": batch_size},
        )
        raw_messages = result.get("messages") if isinstance(result, dict) else None
        if not raw_messages:
            return []
        return [_parse_message(raw) for raw in raw_messages]

    def ack(self, lease_ids: list[str]) -> None:
        if not lease_ids:
            return
        self._post("ack", {"acks": [{"lease_id": lease_id} for lease_id in lease_ids], "retries": []})

    def retry(self, lease_id: str, delay_seconds: int = 60) -> None:
        self._post(
            "ack",
            {"acks": [], "retries": [{"lease_id": lease_id, "delay_seconds": delay_seconds}]},
        )

    def _post(self, endpoint: str, payload: dict[str, Any]) -> Any:
        url = f"{self._base}/{endpoint}"
        try:
            response = self._session.post(url, json=payload, headers=self._headers, timeout=_HTTP_TIMEOUT_S)
        except requests.RequestException as exc:
            raise QueueError(f"queue {endpoint} request failed: {exc}") from exc

        try:
            data: Any = response.json()
        except ValueError:
            data = None

        if response.status_code >= 400 or not isinstance(data, dict) or data.get("success") is not True:
            detail = _cloudflare_errors(data) or str(getattr(response, "text", ""))[:200]
            raise QueueError(f"queue {endpoint} failed (HTTP {response.status_code}): {detail}")
        return data.get("result")


def _parse_message(raw: Any) -> QueueMessage:
    try:
        message_id = str(raw["id"])
        lease_id = str(raw["lease_id"])
        attempts = int(raw.get("attempts", 1))
        encoded = raw["body"]
    except (KeyError, TypeError, ValueError) as exc:
        raise QueueError(f"malformed queue message: {exc}") from exc

    try:
        decoded = base64.b64decode(encoded, validate=True)
        body = json.loads(decoded)
    except (TypeError, ValueError, binascii.Error) as exc:
        raise QueueError(f"cannot decode body of message {message_id}: {exc}") from exc

    if not isinstance(body, dict):
        raise QueueError(f"body of message {message_id} is not a JSON object")
    return QueueMessage(id=message_id, lease_id=lease_id, attempts=attempts, body=body)


def _cloudflare_errors(data: Any) -> str:
    if not isinstance(data, dict):
        return ""
    errors = data.get("errors")
    if not isinstance(errors, list):
        return ""
    texts = [str(err.get("message", err)) if isinstance(err, dict) else str(err) for err in errors]
    return "; ".join(texts)
