---
name: simplicio-video-shorts
description: Use to cut a long video into vertical 9:16 short clips with the simplicio-video CLI: inspect the source, plan the windows from a word transcript (scored, non-overlapping), cut with optional captions, or run the whole chain. Deterministic, ffmpeg only; the agent decides the plan, the CLI applies it.
---

# simplicio-video shorts — cortes verticais de vídeo longo

`simplicio-video shorts` transforma um vídeo longo em N cortes 1080x1920 para Shorts, Reels e TikTok. A nota de cada janela vem de regras fixas (ganchos, pergunta, números, densidade de fala), não de um modelo. Sem transcrição, o comando recusa: não há chute.

## Subcomandos

| Subcomando | Faz |
|---|---|
| `inspect FONTE.mp4` | metadados da fonte |
| `plan FONTE.mp4 --transcript words.json --clips 5 --min 20 --max 60` | escreve `plan.json` com janelas, nota e motivo |
| `cut FONTE.mp4 plan.json --subs` | corta conforme o plano; `--subs` queima legenda |
| `run FONTE.mp4 --transcript words.json --clips 5 --subs` | plano e corte em um comando |

`--dry-run` no `run` mostra os comandos ffmpeg sem gravar nada.

## Exemplos

```bash
# transcrição: edit transcribe gera words.json
simplicio-video edit transcribe palestra.mp4 -o words.json --lang pt

simplicio-video shorts inspect palestra.mp4
simplicio-video shorts plan palestra.mp4 --transcript words.json --clips 5 --min 20 --max 60
# revise shorts/plan.json: troque janelas ruins, remova cortes que cortam uma frase
simplicio-video shorts cut palestra.mp4 shorts/plan.json --subs

# ou tudo de uma vez, sem revisar
simplicio-video shorts run palestra.mp4 --transcript words.json --clips 5 --subs --dry-run
```

## Regras

- O plano é a decisão: versione o `plan.json` e revise antes do `cut`.
- `manifest.json` grava o sha256 de cada corte.
- Legenda queimada precisa de ffmpeg com libass (`simplicio-video doctor`).
- Corte que começa no meio de uma frase é ruim: ajuste o plano antes de publicar.
