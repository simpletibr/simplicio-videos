# ADR-0008: duas rotas de produção no item (determinística intocada e ai_assisted com gasto aprovado)

- **Status:** aceito. Implementado na issue #82 (`src/simplicio_factory/contracts/models.py`, `transitions.py`, `schema.py`, `json_store.py` e `schemas/factory/item.schema.json`), dentro do épico #81.
- **Data:** 08/10/2026 (BRT)
- **Relaciona:** [docs/host/kernel.md](../host/kernel.md) (como usar) · [ADR-0007](ADR-0007-kernel.md) (kernel, que esta decisão estende) · [ADR-0001](ADR-0001-visao-plugin.md) (LLM nunca no caminho padrão) · [ADR-0004](ADR-0004-ugc-generativo.md) (trilha generativa fora do render determinístico) · épico #81

## Contexto

A esteira determinística (ADR-0007) produz vídeo sem LLM: um item sai de `idea`, passa por `drafted` e `rendering` e chega a `rendered` ou `failed`. Esse é o caminho padrão e continua sendo.

Ao mesmo tempo, o Real Oficial gera vídeo com IA, e cada geração gasta créditos. Pela regra desse serviço, qualquer ação que gasta créditos é cotada antes e só roda depois de confirmada pelo usuário. Um item que usa geração por IA precisa, então, de três coisas que o grafo determinístico não tem: um passo que diga qual provedor de mídia será usado, uma estimativa registrada antes de qualquer gasto, e uma confirmação humana registrada antes da geração. O grafo do MVP não tem estados para geração, falha de geração nem aprovação de gasto.

## Decisão

1. **Duas rotas no mesmo item.** `Item.production` tem `route` (`deterministic`, que é o padrão, ou `ai_assisted`) e `steps`. A rota escolhe o grafo de transições do item. Um item sem `production` é determinístico, como antes.
2. **A rota determinística fica intocada.** `DETERMINISTIC_TRANSITIONS` tem as mesmas quatro transições da #33 (`idea -> drafted`, `drafted -> rendering`, `rendering -> rendered`, `rendering -> failed`). `VALID_TRANSITIONS` continua apontando para ele, para as importações existentes, e os testes da #33 seguem valendo sem mudança.
3. **Grafo ai_assisted.** `idea -> drafted -> quoted -> approved -> generating -> generated -> rendering -> rendered`, com `quoted -> drafted` (volta antes da confirmação), `generating -> failed` e `rendering -> failed`.
4. **Estimar, confirmar, depois gerar.** `drafted -> quoted` (a estimativa) exige um passo `ai_media` com `provider` não vazio em `production.steps`. `quoted -> approved` é a confirmação humana, e a única saída de `quoted` para a frente. Nenhum caminho leva de `quoted` a `generating` sem passar por `approved`.
5. **Revisão registrada à parte.** `Item.review` aceita `null`, `pending`, `approved` ou `changes_requested`, e é validado na construção. Nesta versão `transition()` não lê `review`.
6. **Evento com rota.** Cada mudança de estado grava `item.state_changed` com `from`, `to` e `route`, para que o log diga qual grafo valia na mudança.
7. **O kernel não chama provedor.** O kernel valida e grava estados. A estimativa e a confirmação de gasto acontecem no serviço de geração, e o kernel guarda o resultado como transições.

## Consequências

- Itens já existentes continuam válidos: sem `production`, a rota é `deterministic`.
- `transition()` passou a consultar a rota do item. Quem chama `transition()` com um item `ai_assisted` precisa ter o passo `ai_media` antes de `drafted -> quoted`.
- A regra "revisão aprovada antes de gerar" ainda não existe: `review` é só registrado. Se ela for exigida, entra em `transition()` com teste próprio.
- O passo `ai_media` guarda o `provider` como texto livre. O kernel só checa que ele não está vazio; não conhece a lista de provedores.
- O schema do item passou a ter 9 estados, `failed_from` pode ser `generating`, e existem os campos `production` e `review`. Como o schema é gerado, `make regen` precisa estar em dia antes de mudar o `Item`.

## Alternativas descartadas

- **Segundo tipo de item (um `ai_item` separado).** Duplicaria o kernel, o store e o schema, e cada plugin teria de escolher o tipo. Com a rota no mesmo item, o store e o estúdio são os mesmos e só o grafo muda.
- **LangGraph ou CrewAI agora.** Adicionariam dependência e um modelo de execução que o MVP não precisa: o grafo ai_assisted tem dez transições, validadas em `transition()`. As issues #25 (LangGraph) e #26 (CrewAI) continuam em backlog, na M2, e podem ser revisitadas se o fluxo pedir.
