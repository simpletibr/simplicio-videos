"""Edit track: browser-use/video-use over any MP4/MOV (HyperFrames, OpenMontage or OpenCut output).

Thin wrapper over the video-use files shipped in the package (data/tools/video-use): the agent writes edit/edl.json (versioned decision); everything else is ffmpeg.
"""
from __future__ import annotations

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
    r = subprocess.run(["bash", str(setup), "--quiet"], capture_output=True, text=True)
    if r.returncode != 0:
        raise EditError(r.stderr.strip() or "video-use setup.sh falhou")
    return Path(r.stdout.strip().splitlines()[-1])


def _run(cmd: list[str]) -> int:
    return run_child(cmd)


def _tem_saida(rest: list[str]) -> bool:
    """True if the output option is there in any spelling the upstream argparse takes: -o X, -oX, --output X, --out X, --o=X..."""
    for r in rest[1:] if rest and not rest[0].startswith("-") else rest:
        if r == "--":
            break
        if r.startswith("-o") and not r.startswith("--"):
            return True
        if r.startswith("--") and len(r) > 2 and r.split("=", 1)[0] in ("--output", "--outpu", "--outp", "--out", "--ou", "--o"):
            return True
    return False


OUT_FLAGS = ("--output", "--out")
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


def _output_values(rest: list[str]) -> list[str]:
    """Values given to -o / --out / --output in any spelling (-o X, -oX, --out X, --output=X); '' if the value is missing."""
    vals: list[str] = []
    i = 0
    while i < len(rest):
        a = rest[i]
        if a == "--":
            break
        if a == "-o" or a in OUT_FLAGS:
            vals.append(rest[i + 1] if i + 1 < len(rest) else "")
            i += 1
        elif a.startswith("-o") and not a.startswith("--"):
            vals.append(a[2:])
        elif a.startswith("--") and "=" in a and a.split("=", 1)[0] in OUT_FLAGS:
            vals.append(a.split("=", 1)[1])
        i += 1
    return vals


def _grade_inputs(rest: list[str]) -> list[str]:
    """Positional arguments of `grade` once the values of -o/--out/--output/--preset/--filter are set aside."""
    out, skip = [], False
    for r in rest:
        if skip:
            skip = False
        elif r in ("-o", "--preset", "--filter", *OUT_FLAGS):
            skip = True
        elif not r.startswith("-"):
            out.append(r)
    return out


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
