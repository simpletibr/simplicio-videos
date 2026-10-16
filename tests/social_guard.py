"""Auxiliares dos testes de fronteira do `social`: nada daqui lê o `providers.json` para decidir o que é seguro.

Duas coisas independentes do código e dos dados em teste:

- `violacoes_de_codigo`: varredura AST do módulo, que pega os caminhos de burla de um teste de import ingênuo
  (importação dinâmica, `__import__`, `importlib`, `getattr(os, "environ")`, import relativo, `from os import environ`,
  processo fora do ffprobe, `exec`/`eval`).
- `conferir_sequencia_completa`: confere a sequência COMPLETA de passos com listas FIXAS de ferramentas (as de publicar, a
  que expõe o MP4 e a de cotar), sem consultar o `providers.json` carregado, e com o `requires` de cada passo.
"""
from __future__ import annotations

import ast

PUBLICAR_FIXO = {"ro_confirm_publishing", "posts_create", "posts_cross_post", "posts_publish_now", "queue_get_next_queue_slot", "call_tool"}
EXPOR_FIXO = {"media_generate_upload_link"}  # deixa o MP4 com URL pública: só depois do sim
PASSOS_MANUAIS_DEPOIS_DO_SIM = {"put"}
COTAR_FIXO = {"realoficial": {"ro_preview_publication"}, "zernio": set()}

SEQUENCIA_ESPERADA = {
    "realoficial": {"modelo": ["clip", "check", "accounts", "tiktok_options", "preview", "show", "consent", "confirm", "verify"],
                    "com_tiktok": ["check", "accounts", "tiktok_options", "preview", "show", "consent", "confirm", "verify"],
                    "sem_tiktok": ["check", "accounts", "preview", "show", "consent", "confirm", "verify"]},
    "zernio": {"modelo": ["check", "accounts", "show", "consent", "upload", "put", "post", "verify"],
               "com_tiktok": ["check", "accounts", "show", "consent", "upload", "put", "post", "verify"],
               "sem_tiktok": ["check", "accounts", "show", "consent", "upload", "put", "post", "verify"]},
}

MODULOS_PROIBIDOS = {"socket", "ssl", "urllib", "http", "requests", "httpx", "aiohttp", "websockets", "ftplib", "smtplib", "imaplib",
                     "poplib", "telnetlib", "xmlrpc", "socketserver", "selectors", "asyncio", "mcp", "playwright", "selenium",
                     "importlib", "pkgutil", "runpy", "ctypes", "multiprocessing", "webbrowser", "pty"}
RELATIVOS_PERMITIDOS = {"paths"}
NOMES_PROIBIDOS = {"__import__", "environ", "environb", "getenv", "exec", "eval", "Popen", "system", "popen"}
TEXTOS_PROIBIDOS = NOMES_PROIBIDOS | MODULOS_PROIBIDOS
PREFIXOS_OS_PROIBIDOS = ("exec", "spawn", "fork", "system", "popen", "posix_spawn", "startfile")


def violacoes_de_codigo(src: str) -> list[str]:
    out: list[str] = []
    for n in ast.walk(ast.parse(src)):
        if isinstance(n, ast.Import):
            out += [f"import {a.name}" for a in n.names if a.name.split(".")[0] in MODULOS_PROIBIDOS]
        elif isinstance(n, ast.ImportFrom):
            top = (n.module or "").split(".")[0]
            if n.level:
                alvos = [top] if top else [a.name for a in n.names]
                out += [f"import relativo {a}" for a in alvos if a not in RELATIVOS_PERMITIDOS]
            elif top in MODULOS_PROIBIDOS:
                out.append(f"from {n.module} import ...")
            elif top == "subprocess":
                out += [f"from subprocess import {a.name}" for a in n.names if a.name != "run"]
            elif top == "os":
                out += [f"from os import {a.name}" for a in n.names if a.name in NOMES_PROIBIDOS or a.name.startswith(PREFIXOS_OS_PROIBIDOS)]
        elif isinstance(n, ast.Name) and n.id in NOMES_PROIBIDOS:
            out.append(f"nome {n.id}")
        elif isinstance(n, ast.Attribute):
            if n.attr in NOMES_PROIBIDOS:
                out.append(f"atributo {n.attr}")
            if isinstance(n.value, ast.Name) and n.value.id == "os" and n.attr.startswith(PREFIXOS_OS_PROIBIDOS):
                out.append(f"os.{n.attr}")
            if isinstance(n.value, ast.Name) and n.value.id == "subprocess" and n.attr != "run":
                out.append(f"subprocess.{n.attr}")
        elif isinstance(n, ast.Constant) and isinstance(n.value, str) and n.value in TEXTOS_PROIBIDOS:
            out.append(f"texto {n.value!r} (getattr/importação por nome)")
    return out


def sequencia_de_ids(steps, provedor) -> list[str]:
    return [s["id"] for s in steps]


def conferir_sequencia_completa(steps, provedor) -> None:
    """Falha (AssertionError) se qualquer chamada de publicar ou de expor o MP4, ou o passo manual de envio, vier antes de
    cotar -> mostrar -> consentimento, ou se não declarar `requires: consent` apontando para o passo do consentimento."""
    ids = [s["id"] for s in steps]
    assert len(ids) == len(set(ids)), "ids de passo repetidos"
    kinds = [s["kind"] for s in steps]
    assert "show" in kinds and "consent" in kinds, "faltam as etapas de mostrar e de consentimento"
    gated = [i for i, s in enumerate(steps) if (s["kind"] == "call" and s["tool"] in PUBLICAR_FIXO | EXPOR_FIXO)
             or s["id"] in PASSOS_MANUAIS_DEPOIS_DO_SIM]
    assert any(s["kind"] == "call" and s["tool"] in PUBLICAR_FIXO for s in steps), "a receita precisa terminar numa chamada de publicar"
    for i in gated:
        s = steps[i]
        nome = s.get("tool") or s["id"]
        consentimentos = [j for j in range(i) if kinds[j] == "consent"]
        assert consentimentos, f"{nome} antes do consentimento"
        c = consentimentos[-1]
        mostrar = [j for j in range(c) if kinds[j] == "show"]
        assert mostrar, f"{nome}: o consentimento vem sem mostrar nada antes"
        assert s.get("requires") == "consent", f"{nome} sem requires: consent"
        assert s.get("requires_step") == steps[c]["n"], f"{nome}: requires_step não aponta para o consentimento"
        if s["kind"] == "call" and s["tool"] in PUBLICAR_FIXO:
            for q in COTAR_FIXO[provedor]:
                assert any(x["kind"] == "call" and x["tool"] == q for x in steps[:mostrar[-1]]), f"{nome} sem cotar ({q}) antes de mostrar"
