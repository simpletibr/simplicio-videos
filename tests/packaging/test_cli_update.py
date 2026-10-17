"""Contract of `simplicio-video update [--check] [--dry-run] [--force]`: the loop's exit codes, both distributions.

Exit codes (as simplicio-loop): `--check` 0 up to date, 10 update available, 2 error; refusal (dirty tree, no upstream,
not a fast-forward, PEP 668, downgrade without --force) 2; a network failure is `2 if --check else 1`.
Distributions: `pip` (install the latest release from PyPI: `python -m pip install --upgrade "simplicio-video==X"`) and
`source` (a checkout: `git pull --ff-only`, then install, web build and doctor). `--force` reinstalls even when up to date
and allows a downgrade; it NEVER skips the dirty-tree refusal.

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
from _caixa import (SISTEMAS, distribution, doctor_cmd, saida_cp1252, update_cmd, write_fake_tool, write_git_launcher)
from _comum import erros_de_schema, executa, exige_registrado
from simplicio_video import __version__
from simplicio_video.cli import main

# fixtures: assigned (not imported) so pytest finds them and ruff sees no shadowing by the test parameters
caixa = _caixa.caixa
simula_so = _caixa.simula_so

PYPI = "simplicio-video=="


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
    assert c.argvs == [[sys.executable, "-m", "pip", "install", "--upgrade", f"{PYPI}0.5.0"]]
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
    assert "nada foi alterado" in texto


def test_pip_force_em_dia_reinstala_a_mesma_versao(capsys):
    rc, c, _ = pip_update(capsys, installed="0.4.0", tag="v0.4.0", force=True)
    assert rc == 0
    assert c.argvs == [[sys.executable, "-m", "pip", "install", "--upgrade", "--force-reinstall", f"{PYPI}0.4.0"]]


def test_pip_sem_force_nao_usa_force_reinstall(capsys):
    _, c, _ = pip_update(capsys)
    assert "--force-reinstall" not in c.argvs[0]


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
    assert c.argvs == [[sys.executable, "-m", "pip", "install", "--upgrade", f"{PYPI}{etiqueta}"]]
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


# --- multi-system: no `sh`, no POSIX-only step ------------------------------------------------------------------------


@pytest.mark.parametrize("so", SISTEMAS)
def test_o_update_do_checkout_nao_usa_sh_em_nenhum_sistema(so, simula_so, tmp_path):
    """The old web step ran `sh -c ...`, which does not exist on Windows. Nothing here may start `sh`."""
    simula_so(so)
    codigo = Path(update_cmd._real().__file__).read_text(encoding="utf-8")
    assert '"sh"' not in codigo and "'sh'" not in codigo and "WEB_CMD" not in codigo


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


def test_faz_fast_forward_e_imprime_como_voltar(remoto, comandos, capsys):
    checkout = remoto["checkout"]
    rc, out, err = executa(["update"], capsys, main)
    assert rc == 0, out + err
    assert _head(checkout) == remoto["novo"], "update did not move the checkout to the remote"
    assert "0.3.1" in (checkout / "CHANGELOG.md").read_text(encoding="utf8")
    antigo_curto = remoto["antigo"][:7]
    assert antigo_curto in out + err, "update does not print the commit to go back to"
    assert re.search(r"rollback|voltar|git reset", out + err, re.IGNORECASE)
    assert f"reset --keep {remoto['antigo']}" in out


def test_depois_do_pull_roda_install_web_e_doctor_nessa_ordem_sem_sh(remoto, comandos, caixa, capsys):
    web = remoto["checkout"] / "web"
    web.mkdir()
    (web / "package.json").write_text("{}\n")
    npm = write_fake_tool(caixa.bin, "npm", "")
    rc, out, err = executa(["update"], capsys, main)
    assert rc == 0, out + err
    argvs = comandos.argvs
    posicao = {
        "install": next(i for i, a in enumerate(argvs) if a[1:] == ["-m", "simplicio_video", "install"]),
        "ci": next(i for i, a in enumerate(argvs) if a[0] == str(npm) and "ci" in a),
        "build": next(i for i, a in enumerate(argvs) if a[0] == str(npm) and a[-2:] == ["run", "build"]),
        "doctor": next(i for i, a in enumerate(argvs) if a[1:] == ["-m", "simplicio_video", "doctor"]),
    }
    assert posicao["install"] < posicao["ci"] < posicao["build"] < posicao["doctor"]
    assert all(a[0] not in ("sh", "bash") for a in argvs)
    assert all(Path(c).resolve() == remoto["checkout"].resolve() for c in comandos.cwds), "every step runs inside the checkout"


def test_sem_web_o_passo_so_registra_e_segue(remoto, comandos, capsys):
    rc, out, err = executa(["update"], capsys, main)
    assert rc == 0, out + err
    assert "nada a construir" in out
    assert [a for a in comandos.argvs if "npm" in a[0]] == []
    assert len(comandos.argvs) == 2  # install and doctor only


def test_o_codigo_de_saida_do_doctor_e_o_do_update(remoto, comandos, capsys):
    comandos.rc = 1
    rc, out, err = executa(["update"], capsys, main)
    assert rc == 1


def test_dry_run_mostra_o_que_rodaria_e_nao_altera_a_arvore(remoto, comandos, caixa, capsys):
    checkout = remoto["checkout"]
    rc, out, err = executa(["update", "--dry-run"], capsys, main)
    assert rc == 0, out + err
    for trecho in ("git pull --ff-only", "install", "doctor"):
        assert trecho in out, f"--dry-run does not mention {trecho!r}:\n{out}"
    assert _head(checkout) == remoto["antigo"]
    assert comandos.argvs == [], "--dry-run runs nothing"
    assert not (caixa.data / "update-check.json").exists(), "--dry-run records nothing"
    saida_cp1252(out, err)


def test_force_em_dia_reinstala_mesmo_assim(remoto, comandos, capsys):
    _git("pull", "-q", "--ff-only", cwd=remoto["checkout"])
    rc, out, err = executa(["update"], capsys, main)
    assert rc == 0 and comandos.argvs == [], "up to date without --force runs nothing"
    rc, out, err = executa(["update", "--force"], capsys, main)
    assert rc == 0, out + err
    nomes = [a[-1] for a in comandos.argvs]
    assert "install" in nomes and "doctor" in nomes, f"--force must reinstall even when up to date: {comandos.argvs}"


def test_recusa_arvore_suja_com_exit_2_e_a_dica_do_stash(remoto, comandos, capsys):
    checkout = remoto["checkout"]
    (checkout / "CHANGELOG.md").write_text(CHANGELOG_BASE + "- edição local\n", encoding="utf8")
    rc, out, err = executa(["update"], capsys, main)
    assert rc == 2, "a refused update exits 2 (was 1)"
    assert re.search(r"suja|sujo|alterad", out + err, re.IGNORECASE)
    assert "git stash" in out + err
    assert _head(checkout) == remoto["antigo"] and comandos.argvs == []
    assert "edição local" in (checkout / "CHANGELOG.md").read_text(encoding="utf8"), "the local edit was lost"


@pytest.mark.parametrize("opcao", ["--check", "--dry-run", "--force"])
def test_a_arvore_suja_e_recusada_em_todos_os_modos_ate_com_force(remoto, comandos, opcao, capsys):
    checkout = remoto["checkout"]
    (checkout / "CHANGELOG.md").write_text(CHANGELOG_BASE + "- edição local\n", encoding="utf8")
    rc, out, err = executa(["update", opcao], capsys, main)
    assert rc == 2, f"{opcao} accepted a dirty tree"
    assert "git stash" in out + err
    assert _head(checkout) == remoto["antigo"] and comandos.argvs == []


def test_arquivo_novo_nao_rastreado_nao_suja_a_arvore(remoto, comandos, capsys):
    (remoto["checkout"] / "anotacao.txt").write_text("minha nota\n")
    rc, out, err = executa(["update", "--check"], capsys, main)
    assert rc == 10, out + err


def test_sem_upstream_e_recusado_com_exit_2(remoto, comandos, capsys):
    _git("branch", "--unset-upstream", cwd=remoto["checkout"])
    rc, out, err = executa(["update"], capsys, main)
    assert rc == 2 and "upstream" in out + err
    assert _head(remoto["checkout"]) == remoto["antigo"]


def test_fora_de_um_repositorio_git_e_recusado_com_exit_2(caixa, fonte, monkeypatch, capsys):
    vazio = caixa.tmp / "sem-git"
    vazio.mkdir()
    monkeypatch.setenv("SIMPLICIO_VIDEO_HOME", str(vazio))
    rc, out, err = executa(["update", "--dry-run"], capsys, main)
    assert rc == 2 and "não é um repositório git" in out + err


def test_git_ausente_nao_gera_traceback(caixa, fonte, monkeypatch, capsys):
    vazio = caixa.tmp / "sem-git"
    vazio.mkdir()
    monkeypatch.setenv("SIMPLICIO_VIDEO_HOME", str(vazio))
    monkeypatch.setenv("PATH", str(caixa.bin))  # nothing on PATH: no git
    rc, out, err = executa(["update", "--dry-run"], capsys, main)
    assert rc == 2 and "Traceback" not in out + err


def test_historia_divergente_nao_e_fast_forward_e_nada_muda(remoto, comandos, capsys):
    checkout = remoto["checkout"]
    (checkout / "local.txt").write_text("commit local\n")
    _git("add", "local.txt", cwd=checkout)
    _git("commit", "-m", "local", cwd=checkout)
    local = _head(checkout)
    rc, out, err = executa(["update"], capsys, main)
    assert rc == 2 and "fast-forward" in out + err
    assert _head(checkout) == local and comandos.argvs == []


def test_falha_do_fetch_e_2_no_check_e_1_fora_dele(remoto, comandos, caixa, capsys):
    os.rename(caixa.tmp / "origem.git", caixa.tmp / "origem-sumiu.git")
    rc, out, err = executa(["update", "--check"], capsys, main)
    assert rc == 2
    rc, out, err = executa(["update"], capsys, main)
    assert rc == 1
    assert _head(remoto["checkout"]) == remoto["antigo"]


def test_o_check_do_checkout_usa_a_versao_do_pyproject_do_upstream(remoto, comandos, capsys):
    rc, out, err = executa(["update", "--check"], capsys, main)
    assert rc == 10 and "0.5.0" in out


# --- SIMPLICIO_OFFLINE=1 blocks ALL the network, a checkout included; --dry-run never fetches -----------------------------


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


@pytest.mark.parametrize("argv,codigo", [(["update", "--check"], 2), (["update"], 1)])
def test_offline_no_checkout_nao_roda_git_fetch_e_diz_por_que(remoto, comandos, caixa, capsys, monkeypatch, sem_rede, argv, codigo):
    """`git fetch` is network: with SIMPLICIO_OFFLINE=1 the checkout gets the same answer as the pip package (`2 if --check
    else 1`), the message names the variable, and the .git is not touched."""
    monkeypatch.setenv("SIMPLICIO_OFFLINE", "1")
    checkout = remoto["checkout"]
    refs = _refs(checkout)
    rc, out, err = executa(argv, capsys, main)
    assert rc == codigo, out + err
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


@pytest.mark.parametrize("offline", [False, True], ids=["com-rede", "offline"])
def test_dry_run_do_checkout_nao_roda_git_fetch_e_so_mostra_o_plano(remoto, comandos, caixa, capsys, monkeypatch, sem_rede, offline):
    """`git fetch` rewrites FETCH_HEAD, refs/remotes/origin/* and the reflog: it is not a read-only step. The dry-run only prints
    the plan, so it cannot say whether the checkout is up to date (and does not pretend to)."""
    if offline:
        monkeypatch.setenv("SIMPLICIO_OFFLINE", "1")
    checkout = remoto["checkout"]
    refs = _refs(checkout)
    rc, out, err = executa(["update", "--dry-run"], capsys, main)
    assert rc == 0, out + err
    assert [a for a in sem_rede if "fetch" in a and a[0] == "git"] == []
    _nao_mexeu_no_git(checkout, refs)
    for trecho in ("git fetch", "git pull --ff-only", "install", "doctor"):
        assert trecho in out, f"the plan does not mention {trecho!r}:\n{out}"
    assert "não roda" in out and "já está atualizado" not in out
    assert comandos.argvs == [] and not (caixa.data / "update-check.json").exists()
    assert _head(checkout) == remoto["antigo"]


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
