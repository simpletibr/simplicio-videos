"""Conferencia automatica do video com o personagem trocado. Roda em CPU, sem GPU.

Compara o video ORIGINAL com o video TROCADO e responde, com numeros:
  (a) FORA da mascara do alvo: as outras pessoas e o fundo mudaram? (diferenca media, PSNR e SSIM por quadro)
      e DENTRO da mascara: o alvo realmente mudou?
  (b) a regiao do alvo no video trocado se parece com a imagem do avatar? (cosseno de embeddings DINOv2
      e/ou CLIP), comparando tambem com o ator original (controle) para ver se a troca aproximou do avatar;
  (c) o audio e igual ao original (hash do PCM; se o audio foi recodificado, correlacao) e a duracao bate;
  (d) imprime um relatorio JSON (--saida) e um resumo em portugues.

Uso:
  python conferir_troca.py --original entradas\\clipe_corte_75q_480x848.mp4 --trocado saida\\final.mp4 ^
        --mascara mascaras --avatar entradas\\avatar_corpo_inteiro.png --saida relatorio.json

--mascara aceita uma PASTA de PNGs (um por quadro, ordem natural dos nomes, branco = alvo), um VIDEO de
mascara (branco = alvo) ou uma unica imagem (usada em todos os quadros).
Codigo de saida: 0 = tudo OK, 1 = alguma checagem falhou, 2 = erro de uso ou dependencia.

IMPORTANTE: os modelos de video (Wan, VACE) redesenham o quadro INTEIRO. Para a conferencia "fora da mascara"
dar zero, cole os pixels originais fora da mascara antes (compor_final.py faz isso e copia o audio original).

Limiares padrao (calibrados so com os 11 casos sinteticos do teste do kit, NAO com saidas reais do Wan):
  fora da mascara: PSNR minimo por quadro 40 dB e SSIM medio 0,98 (uma regravacao x264 crf 14 do proprio original
  fica em 41 a 43 dB; saida crua de modelo com borrao leve ficou em 38 a 39 dB; um retangulo +35 niveis em 30 dB);
  semelhanca com o avatar: o que vale e a MELHORA sobre o ator original (controle); no clipe de teste o ator original
  ja tem cosseno 0,48 (DINOv2-small) e 0,67 (CLIP) com o avatar, e um avatar colado por cima chegou a 0,74 e 0,82.
  Ajuste com --min-psnr, --min-ssim, --limiar-dino, --limiar-clip, --margem-melhora depois da sua 1a saida real.

Dependencias: numpy e opencv-python (ja vem no ComfyUI portatil: python_embeded\\python.exe conferir_troca.py ...)
e ffmpeg. Para DINOv2/CLIP: torch e transformers (tambem ja vem no ComfyUI). Sem eles use --modelo nenhum.
Pesos baixados na 1a vez do Hugging Face: facebook/dinov2-small (Apache-2.0, 88 MB) e, so se pedir CLIP,
laion/CLIP-ViT-B-32-laion2B-s34B-b79K (MIT, 605 MB). Use --offline se os pesos ja estiverem no cache.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
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
CINZA_NEUTRO = (104, 116, 124)  # BGR = media do ImageNet (124,116,104 RGB)


# ------------------------------------------------------------------ utilidades
def achar_ffmpeg(arg: str | None) -> str | None:
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


def sha256_arquivo(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def chave_natural(p: Path):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", p.name)]


def ler_imagem(p: Path, flag=cv2.IMREAD_COLOR):
    """Le imagem por bytes (funciona com acentos no caminho no Windows)."""
    dados = np.fromfile(str(p), dtype=np.uint8)
    img = cv2.imdecode(dados, flag)
    if img is None:
        raise SystemExit(f"ERRO: nao consegui ler a imagem {p}")
    return img


def sondar(ffmpeg: str, p: Path) -> dict:
    r = subprocess.run([ffmpeg, "-hide_banner", "-i", str(p)], capture_output=True, text=True, errors="replace",
                       creationflags=CREATE_NO_WINDOW)
    t = r.stderr
    info: dict = {"tem_video": False, "tem_audio": False, "duracao_s": None}
    m = re.search(r"Video:.*?, (\d{2,5})x(\d{2,5})[ ,\[]", t)
    if m:
        info.update(tem_video=True, largura=int(m.group(1)), altura=int(m.group(2)))
        f = re.search(r"([\d.]+) fps", t)
        info["fps"] = float(f.group(1)) if f else None
    cor = re.search(r"Video:.*?yuv\w*\(([^)]*)\)", t)
    info["cor"] = re.sub(r",?\s*progressive", "", cor.group(1)).strip(", ") if cor else ""
    m = re.search(r"Audio:.*?, (\d+) Hz, ([^,\n]+)", t)
    if m:
        canais = {"mono": 1, "stereo": 2}.get(m.group(2).strip(), None)
        if canais is None:
            d = re.match(r"(\d+)", m.group(2).strip())
            canais = int(d.group(1)) if d else 2
        info.update(tem_audio=True, taxa_hz=int(m.group(1)), canais=canais)
    m = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", t)
    if m:
        info["duracao_s"] = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    return info


class LeitorVideo:
    """Le quadros BGR de um video pelo ffmpeg (mesma decodificacao em qualquer sistema)."""

    def __init__(self, ffmpeg: str, caminho: Path, info: dict):
        self.w, self.h = info["largura"], info["altura"]
        self.fps = info.get("fps")
        self.proc = subprocess.Popen([ffmpeg, "-v", "error", "-noautorotate", "-i", str(caminho), "-map", "0:v:0",
                                      "-f", "rawvideo", "-pix_fmt", "bgr24", "-"], stdout=subprocess.PIPE,
                                     stderr=subprocess.DEVNULL, bufsize=self.w * self.h * 3 * 2,
                                     creationflags=CREATE_NO_WINDOW)
        self.n = 0

    def proximo(self):
        tam = self.w * self.h * 3
        b = self.proc.stdout.read(tam)
        if len(b) < tam:
            return None
        self.n += 1
        return np.frombuffer(b, dtype=np.uint8).reshape(self.h, self.w, 3)

    def fechar(self):
        try:
            self.proc.stdout.close()
            self.proc.terminate()
            self.proc.wait(timeout=5)
        except Exception:  # noqa: BLE001
            pass


# ------------------------------------------------------------------ mascaras
def carregar_mascaras(caminho: Path, ffmpeg: str, inverter: bool) -> tuple[list[np.ndarray], tuple[int, int], str]:
    """Retorna (lista de mascaras empacotadas em bits, (h, w), tipo). Branco = alvo."""
    brutas: list[np.ndarray] = []
    if caminho.is_dir():
        arqs = sorted([p for p in caminho.iterdir() if p.suffix.lower() in EXT_IMG], key=chave_natural)
        if not arqs:
            raise SystemExit(f"ERRO: nao ha imagens na pasta de mascaras {caminho}")
        for p in arqs:
            brutas.append(ler_imagem(p, cv2.IMREAD_GRAYSCALE))
        tipo = f"pasta com {len(arqs)} imagens"
    elif caminho.suffix.lower() in EXT_VIDEO:
        info = sondar(ffmpeg, caminho)
        if not info["tem_video"]:
            raise SystemExit(f"ERRO: nao consegui ler o video de mascara {caminho}")
        lv = LeitorVideo(ffmpeg, caminho, info)
        while True:
            q = lv.proximo()
            if q is None:
                break
            brutas.append(cv2.cvtColor(q, cv2.COLOR_BGR2GRAY))
        lv.fechar()
        tipo = f"video com {len(brutas)} quadros"
    elif caminho.suffix.lower() in EXT_IMG:
        brutas.append(ler_imagem(caminho, cv2.IMREAD_GRAYSCALE))
        tipo = "imagem unica (usada em todos os quadros)"
    else:
        raise SystemExit(f"ERRO: --mascara deve ser pasta de PNGs, video ou imagem: {caminho}")
    h, w = brutas[0].shape
    emp = []
    for m in brutas:
        b = m > 127
        if inverter:
            b = ~b
        if b.shape != (h, w):
            b = cv2.resize(b.astype(np.uint8), (w, h), interpolation=cv2.INTER_NEAREST) > 0
        emp.append(np.packbits(b))
    return emp, (h, w), tipo


def desempacotar(emp: np.ndarray, h: int, w: int) -> np.ndarray:
    return np.unpackbits(emp)[: h * w].reshape(h, w) > 0


# ------------------------------------------------------------------ metricas de pixel
def ssim_mapa(a_gray: np.ndarray, b_gray: np.ndarray) -> np.ndarray:
    a, b = a_gray.astype(np.float32), b_gray.astype(np.float32)
    c1, c2 = (0.01 * 255) ** 2, (0.03 * 255) ** 2
    g = lambda x: cv2.GaussianBlur(x, (11, 11), 1.5)  # noqa: E731
    mu_a, mu_b = g(a), g(b)
    saa, sbb, sab = g(a * a) - mu_a ** 2, g(b * b) - mu_b ** 2, g(a * b) - mu_a * mu_b
    return ((2 * mu_a * mu_b + c1) * (2 * sab + c2)) / ((mu_a ** 2 + mu_b ** 2 + c1) * (saa + sbb + c2))


def psnr_de_mse(mse: float) -> float:
    return 100.0 if mse <= 0 else min(100.0, 10 * math.log10(255.0 ** 2 / mse))


def metricas_quadro(orig: np.ndarray, troc: np.ndarray, alvo: np.ndarray, alvo_dil: np.ndarray, k_ssim: np.ndarray) -> dict:
    fora = ~alvo_dil
    n_fora = int(fora.sum())
    d = cv2.absdiff(orig, troc)
    r: dict = {"area_alvo_px": int(alvo.sum())}
    if n_fora:
        df = d[fora].astype(np.float32)
        r["dif_media_fora"] = float(df.mean())
        r["psnr_fora_db"] = psnr_de_mse(float((df ** 2).mean()))
        r["dif_max_fora"] = int(df.max())
        r["pct_fora_alterado"] = float(100.0 * ((d.max(axis=2) > 16) & fora).sum() / n_fora)
        valido = cv2.erode(fora.astype(np.uint8), k_ssim) > 0
        if valido.any():
            sm = ssim_mapa(cv2.cvtColor(orig, cv2.COLOR_BGR2GRAY), cv2.cvtColor(troc, cv2.COLOR_BGR2GRAY))
            r["ssim_fora"] = float(sm[valido].mean())
        else:
            r["ssim_fora"] = None
    else:
        r.update(dif_media_fora=None, psnr_fora_db=None, dif_max_fora=None, pct_fora_alterado=None, ssim_fora=None)
    n_alvo = int(alvo.sum())
    if n_alvo:
        di = d[alvo].astype(np.float32)
        r["dif_media_dentro"] = float(di.mean())
        r["pct_dentro_alterado"] = float(100.0 * ((d.max(axis=2) > 24) & alvo).sum() / n_alvo)
    else:
        r["dif_media_dentro"] = None
        r["pct_dentro_alterado"] = None
    return r


def resumo(v: list) -> dict | None:
    x = [a for a in v if a is not None]
    if not x:
        return None
    x_ord = sorted(x)
    return {"n": len(x), "media": float(np.mean(x)), "min": float(x_ord[0]), "max": float(x_ord[-1]),
            "p5": float(np.percentile(x, 5)), "mediana": float(np.median(x))}


# ------------------------------------------------------------------ identidade (DINOv2 / CLIP)
class Embedder:
    def __init__(self, tipo: str, nome: str, dispositivo: str, offline: bool):
        import torch  # noqa: WPS433
        from transformers import AutoModel, CLIPModel

        self.torch, self.tipo, self.nome, self.dispositivo = torch, tipo, nome, dispositivo
        kw = {"local_files_only": True} if offline else {}
        if tipo == "dinov2":
            self.modelo = AutoModel.from_pretrained(nome, **kw)
            self.media, self.desvio = (0.485, 0.456, 0.406), (0.229, 0.224, 0.225)
        else:
            self.modelo = CLIPModel.from_pretrained(nome, **kw)
            self.media, self.desvio = (0.4815, 0.4578, 0.4082), (0.2686, 0.2613, 0.2758)
        self.modelo.eval().to(dispositivo)

    def preparar(self, bgr: np.ndarray) -> np.ndarray:
        h, w = bgr.shape[:2]
        s = max(h, w)
        quadro = np.full((s, s, 3), CINZA_NEUTRO, np.uint8)
        y0, x0 = (s - h) // 2, (s - w) // 2
        quadro[y0:y0 + h, x0:x0 + w] = bgr
        interp = cv2.INTER_AREA if s > 224 else cv2.INTER_CUBIC
        quadro = cv2.resize(quadro, (224, 224), interpolation=interp)
        rgb = cv2.cvtColor(quadro, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        rgb = (rgb - np.array(self.media, np.float32)) / np.array(self.desvio, np.float32)
        return rgb.transpose(2, 0, 1)

    def embutir(self, imagens: list[np.ndarray]) -> np.ndarray:
        torch = self.torch
        x = torch.from_numpy(np.stack([self.preparar(i) for i in imagens])).to(self.dispositivo)
        with torch.no_grad():
            if self.tipo == "dinov2":
                v = self.modelo(pixel_values=x).pooler_output
            else:
                v = self.modelo.get_image_features(pixel_values=x)
                if not hasattr(v, "norm"):  # versoes novas podem devolver um objeto com pooler_output
                    v = v.pooler_output
        v = torch.nn.functional.normalize(v.float(), dim=-1)
        return v.cpu().numpy()


def fundo_neutro_avatar(bgr: np.ndarray, limiar: int = 16) -> np.ndarray:
    """Troca o fundo liso da folha por cinza neutro (so a parte do fundo ligada a borda da imagem)."""
    h, w = bgr.shape[:2]
    anel = np.concatenate([bgr[:3].reshape(-1, 3), bgr[-3:].reshape(-1, 3), bgr[:, :3].reshape(-1, 3), bgr[:, -3:].reshape(-1, 3)])
    fundo = np.median(anel, axis=0)
    cand = (np.abs(bgr.astype(np.float32) - fundo).max(axis=2) <= limiar).astype(np.uint8)
    n, rot = cv2.connectedComponents(cand, connectivity=4)
    ligados = set(np.unique(np.concatenate([rot[0], rot[-1], rot[:, 0], rot[:, -1]]))) - {0}
    bg = np.isin(rot, list(ligados)) if ligados else np.zeros((h, w), bool)
    out = bgr.copy()
    out[bg] = CINZA_NEUTRO
    return out


def recorte_alvo(img: np.ndarray, mascara: np.ndarray, pad: float, so_mascara: bool) -> np.ndarray | None:
    ys, xs = np.where(mascara)
    if len(ys) == 0:
        return None
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    py, px = int((y1 - y0) * pad), int((x1 - x0) * pad)
    y0, y1, x0, x1 = max(0, y0 - py), min(img.shape[0], y1 + py), max(0, x0 - px), min(img.shape[1], x1 + px)
    c = img[y0:y1, x0:x1].copy()
    if so_mascara:
        m = cv2.dilate(mascara.astype(np.uint8), np.ones((5, 5), np.uint8))[y0:y1, x0:x1] > 0
        c[~m] = CINZA_NEUTRO
    return c


# ------------------------------------------------------------------ audio
def pcm_nativo(ffmpeg: str, p: Path) -> bytes:
    r = subprocess.run([ffmpeg, "-v", "error", "-i", str(p), "-map", "0:a:0", "-f", "s16le", "-acodec", "pcm_s16le", "-"],
                       capture_output=True, creationflags=CREATE_NO_WINDOW)
    return r.stdout


def pcm_mono_16k(ffmpeg: str, p: Path) -> np.ndarray:
    r = subprocess.run([ffmpeg, "-v", "error", "-i", str(p), "-map", "0:a:0", "-ac", "1", "-ar", "16000", "-f", "f32le", "-"],
                       capture_output=True, creationflags=CREATE_NO_WINDOW)
    return np.frombuffer(r.stdout, dtype=np.float32).copy()


def correlacao_audio(a: np.ndarray, b: np.ndarray, max_lag: int = 3200) -> dict:
    if len(a) == 0 or len(b) == 0 or not np.any(a) or not np.any(b):
        return {"correlacao": 0.0, "atraso_ms": None, "snr_db": None}
    n = 1 << int(math.ceil(math.log2(len(a) + len(b))))
    fa, fb = np.fft.rfft(a.astype(np.float64), n), np.fft.rfft(b.astype(np.float64), n)
    xc = np.fft.irfft(fa * np.conj(fb), n)
    lags = np.concatenate([np.arange(0, min(max_lag, len(a)) + 1), np.arange(-min(max_lag, len(b)), 0)])
    vals = np.array([xc[l % n] for l in lags])
    k = int(np.argmax(vals))
    lag = int(lags[k])
    # alinha: a[lag:] com b[:] se lag>0; a[:] com b[-lag:] se lag<0
    if lag >= 0:
        aa, bb = a[lag:], b
    else:
        aa, bb = a, b[-lag:]
    m = min(len(aa), len(bb))
    aa, bb = aa[:m].astype(np.float64), bb[:m].astype(np.float64)
    na, nb = np.linalg.norm(aa), np.linalg.norm(bb)
    corr = float(np.dot(aa, bb) / (na * nb)) if na > 0 and nb > 0 else 0.0
    err = float(np.sum((aa - bb) ** 2))
    snr = float(10 * math.log10(np.sum(aa ** 2) / err)) if err > 0 else None
    return {"correlacao": corr, "atraso_ms": lag / 16.0, "snr_db": snr}


# ------------------------------------------------------------------ principal
def main() -> int:
    ap = argparse.ArgumentParser(description="Confere o video com o personagem trocado (CPU).")
    ap.add_argument("--original", required=True, help="video original (na mesma resolucao do trocado, de preferencia)")
    ap.add_argument("--trocado", required=True, help="video com o personagem trocado")
    ap.add_argument("--mascara", required=True, help="pasta de PNGs, video de mascara ou imagem unica (branco = alvo)")
    ap.add_argument("--avatar", action="append", default=[], help="imagem do avatar (pode repetir)")
    ap.add_argument("--saida", default="relatorio_conferencia.json", help="relatorio JSON")
    ap.add_argument("--inverter-mascara", action="store_true", help="a mascara tem o alvo em preto")
    ap.add_argument("--dilatar", type=int, default=10, help="margem (px) em volta da mascara que NAO conta como 'fora' (padrao 10)")
    ap.add_argument("--min-psnr", type=float, default=40.0, help="PSNR minimo por quadro fora da mascara, em dB (padrao 40)")
    ap.add_argument("--min-ssim", type=float, default=0.98, help="SSIM medio minimo fora da mascara (padrao 0,98)")
    ap.add_argument("--min-alvo-alterado", type=float, default=30.0, help="porcentagem minima de pixels do alvo que precisam ter mudado (padrao 30)")
    ap.add_argument("--modelo", default="dinov2", choices=["dinov2", "clip", "ambos", "nenhum"], help="comparacao com o avatar")
    ap.add_argument("--pesos-dinov2", default="facebook/dinov2-small")
    ap.add_argument("--pesos-clip", default="laion/CLIP-ViT-B-32-laion2B-s34B-b79K")
    ap.add_argument("--limiar-dino", type=float, default=0.50, help="cosseno minimo DINOv2 trocado x avatar (padrao 0,50)")
    ap.add_argument("--limiar-clip", type=float, default=0.70, help="cosseno minimo CLIP trocado x avatar (padrao 0,70)")
    ap.add_argument("--margem-melhora", type=float, default=0.05, help="quanto o trocado deve superar o original no cosseno (padrao 0,05)")
    ap.add_argument("--amostras", type=int, default=8, help="quadros usados na comparacao com o avatar (padrao 8)")
    ap.add_argument("--recorte-retangular", action="store_true", help="nao pintar de cinza o que esta fora da mascara no recorte")
    ap.add_argument("--avatar-fundo-original", action="store_true", help="nao trocar o fundo liso do avatar por cinza neutro")
    ap.add_argument("--dispositivo", default="cpu", help="cpu (padrao) ou cuda")
    ap.add_argument("--offline", action="store_true", help="nao baixar pesos; usar so o cache do Hugging Face")
    ap.add_argument("--tol-quadros", type=int, default=0, help="diferenca aceita no numero de quadros (padrao 0)")
    ap.add_argument("--tol-duracao", type=float, default=0.06, help="diferenca aceita de duracao em segundos (padrao 0,06)")
    ap.add_argument("--min-corr-audio", type=float, default=0.999, help="correlacao minima se o audio nao for byte a byte igual")
    ap.add_argument("--max-quadros", type=int, default=0, help="usar so os N primeiros quadros (0 = todos)")
    ap.add_argument("--pasta-debug", default="", help="grava recortes e o quadro de maior diferenca fora da mascara")
    ap.add_argument("--ffmpeg", help="caminho do ffmpeg")
    a = ap.parse_args()

    t_ini = time.time()
    ffmpeg = achar_ffmpeg(a.ffmpeg)
    if not ffmpeg:
        print("ERRO: ffmpeg nao encontrado (instale, ou use --ffmpeg).")
        return 2
    p_orig, p_troc, p_mask = Path(a.original), Path(a.trocado), Path(a.mascara)
    for p in (p_orig, p_troc, p_mask):
        if not p.exists():
            print(f"ERRO: nao achei {p}")
            return 2
    for p in map(Path, a.avatar):
        if not p.is_file():
            print(f"ERRO: nao achei o avatar {p}")
            return 2

    io, it = sondar(ffmpeg, p_orig), sondar(ffmpeg, p_troc)
    if not io["tem_video"] or not it["tem_video"]:
        print("ERRO: um dos videos nao tem trilha de video legivel.")
        return 2
    masks, (mh, mw), tipo_mask = carregar_mascaras(p_mask, ffmpeg, a.inverter_mascara)
    H, W = io["altura"], io["largura"]
    redim = (it["largura"], it["altura"]) != (W, H)

    print(f"Original: {W}x{H}, {io['fps']} fps | Trocado: {it['largura']}x{it['altura']}, {it['fps']} fps"
          + ("  (o trocado sera redimensionado para o tamanho do original)" if redim else ""))
    aviso_cor = ""
    if io["cor"] != it["cor"]:
        aviso_cor = (f"etiquetas de cor diferentes (original: '{io['cor'] or 'nenhuma'}', trocado: '{it['cor'] or 'nenhuma'}'): "
                     "isso desloca levemente as cores e derruba o PSNR fora da mascara sem que nada tenha sido redesenhado. "
                     "Gere o final com compor_final.py, que copia a etiqueta e a matriz de cor do original.")
        print("AVISO:", aviso_cor)
    print(f"Mascara: {tipo_mask}, {mw}x{mh}")

    k_dil = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * a.dilatar + 1, 2 * a.dilatar + 1)) if a.dilatar > 0 else None
    k_ssim = np.ones((11, 11), np.uint8)
    lo, lt = LeitorVideo(ffmpeg, p_orig, io), LeitorVideo(ffmpeg, p_troc, it)

    # ---- passe 1: pixels (fora e dentro da mascara) ----
    n_masks = len(masks)
    por_quadro: list[dict] = []
    areas: list[int] = []
    pior = {"psnr": 1e9, "i": -1}
    guarda_debug = bool(a.pasta_debug)
    quadro_pior = None
    i = 0
    try:
        while True:
            if a.max_quadros and i >= a.max_quadros:
                break
            qo, qt = lo.proximo(), lt.proximo()
            if qo is None or qt is None:
                break
            if redim:
                inter = cv2.INTER_AREA if it["largura"] * it["altura"] > W * H else cv2.INTER_CUBIC
                qt = cv2.resize(qt, (W, H), interpolation=inter)
            if n_masks == 1:
                emp = masks[0]
            elif i < n_masks:
                emp = masks[i]
            else:
                emp = None
            if emp is None:
                alvo = np.zeros((H, W), bool)
            else:
                alvo = desempacotar(emp, mh, mw)
                if (mh, mw) != (H, W):
                    alvo = cv2.resize(alvo.astype(np.uint8), (W, H), interpolation=cv2.INTER_NEAREST) > 0
            alvo_dil = (cv2.dilate(alvo.astype(np.uint8), k_dil) > 0) if (k_dil is not None and alvo.any()) else alvo
            m = metricas_quadro(qo, qt, alvo, alvo_dil, k_ssim)
            m["quadro"] = i
            por_quadro.append(m)
            areas.append(m["area_alvo_px"])
            if guarda_debug and m["psnr_fora_db"] is not None and m["psnr_fora_db"] < pior["psnr"]:
                pior = {"psnr": m["psnr_fora_db"], "i": i}
                quadro_pior = (qo.copy(), qt.copy(), alvo_dil.copy())
            i += 1
        # conta o que sobrou em cada video (para detectar diferenca de numero de quadros)
        if not a.max_quadros:
            while lo.proximo() is not None:
                pass
            while lt.proximo() is not None:
                pass
    finally:
        n_orig, n_troc = lo.n, lt.n
        lo.fechar()
        lt.fechar()
    n_comp = len(por_quadro)
    if n_comp == 0:
        print("ERRO: nao consegui comparar nenhum quadro.")
        return 2
    if n_masks not in (1, n_orig) and not a.max_quadros:
        print(f"AVISO: a mascara tem {n_masks} quadros e o video tem {n_orig}; quadros sem mascara foram tratados como 'sem alvo'.")

    # ---- criterios de video ----
    v: dict = {"cor_original": io["cor"], "cor_trocado": it["cor"], "aviso_cor": aviso_cor, "quadros_original": n_orig, "quadros_trocado": n_troc, "quadros_comparados": n_comp,
               "fps_original": io["fps"], "fps_trocado": it["fps"], "tamanho_original": [W, H],
               "tamanho_trocado": [it["largura"], it["altura"]], "redimensionado": redim,
               "duracao_container_original_s": io["duracao_s"], "duracao_container_trocado_s": it["duracao_s"]}
    dur_o = n_orig / io["fps"] if io["fps"] else None
    dur_t = n_troc / it["fps"] if it["fps"] else None
    v["duracao_video_original_s"], v["duracao_video_trocado_s"] = dur_o, dur_t
    ok_quadros = abs(n_orig - n_troc) <= a.tol_quadros
    ok_fps = bool(io["fps"] and it["fps"] and abs(io["fps"] - it["fps"]) <= 0.01)
    ok_dur = bool(dur_o is not None and dur_t is not None and abs(dur_o - dur_t) <= a.tol_duracao)
    v["ok_quadros"], v["ok_fps"], v["ok_duracao_video"] = ok_quadros, ok_fps, ok_dur

    # ---- fora e dentro da mascara ----
    ps = [q["psnr_fora_db"] for q in por_quadro]
    ss = [q["ssim_fora"] for q in por_quadro]
    r_psnr, r_ssim = resumo(ps), resumo(ss)
    r_dif = resumo([q["dif_media_fora"] for q in por_quadro])
    r_pct = resumo([q["pct_fora_alterado"] for q in por_quadro])
    quadros_ruins = [q["quadro"] for q in por_quadro if q["psnr_fora_db"] is not None and q["psnr_fora_db"] < a.min_psnr]
    ok_fora = bool(r_psnr and r_ssim and r_psnr["min"] >= a.min_psnr and r_ssim["media"] >= a.min_ssim)
    com_alvo = [q for q in por_quadro if q["area_alvo_px"] > 0]
    r_dentro = resumo([q["pct_dentro_alterado"] for q in com_alvo])
    r_dentro_dif = resumo([q["dif_media_dentro"] for q in com_alvo])
    ok_dentro = bool(r_dentro and r_dentro["media"] >= a.min_alvo_alterado)
    fora_info = {"criterios": {"min_psnr_db": a.min_psnr, "min_ssim_medio": a.min_ssim, "dilatar_px": a.dilatar},
                 "psnr_db": r_psnr, "ssim": r_ssim, "dif_media_0_255": r_dif, "pct_pixels_alterados_mais_de_16": r_pct,
                 "quadros_abaixo_do_psnr_minimo": quadros_ruins, "ok": ok_fora}
    dentro_info = {"criterio_min_pct_alterado": a.min_alvo_alterado, "quadros_com_alvo": len(com_alvo),
                   "pct_pixels_alterados_mais_de_24": r_dentro, "dif_media_0_255": r_dentro_dif, "ok": ok_dentro}

    # ---- passe 2: identidade ----
    ident: dict = {"executado": False}
    ok_ident: bool | None = None
    if a.modelo != "nenhum" and a.avatar:
        elegiveis = [q["quadro"] for q in por_quadro if q["area_alvo_px"] >= 0.002 * W * H]
        if not elegiveis:
            ident = {"executado": False, "motivo": "nenhum quadro com alvo grande o bastante na mascara"}
        else:
            idx = sorted({elegiveis[int(round(k))] for k in np.linspace(0, len(elegiveis) - 1, min(a.amostras, len(elegiveis)))})
            alvo_set = set(idx)
            crops_t, crops_o = [], []
            lo, lt = LeitorVideo(ffmpeg, p_orig, io), LeitorVideo(ffmpeg, p_troc, it)
            j = 0
            try:
                while j <= max(idx):
                    qo, qt = lo.proximo(), lt.proximo()
                    if qo is None or qt is None:
                        break
                    if j in alvo_set:
                        if redim:
                            qt = cv2.resize(qt, (W, H), interpolation=cv2.INTER_AREA if it["largura"] * it["altura"] > W * H else cv2.INTER_CUBIC)
                        emp = masks[0] if n_masks == 1 else masks[j]
                        al = desempacotar(emp, mh, mw)
                        if (mh, mw) != (H, W):
                            al = cv2.resize(al.astype(np.uint8), (W, H), interpolation=cv2.INTER_NEAREST) > 0
                        ct = recorte_alvo(qt, al, 0.08, not a.recorte_retangular)
                        co = recorte_alvo(qo, al, 0.08, not a.recorte_retangular)
                        if ct is not None and co is not None:
                            crops_t.append(ct)
                            crops_o.append(co)
                    j += 1
            finally:
                lo.fechar()
                lt.fechar()
            avatares = []
            for pth in map(Path, a.avatar):
                im = ler_imagem(pth)
                avatares.append(im if a.avatar_fundo_original else fundo_neutro_avatar(im))
            if a.pasta_debug:
                Path(a.pasta_debug).mkdir(parents=True, exist_ok=True)
                for k, (ct, co) in enumerate(zip(crops_t, crops_o)):
                    cv2.imwrite(str(Path(a.pasta_debug) / f"recorte_{k:02d}_trocado.png"), ct)
                    cv2.imwrite(str(Path(a.pasta_debug) / f"recorte_{k:02d}_original.png"), co)
                for k, av in enumerate(avatares):
                    cv2.imwrite(str(Path(a.pasta_debug) / f"avatar_{k}_usado.png"), av)
            ident = {"executado": True, "quadros_amostrados": idx, "n_recortes": len(crops_t),
                     "recorte": "retangular" if a.recorte_retangular else "alvo sobre cinza neutro",
                     "aviso": "Mede semelhanca visual global (roupa, cores, silhueta), nao identidade de rosto.", "modelos": {}}
            tipos = {"dinov2": ["dinov2"], "clip": ["clip"], "ambos": ["dinov2", "clip"]}[a.modelo]
            oks = []
            for tipo in tipos:
                nome = a.pesos_dinov2 if tipo == "dinov2" else a.pesos_clip
                limiar = a.limiar_dino if tipo == "dinov2" else a.limiar_clip
                try:
                    emb = Embedder(tipo, nome, a.dispositivo, a.offline)
                    ea = emb.embutir(avatares)
                    et = emb.embutir(crops_t)
                    eo = emb.embutir(crops_o)
                except ImportError as e:
                    ident["modelos"][tipo] = {"pulado": f"falta {e.name} (instale torch e transformers)"}
                    continue
                except Exception as e:  # noqa: BLE001
                    ident["modelos"][tipo] = {"pulado": f"{e.__class__.__name__}: {str(e)[:200]}"}
                    continue
                sim_t = (et @ ea.T).max(axis=1)  # melhor avatar por recorte
                sim_o = (eo @ ea.T).max(axis=1)
                mt, mo = float(sim_t.mean()), float(sim_o.mean())
                ok = mt >= limiar and (mt - mo) >= a.margem_melhora
                oks.append(ok)
                ident["modelos"][tipo] = {"pesos": nome, "limiar": limiar, "margem_melhora": a.margem_melhora,
                                          "cosseno_trocado_x_avatar": {"media": mt, "min": float(sim_t.min()), "max": float(sim_t.max()),
                                                                       "por_recorte": [round(float(x), 4) for x in sim_t]},
                                          "cosseno_original_x_avatar_controle": {"media": mo, "por_recorte": [round(float(x), 4) for x in sim_o]},
                                          "melhora_sobre_original": mt - mo, "ok": ok}
            ok_ident = all(oks) if oks else None
            ident["ok"] = ok_ident
    elif a.modelo != "nenhum" and not a.avatar:
        ident = {"executado": False, "motivo": "sem --avatar"}

    # ---- audio ----
    aud: dict = {"original_tem_audio": io["tem_audio"], "trocado_tem_audio": it["tem_audio"]}
    ok_audio: bool | None
    if not io["tem_audio"]:
        ok_audio = None
        aud["resultado"] = "o original nao tem audio (checagem pulada)"
    elif not it["tem_audio"]:
        ok_audio = False
        aud["resultado"] = "o trocado nao tem audio"
    else:
        po, pt_ = pcm_nativo(ffmpeg, p_orig), pcm_nativo(ffmpeg, p_troc)
        ho, ht = hashlib.sha256(po).hexdigest(), hashlib.sha256(pt_).hexdigest()
        aud.update(pcm_sha256_original=ho, pcm_sha256_trocado=ht, pcm_bytes_original=len(po), pcm_bytes_trocado=len(pt_),
                   taxa_hz_original=io.get("taxa_hz"), taxa_hz_trocado=it.get("taxa_hz"),
                   canais_original=io.get("canais"), canais_trocado=it.get("canais"))
        da = len(po) / (2 * io["canais"] * io["taxa_hz"]) if io.get("taxa_hz") else None
        db = len(pt_) / (2 * it["canais"] * it["taxa_hz"]) if it.get("taxa_hz") else None
        aud["duracao_audio_original_s"], aud["duracao_audio_trocado_s"] = da, db
        ok_dur_audio = bool(da is not None and db is not None and abs(da - db) <= a.tol_duracao)
        aud["ok_duracao_audio"] = ok_dur_audio
        if ho == ht:
            aud.update(identico_byte_a_byte=True, correlacao=1.0, snr_db=None,
                       resultado="IGUAL: o PCM decodificado e identico (mesmo hash).")
            ok_audio = ok_dur_audio
        else:
            c = correlacao_audio(pcm_mono_16k(ffmpeg, p_orig), pcm_mono_16k(ffmpeg, p_troc))
            aud.update(identico_byte_a_byte=False, **c)
            ok_audio = bool(c["correlacao"] >= a.min_corr_audio and ok_dur_audio)
            aud["resultado"] = ((f"EQUIVALENTE: nao e identico byte a byte, mas a correlacao e {c['correlacao']:.5f}. "
                                 "Provavelmente o audio foi recodificado; copie o audio original com -c copy (compor_final.py faz isso).")
                                if ok_audio else f"DIFERENTE: correlacao {c['correlacao']:.5f} (minimo {a.min_corr_audio}).")
        aud["ok"] = ok_audio

    # ---- veredito ----
    itens = {
        "quadros_fps_duracao": "OK" if (ok_quadros and ok_fps and ok_dur) else "FALHOU",
        "fora_da_mascara_nao_mudou": "OK" if ok_fora else "FALHOU",
        "alvo_mudou": "OK" if ok_dentro else "FALHOU",
        "parece_com_o_avatar": "PULADO" if ok_ident is None else ("OK" if ok_ident else "FALHOU"),
        "audio": "PULADO" if ok_audio is None else ("OK" if ok_audio else "FALHOU"),
    }
    geral = all(x != "FALHOU" for x in itens.values())
    pulados = [k for k, x in itens.items() if x == "PULADO"]
    rel = {"versao": 1, "ferramenta": "conferir_troca.py", "gerado_em": datetime.now().isoformat(timespec="seconds"),
           "plataforma": f"{platform.system()} {platform.release()}, python {platform.python_version()}, opencv {cv2.__version__}, numpy {np.__version__}",
           "entradas": {"original": {"arquivo": p_orig.name, "sha256": sha256_arquivo(p_orig)},
                        "trocado": {"arquivo": p_troc.name, "sha256": sha256_arquivo(p_troc)},
                        "mascara": {"caminho": str(p_mask), "tipo": tipo_mask, "quadros": n_masks},
                        "avatares": [{"arquivo": Path(x).name, "sha256": sha256_arquivo(Path(x))} for x in a.avatar]},
           "parametros": {k: v_ for k, v_ in vars(a).items()},
           "video": v, "fora_da_mascara": fora_info, "dentro_da_mascara": dentro_info, "identidade": ident, "audio": aud,
           "por_quadro": {"quadro": [q["quadro"] for q in por_quadro],
                          "area_alvo_px": [q["area_alvo_px"] for q in por_quadro],
                          "psnr_fora_db": [None if x is None else round(x, 3) for x in ps],
                          "ssim_fora": [None if x is None else round(x, 5) for x in ss],
                          "dif_media_fora": [None if q["dif_media_fora"] is None else round(q["dif_media_fora"], 4) for q in por_quadro],
                          "pct_dentro_alterado": [None if q["pct_dentro_alterado"] is None else round(q["pct_dentro_alterado"], 2) for q in por_quadro]},
           "veredito": {"ok": geral, "itens": itens, "pulados": pulados}, "tempo_conferencia_s": round(time.time() - t_ini, 1)}
    Path(a.saida).write_text(json.dumps(rel, indent=2, ensure_ascii=False), encoding="utf-8")

    if a.pasta_debug and quadro_pior is not None:
        qo, qt, ad = quadro_pior
        dif = cv2.absdiff(qo, qt)
        dif = np.clip(dif.astype(np.int32) * 8, 0, 255).astype(np.uint8)
        cont, _ = cv2.findContours(ad.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(dif, cont, -1, (0, 255, 0), 2)
        cv2.imwrite(str(Path(a.pasta_debug) / f"pior_quadro_{pior['i']:05d}_diferenca_x8.png"), dif)

    # ---- resumo em portugues ----
    def f(x, c=2):
        return "n/d" if x is None else f"{x:.{c}f}"

    print("\n================ RESUMO DA CONFERENCIA ================")
    print(f"Quadros: original {n_orig}, trocado {n_troc} | fps {io['fps']} / {it['fps']} | "
          f"duracao (quadros/fps) {f(dur_o)} s / {f(dur_t)} s  -> {itens['quadros_fps_duracao']}")
    if r_psnr:
        print(f"FORA da mascara (margem {a.dilatar}px): PSNR por quadro min {f(r_psnr['min'], 1)} dB, media {f(r_psnr['media'], 1)} dB "
              f"(100 = identico); SSIM medio {f(r_ssim['media'], 4)}; diferenca media {f(r_dif['media'], 3)} de 255; "
              f"pixels com diferenca > 16: {f(r_pct['media'], 3)}%")
        print(f"   criterio: PSNR min >= {a.min_psnr} dB e SSIM medio >= {a.min_ssim}  -> {itens['fora_da_mascara_nao_mudou']}"
              + (f"  (quadros abaixo do PSNR minimo: {quadros_ruins[:10]}{'...' if len(quadros_ruins) > 10 else ''})" if quadros_ruins else ""))
    print(f"DENTRO da mascara: {f(r_dentro['media'] if r_dentro else None, 1)}% dos pixels do alvo mudaram (minimo {a.min_alvo_alterado}%), "
          f"diferenca media {f(r_dentro_dif['media'] if r_dentro_dif else None, 1)} de 255 -> {itens['alvo_mudou']}")
    if ident.get("executado"):
        for tipo, d in ident["modelos"].items():
            if "pulado" in d:
                print(f"Avatar ({tipo}): PULADO - {d['pulado']}")
            else:
                print(f"Avatar ({tipo}): cosseno trocado x avatar {f(d['cosseno_trocado_x_avatar']['media'], 3)} (limiar {d['limiar']}); "
                      f"ator original x avatar {f(d['cosseno_original_x_avatar_controle']['media'], 3)}; melhora {f(d['melhora_sobre_original'], 3)} "
                      f"(minimo {d['margem_melhora']}) -> {'OK' if d['ok'] else 'FALHOU'}")
        print("   (mede semelhanca visual global, nao identidade de rosto)")
    else:
        print(f"Avatar: PULADO ({ident.get('motivo', 'modelo nenhum')})")
    print(f"Audio: {aud['resultado']} -> {itens['audio']}")
    texto_veredito = "HA FALHAS" if not geral else ("TUDO OK, MAS COM ITENS PULADOS (nao verificados)" if pulados else "TUDO OK")
    print(f"\nVEREDITO GERAL: {texto_veredito}   (relatorio: {a.saida}; {rel['tempo_conferencia_s']} s)")
    for k_, v_ in itens.items():
        print(f"  [{v_:<6}] {k_}")
    return 0 if geral else 1


if __name__ == "__main__":
    sys.exit(main())
