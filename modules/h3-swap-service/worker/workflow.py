"""Workflow patching, prompt text and frame arithmetic (CONTRACT section 7).

The user's ComfyUI workflow (API format) is the template. The map says which node
input each job value goes into. apply_workflow never mutates its arguments.
"""

from __future__ import annotations

import copy
import math
import random
from collections.abc import Mapping, Sequence
from typing import Any

MAX_FRAMES_PER_CLIP = 362
CLIP_SECONDS = 15
FRAME_GRID_STEP = 17
FRAME_GRID_OFFSET = 5
SEED_MAX = 2**31 - 1
_PROMPT_SUFFIX = " Keep the original motion, camera, background and audio."

Slot = tuple[str, str]


class WorkflowError(ValueError):
    """The template and map cannot be applied to this job."""


def build_prompt(characters: Sequence[Mapping[str, Any]], prompt_extra: str | None) -> str:
    if not characters:
        raise ValueError("at least one character is required to build a prompt")
    parts = [
        f"Replace {character['replace_description']} in <Video 1> with the person from <Picture {index}>."
        for index, character in enumerate(characters, start=1)
    ]
    text = " ".join(parts) + _PROMPT_SUFFIX
    extra = (prompt_extra or "").strip()
    if extra:
        text += f" {extra}"
    return text


def frames_for_duration(seconds: int, fps: int = 24) -> int:
    """Smallest 17k+5 frame count covering `seconds * fps`, capped at 362 per clip."""
    if seconds < 1 or fps < 1:
        raise ValueError("seconds and fps must be at least 1")
    target = seconds * fps
    steps = max(0, math.ceil((target - FRAME_GRID_OFFSET) / FRAME_GRID_STEP))
    frames = FRAME_GRID_STEP * steps + FRAME_GRID_OFFSET
    return min(frames, MAX_FRAMES_PER_CLIP)


def chunk_count(seconds: int) -> int:
    if seconds < 1:
        raise ValueError("seconds must be at least 1")
    return math.ceil(seconds / CLIP_SECONDS)


def output_spec(mapping: Mapping[str, Any]) -> tuple[str, str]:
    """Return (node id, output kind) from the map's `output` entry."""
    output = mapping.get("output")
    if not isinstance(output, Mapping) or output.get("node") is None or not output.get("kind"):
        raise WorkflowError("map must define output.node and output.kind")
    return str(output["node"]), str(output["kind"])


def apply_workflow(
    template: dict[str, Any],
    mapping: dict[str, Any],
    *,
    source_video: str,
    character_images: list[str],
    prompt: str,
    seed: int | None,
    length_frames: int | None,
    chunk_count: int | None,
) -> dict[str, Any]:
    """Return a patched deep copy of `template`.

    Required map entries: inputs.source_video, inputs.character_images,
    inputs.prompt, output. Optional entries (seed, length_frames, chunk_count) are
    skipped when absent from the map or when the value is None. A None seed is
    replaced by a random integer when the map has a seed slot.
    """
    inputs = mapping.get("inputs")
    if not isinstance(inputs, Mapping):
        raise WorkflowError("map must define inputs")
    output_spec(mapping)

    source_slot = _required_slot(inputs, "source_video")
    prompt_slot = _required_slot(inputs, "prompt")
    image_slots = _image_slots(inputs)

    if not character_images:
        raise WorkflowError("at least one character image is required")
    if len(character_images) > len(image_slots):
        raise WorkflowError(
            f"{len(character_images)} character images but the map has {len(image_slots)} slots"
        )

    result = copy.deepcopy(template)
    _write(result, source_slot, source_video)
    _write(result, prompt_slot, prompt)
    for slot, image in zip(image_slots, character_images):
        _write(result, slot, image)

    seed_slot = _optional_slot(inputs, "seed")
    if seed_slot is not None:
        value = seed if seed is not None else random.randint(0, SEED_MAX)
        _write(result, seed_slot, value)

    length_slot = _optional_slot(inputs, "length_frames")
    if length_slot is not None and length_frames is not None:
        _write(result, length_slot, length_frames)

    chunk_slot = _optional_slot(inputs, "chunk_count")
    if chunk_slot is not None and chunk_count is not None:
        _write(result, chunk_slot, chunk_count)

    return result


def _required_slot(inputs: Mapping[str, Any], name: str) -> Slot:
    spec = inputs.get(name)
    if spec is None:
        raise WorkflowError(f"map inputs.{name} is required")
    return _parse_slot(spec, f"inputs.{name}")


def _optional_slot(inputs: Mapping[str, Any], name: str) -> Slot | None:
    spec = inputs.get(name)
    if spec is None:
        return None
    return _parse_slot(spec, f"inputs.{name}")


def _image_slots(inputs: Mapping[str, Any]) -> list[Slot]:
    specs = inputs.get("character_images")
    if not isinstance(specs, list) or not specs:
        raise WorkflowError("map inputs.character_images must be a non-empty list")
    return [_parse_slot(spec, f"inputs.character_images[{index}]") for index, spec in enumerate(specs)]


def _parse_slot(spec: Any, label: str) -> Slot:
    if not isinstance(spec, Mapping) or "node" not in spec or "field" not in spec:
        raise WorkflowError(f"{label} must have 'node' and 'field'")
    return str(spec["node"]), str(spec["field"])


def _write(workflow: dict[str, Any], slot: Slot, value: Any) -> None:
    node_id, field_name = slot
    node = workflow.get(node_id)
    if not isinstance(node, dict) or not isinstance(node.get("inputs"), dict):
        raise WorkflowError(f"template has no node {node_id} with inputs")
    node["inputs"][field_name] = value
