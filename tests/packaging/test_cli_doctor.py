"""Contrato de `simplicio-video doctor [--json]` (issue #43), com ambientes injetados.

Contrato de saída assumido pelos testes (JSON em stdout com --json):
  {"ok": bool, "checks": [{"name": str, "status": "ok"|"warn"|"fail", "detail": str, "fix": str|null}, ...]}
  rc != 0 se e só se algum check falhou; cada check com status "fail" traz `fix` com a correção exata.

Ambiente injetado (fixture `saude`): shutil.which, os.statvfs e subprocess.run são substituídos. ffmpeg e node
são fakes (versões e libass configuráveis). Qualquer outro comando devolve rc 127 sem executar, e Popen falha:
nenhum ffmpeg ou node de verdade roda. Portas e checagens de plugin (#32) e de workspace avançado (#35) ficam fora.
Credencial: só presença. O valor (sentinela) nunca pode aparecer na saída.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from _comum import executa, exige_registrado
from simplicio_video.cli import main

GB = 1024**3
SENTINELA = "segredo-sentinela-nao-pode-aparecer-na-saida"
FFMPEG_COM_LIBASS = (
    "ffmpeg version 7.0.2 Copyright (c) 2000-2024 the FFmpeg developers\n"
    "configuration: --enable-gpl --enable-version3 --enable-libass --enable-libx264\n"
)
FFMPEG_SEM_LIBASS = (
    "ffmpeg version 7.0.2 Copyright (c) 2000-2024 the FFmpeg developers\n"
    "configuration: --enable-gpl --enable-version3 --enable-libx264\n"
)


@pytest.fixture
def saude(casa, monkeypatch):
    """Ambiente saudável: ffmpeg com libass, node 22, 50 GB livres, GEMINI_API_KEY presente, workspace criado."""
    st = SimpleNamespace(ffmpeg=True, ffmpeg_out=FFMPEG_COM_LIBASS, node="v22.11.0", livre_gb=50.0, chamadas=[])

    def which(nome, *args, **kwargs):
        if nome == "node":
            return "/fake/bin/node"
        if nome == "ffmpeg" and st.ffmpeg:
            return "/fake/bin/ffmpeg"
        return None

    def run(args, *a, **kw):
        argv = list(args) if isinstance(args, (list, tuple)) else [str(args)]
        nome = Path(argv[0]).name
        st.chamadas.append(nome)
        if nome == "ffmpeg":
            if not st.ffmpeg:
                raise FileNotFoundError(2, "No such file or directory", "ffmpeg")
            return subprocess.CompletedProcess(argv, 0, st.ffmpeg_out, "")
        if nome == "node":
            return subprocess.CompletedProcess(argv, 0, st.node + "\n", "")
        return subprocess.CompletedProcess(argv, 127, "", "comando não simulado neste teste")

    def popen(*a, **kw):
        raise AssertionError("doctor não pode usar Popen nos testes: use subprocess.run (fake)")

    def statvfs(caminho):
        bloco = 4096
        livres = int(st.livre_gb * GB // bloco)
        return SimpleNamespace(f_bsize=bloco, f_frsize=bloco, f_blocks=livres * 2, f_bfree=livres, f_bavail=livres)

    monkeypatch.setattr(shutil, "which", which)
    monkeypatch.setattr(subprocess, "run", run)
    monkeypatch.setattr(subprocess, "Popen", popen)
    monkeypatch.setattr(os, "statvfs", statvfs)
    monkeypatch.setenv("GEMINI_API_KEY", SENTINELA)

    casa.workspace.mkdir(parents=True)
    (casa.workspace / "workspace.yaml").write_text(yaml.safe_dump(
        {"schema": "simplicio.workspace/v1", "workspace": "factory/v1", "language": "pt-BR",
         "settings": {"theme": "br", "ui_language": "pt-BR"}}), encoding="utf8")
    (casa.workspace / "policy.yaml").write_text(yaml.safe_dump(
        {"schema": "simplicio.policy/v1", "autonomy": {"default": "L1"},
         "budgets": {"llm_tokens": 0, "llm_usd": 0, "media_credits": 0}}), encoding="utf8")
    return st


def _json(capsys, *extra):
    exige_registrado("doctor", capsys, main)
    rc, out, err = executa(["doctor", "--json", *extra], capsys, main)
    try:
        rel = json.loads(out)
    except ValueError:
        pytest.fail(f"doctor --json não imprimiu JSON (rc {rc}).\nstdout={out!r}\nstderr={err!r}")
    return rc, rel, out, err


def _falhas_com(rel, *termos):
    """Checagens com status fail cujo conteúdo menciona algum dos termos. Tem que haver pelo menos uma."""
    falhas = [c for c in rel["checks"] if c["status"] == "fail"]
    achadas = [c for c in falhas if any(t.lower() in json.dumps(c, ensure_ascii=False).lower() for t in termos)]
    assert achadas, f"nenhuma falha sobre {termos}; checks={json.dumps(rel['checks'], ensure_ascii=False, indent=1)}"
    return achadas


def _sem_falha_sobre(rel, *termos):
    falhas = [c for c in rel["checks"] if c["status"] == "fail"]
    assert not [c for c in falhas if any(t.lower() in c["name"].lower() for t in termos)], \
        f"falha inesperada sobre {termos}: {falhas}"


def test_sem_ffmpeg_sai_com_erro_e_correcao(saude, capsys):
    saude.ffmpeg = False
    rc, rel, _, _ = _json(capsys)
    assert rc != 0
    assert rel["ok"] is False
    for c in _falhas_com(rel, "ffmpeg"):
        assert c["fix"], f"falha sem correção exata: {c}"
        assert "ffmpeg" in c["fix"].lower()


def test_ffmpeg_sem_libass_falha(saude, capsys):
    saude.ffmpeg_out = FFMPEG_SEM_LIBASS
    rc, rel, _, _ = _json(capsys)
    assert rc != 0
    for c in _falhas_com(rel, "libass"):
        assert c["fix"] and "libass" in c["fix"].lower(), f"correção não cita libass: {c}"


def test_node_versao_errada_falha_com_versao_exigida(saude, capsys):
    saude.node = "v20.18.0"
    rc, rel, _, _ = _json(capsys)
    assert rc != 0
    for c in _falhas_com(rel, "node"):
        assert c["fix"] and "22" in c["fix"], f"correção não cita Node 22: {c}"


def test_pouco_disco_falha(saude, capsys):
    saude.livre_gb = 1.0
    rc, rel, _, _ = _json(capsys)
    assert rc != 0
    for c in _falhas_com(rel, "disco", "disk"):
        assert c["fix"], f"falha de disco sem correção: {c}"


def test_credencial_ausente_falha_so_com_o_nome(saude, capsys, monkeypatch):
    # Decisão a confirmar: a credencial exigida é GEMINI_API_KEY (o único provedor de voz nomeado no motor).
    monkeypatch.delenv("GEMINI_API_KEY")
    rc, rel, out, err = _json(capsys)
    assert rc != 0
    for c in _falhas_com(rel, "GEMINI_API_KEY"):
        assert c["fix"] and "GEMINI_API_KEY" in c["fix"], f"correção não diz qual variável definir: {c}"
    assert SENTINELA not in out + err


def test_credencial_presente_nunca_mostra_o_valor(saude, capsys):
    rc, out, err = executa(["doctor"], capsys, main)
    assert SENTINELA not in out + err, "doctor (texto) mostrou o valor da credencial"
    rc, rel, out, err = _json(capsys)
    assert SENTINELA not in out + err, "doctor --json mostrou o valor da credencial"
    achadas = [c for c in rel["checks"] if "GEMINI_API_KEY" in c["name"]]
    assert achadas and all(c["status"] == "ok" for c in achadas), f"credencial presente deveria estar ok: {achadas}"


def test_workspace_ruim_falha_com_setup_como_correcao(saude, casa, capsys):
    (casa.workspace / "workspace.yaml").unlink()
    rc, rel, _, _ = _json(capsys)
    assert rc != 0
    for c in _falhas_com(rel, "workspace"):
        assert c["fix"] and "setup" in c["fix"], f"correção do workspace não manda rodar setup: {c}"


def test_ambiente_saudavel_nao_reprova_ffmpeg_node_nem_disco(saude, capsys):
    rc, rel, _, _ = _json(capsys)
    for termo in ("ffmpeg", "node"):
        assert [c for c in rel["checks"] if termo in c["name"].lower()], f"sem checagem de {termo}"
    _sem_falha_sobre(rel, "ffmpeg", "node")
    assert not [c for c in rel["checks"] if c["status"] == "fail" and "disco" in json.dumps(c, ensure_ascii=False).lower()]


def test_texto_sem_json_sai_com_erro_e_mostra_a_correcao(saude, capsys):
    exige_registrado("doctor", capsys, main)
    saude.ffmpeg = False
    rc, out, err = executa(["doctor"], capsys, main)
    assert rc != 0
    assert "ffmpeg" in (out + err).lower()
