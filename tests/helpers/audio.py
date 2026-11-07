"""Synthetic WAVs, in integers (the same bytes on every machine)."""

import io
import math
import struct
import wave


def pcm_wav(samples: list[int], sr: int = 24000) -> bytes:
    """A mono 16-bit WAV holding exactly `samples`."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1), w.setsampwidth(2), w.setframerate(sr)
        w.writeframes(struct.pack(f"<{len(samples)}h", *samples))
    return buf.getvalue()


def sine_wav(seconds: float = 0.4, sr: int = 24000, freq: int = 330) -> bytes:
    """A mono 16-bit WAV of a `freq` Hz sine (amplitude 8000) lasting `seconds`."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1), w.setsampwidth(2), w.setframerate(sr)
        w.writeframes(b"".join(struct.pack("<h", int(8000 * math.sin(2 * math.pi * freq * i / sr))) for i in range(int(seconds * sr))))
    return buf.getvalue()
