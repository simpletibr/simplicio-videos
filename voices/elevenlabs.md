# ElevenLabs (provider `elevenlabs`)

Pago; **desligado** até existir chave e plano. Implementado em `video-01/scripts/voice.py` (não testado sem chave).

1. Crie a chave em https://elevenlabs.io/app/settings/api-keys e escolha uma voz pt-BR na Voice Library (copie o **voice ID**).
2. `export ELEVENLABS_API_KEY=...` e preencha `spec.json → voice.providers.elevenlabs.voice_id`.
3. `VOICE_PROVIDER=elevenlabs npm run voice && npm run render` — chama `POST https://api.elevenlabs.io/v1/text-to-speech/{voice_id}` e aplica o mesmo corte/tratamento/checagem de tempo.
4. **Licença:** só gere a versão final com plano pago ativo (o plano gratuito não dá uso comercial) e registre plano/voz/data em `assets/audio/LICENSES.md`.

Docs: https://elevenlabs.io/docs/api-reference/text-to-speech · Visão geral dos providers: [README.md](README.md).
