# voices/ — narração (TTS) com escolha de provider + cache

A voz é um **passo de geração com cache**: o TTS roda uma vez por frase, o WAV tratado fica versionado em `clients/<c>/video-NN/assets/audio/vo/` com `manifest.json` (hash de texto + provider + tratamento), e o render só lê esses arquivos — por isso o render é determinístico mesmo com TTS que não repete o áudio bit a bit.

## Providers

| Provider (`spec.json → voice.provider`) | Tipo | Custo / chave | Qualidade pt-BR | Guia |
|---|---|---|---|---|
| `file` + **Gemini** (padrão atual) | nuvem, gerado no Google AI Studio e baixado | conta Google; API opcional com `GEMINI_API_KEY` | ótima, voz Puck no WJR | [gemini.md](gemini.md) |
| `voxcpm` (**local**, clone/design) | roda no box, GPU recomendada | grátis (Apache-2.0) | ótima, 30 idiomas | [voxcpm.md](voxcpm.md) |
| `openvoice` (**local**, clone) | timbre da referência sobre base Kokoro | grátis (MIT) | boa | [openvoice.md](openvoice.md) |
| `voicestudio` (**local**, API HTTP) | app VoiceStudio em `localhost:3900` | grátis (AGPL-3.0, só via HTTP) | depende do engine | [voicestudio.md](voicestudio.md) |
| `audio8` (**local**, CLI `audio8-tts`) | GPU recomendada, env própria (`AUDIO8_TTS_BIN`) | grátis (Apache-2.0, 0.6B) | clone zero-shot | [audio8.md](audio8.md) |
| `elevenlabs` | nuvem (API) | pago, `ELEVENLABS_API_KEY` | ótima, muitas vozes pt-BR | [elevenlabs.md](elevenlabs.md) |
| `xai` | nuvem (API) | pago, `XAI_API_KEY` (US$ 15 / 1M caracteres em 30/09/2026) | boa | [xai.md](xai.md) |
| `chatterbox` / `kokoro` (**local**) | roda no box/CPU, offline | grátis (MIT / Apache-2.0) | boa / razoável | [local.md](local.md) |
| `file` (qualquer outro) | WAV/MP3 externo | — | depende | [narracao-tts.md](narracao-tts.md#narração-gerada-fora-provider-file-ex-gemini-tts-no-google-ai-studio) |
| `none` | sem narração | — | — | — |

Como o intake escolhe: pergunta B6/B7 do [questionário](../intake/questionario.md) → `pedido.voz.provider`/`tipo`/`voz_id` → template do setor sugere o tipo de voz → `spec.json → voice`.

## Regras (valem para todos)

- `npm run voice` corta silêncio, trata (EQ/compressor/sala), converte para 48 kHz mono e **nunca acelera**: frase maior que `max_s` = erro → reajustar tempos ou texto (ver [gemini.md → Reajustar os tempos](gemini.md#reajustar-os-tempos-quando-as-frases-mudam-de-duração)).
- Depois de gerar: faster-whisper confere cada frase (texto reconhecido vai para o manifest) e dá os timestamps por palavra usados nas batidas (`"@t"`) e na legenda (`motion/patterns/caption-word-highlight`).
- Registrar provider, modelo, voz, conta, data e termos em `assets/audio/LICENSES.md` do vídeo.
- Não clonar voz de pessoa real sem autorização escrita dela (vale para `voxcpm`, `openvoice` e `voicestudio`; guarde a autorização junto de `reference_audio`). Chaves só no ambiente/`.env` (gitignored).

Detalhes técnicos do pipeline de voz (manifest, hash, sementes, tratamento, mixagem/ducking): [narracao-tts.md](narracao-tts.md).
Benchmark planejado de TTS open-source: [docs/pipeline-deterministico-gemini.md](../docs/pipeline-deterministico-gemini.md#e-benchmark-de-tts-open-source-depois--gemini-é-o-padrão-por-enquanto).
