"""Receita LangFlow para chamar o motor (#84, épico #81).

O componente em examples/langflow/simplicio_component.py chama o CLI simplicio-video só com comandos que têm
--json (validate, render, status), por lista de argumentos e sem shell. Estes testes trocam o subprocess por um falso e não precisam do
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
def _existe(*comando: str) -> bool:
    """O comando existe se o --help dele sai com 0 e começa com o próprio nome."""
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
    return resultado.returncode == 0 and resultado.stdout.startswith(
        f"usage: simplicio-video {' '.join(comando)}"
    )


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
        m.executar("board", contrato="c.yaml")
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


def test_fluxo_so_usa_comandos_do_componente():
    m = _modulo()
    componentes = [
        no
        for no in _fluxo()["data"]["nodes"]
        if no["data"]["type"] == "SimplicioVideoComponent"
    ]
    usados = {no["data"]["node"]["template"]["comando"]["value"] for no in componentes}

    assert usados, "o fluxo não tem nenhum nó com comando"
    assert usados <= set(m.COMANDOS)


def test_fluxo_cita_so_comandos_do_help_real():
    citados = 0

    for texto in _textos(_fluxo()):
        for achado in RE_COMANDO_CITADO.finditer(texto):
            citados += 1
            primeiro = achado.group(1)
            assert _existe(primeiro), f"simplicio-video {primeiro} não existe no --help"

    assert citados, "o fluxo não cita nenhum comando"


# ----------------------------------------------------------------- receita e nota legal

RECEITA = ROOT / "docs" / "how-to" / "langflow.md"
INDICE_GUIAS = ROOT / "docs" / "how-to" / "README.md"
TERCEIROS = ROOT / "docs" / "legal" / "terceiros.md"
LICENCAS = ROOT / "docs" / "licenses.md"
VERSAO_PENDENTE = (
    "versão do LangFlow: a fixar na primeira execução real; "
    "não testado contra uma instalação real nesta entrega"
)


def _receita() -> str:
    assert RECEITA.is_file(), "falta docs/how-to/langflow.md"
    return RECEITA.read_text(encoding="utf-8")


def test_receita_tem_front_matter_do_padrao():
    cabecalho = re.match(r"^---\n(.*?)\n---\n", _receita(), re.S)
    assert cabecalho, "a receita não tem front matter"
    for chave in ("title:", "summary:", "commands:", "issue: 84", "last_verified:"):
        assert chave in cabecalho.group(1), f"front matter sem {chave}"


def test_receita_esta_linkada_no_indice_de_guias():
    assert "(langflow.md)" in INDICE_GUIAS.read_text(encoding="utf-8")


def test_receita_registra_a_versao_pendente_sem_inventar_versao():
    texto = _receita()
    assert VERSAO_PENDENTE.lower() in texto.lower()
    assert not re.search(r"langflow\s*[=<>~!]*\s*\d+\.\d+", texto, re.I), (
        "versão do LangFlow inventada"
    )


def test_receita_cita_so_comandos_do_help_real():
    citados = 0
    for achado in RE_COMANDO_CITADO.finditer(_receita()):
        citados += 1
        primeiro = achado.group(1)
        assert _existe(primeiro), f"simplicio-video {primeiro} não existe no --help"
    assert citados, "a receita não cita nenhum comando"


def test_receita_linka_os_arquivos_da_pasta_examples():
    texto = _receita()
    assert "../../examples/langflow/simplicio_component.py" in texto
    assert "../../examples/langflow/fluxo-exemplo.json" in texto


def test_terceiros_marca_langflow_como_cliente_externo_fora_do_licenses():
    partes = TERCEIROS.read_text(encoding="utf-8").split("## LangFlow", 1)
    assert len(partes) == 2, "terceiros.md sem a seção LangFlow"
    corpo = partes[1].split("\n## ", 1)[0].lower()
    assert "não empacotado" in corpo
    assert "licenses.md" in corpo
    assert "langflow" not in LICENCAS.read_text(encoding="utf-8").lower()
