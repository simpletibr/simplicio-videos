"""One redactor for every secret the engine could echo: the values of the credentials in the environment and anything shaped like a key,
hidden in logs, errors, manifests, job files and third-party text.

Before this module five functions did the same job with lists of their own (busca, openverse, swap, jobs and the key detector of social), and
a format that one knew the others let through. Now there is one rule, the UNION of what each of them hid, and every module calls it under
the name it always had (`busca.scrub`, `openverse.scrub`, `swap.scrub`, `jobs._scrub`, `swap_providers.base.redact` are this `scrub`).

WHAT IT HIDES. (1) The VALUE of an environment variable that holds a credential: a variable of `KNOWN_ENV` (the swap providers, TinyFish, ElevenLabs,
xAI, Openverse) from `MIN_KNOWN` = 6 characters, one whose name has KEY, SECRET, TOKEN, PASSWORD or PASSWD as a whole `_`-separated word
(GITHUB_TOKEN; PIP_KEYRING_PROVIDER is not one) and a proxy URL that carries `user:password@` from `MIN_GENERIC` = 8, plus what a module
`register`s (the OAuth token that Openverse keeps in memory). Each variable gets the lowest limit any of the old functions gave it, and a longer value
goes before a shorter one that is part of it, so no tail of a key is left in the open. (2) Text SHAPED like a key: the three regexes the old redactors
had (busca's, openverse's and swap's `KEY_PATTERN`, `SHAPES`), and the rule is the UNION of what they match. Where two of them knew the same
format the match of either is hidden, so the limit is the lowest of the two (`AIza` + 8, `sk-` + 8, `Bearer` + 16 letters or + 8 with a digit...) and the
guard the weakest. Every shape but two needs a non-word character before it (the lookbehind of busca and openverse), so `task-based-workflow-x`, which
contains `sk-based-workflow-x`, is a phrase and not a key. The two that do not are the Google shapes swap hid, `AIzaSy` + 25 and `AQ.` + 30: they are
long enough not to be a word, and a key glued to a word (`key_AIzaSy...`) stays hidden. A private key header is hidden in any case. Why three regexes
and not one with all the alternatives: one regex consumes from left to right, and a key that starts inside the stretch another one took (a `Bearer`
inside the token of an earlier `Bearer`) would be left in the open; each rule run on its own hides what it hid, and `shape_spans` merges the stretches.

WHO CALLS WHAT. `scrub(text, values=None)` hides (1) and then (2) (a loop that cleans line after line passes `secret_values()`, asked once);
`has_secret(text)` says whether there is anything to hide, for the places that refuse instead of hiding (a TinyFish query, the arguments of a
background task); `secret_values()` and `mask_values()` are the two halves of (1), for the places that keep the list or the order of their own, and
`shape_spans()` is (2) as stretches. A module that keeps a secret in memory calls `register`.

Standard library plus `terceiros` (a leaf): the swap adapters, busca, openverse and jobs import this module, so it imports none of them. `social` does
not: its guard (tests/social_guard.py) lets it import only `paths` and `fsutil`, so it carries a copy of `SECRET_RE` and the golden test keeps the
two patterns equal.
"""
from __future__ import annotations

import os
import re
from collections.abc import Callable, Iterable

from . import terceiros

__all__ = ["MASK", "KNOWN_ENV", "PROXY_ENV", "MIN_KNOWN", "MIN_GENERIC", "SHAPES", "SECRET_RE", "scrub", "has_secret", "secret_values", "mask_values",
           "shape_spans", "register", "unregister"]

MASK = "***"

# ---------------------------------------------------------------------------------------------------------------- shapes

# The three regexes of the old redactors, each as it was (openverse's capturing group made non-capturing). Run one by one, never as one regex with
# all the alternatives: see the docstring.
#
# swap_providers/base.py (`KEY_PATTERN`): the Google API key and the OAuth-style token (it has `.`, and stops only at a character outside the class).
# No lookbehind: they are the keys that spend money, and 31 and 33 characters are not a word.
_GOOGLE = r"AIzaSy[A-Za-z0-9_-]{25,}|AQ\.[A-Za-z0-9_.-]{30,}"

# busca: every format needs a non-word character before it. A prefix with a provider length (hf_ and npm_ + 30, glpat- + 20, Stripe sk_/rk_ + 16):
# `npm_lifecycle_event` and `hf_model_name` are words, not tokens. A bearer value needs a digit or 20+ characters, so `bearer authentication` is a
# phrase. A private key header is hidden in any case and in any position.
_BUSCA = (r"(?<![A-Za-z0-9_])(?:AIza[0-9A-Za-z_-]{8,}|AQ\.[A-Za-z0-9_-]{8,}|sk-[A-Za-z0-9_-]{8,}|gh[pousr]_[A-Za-z0-9]{8,}|"
          r"github_pat_[A-Za-z0-9_]{20,}|xox[a-z]-[A-Za-z0-9-]{8,}|eyJ[A-Za-z0-9_-]{10,}|ya29\.[A-Za-z0-9_-]{10,}|AKIA[0-9A-Z]{16}|"
          r"[sr]k_(?:live|test)_[A-Za-z0-9]{16,}|hf_[A-Za-z0-9]{30,}|npm_[A-Za-z0-9]{30,}|glpat-[A-Za-z0-9_-]{20,}|"
          r"(?i:bearer)\s+(?:(?=[A-Za-z0-9._~+/=-]{20})|(?=[A-Za-z._~+/=-]*[0-9]))[A-Za-z0-9._~+/=-]{8,})|"
          r"(?i:-----BEGIN [A-Z ]*PRIVATE KEY-----)")

# openverse (and social, without the lookbehind): the same guard, longer limits, and the one format busca let through, `Bearer` + 16 letters.
_OPENVERSE = (r"(?<![A-Za-z0-9_])(?:sk-[A-Za-z0-9_-]{8,}|AIza[0-9A-Za-z_-]{16,}|gh[pousr]_[A-Za-z0-9]{16,}|xox[a-z]-[A-Za-z0-9-]{8,}|"
              r"eyJ[A-Za-z0-9_-]{10,}|ya29\.[A-Za-z0-9_-]{10,}|AQ\.[A-Za-z0-9_-]{10,}|Bearer\s+[A-Za-z0-9._-]{16,})")

SHAPES = tuple(re.compile(p) for p in (_GOOGLE, _BUSCA, _OPENVERSE))
# Only for `search` (is there anything to hide): `search` finds a match if any alternative does, whatever was consumed before. `social` carries a copy of
# this text (it may import only paths and fsutil).
SECRET_RE = re.compile("|".join((_GOOGLE, _BUSCA, _OPENVERSE)))


def shape_spans(text: str) -> list[tuple[int, int]]:
    """The stretches of `text` that any of the three rules of SHAPES matches, the ones that overlap merged (the same key found by two rules is one
    stretch). A stretch is a half-open `(start, end)`, in order."""
    stretches: list[list[int]] = []
    for start, end in sorted(m.span() for rule in SHAPES for m in rule.finditer(text)):
        if stretches and start < stretches[-1][1]:
            stretches[-1][1] = max(stretches[-1][1], end)
        else:
            stretches.append([start, end])
    return [(start, end) for start, end in stretches]


def _mask_shapes(text: str) -> str:
    spans = shape_spans(text)
    if not spans:
        return text
    pieces, last = [], 0
    for start, end in spans:
        pieces += (text[last:start], MASK)
        last = end
    pieces.append(text[last:])
    return "".join(pieces)


# ---------------------------------------------------------------------------------------------------------------- values

MIN_KNOWN = 6    # a variable that is a credential by its NAME in this list: the old swap, jobs, busca (TinyFish) and openverse limit
MIN_GENERIC = 8  # a variable that looks like one by its name, or a proxy with a password: the old busca limit

# One name per owner, each owner's own constant stays where it is (tests/golden/test_segredos.py keeps them in parity): the adapters of
# swap_providers.REGISTRY, busca.ENV_CHAVE, openverse.ENV_ID and ENV_SECRET, and the two paid voice providers jobs used to add by hand.
KNOWN_ENV = ("GEMINI_API_KEY", "FAL_KEY", "WAVESPEED_API_KEY", "KIE_API_KEY", "DASHSCOPE_API_KEY",
             "TINYFISH_API_KEY", "ELEVENLABS_API_KEY", "XAI_API_KEY", "OPENVERSE_CLIENT_ID", "OPENVERSE_CLIENT_SECRET")
_NAME_RE = re.compile(r"(?i)(?:^|_)(?:KEY|SECRET|TOKEN|PASSWORD|PASSWD)(?:_|$)")
# The proxy variables whose value may carry a password: all but NO_PROXY (a list of hosts). busca.ENV_PROXY is the same six names.
PROXY_ENV = tuple(n for n in terceiros.PROXIES if n.upper() != "NO_PROXY")
_USERINFO_RE = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*://[^/?#\s]*@")

# Secrets that live in memory, not in a variable (the Openverse OAuth token): a module hands over a function that returns them NOW, so what it
# keeps can be replaced between two calls.
_SOURCES: dict[str, Callable[[], Iterable[object]]] = {}


def register(name: str, source: Callable[[], Iterable[object]]) -> None:
    """Add a source of secret values under `name` (the same name replaces the earlier source). `source()` runs at each call and returns the
    values to hide now; anything that is empty or shorter than MIN_KNOWN is ignored."""
    _SOURCES[name] = source


def unregister(name: str) -> None:
    _SOURCES.pop(name, None)


def secret_values() -> list[str]:
    """The values to hide right now, the longest first: the credentials of the environment (see the module docstring) and the registered sources."""
    found: set[str] = set()
    for name, raw in os.environ.items():
        value = raw.strip()
        if name in KNOWN_ENV:
            minimum = MIN_KNOWN
        elif _NAME_RE.search(name) or (name in PROXY_ENV and _USERINFO_RE.match(value)):
            minimum = MIN_GENERIC
        else:
            continue
        if len(value) >= minimum:
            found.add(value)
    for source in tuple(_SOURCES.values()):
        try:
            values = list(source())
        except Exception:  # noqa: BLE001 (a broken source must not turn an error message into a second error: the rest is still hidden)
            continue
        found.update(v for v in (str(raw or "").strip() for raw in values) if len(v) >= MIN_KNOWN)
    return sorted(found, key=lambda v: (-len(v), v))


def mask_values(text: str, values: Iterable[str] | None = None) -> str:
    """`text` with each of `values` (default: `secret_values()`) replaced by MASK, the longest first and never the empty string."""
    for value in sorted({v for v in (secret_values() if values is None else values) if v}, key=lambda v: (-len(v), v)):
        text = text.replace(value, MASK)
    return text


def scrub(text: str, values: Iterable[str] | None = None) -> str:
    """Hide the credentials of the environment (`values`, by default `secret_values()`), then anything shaped like a key. A loop that cleans line
    after line asks for `secret_values()` once and passes it: reading the environment at each line costs far more than the cleaning."""
    return _mask_shapes(mask_values(text, values))


def has_secret(text: str) -> bool:
    """Whether `scrub` would hide anything in `text`: a shape of a key or a credential of the environment."""
    return SECRET_RE.search(text) is not None or any(v in text for v in secret_values())
