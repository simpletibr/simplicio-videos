# Template: Varejo (loja física/online, moda, material, eletro) (`varejo`)

**Status: skeleton** — estrutura proposta, ainda sem vídeo renderizado. O primeiro cliente do setor valida e vira `pronto`.

Nichos que caem aqui: loja, varejo, moda, roupas, calçados, material de construção, papelaria, eletrodomésticos, e-commerce, mercado.

| Cena | Papel | s | Padrões de motion | Fala (modelo; `{campo}` vem do intake) |
|---|---|---|---|---|
| S1 | gancho | 2.0 | `kinetic-letters-punch` | {oferta/novidade} |
| S2 | produto | 5.0 | `beat-cut-accelerate`, `card-3d-pushin-sweep` | {produtos/categorias} |
| S3 | oferta | 3.0 | `odometer-digit-roll`, `cliptitle-chip-cascade` | {condição confirmada} |
| S4 | processo | 2.0 | `spending-simulation-9x16`, `process-timeline` | {como comprar / entrega} |
| S5 | cta | 3.0 | `logo-drop-shockwave`, `cta-button-spring` | {cta: venha/peça agora} |

- **Duração:** 15.0 s · 9:16 · 30 fps
- **Voz sugerida:** animada, próxima (Gemini: `Fenrir`) — estilo: empolgado, varejo, chamada de oferta
- **Música:** pop/house animado · 124 BPM · intro → groove → build → drop no CTA
- **Tom:** energético, direto, oferta clara
- **Transições:** `transition-glitch-rgb`

**Cuidados do setor:**
- Preço/condição com validade e regras (CDC: oferta anunciada obriga o fornecedor).
- Produto mostrado = produto vendido (fotos do cliente).
- Estoque limitado/urgência só se for verdade.
