"""OpenCut track: open-source video editor for manual finishing (MIT).

The pin in tools.py is opencut-classic (https://github.com/OpenCut-app/opencut-classic, archived upstream): the rewrite in
OpenCut-app/OpenCut has no headless/MCP yet. The deterministic render stays in `render`; OpenCut is the human-in-the-loop
editor for touching up an MP4 the CLI produced.
"""
from __future__ import annotations

import json
import os
import secrets
import shutil
import socket
import subprocess
from pathlib import Path

from . import tools

OPENCUT_REPO = tools.get("opencut").source
PORT = 3000
LOOPBACK = "127.0.0.1"
LAN_FLAG = "--lan"
ENV_FILE = "apps/web/.env.local"
ENV_EXAMPLE = "apps/web/.env.example"

# apps/web/src/env/web.ts parses these with zod at import time (src/app/layout.tsx imports it), so a missing one is a 500
# on every page. The values are inert placeholders: nothing listens on them and no account is involved.
ENV_DEFAULTS = {
    "NODE_ENV": "development",
    "NEXT_PUBLIC_SITE_URL": f"http://localhost:{PORT}",
    "NEXT_PUBLIC_MARBLE_API_URL": "https://api.marblecms.com",
    "DATABASE_URL": "postgresql://opencut:opencut@localhost:5432/opencut",
    "BETTER_AUTH_SECRET": "",  # always random, see _env_text
    "UPSTASH_REDIS_REST_URL": "http://localhost:8079",
    "UPSTASH_REDIS_REST_TOKEN": "example_token",
    "MARBLE_WORKSPACE_KEY": "placeholder",
    "FREESOUND_CLIENT_ID": "placeholder",
    "FREESOUND_API_KEY": "placeholder",
}

USAGE = (
    f"OpenCut ({OPENCUT_REPO}, MIT; opencut-classic, arquivado no upstream: o rewrite ainda não tem API)\n"
    "  simplicio-video opencut clone [dir]   # clona o editor no commit fixado\n"
    f"  simplicio-video opencut dev [{LAN_FLAG}]   # bun install + next dev (apps/web) em http://{LOOPBACK}:{PORT}\n"
    "  simplicio-video opencut status [--json]   # checkout, pin, bun, node_modules, .env.local, porta\n"
    "  simplicio-video opencut where         # imprime o checkout (OPENCUT_DIR)\n"
    f"dev escuta só em {LOOPBACK}; {LAN_FLAG} abre em 0.0.0.0 (a rede toda alcança o editor, sem login na frente).\n"
    f"Na primeira vez dev cria {ENV_FILE} (modo 0600) a partir de .env.example com valores locais de mentira e um\n"
    "BETTER_AUTH_SECRET aleatório; nunca sobrescreve um .env.local existente.\n"
    "O editor (/editor/<id>) roda no navegador e guarda projetos no IndexedDB: abrir não precisa de Postgres nem de Redis.\n"
    "Precisam de serviços reais só login/conta (Postgres em DATABASE_URL e Redis HTTP em UPSTASH_REDIS_REST_URL; o docker-compose.yml\n"
    "do checkout traz db, redis e serverless-redis-http), a busca de sons (FREESOUND_*) e o blog (NEXT_PUBLIC_MARBLE_API_URL, rede).\n"
)


class OpenCutError(Exception):
    pass


def find_opencut_dir() -> Path | None:
    return tools.find("opencut")


def clone_opencut(target: Path | None = None) -> Path:
    if target is not None:
        os.environ["OPENCUT_DIR"] = str(Path(target).expanduser())
    try:
        return Path(tools.install("opencut"))
    except tools.ToolError as e:
        raise OpenCutError(str(e)) from None


def _port_free(port: int, host: str = LOOPBACK) -> bool:
    """True when nothing accepts connections on host:port (a server on 0.0.0.0 answers on loopback too)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) != 0


def _env_text(example: Path) -> str:
    """Contents of a new .env.local: the example's own lines, the secret replaced by a random one, the required keys the
    example lacks filled with placeholders."""
    lines = example.read_text(encoding="utf-8").splitlines() if example.is_file() else []
    seen: set[str] = set()
    out: list[str] = []
    for line in lines:
        key, sep, _ = line.partition("=")
        key = key.strip()
        if sep and key in ENV_DEFAULTS:
            seen.add(key)
            if key == "BETTER_AUTH_SECRET":
                line = f"BETTER_AUTH_SECRET={secrets.token_hex(32)}"
        out.append(line)
    for key, value in ENV_DEFAULTS.items():
        if key not in seen:
            out.append(f"{key}={secrets.token_hex(32) if key == 'BETTER_AUTH_SECRET' else value}")
    header = "# Criado por `simplicio-video opencut dev`: valores locais de mentira. Pode editar; nunca é sobrescrito.\n"
    return header + "\n".join(out) + "\n"


def ensure_env_local(d: Path) -> bool:
    """Create apps/web/.env.local (0600) when missing. Never overwrites (O_EXCL). Returns True when it created the file."""
    path = d / ENV_FILE
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return False
    except OSError as e:
        raise OpenCutError(f"não consegui criar {path}: {e.strerror}") from None
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(_env_text(d / ENV_EXAMPLE))
    return True


def _dev_steps(d: Path, args: list[str]) -> list[tuple[list[str], Path]]:
    """Validate the flags, create .env.local, announce the address and return the commands dev runs, in order."""
    extra = [a for a in args if a != LAN_FLAG]
    if extra:
        raise OpenCutError(f"dev aceita só {LAN_FLAG} (a porta é {PORT}); recebi: {' '.join(extra)}")
    lan = LAN_FLAG in args
    bun = shutil.which("bun")
    if not bun:
        raise OpenCutError("bun não encontrado (https://bun.sh).")
    if ensure_env_local(d):
        print(f"opencut: criei {d / ENV_FILE} (0600) com valores locais de mentira e um BETTER_AUTH_SECRET aleatório.")
    host = "0.0.0.0" if lan else LOOPBACK
    if lan:
        print(f"opencut: {LAN_FLAG}: escutando em 0.0.0.0:{PORT}, a rede toda alcança o editor.")
    print(f"OpenCut em http://{LOOPBACK if not lan else 'localhost'}:{PORT} (config: {d / ENV_FILE}). Ctrl+C para parar.")
    # `next dev` straight from apps/web (what `turbo run dev --filter=@opencut/web` runs): turbo rejects --hostname, and bun
    # strips the `--` that would pass it through.
    return [([bun, "install"], d), ([bun, "run", "dev", "--hostname", host], d / "apps" / "web")]


def status() -> dict:
    d = find_opencut_dir()
    pin = tools.pinned_ref(tools.get("opencut"))
    head = None
    if d is not None:
        try:
            head = tools._git("rev-parse", "HEAD", cwd=d)
        except tools.ToolError:
            head = None
    return {
        "checkout": str(d) if d else None,
        "pin": pin,
        "head": head,
        "pin_match": bool(head) and head == pin,
        "bun": shutil.which("bun") is not None,
        "node_modules": d is not None and (d / "node_modules").is_dir(),
        "env_local": d is not None and (d / ENV_FILE).is_file(),
        "port": PORT,
        "port_free": _port_free(PORT),
    }


def _status(args: list[str]) -> int:
    if [a for a in args if a != "--json"]:
        raise OpenCutError("status aceita só --json")
    s = status()
    if "--json" in args:
        print(json.dumps(s, ensure_ascii=False, indent=2))
        return 0

    def yn(v: bool) -> str:
        return "sim" if v else "não"

    print(f"checkout:     {s['checkout'] or 'não encontrado (rode `simplicio-video opencut clone`)'}")
    print(f"pin:          {s['pin'][:12]}  head: {(s['head'] or '?')[:12]}  confere: {yn(s['pin_match'])}")
    print(f"bun:          {yn(s['bun'])}")
    print(f"node_modules: {yn(s['node_modules'])}")
    print(f".env.local:   {yn(s['env_local'])} (os valores não são mostrados)")
    print(f"porta {s['port']}:   {'livre' if s['port_free'] else 'em uso'}")
    return 0


def run_opencut(args: list[str]) -> int:
    first = args[0] if args else "help"
    if first in ("-h", "--help", "help"):
        print(USAGE)
        return 0
    if first == "clone":
        print(clone_opencut(Path(args[1]) if len(args) > 1 else None))
        return 0
    if first == "status":
        return _status(args[1:])
    if first not in ("dev", "where"):
        raise OpenCutError(f"subcomando desconhecido: {first} (clone|dev|status|where)")
    d = find_opencut_dir()
    if d is None:
        raise OpenCutError("OpenCut não encontrado: rode `simplicio-video opencut clone` ou defina OPENCUT_DIR.")
    if first == "where":
        print(d)
        return 0
    # dev never ends and the MCP refuses it, so these calls stay bare (tests/test_childio.py allowlist).
    (install, install_cwd), (serve, serve_cwd) = _dev_steps(d, args[1:])
    if subprocess.call(install, cwd=install_cwd) != 0:
        return 1
    return subprocess.call(serve, cwd=serve_cwd)
