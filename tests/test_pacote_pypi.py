"""Pacote pronto para o PyPI: metadados do `pyproject.toml`, a página `PYPI.md`, `MANIFEST.in` e `NOTICE`.

Hermético: só lê arquivos do repo (o build de verdade está em `test_dados_pacote.py`, marcado `slow`).

- pyproject: `setuptools>=77`, licença como expressão SPDX (sem classificador `License ::`), `license-files`, autor
  sem e-mail, palavras-chave, classificadores só do que foi confirmado e `[project.urls]`;
- `PYPI.md` é o readme do pacote (a página do PyPI), curto e factual, com todos os links absolutos, conferidos contra os
  arquivos de `origin/main` (o que `blob/main/...` resolve no dia do upload);
- `MANIFEST.in` põe só o CHANGELOG no sdist além do que o setuptools já inclui: sem `tests/` e sem o `README.md` do GitHub;
- `NOTICE` aponta para documentos que o pacote não traz por URL absoluta.
"""
from __future__ import annotations

import re
import subprocess
import tomllib
import warnings
from dataclasses import dataclass
from typing import Callable

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
    assert re.search(r"não posta\b.{0,20}\bpublica", nao, re.I | re.S), "diga que não posta nem publica"
    assert re.search(r"não chama (um )?LLM", nao, re.I)


def test_pypi_md_plataformas_so_afirma_o_que_foi_medido(pypi_md):
    plat = _secao(pypi_md, "Plataformas")
    assert "Linux" in plat
    assert re.search(r"macOS", plat) and re.search(r"Windows", plat)
    assert re.search(r"ainda\s+(NÃO|não)\s+(foram\s+)?confirmad[ao]s\s+em\s+máquina\s+real", plat), "diga que macOS e Windows não foram confirmados em máquina real"


def test_pypi_md_nao_cita_o_que_so_existe_em_outro_pr(pypi_md):
    """`scripts/smoke_so.py` e os testes com sistema simulado só chegam com o PR de operação: a página é imutável, então a
    menção volta no PR da release, quando os dois estiverem na main."""
    assert "smoke_so" not in pypi_md
    assert not re.search(r"sistema\s+simulado", pypi_md, re.I)


def test_pypi_md_voz_local_diz_o_que_o_extra_nao_instala(pypi_md):
    """`[local-tts]` instala as bibliotecas, mas a voz local procura um Python em SIMPLICIO_TTS_PY e os modelos do Kokoro."""
    for termo in ("SIMPLICIO_TTS_PY", "kokoro-v1.0.onnx", "voices-v1.0.bin", "KOKORO_DIR"):
        assert termo in pypi_md, f"PYPI.md não menciona {termo}, que a voz local exige"
    linha_do_extra = next(ln for ln in pypi_md.splitlines() if "[local-tts]" in ln and "extra" in ln.lower())
    assert "(voz local Kokoro)" not in linha_do_extra, "o extra não entrega a voz local sozinho"
    assert re.search(r"ainda\s+pede\s+mais|não\s+basta", linha_do_extra), "a linha do extra diz que ele não basta"
    assert re.search(r"não\s+baixa", pypi_md), "diga que o pacote não baixa os modelos"


def test_pypi_md_nao_vende_o_esqueleto_do_init_como_primeiros_passos(pypi_md):
    """Preencher os TODO do esqueleto do `init` não basta: os blocos não batem com o template e o `validate` segue falhando."""
    passos = _secao(pypi_md, "Primeiros passos")
    assert not re.search(r"preencha\s+os\s+`?TODO", passos, re.I)
    assert not re.search(r"falha\s+enquanto\s+houver", passos, re.I)
    assert re.search(r"validate.{0,40}aponta\s+o\s+que\s+falta", passos, re.S), "o validate aponta o que falta"
    assert re.search(r"preencher\s+os\s+`?TODO`?\s+não\s+basta", passos, re.I), "diga que preencher os TODO não basta"
    for guia in ("docs/tutorials/primeiro-video.md", "docs/receita-video-cliente.md"):
        assert f"{REPO}/blob/main/{guia}" in pypi_md, f"link para {guia}"


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


@dataclass
class Referencia:
    """Os arquivos que um link `blob/main/...` resolve no dia do upload: a main, não este branch."""
    nome: str
    existe: Callable[[str], bool]
    ler: Callable[[str], str | None]


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True, timeout=120)


def _referencia() -> Referencia:
    """`origin/main` quando existe (links valem na main); senão o checkout deste branch, com aviso."""
    r = _git("ls-tree", "-r", "--name-only", "origin/main")
    if r.returncode == 0 and r.stdout.strip():
        arquivos = set(r.stdout.splitlines())

        def existe(p: str) -> bool:
            p = p.rstrip("/")
            return p in arquivos or any(a.startswith(p + "/") for a in arquivos)

        def ler(p: str) -> str | None:
            g = _git("show", f"origin/main:{p}")
            return g.stdout if g.returncode == 0 else None

        return Referencia("origin/main", existe, ler)
    warnings.warn("origin/main indisponível (git fetch origin main): os links do PYPI.md foram conferidos contra este branch, "
                  "onde arquivos que só existem aqui passam", stacklevel=2)

    def ler_local(p: str) -> str | None:
        f = ROOT / p
        return f.read_text(encoding="utf8") if f.is_file() else None

    return Referencia("o branch", lambda p: (ROOT / p).exists(), ler_local)


def _ancoras(markdown: str) -> set[str]:
    """Âncoras que o GitHub gera dos títulos: minúsculas, sem pontuação, espaços viram hífen."""
    sem_codigo = re.sub(r"```.*?```", "", markdown, flags=re.S)
    return {re.sub(r"\s", "-", re.sub(r"[^\w\s-]", "", t.strip().lower()))
            for t in re.findall(r"^#{1,6}\s+(.+?)\s*#*\s*$", sem_codigo, re.M)}


_CRASE = re.compile(r"`([^`\n]+)`")
_CAMINHO = re.compile(r"[\w.-]+(?:/[\w.-]+)+/?")


def _caminhos_em_crase(texto: str) -> list[str]:
    """Caminhos de arquivo do repositório entre crases. Fora: comandos, URLs, `~`, `./`, `/abs` e `<placeholders>` (o que o
    `init` cria ou a máquina de quem usa tem)."""
    sem_blocos = re.sub(r"```.*?```", "", texto, flags=re.S)
    achados = []
    for c in _CRASE.findall(sem_blocos):
        if "://" in c or c.startswith(("~", ".", "/")) or "<" in c or " " in c.strip():
            continue
        if _CAMINHO.fullmatch(c):
            achados.append(c)
    return achados


def _links_quebrados(texto: str, ref: Referencia) -> list[str]:
    ruins = []
    for d in _destinos(texto):
        m = re.fullmatch(rf"{re.escape(REPO)}/(?:blob|tree)/main/([^#?]*)(?:#(.*))?", d)
        if not m:
            continue
        caminho, ancora = m.group(1), m.group(2)
        if not ref.existe(caminho):
            ruins.append(f"{d}: o arquivo não existe em {ref.nome}")
        elif ancora and caminho.endswith(".md"):
            conteudo = ref.ler(caminho)
            if conteudo is None or ancora not in _ancoras(conteudo):
                ruins.append(f"{d}: a âncora #{ancora} não existe em {caminho} ({ref.nome})")
    for c in _caminhos_em_crase(texto):
        if not ref.existe(c):
            ruins.append(f"`{c}`: o caminho não existe em {ref.nome}")
    return ruins


def _ref_de_mentira(arquivos: dict[str, str]) -> Referencia:
    return Referencia("a main de mentira", lambda p: p.rstrip("/") in arquivos or any(a.startswith(p.rstrip("/") + "/") for a in arquivos),
                      arquivos.get)


def test_links_do_pypi_md_pegam_o_que_a_conferencia_antiga_deixava_passar():
    """Link para arquivo que só existe no branch, âncora que não existe e caminho entre crases (foi assim que o
    `scripts/smoke_so.py` passou): as três coisas são achadas."""
    main = _ref_de_mentira({"README.md": "# Título\n\n## Seção: um (dois)\n", "docs/guia.md": "# Guia\n"})
    ok = f"[a]({REPO}/blob/main/README.md#seção-um-dois) [b]({REPO}/blob/main/docs/guia.md) `docs/guia.md`"
    assert _links_quebrados(ok, main) == []
    so_no_branch = f"[x]({REPO}/blob/main/MANIFEST.in)"
    assert len(_links_quebrados(so_no_branch, main)) == 1
    assert len(_links_quebrados(f"[x]({REPO}/blob/main/README.md#nao-existe)", main)) == 1
    assert len(_links_quebrados("veja `scripts/smoke_so.py` e `docs/guia.md`", main)) == 1
    # o que não é arquivo do repositório não conta como caminho
    assert _caminhos_em_crase("`clients/<c>/x.yaml` `~/.local/share/x/y.py` `./clients/a/b.yaml` `/opt/x/y` `pip install x/y` "
                              "`https://a.b/c/d` `GEMINI_API_KEY` `PYPI.md` `docs/guia.md`") == ["docs/guia.md"]
    assert _ancoras("# Um título\n## Sub: `código` (x)\n```\n# comentário\n```\n") == {"um-título", "sub-código-x"}


def test_pypi_md_links_e_caminhos_existem_na_main(pypi_md):
    ref = _referencia()
    do_repo = [d for d in _destinos(pypi_md) if d.startswith(f"{REPO}/blob/main/")]
    assert do_repo, "PYPI.md deve linkar documentos do repositório por URL absoluta"
    ruins = _links_quebrados(pypi_md, ref)
    assert not ruins, f"link ou caminho que não existe em {ref.nome}:\n" + "\n".join(ruins)
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
        pytest.fail("MANIFEST.in não existe: o sdist precisa do CHANGELOG e de tirar tests/ e README.md", pytrace=False)
    return [ln.strip() for ln in p.read_text(encoding="utf8").splitlines() if ln.strip() and not ln.startswith("#")]


def test_manifest_poe_so_o_changelog_e_tira_testes_readme_e_bytecode():
    """A suíte não vai para o sdist (precisa de clients/, docs/, scripts/ e git, e leva nomes e fixtures de cliente), o
    README.md do GitHub também (o do pacote é o PYPI.md) e o bytecode de um checkout sujo muito menos."""
    linhas = _manifest()
    assert "include CHANGELOG.md" in linhas
    assert "prune tests" in linhas
    assert "exclude README.md" in linhas
    assert "graft tests" not in linhas
    assert "global-exclude *.py[cod]" in linhas and "global-exclude __pycache__" in linhas


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
    """`pip install .` na imagem lê o readme (PYPI.md) e os license-files (LICENSE, NOTICE). Sem eles o build NÃO quebra: o
    setuptools só avisa e gera um wheel sem o readme declarado e sem LICENSE/NOTICE (a AGPL exige o texto no artefato)."""
    copiados: set[str] = set()
    for linha in (ROOT / "Dockerfile").read_text(encoding="utf8").splitlines():
        partes = linha.split()
        if partes[:1] == ["COPY"] and not any(p.startswith("--from") for p in partes):
            copiados.update(partes[1:-1])
    readme = projeto["project"]["readme"]
    lidos = {"pyproject.toml", readme["file"] if isinstance(readme, dict) else readme, *projeto["project"].get("license-files", [])}
    assert {"pyproject.toml", "PYPI.md", "LICENSE", "NOTICE"} <= copiados, f"o Dockerfile copia só {sorted(copiados)}"
    assert lidos <= copiados, f"o pyproject lê {sorted(lidos - copiados)}, que o Dockerfile não copia"


def test_dockerfile_trabalha_dentro_do_volume():
    """O `init` grava em ./clients/... na pasta atual: no contêiner (`run --rm`) isso só sobrevive dentro do volume."""
    estagio_final = (ROOT / "Dockerfile").read_text(encoding="utf8").split("FROM ")[-1]
    workdirs = re.findall(r"^WORKDIR\s+(\S+)", estagio_final, re.M)
    volumes = re.findall(r'"(/[^"]+)"', next(ln for ln in estagio_final.splitlines() if ln.startswith("VOLUME")))
    assert workdirs and volumes, (workdirs, volumes)
    assert workdirs[-1] in volumes, f"WORKDIR {workdirs[-1]} fica fora do volume {volumes}: o contrato do init some com o --rm"
