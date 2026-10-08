"""Contrato de `simplicio-video update [--check]` (issue #43) num repositório git temporário.

Remoto simulado: um bare repo local em tmp_path (transporte por arquivo, sem rede). O checkout de teste fica um
commit atrás. `update` tem que: mostrar o diff do CHANGELOG, recusar árvore suja, fazer `git pull --ff-only`,
imprimir como voltar ao commit anterior e reexecutar install, rebuild do web/ e doctor.

Guarda: todo `git` precisa rodar dentro de tmp_path (senão falha o teste). Comandos que não são git são simulados
(rc 0, sem executar). Nada toca o repo real nem a rede.
"""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest

from _casa import casa  # noqa: F401 (fixture: HOME e workspace isolados)
from _comum import executa, exige_registrado
from simplicio_video.cli import main

GIT_ENV = {
    "GIT_AUTHOR_NAME": "teste", "GIT_AUTHOR_EMAIL": "teste@example.invalid",
    "GIT_COMMITTER_NAME": "teste", "GIT_COMMITTER_EMAIL": "teste@example.invalid",
    "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
}
CHANGELOG_BASE = "# Changelog\n\n## 0.3.0\n- base\n"
CHANGELOG_NOVO = CHANGELOG_BASE.replace("## 0.3.0", "## 0.3.1\n- correção de update\n\n## 0.3.0")


def _git(*args, cwd):
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, env={**os.environ, **GIT_ENV})
    assert r.returncode == 0, f"git {' '.join(args)} falhou: {r.stderr}"
    return r.stdout.strip()


@pytest.fixture
def remoto(casa, monkeypatch):
    """origem.git (remoto simulado), semente (quem publica) e checkout (o repo do usuário, um commit atrás)."""
    tmp = casa.tmp
    _git("init", "--bare", "-b", "main", "origem.git", cwd=tmp)
    semente = tmp / "semente"
    _git("init", "-b", "main", "semente", cwd=tmp)
    (semente / "plugin.json").write_text('{"name": "videos"}\n', encoding="utf8")
    (semente / "CHANGELOG.md").write_text(CHANGELOG_BASE, encoding="utf8")
    _git("add", "plugin.json", "CHANGELOG.md", cwd=semente)
    _git("commit", "-m", "chore: base", cwd=semente)
    _git("remote", "add", "origin", str(tmp / "origem.git"), cwd=semente)
    _git("push", "-q", "origin", "main", cwd=semente)

    checkout = tmp / "checkout"
    _git("clone", "-q", str(tmp / "origem.git"), str(checkout), cwd=tmp)
    antigo = _git("rev-parse", "HEAD", cwd=checkout)

    (semente / "CHANGELOG.md").write_text(CHANGELOG_NOVO, encoding="utf8")
    _git("commit", "-am", "fix: update com ff-only", cwd=semente)
    _git("push", "-q", "origin", "main", cwd=semente)
    novo = _git("rev-parse", "HEAD", cwd=semente)

    monkeypatch.setenv("SIMPLICIO_VIDEO_HOME", str(checkout))
    monkeypatch.chdir(checkout)
    return {"checkout": checkout, "antigo": antigo, "novo": novo}


@pytest.fixture
def comandos(casa, remoto, monkeypatch):
    """Registra cada comando. git passa pelo subprocess real (só dentro de tmp_path); o resto é simulado."""
    chamadas: list[tuple[list[str], str]] = []
    real = subprocess.run
    tmp = casa.tmp.resolve()

    def run(args, *a, **kw):
        argv = [str(x) for x in args] if isinstance(args, (list, tuple)) else [str(args)]
        cwd = str(Path(kw.get("cwd") or os.getcwd()).resolve())
        if "-C" in argv:
            cwd = str(Path(argv[argv.index("-C") + 1]).resolve())
        chamadas.append((argv, cwd))
        if argv[0] == "git":
            if not cwd.startswith(str(tmp)):
                raise AssertionError(f"update tocou git fora de tmp_path: {cwd}")
            return real(args, *a, **kw)
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(subprocess, "run", run)
    return chamadas


def _exige_update(capsys):
    exige_registrado("update", capsys, main)


def _head(checkout):
    return _git("rev-parse", "HEAD", cwd=checkout)


def test_update_check_mostra_o_changelog_e_nao_muda_nada(remoto, comandos, capsys):
    _exige_update(capsys)
    checkout = remoto["checkout"]
    rc, out, err = executa(["update", "--check"], capsys, main)
    assert rc == 0, out + err
    assert "0.3.1" in out, f"--check não mostra o diff do CHANGELOG:\n{out}"
    assert _head(checkout) == remoto["antigo"], "--check não pode mover o HEAD"
    assert "0.3.1" not in (checkout / "CHANGELOG.md").read_text(encoding="utf8")


def test_update_faz_fast_forward_e_imprime_como_voltar(remoto, comandos, capsys):
    _exige_update(capsys)
    checkout = remoto["checkout"]
    rc, out, err = executa(["update"], capsys, main)
    assert rc == 0, out + err
    assert _head(checkout) == remoto["novo"], "update não avançou o checkout até o remoto"
    assert "0.3.1" in (checkout / "CHANGELOG.md").read_text(encoding="utf8")
    assert any("--ff-only" in argv for argv, _ in comandos if argv[0] == "git"), "o pull tem que ser --ff-only"
    antigo_curto = remoto["antigo"][:7]
    assert antigo_curto in out + err, "update não imprime o commit para o qual voltar"
    assert re.search(r"rollback|reverter|voltar|git reset|git checkout", out + err, re.IGNORECASE), \
        "update não explica como voltar (rollback)"


def test_update_recusa_arvore_suja(remoto, comandos, capsys):
    _exige_update(capsys)
    checkout = remoto["checkout"]
    (checkout / "CHANGELOG.md").write_text(CHANGELOG_BASE + "- edição local\n", encoding="utf8")
    rc, out, err = executa(["update"], capsys, main)
    assert rc != 0, "update aceitou árvore suja"
    assert re.search(r"suja|sujo|alterad|uncommitted|dirty", out + err, re.IGNORECASE), "a recusa não diz que a árvore está suja"
    assert _head(checkout) == remoto["antigo"], "update recusado não pode mover o HEAD"
    assert "edição local" in (checkout / "CHANGELOG.md").read_text(encoding="utf8"), "a edição local foi perdida"
    assert "--force" in out + err, "a recusa não diz como forçar (--force)"


def test_update_check_tambem_recusa_arvore_suja(remoto, comandos, capsys):
    _exige_update(capsys)
    checkout = remoto["checkout"]
    (checkout / "CHANGELOG.md").write_text(CHANGELOG_BASE + "- edição local\n", encoding="utf8")
    rc, out, err = executa(["update", "--check"], capsys, main)
    assert rc != 0, "update --check aceitou árvore suja"
    assert re.search(r"suja|sujo|alterad|uncommitted|dirty", out + err, re.IGNORECASE), "--check não diz que a árvore está suja"
    assert _head(checkout) == remoto["antigo"]


def test_update_reexecuta_install_build_e_doctor_em_ordem(remoto, comandos, capsys):
    _exige_update(capsys)
    rc, out, err = executa(["update"], capsys, main)
    assert rc == 0, out + err
    nao_git = [(argv, cwd) for argv, cwd in comandos if argv[0] != "git"]

    def posicao(pred, nome):
        idx = [i for i, (argv, cwd) in enumerate(nao_git) if pred(argv, cwd)]
        assert idx, f"update não executou {nome}. Comandos: {[a for a, _ in nao_git]}"
        return idx[0]

    p_install = posicao(lambda argv, cwd: "install" in argv, "install")
    p_web = posicao(lambda argv, cwd: "web" in " ".join(argv) or "web" in cwd.replace(str(remoto["checkout"]), ""),
                    "o rebuild do web/")
    p_doctor = posicao(lambda argv, cwd: "doctor" in argv, "doctor")
    assert p_install < p_web < p_doctor, "a ordem tem que ser install, web, doctor"
