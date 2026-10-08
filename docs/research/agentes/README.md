# Spike de Agentes: LangGraph, CrewAI e A2A

Pesquisa e medições experimentais da issue #83 (épico #81, milestone M2) para decidir com evidência empírica se, e como, LangGraph, CrewAI e A2A entram no projeto, sem inserir nenhuma dependência no motor central (`simplicio-video` / `simplicio_factory`).

## Documentos

- [Roteiro de medição](roteiro.md): comandos, ambiente de teste, metodologia e critérios de morte verificados.
- [LangGraph](langgraph.md): medição de instalação, compatibilidade e viabilidade como plugin `orchestrator` (`LoopRunner`).
- [CrewAI](crewai.md): medição de instalação, pegada em disco, tempo e viabilidade como plugin `agent-runtime` (`AgentRunner`).
- [A2A](a2a.md): análise da especificação A2A SDK (`a2a-sdk` 1.2.2), requisitos de transporte e fronteira externa.

## Decisão registrada

A decisão arquitetural consolidada está no [ADR-0019](../../decisoes/ADR-0019-agentes.md).
