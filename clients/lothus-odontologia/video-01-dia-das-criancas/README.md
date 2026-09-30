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

## Voz

- Provisória: Kokoro `pf_dora` (local). Final: Gemini TTS, voz **Sulafat** (alternativas Laomedeia, Achernar), estilo em `spec.json → voice.providers.file.gemini.style`.
- Gere no AI Studio uma fala por arquivo em `assets/audio/vo/external/line-01.wav … line-04.wav` e rode `npm run voice:file && npm run render` (ou pelo CLI: `simplicio-video voice contract.yaml --provider file`).

## Comandos (projeto npm; o caminho oficial passa a ser o CLI `simplicio-video`)

```bash
npm run check      # build + lint + layout + contraste
npm run render     # out/lothus-dia-criancas.mp4 (−14 LUFS, TP −1,5)
npm run preview && npm run contact
```

QA do render de 30/09/2026: −14,1 LUFS integrado, pico −2,4 dBFS; faster-whisper reconheceu as 4 falas.
