"""Claim guard do studio (#16).

Número, preço, percentual ou promessa em `Draft.idea` ou `Draft.claims` precisa aparecer em `Brand.facts`.
Caso contrário, `check_claims` levanta `ClaimError` com o trecho e o campo onde ele está.
"""

from __future__ import annotations

import re
import unicodedata

from simplicio_factory.contracts import Brand, Draft

# Ordem importa: preço ("R$ 99") é consumido antes do número solto ("99"); percentual antes do número.
GATILHOS = re.compile(
    r"R\$\s?\d+(?:[.,]\d+)*"
    r"|\d+(?:[.,]\d+)*\s?%"
    r"|\d+(?:[.,]\d+)*"
    r"|\b(?:grátis|gratis|garantia|garantido|garantimos|cura)\b",
    re.IGNORECASE,
)


class ClaimError(ValueError):
    """Claim com número, preço, percentual ou promessa que não está em Brand.facts."""


def _norm(texto: str) -> str:
    sem_acento = "".join(c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", sem_acento).strip().lower()


def _presente(trecho: str, fatos: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(_norm(trecho))}(?!\w)", fatos) is not None


def check_claims(draft: Draft, brand: Brand) -> None:
    fatos = " | ".join(_norm(str(v)) for v in brand.facts.values())
    campos = [("idea", draft.idea)] + [(f"claims[{i}]", c) for i, c in enumerate(draft.claims)]
    for onde, texto in campos:
        for gatilho in GATILHOS.finditer(str(texto)):
            trecho = gatilho.group(0)
            if not _presente(trecho, fatos):
                raise ClaimError(
                    f"claim sem fato em brand.json: {trecho!r} em {onde} ({texto!r}). "
                    "Adicione o fato em brand.json (facts) ou remova o trecho do Draft."
                )
