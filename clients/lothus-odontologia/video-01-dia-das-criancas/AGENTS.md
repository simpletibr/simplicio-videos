# AGENTS.md — video-01-dia-das-criancas

Regras gerais em [`../../../AGENTS.md`](../../../AGENTS.md). Aqui:
- Fonte única: `contract.yaml`. Não há `index.html`/`spec.json` versionados: o CLI gera tudo em `build/simplicio-video/` (gitignored).
- Mudou texto de fala → `simplicio-video voice contract.yaml` (regrava `timing.lock.json`) → `render`.
- Mudou duração de cena → ajuste falas (`inicio_s`/`max_s`) e SFX (tempos relativos à cena) no mesmo contrato e o `roteiro.md`.
- Composição e blocos: `templates/saude-odontologia/composition/` e `motion/patterns/`; nunca edite cópias geradas.
