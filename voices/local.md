# Vozes locais (providers `chatterbox` e `kokoro`)

Grátis, offline, rodam no box (CPU). Instalação única por máquina:

```bash
cd clients/<c>/video-NN
npm run tts:setup     # venv em ~/.local/share/simplicio-tts/cbvenv: torch CPU + chatterbox + kokoro-onnx + faster-whisper
npm run voice         # gera/usa cache (~15 s por take em CPU)
```

| Provider | Modelo | Licença | Notas |
|---|---|---|---|
| `chatterbox` | Chatterbox Multilingual V3 | MIT | mais natural; clona uma referência **sintética** (Kokoro `pm_alex`), nunca voz real; melhor de 3 takes por ASR; marca d'água Perth imperceptível |
| `kokoro` | Kokoro-82M (`pf_dora`, `pm_alex`, `pm_santa`) | Apache-2.0 | mais leve e rápido, menos natural |

Marcas/estrangeirismos: use `"say"` com grafia fonética (ex.: `"Hall Effect"` → `"Ról Iféct"`). Detalhes, comparativo medido (UTMOS/WER) e parâmetros: [narracao-tts.md](narracao-tts.md#provedor-local-recomendado-chatterbox-multilingual-v3-local-mit) e `video-01/assets/audio/LICENSES.md`.
