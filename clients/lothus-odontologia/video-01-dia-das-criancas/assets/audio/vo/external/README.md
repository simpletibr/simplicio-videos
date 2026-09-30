# Narração final (Gemini TTS) — coloque aqui

Gere no Google AI Studio (Generate speech), modelo Gemini TTS, voz **Sulafat** (alternativas: Laomedeia, Achernar), com a instrução de estilo de `contract.yaml → voz.providers.gemini.estilo`. Uma fala por arquivo, na ordem:

| Arquivo | Fala | Máx. |
|---|---|---|
| `line-01.wav` | Feliz Dia das Crianças! | 2,3 s |
| `line-02.wav` | Hoje é dia de brincar, sorrir e se divertir! | 3,3 s |
| `line-03.wav` | E depois da festa, escova nesses dentinhos! | 3,0 s |
| `line-04.wav` | Com carinho, Lothus Odontologia. (pronúncia "Lótus") | 2,6 s |

Depois: `simplicio-video voice contract.yaml --provider file && simplicio-video render contract.yaml` (a partir desta pasta).
