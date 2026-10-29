"""Validation of queue message bodies against CONTRACT section 4."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any, TypeGuard

TIER = "768p"
MAX_DURATION_S = 30
FPS = 24
MAX_CHARACTERS = 3
ALLOWED_IMAGE_EXTS = frozenset({".png", ".jpg", ".webp"})
DESCRIPTION_MIN = 3
DESCRIPTION_MAX = 200
_JOB_ID_RE = re.compile(r"[A-Za-z0-9-]{1,64}")


class InvalidJob(ValueError):
    """The queue message body breaks the contract."""


@dataclass(frozen=True)
class Character:
    image_key: str
    image_ext: str
    replace_description: str


@dataclass(frozen=True)
class Job:
    job_id: str
    user_id: str
    created_at: str
    tier: str
    duration_s: int
    fps: int
    source_key: str
    characters: tuple[Character, ...]
    prompt_extra: str | None
    seed: int | None


def is_valid_job_id(value: object) -> bool:
    return isinstance(value, str) and _JOB_ID_RE.fullmatch(value) is not None


def parse_job(body: object) -> Job:
    if not isinstance(body, dict):
        raise InvalidJob("body must be a JSON object")

    job_id = _text(body, "job_id")
    if not is_valid_job_id(job_id):
        raise InvalidJob("job_id must be 1-64 characters of letters, digits or '-'")
    user_id = _text(body, "user_id")
    created_at = _text(body, "created_at")

    if body.get("tier") != TIER:
        raise InvalidJob(f"tier must be {TIER!r}")

    duration_s = _integer(body, "duration_s")
    if not 1 <= duration_s <= MAX_DURATION_S:
        raise InvalidJob(f"duration_s must be 1..{MAX_DURATION_S}")

    fps = _integer(body, "fps")
    if fps != FPS:
        raise InvalidJob(f"fps must be {FPS}")

    source_key = _text(body, "source_key")
    if source_key != f"uploads/{job_id}/source.mp4":
        raise InvalidJob("source_key must be uploads/<job_id>/source.mp4")

    raw_characters = body.get("characters")
    if not isinstance(raw_characters, list) or not 1 <= len(raw_characters) <= MAX_CHARACTERS:
        raise InvalidJob(f"characters must be a list of 1..{MAX_CHARACTERS} items")
    characters = tuple(_character(job_id, raw) for raw in raw_characters)

    prompt_extra = body.get("prompt_extra")
    if prompt_extra is not None and not isinstance(prompt_extra, str):
        raise InvalidJob("prompt_extra must be a string or null")

    seed = body.get("seed")
    if seed is not None and not _is_int(seed):
        raise InvalidJob("seed must be an integer or null")

    return Job(
        job_id=job_id,
        user_id=user_id,
        created_at=created_at,
        tier=TIER,
        duration_s=duration_s,
        fps=fps,
        source_key=source_key,
        characters=characters,
        prompt_extra=prompt_extra,
        seed=seed,
    )


def _character(job_id: str, raw: object) -> Character:
    if not isinstance(raw, dict):
        raise InvalidJob("each character must be an object")
    image_key = _text(raw, "image_key")
    prefix = f"uploads/{job_id}/"
    name = image_key[len(prefix):] if image_key.startswith(prefix) else ""
    if not name or "/" in name:
        raise InvalidJob("image_key must be uploads/<job_id>/<file>")
    extension = os.path.splitext(name)[1].lower()
    if extension not in ALLOWED_IMAGE_EXTS:
        raise InvalidJob("character images must be .png, .jpg or .webp")
    description = _text(raw, "replace_description").strip()
    if not DESCRIPTION_MIN <= len(description) <= DESCRIPTION_MAX:
        raise InvalidJob(f"replace_description must be {DESCRIPTION_MIN}..{DESCRIPTION_MAX} characters")
    return Character(image_key=image_key, image_ext=extension, replace_description=description)


def _text(body: dict[str, Any], key: str) -> str:
    value = body.get(key)
    if not isinstance(value, str) or not value.strip():
        raise InvalidJob(f"{key} must be a non-empty string")
    return value


def _integer(body: dict[str, Any], key: str) -> int:
    value = body.get(key)
    if not _is_int(value):
        raise InvalidJob(f"{key} must be an integer")
    return int(value)


def _is_int(value: object) -> TypeGuard[int]:
    return isinstance(value, int) and not isinstance(value, bool)
