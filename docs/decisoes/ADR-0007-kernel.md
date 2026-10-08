# ADR-0007: kernel da fábrica (contratos, transition(), JsonStore e testkit)

- **Status:** aceito. Implementado na issue #33 (`src/simplicio_factory/contracts/`, `testkit/`, `make factory-schema`).
- **Data:** 08/10/2026 (BRT)
- **Relaciona:** [docs/host/kernel.md](../host/kernel.md) (como usar) · [docs/factory/contracts.md](../factory/contracts.md) (spec, com a seção "Decisões do MVP") · [ADR-0006](ADR-0006-plugin-host.md) (host que usa o kernel) · [ADR-0001](ADR-0001-visao-plugin.md) (LLM nunca no caminho padrão) · [ADR-0005](ADR-0005-gate-sem-ci.md) (gate local)

## Contexto

O spec da fábrica (`docs/factory/contracts.md`) define o modelo completo: Store com eventos, jobs, políticas, publicação e uma máquina de estados com mais de quinze transições. O MVP da M0a precisa de menos que isso para provar o fluxo do studio (#16): um item sai de `idea`, passa por `drafted`, `rendering` e chega a `rendered` ou `failed`, com eventos e sem LLM.

Havia três lacunas e algumas divergências. O spec assina `transition(item, to, actor, clock)`, mas o MVP não tem atores nem relógio injetado. O spec pede o estado do item como `simplicio.item/v1`, que colide com outras partes do contrato. E o spec não diz onde ficam o estado de cada estágio nem o `content_hash`.

## Decisão

1. **Dataclasses e Protocols mínimos.** `contracts/` define `Brand`, `Draft`, `Item`, `Event`, `RenderResult` e os Protocols `Store`, `Renderer`, `Stage` e `StageContract`. Só o que o studio usa.
2. **`transition(item, to, store)` é a única forma de mudar o estado.** O grafo do MVP tem quatro transições: `idea -> drafted`, `drafted -> rendering`, `rendering -> rendered` e `rendering -> failed`. `failed -> drafted` é inválido, sem mudar o item e sem gravar evento. Cada transição grava o item e emite `item.state_changed` pelo `store.append_event`.
3. **Store em arquivos e em memória.** `JsonStore` grava um arquivo por item (`items/<id>.json`, schema `simplicio.factory-item/v1`) e um log `events.jsonl`, em `SIMPLICIO_FACTORY_HOME` (padrão `.simplicio-factory/`, ignorado pelo git). `MemoryStore` é o do testkit. Nenhum outro backend no MVP. O store real (#35) entra depois, pelo mesmo Protocol.
4. **Schema do item próprio.** `schemas/factory/item.schema.json` usa o título `simplicio.factory-item/v1` e é gerado por `make factory-schema` (`FACTORY_SCHEMA_OUT` troca o caminho de saída). O nome `simplicio.video-contract/v1` continua sendo o do contrato do motor.
5. **O kernel guarda só o estado do item.** O estado de cada estágio fica na pasta do item: `studio.json` (com o `content_hash`) e `draft.json` (o Draft). O `item.json` não ganha campos do estúdio.
6. **Testkit para testes sem rede e sem HyperFrames.** `StubRenderer` grava bytes determinísticos, `MemoryStore` guarda em memória e `ForbiddenLLM` falha se for chamado. O caminho determinístico é provado com `ForbiddenLLM` injetado.
7. **O MVP devolve só o que usa.** `Renderer.render(contract_path, preview)` devolve `RenderResult(mp4_path, content_hash)`. Os campos `manifest_path` e `duration_s` do spec não entram agora.

As divergências em relação ao spec estão listadas na seção "Decisões do MVP (divergências registradas)" de [contracts.md](../factory/contracts.md#decisões-do-mvp-divergências-registradas). Esta ADR registra a decisão; o spec continua como referência do modelo completo.

## Consequências

- A assinatura `transition(item, to, store)` é diferente da do spec. Quando o ator e o relógio forem necessários (aprovação humana, `failed -> drafted`), a função muda de assinatura. Hoje o único chamador é o estágio do studio, e ele muda junto.
- O grafo do MVP não tem `discarded`, `in_review`, `approved` nem `scheduled`. Essas transições entram com os plugins que precisam delas, cada uma com teste.
- O estado do item e o do estágio ficam em arquivos separados. Quem lê o estado completo de um item precisa olhar a pasta do item, não só o `item.json`.
- O `content_hash` não está no `item.json`. Um item já `rendered` não é re-renderizado mesmo que o Draft mude (ver as pendências em [studio.md](../plugins/studio.md)).
- Como o schema do item é gerado, `make regen` precisa estar em dia antes de mudar o `Item` ou o `JsonStore`.

## Alternativas descartadas

- **Implementar o grafo completo do spec agora.** Adicionaria estados e transições que nenhum plugin do MVP usa, sem teste.
- **Reaproveitar `simplicio.video-contract/v1` como schema do item.** Mistura o contrato do motor com o estado da fábrica; o nome é do motor.
- **Guardar o estado do estúdio dentro de `item.json`.** Acoplaria o kernel a um plugin. O kernel fica sem conhecer o studio.
