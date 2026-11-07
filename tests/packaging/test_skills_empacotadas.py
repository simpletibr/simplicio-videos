"""The skills that `install` copies into the agent host ship INSIDE the package (`src/simplicio_video/data/skills/`).

ONE source of truth: the package copy. `skills/<nome>/` at the repo root is the mirror that the Runtime plugin and the
readers of the repo use; a test demands that the two are byte for byte equal, so `pip install simplicio-video` and a checkout
install exactly the same skill. The package copy is also what the wheel carries, so it holds NO client data (PyPI is public and
immutable) and no link that only works inside a checkout.

The mirror is GENERATED (U02): `scripts/sync_skills.py` copies the package copy to `skills/` and rewrites the `GENERATED skills`
block of `.gitignore` from `skill_sync.SKILLS`; `--check` (run by `make docs`, so by `make check`) exits 1 with the diff when
either is stale, and `make regen` runs it without the flag. The tests at the end of this file run the script in a temporary copy
of the checkout, mutate it and look at the exit code, so the gate really breaks when the mirror is edited by hand.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys

import pytest

import dados_cliente_guard as guarda
from _caixa import skill_sync
from _comum import ROOT

PACOTE = ROOT / "src" / "simplicio_video" / "data" / "skills"
ESPELHO = ROOT / "skills"
NOMES = ("deep-news", "deep-product", "deep-service", "simplicio-video", "simplicio-video-edit", "simplicio-video-media", "simplicio-video-shorts",
         "simplicio-video-social", "simplicio-video-trilhas", "simplicio-video-voicestudio")


def _arquivos(raiz):
    return {p.relative_to(raiz).as_posix(): p.read_bytes() for p in sorted(raiz.rglob("*")) if p.is_file()}


def test_o_pacote_traz_as_dez_skills_do_simplicio_video():
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
            f"src/simplicio_video/data/skills/{nome}/{rel} e rode `make regen` (scripts/sync_skills.py) para regerar skills/")


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


# --- o espelho é gerado: scripts/sync_skills.py (U02) -----------------------------------------------------------------------------------
#
# Cada teste roda o script numa CÓPIA do checkout (o script acha a raiz pelo próprio caminho), então a mutação nunca toca o repo real.

SCRIPT = ROOT / "scripts" / "sync_skills.py"
INICIO = "# BEGIN GENERATED skills"
FIM = "# END GENERATED skills"
SO_O_NECESSARIO = ("scripts/sync_skills.py", "src/simplicio_video/skill_sync.py", "src/simplicio_video/data/skills", "skills", ".gitignore")


def _roda(raiz, *args):
    return subprocess.run([sys.executable, str(raiz / "scripts" / "sync_skills.py"), *args], capture_output=True, text=True, timeout=60)


def _make(*args):
    env = {k: v for k, v in os.environ.items() if k not in ("MAKEFLAGS", "MFLAGS", "MAKELEVEL")}
    return subprocess.run(["make", "-n", "-C", str(ROOT), *args], capture_output=True, text=True, timeout=60, env=env)


def _tudo(raiz):
    """Every file under the pieces the script reads or writes: relative path -> bytes."""
    saida = {}
    for rel in SO_O_NECESSARIO:
        alvo = raiz / rel
        if alvo.is_file():
            saida[rel] = alvo.read_bytes()
        elif alvo.is_dir():
            saida.update({p.relative_to(raiz).as_posix(): p.read_bytes() for p in sorted(alvo.rglob("*")) if p.is_file()})
    return saida


@pytest.fixture
def checkout(tmp_path):
    assert SCRIPT.is_file(), "scripts/sync_skills.py não existe (U02: o espelho skills/ é gerado por ele)"
    raiz = tmp_path / "repo"
    for rel in SO_O_NECESSARIO:
        origem, destino = ROOT / rel, raiz / rel
        destino.parent.mkdir(parents=True, exist_ok=True)
        if origem.is_dir():
            shutil.copytree(origem, destino, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        else:
            shutil.copy2(origem, destino)
    return raiz


def _bloco(texto):
    linhas = texto.splitlines()
    return linhas[linhas.index(INICIO):linhas.index(FIM) + 1]


def test_o_checkout_real_esta_em_dia_com_o_sync_skills():
    assert SCRIPT.is_file(), "scripts/sync_skills.py não existe (U02: o espelho skills/ é gerado por ele)"
    r = _roda(ROOT, "--check")
    assert r.returncode == 0, r.stdout + r.stderr


def test_o_gitignore_do_repo_cobre_todas_as_skills_do_skill_sync():
    """Today it lists 6 of the 10: a skill that `install` copies into the repo root would show up as untracked."""
    linhas = _bloco((ROOT / ".gitignore").read_text(encoding="utf-8"))
    assert [l for l in linhas if l.startswith(".claude/skills/")] == [f".claude/skills/{n}/" for n in skill_sync.SKILLS]


def test_o_gitignore_fora_do_bloco_nao_e_tocado(checkout):
    antes = (checkout / ".gitignore").read_text(encoding="utf-8")
    assert _roda(checkout, "--check").returncode == 0
    assert _roda(checkout).returncode == 0
    assert (checkout / ".gitignore").read_text(encoding="utf-8") == antes


def test_editar_o_espelho_a_mao_quebra_o_check_e_o_regen_desfaz(checkout):
    alvo = checkout / "skills" / "simplicio-video" / "SKILL.md"
    alvo.write_bytes(alvo.read_bytes() + b"\nlinha a mao\n")
    r = _roda(checkout, "--check")
    assert r.returncode == 1
    saida = r.stdout + r.stderr
    assert "skills/simplicio-video/SKILL.md" in saida and "make regen" in saida
    assert "linha a mao" in saida, "o --check mostra o diff, não só o nome do arquivo"
    assert _roda(checkout).returncode == 0
    assert _tudo(checkout) == _tudo(ROOT)
    assert _roda(checkout, "--check").returncode == 0


def test_a_fonte_do_pacote_editada_se_propaga_para_o_espelho(checkout):
    fonte = checkout / "src" / "simplicio_video" / "data" / "skills" / "deep-news" / "SKILL.md"
    fonte.write_bytes(fonte.read_bytes() + b"\nacrescentado no pacote\n")
    assert _roda(checkout, "--check").returncode == 1
    assert _roda(checkout).returncode == 0
    assert (checkout / "skills" / "deep-news" / "SKILL.md").read_bytes() == fonte.read_bytes()
    assert _roda(checkout, "--check").returncode == 0


def test_arquivo_a_mais_ou_a_menos_no_espelho_quebra_o_check_e_o_regen_corrige(checkout):
    (checkout / "skills" / "deep-news" / "sobrou.md").write_text("x", encoding="utf-8")
    (checkout / "skills" / "skill-fantasma").mkdir()
    (checkout / "skills" / "skill-fantasma" / "SKILL.md").write_text("x", encoding="utf-8")
    (checkout / "skills" / "deep-product" / "SKILL.md").unlink()
    r = _roda(checkout, "--check")
    assert r.returncode == 1
    saida = r.stdout + r.stderr
    for rel in ("skills/deep-news/sobrou.md", "skills/skill-fantasma/SKILL.md", "skills/deep-product/SKILL.md"):
        assert rel in saida, rel
    assert _roda(checkout).returncode == 0
    assert _tudo(checkout) == _tudo(ROOT)
    assert not (checkout / "skills" / "skill-fantasma").exists(), "a pasta que o pacote não leva some do espelho"


def test_skill_inteira_faltando_no_espelho_e_recriada(checkout):
    shutil.rmtree(checkout / "skills" / "simplicio-video-edit")
    assert _roda(checkout, "--check").returncode == 1
    assert _roda(checkout).returncode == 0
    assert _tudo(checkout) == _tudo(ROOT)


def test_o_check_nunca_escreve(checkout):
    (checkout / "skills" / "deep-service" / "SKILL.md").write_text("editado a mao", encoding="utf-8")
    ignore = checkout / ".gitignore"
    ignore.write_text(ignore.read_text(encoding="utf-8").replace(".claude/skills/deep-product/\n", ""), encoding="utf-8")
    antes = _tudo(checkout)
    assert _roda(checkout, "--check").returncode == 1
    assert _tudo(checkout) == antes


def test_o_regen_em_checkout_em_dia_nao_reescreve_nenhum_arquivo(checkout):
    marcas = {p: p.stat().st_mtime_ns for p in sorted((checkout / "skills").rglob("*")) if p.is_file()}
    marcas[checkout / ".gitignore"] = (checkout / ".gitignore").stat().st_mtime_ns
    assert _roda(checkout).returncode == 0
    assert marcas == {p: p.stat().st_mtime_ns for p in marcas}


def test_bloco_do_gitignore_desatualizado_quebra_o_check_e_o_regen_reescreve(checkout):
    ignore = checkout / ".gitignore"
    certo = ignore.read_text(encoding="utf-8")
    ignore.write_text(certo.replace(".claude/skills/deep-product/\n", "").replace(INICIO, INICIO + "\n.claude/skills/velha/"), encoding="utf-8")
    r = _roda(checkout, "--check")
    assert r.returncode == 1 and ".gitignore" in r.stdout + r.stderr
    assert _roda(checkout).returncode == 0
    assert ignore.read_text(encoding="utf-8") == certo


def test_o_bloco_do_gitignore_sai_de_skill_sync_skills(checkout):
    """The names come from `skill_sync.SKILLS`, not from a list in the script."""
    modulo = checkout / "src" / "simplicio_video" / "skill_sync.py"
    texto = modulo.read_text(encoding="utf-8")
    assert '"deep-product")' in texto
    modulo.write_text(texto.replace('"deep-service", "deep-product")', '"deep-service", "deep-product", "nova-skill")'), encoding="utf-8")
    nova = checkout / "src" / "simplicio_video" / "data" / "skills" / "nova-skill"
    nova.mkdir()
    (nova / "SKILL.md").write_text("---\nname: nova-skill\n---\n", encoding="utf-8")
    assert _roda(checkout, "--check").returncode == 1
    assert _roda(checkout).returncode == 0
    assert ".claude/skills/nova-skill/" in _bloco((checkout / ".gitignore").read_text(encoding="utf-8"))
    assert (checkout / "skills" / "nova-skill" / "SKILL.md").is_file()


def test_pasta_no_pacote_que_o_skill_sync_nao_lista_e_erro_de_estrutura(checkout):
    """A skill in data/skills/ that is not in SKILLS would be mirrored but never installed or ignored: stop, do not guess."""
    extra = checkout / "src" / "simplicio_video" / "data" / "skills" / "fora-da-lista"
    extra.mkdir()
    (extra / "SKILL.md").write_text("x", encoding="utf-8")
    for args in (("--check",), ()):
        r = _roda(checkout, *args)
        assert r.returncode == 2, (args, r.stdout, r.stderr)
        assert "fora-da-lista" in r.stdout + r.stderr
    assert not (checkout / "skills" / "fora-da-lista").exists()


def test_gitignore_sem_o_bloco_e_erro_de_estrutura_e_nada_e_escrito(checkout):
    ignore = checkout / ".gitignore"
    ignore.write_text("\n".join(l for l in ignore.read_text(encoding="utf-8").splitlines() if not l.startswith(("# BEGIN GENERATED skills", "# END GENERATED skills"))) + "\n", encoding="utf-8")
    (checkout / "skills" / "deep-news" / "SKILL.md").write_text("editado a mao", encoding="utf-8")
    antes = _tudo(checkout)
    for args in (("--check",), ()):
        r = _roda(checkout, *args)
        assert r.returncode == 2 and "GENERATED skills" in r.stdout + r.stderr, (args, r.stdout, r.stderr)
    assert _tudo(checkout) == antes


def test_o_make_docs_confere_e_o_make_regen_regera():
    make = shutil.which("make")
    if make is None:
        pytest.skip("make não instalado")
    docs, regen = _make("docs"), _make("regen")
    assert docs.returncode == 0 and regen.returncode == 0, (docs.stderr, regen.stderr)
    assert [l for l in docs.stdout.splitlines() if "scripts/sync_skills.py" in l and l.endswith("--check")], docs.stdout
    sem_flag = [l for l in regen.stdout.splitlines() if "scripts/sync_skills.py" in l and "--check" not in l]
    assert sem_flag, regen.stdout
