"""`simplicio_video.skill_sync`: which hosts ALREADY hold a copy of the skills, and whether that copy differs from the package.

Ported from simplicio-loop (`simplicio_loop/skill_sync.py`, 2034e2d) for the video skills, with one deliberate difference (review of
PR #117, ADR-0020): the loop REFRESHES those copies and deletes the files that left the package; this module only REPORTS them.
Nothing here writes: a copy in `~/.codex/skills` or `~/.cursor/skills` is not in the ownership receipt, so it is not ours to overwrite
or to delete (the review measured `minhas-notas.md` disappearing from two hosts, and `update` did it by itself through
`install --global`). Every folder below is under tmp_path: the real home is never read.
"""
from __future__ import annotations

import pytest

import _caixa
from _caixa import SISTEMAS, posix_real, skill_sync
from _comum import fotografia, write

caixa = _caixa.caixa
simula_so = _caixa.simula_so

# host -> where it keeps its skills under the home: the table of simplicio-loop (skill_sync.py), the same on all three systems
RAIZES_DO_LOOP = {
    "claude": ".claude/skills", "cursor": ".cursor/skills", "codex": ".codex/skills", "grok": ".grok/skills",
    "agents": ".agents/skills", "copilot": ".copilot/skills", "vscode": ".vscode/simplicio-skills",
    "opencode": ".config/opencode/skills", "amp": ".config/amp/skills", "kiro": ".kiro/steering",
    "simplicio_agent": ".simplicio-loop/skills",  # the folder the loop defines for that host
}


@pytest.fixture
def casa(tmp_path):
    pasta = tmp_path / "casa"
    pasta.mkdir()
    return pasta


@pytest.fixture
def pacote(tmp_path):
    """A fake package skills folder: two skills, one with a nested file."""
    raiz = tmp_path / "pacote" / "skills"
    write(raiz / "simplicio-video" / "SKILL.md", "video v2\n")
    write(raiz / "simplicio-video" / "references" / "a.md", "ref a\n")
    write(raiz / "simplicio-video-social" / "SKILL.md", "social v2\n")
    return raiz


def instala_como_o_host(casa, host, pacote, *, velhas=()):
    raiz = casa / skill_sync.HOST_SKILL_ROOTS[host]
    for nome in ("simplicio-video", "simplicio-video-social"):
        for arquivo in (pacote / nome).rglob("*"):
            if arquivo.is_file():
                write(raiz / nome / arquivo.relative_to(pacote / nome), arquivo.read_text(encoding="utf-8"))
    for nome in velhas:
        write(raiz / nome / "SKILL.md", "release antiga\n")
        write(raiz / nome / "removida-no-pacote.md", "sumiu do pacote\n")
    return raiz


def test_as_skills_sao_as_do_simplicio_video():
    assert skill_sync.SKILLS == ("simplicio-video", "simplicio-video-social")


def test_a_tabela_de_hosts_e_a_do_loop():
    assert skill_sync.HOST_SKILL_ROOTS == RAIZES_DO_LOOP


def test_o_pacote_tem_cada_skill_com_skill_md():
    pasta = skill_sync.package_skills_dir()
    for nome in skill_sync.SKILLS:
        assert pasta.joinpath(nome, "SKILL.md").is_file(), nome


def test_o_digest_depende_do_conteudo_e_do_caminho(tmp_path):
    a = tmp_path / "a"
    write(a / "SKILL.md", "v1")
    d1 = skill_sync.skill_digest(a)
    assert d1 == skill_sync.skill_digest(a) and len(d1) == 64
    write(a / "SKILL.md", "v2")
    assert skill_sync.skill_digest(a) != d1
    b = tmp_path / "b"
    write(b / "OUTRO.md", "v2")
    assert skill_sync.skill_digest(b) != skill_sync.skill_digest(a)
    assert skill_sync.skill_digest(tmp_path / "ausente") == ""


def test_o_digest_ignora_o_cache_de_bytecode(tmp_path):
    a = tmp_path / "a"
    write(a / "SKILL.md", "v1")
    antes = skill_sync.skill_digest(a)
    (a / "__pycache__").mkdir()
    (a / "__pycache__" / "x.pyc").write_bytes(b"\0")
    assert skill_sync.skill_digest(a) == antes


def test_o_digest_funciona_com_uma_pasta_do_pacote_e_com_uma_pasta_do_host(tmp_path, pacote):
    copia = tmp_path / "copia"
    for arquivo in (pacote / "simplicio-video").rglob("*"):
        if arquivo.is_file():
            write(copia / arquivo.relative_to(pacote / "simplicio-video"), arquivo.read_text(encoding="utf-8"))
    assert skill_sync.skill_digest(copia) == skill_sync.skill_digest(pacote / "simplicio-video")


@pytest.mark.parametrize("host,rel", sorted(RAIZES_DO_LOOP.items()))
def test_so_conta_o_host_que_ja_tem_a_skill_do_video(casa, pacote, host, rel):
    assert skill_sync.installed_skill_hosts(casa) == {}
    raiz = instala_como_o_host(casa, host, pacote)
    assert raiz == casa / rel
    assert skill_sync.installed_skill_hosts(casa) == {host: raiz}


@pytest.mark.parametrize("host,rel", [("claude", ".claude/skills"), ("cursor", ".cursor/skills"), ("grok", ".grok/skills"),
                                      ("vscode", ".vscode/simplicio-skills"), ("opencode", ".config/opencode/skills")])
def test_a_skill_velha_e_apontada_conforme_o_layout_de_cada_host_e_nada_e_escrito(casa, pacote, host, rel):
    raiz = instala_como_o_host(casa, host, pacote, velhas=["simplicio-video"])
    antes = fotografia(casa)
    assert [(e["host"], e["skill"], e["reason"]) for e in skill_sync.stale_skills(casa, source=pacote)] == [
        (host, "simplicio-video", "stale")]
    assert fotografia(casa) == antes, "reporting a stale copy must not touch it"
    assert (raiz / "simplicio-video" / "SKILL.md").read_text(encoding="utf-8") == "release antiga\n"


def test_este_modulo_so_le_nao_tem_funcao_que_escreva_nas_copias_dos_hosts():
    assert not hasattr(skill_sync, "resync_installed_skills"), "the copies of other hosts are not ours to overwrite or delete"


def test_o_host_que_tem_so_uma_das_skills_aparece_com_a_que_falta_como_missing(casa, pacote):
    write(casa / ".claude" / "skills" / "simplicio-video" / "SKILL.md", "video v2\n")
    write(casa / ".claude" / "skills" / "simplicio-video" / "references" / "a.md", "ref a\n")
    assert [(e["skill"], e["reason"]) for e in skill_sync.stale_skills(casa, source=pacote)] == [("simplicio-video-social", "missing")]


def test_o_host_que_nunca_instalou_nao_aparece(casa, pacote):
    write(casa / ".claude" / "skills" / "minha-skill" / "SKILL.md", "minha\n")
    antes = fotografia(casa)
    assert skill_sync.stale_skills(casa, source=pacote) == []
    assert fotografia(casa) == antes


def test_a_copia_em_dia_nao_aparece(casa, pacote):
    instala_como_o_host(casa, "codex", pacote)
    assert skill_sync.stale_skills(casa, source=pacote) == []


@posix_real
def test_a_skill_do_host_que_e_link_simbolico_nao_e_julgada(tmp_path, casa, pacote):
    clone = tmp_path / "clone" / "simplicio-video"
    write(clone / "SKILL.md", "do clone\n")
    (casa / ".codex" / "skills").mkdir(parents=True)
    (casa / ".codex" / "skills" / "simplicio-video").symlink_to(clone, target_is_directory=True)
    assert [e for e in skill_sync.stale_skills(casa, source=pacote) if e["skill"] == "simplicio-video"] == []
    assert (clone / "SKILL.md").read_text(encoding="utf-8") == "do clone\n"


@pytest.mark.parametrize("so", SISTEMAS)
def test_a_pasta_pessoal_vem_de_home_e_depois_de_userprofile_em_todo_sistema(tmp_path, simula_so, monkeypatch, so):
    simula_so(so)
    a, b = tmp_path / "a", tmp_path / "b"
    monkeypatch.setenv("HOME", str(a))
    monkeypatch.setenv("USERPROFILE", str(b))
    assert skill_sync.default_home() == a
    monkeypatch.delenv("HOME")
    assert skill_sync.default_home() == b
    monkeypatch.setenv("HOME", "  ")
    assert skill_sync.default_home() == b, "a blank HOME is skipped"


@pytest.mark.parametrize("so", SISTEMAS)
def test_sem_argumento_le_a_pasta_pessoal_do_ambiente(caixa, pacote, simula_so, so):
    simula_so(so)
    instala_como_o_host(caixa.home, "cursor", pacote, velhas=["simplicio-video"])
    assert [e["host"] for e in skill_sync.stale_skills(source=pacote)] == ["cursor"]
