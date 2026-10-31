"""Every operations command has --help with examples and says what it really does (install, update, doctor, setup).
The help is part of the contract: it names the flags and the exit codes. login, logout and auth no longer exist here."""
import re

import pytest

from _comum import executa
from simplicio_video.cli import main

COMANDOS = ["install", "update", "doctor", "setup"]

# what each --help must mention (flags, exit codes, files)
DEVE_CITAR = {
    "install": ["--target", "--global", "--host", "--check", "--dry-run", "--json", "--verify", "--uninstall", "--prune-project-copies",
                "10", "simplicio.video-install-plan/v1", "skills", "não tem hooks", ".claude/skills", "install-ownership.json",
                "scripts/dev_install.sh", "dev_install.ps1", "AGENTS.md", "claude", "codex", "cursor", "vscode", "grok", "kiro",
                "antigravity", "opencode", "gemini", "aider", "simplicio_agent", "openclaw", "deixa", "recibo", "sha256",
                "-NoProfile -ExecutionPolicy Bypass -File scripts\\dev_install.ps1", "install.lock", "problems"],
    "update": ["--check", "--dry-run", "--force", "10", "git pull", "PyPI", "update-check.json", "git fetch", "SIMPLICIO_OFFLINE",
               "só mostra o plano e sai com 0", "--no-optional-locks", "2.15", "bash scripts/dev_install.sh",
               "powershell -NoProfile -ExecutionPolicy Bypass -File scripts\\dev_install.ps1", "install --global", "recusa",
               "--force-reinstall --no-deps"],
    "doctor": ["--json", "--online", "all", "simplicio.doctor/v1", "warn", "fail"],
    "setup": ["--yes", "--theme", "--lang"],
}


@pytest.mark.parametrize("comando", COMANDOS)
def test_comando_de_operacao_tem_help_com_exemplos(comando, capsys):
    rc, out, err = executa([*comando.split(), "--help"], capsys, main)
    assert rc == 0, f"{comando} --help falhou: {err}"
    assert "exemplos" in out.lower(), f"{comando} --help sem exemplos"
    assert f"simplicio-video {comando}" in out, f"{comando} --help sem um exemplo que comece por `simplicio-video {comando}`"


@pytest.mark.parametrize("comando", COMANDOS)
def test_help_cita_o_que_o_comando_faz(comando, capsys):
    rc, out, err = executa([*comando.split(), "--help"], capsys, main)
    for trecho in DEVE_CITAR[comando]:
        assert trecho in out, f"{comando} --help não cita {trecho!r}"


def test_o_help_raiz_nao_lista_login_logout_nem_auth(capsys):
    rc, out, err = executa(["--help"], capsys, main)
    assert rc == 0
    listados = [l for l in out.splitlines() if re.match(r"^    (login|logout|auth)\s", l)]
    assert listados == [], f"o help raiz ainda lista: {listados}"


@pytest.mark.parametrize("argv", [["login"], ["login", "--json"], ["logout", "--yes"], ["auth", "status"]],
                         ids=lambda x: " ".join(x) if isinstance(x, list) else str(x))
def test_login_logout_e_auth_sao_comandos_desconhecidos(argv, capsys):
    rc, out, err = executa(argv, capsys, main)
    assert rc == 2 and "invalid choice" in err, (rc, err)


def test_o_install_nao_oferece_mais_as_opcoes_do_venv_e_o_update_nao_promete_o_pull(capsys):
    rc, out, err = executa(["install", "--help"], capsys, main)
    assert "--python" not in out and "--with" not in out and "uv" not in out.replace("scripts/dev_install", ""), \
        "the .venv options live in scripts/dev_install.sh now"
    rc, out, err = executa(["update", "--help"], capsys, main)
    texto = " ".join(out.split())
    assert "git pull --ff-only" not in texto and "stash" not in texto and "árvore suja" not in texto


def test_o_help_raiz_descreve_install_como_skills_no_host_e_update_como_recusa_no_checkout(capsys):
    rc, out, err = executa(["--help"], capsys, main)
    linha = {nome: next(l for l in out.splitlines() if l.startswith(f"  {nome} ")) for nome in ("install", "update")}
    assert "skills" in linha["install"] and "host" in linha["install"] and ".venv" not in linha["install"]
    assert "recusa" in linha["update"] and "pip" in linha["update"] and "git pull --ff-only" not in linha["update"]


