---
title: Pacote de operação (install, update, doctor, setup)
summary: O que cada subcomando faz, o que o doctor checa, por que a falta de GEMINI_API_KEY é aviso e os limites até as #32 e #34.
commands: ./install.sh, simplicio-video install, simplicio-video update, simplicio-video doctor, simplicio-video setup, docker compose build
issue: 43
last_verified: 2026-10-08
---

# Pacote de operação

Como o host instala, atualiza, checa e prepara o workspace. Passo a passo para quem vai usar: [docs/how-to/install.md](../how-to/install.md). Decisão e alternativas: [ADR-0017](../decisoes/ADR-0017-instalacao-atualizacao.md).

## Os comandos

| Comando | O que faz | Toca em |
|---|---|---|
| `./install.sh` | checa Node 22, ffmpeg com libass e 5 GB livres; garante o uv (oferece instalar, só com confirmação); chama `simplicio-video install`; constrói `web/` se existir; roda o doctor e imprime os próximos passos | nada fora do checkout; sem sudo |
| `simplicio-video install [--check] [--python X] [--with EXTRAS]` | cria `<checkout>/.venv` com `uv venv` e instala o pacote em modo editável (`uv pip install -e .[extras]`). Grava `.venv/simplicio-install.json` com Python, extras e hash do `pyproject.toml`. Se nada mudou, não chama o uv | só `.venv` dentro do checkout |
| `simplicio-video update [--check] [--force]` | recusa árvore suja; `git fetch`; mostra commits novos e diff do CHANGELOG; (`--check` para aqui) `git pull --ff-only`; reexecuta `install`; constrói `web/`; roda o doctor; imprime o commit anterior e o `git reset --keep` para voltar | o checkout (via git) |
| `simplicio-video doctor [--json]` | checa o ambiente e diz a correção exata de cada falha. Não instala, não altera e não grava nada | nada |
| `simplicio-video setup [--yes] [--theme] [--lang] [--force] [--realoficial]` | cria o workspace em `$SIMPLICIO_WORKSPACE` (padrão `~/.simplicio-video/workspaces/default`) com `workspace.yaml` (tema, idioma) e `policy.yaml` (autonomia L1; tokens, USD e créditos zerados). Não faz login nem grava credencial | o workspace |

`install --check` sai com `1` quando há mudança pendente, e o `doctor` sai com `1` quando alguma checagem falha. `--force` do `setup` regrava `workspace.yaml` e `policy.yaml` e zera os orçamentos: use só se quiser isso.

Todo comando tem `--help` com exemplos. Os testes da suíte conferem isso (`tests/packaging/test_cli_pacote_help.py`).

## O que o doctor checa

| Checagem | Falha quando | Aviso quando | Correção mostrada |
|---|---|---|---|
| `python` | Python menor que 3.12 | Python 3.14 ou superior (os extras do CrewAI exigem menos de 3.14) | `./install.sh --python 3.12` |
| `node` | ausente, não executa ou versão menor que 22 | — | instalar Node 22 (`nvm install 22`) |
| `ffmpeg` | ausente ou não executa | — | instalar ffmpeg (`brew` ou `apt`) |
| `ffmpeg libass` | `ffmpeg -version` sem `--enable-libass` | — | reinstalar o ffmpeg com libass |
| `disco livre` | menos de 5 GB livres no caminho do checkout | não consegue medir o disco | liberar espaço |
| `portas` | — | 3000 (opencut dev) ou 8000 (montage serve) em uso | parar o processo, ou ignorar se for o seu servidor |
| `GEMINI_API_KEY` | — | variável não definida | definir a chave para voz via Gemini |
| `workspace` | `workspace.yaml` ausente, ilegível ou com schema ou layout errados | — | `simplicio-video setup` |
| `workspace policy` | `policy.yaml` ausente, ilegível ou sem autonomia válida | — | `simplicio-video setup` |

Cada linha tem `name`, `status` (`ok`, `warn` ou `fail`), `detail` e `fix`. No `--json`, o contrato é `{"ok": bool, "checks": [...]}`. `ok` é `false` só quando existe alguma `fail`.

### Por que GEMINI_API_KEY é aviso e não falha

A chave é opcional. Sem ela, o MVP usa a voz local, sem custo, e o ambiente funciona. Se o doctor reprovasse por causa dela, a instalação ficaria marcada como quebrada num caso que funciona. Por isso ela vira `warn`, com a correção de como obtê-la e a informação de que a voz local cobre a falta.

Regra geral: `fail` só quando o comando seguinte não tem como funcionar; `warn` para o que é opcional ou depende de quem usa.

O doctor também nunca mostra o valor de uma credencial. Ele só informa se a variável está definida (`GEMINI_API_KEY definida (valor oculto)`).

## Docker

- `Dockerfile` em três estágios: `node:22-bookworm-slim` (fonte do Node), `python:3.12-slim-bookworm` para o build do venv, e a imagem final com ffmpeg do Debian, Node 22 e um usuário não root (`simplicio`, UID 10001).
- Workspace em `VOLUME ["/workspace"]`, com `SIMPLICIO_WORKSPACE=/workspace`, e `WORKDIR /workspace`: o `init` grava `./clients/<cliente>/<campanha>/contract.yaml` na pasta atual, então o contrato cai no volume e sobrevive ao `docker compose run --rm` (num `WORKDIR` fora do volume ele sumia com o contêiner). `HEALTHCHECK` roda `simplicio-video --version`.
- `compose.yaml` builda a partir do `Dockerfile` e nomeia a imagem `simplicio-video:local`. Não há `image:` pública.
- `deploy/docker/doctor.sh` é um atalho para `docker compose run --rm simplicio doctor`.

Não publicamos imagem pronta. As builds do ffmpeg trazem obrigações de GPL ou LGPL, e a revisão de licença dos componentes empacotados ainda não foi feita (ver [monetization.md](../factory/monetization.md) e [risks-and-policies.md](../factory/risks-and-policies.md)).

## Atualização

Todo o mecanismo de atualização está num módulo só, `src/simplicio_video/commands/update.py`, usando `git pull --ff-only`. Se o repositório virar privado com archives assinados, a troca é local nesse módulo. Os comandos e a documentação do usuário não mudam.

## Limites atuais

- **web/ (#34):** o build de `web/` ainda não existe. `install` e `update` registram `web/ chega com a #34: nada a construir` e seguem.
- **Workspace de checagem (#35):** o doctor checa só a presença e o schema do workspace. As checagens de saúde do workspace chegam com a #35.
- **Windows nativo:** fora do escopo. Use o WSL ou o Docker.
- **Node no host:** a build de `web/` precisa de Node no host. A imagem Docker é o caminho sem Node.
