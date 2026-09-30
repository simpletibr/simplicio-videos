# AGENTS.md — simplicio-videos

Regras e fluxos para qualquer agente (Claude Code, Codex, Grok) trabalhando neste repositório. Cada vídeo também tem o seu `AGENTS.md` com detalhes da composição.

## O que é

**simplicio-videos** é o kit da Simplicio para gerar vídeos promocionais de clientes: a IA escreve a composição (HTML + GSAP no [HyperFrames](https://github.com/heygen-com/hyperframes)) e o render é **determinístico** a partir de `spec.json` (mesmo spec + mesmos assets = mesmo vídeo). Vai virar um plugin do `simplicio-runtime` (`plugin.json` é stub; proposta em `docs/plugin-simplicio-runtime.md`).

## Mapa

| Onde | O quê |
|---|---|
| `clients/<cliente>/coleta/` | **Fonte da verdade dos fatos** do cliente: `brief.md`, `fontes.md` (cada fonte com data), `pendencias.md` (o que falta confirmar e o que cada vídeo usa), site salvo, `colors.json`, checklist |
| `clients/<cliente>/video-NN/` | Projeto HyperFrames autocontido (tem `package.json`; rode os comandos **dentro** dele) |
| `…/video-NN/spec.json` | Tudo que muda: `variables` (copy/imagens/cores), `audio` (BPM, seções, cues de SFX, master), `voice` (linhas com `t`/`max_s`, provider, tratamento), `clips` (slots de vídeo) |
| `…/video-NN/index.html` | Composição: uma `gsap.timeline({paused:true})` em `window.__timelines["main"]`; bloco `RETIME` mapeia a coreografia para os cortes reais |
| `…/video-NN/scripts/` | `build.mjs` (variáveis + trilha/SFX sintetizados + mix da voz), `voice.py` (narração), `master.sh` (loudness final), `setup-tts.sh`, `gemini-tts.mjs` |
| `…/video-NN/assets/audio/LICENSES.md` | Origem e licença de todo áudio (obrigatório manter atualizado) |
| `docs/` | Guias (setup, voz, tutorial Gemini, checklist) e pesquisa — índice em `docs/README.md` |
| `schemas/video-spec.schema.json` | Formato do `video.json` (validar com AJV ao mudar) |

Arquitetura/visão (determinismo, voz em cache, biblioteca de padrões de motion, plugin): [`docs/pipeline-deterministico-gemini.md`](docs/pipeline-deterministico-gemini.md).

## Fluxos

**Novo cliente**
1. `clients/<slug>/coleta/`: copie `docs/checklist-cliente.md`, salve site/Instagram, escreva `brief.md` e `fontes.md` (URL + data de acesso). Tudo que não for confirmado vai para `pendencias.md`.
2. Fato dito pelo usuário/cliente em conversa: registre como fonte nova em `fontes.md` ("confirmado por X em DD/MM/AAAA").

**Novo vídeo**
1. Copie o vídeo mais próximo (`cp -r clients/<c>/video-01 clients/<c>/video-02`), apague `out/`, `build/`, `preview/`.
2. Edite `spec.json` (copy só da `coleta/`), `video.json`, `roteiro.md`, depois `index.html` com o `PROMPT.md`.
3. Loop: `npm run check` (0 erros) → `npm run snapshot` → `npm run render:draft` → `npm run render` → `npm run preview`.

**Voz / narração** (`spec.json → voice`, detalhes em `docs/narracao-tts.md`)
- `file` (padrão atual): WAVs externos em `assets/audio/vo/external/line-NN.wav` — ex.: Gemini TTS no AI Studio (`docs/tutorial-voz-gemini.md`).
- `chatterbox` (local, MIT), `kokoro` (local, Apache-2.0), `elevenlabs` / `xai` (pagos, chave no ambiente).
- `npm run voice` corta silêncio, trata (EQ/compressor/sala), **nunca acelera**; frase maior que `max_s` = erro → reajuste os tempos (cenas + cues) ou o texto.

**Render**
- `npm run render` = `build.mjs` → HyperFrames (`--strict-variables`) → `master.sh` (−14 LUFS, TP ≤ −1,5 dBTP). Conferir com `npm run loudness`.
- HyperFrames sempre fixado: `npx --yes hyperframes@0.8.97`. Node ≥ 22.

**Spec determinístico**
- Nada de `Math.random` (use o `rng()` com semente), `Date.now`, `fetch`, `repeat: -1` na composição.
- Tempos de cena, cues de áudio (`spec.json → audio.cues`) e linhas de voz andam juntos: mudou um, mude os três e o `roteiro.md`.
- WAVs da narração e o `manifest.json` são versionados (cache); o render não precisa de TTS instalado.

## Convenções e travas

- **Só fatos reais**: toda copy vem de `coleta/`. Nada de preço, prazo, garantia, avaliações, números ou promessas ("sem drift") sem confirmação registrada.
- **Licenças**: só trilha/SFX/voz/fonte com uso comercial claro; registre em `assets/audio/LICENSES.md` (e fontes ao lado dos arquivos). Assets do cliente ficam em `assets/client/` (gitignored) até aprovação.
- Não clonar voz de pessoa real sem autorização dela.
- Docs em **pt-BR**; comentários de código em inglês.
- Segredos (API keys) só no ambiente/`.env` (gitignored), nunca no repo.
- Um commit por pedido, mensagem em pt-BR; horários em BRT.
