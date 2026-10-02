"""Layout guard (headless Chrome) for kinetic-words + end-card text fitting + decoration z-order (Wesley 02/10)."""
import re
from pathlib import Path

import pytest

from simplicio_video import kinetic_layout as layout, paths
from simplicio_video import render as R

HOME = paths.home()
BLOCK = HOME / "motion" / "patterns" / "kinetic-words" / "block.html"
FONTS = HOME / "templates" / "internacional-dor" / "composition"
US = {"colors": "#ffffff|#ffffff|#ffe08a", "ink": "#151515", "maxw": 980, "exit": 0.12, "mode": "bounce", "font": "Inter",
      "seed": 12, "stroke": 0, "panel": "#216e64", "panel_alpha": 0.94, "weight": 900, "lead": 0.22, "cy": 900, "y": 200}


def _probe(jobs):
    try:
        layout.tools()
    except layout.LayoutUnavailable as e:
        pytest.skip(str(e))
    return layout.probe(BLOCK, FONTS, jobs)


def _job(i, lines, times, size=112, dur=4.0, **kw):
    return {"id": f"j{i}", "vars": {**US, "lines": lines, "times": times, "size": size, "dur": dur, **kw}, "step": 1 / 30}


CASES = [  # highlight colour (every 3rd word) in the middle, at the end of a line and right after a line break
    ("Pet Joy offers|low-stress grooming|for anxious pets.", "0.1|0.35|0.6|1.0|1.4|2.0|2.3|2.7", ["Pet Joy offers", "low-stress grooming", "for anxious pets."]),
    ("Or tired of|never getting|real answers?", "0.1|0.37|0.84|1.08|1.46|1.82|2.18", ["Or tired of", "never getting", "real answers?"]),
    ("Pet Joy in LA.|Gentle hands, happy tails.", "0.1|0.3|0.5|0.7|1.2|1.6|2.0|2.3", ["Pet Joy in LA.", "Gentle hands, happy tails."]),
    ("Nōvuu enhances|your natural beauty,|never overdone.", "0.1|0.6|1.1|1.4|1.9|2.6|3.0", ["Nōvuu enhances", "your natural beauty,", "never overdone."]),
]


def test_words_never_touch_highlight_middle_end_and_line_break():
    res = _probe([_job(i, l, t) for i, (l, t, _) in enumerate(CASES)])
    for (lines, _, expect), r in zip(CASES, res):
        assert r["text"] == expect  # assembled text per line: every word, single spaces, nothing glued
        assert r["min_gap_em"] >= layout.MIN_GAP_EM, (lines, r["min_gap_at"])
        assert r["out_of_frame_n"] == 0
    assert layout.problems(res) == []


def test_calm_and_stroke_styles_keep_the_gap_too():
    res = _probe([_job(0, CASES[0][0], CASES[0][1], mode="calm", panel="", font="Inter"),
                  _job(1, CASES[1][0], CASES[1][1], stroke=1, panel="", font="Fredoka", weight=0)])
    assert all(r["min_gap_em"] >= layout.MIN_GAP_EM for r in res)


def test_guard_catches_text_leaving_the_frame():
    res = _probe([_job(0, "Hundefriseurtermine Wochenende", "0.1|0.5", size=400, maxw=3000, panel="")])
    probs = layout.problems(res)
    assert probs and "sai da tela" in probs[0]


# ---- end card / note: wraps or shrinks for long languages; never wider than the frame minus the margin ----
FONT = R.preview_font(HOME)


def test_text_width_matches_drawtext_scale():
    w = R.text_width(FONT, "Video von Wesley Simplicio", 34)
    assert 420 < w < 470  # drawtext ink measured 438 px (advance width a bit larger)


@pytest.mark.parametrize("lang", ["pt", "en", "de", "fr"])
def test_end_card_fits_in_every_language(lang):
    P = R.preview_texts(lang)
    maxw = P["width"] - 2 * R.PREVIEW_MARGIN
    for k, size in (("end_title", 34), ("end_url", 44), ("end_note", 20)):
        lines, sz = R.fit_text(FONT, P[k], size, maxw)
        assert all(R.text_width(FONT, x, sz) <= maxw for x in lines), (lang, k, lines, sz)
        assert " ".join(lines) == P[k]


def test_french_title_wraps_in_two_lines(tmp_path):
    lines, sz = R.fit_text(FONT, "Vidéo réalisée par Wesley Simplicio", 34, 460)
    assert lines == ["Vidéo réalisée par", "Wesley Simplicio"] and sz == 34
    fc = R.preview_filter(10.0, FONT, tmp_path, lang="fr")
    assert "end1_0.txt" in fc and "end1_1.txt" in fc
    assert (tmp_path / "end1_1.txt").read_text(encoding="utf8") == "Wesley Simplicio"


def test_fit_text_shrinks_a_single_long_word_and_fails_loudly():
    lines, sz = R.fit_text(FONT, "Vorschauvideoproduktionsgesellschaft", 34, 460)
    assert len(lines) == 1 and sz < 34 and R.text_width(FONT, lines[0], sz) <= 460
    with pytest.raises(SystemExit):
        R.fit_text(FONT, "Vorschauvideoproduktionsgesellschaftsbeauftragter" * 2, 34, 460)


def test_decorations_sit_below_every_text_layer_in_the_intl_template():
    s = (HOME / "templates" / "internacional-dor" / "composition" / "index.template.html").read_text(encoding="utf8")
    track = {m.group(1): int(m.group(2)) for m in re.finditer(r'<div id="([^"]+)"[^>]*data-track-index="(\d+)"', s)}
    for sc in ("s2", "s4"):
        text_layers = [track[f"{sc}-words"], track["s2-main" if sc == "s2" else "s4-lockup"]]
        assert track[f"{sc}-burst"] < min(text_layers)


# ---- sign-off lockup (Wesley 02/10, P076): no empty pill; pill/city follow the real height of the message ----
LOCKUP = HOME / "motion" / "patterns" / "brand-lockup-soft" / "block.html"
LK = {"name": "JASMINE", "sub": "FAHRNI", "tag_y": 880, "chip_y": 1120, "city": "Liebefeld · Bern", "ink": "#1d1d1f",
      "accent": "#7d6a5a", "colors": "#7d6a5a|#e3e3e3", "bg": "transparent", "seed": 4, "dur": 4.6, "bpm": 0,
      "tag_font": "Inter", "dots": 0, "logo": ""}


def _scene(i, blocks, measure=()):
    return {"id": f"c{i}", "t0": 0.0, "t1": 4.4, "step": 1 / 15, "measure": list(measure),
            "blocks": [{"id": b[0], "comp": b[1], "src": str(b[2]), "vars": b[3], "start": 0.0, "dur": 4.6, "track": b[4]} for b in blocks]}


def _probe_scenes(jobs):
    try:
        layout.tools()
    except layout.LayoutUnavailable as e:
        pytest.skip(str(e))
    return layout.probe_scenes(FONTS, jobs)


M = (".chip", ".ct", ".tg")


def test_lockup_without_handle_draws_no_pill_and_three_lines_push_the_city_down():
    tag3 = "Braut · Haarverlängerung · Styling"
    res = _probe_scenes([_scene(0, [("lk", "brand-lockup-soft", LOCKUP, {**LK, "tagline": tag3, "handle": ""}, 2)], M),
                         _scene(1, [("lk", "brand-lockup-soft", LOCKUP, {**LK, "tagline": tag3, "handle": "@jasminefahrni"}, 2)], M),
                         _scene(2, [("lk", "brand-lockup-soft", LOCKUP, {**LK, "tagline": "Hundesalon · Katze", "handle": "@petwash"}, 2)], M)])
    no_handle, handle3, handle1 = (r["measure"] for r in res)
    assert no_handle[".chip"]["shown"] is False                       # (a) no @ -> no pill
    assert no_handle[".ct"]["top"] >= no_handle[".tg"]["bottom"] + 30  # city under the 3rd line
    assert handle3[".chip"]["shown"] and handle3[".chip"]["top"] >= handle3[".tg"]["bottom"] + 30  # (b) pill follows 3 lines
    assert handle3[".ct"]["top"] >= handle3[".chip"]["bottom"]
    assert handle1[".chip"]["top"] == 1120                             # short message: pill stays at chip_y
    assert all(r["hits"] == [] for r in res)


def test_scene_guard_catches_any_shape_over_text():
    old = Path(__file__).parent / "fixtures" / "lockup_pill_bug.html"  # pre-fix behaviour: empty pill at fixed chip_y
    burst = HOME / "motion" / "patterns" / "beat-burst" / "block.html"
    kw = {**US, "lines": "Pet Joy offers|low-stress grooming", "times": "0.1|0.3|0.5|0.8|1.1", "size": 112, "dur": 4.6, "exit": 0}
    res = _probe_scenes([
        _scene(0, [("lk", "brand-lockup-soft", old, {**LK, "tagline": "Braut · Haarverlängerung · Styling", "handle": ""}, 2)]),
        _scene(1, [("w", "kinetic-words", BLOCK, kw, 3),
                   ("b", "beat-burst", burst, {"bpm": 120, "beat0": 0.2, "every": 1, "count": 4, "points": "540,880", "size": 1.4,
                                               "colors": "#7d6a5a|#7d6a5a", "dur": 4.6}, 4)]),
        _scene(2, [("b", "beat-burst", burst, {"bpm": 120, "beat0": 0.2, "every": 1, "count": 4, "points": "540,880", "size": 1.4,
                                               "colors": "#7d6a5a|#7d6a5a", "dur": 4.6}, 1), ("w", "kinetic-words", BLOCK, kw, 3)])])
    pill, over, under = res
    assert any("chip (vazia)" in h["what"] and "Styling" in h["what"] for h in pill["hits"])  # the P076 bug
    assert any(h["what"].startswith("forma b:") for h in over["hits"])                      # confetti above the words
    assert not any(h["what"].startswith("forma") for h in under["hits"])                    # same confetti below: fine
