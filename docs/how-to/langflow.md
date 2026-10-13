---
title: Usar o LangFlow como cliente do motor
summary: Receita para instalar o LangFlow à parte, apontar o executável do simplicio-video, importar o componente e o fluxo de exemplo, e rodar ponta a ponta. O LangFlow é cliente externo: o motor não depende dele.
commands: simplicio-video validate, simplicio-video render, simplicio-video status, simplicio-video doctor
issue: 84
last_verified: 2026-10-08
---

# Usar o LangFlow como cliente do motor

Esta receita liga um fluxo do LangFlow ao motor (issue #84, épico #81). O LangFlow é um cliente externo: ele chama o CLI como um programa separado. O motor não depende dele, e nada daqui entra no `.venv` do motor.

Versão do LangFlow: a fixar na primeira execução real; não testado contra uma instalação real nesta entrega.

## O que o componente chama

O componente em [simplicio_component.py](../../examples/langflow/simplicio_component.py) roda só os comandos do CLI que têm `--json`, conferidos no `--help` real (a lista completa está na [referência da CLI](../reference/cli.md)):

| Comando do componente | Chamada no CLI | Para quê |
|---|---|---|
| `validate` | `simplicio-video validate CONTRATO --json` | valida o contrato antes do render |
| `render` | `simplicio-video render CONTRATO --json` | renderiza; `--preview` gera a prévia 540x960 |
| `status` | `simplicio-video status --json` | ferramentas e, com contrato, o estado do render |

O componente não usa shell: cada chamada é uma lista de argumentos. Quando o CLI responde `ok: false`, o componente levanta um erro com o código do motor.

## 1. Instalar o LangFlow à parte

Use um ambiente próprio, separado do `.venv` do motor. Os pré-requisitos de Python e o comando para subir o servidor estão na documentação oficial do LangFlow.

```bash
python3 -m venv ~/langflow-venv
~/langflow-venv/bin/pip install "langflow==<versão a fixar>"
```

Troque `<versão a fixar>` pela versão testada na primeira execução real, e anote-a aqui.

## 2. Apontar o executável do simplicio-video

O executável do motor fica no `.venv` do checkout (ver [instalar e checar](install.md)):

```bash
export SIMPLICIO_VIDEO_BIN="$PWD/.venv/bin/simplicio-video"
"$SIMPLICIO_VIDEO_BIN" doctor
```

O componente procura o executável nesta ordem: o campo `executavel` do próprio nó, a variável `SIMPLICIO_VIDEO_BIN` e, por último, o comando do PATH. Se o LangFlow for iniciado em outro terminal, preencha o campo `executavel` com o caminho absoluto em vez de depender da variável.

## 3. Importar o componente

Copie [simplicio_component.py](../../examples/langflow/simplicio_component.py) para a pasta de componentes personalizados do LangFlow, ou cole o código num componente novo. O módulo importa sem o LangFlow, e a classe `SimplicioVideoComponent` só existe quando o pacote está instalado. Confira no próprio LangFlow se o nó aparece com as entradas `comando`, `contrato`, `executavel`, `need_lock` e `preview`.

## 4. Importar o fluxo de exemplo

Importe [fluxo-exemplo.json](../../examples/langflow/fluxo-exemplo.json) pelo menu de importação de fluxos do LangFlow. Ele tem um nó do componente, **Estado** (`status`). A descrição do fluxo indica como trocar o comando para `validate` ou `render`.

## 5. Exemplo de ponta a ponta

O exemplo usa o contrato do vídeo `video-01-dia-das-criancas` do cliente `lothus-odontologia`. Troque o caminho pelo contrato do seu vídeo.

**No LangFlow, rode o nó Estado (`status`).** O resultado é o JSON do `status --json`, com as ferramentas instaladas e as versões fixadas. Confira que o executável apontado é o do seu checkout.

**Valide o contrato.** No nó Estado, troque `comando` para `validate` e preencha `contrato` com `clients/lothus-odontologia/video-01-dia-das-criancas/contract.yaml`. Rode de novo. A saída é o JSON do `validate --json` (`ok`, `errors`, `warnings`). Um contrato com problema volta como erro `CONTRATO_INVALIDO`, com a lista dos erros na mensagem.

**Renderize a prévia.** Troque `comando` para `render`, ligue `preview` (prévia 540x960 com marca d'água) e rode. O render local roda na sua máquina e pode levar minutos; o componente espera até 3600 s. O resultado traz o `render.manifest.json` gerado ao lado do contrato.

**Confira no terminal.** O mesmo estado aparece no CLI:

```bash
"$SIMPLICIO_VIDEO_BIN" validate clients/lothus-odontologia/video-01-dia-das-criancas/contract.yaml --json
"$SIMPLICIO_VIDEO_BIN" status --json
```

## Erros

Quando a chamada falha, o componente levanta `ErroMotor` com um código e uma mensagem. Os códigos vêm do CLI (`error.code` de `validate` e `render`) ou da própria receita:

| Código | Quando aparece |
|---|---|
| `CONTRATO_NAO_ENCONTRADO`, `CONTRATO_INVALIDO`, `RENDER_FALHOU`, `FERRAMENTA_AUSENTE` | códigos que o CLI devolve em `error.code` |
| `FERRAMENTA_AUSENTE` (da receita) | o executável não existe no caminho dado: aponte `executavel` ou `SIMPLICIO_VIDEO_BIN` |
| `SAIDA_INVALIDA` | o CLI não imprimiu JSON; a mensagem traz o fim do stderr |
| `SAIDA_INESPERADA` | o CLI saiu com erro sem `ok: false` |
| `TEMPO_ESGOTADO` | a chamada passou de 3600 s (o limite do componente) |

## Limites

- Cada chamada roda o CLI de novo: o componente não guarda estado entre execuções.
- Nada desta receita usa LLM, rede ou shell. Os dados ficam no seu checkout.
- O LangFlow é cliente: a licença dele não está em [docs/licenses.md](../licenses.md), e sim na [nota de terceiros](../legal/terceiros.md).
