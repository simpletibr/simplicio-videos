"""`simplicio-video qc`: controle de qualidade de um MP4 (ffmpeg e ffprobe; sem modelo, sem rede).

`qc congelado` acha os intervalos em que o vídeo fica num mesmo quadro por pelo menos --min-s segundos (filtro freezedetect
do ffmpeg, ruído 0.001). Um quadro congelado até o fim do arquivo é fechado com a duração do arquivo.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

SCHEMA = "simplicio.qc-congelado/v1"
RUIDO = 0.001


class QcError(Exception):
    pass


def adiciona_acoes(ap: argparse.ArgumentParser) -> None:
    """Acrescenta as ações do qc a um parser (o da CLI e o próprio run_qc usam o mesmo)."""
    acoes = ap.add_subparsers(dest="acao", metavar="AÇÃO", title="ações", required=True)
    c = acoes.add_parser("congelado", help="intervalos de quadro congelado (ffmpeg freezedetect)",
                         description="Lista os trechos em que o vídeo fica num mesmo quadro por pelo menos --min-s segundos. "
                                     "Um quadro congelado até o fim do arquivo é fechado com a duração do arquivo.",
                         epilog="exemplos:\n  simplicio-video qc congelado out/video.mp4\n"
                                "  simplicio-video qc congelado out/video.mp4 --min-s 0.3 --json")
    c.add_argument("mp4", help="MP4 a conferir")
    c.add_argument("--min-s", type=float, default=0.5, metavar="S",
                   help="duração mínima do quadro congelado, em segundos (padrão 0.5)")
    c.add_argument("--json", action="store_true", help=f"saída JSON ({SCHEMA}): intervalos com inicio_s, fim_s e duracao_s")


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="simplicio-video qc", description="Controle de qualidade de um MP4 com ffmpeg e ffprobe, "
                                 "sem modelo e sem rede.")
    adiciona_acoes(ap)
    return ap


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
    """Roda `simplicio-video qc ...` e devolve o código de saída (0 ok; 2 uso; erros de dado levantam QcError)."""
    try:
        ns = _parser().parse_args(args)
    except SystemExit as e:  # argparse já imprimiu a ajuda ou o erro de uso
        return int(e.code or 0)
    mp4 = Path(ns.mp4).expanduser()
    if not mp4.is_file():
        raise QcError(f"qc: arquivo não encontrado: {mp4}")
    intervalos = detecta_congelado(mp4, ns.min_s)
    if ns.json:
        doc = {"schema": SCHEMA, "arquivo": str(mp4), "min_s": ns.min_s, "intervalos": intervalos}
        print(json.dumps(doc, ensure_ascii=False, indent=2))
        return 0
    print(f"{len(intervalos)} intervalo(s) de quadro congelado com pelo menos {ns.min_s:g} s em {mp4.name}")
    for iv in intervalos:
        print(f"  de {iv['inicio_s']:.3f} s a {iv['fim_s']:.3f} s ({iv['duracao_s']:.3f} s)")
    return 0
