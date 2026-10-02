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
    assert tm.resolve("vo1:today?", 3) == tm.resolve("vo1:today", 3) and tm.resolve("vo2:tails..end", 3) == tm.resolve("vo2:tails.end", 3)
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


# ---------------------------------------------------------------- v2 standard: new looks + FINAL mode (02/10/2026)
def test_all_music_styles_and_sfx_kinds():
    for style in au.STYLES:
        m = au.music(style, 110, 2.0, seed=3, drop_at=1.0)
        assert len(m) == int(2.0 * au.SR) and np.isfinite(m).all() and np.abs(m).max() > 0
    for k in au.SFX_KINDS:
        s = au.sfx(k)
        assert len(s) > 100 and np.abs(s).max() <= 1.0


def test_concept_accepts_new_looks_and_rejects_unknown(proj):
    f = proj / "broll" / "concept.yaml"
    d = yaml.safe_load(f.read_text())
    d["overlays"] = {"particles": list(B.PARTICLES), "colors": ["accent", "primary"]}
    d["type"].update({"anim": "drop", "panel": "box"})
    d["music"] = {"style": "bossa", "bpm": 96}
    f.write_text(yaml.safe_dump(d))
    B.load_concept(f)
    assert B.check(proj) == []
    for key, bad in (("overlays", {"particles": ["fireworks"]}), ("type", {**d["type"], "anim": "wobble"}),
                     ("type", {**d["type"], "panel": "cloud"}), ("music", {"style": "polka", "bpm": 100})):
        e = dict(d)
        e[key] = bad
        f.write_text(yaml.safe_dump(e))
        with pytest.raises(B.BrollError):
            B.load_concept(f)


def test_overlay_layers_render():
    for fn in (lambda t: fx.sparkles_layer(90, 160, t, 6, 1), lambda t: fx.confetti_layer(90, 160, t, 6, 1),
               lambda t: fx.film_layer(90, 160, t, 1), lambda t: fx.frame_layer(90, 160, t)):
        ims = [fn(t) for t in (0.1, 0.5, 1.0, 2.0)]  # sparkles twinkle: some instant must show something
        assert all(im.size == (90, 160) for im in ims) and any(im.getbbox() is not None for im in ims)
    for arr in (fx.steam_layer(90, 160, 0.5, 1), fx.rays_layer(90, 160, 0.5, 1)):
        assert arr.shape[:2] == (160, 90)


def test_image_sticker_needs_file_and_licence(proj):
    Image.new("RGBA", (120, 120), (255, 200, 0, 255)).save(proj / "broll" / "assets" / "mascot.png")
    _edit_plan(proj, lambda d: d["stickers"].append({"image": "mascot.png", "at": 1.6, "until": 2.2, "x": 0.8, "y": 0.2, "size": 0.15}))
    errs = B.check(proj)
    assert any("mascot.png" in e for e in errs)  # no licence row yet
    with (proj / "assets-licencas.csv").open("a", newline="") as fh:
        csv.writer(fh).writerow(["mascot.png", "teste", "https://example.com/m", "teste"])
    assert B.check(proj) == []
    _edit_plan(proj, lambda d: d["stickers"][-1].__setitem__("image", "nope.png"))
    assert any("imagem ausente" in e for e in B.check(proj))


def test_final_filter_never_carries_preview_text(tmp_path):
    from simplicio_video import paths, render as R
    font = R.preview_font(paths.home())
    for lang in ("pt", "en", "de", "fr"):
        fc = R.final_filter(18.0, font, tmp_path, lang=lang)
        txt = " ".join(p.read_text(encoding="utf8") for p in tmp_path.glob("*.txt")).lower()
        assert "drawtext" in fc and "rotate" not in fc  # no tiled watermark
        assert not any(w in (fc.lower() + txt) for w in R.PREVIEW_WORDS)
        for p in tmp_path.glob("*.txt"):
            p.unlink()
    fc = R.final_filter(18.0, font, tmp_path, lang="en", end_card=False)
    assert "concat" not in fc and "[v]" in fc and "[a]" in fc


def test_final_render_is_clean_full_res_and_deterministic(proj):
    size = (180, 320)
    m1 = B.render(proj, size=size, final=True, log=lambda *_: None)
    fin = proj / "final" / "final.mp4"
    assert fin.is_file() and (proj / "final" / "final.manifest.json").is_file()
    assert not (proj / "preview-v2.mp4").exists()  # the preview is never touched by --final
    info = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,width,height:format=duration",
                                      "-of", "json", str(fin)], capture_output=True, text=True).stdout)
    v = next(s for s in info["streams"] if s["codec_type"] == "video")
    assert (v["width"], v["height"]) == size
    assert abs(float(info["format"]["duration"]) - (3.0 + 2.5)) < 0.2  # spec duration + credit card
    assert m1["schema"] == "simplicio.broll-final/v1" and m1["tts_calls"] == 0 and m1["llm_calls"] == 0
    assert m1["preview"]["watermark"] is None
    clean = proj / "broll" / "out-final" / "broll-full.mp4"
    wm = B.watermark_check(fin, clean, 3.0, n=4, W=180, H=320)
    assert wm["sem_marca_dagua"], wm
    # the same check flags a watermarked preview of the same render
    from simplicio_video import paths, render as R
    prev = proj / "prev-test.mp4"
    R.make_preview(clean, prev, paths.home(), log=lambda *_: None, lang="en")
    assert not B.watermark_check(prev, clean, 3.0, n=4, W=180, H=320)["sem_marca_dagua"]
    # deterministic: same spec -> byte-identical final
    sha1 = m1["preview"]["sha256"]
    m2 = B.render(proj, size=size, final=True, log=lambda *_: None)
    assert m2["preview"]["sha256"] == sha1


def test_emphasis_font_keeps_its_own_case_and_size(proj):
    """Script emphasis fonts must not be upper-cased by an upper base, and the line box must cover them."""
    from simplicio_video import paths
    f = proj / "broll" / "concept.yaml"
    d = yaml.safe_load(f.read_text())
    _edit_plan(proj, lambda p: p["texts"][1].update({"emph": ["hands"]}))
    widths = {}
    for ecase in ("none", "upper"):
        d["type"].update({"case": "upper", "panel": "box", "fonts": {"emph": {
            "font": "motion/assets/fonts/broll/GreatVibes-Regular.ttf", "case": ecase, "tracking": 0.0, "size": 0.16, "fill": "accent"}}})
        f.write_text(yaml.safe_dump(d))
        c, plan = _plan(proj)
        L = B.layout_card(c, paths.home(), plan.cards[1], 540, 960)
        widths[ecase] = {s[6][0]: s[3] for s in L.sprites}
        x0, _, x1, _ = L.lines[0]
        for s in L.sprites:
            assert x0 - 1 <= s[1] - s[3] / 2 and s[1] + s[3] / 2 <= x1 + 1
    assert widths["none"]["hands,"] < widths["upper"]["hands,"] * 0.85   # script caps are much wider: case was honoured


# ---------------------------------------------------------------- regra 2026-10-02: pt sempre mais animado (trilha)
def test_music_lift_zero_e_bit_identico_e_lift_traz_brilho():
    for style in ("bouncy", "elegant", "samba", "acoustic"):
        a = au.music(style, 128, 2.0, seed=5, drop_at=1.0)
        assert np.array_equal(a, au.music(style, 128, 2.0, seed=5, drop_at=1.0, lift=0.0))
        b = au.music(style, 128, 2.0, seed=5, drop_at=1.0, lift=1.0)
        assert np.isfinite(b).all() and not np.array_equal(a, b)
        assert np.array_equal(b, au.music(style, 128, 2.0, seed=5, drop_at=1.0, lift=1.0))  # determinístico

        def hf(x):  # energia acima de ~5 kHz (percussão/brilho)
            m = x.mean(1) if x.ndim == 2 else x
            sp = np.abs(np.fft.rfft(m)) ** 2
            f = np.fft.rfftfreq(len(m), 1 / au.SR)
            return sp[f > 5000].sum() / sp.sum()
        assert hf(b) > hf(a), style


def test_music_for_preset_pt_so_com_voz_nova_e_ingles_igual():
    M = {"style": "bossa", "bpm": 96, "db": -11.5, "duck_db": 8.0, "drop_at": 7.12, "seed": 77}
    en = B.music_for(M, "en-US", True)
    assert {k: en[k] for k in M} == M and en["lift"] == 0.0 and "preset" not in en
    old = B.music_for(M, "pt-BR", False)  # voz antiga (lock sem voz_pt_animada): prévia re-renderiza igual
    assert {k: old[k] for k in M} == M and old["lift"] == 0.0
    pt = B.music_for(M, "pt-BR", True)
    assert pt["preset"] == "pt-animado" and pt["style"] == "samba" and 124 <= pt["bpm"] <= 135
    assert pt["lift"] == 1.0 and pt["db"] == -10.5 and pt["duck_db"] <= 8.0 and pt["seed"] == 77
    fast = B.music_for({**M, "style": "house", "bpm": 150}, "pt-BR", True)
    assert fast["style"] == "house" and fast["bpm"] == 135
    assert B.music_for({**M, "pt_animado": False}, "pt-BR", True)["lift"] == 0.0
    assert B.music_for({**M, "pt_animado": True}, "pt-BR", False)["preset"] == "pt-animado"
    assert B.music_for({**M, "pt_animado": True}, "en-US", True)["lift"] == 0.0


def test_render_pt_com_voz_nova_usa_trilha_animada(proj):
    lock = json.loads((proj / "timing.lock.json").read_text())
    lock["voz_pt_animada"] = True
    (proj / "timing.lock.json").write_text(json.dumps(lock))
    (proj / "contract.yaml").write_text(yaml.safe_dump({"formato": {"duracao_s": 3}, "voz": {"idioma": "pt-BR"}}))
    f = proj / "broll" / "concept.yaml"
    d = yaml.safe_load(f.read_text())
    d["music"] = {"style": "bossa", "bpm": 96}
    f.write_text(yaml.safe_dump(d))
    B.render(proj, size=(180, 320), post=False, log=lambda *_: None)
    man = json.loads((proj / "preview-v2.manifest.json").read_text())
    assert man["music"]["preset"] == "pt-animado" and man["music"]["style"] == "samba" and 124 <= man["music"]["bpm"] <= 135
    d["music"]["pt_animado"] = "talvez"
    f.write_text(yaml.safe_dump(d))
    with pytest.raises(B.BrollError):
        B.load_concept(f)


# ---------------------------------------------------------------- estilos funk e axé (02/10): novos, distintos, sem mexer nos 12
OLD_STYLE_HASHES = {  # sha256[:16] do PCM int16 de au.music(style, 118, 3.0, seed=11, drop_at=1.5, lift=L), gerado no commit d42b4e7
    0.0: {"bouncy": "324cf2875c19322c", "elegant": "1ee7e27d53d4b374", "disco": "c09fbd19aaf183ec", "lofi": "f36a729ab6a62a10",
          "samba": "0e0447c2f7d6ecb3", "bossa": "3e34d7d7324a6290", "house": "8edccd40a7ac1e6c", "cinematic": "d5fe73512e8a4242",
          "hiphop": "21a3872376de29ed", "tropical": "e351acb1e6bab200", "acoustic": "b5c35a86cee77b10", "forro": "178d507449b079ca"},
    1.0: {"bouncy": "276ddec1f773518c", "elegant": "1b94dfc353b18722", "disco": "8c3749ef36c99df9", "lofi": "de1ce363b4d30ce1",
          "samba": "780cbc106d56f605", "bossa": "1ded2453bb87a7a8", "house": "3aeeb56951ee686e", "cinematic": "40df24b4859be11c",
          "hiphop": "0d11ea19a21629e9", "tropical": "881129ba03ac4e40", "acoustic": "15750c29129d6c7e", "forro": "009f109ad01fafed"},
}


def _pcm_hash(x):
    import hashlib
    return hashlib.sha256((np.clip(x, -1, 1) * 32767).round().astype(np.int16).tobytes()).hexdigest()[:16]


def _groove(x, bpm):  # padrão de ataques em 16 avos (normalizado)
    m = x.mean(1)
    hop = int(au.SR * 0.005)
    env = np.add.reduceat(np.abs(m), np.arange(0, len(m), hop))
    on = np.maximum(0, np.diff(env, prepend=env[0]))
    t = np.arange(len(on)) * hop / au.SR
    g = np.zeros(16)
    for k, v in zip(((t / (60 / bpm / 4)).round().astype(int)) % 16, on):
        g[k] += v
    return g / np.linalg.norm(g)


@pytest.mark.parametrize("lift", [0.0, 1.0])
def test_os_12_estilos_antigos_mantem_o_hash(lift):
    got = {s: _pcm_hash(au.music(s, 118, 3.0, seed=11, drop_at=1.5, lift=lift)) for s in OLD_STYLE_HASHES[lift]}
    assert got == OLD_STYLE_HASHES[lift]


def test_funk_e_axe_renderizam_e_sao_deterministicos():
    assert {"funk", "axe"} <= set(au.STYLES) and len(au.STYLES) == len(set(au.STYLES)) == 14
    for style, bpm in (("funk", 130), ("axe", 126)):
        for lift in (0.0, 1.0):
            m = au.music(style, bpm, 3.0, seed=7, drop_at=1.5, lift=lift)
            assert m.shape == (int(3.0 * au.SR), 2) and np.isfinite(m).all()
            assert 0.05 < np.abs(m).max() <= 1.0 and float(np.sqrt((m ** 2).mean())) > 0.01
            assert np.array_equal(m, au.music(style, bpm, 3.0, seed=7, drop_at=1.5, lift=lift))


def test_funk_e_axe_nao_colidem_com_os_outros():
    beds = {s: au.music(s, 128, 4.0, seed=5) for s in au.STYLES}
    hashes = {s: _pcm_hash(b) for s, b in beds.items()}
    assert len(set(hashes.values())) == len(au.STYLES)  # 14 trilhas diferentes
    G = {s: _groove(b, 128) for s, b in beds.items()}
    for new in ("funk", "axe"):
        for other in au.STYLES:
            if other != new:
                assert not np.array_equal(beds[new], beds[other])
                assert float(G[new] @ G[other]) < 0.97, (new, other)  # groove próprio, não cópia de outro estilo
    assert au.PROGRESSIONS["funk"] != au.PROGRESSIONS["axe"]


def test_estilo_de_trilha_desconhecido_da_erro_visivel(proj):
    with pytest.raises(ValueError, match="estilo de trilha desconhecido: polka"):
        au.music("polka", 120, 1.0)
    f = proj / "broll" / "concept.yaml"
    d = yaml.safe_load(f.read_text())
    d["music"] = {"style": "funky", "bpm": 130}
    f.write_text(yaml.safe_dump(d))
    with pytest.raises(B.BrollError, match=r"music\.style desconhecido 'funky'.*funk.*axe"):
        B.load_concept(f)
    d["music"] = {"style": "axe", "bpm": 126}
    f.write_text(yaml.safe_dump(d))
    assert B.load_concept(f)["music"]["style"] == "axe"
