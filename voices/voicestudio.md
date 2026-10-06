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
