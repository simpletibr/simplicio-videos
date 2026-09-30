"""Compile a contract into a self-contained HyperFrames project (the render workdir).

contract.yaml + timing.lock.json + template composition + motion blocks + client assets
  -> workdir/{index.html, compositions/, assets/, spec.json, meta.json, hyperframes.json, scripts/}
Template placeholders (index.template.html):
  {{vars:<bloco>}}      JSON of cenas[].motion[].params for that bloco (HTML-attribute safe)
  {{t:<cena>[+|-off]}}  absolute start of a scene (+/- offset), {{end:<cena>}}, {{dur:<cena>}}
  {{duracao}} {{fps}} {{width}} {{height}}   format values; {{cuts}} = [0, end1, end2, ...]
"""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from . import paths
from .contract import Contract, r4

PH = re.compile(r"\{\{\s*([a-z]+)(?::([\w-]+?)([+-][0-9][0-9.]*)?)?\s*\}\}")


def fmt(x: float) -> str:
    v = r4(x)
    return str(v)


def render_template(html: str, c: Contract, blocks: dict) -> str:
    sc = {s["id"]: s for s in c.scenes()}
    f = c.data["formato"]

    def sub(m: re.Match) -> str:
        kind, arg, off = m.group(1), m.group(2), m.group(3)
        if kind == "vars":
            if arg not in blocks:
                raise SystemExit(f"template uses {{{{vars:{arg}}}}} but no cenas[].motion[] has bloco: {arg}")
            return json.dumps(blocks[arg], ensure_ascii=False, separators=(",", ":")).replace("&", "&amp;").replace("'", "&#39;")
        if kind in ("t", "end", "dur"):
            if arg not in sc:
                raise SystemExit(f"template uses {{{{{kind}:{arg}}}}} but the contract has no scene '{arg}'")
            s = sc[arg]
            base = {"t": s["_start"], "end": s["_end"], "dur": s["duracao_s"]}[kind]
            return fmt(base + (float(off) if off else 0.0))
        if kind == "duracao":
            return fmt(f["duracao_s"])
        if kind in ("fps", "width", "height"):
            return str(f[kind])
        if kind == "cuts":
            return "[" + ", ".join(fmt(x) for x in c.cuts()) + "]"
        raise SystemExit(f"unknown template placeholder {m.group(0)}")

    return PH.sub(sub, html)


def template_meta(c: Contract) -> tuple[dict, Path]:
    tdir = c.template_dir()
    t = json.loads((tdir / "template.json").read_text(encoding="utf8"))
    return t, tdir / t["composicao"].get("dir", "composition")


def build_spec(c: Contract, lock: dict | None) -> dict:
    d = c.data
    variables: dict = {}
    for s in d["cenas"]:
        variables.update(s.get("textos", {}))
    variables.update(d.get("variaveis", {}))
    blocks = {m["bloco"]: m.get("params", {}) for s in d["cenas"] for m in s.get("motion", []) if m.get("bloco")}
    tr = d["trilha"]
    audio = {"bpm": tr["bpm"], "duration_s": d["formato"]["duracao_s"], "seed": tr["seed"], "music": tr["music"],
             "master": tr["master"], "cues": c.cues()}
    v = d["voz"]
    enabled = bool(v.get("habilitada", True) and c.lines())
    voice = {"enabled": enabled, "gain_db": v.get("gain_db", 0), "duck_music_db": v.get("duck_music_db", 0),
             "duck_sfx_db": v.get("duck_sfx_db", 0),
             "lines": [{"id": l["id"], "t": l["t"], "max_s": l["max_s"], "scene": l["scene"], "text": l["texto"],
                        **({"say": l["say"]} if "say" in l else {})} for l in c.lines()]}
    spec = {"variables": variables, "blocks": blocks, "audio": audio, "voice": voice}
    if d.get("placas_video"):
        spec["clips"] = {"slots": d["placas_video"]}
    return spec


def compile_project(c: Contract, workdir: Path, lock: dict | None) -> dict:
    t, comp = template_meta(c)
    entry = t["composicao"].get("entrada", "index.template.html")
    if workdir.exists():
        shutil.rmtree(workdir)
    shutil.copytree(comp, workdir, ignore=shutil.ignore_patterns(entry, ".DS_Store"))
    (workdir / "scripts").mkdir(exist_ok=True)
    for f in ("build.mjs", "master.sh"):
        shutil.copy2(paths.ENGINE_DIR / f, workdir / "scripts" / f)
    # motion blocks used as instances -> compositions/<pattern>.html
    for s in c.data["cenas"]:
        for m in s.get("motion", []):
            if m.get("bloco"):
                dst = workdir / "compositions" / f"{m['padrao']}.html"
                dst.parent.mkdir(exist_ok=True)
                shutil.copy2(c.home / "motion" / "patterns" / m["padrao"] / "block.html", dst)
    # client assets
    items = list(c.data.get("assets", []))
    logo = (c.data.get("marca") or {}).get("logo")
    if logo:
        items.append(logo)
    for a in items:
        dst = workdir / a["destino"]
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(c.rel(a["arquivo"]), dst)
    for slot in c.data.get("placas_video", []):
        src = c.rel(slot["file"])
        if src.is_file():
            (workdir / slot["file"]).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, workdir / slot["file"])
    spec = build_spec(c, lock)
    # narration from timing.lock.json -> engine manifest
    if spec["voice"]["enabled"]:
        if not lock:
            raise SystemExit("voice enabled but timing.lock.json missing - run `simplicio-video voice <contrato>` first")
        vo = workdir / "assets/audio/vo"
        vo.mkdir(parents=True, exist_ok=True)
        man = {"provider": lock["provider"], "lines": {}}
        for l in spec["voice"]["lines"]:
            m = lock["lines"][l["id"]]
            name = Path(m["file"]).name
            shutil.copy2(c.rel(m["file"]), vo / name)
            man["lines"][l["id"]] = {"file": f"assets/audio/vo/{name}", "t": l["t"], "dur_s": m["dur_s"], "max_s": l["max_s"],
                                     "text": l["text"], "say": m["say"]}
        (vo / "manifest.json").write_text(json.dumps(man, indent=2, ensure_ascii=False) + "\n", encoding="utf8")
    (workdir / "spec.json").write_text(json.dumps(spec, indent=2, ensure_ascii=False) + "\n", encoding="utf8")
    html = render_template((comp / entry).read_text(encoding="utf8"), c, spec["blocks"])
    (workdir / "index.html").write_text(html, encoding="utf8")
    meta = {"id": f"{c.data['cliente']['slug']}-{c.data['campanha']['id'].lower()}",
            "name": f"{c.data['cliente']['nome']} — {c.data['campanha'].get('titulo', c.data['campanha']['id'])}"}
    (workdir / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf8")
    return spec
