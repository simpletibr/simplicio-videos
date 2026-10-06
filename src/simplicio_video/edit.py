"""Edit track: browser-use/video-use over any MP4/MOV (HyperFrames, OpenMontage or OpenCut output).

Thin wrapper over tools/video-use: the agent writes edit/edl.json (versioned decision); everything else is ffmpeg.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from . import paths


class EditError(Exception):
    pass


def helpers_dir() -> Path:
    setup = paths.home() / "tools" / "video-use" / "setup.sh"
    r = subprocess.run(["bash", str(setup), "--quiet"], capture_output=True, text=True)
    if r.returncode != 0:
        raise EditError(r.stderr.strip() or "tools/video-use/setup.sh falhou")
    return Path(r.stdout.strip().splitlines()[-1])


def _run(cmd: list[str]) -> int:
    return subprocess.call(cmd)


def run_edit(args: list[str]) -> int:
    first = args[0] if args else "help"
    rest = args[1:]
    if first in ("-h", "--help", "help"):
        print("video-use (https://github.com/browser-use/video-use) sobre qualquer MP4/MOV\n"
              "  edit setup                                  # clona no commit fixado; imprime helpers/\n"
              "  edit transcribe FONTE.mp4 [-o OUT] [--script spec.json]   # local (faster-whisper)\n"
              "  edit pack EDIT_DIR                          # transcrições -> takes_packed.md\n"
              "  edit render EDL.json -o OUT.mp4 [args]      # EDL -> MP4 (sem loudnorm; use master.sh)\n"
              "  edit verify VIDEO T0 T1 -o PNG [--transcript words.json]   # filmstrip do corte")
        return 0
    h = helpers_dir()
    if first == "setup":
        print(h)
        return 0
    py = paths.tts_python()
    tools = paths.home() / "tools" / "video-use"
    if first == "transcribe":
        if not rest:
            raise EditError("transcribe: informe FONTE.mp4")
        return _run([py, str(tools / "transcribe_local.py"), *rest])
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
    raise EditError(f"subcomando desconhecido: {first} (setup|transcribe|pack|render|verify)")
