"""simplicio-video prospect: hermetic (no network, no render) - HTML fixtures through a fake opener."""
import csv
import io
import json

import pytest
import yaml

from conftest import ROOT, run_cli
from simplicio_video import contract as ct
from simplicio_video import prospect as P
from simplicio_video.compiler import compile_project, render_template

HOME_HTML = """<!doctype html><html><head><title>Loja Brinca Mais | Brinquedos em Guarulhos</title>
<meta name="description" content="Loja de brinquedos. Fale com a Dra. Maria Souza pelo (11) 91234-5678 ou contato@brinca.com.br">
<meta property="og:image" content="/img/og.jpg"><meta name="theme-color" content="#e63946">
<link rel="stylesheet" href="/style.css"><style>.btn{background:#1d3557;color:#ffffff} .wa{color:#25d366} .x{color:#cf2e2e}</style></head>
<body><img class="site-logo" src="/img/logo.png" alt="Brinca Mais"><h1>Brinquedos para todas as idades</h1>
<a href="https://www.instagram.com/brincamais.gru/">Instagram</a><a href="https://www.instagram.com/p/XYZ/">post</a>
<a href="https://wa.me/5511987654321?text=oi">WhatsApp</a><a href="https://instagram.com.br/brincamais.gru">ig typo</a><script>var x="#123456";</script></body></html>"""


class FakeResp(io.BytesIO):
    def __init__(self, body, url, ctype, status=200):
        super().__init__(body)
        self.status, self._url, self.headers = status, url, {"Content-Type": ctype}

    def geturl(self):
        return self._url

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def fake_opener(pages):
    calls = []

    def op(req, timeout=None):
        url = req.full_url
        calls.append((url, req.headers.get("User-agent")))
        if url not in pages:
            import urllib.error
            raise urllib.error.HTTPError(url, 404, "nf", {}, None)
        body, ctype = pages[url]
        return FakeResp(body.encode() if isinstance(body, str) else body, url, ctype)
    op.calls = calls
    return op


PAGES = {
    "https://brinca.example/robots.txt": ("User-agent: *\nDisallow: /privado/\n", "text/plain"),
    "https://brinca.example/": (HOME_HTML, "text/html; charset=utf-8"),
    "https://brinca.example/style.css": ("h1{color:#e63946} a{color:#e63946} .g{color:#777777}", "text/css"),
    "https://brinca.example/img/logo.png": (b"\x89PNG fake", "image/png"),
    "https://www.instagram.com/robots.txt": ("User-agent: *\nDisallow: /\n", "text/plain"),
}


def test_collect_site_public_data_only(tmp_path):
    f = P.Fetcher(opener=fake_opener(PAGES))
    s = P.collect_site("brinca.example", f, tmp_path / "coleta")
    assert s["status"] == "ok" and s["url"] == "https://brinca.example/"
    assert s["titulo"].startswith("Loja Brinca Mais")
    # LGPD scrub: no person, no phone, no e-mail in stored text
    assert "Maria" not in s["descricao"] and "91234" not in s["descricao"] and "@" not in s["descricao"]
    assert s["cores"][0] == "#e63946" and "#25d366" not in s["cores"] and "#cf2e2e" not in s["cores"] and "#777777" not in s["cores"]
    assert s["instagram"] == ["@brincamais.gru"]
    assert s["whatsapp_links"] == ["+55 (11) 98765-4321"]
    assert s["logo_url"] == "https://brinca.example/img/logo.png" and s["logo_arquivo"] == "logo.png"
    assert (tmp_path / "coleta" / "logo.png").is_file()
    assert s["og_image"] == "https://brinca.example/img/og.jpg"


def test_robots_disallow_and_instagram_never_fetched():
    op = fake_opener({**PAGES, "https://brinca.example/robots.txt": ("User-agent: *\nDisallow: /\n", "text/plain")})
    f = P.Fetcher(opener=op)
    assert P.collect_site("https://brinca.example/", f)["status"] == "robots_disallow"
    ig = P.collect_instagram("@brincamais.gru", f)
    assert ig["status"].startswith("nao_coletado: robots.txt")
    assert not any("instagram.com/brincamais" in u for u, _ in op.calls)  # only robots.txt was read
    assert all(ua and ua.startswith("SimplicioVideoBot/") for _, ua in op.calls)


def test_collect_row_prefers_csv_and_records_sources():
    f = P.Fetcher(opener=fake_opener(PAGES))
    c = P.collect({"nome": "Brinca Mais", "cidade": "Guarulhos-SP", "setor": "loja de brinquedos", "site": "brinca.example",
                   "whatsapp": "(11) 95555-4444"}, f)
    assert c["instagram"]["handle"] == "@brincamais.gru" and c["instagram"]["fonte"].startswith("site:")
    assert c["whatsapp"]["numero"] == "+55 (11) 95555-4444" and c["whatsapp"]["fonte"] == "csv"
    assert c["whatsapp"]["no_site"] == ["+55 (11) 98765-4321"]
    c2 = P.collect({"nome": "Brinca Mais", "site": "brinca.example", "instagram": "@brincamais.gru", "whatsapp": "11 98765-4321"}, f)
    assert c2["instagram"]["fonte"] == "csv (confirmado no link do site)" and c2["whatsapp"]["fonte"] == "csv (confirmado no site)"


@pytest.mark.parametrize("setor,site,expect", [
    ("odontopediatria", "", "odontologia"), ("Buffet infantil", "", "festas"), ("assistência de games e consoles", "", "games"),
    ("escola infantil (berçário)", "", "escola"), ("moda infantil", "", "moda-infantil"), ("", "Loja de brinquedos em Guarulhos", "brinquedos"),
    ("padaria", "Pão quente", "geral")])
def test_sector_rules_are_deterministic(setor, site, expect):
    S = P.load_setores(ROOT, "dia-das-criancas")
    assert P.match_setor(S, setor, site)[0]["id"] == expect


def test_name_split_and_helpers():
    odonto = {"nome_setor": ["clinica", "odontologica", "odontologia"], "sub": "ODONTOLOGIA"}
    assert P.split_name("Hori Clínica Odontológica Guarulhos", odonto, "Guarulhos") == ("HORI", "CLÍNICA ODONTOLÓGICA")
    assert P.split_name("Clínica Prata", odonto, exact=True) == ("CLÍNICA PRATA", "ODONTOLOGIA")
    assert P.split_name("Cometa da Alegria", {"nome_setor": [], "sub": "X"}, exact=True) == ("COMETA", "DA ALEGRIA")
    assert P.city_label("Guarulhos-SP") == "Guarulhos · SP" and P.city_label("Guarulhos") == "Guarulhos"
    assert P.fmt_handle("https://www.instagram.com/ei.maranata/") == "@ei.maranata" and P.fmt_handle("x y") == ""
    assert P.fmt_whatsapp("(11) 9 0000-0000") == "+55 (11) 90000-0000" and P.fmt_whatsapp("123") is None
    assert P.contrast(P.accent_from(["#ffd23f"], "#2f7fc1"), "#ffffff") >= 3.0
    assert P.slugify("Baby & Kids Berçário") == "baby-kids-bercario"


def _coleta(handle="@brincamais.gru", cores=("#e63946",)):
    return {"site": {"titulo": "Brinca Mais", "descricao": "", "cores": list(cores), "status": "ok"},
            "instagram": {"handle": handle, "status": "x", "fonte": "csv"}, "whatsapp": {"numero": "", "fonte": ""}}


def test_contract_is_valid_deterministic_and_has_no_invented_facts(tmp_path):
    row = {"nome": "Brinca Mais Brinquedos", "cidade": "Guarulhos-SP", "setor": "loja de brinquedos", "nome_curto": "Brinca Mais"}
    d1, m1 = P.build_contract(ROOT, "dia-das-criancas", row, _coleta())
    d2, _ = P.build_contract(ROOT, "dia-das-criancas", row, _coleta())
    assert d1 == d2
    p = tmp_path / "p" / "contract.yaml"
    p.parent.mkdir()
    P.write_contract(p, d1, row, m1)
    c = ct.load(p)
    rep = ct.validate(c)
    assert rep.ok, rep.errors
    assert m1["setor"] == "brinquedos" and m1["lockup"] == ["BRINCA MAIS", "BRINQUEDOS"]
    blocks = {m["bloco"]: m for s in d1["cenas"] for m in s["motion"] if m.get("bloco")}
    assert blocks["s2-main"]["padrao"] == "icon-mascot" and blocks["s2-main"]["params"]["icon"] == "gift"
    assert blocks["s4-lockup"]["params"]["handle"] == "@brincamais.gru" and blocks["s4-lockup"]["params"]["city"] == "Guarulhos · SP"
    assert d1["cenas"][3]["fala"]["texto"] == "Com carinho, Brinca Mais."
    assert d1["voz"]["provider"] == "gemini" and d1["voz"]["providers"]["gemini"]["voice"] == "Laomedeia"  # standard v2 = Lothus v02 voice
    assert m1["padrao"] == P.PADRAO and m1["logo"] is None and blocks["s4-lockup"]["params"]["logo"] == ""  # no real logo -> text
    txt = yaml.safe_dump(d1, allow_unicode=True).lower()
    for bad in ("r$", "promo", "desconto", "grátis", "gratis", "%"):
        assert bad not in txt
    assert not [x for x in d1["cenas"][2]["sfx"] if x["id"].startswith("scrub")]  # brushing SFX only for odontologia


def test_odonto_keeps_lothus_blocks_and_voice_variants():
    row = {"nome": "Clínica Sorriso Feliz", "cidade": "Guarulhos-SP", "setor": "odontopediatria"}
    d, m = P.build_contract(ROOT, "dia-das-criancas", row, _coleta(""), variant={"vo3": 1, "vo4": 2})
    blocks = {mm["bloco"]: mm for s in d["cenas"] for mm in s["motion"] if mm.get("bloco")}
    assert blocks["s2-main"]["padrao"] == "tooth-character" and blocks["s3-main"]["padrao"] == "toothbrush-sparkle"
    assert d["cenas"][2]["fala"]["texto"] == "Depois da festa, escova os dentinhos!"
    assert d["cenas"][3]["fala"]["texto"] == "Com carinho, Sorriso."  # shortest name variant
    assert blocks["s4-lockup"]["params"]["handle"] == ""


def test_template_padrao_placeholder_compiles(tmp_path):
    row = {"nome": "Game Zone", "cidade": "Guarulhos-SP", "setor": "games"}
    d, m = P.build_contract(ROOT, "dia-das-criancas", row, _coleta())
    p = tmp_path / "g" / "contract.yaml"
    p.parent.mkdir()
    P.write_contract(p, d, row, m)
    c = ct.load(p)
    assert render_template("{{padrao:s2-main}}|{{padrao:s3-main}}", c, {}) == "icon-mascot|icon-mascot"
    lock = {"provider": "local", "lines": {l["id"]: {"words": [{"w": w, "t": 0.1 * i, "end": 0.1 * i + 0.1} for i, w in enumerate(l["texto"].split())]}
                                           for l in c.lines()}}
    c.data["voz"]["habilitada"] = False
    compile_project(c, tmp_path / "wd", lock)
    html = (tmp_path / "wd" / "index.html").read_text()
    assert 'data-composition-src="compositions/icon-mascot.html"' in html and "{{padrao" not in html and "{{vars:s" not in html
    assert (tmp_path / "wd" / "compositions" / "icon-mascot.html").is_file()


def test_batch_so_contrato_report_and_resume(tmp_path, monkeypatch):
    lst = tmp_path / "lista.csv"
    lst.write_text("nome,cidade,setor,site,instagram,whatsapp,fontes\n"
                   "Brinca Mais,Guarulhos-SP,loja de brinquedos,brinca.example,,,busca web\n"
                   "Sem Site,Guarulhos-SP,buffet infantil,,@semsite,(11) 93333-2222,csv\n", encoding="utf8")
    f = P.Fetcher(opener=fake_opener(PAGES))
    s = P.run_batch(lst, out=tmp_path / "lote", render=False, fetcher=f, log=lambda *_: None)
    assert s["linhas"] == 2 and s["erros"] == 0
    rows = list(csv.DictReader(open(tmp_path / "lote" / "lote.csv", encoding="utf8")))
    assert [r["slug"] for r in rows] == ["brinca-mais", "sem-site"]
    assert rows[0]["instagram"] == "@brincamais.gru" and rows[0]["whatsapp"] == "+55 (11) 98765-4321"
    assert rows[1]["site_status"] == "sem_site" and rows[1]["instagram"] == "@semsite" and rows[1]["status"] == "contrato"
    for r in rows:
        assert (tmp_path / "lote" / r["slug"] / "contract.yaml").is_file() and (tmp_path / "lote" / r["slug"] / "coleta.json").is_file()
    # resume: an existing ok preview is skipped without touching the network
    d = tmp_path / "lote" / "brinca-mais"
    (d / "preview.mp4").write_bytes(b"x")
    (d / "result.json").write_text(json.dumps({"nome": "Brinca Mais", "slug": "brinca-mais", "status": "ok", "padrao": P.PADRAO,
                                               "timings_s": {"total": 1}}))
    r = P.process({"nome": "Brinca Mais"}, "brinca-mais", tmp_path / "lote", ROOT, P.Fetcher(opener=fake_opener({})))
    assert r["pulado"] and r["status"] == "ok"
    # a preview of an older standard (v1 = no "padrao") is NOT skipped: it is redone with the current standard
    (d / "result.json").write_text(json.dumps({"nome": "Brinca Mais", "slug": "brinca-mais", "status": "ok", "timings_s": {"total": 1}}))
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    r = P.process({"nome": "Brinca Mais"}, "brinca-mais", tmp_path / "lote", ROOT, P.Fetcher(opener=fake_opener({})))
    assert not r.get("pulado") and r["status"] == "aguardando_voz" and (d / "preview.mp4").read_bytes() == b"x"


def test_preview_filter_has_watermark_and_end_card(tmp_path):
    from simplicio_video import render
    fc = render.preview_filter(16.0, render.preview_font(ROOT), tmp_path)
    assert "scale=540:960" in fc and "rotate=-30*PI/180" in fc and "concat=n=2:v=1:a=1" in fc
    assert (tmp_path / "wm.txt").read_text().count("Prévia • Wesley Simplicio • @wesleysimplicio") == 3
    assert (tmp_path / "end1.txt").read_text() == "Vídeo feito por Wesley Simplicio" and (tmp_path / "end2.txt").read_text() == "@wesleysimplicio"
    assert (tmp_path / "badge.txt").read_text() == "PRÉVIA · @wesleysimplicio"
    assert render.PREVIEW["crf"] >= 28 and render.PREVIEW["fps"] == 30


def test_cli_render_help_keeps_preview():  # o subcomando prospect saiu do motor (#77); o --preview do render fica
    r = run_cli("render", "--help")
    assert "--preview" in r.stdout and "@wesleysimplicio" in r.stdout and "simpleti" not in r.stdout.lower()


# ------------------------------------------------------------------ standard v2 (pilot All Prime, 30/09/2026)
def _png(tmp_path, w=240, h=240, name="logo-src.png"):
    import subprocess
    out = tmp_path / name
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"color=c=0xb87333:s={w}x{h}", "-frames:v", "1", str(out)], check=True)
    return out.read_bytes()


def test_standard_v2_is_the_default_lothus_pacing_laomedeia_voice_same_track():
    base = yaml.safe_load((ROOT / "templates/sazonal-dia-das-criancas/contract.base.yaml").read_text(encoding="utf8"))
    lothus = yaml.safe_load((ROOT / "clients/lothus-odontologia/video-01-dia-das-criancas/contract.yaml").read_text(encoding="utf8"))
    v = base["voz"]
    assert P.DEFAULT_PROVIDER == "gemini" and v["provider"] == "gemini" and v["voice"] == "Laomedeia"
    assert v["providers"]["gemini"] == {**v["providers"]["gemini"], "model": "gemini-3.8-flash-tts", "voice": "Laomedeia"}
    festa = ("Voz feminina brasileira bem animada, de festa infantil: sorrindo, energia alta, vibrante e calorosa, ritmo rápido, "
             "português do Brasil, sem gritar e sem voz infantilizada.")
    assert v["estilo"] == v["providers"]["gemini"]["estilo"] == festa  # style prompt requested by Wesley (30/09/2026)
    assert v["voice"] == lothus["voz"]["voice"] == lothus["voz"]["providers"]["gemini"]["voice"]  # exactly the Lothus v02 voice
    assert "Achernar" in v["providers"]["gemini"]["alternativas"] and "Achernar" in lothus["voz"]["providers"]["gemini"]["alternativas"]
    assert base["trilha"] == lothus["trilha"]  # same festive 128 BPM track as Lothus v02
    motion = [m for s in base["cenas"] for m in s["motion"]]
    fx = [m for m in motion if m["padrao"] == "fx-transition"]
    assert len(fx) == len(base["cenas"]) and all(6 <= m["params"]["frames"] <= 10 for m in fx)  # fast cuts, 6-10 frames
    assert sum(m["padrao"] in ("balloons-confetti", "beat-burst") for m in motion) >= 6  # confetti in every scene
    words = [m for m in motion if m["padrao"] == "kinetic-words"]
    assert [m["params"]["times"] for m in words] == [f"{{{{words:vo{i}}}}}" for i in range(1, 5)]  # word by word, on the voice


def test_real_logo_from_site_goes_into_the_lockup(tmp_path):
    pages = {**PAGES, "https://brinca.example/img/logo.png": (_png(tmp_path, 400, 160), "image/png")}
    f = P.Fetcher(opener=fake_opener(pages))
    pdir = tmp_path / "brinca-mais"
    row = {"nome": "Brinca Mais", "cidade": "Guarulhos-SP", "setor": "loja de brinquedos", "site": "brinca.example"}
    c = P.collect(row, f, pdir / "coleta")
    lg = c["logo"]
    assert lg["status"] == "ok" and lg["origem"] == "site" and lg["url"] == "https://brinca.example/img/logo.png"
    assert lg["arquivo"] == "logo.png" and (lg["largura"], lg["altura"]) == (400, 160) and (pdir / "coleta" / "logo.png").is_file()
    d, m = P.build_contract(ROOT, "dia-das-criancas", row, c)
    lp = next(mm["params"] for s in d["cenas"] for mm in s["motion"] if mm.get("bloco") == "s4-lockup")
    assert d["marca"]["logo"] == {"arquivo": "coleta/logo.png", "destino": "assets/client/logo.png"}
    assert lp["logo"] == "assets/client/logo.png" and lp["logo_round"] == 0 and lp["logo_size"] == 330  # wide: not cropped
    assert m["logo"]["origem"] == "site"
    P.write_contract(pdir / "contract.yaml", d, row, m)
    rep = ct.validate(ct.load(pdir / "contract.yaml"))
    assert rep.ok, rep.errors
    cc = ct.load(pdir / "contract.yaml")
    lock = {"provider": "gemini", "lines": {l["id"]: {"words": [{"w": w, "t": 0.1 * i, "end": 0.1 * i + 0.1}
                                                               for i, w in enumerate(l["texto"].split())]} for l in cc.lines()}}
    cc.data["voz"]["habilitada"] = False
    compile_project(cc, tmp_path / "wd", lock)
    assert (tmp_path / "wd" / "assets/client/logo.png").is_file()


def test_logo_is_never_invented(tmp_path):
    # undecodable/too small file = no logo; Instagram avatar never fetched when robots.txt disallows
    tiny = _png(tmp_path, 32, 32, "tiny.png")
    pages = {**PAGES, "https://brinca.example/img/logo.png": (tiny, "image/png")}
    op = fake_opener(pages)
    c = P.collect({"nome": "Brinca Mais", "site": "brinca.example"}, P.Fetcher(opener=op), tmp_path / "x" / "coleta")
    assert c["logo"]["arquivo"] is None and c["logo"]["status"].startswith("nao_encontrado")
    assert not any("cdninstagram" in u for u, _ in op.calls)
    d, m = P.build_contract(ROOT, "dia-das-criancas", {"nome": "Brinca Mais"}, c)
    assert d["marca"]["logo"] is None and m["logo"] is None


def test_logo_from_csv_column_hand_picked_from_instagram(tmp_path):
    src = tmp_path / "avatar.jpg"
    src.write_bytes(_png(tmp_path, 100, 100))
    row = {"nome": "All Prime Odontologia", "setor": "odontologia", "logo": str(src),
           "logo_fonte": "https://www.instagram.com/aprimeodonto/ (foto de perfil pública)"}
    c = P.collect(row, P.Fetcher(opener=fake_opener(PAGES)), tmp_path / "ap" / "coleta")
    assert c["logo"]["origem"] == "csv" and c["logo"]["fonte"].startswith("https://www.instagram.com/aprimeodonto/")
    d, m = P.build_contract(ROOT, "dia-das-criancas", row, c)
    lp = next(mm["params"] for s in d["cenas"] for mm in s["motion"] if mm.get("bloco") == "s4-lockup")
    assert lp["logo_round"] == 1 and lp["logo"] == "assets/client/logo.png" and lp["logo_size"] == 440


def test_voice_waits_for_laomedeia_takes_without_api_key(tmp_path, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    pdir = tmp_path / "x"
    pdir.mkdir()
    with pytest.raises(P.AguardandoVoz):
        P.resolve_provider(pdir, "gemini")
    assert P.resolve_provider(pdir, "local") == "local"
    ext = pdir / "assets/audio/vo/external"
    ext.mkdir(parents=True)
    for i in range(1, 5):
        (ext / f"line-{i:02d}.wav").write_bytes(b"RIFF")
    assert P.resolve_provider(pdir, "gemini") == "file"
    monkeypatch.setenv("GEMINI_API_KEY", "test")
    assert P.resolve_provider(tmp_path, "gemini") == "gemini"


def test_waiting_row_writes_the_exact_lines_and_only_touches_selected_rows(tmp_path, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    lst = tmp_path / "lista.csv"
    lst.write_text("nome,cidade,setor,instagram\nSorriso Kids,Guarulhos-SP,odontopediatria,@sorrisokids\n"
                   "Outra Loja,Guarulhos-SP,loja de brinquedos,@outra\n", encoding="utf8")
    s = P.run_batch(lst, out=tmp_path / "lote", fetcher=P.Fetcher(opener=fake_opener(PAGES)), only=["sorriso-kids"],
                    log=lambda *_: None)
    assert s["aguardando_voz"] == 1 and s["erros"] == 0 and s["padrao"] == P.PADRAO
    sheet = (tmp_path / "lote" / "sorriso-kids" / "falas-gemini.md").read_text(encoding="utf8")
    assert "Laomedeia" in sheet and "Achernar" in sheet and "gemini-3.8-flash-tts" in sheet and "Com carinho, Sorriso Kids." in sheet and "line-04.wav" in sheet
    assert not (tmp_path / "lote" / "outra-loja").exists()  # --only: the other company is not touched
    rows = list(csv.DictReader(open(tmp_path / "lote" / "lote.csv", encoding="utf8")))
    assert [r["status"] for r in rows] == ["aguardando_voz", "nao_processado"]


def test_site_logo_served_as_image_jpg_is_kept():
    """Loja Integrada's CDN answers `image/jpg` (non-standard): the real logo must still be saved (Happily, 30/09/2026)."""
    assert P.IMG_EXT["image/jpg"] == ".jpg"
    import inspect
    assert "IMG_EXT.get(" in inspect.getsource(P.collect_site)
