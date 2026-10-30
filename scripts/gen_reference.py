#!/usr/bin/env python3
"""Generates the reference in docs/reference/ from the code, plus the GENERATED blocks of README.md and AGENTS.md (#44).

Usage:
  scripts/gen_reference.py --out DIR                  writes cli.md, schemas.md, config.md, mcp-tools.md, events.md
  scripts/gen_reference.py --out DIR --check          writes nothing; exits 1 when a file in DIR or a block is stale
  scripts/gen_reference.py --out DIR --update-blocks  writes DIR and rewrites the blocks of README.md and AGENTS.md

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
BLOCK_FILES = (ROOT / "README.md", ROOT / "AGENTS.md")
SECTION_DIRS = {"host": ROOT / "docs" / "host"}
FRONT_MATTER = re.compile(r"^---\n(.*?)\n---\n", re.S)
ENV_NAME = re.compile(r"^[A-Z][A-Z0-9_]+$")
ENV_READERS = {"get", "pop", "setdefault"}

# What each variable is for. A variable the code reads but this table does not describe is still listed, marked
# as undescribed, so the gap shows up in the reference instead of being hidden.
DESCRIPTIONS = {
    "GH_TOKEN": "Token do GitHub que o `update` manda só para `api.github.com` ao ler a última release (um redirect para outro host tira o cabeçalho). Só no ambiente; o `login` nunca o repassa ao Runtime.",
    "GITHUB_TOKEN": "O mesmo que `GH_TOKEN`, quando ele não está definido. Só vai para `api.github.com`; o `login` nunca o repassa ao Runtime.",
    "GEMINI_API_KEY": "Chave da API Gemini (TTS, provider `gemini`; adaptador `gemini` do `swap`). Só no ambiente; nunca no repo.",
    "HYPERFRAMES_BROWSER_PATH": "Chrome headless que o HyperFrames usa na captura. Definido pelo render remoto.",
    "HYPERFRAMES_FFMPEG_PATH": "ffmpeg que o HyperFrames usa. Definido pelo render remoto.",
    "HYPERFRAMES_FFPROBE_PATH": "ffprobe que o HyperFrames usa. Definido pelo render remoto.",
    "KAGGLE_CONFIG_DIR": "Pasta do `kaggle.json` (padrão: `~/.kaggle`).",
    "KAGGLE_USERNAME": "Usuário do Kaggle para o render remoto (sem ele, lê o `kaggle.json`).",
    "KOKORO_DIR": "Pasta dos modelos do Kokoro (TTS local; padrão `~/.local/share/simplicio-tts`).",
    "MONEYPRINTER_DATA_DIR": "Pasta de dados da trilha MoneyPrinterTurbo: venv isolado e storage com os vídeos gerados (padrão: `~/.simplicio-video/moneyprinter-data`, fora do checkout).",
    "MONEYPRINTER_DIR": "Checkout do MoneyPrinterTurbo (alternativa a `SIMPLICIO_TOOLS_DIR/moneyprinter`).",
    "MATCHCUT_DIR": "Checkout do match-cut (alternativa a `SIMPLICIO_TOOLS_DIR/matchcut`).",
    "OPENCUT_DIR": "Pasta do OpenCut, lida pelo próprio editor (trilha `opencut`).",
    "OPENVERSE_CLIENT_ID": "Credencial OAuth2 opcional da API do Openverse (par com `OPENVERSE_CLIENT_SECRET`; sobe o limite de requisições e o tamanho da página). Só no ambiente; nunca em argumento, índice, cache ou saída.",
    "OPENVERSE_CLIENT_SECRET": "Segredo OAuth2 opcional da API do Openverse (par com `OPENVERSE_CLIENT_ID`). Só no ambiente; nunca em argumento, índice, cache ou saída.",
    "OPENVERSE_LIBRARY_DIR": "Pasta da biblioteca do Openverse: `index.json`, `files/<sha256>`, `cache/` e `sheets/` (padrão: `~/.simplicio-video/openverse-library`).",
    "OPENMONTAGE_DIR": "Pasta do OpenMontage (trilha `montage`). Também lida pelo OpenMontage.",
    "OPENVOICE_CHECKPOINTS": "Pasta dos checkpoints do OpenVoice (provider `openvoice`).",
    "OPENVOICE_PY": "Python com o OpenVoice instalado (provider `openvoice`).",
    "PATH": "Lista de pastas de executáveis do sistema. Lida, não configurada pelo produto. O `login` e o `doctor` procuram `simplicio`, `node` e `ffmpeg` só nas pastas absolutas dela, nunca no diretório atual.",
    "PATHEXT": "Extensões executáveis do Windows (`.EXE;.CMD`...). Lida só no Windows, ao procurar `simplicio`, `node`, `ffmpeg` e `npm` no PATH.",
    "PIP_BREAK_SYSTEM_PACKAGES": "`1` autoriza o pip a mexer no Python do sistema (PEP 668). O `update` de um pacote instalado por pip respeita: sem ele, um Python gerenciado pelo sistema é recusado com exit 2.",
    "SIMPLICIO_AUTH_FILE": "Arquivo de login compartilhado com o Simplicio Runtime (padrão: `~/.simplicio/login.json`). Lido por `login`, `logout`, `auth status` e `doctor`; o motor não grava credencial nem lê o token. Mesmo nome que o Runtime lê.",
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
    "SIMPLICIO_VIDEO_DATA": "Pasta de dados do simplicio-video (padrão: `~/.simplicio-video`). Lida pelas trilhas `montage`, `toonflow` e `moneyprinter`, pelo `jobs` (estado das tarefas em `jobs/`), pelo `busca` (cache, contador e registro em `busca/`) e pelo `update` (`update-check.json`, que o `doctor` lê sem rede).",
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


def _help(args: list[str]) -> str:
    env = {
        "PATH": os.environ.get("PATH", ""),
        "PYTHONPATH": str(SRC),
        "SIMPLICIO_OFFLINE": "1",
        "LANG": "C.UTF-8",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONIOENCODING": "utf-8",
    }
    result = subprocess.run(
        [sys.executable, "-m", "simplicio_video", *args, "--help"],
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


def env_reads() -> dict[str, list[str]]:
    """Environment variable names read (or set) by the package, found by ast, with `arquivo:linha` locations."""
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


def block_body(section: str) -> str:
    pages = sorted(
        (p for p in SECTION_DIRS[section].glob("*.md") if p.name != "README.md"),
        key=lambda p: p.relative_to(ROOT).as_posix(),
    )
    note = f"Gerado de `docs/{section}/*.md` (front matter). Não edite aqui: rode `make regen`."
    if not pages:
        return f"{note}\n\nAinda não há páginas em `docs/{section}/`."
    items = []
    for page in pages:
        meta = _front_matter(page)
        items.append(f"- [{meta['title']}]({page.relative_to(ROOT).as_posix()}): {meta['summary']}")
    return f"{note}\n\n" + "\n".join(items)


def updated_block_text(text: str, path: Path) -> str:
    for section in SECTION_DIRS:
        pattern = re.compile(
            rf"(<!-- BEGIN GENERATED: {section} -->\n).*?(<!-- END GENERATED -->)", re.S
        )
        matches = pattern.findall(text)
        if len(matches) != 1:
            raise SystemExit(f"gen_reference: {path.relative_to(ROOT).as_posix()} precisa de exatamente um bloco '{section}'")
        body = block_body(section)
        text = pattern.sub(lambda m: m.group(1) + body + "\n" + m.group(2), text, count=1)
    return text


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Gera docs/reference/ a partir do código e atualiza os blocos GENERATED do README.md e do AGENTS.md.",
        epilog="exemplos:\n  scripts/gen_reference.py --out docs/reference\n  scripts/gen_reference.py --out docs/reference --check",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--out", required=True, type=Path, help="pasta de saída (ex.: docs/reference)")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="não grava; sai com 1 se algo estiver desatualizado")
    mode.add_argument("--update-blocks", action="store_true", help="grava a pasta e reescreve os blocos do README e do AGENTS")
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
        if stale:
            print("gen_reference: desatualizado (rode make regen):")
            for item in stale:
                print(f"  {item}")
            return 1
        print("gen_reference: ok (docs/reference e blocos em dia)")
        return 0

    out.mkdir(parents=True, exist_ok=True)
    for name, text in files.items():
        (out / name).write_text(text, encoding="utf-8")
    if args.update_blocks:
        for path in BLOCK_FILES:
            text = path.read_text(encoding="utf-8")
            path.write_text(updated_block_text(text, path), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
