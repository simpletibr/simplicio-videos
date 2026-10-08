# Decisões (ADRs)

Cada ADR registra uma decisão, o contexto, as alternativas e o status. Os arquivos ficam nesta pasta, numerados em ordem. A lista abaixo cobre os ADRs que existem hoje.

| ADR | Título |
|---|---|
| [ADR-0001 — simplicio-videos é um plugin do Simplicio Runtime (esteira determinística por setor)](ADR-0001-visao-plugin.md) | Visão de plugin |
| [ADR-0002 — CLI `simplicio-video`, contrato YAML, backend Colab e créditos](ADR-0002-cli-contrato-colab-creditos.md) | CLI e contrato |
| [ADR-0003: fluxo 100% script (voz Gemini por API, render remoto sem navegador, entrega no Drive, MCP)](ADR-0003-fluxo-100-script.md) | Fluxo 100% script |
| [ADR-0004: trilha UGC generativa fora do render determinístico (CLI só monta o prompt)](ADR-0004-ugc-generativo.md) | UGC generativo |
| [ADR-0005: gate local no lugar de CI (main verde, TDD e pouso serializado sem GitHub Actions)](ADR-0005-gate-sem-ci.md) | Gate sem CI |
| [ADR-0006: host de plugins (manifesto por plugin, descoberta por varredura e despacho por fallback)](ADR-0006-plugin-host.md) | Host de plugins |
| [ADR-0007: kernel da fábrica (contratos, transition(), JsonStore e testkit)](ADR-0007-kernel.md) | Kernel |
| [ADR-0008: duas rotas de produção no item (determinística intocada e ai_assisted com gasto aprovado)](ADR-0008-duas-rotas.md) | Duas rotas |
| [ADR-0017: instalação e atualização (um comando, git pull --ff-only, Docker só build local)](ADR-0017-instalacao-atualizacao.md) | Instalação e atualização |
| [ADR-0018: render final determinístico também na rota ai_assisted (a mídia gerada entra como asset verificado)](ADR-0018-render-final-deterministico.md) | Render final determinístico |
| [ADR-0019: agentes atrás de Protocols (LangGraph como orchestrator opcional, CrewAI fora do motor, A2A na borda externa)](ADR-0019-agentes.md) | Agentes atrás de Protocols |
