---
title: Pacote de operação (install, update, doctor, setup)
summary: O que cada subcomando faz, o que o doctor checa, por que a falta de GEMINI_API_KEY é aviso e os limites até as #32 e #34.
commands: ./install.sh, simplicio-video install, simplicio-video update, simplicio-video doctor, simplicio-video setup, simplicio-video login, simplicio-video logout, simplicio-video auth status, python scripts/smoke_so.py, docker compose build
issue: 43
last_verified: 2026-10-17
---

# Pacote de operação

Como o host instala, atualiza, checa e prepara o workspace, e como o CLI espelha o login do Simplicio Runtime. Passo a passo para quem vai usar: [docs/how-to/install.md](../how-to/install.md). Decisões: [ADR-0017](../decisoes/ADR-0017-instalacao-atualizacao.md) (instalação e atualização) e [ADR-0019](../decisoes/ADR-0019-login-compartilhado.md) (login compartilhado). Como rodar a fumaça em Windows e macOS: [testar-em-windows-e-macos.md](../how-to/testar-em-windows-e-macos.md).

Os contratos de `install`, `update`, `doctor`, `login`, `logout` e `auth status` seguem o do simplicio-loop (mesmos códigos de saída, mesmos `reason_code`, mesmos documentos `simplicio.doctor/v1`, `simplicio.login/v1`, `simplicio.logout/v1` e `simplicio.auth-status/v1`). A única diferença de conteúdo é que a correção sugerida diz `simplicio-video login`.

## Os comandos

| Comando | O que faz | Toca em |
|---|---|---|
| `./install.sh` | checa Node 22, ffmpeg com libass e 5 GB livres; garante o uv (oferece instalar, só com confirmação); chama `simplicio-video install`; constrói `web/` se existir; roda o doctor e imprime os próximos passos | nada fora do checkout; sem sudo |
| `simplicio-video install [--check] [--dry-run] [--json] [--python X] [--with EXTRAS]` | cria `<checkout>/.venv` com `uv venv` e instala o pacote em modo editável (`uv pip install -e .[extras]`). Grava `.venv/simplicio-install.json` com Python, extras e hash do `pyproject.toml`. Se nada mudou, não chama o uv. `--check` e `--dry-run` não criam nada. Não copia skills para o host de nenhum agente. O `./install.sh` roda este comando com o `python3` do sistema, antes de o `.venv` existir (sem PyYAML, por exemplo no macOS com as ferramentas do Xcode): por isso ele e tudo que ele importa no topo usam só a biblioteca padrão (um teste roda `--check`, `--dry-run`, `--json` e o install de verdade num interpretador que bloqueia qualquer terceiro). Com `--json`, o stdout é UM documento mesmo no erro (com a chave `error`) | só `.venv` dentro do checkout |
| `simplicio-video update [--check] [--dry-run] [--force]` | num checkout: recusa árvore suja, `git fetch`, mostra commits novos e diff do CHANGELOG, `git pull --ff-only`, reexecuta `install`, constrói `web/`, roda o doctor e imprime o `git reset --keep` para voltar. Num pacote instalado por pip: `python -m pip install --upgrade "simplicio-video==<última release>"` (PyPI). `--check` grava o resultado em `update-check.json`. `--dry-run` só mostra o plano: num checkout **não roda `git fetch`** (ele regrava `FETCH_HEAD`, as refs `origin/*` e o reflog, então não é um passo de leitura) | o checkout (via git) ou o ambiente Python do pip; `~/.simplicio-video/update-check.json` com `--check` |
| `simplicio-video doctor [all\|login] [--json] [--online]` | checa o ambiente e diz a correção exata de cada falha. Sem `--online` não usa rede. Não instala e não altera nada; com `--online` regrava só o `update-check.json` | nada (com `--online`, `~/.simplicio-video/update-check.json`) |
| `simplicio-video setup [--yes] [--theme] [--lang] [--force] [--realoficial]` | cria o workspace em `$SIMPLICIO_WORKSPACE` (padrão `~/.simplicio-video/workspaces/default`) com `workspace.yaml` (tema, idioma) e `policy.yaml` (autonomia L1; tokens, USD e créditos zerados). Não faz login nem grava credencial | o workspace |
| `simplicio-video login [--json] [--no-browser]` | roda `simplicio login google` do Runtime (terminal ligado) e confere o arquivo compartilhado. Sem Runtime: `UNVERIFIED`, mostra como instalar e sai com 1. Não guarda credencial | nada: quem grava o login é o Runtime |
| `simplicio-video logout [--yes] [--json]` | apaga `~/.simplicio/login.json` (ou `SIMPLICIO_AUTH_FILE`) sob a trava `login.lock`. Desloga o Runtime também, por isso exige `--yes` | esse arquivo e, se existir, `login.lock` ao lado |
| `simplicio-video auth status [--json]` | mostra a conta (mascarada), a validade dos tokens, os direitos em cache e a versão do Runtime. Nunca imprime token | nada |

Todo comando tem `--help` com exemplos. Os testes da suíte conferem isso (`tests/packaging/test_cli_pacote_help.py`).

### Códigos de saída

| Comando | 0 | 1 | 2 | 10 |
|---|---|---|---|---|
| `install --check` | em dia | — | argumento inválido | há mudança pendente |
| `install --dry-run` | sempre (não escreve nada) | — | argumento inválido | — |
| `install` | instalou ou já estava em dia | falhou, ou o `.venv` usa outro Python | argumento inválido, ou pacote instalado por pip (não há `.venv`) | — |
| `update --check` | em dia | — | erro (rede, git, árvore suja, sem upstream) | há atualização |
| `update` | atualizou, já estava em dia, ou o instalado é mais novo que a última release | falha de rede, ou falha de um passo | recusado: árvore suja, sem upstream, sem fast-forward, PEP 668 | — |
| `doctor` | nenhuma falha (aviso não reprova) | alguma checagem é `fail` | argumento inválido | — |
| `login` | verificado | não verificado (inclui `UNVERIFIED`) | recusado (`--no-browser` no Windows) | — |
| `logout` | saiu, ou não havia login | falhou ao apagar (`login_permissions`, trava) | recusado: faltou `--yes`, ou o arquivo não é um login (`not_a_login_file`) | — |
| `auth status` | logado | não logado | — | — |

`--force` do `update` reinstala mesmo em dia e permite downgrade; ele nunca ignora a árvore suja (nada é descartado: guarde com `git stash`). Falha de rede no `update` sai com `2` com `--check` e com `1` sem ele. Se a versão instalada é mais nova que a última release (o PyPI é publicado antes do GitHub Release), o `update` sai com `0` e diz `é mais novo que a última release`, como o loop; só o `--force` instala a release mesmo assim.

A versão da release é lida com regra estrita: `X.Y`, `X.Y.Z` ou `X.Y.Z.W` com um `v` opcional e o sufixo `.postN`, e nada mais (`v0.5.0-rc1`, `0.5.0 --index-url=...`, `1!2.0.0` e dígitos de largura total são recusados). O argv do pip é remontado só de números: `python -m pip install --upgrade simplicio-video==X.Y.Z`, uma lista, sem shell.

### Rede e `SIMPLICIO_OFFLINE=1`

`SIMPLICIO_OFFLINE=1` bloqueia **toda** a rede do `update` e do `doctor --online`. Num pacote instalado por pip, nem o `gh` nem a API do GitHub são chamados. Num checkout, o `git fetch` também não roda (nem `git pull`, `ls-remote` ou qualquer outro comando de rede): `update --check` sai com `2`, o `update` sai com `1` e o `doctor --online` mostra um aviso; as refs e o `.git` não são tocados. O `update --dry-run` nunca roda `git fetch`, com ou sem a variável, e todo comando git do update usa `--no-optional-locks` para que um passo de leitura não regrave o `.git/index`.

## Duas distribuições: checkout e pacote

`update`, `install` e `doctor` perguntam a `distribution.kind()`:

- **source**: um checkout git (ou `pip install -e`). `install` cria o `.venv` do checkout e `update` usa `git pull --ff-only`.
- **pip**: um pacote instalado (`pip install simplicio-video`). Não há checkout nem `.venv` a criar: `install --check` e `install --dry-run` dizem `instalado por pip: não há .venv a criar; use pip install --upgrade simplicio-video` e saem com 0, o `install` de verdade sai com 2, e nada é criado em `site-packages`. O `update` faz `pip install --upgrade "simplicio-video==<versão>"`, que vem do PyPI; a versão mais nova vem do GitHub Releases (`gh release view -R simpletibr/simplicio-videos`, ou a API `releases/latest`). Um Python gerenciado pelo sistema (PEP 668) é recusado com as saídas possíveis (`venv`, `uv`, `pipx` ou `PIP_BREAK_SYSTEM_PACKAGES=1`).

O pacote ainda não estava no PyPI na última conferência (a página `pypi.org/pypi/simplicio-video/json` respondia 404 em 17/10/2026): até a primeira publicação, o `update` de um pacote instalado acha a release no GitHub e o `pip install` falha com a mensagem do pip. Dentro do container o pacote é instalado por pip (`Dockerfile`): para atualizar, reconstrua a imagem.

## O que o doctor checa

As linhas saem nesta ordem. Cada uma tem `name`, `status` (`ok`, `warn` ou `fail`), `summary`, `fix` e `detail` (um objeto).

| Checagem | Falha quando | Aviso quando | Correção mostrada |
|---|---|---|---|
| `login` | o arquivo existe mas não é seguro ou não é um login (link simbólico, permissão frouxa, outro dono, JSON inválido, data que não é um instante, mais de 1 MiB) ou não dá para abri-lo (`login_permissions`, `login_invalid`) | não há login ou o token expirou | `simplicio-video login`, ou o `chmod` exato |
| `update` | — | há versão nova (no cache do último `update --check`, ou na consulta de `--online`), a consulta online falhou, ou o `update-check.json` está corrompido (data ou versão inválida, grande demais) | `simplicio-video update` |
| `distribution` | — | — | mostra `source` ou `pip` e a versão |
| `runtime` | — | — | o Runtime é opcional; mostra versão e caminho quando existe |
| `python` | Python menor que 3.12 | Python 3.14 ou superior (os extras do CrewAI exigem menos de 3.14) | `./install.sh --python 3.12` |
| `node` | ausente, não executa ou versão menor que 22 | — | instalar Node 22 (`nvm install 22`; no Windows, https://nodejs.org) |
| `ffmpeg` | ausente ou não executa | — | `brew install ffmpeg`, `apt install ffmpeg` ou `winget install Gyan.FFmpeg`, conforme o sistema |
| `ffmpeg-libass` | `ffmpeg -version` sem `--enable-libass` | sem ffmpeg não há como checar | reinstalar o ffmpeg com libass |
| `disk` | menos de 5 GB livres (no checkout; num pacote instalado, na pasta de dados `~/.simplicio-video`) | não consegue medir o disco | liberar espaço |
| `ports` | — | 3000 (opencut dev) ou 8000 (montage serve) em uso | parar o processo, ou ignorar se for o seu servidor |
| `GEMINI_API_KEY` | — | variável não definida | definir a chave para voz via Gemini |
| `setup` | `workspace.yaml` ou `policy.yaml` existe e é inválido ou não pode ser lido (permissão, YAML aninhado demais) | falta `workspace.yaml` ou `policy.yaml` (o setup não rodou) | `simplicio-video setup` (`setup --force` para regravar) |

`status` do documento é o pior dos checks, e o exit code é `1` só quando existe algum `fail`. `doctor login` roda só a linha do login; `doctor all` é o mesmo que `doctor`. Com `--online` o doctor consulta a última versão (GitHub num pacote, `git fetch` num checkout) e regrava `update-check.json`.

### Por que GEMINI_API_KEY, o login e o setup são aviso e não falha

A chave é opcional. Sem ela, o MVP usa a voz local, sem custo, e o ambiente funciona. O login do Runtime também é opcional para o motor: nenhum comando do motor lê o login, então a falta dele não quebra nada. O workspace só é lido por `setup` e `doctor` (nada no motor o usa). Se o doctor reprovasse por causa disso, a instalação ficaria marcada como quebrada num caso que funciona. A regra geral: `fail` só quando o comando seguinte não tem como funcionar, ou quando um arquivo está presente e inseguro ou inválido; `warn` para o que é opcional ou depende de quem usa.

O doctor também nunca mostra o valor de uma credencial nem um token. Ele só informa se a variável está definida (`GEMINI_API_KEY definida (valor oculto)`).

## Login compartilhado com o Runtime

O `login` do CLI é um **espelho** do `login` do simplicio-loop: o motor continua standalone (regra 3 do AGENTS.md).

- **O que é.** `simplicio-video login` roda `simplicio login google` (o Runtime, com o terminal ligado) e depois lê `~/.simplicio/login.json`, ou o arquivo de `SIMPLICIO_AUTH_FILE`: o mesmo arquivo, a mesma variável e a mesma trava (`login.lock`, `0600`, espera de 20 s) que o Runtime usa. Quem grava o login é o Runtime. O Runtime exige login para os comandos protegidos dele, e é por isso que o doctor mostra a linha `login`.
- **O que não é.** Não libera nem cobra nada no motor, não guarda credencial, não renova token, não recebe token por argumento, não aceita `SIMPLICIO_247_LOGIN` (do watcher do loop), não oferece `auth status --online`, não entra no `plugin.json` nem no servidor MCP.
- **Sem Runtime** o login próprio é `UNVERIFIED` (nenhum endpoint está documentado neste repositório, e nenhum é inventado). O comando imprime os comandos de instalação do Runtime do `INSTALL.md` dele (sem executá-los) e sai com 1.
- **Ambiente mínimo.** O processo filho do Runtime recebe só uma lista fechada de nomes exatos: `PATH`, `HOME`, `USERPROFILE`, o locale (`LANG`, `LANGUAGE`, `LC_ALL`, `LC_CTYPE`, `LC_MESSAGES`), o que o `xdg-open` precisa para achar a área de trabalho e o navegador (`XDG_RUNTIME_DIR`, `XDG_CURRENT_DESKTOP`, `XDG_SESSION_TYPE`, `XDG_SESSION_DESKTOP`, `XDG_CONFIG_HOME`, `XDG_CONFIG_DIRS`, `XDG_DATA_HOME`, `XDG_DATA_DIRS`), proxy, certificados, `SIMPLICIO_AUTH_FILE` e as variáveis que o Windows precisa para iniciar um processo. **Não há prefixo livre** (`LC_*` e `XDG_*` passavam por prefixo): `LC_TOKEN` ou `XDG_SECRET` não passam, nem `GH_TOKEN`, `GITHUB_TOKEN`, chaves de API ou `SIMPLICIO_LOGIN_TOKEN` do seu shell.
- **Segurança do arquivo (Linux e macOS).** São recusados: arquivo legível por grupo ou outros (`chmod 600`), link simbólico, FIFO, pasta, arquivo de outro usuário, pasta gravável por grupo ou outros, salvo pasta sticky e sua (`chmod 700`), e `login.lock` de outro usuário ou aberto por outros. A leitura usa `O_NOFOLLOW` e `O_NONBLOCK` e confere no mesmo descritor.
- **Arquivo corrompido ou hostil.** A leitura para em 1 MiB (um login de verdade tem uns 2 KiB) e o arquivo vira `login_invalid` quando é grande demais, não é UTF-8 nem JSON, é aninhado a ponto de estourar a recursão, ou tem `access_expires_at` ou `refresh_token_expires_at` que não é um instante entre 1970 e o ano 9999 (`1e999`, NaN, negativo, booleano, lista, `999999999999`, que é um i64 válido para o Runtime mas dá ano 33658). Pasta do `PATH` sem permissão é pulada, e uma pasta ou arquivo que o usuário não consegue abrir (um `~/.simplicio` de outro dono depois de um `sudo`) é `login_permissions` com a correção (`sudo chown -R "$USER" ...`). Nenhuma exceção sai de `doctor`, `login`, `logout` ou `auth status`, com texto ou `--json`: um teste passa todas essas entradas por todos os comandos.
- **Windows.** `chmod` e uid não valem: a checagem de modo e de dono é pulada e **as ACLs não são verificadas**. Link simbólico e junção (ponto de reparse do tipo link) continuam recusados. `--no-browser` recusa com exit 2 e `no_browser_unsupported`.
- **`--no-browser`** (Linux e macOS) põe substitutos de `xdg-open`, `open`, `gio` e outros no PATH do filho, tira `DISPLAY`, `WAYLAND_DISPLAY` e `DBUS_*`, e imprime o endereço e o código. No macOS, um Runtime que chame `/usr/bin/open` pelo caminho absoluto não é impedido (UNVERIFIED num macOS real).
- **Nunca expõe.** O token nunca aparece em stdout, stderr, JSON, log nem argumento; o e-mail sai mascarado (`w***@gmail.com`).
- **`logout`** apaga o arquivo compartilhado, então desloga o Runtime também. Sem `--yes` nada é apagado (exit 2). **Só apaga um login:** como `SIMPLICIO_AUTH_FILE` pode apontar para qualquer lugar (uma chave `~/.ssh/id_rsa` seria apagada), o arquivo precisa ser comum, pequeno (até 1 MiB) e ter a forma de um login (um objeto JSON com `access_token`, `refresh_token` ou `verification`), conferido antes e de novo sob a trava. Qualquer outra coisa (uma chave, uma pasta, uma fifo, um arquivo de outro formato) sai com exit 2, `REFUSED` e `not_a_login_file`, sem apagar nada e sem criar o `login.lock`. O modo não é conferido, para ainda dar para apagar um login inseguro, e um link simbólico é removido sem tocar no alvo. O token de renovação não é revogado no servidor: nenhum endpoint de revogação está documentado aqui. Sem arquivo de login: `NO_LOGIN`, exit 0, e nada é criado.

`reason_code` possíveis: `ok`, `login_missing`, `login_symlink`, `login_permissions`, `login_invalid`, `login_expired`, `login_lock_timeout`; no `login`, também `runtime_login_failed`, `standalone_login_unverified` e `no_browser_unsupported`; no `logout`, `confirmation_required` e `not_a_login_file`.

## Os schemas

Em `src/simplicio_video/data/schemas/cli/` (Draft 2020-12), conferidos por `tests/packaging/test_contrato_ops.py`:

| Arquivo | `$id` | Para quê |
|---|---|---|
| `doctor.schema.json` | `simplicio.doctor/v1` | saída de `doctor --json` |
| `login.schema.json` | `simplicio.login/v1` | saída de `login --json` |
| `logout.schema.json` | `simplicio.logout/v1` | saída de `logout --json` |
| `auth-status.schema.json` | `simplicio.auth-status/v1` | saída de `auth status --json`; proíbe `access_token` e `refresh_token` |
| `update-check.schema.json` | (arquivo de estado, sem `schema`) | `update-check.json`: `installed`, `latest`, `update_available`, `kind`, `checked_at`; `commits_behind` só em `source` |
| `install-result.schema.json` | `simplicio.video-install/v1` | saída de `install --json` (contrato próprio: o `install` do loop copia skills, este não) |

## Linux, macOS e Windows

O código não assume POSIX: o Python do `.venv` é `Scripts\python.exe` no Windows e `bin/python` nos outros; a pasta pessoal vem de `HOME` e, só depois, de `USERPROFILE`, em todo sistema (a ordem do Runtime, `runtime_auth.rs`, e do loop; com `USERPROFILE` na frente no Windows este CLI leria, e apagaria, outro arquivo que o Runtime grava quando as duas variáveis diferem, como no MSYS2 e no Cygwin); programas são achados no PATH com `PATHEXT` (`simplicio`, `simplicio.exe`, `simplicio.cmd`) e em `~/.simplicio/bin`, **nunca no diretório atual**; o `uv` é achado em `~/.local/bin`, `~/.cargo/bin` e, no macOS, nos prefixos do Homebrew (`/opt/homebrew/bin`, `/usr/local/bin`, também usados para `ffmpeg` e `node`); a trava é `fcntl` no POSIX e `msvcrt` no Windows; o disco é medido com `shutil.disk_usage`; e nenhum passo roda `sh`.

| Sistema | O que foi verificado | O que **não** foi |
|---|---|---|
| Linux | a suíte inteira roda aqui (gate local), `scripts/smoke_so.py` rodou | — |
| macOS | simulado no Linux (`sys.platform`, caminhos do Homebrew, substituto de `open`) | **UNVERIFIED**: nada rodou num macOS de verdade |
| Windows | simulado no Linux (`sys.platform`, `PureWindowsPath`, `msvcrt` falso, PATHEXT, ponto de reparse) | **UNVERIFIED**: nada rodou num Windows de verdade; `msvcrt.locking` × `LockFileEx` do Runtime e as ACLs não foram conferidos |

Windows e macOS reais continuam **UNVERIFIED** até alguém rodar `python scripts/smoke_so.py` (e `python -m pytest tests/packaging`) lá e registrar a tabela. Veja [testar-em-windows-e-macos.md](../how-to/testar-em-windows-e-macos.md). A suíte marca com `posix_real` os testes que precisam de arquivos POSIX de verdade, para a mesma suíte rodar nesses sistemas sem falhar à toa.

## Docker

- `Dockerfile` em três estágios: `node:22-bookworm-slim` (fonte do Node), `python:3.12-slim-bookworm` para o build do venv, e a imagem final com ffmpeg do Debian, Node 22 e um usuário não root (`simplicio`, UID 10001).
- Workspace em `VOLUME ["/workspace"]`, com `SIMPLICIO_WORKSPACE=/workspace`, e `WORKDIR /workspace`: o `init` grava `./clients/<cliente>/<campanha>/contract.yaml` na pasta atual, então o contrato cai no volume e sobrevive ao `docker compose run --rm` (num `WORKDIR` fora do volume ele sumia com o contêiner). `HEALTHCHECK` roda `simplicio-video --version`.
- `compose.yaml` builda a partir do `Dockerfile` e nomeia a imagem `simplicio-video:local`. Não há `image:` pública.
- `deploy/docker/doctor.sh` é um atalho para `docker compose run --rm simplicio doctor`.

Não publicamos imagem pronta. As builds do ffmpeg trazem obrigações de GPL ou LGPL, e a revisão de licença dos componentes empacotados ainda não foi feita (ver [monetization.md](../factory/monetization.md) e [risks-and-policies.md](../factory/risks-and-policies.md)).

## Atualização

A atualização está num módulo só, `src/simplicio_video/commands/update.py`: `git pull --ff-only` num checkout e `pip install --upgrade` num pacote. Se o repositório virar privado com archives assinados, a troca é local nesse módulo. Os comandos e a documentação do usuário não mudam.

## Limites atuais

- **web/ (#34):** o build de `web/` ainda não existe. `install` e `update` registram `web/ chega com a #34: nada a construir` e seguem.
- **Workspace de checagem (#35):** o doctor checa só a presença e o schema do workspace. As checagens de saúde do workspace chegam com a #35.
- **Windows e macOS reais:** UNVERIFIED (veja a tabela acima).
- **Runtime com `login google`:** o `INSTALL.md` do Runtime documenta o comando, mas o motor nunca o rodou de verdade aqui: os testes usam um Runtime falso. UNVERIFIED.
- **PyPI:** o pacote `simplicio-video` ainda não está publicado; o ramo pip do `update` depende disso.
- **Node no host:** a build de `web/` precisa de Node no host. A imagem Docker é o caminho sem Node.

## Mudanças que quebram (desde a 0.4.0)

| Antes | Agora |
|---|---|
| `doctor --json` era `{ok, checks[{name, status, detail (texto), fix}]}` | é `simplicio.doctor/v1`: `{schema, status, version, checks[{name, status, summary, fix, detail (objeto)}]}`; sai `ok`, o texto vira `summary` |
| `install --check` saía com `1` quando havia mudança pendente | sai com `10` (`0` em dia) |
| `update --force` seguia com árvore suja | reinstala mesmo em dia e permite downgrade; a árvore suja é sempre recusada |
| `update` recusado (árvore suja, sem upstream, sem fast-forward) saía com `1` | sai com `2` |
| `update --check` saía sempre com `0` | sai com `0` (em dia), `10` (há atualização) ou `2` (erro) e grava `update-check.json` |
| workspace ausente era `fail` no doctor | é `warn` (a linha `setup`) |
| nomes `ffmpeg libass`, `disco livre`, `portas`, `workspace`, `workspace policy` | `ffmpeg-libass`, `disk`, `ports` e uma linha `setup` |
