"""Helpers shared by the tests (one copy of each, instead of one per test file).

Import them by name: `from helpers import ROOT, edit_yaml`. `tests/` is on sys.path for every test (pytest puts the folder of
conftest.py there), including those in tests/packaging, tests/test_docs, tests/test_scripts and tests/golden.

  repo      ROOT, SRC, SCRIPTS, FIXTURE, WJR, LOTHUS, needs_client, contract_with_coleta_placeholders
  env       offline_env, run_cli, have_render_tools, isolate_tools
  skips     needs_ffmpeg, ffmpeg_ou_pula
  files     edit_yaml, fake_mp4
  capture   run_main
  procs     vivo, espera
  audio     pcm_wav, sine_wav

Left where they are on purpose (the copies look alike, the behaviour is not):
  checkout        each track builds a different fake upstream (other files, other marker, other env var)
  build_checkout  instagram: 13 skills and 6 scripts with hashes; matchcut: SKILL.md and 2 pinned files
  _git            test_cli_update asserts rc 0 and returns stdout; test_skills_empacotadas raises on failure with its own -c config;
                  test_pacote_pypi runs in ROOT and returns the CompletedProcess unchecked
  _run            test_childio runs a child through childio.run_child; test_bundle_script runs render_bundle.sh;
                  test_moneyprinter calls run_moneyprinter (only the in-process `main(argv)` copies share `run_main`)
  _wav            test_mediaio writes a silent file; test_codigo_morto reads a WAV back
Importing this package must stay cheap: no simplicio_video import at the top of a module (the helpers that need it import it inside).
"""

from helpers.audio import pcm_wav, sine_wav
from helpers.capture import run_main
from helpers.env import have_render_tools, isolate_tools, offline_env, run_cli
from helpers.files import edit_yaml, fake_mp4
from helpers.procs import espera, vivo
from helpers.repo import CLIENT_DATA_REASON, FIXTURE, LOTHUS, ROOT, SCRIPTS, SRC, WJR, contract_with_coleta_placeholders, needs_client
from helpers.skips import ffmpeg_ou_pula, needs_ffmpeg

__all__ = [
    "CLIENT_DATA_REASON", "FIXTURE", "LOTHUS", "ROOT", "SCRIPTS", "SRC", "WJR", "contract_with_coleta_placeholders", "edit_yaml", "espera",
    "fake_mp4", "ffmpeg_ou_pula", "have_render_tools", "isolate_tools", "needs_client", "needs_ffmpeg", "offline_env", "pcm_wav",
    "run_cli", "run_main", "sine_wav", "vivo",
]
