# xAI / Grok TTS (provider `xai`)

Pago; **desligado** até existir chave. Implementado em `video-01/scripts/voice.py` (não testado sem chave).

1. Crie a chave em https://console.x.ai → `export XAI_API_KEY=...`.
2. `spec.json → voice.providers.xai`: `voice_id` (`eve`, `ara`, `rex`, `sal`, `leo` ou voz custom — lista em `GET https://api.x.ai/v1/tts/voices`), `language: "pt-BR"`.
3. `VOICE_PROVIDER=xai npm run voice && npm run render` — chama `POST https://api.x.ai/v1/tts`, recebe MP3 e aplica o mesmo corte/tratamento.
4. Custo em 30/09/2026: US$ 15 / 1 milhão de caracteres. Termos: o output é seu e pode ser usado comercialmente; não pode ser apresentado como voz humana nem usado para treinar modelos.

Docs: https://docs.x.ai/developers/model-capabilities/audio/text-to-speech · Visão geral: [README.md](README.md).
