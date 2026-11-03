"""Issue #140: o template `news-tech` (skeleton) e o padrão de movimento `news-caption` (proposto) estão registrados.

Confere o que um colaborador lê: a linha do template no README de templates, o padrão no catálogo, os totais no catálogo
e no README de motion, e a licença OFL ao lado das fontes do template. Hermético: só lê arquivos do repo.
"""
from __future__ import annotations

import collections
import json

from conftest import ROOT

DATA = ROOT / "src" / "simplicio_video" / "data"
TEMPLATE = DATA / "templates" / "news-tech"
PATTERN = DATA / "motion" / "patterns" / "news-caption"
CATALOG = DATA / "motion" / "catalog.json"
MOTION_README = DATA / "motion" / "README.md"
TEMPLATES_README = DATA / "templates" / "README.md"
FONTS = TEMPLATE / "composition" / "assets" / "fonts"


def _catalogo() -> dict:
    return json.loads(CATALOG.read_text(encoding="utf8"))


def test_template_news_tech_tem_manifesto_readme_e_composicao():
    assert (TEMPLATE / "template.json").is_file(), "template news-tech sem template.json"
    assert (TEMPLATE / "README.md").is_file(), "template news-tech sem README.md"
    assert (TEMPLATE / "composition" / "index.template.html").is_file(), "news-tech sem a composição"
    assert (TEMPLATE / "composition" / "hyperframes.json").is_file(), "news-tech sem hyperframes.json"


def test_readme_de_templates_lista_o_news_tech_como_skeleton_de_90_s():
    linhas = [ln for ln in TEMPLATES_README.read_text(encoding="utf8").splitlines() if "`news-tech`" in ln]
    assert linhas, "README de templates sem a linha do news-tech"
    assert "skeleton" in linhas[0] and "90 s" in linhas[0], linhas[0]


def test_catalogo_registra_news_caption_como_proposto():
    itens = {p["id"]: p for p in _catalogo()["patterns"]}
    assert "news-caption" in itens, "news-caption fora do catálogo de motion"
    assert itens["news-caption"]["status"] == "proposto", itens["news-caption"]["status"]
    assert (PATTERN / "pattern.json").is_file(), "news-caption sem pattern.json"


def test_catalogo_declara_os_totais_do_que_lista():
    c = _catalogo()
    assert c["count"] == len(c["patterns"]), (c["count"], len(c["patterns"]))
    assert dict(c["by_status"]) == dict(collections.Counter(p["status"] for p in c["patterns"])), c["by_status"]
    assert sum(c["by_status"].values()) == c["count"]


def test_readme_de_motion_repete_a_linha_de_totais_do_catalogo():
    c = _catalogo()
    linha = f"{c['count']} padrões: " + ", ".join(f"{n} {s}" for s, n in c["by_status"].items()) + "."
    assert linha in MOTION_README.read_text(encoding="utf8"), linha


def test_fontes_do_template_tem_a_licenca_ofl_ao_lado():
    for familia, arquivo in (("Anton", "Anton-Regular.ttf"), ("Inter", "Inter.ttf")):
        assert (FONTS / arquivo).is_file(), f"fonte {arquivo} ausente"
        licenca = FONTS / f"OFL-{familia}.txt"
        assert licenca.is_file(), f"licença OFL de {familia} ausente"
        assert "SIL OPEN FONT LICENSE" in licenca.read_text(encoding="utf8").upper(), f"{licenca.name} não é a OFL"
