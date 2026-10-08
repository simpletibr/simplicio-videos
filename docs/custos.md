# Custos por vídeo: voz, render e entrega

- **Data do estudo:** 30/09/2026 (BRT). Preços conferidos nesse dia. Refaça a conta quando mudar o preço ou o câmbio.
- **Decisão (Wesley, 30/09/2026):** o render **local** é o padrão. Colab e Kaggle são backends **opcionais**, usados para clientes via créditos. Ver [ADR-0003](decisoes/ADR-0003-fluxo-100-script.md) e o design de créditos no [ADR-0002](decisoes/ADR-0002-cli-contrato-colab-creditos.md).
- **Legenda:** **[medido]** = número real de uma execução. **[oficial]** = preço publicado pelo fornecedor, com link. **[estimativa]** = conta nossa, com a premissa escrita ao lado.

## Câmbio e preços de referência

| Item | Valor | Fonte |
|---|---|---|
| USD → BRL | **R$ 5,1809** (PTAX venda, 30/09/2026, boletim das 13h11) **[oficial]** | Banco Central, API PTAX: `olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/odata/CotacaoDolarDia(dataCotacao=@dataCotacao)?@dataCotacao='09-30-2026'` |
| Colab Pay As You Go | **US$ 9,99 por 100 unidades** (US$ 49,99 por 500), ou seja, **US$ 0,0999/unidade** **[oficial]** | [colab.research.google.com/signup](https://colab.research.google.com/signup), lida em 30/09/2026 (`formattedCCU100Price="$9.99"`, `formattedCCU500Price="$49.99"`) |
| Gemini 3.8 Flash TTS (Standard, tier pago) | entrada de texto **US$ 0,50/1M tokens**; saída de áudio **US$ 9,00/1M tokens** (= US$ 0,00225 por 10 s) até 31/12/2026. A partir de 01/01/2027: US$ 1,00 e US$ 18,00. Batch/Flex: metade **[oficial]** | [ai.google.dev/gemini-api/docs/pricing](https://ai.google.dev/gemini-api/docs/pricing) ("Last updated 2026-09-24") |
| Tokens de áudio | **25 tokens por segundo** de áudio **[oficial]** (a página usa essa taxa; US$ 9/1M × 25 × 10 s = US$ 0,00225) | mesma página |
| Modal (CPU) | **US$ 0,0000131 por núcleo físico por s** (1 núcleo = 2 vCPU) + **US$ 0,00000222 por GiB por s**. O plano Starter inclui US$ 30/mês de compute grátis. A página também cita "1.15 - 1.75x base prices" para algumas opções (ex.: escolha de região) **[oficial]** | [modal.com/pricing](https://modal.com/pricing), lida em 30/09/2026 |
| RunPod | a página de preços só lista GPUs (ex.: A100 PCIe US$ 1,19–1,59/h, atualizada em 27/09/2026). Não há preço de pod só CPU publicado nela, então não entra nas contas **[oficial]** | [runpod.io/pricing](https://www.runpod.io/pricing) |
| Kaggle | grátis. Cota de GPU semanal (~30 h, varia). Sessão T4 x2 com 4 núcleos e 29 GB; sessão só CPU com 4 núcleos e 30 GB **[oficial]** | [kaggle.com/docs/notebooks](https://www.kaggle.com/docs/notebooks) |

Os valores em R$ não incluem IOF nem spread do cartão internacional. Os preços do Colab foram lidos de uma máquina fora do Brasil (a página mostrou US$); logado numa conta brasileira, o Google pode mostrar outro valor ou moeda. Confira em colab.research.google.com/signup.

## 1. Render medido (WJR: 20 s, 600 frames, qualidade `delivery`)

| Backend | Máquina | Setup | Render (`hyperframes render`) | Master | Total | Custo |
|---|---|---|---|---|---|---|
| **local (padrão)** | box, 8 núcleos, 15 GB | — | **76,5 s** **[medido]** | 2,1 s **[medido]** | ~87 s com o build de 8,6 s **[medido]** | **US$ 0** (sem custo marginal; energia e amortização do box não são medidas) |
| Colab T4 grátis | 2 vCPU, ~12,7 GB | 31,6 s **[medido]** | **459,7 s** **[medido]** | 7,1 s **[medido]** | **~1198 s** (inclui upload e passos manuais) **[medido]** | **US$ 0** (cota grátis, limites dinâmicos) |
| Colab A100 High-RAM (Pay As You Go) | 12 vCPU, 167 GiB | 29,1 s **[medido]** | **107,3 s** **[medido]** | 3,3 s **[medido]** | **248 s** **[medido]** | **0,43 unidade** (saldo 209,13 → 208,70) **[medido]** × US$ 0,0999 = **US$ 0,0430 = R$ 0,22** |
| Kaggle T4 x2 (`--backend kaggle`) | 4 núcleos, 29 GB | não medido | não medido: ~200 s **[estimativa: 2 workers contra 1 no Colab grátis]** | — | — | **US$ 0** (consome ~5 min da cota semanal de GPU). `--accelerator none` (só CPU, 4 núcleos) não usa a cota de GPU |
| Modal só CPU (container) | 4 núcleos físicos = 8 vCPU, 8 GiB | não medido | não medido | — | 120 s **[estimativa: tempo do box + partida do container]** | 120 × (4 × 0,0000131 + 8 × 0,00000222) = **US$ 0,0084 = R$ 0,044** **[estimativa]**; com o multiplicador de 1,75×: US$ 0,0147 = R$ 0,076 |

Observações:
- O Colab A100 rodou o **notebook antigo**, sem o fix do NVENC e sem o ffmpeg fixo. A taxa mostrada era de ~6,77 unidades/h (≈ US$ 0,68/h); por essa taxa, 248 s dariam 0,47 unidade. Vale o débito **medido** no saldo: 0,43.
- O A100 foi rápido por ter **12 vCPU** (mais workers de captura), não pela GPU. A captura do Chrome é CPU (ADR-0003 §4). Uma máquina só CPU com muitos núcleos sai mais barata que uma GPU para este trabalho.

## 2. Voz: Gemini 3.8 Flash TTS

**Preço oficial** (tabela acima): US$ 0,50/1M tokens de texto de entrada, US$ 9,00/1M tokens de áudio de saída, 25 tokens por segundo de áudio. O preço publicado é do próprio `gemini-3.8-flash-tts`, sem substituto.

**Tier grátis e AI Studio [oficial]:**
- A tabela de preços marca o 3.8 Flash TTS como "Free of charge" no tier grátis (entrada e saída). Nesse tier o conteúdo "é usado para melhorar os produtos" do Google.
- Os limites do tier grátis (RPM/TPM/RPD por projeto) **não são publicados**. A página de [rate limits](https://ai.google.dev/gemini-api/docs/rate-limits) manda ver os limites ativos no AI Studio. O RPD zera à meia-noite do Pacífico.
- Tier 1: ligar o billing ao projeto. A [página de billing](https://ai.google.dev/gemini-api/docs/billing) pede um pré-pago mínimo de US$ 5, e o teto de gasto do Tier 1 é US$ 250 (página de rate limits).
- **Uso pela interface do AI Studio:** "Google AI Studio usage is free of charge in all available regions" (nota da página de pricing). O plano Google AI Pro vale só na interface web e não dá cota de API ([google-ai-plans](https://ai.google.dev/gemini-api/docs/google-ai-plans)).

**Conta por vídeo, tier pago, até 31/12/2026:**
- **Saída:** duração do áudio gerado. Uso a soma dos WAVs brutos do Gemini que estão no repositório, antes do corte de silêncio **[medido]**.
- **Entrada:** cada fala é uma requisição com o texto + o estilo. Estimo 3 caracteres por token, uma premissa conservadora para pt-BR **[estimativa]**.

| Vídeo | Falas | Áudio bruto | Tokens de saída | Custo saída | Caracteres de entrada | Tokens de entrada | Custo entrada | **Total** |
|---|---|---|---|---|---|---|---|---|
| **WJR** | 9 | **21,20 s** (19,21 s após corte) **[medido]** | 21,2 × 25 = **530** | 530 × 9,00/1M = **US$ 0,00477** | 239 do texto + 9 × 126 do estilo = 1.373 | ~458 | ~US$ 0,00023 | **US$ 0,0050 ≈ R$ 0,026** |
| **Lothus** | 4 | **14,12 s** (13,13 s após corte) **[medido]** | 14,12 × 25 = **353** | 353 × 9,00/1M = **US$ 0,00318** | 142 do texto + 4 × 206 do estilo = 966 | ~322 | ~US$ 0,00016 | **US$ 0,0033 ≈ R$ 0,017** |

- A partir de 01/01/2027 o preço dobra: WJR US$ 0,0100 (R$ 0,052); Lothus US$ 0,0067 (R$ 0,035).
- Cada regravação de uma fala custa de novo a parte dela. O cache do CLI (`timing.lock.json`) evita pagar duas vezes pelo mesmo texto, voz e estilo.
- Pelo AI Studio (manual) ou pelo tier grátis da API: **US$ 0** (tier grátis dentro do limite do projeto).

## 3. Entrega no Drive

upload via rclone (ferramenta de operação, fora do motor desde a #75) para o Drive do Wesley: **US$ 0 por vídeo**. Não há cobrança por upload nem por API. O arquivo ocupa a cota de armazenamento da conta: o MP4 da WJR tem **21,4 MB** **[medido]**. O custo só aparece se a conta precisar de um plano de armazenamento maior, e isso não é por vídeo.

## 4. Custo por vídeo (voz + render + Drive), WJR

| Cenário | Voz | Render | Drive | **Total US$** | **Total R$** | Base |
|---|---|---|---|---|---|---|
| **local + AI Studio** (padrão atual) | US$ 0 | US$ 0 | US$ 0 | **US$ 0,00** | **R$ 0,00** | AI Studio grátis **[oficial]**; render local **[medido]** |
| **local + API** (tier pago) | US$ 0,0050 | US$ 0 | US$ 0 | **US$ 0,0050** | **R$ 0,026** | voz **[oficial + medido]** |
| **Colab A100 + API** | US$ 0,0050 | US$ 0,0430 | US$ 0 | **US$ 0,0480** | **R$ 0,25** | render **[medido: 0,43 unidade]** × preço **[oficial]** |
| **Kaggle + API** | US$ 0,0050 | US$ 0 (cota) | US$ 0 | **US$ 0,0050** | **R$ 0,026** | cota grátis **[oficial]**; tempo **[estimativa]** |
| Modal só CPU + API (referência) | US$ 0,0050 | ~US$ 0,0084 | US$ 0 | **~US$ 0,013** | **~R$ 0,07** | render **[estimativa]** |

Com a API no tier grátis, a coluna Voz vale US$ 0 em todos os cenários (dados usados pelo Google, limite por projeto). Lothus: troque a voz por US$ 0,0033 (R$ 0,017); o render da Lothus em Colab/Kaggle não foi medido.

## 5. Margem: exemplo real da WJR vendida por R$ 60

| Cenário | Custo medido/oficial | Sobra dos R$ 60 | Margem sobre esses custos |
|---|---|---|---|
| local + AI Studio | R$ 0,00 | R$ 60,00 | 100% |
| local + API | R$ 0,026 | R$ 59,97 | 99,96% |
| Kaggle + API | R$ 0,026 | R$ 59,97 | 99,96% |
| Colab A100 + API | R$ 0,25 | R$ 59,75 | 99,6% |

**O que NÃO está nessa conta** (não é medido pela ferramenta; não invento números):
- **Custo do assistente (Grok Bot)** para coletar, escrever o contrato e revisar: a ferramenta **não mede** isso. Leia no painel de uso da sua conta e some por vídeo.
- Seu tempo, impostos sobre a venda, taxas do meio de pagamento, IOF/spread de cartão internacional, energia e amortização do box, e plano de armazenamento do Drive, se precisar.

**Como cobrar créditos** ([ADR-0002](decisoes/ADR-0002-cli-contrato-colab-creditos.md)): o custo variável real de voz e render fica abaixo de R$ 0,30 por vídeo em todos os cenários medidos. O que pesa é o tempo do assistente e o humano. Os backends remotos gravam `usage` no `render.manifest.json` (backend, GPU, tempos), e a voz grava `usage.tts_chars_this_run` no `timing.lock.json`. Isso permite debitar créditos pelo uso real.
