---
name: simplicio-video-edit
description: Use for edit-decision-list editing of any MP4 with the simplicio-video CLI (video-use): set up the editor, color grade (auto, presets, analyze), transcribe a source locally with faster-whisper (no cloud key), pack transcripts for review, render a cut list (EDL) with subtitles, and verify a cut visually with a filmstrip. The agent writes the EDL; helpers run ffmpeg.
---

# simplicio-video edit — edição por EDL (video-use)

`simplicio-video edit` encadeia o `video-use` fixado no pacote (os arquivos vão dentro do wheel). O agente lê a transcrição palavra a palavra, escreve o `edl.json` (cortes, ordem, legendas) e os helpers em Python/ffmpeg executam. O EDL é a decisão versionada.

## Subcomandos

| Subcomando | Faz |
|---|---|
| `setup` | clona/atualiza o video-use no commit fixado (`setup.sh` do pacote) |
| `transcribe FONTE.mp4 -o OUT.json [--script spec.json]` | transcrição local com faster-whisper; grava JSON no formato Scribe |
| `pack EDIT_DIR` | junta as transcrições em `takes_packed.md` para revisão |
| `render EDL.json -o OUT.mp4` | aplica o EDL (cortes em limite de palavra, fades de 30 ms, legendas) |
| `verify VIDEO T0 T1 -o PNG [--transcript words.json]` | filmstrip do trecho para conferir o corte |
| `grade FONTE.mp4 -o OUT.mp4 [--preset N \| --filter F]` | correção de cor (ffmpeg). Sem opção = modo auto: mede o clipe e aplica uma correção sutil. Presets: `subtle`, `neutral_punch`, `warm_cinematic` (look retrô, opt-in), `none` |
| `grade --analyze FONTE.mp4` / `grade --list-presets` | só imprime o filtro do modo auto e as medidas / os presets; não grava nada |
| `transcribe-batch DIR` | transcrição em lote com o ElevenLabs Scribe (terceiro pago, `ELEVENLABS_API_KEY`); só no terminal, o MCP recusa |

## Pré-requisitos

- `setup` precisa de um Python com as dependências do video-use (numpy, Pillow, soundfile, faster-whisper). Aponte para ele com `SIMPLICIO_TTS_PY=/caminho/python`.
- `transcribe` exige `-o` (como `render` e `verify`); sem ele o comando para com erro. Usa faster-whisper (modelo `small` por padrão, idioma `pt`). Sem o modelo em cache, ele baixa do Hugging Face.
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
simplicio-video edit grade --analyze entrevista.mp4          # o que o modo auto faria
simplicio-video edit grade entrevista.mp4 -o out/graded.mp4 --preset neutral_punch
```

## Pelo MCP (`video.edit`)

- Toda saída (`-o`, `--out`, `--output`) tem de ser um caminho **absoluto**; relativo é recusado e `transcribe`, `render`, `verify` e `grade` (ao gravar) exigem `-o`.
- `transcribe-batch` é só do terminal: o MCP recusa, porque o Scribe é um terceiro pago.

## Regras

- Corte só em limite de palavra; o helper arredonda, mas confira no `verify`.
- Não chame `render` sem `verify` para trecho que vai ao ar.
- Para legenda traduzida ou texto apagado, use a skill `simplicio-video-media` (`subs`, `burn`, `mask`).
