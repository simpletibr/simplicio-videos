"""Real Oficial track: MCP remoto (https://api.realoficial.com.br/mcp) for scheduling/publishing and AI image/video generation.

This track wires the MCP server (OAuth login in the client; 49 tools, see docs/realoficial.md). Generated media never
enters the deterministic `render` unless it is copied in as a contract asset file.
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
        print(f"ok: npx presente; MCP em {REALOFICIAL_MCP_URL} (OAuth login in your MCP client; tools: docs/realoficial.md)")
        return 0
    raise RealOficialError(f"subcomando desconhecido: {first} (config|check)")
