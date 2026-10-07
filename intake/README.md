# intake/ — questionário e extração automática

Primeiro passo da esteira: entender o cliente e o pedido **antes** de qualquer animação.

| Arquivo | O quê |
|---|---|
| [`questionario.md`](questionario.md) | Perguntas, ordem e padrões sugeridos — modo `auto` (com site/Instagram: pergunta só o que falta) e `completo` |
| [`extracao-automatica.md`](extracao-automatica.md) | Regras para extrair nicho, empresa, serviços, logo, cores e tom do site/Instagram, com fonte e data em cada fato |
| [`intake.schema.json`](intake.schema.json) | Formato `simplicio.intake/v1` do resultado (cada fato com proveniência) |

Saída: `clients/<slug>/coleta/intake.json` → brief/spec do vídeo (ver [`docs/esteira.md`](../docs/esteira.md)).
