# Narração (Gemini TTS) — coloque aqui

Gere no Google AI Studio (Generate speech), modelo Gemini 3.8 Flash TTS, voz **Laomedeia** (Sulafat estava indisponível em 30/09/2026; alternativa: Achernar), com estilo **bem animado** (festa infantil, sorrindo, energia alta, sem gritar). Uma fala por arquivo, na ordem:

| Arquivo | Fala | Máx. (v02, 128 BPM) |
|---|---|---|
| `line-01.wav` | Feliz Dia das Crianças! | 2,5 s |
| `line-02.wav` | Hoje é dia de brincar, sorrir e se divertir! | 4,1 s |
| `line-03.wav` | E depois da festa, escova nesses dentinhos! | 4,5 s |
| `line-04.wav` | Com carinho, Lothus Odontologia. (texto enviado: "Lótus") | 3,5 s |

Máximos medidos depois do corte de silêncio. Arquivos atuais: leva animada de 30/09/2026 (`lothus-animado-01..04.wav`). Se uma leva nova passar do máximo, ajuste `cenas[].duracao_s` no contrato em batidas inteiras (60/128 s); nunca acelere a voz.

Depois: `simplicio-video voice contract.yaml && simplicio-video render contract.yaml` (a partir da pasta do vídeo). O `voice` também grava os tempos de cada palavra no `timing.lock.json` (usados pela tipografia palavra a palavra).
