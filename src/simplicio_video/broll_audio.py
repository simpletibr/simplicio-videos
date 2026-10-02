"""B-roll audio: procedural music bed per concept (license-free, synthesised here), light SFX on every cut and sticker,
voice takes placed at the timing.lock times, music ducked under the voice, then a 2-pass loudness master
(-14 LUFS, true peak <= -1.5 dBTP). Never calls TTS: the voice comes from the approved takes only."""
from __future__ import annotations

import json
import math
import re
import subprocess
import wave
from pathlib import Path

import numpy as np

SR = 48000


def write_wav(path: Path, x: np.ndarray, sr: int = SR) -> Path:
    x = np.asarray(x, np.float32)
    if x.ndim == 1:
        x = np.stack([x, x], axis=1)
    pcm = (np.clip(x, -1, 1) * 32767).astype("<i2")
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())
    return path


def read_wav(path: Path) -> np.ndarray:
    """Any WAV/audio -> float32 mono at SR (via ffmpeg, so sample rate/format never matter)."""
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32).copy()


# ---------------------------------------------------------------- synth voices
def _env(n: int, a: float, d: float) -> np.ndarray:
    t = np.arange(n) / SR
    return np.minimum(1, t / max(a, 1e-4)) * np.exp(-t / max(d, 1e-4))


def _noise(n: int, rng) -> np.ndarray:
    return rng.uniform(-1, 1, n).astype(np.float32)


def _lp(x: np.ndarray, k: float) -> np.ndarray:
    """One-pole low-pass, k in (0, 1] (smaller = darker)."""
    y = np.empty_like(x)
    acc = 0.0
    for i in range(len(x)):
        acc += k * (x[i] - acc)
        y[i] = acc
    return y


def _lp_fast(x: np.ndarray, width: int) -> np.ndarray:
    if width <= 1:
        return x
    c = np.cumsum(np.concatenate([[0], x]))
    y = (c[width:] - c[:-width]) / width
    return np.concatenate([y, np.full(width - 1, y[-1] if len(y) else 0)]).astype(np.float32)


def kick(rng, punch: float = 1.0) -> np.ndarray:
    n = int(0.42 * SR)
    t = np.arange(n) / SR
    f = 46 + 130 * np.exp(-t * 30) * punch
    ph = np.cumsum(2 * np.pi * f / SR)
    return (np.sin(ph) * np.exp(-t * 7.5) + (t < 0.004) * _noise(n, rng) * 0.4).astype(np.float32)


def clap(rng) -> np.ndarray:
    n = int(0.28 * SR)
    t = np.arange(n) / SR
    e = np.exp(-t * 20)
    for dly in (0, 0.011, 0.022):
        e = np.maximum(e, ((t >= dly) & (t < dly + 0.008)).astype(np.float32))
    x = _noise(n, rng)
    x = x - _lp_fast(x, 18)  # crude band-pass: remove lows
    x = _lp_fast(x, 3)
    return (x * e * 1.4).astype(np.float32)


def hat(rng, open_: bool = False) -> np.ndarray:
    n = int((0.25 if open_ else 0.06) * SR)
    t = np.arange(n) / SR
    x = _noise(n, rng)
    x = x - _lp_fast(x, 4)
    return (x * np.exp(-t * (9 if open_ else 55)) * 0.5).astype(np.float32)


def tone(freq: float, dur: float, kind: str = "pluck", rng=None) -> np.ndarray:
    n = int(dur * SR)
    t = np.arange(n) / SR
    if kind == "pluck":  # marimba-ish
        x = np.sin(2 * np.pi * freq * t) + 0.35 * np.sin(2 * np.pi * freq * 4 * t) * np.exp(-t * 30)
        return (x * _env(n, 0.002, 0.22)).astype(np.float32)
    if kind == "bass":
        x = np.sin(2 * np.pi * freq * t) + 0.3 * np.sin(2 * np.pi * freq * 2 * t)
        return (np.tanh(1.6 * x) * _env(n, 0.004, 0.28)).astype(np.float32)
    if kind == "pad":
        x = sum(np.sin(2 * np.pi * freq * d * t + k) for k, d in enumerate((1, 1.003, 0.997, 2.001)))
        a = np.minimum(1, t / 0.35) * np.minimum(1, (dur - t) / 0.35)
        return (x / 4 * a).astype(np.float32)
    if kind == "keys":  # soft electric piano
        x = np.sin(2 * np.pi * freq * t + 0.8 * np.sin(2 * np.pi * freq * t) * np.exp(-t * 6))
        return (x * _env(n, 0.003, 0.7)).astype(np.float32)
    if kind == "bell":
        x = np.sin(2 * np.pi * freq * t) + 0.4 * np.sin(2 * np.pi * freq * 2.76 * t)
        return (x * _env(n, 0.001, 0.5)).astype(np.float32)
    raise ValueError(kind)


def midi(n: float) -> float:
    return 440.0 * 2 ** ((n - 69) / 12)


def _add(buf: np.ndarray, t: float, x: np.ndarray, g: float, pan: float = 0.0):
    i = int(t * SR)
    if i >= len(buf):
        return
    x = x[: len(buf) - i]
    l, r = math.cos((pan + 1) * math.pi / 4), math.sin((pan + 1) * math.pi / 4)
    buf[i:i + len(x), 0] += x * g * l * 1.414
    buf[i:i + len(x), 1] += x * g * r * 1.414


PROGRESSIONS = {
    "bouncy": [(48, [60, 64, 67]), (45, [57, 60, 64]), (41, [57, 60, 65]), (43, [59, 62, 67])],   # C Am F G
    "elegant": [(45, [57, 60, 64, 67]), (41, [57, 60, 64, 65]), (48, [55, 60, 64, 67]), (43, [55, 59, 62, 67])],  # Am7 Fmaj7 C G
}


def music(style: str, bpm: float, dur: float, seed: int = 1, drop_at: float | None = None) -> np.ndarray:
    """Stereo float32 bed. bouncy: kick 4/4, claps 2/4, 16th shaker, staccato bass, marimba arpeggio (playful pop);
    elegant: soft kick, rim, warm pad, keys, sparse bells (premium chill). `drop_at`: brief half-bar break (build -> drop)."""
    rng = np.random.default_rng(seed)
    n = int(dur * SR) + SR
    L = np.zeros((n, 2), np.float32)
    beat = 60.0 / bpm
    prog = PROGRESSIONS["elegant" if style == "elegant" else "bouncy"]
    K, C, Hh, Ho = kick(rng, 1.0 if style != "elegant" else 0.6), clap(rng), hat(rng), hat(rng, True)
    nb = int(dur / beat) + 2
    for b in range(nb):
        t = b * beat
        bar = b // 4
        root, chord = prog[bar % len(prog)]
        brk = drop_at is not None and drop_at - 2 * beat <= t < drop_at
        if style == "elegant":
            if not brk:
                _add(L, t, K, 0.55)
                if b % 2 == 1:
                    _add(L, t, hat(rng) * 1.6, 0.25, 0.2)
            _add(L, t + beat / 2, Hh, 0.22, -0.3)
            if b % 4 == 0:
                for k, m in enumerate(chord):
                    _add(L, t, tone(midi(m), beat * 4 + 0.2, "pad"), 0.07, (k - 1.5) * 0.3)
                _add(L, t, tone(midi(root), beat * 1.6, "bass"), 0.28)
            if b % 2 == 0:
                _add(L, t + beat * 0.5, tone(midi(chord[(b // 2) % len(chord)] + 12), 1.0, "keys"), 0.08, 0.25)
            if b % 8 == 6:
                _add(L, t, tone(midi(chord[-1] + 24), 1.2, "bell"), 0.05, -0.4)
        else:
            if not brk:
                _add(L, t, K, 0.75)
                if b % 2 == 1:
                    _add(L, t, C, 0.42, 0.08)
            for s in range(4):
                _add(L, t + s * beat / 4, Hh, 0.16 if s % 2 else 0.24, 0.35)
            if b % 2 == 1:
                _add(L, t + beat / 2, Ho, 0.12, -0.3)
            for s, off in enumerate((0, 0.75)):
                _add(L, t + off * beat, tone(midi(root - (12 if s else 0)), beat * 0.45, "bass"), 0.3)
            arp = chord + [chord[0] + 12]
            for s in range(2):
                _add(L, t + s * beat / 2, tone(midi(arp[(b * 2 + s) % len(arp)] + 12), 0.4, "pluck"), 0.11, (s - 0.5) * 0.5)
    # gentle bus glue: soft clip + fade in/out
    L = np.tanh(L * 1.2) / 1.2
    fi, fo = int(0.05 * SR), int(0.6 * SR)
    L[:fi] *= np.linspace(0, 1, fi)[:, None]
    end = int(dur * SR)
    L[end - fo:end] *= np.linspace(1, 0.15, fo)[:, None]
    return L[:end]


# ---------------------------------------------------------------- SFX (synthesised; no third-party samples)
def sfx(kind: str, seed: int = 0) -> np.ndarray:
    """Synthesised one-shot (no third-party samples), peak-limited to 0.89 so every cue sits under full scale."""
    x = _sfx_raw(kind, seed)
    pk = float(np.abs(x).max()) if len(x) else 0.0
    return (x * (0.89 / pk)).astype(np.float32) if pk > 0.89 else x


def _sfx_raw(kind: str, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    if kind == "whoosh":  # band-limited noise sweep, rising then falling
        n = int(0.32 * SR)
        t = np.arange(n) / SR
        x = _noise(n, rng)
        y = _lp_fast(x, 6) - _lp_fast(x, 40)
        e = np.sin(np.pi * t / 0.32) ** 2
        return (y * e * 2.2).astype(np.float32)
    if kind == "swish":  # shorter, brighter whip
        n = int(0.18 * SR)
        t = np.arange(n) / SR
        x = _noise(n, rng)
        y = x - _lp_fast(x, 8)
        return (y * np.sin(np.pi * t / 0.18) ** 3 * 1.2).astype(np.float32)
    if kind == "pop":  # bubbly pitch-drop blip
        n = int(0.11 * SR)
        t = np.arange(n) / SR
        f = 900 * np.exp(-t * 28) + 240
        return (np.sin(np.cumsum(2 * np.pi * f / SR)) * np.exp(-t * 38) * 0.9).astype(np.float32)
    if kind == "tick":
        n = int(0.05 * SR)
        t = np.arange(n) / SR
        return (np.sin(2 * np.pi * 2400 * t) * np.exp(-t * 120) * 0.6).astype(np.float32)
    if kind == "shimmer":
        n = int(0.7 * SR)
        x = np.zeros(n, np.float32)
        for k, m in enumerate((88, 91, 95, 100)):
            seg = tone(midi(m), 0.6, "bell")
            i = int(k * 0.035 * SR)
            x[i:i + len(seg)] += seg[: n - i] * 0.3
        return x
    if kind == "impact":  # soft sub thump for the hook / logo
        n = int(0.6 * SR)
        t = np.arange(n) / SR
        f = 38 + 90 * np.exp(-t * 18)
        return (np.sin(np.cumsum(2 * np.pi * f / SR)) * np.exp(-t * 5) * 0.9).astype(np.float32)
    raise ValueError(f"sfx desconhecido: {kind}")


# ---------------------------------------------------------------- mix + master
def duck_envelope(active: np.ndarray, attack: float, release: float, rate: int = 1000) -> np.ndarray:
    """0..1 ducking amount from a speech on/off mask: rises in `attack` s, falls in `release` s (computed at 1 kHz)."""
    step = SR // rate
    a = active[::step]
    out = np.empty(len(a), np.float32)
    up, down = 1 / max(1, attack * rate), 1 / max(1, release * rate)
    g = 0.0
    for i, v in enumerate(a):
        g = min(1.0, g + up) if v > 0.5 else max(0.0, g - down)
        out[i] = g
    return np.repeat(out, step)[: len(active)] if len(out) else np.zeros(len(active), np.float32)


def mix(voice_lines: list[tuple[float, Path]], dur: float, music_bed: np.ndarray, cues: list[tuple[float, str, float]],
        music_db: float = -8.0, duck_db: float = 9.0, sfx_db: float = -14.0, seed: int = 0) -> np.ndarray:
    """Voice at full level; music `music_db` with sidechain-style ducking (`duck_db` under speech, 80 ms attack,
    250 ms release); SFX cues (t, kind, extra_db). Returns stereo float32."""
    n = int(dur * SR)
    out = np.zeros((n, 2), np.float32)
    vo = np.zeros(n, np.float32)
    for t, f in voice_lines:
        x = read_wav(f)
        i = int(t * SR)
        x = x[: max(0, n - i)]
        vo[i:i + len(x)] += x
    # envelope of the voice -> ducking gain
    env = np.abs(vo)
    win = int(0.03 * SR)
    env = _lp_fast(env, win)
    active = (env > 0.01).astype(np.float32)
    g = duck_envelope(active, attack=0.08, release=0.25)
    duck = 10 ** (-(duck_db * np.clip(g, 0, 1)) / 20)
    m = music_bed[:n] if len(music_bed) >= n else np.pad(music_bed, ((0, n - len(music_bed)), (0, 0)))
    out += m * (10 ** (music_db / 20)) * duck[:, None]
    for k, (t, kind, extra) in enumerate(cues):
        x = sfx(kind, seed + k)
        _add(out, t, x, 10 ** ((sfx_db + extra) / 20), pan=((k * 37) % 9 - 4) / 10)
    out[:, 0] += vo
    out[:, 1] += vo
    return out


def loudnorm(src: Path, dst: Path, target: float = -14.0, tp: float = -1.5) -> dict:
    """2-pass EBU R128 to `target` LUFS, true peak `tp`, plus a brickwall limiter (same recipe as scripts/master.sh)."""
    p = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(src), "-af",
                        f"loudnorm=I={target}:TP={tp}:LRA=11:print_format=json", "-f", "null", "-"],
                       capture_output=True, text=True)
    m = json.loads(re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", p.stderr, re.S).group(0))
    af = (f"loudnorm=I={target}:TP={tp}:LRA=11:measured_I={m['input_i']}:measured_TP={m['input_tp']}:"
          f"measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true,"
          f"alimiter=limit=0.75:attack=1:release=40:level=false")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(src), "-af", af, "-ar", str(SR), str(dst)], check=True)
    return {"input_i": float(m["input_i"]), "target": target, "tp": tp}


def measure(mp4: Path) -> dict:
    e = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(mp4), "-af", "ebur128=peak=true", "-f", "null", "-"],
                       capture_output=True, text=True).stderr
    return {"lufs": float(re.findall(r"I:\s+(-?[\d.]+) LUFS", e)[-1]), "tp": float(re.findall(r"Peak:\s+(-?[\d.]+) dBFS", e)[-1])}


def sync_offsets(mix_mono: np.ndarray, voice_lines: list[tuple[float, Path]], search: float = 0.25) -> list[tuple[float, float]]:
    """For each voice take, (delta_s, corr): where the take best matches the final mix near its expected time.
    delta ~ 0 and corr high = the voice is exactly where the timing lock says (lip/word sync of the text cards)."""
    res = []
    hop = 8  # 6 kHz analysis is plenty for alignment
    y = mix_mono[::hop]
    sr = SR // hop
    for t, f in voice_lines:
        x = read_wav(f)[::hop]
        x = x[: int(1.2 * sr)] if len(x) > int(1.2 * sr) else x
        i0 = int(t * sr)
        lo, hi = max(0, i0 - int(search * sr)), i0 + int(search * sr)
        best, bk = -2.0, 0
        xn = (x - x.mean()) / (x.std() + 1e-9)
        for k in range(lo, min(hi, len(y) - len(x))):
            seg = y[k:k + len(x)]
            s = (seg - seg.mean()) / (seg.std() + 1e-9)
            c = float((xn * s).mean())
            if c > best:
                best, bk = c, k
        res.append((round((bk - i0) / sr, 3), round(best, 3)))
    return res
