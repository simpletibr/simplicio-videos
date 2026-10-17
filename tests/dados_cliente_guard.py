"""Shared scanner for the client-data guard (used by test_dados_cliente_no_pacote.py and by the wheel test).

The term list lives here, in a test helper that sits outside src/ and therefore outside the wheel.
"""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path

# Real customers and prospects of the owner. Matched after lower-casing and stripping accents.
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

# Identifiers that contain a term but cannot change without breaking contracts that live in clients/ (a pattern id
# is part of the contract surface). Removed from the text and from the path before matching; keep this list tiny.
IDS_ESTAVEIS = ("service-illustrations-wjr",)

# Placeholders that are allowed because they are obviously fake.
TELEFONE_PLACEHOLDER = "(00) 00000-0000"

BINARIOS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".ttf", ".otf", ".woff", ".woff2", ".wav", ".mp3", ".mp4",
            ".mov", ".webm", ".pyc", ".onnx"}

# Brazilian landline/mobile in the usual written forms, WhatsApp links, e-mail, CPF and CNPJ.
RE_TELEFONE = re.compile(r"\(\d{2}\)\s?9?\d{4}[-\s]?\d{4}|\b\d{2}[\s.]9\d{4}-\d{4}\b|wa\.me/\d+|whatsapp\.com/send\?phone=\d+", re.I)
RE_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)*\.(?:com|net|org|io|app|dev|me|ai|edu|gov|br)\b", re.I)
RE_CPF = re.compile(r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b")
RE_CNPJ = re.compile(r"\b\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\b")
EMAIL_FICTICIO = re.compile(r"@(?:example\.(?:com|org|net)|localhost)\b", re.I)

# Preview images cannot be grepped: the ones that once showed a customer brand are pinned by hash.
PREVIEWS_PROIBIDOS = {
    "503f2f3d1a435a2ad76ef267a17e4752c81b3b9cab366c2223d09a6004b24f04": "brand-lockup-soft/preview.png com a marca LOTHUS ODONTOLOGIA",
}


def normaliza(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().casefold()


def _sem_ids_estaveis(texto: str) -> str:
    for i in IDS_ESTAVEIS:
        texto = texto.replace(i, "")
    return texto


def achados_no_texto(texto: str, origem: str) -> list[str]:
    """Findings (`origem:linha: motivo`) for one text blob; empty when it is clean."""
    achados: list[str] = []
    for n, linha in enumerate(_sem_ids_estaveis(texto).splitlines(), 1):
        baixa = normaliza(linha)
        for termo in TERMOS_DE_CLIENTE:
            if termo in baixa:
                achados.append(f"{origem}:{n}: termo de cliente {termo!r}")
        for m in RE_TELEFONE.finditer(linha):
            if m.group(0) != TELEFONE_PLACEHOLDER:
                achados.append(f"{origem}:{n}: telefone {m.group(0)!r}")
        for m in RE_EMAIL.finditer(linha):
            if not EMAIL_FICTICIO.search(m.group(0)):
                achados.append(f"{origem}:{n}: e-mail {m.group(0)!r}")
        for rx, nome in ((RE_CPF, "CPF"), (RE_CNPJ, "CNPJ")):
            if rx.search(linha):
                achados.append(f"{origem}:{n}: {nome}")
    return achados


def achados_no_caminho(rel: str) -> list[str]:
    baixa = normaliza(_sem_ids_estaveis(rel))
    return [f"{rel}: nome de arquivo com termo de cliente {t!r}" for t in TERMOS_DE_CLIENTE if t in baixa]


def varrer_arvore(raiz: Path) -> list[str]:
    """Scan every file under `raiz` (names, text content, pinned preview hashes)."""
    import hashlib

    achados: list[str] = []
    for p in sorted(raiz.rglob("*")):
        if not p.is_file() or "__pycache__" in p.parts:
            continue
        rel = p.relative_to(raiz).as_posix()
        achados += achados_no_caminho(rel)
        dados = p.read_bytes()
        if p.suffix.lower() in BINARIOS:
            visto = PREVIEWS_PROIBIDOS.get(hashlib.sha256(dados).hexdigest())
            if visto:
                achados.append(f"{rel}: imagem de cliente ({visto})")
            continue
        achados += achados_no_texto(dados.decode("utf-8", errors="replace"), rel)
    return achados
