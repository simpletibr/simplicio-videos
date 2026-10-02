"""B-roll visual primitives (numpy + Pillow): framing, Ken Burns, grading, transitions, kinetic type, stickers,
particles and the logo CTA. Every function is pure and deterministic (seeded), so the same plan renders the same frames.

Frames are uint8 RGB arrays (H, W, 3); overlays are RGBA PIL images composited with alpha."""
from __future__ import annotations

import math
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

# ---------------------------------------------------------------- easing
def clamp01(x: float) -> float:
    return 0.0 if x < 0 else 1.0 if x > 1 else x


def ease_out_cubic(p: float) -> float:
    p = clamp01(p)
    return 1 - (1 - p) ** 3


def ease_in_out(p: float) -> float:
    p = clamp01(p)
    return 3 * p * p - 2 * p * p * p


def ease_out_back(p: float, s: float = 1.9) -> float:
    p = clamp01(p) - 1
    return 1 + (s + 1) * p ** 3 + s * p ** 2


def hex_rgb(c: str) -> tuple[int, int, int]:
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


# ---------------------------------------------------------------- framing
def crop_box(sw: int, sh: int, aspect: float, cx: float = 0.5, cy: float = 0.5) -> tuple[int, int, int, int]:
    """Largest box of the given aspect (w/h) inside sw x sh, centred on (cx, cy) in 0..1 and clamped to the source."""
    if sw / sh > aspect:
        h = sh
        w = int(round(h * aspect))
    else:
        w = sw
        h = int(round(w / aspect))
    x = int(round(cx * sw - w / 2))
    y = int(round(cy * sh - h / 2))
    x = max(0, min(sw - w, x))
    y = max(0, min(sh - h, y))
    return x, y, w, h


def saliency_center(frames: list[np.ndarray], aspect: float) -> float:
    """Horizontal centre (0..1) of the crop window with most detail + motion: column energy of the gradient magnitude
    plus inter-frame difference, smoothed, maximised over every window position. Cheap stand-in for a saliency model."""
    if not frames:
        return 0.5
    g = [f.astype(np.float32).mean(axis=2) for f in frames]
    e = np.zeros(g[0].shape[1], np.float32)
    for k, a in enumerate(g):
        gx = np.abs(np.diff(a, axis=1, prepend=a[:, :1]))
        gy = np.abs(np.diff(a, axis=0, prepend=a[:1, :]))
        e += (gx + gy).mean(axis=0)
        if k:
            e += 2.0 * np.abs(a - g[k - 1]).mean(axis=0)
    h, w = g[0].shape
    cw = min(w, int(round(h * aspect)))
    if cw >= w:
        return 0.5
    # mild centre prior: subjects are usually framed near the middle
    xs = np.linspace(-1, 1, w)
    e = e * (1.0 - 0.35 * xs ** 2)
    c = np.concatenate([[0], np.cumsum(e)])
    win = c[cw:] - c[:-cw]
    x0 = int(np.argmax(win))
    return (x0 + cw / 2) / w


def view(frame: np.ndarray, W: int, H: int, zoom: float = 1.0, px: float = 0.0, py: float = 0.0, rot: float = 0.0) -> np.ndarray:
    """Window of `frame` (already W*zmax x H*zmax, same aspect) at `zoom` >= 1 relative to the full frame, panned by
    px/py (-1..1 of the free margin), resized to W x H. Never upsamples as long as zoom <= the decode oversize."""
    fh, fw = frame.shape[:2]
    z = max(1.0, zoom)
    vw, vh = fw / z, fh / z
    mx, my = (fw - vw) / 2, (fh - vh) / 2
    x0 = mx + px * mx
    y0 = my + py * my
    im = Image.fromarray(frame)
    if rot:
        im = im.rotate(rot, resample=Image.BILINEAR, expand=False)
    im = im.resize((W, H), Image.BILINEAR, box=(x0, y0, x0 + vw, y0 + vh))
    return np.asarray(im)


# ---------------------------------------------------------------- grading
@lru_cache(maxsize=8)
def vignette_mask(W: int, H: int, strength: float) -> np.ndarray:
    y, x = np.ogrid[-1:1:complex(0, H), -1:1:complex(0, W)]
    r = np.sqrt(x * x * 0.8 + y * y)
    m = 1.0 - strength * np.clip((r - 0.45) / 0.9, 0, 1) ** 1.6
    return m.astype(np.float32)[..., None]


def grade(frame: np.ndarray, sat: float = 1.0, contrast: float = 1.0, warmth: float = 0.0, lift: float = 0.0,
          vignette: float = 0.0, tint: tuple[int, int, int] | None = None, tint_amt: float = 0.0) -> np.ndarray:
    f = frame.astype(np.float32) / 255.0
    if sat != 1.0:
        l = (f * np.array([0.299, 0.587, 0.114], np.float32)).sum(axis=2, keepdims=True)
        f = l + (f - l) * sat
    if contrast != 1.0:
        f = (f - 0.5) * contrast + 0.5
    if warmth:
        f = f + np.array([warmth, warmth * 0.3, -warmth], np.float32)
    if lift:
        f = f * (1 - lift) + lift
    if tint is not None and tint_amt:
        f = f * (1 - tint_amt) + (np.array(tint, np.float32) / 255.0) * tint_amt
    if vignette:
        f = f * vignette_mask(frame.shape[1], frame.shape[0], float(vignette))
    return (np.clip(f, 0, 1) * 255).astype(np.uint8)


# ---------------------------------------------------------------- transitions
def _blend(a: np.ndarray, b: np.ndarray, k: float) -> np.ndarray:
    return (a.astype(np.float32) * (1 - k) + b.astype(np.float32) * k).astype(np.uint8)


def _zoomed(f: np.ndarray, z: float) -> np.ndarray:
    if abs(z - 1) < 1e-3:
        return f
    H, W = f.shape[:2]
    if z > 1:
        return view(f, W, H, z)
    im = Image.fromarray(f).resize((max(1, int(W * z)), max(1, int(H * z))), Image.BILINEAR)
    out = np.zeros_like(f)
    y, x = (H - im.height) // 2, (W - im.width) // 2
    out[y:y + im.height, x:x + im.width] = np.asarray(im)
    return out


def _hblur(f: np.ndarray, px: int) -> np.ndarray:
    if px < 2:
        return f
    acc = np.zeros(f.shape, np.float32)
    n = 7
    for k in range(n):
        s = int(round((k - n // 2) * px / n))
        acc += np.roll(f, s, axis=1)
    return (acc / n).astype(np.uint8)


def _shift(f: np.ndarray, dx: int, dy: int = 0) -> np.ndarray:
    out = np.zeros_like(f)
    H, W = f.shape[:2]
    xs, xd = (0, dx) if dx >= 0 else (-dx, 0)
    ys, yd = (0, dy) if dy >= 0 else (-dy, 0)
    w, h = W - abs(dx), H - abs(dy)
    if w > 0 and h > 0:
        out[yd:yd + h, xd:xd + w] = f[ys:ys + h, xs:xs + w]
    return out


def _radial(W: int, H: int, cx: float, cy: float) -> np.ndarray:
    y, x = np.ogrid[0:H, 0:W]
    return np.sqrt(((x - cx * W) / W) ** 2 * (W / H) ** 2 + ((y - cy * H) / H) ** 2).astype(np.float32)


TRANSITIONS = ("cut", "flash", "zoom", "whip", "glitch", "pop", "leak", "blur", "mask", "slide", "dip",
               "iris", "stripes", "push", "spin", "split")


def transition(kind: str, a: np.ndarray, b: np.ndarray, p: float, seed: int = 0, color=(255, 255, 255),
               leak=(255, 196, 140), direction: int = 1) -> np.ndarray:
    """Frame of transition `kind` from shot a to shot b at progress p in [0, 1] (0 = all a, 1 = all b)."""
    H, W = a.shape[:2]
    p = clamp01(p)
    if kind == "cut":
        return a if p < 0.5 else b
    if kind == "flash":  # hard cut under a white (or brand) flash peaking at the cut
        base = a if p < 0.5 else b
        k = 1 - abs(p - 0.5) * 2
        return _blend(base, np.full_like(base, color), 0.85 * k ** 1.5)
    if kind == "dip":
        base = a if p < 0.5 else b
        k = 1 - abs(p - 0.5) * 2
        return _blend(base, np.zeros_like(base), k)
    if kind == "zoom":  # zoom punch: a pushes in fast, b lands from a bigger scale, short flash at the seam
        if p < 0.5:
            q = p / 0.5
            f = _zoomed(a, 1 + 0.35 * q ** 2)
        else:
            q = (p - 0.5) / 0.5
            f = _zoomed(b, 1 + 0.25 * (1 - ease_out_cubic(q)))
        k = 1 - abs(p - 0.5) * 2
        return _blend(f, np.full_like(f, color), 0.45 * k ** 2)
    if kind == "whip":  # whip pan with horizontal motion blur
        e = ease_in_out(p)
        off = int(round(e * W))
        f = np.empty_like(a)
        if direction >= 0:  # content moves left: a exits left, b enters from the right
            f[:, :W - off] = a[:, off:]
            f[:, W - off:] = b[:, :off]
        else:
            f[:, off:] = a[:, :W - off]
            f[:, :off] = b[:, W - off:]
        sp = math.sin(p * math.pi)
        return _hblur(f, int(sp * W * 0.22))
    if kind == "glitch":
        base = a if p < 0.5 else b
        k = math.sin(p * math.pi)
        rng = np.random.default_rng(seed + int(p * 97))
        out = base.copy()
        s = int(k * W * 0.035)
        if s:
            out[..., 0] = np.roll(base[..., 0], s, axis=1)
            out[..., 2] = np.roll(base[..., 2], -s, axis=1)
        for _ in range(int(6 * k)):
            y0 = int(rng.integers(0, H - 8))
            h = int(rng.integers(6, max(8, H // 14)))
            out[y0:y0 + h] = np.roll(out[y0:y0 + h], int(rng.integers(-W // 8, W // 8)), axis=1)
        return out
    if kind == "pop":  # b bounces in from small over a (cartoon pop)
        if p < 0.08:
            return a
        q = (p - 0.08) / 0.92
        z = 0.55 + 0.45 * ease_out_back(q, 2.4)
        im = Image.fromarray(b).resize((max(2, int(W * z)), max(2, int(H * z))), Image.BILINEAR)
        out = (a.astype(np.float32) * (1 - 0.35 * min(1, q * 3))).astype(np.uint8)
        if z >= 1:
            return _zoomed(b, z)
        bw, bh = im.size
        x, y = (W - bw) // 2, (H - bh) // 2
        mask = Image.new("L", (bw, bh), 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, bw - 1, bh - 1), radius=int(min(bw, bh) * 0.08 * (1 - q)), fill=255)
        o = Image.fromarray(out)
        o.paste(im, (x, y), mask)
        return np.asarray(o)
    if kind == "leak":  # light-leak crossfade: warm additive glow sweeps across the seam
        k = math.sin(p * math.pi)
        base = _blend(a, b, ease_in_out(p))
        r = _radial(W, H, 0.15 + 0.7 * p * (1 if direction > 0 else -1) % 1.0, 0.35)
        g = np.clip(1.15 - r * 1.6, 0, 1)[..., None] * k
        f = base.astype(np.float32) / 255.0
        lc = np.array(leak, np.float32) / 255.0
        f = 1 - (1 - f) * (1 - g * lc * 0.95)  # screen
        return (np.clip(f, 0, 1) * 255).astype(np.uint8)
    if kind == "blur":
        k = math.sin(p * math.pi)
        base = _blend(a, b, ease_in_out(p))
        if k > 0.05:
            im = Image.fromarray(base).resize((W // 4, H // 4), Image.BILINEAR).filter(ImageFilter.GaussianBlur(6 * k))
            base = _blend(base, np.asarray(im.resize((W, H), Image.BILINEAR)), min(1, k * 1.4))
        return base
    if kind == "mask":  # soft circular reveal of b from the centre
        e = ease_in_out(p)
        r = _radial(W, H, 0.5, 0.5)
        edge = 0.06
        m = np.clip((e * 1.25 - r) / edge, 0, 1)[..., None]
        return (a.astype(np.float32) * (1 - m) + b.astype(np.float32) * m).astype(np.uint8)
    if kind == "slide":  # b slides up softly over a, with a subtle zoom punch
        e = ease_out_cubic(p)
        dy = int((1 - e) * H * 0.9)
        fb = _zoomed(b, 1 + 0.06 * (1 - e))
        out = a.copy()
        if dy < H:
            out[dy:] = fb[:H - dy]
        return out
    if kind == "iris":  # hard-edged circle opening from a point, with a brand-colour ring at the edge
        e = ease_in_out(p)
        r = _radial(W, H, 0.5 + 0.25 * direction * 0.0, 0.42)
        R = e * 1.3
        m = (r < R).astype(np.float32)[..., None]
        ring = ((r >= R) & (r < R + 0.035) & (0.02 < e < 0.98)).astype(np.float32)[..., None]
        out = a.astype(np.float32) * (1 - m) + b.astype(np.float32) * m
        out = out * (1 - ring) + np.array(color, np.float32) * ring
        return out.astype(np.uint8)
    if kind == "stripes":  # venetian blinds: vertical bars of b grow one after another
        n = 6
        out = a.copy()
        bw = W / n
        for k in range(n):
            q = clamp01((p - k * 0.06) / (1 - (n - 1) * 0.06))
            w = int(round(ease_in_out(q) * bw))
            x0 = int(round(k * bw)) if direction >= 0 else int(round((n - 1 - k) * bw))
            if w > 0:
                out[:, x0:x0 + w] = b[:, x0:x0 + w]
        return out
    if kind == "push":  # vertical push: a leaves upwards while b pushes in from below (story-style)
        e = ease_in_out(p)
        off = int(round(e * H))
        f = np.empty_like(a)
        f[:H - off] = a[off:]
        f[H - off:] = b[:off]
        sp = math.sin(p * math.pi)
        if sp > 0.1:
            im = Image.fromarray(f).filter(ImageFilter.BoxBlur(int(sp * 3)))
            f = np.asarray(im)
        return f
    if kind == "spin":  # a spins out with a zoom, b spins in (energetic)
        base, q = (a, p / 0.5) if p < 0.5 else (b, (1 - p) / 0.5)
        ang = (1 if p < 0.5 else -1) * direction * 25 * q ** 2
        z = 1 + 0.5 * q ** 2
        im = Image.fromarray(_zoomed(base, z)).rotate(ang, resample=Image.BILINEAR)
        return np.asarray(im)
    if kind == "split":  # b closes in as two halves from top and bottom
        e = ease_out_cubic(p)
        out = a.copy()
        h = int(round(e * H / 2))
        if h > 0:
            out[:h] = b[H // 2 - h:H // 2]
            out[H - h:] = b[H // 2:H // 2 + h]
        return out
    raise ValueError(f"transição desconhecida: {kind}")


# ---------------------------------------------------------------- type
@lru_cache(maxsize=64)
def load_font(path: str, size: int, variation: str | None = None, axes: tuple | None = None) -> ImageFont.FreeTypeFont:
    f = ImageFont.truetype(path, size)
    try:
        if axes:
            f.set_variation_by_axes(list(axes))
        elif variation:
            f.set_variation_by_name(variation)
    except (OSError, ValueError):
        pass
    return f


def text_size(font: ImageFont.FreeTypeFont, text: str, tracking: float = 0.0) -> tuple[int, int, int]:
    """(width, ascent+descent box height, top offset) of text with extra letter spacing (em)."""
    if not tracking:
        l, t, r, b = font.getbbox(text)
        return r - l, b - t, t
    w = 0.0
    for ch in text:
        w += font.getlength(ch) + tracking * font.size
    w -= tracking * font.size
    l, t, r, b = font.getbbox(text)
    return int(round(w)), b - t, t


def render_word(text: str, font: ImageFont.FreeTypeFont, fill, stroke=None, stroke_w: int = 0, shadow=None,
                shadow_blur: float = 0, shadow_dy: int = 0, tracking: float = 0.0, pad: int = 0) -> Image.Image:
    """RGBA sprite of one word (fill + optional stroke + soft drop shadow), trimmed with `pad` margin."""
    w, h, top = text_size(font, text, tracking)
    m = pad + stroke_w + int(shadow_blur * 2) + abs(shadow_dy)
    W, H = w + 2 * m, int(font.size * 1.3) + 2 * m
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    def draw(dst, color, sw=0, scol=None, dx=0, dy=0):
        d = ImageDraw.Draw(dst)
        if not tracking:
            d.text((m + dx, m + dy - top + int(font.size * 0.05)), text, font=font, fill=color, stroke_width=sw, stroke_fill=scol)
            return
        x = m + dx
        for ch in text:
            d.text((x, m + dy - top + int(font.size * 0.05)), ch, font=font, fill=color, stroke_width=sw, stroke_fill=scol)
            x += font.getlength(ch) + tracking * font.size
    if shadow is not None:
        sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        draw(sh, shadow, stroke_w, shadow, 0, shadow_dy)
        if shadow_blur:
            sh = sh.filter(ImageFilter.GaussianBlur(shadow_blur))
        im = Image.alpha_composite(im, sh)
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw(lay, fill, stroke_w, stroke if stroke_w else None)
    im = Image.alpha_composite(im, lay)
    bb = im.getbbox() or (0, 0, 1, 1)
    return im.crop((max(0, bb[0] - pad), max(0, bb[1] - pad), min(W, bb[2] + pad), min(H, bb[3] + pad)))


def emoji_sprite(ch: str, font_path: str, size: int) -> Image.Image | None:
    try:
        f = ImageFont.truetype(font_path, 109)
    except OSError:
        return None
    im = Image.new("RGBA", (160, 160), (0, 0, 0, 0))
    ImageDraw.Draw(im).text((10, 10), ch, font=f, embedded_color=True)
    bb = im.getbbox()
    if not bb:
        return None
    im = im.crop(bb)
    k = size / max(im.size)
    return im.resize((max(1, int(im.width * k)), max(1, int(im.height * k))), Image.LANCZOS)


# ---------------------------------------------------------------- vector icons (license-free, drawn here)
def icon_sprite(name: str, size: int, color, accent=(255, 255, 255, 255)) -> Image.Image:
    S = size * 4
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    c = color
    if name == "paw":
        d.ellipse((S * .22, S * .45, S * .78, S * .92), fill=c)
        for (x, y, r) in ((.18, .36, .11), (.38, .2, .12), (.62, .2, .12), (.82, .36, .11)):
            d.ellipse(((x - r) * S, (y - r * 1.2) * S, (x + r) * S, (y + r * 1.2) * S), fill=c)
    elif name == "heart":
        d.ellipse((S * .1, S * .15, S * .52, S * .57), fill=c)
        d.ellipse((S * .48, S * .15, S * .9, S * .57), fill=c)
        d.polygon([(S * .13, S * .45), (S * .87, S * .45), (S * .5, S * .9)], fill=c)
    elif name == "sparkle":
        pts = []
        for k in range(8):
            a = k * math.pi / 4 - math.pi / 2
            r = 0.48 if k % 2 == 0 else 0.13
            pts.append((S / 2 + math.cos(a) * r * S, S / 2 + math.sin(a) * r * S))
        d.polygon(pts, fill=c)
    elif name == "bubble":
        w = max(2, S // 22)
        d.ellipse((w, w, S - w, S - w), outline=c, width=w)
        d.ellipse((S * .22, S * .2, S * .42, S * .36), fill=accent)
    elif name == "phone":
        d.rounded_rectangle((S * .28, S * .08, S * .72, S * .92), radius=S * .08, fill=c)
        d.rounded_rectangle((S * .32, S * .16, S * .68, S * .78), radius=S * .03, fill=accent)
        d.ellipse((S * .46, S * .82, S * .54, S * .88), fill=accent)
    elif name == "chat":
        d.rounded_rectangle((S * .08, S * .14, S * .92, S * .7), radius=S * .16, fill=c)
        d.polygon([(S * .25, S * .66), (S * .45, S * .66), (S * .2, S * .88)], fill=c)
        for k in range(3):
            x = S * (.3 + k * .2)
            d.ellipse((x - S * .05, S * .37, x + S * .05, S * .47), fill=accent)
    elif name == "check":
        d.ellipse((0, 0, S - 1, S - 1), fill=c)
        d.line([(S * .27, S * .52), (S * .44, S * .69), (S * .74, S * .34)], fill=accent, width=max(3, S // 10), joint="curve")
    elif name == "drop":
        d.ellipse((S * .2, S * .38, S * .8, S * .95), fill=c)
        d.polygon([(S * .5, S * .02), (S * .23, S * .55), (S * .77, S * .55)], fill=c)
    elif name == "leaf":
        d.ellipse((S * .25, S * .05, S * .75, S * .95), fill=c)
        d.line([(S * .5, S * .1), (S * .5, S * .98)], fill=accent, width=max(2, S // 40))
    else:
        raise ValueError(f"ícone desconhecido: {name}")
    return im.resize((size, size), Image.LANCZOS)


# ---------------------------------------------------------------- particles
def bubbles_layer(W: int, H: int, t: float, n: int, seed: int, color=(255, 255, 255)) -> Image.Image:
    """Soap bubbles drifting up with a wobble; each bubble has a rim and a specular highlight."""
    rng = np.random.default_rng(seed)
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    for k in range(n):
        x0, sp, r, ph, y0 = rng.random(), 0.08 + rng.random() * 0.16, 0.02 + rng.random() * 0.05, rng.random() * 6.28, rng.random()
        y = (y0 - t * sp) % 1.2 - 0.1
        x = x0 + 0.03 * math.sin(t * 2.2 + ph)
        R = r * W
        cx, cy = x * W, y * H
        a = int(150 + 80 * math.sin(t * 3 + ph))
        d.ellipse((cx - R, cy - R, cx + R, cy + R), outline=color + (a,), width=max(2, int(R * 0.09)))
        d.ellipse((cx - R * .55, cy - R * .6, cx - R * .15, cy - R * .25), fill=(255, 255, 255, min(255, a + 40)))
    return im


def sparkles_layer(W: int, H: int, t: float, n: int, seed: int, color=(255, 255, 255)) -> Image.Image:
    """Twinkling 4-point glints (glitter / nail shine): each one flashes on and off at its own rhythm."""
    rng = np.random.default_rng(seed)
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    for k in range(n):
        x, y, ph, sp, r = rng.random(), rng.random(), rng.random() * 6.28, 2 + rng.random() * 3, 0.012 + rng.random() * 0.022
        y = (y - t * 0.02) % 1.0
        a = max(0.0, math.sin(t * sp + ph)) ** 3
        if a < 0.05:
            continue
        cx, cy, R = x * W, y * H, r * W * (0.6 + 0.4 * a)
        c = color + (int(235 * a),)
        d.polygon([(cx, cy - R), (cx + R * 0.18, cy - R * 0.18), (cx + R, cy), (cx + R * 0.18, cy + R * 0.18),
                   (cx, cy + R), (cx - R * 0.18, cy + R * 0.18), (cx - R, cy), (cx - R * 0.18, cy - R * 0.18)], fill=c)
        d.ellipse((cx - R * 0.2, cy - R * 0.2, cx + R * 0.2, cy + R * 0.2), fill=(255, 255, 255, int(255 * a)))
    return im


def confetti_layer(W: int, H: int, t: float, n: int, seed: int, colors=((255, 80, 120), (255, 210, 60), (60, 180, 255))) -> Image.Image:
    """Falling, tumbling confetti strips in the brand colours."""
    rng = np.random.default_rng(seed)
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    for k in range(n):
        x0, sp, ph, w, c = rng.random(), 0.12 + rng.random() * 0.18, rng.random() * 6.28, 0.012 + rng.random() * 0.012, colors[k % len(colors)]
        y = (rng.random() + t * sp) % 1.15 - 0.08
        x = x0 + 0.04 * math.sin(t * 1.7 + ph)
        sw, sh = max(2, int(w * W)), max(2, int(w * W * (0.3 + 0.7 * abs(math.sin(t * 5 + ph)))))
        piece = Image.new("RGBA", (sw, sh), tuple(c) + (230,))
        piece = piece.rotate((t * 220 + ph * 57) % 360, expand=True)
        im.alpha_composite(piece, (int(x * W) % W, max(0, int(y * H))))
    return im


def steam_layer(W: int, H: int, t: float, seed: int, strength: float = 0.25) -> np.ndarray:
    """Float32 (H, W, 3) soft rising wisps (coffee steam / fresh-baked warmth), screen-blended by the caller."""
    rng = np.random.default_rng(seed)
    h, w = H // 6, W // 6
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    acc = np.zeros((h, w), np.float32)
    for k in range(5):
        x0, ph, sp = rng.random(), rng.random() * 6.28, 0.05 + rng.random() * 0.05
        cx = (x0 + 0.08 * np.sin(yy / h * 6 + t * 1.3 + ph)) * w
        band = np.exp(-((xx - cx) / (w * 0.06)) ** 2)
        fade = np.clip(1 - ((yy / h + t * sp + ph) % 1.0), 0, 1) ** 1.5
        acc += band * fade * (0.5 + 0.5 * np.sin(yy / h * 9 - t * 2 + ph))
    acc = np.clip(acc * strength, 0, 1)
    im = Image.fromarray((acc * 255).astype(np.uint8)).resize((W, H), Image.BILINEAR).filter(ImageFilter.GaussianBlur(6))
    a = np.asarray(im).astype(np.float32) / 255.0
    return np.repeat(a[..., None], 3, axis=2)


def film_layer(W: int, H: int, t: float, seed: int, color=(255, 250, 235)) -> Image.Image:
    """Vintage film: dust specks, a vertical scratch or two, frame-to-frame flicker (RGBA over the frame)."""
    fi = int(t * 24)
    rng = np.random.default_rng(seed * 1000 + fi)
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    for _ in range(int(rng.integers(6, 16))):
        x, y, r = rng.random() * W, rng.random() * H, 0.6 + rng.random() * 2.2
        d.ellipse((x - r, y - r, x + r, y + r), fill=(30, 25, 20, int(rng.integers(60, 160))))
    for _ in range(int(rng.integers(0, 3))):
        x = rng.random() * W
        d.line((x, 0, x + rng.normal(0, 4), H), fill=color + (int(rng.integers(40, 110)),), width=1)
    fl = int(abs(rng.normal(0, 10)))
    d.rectangle((0, 0, W, H), fill=(255, 245, 225, min(28, fl)))
    return im


def rays_layer(W: int, H: int, t: float, seed: int, colors=((255, 236, 190),), strength: float = 0.25) -> np.ndarray:
    """Float32 sun rays fanning from the top corner, slowly rotating (beach / bright mornings)."""
    h, w = H // 4, W // 4
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    ang = np.arctan2(yy + h * 0.1, xx - w * 1.05)
    rays = (0.5 + 0.5 * np.sin(ang * 18 + t * 0.6)) ** 6
    fall = np.clip(1 - np.hypot(xx - w * 1.05, yy + h * 0.1) / (h * 1.1), 0, 1)
    g = (rays * fall * strength)[..., None] * (np.array(colors[0], np.float32) / 255.0)
    im = Image.fromarray((np.clip(g, 0, 1) * 255).astype(np.uint8)).resize((W, H), Image.BILINEAR).filter(ImageFilter.GaussianBlur(3))
    return np.asarray(im).astype(np.float32) / 255.0


def frame_layer(W: int, H: int, t: float, color=(201, 166, 70), inset: float = 0.035) -> Image.Image:
    """Editorial double frame in the brand colour that draws itself on in 0.8 s, with a glint running round it."""
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    p = ease_out_cubic(t / 0.8)
    for k, (ins, wd, al) in enumerate(((inset, 2, 230), (inset + 0.012, 1, 150))):
        x0, y0, x1, y1 = W * ins, H * ins * W / H, W * (1 - ins), H - H * ins * W / H
        per = 2 * ((x1 - x0) + (y1 - y0))
        segs = [((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)), ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))]
        left = per * p
        for (a, b) in segs:
            L = math.hypot(b[0] - a[0], b[1] - a[1])
            if left <= 0:
                break
            q = min(1, left / L)
            d.line((a[0], a[1], a[0] + (b[0] - a[0]) * q, a[1] + (b[1] - a[1]) * q), fill=color + (al,), width=wd)
            left -= L
    # glint
    g = (t * 0.35) % 1.0
    x0, y0, x1, y1 = W * inset, H * inset * W / H, W * (1 - inset), H - H * inset * W / H
    per = 2 * ((x1 - x0) + (y1 - y0)); pos = g * per
    for (a, b) in [((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)), ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))]:
        L = math.hypot(b[0] - a[0], b[1] - a[1])
        if pos <= L:
            cx, cy = a[0] + (b[0] - a[0]) * pos / L, a[1] + (b[1] - a[1]) * pos / L
            for r, al in ((10, 60), (5, 140), (2, 255)):
                d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(255, 250, 230, al))
            break
        pos -= L
    return im


def leak_layer(W: int, H: int, t: float, seed: int, colors=((255, 214, 170), (255, 236, 214)), strength: float = 0.35) -> np.ndarray:
    """Float32 (H, W, 3) additive light-leak field: two soft warm blobs drifting slowly (screen-blended by the caller)."""
    rng = np.random.default_rng(seed)
    acc = np.zeros((H // 4, W // 4, 3), np.float32)
    for k, c in enumerate(colors):
        ph = rng.random() * 6.28
        cx = 0.5 + 0.55 * math.sin(t * 0.35 + ph)
        cy = 0.3 + 0.4 * math.cos(t * 0.27 + ph * 1.3)
        r = _radial(W // 4, H // 4, cx, cy)
        g = np.clip(1 - r / (0.55 + 0.1 * k), 0, 1) ** 2
        acc += g[..., None] * (np.array(c, np.float32) / 255.0)
    im = Image.fromarray((np.clip(acc * strength, 0, 1) * 255).astype(np.uint8)).resize((W, H), Image.BILINEAR)
    return np.asarray(im).astype(np.float32) / 255.0


def screen(frame: np.ndarray, layer: np.ndarray) -> np.ndarray:
    f = frame.astype(np.float32) / 255.0
    return ((1 - (1 - f) * (1 - layer)) * 255).astype(np.uint8)


def grain(frame: np.ndarray, amt: float, seed: int) -> np.ndarray:
    if amt <= 0:
        return frame
    rng = np.random.default_rng(seed)
    n = rng.normal(0, amt * 255, frame.shape[:2]).astype(np.float32)[..., None]
    return np.clip(frame.astype(np.float32) + n, 0, 255).astype(np.uint8)


def paste(dst: Image.Image, spr: Image.Image, cx: float, cy: float, scale: float = 1.0, alpha: float = 1.0,
          rot: float = 0.0) -> tuple[int, int, int, int]:
    """Composite sprite centred at (cx, cy) px with scale/alpha/rotation; returns the bbox actually covered."""
    if alpha <= 0.01 or scale <= 0.01:
        return (0, 0, 0, 0)
    s = spr
    if abs(scale - 1) > 1e-3:
        s = s.resize((max(1, int(s.width * scale)), max(1, int(s.height * scale))), Image.BILINEAR)
    if rot:
        s = s.rotate(rot, resample=Image.BILINEAR, expand=True)
    if alpha < 0.999:
        a = s.getchannel("A").point(lambda v: int(v * alpha))
        s = s.copy()
        s.putalpha(a)
    x, y = int(round(cx - s.width / 2)), int(round(cy - s.height / 2))
    dst.alpha_composite(s, (max(0, x), max(0, y)), (max(0, -x), max(0, -y)))
    return (x, y, x + s.width, y + s.height)
