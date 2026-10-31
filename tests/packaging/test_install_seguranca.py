"""Review of PR #117 (head 2e3d95c): what `install`, `--uninstall` and `--prune-project-copies` may touch, and what `--verify` promises.

The review measured, with nothing hostile involved, that the first install overwrote a customized SKILL.md, that the uninstall
deleted an AGENTS.md the user had written rules in, that an install over a receipt planted in a cloned repo inherited its paths,
that a link above the skill folder was written through (and made the uninstall fail for ever), that `--verify` said ok for a
target never installed, and that three installs at once left entry files out of the receipt.

The rules these tests pin (ADR-0020):

* the receipt keeps the sha256 of every file it registers; a file is deleted (or overwritten by a later install) only when it
  is in the receipt AND its sha256 still matches what was written: an edited file is `left_alone`, with a warning;
* a path in the receipt must be one that the registry (hosts x skills) can produce: the skill folders, the entry files of the
  hosts and the receipt itself. Anything else (`.git/config`, `src/app.py`, `.ssh/authorized_keys`, a NUL, a huge string) makes
  the uninstall and the prune refuse the whole receipt, and an install over it ignores it, with a warning;
* the folders the install CREATES (`skills`, `simplicio-video`, `.simplicio-video`) are never links (refused, exit 2, nothing
  written); the host base folder (`~/.claude`) may be one (dotfiles): it is resolved once and recorded in the receipt;
* `--verify` compares the files with the receipt and with the package and fails (exit 1, `ok: false`, the list of what differs);
* a file that was already there before the first install is never overwritten and never becomes "ours";
* installs in the same target at the same time are serialized by `.simplicio-video/install.lock`.

Everything runs in tmp_path. Tests that need real symlinks or flock are marked `posix_real`.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest

import _caixa
from _caixa import installer, posix_real, roda_com_prazo, solta_fifo
from _comum import fotografia, make_bundle, write
from simplicio_video import __version__

caixa = _caixa.caixa

RECIBO = ".simplicio-video/install-ownership.json"
TRAVA = ".simplicio-video/install.lock"
SKILL = ".claude/skills/simplicio-video/SKILL.md"
REF = ".claude/skills/simplicio-video/references/a.md"
ENTRADAS = {"codex": "AGENTS.md", "gemini": "GEMINI.md", "aider": "CONVENTIONS.md", "vscode": ".github/copilot-instructions.md",
            "kiro": ".kiro/steering/simplicio-video.md"}


@pytest.fixture
def bundle(tmp_path):
    return make_bundle(tmp_path / "bundle")


@pytest.fixture
def repo(tmp_path):
    alvo = tmp_path / "repo"
    alvo.mkdir()
    return alvo


def instala(raiz, bundle, *, host="claude", globally=False, dry_run=False):
    return installer.apply_plan(installer.plan_install(raiz, host=host, globally=globally), bundle=bundle, dry_run=dry_run)


def sha(texto: str | bytes) -> str:
    return hashlib.sha256(texto.encode("utf-8") if isinstance(texto, str) else texto).hexdigest()


def recibo_de(raiz) -> dict:
    return json.loads((raiz / RECIBO).read_text(encoding="utf-8"))


def grava_recibo(raiz, **mudancas) -> None:
    recibo = recibo_de(raiz)
    recibo.update(mudancas)
    (raiz / RECIBO).write_text(json.dumps(recibo), encoding="utf-8")


def planta_recibo(raiz, caminhos, dirs=()) -> None:
    """A receipt that looks right (owner, schema) and lists `caminhos` with the REAL sha256 of what is on disk."""
    digestos = {rel: sha((raiz / rel).read_bytes()) for rel in caminhos if (raiz / rel).is_file()}
    write(raiz / RECIBO, json.dumps({"schema": installer.OWNERSHIP_SCHEMA, "owner": "simplicio-video", "version": "0.0.1",
                                     "digest": "sha256:" + "0" * 64, "paths": list(caminhos), "dirs": list(dirs),
                                     "sha256": digestos}))


# --- the receipt keeps the sha256 of every file it registers ---------------------------------------------------------------------


def test_o_recibo_guarda_o_sha256_de_cada_arquivo_que_registra(repo, bundle):
    instala(repo, bundle, host="codex")
    recibo = recibo_de(repo)
    assert set(recibo["sha256"]) == set(recibo["paths"]) and {SKILL, REF, "AGENTS.md"} <= set(recibo["paths"])
    for rel in recibo["paths"]:
        assert recibo["sha256"][rel] == sha((repo / rel).read_bytes()), rel
    assert RECIBO not in recibo["paths"], "the receipt cannot hold its own digest"


def test_o_recibo_so_tem_bases_quando_uma_pasta_base_e_link(repo, bundle):
    instala(repo, bundle)
    assert set(recibo_de(repo)) == {"schema", "owner", "version", "digest", "paths", "dirs", "sha256"}


# --- the uninstall deletes only what still has the digest it wrote ------------------------------------------------------------------


@pytest.mark.parametrize("host,entrada", sorted(ENTRADAS.items()))
def test_uninstall_nao_apaga_o_arquivo_de_entrada_em_que_o_usuario_escreveu(repo, bundle, host, entrada):
    instala(repo, bundle, host=host)
    caminho = repo / entrada
    caminho.write_text(caminho.read_text(encoding="utf-8") + "\n# as minhas regras\nnunca force push\n", encoding="utf-8")
    resultado = installer.uninstall(repo)
    assert "as minhas regras" in caminho.read_text(encoding="utf-8"), f"the uninstall deleted the user's {entrada}"
    assert entrada in resultado["left_alone"] and entrada not in resultado["removed"]
    assert any(entrada in aviso for aviso in resultado["warnings"]), resultado["warnings"]
    assert not (repo / SKILL).exists() and not (repo / RECIBO).exists()


def test_uninstall_nao_apaga_a_skill_que_o_usuario_editou(repo, bundle):
    instala(repo, bundle)
    (repo / SKILL).write_text("a minha versão\n", encoding="utf-8")
    resultado = installer.uninstall(repo)
    assert (repo / SKILL).read_text(encoding="utf-8") == "a minha versão\n"
    assert SKILL in resultado["left_alone"] and SKILL not in resultado["removed"] and REF in resultado["removed"]
    assert ".claude/skills/simplicio-video" in resultado["kept"], "the folder holds a file that is not ours any more"
    assert not (repo / RECIBO).exists()


def test_uninstall_dry_run_diz_o_que_deixaria_e_nao_apaga_nada(repo, bundle):
    instala(repo, bundle, host="codex")
    (repo / "AGENTS.md").write_text("meu\n", encoding="utf-8")
    antes = fotografia(repo)
    resultado = installer.uninstall(repo, dry_run=True)
    assert resultado["status"] == "dry_run" and resultado["left_alone"] == ["AGENTS.md"] and fotografia(repo) == antes


def test_recibo_sem_sha256_e_invalido_e_a_mensagem_nao_diz_que_o_usuario_editou(repo, bundle):
    """A receipt of the 2e3d95c build (it never shipped) has no `sha256` and the same id: it is read safely, nothing is deleted, and
    the message says what is true (the receipt is from a version without digests), not "edited"."""
    instala(repo, bundle, host="codex")
    recibo = recibo_de(repo)
    del recibo["sha256"]
    (repo / RECIBO).write_text(json.dumps(recibo), encoding="utf-8")
    antes = fotografia(repo)
    for dry in (True, False):
        with pytest.raises(installer.InstallError, match="sha256") as erro:
            installer.uninstall(repo, dry_run=dry)
        assert "editado" not in str(erro.value) and "versão sem" in str(erro.value), str(erro.value)
    assert fotografia(repo) == antes, "a receipt that cannot be trusted removes nothing, not even itself"
    verificado = installer.verify_install(installer.plan_install(repo, host="codex"), bundle=bundle)
    assert (RECIBO, "bad_receipt") in _problemas(verificado) and "sha256" in verificado["problems"][0]["detail"]
    resultado = instala(repo, bundle, host="codex")  # an install over it ignores it, says why, and writes a new one
    assert any("sha256" in aviso for aviso in resultado["warnings"]) and "sha256" in recibo_de(repo)


def test_um_caminho_sem_sha256_no_recibo_fica_em_paz_com_a_mensagem_verdadeira(repo, bundle):
    instala(repo, bundle)
    recibo = recibo_de(repo)
    del recibo["sha256"][SKILL]
    (repo / RECIBO).write_text(json.dumps(recibo), encoding="utf-8")
    resultado = installer.uninstall(repo)
    assert (repo / SKILL).is_file() and SKILL in resultado["left_alone"] and REF in resultado["removed"]
    aviso = next(a for a in resultado["warnings"] if a.startswith(SKILL))
    assert "sha256" in aviso and "editado" not in aviso, aviso


def test_reinstalar_depois_de_editar_a_entrada_a_tira_do_recibo(repo, bundle):
    instala(repo, bundle, host="codex")
    (repo / "AGENTS.md").write_text("# agora é meu\n", encoding="utf-8")
    segunda = instala(repo, bundle, host="codex")
    assert "AGENTS.md" in segunda["changes"]["left_alone"] and "AGENTS.md" not in segunda["owned"]
    assert "AGENTS.md" not in recibo_de(repo)["paths"] and "AGENTS.md" not in recibo_de(repo)["sha256"]
    installer.uninstall(repo)
    assert (repo / "AGENTS.md").read_text(encoding="utf-8") == "# agora é meu\n"


def test_o_arquivo_de_entrada_de_outro_host_continua_no_recibo_ao_instalar_um_segundo_host(repo, bundle):
    instala(repo, bundle, host="codex")
    instala(repo, bundle, host="gemini")
    recibo = recibo_de(repo)
    assert {"AGENTS.md", "GEMINI.md"} <= set(recibo["paths"]) and set(recibo["sha256"]) == set(recibo["paths"])
    installer.uninstall(repo)
    assert fotografia(repo) == {}


# --- a receipt names only what the registry can produce ----------------------------------------------------------------------------


CAMINHOS_ALHEIOS = [
    ".git/config", "src/app.py", "notes.md", ".ssh/authorized_keys", ".claude/settings.json", ".github/workflows/ci.yml",
    ".claude/skills/minha-skill/SKILL.md", ".claude/skills/simplicio-video-evil/SKILL.md", ".simplicio-video/outro.json",
    "AGENTS.md.bak", ".kiro/steering/minha-regra.md",
]


def _vitimas(raiz) -> list:
    return [write(raiz / rel, f"do usuário: {rel}\n") for rel in CAMINHOS_ALHEIOS]


@pytest.mark.parametrize("rel", CAMINHOS_ALHEIOS)
def test_recibo_plantado_num_repo_clonado_nao_apaga_nada_no_uninstall(repo, bundle, rel):
    vitima = write(repo / rel, "do repositório\n")
    instala(repo, bundle)
    antes = fotografia(repo)
    planta_recibo(repo, [rel, SKILL])
    with pytest.raises(installer.InstallError, match="recibo"):
        installer.uninstall(repo)
    with pytest.raises(installer.InstallError, match="recibo"):
        installer.uninstall(repo, dry_run=True)
    assert vitima.read_text(encoding="utf-8") == "do repositório\n"
    assert fotografia(repo) == {**antes, RECIBO: fotografia(repo)[RECIBO]}, "a refused receipt leaves everything where it was"


def test_o_recibo_plantado_com_varios_caminhos_do_repo_nao_apaga_arquivo_nem_pasta(repo, bundle):
    vitimas = _vitimas(repo)
    planta_recibo(repo, [".git/config", "src/app.py", "notes.md"], dirs=["src", ".git"])
    with pytest.raises(installer.InstallError):
        installer.uninstall(repo)
    assert all(v.is_file() for v in vitimas) and (repo / "src").is_dir() and (repo / ".git").is_dir()


@pytest.mark.parametrize("rel", ["src/app.py", ".git/config", "notes.md"])
def test_prune_recusa_o_recibo_plantado_e_nao_apaga_nada(repo, bundle, rel):
    vitima = write(repo / rel, "do repositório\n")
    planta_recibo(repo, [rel])
    with pytest.raises(installer.InstallError):
        installer.prune_project_copies(repo)
    assert vitima.read_text(encoding="utf-8") == "do repositório\n"


def test_um_install_normal_por_cima_de_um_recibo_plantado_nao_herda_os_caminhos_dele(repo, bundle):
    vitima = write(repo / "notes.md", "do repositório\n")
    planta_recibo(repo, ["notes.md", ".git/config"])
    resultado = instala(repo, bundle)
    assert "notes.md" not in recibo_de(repo)["paths"] and ".git/config" not in recibo_de(repo)["paths"]
    assert "notes.md" not in resultado["owned"]
    assert resultado["warnings"] and any("recibo" in aviso for aviso in resultado["warnings"]), resultado["warnings"]
    installer.uninstall(repo)
    assert vitima.read_text(encoding="utf-8") == "do repositório\n"
    assert not (repo / SKILL).exists(), "what this install wrote is still removed"


def test_um_recibo_no_home_com_authorized_keys_nao_apaga_a_chave_no_install_global(tmp_path, bundle):
    casa = tmp_path / "casa"
    chave = write(casa / ".ssh" / "authorized_keys", "ssh-ed25519 AAAA fake\n")
    instala(casa, bundle, globally=True)
    planta_recibo(casa, [".ssh/authorized_keys", SKILL], dirs=[".ssh"])
    with pytest.raises(installer.InstallError):
        installer.uninstall(casa)
    assert chave.read_text(encoding="utf-8") == "ssh-ed25519 AAAA fake\n" and (casa / SKILL).is_file()


@pytest.mark.parametrize("rel", ["a\u0000b/c", "x" * 5000, "a/" * 300 + "b.md", ".claude/skills/simplicio-video/\u0000", "\u0000"])
def test_caminho_com_nul_ou_gigante_no_recibo_vira_erro_claro_e_nunca_traceback(repo, bundle, rel):
    instala(repo, bundle)
    grava_recibo(repo, paths=[rel])
    with pytest.raises(installer.InstallError):
        installer.uninstall(repo)
    with pytest.raises(installer.InstallError):
        installer.prune_project_copies(repo)
    resultado = instala(repo, bundle)  # an install ignores such a receipt, with a warning
    assert resultado["warnings"] and rel not in recibo_de(repo)["paths"]


def test_so_os_destinos_do_registro_valem_no_recibo():
    certos = [SKILL, REF, ".codex/skills/simplicio-video/SKILL.md", ".config/opencode/skills/simplicio-video-social/references/a.md",
              ".kiro/steering/simplicio-video/SKILL.md", ".claude/skills/simplicio-video-social/SKILL.md", ".claude/skills/simplicio-video/a/b/c.md", "AGENTS.md",
              "GEMINI.md", "CONVENTIONS.md", ".github/copilot-instructions.md", ".kiro/steering/simplicio-video.md", RECIBO]
    errados = ["", ".", "..", "/etc/passwd", "../x", ".claude", ".claude/skills", ".claude/skills/simplicio-video", ".config/git/config",
               ".codex/config.toml", ".cursor/rules/x.mdc", ".config/opencode/skills/minha-skill/SKILL.md",
               ".claude/skills/simplicio-video/", ".claude/skills/simplicio-video/../../../x", ".claude/skills/simplicio-video-x/a",
               ".claude/skills/simplicio-video/a:b", ".claude/skills/simplicio-video\\a.md", "C:/x", "AGENTS.md/x", "agents.md",
               ".simplicio-video/install.lock", ".simplicio-video", ".git/config", 7, None, "a\u0000"]
    for rel in certos:
        assert installer.known_file(rel), rel
    for rel in errados:
        assert not installer.known_file(rel), rel
    for rel in (".claude", ".claude/skills", ".claude/skills/simplicio-video", ".claude/skills/simplicio-video/references", ".github",
                ".kiro", ".kiro/steering", ".simplicio-video", ".cursor", ".cursor/skills", ".config", ".config/opencode",
                ".config/opencode/skills/simplicio-video-social", ".simplicio-loop/skills/simplicio-video"):
        assert installer.known_dir(rel), rel
    for rel in ("", ".", "..", "src", ".git", ".ssh", ".claude/rules", ".claude/skills/minha-skill", ".cursor/rules", ".config/git",
                ".config/opencode/skills/minha-skill", "a/../b", None):
        assert not installer.known_dir(rel), rel


# --- a file that was already there is never overwritten and never becomes ours ------------------------------------------------------


def test_o_primeiro_install_nao_sobrescreve_um_skill_md_customizado(repo, bundle):
    custom = write(repo / SKILL, "a minha skill customizada\n")
    resultado = instala(repo, bundle)
    assert custom.read_text(encoding="utf-8") == "a minha skill customizada\n"
    assert SKILL in resultado["changes"]["left_alone"] and SKILL not in resultado["owned"]
    assert SKILL not in resultado["changes"]["updated"] and REF in resultado["changes"]["created"]
    assert SKILL not in recibo_de(repo)["paths"]
    installer.uninstall(repo)
    assert custom.read_text(encoding="utf-8") == "a minha skill customizada\n" and not (repo / REF).exists()


def test_uma_copia_identica_do_usuario_nao_vira_propria_e_o_uninstall_nao_a_apaga(repo, bundle):
    copia = write(repo / SKILL, "video\n")  # exactly what the bundle holds
    resultado = instala(repo, bundle)
    assert resultado["changes"]["unchanged"] >= 1 and SKILL not in resultado["owned"] and SKILL not in recibo_de(repo)["paths"]
    assert SKILL not in resultado["changes"]["left_alone"], "it is identical: nothing to say"
    installer.uninstall(repo)
    assert copia.read_text(encoding="utf-8") == "video\n", "the user's own copy was deleted by the uninstall"


def test_a_skill_editada_depois_do_install_nao_e_atualizada_quando_o_pacote_muda(repo, bundle):
    instala(repo, bundle)
    (repo / SKILL).write_text("a minha versão\n", encoding="utf-8")
    (bundle / "skills" / "simplicio-video" / "SKILL.md").write_text("video v2\n", encoding="utf-8")
    resultado = instala(repo, bundle)
    assert (repo / SKILL).read_text(encoding="utf-8") == "a minha versão\n"
    assert SKILL in resultado["changes"]["left_alone"] and SKILL not in resultado["changes"]["updated"]
    assert SKILL not in recibo_de(repo)["paths"], "an edited file is the user's, so it leaves the receipt"


def test_a_skill_nossa_e_intacta_continua_sendo_atualizada(repo, bundle):
    instala(repo, bundle)
    (bundle / "skills" / "simplicio-video" / "SKILL.md").write_text("video v2\n", encoding="utf-8")
    resultado = instala(repo, bundle)
    assert resultado["changes"]["updated"] == [SKILL, RECIBO] and (repo / SKILL).read_text(encoding="utf-8") == "video v2\n"
    assert recibo_de(repo)["sha256"][SKILL] == sha("video v2\n")


def test_arquivos_do_usuario_dentro_da_pasta_da_skill_ficam_intactos_e_sao_relatados(repo, bundle):
    instala(repo, bundle)
    notas = write(repo / ".claude" / "skills" / "simplicio-video" / "minhas-notas.md", "notas\n")
    (bundle / "skills" / "simplicio-video" / "SKILL.md").write_text("video v2\n", encoding="utf-8")
    resultado = instala(repo, bundle)
    assert notas.read_text(encoding="utf-8") == "notas\n"
    assert ".claude/skills/simplicio-video/minhas-notas.md" in resultado["changes"]["left_alone"]
    installer.uninstall(repo)
    assert notas.is_file(), "the uninstall keeps the user's notes too"


# --- links ---------------------------------------------------------------------------------------------------------------------------


@posix_real
@pytest.mark.parametrize("onde", [".claude/skills", ".claude/skills/simplicio-video", ".claude/skills/simplicio-video/references",
                                  ".simplicio-video"])
def test_pasta_que_o_install_cria_e_link_e_recusada_e_nada_e_escrito(tmp_path, repo, bundle, onde):
    fora = tmp_path / "dotfiles"
    fora.mkdir()
    link = repo / onde
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(fora, target_is_directory=True)
    antes = fotografia(repo)
    for dry in (True, False):
        with pytest.raises(installer.InstallRefused, match="link"):
            instala(repo, bundle, dry_run=dry)
    assert fotografia(fora) == {} and fotografia(repo) == antes, "nothing was written, through the link or beside it"
    assert issubclass(installer.InstallRefused, installer.InstallError)


@posix_real
def test_pasta_base_que_aponta_para_um_arquivo_ou_nao_existe_e_recusada(tmp_path, repo, bundle):
    arquivo = write(tmp_path / "arquivo", "x\n")
    (repo / ".claude").symlink_to(arquivo)
    with pytest.raises(installer.InstallRefused):
        instala(repo, bundle)
    (repo / ".claude").unlink()
    (repo / ".claude").symlink_to(tmp_path / "nao-existe")
    with pytest.raises(installer.InstallRefused):
        instala(repo, bundle)
    assert arquivo.read_text(encoding="utf-8") == "x\n"


@posix_real
@pytest.mark.parametrize("escopo", ["projeto", "global"])
def test_a_pasta_base_pode_ser_link_de_dotfiles_e_o_ciclo_install_verify_uninstall_fecha(tmp_path, repo, bundle, escopo):
    raiz = repo
    dotfiles = tmp_path / "dotfiles" / "claude"
    dotfiles.mkdir(parents=True)
    write(dotfiles / "settings.json", "{}\n")
    (raiz / ".claude").symlink_to(dotfiles, target_is_directory=True)
    plano = installer.plan_install(raiz, host="claude", globally=escopo == "global")
    resultado = installer.apply_plan(plano, bundle=bundle)
    assert (dotfiles / "skills" / "simplicio-video" / "SKILL.md").read_text(encoding="utf-8") == "video\n"
    recibo = recibo_de(raiz)
    assert recibo["bases"] == {".claude": str(dotfiles.resolve())}, "the resolved path of the base is in the receipt"
    assert ".claude" not in recibo["dirs"], "the base folder is the user's: the install did not create it"
    assert resultado["up_to_date"] is False
    assert installer.apply_plan(plano, bundle=bundle)["up_to_date"] is True
    assert installer.verify_install(plano, bundle=bundle)["ok"] is True
    removido = installer.uninstall(raiz)
    assert SKILL in removido["removed"]
    assert fotografia(dotfiles) == {"settings.json": "{}\n"}, "everything the install put under the link is gone, the rest stays"
    assert (raiz / ".claude").is_symlink() and not (raiz / ".simplicio-video").exists()


@posix_real
def test_o_link_da_pasta_base_que_mudou_depois_do_install_faz_o_uninstall_recusar(tmp_path, repo, bundle):
    um, dois = tmp_path / "um", tmp_path / "dois"
    for pasta in (um, dois):
        pasta.mkdir()
    (repo / ".claude").symlink_to(um, target_is_directory=True)
    instala(repo, bundle)
    (repo / ".claude").unlink()
    (repo / ".claude").symlink_to(dois, target_is_directory=True)
    write(dois / "skills" / "simplicio-video" / "SKILL.md", "outro\n")
    with pytest.raises(installer.InstallError, match="link"):
        installer.uninstall(repo)
    assert (dois / "skills" / "simplicio-video" / "SKILL.md").read_text(encoding="utf-8") == "outro\n"
    assert (um / "skills" / "simplicio-video" / "SKILL.md").is_file()


@posix_real
def test_recibo_com_bases_adulterado_nao_leva_o_uninstall_para_fora(tmp_path, repo, bundle):
    fora = tmp_path / "fora"
    chave = write(fora / "skills" / "simplicio-video" / "SKILL.md", "do usuário\n")
    instala(repo, bundle)
    grava_recibo(repo, bases={".claude": str(fora)})
    with pytest.raises(installer.InstallError):
        installer.uninstall(repo)
    assert chave.read_text(encoding="utf-8") == "do usuário\n" and (repo / SKILL).is_file()


def _lstat_de(monkeypatch, caminho, *, atributos, tag="ausente"):
    """Make `os.lstat(caminho)` look like a Windows folder with these file attributes (and reparse tag, when there is one)."""
    real = os.lstat
    alvo = os.fspath(caminho)

    def falso(p, *a, **kw):
        if os.fspath(p) == alvo:
            info = SimpleNamespace(st_mode=stat.S_IFDIR | 0o755, st_file_attributes=atributos)
            if tag != "ausente":
                info.st_reparse_tag = tag
            return info
        return real(p, *a, **kw)

    monkeypatch.setattr(os, "lstat", falso)


REPARSE = 0x400


@pytest.mark.parametrize("atributos,tag,link", [
    (REPARSE, 0xA0000003, True),    # IO_REPARSE_TAG_MOUNT_POINT: an NTFS junction
    (REPARSE, 0xA000000C, True),    # IO_REPARSE_TAG_SYMLINK
    (REPARSE, "ausente", True),     # a Python that gives the attributes and not the tag: a reparse point is not trusted
    (REPARSE, 0x9000001A, False),   # a OneDrive placeholder is a real folder
    (0x10, 0xA0000003, False),      # a plain directory (FILE_ATTRIBUTE_DIRECTORY only)
])
def test_juncao_ntfs_vale_como_link_sem_os_path_isjunction(tmp_path, monkeypatch, atributos, tag, link):
    """Python 3.10 and 3.11 on Windows have no `os.path.isjunction`: the reparse attribute and tag of `lstat` decide."""
    monkeypatch.delattr(os.path, "isjunction", raising=False)
    pasta = tmp_path / "pasta"
    pasta.mkdir()
    _lstat_de(monkeypatch, pasta, atributos=atributos, tag=tag)
    assert installer.is_link(pasta) is link


def test_uma_juncao_do_windows_na_pasta_da_skill_e_recusada(tmp_path, repo, bundle, monkeypatch):
    monkeypatch.delattr(os.path, "isjunction", raising=False)
    pasta = repo / ".claude" / "skills" / "simplicio-video"
    pasta.mkdir(parents=True)
    _lstat_de(monkeypatch, pasta, atributos=REPARSE, tag=0xA0000003)
    with pytest.raises(installer.InstallRefused):
        instala(repo, bundle)
    assert not (pasta / "SKILL.md").exists(), "nothing was written through the junction"


def test_is_link_nao_levanta_numa_pasta_que_nao_da_para_abrir(tmp_path, monkeypatch):
    def nega(p, *a, **kw):
        raise PermissionError(13, "Permission denied", os.fspath(p))

    monkeypatch.setattr(os, "lstat", nega)
    assert installer.is_link(tmp_path / "x") is False


# --- --verify: it compares the files, with the receipt and with the package -----------------------------------------------------------


def _problemas(resultado) -> dict:
    return {(p["path"], p["problem"]) for p in resultado["problems"]}


def test_verify_de_um_alvo_nunca_instalado_falha(repo, bundle):
    resultado = installer.verify_install(installer.plan_install(repo), bundle=bundle)
    assert resultado["ok"] is False
    assert (RECIBO, "no_receipt") in _problemas(resultado) and (SKILL, "missing") in _problemas(resultado)
    assert fotografia(repo) == {}, "verify writes nothing"


def test_verify_de_uma_instalacao_inteira_passa_e_traz_as_chaves_do_loop(repo, bundle):
    instala(repo, bundle, host="codex")
    plano = installer.plan_install(repo, host="codex")
    resultado = installer.verify_install(plano, bundle=bundle)
    assert resultado == {"ok": True, "version": __version__, "digest": plano["digest"], "problems": []}


def test_verify_pega_a_skill_adulterada(repo, bundle):
    instala(repo, bundle)
    (repo / SKILL).write_text("poste sem confirmar\n", encoding="utf-8")
    resultado = installer.verify_install(installer.plan_install(repo), bundle=bundle)
    assert resultado["ok"] is False and (SKILL, "modified") in _problemas(resultado)


def test_verify_pega_o_arquivo_apagado_e_o_de_entrada_editado(repo, bundle):
    instala(repo, bundle, host="codex")
    (repo / REF).unlink()
    (repo / "AGENTS.md").write_text("outra coisa\n", encoding="utf-8")
    resultado = installer.verify_install(installer.plan_install(repo, host="codex"), bundle=bundle)
    assert {(REF, "missing"), ("AGENTS.md", "modified")} <= _problemas(resultado) and resultado["ok"] is False


def test_verify_diz_outdated_quando_o_pacote_mudou_e_o_install_ainda_nao_rodou(repo, bundle):
    instala(repo, bundle)
    (bundle / "skills" / "simplicio-video" / "SKILL.md").write_text("video v2\n", encoding="utf-8")
    resultado = installer.verify_install(installer.plan_install(repo), bundle=bundle)
    assert resultado["ok"] is False and _problemas(resultado) == {(SKILL, "outdated")}


@pytest.mark.parametrize("lixo", ["{nao json", "", "[1]", "null", '{"owner": "outro"}'])
def test_verify_com_o_recibo_trocado_por_lixo_falha(repo, bundle, lixo):
    instala(repo, bundle)
    (repo / RECIBO).write_text(lixo, encoding="utf-8")
    resultado = installer.verify_install(installer.plan_install(repo), bundle=bundle)
    assert resultado["ok"] is False and (RECIBO, "bad_receipt") in _problemas(resultado)


def test_verify_sem_recibo_mas_com_os_arquivos_falha_porque_o_uninstall_nao_saberia_remover(repo, bundle):
    instala(repo, bundle)
    (repo / RECIBO).unlink()
    resultado = installer.verify_install(installer.plan_install(repo), bundle=bundle)
    assert resultado["ok"] is False and (RECIBO, "no_receipt") in _problemas(resultado)


def test_verify_um_arquivo_identico_que_nao_e_nosso_passa_e_um_diferente_falha_como_foreign(repo, bundle):
    write(repo / SKILL, "video\n")
    instala(repo, bundle)
    assert installer.verify_install(installer.plan_install(repo), bundle=bundle)["ok"] is True
    (repo / SKILL).write_text("diferente\n", encoding="utf-8")
    assert (SKILL, "foreign") in _problemas(installer.verify_install(installer.plan_install(repo), bundle=bundle))


def test_verify_uma_pasta_no_lugar_do_arquivo_falha_como_not_a_file(repo, bundle):
    instala(repo, bundle)
    (repo / REF).unlink()
    (repo / REF).mkdir()
    assert (REF, "not_a_file") in _problemas(installer.verify_install(installer.plan_install(repo), bundle=bundle))


def test_verify_com_a_versao_errada_continua_recusando_como_o_do_loop(repo, bundle):
    with pytest.raises(installer.InstallError, match="versão"):
        installer.verify_install(installer.plan_install(repo, version="0.0.1"), bundle=bundle)


# --- the lock: installs in the same target at the same time are serialized -------------------------------------------------------------


@posix_real
def test_o_install_real_grava_install_lock_0600_e_o_uninstall_leva_embora(repo, bundle):
    instala(repo, bundle)
    trava = repo / TRAVA
    assert trava.is_file() and stat.S_IMODE(trava.stat().st_mode) == 0o600
    installer.uninstall(repo)
    assert fotografia(repo) == {}, "the lock file and the folder that held it are gone"


def test_dry_run_e_check_nao_criam_a_trava_nem_a_pasta(repo, bundle):
    instala(repo, bundle, dry_run=True)
    installer.verify_install(installer.plan_install(repo), bundle=bundle)
    assert fotografia(repo) == {}


@posix_real
def test_o_install_espera_pouco_pela_trava_e_depois_diz_quem_a_segura(repo, bundle, monkeypatch):
    from simplicio_video import lockfile

    monkeypatch.setattr(installer, "LOCK_WAIT_S", 0.2)
    instala(repo, bundle)
    with lockfile.file_lock(repo / ".simplicio-video" / "install.json", wait_s=1):
        with pytest.raises(installer.InstallError, match="install.lock"):
            instala(repo, bundle, host="codex")
    assert instala(repo, bundle, host="codex")["written"] >= 0, "free again: it installs"


@posix_real
@pytest.mark.parametrize("rodada", range(8))
def test_tres_installs_ao_mesmo_tempo_deixam_todas_as_entradas_no_recibo(tmp_path, bundle, rodada):
    """Without the lock the three read the receipt, each writes its own entry file and the last receipt wins: orphans."""
    alvo = tmp_path / f"alvo{rodada}"
    alvo.mkdir()
    largada = threading.Barrier(3)

    def roda(host):
        largada.wait()
        return instala(alvo, bundle, host=host)

    with ThreadPoolExecutor(3) as pool:
        for futuro in [pool.submit(roda, h) for h in ("codex", "gemini", "aider")]:
            futuro.result(timeout=60)
    recibo = recibo_de(alvo)
    for entrada in ("AGENTS.md", "GEMINI.md", "CONVENTIONS.md"):
        assert (alvo / entrada).is_file() and entrada in recibo["paths"], f"{entrada} is not in the receipt"
    installer.uninstall(alvo)
    assert fotografia(alvo) == {}, "the uninstall removes all three entry files and everything else"


@posix_real
def test_tres_processos_instalam_ao_mesmo_tempo_sem_orfaos(tmp_path):
    import subprocess
    import sys

    from _comum import ROOT

    alvo, casa = tmp_path / "alvo", tmp_path / "casa"
    alvo.mkdir()
    casa.mkdir()
    env = {**os.environ, "HOME": str(casa), "USERPROFILE": str(casa), "PATH": str(tmp_path / "vazio"), "SIMPLICIO_OFFLINE": "1",
           "PYTHONPATH": str(ROOT / "src"), "PYTHONDONTWRITEBYTECODE": "1"}
    for _ in range(3):
        filhos = [subprocess.Popen([sys.executable, "-m", "simplicio_video", "install", "--host", host, "--target", str(alvo)],
                                   env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
                  for host in ("codex", "gemini", "aider")]
        saidas = [(f.communicate(timeout=120)[0], f.returncode) for f in filhos]
        assert [rc for _out, rc in saidas] == [0, 0, 0], saidas
        recibo = recibo_de(alvo)
        assert {"AGENTS.md", "GEMINI.md", "CONVENTIONS.md"} <= set(recibo["paths"])
        assert subprocess.run([sys.executable, "-m", "simplicio_video", "install", "--uninstall", "--target", str(alvo)], env=env,
                              stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=120).returncode == 0
        assert fotografia(alvo) == {}


# --- a failed install leaves a receipt that matches the disk ---------------------------------------------------------------------------


def test_um_disco_que_falha_no_meio_deixa_o_recibo_do_que_foi_escrito_e_nenhuma_pasta_orfa(repo, bundle, monkeypatch):
    real = os.replace

    def falha(origem, destino, *a, **kw):
        if Path(destino).name == "a.md":
            raise OSError(28, "No space left on device", str(destino))
        return real(origem, destino, *a, **kw)

    monkeypatch.setattr(os, "replace", falha)
    with pytest.raises(OSError, match="No space"):
        instala(repo, bundle)
    monkeypatch.setattr(os, "replace", real)
    recibo = recibo_de(repo)
    assert recibo["paths"] == [SKILL] and ".claude/skills/simplicio-video/references" in recibo["dirs"]
    assert not [p for p in repo.rglob("*") if p.name.endswith(".tmp")]
    installer.uninstall(repo)
    assert fotografia(repo) == {}, "no folder is left that no receipt knows about"


# --- the prune: only the project's own receipt, never the global install ------------------------------------------------------------------


def test_prune_so_apaga_o_que_o_recibo_do_projeto_registra_com_o_mesmo_sha256(repo, bundle):
    instala(repo, bundle, host="kiro")
    (repo / ".kiro" / "steering" / "simplicio-video.md").write_text("editado\n", encoding="utf-8")
    copia_sem_recibo = write(repo / ".cursor" / "skills" / "simplicio-video" / "SKILL.md", "velha\n")
    minha = write(repo / ".claude" / "skills" / "minha-skill" / "SKILL.md", "m\n")
    resultado = installer.prune_project_copies(repo)
    assert not (repo / SKILL).exists() and not (repo / RECIBO).exists()
    assert (repo / ".kiro" / "steering" / "simplicio-video.md").read_text(encoding="utf-8") == "editado\n"
    assert ".kiro/steering/simplicio-video.md" in resultado["left_alone"]
    assert copia_sem_recibo.read_text(encoding="utf-8") == "velha\n", "a copy no receipt registers is not ours"
    assert minha.is_file()


def test_prune_sem_recibo_nao_apaga_nada(repo):
    copia = write(repo / ".claude" / "skills" / "simplicio-video" / "SKILL.md", "velha\n")
    resultado = installer.prune_project_copies(repo)
    assert copia.is_file() and resultado["removed"] == [] and resultado["left_alone"] == []


def test_prune_dry_run_lista_e_nao_remove(repo, bundle):
    instala(repo, bundle)
    antes = fotografia(repo)
    resultado = installer.prune_project_copies(repo, dry_run=True)
    assert resultado["status"] == "dry_run" and SKILL in resultado["removed"] and fotografia(repo) == antes


@posix_real
def test_prune_protege_o_que_a_instalacao_global_acabou_de_escrever_mesmo_por_um_link(tmp_path, repo, bundle):
    """The project's `.claude` is a link to the home's: the project's "copy" IS the global install."""
    casa = tmp_path / "casa"
    (casa / ".claude").mkdir(parents=True)
    (repo / ".claude").symlink_to(casa / ".claude", target_is_directory=True)
    instala(repo, bundle)  # the project install writes through the link, into the home
    instala(casa, bundle, globally=True)
    protegida = os.path.realpath(casa / ".claude" / "skills" / "simplicio-video")
    resultado = installer.prune_project_copies(repo, protect=[protegida])
    assert (casa / SKILL).is_file() and (casa / REF).is_file(), "the global install was pruned through the project's link"
    assert SKILL not in resultado["removed"] and SKILL in resultado["kept"] + resultado["left_alone"]


# --- `install --global`: the skill in ALL the global skill folders of the loop, with the ownership rules ------------------------------
#
# The loop's `skill_sync` knows 11 folders under the home (`~/.claude/skills`, `~/.codex/skills`, `~/.cursor/skills`...). The owner asked
# for "universal" and "igual ao loop": `install --global` puts the skills in every one of them. What keeps that from hurting is the
# ownership rule of the review (B2/I5): create what is missing (it enters the receipt with its sha256); update ONLY a file that is in
# the receipt and still has the recorded sha256 (our copy, not edited); never overwrite a file that was already there or that the user
# edited (`left_alone`); never delete an extra file of the user inside those folders; the uninstall removes only what is ours.

RAIZES_GLOBAIS = {
    "claude": ".claude/skills", "cursor": ".cursor/skills", "codex": ".codex/skills", "grok": ".grok/skills", "agents": ".agents/skills",
    "copilot": ".copilot/skills", "vscode": ".vscode/simplicio-skills", "opencode": ".config/opencode/skills",
    "amp": ".config/amp/skills", "kiro": ".kiro/steering", "simplicio_agent": ".simplicio-loop/skills",
}


def _skill_em(raiz_global: str) -> str:
    return f"{raiz_global}/simplicio-video/SKILL.md"


@pytest.fixture
def casa(tmp_path):
    pasta = tmp_path / "casa"
    pasta.mkdir()
    return pasta


def test_global_cria_a_skill_nas_onze_pastas_do_loop_e_registra_cada_arquivo_com_sha256(casa, bundle):
    resultado = instala(casa, bundle, globally=True)
    for raiz in RAIZES_GLOBAIS.values():
        assert (casa / _skill_em(raiz)).read_text(encoding="utf-8") == "video\n", raiz
        assert (casa / raiz / "simplicio-video" / "references" / "a.md").is_file(), raiz
    recibo = recibo_de(casa)
    for raiz in RAIZES_GLOBAIS.values():
        assert _skill_em(raiz) in recibo["paths"] and recibo["sha256"][_skill_em(raiz)] == sha("video\n")
    assert len(recibo["paths"]) == 2 * len(RAIZES_GLOBAIS) and set(recibo["sha256"]) == set(recibo["paths"])
    assert resultado["up_to_date"] is False and len(resultado["changes"]["created"]) == 2 * len(RAIZES_GLOBAIS) + 1
    assert installer.apply_plan(installer.plan_install(casa, globally=True), bundle=bundle)["up_to_date"] is True


def test_global_o_host_pedido_nao_muda_nada_todas_as_pastas_recebem(casa, bundle):
    for host in ("claude", "codex", "all"):
        plano = installer.plan_install(casa, host=host, globally=True)
        assert {a["destination"] for a in plano["actions"]} == set(RAIZES_GLOBAIS.values()), host
        assert {a["kind"] for a in plano["actions"]} == {"skills"} and plano["scope"] == "global"


def test_global_atualiza_so_a_copia_que_e_nossa_e_nao_foi_editada(casa, bundle):
    instala(casa, bundle, globally=True)
    (casa / _skill_em(".cursor/skills")).write_text("editada pelo usuário\n", encoding="utf-8")
    (bundle / "skills" / "simplicio-video" / "SKILL.md").write_text("video v2\n", encoding="utf-8")
    resultado = instala(casa, bundle, globally=True)
    assert (casa / _skill_em(".codex/skills")).read_text(encoding="utf-8") == "video v2\n", "our copy, not edited: updated"
    assert (casa / _skill_em(".claude/skills")).read_text(encoding="utf-8") == "video v2\n"
    assert (casa / _skill_em(".cursor/skills")).read_text(encoding="utf-8") == "editada pelo usuário\n", "an edited copy is the user's"
    assert _skill_em(".cursor/skills") in resultado["changes"]["left_alone"]
    assert _skill_em(".cursor/skills") not in recibo_de(casa)["paths"]
    assert _skill_em(".codex/skills") in resultado["changes"]["updated"]


def test_global_nao_sobrescreve_nem_toma_o_que_ja_existia_no_host(casa, bundle):
    antiga = write(casa / _skill_em(".codex/skills"), "release antiga, copiada à mão\n")
    identica = write(casa / _skill_em(".grok/skills"), "video\n")
    resultado = instala(casa, bundle, globally=True)
    assert antiga.read_text(encoding="utf-8") == "release antiga, copiada à mão\n"
    assert _skill_em(".codex/skills") in resultado["changes"]["left_alone"] and _skill_em(".codex/skills") not in resultado["owned"]
    assert _skill_em(".grok/skills") not in resultado["owned"] and _skill_em(".grok/skills") not in recibo_de(casa)["paths"]
    (bundle / "skills" / "simplicio-video" / "SKILL.md").write_text("video v2\n", encoding="utf-8")
    instala(casa, bundle, globally=True)
    assert antiga.read_text(encoding="utf-8") == "release antiga, copiada à mão\n" and identica.read_text(encoding="utf-8") == "video\n", \
        "a copy the install never owned is never updated either"


def test_global_nunca_apaga_um_arquivo_extra_do_usuario_nas_pastas_dos_hosts(casa, bundle):
    instala(casa, bundle, globally=True)
    notas = [write(casa / raiz / "simplicio-video" / "minhas-notas.md", "notas\n") for raiz in (".claude/skills", ".codex/skills")]
    outra = write(casa / ".codex" / "skills" / "minha-skill" / "SKILL.md", "minha\n")
    (bundle / "skills" / "simplicio-video" / "SKILL.md").write_text("video v2\n", encoding="utf-8")
    (bundle / "skills" / "simplicio-video" / "references" / "a.md").unlink()  # a file that LEFT the package is not deleted either
    for _ in range(2):
        resultado = instala(casa, bundle, globally=True)
    assert all(n.read_text(encoding="utf-8") == "notas\n" for n in notas) and outra.is_file()
    assert (casa / ".codex" / "skills" / "simplicio-video" / "references" / "a.md").is_file()
    assert ".codex/skills/simplicio-video/minhas-notas.md" in resultado["changes"]["left_alone"]


def test_global_check_fica_pendente_quando_uma_copia_nossa_e_nao_editada_esta_velha(casa, bundle):
    instala(casa, bundle, globally=True)
    plano = installer.plan_install(casa, globally=True)
    assert installer.apply_plan(plano, bundle=bundle, dry_run=True)["up_to_date"] is True
    (bundle / "skills" / "simplicio-video" / "SKILL.md").write_text("video v2\n", encoding="utf-8")
    seco = installer.apply_plan(plano, bundle=bundle, dry_run=True)
    assert seco["up_to_date"] is False and _skill_em(".kiro/steering") in seco["changes"]["updated"]
    assert (casa / _skill_em(".kiro/steering")).read_text(encoding="utf-8") == "video\n", "a dry run changes nothing"


def test_global_uma_copia_antiga_que_nao_e_nossa_nao_deixa_o_check_pendente(casa, bundle):
    write(casa / _skill_em(".codex/skills"), "release antiga\n")
    instala(casa, bundle, globally=True)
    assert installer.apply_plan(installer.plan_install(casa, globally=True), bundle=bundle, dry_run=True)["up_to_date"] is True


def test_global_uninstall_remove_so_o_nosso_nas_onze_pastas(casa, bundle):
    antiga = write(casa / _skill_em(".codex/skills"), "release antiga\n")
    instala(casa, bundle, globally=True)
    editada = casa / _skill_em(".cursor/skills")
    editada.write_text("editada\n", encoding="utf-8")
    notas = write(casa / ".claude" / "skills" / "simplicio-video" / "minhas-notas.md", "notas\n")
    resultado = installer.uninstall(casa)
    assert antiga.read_text(encoding="utf-8") == "release antiga\n" and editada.read_text(encoding="utf-8") == "editada\n"
    assert notas.is_file() and _skill_em(".cursor/skills") in resultado["left_alone"]
    for raiz in RAIZES_GLOBAIS.values():
        if raiz not in (".codex/skills", ".cursor/skills", ".claude/skills"):
            assert not (casa / raiz / "simplicio-video").exists(), raiz
    assert not (casa / ".simplicio-loop").exists() and not (casa / ".config").exists(), "the folders the install created are gone"
    assert (casa / ".codex" / "skills" / "simplicio-video" / "SKILL.md").is_file()


def test_global_verify_confere_as_onze_pastas(casa, bundle):
    plano = installer.plan_install(casa, globally=True)
    assert installer.verify_install(plano, bundle=bundle)["ok"] is False
    instala(casa, bundle, globally=True)
    assert installer.verify_install(plano, bundle=bundle)["ok"] is True
    (casa / _skill_em(".agents/skills")).write_text("adulterada\n", encoding="utf-8")
    assert (_skill_em(".agents/skills"), "modified") in _problemas(installer.verify_install(plano, bundle=bundle))


@posix_real
def test_global_uma_pasta_secundaria_que_e_link_e_pulada_e_as_outras_seguem(tmp_path, casa, bundle):
    dotfiles = tmp_path / "dotfiles-opencode"
    dotfiles.mkdir()
    (casa / ".config").mkdir()
    (casa / ".config" / "opencode").symlink_to(dotfiles, target_is_directory=True)
    resultado = instala(casa, bundle, globally=True)
    assert fotografia(dotfiles) == {}, "nothing was written through the link of a secondary host"
    assert ".config/opencode/skills" in resultado["changes"]["left_alone"]
    assert any(".config/opencode/skills" in aviso and "link" in aviso for aviso in resultado["warnings"]), resultado["warnings"]
    assert (casa / _skill_em(".claude/skills")).is_file() and (casa / _skill_em(".config/amp/skills")).is_file()
    assert installer.apply_plan(installer.plan_install(casa, globally=True), bundle=bundle, dry_run=True)["up_to_date"] is True
    assert installer.verify_install(installer.plan_install(casa, globally=True), bundle=bundle)["ok"] is True
    installer.uninstall(casa)
    assert fotografia(dotfiles) == {} and not (casa / _skill_em(".claude/skills")).exists()


@posix_real
def test_global_a_pasta_principal_claude_skills_que_e_link_continua_recusando_tudo(tmp_path, casa, bundle):
    fora = tmp_path / "dotfiles"
    fora.mkdir()
    (casa / ".claude").mkdir()
    (casa / ".claude" / "skills").symlink_to(fora, target_is_directory=True)
    with pytest.raises(installer.InstallRefused):
        instala(casa, bundle, globally=True)
    assert not (casa / ".codex").exists() and fotografia(fora) == {}, "a refusal writes nothing, in any folder"


@posix_real
def test_global_a_pasta_base_de_um_host_que_e_link_de_dotfiles_fecha_o_ciclo(tmp_path, casa, bundle):
    dotfiles = tmp_path / "dotfiles-codex"
    dotfiles.mkdir()
    (casa / ".codex").symlink_to(dotfiles, target_is_directory=True)
    plano = installer.plan_install(casa, globally=True)
    installer.apply_plan(plano, bundle=bundle)
    assert (dotfiles / "skills" / "simplicio-video" / "SKILL.md").is_file()
    assert recibo_de(casa)["bases"][".codex"] == str(dotfiles.resolve())
    assert installer.apply_plan(plano, bundle=bundle)["up_to_date"] is True and installer.verify_install(plano, bundle=bundle)["ok"] is True
    installer.uninstall(casa)
    assert fotografia(dotfiles) == {} and (casa / ".codex").is_symlink()


@posix_real
def test_global_uma_pasta_que_virou_link_depois_do_install_nao_derruba_o_resto_do_recibo(tmp_path, casa, bundle):
    instala(casa, bundle, globally=True)
    movido = tmp_path / "amp-movido"
    (casa / ".config" / "amp").rename(movido)
    (casa / ".config" / "amp").symlink_to(movido, target_is_directory=True)  # the user moved it into a dotfiles repository
    (bundle / "skills" / "simplicio-video" / "SKILL.md").write_text("video v2\n", encoding="utf-8")
    resultado = instala(casa, bundle, globally=True)
    assert (casa / _skill_em(".codex/skills")).read_text(encoding="utf-8") == "video v2\n", "the other folders stay ours and are updated"
    assert (movido / "skills" / "simplicio-video" / "SKILL.md").read_text(encoding="utf-8") == "video\n", "nothing is written through the new link"
    assert resultado["warnings"] and any("amp" in aviso for aviso in resultado["warnings"]), resultado["warnings"]
    assert not any(p.startswith(".config/amp") for p in recibo_de(casa)["paths"]), "the paths under the new link left the receipt"
    installer.uninstall(casa)
    assert not (casa / _skill_em(".codex/skills")).exists() and (movido / "skills" / "simplicio-video" / "SKILL.md").is_file()


# --- review 2 of PR #117 (head a342a1c) ----------------------------------------------------------------------------------------------


def _falha_a_escrita_de(monkeypatch, nome: str, erro: OSError):
    real = os.replace

    def falha(origem, destino, *a, **kw):
        if Path(destino).name == nome:
            raise erro
        return real(origem, destino, *a, **kw)

    monkeypatch.setattr(os, "replace", falha)
    return real


@pytest.mark.parametrize("erro", [OSError(28, "No space left on device", "x"), PermissionError(13, "Permission denied", "x")],
                         ids=["disco-cheio", "permissao-negada"])
def test_escrita_que_falha_na_atualizacao_nao_tira_a_skill_nossa_do_recibo(repo, bundle, monkeypatch, erro):
    """I1: a file of ours that could not be updated is still ours, with the OLD sha256 (it is still on disk, atomically intact)."""
    instala(repo, bundle)
    (bundle / "skills" / "simplicio-video" / "SKILL.md").write_text("video v2\n", encoding="utf-8")
    real = _falha_a_escrita_de(monkeypatch, "SKILL.md", erro)
    with pytest.raises(OSError):
        instala(repo, bundle)
    monkeypatch.setattr(os, "replace", real)
    recibo = recibo_de(repo)
    assert SKILL in recibo["paths"] and recibo["sha256"][SKILL] == sha("video\n"), "the failed file left the receipt: stale for ever"
    assert (repo / SKILL).read_text(encoding="utf-8") == "video\n"


def test_depois_da_escrita_que_falhou_o_retry_corrige_e_o_uninstall_remove(repo, bundle, monkeypatch):
    instala(repo, bundle)
    (bundle / "skills" / "simplicio-video" / "SKILL.md").write_text("video v2\n", encoding="utf-8")
    real = _falha_a_escrita_de(monkeypatch, "SKILL.md", OSError(28, "No space left on device", "x"))
    with pytest.raises(OSError):
        instala(repo, bundle)
    monkeypatch.setattr(os, "replace", real)
    resultado = instala(repo, bundle)  # the retry
    assert SKILL in resultado["changes"]["updated"] and SKILL not in resultado["changes"]["left_alone"]
    assert (repo / SKILL).read_text(encoding="utf-8") == "video v2\n" and recibo_de(repo)["sha256"][SKILL] == sha("video v2\n")
    installer.uninstall(repo)
    assert fotografia(repo) == {}


def test_o_uninstall_logo_depois_da_escrita_que_falhou_remove_a_skill_velha(repo, bundle, monkeypatch):
    instala(repo, bundle)
    (bundle / "skills" / "simplicio-video" / "SKILL.md").write_text("video v2\n", encoding="utf-8")
    real = _falha_a_escrita_de(monkeypatch, "SKILL.md", PermissionError(13, "Permission denied", "x"))
    with pytest.raises(OSError):
        instala(repo, bundle)
    monkeypatch.setattr(os, "replace", real)
    resultado = installer.uninstall(repo)
    assert SKILL in resultado["removed"] and fotografia(repo) == {}, "the old file was ours and nobody edited it: it goes"


def test_global_escrita_que_falha_numa_pasta_de_host_mantem_a_copia_dela_no_recibo(casa, bundle, monkeypatch):
    instala(casa, bundle, globally=True)
    (bundle / "skills" / "simplicio-video" / "SKILL.md").write_text("video v2\n", encoding="utf-8")
    real = os.replace

    def falha(origem, destino, *a, **kw):
        if ".codex" in Path(destino).parts and Path(destino).name == "SKILL.md":
            raise PermissionError(13, "Permission denied", str(destino))
        return real(origem, destino, *a, **kw)

    monkeypatch.setattr(os, "replace", falha)
    with pytest.raises(OSError):
        instala(casa, bundle, globally=True)
    monkeypatch.setattr(os, "replace", real)
    assert _skill_em(".codex/skills") in recibo_de(casa)["paths"], "the copy of the other host stays ours and gets fixed on retry"
    resultado = instala(casa, bundle, globally=True)
    assert (casa / _skill_em(".codex/skills")).read_text(encoding="utf-8") == "video v2\n"
    assert _skill_em(".codex/skills") in resultado["changes"]["updated"]


# I3 (mutants that survived): one test per safeguard


@pytest.mark.parametrize("dry", [False, True])
def test_a_recusa_do_recibo_plantado_vem_antes_da_trava_e_nada_nasce_no_repo_hostil(repo, bundle, dry):
    """M1: the lock creates `.simplicio-video/install.lock`; a receipt that is refused must not have made a hostile repo grow a file."""
    write(repo / "notes.md", "do repositório\n")
    planta_recibo(repo, ["notes.md", ".git/config"])
    antes = fotografia(repo)
    with pytest.raises(installer.InstallError):
        installer.uninstall(repo, dry_run=dry)
    with pytest.raises(installer.InstallError):
        installer.prune_project_copies(repo, dry_run=dry)
    assert not (repo / TRAVA).exists() and fotografia(repo) == antes


def test_arquivo_de_entrada_editado_nao_continua_no_recibo_quando_o_install_e_de_outro_host(repo, bundle):
    """M2: the entry file of a host this run does not look at is carried forward ONLY while it still has the sha256 that was written."""
    instala(repo, bundle, host="codex")
    (repo / "AGENTS.md").write_text("# as minhas regras\n", encoding="utf-8")
    instala(repo, bundle, host="claude")
    recibo = recibo_de(repo)
    assert "AGENTS.md" not in recibo["paths"] and "AGENTS.md" not in recibo["sha256"]
    installer.uninstall(repo)
    assert (repo / "AGENTS.md").read_text(encoding="utf-8") == "# as minhas regras\n"


def test_arquivo_de_entrada_intacto_de_outro_host_continua_no_recibo(repo, bundle):
    instala(repo, bundle, host="codex")
    instala(repo, bundle, host="claude")
    assert "AGENTS.md" in recibo_de(repo)["paths"]


@posix_real
def test_arquivo_do_recibo_que_virou_link_e_do_usuario_e_o_uninstall_e_o_prune_nao_apagam_o_link(tmp_path, repo, bundle):
    """M3: the link points at a file with the SAME bytes as ours, so a check that follows it would match and delete the user's link."""
    instala(repo, bundle)
    alvo = write(tmp_path / "meu" / "SKILL.md", "video\n")
    (repo / SKILL).unlink()
    (repo / SKILL).symlink_to(alvo)
    seco = installer.uninstall(repo, dry_run=True)
    assert SKILL in seco["left_alone"] and SKILL not in seco["removed"]
    podado = installer.prune_project_copies(repo)
    assert (repo / SKILL).is_symlink() and alvo.read_text(encoding="utf-8") == "video\n"
    assert SKILL in podado["left_alone"] and any("link" in aviso for aviso in podado["warnings"]), podado


@posix_real
def test_recibo_que_e_fifo_nao_trava_o_uninstall_o_prune_nem_o_verify(repo, bundle):
    """M5: the receipt is read O_NONBLOCK and checked with fstat on the same descriptor; a plain open() would block for ever."""
    instala(repo, bundle)
    plano = installer.plan_install(repo)
    (repo / RECIBO).unlink()
    os.mkfifo(repo / RECIBO)

    def tenta(funcao):
        try:
            funcao()
        except installer.InstallError as erro:
            return str(erro)
        return None

    for nome, funcao in (("uninstall", lambda: installer.uninstall(repo)), ("uninstall --dry-run", lambda: installer.uninstall(repo, dry_run=True)),
                         ("prune", lambda: installer.prune_project_copies(repo, dry_run=True)),
                         ("apply", lambda: installer.apply_plan(plano, bundle=bundle, dry_run=True))):
        mensagem = roda_com_prazo(lambda f=funcao: tenta(f), destravar=lambda: solta_fifo(repo / RECIBO))
        assert mensagem, f"{nome} on a FIFO receipt must fail with a message"
    verificado = roda_com_prazo(lambda: installer.verify_install(plano, bundle=bundle), destravar=lambda: solta_fifo(repo / RECIBO))
    assert verificado["ok"] is False and (RECIBO, "bad_receipt") in _problemas(verificado)


@posix_real
def test_link_abaixo_da_pasta_base_gravada_nao_e_atravessado_no_uninstall(tmp_path, repo, bundle):
    """M6: `.claude` is a recorded dotfiles link; later `skills` BELOW it becomes a link to a copy with the same bytes."""
    dot = tmp_path / "dot"
    dot.mkdir()
    (repo / ".claude").symlink_to(dot, target_is_directory=True)
    instala(repo, bundle)
    outro = tmp_path / "outro"
    shutil.copytree(dot / "skills", outro)
    shutil.rmtree(dot / "skills")
    (dot / "skills").symlink_to(outro, target_is_directory=True)
    resultado = installer.uninstall(repo)
    assert (outro / "simplicio-video" / "SKILL.md").is_file() and (outro / "simplicio-video" / "references" / "a.md").is_file()
    assert SKILL in resultado["left_alone"] and REF in resultado["left_alone"] and resultado["warnings"]


def test_sha256_de_arquivo_maior_que_o_limite_e_none_nunca_o_digest_de_um_pedaco(tmp_path, monkeypatch):
    """M7: `read_regular` hands back limit + 1 bytes of a bigger file; hashing that prefix would let a planted digest match."""
    monkeypatch.setattr(installer, "MAX_FILE_BYTES", 8)
    assert installer.sha256_of(write(tmp_path / "grande", "x" * 100)) is None
    assert installer.sha256_of(write(tmp_path / "ok", "12345678")) == sha("12345678")


def test_o_sha256_le_no_maximo_o_limite_mais_um_byte(tmp_path, monkeypatch):
    from simplicio_video import hostos

    pedidos = []
    real = hostos.read_regular
    monkeypatch.setattr(hostos, "read_regular", lambda caminho, limite: pedidos.append(limite) or real(caminho, limite))
    installer.sha256_of(write(tmp_path / "a", "abc"))
    assert pedidos == [installer.MAX_FILE_BYTES]


def test_o_uninstall_nao_apaga_arquivo_maior_que_o_limite_mesmo_com_o_digest_do_pedaco(repo, bundle, monkeypatch):
    instala(repo, bundle)
    monkeypatch.setattr(installer, "MAX_FILE_BYTES", 8)
    grande = "x" * 100
    (repo / REF).write_text(grande, encoding="utf-8")
    grava_recibo(repo, sha256={**recibo_de(repo)["sha256"], REF: sha(grande[:9])})  # the digest of the first limit + 1 bytes
    resultado = installer.uninstall(repo)
    assert (repo / REF).is_file() and REF in resultado["left_alone"]


@posix_real
def test_recibo_que_e_link_e_recusado_no_install_no_uninstall_e_no_verify(tmp_path, repo, bundle):
    """M8: a receipt that is a link could be the victim's own receipt, pointed at by a repository."""
    instala(repo, bundle)
    conteudo = (repo / RECIBO).read_bytes()
    fora = tmp_path / "fora.json"
    fora.write_bytes(conteudo)
    (repo / RECIBO).unlink()
    (repo / RECIBO).symlink_to(fora)
    plano = installer.plan_install(repo)
    with pytest.raises(installer.InstallError):
        installer.apply_plan(plano, bundle=bundle)
    for dry in (True, False):
        with pytest.raises(installer.InstallError, match="link"):
            installer.uninstall(repo, dry_run=dry)
    with pytest.raises(installer.InstallError, match="link"):
        installer.prune_project_copies(repo)
    assert (repo / RECIBO).is_symlink() and fora.read_bytes() == conteudo and (repo / SKILL).is_file()
    verificado = installer.verify_install(plano, bundle=bundle)
    assert verificado["ok"] is False and (RECIBO, "bad_receipt") in _problemas(verificado)


def test_digest_que_falta_nao_autoriza_apagar_nem_quando_o_arquivo_nao_pode_ser_lido(repo, bundle, monkeypatch):
    """M9: a path without a digest has `None`; an unreadable file also hashes to `None`; `None == None` must never delete."""
    instala(repo, bundle)
    monkeypatch.setattr(installer, "MAX_FILE_BYTES", 8)
    (repo / REF).write_text("x" * 100, encoding="utf-8")  # now unreadable for the check: sha256_of -> None
    recibo = recibo_de(repo)
    del recibo["sha256"][REF]
    (repo / RECIBO).write_text(json.dumps(recibo), encoding="utf-8")
    resultado = installer.uninstall(repo)
    assert (repo / REF).is_file() and REF in resultado["left_alone"]


# minor (a): a forged `bases` must not reach the global install


@posix_real
def test_repo_com_claude_em_link_para_o_do_home_e_recibo_forjado_nao_apaga_a_instalacao_global(tmp_path, bundle):
    casa = tmp_path / "casa"
    instala(casa, bundle, globally=True)
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".claude").symlink_to(casa / ".claude", target_is_directory=True)
    real = os.path.realpath(casa / ".claude")
    write(repo / RECIBO, json.dumps({
        "schema": installer.OWNERSHIP_SCHEMA, "owner": "simplicio-video", "version": "0.0.1", "digest": "sha256:" + "0" * 64,
        "paths": [SKILL, REF], "dirs": [], "sha256": {SKILL: sha("video\n"), REF: sha("ref a\n")}, "bases": {".claude": real}}))
    cerca = [casa / raiz / nome for raiz in RAIZES_GLOBAIS.values() for nome in ("simplicio-video", "simplicio-video-social")]
    resultado = installer.uninstall(repo, protect=cerca)
    assert (casa / SKILL).is_file() and (casa / REF).is_file(), "a project uninstall removed the GLOBAL install through a forged base"
    assert SKILL in resultado["left_alone"] and any("global" in aviso for aviso in resultado["warnings"])


# minor (d): the verify's own message for a linked `.simplicio-video`


@posix_real
def test_verify_com_simplicio_video_em_link_tem_mensagem_propria_sem_dizer_que_nada_foi_escrito(tmp_path, repo, bundle):
    instala(repo, bundle)
    shutil.move(str(repo / ".simplicio-video"), str(tmp_path / "sv"))
    (repo / ".simplicio-video").symlink_to(tmp_path / "sv", target_is_directory=True)
    resultado = installer.verify_install(installer.plan_install(repo), bundle=bundle)
    assert resultado["ok"] is False
    achado = [p for p in resultado["problems"] if p["path"] == ".simplicio-video"]
    assert achado and achado[0]["problem"] == "not_a_file" and "link" in achado[0]["detail"]
    assert not any("Nada foi escrito" in p["detail"] for p in resultado["problems"]), "verify writes nothing, ever: no need to say it"
    assert all(p["path"] != ".claude/skills" for p in resultado["problems"]), "the problem is labelled with its own path"
