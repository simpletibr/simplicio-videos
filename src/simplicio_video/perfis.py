"""Perfis de saída: `saida.qualidade` com os valores master, lite e thumb (BRASA, etapa 1).

- master: H.264 CRF 16, maxrate 32 Mbps, bufsize 64 Mbps, tags de cor BT.709, AAC 320 kbps, +faststart.
- lite: H.264 maxrate 10 Mbps (bufsize 20 Mbps: sem ele o maxrate não tem efeito no x264), AAC 192 kbps, +faststart.
- thumb: só o PNG do quadro 0, sem fade, e nunca um MP4.

`args_saida` é função pura: devolve a lista de argumentos do ffmpeg, sem rodar nada. O scripts/master.sh recebe essa
lista num arquivo (perfil.args, gravado pelo compilador) e a usa na codificação final; o áudio continua com a
normalização de loudness.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

PERFIS = ("master", "lite", "thumb")
X264_BT709 = "colorprim=bt709:transfer=bt709:colormatrix=bt709"

# qualidade do HyperFrames (--quality) por perfil: o quadro é o mesmo para master e lite; thumb só precisa do quadro 0
_QUALIDADE_RENDER = {"master": "delivery", "lite": "delivery", "thumb": "draft"}


def qualidade_render(perfil: str) -> str:
    _valida(perfil)
    return _QUALIDADE_RENDER[perfil]


def args_saida(perfil: str) -> list[str]:
    """Argumentos de saída do ffmpeg para o MP4 final (master e lite). thumb não tem MP4: ver encerra_thumb."""
    if perfil == "master":
        return ["-c:v", "libx264", "-crf", "16", "-maxrate", "32M", "-bufsize", "64M", "-pix_fmt", "yuv420p",
                "-x264-params", X264_BT709, "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
                "-c:a", "aac", "-b:a", "320k", "-movflags", "+faststart"]
    if perfil == "lite":
        return ["-c:v", "libx264", "-maxrate", "10M", "-bufsize", "20M", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart"]
    if perfil == "thumb":
        raise ValueError("thumb não gera MP4: não tem argumentos de vídeo (use encerra_thumb, que grava o PNG do quadro 0)")
    _valida(perfil)
    raise AssertionError("inalcançável")  # _valida já recusou o perfil


def args_thumb() -> list[str]:
    """Argumentos do ffmpeg para o PNG do quadro 0 (sem vídeo de saída, sem fade)."""
    return ["-frames:v", "1", "-an", "-c:v", "png"]


def encerra_thumb(raw: Path, destino: Path) -> dict:
    """Grava o quadro 0 de `raw` como PNG ao lado de `destino` (mesmo nome, extensão .png). Não grava MP4."""
    png = Path(destino).with_suffix(".png")
    png.parent.mkdir(parents=True, exist_ok=True)
    p = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(raw), *args_thumb(), str(png)],
                       capture_output=True, text=True)
    if p.returncode != 0 or not png.is_file():
        raise SystemExit(f"thumb: o ffmpeg não gerou o PNG do quadro 0 de {raw} ({p.returncode})\n{(p.stderr or '')[-2000:]}")
    return {"saida": png, "quadro": 0}


def _valida(perfil: str) -> None:
    if perfil not in PERFIS:
        raise ValueError(f"perfil de saída desconhecido: {perfil!r} (use {', '.join(PERFIS)})")
