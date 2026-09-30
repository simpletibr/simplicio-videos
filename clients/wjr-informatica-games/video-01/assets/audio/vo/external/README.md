# Narração externa (provider `file`)

Solte aqui um arquivo por frase de `spec.json → voice.lines`, na ordem:

| Arquivo | Linha | Texto (falar exatamente) | Duração máx. (slot) |
|---|---|---|---|
| `line-01.wav` | vo1 | Seu console parou? | 1,80 s |
| `line-02.wav` | vo2 | A gente coloca ele de volta no jogo. | 1,95 s |
| `line-03.wav` | vo3 | Drift? Superaquecimento? Não liga? | 2,55 s |
| `line-04.wav` | vo4 | Xbox e PlayStation. | 1,90 s |
| `line-05.wav` | vo5 | Limpeza de controle. | 1,45 s |
| `line-06.wav` | vo6 | Metal líquido no PS5. ("PS cinco") | 1,95 s |
| `line-07.wav` | vo7 | Analógico Hall Effect. | 1,95 s |
| `line-08.wav` | vo8 | Você aprova antes do reparo. | 1,90 s |
| `line-09.wav` | vo9 | Chama a WJR no WhatsApp e volte pro jogo! ("dáblio jota erre") | 3,60 s |

WAV/MP3/M4A, qualquer taxa. Depois: `VOICE_PROVIDER=file npm run voice && npm run render`.
O script corta silêncio, aplica EQ/compressor/sala, converte para 48 kHz mono e **para com erro** se a frase (sem silêncio) passar do slot — sem acelerar.
Registre modelo/voz/data (ex.: Gemini TTS no AI Studio) em `../../LICENSES.md`.
