# docs — índice

| Doc | Para quê |
|---|---|
| [decisoes/ADR-0001-visao-plugin.md](decisoes/ADR-0001-visao-plugin.md) | **Decisão de produto** (Wesley, 30/09/2026): plugin do Simplicio Runtime, esteira determinística por setor |
| [esteira.md](esteira.md) | A esteira ponta a ponta (intake → spec → template → motion → voz → footage → render), o que é determinístico e o estado atual |
| [video-use-integracao.md](video-use-integracao.md) | Etapa 6: video-use (edição agêntica de footage) — o que faz, o que precisa de chave, integração com HyperFrames/motion/voz, o que acrescentou |
| [setup.md](setup.md) | Instalar Node, FFmpeg, Claude Code/Codex, skills do HyperFrames; primeiro render |
| [pipeline-deterministico-gemini.md](pipeline-deterministico-gemini.md) | Por que dá para ser determinístico com voz Gemini: cache por hash, biblioteca de motion, render sem LLM, HyperFrames vs Python |
| [checklist-cliente.md](checklist-cliente.md) | Checklist do que pedir ao cliente (logo, fotos, vídeos, confirmações) — complementa o [questionário](../intake/questionario.md) |
| [como-gerar-videos-opus-5-5.md](como-gerar-videos-opus-5-5.md) | Pesquisa: como se faz vídeo com Opus 5.5 (stacks, prompts, skills, custos) |
| [tokens-e-deterministico.md](tokens-e-deterministico.md) | Custos, economia de tokens e o pipeline determinístico |
| [plugin-simplicio-runtime.md](plugin-simplicio-runtime.md) | Arquitetura proposta do plugin (`simplicio.plugin/v1`) |
| [recursos.md](recursos.md) | Curadoria de ferramentas/repos de vídeo e motion |

Voz/narração saiu daqui e foi para [`voices/`](../voices/README.md) (tutorial Gemini, pipeline TTS, ElevenLabs, xAI, locais).
