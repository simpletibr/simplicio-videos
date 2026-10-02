import pytest

from conftest import run_cli

SUBS = ["init", "validate", "voice", "render", "publish", "run", "venda", "ugc", "mcp", "list"]


def test_main_help_lists_the_whole_flow():
    r = run_cli("--help")
    assert r.returncode == 0
    out = r.stdout
    pos = [out.index(w) for w in ("1. init", "3. validate", "4. voice", "5. render", "6. publish", "run ")]
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
    ("publish", ["CONTRATO.yaml", "--file", "--remote", "--dry-run", "--no-readme", "rclone", "Entregas no Drive", "vNN+1"]),
    ("run", ["CONTRATO.yaml", "--provider", "--backend", "--publish", "--accelerator", "dry-run"]),
    ("venda", ["cobrar", "webhook", "entregar", "status", "--preco", "ABACATEPAY_API_KEY", "cobranca_criada", "erro_entrega"]),
    ("ugc", ["list", "prompt", "--app", "--fala", "--duracao", "--todos", "Seedance", "coleta/", "22-28", "ugc/pack.schema.json"]),
    ("mcp", ["video.init", "video.render", "video.publish", "stdio"]),
    ("list", ["templates", "motion", "voices", "--json"]),
])
def test_subcommand_help_is_complete(sub, must):
    r = run_cli(sub, "--help")
    assert r.returncode == 0, r.stderr
    for m in must:
        assert m in r.stdout, f"{sub} --help missing {m!r}"
    assert "exemplos:" in r.stdout and "simplicio-video " + sub in r.stdout
    if sub in ("venda", "ugc"):
        return
    if sub != "list":
        assert "schema/contract.schema.json" in r.stdout


@pytest.mark.parametrize("args,must", [
    (("venda", "cobrar"), ["PASTA", "--preco", "120|80|60", "sem padrão", "copia-e-cola", "pix-qr.png", "Idempotente", "ABACATEPAY_API_KEY"]),
    (("venda", "webhook"), ["serve", "ABACATEPAY_WEBHOOK_SECRET", "X-Webhook-Signature", "4xx", "127.0.0.1"]),
    (("venda", "webhook", "serve"), ["--port", "--host", "--raiz"]),
    (("venda", "entregar"), ["PASTA", "erro_entrega", "publish"]),
    (("venda", "status"), ["lote", "slug"]),
])
def test_venda_subcommand_help(args, must):
    r = run_cli(*args, "--help")
    assert r.returncode == 0, r.stderr
    for m in must:
        assert m in r.stdout, f"{' '.join(args)} --help missing {m!r}"
    assert "exemplo" in r.stdout
