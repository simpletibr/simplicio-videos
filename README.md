# simplicio-videos

Kit para produzir **vídeos promocionais de clientes** da Simplicio com IA (Claude Opus 5.5 / Codex escrevendo HTML + GSAP) e **render determinístico** a partir de um spec JSON (HyperFrames → MP4). No futuro vira um plugin do `simplicio-runtime` ([proposta](docs/plugin-simplicio-runtime.md), stub em [`plugin.json`](plugin.json)).

> Agentes (Claude Code, Codex, Grok): comecem por [`AGENTS.md`](AGENTS.md).

## Mapa do repositório

```
simplicio-videos/
├── AGENTS.md / CLAUDE.md          # regras + fluxos para agentes (CLAUDE.md aponta para AGENTS.md)
├── README.md                      # este índice
├── plugin.json                    # simplicio.plugin/v1 — STUB (futuro plugin do simplicio-runtime)
├── schemas/
│   └── video-spec.schema.json     # simplicio.video-spec/v1 (formato do video.json de cada vídeo)
├── docs/                          # guias e pesquisa (índice em docs/README.md)
│   ├── setup.md                   #   instalar Node/FFmpeg/agentes/skills
│   ├── narracao-tts.md            #   pipeline de voz (providers file/chatterbox/kokoro/elevenlabs/xai)
│   ├── tutorial-voz-gemini.md     #   passo a passo: voz do Gemini no AI Studio → vídeo
│   ├── pipeline-deterministico-gemini.md # dá para ser 100% determinístico? voz em cache, biblioteca de motion, plano
│   ├── checklist-cliente.md       #   o que pedir a qualquer cliente (template)
│   ├── como-gerar-videos-opus-5-5.md, tokens-e-deterministico.md, plugin-simplicio-runtime.md, recursos.md
└── clients/
    └── <cliente>/                 # um diretório por cliente (slug)
        ├── coleta/                #   FATOS: brief, fontes datadas, site salvo, cores, pendências, checklist
        └── video-NN/              #   um projeto HyperFrames por vídeo (autocontido, tem package.json)
            ├── index.html         #     composição (HTML + GSAP, timeline única e pausada)
            ├── spec.json          #     tudo que muda: variáveis, áudio (cues), voz (linhas), clipes
            ├── video.json         #     manifest simplicio.video-spec/v1
            ├── roteiro.md, PROMPT.md, README.md
            ├── scripts/           #     build.mjs (áudio+variáveis), voice.py, master.sh, setup-tts.sh, gemini-tts.mjs
            ├── assets/            #     fonts, placeholders, audio (vo + LICENSES.md), imagine (clipes)
            └── preview/           #     preview 720p com áudio + contact sheet (versionados)
```

## Clientes e vídeos

| Cliente | Vídeo | O que é |
|---|---|---|
| WJR Informática e Games (Guarulhos) | [coleta](clients/wjr-informatica-games/coleta/) | brief, site salvo, fontes, pendências |
| | [video-01](clients/wjr-informatica-games/video-01/) | Reels 9:16, 20 s, narração pt-BR (Gemini TTS, voz Puck) + trilha/SFX próprios + cena de serviços · [preview](clients/wjr-informatica-games/video-01/preview/) |

## Quick start

```bash
gh repo clone simpletibr/simplicio-videos
cd simplicio-videos/clients/wjr-informatica-games/video-01
npm run assets:site   # imagens públicas do site p/ rascunho (gitignored)
npm run check         # build (variáveis + áudio + voz) + lint + layout + contraste
npm run render        # out/video-01.mp4 (1080×1920, 30 fps, 20 s, −14 LUFS)
npm run preview       # preview/video-01-preview-720p.mp4
```
Requer Node ≥ 22 e FFmpeg ([setup](docs/setup.md)). Trocar a voz: [tutorial Gemini](docs/tutorial-voz-gemini.md) · [todas as opções](docs/narracao-tts.md).

## Documentação

Visão de arquitetura (determinismo + voz Gemini + biblioteca de padrões): [`docs/pipeline-deterministico-gemini.md`](docs/pipeline-deterministico-gemini.md).

Índice completo em [`docs/README.md`](docs/README.md). Curadoria de ferramentas de vídeo/motion (com estrelas e licenças): [`docs/recursos.md`](docs/recursos.md).
