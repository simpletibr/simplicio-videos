"""Shared test data for the worker tests. Not a test module."""

from __future__ import annotations

import base64
import json
from typing import Any

JOB_ID = "11111111-2222-4333-8444-555555555555"

TEMPLATE: dict[str, Any] = {
    "12": {"class_type": "LoadVideo", "inputs": {"video": "placeholder.mp4"}},
    "20": {"class_type": "LoadImage", "inputs": {"image": "ph1.png"}},
    "21": {"class_type": "LoadImage", "inputs": {"image": "ph2.png"}},
    "22": {"class_type": "LoadImage", "inputs": {"image": "ph3.png"}},
    "30": {"class_type": "PromptText", "inputs": {"text": "old prompt"}},
    "40": {"class_type": "Sampler", "inputs": {"seed": 1}},
    "41": {"class_type": "Length", "inputs": {"length": 0}},
    "42": {"class_type": "Chunks", "inputs": {"chunks": 0}},
    "90": {"class_type": "SaveVideo", "inputs": {"filename_prefix": "h3"}},
}

MAP: dict[str, Any] = {
    "inputs": {
        "source_video": {"node": "12", "field": "video"},
        "character_images": [
            {"node": "20", "field": "image"},
            {"node": "21", "field": "image"},
            {"node": "22", "field": "image"},
        ],
        "prompt": {"node": "30", "field": "text"},
        "seed": {"node": "40", "field": "seed"},
        "length_frames": {"node": "41", "field": "length"},
        "chunk_count": {"node": "42", "field": "chunks"},
    },
    "output": {"node": "90", "kind": "videos"},
}


def valid_body(**overrides: Any) -> dict[str, Any]:
    """A queue message body that satisfies CONTRACT section 4."""
    body: dict[str, Any] = {
        "job_id": JOB_ID,
        "user_id": "user-1",
        "created_at": "2026-10-17T20:00:00Z",
        "tier": "768p",
        "duration_s": 10,
        "fps": 24,
        "source_key": f"uploads/{JOB_ID}/source.mp4",
        "characters": [
            {
                "image_key": f"uploads/{JOB_ID}/char1.png",
                "replace_description": "o homem de boné, à esquerda",
            }
        ],
        "prompt_extra": None,
        "seed": None,
    }
    body.update(overrides)
    return body


def b64_json(obj: Any) -> str:
    """Encode like Cloudflare does for json-content-type queue bodies."""
    return base64.b64encode(json.dumps(obj, ensure_ascii=False).encode("utf-8")).decode("ascii")
