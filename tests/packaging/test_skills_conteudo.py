"""Review of PR #117 (B1): what the two skills tell an agent must be true of the CLI that ships with them.

The skills travel in the wheel (public on PyPI, immutable): a line that says "`install` creates the `.venv`" or "`update` refuses a
dirty tree, stash it" makes an agent run the wrong command or stash the user's work for nothing. Nothing checked the text, so
these tests do:

* every `simplicio-video <command> [<verb>] --flag` in a code block or in an inline code span exists in the real parsers (the nested
  ones of `social`, `openverse` and `busca` included), and so does every verb;
* no sentence describes the removed behavior of `install` (the `.venv`) or of `update` (pull, stash, dirty tree);
* the text says what `install` and `update` do now, with the exact commands;
* no customer, owner or e-mail in a skill that is published to PyPI; the package copy equals the `skills/` mirror byte by byte.
"""
from __future__ import annotations

import argparse
import re

import pytest

from _comum import ROOT
from simplicio_video import busca, openverse, social
from simplicio_video.cli import build_parser

PACOTE = ROOT / "src" / "simplicio_video" / "data" / "skills"
ESPELHO = ROOT / "skills"
NOMES = ("simplicio-video", "simplicio-video-social")
DELEGADOS = {"social": social._parser, "openverse": openverse._parser, "busca": busca._parser}  # `args: REMAINDER` in cli.py


def _texto(nome: str) -> str:
    return (PACOTE / nome / "SKILL.md").read_text(encoding="utf-8")


def _sub(parser) -> dict:
    for acao in parser._actions:
        if isinstance(acao, argparse._SubParsersAction):
            return dict(acao.choices)
    return {}


def _flags(parser) -> set:
    return {opcao for acao in parser._actions for opcao in acao.option_strings}


def _comandos(texto: str) -> list:
    """Every `simplicio-video ...` line of a fenced block and every inline code span that starts with it."""
    linhas, dentro = [], False
    for linha in texto.splitlines():
        if linha.strip().startswith("```"):
            dentro = not dentro
        elif dentro:
            linhas.append(linha.strip())
    linhas += re.findall(r"`([^`\n]+)`", texto)
    return [re.sub(r"\s+#.*$", "", item) for item in linhas if item.startswith("simplicio-video ")]


def _confere(comando: str) -> list:
    """What is wrong with one command line: an unknown verb, or a flag that the parser at the end of the chain does not have."""
    problemas = []
    palavras = comando.split()[1:]
    parser, usados = build_parser(), []
    for palavra in palavras:
        if len(usados) == 1 and usados[0] in DELEGADOS and not getattr(parser, "_delegado", False):
            parser = DELEGADOS[usados[0]]()
            parser._delegado = True
        filhos = _sub(parser)
        if palavra in filhos:
            parser = filhos[palavra]
            usados.append(palavra)
        elif filhos and re.fullmatch(r"[a-z][a-z-]*", palavra) and "|" not in palavra and usados:
            problemas.append(f"`{palavra}` is not a verb of `{' '.join(usados)}` ({sorted(filhos)})")
            break
        elif not palavra.startswith(("-", "<", "[", '"', "'")):
            break
    for flag in set(re.findall(r"--[a-z][a-z0-9-]*", comando)):
        if flag not in _flags(parser):
            problemas.append(f"{flag} is not a flag of `simplicio-video {' '.join(usados)}`")
    return problemas


@pytest.mark.parametrize("nome", NOMES)
def test_cada_comando_e_flag_citado_na_skill_existe_no_cli(nome):
    comandos = _comandos(_texto(nome))
    assert comandos, f"{nome}: no `simplicio-video ...` command found: the scan is broken"
    ruins = {c: p for c in comandos if (p := _confere(c))}
    assert not ruins, "the skill cites commands that the CLI does not have:\n" + "\n".join(f"  {c}\n    {p}" for c, p in ruins.items())


def test_o_varredor_acha_um_verbo_e_uma_flag_que_nao_existem():
    assert _confere("simplicio-video install --venv") and _confere("simplicio-video openverse library inexistente")
    assert _confere("simplicio-video social plan --nao-existe") and _confere("simplicio-video busca consulta --nao-existe")
    assert not _confere("simplicio-video install --global --check") and not _confere("simplicio-video openverse library verify <contrato>")
    assert not _confere("simplicio-video social plan --video a.mp4 --target tiktok=@conta --ai-generated")


@pytest.mark.parametrize("nome", NOMES)
def test_toda_flag_da_skill_existe_em_algum_parser_do_cli(nome):
    """Flags written without their command (`--gpu-encode`, `--aceito-restricao`, `--permitir-dado-pessoal`...) must exist somewhere."""
    conhecidas = set()

    def anda(parser):
        conhecidas.update(_flags(parser))
        for filho in _sub(parser).values():
            anda(filho)

    anda(build_parser())
    for fabrica in DELEGADOS.values():
        anda(fabrica())
    texto = _texto(nome)
    # `--gpu-encode` is a flag of the remote render script, `--with` of scripts/dev_install.sh and `--upgrade` of pip: not parsers of the CLI
    de_scripts = {"--gpu-encode", "--with", "--upgrade", "--publish"}  # `--publish`: the text says that it does NOT exist (#75)
    faltam = {f for f in re.findall(r"(?<![\w-])--[a-z][a-z0-9-]*", texto)} - conhecidas - de_scripts
    assert not faltam, f"{nome} cites flags that no parser has: {sorted(faltam)}"


@pytest.mark.parametrize("nome", NOMES)
def test_nenhuma_frase_descreve_o_install_do_venv_nem_o_update_que_puxa(nome):
    texto = " ".join(_texto(nome).split())
    for velho in (r"install`? cria o `?\.venv", r"cria o `\.venv` do checkout", r"git stash", r"árvore suja", r"arvore suja",
                  r"git pull --ff-only", r"git reset", r"update`? (faz|roda) (o )?`?git", r"install --python", r"install --with",
                  r"simplicio-install\.json"):
        assert not re.search(velho, texto), f"{nome} still describes the old behavior: /{velho}/"


def test_a_skill_diz_o_que_o_install_e_o_update_fazem_agora():
    texto = " ".join(_texto("simplicio-video").split())
    for trecho in ("simplicio-video install", "install --global", "--dry-run", "--check", "--verify", "--uninstall", ".claude/skills",
                   "scripts/dev_install.sh", "dev_install.ps1", "git pull", "recusa", "update --check",
                   "pip install --upgrade", "install --global"):
        assert trecho in texto, f"the skill does not mention {trecho!r}"
    assert re.search(r"dev_install\.(sh|ps1)[^.]{0,200}\.venv|\.venv[^.]{0,200}dev_install\.(sh|ps1)", texto), \
        "the skill must say that the `.venv` comes from scripts/dev_install, not from `install`"
    assert re.search(r"update[^.]{0,120}recusa[^.]{0,200}git pull", texto), "the update of a checkout refuses and says `git pull`"
    assert "-NoProfile -ExecutionPolicy Bypass -File scripts\\dev_install.ps1" in texto, "the PowerShell command that works on Windows"


# --- what a public package must not say ---------------------------------------------------------------------------------------------


PROIBIDO = [r"Wesley", r"wesley", r"wesleysimplicio", r"Lothus", r"lothus", r"\bWJR\b", r"\bwjr\b",
            r"[\w.+-]+@[\w-]+\.[\w.-]+", r"/home/\w+", r"/Users/\w+", r"C:\\Users"]


@pytest.mark.parametrize("nome", NOMES)
def test_a_skill_publica_nao_cita_dono_cliente_nem_email(nome):
    texto = _texto(nome)
    for padrao in PROIBIDO:
        achado = re.search(padrao, texto)
        assert not achado, f"{nome} names someone or somewhere private: {achado.group(0)!r}"


@pytest.mark.parametrize("nome", NOMES)
def test_o_espelho_de_skills_e_a_copia_do_pacote_sao_iguais_byte_a_byte(nome):
    assert (ESPELHO / nome / "SKILL.md").read_bytes() == (PACOTE / nome / "SKILL.md").read_bytes()


# --- what an agent of a `pip install` user can follow (review follow-up: the package copy is immutable on PyPI) -----------------------
#
# The two skills travel in the wheel. A path like `ugc/README.md`, `docs/custos.md` or `clients/<slug>/coleta/` is a file of the CHECKOUT:
# the user of `pip install simplicio-video` does not have it (the `ugc` module is gone since #115). Everything the user will not have is an
# absolute URL to a file that EXISTS in origin/main, or neutral text. A path may stay only when it is (a) inside the package, (b) a file the CLI
# writes in the user's own folder (`out/`, `assets/`), or (c) a script the CLI itself tells a CHECKOUT to run (`scripts/dev_install.sh`).

import subprocess  # noqa: E402

URL_BASE = "https://github.com/simpletibr/simplicio-videos/blob/main/"
SAIDAS_DO_CLI = ("out/", "assets/")                                         # written by the CLI next to the user's contract
SCRIPTS_DO_CHECKOUT = ("scripts/dev_install.sh", "scripts/dev_install.ps1", "./install.sh")  # what `update` tells a checkout to run
NOMES_PERMITIDOS = {"template.json", "contract.yaml", "brief.md", "pendencias.md", "intake.json", "fontes.md", "referencias.md",
                    "timing.lock.json", "render.manifest.json", "social.plan.json", "legenda.txt", "index.json", "mix.wav",
                    "CREDITS-openverse.md", "<video>.CREDITS-openverse.md", "busca.registro.jsonl", "render_bundle.sh", "pattern.json",
                    "dev_install.ps1", "dev_install.sh", "install.sh", "vNN.mp4"}  # the last four: parts of a command and a naming convention
PROIBIDAS = re.compile(r"\b(ugc|prospect|prospects|venda|vendas)\b", re.IGNORECASE)
CAMINHO = re.compile(r"(?<![\w<>.\-])(?:\.{1,2}/)?[\w<>{}.\-~]+(?:/[\w<>{}.\-~]+)+/?")
ARQUIVO = re.compile(r"(?<![\w<>/.\-])[\w<>.\-]+\.(?:md|json|jsonl|yaml|yml|py|sh|ps1|mp4|wav|txt|ipynb|jpg|png|srt)\b")


def _sem_links(texto: str):
    """(texto sem os links do Markdown e sem URLs, urls)."""
    urls = re.findall(r"https?://[^\s)\]>`]+", texto)
    semurl = re.sub(r"\[[^\]]*\]\(https?://[^)]+\)", " ", texto)
    return re.sub(r"https?://[^\s)\]>`]+", " ", semurl), urls


def _trechos_de_codigo(texto: str) -> list:
    """The inline code spans and the lines of the fenced blocks: where a path or a command is written to be followed."""
    trechos, dentro = [], False
    for linha in texto.splitlines():
        if linha.strip().startswith("```"):
            dentro = not dentro
        elif dentro:
            trechos.append(re.sub(r"\s+#.*$", "", linha))  # the prose of a comment is not a path
    return trechos + re.findall(r"`([^`\n]+)`", texto)


def _existe_na_main(caminho: str):
    """True/False when origin/main is there to ask, None when it is not (a source tarball)."""
    try:
        existe = subprocess.run(["git", "cat-file", "-e", f"origin/main:{caminho}"], cwd=ROOT, capture_output=True)
        pronto = subprocess.run(["git", "rev-parse", "--verify", "--quiet", "origin/main"], cwd=ROOT, capture_output=True)
    except OSError:
        return None
    return None if pronto.returncode != 0 else existe.returncode == 0


def _no_pacote(token: str) -> bool:
    """`motion/patterns/<id>/pattern.json` -> a glob under simplicio_video/data/."""
    modelo = re.sub(r"<[^>]*>|\{[^}]*\}", "*", token).strip("/")
    return bool(list(PACOTE.parent.glob(modelo)))


def _problemas_de_caminho(texto: str) -> list:
    sem_url, urls = _sem_links(texto)
    ruins = []
    for url in urls:
        if url.startswith(URL_BASE):
            alvo = url[len(URL_BASE):].split("#")[0]
            achou = _existe_na_main(alvo)
            if achou is False:
                ruins.append(f"{url}: that file is not in origin/main")
    for trecho in _trechos_de_codigo(sem_url):
        trecho = re.sub(r"--[a-z][a-z0-9-]*", " ", trecho)
        for token in {*CAMINHO.findall(trecho), *ARQUIVO.findall(trecho)}:
            limpo = token.rstrip("/.,;:)")
            if ("<" in limpo) != (">" in limpo) or limpo.startswith("../"):
                continue  # a piece of a placeholder (`<nome que o export criou>.jpg`), or a folder next to the user's own contract
            if re.fullmatch(r"simplicio\.[a-z-]+/v\d+|[A-Z][a-z]+/[A-Z][A-Za-z_]+|\d+/\d+|[\w<>.\-]+\|[\w<>.\-|]+", limpo):
                continue  # a schema id, a time zone, an aspect ratio, an alternative list
            if limpo.replace("\\", "/") in SCRIPTS_DO_CHECKOUT or limpo.startswith(SAIDAS_DO_CLI) or limpo in NOMES_PERMITIDOS:
                continue
            if limpo.startswith(".claude/skills"):
                continue  # where `install` puts the skills in the user's own project
            if "/" in limpo and _no_pacote(limpo):
                continue
            ruins.append(f"`{limpo}` is not in the package, not an output of the CLI and not an absolute URL")
    return sorted(set(ruins))


@pytest.mark.parametrize("nome", NOMES)
def test_nenhum_caminho_citado_depende_do_checkout(nome):
    ruins = _problemas_de_caminho(_texto(nome))
    assert not ruins, f"{nome} cites files that a `pip install` user does not have:\n  " + "\n  ".join(ruins)


def test_o_varredor_de_caminhos_pega_o_que_o_usuario_do_pip_nao_tem():
    assert _problemas_de_caminho("Veja `ugc/README.md` e `docs/custos.md` e `clients/<slug>/coleta/` e `AGENTS.md` e `tools/video-use/`.")
    assert _problemas_de_caminho(f"[x]({URL_BASE}docs/nao-existe-mesmo.md)") or _existe_na_main("README.md") is None
    assert not _problemas_de_caminho("`out/final.mp4`, `assets/openverse/`, `schema/contract.schema.json`, `bash scripts/dev_install.sh`, `timing.lock.json`")
    assert not _problemas_de_caminho(f"Veja [o custo]({URL_BASE}docs/custos.md).") or _existe_na_main("docs/custos.md") is None


@pytest.mark.parametrize("nome", NOMES)
def test_as_skills_do_pacote_nao_citam_o_que_saiu_do_cli(nome):
    texto = _texto(nome)
    achado = PROIBIDAS.search(texto)
    assert not achado, f"{nome} still mentions {achado.group(0)!r}: those commands and the ugc module are gone"


@pytest.mark.parametrize("nome", NOMES)
def test_todo_link_para_o_repositorio_e_absoluto_e_aponta_para_um_arquivo_que_existe_na_main(nome):
    _, urls = _sem_links(_texto(nome))
    repo = [u for u in urls if "simpletibr/simplicio-videos" in u]
    for url in repo:
        assert url.startswith(URL_BASE), f"{nome}: {url} must be https://github.com/simpletibr/simplicio-videos/blob/main/<file>"
        achou = _existe_na_main(url[len(URL_BASE):].split("#")[0])
        if achou is not None:
            assert achou, f"{nome}: {url} does not exist in origin/main"


@pytest.mark.parametrize("nome", NOMES)
def test_toda_tool_mcp_citada_existe_no_servidor(nome):
    from simplicio_video import mcp_server

    existentes = {t[0] for t in mcp_server.TOOLS}
    citadas = set(re.findall(r"\bvideo\.[a-z]+\b", _texto(nome)))
    assert citadas <= existentes | {"video.*"}, f"{nome} cites MCP tools that do not exist: {sorted(citadas - existentes)}"


@pytest.mark.parametrize("nome", NOMES)
def test_todo_comando_do_motor_citado_em_codigo_existe_mesmo_sem_flag(nome):
    """`simplicio-video <word>` in a code span or line: the word is a command of the root parser (flags are checked in the other test)."""
    raiz = set(_sub(build_parser()))
    for comando in _comandos(_texto(nome)):
        palavras = comando.split()
        if len(palavras) > 1 and re.fullmatch(r"[a-z][a-z-]*", palavras[1]):
            assert palavras[1] in raiz, f"{nome}: `{comando}`: `{palavras[1]}` is not a command ({sorted(raiz)})"
