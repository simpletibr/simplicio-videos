import pytest

from conftest import run_cli

SUBS = ["init", "validate", "voice", "render", "run", "clone", "montage", "edit", "shorts", "opencut", "toonflow", "swap", "moneyprinter", "matchcut", "jobs", "social", "openverse", "busca", "mcp", "list",
        "install", "update", "doctor", "setup"]


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
    ("jobs", ["submit", "status", "list", "cancel", "result", "swap-run", "voice", "--yes"]),
    ("social", ["providers", "plan", "check", "recipe", "realoficial", "zernio", "consentimento", "UNVERIFIED"]),
    ("openverse", ["search", "get", "library", "review", "export", "credits", "--licencas", "cc0,pdm,by", "--pedido", "--folha", "parecer jurídico", "OPENVERSE_CLIENT_ID"]),
    ("busca", ["consulta", "pagina", "status", "log", "TinyFish", "enviada a um terceiro", "--max-chamadas-dia", "--permitir-dado-pessoal", "TINYFISH_API_KEY", "untrusted_"]),
    ("mcp", ["video.init", "video.render", "video.run", "stdio"]),
    ("list", ["templates", "motion", "voices", "--json"]),
])
def test_subcommand_help_is_complete(sub, must):
    r = run_cli(sub, "--help")
    assert r.returncode == 0, r.stderr
    for m in must:
        assert m in r.stdout, f"{sub} --help missing {m!r}"
    assert "exemplos:" in r.stdout and "simplicio-video " + sub in r.stdout
    if sub in ("clone", "montage", "edit", "opencut", "toonflow", "swap", "moneyprinter", "matchcut", "jobs", "social", "openverse", "busca"):
        return
    if sub != "list":
        assert "schema/contract.schema.json" in r.stdout


