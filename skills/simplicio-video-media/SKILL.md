---
name: simplicio-video-media
description: Use for audio-visual work on any MP4 with the simplicio-video CLI: read metadata, extract audio, review on-screen text frames, generate subtitles (SRT/ASS), burn them into the picture, erase on-screen text in a box and time window, replace the sound track, and assemble a voice track from timed clips (for dubbing). Trigger on requests to translate a video's subtitles or on-screen text, dub a video, clean text off a picture, or change a video's audio. Deterministic, local, ffmpeg and ffprobe only.
---

# simplicio-video media — áudio e vídeo sobre qualquer MP4

`simplicio-video media` faz uma operação por subcomando. Cada um monta um comando ffmpeg a partir dos argumentos, roda e imprime um JSON com o resultado. Nada sai da máquina e nenhum modelo roda aqui.

**Quem decide é você (o agente).** Você escreve a tradução, os tempos e a escolha do que apagar. O CLI só aplica. Nunca invente um tempo de legenda: use a transcrição (`simplicio-video edit transcribe`) ou o texto do autor.

## Pré-requisito

- `ffmpeg` e `ffprobe` com **libass** (para `burn`). Confira com `simplicio-video doctor`.
- No macOS com Homebrew, o `ffmpeg` padrão pode estar quebrado (biblioteca do libvpx faltando). Use o `ffmpeg-full` e ponha o `bin` dele primeiro no PATH.

## Subcomandos

| Subcomando | Faz | Entrada | Saída |
|---|---|---|---|
| `probe` | metadados: duração, largura, altura, fps, se tem áudio, sha256 | MP4 | JSON |
| `audio` | trilha mono PCM (para transcrição ou referência de voz) | MP4 | `.wav` |
| `sheet` | folha de contato de quadros a cada N segundos (revisar texto na tela) | MP4 | `.jpg` |
| `subs` | legenda a partir de cues com tempo | `cues.json` | `.srt` ou `.ass` |
| `burn` | queima SRT ou ASS na imagem | MP4 + legenda | MP4 |
| `mask` | apaga texto dentro de uma caixa, com janela de tempo opcional | MP4 | MP4 |
| `replace-audio` | mantém a imagem e troca a trilha | MP4 + áudio | MP4 |
| `voice-track` | monta uma trilha de voz: um clipe por cue, no início certo | `cues.json` | `.wav` |

## Formato dos cues

```json
{
  "schema": "simplicio.media-cues/v1",
  "cues": [
    {"start": 0.0, "end": 4.24, "text": "Czy wiesz, co dzieje się z psem?"},
    {"start": 4.52, "end": 5.82, "text": "Wielu ludzi nawet o tym nie wie.", "audio": "clips/002.wav"}
  ]
}
```

- `start` e `end` em segundos; `end` precisa ser maior que `start`.
- `text` é usado por `subs`. `audio` é usado só por `voice-track`; caminho relativo ao arquivo de cues.

## Exemplos

**1. Ver o texto que está na tela antes de apagar nada**

```bash
simplicio-video media sheet reel.mp4 -o sheet.jpg --every 2 --cols 8
```

Abra o `sheet.jpg` e anote a caixa (x,y,w,h em pixels) de cada texto. Em um vídeo 720x1280, uma faixa central costuma ficar perto de `150,622,430,104`.

**2. Apagar o texto original dentro de uma janela de tempo**

```bash
simplicio-video media mask reel.mp4 --box 150,622,430,104 --from 0 --to 58 -o clean.mp4
```

`mask` usa `delogo`. Ele preenche a caixa com a vizinhança. Funciona bem sobre fundo liso (camisa escura, grama). Se algo se mexer dentro da caixa (mão, ovo), aparece um borrão retangular. Por isso use caixa justa e janela de tempo curta.

**3. Gerar legenda estilizada e queimar**

```bash
simplicio-video media subs cues.json -o subs.ass --style band        # centralizada, estilo de Reels
simplicio-video media subs cues.json -o subs.srt                      # SRT simples
simplicio-video media burn clean.mp4 subs.ass -o final.mp4 --crf 20
```

`--style bottom` põe a legenda embaixo. `--wrap N` muda a quebra de linha (padrão: 22 no `band`, 42 no `bottom`).

**4. Montar a voz da dublagem e trocar a trilha**

Cada cue precisa de um clipe `audio` já gerado (ex.: `voicestudio tts`). Depois:

```bash
simplicio-video media voice-track cues.json -o voice.wav --duration 58.2 --max-stretch 1.25
simplicio-video media replace-audio clean.mp4 voice.wav -o dubbed.mp4
```

- `voice-track` encaixa cada clipe no `start`. Se o clipe for mais longo que a janela, acelera até `--max-stretch` (padrão 1.25). O que ainda passar aparece em `overflow`: encurte o texto em polonês e gere de novo.
- `replace-audio` corta no fim do menor; use `--keep-length` para não cortar.

**5. Extrair áudio de referência para clonar a voz**

```bash
simplicio-video media audio reel.mp4 -o ref.wav --rate 16000
```

## Regras

- Nenhum subcomando altera a fonte: todos gravam em `-o`, que precisa ser um arquivo novo.
- Texto da tela: `mask` apaga, não traduz. Para texto novo na tela, faça a legenda com `subs`.
- Não publique vídeo de outra pessoa sem autorização por escrito; a versão traduzida também é derivada.
- Nunca use `burn` com legenda sem revisão humana quando o texto for de saúde (ex.: receitas para animais): revise antes.
