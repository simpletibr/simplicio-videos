"""Versão do produto e corte do CHANGELOG: o release 0.7.0 (a versão está nos mesmos lugares da 0.6.0, commit 45c8387).

`pyproject.toml`, `simplicio_video.__version__`, `plugin.json`, a linha do produto em `docs/licenses.md` e a primeira linha do
help em `docs/reference/cli.md` dizem a mesma versão; o CHANGELOG tem a seção `## <versão> — <data>` e uma `## Unreleased`
acima dela; a seção 0.7.0 registra o que o corte levou (a mudança quebrante do `busca log` e o que entrou depois dela).
Só lê arquivos do repo; sem rede. A versão de teste de `update` (fixtures de comparação PEP 440) não passa por aqui.
"""
from __future__ import annotations

import json
import re

import pytest

from _comum import ROOT
from simplicio_video import __version__

tomllib = pytest.importorskip("tomllib")


def _changelog() -> str:
    return (ROOT / "CHANGELOG.md").read_text(encoding="utf8")


def _secao(titulo: str) -> str:
    return _changelog().split(f"## {titulo}", 1)[1].split("\n## ", 1)[0]


def test_a_versao_e_a_mesma_no_pyproject_no_pacote_e_no_plugin():
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf8"))["project"]["version"]
    plugin = json.loads((ROOT / "plugin.json").read_text(encoding="utf8"))["version"]
    assert pyproject == __version__ == plugin


def test_os_docs_gerados_dizem_a_versao_do_pacote():
    licencas = (ROOT / "docs" / "licenses.md").read_text(encoding="utf8")
    assert re.search(rf"^\| simplicio-video \| {re.escape(__version__)} \| AGPL-3.0-or-later \| produto \|", licencas, re.M)
    cli = (ROOT / "docs" / "reference" / "cli.md").read_text(encoding="utf8")
    assert f"simplicio-video {__version__} — " in cli


def test_o_produto_esta_na_0_7_0_ou_depois():
    versao = tuple(int(n) for n in re.match(r"(\d+)\.(\d+)\.(\d+)", __version__).groups())
    assert versao >= (0, 7, 0), f"a versão {__version__} é anterior ao corte 0.7.0"


def test_o_changelog_tem_a_secao_da_versao_com_data_e_o_unreleased_acima():
    texto = _changelog()
    titulos = re.findall(r"^## (.+)$", texto, re.M)
    assert titulos[0] == "Unreleased"
    assert any(re.fullmatch(rf"{re.escape(__version__)} — \d{{4}}-\d{{2}}-\d{{2}}", t) for t in titulos), titulos


def test_o_unreleased_nao_leva_o_que_ja_saiu_na_0_7_0():
    """Depois do corte a seção Unreleased fica vazia (só recebe o que entrar depois); as notas moram na 0.7.0."""
    unreleased = _secao("Unreleased")
    assert "busca-log/v2" not in unreleased and "guarded_child" not in unreleased


def test_a_secao_0_7_0_diz_a_faixa_de_prs_e_o_pypi_publicado():
    secao = _secao("0.7.0 — ")
    assert "0.6.0" in secao and "PyPI" in secao and "tag" in secao
    assert "não foi publicado" not in secao and "sem credencial" not in secao, "o PyPI já foi publicado em 2026-11-06"
    assert "publicado em 2026-11-06 a partir do commit d703a79" in secao
    assert "pip install simplicio-video==0.7.0" in secao
    assert "4ad007d621f89e493a5e3c52ed7b00e03e153ea1669f23e5726d61cdbe6dbbe7" in secao  # wheel
    assert "1f099175f39ea9af1d887ba9e8766c2eeb82ed131cfa137db6c57ef5f5799624" in secao  # sdist
    assert "simplicio-video 0.7.0 (hyperframes@0.8.97)" in secao
    assert "com o dono" not in secao  # a tag v0.7.0 e a GitHub Release já existem (2026-11-06); "independente" não conta
    assert "tag `v0.7.0` (commit d703a79)" in secao
    assert "GitHub Release `v0.7.0`" in secao and "publicada em 2026-11-06" in secao


def test_a_secao_0_7_0_registra_a_mudanca_quebrante_do_busca_log():
    secao = _secao("0.7.0 — ")
    assert "### Mudança quebrante" in secao and "busca-log/v2" in secao


@pytest.mark.parametrize("trecho", [
    "childio.guarded_child",  # the child kill armed before Popen returns (#192, #194 to #197, #201)
    "143", "130", "129",  # exit codes of the MCP server under SIGTERM, SIGINT and SIGHUP (#202)
    "run_child", "check_child",  # what the exit guard does not cover
    "os._exit",  # and the private folders that stay
    "doctor trilhas",  # #182
    "pytest-xdist", "533 s",  # the parallel gate against the serial one (#183)
    "ruff==0.17.3", "pytest==9.2.0", "pytest-socket==0.8.1", "pytest-xdist==3.8.0", "shellcheck-py==0.11.0.1",  # pinned [test] extra (#189)
    "UNVERIFIED",
])
def test_a_secao_0_7_0_cita_o_que_entrou_depois_da_ultima_nota(trecho):
    assert trecho in _secao("0.7.0 — ")
