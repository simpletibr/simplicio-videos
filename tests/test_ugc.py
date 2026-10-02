import json
from pathlib import Path

import pytest

from conftest import ROOT, run_cli
from simplicio_video import ugc

GOLDEN = (ROOT / "tests" / "fixtures" / "ugc" / "notion-prompts.txt").read_text(encoding="utf8").strip().split("\n\n")


def test_pack_is_valid_and_has_ten_characters():
    pack = ugc.load_pack()
    assert len(pack["personagens"]) == 10 == len(GOLDEN)


def test_prompts_match_the_source_pack_byte_for_byte():
    pack = ugc.load_pack()
    got = [ugc.build_prompt(c, "[app name]")["prompt"] for c in pack["personagens"]]
    assert got == GOLDEN


def test_example_lines_are_inside_the_word_band():
    for c in ugc.load_pack()["personagens"]:
        assert ugc.build_prompt(c, "X")["avisos"] == [], c["id"]


def test_word_range_is_22_to_28_for_7_seconds():
    assert ugc.word_range(7) == (22, 28)
    assert ugc.word_range(5) == (16, 20)


@pytest.mark.parametrize("fala,warn", [("one two three", "encarando"), (" ".join(["w"] * 40), "apressada")])
def test_fala_outside_band_warns(fala, warn):
    c = ugc.find(ugc.load_pack(), "gym-girl")
    r = ugc.build_prompt(c, "Appz", fala=fala)
    assert len(r["avisos"]) == 1 and warn in r["avisos"][0]
    assert 'says exactly: "' + fala + '"' in r["prompt"] and "phone with Appz open" in r["prompt"]


@pytest.mark.parametrize("kw", [dict(app="  "), dict(app="A", fala="diz \"oi\""), dict(app="A", fala=" "), dict(app="A", duration_s=0)])
def test_bad_input_is_rejected(kw):
    with pytest.raises(ugc.UgcError):
        ugc.build_prompt(ugc.find(ugc.load_pack(), "gym-guy"), **kw)


def test_unknown_character_lists_ids():
    with pytest.raises(ugc.UgcError, match="gym-girl"):
        ugc.find(ugc.load_pack(), "nope")


def test_duplicate_ids_are_rejected(tmp_path):
    pack = json.loads((ROOT / ugc.PACK_REL).read_text(encoding="utf8"))
    pack["personagens"].append(dict(pack["personagens"][0]))
    (tmp_path / "ugc").mkdir()
    (tmp_path / ugc.PACK_REL).write_text(json.dumps(pack), encoding="utf8")
    (tmp_path / ugc.SCHEMA_REL).write_text((ROOT / ugc.SCHEMA_REL).read_text(encoding="utf8"), encoding="utf8")
    with pytest.raises(ugc.UgcError, match="duplicados"):
        ugc.load_pack(tmp_path)


def test_cli_list_json():
    r = run_cli("ugc", "list", "--json")
    assert r.returncode == 0, r.stderr
    rows = json.loads(r.stdout)
    assert len(rows) == 10 and {"id", "nome", "entrega", "palavras"} <= set(rows[0])


def test_cli_prompt_single_prints_only_the_prompt():
    r = run_cli("ugc", "prompt", "gym-guy", "--app", "FitApp")
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == ugc.build_prompt(ugc.find(ugc.load_pack(), "gym-guy"), "FitApp")["prompt"]


def test_cli_prompt_todos_json():
    r = run_cli("ugc", "prompt", "--todos", "--app", "FitApp", "--json")
    assert r.returncode == 0, r.stderr
    rows = json.loads(r.stdout)
    assert len(rows) == 10 and all("FitApp" in x["prompt"] for x in rows)


@pytest.mark.parametrize("args", [
    ["prompt", "--app", "A"],
    ["prompt", "gym-guy", "--todos", "--app", "A"],
    ["prompt", "--todos", "--app", "A", "--fala", "x"],
    ["prompt", "nope", "--app", "A"],
])
def test_cli_prompt_usage_errors(args):
    r = run_cli("ugc", *args)
    assert r.returncode == 2 and r.stderr.strip()
