#!/usr/bin/env python3
"""Smoke só de leitura das trilhas externas e do núcleo do simplicio-video.

Para cada trilha de src/simplicio_video/tools.py (TOOLS) roda, pelo CLI e pelo MCP (in-process), só comandos de leitura:
  - `<comando> --help`: sempre (não precisa da trilha instalada);
  - `<comando> where` e `<comando> status`: quando o --help lista o subcomando (o script lê o próprio --help);
  - a função `video_*` do MCP com argumentos de leitura (`where`, `status`, `--help`).
No núcleo: `doctor --json`, `status --json`, `list templates`, `validate` do tests/fixtures/mini e a lista de tools do
servidor MCP (o SDK monta a lista em memória; nenhum processo de servidor sobe).

Não instala, não clona, não baixa, não sobe servidor e não gasta. Trilha sem checkout (ou sem o binário, no npm) vira SKIP
"não instalado"; subcomando que o --help não lista vira SKIP "subcomando ausente" (recurso que ainda não chegou não é falha).
Cada chamada tem 30 s. Os processos filhos recebem SIMPLICIO_OFFLINE=1 (o motor recusa rede); as chamadas MCP recebem
também SIMPLICIO_MCP=1 (marca de quem chama; o motor não lê essa variável hoje).

Uso:
  .venv/bin/python scripts/smoke_trilhas.py          tabela (trilha | checagem | estado | detalhe)
  .venv/bin/python scripts/smoke_trilhas.py --json   só o JSON (simplicio.smoke-trilhas/v1) no stdout

Sai com 0 se nenhuma checagem deu FAIL e com 1 se alguma deu FAIL (SKIP não reprova).

Exemplos:
  bash scripts/dev_install.sh --with test,mcp
  .venv/bin/python scripts/smoke_trilhas.py
  .venv/bin/python scripts/smoke_trilhas.py --json > smoke-trilhas.json
"""
from __future__ import annotations

import argparse
import asyncio
import contextlib
import io
import json
import os
import platform
import re
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCHEMA = "simplicio.smoke-trilhas/v1"
TIMEOUT_S = 30
DETALHE_MAX = 90
FIXTURE = REPO / "tests" / "fixtures" / "mini" / "contract.yaml"
OK, FAIL, SKIP = "OK", "FAIL", "SKIP"
NAO_INSTALADO = "não instalado"
APP_FECHADO = "não consegui falar"  # VoiceStudio's answer while its app is closed: a state of the machine, not a broken command

try:
    from simplicio_video import mcp_server, tools
except ImportError as exc:
    print(f"smoke_trilhas: o pacote simplicio_video não importa ({exc}).\n"
          "Rode com o venv deste checkout: bash scripts/dev_install.sh --with test,mcp", file=sys.stderr)
    raise SystemExit(2) from exc


@dataclass
class Resultado:
    trilha: str
    checagem: str
    estado: str            # OK | FAIL | SKIP
    detalhe: str = ""
    via: str = "core"      # core | cli | mcp
    comando: str = ""      # what was run, for people and for the JSON
    segundos: float = 0.0


@dataclass
class Saida:
    rc: int
    out: str = ""
    err: str = ""
    timeout: bool = False
    segundos: float = 0.0

    @property
    def texto(self) -> str:
        return f"{self.out}\n{self.err}".strip()


@dataclass(frozen=True)
class ChamadaMcp:
    funcao: str            # a video_* function of mcp_server
    kwargs: dict           # read-only arguments only
    precisa: bool          # reads the checkout: runs only when the track is installed
    espera: str = "ok"     # "ok": the answer has ok true; "recusa": must refuse (fetch with no URL, nothing downloaded)


# The read-only MCP call of each track, keyed by the registry names of tools.py (TOOLS).
MCP_LEITURA: dict[str, ChamadaMcp] = {
    "openmontage": ChamadaMcp("video_montage", {"args": "--help"}, precisa=False),
    "opencut": ChamadaMcp("video_opencut", {"args": "where"}, precisa=True),
    "hypit": ChamadaMcp("video_clone", {"args": "--help"}, precisa=False),
    "toonflow": ChamadaMcp("video_toonflow", {"args": "where"}, precisa=True),
    "moneyprinter": ChamadaMcp("video_moneyprinter", {"args": "status"}, precisa=True),
    "matchcut": ChamadaMcp("video_matchcut", {"args": "status"}, precisa=True),
    "instagram": ChamadaMcp("video_instagram", {"acao": "status"}, precisa=True),
    "voicestudio": ChamadaMcp("video_voicestudio", {"args": "status"}, precisa=False),
    "video-use": ChamadaMcp("video_edit", {"args": "--help"}, precisa=False),
    "tinyfish": ChamadaMcp("video_busca", {"acao": "status"}, precisa=True),
    "yt-dlp": ChamadaMcp("video_media", {"args": ["fetch"]}, precisa=False, espera="recusa"),
    "rea_video": ChamadaMcp("video_rea_video", {"args": "where"}, precisa=True),
}

# A subcommand that must refuse without its arguments (checked with no URL, so nothing is downloaded).
CLI_RECUSA = {"yt-dlp": "fetch"}

# Desktop apps: their status asks the app over its local API, so it runs even with no checkout here. The app decides the answer
# (OK when it answers, SKIP "app fechado" when it does not); a missing checkout is not a reason to skip the question.
APP_LOCAL = {"voicestudio"}


# ---------------------------------------------------------------- running the CLI and the MCP functions

def _comando_cli() -> list[str]:
    """The `simplicio-video` of this interpreter (the venv's); `python -m simplicio_video` when it is not beside it."""
    for nome in ("simplicio-video", "simplicio-video.exe"):
        candidato = Path(sys.executable).parent / nome
        if candidato.is_file():
            return [str(candidato)]
    return [sys.executable, "-m", "simplicio_video"]


def _matar_arvore(proc: subprocess.Popen) -> None:
    """Kills the child and everything it started: on POSIX its whole process group (it was started in a new session)."""
    try:
        if os.name == "posix":
            os.killpg(proc.pid, signal.SIGKILL)
        else:
            proc.kill()
    except OSError:
        pass  # the group already ended


def _rodar_cli(argv: list[str]) -> Saida:
    """One command of the CLI as a child process, with a 30 s limit. The child runs offline (SIMPLICIO_OFFLINE=1). On timeout
    the child's whole process group is killed, so a grandchild that holds the pipes does not outlive the check."""
    inicio = time.monotonic()
    env = {**os.environ, "SIMPLICIO_OFFLINE": "1"}
    try:
        proc = subprocess.Popen([*_comando_cli(), *argv], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                encoding="utf-8", errors="replace", env=env, cwd=str(REPO),
                                start_new_session=os.name == "posix")
    except OSError as exc:
        return Saida(127, "", str(exc), segundos=time.monotonic() - inicio)
    try:
        out, err = proc.communicate(timeout=TIMEOUT_S)
    except subprocess.TimeoutExpired:
        _matar_arvore(proc)
        try:
            out, err = proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            out, err = "", ""  # a pipe is still held by a process that left the group: give up on its output
        return Saida(124, out or "", f"sem resposta em {TIMEOUT_S} s", timeout=True, segundos=time.monotonic() - inicio)
    return Saida(proc.returncode, out or "", err or "", segundos=time.monotonic() - inicio)


@contextlib.contextmanager
def _ambiente_mcp():
    """The variables an in-process MCP call runs with; the previous values come back afterwards."""
    novos = {"SIMPLICIO_OFFLINE": "1", "SIMPLICIO_MCP": "1"}
    antigos = {k: os.environ.get(k) for k in novos}
    os.environ.update(novos)
    try:
        yield
    finally:
        for k, valor in antigos.items():
            if valor is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = valor


def _com_limite(fn) -> tuple[object, str]:
    """Runs fn() in a daemon thread with a TIMEOUT_S limit, with the MCP environment. Returns (value, "") or (None, reason).

    A call that never ends can stay inside contextlib.redirect_stdout/redirect_stderr (as the CLI wrapper of mcp_server does),
    which points sys.stdout at an abandoned buffer: on timeout both streams and the environment come back as they were, so the
    table and the JSON still reach the terminal. The thread itself is a daemon and is left behind."""
    stdout, stderr = sys.stdout, sys.stderr
    caixa: dict = {}

    def alvo():
        try:
            caixa["valor"] = fn()
        except Exception as exc:  # noqa: BLE001 - the check reports the failure and the script goes on
            caixa["erro"] = f"{type(exc).__name__}: {exc}"

    with _ambiente_mcp():
        fio = threading.Thread(target=alvo, daemon=True)
        fio.start()
        fio.join(TIMEOUT_S)
    if fio.is_alive():
        sys.stdout, sys.stderr = stdout, stderr
        return None, f"sem resposta em {TIMEOUT_S} s"
    if "erro" in caixa:
        return None, caixa["erro"]
    return caixa.get("valor"), ""


def _chamar_mcp(funcao: str, kwargs: dict) -> tuple[dict | None, str]:
    """One video_* function of mcp_server, in-process, with a 30 s limit. Returns (answer, "") or (None, reason).

    Some tools print their message to stderr instead of the log (VoiceStudio's "app fechado"): that text is taken as the
    log when the answer has none, so the check can still read it."""
    fn = getattr(mcp_server, funcao)
    erro_saida = io.StringIO()

    def chamada():
        with contextlib.redirect_stderr(erro_saida):
            return fn(**kwargs)

    resposta, erro = _com_limite(chamada)
    if erro:
        return None, erro
    if not isinstance(resposta, dict):
        return None, f"resposta inesperada: {type(resposta).__name__}"
    if not resposta.get("log") and erro_saida.getvalue().strip():
        resposta = {**resposta, "log": erro_saida.getvalue().strip()}
    return resposta, ""


# ---------------------------------------------------------------- reading the output

def subcomandos(ajuda: str) -> set[str]:
    """The subcommands listed in the `args` line of a track's --help ("clone [dir] | dev | where"). Empty when that line
    lists none, e.g. a free text that describes the upstream's own arguments."""
    linhas = ajuda.splitlines()
    for i, linha in enumerate(linhas):
        casa = re.match(r"^\s{2}args\s+(.*)$", linha)
        if not casa:
            continue
        partes = [casa.group(1).strip()]
        for seguinte in linhas[i + 1:]:
            if not seguinte.startswith(" " * 10) or not seguinte.strip():
                break  # argparse indents the continuation lines of a long help; a blank line ends the block
            partes.append(seguinte.strip())
        texto = " ".join(partes)
        if "|" not in texto:
            return set()
        nomes = set()
        for segmento in texto.split("|"):
            nome = re.match(r"\s*([a-z][a-z0-9-]*)", segmento)
            if nome:
                nomes.add(nome.group(1))
        return nomes
    return set()


def _curto(texto: str, limite: int = DETALHE_MAX) -> str:
    unico = " ".join(str(texto).split())
    return unico if len(unico) <= limite else unico[: limite - 3] + "..."


def _resumo(texto: str) -> str:
    """The last non-empty line of a message: where a failed command ends."""
    linhas = [linha for linha in texto.splitlines() if linha.strip()]
    return linhas[-1].strip() if linhas else "sem saída"


def _primeira_linha(texto: str) -> str:
    linhas = [linha.strip() for linha in texto.splitlines() if linha.strip()]
    return linhas[0] if linhas else ""


def _json(texto: str):
    try:
        return json.loads(texto)
    except (ValueError, TypeError):
        return None


def _recusa_json(texto: str) -> bool:
    """True when the command has no --json (it answers `... não recebe argumentos; argumento a mais: --json`)."""
    return "não recebe argumentos" in texto or "argumento a mais" in texto


# ---------------------------------------------------------------- the checks of a track

def _checar_ajuda(nome: str, top: str, saida: Saida) -> Resultado:
    cmd = f"simplicio-video {top} --help"
    if saida.rc == 0 and "usage:" in saida.out:
        return Resultado(nome, "cli --help", OK, "ajuda do comando ok", "cli", cmd, saida.segundos)
    if "invalid choice" in saida.err:
        return Resultado(nome, "cli --help", SKIP, "comando ausente no CLI", "cli", cmd, saida.segundos)
    return Resultado(nome, "cli --help", FAIL, f"rc {saida.rc}: {_resumo(saida.texto)}", "cli", cmd, saida.segundos)


def _checar_sub_cli(nome: str, top: str, sub: str, subs: set[str], pode_rodar: bool, comando_ausente: bool) -> Resultado:
    """`where` and `status` of a track, when its --help lists them. `pode_rodar` is False when the track is not installed (and
    is not asked over a local app). `status` asks for --json and reads the text when the track has no --json."""
    checagem = f"cli {sub}"
    if comando_ausente:
        return Resultado(nome, checagem, SKIP, "comando ausente no CLI", "cli", f"simplicio-video {top} {sub}")
    if sub not in subs:
        return Resultado(nome, checagem, SKIP, "subcomando ausente no --help", "cli", f"simplicio-video {top} {sub}")
    if not pode_rodar:
        return Resultado(nome, checagem, SKIP, NAO_INSTALADO, "cli", f"simplicio-video {top} {sub}")
    argv = [top, sub, "--json"] if sub == "status" else [top, sub]
    saida = _rodar_cli(argv)
    if sub == "status" and saida.rc != 0 and _recusa_json(saida.texto):
        argv = [top, sub]
        saida = _rodar_cli(argv)
    cmd = "simplicio-video " + " ".join(argv)
    if saida.timeout:
        return Resultado(nome, checagem, FAIL, saida.err, "cli", cmd, saida.segundos)
    if saida.rc != 0:
        if APP_FECHADO in saida.texto:
            return Resultado(nome, checagem, SKIP, "app fechado (sem resposta local)", "cli", cmd, saida.segundos)
        return Resultado(nome, checagem, FAIL, f"rc {saida.rc}: {_resumo(saida.texto)}", "cli", cmd, saida.segundos)
    if sub == "where":
        if not saida.out.strip():
            return Resultado(nome, checagem, FAIL, "saída vazia", "cli", cmd, saida.segundos)
        return Resultado(nome, checagem, OK, _curto(_primeira_linha(saida.out)), "cli", cmd, saida.segundos)
    dados = _json(saida.out)
    if isinstance(dados, dict):
        detalhe = f"json, {len(dados)} campos"
    else:
        detalhe = "texto (sem --json)"
    return Resultado(nome, checagem, OK, detalhe, "cli", cmd, saida.segundos)


def _checar_recusa_cli(nome: str, top: str, sub: str, comando_ausente: bool) -> Resultado:
    checagem = f"cli {sub} sem URL"
    cmd = f"simplicio-video {top} {sub}"
    if comando_ausente:
        return Resultado(nome, checagem, SKIP, "comando ausente no CLI", "cli", cmd)
    saida = _rodar_cli([top, sub])
    if saida.timeout:
        return Resultado(nome, checagem, FAIL, saida.err, "cli", cmd, saida.segundos)
    if saida.rc != 0 and "URL" in saida.texto:
        return Resultado(nome, checagem, OK, "recusou sem URL (nada baixado)", "cli", cmd, saida.segundos)
    return Resultado(nome, checagem, FAIL, f"não recusou (rc {saida.rc}): {_resumo(saida.texto)}", "cli", cmd, saida.segundos)


def _checar_mcp(nome: str, instalada: bool) -> Resultado:
    chamada = MCP_LEITURA.get(nome)
    checagem = f"mcp {chamada.funcao}" if chamada else "mcp"
    if chamada is None:
        return Resultado(nome, checagem, SKIP, "sem chamada MCP de leitura no smoke", "mcp")
    cmd = f"{chamada.funcao}({', '.join(f'{k}={v!r}' for k, v in chamada.kwargs.items())})"
    if not hasattr(mcp_server, chamada.funcao):
        return Resultado(nome, checagem, SKIP, "função ausente em mcp_server", "mcp", cmd)
    if chamada.precisa and not instalada:
        return Resultado(nome, checagem, SKIP, NAO_INSTALADO, "mcp", cmd)
    inicio = time.monotonic()
    resposta, erro = _chamar_mcp(chamada.funcao, chamada.kwargs)
    segundos = time.monotonic() - inicio
    if resposta is None:
        return Resultado(nome, checagem, FAIL, erro, "mcp", cmd, segundos)
    texto = str(resposta.get("log") or resposta.get("error") or "")
    if chamada.espera == "recusa":
        if resposta.get("ok") is False and "URL" in texto:
            return Resultado(nome, checagem, OK, "recusou sem URL (nada baixado)", "mcp", cmd, segundos)
        return Resultado(nome, checagem, FAIL, f"não recusou: {_curto(_resumo(texto))}", "mcp", cmd, segundos)
    if resposta.get("ok") is True:
        detalhe = _primeira_linha(str(resposta.get("log") or "")) or str(resposta.get("schema") or "ok")
        if detalhe.startswith("usage:"):
            detalhe = "ajuda do comando ok"
        return Resultado(nome, checagem, OK, _curto(detalhe), "mcp", cmd, segundos)
    if APP_FECHADO in texto:
        return Resultado(nome, checagem, SKIP, "app fechado (sem resposta local)", "mcp", cmd, segundos)
    return Resultado(nome, checagem, FAIL, _curto(_resumo(texto)), "mcp", cmd, segundos)


def checar_trilha(nome: str) -> list[Resultado]:
    """The checks of one external track: its --help, then `where` and `status` through the CLI (when the --help lists them)
    and its read-only MCP call. Nothing runs past the --help unless the track is installed."""
    top = tools.COMMANDS.get(nome, nome).split()[0]
    instalada = tools.is_installed(tools.TOOLS[nome])
    ajuda = _rodar_cli([top, "--help"])
    ausente = ajuda.rc != 0 and "invalid choice" in ajuda.err
    subs = subcomandos(ajuda.out) if ajuda.rc == 0 else set()
    resultados = [_checar_ajuda(nome, top, ajuda),
                  _checar_sub_cli(nome, top, "where", subs, instalada, ausente),
                  _checar_sub_cli(nome, top, "status", subs, instalada or nome in APP_LOCAL, ausente)]
    if nome in CLI_RECUSA:
        resultados.append(_checar_recusa_cli(nome, top, CLI_RECUSA[nome], ausente))
    resultados.append(_checar_mcp(nome, instalada))
    return resultados


# ---------------------------------------------------------------- the checks of the core

def _core_doctor() -> Resultado:
    cmd = "simplicio-video doctor --json"
    saida = _rodar_cli(["doctor", "--json"])
    dados = _json(saida.out)
    if saida.timeout or not isinstance(dados, dict):
        return Resultado("core", "doctor --json", FAIL, f"rc {saida.rc}, sem JSON: {_resumo(saida.texto)}", "cli", cmd,
                         saida.segundos)
    checks = dados.get("checks") or []
    falhas = [c.get("name", "?") for c in checks if c.get("status") == "fail"]
    avisos = sum(1 for c in checks if c.get("status") == "warn")
    if saida.rc == 0 and not falhas:
        return Resultado("core", "doctor --json", OK, f"{len(checks)} checagens, {avisos} aviso(s)", "cli", cmd, saida.segundos)
    return Resultado("core", "doctor --json", FAIL, f"rc {saida.rc}; falhas: {', '.join(falhas) or '-'}", "cli", cmd,
                     saida.segundos)


def _core_status() -> Resultado:
    cmd = "simplicio-video status --json"
    saida = _rodar_cli(["status", "--json"])
    dados = _json(saida.out)
    if saida.rc == 0 and isinstance(dados, dict) and isinstance(dados.get("tools"), list):
        instaladas = sum(1 for t in dados["tools"] if t.get("installed"))
        return Resultado("core", "status --json", OK, f"{len(dados['tools'])} trilhas, {instaladas} instalada(s)", "cli", cmd,
                         saida.segundos)
    return Resultado("core", "status --json", FAIL, f"rc {saida.rc}: {_resumo(saida.texto)}", "cli", cmd, saida.segundos)


def _core_list() -> Resultado:
    cmd = "simplicio-video list templates --json"
    saida = _rodar_cli(["list", "templates", "--json"])
    itens = _json(saida.out)
    if saida.rc == 0 and isinstance(itens, list) and itens:
        renderizaveis = sum(1 for i in itens if i.get("renderizavel"))
        return Resultado("core", "list templates", OK, f"{len(itens)} templates ({renderizaveis} renderizáveis)", "cli", cmd,
                         saida.segundos)
    return Resultado("core", "list templates", FAIL, f"rc {saida.rc}: {_resumo(saida.texto)}", "cli", cmd, saida.segundos)


def _core_validate() -> Resultado:
    cmd = "simplicio-video validate --json tests/fixtures/mini/contract.yaml"
    if not FIXTURE.is_file():
        return Resultado("core", "validate", FAIL, "fixture ausente: tests/fixtures/mini/contract.yaml", "cli", cmd)
    saida = _rodar_cli(["validate", "--json", str(FIXTURE)])
    dados = _json(saida.out)
    if saida.rc == 0 and isinstance(dados, dict) and dados.get("ok") is True:
        return Resultado("core", "validate", OK, f"mini válido, {len(dados.get('warnings') or [])} aviso(s)", "cli", cmd,
                         saida.segundos)
    erros = "; ".join(str(e) for e in (dados or {}).get("errors", [])) if isinstance(dados, dict) else ""
    return Resultado("core", "validate", FAIL, f"rc {saida.rc}: {_curto(erros or _resumo(saida.texto))}", "cli", cmd,
                     saida.segundos)


def _contar_tools_mcp() -> int | str:
    """How many tools the MCP server lists, or the reason it cannot be built (the SDK is missing)."""
    try:
        servidor = mcp_server.build_server()
    except SystemExit as exc:  # the MCP SDK is not installed (extra `mcp`): a missing feature, not a failure
        return str(exc.code or "SDK mcp ausente")
    return len(asyncio.run(servidor.list_tools()))


def _core_mcp_lista() -> Resultado:
    cmd = "build_server().list_tools()"
    inicio = time.monotonic()
    valor, erro = _com_limite(_contar_tools_mcp)
    segundos = time.monotonic() - inicio
    if erro:
        return Resultado("core", "mcp tools/list", FAIL, erro, "mcp", cmd, segundos)
    if isinstance(valor, str):
        return Resultado("core", "mcp tools/list", SKIP, _curto(valor), "mcp", cmd, segundos)
    n = int(valor or 0)
    registro = len(mcp_server.TOOLS)
    if n and n == registro:
        return Resultado("core", "mcp tools/list", OK, f"{n} tools, igual ao registro", "mcp", cmd, segundos)
    return Resultado("core", "mcp tools/list", FAIL, f"{n} tools no servidor, {registro} no registro", "mcp", cmd, segundos)


def _executar(trilha: str, checagem: str, fn, *args) -> list[Resultado]:
    """Runs one check; an exception becomes a FAIL of that check, so one broken check never hides the others."""
    try:
        achado = fn(*args)
    except Exception as exc:  # noqa: BLE001 - report it and keep going
        return [Resultado(trilha, checagem, FAIL, _curto(f"{type(exc).__name__}: {exc}"), "core")]
    return achado if isinstance(achado, list) else [achado]


def checar_tudo() -> list[Resultado]:
    resultados: list[Resultado] = []
    resultados += _executar("core", "doctor --json", _core_doctor)
    resultados += _executar("core", "status --json", _core_status)
    resultados += _executar("core", "list templates", _core_list)
    resultados += _executar("core", "validate", _core_validate)
    resultados += _executar("core", "mcp tools/list", _core_mcp_lista)
    for nome in tools.TOOLS:
        resultados += _executar(nome, "trilha", checar_trilha, nome)
    return resultados


# ---------------------------------------------------------------- the output

def resumo(resultados: list[Resultado]) -> dict[str, int]:
    return {estado: sum(1 for r in resultados if r.estado == estado) for estado in (OK, FAIL, SKIP)}


def codigo_de_saida(resultados: list[Resultado]) -> int:
    return 1 if any(r.estado == FAIL for r in resultados) else 0


def formatar_tabela(resultados: list[Resultado]) -> str:
    cabecalho = ("trilha", "checagem", "estado", "detalhe")
    linhas = [(r.trilha, r.checagem, r.estado, _curto(r.detalhe)) for r in resultados]
    larguras = [max([len(cabecalho[i])] + [len(linha[i]) for linha in linhas]) for i in range(3)]

    def formatar(celulas) -> str:
        return " | ".join(celulas[i].ljust(larguras[i]) for i in range(3)) + " | " + celulas[3]

    separador = "-+-".join("-" * larguras[i] for i in range(3)) + "-+-" + "-" * 20
    return "\n".join([formatar(cabecalho), separador] + [formatar(linha) for linha in linhas])


def formatar_json(resultados: list[Resultado], duracao_s: float) -> dict:
    contagem = resumo(resultados)
    return {
        "schema": SCHEMA,
        "ok": contagem[FAIL] == 0,
        "resumo": contagem,
        "duracao_s": round(duracao_s, 1),
        "ambiente": {"python": platform.python_version(), "plataforma": sys.platform,
                     "ferramentas": str(tools.tools_dir())},
        "checagens": [{"trilha": r.trilha, "checagem": r.checagem, "status": r.estado, "detalhe": r.detalhe, "via": r.via,
                       "comando": r.comando, "segundos": round(r.segundos, 2)} for r in resultados],
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Smoke só de leitura das trilhas externas (CLI e MCP) e do núcleo. Não instala, não baixa e não gasta.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="exemplos:\n  .venv/bin/python scripts/smoke_trilhas.py\n  .venv/bin/python scripts/smoke_trilhas.py --json")
    ap.add_argument("--json", action="store_true", help="imprime só o JSON (simplicio.smoke-trilhas/v1) no stdout")
    args = ap.parse_args(argv)
    inicio = time.monotonic()
    resultados = checar_tudo()
    duracao = time.monotonic() - inicio
    if args.json:
        print(json.dumps(formatar_json(resultados, duracao), ensure_ascii=False, indent=2))
    else:
        print(formatar_tabela(resultados))
        contagem = resumo(resultados)
        print(f"\nresumo: {contagem[OK]} OK, {contagem[FAIL]} FAIL, {contagem[SKIP]} SKIP em {duracao:.1f} s")
    return codigo_de_saida(resultados)


if __name__ == "__main__":
    raise SystemExit(main())
