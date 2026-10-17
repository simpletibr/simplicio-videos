"""Issue #74: o motor roda fora do checkout. Esquemas, templates e motion viajam dentro do pacote
(`src/simplicio_video/data/`), então um `pip install` numa pasta limpa basta para `list`, `validate` e `render`.

- (a) um wheel construído do código-fonte contém os dados em `simplicio_video/data/` (schema, templates, motion);
- (b) wheel extraído fora do repo: `list templates` sai com rc 0 e lista um template do próprio wheel;
- (c) com o mesmo ambiente, `validate` do contrato mínimo (tests/fixtures/mini, copiado para tmp_path) sai com rc 0;
- (d) `render` de 1 s fora do repo; pulado com motivo explícito se faltar node>=22, npx ou ffmpeg;
- (e) rápido: o código-fonte traz os dados em `src/simplicio_video/data/` e o pyproject declara o package-data;
- (f) rápido: `init` num pacote instalado (sem checkout) grava em `./clients/...` e nunca dentro do pacote (site-packages);
- (g) lento: o wheel não leva dado de cliente e declara os metadados do PyPI; o sdist, construído de uma cópia do checkout com
  cache de bytecode plantado, não leva `tests/`, `README.md` nem bytecode, e passa pela mesma guarda de dado de cliente.

(a) a (d) e o sdist de (g) são `slow`: (a) constrói um wheel (pip baixa o setuptools do PyPI), o sdist usa o setuptools do
ambiente (ou o instala numa pasta temporária pelo pip) e (d) renderiza. Os subprocessos herdam o
guarda de sockets de `conftest.offline_env()`; os testes rápidos não abrem socket. SIMPLICIO_VIDEO_HOME é removido do
ambiente dos subprocessos: o motor precisa achar os dados sozinho, sem o checkout.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
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


def _video_init(site: Path, cwd: Path, **kw) -> dict:
    """`mcp_server.video_init` chamado num processo que só enxerga o pacote copiado como o pip deixa."""
    prog = ("import json, sys; from simplicio_video import mcp_server; "
            "print(json.dumps(mcp_server.video_init(**json.loads(sys.argv[1]))))")
    r = subprocess.run([sys.executable, "-c", prog, json.dumps(kw)], capture_output=True, text=True, cwd=cwd,
                       env=_env_instalado(site), timeout=120)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout.strip().splitlines()[-1])


BASE_INIT = {"cliente": "acme", "campanha": "Teste", "template": "saude-odontologia", "nome": "Acme Exemplo"}


def test_mcp_init_instalado_sem_out_nao_grava_e_pede_o_out(tmp_path):
    """Sem checkout o servidor MCP não sabe onde gravar: a pasta onde ele foi iniciado (`/`, `$HOME`, a pasta da IDE) não é
    escolha do cliente LLM. Nada é gravado e o erro pede `out`."""
    site = _pacote_como_o_pip_deixa(tmp_path)
    antes = _arvore(site)
    trabalho = tmp_path / "trabalho"
    trabalho.mkdir()
    res = _video_init(site, trabalho, **BASE_INIT)
    assert res["ok"] is False, res
    assert "`out`" in res["error"] and "caminho absoluto" in res["error"], res["error"]
    assert "clients" in res["error"] or "pasta" in res["error"], res["error"]
    assert list(trabalho.iterdir()) == [], "o video.init gravou na pasta onde o servidor foi iniciado"
    assert _arvore(site) == antes, "video.init escreveu dentro do pacote instalado (site-packages)"


def test_mcp_init_instalado_recusa_out_relativo(tmp_path):
    """Um `out` relativo cai na mesma pasta que o cliente não controla."""
    site = _pacote_como_o_pip_deixa(tmp_path)
    trabalho = tmp_path / "trabalho"
    trabalho.mkdir()
    res = _video_init(site, trabalho, out="clients/acme/teste/contract.yaml", **BASE_INIT)
    assert res["ok"] is False and "caminho absoluto" in res["error"], res
    assert list(trabalho.iterdir()) == []


def test_mcp_init_instalado_com_out_grava_la(tmp_path):
    site = _pacote_como_o_pip_deixa(tmp_path)
    antes = _arvore(site)
    trabalho = tmp_path / "trabalho"
    trabalho.mkdir()
    destino = tmp_path / "projeto" / "acme" / "contract.yaml"
    res = _video_init(site, trabalho, out=str(destino), **BASE_INIT)
    assert res["ok"], res
    assert destino.is_file()
    assert Path(res["result"]["contrato"]).resolve() == destino.resolve()
    assert list(trabalho.iterdir()) == []
    assert _arvore(site) == antes


def test_mcp_init_no_checkout_continua_em_clients_do_checkout(tmp_path):
    """No checkout o `out` continua opcional: <checkout>/clients/<cliente>/<campanha>/contract.yaml."""
    checkout = tmp_path / "checkout"
    (checkout / "src" / "simplicio_video").mkdir(parents=True)
    (checkout / "plugin.json").write_text('{"name": "videos"}', encoding="utf8")
    (checkout / "src" / "simplicio_video" / "data").symlink_to(DATA, target_is_directory=True)
    trabalho = tmp_path / "trabalho"
    trabalho.mkdir()
    env = offline_env(SIMPLICIO_VIDEO_HOME=str(checkout))
    env["PYTHONPATH"] = os.pathsep.join([str(ROOT / "src"), env["PYTHONPATH"]])
    prog = ("import json, sys; from simplicio_video import mcp_server; "
            "print(json.dumps(mcp_server.video_init(**json.loads(sys.argv[1]))))")
    r = subprocess.run([sys.executable, "-c", prog, json.dumps(BASE_INIT)], capture_output=True, text=True, cwd=trabalho, env=env, timeout=120)
    assert r.returncode == 0, r.stderr
    res = json.loads(r.stdout.strip().splitlines()[-1])
    assert res["ok"], res
    assert (checkout / "clients" / "acme" / "teste" / "contract.yaml").is_file()
    assert list(trabalho.iterdir()) == []


def test_init_no_checkout_continua_gravando_em_clients_do_checkout(tmp_path):
    """No checkout (plugin.json na raiz, SIMPLICIO_VIDEO_HOME) o padrão não muda: <checkout>/clients/<cliente>/<campanha>."""
    checkout = tmp_path / "checkout"
    (checkout / "src" / "simplicio_video").mkdir(parents=True)
    (checkout / "plugin.json").write_text('{"name": "videos"}', encoding="utf8")
    (checkout / "src" / "simplicio_video" / "data").symlink_to(DATA, target_is_directory=True)
    trabalho = tmp_path / "trabalho"
    trabalho.mkdir()
    env = offline_env(SIMPLICIO_VIDEO_HOME=str(checkout))
    env["PYTHONPATH"] = os.pathsep.join([str(ROOT / "src"), env["PYTHONPATH"]])  # absolute: the cwd below is not the repo
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


# O sdist sai de uma cópia do checkout (tudo que o git rastreia ou ainda não ignora, como um `git archive` do que está na
# mesa). A cópia "suja" leva cache de bytecode plantado em tests/, no pacote e dentro de data/: o que um `python -m build`
# num checkout sujo encontraria. A "limpa" é a de uma release: sem aviso nenhum do build. A guarda de dado de cliente roda
# sobre o sdist inteiro, não só sobre src/.
LIXO_DE_BYTECODE = ("tests/__pycache__/planted.cpython-313.pyc", "src/simplicio_video/__pycache__/planted.cpython-313.pyc",
                    "src/simplicio_video/data/motion/__pycache__/planted.cpython-313.pyc")
# Tudo o que o sdist pode ter na raiz: o resto (tests/, README.md, MANIFEST.in, clients/, docs/, scripts/...) fica de fora.
RAIZ_DO_SDIST = {"src", "pyproject.toml", "PKG-INFO", "setup.cfg", "CHANGELOG.md", "LICENSE", "NOTICE", "PYPI.md"}


def _copia_do_checkout(destino: Path, *, sujo: bool) -> Path:
    r = subprocess.run(["git", "-C", str(ROOT), "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, f"git ls-files falhou (o teste do sdist precisa do checkout): {r.stderr}"
    for rel in filter(None, r.stdout.split("\0")):
        origem = ROOT / rel
        if origem.is_file():
            (destino / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(origem, destino / rel)
    for lixo in LIXO_DE_BYTECODE if sujo else ():
        (destino / lixo).parent.mkdir(parents=True, exist_ok=True)
        (destino / lixo).write_bytes(b"\0")
    return destino


@pytest.fixture(scope="module")
def env_de_build(tmp_path_factory) -> dict:
    """Ambiente com setuptools>=77: o do interpretador se já tem; senão o pip o instala numa pasta temporária.

    Falha (nunca pula) se não houver como obter a ferramenta: sem ela o sdist não é medido e o teste não vale nada."""
    env = os.environ.copy()
    try:
        import setuptools
        if int(setuptools.__version__.split(".")[0]) >= 77:
            return env
    except ImportError:
        pass
    alvo = tmp_path_factory.mktemp("setuptools-77") / "pacotes"
    r = subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "--no-deps", "--target", str(alvo), "setuptools>=77"],
                       capture_output=True, text=True, timeout=900)
    if r.returncode != 0:
        pytest.fail("sem setuptools>=77 para construir o sdist (instale: pip install 'setuptools>=77'):\n"
                    + r.stdout[-800:] + r.stderr[-800:], pytrace=False)
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(alvo), env.get("PYTHONPATH", "")]))
    return env


def _construir(pasta: Path, env: dict, comando: str, saida: Path) -> tuple[Path, str]:
    """Roda `setuptools.build_meta.<comando>` em `pasta`; devolve o arquivo gerado e tudo o que o build escreveu."""
    saida.mkdir()
    prog = f"from setuptools import build_meta; print(build_meta.{comando}({str(saida)!r}))"
    r = subprocess.run([sys.executable, "-c", prog], capture_output=True, text=True, cwd=pasta, env=env, timeout=900)
    assert r.returncode == 0, r.stdout[-1500:] + r.stderr[-1500:]
    return saida / r.stdout.strip().splitlines()[-1], r.stdout + r.stderr


def _extrai(tar_gz: Path, destino: Path) -> Path:
    with tarfile.open(tar_gz) as tar:
        tar.extractall(destino, filter="data")
    return next(destino.iterdir())


@pytest.fixture(scope="module")
def sdist(tmp_path_factory, env_de_build) -> Path:
    """O sdist de um checkout sujo (bytecode plantado)."""
    base = tmp_path_factory.mktemp("sdist")
    return _construir(_copia_do_checkout(base / "fonte", sujo=True), env_de_build, "build_sdist", base / "saida")[0]


@pytest.fixture(scope="module")
def build_de_release(tmp_path_factory, env_de_build) -> dict:
    """O que `python -m build` faz numa cópia limpa: o sdist e, a partir dele extraído, o wheel (com tudo o que escreveram)."""
    base = tmp_path_factory.mktemp("release")
    tar_gz, log_sdist = _construir(_copia_do_checkout(base / "fonte", sujo=False), env_de_build, "build_sdist", base / "sdist")
    extraido = _extrai(tar_gz, base / "extraido")
    whl, log_wheel = _construir(extraido, env_de_build, "build_wheel", base / "wheel")
    return {"sdist": tar_gz, "wheel": whl, "log_sdist": log_sdist, "log_wheel": log_wheel}


@pytest.fixture(scope="module")
def sdist_nomes(sdist) -> set[str]:
    with tarfile.open(sdist) as tar:
        return {n.split("/", 1)[1].rstrip("/") for n in tar.getnames() if "/" in n}


@pytest.fixture(scope="module")
def sdist_extraido(sdist, tmp_path_factory) -> Path:
    return _extrai(sdist, tmp_path_factory.mktemp("sdist-extraido"))


@pytest.mark.slow
def test_sdist_nao_leva_os_testes_nem_o_readme_do_github(sdist_nomes):
    """A suíte não roda a partir do sdist (precisa de clients/, docs/, scripts/ e git): 200 falhas medidas. Ela leva nomes e
    fixtures de cliente, então fica fora. O README.md do GitHub também (o readme do pacote é o PYPI.md)."""
    assert not [n for n in sdist_nomes if n == "tests" or n.startswith("tests/")], "tests/ no sdist"
    assert "README.md" not in sdist_nomes
    raiz = {n.split("/", 1)[0] for n in sdist_nomes}
    assert raiz <= RAIZ_DO_SDIST, f"raiz do sdist com o que não devia: {sorted(raiz - RAIZ_DO_SDIST)}"


@pytest.mark.slow
def test_sdist_leva_o_changelog_as_licencas_e_o_readme_do_pacote(sdist_nomes, sdist_extraido):
    for esperado in ("CHANGELOG.md", "LICENSE", "NOTICE", "PYPI.md", "pyproject.toml", "PKG-INFO",
                     "src/simplicio_video/cli.py", "src/simplicio_video/data/schema/contract.schema.json"):
        assert esperado in sdist_nomes, esperado
    pkg_info = (sdist_extraido / "PKG-INFO").read_text(encoding="utf8")
    assert "Description-Content-Type: text/markdown" in pkg_info
    assert pkg_info.split("\n\n", 1)[1].lstrip().startswith("# simplicio-video\n")


@pytest.mark.slow
def test_sdist_nao_leva_bytecode(sdist_nomes):
    """O cache de bytecode de um checkout sujo (plantado na cópia, em tests/, no pacote e em data/) não vai para o PyPI."""
    sujos = [n for n in sdist_nomes if "__pycache__" in n or n.endswith((".pyc", ".pyo"))]
    assert not sujos, sujos


@pytest.mark.slow
def test_sdist_nao_leva_dado_de_cliente(sdist_extraido):
    """A mesma guarda do wheel e de src/, sobre o sdist inteiro: texto, nomes de arquivo e o hash da prévia antiga."""
    import dados_cliente_guard as guarda

    achados = guarda.varrer_arvore(sdist_extraido)
    assert not achados, f"{len(achados)} achado(s) de dado de cliente no sdist:\n" + "\n".join(achados[:40])


@pytest.mark.slow
def test_build_de_release_nao_emite_aviso(build_de_release):
    """Numa cópia limpa nem o sdist nem o wheel feito a partir dele avisam nada. Um `exclude` ou `global-exclude` que não acha
    o arquivo avisa ("warning: no previously-included files ..."), e o wheel relê o MANIFEST.in do sdist, onde o README.md e a
    suíte já ficaram de fora: por isso o sdist também não leva o MANIFEST.in."""
    for qual in ("log_sdist", "log_wheel"):
        avisos = [ln for ln in build_de_release[qual].splitlines() if ln.lower().startswith("warning")]
        assert not avisos, f"{qual}: {avisos}"


@pytest.mark.slow
def test_wheel_feito_a_partir_do_sdist_leva_as_licencas_e_nao_leva_bytecode(build_de_release):
    with zipfile.ZipFile(build_de_release["wheel"]) as z:
        nomes = z.namelist()
    assert any(n.endswith(".dist-info/licenses/LICENSE") for n in nomes)
    assert any(n.endswith(".dist-info/licenses/NOTICE") for n in nomes)
    assert CONTRACT_SCHEMA in nomes
    assert not [n for n in nomes if "__pycache__" in n or n.endswith((".pyc", ".pyo"))]
