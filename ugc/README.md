# ugc — trilha UGC (gerativa)

Trilha para produzir em volume vídeos curtos no estilo UGC (selfie vertical de ~7 s de uma pessoa falando do app ou produto) com **personagens sintéticos**: um LLM escolhe o elenco, escreve roteiros e prompts; um modelo de imagem cria o elenco; um modelo de vídeo (Seedance 2.5) renderiza os clipes. O método é o do artigo de @sleepclip ([fonte e atribuição](#fonte-e-atribuição)), adaptado a este repositório.

> **Gerativo, fora do `render`.** O resto do repo é uma esteira determinística (mesmo contrato = mesmo MP4). UGC não é: imagem e vídeo saem de modelos e não se reproduzem byte a byte. Por isso esta pasta não usa contrato, template, motion nem `simplicio-video render`, e o CLI só faz a parte determinística (listar o elenco e montar o prompt). Decisão: [ADR-0004](../docs/decisoes/ADR-0004-ugc-generativo.md).

## Onde cabe na esteira

- **Entrada:** fatos do cliente em `clients/<slug>/coleta/` (o que o app faz, público, falas permitidas), do mesmo jeito das etapas 1–2 ([intake](../intake/README.md)). Sem fato confirmado, sem fala.
- **Meio:** esta trilha (passos abaixo). Não passa pelas etapas 3–7 da [esteira](../docs/esteira.md).
- **Saída:** prompts e falas (texto, pode ir ao README do cliente) e os arquivos gerados (imagens, MP4), que **não entram no git** e vão para o Drive ([guardrails](#guardrails)).

## Pipeline (7 passos)

Ferramentas do autor: Opus 5.5 (claude.ai) para o texto, GPT Image 2.5 (chatgpt.com) para as imagens, Seedance 2.5 (Higgsfield, higgsfield.ai) ou Krea (krea.ai) para o vídeo. Os prompts ficam em inglês, como no original.

| Passo | O que | Quem executa | Arquivo de prompt |
|---|---|---|---|
| 1 | Escolher 10 personagens (pessoas que você rolaria na tela do TikTok, não modelos; 1 detalhe físico reconhecível) | LLM | [01-elenco.md](prompts/01-elenco.md) |
| 2 | Transformar cada personagem em prompt de imagem (selfie de iPhone, textura de pele, cabelo bagunçado, cômodo com bagunça) | LLM | [02-prompt-imagem.md](prompts/02-prompt-imagem.md) |
| 3 | Gerar cada prompt 5 vezes e ficar com a que menos parece IA; gerar o fullbody a partir do headshot escolhido. Resultado: 10 personagens x 2 imagens = elenco fixo | manual (ChatGPT) ou MCP | [03-fullbody.md](prompts/03-fullbody.md) (o headshot vem do prompt do passo 2) |
| 4 | 10 roteiros por personagem (7 s, 22–28 palavras) | LLM (mesmo chat do passo 1) | [04-roteiros.md](prompts/04-roteiros.md) |
| 5 | Converter cada roteiro no esqueleto Seedance 2.5 | LLM **ou CLI** (`ugc prompt`) | [05-seedance.md](prompts/05-seedance.md) |
| 6 | Renderizar 1 clipe por personagem, conferir rosto e voz, só então salvar o áudio como referência de voz e renderizar o resto | manual (Higgsfield, Krea) ou MCP | — |
| 7 | Postar 2–3 por dia por conta; o vencedor volta ao LLM para 20 variações | manual + LLM | bloco do passo 7 em [04-roteiros.md](prompts/04-roteiros.md) |

Nos prompts, as quebras de linha dentro dos blocos (inclusive `phone-` / `photo`) vêm da diagramação do X e foram preservadas para fidelidade. Ao usar, junte em parágrafo corrido.

## Regras de qualidade

Todas vêm do artigo; segundo o autor, cada trecho do esqueleto existe porque um render quebrou sem ele.

**Elenco e imagens**
- Personagens, não modelos: gente que se rola na tela, com 1 detalhe físico reconhecível (pinta, cicatriz, sardas, dente separado). A última linha do prompt de elenco evita pele perfeita, que denuncia IA nos comentários.
- Prompt de imagem: selfie de iPhone, textura de pele (poros, brilho, olheiras), cabelo com fios soltos, cômodo com bagunça, luz natural, enquadramento levemente fora do centro.
- Gere cada prompt 5 vezes e fique com a que menos parece IA. Apague na hora: pele de plástico, cabelo sem um fio solto, olhos um pouco grandes demais, fundo limpo de showroom, luz de ring light.

**Fala**
- 7 s = 22–28 palavras (~3,5 palavras por segundo). O Seedance estica a fala para preencher o clipe: 40 palavras em 7 s saem apressadas; 12 palavras deixam o personagem encarando a câmera uns 4 s. O CLI avisa quando a fala foge disso.
- Mix de aberturas: 4 confissões, 4 chamadas, 2 ofertas. Nenhuma pergunta como abertura. Cada roteiro soa como aquela pessoa, com as palavras dela.
- App citado 1 vez, de forma natural, nunca como anúncio.
- A taxa de 3,5 palavras por segundo é do artigo, em inglês. Em pt-BR não foi medida aqui: confira no primeiro clipe do passo 6.

**Esqueleto Seedance** ([05-seedance.md](prompts/05-seedance.md))

| Trecho | Por que está lá |
|---|---|
| `already holding [his/her] phone with [app name] open` | pedir que o modelo pegue o celular gera sexto dedo ou 2 celulares |
| `delivery: [one word]` | 1 palavra (ex.: `tired`) dá performance; pilha de adjetivos deixa o rosto chapado |
| `around second 5 ... glances down at the screen` | olhar para a tela no segundo 5 é o truque de realismo mais barato: ninguém encara a própria câmera por 7 s seguidos |
| `exactly one phone in the entire scene` | o Seedance gosta de pôr um segundo celular numa prateleira atrás |
| specs de câmera por último, sem "iPhone" na descrição da cena | escrever "iPhone" na cena faz o modelo renderizar um iPhone no quadro |

O autor ainda recomenda pedir ao LLM que tudo saia natural: visual, emoções, palavras, estrutura e roteiro.

**Render e distribuição**
- Não renderize tudo de uma vez. 1 clipe por personagem, sozinho: confira se o rosto bate com o headshot e a voz combina com a pessoa. Se algo estiver errado, refaça agora (descobrir no clipe 40 são 39 renders perdidos).
- Com o primeiro clipe certo, salve o áudio e anexe como referência de voz nos outros 9. Renderize o resto sempre com headshot, fullbody e voz anexados.
- Esperado, segundo o autor: ~90% morre sem alcance e se caçam os 3–4 que explodem. O vencedor vira 20 variações (mesmo roteiro, mesmo personagem, mantém o hook, muda os detalhes).

## CLI

```bash
simplicio-video ugc list [--json]
simplicio-video ugc prompt PERSONAGEM --app "NOME" [--fala "texto"] [--duracao 7] [--json]
simplicio-video ugc prompt --todos --app "NOME" [--duracao 7] [--json]
```

- `ugc list` lista os 10 personagens do pack: id, nome, entrega (a palavra de `delivery`) e nº de palavras da fala.
- `ugc prompt` monta o prompt Seedance 2.5 do personagem com o esqueleto do artigo, byte a byte (só os colchetes mudam). Avisa se a fala foge de ~3,5 palavras por segundo (22–28 palavras para 7 s). `PERSONAGEM` é o id do pack (ex.: `casual-dater-guy`); `--duracao` é em segundos (padrão 7); sem `--fala`, usa a fala de exemplo do pack.
- `ugc prompt --todos` gera os 10 com as falas de exemplo do pack.
- Saída: texto para colar no Seedance (Higgsfield ou Krea) junto com headshot, fullbody e, a partir do segundo clipe, a voz de referência. O CLI não chama LLM nem API de geração.

As falas do pack são **exemplos de formato** (apps de namoro, treino, diário e finanças), não fatos de nenhum cliente. Para cliente real, a fala vem de `clients/<slug>/coleta/` e entra por `--fala`:

```bash
simplicio-video ugc list
simplicio-video ugc prompt casual-dater-guy --app "NOME_DO_APP" --fala "<fala confirmada em coleta/>" --duracao 7
```

## Guardrails

1. **Personagens sintéticos.** Nunca gerar ou clonar rosto ou voz de pessoa real sem autorização dela ([AGENTS.md](../AGENTS.md)). Não use foto ou áudio de pessoa real como referência do headshot, do fullbody ou da voz.
2. **Sem depoimento fabricado como se fosse cliente real.** Falas como "eu uso há 40 dias" ou "economizei R$ 400" apresentadas como experiência de cliente são publicidade enganosa (CDC, art. 37; CONAR). A fala precisa vir de fato confirmado em `coleta/` ou ser claramente uma encenação. Isso vale também para as falas de exemplo do pack: não as publique para um cliente real. Não distribua o mesmo conteúdo em contas falsas que simulem pessoas diferentes; publique nas contas do cliente.
3. **Divulgação de IA.** O conteúdo gerado por IA usa o rótulo ou a divulgação de IA da plataforma (TikTok, Instagram, YouTube) e respeita o CONAR (identificação publicitária, testemunhos verdadeiros). Isto não é parecer jurídico: em dúvida, confirme com o cliente.
4. **Arquivos gerados fora do git.** Imagens do elenco e MP4s ficam em `out/ugc/<slug>/` (`out/` é gitignored) e a entrega vai para o Drive como no resto do repo: `simplicio-video/clientes/NOME_CLIENTE/ANO/CAMPANHA`, arquivo `<CLIENTE> - <descricao> - vNN.mp4`, link na tabela **Entregas no Drive** do `clients/<slug>/README.md`. Upload só com pedido explícito; hoje o `publish` exige contrato, então o upload de clipes UGC é manual.
5. **Segredos só no ambiente.** Chaves de Higgsfield, Krea, OpenAI etc. ficam no ambiente ou no `.env` (gitignored), nunca no repo, num prompt ou numa conversa.
6. **Crédito é gasto real.** Gerar imagem ou vídeo em plataforma paga (inclusive pelo MCP do Higgsfield) só com pedido explícito do Wesley.

## O que não está automatizado, de propósito

- **Geração de imagem (passo 3) e de vídeo (passo 6):** exige chave e crédito e a saída não é determinística. O agente pode usar o MCP do Higgsfield manualmente, com o pedido de guardrail 6. Ver [ADR-0004](../docs/decisoes/ADR-0004-ugc-generativo.md).
- **Escolha do headshot** ("seja brutal") e **conferência de rosto e voz** do primeiro clipe: julgamento humano.
- **Passos 1, 2, 4 e 7:** conversa com o LLM; o CLI nunca chama LLM.
- **Upload das referências, postagem e leitura de métricas.**

## Arquivos

| Arquivo | O quê |
|---|---|
| [`pack.json`](pack.json) | `simplicio.ugc-pack/v1`: 10 personagens (`id`, `nome`, `genero`, `local`, `entrega`, `fala`, `reacao`) + fonte. Só texto: as imagens do pack do Notion não foram copiadas; o elenco do cliente nasce nos passos 1–3 |
| [`pack.schema.json`](pack.schema.json) | JSON Schema do pack |
| [`prompts/`](prompts/) | 01-elenco, 02-prompt-imagem, 03-fullbody, 04-roteiros, 05-seedance (prompts originais em inglês, byte a byte) |

## Fonte e atribuição

- **Artigo:** ["How I Make 100 AI UGC Videos for $0 with Opus 5.5 (Full Course)"](https://x.com/sleepclip/status/2105574125745922166), @sleepclip, 01/10/2026. Os prompts de `prompts/` são os dele; este repo resume os passos e linka a fonte.
- **Pack:** [10 AI UGC CHARACTER PACK](https://app.notion.com/p/10-AI-UGC-CHARACTER-PACK-3eaa9e04517680b4a5eacc4c6143cdaf) (Notion, mesmo autor), convertido em `pack.json`. O autor o descreve como "open to use"; o texto coletado não traz licença formal.
- **Coleta:** 02/10/2026 (BRT). Texto do artigo e prompts lidos no dia; podem ter mudado desde então.
- **Números do artigo são alegação do autor, não medidos aqui:** 100 vídeos UGC "do jeito normal" custariam US$ 1.500–20.000 (criador de US$ 15–200 por vídeo) contra centavos de crédito de render, e o título fala em US$ 0. Este repo não mediu custo UGC algum (o que é medido está em [custos](../docs/custos.md)).
- O artigo termina com uma oferta comercial do autor (distribuição por rede de criadores). Não faz parte do método e não é endossada nem verificada aqui.

Curadoria: [docs/recursos.md](../docs/recursos.md).
