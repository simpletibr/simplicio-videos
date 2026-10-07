#!/usr/bin/env python3
"""Packs generated art into the prototype.

    python3 docs/factory/prototype/src/art/pack.py

Reads raw images from art/raw/ (not committed) and writes small WebP files to art/webp/ plus
../proto.art.data.js (data URIs the prototype loads), then rebuild with ../build.py.

Raw file names (PNG or JPG):
  char-<role>.png     brander, ideator, director, gatekeeper, poster, analyst, reflector, evolver
                      one character on a flat white background (no floor, no shadow)
  plaza.png           azulejo tile; made seamless here when its edges do not match
  hero-day.png, hero-night.png     16:9 illustrations
  poster-1.png .. poster-5.png     9:16 video backgrounds
  scene-<stage>.png   16:9 scenery behind each house (brand, ideas, make, review, publish, metrics, report)

Needs Pillow, numpy and scipy.
"""
import base64, io, json, os, sys
import numpy as np
from PIL import Image
from scipy import ndimage

HERE = os.path.dirname(os.path.abspath(__file__))
RAW, OUT = os.path.join(HERE, 'raw'), os.path.join(HERE, 'webp')
DATA = os.path.join(HERE, '..', 'proto.art.data.js')
ROLES = ['brander', 'ideator', 'director', 'gatekeeper', 'poster', 'analyst', 'reflector', 'evolver']


def find(stem):
    for ext in ('png', 'jpg', 'jpeg', 'webp'):
        p = os.path.join(RAW, f'{stem}.{ext}')
        if os.path.exists(p):
            return p
    return None


def cutout(im, tol=26):
    """Remove a flat background that touches the image border; returns an RGBA image."""
    rgb = im.convert('RGB')
    a = np.asarray(rgb).astype(np.int16)
    corners = np.concatenate([a[:8, :8].reshape(-1, 3), a[:8, -8:].reshape(-1, 3), a[-8:, :8].reshape(-1, 3), a[-8:, -8:].reshape(-1, 3)])
    bg = np.median(corners, axis=0)
    near = np.abs(a - bg).max(axis=2) <= tol
    lab, _ = ndimage.label(near)
    border = set(np.unique(np.concatenate([lab[0, :], lab[-1, :], lab[:, 0], lab[:, -1]]))) - {0}
    fg = ~np.isin(lab, list(border))
    fg = ndimage.binary_fill_holes(fg)
    # keep the main subject and any piece that is not a speck
    lab2, n = ndimage.label(fg)
    if n > 1:
        sizes = ndimage.sum(fg, lab2, range(1, n + 1))
        keep = [i + 1 for i, s in enumerate(sizes) if s >= max(60, 0.004 * fg.sum())]
        fg = np.isin(lab2, keep)
    # shave the light fringe the generator leaves at the edge, then soften
    fg = ndimage.binary_erosion(fg, iterations=2)
    alpha = ndimage.gaussian_filter(fg.astype(np.float32), 1.0)
    out = np.dstack([np.asarray(rgb), (np.clip(alpha, 0, 1) * 255).astype(np.uint8)])
    return Image.fromarray(out, 'RGBA')


def trim(im, pad=6):
    box = im.getchannel('A').point(lambda v: 255 if v > 8 else 0).getbbox()
    if not box:
        return im
    l, t, r, b = box
    return im.crop((max(0, l - pad), max(0, t - pad), min(im.width, r + pad), min(im.height, b + pad)))


def resize_alpha(im, height):
    w = max(1, round(im.width * height / im.height))
    return im.convert('RGBa').resize((w, height), Image.LANCZOS).convert('RGBA')


def seamless(im, limit=12.0):
    """Cross-fade a tile with itself shifted by half so the edges meet; skipped when they already do."""
    a = np.asarray(im.convert('RGB')).astype(np.float32)
    edge = (np.abs(a[:, 0] - a[:, -1]).mean() + np.abs(a[0] - a[-1]).mean()) / 2
    if edge <= limit:
        return im.convert('RGB'), edge
    h, w = a.shape[:2]
    m = np.outer(np.sin(np.pi * (np.arange(h) + .5) / h) ** 2, np.sin(np.pi * (np.arange(w) + .5) / w) ** 2)[..., None]
    shifted = np.roll(a, (h // 2, w // 2), axis=(0, 1))
    return Image.fromarray((a * m + shifted * (1 - m)).clip(0, 255).astype(np.uint8)), edge


def webp(im, name, q, **kw):
    buf = io.BytesIO()
    im.save(buf, 'WEBP', quality=q, method=6, **kw)
    open(os.path.join(OUT, name), 'wb').write(buf.getvalue())
    return buf.getvalue()


def uri(b):
    return 'data:image/webp;base64,' + base64.b64encode(b).decode()


def main():
    os.makedirs(OUT, exist_ok=True)
    art = {'chars': {}, 'plaza': None, 'hero': {}, 'posters': [], 'scenes': {}}
    report = []
    for role in ROLES:
        p = find(f'char-{role}')
        if not p:
            continue
        im = resize_alpha(trim(cutout(Image.open(p))), 512)
        q = 84
        b = webp(im, f'char-{role}.webp', q)
        while len(b) > 64 * 1024 and q > 50:
            q -= 6
            b = webp(im, f'char-{role}.webp', q)
        art['chars'][role] = {'src': uri(b), 'w': im.width, 'h': im.height}
        report.append(f'char-{role}: {im.width}x{im.height}, {len(b) // 1024} KB (q{q})')
    p = find('plaza')
    if p:
        im = Image.open(p).convert('RGB')
        s = min(im.size)
        im = im.crop(((im.width - s) // 2, (im.height - s) // 2, (im.width + s) // 2, (im.height + s) // 2)).resize((512, 512), Image.LANCZOS)
        im, edge = seamless(im)
        b = webp(im, 'plaza.webp', 80)
        art['plaza'] = uri(b)
        report.append(f'plaza: 512x512, {len(b) // 1024} KB (edge mismatch {edge:.1f})')
    for k in ('day', 'night'):
        p = find(f'hero-{k}')
        if p:
            im = Image.open(p).convert('RGB')
            im = im.resize((1280, round(im.height * 1280 / im.width)), Image.LANCZOS)
            b = webp(im, f'hero-{k}.webp', 76)
            art['hero'][k] = uri(b)
            report.append(f'hero-{k}: {im.width}x{im.height}, {len(b) // 1024} KB')
    for i in range(1, 6):
        p = find(f'poster-{i}')
        if p:
            im = Image.open(p).convert('RGB')
            im = im.resize((360, round(im.height * 360 / im.width)), Image.LANCZOS)
            b = webp(im, f'poster-{i}.webp', 74)
            art['posters'].append(uri(b))
            report.append(f'poster-{i}: {im.width}x{im.height}, {len(b) // 1024} KB')
    for st in ('brand', 'ideas', 'make', 'review', 'publish', 'metrics', 'report'):
        p = find(f'scene-{st}')
        if p:
            im = Image.open(p).convert('RGB')
            im = im.resize((1024, round(im.height * 1024 / im.width)), Image.LANCZOS)
            b = webp(im, f'scene-{st}.webp', 72)
            art['scenes'][st] = uri(b)
            report.append(f'scene-{st}: {im.width}x{im.height}, {len(b) // 1024} KB')
    js = '/* generated by src/art/pack.py: do not edit by hand */\nconst ART=' + json.dumps(art, separators=(',', ':')) + ';\n'
    open(DATA, 'w').write(js)
    print('\n'.join(report) or 'nothing found in art/raw/ (wrote an empty ART)')
    print(f'wrote {os.path.normpath(DATA)} ({len(js) // 1024} KB)')


if __name__ == '__main__':
    sys.exit(main())
