"""`simplicio-video media`: audio-visual operations on any MP4, deterministic and local (ffmpeg and ffprobe only).

Each subcommand builds one ffmpeg command from its arguments and runs it; no model runs here. The translation, the cue
timing and the voice are inputs (JSON files written by the agent or by `voicestudio`); this module only places them on the
picture and in the sound. The one exception is `fetch`, which downloads a public video with the pinned yt-dlp (download.py).
"""

from __future__ import annotations

import json
import math
import re
import shutil
import subprocess
from pathlib import Path

from . import download, shorts

CUES_SCHEMA = "simplicio.media-cues/v1"


class MediaError(Exception):
    pass


HELP = """media (audio-visual on any MP4: ffmpeg/ffprobe, deterministic; fetch uses the pinned yt-dlp)

  fetch URL -o OUT.mp4 --autorizo [--max-mb 500] [--timeout 600]
                                                   download one public video page to a new MP4 and write
                                                   OUT.fetch.json (source, sha256, yt-dlp version, time); needs --autorizo
  probe FONTE [-o info.json]                       metadata: duration, size, fps, audio
  audio FONTE -o OUT.wav [--rate 16000]            mono PCM track (for transcription or a voice reference)
  sheet FONTE -o SHEET.jpg [--every 4] [--cols 8]  contact sheet of frames, to review on-screen text
  subs CUES.json -o OUT.srt|OUT.ass [--style band|bottom] [--wrap N]
                                                   subtitle file from timed cues (SRT or styled ASS)
  burn FONTE SUBS -o OUT [--crf 20] [--preset medium]
                                                   burn an SRT or ASS file into the picture (needs libass)
  mask FONTE --box x,y,w,h [--from S --to E] -o OUT
                                                   erase on-screen text inside a box (delogo), optional time window
  replace-audio FONTE AUDIO -o OUT [--keep-length]
                                                   keep the picture, swap the sound track
  voice-track CUES.json -o OUT.wav --duration SEC [--max-stretch 1.25]
                                                   place one voice clip per cue at its start time; speeds up
                                                   a clip only up to --max-stretch, and reports the rest

Cues file: {"schema": "simplicio.media-cues/v1", "cues": [{"start": 0.0, "end": 2.5, "text": "...", "audio": "clip.wav"}]}
The "audio" key is used only by voice-track. Times are seconds.

Examples:
  simplicio-video media fetch https://www.instagram.com/veramundopet/reel/DfDdh8ugFWN/ -o reel.mp4 --autorizo
  simplicio-video media probe reel.mp4
  simplicio-video media mask reel.mp4 --box 150,622,430,104 -o clean.mp4
  simplicio-video media subs cues.json -o subs.ass --style band
  simplicio-video media burn clean.mp4 subs.ass -o final.mp4
  simplicio-video media voice-track cues.json -o voice.wav --duration 58.2
  simplicio-video media replace-audio clean.mp4 voice.wav -o dubbed.mp4
"""

SUBCOMMANDS = ("fetch", "probe", "audio", "sheet", "subs", "burn", "mask", "replace-audio", "voice-track")

ASS_STYLES = {
    # centred on the picture, where short-form captions usually sit (matches the reel used in the first test)
    "band": {"alignment": 5, "margin_v": 0, "wrap": 22, "size": 44},
    # classic bottom captions
    "bottom": {"alignment": 2, "margin_v": 90, "wrap": 42, "size": 36},
}


def _need(exe: str) -> str:
    found = shutil.which(exe)
    if not found:
        raise MediaError(f"{exe} não encontrado no PATH (media usa ffmpeg e ffprobe)")
    return found


def _run(cmd: list[str]) -> None:
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise MediaError((r.stderr or r.stdout).strip().splitlines()[-1] if (r.stderr or r.stdout).strip() else "ffmpeg falhou")


def _ff_path(path: Path) -> str:
    """Path as an ffmpeg filter argument: escapes what the filtergraph parser reads."""
    return str(path).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'").replace(",", "\\,").replace("[", "\\[").replace("]", "\\]")


def _stamp_srt(sec: float) -> str:
    ms = int(round(max(0.0, sec) * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return "%02d:%02d:%02d,%03d" % (h, m, s, ms)


def _stamp_ass(sec: float) -> str:
    cs = int(round(max(0.0, sec) * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return "%d:%02d:%02d.%02d" % (h, m, s, cs)


def read_cues(path: Path) -> list[dict]:
    """Validated cues, sorted by start. Every cue needs start < end; text is required for subs, audio for voice-track."""
    try:
        doc = json.loads(path.read_text(encoding="utf8"))
    except (OSError, ValueError) as e:
        raise MediaError(f"cues ilegíveis: {path}: {e}") from None
    if not isinstance(doc, dict) or doc.get("schema") != CUES_SCHEMA or not isinstance(doc.get("cues"), list):
        raise MediaError(f"cues com schema desconhecido: {path} (esperado {CUES_SCHEMA} com a lista 'cues')")
    cues = []
    for i, c in enumerate(doc["cues"], 1):
        if not isinstance(c, dict):
            raise MediaError(f"cue {i}: precisa ser um objeto")
        try:
            start, end = float(c["start"]), float(c["end"])
        except (KeyError, TypeError, ValueError):
            raise MediaError(f"cue {i}: start e end precisam ser números") from None
        if start < 0 or end <= start:
            raise MediaError(f"cue {i}: start/end inválidos ({start} -> {end})")
        text = c.get("text", "")
        if not isinstance(text, str):
            raise MediaError(f"cue {i}: text precisa ser texto")
        cues.append({"start": start, "end": end, "text": " ".join(text.split()), "audio": c.get("audio")})
    cues.sort(key=lambda c: c["start"])
    return cues


def _wrap(text: str, width: int) -> list[str]:
    linhas: list[str] = []
    atual = ""
    for palavra in text.split():
        candidata = (atual + " " + palavra).strip()
        if atual and len(candidata) > width:
            linhas.append(atual)
            atual = palavra
        else:
            atual = candidata
    if atual:
        linhas.append(atual)
    return linhas or [""]


def write_subs(cues: list[dict], dest: Path, style: str = "band", wrap: int | None = None) -> Path:
    if style not in ASS_STYLES:
        raise MediaError(f"--style desconhecido: {style} (band|bottom)")
    cfg = ASS_STYLES[style]
    width = wrap or cfg["wrap"]
    if width < 8:
        raise MediaError("--wrap precisa ser >= 8")
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.suffix.lower() == ".srt":
        linhas: list[str] = []
        for i, c in enumerate(cues, 1):
            linhas += [str(i), f"{_stamp_srt(c['start'])} --> {_stamp_srt(c['end'])}", "\n".join(_wrap(c["text"], width)), ""]
        dest.write_text("\n".join(linhas), encoding="utf8")
        return dest
    if dest.suffix.lower() != ".ass":
        raise MediaError("subs: a saída precisa ser .srt ou .ass")
    linhas = [
        "[Script Info]", "ScriptType: v4.00+", "PlayResX: 720", "PlayResY: 1280", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, "
        "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, "
        "MarginV, Encoding",
        f"Style: Media,Arial Black,{cfg['size']},&H00FFFFFF,&H000000FF,&H00000000,&H00000000,1,0,0,0,100,100,0,0,1,4,0,"
        f"{cfg['alignment']},40,40,{cfg['margin_v']},1",
        "", "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    for c in cues:
        texto = r"\N".join(_wrap(c["text"], width))
        linhas.append(f"Dialogue: 0,{_stamp_ass(c['start'])},{_stamp_ass(c['end'])},Media,,40,40,0,,{texto}")
    dest.write_text("\n".join(linhas) + "\n", encoding="utf8")
    return dest


def parse_box(text: str) -> tuple[int, int, int, int]:
    partes = text.split(",")
    if len(partes) != 4:
        raise MediaError("--box precisa ser x,y,w,h em pixels (ex.: 150,622,430,104)")
    try:
        x, y, w, h = (int(p) for p in partes)
    except ValueError:
        raise MediaError("--box: use inteiros") from None
    if x < 0 or y < 0 or w < 2 or h < 2:
        raise MediaError("--box: x e y >= 0, w e h >= 2")
    return x, y, w, h


def mask_filter(box: tuple[int, int, int, int], start: float | None = None, end: float | None = None) -> str:
    x, y, w, h = box
    base = f"delogo=x={x}:y={y}:w={w}:h={h}:show=0"
    if start is None and end is None:
        return base
    s = 0.0 if start is None else start
    e = 1e9 if end is None else end
    return f"{base}:enable='between(t,{s:g},{e:g})'"


def atempo_chain(factor: float) -> list[str]:
    """ffmpeg atempo accepts 0.5..2.0 per stage; a larger factor is split into stages."""
    if factor <= 0:
        raise MediaError("fator de velocidade precisa ser > 0")
    stages: list[str] = []
    f = factor
    while f > 2.0:
        stages.append("atempo=2.0")
        f /= 2.0
    while f < 0.5:
        stages.append("atempo=0.5")
        f /= 0.5
    stages.append(f"atempo={f:.6f}")
    return stages


def voice_plan(cues: list[dict], durations: dict[int, float], max_stretch: float) -> list[dict]:
    """For each cue with a clip: how much to speed it up so it fits its window, and what does not fit even then."""
    plano = []
    for i, c in enumerate(cues):
        if not c.get("audio"):
            continue
        dur = durations[i]
        janela = c["end"] - c["start"]
        fator = max(1.0, dur / janela) if janela > 0 else 1.0
        fator = min(fator, max_stretch)
        restante = max(0.0, dur / fator - janela)
        plano.append({"index": i, "start": c["start"], "clip": c["audio"], "clip_seconds": round(dur, 3),
                      "window_seconds": round(janela, 3), "speed": round(fator, 4),
                      "overflow_seconds": round(restante, 3)})
    return plano


def voice_filter(plano: list[dict], duration: float) -> str:
    partes = []
    labels = []
    for n, item in enumerate(plano):
        lab = f"v{n}"
        cadeia = [f"[{n}:a]aresample=24000"]
        if item["speed"] > 1.0001:
            cadeia += atempo_chain(item["speed"])
        ms = int(round(item["start"] * 1000))
        cadeia.append(f"adelay={ms}|{ms}")
        partes.append(",".join(cadeia) + f"[{lab}]")
        labels.append(f"[{lab}]")
    if not labels:
        raise MediaError("voice-track: nenhum cue tem 'audio'")
    mix = "".join(labels) + f"amix=inputs={len(labels)}:normalize=0:duration=longest,atrim=0:{duration:g},apad=whole_dur={duration:g}"
    return ";".join(partes) + ";" + mix + "[out]"


def _clip_seconds(path: Path) -> float:
    ffprobe = _need("ffprobe")
    r = subprocess.run([ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)],
                       capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        raise MediaError(f"não consegui ler a duração de {path}") from None


def _has_filter(name: str) -> bool:
    r = subprocess.run([_need("ffmpeg"), "-hide_banner", "-filters"], capture_output=True, text=True)
    return any(re.match(r"\s*\S+\s+%s\s" % re.escape(name), linha) for linha in r.stdout.splitlines())


def _parse(args: list[str]) -> tuple[list[str], dict[str, str]]:
    pos: list[str] = []
    vals: dict[str, str] = {}
    i = 0
    flags_sem_valor = {"--keep-length", "--autorizo"}
    while i < len(args):
        a = args[i]
        if a in flags_sem_valor:
            vals[a] = "1"
            i += 1
        elif a.startswith("-") and len(a) > 1:
            if i + 1 >= len(args):
                raise MediaError(f"{a}: falta o valor")
            vals[a] = args[i + 1]
            i += 2
        else:
            pos.append(a)
            i += 1
    return pos, vals


def _float(vals: dict[str, str], key: str, default: float | None) -> float | None:
    if key not in vals:
        return default
    try:
        return float(vals[key])
    except ValueError:
        raise MediaError(f"{key}: use um número") from None


def _int(vals: dict[str, str], key: str, default: int) -> int:
    if key not in vals:
        return default
    try:
        return int(vals[key])
    except ValueError:
        raise MediaError(f"{key}: use um inteiro") from None


def _source(pos: list[str], cmd: str) -> Path:
    if not pos:
        raise MediaError(f"{cmd}: informe o arquivo de entrada")
    src = Path(pos[0]).expanduser()
    if not src.exists():
        raise MediaError(f"arquivo não existe: {src}")
    return src


def _out(vals: dict[str, str], cmd: str) -> Path:
    if "-o" not in vals:
        raise MediaError(f"{cmd}: informe -o SAIDA")
    dest = Path(vals["-o"]).expanduser()
    dest.parent.mkdir(parents=True, exist_ok=True)
    return dest


def cmd_fetch(pos, vals) -> dict:
    if not pos:
        raise MediaError("fetch: informe a URL pública do vídeo")
    if "--autorizo" not in vals:
        raise MediaError("fetch: confirme que você pode usar este vídeo com --autorizo (o motor não verifica o direito de uso)")
    dest = _out(vals, "fetch")
    try:
        return download.fetch(pos[0], dest, autorizo=True, max_mb=_int(vals, "--max-mb", download.DEFAULT_MAX_MB),
                              timeout=_int(vals, "--timeout", download.DEFAULT_TIMEOUT_S))
    except download.DownloadError as e:
        raise MediaError(str(e)) from None


def cmd_probe(pos, vals) -> dict:
    src = _source(pos, "probe")
    try:
        info = shorts.probe(src)
    except shorts.ShortsError as e:
        raise MediaError(str(e)) from None
    if "-o" in vals:
        Path(vals["-o"]).expanduser().write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf8")
    return info


def cmd_audio(pos, vals) -> dict:
    src = _source(pos, "audio")
    dest = _out(vals, "audio")
    rate = _int(vals, "--rate", 16000)
    _run([_need("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y", "-i", str(src), "-vn", "-ac", "1", "-ar", str(rate),
          "-c:a", "pcm_s16le", str(dest)])
    return {"output": str(dest), "rate": rate}


def cmd_sheet(pos, vals) -> dict:
    src = _source(pos, "sheet")
    dest = _out(vals, "sheet")
    every = _float(vals, "--every", 4.0)
    cols = _int(vals, "--cols", 8)
    if every is None or every <= 0 or cols < 1:
        raise MediaError("sheet: --every > 0 e --cols >= 1")
    filtro = f"fps=1/{every:g},scale=240:-1,tile={cols}x{max(1, math.ceil(_clip_count(src, every) / cols))}"
    _run([_need("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y", "-i", str(src), "-vf", filtro, "-frames:v", "1", str(dest)])
    return {"output": str(dest), "every_seconds": every, "cols": cols}


def _clip_count(src: Path, every: float) -> int:
    info = shorts.probe(src)
    return max(1, int(math.ceil(info["duration"] / every)))


def cmd_subs(pos, vals) -> dict:
    if not pos:
        raise MediaError("subs: informe o arquivo de cues")
    cues = read_cues(Path(pos[0]).expanduser())
    dest = _out(vals, "subs")
    write_subs(cues, dest, vals.get("--style", "band"), _int(vals, "--wrap", 0) or None)
    return {"output": str(dest), "cues": len(cues)}


def cmd_burn(pos, vals) -> dict:
    if len(pos) < 2:
        raise MediaError("burn: informe FONTE.mp4 e o arquivo de legenda (.srt ou .ass)")
    src = _source(pos[:1], "burn")
    subs = Path(pos[1]).expanduser()
    if not subs.exists():
        raise MediaError(f"legenda não existe: {subs}")
    if subs.suffix.lower() not in (".srt", ".ass"):
        raise MediaError("burn: a legenda precisa ser .srt ou .ass")
    if not _has_filter("subtitles"):
        raise MediaError("burn: este ffmpeg não tem o filtro subtitles (falta libass); use o ffmpeg-full")
    dest = _out(vals, "burn")
    filtro = f"subtitles=filename='{_ff_path(subs)}'"
    _run([_need("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y", "-i", str(src), "-vf", filtro,
          "-c:v", "libx264", "-preset", vals.get("--preset", "medium"), "-crf", str(_int(vals, "--crf", 20)),
          "-pix_fmt", "yuv420p", "-c:a", "copy", "-movflags", "+faststart", str(dest)])
    return {"output": str(dest), "subtitles": str(subs)}


def cmd_mask(pos, vals) -> dict:
    src = _source(pos, "mask")
    if "--box" not in vals:
        raise MediaError("mask: informe --box x,y,w,h")
    box = parse_box(vals["--box"])
    inicio, fim = _float(vals, "--from", None), _float(vals, "--to", None)
    if inicio is not None and fim is not None and fim <= inicio:
        raise MediaError("mask: --to precisa ser maior que --from")
    dest = _out(vals, "mask")
    _run([_need("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y", "-i", str(src), "-vf", mask_filter(box, inicio, fim),
          "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p", "-c:a", "copy",
          "-movflags", "+faststart", str(dest)])
    return {"output": str(dest), "box": list(box), "from": inicio, "to": fim}


def cmd_replace_audio(pos, vals) -> dict:
    if len(pos) < 2:
        raise MediaError("replace-audio: informe FONTE.mp4 e o áudio")
    src = _source(pos[:1], "replace-audio")
    audio = Path(pos[1]).expanduser()
    if not audio.exists():
        raise MediaError(f"áudio não existe: {audio}")
    dest = _out(vals, "replace-audio")
    cmd = [_need("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y", "-i", str(src), "-i", str(audio),
           "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k"]
    if "--keep-length" not in vals:
        cmd.append("-shortest")
    _run(cmd + ["-movflags", "+faststart", str(dest)])
    return {"output": str(dest), "audio": str(audio)}


def cmd_voice_track(pos, vals) -> dict:
    if not pos:
        raise MediaError("voice-track: informe o arquivo de cues")
    cues = read_cues(Path(pos[0]).expanduser())
    dur = _float(vals, "--duration", None)
    if dur is None or dur <= 0:
        raise MediaError("voice-track: informe --duration SEGUNDOS (a duração do vídeo)")
    max_stretch = _float(vals, "--max-stretch", 1.25)
    if max_stretch is None or max_stretch < 1.0:
        raise MediaError("voice-track: --max-stretch precisa ser >= 1.0")
    clips = [c for c in cues if c.get("audio")]
    if not clips:
        raise MediaError("voice-track: nenhum cue tem 'audio'")
    base = Path(pos[0]).expanduser().parent
    durations: dict[int, float] = {}
    for i, c in enumerate(cues):
        if c.get("audio"):
            caminho = Path(c["audio"]).expanduser()
            if not caminho.is_absolute():
                caminho = base / caminho
            if not caminho.exists():
                raise MediaError(f"clipe não existe: {caminho}")
            c["audio"] = str(caminho)
            durations[i] = _clip_seconds(caminho)
    plano = voice_plan(cues, durations, max_stretch)
    dest = _out(vals, "voice-track")
    cmd = [_need("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y"]
    for item in plano:
        cmd += ["-i", item["clip"]]
    cmd += ["-filter_complex", voice_filter(plano, dur), "-map", "[out]", "-ac", "1", "-ar", "24000", "-c:a", "pcm_s16le", str(dest)]
    _run(cmd)
    estourados = [p for p in plano if p["overflow_seconds"] > 0.05]
    return {"output": str(dest), "clips": len(plano), "plan": plano,
            "overflow": [{"index": p["index"], "seconds": p["overflow_seconds"]} for p in estourados]}


DISPATCH = {
    "fetch": cmd_fetch, "probe": cmd_probe, "audio": cmd_audio, "sheet": cmd_sheet, "subs": cmd_subs, "burn": cmd_burn,
    "mask": cmd_mask, "replace-audio": cmd_replace_audio, "voice-track": cmd_voice_track,
}


def run_media(args: list[str]) -> int:
    first = args[0] if args else "help"
    if first in ("-h", "--help", "help"):
        print(HELP)
        return 0
    if first not in DISPATCH:
        raise MediaError(f"subcomando desconhecido: {first} ({'|'.join(SUBCOMMANDS)})")
    pos, vals = _parse(args[1:])
    resultado = DISPATCH[first](pos, vals)
    print(json.dumps(resultado, ensure_ascii=False, indent=2))
    return 0
