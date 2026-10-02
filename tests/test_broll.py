"""B-roll visual mode: time refs, word-synced captions, editorial cut rules, licences, health rules, layout guard,
transitions, audio mix/loudness and a tiny end-to-end render (synthetic clips, no TTS, no network)."""
import csv
import json
import shutil
import subprocess
import wave
from pathlib import Path

import numpy as np
import pytest
import yaml
from PIL import Image

from simplicio_video import broll as B
from simplicio_video import broll_audio as au
from simplicio_video import broll_fx as fx

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg ausente")

SR = 48000


def _wav(path: Path, dur: float, freq: float = 220.0):
    t = np.arange(int(SR * dur)) / SR
    x = (0.3 * np.sin(2 * np.pi * freq * t) * np.minimum(1, t * 20) * np.minimum(1, (dur - t) * 20)).astype(np.float32)
    rng = np.random.default_rng(int(freq))
    x += (0.05 * rng.standard_normal(len(x))).astype(np.float32)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype(np.int16).tobytes())


def _clip(path: Path, dur: float, src: str = "testsrc2"):
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"{src}=size=320x240:rate=30:duration={dur}",
                    "-pix_fmt", "yuv420p", str(path)], check=True)


@pytest.fixture
def proj(tmp_path):
    """3 s project: 2 voice takes in a timing lock, 3 synthetic clips + 1 still + logo, licences, concept and plan."""
    p = tmp_path / "proj"
    (p / "voz").mkdir(parents=True)
    a = p / "broll" / "assets"
    a.mkdir(parents=True)
    _wav(p / "voz" / "vo1.wav", 1.0, 220)
    _wav(p / "voz" / "vo2.wav", 1.0, 330)
    lock = {"lines": {
        "vo1": {"t": 0.2, "dur_s": 1.0, "file": "voz/vo1.wav", "fits": True, "text": "Nervous pup today?",
                "words": [{"w": "Nervous", "t": 0.0, "end": 0.4}, {"w": "pup", "t": 0.45, "end": 0.7}, {"w": "today?", "t": 0.72, "end": 1.0}]},
        "vo2": {"t": 1.6, "dur_s": 1.0, "file": "voz/vo2.wav", "fits": True, "text": "Gentle hands, happy tails.",
                "words": [{"w": "Gentle", "t": 0.0}, {"w": "hands,", "t": 0.3}, {"w": "happy", "t": 0.55}, {"w": "tails.", "t": 0.75}]}}}
    (p / "timing.lock.json").write_text(json.dumps(lock))
    (p / "contract.yaml").write_text(yaml.safe_dump({"formato": {"duracao_s": 3}, "voz": {"idioma": "en-US"}}))
    _clip(a / "c1.mp4", 2.0)
    _clip(a / "c2.mp4", 2.0, "smptebars")
    _clip(a / "c3.mp4", 2.0, "rgbtestsrc")
    Image.new("RGB", (400, 300), (40, 160, 140)).save(a / "still.jpg")
    lg = Image.new("RGBA", (300, 80), (0, 0, 0, 0))
    lg.paste((93, 189, 169, 255), (10, 10, 290, 70))
    lg.save(a / "logo.png")
    with (p / "assets-licencas.csv").open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["arquivo", "fonte", "link", "licenca"])
        for f in ["c1.mp4", "c2.mp4", "c3.mp4", "still.jpg", "logo.png"]:
            w.writerow([f, "teste", "https://example.com/" + f, "teste"])
    concept = {"nome": "teste", "palette": {"primary": "#5dbda9", "secondary": "#fffb89", "accent": "#2f9e8f", "ink": "#111111", "light": "#ffffff"},
               "type": {"font": "motion/assets/fonts/Fredoka.ttf", "variation": "Bold", "size": 0.12, "panel": "pill",
                        "panel_colors": ["secondary", "primary"], "fill": "ink"},
               "transitions": {"default": ["pop", "whip"], "frames": 7},
               "overlays": {"particles": "bubbles", "density": 4},
               "music": {"style": "bouncy", "bpm": 124}, "sfx": {"cut": "swish", "sticker": "pop", "hook": "impact", "logo": "shimmer"}}
    (p / "broll" / "concept.yaml").write_text(yaml.safe_dump(concept, allow_unicode=True))
    plan = {"shots": [{"src": "c1.mp4", "until": "vo1:pup"}, {"src": "c2.mp4", "until": 1.5, "tx": "glitch"},
                      {"src": "still.jpg", "until": "vo2:happy"}, {"src": "c3.mp4"}],
            "texts": [{"text": "Nervous / pup?", "sync": "vo1", "y": 0.65}, {"text": "Gentle hands,", "sync": "vo2", "y": 0.65}],
            "stickers": [{"icon": "paw", "at": 0.3, "until": 1.0, "x": 0.8, "y": 0.2}],
            "logo": {"file": "logo.png", "at": "vo2:happy", "until": "end", "y": 0.35}}
    (p / "broll" / "plan.yaml").write_text(yaml.safe_dump(plan, allow_unicode=True))
    return p


def _plan(p):
    c = B.load_concept(p / "broll" / "concept.yaml")
    return c, B.load_plan(p, B.Timing.load(p), 3.0, c)


def _edit_plan(p, fn):
    f = p / "broll" / "plan.yaml"
    d = yaml.safe_load(f.read_text())
    fn(d)
    f.write_text(yaml.safe_dump(d, allow_unicode=True))


def test_time_refs(proj):
    tm = B.Timing.load(proj)
    assert tm.resolve(1.25, 3) == 1.25
    assert tm.resolve("end", 3) == 3
    assert tm.resolve("end-0.5", 3) == 2.5
    assert tm.resolve("vo1", 3) == pytest.approx(0.2)
    assert tm.resolve("vo1.end", 3) == pytest.approx(1.2)
    assert tm.resolve("vo1:pup", 3) == pytest.approx(0.65)
    assert tm.resolve("vo1:pup.end", 3) == pytest.approx(0.9)
    assert tm.resolve("vo2#1", 3) == pytest.approx(1.9)
    assert tm.resolve("vo2:happy+0.1", 3) == pytest.approx(2.25)
    with pytest.raises(B.BrollError):
        tm.resolve("vo9", 3)


def test_lock_without_fit_is_refused(proj):
    lock = json.loads((proj / "timing.lock.json").read_text())
    lock["lines"]["vo2"]["fits"] = False
    (proj / "timing.lock.json").write_text(json.dumps(lock))
    with pytest.raises(B.BrollError, match="nunca regenera"):
        B.Timing.load(proj)


def test_caption_words_enter_on_voice_onsets(proj):
    c, plan = _plan(proj)
    cd = plan.cards[0]
    assert [(t[0], t[1]) for t in cd.tokens] == [("Nervous", 0.2), ("pup?", 0.65)]
    assert cd.start == pytest.approx(0.14)
    assert [t[2] for t in cd.tokens] == [0, 1]


def test_caption_must_be_what_the_voice_says(proj):
    _edit_plan(proj, lambda d: d["texts"].__setitem__(0, {"text": "Scared pup?", "sync": "vo1"}))
    with pytest.raises(B.BrollError, match="não aparece"):
        _plan(proj)


def test_captions_hand_over_instead_of_stacking(proj):
    _edit_plan(proj, lambda d: d["texts"].insert(1, {"text": "today?", "sync": "vo1", "y": 0.65}))
    c, plan = _plan(proj)
    assert plan.cards[0].end <= plan.cards[1].start


def test_plan_rules_ok_and_cut_limits(proj):
    c, plan = _plan(proj)
    assert B.check_plan(plan, c) == []
    assert B.check_licenses(proj, plan) == []
    _edit_plan(proj, lambda d: d["shots"][1].__setitem__("until", 2.6))
    c, plan = _plan(proj)
    errs = B.check_plan(plan, c)
    assert any("dura" in e for e in errs)


def test_hook_needs_cut_and_text(proj):
    def f(d):
        d["shots"] = [{"src": "c1.mp4", "until": 1.2, "hold": True}, {"src": "c2.mp4", "until": 2.1}, {"src": "c3.mp4"}]
        d["texts"] = [{"text": "Gentle hands,", "sync": "vo2"}]
    _edit_plan(proj, f)
    c, plan = _plan(proj)
    errs = B.check_plan(plan, c)
    assert any("gancho sem texto" in e for e in errs)


def test_missing_licence_row_fails(proj):
    rows = [r for r in csv.reader((proj / "assets-licencas.csv").open()) if r[0] != "c2.mp4"]
    with (proj / "assets-licencas.csv").open("w", newline="") as fh:
        csv.writer(fh).writerows(rows)
    c, plan = _plan(proj)
    assert B.check_licenses(proj, plan) == ["asset sem fonte/licença em assets-licencas.csv: c2.mp4"]


def test_health_rules_block_brands_and_promises(proj):
    lock = json.loads((proj / "timing.lock.json").read_text())
    lock["lines"]["vo2"]["words"] += [{"w": "Botox", "t": 0.85}, {"w": "results", "t": 0.9}]
    (proj / "timing.lock.json").write_text(json.dumps(lock))
    _edit_plan(proj, lambda d: d["texts"].__setitem__(1, {"text": "Botox results", "sync": "vo2"}))
    c, plan = _plan(proj)
    c["setor"] = "saude"
    errs = B.check_plan(plan, c)
    assert any("marca registrada" in e for e in errs) and any("resultado" in e for e in errs)


def test_price_text_is_blocked(proj):
    _edit_plan(proj, lambda d: d["texts"].append({"text": "Only $99", "at": 2.0}))
    c, plan = _plan(proj)
    assert any("proibido" in e for e in B.check_plan(plan, c))


def test_concept_validation(proj):
    f = proj / "broll" / "concept.yaml"
    d = yaml.safe_load(f.read_text())
    d["transitions"]["frames"] = 14
    f.write_text(yaml.safe_dump(d))
    with pytest.raises(B.BrollError, match="6 e 10"):
        B.load_concept(f)
    d["transitions"] = {"default": ["spin360"], "frames": 8}
    f.write_text(yaml.safe_dump(d))
    with pytest.raises(B.BrollError, match="desconhecida"):
        B.load_concept(f)
    d["transitions"] = {"default": ["pop"], "frames": 8}
    d["palette"]["primary"] = "teal"
    f.write_text(yaml.safe_dump(d))
    with pytest.raises(B.BrollError, match="rrggbb"):
        B.load_concept(f)


def test_layout_guard_catches_sticker_over_text(proj):
    assert B.check(proj) == []
    _edit_plan(proj, lambda d: d["stickers"].__setitem__(0, {"icon": "paw", "at": 0.3, "until": 1.0, "x": 0.5, "y": 0.65, "size": 0.3}))
    assert any("cobre o texto" in e for e in B.check(proj))


def test_layout_guard_safe_area(proj):
    _edit_plan(proj, lambda d: d["texts"][0].__setitem__("y", 0.98))
    assert any("área segura" in e for e in B.check(proj))


@pytest.mark.parametrize("kind", list(fx.TRANSITIONS))
def test_transitions_shape_and_endpoints(kind):
    a = np.full((64, 36, 3), 30, np.uint8)
    b = np.full((64, 36, 3), 220, np.uint8)
    for p in (0.0, 0.3, 0.5, 0.8, 1.0):
        out = fx.transition(kind, a, b, p, seed=1, color=(255, 255, 255), leak=(255, 210, 170), direction=1)
        assert out.shape == a.shape and out.dtype == np.uint8
    assert np.abs(fx.transition(kind, a, b, 1.0, seed=1, color=(255, 255, 255), leak=(255, 210, 170), direction=1).astype(int) - 220).mean() < 25


def test_crop_box_is_9x16_inside_source():
    x, y, w, h = fx.crop_box(1920, 1080, 9 / 16, 0.9, 0.5)
    assert abs(w / h - 9 / 16) < 0.01 and x >= 0 and x + w <= 1920 and h == 1080


def test_music_sfx_mix_and_loudnorm(tmp_path):
    for style in ("bouncy", "elegant"):
        m = au.music(style, 120, 3.0, seed=1)
        assert m.ndim in (1, 2) and len(m) == int(3.0 * au.SR) and np.isfinite(m).all()
    for k in ("whoosh", "swish", "pop", "tick", "shimmer", "impact"):
        s = au.sfx(k)
        assert len(s) > 100 and np.abs(s).max() <= 1.0
    _wav(tmp_path / "v.wav", 1.0, 260)
    bed = au.music("bouncy", 124, 3.0, seed=2)
    mix = au.mix([(0.5, tmp_path / "v.wav")], 3.0, bed, [(0.0, "impact", 0.0), (1.5, "pop", 0.0)])
    au.write_wav(tmp_path / "mix.wav", mix)
    au.loudnorm(tmp_path / "mix.wav", tmp_path / "master.wav", -14.0, -1.5)
    m = au.measure(tmp_path / "master.wav")
    assert -15.5 <= m["lufs"] <= -12.5 and m["tp"] <= -1.4
    off = au.sync_offsets(au.read_wav(tmp_path / "master.wav"), [(0.5, tmp_path / "v.wav")])
    assert abs(off[0][0]) <= 0.02 and off[0][1] > 0.3


def test_render_end_to_end_small(proj):
    B.render(proj, size=(180, 320), post=False, log=lambda *_: None)
    out = proj / "broll" / "out"
    full = out / "broll-full.mp4"
    assert full.is_file()
    info = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,width,height:format=duration",
                                      "-of", "json", str(full)], capture_output=True, text=True).stdout)
    v = next(s for s in info["streams"] if s["codec_type"] == "video")
    assert (v["width"], v["height"]) == (180, 320)
    assert any(s["codec_type"] == "audio" for s in info["streams"])
    assert abs(float(info["format"]["duration"]) - 3.0) < 0.15
    man = json.loads((proj / "preview-v2.manifest.json").read_text())
    assert man["tts_calls"] == 0 and len(man["shots"]) == 4
    assert [t["kind"] for t in man["transitions"]] == ["glitch", "whip", "pop"]
    words = json.loads((out / "broll-words.json").read_text())
    seen = {w for fr in words for w in fr["words"]}
    assert {"Nervous", "pup?", "Gentle", "hands,"} <= seen
    assert not any("pup?" in fr["words"] for fr in words if fr["t"] < 0.6)
    m = au.measure(full)
    assert -15.5 <= m["lufs"] <= -12.5 and m["tp"] <= -1.4
