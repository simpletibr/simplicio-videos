"""`simplicio-video qc`: controle de qualidade de um MP4 (ffmpeg e ffprobe; sem modelo, sem rede).

`qc congelado` acha os intervalos em que o vídeo fica num mesmo quadro por pelo menos --min-s segundos (filtro freezedetect
do ffmpeg, ruído 0.001). Um quadro congelado até o fim do arquivo é fechado com a duração do arquivo.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

SCHEMA = "simplicio.qc-congelado/v1"
RUIDO = 0.001

HELP = """qc (controle de qualidade de um MP4; ffmpeg e ffprobe, sem modelo e sem rede)

  congelado MP4 [--min-s 0.5] [--json]
                                                   intervalos em que o vídeo fica num mesmo quadro por pelo menos
                                                   --min-s segundos (ffmpeg freezedetect); --json grava
                                                   simplicio.qc-congelado/v1 em stdout com inicio_s, fim_s, duracao_s

Exemplos:
  simplicio-video qc congelado out/video.mp4
  simplicio-video qc congelado out/video.mp4 --min-s 0.3 --json
"""


class QcError(Exception):
    pass


def _duracao_arquivo(mp4: Path) -> float:
    p = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(mp4)],
                       capture_output=True, text=True)
    if p.returncode != 0 or not p.stdout.strip():
        raise QcError(f"qc: ffprobe não leu a duração de {mp4}")
    return float(p.stdout.strip())


def detecta_congelado(mp4: Path, min_s: float) -> list[dict]:
    if min_s <= 0:
        raise QcError("qc: --min-s tem de ser maior que zero")
    cmd = ["ffmpeg", "-hide_banner", "-nostats", "-i", str(mp4), "-map", "0:v:0",
           "-vf", f"freezedetect=n={RUIDO}:d={min_s:g}", "-f", "null", "-"]
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise QcError(f"qc: ffmpeg falhou ao ler {mp4}:\n{(p.stderr or '')[-1500:]}")
    inicios = [float(x) for x in re.findall(r"freeze_start: ([0-9.]+)", p.stderr)]
    duracoes = [float(x) for x in re.findall(r"freeze_duration: ([0-9.]+)", p.stderr)]
    intervalos = []
    for i, inicio in enumerate(inicios):
        if i < len(duracoes):
            dur = duracoes[i]
        else:  # quadro congelado até o fim do arquivo: o freezedetect não escreve a duração
            dur = _duracao_arquivo(mp4) - inicio
        dur = round(max(dur, 0.0), 3)
        intervalos.append({"inicio_s": round(inicio, 3), "fim_s": round(inicio + dur, 3), "duracao_s": dur})
    return intervalos


def run_qc(args: list[str]) -> int:
    if not args or args[0] in ("-h", "--help"):
        print(HELP)
        return 0
    if args[0] != "congelado":
        raise QcError(f"qc: subcomando desconhecido: {args[0]} (use: congelado)")
    mp4, min_s, como_json = None, 0.5, False
    resto = args[1:]
    i = 0
    while i < len(resto):
        a = resto[i]
        if a == "--json":
            como_json = True
        elif a == "--min-s":
            i += 1
            if i >= len(resto):
                raise QcError("qc: --min-s pede um número de segundos")
            try:
                min_s = float(resto[i])
            except ValueError:
                raise QcError(f"qc: --min-s inválido: {resto[i]!r}") from None
        elif a.startswith("-"):
            raise QcError(f"qc: opção desconhecida: {a}")
        elif mp4 is None:
            mp4 = Path(a).expanduser()
        else:
            raise QcError(f"qc: argumento extra: {a}")
        i += 1
    if mp4 is None:
        raise QcError("qc congelado: falta o MP4 (simplicio-video qc congelado MP4 [--min-s 0.5] [--json])")
    if not mp4.is_file():
        raise QcError(f"qc: arquivo não encontrado: {mp4}")
    intervalos = detecta_congelado(mp4, min_s)
    if como_json:
        doc = {"schema": SCHEMA, "arquivo": str(mp4), "min_s": min_s, "intervalos": intervalos}
        print(json.dumps(doc, ensure_ascii=False, indent=2))
        return 0
    print(f"{len(intervalos)} intervalo(s) de quadro congelado com pelo menos {min_s:g} s em {mp4.name}")
    for iv in intervalos:
        print(f"  de {iv['inicio_s']:.3f} s a {iv['fim_s']:.3f} s ({iv['duracao_s']:.3f} s)")
    return 0
