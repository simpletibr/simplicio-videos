# Template: Saúde e clínicas (odonto, fisioterapia, psicologia, clínica médica, pet) (`saude-clinica`)

**Status: skeleton** — estrutura proposta, ainda sem vídeo renderizado. O primeiro cliente do setor valida e vira `pronto`.

Nichos que caem aqui: clínica, consultório, dentista, odontologia, fisioterapia, psicologia, nutrição, médico, veterinária, pet.

| Cena | Papel | s | Padrões de motion | Fala (modelo; `{campo}` vem do intake) |
|---|---|---|---|---|
| S1 | gancho | 2.5 | `marker-underline-title` | {situação do paciente, sem alarmismo} |
| S2 | promessa | 3.0 | `word-mask-highlight` | {como a clínica ajuda} |
| S3 | servicos | 6.0 | `service-panels-slide` | {especialidades} |
| S4 | ambiente | 3.0 | `card-3d-pushin-sweep`, `spotlight-sweep` | {estrutura/equipe (fotos reais)} |
| S5 | processo | 2.5 | `process-timeline` | {como agendar} |
| S6 | cta | 3.0 | `logo-wireframe-shards`, `cta-button-spring` | {cta: agende sua avaliação} |

- **Duração:** 20.0 s · 9:16 · 30 fps
- **Voz sugerida:** calma, clara, confiável (Gemini: `Achird`) — estilo: tranquilo, acolhedor, sem pressa
- **Música:** piano/ambiente leve · 85 BPM · contínua, sem drop
- **Tom:** sereno, informativo, humano; nada de sensacionalismo
- **Transições:** `circle-iris-transition`

**Cuidados do setor:**
- Publicidade de saúde segue o conselho profissional de cada área (medicina, odontologia, psicologia, fisioterapia, nutrição, veterinária) — confirmar as regras vigentes antes de publicar.
- Sem promessa de cura/resultado, sem preço como chamariz, sem depoimento/antes-depois sem checar a norma do conselho.
- Mostrar nome e registro profissional do responsável quando exigido.
- Evitar glitch/cortes agressivos.
