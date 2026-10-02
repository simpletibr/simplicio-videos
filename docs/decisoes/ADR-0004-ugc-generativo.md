# ADR-0004: trilha UGC generativa fora do render determinístico (CLI só monta o prompt)

- **Status:** aceito. A parte determinística (`simplicio-video ugc list|prompt`) é implementada junto com esta decisão; geração de imagem e de vídeo continua manual, sem código no CLI.
- **Data:** 02/10/2026 (BRT)
- **Relaciona:** [ADR-0001](ADR-0001-visao-plugin.md) (esteira determinística; LLM nunca no caminho do render) · [ADR-0003](ADR-0003-fluxo-100-script.md) (fluxo 100% script, Drive, MCP) · trilha: [ugc/README.md](../../ugc/README.md) · fonte: [docs/recursos.md](../recursos.md)

## Contexto

O Wesley pediu para acrescentar UGC ao simplicio-videos com base em duas fontes coletadas em 02/10/2026: o artigo de @sleepclip "How I Make 100 AI UGC Videos for $0 with Opus 5.5 (Full Course)" (X, 01/10/2026) e o "10 AI UGC CHARACTER PACK" (Notion, mesmo autor). O método tem 7 passos: o LLM escolhe 10 personagens, escreve o prompt de imagem de cada um, escreve 10 roteiros por personagem e converte cada roteiro num prompt do Seedance 2.5; o GPT Image 2.5 gera o elenco (headshot + fullbody); o Seedance 2.5 (Higgsfield) ou o Krea renderiza um clipe de ~7 s por roteiro; o autor posta 2–3 por dia por conta e reaproveita o vencedor em 20 variações. Pelo texto do autor, o jeito normal custaria US$ 1.500–20.000 por 100 vídeos contra centavos de crédito de render; não foi medido aqui.

O encaixe não é óbvio:

- O repo é uma **esteira determinística** ([ADR-0001](ADR-0001-visao-plugin.md)): contrato YAML → HyperFrames, mesma entrada = mesmo MP4 byte a byte, LLM só cria template/padrão novo.
- UGC é **generativo**: a imagem e o vídeo saem de modelos, a mesma entrada pode dar saída diferente, e cada render gasta crédito. Nem a voz do clipe é nossa: o Seedance a gera junto com o vídeo.
- Parte do método é texto repetitivo e sensível a erro: o esqueleto do passo 5 existe, segundo o autor, porque cada trecho evitou um render quebrado (sexto dedo, 2 celulares, fala apressada). Isso é determinístico e vale automatizar.
- O método, aplicado a cliente real, tem risco de publicidade enganosa (depoimento fabricado) e de falso rosto/voz.

## Decisão

1. **Nova pasta de etapa `ugc/`** (README, `pack.json`, `pack.schema.json`, `prompts/`), seguindo a regra "cada coisa na pasta da sua etapa" do [AGENTS.md](../../AGENTS.md).
2. **O gerativo fica fora do `render`.** Os passos 1–5 e 7 são prompts de LLM (conversa com o agente, prompts originais em `ugc/prompts/`); os passos 3 e 6 são geração manual (ChatGPT, Higgsfield, Krea) ou, a pedido do Wesley, pelo MCP do Higgsfield usado pelo agente. Nada disso passa por contrato, template, motion ou `render`.
3. **O CLI só faz a parte determinística:**
   - `simplicio-video ugc list [--json]`: lista os 10 personagens do pack (id, nome, entrega, nº de palavras da fala).
   - `simplicio-video ugc prompt PERSONAGEM --app "NOME" [--fala "texto"] [--duracao 7] [--json]`: monta o prompt Seedance 2.5 do personagem com o esqueleto do artigo, byte a byte, e avisa se a fala foge de ~3,5 palavras por segundo (22–28 palavras para 7 s).
   - `simplicio-video ugc prompt --todos --app "NOME" [--duracao 7] [--json]`: os 10, com as falas de exemplo do pack.
   - Sem LLM, sem rede, sem chave: mesma entrada, mesmo texto.
4. **Fala vem de fato, não do pack.** As falas do pack são exemplos de formato (apps de namoro, treino, diário e finanças). Para cliente real a fala vem de `clients/<slug>/coleta/` e entra por `--fala` (regra "Só fatos reais" do AGENTS.md).
5. **O pack é dado, não código.** Os personagens ficam em `ugc/pack.json` com schema (`simplicio.ugc-pack/v1`); o código lê o arquivo.
6. **Arquivos gerados não entram no git.** Imagens e MP4 ficam em `out/ugc/<slug>/` (gitignored) e a entrega vai para o Drive no padrão do AGENTS.md. O que se versiona é a entrada reprodutível (prompt, fala, fonte da fala), como o WAV da voz no [ADR-0001](ADR-0001-visao-plugin.md), não o resultado.

### Guardrails (obrigatórios na doc e no uso)

- Personagens sintéticos; nunca gerar ou clonar rosto ou voz de pessoa real sem autorização (regra já existente no AGENTS.md).
- Depoimento fabricado ("eu uso há 40 dias", "economizei R$ 400") apresentado como cliente real é publicidade enganosa: a fala vem de fato confirmado em `coleta/` ou é claramente uma encenação; o conteúdo usa o rótulo de IA da plataforma (TikTok, Instagram, YouTube) e respeita o CONAR. Sem contas falsas que simulem pessoas diferentes.
- Segredos (chaves de Higgsfield, Krea, OpenAI) só no ambiente.
- Gerar em plataforma paga só com pedido explícito do Wesley, como o `publish` no Drive.

## Alternativas descartadas

| Opção | Por que não |
|---|---|
| **Renderizar UGC dentro do HyperFrames / `contract.yaml`** | O HyperFrames compõe HTML/GSAP de forma determinística e não gera pessoas. Meter o gerativo no contrato mistura duas garantias (hash byte a byte e "parece gente") e o schema do contrato não tem como representar um clipe de modelo. |
| **Integrar a API do Higgsfield / Krea no CLI agora** | Exige chave e crédito, a saída não é determinística, e preços e limites não foram verificados aqui. Descartado por ora: o agente pode usar o MCP do Higgsfield manualmente, a pedido. Reabrir se houver volume recorrente que justifique a chave e o custo. |
| **Chamar o LLM de dentro do CLI** (elenco, roteiros, esqueleto por API) | O CLI nunca chama LLM ([ADR-0001](ADR-0001-visao-plugin.md)). O agente que roda o CLI já é o LLM; os passos de texto são conversa, com os prompts documentados. |
| **Só documentar, sem CLI** | O passo 5 é texto fixo repetido 10 (ou 100) vezes; um trecho errado quebra o render. Montar e conferir o ritmo da fala por script é barato e determinístico. |
| **Embutir o pack no código Python** | Dado em código exige deploy para mudar; em `ugc/pack.json` com schema qualquer agente lê, valida e estende. |

## Consequências

- A trilha é auditável no texto (prompt, fala, fonte da fala), mas **o resultado visual não é reproduzível**: refazer o mesmo prompt dá outro clipe. Guarde o prompt final, o modelo e a data junto da entrega.
- O aviso de ritmo evita render apressado ou com o personagem encarando a câmera. A taxa de 3,5 palavras por segundo é do artigo (inglês); em pt-BR não foi medida, e o primeiro clipe do passo 6 serve para conferir.
- Para cliente real o fluxo depende de `coleta/`: sem fato confirmado, sem depoimento. O uso do pack com as falas de exemplo fica restrito a teste e demonstração.
- Lacuna conhecida: `simplicio-video publish` exige contrato; o upload de clipes UGC para o Drive é manual por enquanto (mesmas pastas e nomes do AGENTS.md).
- O custo UGC não foi medido. Os números do artigo (US$ 1.500–20.000 contra centavos de crédito; título com US$ 0) são alegação do autor; quando houver um piloto, registrar o medido em [docs/custos.md](../custos.md).
- Os guardrails regulatórios (CDC art. 37, CONAR, rótulos de IA das plataformas) não são parecer jurídico; em dúvida, confirme com o cliente antes de publicar.
