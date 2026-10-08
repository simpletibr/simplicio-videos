# Questionário de intake

O plugin sempre começa aqui. Resultado: um `intake.json` ([`intake.schema.json`](intake.schema.json)) que vira o brief/spec. Exemplo real: `exemplos/wjr-informatica-games.intake.json`.

**Primeira pergunta (decide o modo):**

> "Tem site ou Instagram da empresa? Pode mandar os dois."

- **Tem site e/ou Instagram → modo `auto`:** roda a [extração automática](extracao-automatica.md), mostra um resumo do que achou ("Encontrei: nome, nicho, 6 serviços, WhatsApp, endereço, logo e cores — confere?") e pergunta **só o que falta** (bloco B) + o que ficou marcado `inferido`.
- **Não tem → modo `completo`:** blocos A + B.

Regras de conversa: uma pergunta por vez (no máximo 3 agrupadas quando são curtas), sempre com um padrão sugerido ("Se não tiver preferência, uso 9:16 com 20 s"), e nunca preencher fato do cliente sem fonte — o que ficar sem resposta vai para `pendencias`.

## Bloco A — a empresa (só no modo `completo`, ou o que a extração não achou)

| # | Pergunta | Campo | Obrigatório |
|---|---|---|---|
| A1 | Qual o nome da empresa (como deve aparecer no vídeo)? | `empresa.nome` | sim |
| A2 | Em uma frase: o que vocês fazem e para quem? | `empresa.descricao`, `empresa.nicho` → `setor_template` | sim |
| A3 | Quais serviços/produtos principais entram no vídeo? (até 5) | `empresa.servicos[]` | sim |
| A4 | Tem alguma oferta/promoção para citar? Com preço/prazo/validade? | `empresa.ofertas[]` | não |
| A5 | O que diferencia vocês? (só o que puderem sustentar) | `empresa.diferenciais[]` | não |
| A6 | Contatos que podem aparecer: WhatsApp, telefone, endereço, Instagram, site, horário | `empresa.contatos` | pelo menos 1 |
| A7 | Manda o logo (PNG/SVG, de preferência fundo transparente) | `marca.logo` | sim |
| A8 | Cores da marca? (ou "usa as do logo") | `marca.cores` | não (extrai do logo) |
| A9 | Como a marca fala? (ex.: descontraída, séria, técnica, acolhedora) | `marca.tom` | não (sugerir pelo nicho) |
| A10 | Posso usar logo, fotos e marca nos vídeos? | `marca.uso_de_imagem_aprovado` | sim |

## Bloco B — o vídeo (sempre)

| # | Pergunta | Campo | Padrão sugerido |
|---|---|---|---|
| B1 | Qual o objetivo? (mais contatos no WhatsApp, divulgar serviço, institucional, evento…) | `pedido.objetivo` | gerar contatos |
| B2 | Onde vai postar? | `pedido.formato.plataformas` | Instagram Reels |
| B3 | Formato | `pedido.formato.aspect` | 9:16 |
| B4 | Duração | `pedido.duracao_s` | 20 s (Reels 15–30 s) |
| B5 | Quer narração? | `pedido.voz.usar` | sim |
| B6 | Se sim: qual voz? **Gemini** (padrão; Google AI Studio ou API), **ElevenLabs**, **xAI**, **local** (Chatterbox/Kokoro, grátis, offline) ou outra | `pedido.voz.provider` | gemini — ver [`voices/`](../voices/README.md) |
| B7 | Tipo de voz: masculina/feminina, idade, energia, sotaque | `pedido.voz.tipo`, `voz_id` | masculina jovem animada (Gemini `Puck`) |
| B8 | Música: animada, calma, sem música? | `pedido.musica` | conforme o template do setor |
| B9 | Legenda queimada no vídeo? | `pedido.legendas` | sim quando houver narração |
| B10 | Tem vídeo de referência que você gosta? (link) | `pedido.referencias[]` | — (usamos só a estrutura, nunca o material) |
| B11 | Qual é a chamada final? (uma ação só) | `pedido.cta` | "Chama no WhatsApp" |
| B12 | Tem algo que NÃO pode aparecer/ser dito? | `pedido.evitar[]` | preço/prazo/garantia sem confirmação |
| B13 | Tem vídeos/fotos próprios (loja, equipe, produto)? | `pedido.material_proprio[]` | — (ativa video-use + slots de clipe) |

## Fechamento

1. Mostrar o brief em 5–8 linhas (empresa, objetivo, formato/duração, voz, CTA, cenas previstas pelo template) e pedir **"pode seguir?"**.
2. Aprovado → `intake.json` salvo em `clients/<slug>/coleta/intake.json`, fatos copiados para `brief.md`/`fontes.md` (com data), pendências em `pendencias.md`.
3. Só então: spec → template → composição → voz → render (ver [`docs/esteira.md`](../docs/esteira.md)).
