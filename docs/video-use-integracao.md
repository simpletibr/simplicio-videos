# video-use na esteira (etapa 6) — avaliação e integração

**O que é:** [browser-use/video-use](https://github.com/browser-use/video-use) (MIT, avaliado no commit `b877063`, 23/09/2026) é uma *skill* para Claude Code/Codex/qualquer agente com shell que edita **footage bruto** por conversa: o próprio agente anfitrião lê a transcrição, propõe a estratégia, escreve um EDL (`edl.json`) e os helpers em Python/ffmpeg executam. Não embute LLM; não precisa de chave de modelo.

Uso e setup: [`tools/video-use/`](../tools/video-use/README.md) (ferramenta **opcional**, op `edit` do plugin). Prova feita aqui: [`clients/wjr-informatica-games/video-02-videouse/`](../clients/wjr-informatica-games/video-02-videouse/README.md) — cutdown de 11,5 s do video-01 (transcrição local → EDL → overlay HyperFrames → render → autoavaliação), 30/09/2026.

## Peças do video-use

| Helper | Faz | Dependências |
|---|---|---|
| `transcribe.py` / `transcribe_batch.py` | Transcrição palavra a palavra (ElevenLabs **Scribe**, diarização, eventos de áudio) → `edit/transcripts/<fonte>.json` | **`ELEVENLABS_API_KEY`** (único item pago) |
| `pack_transcripts.py` | Agrupa em frases (quebra em silêncio ≥ 0,5 s / troca de falante) → `takes_packed.md`, o que o agente lê para cortar | — |
| `timeline_view.py` | Filmstrip + forma de onda (+ palavras) de um trecho → PNG, para o agente "ver" o corte | numpy, Pillow |
| `render.py` | EDL → extrai cada trecho (fades de 30 ms, grade) → concat sem reencode → overlays (`setpts` + `enable=between`) → legendas por último → loudnorm (−14 LUFS / −1 dBTP) | ffmpeg (libass) |
| `grade.py` | Presets/auto-grade por trecho | ffmpeg |
| `SKILL.md` | Processo (inventário → conversa → estratégia confirmada → EDL → autoavaliação → `project.md`) e 12 regras duras (legenda por último, nunca cortar dentro de palavra, folga 30–200 ms, fades, etc.) | — |

## Como encaixa na esteira

```
footage do cliente (ou render nosso) ──► transcrição palavra a palavra ──► takes_packed.md
        │                                                                      │
        │                                   agente anfitrião (conversa) ──► edl.json  ◄── versionado (decisão não determinística congelada)
        ▼                                                                      │
 overlays: blocos de motion/ renderizados em MOV com alfa (HyperFrames) ──────►│
 voz: narração do voices/ (se o corte precisar de VO nova) ────────────────────►│
                                                                               ▼
                                               render.py (ffmpeg puro, determinístico) → master.sh (nosso) → QA
```

- **Onde entra:** etapa 6, *só quando há vídeo filmado* (depoimentos, bancada, loja, clipes do Grok Imagine). O resultado vira clipe para os slots `clips` do spec **ou** vídeo final (cutdown, versão por canal).
- **Determinismo:** a *decisão* de corte é do LLM, mas fica congelada no `edl.json` versionado; reexecutar o EDL é ffmpeg puro. Transcrições são cache por fonte (regra 9 do próprio video-use).
- **Com a biblioteca de motion:** overlays são blocos de [`motion/`](../src/simplicio_video/data/motion/README.md) renderizados com `hyperframes render --format mov` (ProRes 4444 com alfa) e referenciados em `overlays[]` do EDL.
- **Com a voz:** o video-use não gera voz; se o corte precisar de narração nova, ela vem de [`voices/`](../voices/README.md) (cache) e entra como faixa/overlay de áudio — ainda não automatizado.

## Decisões tomadas aqui

| Tema | Decisão | Por quê |
|---|---|---|
| Transcrição | `tools/video-use/transcribe_local.py`: faster-whisper local → JSON formato Scribe, com **alinhamento ao roteiro** (`--script spec.json`) | Sem chave ElevenLabs. O SKILL.md desaconselha Whisper local (lento, normaliza "éé/hã"); para **narração nossa** isso não importa (texto conhecido, sem hesitação) e o alinhamento corrige erros de ASR ("Se o console" → "Seu console", "Whole Effect" → "Hall Effect") e prende cada palavra na janela conhecida da fala `[t, t + max_s]` — sem isso o faster-whisper variou até ~80 ms entre execuções e pôs "Drift?" antes do corte de 4,0 s (vazava na legenda). Transcrição fica em cache. Para depoimento real de cliente, preferir Scribe (diarização + hesitações = sinal editorial). |
| Overlay | **MOV** (ProRes 4444), nunca WebM | Bug encontrado: o `render.py` decodifica WebM com o VP9 nativo do ffmpeg, que descarta o alfa → overlay preto cobrindo tudo. Testado: WebM sobre verde = preto; com `-c:v libvpx-vp9` = ok; MOV = ok. |
| Loudness | `render.py --no-loudnorm` + nosso `master.sh` | Alvo do repo: −14 LUFS / TP −1,5 dBTP (o do video-use é −1 dBTP). |
| Legendas | `master.srt` gerado pelo helper, **não queimado** | Nossas composições já têm tipografia cinética; SRT fica como legenda lateral (upload no Instagram/TikTok). Para footage cru, queimar é bom (regra: por último). |
| Instalação | `tools/video-use/setup.sh` clona o video-use fixado no commit em `~/.cache/simplicio/video-use` | Não vendorizar; versão fixa = reprodutível. |

## O que o video-use acrescentou de fato

1. **Corte com precisão de palavra, sem estalo:** EDL em segundos + fades de 30 ms + concat sem reencode. O corte em 4,0 s do video-02 saiu limpo (ver `edit/verify/corte-4s.png`).
2. **Autoavaliação visual barata:** `timeline_view` (filmstrip + onda + palavras na linha do tempo da saída) — útil também para QA dos nossos renders HyperFrames.
3. **Formato de EDL e de memória (`project.md`)** simples e versionável — bom contrato para a etapa 6 do plugin (`videos edit --edl`).
4. **Legendas de 2 palavras em maiúsculas com offsets corretos** a partir da transcrição (SRT lateral).

O que **não** acrescentou: motion design (continua sendo HyperFrames/`motion/`), voz, e nada para vídeos 100% sintéticos como o video-01 — lá o HyperFrames já corta no quadro. O ganho real aparece com footage do cliente.

## Limites e pendências

- Sem footage do cliente ainda (clipes do Grok Imagine ausentes): a prova usa o próprio render do video-01 como fonte.
- `transcribe.py` (Scribe) não testado — sem `ELEVENLABS_API_KEY`.
- O recorte perde 1 quadro no fim (fonte termina em 20,0 s; 344 de 345 quadros). Irrelevante no cutdown; para encaixe exato, terminar o trecho 1 quadro antes do fim da fonte.
- Bug do alfa em WebM: vale reportar ao upstream (issue não aberta — ação externa, aguarda aprovação).
- Dois reencodes H.264 (trecho CRF 20 + composição CRF 18) sobre o master do video-01; visualmente ok, mas para entrega premium renderizar a fonte em qualidade maior.
