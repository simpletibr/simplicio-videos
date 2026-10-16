# Changelog

O que mudou em cada issue. `simplicio-video update --check` mostra o diff deste arquivo antes de atualizar.

## Unreleased

### Correções na receita do social e na saída de tarefas
- **`social recipe` não reescreve mais a legenda aprovada.** A receita resolvia os campos do plano e depois passava a troca de marcadores sobre o resultado, então `{plan}`, `{step.x}`, `{video_name}` e `{video_sha256_short}` escritos DENTRO da legenda, do título ou do nome do vídeo viravam caminho, número de passo ou nome de arquivo, e a publicação pública podia sair diferente do que o usuário aprovou. Agora o texto do plano (legenda, título, contas, nome e caminho do vídeo) entra como dado, e só os modelos do `providers.json` passam pela troca de marcadores, em uma única passada que não reprocessa o que inseriu (a troca em cadeia também reprocessava o caminho do plano). Os espaços reservados que o próprio motor escreve (`passo N`) ganham o número na construção. Testes: legenda e título com `{plan}`, `{step.x}`, `{{`, `}}`, `%s`, `$(...)`, crase, quebra de linha, tab e emoji saem idênticos byte a byte na função, no CLI em JSON, no CLI em texto e no MCP, nos dois provedores; a receita hostil é igual à comum fora dos dados.
- **Chave local de aceite sem corrida.** Dois `plan --aceito-unverified` ao mesmo tempo estouravam `FileExistsError` (traceback) ao criar a chave. A chave agora sai inteira de um arquivo temporário privado e entra no lugar com `os.link` (atômico, nunca sobrescreve); quem perde a corrida relê a chave vencedora. Chave truncada vira erro claro do `social`, sem sobrescrever.
- **`jobs`: ordem da saída.** A linha de progresso (`\r`) ficava guardada até o fim da saída e saía DEPOIS das linhas reais que vieram depois dela, e o `error` de uma tarefa que falhou podia mostrar uma barra de progresso velha no lugar da mensagem. Ao chegar uma linha real, o progresso pendente é escrito antes dela (log, `tail` e leitura do JSON do resultado); no fim sai o último pendente, e os intermediários continuam colapsados em um só.
- `social.py`: comentários e docstrings em inglês (AGENTS.md), sem mudar comportamento; um teste vigia o arquivo. Mensagens de erro e textos de ajuda seguem em pt-BR.

### Kit de medição da troca de personagem em GPU de 6 GB
- Material de operação e de teste, sem mudar o motor: how-to em `docs/how-to/troca-personagem-gpu/` (passo a passo para Windows com GPU NVIDIA de 6 GB, prompt para a sessão da GPU, resultados dos testes em CPU e planilha) e seis scripts autônomos em `scripts/kit_gpu/`. Também funciona fora do repositório, copiando as duas pastas.
- Só testado em Linux com CPU: Windows, NVIDIA, ComfyUI e os modelos seguem sem teste, e as ressalvas UNVERIFIED e as licenças ficam como estavam. `numpy`/`opencv` (e `torch`) são só dos scripts, fora do `pyproject.toml`. Nenhuma mídia entra no repositório.

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

### Paralelismo (asyncio) e tarefas em segundo plano
- `swap run --concurrency N` (padrão 3; cada adaptador pode limitar a menos: os UNVERIFIED ficam em 2; 1 = serial): os pedaços do vídeo são enviados e consultados em paralelo (asyncio sobre o cliente HTTP da biblioteca padrão, cada chamada bloqueante numa thread daemon, sem dependência nova). A emenda e o manifesto seguem a ordem do vídeo, não a de conclusão: a saída tem o mesmo sha256 da serial. Se um pedaço falha, os outros são cancelados e o erro diz qual (`pedaço 2/3: ...`); `--timeout` vale por pedaço; Ctrl+C cancela limpo (estado `interrupted`, sem `.swap-work`, sem thread, handles pagos no manifesto). As regras do #103 continuam: manifesto gravado após cada submit, pedaços pagos preservados em `.swap-recovery`, submit nunca repetido após erro de rede. O ffmpeg (corte, normalização, emenda) segue serial.
- O manifesto registra `concurrency` (pedido, efetivo, limite do adaptador), `latency.total_s` por pedaço e `timing` (`wall_s`, `sum_chunks_s`, `speedup`, `saved_s`): o tempo total contra a soma dos tempos dos pedaços.
- `voice --concurrency N` (padrão 4, só provedor de rede: `gemini`): as falas são geradas em paralelo e o resto (ffmpeg, lock) segue a ordem das falas, então o `timing.lock.json` e os WAVs são byte a byte os do modo serial. Respeita cache e `only`. Provedores locais (CPU) ficam seriais.
- `simplicio-video jobs submit|status|list|cancel|result|clean` e a tool MCP `video.jobs`: tarefas em segundo plano num processo separado (runner asyncio por tarefa, grupo de processos próprio, sem daemon e sem porta de rede), com estado em JSON atômico em `<dados>/jobs/<id>/`. Lista fechada: `swap-run` (gasta: confirmado na submissão com `--autorizo --yes`, só pelo terminal) e `voice`. O MCP lista, consulta, lê o resultado, cancela e só submete `voice` com provedor local (`file`, `local`, `voxcpm`, `openvoice`); não há como confirmar gasto por ele. Runner morto vira `lost` (a tarefa que sobrou é encerrada); tarefas terminadas há mais de 7 dias são removidas. Argumentos com chave de API são recusados e a redação do swap vale para estado e log.
- `scripts/bench_concurrency.py`: benchmark com latência SIMULADA (adaptador `fake`, Gemini de voz trocado; sem rede). Medido aqui (mediana de 3, latência 1,0 s por pedaço e por fala, ffmpeg real): swap com 3 pedaços, serial 6,015 s contra paralelo 3,197 s (1,88x; só a fase dos pedaços, pelo manifesto: 2,74x); voice com 8 falas, serial 9,653 s contra paralelo (4) 3,613 s (2,67x). Saída idêntica nos dois (sha256 do MP4 e dos pedaços; `timing.lock.json` byte a byte). O ganho é de sobrepor espera, não de CPU: o render e o ffmpeg continuam seriais porque asyncio não acelera CPU e mais processos só disputariam os mesmos núcleos.

- Revisão independente do PR #106 (bloqueantes e importantes corrigidos, cada um com teste vermelho antes):
  - **B1** swap: o `submit` de um pedaço fica protegido do cancelamento. Quando outro pedaço falha (ou Ctrl+C) durante o upload, o pedaço espera até `SUBMIT_DRAIN_S` (10 s) pelo handle que o provedor devolver e o grava no manifesto antes de repropagar o cancelamento; se não terminar, o pedaço fica `possibly_charged: true` e `state: cancelled_during_submit`.
  - **B2** jobs: o grupo de processos de uma tarefa só recebe sinal depois de provada a identidade (pid, start time e boot id gravados em `task_start`/`task_boot` e conferidos). Sem prova (pgid reciclado, outro boot, estado antigo sem identidade) nada é morto: a tarefa vira `lost` e o erro diz que o grupo não foi encerrado. `list`, `status` e `submit` deixam de matar processo alheio.
  - **I1** jobs: a saída da tarefa é lida em blocos de 64 KiB, sem esperar `\n`. Barra de progresso com `\r` e linhas acima de 64 KiB não travam mais o runner (o pipe nunca enche); a chave partida na fronteira de um corte continua apagada.
  - **I2** voice: depois de uma falha, as falas já geradas (e pagas) entram no cache; a rodada seguinte paga só as que faltam, como no serial (12 chamadas contra 7 antes, agora 7). Nenhuma fala nova começa depois da primeira falha, as em voo terminam e são mantidas. O erro reportado é o da fala de menor índice (M3) e a chave do pré-cache passou a ser a mesma da chave real (M4).
  - **I3** o CLI inteiro volta a importar no Windows: nenhum atributo específico de plataforma no import (`signal.SIGKILL` resolvido em tempo de uso, `fcntl` importado onde é usado). `jobs` no Windows recusa com mensagem clara (precisa de grupos de processos e sinais POSIX).
  - **I4** sem `/proc` (macOS) o start time vem de `ps -o lstart=`; sem nenhuma prova de identidade, `cancel` não sinaliza o pid e pede para conferir à mão.
  - **I5** swap: uma execução por pasta de saída, com `flock` em `.swap.lock` (a segunda recusa com mensagem clara em vez de sobrescrever o `swap.manifest.json`); o manifesto agora é gravado com arquivo temporário e `os.replace`. `jobs submit swap-run` também recusa uma segunda tarefa ativa na mesma pasta. O nome do manifesto não mudou.
  - Menores: M1 `jobs submit` recusa argumento com formato de chave mesmo fora do ambiente; M2 o retry síncrono morto do swap foi removido e os testes de cota exercitam o caminho real; M5 o limite das threads órfãs está documentado em `aio.py`; M6 `video.jobs cancel` no MCP só envia o pedido (não bloqueia até 25 s). Sem correção: M7 (`status` não mostra `jobs`).
  - `scripts/bench_concurrency.py` e seu teste: a prova de paralelismo deixou de ser o relógio (o teste antigo afirmava `speedup > 1,2` e falhou 4 de 5 rodadas com 8 laços ocupando 4 núcleos) e passou a ser `max_in_flight` (o máximo de chamadas em voo ao mesmo tempo: 1 no serial, a concorrência pedida no paralelo; nas rodadas paralelas nenhum trabalho termina antes de todos estarem em voo). O ganho de tempo é só um número reportado, sem assert de relógio.
  - Benchmark depois das correções (mediana de 3, latência simulada de 1,0 s): swap serial 6,26 s contra paralelo 3,303 s (1,895x, saída idêntica); voice serial 9,742 s contra paralelo 3,793 s (2,568x, lock idêntico).

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
