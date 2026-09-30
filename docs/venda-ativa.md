# Venda ativa em massa — `simplicio-video prospect`

Lista de empresas → coleta pública → contrato por setor → **prévia com marca d'água SimpleTI** para o Wesley oferecer.
Tudo determinístico: nenhuma chamada de LLM por vídeo; mesma lista + mesma coleta → mesmos contratos e mesmas prévias.

## Fluxo

```bash
simplicio-video prospect lista.csv --lote dia-criancas            # saída em prospects/dia-criancas/
simplicio-video prospect lista.csv --out /caminho/lote --jobs 2    # outra pasta, 2 empresas em paralelo
simplicio-video batch lista.csv --so-contrato                      # alias; só coleta + contract.yaml (sem voz/render)
simplicio-video render prospects/dia-criancas/<slug>/contract.yaml --preview   # refaz uma prévia
```

1. **CSV** (UTF-8 com cabeçalho; só `nome` é obrigatório):
   `nome, cidade, setor, site, instagram, whatsapp, maps, nome_curto, fontes`. `nome_curto` é o nome da marca no lockup e
   na fala ("Clínica Prata", "Pik Total"); `fontes` diz onde cada dado foi achado (busca web, site, página do shopping).
   Exemplo versionado: [`prospects/exemplo-dia-criancas.csv`](../prospects/exemplo-dia-criancas.csv).
2. **Coleta** (`coleta.json`), pública e leve, com o agente `SimplicioVideoBot/<versão> (+https://simpleti.com.br)`:
   - site: só a página inicial (+ `robots.txt`, até 2 CSS do mesmo domínio e o arquivo do logo): `title`/`description`/
     `og:*`, `theme-color` + cores do CSS (sem cinzas, sem a paleta padrão do WordPress e sem as cores de WhatsApp/
     Instagram/Facebook), candidato a logo (`<img>` com "logo" ou `apple-touch-icon`), `og:image`, links de Instagram e
     WhatsApp (`wa.me`, `api.whatsapp.com`) e o número após "WhatsApp" no texto. Timeout de 15 s e limite de tamanho;
   - Instagram: só `og:title/description/image` públicos, **sem login**, uma tentativa, intervalo global mínimo de 6 s e
     **só se o `robots.txt` permitir**. O `instagram.com/robots.txt` tem `User-agent: * / Disallow: /` e proíbe coleta
     automatizada sem autorização por escrito, então hoje o CLI **não baixa nada do Instagram**: registra
     `nao_coletado: robots.txt…` e segue. O @ vem do CSV (busca web, com fonte) ou do link publicado no site;
   - Maps: só a URL do CSV (sem scraping).
3. **Setor → modelo**: regex de [`templates/sazonal-dia-das-criancas/setores.json`](../templates/sazonal-dia-das-criancas/setores.json)
   aplicados à coluna `setor` (sem acento, minúsculas); sem casar, ao título/descrição do site; senão `geral`. Setores:
   odontologia, pediatria, escola (berçário, cursos), brinquedos, festas (buffet, parque), games, moda infantil.
4. **Contrato** (`contract.yaml`): [`contract.base.yaml`](../templates/sazonal-dia-das-criancas/contract.base.yaml) (a
   coreografia da Lothus v02: 16 s, 128 BPM, cortes na batida, `fx-transition`, confete, `kinetic-words` palavra a palavra
   no tempo da fala) + o modelo do setor (mascote `tooth-character`/`icon-mascot`, frase da s3) + os dados reais: nome,
   @ do Instagram, cidade e a cor do site (ajustada para contraste ≥ 3:1 com texto branco). As falas são genéricas da data
   e do setor: **nunca** preço, promoção, prazo, garantia, avaliação ou qualquer fato que não esteja na coleta. O logo não
   é recriado (lockup de texto); o arquivo coletado fica em `coleta/` para o vídeo pago.
5. **Voz**: `local` (Kokoro `pf_dora`, custo 0) é o padrão da prévia; `--provider gemini` usa a API (`GEMINI_API_KEY`).
   Se uma fala estourar o slot, o CLI troca para a variante mais curta (frase curta do setor; nome curto; primeiro nome
   da marca), em ordem fixa. Nunca acelera a voz.
6. **Prévia** (`render --preview`): render local `draft` → pós-processo ffmpeg determinístico: 540x960, 30 fps, x264
   crf 30, AAC 96 kb/s; marca d'água "Prévia • SimpleTI • simpleti.com.br" em linhas diagonais (−30°, 20 % de opacidade,
   contorno escuro) cobrindo o quadro inteiro + selo "PRÉVIA · simpleti.com.br" em dois cantos opostos (cortar um canto não
   remove a marca); cartão final de 2,5 s "Vídeo feito pela SimpleTI — simpleti.com.br". Logo da SimpleTI entra no canto se
   existir `assets/brand/simpleti-logo.png` no repo (hoje não há: só texto). Não toca no `render.manifest.json` de entrega
   (grava `preview.manifest.json`).
7. **Saída**: `<out>/<slug>/{coleta.json, contract.yaml, preview.mp4, result.json}` + `<out>/lote.csv` (nome, setor, regra,
   instagram + fonte, whatsapp + fonte, status do site/Instagram, título, cores, logo, fontes, status, motivo da falha,
   caminho da prévia, tempo) + `lote.json` (resumo). Uma linha com erro não para o lote.
8. **Retomada idempotente**: linha com `preview.mp4` + `result.json` ok é pulada; `coleta.json` existente é reaproveitada
   (`--recoletar` refaz); `--force` refaz as prévias; voz em cache por hash.
9. **Paralelismo**: `--jobs N` empresas ao mesmo tempo. Cada render já usa `SV_WORKERS` capturas do Chrome (auto =
   núcleos − 2), então em 8 vCPU `--jobs 1` é o mais rápido por prévia; `--jobs 2` só compensa em máquina maior.

Prévias, coletas e relatórios ficam **fora do git** (`prospects/*` no `.gitignore`, exceto o CSV de exemplo).

## Cobrança e entrega (prévia aprovada → Pix → HD no Drive)

Depois que o cliente aprova a prévia, o Wesley escolhe o preço (**R$ 120** cheio; **R$ 80** oferta Dia das Crianças, só se o
cliente perguntar; **R$ 60** depois de 3 dias sem fechar). O código **nunca** aplica desconto sozinho: `--preco` é
obrigatório e só aceita 120, 80 ou 60. O CLI **não envia nada ao cliente**: o Wesley manda o copia-e-cola/QR.

```bash
export ABACATEPAY_API_KEY=...            # só no ambiente (chave de teste até o KYC, SIM-116)
simplicio-video venda cobrar prospects/<lote>/<slug> --preco 120   # Pix transparente; grava venda.json + pix-qr.png
# cobrança não paga vence em 24h (expiresIn explícito); rodar `cobrar` de novo depois de vencida cria outra (aceita outro --preco) e guarda o id antigo em cobrancas_anteriores
export ABACATEPAY_WEBHOOK_SECRET=...     # o mesmo secret cadastrado no webhook da AbacatePay
simplicio-video venda webhook serve --port 8787                    # escuta em 127.0.0.1
simplicio-video venda entregar prospects/<lote>/<slug>             # refaz só a entrega (status pago ou erro_entrega)
simplicio-video venda status [<lote>]                              # slug, preço, status, link
```

Estado em `prospects/<lote>/<slug>/venda.json` (fora do git): `cobranca_criada` → `pago` → `entregue` (com `link` do Drive) ou
`erro_entrega` (com `motivo`).

- **Cobrança**: `POST https://api.abacatepay.com/v2/transparents/create` com `method: PIX` e `data.amount` em centavos
  (12000 / 8000 / 6000). Precisa de chave com permissão de Pix transparente (SIM-112). Idempotente: com `venda.json`
  existente não cria outra cobrança (preço diferente = erro).
- **Webhook**: `POST /webhook/abacatepay?webhookSecret=...`. Valida o secret e a assinatura HMAC-SHA256 (`X-Webhook-Signature`,
  chave pública da AbacatePay), casa `transparent.completed` (`data.transparent.id`, `status=PAID`, valor igual ao da cobrança)
  com o `venda.json` e marca `pago`. Segredo/assinatura errados: 401; payload inválido: 400; evento de outro tipo ou valor
  diferente: 422; cobrança desconhecida: 404, tudo sem mudar estado. Evento repetido: 200 sem fazer nada. A entrega roda em segundo plano.
- **Entrega**: render final HD do `contract.yaml` do prospect + `publish` (rclone, nunca sobrescreve) em
  `simplicio-video/clientes/<CLIENTE>/<ANO>/<CAMPANHA>`, arquivo `<CLIENTE> - <descricao> - vNN.mp4` (o " - Previa " do nome da prévia
  sai). Não altera README de cliente. Falha de render/publish = `erro_entrega`; rode `venda entregar`.
- **Segredos**: só por variável de ambiente; nada em `venda.json`, log ou saída do CLI (teste cobre).
- **Fora daqui**: expor o webhook na internet (HTTPS/Funnel na VPS) precisa de aprovação do conselho; o servidor só escuta em
  127.0.0.1 por padrão. O payload do webhook segue a doc da AbacatePay; o E2E em modo teste (cobrança + `simulate-payment` +
  webhook local) fica pendente da chave da SIM-112.

## Limites

- **Só dados públicos e leves**: uma página por site, `robots.txt` respeitado, sem login, sem burlar bloqueio, sem
  scraping de Instagram/Facebook/Google Maps. Bloqueio (robots, 403/404, DNS) vira `site_status`/`instagram_status` no
  relatório e a prévia sai com os dados do CSV.
- **LGPD**: só dados da **empresa** (nome, cidade, setor, site, @ comercial, WhatsApp comercial publicado por ela). O texto
  guardado passa por limpeza (sem e-mails, telefones, nomes de profissionais "Dr./Dra.", números de CRO). Não guardar
  sócios, funcionários, clientes nem fotos de pessoas. Base legal da abordagem: legítimo interesse B2B, com opção de
  "não quero receber" respeitada na hora (anotar em `lote.csv`).
- **Sem envio automático**: o CLI não manda mensagem, e-mail nem DM. O Wesley revisa cada prévia e envia manualmente.
- **Sem fato inventado**: nada de preço, promoção, prazo, garantia, avaliação ou serviço não confirmado. A prévia é
  genérica da data; o vídeo pago usa a coleta completa com o cliente (fluxo normal, `docs/receita-video-cliente.md`).

## Custo por prévia

| Item | Custo |
|---|---|
| Coleta (1 página + robots + CSS) | R$ 0 |
| Voz `local` (Kokoro) | R$ 0 |
| Render local (draft) + pós-processo | R$ 0 (só energia/CPU da máquina) |
| **Total com voz local** | **R$ 0** |
| Opcional: voz `gemini` (4 falas ≈ 130 caracteres) | ≈ US$ 0,003 (≈ R$ 0,02), ver [custos.md](custos.md) |

Tempo medido no piloto (8 vCPU, `--jobs 1`): **~99 s por prévia**, 10 prévias em 16 min 32 s.

## Piloto — Dia das Crianças 2026 (10 empresas de Guarulhos-SP)

Rodado em 30/09/2026 (~18h BRT) num box de 8 vCPU, `--jobs 1`, voz `local`:

```bash
simplicio-video prospect /workspace/prospects-piloto/dia-criancas/lista.csv --lote dia-criancas \
  --out /workspace/prospects-piloto/dia-criancas --jobs 1
```

**10/10 prévias ok, 991,7 s no total (16 min 32 s), média de 99,2 s por prévia** (coleta 0–10 s, voz Kokoro ~8 s, render draft 1080x1920 + pós-processo ~86–94 s). Rodar de novo o mesmo comando pula as 10 (retomada idempotente, < 1 s). Cada prévia: 18,5 s (16 s + cartão final), 540x960, ~1,5 MB.

| Empresa | Setor → modelo | Instagram (fonte) | WhatsApp comercial (fonte) | Site | Tempo |
|---|---|---|---|---|---|
| All Prime Odontologia | odontologia | @aprimeodonto (csv) | coletado (csv) | falhou (DNS) | 96.1 s |
| Aurea Odontologia | odontologia | @aureaodontologia (site) | coletado (site) | ok | 108.48 s |
| Buffet Pik Total | festas | @buffetpiktotal (site) | coletado (csv confirmado no site) | ok | 106.41 s |
| Pikoki Diversões | festas | @pikoki.diversoes (csv) | coletado (csv) | sem site no CSV | 96.79 s |
| Happily Brinquedos | brinquedos | @happilybrinquedos (site) | coletado (csv confirmado no site) | ok | 97.26 s |
| Escola Maranata | escola | @ei.maranata (csv confirmado no site) | coletado (csv confirmado no site) | ok | 97.26 s |
| Baby & Kids Berçário e Escola | escola | @babyekids.vencermais (csv confirmado no site) | coletado (csv confirmado no site) | ok | 98.5 s |
| Colégio Cometa da Alegria | escola | @colegiocometadaalegria (site) | coletado (csv confirmado no site) | ok | 95.94 s |
| GuaruSmart | games | @guarusmart (site) | coletado (site) | ok | 97.33 s |
| ShopKids Guarulhos | moda-infantil | @shopkids_gru (csv confirmado no site) | coletado (site) | ok | 97.65 s |

Os números de WhatsApp ficam só no `lote.csv` do piloto (fora do git). Fontes completas por empresa na coluna `fontes` de `lista.csv`/`lote.csv` (busca web de 30/09/2026 + o próprio site). Falhas de coleta: All Prime Odontologia (domínio não resolveu no DNS na hora da coleta; @ e WhatsApp vieram do conteúdo do site indexado pela busca); Pikoki Diversões (sem site próprio: dados da página da loja no Shopping Bonsucesso); Instagram de todas: não coletado automaticamente (robots.txt do instagram.com proíbe robôs). Substituições durante o piloto: Clínica Prata e Game Velho saíram porque o @ não aparecia em fonte primária (entraram Aurea Odontologia e GuaruSmart, com @ e WhatsApp linkados no site).

## Script de abordagem sugerido (o Wesley envia; nada automático)

Primeira mensagem (WhatsApp comercial ou DM do Instagram da empresa):

> Oi, tudo bem? Aqui é o Wesley, da SimpleTI (simpleti.com.br), de Guarulhos. Fiz uma prévia de um vídeo de
> **Dia das Crianças** para a **{nome}**, com o nome e o @ de vocês, pronto para Reels/Stories. Posso te mandar aqui
> para você ver? São 16 segundos.

Se responder que sim, enviar o `preview.mp4` e:

> Essa é a prévia (baixa resolução, com marca d'água). A versão final sai em Full HD, sem marca d'água, com o logo de
> vocês e, se quiserem, fotos da loja e uma voz de locução profissional. Dá tempo de postar antes do dia 12/10.
> Quer que eu te passe como funciona?

Se não tiver interesse:

> Sem problema, obrigado pelo retorno! Não vou mandar mais mensagens. Boas vendas no Dia das Crianças!

Regras: uma mensagem por empresa, só no canal comercial publicado por ela, em horário comercial; não insistir; quem
pedir para não receber sai da lista (anotar em `lote.csv`). Não citar preço na primeira mensagem.

## Planilha de controle de vendas (única, no Drive)

Uma só planilha controla prospects, envios, respostas, preços e pagamentos. **Nunca criar outra nem cópia.**

- Arquivo: `controle-vendas-videos.xlsx` (Excel .xlsx de verdade, não convertido para Google Sheets)
- Pasta: `simplicio-video` (id `17OFuLyTCFyh9jG4Lb_GNnSpx-hcnHBfb`), conta wesleybob4
- **File id: `18uRagw8rS-FbEk_KM8E8h3r-5ytNO0hA`**
- Link: https://drive.google.com/file/d/18uRagw8rS-FbEk_KM8E8h3r-5ytNO0hA/view?usp=drivesdk
- Criada em 30/09/2026 18:30 (BRT) com `openpyxl` (script `/workspace/controle/build_controle.py` no box).
- Abas: `Prospects` (25 colunas; listas de status/canal/responsável/preço), `Resumo diario`, `Precos`, `Regras`,
  `Clientes` (WJR Informática Games e Lothus Odontologia, que não entram em Prospects).
- Carga inicial: as 10 empresas do piloto Dia das Crianças (`prospects-piloto/dia-criancas/lote.csv`), status
  `previa_pronta`, com fonte de cada dado em `fonte_dados`. `link_previa_drive` fica vazio até a prévia subir para o Drive.

Preços (aba `Precos`): R$ 120 cheio; R$ 80 oferta Dia das Crianças **só se o cliente perguntar**; R$ 60 três dias depois
se não fechar (`data_followup_60`). Nada vai para cliente sem o Wesley aprovar o lote (`aprovado_wesley` antes de
`enviado`). Sem falsa escassez. Atualizar todo dia.

### Como editar SEMPRE o mesmo arquivo (mesmo file id)

1. Antes de mexer, confirmar que só existe uma: `search_files` com
   `parentId = '17OFuLyTCFyh9jG4Lb_GNnSpx-hcnHBfb' and title contains 'controle'` → deve voltar só o id acima.
2. Baixar a versão atual: `DownloadFile` (conexão `user-Google-drive`, `fileId` acima) ou
   `download_file_content`. Editar localmente (openpyxl ou Excel) mantendo nome, abas e colunas.
3. Enviar o conteúdo como **nova versão do MESMO arquivo**: no Drive web (conta wesleybob4), botão direito no arquivo →
   **Gerenciar versões → Enviar nova versão** → escolher o .xlsx editado. O id e o link não mudam.
   (Equivalente por API: `PATCH https://www.googleapis.com/upload/drive/v3/files/18uRagw8rS-FbEk_KM8E8h3r-5ytNO0hA?uploadType=media`.)
4. Conferir com `get_file_metadata` (id acima): mesmo `id`, `modifiedTime` novo, `mimeType` ainda
   `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`.

Limites das ferramentas do agente (verificado em 30/09/2026):

- `update_file` do conector `user-Google-drive` **só altera nome e pasta** (metadados), **não o conteúdo**. Teste feito:
  `update_file` com o mesmo título → `id` igual, `modifiedTime` 21:30:06Z → 21:30:21Z (18:30 BRT), conteúdo intacto
  (download idêntico byte a byte ao enviado).
- `UploadFile`/`create_file` **sempre criam um arquivo novo** (id novo). **Não usar** para atualizar a planilha: isso gera
  duplicata. Se acontecer por engano, mandar o arquivo novo para a lixeira (`trash_file`) e refazer a edição no id acima.
- Sem ferramenta de upload de conteúdo para um id existente, o agente prepara o .xlsx editado no box e o Wesley (ou um
  agente com o navegador logado no Drive) faz o passo 3.
