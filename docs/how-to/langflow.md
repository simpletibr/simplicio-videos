---
title: Usar o LangFlow como cliente do motor
summary: Receita para instalar o LangFlow à parte, apontar o executável do simplicio-video, importar o componente e o fluxo de exemplo, e rodar ponta a ponta. O LangFlow é cliente externo: o motor não depende dele.
commands: simplicio-video make, simplicio-video board list, simplicio-video board review, simplicio-video validate, simplicio-video render, simplicio-video status, simplicio-video doctor
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
| `board_list` | `simplicio-video board list --json` | lê o quadro dos itens |

`make` não tem `--json`, então o componente não o chama. A criação do item continua no terminal, com `simplicio-video make --from DRAFT.JSON`. O componente não usa shell: cada chamada é uma lista de argumentos. Quando o CLI responde `ok: false`, o componente levanta um erro com o código do motor.

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

Importe [fluxo-exemplo.json](../../examples/langflow/fluxo-exemplo.json) pelo menu de importação de fluxos do LangFlow. Ele tem dois nós do componente: **Quadro** (`board_list`) e **Estado** (`status`). A descrição do fluxo lembra o passo de criação do item, que fica no terminal.

## 5. Exemplo de ponta a ponta

O exemplo usa o Draft e a marca de [studio](../plugins/studio.md), com o id `itm_01HZEXEMPLO0000000000001`. Troque pelo id do seu item.

**No terminal, crie o item e confira o quadro:**

```bash
simplicio-video make --from draft.json --brand brand.json
# saída: itm_01HZEXEMPLO0000000000001: rendered (e o caminho do MP4)

simplicio-video board list --json > quadro.json
```

**No LangFlow, rode o nó Quadro.** O resultado é o mesmo JSON do `board list --json` (schema `simplicio.board/v1`). O cartão aparece em Revisão, porque o estado é `rendered` e ainda não há revisão aprovada ([board](../plugins/board.md)).

**Aprove a revisão no terminal:**

```bash
simplicio-video board review itm_01HZEXEMPLO0000000000001 approve --by Ana --note "pode publicar"
```

**De novo no LangFlow, rode o nó Quadro.** O cartão agora está em Pronto.

**Valide um contrato (opcional).** No nó Quadro, troque `comando` para `validate` e preencha `contrato` com o caminho do YAML. A saída é o JSON do `validate --json`, e um contrato inválido vira erro com o código `CONTRATO_INVALIDO` ou `CONTRATO_NAO_ENCONTRADO`.

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
- O quadro não tem trava de escrita. Com dois escritores ao mesmo tempo, um comentário ou uma revisão pode se perder ([ressalvas do board](../plugins/board.md#ressalvas)).
- Nada desta receita usa LLM, rede ou shell. Os dados ficam no seu checkout.
- O LangFlow é cliente: a licença dele não está em [docs/licenses.md](../licenses.md), e sim na [nota de terceiros](../legal/terceiros.md).
