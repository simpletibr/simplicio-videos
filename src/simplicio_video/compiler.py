"""Compile a contract into a self-contained HyperFrames project (the render workdir).

contract.yaml + timing.lock.json + template composition + motion blocks + client assets
  -> workdir/{index.html, compositions/, assets/, spec.json, meta.json, hyperframes.json, scripts/}
Template placeholders (index.template.html):
  {{vars:<bloco>}}      JSON of cenas[].motion[].params for that bloco (HTML-attribute safe)
  {{t:<cena>[+|-off]}}  absolute start of a scene (+/- offset), {{end:<cena>}}, {{dur:<cena>}}
  {{duracao}} {{fps}} {{width}} {{height}}   format values; {{cuts}} = [0, end1, end2, ...]
  {{bpm}} {{beat}}      trilha.bpm and one beat in seconds (sync visual hits with the music)
  {{words:<fala id>}}   word start times of that line, seconds from its SCENE start, "|"-joined (timing.lock.json)
  {{padrao:<bloco>}}    motion pattern id used by that bloco (lets one template swap the scene's main block per
                        contract, e.g. s2-main = tooth-character | icon-mascot in sazonal-dia-das-criancas)
The same placeholders work inside string params of cenas[].motion[].params (a param that is exactly one numeric
placeholder becomes a number), e.g. times: '{{words:vo1}}', bpm: '{{bpm}}', t_cut: '{{dur:s1}}'.
"""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from . import paths, perfis, trilha
from .contract import Contract, r4

PH = re.compile(r"\{\{\s*([a-z]+)(?::([\w-]+?)([+-][0-9][0-9.]*)?)?\s*\}\}")


def fmt(x: float) -> str:
    v = r4(x)
    return str(v)


def _subber(c: Contract, blocks: dict | None, lock: dict | None):
    sc = {s["id"]: s for s in c.scenes()}
    f = c.data["formato"]
    lines = {l["id"]: l for l in c.lines()}
    padrao = {m["bloco"]: m["padrao"] for s in c.data["cenas"] for m in s.get("motion", []) if m.get("bloco")}

    def sub(m: re.Match) -> str:
        kind, arg, off = m.group(1), m.group(2), m.group(3)
        if kind == "bpm":
            return fmt(c.data["trilha"]["bpm"])
        if kind == "beat":
            return str(round(60.0 / c.data["trilha"]["bpm"], 6))
        if kind == "words":
            if arg not in lines:
                raise SystemExit(f"{{{{words:{arg}}}}}: the contract has no fala '{arg}'")
            w = ((lock or {}).get("lines", {}).get(arg) or {}).get("words")
            if not w:
                raise SystemExit(f"{{{{words:{arg}}}}}: timing.lock.json has no word timings - run `simplicio-video voice <contrato>`")
            base = lines[arg]["t"] - sc[lines[arg]["scene"]]["_start"] + (float(off) if off else 0.0)
            return "|".join(str(round(base + x["t"], 3)) for x in w)
        if kind == "padrao":
            if arg not in padrao:
                raise SystemExit(f"template uses {{{{padrao:{arg}}}}} but no cenas[].motion[] has bloco: {arg}")
            return padrao[arg]
        if kind == "vars":
            if blocks is None:
                raise SystemExit("{{vars:...}} is only valid in the template")
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

    return sub


def render_template(html: str, c: Contract, blocks: dict, lock: dict | None = None) -> str:
    return PH.sub(_subber(c, blocks, lock), html)


def resolve_params(blocks: dict, c: Contract, lock: dict | None) -> dict:
    """Expand placeholders inside string params (numeric when the whole value is one placeholder)."""
    sub = _subber(c, None, lock)
    out = {}
    for bloco, params in blocks.items():
        res = {}
        for k, v in params.items():
            if isinstance(v, str) and "{{" in v:
                whole = PH.fullmatch(v.strip())
                v2 = PH.sub(sub, v)
                if whole and whole.group(1) != "words":
                    try:
                        v2 = float(v2) if "." in v2 else int(v2)
                    except ValueError:
                        pass
                v = v2
            res[k] = v
        out[bloco] = res
    return out


def template_meta(c: Contract) -> tuple[dict, Path]:
    tdir = c.template_dir()
    t = json.loads((tdir / "template.json").read_text(encoding="utf8"))
    return t, tdir / t["composicao"].get("dir", "composition")


MARCA_PADRAO_DAGUA = "Prévia"  # neutro: o motor não tem marca própria (issue #76)


def marca_spec(d: dict) -> dict:
    """`marca` do spec.json: marca d'água e crédito final com os padrões preenchidos (sem crédito = null)."""
    m = d.get("marca") or {}
    return {"dagua": m.get("dagua", MARCA_PADRAO_DAGUA), "credito": m.get("credito") or None}


def build_spec(c: Contract, lock: dict | None) -> dict:
    d = c.data
    variables: dict = {}
    for s in d["cenas"]:
        variables.update(s.get("textos", {}))
    variables.update(d.get("variaveis", {}))
    blocks = resolve_params({m["bloco"]: m.get("params", {}) for s in d["cenas"] for m in s.get("motion", []) if m.get("bloco")}, c, lock)
    tr = d["trilha"]
    audio = {"bpm": tr["bpm"], "duration_s": d["formato"]["duracao_s"], "seed": tr["seed"], "music": tr["music"],
             "master": tr["master"], "cues": c.cues()}
    v = d["voz"]
    enabled = bool(v.get("habilitada", True) and c.lines())
    voice = {"enabled": enabled, "gain_db": v.get("gain_db", 0), "duck_music_db": v.get("duck_music_db", 0),
             "duck_sfx_db": v.get("duck_sfx_db", 0),
             "lines": [{"id": l["id"], "t": l["t"], "max_s": l["max_s"], "scene": l["scene"], "text": l["texto"],
                        **({"say": l["say"]} if "say" in l else {})} for l in c.lines()]}
    spec = {"variables": variables, "blocks": blocks, "audio": audio, "voice": voice, "marca": marca_spec(d)}
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
                shutil.copy2(paths.data_dir() / "motion" / "patterns" / m["padrao"] / "block.html", dst)
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
    if c.data["trilha"]["music"].get("arquivo"):  # trilha de arquivo: arranjada aqui (cortes); o build.mjs só a lê
        spec["audio"]["music"] = {**spec["audio"]["music"], "arquivo": trilha.prepara(c, workdir, lock)}
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
    perfil = c.data["saida"].get("qualidade", "master")
    if perfil != "thumb":  # argumentos de saída do ffmpeg para o master.sh (um por linha); thumb não grava MP4
        (workdir / "perfil.args").write_text("\n".join(perfis.args_saida(perfil)) + "\n", encoding="utf8")
    html = render_template((comp / entry).read_text(encoding="utf8"), c, spec["blocks"], lock)
    (workdir / "index.html").write_text(html, encoding="utf8")
    meta = {"id": f"{c.data['cliente']['slug']}-{c.data['campanha']['id'].lower()}",
            "name": f"{c.data['cliente']['nome']} — {c.data['campanha'].get('titulo', c.data['campanha']['id'])}"}
    (workdir / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf8")
    return spec
