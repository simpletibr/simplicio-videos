# simplicio-videos

**Plugin de vídeo do Simplicio Runtime (Simplicio MCP).** Quando um usuário do Simplicio pede um vídeo, o plugin roda uma **esteira determinística**: questionário de intake (com extração automática de site/Instagram) → brief/spec → template do setor → composição com a biblioteca de padrões de motion (HyperFrames) → voz TTS (Gemini, ElevenLabs, xAI ou local, com cache) → edição de footage com video-use (opcional) → render determinístico. LLM (Opus 5.5) só cria templates e padrões novos.

Decisão: [ADR-0001](docs/decisoes/ADR-0001-visao-plugin.md) · Fluxo: [docs/esteira.md](docs/esteira.md) · Manifest (stub): [`plugin.json`](plugin.json)

> Agentes (Claude Code, Codex, Grok): comecem por [`AGENTS.md`](AGENTS.md).

## Mapa do repositório

```
simplicio-videos/
├── AGENTS.md / CLAUDE.md   # regras + mapa + fluxos para agentes (CLAUDE.md → AGENTS.md)
├── plugin.json             # simplicio.plugin/v1 — STUB (ops da esteira; sem binário ainda)
├── intake/                 # 1 questionário, extração automática site/IG, intake.schema.json, exemplos/
├── templates/              # 3 um template por setor (template.json + README); schema
├── motion/                 # 4 biblioteca de padrões: patterns/<id>/{pattern.json, block.html, preview.png}, catalog.json, lib/, scripts/
├── voices/                 # 5 providers de voz (gemini, elevenlabs, xai, local) + pipeline TTS
├── tools/                  # 6 opcional: video-use (setup fixado, transcrição local, uso) — edição quando o usuário pede
├── schemas/                # 2 video-spec.schema.json (simplicio.video-spec/v1)
├── docs/                   # ADRs (decisoes/), esteira, setup, pesquisa — índice em docs/README.md
└── clients/<cliente>/      # trabalho de cliente
    ├── coleta/             #   fatos com fonte e data (brief, fontes, site salvo, cores, pendências)
    └── video-NN/           #   projeto HyperFrames autocontido (spec.json, index.html, scripts/, assets/, preview/)
```

## Catálogos

| O quê | Onde | Hoje |
|---|---|---|
| Padrões de motion | [motion/README.md](motion/README.md) | 46 (24 blocos prontos com preview, 1 lib, 2 inline, 19 propostos) |
| Templates por setor | [templates/README.md](templates/README.md) | 2 prontos (assistência técnica/games, odontologia) + 6 skeleton |
| Vozes | [voices/README.md](voices/README.md) | Gemini (padrão, via `file`), Chatterbox/Kokoro locais, ElevenLabs/xAI (sem chave) |
| Intake | [intake/README.md](intake/README.md) | questionário, extração automática, schema, exemplo WJR |
| Ferramentas opcionais | [tools/README.md](tools/README.md) | video-use (edição: cortar p/ X s, reordenar, aparar footage, legendas, revisão) |

## Clientes e vídeos

| Cliente | Vídeo | O que é |
|---|---|---|
| WJR Informática e Games (Guarulhos) | [coleta](clients/wjr-informatica-games/coleta/) | brief, site salvo, fontes, pendências |
| | [video-01](clients/wjr-informatica-games/video-01/) | Reels 9:16, 20 s, narração pt-BR (Gemini TTS, voz Puck) + trilha/SFX próprios · [preview](clients/wjr-informatica-games/video-01/preview/) · referência do template `assistencia-tecnica-games` |
| | [video-02-videouse](clients/wjr-informatica-games/video-02-videouse/) | Cutdown 11,5 s do video-01 montado com [video-use](docs/video-use-integracao.md) (EDL + overlay HyperFrames) · [preview](clients/wjr-informatica-games/video-02-videouse/preview/) |
| | [README + entregas no Drive](clients/wjr-informatica-games/README.md) | links dos MP4 entregues |
| Lothus Odontologia (Guarulhos) | [coleta](clients/lothus-odontologia/coleta/) · [README + Drive](clients/lothus-odontologia/README.md) | Instagram público + CNES + espelho Google Places; conflitos de endereço/telefone em pendências |
| | [video-01-dia-das-criancas](clients/lothus-odontologia/video-01-dia-das-criancas/) | Post 9:16, 15 s, Dia das Crianças, voz provisória local (final Gemini Sulafat) · [preview](clients/lothus-odontologia/video-01-dia-das-criancas/preview/) · referência do template `saude-odontologia` |

## Quick start

```bash
gh repo clone simpletibr/simplicio-videos
cd simplicio-videos/clients/wjr-informatica-games/video-01
npm run assets:site   # imagens públicas do site p/ rascunho (gitignored)
npm run check         # build (variáveis + áudio + voz) + lint + layout + contraste
npm run render        # out/video-01.mp4 (1080×1920, 30 fps, 20 s, −14 LUFS)
npm run preview       # preview/video-01-preview-720p.mp4
```
Requer Node ≥ 22 e FFmpeg ([setup](docs/setup.md)). Voz: [tutorial Gemini](voices/gemini.md) · [todas as opções](voices/README.md). Edição opcional: [tools/video-use](tools/video-use/README.md) (exemplo: `bash clients/wjr-informatica-games/video-02-videouse/run.sh`). Biblioteca: `bash motion/scripts/preview.sh && node motion/scripts/catalog.mjs`.

## Documentação

Índice em [`docs/README.md`](docs/README.md). Curadoria de ferramentas de vídeo/motion (com estrelas e licenças): [`docs/recursos.md`](docs/recursos.md).

### Referências principais

- [HyperFrames](https://github.com/heygen-com/hyperframes) — render HTML/GSAP → MP4 (base do repo).
- [video-use](https://github.com/browser-use/video-use) — edição agêntica de footage (etapa 6; [avaliação](docs/video-use-integracao.md)).
- [video-shotcraft](https://github.com/Vincentwei1021/video-shotcraft) e [awesome-opus5-5-videos](https://github.com/yihui-dev/awesome-opus5-5-videos) — receitas e prompts destilados em `motion/`.
- [motion-video-kit](https://github.com/echris6/motion-video-kit) (MIT) — skill `business-motion-film` para comerciais de negócios reais: loop de crítica independente ("Gauntlet"), gramática de motion (6 regras + catálogo de mecanismos a partir de 28 launch films), barra de qualidade medida (tempo congelado, loudness, contraste, cor da marca) e scripts ffmpeg. Fonte de 5 padrões `proposto` em `motion/`.
