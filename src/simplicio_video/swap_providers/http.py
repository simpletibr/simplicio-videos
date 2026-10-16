"""HTTP for the swap adapters and the openverse client: standard library only (urllib). Every caller goes through
`request`, so tests replace this one function and no test touches the network. Headers carry the API key: they are never
logged or stored."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field


class NetworkError(Exception):
    """The request did not reach the server (DNS, TLS, timeout, offline mode). The message never carries headers."""


@dataclass
class Response:
    status: int
    body: bytes
    headers: dict = field(default_factory=dict)  # lowercase names (Retry-After, x-ratelimit-*)

    def json(self):
        try:
            return json.loads(self.body.decode("utf8"))
        except (ValueError, UnicodeDecodeError):
            return None


def _lower(headers) -> dict:
    return {str(k).lower(): str(v) for k, v in (headers.items() if headers is not None else [])}


def request(method: str, url: str, headers: dict | None = None, json_body: dict | None = None, timeout: float = 60,
            form: dict | None = None) -> Response:
    if os.environ.get("SIMPLICIO_OFFLINE", "").strip().lower() in ("1", "true", "yes", "on"):
        raise NetworkError("SIMPLICIO_OFFLINE=1: rede bloqueada")
    data = None
    hdrs = dict(headers or {})
    if json_body is not None:
        data = json.dumps(json_body).encode("utf8")
        hdrs.setdefault("Content-Type", "application/json")
    elif form is not None:  # application/x-www-form-urlencoded (OAuth2 token endpoints)
        data = urllib.parse.urlencode(form).encode("utf8")
        hdrs.setdefault("Content-Type", "application/x-www-form-urlencoded")
    req = urllib.request.Request(url, data=data, method=method, headers=hdrs)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 (URLs chosen by the adapters)
            return Response(r.status, r.read(), _lower(r.headers))
    except urllib.error.HTTPError as e:
        return Response(e.code, e.read() if hasattr(e, "read") else b"", _lower(getattr(e, "headers", None)))
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise NetworkError(f"falha de rede: {type(e).__name__}") from None
