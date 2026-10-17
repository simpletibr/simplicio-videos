"""Contrato dos docs do pacote de operação (issue #43): arquivos existem, ADR-0017 tem as seções, exemplos batem com o código.

Confere: os arquivos (how-to/install.md, how-to/testar-em-windows-e-macos.md, host/packaging.md, ADR-0017 e ADR-0019)
existem; os ADRs têm Contexto, Decisão e Consequências; todo `--with` dos blocos de código usa um extra que existe no
pyproject.toml; todo subcomando `simplicio-video X` citado nos docs está registrado no CLI; links relativos apontam para
arquivos que existem; o texto diz o que foi e o que não foi verificado (Windows e macOS reais são UNVERIFIED até alguém
rodar scripts/smoke_so.py); o CHANGELOG registra as mudanças que quebram. Só lê arquivos do repo; sem rede.
"""
from __future__ import annotations

import re

import pytest

from _comum import ROOT, exige_registrado
from simplicio_video.cli import main

tomllib = pytest.importorskip("tomllib")

INSTALL_MD = ROOT / "docs" / "how-to" / "install.md"
PACKAGING_MD = ROOT / "docs" / "host" / "packaging.md"
ADR = ROOT / "docs" / "decisoes" / "ADR-0017-instalacao-atualizacao.md"
ADR_LOGIN = ROOT / "docs" / "decisoes" / "ADR-0019-login-compartilhado.md"
SO_MD = ROOT / "docs" / "how-to" / "testar-em-windows-e-macos.md"
DOCS = [INSTALL_MD, PACKAGING_MD, ADR, ADR_LOGIN, SO_MD]
SECOES_ADR = ("## Contexto", "## Decisão", "## Consequências")
BLOCO = re.compile(r"```(?:bash|sh)\n(.*?)```", re.S)


def _extras_do_pyproject() -> set[str]:
    dados = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf8"))
    return set(dados["project"].get("optional-dependencies", {}))


def _blocos_de_codigo(caminho) -> list[str]:
    return BLOCO.findall(caminho.read_text(encoding="utf8"))


@pytest.mark.parametrize("caminho", DOCS, ids=lambda p: p.name)
def test_arquivo_do_pacote_existe(caminho):
    assert caminho.is_file(), f"{caminho.relative_to(ROOT)} não existe"


@pytest.mark.parametrize("caminho", [ADR, ADR_LOGIN], ids=lambda p: p.name)
def test_adr_tem_contexto_decisao_e_consequencias(caminho):
    texto = caminho.read_text(encoding="utf8")
    for secao in SECOES_ADR:
        assert re.search(rf"^{re.escape(secao)}\s*$", texto, re.M), f"{caminho.name} sem a seção {secao!r}"


def test_exemplos_de_with_usam_extras_que_existem():
    existentes = _extras_do_pyproject()
    assert existentes, "pyproject.toml sem optional-dependencies"
    usados = set()
    for bloco in _blocos_de_codigo(INSTALL_MD):
        for lista in re.findall(r"--with[ =]([A-Za-z0-9_,.-]+)", bloco):
            usados.update(lista.split(","))
    assert usados, "install.md não tem nenhum exemplo com --with"
    inexistentes = usados - existentes
    assert not inexistentes, f"install.md cita extras que não existem no pyproject: {sorted(inexistentes)}"


def test_subcomandos_citados_nos_docs_estao_registrados(capsys):
    citados = set()
    for caminho in (INSTALL_MD, PACKAGING_MD, SO_MD):
        for bloco in _blocos_de_codigo(caminho):
            citados.update(re.findall(r"simplicio-video\s+([a-z]+)", bloco))
    assert citados, "os docs não citam nenhum subcomando"
    for nome in sorted(citados):
        exige_registrado(nome, capsys, main)


@pytest.mark.parametrize("caminho", DOCS, ids=lambda p: p.name)
def test_links_relativos_apontam_para_arquivos_existentes(caminho):
    texto = caminho.read_text(encoding="utf8")
    faltando = []
    for alvo in re.findall(r"\]\(([^)\s]+)\)", texto):
        if alvo.startswith(("http://", "https://", "#", "mailto:")):
            continue
        arquivo = alvo.split("#", 1)[0]
        if not (caminho.parent / arquivo).resolve().exists():
            faltando.append(alvo)
    assert not faltando, f"{caminho.name} tem links quebrados: {faltando}"


def _texto(caminho) -> str:
    return " ".join(caminho.read_text(encoding="utf8").split())


def test_adr_0019_registra_a_decisao_do_login_compartilhado():
    texto = _texto(ADR_LOGIN)
    for trecho in ("espelho", "simplicio login google", "~/.simplicio/login.json", "SIMPLICIO_AUTH_FILE", "não libera",
                   "não cobra", "não guarda", "plugin.json", "regra 3", "login.lock"):
        assert trecho in texto, f"ADR-0019 não cita {trecho!r}"


def test_como_testar_em_windows_e_macos_diz_a_verdade_sobre_o_que_foi_rodado():
    texto = _texto(SO_MD)
    for trecho in ("scripts/smoke_so.py", "UNVERIFIED", "Windows", "macOS", "Python 3.10", "exit", "falhou"):
        assert trecho in texto, f"o how-to de Windows e macOS não cita {trecho!r}"
    assert "ACL" in texto, "the Windows limit (modes and ACLs are not verified) must be written down"
    assert not re.search(r"(Windows|macOS)[^.]{0,80}\b(foi testado|está testado|verificado em)\b", texto), \
        "the doc must not claim a system that was not run"


def test_packaging_documenta_login_update_doctor_e_o_que_cada_comando_toca():
    texto = _texto(PACKAGING_MD)
    for trecho in ("simplicio-video login", "simplicio-video logout", "simplicio-video auth status", "--dry-run", "--online",
                   "simplicio.doctor/v1", "update-check.json", "~/.simplicio/login.json", "login.lock", "SIMPLICIO_AUTH_FILE",
                   "PyPI", "git stash", "exit", "10"):
        assert trecho in texto, f"packaging.md não cita {trecho!r}"
    assert "Windows" in texto and "macOS" in texto and "UNVERIFIED" in texto


def test_how_to_install_cobre_pip_checkout_e_o_login():
    texto = _texto(INSTALL_MD)
    for trecho in ("pip install --upgrade simplicio-video", "simplicio-video login", "instalado por pip",
                   "simplicio-video doctor --online", "git stash"):
        assert trecho in texto, f"install.md não cita {trecho!r}"


def test_o_changelog_registra_as_mudancas_que_quebram_e_o_que_nao_foi_verificado():
    texto = (ROOT / "CHANGELOG.md").read_text(encoding="utf8")
    unreleased = texto.split("## Unreleased", 1)[1].split("\n## ", 1)[0]
    plano = " ".join(unreleased.split())
    for trecho in ("Mudanças que quebram", "doctor --json", "`ok`", "install --check", "10", "--force", "update",
                   "exit 2", "UNVERIFIED", "Windows", "macOS", "scripts/smoke_so.py", "PyPI"):
        assert trecho in plano, f"CHANGELOG (Unreleased) não cita {trecho!r}"


def test_o_agents_md_lista_os_comandos_novos_no_quickstart():
    texto = (ROOT / "AGENTS.md").read_text(encoding="utf8")
    for trecho in ("simplicio-video login", "simplicio-video logout", "simplicio-video auth status"):
        assert trecho in texto, f"AGENTS.md sem {trecho!r}"


def test_a_referencia_gerada_descreve_as_variaveis_novas_e_lista_os_schemas():
    config = (ROOT / "docs" / "reference" / "config.md").read_text(encoding="utf8")
    for nome in ("SIMPLICIO_AUTH_FILE", "GH_TOKEN", "GITHUB_TOKEN", "PIP_BREAK_SYSTEM_PACKAGES"):
        linha = next((l for l in config.splitlines() if l.startswith(f"| `{nome}` |")), None)
        assert linha, f"{nome} não está em docs/reference/config.md"
        assert "sem descrição" not in linha, f"{nome} sem descrição em gen_reference.DESCRIPTIONS"
    schemas = (ROOT / "docs" / "reference" / "schemas.md").read_text(encoding="utf8")
    for nome in ("doctor", "login", "logout", "auth-status", "update-check", "install-result"):
        assert f"schemas/cli/{nome}.schema.json" in schemas, f"{nome} fora de docs/reference/schemas.md"
    cli = (ROOT / "docs" / "reference" / "cli.md").read_text(encoding="utf8")
    for nome in ("login", "logout", "auth"):
        assert f"## simplicio-video {nome}" in cli


# --- the corrections of the review of PR #116 ----------------------------------------------------------------------------------


def test_a_pasta_pessoal_vem_de_home_e_so_depois_de_userprofile_nos_docs():
    """The Runtime and the loop read HOME first on every system: the docs must not say USERPROFILE comes first on Windows."""
    packaging = _texto(PACKAGING_MD)
    assert "`HOME` e, só depois, de `USERPROFILE`" in packaging, "packaging.md does not state the order of HOME and USERPROFILE"
    assert "vem de `USERPROFILE` no Windows" not in packaging and "`USERPROFILE` no Windows e de `HOME` nos outros" not in packaging
    guia = _texto(SO_MD)
    for trecho in ("pastas diferentes", "HOME", "USERPROFILE", "Runtime"):
        assert trecho in guia, f"the Windows guide does not mention {trecho!r}"


def test_packaging_documenta_o_que_a_revisao_do_116_mudou():
    texto = _texto(PACKAGING_MD)
    for trecho in ("SIMPLICIO_OFFLINE", "git fetch", "not_a_login_file", "mais nova que a última release", "LC_ALL",
                   "XDG_RUNTIME_DIR", "1 MiB", "biblioteca padrão", "login_permissions", "login_invalid"):
        assert trecho in texto, f"packaging.md não cita {trecho!r}"
    assert "recusando um downgrade" not in texto and "downgrade sem `--force` |" not in texto, \
        "an installed version newer than the latest release is up to date (exit 0), not a refusal"


def test_o_changelog_registra_as_correcoes_da_revisao_do_116():
    texto = (ROOT / "CHANGELOG.md").read_text(encoding="utf8")
    unreleased = " ".join(texto.split("## Unreleased", 1)[1].split("\n## ", 1)[0].split())
    for trecho in ("install.sh", "PyYAML", "not_a_login_file", "git fetch", "`HOME`", "1 MiB", "mais nova"):
        assert trecho in unreleased, f"CHANGELOG (Unreleased) não cita {trecho!r}"
