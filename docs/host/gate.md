---
title: Gate local, TDD e pouso de PRs
summary: Como provar que a main está verde com um comando offline, a regra de testes primeiro, o ownership por issue e o pouso serializado sem CI.
commands: make setup, make check, make check-full, make check-web, make hooks, make regen, scripts/check_ownership.py, scripts/check_tdd.py, scripts/land.sh
issue: 31
last_verified: 2026-10-07
---

# Gate local, TDD e pouso de PRs

Não há GitHub Actions (política da organização). A `main` fica verde porque todo PR passa pelo mesmo gate **na máquina de quem pousa**, um de cada vez. Decisão e alternativas: [ADR-0005](../decisoes/ADR-0005-gate-sem-ci.md). Acordo de trabalho em paralelo: [parallel-work.md](../factory/parallel-work.md).

## Como rodar

```bash
make setup        # cria .venv, instala o extra `test` (pytest, pytest-socket, ruff, shellcheck-py) e liga os hooks
make check        # o gate: offline, menos de 60 s
make check-full   # check + testes render/integration/ui/slow (podem usar rede)
make check-web    # workspace web (chega com a #34; por enquanto só avisa e sai com 0)
make hooks        # git config core.hooksPath .githooks (o pre-push roda `make check`)
make regen        # regenera os arquivos gerados (plugin.json, schemas, referências)
```

Numa cópia limpa: `python3 -m venv .venv && .venv/bin/pip install -e '.[test]' && make check`.

`make check` descobre a issue e a base sozinho: a issue vem do nome do branch (`feat/31-gate`, `loop/issue-31`) e a base é `origin/main`. Para forçar: `ISSUE=31 BASE=origin/main make check`. Sem issue ou sem base, as checagens de ownership e TDD são puladas com um aviso.

As trilhas estendem o gate sem editar o `Makefile`: criam `mk/<trilha>.mk` com `CHECKS += alvo`, `REGEN += alvo` ou `CHECKS_WEB += alvo` e definem o alvo.

## O que é verificado

`make check` roda `scripts/check.sh`, nesta ordem:

| Etapa | O quê |
|---|---|
| ruff | `ruff check .` com `[tool.ruff]` do `pyproject.toml`: só `src/simplicio_video` e `scripts`; mais os `.py` que o branch alterou (qualquer pasta) |
| shellcheck | `scripts/*.sh` e `.githooks/*` |
| testes | `pytest -m "not slow and not render and not integration and not ui"`, `SIMPLICIO_OFFLINE=1`, sockets bloqueados |
| ownership | `scripts/check_ownership.py <issue> --base <base>` |
| TDD | `scripts/check_tdd.py --base <base>` |

**Marcadores** (registrados em `pyproject.toml`): `unit` (padrão de todo teste sem marcador), `contract`, `e2e`, `integration`, `render`, `ui` e `slow`. `render`, `integration`, `ui` e `slow` ficam fora do `make check`.

**Sem rede nos testes.** `addopts` liga `--disable-socket --allow-unix-socket` (pytest-socket): um teste que abre socket falha com `SocketBlockedError`. `render`, `integration` e `ui` são liberados em `tests/conftest.py` (o render chama `npx`). Três testes antigos sobem um servidor em `127.0.0.1`; eles só falam com o loopback (`LOOPBACK_TESTS` no `conftest.py`).

**Testes que rodam subprocessos** (`run_cli`) não são cobertos pelo guarda em processo, então `conftest.offline_env()` injeta o mesmo guarda no Python filho (`sitecustomize`) e exporta `SIMPLICIO_OFFLINE=1`. O motor respeita a variável: `montage clone` se recusa a baixar o OpenMontage em modo offline.

**Testes herméticos.** Um fixture automático aponta `SIMPLICIO_VIDEO_DATA` para um diretório temporário, limpa `OPENMONTAGE_DIR`/`SIMPLICIO_TOOLS_DIR` e troca `tools._git` por uma função que falha: nenhum teste clona nada nem toca no `~/.simplicio-video`. O OpenMontage fica em `$SIMPLICIO_VIDEO_DATA/tools/openmontage` (padrão `~/.simplicio-video/tools/openmontage`).

**Ownership.** Cada issue só pode alterar os paths de `docs/factory/ownership.yaml`. `path#secao` marca um arquivo compartilhado (o script libera o arquivo e avisa; o revisor confere a seção); `generated` vale para todas as issues e vem de `make regen`. Issue em `status: backlog` não começa. O próprio `ownership.yaml` só pode mudar na entrada da issue.

## Regra de TDD

1. O **primeiro commit do branch** só toca testes, fixtures e docs (`tests/`, `docs/`, pastas `fixtures/`) e falha pelo motivo certo.
2. Toda mudança em `src/` vem com mudança em `tests/` no mesmo branch.
3. O label `tdd-exempt` dispensa as duas regras (PR só de docs, refactor puro). O motivo vai no corpo do PR. Passe o label por `--labels` ou por `PR_LABELS="mvp tdd-exempt"`.

## Pouso (land.sh)

```bash
scripts/land.sh 123 --dry-run     # mostra o plano e confere o PR em leitura; não muda nada
scripts/land.sh 123               # pousa de verdade
scripts/land.sh 123 --issue 31    # quando o corpo do PR não tem "Closes #31"
```

Ordem: lock (um pouso por vez, em `.git/simplicio-land.lock`) → confere PR aberto, label `reviewed` e a issue → `gh pr checkout` → `git fetch` e `git rebase origin/main` → `make check` → ownership → TDD → empurra o branch rebaseado se mudou → `gh pr merge --squash --delete-branch --match-head-commit`. Qualquer falha para tudo, sem merge. Só PRs de branches do próprio repositório.

O `reviewed` é aplicado pelo revisor independente (outro agente ou pessoa rodando `/code-review` no diff). Se a `main` ficar vermelha: reverta primeiro, investigue depois.

## Solução de problemas

| Sintoma | Causa e saída |
|---|---|
| `unrecognized arguments: --disable-socket` | falta o extra `test`: `pip install -e '.[test]'` |
| `SocketBlockedError` num teste | o teste abriu rede. Use fake/fixture; se for de verdade `render`/`integration`/`ui`, marque-o; servidor local de teste: peça para entrar em `LOOPBACK_TESTS` |
| `hermetic: unit tests must not run git` | o teste chamou `tools._git`; troque por `monkeypatch.setattr(tools, "_git", ...)` |
| `ruff: command not found` | `.venv/bin/python -m ruff` ou reinstale o extra `test` |
| `FALHA: <arquivo> não pertence à issue` | o arquivo é de outra issue: comente na dona. Se for gerado, rode `make regen` |
| `base desconhecida: origin/main` | `git fetch origin` |
| `lock ocupado` | outro pouso em andamento; se o processo morreu o lock é reaproveitado sozinho |
| `make check` passou de 60 s | o script avisa; marque o teste lento como `slow` |
| rebase com conflito | o `land.sh` aborta o rebase; resolva no branch e rode de novo |
| `openmontage` não é encontrado | `simplicio-video montage clone` (precisa de rede) ou `OPENMONTAGE_DIR=<checkout>` |
