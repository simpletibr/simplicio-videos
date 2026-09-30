# Template: Alimentação (restaurante, delivery, confeitaria, café) (`alimentacao`)

**Status: skeleton** — estrutura proposta, ainda sem vídeo renderizado. O primeiro cliente do setor valida e vira `pronto`.

Nichos que caem aqui: restaurante, lanchonete, hamburgueria, pizzaria, delivery, confeitaria, doceria, café, padaria, marmita.

| Cena | Papel | s | Padrões de motion | Fala (modelo; `{campo}` vem do intake) |
|---|---|---|---|---|
| S1 | gancho | 2.0 | `kinetic-letters-punch` | {desejo/fome} (ex.: 'Bateu a fome?') |
| S2 | produto | 5.0 | `card-3d-pushin-sweep`, `recipe-ingredients-explainer` | {prato/produto carro-chefe} |
| S3 | oferta | 3.0 | `odometer-digit-roll`, `marker-underline-title` | {oferta confirmada, se houver} |
| S4 | processo | 2.0 | `process-timeline` | {como pedir / horário} |
| S5 | cta | 3.0 | `logo-wireframe-shards`, `cta-button-spring` | {cta: peça pelo WhatsApp/app} |

- **Duração:** 15.0 s · 9:16 · 30 fps
- **Voz sugerida:** feminina ou masculina, calorosa (Gemini: `Sulafat`) — estilo: caloroso, apetitoso, sorridente
- **Música:** funk/pop leve, alegre · 100 BPM · intro curta → groove → CTA
- **Tom:** acolhedor, sensorial (sabor, textura), simples
- **Transições:** `circle-iris-transition`

**Cuidados do setor:**
- Foto/vídeo do prato tem que ser do próprio cliente (nada de banco de imagem passando por produto real).
- Não afirmar benefício à saúde ('saudável', 'emagrece') sem base; atenção a alergênicos se citar ingredientes.
- Preço/promoção só com valor e validade confirmados.
