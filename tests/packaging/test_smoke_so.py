"""`scripts/smoke_so.py`: the script that someone runs on a REAL Windows or macOS machine (Python 3.10+, standard library).

It runs the operations commands against a sealed HOME/USERPROFILE/PATH in a temporary folder (never the real ~, never the real
Runtime: there is no `simplicio` on its PATH), validates each JSON against the packaged schema, prints a Markdown table (OS,
Python, command, expected x obtained exit, ok/failed) and exits 1 when anything fails.

These tests run the script here, on Linux, and prove its guarantees. They do NOT prove anything about Windows or macOS:
those stay UNVERIFIED until the script is run there.
"""
from __future__ import annotations

import importlib.util
import os
import platform
import shutil
import sys
from pathlib import Path

import pytest

from _comum import ROOT

SCRIPT = ROOT / "scripts" / "smoke_so.py"


@pytest.fixture(scope="module")
def smoke():
    assert SCRIPT.is_file(), "scripts/smoke_so.py does not exist"
    spec = importlib.util.spec_from_file_location("smoke_so_sob_teste", SCRIPT)
    modulo = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = modulo  # dataclasses look the module up by name while the script is executed
    try:
        spec.loader.exec_module(modulo)
        yield modulo
    finally:
        sys.modules.pop(spec.name, None)


def test_o_script_usa_so_a_biblioteca_padrao_no_topo():
    """The script must start on a bare Python: third-party imports (jsonschema) are lazy, inside the validation."""
    topo = []
    for linha in SCRIPT.read_text(encoding="utf-8").splitlines():
        if linha.startswith(("import ", "from ")):
            topo.append(linha.split()[1].split(".")[0])
    assert topo, "no imports found?"
    stdlib = set(sys.stdlib_module_names) if hasattr(sys, "stdlib_module_names") else None
    if stdlib is not None:
        fora = [m for m in topo if m not in stdlib and m != "__future__"]
        assert fora == [], f"top-level imports outside the standard library: {fora}"


def test_o_help_tem_exemplos_e_diz_que_roda_em_pasta_temporaria():
    import subprocess
    r = subprocess.run([sys.executable, str(SCRIPT), "--help"], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    assert "exemplos" in r.stdout.lower() and "scripts/smoke_so.py" in r.stdout
    assert "temporária" in r.stdout or "temporaria" in r.stdout


def test_o_ambiente_do_filho_e_isolado(smoke, tmp_path):
    real = {"HOME": "/home/real", "USERPROFILE": r"C:\Users\real", "PATH": "/usr/bin" + os.pathsep + "/bin",
            "GH_TOKEN": "fake-gh", "GITHUB_TOKEN": "fake-gh2", "GEMINI_API_KEY": "fake-gem", "SIMPLICIO_AUTH_FILE": "/real/login.json",
            "SIMPLICIO_LOGIN_TOKEN": "fake-lt", "BROWSER": "firefox", "SYSTEMROOT": r"C:\Windows", "OUTRA": "x"}
    env = smoke.build_env(tmp_path, real)
    assert Path(env["HOME"]) == tmp_path / "home"
    assert env["USERPROFILE"] != env["HOME"] and Path(env["USERPROFILE"]).parent == tmp_path, \
        "HOME and USERPROFILE must be DIFFERENT folders: with the same one, a program that reads the wrong variable passes"
    for nome in ("GH_TOKEN", "GITHUB_TOKEN", "GEMINI_API_KEY", "SIMPLICIO_AUTH_FILE", "SIMPLICIO_LOGIN_TOKEN", "BROWSER", "OUTRA"):
        assert nome not in env, f"{nome} leaked into the child environment"
    assert str(tmp_path) in env["PATH"] and "/usr/bin" not in env["PATH"] and "/bin" not in env["PATH"].split(os.pathsep)
    assert env["SIMPLICIO_OFFLINE"] == "1"
    assert env["SYSTEMROOT"] == r"C:\Windows", "Windows needs SYSTEMROOT to start Python"
    for nome in ("SIMPLICIO_VIDEO_DATA", "SIMPLICIO_WORKSPACE", "SIMPLICIO_VIDEO_HOME"):
        assert str(tmp_path) in env[nome], f"{nome} must be under the temporary folder"


def test_nao_existe_simplicio_no_path_do_filho(smoke, tmp_path):
    env = smoke.build_env(tmp_path, dict(os.environ))
    for nome in ("simplicio", "simplicio.exe", "simplicio.cmd"):
        assert shutil.which(nome, path=env["PATH"]) is None
    assert not any(Path(p, "simplicio").exists() for p in env["PATH"].split(os.pathsep) if p)


def test_nenhum_passo_fala_com_login(smoke):
    for passo in smoke.PASSOS:
        assert "login" not in passo.argv and "logout" not in passo.argv, passo.argv
    nomes = [" ".join(p.argv) for p in smoke.PASSOS]
    for esperado in ("--version", "doctor --json", "install --check --target {alvo}", "install --dry-run --json --target {alvo}",
                     "install --verify --json --target {alvo}", "install --target {alvo}", "install --verify --target {alvo}",
                     "install --check --json --target {alvo}",
                     "install --uninstall --target {alvo}", "update --dry-run"):
        assert esperado in nomes, f"missing step {esperado!r}: {nomes}"
    assert len(nomes) == len(set(nomes)), "two steps with the same name hide each other"


def test_o_install_do_smoke_so_toca_num_alvo_temporario_e_nunca_no_home():
    """`install` of the skills runs into a folder of the temporary base (`{alvo}`): never `--global` (that is the real ~), and the
    child never gets a terminal on stdin (the end of `install` would start the interactive `setup`)."""
    for passo in SCRIPT_PASSOS():
        if passo.argv[:1] == ["install"]:
            assert "--global" not in passo.argv and "--target" in passo.argv and "{alvo}" in passo.argv, passo.argv
    assert "stdin=subprocess.DEVNULL" in SCRIPT.read_text(encoding="utf-8")


def test_o_alvo_do_smoke_fica_dentro_da_pasta_temporaria(smoke, tmp_path):
    passo = smoke.Passo(argv=["install", "--check", "--target", "{alvo}"], esperado={10})
    assert smoke.resolve_argv(passo, tmp_path) == ["install", "--check", "--target", str(tmp_path / "alvo")]
    assert "alvo" in smoke.PASTAS


def test_cada_passo_json_tem_schema_e_cada_passo_tem_exit_esperado(smoke):
    for passo in smoke.PASSOS:
        assert passo.esperado and all(isinstance(c, int) for c in passo.esperado)
        if "--json" in passo.argv:
            assert passo.schema, f"{passo.argv} prints JSON and must be validated against a packaged schema"
    esperados = {" ".join(p.argv): p for p in smoke.PASSOS}
    assert esperados["install --check --target {alvo}"].esperado == {10}, "a fresh target has the skill pending"
    seco = esperados["install --dry-run --json --target {alvo}"]
    assert seco.esperado == {0} and seco.schema == "install-plan" and seco.status == "dry_run"
    antes = esperados["install --verify --json --target {alvo}"]
    assert antes.esperado == {1} and antes.schema == "install-plan" and antes.status == "failed", "a target never installed fails the verify"
    assert esperados["install --verify --target {alvo}"].esperado == {0}, "after the install the files match the receipt and the package"
    assert esperados["install --target {alvo}"].esperado == {0}
    de_novo = esperados["install --check --json --target {alvo}"]
    assert de_novo.esperado == {0} and de_novo.schema == "install-plan", "after the install the target is up to date"
    assert esperados["install --uninstall --target {alvo}"].esperado == {0}


def test_a_tabela_markdown_tem_as_colunas_pedidas(smoke):
    r = smoke.Resultado(passo=smoke.PASSOS[0], obtido=0, ok=True, motivo="")
    ruim = smoke.Resultado(passo=smoke.PASSOS[1], obtido=3, ok=False, motivo="exit 3 fora de {0, 1}")
    tabela = smoke.tabela([r, ruim])
    linhas = tabela.splitlines()
    cabecalho = [c.strip() for c in linhas[0].strip("|").split("|")]
    assert cabecalho == ["SO", "Python", "Comando", "Esperado", "Obtido", "Resultado"]
    assert set(linhas[1].replace("|", "").replace(" ", "")) <= {"-", ":"}
    assert linhas[2].count("|") == 7 and "| ok |" in linhas[2]
    assert "falhou" in linhas[3] and "3" in linhas[3]
    assert platform.python_version() in linhas[2] and platform.system() in linhas[2]


def test_a_tabela_escapa_a_barra_vertical(smoke):
    passo = smoke.Passo(argv=["x", "a|b"], esperado={0})
    tabela = smoke.tabela([smoke.Resultado(passo=passo, obtido=0, ok=True, motivo="")])
    assert "a\\|b" in tabela


def test_sai_1_e_diz_falhou_quando_um_passo_falha(smoke, monkeypatch, capsys, tmp_path):
    ruim = smoke.Passo(argv=["--version"], esperado={99})
    monkeypatch.setattr(smoke, "PASSOS", [ruim])
    rc = smoke.main(["--pasta", str(tmp_path / "pasta")])
    out = capsys.readouterr().out
    assert rc == 1 and "falhou" in out


def test_um_schema_que_nao_bate_reprova_o_passo(smoke, monkeypatch, capsys, tmp_path):
    passo = smoke.Passo(argv=["doctor", "--json"], esperado={0, 1}, schema="install-plan")  # wrong schema on purpose
    monkeypatch.setattr(smoke, "PASSOS", [passo])
    rc = smoke.main(["--pasta", str(tmp_path / "pasta")])
    out = capsys.readouterr().out
    assert rc == 1 and "schema" in out.lower()


def SCRIPT_PASSOS():
    spec = importlib.util.spec_from_file_location("smoke_so_passos", SCRIPT)
    modulo = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = modulo
    try:
        spec.loader.exec_module(modulo)
        return list(modulo.PASSOS)
    finally:
        sys.modules.pop(spec.name, None)


def test_roda_de_verdade_no_linux_passa_e_nao_toca_no_home_real(smoke, capsys, tmp_path):
    casa = Path.home()
    antes = {n: (casa / n).exists() for n in (".simplicio", ".simplicio-video")}
    rc = smoke.main(["--pasta", str(tmp_path / "pasta"), "--manter"])
    out = capsys.readouterr().out
    assert rc == 0, out
    assert out.count("| ok |") == len(smoke.PASSOS) and "falhou" not in out
    assert platform.python_version() in out and platform.system() in out
    assert {n: (casa / n).exists() for n in antes} == antes, "the smoke touched the real home"
    assert not (tmp_path / "pasta" / "profile" / ".simplicio").exists()
    assert list((tmp_path / "pasta" / "alvo").iterdir()) == [], "the install of the temporary target was uninstalled again"
    assert list((tmp_path / "pasta" / "home").iterdir()) == [] and list((tmp_path / "pasta" / "profile").iterdir()) == []


def test_a_pasta_temporaria_e_apagada_no_fim_salvo_com_manter(smoke, capsys, tmp_path, monkeypatch):
    monkeypatch.setattr(smoke, "PASSOS", [smoke.Passo(argv=["--version"], esperado={0})])
    smoke.main(["--pasta", str(tmp_path / "apagar")])
    capsys.readouterr()
    assert not (tmp_path / "apagar").exists()
    smoke.main(["--pasta", str(tmp_path / "ficar"), "--manter"])
    capsys.readouterr()
    assert (tmp_path / "ficar").is_dir()


def test_o_verify_que_falha_vem_antes_do_install_e_o_que_passa_vem_depois(smoke):
    nomes = [" ".join(p.argv) for p in smoke.PASSOS]
    antes, instalar, depois = (nomes.index(n) for n in ("install --verify --json --target {alvo}", "install --target {alvo}",
                                                         "install --verify --target {alvo}"))
    assert antes < instalar < depois
