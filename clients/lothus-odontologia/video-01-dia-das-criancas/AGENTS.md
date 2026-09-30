# AGENTS.md — video-01-dia-das-criancas

Regras gerais em [`../../../AGENTS.md`](../../../AGENTS.md). Aqui:
- `spec.json` é a fonte única: `blocks` (parâmetros de cada bloco), `audio` (trilha/cues), `voice` (falas com `max_s`).
- `index.html` é **gerado** por `scripts/build.mjs` a partir de `src/index.template.html` (`{{vars:<id>}}` = `spec.blocks[id]`). Edite o template, nunca o `index.html`.
- `compositions/*.html` são cópias de `motion/patterns/<id>/block.html`; atualize copiando da biblioteca.
- Mudou tempo de cena → mude cues, falas e `roteiro.md` juntos.
