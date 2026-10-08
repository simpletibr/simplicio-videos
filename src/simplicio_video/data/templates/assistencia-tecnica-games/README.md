# Template: Assistência técnica / games (`assistencia-tecnica-games`)

**Status: pronto** — tem vídeo de referência renderizado.

Referência: [`clients/wjr-informatica-games/video-01`](../../../../../clients/wjr-informatica-games/video-01/)

Nichos que caem aqui: assistência técnica, conserto de console, conserto de controle, games, videogame, celular, informática, eletrônicos.

| Cena | Papel | s | Padrões de motion | Fala (modelo; `{campo}` vem do intake) |
|---|---|---|---|---|
| S1 | gancho | 1.5 | `kinetic-letters-punch`, `bg-grid-glow-particles` | {pergunta de dor}? (ex.: 'Seu console parou?') |
| S2 | promessa | 2.5 | `card-3d-pushin-sweep`, `word-mask-highlight` | {promessa com trecho destacado} |
| S3 | problemas | 2.75 | `item-relay-counter`, `reactive-icon-controller` | {problema 1}. {problema 2}. {problema 3}? |
| S4 | prova | 1.75 | `hud-scan-photo`, `cliptitle-chip-cascade` | {linhas/marcas atendidas} |
| SV | servicos | 6.0 | `service-panels-slide`, `service-illustrations-wjr` | {serviço 1}. {serviço 2}. {serviço 3}. |
| S5 | processo | 2.0 | `process-timeline` | {diferencial de processo} (ex.: 'Você aprova antes do reparo.') |
| S6 | cta | 3.5 | `logo-drop-shockwave`, `cta-button-spring` | {cta com o canal} |

- **Duração:** 20.0 s · 9:16 · 30 fps
- **Voz sugerida:** masculina jovem, animada (Gemini: `Puck`) — estilo: locutor de propaganda de loja de games, animado, natural, ritmo ágil sem correr
- **Música:** eletrônica energética, sidechain · 120 BPM · intro → groove → build 1 s antes do CTA → drop no CTA
- **Tom:** direto, informal-confiante, vocabulário do público (gamer), promessas moderadas
- **Transições:** `transition-glitch-rgb`

**Cuidados do setor:**
- Não citar preço, prazo, garantia ou avaliações sem confirmação registrada.
- Não prometer resultado absoluto ('fim do drift'); o próprio site da WJR diz que o serviço depende da avaliação técnica.
- Marcas (Xbox, PlayStation) só como compatibilidade, sem logotipos oficiais.

Como instanciar hoje: copiar a referência (`cp -r clients/wjr-informatica-games/video-01 clients/<novo>/video-01`), trocar `spec.json` com os fatos do intake e seguir `docs/esteira.md`. O gerador automático intake → spec é o próximo passo (ver `docs/esteira.md`, status).
