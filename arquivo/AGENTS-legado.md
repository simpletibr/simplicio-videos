# AGENTS.md — texto arquivado

Cinco trechos do [`AGENTS.md`](../AGENTS.md) que descreviam operação fora do repositório do motor: a missão e a venda ativa, o fluxo de UGC, as entregas no Drive e as linhas do mapa de pastas de coisas que saíram da raiz. Saíram do `AGENTS.md` na U16 do plano de limpeza e foram copiados para cá **como estavam**, byte a byte (cada bloco começa no comentário `<!-- origem: ... -->`): nada foi reescrito nem apagado. O `AGENTS.md` ficou só com o que vale hoje.

- Os links relativos dentro dos blocos apontam para onde as coisas ficavam antes (`ugc/README.md`, `docs/venda-ativa.md`, ...); onde cada uma está agora, em [`README.md`](README.md) desta pasta.
- O último item do bloco `drive` (redes sociais e a regra 3) é regra viva: o `AGENTS.md` continua com uma cópia dele.
- `scripts/check_docs.py` não confere nada em `arquivo/`.

## Linhas do mapa de pastas

Estas quatro linhas eram da tabela "Mapa (todas as pastas)":

<!-- origem: mapa -->
| Pasta | O quê | Entrada principal |
|---|---|---|
| `modules/h3-swap-service/` | Módulo opcional e isolado: troca de personagem em vídeo (MiniMax H3 + LoRA) em GPU alugada (Vast/Salad) com fila na Cloudflare. NÃO é importado pelo motor nem entra no wheel/sdist; `api/` (créditos/cobrança) é deploy próprio, fora do pacote (ver o conflito com o boundary no README do módulo). Tudo UNVERIFIED até o benchmark numa GPU real | [README](modules/h3-swap-service/README.md) |
| `ugc/` | **Trilha UGC (gerativa, fora do `render`)**: `pack.json` (10 personagens, `simplicio.ugc-pack/v1`) + `pack.schema.json`, `prompts/` (5 prompts: elenco, imagem, fullbody, roteiros, Seedance). O CLI `ugc list\|prompt` só monta/valida o prompt; imagem e vídeo são gerados à mão. [ADR-0004](docs/decisoes/ADR-0004-ugc-generativo.md) | [ugc/README.md](ugc/README.md) |
| `scripts/kit_gpu/` | **Kit de medição da troca de personagem em GPU de 6 GB** (material de operação e de teste, fora do pacote `simplicio_video`): seis scripts Python autônomos (`checar_maquina`, `preparar_entradas`, `medir_gpu`, `compor_final`, `conferir_troca`, `receita_test_hash`); `numpy`/`opencv`/`torch` são só deles, fora do `pyproject.toml`. Texto, prompt e resultados em `docs/how-to/troca-personagem-gpu/` | [LEIA-ME](docs/how-to/troca-personagem-gpu/LEIA-ME.md) |
| `prospects/` | **Venda ativa** (fora do git, exceto `exemplo-dia-criancas.csv`): `<lote>/<slug>/{coleta.json, contract.yaml, preview.mp4, result.json}` + `<lote>/lote.csv` | [docs/venda-ativa.md](docs/venda-ativa.md) |

<!-- origem: missao -->
## Missão e operação de vendas

Este repositório é só a **execução dos scripts e a geração dos vídeos** (CLI `simplicio-video`). A **missão de vendas e o guia de operação** (preços, mensagens aprovadas, funil, planilha de controle, Paperclip, times, estado atual e próximos passos) ficam no Google Drive, em [`simplicio-video/AGENTS.md`](https://drive.google.com/file/d/19Y0BvZw-st_YasMk39vNkbNGd_4pJ4ir/view?usp=drivesdk) (conta wesleybob4). Leia esse guia antes de qualquer trabalho de venda ativa.

<!-- origem: venda-ativa -->
**Venda ativa em massa (prévias para oferecer)**
1. Monte o CSV (`nome, cidade, setor, site, instagram, whatsapp, maps, nome_curto, fontes`) com empresas achadas por busca web; registre a fonte de cada @/WhatsApp.
2. O template sai da coluna `setor` (tabela de roteamento do repositório de operação; saiu do pacote do motor): `--campanha auto` (padrão) = odontologia/infantil no Dia das Crianças, advocacia e estética nos institucionais; `--campanha institucional` = institucional por setor. Advocacia exige `oab`.
   `prospect` saiu do CLI do motor (#77) e fica no repositório de operação (antes gerava `prospects/<lote>/<slug>/preview.mp4` + `lote.csv`).
3. Padrão v2 (default): voz Gemini 3.8 Flash TTS Laomedeia animada (a da Lothus v02; reserva Achernar), **logo real** (coluna `logo` do CSV tirada do site/Instagram da empresa, ou logo do site) e ritmo da Lothus v02; nunca gerar/recriar logo. Só dado público e da empresa (LGPD), Instagram sem login (robots.txt do instagram.com proíbe robôs: o @ vem do CSV/site), nunca preço/promoção/fato inventado. **Nada é enviado pelo agente**: o Wesley revisa e envia ([docs/venda-ativa.md](docs/venda-ativa.md)).

<!-- origem: ugc -->
**Vídeo UGC (gerativo)** ([ugc/README.md](ugc/README.md) · [ADR-0004](docs/decisoes/ADR-0004-ugc-generativo.md))
1. Fatos e público vêm de `clients/<slug>/coleta/`; sem fato confirmado, sem fala ("Só fatos reais"). Fora da esteira: sem contrato, template, motion nem `render`, e fora da regra de determinismo.
2. Elenco, prompt de imagem e roteiros (passos 1, 2, 4) são prompts de LLM em `ugc/prompts/01` a `04`; imagens (passo 3) e clipes (passo 6) são gerativos e manuais (ChatGPT, Higgsfield, Krea).
3. Os comandos `ugc` saíram do CLI do motor (#77) e ficam no repositório de operação. Renderize 1 clipe por personagem, confira rosto e voz e só então use o áudio como referência de voz nos outros.
4. Travas: personagem sintético (nunca rosto ou voz de pessoa real sem autorização); sem depoimento fabricado apresentado como cliente real; rótulo de IA da plataforma e CONAR; imagens e MP4 em `out/ugc/<slug>/` e no Drive, nunca no git; chaves só no ambiente; gerar em plataforma paga só com pedido explícito do Wesley.

<!-- origem: drive -->
## Entregas no Google Drive

- Vídeo entregue fica no Drive em `simplicio-video/clientes/NOME_CLIENTE/ANO/CAMPANHA`.
  - `NOME_CLIENTE`: Title_Case com underscore, sem acento (ex.: `WJR_Informatica_Games`, `Lothus_Odontologia`).
  - `ANO`: ano da campanha (`2026`). `CAMPANHA`: Title_Case com underscore (ex.: `Video_Institucional`, `Dia_Criancas`).
- Nome do arquivo: `<CLIENTE> - <descricao> - vNN.mp4` (ex.: `Lothus - Dia das Criancas 15s - v01.mp4`); versão nova = `vNN+1`, nunca sobrescrever.
- O repositório guarda **os links**, nunca o MP4 final como entrega (`out/` é gitignored; `preview/` só leva a prévia leve 720p).
- Todo link novo entra na tabela **Entregas no Drive** de `clients/<slug>/README.md` (campanha, pasta, arquivo, link, versão/status).
- Upload: `publish` e a flag de upload do `run` saíram do CLI do motor (#77) e ficam no repositório de operação (rclone, remote `gdrive`; nunca sobrescreve, link pelo ID). O agente **só** faz upload com pedido explícito do Wesley para aquele vídeo. A exceção do fluxo de venda (Pix) também saiu do motor (#77).
- Redes sociais não são upload no Drive e a regra 3 continua valendo: **O motor não posta.** O módulo `social` não é exceção à regra 3: só planeja e documenta (`social providers|plan|check|recipe`: confere o MP4 contra os limites de cada rede, grava `social.plan.json` e imprime a receita de chamadas MCP; sem rede, sem credencial, nada de publicar no MCP do motor). Quem posta é o agente, com as ferramentas MCP do próprio provedor (Real Oficial, padrão, ou Zernio) e o sim explícito do Wesley para cada postagem. Skill: [`skills/simplicio-video-social/SKILL.md`](skills/simplicio-video-social/SKILL.md) · [ADR-0018](docs/decisoes/ADR-0018-social-planejar-sem-postar.md).
