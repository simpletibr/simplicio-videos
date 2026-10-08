"""Contrato da issue #73: `--version --json` e `status --json`, a interface do motor para o looping.

Testes em processo (main()), sem rede e sem rodar ffmpeg, node ou npx. O PATH vira um diretório temporário;
a única coisa que existe nele é um script falso `ffmpeg` que só imprime uma linha de versão.
"""
import hashlib
import json
import shutil
from pathlib import Path

import pytest

from simplicio_video import __version__, tools
from simplicio_video.cli import main

FIXTURE = Path(__file__).parent / "fixtures" / "mini" / "contract.yaml"
TOOL_NAMES = {"openmontage", "opencut", "hypit", "ffmpeg", "node"}


def _run(argv, capsys):
    try:
        rc = main(argv)
    except SystemExit as e:  # argparse encerra com SystemExit (--version, erro de uso)
        rc = e.code
    out, err = capsys.readouterr()
    return rc, out, err


@pytest.fixture
def ambiente(tmp_path, monkeypatch):
    """Nenhuma ferramenta instalada: PATH sem nada, diretório de ferramentas vazio, sem overrides de ambiente."""
    for t in tools.TOOLS.values():
        for var in (f"{t.name.upper()}_DIR", f"SIMPLICIO_{t.name.upper()}_DIR", f"SIMPLICIO_{t.name.upper()}_REF"):
            monkeypatch.delenv(var, raising=False)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    monkeypatch.setenv("PATH", str(bin_dir))
    monkeypatch.setenv("SIMPLICIO_TOOLS_DIR", str(tmp_path / "tools"))
    return bin_dir


def _ferramentas(out):
    return {t["name"]: t for t in json.loads(out)["tools"]}


def _contrato(tmp_path):
    contrato = tmp_path / "video" / "contract.yaml"
    contrato.parent.mkdir()
    shutil.copy(FIXTURE, contrato)
    return contrato


# (a) --version --json

def test_version_texto_continua_igual(capsys, ambiente):
    rc, out, _ = _run(["--version"], capsys)
    assert rc == 0
    assert out.startswith(f"simplicio-video {__version__}")


def test_version_json_traz_version_e_engine(capsys, ambiente):
    rc, out, _ = _run(["--version", "--json"], capsys)
    assert rc == 0
    data = json.loads(out)
    assert data["version"] == __version__
    assert isinstance(data["engine"], str) and "hyperframes" in data["engine"].lower()


# (b) status --json lista ferramentas com os campos do contrato

def test_status_json_lista_ferramentas_e_campos(capsys, ambiente):
    rc, out, _ = _run(["status", "--json"], capsys)
    assert rc == 0
    tlist = json.loads(out)["tools"]
    names = {t["name"] for t in tlist}
    assert TOOL_NAMES <= names
    for t in tlist:
        assert {"name", "installed", "version", "pinned", "pinned_source"} <= set(t)
        assert isinstance(t["installed"], bool)

    by = _ferramentas(out)
    for nome in ("openmontage", "opencut", "hypit"):
        t = tools.TOOLS[nome]
        assert by[nome]["pinned"] == tools.pinned_ref(t)
        assert "tools.py" in by[nome]["pinned_source"]
    for nome in ("ffmpeg", "node"):
        assert by[nome]["pinned"] is None
        assert by[nome]["pinned_source"] == "sem versão fixada"


# (c) ferramenta ausente vira installed false, com exit 0

def test_ferramenta_ausente_vira_installed_false_com_exit_0(capsys, ambiente):
    rc, out, _ = _run(["status", "--json"], capsys)
    assert rc == 0
    by = _ferramentas(out)
    for nome in TOOL_NAMES:
        assert by[nome]["installed"] is False, nome
        assert by[nome]["version"] is None, nome


def test_ferramenta_presente_no_path_traz_versao(capsys, ambiente):
    exe = ambiente / "ffmpeg"
    exe.write_text("#!/bin/sh\necho 'ffmpeg version 6.1.1-teste'\n")
    exe.chmod(0o755)
    rc, out, _ = _run(["status", "--json"], capsys)
    assert rc == 0
    by = _ferramentas(out)
    assert by["ffmpeg"]["installed"] is True
    assert "6.1.1" in str(by["ffmpeg"]["version"])
    assert by["node"]["installed"] is False


# (d) status --json <contrato> inclui o estado do render ao lado do contrato

def test_status_json_com_contrato_inclui_estado_do_render(tmp_path, capsys, ambiente):
    contrato = _contrato(tmp_path)
    sha = hashlib.sha256(contrato.read_bytes()).hexdigest()
    (contrato.parent / "render.manifest.json").write_text(json.dumps({
        "schema": "simplicio.render-manifest/v1", "contract": "video/contract.yaml",
        "contract_sha256": sha, "backend": "local", "finished_at": "2026-10-08T12:00:00Z",
    }))
    rc, out, _ = _run(["status", "--json", str(contrato)], capsys)
    assert rc == 0
    render = json.loads(out)["render"]
    assert render["rendered"] is True
    assert render["contract_sha256"] == sha
    assert render["finished_at"] == "2026-10-08T12:00:00Z"


def test_status_json_com_contrato_sem_render_marca_rendered_false(tmp_path, capsys, ambiente):
    contrato = _contrato(tmp_path)
    rc, out, _ = _run(["status", "--json", str(contrato)], capsys)
    assert rc == 0
    render = json.loads(out)["render"]
    assert render["rendered"] is False
    assert render["contract_sha256"] is None
    assert render["finished_at"] is None


# (e) status em texto continua funcionando

def test_status_texto_continua_funcionando(capsys, ambiente):
    rc, out, _ = _run(["status"], capsys)
    assert rc == 0
    assert "openmontage" in out
    assert "ffmpeg" in out
