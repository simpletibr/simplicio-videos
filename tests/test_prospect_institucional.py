"""Institutional sector templates (odontologia, estética, advocacia) + sector routing of `simplicio-video prospect`. Hermetic."""
import json
import re

import pytest
import yaml

from conftest import ROOT
DATA = ROOT / "src" / "simplicio_video" / "data"  # esquemas, templates e motion: dentro do pacote (#74)
from simplicio_video import contract as ct  # noqa: E402
from simplicio_video import prospect as P  # noqa: E402
from simplicio_video.compiler import compile_project  # noqa: E402
from test_prospect import PAGES, _coleta, _png, fake_opener  # noqa: E402

INST = ["institucional-odontologia", "institucional-estetica", "institucional-advocacia"]
ALL = INST + ["sazonal-dia-das-criancas"]
# claims that break CFO/OAB/consumer rules in advertising (and our "no invented facts" rule)
BANNED = re.compile(r"melhor|garant|ganhe|resultado|gr[aá]tis|pre[cç]o|promo|desconto|r\$|%|vit[oó]ria|especialista|causa ganha|n[ºo°] ?1|"
                    r"l[ií]der|imperd[ií]vel|oferta|antes e depois|perfeit", re.I)


def _base(tid):
    return yaml.safe_load((DATA / "templates" / tid / "contract.base.yaml").read_text(encoding="utf8"))


def _texts(tid):
    """Every spoken/written line of a template: base contract falas/tela/kinetic lines/tagline + setores.json lines."""
    b, s = _base(tid), json.loads((DATA / "templates" / tid / "setores.json").read_text(encoding="utf8"))
    out = [b["campanha"]["titulo"]]
    for c in b["cenas"]:
        out += [c["fala"]["texto"], *c.get("tela", [])]
        out += [m["params"][k] for m in c["motion"] for k in ("lines", "tagline", "label") if isinstance(m.get("params", {}).get(k), str)]
    camp = s["campanha"]
    out += [camp["tagline"], camp["titulo"], camp["fala4"], camp["linhas4"], *camp["vo4"]]
    for st in s["setores"] + [s["padrao"]]:
        out += st["vo3"] + st["lines3"]
    return out


def _row(setor, nome="Empresa Teste", **kw):
    return {"nome": nome, "cidade": "Guarulhos-SP", "setor": setor, **kw}


@pytest.mark.parametrize("setor,campanha,tid", [
    ("odontologia", "auto", "sazonal-dia-das-criancas"),            # odonto keeps the kids hook while the season runs
    ("odontologia", "institucional", "institucional-odontologia"),
    ("Clínica Odontológica", "institucional", "institucional-odontologia"),
    ("advocacia", "auto", "institucional-advocacia"),
    ("Escritório de Advocacia", "dia-das-criancas", "institucional-advocacia"),  # law firms never get the festive template
    ("direito de família", "auto", "institucional-advocacia"),
    ("estética", "auto", "institucional-estetica"),
    ("Harmonização facial", "institucional", "institucional-estetica"),
    ("odontologia estética", "institucional", "institucional-odontologia"),  # dental first
    ("escola infantil", "auto", "sazonal-dia-das-criancas"),
    ("loja de brinquedos", "dia-das-criancas", "sazonal-dia-das-criancas"),
    ("", "auto", "sazonal-dia-das-criancas"),
])
def test_routing_by_sector_column(setor, campanha, tid):
    assert P.route_template(ROOT, campanha, _row(setor))[0] == tid


def test_routing_overrides_and_errors():
    assert P.route_template(ROOT, "auto", _row("advocacia", template="institucional-estetica")) == ("institucional-estetica", "csv:template")
    assert P.route_template(ROOT, "auto", _row("odontologia", campanha="institucional"))[0] == "institucional-odontologia"
    assert P.route_template(ROOT, "auto", _row("", ), "Escritório de advocacia em Guarulhos")[0] == "institucional-advocacia"  # site text
    with pytest.raises(ValueError):
        P.route_template(ROOT, "institucional", _row("buffet infantil"))  # no institutional template for kids party venues
    with pytest.raises(SystemExit):
        P.route_template(ROOT, "auto", _row("odontologia", template="nao-existe"))


def test_lote2_sector_values_all_route():
    for setor, tid in (("odontologia", "institucional-odontologia"), ("advocacia", "institucional-advocacia"), ("estética", "institucional-estetica")):
        assert P.route_template(ROOT, "institucional", _row(setor))[0] == tid


def test_logo_url_column_is_an_alias_of_logo(tmp_path):
    src = tmp_path / "logo.png"
    src.write_bytes(_png(tmp_path, 120, 120))
    lst = tmp_path / "lista.csv"
    lst.write_text(f"nome,setor,logo_url\nAlfa Advocacia,advocacia,{src}\nBeta Estética,estética,logos/beta.png\n", encoding="utf8")
    rows = P.read_csv(lst)
    assert rows[0]["logo"] == str(src) and rows[1]["logo"] == "logos/beta.png"
    c = P.collect(rows[0], P.Fetcher(opener=fake_opener(PAGES)), tmp_path / "a" / "coleta")
    assert c["logo"]["origem"] == "csv" and c["logo"]["arquivo"] == "logo.png"


@pytest.mark.parametrize("tid", INST)
def test_institutional_template_builds_validates_and_compiles(tmp_path, tid):
    setor = {"institucional-odontologia": "odontologia", "institucional-estetica": "estética", "institucional-advocacia": "advocacia"}[tid]
    row = _row(setor, "Silva & Souza Advogados Associados" if "advocacia" in tid else "Clínica Bella Estética", oab="OAB/SP 12.345")
    src = tmp_path / "logo.png"
    src.write_bytes(_png(tmp_path, 200, 200))
    row["logo"] = str(src)
    pdir = tmp_path / "p"
    col = P.collect(row, P.Fetcher(opener=fake_opener(PAGES)), pdir / "coleta")
    col["instagram"]["handle"] = "@empresa"
    d, m = P.build_contract(ROOT, tid, row, col)
    assert m["template"] == tid and d["template"] == tid and d["voz"]["voice"] == "Laomedeia"
    assert "drive" not in d  # a entrega fica fora do motor (issue #75)
    lp = next(mm["params"] for s in d["cenas"] for mm in s["motion"] if mm.get("bloco") == "s4-lockup")
    assert lp["logo"] == "assets/client/logo.png" and lp["logo_round"] == 1
    P.write_contract(pdir / "contract.yaml", d, row, m)
    rep = ct.validate(ct.load(pdir / "contract.yaml"))
    assert rep.ok, rep.errors
    c = ct.load(pdir / "contract.yaml")
    assert abs(sum(s["duracao_s"] for s in c.data["cenas"]) - 16) < 1e-6
    lock = {"provider": "gemini", "lines": {l["id"]: {"words": [{"w": w, "t": 0.1 * i, "end": 0.1 * i + 0.1} for i, w in enumerate(l["texto"].split())]}
                                            for l in c.lines()}}
    c.data["voz"]["habilitada"] = False
    compile_project(c, tmp_path / "wd", lock)
    html = (tmp_path / "wd" / "index.html").read_text()
    assert "{{" not in html.split("-->", 1)[1] and (tmp_path / "wd" / "assets/client/logo.png").is_file()
    spec = json.loads((tmp_path / "wd" / "spec.json").read_text())
    assert spec["audio"]["music"]["style"] == "institucional"
    if "advocacia" in tid:
        assert lp["city"].startswith("OAB/SP 12.345") and lp["name"] == "SILVA & SOUZA" and lp["sub"] == "ADVOGADOS ASSOCIADOS"
        assert d["cenas"][3]["fala"]["texto"] == "Silva & Souza Advogados Associados."
    else:
        assert d["cenas"][3]["fala"]["texto"] == "Conheça Clínica Bella Estética." or d["cenas"][3]["fala"]["texto"].startswith("Conheça ")


@pytest.mark.parametrize("tid", INST)
def test_institutional_texts_make_no_claims(tid):
    bad = [t for t in _texts(tid) if BANNED.search(t)]
    assert not bad, bad


@pytest.mark.parametrize("tid", ALL)
def test_every_template_uses_the_laomedeia_standard_voice_and_fast_cuts(tid):
    b = _base(tid)
    v = b["voz"]
    assert v["provider"] == "gemini" and v["voice"] == v["providers"]["gemini"]["voice"] == "Laomedeia"
    assert v["providers"]["gemini"]["model"] == "gemini-3.8-flash-tts" and "Achernar" in v["providers"]["gemini"]["alternativas"]
    assert v["estilo"] == v["providers"]["gemini"]["estilo"]
    fx = [m for s in b["cenas"] for m in s["motion"] if m["padrao"] == "fx-transition"]
    assert len(fx) == 4 and all(6 <= m["params"]["frames"] <= 10 for m in fx)
    words = [m for s in b["cenas"] for m in s["motion"] if m["padrao"] == "kinetic-words"]
    assert [m["params"]["times"] for m in words] == [f"{{{{words:vo{i}}}}}" for i in range(1, 5)]
    tj = json.loads((DATA / "templates" / tid / "template.json").read_text(encoding="utf8"))
    assert tj["voz"]["gemini_voz"] == "Laomedeia" and tj["composicao"]["cenas"] == ["s1", "s2", "s3", "s4"]
    blocos = {m["bloco"] for s in b["cenas"] for m in s["motion"]}
    assert blocos == set(tj["composicao"]["blocos"])


def test_institutional_templates_have_no_confetti_and_advocacia_is_sober():
    for tid in INST:
        motion = [m for s in _base(tid)["cenas"] for m in s["motion"]]
        assert not any(m["padrao"] == "balloons-confetti" for m in motion)
        assert all(m["params"]["confetti"] == 0 for m in motion if m["padrao"] == "beat-burst")
    b = _base("institucional-advocacia")
    motion = [m for s in b["cenas"] for m in s["motion"]]
    pats = {m["padrao"] for m in motion}
    assert pats <= {"bg-parallax", "fx-transition", "line-accent", "kinetic-words", "brand-lockup-soft"}
    assert all(m["params"]["mode"] == "calm" and m["params"]["font"] == "Inter" for m in motion if m["padrao"] == "kinetic-words")
    assert all(m["params"]["kind"] == "flash" and m["params"]["flash_max"] <= 0.35 for m in motion if m["padrao"] == "fx-transition")
    assert next(m["params"] for m in motion if m["padrao"] == "bg-parallax")["shapes"] == 0  # no floating stars/shapes
    lk = next(m["params"] for m in motion if m["padrao"] == "brand-lockup-soft")
    assert lk["dots"] == 0 and lk["bpm"] == 0 and lk["tag_font"] == "Inter"
    assert b["trilha"]["music"]["style"] == "institucional" and b["trilha"]["music"]["drums"] == 0
    assert {x["tipo"] for s in b["cenas"] for x in s["sfx"]} <= {"whoosh"}
    est = b["voz"]["estilo"]
    assert "calmo" in est and "sem entusiasmo publicitário" in est
    html = (DATA / "templates/institucional-advocacia/composition/index.template.html").read_text()
    cam = html.split("<script>")[-1]
    assert "elastic.out" not in cam and "whipL" not in cam and "rotation" not in cam and "z:" not in cam  # no punch/whip/shake


def test_advocacia_without_oab_is_not_rendered_but_gets_contract_and_lines(tmp_path, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    lst = tmp_path / "lista.csv"
    lst.write_text("nome,cidade,setor\nAlfa Advocacia,Guarulhos-SP,advocacia\nBella Estética,Guarulhos-SP,estética\n", encoding="utf8")
    s = P.run_batch(lst, out=tmp_path / "lote", fetcher=P.Fetcher(opener=fake_opener(PAGES)), log=lambda *_: None)
    r = json.loads((tmp_path / "lote" / "alfa-advocacia" / "result.json").read_text())
    assert r["status"] == "aguardando_oab" and "art. 44" in r["motivo"] and r["template"] == "institucional-advocacia"
    assert (tmp_path / "lote" / "alfa-advocacia" / "falas-gemini.md").is_file()
    assert json.loads((tmp_path / "lote" / "bella-estetica" / "result.json").read_text())["status"] == "aguardando_voz"
    assert s["aguardando_dados"] == 1 and s["aguardando_voz"] == 1 and s["templates"] == {"institucional-advocacia": 1, "institucional-estetica": 1}
    rep = (tmp_path / "lote" / "lote.csv").read_text()
    assert "institucional-advocacia" in rep and "template" in rep.splitlines()[0]


def test_so_contrato_writes_lines_sheet_without_voice_or_render(tmp_path, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    lst = tmp_path / "lista.csv"
    lst.write_text("nome,cidade,setor,oab\nAlfa Advocacia,Guarulhos-SP,advocacia,OAB/SP 99.999\n", encoding="utf8")
    s = P.run_batch(lst, out=tmp_path / "lote", render=False, fetcher=P.Fetcher(opener=fake_opener(PAGES)), log=lambda *_: None)
    pdir = tmp_path / "lote" / "alfa-advocacia"
    sheet = (pdir / "falas-gemini.md").read_text()
    assert s["contratos"] == 1 and not (pdir / "preview.mp4").exists() and not (pdir / "timing.lock.json").exists()
    assert "Laomedeia" in sheet and "Achernar" in sheet and "calmo" in sheet
    assert "Tem dúvidas sobre os seus direitos?" in sheet and "Alfa Advocacia." in sheet
    d = yaml.safe_load((pdir / "contract.yaml").read_text())
    lp = next(m["params"] for s_ in d["cenas"] for m in s_["motion"] if m.get("bloco") == "s4-lockup")
    assert lp["city"] == "OAB/SP 99.999 · Guarulhos · SP"


def test_takes_origin_is_recorded(tmp_path):
    ext = tmp_path / "assets/audio/vo/external"
    ext.mkdir(parents=True)
    (ext / "ORIGEM.txt").write_text("Gemini 3.8 Flash TTS, voz Laomedeia,\n conta x@y, 30/09/2026\n")
    assert P.takes_origin(tmp_path) == "Gemini 3.8 Flash TTS, voz Laomedeia, conta x@y, 30/09/2026"
    d, _ = P.build_contract(ROOT, "dia-das-criancas", {"nome": "Sorriso Kids", "setor": "odontologia"}, _coleta())
    d["voz"]["provider"] = "file"
    d["voz"]["providers"]["file"]["origem"] = P.takes_origin(tmp_path)
    P.write_licenses(tmp_path, d, {"logo": {"arquivo": "logo.png", "fonte": "https://instagram.com/x", "origem": "csv"}})
    lic = (tmp_path / "assets/audio/LICENSES.md").read_text()
    assert "voz Laomedeia" in lic and "conta x@y" in lic and "Gemini API Additional Terms" in lic and "festive" in lic


def test_older_preview_survives_a_waiting_run(tmp_path, monkeypatch):
    """A v1 preview followed by an aguardando_voz run must still be kept as preview.v1.mp4 when v2 renders."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    pdir = tmp_path / "lote" / "sorriso-kids"
    pdir.mkdir(parents=True)
    (pdir / "preview.mp4").write_bytes(b"v1")
    (pdir / "result.json").write_text(json.dumps({"status": "ok", "padrao": "v1"}))
    r = P.process({"nome": "Sorriso Kids", "setor": "odontologia"}, "sorriso-kids", tmp_path / "lote", ROOT, P.Fetcher(opener=fake_opener(PAGES)),
                  log=lambda *_: None)
    assert r["status"] == "aguardando_voz" and r["preview_padrao"] == "v1"
    assert json.loads((pdir / "result.json").read_text())["preview_padrao"] == "v1"


def _rgba_png(tmp_path, name, w, h, color):
    import subprocess
    out = tmp_path / name
    r, g, b = color
    a = f"if(between(X,{w // 4},{3 * w // 4})*between(Y,{h // 4},{3 * h // 4}),255,0)"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"color=c=black:s={w}x{h},format=rgba",
                    "-vf", f"geq=r='{r}':g='{g}':b='{b}':a='{a}'", "-frames:v", "1", str(out)], check=True)
    return out


def test_light_transparent_logo_gets_a_dark_plate_and_wide_wordmarks_are_kept(tmp_path):
    white = _rgba_png(tmp_path, "white.png", 240, 240, (255, 255, 255))
    row = {"nome": "Alfa Advocacia", "setor": "advocacia", "logo": str(white), "oab": "OAB/SP 1"}
    c = P.collect(row, P.Fetcher(opener=fake_opener(PAGES)), tmp_path / "a" / "coleta")
    assert c["logo"]["claro"] is True
    d, _ = P.build_contract(ROOT, "institucional-advocacia", row, c)
    lp = next(m["params"] for s in d["cenas"] for m in s["motion"] if m.get("bloco") == "s4-lockup")
    assert lp["logo_bg"] == d["marca"]["paleta"]["ink"]
    navy = _rgba_png(tmp_path, "navy.png", 300, 27, (31, 42, 68))  # 300x27 wordmark: real logo, not "too small"
    c2 = P.collect({**row, "logo": str(navy)}, P.Fetcher(opener=fake_opener(PAGES)), tmp_path / "b" / "coleta")
    assert c2["logo"]["arquivo"] == "logo.png" and c2["logo"]["claro"] is False
    d2, _ = P.build_contract(ROOT, "institucional-advocacia", {**row, "logo": str(navy)}, c2)
    assert next(m["params"] for s in d2["cenas"] for m in s["motion"] if m.get("bloco") == "s4-lockup")["logo_bg"] == ""


def test_non_ascii_logo_url_is_percent_encoded():
    seen = []

    def op(req, timeout=None):
        seen.append(req.full_url)
        import urllib.error
        raise urllib.error.HTTPError(req.full_url, 404, "nf", {}, None)
    P.Fetcher(opener=op).get("https://x.example/wp-content/logo-250-×-150-px.png")
    assert seen == ["https://x.example/wp-content/logo-250-%C3%97-150-px.png"]


# --- sign-off layout guard (All Prime v02 QA, 30/09/2026: "Com carinho, All Prime." over "@aprimeodonto / Guarulhos · SP") ---
from simplicio_video.layout import endcard_collisions  # noqa: E402


def test_guard_catches_the_v02_end_card_collision():
    v02 = [{"id": "s4", "motion": [
        {"padrao": "brand-lockup-soft", "bloco": "s4-lockup", "params": {"handle": "@x", "city": "Guarulhos · SP"}},
        {"padrao": "kinetic-words", "bloco": "s4-words", "params": {"lines": "Com carinho,|All Prime.", "size": 92, "y": 1500}}]}]
    assert endcard_collisions(v02)


@pytest.mark.parametrize("tid", ALL)
def test_sign_off_words_never_reach_the_handle_city_block(tid):
    assert endcard_collisions(_base(tid)["cenas"]) == []


def test_build_contract_refuses_a_colliding_end_card(tmp_path, monkeypatch):
    monkeypatch.setattr(P, "endcard_collisions", lambda scenes: ["s4/s4-words: colisão"])
    row = {"nome": "Clínica Sorriso", "cidade": "Guarulhos · SP", "setor": "odontologia"}
    with pytest.raises(ValueError, match="layout do fechamento"):
        P.build_contract(ROOT, "institucional-odontologia", row, _coleta())


# --- branding (Wesley, 30/09/2026): previews say "Wesley Simplicio / @wesleysimplicio", never SimpleTI/simpleti.com.br ---
OLD_BRAND = re.compile(r"simple\s*ti|simpleti\.com\.br", re.I)


def test_preview_watermark_and_end_card_have_no_simpleti(tmp_path):
    from simplicio_video import render
    assert P.MARCA_PREVIA["dagua"] == "Prévia • Wesley Simplicio • @wesleysimplicio"
    render.preview_filter(16.0, render.preview_font(ROOT), tmp_path, marca=P.MARCA_PREVIA, chrome=P.SELO_PREVIA)
    for f in ("wm", "badge", "end1", "end2", "end3"):
        assert not OLD_BRAND.search((tmp_path / f"{f}.txt").read_text()), f
    assert "@wesleysimplicio" in (tmp_path / "end2.txt").read_text()
    assert all(not OLD_BRAND.search(str(v)) for v in render.PREVIEW.values())
    assert all(not OLD_BRAND.search(str(v)) for v in (P.MARCA_PREVIA, P.SELO_PREVIA))


@pytest.mark.parametrize("tid", ALL)
def test_no_template_output_mentions_simpleti(tid, tmp_path):
    """Whole generated contract (end card lockup, tela, objetivo) of every prospect template."""
    row = {"nome": "Clínica Sorriso", "cidade": "Guarulhos · SP", "setor": "odontologia", "oab": "OAB/SP 123.456"}
    d, meta = P.build_contract(ROOT, tid, row, _coleta())
    assert not OLD_BRAND.search(yaml.safe_dump(d, allow_unicode=True)), tid
    assert not OLD_BRAND.search((DATA / "templates" / tid / "composition" / "index.template.html").read_text(encoding="utf8"))


# --- batch voice via the Gemini API: bounded regeneration, never speed-up (mock server, no network) ---
def _mock_server(overlong_first, log):
    import socket
    import threading
    from simplicio_video import mock_gemini
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    threading.Thread(target=mock_gemini.serve, args=(port, overlong_first, str(log)), daemon=True).start()
    import time
    for _ in range(50):
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
            break
        except OSError:
            time.sleep(0.05)
    return f"http://127.0.0.1:{port}/v1beta"


def test_gemini_overlong_take_is_regenerated_not_sped_up(tmp_path, monkeypatch):
    log = tmp_path / "mock.jsonl"
    monkeypatch.setenv("SIMPLICIO_GEMINI_BASE", _mock_server(1, log))
    monkeypatch.setenv("GEMINI_API_KEY", "mock-not-a-key")
    pdir = tmp_path / "sorriso"
    pdir.mkdir()
    row = {"nome": "Clínica Sorriso", "cidade": "Guarulhos-SP", "setor": "odontologia"}
    msgs = []
    d, meta = P._voice_fit(pdir, ROOT, "sazonal-dia-das-criancas", row, _coleta(), "gemini", msgs.append)
    calls = [json.loads(x) for x in log.read_text().splitlines()]
    assert calls[0]["overlong"] and calls[0]["text"] == d["cenas"][0]["fala"]["texto"]
    assert len(calls) == 5 and calls[4]["text"] == calls[0]["text"]  # 4 lines + 1 regeneration of vo1
    assert {c["voice"] for c in calls} == {"Laomedeia"} and {c["model"] for c in calls} == {"gemini-3.8-flash-tts"}
    assert all("animada" in c["style"] for c in calls)
    assert meta["voz_regeneradas"] == {"vo1@0": 1} and any("nova leva" in m for m in msgs)
    lock = json.loads((pdir / "timing.lock.json").read_text())
    assert all(v["fits"] for v in lock["lines"].values())
