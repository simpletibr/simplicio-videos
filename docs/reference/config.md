# Variáveis de ambiente

> Gerado por `scripts/gen_reference.py` (leitura estática com `ast` em `src/simplicio_video/`). Não edite à mão: rode `make regen`.

Lista só os nomes escritos literalmente no código. Variáveis montadas em tempo de execução (por exemplo `SIMPLICIO_<FERRAMENTA>_REF`) não aparecem aqui.

| Variável | Para quê | Onde o código lê ou define |
|---|---|---|
| `ABACATEPAY_API_KEY` | Chave da API AbacatePay (cobrança Pix da trilha de venda). Só no ambiente. | `src/simplicio_video/venda.py:119` |
| `ABACATEPAY_WEBHOOK_SECRET` | Segredo que valida o webhook de pagamento da trilha de venda. | `src/simplicio_video/venda.py:168`<br>`src/simplicio_video/venda.py:196` |
| `CORS_ALLOWED_ORIGINS` | (sem descrição na tabela de gen_reference.py) | `src/simplicio_video/moneyprinter.py:387` |
| `GEMINI_API_KEY` | Chave da API Gemini (TTS, provider `gemini`; adaptador `gemini` do `swap`). Só no ambiente; nunca no repo. | `src/simplicio_video/prospect.py:811`<br>`src/simplicio_video/voice.py:208` |
| `HYPERFRAMES_BROWSER_PATH` | Chrome headless que o HyperFrames usa na captura. Definido pelo render remoto. | `src/simplicio_video/engine/remote_render.py:155` |
| `HYPERFRAMES_FFMPEG_PATH` | ffmpeg que o HyperFrames usa. Definido pelo render remoto. | `src/simplicio_video/engine/remote_render.py:179` |
| `HYPERFRAMES_FFPROBE_PATH` | ffprobe que o HyperFrames usa. Definido pelo render remoto. | `src/simplicio_video/engine/remote_render.py:182` |
| `KAGGLE_CONFIG_DIR` | Pasta do `kaggle.json` (padrão: `~/.kaggle`). | `src/simplicio_video/remote.py:72` |
| `KAGGLE_USERNAME` | Usuário do Kaggle para o render remoto (sem ele, lê o `kaggle.json`). | `src/simplicio_video/remote.py:70`<br>`src/simplicio_video/remote.py:71` |
| `KOKORO_DIR` | Pasta dos modelos do Kokoro (TTS local; padrão `~/.local/share/simplicio-tts`). | `src/simplicio_video/voice.py:136` |
| `MONEYPRINTER_DATA_DIR` | Pasta de dados da trilha MoneyPrinterTurbo: venv isolado e storage com os vídeos gerados (padrão: `~/.simplicio-video/moneyprinter-data`, fora do checkout). | `src/simplicio_video/moneyprinter.py:74` |
| `MONEYPRINTER_DIR` | Checkout do MoneyPrinterTurbo (alternativa a `SIMPLICIO_TOOLS_DIR/moneyprinter`). | `src/simplicio_video/moneyprinter.py:90`<br>`src/simplicio_video/moneyprinter.py:91`<br>`src/simplicio_video/moneyprinter.py:96`<br>`src/simplicio_video/moneyprinter.py:98` |
| `OPENCUT_DIR` | Pasta do OpenCut, lida pelo próprio editor (trilha `opencut`). | `src/simplicio_video/opencut.py:29` |
| `OPENMONTAGE_DIR` | Pasta do OpenMontage (trilha `montage`). Também lida pelo OpenMontage. | `src/simplicio_video/montage.py:32`<br>`src/simplicio_video/montage.py:51`<br>`src/simplicio_video/montage.py:52`<br>`src/simplicio_video/montage.py:57`<br>`src/simplicio_video/montage.py:59` |
| `OPENVERSE_LIBRARY_DIR` | Pasta da biblioteca do Openverse: `index.json`, `files/<sha256>`, `cache/` e `sheets/` (padrão: `~/.simplicio-video/openverse-library`). | `src/simplicio_video/openverse.py:184` |
| `OPENVOICE_CHECKPOINTS` | Pasta dos checkpoints do OpenVoice (provider `openvoice`). | `src/simplicio_video/voice_clone.py:50` |
| `OPENVOICE_PY` | Python com o OpenVoice instalado (provider `openvoice`). | `src/simplicio_video/voice_clone.py:49` |
| `PATH` | Lista de pastas de executáveis do sistema. Lida, não configurada pelo produto. | `src/simplicio_video/engine/remote_render.py:178` |
| `PYTHONPATH` | (sem descrição na tabela de gen_reference.py) | `src/simplicio_video/moneyprinter.py:412` |
| `SIMPLICIO_BUSCA_MAX_DIA` | Teto de chamadas ao TinyFish por dia UTC no `busca` (padrão 20; máximo 1000). `--max-chamadas-dia` vence. O MCP e o plugin só usam este valor ou o padrão. | `src/simplicio_video/busca.py:342` |
| `SIMPLICIO_COLAB_AUTH` | Modo de autenticação do Colab CLI, repassado a `--auth`. | `src/simplicio_video/remote.py:183`<br>`src/simplicio_video/remote.py:184` |
| `SIMPLICIO_DRIVE_DESTINO` | JSON com `caminho` e `arquivo` da entrega no Drive da trilha de venda. | `src/simplicio_video/venda.py:239` |
| `SIMPLICIO_DRIVE_REMOTE` | Nome do remote do rclone para o Drive (padrão: `gdrive`). | `src/simplicio_video/publish.py:108` |
| `SIMPLICIO_FFMPEG_DIR` | Pasta do ffmpeg/ffprobe fixados (render local e `swap`). | `src/simplicio_video/openverse_sheet.py:30`<br>`src/simplicio_video/swap.py:106` |
| `SIMPLICIO_FFMPEG_SHA256` | SHA-256 esperado do ffmpeg estático de `SIMPLICIO_FFMPEG_URL`. | `src/simplicio_video/render.py:246` |
| `SIMPLICIO_FFMPEG_URL` | URL de um ffmpeg estático fixado, baixado e verificado pelos renders remotos. | `src/simplicio_video/render.py:244`<br>`src/simplicio_video/render.py:245` |
| `SIMPLICIO_GEMINI_BASE` | Base da API Gemini (padrão: a oficial). Para proxies e testes. | `src/simplicio_video/swap_providers/gemini.py:60`<br>`src/simplicio_video/voice.py:149` |
| `SIMPLICIO_JOBS_GRACE_S` | Tolerância, em segundos, entre o SIGINT e o SIGKILL ao cancelar uma tarefa de `jobs` (padrão 15). | `src/simplicio_video/jobs.py:576` |
| `SIMPLICIO_OFFLINE` | `1` bloqueia rede nas checagens offline. O gate (`make check`) roda com `1`. | `src/simplicio_video/busca.py:545`<br>`src/simplicio_video/montage.py:24`<br>`src/simplicio_video/openverse.py:774`<br>`src/simplicio_video/swap_providers/http.py:45`<br>`src/simplicio_video/toonflow.py:43` |
| `SIMPLICIO_OPENMONTAGE_DIR` | Pasta do OpenMontage (alternativa a `OPENMONTAGE_DIR`). | `src/simplicio_video/montage.py:32` |
| `SIMPLICIO_RCLONE_BIN` | Caminho do binário do rclone (padrão: o `rclone` do PATH). | `src/simplicio_video/publish.py:116` |
| `SIMPLICIO_STT_PY` | Python com o motor de transcrição (STT). Padrão: o Python do TTS local. | `src/simplicio_video/words.py:36` |
| `SIMPLICIO_TOOLS_DIR` | Pasta das ferramentas opcionais instaladas (padrão: `~/.simplicio-video/tools`). | `src/simplicio_video/montage.py:35`<br>`src/simplicio_video/tools.py:86` |
| `SIMPLICIO_TTS_PY` | Python com kokoro-onnx e soundfile (TTS local; padrão: `~/.local/share/simplicio-tts/cbvenv`). | `src/simplicio_video/paths.py:55` |
| `SIMPLICIO_VIDEO_DATA` | Pasta de dados do simplicio-video (padrão: `~/.simplicio-video`). Lida pelas trilhas `montage`, `toonflow` e `moneyprinter`, pelo `jobs` (estado das tarefas em `jobs/`) e pelo `busca` (cache, contador e registro em `busca/`). | `src/simplicio_video/busca.py:268`<br>`src/simplicio_video/jobs.py:68`<br>`src/simplicio_video/moneyprinter.py:77`<br>`src/simplicio_video/montage.py:37`<br>`src/simplicio_video/openverse.py:187`<br>`src/simplicio_video/toonflow.py:57` |
| `SIMPLICIO_VIDEO_HOME` | Checkout do simplicio-video (dados do motor e raiz do repo). Sem ela, o pacote procura o checkout. | `src/simplicio_video/paths.py:29`<br>`src/simplicio_video/paths.py:43` |
| `SIMPLICIO_VOICE_REGEN` | Tomadas novas por fala antes de encurtar o texto (padrão: 3). | `src/simplicio_video/prospect.py:867` |
| `SIMPLICIO_WORKSPACE` | Pasta do workspace da fábrica (padrão: `~/.simplicio-video/workspaces/default`). | `src/simplicio_video/commands/setup.py:32` |
| `SV_BROWSER_GPU` | `1` liga a GPU do navegador na captura do render. | `src/simplicio_video/render.py:185`<br>`src/simplicio_video/render.py:94` |
| `SV_BUNDLE` | Caminho do bundle a renderizar no render remoto. | `src/simplicio_video/engine/remote_render.py:190` |
| `SV_FFMPEG_SHA256` | SHA-256 do ffmpeg estático do render remoto (padrão: o fixado no bundle). | `src/simplicio_video/engine/remote_render.py:220` |
| `SV_FFMPEG_URL` | URL do ffmpeg estático do render remoto (padrão: o fixado no bundle). | `src/simplicio_video/engine/remote_render.py:219` |
| `SV_OUT` | Pasta de saída do render remoto (padrão: `/kaggle/working` ou `sv-out`). | `src/simplicio_video/engine/remote_render.py:201` |
| `SV_QUALITY` | Qualidade do render remoto: `draft`, `looks` ou `delivery`. | `src/simplicio_video/engine/remote_render.py:223` |
| `SV_SKIP_SETUP` | `1` pula a instalação de dependências do render remoto. | `src/simplicio_video/engine/remote_render.py:205` |
| `SV_WORKERS` | Workers do HyperFrames no render: `auto` (padrão) ou um inteiro. | `src/simplicio_video/render.py:186`<br>`src/simplicio_video/render.py:91` |
| `TINYFISH_API_KEY` | Chave da API do TinyFish, lida só pelo binário `tinyfish` (que também a guarda em `~/.tinyfish/config.json`). O `busca` a repassa ao binário se estiver no ambiente e nunca a lê, imprime nem grava; nunca em argumento. | `src/simplicio_video/busca.py:165`<br>`src/simplicio_video/busca.py:995` |
| `TOONFLOW_DATA_DIR` | Pasta de dados do servidor Toonflow (padrão: `~/.simplicio-video/toonflow-data`, fora do checkout). | `src/simplicio_video/toonflow.py:54` |
| `TOONFLOW_DIR` | Checkout do Toonflow (alternativa a `SIMPLICIO_TOOLS_DIR/toonflow`). | `src/simplicio_video/toonflow.py:65`<br>`src/simplicio_video/toonflow.py:66`<br>`src/simplicio_video/toonflow.py:71`<br>`src/simplicio_video/toonflow.py:73` |
| `VOICESTUDIO_API_KEY` | Chave opcional da API local do VoiceStudio (provider `voicestudio`). | `src/simplicio_video/voice_clone.py:70`<br>`src/simplicio_video/voice_clone.py:71` |
| `VOICESTUDIO_URL` | URL da API local do VoiceStudio (padrão: `http://localhost:3900`). | `src/simplicio_video/voice_clone.py:63` |
| `VOXCPM_BIN` | Executável do VoxCPM (provider `openvoice`, clonagem com clipe de referência). | `src/simplicio_video/voice_clone.py:27` |
