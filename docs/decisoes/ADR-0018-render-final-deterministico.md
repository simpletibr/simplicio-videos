# ADR-0018: render final determinístico também na rota ai_assisted (a mídia gerada entra como asset verificado)

- **Status:** aceito. Implementado pelo studio (#16), pelo `media attach` (#87) e pelo teste de fluxo da issue #90, dentro do épico #81.
- **Data:** 08/10/2026 (BRT)
- **Relaciona:** [docs/host/duas-rotas.md](../host/duas-rotas.md) (como usar) · [ADR-0008](ADR-0008-duas-rotas.md) (duas rotas no item) · [ADR-0001](ADR-0001-visao-plugin.md) (LLM nunca no caminho do render) · [ADR-0004](ADR-0004-ugc-generativo.md) (trilha generativa fora do render determinístico) · épico #81

## Contexto

A rota `ai_assisted` põe no item um vídeo gerado por IA, comprado no Real Oficial. Esse arquivo tem duas propriedades que a rota determinística não tem: cada geração gasta créditos, e o mesmo prompt não gera o mesmo arquivo. Se o produto passasse a entregar o MP4 gerado como está, o controle de marca, formato e loudness ficaria no serviço externo, e a revisão de um item não poderia ser repetida.

Ao mesmo tempo, a rota determinística já tem um render final que é reproduzível: o composer monta o contrato sem relógio, aleatoriedade ou rede, e o motor renderiza o mesmo contrato para o mesmo resultado. O studio também grava o `content_hash`, que identifica as entradas do render. O que falta é decidir se a rota generativa usa esse mesmo render final ou outro caminho.

## Decisão

1. **O render final da rota ai_assisted é o mesmo da rota determinística.** O item passa pelo estágio studio (composer, motor e `content_hash`), sem caminho próprio. A mídia gerada entra como asset do contrato, e nada além disso muda na composição.
2. **A mídia gerada entra como arquivo verificado.** `media attach` copia o arquivo para a pasta do item e grava o recibo com o sha256. Antes de cada render, o studio confere esse sha256 e recusa a cópia se o arquivo mudou.
3. **Nenhum modelo entra na composição nem no render.** O composer não chama LLM nem serviço de geração, e o render do studio só chama TTS se a voz estiver habilitada, o que é desligado por padrão (`voz.habilitada: false`). A geração acontece antes, no Real Oficial, e o resultado chega ao item só como arquivo anexado.
4. **O MP4 gerado não é entrega.** A saída do item é o MP4 do render final, com marca, formato e loudness do studio. O arquivo bruto do Real Oficial fica na pasta do item como insumo.

## Consequências

- O que é reproduzível é o render final a partir da mídia anexada: o mesmo Draft, a mesma marca e o mesmo arquivo dão o mesmo `content_hash`. A geração em si não é reproduzível, e isso fica explícito no doc da rota.
- Trocar a mídia de um item pede outro item, porque nesta versão não há reanexo. Isso mantém o recibo e o `content_hash` de cada item apontando para um único arquivo.
- O render final continua sem legendas, porque o template `brand-promo` não tem legenda. Se a legenda entrar no template, ela entra nas duas rotas, e o `content_hash` muda para as duas.
- O teste de fluxo da issue #90 prova o caminho completo com o StubRenderer: a geração é simulada por um arquivo falso e o render é trocado. O render real com o motor continua coberto pelos testes de determinismo do motor.

## Alternativas descartadas

- **Entregar o MP4 gerado direto, sem render final.** Perde a marca, o formato e o loudness do studio, e a entrega deixaria de depender da mesma revisão das duas rotas.
- **Renderizar o final no Real Oficial.** Cada render gastaria créditos, e o controle de marca e de hash ficaria no serviço externo.
- **Deixar um modelo montar o contrato da rota generativa.** Viola o ADR-0001: o LLM não entra no caminho do render, e a composição passaria a não ser reproduzível.
- **Reproduzir a geração com semente.** Os provedores não garantem bytes iguais entre gerações, e cada tentativa custaria créditos. O que se fixa é o arquivo, pelo sha256 no recibo.
