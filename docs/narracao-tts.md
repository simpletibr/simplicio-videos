# Narração (voice-over) com TTS — como funciona e como trocar de voz

Aplicado no `clients/wjr-informatica-games/video-01`. Tudo parte de `spec.json → voice`; nada de LLM.

## Fluxo

```
spec.json → voice.lines[] (texto, "say" opcional, início t, slot max_s)
   │  npm run voice          (scripts/voice.py — TTS em 3 sementes → corte de silêncio → escolha por ASR
   │                          → EQ + compressor + sala → 48 kHz mono; SEM aceleração)
   ▼
assets/audio/vo/vo1..vo9-<hash>.wav + manifest.json + ref/pm_alex.wav   ← versionados
   │  npm run build          (scripts/build.mjs — posiciona cada frase em t, nivela, ducking da música/SFX)
   ▼
assets/audio/build/mix.wav  →  hyperframes render  →  scripts/master.sh (−14 LUFS, TP ≤ −1,5 dBTP)
```

- O nome de cada arquivo inclui um hash de (provedor + ajustes, texto falado, cadeia de tratamento, modo de seleção). Mudou o texto → `npm run voice` gera só aquela frase; o resto vem do cache. `t`/`max_s` **não** entram no hash (mover uma frase não regera). Sem mudança, **não precisa ter o TTS instalado** para renderizar (os WAVs estão no repo).
- **Sem time-stretch**: a voz sai na velocidade natural. Se uma frase não cabe no slot (`max_s`), o script grava o manifest e **para com erro** listando as frases longas → encurte o texto ou mova/alargue o slot (e ajuste a cena no `index.html`).
- `build.mjs` falha com mensagem clara se o texto de uma frase no `spec.json` não bater com o que foi gerado (evita narração velha).
- O manifest guarda, por frase: semente escolhida, nota e texto do ASR, duração e slot.

## Provedor padrão: Chatterbox Multilingual V3 (local, MIT)

```bash
npm run tts:setup     # uma vez: venv (uv, torch CPU) + chatterbox (git) + kokoro-onnx + faster-whisper
npm run voice         # gera/usa cache (~15 s por take em CPU; 3 takes por frase)
npm run voice:force   # regera tudo
```

- **Timbre**: o Chatterbox clona um clipe de referência. A referência é **sintética** (Kokoro `pm_alex`, Apache-2.0), gerada automaticamente em `assets/audio/vo/ref/pm_alex.wav` — nenhuma voz de pessoa real é clonada. Troque em `spec.json → voice.providers.chatterbox.reference` (ex.: `"voice": "pf_dora"` para feminina).
- **Melhor de 3** (`"select": "asr"`): cada frase é gerada com as sementes 7, 11 e 23; o faster-whisper `small` transcreve cada take e fica o mais fiel ao texto (empate → o mais curto). Sementes fixas deixam o resultado estável, mas o Chatterbox em CPU **não garante WAV bit a bit idêntico** entre execuções (numa regeração a vo4 escolheu outra semente com a mesma nota). Por isso os WAVs versionados são a fonte da verdade: sem mudança de texto/ajuste, o cache é usado e o render é reproduzível.
- **Marcas / inglês**: use `"say"` com a grafia fonética — `"Xbox"` → `"Équis box"`, `"PS5"` → `"PS cinco"`, `"WJR"` → `"dáblio jota erre"`, `"Hall Effect"` → `"Ról Iféct"` (o "h" do português é mudo; o "R" inicial soa como o "h" do inglês).
- **Tratamento** (`voice.processing`, ffmpeg): passa-altas 85 Hz, −2,5 dB @320 Hz, +2,5 dB @3,4 kHz, +1,5 dB @9 kHz, compressor 2,5:1, sala curta sutil (`aecho`). Ajuste a string e rode `npm run voice` (entra no hash).
- Marca d'água: o áudio do Chatterbox leva a marca imperceptível **Perth** (identifica áudio sintético; não é audível).
- Alternativa local mais leve: `"provider": "kokoro"` (Kokoro-82M, `pf_dora`/`pm_alex`/`pm_santa`, `speed` 1.0) — menos natural, mais rápido.

Comparativo medido (UTMOS/WER) e licenças de tudo que foi avaliado: [`video-01/assets/audio/LICENSES.md`](../clients/wjr-informatica-games/video-01/assets/audio/LICENSES.md).

## Narração gerada fora (provider `file`, ex.: Gemini TTS no Google AI Studio)

1. Gere uma frase por arquivo, na ordem de `voice.lines`, e salve em `clients/.../video-01/assets/audio/vo/external/line-01.wav … line-09.wav` (aceita também `vo1.wav`, `.mp3`, `.m4a`). Tabela com texto e duração máxima de cada frase: `assets/audio/vo/external/README.md`.
2. `VOICE_PROVIDER=file npm run voice` (ou `"provider": "file"` no `spec.json`) → corta silêncio, aplica o mesmo tratamento, 48 kHz mono, confere o slot (sem acelerar) e transcreve para o manifest. Trocou um arquivo → o hash muda e só aquela frase é reprocessada.
3. `npm run render`. Registre modelo/voz/data e os termos do serviço em `assets/audio/LICENSES.md`.

## Opções pagas (desligadas; não precisam de chave agora)

Chaves só no ambiente (ou num `.env` local — `.env` está no `.gitignore`). Troca sem editar arquivo: `VOICE_PROVIDER=<provedor> npm run voice`.

### ElevenLabs
1. Crie a chave em elevenlabs.io e escolha uma voz pt-BR (copie o **voice ID**).
2. `export ELEVENLABS_API_KEY=...` e preencha `spec.json → voice.providers.elevenlabs.voice_id`.
3. `VOICE_PROVIDER=elevenlabs npm run voice && npm run render` (chama `POST https://api.elevenlabs.io/v1/text-to-speech/{voice_id}`).
4. Licença: só gere a versão final **com plano pago ativo** e registre plano/voz/data em `assets/audio/LICENSES.md`.

### xAI (Grok) Text to Speech
1. Crie a chave em console.x.ai → `export XAI_API_KEY=...`.
2. `spec.json → voice.providers.xai`: `voice_id` (`eve`, `ara`, `rex`, `sal`, `leo` ou uma voz custom; lista em `GET https://api.x.ai/v1/tts/voices`), `language: "pt-BR"`.
3. `VOICE_PROVIDER=xai npm run voice && npm run render` (chama `POST https://api.x.ai/v1/tts`, recebe MP3 e aplica o mesmo corte/tratamento).
4. Custo em 30/09/2026: US$ 15 / 1 milhão de caracteres. Termos: o output é seu e pode ser usado comercialmente; não pode ser apresentado como voz humana nem usado para treinar modelos. [Docs](https://docs.x.ai/developers/model-capabilities/audio/text-to-speech).

## Ajustes finos de mixagem (`spec.json → voice`)

| Campo | Padrão | Efeito |
|---|---|---|
| `gain_db` | 0 | volume da voz (depois do nivelamento por frase) |
| `duck_music_db` | 10 | quanto a música abaixa sob a voz (envelope com 60 ms de antecipação, 300 ms de retorno) |
| `duck_sfx_db` | 6 | quanto os efeitos abaixam sob a voz |
| `lines[].t` / `max_s` | — | início e tamanho do slot; frase maior que o slot = erro (sem aceleração) |
| `processing` | ver acima | cadeia ffmpeg aplicada em cada frase |
