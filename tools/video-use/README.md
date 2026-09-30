# tools/video-use — edição agêntica (opcional)

[browser-use/video-use](https://github.com/browser-use/video-use) (MIT), fixado no commit `b877063` (23/09/2026) em [`setup.sh`](setup.sh). É uma skill de edição: o agente (humano ou LLM) lê a transcrição palavra a palavra, decide os cortes num **EDL** (`edl.json`) e os helpers em Python/ffmpeg executam — cortes em limite de palavra, fades de 30 ms, concat sem reencode, overlays (inclusive HyperFrames), legendas e autoavaliação por filmstrip. Avaliação completa: [docs/video-use-integracao.md](../../docs/video-use-integracao.md).

## Quando usar × compor direto no HyperFrames

| Pedido | Caminho |
|---|---|
| Vídeo novo a partir do intake/template, motion, tipografia, cenas sintéticas | **HyperFrames direto** (etapas 3–4–7). O LLM/template compõe e o render já corta no quadro; video-use não acrescenta nada |
| "Corta para 15 s / 6 s", versão curta de um vídeo pronto | **video-use** sobre o MP4 renderizado (ex.: [video-02](../../clients/wjr-informatica-games/video-02-videouse/README.md)) — ou, se a cena inteira puder sair, um spec novo no HyperFrames |
| Reordenar blocos de um vídeo pronto, aparar início/fim | **video-use** |
| Footage do cliente (depoimento, bancada, loja, clipes Grok Imagine): tirar "éé", retakes, silêncio | **video-use** (é para isso que ele existe) → clipes vão para os slots `clips` do spec ou viram o vídeo final |
| Legendas (queimadas ou SRT lateral) sobre fala real | **video-use** (`--build-subtitles`), por último na cadeia |
| Revisar cortes de um render ("o corte em 4 s está limpo?") | **video-use** `timeline_view.py` (filmstrip + forma de onda + palavras) |

Regra da esteira: video-use só entra **quando o usuário pede ajuda de edição** ou há footage real. É o op opcional `edit` do [`plugin.json`](../../plugin.json).

## Setup

```bash
bash tools/video-use/setup.sh        # clona/atualiza em ~/.cache/simplicio/video-use no commit fixado; última linha = pasta helpers/
```
Precisa: ffmpeg (libass para legendas queimadas), Python com numpy + Pillow (`SIMPLICIO_TTS_PY`, padrão = venv do TTS) e, para transcrição local, faster-whisper. Transcrição Scribe (a do video-use) precisa de `ELEVENLABS_API_KEY`.

## Uso (layout de um projeto de edição)

```
clients/<c>/video-NN-<nome>/
├── run.sh                 # passos reprodutíveis (copie o do video-02)
├── edit/                  # regra 12 do video-use: tudo da sessão aqui
│   ├── transcripts/<fonte>.json   # formato Scribe (cache por fonte)
│   ├── takes_packed.md    # frases com [início-fim] — o que o agente lê
│   ├── edl.json           # decisão de corte (versionada)
│   ├── master.srt         # legendas na linha do tempo da saída
│   ├── project.md         # memória da sessão
│   └── verify/*.png       # autoavaliação no(s) corte(s)
├── overlay/               # composição HyperFrames transparente (opcional)
└── preview/               # preview 720p + contact sheet (versionados); out/ é gitignored
```

```bash
H=$(bash tools/video-use/setup.sh --quiet)
PY=${SIMPLICIO_TTS_PY:-~/.local/share/simplicio-tts/cbvenv/bin/python}
# 1. transcrição (local, sem chave; --script alinha à narração conhecida do spec)
$PY tools/video-use/transcribe_local.py fonte.mp4 -o edit/transcripts/fonte.json [--script spec.json]
#    ou Scribe: $PY $H/transcribe.py fonte.mp4  (ELEVENLABS_API_KEY; melhor para fala real)
$PY $H/pack_transcripts.py --edit-dir edit
# 2. o agente propõe a estratégia em texto, o usuário confirma, o agente escreve edit/edl.json
# 3. overlay HyperFrames (se houver): SEMPRE --format mov
(cd overlay && npx --yes hyperframes@0.8.97 render --format mov --output ../out/overlay.mov .)
# 4. render do EDL (loudness pelo nosso master)
$PY $H/render.py edit/edl.json -o out/final.raw.mp4 --no-loudnorm --fps 30 [--build-subtitles | --no-subtitles]
bash clients/wjr-informatica-games/video-01/scripts/master.sh "$PWD/out/final.raw.mp4" "$PWD/out/final.mp4"
# 5. autoavaliação em cada corte (±1,5 s), palavras na linha do tempo da saída
$PY tools/video-use/edl_transcript.py edit/edl.json -o edit/verify/out.words.json
$PY $H/timeline_view.py out/final.mp4 2.5 5.5 -o edit/verify/corte.png --transcript edit/verify/out.words.json
```

## Arquivos daqui

| Arquivo | O quê |
|---|---|
| `setup.sh` | Clona o video-use no commit fixado, confere deps, imprime a pasta `helpers/` |
| `transcribe_local.py` | faster-whisper → JSON formato Scribe (sem diarização/eventos). `--script spec.json` troca as palavras do ASR pelo texto do roteiro e prende cada palavra em `[t, t+max_s]` (estável entre execuções) |
| `edl_transcript.py` | Projeta as transcrições das fontes na linha do tempo da saída do EDL (para `timeline_view --transcript`) |

## Travas (aprendidas no video-02)

- **Overlay HyperFrames = MOV** (ProRes 4444). WebM perde o alfa no `render.py` (decodificador VP9 nativo) e escurece o vídeo inteiro.
- **`--no-loudnorm`** + nosso `master.sh` (−14 LUFS / TP −1,5 dBTP; o do video-use é −1 dBTP).
- Não queime legenda sobre composição que já tem tipografia cinética; gere `master.srt` como legenda lateral.
- Transcrição é cache: só refaça se a fonte ou o roteiro mudarem (regra 9).
- Estratégia de corte confirmada com o usuário antes do EDL (regra 11); nada é escrito dentro da pasta do video-use (regra 12).
- Fonte com texto que depende do contexto (contadores "03 / 03", "passo 2") → gere uma variante da fonte pelo spec em vez de mascarar no overlay (ex.: `sv_count_on: false` no video-02).
