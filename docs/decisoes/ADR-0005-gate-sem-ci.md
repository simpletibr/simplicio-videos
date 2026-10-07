# ADR-0005: gate local no lugar de CI (main verde, TDD e pouso serializado sem GitHub Actions)

- **Status:** aceito. Implementado na issue #31 (`make check`, `scripts/check_ownership.py`, `scripts/check_tdd.py`, `scripts/land.sh`, hooks e templates).
- **Data:** 07/10/2026 (BRT)
- **Relaciona:** [docs/host/gate.md](../host/gate.md) (como usar) · [parallel-work.md](../factory/parallel-work.md) (acordo de trabalho em paralelo) · [ownership.yaml](../factory/ownership.yaml) · [ADR-0001](ADR-0001-visao-plugin.md) (LLM nunca no caminho padrão)

## Contexto

Várias issues andam ao mesmo tempo e cada PR precisa pousar sem quebrar a `main`. A política da organização **não permite GitHub Actions**, então não existe CI. Hoje a `main` não é provadamente verde: três testes falhavam em qualquer máquina sem `/projetos/ai/OpenMontage` (caminho absoluto no código), dois testes de render chamam `npx` pela rede e falham de forma intermitente, `clone` e `montage` eram instalados como scripts de console genéricos, e não havia gate, checagem de ownership nem procedimento de pouso.

## Decisão

1. **O gate é local e offline.** `make check` roda `scripts/check.sh`: ruff, shellcheck, `pytest -m "not slow and not render and not integration and not ui"`, ownership e ordem do TDD, em menos de 60 s e sem rede. `make check-full` soma os testes que podem usar rede. As trilhas estendem o gate por `mk/<trilha>.mk` (`CHECKS`, `REGEN`, `CHECKS_WEB`), sem editar o `Makefile`.
2. **Marcadores:** `unit` (padrão), `contract`, `e2e`, `integration`, `render`, `ui`, `slow`. Os testes de render e os que usam `npx` são `render`.
3. **Sockets bloqueados nos testes** com `pytest-socket` (`--disable-socket --allow-unix-socket` em `addopts`, extra `test`). `render`, `integration` e `ui` são liberados em `tests/conftest.py`; três testes antigos que sobem um servidor em `127.0.0.1` só podem falar com o loopback.
4. **Subprocessos também ficam offline.** O guarda em processo não alcança `python -m simplicio_video` rodando como filho. Os testes passam por `conftest.offline_env()`, que exporta `SIMPLICIO_OFFLINE=1` (o motor checa: `montage clone` se recusa a baixar) e injeta o mesmo guarda de socket no Python filho por `sitecustomize`. Node e `npx` filhos não são cobertos; por isso o que usa `npx` é `render`.
5. **Testes herméticos.** Um fixture automático isola `SIMPLICIO_VIDEO_DATA`, limpa as variáveis de checkout das ferramentas e troca `tools._git` por uma função que falha. O OpenMontage fica em `$SIMPLICIO_VIDEO_DATA/tools/openmontage` (padrão `~/.simplicio-video/tools/openmontage`), sem caminho absoluto de máquina.
6. **TDD por script.** `scripts/check_tdd.py`: o primeiro commit do branch só toca testes, fixtures e docs; mudança em `src/` exige mudança em `tests/`; o label `tdd-exempt` dispensa, com o motivo no PR.
7. **Ownership por script.** `scripts/check_ownership.py <issue>` compara o diff com `owns` e `generated` de `ownership.yaml` (`path#secao` libera o arquivo compartilhado e o revisor confere a seção; `backlog` não começa).
8. **Pouso serializado.** `scripts/land.sh <pr>` pega um lock, faz `gh pr checkout`, rebase em `origin/main`, `make check`, ownership e TDD, exige o label `reviewed`, empurra o head testado e faz squash-merge apagando o branch (`--match-head-commit`). Recusa se qualquer etapa falhar; `--dry-run` não muda nada. O hook `pre-push` (`make hooks`) roda `make check`.
9. **Os console scripts `clone` e `montage` saem** de `[project.scripts]`; os subcomandos `simplicio-video clone|montage` continuam.
10. **Sem workflows.** `.github/` só leva templates (PR e issue).

## Consequências

- Cada PR custa um `make check` na máquina de quem pousa; o lock garante um pouso por vez (fila de merge local). O gate depende dessa máquina estar com as ferramentas do extra `test`; o `make setup` as instala.
- Se a `main` ficar vermelha: reverte primeiro, investiga depois.
- Quem escreve teste novo que precisa de rede escolhe um marcador (`integration`, `render`, `ui`) e fica fora do `make check`.
- O guarda de subprocesso só enxerga Python; ferramentas externas (Node, ffmpeg, git) continuam fora do alcance e são cobertas por fakes ou pelos marcadores.
- O `ruff` cobre `src/simplicio_video` e `scripts` mais os `.py` que o branch altera; achados antigos do motor ficam em `per-file-ignores` até o dono do arquivo corrigir.

## Alternativas descartadas

- **GitHub Actions / fila de merge do GitHub:** proibido pela política da organização.
- **Framework `pre-commit`:** mais uma dependência e não resolve o pouso serializado; o hook versionado em `.githooks/` basta.
- **Bloquear rede só com variável de ambiente nos testes:** não impede um teste de abrir socket; o `pytest-socket` falha na hora.
