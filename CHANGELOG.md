# Changelog

O que mudou em cada issue. `simplicio-video update --check` mostra o diff deste arquivo antes de atualizar.

## Unreleased

### Redes sociais sem postar (social)
- `simplicio-video social providers|plan|check|recipe` e a tool MCP `video.social` (só `providers`, `plan`, `check` e `recipe`; qualquer ação de publicar é recusada). O motor não posta ([ADR-0018](docs/decisoes/ADR-0018-social-planejar-sem-postar.md)): planeja, confere e documenta; quem publica é o agente, com as ferramentas MCP do Real Oficial (padrão) ou do Zernio e o sim explícito do usuário por postagem.
- `plan` recusa vídeo inexistente ou que não seja MP4, mede com `ffprobe` e confere duração, proporção, tamanho, legenda, título e hashtags contra `data/social/limits.json` (`source_url`, `read_on` e `confidence` por linha; só a duração do YouTube Shorts foi conferida na página oficial, o resto é UNVERIFIED e pede `--aceito-unverified`). Grava `social.plan.json` determinístico, sem horário de geração e sem chave ou token; não sobrescreve sem `--force`.
- `check` confere sha256, tamanho, integridade do plano e se o agendamento ainda está no futuro. `recipe` imprime a sequência exata de chamadas MCP por provedor (modelo de dados em `data/social/providers.json`): cotar ou prever, mostrar, consentimento, publicar; o motor se recusa a gerar receita que publique antes do consentimento.
- Skill `skills/simplicio-video-social/SKILL.md` com o fluxo e as regras de consentimento; `plugin.json` ganha quatro verbos fechados (`video.social.providers|plan|check|recipe`).
- Lacuna registrada: o Real Oficial não recebe MP4 local por MCP (a receita pede o `clip_id`); o fluxo do Zernio está em boa parte UNVERIFIED.
- Revisão do PR #107: `check` e `recipe` revalidam o plano contra o vídeo (`ffprobe`) e a tabela de limites e recusam plano que não seja o que `plan` geraria (o `plan_id` é só soma de integridade); o aceite UNVERIFIED é assinado (HMAC) com chave local. A trava de consentimento vale para a sequência completa do `providers.json`, executa `requires` e tem piso no código; `providers.json` adulterado faz o motor recusar a receita. Real Oficial sem `--clip-id` bloqueia a receita com o motivo (texto, JSON, MCP; saída 1). `youtube` (vídeo) separado de `youtube_shorts` (180 s e proporção 9:16 ou 1:1 só no Shorts, com um quadro de folga). Conta, legenda e título com cara de segredo são recusados; `--at` no passado ou além de 30 dias é recusado; sem `--ai-generated` a receita pergunta; o plano não segue symlink no `.tmp`; MOV renomeado para `.mp4` é recusado. Testes: varredura AST de importação dinâmica, fluxo sem socket, sequência com lista fixa e mutação.

### Troca de personagem (swap)
- `simplicio-video swap providers|estimate|run|status` e a tool MCP `video.swap` (só `providers` e `estimate`; gastar é só pelo terminal). Orquestração única em `src/simplicio_video/swap.py` e um adaptador por fornecedor em `src/simplicio_video/swap_providers/`: `gemini` (Interactions API, conferido na documentação), `fal`, `wavespeed`, `kie` e `alibaba` (**UNVERIFIED**: escritos da documentação pública, sem conferência na API real) e `fake` para testes.
- `--autorizo` é obrigatório; sem `--yes` só estima (dry-run, sem rede); `--max-usd` (padrão US$ 2) aborta antes de submeter; adaptador UNVERIFIED pede `--aceito-unverified`. A chave só entra pela variável de ambiente do provedor e nunca vai a argumento, log ou manifesto.
- Corta o vídeo em pedaços do tamanho que o provedor aceita, remonta o áudio original quando o provedor não o preserva, normaliza fps e duração e emenda. Grava `swap.manifest.json` com hashes, custo previsto e medido, latência por etapa, tentativas e o texto da autorização.
- Tabela de preços por adaptador com `source_url`, `read_on` (2026-10-15) e `confidence`, e câmbio de referência (R$ 5,0521 por US$, PTAX de 2026-10-15) em campo separado. `status` lista quais provedores têm a variável da chave definida (nunca o valor).

- Revisão independente do PR #103: a emenda usa nomes relativos e escapa apóstrofo no caminho; se algo falhar depois do download, os pedaços já gerados e pagos ficam numa pasta `<saída>.swap-recovery` (caminho na mensagem de erro e em `recovery_dir` do manifesto), nunca apagados; o manifesto é gravado logo após cada `submit` (com o handle) e também em Ctrl+C (`interrupted`, código 130) e em qualquer exceção, sem traceback.
- `submit` não é repetido após erro de rede nem após resposta 2xx sem JSON (a requisição pode ter sido aceita e cobrada; nenhum provedor tem chave de idempotência aqui): o erro avisa do risco e o pedaço fica com `possibly_charged: true` no manifesto. Respostas 429/5xx continuam com nova tentativa. Erro de cota ("You exceeded your current quota") e de plano grátis (`limit: 0`, qualquer redação) nunca repetem.
- A redação de segredos reconhece chaves pelo formato (`AIzaSy...`, `AQ....`) além das variáveis de ambiente, em log, manifesto e mensagem de erro. Chave com espaço ou caractere de controle é recusada. A chave do Gemini só vai a `*.googleapis.com` por https, e `SIMPLICIO_GEMINI_BASE` exige https (http só em localhost). `--max-usd` recusa `nan`, `inf` e negativo.
- `plugin.json`: o verbo `video.swap` deixou de aceitar `args` livre (que permitia `run` pago pelo runtime). Agora são dois verbos fechados e sem gasto: `video.swap` (só `estimate`, com `provider`, `video`, `ref`) e `video.swap.providers`.

### Formatos de anúncio
- `simplicio-video formats list|show|prompt` e o tool MCP `video.formats`. Biblioteca dos 50 formatos da pasta "Swipe File - 50 Formatos" do Drive (`src/simplicio_video/data/formats/formats.json`): cada um com a descrição, a estrutura, os limites, o objetivo e o link da pasta com o nome do arquivo de exemplo.
- `formats prompt <id> --copia <arquivo|->` monta o pedido para adaptar uma copy ao formato (instruções em `data/formats/instrucoes.md` + copy + formato). O CLI não chama modelo: quem adapta é o LLM.
- As descrições são estruturais, escritas a partir do nome do formato. Ficam com `verificado: false` até conferir o arquivo no Drive.
### Ângulos de anúncio
- `simplicio-video list angles [--grupo problema|prova|desejo|decisao|estrategia] [--json]` e o tool MCP `video.list` com `what=angles`. Catálogo de 50 ângulos em `src/simplicio_video/data/angles/angles.json`: 10 por grupo, cada um com gatilho, quando usar, gancho de exemplo (só com marcadores de fato, nunca número ou promessa) e cuidado.
### Trilha MoneyPrinterTurbo
- `simplicio-video moneyprinter clone|setup|serve|where|status` e a tool MCP `video.moneyprinter` (só `where` e `clone` na pasta padrão; `setup`, `serve`, `status` e `clone <pasta>` ficam no terminal). Checkout fixado do [MoneyPrinterTurbo](https://github.com/harry0703/MoneyPrinterTurbo) (MIT) em `tools.py`. Trilha externa de apoio, como toonflow e opencut: não substitui o `contract.yaml -> MP4`.
- `setup` cria um venv isolado em `MONEYPRINTER_DATA_DIR` (padrão `~/.simplicio-video/moneyprinter-data`), instala o `requirements.txt` do upstream (Python 3.11+), copia `config.example.toml` para `config.toml` sem preencher chave nenhuma e nunca sobrescreve um `config.toml` existente. `status` mostra só se o arquivo existe e quais chaves estão preenchidas.
- `serve` sobe a WebUI (porta 8501) e, com `--api`, a API (8080) em grupos de processos próprios. O upstream escuta em `0.0.0.0` por padrão na API, então o host é forçado para `127.0.0.1` por argumento (uvicorn em `app.asgi:app`, sem depender do `listen_host` do config); `--lan` é o único jeito de escutar em todas as interfaces.
- Revisão do PR #104: o `serve` ignora sinais repetidos durante a parada e repete a parada de cada servidor, trata SIGHUP (terminal fechado) como Ctrl+C e faz a varredura SIGKILL também do servidor que já saiu, para nenhum dos dois ficar órfão. Quando um servidor cai sozinho, diz qual foi em stderr e devolve código positivo.
- `serve --api` com `app.api_key` vazio avisa que a API fica sem login e recusa `CORS_ALLOWED_ORIGINS` com `*` nesse caso. Conferido no upstream (pino `4b7b965`): o CORS vem fechado por padrão, então outro site não lê a API; o risco que sobra é qualquer programa que alcance a porta usar as suas chaves.
- `status` lê o `config.toml` com `tomllib` (chaves pontuadas, entre aspas, tabelas inline, maiúsculas, `access_key_id`, `[[tabelas]]`), sem inventar nomes de dentro de um valor; o leitor por linha ficou de reserva para o Python 3.10 e TOML inválido. O `config.toml` criado pelo `setup` fica com modo 0600, o `setup` avisa quando o checkout não está no commit fixado, erros de arquivo e de processo viram `moneyprinter: ...` sem traceback, argumentos a mais em `clone`, `where` e `status` são recusados e o `setup` só exige Python 3.11 ao criar o venv.
### Trilha Toonflow
- `simplicio-video toonflow clone|serve --lan|where` e a tool MCP `video.toonflow` (clone na pasta padrão e where; `serve` só no terminal). Checkout fixado do [Toonflow](https://github.com/HBAI-Ltd/Toonflow-app) (MIT) em `tools.py`; `serve` faz `bun install --frozen-lockfile`, `build:server` e `start:server`. O Toonflow escuta em `0.0.0.0:3000` sem login, então `serve` recusa sem `--lan`. Dados em `TOONFLOW_DATA_DIR` (padrão `~/.simplicio-video/toonflow-data`), fora do checkout.
- Conhecido, fora deste trecho: os wrappers MCP de `video.montage`, `video.opencut`, `video.clone` e `video.edit` falham sempre com `TypeError` (o `_capture` passa `log=` a funções que não o aceitam). Corrigir exige capturar a saída dos subprocessos, porque eles escrevem no canal stdio do MCP e alguns não terminam (`opencut dev`, `montage serve`). Fica para issue própria.

### #31 Gate local
- `make check` roda o gate offline: checagens de ownership (`scripts/check_ownership.py`) e de TDD (`scripts/check_tdd.py`), pouso serializado (`scripts/land.sh`) e hooks em `.githooks/`. Sem GitHub Actions ([ADR-0005](docs/decisoes/ADR-0005-gate-sem-ci.md)).

### #43 Pacote de operação
- `./install.sh`, `simplicio-video install`, `update`, `doctor` e `setup`, com `Dockerfile` e `compose.yaml` só para build local ([ADR-0017](docs/decisoes/ADR-0017-instalacao-atualizacao.md)).

### #44 Docs
- Estrutura em `docs/` por tipo de documento: tutoriais, how-to, referência gerada, decisões (ADRs), host, plugins e factory.
- `docs/reference/` é gerado a partir do `--help` e das schemas; `make docs` falha se ficar desatualizado.
- `scripts/check_docs.py`: links relativos, âncoras, front matter, órfãos, pendências deixadas em texto e mermaid, offline.
- `docs/glossary.md` com os termos do projeto.
- Tutorial "Primeiro vídeo" e índices de tutoriais, how-to, decisões, host e plugins.

### #46 Licenças
- `scripts/licenses.py` confere as licenças do ambiente contra a allowlist (MIT, Apache-2.0, BSD, ISC, PSF, MPL-2.0), aceita exceções justificadas e checa o isolamento de dependências AGPL ([docs/host/licenses.md](docs/host/licenses.md)). `web/` ainda não entra no scan.

### #72 Saída em JSON
- `validate`, `run` e `render` aceitam `--json` com objeto estável e erros com código (`CONTRATO_NAO_ENCONTRADO`, `CONTRATO_INVALIDO`, `RENDER_FALHOU`, `FERRAMENTA_AUSENTE`).

### #73 Versão e status
- `simplicio-video --version --json` e `simplicio-video status` (texto e `--json`), para o looping.

### #74 Dados dentro do pacote
- Schemas, templates e motion do motor ficam em `src/simplicio_video/data/`, dentro do pacote.

### #75 Sem Drive no motor
- O bloco `drive` saiu do contrato e do motor. Contrato com `drive` falha no `validate`; a entrega fica fora do motor.

### #76 Marca como entrada do contrato
- Marca d'água e crédito final são entradas do contrato (`marca.dagua`, `marca.credito`), usadas por `render --preview`.

### #77 Motor sem vendas
- O CLI do motor não expõe mais os subcomandos de venda (`prospect`, `venda`, `ugc`, `publish`). Os módulos continuam no repositório.
