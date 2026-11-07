"""Network policy of the engine: whether the network may be used at all, and the one HTTP client. Standard library only (a leaf).

* `offline()` is the one reading of SIMPLICIO_OFFLINE (1, true, yes or on; spaces and case ignored). `motivo_offline(acao)` is the
  opening of every refusal made in offline mode: "modo offline (SIMPLICIO_OFFLINE=1): não vou <acao>".
* `request` is the HTTP client of the swap adapters and of the Openverse client (urllib only). Every caller goes through it, so tests
  replace this one function and no test touches the network. Headers carry the API key: they are never logged or stored. It refuses
  to run in offline mode. `NoRedirect` never follows a redirect (urllib would forward the Authorization header to the new host).

The standard-library HTTP stack (urllib, and through it socket, ssl, http.client and email) is imported when a request is made, not when
this module is imported: `offline`, `motivo_offline`, `Response` and `NetworkError` need none of it, and `trilha_base` (so every track,
instagram included) imports this module for `offline` alone. `NoRedirect` is a subclass of a urllib class, so it is built on first access
(module `__getattr__`, PEP 562) and cached in the module: every access, `from simplicio_video.rede import NoRedirect` included, is the same object.

`swap_providers/http.py` is this module under its old name (it imports it and takes its place in sys.modules), so `request`, `Response`,
`NetworkError` and `NoRedirect` are the same objects under both names.
"""
from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass, field

_VERDADEIROS = ("1", "true", "yes", "on")
PREFIXO_OFFLINE = "modo offline (SIMPLICIO_OFFLINE=1): não vou "  # what every refusal in offline mode opens with


def offline(env: Mapping[str, str] | None = None) -> bool:
    """True when SIMPLICIO_OFFLINE is 1, true, yes or on (spaces and case ignored): the network must not be used. Without `env` it reads
    the `os.environ` that is there at the call (a default argument would keep the object `os.environ` was at import)."""
    valor = os.environ.get("SIMPLICIO_OFFLINE", "") if env is None else env.get("SIMPLICIO_OFFLINE", "")
    return valor.strip().lower() in _VERDADEIROS


def motivo_offline(acao: str) -> str | None:
    """The refusal of an action that needs the network, or None when the network may be used: "modo offline (SIMPLICIO_OFFLINE=1):
    não vou <acao>" (`acao` is the rest of the sentence, with whatever the caller adds after it)."""
    if not offline():
        return None
    return PREFIXO_OFFLINE + acao


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


def _no_redirect():
    """The `NoRedirect` class: built the first time it is needed (it subclasses a urllib class, and urllib is not imported with this module)
    and cached in the module, so `rede.NoRedirect` and the handler `request` uses are one object. `setdefault` is atomic: threads that race
    on the first access all get the one class that won."""
    cached = globals().get("NoRedirect")
    if cached is not None:
        return cached
    import urllib.request

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        """Never follow a redirect: urllib would forward the Authorization header to the new host."""

        __qualname__ = "NoRedirect"  # not `_no_redirect.<locals>.NoRedirect`: the name it always had

        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None

    return globals().setdefault("NoRedirect", NoRedirect)


def __getattr__(nome: str):
    """PEP 562: `rede.NoRedirect` (and `from simplicio_video.rede import NoRedirect`) builds the class on first access."""
    if nome == "NoRedirect":
        return _no_redirect()
    raise AttributeError(f"module {__name__!r} has no attribute {nome!r}")


def __dir__() -> list[str]:
    return sorted({*globals(), "NoRedirect"})


def request(method: str, url: str, headers: dict | None = None, json_body: dict | None = None, timeout: float = 60,
            form: dict | None = None, follow_redirects: bool = True, max_bytes: int | None = None) -> Response:
    """`follow_redirects=False` returns the 3xx as a Response; `max_bytes` turns an oversized body into a NetworkError."""
    if offline():
        raise NetworkError("SIMPLICIO_OFFLINE=1: rede bloqueada")
    import urllib.error  # here and not at the top: see the module docstring (the refusal above loads none of it)
    import urllib.parse
    import urllib.request
    data = None
    hdrs = dict(headers or {})
    if json_body is not None:
        data = json.dumps(json_body).encode("utf8")
        hdrs.setdefault("Content-Type", "application/json")
    elif form is not None:  # application/x-www-form-urlencoded (OAuth2 token endpoints)
        data = urllib.parse.urlencode(form).encode("utf8")
        hdrs.setdefault("Content-Type", "application/x-www-form-urlencoded")
    req = urllib.request.Request(url, data=data, method=method, headers=hdrs)
    opener = urllib.request.build_opener(_no_redirect()) if not follow_redirects else None
    try:
        with (opener.open(req, timeout=timeout) if opener else urllib.request.urlopen(req, timeout=timeout)) as r:  # noqa: S310 (URLs chosen by the callers)
            body = r.read() if max_bytes is None else r.read(max_bytes + 1)
            if max_bytes is not None and len(body) > max_bytes:
                raise NetworkError(f"resposta acima de {max_bytes} bytes")
            return Response(r.status, body, _lower(r.headers))
    except urllib.error.HTTPError as e:
        err = (e.read() if max_bytes is None else e.read(max_bytes)) if hasattr(e, "read") else b""
        return Response(e.code, err, _lower(getattr(e, "headers", None)))
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise NetworkError(f"falha de rede: {type(e).__name__}") from None
