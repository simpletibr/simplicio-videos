import pytest

from helpers import run_cli

SUBS = ["init", "validate", "voice", "render", "run", "clone", "montage", "edit", "shorts", "opencut", "toonflow", "swap", "moneyprinter", "matchcut", "instagram", "jobs", "social", "openverse", "busca", "mcp", "list",
        "install", "update", "doctor", "setup", "rea-video"]


def test_main_help_lists_the_whole_flow():
    r = run_cli("--help")
    assert r.returncode == 0
    out = r.stdout
    pos = [out.index(w) for w in ("1. init", "3. validate", "4. voice", "5. render", "run ")]
    assert pos == sorted(pos)
    for s in SUBS:
        assert f"    {s}" in out
    assert "schema/contract.schema.json" in out and "exemplos:" in out and "skills/simplicio-video/SKILL.md" in out


@pytest.mark.parametrize("sub,must", [
    ("init", ["cliente", "campanha", "--template", "--nome", "--drive-nome", "--ano", "--out", "--force"]),
    ("validate", ["CONTRATO.yaml", "--need-lock", "--json", "J-cut", "NUNCA"]),
    ("voice", ["CONTRATO.yaml", "--provider", "--force", "FALA_ID", "file", "local", "gemini", "elevenlabs", "xai", "timing.lock.json"]),
    ("render", ["CONTRATO.yaml", "--backend", "--out", "--quality", "--gpu", "--workdir", "colab", "render.manifest.json", "-14 LUFS",
                "kaggle", "colab-cli", "--accelerator", "--timeout", "KAGGLE_USERNAME"]),
    ("run", ["CONTRATO.yaml", "--provider", "--backend", "--accelerator", "ferramenta de operação"]),
    ("clone", ["Hypit AI", "argumentos repassados"]),
    ("montage", ["OpenMontage", "argumentos repassados"]),
    ("edit", ["video-use", "render"]),
    ("opencut", ["OpenCut", "dev"]),
    ("toonflow", ["Toonflow", "clone", "serve", "where", "Bun", "--lan", "0.0.0.0"]),
    ("swap", ["providers", "estimate", "run", "status", "--autorizo", "--yes", "--max-usd", "UNVERIFIED"]),
    ("moneyprinter", ["MoneyPrinterTurbo", "clone", "setup", "serve", "where", "--lan", "0.0.0.0", "8501", "8080"]),
    ("matchcut", ["match-cut", "clone", "where", "status", "Renoise", "créditos"]),
    ("instagram", ["instagram-agent-skill", "clone", "where", "status", "skills", "run", "hookscore", "beats", "caption", "humanize", "detect", "swipe",
                   "--forcar", "--bruto", "INSTAGRAM_DIR", "MIT", "Jake Schincariol", "sha256", "inglês", "não posta", "terminal"]),
    ("rea-video", ["rea-video", "clone", "setup", "where", "status", "decompose", "--vlm", "ffmpeg", "REA_VLM_API_KEY", "terceiro"]),
    ("jobs", ["submit", "status", "list", "cancel", "result", "swap-run", "voice", "--yes"]),
    ("social", ["providers", "plan", "check", "recipe", "realoficial", "zernio", "consentimento", "UNVERIFIED"]),
    ("openverse", ["search", "get", "library", "review", "export", "credits", "--licencas", "cc0,pdm,by", "--pedido", "--folha", "parecer jurídico", "OPENVERSE_CLIENT_ID"]),
    ("busca", ["consulta", "pagina", "status", "log", "TinyFish", "enviada a um terceiro", "--max-chamadas-dia", "--permitir-dado-pessoal", "TINYFISH_API_KEY", "untrusted_"]),
    ("mcp", ["video.init", "video.render", "video.run", "stdio"]),
    ("list", ["templates", "motion", "voices", "--json"]),
])
def test_subcommand_help_is_complete(sub, must):
    r = run_cli(sub, "--engine-help" if sub == "clone" else "--help")  # `clone --help` is Hypit's own help
    assert r.returncode == 0, r.stderr
    for m in must:
        assert m in r.stdout, f"{sub} --help missing {m!r}"
    assert "exemplos:" in r.stdout and "simplicio-video " + sub in r.stdout
    if sub in ("clone", "montage", "edit", "opencut", "toonflow", "swap", "moneyprinter", "matchcut", "instagram", "rea-video", "jobs", "social", "openverse", "busca"):
        return
    if sub != "list":
        assert "schema/contract.schema.json" in r.stdout


# U22e: `voice` and `run` list the providers of the registry (`voice.PROVIDERS`, the order of `list voices`), not two lists by hand
@pytest.mark.parametrize("sub", ["voice", "run"])
def test_the_help_of_voice_and_run_lists_the_providers_of_the_registry_in_its_order(sub):
    import re

    from simplicio_video import voice

    r = run_cli(sub, "--help")
    assert r.returncode == 0, r.stderr
    achou = re.search(r"--provider, -p \{([^}]*)\}", r.stdout)
    assert achou, r.stdout
    assert achou.group(1).split(",") == list(voice.PROVIDERS)


# ...and without loading `voice` to do it (it adds 6 modules, childio among them): not in a help page, not in a refused `--provider`
SONDA_PROVIDERS = """\
import contextlib, io, json, sys
from simplicio_video import cli
with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
    try:
        cli.main({argv!r})
    except SystemExit:
        pass
print(json.dumps(sorted(m for m in ("voice", "voice_clone", "childio") if "simplicio_video." + m in sys.modules)))
"""


@pytest.mark.parametrize("argv", [["--help"], ["voice", "--help"], ["run", "--help"],
                                  ["voice", "contract.yaml", "--provider", "nope"], ["run", "contract.yaml", "--provider", "nope"]],
                         ids=["main", "voice", "run", "voice-refused", "run-refused"])
def test_listing_the_providers_does_not_load_the_voice_engine(tmp_path, argv):
    import json
    import subprocess
    import sys

    from helpers import offline_env

    (tmp_path / "home").mkdir()
    env = offline_env(HOME=str(tmp_path / "home"), SIMPLICIO_VIDEO_DATA=str(tmp_path / "data"), NO_COLOR="1")
    r = subprocess.run([sys.executable, "-c", SONDA_PROVIDERS.format(argv=argv)], capture_output=True, text=True, cwd=tmp_path, env=env,
                       timeout=120)
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout.splitlines()[-1]) == []
