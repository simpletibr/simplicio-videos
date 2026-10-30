# Audio8 TTS (`provider: audio8`)

Clonagem zero-shot com o [audio8_tts](https://github.com/wesleysimplicio/audio8_tts). O simplicio-video não vendora o modelo: ele chama o CLI `audio8-tts` do próprio repo, instalado no seu venv.

## Instalar (fora do simplicio-video)

```bash
git clone https://github.com/wesleysimplicio/audio8_tts && cd audio8_tts
python3 -m venv .venv && . .venv/bin/activate
pip install -e .            # GPU CUDA recomendada; ver o README do audio8_tts
export AUDIO8_TTS_BIN="$PWD/.venv/bin/audio8-tts"
```

## Contrato

```yaml
voz:
  provider: audio8
  providers:
    audio8:
      model: Edge0/Audio8-TTS-Realistic-0.6b   # padrão
      reference_audio: assets/voz/autorizada.wav   # só com autorização escrita do dono da voz
      reference_text: "transcrição exata do áudio de referência"
```

## Licença e limites

- Código e pesos do 0.6B: Apache-2.0. O 0.1B tem licença própria do checkpoint; por isso não é o padrão.
- Clonagem só com referência autorizada pelo dono da voz (ver `voices/README.md`).
- Sem GPU, não há benchmark aqui: o teste de geração roda na VPS.
