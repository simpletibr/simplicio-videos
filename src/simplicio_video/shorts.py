"""Shorts track: um vídeo longo vira N cortes verticais 9:16, determinístico (só ffmpeg).

O agente decide, o script corta. A decisão fica num plan.json versionado (janelas de corte),
igual ao EDL do video-use: nenhum modelo entra no caminho de render e nada aqui abre a rede.

Fluxo:
  inspect  -> ffprobe: duração, tamanho, fps, áudio, sha256 da fonte
  plan     -> transcrição (words.json, a do "edit transcribe") -> janelas pontuadas -> plan.json
  cut      -> plan.json -> MP4 vertical 1080x1920 + legenda queimada opcional + manifest.json
  run      -> plan + cut numa chamada

A transcrição é a mesma do "simplicio-video edit transcribe FONTE.mp4" (faster-whisper local);
sem ela não há seleção: o plano é a decisão, não um chute.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path

PLAN_SCHEMA = "simplicio.shorts-plan/v1"
MANIFEST_SCHEMA = "simplicio.shorts-manifest/v1"
TARGET_W, TARGET_H = 1080, 1920
GAP = 0.65  # silêncio que fecha uma fala
PAD = 0.12  # respiro antes e depois do corte
STYLE = ("Fontname=DejaVu Sans,Fontsize=18,PrimaryColour=&H00FFFFFF,OutlineColour=&H90000000,"
         "BorderStyle=3,Outline=1,Shadow=0,MarginV=140,Alignment=2")
# Ganchos que costumam puxar retenção em notícia/fofoca. A lista é do projeto, não do modelo:
# mudar aqui muda todo plano futuro do mesmo jeito, o que mantém o resultado reprodutível.
HOOKS = ("morre", "morreu", "morte", "urgente", "agora", "confirmado", "confirmada", "vídeo", "video",
         "presidente", "presidência", "polêmica", "polemica", "revela", "revelou", "denúncia", "denuncia",
         "acidente", "explosão", "explosao", "justiça", "justica", "eleição", "eleicao", "escândalo",
         "escandalo", "famosa", "famoso", "família", "familia", "dinheiro", "erro", "perigo", "proibido",
         "verdade", "nunca", "ninguém", "ninguem", "primeira vez", "exclusivo", "bomba", "chorou")


class ShortsError(Exception):
    pass


# ---------------------------------------------------------------- utilidades

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _need(exe: str) -> str:
    found = shutil.which(exe)
    if not found:
        raise ShortsError(f"{exe} não encontrado no PATH (o shorts usa só ffmpeg/ffprobe)")
    return found


def _fps(raw) -> float:
    if not raw or "/" not in str(raw):
        try:
            return round(float(raw), 3)
        except (TypeError, ValueError):
            return 0.0
    num, _, den = str(raw).partition("/")
    try:
        return round(float(num) / float(den or 1), 3)
    except ValueError:
        return 0.0


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def probe(path: Path) -> dict:
    """Metadados da fonte: nada é escrito, nada é decodificado."""
    if not path.exists():
        raise ShortsError(f"arquivo não existe: {path}")
    ffprobe = _need("ffprobe")
    r = subprocess.run(
        [ffprobe, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
        capture_output=True, text=True)
    if r.returncode != 0:
        raise ShortsError(r.stderr.strip() or f"ffprobe falhou em {path}")
    data = json.loads(r.stdout or "{}")
    streams = data.get("streams") or []
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    if video is None:
        raise ShortsError(f"sem trilha de vídeo: {path}")
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    duration = data.get("format", {}).get("duration") or video.get("duration") or 0
    try:
        duration_f = float(duration)
    except (TypeError, ValueError):
        duration_f = 0.0
    return {
        "path": str(path),
        "duration": round(duration_f, 3),
        "width": int(video.get("width") or 0),
        "height": int(video.get("height") or 0),
        "fps": _fps(video.get("avg_frame_rate") or video.get("r_frame_rate")),
        "has_audio": audio is not None,
        "size_bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }

# ---------------------------------------------------------------- transcrição

def load_words(path: Path) -> list[dict]:
    """words.json -> [{start, end, text}] ordenado. Aceita lista solta, {"words": ...} ou {"segments": ...}."""
    if not path.exists():
        raise ShortsError(f"transcrição não existe: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf8"))
    except ValueError as e:
        raise ShortsError(f"transcrição inválida (json): {e}") from e
    if isinstance(data, dict):
        raw = data.get("words") or data.get("segments") or []
    elif isinstance(data, list):
        raw = data
    else:
        raise ShortsError("transcrição: esperava lista ou objeto com words/segments")
    words: list[dict] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        text = _norm(str(item.get("text") or item.get("word") or ""))
        try:
            start = float(item.get("start"))
            end = float(item.get("end"))
        except (TypeError, ValueError):
            continue
        if not text or end <= start:
            continue
        words.append({"start": round(start, 3), "end": round(end, 3), "text": text})
    words.sort(key=lambda w: w["start"])
    if not words:
        raise ShortsError("transcrição sem palavras com start/end/text")
    return words


def utterances(words: list[dict]) -> list[dict]:
    """Junta palavras em falas: uma pausa maior que GAP abre outra."""
    out: list[dict] = []
    atual: list[dict] = []
    for w in words:
        if atual and w["start"] - atual[-1]["end"] > GAP:
            out.append({"start": atual[0]["start"], "end": atual[-1]["end"],
                        "text": _norm(" ".join(x["text"] for x in atual))})
            atual = []
        atual.append(w)
    if atual:
        out.append({"start": atual[0]["start"], "end": atual[-1]["end"],
                    "text": _norm(" ".join(x["text"] for x in atual))})
    return out


def group_captions(words: list[dict], max_chars: int = 42, max_gap: float = 0.8) -> list[dict]:
    """Legenda curta por cartão: corta por tamanho e por pausa."""
    out: list[dict] = []
    linha: list[dict] = []
    for w in words:
        texto = (" ".join(x["text"] for x in linha) + " " + w["text"]).strip()
        if linha and (len(texto) > max_chars or w["start"] - linha[-1]["end"] > max_gap):
            out.append({"start": linha[0]["start"], "end": linha[-1]["end"],
                        "text": _norm(" ".join(x["text"] for x in linha))})
            linha = []
        linha.append(w)
    if linha:
        out.append({"start": linha[0]["start"], "end": linha[-1]["end"],
                    "text": _norm(" ".join(x["text"] for x in linha))})
    return out


# ---------------------------------------------------------------- seleção

def score_window(text: str, duration: float, min_s: float, max_s: float) -> tuple[float, list[str]]:
    """Nota determinística de uma janela: mesmas palavras, mesma nota, sem modelo."""
    baixo = text.lower()
    motivos: list[str] = []
    nota = 1.0
    ganchos = sorted({h for h in HOOKS if h in baixo})
    if ganchos:
        nota += min(3.0, 1.2 * len(ganchos))
        motivos.append("ganchos: " + ", ".join(ganchos[:4]))
    if "?" in text:
        nota += 1.0
        motivos.append("pergunta")
    if "!" in text:
        nota += 0.8
        motivos.append("exclamação")
    digitos = len(re.findall(r"\d", text))
    if digitos:
        nota += min(1.2, 0.2 * digitos)
        motivos.append(f"{digitos} dígito(s)")
    palavras = len(text.split())
    densidade = palavras / duration if duration > 0 else 0.0
    if densidade >= 2.5:
        nota += 0.6
        motivos.append("fala densa")
    elif densidade <= 1.0:
        nota -= 0.3
        motivos.append("fala esparsa")
    alvo = (min_s + max_s) / 2
    nota += max(-0.5, 0.5 - abs(duration - alvo) / max(1.0, alvo))
    return round(nota, 3), motivos


def candidate_windows(words: list[dict], duration: float, min_s: float, max_s: float) -> list[dict]:
    """Uma janela por fala de abertura: a mais longa que ainda cabe em max_s."""
    utts = utterances(words)
    out: list[dict] = []
    for i in range(len(utts)):
        inicio = max(0.0, utts[i]["start"] - PAD)
        fim = None
        for j in range(i, len(utts)):
            e = utts[j]["end"]
            if e - inicio > max_s:
                break
            if e - inicio >= min_s:
                fim = e
        if fim is None:
            continue
        fim = min(duration, fim + PAD) if duration else fim + PAD
        if fim - inicio < min_s:
            continue
        texto = _norm(" ".join(u["text"] for u in utts[i:] if u["start"] < fim))
        nota, motivos = score_window(texto, fim - inicio, min_s, max_s)
        out.append({"start": round(inicio, 3), "end": round(fim, 3), "score": nota,
                    "reasons": motivos, "text": texto})
    return out


def select_clips(candidates: list[dict], wanted: int, overlap: float = 0.25) -> list[dict]:
    """Melhores notas que não se sobrepõem; empate desfeito pela ordem no vídeo."""
    escolhidos: list[dict] = []
    for cand in sorted(candidates, key=lambda c: (-c["score"], c["start"])):
        if len(escolhidos) >= wanted:
            break
        conflita = any(cand["start"] < e["end"] - overlap and e["start"] < cand["end"] - overlap
                       for e in escolhidos)
        if not conflita:
            escolhidos.append(dict(cand))
    escolhidos.sort(key=lambda c: c["start"])
    for i, c in enumerate(escolhidos, 1):
        c["id"] = "c%02d" % i
        c["duration"] = round(c["end"] - c["start"], 3)
    return escolhidos


def build_plan(source: dict, words: list[dict], clips: int, min_s: float, max_s: float) -> dict:
    candidates = candidate_windows(words, source["duration"], min_s, max_s)
    if not candidates:
        raise ShortsError("nenhuma janela entre %gs e %gs; a fonte tem fala suficiente?" % (min_s, max_s))
    chosen = select_clips(candidates, clips)
    if not chosen:
        raise ShortsError("nenhum corte sobrou depois de remover sobreposição")
    return {
        "schema": PLAN_SCHEMA,
        "source": source,
        "options": {"clips": clips, "min_seconds": min_s, "max_seconds": max_s,
                    "gap": GAP, "pad": PAD, "vertical": [TARGET_W, TARGET_H]},
        "clips": chosen,
    }

# ---------------------------------------------------------------- legenda e corte

def _ff_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")


def write_srt(captions: list[dict], dest: Path, offset: float) -> Path:
    def stamp(sec: float) -> str:
        ms = int(round(max(0.0, sec) * 1000))
        h, ms = divmod(ms, 3600000)
        m, ms = divmod(ms, 60000)
        s, ms = divmod(ms, 1000)
        return "%02d:%02d:%02d,%03d" % (h, m, s, ms)

    linhas: list[str] = []
    for i, cap in enumerate(captions, 1):
        linhas += [str(i), "%s --> %s" % (stamp(cap["start"] - offset), stamp(cap["end"] - offset)),
                   cap["text"], ""]
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text("\n".join(linhas), encoding="utf8")
    return dest


def build_filter(fit: str, srt: Path | None = None) -> str:
    w, h = TARGET_W, TARGET_H
    if fit == "crop":
        cadeia = "[0:v]scale=%d:%d:force_original_aspect_ratio=increase,crop=%d:%d" % (w, h, w, h)
    else:
        cadeia = ("[0:v]split=2[b0][f0];"
                  "[b0]scale=%d:%d:force_original_aspect_ratio=increase,crop=%d:%d,boxblur=32:2[bg];"
                  "[f0]scale=%d:%d:force_original_aspect_ratio=decrease[fg];"
                  "[bg][fg]overlay=(W-w)/2:(H-h)/2" % (w, h, w, h, w, h))
    if srt is not None:
        cadeia += ",subtitles='%s':force_style='%s'" % (_ff_escape(str(srt)), STYLE)
    return cadeia + ",format=yuv420p[v]"


def cut_command(src: Path, clip: dict, dest: Path, has_audio: bool, filt: str, crf: int, preset: str,
                fps: int) -> list[str]:
    cmd = [_need("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y",
           "-ss", "%.3f" % clip["start"], "-t", "%.3f" % clip["duration"], "-i", str(src),
           "-filter_complex", filt, "-map", "[v]"]
    cmd += ["-map", "0:a:0", "-c:a", "aac", "-b:a", "160k"] if has_audio else ["-an"]
    cmd += ["-c:v", "libx264", "-preset", preset, "-crf", str(crf), "-pix_fmt", "yuv420p",
            "-r", str(fps), "-movflags", "+faststart", str(dest)]
    return cmd


def cut_one(src: Path, clip: dict, out_dir: Path, source: dict, words: list[dict], opts: dict) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / ("%s.mp4" % clip["id"])
    srt = None
    if opts.get("subs") and words:
        dentro = [w for w in words if clip["start"] <= w["start"] < clip["end"]]
        caps = [c for c in group_captions(dentro) if c["end"] > clip["start"]]
        if caps:
            srt = write_srt(caps, out_dir / ("%s.srt" % clip["id"]), clip["start"])
    filt = build_filter(opts.get("fit", "blur"), srt)
    cmd = cut_command(src, clip, dest, source.get("has_audio", True), filt, int(opts.get("crf", 20)),
                      str(opts.get("preset", "medium")), int(opts.get("fps", 30)))
    if opts.get("dry_run"):
        return {"file": str(dest), "command": cmd, "dry_run": True}
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise ShortsError(r.stderr.strip() or ("ffmpeg falhou no corte %s" % clip["id"]))
    return {"file": str(dest), "dry_run": False}


def cut_plan(src: Path, plan: dict, out_dir: Path, opts: dict) -> dict:
    words = opts.get("words") or []
    metas: list[dict] = []
    for clip in plan["clips"]:
        one = cut_one(src, clip, out_dir, plan["source"], words, opts)
        meta = {"id": clip["id"], "file": one["file"], "start": clip["start"], "end": clip["end"],
                "duration": clip["duration"], "score": clip["score"], "reasons": clip.get("reasons", [])}
        if one.get("dry_run"):
            meta["command"] = " ".join(one["command"])
            metas.append(meta)
            continue
        info = probe(Path(one["file"]))
        meta.update({"bytes": info["size_bytes"], "sha256": info["sha256"], "width": info["width"],
                     "height": info["height"], "fps": info["fps"], "has_audio": info["has_audio"]})
        metas.append(meta)
    manifest = {
        "schema": MANIFEST_SCHEMA,
        "source": {k: plan["source"].get(k) for k in ("path", "sha256", "duration", "width", "height")},
        "options": {k: v for k, v in opts.items() if k not in ("words", "subs", "dry_run")},
        "clips": metas,
    }
    if not opts.get("dry_run"):
        (out_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2),
                                               encoding="utf8")
    return manifest

# ---------------------------------------------------------------- CLI

HELP = ("shorts (vídeo longo -> cortes verticais 9:16, determinístico, só ffmpeg)\n"
        "  shorts inspect FONTE.mp4 [-o out.json]                  # ffprobe: duração, fps, áudio, sha256\n"
        "  shorts plan FONTE.mp4 --transcript words.json [-o plan.json] [--clips 5] [--min 20] [--max 60]\n"
        "  shorts cut FONTE.mp4 plan.json [-o shorts/] [--subs] [--fit blur|crop] [--crf 20] [--dry-run]\n"
        "  shorts run FONTE.mp4 --transcript words.json [-o shorts/] [--clips 5] [--subs]\n"
        "\n"
        "A transcrição vem de: simplicio-video edit transcribe FONTE.mp4 -o words.json\n"
        "O plano é a decisão (janelas, nota, motivo) e fica versionado; o render só obedece.")


def _parse(args: list[str]) -> tuple[list[str], set[str], dict]:
    flags: set[str] = set()
    vals: dict = {}
    pos: list[str] = []
    i = 0
    while i < len(args):
        a = args[i]
        if a in ("--subs", "--dry-run"):
            flags.add(a)
            i += 1
        elif (a.startswith("--") or a == "-o") and i + 1 < len(args):
            vals[a] = args[i + 1]
            i += 2
        else:
            pos.append(a)
            i += 1
    return pos, flags, vals


def _num(vals: dict, key: str, default, cast=float):
    raw = vals.get(key)
    if raw is None:
        return default
    try:
        return cast(raw)
    except (TypeError, ValueError) as e:
        raise ShortsError("%s inválido: %r" % (key, raw)) from e


def run_shorts(args: list[str]) -> int:
    first = args[0] if args else "help"
    if first in ("-h", "--help", "help"):
        print(HELP)
        return 0
    if first not in ("inspect", "plan", "cut", "run"):
        raise ShortsError("subcomando desconhecido: %s (inspect|plan|cut|run)" % first)

    pos, flags, vals = _parse(args[1:])
    if not pos:
        raise ShortsError("%s: informe FONTE.mp4" % first)
    src = Path(pos[0]).expanduser()
    if not src.exists():
        raise ShortsError("fonte não existe: %s" % src)

    if first == "inspect":
        info = probe(src)
        texto = json.dumps(info, ensure_ascii=False, indent=2)
        print(texto)
        dest = vals.get("-o") or vals.get("--out")
        if dest:
            path = Path(dest).expanduser()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(texto, encoding="utf8")
        return 0

    clips_n = _num(vals, "--clips", 5, int)
    min_s = _num(vals, "--min", 20.0)
    max_s = _num(vals, "--max", 60.0)
    if clips_n < 1:
        raise ShortsError("--clips precisa ser >= 1")
    if min_s <= 0 or max_s <= min_s:
        raise ShortsError("use --min > 0 e --max > --min")

    source = probe(src)

    if first == "plan":
        transcript = vals.get("--transcript")
        if not transcript:
            raise ShortsError("plan: informe --transcript words.json (rode antes: edit transcribe)")
        tpath = Path(transcript).expanduser()
        plan = build_plan(source, load_words(tpath), clips_n, min_s, max_s)
        plan["transcript"] = str(tpath)
        dest = Path(vals.get("-o") or vals.get("--out") or "shorts/plan.json").expanduser()
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf8")
        print(json.dumps({"plan": str(dest), "clips": len(plan["clips"]),
                          "scores": [c["score"] for c in plan["clips"]]}, ensure_ascii=False, indent=2))
        return 0

    if first == "cut":
        if len(pos) < 2:
            raise ShortsError("cut: informe FONTE.mp4 PLAN.json")
        plan_path = Path(pos[1]).expanduser()
        if not plan_path.exists():
            raise ShortsError("plano não existe: %s" % plan_path)
        plan = json.loads(plan_path.read_text(encoding="utf8"))
        if plan.get("schema") != PLAN_SCHEMA:
            raise ShortsError("plano com schema diferente de %s" % PLAN_SCHEMA)
    else:  # run
        transcript = vals.get("--transcript")
        if not transcript:
            raise ShortsError("run: informe --transcript words.json")
        tpath = Path(transcript).expanduser()
        plan = build_plan(source, load_words(tpath), clips_n, min_s, max_s)
        plan["transcript"] = str(tpath)

    out_dir = Path(vals.get("-o") or vals.get("--out") or "shorts/").expanduser()
    opts = {
        "subs": "--subs" in flags,
        "fit": vals.get("--fit", "blur"),
        "crf": _num(vals, "--crf", 20, int),
        "preset": vals.get("--preset", "medium"),
        "fps": _num(vals, "--fps", 30, int),
        "dry_run": "--dry-run" in flags,
    }
    if opts["fit"] not in ("blur", "crop"):
        raise ShortsError("--fit aceita blur ou crop")
    if opts["subs"]:
        t = vals.get("--transcript") or plan.get("transcript")
        if not t:
            raise ShortsError("--subs precisa de --transcript (o plano não guarda as palavras)")
        opts["words"] = load_words(Path(t).expanduser())

    manifest = cut_plan(src, plan, out_dir, opts)
    if opts["dry_run"]:
        print(json.dumps({"dry_run": True, "out": str(out_dir),
                          "commands": [c.get("command") for c in manifest["clips"]]},
                         ensure_ascii=False, indent=2))
        return 0
    print(json.dumps({"out": str(out_dir), "manifest": str(out_dir / "manifest.json"),
                      "clips": [{"id": c["id"], "file": c["file"], "duration": c["duration"],
                                 "score": c["score"], "size": [c["width"], c["height"]]}
                                for c in manifest["clips"]]}, ensure_ascii=False, indent=2))
    return 0
