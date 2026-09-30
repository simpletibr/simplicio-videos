"""Static layout guard for the sign-off scene: kinetic words must never touch the lockup's @/city block.

Worst-case vertical extents from the block code (motion/patterns/*/block.html), no browser needed:
- brand-lockup-soft: chip at chip_y (~100 px tall), city at chip_y + 130 (40 px font) -> bottom = chip_y + 180.
- kinetic-words (bounce): each word drops in from y - 0.6*fs stretched scaleY 1.7 from its baseline
  (line box 1.12*fs), then the whole block floats up 18 px -> top can reach y - 1.42*fs - 18.
  (calm: rises from below, floats 6 px -> y - 6.) fs <= size, so checking with `size` is the worst case.
Bug this guards (All Prime v02, 30/09/2026): "Com carinho, All Prime." at y=1500/92 px reached over "Guarulhos · SP".
"""
from __future__ import annotations

MIN_GAP = 20
LOCKUP_DEFAULTS = {"chip_y": 1240, "tag_y": 900}


def _num(v, default):
    try:
        return float(v)
    except (TypeError, ValueError):
        return float(default)


def lockup_bottom(p: dict) -> float:
    return _num(p.get("chip_y"), LOCKUP_DEFAULTS["chip_y"]) + 180


def words_top(p: dict) -> float:
    y, fs = _num(p.get("y"), 300), _num(p.get("size"), 160)
    return y - 6 if p.get("mode") == "calm" else y - 1.42 * fs - 18


def words_bottom(p: dict) -> float:
    rows = max(1, len(str(p.get("lines", "")).split("|")))
    return _num(p.get("y"), 300) + rows * 1.12 * _num(p.get("size"), 160) * 1.14


def endcard_collisions(scenes: list[dict], min_gap: float = MIN_GAP) -> list[str]:
    """Problems in scenes that stack kinetic-words under a brand-lockup-soft (empty list = ok)."""
    out = []
    for sc in scenes:
        ms = sc.get("motion", [])
        locks = [m.get("params", {}) for m in ms if m.get("padrao") == "brand-lockup-soft"]
        words = [m for m in ms if m.get("padrao") == "kinetic-words"]
        for lp in locks:
            lb = lockup_bottom(lp)
            for m in words:
                wp = m.get("params", {})
                if _num(wp.get("y"), 300) < lb:   # words above the chip/city (e.g. at the top) are not stacked
                    continue
                top = words_top(wp)
                if top < lb + min_gap:
                    out.append(f"{sc.get('id')}/{m.get('bloco')}: palavras sobem até y={top:.0f}, "
                               f"@/cidade terminam em y={lb:.0f} (folga mínima {min_gap}px)")
                if words_bottom(wp) > 1800:
                    out.append(f"{sc.get('id')}/{m.get('bloco')}: palavras descem até y={words_bottom(wp):.0f} (>1800)")
    return out
