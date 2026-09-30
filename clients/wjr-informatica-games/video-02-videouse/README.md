# video-02 — cutdown 11,5 s montado com video-use

Versão curta do [video-01](../video-01/) (Reels 9:16) editada com o **[video-use](https://github.com/browser-use/video-use)** (browser-use, MIT, commit fixado `b877063`, 23/09/2026): transcrição → EDL escrito pelo agente → render com cortes limpos, overlay HyperFrames e autoavaliação. Serve de **prova da etapa 6 da esteira** ([docs/esteira.md](../../../docs/esteira.md)) enquanto não chega footage filmado do cliente. Avaliação completa: [docs/video-use-integracao.md](../../../docs/video-use-integracao.md).

| | |
|---|---|
| Saída | `out/video-02.mp4` (gitignored) · 1080×1920 · 30 fps · 11,47 s · −14,0 LUFS · pico −3,1 dBFS |
| Preview | [preview/video-02-preview-720p.mp4](preview/video-02-preview-720p.mp4) · [contact sheet](preview/contact-sheet.png) |
| EDL | [edit/edl.json](edit/edl.json) — [0–4 s] gancho + promessa · [12,5–20 s] Hall Effect + aprovação + CTA |
| Transcrição | [edit/transcripts/video-01.json](edit/transcripts/video-01.json) (formato Scribe) → [edit/takes_packed.md](edit/takes_packed.md) |
| Legenda lateral | [edit/master.srt](edit/master.srt) (não queimada) |
| Autoavaliação | [edit/verify/](edit/verify/) — filmstrip + forma de onda no corte e nas pontas |
| Memória | [edit/project.md](edit/project.md) |

## Rodar

```bash
bash run.sh   # ~2–3 min na primeira vez (renderiza a fonte); depois usa cache
```

`run.sh` usa a ferramenta opcional [`tools/video-use/`](../../../tools/video-use/README.md) (setup fixado no commit, fora do repo). A **fonte** é uma variante do video-01 gerada pelo spec: [`source.variables.json`](source.variables.json) liga `sv_count_on: false`, escondendo o contador "0N / 03" dos serviços (no corte só aparece o 3º serviço). Depois transcreve localmente (cache), renderiza o overlay, aplica o EDL (`render.py --no-loudnorm --no-subtitles --fps 30`), masteriza com o `master.sh` do video-01, gera SRT, filmstrips, preview e mede loudness. Python: o venv do TTS (`SIMPLICIO_TTS_PY`, precisa de faster-whisper, numpy, Pillow).

## Arquivos

- `source.variables.json` — sobrescreve variáveis do video-01 para gerar a fonte do corte (`out/source.mp4`, gitignored).
- Transcrição e projeção das palavras: `tools/video-use/transcribe_local.py` e `edl_transcript.py` (compartilhados).
- `overlay/` — composição HyperFrames transparente (barra de progresso + glitch no corte), render MOV ProRes 4444.

## Por que MOV e não WebM no overlay

O `render.py` do video-use sobrepõe o overlay com o decodificador VP9 nativo do ffmpeg, que **ignora o canal alfa do WebM** (teste: o WebM do HyperFrames sobre verde puro vira preto; forçando `-c:v libvpx-vp9` o alfa volta). O MOV ProRes 4444 do HyperFrames (`yuva444p12le`) mantém o alfa sem mudar o `render.py`. O SKILL.md do video-use sugere `--format webm` quando precisa de alfa; com o `render.py` atual isso escurece o vídeo inteiro — use **`--format mov`**.
