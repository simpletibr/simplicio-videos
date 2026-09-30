# ADR-0003: fluxo 100% script (voz Gemini por API, render remoto sem navegador, entrega no Drive, MCP)

- **Status:** aceito e implementado no CLI. Voz, Kaggle, colab-cli e Drive foram testados só com mocks, porque nenhuma conta ou chave foi usada. O Colab manual já foi medido de verdade pelo Wesley (seção 3).
- **Data:** 30/09/2026 (BRT)
- **Relaciona:** [ADR-0002](ADR-0002-cli-contrato-colab-creditos.md) (CLI, contrato, bundle Colab, créditos)

## Contexto

Até o ADR-0002 havia três passos manuais: gerar a voz no AI Studio, abrir o notebook do Colab no navegador e subir o MP4 no Drive. A meta agora é um comando só, que um agente consiga rodar sem navegador:

```bash
simplicio-video run clients/<slug>/<video>/contract.yaml --provider gemini --backend local|kaggle|colab-cli --publish
```

`run` = validate → voice → validate --need-lock → render → publish. Sem `--publish`, o publish roda em dry-run. O mesmo fluxo está exposto como servidor MCP (`simplicio-video mcp`, tools `video.init|validate|voice|render|publish|run|list`).

## 1. Opções avaliadas (preços lidos em 30/09/2026)

### Voz (TTS)

| Opção | Custo | Grátis? | Credencial | Esforço | Decisão |
|---|---|---|---|---|---|
| **Gemini API** `gemini-3.8-flash-tts`, Interactions API (padrão) ou `generateContent` (`voz.api: generate_content`) | tier grátis sem custo (o Google usa os dados para melhorar produtos); pago: US$ 0,50/1M tokens de entrada + US$ 9,00/1M de saída de áudio até 31/12/2026 (≈ US$ 0,002 por 10 s), depois US$ 1/US$ 18; Batch pela metade | **sim** (cota do tier grátis por projeto, não publicada; ver em AI Studio → Rate limits) | `GEMINI_API_KEY` | pronto | **implementado** (`voice.py`, retry em 429/5xx, cache por hash no `timing.lock.json`) |
| `gemini-3.8-flash-lite-tts` | saída US$ 6,00/1M (depois US$ 12) | sim | mesma | trocar `voz.modelo` | opcional |
| AI Studio manual (web) | grátis; o plano Google AI Pro vale **só na interface web**, não dá cota de API | sim | login no navegador | manual | continua como alternativa (`--provider external`) |
| ElevenLabs / xAI | pagos | não | chaves próprias | stubs | fora do escopo |

Fontes: [speech-generation](https://ai.google.dev/gemini-api/docs/speech-generation), [pricing](https://ai.google.dev/gemini-api/docs/pricing), [rate-limits](https://ai.google.dev/gemini-api/docs/rate-limits), [google-ai-plans](https://ai.google.dev/gemini-api/docs/google-ai-plans), [migrate-to-interactions](https://ai.google.dev/gemini-api/docs/migrate-to-interactions).

### Render

| Backend | Custo | Grátis? | vCPU / RAM | Credencial | Automação | Decisão |
|---|---|---|---|---|---|---|
| **local** (box / máquina do Wesley) | 0 | sim | box: 8 / 15 GB | nenhuma | total | **referência de hash** |
| **Kaggle** kernel (`--backend kaggle`) | 0 (~30 h GPU/semana, varia; sessões de 12 h) | sim | **4 / 29 GB** (T4 x2) | `KAGGLE_USERNAME` + token; telefone verificado para ter internet | total (dataset privado → kernel script `machine_shape: NvidiaTeslaT4` → poll → output) | **implementado**; melhor opção grátis por CPU |
| **Colab CLI** oficial (`--backend colab-cli`) | 0 no grátis (limites dinâmicos) / assinatura Pro | sim | **2 / ~12,7 GB** (grátis) | login OAuth único (`colab` cola o código) | total (new → upload → exec → download → stop) | **implementado** |
| Colab manual (`--backend colab`) | igual | sim | 2 / ~12,7 GB | navegador | manual | mantido; medido (seção 3) |
| Colab Enterprise | T4 US$ 0,42/h + US$ 0,07/h de gestão + VM/discos | não | n1-standard-4 = 4 | GCP com billing | API | só se já existir GCP pago |
| Modal | T4 ≈ US$ 0,59/h (US$ 0,000164/s); plano Starter com US$ 30/mês de crédito | crédito mensal | escolhe CPU à parte | token Modal | total, **imagem própria** | melhor candidato pago (container travado + cobrança por segundo) |
| RunPod | T4 ≈ US$ 0,12–0,25/h, sem crédito grátis | não | varia | API key | total, imagem própria | alternativa paga |
| Lightning AI | créditos únicos | uma vez | varia | conta | parcial | não |

Fontes: [Kaggle notebooks (specs)](https://www.kaggle.com/docs/notebooks), [kaggle-cli kernels](https://github.com/Kaggle/kaggle-cli/blob/main/docs/kernels.md) (+ [issue #821](https://github.com/Kaggle/kaggle-cli/issues/821): `machine_shape` no metadata), [google-colab-cli](https://github.com/googlecolab/google-colab-cli), [Colab pricing](https://cloud.google.com/colab/pricing), [Modal pricing](https://modal.com/pricing).

### Entrega no Drive

| Opção | Credencial | Observação | Decisão |
|---|---|---|---|
| **rclone** (`publish`) | client_id/secret OAuth **próprio** + token do `rclone config` (escopo `drive`) | o client_id compartilhado do rclone será aposentado em 2026; publicar o app como "In production" para o refresh token não expirar em 7 dias; headless via `rclone authorize "drive"` | **implementado**: nunca sobrescreve, é idempotente, link montado pelo ID (sem `rclone link`, não mexe em compartilhamento) |
| google-api-python-client + OAuth | mesmo client_id | mais código, mesma credencial | não |
| Service account | JSON da SA | não tem cota em My Drive (só Shared Drive/Workspace) | não |

Fonte: [rclone drive](https://rclone.org/drive/).

## 2. Decisão

1. **Voz:** Gemini API como padrão (`--provider gemini`), cache por hash de texto+voz+modelo. Com o mesmo lock, o render não chama TTS de novo.
2. **Render:** `local` continua a referência. `kaggle` e `colab-cli` para rodar grátis sem navegador. Para cobrar crédito de cliente, usar um backend pago por segundo (Modal/RunPod/VM) **com o container travado da seção 5**. O `usage` do manifest já registra backend, GPU, tempos e ambiente.
3. **Drive:** `publish` com rclone. Só roda com pedido explícito (flag `--publish` ou comando `publish`).
4. **MCP:** `simplicio-video mcp` (stdio), com os mesmos comandos em forma de tools.

## 3. Dado real: Colab T4 grátis contra local (WJR, 600 frames, `delivery`)

| Etapa | Colab T4 grátis | Local (box) |
|---|---|---|
| setup (Node, ffmpeg, Chrome) | 31,6 s | (já instalado) |
| captura + encode (streaming) | **420 s** (0,70 s/frame) | **65,3 s** |
| render total (`hyperframes render`) | 459,7 s | 76,5 s |
| master (loudnorm 2 passes + AAC) | 7,1 s | 2,1 s |
| `gpu_encode` | false (NVENC existia, mas não foi usado: bug, ver 4.3) | false (sem GPU) |
| Chrome | chrome-headless-shell 152.0.7977.30 | **o mesmo** 152.0.7977.30 (fixado pelo HyperFrames 0.8.97) |
| ffmpeg | o do Ubuntu do Colab (4.x provavelmente; agora vai para o `timings.json`) | 7.1.5-0+deb13u1 (Debian 13) |
| frames / áudio iguais ao local? | **não / não** | referência |

**Conclusão:** o gargalo é a captura do HTML pelo Chrome headless, que roda em CPU. A GPU do T4 praticamente não entra.

## 4. Por que o Colab foi 6× mais lento e o que fazer

### 4.1 vCPU por backend e workers

O HyperFrames escolhe os workers (um Chrome por worker, ~256 MB de RAM cada) assim: `max(1, núcleos − 2)`, limitado ainda por RAM, heap e frames. Com ≤ 8 GB de RAM ele entra em `low-memory-mode` (1 worker + screenshot).

| Máquina | vCPU | workers auto | Captura WJR |
|---|---|---|---|
| Colab grátis | 2 (1 núcleo físico com HT, Xeon ~2,0–2,2 GHz) | **1** | 420 s medidos |
| Kaggle T4 x2 | 4 | **2** | ~200 s estimados (metade do Colab se o clock for parecido; **medir**) |
| Colab Enterprise / VM n1-standard-4 | 4 | 2 | parecido com o Kaggle |
| Box local | 8 | 3 (a Lothus logou "3 workers") | 65,3 s |

Pôr mais workers que núcleos não acelera: cada worker é um Chrome inteiro disputando CPU. `SV_WORKERS=N` (repassado como `--workers N`; quando definido na hora de montar o bundle, vira o padrão do `render_bundle.sh`, porque Kaggle e colab-cli não recebem env arbitrário) serve para testar, por exemplo `SV_WORKERS=3` no Kaggle. O padrão continua auto. Os workers não mudam os pixels, só o paralelismo.

### 4.2 GPU no Chrome (`--browser-gpu`, ANGLE)

- O HyperFrames 0.8.97 tem `--browser-gpu` / `--no-browser-gpu`. No modo **auto** ele testa a GPU e, no Linux, liga `--use-gl=angle --use-angle=gl-egl --enable-gpu-rasterization`. No T4 isso **pode ter ligado a rasterização por hardware**, que gera pixels diferentes do SwiftShader (software) usado no local. É uma causa possível da divergência de frames.
- A GPU no Chrome acelera o raster e a composição, mas o BeginFrame, o readback e a codificação de cada frame continuam em CPU. O ganho em 2 vCPU é limitado e o determinismo acaba.
- **Implementado:** o `render_bundle.sh` usa por padrão `--no-browser-gpu` + `PRODUCER_FORCE_SCREENSHOT=false`. Isso mantém a captura BeginFrame com SwiftShader, os mesmos pixels do local. Com `--no-browser-gpu` sozinho o HyperFrames cai para captura por screenshot, 2,4× mais lenta no teste. O render local passou a usar as mesmas flags de forma explícita, e os hashes não mudaram: fixture `c7aee2ea…` e **WJR re-renderizada com MP4 byte a byte igual** (`19d8e6ca…`, 600 frames). `SV_BROWSER_GPU=1` é opt-in, só para medir velocidade.

### 4.3 Por que o NVENC não ativou (corrigido)

O script antigo fazia `set -euo pipefail` + `ffmpeg -encoders | grep -q h264_nvenc`. O `grep -q` sai no primeiro match, o ffmpeg ainda está escrevendo o resto da lista e toma SIGPIPE (código 141). Com `pipefail` o pipeline inteiro dá falso. Resultado: `gpu_encode=false` mesmo com o encoder presente. O bug foi reproduzido: 0/20 com um ffmpeg falso que lista `h264_nvenc` no meio.

**Correção** (`render.py → BUNDLE_SCRIPT`, testes em `tests/test_bundle_script.py`):
- a lista de encoders vai para uma variável (`ENC=$(ffmpeg -encoders || true)`) e o grep roda sobre ela, sem pipe;
- além de o encoder aparecer na lista, faz um **encode de teste real** (`-f lavfi -i color=... -c:v h264_nvenc -f null -`) e checa o `nvidia-smi`;
- `SV_GPU_ENCODE=auto|1|0` (CLI: `--gpu-encode`), com o motivo registrado em `gpu_encode_reason`.

**Ganho esperado:** o encode já corre em paralelo à captura (streaming). O NVENC tira do CPU só o libx264, que em 2 vCPU disputa com o Chrome. O ganho é modesto e **precisa ser medido**. Com NVENC os bytes do vídeo **sempre** diferem do local (outro encoder). Para comparar frames com o local, use `--gpu-encode 0`. O `master.sh` copia o vídeo (`-c:v copy`) e só recodifica o áudio.

### 4.4 O que ficou registrado em cada render remoto

`TIMINGS`, `timings.json` e o manifest (`timings_s.remote.env` + `tools`) guardam: nproc, RAM, workers efetivos, flag de GPU do browser, versão do Chrome, versão do ffmpeg, versão do Node, quantidade de fontes do sistema, GPU/driver, `gpu_encode` e o motivo. O `tools` do manifest remoto passa a mostrar as versões da máquina que renderizou (antes mostrava as do box que montou o bundle).

## 5. Divergência de frames e áudio: causas e como fixar o ambiente

### 5.1 Causas (em ordem de peso)

1. **Versão do ffmpeg/libx264. Comprovado.** Teste no box com o fixture mini: o mesmo bundle, trocando só o ffmpeg (7.1.5 do Debian → 7.0.2 estático), mudou o hash dos frames decodificados (`e5c6339f` → `685ce9ba`) e o hash do PCM do áudio (`19b45a51` → `ef03bd94`). Só o `master.sh` com o outro ffmpeg já muda o áudio (`19b45a51` → `c8e52a23`), porque o encoder AAC nativo e o `loudnorm` (que reamostra internamente para 192 kHz via swresample) mudam entre versões. No Colab a diferença de versão é bem maior (Ubuntu contra Debian 13).
2. **Raster de GPU no Chrome** (modo auto, 4.2). Agora está forçado para software.
3. **Fontes/fontconfig.** As fontes da marca vão no bundle e o HyperFrames tem cache próprio de fontes. As fontes do sistema só entram como fallback (glifos que faltam, emoji), mas a configuração de hinting/antialias do `/etc/fonts` da distro afeta o texto. O `system_fonts` agora é registrado.
4. **O Chrome não é causa:** a versão é a mesma nos dois (152.0.7977.30, fixada pelo HyperFrames). Node também está fixado (v22.23.3).

O `mix.wav` e os clipes de footage são gerados no **build local** (`build.mjs` usa ffmpeg: loudnorm, reencode dos slots) e vão prontos no bundle. Por isso o `inputs_sha256` também depende do ffmpeg local: no teste, o ffmpeg travado mudou o inputs de `8f4b2f7f` para `6c1a7d31`.

### 5.2 Implementado agora: ffmpeg travado em todo backend

- `SIMPLICIO_FFMPEG_DIR=<pasta com ffmpeg/ffprobe>` faz o CLI local (HyperFrames via `HYPERFRAMES_FFMPEG_PATH`/`HYPERFRAMES_FFPROBE_PATH`, `build.mjs` e `master.sh` via PATH) usar esse build.
- `SIMPLICIO_FFMPEG_URL` + `SIMPLICIO_FFMPEG_SHA256` gravam `toolchain` no `bundle.json`. O `remote_render.py` (Kaggle/colab-cli) baixa, **confere o sha256**, descompacta e põe esse ffmpeg na frente do PATH. Também dá para passar `SV_FFMPEG_URL`/`SV_FFMPEG_SHA256` direto.
- **Verificado no box:** render local com o ffmpeg estático 7.0.2 contra `remote_render.py` baixando o mesmo tarball pelo `bundle.json` resultou em **MP4 byte a byte igual** (`999cfc97…`). Sem o pin, o `remote_render.py` também bate byte a byte com o local quando o ffmpeg é o mesmo (`c7aee2ea…`).

### 5.3 Proposta: toolchain de referência único

1. **Escolher um build estático do ffmpeg e hospedá-lo nós mesmos** como asset de release do repositório, com sha256. URLs de builds de terceiros do tipo "latest/release" mudam de conteúdo. Recomendado: BtbN FFmpeg-Builds `linux64-gpl` da série n7.1 (traz libx264 e suporte a NVENC). O johnvansickle usado no teste não tem NVENC.
2. **Migrar a referência local para esse build** (`SIMPLICIO_FFMPEG_DIR`). Isso muda os hashes uma vez: re-renderizar WJR e Lothus e guardar os manifests antigos como histórico. A prova "byte a byte igual ao projeto npm" do ADR-0002 fica atrelada ao toolchain antigo (ffmpeg 7.1.5 do Debian).
3. **Container para backends pagos e para o local** (`docker/render.Dockerfile`, a criar e validar):
   - `FROM debian:trixie-<data>@sha256:<digest>` + `apt` apontando para `snapshot.debian.org/archive/debian/<data>` (pacotes congelados);
   - Node `v22.23.3` (tarball oficial + sha256), `hyperframes@0.8.97` instalado no build da imagem (sem `npx` no runtime), `chrome-headless-shell@152.0.7977.30` via `@puppeteer/browsers` na imagem;
   - o mesmo tarball de ffmpeg do item 1, com `HYPERFRAMES_FFMPEG_PATH`;
   - fontes: só as do bundle + um conjunto fixo (`fonts-liberation`, `fonts-noto-color-emoji` da snapshot) e um `fonts.conf` fixo;
   - roda em Modal/RunPod/VM/local com `docker run`. O Docker oficial do HyperFrames **não** serve assim, porque usa `chrome-headless-shell@stable` e o ffmpeg do bookworm sem trava.
4. **Kaggle/Colab** não rodam Docker. Neles o `remote_render.py` já fixa Node (tarball), Chrome (versão do HyperFrames) e ffmpeg (item 1). O que sobra de variação é o fontconfig e a libc da distro. Para aceitar um render remoto como "igual", compare `video_frames_sha256`/`audio_pcm_sha256` com o `reference_local` que já vai no `bundle.json`.
5. **Opcional:** gravar o hash dos frames capturados antes do encode (PNG/raw). Isso separa "Chrome diferente" de "encoder diferente" quando algo divergir.

## 6. Credenciais que o Wesley precisa fornecer (nenhuma foi usada até agora)

| Para | O quê | Onde |
|---|---|---|
| Voz | `GEMINI_API_KEY` | aistudio.google.com/apikey (tier grátis serve; billing opcional, pré-pago mínimo de US$ 5 no Tier 1) |
| Kaggle | `KAGGLE_USERNAME` + token (`KAGGLE_API_TOKEN` ou `~/.kaggle/access_token`; o `kaggle.json` legado também funciona) + telefone verificado | kaggle.com/settings/api → Generate New Token |
| Colab CLI | `pip install google-colab-cli` + login único (`colab` mostra a URL, o código é colado de volta) | conta Google do Colab |
| Drive | client_id/secret OAuth próprio (projeto GCP grátis, Drive API habilitada, tela de consentimento External publicada "In production") + `rclone config` criando o remote `gdrive` (escopo `drive`; token via `rclone authorize "drive"` numa máquina com navegador) | console.cloud.google.com |
| MCP | `pip install -e .[mcp]` | local |

## Consequências

- Vídeo novo = contrato + `run`, sem navegador em nenhuma etapa.
- Renders remotos passam a ser comparáveis com o local **se** o toolchain for o mesmo. O manifest mostra exatamente o que mudou quando não for.
- Colab grátis serve para teste, não para escala: 2 vCPU = 1 worker. Kaggle (4 vCPU) é a opção grátis mais rápida. Para clientes pagantes, CPU importa mais que GPU: uma VM de 8 vCPU sem GPU renderiza mais rápido que um T4 com 2 vCPU.
