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
    assert d1["voz"]["provider"] == "local"
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
    (d / "result.json").write_text(json.dumps({"nome": "Brinca Mais", "slug": "brinca-mais", "status": "ok", "timings_s": {"total": 1}}))
    r = P.process({"nome": "Brinca Mais"}, "brinca-mais", tmp_path / "lote", ROOT, P.Fetcher(opener=fake_opener({})))
    assert r["pulado"] and r["status"] == "ok"


def test_preview_filter_has_watermark_and_end_card(tmp_path):
    from simplicio_video import render
    fc = render.preview_filter(16.0, render.preview_font(ROOT), tmp_path)
    assert "scale=540:960" in fc and "rotate=-30*PI/180" in fc and "concat=n=2:v=1:a=1" in fc
    assert (tmp_path / "wm.txt").read_text().count("Prévia • SimpleTI • simpleti.com.br") == 3
    assert (tmp_path / "end1.txt").read_text() == "Vídeo feito pela SimpleTI" and (tmp_path / "end2.txt").read_text() == "simpleti.com.br"
    assert render.PREVIEW["crf"] >= 28 and render.PREVIEW["fps"] == 30


def test_cli_help_mentions_prospect():
    r = run_cli("prospect", "--help")
    assert r.returncode == 0 and "robots.txt" in r.stdout and "LGPD" in r.stdout and "lote.csv" in r.stdout
    assert run_cli("batch", "--help").returncode == 0
    r = run_cli("render", "--help")
    assert "--preview" in r.stdout and "simpleti.com.br" in r.stdout
