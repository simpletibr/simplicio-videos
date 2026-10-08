---
title: Instalar, atualizar e checar o simplicio-video
summary: Como instalar com um comando, atualizar com segurança, checar o ambiente e rodar pelo Docker local.
commands: ./install.sh, simplicio-video install, simplicio-video update, simplicio-video doctor, simplicio-video setup, docker compose build
issue: 43
last_verified: 2026-10-08
---

# Instalar, atualizar e checar o simplicio-video

Um comando instala tudo no checkout: Python 3.12 num `.venv`, o pacote, os extras pedidos e uma checagem final. Não usa sudo e pode rodar de novo sem estragar nada. O que cada passo faz e por que está assim: [packaging.md](../host/packaging.md) e [ADR-0017](../decisoes/ADR-0017-instalacao-atualizacao.md).

## Requisitos

| O quê | Como conferir | Se faltar |
|---|---|---|
| Node 22 ou superior | `node -v` | `nvm install 22` |
| ffmpeg com libass | `ffmpeg -version \| grep -- --enable-libass` | macOS: `brew install ffmpeg`; Debian/Ubuntu: `apt install ffmpeg` (use um pacote compilado com libass) |
| 5 GB livres no disco do checkout | `df -h .` | libere espaço: o `.venv` e o render precisam dele |
| uv | `uv --version` | o `install.sh` oferece instalar, e só baixa com a sua confirmação |

macOS e Linux são suportados. No Windows, use o WSL ou o Docker (seção abaixo).

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
.venv/bin/simplicio-video doctor          # confere Python, Node, ffmpeg, disco, credenciais e workspace
```

### Só o ambiente Python

`simplicio-video install` é o passo que o `install.sh` chama. Use-o sozinho para trocar extras ou o Python:

```bash
.venv/bin/simplicio-video install --check                       # mostra o que mudaria; sai com 1 se houver mudança pendente
.venv/bin/simplicio-video install --python 3.12 --with local-tts
```

## Atualizar

```bash
.venv/bin/simplicio-video update --check    # busca os commits novos e mostra o diff do CHANGELOG; não altera nada
.venv/bin/simplicio-video update            # git pull --ff-only, reinstala, reconstrói web/ e roda o doctor
```

`update --check` faz `git fetch`, então precisa de rede.

- Se a árvore tiver alterações não commitadas, o update recusa. Faça commit ou stash delas.
- `--force` deixa seguir com a árvore suja, mas não descarta nada: o git ainda recusa o pull se ele tocar nos mesmos arquivos.
- Só há avanço rápido. Se a sua branch divergiu do remoto, o pull falha e nada muda.
- O update imprime o commit anterior e o comando para voltar a ele, no formato `git -C <checkout> reset --keep <commit>`.

## Checar

```bash
.venv/bin/simplicio-video doctor            # tabela com ok, aviso e falha; a correção de cada falha
.venv/bin/simplicio-video doctor --json     # mesma saída em JSON, para scripts
```

O doctor sai com `0` quando nenhuma checagem falhou e com `1` quando alguma falhou. Aviso não reprova. Ele nunca imprime o valor de uma credencial, só se ela está definida. A lista completa do que é checado está em [packaging.md](../host/packaging.md).

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
| `uv não encontrado` | aceite a instalação oferecida pelo `install.sh` ou instale em https://docs.astral.sh/uv/ |
| `update recusado: a árvore está suja` | faça commit ou stash das alterações, depois rode o update |
| `sem workspace.yaml` | `.venv/bin/simplicio-video setup --yes` |
| `.venv usa Python 3.13 e o pedido é 3.12` | `rm -rf .venv` e rode o `install.sh` de novo |

## Limites atuais

- O doctor ainda não checa plugins: o health check de plugin chega com a #32. Hoje ele mostra `nenhum plugin instalado`.
- Não há build de `web/`: ele chega com a #34. Até lá, o `install.sh` e o `update` registram isso e seguem.
- Windows nativo não é suportado. Use o WSL ou o Docker.
