"""Load, schema-check and semantically validate a simplicio.video-contract/v1 YAML file."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

from . import paths

EPS = 1e-6


def r4(x: float) -> float:
    """Round scene-relative -> absolute times so float noise never reaches the engine (6.75 + 0.05 -> 6.8)."""
    v = round(float(x), 4)
    return int(v) if v == int(v) else v


@dataclass
class Report:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


@dataclass
class Contract:
    path: Path
    data: dict
    home: Path

    @property
    def dir(self) -> Path:
        return self.path.parent

    def rel(self, p: str) -> Path:
        return (self.dir / p).resolve()

    # ---- timeline ----
    def scenes(self) -> list[dict]:
        out, t = [], 0.0
        for c in self.data["cenas"]:
            out.append({**c, "_start": r4(t), "_end": r4(t + c["duracao_s"])})
            t += c["duracao_s"]
        return out

    def cuts(self) -> list[float]:
        sc = self.scenes()
        return [0] + [s["_end"] for s in sc]

    def lines(self) -> list[dict]:
        """Voice lines with absolute start time, in scene order."""
        res = []
        for s in self.scenes():
            f = s.get("fala")
            if f:
                res.append({**f, "scene": s["id"], "t": r4(s["_start"] + f["inicio_s"]), "_scene_end": s["_end"]})
        return res

    def cues(self) -> list[dict]:
        res = []
        for s in self.scenes():
            for x in s.get("sfx", []):
                cue = {"id": x["id"], "t": r4(s["_start"] + x["t"]), "sfx": x["tipo"]}
                for k in ("args", "gain_db", "pan", "duck_db"):
                    if k in x:
                        cue[k] = x[k]
                res.append(cue)
        return res

    def template_dir(self) -> Path:
        t = self.data["template"]
        cand = paths.data_dir() / "templates" / t
        if "/" not in t and cand.is_dir():
            return cand
        return self.rel(t)

    def sha256(self) -> str:
        return hashlib.sha256(canonical(self.data).encode()).hexdigest()


def canonical(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def load(path: str | Path) -> Contract:
    p = Path(path).resolve()
    if not p.is_file():
        raise SystemExit(f"contract not found: {p}")
    data = yaml.safe_load(p.read_text(encoding="utf8"))
    if not isinstance(data, dict):
        raise SystemExit(f"{p}: not a YAML mapping")
    return Contract(p, data, paths.home(p.parent))


def schema_errors(data: dict) -> list[str]:
    schema = json.loads(paths.schema_path().read_text(encoding="utf8"))
    v = Draft202012Validator(schema)
    errs = []
    for e in sorted(v.iter_errors(data), key=lambda e: list(e.absolute_path)):
        loc = "/".join(str(x) for x in e.absolute_path) or "(root)"
        errs.append(f"schema: {loc}: {e.message}")
    return errs


def load_lock(c: Contract) -> dict | None:
    lp = c.dir / "timing.lock.json"
    return json.loads(lp.read_text(encoding="utf8")) if lp.is_file() else None


DRIVE_FORA = ("drive: o bloco drive saiu do contrato (issue #75); a entrega (Drive, link, Real Oficial) "
              "fica fora do motor. Remova a chave drive do contrato.")


def validate(c: Contract, need_lock: bool = False) -> Report:
    if "drive" in c.data:
        return Report(errors=[DRIVE_FORA])
    rep = Report(errors=schema_errors(c.data))
    if rep.errors:
        return rep
    d = c.data
    # ---- durations ----
    total = sum(s["duracao_s"] for s in d["cenas"])
    if abs(total - d["formato"]["duracao_s"]) > EPS:
        rep.errors.append(f"durations: sum of cenas[].duracao_s = {r4(total)} s != formato.duracao_s = {d['formato']['duracao_s']} s")
    ids = [s["id"] for s in d["cenas"]]
    if len(set(ids)) != len(ids):
        rep.errors.append("cenas: duplicated scene id")
    # ---- template ----
    tdir = c.template_dir()
    tjson = tdir / "template.json"
    if not tjson.is_file():
        rep.errors.append(f"template: {d['template']} not found ({tjson})")
    else:
        comp = json.loads(tjson.read_text(encoding="utf8")).get("composicao")
        if not comp:
            rep.errors.append(f"template: {d['template']} has no 'composicao' (skeleton templates cannot render yet)")
        else:
            entry = tdir / comp.get("dir", "composition") / comp.get("entrada", "index.template.html")
            if not entry.is_file():
                rep.errors.append(f"template: composition entry missing: {entry}")
            want = comp.get("cenas")
            if want and want != ids:
                rep.errors.append(f"template: scene ids {ids} != template composition scenes {want}")
            fixed = comp.get("duracao_fixa_s")
            if fixed and abs(fixed - d["formato"]["duracao_s"]) > EPS:
                rep.errors.append(f"template: composition is authored for exactly {fixed} s (formato.duracao_s = {d['formato']['duracao_s']})")
            used = {m.get("bloco") for s in d["cenas"] for m in s.get("motion", []) if m.get("bloco")}
            missing = [b for b in comp.get("blocos", []) if b not in used]
            if missing:
                rep.errors.append(f"template: composition needs blocos {missing} (cenas[].motion[].bloco)")
    # ---- motion patterns ----
    pdir = paths.data_dir() / "motion" / "patterns"
    blocks = []
    for s in d["cenas"]:
        for m in s.get("motion", []):
            pj = pdir / m["padrao"] / "pattern.json"
            if not pj.is_file():
                rep.errors.append(f"motion: {s['id']}: pattern '{m['padrao']}' not in motion/patterns/")
                continue
            meta = json.loads(pj.read_text(encoding="utf8"))
            if m.get("bloco"):
                blocks.append(m["bloco"])
                if not (pdir / m["padrao"] / "block.html").is_file():
                    rep.errors.append(f"motion: {s['id']}: pattern '{m['padrao']}' has no block.html (status {meta.get('status')}) but is used as bloco")
    if len(set(blocks)) != len(blocks):
        rep.errors.append("motion: duplicated bloco id")
    # ---- assets ----
    items = list(d.get("assets", []))
    logo = (d.get("marca") or {}).get("logo")
    if logo:
        items.append(logo)
    for a in items:
        if not c.rel(a["arquivo"]).is_file():
            rep.errors.append(f"assets: missing file {a['arquivo']} (-> {a['destino']})")
    # ---- assets from the Openverse library: declared provenance, review for the request, rights and credit (offline) ----
    from . import openverse_contract  # lazy: a contract with no asset never loads it
    ov = openverse_contract.verify(c)
    rep.errors += ov.errors
    rep.warnings += ov.warnings
    # ---- voice fits the scene, never sped up ----
    v = d["voz"]
    jcut = v.get("jcut_max_s", 0.15)
    lines = c.lines()
    lids = [l["id"] for l in lines]
    if len(set(lids)) != len(lids):
        rep.errors.append("fala: duplicated line id")
    for l in lines:
        slot_end = l["t"] + l["max_s"]
        if slot_end > l["_scene_end"] + jcut + EPS:
            rep.errors.append(f"fala {l['id']}: slot ends at {r4(slot_end)} s, past scene {l['scene']} end {l['_scene_end']} s + J-cut {jcut} s")
        if slot_end > d["formato"]["duracao_s"] + EPS:
            rep.errors.append(f"fala {l['id']}: slot ends after the video ({r4(slot_end)} s)")
    if v.get("habilitada", True) and lines:
        lock = load_lock(c)
        if lock is None:
            (rep.errors if need_lock else rep.warnings).append("voice: timing.lock.json missing - run `simplicio-video voice <contrato>`")
        else:
            for l in lines:
                m = lock.get("lines", {}).get(l["id"])
                if not m:
                    (rep.errors if need_lock else rep.warnings).append(f"voice: {l['id']} not in timing.lock.json - run voice")
                    continue
                if m["text"] != l["texto"] or m.get("say") != l.get("say", l["texto"]):
                    (rep.errors if need_lock else rep.warnings).append(f"voice: {l['id']} text changed since timing.lock.json - run voice")
                if m["dur_s"] > l["max_s"] + EPS:
                    rep.errors.append(f"voice: {l['id']} take {m['dur_s']:.3f} s > max_s {l['max_s']} s (no time-stretch: shorten text or widen the slot)")
                if not c.rel(m["file"]).is_file():
                    rep.errors.append(f"voice: {l['id']} file missing: {m['file']}")
    # ---- sfx inside the video ----
    for cue in c.cues():
        if cue["t"] >= d["formato"]["duracao_s"]:
            rep.errors.append(f"sfx {cue['id']}: t={cue['t']} s outside the video")
    # ---- unfilled skeleton ----
    def walk(o, loc):
        if isinstance(o, dict):
            for k, x in o.items():
                walk(x, f"{loc}/{k}")
        elif isinstance(o, list):
            for i, x in enumerate(o):
                walk(x, f"{loc}/{i}")
        elif isinstance(o, str) and "TODO" in o:
            rep.errors.append(f"todo: {loc.lstrip('/')} still has a TODO: {o[:60]}")
    walk(d, "")
    if not (d.get("marca") or {}).get("logo"):
        rep.warnings.append("marca.logo is null: text lockup only (never recreate a logo)")
    return rep
