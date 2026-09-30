# video-01 — WJR Infogames · Instagram Reels "showreel" (9:16)

1080×1920 · 30 fps · **15 s** · 120 BPM · **narração pt-BR (Kokoro TTS local)** + trilha + efeitos sonoros originais (gerados por código) · HyperFrames 0.8.97 (HTML + GSAP).

| Arquivo | Para quê |
|---|---|
| `index.html` | composição; todo texto/imagem/cor é variável (`data-composition-variables` + `data-var-*`) |
| `spec.json` | **tudo que muda**: `variables` (copy, imagens, cores), `audio` (BPM, seções, 32 cues de SFX com tempo/ganho/ducking, master), `voice` (6 frases de narração com tempo, provedor Kokoro/ElevenLabs, ducking) e `clips` (slots de vídeo opcionais) |
| `scripts/build.mjs` | passo determinístico: gera `build/variables.json`, sintetiza trilha + SFX, mixa (sidechain, ducking, fades), normaliza (−14 LUFS) e prepara os clipes |
| `scripts/voice.py` / `scripts/setup-tts.sh` | narração: gera/cacheia as frases em `assets/audio/vo/` (Kokoro local ou ElevenLabs) — ver `docs/narracao-tts.md` |
| `scripts/master.sh` | master final no MP4 renderizado (loudnorm 2 passagens + limiter, vídeo copiado) |
| `video.json` | spec do futuro plugin (`simplicio.video-spec/v1`, proposta) |
| `storyboard.simplicio.json` | versão para o plugin `motion` do simplicio-runtime (fallback sem áudio; não validada no binário) |
| `roteiro.md` | roteiro por cena com tempos de motion **e** de áudio |
| `PROMPT.md` | prompts para Opus 5.5 (inclui o "showreel" adaptado) |
| `AGENTS.md` / `CLAUDE.md` | regras para o agente |
| `assets/audio/LICENSES.md` | origem/licença do áudio (síntese própria, sem terceiros) |
| `assets/imagine/` | slots para clipes verticais (Grok Imagine etc.) — ver o README da pasta |
| `assets/placeholders/` | slots marcados (logo, foto 1, foto 2) |
| `assets/client/` | arquivos do cliente (gitignored; `npm run assets:site` copia de `../coleta/site/imagens/`) |
| `assets/fonts/` | Anton + Inter (SIL OFL, licenças ao lado) |
| `preview/` | preview 720p **com áudio** e contact sheet do render final |

## Comandos

```bash
npm run assets:site        # imagens públicas do site (rascunho) a partir de ../coleta
npm run tts:setup          # uma vez: instala o Kokoro local (~360 MB)
npm run voice              # gera/usa cache da narração (assets/audio/vo/)
npm run build              # só o passo determinístico (variáveis + áudio + narração + clipes)
npm run check              # build + lint + layout + contraste (precisa passar)
npm run snapshot           # frames-chave em snapshots/
npm run render:draft       # out/video-01-draft.mp4
npm run render             # out/video-01.mp4 (delivery, --strict-variables, masterizado)
npm run loudness           # confere LUFS/true peak
npm run preview            # preview/video-01-preview-720p.mp4
npm run render:placeholder # sem assets do cliente
```

Verificado no box (Linux, Node 22.23.3, FFmpeg 7.1), 30/09/2026 14:02 BRT: `check` passou (0 erros); `render` gerou H.264 1080×1920 30 fps + AAC 48 kHz estéreo, 15,0 s, 16,8 MB em ~1 min; MP4 final **−14,0 LUFS integrado, true peak −2,5 dBTP, LRA 1,2 LU**; transcrição automática (faster-whisper small) do MP4 final reconhece as 6 frases da narração; `voice:force` duas vezes = WAVs idênticos, e o mesmo `spec.json` gera a mesma mixagem. Com 5 clipes de teste em `assets/imagine/` as placas entraram nas cenas S1/S2/S3/S4/S6; sem eles, as cenas voltam ao design com imagens.

**Antes de publicar:** trocar fotos pelas reais do cliente (ou clipes aprovados), confirmar logo/cores e aprovar o roteiro — ver [`../coleta/checklist-cliente.md`](../coleta/checklist-cliente.md) e [`../coleta/pendencias.md`](../coleta/pendencias.md).
