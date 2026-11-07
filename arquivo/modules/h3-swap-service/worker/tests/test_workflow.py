from __future__ import annotations

import copy
from typing import Any

import pytest

from worker import workflow
from worker.tests.fixtures import MAP, TEMPLATE
from worker.workflow import (
    WorkflowError,
    apply_workflow,
    build_prompt,
    chunk_count,
    frames_for_duration,
    output_spec,
)

SUFFIX = " Keep the original motion, camera, background and audio."


def _apply(**overrides: Any) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "source_video": "job_source.mp4",
        "character_images": ["job_char1.png", "job_char2.png", "job_char3.png"],
        "prompt": "a prompt",
        "seed": 7,
        "length_frames": 243,
        "chunk_count": 1,
    }
    kwargs.update(overrides)
    return apply_workflow(TEMPLATE, MAP, **kwargs)


def test_build_prompt_single_character_without_extra() -> None:
    text = build_prompt([{"replace_description": "o homem de boné, à esquerda"}], None)
    assert text == (
        "Replace o homem de boné, à esquerda in <Video 1> with the person from <Picture 1>." + SUFFIX
    )


def test_build_prompt_numbers_pictures_and_appends_extra() -> None:
    text = build_prompt(
        [{"replace_description": "the man in red"}, {"replace_description": "the woman on the left"}],
        "Make it cinematic.",
    )
    assert text == (
        "Replace the man in red in <Video 1> with the person from <Picture 1>. "
        "Replace the woman on the left in <Video 1> with the person from <Picture 2>."
        + SUFFIX
        + " Make it cinematic."
    )


@pytest.mark.parametrize("extra", ["", "   ", None])
def test_build_prompt_ignores_blank_extra(extra: str | None) -> None:
    text = build_prompt([{"replace_description": "the man"}], extra)
    assert text.endswith(SUFFIX)


def test_build_prompt_strips_extra_whitespace() -> None:
    text = build_prompt([{"replace_description": "the man"}], "  wide shot  ")
    assert text.endswith(SUFFIX + " wide shot")


def test_build_prompt_requires_at_least_one_character() -> None:
    with pytest.raises(ValueError):
        build_prompt([], None)


@pytest.mark.parametrize("seconds, expected", [(1, 39), (10, 243), (15, 362), (30, 362)])
def test_frames_for_duration_matches_expected_grid_values(seconds: int, expected: int) -> None:
    assert frames_for_duration(seconds) == expected


def test_frames_for_duration_always_lands_on_17k_plus_5_grid_within_cap() -> None:
    for seconds in range(1, 31):
        frames = frames_for_duration(seconds)
        assert frames <= 362
        assert (frames - 5) % 17 == 0


def test_frames_for_duration_covers_the_target_when_under_cap() -> None:
    for seconds in range(1, 16):
        assert frames_for_duration(seconds) >= seconds * 24


def test_frames_for_duration_honours_fps() -> None:
    assert frames_for_duration(10, fps=30) == 311


def test_frames_for_duration_rejects_non_positive_input() -> None:
    with pytest.raises(ValueError):
        frames_for_duration(0)


@pytest.mark.parametrize("seconds, expected", [(1, 1), (10, 1), (15, 1), (16, 2), (30, 2)])
def test_chunk_count_is_ceil_of_seconds_over_15(seconds: int, expected: int) -> None:
    assert chunk_count(seconds) == expected


def test_chunk_count_rejects_non_positive_input() -> None:
    with pytest.raises(ValueError):
        chunk_count(0)


def test_output_spec_returns_node_and_kind() -> None:
    assert output_spec(MAP) == ("90", "videos")


def test_output_spec_without_output_raises() -> None:
    with pytest.raises(WorkflowError):
        output_spec({"inputs": {}})


def test_apply_sets_every_mapped_input() -> None:
    out = _apply()
    assert out["12"]["inputs"]["video"] == "job_source.mp4"
    assert out["20"]["inputs"]["image"] == "job_char1.png"
    assert out["21"]["inputs"]["image"] == "job_char2.png"
    assert out["22"]["inputs"]["image"] == "job_char3.png"
    assert out["30"]["inputs"]["text"] == "a prompt"
    assert out["40"]["inputs"]["seed"] == 7
    assert out["41"]["inputs"]["length"] == 243
    assert out["42"]["inputs"]["chunks"] == 1


def test_apply_returns_new_dict_and_never_mutates_template_or_map() -> None:
    template_before = copy.deepcopy(TEMPLATE)
    map_before = copy.deepcopy(MAP)
    out = apply_workflow(
        TEMPLATE,
        MAP,
        source_video="s.mp4",
        character_images=["c.png"],
        prompt="p",
        seed=1,
        length_frames=39,
        chunk_count=1,
    )
    assert out is not TEMPLATE
    assert TEMPLATE == template_before
    assert MAP == map_before
    out["12"]["inputs"]["video"] = "changed"
    assert TEMPLATE == template_before


def test_apply_with_fewer_images_leaves_unused_slots_untouched() -> None:
    out = _apply(character_images=["job_char1.png"])
    assert out["20"]["inputs"]["image"] == "job_char1.png"
    assert out["21"]["inputs"]["image"] == "ph2.png"
    assert out["22"]["inputs"]["image"] == "ph3.png"


def test_apply_with_more_images_than_slots_raises() -> None:
    with pytest.raises(WorkflowError):
        _apply(character_images=["a.png", "b.png", "c.png", "d.png"])


def test_apply_requires_at_least_one_character_image() -> None:
    with pytest.raises(WorkflowError):
        _apply(character_images=[])


def test_apply_draws_random_seed_in_range_when_seed_is_none(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[int, int]] = []

    def fake_randint(low: int, high: int) -> int:
        calls.append((low, high))
        return 123456

    monkeypatch.setattr(workflow.random, "randint", fake_randint)
    out = _apply(seed=None)
    assert out["40"]["inputs"]["seed"] == 123456
    assert calls == [(0, 2**31 - 1)]


def test_apply_uses_explicit_seed() -> None:
    assert _apply(seed=99)["40"]["inputs"]["seed"] == 99


def test_apply_skips_optional_keys_missing_from_map() -> None:
    mapping = copy.deepcopy(MAP)
    del mapping["inputs"]["length_frames"]
    del mapping["inputs"]["chunk_count"]
    del mapping["inputs"]["seed"]
    out = apply_workflow(
        TEMPLATE,
        mapping,
        source_video="s.mp4",
        character_images=["c.png"],
        prompt="p",
        seed=5,
        length_frames=243,
        chunk_count=1,
    )
    assert out["41"]["inputs"]["length"] == 0
    assert out["42"]["inputs"]["chunks"] == 0
    assert out["40"]["inputs"]["seed"] == 1


def test_apply_skips_none_length_and_chunk_values() -> None:
    out = _apply(length_frames=None, chunk_count=None)
    assert out["41"]["inputs"]["length"] == 0
    assert out["42"]["inputs"]["chunks"] == 0


@pytest.mark.parametrize("missing", ["source_video", "character_images", "prompt", "output"])
def test_apply_missing_required_map_key_raises(missing: str) -> None:
    mapping = copy.deepcopy(MAP)
    if missing == "output":
        del mapping["output"]
    else:
        del mapping["inputs"][missing]
    with pytest.raises(WorkflowError):
        apply_workflow(
            TEMPLATE,
            mapping,
            source_video="s.mp4",
            character_images=["c.png"],
            prompt="p",
            seed=1,
            length_frames=39,
            chunk_count=1,
        )


def test_apply_unknown_node_id_raises() -> None:
    mapping = copy.deepcopy(MAP)
    mapping["inputs"]["prompt"] = {"node": "999", "field": "text"}
    with pytest.raises(WorkflowError):
        apply_workflow(
            TEMPLATE,
            mapping,
            source_video="s.mp4",
            character_images=["c.png"],
            prompt="p",
            seed=1,
            length_frames=39,
            chunk_count=1,
        )
