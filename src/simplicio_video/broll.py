"""`--visual broll`: impact/dopamine previews built from real footage, on top of the APPROVED voice takes.

Two files per company, next to the existing contract (previas/<slug>/broll/):
  concept.yaml  the company's own visual concept (palette from logo/site, fonts, rhythm, transitions, type animation,
                overlays, hook style, music/SFX). Two companies never share a concept: it is the brand, not a skin.
  plan.yaml     the edit: shots (real clip/photo per spoken idea, cut every 0.5-1.5 s), kinetic text cards synced
                word by word to timing.lock.json, stickers/icons, logo CTA.
Assets live in broll/assets/ and every one of them must be listed in <slug>/assets-licencas.csv (source, link, licence).

Pipeline (deterministic, no TTS, no network): decode + frame every shot to 9:16 -> Ken Burns / push-in -> transitions
(6-10 frames) -> concept grade + particles -> text/stickers/logo layer -> H.264; audio = voice takes at the lock times +
procedural music ducked under the voice + synthesised SFX on cuts -> loudness master -> the standard preview post
(540x960, watermark, Wesley Simplicio end card) -> preview-v2.mp4 + preview-v2.manifest.json + broll-layout.json."""
from __future__ import annotations

import csv
import json
import math
import re
import subprocess
import time
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import yaml
from PIL import Image, ImageDraw, ImageFilter

from . import broll_audio as au
from . import broll_fx as fx
from . import paths

FPS = 30
CUT_MIN, CUT_MAX, HOLD_MAX = 0.35, 1.6, 2.6   # seconds per shot (hold: logo/CTA shots with continuous motion)
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp"}
SAFE = (0.05, 0.075, 0.95, 0.885)               # text safe area (x0, y0, x1, y1) as fractions of the frame
MIN_GAP_EM = 0.15
# health sector (med spa, clinics): no trademarks of regulated products, no results promises, no before/after
HEALTH_FORBIDDEN = [
    (r"\b(?:botox|dysport|xeomin|jeuveau|daxxify|juv[eé]derm|restylane|sculptra|radiesse|kybella|morpheus8|"
     r"coolsculpting|hydrafacial|ultherapy|emsculpt|fraxel|clear\s*\+?\s*brilliant)\b", "marca registrada (saúde)"),
    (r"\b(?:results?|resultados?|ergebnis\w*|r[ée]sultats?)\b", "promessa de resultado (saúde)"),
    (r"\b(?:younger|years? younger|anti-?aging|wrinkle-?free|erase|eliminate|permanent\w*|instant\w*|painless|no pain|zero downtime)\b", "promessa (saúde)"),
    (r"\b(?:before\b|after\b)", "antes/depois (saúde)"),
]


PARTICLES = ("bubbles", "leak", "sparkles", "confetti", "steam", "film", "rays", "frame")
ANIMS = ("pop", "rise", "slam", "drop", "type", "fade")
PANELS = ("pill", "bar", "box", "none", None)


class BrollError(ValueError):
    pass


# ================================================================ loading
def _load_yaml(p: Path) -> dict:
    if not p.is_file():
        raise BrollError(f"arquivo ausente: {p}")
    return yaml.safe_load(p.read_text(encoding="utf8")) or {}


def norm_word(w: str) -> str:
    w = unicodedata.normalize("NFKD", w.lower())
    return re.sub(r"[^a-z0-9]", "", "".join(c for c in w if not unicodedata.combining(c)))


@dataclass
class Timing:
    lines: dict  # id -> {"t", "dur_s", "words": [(word, t_abs, end_abs)], "file"}
    voz_pt_animada: bool = False  # timing.lock gravado com a voz enérgica pt (liga o preset de trilha pt)

    @classmethod
    def load(cls, pdir: Path) -> "Timing":
        lock = json.loads((pdir / "timing.lock.json").read_text(encoding="utf8"))
        out = {}
        for lid, v in lock["lines"].items():
            if not v.get("fits", True):
                raise BrollError(f"{lid}: fala não cabe no slot (timing.lock) — o broll nunca regenera voz")
            words = [(w["w"], round(v["t"] + w["t"], 3), round(v["t"] + w.get("end", w["t"] + 0.2), 3)) for w in v.get("words", [])]
            out[lid] = {"t": float(v["t"]), "dur_s": float(v["dur_s"]), "end": round(v["t"] + v["dur_s"], 3), "words": words,
                        "file": pdir / v["file"], "text": v.get("text", "")}
        return cls(out, bool(lock.get("voz_pt_animada")))

    def resolve(self, ref, dur: float) -> float:
        """Number, 'end', 'vo1', 'vo1.end', 'vo1:grooming' (onset), 'vo1:grooming.end', 'vo1#3' (0-based word index), each with
        an optional +/-offset ('vo2:trust+0.1')."""
        if isinstance(ref, (int, float)):
            return float(ref)
        s = str(ref).strip()
        m = re.fullmatch(r"(.+?)([+-]\d+(?:\.\d+)?)?", s)
        base, off = m.group(1), float(m.group(2) or 0)
        if base == "end":
            return dur + off
        try:
            return float(base) + off
        except ValueError:
            pass
        base = re.sub(r"^(vo\d+:.+?)[.,?!;]+((?:\.end)?)$", r"\1\2", base)  # 'vo2:here.' == 'vo2:here' (punctuation of the take)
        m = re.fullmatch(r"(vo\d+)(?:([:#])([^.]+?))?(\.end)?", base)
        if not m or m.group(1) not in self.lines:
            raise BrollError(f"referência de tempo inválida: {ref!r}")
        L = self.lines[m.group(1)]
        if not m.group(2):
            return (L["end"] if m.group(4) else L["t"]) + off
        if m.group(2) == "#":
            k = int(m.group(3))
            if not 0 <= k < len(L["words"]):
                raise BrollError(f"{ref!r}: índice de palavra fora da fala")
            w = L["words"][k]
        else:
            want = norm_word(m.group(3))
            hits = [w for w in L["words"] if norm_word(w[0]) == want]
            if not hits:
                raise BrollError(f"{ref!r}: palavra não está na fala {m.group(1)} ({L['text']!r})")
            w = hits[0]
        return (w[2] if m.group(4) else w[1]) + off


# ================================================================ concept
DEFAULT_CONCEPT = {
    "palette": {"primary": "#222222", "secondary": "#ffffff", "accent": "#ffcc00", "ink": "#111111", "light": "#ffffff"},
    "type": {"font": "motion/assets/fonts/Inter.ttf", "variation": None, "axes": None, "size": 0.12, "case": "upper",
             "tracking": 0.0, "anim": "pop", "fill": "light", "emph": "accent", "stroke": None, "stroke_w": 0,
             "shadow": "#000000", "shadow_alpha": 0.55, "shadow_blur": 0.06, "shadow_dy": 0.04,
             "panel": "pill", "panel_colors": ["primary"], "panel_alpha": 0.92, "line_gap": 0.12, "word_gap": 0.28,
             "scrim": 0.0, "fonts": {}},
    "rhythm": {"bpm": 120},
    "transitions": {"default": ["cut"], "frames": 8, "flash": "#ffffff", "leak": "#ffd2a8"},
    "grade": {"sat": 1.0, "contrast": 1.0, "warmth": 0.0, "lift": 0.0, "vignette": 0.0, "tint": None, "tint_amt": 0.0},
    "overlays": {"particles": None, "density": 8, "grain": 0.0, "leak_strength": 0.3, "emoji_font": None},
    "music": {"style": "bouncy", "bpm": 120, "db": -9.0, "duck_db": 9.0, "drop_at": None},
    "sfx": {"cut": "whoosh", "sticker": "pop", "card": None, "hook": "impact", "logo": "shimmer", "db": -15.0},
    "logo": {"plate": "round", "plate_color": "light", "size": 0.62, "anim": "pop"},
    "setor": None,
}


# Regra permanente do Wesley (2026-10-02): vídeo em português sempre mais animado que o em inglês. Preset de trilha pt:
# estilos calmos viram um parente animado, BPM entra na faixa 124-135, camada extra de percussão/brilho (lift), trilha
# +1 dB e ducking no máx. 8 dB. Liga sozinho quando o timing.lock traz voz_pt_animada (voz enérgica pt gravada pelo
# `voice` com o estilo novo), então voz e trilha mudam juntas e prévias antigas re-renderizam idênticas. concept
# music.pt_animado: true força (só pt), false desliga. Inglês e demais idiomas: trilha do concept sem mudança.
PT_MUSIC_PRESET = {"bpm_min": 124, "bpm_max": 135, "lift": 1.0, "db_boost": 1.0, "duck_db_max": 8.0,
                   "style_map": {"elegant": "bouncy", "lofi": "tropical", "bossa": "samba", "cinematic": "house"}}


def music_for(M: dict, lang: str, voz_pt_animada: bool = False) -> dict:
    """Trilha efetiva do render: o concept, ou o preset pt animado aplicado por cima (ver PT_MUSIC_PRESET)."""
    flag = M.get("pt_animado", "auto")
    on = str(lang or "").lower().startswith("pt") and (flag is True or (flag == "auto" and voz_pt_animada))
    out = {k: v for k, v in M.items() if k != "pt_animado"}
    out["lift"] = 0.0
    if not on:
        return out
    P = PT_MUSIC_PRESET
    out["style"] = P["style_map"].get(M["style"], M["style"])
    out["bpm"] = float(min(P["bpm_max"], max(P["bpm_min"], float(M["bpm"]))))
    out["db"] = float(M["db"]) + P["db_boost"]
    out["duck_db"] = min(float(M["duck_db"]), P["duck_db_max"])
    out["lift"] = P["lift"]
    out["preset"] = "pt-animado"
    return out


def _merge(a: dict, b: dict) -> dict:
    out = dict(a)
    for k, v in (b or {}).items():
        out[k] = _merge(a[k], v) if isinstance(v, dict) and isinstance(a.get(k), dict) else v
    return out


def load_concept(path: Path) -> dict:
    c = _merge(DEFAULT_CONCEPT, _load_yaml(path))
    for k in ("primary", "secondary", "accent", "ink", "light"):
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", str(c["palette"].get(k, ""))):
            raise BrollError(f"concept: palette.{k} precisa ser #rrggbb")
    for k in c["transitions"]["default"]:
        if k not in fx.TRANSITIONS:
            raise BrollError(f"concept: transição desconhecida {k!r} (use {', '.join(fx.TRANSITIONS)})")
    if not 6 <= int(c["transitions"]["frames"]) <= 10:
        raise BrollError("concept: transitions.frames deve ficar entre 6 e 10")
    parts = c["overlays"].get("particles") or []
    for k in ([parts] if isinstance(parts, str) else parts):
        if k not in PARTICLES:
            raise BrollError(f"concept: overlays.particles desconhecido {k!r} (use {', '.join(PARTICLES)})")
    if c["type"].get("anim") not in ANIMS:
        raise BrollError(f"concept: type.anim desconhecida {c['type'].get('anim')!r} (use {', '.join(ANIMS)})")
    if c["type"].get("panel") not in PANELS:
        raise BrollError(f"concept: type.panel desconhecido {c['type'].get('panel')!r} (use {', '.join(str(x) for x in PANELS)})")
    from .broll_audio import STYLES
    if c["music"].get("style") not in STYLES:
        raise BrollError(f"concept: music.style desconhecido {c['music'].get('style')!r} (use {', '.join(STYLES)})")
    if c["music"].get("pt_animado", "auto") not in ("auto", True, False):
        raise BrollError("concept: music.pt_animado deve ser auto, true ou false")
    return c


def color(c: dict, v, alpha: float | None = None) -> tuple:
    if v is None:
        return None
    s = c["palette"].get(v, v) if isinstance(v, str) else v
    rgb = fx.hex_rgb(s) if isinstance(s, str) else tuple(s[:3])
    return rgb + ((int(round(alpha * 255)),) if alpha is not None else (255,))


def font_path(c: dict, home: Path, key: str | None = None) -> tuple[str, str | None, tuple | None]:
    T = c["type"]
    spec = T["fonts"].get(key) if key else None
    f, var, axes = (spec.get("font", T["font"]), spec.get("variation"), spec.get("axes")) if spec else (T["font"], T.get("variation"), T.get("axes"))
    p = Path(f)
    if not p.is_absolute():
        p = home / f
    if not p.is_file():
        raise BrollError(f"fonte ausente: {p}")
    return str(p), var, tuple(axes) if axes else None


# ================================================================ plan
@dataclass
class Shot:
    i: int
    src: Path
    start: float
    end: float
    tin: float = 0.0
    crop: float | str = "auto"
    cy: float = 0.5
    zoom: tuple = (1.0, 1.08)
    pan: tuple = ((0.0, 0.0), (0.0, 0.0))
    speed: float = 1.0
    tx: str | None = None
    tx_frames: int | None = None
    hold: bool = False
    flip: bool = False
    dim: float = 0.0
    blur: float = 0.0
    is_image: bool = False
    note: str = ""

    @property
    def dur(self) -> float:
        return self.end - self.start


@dataclass
class Card:
    i: int
    tokens: list            # [(display, t_on, line_no, emph)]
    start: float
    end: float
    y: float = 0.42
    size: float = 1.0
    font: str | None = None
    case: str | None = None
    anim: str | None = None
    panel: str | None = None
    sync: str | None = None
    colors: list | None = None   # per-card pill colours (palette keys or #hex), overrides type.panel_colors


@dataclass
class Sticker:
    i: int
    start: float
    end: float
    x: float
    y: float
    size: float
    emoji: str | None = None
    icon: str | None = None
    color: str | None = None
    anim: str = "pop"
    count: int = 1
    image: Path | None = None


@dataclass
class Plan:
    dur: float
    shots: list
    cards: list
    stickers: list
    logo: dict | None
    hook: dict
    sfx: list = field(default_factory=list)


def parse_card_text(c: dict, timing: Timing, raw: dict, dur: float, i: int) -> Card:
    text = str(raw["text"])
    sync = raw.get("sync")
    lines = [ln.split() for ln in text.split("/")]
    toks = []
    if sync:
        if sync not in timing.lines:
            raise BrollError(f"texto {i}: sync {sync!r} não existe no timing.lock")
        words = timing.lines[sync]["words"]
        cur = 0
        last_t = timing.resolve(raw["at"], dur) if "at" in raw else (words[0][1] if words else timing.lines[sync]["t"])
        for ln_no, ln in enumerate(lines):
            for w in ln:
                nw = norm_word(w)
                hit = next((k for k in range(cur, len(words)) if norm_word(words[k][0]) == nw), None) if nw else None
                if hit is not None:
                    last_t = words[hit][1]
                    cur = hit + 1
                elif nw:
                    raise BrollError(f"texto {i}: {w!r} não aparece (em ordem) na fala {sync} — o texto tem que ser o que a voz diz")
                toks.append([w, last_t, ln_no, w.strip(".,!?:;").lower() in [e.lower() for e in raw.get("emph", [])]])
        start = timing.resolve(raw["at"], dur) if "at" in raw else min(t[1] for t in toks) - 0.06
    else:
        start = timing.resolve(raw["at"], dur)
        for ln_no, ln in enumerate(lines):
            for k, w in enumerate(ln):
                toks.append([w, start + 0.07 * len(toks), ln_no, w.lower() in [e.lower() for e in raw.get("emph", [])]])
    end = timing.resolve(raw["until"], dur) if "until" in raw else max(t[1] for t in toks) + 0.6
    if end <= start:
        raise BrollError(f"texto {i}: until antes do início")
    for t in toks:
        t[1] = max(start, t[1])
    return Card(i=i, tokens=[tuple(t) for t in toks], start=round(start, 3), end=round(end, 3), y=float(raw.get("y", 0.42)),
                size=float(raw.get("size", 1.0)), font=raw.get("font"), case=raw.get("case"), anim=raw.get("anim"),
                panel=raw.get("panel"), sync=sync, colors=list(raw["colors"]) if raw.get("colors") else None)


def load_plan(pdir: Path, timing: Timing, dur: float, c: dict, plan_path: Path | None = None) -> Plan:
    P = _load_yaml(plan_path or pdir / "broll" / "plan.yaml")
    adir = (plan_path or pdir / "broll" / "plan.yaml").parent / "assets"
    shots, t0 = [], 0.0
    raw_shots = P.get("shots") or []
    if not raw_shots:
        raise BrollError("plan: nenhuma cena (shots)")
    for k, s in enumerate(raw_shots):
        src = Path(s["src"])
        src = src if src.is_absolute() else adir / src
        if not src.is_file():
            raise BrollError(f"cena {k}: asset ausente {src}")
        end = dur if k == len(raw_shots) - 1 else (timing.resolve(s["until"], dur) if "until" in s else t0 + float(s["dur"]))
        sh = Shot(i=k, src=src, start=round(t0, 3), end=round(end, 3), tin=float(s.get("in", 0)), crop=s.get("crop", "auto"),
                  cy=float(s.get("cy", 0.5)), zoom=tuple(s.get("zoom", (1.0, 1.25) if src.suffix.lower() in IMAGE_EXT else (1.0, 1.08))),
                  pan=tuple(tuple(x) for x in s.get("pan", ((0, 0), (0, 0)))), speed=float(s.get("speed", 1.0)),
                  tx=s.get("tx"), tx_frames=s.get("tx_frames"), hold=bool(s.get("hold", False)), flip=bool(s.get("flip", False)),
                  dim=float(s.get("dim", 0)), blur=float(s.get("blur", 0)), is_image=src.suffix.lower() in IMAGE_EXT,
                  note=str(s.get("note", "")))
        if sh.tx and sh.tx not in fx.TRANSITIONS:
            raise BrollError(f"cena {k}: transição desconhecida {sh.tx!r}")
        if sh.tx_frames is not None and not 6 <= int(sh.tx_frames) <= 10:
            raise BrollError(f"cena {k}: tx_frames deve ficar entre 6 e 10")
        shots.append(sh)
        t0 = end
    cards = [parse_card_text(c, timing, raw, dur, k) for k, raw in enumerate(P.get("texts") or [])]
    handoff_cards(cards)
    stickers = []
    for k, s in enumerate(P.get("stickers") or []):
        if not (s.get("emoji") or s.get("icon") or s.get("image")):
            raise BrollError(f"sticker {k}: precisa de emoji, icon ou image")
        img = (adir / s["image"]) if s.get("image") else None
        if img is not None and not img.is_file():
            raise BrollError(f"sticker {k}: imagem ausente {img}")
        st = timing.resolve(s["at"], dur)
        en = timing.resolve(s["until"], dur) if "until" in s else st + 0.9
        stickers.append(Sticker(i=k, start=st, end=en, x=float(s.get("x", 0.5)), y=float(s.get("y", 0.2)), size=float(s.get("size", 0.16)),
                                emoji=s.get("emoji"), icon=s.get("icon"), color=s.get("color"), anim=s.get("anim", "pop"),
                                count=int(s.get("count", 1)), image=img))
    logo = None
    if P.get("logo"):
        L = dict(P["logo"])
        L["start"] = timing.resolve(L.get("at", "vo4"), dur)
        L["end"] = timing.resolve(L.get("until", "end"), dur)
        f = L.get("file")
        L["path"] = (adir / f) if f else (pdir / "coleta" / "logo.png")
        if not Path(L["path"]).is_file():
            raise BrollError(f"logo ausente: {L['path']}")
        logo = L
    return Plan(dur=dur, shots=shots, cards=cards, stickers=stickers, logo=logo, hook=P.get("hook") or {}, sfx=P.get("sfx") or [])


def handoff_cards(cards: list, near: float = 0.22) -> None:
    """Consecutive captions in the same screen band hand over instead of stacking: when the next card starts
    (its first word minus the lead-in) before the previous one ends, the previous one ends right there.
    Cards in different bands (|dy| > near) may coexist; the layout guard still checks them."""
    for a in cards:
        for b in cards:
            if b is a or b.start <= a.start or abs(b.y - a.y) > near:
                continue
            if b.start < a.end:
                a.end = round(b.start, 3)
        if a.end <= a.start:
            raise BrollError(f"texto {a.i}: o texto seguinte começa antes dele")


# ================================================================ validation (no rendering)
def check_plan(plan: Plan, c: dict) -> list[str]:
    """Editorial rules: every shot 0.35-1.6 s (hold shots <= 2.6 s), timeline covers 0..dur, transitions 6-10 frames,
    first cut inside the hook (<= 2 s), logo shown in the last seconds, no forbidden text."""
    from .intl import check_text
    errs = []
    if abs(plan.shots[0].start) > 1e-6 or abs(plan.shots[-1].end - plan.dur) > 1e-3:
        errs.append("cenas não cobrem 0..duração")
    for s in plan.shots:
        lim = HOLD_MAX if s.hold else CUT_MAX
        if s.dur < CUT_MIN - 1e-6 or s.dur > lim + 1e-6:
            errs.append(f"cena {s.i} ({s.src.name}) dura {s.dur:.2f} s (limite {CUT_MIN}-{lim} s)")
    if len(plan.shots) > 1 and plan.shots[1].start > 2.0 + 1e-6:
        errs.append("gancho sem corte nos 2 primeiros segundos")
    if not any(cd.start <= 0.6 for cd in plan.cards):
        errs.append("gancho sem texto grande até 0,6 s")
    if not plan.logo:
        errs.append("sem CTA com a logo do cliente")
    elif plan.logo["end"] < plan.dur - 0.05:
        errs.append("a logo precisa ficar até o fim do vídeo")
    texts = [" ".join(t[0] for t in cd.tokens) for cd in plan.cards]
    for t in texts:
        errs += [f"texto proibido: {x}" for x in check_text(t)]
        if c.get("setor") == "saude":
            errs += [f"texto proibido: {why}: {t!r}" for rx, why in HEALTH_FORBIDDEN if re.search(rx, t.lower())]
    return errs


def check_licenses(pdir: Path, plan: Plan) -> list[str]:
    f = pdir / "assets-licencas.csv"
    if not f.is_file():
        return [f"{f.name} ausente"]
    rows = list(csv.DictReader(f.open(encoding="utf8")))
    need = {"arquivo", "fonte", "link", "licenca"}
    if rows and not need <= set(rows[0]):
        return [f"{f.name}: colunas obrigatórias {sorted(need)}"]
    have = {r["arquivo"].strip() for r in rows if r.get("licenca", "").strip() and r.get("link", "").strip()}
    used = {s.src.name for s in plan.shots} | ({Path(plan.logo["path"]).name} if plan.logo else set()) | \
        {st.image.name for st in plan.stickers if st.image is not None}
    return [f"asset sem fonte/licença em {f.name}: {u}" for u in sorted(used - have)]


# ================================================================ frames
class ShotFrames:
    """Decoded, 9:16-framed frames of one shot (with transition padding), oversized for Ken Burns."""

    def __init__(self, sh: Shot, W: int, H: int, pad: float, log=print):
        self.sh = sh
        zmax = max(max(sh.zoom), 1.0) * 1.02
        self.DW, self.DH = int(math.ceil(W * zmax / 2) * 2), int(math.ceil(H * zmax / 2) * 2)
        self.W, self.H, self.pad = W, H, pad
        self.t0 = sh.start - pad
        self.n = int(math.ceil((sh.dur + 2 * pad) * FPS)) + 1
        self.crop_cx = None
        if sh.is_image:
            im = Image.open(sh.src).convert("RGB")
            if sh.flip:
                im = im.transpose(Image.FLIP_LEFT_RIGHT)
            cx = self._auto([np.asarray(im.resize((max(1, im.width // 4), max(1, im.height // 4))))], im.width, im.height) \
                if sh.crop == "auto" else float(sh.crop)
            x, y, w, h = fx.crop_box(im.width, im.height, W / H, cx, sh.cy)
            self.crop_cx = round(cx, 3)
            self.still = np.asarray(im.crop((x, y, x + w, y + h)).resize((self.DW, self.DH), Image.LANCZOS))
            self.frames = None
        else:
            self.still = None
            self.frames = self._decode()

    def _auto(self, frames, sw, sh_) -> float:
        return fx.saliency_center(frames, self.W / self.H) if frames else 0.5

    def _probe(self):
        o = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height:format=duration",
                            "-of", "json", str(self.sh.src)], capture_output=True, text=True, check=True).stdout
        j = json.loads(o)
        return j["streams"][0]["width"], j["streams"][0]["height"], float(j["format"]["duration"])

    def _decode(self) -> np.ndarray:
        sh = self.sh
        sw, shh, sdur = self._probe()
        speed = sh.speed
        src0 = sh.tin - self.pad * speed
        lead = 0
        if src0 < 0:
            lead = int(round(-src0 / speed * FPS))
            src0 = 0.0
        need = self.n - lead
        if src0 + need / FPS * speed > sdur - 0.05:
            raise BrollError(f"cena {sh.i}: {sh.src.name} tem {sdur:.2f} s; pedi {sh.tin:.2f}+{sh.dur:.2f} s (velocidade {speed})")
        if sh.crop == "auto":
            small = []
            for k in range(4):
                tt = src0 + (k + 0.5) / 4 * need / FPS * speed
                raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{tt:.3f}", "-i", str(sh.src), "-frames:v", "1",
                                      "-vf", "scale=320:-2", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True).stdout
                h = int(len(raw) / (320 * 3))
                if h:
                    small.append(np.frombuffer(raw[: 320 * 3 * h], np.uint8).reshape(h, 320, 3))
            cx = fx.saliency_center(small, self.W / self.H) if small else 0.5
        else:
            cx = float(sh.crop)
        self.crop_cx = round(cx, 3)
        x, y, w, h = fx.crop_box(sw, shh, self.W / self.H, cx, sh.cy)
        vf = f"crop={w}:{h}:{x}:{y}," + ("hflip," if sh.flip else "") + f"scale={self.DW}:{self.DH}:flags=bicubic,setpts=PTS/{speed},fps={FPS}"
        raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{src0:.3f}", "-i", str(sh.src), "-vf", vf, "-frames:v", str(need),
                              "-an", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True, check=True).stdout
        fs = len(raw) // (self.DW * self.DH * 3)
        arr = np.frombuffer(raw[: fs * self.DW * self.DH * 3], np.uint8).reshape(fs, self.DH, self.DW, 3)
        if fs == 0:
            raise BrollError(f"cena {sh.i}: nada decodificado de {sh.src.name}")
        if lead:
            arr = np.concatenate([np.repeat(arr[:1], lead, axis=0), arr])
        if len(arr) < self.n:
            arr = np.concatenate([arr, np.repeat(arr[-1:], self.n - len(arr), axis=0)])
        return arr

    def at(self, t: float) -> np.ndarray:
        sh = self.sh
        p = fx.clamp01((t - sh.start) / max(sh.dur, 1e-3))
        q = fx.ease_in_out(p) if sh.is_image else p
        z = sh.zoom[0] + (sh.zoom[1] - sh.zoom[0]) * q
        px = sh.pan[0][0] + (sh.pan[1][0] - sh.pan[0][0]) * q
        py = sh.pan[0][1] + (sh.pan[1][1] - sh.pan[0][1]) * q
        if self.still is not None:
            src = self.still
        else:
            k = int(round((t - self.t0) * FPS))
            src = self.frames[max(0, min(len(self.frames) - 1, k))]
        f = fx.view(src, self.W, self.H, zoom=z, px=px, py=py)
        if sh.blur:
            f = np.asarray(Image.fromarray(f).filter(ImageFilter.GaussianBlur(sh.blur * self.W / 540)))
        if sh.dim:
            f = (f.astype(np.float32) * (1 - sh.dim)).astype(np.uint8)
        return f


# ================================================================ text layout + drawing
@dataclass
class CardLayout:
    card: Card
    sprites: list   # per token: (sprite RGBA, cx, cy, w, h, line_no)
    lines: list     # per line: (x0, y0, x1, y1)
    font_px: int


def _case(s: str, mode: str) -> str:
    return s.upper() if mode == "upper" else s.lower() if mode == "lower" else s


def layout_card(c: dict, home: Path, cd: Card, W: int, H: int) -> CardLayout:
    T = c["type"]
    key = cd.font
    spec = T["fonts"].get(key, {}) if key else {}
    case = cd.case or spec.get("case") or T["case"]
    tracking = float(spec.get("tracking", T["tracking"]))
    fpath, var, axes = font_path(c, home, key)
    base = float(spec.get("size", T["size"])) * cd.size * W
    maxw = (SAFE[2] - SAFE[0]) * W * 0.92
    gap_em = float(T["word_gap"])
    nlines = max(t[2] for t in cd.tokens) + 1
    size = int(base)
    use_emph = spec.get("emph_font") is None and bool(T["fonts"].get("emph"))
    es_rel = float(T["fonts"]["emph"]["size"]) / float(T["size"]) if use_emph and T["fonts"]["emph"].get("size") else 1.0
    espec = T["fonts"]["emph"] if use_emph else {}
    ecase = espec.get("case") or case          # a script emphasis font usually wants case: none even when the base is upper
    etrack = float(espec.get("tracking", tracking))
    def _tc(tok):  # (case, tracking) of one token
        return (ecase, etrack) if (tok[3] and use_emph) else (case, tracking)
    while True:
        font = fx.load_font(fpath, size, var, axes)
        efit = None
        if use_emph and any(t[3] for t in cd.tokens):
            ef, ev, ea = font_path(c, home, "emph")
            efit = fx.load_font(ef, int(size * es_rel), ev, ea)
        widths = []
        for ln in range(nlines):
            ws = [fx.text_size(efit if (t[3] and efit) else font, _case(t[0], _tc(t)[0]), _tc(t)[1])[0] for t in cd.tokens if t[2] == ln]
            widths.append(sum(ws) + gap_em * size * (len(ws) - 1))
        if max(widths) <= maxw or size <= 18:
            break
        size = int(size * 0.94)
    fill = color(c, spec.get("fill", T["fill"]))
    emph = color(c, spec.get("emph", espec.get("fill", T["emph"])))
    sh = color(c, T["shadow"], T["shadow_alpha"]) if T.get("shadow") else None
    stroke = color(c, T["stroke"]) if T.get("stroke") else None
    sw = int(round(float(T.get("stroke_w", 0)) * size))
    lh = size * (1.0 + float(T["line_gap"])) + size * {"pill": 0.36, "box": 0.22}.get(cd.panel or T["panel"], 0)
    total_h = lh * nlines
    cy0 = cd.y * H - total_h / 2 + lh / 2
    sprites, lines = [], []
    for ln in range(nlines):
        toks = [t for t in cd.tokens if t[2] == ln]
        spr = []
        for t in toks:
            efont = font
            if t[3] and use_emph:  # emphasis font; its optional `size` is relative to type.size (script fonts run small)
                ef, ev, ea = font_path(c, home, "emph")
                efont = fx.load_font(ef, int(size * es_rel), ev, ea)
            im = fx.render_word(_case(t[0], _tc(t)[0]), efont, emph if t[3] else fill, stroke, sw, sh,
                                float(T["shadow_blur"]) * size, int(float(T["shadow_dy"]) * size), _tc(t)[1])
            spr.append(im)
        widths = [im.width for im in spr]
        gap = gap_em * size
        lw = sum(widths) + gap * (len(spr) - 1)
        x = W / 2 - lw / 2
        cy = cy0 + ln * lh
        for im, t in zip(spr, toks):
            sprites.append((im, x + im.width / 2, cy, im.width, im.height, ln, t))
            x += im.width + gap
        lines.append((W / 2 - lw / 2, cy - size * 0.62, W / 2 + lw / 2, cy + size * 0.62))
    return CardLayout(card=cd, sprites=sprites, lines=lines, font_px=size)


def card_alpha_scale(c: dict, cd: Card, t_on: float, t: float, anim: str) -> tuple[float, float, float, float]:
    """(alpha, scale, dy_frac, rot) of one word at time t."""
    if t < t_on:
        return 0, 0, 0, 0
    a_out = 1.0
    if t > cd.end - 0.14:
        a_out = fx.clamp01((cd.end - t) / 0.14)
    d = t - t_on
    if anim == "pop":
        p = fx.clamp01(d / 0.22)
        return min(1, d / 0.05) * a_out, (0.35 + 0.65 * fx.ease_out_back(p, 2.6)) * (0.85 + 0.15 * a_out), 0.0, 7 * (1 - p) * math.sin(d * 40)
    if anim == "rise":
        p = fx.ease_out_cubic(d / 0.45)
        return p * a_out, 1.0, 0.035 * (1 - p), 0.0
    if anim == "slam":
        p = fx.clamp01(d / 0.12)
        return min(1, d / 0.04) * a_out, 1.6 - 0.6 * fx.ease_out_cubic(p), 0.0, 0.0
    if anim == "drop":  # falls from above and bounces once
        p = fx.clamp01(d / 0.32)
        y = -0.05 * (1 - p) ** 2 + 0.012 * math.sin(p * math.pi) * (p > 0.6)
        return min(1, d / 0.06) * a_out, 1.0, y, -4 * (1 - p)
    if anim == "type":
        return a_out, 1.0, 0.0, 0.0
    if anim == "fade":
        return fx.clamp01(d / 0.25) * a_out, 1.0, 0.0, 0.0
    return a_out, 1.0, 0.0, 0.0


def draw_cards(c: dict, layer: Image.Image, layouts: list, t: float, W: int, H: int) -> list:
    """Draws every visible card on the RGBA layer; returns [(card_i, token, bbox)] of the visible words."""
    T = c["type"]
    boxes = []
    d = ImageDraw.Draw(layer)
    for L in layouts:
        cd = L.card
        if not (cd.start <= t < cd.end):
            continue
        anim = cd.anim or T["anim"]
        panel = cd.panel or T["panel"]
        if T.get("scrim"):
            a = min(1, (t - cd.start) / 0.25, (cd.end - t) / 0.2)
            y0 = min(l[1] for l in L.lines) - L.font_px * 0.9
            y1 = max(l[3] for l in L.lines) + L.font_px * 0.9
            sc = Image.new("L", (1, 64))
            for k in range(64):
                sc.putpixel((0, k), int(255 * float(T["scrim"]) * a * math.sin(math.pi * k / 63) ** 0.8))
            sc = sc.resize((W, max(1, int(y1 - y0))))
            blk = Image.new("RGBA", sc.size, color(c, "ink")[:3] + (0,))
            blk.putalpha(sc)
            layer.alpha_composite(blk, (0, max(0, int(y0))))
        if panel == "pill":
            cols = cd.colors or T["panel_colors"]
            for ln, (x0, y0, x1, y1) in enumerate(L.lines):
                first = min(s[6][1] for s in L.sprites if s[5] == ln)
                if t < first:
                    continue
                p = fx.ease_out_back(fx.clamp01((t - first) / 0.2), 1.6)
                a = min(1, (cd.end - t) / 0.14)
                cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
                hw = (x1 - x0) / 2 + L.font_px * 0.38
                hh = (y1 - y0) / 2 + L.font_px * 0.12
                hw *= p
                d.rounded_rectangle((cx - hw, cy - hh, cx + hw, cy + hh), radius=hh,
                                    fill=color(c, cols[(cd.i + ln) % len(cols)], float(T["panel_alpha"]) * a))
        elif panel == "box":  # square block behind each line, wiping in from the left
            cols = cd.colors or T["panel_colors"]
            for ln, (x0, y0, x1, y1) in enumerate(L.lines):
                first = min(s[6][1] for s in L.sprites if s[5] == ln)
                if t < first:
                    continue
                p = fx.ease_out_cubic((t - first) / 0.18)
                a = min(1, (cd.end - t) / 0.14)
                pad = L.font_px * 0.28
                xa, xb = x0 - pad, x1 + pad
                d.rectangle((xa, y0 - L.font_px * 0.06, xa + (xb - xa) * p, y1 + L.font_px * 0.06),
                            fill=color(c, cols[(cd.i + ln) % len(cols)], float(T["panel_alpha"]) * a))
        elif panel == "bar":
            for ln, (x0, y0, x1, y1) in enumerate(L.lines):
                first = min(s[6][1] for s in L.sprites if s[5] == ln)
                if t < first:
                    continue
                p = fx.ease_out_cubic((t - first) / 0.35)
                a = min(1, (cd.end - t) / 0.2)
                yb = y1 + L.font_px * 0.12
                w = (x1 - x0) * p
                d.rectangle(((x0 + x1) / 2 - w / 2, yb, (x0 + x1) / 2 + w / 2, yb + max(2, L.font_px * 0.035)),
                            fill=color(c, T["panel_colors"][0], 0.9 * a))
        for im, cx, cy, w, h, ln, tok in L.sprites:
            a, s, dy, rot = card_alpha_scale(c, cd, tok[1], t, anim)
            if a <= 0.01:
                continue
            if anim == "type":  # typewriter: letters appear left to right
                q = fx.clamp01((t - tok[1]) / max(0.08, 0.035 * len(tok[0])))
                ww = max(1, int(im.width * q))
                im2 = im.crop((0, 0, ww, im.height))
                bb = fx.paste(layer, im2, cx - im.width / 2 + ww / 2, cy, 1.0, a, 0)
            elif anim == "rise":  # mask reveal from below while rising
                p = fx.ease_out_cubic((t - tok[1]) / 0.45)
                hh = max(1, int(im.height * min(1, 0.15 + p)))
                im2 = im.crop((0, 0, im.width, hh))
                bb = fx.paste(layer, im2, cx, cy - im.height / 2 + hh / 2 + dy * H, s, a, rot)
            else:
                bb = fx.paste(layer, im, cx, cy + dy * H, s, a, rot)
            boxes.append((cd.i, tok[0], (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2), bb))
    return boxes


def sticker_state(st: Sticker, t: float) -> tuple[float, float, float, float]:
    """(alpha, scale, dy, rot) at t."""
    if not (st.start <= t < st.end):
        return 0, 0, 0, 0
    d = t - st.start
    out = fx.clamp01((st.end - t) / 0.12)
    if st.anim == "pop":
        p = fx.clamp01(d / 0.25)
        return out, fx.ease_out_back(p, 2.8) * (0.7 + 0.3 * out), 0.0, 10 * math.sin(d * 9) * math.exp(-d * 2)
    if st.anim == "float":
        p = fx.ease_out_cubic(d / 0.4)
        return p * out, 0.9 + 0.1 * p, -0.02 * d + 0.01 * math.sin(d * 5), 6 * math.sin(d * 4)
    if st.anim == "spin":
        p = fx.ease_out_back(fx.clamp01(d / 0.3), 2)
        return out, p, 0.0, 360 * (1 - fx.clamp01(d / 0.45))
    if st.anim == "burst":
        return out, 1.0, 0.0, 0.0
    return out, 1.0, 0.0, 0.0


def sticker_sprite(c: dict, home: Path, st: Sticker, W: int) -> Image.Image:
    px = max(8, int(st.size * W))
    if st.image is not None:  # brand art (mascot, seal) from the client's site, listed in assets-licencas.csv
        im = Image.open(st.image).convert("RGBA")
        bb = im.getbbox()
        im = im.crop(bb) if bb else im
        k = px / max(im.width, im.height)
        return im.resize((max(1, int(im.width * k)), max(1, int(im.height * k))), Image.LANCZOS)
    if st.emoji:
        ef = c["overlays"].get("emoji_font")
        if ef:
            p = Path(ef) if Path(ef).is_absolute() else home / ef
            im = fx.emoji_sprite(st.emoji, str(p), px)
            if im is not None:
                return im
        raise BrollError(f"sticker {st.i}: fonte de emoji ausente (overlays.emoji_font) para {st.emoji!r}; use icon:")
    return fx.icon_sprite(st.icon, px, color(c, st.color or "accent"), color(c, "light"))


def draw_stickers(c: dict, layer: Image.Image, stickers: list, sprites: dict, t: float, W: int, H: int) -> list:
    boxes = []
    for st in stickers:
        a, s, dy, rot = sticker_state(st, t)
        if a <= 0.01:
            continue
        spr = sprites[st.i]
        if st.anim == "burst":  # several small copies flying out from (x, y)
            d = t - st.start
            for k in range(st.count):
                ang = 2 * math.pi * k / st.count + 0.4
                r = fx.ease_out_cubic(d / 0.5) * W * 0.22
                sc = 0.5 + 0.5 * fx.ease_out_back(fx.clamp01(d / 0.25))
                bb = fx.paste(layer, spr, st.x * W + math.cos(ang) * r, st.y * H + math.sin(ang) * r, sc * 0.6, a, 15 * math.sin(d * 8 + k))
                boxes.append((st.i, bb))
        else:
            bb = fx.paste(layer, spr, st.x * W, (st.y + dy) * H, s, a, rot)
            boxes.append((st.i, bb))
    return boxes


def logo_sprite(c: dict, L: dict, W: int) -> Image.Image:
    im = Image.open(L["path"]).convert("RGBA")
    bb = im.getbbox()
    if bb:
        im = im.crop(bb)
    target = float(L.get("size", c["logo"]["size"])) * W
    k = target / im.width
    if im.height * k > target * 0.9:
        k = target * 0.9 / im.height
    im = im.resize((max(1, int(im.width * k)), max(1, int(im.height * k))), Image.LANCZOS)
    plate = L.get("plate", c["logo"]["plate"])
    if plate in (None, "none"):
        return im
    pad = int(W * 0.06)
    pw, ph = im.width + 2 * pad, im.height + 2 * pad
    base = Image.new("RGBA", (pw, ph), (0, 0, 0, 0))
    d = ImageDraw.Draw(base)
    pc = color(c, L.get("plate_color", c["logo"]["plate_color"]))
    if plate == "arch":
        r = pw // 2
        d.rounded_rectangle((0, 0, pw - 1, ph - 1), radius=int(pw * 0.08), fill=pc)
        base = Image.new("RGBA", (pw, ph + r // 2), (0, 0, 0, 0))
        d = ImageDraw.Draw(base)
        d.ellipse((0, 0, pw - 1, 2 * r), fill=pc)
        d.rectangle((0, r, pw - 1, ph + r // 2 - 1), fill=pc)
        base.alpha_composite(im, (pad, (ph + r // 2 - im.height) // 2 + r // 6))
        return base
    d.rounded_rectangle((0, 0, pw - 1, ph - 1), radius=int(min(pw, ph) * 0.22), fill=pc)
    base.alpha_composite(im, (pad, pad))
    return base


def draw_logo(c: dict, layer: Image.Image, L: dict, spr: Image.Image, t: float, W: int, H: int):
    if not (L["start"] <= t < L["end"] + 1e-6):
        return None
    d = t - L["start"]
    anim = L.get("anim", c["logo"]["anim"])
    y = float(L.get("y", 0.4)) * H
    if anim == "pop":
        s = 0.2 + 0.8 * fx.ease_out_back(fx.clamp01(d / 0.35), 2.2)
        s *= 1 + 0.025 * math.sin(d * 6.0)  # keeps breathing: never static
        return fx.paste(layer, spr, W / 2, y, s, min(1, d / 0.08), 6 * math.exp(-d * 4) * math.sin(d * 14))
    p = fx.ease_out_cubic(d / 0.7)  # "reveal": premium fade + slow scale
    return fx.paste(layer, spr, W / 2, y + (1 - p) * H * 0.02, 0.94 + 0.06 * p + 0.012 * d, p)


# ================================================================ layout guard
def _overlap(a, b, pad: float = 0.0) -> bool:
    return a[0] < b[2] - pad and b[0] < a[2] - pad and a[1] < b[3] - pad and b[1] < a[3] - pad


def layout_problems(plan: Plan, layouts: list, sticker_px: dict, logo_box, W: int, H: int) -> list[str]:
    """Static guard on the resting layout: words inside the safe area, words of one line never closer than
    MIN_GAP_EM, and no sticker/logo/other card covering a word while both are on screen (rule c)."""
    errs = []
    sx0, sy0, sx1, sy1 = SAFE[0] * W, SAFE[1] * H, SAFE[2] * W, SAFE[3] * H
    word_boxes = []
    for L in layouts:
        cd = L.card
        for im, cx, cy, w, h, ln, tok in L.sprites:
            b = (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)
            if b[0] < sx0 or b[2] > sx1 or b[1] < sy0 or b[3] > sy1:
                errs.append(f"texto {cd.i} {tok[0]!r} sai da área segura")
            word_boxes.append((cd, tok, b))
        by_line = {}
        for im, cx, cy, w, h, ln, tok in L.sprites:
            by_line.setdefault(ln, []).append((cx - w / 2, cx + w / 2, tok[0]))
        for ln, ws in by_line.items():
            ws.sort()
            for a, b in zip(ws, ws[1:]):
                gap = (b[0] - a[1]) / L.font_px
                if gap < MIN_GAP_EM:
                    errs.append(f"texto {cd.i}: palavras quase coladas ({a[2]}|{b[2]}, {gap:.3f} em)")
    for k, (cd, tok, b) in enumerate(word_boxes):
        for cd2, tok2, b2 in word_boxes[k + 1:]:
            if cd2.i != cd.i and cd.start < cd2.end and cd2.start < cd.end and _overlap(b, b2):
                errs.append(f"texto {cd.i} {tok[0]!r} sobre texto {cd2.i} {tok2[0]!r}")
        for st in plan.stickers:
            sp = sticker_px[st.i]
            if st.anim == "burst" or not (st.start < cd.end and cd.start < st.end):
                continue
            sb = (st.x * W - sp[0] / 2, st.y * H - sp[1] / 2, st.x * W + sp[0] / 2, st.y * H + sp[1] / 2)
            if _overlap(sb, b, pad=2):
                errs.append(f"sticker {st.i} ({st.emoji or st.icon}) cobre o texto {cd.i} {tok[0]!r}")
        if logo_box and plan.logo["start"] < cd.end and cd.start < plan.logo["end"] and _overlap(logo_box, b, pad=2):
            errs.append(f"logo cobre o texto {cd.i} {tok[0]!r}")
    return errs


# ================================================================ render
def transitions_for(plan: Plan, c: dict) -> list[tuple[float, str, int]]:
    """(boundary_s, kind, frames) for every cut; plan tx overrides the concept's rotation."""
    out = []
    rot = c["transitions"]["default"]
    for k, s in enumerate(plan.shots[1:], start=1):
        kind = s.tx or rot[(k - 1) % len(rot)]
        n = int(s.tx_frames or c["transitions"]["frames"])
        out.append((s.start, kind, n))
    return out


FINAL_SIZE = (1080, 1920)


def render(pdir: Path, out: Path | None = None, size: tuple[int, int] | None = None, concept_path: Path | None = None,
           plan_path: Path | None = None, log=print, post: bool = True, final: bool = False, end_card: bool = True) -> dict:
    """final=False: watermarked 540x960 preview-v2.mp4 (unchanged). final=True: the SAME spec rendered clean at 1080x1920
    (no watermark/badge/preview note, credit end card) -> <pasta>/final/final.mp4, work files in broll/out-final/."""
    t_start = time.time()
    size = size or (FINAL_SIZE if final else (540, 960))
    pdir = Path(pdir).resolve()
    home = paths.home()
    bdir = pdir / "broll"
    c = load_concept(concept_path or bdir / "concept.yaml")
    contract = _load_yaml(pdir / "contract.yaml")
    dur = float(contract["formato"]["duracao_s"])
    lang = (contract.get("voz") or {}).get("idioma") or "en-US"
    timing = Timing.load(pdir)
    plan = load_plan(pdir, timing, dur, c, plan_path)
    errs = check_plan(plan, c) + check_licenses(pdir, plan)
    if errs:
        raise BrollError("plano reprovado:\n  " + "\n  ".join(errs))
    W, H = size
    layouts = [layout_card(c, home, cd, W, H) for cd in plan.cards]
    st_sprites = {st.i: sticker_sprite(c, home, st, W) for st in plan.stickers}
    lg_sprite = logo_sprite(c, plan.logo, W) if plan.logo else None
    lg_box = None
    if lg_sprite is not None:
        y = float(plan.logo.get("y", 0.4)) * H
        lg_box = (W / 2 - lg_sprite.width / 2, y - lg_sprite.height / 2, W / 2 + lg_sprite.width / 2, y + lg_sprite.height / 2)
    lay_errs = layout_problems(plan, layouts, {k: v.size for k, v in st_sprites.items()}, lg_box, W, H)
    work = bdir / ("out-final" if final else "out")
    work.mkdir(parents=True, exist_ok=True)
    report = {"schema": "simplicio.broll-layout/v1", "size": [W, H], "cards": [
        {"i": L.card.i, "text": " / ".join(" ".join(t[0] for t in L.card.tokens if t[2] == ln) for ln in range(len(L.lines))),
         "start": L.card.start, "end": L.card.end, "font_px": L.font_px,
         "words": [{"w": tok[0], "t": tok[1]} for *_, tok in L.sprites]} for L in layouts], "problems": lay_errs}
    (work / "broll-layout.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf8")
    if lay_errs:
        raise BrollError("layout reprovado:\n  " + "\n  ".join(lay_errs))
    txs = transitions_for(plan, c)
    tx_at = {round(b, 3): (k, n) for b, k, n in txs}
    G = c["grade"]
    O = c["overlays"]
    pad = 0.25
    parts = O.get("particles") or []
    parts = [parts] if isinstance(parts, str) else list(parts)
    bad_parts = [x for x in parts if x not in PARTICLES]
    if bad_parts:
        raise BrollError(f"overlays.particles desconhecido: {bad_parts} (use {', '.join(PARTICLES)})")
    pcol = [fx.hex_rgb(c["palette"].get(k, k)) for k in (O.get("colors") or ["accent", "primary", "secondary"])]
    n_frames = int(round(dur * FPS))
    raw_v = work / "broll-video.mp4"
    enc = subprocess.Popen(["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
                            "-i", "-", "-c:v", "libx264", "-preset", "fast", "-crf", "16", "-pix_fmt", "yuv420p", str(raw_v)],
                           stdin=subprocess.PIPE)
    cache: dict[int, ShotFrames] = {}
    crops = {}
    def frames_of(k: int) -> ShotFrames:
        if k not in cache:
            cache[k] = ShotFrames(plan.shots[k], W, H, pad, log)
            crops[k] = cache[k].crop_cx
        return cache[k]
    flash = fx.hex_rgb(c["transitions"].get("flash", "#ffffff"))
    leakc = fx.hex_rgb(c["transitions"].get("leak", "#ffd2a8"))
    tint = fx.hex_rgb(G["tint"]) if G.get("tint") else None
    word_trace = []
    try:
        for fi in range(n_frames):
            t = fi / FPS
            k = max(i for i, s in enumerate(plan.shots) if s.start <= t + 1e-9)
            for old in [i for i in cache if i < k - 1]:
                del cache[old]
            base = frames_of(k).at(t)
            # transition windows: around the boundary into shot k (incoming) or into shot k+1 (outgoing)
            for b_idx in (k, k + 1):
                if b_idx <= 0 or b_idx >= len(plan.shots):
                    continue
                b = plan.shots[b_idx].start
                kind, n = tx_at[round(b, 3)]
                half = n / 2 / FPS
                if b - half <= t < b + half:
                    A = frames_of(b_idx - 1).at(t)
                    B = frames_of(b_idx).at(t)
                    base = fx.transition(kind, A, B, (t - (b - half)) / (2 * half), seed=b_idx, color=flash, leak=leakc,
                                         direction=1 if b_idx % 2 else -1)
            f = fx.grade(base, G["sat"], G["contrast"], G["warmth"], G["lift"], G["vignette"], tint, G["tint_amt"])
            if "leak" in parts:
                f = fx.screen(f, fx.leak_layer(W, H, t, seed=7, strength=float(O.get("leak_strength", 0.3))))
            if "steam" in parts:
                f = fx.screen(f, fx.steam_layer(W, H, t, seed=5, strength=float(O.get("steam_strength", 0.25))))
            if "rays" in parts:
                f = fx.screen(f, fx.rays_layer(W, H, t, seed=3, colors=(pcol[0],), strength=float(O.get("rays_strength", 0.25))))
            if O.get("grain"):
                f = fx.grain(f, float(O["grain"]), seed=fi)
            layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            if "film" in parts:
                layer.alpha_composite(fx.film_layer(W, H, t, seed=13))
            if "bubbles" in parts:
                layer.alpha_composite(fx.bubbles_layer(W, H, t, int(O.get("density", 8)), seed=11))
            if "sparkles" in parts:
                layer.alpha_composite(fx.sparkles_layer(W, H, t, int(O.get("density", 8)), seed=17, color=pcol[0]))
            if "frame" in parts:
                layer.alpha_composite(fx.frame_layer(W, H, t, color=pcol[0]))
            if "confetti" in parts:
                layer.alpha_composite(fx.confetti_layer(W, H, t, int(O.get("density", 8)) * 2, seed=19, colors=pcol))
            draw_stickers(c, layer, plan.stickers, st_sprites, t, W, H)
            if plan.logo:
                draw_logo(c, layer, plan.logo, lg_sprite, t, W, H)
            boxes = draw_cards(c, layer, layouts, t, W, H)
            if fi % 3 == 0:
                word_trace.append({"t": round(t, 3), "words": [b[1] for b in boxes]})
            im = Image.fromarray(f).convert("RGBA")
            im.alpha_composite(layer)
            enc.stdin.write(np.asarray(im.convert("RGB")).tobytes())
    finally:
        enc.stdin.close()
        enc.wait()
    if enc.returncode:
        raise BrollError("ffmpeg (vídeo) falhou")
    t_video = time.time()
    # ---------------- audio
    M = music_for(c["music"], lang, timing.voz_pt_animada)
    S = c["sfx"]
    drop = timing.resolve(M["drop_at"], dur) if M.get("drop_at") is not None else None
    bed = au.music(M["style"], float(M["bpm"]), dur, seed=int(M.get("seed", 3)), drop_at=drop, lift=float(M["lift"]))
    cues = []
    if S.get("hook"):
        cues.append((0.0, S["hook"], 4.0))
    for b, kind, n in txs:
        snd = S.get("cut")
        if isinstance(snd, dict):
            snd = snd.get(kind, snd.get("default"))
        if snd:
            cues.append((max(0, b - n / 2 / FPS), snd, 0.0))
    if S.get("sticker"):
        cues += [(st.start, S["sticker"], -2.0) for st in plan.stickers]
    if S.get("card"):
        cues += [(cd.start, S["card"], -4.0) for cd in plan.cards]
    if S.get("logo") and plan.logo:
        cues.append((plan.logo["start"], S["logo"], 2.0))
    for x in plan.sfx:
        cues.append((timing.resolve(x["at"], dur), x["kind"], float(x.get("db", 0))))
    voices = [(L["t"], L["file"]) for L in timing.lines.values()]
    mixed = au.mix(voices, dur, bed, cues, music_db=float(M["db"]), duck_db=float(M["duck_db"]), sfx_db=float(S["db"]))
    au.write_wav(work / "broll-mix.wav", mixed)
    au.loudnorm(work / "broll-mix.wav", work / "broll-master.wav", -14.0, -1.5)
    full = work / "broll-full.mp4"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(raw_v), "-i", str(work / "broll-master.wav"), "-map", "0:v", "-map", "1:a",
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", str(full)], check=True)
    dst = Path(out).resolve() if out else (pdir / "final" / "final.mp4" if final else pdir / "preview-v2.mp4")
    res = {"full": str(full)}
    if post and final:
        from . import render as rmod
        res = rmod.make_final(full, dst, home, log=log, lang=rmod.preview_lang(lang), end_card=end_card, size=size)
    elif post:
        from . import render as rmod
        res = rmod.make_preview(full, dst, home, log=log, lang=rmod.preview_lang(lang), wm=(contract.get("saida") or {}).get("marca_dagua", "padrao"))
    man = {"schema": "simplicio.broll-final/v1" if final else "simplicio.broll-preview/v1", "visual": "broll", "modo": "final" if final else "previa",
           "concept": c.get("nome"), "preview": res, "llm_calls": 0,
           "size_render": [W, H], "duracao_s": dur, "tts_calls": 0,
           "music": {k: M.get(k) for k in ("style", "bpm", "db", "duck_db", "lift", "preset") if M.get(k) is not None},
           "shots": [{"i": s.i, "src": s.src.name, "start": s.start, "end": s.end, "dur": round(s.dur, 3), "in": s.tin,
                      "crop_cx": crops.get(s.i), "zoom": list(s.zoom), "tx_in": next((k for b, k, n in txs if abs(b - s.start) < 1e-6), None),
                      "note": s.note} for s in plan.shots],
           "cards": report["cards"], "stickers": [{"i": st.i, "emoji": st.emoji, "icon": st.icon, "image": st.image.name if st.image else None, "start": st.start, "end": st.end} for st in plan.stickers],
           "transitions": [{"t": b, "kind": k, "frames": n} for b, k, n in txs], "sfx": [{"t": round(a, 3), "kind": b} for a, b, _ in cues],
           "timings_s": {"video": round(t_video - t_start, 1), "total": round(time.time() - t_start, 1)}}
    (dst.parent if final else pdir).joinpath(dst.stem + ".manifest.json").write_text(json.dumps(man, indent=2, ensure_ascii=False) + "\n", encoding="utf8")
    (work / "broll-words.json").write_text(json.dumps(word_trace, ensure_ascii=False) + "\n", encoding="utf8")
    log(f"broll: {dst} · {len(plan.shots)} cortes · {len(plan.cards)} textos · vídeo {t_video - t_start:.0f}s · total {time.time() - t_start:.0f}s")
    return man


# ================================================================ QA
def check(pdir: Path, size: tuple[int, int] = (540, 960), concept_path: Path | None = None, plan_path: Path | None = None) -> list[str]:
    """Everything render() validates before spending CPU: concept, plan rules, licences and the resting layout."""
    pdir = Path(pdir).resolve()
    home = paths.home()
    try:
        c = load_concept(concept_path or pdir / "broll" / "concept.yaml")
        dur = float(_load_yaml(pdir / "contract.yaml")["formato"]["duracao_s"])
        plan = load_plan(pdir, Timing.load(pdir), dur, c, plan_path)
    except BrollError as e:
        return [str(e)]
    errs = check_plan(plan, c) + check_licenses(pdir, plan)
    W, H = size
    layouts = [layout_card(c, home, cd, W, H) for cd in plan.cards]
    sp = {st.i: sticker_sprite(c, home, st, W).size for st in plan.stickers}
    box = None
    if plan.logo:
        lg = logo_sprite(c, plan.logo, W)
        y = float(plan.logo.get("y", 0.4)) * H
        box = (W / 2 - lg.width / 2, y - lg.height / 2, W / 2 + lg.width / 2, y + lg.height / 2)
    return errs + layout_problems(plan, layouts, sp, box, W, H)


def qa(pdir: Path, mp4: Path | None = None, concept_path: Path | None = None, final: bool = False) -> dict:
    """Automatic checks on the finished preview-v2: duration, loudness/true peak, voice sync against the timing lock
    (cross-correlation of every take in the final mix), text rules (price/SimpleTI/health), layout report, cut lengths,
    licences. Returns {ok, avisos, ...} and writes broll/out/qa-broll.json."""
    from .intl import check_text
    pdir = Path(pdir).resolve()
    mp4 = Path(mp4) if mp4 else (pdir / "final" / "final.mp4" if final else pdir / "preview-v2.mp4")
    work = pdir / "broll" / ("out-final" if final else "out")
    c = load_concept(concept_path or pdir / "broll" / "concept.yaml")
    contract = _load_yaml(pdir / "contract.yaml")
    dur = float(contract["formato"]["duracao_s"])
    timing = Timing.load(pdir)
    plan = load_plan(pdir, timing, dur, c)
    q = {"slug": pdir.name, "mp4": str(mp4), "ok": True, "avisos": []}
    def bad(m):
        q["ok"] = False
        q["avisos"].append(m)
    q["dur_s"] = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(mp4)],
                                      capture_output=True, text=True).stdout)
    if not 15 <= q["dur_s"] <= 25:
        bad(f"duração {q['dur_s']}")
    wh = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=p=0", str(mp4)],
                        capture_output=True, text=True).stdout.strip()
    q["resolucao"] = wh
    want = "%d,%d" % FINAL_SIZE if final else "540,960"
    if wh != want:
        bad(f"resolução {wh} (esperado {want.replace(',', 'x')})")
    q.update(au.measure(mp4))
    if not -15 <= q["lufs"] <= -13:
        bad(f"loudness {q['lufs']} LUFS")
    if q["tp"] > -1.5:
        bad(f"true peak {q['tp']} dBTP (> -1,5)")
    mix = au.read_wav(mp4)
    voices = [(L["t"], L["file"]) for L in timing.lines.values()]
    q["sync"] = au.sync_offsets(mix, voices)
    q["sync_max_ms"] = round(1000 * max((abs(d) for d, _ in q["sync"]), default=0.0), 1)
    if any(abs(d) > 0.04 or cr < 0.3 for d, cr in q["sync"]):
        bad(f"sincronia {q['sync']}")
    errs = check_plan(plan, c) + check_licenses(pdir, plan)
    for e in errs:
        bad(e)
    lay = json.loads((work / "broll-layout.json").read_text())
    if lay["problems"]:
        bad(f"layout: {lay['problems'][:3]}")
    q["textos"] = [cd["text"] for cd in lay["cards"]]
    # word sync of the cards: every synced word appears at its voice onset (within one frame)
    drift = []
    for cd in plan.cards:
        if not cd.sync:
            continue
        words = timing.lines[cd.sync]["words"]
        for tok in cd.tokens:
            nw = norm_word(tok[0])
            ts = [w[1] for w in words if norm_word(w[0]) == nw]
            if ts and min(abs(tok[1] - x) for x in ts) > 1 / FPS + 1e-6 and tok[1] > cd.start + 1e-6:
                drift.append((tok[0], tok[1]))
    q["texto_fora_do_tempo"] = drift
    if drift:
        bad(f"texto fora do tempo da voz: {drift[:3]}")
    q["cortes"] = len(plan.shots)
    q["corte_medio_s"] = round(dur / len(plan.shots), 2)
    q["corte_max_s"] = round(max(s.dur for s in plan.shots), 2)
    if final:
        q["modo"] = "final"
        q.update(watermark_check(mp4, work / "broll-full.mp4", dur))
        if not q["sem_marca_dagua"]:
            bad(f"marca d'água/selo detectado no final: {q['marca_dagua_diff']}")
    (work / "qa-broll.json").write_text(json.dumps(q, indent=2, ensure_ascii=False) + "\n", encoding="utf8")
    return q


def _gray_frame(mp4: Path, t: float, W: int, H: int) -> np.ndarray | None:
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", str(mp4), "-frames:v", "1", "-vf", f"scale={W}:{H}",
                          "-f", "rawvideo", "-pix_fmt", "gray", "-"], capture_output=True).stdout
    return np.frombuffer(raw[: W * H], np.uint8).reshape(H, W).astype(np.int16) if len(raw) >= W * H else None


def watermark_check(mp4: Path, clean: Path, dur: float, n: int = 12, W: int = 540, H: int = 960) -> dict:
    """No-watermark proof for a final: every sampled frame (before the end card) must match the clean pre-post render
    (broll-full.mp4) except for codec noise. The preview's tiled watermark + corner badges leave thousands of pixels off
    by > 24 levels (measured ~6-15 % of the frame); a clean final stays ~0 %. Also checks the badge corners separately."""
    worst, corner = 0.0, 0.0
    for k in range(n):
        t = 0.5 + k * (dur - 1.0) / max(1, n - 1)
        a, b = _gray_frame(mp4, t, W, H), _gray_frame(clean, t, W, H)
        if a is None or b is None:
            return {"sem_marca_dagua": False, "marca_dagua_diff": f"quadro ilegível em {t:.2f}s"}
        d = np.abs(a - b) > 24
        worst = max(worst, float(d.mean()))
        corner = max(corner, float(d[: H // 16, W // 2:].mean()), float(d[-H // 16:, : W // 2].mean()))
    ok = worst < 0.01 and corner < 0.02
    return {"sem_marca_dagua": ok, "marca_dagua_diff": {"pixels_diferentes_max": round(worst, 4), "cantos_max": round(corner, 4)}}


def qa_sheet(mp4: Path, out: Path, n: int = 20, width: int = 270, title: str = "") -> Path:
    """Dense contact sheet: n frames evenly spaced (~1 s apart on a 20 s preview), `width` px each, 5 per row."""
    from PIL import ImageFont
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(mp4)],
                               capture_output=True, text=True).stdout)
    h = int(width * 16 / 9)
    cols = 5
    rows = math.ceil(n / cols)
    top = 40
    sheet = Image.new("RGB", (cols * (width + 6) + 6, top + rows * (h + 6) + 6), (20, 20, 24))
    d = ImageDraw.Draw(sheet)
    try:
        F = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 18)
        Fs = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 15)
    except OSError:
        F = Fs = ImageFont.load_default()
    d.text((8, 10), title or mp4.name, font=F, fill=(255, 255, 255))
    for k in range(n):
        t = (k + 0.5) * dur / n
        raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", str(mp4), "-frames:v", "1", "-vf", f"scale={width}:{h}",
                              "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True).stdout
        if len(raw) < width * h * 3:
            continue
        im = Image.frombytes("RGB", (width, h), raw[: width * h * 3])
        x, y = 6 + (k % cols) * (width + 6), top + 6 + (k // cols) * (h + 6)
        sheet.paste(im, (x, y))
        d.rectangle((x, y + h - 22, x + 54, y + h), fill=(0, 0, 0))
        d.text((x + 4, y + h - 20), f"{t:.1f}s", font=Fs, fill=(255, 230, 0))
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)
    return out
