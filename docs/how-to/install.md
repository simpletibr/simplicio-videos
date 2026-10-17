---
title: Instalar, atualizar e checar o simplicio-video
summary: Como instalar com um comando, atualizar com segurança (checkout ou pip), checar o ambiente, entrar com o login do Runtime e rodar pelo Docker local.
commands: ./install.sh, simplicio-video install, simplicio-video update, simplicio-video doctor, simplicio-video setup, simplicio-video login, simplicio-video logout, simplicio-video auth status, docker compose build
issue: 43
last_verified: 2026-10-17
---

# Instalar, atualizar e checar o simplicio-video

Um comando instala tudo no checkout: Python 3.12 num `.venv`, o pacote, os extras pedidos e uma checagem final. Não usa sudo e pode rodar de novo sem estragar nada. O que cada passo faz e por que está assim: [packaging.md](../host/packaging.md) e [ADR-0017](../decisoes/ADR-0017-instalacao-atualizacao.md). O login compartilhado com o Runtime: [ADR-0019](../decisoes/ADR-0019-login-compartilhado.md).

## Requisitos

| O quê | Como conferir | Se faltar |
|---|---|---|
| Node 22 ou superior | `node -v` | `nvm install 22` (no Windows, https://nodejs.org) |
| ffmpeg com libass | `ffmpeg -version \| grep -- --enable-libass` | macOS: `brew install ffmpeg`; Debian/Ubuntu: `apt install ffmpeg` (use um pacote compilado com libass); Windows: `winget install Gyan.FFmpeg` |
| 5 GB livres no disco do checkout | `df -h .` | libere espaço: o `.venv` e o render precisam dele |
| uv | `uv --version` | o `install.sh` oferece instalar, e só baixa com a sua confirmação; sem ele, o `simplicio-video install` mostra o comando do seu sistema |

Linux e macOS são o alvo do `install.sh`. No Windows, o CLI (`install`, `update`, `doctor`, `login`) foi escrito sem premissa POSIX, mas **ainda não foi rodado num Windows de verdade (UNVERIFIED)**: veja [testar em Windows e macOS](testar-em-windows-e-macos.md). Para o render no Windows, use o WSL ou o Docker (seção abaixo).

## Instalar

```bash
git clone https://github.com/simpletibr/simplicio-videos.git
cd simplicio-videos

./install.sh --dry-run    # mostra o plano e não cria nem altera nada
./install.sh              # cria o .venv, instala o pacote, checa o ambiente e roda o doctor
```

O `install.sh` aceita três opções:

| Opção | O que faz |
|---|---|
| `--dry-run` | lista o plano (checagens, uv, `.venv`, extras, `web/`, doctor) e sai sem criar nada |
| `--with EXTRAS` | extras separados por vírgula. Os que existem hoje: `test` (pytest, ruff, shellcheck: o gate), `local-tts` (voz local, sem custo), `mcp` (servidor MCP), `remote` (Kaggle e Colab) |
| `--python VERSÃO` | Python do `.venv`. O padrão é 3.12, porque os extras do CrewAI exigem Python menor que 3.14 |

Exemplos reais:

```bash
./install.sh --with local-tts                  # o MVP com voz local
./install.sh --with test --python 3.12         # quem vai rodar o gate (make check)
./install.sh --dry-run --with local-tts --python 3.12
```

Sem `--with`, a instalação reaproveita os extras da última vez. Rodar de novo sem mudanças não chama o uv e não altera o `.venv`.

Depois da instalação, crie o workspace e confira o ambiente:

```bash
.venv/bin/simplicio-video setup --yes     # workspace com tema br, idioma pt-BR, autonomia L1 e orçamentos zerados
.venv/bin/simplicio-video doctor          # confere login, Python, Node, ffmpeg, disco, credenciais e workspace
```

### Só o ambiente Python

`simplicio-video install` é o passo que o `install.sh` chama. Use-o sozinho para trocar extras ou o Python:

```bash
.venv/bin/simplicio-video install --check                       # mostra o plano; sai com 10 se houver mudança pendente (0 em dia)
.venv/bin/simplicio-video install --dry-run --json              # o plano em JSON (simplicio.video-install/v1); não cria nada
.venv/bin/simplicio-video install --python 3.12 --with local-tts
```

O `install` do `simplicio-video` cria o `.venv` do checkout. Ele **não** copia skills para o host de nenhum agente (o `install` do simplicio-loop faz isso; aqui o Runtime acha as skills pelo `plugin.json`).

### Se o pacote veio do pip

Instalado por `pip install simplicio-video`, não há checkout nem `.venv`: `install --check` e `install --dry-run` dizem `instalado por pip: não há .venv a criar; use pip install --upgrade simplicio-video` e saem com 0, e o `install` de verdade sai com 2. Nada é criado em `site-packages`. O pacote ainda não está publicado no PyPI (conferido em 17/10/2026): até lá, instale pelo checkout.

## Atualizar

```bash
.venv/bin/simplicio-video update --check    # 0 em dia, 10 há atualização, 2 erro; não altera nada
.venv/bin/simplicio-video update --dry-run  # mostra o que rodaria; não altera nada
.venv/bin/simplicio-video update            # git pull --ff-only, reinstala, reconstrói web/ e roda o doctor
```

`update --check` faz `git fetch`, então precisa de rede, e grava o resultado em `~/.simplicio-video/update-check.json` (ou em `$SIMPLICIO_VIDEO_DATA`), que o `doctor` lê sem rede.

- Se a árvore tiver alterações não commitadas, o update recusa com exit 2. Guarde com `git stash` (ou faça commit) e rode de novo. O `--force` **não** ignora a árvore suja: nada é descartado.
- `--force` reinstala mesmo em dia e permite downgrade.
- Só há avanço rápido. Se a sua branch divergiu do remoto, o pull falha com exit 2 e nada muda.
- O update imprime o commit anterior e o comando para voltar a ele, no formato `git -C <checkout> reset --keep <commit>`.
- Falha de rede: exit 2 com `--check` e exit 1 sem ele.

Num pacote instalado por pip, o update faz `python -m pip install --upgrade "simplicio-video==<última release>"` (PyPI). Um Python gerenciado pelo sistema (PEP 668) é recusado com exit 2 e quatro saídas: um `venv`, `uv`, `pipx`, ou `PIP_BREAK_SYSTEM_PACKAGES=1 simplicio-video update` se você autoriza. Dentro do container, reconstrua a imagem (`docker compose build`).

## Checar

```bash
.venv/bin/simplicio-video doctor            # tabela com ok, warn e fail; a correção de cada falha
.venv/bin/simplicio-video doctor --json     # o mesmo em JSON (simplicio.doctor/v1), para scripts
.venv/bin/simplicio-video doctor login      # só a linha do login
.venv/bin/simplicio-video doctor --online   # consulta a última versão e regrava o cache do update
```

O doctor sai com `0` quando nenhuma checagem falhou e com `1` quando alguma falhou. Aviso não reprova: login ausente, workspace ausente e `GEMINI_API_KEY` ausente são avisos. Ele nunca imprime o valor de uma credencial nem um token, só se existem. A lista completa do que é checado está em [packaging.md](../host/packaging.md).

## Login do Simplicio (o mesmo do Runtime)

O Runtime exige login para os comandos protegidos dele. O `simplicio-video` não tem login próprio: ele **espelha** o do simplicio-loop e usa o mesmo arquivo, `~/.simplicio/login.json` (ou `SIMPLICIO_AUTH_FILE`).

```bash
.venv/bin/simplicio-video login              # roda `simplicio login google` e confere o arquivo compartilhado
.venv/bin/simplicio-video login --no-browser # mostra o endereço e o código em vez de abrir o navegador (Linux e macOS)
.venv/bin/simplicio-video auth status        # conta (mascarada), validade, direitos em cache e versão do Runtime
.venv/bin/simplicio-video logout --yes       # apaga o arquivo: desloga o Runtime também
```

- O login **não libera nem cobra nada** no motor e não guarda credencial: nenhum comando do motor depende dele, e ele não está no `plugin.json` nem no MCP.
- Sem o Runtime instalado, `login` diz `UNVERIFIED`, mostra como instalar o Runtime e sai com 1. Ele não inicia um login por conta própria.
- `auth status` sai com 0 logado e 1 não logado; nunca imprime token, e a conta sai mascarada (`w***@gmail.com`).
- `logout` sem `--yes` não apaga nada (exit 2), porque o arquivo é do Runtime também. O token de renovação não é revogado no servidor.
- Linux e macOS recusam arquivo de login legível por outros (`chmod 600`) e pasta gravável por outros (`chmod 700`). No Windows essas checagens não existem e as ACLs não são verificadas.

## Docker (build local)

Não há imagem publicada. A imagem é construída na sua máquina, porque as builds do ffmpeg trazem obrigações de licença (GPL ou LGPL) que ainda passam por revisão. Ela já traz Python 3.12, ffmpeg com libass e Node 22, então serve quando você não quer instalar nada no host.

```bash
docker compose build                                  # constrói a imagem simplicio-video:local
docker compose run --rm simplicio setup --yes         # cria o workspace no volume /workspace
docker compose run --rm simplicio doctor              # confere a imagem
deploy/docker/doctor.sh --json                        # atalho para o doctor, com saída em JSON
```

A chave `GEMINI_API_KEY` é passada do seu shell em tempo de execução (o `compose.yaml` só repete o nome da variável) e não entra na imagem:

```bash
export GEMINI_API_KEY=...                             # no seu shell; não vai para o repositório
docker compose run --rm simplicio doctor
```

Sem a chave, o doctor mostra aviso e o MVP usa a voz local.

## Problemas comuns

| Sintoma | Saída |
|---|---|
| `node v20 (exigido: 22 ou superior)` | `nvm install 22` e rode o doctor de novo |
| `ffmpeg sem libass` | reinstale o ffmpeg com libass (veja a tabela de requisitos) |
| `uv não encontrado` | aceite a instalação oferecida pelo `install.sh`, ou rode o comando que o `install` mostra para o seu sistema, ou veja https://docs.astral.sh/uv/ |
| `update recusado: a árvore está suja` | `git stash` (ou commit) das alterações, depois rode o update |
| `instalado por pip: não há .venv a criar` | é esperado num pacote do pip; atualize com `simplicio-video update` ou `pip install --upgrade simplicio-video` |
| `login: ... pode ser lido pelo grupo ou por outros` | rode o `chmod 600` que o `auth status` mostra |
| `login: Simplicio Runtime não encontrado` | instale o Runtime (o comando aparece na saída) e rode `simplicio-video login` de novo |
| `sem workspace.yaml` / `o setup ainda não rodou` | `.venv/bin/simplicio-video setup --yes` |
| `.venv usa Python 3.13 e o pedido é 3.12` | `rm -rf .venv` e rode o `install.sh` de novo |

## Limites atuais

- O doctor ainda não checa plugins: o health check de plugin chega com a #32.
- Não há build de `web/`: ele chega com a #34. Até lá, o `install.sh` e o `update` registram isso e seguem.
- Windows e macOS reais são UNVERIFIED até alguém rodar `scripts/smoke_so.py` lá ([guia](testar-em-windows-e-macos.md)).
- O `login google` do Runtime nunca foi rodado de verdade por este CLI (os testes usam um Runtime falso): UNVERIFIED.
