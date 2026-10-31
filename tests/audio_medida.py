"""Medições de áudio dos testes do BRASA, em Python puro (sem numpy: a licença BSD-3 em AND com CC0/Zlib/0BSD é negada
pelo gate de licenças, docs/licenses.md).

- le_wav: WAV PCM 16 bits -> canais em ponto flutuante;
- fft: FFT radix-2 iterativa (comprimento potência de 2);
- potencia_banda_db / freq_dominante: janela de Hann de N amostras a partir de t0 (segundos), por FFT.
"""

from __future__ import annotations

import cmath
import math
import wave
from array import array


def le_wav(path) -> tuple[int, list[list[float]]]:
    with wave.open(str(path), "rb") as w:
        sr, n, ch = w.getframerate(), w.getnframes(), w.getnchannels()
        dados = array("h")
        dados.frombytes(w.readframes(n))
    canais = [[dados[i * ch + k] / 32768.0 for i in range(n)] for k in range(ch)]
    return sr, canais


def fft(xs: list[complex]) -> list[complex]:
    n = len(xs)
    assert n & (n - 1) == 0, "comprimento da FFT tem de ser potência de 2"
    a = list(xs)
    j = 0
    for i in range(1, n):  # permutação por bits reversos
        bit = n >> 1
        while j & bit:
            j ^= bit
            bit >>= 1
        j |= bit
        if i < j:
            a[i], a[j] = a[j], a[i]
    comprimento = 2
    while comprimento <= n:
        ang = -2 * math.pi / comprimento
        wl = cmath.exp(1j * ang)
        for inicio in range(0, n, comprimento):
            w = 1.0 + 0j
            for k in range(comprimento // 2):
                u = a[inicio + k]
                v = a[inicio + k + comprimento // 2] * w
                a[inicio + k] = u + v
                a[inicio + k + comprimento // 2] = u - v
                w *= wl
        comprimento <<= 1
    return a


def espectro(x: list[float], sr: int, t0: float, n: int = 1 << 15):
    """Magnitudes (com Hann) de n amostras a partir de t0. Devolve (frequências, magnitudes) só da metade positiva."""
    i0 = int(round(t0 * sr))
    seg = x[i0:i0 + n]
    if len(seg) < n:
        raise ValueError(f"janela curta: {len(seg)} de {n} amostras a partir de {t0} s")
    jan = [0.5 - 0.5 * math.cos(2 * math.pi * i / (n - 1)) for i in range(n)]
    X = fft([complex(seg[i] * jan[i]) for i in range(n)])
    freqs = [k * sr / n for k in range(n // 2 + 1)]
    mags = [abs(X[k]) for k in range(n // 2 + 1)]
    return freqs, mags


def potencia_banda_db(x: list[float], sr: int, t0: float, f0: float, f1: float, n: int = 1 << 15) -> float:
    """Potência (dB) da banda f0..f1 numa janela de n amostras a partir de t0."""
    freqs, mags = espectro(x, sr, t0, n)
    p = sum(m * m for f, m in zip(freqs, mags) if f0 <= f <= f1)
    return 10 * math.log10(p)


def freq_dominante(x: list[float], sr: int, t0: float, f0: float = 50.0, f1: float = 2500.0, n: int = 1 << 15) -> float:
    freqs, mags = espectro(x, sr, t0, n)
    melhor = max((k for k, f in enumerate(freqs) if f0 <= f <= f1), key=lambda k: mags[k])
    return freqs[melhor]


def tons(n_amostras: int, sr: int, componentes: list[tuple[float, float]]) -> list[float]:
    """Soma de senoides: componentes = [(frequência Hz, amplitude)], do início ao fim."""
    out = [0.0] * n_amostras
    for f, amp in componentes:
        w = 2 * math.pi * f / sr
        for i in range(n_amostras):
            out[i] += amp * math.sin(w * i)
    return out


def grava_wav(path, canais: list[list[float]], sr: int = 48000) -> None:
    """canais: uma lista por canal, em [-1, 1]; grava PCM 16 bits entrelaçado."""
    n = len(canais[0])
    dados = array("h", [0] * (n * len(canais)))
    for k, canal in enumerate(canais):
        for i, v in enumerate(canal):
            dados[i * len(canais) + k] = max(-32768, min(32767, int(round(v * 32767))))
    with wave.open(str(path), "wb") as w:
        w.setnchannels(len(canais))
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(dados.tobytes())
