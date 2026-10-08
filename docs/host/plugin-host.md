---
title: Host de plugins (manifesto, registro e despacho)
summary: Como cada plugin declara os seus comandos no plugin.json, como o registro descobre os plugins, como o despacho roda antes do argparse, e por que o plugin.json da raiz é outro arquivo.
commands: plugin list
issue: 32
last_verified: 2026-10-08
---

# Host de plugins

O host de plugins (issue #32) deixa um plugin acrescentar comandos à CLI `simplicio-video` sem editar `cli.py`. Cada plugin declara os seus comandos num manifesto. O registro descobre os manifestos na pasta de plugins e o despacho chama o handler do comando. Decisão e alternativas: [ADR-0006](../decisoes/ADR-0006-plugin-host.md).

## Manifesto por plugin

Cada plugin de primeira parte tem uma pasta `src/simplicio_factory/plugins/<id>/` com um `plugin.json`. O schema é [schemas/plugin.manifest.schema.json](../../schemas/plugin.manifest.schema.json). Exemplo, o manifesto do studio:

```json
{
  "id": "studio",
  "kind": "studio",
  "version": "0.1.0",
  "commands": [
    {
      "name": "make",
      "handler": "simplicio_factory.plugins.studio.cli:make_cmd",
      "help": "roda o estágio studio do item até rendered; 'make preview ITEM' renderiza 540x960",
      "example": "simplicio-video make ITEM"
    }
  ],
  "stages": []
}
```

| Campo | Regra |
|---|---|
| `id` | começa com letra minúscula; depois, minúsculas, dígitos, `_` e `-`; tem de ser igual ao nome da pasta |
| `kind` | texto não vazio |
| `version` | `X.Y.Z` |
| `commands` | lista de `{name, handler, help, example}`; todos os campos são textos não vazios |
| `commands[].name` | começa com letra minúscula; depois, minúsculas, dígitos e hífen; único entre todos os plugins |
| `commands[].handler` | `modulo:funcao`, importável a partir do pacote |
| `stages` | opcional; lista de textos, default `[]` |

Um manifesto inválido interrompe o registro com uma mensagem que aponta o arquivo e o campo.

## Descoberta

`src/simplicio_video/registry.py` varre `src/simplicio_factory/plugins/*/plugin.json`, em ordem de id. Não há lista fixa de plugins no código. Pastas sem `plugin.json` são ignoradas. Se o `id` do manifesto for diferente do nome da pasta, o registro falha.

O handler só é importado no despacho, nunca na descoberta. Assim, listar os plugins não carrega código de comando.

## `plugin list`

Lista os plugins encontrados, com id, kind e os nomes dos comandos:

```bash
simplicio-video plugin list
```

```text
studio       studio     make, draft
```

Sai com 0. Se algum manifesto estiver inválido, imprime `plugin list: <erro>` em stderr e sai com 2.

## Despacho por fallback

A CLI só consulta o registro quando o primeiro argumento não começa com `-` e não é um subcomando já conhecido pelo argparse. Nesse caso, `cli.main` procura o nome em `commands_index()`, importa o handler e chama `handler(argumentos_restantes)`. O código de saída do handler vira o da CLI.

```bash
simplicio-video make --help        # o handler de make imprime a própria ajuda
simplicio-video draft show ITEM    # o handler de draft recebe ["show", "ITEM"]
```

Os subcomandos existentes (`render`, `validate`, `plugin` e os demais) passam pelo argparse como antes. O despacho acontece antes do argparse, e `tests/test_help.py` confere que o `--help` dos subcomandos existentes continua completo. Um nome que não é de plugin e não é subcomando continua saindo com código 2, pelo argparse.

## O `plugin.json` da raiz é outro arquivo

O `plugin.json` na raiz do repositório descreve este repositório como plugin do Simplicio Runtime: `schema: simplicio.plugin/v1`, `binary: simplicio-video` e os verbos `video.*`. Ele é o contrato do runtime (ADR-0001), não é lido pelo registro e não lista comandos de plugin. O registro só lê `src/simplicio_factory/plugins/*/plugin.json`.

## Testes

- `tests/test_registry.py`: validação do manifesto, descoberta, comando duplicado e handler inválido.
- `tests/test_plugin_host/`: `plugin list`, o despacho para o handler, o código 2 de comando desconhecido e o schema de `schemas/plugin.manifest.schema.json` (`test_manifest_schema.py`).
- `tests/test_help.py`: o `--help` dos subcomandos existentes.
