---
title: Kernel da fábrica (simplicio_factory)
summary: O que é o kernel da fábrica, os Protocols e dataclasses, transition() como única forma de mudar o estado, JsonStore e MemoryStore, o testkit e o alvo make factory-schema.
commands: make factory-schema
issue: 33
last_verified: 2026-10-08
---

# Kernel da fábrica

O kernel é o núcleo do pacote `src/simplicio_factory/` (issue #33). Ele define os contratos que os plugins usam (Protocols e dataclasses), a máquina de estados do item e o armazenamento local em arquivos. Não conhece vídeo, publicação nem venda: o teste de arquitetura (`tests/factory/test_architecture.py`) garante que o kernel não importa nada disso.

Decisão e divergências em relação ao spec: [ADR-0007](../decisoes/ADR-0007-kernel.md), e as duas rotas de produção em [ADR-0008](../decisoes/ADR-0008-duas-rotas.md) (issue #82, épico #81). [Decisões do MVP](../factory/contracts.md#decisões-do-mvp-divergências-registradas). O spec completo continua em [docs/factory/contracts.md](../factory/contracts.md); aqui fica só o que o MVP implementa. O host de plugins que usa o kernel está em [plugin-host.md](plugin-host.md).

## O que o kernel contém

| Caminho | Conteúdo |
|---|---|
| `contracts/models.py` | `Brand`, `Draft`, `Item`, `Event`, `RenderResult`; as constantes `STATES`, `ROUTES`, `REVIEW_VALUES` e `DEFAULT_ROUTE` |
| `contracts/protocols.py` | `Store`, `Renderer`, `Stage` e `StageContract` (base da suíte de contrato) |
| `contracts/transitions.py` | `transition()`, `transitions_for(route)`, os grafos `DETERMINISTIC_TRANSITIONS` e `AI_ASSISTED_TRANSITIONS` e `VALID_TRANSITIONS` (alias do grafo determinístico) |
| `contracts/errors.py` | `InvalidTransition` |
| `contracts/json_store.py` | `JsonStore` (import explícito; não é reexportado por `contracts`) |
| `contracts/schema.py` | gerador de `schemas/factory/item.schema.json` |
| `app.py` | `default_store()`, que devolve um `JsonStore` |
| `testkit/` | `StubRenderer`, `MemoryStore`, `ForbiddenLLM` |

## Dataclasses

- **`Brand`**: `name`, `colors`, `logo` (caminho ou `None`), `facts`. Os fatos são a única fonte de número, preço ou promessa que um Draft pode usar.
- **`Draft`**: `item_id`, `idea`, `facts`, `claims`, `platform`, `duration_s`. É a entrada do estágio.
- **`Item`**: `id`, `brand`, `state` (começa em `idea`), `failed_from`, `production` e `review`. Só `transition()` muda `state`.
  - `production`: `route` (`deterministic` por padrão, ou `ai_assisted`) e `steps` (lista de passos; o passo `ai_media` leva `kind` e `provider`).
  - `review`: `null` (sem revisão) ou um de `pending`, `approved`, `changes_requested`.
  - `production` e `review` são validados na construção: uma rota ou uma revisão fora da lista levanta `ValueError`.
- **`Event`**: `seq`, `kind`, `item_id`, `data`. Cada mudança de estado grava `item.state_changed` com `from`, `to` e `route` (ver [Rotas de produção](#rotas-de-produção)).
- **`RenderResult`**: `mp4_path` e `content_hash`.

## Protocols

- **`Store`**: `save_item`, `get_item`, `list_items`, `append_event`, `read`. Implementado por `JsonStore` e `MemoryStore`.
- **`Renderer`**: `render(contract_path, preview) -> RenderResult`. Implementado pelo renderer do studio e pelo `StubRenderer`.
- **`Stage`**: tem um `name` e `run(item, store)`. Um estágio é idempotente por `(item_id, stage)`.
- **`StageContract`**: classe base abstrata da suíte de contrato de um estágio. A subclasse implementa `make_stage()`.

## Rotas de produção

Cada item segue o grafo da sua rota, dada por `item.production["route"]`. `transitions_for(route)` (em `simplicio_factory.contracts.transitions`) devolve os pares `(de, para)` válidos na rota. `transition()` usa o grafo da rota do item: qualquer par fora dele levanta `InvalidTransition`, sem mudar o item e sem gravar evento. A decisão está no [ADR-0008](../decisoes/ADR-0008-duas-rotas.md).

### Rota `deterministic` (padrão, sem LLM)

É a esteira da #33, sem mudança. Nenhum LLM entra nesse caminho.

| De | Para |
|---|---|
| `idea` | `drafted` |
| `drafted` | `rendering` |
| `rendering` | `rendered` |
| `rendering` | `failed` (grava `failed_from = "rendering"`) |

`failed -> drafted` é inválido: o retry do spec fica para depois.

### Rota `ai_assisted` (issue #82)

Geração por IA com gasto aprovado por um humano. A estimativa vem antes da confirmação, e a confirmação vem antes da geração.

| De | Para |
|---|---|
| `idea` | `drafted` |
| `drafted` | `quoted` (a estimativa; exige o passo `ai_media`, ver abaixo) |
| `quoted` | `drafted` (volta antes da confirmação) |
| `quoted` | `approved` (a confirmação humana do gasto) |
| `approved` | `generating` |
| `generating` | `generated` |
| `generating` | `failed` (grava `failed_from = "generating"`) |
| `generated` | `rendering` |
| `rendering` | `rendered` |
| `rendering` | `failed` (grava `failed_from = "rendering"`) |

- `drafted -> quoted` lê `production["steps"]`: precisa de um passo com `kind: "ai_media"` e `provider` com texto não vazio. Sem ele, `InvalidTransition`.
- Nenhum caminho leva de `quoted` a `generating` sem passar por `approved`.
- O kernel não chama provedor de mídia. Ele valida e grava as transições; a estimativa e a confirmação de gasto acontecem no serviço de geração.

```python
from simplicio_factory.contracts import Item, transition
from simplicio_factory.contracts.json_store import JsonStore

store = JsonStore()
item = Item(
    id="itm_01HZEXEMPLO0000000000002",
    brand="clinica-exemplo",
    production={"route": "ai_assisted", "steps": [{"kind": "ai_media", "provider": "provedor-exemplo"}]},
)
store.save_item(item)
transition(item, "drafted", store)
transition(item, "quoted", store)  # só passa porque há o passo ai_media com provider
```

### Revisão (`review`)

`item.review` registra a revisão humana do conteúdo: `null`, `pending`, `approved` ou `changes_requested`. Nesta versão `transition()` não lê `review`, então o grafo não exige revisão aprovada antes de gerar. Se essa regra for exigida, ela entra em `transition()` com teste próprio.

### Evento `item.state_changed`

Cada transição grava um evento `item.state_changed` com `{"from": ..., "to": ..., "route": ...}`. O campo `route` diz qual grafo valia na mudança.

A assinatura é `transition(item, to, store)`. O spec pede `transition(item, to, actor, clock)`; a diferença está registrada no ADR-0007.

## Store: JsonStore e MemoryStore

**`JsonStore`** guarda o estado em `SIMPLICIO_FACTORY_HOME` (padrão `.simplicio-factory/`, ignorada pelo git):

- `items/<id>.json`: estado do item, com o schema `simplicio.factory-item/v1`, incluindo `production` e `review` (que voltam iguais na leitura). A gravação é atômica (arquivo temporário e `os.replace`).
- `events.jsonl`: log de eventos em JSON Lines, um por linha, com `seq` crescente.

O id do item só aceita `[A-Za-z0-9_-]+`. O kernel guarda só o estado do item; o estado de cada estágio fica na pasta do item (no studio, [studio.md](../plugins/studio.md)). No MVP não há outro backend.

**`MemoryStore`** (testkit) tem a mesma interface, em memória, e devolve cópias, como um store real.

## Testkit

Importado de `simplicio_factory.testkit`:

- **`StubRenderer(out_dir)`**: grava bytes determinísticos derivados do contrato (um cabeçalho `STUB-MP4` seguido do próprio contrato). O nome do arquivo usa os 16 primeiros caracteres do sha256 do contrato. Não chama o HyperFrames.
- **`MemoryStore()`**: o store em memória descrito acima.
- **`ForbiddenLLM()`**: o método `complete()` levanta `AssertionError`. Os testes injetam esse dublê para provar que o caminho determinístico não chama LLM.

## Schema do item (`make factory-schema`)

`schemas/factory/item.schema.json` é gerado por `simplicio_factory.contracts.schema`. Não edite o JSON à mão.

```bash
make factory-schema                                       # regrava schemas/factory/item.schema.json
make factory-schema FACTORY_SCHEMA_OUT=out/item.schema.json  # grava em outro caminho (usado pelos testes)
```

O alvo também entra em `make regen`. O schema descreve `id`, `brand`, `state` (os nove estados: `idea`, `drafted`, `quoted`, `approved`, `generating`, `generated`, `rendering`, `rendered`, `failed`), `failed_from` (`rendering`, `generating` ou `null`), `production` (`route` e `steps`) e `review` (`null` ou um dos três valores). O nome `simplicio.video-contract/v1` é do contrato do motor de vídeo e não é usado para o estado do item.
