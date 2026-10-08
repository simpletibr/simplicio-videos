---
title: Board (quadro kanban dos itens)
summary: O quadro de itens da fábrica, com oito colunas derivadas de state e review (nunca guardadas), os comandos board list, board comment e board review, o arquivo comments.jsonl, as regras de revisão, o schema simplicio.board/v1 e as ressalvas de escritores concorrentes.
commands: board list, board comment, board review
issue: 86
last_verified: 2026-10-08
---

# Board (quadro kanban dos itens)

O board (issue #86, épico #81) mostra os itens da fábrica como um quadro kanban. Cada item vira um cartão, e a coluna do cartão sai do estado do item (`state`) e da revisão humana (`review`). Ele também guarda comentários e a revisão do vídeo renderizado. Não há LLM nem rede no caminho padrão.

Código: `src/simplicio_factory/plugins/board/`. Comandos declarados em [plugin.json](../../src/simplicio_factory/plugins/board/plugin.json) e registrados pelo host ([plugin-host.md](../host/plugin-host.md)). Estado dos itens e o grafo de transições: [kernel.md](../host/kernel.md).

O board não move cartão de etapa. Para mudar a coluna de um item, o estado dele muda pelo estágio que o produz (`transition()`); o board só lê. A única coisa que ele grava no item é `review`.

## Colunas

As colunas são derivadas. Nenhum item guarda a coluna: ela sai de `state`, e só para `rendered` também de `review`.

| Coluna | Chave | Estado (`state`) | Condição extra | Rotas |
|---|---|---|---|---|
| Ideia | `ideia` | `idea` | | deterministic, ai_assisted |
| Roteiro | `roteiro` | `drafted` | | deterministic, ai_assisted |
| Orçamento | `orcamento` | `quoted` | | ai_assisted |
| Aprovado | `aprovado` | `approved` | | ai_assisted |
| Gerando | `gerando` | `generating`, `generated`, `rendering` | | deterministic (só `rendering`), ai_assisted |
| Revisão | `revisao` | `rendered` | `review` não é `approved` | deterministic, ai_assisted |
| Pronto | `pronto` | `rendered` | `review` é `approved` | deterministic, ai_assisted |
| Falhou | `falhou` | `failed` | | deterministic, ai_assisted |

A rota determinística passa só por Ideia, Roteiro, Gerando (`rendering`), Revisão e Pronto. Falhou é o caminho de erro do render. A rota `ai_assisted` também passa por Orçamento e Aprovado, e por `generating` e `generated` em Gerando. A ordem das colunas no quadro é a da tabela.

## Comandos

| Comando | Para quê |
|---|---|
| `simplicio-video board list [--json]` | mostra as oito colunas e os cartões; com `--json`, imprime o quadro em JSON |
| `simplicio-video board comment ITEM "texto" --by NOME` | grava um comentário no item |
| `simplicio-video board review ITEM approve\|changes --by NOME [--note TEXTO]` | aprova ou pede alterações no vídeo renderizado |

Cada comando tem `--help` com exemplo. O estado vem de `SIMPLICIO_FACTORY_HOME` (padrão `.simplicio-factory/`, gitignored).

### `board list`

```bash
simplicio-video board list
```

```text
Ideia (0)
  (vazia)
Roteiro (1)
  itm_SMOKE000000000000002  acme  [drafted]  rota=deterministic  comentários=1
Orçamento (0)
  (vazia)
Aprovado (0)
  (vazia)
Gerando (0)
  (vazia)
Revisão (0)
  (vazia)
Pronto (1)
  itm_SMOKE000000000000001  acme  [rendered]  rota=deterministic  comentários=1  review=approved
Falhou (0)
  (vazia)
```

Cada cartão mostra o id, a marca, o estado, a rota, o número de comentários e, se houver, o `review`. A ordem é fixa: colunas na ordem da tabela, cartões por id.

Com `--json`, a saída é determinística (sem horário, mesma entrada, mesmos bytes) e valida contra o schema [board.schema.json](../../schemas/factory/board.schema.json):

```bash
simplicio-video board list --json > quadro.json
```

```json
{
  "schema": "simplicio.board/v1",
  "columns": [
    {"id": "ideia", "title": "Ideia", "cards": []},
    {"id": "roteiro", "title": "Roteiro", "cards": [
      {"id": "itm_SMOKE000000000000002", "brand": "acme", "state": "drafted",
       "route": "deterministic", "review": null, "failed_from": null, "comments": 1}
    ]},
    "..."
  ]
}
```

A lista tem sempre as oito colunas, mesmo vazias. O cartão tem os sete campos do schema: `id`, `brand`, `state`, `route`, `review`, `failed_from` e `comments`.

### `board comment`

```bash
simplicio-video board comment itm_01HZEXEMPLO0000000000001 "Trocar a cor do logo" --by Bruno
```

```text
itm_01HZEXEMPLO0000000000001: comentário 1 registrado
```

`--by` é obrigatório: sem ele, o comando sai com código 2 e não grava nada. O texto e o autor não podem ser vazios. O item precisa existir.

### `board review`

```bash
simplicio-video board review itm_01HZEXEMPLO0000000000001 approve --by Ana --note "pode publicar"
simplicio-video board review itm_01HZEXEMPLO0000000000001 changes --by Ana --note "refazer o final"
```

- `approve` define `review: approved`. O cartão vai de Revisão para Pronto.
- `changes` define `review: changes_requested`. O cartão fica em Revisão.
- A revisão só vale para item em estado `rendered`. Em outro estado, o comando falha e não muda nada.
- Revisar de novo substitui o `review` anterior. Por exemplo, `changes` seguido de `approve` leva o cartão a Pronto.
- Sem `--note`, a linha de revisão leva um texto padrão (`aprovado` ou `alterações solicitadas`).

## Comentários (`comments.jsonl`)

Os comentários ficam em `<SIMPLICIO_FACTORY_HOME>/items/<id>/comments.jsonl`, um objeto JSON por linha. O arquivo é append-only: cada comando só acrescenta uma linha, e as linhas antigas não são reescritas.

```json
{"id": 1, "at": "2026-10-08T10:00:00-03:00", "by": "Bruno", "kind": "comment", "text": "Trocar a cor do logo"}
{"id": 2, "at": "2026-10-08T10:05:00-03:00", "by": "Ana", "kind": "review", "text": "pode publicar"}
```

| Campo | Valor |
|---|---|
| `id` | posição da linha, a partir de 1 |
| `at` | horário de Brasília, ISO 8601 (`-03:00`) |
| `by` | quem escreveu (de `--by`) |
| `kind` | `comment` (de `board comment`) ou `review` (de `board review`) |
| `text` | o texto do comentário ou a nota da revisão |

Os comentários não mudam estado nem coluna. O board conta os comentários de cada item para mostrar o número no cartão.

## Schema do quadro

`schemas/factory/board.schema.json` é gerado por `make factory-schema`, que também grava `item.schema.json`. O gerador é [simplicio_factory/plugins/board/schema.py](../../src/simplicio_factory/plugins/board/schema.py), chamado por [contracts/schema.py](../../src/simplicio_factory/contracts/schema.py). Não edite o JSON à mão. O schema fixa as oito colunas na ordem (`prefixItems`) e os valores de `state`, `route` e `review`.

## Ressalvas

- **Escritores concorrentes.** Duas escritas no mesmo item ao mesmo tempo (dois `comment`, ou um `comment` e um `review`) podem se atropelar: o id da linha é calculado pelo número de linhas do arquivo, e o `review` é gravado com regravação do JSON do item. A CLI não tem trava de arquivo. O servidor (issue #89) é quem serializa as escritas; até lá, use um escritor por vez.
- **Sem visualização HTML.** O board entrega o quadro em texto e em JSON. Uma tela para o quadro fica fora deste plugin.
- **Coluna não se edita.** Não há comando para mover cartão. Para mudar a coluna, muda-se o estado do item pelo estágio que o produz.
