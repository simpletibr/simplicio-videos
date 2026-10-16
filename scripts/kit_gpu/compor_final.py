"""Cola o resultado gerado SO dentro da mascara do alvo e copia o audio ORIGINAL sem recodificar.

Por que existe: os modelos (Wan Animate, VACE) redesenham o quadro inteiro e passam por compressao; o fundo e as
outras pessoas saem levemente diferentes do original. Esta etapa pega os pixels ORIGINAIS fora da mascara e so
usa o que o modelo gerou dentro dela (com uma borda suave), e remonta o audio do original com -c copy
(bit a bit igual). So depois disso a conferencia "fora da mascara nao mudou" faz sentido.

Uso:
  python compor_final.py --original entradas\\clipe_corte_75q_480x848.mp4 --gerado saida\\animate.mp4 ^
        --mascara mascaras --saida final.mp4

--mascara: pasta de PNGs (branco = alvo), video de mascara ou imagem unica.
--gerado pode ter outro tamanho (e redimensionado ao do original) e, com --reamostrar, outro numero de quadros
(cada quadro do original recebe o quadro gerado mais proximo no tempo; o avatar fica menos fluido, mas o sincronismo
com o audio e mantido). Sem --reamostrar, numeros de quadros diferentes sao um erro.

Transicao: a mascara e dilatada em --dilatar px (padrao 4) e suavizada (--suavizar, padrao 3). A borda de mistura
termina a cerca de dilatar + 1,5*suavizar px da mascara; use conferir_troca.py --dilatar maior que isso (padrao 10).
O video final e recodificado em H.264 (crf 14); isso deixa uma diferenca minima fora da mascara (PSNR tipico
acima de 45 dB, medido no teste do kit), nao exatamente zero.
"""
from __future__ import annotations

import argparse
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    import cv2
    import numpy as np
except ImportError as e:  # noqa: BLE001
    print(f"ERRO: falta {e.name}. Instale com:  python -m pip install numpy opencv-python-headless")
    sys.exit(2)

CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
EXT_VIDEO = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v", ".gif"}
EXT_IMG = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}


def achar_ffmpeg(arg):
    for cand in (arg, os.environ.get("FFMPEG")):
        if cand and shutil.which(cand):
            return shutil.which(cand)
    if shutil.which("ffmpeg"):
        return shutil.which("ffmpeg")
    try:
        import imageio_ffmpeg  # type: ignore

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:  # noqa: BLE001
        return None


def chave_natural(p: Path):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", p.name)]


def ler_imagem_cinza(p: Path):
    img = cv2.imdecode(np.fromfile(str(p), dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise SystemExit(f"ERRO: nao consegui ler a imagem {p}")
    return img


def sondar(ffmpeg, p: Path) -> dict:
    r = subprocess.run([ffmpeg, "-hide_banner", "-i", str(p)], capture_output=True, text=True, errors="replace",
                       creationflags=CREATE_NO_WINDOW)
    t = r.stderr
    m = re.search(r"Video:.*?, (\d{2,5})x(\d{2,5})[ ,\[]", t)
    if not m:
        raise SystemExit(f"ERRO: nao consegui ler o video {p}")
    f = re.search(r"([\d.]+) fps", t)
    cor = re.search(r"Video:.*?yuv\w*\(([^)]*)\)", t)
    return {"largura": int(m.group(1)), "altura": int(m.group(2)), "fps": float(f.group(1)) if f else 25.0,
            "audio": "Audio:" in t, "cor": cor.group(1) if cor else ""}


def opcoes_de_cor(tags: str) -> tuple[list[str], list[str]]:
    """Do texto de cor do ffmpeg (ex.: 'tv, bt709, progressive') tira o filtro de conversao e as etiquetas de saida,
    para o arquivo final ter a MESMA matriz de cor do original. Sempre usa accurate_rnd+full_chroma_int: sem isso a
    conversao RGB->YUV do ffmpeg deixa um erro de ate 5 niveis (medido no teste do kit) que apareceria como se o
    fundo tivesse mudado. Sem etiqueta de cor no original: converte com a matriz padrao e nao etiqueta."""
    flags = "flags=accurate_rnd+full_chroma_int"
    partes = [x.strip() for x in tags.split(",") if x.strip() and x.strip() != "progressive"]
    resto = partes[1:] if partes and partes[0] in ("tv", "pc", "mpeg", "jpeg") else partes
    faixa = "pc" if partes and partes[0] in ("pc", "jpeg") else "tv"
    if not resto:
        return ["-vf", f"scale={flags},format=yuv420p"], []
    esp, prim, trc = (resto[0].split("/") + ["", ""])[:3] if "/" in resto[0] else (resto[0], resto[0], resto[0])
    matriz = {"bt709": "bt709", "smpte170m": "smpte170m", "bt470bg": "bt601", "bt2020nc": "bt2020"}.get(esp)
    if not matriz:
        return ["-vf", f"scale={flags},format=yuv420p"], []
    vf = ["-vf", f"scale={flags}:out_color_matrix={matriz}:out_range={faixa},format=yuv420p"]
    tag = ["-colorspace", esp, "-color_range", faixa]
    if prim not in ("", "unknown"):
        tag += ["-color_primaries", prim]
    if trc not in ("", "unknown"):
        tag += ["-color_trc", trc]
    return vf, tag


class Leitor:
    def __init__(self, ffmpeg, caminho: Path, info: dict):
        self.w, self.h = info["largura"], info["altura"]
        self.proc = subprocess.Popen([ffmpeg, "-v", "error", "-noautorotate", "-i", str(caminho), "-map", "0:v:0", "-f",
                                      "rawvideo", "-pix_fmt", "bgr24", "-"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                     bufsize=self.w * self.h * 6, creationflags=CREATE_NO_WINDOW)

    def proximo(self):
        tam = self.w * self.h * 3
        b = self.proc.stdout.read(tam)
        return None if len(b) < tam else np.frombuffer(b, dtype=np.uint8).reshape(self.h, self.w, 3).copy()

    def fechar(self):
        try:
            self.proc.stdout.close()
            self.proc.terminate()
            self.proc.wait(timeout=5)
        except Exception:  # noqa: BLE001
            pass


def carregar_mascaras(caminho: Path, ffmpeg) -> list[np.ndarray]:
    if caminho.is_dir():
        arqs = sorted([p for p in caminho.iterdir() if p.suffix.lower() in EXT_IMG], key=chave_natural)
        if not arqs:
            raise SystemExit(f"ERRO: sem imagens em {caminho}")
        return [ler_imagem_cinza(p) > 127 for p in arqs]
    if caminho.suffix.lower() in EXT_VIDEO:
        info = sondar(ffmpeg, caminho)
        lv, out = Leitor(ffmpeg, caminho, info), []
        while True:
            q = lv.proximo()
            if q is None:
                break
            out.append(cv2.cvtColor(q, cv2.COLOR_BGR2GRAY) > 127)
        lv.fechar()
        return out
    if caminho.suffix.lower() in EXT_IMG:
        return [ler_imagem_cinza(caminho) > 127]
    raise SystemExit("ERRO: --mascara deve ser pasta de PNGs, video ou imagem.")


def main() -> int:
    ap = argparse.ArgumentParser(description="Cola o gerado dentro da mascara sobre o original e copia o audio original.")
    ap.add_argument("--original", required=True)
    ap.add_argument("--gerado", required=True)
    ap.add_argument("--mascara", required=True)
    ap.add_argument("--saida", required=True, help="mp4 final")
    ap.add_argument("--dilatar", type=int, default=4, help="px de dilatacao da mascara (padrao 4)")
    ap.add_argument("--suavizar", type=int, default=3, help="px de suavizacao da borda (padrao 3)")
    ap.add_argument("--crf", type=int, default=14, help="qualidade x264 (menor = melhor; padrao 14)")
    ap.add_argument("--inverter-mascara", action="store_true")
    ap.add_argument("--reamostrar", action="store_true", help="aceita numero de quadros diferente (quadro mais proximo no tempo)")
    ap.add_argument("--ffmpeg")
    a = ap.parse_args()

    ffmpeg = achar_ffmpeg(a.ffmpeg)
    if not ffmpeg:
        print("ERRO: ffmpeg nao encontrado.")
        return 2
    po, pg, pm = Path(a.original), Path(a.gerado), Path(a.mascara)
    for p in (po, pg, pm):
        if not p.exists():
            print(f"ERRO: nao achei {p}")
            return 2
    io, ig = sondar(ffmpeg, po), sondar(ffmpeg, pg)
    W, H, fps = io["largura"], io["altura"], io["fps"]
    masks = carregar_mascaras(pm, ffmpeg)
    if a.inverter_mascara:
        masks = [~m for m in masks]
    lo, lg = Leitor(ffmpeg, po, io), Leitor(ffmpeg, pg, ig)

    def ajustar(q):
        if (q.shape[1], q.shape[0]) != (W, H):
            return cv2.resize(q, (W, H), interpolation=cv2.INTER_AREA if q.shape[1] * q.shape[0] > W * H else cv2.INTER_CUBIC)
        return q

    gerados = None
    if a.reamostrar:
        gerados = []
        while True:
            q = lg.proximo()
            if q is None:
                break
            gerados.append(q)
        n_g = len(gerados)
        print(f"Gerado: {n_g} quadros lidos na memoria.")
    originais = []
    if a.reamostrar:
        while True:
            q = lo.proximo()
            if q is None:
                break
            originais.append(q)
        n_o = len(originais)
    else:
        n_o = n_g = None

    k = None
    if a.dilatar > 0:
        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * a.dilatar + 1, 2 * a.dilatar + 1))
    sigma = max(a.suavizar, 0) / 2.0
    ksz = 2 * int(math.ceil(3 * sigma)) + 1

    cmd = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}",
           "-r", f"{fps:g}", "-i", "pipe:0", "-i", str(po), "-map", "0:v:0"]
    if io["audio"]:
        cmd += ["-map", "1:a:0", "-c:a", "copy"]
    vf_cor, tag_cor = opcoes_de_cor(io.get("cor", ""))
    cmd += vf_cor + ["-c:v", "libx264", "-preset", "slow", "-crf", str(a.crf), "-pix_fmt", "yuv420p", "-threads", "1"] + tag_cor
    cmd += ["-fflags", "+bitexact", "-flags:v", "+bitexact", "-map_metadata", "-1", "-movflags", "+faststart", a.saida]
    erro_tmp = tempfile.TemporaryFile()
    enc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=erro_tmp, creationflags=CREATE_NO_WINDOW)

    i = 0
    concluido = False
    try:
        while True:
            if a.reamostrar:
                if i >= n_o:
                    break
                qo = originais[i]
                qg = gerados[min(n_g - 1, int(round(i * n_g / n_o)))] if n_g != n_o else gerados[i]
            else:
                qo, qg = lo.proximo(), lg.proximo()
                if qo is None and qg is None:
                    break
                if qo is None or qg is None:
                    raise SystemExit(f"ERRO: os videos tem numeros de quadros diferentes (parou no quadro {i}). "
                                     "Use --reamostrar se for esperado (ex.: gerado a 16 fps).")
            qg = ajustar(qg)
            m = masks[0] if len(masks) == 1 else (masks[i] if i < len(masks) else np.zeros((H, W), bool))
            if m.shape != (H, W):
                m = cv2.resize(m.astype(np.uint8), (W, H), interpolation=cv2.INTER_NEAREST) > 0
            mm = m.astype(np.uint8)
            if k is not None and mm.any():
                mm = cv2.dilate(mm, k)
            alfa = mm.astype(np.float32)
            if sigma > 0 and mm.any():
                alfa = cv2.GaussianBlur(alfa, (ksz, ksz), sigma)
            alfa = alfa[..., None]
            saida = (qg.astype(np.float32) * alfa + qo.astype(np.float32) * (1.0 - alfa)).round().astype(np.uint8)
            enc.stdin.write(saida.tobytes())
            i += 1
        enc.stdin.close()
        enc.wait()
        concluido = True
    finally:
        lo.fechar()
        lg.fechar()
        if not concluido:  # erro no meio: nao deixa um arquivo pela metade
            try:
                enc.kill()
                enc.wait(timeout=10)
            except Exception:  # noqa: BLE001
                pass
            try:
                Path(a.saida).unlink()
            except OSError:
                pass
    if enc.returncode != 0:
        erro_tmp.seek(0)
        print("ERRO do ffmpeg:", erro_tmp.read().decode(errors="replace")[-800:])
        return 1
    if len(masks) not in (1, i):
        print(f"AVISO: a mascara tem {len(masks)} quadros e o video {i}.")
    print(f"Pronto: {a.saida}  ({i} quadros, {W}x{H}, {fps:g} fps, audio {'copiado do original sem recodificar' if io['audio'] else 'inexistente'}; "
          f"cor do original: {io.get('cor') or 'sem etiqueta'})")
    print("Agora rode conferir_troca.py com o ORIGINAL (mesma resolucao) e este arquivo.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
