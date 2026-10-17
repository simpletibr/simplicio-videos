"""Pacote pronto para o PyPI: metadados do `pyproject.toml`, a página `PYPI.md`, `MANIFEST.in` e `NOTICE`.

Hermético: só lê arquivos do repo (o build de verdade está em `test_dados_pacote.py`, marcado `slow`).

- pyproject: `setuptools>=77`, licença como expressão SPDX (sem classificador `License ::`), `license-files`, autor
  sem e-mail, palavras-chave, classificadores só do que foi confirmado e `[project.urls]`;
- `PYPI.md` é o readme do pacote (a página do PyPI), curto e factual, com todos os links absolutos;
- `MANIFEST.in` põe a suíte inteira e o CHANGELOG no sdist;
- `NOTICE` aponta para documentos que o pacote não traz por URL absoluta.
"""
from __future__ import annotations

import re
import tomllib

import pytest

from conftest import ROOT

REPO = "https://github.com/simpletibr/simplicio-videos"
CLASSIFICADORES = {
    "Development Status :: 4 - Beta",
    "Environment :: Console",
    "Intended Audience :: Developers",
    "Operating System :: POSIX :: Linux",  # só Linux: macOS e Windows ainda não foram confirmados em máquina real
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
    "Programming Language :: Python :: 3.13",
    "Topic :: Multimedia :: Video",
}


@pytest.fixture(scope="module")
def projeto() -> dict:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf8"))


@pytest.fixture(scope="module")
def pypi_md() -> str:
    p = ROOT / "PYPI.md"
    return p.read_text(encoding="utf8") if p.is_file() else ""


# --------------------------------------------------------------------------- pyproject.toml
def test_build_system_exige_setuptools_com_licenca_spdx(projeto):
    exigencias = projeto["build-system"]["requires"]
    setuptools = [r for r in exigencias if r.lower().startswith("setuptools")]
    assert setuptools, exigencias
    m = re.fullmatch(r"setuptools\s*>=\s*(\d+)(?:\.\d+)*", setuptools[0])
    assert m and int(m.group(1)) >= 77, f"licença SPDX pede setuptools>=77, mas é {setuptools[0]!r}"


def test_licenca_e_expressao_spdx_com_arquivos(projeto):
    p = projeto["project"]
    assert p["license"] == "AGPL-3.0-or-later"
    assert p["license-files"] == ["LICENSE", "NOTICE"]


def test_autor_sem_email(projeto):
    p = projeto["project"]
    assert p["authors"] == [{"name": "Wesley Simplicio"}]
    assert "maintainers" not in p
    assert "@" not in str(p["authors"])


def test_palavras_chave(projeto):
    chaves = projeto["project"]["keywords"]
    assert isinstance(chaves, list) and len(chaves) >= 5
    assert {"video", "mcp", "hyperframes"} <= set(chaves)


def test_classificadores_so_do_que_foi_confirmado(projeto):
    classes = projeto["project"]["classifiers"]
    assert set(classes) == CLASSIFICADORES, f"sobra {sorted(set(classes) - CLASSIFICADORES)}, falta {sorted(CLASSIFICADORES - set(classes))}"
    assert len(classes) == len(set(classes))
    assert not [c for c in classes if c.startswith("License ::")], "expressão SPDX e classificador License :: não convivem"
    assert not [c for c in classes if "Windows" in c or "Microsoft" in c or "MacOS" in c or "OS Independent" in c]


def test_urls_do_projeto(projeto):
    assert projeto["project"]["urls"] == {
        "Homepage": REPO,
        "Repository": REPO,
        "Issues": f"{REPO}/issues",
        "Changelog": f"{REPO}/blob/main/CHANGELOG.md",
    }


def test_readme_do_pacote_e_o_pypi_md(projeto):
    assert projeto["project"]["readme"] == {"file": "PYPI.md", "content-type": "text/markdown"}


def test_versao_do_pyproject_bate_com_o_init(projeto):
    # o release tem o próprio bump (pyproject, __init__.py e plugin.json juntos); aqui só se confere que não divergiram
    init = (ROOT / "src" / "simplicio_video" / "__init__.py").read_text(encoding="utf8")
    assert f'__version__ = "{projeto["project"]["version"]}"' in init


# --------------------------------------------------------------------------- PYPI.md
def test_pypi_md_existe_na_raiz():
    assert (ROOT / "PYPI.md").is_file(), "PYPI.md não existe na raiz: é a página do PyPI (readme do pacote)"


def _secao(texto: str, titulo: str) -> str:
    m = re.search(rf"^## {re.escape(titulo)}\s*\n(.*?)(?=^## |\Z)", texto, re.M | re.S)
    assert m, f"PYPI.md sem a seção '## {titulo}'"
    return m.group(1)


def test_pypi_md_abre_com_o_nome_e_e_curto(pypi_md):
    assert pypi_md.startswith("# simplicio-video\n")
    assert len(pypi_md.splitlines()) <= 120, "PYPI.md deve ser curto e factual"


def test_pypi_md_diz_como_instalar(pypi_md):
    for cmd in ("pip install simplicio-video", "pipx install simplicio-video", 'pip install "simplicio-video[mcp]"'):
        assert cmd in pypi_md, cmd


def test_pypi_md_requisitos(pypi_md):
    req = _secao(pypi_md, "Requisitos")
    assert re.search(r"Node(\.js)?\s*>=\s*22", req), "Node >= 22"
    assert "ffmpeg" in req and "libass" in req
    assert "hyperframes@0.8.97" in req and "npx" in req
    assert "470 MB" in req
    assert "Chrome" in req
    assert re.search(r"Python\s*>=\s*3\.10", req)
    assert "primeiro render" in req


def test_pypi_md_primeiros_passos(pypi_md):
    passos = _secao(pypi_md, "Primeiros passos")
    ordem = [passos.find(f"simplicio-video {c}") for c in ("setup", "doctor", "init", "validate", "run")]
    assert all(i >= 0 for i in ordem), ordem
    assert ordem == sorted(ordem), "setup, doctor, init, validate, run, nessa ordem"
    assert re.search(r"doctor.{0,60}(sai com erro|falha).{0,80}setup", passos, re.S | re.I), "doctor sai com erro até rodar setup"


def test_pypi_md_o_que_nao_faz(pypi_md):
    nao = _secao(pypi_md, "O que não faz")
    assert re.search(r"não posta", nao, re.I) and re.search(r"não publica", nao, re.I)
    assert re.search(r"não chama (um )?LLM", nao, re.I)


def test_pypi_md_plataformas_so_afirma_o_que_foi_medido(pypi_md):
    plat = _secao(pypi_md, "Plataformas")
    assert "Linux" in plat
    assert re.search(r"macOS", plat) and re.search(r"Windows", plat)
    assert re.search(r"ainda\s+(NÃO|não)\s+(foram\s+)?confirmad[ao]s\s+em\s+máquina\s+real", plat), "diga que macOS e Windows não foram confirmados em máquina real"
    assert "smoke_so.py" in plat


def test_pypi_md_licenca(pypi_md):
    lic = _secao(pypi_md, "Licença")
    assert "AGPL-3.0-or-later" in lic


_LINK = re.compile(r"!?\[[^\]]*\]\(\s*<?([^)\s>]+)")
_LINK_REF = re.compile(r"^\s*\[[^\]]+\]:\s*<?(\S+)", re.M)
_HTML = re.compile(r"""(?:href|src)\s*=\s*["']([^"']+)["']""", re.I)
_AUTO = re.compile(r"<((?:[a-z][a-z0-9+.-]*):[^>\s]+)>", re.I)


def _destinos(texto: str) -> list[str]:
    sem_codigo = re.sub(r"```.*?```", "", texto, flags=re.S)
    sem_codigo = re.sub(r"`[^`\n]*`", "", sem_codigo)
    return [m for rx in (_LINK, _LINK_REF, _HTML, _AUTO) for m in rx.findall(sem_codigo)]


def test_pypi_md_todos_os_links_sao_absolutos(pypi_md):
    destinos = _destinos(pypi_md)
    assert destinos, "PYPI.md sem nenhum link"
    ruins = [d for d in destinos if not d.startswith("https://")]
    assert not ruins, f"link relativo ou sem https na página do PyPI (quebra fora do GitHub): {ruins}"


def test_pypi_md_links_do_repositorio_apontam_para_arquivos_que_existem(pypi_md):
    prefixo = f"{REPO}/blob/main/"
    do_repo = [d for d in _destinos(pypi_md) if d.startswith(prefixo)]
    assert do_repo, "PYPI.md deve linkar documentos do repositório por URL absoluta"
    faltam = [d for d in do_repo if not (ROOT / d[len(prefixo):].split("#", 1)[0]).exists()]
    assert not faltam, f"link para arquivo que não existe no repositório: {faltam}"
    outros = [d for d in _destinos(pypi_md) if d.startswith("https://github.com/") and not d.startswith(REPO)]
    assert not outros, outros


def test_pypi_md_nao_cita_cliente(pypi_md):
    import dados_cliente_guard as guarda

    assert pypi_md, "PYPI.md vazio ou ausente"
    assert guarda.achados_no_texto(pypi_md, "PYPI.md") == []


# --------------------------------------------------------------------------- MANIFEST.in
def _manifest() -> list[str]:
    p = ROOT / "MANIFEST.in"
    if not p.is_file():
        pytest.fail("MANIFEST.in não existe: o sdist precisa da suíte inteira e do CHANGELOG", pytrace=False)
    return [ln.strip() for ln in p.read_text(encoding="utf8").splitlines() if ln.strip() and not ln.startswith("#")]


def test_manifest_poe_a_suite_inteira_e_o_changelog_no_sdist():
    linhas = _manifest()
    assert "graft tests" in linhas
    assert "include CHANGELOG.md" in linhas
    assert any(ln.startswith("global-exclude") and "__pycache__" in ln and "*.py[cod]" in ln for ln in linhas)


def test_manifest_nao_puxa_dado_de_cliente_nem_pastas_de_operacao():
    for ln in _manifest():
        assert not re.search(r"\b(clients|coleta|prospects|intake|docs)\b", ln), ln


# --------------------------------------------------------------------------- NOTICE
def test_notice_usa_url_absoluta_para_o_que_o_pacote_nao_traz():
    texto = (ROOT / "NOTICE").read_text(encoding="utf8")
    for rel in ("docs/legal/README.md", "docs/licenses.md"):
        assert f"{REPO}/blob/main/{rel}" in texto, rel
        assert not re.search(rf"(?<!main/){re.escape(rel)}", texto), f"{rel} aparece como caminho relativo (o pacote não traz docs/)"
        assert (ROOT / rel).is_file()
    assert "AGPL-3.0-or-later" in texto and "LICENSE" in texto


# --------------------------------------------------------------------------- Dockerfile
def test_dockerfile_copia_o_que_o_build_do_pacote_le(projeto):
    """`pip install .` na imagem lê o readme (PYPI.md) e os license-files (LICENSE, NOTICE): sem eles o build quebra."""
    copiados: set[str] = set()
    for linha in (ROOT / "Dockerfile").read_text(encoding="utf8").splitlines():
        partes = linha.split()
        if partes[:1] == ["COPY"] and not any(p.startswith("--from") for p in partes):
            copiados.update(partes[1:-1])
    readme = projeto["project"]["readme"]
    lidos = {"pyproject.toml", readme["file"] if isinstance(readme, dict) else readme, *projeto["project"].get("license-files", [])}
    assert {"pyproject.toml", "PYPI.md", "LICENSE", "NOTICE"} <= copiados, f"o Dockerfile copia só {sorted(copiados)}"
    assert lidos <= copiados, f"o pyproject lê {sorted(lidos - copiados)}, que o Dockerfile não copia"
