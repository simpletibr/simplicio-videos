# Narração externa (provider `file`)

Solte aqui um arquivo por frase de `spec.json → voice.lines`, na ordem:

| Arquivo | Linha | Texto (falar exatamente) | Duração máx. (slot) |
|---|---|---|---|
| `line-01.wav` | vo1 | Seu console parou? | 1,45 s |
| `line-02.wav` | vo2 | A gente coloca ele de volta no jogo. | 2,50 s |
| `line-03.wav` | vo3 | Drift? Superaquecimento? Não liga? | 2,80 s |
| `line-04.wav` | vo4 | Xbox e PlayStation. | 1,75 s |
| `line-05.wav` | vo5 | Limpeza de controle. | 1,75 s |
| `line-06.wav` | vo6 | Metal líquido no PS5. ("PS cinco") | 2,25 s |
| `line-07.wav` | vo7 | Analógico Hall Effect. | 2,00 s |
| `line-08.wav` | vo8 | Você aprova antes do reparo. | 2,05 s |
| `line-09.wav` | vo9 | Chama a WJR no WhatsApp e volte pro jogo! ("dáblio jota erre") | 3,40 s |

WAV/MP3/M4A, qualquer taxa. Depois: `npm run voice && npm run render` (o `spec.json` já usa `provider: "file"`). Atuais: Gemini 3.8 Flash TTS, voz Puck (AI Studio, 30/09/2026) — tutorial em `docs/tutorial-voz-gemini.md`.
Duração máx. = tempo depois do corte de silêncio e com a cauda da sala (~0,1 s a mais que o arquivo aparado).
O script corta silêncio, aplica EQ/compressor/sala, converte para 48 kHz mono e **para com erro** se a frase (sem silêncio) passar do slot — sem acelerar.
Registre modelo/voz/data (ex.: Gemini TTS no AI Studio) em `../../LICENSES.md`.
