# Referência da CLI

> Gerado por `scripts/gen_reference.py` a partir do `--help` real de cada comando. Não edite à mão: rode `make regen`.

Cada seção abaixo é a saída de `simplicio-video <comando> --help`. Os exemplos vêm do próprio help.

## simplicio-video

```text
usage: simplicio-video [-h] [--version] [--json] COMANDO ...

simplicio-video 0.4.0 — vídeo determinístico a partir de um contrato YAML (simplicio.video-contract/v1).
O LLM raciocina e escreve o contrato; o CLI executa. Mesma entrada => mesma saída.

Fluxo completo:
  1. init      gera o esqueleto do contrato a partir de um template de setor
  2. (autor)   preenche os TODO só com fatos de clients/<cliente>/coleta/
  3. validate  JSON Schema + assets existem + soma das durações + cada fala cabe na cena (sem acelerar)
  4. voice     gera/cacheia as falas (file | local | gemini API) e grava timing.lock.json com as durações reais
  5. render    contrato -> composição HyperFrames -> frames -> ffmpeg (trilha/SFX/voz, -14 LUFS)
               backend PADRÃO: local (referência de hash, sem custo). Opcionais, para clientes via créditos:
               kaggle (cota grátis semanal) | colab-cli (CLI oficial do Colab, pago em unidades) | colab (bundle manual)
  run          tudo de uma vez: voice -> validate --need-lock -> render (termina no MP4; o upload não é do motor)
  clone        trilha Clone (Hypit AI): clonagem de vídeos com agentes de IA (https://github.com/hypit-ai/hypit)
  montage      trilha Montage (OpenMontage): produção de vídeo com agentes de IA (https://github.com/calesthio/OpenMontage)
  edit         video-use: edita qualquer MP4 (HyperFrames, OpenMontage, OpenCut) por EDL (https://github.com/browser-use/video-use)
  opencut      editor open-source OpenCut para acabamento manual (https://github.com/OpenCut-app/OpenCut)
  formats      biblioteca de 50 formatos de anúncio (Drive) e pedido para adaptar uma copy a um formato
  swap         troca o personagem de um vídeo por um avatar de referência (gemini, fal, wavespeed, kie, alibaba); gasta só com --autorizo --yes
  jobs         tarefas em segundo plano (swap run, voice) num processo separado: submit, status, list, cancel, result
  toonflow     Toonflow (MIT): estúdio open-source de séries e vídeos com IA; serve pede --lan (https://github.com/HBAI-Ltd/Toonflow-app)
  moneyprinter MoneyPrinterTurbo (MIT): tema vira vídeo curto (roteiro por LLM, voz, estoque); serve só em 127.0.0.1, pede --lan para a rede (https://github.com/harry0703/MoneyPrinterTurbo)
  social       redes sociais sem postar: provedores (Real Oficial padrão, Zernio), plano de postagem com limites por rede, receita de chamadas MCP
  openverse    biblioteca de imagens e áudio do Openverse revisada por pedido: search, get, library (list, show, review, export, credits); licença das fontes, não é parecer jurídico
  busca        pesquisa e leitura de páginas na internet pelo CLI tinyfish (TinyFish), com fonte e data por resultado e teto de chamadas por dia: consulta, pagina, status, log; a consulta é enviada a um terceiro
  mcp          servidor MCP (stdio) com as tools video.init/validate/voice/render/run/list/clone/montage/edit/opencut/formats/swap/jobs/toonflow/moneyprinter/social/openverse/busca
  status       ferramentas (instaladas, versão, versão fixada) e, com CONTRATO, o estado do render (--json para o looping)
  install      copia as skills do simplicio-video para o host do agente (12 hosts; projeto, ou o home com --global; sem hooks); ambiente do checkout: scripts/dev_install.sh
  update       pacote pip: PyPI e reinstala as skills; checkout git: recusa (git pull e scripts/dev_install.sh); --check sai 0, 10 ou 2
  doctor       diagnóstico: Python, Node 22, ffmpeg com libass, disco, portas, credenciais, workspace
  setup        primeira execução: cria o workspace (tema, idioma, autonomia L1, orçamentos zero)

Schema do contrato: src/simplicio_video/data/schema/contract.schema.json (no checkout do plugin; ver `simplicio-video validate --help`).
Skill para LLMs: skills/simplicio-video/SKILL.md

options:
  -h, --help      show this help message and exit
  --version       mostra a versão do motor e sai (com --json: {version, engine})
  --json          com --version: imprime {version, engine} em JSON

comandos (na ordem do fluxo):
  COMANDO
    init          gera o esqueleto de contrato para <cliente> <campanha>
    validate      valida o contrato (schema, assets, durações, falas)
    voice         gera/cacheia as falas e grava timing.lock.json
    render        compila e renderiza (padrão local; kaggle/colab-cli/colab opcionais via créditos)
    run           voice -> validate -> render num comando só (para no MP4)
    clone         trilha Clone (Hypit AI): clonagem de vídeos com agentes de IA
    montage       trilha Montage (OpenMontage): produção de vídeo com agentes de IA
    edit          edição por EDL com video-use sobre qualquer MP4
    opencut       editor OpenCut (open-source) para acabamento manual
    toonflow      Toonflow (MIT): estúdio de séries e vídeos com IA, app web local
    moneyprinter  MoneyPrinterTurbo (MIT): tema vira vídeo curto, trilha externa de apoio
    formats       biblioteca de 50 formatos de anúncio (Drive) e pedido para adaptar uma copy
    swap          troca o personagem de um vídeo por um avatar (agnóstico de fornecedor)
    jobs          tarefas em segundo plano (swap run, voice) num processo separado
    social        redes sociais sem postar: provedores, plano de postagem e receita de chamadas MCP
    openverse     biblioteca de imagens e áudio do Openverse, revisada por pedido
    busca         pesquisa e leitura de páginas na internet (TinyFish), com procedência e teto diário
    mcp           servidor MCP (stdio) para o simplicio-runtime
    status        ferramentas instaladas, versões fixadas e estado do render
    list          lista templates, padrões de motion, providers de voz ou ângulos de anúncio
    install       copia as skills do simplicio-video para o host do agente (o projeto, ou o home com --global)
    update        atualiza: pip (PyPI) num pacote instalado; num checkout git recusa e diz o que rodar
    doctor        diagnóstico: login, update, runtime, Python, Node 22, ffmpeg+libass, disco, portas,
                  workspace
    login         entra com o login do Simplicio, o mesmo do Runtime (delega a `simplicio login google`)
    logout        apaga o arquivo de login compartilhado (desloga o Runtime também)
    auth          inspeciona o login compartilhado com o Runtime (auth status)
    setup         primeira execução: cria o workspace (tema, idioma, autonomia L1, orçamentos zero)

exemplos:
  simplicio-video list templates
  simplicio-video init <cliente> <Campanha> --template saude-odontologia --nome "<Nome do cliente>" --ano 2026
  simplicio-video validate clients/<cliente>/<campanha>/contract.yaml
  simplicio-video voice clients/<cliente>/<campanha>/contract.yaml --provider local
  simplicio-video render clients/<cliente>/<campanha>/contract.yaml
  simplicio-video render clients/<cliente>/<campanha>/contract.yaml --backend kaggle
  simplicio-video run clients/<cliente>/<campanha>/contract.yaml --provider gemini
  simplicio-video render contract.yaml --preview          # 540x960, marca d'água e crédito final do contrato (marca)

ambiente:
  SIMPLICIO_VIDEO_HOME  checkout do plugin (dados em src/simplicio_video/data/); padrão: os dados do próprio pacote
  SIMPLICIO_TTS_PY      python com kokoro-onnx para --provider local
  GEMINI_API_KEY        --provider gemini (aistudio.google.com/apikey; nunca commitar)
  KAGGLE_USERNAME, KAGGLE_API_TOKEN (ou ~/.kaggle/access_token)   --backend kaggle
  SIMPLICIO_COLAB_AUTH  oauth2|adc para --backend colab-cli (padrão do CLI colab)
  SIMPLICIO_FFMPEG_DIR  ffmpeg travado no render local (mesmo build em todo backend = mesmos bytes)
  SIMPLICIO_FFMPEG_URL/_SHA256  o mesmo ffmpeg (.tar.xz) baixado e conferido pelos backends remotos
  SV_WORKERS / SV_BROWSER_GPU  workers de captura (auto = núcleos-2) / raster de GPU no Chrome (1 = sem determinismo)
custo por vídeo (medido e oficial): docs/custos.md · credenciais: docs/decisoes/ADR-0003-fluxo-100-script.md
```

## simplicio-video auth

```text
usage: simplicio-video auth [-h] AÇÃO ...

Ações: status. Mostra quem está logado (conta mascarada), a validade do token, os direitos em cache e a versão do
Runtime, lendo ~/.simplicio/login.json (ou SIMPLICIO_AUTH_FILE). Nunca imprime um token.

options:
  -h, --help  show this help message and exit

ações:
  AÇÃO
    status    quem está logado, validade e direitos em cache; nunca imprime token

exemplos:
  simplicio-video auth status
  simplicio-video auth status --json
```

## simplicio-video busca

```text
usage: simplicio-video busca [-h] ...

Pesquisa e leitura de páginas na internet a serviço dos vídeos, pelo CLI `tinyfish` (npm @tiny-fish/cli, TinyFish), com procedência
(fonte e data de cada resultado) e teto de chamadas por dia. Zero tokens: nenhuma chamada de LLM; o comando só repassa e registra.

ATENÇÃO, PRIVACIDADE: a consulta (e a URL de `pagina`) é enviada a um terceiro (TinyFish). Nunca ponha dado pessoal nem segredo de
cliente nela. O motor recusa consulta com chave ou token (AIzaSy, AQ., sk-, sk_live_, ghp_, hf_, npm_, glpat-, Bearer, JWT, chave privada,
o valor de uma variável KEY/SECRET/TOKEN/PASSWORD do ambiente) sempre, e com e-mail, CPF ou CNPJ salvo --permitir-dado-pessoal (só no terminal). É um freio,
não uma garantia: telefone, nome de pessoa e endereço não são detectados.

Subcomandos:
  consulta "<texto>"   busca na web (`tinyfish search query`). --dominios a.com,b.com e --excluir c.com (até 10), --idioma pt,
                       --limite N (padrão 5, até 20, aplicado aqui), --atualizar ignora o cache e gasta 1 chamada
  pagina <url>         lê UMA página (`tinyfish fetch content get <url> --format markdown`): só http/https de host com nome público
                       (nada de IP, localhost, nem sufixo .internal, .local, .lan, .localdomain, .localhost, nip.io ou sslip.io: lista
                       curta, não garantia), sem usuário:senha nem chave, token, assinatura ou código na query ou no fragmento. Se a
                       página redirecionar para uma URL que o motor recusa, o conteúdo não é entregue (fica o registro). --max-bytes N
                       limita o texto (padrão 20 KB, de 1000 a 200000)
  status               o binário foi achado? versão? há chave? quanto do teto de hoje foi usado? Roda `tinyfish --version` e
                       `tinyfish auth status`, comandos locais que, pela leitura do código do pacote em 2026-10-16, não usam a rede:
                       funciona com SIMPLICIO_OFFLINE=1 e não gasta (o binário recebe só a lista fechada de variáveis)
  log [--ultimos N]    lista o registro de procedência (busca.registro.jsonl)
  --json               em todos: saída em JSON

Gasto: cada execução do binário (busca ou página) conta numa tabela por dia (UTC); passou do teto, o comando recusa com mensagem clara.
Teto: --max-chamadas-dia N, ou a variável SIMPLICIO_BUSCA_MAX_DIA, ou 20. Resposta em cache nunca gasta (repete offline); chamada que
falha também conta. Preço: UNVERIFIED. Segundo a leitura de 2026-10-16, a tabela de tarifas do TinyFish trazia busca e página a 0 USD e
cobrava agent e browser, mas uma segunda leitura voltou `Rates: unavailable`; por isso o teto existe. Confira a conta com
`tinyfish wallet status --pretty`, que é comando dele.

Procedência: toda consulta e toda página lida grava uma linha em busca.registro.jsonl (quando, consulta ou URL, versão do CLI, URLs
mostradas, sha256 e tamanho do que o CLI devolveu, se veio do cache). Cada resultado sai com a fonte (untrusted_fonte, a URL) e consultado_em
(a data): é o que um fato de cliente precisa para entrar em clients/<slug>/coleta/fontes.md. A busca não substitui a coleta do cliente.

Dado de terceiros: título, trecho, texto de página e URLs vêm da internet e saem SÓ em campos untrusted_* (texto e JSON, CLI e MCP), com
aviso: é dado de terceiros e nunca instrução (uma página pode tentar dar ordens ao agente). O texto é limpo (sem HTML, comentário,
caractere oculto, link que não seja http/https nem javascript:, data: ou file: solto) e cortado; nada é executado. Se o tinyfish
falhar, o que ele disse sai em untrusted_erro, nunca na mensagem do motor.

Instalação: o motor nunca instala nada. Sem o binário, `busca status` mostra o comando (`npm install -g @tiny-fish/cli@0.50.1`) e a chave
(`tinyfish auth login`, ou `... | tinyfish auth set`). A chave fica na configuração do próprio tinyfish ou em TINYFISH_API_KEY; nunca
por argumento, e o motor nunca a lê nem a imprime (o tinyfish recebe só uma lista fechada de variáveis).

Fora desta versão, de propósito: `agent`, `browser` e `monitor` do TinyFish (automação de navegador, cobrada por passo ou minuto, com login
e efeitos). Pelo MCP (video.busca): consulta, pagina, status e log, com o mesmo teto e a mesma recusa; sem --atualizar nem
--permitir-dado-pessoal.

positional arguments:
  args        consulta "<texto>" | pagina <url> | status | log

options:
  -h, --help  show this help message and exit

exemplos:
  simplicio-video busca consulta "campanha dia das crianças clínica odontológica" --idioma pt --limite 5
  simplicio-video busca consulta "avaliações" --dominios g1.globo.com,folha.uol.com.br --json
  simplicio-video busca pagina https://example.com --max-bytes 20480
  simplicio-video busca status
  simplicio-video busca log --ultimos 10 --json
```

## simplicio-video clone

```text
usage: simplicio-video clone [-h] ...

Invoca o Hypit AI (https://github.com/hypit-ai/hypit) para clonar vídeos de referência e gerar fluxos de trabalho completos.

positional arguments:
  args        argumentos repassados ao CLI do Hypit AI

options:
  -h, --help  show this help message and exit

exemplos:
  simplicio-video clone --help
  simplicio-video clone video.mp4
```

## simplicio-video doctor

```text
usage: simplicio-video doctor [-h] [--json] [--online] [all|login]

Checa o ambiente e diz a correção exata de cada falha, no contrato simplicio.doctor/v1 do simplicio-loop:
login, update, distribution, runtime, python, node, ffmpeg, ffmpeg-libass, disk, ports, GEMINI_API_KEY e setup.
Credenciais só mostram presença, nunca o valor, e nenhum token é impresso. warn não reprova: login ausente,
workspace ausente e GEMINI_API_KEY ausente são avisos. Exit code 1 só quando alguma checagem é fail.
Sem --online não usa rede: o update vem do cache do último `update --check`.

positional arguments:
  all|login   all (padrão): todas as checagens; login: só a linha do login

options:
  -h, --help  show this help message and exit
  --json      imprime {schema, status, version, checks[{name, status, summary, fix, detail}]} em JSON
  --online    consulta a última versão (GitHub ou git) e regrava o cache do update

exemplos:
  simplicio-video doctor
  simplicio-video doctor --json
  simplicio-video doctor login
  simplicio-video doctor --online
  docker compose run --rm simplicio doctor
```

## simplicio-video edit

```text
usage: simplicio-video edit [-h] ...

Encadeia tools/video-use (https://github.com/browser-use/video-use): setup, transcribe, pack, render, verify. A decisão de corte fica no edl.json versionado.

positional arguments:
  args        setup | transcribe | pack | render | verify

options:
  -h, --help  show this help message and exit

exemplos:
  simplicio-video edit setup
  simplicio-video edit render edit/edl.json -o out/final.raw.mp4
```

## simplicio-video formats

```text
usage: simplicio-video formats [-h] ...

Os 50 formatos da pasta 'Swipe File - 50 Formatos' (Drive): descrição, estrutura e o exemplo de cada um. `prompt` monta o pedido para adaptar uma copy ao formato; quem adapta é o LLM, não o CLI.

positional arguments:
  args        list [--objetivo ...] | show <id> | prompt <id> --copia <arquivo|->

options:
  -h, --help  show this help message and exit

exemplos:
  simplicio-video formats list --objetivo venda
  simplicio-video formats show caixinha
  simplicio-video formats prompt caixinha --copia roteiro.txt
```

## simplicio-video init

```text
usage: simplicio-video init [-h] --template TEMPLATE [--nome NOME] [--drive-nome DRIVE_NOME] [--ano ANO]
                            [--out OUT] [--force]
                            cliente campanha

Gera um contrato-esqueleto a partir de templates/<template>/template.json: cenas, padrões de motion,
voz sugerida e trilha padrão. Campos com TODO precisam ser preenchidos
(validate falha enquanto houver TODO). Schema: src/simplicio_video/data/schema/contract.schema.json.

positional arguments:
  cliente                  slug do cliente (pasta em clients/, ex.: clinica-sorriso)
  campanha                 campanha em Title_Case com underscore, sem acento (ex.: Dia_Criancas)

options:
  -h, --help               show this help message and exit
  --template, -t TEMPLATE  id do template de setor (ver `simplicio-video list templates`)
  --nome NOME              nome de exibição do cliente (padrão: TODO)
  --drive-nome DRIVE_NOME  NOME_CLIENTE no Drive (padrão: derivado de --nome/slug, ex.: Clinica_Sorriso)
  --ano ANO                ano da campanha (padrão: ano atual)
  --out, -o OUT            onde gravar (padrão: clients/<cliente>/<campanha-slug>/contract.yaml, no checkout
                           ou, instalado por pip, na pasta atual)
  --force                  sobrescreve um contrato existente

exemplos:
  simplicio-video init <cliente> <Campanha> --template saude-odontologia --nome "<Nome do cliente>"
  simplicio-video init <cliente> <Campanha> --template assistencia-tecnica-games --ano 2026 \
      --out clients/<cliente>/<campanha>/contract.yaml
```

## simplicio-video install

```text
usage: simplicio-video install [-h] [--target DIR] [--global] [--host HOST] [--dry-run] [--check] [--json]
                               [--verify] [--uninstall] [--prune-project-copies]

Copia as skills empacotadas (simplicio-video e simplicio-video-social) para o host do agente e grava o recibo de posse
.simplicio-video/install-ownership.json, como o `install` do simplicio-loop. Por padrão instala no projeto (--target, padrão: a
pasta atual) em .claude/skills/ e, para o host que precisa, no arquivo de entrada dele (AGENTS.md, GEMINI.md, CONVENTIONS.md,
.github/copilot-instructions.md ou .kiro/steering/simplicio-video.md). Um arquivo de entrada que já existe não recebe
apontador: fica como está. Com --global instala nas 11 pastas de skills do loop sob o home (~/.claude/skills, ~/.codex/skills,
~/.cursor/skills, ~/.grok/skills, ~/.agents/skills, ~/.copilot/skills, ~/.vscode/simplicio-skills, ~/.config/opencode/skills,
~/.config/amp/skills, ~/.kiro/steering e ~/.simplicio-loop/skills); com --global o --host é ignorado (o loop faz o mesmo). Em cada
pasta o install cria o que falta (entra no recibo com o sha256), atualiza só a cópia que é dele e que ninguém editou, deixa em
paz o que já existia ou que você editou e nunca apaga um arquivo extra seu; uma pasta secundária que é link é pulada, e
~/.claude/skills que é link recusa tudo.
Hosts (--host, padrão claude; all = todos): claude, codex, cursor, vscode, grok, kiro, antigravity, opencode, gemini, aider,
simplicio_agent, openclaw. O simplicio-video não tem hooks: só skills.
O install nunca sobrescreve nem apaga o que não é dele: outras skills, o seu AGENTS.md, uma SKILL.md que já existia ou que
você editou, um link simbólico. O install deixa isso em paz (left_alone) e diz. O recibo guarda o sha256 de cada arquivo: o --uninstall e
o --prune-project-copies só removem o que o recibo registra, que o registro de hosts consegue produzir e que ainda tem o sha256
gravado; um recibo com outro caminho (.git/config, src/app.py...) é recusado inteiro, e um install por cima dele o ignora.
As pastas que o install cria (.claude/skills, a da skill e .simplicio-video) nunca são link: com link ele recusa (exit 2) e
não escreve nada. A pasta base do host (~/.claude) pode ser link para o seu repositório de dotfiles: o install a resolve uma
vez, escreve no caminho real e o recibo o grava. Dois installs ao mesmo tempo no mesmo alvo esperam um pelo outro
(.simplicio-video/install.lock).
--verify confere os arquivos instalados com o recibo e com o pacote: se o alvo nunca foi instalado, uma skill foi alterada, falta
um arquivo ou o recibo é lixo, sai com exit 1, ok false e a lista do que difere (problems).
Saída: --check 0 em dia, 10 com mudança pendente; --dry-run 0 sem escrever; 1 se a instalação falhar (host desconhecido,
escrita negada, recibo em que não se confia, --verify que acha diferença); 2 para argumento inválido ou link nas pastas que o
install cria. --json imprime UM documento simplicio.video-install-plan/v1 (as mesmas chaves do plano do loop), também no
erro. Funciona igual num checkout e num pacote do pip. O ambiente de desenvolvimento do checkout (o .venv) é
`bash scripts/dev_install.sh` (Windows: `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\dev_install.ps1`). No
fim, se o setup nunca rodou, ele roda num terminal e senão diz como rodar.

options:
  -h, --help              show this help message and exit
  --target DIR            pasta do projeto onde instalar (padrão: a pasta atual)
  --global                instala nas 11 pastas de skills sob o home (~/.claude/skills, ~/.codex/skills...) em
                          vez do projeto
  --host HOST             id do host ou all (padrão: claude); com --global é ignorado
  --dry-run               mostra o plano e não escreve nada; sai com 0
  --check                 não escreve nada; sai com 0 se está em dia e com 10 se há mudança pendente
  --json                  imprime UM documento JSON (simplicio.video-install-plan/v1), também no erro
  --verify                confere os arquivos instalados com o recibo e com o pacote (exit 1 e a lista se algo
                          difere); não escreve nada
  --uninstall             remove só o que o recibo registra e ainda tem o sha256 gravado; com --dry-run, lista
                          e não remove
  --prune-project-copies  com --global: remove a cópia do projeto (--target) que o recibo dele registra,
                          depois de instalar no home

exemplos:
  simplicio-video install --check
  simplicio-video install --dry-run --json
  simplicio-video install
  simplicio-video install --host codex --target ~/meu-projeto
  simplicio-video install --global
  simplicio-video install --global --prune-project-copies --target ~/meu-projeto
  simplicio-video install --verify
  simplicio-video install --uninstall --dry-run
```

## simplicio-video jobs

```text
usage: simplicio-video jobs [-h] ...

Tarefas em segundo plano: `submit` volta na hora e a tarefa roda num processo separado (grupo de processos próprio,
um loop asyncio por tarefa), sem daemon e sem abrir porta. O estado fica em JSON em <dados>/jobs/<id>/job.json
($SIMPLICIO_VIDEO_DATA, padrão ~/.simplicio-video), com escrita atômica.

Lista fechada de tarefas:
  swap-run    swap run em segundo plano. Gasta dinheiro: confirmado AQUI, com --autorizo e --yes (as mesmas checagens
              do swap run: estimativa abaixo de --max-usd, chave no ambiente, saída livre). Só pelo terminal
  voice       voice em segundo plano. Provedor local (file, local, voxcpm, openvoice) não gasta; provedor de rede
              (gemini) pede --yes

Subcomandos:
  submit TIPO ...   cria a tarefa e devolve o id
  status ID         estado, tempos, pids e erro (estado lost = o runner morreu; a tarefa que sobrou é encerrada)
  list              tarefas, da mais nova para a mais antiga (--state filtra)
  result ID         o resultado de uma tarefa terminada (sai com 2 se ainda roda)
  cancel ID         SIGINT no grupo da tarefa, SIGKILL depois da tolerância; o swap cancela limpo e grava o manifesto
  clean             remove tarefas terminadas há mais de 7 dias (--older-than-days); `submit` também limpa

Pelo MCP (tool video.jobs): list, status, result, cancel e submit só de voz com provedor local. swap-run nunca.
A chave de API fica só no ambiente: argumentos com chave são recusados e nada vai para o estado nem para o log.

positional arguments:
  args        submit | status | list | cancel | result | clean

options:
  -h, --help  show this help message and exit

exemplos:
  simplicio-video jobs submit voice clients/x/video-01/contract.yaml --provider local
  simplicio-video jobs submit swap-run --provider gemini --video in.mp4 --ref avatar.png --out out/swap.mp4 --autorizo --yes
  simplicio-video jobs status 20261016-120000-1a2b3c4d --json
  simplicio-video jobs list --state running
  simplicio-video jobs result 20261016-120000-1a2b3c4d
  simplicio-video jobs cancel 20261016-120000-1a2b3c4d
```

## simplicio-video list

```text
usage: simplicio-video list [-h] [--json] [--grupo {problema,prova,desejo,decisao,estrategia}]
                            {templates,motion,voices,angles}

Catálogos do plugin: templates/ (renderizável = tem composição), motion/catalog.json, providers de voz, ângulos de anúncio (data/angles, 50 em 5 grupos; só fatos por marcador).

positional arguments:
  {templates,motion,voices,angles}
                                  catálogo a listar

options:
  -h, --help                      show this help message and exit
  --json                          saída em JSON
  --grupo {problema,prova,desejo,decisao,estrategia}
                                  só com angles: lista só os ângulos desse grupo

exemplos:
  simplicio-video list templates
  simplicio-video list motion --json
  simplicio-video list voices
  simplicio-video list angles --grupo prova --json
```

## simplicio-video login

```text
usage: simplicio-video login [-h] [--json] [--no-browser]

Espelho do `login` do simplicio-loop: roda `simplicio login google` do Simplicio Runtime (com o terminal ligado) e
confere o arquivo compartilhado ~/.simplicio/login.json (ou SIMPLICIO_AUTH_FILE). Sem o Runtime o login próprio é
UNVERIFIED (sem endpoint documentado): mostra como instalar o Runtime e sai com 1.
O login não libera nem cobra nada no motor, não guarda credencial e não recebe token por argumento: o filho roda com
ambiente mínimo (sem GH_TOKEN, chaves de API nem SIMPLICIO_LOGIN_TOKEN). A conta sai mascarada e nenhum token é impresso.
Saída: 0 verificado, 1 não verificado, 2 recusado (--no-browser impossível no Windows: no_browser_unsupported).

options:
  -h, --help    show this help message and exit
  --json        imprime um documento simplicio.login/v1 (a saída do Runtime vai para o stderr)
  --no-browser  pede ao Runtime que não abra o navegador e mostra o endereço e o código (Linux e macOS)

exemplos:
  simplicio-video login
  simplicio-video login --json
  simplicio-video login --no-browser
```

## simplicio-video logout

```text
usage: simplicio-video logout [-h] [--yes] [--json]

Apaga ~/.simplicio/login.json (ou SIMPLICIO_AUTH_FILE) sob a trava login.lock. Esse arquivo é do Simplicio Runtime
também: sair aqui desloga o Runtime, por isso sem --yes nada é apagado (REFUSED, exit 2). Só apaga um arquivo
comum, pequeno e com a forma de login do Runtime: JSON com access_token (texto) e access_expires_at (número); só
refresh_token, como nas credenciais do gcloud, não basta. Qualquer outro (uma chave ssh que SIMPLICIO_AUTH_FILE
aponte, uma pasta) é recusado, exit 2, not_a_login_file, sem apagar nada. Um link simbólico (um ponto de reparse
de link no Windows) também é recusado, exit 2, login_symlink, antes de qualquer trava, sem tocar no link nem no alvo.
O token de renovação não é revogado no servidor. Sem arquivo de login: NO_LOGIN, exit 0, nada é criado.

options:
  -h, --help  show this help message and exit
  --yes       confirma: sem isto nada é apagado
  --json      imprime um documento simplicio.logout/v1

exemplos:
  simplicio-video logout
  simplicio-video logout --yes
  simplicio-video logout --yes --json
```

## simplicio-video mcp

```text
usage: simplicio-video mcp [-h]

Expõe o CLI como servidor MCP (stdio): tools video.init, video.validate, video.voice, video.render,
video.run, video.list. Requer `pip install -e .[mcp]` (SDK Python `mcp`).
Contratos seguem src/simplicio_video/data/schema/contract.schema.json.

options:
  -h, --help  show this help message and exit

exemplos:
  simplicio-video mcp                  # stdio (o runtime lança este processo)
  simplicio-video-mcp                  # mesmo servidor, entrypoint dedicado
```

## simplicio-video moneyprinter

```text
usage: simplicio-video moneyprinter [-h] ...

Clona, prepara e sobe o MoneyPrinterTurbo (https://github.com/harry0703/MoneyPrinterTurbo, MIT) no commit fixado em tools.py. Exige Python 3.11 ou mais novo; o setup cria um venv isolado e copia o config.toml sem chave nenhuma. O upstream escuta em 0.0.0.0 por padrão na API; o serve força 127.0.0.1 (WebUI 8501, API 8080) e só abre para a rede com --lan. As chaves de API nunca são impressas. Fica fora do render determinístico.

positional arguments:
  args        clone [dir] | setup | serve [--webui] [--api] [--lan] [--host H] | where | status

options:
  -h, --help  show this help message and exit

exemplos:
  simplicio-video moneyprinter clone
  simplicio-video moneyprinter setup
  simplicio-video moneyprinter serve --api
  simplicio-video moneyprinter status
```

## simplicio-video montage

```text
usage: simplicio-video montage [-h] ...

Invoca o OpenMontage (https://github.com/calesthio/OpenMontage) para pipelines e agentes de produção de vídeo (Backlot, Remotion, HyperFrames).

positional arguments:
  args        argumentos repassados ao OpenMontage

options:
  -h, --help  show this help message and exit

exemplos:
  simplicio-video montage --help
  simplicio-video montage clone
  simplicio-video montage open
  simplicio-video montage serve --port 8000
```

## simplicio-video opencut

```text
usage: simplicio-video opencut [-h] ...

Clona e sobe o OpenCut (https://github.com/OpenCut-app/OpenCut, MIT; usa o opencut-classic até o rewrite ter API).

positional arguments:
  args        clone [dir] | dev | where

options:
  -h, --help  show this help message and exit

exemplos:
  simplicio-video opencut clone
  simplicio-video opencut dev
```

## simplicio-video openverse

```text
usage: simplicio-video openverse [-h] ...

Biblioteca local de imagens e áudio do Openverse (https://openverse.org/) para compor e melhorar os vídeos, com revisão
POR PEDIDO: o ativo só entra num vídeo se alguém aprovou aquele ativo para aquele pedido. Usa a API pública do Openverse;
o Openverse não endossa nem certifica o simplicio-video. Zero tokens: nenhuma chamada de LLM; o motor gera uma folha
determinística e quem revisa (agente ou pessoa) decide.

Subcomandos:
  search --tipo imagem|audio --consulta "..."   busca (cacheada por consulta, repete offline). --licencas cc0,pdm,by (padrão),
                                               --minimo-largura N (imagem), --duracao-min/--duracao-max S (áudio), --limite N
                                               (até 20 sem credencial, 50 com), --pagina N, --atualizar ignora o cache
  get <id> [--tipo imagem|audio]               baixa para a biblioteca: só https, IP público, limite de 25 MB (imagem) ou 50 MB
                                               (áudio), tipo pela assinatura do arquivo, nome pelo sha256
  library list|show <id>                       o que há na biblioteca, integridade e vereditos
  library review <id> --pedido "..." --folha    gera a FOLHA de revisão: dimensões, nitidez, brilho, miniatura (imagem); duração,
                                               taxa de amostragem, loudness, silêncio, clipping, espectrograma (áudio); pista textual
  library review <id> --pedido "..." --aprovar|--reprovar --motivo "..." --por "nome"
                                               grava o veredito do par (id, sha256 do ativo, pedido, proveniência); aprovar exige a folha antes;
                                               --canal terminal|plugin grava de onde veio (o servidor MCP grava mcp)
  library export <id> --pedido "..." --para PASTA | --contrato contract.yaml
                                               copia só o aprovado para aquele pedido (nunca sobrescreve bytes diferentes) e acrescenta
                                               a linha de crédito a CREDITS-openverse.md; contrato = assets/openverse ao lado dele
  library credits [--para PASTA]               bloco de créditos de tudo o que foi exportado
  library verify <contrato>                    confere, sem rede, os assets do contrato que vêm do Openverse (bloco openverse: {id, pedido}):
                                               id na biblioteca, sha256 do arquivo, veredito aprovado para o pedido, aceite da restrição e crédito;
                                               lista o que falta (o mesmo portão do validate e do render); sai com 1 se algo falta

No contrato: o export deixa o arquivo em assets/openverse/ e o asset declara a procedência com `openverse: {id: <uuid>, pedido: "..."}`;
arquivo em assets/openverse/ sem esse bloco é recusado. O render grava a procedência no render.manifest.json e os créditos ao lado do MP4.

Licenças: padrão cc0, pdm e by (seguras para uso comercial e edição). by-sa, by-nc e by-nd (e by-nc-sa, by-nc-nd) só por
opção explícita em --licencas, com aviso do que implicam; nc e nd nunca entram por padrão e o export de nc, nd e sa exige --aceito-restricao.
A licença que o Openverse devolve vem das fontes e ele mesmo manda conferir na origem (foreign_landing_url, gravada em cada
item): isto não é parecer jurídico. Item sem licença conhecida nunca é baixado; CC BY sem autor nunca é exportado.

Biblioteca em OPENVERSE_LIBRARY_DIR (padrão ~/.simplicio-video/openverse-library): index.json (schema versionado), files/<sha256>.<ext>,
cache/, sheets/. Credenciais OAuth2 opcionais só por variável de ambiente: OPENVERSE_CLIENT_ID e OPENVERSE_CLIENT_SECRET (nunca
por argumento; nada vai para índice, cache, folha ou saída). Respeite os termos do Openverse: sem raspagem em massa.
Pelo MCP (video.openverse): search, list, show, folha e review; baixar e exportar só pelo terminal.

positional arguments:
  args        search | get <id> | library list|show|review|export|credits

options:
  -h, --help  show this help message and exit

exemplos:
  simplicio-video openverse search --tipo imagem --consulta "sunrise over the sea" --minimo-largura 1280 --limite 10
  simplicio-video openverse search --tipo audio --consulta "rain" --duracao-min 20 --duracao-max 90 --json
  simplicio-video openverse get 9d8abc2c-c4dd-4dce-8164-cadd775befcf
  simplicio-video openverse library review 9d8abc2c-c4dd-4dce-8164-cadd775befcf --pedido "nascer do sol para a abertura" --folha
  simplicio-video openverse library review 9d8abc2c-c4dd-4dce-8164-cadd775befcf --pedido "nascer do sol para a abertura" \
      --aprovar --motivo "o sol aparece no centro, sem marca" --por "Wesley"
  simplicio-video openverse library export 9d8abc2c-c4dd-4dce-8164-cadd775befcf --pedido "nascer do sol para a abertura" \
      --contrato clients/acme/video-01/contract.yaml
  simplicio-video openverse library credits
  simplicio-video openverse library verify clients/acme/video-01/contract.yaml
```

## simplicio-video render

```text
usage: simplicio-video render [-h] [--backend {local,kaggle,colab-cli,colab}] [--out OUT]
                              [--accelerator ACCELERATOR] [--timeout TIMEOUT]
                              [--quality {draft,looks,delivery}] [--gpu] [--gpu-encode {auto,1,0}]
                              [--workdir WORKDIR] [--json] [--preview]
                              CONTRATO.yaml

Compila contrato + timing.lock.json + template (templates/<id>/composition) + blocos de motion +
assets numa composição HyperFrames (build/simplicio-video/), sintetiza trilha/SFX e mixa a voz
(engine build.mjs, semente fixa), renderiza os frames (hyperframes@0.8.97) e masteriza com ffmpeg
(loudnorm 2 passes, alvo trilha.master: -14 LUFS / TP -1,5). Grava render.manifest.json ao lado do
contrato: hash do contrato, de cada input compilado, das ferramentas e do vídeo/áudio decodificados.
Com ativos do Openverse (asset com openverse: {id, pedido}), o manifesto traz a procedência de cada um (chave openverse)
e os créditos vão para <saida>.CREDITS-openverse.md ao lado do MP4.
backends (todos sem navegador, exceto colab):
  local      PADRÃO. Renderiza aqui (CPU; --gpu usa encoder de GPU do HyperFrames se houver).
             Referência de hash, sem custo (vídeo de 600 frames: 76,5 s em 8 núcleos).
  -- opcionais, para clientes via créditos (custo e tempo medidos em docs/custos.md) --
  kaggle     bundle -> dataset privado Kaggle -> kernel (T4, internet) -> poll -> baixa o MP4.
             Precisa do CLI `kaggle`, KAGGLE_USERNAME + token (KAGGLE_API_TOKEN ou ~/.kaggle/access_token)
             e conta com telefone verificado (internet no kernel). --accelerator none = CPU (sem cota de GPU).
  colab-cli  Colab oficial por CLI (`pip install google-colab-cli`): new --gpu T4 -> upload -> exec ->
             download -> stop (sempre). Login Google uma vez (código colado no terminal).
  colab      NÃO renderiza: gera <saida>.colab-bundle.zip para colab/render.ipynb no navegador (manual)
Remotos baixam final.mp4 e gravam o mesmo render.manifest.json (+ usage: backend, GPU, tempos) para créditos.
--json: stdout só o objeto {ok, contrato, backend, preview, output, manifest}; erro vira
  {ok: false, error: {code, message}}. Códigos de erro (error.code): CONTRATO_NAO_ENCONTRADO,
  CONTRATO_INVALIDO, RENDER_FALHOU, FERRAMENTA_AUSENTE. Logs de render vão para stderr; exit 1 = erro.

positional arguments:
  CONTRATO.yaml                   caminho do contrato YAML (simplicio.video-contract/v1; schema em
                                  src/simplicio_video/data/schema/contract.schema.json)

options:
  -h, --help                      show this help message and exit
  --backend, -b {local,kaggle,colab-cli,colab}
                                  onde renderizar (padrão: local; kaggle/colab-cli/colab são opcionais, via
                                  créditos)
  --out, -o OUT                   MP4 de saída (local) ou .zip do bundle (colab); padrão: saida.arquivo
  --accelerator ACCELERATOR       kaggle: NvidiaTeslaT4 (padrão) | NvidiaL4 | none; colab-cli: T4 (padrão) |
                                  L4 | A100 | none
  --timeout TIMEOUT               kaggle/colab-cli: limite do render remoto em s (padrão 3600)
  --quality, -q {draft,looks,delivery}
                                  qualidade HyperFrames (padrão: saida.qualidade)
  --gpu                           local: encoder de GPU do HyperFrames (--gpu); muda os bytes do vídeo
  --gpu-encode {auto,1,0}         kaggle/colab-cli/colab: NVENC no encode (auto = usa se o teste de encode
                                  passar; 0 = libx264, necessário p/ comparar frames com o local). A captura
                                  (Chrome) é CPU de qualquer jeito
  --workdir WORKDIR               pasta da composição compilada (padrão: <contrato>/build/simplicio-video)
  --json                          imprime o resultado em JSON no stdout (ok, output, manifest; com erro,
                                  error.code); os logs vão para stderr
  --preview                       prévia (só local): render draft -> 540x960, 30 fps, x264 crf 30, marca
                                  d'água diagonal (marca.dagua, padrão 'Prévia') + selo nos cantos + cartão
                                  final com marca.credito.texto (2,5 s; sem crédito, sem cartão). Padrão
                                  --out: <saida.arquivo>-previa.mp4. Grava preview.manifest.json (não toca no
                                  render.manifest.json da entrega)

exemplos:
  simplicio-video render contract.yaml
  simplicio-video render contract.yaml --out /tmp/teste.mp4 --quality draft
  simplicio-video render contract.yaml --backend kaggle                   # opcional: T4 grátis (cota semanal)
  simplicio-video render contract.yaml --backend kaggle --accelerator none
  simplicio-video render contract.yaml --backend colab-cli --accelerator T4
  simplicio-video render contract.yaml --backend colab   # -> out/<nome>.colab-bundle.zip
  simplicio-video render contract.yaml --json            # resultado em JSON (logs no stderr)
  simplicio-video render contract.yaml --preview         # prévia 540x960 + marca d'água (marca.dagua) e crédito final (marca.credito)
```

## simplicio-video run

```text
usage: simplicio-video run [-h] [--provider {file,local,gemini,voxcpm,openvoice,voicestudio}] [--force-voice]
                           [--backend {local,kaggle,colab-cli,colab}] [--accelerator ACCELERATOR]
                           [--quality {draft,looks,delivery}] [--timeout TIMEOUT] [--json]
                           CONTRATO.yaml

Fluxo 100% script: validate -> voice (provider do contrato ou --provider, ex.: gemini) ->
validate --need-lock -> render (--backend local|kaggle|colab-cli|colab). Termina no render: o MP4 fica
em saida.arquivo. O upload no Drive não é feito pelo motor; é feito pela ferramenta de operação.
--json: stdout só o objeto JSON do resumo (ok, contrato, ...); erro vira {ok: false, error: {code, message}}.
  Códigos de erro (error.code): CONTRATO_NAO_ENCONTRADO, CONTRATO_INVALIDO, RENDER_FALHOU, FERRAMENTA_AUSENTE.
Schema: src/simplicio_video/data/schema/contract.schema.json.

positional arguments:
  CONTRATO.yaml                   caminho do contrato YAML (simplicio.video-contract/v1; schema em
                                  src/simplicio_video/data/schema/contract.schema.json)

options:
  -h, --help                      show this help message and exit
  --provider, -p {file,local,gemini,voxcpm,openvoice,voicestudio}
                                  override voz.provider
  --force-voice                   regera todas as falas (ignora o cache)
  --backend, -b {local,kaggle,colab-cli,colab}
                                  onde renderizar (padrão: local; kaggle/colab-cli/colab são opcionais, via
                                  créditos)
  --accelerator ACCELERATOR       ver `render --help` (none = CPU)
  --quality, -q {draft,looks,delivery}
                                  qualidade HyperFrames
  --timeout TIMEOUT               limite do render remoto em s
  --json                          imprime o resumo em JSON no stdout (com erro, error.code); os logs vão para
                                  stderr

exemplos:
  simplicio-video run contract.yaml                                   # voz do contrato, render local
  simplicio-video run contract.yaml --provider gemini                    # local (padrão)
  simplicio-video run contract.yaml --provider gemini --backend kaggle   # opcional (créditos)
  simplicio-video run contract.yaml --backend colab-cli --json
```

## simplicio-video setup

```text
usage: simplicio-video setup [-h] [--yes] [--theme ID] [--lang IDIOMA] [--force] [--realoficial]

Cria o workspace em $SIMPLICIO_WORKSPACE (padrão ~/.simplicio-video/workspaces/default) com
workspace.yaml (tema, idioma) e policy.yaml (autonomia L1; tokens, USD e créditos em zero).
--yes aceita os padrões sem perguntar. Não faz login nem grava credencial.

options:
  -h, --help     show this help message and exit
  --yes, -y      aceita os padrões sem perguntar
  --theme ID     tema visual (padrão: br)
  --lang IDIOMA  idioma do conteúdo (padrão: pt-BR)
  --force        regrava workspace.yaml e policy.yaml (zera orçamentos)
  --realoficial  mostra como conectar o MCP do Real Oficial (OAuth no cliente)

exemplos:
  simplicio-video setup
  simplicio-video setup --yes --theme br --lang pt-BR
  simplicio-video setup --yes --realoficial
```

## simplicio-video social

```text
usage: simplicio-video social [-h] ...

Redes sociais sem postar: o motor só planeja e documenta. `providers` lista o Real Oficial (`realoficial`, padrão) e o Zernio (`zernio`) com as ferramentas MCP de cada um; `plan` confere um MP4 final contra os limites de cada rede e grava social.plan.json (determinístico, sem chave); `check` reconfere o plano contra o arquivo; `recipe` imprime a sequência de chamadas MCP (cotar ou prever, mostrar ao usuário, pedir o consentimento, publicar). Este comando não posta, não chama o provedor e não guarda credencial: quem publica é o agente, com as ferramentas do próprio provedor e o sim explícito do usuário em cada postagem. Limites e ferramentas não conferidos na fonte oficial ficam marcados UNVERIFIED; uma violação de limite UNVERIFIED só passa com --aceito-unverified (assinado com chave local). `check` e `recipe` revalidam o plano contra o vídeo e a tabela. `recipe` do Real Oficial sem --clip-id sai BLOQUEADA (saída 1): o MCP dele não recebe MP4 local.

positional arguments:
  args        providers | plan | check <plano> | recipe <plano>

options:
  -h, --help  show this help message and exit

exemplos:
  simplicio-video social providers
  simplicio-video social plan --video out/final.mp4 --caption-file legenda.txt --target tiktok=@conta --target youtube
  simplicio-video social plan --video out/final.mp4 --caption "Texto #tag" --target instagram --at 2026-10-20T09:30 --timezone America/Sao_Paulo
  simplicio-video social check out/social.plan.json
  simplicio-video social recipe out/social.plan.json --clip-id <id do clip no Real Oficial>
  simplicio-video social recipe out/social.plan.json --provider zernio --json
```

## simplicio-video status

```text
usage: simplicio-video status [-h] [--json] [CONTRATO.yaml]

Estado do motor para o looping: ferramentas (OpenMontage, OpenCut, Hypit, ffmpeg, node) com
installed, version, pinned (versão fixada em tools.py ou SIMPLICIO_<NOME>_REF) e pinned_source.
Com CONTRATO, acrescenta o estado do render (render.manifest.json ao lado do contrato): rendered,
contract_sha256 e finished_at. Ferramenta ausente não é erro: sai com 0. Sai com 2 se o contrato não existir.

positional arguments:
  CONTRATO.yaml  contrato cujo render (render.manifest.json) será lido

options:
  -h, --help     show this help message and exit
  --json         imprime tools (e render, com CONTRATO) em JSON

exemplos:
  simplicio-video status
  simplicio-video status --json
  simplicio-video status --json clients/<cliente>/<campanha>/contract.yaml
```

## simplicio-video swap

```text
usage: simplicio-video swap [-h] ...

Troca o personagem de um vídeo existente por um avatar de referência. Agnóstico de fornecedor: cada provedor entra por
um adaptador (gemini, fal, wavespeed, kie, alibaba e fake para testes). Os adaptadores fal, wavespeed, kie e alibaba
estão UNVERIFIED: escritos da documentação pública, sem conferência na API real; `run` só gasta neles com
--aceito-unverified.

Subcomandos:
  providers             lista adaptadores, capacidades, preço (US$ e R$) e confiança
  estimate              custo previsto, sem rede (precisa de ffprobe)
  run                   executa; exige --autorizo; sem --yes só estima (dry-run); --max-usd é o teto de gasto
  status <manifesto>    lê o swap.manifest.json de uma execução

Os pedaços do vídeo vão em paralelo (asyncio sobre o cliente HTTP da biblioteca padrão): --concurrency N (padrão 3, o
adaptador pode limitar a menos; 1 = serial). A emenda e o manifesto seguem a ordem do vídeo; se um pedaço falhar, os outros
são cancelados e o erro diz qual foi; Ctrl+C cancela limpo. O ffmpeg (corte, normalização, emenda) segue serial.

A chave de API entra só pela variável de ambiente do provedor (GEMINI_API_KEY, FAL_KEY, WAVESPEED_API_KEY, KIE_API_KEY,
DASHSCOPE_API_KEY), nunca por argumento. Use só vídeo e imagens sobre os quais você tem direito. O prompt padrão mantém
todas as outras pessoas, o cenário, a câmera e o áudio.

positional arguments:
  args        providers | estimate | run | status <manifesto>

options:
  -h, --help  show this help message and exit

exemplos:
  simplicio-video swap providers
  simplicio-video swap estimate --provider gemini --video in.mp4 --ref avatar.png
  simplicio-video swap run --provider gemini --video in.mp4 --ref avatar.png --out out/swap.mp4 --autorizo
  simplicio-video swap run --provider gemini --video in.mp4 --ref avatar.png --out out/swap.mp4 --autorizo --yes --max-usd 2
  simplicio-video swap status out/swap.manifest.json --json
```

## simplicio-video toonflow

```text
usage: simplicio-video toonflow [-h] ...

Clona e sobe o Toonflow (https://github.com/HBAI-Ltd/Toonflow-app, MIT) no commit fixado em tools.py. Precisa de Bun. O serve escuta em 0.0.0.0:3000 sem login, por isso só sobe com --lan. Fica fora do render determinístico.

positional arguments:
  args        clone [dir] | serve --lan | where

options:
  -h, --help  show this help message and exit

exemplos:
  simplicio-video toonflow clone
  simplicio-video toonflow serve --lan
  simplicio-video toonflow where
```

## simplicio-video update

```text
usage: simplicio-video update [-h] [--check] [--dry-run] [--force]

Segue o `update` do simplicio-loop. Num pacote instalado por pip: python -m pip install --upgrade "simplicio-video==<última
release>" (PyPI; a última release vem do GitHub Releases) e, depois, `simplicio-video install --global`, que reinstala as skills
em ~/.claude/skills sem apagar nada que não seja do recibo. Um Python gerenciado pelo sistema (PEP 668) é recusado com as saídas
possíveis, e um Python sem pip (um `uv tool install`) também (exit 2): use `uv tool upgrade simplicio-video` ou `pipx upgrade`.
Num checkout git ou instalação editável o update RECUSA e sai com 2: o que atualiza é, dentro do checkout, `git pull` e
`bash scripts/dev_install.sh` (Windows: `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\dev_install.ps1`; o Windows de
cliente vem com a política Restricted, e o Bypass vale só para esse processo). Nada é puxado, reconstruído nem apagado.
Saída: --check 0 em dia, 10 com atualização, 2 erro; recusa 2; falha de rede 2 com --check, senão 1. Versão instalada mais nova
que a última release (o PyPI sai antes do GitHub Release) é em dia: 0. --force reinstala a release mesmo em dia e permite
downgrade (pip): só o nosso pacote, com --force-reinstall --no-deps, e só quando não há versão mais nova (com uma nova, o
--upgrade normal, que traz as dependências dela). --check grava o resultado em update-check.json (em $SIMPLICIO_VIDEO_DATA), que o doctor lê sem rede; num
checkout ele pergunta ao git quantos commits são novos (git fetch; alterações locais não atrapalham). --dry-run só mostra o plano e
sai com 0 no pacote (num checkout mostra a recusa). SIMPLICIO_OFFLINE=1 bloqueia toda a rede, também o git fetch do checkout
(--check sai com 2). Todo git do `--check` leva --no-optional-locks (para não regravar o .git/index); o git anterior à 2.15,
que não conhece a opção, é chamado de novo uma vez sem ela. Versão instalada de desenvolvimento ou pré-release (0.5.0rc1) é
anterior à release final (PEP 440).

options:
  -h, --help  show this help message and exit
  --check     não altera nada; sai com 0 (em dia), 10 (há atualização) ou 2 (erro)
  --dry-run   só mostra o plano e sai com 0 (no pacote; num checkout mostra a recusa); não altera nada nem
              grava o estado
  --force     reinstala a release do pip mesmo em dia e permite downgrade

exemplos:
  simplicio-video update --check
  simplicio-video update --dry-run
  simplicio-video update
  simplicio-video update --force
```

## simplicio-video validate

```text
usage: simplicio-video validate [-h] [--need-lock] [--json] CONTRATO.yaml

Valida o contrato contra o JSON Schema (src/simplicio_video/data/schema/contract.schema.json) e checa:
  - template existe e tem composição renderizável; ids de cena batem com a composição
  - padrões de motion existem em motion/patterns/ (bloco exige block.html)
  - todos os assets/logo existem (caminhos relativos ao contrato)
  - asset do Openverse (bloco openverse: {id, pedido}): id na biblioteca, sha256 do arquivo, veredito aprovado para o pedido,
    aceite da restrição e crédito em CREDITS-openverse.md, sem rede; arquivo em assets/openverse/ sem o bloco é recusado
  - soma de cenas[].duracao_s == formato.duracao_s
  - cada fala: inicio_s + max_s cabe na cena (+ J-cut voz.jcut_max_s, padrão 0,15 s);
    com timing.lock.json, a duração real <= max_s (a voz NUNCA é acelerada)
  - nenhum bloco drive (a entrega no Drive fica fora do motor); nenhum TODO
--json: stdout só o objeto {ok, contrato, errors, warnings}; erro vira {ok: false, error: {code, message}}.
  Códigos de erro (error.code): CONTRATO_NAO_ENCONTRADO, CONTRATO_INVALIDO, RENDER_FALHOU, FERRAMENTA_AUSENTE.
Saída 0 = válido, 1 = erros.

positional arguments:
  CONTRATO.yaml  caminho do contrato YAML (simplicio.video-contract/v1; schema em
                 src/simplicio_video/data/schema/contract.schema.json)

options:
  -h, --help     show this help message and exit
  --need-lock    falha se timing.lock.json faltar ou estiver desatualizado
  --json         imprime {ok, errors, warnings} em JSON

exemplos:
  simplicio-video validate clients/<cliente>/<campanha>/contract.yaml
  simplicio-video validate contract.yaml --json      # relatório em JSON
  simplicio-video validate contract.yaml --need-lock # exige timing.lock.json (antes do render)
```

## simplicio-video voice

```text
usage: simplicio-video voice [-h] [--provider {file,local,gemini,voxcpm,openvoice,voicestudio,elevenlabs,xai}]
                             [--force] [--concurrency N]
                             CONTRATO.yaml [FALA_ID ...]

Gera cada fala (cenas[].fala), trata (corte de silêncio + cadeia ffmpeg voz.processamento, 48 kHz mono)
e grava em voz.cache_dir (padrão assets/audio/voz/, versionado). Mede a duração real e grava
timing.lock.json ao lado do contrato. Fala maior que max_s = erro (sem time-stretch).
providers:
  file        WAVs externos (Gemini no Google AI Studio): voz.providers.file.dir/line-01.wav ... (ordem das falas)
  local       TTS local provisório (Kokoro, voz voz.voice ou voz.providers.local.voice, ex.: pf_dora)
  gemini      API Gemini TTS (GEMINI_API_KEY de aistudio.google.com/apikey; cota grátis serve; Google AI Pro NÃO
              inclui API). Modelo voz.providers.gemini.model (padrão gemini-3.8-flash-tts), voz, estilo em
              speech_metadata; api interactions (padrão) ou generate_content. WAV 24 kHz guardado em file.dir
  elevenlabs  stub (gere fora e use file)
  xai         stub (gere fora e use file)

positional arguments:
  CONTRATO.yaml                   caminho do contrato YAML (simplicio.video-contract/v1; schema em
                                  src/simplicio_video/data/schema/contract.schema.json)
  FALA_ID                         ids de fala para refazer com --force (ex.: vo2 vo4)

options:
  -h, --help                      show this help message and exit
  --provider, -p {file,local,gemini,voxcpm,openvoice,voicestudio,elevenlabs,xai}
                                  override voz.provider
  --force                         ignora o cache (com ids: só esses)
  --concurrency N                 falas geradas ao mesmo tempo, só em provedor de rede (gemini; padrão 4; 1 =
                                  serial). Provedor local é sempre serial

exemplos:
  simplicio-video voice contract.yaml                    # provider do contrato (voz.provider)
  simplicio-video voice contract.yaml --provider file    # depois de baixar line-01..NN.wav do AI Studio
  simplicio-video voice contract.yaml --force vo2        # refaz só a vo2
```
