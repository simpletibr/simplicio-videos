# video-01-dia-das-criancas — Lothus Odontologia

Post 9:16, 1080×1920, 30 fps, 15 s, para o Dia das Crianças (12/10/2026). Referência do template [`saude-odontologia`](../../../templates/saude-odontologia/). Roteiro: [`roteiro.md`](roteiro.md) · fatos: [`../coleta/`](../coleta/) · licenças: [`assets/audio/LICENSES.md`](assets/audio/LICENSES.md).

## Por que estes blocos

| Cena | Blocos (`motion/patterns/`) | Motivo |
|---|---|---|
| S1 | `balloons-confetti` + `kinetic-bounce-title` | Balões dão a data na hora; letras saltando na paleta infantil seguram a leitura no 9:16 |
| S2 | `tooth-character` + título | Mascote-dente acena ("Oi!"): traz o assunto odonto sem fotos do cliente nem crianças reais |
| S3 | `toothbrush-sparkle` + título | Dica de cuidado genérica (escovar), sem promessa clínica (CFO) |
| S4 | `brand-lockup-soft` + confete | Lockup de texto: **não** recriamos o logo (só existe avatar 100×100); o slot de logo fica vazio até chegar arquivo em alta |

Gramática de motion do [motion-video-kit](https://github.com/echris6/motion-video-kit): o primeiro plano vira a transição (discos coloridos em 3,5/7,5/11 s), cada cena com um único foco e sem tempo congelado. Receitas de ritmo (entradas em escada, 1 ideia por cena) do video-shotcraft / awesome-opus5-5-videos.

Fica **fora** do vídeo: telefone e endereço (fontes divergem), nota/avaliações, Invisalign, nome/CRO da dentista.

## Como é gerado (só pelo CLI)

Este vídeo não tem projeto npm: a fonte única é [`contract.yaml`](contract.yaml) (`simplicio.video-contract/v1`). O CLI compila o contrato com a composição do template ([`templates/saude-odontologia/composition/`](../../../templates/saude-odontologia/composition/)) e os blocos de `motion/patterns/`.

```bash
cd clients/lothus-odontologia/video-01-dia-das-criancas
simplicio-video validate contract.yaml
simplicio-video voice contract.yaml              # provisória: local (Kokoro pf_dora) -> assets/audio/voz/ + timing.lock.json
simplicio-video render contract.yaml             # -> out/lothus-dia-criancas.mp4 + render.manifest.json
```

| Arquivo | O quê |
|---|---|
| `contract.yaml` | cenas, blocos + params, falas (texto, início relativo à cena, `max_s`), SFX, voz, trilha, saída, destino no Drive |
| `timing.lock.json` | duração real de cada fala (gerado por `voice`) |
| `render.manifest.json` | hashes do contrato, dos inputs compilados, do vídeo/áudio decodificados, loudness e tempos |
| `assets/audio/voz/` | falas tratadas (cache versionado) |
| `assets/audio/vo/external/` | onde entram os WAVs do Gemini (ver README da pasta) |
| `preview/` | prévia 720p + contact sheet |

## Voz final (Gemini)

- Voz **Sulafat** (alternativas Laomedeia, Achernar); estilo em `contract.yaml → voz.providers.gemini.estilo`.
- Gere no AI Studio uma fala por arquivo em `assets/audio/vo/external/line-01.wav … line-04.wav` ([instruções](assets/audio/vo/external/README.md)) e rode:
  `simplicio-video voice contract.yaml --provider file && simplicio-video render contract.yaml` (ou mude `voz.provider` para `file` no contrato).
- Com `GEMINI_API_KEY`: `simplicio-video voice contract.yaml --provider gemini` (não testado aqui, sem chave).

## Entrega

Drive: `simplicio-video/clientes/Lothus_Odontologia/2026/Dia_Criancas` → `Lothus - Dia das Criancas 15s - v01.mp4` (link na tabela do [README do cliente](../README.md)).

QA do render de 30/09/2026 (CLI, voz provisória): −14,1 LUFS integrado, pico −2,4 dBFS; faster-whisper reconheceu as 4 falas; frames e áudio idênticos ao render anterior pelo projeto npm (mesmo sha256 do MP4).
