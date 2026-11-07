#!/usr/bin/env python3
"""Generates the reference in docs/reference/ from the code, plus the GENERATED blocks of the docs and the generated fields of
plugin.json (#44).

Usage:
  scripts/gen_reference.py --out DIR                  writes cli.md, schemas.md, config.md, mcp-tools.md, events.md
  scripts/gen_reference.py --out DIR --check          writes nothing; exits 1 when a file in DIR, a block or plugin.json is stale
  scripts/gen_reference.py --out DIR --update-blocks  writes DIR, rewrites the GENERATED blocks and the generated fields of plugin.json

The blocks (BLOCKS below says which file carries which): `host` (map of docs/host/*.md, from the front matter), `fatos` (the
counts and pins that the docs used to repeat by hand: MCP tools, external tracks, templates, motion patterns, HyperFrames, hosts,
skills, the pin of each track) and `mapa-modulos` (the first sentence of the docstring of each module of the package). In
plugin.json the generator owns `version`, `contract_schema`, `skills` and `mcp.tools`; `commands` stays hand-written.

Deterministic: no dates, no absolute paths, sorted order. Each subcommand's help is the real output of
`python -m simplicio_video <sub> --help` run in a subprocess, offline (SIMPLICIO_OFFLINE=1).

Examples:
  scripts/gen_reference.py --out docs/reference
  scripts/gen_reference.py --out docs/reference --check
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
PKG = SRC / "simplicio_video"
DATA = PKG / "data"
PLUGIN_JSON = ROOT / "plugin.json"
SECTION_DIRS = {"host": ROOT / "docs" / "host"}
# Which generated blocks each file carries (path from the repo root -> sections). A file that must carry a block and has none, or
# has it twice, is an error: a block that disappears must not turn into a silent skip.
BLOCKS = {
    "README.md": ("host", "fatos"),
    "README.pt-BR.md": ("fatos",),
    "PYPI.md": ("fatos",),
    "AGENTS.md": ("host", "fatos", "mapa-modulos"),
    "docs/esteira.md": ("fatos",),
    "docs/host/README.md": ("fatos",),
}
BLOCK_FILES = tuple(ROOT / rel for rel in BLOCKS)
# Language of the `fatos` block of each file and the facts it carries ("pins" = the table of pins per track). Each file gets only
# the facts it talks about; PYPI.md has no pin table (it is the short page of the package).
_COUNTS = ("tools", "trilhas", "templates", "padroes", "hyperframes", "hosts", "hosts_globais", "skills")
FATOS = {
    "README.md": ("en", _COUNTS + ("pins",)),
    "README.pt-BR.md": ("pt", _COUNTS + ("pins",)),
    "PYPI.md": ("pt", ("tools", "trilhas", "hyperframes", "hosts")),
    "AGENTS.md": ("pt", _COUNTS),
    "docs/esteira.md": ("pt", ("templates", "padroes", "hyperframes")),
    "docs/host/README.md": ("pt", ("hosts", "hosts_globais", "skills")),
}
# Modules the module map leaves out: the entry shim and the empty package marker. Any other module without a docstring is listed
# and marked, so the gap shows in AGENTS.md instead of being hidden.
MAP_SKIP = {"__main__.py", "commands/__init__.py"}
NO_NOTE = {"PYPI.md"}
FATOS_TEXT = {
    "en": {
        "note": "Counts generated from the code (`scripts/gen_reference.py`); where hand-written text elsewhere says another number, "
                "these are the ones read from the code. Do not edit here: run `make regen`.",
        "head": ("Fact", "Value"), "pins": ("Track", "Kind", "Pin"),
        "tools": "MCP tools (`video.*`)", "trilhas": "External tracks", "templates": "Templates", "padroes": "Motion patterns",
        "hyperframes": "HyperFrames", "hosts": "Agent hosts (`install`)",
        "hosts_globais": "Hosts with a global skills folder (`install --global`)", "skills": "Skills for agents",
        "sem_composicao": "{n} without `composicao` (do not render)", "sem_status": "no status",
    },
    "pt": {
        "note": "Contagens geradas do código (`scripts/gen_reference.py`); onde um texto à mão em outro ponto diz outro número, "
                "estes são os lidos do código. Não edite aqui: rode `make regen`.",
        "head": ("Fato", "Valor"), "pins": ("Trilha", "Tipo", "Pin"),
        "tools": "Tools MCP (`video.*`)", "trilhas": "Trilhas externas", "templates": "Templates", "padroes": "Padrões de motion",
        "hyperframes": "HyperFrames", "hosts": "Hosts de agente (`install`)",
        "hosts_globais": "Hosts com pasta global de skills (`install --global`)", "skills": "Skills para agentes",
        "sem_composicao": "{n} sem `composicao` (não renderizam)", "sem_status": "sem status",
    },
}
FRONT_MATTER = re.compile(r"^---\n(.*?)\n---\n", re.S)
ENV_NAME = re.compile(r"^[A-Z][A-Z0-9_]+$")
ENV_READERS = {"get", "pop", "setdefault"}
TRILHA_ENV_ARGS = ("env_dir", "env_data")  # the keyword names of the two variables of a `Trilha(...)` (positions 1 and 2)

# What each variable is for. A variable the code reads but this table does not describe is still listed, marked
# as undescribed, so the gap shows up in the reference instead of being hidden.
DESCRIPTIONS = {
    "GH_TOKEN": "Token do GitHub que o `update` manda só para `api.github.com` ao ler a última release (um redirect para outro host tira o cabeçalho). Só no ambiente.",
    "GITHUB_TOKEN": "O mesmo que `GH_TOKEN`, quando ele não está definido. Só vai para `api.github.com`.",
    "GEMINI_API_KEY": "Chave da API Gemini (TTS, provider `gemini`; adaptador `gemini` do `swap`). Só no ambiente; nunca no repo.",
    "HYPERFRAMES_BROWSER_PATH": "Chrome headless que o HyperFrames usa na captura. Definido pelo render remoto.",
    "HYPERFRAMES_FFMPEG_PATH": "ffmpeg que o HyperFrames usa. Definido pelo render remoto.",
    "HYPERFRAMES_FFPROBE_PATH": "ffprobe que o HyperFrames usa. Definido pelo render remoto.",
    "KAGGLE_CONFIG_DIR": "Pasta do `kaggle.json` (padrão: `~/.kaggle`).",
    "KAGGLE_USERNAME": "Usuário do Kaggle para o render remoto (sem ele, lê o `kaggle.json`).",
    "KOKORO_DIR": "Pasta dos modelos do Kokoro (TTS local; padrão `~/.local/share/simplicio-tts`).",
    "MONEYPRINTER_DATA_DIR": "Pasta de dados da trilha MoneyPrinterTurbo: venv isolado e storage com os vídeos gerados (padrão: `~/.simplicio-video/moneyprinter-data`, fora do checkout).",
    "MONEYPRINTER_DIR": "Checkout do MoneyPrinterTurbo (alternativa a `SIMPLICIO_TOOLS_DIR/moneyprinter`).",
    "INSTAGRAM_DIR": "Checkout do instagram-agent-skill (alternativa a `SIMPLICIO_TOOLS_DIR/instagram`). O `instagram run` avisa quando ele está em uso e confere o sha256 de cada script do mesmo jeito.",
    "MATCHCUT_DIR": "Checkout do match-cut (alternativa a `SIMPLICIO_TOOLS_DIR/matchcut`).",
    "VIDEO_USE_DIR": "Checkout do video-use (trilha `edit`), mantido pelo setup.sh em data/tools/video-use; o `update` segue esta pasta (padrão `~/.cache/simplicio/video-use`).",
    "REA_VIDEO_DATA_DIR": "Pasta de dados da trilha rea-video: o venv próprio e o estado do upstream (padrão: `~/.simplicio-video/rea-video-data`, fora do checkout).",
    "REA_VIDEO_DIR": "Checkout do rea-video (alternativa a `SIMPLICIO_TOOLS_DIR/rea_video`).",
    "REA_VIDEO_HOME": "Memória e preferências do rea-video. A trilha aponta para a pasta de dados dela (`.../rea-video-data/home`) só se a variável não estiver definida.",
    "REA_VIDEO_MODELS": "Pasta dos modelos do rea-video (separação de voz de cerca de 67 MB, detector de rosto, OCR). A trilha aponta para `.../rea-video-data/models` só se a variável não estiver definida.",
    "REA_VIDEO_PYTHON": "Interpretador que cria o venv do rea-video no `setup`, por exemplo `python3.11` para o extra de OCR. Um venv que já existe é mantido.",
    "OPENCUT_DIR": "Pasta do OpenCut, lida pelo próprio editor (trilha `opencut`).",
    "OPENVERSE_CLIENT_ID": "Credencial OAuth2 opcional da API do Openverse (par com `OPENVERSE_CLIENT_SECRET`; sobe o limite de requisições e o tamanho da página). Só no ambiente; nunca em argumento, índice, cache ou saída.",
    "OPENVERSE_CLIENT_SECRET": "Segredo OAuth2 opcional da API do Openverse (par com `OPENVERSE_CLIENT_ID`). Só no ambiente; nunca em argumento, índice, cache ou saída.",
    "OPENVERSE_LIBRARY_DIR": "Pasta da biblioteca do Openverse: `index.json`, `files/<sha256>`, `cache/` e `sheets/` (padrão: `~/.simplicio-video/openverse-library`).",
    "BACKLOT_PORT": "Porta do board (Backlot) do OpenMontage; o `montage open` e o `montage serve` a repassam ao upstream.",
    "OPENMONTAGE_DATA_DIR": "Pasta do venv do OpenMontage (padrão: `~/.simplicio-video/openmontage-data`); um caminho relativo vira absoluto a partir da pasta atual, com aviso.",
    "OPENMONTAGE_DIR": "Pasta do OpenMontage (trilha `montage`). Também lida pelo OpenMontage.",
    "OPENVOICE_CHECKPOINTS": "Pasta dos checkpoints do OpenVoice (provider `openvoice`).",
    "OPENVOICE_PY": "Python com o OpenVoice instalado (provider `openvoice`).",
    "PATH": "Lista de pastas de executáveis do sistema. Lida, não configurada pelo produto. O `doctor` procura `simplicio`, `node` e `ffmpeg` só nas pastas absolutas dela, nunca no diretório atual.",
    "PATHEXT": "Extensões executáveis do Windows (`.EXE;.CMD`...). Lida só no Windows, ao procurar `simplicio`, `node`, `ffmpeg` e `npm` no PATH.",
    "PIP_BREAK_SYSTEM_PACKAGES": "`1` autoriza o pip a mexer no Python do sistema (PEP 668). O `update` de um pacote instalado por pip respeita: sem ele, um Python gerenciado pelo sistema é recusado com exit 2.",
    "SIMPLICIO_COLAB_AUTH": "Modo de autenticação do Colab CLI, repassado a `--auth`.",
    "SIMPLICIO_DRIVE_REMOTE": "Nome do remote do rclone para o Drive (padrão: `gdrive`).",
    "SIMPLICIO_FFMPEG_DIR": "Pasta do ffmpeg/ffprobe fixados (render local e `swap`).",
    "SIMPLICIO_FFMPEG_SHA256": "SHA-256 esperado do ffmpeg estático de `SIMPLICIO_FFMPEG_URL`.",
    "SIMPLICIO_FFMPEG_URL": "URL de um ffmpeg estático fixado, baixado e verificado pelos renders remotos.",
    "SIMPLICIO_FAKE_FAIL": "`1` faz o adaptador `fake` do swap recusar o envio de vez (testes de `jobs`).",
    "SIMPLICIO_FAKE_FETCH_S": "Atraso simulado, em segundos, do download no adaptador `fake` do swap.",
    "SIMPLICIO_FAKE_GENERATION_S": "Tempo simulado, em segundos, que um pedaço fica `running` no adaptador `fake` do swap.",
    "SIMPLICIO_FAKE_STUCK": "`1` faz o adaptador `fake` do swap nunca terminar (testes de cancelamento).",
    "SIMPLICIO_FAKE_SUBMIT_S": "Atraso simulado, em segundos, do envio no adaptador `fake` do swap.",
    "SIMPLICIO_GEMINI_BASE": "Base da API Gemini (padrão: a oficial). Para proxies e testes.",
    "SIMPLICIO_JOB_ORIGIN": "Rótulo de procedência de uma tarefa de `jobs`: `terminal` ou `mcp`. O runner (`jobs.py`) grava no ambiente do processo filho a origem de quem submeteu a tarefa, e a trilha `video-to-skill` a copia para o `PASTA.extract.json` (`submitted_via`). Não é controle de acesso: não autoriza nem bloqueia nada, só registra de onde veio o pedido.",
    "SIMPLICIO_JOBS_GRACE_S": "Tolerância, em segundos, entre o SIGINT e o SIGKILL ao cancelar uma tarefa de `jobs` (padrão 15).",
    "SIMPLICIO_OFFLINE": "`1` bloqueia rede nas checagens offline (inclui a consulta da última release no `update` e no `doctor --online`). O gate (`make check`) roda com `1`.",
    "SIMPLICIO_OPENMONTAGE_DIR": "Pasta do OpenMontage (alternativa a `OPENMONTAGE_DIR`).",
    "SIMPLICIO_RCLONE_BIN": "Caminho do binário do rclone (padrão: o `rclone` do PATH).",
    "SIMPLICIO_STT_PY": "Python com o motor de transcrição (STT). Padrão: o Python do TTS local.",
    "SIMPLICIO_BUSCA_MAX_DIA": "Teto de chamadas ao TinyFish por dia UTC no `busca` (padrão 20; máximo 1000). `--max-chamadas-dia` vence. O MCP e o plugin só usam este valor ou o padrão.",
    "TINYFISH_API_KEY": "Chave da API do TinyFish, lida só pelo binário `tinyfish` (que também a guarda em `~/.tinyfish/config.json`). O `busca` a repassa ao binário se estiver no ambiente e nunca a lê, imprime nem grava; nunca em argumento.",
    "TOONFLOW_DATA_DIR": "Pasta de dados do servidor Toonflow (padrão: `~/.simplicio-video/toonflow-data`, fora do checkout).",
    "TOONFLOW_DIR": "Checkout do Toonflow (alternativa a `SIMPLICIO_TOOLS_DIR/toonflow`).",
    "SIMPLICIO_TOOLS_DIR": "Pasta das ferramentas opcionais instaladas (padrão: `~/.simplicio-video/tools`).",
    "SIMPLICIO_TTS_PY": "Python com kokoro-onnx e soundfile (TTS local; padrão: `~/.local/share/simplicio-tts/cbvenv`).",
    "SIMPLICIO_VIDEO_DATA": "Pasta de dados do simplicio-video (padrão: `~/.simplicio-video`). Lida pelas trilhas `montage`, `toonflow`, `moneyprinter` e `rea-video`, pelo `jobs` (estado das tarefas em `jobs/`), pelo `busca` (cache, contador e registro em `busca/`) e pelo `update` (`update-check.json`, que o `doctor` lê sem rede).",
    "SIMPLICIO_VIDEO_HOME": "Checkout do simplicio-video (dados do motor e raiz do repo). Sem ela, o pacote procura o checkout.",
    "SIMPLICIO_WORKSPACE": "Pasta do workspace da fábrica (padrão: `~/.simplicio-video/workspaces/default`).",
    "SV_BROWSER_GPU": "`1` liga a GPU do navegador na captura do render.",
    "SV_BUNDLE": "Caminho do bundle a renderizar no render remoto.",
    "SV_FFMPEG_SHA256": "SHA-256 do ffmpeg estático do render remoto (padrão: o fixado no bundle).",
    "SV_FFMPEG_URL": "URL do ffmpeg estático do render remoto (padrão: o fixado no bundle).",
    "SV_OUT": "Pasta de saída do render remoto (padrão: `/kaggle/working` ou `sv-out`).",
    "SV_QUALITY": "Qualidade do render remoto: `draft`, `looks` ou `delivery`.",
    "SV_SKIP_SETUP": "`1` pula a instalação de dependências do render remoto.",
    "SV_WORKERS": "Workers do HyperFrames no render: `auto` (padrão) ou um inteiro.",
    "VIDEO_TO_SKILL_DIR": "Checkout do video-to-skill (alternativa a `SIMPLICIO_TOOLS_DIR/video_to_skill`). O binário `vts-extract` fica à parte, em `SIMPLICIO_TOOLS_DIR/video-to-skill-bin`.",
    "VTS_DATA_DIR": "Pasta de dados do `vts-extract` (ffmpeg, yt-dlp e modelos que o `check --fix --yes` do upstream baixa; padrão: a pasta de dados da plataforma, em `video-to-skill`). O motor repassa a variável ao extrator, mas nunca roda o `check --fix --yes`.",
    "VOICESTUDIO_API_KEY": "Chave opcional da API local do VoiceStudio (provider `voicestudio`).",
    "VOICESTUDIO_URL": "URL da API local do VoiceStudio (padrão: `http://localhost:3900`).",
    "VOXCPM_BIN": "Executável do VoxCPM (provider `openvoice`, clonagem com clipe de referência).",
}


def _import_cli():
    sys.path.insert(0, str(SRC))
    from simplicio_video.cli import build_parser  # noqa: PLC0415 (path set above)

    return build_parser()


def _subcommands(parser) -> list[str]:
    action = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
    return sorted(action.choices)


# O argparse do 3.12 mede a coluna de ajuda dos subcomandos com o recuo do pai; o do 3.13 (e a referência commitada) mede cada
# um com o seu, e imprime `-t, --template X` uma vez só (3.13) em vez de repetir o metavar por opção (3.12). O filho roda por este invólucro, que impõe a regra do 3.13 em qualquer Python, para o cli.md não depender da versão.
_CHILD = """
import argparse, runpy, sys
def add_argument(self, action):
    if action.help is not argparse.SUPPRESS:
        get = self._format_action_invocation
        lengths = [len(get(action)) + self._current_indent]
        for sub in self._iter_indented_subactions(action):
            lengths.append(len(get(sub)) + self._current_indent)
        self._action_max_length = max(self._action_max_length, max(lengths))
        self._add_item(self._format_action, [action])
def invocation(self, action):
    if not action.option_strings:
        default = self._get_default_metavar_for_positional(action)
        return " ".join(self._metavar_formatter(action, default)(1))
    if action.nargs == 0:
        return ", ".join(action.option_strings)
    default = self._get_default_metavar_for_optional(action)
    return ", ".join(action.option_strings) + " " + self._format_args(action, default)
argparse.HelpFormatter.add_argument = add_argument
argparse.HelpFormatter._format_action_invocation = invocation
sys.argv[0] = "simplicio_video"
runpy.run_module("simplicio_video", run_name="__main__", alter_sys=True)
"""


def _help(args: list[str]) -> str:
    env = {
        "PATH": os.environ.get("PATH", ""),
        "PYTHONPATH": str(SRC),
        "SIMPLICIO_OFFLINE": "1",
        "LANG": "C.UTF-8",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONIOENCODING": "utf-8",
    }
    flag = "--engine-help" if args == ["clone"] else "--help"  # `clone --help` is Hypit's own help (npx), not the engine's
    result = subprocess.run(
        [sys.executable, "-c", _CHILD, *args, flag],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        env=env,
        timeout=120,
    )
    if result.returncode != 0:
        raise SystemExit(f"gen_reference: `simplicio-video {' '.join(args)} --help` saiu com {result.returncode}:\n{result.stderr}")
    text = result.stdout.rstrip("\n")
    if "```" in text:
        raise SystemExit(f"gen_reference: o help de `{' '.join(args)}` tem três crases e quebraria o bloco de código")
    return text


def cli_md() -> str:
    names = _subcommands(_import_cli())
    targets = [[]] + [[name] for name in names]
    with ThreadPoolExecutor(max_workers=8) as pool:
        helps = list(pool.map(_help, targets))
    lines = [
        "# Referência da CLI",
        "",
        "> Gerado por `scripts/gen_reference.py` a partir do `--help` real de cada comando. Não edite à mão: rode `make regen`.",
        "",
        "Cada seção abaixo é a saída de `simplicio-video <comando> --help`. Os exemplos vêm do próprio help.",
        "",
    ]
    for target, text in zip(targets, helps):
        title = " ".join(["simplicio-video", *target])
        lines += [f"## {title}", "", "```text", text, "```", ""]
    return "\n".join(lines)


def schemas_md() -> str:
    paths = sorted(DATA.rglob("*.schema.json"), key=lambda p: p.relative_to(ROOT).as_posix())
    lines = [
        "# Schemas JSON do pacote",
        "",
        "> Gerado por `scripts/gen_reference.py` a partir de `src/simplicio_video/data/**/*.schema.json`. Não edite à mão: rode `make regen`.",
        "",
        "| Arquivo | `$id` ou título | Descrição |",
        "|---|---|---|",
    ]
    for path in paths:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise SystemExit(f"gen_reference: {path.relative_to(ROOT)} não é JSON válido: {exc}")
        ident = data.get("$id") or data.get("title") or "—"
        desc = (data.get("description") or "").strip().splitlines()[0:1]
        desc_text = desc[0] if desc else "—"
        cells = [path.relative_to(ROOT).as_posix(), ident, desc_text]
        lines.append("| " + " | ".join(c.replace("|", "\\|") for c in cells) + " |")
    lines.append("")
    return "\n".join(lines)


def _is_environ(node) -> bool:
    return (isinstance(node, ast.Attribute) and node.attr == "environ") or (
        isinstance(node, ast.Name) and node.id == "environ"
    )


def _is_trilha(func) -> bool:
    return (isinstance(func, ast.Name) and func.id == "Trilha") or (isinstance(func, ast.Attribute) and func.attr == "Trilha")


def _variaveis_da_trilha(call) -> list:
    """The nodes that name the two environment variables of a `Trilha(nome, env_dir, env_data)` call, positional or by keyword."""
    return [*call.args[1:3], *(k.value for k in call.keywords if k.arg in TRILHA_ENV_ARGS)]


def env_reads() -> dict[str, list[str]]:
    """Environment variable names read (or set) by the package, found by ast, with `arquivo:linha` locations. A track names its
    checkout and data variables only as the arguments of `Trilha(...)` (trilha_base reads them through the declaration), so those
    arguments count as reads, at the line of the call."""
    found: dict[str, set[str]] = {}

    def add(name, rel, line):
        if isinstance(name, str) and ENV_NAME.match(name):
            found.setdefault(name, set()).add(f"{rel}:{line}")

    for path in sorted(PKG.rglob("*.py")):
        rel = path.relative_to(ROOT).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        consts = {}  # module-level NAME = "VALUE", so os.environ.get(ENV_KEY) resolves to its value
        for stmt in tree.body:
            if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 and isinstance(stmt.targets[0], ast.Name):
                if isinstance(stmt.value, ast.Constant) and isinstance(stmt.value.value, str):
                    consts[stmt.targets[0].id] = stmt.value.value

        def literal(arg):
            if isinstance(arg, ast.Constant):
                return arg.value
            if isinstance(arg, ast.Name):
                return consts.get(arg.id)
            return None

        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and _is_trilha(node.func):
                for arg in _variaveis_da_trilha(node):
                    add(literal(arg), rel, node.lineno)
            if isinstance(node, ast.Call) and node.args:
                func = node.func
                if isinstance(func, ast.Attribute) and func.attr in ENV_READERS and _is_environ(func.value):
                    add(literal(node.args[0]), rel, node.lineno)
                elif (isinstance(func, ast.Attribute) and func.attr == "getenv") or (
                    isinstance(func, ast.Name) and func.id == "getenv"
                ):
                    add(literal(node.args[0]), rel, node.lineno)
            elif isinstance(node, ast.Subscript) and _is_environ(node.value):
                add(literal(node.slice), rel, node.lineno)
    return {name: sorted(locs) for name, locs in sorted(found.items())}


def config_md() -> str:
    reads = env_reads()
    lines = [
        "# Variáveis de ambiente",
        "",
        "> Gerado por `scripts/gen_reference.py` (leitura estática com `ast` em `src/simplicio_video/`). Não edite à mão: rode `make regen`.",
        "",
        "Lista só os nomes escritos literalmente no código. Variáveis montadas em tempo de execução (por exemplo `SIMPLICIO_<FERRAMENTA>_REF`) não aparecem aqui.",
        "",
        "| Variável | Para quê | Onde o código lê ou define |",
        "|---|---|---|",
    ]
    for name, locs in reads.items():
        desc = DESCRIPTIONS.get(name, "(sem descrição na tabela de gen_reference.py)")
        where = "<br>".join(f"`{loc}`" for loc in locs)
        lines.append(f"| `{name}` | {desc} | {where} |")
    lines.append("")
    return "\n".join(lines)


def mcp_tools_md() -> str:
    sys.path.insert(0, str(SRC))
    from simplicio_video.mcp_server import TOOLS  # noqa: PLC0415 (path set above)

    lines = [
        "# Tools MCP",
        "",
        "> Gerado por `scripts/gen_reference.py` a partir de `TOOLS` em `src/simplicio_video/mcp_server.py`. Não edite à mão: rode `make regen`.",
        "",
        "| Tool | Descrição |",
        "|---|---|",
    ]
    for name, _fn, desc in TOOLS:
        lines.append(f"| `{name}` | {desc.replace('|', chr(92) + '|')} |")
    lines.append("")
    return "\n".join(lines)


def events_md() -> str:
    return "\n".join([
        "# Eventos",
        "",
        "> Gerado por `scripts/gen_reference.py`. Não edite à mão: rode `make regen`.",
        "",
        "Ainda não há eventos catalogados. O catálogo aparece aqui quando o motor começar a emitir eventos.",
        "",
    ])


def reference_files() -> dict[str, str]:
    return {
        "cli.md": cli_md(),
        "schemas.md": schemas_md(),
        "config.md": config_md(),
        "mcp-tools.md": mcp_tools_md(),
        "events.md": events_md(),
    }


def _front_matter(path: Path) -> dict:
    match = FRONT_MATTER.match(path.read_text(encoding="utf-8"))
    if not match:
        raise SystemExit(f"gen_reference: {path.relative_to(ROOT).as_posix()} sem front matter")
    import yaml  # noqa: PLC0415 (only the block generator needs it)

    meta = yaml.safe_load(match.group(1))
    if not isinstance(meta, dict) or "title" not in meta or "summary" not in meta:
        raise SystemExit(f"gen_reference: {path.relative_to(ROOT).as_posix()} sem title ou summary no front matter")
    return meta


def host_body() -> str:
    pages = sorted(
        (p for p in SECTION_DIRS["host"].glob("*.md") if p.name != "README.md"),
        key=lambda p: p.relative_to(ROOT).as_posix(),
    )
    note = "Gerado de `docs/host/*.md` (front matter). Não edite aqui: rode `make regen`."
    if not pages:
        return f"{note}\n\nAinda não há páginas em `docs/host/`."
    items = []
    for page in pages:
        meta = _front_matter(page)
        items.append(f"- [{meta['title']}]({page.relative_to(ROOT).as_posix()}): {meta['summary']}")
    return f"{note}\n\n" + "\n".join(items)


def _package():
    """The package modules the facts come from, imported from this checkout (src/), like the CLI help above."""
    if str(SRC) not in sys.path:
        sys.path.insert(0, str(SRC))
    import simplicio_video  # noqa: PLC0415 (path set above)
    from simplicio_video import catalog, cli, installer, mcp_server, skill_sync, tools  # noqa: PLC0415

    return simplicio_video, catalog, cli, installer, mcp_server, skill_sync, tools


def facts() -> dict:
    """The numbers and pins the docs repeat, read from the code: the registries and the data files, never typed here."""
    package, catalog, _cli, installer, mcp_server, skill_sync, tools = _package()
    templates = catalog.templates(DATA)
    patterns = catalog.motion(DATA)
    by_pattern: dict = {}
    for item in patterns:
        by_pattern[item["status"]] = by_pattern.get(item["status"], 0) + 1
    by_template: dict = {}
    for item in templates:
        by_template[item["status"]] = by_template.get(item["status"], 0) + 1
    return {
        "tools": len(mcp_server.TOOLS),
        "trilhas": len(tools.TOOLS),
        "templates": len(templates),
        "templates_por_status": sorted(by_template.items()),
        "sem_composicao": sum(1 for item in templates if not item["renderizavel"]),
        "padroes": len(patterns),
        "padroes_por_status": sorted(by_pattern.items(), key=lambda kv: (-kv[1], str(kv[0]))),
        "hyperframes": package.HYPERFRAMES,
        "hosts": sorted(installer.HOST_ENTRY),
        "hosts_globais": sorted(skill_sync.HOST_SKILL_ROOTS),
        "skills": len(skill_sync.SKILLS),
        "pins": [(name, tool.kind, tool.ref[:7] if tool.kind == "git" else tool.ref) for name, tool in tools.TOOLS.items()],
    }


def fatos_body(rel: str) -> str:
    language, keys = FATOS[rel]
    text = FATOS_TEXT[language]
    data = facts()

    def counts(items) -> str:
        return ", ".join(f"{n} `{text['sem_status'] if status is None else status}`" for status, n in items)

    def names(items) -> str:
        return f"{len(items)}: " + ", ".join(f"`{item}`" for item in items)

    cells = {
        "tools": str(data["tools"]),
        "trilhas": str(data["trilhas"]),
        "templates": f"{data['templates']}: {counts(data['templates_por_status'])}; " + text["sem_composicao"].format(n=data["sem_composicao"]),
        "padroes": f"{data['padroes']}: {counts(data['padroes_por_status'])}",
        "hyperframes": f"`{data['hyperframes']}`",
        "hosts": names(data["hosts"]),
        "hosts_globais": names(data["hosts_globais"]),
        "skills": str(data["skills"]),
    }
    # PYPI.md is the public page of the package: the maintainer note would show there (the BEGIN/END comments do not render).
    lines = [""] if rel in NO_NOTE else [text["note"], ""]  # a blank line after the comment keeps the table a block of its own
    lines += [f"| {text['head'][0]} | {text['head'][1]} |", "|---|---|"]
    lines += [f"| {text[key]} | {cells[key]} |" for key in keys if key in cells]
    if "pins" in keys:
        head = text["pins"]
        lines += ["", f"| {head[0]} | {head[1]} | {head[2]} |", "|---|---|---|"]
        lines += [f"| `{name}` | {kind} | `{pin}` |" for name, kind, pin in data["pins"]]
    return "\n".join(lines)


_SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z`])")


def first_sentence(doc: str) -> str:
    """The first sentence of the first paragraph of a docstring, on one line (a docstring wraps, so its first line is often cut)."""
    paragraph = " ".join(doc.strip().split("\n\n", 1)[0].split())
    return _SENTENCE_END.split(paragraph, 1)[0]


def _escape_angle(text: str) -> str:
    """`<slug>` outside a code span would vanish as an HTML tag when the page is rendered."""
    parts = text.split("`")
    for index in range(0, len(parts), 2):
        parts[index] = parts[index].replace("<", "\\<")
    return "`".join(parts)


def mapa_modulos_body() -> str:
    items = []
    for path in sorted(PKG.rglob("*.py"), key=lambda p: p.relative_to(PKG).as_posix()):
        rel = path.relative_to(PKG).as_posix()
        if rel.startswith("data/") or rel in MAP_SKIP:
            continue
        doc = ast.get_docstring(ast.parse(path.read_text(encoding="utf-8"), filename=str(path)))
        summary = _escape_angle(first_sentence(doc)) if doc else "(sem docstring)"
        items.append(f"- `{rel}`: {summary}")
    note = ("Complementa a linha `src/simplicio_video/` da tabela acima (essa é à mão). Gerado da primeira frase da docstring de "
            "cada módulo de `src/simplicio_video/` (ficam de fora `data/` e os arquivos que não são Python em `engine/`). "
            "Não edite aqui: rode `make regen`.")
    return f"{note}\n\n" + "\n".join(items)


def block_body(section: str, rel: str) -> str:
    if section == "host":
        return host_body()
    if section == "fatos":
        return fatos_body(rel)
    if section == "mapa-modulos":
        return mapa_modulos_body()
    raise SystemExit(f"gen_reference: bloco desconhecido {section!r}")


def updated_block_text(text: str, path: Path) -> str:
    rel = path.relative_to(ROOT).as_posix()
    for section in BLOCKS[rel]:
        pattern = re.compile(rf"(<!-- BEGIN GENERATED: {section} -->\n).*?(<!-- END GENERATED -->)", re.S)
        matches = pattern.findall(text)
        if len(matches) != 1:
            raise SystemExit(f"gen_reference: {rel} precisa de exatamente um bloco '{section}'")
        body = block_body(section, rel)
        text = pattern.sub(lambda m: m.group(1) + body + "\n" + m.group(2), text, count=1)
    return text


def plugin_json_text(text: str) -> str:
    """plugin.json with the four generated fields rewritten from the code; `commands` and the rest stay as they are."""
    package, _catalog, cli, _installer, mcp_server, skill_sync, _tools = _package()
    try:
        plugin = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"gen_reference: plugin.json não é JSON válido: {exc}")
    plugin["version"] = package.__version__
    plugin["contract_schema"] = cli.SCHEMA_REL
    plugin["skills"] = [{"name": name, "path": f"skills/{name}/SKILL.md"} for name in skill_sync.SKILLS]
    plugin["mcp"]["tools"] = [name for name, _fn, _desc in mcp_server.TOOLS]
    for target in [plugin["contract_schema"], *(skill["path"] for skill in plugin["skills"])]:
        if not (ROOT / target).is_file():
            raise SystemExit(f"gen_reference: plugin.json apontaria para {target}, que não existe")
    return json.dumps(plugin, indent=2, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Gera docs/reference/ a partir do código e atualiza os blocos GENERATED dos docs e os campos gerados do plugin.json.",
        epilog="exemplos:\n  scripts/gen_reference.py --out docs/reference\n  scripts/gen_reference.py --out docs/reference --check",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--out", required=True, type=Path, help="pasta de saída (ex.: docs/reference)")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="não grava; sai com 1 se algo estiver desatualizado")
    mode.add_argument("--update-blocks", action="store_true", help="grava a pasta e reescreve os blocos dos docs e os campos gerados do plugin.json")
    args = parser.parse_args(argv)

    out = args.out.resolve()
    files = reference_files()
    stale = []
    if args.check:
        for name, text in files.items():
            current = (out / name).read_text(encoding="utf-8") if (out / name).exists() else None
            if current != text:
                stale.append(f"{out.relative_to(ROOT) if out.is_relative_to(ROOT) else out}/{name}")
        for path in BLOCK_FILES:
            text = path.read_text(encoding="utf-8")
            if updated_block_text(text, path) != text:
                stale.append(path.relative_to(ROOT).as_posix())
        plugin = PLUGIN_JSON.read_text(encoding="utf-8")
        if plugin_json_text(plugin) != plugin:
            stale.append(PLUGIN_JSON.relative_to(ROOT).as_posix())
        if stale:
            print("gen_reference: desatualizado (rode make regen):")
            for item in stale:
                print(f"  {item}")
            return 1
        print("gen_reference: ok (docs/reference, blocos e plugin.json em dia)")
        return 0

    out.mkdir(parents=True, exist_ok=True)
    for name, text in files.items():
        (out / name).write_text(text, encoding="utf-8")
    if args.update_blocks:
        for path in BLOCK_FILES:
            text = path.read_text(encoding="utf-8")
            path.write_text(updated_block_text(text, path), encoding="utf-8")
        PLUGIN_JSON.write_text(plugin_json_text(PLUGIN_JSON.read_text(encoding="utf-8")), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
