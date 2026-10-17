"""Issue #74: o motor roda fora do checkout. Esquemas, templates e motion viajam dentro do pacote
(`src/simplicio_video/data/`), então um `pip install` numa pasta limpa basta para `list`, `validate` e `render`.

- (a) um wheel construído do código-fonte contém os dados em `simplicio_video/data/` (schema, templates, motion);
- (b) wheel extraído fora do repo: `list templates` sai com rc 0 e lista um template do próprio wheel;
- (c) com o mesmo ambiente, `validate` do contrato mínimo (tests/fixtures/mini, copiado para tmp_path) sai com rc 0;
- (d) `render` de 1 s fora do repo; pulado com motivo explícito se faltar node>=22, npx ou ffmpeg;
- (e) rápido: o código-fonte traz os dados em `src/simplicio_video/data/` e o pyproject declara o package-data;
- (f) rápido: `init` num pacote instalado (sem checkout) grava em `./clients/...` e nunca dentro do pacote (site-packages);
- (g) lento: o wheel não leva dado de cliente e declara os metadados do PyPI; o sdist leva os testes inteiros.

(a) a (d) são `slow`: (a) constrói um wheel (pip baixa o setuptools do PyPI) e (d) renderiza. Os subprocessos herdam o
guarda de sockets de `conftest.offline_env()`; os testes rápidos não abrem socket. SIMPLICIO_VIDEO_HOME é removido do
ambiente dos subprocessos: o motor precisa achar os dados sozinho, sem o checkout.
"""
import os
import re
import shutil
import subprocess
import sys
import tomllib
import zipfile
from pathlib import Path

import pytest

from conftest import FIXTURE, ROOT, offline_env

SRC = ROOT / "src" / "simplicio_video"
DATA = SRC / "data"
DADOS_OBRIGATORIOS = [
    "schema/contract.schema.json",
    "schemas/cli/validate-result.schema.json",
    "motion/catalog.json",
    "templates",
]
TEMPLATE_JSON = re.compile(r"^simplicio_video/data/templates/([^/]+)/template\.json$")
PATTERN_JSON = re.compile(r"^simplicio_video/data/motion/patterns/[^/]+/pattern\.json$")
CATALOG_JSON = "simplicio_video/data/motion/catalog.json"
CONTRACT_SCHEMA = "simplicio_video/data/schema/contract.schema.json"
IGNORAR_FIXTURE = shutil.ignore_patterns("out", "build", "timing.lock.json", "render.manifest.json", "voz")


def _copia_fonte(destino: Path) -> Path:
    """Cópia de src/ e dos arquivos que o build lê (pyproject, PYPI.md, LICENSE, NOTICE): o build não suja o checkout."""
    shutil.copytree(ROOT / "src", destino / "src", ignore=shutil.ignore_patterns("__pycache__", "*.egg-info", "build"))
    for nome in ("pyproject.toml", "PYPI.md", "LICENSE", "NOTICE"):
        shutil.copy2(ROOT / nome, destino / nome)
    return destino


def _templates_do_wheel(whl: Path) -> list[str]:
    with zipfile.ZipFile(whl) as z:
        return sorted(m.group(1) for n in z.namelist() if (m := TEMPLATE_JSON.match(n)))


@pytest.fixture(scope="module")
def wheel(tmp_path_factory):
    base = tmp_path_factory.mktemp("pacote")
    fonte = _copia_fonte(base / "fonte")
    saida = base / "wheel"
    r = subprocess.run([sys.executable, "-m", "pip", "wheel", "--no-deps", "-w", str(saida), str(fonte)],
                       capture_output=True, text=True, timeout=900)
    assert r.returncode == 0, r.stdout[-1500:] + r.stderr[-1500:]
    whls = sorted(saida.glob("simplicio_video-*.whl"))
    assert len(whls) == 1, [w.name for w in saida.iterdir()]
    return whls[0]


@pytest.fixture(scope="module")
def instalado(wheel, tmp_path_factory):
    """O wheel extraído numa pasta própria, fora do repo: é o único lugar de onde o pacote pode ser importado."""
    site = tmp_path_factory.mktemp("site")
    with zipfile.ZipFile(wheel) as z:
        z.extractall(site)
    return site


def _env_instalado(site: Path, *, offline: bool = True) -> dict:
    env = offline_env()
    env.pop("SIMPLICIO_VIDEO_HOME", None)
    env["PYTHONPATH"] = os.pathsep.join([str(site), env["PYTHONPATH"]])
    if not offline:
        env.pop("SIMPLICIO_OFFLINE", None)
    return env


def _cli(site: Path, *args, cwd: Path, offline: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-m", "simplicio_video", *map(str, args)], capture_output=True, text=True,
                          cwd=cwd, env=_env_instalado(site, offline=offline), timeout=600)


def _origem_do_pacote(site: Path, cwd: Path) -> Path:
    r = subprocess.run([sys.executable, "-c", "import simplicio_video; print(simplicio_video.__file__)"],
                       capture_output=True, text=True, cwd=cwd, env=_env_instalado(site), timeout=120)
    assert r.returncode == 0, r.stderr
    return Path(r.stdout.strip()).resolve()


def _mini_em(tmp_path: Path) -> Path:
    """O contrato mínimo com o template e a voz que ele referencia (`template: template`, `vo/`)."""
    dst = tmp_path / "mini"
    shutil.copytree(FIXTURE, dst, ignore=IGNORAR_FIXTURE)
    return dst / "contract.yaml"


def _motivo_sem_render() -> str | None:
    from simplicio_video import paths
    env = paths.node_env()
    node = shutil.which("node", path=env["PATH"])
    if not node:
        return "render pulado: falta node (>=22) no PATH"
    versao = subprocess.run([node, "-p", "process.versions.node"], capture_output=True, text=True).stdout.strip()
    if not versao or int(versao.split(".")[0]) < 22:
        return f"render pulado: node {versao or '?'} é anterior a 22"
    if not shutil.which("npx", path=env["PATH"]):
        return "render pulado: falta npx no PATH"
    if not shutil.which("ffmpeg", path=env["PATH"]):
        return "render pulado: falta ffmpeg no PATH"
    return None


def test_dados_do_motor_estao_dentro_do_pacote_fonte():
    faltam = [p for p in DADOS_OBRIGATORIOS if not (DATA / p).exists()]
    assert not faltam, f"dados fora de src/simplicio_video/data/: {faltam}"
    assert list(DATA.glob("templates/*/template.json")), "nenhum template.json em data/templates/"
    assert list(DATA.glob("motion/patterns/*/pattern.json")), "nenhum pattern.json em data/motion/patterns/"


def test_pyproject_declara_package_data_dos_dados():
    cfg = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf8"))
    padroes = cfg["tool"]["setuptools"]["package-data"]["simplicio_video"]
    assert any(p.startswith("data/") for p in padroes), padroes


@pytest.mark.slow
def test_wheel_contem_schema_templates_e_motion(wheel):
    with zipfile.ZipFile(wheel) as z:
        nomes = z.namelist()
    assert CONTRACT_SCHEMA in nomes
    assert CATALOG_JSON in nomes
    assert any(TEMPLATE_JSON.match(n) for n in nomes), "nenhum templates/*/template.json no wheel"
    assert any(PATTERN_JSON.match(n) for n in nomes), "nenhum motion/patterns/*/pattern.json no wheel"


@pytest.mark.slow
def test_list_templates_fora_do_repo(wheel, instalado, tmp_path):
    origem = _origem_do_pacote(instalado, tmp_path)
    assert origem.is_relative_to(instalado), f"o pacote importado não é o do wheel: {origem}"
    r = _cli(instalado, "list", "templates", cwd=tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    nomes = _templates_do_wheel(wheel)
    assert nomes, "wheel sem templates"
    assert any(n in r.stdout for n in nomes), r.stdout


@pytest.mark.slow
def test_validate_contrato_minimo_fora_do_repo(instalado, tmp_path):
    contrato = _mini_em(tmp_path)
    r = _cli(instalado, "validate", contrato, cwd=tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "OK: contrato válido" in r.stdout


@pytest.mark.slow
@pytest.mark.render
def test_render_1s_fora_do_repo(instalado, tmp_path):
    motivo = _motivo_sem_render()
    if motivo:
        pytest.skip(motivo)
    contrato = _mini_em(tmp_path)
    v = _cli(instalado, "voice", contrato, cwd=tmp_path)  # provider file (offline): gera o timing.lock.json que o render exige
    assert v.returncode == 0, v.stdout + v.stderr
    r = _cli(instalado, "render", contrato, cwd=tmp_path, offline=False)
    assert r.returncode == 0, r.stdout[-1500:] + r.stderr[-1500:]
    assert (contrato.parent / "out" / "mini.mp4").is_file()


# ------------------------------------------------------------------ (f) `init` num pacote instalado não escreve no pacote

def _pacote_como_o_pip_deixa(tmp_path: Path) -> Path:
    """site-packages/simplicio_video com código, dados e engine, sem plugin.json por perto: `paths.home()` cai no DATA_DIR."""
    site = tmp_path / "site-packages"
    shutil.copytree(SRC, site / "simplicio_video", ignore=shutil.ignore_patterns("__pycache__"))
    return site


def _arvore(raiz: Path) -> list[str]:
    """Every path under `raiz`, except the bytecode caches that merely importing the package creates."""
    return sorted(p.relative_to(raiz).as_posix() for p in raiz.rglob("*") if "__pycache__" not in p.parts)


def test_init_instalado_grava_na_pasta_atual_e_nao_no_pacote(tmp_path):
    site = _pacote_como_o_pip_deixa(tmp_path)
    antes = _arvore(site)
    trabalho = tmp_path / "trabalho"
    trabalho.mkdir()
    assert _origem_do_pacote(site, trabalho).is_relative_to(site)
    r = _cli(site, "init", "acme", "Teste", "--template", "saude-odontologia", "--nome", "Acme Exemplo", cwd=trabalho)
    assert r.returncode == 0, r.stdout + r.stderr
    contrato = trabalho / "clients" / "acme" / "teste" / "contract.yaml"
    assert contrato.is_file(), f"contrato fora de ./clients/<cliente>/<campanha>: {r.stdout}"
    assert str(contrato) in r.stdout
    assert _arvore(site) == antes, "o init escreveu dentro do pacote instalado (site-packages)"


def test_init_instalado_respeita_o_out_explicito(tmp_path):
    site = _pacote_como_o_pip_deixa(tmp_path)
    antes = _arvore(site)
    trabalho = tmp_path / "trabalho"
    trabalho.mkdir()
    destino = tmp_path / "saida" / "meu-contrato.yaml"
    r = _cli(site, "init", "acme", "Teste", "--template", "saude-odontologia", "--out", destino, cwd=trabalho)
    assert r.returncode == 0, r.stdout + r.stderr
    assert destino.is_file()
    assert not (trabalho / "clients").exists()
    assert _arvore(site) == antes


def test_mcp_init_instalado_grava_na_pasta_atual_e_nao_no_pacote(tmp_path):
    site = _pacote_como_o_pip_deixa(tmp_path)
    antes = _arvore(site)
    trabalho = tmp_path / "trabalho"
    trabalho.mkdir()
    prog = ("import json; from simplicio_video import mcp_server; "
            "print(json.dumps(mcp_server.video_init('acme', 'Teste', 'saude-odontologia', nome='Acme Exemplo')))")
    r = subprocess.run([sys.executable, "-c", prog], capture_output=True, text=True, cwd=trabalho, env=_env_instalado(site), timeout=120)
    assert r.returncode == 0, r.stderr
    res = __import__("json").loads(r.stdout.strip().splitlines()[-1])
    assert res["ok"], res
    contrato = trabalho / "clients" / "acme" / "teste" / "contract.yaml"
    assert contrato.is_file(), res
    assert Path(res["result"]["contrato"]).resolve() == contrato.resolve()
    assert _arvore(site) == antes, "video.init escreveu dentro do pacote instalado (site-packages)"


def test_init_no_checkout_continua_gravando_em_clients_do_checkout(tmp_path):
    """No checkout (plugin.json na raiz, SIMPLICIO_VIDEO_HOME) o padrão não muda: <checkout>/clients/<cliente>/<campanha>."""
    checkout = tmp_path / "checkout"
    (checkout / "src" / "simplicio_video").mkdir(parents=True)
    (checkout / "plugin.json").write_text('{"name": "videos"}', encoding="utf8")
    (checkout / "src" / "simplicio_video" / "data").symlink_to(DATA, target_is_directory=True)
    trabalho = tmp_path / "trabalho"
    trabalho.mkdir()
    env = offline_env(SIMPLICIO_VIDEO_HOME=str(checkout))
    r = subprocess.run([sys.executable, "-m", "simplicio_video", "init", "acme", "Teste", "--template", "saude-odontologia"],
                       capture_output=True, text=True, cwd=trabalho, env=env, timeout=120)
    assert r.returncode == 0, r.stdout + r.stderr
    assert (checkout / "clients" / "acme" / "teste" / "contract.yaml").is_file()
    assert not (trabalho / "clients").exists()


# ------------------------------------------------------------------ (g) wheel e sdist para o PyPI

@pytest.mark.slow
def test_wheel_nao_leva_dado_de_cliente(wheel, tmp_path):
    import dados_cliente_guard as guarda

    with zipfile.ZipFile(wheel) as z:
        z.extractall(tmp_path / "wheel")
    achados = guarda.varrer_arvore(tmp_path / "wheel")
    assert not achados, "dado de cliente no wheel:\n" + "\n".join(achados[:40])


@pytest.mark.slow
def test_wheel_declara_os_metadados_do_pypi(wheel):
    with zipfile.ZipFile(wheel) as z:
        nomes = z.namelist()
        meta_nome = next(n for n in nomes if n.endswith(".dist-info/METADATA"))
        meta = z.read(meta_nome).decode("utf8")
    cabecalho = meta.split("\n\n", 1)[0]
    assert "License-Expression: AGPL-3.0-or-later" in cabecalho
    assert "Author: Wesley Simplicio" in cabecalho
    assert "Author-email" not in cabecalho and "Maintainer" not in cabecalho
    assert "Description-Content-Type: text/markdown" in cabecalho
    assert "Classifier: Operating System :: POSIX :: Linux" in cabecalho
    assert not [c for c in cabecalho.splitlines() if c.startswith("Classifier: License ::")]
    assert not [c for c in cabecalho.splitlines() if c.startswith("Classifier: Operating System ::") and "POSIX :: Linux" not in c]
    for url in ("Homepage, https://github.com/simpletibr/simplicio-videos",
                "Repository, https://github.com/simpletibr/simplicio-videos",
                "Issues, https://github.com/simpletibr/simplicio-videos/issues",
                "Changelog, https://github.com/simpletibr/simplicio-videos/blob/main/CHANGELOG.md"):
        assert f"Project-URL: {url}" in cabecalho, url
    assert any(n.endswith(".dist-info/licenses/LICENSE") for n in nomes)
    assert any(n.endswith(".dist-info/licenses/NOTICE") for n in nomes)
    # a página do PyPI é o PYPI.md (links absolutos), não o README do GitHub
    corpo = meta.split("\n\n", 1)[1]
    assert corpo.lstrip().startswith("# simplicio-video\n")
    assert "](docs/" not in corpo and "](src/" not in corpo and "](clients/" not in corpo


@pytest.mark.slow
def test_sdist_leva_os_testes_inteiros_e_o_changelog(tmp_path):
    """O sdist traz conftest.py e fixtures (quem empacota roda a suíte), CHANGELOG, LICENSE, NOTICE e PYPI.md; nada de clients/."""
    import tarfile

    setuptools = pytest.importorskip("setuptools")
    if int(setuptools.__version__.split(".")[0]) < 77:
        pytest.skip(f"setuptools {setuptools.__version__} < 77 (licença SPDX no pyproject)")
    fonte = _copia_fonte(tmp_path / "fonte")
    shutil.copytree(ROOT / "tests", fonte / "tests", ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
    for nome in ("MANIFEST.in", "CHANGELOG.md"):
        shutil.copy2(ROOT / nome, fonte / nome)
    saida = tmp_path / "sdist"
    saida.mkdir()
    prog = f"from setuptools import build_meta; print(build_meta.build_sdist({str(saida)!r}))"
    r = subprocess.run([sys.executable, "-c", prog], capture_output=True, text=True, cwd=fonte, timeout=900)
    assert r.returncode == 0, r.stdout[-1500:] + r.stderr[-1500:]
    pacote = next(saida.glob("simplicio_video-*.tar.gz"))
    with tarfile.open(pacote) as tar:
        nomes = {n.split("/", 1)[1] for n in tar.getnames() if "/" in n}
    for esperado in ("tests/conftest.py", "tests/fixtures/mini/contract.yaml", "CHANGELOG.md", "LICENSE", "NOTICE", "PYPI.md", "pyproject.toml"):
        assert esperado in nomes, esperado
    assert not [n for n in nomes if n.startswith(("clients/", "coleta/", "prospects/", "docs/"))]
    assert not [n for n in nomes if "__pycache__" in n or n.endswith(".pyc")]
