# templates/ — um template por setor

Um template transforma um intake aprovado em spec **sem LLM**: define a sequência de cenas (papel + duração), os padrões de `motion/` de cada cena, os campos do intake que alimentam cada uma, voz/música sugeridas e os cuidados do setor. Formato: [`template.schema.json`](template.schema.json) (`simplicio.video-template/v1`).

| Template | Setor | Status | Duração | Referência |
|---|---|---|---|---|
| [`assistencia-tecnica-games`](assistencia-tecnica-games/) | Assistência técnica / games / eletrônicos | **pronto** | 20 s | `clients/wjr-informatica-games/video-01` |
| [`alimentacao`](alimentacao/) | Restaurante, delivery, confeitaria, café | skeleton | 15 s | — |
| [`beleza-estetica`](beleza-estetica/) | Salão, barbearia, estética | skeleton | 15 s | — |
| [`saude-clinica`](saude-clinica/) | Odonto, fisio, psicologia, clínica, pet | skeleton | 20 s | — |
| [`saas-tech`](saas-tech/) | SaaS, apps, tecnologia | skeleton | 20 s | — |
| [`varejo`](varejo/) | Loja física/online, moda, material | skeleton | 15 s | — |
| [`imobiliario`](imobiliario/) | Imobiliária, corretor, construtora | skeleton | 20 s | — |

**skeleton** = estrutura proposta (cenas, padrões, voz, cuidados), sem vídeo renderizado; o primeiro cliente do setor valida e o template vira **pronto** apontando para o projeto de referência.

## Como o template é escolhido

1. Intake → `empresa.nicho` + `descricao` (ver [`intake/`](../intake/README.md)).
2. Compara com a lista `nichos` de cada `template.json`; empate ou nenhum → pergunta ao usuário com as 2 opções mais próximas.
3. Grava em `intake.empresa.setor_template`.

## Regras

- Padrões citados em `cenas[].padroes` têm que existir em `motion/patterns/` (status `pronto` para renderizar; `proposto` indica o que falta construir para o setor).
- As falas são **modelos**: `{campo}` vem do intake; frase sem fato confirmado não entra.
- A soma de `cenas[].dur_s` = `duracao_s`; os tempos finais são ajustados pela duração real da narração (RETIME, `motion/lib/retime.js`).
- Novo setor ou novo template = trabalho de autoria (Opus 5.5 / humano), nunca no caminho do render.
