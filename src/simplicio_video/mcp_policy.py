"""The argument policy of the MCP tools in one table: what each tool runs over MCP, what only the terminal does, and the words that say so.

`POLITICA[tool][word]` is a `Verbo`. `mcp` says that the MCP runs the word; `terminal_motivo` is why a word, or the part of it that
takes a folder or another operand (`montage clone <dir>`, `edit grade --filter`), is terminal-only. `forma` is the command to type in the
terminal (what follows `simplicio-video`): with it the refusal is the standard sentence "<reason>: rode `simplicio-video <forma>` no
terminal; o MCP não faz isso"; without it `terminal_motivo` is already the whole text. `{tool}` and `{nome}` in the texts are the tool
and the word, and `so_terminal` fills in any other `{valor}` its caller passes (`{resto}` for the words of a refused `--watch`). The row
`"*"` of a tool says the same of every other word.

The `cmd` list of each tool (`mcp_server._CMD_*`, the `Literal` of its schema and the line of its description) is `verbos_mcp(tool)`: a
verb the table does not list is not in the list, so a new upstream subcommand is terminal-only until someone adds it here. A word that
is in neither the table nor the list is refused by the track itself, with its own text (rea-video, video-to-skill).

The rest is the gate that every path and every output option goes through (`caminho_seguro`, `saida_absoluta_nova`), the closed allow-list
of the Hypit tool, and the policy of `edit` (what it asks of an output, the colour filters `grade` takes). The wrappers in mcp_server.py
call these and return what they say.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, replace
from pathlib import Path

from .edit import GRADE_READ_ONLY, filter_values, output_values


@dataclass(frozen=True)
class Verbo:
    nome: str
    mcp: bool
    terminal_motivo: str | None = None
    forma: str | None = None


def _mcp(*nomes: str) -> dict[str, Verbo]:
    return {n: Verbo(n, True) for n in nomes}


HYPIT_LIVRE = ("help", "version", "doctor", "check", "plan", "pricing", "status", "builds", "history", "activity", "inspect", "logs",
               "paths", "vocabulary")
HYPIT_MEDIA = ("probe", "frames", "tile", "tiles", "boundaries", "cut")

_CLONE_NA_PASTA_PADRAO = "{tool} clone com pasta só pelo terminal; pelo MCP o checkout vai para a pasta padrão"
_MONEYPRINTER_RESTO = ("moneyprinter pelo MCP aceita `where`, `clone` (na pasta padrão), `status` (leitura), e `generate` e `run` "
                       "(roteiro seu, material local, voz Edge, --out absoluto: viram uma tarefa em segundo plano); "
                       "setup, serve, roteiro por LLM, fonte paga e lote são pelo terminal: `simplicio-video moneyprinter setup|serve|run --yes`")
_MONTAGE_ABRIR = "montage open e serve sobem uma interface que não termina"

POLITICA: dict[str, dict[str, Verbo]] = {
    "clone": {
        **_mcp(*HYPIT_LIVRE, "get", "media"),
        "build": Verbo("build", False, "build pode gastar em provedores e fica só no terminal na v1", "clone {nome}"),
        "studio": Verbo("studio", False, "studio sobe uma interface que nunca termina", "clone {nome}"),
        "auth": Verbo("auth", False, "auth lê um segredo da entrada padrão", "clone {nome}"),
        "runtime": Verbo("runtime", False, "runtime up/down mexe em processos do runtime", "clone {nome}"),
        "packages": Verbo("packages", False, "packages instala código de terceiros", "clone {nome}"),
        "capture": Verbo("capture", False, "capture baixa um navegador e abre páginas", "clone {nome}"),
        "transcribe": Verbo("transcribe", False, "transcribe usa provedores e fica só no terminal", "clone {nome}"),
        "measure": Verbo("measure", False, "measure usa provedores e fica só no terminal", "clone {nome}"),
        "media fetch": Verbo("media fetch", False, "media fetch baixa sem o portão --autorizo", "media fetch --autorizo"),
        "media prepare-fetch": Verbo("media prepare-fetch", False, "media prepare-fetch baixa sem o portão --autorizo", "media fetch --autorizo"),
        "--watch": Verbo("--watch", False, "--watch não termina até o build acabar e o MCP não tem tempo limite", "clone {resto}"),
        "*": Verbo("*", False, "`{nome}` não está na lista do MCP (comando desconhecido ou não permitido, ou um caminho que não é absoluto)",
                   "clone {nome}"),
    },
    "montage": {
        "clone": Verbo("clone", True, "clonar o OpenMontage num diretório escolhido", "montage clone <dir>"),
        **_mcp("doctor", "hyperframes-doctor", "preflight", "help", "pipelines", "tools", "envelope", "estimate", "status"),
        "run-tool": Verbo("run-tool", True, "pelo MCP, run-tool recebe só o nome da tool e `input` como objeto",
                          "montage run-tool NOME --input JSON --yes"),
        "setup": Verbo("setup", False, "montage setup cria o venv e instala dependências com pip e npm", "montage setup"),
        "open": Verbo("open", False, _MONTAGE_ABRIR, "montage open|serve"),
        "serve": Verbo("serve", False, _MONTAGE_ABRIR, "montage open|serve"),
        "*": Verbo("*", False, "montage {nome} roda outra coisa do OpenMontage que o MCP não aceita", "montage {nome}"),
    },
    "opencut": {
        "clone": Verbo("clone", True, "clonar o OpenCut num diretório escolhido", "opencut clone <dir>"),
        **_mcp("status", "where"),
        "dev": Verbo("dev", False, "opencut dev sobe um servidor que não termina", "opencut dev"),
    },
    "edit": {
        **_mcp("setup", "transcribe", "pack", "render", "verify"),
        "grade": Verbo("grade", True, "pelo MCP o --filter só aceita filtros de cor (eq, curves, colorbalance, hue, lut, lutrgb, lutyuv, "
                                      "colorchannelmixer, vibrance), sem opção que leia ou grave arquivo, sem barra invertida nem aspas; "
                                      "uma cadeia livre", "edit grade --filter"),
        "transcribe-batch": Verbo("transcribe-batch", False, "transcrever em lote usa o ElevenLabs Scribe, um terceiro pago, e só roda com "
                                                             "você no terminal", "edit transcribe-batch"),
    },
    "toonflow": {
        "clone": Verbo("clone", True, _CLONE_NA_PASTA_PADRAO),
        **_mcp("mcp", "status", "where"),
        "serve": Verbo("serve", False, "{tool} serve sobe um servidor local que não termina; rode `simplicio-video toonflow serve --lan` "
                                       "(ou `serve --docker`, só em 127.0.0.1) no terminal"),
        "*": Verbo("*", False, "toonflow pelo MCP aceita `status [--json]`, `mcp [--port N] [--json]`, `where` e `clone` (pasta padrão); "
                               "o resto é pelo terminal"),
    },
    "moneyprinter": {
        "where": Verbo("where", True),
        "clone": Verbo("clone", True, _CLONE_NA_PASTA_PADRAO),
        **_mcp("status", "generate", "run"),
        "setup": Verbo("setup", False, _MONEYPRINTER_RESTO),
        "serve": Verbo("serve", False, _MONEYPRINTER_RESTO),
        "*": Verbo("*", False, _MONEYPRINTER_RESTO),
    },
    "matchcut": {
        **_mcp("where", "status", "run"),
        "setup": Verbo("setup", False, "{tool} {nome} só pelo terminal: `simplicio-video {tool} {nome}` (o MCP não baixa código nem instala pacotes)"),
        "clone": Verbo("clone", False, "{tool} {nome} só pelo terminal: `simplicio-video {tool} {nome}` (o MCP não baixa código nem instala pacotes)"),
        "*": Verbo("*", False, "matchcut pelo MCP aceita `where`, `status` e `run SCRIPT ...`; setup e clone são só do terminal"),
    },
    "instagram": {
        "clone": Verbo("clone", False, "baixar o instagram-agent-skill é código de terceiros vindo da rede", "instagram clone"),
    },
    "voicestudio": _mcp("status", "voices", "languages", "personalities", "tts", "transcribe", "clone", "describe", "design", "dub", "dub-export", "mcp"),
    "rea-video": {
        "clone": Verbo("clone", True, _CLONE_NA_PASTA_PADRAO),
        **_mcp("where", "status", "summary", "probe", "tiles", "stems", "review", "apply-review", "remake-plan", "decompose"),
    },
    "video-to-skill": _mcp("status", "where", "check", "skill", "extract", "frame-at", "clip", "compile", "merge"),
    "shorts": _mcp("inspect", "plan", "cut", "run"),
    "media": _mcp("fetch", "probe", "audio", "sheet", "subs", "burn", "mask", "replace-audio", "voice-track"),
    "qc": _mcp("congelado"),
    "install": {
        "--uninstall": Verbo("--uninstall", False, "remover as skills dos hosts", "install --uninstall"),
    },
    "update": {
        "instalar": Verbo("instalar", False, "atualizar o pacote instala software", "update"),
    },
}

# The tools that refuse a call with no output, and the subcommands that need one.
SAIDA_OBRIGATORIA = {"edit": ("transcribe", "render", "verify", "grade"), "shorts": ("plan", "cut", "run")}

AJUDA = ("-h", "--help")
_OPCOES_DE_REMOCAO = ("--uninstall", "--prune-project-copies")


def verbos_mcp(tool: str) -> tuple[str, ...]:
    """The words of `tool` that the MCP runs, in the order of the table: the closed list of its `cmd`."""
    return tuple(nome for nome, v in POLITICA[tool].items() if v.mcp)


def _palavra(nome: str) -> bool:
    """A word a caller typed, as opposed to a row that stands for a shape (`media fetch`, `--watch`) or for every other word (`*`)."""
    return " " not in nome and not nome.startswith("-") and nome != "*"


def verbo(tool: str, nome: str) -> Verbo:
    """The row of a word the caller typed when it says something terminal-only about it, else the row `*` of the tool for that word."""
    linha = POLITICA[tool]
    v = linha.get(nome) if _palavra(nome) else None
    if v is not None and v.terminal_motivo:
        return v
    return replace(linha["*"], nome=nome)


def so_terminal(tool: str, verbo: Verbo, **valores: str) -> str | None:
    """The refusal text of a verb that is terminal-only (or has a terminal-only part), or None when it has nothing terminal-only."""
    if not verbo.terminal_motivo:
        return None
    mapa = {"tool": tool, "nome": verbo.nome, **valores}

    def preenche(texto: str) -> str:  # one pass: a value that holds `{resto}` is not filled in again
        return re.sub(r"\{(\w+)\}", lambda m: str(mapa.get(m.group(1), m.group(0))), texto)

    motivo = preenche(verbo.terminal_motivo)
    if verbo.forma is None:
        return motivo
    return f"{motivo}: rode `simplicio-video {preenche(verbo.forma)}` no terminal; o MCP não faz isso"


def caminho_seguro(p: str) -> bool:
    """Absolute and without `..`: Hypit resolves a relative path against the server's folder, which the client does not control."""
    return os.path.isabs(p) and ".." not in Path(p).parts


def pede_ajuda(argv: list[str]) -> bool:
    """`-h` or `--help` in the argument list: the help of the command is what the caller asked for (see INSTRUCTIONS in mcp_server)."""
    return any(t in AJUDA for t in argv)


def clone_com_pasta(argv: list[str], ajuda_passa: bool = False) -> bool:
    """`clone` with an operand: the folder where the checkout is written. An agent does not choose that, so it is terminal-only. With
    `ajuda_passa` a help request (`clone <dir> --help`) is not that: the CLI prints the help and writes nothing."""
    return argv[:1] == ["clone"] and len(argv) > 1 and not (ajuda_passa and pede_ajuda(argv))


def opcao_de_remocao(token: str) -> bool:
    """`--uninstall` or `--prune-project-copies`, a prefix of either with 3+ letters after `--`, with or without `=value`. argparse
    takes all of these (the install parser refuses the prefixes now too), so the MCP guard matches them all."""
    nome = token.split("=", 1)[0]
    return len(nome) >= 5 and nome.startswith("--") and any(opcao.startswith(nome) for opcao in _OPCOES_DE_REMOCAO)


def saida_absoluta_nova(argv: list[str], flags: dict | None = None, *, nome: str, opcoes: str = "-o/--out", chaves: tuple[str, ...] = (),
                        obrigatoria: str | None = None) -> str | None:
    """The output rule of the tools that write with -o (media, shorts, edit), checked on what the CLI itself reads (`flags`: the dict its
    own parser builds from the same words; None when there is none). Every spelling of an output option (-o, -oX, -o=X, --out, --out=X,
    --output, --ou...; edit.output_values reads them all) must be an absolute path with no `..`: a relative one lands in the folder the MCP
    server was started from. Each output key the CLI reads (`chaves`) must come from one -o of the call: a -o that another option
    swallowed (`--fit -o X`, `--out=X -o Y`) or a repeated one is refused. With `obrigatoria` (the text of the refusal) a call with no
    output at all is refused too. Whether the file is new is not asked here: media, shorts and edit overwrite, as their descriptions say.
    Returns the refusal, or None."""
    valores = output_values(argv)
    if obrigatoria and not valores:
        return obrigatoria
    for valor in valores:
        if not caminho_seguro(valor):
            return f"{nome}: {opcoes} precisa ser um caminho absoluto, sem `..` (um relativo cairia na pasta onde o servidor MCP foi iniciado)"
    lidas = chaves if flags is not None else ()  # no parse (the CLI rejects the words) there is no key to count against
    for chave in lidas:
        if argv.count(chave) != (1 if chave in flags else 0):
            return (f"{nome}: {chave} não é uma opção própria com um valor: foi engolido por outra opção, falta o valor, "
                    "ou está repetido; ponha -o com um caminho absoluto")
    return None


GRADE_FILTERS_MCP = frozenset({"eq", "curves", "colorbalance", "hue", "lut", "lutrgb", "lutyuv", "colorchannelmixer", "vibrance"})
GRADE_BAD_OPTIONS = frozenset({"file", "filename", "stats_file", "result", "psfile", "preset"})


def colour_filter_ok(chain: str) -> bool:
    """True if every filter of the chain is a colour filter from the closed set, with no file-reading option. A backslash or a
    quote is refused wherever it is: ffmpeg drops them before it matches the option names, so ps\\file and 'psfile' are psfile."""
    if any(c in chain for c in "\\'\""):
        return False
    for part in re.split(r"[,;]", chain):
        name, _, opts = part.strip().partition("=")
        if name.strip() not in GRADE_FILTERS_MCP:
            return False
        for o in (opts.split(":") if opts else []):
            key, eq, _v = o.partition("=")
            if key.strip().lower() in GRADE_BAD_OPTIONS or (not eq and name.strip() == "curves"):
                return False
    return True


def edit_recusa(argv: list[str]) -> str | None:
    """The refusal of `video.edit` for this argument list (subcommand first), or None. transcribe-batch is terminal-only; a subcommand that
    writes needs an absolute output with no `..`; the EDL of render and the folder of pack must be absolute too (the upstream render writes
    its intermediates beside the EDL, and pack writes takes_packed.md into its folder: both are read from the cwd when relative, so the MCP
    takes them absolute, no `..`, and says so); grade --filter takes only colour filters here. A help request or a read-only grade
    (--analyze, --list-presets, --print-preset) writes nothing and is left to the CLI."""
    sub, rest = (argv[0] if argv else ""), argv[1:]
    if sub in ("transcribe-batch", "transcribe_batch"):
        return so_terminal("edit", POLITICA["edit"]["transcribe-batch"])
    leitura = pede_ajuda(rest) or any(r.split("=", 1)[0] in GRADE_READ_ONLY for r in rest if sub == "grade")
    if sub in SAIDA_OBRIGATORIA["edit"] and not leitura:
        erro = saida_absoluta_nova(rest, None, nome=f"edit {sub}", opcoes="-o/--out/--output",
                                   obrigatoria=f"edit {sub}: -o <caminho absoluto> é obrigatório no MCP")
        if erro:
            return erro
    # the upstream render writes its intermediates beside the EDL, and pack writes takes_packed.md into its folder: both are read
    # from the cwd when relative, so the MCP takes them absolute (no `..`) and says so
    if not leitura and sub == "render" and not (rest and caminho_seguro(rest[0])):
        return ("edit render: o EDL precisa ser um caminho absoluto, sem `..` (o render grava os intermediários na pasta dele, "
                "e o MCP não sabe de que pasta o servidor foi iniciado)")
    if not leitura and sub == "pack" and not (rest and caminho_seguro(rest[0])):
        return "edit pack: a pasta EDIT_DIR precisa ser um caminho absoluto, sem `..` (o pack grava takes_packed.md nela)"
    if sub == "grade":
        for f in filter_values(rest):
            if not colour_filter_ok(f):
                return so_terminal("edit", POLITICA["edit"]["grade"])
    return None


# ---- Hypit (the `clone` tool): a closed allow-list --------------------------------------------------------------------
_MEDIA_VALOR = ("--start", "--end", "--at", "--every", "--around", "--occurrence", "--padding", "--frames", "--cell", "--columns", "--rows",
                "--keep", "--color")   # options with a value that is not a path
_MEDIA_CAMINHO = ("--to", "--ranges", "--transcript")  # options whose value is a path: absolute, no `..`
_MEDIA_FLAG = ("--json", "--label-time", "--every-frame", "--debug", "--verbose", "--no-color")


def _media_permitido(resto: list[str]) -> bool:
    if "--help" in resto:
        return True  # Hypit prints help before it reads anything else
    i = 0
    while i < len(resto):
        t = resto[i]
        if t in _MEDIA_FLAG:
            i += 1
        elif t in _MEDIA_VALOR:
            i += 2
        elif t in _MEDIA_CAMINHO:
            if i + 1 >= len(resto) or not caminho_seguro(resto[i + 1]):
                return False
            i += 2
        elif t.startswith("--"):
            return False  # unknown option, or the `--opt=value` form
        else:
            if not caminho_seguro(t):
                return False
            i += 1
    return True


def hypit_permitido(argv: list[str]) -> bool:
    """A closed allowlist: the first word is the Hypit command, and nothing outside the list reaches Hypit."""
    if not argv or "--watch" in argv:
        return False
    cmd = argv[0]
    if cmd in ("--help", "-h"):
        return True
    if cmd == "media":
        return argv[1:2] != [] and argv[1] in HYPIT_MEDIA and _media_permitido(argv[2:])
    if cmd == "get":
        i = argv.index("--to") + 1 if "--to" in argv[:-1] else 0
        return bool(i) and caminho_seguro(argv[i]) and not any(a.startswith("--to=") for a in argv)
    return cmd in HYPIT_LIVRE


def hypit_recusa(argv: list[str]) -> str:
    """The refusal text for an argument list `hypit_permitido` turned down: which word is terminal-only and the command to type."""
    tabela = POLITICA["clone"]
    if argv[:2] in (["media", "fetch"], ["media", "prepare-fetch"]):
        return so_terminal("clone", tabela[f"media {argv[1]}"])
    if "--watch" in argv:
        return so_terminal("clone", tabela["--watch"], resto=" ".join(argv))
    return so_terminal("clone", verbo("clone", argv[0] if argv else "(vazio)"))
