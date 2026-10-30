# VoiceStudio (provider `voicestudio`)

[debpalash/VoiceStudio](https://github.com/debpalash/VoiceStudio) · **AGPL-3.0**: used only over its local HTTP API, never vendored or imported here. Fully local voice cloning/design app; your cloned voices are "voice profiles".

1. Install and start VoiceStudio (desktop app or backend on port 3900); create a voice profile from an authorized reference recording.
2. `GET $VOICESTUDIO_URL/v1/audio/voices` lists profile ids.

```yaml
voz:
  provider: voicestudio
  voice: <profile-id>            # or providers.voicestudio.voice
  providers:
    voicestudio: { model: omnivoice }   # any installed engine id
```

```bash
export VOICESTUDIO_URL=http://localhost:3900     # default; VOICESTUDIO_API_KEY if you set one
simplicio-video voice contract.yaml --provider voicestudio
```

Calls `POST /v1/audio/speech` (OpenAI-compatible, `response_format=wav`). Takes are kept in `<file.dir>/voicestudio/line-NN.wav`.

## Exportar uma dublagem pronta, com o fundo preservado

```bash
simplicio-video voicestudio dub-export --job ID --lang pl [--bed-level 1.0] -o dublado.mp4
```

Exporta um job de dublagem que **já existe** no app: o vídeo sai com a faixa dublada do idioma escolhido por cima do fundo original (música e efeitos, sem a fala), que o app separa na dublagem. Chama `GET /dub/download/{job}?preserve_bg=true&bed_level=…&default_track=LANG&include_tracks=LANG` na API loopback (`VOICESTUDIO_URL`, padrão `http://127.0.0.1:3900`), sem importar código do app (AGPL-3.0 só por HTTP).

- `--bed-level` vai de 0 (fundo mudo) a 4; 1.0 mantém o nível original. Um limitador do app evita estouro quando o fundo sobe.
- **Não gera nada.** Transcrição, tradução, voz e separação do fundo acontecem no app (modelos pesados e GPU). Sem o job pronto no app, o comando só devolve o erro do app em linguagem clara (job inexistente, idioma sem faixa dublada, fundo indisponível).
- O ID do job aceita só letras, números, hífen e sublinhado; o idioma é o código da faixa dublada no app (ex.: `pl`).
- Fonte de verdade: VoiceStudio `beeaae08`, `backend/api/routers/dub_export.py` e `docs/dubbing/export.md`.

