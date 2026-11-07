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

from helpers import ROOT
from simplicio_video import busca, openverse, social
from simplicio_video.cli import build_parser

PACOTE = ROOT / "src" / "simplicio_video" / "data" / "skills"
ESPELHO = ROOT / "skills"
NOMES = ("simplicio-video", "simplicio-video-social", "simplicio-video-trilhas", "deep-news", "deep-service", "deep-product")
DELEGADOS = {"social": social._parser, "openverse": openverse._parser, "busca": busca._parser}  # `args: REMAINDER` in cli.py
# Os outros grupos que repassam os argumentos a outro programa (`args: REMAINDER` em cli.py): o parser não conhece o verbo nem as
# flags, então a conferência é esta. Cada verbo citado tem de estar na lista do grupo, e a lista tem de aparecer como texto no módulo
# que a implementa (o teste lê o código; nenhum destes programas roda aqui). As listas vêm do --help de cada comando e do código.
PASSAGEM = {
    "media": ("media.py", ("fetch", "probe", "audio", "sheet", "subs", "burn", "mask", "replace-audio", "voice-track")),
    "edit": ("edit.py", ("setup", "transcribe", "transcribe-batch", "pack", "render", "verify", "grade")),
    "shorts": ("shorts.py", ("inspect", "plan", "cut", "run")),
    "voicestudio": ("voicestudio.py", ("status", "voices", "languages", "personalities", "tts", "transcribe", "clone", "describe",
                                       "design", "dub", "dub-export", "mcp")),
    "montage": ("montage.py", ("clone", "open", "serve", "demo", "setup", "status", "doctor", "hyperframes-doctor", "preflight",
                               "pipelines", "tools", "envelope", "estimate", "run-tool")),
    "moneyprinter": ("moneyprinter.py", ("clone", "setup", "serve", "where", "generate", "run", "status")),
    "matchcut": ("matchcut.py", ("clone", "where", "status", "setup", "run")),
    "instagram": ("instagram.py", ("clone", "where", "status", "skills", "skill", "run")),
    "rea-video": ("rea_video.py", ("clone", "setup", "where", "status", "summary", "probe", "tiles", "stems", "review",
                                   "apply-review", "remake-plan", "remake-run", "assemble", "capsule-draft", "decompose")),
    "video-to-skill": ("video_to_skill.py", ("clone", "setup", "where", "status", "check", "skill", "extract", "frame-at", "clip",
                                              "compile", "merge", "install")),
    "toonflow": ("toonflow.py", ("clone", "serve", "status", "mcp", "where")),
    "opencut": ("opencut.py", ("clone", "dev", "status", "where")),
    "clone": ("mcp_server.py", ("media", "help", "version", "doctor", "check", "plan", "pricing", "status", "builds", "history", "activity",
                                "inspect", "logs", "paths", "vocabulary", "build", "get")),  # o Hypit: a lista que o MCP aceita
    "jobs": ("jobs.py", ("submit", "status", "list", "cancel", "result", "clean")),
    "swap": ("swap.py", ("providers", "estimate", "run", "status")),
    "formats": ("formats.py", ("list", "show", "prompt")),
}


# As flags de cada verbo que a skill cita: o que o --help e o código do módulo aceitam ao verbo (a flag de um verbo não serve a outro:
# `--autorizo` existe em media.py para `fetch`, e `media probe --autorizo` tem de falhar). Só o que vem antes do `--` conta: depois dele
# são argumentos do programa de terceiros (o upstream), que aqui não são conferidos. Verbos fora desta tabela seguem a conferência por módulo.
# `rea-video remake-run` e `assemble` ficam de fora: são do upstream, e as opções deles não estão no código do motor.
FLAGS_POR_VERBO = {
    ("media", "fetch"): {"-o", "--info", "--autorizo", "--max-mb", "--timeout", "--subs", "--auto-subs", "--section", "--audio-only"},
    ("media", "probe"): {"-o"},
    ("media", "audio"): {"-o", "--rate"},
    ("media", "sheet"): {"-o", "--every", "--cols"},
    ("media", "subs"): {"-o", "--style", "--wrap"},
    ("media", "burn"): {"-o", "--crf", "--preset"},
    ("media", "mask"): {"-o", "--box", "--from", "--to"},
    ("media", "replace-audio"): {"-o", "--keep-length"},
    ("media", "voice-track"): {"-o", "--duration", "--max-stretch"},
    ("edit", "setup"): set(),
    ("edit", "transcribe"): {"-o", "--out", "--output", "--model", "--lang", "--fixes", "--script"},
    ("edit", "grade"): {"-o", "--output", "--preset", "--filter", "--analyze", "--list-presets", "--print-preset"},
    ("shorts", "inspect"): set(),
    ("shorts", "plan"): {"-o", "--out", "--transcript", "--clips", "--min", "--max"},
    ("shorts", "cut"): {"-o", "--out", "--subs", "--fit", "--crf", "--preset", "--fps", "--dry-run"},
    ("shorts", "run"): {"-o", "--out", "--transcript", "--clips", "--min", "--max", "--subs", "--fit", "--crf", "--preset", "--fps",
                        "--dry-run"},
    ("voicestudio", "status"): {"--json"},
    ("voicestudio", "voices"): {"--json"},
    ("voicestudio", "languages"): {"--json"},
    ("voicestudio", "tts"): {"-o", "--out", "--profile", "--language", "--format", "--json"},
    ("voicestudio", "transcribe"): {"--language", "--rest", "--json"},
    ("voicestudio", "clone"): {"--name", "--language", "--ref-text", "--json"},
    ("voicestudio", "design"): {"--name", "--language", "--json"},
    ("voicestudio", "dub"): {"--source-lang", "--audio", "--job-id", "--json"},
    ("voicestudio", "dub-export"): {"--job", "--lang", "--bed-level", "-o", "--out", "--json"},
    ("montage", "status"): {"--json"},
    ("montage", "pipelines"): {"--json"},
    ("montage", "tools"): {"--json", "--runtime"},
    ("montage", "estimate"): {"--json", "--input"},
    ("montage", "run-tool"): {"--input", "--yes", "--json", "--timeout"},
    ("moneyprinter", "generate"): {"--script", "--material", "--out", "--voice", "--aspect", "--subject", "--api-port", "--json"},
    ("moneyprinter", "run"): {"--yes", "--out"},
    ("moneyprinter", "serve"): {"--webui", "--api", "--lan", "--host", "--api-port"},
    ("instagram", "run"): {"--forcar", "--bruto"},
    ("instagram", "where"): {"--skills", "--json"},
    ("matchcut", "run"): {"--forcar", "--bruto"},
    ("rea-video", "decompose"): {"-o", "--out", "--vlm", "--no-vlm", "--no-whole", "--no-ocr", "--ocr-lang", "--no-packaging",
                                 "--no-stems", "--workers", "--engine", "--meta"},
    ("rea-video", "review"): {"--force"},
    ("rea-video", "apply-review"): {"--by"},
    ("rea-video", "probe"): {"--tags"},
    ("rea-video", "tiles"): {"-o", "--out", "--start", "--end", "--every", "--cols", "--cell", "--max"},
    ("rea-video", "stems"): {"-o", "--out"},
    ("rea-video", "remake-plan"): {"--capsule-root", "--engine", "--mode", "--labels"},
    ("rea-video", "summary"): set(),
    ("video-to-skill", "where"): {"--binary", "--json"},
    ("video-to-skill", "status"): {"--json"},
    ("video-to-skill", "check"): {"--print-downloads"},
    ("video-to-skill", "extract"): {"--out", "--autorizo"},
    ("video-to-skill", "frame-at"): {"--bundle"},
    ("video-to-skill", "clip"): {"--bundle", "--fps"},
    ("video-to-skill", "compile"): {"--bundle", "--ir", "--out"},
    ("video-to-skill", "merge"): {"--skill", "--ir", "--bundle", "--out", "--dry-run"},
    ("video-to-skill", "install"): {"--package", "--scope", "--only", "--force", "--yes"},
    ("toonflow", "serve"): {"--lan", "--docker"},
    ("toonflow", "mcp"): {"--port", "--json"},
    ("toonflow", "status"): {"--json"},
    ("opencut", "dev"): {"--lan"},
    ("opencut", "status"): {"--json"},
}


def _fonte(arquivo: str) -> str:
    return (ROOT / "src" / "simplicio_video" / arquivo).read_text(encoding="utf-8")


def _literal(fonte: str, token: str) -> bool:
    """The verb is written in the module: in its code, its help or its `a|b|c` lists (a word, not a part of a longer one)."""
    return re.search(rf"(?<![\w-]){re.escape(token)}(?![\w-])", fonte) is not None


def _flag_no_texto(fonte: str, flag: str) -> bool:
    return re.search(rf"(?<![\w-]){re.escape(flag)}(?![\w-])", fonte) is not None


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
    if palavras and palavras[0] in PASSAGEM:
        arquivo, verbos = PASSAGEM[palavras[0]]
        fonte = _fonte(arquivo)
        if len(palavras) > 1 and re.fullmatch(r"[a-z][a-z-]*", palavras[1]) and palavras[1] not in verbos:
            problemas.append(f"`{palavras[1]}` is not a verb of `simplicio-video {palavras[0]}` ({', '.join(verbos)})")
        grupo, verbo = palavras[0], (palavras[1] if len(palavras) > 1 else "")
        if (grupo, verbo) in FLAGS_POR_VERBO:  # the option belongs to THIS verb, not to any verb of the module
            antes = palavras[: palavras.index("--")] if "--" in palavras else palavras
            permitidas = FLAGS_POR_VERBO[(grupo, verbo)] | {"-h", "--help"}
            for token in antes[2:]:
                opcao = token.split("=")[0]
                if opcao.startswith("-") and opcao not in permitidas:
                    problemas.append(f"{opcao} is not an option of `simplicio-video {grupo} {verbo}`")
        for flag in set(re.findall(r"(?<![\w-])--[a-z][a-z0-9-]*", comando)):
            if not _flag_no_texto(fonte, flag):
                problemas.append(f"{flag} is not an option of `simplicio-video {palavras[0]}` ({arquivo})")
        return problemas
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


def test_o_varredor_de_passagem_acha_verbo_e_flag_que_nao_existem():
    assert _confere("simplicio-video media fetchh URL -o out/a.mp4 --autorizo")
    assert _confere("simplicio-video media fetch URL -o out/a.mp4 --nao-existe")
    assert _confere("simplicio-video montage run-tool audio_probe --input '{}' --nao-existe")
    assert not _confere("simplicio-video media fetch URL -o out/a.mp4 --autorizo")
    assert not _confere("simplicio-video montage run-tool audio_probe --input '{}' --yes")
    assert not _confere("simplicio-video instagram run caption -- legenda.txt --json")


def test_todo_comando_de_passagem_do_cli_esta_na_conferencia():
    """Every command of cli.py that takes `args: REMAINDER` is checked here, by its verb list (or its own parser, `DELEGADOS`)."""
    passagem = [nome for nome, sub in _sub(build_parser()).items() if any(a.dest == "args" and a.nargs == argparse.REMAINDER for a in sub._actions)]
    assert len(passagem) >= 15, "the scan is broken: too few passthrough commands"
    sem_conferencia = sorted(set(passagem) - set(PASSAGEM) - set(DELEGADOS))
    assert not sem_conferencia, f"passthrough commands with no check in this test: {sem_conferencia}"


@pytest.mark.parametrize("grupo", sorted(PASSAGEM))
def test_os_verbos_de_passagem_estao_no_codigo_do_modulo(grupo):
    arquivo, verbos = PASSAGEM[grupo]
    fonte = _fonte(arquivo)
    ausentes = [verbo for verbo in verbos if not _literal(fonte, verbo)]
    assert not ausentes, f"`{grupo}` lists verbs that {arquivo} does not have: {ausentes}"


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
    for arquivo, _ in PASSAGEM.values():  # the options of a passthrough command live in its module (see `_confere`)
        conhecidas.update(re.findall(r"(?<![\w-])--[a-z][a-z0-9-]*", _fonte(arquivo)))
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
    """A path INSIDE the package is written with its package root (`simplicio_video/data/schema/contract.schema.json`), so that the reader
    knows where it is. `schema/contract.schema.json` alone exists nowhere: not in the repo, not in the user's folder."""
    modelo = re.sub(r"<[^>]*>|\{[^}]*\}", "*", token).strip("/")
    return modelo.startswith("simplicio_video/") and bool(list((ROOT / "src").glob(modelo)))


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
            if re.match(r"<[^>]+>/", limpo):
                continue  # the user's own absolute folder, as a placeholder: `<pasta-absoluta>/assets/clip.mp4` (the MCP wants absolute paths)
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
    assert not _problemas_de_caminho("`out/final.mp4`, `assets/openverse/`, `simplicio_video/data/schema/contract.schema.json`, `bash scripts/dev_install.sh`, `timing.lock.json`")
    assert not _problemas_de_caminho("`--input '{\"input_path\": \"<pasta-absoluta>/assets/video.mp4\"}'` e `<pasta-absoluta>/out/curto`")
    assert _problemas_de_caminho("`/home/user/clip.mp4` e `src/simplicio_video/mcp_server.py`")
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
    citadas = set(re.findall(r"\bvideo\.[a-z][a-z-]*[a-z]\b", _texto(nome)))  # `video.rea-video` has a hyphen
    assert citadas <= existentes | {"video.*"}, f"{nome} cites MCP tools that do not exist: {sorted(citadas - existentes)}"


@pytest.mark.parametrize("nome", NOMES)
def test_todo_comando_do_motor_citado_em_codigo_existe_mesmo_sem_flag(nome):
    """`simplicio-video <word>` in a code span or line: the word is a command of the root parser (flags are checked in the other test)."""
    raiz = set(_sub(build_parser()))
    for comando in _comandos(_texto(nome)):
        palavras = comando.split()
        if len(palavras) > 1 and re.fullmatch(r"[a-z][a-z-]*", palavras[1]):
            assert palavras[1] in raiz, f"{nome}: `{comando}`: `{palavras[1]}` is not a command ({sorted(raiz)})"


def test_o_varredor_nao_aceita_caminho_do_pacote_sem_dizer_onde_ele_esta():
    assert _problemas_de_caminho("O schema é `schema/contract.schema.json`.")
    assert _problemas_de_caminho("O padrão é `motion/patterns/<id>/pattern.json`.")
    assert not _problemas_de_caminho("O schema vai no pacote: `simplicio_video/data/schema/contract.schema.json`.")
    assert _problemas_de_caminho("`simplicio_video/data/schema/nao-existe.json`")


def test_a_skill_nao_cita_o_schema_do_contrato_por_um_caminho_que_nao_existe():
    texto = _texto("simplicio-video")
    assert not re.search(r"(?<!data/)schema/contract\.schema\.json", texto), "`schema/contract.schema.json` exists nowhere"
    assert "simplicio_video/data/schema/contract.schema.json" in texto and "validate" in texto


def test_o_update_do_pip_na_skill_diz_que_o_install_global_mexe_nas_11_pastas_de_hosts():
    """The `update` of a pip package runs `install --global`, which creates up to 11 folders under the home: the text must say so."""
    texto = " ".join(_texto("simplicio-video").split())
    assert re.search(r"update[^.]{0,200}install --global[^.]{0,200}11 pastas", texto), "the update paragraph must name the 11 folders"
    assert re.search(r"install --global[^.]{0,200}11 pastas[^.]{0,200}cria as que faltam", texto) or "cria as que faltam" in texto
    assert not re.search(r"install --global`? \(o home\): copia a skill para `\.claude/skills`", texto), "it writes in 11 folders, not one"


CTA_ITEM = "termina com um CTA"


def _secao(texto: str, titulo: str) -> str:
    inicio = texto.index(titulo)
    fim = texto.find("\n## ", inicio + len(titulo))
    return texto[inicio:] if fim == -1 else texto[inicio:fim]


def test_todo_video_tem_cta_no_final_nas_quatro_skills():
    # regra do Wesley (via XViral): todo vídeo tem um CTA no final pedindo uma ação; sem CTA, o vídeo não sai
    for nome in ("deep-news", "deep-service", "deep-product", "simplicio-video"):
        texto = _texto(nome)
        checklist = _secao(texto, "## Checklist")
        assert CTA_ITEM in checklist, f"{nome}: o checklist precisa do item de CTA"
        assert "sem CTA, o vídeo não sai" in checklist, nome
        # três tipos de CTA: pedido de ação, chamada final da empresa do cliente, ou o slogan dela
        assert "pedido de ação" in checklist, nome
        assert "chamada final" in checklist and "slogan" in checklist, nome
        for acao in ("comente", "clique", "siga", "salve"):
            assert acao in checklist, (nome, acao)


# --- review of PR #181: a flag vale para o verbo que a aceita, e a tabela cita verbos que existem ----------------------------------------


def _problemas_de_celula(texto: str) -> list:
    """What is wrong with the commands that the table cells of `texto` cite without the `simplicio-video` prefix (`media fetch URL`):
    the same checks of `_confere`, on the group and the verb that the cell names."""
    problemas = []
    for linha in texto.splitlines():
        if not linha.startswith("|"):
            continue
        for trecho in re.findall(r"`([^`\n]+)`", linha):
            palavras = trecho.split()
            if palavras and (palavras[0] in PASSAGEM or palavras[0] in DELEGADOS):
                problemas += [f"`{trecho}`: {problema}" for problema in _confere("simplicio-video " + trecho)]
    return problemas


def test_a_flag_de_um_verbo_nao_serve_a_outro_verbo():
    """`--autorizo` exists in media.py (for `fetch`): `media probe --autorizo` passes the module check and must fail per verb."""
    assert _confere("simplicio-video media probe reel.mp4 --autorizo")
    assert _confere("simplicio-video voicestudio tts \"oi\" -o out/a.wav --name Voz")
    assert not _confere("simplicio-video media fetch URL -o out/a.mp4 --autorizo")
    assert not _confere("simplicio-video media mask out/a.mp4 --box 1,2,3,4 --from 0 --to 2 -o out/b.mp4")


def test_a_tabela_pega_grupo_e_verbo_que_nao_existem_mesmo_sem_o_prefixo():
    """A table cell cites `media fetch` without the `simplicio-video` prefix: its verb must exist too."""
    assert _problemas_de_celula("| Pedido | `media fetchh URL -o out/a.mp4 --autorizo` |")
    assert not _problemas_de_celula("| Pedido | `media fetch URL -o out/a.mp4 --autorizo` |")


@pytest.mark.parametrize("nome", NOMES)
def test_as_celulas_de_tabela_das_skills_citam_so_verbos_que_existem(nome):
    ruins = _problemas_de_celula(_texto(nome))
    assert not ruins, f"{nome}: cells that cite a command the CLI does not have:\n  " + "\n  ".join(ruins)


@pytest.mark.parametrize("grupo, verbo", sorted(FLAGS_POR_VERBO))
def test_as_flags_por_verbo_sao_de_verbos_listados_e_existem_no_codigo(grupo, verbo):
    arquivo, verbos = PASSAGEM[grupo]
    assert verbo in verbos, f"`{grupo} {verbo}` has options but is not a verb of the group"
    fonte = _fonte(arquivo)
    ausentes = [opcao for opcao in FLAGS_POR_VERBO[(grupo, verbo)] if not _flag_no_texto(fonte, opcao)]
    assert not ausentes, f"`{grupo} {verbo}` lists options that {arquivo} does not have: {ausentes}"
