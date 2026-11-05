"""Testes do `scripts/smoke_trilhas.py` (o smoke só de leitura das trilhas externas e do núcleo).

Dois níveis. As funções de formatação e de decisão rodam offline, sem CLI nem rede, e entram no `make check`.
O script de verdade roda contra o que está instalado nesta máquina: é o teste `integration`, fora do `make check`.
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from simplicio_video import mcp_server, tools

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "smoke_trilhas.py"
PROC_DISPONIVEL = os.name == "posix" and Path("/proc/self/stat").is_file()

AJUDA_OPENCUT = """usage: simplicio-video opencut [-h] ...

Clona e sobe o OpenCut.

positional arguments:
  args        clone [dir] | dev | where

options:
  -h, --help  show this help message and exit
"""

AJUDA_INSTAGRAM = """usage: simplicio-video instagram [-h] ...

positional arguments:
  args        clone [dir] | where [--skills] | status | skills | run FERRAMENTA
              [--forcar] [--bruto] [-- argumentos]

options:
  -h, --help  show this help message and exit
"""

AJUDA_VOICESTUDIO = """usage: simplicio-video voicestudio [-h] ...

positional arguments:
  args        status | voices | languages | personalities | tts | transcribe | clone | describe | design | mcp

options:
  -h, --help  show this help message and exit
"""

# What `clone --help` really prints on main: it passes through to Hypit's own help (no `usage:` line; the engine's argparse
# help is `clone --engine-help`). Copied from packages/cli/src/output.ts and packages/video-cli/src/cli.ts of @hypit/hypit 0.2.17.
AJUDA_CLONE = """Hypit

Authoring
  check <source>                verify one self-described Author or Run source
  plan <run-source>             show selected work without executing
  build <run-source>            submit a Build; --follow observes it

Results
  builds                        list Results newest first
  status <build-id> [--watch]   show current work and Result facts

Preparation (local tools and project files)
  media probe | frames | cut
  capture screenshot | run | install-browser
  vocabulary
  hypit help media, hypit help capture, hypit help vocabulary
"""

AJUDA_CLONE_MOTOR = """usage: simplicio-video clone [-h] ...

positional arguments:
  args        argumentos repassados ao CLI do Hypit AI

options:
  -h, --help  show this help message and exit
"""

AJUDA_MONTAGE = """usage: simplicio-video montage [-h] ...

positional arguments:
  args        argumentos repassados ao OpenMontage

options:
  -h, --help  show this help message and exit
"""


@pytest.fixture(scope="module")
def smoke():
    assert SCRIPT.is_file(), "scripts/smoke_trilhas.py does not exist"
    spec = importlib.util.spec_from_file_location("smoke_trilhas_sob_teste", SCRIPT)
    modulo = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = modulo  # dataclasses look the module up by name while the script is executed
    try:
        spec.loader.exec_module(modulo)
        yield modulo
    finally:
        sys.modules.pop(spec.name, None)


def _resultados_falsos(smoke):
    return [
        smoke.Resultado("opencut", "cli where", smoke.OK, "/root/.simplicio-video/tools/opencut",
                        via="cli", comando="simplicio-video opencut where", segundos=0.4),
        smoke.Resultado("voicestudio", "mcp video_voicestudio", smoke.SKIP, "não instalado", via="mcp"),
        smoke.Resultado("tinyfish", "cli status", smoke.FAIL, "rc 1: " + "detalhe longo " * 20, via="cli"),
    ]


def test_tabela_tem_cabecalho_uma_linha_por_checagem_e_detalhe_curto(smoke):
    linhas = smoke.formatar_tabela(_resultados_falsos(smoke)).splitlines()
    cabecalho = [c.strip() for c in linhas[0].split("|")]
    assert cabecalho[:3] == ["trilha", "checagem", "estado"]
    assert "detalhe" in linhas[0]
    assert len(linhas) == 2 + 3  # cabeçalho, separador e as três checagens
    assert any("FAIL" in linha for linha in linhas)
    assert any("não instalado" in linha for linha in linhas)
    assert all(linha.endswith("...") for linha in linhas[2:] if "detalhe longo" in linha)


def test_json_tem_schema_contagem_e_ok_so_sem_fail(smoke):
    dados = smoke.formatar_json(_resultados_falsos(smoke), 1.25)
    assert dados["schema"] == "simplicio.smoke-trilhas/v1"
    assert dados["resumo"] == {"OK": 1, "FAIL": 1, "SKIP": 1}
    assert dados["ok"] is False
    assert [c["status"] for c in dados["checagens"]] == ["OK", "SKIP", "FAIL"]
    assert dados["checagens"][0]["comando"] == "simplicio-video opencut where"
    json.dumps(dados)  # serializável como está


def test_codigo_de_saida_so_reprova_com_fail(smoke):
    sem_fail = [r for r in _resultados_falsos(smoke) if r.estado != smoke.FAIL]
    assert smoke.codigo_de_saida(sem_fail) == 0
    assert smoke.codigo_de_saida(_resultados_falsos(smoke)) == 1


def test_subcomandos_saem_da_linha_args_do_help(smoke):
    assert smoke.subcomandos(AJUDA_OPENCUT) == {"clone", "dev", "where"}
    assert smoke.subcomandos(AJUDA_INSTAGRAM) == {"clone", "where", "status", "skills", "run"}
    assert smoke.subcomandos(AJUDA_CLONE) == set()  # texto livre: o help não lista subcomandos


def test_trilha_nao_instalada_so_roda_a_ajuda(smoke, monkeypatch):
    chamadas = []

    def cli_falso(argv):
        chamadas.append(list(argv))
        return smoke.Saida(0, AJUDA_OPENCUT, "")

    def mcp_proibido(funcao, kwargs):
        pytest.fail(f"a chamada MCP {funcao} não pode rodar com a trilha não instalada")

    monkeypatch.setattr(smoke, "_rodar_cli", cli_falso)
    monkeypatch.setattr(smoke, "_chamar_mcp", mcp_proibido)
    monkeypatch.setattr(smoke.tools, "is_installed", lambda t: False)

    res = smoke.checar_trilha("opencut")

    assert chamadas == [["opencut", "--help"]]  # nenhum `where` nem `status` roda sem o checkout
    assert {r.checagem: r.estado for r in res} == {
        "cli --help": "OK", "cli where": "SKIP", "cli status": "SKIP", "mcp video_opencut": "SKIP"}
    assert all(r.detalhe == "não instalado" for r in res if r.estado == "SKIP" and r.via == "cli" and "where" in r.checagem)


def test_where_quebrado_em_trilha_instalada_reprova(smoke, monkeypatch):
    def cli_falso(argv):
        if argv[1:] == ["where"]:
            return smoke.Saida(1, "", "boom")
        return smoke.Saida(0, AJUDA_OPENCUT, "")

    monkeypatch.setattr(smoke, "_rodar_cli", cli_falso)
    monkeypatch.setattr(smoke, "_chamar_mcp", lambda funcao, kwargs: ({"ok": True, "log": "/x"}, ""))
    monkeypatch.setattr(smoke.tools, "is_installed", lambda t: True)

    por_checagem = {r.checagem: r for r in smoke.checar_trilha("opencut")}

    assert por_checagem["cli where"].estado == smoke.FAIL
    assert por_checagem["cli where"].detalhe == "rc 1: boom"
    assert por_checagem["mcp video_opencut"].estado == smoke.OK
    assert smoke.codigo_de_saida(list(por_checagem.values())) == 1


def test_status_sem_json_le_o_texto(smoke, monkeypatch):
    def cli_falso(argv):
        if argv[-1] == "--json":
            return smoke.Saida(1, "", "moneyprinter: status não recebe argumentos; argumento a mais: --json")
        return smoke.Saida(0, "checkout: /x\n", "")

    monkeypatch.setattr(smoke, "_rodar_cli", cli_falso)
    r = smoke._checar_sub_cli("moneyprinter", "moneyprinter", "status", {"status"}, True, False)
    assert (r.estado, r.detalhe) == (smoke.OK, "texto (sem --json)")


def test_app_fechado_nao_reprova(smoke, monkeypatch):
    monkeypatch.setattr(smoke, "_rodar_cli", lambda argv: smoke.Saida(
        1, "", "voicestudio: não consegui falar com o VoiceStudio em http://127.0.0.1:3900/mcp/"))
    r = smoke._checar_sub_cli("voicestudio", "voicestudio", "status", {"status"}, True, False)
    assert r.estado == smoke.SKIP
    assert smoke.codigo_de_saida([r]) == 0


def test_chamadas_mcp_do_smoke_so_leem(smoke):
    # `fetch` sem URL é recusado antes de qualquer download; `status --json` só lê (clone e montage informam o estado)
    permitidos = ("--help", "where", "status", "status --json", ["fetch"])
    for trilha, chamada in smoke.MCP_LEITURA.items():
        assert trilha in tools.TOOLS, trilha
        assert all(valor in permitidos for valor in chamada.kwargs.values()), (trilha, chamada.kwargs)
        assert hasattr(mcp_server, chamada.funcao), (trilha, chamada.funcao)


def test_clone_pede_a_ajuda_do_motor_e_nunca_a_do_hypit(smoke, monkeypatch):
    """`clone --help` passes through to Hypit, which runs through npx when it is not installed: the check asks the engine
    (`--engine-help`) and never sends `--help` to Hypit."""
    chamadas = []

    def cli(argv):
        chamadas.append(list(argv))
        if argv[1:] == ["--help"]:
            return smoke.Saida(0, AJUDA_CLONE, "")  # Hypit's own help: rc 0, no `usage:`
        if argv[1:] == ["--engine-help"]:
            return smoke.Saida(0, AJUDA_CLONE_MOTOR, "")
        return smoke.Saida(0, '{"ok": true, "source": "npx"}', "")

    monkeypatch.setattr(smoke, "_rodar_cli", cli)
    monkeypatch.setattr(smoke, "_chamar_mcp", lambda funcao, kwargs: ({"ok": True, "log": "x"}, ""))
    monkeypatch.setattr(smoke.tools, "is_installed", lambda t: True)
    resultados = smoke.checar_trilha("hypit")
    assert ["clone", "--help"] not in chamadas
    ajuda = [r for r in resultados if r.checagem.startswith("cli --")]
    assert len(ajuda) == 1 and ajuda[0].estado == smoke.OK and ajuda[0].checagem == "cli --engine-help"


def test_clone_status_json_entra_na_checagem_local(smoke, monkeypatch):
    chamadas = []

    def cli(argv):
        chamadas.append(list(argv))
        if argv[1:] == ["status", "--json"]:
            return smoke.Saida(0, '{"ok": true, "source": "npx", "pinned": "0.3.1"}', "")
        return smoke.Saida(0, AJUDA_CLONE_MOTOR, "")

    monkeypatch.setattr(smoke, "_rodar_cli", cli)
    monkeypatch.setattr(smoke, "_chamar_mcp", lambda funcao, kwargs: ({"ok": True, "log": "x"}, ""))
    monkeypatch.setattr(smoke.tools, "is_installed", lambda t: True)
    por_checagem = {r.checagem: r for r in smoke.checar_trilha("hypit")}
    assert ["clone", "status", "--json"] in chamadas
    assert por_checagem["cli status"].estado == smoke.OK
    assert por_checagem["cli status"].comando == "simplicio-video clone status --json"


def test_montage_status_json_entra_na_checagem(smoke, monkeypatch):
    chamadas = []

    def cli(argv):
        chamadas.append(list(argv))
        if argv[1:] == ["status", "--json"]:
            return smoke.Saida(0, '{"ok": true, "checkout": {"found": true}}', "")
        return smoke.Saida(0, AJUDA_MONTAGE, "")

    monkeypatch.setattr(smoke, "_rodar_cli", cli)
    monkeypatch.setattr(smoke, "_chamar_mcp", lambda funcao, kwargs: ({"ok": True, "log": "x"}, ""))
    monkeypatch.setattr(smoke.tools, "is_installed", lambda t: True)
    por_checagem = {r.checagem: r for r in smoke.checar_trilha("openmontage")}
    assert ["montage", "status", "--json"] in chamadas
    assert por_checagem["cli status"].estado == smoke.OK


def test_instagram_skills_entra_na_checagem(smoke, monkeypatch):
    chamadas = []

    def cli(argv):
        chamadas.append(list(argv))
        if argv[1:] == ["skills"]:
            return smoke.Saida(0, "skills do instagram-agent-skill (a descrição é texto de terceiros):\nig-audit  ...\n", "")
        return smoke.Saida(0, AJUDA_INSTAGRAM if argv[1:] == ["--help"] else "x", "")

    monkeypatch.setattr(smoke, "_rodar_cli", cli)
    monkeypatch.setattr(smoke, "_chamar_mcp", lambda funcao, kwargs: ({"ok": True, "log": "x"}, ""))
    monkeypatch.setattr(smoke.tools, "is_installed", lambda t: True)
    por_checagem = {r.checagem: r for r in smoke.checar_trilha("instagram")}
    assert ["instagram", "skills"] in chamadas
    assert por_checagem["cli skills"].estado == smoke.OK


def test_voicestudio_voices_entra_na_checagem_e_app_fechado_nao_reprova(smoke, monkeypatch):
    fechado = "voicestudio: não consegui falar com o VoiceStudio em http://127.0.0.1:3900/mcp/"

    def cli(argv):
        if argv[1:] == ["--help"]:
            return smoke.Saida(0, AJUDA_VOICESTUDIO, "")
        return smoke.Saida(1, "", fechado)

    monkeypatch.setattr(smoke, "_rodar_cli", cli)
    monkeypatch.setattr(smoke, "_chamar_mcp", lambda funcao, kwargs: ({"ok": False, "log": fechado}, ""))
    monkeypatch.setattr(smoke.tools, "is_installed", lambda t: False)  # the app is not a checkout: it is asked anyway
    por_checagem = {r.checagem: r for r in smoke.checar_trilha("voicestudio")}
    assert por_checagem["cli voices"].estado == smoke.SKIP
    assert por_checagem["cli voices"].detalhe == "app fechado (sem resposta local)"


def test_mcp_do_hypit_e_do_montage_leem_o_status(smoke):
    """Both live behind their own read-only status (the registry allows it); neither MCP call asks for a help that passes
    through to an upstream (Hypit's `--help` runs npx)."""
    assert smoke.MCP_LEITURA["hypit"].kwargs == {"args": "status --json"}
    assert smoke.MCP_LEITURA["hypit"].precisa is True
    assert smoke.MCP_LEITURA["openmontage"].kwargs == {"args": "status --json"}


def test_toda_trilha_do_registro_tem_roteiro_no_smoke(smoke):
    assert set(tools.TOOLS) <= set(smoke.MCP_LEITURA)


def test_chamada_mcp_que_estoura_dentro_do_redirect_nao_perde_o_stdout(smoke, monkeypatch):
    """A call that never ends inside contextlib.redirect_stdout (as _cli does) must not leave sys.stdout on its buffer."""
    liberar, terminou = threading.Event(), threading.Event()

    def preso(**kwargs):
        with contextlib.redirect_stdout(io.StringIO()):
            liberar.wait(5)
        terminou.set()
        return {"ok": True}

    monkeypatch.setattr(smoke, "TIMEOUT_S", 0.2)
    monkeypatch.setattr(smoke.mcp_server, "video_preso", preso, raising=False)
    stdout, stderr = sys.stdout, sys.stderr
    env_antes = os.environ.get("SIMPLICIO_MCP")
    try:
        resposta, erro = smoke._chamar_mcp("video_preso", {})
        assert resposta is None and "sem resposta" in erro
        assert sys.stdout is stdout and sys.stderr is stderr
        assert os.environ.get("SIMPLICIO_MCP") == env_antes
    finally:
        liberar.set()
        assert terminou.wait(5)


@pytest.mark.skipif(not PROC_DISPONIVEL, reason="o teste lê /proc (Linux); em outros sistemas fica UNVERIFIED")
@pytest.mark.slow
def test_rodar_cli_estouro_mata_o_processo_e_os_netos(smoke, monkeypatch, tmp_path):
    pidfile = tmp_path / "neto.pid"
    filho = ("import subprocess, sys, time\n"
             f"neto = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
             f"open({str(pidfile)!r}, 'w').write(str(neto.pid))\n"
             "time.sleep(60)\n")
    monkeypatch.setattr(smoke, "_comando_cli", lambda: [sys.executable, "-c", filho])
    monkeypatch.setattr(smoke, "TIMEOUT_S", 3)
    saida = smoke._rodar_cli(["qualquer"])
    neto = int(pidfile.read_text())
    try:
        assert saida.timeout and saida.rc == 124
        # The pipe reaches EOF when the neto closes its fds, a moment before the kernel marks it dead: poll briefly.
        prazo = time.monotonic() + 2
        while _vivo(neto) and time.monotonic() < prazo:
            time.sleep(0.02)
        assert not _vivo(neto), "o neto sobreviveu ao estouro: o grupo do processo não foi morto"
    finally:
        if _vivo(neto):
            os.kill(neto, 9)


def _vivo(pid: int) -> bool:
    """True while `pid` runs; a zombie (Z) or a process that is exiting (X) is dead for this purpose."""
    try:
        estado = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0]
    except (FileNotFoundError, ProcessLookupError, IndexError):
        return False
    return estado not in ("Z", "X")


def test_mensagem_do_mcp_no_stderr_entra_no_resultado(smoke, monkeypatch):
    """video_voicestudio prints its 'app closed' message to stderr and returns an empty log: the check must still read it."""
    def fechado(**kwargs):
        print("voicestudio: não consegui falar com o VoiceStudio", file=sys.stderr)
        return {"ok": False, "result": 1, "log": ""}

    monkeypatch.setattr(smoke.mcp_server, "video_fechado", fechado, raising=False)
    monkeypatch.setitem(smoke.MCP_LEITURA, "voicestudio", smoke.ChamadaMcp("video_fechado", {}, precisa=False))
    resposta, erro = smoke._chamar_mcp("video_fechado", {})
    assert erro == "" and "não consegui falar" in resposta["log"]
    r = smoke._checar_mcp("voicestudio", False)
    assert r.estado == smoke.SKIP and r.detalhe == "app fechado (sem resposta local)"


def test_lista_de_tools_do_mcp_tem_limite_de_tempo(smoke, monkeypatch):
    liberar = threading.Event()

    class Servidor:
        async def list_tools(self):
            liberar.wait(2)
            return []

    monkeypatch.setattr(smoke, "TIMEOUT_S", 0.2)
    monkeypatch.setattr(smoke.mcp_server, "build_server", lambda: Servidor())
    try:
        r = smoke._core_mcp_lista()
    finally:
        liberar.set()
    assert r.estado == smoke.FAIL and "sem resposta" in r.detalhe


def test_comando_inexistente_no_cli_e_skip(smoke, monkeypatch):
    erro = "simplicio-video: error: argument COMANDO: invalid choice: 'hypit' (choose from 'init', 'validate')"
    monkeypatch.setattr(smoke, "_rodar_cli", lambda argv: smoke.Saida(2, "", erro))
    monkeypatch.setattr(smoke, "_chamar_mcp", lambda funcao, kwargs: ({"ok": True, "log": "x"}, ""))
    monkeypatch.setattr(smoke.tools, "is_installed", lambda t: True)
    resultados = smoke.checar_trilha("hypit")
    ajuda = [r for r in resultados if r.checagem.startswith("cli --")]
    assert len(ajuda) == 1 and ajuda[0].estado == smoke.SKIP
    assert ajuda[0].detalhe == "comando ausente no CLI"
    por_checagem = {r.checagem: r for r in resultados}
    assert por_checagem["cli where"].estado == smoke.SKIP
    assert por_checagem["cli status"].estado == smoke.SKIP
    assert smoke.codigo_de_saida(resultados) == 0


@pytest.mark.parametrize("app_responde", [True, False])
def test_voicestudio_sem_checkout_pergunta_ao_app(smoke, monkeypatch, app_responde):
    """VoiceStudio is a desktop app: its status talks to the local API, so a missing checkout must not skip the check."""
    if app_responde:
        status_cli = smoke.Saida(0, '{"ok": true, "vozes": 3}', "")
        status_mcp = ({"ok": True, "log": '{"ok": true, "vozes": 3}'}, "")
        esperado = smoke.OK
    else:
        fechado = "voicestudio: não consegui falar com o VoiceStudio em http://127.0.0.1:3900/mcp/"
        status_cli = smoke.Saida(1, "", fechado)
        status_mcp = ({"ok": False, "log": fechado}, "")
        esperado = smoke.SKIP

    def cli(argv):
        if argv[1:] == ["--help"]:
            return smoke.Saida(0, AJUDA_VOICESTUDIO, "")
        assert argv[1:] in (["status", "--json"], ["voices", "--json"]), argv
        return status_cli

    monkeypatch.setattr(smoke, "_rodar_cli", cli)
    monkeypatch.setattr(smoke, "_chamar_mcp", lambda funcao, kwargs: status_mcp)
    monkeypatch.setattr(smoke.tools, "is_installed", lambda t: False)
    por_checagem = {r.checagem: r for r in smoke.checar_trilha("voicestudio")}
    assert por_checagem["cli status"].estado == esperado
    assert por_checagem["mcp video_voicestudio"].estado == esperado
    if not app_responde:
        assert por_checagem["cli status"].detalhe == "app fechado (sem resposta local)"
        assert por_checagem["mcp video_voicestudio"].detalhe == "app fechado (sem resposta local)"


@pytest.mark.integration
def test_smoke_trilhas_nesta_maquina_sem_fail():
    r = subprocess.run([sys.executable, str(SCRIPT), "--json"], capture_output=True, text=True, encoding="utf-8",
                       timeout=600, cwd=ROOT)
    assert r.returncode == 0, (r.stdout[-3000:], r.stderr[-2000:])
    dados = json.loads(r.stdout)
    assert dados["schema"] == "simplicio.smoke-trilhas/v1"
    assert [c for c in dados["checagens"] if c["status"] == "FAIL"] == []
    trilhas = {c["trilha"] for c in dados["checagens"]}
    assert set(tools.TOOLS) <= trilhas
    assert {"doctor --json", "status --json", "list templates", "validate", "mcp tools/list"} <= {
        c["checagem"] for c in dados["checagens"] if c["trilha"] == "core"}


def test_trilha_quebrada_no_doctor_e_aviso_no_smoke_e_nao_falha(smoke, monkeypatch):
    from types import SimpleNamespace

    dados = {"schema": "simplicio.doctor/v1", "status": "fail", "checks": [
        {"name": "python", "status": "ok", "summary": "Python 3.12", "fix": None, "detail": {}},
        {"name": "trilhas", "status": "fail", "summary": "1 com instalação quebrada",
         "fix": "simplicio-video doctor trilhas", "detail": {}}]}
    saida = SimpleNamespace(out=json.dumps(dados), rc=1, timeout=False, texto=json.dumps(dados), segundos=0.1)
    monkeypatch.setattr(smoke, "_rodar_cli", lambda argv: saida)
    assert smoke._core_doctor().estado != smoke.FAIL


def test_falha_do_nucleo_mais_trilha_quebrada_continua_FAIL_no_smoke(smoke, monkeypatch):
    from types import SimpleNamespace

    dados = {"schema": "simplicio.doctor/v1", "status": "fail", "checks": [
        {"name": "python", "status": "fail", "summary": "Python 3.11", "fix": "instale Python 3.12", "detail": {}},
        {"name": "trilhas", "status": "fail", "summary": "1 com instalação quebrada",
         "fix": "simplicio-video doctor trilhas", "detail": {}}]}
    saida = SimpleNamespace(out=json.dumps(dados), rc=1, timeout=False, texto=json.dumps(dados), segundos=0.1)
    monkeypatch.setattr(smoke, "_rodar_cli", lambda argv: saida)
    assert smoke._core_doctor().estado == smoke.FAIL
