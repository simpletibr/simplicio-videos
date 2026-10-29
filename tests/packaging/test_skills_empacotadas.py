"""The skills that `install` copies into the agent host ship INSIDE the package (`src/simplicio_video/data/skills/`).

ONE source of truth: the package copy. `skills/<nome>/` at the repo root is the mirror that the Runtime plugin and the
readers of the repo use; a test demands that the two are byte for byte equal, so `pip install simplicio-video` and a checkout
install exactly the same skill. The package copy is also what the wheel carries, so it holds NO client data (PyPI is public and
immutable) and no link that only works inside a checkout.
"""
from __future__ import annotations

import re

import pytest

import dados_cliente_guard as guarda
from _caixa import skill_sync
from _comum import ROOT

PACOTE = ROOT / "src" / "simplicio_video" / "data" / "skills"
ESPELHO = ROOT / "skills"
NOMES = ("simplicio-video", "simplicio-video-edit", "simplicio-video-media", "simplicio-video-shorts",
         "simplicio-video-social", "simplicio-video-voicestudio")


def _arquivos(raiz):
    return {p.relative_to(raiz).as_posix(): p.read_bytes() for p in sorted(raiz.rglob("*")) if p.is_file()}


def test_o_pacote_traz_as_seis_skills_do_simplicio_video():
    assert tuple(sorted(p.name for p in PACOTE.iterdir() if p.is_dir())) == NOMES
    assert tuple(sorted(skill_sync.SKILLS)) == NOMES
    for nome in NOMES:
        assert (PACOTE / nome / "SKILL.md").is_file(), nome


@pytest.mark.parametrize("nome", NOMES)
def test_a_skill_do_pacote_e_igual_byte_a_byte_a_do_repo(nome):
    pacote, espelho = _arquivos(PACOTE / nome), _arquivos(ESPELHO / nome)
    assert pacote.keys() == espelho.keys(), f"arquivos diferentes em skills/{nome} e no pacote"
    for rel in pacote:
        assert pacote[rel] == espelho[rel], (
            f"skills/{nome}/{rel} difere da cópia do pacote. A fonte da verdade é o pacote: edite "
            f"src/simplicio_video/data/skills/{nome}/{rel} e copie para skills/{nome}/{rel}")


def test_o_repo_nao_tem_skill_que_o_pacote_nao_leva():
    assert sorted(p.name for p in ESPELHO.iterdir() if p.is_dir()) == sorted(NOMES)


@pytest.mark.parametrize("nome", NOMES)
def test_o_cabecalho_da_skill_tem_name_igual_a_pasta_e_description(nome):
    texto = (PACOTE / nome / "SKILL.md").read_text(encoding="utf-8")
    cabecalho = re.match(r"---\n(.*?)\n---\n", texto, re.S)
    assert cabecalho, f"{nome}/SKILL.md sem front matter"
    campos = dict(re.findall(r"^(name|description):\s*(.+)$", cabecalho.group(1), re.M))
    assert campos.get("name") == nome and len(campos.get("description", "")) > 40


@pytest.mark.parametrize("nome", NOMES)
def test_a_skill_do_pacote_nao_tem_dado_de_cliente_nem_identificador_do_dono(nome):
    """The wheel is public and PyPI is immutable: the same guard that scans src/ scans the skills."""
    for arquivo in (PACOTE / nome).rglob("*"):
        if arquivo.is_file():
            achados = guarda.achados_no_texto(arquivo.read_text(encoding="utf-8"), str(arquivo.relative_to(ROOT)))
            assert achados == [], "\n".join(achados)


@pytest.mark.parametrize("nome", NOMES)
def test_a_skill_do_pacote_nao_tem_link_relativo_que_so_vale_no_checkout(nome):
    texto = (PACOTE / nome / "SKILL.md").read_text(encoding="utf-8")
    relativos = [alvo for alvo in re.findall(r"\]\(([^)\s]+)\)", texto) if not re.match(r"(https?://|#|mailto:)", alvo)]
    assert relativos == [], f"links que quebram numa skill instalada fora do checkout: {relativos}"


def test_as_skills_nao_levam_cache_de_bytecode():
    assert not list(PACOTE.rglob("__pycache__")) and not list(PACOTE.rglob("*.pyc"))
