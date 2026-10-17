"""Docs of the PR "install universal e update igual ao simplicio-loop" (direct owner request, no issue).

The owner asked, in this order: "Coloca install, update, doctor, login, mesma coisa que fizemos no simplicio-loop e compatível com
simplicio-runtime"; "Só olha simplicio-loop"; "Fazia igual estava no simplicio-loop"; "Universal". PR #116 delivered login, doctor and
`update --check` but kept two decisions of its own: `install` stayed the `.venv` with uv and `update` of a checkout stayed `git pull
--ff-only`. This PR undoes both. The docs must say so: the ADR that supersedes ADR-0017 on the checkout, what is ported and what is
not (hooks, the hosts), how to use it on the three systems, what is UNVERIFIED, and the breaking changes. Reads repo files only.
"""
from __future__ import annotations

import re

import pytest

from _caixa import installer, skill_sync
from _comum import ROOT, exige_registrado
from simplicio_video.cli import main

ADR_20 = ROOT / "docs" / "decisoes" / "ADR-0020-install-universal-e-update-igual-ao-loop.md"
ADR_17 = ROOT / "docs" / "decisoes" / "ADR-0017-instalacao-atualizacao.md"
ADRS_README = ROOT / "docs" / "decisoes" / "README.md"
INSTALL_MD = ROOT / "docs" / "how-to" / "install.md"
PACKAGING_MD = ROOT / "docs" / "host" / "packaging.md"
SO_MD = ROOT / "docs" / "how-to" / "testar-em-windows-e-macos.md"
PLUGINS_MD = ROOT / "docs" / "factory" / "plugins.md"


def _texto(caminho) -> str:
    return " ".join(caminho.read_text(encoding="utf-8").split())


def _unreleased() -> str:
    texto = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    return " ".join(texto.split("## Unreleased", 1)[1].split("\n## ", 1)[0].split())


# --- ADR-0020 ------------------------------------------------------------------------------------------------------------------


def test_adr_0020_existe_tem_as_secoes_e_esta_no_indice():
    assert ADR_20.is_file(), f"{ADR_20.relative_to(ROOT)} não existe"
    texto = ADR_20.read_text(encoding="utf-8")
    for secao in ("## Contexto", "## Decisão", "## Consequências"):
        assert re.search(rf"^{re.escape(secao)}\s*$", texto, re.M), f"ADR-0020 sem a seção {secao!r}"
    assert "ADR-0020" in ADRS_README.read_text(encoding="utf-8"), "decisoes/README.md não lista a ADR-0020"


def test_adr_0020_registra_o_pedido_do_dono_e_o_que_supersede():
    texto = _texto(ADR_20)
    for trecho in ("Coloca install, update, doctor, login", "Só olha simplicio-loop", "Fazia igual estava no simplicio-loop",
                   "Universal", "supersede", "ADR-0017", "git pull --ff-only", ".venv", "uv", "pedido do dono"):
        assert trecho in texto, f"ADR-0020 não cita {trecho!r}"


def test_adr_0020_diz_o_que_foi_portado_e_o_que_nao_foi():
    texto = _texto(ADR_20)
    for host in installer.HOSTS:
        assert f"`{host}`" in texto, f"ADR-0020 não cita o host {host}"
    for trecho in ("hooks", "não tem hooks", "left_alone", "install-ownership.json", "simplicio.video-install-plan/v1",
                   "scripts/dev_install.sh", "scripts/dev_install.ps1", "install.sh", "install.ps1", "recusa", "exit 2",
                   "install --global", "UNVERIFIED", "Windows", "macOS", "PowerShell", "regras de host", "doctor"):
        assert trecho in texto, f"ADR-0020 não cita {trecho!r}"


def test_adr_0020_lista_as_diferencas_de_proposito_em_relacao_ao_loop():
    texto = _texto(ADR_20)
    assert "Diferenças de propósito" in texto
    for trecho in ("--prune-project-copies", "up_to_date", "link simbólico", "--json", "status"):
        assert trecho in texto, f"ADR-0020 não cita {trecho!r} entre as diferenças"


def test_adr_0017_avisa_que_a_decisao_do_checkout_foi_superada_pela_0020():
    texto = _texto(ADR_17)
    assert "ADR-0020" in texto and re.search(r"[Ss]uperad[ao]", texto)


# --- how-to/install.md and packaging.md -----------------------------------------------------------------------------------------


@pytest.mark.parametrize("caminho", [INSTALL_MD, PACKAGING_MD], ids=lambda p: p.name)
def test_o_install_dos_docs_e_o_das_skills_com_todos_os_hosts_e_flags(caminho):
    texto = _texto(caminho)
    for host in installer.HOSTS:
        assert f"`{host}`" in texto, f"{caminho.name} não lista o host {host}"
    for trecho in ("simplicio-video install", "--global", "--check", "--dry-run", "--json", "--verify", "--uninstall",
                   "--prune-project-copies", "--target", "--host", "left_alone", "install-ownership.json", "não tem hooks",
                   "scripts/dev_install.sh", "scripts/dev_install.ps1", ".claude/skills"):
        assert trecho in texto, f"{caminho.name} não cita {trecho!r}"


def test_o_how_to_diz_que_o_venv_e_o_dev_install_e_que_o_update_do_checkout_recusa():
    texto = _texto(INSTALL_MD)
    for trecho in ("bash scripts/dev_install.sh", "powershell -File scripts/dev_install.ps1", "./install.sh", "git pull",
                   "recusa", "exit 2", "pip install --upgrade simplicio-video", "install --global"):
        assert trecho in texto, f"install.md não cita {trecho!r}"
    assert "git pull --ff-only" not in texto, "the update no longer runs it"
    assert not re.search(r"simplicio-video install[^\n`]*--(python|with)\b", texto), "install --python/--with are gone"


def test_packaging_tem_a_tabela_dos_comandos_e_dos_codigos_de_saida_do_novo_contrato():
    texto = _texto(PACKAGING_MD)
    for trecho in ("install-plan.schema.json", "install-ownership.schema.json", "`simplicio.video-install-plan/v1`",
                   "`simplicio.video-install-ownership/v1`", "recusado: é um checkout", "dev_install.sh", "Mudanças que quebram"):
        assert trecho in texto, f"packaging.md não cita {trecho!r}"
    assert "install-result.schema.json" not in texto, "the schema of the .venv install is gone"
    quebram = texto.split("Mudanças que quebram", 1)[1]
    for trecho in ("install", "skills", "dev_install.sh", "git pull --ff-only", "update"):
        assert trecho in quebram, f"a seção de mudanças que quebram não cita {trecho!r}"


def test_packaging_diz_onde_cada_host_guarda_as_skills_nos_tres_sistemas():
    texto = _texto(PACKAGING_MD)
    for host, relativo in skill_sync.HOST_SKILL_ROOTS.items():
        assert relativo in texto, f"packaging.md não cita {relativo} ({host})"
    for trecho in ("HOME", "USERPROFILE", "Windows", "macOS", "Linux", "UNVERIFIED"):
        assert trecho in texto


def test_o_doc_diz_que_o_doctor_nao_ganhou_linha_de_skills_porque_o_loop_nao_tem():
    texto = _texto(ADR_20)
    assert "doctor" in texto and re.search(r"não (tem|ganha|cria)[^.]{0,80}skills", texto), \
        "ADR-0020 must say the doctor has no `skills` row, as in the loop"


# --- the guide for Windows and macOS ------------------------------------------------------------------------------------------


def test_o_guia_de_windows_e_macos_cobre_o_install_e_o_powershell():
    texto = _texto(SO_MD)
    for trecho in ("install --check", "install --dry-run --json", "install --verify", "dev_install.ps1", "PowerShell", "UNVERIFIED",
                   "alvo", "install.ps1", "powershell -File"):
        assert trecho in texto, f"o guia de Windows e macOS não cita {trecho!r}"
    assert not re.search(r"(Windows|macOS)[^.]{0,80}\b(foi testado|está testado|verificado em)\b", texto)


# --- the places that describe the commands ---------------------------------------------------------------------------------------


def test_agents_md_descreve_install_update_e_o_dev_install():
    texto = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    quick = [l for l in texto.splitlines() if l.startswith("simplicio-video install") or l.startswith("simplicio-video update")]
    assert len(quick) == 2, quick
    install, update = quick
    assert "skills" in install and "--global" in install and "--check" in install and "hooks" in install
    assert "recusa" in update and "git pull" in update and "dev_install" in update
    assert "bash scripts/dev_install.sh" in texto and "scripts/dev_install.ps1" in texto


def test_o_changelog_registra_o_install_universal_e_o_update_que_recusa():
    unreleased = _unreleased()
    for trecho in ("Mudanças que quebram", "install", "skills", "scripts/dev_install.sh", "scripts/dev_install.ps1", "install.ps1",
                   "update", "git pull --ff-only", "exit 2", "recusa", "simplicio.video-install-plan/v1", "install-ownership.json",
                   "install --global", "ADR-0020", "UNVERIFIED", "PowerShell", "hooks"):
        assert trecho in unreleased, f"CHANGELOG (Unreleased) não cita {trecho!r}"
    for host in installer.HOSTS:
        assert host in unreleased, f"CHANGELOG (Unreleased) não cita o host {host}"


def test_o_changelog_nao_descreve_mais_o_install_do_venv_nem_o_pull_como_se_fossem_do_motor():
    unreleased = _unreleased()
    # the removed file is named once, in the block that says it is gone; no other entry may still describe it
    a = unreleased.index("Mudanças que quebram: `install` universal")
    b = unreleased.index("### `install` universal (as skills vão para o host)")
    assert "simplicio-install.json" in unreleased[a:b]
    assert "simplicio-install.json" not in unreleased[:a] + unreleased[b:]
    assert not re.search(r"`update` (num|no) checkout:? recusa árvore suja", unreleased)


def test_o_skill_md_diz_como_instalar_a_skill_e_a_do_pacote_diz_o_mesmo():
    for caminho in (ROOT / "skills" / "simplicio-video" / "SKILL.md", ROOT / "src" / "simplicio_video" / "data" / "skills" / "simplicio-video" / "SKILL.md"):
        texto = caminho.read_text(encoding="utf-8")
        assert "simplicio-video install" in texto and ("scripts/dev_install.sh" in texto or "./install.sh" in texto), caminho


def test_o_plugins_md_nao_diz_mais_que_o_install_e_o_do_venv():
    texto = PLUGINS_MD.read_text(encoding="utf-8")
    assert "what `install.sh` calls" not in texto
    assert "simplicio-video install" in texto and "skills" in texto


def test_o_readme_do_repo_aponta_o_install_das_skills_e_o_dev_install():
    texto = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "simplicio-video install" in texto and "dev_install" in texto


@pytest.mark.parametrize("nome", ["install", "update"])
def test_os_subcomandos_citados_existem(nome, capsys):
    exige_registrado(nome, capsys, main)
