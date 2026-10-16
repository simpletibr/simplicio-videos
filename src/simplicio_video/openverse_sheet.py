"""Sinais objetivos da folha de revisão do Openverse (ffmpeg e ffprobe, sem rede e sem LLM).

O arquivo vem de um servidor não confiável. Por isso o ffmpeg nunca adivinha o formato: o demuxer é forçado a partir da
assinatura já conferida no download (`-f`), só o protocolo `file` é liberado (`-protocol_whitelist file`, sem http, tcp,
concat ou playlist) e o caminho é sempre o da biblioteca (nome derivado do sha256). Nada do arquivo é executado.
"""
from __future__ import annotations

import json
import math
import os
import re
import subprocess
from pathlib import Path

from .openverse import OpenverseError

DEMUXER = {"jpeg": "image2", "png": "image2", "webp": "image2", "gif": "gif", "mp3": "mp3", "ogg": "ogg", "wav": "wav",
           "flac": "flac", "m4a": "mov"}
STANDARD_RATIOS = {"1:1": 1.0, "4:3": 4 / 3, "3:2": 3 / 2, "16:9": 16 / 9, "21:9": 21 / 9, "2:1": 2.0, "5:4": 5 / 4, "3:4": 3 / 4,
                   "2:3": 2 / 3, "9:16": 9 / 16, "4:5": 4 / 5, "9:21": 9 / 21}
ANALYSIS_SIDE = 512      # a nitidez e o brilho saem de uma versão com no máximo 512 px no lado maior
SILENCE_DB = -50
SILENCE_MIN_S = 0.3
TOOL_TIMEOUT_S = 180


def _bin(name: str) -> str:
    d = os.environ.get("SIMPLICIO_FFMPEG_DIR")
    if d and (Path(d) / name).exists():
        return str(Path(d) / name)
    return name


def _run(cmd: list[str], binary: bool = False) -> subprocess.CompletedProcess:
    try:
        r = subprocess.run(cmd, capture_output=True, text=not binary, timeout=TOOL_TIMEOUT_S)
    except FileNotFoundError:
        raise OpenverseError(f"{Path(cmd[0]).name} não encontrado: instale o ffmpeg (ffmpeg e ffprobe no PATH) para gerar a folha") from None
    except subprocess.TimeoutExpired:
        raise OpenverseError(f"{Path(cmd[0]).name} passou de {TOOL_TIMEOUT_S} s: arquivo recusado pela folha") from None
    return r


def _input(path: Path, formato: str) -> list[str]:
    """Entrada travada: demuxer forçado, só o protocolo file, caminho absoluto da biblioteca."""
    if formato not in DEMUXER:
        raise OpenverseError(f"formato sem demuxer conhecido: {formato}")
    return ["-protocol_whitelist", "file", "-f", DEMUXER[formato], "-i", str(Path(path).resolve())]


def _ffmpeg(*args: str) -> list[str]:
    return [_bin("ffmpeg"), "-nostdin", "-hide_banner", *args]


def probe(path: Path, formato: str) -> dict:
    r = _run([_bin("ffprobe"), "-v", "error", "-protocol_whitelist", "file", "-f", DEMUXER[formato], "-show_entries",
              "stream=codec_type,codec_name,width,height,sample_rate,channels:stream_disposition=attached_pic:format=duration,bit_rate",
              "-of", "json", "-i", str(Path(path).resolve())])
    if r.returncode != 0:
        raise OpenverseError(f"o ffprobe não conseguiu ler o arquivo ({formato}): {(r.stderr or '').strip()[-300:]}")
    try:
        return json.loads(r.stdout or "{}")
    except ValueError:
        raise OpenverseError("o ffprobe devolveu uma resposta ilegível") from None


def ratio_text(w: int, h: int) -> str:
    if not w or not h:
        return "?"
    r = w / h
    nome, valor = min(STANDARD_RATIOS.items(), key=lambda kv: abs(kv[1] - r))
    return nome if abs(valor - r) / valor <= 0.015 else f"{r:.3f}:1"


def _gray_pixels(path: Path, formato: str, w: int, h: int) -> tuple[bytes, int, int]:
    s = min(1.0, ANALYSIS_SIDE / max(w, h))
    tw, th = max(1, round(w * s)), max(1, round(h * s))
    r = _run(_ffmpeg("-v", "error", *_input(path, formato), "-frames:v", "1", "-vf", f"scale={tw}:{th}:flags=area,format=gray",
                     "-f", "rawvideo", "-"), binary=True)
    if r.returncode != 0 or len(r.stdout) != tw * th:
        raise OpenverseError("o ffmpeg não conseguiu decodificar a imagem para medir nitidez e brilho: "
                             f"{(r.stderr or b'').decode('utf8', 'replace').strip()[-300:]}")
    return r.stdout, tw, th


def laplacian_variance(px: bytes, w: int, h: int) -> float:
    """Variância do Laplaciano (4*c - cima - baixo - esquerda - direita): quanto maior, mais nítida a imagem."""
    if w < 3 or h < 3:
        return 0.0
    n = s = s2 = 0
    rows = [px[i * w:(i + 1) * w] for i in range(h)]
    for y in range(1, h - 1):
        up, cur, dn = rows[y - 1], rows[y], rows[y + 1]
        for u, left, c, right, d in zip(up[1:-1], cur[:-2], cur[1:-1], cur[2:], dn[1:-1]):
            v = 4 * c - u - left - right - d
            s += v
            s2 += v * v
            n += 1
    mean = s / n
    return max(0.0, s2 / n - mean * mean)


def image_signals(path: Path, formato: str, rec: dict) -> dict:
    info = probe(path, formato)
    video = next((s for s in info.get("streams", []) if s.get("codec_type") == "video"), None)
    if not video or not video.get("width") or not video.get("height"):
        raise OpenverseError("o arquivo não tem imagem legível (o ffprobe não achou largura e altura)")
    w, h = int(video["width"]), int(video["height"])
    px, tw, th = _gray_pixels(path, formato, w, h)
    return {"largura": w, "altura": h, "proporcao": round(w / h, 6), "proporcao_texto": ratio_text(w, h),
            "tamanho_bytes": Path(path).stat().st_size, "formato": formato,
            "nitidez": round(float(laplacian_variance(px, tw, th)), 4), "brilho_medio": round(sum(px) / len(px), 3),
            "dimensoes_declaradas": f"{rec['largura']}x{rec['altura']}" if rec.get("largura") and rec.get("altura") else None,
            "mature": bool(rec.get("mature"))}


def thumbnail(path: Path, formato: str, out: Path) -> Path:
    r = _run(_ffmpeg("-y", "-v", "error", *_input(path, formato), "-frames:v", "1", "-vf", "scale='min(640,iw)':-2", str(out)))
    if r.returncode != 0 or not out.is_file():
        raise OpenverseError(f"o ffmpeg não gerou a miniatura: {(r.stderr or '').strip()[-300:]}")
    return out


def spectrogram(path: Path, formato: str, out: Path) -> Path:
    for legend in (1, 0):  # a legenda precisa de freetype no ffmpeg; sem ela o espectrograma sai sem eixos
        r = _run(_ffmpeg("-y", "-v", "error", *_input(path, formato), "-lavfi", f"showspectrumpic=s=1024x512:legend={legend}",
                         "-frames:v", "1", str(out)))
        if r.returncode == 0 and out.is_file():
            return out
    raise OpenverseError(f"o ffmpeg não gerou o espectrograma: {(r.stderr or '').strip()[-300:]}")


def _num(text: str | None) -> float | None:
    if text is None or text.strip().lower() in ("-inf", "inf", "nan"):
        return None
    try:
        v = float(text)
    except ValueError:
        return None
    return v if math.isfinite(v) else None


def _grep(pattern: str, text: str) -> float | None:
    m = re.search(pattern, text)
    return _num(m.group(1)) if m else None


def audio_signals(path: Path, formato: str, rec: dict) -> dict:
    info = probe(path, formato)
    streams = info.get("streams", [])
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    if audio is None:
        raise OpenverseError("o arquivo não tem trilha de áudio legível")
    video = [s for s in streams if s.get("codec_type") == "video" and not (s.get("disposition") or {}).get("attached_pic")]
    duracao = _num((info.get("format") or {}).get("duration"))
    if not duracao or duracao <= 0:
        raise OpenverseError("não consegui medir a duração do áudio")
    r = _run(_ffmpeg("-nostats", "-v", "info", *_input(path, formato), "-vn", "-af",
                     f"ebur128=peak=true,silencedetect=noise={SILENCE_DB}dB:d={SILENCE_MIN_S},astats=metadata=0", "-f", "null", "-"))
    if r.returncode != 0:
        raise OpenverseError(f"o ffmpeg não conseguiu analisar o áudio: {(r.stderr or '').strip()[-300:]}")
    log = r.stderr or ""
    lufs = re.findall(r"Integrated loudness:\s*\n\s*I:\s*(\S+)\s*LUFS", log)
    lra = re.findall(r"Loudness range:\s*\n\s*LRA:\s*(\S+)\s*LU", log)
    tp = re.findall(r"True peak:\s*\n\s*Peak:\s*(\S+)\s*dBFS", log)
    starts = [float(x) for x in re.findall(r"silence_start:\s*(-?[\d.]+)", log)]
    spans = [float(x) for x in re.findall(r"silence_duration:\s*([\d.]+)", log)]
    silencio = sum(spans) + (max(0.0, duracao - starts[-1]) if len(starts) > len(spans) else 0.0)
    overall = log.rsplit("Overall", 1)[-1]
    pico = _grep(r"Peak level dB:\s*(\S+)", overall)
    plano = _grep(r"Flat factor:\s*(\S+)", overall) or 0.0
    contagem = int(_grep(r"Peak count:\s*(\S+)", overall) or 0)
    return {"duracao_s": round(duracao, 3), "taxa_amostragem_hz": int(audio["sample_rate"]) if audio.get("sample_rate") else None,
            "canais": audio.get("channels"), "formato": formato, "codec": audio.get("codec_name"),
            "tamanho_bytes": Path(path).stat().st_size, "loudness_lufs": _num(lufs[-1]) if lufs else None,
            "faixa_de_loudness_lu": _num(lra[-1]) if lra else None, "pico_verdadeiro_dbfs": _num(tp[-1]) if tp else None,
            "fracao_silencio": round(min(1.0, silencio / duracao), 4),
            "clipping": {"pico_dbfs": pico, "amostras_no_pico": contagem, "fator_plano": plano,
                         "suspeita": bool(pico is not None and pico >= -0.1 and (plano > 0 or contagem >= 3))},
            "tem_video": bool(video), "duracao_declarada_s": rec.get("duracao_s"), "mature": bool(rec.get("mature"))}


def checklist(rec: dict, sinais: dict) -> list[str]:
    """O que o motor não consegue saber e o revisor precisa conferir, mais os alertas dos sinais."""
    out: list[str] = []
    if rec["tipo"] == "imagem":
        out += ["O assunto do pedido aparece de verdade na imagem? (veja a miniatura e, se preciso, o arquivo inteiro)",
                "Há texto, logotipo, marca registrada, rosto reconhecível ou marca d'água que não pode aparecer no vídeo?",
                "A proporção e a resolução servem ao quadro do vídeo sem esticar nem cortar o que importa?"]
        if sinais["dimensoes_declaradas"] and sinais["dimensoes_declaradas"] != f"{sinais['largura']}x{sinais['altura']}":
            out.append(f"As dimensões do arquivo ({sinais['largura']}x{sinais['altura']}) diferem das declaradas pelo Openverse "
                       f"({sinais['dimensoes_declaradas']}): o arquivo baixado pode não ser o mesmo da página de origem.")
        if sinais["largura"] < 1080 and sinais["altura"] < 1080:
            out.append(f"Resolução baixa ({sinais['largura']}x{sinais['altura']}): ampliar para o quadro do vídeo pode borrar.")
        if sinais["nitidez"] < 20:
            out.append(f"Nitidez baixa (variância do Laplaciano {sinais['nitidez']}): confira se a imagem está desfocada ou lisa demais.")
        if sinais["brilho_medio"] < 25 or sinais["brilho_medio"] > 230:
            out.append(f"Brilho médio extremo ({sinais['brilho_medio']} de 255): confira se a imagem está escura ou estourada demais.")
    else:
        out += ["O som corresponde ao pedido? (ouça o arquivo e veja o espectrograma)",
                "Há voz, música reconhecível ou marca sonora de terceiros que não pode aparecer no vídeo?",
                "A duração e o ritmo cobrem a cena sem precisar de loop ou corte que se note?"]
        decl = sinais.get("duracao_declarada_s")
        if decl and abs(decl - sinais["duracao_s"]) > max(1.0, 0.1 * decl):
            out.append(f"A duração do arquivo ({sinais['duracao_s']} s) é diferente da declarada pelo Openverse ({decl} s): "
                       "o arquivo baixado pode ser uma prévia ou outro trecho.")
        if sinais["fracao_silencio"] > 0.3:
            out.append(f"{round(sinais['fracao_silencio'] * 100)}% do áudio é silêncio: confira se o trecho útil cobre a cena.")
        if sinais["clipping"]["suspeita"]:
            out.append("Suspeita de clipping (pico em 0 dBFS com amostras achatadas): ouça com atenção à distorção.")
        if sinais["tem_video"]:
            out.append("O arquivo traz trilha de vídeo além do áudio: confira o conteúdo antes de usar.")
        out.append("O master do vídeo é -14 LUFS: confira se o nível deste áudio cabe na mixagem.")
    if sinais.get("mature"):
        out.append("O Openverse marcou o item como mature (sensível): não deveria ter chegado até aqui.")
    out.append(f"A licença e o autor registrados conferem com a origem? ({rec.get('origem_url')}) A licença vem das fontes; isto não é parecer jurídico.")
    return out
