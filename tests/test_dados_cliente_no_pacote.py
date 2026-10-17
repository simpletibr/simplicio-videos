"""PyPI: nenhum dado de cliente viaja dentro de `src/simplicio_video/` (tudo ali vai para o wheel).

O repositório é público e cada versão do PyPI é imutável: telefone, endereço, @, nome e marca de cliente no pacote
não saem mais. Os projetos e contratos de cliente ficam em `clients/` (fora do pacote) e seguem com os dados deles;
só o que é empacotado usa placeholders genéricos e evidentes.

A lista de termos fica em `dados_cliente_guard.py`, um helper de teste que está fora de src/ e fora do wheel.
Hermético: só lê arquivos do repo.
"""
from __future__ import annotations

import hashlib
import json
import re
import struct
import unicodedata
import zlib

import pytest

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
    assert padroes["name"] == "MARCA"
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


def test_arquivos_da_raiz_que_vao_no_sdist_nao_citam_cliente():
    """CHANGELOG, NOTICE, LICENSE, PYPI.md e pyproject.toml entram no sdist, que é imutável no PyPI: mesma guarda de src/."""
    achados = [a for nome in ("CHANGELOG.md", "NOTICE", "LICENSE", "PYPI.md", "pyproject.toml")
               for a in guarda.achados_no_texto((ROOT / nome).read_text(encoding="utf8"), nome)]
    assert not achados, "\n".join(achados)


def test_templates_de_venda_nao_citam_o_comando_prospect():
    """`prospect` saiu do CLI do motor (#77) e do pacote: o texto dos templates e do README deles não manda rodá-lo."""
    achados = [f"{p.relative_to(SRC)}:{n}" for p in sorted((SRC / "data" / "templates").rglob("*")) if p.is_file()
               for n, linha in enumerate(p.read_text(encoding="utf8", errors="replace").splitlines(), 1)
               if re.search(r"prospect", linha, re.I)]
    assert not achados, "texto velho sobre o comando prospect (saiu do motor):\n" + "\n".join(achados)


# ---------------------------------------------------------------------------------------- guarda endurecida (revisão do PR #115)
# A guarda de antes do review, congelada: cada caso burlável abaixo passou por ela com a suíte inteira verde.
_TERMOS_ANTIGOS = ("sideropolis", "jovaia", "wjrinformatica", "wjr", "lothus", "all prime", "allprime", "aprimeodonto", "guarulhos")
_RE_TELEFONE_ANTIGO = re.compile(r"\(\d{2}\)\s?9?\d{4}[-\s]?\d{4}|\b\d{2}[\s.]9\d{4}-\d{4}\b|wa\.me/\d+|whatsapp\.com/send\?phone=\d+", re.I)
_RE_EMAIL_ANTIGO = re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)*\.(?:com|net|org|io|app|dev|me|ai|edu|gov|br)\b", re.I)
_RE_CPF_ANTIGO = re.compile(r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b")
_RE_CNPJ_ANTIGO = re.compile(r"\b\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\b")


def _guarda_antiga(texto: str) -> list[str]:
    achados = []
    for linha in texto.splitlines():
        baixa = unicodedata.normalize("NFKD", linha).encode("ascii", "ignore").decode().casefold()
        achados += [t for t in _TERMOS_ANTIGOS if t in baixa]
        achados += [m.group(0) for m in _RE_TELEFONE_ANTIGO.finditer(linha) if m.group(0) != "(00) 00000-0000"]
        achados += [m.group(0) for m in _RE_EMAIL_ANTIGO.finditer(linha) if not re.search(r"@(?:example\.(?:com|org|net)|localhost)\b", m.group(0), re.I)]
        achados += [rx.pattern for rx in (_RE_CPF_ANTIGO, _RE_CNPJ_ANTIGO) if rx.search(linha)]
    return achados


# (nome, texto como o revisor o colou num bloco do motion, trecho esperado no achado)
CASOS_BURLAVEIS = [
    ("endereço com entidade HTML", "<div>R. Sider&oacute;polis, 168 · Jardim Jova&iacute;a</div>", "sideropolis"),
    ("entidade numérica", "<!-- Sider&#243;polis -->", "sideropolis"),
    ("entidade dentro de entidade", "<div>Sider&amp;oacute;polis</div>", "sideropolis"),
    ("escape JSON (json.dumps padrão)", json.dumps({"endereco": "Siderópolis · Jovaía"}), "jovaia"),
    ("escape \\xNN", 'const rua = "Sider\\xf3polis";', "sideropolis"),
    ("percent-encoding", "https://exemplo.com/mapa?q=Sider%C3%B3polis", "sideropolis"),
    ("@ do dono", "<b>@wesleysimplicio</b>", "wesleysimplicio"),
    ("conta do dono sem @", "// conta wesleybob4 no Drive", "wesleybob4"),
    ("@ de cliente novo", "<b>@clinicasorriso_oficial</b>", "@clinicasorriso_oficial"),
    ("e-mail com TLD fora da lista", "contato@x.online", "e-mail"),
    ("e-mail com arroba em entidade", "fulano&#64;empresa.com.br", "e-mail"),
    ("telefone só com espaços", "<span>11 99876 5432</span>", "telefone"),
    ("telefone com nono dígito solto", "(11) 9 9876-5432", "telefone"),
    ("telefone só com dígitos", "tel:11998765432", "telefone"),
    ("telefone com +55 e dígitos colados", "+5511998765432", "telefone"),
    ("telefone fixo com espaços", "<i>11 3456 7890</i>", "telefone"),
    ("CPF sem pontuação", "52998224725", "CPF"),
    ("CPF com espaços", "CPF 529 982 247 25", "CPF"),
    ("CNPJ sem pontuação", "11222333000181", "CNPJ"),
]
# Já pegos pela guarda antiga: não são burla, mas têm que continuar pegos (formas escritas de outro jeito).
CASOS_JA_PEGOS = [
    ("telefone com DDD entre parênteses colado", "(11)99876-5432", "telefone"),
    ("telefone com +55 e hífen", "+55 11 99876-5432", "telefone"),
    ("e-mail do dono", "wesleybob4@live.com", "wesleybob4"),
]


@pytest.mark.parametrize("nome,texto,esperado", CASOS_BURLAVEIS, ids=[c[0] for c in CASOS_BURLAVEIS])
def test_guarda_pega_o_que_a_guarda_antiga_deixava_passar(nome, texto, esperado):
    assert _guarda_antiga(texto) == [], f"{nome}: a guarda antiga já pegava; o caso não prova nada"
    achados = guarda.achados_no_texto(texto, "bloco.html")
    assert any(esperado in a for a in achados), (nome, achados)


@pytest.mark.parametrize("nome,texto,esperado", CASOS_JA_PEGOS, ids=[c[0] for c in CASOS_JA_PEGOS])
def test_guarda_continua_pegando_o_que_ja_pegava(nome, texto, esperado):
    assert any(esperado in a for a in guarda.achados_no_texto(texto, "bloco.html")), nome


# Placeholders e números técnicos que parecem dado pessoal e não são: nenhum pode virar achado.
INOFENSIVOS = [
    "(00) 00000-0000", "Rua Exemplo, 123 · Cidade", "@suaempresa", "@empresa", "nome@example.com", "contato@exemplo.com",
    "contato@exemplo.com.br", "width: 1080px; height: 1920px; fps 30", 'viewBox="0 0 1080 1920"', "times: [0.5, 1.25, 3.0, 4]",
    "rgba(255, 0, 0, .5)", "1700000000 1700000001", "Chrome 152.0.7977.30", "hyperframes@0.8.97 gsap@3.14.2 v0.4.0 2026-10-16",
    "2026-10-17 18:30:00", "20241017", "@media (max-width: 600px) { @font-face { src: url(x.woff2) } }", "#2f3b45 #f5fafd",
    "sha256 503f2f3d1a435a2ad76ef267a17e4752c81b3b9cab366c2223d09a6004b24f04", "R$ 1.299,00", "12345678900",
]


@pytest.mark.parametrize("texto", INOFENSIVOS)
def test_guarda_nao_acusa_placeholder_nem_numero_tecnico(texto):
    assert guarda.achados_no_texto(texto, "ok") == []


def test_guarda_acha_o_dado_codificado_dentro_de_um_arquivo(tmp_path):
    pasta = tmp_path / "data" / "motion" / "patterns" / "kinetic-words"
    pasta.mkdir(parents=True)
    (pasta / "block.html").write_text("<!-- Sider&oacute;polis -->\n<p>ok</p>\n", encoding="utf8")
    (pasta / "pattern.json").write_text(json.dumps({"ref": "Jovaía", "contato": "(11)99876-5432"}), encoding="utf8")
    achados = guarda.varrer_arvore(tmp_path)
    assert any("block.html:1" in a and "sideropolis" in a for a in achados), achados
    assert any("pattern.json" in a and "jovaia" in a for a in achados), achados
    assert any("pattern.json" in a and "telefone" in a for a in achados), achados


# --- prévia antiga reencodada: o hash do arquivo muda, o dos pixels não
def _png(largura: int, altura: int, *, filtro: int, nivel: int, extra: bytes = b"") -> bytes:
    """PNG RGB mínimo: a mesma imagem sai com outro filtro (0 nenhum, 1 sub), nível de zlib e chunk de metadado."""
    def chunk(tipo: bytes, dados: bytes) -> bytes:
        return struct.pack(">I", len(dados)) + tipo + dados + struct.pack(">I", zlib.crc32(tipo + dados) & 0xFFFFFFFF)

    cru = b""
    for y in range(altura):
        linha = bytes((x * 7 + y * 13 + c * 31) % 256 for x in range(largura) for c in range(3))
        if filtro == 1:
            linha = bytes((linha[i] - (linha[i - 3] if i >= 3 else 0)) & 255 for i in range(len(linha)))
        cru += bytes([filtro]) + linha
    ihdr = struct.pack(">IIBBBBB", largura, altura, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + extra + chunk(b"IDAT", zlib.compress(cru, nivel)) + chunk(b"IEND", b"")


def test_guarda_pega_a_previa_antiga_so_reencodada(tmp_path, monkeypatch):
    original = _png(24, 16, filtro=0, nivel=9)
    reencodada = _png(24, 16, filtro=1, nivel=1, extra=struct.pack(">I", 4) + b"tEXt" + b"a\0bc" + struct.pack(">I", zlib.crc32(b"tEXta\0bc") & 0xFFFFFFFF))
    outra = _png(24, 17, filtro=0, nivel=9)
    assert hashlib.sha256(original).hexdigest() != hashlib.sha256(reencodada).hexdigest(), "o caso precisa mudar o hash do arquivo"
    assert guarda.hash_dos_pixels(original) == guarda.hash_dos_pixels(reencodada) != guarda.hash_dos_pixels(outra)
    monkeypatch.setitem(guarda.PREVIEWS_PROIBIDOS, hashlib.sha256(original).hexdigest(), "prévia de teste")
    monkeypatch.setitem(guarda.PREVIEWS_PROIBIDOS_PIXELS, guarda.hash_dos_pixels(original), "prévia de teste")
    (tmp_path / "a").mkdir()
    for nome, dados in (("original", original), ("reencodada", reencodada), ("outra", outra)):
        (tmp_path / "a" / f"{nome}.png").write_bytes(dados)
    achados = guarda.varrer_arvore(tmp_path)
    assert sorted(a.split(":")[0] for a in achados) == ["a/original.png", "a/reencodada.png"], achados
    # só o hash do arquivo (a guarda antiga) deixaria a reencodada passar
    monkeypatch.setattr(guarda, "PREVIEWS_PROIBIDOS_PIXELS", {})
    assert [a.split(":")[0] for a in guarda.varrer_arvore(tmp_path)] == ["a/original.png"]


def test_a_previa_antiga_do_lockup_esta_fixada_por_arquivo_e_por_pixels():
    assert "503f2f3d1a435a2ad76ef267a17e4752c81b3b9cab366c2223d09a6004b24f04" in guarda.PREVIEWS_PROIBIDOS
    assert "8130dec0b2fc697247386db8c596b6a2bf86a2a0f395db0e159adb25832442a3" in guarda.PREVIEWS_PROIBIDOS_PIXELS
    assert guarda.hash_dos_pixels((LOCKUP / "preview.png").read_bytes()) not in guarda.PREVIEWS_PROIBIDOS_PIXELS, "o preview atual é o do placeholder"
