"""`simplicio-video init`: write a contract skeleton from a sector template (TODOs must be filled by the author)."""
from __future__ import annotations

import datetime as dt
import json
import re
import unicodedata
from pathlib import Path

import yaml

from . import paths


def drive_token(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return "_".join(w[:1].upper() + w[1:] for w in re.split(r"[^A-Za-z0-9]+", s) if w)


def sem_checkout() -> bool:
    """True for a pip-installed package: `paths.home()` fell back to the package data dir, which lives in site-packages."""
    return paths.home() == paths.DATA_DIR


def default_out(campanha_id: str, slug: str) -> Path:
    """Default contract path: <checkout>/clients/<slug>/<campaign>/contract.yaml.

    Without a checkout (pip install) the data dir is in site-packages, which may be read-only and must never be written
    to, so the CLI puts the project under the cwd (the folder of whoever typed the command). An MCP server has no such
    folder: its cwd is wherever the client started it, so `mcp_server.video_init` asks for `out` instead."""
    base = Path.cwd() if sem_checkout() else paths.home()
    return base / "clients" / slug / campanha_id.lower().replace("_", "-") / "contract.yaml"


def skeleton(home: Path, slug: str, campanha: str, template: str, ano: int | None, nome: str | None,
             drive_nome: str | None) -> dict:
    tj = paths.data_dir() / "templates" / template / "template.json"
    if not tj.is_file():
        raise SystemExit(f"template '{template}' not found (see `simplicio-video list templates`)")
    t = json.loads(tj.read_text(encoding="utf8"))
    ano = ano or dt.date.today().year
    camp = drive_token(campanha)
    dn = drive_nome or drive_token(nome or slug)
    cenas = []
    for i, sc in enumerate(t["cenas"], 1):
        cid = sc["id"].lower()
        cena = {"id": cid, "papel": sc["papel"], "duracao_s": sc["dur_s"],
                "motion": [{"padrao": p, "bloco": f"{cid}-{p.split('-')[0]}", "params": {}} for p in sc["padroes"]],
                "tela": ["TODO: texto na tela (só fatos de coleta/)"],
                "fala": {"id": f"vo{i}", "texto": f"TODO: {sc.get('fala', 'fala')}", "inicio_s": 0.25,
                         "max_s": round(max(0.5, sc["dur_s"] - 0.5), 2)},
                "sfx": []}
        cenas.append(cena)
    v = t.get("voz", {})
    f = t.get("formato", {})
    return {
        "schema": "simplicio.video-contract/v1",
        "cliente": {"slug": slug, "nome": nome or "TODO: nome do cliente", "drive_nome": dn, "coleta": "../coleta"},
        "campanha": {"id": camp, "ano": ano, "titulo": f"TODO: título de {camp}"},
        "formato": {"aspect": f.get("aspect", "9:16"), "width": f.get("width", 1080), "height": f.get("height", 1920),
                    "fps": f.get("fps", 30), "duracao_s": t["duracao_s"]},
        "template": template,
        "marca": {"paleta": t.get("paleta_padrao", {}).get("ink") and {"ink": t["paleta_padrao"]["ink"]} or {}, "logo": None, "fontes": []},
        "cenas": cenas,
        "voz": {"provider": "local", "voice": "pf_dora", "estilo": v.get("estilo", ""), "idioma": "pt-BR",
                "gain_db": 0, "duck_music_db": 10, "duck_sfx_db": 6,
                "providers": {"file": {"dir": "assets/audio/vo/external"},
                              "gemini": {"model": "gemini-3.8-flash-tts", "voice": v.get("gemini_voz", "Sulafat"), "estilo": v.get("estilo", "")}}},
        "trilha": {"bpm": t.get("musica", {}).get("bpm", 120), "seed": int(f"{ano}0101"),
                   "music": {"gain_db": -5, "fade_in_s": 0.05, "fade_out_s": 1.0,
                             "progression": [[48, [60, 64, 67]], [43, [59, 62, 67]], [45, [57, 60, 64]], [41, [57, 60, 65]]]},
                   "master": {"target_lufs": -14, "true_peak_db": -1.5}},
        "saida": {"arquivo": f"out/{slug}-{camp.lower().replace('_', '-')}.mp4", "qualidade": "delivery"},
    }


def write(path: Path, data: dict, force: bool) -> Path:
    if path.exists() and not force:
        raise SystemExit(f"{path} exists (use --force to overwrite)")
    path.parent.mkdir(parents=True, exist_ok=True)
    head = ("# simplicio.video-contract/v1 — gerado por `simplicio-video init`. Preencha os TODO só com fatos de coleta/,\n"
            "# depois: simplicio-video validate / voice / render. Schema: schema/contract.schema.json\n")
    path.write_text(head + yaml.safe_dump(data, allow_unicode=True, sort_keys=False, width=120), encoding="utf8")
    return path
