# ADR-0019: agentes atrás de Protocols (LangGraph como orchestrator opcional, CrewAI fora do motor, A2A na borda externa)

- **Status:** aceito. Resultado experimental do spike da issue #83, dentro do épico #81 (milestone M2).
- **Data:** 08/10/2026 (BRT)
- **Relaciona:** [docs/research/agentes/](../research/agentes/README.md) (roteiro e medições) · [ADR-0001](ADR-0001-visao-plugin.md) (visão de plugin) · [ADR-0006](ADR-0006-plugin-host.md) (host de plugins) · [ADR-0007](ADR-0007-kernel.md) (kernel da fábrica) · [design-review](../../docs/factory/design-review.md) · épico #81

## Contexto

O projeto previa a integração futura com ecossistemas de agentes autônomos (LangGraph, CrewAI e A2A), conforme rascunhado no roadmap do milestone M2 (entradas 25, 26 e 27 do `ownership.yaml`). O [design review](../../docs/factory/design-review.md) apontou os riscos de adotar esses frameworks jovens prematuramente: dependências volumosas, tempos excessivos de instalação, bloqueios de versão de Python e imposição de tráfego de rede HTTP para comunicação interna.

Para proteger o motor (`simplicio-video` e `simplicio_factory`), foram definidos três critérios de morte estritos. O spike #83 realizou a medição empírica e a análise arquitetural de cada um desses frameworks em ambiente limpo (Python 3.12.14, Linux x86_64, gerenciador `uv`).

## Decisão

1. **Nenhum framework de agentes entra nas dependências obrigatórias do motor.** O `pyproject.toml` base continua sem dependências de LangGraph, CrewAI ou A2A. O motor segue rápido, hermético e 100% testável offline.
2. **LangGraph (PASS):** Aprovado como plugin opcional futuro de orquestração (`orchestrator`).
   - Medição: instalação em 2.81 s, tamanho 52 MB.
   - Critério de morte: não exige alteração no contrato do item (`Item`) nem no kernel. O estado do grafo pode transportar apenas referências do item e executar os estágios existentes via Protocol `LoopRunner`.
   - O executor sequencial simples do kernel continua sendo o padrão.
3. **CrewAI (PASS nos limites técnicos, isolado como plugin opcional):**
   - Medição: instalação em 10.23 s, tamanho 753 MB (134 pacotes transitivos), compatível com Python 3.12.
   - Critério de morte: ficou abaixo do teto de 2 GB e de 5 minutos. No entanto, sua pegada em disco é grande demais para a distribuição base.
   - Fica estritamente encapsulado atrás do Protocol `AgentRunner`. O motor padrão implementará um executor enxuto nativo de ferramentas (`SimpleToolLoop`), com zero tokens de LLM e zero dependências pesadas.
4. **A2A (MORTA para transporte in-process; MANTIDA na borda externa):**
   - Medição: `a2a-sdk` 1.2.2 impõe cliente/servidor JSON-RPC sobre HTTP/SSE (`httpx`, `requests`).
   - Critério de morte: o transporte in-process exige HTTP. Portanto, o A2A **não** será usado para troca de mensagens entre estágios internos da fábrica.
   - Fica reservado exclusivamente para a fronteira externa (exposição de interfaces MCP / A2A para que agentes de outros repositórios interajam com o motor).

## Consequências e Próximos Passos (Substituição do Backlog)

As entradas 25, 26 e 27 do `ownership.yaml` deixam de ser caixas-pretas e são especificadas como issues de implementação modulares:

### Issue Substituta para #25: `[M2] orchestrator: plugin opcional LoopRunner com LangGraph`
- **Escopo:** Criar plugin `orchestrator-langgraph` implementando o Protocol `LoopRunner`, testado com fixtures herméticas.
- **Paths possuídos:** `src/simplicio_factory/plugins/orchestrator_langgraph/**`, `tests/factory/plugins/orchestrator_langgraph/**`.
- **Critérios:** Grafo executa nós respeitando o `Item.state`, sem alterar `contracts/models.py`.

### Issue Substituta para #26: `[M2] agent-runtime: executor nativo SimpleToolLoop e plugin opcional CrewAI`
- **Escopo:** Criar o Protocol `AgentRunner`, um executor padrão leve `SimpleToolLoop` no kernel (zero dependências) e o plugin opcional `agents-crewai`.
- **Paths possuídos:** `src/simplicio_factory/plugins/agents_crewai/**`, `tests/factory/plugins/agents_crewai/**`, `src/simplicio_factory/runner/simple_loop.py`.
- **Critérios:** `SimpleToolLoop` roda sem rede; plugin `crewai` só é importado quando expressamente ativado.

### Issue Substituta para #27: `[M2] boundary: adaptador de interoperabilidade A2A na borda externa`
- **Escopo:** Endpoint/servidor de borda que traduz mensagens do A2A SDK para chamadas do motor via MCP/CLI, sem tocar no fluxo in-process dos estágios.
- **Paths possuídos:** `src/simplicio_video/boundary/a2a/**`, `tests/test_boundary_a2a.py`, `docs/host/a2a-boundary.md`.
- **Critérios:** Provar isolamento total em relação ao pipeline local de renderização.

## Alternativas Descartadas

- **Adicionar CrewAI diretamente ao pyproject.toml base:** Descartado. Aumentaria o tamanho do ambiente de desenvolvimento em centenas de megabytes desnecessariamente.
- **Usar A2A como barramento de eventos interno:** Descartado. Viola o hermetismo e adiciona sobrecarga de rede desnecessária para um pipeline local determinístico.
- **Depender exclusivamente do LangGraph para rodar o loop:** Descartado. O loop sequencial simples do kernel resolve a maior parte dos casos sem adicionar complexidade gráfica.
