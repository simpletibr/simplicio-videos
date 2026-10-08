"""Receita LangFlow para chamar o motor (#84, épico #81).

O componente em examples/langflow/simplicio_component.py chama o CLI simplicio-video só com comandos que têm
--json, por lista de argumentos e sem shell. Estes testes trocam o subprocess por um falso e não precisam do
LangFlow instalado. O fluxo de exemplo cita só comandos que existem no --help real do CLI.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import os
import re
import subprocess
import sys
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
COMPONENTE = ROOT / "examples" / "langflow" / "simplicio_component.py"
FLUXO = ROOT / "examples" / "langflow" / "fluxo-exemplo.json"

RE_COMANDO_CITADO = re.compile(
    r"simplicio-video[ \t]+([a-z][a-z-]*)(?:[ \t]+([a-z][a-z-]*))?"
)


def _modulo():
    assert COMPONENTE.is_file(), "falta examples/langflow/simplicio_component.py"
    spec = importlib.util.spec_from_file_location(
        "simplicio_component_teste", COMPONENTE
    )
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def _falso_run(monkeypatch, returncode=0, stdout="", stderr=""):
    """Troca subprocess.run por um falso que grava (argv, kwargs) e devolve a saída pedida."""
    monkeypatch.delenv("SIMPLICIO_VIDEO_BIN", raising=False)
    chamadas = []

    def falso(argv, **kwargs):
        chamadas.append((argv, kwargs))
        return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)

    monkeypatch.setattr(subprocess, "run", falso)
    return chamadas


@lru_cache(maxsize=None)
def _ajuda(*comando: str) -> str:
    """O --help real do CLI, rodado a partir do src deste checkout."""
    env = dict(os.environ)
    env["PYTHONPATH"] = str(SRC)
    resultado = subprocess.run(
        [sys.executable, "-m", "simplicio_video.cli", *comando, "--help"],
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
        check=False,
    )
    assert resultado.returncode == 0, resultado.stderr
    return resultado.stdout


@lru_cache(maxsize=None)
def _comandos_reais() -> tuple[frozenset[str], dict[str, frozenset[str]]]:
    """Comandos de primeiro nível (da seção 'comandos' do help) e os subcomandos dos grupos conhecidos."""
    principal = _ajuda()
    secao = principal.split("comandos (na ordem do fluxo):", 1)[1].split(
        "exemplos:", 1
    )[0]
    principais = frozenset(re.findall(r"^ {4}([a-z][a-z-]*)\s", secao, flags=re.M))
    usado = re.search(r"simplicio-video board \[-h\] \{([a-z,-]+)\}", _ajuda("board"))
    assert usado, "o help de board não lista os subcomandos entre chaves"
    grupos = {"board": frozenset(usado.group(1).split(","))}
    return principais, grupos


def _fluxo():
    assert FLUXO.is_file(), "falta examples/langflow/fluxo-exemplo.json"
    return json.loads(FLUXO.read_text(encoding="utf-8"))


def _textos(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for valor in obj.values():
            yield from _textos(valor)
    elif isinstance(obj, list):
        for valor in obj:
            yield from _textos(valor)


# ----------------------------------------------------------------- componente: resultado e argumentos


def test_componente_devolve_o_json_do_validate(monkeypatch):
    m = _modulo()
    payload = {"ok": True, "contrato": "c.yaml", "errors": [], "warnings": []}
    chamadas = _falso_run(monkeypatch, 0, json.dumps(payload))

    assert m.executar("validate", contrato="c.yaml") == payload
    assert chamadas[0][0] == ["simplicio-video", "validate", "--json", "c.yaml"]


def test_componente_devolve_o_quadro_do_board_list(monkeypatch):
    m = _modulo()
    quadro = {"schema": "simplicio.board/v1", "columns": []}
    chamadas = _falso_run(monkeypatch, 0, json.dumps(quadro))

    assert m.executar("board_list") == quadro
    assert chamadas[0][0] == ["simplicio-video", "board", "list", "--json"]


@pytest.mark.parametrize(
    "comando, kwargs, argv_esperado",
    [
        ("status", {}, ["simplicio-video", "status", "--json"]),
        (
            "status",
            {"contrato": "c.yaml"},
            ["simplicio-video", "status", "--json", "c.yaml"],
        ),
        (
            "render",
            {"contrato": "c.yaml", "preview": True},
            ["simplicio-video", "render", "--json", "--preview", "c.yaml"],
        ),
        (
            "validate",
            {"contrato": "c.yaml", "need_lock": True},
            ["simplicio-video", "validate", "--json", "--need-lock", "c.yaml"],
        ),
    ],
)
def test_argv_de_cada_comando(monkeypatch, comando, kwargs, argv_esperado):
    m = _modulo()
    chamadas = _falso_run(monkeypatch, 0, json.dumps({"ok": True}))

    m.executar(comando, **kwargs)
    assert chamadas[0][0] == argv_esperado


def test_componente_usa_o_executavel_configurado(monkeypatch):
    m = _modulo()
    chamadas = _falso_run(monkeypatch, 0, json.dumps({"ok": True}))

    m.executar("status", executavel="/opt/motor/bin/simplicio-video")
    assert chamadas[0][0][0] == "/opt/motor/bin/simplicio-video"


def test_recusa_contrato_que_parece_opcao_e_comando_sem_contrato(monkeypatch):
    m = _modulo()
    chamadas = _falso_run(monkeypatch, 0, json.dumps({"ok": True}))

    with pytest.raises(ValueError):
        m.executar("validate", contrato="--out=/tmp/x")
    with pytest.raises(ValueError):
        m.executar("render")
    with pytest.raises(ValueError):
        m.executar("board_list", contrato="c.yaml")
    assert chamadas == []


# ----------------------------------------------------------------- erros viram exceção clara


@pytest.mark.parametrize(
    "payload, codigo, trecho",
    [
        (
            {
                "ok": False,
                "contrato": "c.yaml",
                "error": {
                    "code": "CONTRATO_INVALIDO",
                    "message": "soma das cenas diferente",
                },
            },
            "CONTRATO_INVALIDO",
            "soma das cenas",
        ),
        (
            {"ok": False, "contrato": "c.yaml", "errors": ["fala 3 não cabe na cena"]},
            "CONTRATO_INVALIDO",
            "fala 3 não cabe na cena",
        ),
    ],
)
def test_erro_json_ok_false_vira_excecao_clara(monkeypatch, payload, codigo, trecho):
    m = _modulo()
    _falso_run(monkeypatch, 1, json.dumps(payload))

    with pytest.raises(m.ErroMotor) as info:
        m.executar("validate", contrato="c.yaml")
    assert info.value.codigo == codigo
    assert trecho in str(info.value)
    assert "simplicio-video" in str(info.value)


def test_saida_que_nao_e_json_vira_erro_com_o_stderr(monkeypatch):
    m = _modulo()
    _falso_run(
        monkeypatch, 1, "Traceback (most recent call last)", "KeyError: 'render'"
    )

    with pytest.raises(m.ErroMotor) as info:
        m.executar("status")
    assert info.value.codigo == "SAIDA_INVALIDA"
    assert "KeyError" in str(info.value)


def test_executavel_ausente_vira_erro_claro(monkeypatch):
    m = _modulo()
    monkeypatch.delenv("SIMPLICIO_VIDEO_BIN", raising=False)

    def sem_binario(argv, **kwargs):
        raise FileNotFoundError(2, "No such file or directory", argv[0])

    monkeypatch.setattr(subprocess, "run", sem_binario)
    with pytest.raises(m.ErroMotor) as info:
        m.executar("status")
    assert info.value.codigo == "FERRAMENTA_AUSENTE"


def test_tempo_esgotado_vira_erro_claro(monkeypatch):
    m = _modulo()
    monkeypatch.delenv("SIMPLICIO_VIDEO_BIN", raising=False)

    def demorou(argv, **kwargs):
        raise subprocess.TimeoutExpired(argv, kwargs.get("timeout"))

    monkeypatch.setattr(subprocess, "run", demorou)
    with pytest.raises(m.ErroMotor) as info:
        m.executar("render", contrato="c.yaml")
    assert info.value.codigo == "TEMPO_ESGOTADO"


# ----------------------------------------------------------------- sem shell e sem texto livre


def test_chama_com_lista_de_argumentos_e_sem_shell(monkeypatch):
    m = _modulo()
    chamadas = _falso_run(monkeypatch, 0, json.dumps({"ok": True}))
    perigoso = "c.yaml; rm -rf ~ $(whoami)"

    m.executar("validate", contrato=perigoso)
    argv, kwargs = chamadas[0]
    assert isinstance(argv, list)
    assert all(isinstance(parte, str) for parte in argv)
    assert argv[-1] == perigoso, (
        "o contrato tem que chegar como um argumento só, sem interpretação"
    )
    assert len(argv) == 4
    assert kwargs.get("shell", False) is False


def test_codigo_do_componente_nao_usa_shell_nem_concatena_texto():
    arvore = ast.parse(COMPONENTE.read_text(encoding="utf-8"))

    for no in ast.walk(arvore):
        if isinstance(no, ast.keyword) and no.arg == "shell":
            assert not (
                isinstance(no.value, ast.Constant) and no.value.value is True
            ), "shell=True proibido"
        if isinstance(no, ast.Attribute):
            assert no.attr not in {"system", "popen", "getoutput", "getstatusoutput"}, (
                f"{no.attr} proibido"
            )

    chamadas = [
        no
        for no in ast.walk(arvore)
        if isinstance(no, ast.Call)
        and isinstance(no.func, ast.Attribute)
        and no.func.attr in {"run", "Popen", "call", "check_call", "check_output"}
    ]
    assert chamadas, "o componente não chama subprocess"
    for chamada in chamadas:
        primeiro = chamada.args[0] if chamada.args else None
        assert isinstance(primeiro, (ast.Name, ast.List)), (
            "o primeiro argumento de subprocess tem que ser uma lista (ou variável com lista), nunca texto montado"
        )


# ----------------------------------------------------------------- só comandos com --json, do help real


def test_componente_so_chama_comandos_com_json_no_help_real():
    m = _modulo()
    assert m.COMANDOS, "COMANDOS vazio"
    for base in m.COMANDOS.values():
        assert "--json" in base
        subcomando = tuple(parte for parte in base if not parte.startswith("-"))
        assert "--json" in _ajuda(*subcomando), (
            f"simplicio-video {' '.join(subcomando)} não tem --json no help real"
        )


def test_importavel_sem_langflow(monkeypatch):
    for nome in ("langflow", "langflow.custom", "langflow.io", "langflow.schema"):
        monkeypatch.setitem(sys.modules, nome, None)

    m = _modulo()
    assert m.LANGFLOW_DISPONIVEL is False
    assert callable(m.executar)


# ----------------------------------------------------------------- fluxo exportado


def test_fluxo_e_json_valido_com_o_componente_atual():
    fluxo = _fluxo()
    nos = fluxo["data"]["nodes"]
    assert isinstance(nos, list) and nos

    componentes = [no for no in nos if no["data"]["type"] == "SimplicioVideoComponent"]
    assert componentes, "o fluxo não usa o componente SimplicioVideoComponent"
    codigo = componentes[0]["data"]["node"]["template"]["code"]["value"]
    assert codigo == COMPONENTE.read_text(encoding="utf-8"), (
        "o código no fluxo está defasado: exporte o fluxo de novo"
    )


def test_fluxo_so_usa_comandos_do_componente_e_le_o_quadro():
    m = _modulo()
    componentes = [
        no
        for no in _fluxo()["data"]["nodes"]
        if no["data"]["type"] == "SimplicioVideoComponent"
    ]
    usados = {no["data"]["node"]["template"]["comando"]["value"] for no in componentes}

    assert usados <= set(m.COMANDOS)
    assert "board_list" in usados


def test_fluxo_cita_so_comandos_do_help_real():
    principais, grupos = _comandos_reais()
    citados = []

    for texto in _textos(_fluxo()):
        for achado in RE_COMANDO_CITADO.finditer(texto):
            primeiro, segundo = achado.group(1), achado.group(2)
            citados.append(primeiro)
            if primeiro in grupos:
                assert segundo in grupos[primeiro], (
                    f"simplicio-video {primeiro} {segundo} não existe no --help"
                )
            else:
                assert primeiro in principais, (
                    f"simplicio-video {primeiro} não existe no --help"
                )

    assert "board" in citados, (
        "o fluxo deveria citar 'simplicio-video board list' (leitura do quadro)"
    )
