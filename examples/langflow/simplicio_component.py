"""Componente LangFlow para o motor de vídeo, pela linha de comando (#84, épico #81).

O componente roda só os comandos do CLI que têm --json (conferido no --help real): validate, render,
status e board list. Cada chamada é uma lista de argumentos para subprocess, sem shell e sem texto montado
por concatenação. O JSON que o CLI imprime volta como dicionário. Quando o CLI devolve ok=false, ou quando
não há JSON, a chamada levanta ErroMotor com o código do motor.

O módulo importa sem o LangFlow instalado. As funções puras (montar_argv, interpretar_saida, executar)
não dependem dele; a classe do componente só existe quando LANGFLOW_DISPONIVEL é True. Versão do LangFlow:
a fixar na primeira execução real; não testado contra uma instalação real nesta entrega.

Executável: o campo `executavel` do componente, depois a variável SIMPLICIO_VIDEO_BIN, depois o padrão
`simplicio-video` (do PATH). Receita completa: docs/how-to/langflow.md.
"""

from __future__ import annotations

import json
import os
import subprocess
from typing import Any

try:  # LangFlow é opcional: sem ele, o módulo segue importável e testável.
    from langflow.custom import Component
    from langflow.io import BoolInput, DropdownInput, MessageTextInput, Output
    from langflow.schema import Data

    LANGFLOW_DISPONIVEL = True
except ImportError:
    LANGFLOW_DISPONIVEL = False

EXECUTAVEL_PADRAO = "simplicio-video"
VARIAVEL_EXECUTAVEL = "SIMPLICIO_VIDEO_BIN"
# Limite para o subprocess não travar o fluxo. O render local pode levar minutos.
TIMEOUT_S = 3600

# Comandos do CLI com --json. `make` não tem --json e por isso não entra aqui.
COMANDOS: dict[str, tuple[str, ...]] = {
    "validate": ("validate", "--json"),
    "render": ("render", "--json"),
    "status": ("status", "--json"),
    "board_list": ("board", "list", "--json"),
}
EXIGE_CONTRATO = frozenset({"validate", "render"})
CONTRATO_OPCIONAL = frozenset({"status"})


class ErroMotor(RuntimeError):
    """Falha do motor: `codigo` é o error.code do CLI (ou um código da própria receita)."""

    def __init__(self, codigo: str, mensagem: str):
        self.codigo = codigo
        self.mensagem = mensagem
        super().__init__(f"simplicio-video [{codigo}]: {mensagem}")


def _executavel(valor: Any) -> str:
    escolhido = (
        os.fspath(valor)
        if valor
        else os.environ.get(VARIAVEL_EXECUTAVEL) or EXECUTAVEL_PADRAO
    )
    if not escolhido.strip() or "\x00" in escolhido:
        raise ValueError(f"executável inválido: {escolhido!r}")
    return escolhido


def _caminho(valor: Any) -> str:
    texto = os.fspath(valor)
    # Um caminho que começa com "-" seria lido pelo CLI como opção; recusamos.
    if not texto.strip() or texto.startswith("-") or "\x00" in texto:
        raise ValueError(f"caminho de contrato inválido: {texto!r}")
    return texto


def montar_argv(
    comando: str,
    *,
    contrato: Any = None,
    executavel: Any = None,
    need_lock: bool = False,
    preview: bool = False,
) -> list[str]:
    """Monta a lista de argumentos. Cada parte é um item da lista; nada é juntado em texto."""
    if comando not in COMANDOS:
        raise ValueError(
            f"comando desconhecido: {comando!r} (use um de {sorted(COMANDOS)})"
        )
    if comando in EXIGE_CONTRATO and contrato is None:
        raise ValueError(f"{comando} precisa do caminho do contrato")
    if contrato is not None and comando not in EXIGE_CONTRATO | CONTRATO_OPCIONAL:
        raise ValueError(f"{comando} não recebe contrato")
    if need_lock and comando != "validate":
        raise ValueError("need_lock só vale para validate")
    if preview and comando != "render":
        raise ValueError("preview só vale para render")

    argv = [_executavel(executavel), *COMANDOS[comando]]
    if need_lock:
        argv.append("--need-lock")
    if preview:
        argv.append("--preview")
    if contrato is not None:
        argv.append(_caminho(contrato))
    return argv


def _erro_do_payload(payload: dict[str, Any]) -> tuple[str, str]:
    erro = payload.get("error")
    if isinstance(erro, dict):
        return str(erro.get("code") or "ERRO_MOTOR"), str(
            erro.get("message") or "sem mensagem"
        )
    errors = payload.get("errors") or []
    if errors:
        return "CONTRATO_INVALIDO", "; ".join(str(item) for item in errors)
    return "ERRO_MOTOR", "falha sem detalhe"


def interpretar_saida(
    comando: str, returncode: int, stdout: str, stderr: str = ""
) -> dict[str, Any]:
    """Transforma a saída do CLI em dicionário, ou em ErroMotor quando o motor reportou falha."""
    try:
        payload = json.loads(stdout or "")
    except json.JSONDecodeError as exc:
        trecho = (stderr or stdout or "").strip()[-300:]
        raise ErroMotor(
            "SAIDA_INVALIDA",
            f"{comando}: o CLI não imprimiu JSON (código {returncode}). {trecho}",
        ) from exc
    if not isinstance(payload, dict):
        raise ErroMotor("SAIDA_INVALIDA", f"{comando}: o JSON não é um objeto")
    if payload.get("ok") is False:
        raise ErroMotor(*_erro_do_payload(payload))
    if returncode != 0:
        raise ErroMotor(
            "SAIDA_INESPERADA", f"{comando}: código {returncode} sem ok=false"
        )
    return payload


def executar(
    comando: str,
    *,
    contrato: Any = None,
    executavel: Any = None,
    need_lock: bool = False,
    preview: bool = False,
) -> dict[str, Any]:
    """Roda um comando do CLI com --json e devolve o JSON. Não usa shell."""
    argv = montar_argv(
        comando,
        contrato=contrato,
        executavel=executavel,
        need_lock=need_lock,
        preview=preview,
    )
    try:
        resultado = subprocess.run(
            argv,
            shell=False,
            capture_output=True,
            text=True,
            timeout=TIMEOUT_S,
            check=False,
        )
    except FileNotFoundError as exc:
        raise ErroMotor(
            "FERRAMENTA_AUSENTE",
            f"executável não encontrado: {argv[0]!r}. Instale o pacote (simplicio-video) ou aponte o caminho "
            f"(campo executavel ou {VARIAVEL_EXECUTAVEL}).",
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise ErroMotor("TEMPO_ESGOTADO", f"{comando} passou de {TIMEOUT_S} s") from exc
    return interpretar_saida(
        comando, resultado.returncode, resultado.stdout, resultado.stderr
    )


if LANGFLOW_DISPONIVEL:

    class SimplicioVideoComponent(Component):
        display_name = "simplicio-video"
        description = "Chama o CLI do motor (só comandos com --json) e devolve o JSON."
        icon = "video"
        name = "SimplicioVideoComponent"

        inputs = [
            DropdownInput(
                name="comando",
                display_name="Comando",
                options=list(COMANDOS),
                value="board_list",
                info="board_list lê o quadro; status mostra o estado do motor.",
            ),
            MessageTextInput(
                name="contrato",
                display_name="Contrato (YAML)",
                value="",
                info="Obrigatório para validate e render; opcional para status.",
            ),
            MessageTextInput(
                name="executavel",
                display_name="Executável",
                value="",
                info="Vazio = SIMPLICIO_VIDEO_BIN; sem ela, o executável do PATH.",
            ),
            BoolInput(
                name="need_lock", display_name="Exigir timing.lock.json", value=False
            ),
            BoolInput(
                name="preview", display_name="Prévia 540x960 (render)", value=False
            ),
        ]
        outputs = [Output(display_name="Resultado", name="resultado", method="rodar")]

        def rodar(self) -> Data:
            comando = self.comando
            usa_contrato = comando in EXIGE_CONTRATO | CONTRATO_OPCIONAL
            contrato = (self.contrato or None) if usa_contrato else None
            payload = executar(
                comando,
                contrato=contrato,
                executavel=self.executavel or None,
                need_lock=bool(self.need_lock) and comando == "validate",
                preview=bool(self.preview) and comando == "render",
            )
            return Data(data=payload)
