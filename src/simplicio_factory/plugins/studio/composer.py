"""Composer do studio (#16): Draft + Brand -> contract.yaml do motor (simplicio.video-contract/v1), em bytes fixos.

Mesma entrada, mesmos bytes: a ordem das chaves é a do template (não sort_keys), sem timestamp, sem rede.
O emissor abaixo escreve o formato do golden (tests/factory/plugins/studio/golden/contract.yaml): escalares simples
sem aspas, textos com espaço ou símbolo entre aspas duplas, listas de escalares em estilo de fluxo.
"""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

from simplicio_factory.contracts import Brand, Draft
from simplicio_factory.plugins.studio.claims import check_claims

TEMPLATE_ID = "brand-promo"
DURACAO_MAX_S = 20
PRESETS = {"9:16": (1080, 1920)}  # plataforma -> (largura, altura) do preset
PREVIA_9_16 = (540, 960)
FPS = 30
CLAIMS_MAX = 2  # prova_1 e prova_2 (s2)
CAMPANHA = {"id": "Promo", "ano": 2026}
TAGLINE = "Cuidado com hora marcada."  # texto do template (s3)
CTA = "Agende sua visita."  # texto do template (s3)
CONECTIVOS = ("em", "de", "com", "para", "no", "na", "por")
TRILHA = {
    "bpm": 120,
    "seed": 7,
    "music": {
        "gain_db": -6,
        "fade_in_s": 0.5,
        "fade_out_s": 1.0,
        "progression": [[48, [60, 64, 67]]],
    },
    "master": {"target_lufs": -14, "true_peak_db": -1.5},
}

_PLAIN = re.compile(r"[A-Za-z][A-Za-z0-9_./-]*")
_PLAIN_COM_ESPACO = re.compile(r"[^\W\d_][\w .-]*")  # nome com letras e espaços: plano só se não houver ': ' nem ' #'
_RESERVADAS = {"true", "false", "null", "yes", "no", "on", "off", "y", "n"}


class _NomeLivre(str):
    """Texto que o golden escreve sem aspas quando é seguro (cliente.nome), ex.: `nome: Clínica Exemplo`."""


def compose_contract(draft: Draft, brand: Brand, *, preview: bool = False) -> str:
    check_claims(draft, brand)
    plataforma = _plataforma(draft)
    largura, altura = PREVIA_9_16 if preview else PRESETS[plataforma]
    dados = {
        "schema": "simplicio.video-contract/v1",
        "cliente": {"slug": _slug(brand.name), "nome": _NomeLivre(brand.name), "drive_nome": _drive_nome(brand.name)},
        "campanha": dict(CAMPANHA),
        "formato": {
            "aspect": "9:16",
            "width": largura,
            "height": altura,
            "fps": FPS,
            "duracao_s": draft.duration_s,
        },
        "template": TEMPLATE_ID,
        "marca": _marca(brand),
        "cenas": _cenas(draft, brand),
        "voz": {"habilitada": False, "provider": "file"},
        "trilha": TRILHA,
        "saida": {"arquivo": "out/brand-promo.mp4", "qualidade": "draft" if preview else "delivery"},
    }
    linhas: list[str] = []
    _emitir(dados, 0, linhas)
    return "\n".join(linhas) + "\n"


def _plataforma(draft: Draft) -> str:
    if draft.platform not in PRESETS:
        raise ValueError(f"plataforma sem preset: {draft.platform!r} (presets: {', '.join(PRESETS)})")
    if not 0 < draft.duration_s <= DURACAO_MAX_S:
        raise ValueError(f"duração de {draft.duration_s} s: o máximo para {draft.platform} é {DURACAO_MAX_S} s")
    return draft.platform


def _marca(brand: Brand) -> dict:
    cores = {chave: str(valor) for chave, valor in brand.colors.items()}
    for obrigatoria in ("primary", "accent", "ink"):
        if obrigatoria not in cores:
            raise ValueError(f"brand.json precisa da cor {obrigatoria!r} (colors)")
    logo = None
    if brand.logo:
        nome = Path(brand.logo).name
        logo = {"arquivo": f"assets/{nome}", "destino": f"assets/{nome}"}
    return {"paleta": {chave: cores[chave] for chave in sorted(cores)}, "logo": logo}


def _cenas(draft: Draft, brand: Brand) -> list[dict]:
    if len(draft.claims) > CLAIMS_MAX:
        raise ValueError(f"o Draft tem {len(draft.claims)} claims; o máximo é {CLAIMS_MAX} (prova_1, prova_2)")
    base = round(draft.duration_s / 3, 3)
    duracoes = [_numero(base), _numero(base), _numero(round(draft.duration_s - 2 * base, 3))]
    cores = brand.colors
    primaria, destaque, tinta = str(cores["primary"]), str(cores["accent"]), str(cores["ink"])
    logo = Path(brand.logo).name if brand.logo else None
    return [
        {
            "id": "s1",
            "papel": "gancho",
            "duracao_s": duracoes[0],
            "motion": [
                {
                    "padrao": "kinetic-words",
                    "bloco": "s1-words",
                    "params": {"lines": _duas_linhas(draft.idea), "colors": f"{primaria}|{destaque}", "ink": tinta},
                }
            ],
            "textos": {"titulo": draft.idea},
        },
        {
            "id": "s2",
            "papel": "prova",
            "duracao_s": duracoes[1],
            "motion": [{"padrao": "line-accent", "bloco": "s2-accent", "params": {"color": destaque, "ink": tinta}}],
            "textos": {f"prova_{i + 1}": texto for i, texto in enumerate(draft.claims)},
        },
        {
            "id": "s3",
            "papel": "marca",
            "duracao_s": duracoes[2],
            "motion": [
                {
                    "padrao": "brand-lockup-soft",
                    "bloco": "s3-lockup",
                    "params": {
                        "name": brand.name,
                        "sub": "",
                        "tagline": TAGLINE,
                        "handle": "",
                        "city": _cidade(brand.facts),
                        "logo": f"assets/{logo}" if logo else "",
                        "ink": tinta,
                        "accent": primaria,
                    },
                }
            ],
            "textos": {"cta": CTA},
        },
    ]


def _duas_linhas(texto: str) -> str:
    """Quebra o título em duas linhas ('|'): antes do primeiro conectivo a partir da 3ª palavra, ou no meio."""
    palavras = texto.split()
    if len(palavras) < 4:
        return " ".join(palavras)
    corte = next((i for i in range(2, len(palavras)) if palavras[i].lower() in CONECTIVOS), len(palavras) // 2)
    return " ".join(palavras[:corte]) + "|" + " ".join(palavras[corte:])


def _cidade(facts: dict) -> str:
    if facts.get("cidade"):
        return str(facts["cidade"])
    achado = re.search(r"\b(?:de|em)\s+((?:[A-ZÀ-Ú]\w*)(?:\s+[A-ZÀ-Ú]\w*)*)\s*$", str(facts.get("unidade", "")))
    return achado.group(1) if achado else ""


def _sem_acento(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c))


def _slug(nome: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", _sem_acento(nome).lower()).strip("-")


def _drive_nome(nome: str) -> str:
    return "_".join(_sem_acento(p).capitalize() for p in nome.split())


def _numero(x: float):
    x = round(float(x), 3)
    return int(x) if x.is_integer() else x


def _escalar(valor) -> str:
    if valor is None:
        return "null"
    if isinstance(valor, bool):
        return "true" if valor else "false"
    if isinstance(valor, int):
        return str(valor)
    if isinstance(valor, float):
        return repr(valor)
    texto = str(valor)
    if texto.lower() not in _RESERVADAS:
        if _PLAIN.fullmatch(texto):
            return texto
        if isinstance(valor, _NomeLivre) and _PLAIN_COM_ESPACO.fullmatch(texto) and texto == texto.strip():
            return texto
    return json.dumps(texto, ensure_ascii=False)


def _fluxo(valor) -> str:
    if isinstance(valor, list):
        return "[" + ", ".join(_fluxo(x) for x in valor) + "]"
    return _escalar(valor)


def _emitir(obj: dict, indent: int, saida: list[str]) -> None:
    pad = " " * indent
    for chave, valor in obj.items():
        if isinstance(valor, dict):
            if not valor:
                saida.append(f"{pad}{chave}: {{}}")
            else:
                saida.append(f"{pad}{chave}:")
                _emitir(valor, indent + 2, saida)
        elif isinstance(valor, list) and valor and all(isinstance(x, dict) for x in valor):
            saida.append(f"{pad}{chave}:")
            for item in valor:
                bloco: list[str] = []
                _emitir(item, indent + 4, bloco)
                bloco[0] = " " * (indent + 2) + "- " + bloco[0][indent + 4 :]
                saida.extend(bloco)
        elif isinstance(valor, list):
            saida.append(f"{pad}{chave}: {_fluxo(valor)}")
        else:
            saida.append(f"{pad}{chave}: {_escalar(valor)}")
