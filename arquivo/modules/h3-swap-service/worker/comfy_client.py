"""Client for ComfyUI's HTTP API: queue a prompt, poll its history, fetch outputs."""

from __future__ import annotations

import json
import time
import uuid
from typing import Any

import requests

_HTTP_TIMEOUT_S = 60
_VIEW_TIMEOUT_S = 300
_DEFAULT_POLL_S = 2.0


class ComfyError(RuntimeError):
    """ComfyUI rejected a prompt, failed during execution, timed out, or was unreachable."""


class ComfyClient:
    def __init__(
        self,
        base_url: str,
        timeout_s: int = 2400,
        session: requests.Session | None = None,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._timeout_s = timeout_s
        self._session = session if session is not None else requests.Session()
        self._client_id = str(uuid.uuid4())

    def ready(self) -> bool:
        try:
            response = self._session.get(f"{self._base}/system_stats", timeout=_HTTP_TIMEOUT_S)
        except requests.RequestException:
            return False
        return response.status_code == 200

    def queue_prompt(self, workflow: dict[str, Any]) -> str:
        payload: dict[str, Any] = {"prompt": workflow, "client_id": self._client_id}
        try:
            response = self._session.post(f"{self._base}/prompt", json=payload, timeout=_HTTP_TIMEOUT_S)
        except requests.RequestException as exc:
            raise ComfyError(f"could not reach ComfyUI at {self._base}: {exc}") from exc

        data = _json_or_none(response)
        node_text = _node_error_text(data.get("node_errors")) if isinstance(data, dict) else ""

        if response.status_code >= 400:
            error = data.get("error") if isinstance(data, dict) else None
            message = error.get("message") if isinstance(error, dict) else None
            detail = str(message or "no details")
            if node_text:
                detail = f"{detail}; {node_text}"
            raise ComfyError(f"ComfyUI rejected prompt (HTTP {response.status_code}): {detail}")

        if not isinstance(data, dict):
            raise ComfyError("ComfyUI returned a non-JSON response to /prompt")
        if node_text:
            raise ComfyError(f"ComfyUI node errors: {node_text}")

        prompt_id = data.get("prompt_id")
        if not isinstance(prompt_id, str) or not prompt_id:
            raise ComfyError("ComfyUI response has no prompt_id")
        return prompt_id

    def wait_for_outputs(
        self,
        prompt_id: str,
        output_node: str,
        kind: str,
        poll_s: float = _DEFAULT_POLL_S,
    ) -> list[dict[str, Any]]:
        deadline = time.monotonic() + self._timeout_s
        while True:
            entry = self._history_entry(prompt_id)
            if entry is not None:
                raw_status = entry.get("status")
                status: dict[str, Any] = raw_status if isinstance(raw_status, dict) else {}
                if status.get("status_str") == "error":
                    messages = json.dumps(status.get("messages", []))[:500]
                    raise ComfyError(f"ComfyUI execution failed for prompt {prompt_id}: {messages}")
                if status.get("completed") is True:
                    return _extract_outputs(entry, output_node, kind)
            if time.monotonic() >= deadline:
                raise ComfyError(f"timed out after {self._timeout_s}s waiting for prompt {prompt_id}")
            time.sleep(poll_s)

    def download_output(self, item: dict[str, Any]) -> bytes:
        filename = item.get("filename")
        if not isinstance(filename, str) or not filename:
            raise ComfyError("output item has no filename")
        params = {
            "filename": filename,
            "subfolder": item.get("subfolder", ""),
            "type": item.get("type", "output"),
        }
        try:
            response = self._session.get(f"{self._base}/view", params=params, timeout=_VIEW_TIMEOUT_S)
        except requests.RequestException as exc:
            raise ComfyError(f"could not download {filename}: {exc}") from exc
        if response.status_code >= 400:
            raise ComfyError(f"could not download {filename} (HTTP {response.status_code})")
        return bytes(response.content)

    def _history_entry(self, prompt_id: str) -> dict[str, Any] | None:
        try:
            response = self._session.get(f"{self._base}/history/{prompt_id}", timeout=_HTTP_TIMEOUT_S)
        except requests.RequestException as exc:
            raise ComfyError(f"history request failed: {exc}") from exc
        if response.status_code >= 400:
            raise ComfyError(f"history request failed (HTTP {response.status_code})")
        data = _json_or_none(response)
        if not isinstance(data, dict):
            raise ComfyError("history response is not a JSON object")
        entry = data.get(prompt_id)
        return entry if isinstance(entry, dict) else None


def _json_or_none(response: Any) -> Any:
    try:
        return response.json()
    except ValueError:
        return None


def _node_error_text(node_errors: Any) -> str:
    if not isinstance(node_errors, dict) or not node_errors:
        return ""
    parts: list[str] = []
    for node_id, info in node_errors.items():
        messages: list[str] = []
        if isinstance(info, dict):
            for err in info.get("errors") or []:
                if not isinstance(err, dict):
                    continue
                message = str(err.get("message", ""))
                detail = err.get("details")
                messages.append(f"{message} ({detail})" if detail else message)
        parts.append(f"node {node_id}: {'; '.join(messages) or 'error'}")
    return "; ".join(parts)


def _extract_outputs(entry: dict[str, Any], output_node: str, kind: str) -> list[dict[str, Any]]:
    raw_outputs = entry.get("outputs")
    outputs: dict[str, Any] = raw_outputs if isinstance(raw_outputs, dict) else {}
    node_outputs = outputs.get(str(output_node))
    if not isinstance(node_outputs, dict):
        raise ComfyError(f"output node {output_node} produced no outputs")
    items = node_outputs.get(kind)
    if not isinstance(items, list):
        raise ComfyError(f"output node {output_node} produced no '{kind}' files")
    result = [item for item in items if isinstance(item, dict) and item.get("filename")]
    if not result:
        raise ComfyError(f"output node {output_node} produced no '{kind}' files")
    return result
