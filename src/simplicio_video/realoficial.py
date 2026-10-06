"""Real Oficial track: MCP remoto (https://api.realoficial.com.br/mcp) for scheduling and low-cost image/video generation.

The service does not expose those tools yet; this track only wires the MCP server so agents can use it as soon
as it ships. Generated media never enters the deterministic `render` unless it is a contract asset file.
"""
from __future__ import annotations

import json
import shutil

REALOFICIAL_MCP_URL = "https://api.realoficial.com.br/mcp"

MCP_CONFIG = {"mcpServers": {"realoficial": {"command": "npx", "args": ["-y", "mcp-remote", REALOFICIAL_MCP_URL]}}}


class RealOficialError(Exception):
    pass


def run_realoficial(args: list[str]) -> int:
    first = args[0] if args else "config"
    if first in ("-h", "--help", "help"):
        print(f"Real Oficial MCP ({REALOFICIAL_MCP_URL})\n  simplicio-video realoficial config   # JSON para o cliente MCP (Claude/Cursor/...)\n"
              "  simplicio-video realoficial check    # confere npx e lista a URL do MCP")
        return 0
    if first == "config":
        print(json.dumps(MCP_CONFIG, indent=2))
        return 0
    if first == "check":
        if not shutil.which("npx"):
            raise RealOficialError("npx não encontrado no PATH (necessário para mcp-remote).")
        print(f"ok: npx presente; MCP em {REALOFICIAL_MCP_URL} (agendamento, imagem e vídeo: em breve)")
        return 0
    raise RealOficialError(f"subcomando desconhecido: {first} (config|check)")
