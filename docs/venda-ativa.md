# Venda ativa em massa — `simplicio-video prospect`

Lista de empresas → coleta pública → contrato por setor → **prévia com marca d'água Wesley Simplicio (@wesleysimplicio)** para o Wesley oferecer.
Tudo determinístico: nenhuma chamada de LLM por vídeo; mesma lista + mesma coleta → mesmos contratos e mesmas prévias.

## Fluxo

```bash
simplicio-video prospect lista.csv --lote dia-criancas            # saída em prospects/dia-criancas/
simplicio-video prospect lista.csv --out /caminho/lote --jobs 2    # outra pasta, 2 empresas em paralelo
simplicio-video batch lista.csv --so-contrato                      # alias; só coleta + contract.yaml (sem voz/render)
simplicio-video prospect lista.csv --lote dia-criancas --only <slug>       # refaz só uma empresa (piloto); as outras ficam intactas
simplicio-video render prospects/dia-criancas/<slug>/contract.yaml --preview   # refaz uma prévia
```

**Padrão atual: v2** (definido no piloto All Prime Odontologia, 30/09/2026) — voz **Gemini 3.8 Flash TTS, Laomedeia, leva animada** (exatamente a voz da Lothus v02; reserva: Achernar);
**logo real** da empresa no anel da assinatura; ritmo da Lothus v02 (cortes na batida de 128 BPM, transições de 6–10 frames,
confete/balões, texto palavra a palavra no tempo da fala) e a **mesma trilha festiva** da Lothus v02 (`trilha` idêntica, semente
`20261012`). O `result.json` grava `padrao`; prévia de padrão antigo é guardada como `preview.v1.mp4` e refeita.

1. **CSV** (UTF-8 com cabeçalho; só `nome` é obrigatório):
   `nome, cidade, setor, site, instagram, whatsapp, maps, nome_curto, fontes, logo, logo_fonte` (+ opcionais `logo_url` = apelido
   de `logo`, `oab` = inscrição REAL na OAB para advocacia, `template`/`campanha` = força o template da linha). `nome_curto` é o nome da marca
   no lockup e na fala ("Clínica Prata", "Pik Total"); `fontes` diz onde cada dado foi achado (busca web, site, página do shopping);
   `logo` = caminho (relativo ao CSV) ou URL do **logo real** tirado à mão do site ou do Instagram da própria empresa e
   `logo_fonte` = a página de onde veio (ex.: foto de perfil pública do Instagram quando o site está fora do ar).
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
3. **Setor → template → modelo**. Primeiro [`templates/prospect-roteamento.json`](../templates/prospect-roteamento.json) escolhe o
   template pela coluna `setor` (sem acento, minúsculas; sem casar, título/descrição do site), conforme `--campanha`:

   | Setor (regex) | `auto` (padrão) | `dia-das-criancas` | `institucional` |
   |---|---|---|---|
   | odontologia (`odonto`, `dent`, `ortodon`, `sorriso`, `implant`) | `sazonal-dia-das-criancas` | sazonal | `institucional-odontologia` |
   | advocacia (`advoca`, `advogad`, `juridic`, `direito`, `law`) | `institucional-advocacia` | **institucional-advocacia** (nunca festivo) | `institucional-advocacia` |
   | estética (`estetic`, `beleza`, `harmoniza`, `depila`, `spa`, `micropig`, `sobrancelha`, `cilios`, `laser`) | `institucional-estetica` | sazonal | `institucional-estetica` |
   | infantil (`pediatr`, `infantil`, `crianc`, `kids`, `escola`, `buffet`, `brinquedo`, `festa`, `game`…) | `sazonal-dia-das-criancas` | sazonal | erro (sem template) |
   | outros / sem setor | `sazonal-dia-das-criancas` | sazonal | erro |

   Depois, o `setores.json` do template escolhido dá o modelo do setor (blocos de s2/s3, frase da s3, subtítulo do lockup).
   Setores do sazonal: odontologia, pediatria, escola (berçário, cursos), brinquedos, festas (buffet, parque), games, moda infantil.
   **Templates institucionais** (mesmo padrão v2: voz Laomedeia, logo real, ritmo Lothus; sem confete):
   [`institucional-odontologia`](../templates/institucional-odontologia/) (fora de data comemorativa, mascote dente, 128 BPM),
   [`institucional-estetica`](../templates/institucional-estetica/) (elegante, ornamento `line-accent`, 128 BPM) e
   [`institucional-advocacia`](../templates/institucional-advocacia/) (sóbrio, OAB Provimento 205/2021, 96 BPM, sem percussão;
   **exige a coluna `oab`**: sem ela a linha fica `aguardando_oab`, com contrato e `falas-gemini.md`, mas sem render).
4. **Contrato** (`contract.yaml`): [`contract.base.yaml`](../templates/sazonal-dia-das-criancas/contract.base.yaml) (a
   coreografia da Lothus v02: 16 s, 128 BPM, cortes na batida, `fx-transition`, confete, `kinetic-words` palavra a palavra
   no tempo da fala) + o modelo do setor (mascote `tooth-character`/`icon-mascot`, frase da s3) + os dados reais: nome,
   @ do Instagram, cidade, logo e a cor do site (ajustada para contraste ≥ 3:1 com texto branco). As falas são genéricas da data
   e do setor: **nunca** preço, promoção, prazo, garantia, avaliação ou qualquer fato que não esteja na coleta.
   **Logo real** (nunca gerado, redesenhado ou inventado), nesta ordem: coluna `logo` do CSV > logo do site (`<img>` com "logo"
   ou `apple-touch-icon`) > avatar do Instagram (só se o robots.txt permitir, hoje nunca). Vira `coleta/logo.png` (só conversão
   de formato, mínimo 64 px) e entra no anel do `brand-lockup-soft` (redondo 440 px se for quase quadrado; 330 px sem cortar se
   for largo). Origem, URL e página ficam em `coleta.json → logo` e em `lote.csv` (`logo`, `logo_fonte`). Sem logo real = lockup de texto.
5. **Voz (padrão v2)** — institucionais usam a mesma Laomedeia com estilo do setor (advocacia: sóbria e calma): Gemini 3.8 Flash TTS, voz **Laomedeia** (reserva Achernar, como na Lothus), estilo "Voz feminina brasileira bem animada, de festa infantil:
   sorrindo, energia alta, vibrante e calorosa, ritmo rápido, português do Brasil, sem gritar e sem voz infantilizada.". Com `GEMINI_API_KEY` o CLI gera pela API (e guarda os WAVs em `assets/audio/vo/external/`);
   sem chave, usa as falas do Google AI Studio já salvas em `<slug>/assets/audio/vo/external/line-01..04.wav` (provider
   `file`); sem nenhuma das duas, a linha fica `aguardando_voz` e o CLI escreve `<slug>/falas-gemini.md` com o texto exato de
   cada fala, voz, estilo e duração máxima (`--so-contrato` também escreve, sem voz nem render). Procedência das falas:
   `assets/audio/vo/external/ORIGEM.txt` (voz, modelo, conta do AI Studio, data) vai para `voz.providers.file.origem` do
   contrato e para `assets/audio/LICENSES.md` da prévia. `--provider local` (Kokoro `pf_dora`, custo 0) é só rascunho, fora do padrão.
   Se uma fala estourar o slot, o CLI troca para a variante mais curta (frase curta do setor; nome curto; primeiro nome
   da marca), em ordem fixa (com a API; com falas fixas do AI Studio, gere uma leva mais curta). Nunca acelera a voz.
6. **Prévia** (`render --preview`): render local `draft` → pós-processo ffmpeg determinístico: 540x960, 30 fps, x264
   crf 30, AAC 96 kb/s; marca d'água "Prévia • Wesley Simplicio • @wesleysimplicio" em linhas diagonais (−30°, 20 % de opacidade,
   contorno escuro) cobrindo o quadro inteiro + selo "PRÉVIA · @wesleysimplicio" em dois cantos opostos (cortar um canto não
   remove a marca); cartão final de 2,5 s "Vídeo feito por Wesley Simplicio — @wesleysimplicio" (padrão desde 30/09/2026, pedido do Wesley:
   nunca SimpleTI/simpleti.com.br na prévia; teste garante). Logo entra no canto se
   existir `assets/brand/wesley-simplicio-logo.png` no repo (hoje não há: só texto). Não toca no `render.manifest.json` de entrega
   (grava `preview.manifest.json`).
7. **Saída**: `<out>/<slug>/{coleta.json, contract.yaml, preview.mp4, result.json}` + `<out>/lote.csv` (nome, setor, regra,
   instagram + fonte, whatsapp + fonte, status do site/Instagram, título, cores, logo, fontes, status, motivo da falha,
   caminho da prévia, tempo) + `lote.json` (resumo). Uma linha com erro não para o lote.
8. **Retomada idempotente**: linha com `preview.mp4` + `result.json` ok é pulada; `coleta.json` existente é reaproveitada
   (`--recoletar` refaz); `--force` refaz as prévias; voz em cache por hash.
9. **Paralelismo**: `--jobs N` empresas ao mesmo tempo. Cada render já usa `SV_WORKERS` capturas do Chrome (auto =
   núcleos − 2), então em 8 vCPU `--jobs 1` é o mais rápido por prévia; `--jobs 2` só compensa em máquina maior.

Prévias, coletas e relatórios ficam **fora do git** (`prospects/*` no `.gitignore`, exceto o CSV de exemplo).

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
| Voz `gemini` Laomedeia (padrão v2; 4 falas ≈ 130 caracteres) | ≈ US$ 0,003 (≈ R$ 0,02) pela API; R$ 0 no AI Studio/tier grátis, ver [custos.md](custos.md) |
| Render local (draft) + pós-processo | R$ 0 (só energia/CPU da máquina) |
| **Total (padrão v2)** | **≈ R$ 0,02** |
| Rascunho com voz `local` (Kokoro, fora do padrão) | R$ 0 |

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

## Piloto do padrão v2 — All Prime Odontologia (30/09/2026)

Refeita **só** a prévia da All Prime (as outras 9 continuam v1 até o Wesley aprovar o piloto):

```bash
simplicio-video prospect /workspace/prospects-piloto/dia-criancas/lista.csv --lote dia-criancas \
  --out /workspace/prospects-piloto/dia-criancas --only all-prime-odontologia
```

- Logo: o site do CSV (`allprimeodontologia.com.br`) e o da listagem de mapa (`allprimeodonto.com.br`) dão NXDOMAIN e não têm
  cópia no Wayback; o logo real veio da **foto de perfil pública do Instagram** @aprimeodonto (100x100, arte "All PRIME —
  Odontologia Especializada"), baixada uma vez à mão e registrada na coluna `logo`/`logo_fonte` do `lista.csv`.
- Voz: sem `GEMINI_API_KEY` no box, a linha fica `aguardando_voz` até as 4 falas Laomedeia do AI Studio entrarem em
  `all-prime-odontologia/assets/audio/vo/external/` (lista exata em `falas-gemini.md`); aí o mesmo comando renderiza.

**v02 → v03 (QA interno, 30/09/2026):** (1) fechamento: no cartão da marca as palavras "Com carinho, {nome}." (modo
bounce entra de cima, esticada) alcançavam o "@ / cidade" do `brand-lockup-soft`; agora os 4 templates de prospect usam
`tag_y: 880`, `chip_y: 1120` (cidade 130 px abaixo) e palavras em `y: 1470` / `size: 84`, e `src/simplicio_video/layout.py`
(`endcard_collisions`) recusa qualquer contrato cujo pior caso de animação chegue a menos de 20 px do bloco @/cidade
(testado em `tests/test_prospect_institucional.py`). A Lothus v02 entregue tem a mesma geometria antiga (não mexida).
(2) voz: o pipeline só corta silêncio no início/fim (fala intacta, amostra a amostra; verificado take → voz processada →
mix → mp4). Se uma fala não couber no slot, `voice` tenta uma vez o corte mais justo `TRIM_TIGHT` (-42/-45 dB, 40 ms
antes / 80 ms depois), que tira só o "ar" de -55..-45 dB que o AI Studio deixa antes da fala; nunca acelera a voz.
(3) marca: prévia assina **Wesley Simplicio · @wesleysimplicio** (marca d'água, selos e cartão final); teste garante que
nenhum template/prévia contém SimpleTI ou simpleti.com.br.

## Script de abordagem sugerido (o Wesley envia; nada automático)

Primeira mensagem (WhatsApp comercial ou DM do Instagram da empresa):

> Oi, tudo bem? Aqui é o Wesley Simplicio (@wesleysimplicio no Instagram), de Guarulhos. Fiz uma prévia de um vídeo de
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

## Board Paperclip (projeto "Videos")

- Os processos da venda de vídeos ficam no Paperclip, empresa **SimpleTI** (prefixo `SIM`), projeto **"Videos"**:
  https://vps.tail532f31.ts.net:8443/SIM/projects/videos/issues. Só abre pelo **Tailscale** do Wesley (VPS `vps.tail532f31.ts.net`).
- **Um card por tarefa ou lote**, com status real: `done`, `in_progress`, `todo`, `backlog`. Criado em 30/09/2026 com os
  cards SIM-102 a SIM-130: histórico (repo, CLI, vídeos WJR e Lothus, custos, pilotos, lote 2, planilha) e próximos passos
  (aprovação e envio dos lotes, follow-up, Pix AbacatePay, KYC, automação da entrega em HD).
- **Divisão:** planilha `controle-vendas-videos.xlsx` = clientes, valores e balanço; Paperclip = processos. Ao terminar
  um passo, atualize **os dois**.
- O Paperclip exige responsável para `in_progress`: esses cards ficam com o Wesley. **Não atribua cards a agentes** nem
  dispare execuções sem pedido explícito do Wesley.
- Acesso a partir do box de agentes: via Tailscale (modo userspace) e a API REST do Paperclip, com login aprovado pelo
  Wesley no navegador. As instruções ficam fora do repo; **nenhuma credencial entra no git**.
