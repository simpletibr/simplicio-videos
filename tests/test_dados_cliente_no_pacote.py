"""PyPI: nenhum dado de cliente viaja dentro de `src/simplicio_video/` (tudo ali vai para o wheel).

O repositório é público e cada versão do PyPI é imutável: telefone, endereço, @, nome e marca de cliente no pacote
não saem mais. Os projetos e contratos de cliente ficam em `clients/` (fora do pacote) e seguem com os dados deles;
só o que é empacotado usa placeholders genéricos e evidentes.

A lista de termos fica em `dados_cliente_guard.py`, um helper de teste que está fora de src/ e fora do wheel.
Hermético: só lê arquivos do repo.
"""
from __future__ import annotations

import re

import dados_cliente_guard as guarda
from conftest import ROOT

SRC = ROOT / "src" / "simplicio_video"
TEMPLATE_GAMES = SRC / "data" / "templates" / "assistencia-tecnica-games" / "composition" / "index.template.html"
LOCKUP = SRC / "data" / "motion" / "patterns" / "brand-lockup-soft"


def test_pacote_nao_tem_dado_de_cliente():
    achados = guarda.varrer_arvore(SRC)
    assert not achados, f"{len(achados)} achado(s) de dado de cliente em src/simplicio_video:\n" + "\n".join(achados[:40])


def test_guarda_pega_o_que_deve_pegar():
    """O próprio scanner: termos, telefone, e-mail, CPF/CNPJ e nome de arquivo; placeholders passam."""
    sujo = ("Rua Siderópolis\nJardim JOVAIA\n@lothus_odontologia\nwjrinformatica.com.br\n(11) 91234-5678\n"
            "contato: fulano@empresa.com.br\n123.456.789-09\n12.345.678/0001-95\nGuarulhos · SP\n")
    achados = guarda.achados_no_texto(sujo, "x.html")
    for esperado in ("sideropolis", "jovaia", "lothus", "wjrinformatica", "guarulhos", "telefone", "e-mail", "CPF", "CNPJ"):
        assert any(esperado in a for a in achados), (esperado, achados)
    assert guarda.achados_no_texto("(00) 00000-0000\nRua Exemplo, 123 · Cidade\n@suaempresa\nnome@example.com\n", "ok") == []
    assert guarda.achados_no_caminho("data/motion/patterns/logo-wjr/pattern.json")
    assert guarda.achados_no_caminho("data/motion/patterns/service-illustrations-wjr/pattern.json") == []  # id estável de contrato


def test_template_assistencia_tecnica_usa_placeholders_evidentes():
    """O template de assistência técnica nasceu do cliente WJR: telefone, endereço, @, alt e cidade são genéricos."""
    html = TEMPLATE_GAMES.read_text(encoding="utf8")
    assert '"id":"whatsapp","type":"string","label":"WhatsApp","default":"(00) 00000-0000"' in html
    assert '"id":"address","type":"string","label":"Endereço","default":"Rua Exemplo, 123 · Cidade"' in html
    assert '"id":"instagram","type":"string","label":"Instagram","default":"@suaempresa"' in html
    assert '<span data-var-text="whatsapp">(00) 00000-0000</span>' in html
    assert '<div data-var-text="address">Rua Exemplo, 123 · Cidade</div>' in html
    assert '<b data-var-text="instagram">@suaempresa</b>' in html
    assert 'alt="Logo"' in html
    assert "Assistência técnica na sua cidade" in html


def test_lockup_de_marca_usa_placeholders_evidentes():
    """O padrão brand-lockup-soft nasceu do cliente Lothus: nome, subtítulo, @ e cidade são genéricos."""
    import json

    pat = json.loads((LOCKUP / "pattern.json").read_text(encoding="utf8"))
    padroes = {p["id"]: p["default"] for p in pat["params"]}
    assert padroes["name"] == "EMPRESA"
    assert padroes["sub"] == "EXEMPLO"
    assert padroes["handle"] == "@empresa"
    assert padroes["city"] == "Cidade · UF"
    bloco = (LOCKUP / "block.html").read_text(encoding="utf8")
    m = re.search(r"const DEF = (\{.*?\});", bloco)
    assert m, "block.html sem const DEF"
    defs = json.loads(m.group(1))
    assert {k: defs[k] for k in ("name", "sub", "handle", "city")} == {k: padroes[k] for k in ("name", "sub", "handle", "city")}


def test_catalogo_do_motion_nao_cita_projeto_de_cliente():
    """`catalog.json` é gerado de `pattern.json`: a procedência dos padrões não aponta para clients/."""
    texto = (SRC / "data" / "motion" / "catalog.json").read_text(encoding="utf8")
    assert "clients/" not in texto


def test_help_do_cli_usa_exemplos_genericos():
    """`--help` (principal e de cada subcomando) é o que o `pip install` mostra primeiro: nada de cliente real nos exemplos."""
    import argparse

    from simplicio_video import cli

    ap = cli.build_parser()
    subs = next(a for a in ap._actions if isinstance(a, argparse._SubParsersAction)).choices
    textos = {"simplicio-video": ap.format_help(), **{f"simplicio-video {nome}": p.format_help() for nome, p in subs.items()}}
    achados = [a for nome, texto in textos.items() for a in guarda.achados_no_texto(texto, nome)]
    assert not achados, "\n".join(achados)
    assert "clients/<cliente>/<campanha>/contract.yaml" in textos["simplicio-video"]
    assert "clients/<cliente>/<campanha>/contract.yaml" in textos["simplicio-video init"]
