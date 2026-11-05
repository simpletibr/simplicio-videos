"""Edit track: browser-use/video-use over any MP4/MOV (HyperFrames, OpenMontage or OpenCut output).

Thin wrapper over the video-use files shipped in the package (data/tools/video-use): the agent writes edit/edl.json (versioned decision); everything else is ffmpeg.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

from . import paths
from .childio import run_child


class EditError(Exception):
    pass


def tool_dir() -> Path:
    """Our video-use files (setup.sh, transcribe_local.py, edl_transcript.py). They are package data, so they are found the same
    way in a checkout and in a wheel; SIMPLICIO_VIDEO_HOME does not move them."""
    return paths.DATA_DIR / "tools" / "video-use"


def helpers_dir() -> Path:
    setup = tool_dir() / "setup.sh"
    r = subprocess.run(["bash", str(setup), "--quiet"], stdin=subprocess.DEVNULL, capture_output=True, text=True)
    if r.returncode != 0:
        raise EditError(r.stderr.strip() or "video-use setup.sh falhou")
    return Path(r.stdout.strip().splitlines()[-1])


def _run(cmd: list[str]) -> int:
    return run_child(cmd)


def _tem_saida(rest: list[str]) -> bool:
    """True if the output option is there in any spelling the upstream argparse takes (see _output_values)."""
    return bool(_output_values(rest))


SUBCOMMANDS = ("setup", "transcribe", "transcribe-batch", "pack", "render", "verify", "grade")
NEEDS_OUT = ("transcribe", "render", "verify", "grade")
GRADE_READ_ONLY = ("--analyze", "--list-presets", "--print-preset")

GRADE_HELP = """edit grade FONTE.mp4 -o OUT.mp4 [--preset NOME | --filter 'FFMPEG'] | --analyze FONTE.mp4 | --list-presets
  correção de cor do video-use (grade.py, ffmpeg); a decisão de olhar da cena é sua, o comando só aplica
  modo auto (padrão): mede o clipe (luminância, contraste, saturação) e aplica uma correção sutil, sem mudar o tom
  --preset NOME      subtle | neutral_punch | warm_cinematic | none (warm_cinematic é opt-in, look retrô/cinema)
  --filter 'F'       cadeia ffmpeg crua (vence --preset), p.ex. 'eq=contrast=1.05:saturation=0.95'
  --analyze FONTE    só imprime o filtro que o modo auto aplicaria e as medidas; não grava nada
  --list-presets     lista os presets e seus filtros; --print-preset NOME imprime o filtro de um
  -o, --output OUT   obrigatório ao aplicar (a menos que use --analyze/--list-presets/--print-preset)
exemplos:
  simplicio-video edit grade --analyze entrevista.mp4
  simplicio-video edit grade entrevista.mp4 -o out/entrevista.graded.mp4
  simplicio-video edit grade entrevista.mp4 -o out/quente.mp4 --preset warm_cinematic
  simplicio-video edit grade entrevista.mp4 -o out/c.mp4 --filter 'eq=contrast=1.05:saturation=0.95'
  simplicio-video edit grade --list-presets
Teste o tom de pele num quadro (edit verify) antes de aplicar em tudo; grade no corte (por trecho), não depois de concatenar."""


def _is_out_flag(a: str) -> bool:
    """--output or any prefix of it from --o: argparse takes every unambiguous abbreviation (--o, --ou, --outp, --outpu...)."""
    flag = a.split("=", 1)[0]
    return a.startswith("--") and len(flag) >= 3 and "--output".startswith(flag)


def _output_values(rest: list[str]) -> list[str]:
    """ALL values given to the output option, in any spelling argparse accepts: -o X, -oX, -o=X, --output X, --out=X, --o X ...
    (the last one wins upstream, so a caller that checks them must check every one). '' marks a missing value. Stops at `--`."""
    vals: list[str] = []
    i = 0
    while i < len(rest):
        a = rest[i]
        if a == "--":
            break
        if a == "-o" or (_is_out_flag(a) and "=" not in a):
            vals.append(rest[i + 1] if i + 1 < len(rest) else "")
            i += 1
        elif a.startswith("-o") and not a.startswith("--"):
            v = a[2:]
            vals.append(v[1:] if v.startswith("=") else v)
        elif _is_out_flag(a):
            vals.append(a.split("=", 1)[1])
        i += 1
    return vals


GRADE_FILTERS_MCP = frozenset({"eq", "curves", "colorbalance", "hue", "lut", "lutrgb", "lutyuv", "colorchannelmixer", "vibrance"})
GRADE_BAD_OPTIONS = frozenset({"file", "filename", "stats_file", "result", "psfile", "preset"})


def filter_values(rest: list[str]) -> list[str]:
    """Values of --filter in any abbreviation (--f ... --filter, with or without =)."""
    vals: list[str] = []
    i = 0
    while i < len(rest):
        a = rest[i]
        if a == "--":
            break
        flag = a.split("=", 1)[0]
        if a.startswith("--") and len(flag) >= 3 and "--filter".startswith(flag):
            if "=" in a:
                vals.append(a.split("=", 1)[1])
            else:
                vals.append(rest[i + 1] if i + 1 < len(rest) else "")
                i += 1
        i += 1
    return vals


def colour_filter_ok(chain: str) -> bool:
    """True if every filter of the chain is a colour filter from the closed set, with no file-reading option."""
    for part in re.split(r"[,;]", chain):
        name, _, opts = part.strip().partition("=")
        if name.strip() not in GRADE_FILTERS_MCP:
            return False
        for o in (opts.split(":") if opts else []):
            key, eq, _v = o.partition("=")
            if key.strip().lower() in GRADE_BAD_OPTIONS or (not eq and name.strip() == "curves"):
                return False
    return True


def _grade_inputs(rest: list[str]) -> list[str]:
    """Positional arguments of `grade` once the values of -o/--out/--output/--preset/--filter are set aside."""
    out, skip = [], False
    for r in rest:
        if skip:
            skip = False
        elif r in ("-o", "--preset") or ((_is_out_flag(r) or (r.startswith("--f") and "--filter".startswith(r))) and "=" not in r):
            skip = True
        elif not r.startswith("-"):
            out.append(r)
    return out


SUB_HELP = {
    "setup": "simplicio-video edit setup\n  clona/atualiza o video-use no commit fixado e imprime a pasta helpers/ (precisa de ffmpeg e de SIMPLICIO_TTS_PY)\n"
             "exemplo:\n  simplicio-video edit setup",
    "pack": "simplicio-video edit pack EDIT_DIR\n  junta edit/transcripts/*.json em takes_packed.md (o que o agente lê)\n"
            "exemplo:\n  simplicio-video edit pack edit",
    "render": "simplicio-video edit render EDL.json -o OUT.mp4 [args do render.py]\n  aplica o EDL (sem loudnorm, 30 fps); legendas precisam de ffmpeg com libass\n"
              "exemplo:\n  simplicio-video edit render edit/edl.json -o out/final.raw.mp4",
    "verify": "simplicio-video edit verify VIDEO T0 T1 -o PNG [--transcript words.json]\n  filmstrip do trecho para conferir o corte\n"
              "exemplo:\n  simplicio-video edit verify out/final.mp4 12.0 18.5 -o out/check.png",
    "transcribe-batch": "simplicio-video edit transcribe-batch DIR [args do transcribe_batch.py]\n  transcreve uma pasta de vídeos em paralelo com o ElevenLabs Scribe "
                        "(terceiro pago, ELEVENLABS_API_KEY); só no terminal, o MCP recusa\nexemplo:\n  simplicio-video edit transcribe-batch videos/",
}


def run_edit(args: list[str]) -> int:
    first = args[0] if args else "help"
    rest = args[1:]
    if first == "help" and rest[:1] == ["grade"]:  # the CLI's argparse keeps `edit grade --help` for itself; this one always reaches us
        print(GRADE_HELP)
        return 0
    if first in ("-h", "--help", "help"):
        print("video-use (https://github.com/browser-use/video-use) sobre qualquer MP4/MOV\n"
              "  edit setup                                  # clona no commit fixado; imprime helpers/\n"
              "  edit transcribe FONTE.mp4 -o OUT.json [--script spec.json]   # local (faster-whisper)\n"
              "  edit pack EDIT_DIR                          # transcrições -> takes_packed.md\n"
              "  edit render EDL.json -o OUT.mp4 [args]      # EDL -> MP4 (sem loudnorm; use master.sh)\n"
              "  edit verify VIDEO T0 T1 -o PNG [--transcript words.json]   # filmstrip do corte\n"
              "  edit grade FONTE.mp4 -o OUT.mp4 [--preset N|--filter F] | --analyze FONTE   # cor (edit help grade)\n"
              "  edit transcribe-batch DIR [args]            # Scribe em lote (ElevenLabs, terceiro pago): só no terminal")
        return 0
    if first in SUB_HELP and any(h in rest for h in ("-h", "--help")):
        print(SUB_HELP[first])
        return 0
    if first == "grade" and any(h in rest for h in ("-h", "--help")):
        print(GRADE_HELP)
        return 0
    if first == "grade" and not any(r.split("=", 1)[0] in GRADE_READ_ONLY for r in rest):
        if not _grade_inputs(rest):
            raise EditError("grade: informe FONTE.mp4 -o OUT.mp4 (edit help grade)")
        if not _output_values(rest):
            raise EditError("grade: -o OUT.mp4 é obrigatório (ou use --analyze FONTE.mp4)")
    if first == "transcribe" and not any(h in rest for h in ("-h", "--help")):
        if not rest:
            raise EditError("transcribe: informe FONTE.mp4 -o OUT.json")
        if not _tem_saida(rest):
            raise EditError("transcribe: -o OUT.json é obrigatório (como em render e verify)")
    if first == "transcribe" and any(h in rest for h in ("-h", "--help")):
        print("edit transcribe FONTE.mp4 -o OUT.json [--model M] [--lang L] [--fixes F.json] [--script spec.json]\n"
              "  transcrição local (faster-whisper); -o (ou --out/--output) é obrigatório, como em render e verify")
        return 0
    h = helpers_dir()
    if first == "setup":
        print(h)
        return 0
    py = paths.tts_python()
    tools = tool_dir()
    if first == "transcribe":
        return _run([py, str(tools / "transcribe_local.py"), *rest])
    if first == "grade":
        return _run([py, str(h / "grade.py"), *rest])
    if first == "transcribe-batch":
        return _run([py, str(h / "transcribe_batch.py"), *rest])
    if first == "pack":
        if len(rest) != 1:
            raise EditError("pack: informe EDIT_DIR")
        return _run([py, str(h / "pack_transcripts.py"), "--edit-dir", rest[0]])
    if first == "render":
        if not rest:
            raise EditError("render: informe EDL.json -o OUT.mp4")
        return _run([py, str(h / "render.py"), rest[0], "--no-loudnorm", "--fps", "30", *rest[1:]])
    if first == "verify":
        if len(rest) < 3:
            raise EditError("verify: informe VIDEO T0 T1 -o PNG")
        return _run([py, str(h / "timeline_view.py"), *rest])
    raise EditError(f"subcomando desconhecido: {first} (setup|transcribe|transcribe-batch|pack|render|verify|grade)")
