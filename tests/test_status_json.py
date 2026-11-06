"""Contrato da issue #73: `--version --json` e `status --json`, a interface do motor para o looping.

Testes em processo (main()), sem rede e sem rodar ffmpeg, node ou npx. O PATH vira um diretório temporário;
a única coisa que existe nele é um script falso `ffmpeg` que só imprime uma linha de versão.
"""
import hashlib
import json
import shutil
import sys
from pathlib import Path

import pytest

from simplicio_video import __version__, status, tools
from simplicio_video.cli import main

FIXTURE = Path(__file__).parent / "fixtures" / "mini" / "contract.yaml"
TOOL_NAMES = {"openmontage", "opencut", "hypit", "toonflow", "moneyprinter", "matchcut", "instagram", "voicestudio",
              "video-use", "tinyfish", "yt-dlp", "rea_video", "video_to_skill", "ffmpeg", "node"}


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
    for nome in ("openmontage", "opencut", "hypit", "toonflow", "moneyprinter"):
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


# (f) status --json lista todas as trilhas do tools.py, e cada uma é achada onde o setup a deixa

def test_status_json_lista_todas_as_trilhas_do_tools_py(capsys, ambiente):
    rc, out, _ = _run(["status", "--json"], capsys)
    assert rc == 0
    names = [t["name"] for t in json.loads(out)["tools"]]
    assert len(names) == len(set(names))
    assert set(names) == TOOL_NAMES == set(tools.TOOLS) | {"ffmpeg", "node"}


@pytest.mark.parametrize("nome, marcador", [("matchcut", "SKILL.md"), ("instagram", "skills/ig-reel/hookscore.py"),
                                             ("rea_video", "rea_video/cli.py"), ("video-use", "helpers/render.py")])
def test_trilha_git_com_checkout_no_lugar_do_setup_aparece_instalada(nome, marcador, capsys, ambiente, monkeypatch):
    """The layout is written out here, not read from the registry: a wrong marker in tools.py must fail this test."""
    t = tools.get(nome)
    (tools.checkout_dir(t) / marcador).parent.mkdir(parents=True, exist_ok=True)
    (tools.checkout_dir(t) / marcador).write_text("", encoding="utf8")
    monkeypatch.setattr(tools, "_git", lambda *args, cwd=None: "0123456789ab")
    rc, out, _ = _run(["status", "--json"], capsys)
    assert rc == 0
    by = _ferramentas(out)
    assert by[nome]["installed"] is True and by[nome]["version"] == "0123456789ab", nome
    assert by[nome]["pinned"] == tools.pinned_ref(t)


def test_yt_dlp_no_venv_do_cache_aparece_instalado_com_a_versao_do_venv(capsys, ambiente):
    """yt-dlp é uma trilha pip: o executável e a versão vêm do venv do cache, nunca do PATH. A versão é a que o pip gravou
    (o dist-info do venv, sem abrir o processo): o executável diz outra coisa para provar que ele não é aberto."""
    t = tools.get("yt-dlp")
    venv = ambiente.parent / "tools" / "yt-dlp" / "venv"
    exe = venv / tools.PIP_BIN_DIR / "yt-dlp"
    exe.parent.mkdir(parents=True)
    exe.write_text("#!/bin/sh\necho 9999.9.9\n")
    exe.chmod(0o755)
    dist = venv / "lib" / "python3.12" / "site-packages" / "yt_dlp-2026.10.26.dist-info"
    dist.mkdir(parents=True)
    (dist / "METADATA").write_text("Metadata-Version: 2.1\nName: yt-dlp\nVersion: 2026.10.26\n", encoding="utf8")
    rc, out, _ = _run(["status", "--json"], capsys)
    assert rc == 0
    by = _ferramentas(out)
    assert by["yt-dlp"]["installed"] is True
    assert by["yt-dlp"]["version"] == "2026.10.26"
    assert by["yt-dlp"]["pinned"] == tools.pinned_ref(t)


# ------------------------------------------------------------------------------------------------ (#113 2) ambiente da sonda de versão

SONDA = """#!{py}
import json, os, sys
with open({log!r}, "a") as f:
    f.write(json.dumps({{"nome": os.path.basename(sys.argv[0]), "env": dict(os.environ)}}) + "\\n")
print({linha!r})
"""
def test_sonda_de_versao_do_ffmpeg_e_do_node_recebe_ambiente_fechado_com_proxy(tmp_path, monkeypatch, ambiente):
    """#113 (2): `status` geral roda ffmpeg e node com um ambiente fechado (sem as chaves do shell), mas com o proxy e os
    certificados do usuário, como o `busca` já faz com o tinyfish."""
    from simplicio_video import busca  # a lista da sonda sai da do busca (sem a chave do TinyFish) mais LC_CTYPE: uma deriva quebra aqui
    permitido = set(status.ENV_FERRAMENTA)
    assert permitido == (set(busca.ENV_REPASSADO) - {busca.ENV_CHAVE}) | {"LC_CTYPE"}
    log = tmp_path / "sonda.jsonl"
    for nome, linha in (("ffmpeg", "ffmpeg version 6.1.1-test"), ("node", "v22.23.4")):
        exe = ambiente / nome
        exe.write_text(SONDA.format(py=sys.executable, log=str(log), linha=linha), encoding="utf8")
        exe.chmod(0o755)
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.local:3128")
    monkeypatch.setenv("SSL_CERT_FILE", "/etc/ssl/certs/ca.pem")
    monkeypatch.setenv("GEMINI_API_KEY", "gem-segredo-113")
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_segredo113113113113")
    assert status.tool_status("ffmpeg")["installed"] is True and status.tool_status("node")["installed"] is True
    chamadas = [json.loads(linha) for linha in log.read_text(encoding="utf8").splitlines()]
    assert sorted(c["nome"] for c in chamadas) == ["ffmpeg", "node"]
    for c in chamadas:
        assert set(c["env"]) <= permitido, sorted(set(c["env"]) - permitido)
        assert c["env"]["HTTPS_PROXY"] == "http://proxy.local:3128", c["nome"]
        assert c["env"]["SSL_CERT_FILE"] == "/etc/ssl/certs/ca.pem", c["nome"]
        assert "gem-segredo-113" not in c["env"].values() and "ghp_segredo113113113113" not in c["env"].values()
