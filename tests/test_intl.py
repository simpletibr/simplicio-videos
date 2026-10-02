"""INT (international) previews: `simplicio-video intl`, template internacional-dor, localized watermark/end card. Hermetic: no TTS, no render."""
import csv
import json
import subprocess

import pytest
import yaml

from conftest import ROOT, run_cli
from simplicio_video import contract as ct
from simplicio_video import intl
from simplicio_video import render as R

PAISES = intl.load_paises(ROOT)

# synthetic companies (not real prospects), one per country style
LINES = {
    "en": ["Long wait at the salon?", "Booking should be simple.", "At Demo Studio, you book online in seconds.", "Demo Studio, Main Street."],
    "de": ["Stress beim Hundefriseur?", "Zeitdruck bedeutet Stress für das Tier.", "Bei Demo Studio wird in Ruhe gepflegt.", "Demo Studio, im Viertel."],
    "fr": ["Envie d'un regard plus net?", "Le maquillage prend du temps.", "Chez Demo Studio, on prend le temps.", "Demo Studio, à Genève."],
}


def _png(path, w=240, h=240):
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"color=c=0xb87333:s={w}x{h}", "-frames:v", "1", str(path)], check=True)
    return path


def _ficha(pais, slug=None, logo=None, lines=None, **kw):
    lang = PAISES[pais]["idioma"].split("-")[0]
    L = lines or LINES[lang]
    f = {"p": "P999", "slug": slug or f"demo-{pais}", "nome": "Demo Studio", "pais": pais, "drive_nome": "Demo_Studio",
         "cidade_label": "Main Street · Town", "handle": "@demostudio", "tagline": "Hair · Nails", "lockup": ["DEMO STUDIO", "HAIR"],
         "dor": {"escolhida": "espera", "evidencia": "review", "fonte": "https://example.com"},
         "falas": {f"vo{i + 1}": {"texto": t} for i, t in enumerate(L)}}
    if logo:
        f.update(logo=str(logo), logo_px=[240, 240], logo_fonte="site oficial")
    f.update(kw)
    return f


@pytest.mark.parametrize("lang,word,end", [("pt", "Prévia", "Vídeo feito por Wesley Simplicio"), ("en", "Preview", "Video by Wesley Simplicio"),
                                           ("de", "Vorschau", "Video von Wesley Simplicio"), ("fr", "Aperçu", "Vidéo réalisée par Wesley Simplicio")])
def test_preview_texts_localized_and_never_simpleti(lang, word, end):
    t = R.preview_texts(lang)
    assert t["watermark"].startswith(word) and t["watermark"].endswith("• Wesley Simplicio • @wesleysimplicio")
    assert t["end_title"] == end and t["end_url"] == "@wesleysimplicio"
    assert t["width"] == 540 and t["height"] == 960
    assert "simpleti" not in json.dumps(t, ensure_ascii=False).lower()


def test_preview_lang_mapping_and_pt_default_unchanged():
    assert [R.preview_lang(x) for x in ("en-US", "de-CH", "fr-CH", "pt-BR", None, "", "es-ES")] == ["en", "de", "fr", "pt", "pt", "pt", "pt"]
    assert R.preview_texts() == {**R.PREVIEW, **R.PREVIEW_I18N["pt"]}
    assert R.preview_texts("pt")["watermark"] == R.PREVIEW_I18N["pt"]["watermark"]


def test_preview_filter_uses_language_and_optional_note(tmp_path):
    font = R.preview_font(ROOT)
    f = R.preview_filter(10.0, font, tmp_path, lang="de", note="SEM VOZ")
    assert (tmp_path / "wm.txt").read_text(encoding="utf8").strip().startswith("Vorschau • Wesley Simplicio")
    assert " ".join(x.read_text(encoding="utf8") for x in sorted(tmp_path.glob("end1_*.txt"))) == "Video von Wesley Simplicio"
    assert (tmp_path / "note.txt").read_text(encoding="utf8") == "SEM VOZ" and "0xc0392b" in f
    (tmp_path / "en").mkdir()
    g = R.preview_filter(10.0, font, tmp_path / "en", lang="en")
    assert "0xc0392b" not in g and (tmp_path / "en" / "wm.txt").read_text(encoding="utf8").strip().startswith("Preview • Wesley")


@pytest.mark.parametrize("text", ["Only $49 today", "Ab 39 € pro Termin", "Seulement 30 CHF", "Free consultation", "kostenlos testen",
                                  "Guaranteed results", "Die beste Pflege", "Le meilleur salon", "20% off", "Before and after", "by SimpleTI"])
def test_guards_reject_price_promo_guarantee_superlative(text):
    assert intl.check_text(text), text


@pytest.mark.parametrize("text", ["Fear-free grooming at your door.", "Stress beim Hundefriseur?", "Chez Jessi, on prend le temps.",
                                  "Odeon, Jumeirah Beach Road. Since 2017."])
def test_guards_allow_honest_lines(text):
    assert intl.check_text(text) == []


@pytest.mark.parametrize("pais", sorted(PAISES))
def test_every_country_builds_a_valid_contract(pais, tmp_path):
    logo = _png(tmp_path / "logo.png")
    f = _ficha(pais, logo=logo)
    d, meta = intl.build_contract(f)
    P = PAISES[pais]
    assert d["template"] == "internacional-dor" and d["voz"]["idioma"] == P["idioma"]
    assert d["voz"]["providers"]["gemini"]["voice"] == P["voz"]["voice"]
    assert abs(sum(s["duracao_s"] for s in d["cenas"]) - d["formato"]["duracao_s"]) < 1e-3
    assert d["drive"]["caminho"] == "simplicio-video/clientes/Demo_Studio/2026/Preview_INT1"
    blob = json.dumps(d, ensure_ascii=False).lower()
    assert "simpleti" not in blob and "preço" not in blob
    path = intl.write_contract(tmp_path / f["slug"], f, d)
    rep = ct.validate(ct.load(path))
    assert rep.errors == [], rep.errors
    assert meta["logo"] == "real"


def test_text_lockup_when_no_logo():
    d, meta = intl.build_contract(_ficha("de"))
    assert d["marca"]["logo"] is None and meta["logo"] == "lockup de texto"
    lock = [m for m in d["cenas"][3]["motion"] if m["padrao"] == "brand-lockup-soft"][0]["params"]
    assert lock["logo"] == "" and lock["name"] == "DEMO STUDIO"


def test_dubai_is_dark_premium_and_germany_sober():
    ae, de, us = PAISES["ae"], PAISES["de"], PAISES["us"]
    assert intl.luminance(ae["base"]) < 0.1 and intl.luminance(de["base"]) > 0.5
    assert de["modo"] == "calm" and de["bpm"] < us["bpm"]
    d, _ = intl.build_contract(_ficha("ae"))
    bg = [m for m in d["cenas"][0]["motion"] if m["padrao"] == "bg-parallax"][0]["params"]
    assert bg["center"] == ae["centro"] and bg["base"] == ae["base"]


def test_price_in_a_line_fails_the_company():
    L = list(LINES["en"])
    L[2] = "Demo Studio, only $20 a visit."
    with pytest.raises(intl.FichaError, match="Demo Studio|\\$|preço|moeda"):
        intl.build_contract(_ficha("us", lines=L))


def test_screen_words_must_follow_the_speech():
    f = _ficha("us")
    f["falas"]["vo1"]["tela"] = "Long wait|at the spa?"
    with pytest.raises(intl.FichaError, match="vo1"):
        intl.build_contract(f)


def test_too_long_line_fails_without_speeding_up():
    L = list(LINES["en"])
    L[0] = "A really very long opening question that never fits the hook slot at all?"
    with pytest.raises(intl.FichaError, match="encurte"):
        intl.build_contract(_ficha("us", lines=L))


def test_long_handle_is_left_out_of_the_chip():
    d, meta = intl.build_contract(_ficha("us", handle="@a_really_long_instagram_handle_x"))
    lock = [m for m in d["cenas"][3]["motion"] if m["padrao"] == "brand-lockup-soft"][0]["params"]
    assert lock["handle"] == "" and meta["chip_handle"] is False


def test_same_line_same_voice_is_one_tts_call(tmp_path):
    fd = tmp_path / "fichas"
    fd.mkdir()
    a = _ficha("de", slug="a-de")
    b = _ficha("ch-de", slug="b-ch", lines=["Stress beim Hundefriseur?", "Hier zählt Geduld.", "Bei Demo Basel wird in Ruhe gepflegt.", "Demo Basel, im Quartier."])
    for f in (a, b):
        (fd / f"{f['slug']}.yaml").write_text(yaml.safe_dump(f, allow_unicode=True), encoding="utf8")
    da, _ = intl.build_contract(a)
    db, _ = intl.build_contract(b)
    assert intl.voice_key(da, "vo1") == intl.voice_key(db, "vo1")
    assert intl.voice_key(da, "vo2") != intl.voice_key(db, "vo2")
    out = tmp_path / "out"
    res = intl.run([fd], out, log=lambda *a: None)
    rows = list(csv.DictReader((out / "falas-todas.csv").open(encoding="utf8")))
    assert len(rows) == 8 and sum(int(r["tts_necessaria"]) for r in rows) == 7
    reused = [r for r in rows if r["reusa_de"]]
    assert len(reused) == 1 and reused[0]["id"] == "vo1" and reused[0]["reusa_de"] == "a-de"
    for slug in ("a-de", "b-ch"):
        for n in ("contract.yaml", "roteiro.md", "falas.csv", "briefing-visual.md"):
            assert (out / slug / n).is_file()
        assert "https://example.com" in (out / slug / "roteiro.md").read_text(encoding="utf8")
    assert res["tts_necessarias"] == 7


def test_intl_help():
    r = run_cli("intl", "--help")
    assert r.returncode == 0, r.stderr
    for m in ("FICHA", "--out", "--mudo", "--render", "--provider", "Vorschau", "exemplos:", "simplicio-video intl"):
        assert m in r.stdout


# ---- layout v2 (Wesley 02/10: readable US text, centred safe zone, subtle watermark, logo in S3) + pt-BR (INT-2-BR) ----

def _kw(d, i):
    return [m for m in d["cenas"][i]["motion"] if m["padrao"] == "kinetic-words"][0]["params"]


def test_kinetic_words_declares_the_new_options():
    import re as _re
    html = (ROOT / "motion/patterns/kinetic-words/block.html").read_text(encoding="utf8")
    decl = json.loads(_re.search(r"data-composition-variables='(\[.*?\])'", html).group(1))
    pj = json.loads((ROOT / "motion/patterns/kinetic-words/pattern.json").read_text(encoding="utf8"))
    for k in ("cy", "stroke", "panel", "panel_alpha", "weight", "lead", "logo", "logo_h", "logo_w", "logo_bg"):
        assert k in {v["id"] for v in decl} and k in {v["id"] for v in pj["params"]}
    # defaults keep the Brazilian v03 look: stroke on, no panel, no centring, no lead
    D = {v["id"]: v["default"] for v in decl}
    assert D["stroke"] == 1 and D["panel"] == "" and D["cy"] == 0 and D["lead"] == 0


def test_subtle_watermark_has_fewer_lighter_rows(tmp_path):
    font = R.preview_font(ROOT)
    a = R.preview_filter(10.0, font, tmp_path, lang="en")
    (tmp_path / "s").mkdir()
    b = R.preview_filter(10.0, font, tmp_path / "s", lang="en", wm="sutil")
    assert a.count("textfile=") - b.count("textfile=") == 5
    assert "colorchannelmixer=aa=0.2[wm]" in a and "colorchannelmixer=aa=0.11[wm]" in b


def test_us_text_is_solid_on_a_panel_and_centred(tmp_path):
    d, meta = intl.build_contract(_ficha("us", logo=_png(tmp_path / "l.png", 600, 200), logo_px=[600, 200]))
    for i in range(3):
        k = _kw(d, i)
        assert k["stroke"] == 0 and k["font"] == "Inter" and k["panel"] and k["lead"] > 0
        assert 0.25 * 1920 <= k["cy"] <= 0.65 * 1920
        assert intl.contrast("#ffffff", k["panel"]) >= 5.0
    assert _kw(d, 2)["logo"] == "assets/client/logo.png" and _kw(d, 2)["logo_bg"] == "#ffffff"
    lock = [m for m in d["cenas"][3]["motion"] if m["padrao"] == "brand-lockup-soft"][0]["params"]
    assert lock["logo"] and lock["logo_size"] >= 400
    assert d["saida"]["marca_dagua"] == "sutil"


@pytest.mark.parametrize("pais", sorted(PAISES))
def test_text_reads_on_every_country_background(pais):
    d, _ = intl.build_contract(_ficha(pais))
    P = PAISES[pais]
    for i in range(3):
        k = _kw(d, i)
        bg = k["panel"] or P["base"]
        for c in k["colors"].split("|"):
            assert intl.contrast(c, bg) >= 4.5, (pais, c, bg)
        assert 0.25 * 1920 <= k["cy"] <= 0.65 * 1920


PT = ["Saudade do pastel de feira?", "Aqui na Flórida é difícil achar.", "No Demo Studio, sai na hora, crocante.", "Demo Studio, Pompano Beach."]


def test_pt_br_video_in_a_foreign_country(tmp_path):
    f = _ficha("us", lines=PT, idioma="pt-BR", lote="INT-2-BR", toque_br=True)
    d, meta = intl.build_contract(f)
    assert d["voz"]["idioma"] == "pt-BR" and d["voz"]["voice"] == "Laomedeia" and "Brazilians who live in the US" in d["voz"]["estilo"]
    assert R.preview_texts(R.preview_lang(d["voz"]["idioma"]))["watermark"].startswith("Prévia • Wesley Simplicio")
    assert d["drive"]["caminho"].endswith("/2026/Preview_INT2BR") and "Preview INT-2-BR" in d["drive"]["arquivo"]
    bg = [m for m in d["cenas"][0]["motion"] if m["padrao"] == "bg-parallax"][0]["params"]
    assert "#009c3b" in bg["colors"]
    path = intl.write_contract(tmp_path / "x", f, d)
    assert ct.validate(ct.load(path)).errors == []


def test_run_uses_ficha_language_in_falas_csv(tmp_path):
    fd = tmp_path / "fichas"
    fd.mkdir()
    f = _ficha("us", slug="pt-us", lines=PT, idioma="pt-BR", lote="INT-2-BR")
    (fd / "pt-us.yaml").write_text(yaml.safe_dump(f, allow_unicode=True), encoding="utf8")
    intl.run([fd], tmp_path / "out", log=lambda *a: None)
    rows = list(csv.DictReader((tmp_path / "out" / "falas-todas.csv").open(encoding="utf8")))
    assert {r["idioma"] for r in rows} == {"pt-BR"} and {r["voz_gemini"] for r in rows} == {"Laomedeia"}


@pytest.mark.parametrize("text", ["Só R$ 50", "Avaliação grátis", "O melhor salão de Orlando", "Resultado garantido", "Últimas vagas", "Antes e depois"])
def test_pt_guards(text):
    assert intl.check_text(text), text


def test_unknown_language_fails_clearly():
    with pytest.raises(intl.FichaError, match="idioma"):
        intl.build_contract(_ficha("us", idioma="es-MX"))


def test_voice_error_does_not_stop_the_batch(tmp_path, monkeypatch):
    from simplicio_video import voice
    fd = tmp_path / "fichas"
    fd.mkdir()
    for s in ("a-us", "b-us"):
        f = _ficha("us", slug=s)
        (fd / f"{s}.yaml").write_text(yaml.safe_dump(f, allow_unicode=True), encoding="utf8")

    def boom(*a, **k):
        raise voice.VoiceError("lines longer than their slot")
    monkeypatch.setattr(intl, "render_mudo", boom)
    res = intl.run([fd], tmp_path / "out", mudo=True, log=lambda *a: None)
    assert [r["status"] for r in res["resultados"]] == ["erro_render", "erro_render"]


def test_preview_audio_has_oversampled_limiter(tmp_path):
    fc = R.preview_filter(10.0, R.preview_font(ROOT), tmp_path, lang="en")
    assert "aresample=192000,alimiter=limit=0.794" in fc
