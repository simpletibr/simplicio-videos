# Narração (voice-over) com TTS — como funciona e como trocar de voz

Aplicado no `clients/wjr-informatica-games/video-01`. Tudo parte de `spec.json → voice`; nada de LLM.

## Fluxo

```
spec.json → voice.lines[] (texto, "say" opcional, início t, slot max_s)
   │  npm run voice          (scripts/voice.py — TTS + corte de silêncio + atempo ≤1,3× + 48 kHz mono)
   ▼
assets/audio/vo/vo1..vo6-<hash>.wav + manifest.json   ← versionados (cache: mesmo texto/voz = mesmo arquivo)
   │  npm run build          (scripts/build.mjs — posiciona cada frase em t, ducking da música/SFX pela voz)
   ▼
assets/audio/build/mix.wav  →  hyperframes render  →  scripts/master.sh (−14 LUFS, TP ≤ −1,5 dBTP)
```

- O nome de cada arquivo inclui um hash de (provedor, modelo, voz, velocidade, idioma, texto falado, slot). Mudou o texto → `npm run voice` gera só aquela frase de novo; o resto vem do cache. Sem mudança, **não precisa ter o TTS instalado** para renderizar (os WAVs estão no repo).
- `build.mjs` falha com mensagem clara se o texto de uma frase no `spec.json` não bater com o que foi gerado (evita narração velha).
- Verificado: dois `voice:force` seguidos geraram WAVs idênticos (md5) com Kokoro em CPU; transcrição automática (faster-whisper small) da mixagem final reconheceu as 6 frases (uma única variação: "Chama" → "Tchama", pronúncia da voz).

## Provedor padrão: Kokoro-82M (local, Apache-2.0)

```bash
npm run tts:setup     # uma vez: venv + kokoro-onnx + modelo (~360 MB) em ~/.local/share/simplicio-tts
npm run voice         # gera/usa cache
npm run voice:force   # regera tudo
```
Vozes pt-BR do Kokoro v1.0: `pm_alex` (padrão), `pm_santa` (masculinas), `pf_dora` (feminina). Troque em `spec.json → voice.providers.kokoro.voice`. Palavras em inglês/marcas: use `"say"` com a pronúncia (ex.: `"Xbox"` → `"Équis box"`).

Comparativo de licenças (Piper, XTTS, edge-tts, ElevenLabs): [`video-01/assets/audio/LICENSES.md`](../clients/wjr-informatica-games/video-01/assets/audio/LICENSES.md).

## Opção ElevenLabs (paga; não precisa de chave agora)

1. Crie a chave em elevenlabs.io e escolha uma voz pt-BR (copie o **voice ID**).
2. No terminal: `export ELEVENLABS_API_KEY=...` (não commitar; pode ir num `.env` local — `.env` já está no `.gitignore`).
3. Em `spec.json`:
   ```json
   "voice": {
     "provider": "elevenlabs",
     "providers": {
       "elevenlabs": { "model": "eleven_multilingual_v2", "voice_id": "SEU_VOICE_ID",
                       "stability": 0.4, "similarity_boost": 0.8, "style": 0.35, "env": "ELEVENLABS_API_KEY" }
     }
   }
   ```
   (ou, sem editar o arquivo: `VOICE_PROVIDER=elevenlabs npm run voice`).
4. `npm run voice && npm run render`. O script chama `POST https://api.elevenlabs.io/v1/text-to-speech/{voice_id}?output_format=mp3_44100_128` com o header `xi-api-key`, e aplica o mesmo corte/atempo/48 kHz.
5. Licença: só gere a versão final **com plano pago ativo** (o gratuito não permite uso comercial) e registre plano/voz/data em `assets/audio/LICENSES.md`.

## Ajustes finos de mixagem (`spec.json → voice`)

| Campo | Padrão | Efeito |
|---|---|---|
| `gain_db` | 0 | volume da voz (depois do nivelamento por frase) |
| `duck_music_db` | 10 | quanto a música abaixa sob a voz (envelope com 60 ms de antecipação, 300 ms de retorno) |
| `duck_sfx_db` | 6 | quanto os efeitos abaixam sob a voz |
| `lines[].t` / `max_s` | — | início (no grid de 120 BPM) e tamanho do slot; frase maior que o slot é acelerada até 1,3×, acima disso o script para e pede texto menor |
