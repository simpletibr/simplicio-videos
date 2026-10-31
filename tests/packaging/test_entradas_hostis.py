"""No unhandled exception comes out of `doctor` (text and --json) with hostile input.

The review of PR #116 reproduced tracebacks from: a PATH folder the user cannot open and a `~/.simplicio` that another user
owns with mode 0700 (common after `sudo` on macOS): `Path.is_file()` raises PermissionError on Python 3.12 and 3.13 where
`shutil.which` swallowed it; and from a corrupt or hostile `update-check.json`. Here every one of those, and more, goes through
the commands, and each must end in an exit code and, with --json, ONE document that fits its packaged schema. Nothing is ever
a traceback.

Real `chmod 000` does nothing for root, who runs this suite in some environments, so the unreadable folders are SIMULATED
(`nega_acesso`: stat, open and friends raise PermissionError inside them). Every file here is under tmp_path.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

import _caixa
from _caixa import LEAKY_ENV, hostos, nega_acesso, roda, write_fake_runtime
from _comum import erros_de_schema

# fixtures: assigned (not imported) so pytest finds them and ruff sees no shadowing by the test parameters
caixa = _caixa.caixa
saude = _caixa.saude

COMANDOS = [
    (["doctor"], None), (["doctor", "--json"], "doctor"),
]


def verifica(argv: list[str], esquema: str | None, capsys):
    """Run one command: an int exit code, no traceback, and with --json ONE document that fits its schema."""
    rc, out, err = roda(argv, capsys)
    assert isinstance(rc, int)
    assert "Traceback" not in out + err, f"{argv}: {err[-400:]}"
    for segredo in LEAKY_ENV.values():
        assert segredo not in out + err, f"{argv} leaked {segredo!r}"
    if esquema:
        try:
            doc = json.loads(out)
        except ValueError:
            pytest.fail(f"{argv}: stdout is not ONE JSON document\nstdout={out[:300]!r}\nstderr={err[:300]!r}")
        assert erros_de_schema(esquema, doc) == [], f"{argv}: {erros_de_schema(esquema, doc)}"
    else:
        assert out.strip() or err.strip(), f"{argv} printed nothing"
    return rc, out, err


# --- a PATH folder the user cannot open -----------------------------------------------------------------------------------


def test_which_pula_a_pasta_sem_permissao_e_acha_na_seguinte(tmp_path, monkeypatch):
    negada = tmp_path / "negada"
    negada.mkdir()
    bom = write_fake_runtime(tmp_path / "bom")
    nega_acesso(monkeypatch, negada)
    assert hostos.which("simplicio", os.pathsep.join([str(negada), str(tmp_path / "bom")])) == bom
    assert hostos.which("simplicio", str(negada)) is None


def test_find_tool_tambem_pula_a_pasta_sem_permissao(tmp_path, monkeypatch):
    negada = tmp_path / "negada"
    negada.mkdir()
    nega_acesso(monkeypatch, negada, tmp_path / "home" / ".local")
    ambiente = {"PATH": str(negada), "HOME": str(tmp_path / "home")}
    assert hostos.find_tool("node", ambiente) is None


@pytest.mark.parametrize("argv,esquema", COMANDOS, ids=lambda x: " ".join(x) if isinstance(x, list) else str(x))
def test_path_com_pasta_ilegivel_nao_derruba_nenhum_comando(caixa, capsys, monkeypatch, argv, esquema):
    negada = caixa.tmp / "negada"
    negada.mkdir()
    caixa.runtime()
    nega_acesso(monkeypatch, negada)
    monkeypatch.setenv("PATH", os.pathsep.join([str(negada), str(caixa.bin)]))  # the unreadable folder comes FIRST
    rc, out, err = verifica(argv, esquema, capsys)


def test_o_doctor_inteiro_com_pasta_ilegivel_no_path(saude, capsys, monkeypatch):
    negada = saude.caixa.tmp / "negada"
    negada.mkdir()
    nega_acesso(monkeypatch, negada)
    monkeypatch.setenv("PATH", os.pathsep.join([str(negada), str(saude.caixa.bin)]))
    rc, out, err = verifica(["doctor", "--json"], "doctor", capsys)
    doc = json.loads(out)
    assert rc == 0 and len(doc["checks"]) == 11
    assert [c["status"] for c in doc["checks"] if c["name"] in ("node", "ffmpeg", "ffmpeg-libass")] == ["ok", "ok", "ok"]


# --- a ~/.simplicio/bin that another user owns (mode 0700, common after `sudo`) ------------------------------------------------


def test_runtime_gerenciado_em_pasta_ilegivel_e_so_nao_encontrado(caixa, monkeypatch):
    write_fake_runtime(caixa.home / ".simplicio" / "bin")
    nega_acesso(monkeypatch, caixa.home / ".simplicio")
    env = {"HOME": str(caixa.home), "PATH": str(caixa.tmp / "vazio")}
    assert _caixa.doctor_cmd.runtime_binary(env) is None


# --- workspace and home folders of another user -------------------------------------------------------------------------


# --- no HOME at all, a workspace that is hostile ---------------------------------------------------------------------------


def _sem_home(monkeypatch) -> None:
    def falha(cls):
        raise RuntimeError("Could not determine home directory.")

    monkeypatch.delenv("HOME", raising=False)
    monkeypatch.delenv("USERPROFILE", raising=False)
    monkeypatch.setattr(Path, "home", classmethod(falha))


@pytest.mark.parametrize("argv,esquema", COMANDOS, ids=lambda x: " ".join(x) if isinstance(x, list) else str(x))
def test_sem_home_nenhum_comando_derruba(caixa, capsys, monkeypatch, argv, esquema):
    _sem_home(monkeypatch)
    verifica(argv, esquema, capsys)


def test_o_doctor_inteiro_sem_home_e_sem_workspace_configurado(saude, capsys, monkeypatch):
    """The workspace folder defaults to ~/.simplicio-video/workspaces/default: with no home it must not raise."""
    monkeypatch.delenv("SIMPLICIO_WORKSPACE")
    _sem_home(monkeypatch)
    rc, out, err = verifica(["doctor", "--json"], "doctor", capsys)
    assert len(json.loads(out)["checks"]) == 11


def test_workspace_com_til_de_usuario_que_nao_existe(saude, capsys, monkeypatch):
    """Path('~nobody-xyz/ws').expanduser() raises RuntimeError: a hostile SIMPLICIO_WORKSPACE must not take the doctor down."""
    monkeypatch.setenv("SIMPLICIO_WORKSPACE", "~um-usuario-que-nao-existe-xyz/ws")
    rc, out, err = verifica(["doctor", "--json"], "doctor", capsys)
    linha = [c for c in json.loads(out)["checks"] if c["name"] == "setup"][0]
    assert linha["status"] == "warn", "a workspace that is not there yet: the setup never ran"


def test_workspace_que_o_usuario_nao_consegue_ler_e_fail_e_nao_traceback(saude, capsys, monkeypatch):
    nega_acesso(monkeypatch, saude.caixa.workspace)
    rc, out, err = verifica(["doctor", "--json"], "doctor", capsys)
    linha = [c for c in json.loads(out)["checks"] if c["name"] == "setup"][0]
    assert rc == 1 and linha["status"] == "fail" and linha["fix"]
    assert "permiss" in linha["summary"].lower(), "say it is a permission problem, not that the setup never ran"


def test_workspace_yaml_aninhado_demais_e_fail_e_nao_traceback(saude, capsys):
    (saude.caixa.workspace / "workspace.yaml").write_text("a: " + "[" * 100_000 + "]" * 100_000, encoding="utf-8")
    rc, out, err = verifica(["doctor", "--json"], "doctor", capsys)
    linha = [c for c in json.loads(out)["checks"] if c["name"] == "setup"][0]
    assert rc == 1 and linha["status"] == "fail"


# --- a Runtime that cannot be started, odd PATH strings --------------------------------------------------------------------


@pytest.mark.parametrize("path", ["", ":", ":::", ".", "relativo/bin", '"', "'", " ", "\t", "/nao/existe", "~", "$HOME", "%PATH%"])
def test_path_estranho_nao_derruba_nenhum_comando(caixa, capsys, monkeypatch, path):
    monkeypatch.setenv("PATH", path)
    for argv, esquema in COMANDOS[:6]:
        verifica(argv, esquema, capsys)


def test_path_com_um_arquivo_e_uma_pasta_chamados_simplicio(caixa, capsys, monkeypatch):
    (caixa.bin / "simplicio").mkdir()
    arquivo = caixa.tmp / "arquivo-no-path"
    arquivo.write_text("x")
    monkeypatch.setenv("PATH", os.pathsep.join([str(arquivo), str(caixa.bin)]))
    rc, out, err = verifica(["doctor", "--json"], "doctor", capsys)
    runtime = next(c for c in json.loads(out)["checks"] if c["name"] == "runtime")
    assert runtime["detail"]["found"] is False


# --- install and the distribution probe on a checkout the user cannot open ---------------------------------------------------


def test_checkout_que_o_usuario_nao_consegue_abrir_nao_e_um_checkout_nem_derruba_ninguem(tmp_path, monkeypatch):
    raiz = tmp_path / "repo"
    raiz.mkdir()
    (raiz / ".git").mkdir()
    (raiz / "plugin.json").write_text('{"name": "videos"}')
    assert _caixa.distribution.checkout_marker(raiz) is True
    nega_acesso(monkeypatch, raiz)
    assert _caixa.distribution.checkout_marker(raiz) is False
    from simplicio_video import paths
    monkeypatch.setenv("SIMPLICIO_VIDEO_HOME", str(raiz))
    assert paths.home() == raiz.resolve(), "an unreadable SIMPLICIO_VIDEO_HOME is still the folder that was asked for"


@pytest.mark.parametrize("argv,codigo", [(["install", "--check"], 10), (["install", "--check", "--json"], 10), (["install", "--dry-run"], 0),
                                         (["install"], 1), (["install", "--json"], 1), (["install", "--uninstall"], 1),
                                         (["install", "--verify"], 1)])
def test_install_com_alvo_que_o_usuario_nao_consegue_abrir_nao_derruba_e_diz_o_que_aconteceu(caixa, capsys, monkeypatch, argv, codigo):
    """A target folder of another user (0700 after a `sudo`): looking at it says "not there yet" (the plan is to install), writing
    into it is a failed install (exit 1) with the reason, and nothing is a traceback."""
    alvo = caixa.tmp / "proj"
    alvo.mkdir()
    nega_acesso(monkeypatch, alvo)
    rc, out, err = verifica([*argv, "--target", str(alvo)], "install-plan" if "--json" in argv else None, capsys)
    assert rc == codigo, (rc, out, err)
    if codigo == 1:
        assert "Permission denied" in out + err or "negado" in out + err or "recibo" in out + err or "não consegui travar" in out + err
