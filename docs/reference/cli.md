# Referência da CLI

> Gerado por `scripts/gen_reference.py` a partir do `--help` real de cada comando. Não edite à mão: rode `make regen`.

Cada seção abaixo é a saída de `simplicio-video <comando> --help`. Os exemplos vêm do próprio help.

## simplicio-video

```text
usage: simplicio-video [-h] [--version] [--json] COMANDO ...

simplicio-video 0.3.0 — vídeo determinístico a partir de um contrato YAML (simplicio.video-contract/v1).
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
  toonflow     Toonflow (MIT): estúdio open-source de séries e vídeos com IA; serve pede --lan (https://github.com/HBAI-Ltd/Toonflow-app)
  moneyprinter MoneyPrinterTurbo (MIT): tema vira vídeo curto (roteiro por LLM, voz, estoque); serve só em 127.0.0.1, pede --lan para a rede (https://github.com/harry0703/MoneyPrinterTurbo)
  social       redes sociais sem postar: provedores (Real Oficial padrão, Zernio), plano de postagem com limites por rede, receita de chamadas MCP
  mcp          servidor MCP (stdio) com as tools video.init/validate/voice/render/run/list/clone/montage/edit/opencut/formats/swap/toonflow/moneyprinter/social
  status       ferramentas (instaladas, versão, versão fixada) e, com CONTRATO, o estado do render (--json para o looping)
  install      ambiente do checkout: .venv com uv, Python 3.12 e extras (--check mostra o plano)
  update       git pull --ff-only (recusa árvore suja), reinstala, reconstrói web/ e roda doctor
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
    social        redes sociais sem postar: provedores, plano de postagem e receita de chamadas MCP
    mcp           servidor MCP (stdio) para o simplicio-runtime
    status        ferramentas instaladas, versões fixadas e estado do render
    list          lista templates, padrões de motion, providers de voz ou ângulos de anúncio
    install       ambiente idempotente: .venv com uv, Python e extras (--check mostra o plano)
    update        git pull --ff-only (recusa árvore suja), reinstala, reconstrói web/ e roda doctor
    doctor        diagnóstico: Python, Node 22, ffmpeg+libass, disco, portas, credenciais, workspace
    setup         primeira execução: cria o workspace (tema, idioma, autonomia L1, orçamentos zero)

exemplos:
  simplicio-video list templates
  simplicio-video init lothus-odontologia Dia_Criancas --template saude-odontologia --nome "Lothus Odontologia" --ano 2026
  simplicio-video validate clients/lothus-odontologia/video-01-dia-das-criancas/contract.yaml
  simplicio-video voice clients/lothus-odontologia/video-01-dia-das-criancas/contract.yaml --provider local
  simplicio-video render clients/lothus-odontologia/video-01-dia-das-criancas/contract.yaml
  simplicio-video render clients/wjr-informatica-games/video-01/contract.yaml --backend kaggle
  simplicio-video run clients/lothus-odontologia/video-01-dia-das-criancas/contract.yaml --provider gemini
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
usage: simplicio-video doctor [-h] [--json]

Checa o ambiente e diz a correção exata de cada falha. Credenciais só mostram presença, nunca o valor.
Aviso (warn) não reprova. Exit code 0 sem falhas; 1 se alguma checagem falhou. --json para máquinas.

options:
  -h, --help  show this help message and exit
  --json      imprime {ok, checks[{name, status, detail, fix}]} em JSON

exemplos:
  simplicio-video doctor
  simplicio-video doctor --json
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
  cliente                  slug do cliente (pasta em clients/, ex.: lothus-odontologia)
  campanha                 campanha em Title_Case com underscore, sem acento (ex.: Dia_Criancas)

options:
  -h, --help               show this help message and exit
  --template, -t TEMPLATE  id do template de setor (ver `simplicio-video list templates`)
  --nome NOME              nome de exibição do cliente (padrão: TODO)
  --drive-nome DRIVE_NOME  NOME_CLIENTE no Drive (padrão: derivado de --nome/slug, ex.: Lothus_Odontologia)
  --ano ANO                ano da campanha (padrão: ano atual)
  --out, -o OUT            onde gravar (padrão: clients/<cliente>/<campanha-slug>/contract.yaml)
  --force                  sobrescreve um contrato existente

exemplos:
  simplicio-video init lothus-odontologia Dia_Criancas --template saude-odontologia --nome "Lothus Odontologia"
  simplicio-video init wjr-informatica-games Black_Friday --template assistencia-tecnica-games --ano 2026 \
      --out clients/wjr-informatica-games/video-03/contract.yaml
```

## simplicio-video install

```text
usage: simplicio-video install [-h] [--check] [--python VERSÃO] [--with EXTRAS]

Cria <checkout>/.venv com uv (Python --python; padrão: o último usado, ou 3.12) e instala o pacote
em modo editável com os extras. Idempotente: sem mudança em Python, extras ou pyproject.toml, não faz nada.
--check mostra o plano sem criar nada e sai com 1 se houver mudança pendente. Não usa sudo.

options:
  -h, --help       show this help message and exit
  --check          mostra o que mudaria e não cria nada
  --python VERSÃO  versão do Python do .venv, ex.: 3.12 (padrão: a última usada, ou 3.12)
  --with EXTRAS    extras separados por vírgula, ex.: local-tts,mcp (padrão: os da última instalação)

exemplos:
  simplicio-video install --check
  simplicio-video install
  simplicio-video install --python 3.12 --with local-tts
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
backends (todos sem navegador, exceto colab):
  local      PADRÃO. Renderiza aqui (CPU; --gpu usa encoder de GPU do HyperFrames se houver).
             Referência de hash, sem custo (WJR 600 frames: 76,5 s em 8 núcleos).
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
  simplicio-video status --json clients/lothus-odontologia/video-01/contract.yaml
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
usage: simplicio-video update [-h] [--check] [--force]

Mostra os commits novos e o diff do CHANGELOG, aplica com git pull --ff-only, reexecuta install,
reconstrói web/ e roda doctor. Recusa árvore suja (--force deixa seguir; o git ainda protege arquivos
alterados). Imprime o commit anterior e o comando para voltar a ele (rollback).

options:
  -h, --help  show this help message and exit
  --check     mostra os commits novos e o diff do CHANGELOG; não altera nada
  --force     segue com árvore suja (não descarta alterações)

exemplos:
  simplicio-video update --check
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
  simplicio-video validate clients/wjr-informatica-games/video-01/contract.yaml
  simplicio-video validate contract.yaml --json      # relatório em JSON
  simplicio-video validate contract.yaml --need-lock # exige timing.lock.json (antes do render)
```

## simplicio-video voice

```text
usage: simplicio-video voice [-h] [--provider {file,local,gemini,voxcpm,openvoice,voicestudio,elevenlabs,xai}]
                             [--force]
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

exemplos:
  simplicio-video voice contract.yaml                    # provider do contrato (voz.provider)
  simplicio-video voice contract.yaml --provider file    # depois de baixar line-01..NN.wav do AI Studio
  simplicio-video voice contract.yaml --force vo2        # refaz só a vo2
```
