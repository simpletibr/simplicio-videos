"""The host-aware install planner of simplicio-video (`simplicio_video.installer`): the skills go INTO the agent host.

Ported from simplicio-loop (`simplicio_loop/install/planner.py`, 2034e2d) with the names swapped (`simplicio-loop` ->
`simplicio-video`, `.simplicio-loop` -> `.simplicio-video`, `simplicio.loop-install-plan/v1` ->
`simplicio.video-install-plan/v1`). The video has no hooks, so only skills (and the host's entry file) are written.

Contract: idempotent (an identical file is not rewritten), every file it writes is registered in an ownership receipt
(`.simplicio-video/install-ownership.json`), a file that is not ours is never overwritten (`left_alone`) and the uninstall
removes only what the receipt registers, never anything outside the target, whatever the receipt says.

Everything runs in tmp_path. Linux, macOS and Windows are simulated where the code reads the system; the tests that need real
POSIX files (symlinks) are marked `posix_real`.
"""
from __future__ import annotations

import json
import os
import zipfile
from pathlib import Path

import pytest

import _caixa
from _caixa import SISTEMAS, installer, posix_real, skill_sync
from _comum import fotografia, make_bundle, write

caixa = _caixa.caixa
simula_so = _caixa.simula_so

HOSTS_DO_LOOP = ("claude", "codex", "cursor", "vscode", "grok", "kiro", "antigravity", "opencode", "gemini", "aider",
                 "simplicio_agent", "openclaw")
# The entry file each host reads, from the loop's own table (scripts/install_lib.py RUNTIMES); None = the host needs none.
ENTRADA = {"claude": None, "codex": "AGENTS.md", "cursor": None, "vscode": ".github/copilot-instructions.md", "grok": "AGENTS.md",
           "kiro": ".kiro/steering/simplicio-video.md", "antigravity": "AGENTS.md", "opencode": "AGENTS.md", "gemini": "GEMINI.md",
           "aider": "CONVENTIONS.md", "simplicio_agent": None, "openclaw": None}
RECIBO = ".simplicio-video/install-ownership.json"
SKILL = ".claude/skills/simplicio-video/SKILL.md"
REF = ".claude/skills/simplicio-video/references/a.md"


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


def desinstala(raiz, **kw):
    return installer.uninstall(raiz, **kw)


# --- the registry of hosts ----------------------------------------------------------------------------------------------


def test_os_hosts_sao_os_doze_do_registro_do_loop():
    assert tuple(installer.HOSTS) == HOSTS_DO_LOOP


def test_o_esquema_do_plano_e_o_do_video():
    assert installer.SCHEMA == "simplicio.video-install-plan/v1"
    assert installer.OWNERSHIP_SCHEMA == "simplicio.video-install-ownership/v1"
    assert str(installer.RECEIPT).replace("\\", "/") == RECIBO


@pytest.mark.parametrize("host", HOSTS_DO_LOOP)
def test_cada_host_recebe_as_skills_em_claude_skills_e_so_o_seu_arquivo_de_entrada(repo, host):
    plano = installer.plan_install(repo, host=host)
    destinos = {a["destination"]: a["kind"] for a in plano["actions"]}
    esperado = {".claude/skills": "skills"}
    if ENTRADA[host]:
        esperado[ENTRADA[host]] = "entry"
    assert destinos == esperado
    assert all(a["owner"] == "simplicio-video" and a["host"] == host for a in plano["actions"])
    assert "hooks" not in {a["kind"] for a in plano["actions"]}, "the video has no hooks"


def test_global_so_escreve_as_skills_em_claude_skills_para_qualquer_host(repo):
    for host in HOSTS_DO_LOOP:
        plano = installer.plan_install(repo, host=host, globally=True)
        assert {a["destination"]: a["kind"] for a in plano["actions"]} == {".claude/skills": "skills"}
        assert plano["scope"] == "global"


def test_all_cobre_todos_os_hosts_e_o_dono_dos_arquivos_nao_repete(repo, bundle):
    plano = installer.plan_install(repo, host="all")
    assert plano["hosts"] == list(HOSTS_DO_LOOP)
    resultado = instala(repo, bundle, host="all")
    for entrada in {e for e in ENTRADA.values() if e}:
        assert (repo / entrada).is_file(), entrada
    assert len(resultado["owned"]) == len(set(resultado["owned"])), "a path shared by two hosts is owned once"


def test_host_desconhecido_falha_fechado(repo):
    with pytest.raises(installer.InstallError, match="host desconhecido"):
        installer.plan_install(repo, host="nao-existe")
    assert fotografia(repo) == {}


def test_o_plano_tem_as_chaves_do_loop_e_um_digest_estavel(repo):
    plano = installer.plan_install(repo, host="codex", version="1.2.3")
    assert set(plano) == {"schema", "version", "target", "scope", "hosts", "actions", "entrypoint", "digest"}
    assert plano["schema"] == installer.SCHEMA and plano["version"] == "1.2.3" and plano["scope"] == "project"
    assert plano["entrypoint"] == "simplicio-video=simplicio_video.cli:main"
    assert plano["digest"].startswith("sha256:") and len(plano["digest"]) == len("sha256:") + 64
    assert plano["digest"] == installer.plan_install(repo, host="codex", version="1.2.3")["digest"]
    assert plano["digest"] != installer.plan_install(repo, host="claude", version="1.2.3")["digest"]
    assert plano["digest"] != installer.plan_install(repo, host="codex", version="1.2.4")["digest"]
    assert plano["digest"] != installer.plan_install(repo, host="codex", version="1.2.3", globally=True)["digest"]


def test_planejar_nao_toca_no_disco(repo):
    installer.plan_install(repo, host="all")
    assert fotografia(repo) == {}


def test_o_alvo_do_plano_e_resolvido(repo, monkeypatch):
    monkeypatch.chdir(repo)
    assert Path(installer.plan_install(".", host="claude")["target"]) == repo.resolve()


# --- apply: idempotent, honest about what it did --------------------------------------------------------------------------


def test_a_primeira_instalacao_cria_tudo_e_o_cache_de_bytecode_nao_viaja(repo, bundle):
    resultado = instala(repo, bundle)
    mudancas = resultado["changes"]
    assert sorted(mudancas["created"]) == sorted([SKILL, REF, RECIBO])
    assert mudancas["updated"] == [] and mudancas["unchanged"] == 0 and mudancas["left_alone"] == []
    assert resultado["written"] == 3 and resultado["up_to_date"] is False and resultado["status"] == "applied"
    assert resultado["schema"] == installer.SCHEMA
    assert not list(repo.rglob("__pycache__"))
    assert (repo / SKILL).read_bytes() == (bundle / "skills" / "simplicio-video" / "SKILL.md").read_bytes()


def test_a_segunda_instalacao_nao_muda_nem_regrava_nada(repo, bundle):
    instala(repo, bundle)
    arquivos = [p for p in repo.rglob("*") if p.is_file()]
    for caminho in arquivos:
        os.utime(caminho, ns=(10**9, 10**9))
    resultado = instala(repo, bundle)
    mudancas = resultado["changes"]
    assert mudancas["created"] == [] and mudancas["updated"] == [] and mudancas["unchanged"] == 3
    assert resultado["written"] == 0 and resultado["up_to_date"] is True and resultado["status"] == "applied"
    assert {p.stat().st_mtime_ns for p in arquivos} == {10**9}, "an identical file was rewritten"


def test_arquivo_do_pacote_que_mudou_e_atualizado_e_o_apagado_e_criado_de_novo(repo, bundle):
    instala(repo, bundle)
    (bundle / "skills" / "simplicio-video" / "SKILL.md").write_text("video v2\n", encoding="utf-8")
    (repo / REF).unlink()
    resultado = instala(repo, bundle)
    assert resultado["changes"]["updated"] == [SKILL] and resultado["changes"]["created"] == [REF]
    assert resultado["changes"]["unchanged"] == 1
    assert (repo / SKILL).read_text(encoding="utf-8") == "video v2\n"


def test_o_que_nao_e_do_simplicio_video_fica_em_paz_e_e_relatado(repo, bundle):
    alheia = write(repo / ".claude" / "skills" / "minha-skill" / "SKILL.md", "minha\n")
    resultado = instala(repo, bundle)
    assert resultado["changes"]["left_alone"] == [".claude/skills/minha-skill"]
    assert alheia.read_text(encoding="utf-8") == "minha\n"


def test_arquivo_de_entrada_que_ja_existe_nao_e_sobrescrito(repo, bundle):
    write(repo / "AGENTS.md", "# o meu AGENTS\n")
    resultado = instala(repo, bundle, host="codex")
    assert "AGENTS.md" in resultado["changes"]["left_alone"]
    assert (repo / "AGENTS.md").read_text(encoding="utf-8") == "# o meu AGENTS\n"
    de_novo = instala(repo, bundle, host="grok")  # the same entry file, already there
    assert "AGENTS.md" in de_novo["changes"]["left_alone"]
    assert "AGENTS.md" not in resultado["owned"]


def test_arquivo_de_entrada_novo_aponta_para_a_skill_e_e_do_simplicio_video(repo, bundle):
    resultado = instala(repo, bundle, host="gemini")
    texto = (repo / "GEMINI.md").read_text(encoding="utf-8")
    assert ".claude/skills/simplicio-video/SKILL.md" in texto and "gemini" in texto
    assert "GEMINI.md" in resultado["owned"]
    assert "GEMINI.md" in json.loads((repo / RECIBO).read_text(encoding="utf-8"))["paths"]


def test_dry_run_diz_o_mesmo_e_nao_escreve_nada(repo, bundle):
    antes = fotografia(repo)
    resultado = instala(repo, bundle, dry_run=True)
    assert resultado["status"] == "dry_run" and resultado["written"] == 0
    assert len(resultado["changes"]["created"]) == 3 and fotografia(repo) == antes
    instala(repo, bundle)
    de_novo = instala(repo, bundle, dry_run=True)
    assert de_novo["up_to_date"] is True and de_novo["changes"]["unchanged"] == 3


def test_o_bundle_pode_ser_um_traversable_que_nao_e_caminho_de_disco(tmp_path, repo, bundle):
    """A zip served as package data: nothing may need Path.rglob or shutil on the bundle."""
    arquivo = tmp_path / "bundle.zip"
    with zipfile.ZipFile(arquivo, "w") as zf:
        for caminho in bundle.rglob("*"):
            if caminho.is_file():
                zf.write(caminho, caminho.relative_to(bundle).as_posix())
    resultado = instala(repo, zipfile.Path(arquivo))
    assert len(resultado["changes"]["created"]) == 3
    assert (repo / REF).read_text(encoding="utf-8") == "ref a\n"
    assert instala(repo, zipfile.Path(arquivo))["up_to_date"] is True


def test_sem_skills_no_pacote_a_instalacao_para_e_nao_escreve_nada(tmp_path, repo):
    vazio = tmp_path / "vazio"
    vazio.mkdir()
    with pytest.raises(installer.InstallError, match="skills"):
        instala(repo, vazio)
    assert fotografia(repo) == {}


def test_o_bundle_padrao_vem_do_importlib_resources_e_tem_as_skills_de_skill_sync():
    raiz = installer.bundle_root()
    nomes = sorted(c.name for c in raiz.joinpath("skills").iterdir() if c.is_dir())
    assert nomes == sorted(skill_sync.SKILLS)
    for nome in skill_sync.SKILLS:
        assert raiz.joinpath("skills", nome, "SKILL.md").is_file()


def test_o_recibo_e_json_utf8_com_nova_linha_e_registra_arquivos_e_pastas(repo, bundle):
    instala(repo, bundle)
    bruto = (repo / RECIBO).read_bytes()
    assert bruto.endswith(b"\n")
    recibo = json.loads(bruto.decode("utf-8"))
    assert recibo["schema"] == installer.OWNERSHIP_SCHEMA and recibo["owner"] == "simplicio-video"
    assert recibo["paths"] == sorted([SKILL, REF]) and ".simplicio-video" in recibo["dirs"]
    assert ".claude/skills/simplicio-video/references" in recibo["dirs"]
    assert set(recibo) == {"schema", "owner", "version", "digest", "paths", "dirs"}


def test_um_segundo_host_instalado_depois_nao_apaga_do_recibo_o_do_primeiro(repo, bundle):
    instala(repo, bundle, host="claude")
    instala(repo, bundle, host="codex")
    recibo = json.loads((repo / RECIBO).read_text(encoding="utf-8"))
    assert SKILL in recibo["paths"] and "AGENTS.md" in recibo["paths"]
    desinstala(repo)
    assert fotografia(repo) == {}


def test_recibo_de_outro_dono_ou_esquema_nao_e_lido_na_instalacao(repo, bundle):
    write(repo / RECIBO, json.dumps({"schema": "outro/v9", "owner": "simplicio-video", "paths": ["keep.txt"], "dirs": []}))
    instala(repo, bundle)
    assert "keep.txt" not in json.loads((repo / RECIBO).read_text(encoding="utf-8"))["paths"]


def test_a_escrita_e_atomica_um_replace_que_falha_nao_deixa_arquivo_pela_metade_nem_temporario(repo, bundle, monkeypatch):
    instala(repo, bundle)
    (bundle / "skills" / "simplicio-video" / "SKILL.md").write_text("video v2\n", encoding="utf-8")
    real = os.replace

    def falha(origem, destino, *a, **kw):
        if Path(destino).name == "SKILL.md":
            raise PermissionError(13, "Permission denied", str(destino))
        return real(origem, destino, *a, **kw)

    monkeypatch.setattr(os, "replace", falha)
    with pytest.raises(OSError):
        instala(repo, bundle)
    assert (repo / SKILL).read_text(encoding="utf-8") == "video\n", "the old file must survive a failed write"
    assert not [p for p in repo.rglob("*") if p.name.endswith(".tmp")], "a temporary file was left behind"


def test_arquivo_novo_respeita_o_umask_e_nao_fica_0600(repo, bundle):
    if os.name == "nt":
        pytest.skip("POSIX modes")
    antigo = os.umask(0o022)
    try:
        instala(repo, bundle)
    finally:
        os.umask(antigo)
    assert (repo / SKILL).stat().st_mode & 0o777 == 0o644


@posix_real
def test_link_simbolico_no_lugar_do_arquivo_nao_e_nosso_e_o_alvo_nao_e_tocado(tmp_path, repo, bundle):
    alvo = write(tmp_path / "dotfiles" / "SKILL.md", "do dono\n")
    (repo / ".claude" / "skills" / "simplicio-video").mkdir(parents=True)
    (repo / SKILL).symlink_to(alvo)
    resultado = instala(repo, bundle)
    assert SKILL in resultado["changes"]["left_alone"] and SKILL not in resultado["owned"]
    assert alvo.read_text(encoding="utf-8") == "do dono\n" and (repo / SKILL).is_symlink()


@posix_real
def test_a_pasta_da_skill_que_e_link_simbolico_nao_e_escrita_por_dentro(tmp_path, repo, bundle):
    """The owner's skills may be links into a clone (dotfiles, this repo): writing through them would edit the clone."""
    clone = tmp_path / "clone" / "skills" / "simplicio-video"
    write(clone / "SKILL.md", "do clone\n")
    (repo / ".claude" / "skills").mkdir(parents=True)
    (repo / ".claude" / "skills" / "simplicio-video").symlink_to(clone, target_is_directory=True)
    resultado = instala(repo, bundle)
    assert ".claude/skills/simplicio-video" in resultado["changes"]["left_alone"]
    assert fotografia(clone.parent.parent) == {"skills": None, "skills/simplicio-video": None,
                                               "skills/simplicio-video/SKILL.md": "do clone\n"}


@posix_real
def test_claude_skills_pode_ser_um_link_do_dono_e_as_skills_vao_para_o_alvo_dele(tmp_path, repo, bundle):
    destino = tmp_path / "dotfiles" / "skills"
    destino.mkdir(parents=True)
    (repo / ".claude").mkdir()
    (repo / ".claude" / "skills").symlink_to(destino, target_is_directory=True)
    resultado = instala(repo, bundle)
    assert (destino / "simplicio-video" / "SKILL.md").is_file() and resultado["up_to_date"] is False
    assert instala(repo, bundle)["up_to_date"] is True


@pytest.mark.parametrize("so", SISTEMAS)
def test_os_caminhos_do_recibo_e_do_resultado_usam_barra_em_qualquer_sistema(repo, bundle, simula_so, so):
    simula_so(so)
    resultado = instala(repo, bundle, host="kiro")
    todos = resultado["owned"] + resultado["changes"]["created"] + json.loads((repo / RECIBO).read_text(encoding="utf-8"))["paths"]
    assert todos and all("\\" not in p and not p.startswith("/") for p in todos)
    assert ".kiro/steering/simplicio-video.md" in resultado["owned"]


# --- uninstall: only what the receipt registers ---------------------------------------------------------------------------


def test_skill_de_usuario_ao_lado_da_do_video_sobrevive_ao_uninstall(repo, bundle):
    minha = write(repo / ".claude" / "skills" / "minha-skill" / "SKILL.md", "minha\n")
    instala(repo, bundle)
    desinstala(repo)
    assert minha.read_text(encoding="utf-8") == "minha\n"
    assert not (repo / ".claude" / "skills" / "simplicio-video").exists()


def test_skill_do_usuario_criada_depois_da_instalacao_tambem_sobrevive(repo, bundle):
    instala(repo, bundle)
    minha = write(repo / ".claude" / "skills" / "minha-skill" / "SKILL.md", "minha\n")
    desinstala(repo)
    assert minha.is_file() and (repo / ".claude" / "skills").is_dir()


def test_as_pastas_que_o_install_criou_saem_quando_vazias_e_o_alvo_volta_ao_inicio(repo, bundle):
    instala(repo, bundle)
    desinstala(repo)
    assert fotografia(repo) == {}


def test_pastas_que_ja_existiam_antes_da_instalacao_nao_sao_removidas(repo, bundle):
    (repo / ".claude" / "skills").mkdir(parents=True)
    instala(repo, bundle)
    desinstala(repo)
    assert (repo / ".claude" / "skills").is_dir() and not (repo / SKILL).exists()


def test_arquivo_de_entrada_que_ja_existia_nunca_e_removido_e_o_criado_pelo_install_e(repo, bundle):
    write(repo / "AGENTS.md", "# meu\n")
    instala(repo, bundle, host="codex")
    desinstala(repo)
    assert (repo / "AGENTS.md").read_text(encoding="utf-8") == "# meu\n"
    (repo / "AGENTS.md").unlink()
    instala(repo, bundle, host="codex")
    assert (repo / "AGENTS.md").is_file()
    desinstala(repo)
    assert not (repo / "AGENTS.md").exists()


@pytest.mark.parametrize("host", ["cursor", "codex", "kiro", "vscode", "grok", "gemini"])
def test_as_pastas_dos_hosts_mantem_os_arquivos_do_usuario(repo, bundle, host):
    do_usuario = [write(repo / ".cursor" / "rules" / "mine.mdc", "c\n"), write(repo / ".codex" / "config.toml", "x\n"),
                  write(repo / ".kiro" / "steering" / "mine.md", "k\n"), write(repo / ".github" / "workflows" / "ci.yml", "ci\n")]
    instala(repo, bundle, host=host)
    desinstala(repo)
    for caminho in do_usuario:
        assert caminho.is_file(), f"uninstall --host {host} removed a user file: {caminho}"
    assert not (repo / ".claude" / "skills" / "simplicio-video").exists()


def test_escopo_global_mantem_skills_regras_e_arquivos_do_codex(tmp_path, bundle):
    casa = tmp_path / "casa"
    casa.mkdir()
    suas = [write(casa / ".claude" / "skills" / "minha-skill" / "SKILL.md", "m\n"), write(casa / ".claude" / "rules" / "mine.md", "r\n"),
            write(casa / ".codex" / "skills" / "minha-codex" / "SKILL.md", "c\n")]
    instala(casa, bundle, globally=True)
    desinstala(casa)
    assert all(p.is_file() for p in suas)
    assert not (casa / ".claude" / "skills" / "simplicio-video").exists()


def test_uninstall_dry_run_lista_o_que_sairia_e_nao_remove_nada(repo, bundle):
    minha = write(repo / ".claude" / "skills" / "minha-skill" / "SKILL.md", "m\n")
    instala(repo, bundle)
    antes = fotografia(repo)
    resultado = desinstala(repo, dry_run=True)
    assert resultado["status"] == "dry_run" and SKILL in resultado["removed"] and RECIBO in resultado["removed"]
    assert fotografia(repo) == antes and minha.is_file()
    assert desinstala(repo)["status"] == "removed"


def test_o_resultado_do_uninstall_tem_as_listas_do_loop(repo, bundle):
    instala(repo, bundle)
    write(repo / ".claude" / "skills" / "simplicio-video" / "minha.md", "m\n")  # a user file inside a folder we created
    resultado = desinstala(repo)
    assert set(resultado) == {"schema", "status", "removed", "removed_dirs", "kept", "skipped"}
    assert ".claude/skills/simplicio-video/references" in resultado["removed_dirs"]
    assert ".claude/skills/simplicio-video" in resultado["kept"] and (repo / ".claude/skills/simplicio-video/minha.md").is_file()


def test_sem_recibo_o_uninstall_nao_remove_nada(repo, bundle):
    instala(repo, bundle)
    (repo / RECIBO).unlink()
    with pytest.raises(installer.InstallError, match="recibo"):
        desinstala(repo)
    assert (repo / SKILL).is_file()


def test_recibo_com_esquema_desconhecido_falha_fechado_e_diz_o_que_fazer(repo, bundle):
    minha = write(repo / ".claude" / "skills" / "minha-skill" / "SKILL.md", "m\n")
    write(repo / RECIBO, json.dumps({"schema": "simplicio.video-install-ownership/v0", "owner": "simplicio-video",
                                     "paths": [".claude/skills"], "dirs": []}))
    with pytest.raises(installer.InstallError, match="esquema"):
        desinstala(repo)
    assert minha.is_file()


def tamper(raiz, **mudancas):
    caminho = raiz / RECIBO
    recibo = json.loads(caminho.read_text(encoding="utf-8"))
    recibo.update(mudancas)
    caminho.write_text(json.dumps(recibo), encoding="utf-8")


def recibo_de(raiz):
    return json.loads((raiz / RECIBO).read_text(encoding="utf-8"))


def _mais(raiz, chave, *itens):
    tamper(raiz, **{chave: recibo_de(raiz)[chave] + list(itens)})


def _elo(raiz, nome, alvo):
    (raiz / nome).symlink_to(alvo, target_is_directory=alvo.is_dir())


def _por_elo_de_pasta(raiz, fora):
    _elo(raiz, "docs", fora)
    _mais(raiz, "paths", "docs/keep.txt")


def _elo_folha(raiz, fora):
    _elo(raiz, "ln.txt", fora / "keep.txt")
    _mais(raiz, "paths", "ln.txt")


def _elo_de_pasta_como_arquivo(raiz, fora):
    _elo(raiz, "link", fora)
    _mais(raiz, "paths", "link")


def _elo_de_pasta_como_pasta(raiz, fora):
    _elo(raiz, "link", fora)
    _mais(raiz, "dirs", "link")


def _pasta_do_recibo_virou_elo(raiz, fora):
    pasta = raiz / ".simplicio-video"
    for filho in pasta.iterdir():
        if filho.name != "install-ownership.json":
            filho.unlink()
    tamper(raiz, dirs=recibo_de(raiz)["dirs"] + ["docs-elo"])
    _elo(raiz, "docs-elo", fora)


ADULTERACOES = [
    pytest.param(lambda r, o: _mais(r, "paths", str(o / "keep.txt")), True, id="paths-absoluto"),
    pytest.param(lambda r, o: _mais(r, "paths", "../outside/keep.txt"), True, id="paths-ponto-ponto"),
    pytest.param(lambda r, o: _mais(r, "paths", ".claude/../../outside/keep.txt"), True, id="paths-ponto-ponto-aninhado"),
    pytest.param(lambda r, o: _mais(r, "paths", "../*"), True, id="paths-ponto-ponto-glob"),
    pytest.param(lambda r, o: _mais(r, "paths", "."), True, id="paths-ponto"),
    pytest.param(lambda r, o: _mais(r, "paths", ""), True, id="paths-vazio"),
    pytest.param(lambda r, o: _mais(r, "paths", "/"), True, id="paths-raiz"),
    pytest.param(lambda r, o: _mais(r, "paths", "..\\outside\\keep.txt"), True, id="paths-ponto-ponto-do-windows"),
    pytest.param(lambda r, o: _mais(r, "paths", "C:\\Users\\x\\keep.txt"), True, id="paths-letra-de-unidade"),
    pytest.param(lambda r, o: _mais(r, "paths", "C:keep.txt"), True, id="paths-unidade-relativa"),
    pytest.param(lambda r, o: _mais(r, "paths", "\\outside\\keep.txt"), True, id="paths-raiz-do-windows"),
    pytest.param(lambda r, o: _mais(r, "paths", "\\\\servidor\\share\\keep.txt"), True, id="paths-unc"),
    pytest.param(lambda r, o: _mais(r, "dirs", "..\\outside"), True, id="dirs-ponto-ponto-do-windows"),
    pytest.param(_por_elo_de_pasta, True, id="paths-por-elo-de-pasta"),
    pytest.param(_elo_folha, False, id="paths-elo-folha-so-perde-o-elo"),
    pytest.param(_elo_de_pasta_como_arquivo, False, id="paths-elo-de-pasta-listado-como-arquivo"),
    pytest.param(lambda r, o: _mais(r, "paths", "*"), False, id="paths-glob-e-literal"),
    pytest.param(lambda r, o: tamper(r, paths=[1]), True, id="paths-item-inteiro"),
    pytest.param(lambda r, o: tamper(r, paths="abc"), True, id="paths-texto"),
    pytest.param(lambda r, o: tamper(r, paths=None), True, id="paths-nulo"),
    pytest.param(lambda r, o: _mais(r, "dirs", str(o)), True, id="dirs-absoluto-fora"),
    pytest.param(lambda r, o: _mais(r, "dirs", "../outside"), True, id="dirs-ponto-ponto"),
    pytest.param(lambda r, o: _mais(r, "dirs", "."), True, id="dirs-ponto"),
    pytest.param(_elo_de_pasta_como_pasta, False, id="dirs-elo-para-pasta-de-fora"),
    pytest.param(lambda r, o: tamper(r, dirs=[None]), True, id="dirs-item-nulo"),
    pytest.param(lambda r, o: tamper(r, dirs="x"), True, id="dirs-texto"),
    pytest.param(lambda r, o: tamper(r, owner="outro"), True, id="dono-adulterado"),
]


@posix_real
@pytest.mark.parametrize("adultera,recusado", ADULTERACOES)
def test_nenhum_recibo_adulterado_apaga_algo_fora_do_alvo(tmp_path, repo, bundle, adultera, recusado):
    fora = tmp_path / "outside"
    write(fora / "keep.txt", "keep\n")
    write(fora / "sub" / "keep2.txt", "keep2\n")
    instala(repo, bundle)
    antes = fotografia(fora)
    adultera(repo, fora)
    if recusado:
        with pytest.raises(installer.InstallError):
            desinstala(repo)
        assert (repo / SKILL).is_file(), "a refused receipt must leave our own files too"
    else:
        desinstala(repo)
    assert fotografia(fora) == antes


@pytest.mark.parametrize("corpo", ["{nao json", "", "[1, 2]", "null"])
def test_recibo_corrompido_e_recusado_e_nada_e_removido(repo, bundle, corpo):
    minha = write(repo / ".claude" / "skills" / "minha-skill" / "SKILL.md", "m\n")
    instala(repo, bundle)
    (repo / RECIBO).write_text(corpo, encoding="utf-8")
    with pytest.raises(installer.InstallError):
        desinstala(repo)
    assert minha.is_file() and (repo / SKILL).is_file()


def test_diretorio_registrado_como_arquivo_nunca_e_apagado_como_se_fosse_arquivo(repo, bundle):
    minha = write(repo / ".claude" / "skills" / "minha-skill" / "SKILL.md", "m\n")
    instala(repo, bundle)
    _mais(repo, "paths", ".claude/skills/minha-skill")
    resultado = desinstala(repo)
    assert minha.is_file() and ".claude/skills/minha-skill" in resultado["skipped"]


def test_um_alvo_alcancado_por_um_elo_ainda_e_desinstalado(tmp_path, repo, bundle):
    if os.name == "nt":
        pytest.skip("needs a POSIX symlink")
    instala(repo, bundle)
    via = tmp_path / "via"
    via.symlink_to(repo, target_is_directory=True)
    assert SKILL in desinstala(via)["removed"] and not (repo / SKILL).exists()


# --- verify ------------------------------------------------------------------------------------------------------------


def test_verify_confere_a_versao_do_pacote(repo):
    plano = installer.plan_install(repo, host="vscode")
    resposta = installer.verify_plan(plano)
    assert resposta["ok"] is True and resposta["digest"] == plano["digest"]
    with pytest.raises(installer.InstallError, match="versão"):
        installer.verify_plan(installer.plan_install(repo, host="vscode", version="0.0.1"))


# --- --prune-project-copies --------------------------------------------------------------------------------------------


def test_prune_remove_as_copias_do_projeto_e_preserva_o_que_e_do_usuario(repo, bundle):
    instala(repo, bundle, host="kiro")
    (repo / ".cursor" / "skills" / "simplicio-video").mkdir(parents=True)
    (repo / ".cursor" / "skills" / "simplicio-video" / "SKILL.md").write_text("velha\n", encoding="utf-8")
    write(repo / ".claude" / "settings.json", '{"meu": 1}')
    write(repo / ".claude" / "skills" / "minha-skill" / "SKILL.md", "m\n")
    seco = installer.prune_project_copies(repo, dry_run=True)
    assert seco["status"] == "dry_run" and SKILL in seco["removed"] and ".cursor/skills/simplicio-video/SKILL.md" in seco["removed"]
    assert RECIBO in seco["removed"] and ".kiro/steering/simplicio-video.md" in seco["removed"]
    assert (repo / SKILL).is_file(), "a dry run removes nothing"
    feito = installer.prune_project_copies(repo)
    assert feito["status"] == "removed" and not (repo / SKILL).exists() and not (repo / RECIBO).exists()
    assert (repo / ".claude" / "settings.json").is_file() and (repo / ".claude" / "skills" / "minha-skill" / "SKILL.md").is_file()
    assert ".claude/skills" in feito["kept"] and not (repo / ".cursor").exists()


def test_prune_nao_apaga_o_estado_de_outro_arquivo_em_simplicio_video(repo, bundle):
    instala(repo, bundle)
    estado = write(repo / ".simplicio-video" / "meu-estado.json", "{}")
    installer.prune_project_copies(repo)
    assert estado.is_file() and not (repo / RECIBO).exists()


# --- the files of this module name their encoding ----------------------------------------------------------------------


def test_o_planejador_so_usa_a_biblioteca_padrao():
    from _comum import ROOT
    import ast
    for nome in ("installer.py", "skill_sync.py"):
        arvore = ast.parse((ROOT / "src" / "simplicio_video" / nome).read_text(encoding="utf-8"))
        topo = set()
        for no in arvore.body:
            if isinstance(no, ast.Import):
                topo |= {a.name.split(".")[0] for a in no.names}
            elif isinstance(no, ast.ImportFrom) and no.level == 0 and no.module:
                topo.add(no.module.split(".")[0])
        assert topo <= set(__import__("sys").stdlib_module_names) | {"__future__"}, (nome, topo)
