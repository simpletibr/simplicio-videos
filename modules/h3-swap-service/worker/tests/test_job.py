from __future__ import annotations

from typing import Any

import pytest

from worker.job import InvalidJob, is_valid_job_id, parse_job
from worker.tests.fixtures import JOB_ID, valid_body


def _char(**overrides: Any) -> dict[str, Any]:
    char: dict[str, Any] = {"image_key": f"uploads/{JOB_ID}/char1.png", "replace_description": "the man"}
    char.update(overrides)
    return char


def test_parse_valid_job_maps_contract_fields() -> None:
    job = parse_job(valid_body())
    assert job.job_id == JOB_ID
    assert job.user_id == "user-1"
    assert job.tier == "768p"
    assert job.duration_s == 10
    assert job.fps == 24
    assert job.source_key == f"uploads/{JOB_ID}/source.mp4"
    assert len(job.characters) == 1
    char = job.characters[0]
    assert char.image_key == f"uploads/{JOB_ID}/char1.png"
    assert char.image_ext == ".png"
    assert char.replace_description == "o homem de boné, à esquerda"
    assert job.prompt_extra is None
    assert job.seed is None


def test_parse_accepts_three_characters_with_all_allowed_extensions() -> None:
    chars = [
        {"image_key": f"uploads/{JOB_ID}/char1.png", "replace_description": "person one"},
        {"image_key": f"uploads/{JOB_ID}/char2.JPG", "replace_description": "person two"},
        {"image_key": f"uploads/{JOB_ID}/char3.webp", "replace_description": "person three"},
    ]
    job = parse_job(valid_body(characters=chars, prompt_extra="warm light", seed=42))
    assert [c.image_ext for c in job.characters] == [".png", ".jpg", ".webp"]
    assert job.seed == 42
    assert job.prompt_extra == "warm light"


def test_parse_strips_description_whitespace() -> None:
    job = parse_job(valid_body(characters=[_char(replace_description="  the man  ")]))
    assert job.characters[0].replace_description == "the man"


def test_parse_accepts_description_length_boundaries() -> None:
    assert parse_job(valid_body(characters=[_char(replace_description="abc")]))
    assert parse_job(valid_body(characters=[_char(replace_description="x" * 200)]))


@pytest.mark.parametrize(
    "overrides",
    [
        {"duration_s": 0},
        {"duration_s": 31},
        {"duration_s": "10"},
        {"duration_s": True},
        {"duration_s": 10.0},
        {"tier": "1080p"},
        {"fps": 30},
        {"source_key": f"uploads/{JOB_ID}/other.mp4"},
        {"source_key": "uploads/other-job/source.mp4"},
        {"characters": []},
        {"characters": "char1"},
        {"seed": "abc"},
        {"seed": True},
        {"prompt_extra": 5},
        {"user_id": ""},
        {"created_at": None},
    ],
)
def test_parse_rejects_invalid_top_level_fields(overrides: dict[str, Any]) -> None:
    with pytest.raises(InvalidJob):
        parse_job(valid_body(**overrides))


@pytest.mark.parametrize(
    "char",
    [
        _char(image_key=f"uploads/{JOB_ID}/char1.gif"),
        _char(image_key="uploads/other-job/char1.png"),
        _char(image_key=f"uploads/{JOB_ID}/sub/char1.png"),
        _char(image_key=f"uploads/{JOB_ID}/char1"),
        _char(replace_description="ab"),
        _char(replace_description="x" * 201),
        _char(replace_description="   "),
        "not-a-dict",
    ],
)
def test_parse_rejects_invalid_character(char: Any) -> None:
    with pytest.raises(InvalidJob):
        parse_job(valid_body(characters=[char]))


def test_parse_rejects_more_than_three_characters() -> None:
    chars = [_char(image_key=f"uploads/{JOB_ID}/char{i}.png") for i in range(1, 5)]
    with pytest.raises(InvalidJob):
        parse_job(valid_body(characters=chars))


@pytest.mark.parametrize("job_id", ["", "a/b", "../etc", "x" * 65, "has space"])
def test_parse_rejects_unsafe_job_id(job_id: str) -> None:
    with pytest.raises(InvalidJob, match="job_id"):
        parse_job(valid_body(job_id=job_id))


def test_parse_rejects_non_object_body() -> None:
    with pytest.raises(InvalidJob):
        parse_job(["not", "an", "object"])


def test_parse_rejects_missing_field() -> None:
    body = valid_body()
    del body["tier"]
    with pytest.raises(InvalidJob):
        parse_job(body)


def test_is_valid_job_id() -> None:
    assert is_valid_job_id(JOB_ID) is True
    assert is_valid_job_id("") is False
    assert is_valid_job_id("a/b") is False
    assert is_valid_job_id("abc\n") is False
    assert is_valid_job_id(None) is False
    assert is_valid_job_id(5) is False
