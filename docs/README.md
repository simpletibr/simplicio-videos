# docs — índice

| Doc | Para quê |
|---|---|
| [tutorials/README.md](tutorials/README.md) | **Índice dos tutoriais** (do zero ao resultado): comece por [primeiro vídeo](tutorials/primeiro-video.md) |
| [how-to/README.md](how-to/README.md) | **Índice dos how-to** (tarefas específicas): instalar, atualizar e checar; receita de vídeo para cliente |
| [decisoes/README.md](decisoes/README.md) | **Índice dos ADRs** (decisões de arquitetura e de produto), em ordem |
| [host/README.md](host/README.md) | **Índice do host**: gate local, pacote de operação e licenças |
| [plugins/README.md](plugins/README.md) | **Índice de plugins**: ainda vazio; a #32 define o registro |
| [decisoes/ADR-0001-visao-plugin.md](decisoes/ADR-0001-visao-plugin.md) | **Decisão de produto** (Wesley, 30/09/2026): plugin do Simplicio Runtime, esteira determinística por setor |
| [receita-video-cliente.md](receita-video-cliente.md) | **Receita atual:** o agente escreve o contrato, o CLI `simplicio-video` executa (coleta → contrato → validate → voice → render → Drive) |
| [decisoes/ADR-0002-cli-contrato-colab-creditos.md](decisoes/ADR-0002-cli-contrato-colab-creditos.md) | CLI + contrato YAML, backend Colab (GPU), design de créditos para clientes pagantes |
| [custos.md](custos.md) | **Custo por vídeo** (voz Gemini, render local/Colab/Kaggle/Modal, Drive) em US$ e R$, com o que é medido, oficial ou estimativa, e margem (WJR a R$ 60) |
| [venda-ativa.md](venda-ativa.md) | **Venda ativa em massa** (saiu do CLI do motor na #77; fica no repositório de operação): lista → coleta pública → contrato por setor → prévia com marca d'água Wesley Simplicio), limites (dados públicos, Instagram sem login, LGPD), custo por prévia (local = R$ 0), piloto Dia das Crianças e script de abordagem |
| [decisoes/ADR-0003-fluxo-100-script.md](decisoes/ADR-0003-fluxo-100-script.md) | **Fluxo 100% script:** voz Gemini por API, render remoto (Kaggle, Colab CLI) com custos, vCPU e o dado real do Colab, bug do NVENC, determinismo entre backends (ffmpeg travado, container), Drive via rclone, MCP, credenciais |
| [decisoes/ADR-0004-ugc-generativo.md](decisoes/ADR-0004-ugc-generativo.md) | **UGC generativo:** por que a trilha fica fora do render determinístico, o que o CLI faz (`ugc list`, `ugc prompt`), guardrails (sem depoimento fabricado, rótulo de IA, nada de arquivo gerado no git) e alternativas descartadas (HyperFrames, API do Higgsfield/Krea) |
| [../ugc/README.md](../ugc/README.md) | **Trilha UGC (gerativa):** pipeline de 7 passos (elenco, imagens, roteiros, Seedance), regras de qualidade, comandos `ugc` (saíram do CLI do motor na #77), guardrails e atribuição (@sleepclip, pack do Notion); 10 personagens + 5 prompts |
| [esteira.md](esteira.md) | A esteira ponta a ponta (intake → spec → template → motion → voz → footage → render), o que é determinístico e o estado atual |
| [video-use-integracao.md](video-use-integracao.md) | Etapa 6: video-use (edição agêntica de footage) — o que faz, o que precisa de chave, integração com HyperFrames/motion/voz, o que acrescentou |
| [setup.md](setup.md) | Instalar Node, FFmpeg, Claude Code/Codex, skills do HyperFrames; primeiro render |
| [pipeline-deterministico-gemini.md](pipeline-deterministico-gemini.md) | Por que dá para ser determinístico com voz Gemini: cache por hash, biblioteca de motion, render sem LLM, HyperFrames vs Python |
| [checklist-cliente.md](checklist-cliente.md) | Checklist do que pedir ao cliente (logo, fotos, vídeos, confirmações) — complementa o [questionário](../intake/questionario.md) |
| [como-gerar-videos-opus-5-5.md](como-gerar-videos-opus-5-5.md) | Pesquisa: como se faz vídeo com Opus 5.5 (stacks, prompts, skills, custos) |
| [tokens-e-deterministico.md](tokens-e-deterministico.md) | Custos, economia de tokens e o pipeline determinístico |
| [plugin-simplicio-runtime.md](plugin-simplicio-runtime.md) | Arquitetura proposta do plugin (`simplicio.plugin/v1`) |
| [recursos.md](recursos.md) | Curadoria de ferramentas/repos de vídeo e motion |
| [licenses.md](licenses.md) | Licenças das dependências instaladas (scan do `.venv`, allowlist e exceções); gerado por `make licenses-write` |
| [host/licenses.md](host/licenses.md) | Como o gate confere licenças, como pedir uma exceção e como regerar `docs/licenses.md` |
| [glossary.md](glossary.md) | Glossário: contrato, render, marca, motion, template, voz, manifesto, ferramenta, ADR, stage, station, character, plugin e Runtime plugin |
| [reference/cli.md](reference/cli.md) | Referência da CLI: o `--help` real de cada comando (gerado por `make regen`) |
| [reference/schemas.md](reference/schemas.md) | Schemas JSON do pacote (gerado) |
| [reference/config.md](reference/config.md) | Variáveis de ambiente que o código lê (gerado) |
| [reference/mcp-tools.md](reference/mcp-tools.md) | Tools do servidor MCP (gerado) |
| [reference/plugins.md](reference/plugins.md) | Plugins instalados (gerado; vazio até o host de plugins) |
| [reference/events.md](reference/events.md) | Eventos catalogados (gerado; vazio por enquanto) |

Voz/narração saiu daqui e foi para [`voices/`](../voices/README.md) (tutorial Gemini, pipeline TTS, ElevenLabs, xAI, locais).
