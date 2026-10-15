"""Catalog lookups: templates, motion patterns, voice providers."""
from __future__ import annotations

import json
from pathlib import Path

from .voice import PROVIDERS


def templates(data: Path) -> list[dict]:
    res = []
    for tj in sorted((data / "templates").glob("*/template.json")):
        t = json.loads(tj.read_text(encoding="utf8"))
        res.append({"id": t["id"], "status": t["status"], "duracao_s": t["duracao_s"], "setor": t["setor"],
                    "renderizavel": bool(t.get("composicao")), "cenas": [c["id"].lower() for c in t["cenas"]]})
    return res


def motion(data: Path) -> list[dict]:
    cat = json.loads((data / "motion" / "catalog.json").read_text(encoding="utf8"))
    items = cat.get("patterns", cat) if isinstance(cat, dict) else cat
    return [{"id": p["id"], "status": p.get("status"), "category": p.get("category"), "duration_s": p.get("duration_s"),
             "block": bool(p.get("block")), "params": p.get("params", []), "title": p.get("title", "")} for p in items]


def voices() -> list[dict]:
    return [{"id": k, "desc": v} for k, v in PROVIDERS.items()]


GRUPOS_ANGULOS = ("problema", "prova", "desejo", "decisao", "estrategia")


def angles(data: Path, grupo: str | None = None) -> list[dict]:
    """Ângulos de anúncio (data/angles/angles.json): todos, ou só os de um grupo."""
    doc = json.loads((data / "angles" / "angles.json").read_text(encoding="utf8"))
    return [a for a in doc["angulos"] if grupo is None or a["grupo"] == grupo]
