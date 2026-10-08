---
title: Duas rotas de produção (determinística e ai_assisted)
summary: As duas rotas do item lado a lado, o que é reproduzível byte a byte, onde mora cada decisão e os comandos reais de cada etapa.
commands: simplicio-video make, simplicio-video make preview, simplicio-video draft show, simplicio-video generate quote, simplicio-video generate approve, simplicio-video generate start, simplicio-video generate show, simplicio-video media attach, simplicio-video board list, simplicio-video board comment, simplicio-video board review, simplicio-video board build
issue: 90
last_verified: 2026-10-08
---

# Duas rotas de produção

Um item segue uma de duas rotas, dada por `production.route` ([ADR-0008](../decisoes/ADR-0008-duas-rotas.md)). A rota `deterministic` é o padrão e não usa modelo. A rota `ai_assisted` gera o vídeo com IA no Real Oficial, e só gasta créditos depois que uma pessoa aprova o orçamento.

## Comandos por etapa

| Rota | Etapa | Comando |
|---|---|---|
| deterministic | importa o Draft e roda até `rendered` | `simplicio-video make --from draft.json` |
| deterministic | prévia 540x960 com marca d'água | `simplicio-video make preview ITEM` |
| ai_assisted | cota o custo (`drafted` para `quoted`) | `simplicio-video generate quote ITEM --provider real-oficial --estimate-ref REF --credits N` |
| ai_assisted | aprova o gasto (`quoted` para `approved`) | `simplicio-video generate approve ITEM --by NOME` |
| ai_assisted | inicia a geração (`approved` para `generating`) | `simplicio-video generate start ITEM` |
| ai_assisted | mostra o passo, o custo e quem aprovou | `simplicio-video generate show ITEM` |
| ai_assisted | anexa o MP4 com recibo (`generating` para `generated`) | `simplicio-video media attach ITEM ARQUIVO --source real-oficial --media-id ID --prompt-file ARQ` |
| ambas | renderiza o item até `rendered` | `simplicio-video make ITEM` |
| ambas | quadro e revisão | `simplicio-video board list`, `simplicio-video board comment ITEM "texto" --by NOME`, `simplicio-video board review ITEM approve --by NOME`, `simplicio-video board build --out board.html` |
