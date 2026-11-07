"""Prepara as entradas do teste de troca de personagem.

O que faz (tudo local, sem internet):
  1. corta um trecho do clipe (padrao: 3 s = 75 quadros a partir de 3,0 s) mantendo o audio;
  2. cria uma versao reduzida do trecho (padrao 480x848) para a primeira rodada, com o MESMO audio;
  3. recorta o corpo inteiro do avatar do painel da folha de 4 vistas (padrao: painel inferior direito) em PNG;
  4. grava um manifesto com hashes sha256 e confere se o numero de quadros ficou exato.

Uso (Windows, dentro da pasta do kit):
  python preparar_entradas.py --clipe "C:\\caminho\\clipe.mp4" --folha "C:\\caminho\\folha.webp" --saida entradas

Requisitos: Python 3.8+, ffmpeg no PATH (ou --ffmpeg), e Pillow para o avatar (python -m pip install pillow).
Por que o padrao comeca em 3,0 s: no clipe de teste o alvo (agasalho laranja) so aparece inteiro a partir do
quadro ~75; nos 3 s iniciais ele esta ausente ou quase todo fora do quadro. Use --inicio 0 para cortar do comeco.
Por que 848 e nao 854: o ComfyUI (WanAnimateToVideo) pede largura e altura multiplas de 16; 854 nao e. Use
--altura 854 se quiser exatamente 480x854.
Os arquivos de entrada sao tratados como dados: o script nunca executa nada que venha deles.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

X264 = ["-c:v", "libx264", "-preset", "slow", "-crf", "12", "-pix_fmt", "yuv420p", "-threads", "1"]
BITEXACT = ["-fflags", "+bitexact", "-flags:v", "+bitexact", "-flags:a", "+bitexact", "-map_metadata", "-1"]
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def achar_ffmpeg(arg: str | None) -> str | None:
    """Procura o ffmpeg: argumento, variavel FFMPEG, PATH, e por fim o pacote imageio-ffmpeg (se instalado)."""
    for cand in (arg, os.environ.get("FFMPEG")):
        if cand and shutil.which(cand):
            return shutil.which(cand)
    achado = shutil.which("ffmpeg")
    if achado:
        return achado
    try:
        import imageio_ffmpeg  # type: ignore

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:  # noqa: BLE001
        return None


def rodar(cmd: list[str], timeout: int = 900) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, errors="replace", timeout=timeout,
                          creationflags=CREATE_NO_WINDOW)


def sha256_arquivo(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def sondar(ffmpeg: str, p: Path) -> dict:
    """Le largura, altura, fps, duracao e audio a partir da saida de `ffmpeg -i` (nao precisa do ffprobe)."""
    r = rodar([ffmpeg, "-hide_banner", "-i", str(p)])
    txt = r.stderr
    info: dict = {"audio": "Audio:" in txt}
    m = re.search(r"Video:.*?, (\d{2,5})x(\d{2,5})[ ,\[]", txt)
    if not m:
        raise SystemExit(f"ERRO: nao consegui ler o video em {p}. Saida do ffmpeg:\n{txt[-600:]}")
    info["largura"], info["altura"] = int(m.group(1)), int(m.group(2))
    m = re.search(r"([\d.]+) fps", txt)
    info["fps"] = float(m.group(1)) if m else 25.0
    m = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", txt)
    info["duracao_s"] = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)) if m else None
    return info


def contar_quadros(ffmpeg: str, p: Path) -> int:
    """Conta os quadros decodificados do 1o video (confiavel, nao depende do cabecalho do arquivo)."""
    r = rodar([ffmpeg, "-hide_banner", "-nostats", "-progress", "pipe:1", "-i", str(p), "-map", "0:v:0", "-f", "null", "-"])
    achados = re.findall(r"^frame=\s*(\d+)", r.stdout, flags=re.M)
    if not achados:
        raise SystemExit(f"ERRO: nao consegui contar os quadros de {p}.")
    return int(achados[-1])


def versao_ffmpeg(ffmpeg: str) -> str:
    r = rodar([ffmpeg, "-version"])
    return (r.stdout or r.stderr).splitlines()[0] if (r.stdout or r.stderr) else "desconhecida"


def cortar(ffmpeg: str, clipe: Path, saida: Path, ini_q: int, fim_q: int, fps: float, com_audio: bool) -> None:
    t0, t1 = ini_q / fps, fim_q / fps
    cmd = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", str(clipe), "-map", "0:v:0"]
    if com_audio:
        cmd += ["-map", "0:a:0"]
    cmd += ["-vf", f"trim=start_frame={ini_q}:end_frame={fim_q},setpts=PTS-STARTPTS", "-r", f"{fps:g}"]
    if com_audio:
        cmd += ["-af", f"atrim=start={t0:.6f}:end={t1:.6f},asetpts=PTS-STARTPTS"]
    cmd += X264
    if com_audio:
        cmd += ["-c:a", "aac", "-b:a", "192k"]
    cmd += BITEXACT + ["-movflags", "+faststart", str(saida)]
    r = rodar(cmd)
    if r.returncode != 0 or not saida.exists():
        raise SystemExit(f"ERRO ao cortar o clipe:\n{r.stderr[-800:]}")


def reduzir(ffmpeg: str, corte: Path, saida: Path, w: int, h: int, fps: float, com_audio: bool) -> None:
    cmd = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", str(corte), "-map", "0:v:0"]
    if com_audio:
        cmd += ["-map", "0:a:0"]
    cmd += ["-vf", f"scale={w}:{h}:flags=lanczos,setsar=1", "-r", f"{fps:g}"] + X264
    if com_audio:
        cmd += ["-c:a", "copy"]  # mesmo audio, byte a byte, do corte
    cmd += BITEXACT + ["-movflags", "+faststart", str(saida)]
    r = rodar(cmd)
    if r.returncode != 0 or not saida.exists():
        raise SystemExit(f"ERRO ao criar a versao reduzida:\n{r.stderr[-800:]}")


def recortar_avatar(folha: Path, saida: Path, painel: str, grade: str, margem: int, limiar: int) -> dict:
    try:
        from PIL import Image, ImageFilter  # type: ignore
    except ImportError:
        raise SystemExit("ERRO: falta o Pillow. Instale com:  python -m pip install pillow")
    linhas, colunas = (int(x) for x in grade.lower().split("x"))
    pos = {"cima-esquerda": (0, 0), "cima-direita": (0, colunas - 1),
           "baixo-esquerda": (linhas - 1, 0), "baixo-direita": (linhas - 1, colunas - 1)}
    lin, col = pos[painel]
    im = Image.open(folha).convert("RGB")
    W, H = im.size
    caixa_painel = (col * W // colunas, lin * H // linhas, (col + 1) * W // colunas, (lin + 1) * H // linhas)
    pn = im.crop(caixa_painel)
    pw, ph = pn.size
    px = pn.load()
    # cor de fundo = mediana do anel externo do painel (o fundo da folha e um degrade cinza claro)
    anel = [px[x, y] for x in range(pw) for y in (0, 1, 2, ph - 3, ph - 2, ph - 1)] + \
           [px[x, y] for y in range(ph) for x in (0, 1, 2, pw - 3, pw - 2, pw - 1)]
    fundo = tuple(sorted(c[i] for c in anel)[len(anel) // 2] for i in range(3))
    suave = pn.filter(ImageFilter.MedianFilter(5))
    sp = suave.load()
    cols_ativas = [0] * pw
    lins_ativas = [0] * ph
    for y in range(ph):
        for x in range(pw):
            c = sp[x, y]
            if max(abs(c[0] - fundo[0]), abs(c[1] - fundo[1]), abs(c[2] - fundo[2])) > limiar:
                cols_ativas[x] += 1
                lins_ativas[y] += 1
    xs = [x for x, n in enumerate(cols_ativas) if n >= 3]
    ys = [y for y, n in enumerate(lins_ativas) if n >= 3]
    if not xs or not ys:
        raise SystemExit("ERRO: nao achei o personagem no painel. Tente --limiar-avatar menor ou outro --painel.")
    x0, x1 = max(0, min(xs) - margem), min(pw, max(xs) + 1 + margem)
    y0, y1 = max(0, min(ys) - margem), min(ph, max(ys) + 1 + margem)
    rec = pn.crop((x0, y0, x1, y1))
    rec.save(saida, format="PNG")
    return {"painel": painel, "caixa_painel_na_folha": list(caixa_painel), "fundo_rgb": list(fundo),
            "caixa_no_painel": [x0, y0, x1, y1], "tamanho_png": list(rec.size), "folha_tamanho": [W, H]}


def main() -> int:
    ap = argparse.ArgumentParser(description="Prepara as entradas do teste (corte, versao reduzida, avatar).")
    ap.add_argument("--clipe", required=True, help="video de entrada (mp4)")
    ap.add_argument("--folha", help="folha do avatar (webp/png/jpg); sem ela o avatar e pulado")
    ap.add_argument("--saida", default="entradas", help="pasta de saida (padrao: entradas)")
    ap.add_argument("--inicio", type=float, default=3.0, help="inicio do corte em segundos (padrao 3.0)")
    ap.add_argument("--quadros", type=int, default=75, help="quadros do corte (padrao 75 = 3 s a 25 fps; se o no do Animate reclamar, tente 73 ou 77)")
    ap.add_argument("--largura", type=int, default=480, help="largura da versao reduzida")
    ap.add_argument("--altura", type=int, default=848, help="altura da versao reduzida (padrao 848, multiplo de 16)")
    ap.add_argument("--painel", default="baixo-direita", choices=["cima-esquerda", "cima-direita", "baixo-esquerda", "baixo-direita"])
    ap.add_argument("--grade", default="2x2", help="grade da folha, linhasxcolunas (padrao 2x2)")
    ap.add_argument("--margem-avatar", type=int, default=12, help="folga em pixels ao redor do corpo (padrao 12)")
    ap.add_argument("--limiar-avatar", type=int, default=30, help="diferenca de cor para separar corpo e fundo (padrao 30)")
    ap.add_argument("--ffmpeg", help="caminho do ffmpeg, se nao estiver no PATH")
    a = ap.parse_args()

    clipe, saida = Path(a.clipe), Path(a.saida)
    if not clipe.is_file():
        print(f"ERRO: nao achei o clipe: {clipe}")
        return 2
    ffmpeg = achar_ffmpeg(a.ffmpeg)
    if not ffmpeg:
        print("ERRO: ffmpeg nao encontrado. Instale o ffmpeg e coloque no PATH, ou use --ffmpeg \"C:\\...\\ffmpeg.exe\".")
        return 2
    saida.mkdir(parents=True, exist_ok=True)

    info = sondar(ffmpeg, clipe)
    total = contar_quadros(ffmpeg, clipe)
    fps = info["fps"]
    ini_q = round(a.inicio * fps)
    fim_q = ini_q + a.quadros
    print(f"Clipe: {info['largura']}x{info['altura']}, {fps:g} fps, {total} quadros, audio: {'sim' if info['audio'] else 'nao'}")
    if fim_q > total:
        print(f"ERRO: o corte pede os quadros {ini_q} a {fim_q - 1}, mas o clipe so tem {total}. Diminua --inicio ou --quadros.")
        return 2

    nome = f"{a.quadros}q_{info['largura']}x{info['altura']}"
    corte = saida / f"clipe_corte_{nome}.mp4"
    reduzida = saida / f"clipe_corte_{a.quadros}q_{a.largura}x{a.altura}.mp4"
    print(f"Cortando quadros {ini_q} a {fim_q - 1} ({a.quadros / fps:.2f} s) -> {corte.name}")
    cortar(ffmpeg, clipe, corte, ini_q, fim_q, fps, info["audio"])
    print(f"Reduzindo para {a.largura}x{a.altura} -> {reduzida.name}")
    reduzir(ffmpeg, corte, reduzida, a.largura, a.altura, fps, info["audio"])

    avisos = []
    if a.largura % 16 or a.altura % 16:
        avisos.append(f"{a.largura}x{a.altura} nao e multiplo de 16; o ComfyUI pode reclamar ou ajustar.")
    resultado = {"versao": 1, "ffmpeg": versao_ffmpeg(ffmpeg), "parametros": vars(a), "avisos": avisos,
                 "entrada": {"clipe": {"arquivo": clipe.name, "sha256": sha256_arquivo(clipe), **info, "quadros": total}},
                 "saidas": {}}
    erros = []
    for rotulo, arq, w, h in (("corte", corte, info["largura"], info["altura"]), ("reduzida", reduzida, a.largura, a.altura)):
        n = contar_quadros(ffmpeg, arq)
        s = sondar(ffmpeg, arq)
        ok = n == a.quadros and (s["largura"], s["altura"]) == (w, h) and s["audio"] == info["audio"]
        resultado["saidas"][rotulo] = {"arquivo": arq.name, "sha256": sha256_arquivo(arq), "quadros": n,
                                       "largura": s["largura"], "altura": s["altura"], "fps": s["fps"],
                                       "duracao_s": s["duracao_s"], "audio": s["audio"], "conferido": ok}
        print(f"  {arq.name}: {n} quadros, {s['largura']}x{s['altura']}, {s['fps']:g} fps, duracao {s['duracao_s']} s, audio {'sim' if s['audio'] else 'nao'} -> {'OK' if ok else 'FALHOU'}")
        if not ok:
            erros.append(arq.name)

    if a.folha:
        folha = Path(a.folha)
        if not folha.is_file():
            print(f"AVISO: folha nao encontrada ({folha}); avatar pulado.")
        else:
            png = saida / "avatar_corpo_inteiro.png"
            av = recortar_avatar(folha, png, a.painel, a.grade, a.margem_avatar, a.limiar_avatar)
            av.update({"arquivo": png.name, "sha256": sha256_arquivo(png), "folha_sha256": sha256_arquivo(folha)})
            resultado["saidas"]["avatar"] = av
            print(f"Avatar: {png.name}, {av['tamanho_png'][0]}x{av['tamanho_png'][1]} px (recorte do painel {a.painel} da folha)")
            if av["tamanho_png"][1] < 600:
                print("  AVISO: o corpo inteiro do painel e pequeno (rosto com poucos pixels). O ComfyUI vai ampliar; "
                      "a fidelidade do rosto fica limitada por isso.")

    man = saida / "manifesto_entradas.json"
    man.write_text(json.dumps(resultado, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Manifesto: {man}")
    for av_ in avisos:
        print("AVISO:", av_)
    if erros:
        print("FALHOU a conferencia de:", ", ".join(erros))
        return 1
    print("\nPronto. Use no ComfyUI:")
    print(f"  1a rodada (leve):  {reduzida.name}  +  avatar_corpo_inteiro.png")
    print(f"  rodada em tamanho original:  {corte.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
