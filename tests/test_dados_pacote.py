"""Issue #74: o motor roda fora do checkout. Esquemas, templates e motion viajam dentro do pacote
(`src/simplicio_video/data/`), então um `pip install` numa pasta limpa basta para `list`, `validate` e `render`.

- (a) um wheel construído do código-fonte contém os dados em `simplicio_video/data/` (schema, templates, motion);
- (b) wheel extraído fora do repo: `list templates` sai com rc 0 e lista um template do próprio wheel;
- (c) com o mesmo ambiente, `validate` do contrato mínimo (tests/fixtures/mini, copiado para tmp_path) sai com rc 0;
- (d) `render` de 1 s fora do repo; pulado com motivo explícito se faltar node>=22, npx ou ffmpeg;
- (e) rápido: o código-fonte traz os dados em `src/simplicio_video/data/` e o pyproject declara o package-data.

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
    """Cópia de src/, pyproject.toml e README.md: o build não suja o checkout (build/, *.egg-info)."""
    shutil.copytree(ROOT / "src", destino / "src", ignore=shutil.ignore_patterns("__pycache__", "*.egg-info", "build"))
    for nome in ("pyproject.toml", "README.md"):
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
    r = _cli(instalado, "render", contrato, cwd=tmp_path, offline=False)
    assert r.returncode == 0, r.stdout[-1500:] + r.stderr[-1500:]
    assert (contrato.parent / "out" / "mini.mp4").is_file()
