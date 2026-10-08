---
title: Kernel da fábrica (simplicio_factory)
summary: O que é o kernel da fábrica, os Protocols e dataclasses, transition() como única forma de mudar o estado, JsonStore e MemoryStore, o testkit e o alvo make factory-schema.
commands: make factory-schema
issue: 33
last_verified: 2026-10-08
---

# Kernel da fábrica

O kernel é o núcleo do pacote `src/simplicio_factory/` (issue #33). Ele define os contratos que os plugins usam (Protocols e dataclasses), a máquina de estados do item e o armazenamento local em arquivos. Não conhece vídeo, publicação nem venda: o teste de arquitetura (`tests/factory/test_architecture.py`) garante que o kernel não importa nada disso.

Decisão e divergências em relação ao spec: [ADR-0007](../decisoes/ADR-0007-kernel.md) e [Decisões do MVP](../factory/contracts.md#decisões-do-mvp-divergências-registradas). O spec completo continua em [docs/factory/contracts.md](../factory/contracts.md); aqui fica só o que o MVP implementa. O host de plugins que usa o kernel está em [plugin-host.md](plugin-host.md).

## O que o kernel contém

| Caminho | Conteúdo |
|---|---|
| `contracts/models.py` | `Brand`, `Draft`, `Item`, `Event`, `RenderResult` |
| `contracts/protocols.py` | `Store`, `Renderer`, `Stage` e `StageContract` (base da suíte de contrato) |
| `contracts/transitions.py` | `transition()` e `VALID_TRANSITIONS` |
| `contracts/errors.py` | `InvalidTransition` |
| `contracts/json_store.py` | `JsonStore` (import explícito; não é reexportado por `contracts`) |
| `contracts/schema.py` | gerador de `schemas/factory/item.schema.json` |
| `app.py` | `default_store()`, que devolve um `JsonStore` |
| `testkit/` | `StubRenderer`, `MemoryStore`, `ForbiddenLLM` |

## Dataclasses

- **`Brand`**: `name`, `colors`, `logo` (caminho ou `None`), `facts`. Os fatos são a única fonte de número, preço ou promessa que um Draft pode usar.
- **`Draft`**: `item_id`, `idea`, `facts`, `claims`, `platform`, `duration_s`. É a entrada do estágio.
- **`Item`**: `id`, `brand`, `state` (começa em `idea`) e `failed_from`. Só `transition()` muda `state`.
- **`Event`**: `seq`, `kind`, `item_id`, `data`. É o registro de cada mudança de estado.
- **`RenderResult`**: `mp4_path` e `content_hash`.

## Protocols

- **`Store`**: `save_item`, `get_item`, `list_items`, `append_event`, `read`. Implementado por `JsonStore` e `MemoryStore`.
- **`Renderer`**: `render(contract_path, preview) -> RenderResult`. Implementado pelo renderer do studio e pelo `StubRenderer`.
- **`Stage`**: tem um `name` e `run(item, store)`. Um estágio é idempotente por `(item_id, stage)`.
- **`StageContract`**: classe base abstrata da suíte de contrato de um estágio. A subclasse implementa `make_stage()`.

## Máquina de estados

O MVP tem quatro transições:

| De | Para |
|---|---|
| `idea` | `drafted` |
| `drafted` | `rendering` |
| `rendering` | `rendered` |
| `rendering` | `failed` (grava `failed_from = "rendering"`) |

`failed -> drafted` é inválido no MVP: o retry do spec fica para depois. Qualquer transição fora da tabela levanta `InvalidTransition`, sem mudar o item e sem gravar evento.

```python
from simplicio_factory.contracts import Item, transition
from simplicio_factory.contracts.json_store import JsonStore

store = JsonStore()  # SIMPLICIO_FACTORY_HOME ou .simplicio-factory/
item = Item(id="itm_01HZEXEMPLO0000000000001", brand="clinica-exemplo")
store.save_item(item)
transition(item, "drafted", store)  # grava o item e devolve o Event "item.state_changed"
```

A assinatura é `transition(item, to, store)`. O spec pede `transition(item, to, actor, clock)`; a diferença está registrada no ADR-0007.

## Store: JsonStore e MemoryStore

**`JsonStore`** guarda o estado em `SIMPLICIO_FACTORY_HOME` (padrão `.simplicio-factory/`, ignorada pelo git):

- `items/<id>.json`: estado do item, com o schema `simplicio.factory-item/v1`. A gravação é atômica (arquivo temporário e `os.replace`).
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

O alvo também entra em `make regen`. O schema descreve `id`, `brand`, `state` (`idea`, `drafted`, `rendering`, `rendered`, `failed`) e `failed_from` (`rendering` ou `null`). O nome `simplicio.video-contract/v1` é do contrato do motor de vídeo e não é usado para o estado do item.
