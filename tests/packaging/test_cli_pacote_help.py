"""Every operations command has --help with examples and says what it really does (install, update, doctor, setup, login,
logout, auth). The help is part of the contract: it names the flags, the exit codes and the Runtime login."""
import pytest

from _comum import executa
from simplicio_video.cli import main

COMANDOS = ["install", "update", "doctor", "setup", "login", "logout", "auth", "auth status"]

# what each --help must mention (flags, exit codes, files)
DEVE_CITAR = {
    "install": ["--check", "--dry-run", "--json", "--python", "--with", "10", "simplicio.video-install/v1"],
    "update": ["--check", "--dry-run", "--force", "10", "git pull --ff-only", "PyPI", "git stash", "update-check.json",
               "git fetch", "SIMPLICIO_OFFLINE"],
    "doctor": ["--json", "--online", "all", "login", "simplicio.doctor/v1", "warn", "fail"],
    "setup": ["--yes", "--theme", "--lang"],
    "login": ["--json", "--no-browser", "simplicio login google", "login.json", "SIMPLICIO_AUTH_FILE", "UNVERIFIED",
              "não guarda credencial"],
    "logout": ["--yes", "--json", "Runtime", "login.json", "forma de login", "not_a_login_file"],
    "auth": ["status"],
    "auth status": ["--json", "login.json", "nunca imprime"],
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


def test_o_help_raiz_lista_os_comandos_novos(capsys):
    rc, out, err = executa(["--help"], capsys, main)
    for nome in ("login", "logout", "auth"):
        assert f"    {nome} " in out, f"o help raiz não lista `{nome}`"


def test_login_nao_promete_o_que_nao_faz(capsys):
    """The login is a mirror of the Runtime's: it unlocks and charges nothing, and stores no credential."""
    rc, out, err = executa(["login", "--help"], capsys, main)
    texto = " ".join(out.split())
    assert "não libera nem cobra nada" in texto
    assert "crédito" not in texto.lower().replace("não guarda credencial", "")


def test_auth_status_nao_oferece_online(capsys):
    rc, out, err = executa(["auth", "status", "--help"], capsys, main)
    assert rc == 0, err
    assert "--json" in out and "--online" not in out
