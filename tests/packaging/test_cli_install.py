"""Contract of `simplicio-video install [--target DIR] [--global] [--host H] [--dry-run] [--check] [--json] [--verify]
[--uninstall] [--prune-project-copies]`: the skills go INTO the agent host, exactly like the `install` of simplicio-loop.

Breaking change (direct owner request: "faz igual ao simplicio-loop"): `install` was the `.venv` of the checkout (uv). That is now
`bash scripts/dev_install.sh` (Windows: `scripts/dev_install.ps1`, see test_dev_install.py). `install` copies the bundled skill to the
project (`.claude/skills`, plus the entry file of the host when it has one) or, with `--global`, to the home; it writes an ownership
receipt (`.simplicio-video/install-ownership.json`), never overwrites a file that is not its own (`left_alone`) and `--uninstall`
removes only what the receipt registers. The video has no hooks: only skills. `--check` exits 0 up to date and 10 when pending.
`--json` prints ONE `simplicio.video-install-plan/v1` document (the loop's keys), an error included.

Tests run in process with HOME, USERPROFILE and PATH sealed under tmp_path (`caixa`): never the real home.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys

import pytest

import _caixa
from _caixa import SISTEMAS, distribution, posix_real, roda_com_prazo, saida_cp1252, skill_sync, solta_fifo
from _comum import ROOT, erros_de_schema, executa, exige_registrado, fotografia, make_bundle, write
from simplicio_video import __version__
from simplicio_video.cli import main

caixa = _caixa.caixa
simula_so = _caixa.simula_so

RECIBO = ".simplicio-video/install-ownership.json"
SKILL = ".claude/skills/simplicio-video/SKILL.md"


@pytest.fixture
def falso(caixa, monkeypatch, tmp_path):
    """A tiny bundle instead of the real package data, and a target folder that exists."""
    pacote = make_bundle(tmp_path / "bundle")
    monkeypatch.setattr(distribution, "bundle_root", lambda: pacote, raising=False)
    alvo = tmp_path / "proj"
    alvo.mkdir()
    caixa.bundle, caixa.alvo = pacote, alvo
    return caixa


def _json(capsys, *argv):
    rc, out, err = executa(["install", "--json", *argv], capsys, main)
    try:
        doc = json.loads(out)
    except ValueError:
        pytest.fail(f"install --json did not print a single JSON document (rc {rc}).\nstdout={out!r}\nstderr={err!r}")
    return rc, doc, err


# --- --check ---------------------------------------------------------------------------------------------------------


def test_check_com_mudanca_pendente_sai_10_e_nao_escreve_nada(falso, capsys):
    exige_registrado("install", capsys, main)
    rc, out, err = executa(["install", "--check", "--target", str(falso.alvo)], capsys, main)
    assert rc == 10, out + err
    assert "check: há mudanças pendentes" in out and "3 criados" in out
    assert fotografia(falso.alvo) == {} and list(falso.home.iterdir()) == []


def test_check_em_dia_sai_0(falso, capsys):
    assert executa(["install", "--target", str(falso.alvo)], capsys, main)[0] == 0
    rc, out, err = executa(["install", "--check", "--target", str(falso.alvo)], capsys, main)
    assert rc == 0 and "check: em dia" in out and "0 criados, 0 atualizados, 3 iguais" in out


def test_check_volta_a_ficar_pendente_quando_o_pacote_muda(falso, capsys):
    executa(["install", "--target", str(falso.alvo)], capsys, main)
    (falso.bundle / "skills" / "simplicio-video" / "SKILL.md").write_text("video v2\n", encoding="utf-8")
    rc, out, err = executa(["install", "--check", "--target", str(falso.alvo)], capsys, main)
    assert rc == 10 and "2 atualizados" in out, "the skill and the receipt (its sha256 changed)"


# --- --dry-run -------------------------------------------------------------------------------------------------------


def test_dry_run_sai_0_mesmo_com_mudanca_pendente_e_nao_escreve_nada(falso, capsys):
    rc, out, err = executa(["install", "--dry-run", "--target", str(falso.alvo)], capsys, main)
    assert rc == 0, out + err
    assert "dry-run (nada foi escrito)" in out and "3 criados" in out
    assert fotografia(falso.alvo) == {} and list(falso.home.iterdir()) == []


# --- the real install ----------------------------------------------------------------------------------------------------


def test_instala_diz_o_que_mudou_e_depois_diz_que_ja_esta_em_dia(falso, capsys):
    rc, out, err = executa(["install", "--target", str(falso.alvo)], capsys, main)
    assert rc == 0, out + err
    assert f"simplicio-video {__version__} instalado:" in out and "3 criados, 0 atualizados, 0 iguais" in out
    assert "host" in out and "claude" in out and "criado: .claude/skills/simplicio-video/SKILL.md" in out
    assert "/simplicio-video" in out, "it says how to use the skill"
    assert (falso.alvo / SKILL).read_text(encoding="utf-8") == "video\n"
    rc, out, err = executa(["install", "--target", str(falso.alvo)], capsys, main)
    assert rc == 0 and "já está em dia" in out and "0 criados, 0 atualizados, 3 iguais" in out


def test_o_que_nao_e_do_video_e_dito_como_deixado_em_paz(falso, capsys):
    write(falso.alvo / ".claude" / "skills" / "minha" / "SKILL.md", "m\n")
    rc, out, err = executa(["install", "--target", str(falso.alvo)], capsys, main)
    assert rc == 0 and "deixado em paz" in out and ".claude/skills/minha" in out


def test_a_lista_de_deixados_em_paz_e_cortada_nos_limites_de_um_caminho(falso, capsys):
    for n in range(7):
        write(falso.alvo / ".claude" / "skills" / f"habilidade_do_usuario_numero_{n}" / "SKILL.md", "m\n")
    rc, out, err = executa(["install", "--target", str(falso.alvo)], capsys, main)
    linha = next(l for l in out.splitlines() if "deixado em paz" in l)
    assert "7 que não são do simplicio-video" in linha and "(+" in linha and "mais)" in linha
    assert not linha.rstrip().endswith("habilidade_do_usuario_nu")


def test_a_lista_de_criados_tem_no_maximo_oito_linhas_e_diz_quantos_faltam(falso, capsys):
    for n in range(12):
        write(falso.bundle / "skills" / "simplicio-video" / "references" / f"r{n:02d}.md", f"r{n}\n")
    rc, out, err = executa(["install", "--target", str(falso.alvo)], capsys, main)
    assert out.count("    criado: ") == 9 and "e mais 7" in out  # 15 created: 8 shown + the "and N more" line


def test_host_codex_escreve_o_agents_md_e_o_uninstall_leva_embora(falso, capsys):
    rc, out, err = executa(["install", "--host", "codex", "--target", str(falso.alvo)], capsys, main)
    assert rc == 0 and (falso.alvo / "AGENTS.md").is_file() and "AGENTS.md" in out
    rc, out, err = executa(["install", "--uninstall", "--target", str(falso.alvo)], capsys, main)
    assert rc == 0 and fotografia(falso.alvo) == {}


def test_agents_md_do_usuario_nunca_e_sobrescrito(falso, capsys):
    write(falso.alvo / "AGENTS.md", "# meu\n")
    rc, out, err = executa(["install", "--host", "codex", "--target", str(falso.alvo)], capsys, main)
    assert rc == 0 and "deixado em paz" in out and "AGENTS.md" in out
    assert (falso.alvo / "AGENTS.md").read_text(encoding="utf-8") == "# meu\n"


def test_o_alvo_padrao_e_a_pasta_atual(falso, capsys, monkeypatch):
    monkeypatch.chdir(falso.alvo)
    rc, out, err = executa(["install"], capsys, main)
    assert rc == 0 and (falso.alvo / SKILL).is_file()


def test_com_o_pacote_de_verdade_instala_igual_ao_do_pacote_e_e_idempotente(caixa, capsys, tmp_path):
    alvo = tmp_path / "proj"
    alvo.mkdir()
    assert executa(["install", "--target", str(alvo)], capsys, main)[0] == 0
    rc, out, err = executa(["install", "--check", "--target", str(alvo)], capsys, main)
    assert rc == 0 and "0 criados, 0 atualizados" in out
    for nome in skill_sync.SKILLS:
        real = ROOT / "src" / "simplicio_video" / "data" / "skills" / nome / "SKILL.md"
        assert (alvo / ".claude" / "skills" / nome / "SKILL.md").read_bytes() == real.read_bytes()


# --- --json ----------------------------------------------------------------------------------------------------------


def test_json_do_check_tem_as_chaves_do_loop_e_fecha_com_o_schema(falso, capsys):
    rc, doc, err = _json(capsys, "--check", "--target", str(falso.alvo))
    assert rc == 10 and erros_de_schema("install-plan", doc) == [], doc
    assert doc["schema"] == "simplicio.video-install-plan/v1" and doc["status"] == "dry_run"
    assert doc["up_to_date"] is False and doc["host"] == "claude" and doc["version"] == __version__
    assert len(doc["changes"]["created"]) == 3 and doc["changes"]["unchanged"] == 0
    assert set(doc["changes"]) == {"created", "updated", "unchanged", "left_alone"}
    assert doc["digest"].startswith("sha256:") and doc["resynced"] is None
    assert {"owned", "ownership", "written"} <= set(doc)


def test_json_do_dry_run_sai_0_e_do_install_real_diz_applied(falso, capsys):
    rc, doc, _ = _json(capsys, "--dry-run", "--target", str(falso.alvo))
    assert rc == 0 and doc["status"] == "dry_run" and fotografia(falso.alvo) == {}
    rc, doc, _ = _json(capsys, "--target", str(falso.alvo))
    assert rc == 0 and doc["status"] == "applied" and doc["written"] == 3 and erros_de_schema("install-plan", doc) == []
    rc, doc, _ = _json(capsys, "--check", "--target", str(falso.alvo))
    assert rc == 0 and doc["up_to_date"] is True and doc["changes"]["unchanged"] == 3


def test_json_so_tem_o_documento_no_stdout(falso, capfd):
    rc = main(["install", "--json", "--target", str(falso.alvo)])
    out, err = capfd.readouterr()
    assert rc == 0 and json.loads(out)["status"] == "applied" and err == ""


def test_json_e_host_escolhido_aparece_no_documento(falso, capsys):
    rc, doc, _ = _json(capsys, "--host", "gemini", "--target", str(falso.alvo))
    assert rc == 0 and doc["host"] == "gemini" and "GEMINI.md" in doc["owned"]


# --- errors: exit 1 for a failed install, exit 2 for a bad argument, one document with --json ------------------------------------


def test_host_desconhecido_sai_1_e_nao_escreve_nada(falso, capsys):
    rc, out, err = executa(["install", "--host", "nao-existe", "--target", str(falso.alvo)], capsys, main)
    assert rc == 1 and "host desconhecido: nao-existe" in out + err and "Traceback" not in out + err
    assert fotografia(falso.alvo) == {}


def test_host_desconhecido_com_json_imprime_um_documento_de_erro(falso, capsys):
    rc, doc, err = _json(capsys, "--host", "nao-existe", "--target", str(falso.alvo))
    assert rc == 1 and erros_de_schema("install-plan", doc) == [], doc
    assert doc["status"] == "error" and "host desconhecido" in doc["error"] and doc["error"] in err
    assert doc["schema"] == "simplicio.video-install-plan/v1" and doc["version"] == __version__


def test_pacote_sem_skills_sai_1_com_a_mensagem(caixa, capsys, monkeypatch, tmp_path):
    vazio = tmp_path / "vazio"
    vazio.mkdir()
    monkeypatch.setattr(distribution, "bundle_root", lambda: vazio, raising=False)
    rc, out, err = executa(["install", "--target", str(tmp_path)], capsys, main)
    assert rc == 1 and "skills" in out + err and "Traceback" not in out + err


def test_escrita_negada_sai_1_sem_traceback_e_com_json_valido(falso, capsys, monkeypatch):
    def nega(*a, **kw):
        raise PermissionError(13, "Permission denied", "x")

    monkeypatch.setattr(os, "replace", nega)
    rc, out, err = executa(["install", "--target", str(falso.alvo)], capsys, main)
    assert rc == 1 and "Permission denied" in out + err and "Traceback" not in out + err
    rc, doc, _ = _json(capsys, "--target", str(falso.alvo))
    assert rc == 1 and doc["status"] == "error" and erros_de_schema("install-plan", doc) == []
    assert not [p for p in falso.alvo.rglob("*") if p.name.endswith(".tmp")]


def test_prune_sem_global_e_argumento_invalido_sai_2(falso, capsys):
    rc, out, err = executa(["install", "--prune-project-copies", "--target", str(falso.alvo)], capsys, main)
    assert rc == 2 and "--global" in out + err and fotografia(falso.alvo) == {}


def test_flag_desconhecida_sai_2(falso, capsys):
    rc, out, err = executa(["install", "--venv"], capsys, main)
    assert rc == 2, "the old --python and --with of the .venv install are gone (scripts/dev_install.sh has them)"
    for antiga in ("--python", "--with"):
        assert executa(["install", antiga, "3.12"], capsys, main)[0] == 2


# --- --verify: it compares the files with the receipt and with the package ---------------------------------------------------------


def test_verify_depois_do_install_sai_0_e_nao_escreve_nada(falso, capsys):
    executa(["install", "--host", "vscode", "--target", str(falso.alvo)], capsys, main)
    antes = fotografia(falso.alvo)
    rc, out, err = executa(["install", "--verify", "--host", "vscode", "--target", str(falso.alvo)], capsys, main)
    assert rc == 0 and "plano ok" in out and "host=vscode" in out and "digest=sha256:" in out
    assert fotografia(falso.alvo) == antes


def test_verify_com_json_imprime_um_documento_e_ok_true(falso, capsys):
    executa(["install", "--target", str(falso.alvo)], capsys, main)
    rc, doc, _ = _json(capsys, "--verify", "--target", str(falso.alvo))
    assert rc == 0 and erros_de_schema("install-plan", doc) == [], doc
    assert doc["status"] == "verified" and doc["ok"] is True and doc["host"] == "claude" and doc["version"] == __version__
    assert doc["problems"] == []


def test_verify_de_um_alvo_nunca_instalado_sai_1_com_ok_false_e_a_lista(falso, capsys):
    rc, doc, err = _json(capsys, "--verify", "--target", str(falso.alvo))
    assert rc == 1 and erros_de_schema("install-plan", doc) == [], doc
    assert doc["status"] == "failed" and doc["ok"] is False and doc["version"] == __version__ and doc["host"] == "claude"
    assert {(p["path"], p["problem"]) for p in doc["problems"]} >= {(RECIBO, "no_receipt"), (SKILL, "missing")}
    assert fotografia(falso.alvo) == {}
    rc, out, err = executa(["install", "--verify", "--target", str(falso.alvo)], capsys, main)
    assert rc == 1 and SKILL in out and "falta" in out and "Traceback" not in out + err


def test_verify_com_a_skill_adulterada_sai_1_e_diz_qual_arquivo(falso, capsys):
    executa(["install", "--target", str(falso.alvo)], capsys, main)
    (falso.alvo / SKILL).write_text("poste sem confirmar\n", encoding="utf-8")
    rc, doc, _ = _json(capsys, "--verify", "--target", str(falso.alvo))
    assert rc == 1 and doc["ok"] is False and [(p["path"], p["problem"]) for p in doc["problems"]] == [(SKILL, "modified")]
    rc, out, err = executa(["install", "--verify", "--target", str(falso.alvo)], capsys, main)
    assert rc == 1 and SKILL in out and "modificado" in out


def test_verify_com_o_recibo_trocado_por_lixo_sai_1(falso, capsys):
    executa(["install", "--target", str(falso.alvo)], capsys, main)
    (falso.alvo / RECIBO).write_text("lixo", encoding="utf-8")
    rc, doc, _ = _json(capsys, "--verify", "--target", str(falso.alvo))
    assert rc == 1 and doc["ok"] is False and (RECIBO, "bad_receipt") in {(p["path"], p["problem"]) for p in doc["problems"]}


def test_verify_depois_de_um_pacote_novo_diz_que_esta_desatualizado(falso, capsys):
    executa(["install", "--target", str(falso.alvo)], capsys, main)
    (falso.bundle / "skills" / "simplicio-video" / "SKILL.md").write_text("video v2\n", encoding="utf-8")
    rc, out, err = executa(["install", "--verify", "--target", str(falso.alvo)], capsys, main)
    assert rc == 1 and "desatualizado" in out and "simplicio-video install" in out


def test_verify_com_host_desconhecido_sai_1(falso, capsys):
    rc, out, err = executa(["install", "--verify", "--host", "x", "--target", str(falso.alvo)], capsys, main)
    assert rc == 1 and "host desconhecido" in out + err


def test_verify_global_confere_o_home_e_nao_o_alvo(falso, capsys):
    assert executa(["install", "--verify", "--global"], capsys, main)[0] == 1
    executa(["install", "--global"], capsys, main)
    assert executa(["install", "--verify", "--global"], capsys, main)[0] == 0
    (falso.home / SKILL).write_text("adulterada\n", encoding="utf-8")
    assert executa(["install", "--verify", "--global"], capsys, main)[0] == 1


# --- --uninstall ---------------------------------------------------------------------------------------------------------


def test_uninstall_remove_so_o_do_recibo_e_o_dry_run_nao_remove_nada(falso, capsys):
    minha = write(falso.alvo / ".claude" / "skills" / "minha" / "SKILL.md", "m\n")
    executa(["install", "--target", str(falso.alvo)], capsys, main)
    antes = fotografia(falso.alvo)
    rc, out, err = executa(["install", "--uninstall", "--dry-run", "--target", str(falso.alvo)], capsys, main)
    assert rc == 0 and "dry-run" in out and "SKILL.md" in out and fotografia(falso.alvo) == antes
    rc, out, err = executa(["install", "--uninstall", "--target", str(falso.alvo)], capsys, main)
    assert rc == 0 and "removidos 3 arquivos" in out and minha.is_file()
    assert not (falso.alvo / ".claude" / "skills" / "simplicio-video").exists() and not (falso.alvo / ".simplicio-video").exists()


def test_uninstall_sem_recibo_sai_1_e_nao_remove_nada(falso, capsys):
    write(falso.alvo / SKILL, "do usuario\n")
    rc, out, err = executa(["install", "--uninstall", "--target", str(falso.alvo)], capsys, main)
    assert rc == 1 and "recibo" in out + err and (falso.alvo / SKILL).read_text(encoding="utf-8") == "do usuario\n"


def test_uninstall_com_json_imprime_um_documento(falso, capsys):
    executa(["install", "--target", str(falso.alvo)], capsys, main)
    rc, doc, _ = _json(capsys, "--uninstall", "--dry-run", "--target", str(falso.alvo))
    assert rc == 0 and erros_de_schema("install-plan", doc) == [], doc
    assert doc["status"] == "dry_run" and SKILL in doc["removed"]
    rc, doc, _ = _json(capsys, "--uninstall", "--target", str(falso.alvo))
    assert rc == 0 and doc["status"] == "removed" and RECIBO in doc["removed"]
    rc, doc, _ = _json(capsys, "--uninstall", "--target", str(falso.alvo))
    assert rc == 1 and doc["status"] == "error" and erros_de_schema("install-plan", doc) == []


def test_uninstall_global_diz_o_que_fica_fora_do_recibo(falso, capsys):
    executa(["install", "--global"], capsys, main)
    rc, out, err = executa(["install", "--uninstall", "--global"], capsys, main)
    assert rc == 0 and "fora do recibo" in out and "simplicio-video" in out
    executa(["install", "--target", str(falso.alvo)], capsys, main)
    rc, out, err = executa(["install", "--uninstall", "--target", str(falso.alvo)], capsys, main)
    assert rc == 0 and "fora do recibo" not in out


# --- --global: the home, and the hosts that already have the skill ------------------------------------------------------------


def test_global_instala_no_home_e_nao_toca_no_alvo(falso, capsys):
    rc, out, err = executa(["install", "--global", "--target", str(falso.alvo)], capsys, main)
    assert rc == 0, out + err
    assert (falso.home / SKILL).is_file() and (falso.home / RECIBO).is_file() and fotografia(falso.alvo) == {}


def test_global_com_qualquer_host_escreve_so_em_claude_skills(falso, capsys):
    rc, out, err = executa(["install", "--global", "--host", "codex"], capsys, main)
    assert rc == 0 and (falso.home / SKILL).is_file() and not (falso.home / "AGENTS.md").exists()


def test_global_nao_mexe_na_copia_de_outro_host_e_diz_que_a_deixou_em_paz(falso, capsys):
    """The copy of another host is not in the receipt: it is not ours to overwrite (the loop refreshes it, ADR-0020)."""
    velha = falso.home / ".codex" / "skills" / "simplicio-video"
    write(velha / "SKILL.md", "release antiga\n")
    notas = write(velha / "minhas-notas.md", "notas do usuário\n")
    rc, out, err = executa(["install", "--global"], capsys, main)
    assert rc == 0, out + err
    assert "deixadas em paz" in out and "codex (1)" in out
    assert (velha / "SKILL.md").read_text(encoding="utf-8") == "release antiga\n" and notas.read_text(encoding="utf-8") == "notas do usuário\n"
    assert (falso.home / SKILL).is_file()


def test_global_check_nao_fica_pendente_por_causa_da_copia_de_outro_host(falso, capsys):
    """The home itself is up to date; another host's old copy is something `install` will never change, so it cannot keep `--check` at 10."""
    assert executa(["install", "--global"], capsys, main)[0] == 0
    write(falso.home / ".codex" / "skills" / "simplicio-video" / "SKILL.md", "release antiga\n")
    rc, out, err = executa(["install", "--global", "--check"], capsys, main)
    assert rc == 0 and "codex (1)" in out and "0 criados, 0 atualizados" in out, out + err
    rc, doc, _ = _json(capsys, "--global", "--check")
    assert rc == 0 and doc["up_to_date"] is True and doc["resynced"]["pending"] == 0 and doc["resynced"]["skills"] == ["codex"]


def test_global_json_traz_o_resynced_com_as_chaves_do_loop(falso, capsys):
    write(falso.home / ".cursor" / "skills" / "simplicio-video" / "SKILL.md", "release antiga\n")
    rc, doc, _ = _json(capsys, "--global", "--check")
    assert rc == 10 and erros_de_schema("install-plan", doc) == [], doc  # 10: the home itself has nothing installed yet
    assert set(doc["resynced"]) == {"skills", "rules", "skills_counts", "rules_counts", "errors", "pending"}
    assert doc["resynced"]["skills"] == ["cursor"] and doc["resynced"]["pending"] == 0 and doc["resynced"]["rules"] == []
    assert doc["resynced"]["skills_counts"] == {"cursor": 1}, "the fake bundle of the fixture has one skill, and the copy differs in it"


def test_global_nao_apaga_arquivo_do_usuario_dentro_da_pasta_da_skill_nem_nas_copias_dos_hosts(falso, capsys):
    """Review of #117: `minhas-notas.md` vanished from ~/.claude and ~/.codex, and `update` (pip) did it by itself."""
    executa(["install", "--global"], capsys, main)
    notas_claude = write(falso.home / ".claude" / "skills" / "simplicio-video" / "minhas-notas.md", "notas\n")
    notas_codex = write(falso.home / ".codex" / "skills" / "simplicio-video" / "minhas-notas.md", "notas\n")
    write(falso.home / ".codex" / "skills" / "simplicio-video" / "SKILL.md", "release antiga\n")
    (falso.bundle / "skills" / "simplicio-video" / "SKILL.md").write_text("video v2\n", encoding="utf-8")
    for _ in range(2):
        rc, out, err = executa(["install", "--global"], capsys, main)
        assert rc == 0, out + err
    assert notas_claude.read_text(encoding="utf-8") == "notas\n" and notas_codex.read_text(encoding="utf-8") == "notas\n"
    assert (falso.home / SKILL).read_text(encoding="utf-8") == "video v2\n", "our own file is still updated"
    assert "minhas-notas.md" in out, "it says it left the user's file alone"


def test_global_em_dia_sai_0_no_check_mesmo_com_hosts_instalados(falso, capsys):
    executa(["install", "--global"], capsys, main)
    write(falso.home / ".grok" / "skills" / "simplicio-video" / "SKILL.md", "video\n")
    write(falso.home / ".grok" / "skills" / "simplicio-video" / "references" / "a.md", "ref a\n")
    assert executa(["install", "--global", "--check"], capsys, main)[0] == 0


def test_global_prune_remove_as_copias_do_projeto_e_diz_quantas(falso, capsys):
    assert executa(["install", "--target", str(falso.alvo)], capsys, main)[0] == 0  # the project copy, with its receipt
    obsoleta = falso.alvo / SKILL
    do_usuario = write(falso.alvo / ".claude" / "settings.json", "{}")
    rc, out, err = executa(["install", "--global", "--prune-project-copies", "--check", "--target", str(falso.alvo)], capsys, main)
    assert rc == 10 and "podaria" in out and obsoleta.is_file(), "--check removes nothing"
    rc, out, err = executa(["install", "--global", "--prune-project-copies", "--target", str(falso.alvo)], capsys, main)
    assert rc == 0 and "podadas" in out and not obsoleta.exists() and do_usuario.is_file()
    assert (falso.home / SKILL).is_file()


def test_global_prune_json_traz_pruned_project(falso, capsys):
    executa(["install", "--target", str(falso.alvo)], capsys, main)
    rc, doc, _ = _json(capsys, "--global", "--prune-project-copies", "--target", str(falso.alvo))
    assert rc == 0 and doc["pruned_project"]["status"] == "removed" and erros_de_schema("install-plan", doc) == []
    assert SKILL in doc["pruned_project"]["removed"]


def test_prune_nao_apaga_a_copia_do_projeto_que_nenhum_recibo_registra(falso, capsys):
    copia = write(falso.alvo / SKILL, "velha\n")
    rc, out, err = executa(["install", "--global", "--prune-project-copies", "--target", str(falso.alvo)], capsys, main)
    assert rc == 0 and copia.read_text(encoding="utf-8") == "velha\n" and (falso.home / SKILL).is_file()


def test_prune_com_o_alvo_igual_ao_home_sai_2_e_nao_apaga_a_instalacao_global(falso, capsys, monkeypatch):
    """Review of #117: from the home (`--target` defaults to `.`), the prune deleted the global install it had just written."""
    assert executa(["install", "--global"], capsys, main)[0] == 0
    monkeypatch.chdir(falso.home)
    antes = fotografia(falso.home)
    rc, out, err = executa(["install", "--global", "--prune-project-copies"], capsys, main)
    assert rc == 2 and "--prune-project-copies" in out + err and "home" in out + err
    assert fotografia(falso.home) == antes and (falso.home / SKILL).is_file()
    rc, doc, _ = _json(capsys, "--global", "--prune-project-copies", "--target", str(falso.home))
    assert rc == 2 and doc["status"] == "error" and erros_de_schema("install-plan", doc) == []


@posix_real
def test_prune_com_o_alvo_que_e_um_link_para_o_home_tambem_sai_2(falso, capsys):
    executa(["install", "--global"], capsys, main)
    via = falso.tmp / "via"
    via.symlink_to(falso.home, target_is_directory=True)
    rc, out, err = executa(["install", "--global", "--prune-project-copies", "--target", str(via)], capsys, main)
    assert rc == 2 and (falso.home / SKILL).is_file()


@posix_real
def test_prune_nao_leva_embora_a_instalacao_global_quando_o_claude_do_projeto_e_link_para_o_do_home(falso, capsys):
    (falso.home / ".claude").mkdir()
    (falso.alvo / ".claude").symlink_to(falso.home / ".claude", target_is_directory=True)
    assert executa(["install", "--target", str(falso.alvo)], capsys, main)[0] == 0
    rc, out, err = executa(["install", "--global", "--prune-project-copies", "--target", str(falso.alvo)], capsys, main)
    assert rc == 0, out + err
    assert (falso.home / SKILL).is_file() and executa(["install", "--global", "--check"], capsys, main)[0] == 0


@pytest.mark.parametrize("so", SISTEMAS)
def test_global_acha_o_home_por_home_e_depois_por_userprofile_em_todo_sistema(falso, capsys, simula_so, monkeypatch, so):
    simula_so(so)
    outro = falso.tmp / "so-userprofile"
    outro.mkdir()
    monkeypatch.delenv("HOME")
    monkeypatch.setenv("USERPROFILE", str(outro))
    monkeypatch.setattr("pathlib.Path.home", classmethod(lambda cls: falso.tmp / "nao-usar"))
    rc, out, err = executa(["install", "--global"], capsys, main)
    assert rc == 0 and (outro / SKILL).is_file() and not (falso.home / ".claude").exists()


# --- the end of the install: the setup, as the loop's `after_install` ----------------------------------------------------------


def test_sem_terminal_e_sem_workspace_diz_para_rodar_o_setup(falso, capsys):
    rc, out, err = executa(["install", "--target", str(falso.alvo)], capsys, main)
    assert rc == 0 and "simplicio-video setup" in out


def test_com_workspace_pronto_nao_fala_do_setup(falso, capsys):
    write(falso.workspace / "workspace.yaml", "schema: simplicio.workspace/v1\n")
    write(falso.workspace / "policy.yaml", "schema: simplicio.policy/v1\n")
    rc, out, err = executa(["install", "--target", str(falso.alvo)], capsys, main)
    assert rc == 0 and "simplicio-video setup" not in out


def test_com_terminal_e_sem_workspace_roda_o_setup_pelo_executor_injetado(falso, capsys):
    chamadas = []
    install = _caixa.install_cmd
    install.after_install(interactive=True, runner=lambda argv: chamadas.append(list(argv)) or 0)
    assert chamadas == [[sys.executable, "-m", "simplicio_video", "setup"]]
    install.after_install(interactive=False, runner=lambda argv: chamadas.append(list(argv)) or 0)
    assert len(chamadas) == 1, "no terminal, no setup run: only the hint"
    out = capsys.readouterr().out
    assert "simplicio-video setup" in out


def test_o_setup_que_falha_nao_derruba_o_install(falso, capsys):
    install = _caixa.install_cmd
    install.after_install(interactive=True, runner=lambda argv: 3)
    assert "setup" in capsys.readouterr().out


@pytest.mark.parametrize("opcao", ["--check", "--dry-run"])
def test_check_e_dry_run_nunca_rodam_o_setup(falso, capsys, monkeypatch, opcao):
    chamadas = []
    monkeypatch.setattr(_caixa.install_cmd, "_run_setup", lambda argv: chamadas.append(argv) or 0)
    monkeypatch.setattr(_caixa.install_cmd, "_terminal", lambda: True)
    executa(["install", opcao, "--target", str(falso.alvo)], capsys, main)
    assert chamadas == []


def test_num_terminal_o_install_de_verdade_roda_o_setup(falso, capsys, monkeypatch):
    chamadas = []
    monkeypatch.setattr(_caixa.install_cmd, "_run_setup", lambda argv: chamadas.append(list(argv)) or 0)
    monkeypatch.setattr(_caixa.install_cmd, "_terminal", lambda: True)
    rc, out, err = executa(["install", "--target", str(falso.alvo)], capsys, main)
    assert rc == 0 and chamadas == [[sys.executable, "-m", "simplicio_video", "setup"]]


def test_o_install_ja_em_dia_tambem_nao_insiste_no_setup_quando_ele_ja_rodou(falso, capsys):
    write(falso.workspace / "workspace.yaml", "x: 1\n")
    write(falso.workspace / "policy.yaml", "x: 1\n")
    executa(["install", "--target", str(falso.alvo)], capsys, main)
    rc, out, err = executa(["install", "--target", str(falso.alvo)], capsys, main)
    assert "simplicio-video setup" not in out


# --- the distribution does not matter: a pip package installs the skills too ---------------------------------------------------


@pytest.mark.parametrize("tipo", ["source", "pip"])
def test_pacote_pip_e_checkout_instalam_as_skills_do_mesmo_jeito(falso, capsys, monkeypatch, tipo):
    monkeypatch.setattr(distribution, "kind", lambda **kw: tipo)
    rc, out, err = executa(["install", "--target", str(falso.alvo)], capsys, main)
    assert rc == 0 and (falso.alvo / SKILL).is_file()
    assert executa(["install", "--check", "--target", str(falso.alvo)], capsys, main)[0] == 0


# --- hostile things where the install writes ------------------------------------------------------------------------------------


def test_uma_pasta_no_lugar_da_skill_fica_em_paz_e_nao_trava_nem_cai(falso, capsys):
    (falso.alvo / ".claude" / "skills" / "simplicio-video" / "SKILL.md").mkdir(parents=True)
    rc, out, err = executa(["install", "--target", str(falso.alvo)], capsys, main)
    assert rc == 0 and "Traceback" not in out + err and (falso.alvo / SKILL).is_dir()
    assert SKILL in out, "it says it left the folder alone"


@posix_real
def test_um_fifo_no_lugar_da_skill_nao_trava_e_fica_em_paz(falso, capsys):
    destino = falso.alvo / SKILL
    destino.parent.mkdir(parents=True)
    os.mkfifo(destino)
    rc, out, err = roda_com_prazo(lambda: executa(["install", "--target", str(falso.alvo)], capsys, main),
                                  destravar=lambda: solta_fifo(destino))
    assert rc == 0 and "Traceback" not in out + err


@posix_real
def test_um_fifo_no_lugar_do_recibo_nao_trava_a_instalacao(falso, capsys):
    recibo = falso.alvo / RECIBO
    recibo.parent.mkdir(parents=True)
    os.mkfifo(recibo)
    rc, out, err = roda_com_prazo(lambda: executa(["install", "--target", str(falso.alvo)], capsys, main),
                                  destravar=lambda: solta_fifo(recibo))
    assert rc in (0, 1) and "Traceback" not in out + err


def test_o_alvo_que_e_um_arquivo_sai_1_sem_traceback(falso, capsys):
    arquivo = write(falso.tmp / "arquivo.txt", "x\n")
    rc, out, err = executa(["install", "--target", str(arquivo)], capsys, main)
    assert rc == 1 and "Traceback" not in out + err


# --- review of #117: links, receipts and files that were already there ---------------------------------------------------------------


@posix_real
def test_claude_skills_que_e_link_sai_2_com_o_motivo_e_nada_e_escrito(falso, capsys):
    fora = falso.tmp / "dotfiles"
    fora.mkdir()
    (falso.alvo / ".claude").mkdir()
    (falso.alvo / ".claude" / "skills").symlink_to(fora, target_is_directory=True)
    rc, out, err = executa(["install", "--target", str(falso.alvo)], capsys, main)
    assert rc == 2 and ".claude/skills" in out + err and "link" in out + err and "Traceback" not in out + err
    rc, doc, err = _json(capsys, "--target", str(falso.alvo))
    assert rc == 2 and doc["status"] == "error" and "link" in doc["error"] and erros_de_schema("install-plan", doc) == []
    assert fotografia(fora) == {} and not (falso.alvo / ".simplicio-video").exists()
    assert executa(["install", "--check", "--target", str(falso.alvo)], capsys, main)[0] == 2


@posix_real
def test_claude_que_e_link_de_dotfiles_instala_confere_e_desinstala_pelo_cli(falso, capsys):
    dotfiles = falso.tmp / "dotfiles"
    dotfiles.mkdir()
    (falso.alvo / ".claude").symlink_to(dotfiles, target_is_directory=True)
    assert executa(["install", "--target", str(falso.alvo)], capsys, main)[0] == 0
    assert (dotfiles / "skills" / "simplicio-video" / "SKILL.md").is_file()
    assert executa(["install", "--check", "--target", str(falso.alvo)], capsys, main)[0] == 0
    assert executa(["install", "--verify", "--target", str(falso.alvo)], capsys, main)[0] == 0
    rc, out, err = executa(["install", "--uninstall", "--target", str(falso.alvo)], capsys, main)
    assert rc == 0 and fotografia(dotfiles) == {}, out + err


def test_o_primeiro_install_nao_sobrescreve_a_skill_customizada_e_diz_como_assumir(falso, capsys):
    custom = write(falso.alvo / SKILL, "a minha skill\n")
    rc, out, err = executa(["install", "--target", str(falso.alvo)], capsys, main)
    assert rc == 0 and custom.read_text(encoding="utf-8") == "a minha skill\n"
    assert "deixado em paz" in out and SKILL in out
    assert "apague" in out, "it says how to let the install take the folder over"
    rc, out, err = executa(["install", "--uninstall", "--target", str(falso.alvo)], capsys, main)
    assert rc == 0 and custom.read_text(encoding="utf-8") == "a minha skill\n"


def test_um_arquivo_do_usuario_dentro_da_pasta_da_skill_nao_ganha_a_dica_de_apagar_a_pasta(falso, capsys):
    """"Delete the folder and install again" is for a skill file that was in the way, never for the user's own note beside ours."""
    write(falso.alvo / ".claude" / "skills" / "simplicio-video" / "minhas-notas.md", "notas\n")
    rc, out, err = executa(["install", "--target", str(falso.alvo)], capsys, main)
    assert rc == 0 and "minhas-notas.md" in out and "deixado em paz" in out
    assert "apague-a" not in out, out
    assert (falso.alvo / ".claude" / "skills" / "simplicio-video" / "minhas-notas.md").is_file()


def test_uninstall_diz_o_que_deixou_porque_o_usuario_editou(falso, capsys):
    executa(["install", "--host", "codex", "--target", str(falso.alvo)], capsys, main)
    (falso.alvo / "AGENTS.md").write_text("# as minhas regras\n", encoding="utf-8")
    rc, out, err = executa(["install", "--uninstall", "--target", str(falso.alvo)], capsys, main)
    assert rc == 0 and "AGENTS.md" in out and "editado" in out
    assert (falso.alvo / "AGENTS.md").read_text(encoding="utf-8") == "# as minhas regras\n"
    (falso.alvo / "AGENTS.md").unlink()
    executa(["install", "--host", "codex", "--target", str(falso.alvo)], capsys, main)  # ours again: created by this install
    (falso.alvo / "AGENTS.md").write_text("# de novo\n", encoding="utf-8")
    rc, doc, _ = _json(capsys, "--uninstall", "--target", str(falso.alvo))
    assert rc == 0 and doc["left_alone"] == ["AGENTS.md"] and doc["warnings"] and erros_de_schema("install-plan", doc) == [], doc


def test_recibo_plantado_no_repo_faz_o_uninstall_sair_1_sem_apagar_nada(falso, capsys):
    notas = write(falso.alvo / "notes.md", "do repositório\n")
    executa(["install", "--target", str(falso.alvo)], capsys, main)
    recibo = json.loads((falso.alvo / RECIBO).read_text(encoding="utf-8"))
    recibo["paths"].append("notes.md")
    recibo["sha256"]["notes.md"] = "0" * 64
    (falso.alvo / RECIBO).write_text(json.dumps(recibo), encoding="utf-8")
    rc, doc, err = _json(capsys, "--uninstall", "--target", str(falso.alvo))
    assert rc == 1 and doc["status"] == "error" and "recibo" in doc["error"] and erros_de_schema("install-plan", doc) == []
    assert notas.is_file() and (falso.alvo / SKILL).is_file()


def test_recibo_no_home_com_authorized_keys_nao_apaga_a_chave_no_uninstall_global(falso, capsys):
    chave = write(falso.home / ".ssh" / "authorized_keys", "ssh-ed25519 AAAA fake\n")
    executa(["install", "--global"], capsys, main)
    recibo = json.loads((falso.home / RECIBO).read_text(encoding="utf-8"))
    recibo["paths"].append(".ssh/authorized_keys")
    recibo["sha256"][".ssh/authorized_keys"] = hashlib.sha256(chave.read_bytes()).hexdigest()
    (falso.home / RECIBO).write_text(json.dumps(recibo), encoding="utf-8")
    rc, out, err = executa(["install", "--uninstall", "--global"], capsys, main)
    assert rc == 1 and "recibo" in out + err and chave.read_text(encoding="utf-8") == "ssh-ed25519 AAAA fake\n"
    assert (falso.home / SKILL).is_file()


@pytest.mark.parametrize("rel", ["a\u0000b/c", "x" * 5000])
def test_recibo_com_nul_ou_gigante_nao_vira_traceback_em_nenhum_modo(falso, capsys, rel):
    executa(["install", "--target", str(falso.alvo)], capsys, main)
    recibo = json.loads((falso.alvo / RECIBO).read_text(encoding="utf-8"))
    recibo["paths"] = [rel]
    (falso.alvo / RECIBO).write_text(json.dumps(recibo), encoding="utf-8")
    for opcao in ("--uninstall", "--uninstall --dry-run", "--verify"):
        rc, out, err = executa(["install", *opcao.split(), "--target", str(falso.alvo)], capsys, main)
        assert rc == 1 and "Traceback" not in out + err and "ValueError" not in out + err, (opcao, out, err)
    rc, doc, _ = _json(capsys, "--uninstall", "--target", str(falso.alvo))
    assert rc == 1 and doc["status"] == "error" and erros_de_schema("install-plan", doc) == []
    rc, out, err = executa(["install", "--target", str(falso.alvo)], capsys, main)
    assert rc == 0 and "aviso" in out and "Traceback" not in out + err, "an install ignores the receipt and says so"


def test_o_help_do_install_diz_o_que_o_global_ignora_e_o_que_o_verify_confere(capsys):
    rc, out, err = executa(["install", "--help"], capsys, main)
    texto = " ".join(out.split())
    assert rc == 0
    assert "--host" in texto and "com --global" in texto and "ignora" in texto and ".claude/skills" in texto, \
        "with --global the host is ignored and only ~/.claude/skills is written"
    assert "já existir" in texto or "já existe" in texto, "an entry file that exists gets no pointer"
    assert "recibo" in texto and "sha256" in texto and "link" in texto
    assert "arquivos" in texto and "confere" in texto and "exit 1" in texto


# --- the output must survive a Windows console ------------------------------------------------------------------------------------


@pytest.mark.parametrize("so", SISTEMAS)
@pytest.mark.parametrize("opcoes", [["--check"], ["--dry-run"], [], ["--verify"], ["--uninstall", "--dry-run"]])
def test_a_saida_cabe_no_cp1252_e_nao_ha_traceback(falso, capsys, simula_so, so, opcoes):
    simula_so(so)
    executa(["install", "--target", str(falso.alvo)], capsys, main)
    rc, out, err = executa(["install", *opcoes, "--target", str(falso.alvo)], capsys, main)
    assert out.strip() and "Traceback" not in out + err
    saida_cp1252(out, err)
