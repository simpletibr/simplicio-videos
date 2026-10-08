# ADR-0006: host de plugins (manifesto por plugin, descoberta por varredura e despacho por fallback)

- **Status:** aceito. Implementado na issue #32 (`src/simplicio_video/registry.py`, despacho em `cli.py`, comando `plugin list`).
- **Data:** 08/10/2026 (BRT)
- **Relaciona:** [docs/host/plugin-host.md](../host/plugin-host.md) (como usar) · [ADR-0007](ADR-0007-kernel.md) (kernel que os plugins usam) · [ADR-0002](ADR-0002-cli-contrato-colab-creditos.md) (CLI `simplicio-video`) · [ADR-0001](ADR-0001-visao-plugin.md) (plugin do Simplicio Runtime)

## Contexto

A CLI `simplicio-video` tinha todos os subcomandos declarados em `cli.py`. Para a fábrica acrescentar comandos (o studio, depois os demais plugins), cada novo comando teria de editar o `cli.py`, o `--help` e os testes de ajuda. Esse acoplamento faria cada issue de plugin mexer no mesmo arquivo central, o que contraria o acordo de trabalho em paralelo ([parallel-work.md](../factory/parallel-work.md)).

Já existe um `plugin.json` na raiz do repositório, mas ele descreve o repositório como plugin do Simplicio Runtime (`schema: simplicio.plugin/v1`, verbos `video.*`, ADR-0001). É outro contrato, com outro leitor. Usá-lo como registro de comandos misturaria os dois.

## Decisão

1. **Um manifesto por plugin.** Cada plugin de primeira parte tem `src/simplicio_factory/plugins/<id>/plugin.json` com `id`, `kind`, `version` (X.Y.Z), `commands` (lista de `{name, handler, help, example}`) e `stages` (opcional). O schema é `schemas/plugin.manifest.schema.json`.
2. **Descoberta por varredura.** `registry.discover` lê `plugins/*/plugin.json` em ordem de id. Não há lista fixa de plugins no código. Pastas sem manifesto são ignoradas. O id precisa ser igual ao nome da pasta. Um comando repetido, dentro do plugin ou entre plugins, é erro.
3. **Handler importado só no despacho.** O `handler` tem o formato `modulo:funcao`. A descoberta não importa código de plugin; o import acontece quando o comando é chamado.
4. **Despacho por fallback, antes do argparse.** `cli.main` consulta o registro quando o primeiro argumento não começa com `-` e não é subcomando conhecido. O handler recebe os argumentos restantes e o código de saída dele vira o da CLI. O argparse e o `--help` dos subcomandos existentes não mudam.
5. **`plugin list` mostra o que foi descoberto.** Uma linha por plugin, com id, kind e nomes dos comandos. Manifesto inválido sai com código 2.
6. **O `plugin.json` da raiz não é lido pelo registro.** Ele continua sendo o descritor do Simplicio Runtime.

## Consequências

- Adicionar um comando de plugin é criar uma pasta com `plugin.json` e o handler. O `cli.py` não muda, e cada issue de plugin toca só a própria pasta.
- Um manifesto com erro não derruba a CLI inteira: o erro aparece quando o registro é lido (`plugin list` ou a primeira chamada de comando de plugin), com o arquivo e o campo.
- O despacho só roda para nomes que o argparse não conhece: um comando de plugin nunca substitui um subcomando existente. Por isso um plugin não deve escolher o nome de um subcomando do `cli.py`. Essa é uma convenção; o registro não a verifica hoje.
- A descoberta lê o diretório de plugins de primeira parte (`PLUGINS_DIR`). Plugins de terceiros não entram no MVP.

## Alternativas descartadas

- **Lista fixa de comandos em `cli.py`.** Contraria o requisito de não editar o `cli.py` a cada plugin e espalha o acoplamento entre as issues.
- **Reusar o `plugin.json` da raiz como registro.** Ele tem outro schema e outro leitor (o Simplicio Runtime). Misturar os dois faria uma mudança para o runtime quebrar o registro, e o inverso.
- **Importar o handler na descoberta.** Faria `plugin list` executar código de todos os plugins. Só o despacho precisa do handler.
