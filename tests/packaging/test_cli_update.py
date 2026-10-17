"""Contract of `simplicio-video update [--check] [--dry-run] [--force]`: the loop's exit codes, both distributions.

Exit codes (as simplicio-loop): `--check` 0 up to date, 10 update available, 2 error; refusal (a checkout, PEP 668, downgrade
without --force) 2; a network failure is `2 if --check else 1`.
Distributions: `pip` (install the latest release from PyPI: `python -m pip install --upgrade "simplicio-video==X"`, then
`simplicio-video install --global` to reinstall the skills in the agent hosts, as the loop does) and `source` (a checkout or an
editable install): REFUSED, exit 2, printing `git pull` and `bash scripts/dev_install.sh` (Windows: `powershell -NoProfile
-ExecutionPolicy Bypass -File scripts\\dev_install.ps1`: the policy of the client Windows is Restricted). Breaking change (direct owner request): the update used to run `git pull --ff-only` there; the loop
refuses, so does this. `--check` of a checkout still answers 0/10/2 (it asks git how many commits are new) and records the cache.
`--force` reinstalls the pip release even when up to date and allows a downgrade (only our package: `--force-reinstall --no-deps`,
and only when there is nothing newer, so the dependencies of a newer release are never skipped); `--dry-run` shows the plan and changes
nothing.

Part 1 injects the network, git and subprocesses (like the loop's tests). Part 2 runs real git against a bare repo in
tmp_path (transport by file, no network). Nothing touches the real repo, ~ or the network (pytest-socket).
"""
from __future__ import annotations

import io
import json
import os
import re
import socket
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

import pytest

import _caixa
from _caixa import (distribution, doctor_cmd, posix_real, roda_com_prazo, saida_cp1252, solta_fifo, update_cmd,
                    write_fake_tool, write_git_launcher)
from _comum import erros_de_schema, executa, exige_registrado
from simplicio_video import __version__
from simplicio_video.cli import main

# fixtures: assigned (not imported) so pytest finds them and ruff sees no shadowing by the test parameters
caixa = _caixa.caixa
simula_so = _caixa.simula_so

PYPI = "simplicio-video=="
INSTALL_GLOBAL = [sys.executable, "-m", "simplicio_video", "install", "--global"]


@pytest.fixture(autouse=True)
def _com_pip(monkeypatch):
    """The tests must not depend on whether the interpreter that runs them has pip (a `uv tool` venv has none)."""
    monkeypatch.setattr(update_cmd, "_has_pip", lambda: True, raising=False)


class Chamadas:
    """A recorder for the runner and for `record`."""

    def __init__(self, rc: int = 0) -> None:
        self.rc = rc
        self.argvs: list[list[str]] = []
        self.cwds: list = []
        self.registros: list[dict] = []

    def runner(self, argv, cwd=None):
        self.argvs.append([str(x) for x in argv])
        self.cwds.append(cwd)
        return self.rc

    def record(self, info, *a, **kw):
        self.registros.append(dict(info))


def pip_update(capsys, *, installed="0.4.0", tag="v0.5.0", check=False, force=False, dry_run=False, rc=0,
               gerenciado=False, fetch=None):
    c = Chamadas(rc)
    codigo = update_cmd.run_update(check=check, force=force, dry_run=dry_run, installed=installed,
                                   fetch=fetch or (lambda: tag), runner=c.runner, kind="pip", record=c.record,
                                   externally_managed=gerenciado)
    out, err = capsys.readouterr()
    return codigo, c, out + err


# --- pip: exit codes -------------------------------------------------------------------------------------------------


def test_pip_em_dia_sai_0_sem_rodar_nada_e_registra(capsys):
    rc, c, texto = pip_update(capsys, installed="0.4.0", tag="v0.4.0")
    assert rc == 0 and c.argvs == []
    assert "em dia" in texto
    assert c.registros == [{"installed": "0.4.0", "latest": "0.4.0", "update_available": False, "kind": "pip"}]


def test_pip_check_com_atualizacao_sai_10_e_nao_roda_nada(capsys):
    rc, c, texto = pip_update(capsys, check=True)
    assert rc == update_cmd.EXIT_UPDATE_AVAILABLE == 10 and c.argvs == []
    assert "0.4.0 -> 0.5.0" in texto
    assert c.registros == [{"installed": "0.4.0", "latest": "0.5.0", "update_available": True, "kind": "pip"}]


def test_pip_check_em_dia_sai_0(capsys):
    rc, c, _ = pip_update(capsys, check=True, tag="0.4.0")
    assert rc == 0 and c.argvs == []


@pytest.mark.parametrize("erro", [OSError("rede fora"), ValueError("sem versão"), KeyError("tag_name")])
def test_pip_falha_ao_ler_a_release_e_2_no_check_e_1_fora_dele(capsys, erro):
    def quebra():
        raise erro

    rc, c, texto = pip_update(capsys, check=True, fetch=quebra)
    assert rc == 2 and c.argvs == [] and "não consegui ler" in texto
    rc, c, texto = pip_update(capsys, check=False, fetch=quebra)
    assert rc == 1 and c.argvs == [] and c.registros == []


def test_pip_falha_de_rede_com_dry_run_e_1(capsys):
    def quebra():
        raise OSError("rede fora")

    rc, c, _ = pip_update(capsys, dry_run=True, fetch=quebra)
    assert rc == 1 and c.argvs == []


# --- pip: the upgrade ------------------------------------------------------------------------------------------------


def test_pip_instala_a_ultima_release_do_pypi_com_o_python_atual(capsys):
    rc, c, texto = pip_update(capsys, tag="v0.5.0")
    assert rc == 0
    assert c.argvs == [[sys.executable, "-m", "pip", "install", "--upgrade", f"{PYPI}0.5.0"], INSTALL_GLOBAL]
    assert "0.4.0 -> 0.5.0" in texto
    assert c.registros[-1] == {"installed": "0.5.0", "latest": "0.5.0", "update_available": False, "kind": "pip"}
    assert "git+" not in " ".join(c.argvs[0]), "the pip distribution comes from PyPI, not from git"


def test_pip_que_falha_devolve_o_codigo_do_pip_e_nao_registra_sucesso(capsys):
    rc, c, texto = pip_update(capsys, rc=3)
    assert rc == 3
    assert all(r["installed"] == "0.4.0" for r in c.registros), "a failed install must not be recorded as done"
    assert "pip" in texto


def test_pip_dry_run_mostra_o_comando_nao_roda_e_nao_registra(capsys):
    rc, c, texto = pip_update(capsys, dry_run=True)
    assert rc == 0 and c.argvs == [] and c.registros == []
    assert f"{PYPI}0.5.0" in texto and "pip install --upgrade" in texto
    assert "simplicio_video install --global" in texto, "the plan shows the skills refresh too"
    assert "nada foi alterado" in texto


def test_pip_force_em_dia_reinstala_a_mesma_versao(capsys):
    rc, c, _ = pip_update(capsys, installed="0.4.0", tag="v0.4.0", force=True)
    assert rc == 0
    assert c.argvs == [[sys.executable, "-m", "pip", "install", "--upgrade", "--force-reinstall", "--no-deps", f"{PYPI}0.4.0"],
                       INSTALL_GLOBAL], "only our package is reinstalled, not every dependency (the loop's own repair does the same)"


def test_pip_force_com_versao_nova_nao_pula_as_dependencias(capsys):
    """`--no-deps` on a NEWER release would skip a dependency that release adds: the force only reinstalls when nothing is newer."""
    rc, c, _ = pip_update(capsys, installed="0.4.0", tag="v0.5.0", force=True)
    assert rc == 0 and c.argvs[0] == [sys.executable, "-m", "pip", "install", "--upgrade", f"{PYPI}0.5.0"]


def test_pip_sem_force_nao_usa_force_reinstall_nem_no_deps(capsys):
    _, c, _ = pip_update(capsys)
    assert "--force-reinstall" not in c.argvs[0] and "--no-deps" not in c.argvs[0]


def test_update_num_python_sem_pip_diz_o_que_fazer_e_sai_2_sem_rodar_nada(capsys, monkeypatch):
    """A `uv tool install` venv has no pip: `python -m pip` would fail with "No module named pip" (review of #117)."""
    monkeypatch.setattr(update_cmd, "_has_pip", lambda: False)
    rc, c, texto = pip_update(capsys)
    assert rc == 2 and c.argvs == []
    assert "pip" in texto and "uv tool upgrade simplicio-video" in texto and "pipx upgrade simplicio-video" in texto
    assert "Traceback" not in texto and "No module named" not in texto


def test_update_sem_pip_nao_barra_o_check_nem_o_dry_run(capsys, monkeypatch):
    monkeypatch.setattr(update_cmd, "_has_pip", lambda: False)
    assert pip_update(capsys, check=True)[0] == 10
    rc, c, texto = pip_update(capsys, dry_run=True)
    assert rc == 0 and "executaria" in texto


def test_pip_instalado_mais_novo_que_a_ultima_release_e_em_dia_e_sai_0(capsys):
    """PyPI is published before the GitHub Release (the flow of #115), so the installed version can be NEWER than the latest
    release. The loop answers 0, "up to date" (self_update.py:487-491); refusing with exit 2 would break that flow."""
    rc, c, texto = pip_update(capsys, installed="0.6.0", tag="v0.5.0")
    assert rc == 0 and c.argvs == []
    assert re.search(r"mais nov[oa]", texto) and "0.5.0" in texto and "recusando" not in texto
    assert c.registros[-1]["update_available"] is False and c.registros[-1]["latest"] == "0.5.0"


def test_pip_downgrade_com_force_e_permitido(capsys):
    rc, c, _ = pip_update(capsys, installed="0.6.0", tag="v0.5.0", force=True)
    assert rc == 0 and c.argvs[0][-1] == f"{PYPI}0.5.0"


def test_pip_downgrade_no_check_nao_e_atualizacao(capsys):
    rc, c, _ = pip_update(capsys, installed="0.6.0", tag="v0.5.0", check=True)
    assert rc == 0 and c.registros[0]["update_available"] is False


class FalhaNoInstall(Chamadas):
    """The pip upgrade works; the `install --global` that follows it fails with 5."""

    def runner(self, argv, cwd=None):
        super().runner(argv, cwd)
        return 5 if "--global" in argv else 0


def test_pip_depois_do_upgrade_reinstala_as_skills_nos_hosts_e_so_entao_registra(capsys):
    c = Chamadas()
    visto_na_hora = []

    def runner(argv, cwd=None):
        visto_na_hora.append((list(argv), len(c.registros)))
        return c.runner(argv, cwd)

    codigo = update_cmd.run_update(installed="0.4.0", fetch=lambda: "v0.5.0", runner=runner, kind="pip", record=c.record,
                                   externally_managed=False)
    capsys.readouterr()
    assert codigo == 0 and [a for a, _ in visto_na_hora][-1] == INSTALL_GLOBAL
    assert visto_na_hora[-1][1] == 1, "the success is recorded only AFTER the skills were reinstalled"
    assert c.registros[-1]["installed"] == "0.5.0" and c.registros[-1]["update_available"] is False


def test_pip_se_o_install_global_falha_o_codigo_e_o_dele_e_nao_registra_sucesso(capsys):
    c = FalhaNoInstall()
    codigo = update_cmd.run_update(installed="0.4.0", fetch=lambda: "v0.5.0", runner=c.runner, kind="pip", record=c.record,
                                   externally_managed=False)
    texto = "".join(capsys.readouterr())
    assert codigo == 5 and c.argvs[-1] == INSTALL_GLOBAL
    assert all(r["installed"] == "0.4.0" for r in c.registros), "a half update must not be recorded as done"
    assert "install --global" in texto and "simplicio-video install --global" in texto, "it says how to finish by hand"


def test_pip_em_dia_check_e_pep_668_nao_reinstalam_as_skills(capsys):
    for kw in ({"installed": "0.5.0", "tag": "v0.5.0"}, {"check": True}, {"gerenciado": True}):
        rc, c, _ = pip_update(capsys, **kw)
        assert INSTALL_GLOBAL not in c.argvs, kw


def test_pip_dry_run_mostra_o_install_global_e_nao_o_roda(capsys):
    rc, c, texto = pip_update(capsys, dry_run=True)
    assert rc == 0 and c.argvs == [] and "executaria: " + " ".join(INSTALL_GLOBAL) in texto


def test_main_update_de_pacote_roda_pip_e_depois_o_install_global(caixa, capsys, monkeypatch):
    c = Chamadas()
    monkeypatch.setattr(distribution, "kind", lambda **kw: "pip")
    monkeypatch.setattr(update_cmd, "fetch_latest_tag", lambda: "v99.0.0")
    monkeypatch.setattr(update_cmd, "_run", c.runner)
    monkeypatch.setattr(update_cmd, "is_pep668_environment", lambda **kw: (False, None))
    rc, out, err = executa(["update"], capsys, main)
    assert rc == 0, out + err
    assert [a[1:4] for a in c.argvs] == [["-m", "pip", "install"], ["-m", "simplicio_video", "install"]]
    assert json.loads((caixa.data / "update-check.json").read_text())["installed"] == "99.0.0"


# --- pip: PEP 668 ----------------------------------------------------------------------------------------------------


def test_pep_668_recusa_com_quatro_saidas_e_nao_roda_o_pip(capsys):
    rc, c, texto = pip_update(capsys, gerenciado=True)
    assert rc == 2 and c.argvs == []
    assert "PEP 668" in texto and "PIP_BREAK_SYSTEM_PACKAGES=1" in texto
    for saida in ("venv", "uv", "pipx", "simplicio-video"):
        assert saida in texto, saida


def test_pep_668_nao_barra_o_check(capsys):
    rc, c, _ = pip_update(capsys, gerenciado=True, check=True)
    assert rc == 10 and c.argvs == []


def test_pep_668_barra_o_force_em_dia_tambem(capsys):
    rc, c, _ = pip_update(capsys, gerenciado=True, installed="0.5.0", tag="v0.5.0", force=True)
    assert rc == 2 and c.argvs == []


def test_pep_668_detecta_o_arquivo_externally_managed(tmp_path):
    base = tmp_path / "prefix"
    lib = base / "lib" / f"python{sys.version_info.major}.{sys.version_info.minor}"
    lib.mkdir(parents=True)
    (lib / "EXTERNALLY-MANAGED").write_text("[externally-managed]\nError=use um venv\n")
    gerenciado, detalhes = update_cmd.is_pep668_environment(prefix=str(base), base_prefix=str(base), environ={})
    assert gerenciado is True and "use um venv" in detalhes
    assert update_cmd.is_pep668_environment(prefix=str(base), base_prefix=str(base),
                                            environ={"PIP_BREAK_SYSTEM_PACKAGES": "1"}) == (False, None)
    assert update_cmd.is_pep668_environment(prefix=str(base / "venv"), base_prefix=str(base), environ={}) == (False, None)
    assert update_cmd.is_pep668_environment(prefix=str(tmp_path / "x"), base_prefix=str(tmp_path / "x"),
                                            environ={}) == (False, None)


# --- the latest release (gh, then the GitHub API) ---------------------------------------------------------------------


@pytest.fixture
def com_rede(monkeypatch):
    """Offline is the default of the whole suite; the tests of the fetch itself turn it off (nothing real is called)."""
    monkeypatch.delenv("SIMPLICIO_OFFLINE", raising=False)


def test_a_ultima_release_vem_do_gh_quando_ele_existe(caixa, com_rede):
    write_fake_tool(caixa.bin, "gh", "v9.9.9\n")
    assert update_cmd.fetch_latest_tag() == "v9.9.9"
    argv = (caixa.bin / "gh.argv").read_text().strip()
    assert argv == "release view -R simpletibr/simplicio-videos --json tagName -q .tagName"
    assert update_cmd.REPO == "simpletibr/simplicio-videos"


def test_sem_gh_ou_com_gh_falhando_usa_a_api_do_github(caixa, com_rede, monkeypatch):
    pedidos = []

    class Resposta:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self, *a):
            return b'{"tag_name": "v0.7.0"}'

    def abre(url):
        pedidos.append(url)
        return Resposta()

    monkeypatch.setattr(update_cmd, "_open", abre)
    assert update_cmd.fetch_latest_tag() == "v0.7.0"
    assert pedidos == ["https://api.github.com/repos/simpletibr/simplicio-videos/releases/latest"]
    write_fake_tool(caixa.bin, "gh", "", rc=1)
    assert update_cmd.fetch_latest_tag() == "v0.7.0"


def test_offline_bloqueia_a_rede_do_update_sem_chamar_gh_nem_a_api(caixa, monkeypatch):
    """SIMPLICIO_OFFLINE=1 (the default of the suite and of the smoke script) means no network tool is started."""
    assert os.environ.get("SIMPLICIO_OFFLINE") == "1"
    write_fake_tool(caixa.bin, "gh", "v9.9.9\n")
    monkeypatch.setattr(update_cmd, "_open", lambda url: pytest.fail("the API was called while offline"))
    monkeypatch.setattr(distribution, "kind", lambda **kw: "pip")
    with pytest.raises(OSError, match="SIMPLICIO_OFFLINE"):
        update_cmd.fetch_latest_tag()
    assert not (caixa.bin / "gh.argv").exists()


def test_main_pip_offline_diz_que_esta_offline_e_nao_grava_nada(caixa, capsys, monkeypatch):
    monkeypatch.setattr(distribution, "kind", lambda **kw: "pip")
    monkeypatch.setattr(update_cmd, "_git", lambda *a, **k: pytest.fail("git is not part of the pip update"))
    rc, out, err = executa(["update", "--dry-run"], capsys, main)
    assert rc == 1 and "SIMPLICIO_OFFLINE" in out + err
    rc, out, err = executa(["update", "--check"], capsys, main)
    assert rc == 2
    assert not caixa.data.exists(), "a failed check records nothing"


def test_o_token_do_github_so_vai_para_a_api(monkeypatch):
    monkeypatch.setenv("GH_TOKEN", "fake-gh-token")
    api = update_cmd._request("https://api.github.com/repos/simpletibr/simplicio-videos/releases/latest")
    assert api.get_header("Authorization") == "Bearer fake-gh-token"
    baixa = update_cmd._request("https://github.com/simpletibr/simplicio-videos/releases/download/v1/x")
    assert baixa.get_header("Authorization") is None
    outro = update_cmd._request("https://objects.githubusercontent.com/x")
    assert outro.get_header("Authorization") is None


def test_o_github_token_tambem_e_aceito_so_para_a_api(monkeypatch):
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.setenv("GITHUB_TOKEN", "fake-gh-token-2")
    assert update_cmd._request("https://api.github.com/x").get_header("Authorization") == "Bearer fake-gh-token-2"


def test_o_redirect_para_outro_host_tira_o_token_e_https_para_http_e_recusado():
    handler = update_cmd._SameHostRedirect()
    req = urllib.request.Request("https://api.github.com/x", headers={"Authorization": "Bearer fake-gh-token"})
    cabecalhos = {}
    movido = handler.redirect_request(req, io.BytesIO(b""), 302, "Found", cabecalhos, "https://objects.example.org/y")
    assert movido is not None and movido.get_header("Authorization") is None
    mesmo = handler.redirect_request(req, io.BytesIO(b""), 302, "Found", cabecalhos, "https://api.github.com/z")
    assert mesmo.get_header("Authorization") == "Bearer fake-gh-token"
    with pytest.raises(urllib.error.HTTPError, match="plain http"):
        handler.redirect_request(req, io.BytesIO(b""), 302, "Found", cabecalhos, "http://objects.example.org/y")


def test_url_que_nao_e_https_e_recusada(com_rede):
    with pytest.raises(ValueError, match="https"):
        update_cmd._open("http://api.github.com/x")


@pytest.mark.parametrize("texto,etiqueta", [
    ("v0.4.0", "0.4.0"), ("0.10.2", "0.10.2"), ("1.2", "1.2.0"), ("1.2.3.4", "1.2.3.4"), ("1.2.3.0", "1.2.3"),
    ("v1.2.3.post1", "1.2.3.post1"), (" v0.5.0\n", "0.5.0"), ("10.20.30", "10.20.30"),
])
def test_parse_version_aceita_so_a_release_final(texto, etiqueta):
    """`\\d+(\\.\\d+){1,3}` with an optional `v`, plus the post-release suffix of PEP 440; the label is rebuilt from integers."""
    assert update_cmd.format_version(update_cmd.parse_version(texto)) == etiqueta


@pytest.mark.parametrize("texto", [
    "latest", "", "v", "1", "1.", ".1.2", "1..2", "v0.5.0 --index-url=http://evil", "0.5.0 @ git+https://evil", "v0.5.0-rc1",
    "0.5.0rc1", "0.5.0a1", "0.5.0b2", "0.5.0.dev1", "1!2.0.0", "0.5.0+local", "\uff11.\uff12.\uff13", "release 1.2.3", "V0.5.0",
    "0.5.0\n0.6.0", "1.2.3.4.5", "v0.5.0.post", "0.5.0.post1.dev2", "0.5.0;rm -rf /", "0.5.0 && echo x", "0.5.0\x00", "-1.2.3",
    "v 0.5.0", "0.5.0.POST1", "0.5.0-1",
])
def test_parse_version_recusa_o_resto(texto):
    with pytest.raises(ValueError):
        update_cmd.parse_version(texto)


def test_a_comparacao_de_versoes_segue_o_pep_440_para_o_que_aceita():
    parse = update_cmd.parse_version
    assert parse("1.2") == parse("1.2.0") == parse("v1.2.0.0")
    assert parse("0.10.0") > parse("0.9.9") and parse("1.2.3.post1") > parse("1.2.3") and parse("1.2.3.1") > parse("1.2.3")
    assert parse("1.2.3.post2") > parse("1.2.3.post1") and parse("2.0") > parse("1.99.99")


@pytest.mark.parametrize("tag", ["v0.5.0 --index-url=http://evil", "0.5.0 @ git+https://evil", "v0.5.0-rc1", "1!2.0.0",
                                 "\uff11.\uff12.\uff13", "0.5.0;rm -rf /", "$(touch pwned)", "v0.5.0\n--pre"])
def test_um_tag_estranho_nao_chega_ao_pip(capsys, tag):
    """The argv is rebuilt from integers; a tag that is not a plain version stops the update before pip is started."""
    rc, c, texto = pip_update(capsys, tag=tag)
    assert rc == 1 and c.argvs == [] and "não consegui ler" in texto
    rc, c, texto = pip_update(capsys, tag=tag, check=True)
    assert rc == 2 and c.argvs == [] and c.registros == []


@pytest.mark.parametrize("tag,etiqueta", [("v0.5.0", "0.5.0"), ("1.2.3.post4", "1.2.3.post4"), ("v2.0", "2.0.0"), ("3.4.5.6", "3.4.5.6")])
def test_o_argv_do_pip_tem_so_numeros_e_um_igual_igual_fixo(capsys, tag, etiqueta):
    rc, c, _ = pip_update(capsys, tag=tag, installed="0.1.0")
    assert c.argvs == [[sys.executable, "-m", "pip", "install", "--upgrade", f"{PYPI}{etiqueta}"], INSTALL_GLOBAL]
    assert re.fullmatch(r"simplicio-video==\d+(\.\d+){2,3}(\.post\d+)?", c.argvs[0][-1]) and isinstance(c.argvs[0], list)


def test_o_pip_roda_sem_shell(monkeypatch):
    chamadas = []
    monkeypatch.setattr(subprocess, "call", lambda *a, **kw: chamadas.append((a, kw)) or 0)
    update_cmd._run([sys.executable, "-m", "pip", "install", "--upgrade", "simplicio-video==0.5.0"])
    (args, kw), = chamadas
    assert isinstance(args[0], list) and not kw.get("shell")
    from _comum import ROOT
    for nome in ("update", "install", "login", "doctor", "setup"):
        fonte = (ROOT / "src" / "simplicio_video" / "commands" / f"{nome}.py").read_text(encoding="utf-8")
        assert "shell=True" not in fonte and "os.system" not in fonte, nome


def test_versao_instalada_de_desenvolvimento_nao_derruba_o_update(capsys):
    """The installed version is read from our own `__version__`, which can be a dev version: it must not raise."""
    rc, c, texto = pip_update(capsys, installed="0.5.0.dev1", tag="v0.4.0")
    assert rc == 0 and c.argvs == [] and "Traceback" not in texto
    rc, c, texto = pip_update(capsys, installed="0.5.0.dev1", tag="v0.6.0", check=True)
    assert rc == 10


# --- the state: update-check.json, read by `doctor` without network --------------------------------------------------


def test_o_estado_vai_para_simplicio_video_data_de_forma_atomica(caixa):
    update_cmd.write_check({"installed": "0.4.0", "latest": "0.5.0", "update_available": True, "kind": "pip"})
    arq = caixa.data / "update-check.json"
    dados = json.loads(arq.read_text())
    assert dados["latest"] == "0.5.0" and isinstance(dados["checked_at"], int)
    assert update_cmd.read_check() == dados
    assert update_cmd.default_state_dir() == caixa.data
    assert [p.name for p in caixa.data.iterdir()] == ["update-check.json"], "no temp file may be left behind"


def test_estado_ausente_e_none_e_o_ilegivel_ou_invalido_e_um_erro_claro(caixa):
    assert update_cmd.read_check() is None
    caixa.data.mkdir()
    arq = caixa.data / "update-check.json"
    for bruto in ("not json", "[1]", '"x"', "", "{}", '{"latest": "1.2.3"}',
                  '{"latest": "1.2.3", "checked_at": "yesterday"}', '{"latest": "1.2.3", "checked_at": 1e20}',
                  '{"latest": "1.2.3", "checked_at": [1]}', '{"latest": "1.2.3", "checked_at": true}',
                  '{"latest": "1.2.3", "checked_at": -5}', '{"latest": "1.2.3", "checked_at": 1.5}',
                  '{"latest": 99, "checked_at": 1700000000}', '{"latest": "x\\u001b[31m9.9.9", "checked_at": 1700000000}',
                  '{"latest": "1.2.3", "checked_at": 253402300800}', "[" * 100000):
        arq.write_text(bruto)
        with pytest.raises(update_cmd.CheckInvalid):
            update_cmd.read_check()


def test_read_check_devolve_so_as_chaves_conhecidas_e_com_o_tipo_certo(caixa):
    caixa.data.mkdir()
    base = {"installed": "0.4.0", "latest": "0.5.0", "update_available": True, "kind": "source", "commits_behind": 3,
            "checked_at": 1700000000}
    arq = caixa.data / "update-check.json"
    arq.write_text(json.dumps({**base, "access_token": "fake-secret-tok", "zzz": 1}))
    assert update_cmd.read_check() == base
    arq.write_text(json.dumps({**base, "kind": "pip"}))  # commits_behind only exists for kind=source
    assert "commits_behind" not in update_cmd.read_check()
    arq.write_text(json.dumps({**base, "installed": ["x"], "update_available": "sim", "kind": "binary", "commits_behind": -1}))
    assert update_cmd.read_check() == {"latest": "0.5.0", "checked_at": 1700000000}, "a known key of the wrong type is dropped"


def test_o_estado_gravado_fecha_com_o_schema(caixa):
    update_cmd.write_check({"installed": "0.4.0", "latest": "0.5.0", "update_available": True, "kind": "source", "commits_behind": 2})
    assert erros_de_schema("update-check", json.loads((caixa.data / "update-check.json").read_text())) == []
    assert update_cmd.read_check()["commits_behind"] == 2


INFO = {"installed": "0.4.0", "latest": "0.5.0", "update_available": True, "kind": "pip"}


def test_a_gravacao_do_estado_e_atomica_temporario_na_mesma_pasta_e_replace(caixa, monkeypatch):
    chamadas = []
    real = os.replace
    monkeypatch.setattr(os, "replace", lambda origem, destino: chamadas.append((origem, destino)) or real(origem, destino))
    update_cmd.write_check(INFO)
    (origem, destino), = chamadas
    assert Path(destino) == caixa.data / "update-check.json"
    assert Path(origem).parent == caixa.data and Path(origem) != Path(destino), "the temp file must be beside the target"


def test_replace_que_falha_nao_estraga_o_estado_anterior_nem_deixa_temporario(caixa, monkeypatch):
    update_cmd.write_check(INFO)
    antes = (caixa.data / "update-check.json").read_bytes()

    def falha(origem, destino):
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", falha)
    update_cmd.write_check({**INFO, "latest": "9.9.9"})  # best effort: no exception
    assert (caixa.data / "update-check.json").read_bytes() == antes
    assert [p.name for p in caixa.data.iterdir()] == ["update-check.json"], "a failed write must not leave a temp file behind"


def test_escrita_interrompida_no_meio_nao_deixa_o_estado_pela_metade(caixa, monkeypatch):
    update_cmd.write_check(INFO)
    antes = (caixa.data / "update-check.json").read_bytes()

    def pela_metade(obj, handle, **kw):
        handle.write('{"installed": "0.4.0", "lat')
        raise OSError("disk full")

    monkeypatch.setattr(json, "dump", pela_metade)
    update_cmd.write_check({**INFO, "latest": "9.9.9"})
    assert (caixa.data / "update-check.json").read_bytes() == antes
    assert [p.name for p in caixa.data.iterdir()] == ["update-check.json"]


def test_o_estado_que_nao_da_para_gravar_nao_derruba_o_update(caixa):
    caixa.data.parent.mkdir(exist_ok=True)
    caixa.data.write_text("a file where the folder should be")
    update_cmd.write_check({"installed": "0.4.0", "latest": "0.5.0", "update_available": True, "kind": "pip"})


def test_sem_simplicio_video_data_o_estado_fica_em_home_simplicio_video(caixa, monkeypatch):
    monkeypatch.delenv("SIMPLICIO_VIDEO_DATA")
    assert update_cmd.default_state_dir() == caixa.home / ".simplicio-video"


# --- source distribution (a checkout) with real git ------------------------------------------------------------------

GIT_ENV = {
    "GIT_AUTHOR_NAME": "teste", "GIT_AUTHOR_EMAIL": "teste@example.invalid",
    "GIT_COMMITTER_NAME": "teste", "GIT_COMMITTER_EMAIL": "teste@example.invalid",
    "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
}
CHANGELOG_BASE = "# Changelog\n\n## 0.3.0\n- base\n"
CHANGELOG_NOVO = CHANGELOG_BASE.replace("## 0.3.0", "## 0.3.1\n- correção de update\n\n## 0.3.0")
PYPROJECT = '[project]\nname = "simplicio-video"\nversion = "{v}"\n'


def _git(*args, cwd):
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, env={**os.environ, **GIT_ENV})
    assert r.returncode == 0, f"git {' '.join(args)} falhou: {r.stderr}"
    return r.stdout.strip()


@pytest.fixture
def fonte(monkeypatch):
    """The distribution is a checkout, whatever the machine that runs the suite is."""
    monkeypatch.setattr(distribution, "kind", lambda **kw: "source")


@pytest.fixture
def remoto(caixa, fonte, com_rede, monkeypatch):
    """origem.git (simulated remote), semente (the publisher) and checkout (the user's repo, one commit behind)."""
    tmp = caixa.tmp
    write_git_launcher(caixa.tmp / "gitbin")
    monkeypatch.setenv("PATH", os.pathsep.join([str(caixa.bin), str(caixa.tmp / "gitbin")]))
    _git("init", "--bare", "-b", "main", "origem.git", cwd=tmp)
    semente = tmp / "semente"
    _git("init", "-b", "main", "semente", cwd=tmp)
    (semente / "plugin.json").write_text('{"name": "videos"}\n', encoding="utf8")
    (semente / "CHANGELOG.md").write_text(CHANGELOG_BASE, encoding="utf8")
    (semente / "pyproject.toml").write_text(PYPROJECT.format(v="0.4.0"), encoding="utf8")
    _git("add", "plugin.json", "CHANGELOG.md", "pyproject.toml", cwd=semente)
    _git("commit", "-m", "chore: base", cwd=semente)
    _git("remote", "add", "origin", str(tmp / "origem.git"), cwd=semente)
    _git("push", "-q", "origin", "main", cwd=semente)

    checkout = tmp / "checkout"
    _git("clone", "-q", str(tmp / "origem.git"), str(checkout), cwd=tmp)
    antigo = _git("rev-parse", "HEAD", cwd=checkout)

    (semente / "CHANGELOG.md").write_text(CHANGELOG_NOVO, encoding="utf8")
    (semente / "pyproject.toml").write_text(PYPROJECT.format(v="0.5.0"), encoding="utf8")
    _git("commit", "-am", "fix: update com ff-only", cwd=semente)
    _git("push", "-q", "origin", "main", cwd=semente)
    novo = _git("rev-parse", "HEAD", cwd=semente)

    monkeypatch.setenv("SIMPLICIO_VIDEO_HOME", str(checkout))
    monkeypatch.chdir(checkout)
    return {"checkout": checkout, "semente": semente, "antigo": antigo, "novo": novo}


@pytest.fixture
def comandos(caixa, remoto, monkeypatch):
    """Records what the update would run (install, web, doctor) without running it; git only inside tmp_path."""
    c = Chamadas()
    tmp = caixa.tmp.resolve()
    real_git = update_cmd._git

    def git_guardado(checkout, *args, **kw):
        if not str(Path(checkout).resolve()).startswith(str(tmp)):
            raise AssertionError(f"update touched git outside tmp_path: {checkout}")
        return real_git(checkout, *args, **kw)

    monkeypatch.setattr(update_cmd, "_git", git_guardado)
    monkeypatch.setattr(update_cmd, "_run", c.runner)
    return c


def _head(checkout):
    return _git("rev-parse", "HEAD", cwd=checkout)


def test_check_mostra_o_changelog_sai_10_e_nao_muda_nada(remoto, comandos, caixa, capsys):
    exige_registrado("update", capsys, main)
    checkout = remoto["checkout"]
    rc, out, err = executa(["update", "--check"], capsys, main)
    assert rc == 10, out + err
    assert "0.3.1" in out, f"--check does not show the CHANGELOG diff:\n{out}"
    assert _head(checkout) == remoto["antigo"], "--check must not move HEAD"
    assert "0.3.1" not in (checkout / "CHANGELOG.md").read_text(encoding="utf8")
    assert comandos.argvs == [], "--check must run nothing"
    registro = json.loads((caixa.data / "update-check.json").read_text())
    assert registro["kind"] == "source" and registro["update_available"] is True and registro["commits_behind"] == 1
    assert registro["installed"] == __version__ and registro["latest"] == "0.5.0"


def test_check_em_dia_sai_0(remoto, comandos, caixa, capsys):
    _git("pull", "-q", "--ff-only", cwd=remoto["checkout"])
    rc, out, err = executa(["update", "--check"], capsys, main)
    assert rc == 0, out + err
    registro = json.loads((caixa.data / "update-check.json").read_text())
    assert registro["update_available"] is False and registro["commits_behind"] == 0


def test_arquivo_novo_nao_rastreado_nao_suja_a_arvore(remoto, comandos, capsys):
    (remoto["checkout"] / "anotacao.txt").write_text("minha nota\n")
    rc, out, err = executa(["update", "--check"], capsys, main)
    assert rc == 10, out + err


def test_o_check_do_checkout_usa_a_versao_do_pyproject_do_upstream(remoto, comandos, capsys):
    rc, out, err = executa(["update", "--check"], capsys, main)
    assert rc == 10 and "0.5.0" in out


# --- the update of a checkout is REFUSED, as in the loop: `git pull` and the dev install ARE the update -----------------------

PULL = "git pull"
DEV_SH = "bash scripts/dev_install.sh"
DEV_PS1 = "powershell -NoProfile -ExecutionPolicy Bypass -File scripts\\dev_install.ps1"


@pytest.mark.parametrize("opcoes", [[], ["--force"], ["--dry-run"], ["--check", "--dry-run"], ["--force", "--dry-run"]])
def test_update_no_checkout_recusa_com_exit_2_e_diz_git_pull_e_o_dev_install(remoto, comandos, caixa, capsys, opcoes):
    checkout = remoto["checkout"]
    rc, out, err = executa(["update", *opcoes], capsys, main)
    assert rc == 2, out + err
    assert PULL in out + err and DEV_SH in out + err and "--ff-only" not in out + err
    assert _head(checkout) == remoto["antigo"] and comandos.argvs == [], "a refusal changes and runs nothing"
    assert not (caixa.data / "update-check.json").exists(), "a refusal records nothing"
    saida_cp1252(out, err)


@pytest.mark.parametrize("so,esperado,ausente", [("linux", DEV_SH, DEV_PS1), ("darwin", DEV_SH, DEV_PS1), ("win32", DEV_PS1, DEV_SH)])
def test_a_recusa_diz_o_dev_install_do_sistema(remoto, comandos, capsys, simula_so, so, esperado, ausente):
    simula_so(so)
    rc, out, err = executa(["update"], capsys, main)
    assert rc == 2 and PULL in out + err and esperado in out + err and ausente not in out + err


def test_a_recusa_nao_roda_git_nem_rede_nem_programa_nenhum(remoto, comandos, caixa, capsys, monkeypatch, sem_rede):
    for rede in ("1", "0"):
        monkeypatch.setenv("SIMPLICIO_OFFLINE", rede)
        rc, out, err = executa(["update"], capsys, main)
        assert rc == 2
    assert sem_rede == [], f"the refusal started a process: {sem_rede}"


def test_o_update_nao_tem_mais_git_pull_nem_reset_no_codigo():
    codigo = Path(update_cmd._real().__file__).read_text(encoding="utf-8")
    assert '"pull"' not in codigo and "--ff-only" not in codigo and '"reset"' not in codigo
    assert "_web_steps" not in codigo and "npm" not in codigo, "the web/ build moved to scripts/dev_install.sh"


def test_o_update_do_checkout_nao_usa_sh_em_nenhum_sistema():
    codigo = Path(update_cmd._real().__file__).read_text(encoding="utf-8")
    assert '"sh"' not in codigo and "'sh'" not in codigo and "WEB_CMD" not in codigo


def test_o_check_nao_liga_para_arvore_suja_porque_nada_e_puxado(remoto, comandos, capsys):
    checkout = remoto["checkout"]
    (checkout / "CHANGELOG.md").write_text(CHANGELOG_BASE + "- edição local\n", encoding="utf-8")
    rc, out, err = executa(["update", "--check"], capsys, main)
    assert rc == 10, out + err
    assert "git stash" not in out + err and "suja" not in out + err
    assert "edição local" in (checkout / "CHANGELOG.md").read_text(encoding="utf-8")
    assert _head(checkout) == remoto["antigo"]


def test_o_check_com_historia_divergente_conta_os_commits_novos_e_nao_mexe(remoto, comandos, capsys):
    checkout = remoto["checkout"]
    (checkout / "local.txt").write_text("commit local\n", encoding="utf-8")
    _git("add", "local.txt", cwd=checkout)
    _git("commit", "-m", "local", cwd=checkout)
    local = _head(checkout)
    rc, out, err = executa(["update", "--check"], capsys, main)
    assert rc == 10 and _head(checkout) == local and comandos.argvs == []


@pytest.mark.parametrize("onde", ["sem-upstream", "sem-git", "git-ausente", "fetch-falha"])
def test_o_check_do_checkout_que_nao_da_para_responder_sai_2_sem_traceback(remoto, comandos, caixa, capsys, monkeypatch, onde):
    if onde == "sem-upstream":
        _git("branch", "--unset-upstream", cwd=remoto["checkout"])
        trecho = "upstream"
    elif onde == "fetch-falha":
        os.rename(caixa.tmp / "origem.git", caixa.tmp / "origem-sumiu.git")
        trecho = "fetch"
    else:
        vazio = caixa.tmp / "sem-git"
        vazio.mkdir()
        monkeypatch.setenv("SIMPLICIO_VIDEO_HOME", str(vazio))
        trecho = "repositório git"
        if onde == "git-ausente":
            monkeypatch.setenv("PATH", str(caixa.bin))  # nothing on PATH: no git
    rc, out, err = executa(["update", "--check"], capsys, main)
    assert rc == 2 and "Traceback" not in out + err
    if onde != "git-ausente":
        assert trecho in out + err
    assert not (caixa.data / "update-check.json").exists(), "a check that could not answer records nothing"


@posix_real
def test_o_check_do_checkout_so_le_nao_olha_a_arvore_nem_puxa_e_todo_git_leva_no_optional_locks(remoto, comandos, caixa, capsys,
                                                                                              monkeypatch):
    pasta = _git_falso(caixa, monkeypatch, 'exec "$REAL" "$@"', "gitlog")
    rc, out, err = executa(["update", "--check"], capsys, main)
    assert rc == 10, out + err
    chamadas = (pasta / "chamadas.log").read_text().splitlines()
    verbos = {_subcomando_do_git(c.split()) for c in chamadas}
    assert verbos <= {"rev-parse", "fetch", "log", "show", "diff"}, verbos
    assert all("--no-optional-locks" in c for c in chamadas), [c for c in chamadas if "--no-optional-locks" not in c]


@posix_real
def test_o_check_nao_regrava_o_index_do_git(remoto, comandos, capsys):
    checkout = remoto["checkout"]
    arq = checkout / "CHANGELOG.md"
    novo = os.stat(arq).st_mtime + 3600
    os.utime(arq, (novo, novo))  # same bytes, other mtime: a plain `git status` refreshes the index entry and writes it
    index = checkout / ".git" / "index"
    antes = (index.read_bytes(), os.stat(index).st_mtime_ns)
    rc, out, err = executa(["update", "--check"], capsys, main)
    assert rc == 10, out + err
    assert (index.read_bytes(), os.stat(index).st_mtime_ns) == antes, "a read-only step rewrote .git/index"


@pytest.mark.parametrize("offline", [False, True], ids=["com-rede", "offline"])
def test_o_dry_run_do_checkout_nao_roda_git_e_so_recusa(remoto, comandos, caixa, capsys, monkeypatch, sem_rede, offline):
    if offline:
        monkeypatch.setenv("SIMPLICIO_OFFLINE", "1")
    checkout = remoto["checkout"]
    refs = _refs(checkout)
    antes = list(sem_rede)  # the test's own `git for-each-ref` above is not the update's
    rc, out, err = executa(["update", "--dry-run"], capsys, main)
    assert rc == 2 and PULL in out + err
    assert sem_rede == antes, f"the refusal started a process: {sem_rede[len(antes):]}"
    _nao_mexeu_no_git(checkout, refs)


# --- SIMPLICIO_OFFLINE=1 blocks ALL the network, a checkout included (`--check` runs git fetch) -----------------------------


REDE_DO_GIT = {"fetch", "pull", "push", "clone", "ls-remote", "remote", "submodule"}
PROGRAMAS_DE_REDE = {"gh", "curl", "wget", "ssh", "pip", "pip3"}


def _subcomando_do_git(args: list[str]) -> str | None:
    """`git -C <dir> --no-pager <subcommand> ...` -> the subcommand."""
    i = 0
    while i < len(args):
        if args[i] == "-C":
            i += 2
        elif args[i].startswith("-"):
            i += 1
        else:
            return args[i]
    return None


@pytest.fixture
def sem_rede(monkeypatch):
    """A spy: any program or call that could touch the network FAILS the test. Returns the list of every argv started."""
    visto: list[list[str]] = []
    real_init = subprocess.Popen.__init__

    def cuidado(self, args, *a, **kw):
        argv = [str(x) for x in (args if isinstance(args, (list, tuple)) else [args])]
        visto.append(argv)
        programa = Path(argv[0]).name.lower() if argv else ""
        programa = programa.rsplit(".", 1)[0] if programa.endswith((".exe", ".cmd", ".bat")) else programa
        if programa == "git" and _subcomando_do_git(argv[1:]) in REDE_DO_GIT:
            raise AssertionError(f"SIMPLICIO_OFFLINE: `git {_subcomando_do_git(argv[1:])}` would use the network: {argv}")
        if programa in PROGRAMAS_DE_REDE or (argv[:1] == [sys.executable] and "pip" in argv[1:4]):
            raise AssertionError(f"SIMPLICIO_OFFLINE: {argv} would use the network")
        return real_init(self, args, *a, **kw)

    def sem_socket(*a, **kw):
        raise AssertionError("SIMPLICIO_OFFLINE: the network was used")

    monkeypatch.setattr(subprocess.Popen, "__init__", cuidado)
    monkeypatch.setattr(socket.socket, "connect", sem_socket)
    monkeypatch.setattr(socket, "create_connection", sem_socket)
    monkeypatch.setattr(urllib.request.OpenerDirector, "open", sem_socket)
    return visto


def _refs(checkout) -> str:
    return _git("for-each-ref", "--format=%(refname) %(objectname)", cwd=checkout)


def _nao_mexeu_no_git(checkout, refs_antes) -> None:
    assert _refs(checkout) == refs_antes, "the remote-tracking refs moved: a fetch ran"
    assert not (checkout / ".git" / "FETCH_HEAD").exists(), "FETCH_HEAD exists: a fetch ran"


def test_offline_o_check_no_checkout_nao_roda_git_fetch_e_diz_por_que(remoto, comandos, caixa, capsys, monkeypatch, sem_rede):
    """`git fetch` is network: with SIMPLICIO_OFFLINE=1 the checkout gets the same answer as the pip package (`--check` 2), the
    message names the variable, and the .git is not touched."""
    monkeypatch.setenv("SIMPLICIO_OFFLINE", "1")
    checkout = remoto["checkout"]
    refs = _refs(checkout)
    rc, out, err = executa(["update", "--check"], capsys, main)
    assert rc == 2, out + err
    assert "SIMPLICIO_OFFLINE" in out + err and "git fetch" in out + err
    assert [a for a in sem_rede if "fetch" in a] == []
    _nao_mexeu_no_git(checkout, refs)
    assert _head(checkout) == remoto["antigo"] and comandos.argvs == []
    assert not (caixa.data / "update-check.json").exists(), "a failed check records nothing"


def test_offline_o_doctor_online_no_checkout_e_aviso_e_nao_roda_git_fetch(remoto, comandos, caixa, monkeypatch, sem_rede):
    monkeypatch.setenv("SIMPLICIO_OFFLINE", "1")
    refs = _refs(remoto["checkout"])
    linha = doctor_cmd.collect(online=True, only="update")["checks"][0]
    assert linha["name"] == "update" and linha["status"] == "warn" and "SIMPLICIO_OFFLINE" in linha["summary"]
    assert [a for a in sem_rede if "fetch" in a] == []
    _nao_mexeu_no_git(remoto["checkout"], refs)
    assert not (caixa.data / "update-check.json").exists()


@pytest.mark.parametrize("argv", [["update", "--check"], ["update"], ["update", "--dry-run"]])
def test_offline_no_pacote_pip_nao_chama_gh_pip_nem_a_api(caixa, capsys, monkeypatch, sem_rede, argv):
    monkeypatch.setattr(distribution, "kind", lambda **kw: "pip")
    write_fake_tool(caixa.bin, "gh", "v9.9.9\n")  # a gh on PATH that must not be started
    rc, out, err = executa(argv, capsys, main)
    assert rc in (1, 2) and "SIMPLICIO_OFFLINE" in out + err
    assert not [a for a in sem_rede if Path(a[0]).name in ("gh", "pip")] and not (caixa.bin / "gh.argv").exists()


# --- the version the checkout reports and the text git prints ------------------------------------------------------------


def test_versao_estranha_no_upstream_nao_vai_para_o_estado(remoto, comandos, caixa, capsys):
    semente = remoto["semente"]
    (semente / "pyproject.toml").write_text(PYPROJECT.format(v="0.6.0rc1"), encoding="utf8")
    _git("commit", "-am", "chore: versão de teste", cwd=semente)
    _git("push", "-q", "origin", "main", cwd=semente)
    rc, out, err = executa(["update", "--check"], capsys, main)
    assert rc == 10, out + err
    registro = json.loads((caixa.data / "update-check.json").read_text())
    assert erros_de_schema("update-check", registro) == []
    update_cmd.parse_version(registro["latest"])  # a real version, never the raw text of someone else's pyproject.toml


def test_diff_do_changelog_com_byte_que_nao_e_utf8_nao_derruba_o_update(remoto, comandos, capsys):
    """On Windows git's output is decoded with the console codec (cp1252 cannot read 0x8D, the second byte of an `Í`); here a
    Latin-1 byte, which UTF-8 cannot read either. The text is read as UTF-8 with `errors=replace`."""
    semente = remoto["semente"]
    (semente / "CHANGELOG.md").write_bytes(CHANGELOG_NOVO.encode("utf-8") + b"- caf\xe9 com um byte latin-1\n")
    _git("commit", "-am", "fix: byte latin-1", cwd=semente)
    _git("push", "-q", "origin", "main", cwd=semente)
    rc, out, err = executa(["update", "--check"], capsys, main)
    assert rc == 10 and "caf" in out and "�" in out, out + err


def test_git_devolve_texto_utf8_com_substituicao(remoto):
    (remoto["checkout"] / "CHANGELOG.md").write_bytes(b"# caf\xe9 \xc3\x8d\n")
    feito = update_cmd._git(remoto["checkout"], "show", "--no-patch", "HEAD")  # any text; the real check is the diff above
    assert feito.returncode == 0
    feito = update_cmd._git(remoto["checkout"], "diff", "HEAD", "--", "CHANGELOG.md")
    assert "caf�" in feito.stdout and "Í" in feito.stdout


# --- a FIFO as update-check.json must not hang anything (the second review) ---------------------------------------------------


@posix_real
def test_update_check_que_e_fifo_nao_trava_e_e_cache_invalido(caixa):
    """`open()` on a FIFO with no writer blocks forever: the state file is opened O_NONBLOCK and checked with fstat on that
    descriptor, like the login file, and anything that is not a regular file is an invalid cache (a warning in the doctor)."""
    caixa.data.mkdir()
    fifo = caixa.data / "update-check.json"
    os.mkfifo(fifo)
    with pytest.raises(update_cmd.CheckInvalid) as err:
        roda_com_prazo(update_cmd.read_check, destravar=lambda: solta_fifo(fifo))
    assert "arquivo comum" in str(err.value)
    linha = roda_com_prazo(lambda: doctor_cmd.collect(only="update")["checks"][0], destravar=lambda: solta_fifo(fifo))
    assert linha["status"] == "warn" and linha["fix"] == "simplicio-video update --check" and linha["detail"] == {}


def test_update_check_que_e_pasta_e_cache_invalido(caixa):
    caixa.data.mkdir()
    (caixa.data / "update-check.json").mkdir()
    with pytest.raises(update_cmd.CheckInvalid):
        update_cmd.read_check()


# --- git: the real reason is shown, and a git older than 2.15 still works -----------------------------------------------------


def _git_falso(caixa, monkeypatch, corpo: str, nome: str = "gitfalso") -> Path:
    """A `git` first on PATH: `corpo` is a /bin/sh script; `REAL` is the real git. Calls are logged in <dir>/chamadas.log."""
    real = _caixa.shutil.which("git", path=_caixa.REAL_PATH)
    pasta = caixa.tmp / nome
    pasta.mkdir()
    arq = pasta / "git"
    arq.write_text(f"#!/bin/sh\nREAL='{real}'\necho \"$@\" >> '{pasta}/chamadas.log'\n{corpo}\n", encoding="utf-8")
    arq.chmod(0o755)
    monkeypatch.setenv("PATH", os.pathsep.join([str(pasta), os.environ["PATH"]]))
    return pasta


GIT_ANTIGO = '''for a in "$@"; do
  case "$a" in --no-optional-locks) echo "Unknown option: --no-optional-locks" >&2; echo "usage: git [--version] [--help]" >&2; exit 129;; esac
done
exec "$REAL" "$@"'''


@posix_real
def test_git_antigo_que_nao_conhece_no_optional_locks_ainda_funciona_com_uma_tentativa_sem_a_opcao(remoto, comandos, caixa, capsys,
                                                                                                    monkeypatch):
    """git before 2.15 answers `Unknown option: --no-optional-locks` (exit 129): each call is repeated ONCE without it."""
    pasta = _git_falso(caixa, monkeypatch, GIT_ANTIGO)
    rc, out, err = executa(["update", "--check"], capsys, main)
    assert rc == 10 and "0.3.1" in out and "não é um repositório git" not in out + err, out + err
    chamadas = (pasta / "chamadas.log").read_text().splitlines()
    com = [c for c in chamadas if "--no-optional-locks" in c]
    sem = [c for c in chamadas if "--no-optional-locks" not in c]
    assert com and len(sem) == len(com), f"each rejected call is retried exactly once without the option: {len(com)} x {len(sem)}"
    assert all(c.replace(" --no-optional-locks", "") == s for c, s in zip(com, sem)), "the retry is the same call"


@posix_real
def test_git_novo_nao_e_chamado_duas_vezes(remoto, comandos, caixa, capsys, monkeypatch):
    pasta = _git_falso(caixa, monkeypatch, 'exec "$REAL" "$@"', "gitnormal")
    rc, out, err = executa(["update", "--check"], capsys, main)
    assert rc == 10
    chamadas = (pasta / "chamadas.log").read_text().splitlines()
    assert chamadas and all("--no-optional-locks" in c for c in chamadas), "a git that knows the option is called once"


GIT_DESCONFIADO = '''echo "fatal: detected dubious ownership in repository at '/outro/dono'" >&2
echo "To add an exception for this directory, call:" >&2
echo "" >&2
echo "	git config --global --add safe.directory /outro/dono" >&2
exit 128'''


@posix_real
def test_git_que_recusa_o_repositorio_mostra_o_motivo_do_git(remoto, comandos, caixa, capsys, monkeypatch):
    """`dubious ownership` (a checkout of another user) used to read as plain "não é um repositório git": git's stderr was dropped."""
    _git_falso(caixa, monkeypatch, GIT_DESCONFIADO)
    rc, out, err = executa(["update", "--check"], capsys, main)
    assert rc == 2 and "não é um repositório git" in out + err
    assert "dubious ownership" in out + err and "safe.directory" in out + err
    linha = doctor_cmd.collect(online=True, only="update")["checks"][0]
    assert linha["status"] == "warn" and "dubious ownership" in linha["summary"]


GIT_COM_LIXO = '''printf 'fatal: \\033[2J\\033[31mboom %s\\n' "$(head -c 3000 /dev/zero | tr '\\0' 'x')" >&2
exit 128'''


@posix_real
def test_o_motivo_do_git_sai_cortado_e_sem_escape_de_terminal(remoto, comandos, caixa, capsys, monkeypatch):
    _git_falso(caixa, monkeypatch, GIT_COM_LIXO)
    rc, out, err = executa(["update", "--check"], capsys, main)
    texto = out + err
    assert rc == 2 and "boom" in texto and "\x1b" not in texto
    assert len(texto) < 1200, f"git's message is cut: {len(texto)} characters"


# --- --dry-run with --check: ONE rule, in both distributions ---------------------------------------------------------------------


def test_dry_run_junto_com_check_so_mostra_o_plano_e_sai_0_no_pip(capsys):
    """The dry-run prints the plan and exits 0, `--check` or not: the same as in a checkout (`--check` alone answers 10)."""
    rc, c, texto = pip_update(capsys, check=True, dry_run=True)
    assert rc == 0 and c.argvs == [] and c.registros == []
    assert "executaria" in texto and f"{PYPI}0.5.0" in texto
    rc, c, texto = pip_update(capsys, check=True)
    assert rc == update_cmd.EXIT_UPDATE_AVAILABLE, "--check alone still answers 10"


# --- a development or pre-release installed version is OLDER than the release (PEP 440) --------------------------------------


@pytest.mark.parametrize("instalada", ["0.5.0.dev1", "0.5.0rc1", "0.5.0-rc.1", "0.5.0a2", "0.5.0b1", "0.5.0.dev3+local", "0.4.9.post2"])
def test_versao_instalada_anterior_a_release_final_tem_atualizacao(capsys, instalada):
    rc, c, texto = pip_update(capsys, installed=instalada, tag="v0.5.0", check=True)
    assert rc == update_cmd.EXIT_UPDATE_AVAILABLE and "em dia" not in texto, f"{instalada} < 0.5.0 (PEP 440)"
    rc, c, texto = pip_update(capsys, installed=instalada, tag="v0.5.0")
    assert c.argvs[0] == [sys.executable, "-m", "pip", "install", "--upgrade", f"{PYPI}0.5.0"], "the target is the FINAL release"


@pytest.mark.parametrize("instalada", ["0.5.0", "0.5.0+local", "0.5.0.post1", "0.5.1.dev1", "0.6.0rc1", "0.5.0.post1.dev2"])
def test_versao_instalada_igual_ou_mais_nova_que_a_release_final_esta_em_dia(capsys, instalada):
    rc, c, texto = pip_update(capsys, installed=instalada, tag="v0.5.0", check=True)
    assert rc == 0 and c.argvs == []


def test_a_ordem_das_versoes_instaladas_e_a_do_pep_440():
    chave = update_cmd.release_tuple
    ordem = ["0.5.0.dev1", "0.5.0a1", "0.5.0a2", "0.5.0b1", "0.5.0rc1", "0.5.0rc2", "0.5.0", "0.5.0.post1"]
    chaves = [chave(v) for v in ordem]
    assert chaves == sorted(chaves) and len(set(chaves)) == len(chaves), ordem
    assert chave("0.5.0-rc.1") == chave("0.5.0rc1") and chave("0.5.0+local") >= chave("0.5.0")
    assert update_cmd.parse_version("v0.5.0") > chave("0.5.0rc1")
    assert update_cmd.parse_version("0.5.0") == chave("0.5.0") and update_cmd.parse_version("1.2") == chave("1.2.0")
    with pytest.raises(ValueError):
        update_cmd.parse_version("0.5.0rc1")  # a pre-release is never a TARGET


# --- every git of the update asks for no optional locks, and the index stays as it was ------------------------------------------

