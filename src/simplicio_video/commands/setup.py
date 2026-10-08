"""`simplicio-video setup [--yes] [--theme ID] [--lang IDIOMA] [--force] [--realoficial]` (issue #43).

Wizard da primeira execução. Cria o workspace ($SIMPLICIO_WORKSPACE, padrão ~/.simplicio-video/workspaces/default)
com workspace.yaml (tema, idioma) e policy.yaml (autonomia L1; orçamentos de tokens, USD e créditos em zero).
--yes aceita os padrões sem perguntar. O setup não faz login e não grava credencial: tudo fica dentro do workspace.

Exemplos:
  simplicio-video setup
  simplicio-video setup --yes --theme br --lang pt-BR
  simplicio-video setup --yes --realoficial
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import yaml

from ..realoficial import REALOFICIAL_MCP_URL

WS_SCHEMA = "simplicio.workspace/v1"
WS_LAYOUT = "factory/v1"
POL_SCHEMA = "simplicio.policy/v1"
TEMA_PADRAO = "br"
IDIOMA_PADRAO = "pt-BR"
FUSO_PADRAO = "America/Sao_Paulo"


def workspace_dir() -> Path:
    """$SIMPLICIO_WORKSPACE ou ~/.simplicio-video/workspaces/default (docs/factory/contracts.md)."""
    env = os.environ.get("SIMPLICIO_WORKSPACE")
    if env:
        return Path(env).expanduser()
    return Path.home() / ".simplicio-video" / "workspaces" / "default"


def _pergunta(rotulo: str, padrao: str) -> str:
    try:
        resp = input(f"{rotulo} [{padrao}]: ").strip()
    except EOFError:
        resp = ""
    return resp or padrao


def _grava(caminho: Path, dados: dict) -> None:
    """Escrita atômica: arquivo temporário ao lado e troca por os.replace."""
    caminho.parent.mkdir(parents=True, exist_ok=True)
    tmp = caminho.with_name(caminho.name + ".tmp")
    tmp.write_text(yaml.safe_dump(dados, allow_unicode=True, sort_keys=False), encoding="utf8")
    os.replace(tmp, caminho)


def run(a) -> int:
    ws = workspace_dir()
    if (ws / "workspace.yaml").is_file() and not a.force:
        print(f"workspace já existe em {ws}: nada foi alterado.\n"
              "  para regravar workspace.yaml e policy.yaml: simplicio-video setup --force\n"
              "  próximo passo: simplicio-video doctor")
        return 0
    tema = a.theme or TEMA_PADRAO
    idioma = a.lang or IDIOMA_PADRAO
    if not a.yes:
        if not sys.stdin.isatty():
            print("setup: sem terminal interativo. Use --yes (aceita os padrões) ou passe --theme e --lang.",
                  file=sys.stderr)
            return 2
        tema = _pergunta("Tema visual", tema)
        idioma = _pergunta("Idioma do conteúdo", idioma)
    (ws / "logs").mkdir(parents=True, exist_ok=True)
    _grava(ws / "workspace.yaml", {
        "schema": WS_SCHEMA, "workspace": WS_LAYOUT, "name": "default", "language": idioma,
        "timezone": FUSO_PADRAO, "settings": {"theme": tema, "ui_language": idioma}})
    _grava(ws / "policy.yaml", {
        "schema": POL_SCHEMA, "autonomy": {"default": "L1"},
        "budgets": {"llm_tokens": 0, "llm_usd": 0, "media_credits": 0}})
    print(f"workspace criado em {ws}\n"
          f"  tema: {tema} · idioma: {idioma} · autonomia: L1 · orçamentos de tokens, USD e créditos: zero\n"
          "  próximo passo: simplicio-video doctor")
    if a.realoficial:
        print(f"Real Oficial: o MCP é {REALOFICIAL_MCP_URL}. Adicione essa URL no seu cliente MCP e entre com OAuth "
              "(docs/realoficial.md). O setup não guarda token.")
    return 0
