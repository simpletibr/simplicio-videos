from __future__ import annotations

import base64
from typing import Any
from unittest.mock import MagicMock

import pytest
import requests

from worker.queue_client import QueueClient, QueueError, QueueMessage
from worker.tests.fixtures import b64_json

ACCOUNT = "acct-1"
QUEUE = "queue-1"
BASE = f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT}/queues/{QUEUE}/messages"
PULL_URL = f"{BASE}/pull"
ACK_URL = f"{BASE}/ack"


class FakeResponse:
    def __init__(self, status_code: int = 200, payload: Any = None, text: str = "") -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self) -> Any:
        if self._payload is None:
            raise ValueError("no JSON body")
        return self._payload


def cf_ok(result: Any) -> dict[str, Any]:
    return {"success": True, "errors": [], "messages": [], "result": result}


def cf_fail(message: str, status: int = 200) -> FakeResponse:
    payload = {"success": False, "errors": [{"code": 10000, "message": message}], "messages": [], "result": None}
    return FakeResponse(status, payload)


def raw_message(**overrides: Any) -> dict[str, Any]:
    message: dict[str, Any] = {
        "id": "msg-1",
        "lease_id": "lease-1",
        "attempts": 2,
        "body": b64_json({"job_id": "j1"}),
        "timestamp_ms": 1_700_000_000_000,
        "metadata": {},
    }
    message.update(overrides)
    return message


def client_returning(response: Any) -> tuple[QueueClient, MagicMock]:
    session = MagicMock(spec=requests.Session)
    session.post.return_value = response
    return QueueClient(ACCOUNT, QUEUE, "tok-123", session=session), session


def test_pull_decodes_base64_json_body() -> None:
    body = {"job_id": "j1", "duration_s": 10}
    response = FakeResponse(
        200,
        cf_ok({"messages": [raw_message(body=b64_json(body))], "message_backlog_count": 0}),
    )
    client, _ = client_returning(response)
    assert client.pull() == [QueueMessage(id="msg-1", lease_id="lease-1", attempts=2, body=body)]


def test_pull_sends_exact_endpoint_body_and_bearer_token() -> None:
    client, session = client_returning(FakeResponse(200, cf_ok({"messages": [], "message_backlog_count": 0})))
    client.pull(batch_size=1, visibility_timeout_ms=900_000)
    args, kwargs = session.post.call_args
    assert args[0] == PULL_URL
    assert kwargs["json"] == {"visibility_timeout_ms": 900_000, "batch_size": 1}
    assert kwargs["headers"]["Authorization"] == "Bearer tok-123"
    assert kwargs["timeout"] > 0


def test_pull_defaults_to_one_message_and_45_minute_visibility() -> None:
    client, session = client_returning(FakeResponse(200, cf_ok({"messages": []})))
    client.pull()
    assert session.post.call_args.kwargs["json"] == {"visibility_timeout_ms": 2_700_000, "batch_size": 1}


def test_pull_empty_result_returns_empty_list() -> None:
    client, _ = client_returning(FakeResponse(200, cf_ok({"messages": [], "message_backlog_count": 0})))
    assert client.pull() == []


def test_pull_null_result_returns_empty_list() -> None:
    client, _ = client_returning(FakeResponse(200, cf_ok(None)))
    assert client.pull() == []


def test_pull_http_error_raises_queue_error() -> None:
    client, _ = client_returning(cf_fail("Internal error", status=500))
    with pytest.raises(QueueError, match="500"):
        client.pull()


def test_pull_success_false_raises_with_cloudflare_message() -> None:
    client, _ = client_returning(cf_fail("Authentication error"))
    with pytest.raises(QueueError, match="Authentication error"):
        client.pull()


def test_pull_network_failure_raises_queue_error() -> None:
    client, session = client_returning(None)
    session.post.side_effect = requests.ConnectionError("connection reset")
    with pytest.raises(QueueError):
        client.pull()


def test_pull_non_json_response_raises_queue_error() -> None:
    client, _ = client_returning(FakeResponse(502, None, text="<html>bad gateway</html>"))
    with pytest.raises(QueueError):
        client.pull()


def test_pull_invalid_base64_body_raises_queue_error() -> None:
    client, _ = client_returning(
        FakeResponse(200, cf_ok({"messages": [raw_message(body="%%% not base64 %%%")]}))
    )
    with pytest.raises(QueueError):
        client.pull()


def test_pull_non_json_body_raises_queue_error() -> None:
    body = base64.b64encode(b"not json").decode("ascii")
    client, _ = client_returning(FakeResponse(200, cf_ok({"messages": [raw_message(body=body)]})))
    with pytest.raises(QueueError):
        client.pull()


def test_pull_non_object_body_raises_queue_error() -> None:
    body = base64.b64encode(b"[1, 2]").decode("ascii")
    client, _ = client_returning(FakeResponse(200, cf_ok({"messages": [raw_message(body=body)]})))
    with pytest.raises(QueueError):
        client.pull()


def test_pull_message_without_lease_id_raises_queue_error() -> None:
    message = raw_message()
    del message["lease_id"]
    client, _ = client_returning(FakeResponse(200, cf_ok({"messages": [message]})))
    with pytest.raises(QueueError):
        client.pull()


def test_ack_posts_every_lease_id_with_empty_retries() -> None:
    client, session = client_returning(FakeResponse(200, cf_ok(None)))
    client.ack(["lease-1", "lease-2"])
    args, kwargs = session.post.call_args
    assert args[0] == ACK_URL
    assert kwargs["json"] == {
        "acks": [{"lease_id": "lease-1"}, {"lease_id": "lease-2"}],
        "retries": [],
    }
    assert kwargs["headers"]["Authorization"] == "Bearer tok-123"


def test_ack_with_no_leases_makes_no_request() -> None:
    client, session = client_returning(FakeResponse(200, cf_ok(None)))
    client.ack([])
    session.post.assert_not_called()


def test_ack_failure_raises_queue_error() -> None:
    client, _ = client_returning(cf_fail("Bad lease", status=400))
    with pytest.raises(QueueError, match="Bad lease"):
        client.ack(["lease-1"])


def test_retry_defaults_to_sixty_second_delay() -> None:
    client, session = client_returning(FakeResponse(200, cf_ok(None)))
    client.retry("lease-1")
    args, kwargs = session.post.call_args
    assert args[0] == ACK_URL
    assert kwargs["json"] == {"acks": [], "retries": [{"lease_id": "lease-1", "delay_seconds": 60}]}


def test_retry_uses_custom_delay() -> None:
    client, session = client_returning(FakeResponse(200, cf_ok(None)))
    client.retry("lease-9", delay_seconds=120)
    assert session.post.call_args.kwargs["json"]["retries"] == [{"lease_id": "lease-9", "delay_seconds": 120}]
