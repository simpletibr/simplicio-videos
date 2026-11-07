# Variáveis de ambiente

> Gerado por `scripts/gen_reference.py` (leitura estática com `ast` em `src/simplicio_video/`). Não edite à mão: rode `make regen`.

Lista só os nomes escritos literalmente no código. Variáveis montadas em tempo de execução (por exemplo `SIMPLICIO_<FERRAMENTA>_REF`) não aparecem aqui.

| Variável | Para quê | Onde o código lê ou define |
|---|---|---|
| `AUDIO8_TTS_BIN` | (sem descrição na tabela de gen_reference.py) | `src/simplicio_video/voice_clone.py:88` |
| `BACKLOT_PORT` | Porta do board (Backlot) do OpenMontage; o `montage open` e o `montage serve` a repassam ao upstream. | `src/simplicio_video/montage.py:337` |
| `CORS_ALLOWED_ORIGINS` | (sem descrição na tabela de gen_reference.py) | `src/simplicio_video/moneyprinter.py:447` |
| `GEMINI_API_KEY` | Chave da API Gemini (TTS, provider `gemini`; adaptador `gemini` do `swap`). Só no ambiente; nunca no repo. | `src/simplicio_video/voice.py:215` |
| `GH_TOKEN` | Token do GitHub que o `update` manda só para `api.github.com` ao ler a última release (um redirect para outro host tira o cabeçalho). Só no ambiente. | `src/simplicio_video/commands/update.py:215` |
| `GITHUB_TOKEN` | O mesmo que `GH_TOKEN`, quando ele não está definido. Só vai para `api.github.com`. | `src/simplicio_video/commands/update.py:215` |
| `HYPERFRAMES_BROWSER_PATH` | Chrome headless que o HyperFrames usa na captura. Definido pelo render remoto. | `src/simplicio_video/engine/remote_render.py:155` |
| `HYPERFRAMES_FFMPEG_PATH` | ffmpeg que o HyperFrames usa. Definido pelo render remoto. | `src/simplicio_video/engine/remote_render.py:179` |
| `HYPERFRAMES_FFPROBE_PATH` | ffprobe que o HyperFrames usa. Definido pelo render remoto. | `src/simplicio_video/engine/remote_render.py:182` |
| `INSTAGRAM_DIR` | Checkout do instagram-agent-skill (alternativa a `SIMPLICIO_TOOLS_DIR/instagram`). O `instagram run` avisa quando ele está em uso e confere o sha256 de cada script do mesmo jeito. | `src/simplicio_video/instagram.py:231`<br>`src/simplicio_video/instagram.py:232`<br>`src/simplicio_video/instagram.py:237`<br>`src/simplicio_video/instagram.py:239` |
| `KAGGLE_CONFIG_DIR` | Pasta do `kaggle.json` (padrão: `~/.kaggle`). | `src/simplicio_video/remote.py:72` |
| `KAGGLE_USERNAME` | Usuário do Kaggle para o render remoto (sem ele, lê o `kaggle.json`). | `src/simplicio_video/remote.py:70`<br>`src/simplicio_video/remote.py:71` |
| `KOKORO_DIR` | Pasta dos modelos do Kokoro (TTS local; padrão `~/.local/share/simplicio-tts`). | `src/simplicio_video/voice.py:143` |
| `MATCHCUT_DATA_DIR` | (sem descrição na tabela de gen_reference.py) | `src/simplicio_video/matchcut.py:416` |
| `MATCHCUT_DIR` | Checkout do match-cut (alternativa a `SIMPLICIO_TOOLS_DIR/matchcut`). | `src/simplicio_video/matchcut.py:147`<br>`src/simplicio_video/matchcut.py:148`<br>`src/simplicio_video/matchcut.py:153`<br>`src/simplicio_video/matchcut.py:155` |
| `MATCHCUT_MEM_GIB` | (sem descrição na tabela de gen_reference.py) | `src/simplicio_video/matchcut.py:973` |
| `MATCHCUT_PYTHON` | (sem descrição na tabela de gen_reference.py) | `src/simplicio_video/matchcut.py:466` |
| `MONEYPRINTER_DATA_DIR` | Pasta de dados da trilha MoneyPrinterTurbo: venv isolado e storage com os vídeos gerados (padrão: `~/.simplicio-video/moneyprinter-data`, fora do checkout). | `src/simplicio_video/moneyprinter.py:106` |
| `MONEYPRINTER_DIR` | Checkout do MoneyPrinterTurbo (alternativa a `SIMPLICIO_TOOLS_DIR/moneyprinter`). | `src/simplicio_video/moneyprinter.py:122`<br>`src/simplicio_video/moneyprinter.py:123`<br>`src/simplicio_video/moneyprinter.py:128`<br>`src/simplicio_video/moneyprinter.py:130` |
| `OMNIVOICE_API_KEY` | (sem descrição na tabela de gen_reference.py) | `src/simplicio_video/voicestudio.py:249` |
| `OMNIVOICE_PORT` | (sem descrição na tabela de gen_reference.py) | `src/simplicio_video/voicestudio.py:109` |
| `OMNIVOICE_URL` | (sem descrição na tabela de gen_reference.py) | `src/simplicio_video/voicestudio.py:106` |
| `OPENCUT_DIR` | Pasta do OpenCut, lida pelo próprio editor (trilha `opencut`). | `src/simplicio_video/opencut.py:69` |
| `OPENMONTAGE_DATA_DIR` | Pasta do venv do OpenMontage (padrão: `~/.simplicio-video/openmontage-data`); um caminho relativo vira absoluto a partir da pasta atual, com aviso. | `src/simplicio_video/montage.py:189` |
| `OPENMONTAGE_DIR` | Pasta do OpenMontage (trilha `montage`). Também lida pelo OpenMontage. | `src/simplicio_video/montage.py:44`<br>`src/simplicio_video/montage.py:63`<br>`src/simplicio_video/montage.py:64`<br>`src/simplicio_video/montage.py:69`<br>`src/simplicio_video/montage.py:71` |
| `OPENVERSE_LIBRARY_DIR` | Pasta da biblioteca do Openverse: `index.json`, `files/<sha256>`, `cache/` e `sheets/` (padrão: `~/.simplicio-video/openverse-library`). | `src/simplicio_video/openverse.py:193` |
| `OPENVOICE_CHECKPOINTS` | Pasta dos checkpoints do OpenVoice (provider `openvoice`). | `src/simplicio_video/voice_clone.py:52` |
| `OPENVOICE_PY` | Python com o OpenVoice instalado (provider `openvoice`). | `src/simplicio_video/voice_clone.py:51` |
| `PATH` | Lista de pastas de executáveis do sistema. Lida, não configurada pelo produto. O `doctor` procura `simplicio`, `node` e `ffmpeg` só nas pastas absolutas dela, nunca no diretório atual. | `src/simplicio_video/commands/doctor.py:146`<br>`src/simplicio_video/engine/remote_render.py:178`<br>`src/simplicio_video/tools.py:455` |
| `PATHEXT` | Extensões executáveis do Windows (`.EXE;.CMD`...). Lida só no Windows, ao procurar `simplicio`, `node`, `ffmpeg` e `npm` no PATH. | `src/simplicio_video/hostos.py:249` |
| `PIP_BREAK_SYSTEM_PACKAGES` | `1` autoriza o pip a mexer no Python do sistema (PEP 668). O `update` de um pacote instalado por pip respeita: sem ele, um Python gerenciado pelo sistema é recusado com exit 2. | `src/simplicio_video/commands/update.py:77` |
| `PYTHONPATH` | (sem descrição na tabela de gen_reference.py) | `src/simplicio_video/moneyprinter.py:1363`<br>`src/simplicio_video/moneyprinter.py:473`<br>`src/simplicio_video/moneyprinter.py:862` |
| `REA_VIDEO_DATA_DIR` | Pasta de dados da trilha rea-video: o venv próprio e o estado do upstream (padrão: `~/.simplicio-video/rea-video-data`, fora do checkout). | `src/simplicio_video/rea_video.py:69` |
| `REA_VIDEO_DIR` | Checkout do rea-video (alternativa a `SIMPLICIO_TOOLS_DIR/rea_video`). | `src/simplicio_video/rea_video.py:90`<br>`src/simplicio_video/rea_video.py:91`<br>`src/simplicio_video/rea_video.py:96`<br>`src/simplicio_video/rea_video.py:98` |
| `REA_VIDEO_PYTHON` | Interpretador que cria o venv do rea-video no `setup`, por exemplo `python3.11` para o extra de OCR. Um venv que já existe é mantido. | `src/simplicio_video/rea_video.py:161` |
| `SIMPLICIO_BUSCA_MAX_DIA` | Teto de chamadas ao TinyFish por dia UTC no `busca` (padrão 20; máximo 1000). `--max-chamadas-dia` vence. O MCP e o plugin só usam este valor ou o padrão. | `src/simplicio_video/busca.py:365` |
| `SIMPLICIO_COLAB_AUTH` | Modo de autenticação do Colab CLI, repassado a `--auth`. | `src/simplicio_video/remote.py:183`<br>`src/simplicio_video/remote.py:184` |
| `SIMPLICIO_DRIVE_REMOTE` | Nome do remote do rclone para o Drive (padrão: `gdrive`). | `src/simplicio_video/publish.py:108` |
| `SIMPLICIO_FFMPEG_DIR` | Pasta do ffmpeg/ffprobe fixados (render local e `swap`). | `src/simplicio_video/mediaio.py:25`<br>`src/simplicio_video/openverse_sheet.py:30`<br>`src/simplicio_video/swap.py:106` |
| `SIMPLICIO_FFMPEG_SHA256` | SHA-256 esperado do ffmpeg estático de `SIMPLICIO_FFMPEG_URL`. | `src/simplicio_video/render.py:259` |
| `SIMPLICIO_FFMPEG_URL` | URL de um ffmpeg estático fixado, baixado e verificado pelos renders remotos. | `src/simplicio_video/render.py:257`<br>`src/simplicio_video/render.py:258` |
| `SIMPLICIO_GEMINI_BASE` | Base da API Gemini (padrão: a oficial). Para proxies e testes. | `src/simplicio_video/swap_providers/gemini.py:60`<br>`src/simplicio_video/voice.py:156` |
| `SIMPLICIO_JOBS_GRACE_S` | Tolerância, em segundos, entre o SIGINT e o SIGKILL ao cancelar uma tarefa de `jobs` (padrão 15). | `src/simplicio_video/jobs.py:778` |
| `SIMPLICIO_JOB_ORIGIN` | Rótulo de procedência de uma tarefa de `jobs`: `terminal` ou `mcp`. O runner (`jobs.py`) grava no ambiente do processo filho a origem de quem submeteu a tarefa, e a trilha `video-to-skill` a copia para o `PASTA.extract.json` (`submitted_via`). Não é controle de acesso: não autoriza nem bloqueia nada, só registra de onde veio o pedido. | `src/simplicio_video/video_to_skill.py:1328` |
| `SIMPLICIO_MCP` | (sem descrição na tabela de gen_reference.py) | `src/simplicio_video/childio.py:97`<br>`src/simplicio_video/mcp_server.py:1076` |
| `SIMPLICIO_MONTAGE_TIMEOUT` | (sem descrição na tabela de gen_reference.py) | `src/simplicio_video/montage.py:778` |
| `SIMPLICIO_OFFLINE` | `1` bloqueia rede nas checagens offline (inclui a consulta da última release no `update` e no `doctor --online`). O gate (`make check`) roda com `1`. | `src/simplicio_video/busca.py:602`<br>`src/simplicio_video/commands/update.py:63`<br>`src/simplicio_video/instagram.py:148`<br>`src/simplicio_video/montage.py:36`<br>`src/simplicio_video/openverse.py:783`<br>`src/simplicio_video/swap_providers/http.py:45`<br>`src/simplicio_video/tools_update.py:67`<br>`src/simplicio_video/toonflow.py:59` |
| `SIMPLICIO_OPENMONTAGE_DIR` | Pasta do OpenMontage (alternativa a `OPENMONTAGE_DIR`). | `src/simplicio_video/montage.py:44` |
| `SIMPLICIO_RCLONE_BIN` | Caminho do binário do rclone (padrão: o `rclone` do PATH). | `src/simplicio_video/publish.py:116` |
| `SIMPLICIO_STT_PY` | Python com o motor de transcrição (STT). Padrão: o Python do TTS local. | `src/simplicio_video/words.py:36` |
| `SIMPLICIO_TOOLS_DIR` | Pasta das ferramentas opcionais instaladas (padrão: `~/.simplicio-video/tools`). | `src/simplicio_video/montage.py:47`<br>`src/simplicio_video/tools.py:225` |
| `SIMPLICIO_TTS_PY` | Python com kokoro-onnx e soundfile (TTS local; padrão: `~/.local/share/simplicio-tts/cbvenv`). | `src/simplicio_video/doctor_trilhas.py:535`<br>`src/simplicio_video/paths.py:76` |
| `SIMPLICIO_VIDEO_DATA` | Pasta de dados do simplicio-video (padrão: `~/.simplicio-video`). Lida pelas trilhas `montage`, `toonflow`, `moneyprinter` e `rea-video`, pelo `jobs` (estado das tarefas em `jobs/`), pelo `busca` (cache, contador e registro em `busca/`) e pelo `update` (`update-check.json`, que o `doctor` lê sem rede). | `src/simplicio_video/busca.py:288`<br>`src/simplicio_video/commands/update.py:312`<br>`src/simplicio_video/jobs.py:75`<br>`src/simplicio_video/matchcut.py:419`<br>`src/simplicio_video/moneyprinter.py:109`<br>`src/simplicio_video/montage.py:197`<br>`src/simplicio_video/montage.py:49`<br>`src/simplicio_video/openverse.py:196`<br>`src/simplicio_video/rea_video.py:72`<br>`src/simplicio_video/tools_lock.py:48`<br>`src/simplicio_video/toonflow.py:73`<br>`src/simplicio_video/trilha_base.py:46` |
| `SIMPLICIO_VIDEO_HOME` | Checkout do simplicio-video (dados do motor e raiz do repo). Sem ela, o pacote procura o checkout. | `src/simplicio_video/paths.py:31`<br>`src/simplicio_video/paths.py:64` |
| `SIMPLICIO_WORKSPACE` | Pasta do workspace da fábrica (padrão: `~/.simplicio-video/workspaces/default`). | `src/simplicio_video/paths.py:48` |
| `SV_BROWSER_GPU` | `1` liga a GPU do navegador na captura do render. | `src/simplicio_video/render.py:191`<br>`src/simplicio_video/render.py:94` |
| `SV_BUNDLE` | Caminho do bundle a renderizar no render remoto. | `src/simplicio_video/engine/remote_render.py:190` |
| `SV_FFMPEG_SHA256` | SHA-256 do ffmpeg estático do render remoto (padrão: o fixado no bundle). | `src/simplicio_video/engine/remote_render.py:220` |
| `SV_FFMPEG_URL` | URL do ffmpeg estático do render remoto (padrão: o fixado no bundle). | `src/simplicio_video/engine/remote_render.py:219` |
| `SV_OUT` | Pasta de saída do render remoto (padrão: `/kaggle/working` ou `sv-out`). | `src/simplicio_video/engine/remote_render.py:201` |
| `SV_QUALITY` | Qualidade do render remoto: `draft`, `looks` ou `delivery`. | `src/simplicio_video/engine/remote_render.py:223` |
| `SV_SKIP_SETUP` | `1` pula a instalação de dependências do render remoto. | `src/simplicio_video/engine/remote_render.py:205` |
| `SV_WORKERS` | Workers do HyperFrames no render: `auto` (padrão) ou um inteiro. | `src/simplicio_video/render.py:192`<br>`src/simplicio_video/render.py:91` |
| `TINYFISH_API_KEY` | Chave da API do TinyFish, lida só pelo binário `tinyfish` (que também a guarda em `~/.tinyfish/config.json`). O `busca` a repassa ao binário se estiver no ambiente e nunca a lê, imprime nem grava; nunca em argumento. | `src/simplicio_video/busca.py:1144`<br>`src/simplicio_video/busca.py:185` |
| `TOONFLOW_DATA_DIR` | Pasta de dados do servidor Toonflow (padrão: `~/.simplicio-video/toonflow-data`, fora do checkout). | `src/simplicio_video/toonflow.py:70` |
| `TOONFLOW_DIR` | Checkout do Toonflow (alternativa a `SIMPLICIO_TOOLS_DIR/toonflow`). | `src/simplicio_video/toonflow.py:81`<br>`src/simplicio_video/toonflow.py:82`<br>`src/simplicio_video/toonflow.py:87`<br>`src/simplicio_video/toonflow.py:89` |
| `VIDEO_TO_SKILL_DIR` | Checkout do video-to-skill (alternativa a `SIMPLICIO_TOOLS_DIR/video_to_skill`). O binário `vts-extract` fica à parte, em `SIMPLICIO_TOOLS_DIR/video-to-skill-bin`. | `src/simplicio_video/video_to_skill.py:1101`<br>`src/simplicio_video/video_to_skill.py:1102`<br>`src/simplicio_video/video_to_skill.py:1107`<br>`src/simplicio_video/video_to_skill.py:1109` |
| `VIDEO_USE_DIR` | Checkout do video-use (trilha `edit`), mantido pelo setup.sh em data/tools/video-use; o `update` segue esta pasta (padrão `~/.cache/simplicio/video-use`). | `src/simplicio_video/tools_update.py:207` |
| `VOICESTUDIO_API_KEY` | Chave opcional da API local do VoiceStudio (provider `voicestudio`). | `src/simplicio_video/voice_clone.py:72`<br>`src/simplicio_video/voice_clone.py:73`<br>`src/simplicio_video/voicestudio.py:249` |
| `VOICESTUDIO_PORT` | (sem descrição na tabela de gen_reference.py) | `src/simplicio_video/voicestudio.py:109` |
| `VOICESTUDIO_URL` | URL da API local do VoiceStudio (padrão: `http://localhost:3900`). | `src/simplicio_video/voice_clone.py:65`<br>`src/simplicio_video/voicestudio.py:106` |
| `VOXCPM_BIN` | Executável do VoxCPM (provider `openvoice`, clonagem com clipe de referência). | `src/simplicio_video/voice_clone.py:26` |
| `VOXCPM_DEVICE` | (sem descrição na tabela de gen_reference.py) | `src/simplicio_video/voice_clone.py:42`<br>`src/simplicio_video/voice_clone.py:43` |
| `VTS_DATA_DIR` | Pasta de dados do `vts-extract` (ffmpeg, yt-dlp e modelos que o `check --fix --yes` do upstream baixa; padrão: a pasta de dados da plataforma, em `video-to-skill`). O motor repassa a variável ao extrator, mas nunca roda o `check --fix --yes`. | `src/simplicio_video/video_to_skill.py:1227` |
