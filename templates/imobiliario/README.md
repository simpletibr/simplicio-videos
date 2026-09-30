# Template: Imobiliário (imobiliária, corretor, construtora, aluguel) (`imobiliario`)

**Status: skeleton** — estrutura proposta, ainda sem vídeo renderizado. O primeiro cliente do setor valida e vira `pronto`.

Nichos que caem aqui: imobiliária, corretor, imóveis, construtora, incorporadora, aluguel, lançamento imobiliário, condomínio.

| Cena | Papel | s | Padrões de motion | Fala (modelo; `{campo}` vem do intake) |
|---|---|---|---|---|
| S1 | gancho | 2.5 | `marker-underline-title` | {desejo: o lugar certo} |
| S2 | ambiente | 7.0 | `spotlight-sweep`, `card-3d-pushin-sweep`, `hud-scan-photo` | {ambientes do imóvel (fotos/vídeos reais)} |
| S3 | prova | 3.5 | `cliptitle-chip-cascade` | {características confirmadas: quartos, m², bairro} |
| S4 | processo | 3.0 | `process-timeline` | {como visitar/financiar} |
| S5 | cta | 4.0 | `logo-shrink-lockup`, `cta-button-spring` | {cta: agende sua visita} |

- **Duração:** 20.0 s · 9:16 · 30 fps
- **Voz sugerida:** madura, confiável (Gemini: `Gacrux`) — estilo: calmo, sofisticado, seguro
- **Música:** cinemático/ambiente elegante · 90 BPM · contínua com leve crescendo no CTA
- **Tom:** sofisticado, confiável, aspiracional sem exagero
- **Transições:** `circle-iris-transition`

**Cuidados do setor:**
- Número do CRECI do corretor/imobiliária no anúncio (exigência do sistema COFECI/CRECI — confirmar a regra vigente).
- Metragem, preço, condições e prazos de entrega só como constam no material oficial do empreendimento.
- Imagens ilustrativas/renderizações marcadas como tal.
