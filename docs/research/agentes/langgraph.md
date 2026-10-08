# Pesquisa e Medição: LangGraph

Relatório de medição da biblioteca LangGraph para a issue #83 (épico #81, milestone M2).

## Dados da Medição

- **Pacote:** `langgraph`
- **Versão testada:** `1.2.14`
- **Data da medição:** 2026-10-08
- **Ambiente:** Linux x86_64, CPython 3.12.14, `uv` 0.5+
- **Tempo de resolução e instalação:** 2.81 s
- **Tamanho total em disco do ambiente:** 52 MB
- **Total de pacotes transitivos:** 12 (`langgraph`, `langgraph-checkpoint`, `langgraph-sdk`, `langchain-core`, etc.)

## Critério de Morte Verificado

> **Critério de morte:** *se exigir mudar o contrato do item ou o kernel → fica de fora.*

### Experimento e Teste Arquitetural

Testamos a criação de um grafo de estados (`StateGraph`) para atuar como executor do loop de fábrica (`LoopRunner`):

```python
from typing import TypedDict
from langgraph.graph import StateGraph, START, END

class LoopState(TypedDict):
    item_id: str
    stage: str
    status: str

def draft_node(state: LoopState):
    # O nó consome o item e aciona o estágio correspondente
    return {"stage": "drafted", "status": "ok"}

builder = StateGraph(LoopState)
builder.add_node("draft", draft_node)
builder.add_edge(START, "draft")
builder.add_edge("draft", END)
graph = builder.compile()

res = graph.invoke({"item_id": "video-123", "stage": "init", "status": "pending"})
```

### Análise

1. **Impacto no Contrato do Item:** Zero. O estado do grafo pode transportar apenas referências (`item_id`) ou carregar diretamente a instância de `simplicio_factory.contracts.models.Item` sem alterar um único campo do schema do item (`schemas/factory/item.schema.json` e `contract.schema.json`).
2. **Impacto no Kernel:** Zero. O motor central continua operando com `transition()` e `Store` agnósticos. O `LoopRunner` LangGraph pode ser instanciado como uma classe externa que implementa o Protocol `LoopRunner`:
   ```python
   class LoopRunner(Protocol):
       def run_loop(self, item_id: str, store: Store) -> None: ...
   ```
3. **Desempenho e Pegada:** A biblioteca é leve (52 MB), compila grafos rapidamente em memória e instala em menos de 3 segundos com `uv`.

## Veredito: PASS

- **Resultado:** **PASS** (aprovado para implementação como plugin opcional futuro de orquestração).
- **Enquadramento:** O executor sequencial simples do kernel permanece o padrão sem dependências. O plugin `orchestrator-langgraph` será oferecido como extra opcional para orquestrações complexas com ramificações e ciclos de aprovação.
