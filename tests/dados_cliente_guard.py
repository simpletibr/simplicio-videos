"""Shared scanner for the client-data guard (used by the source-tree, wheel and sdist tests).

The term list lives here, in a test helper that sits outside src/ and therefore outside the wheel and the sdist.

The scanner never trusts the raw bytes: every line is decoded first (HTML entities, `\\uXXXX` and `\\xNN` escapes,
percent-encoding, repeated until stable), then accents and case are stripped, and phones, CPF and CNPJ are matched on
the digits alone, so spacing, punctuation and a `+55` prefix change nothing. A list of terms only catches what it
lists, so the owner's identifiers are forbidden too and so is any @handle nobody has cleared.
"""
from __future__ import annotations

import hashlib
import html
import re
import struct
import unicodedata
import urllib.parse
import zlib
from pathlib import Path

# Real customers and prospects of the owner. Matched after decoding, lower-casing and stripping accents.
TERMOS_DE_CLIENTE = (
    "sideropolis",      # WJR street
    "jovaia",           # WJR neighbourhood
    "wjrinformatica",   # WJR domain and handle
    "wjr",
    "lothus",
    "all prime",
    "allprime",
    "aprimeodonto",
    "guarulhos",        # city of both pilot customers
)

# The owner's own identifiers: handle, account name and the mail provider of the account. The owner's name as the package
# author (pyproject, PKG-INFO) is public by choice and is not here. `live.com` needs a boundary on the left (olive.com).
TERMOS_DO_DONO = {
    "wesleysimplicio": r"wesleysimplicio",
    "wesleybob4": r"wesleybob4",
    "live.com": r"(?<![a-z0-9.-])live\.com",
}

# Identifiers that contain a term but cannot change without breaking contracts that live in clients/ (a pattern id
# is part of the contract surface). Removed from the text and from the path before matching; keep this list tiny.
IDS_ESTAVEIS = ("service-illustrations-wjr",)

# @tokens that are not a customer: placeholders, CSS at-rules, decorators, jsdoc tags, npm scopes and package tags,
# and the creators credited as the origin of a motion pattern. A new @ is a finding until someone clears it here.
ARROBAS_PERMITIDAS = frozenset({
    "suaempresa", "empresa", "perfil", "conta",  # placeholders
    "media", "keyframes", "font-face", "import", "supports", "page", "charset", "layer", "container", "property",
    "namespace", "font",  # CSS
    "dataclass", "classmethod", "staticmethod", "contextlib.contextmanager", "latest", "puppeteer", "hypit", "tiny-fish",
    "tiny", "t",  # code and npm (`@t` is the time marker of the retime docs)
    "annacher___", "mounnna", "ror_fly", "sayajiiinz", "felipemoller", "koldo2k", "lukasersil", "reflex_cloud",
    "shengkunye", "twoclipping", "__morse", "hypitai", "simpliciomcp",  # creators credited in motion/patterns
})

BINARIOS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".ttf", ".otf", ".woff", ".woff2", ".wav", ".mp3", ".mp4",
            ".mov", ".webm", ".pyc", ".onnx"}

# Area codes in use in Brazil. `(00) 00000-0000` and friends are not phones, so the placeholders pass without a special case.
DDDS = frozenset({11, 12, 13, 14, 15, 16, 17, 18, 19, 21, 22, 24, 27, 28, 31, 32, 33, 34, 35, 37, 38, 41, 42, 43, 44, 45, 46,
                  47, 48, 49, 51, 53, 54, 55, 61, 62, 63, 64, 65, 66, 67, 68, 69, 71, 73, 74, 75, 77, 79, 81, 82, 83, 84, 85,
                  86, 87, 88, 89, 91, 92, 93, 94, 95, 96, 97, 98, 99})

RE_WHATSAPP = re.compile(r"wa\.me/\d+|whatsapp\.com/send\?phone=\d+", re.I)
# A run of digit groups glued by the separators people use in phones, CPF and CNPJ. Each group is tried alone and in
# short windows of neighbours, so two numbers on one line do not hide each other.
RE_NUMEROS = re.compile(r"(?<![\w.])[+(]*\d[\d\s().\-/+]*\d(?![\w])")
JANELA_MAX = 7
RE_EMAIL = re.compile(r"(?<![\w.+-])[\w.+-]+@[\w-]+(?:\.[\w-]+)*\.[a-z]{2,}\b")
EMAIL_FICTICIO = re.compile(r"@(?:example\.(?:com|org|net)|exemplo\.com(?:\.br)?|localhost)$")
RE_ARROBA = re.compile(r"(?<![\w@/.:%+-])@([a-z_][a-z0-9_.-]*)")
RE_CPF_PONTUADO = re.compile(r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b")
RE_CNPJ_PONTUADO = re.compile(r"\b\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\b")

RE_ESCAPE_U = re.compile(r"\\+u\{([0-9a-fA-F]{1,6})\}|\\+u([0-9a-fA-F]{4})")
RE_ESCAPE_X = re.compile(r"\\+x([0-9a-fA-F]{2})")

# Preview images cannot be grepped: the ones that once showed a customer brand are pinned by file hash and by the hash
# of their decoded pixels (re-saving the same picture changes the file hash and not the pixels).
PREVIEWS_PROIBIDOS = {
    "503f2f3d1a435a2ad76ef267a17e4752c81b3b9cab366c2223d09a6004b24f04": "brand-lockup-soft/preview.png com a marca LOTHUS ODONTOLOGIA",
}
PREVIEWS_PROIBIDOS_PIXELS: dict[str, str] = {
    "8130dec0b2fc697247386db8c596b6a2bf86a2a0f395db0e159adb25832442a3": "brand-lockup-soft/preview.png com a marca LOTHUS ODONTOLOGIA, mesmo reencodado",
}


# ------------------------------------------------------------------ text
def _chr(m: re.Match) -> str:
    try:
        return chr(int(m.group(1) or m.group(2), 16))
    except (ValueError, OverflowError):
        return m.group(0)


def decodifica(texto: str) -> str:
    """Undo the usual ways to hide text, until nothing changes (an entity inside an escape inside a URL)."""
    for _ in range(4):
        novo = html.unescape(texto)
        novo = RE_ESCAPE_U.sub(_chr, novo)
        novo = RE_ESCAPE_X.sub(_chr, novo)
        novo = urllib.parse.unquote(novo)
        if novo == texto:
            break
        texto = novo
    return texto


def normaliza(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().casefold()


def _sem_ids_estaveis(texto: str) -> str:
    for i in IDS_ESTAVEIS:
        texto = texto.replace(i, "")
    return texto


def _cpf_valido(d: str) -> bool:
    if len(d) != 11 or len(set(d)) == 1:
        return False
    for n in (9, 10):
        soma = sum(int(d[i]) * (n + 1 - i) for i in range(n))
        if (soma * 10 % 11) % 10 != int(d[n]):
            return False
    return True


def _cnpj_valido(d: str) -> bool:
    if len(d) != 14 or len(set(d)) == 1:
        return False
    pesos = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    for n, p in ((12, pesos), (13, [6] + pesos)):
        r = sum(int(d[i]) * p[i] for i in range(n)) % 11
        if (0 if r < 2 else 11 - r) != int(d[n]):
            return False
    return True


def _telefone_valido(d: str) -> bool:
    if len(d) in (12, 13) and d.startswith("55"):
        d = d[2:]
    if len(d) == 11:
        return int(d[:2]) in DDDS and d[2] == "9"
    return len(d) == 10 and int(d[:2]) in DDDS and d[2] in "2345"


# How the digits of a phone are grouped when written: after the optional country code (`55`, glued to the area code or
# apart), the area code and the number in the usual splits, or all digits glued. Anything else is not a phone.
_BASE = {(2, 9), (2, 8), (2, 5, 4), (2, 4, 4), (2, 1, 4, 4), (2, 1, 8)}
FORMAS_DE_TELEFONE = {(11,), (12,), (13,)} | _BASE | {(2,) + b for b in _BASE} | {(4,) + b[1:] for b in _BASE}


def _numeros_de_documento(linha: str) -> list[str]:
    """Findings among the digit groups of one normalised line: phone, CPF and CNPJ, whatever the punctuation.

    Every candidate is split into digit groups; each group and each short window of neighbours is tried, so two numbers on
    one line do not hide each other. A phone needs an area code in use, a mobile 9 or a landline 2-5, and a usual grouping;
    CPF and CNPJ need the check digits and their usual grouping (3+3+3+2 and 2+3+3+4+2, or all digits glued)."""
    achados: list[str] = []
    for m in RE_NUMEROS.finditer(linha):
        grupos = re.findall(r"\d+", m.group(0))
        for i in range(len(grupos)):
            for j in range(i, min(len(grupos), i + JANELA_MAX)):
                janela = grupos[i:j + 1]
                d = "".join(janela)
                if len(d) > 14:
                    break
                forma = tuple(len(g) for g in janela)
                if _telefone_valido(d) and forma in FORMAS_DE_TELEFONE:
                    achados.append(f"telefone {d!r}")
                if _cpf_valido(d) and forma in ((11,), (3, 3, 3, 2)):
                    achados.append(f"CPF {d!r}")
                if _cnpj_valido(d) and forma in ((14,), (2, 3, 3, 4, 2)):
                    achados.append(f"CNPJ {d!r}")
    return achados


def achados_no_texto(texto: str, origem: str, *, arrobas: bool = True) -> list[str]:
    """Findings (`origem:linha: motivo`) for one text blob; empty when it is clean."""
    achados: list[str] = []
    for n, linha in enumerate(_sem_ids_estaveis(texto).splitlines(), 1):
        baixa = normaliza(decodifica(linha))
        for termo in TERMOS_DE_CLIENTE:
            if termo in baixa:
                achados.append(f"{origem}:{n}: termo de cliente {termo!r}")
        for termo, rx in TERMOS_DO_DONO.items():
            if re.search(rx, baixa):
                achados.append(f"{origem}:{n}: identificador do dono {termo!r}")
        for m in RE_WHATSAPP.finditer(baixa):
            achados.append(f"{origem}:{n}: telefone {m.group(0)!r}")
        for motivo in _numeros_de_documento(baixa):
            achados.append(f"{origem}:{n}: {motivo}")
        for rx, nome in ((RE_CPF_PONTUADO, "CPF"), (RE_CNPJ_PONTUADO, "CNPJ")):
            if rx.search(baixa):
                achados.append(f"{origem}:{n}: {nome} pontuado")
        for m in RE_EMAIL.finditer(baixa):
            if not EMAIL_FICTICIO.search(m.group(0)):
                achados.append(f"{origem}:{n}: e-mail {m.group(0)!r}")
        if arrobas:
            for m in RE_ARROBA.finditer(baixa):
                nome = m.group(1).rstrip(".-")
                if nome not in ARROBAS_PERMITIDAS:
                    achados.append(f"{origem}:{n}: @{nome} não liberado (cliente novo?)")
    return achados


def achados_no_caminho(rel: str) -> list[str]:
    baixa = normaliza(decodifica(_sem_ids_estaveis(rel)))
    return [f"{rel}: nome de arquivo com termo de cliente {t!r}" for t in TERMOS_DE_CLIENTE if t in baixa]


# ------------------------------------------------------------------ images
def hash_dos_pixels(dados: bytes) -> str | None:
    """sha256 of a non-interlaced PNG's decoded scanlines, palette and transparency; None for anything else.

    The same picture saved with another filter, compression level, or metadata has the same pixel hash."""
    if not dados.startswith(b"\x89PNG\r\n\x1a\n"):
        return None
    pos, ihdr, idat, extra = 8, None, [], []
    while pos + 8 <= len(dados):
        tam, tipo = struct.unpack(">I4s", dados[pos:pos + 8])
        corpo = dados[pos + 8:pos + 8 + tam]
        pos += 12 + tam
        if tipo == b"IHDR":
            ihdr = struct.unpack(">IIBBBBB", corpo)
        elif tipo == b"IDAT":
            idat.append(corpo)
        elif tipo in (b"PLTE", b"tRNS"):
            extra.append(tipo + corpo)
    if not ihdr or not idat or ihdr[6] != 0:
        return None
    w, h, bits, cor = ihdr[:4]
    canais = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}.get(cor)
    if canais is None:
        return None
    try:
        cru = zlib.decompress(b"".join(idat))
    except zlib.error:
        return None
    bpp = max(1, canais * bits // 8)
    linha = (w * canais * bits + 7) // 8
    if len(cru) < h * (linha + 1):
        return None
    pixels = bytearray()
    ant = bytearray(linha)
    for y in range(h):
        base = y * (linha + 1)
        filtro, atual = cru[base], bytearray(cru[base + 1:base + 1 + linha])
        for x in range(linha):
            a = atual[x - bpp] if x >= bpp else 0
            b = ant[x]
            c = ant[x - bpp] if x >= bpp else 0
            if filtro == 1:
                atual[x] = (atual[x] + a) & 255
            elif filtro == 2:
                atual[x] = (atual[x] + b) & 255
            elif filtro == 3:
                atual[x] = (atual[x] + (a + b) // 2) & 255
            elif filtro == 4:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                atual[x] = (atual[x] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        pixels += atual
        ant = atual
    resumo = hashlib.sha256(struct.pack(">IIBB", w, h, bits, cor) + b"".join(extra) + bytes(pixels))
    return resumo.hexdigest()


def varrer_arvore(raiz: Path) -> list[str]:
    """Scan every file under `raiz` (names, text content, pinned preview hashes)."""
    achados: list[str] = []
    for p in sorted(raiz.rglob("*")):
        if not p.is_file() or "__pycache__" in p.parts:
            continue
        rel = p.relative_to(raiz).as_posix()
        achados += achados_no_caminho(rel)
        dados = p.read_bytes()
        if p.suffix.lower() in BINARIOS:
            visto = PREVIEWS_PROIBIDOS.get(hashlib.sha256(dados).hexdigest())
            if not visto and p.suffix.lower() == ".png":
                visto = PREVIEWS_PROIBIDOS_PIXELS.get(hash_dos_pixels(dados) or "")
            if visto:
                achados.append(f"{rel}: imagem de cliente ({visto})")
            continue
        achados += achados_no_texto(dados.decode("utf-8", errors="replace"), rel, arrobas=p.suffix.lower() not in (".py", ".pyi"))
    return achados
