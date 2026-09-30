# AGENTS.md — simplicio-videos

Regras, mapa e fluxos para qualquer agente (Claude Code, Codex, Grok) trabalhando neste repositório. Cada vídeo também tem o seu `AGENTS.md` com detalhes da composição.

## O que é

**simplicio-videos** é o plugin de vídeo do **Simplicio Runtime (Simplicio MCP)** ([ADR-0001](docs/decisoes/ADR-0001-visao-plugin.md)). Pedido de vídeo → **esteira determinística** ([docs/esteira.md](docs/esteira.md)):

1. **intake** (questionário; com site/Instagram extrai sozinho e pergunta só o que falta) → 2. **brief/spec** (fonte única da verdade) → 3. **template do setor** → 4. **composição** com a biblioteca de motion (HyperFrames) → 5. **voz TTS** (provider à escolha, cache) → 6. **video-use** (footage, opcional) → 7. **render determinístico** + QA.

LLM (Opus 5.5) **só** cria template/padrão novo; nunca está no caminho do render. `plugin.json` é stub (sem binário); hoje os passos rodam pelos scripts do repo e pelo agente anfitrião.

## Mapa (todas as pastas)

| Pasta | O quê | Entrada principal |
|---|---|---|
| `intake/` | Etapa 1: questionário (modo auto/completo), regras de extração de site/IG (só público, fonte+data por fato), `intake.schema.json` (`simplicio.intake/v1`), `exemplos/` | [intake/README.md](intake/README.md) |
| `schemas/` | Etapa 2: `video-spec.schema.json` (`simplicio.video-spec/v1`, formato do `video.json`) | — |
| `templates/<setor>/` | Etapa 3: `template.json` (cenas, padrões, campos do intake, voz, música, cuidados) + README; `template.schema.json`. `pronto` ou `skeleton` | [templates/README.md](templates/README.md) |
| `motion/` | Etapa 4: biblioteca — `patterns/<id>/` (`pattern.json`, `block.html`, `preview.png`), `catalog.json` (gerado), `lib/retime.js`, `assets/` (fontes OFL, placeholders), `scripts/` (`preview.sh`, `catalog.mjs`), `pattern.schema.json` | [motion/README.md](motion/README.md) |
| `voices/` | Etapa 5: providers (`gemini.md` = tutorial, `elevenlabs.md`, `xai.md`, `local.md`), `narracao-tts.md` (pipeline, cache, tratamento) | [voices/README.md](voices/README.md) |
| `docs/` | `decisoes/` (ADRs), `esteira.md`, setup, pipeline determinístico, plugin, pesquisa | [docs/README.md](docs/README.md) |
| `clients/<cliente>/coleta/` | **Fatos** do cliente: `brief.md`, `fontes.md` (com data), `pendencias.md`, site salvo, `colors.json`, checklist | — |
| `clients/<cliente>/video-NN-videouse/` | Edição com video-use (etapa 6): `run.sh`, `edit/` (`edl.json`, transcrições, `takes_packed.md`, `project.md`, `verify/`), `overlay/` (HyperFrames → MOV alfa), `preview/` | README do vídeo |
| `clients/<cliente>/video-NN/` | Projeto HyperFrames autocontido (`package.json`; rode os comandos **dentro** dele): `spec.json` (variáveis, áudio/cues, voz, clipes), `video.json`, `index.html` (timeline única + `RETIME`), `scripts/` (`build.mjs`, `voice.py`, `master.sh`, `gemini-tts.mjs`), `assets/` (+ `audio/LICENSES.md`), `preview/` | README do vídeo |

## Fluxos

**Novo cliente / novo pedido (etapas 1–2)**
1. Rode o [questionário](intake/questionario.md): com site/IG, extraia conforme [extracao-automatica.md](intake/extracao-automatica.md) e pergunte só o que falta.
2. Congele em `clients/<slug>/coleta/intake.json` (valide com `intake/intake.schema.json`) + `brief.md`, `fontes.md` (URL + data), `pendencias.md`. Fato dito em conversa = fonte nova ("confirmado por X em DD/MM/AAAA").
3. Confirme o brief com o usuário antes de seguir.

**Novo vídeo (etapas 3–7)**
1. Escolha o template pelo nicho ([templates/README.md](templates/README.md)). Hoje: copie o projeto de referência do template (`cp -r clients/wjr-informatica-games/video-01 clients/<c>/video-01`), apague `out/`, `build/`, `preview/`, `assets/audio/vo/external/`.
2. Preencha `spec.json`/`video.json` a partir do intake (copy só da coleta); monte as cenas com blocos de `motion/` (`data-variable-values` vindo do spec).
3. Voz: `npm run voice` (cache). Loop: `npm run check` (0 erros) → `npm run snapshot` → `npm run render:draft` → `npm run render` → `npm run loudness` → `npm run preview`.

**Voz / narração** ([voices/](voices/README.md))
- `file` (padrão atual): WAVs externos em `assets/audio/vo/external/line-NN.wav` — ex.: Gemini no AI Studio ([voices/gemini.md](voices/gemini.md)); `scripts/gemini-tts.mjs` faz a rota API (não testada, sem chave).
- `chatterbox` / `kokoro` (locais), `elevenlabs` / `xai` (pagos, chave no ambiente).
- `voice.py` corta silêncio, trata, **nunca acelera**; frase maior que `max_s` = erro → reajuste tempos (cenas + cues) ou texto.

**Biblioteca de motion (autoria)**
- Padrão novo: `motion/patterns/<id>/pattern.json` + `block.html` → `bash motion/scripts/preview.sh <id>` (lint + preview) → `node motion/scripts/catalog.mjs` (regenera catálogo e tabela do README). Só vira `pronto` com lint limpo e preview.
- Inspiração externa: descreva e **reimplemente** com link da fonte; nunca copie código com licença restrita.

**Footage / cutdown com video-use (etapa 6)** ([docs/video-use-integracao.md](docs/video-use-integracao.md))
- Modelo: `clients/wjr-informatica-games/video-02-videouse/` (`run.sh`, `edit/edl.json`, `edit/project.md`). video-use fixado no commit, clonado fora do repo; saídas de trabalho em `edit/`.
- Transcrição sem chave: `scripts/fw_to_scribe.py` (faster-whisper → formato Scribe, `--script spec.json` para narração nossa). Depoimento real → Scribe (`ELEVENLABS_API_KEY`).
- Overlays HyperFrames sempre `--format mov` (WebM perde o alfa no `render.py`); loudness pelo nosso `master.sh` (`--no-loudnorm`).
- Estratégia de corte confirmada com o usuário antes do EDL; autoavaliação com `timeline_view` no corte antes de mostrar.

**Render**
- `npm run render` = `build.mjs` → HyperFrames (`--strict-variables`) → `master.sh` (−14 LUFS, TP ≤ −1,5 dBTP). HyperFrames sempre fixado: `npx --yes hyperframes@0.8.97`. Node ≥ 22.

**Determinismo**
- Nada de `Math.random` (use `rng()` com semente), `Date.now`, `fetch`, `repeat: -1` em composição ou bloco.
- Tempos de cena, cues (`spec.json → audio.cues`) e linhas de voz andam juntos: mudou um, mude os três e o `roteiro.md`.
- WAVs da narração + `manifest.json` são versionados (cache); o render não precisa de TTS nem rede.

**Validação antes de commitar**
- `node motion/scripts/catalog.mjs --check` (catálogo em dia) · schemas com AJV (`intake`, `template`, `pattern`, `video-spec`) · links relativos dos `.md` sem quebra · `npm run check` no vídeo alterado.

## Convenções e travas

- **Só fatos reais**: toda copy vem de `coleta/`. Nada de preço, prazo, garantia, avaliações, números ou promessas ("sem drift") sem confirmação registrada.
- **Organização**: cada coisa na pasta da sua etapa (tabela acima); nada solto na raiz; trabalho de cliente só em `clients/`; artefatos (`out/`, `build/`, `node_modules/`) gitignored.
- **Licenças**: só trilha/SFX/voz/fonte com uso comercial claro; registre em `assets/audio/LICENSES.md` (e fontes ao lado dos arquivos). Assets do cliente ficam em `assets/client/` (gitignored) até aprovação.
- Não clonar voz de pessoa real sem autorização dela.
- Docs em **pt-BR**; comentários de código em inglês.
- Segredos (API keys) só no ambiente/`.env` (gitignored), nunca no repo.
- Um commit por pedido, mensagem em pt-BR; horários em BRT.
