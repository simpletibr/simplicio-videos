---
name: simplicio-video-edit
description: Use for edit-decision-list editing of any MP4 with the simplicio-video CLI (video-use): set up the editor, transcribe a source locally with faster-whisper (no cloud key), pack transcripts for review, render a cut list (EDL) with subtitles, and verify a cut visually with a filmstrip. The agent writes the EDL; helpers run ffmpeg.
---

# simplicio-video edit — edição por EDL (video-use)

`simplicio-video edit` encadeia o `video-use` fixado no repo (`tools/video-use`). O agente lê a transcrição palavra a palavra, escreve o `edl.json` (cortes, ordem, legendas) e os helpers em Python/ffmpeg executam. O EDL é a decisão versionada.

## Subcomandos

| Subcomando | Faz |
|---|---|
| `setup` | clona/atualiza o video-use no commit fixado (`tools/video-use/setup.sh`) |
| `transcribe FONTE.mp4 [-o OUT] [--script spec.json]` | transcrição local com faster-whisper; grava JSON no formato Scribe |
| `pack EDIT_DIR` | junta as transcrições em `takes_packed.md` para revisão |
| `render EDL.json -o OUT.mp4` | aplica o EDL (cortes em limite de palavra, fades de 30 ms, legendas) |
| `verify VIDEO T0 T1 -o PNG [--transcript words.json]` | filmstrip do trecho para conferir o corte |

## Pré-requisitos

- `setup` precisa de um Python com as dependências do video-use (numpy, Pillow, faster-whisper). Aponte para ele com `SIMPLICIO_TTS_PY=/caminho/python`.
- `transcribe` usa faster-whisper (modelo `small` por padrão, idioma `pt`). Sem o modelo em cache, ele baixa do Hugging Face.
- `render` com legenda precisa de ffmpeg com libass.

## Exemplo: cortar um trecho e legendar

```bash
export SIMPLICIO_TTS_PY=/caminho/para/python-com-faster-whisper
simplicio-video edit setup
simplicio-video edit transcribe entrevista.mp4 -o edit/transcripts/entrevista.json --lang pt
simplicio-video edit pack edit
# escreva edit/edl.json com os intervalos escolhidos (start/end em segundos, no limite de palavra)
simplicio-video edit render edit/edl.json -o out/final.mp4
simplicio-video edit verify out/final.mp4 12.0 18.5 -o out/check.png
```

## Regras

- Corte só em limite de palavra; o helper arredonda, mas confira no `verify`.
- Não chame `render` sem `verify` para trecho que vai ao ar.
- Para legenda traduzida ou texto apagado, use a skill `simplicio-video-media` (`subs`, `burn`, `mask`).
