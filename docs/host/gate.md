---
title: Gate local, TDD e pouso de PRs
summary: Como provar que a main está verde com um comando offline, a regra de testes primeiro, o ownership por issue e o pouso serializado sem CI.
commands: make setup, make check, make check-full, make check-web, make hooks, make regen, scripts/check_ownership.py, scripts/check_tdd.py, scripts/land.sh
issue: 31
last_verified: 2026-11-05
---

# Gate local, TDD e pouso de PRs

Não há GitHub Actions (política da organização). A `main` fica verde porque todo PR passa pelo mesmo gate **na máquina de quem pousa**, um de cada vez. Decisão e alternativas: [ADR-0005](../decisoes/ADR-0005-gate-sem-ci.md). Acordo de trabalho em paralelo: [parallel-work.md](../factory/parallel-work.md).

## Como rodar

```bash
make setup        # cria .venv, instala o extra `test` (pytest, pytest-socket, ruff, shellcheck-py) e liga os hooks
make check        # o gate: offline, em paralelo com o pytest-xdist (medidas e orçamento em "Tempo do gate")
make check-full   # check + testes render/integration/ui/slow (podem usar rede)
make check-web    # workspace web (chega com a #34; por enquanto só avisa e sai com 0)
make hooks        # git config core.hooksPath .githooks (o pre-push roda `make check`)
make regen        # regenera os arquivos gerados (plugin.json, schemas, referências)
```

Numa cópia limpa: `python3 -m venv .venv && .venv/bin/pip install -e '.[test]' && make check`.

`make check` descobre a issue e a base sozinho: a issue vem do nome do branch (`feat/31-gate`, `loop/issue-31`) e a base é `origin/main`. Para forçar: `ISSUE=31 BASE=origin/main make check`. Sem issue ou sem base, as checagens de ownership e TDD são puladas com um aviso.

As checagens também rodam sozinhas:

```bash
scripts/check_ownership.py 31 --base origin/main   # só paths da issue (0 ok, 1 fora do escopo, 2 erro de uso)
scripts/check_tdd.py --base origin/main            # testes primeiro (aceita --labels tdd-exempt ou PR_LABELS)
scripts/check.sh --help                            # variáveis do gate
```

As trilhas estendem o gate sem editar o `Makefile`: criam `mk/<trilha>.mk` com `CHECKS += alvo`, `REGEN += alvo` ou `CHECKS_WEB += alvo` e definem o alvo.

## O que é verificado

`make check` roda `scripts/check.sh`, nesta ordem:

| Etapa | O quê |
|---|---|
| ruff | `ruff check .` com `[tool.ruff]` do `pyproject.toml`: só `src/simplicio_video` e `scripts`; mais os `.py` que o branch alterou (qualquer pasta) |
| shellcheck | `scripts/*.sh` e `.githooks/*` |
| testes | `pytest -m "not slow and not render and not integration and not ui"`, `SIMPLICIO_OFFLINE=1`, sockets bloqueados; com o pytest-xdist (extra `test`) em `-n auto --dist loadscope` (`CHECK_JOBS=1` roda em série) |
| ownership | `scripts/check_ownership.py <issue> --base <base>` |
| TDD | `scripts/check_tdd.py --base <base>` |

**Marcadores** (registrados em `pyproject.toml`): `unit` (padrão de todo teste sem marcador), `contract`, `e2e`, `integration`, `render`, `ui` e `slow`. `render`, `integration`, `ui` e `slow` ficam fora do `make check`.

**Sem rede nos testes.** `addopts` liga `--disable-socket --allow-unix-socket` (pytest-socket): um teste que abre socket falha com `SocketBlockedError`. `render`, `integration` e `ui` são liberados em `tests/conftest.py` (o render chama `npx`). Três testes antigos sobem um servidor em `127.0.0.1`; eles só falam com o loopback (`LOOPBACK_TESTS` no `conftest.py`).

**Testes que rodam subprocessos** (`run_cli`) não são cobertos pelo guarda em processo, então `conftest.offline_env()` injeta o mesmo guarda no Python filho (`sitecustomize`) e exporta `SIMPLICIO_OFFLINE=1`. O motor respeita a variável: `montage clone` se recusa a baixar o OpenMontage em modo offline.

**Testes herméticos.** Um fixture automático aponta `SIMPLICIO_VIDEO_DATA` para um diretório temporário, limpa `OPENMONTAGE_DIR`/`SIMPLICIO_TOOLS_DIR` e troca `tools._git` por uma função que falha: nenhum teste clona nada nem toca no `~/.simplicio-video`. O OpenMontage fica em `$SIMPLICIO_VIDEO_DATA/tools/openmontage` (padrão `~/.simplicio-video/tools/openmontage`).

**Ownership.** Cada issue só pode alterar os paths de `docs/factory/ownership.yaml`. `path#secao` marca um arquivo compartilhado (o script libera o arquivo e avisa; o revisor confere a seção); `generated` vale para todas as issues e vem de `make regen`. Issue em `status: backlog` não começa. O próprio `ownership.yaml` só pode mudar na entrada da issue.

## Tempo do gate

Orçamento: 60 s. Os testes do gate rodam em paralelo com o pytest-xdist (`-n auto --dist loadscope`: um módulo inteiro por worker, para os fixtures de módulo não se repetirem). Sem o xdist, ou com `CHECK_JOBS=1`, rodam em série.

Medidas de 2026-11-05 nesta máquina (4 núcleos). Outras sessões rodavam testes no mesmo host durante as medidas (load médio de 5 a 13), então o wall é pessimista; a CPU (usuário + sistema de toda a árvore do `make check`) varia menos:

| Medição | `make check` (wall) | CPU | pytest do gate | Resultado |
|---|---|---|---|---|
| antes (`main`, 143a804), serial | 533 s | não medido | 528 s | 4469 passaram, 8 pulados |
| depois, serial (`CHECK_JOBS=1`) | 269 s | 247 s | 261 s | 4384 passaram, 8 pulados |
| depois, paralelo (`-n auto`, 4 workers) | 128 s | 270 s | 123 s | 4384 passaram, 8 pulados |

Outra medida paralela do mesmo estado deu 154 s de parede e 256 s de CPU; a CPU é a medida mais estável.

O trabalho caiu pela metade em série (528 para 261 s de pytest) e o paralelo leva 250 a 270 s de CPU a 125 a 155 s de parede nesta máquina ocupada. Com os 4 núcleos livres a estimativa é ~70 a 75 s (CPU / 4, mais ~8 s dos passos seriais: ruff, shellcheck, docs e licenças). **Não chegou a 60 s**, e não medi em máquina livre.

O que segura o resto é o custo de subir o CLI: `python -m simplicio_video` gasta ~0,2 s de CPU só para importar a árvore de comandos, e centenas de testes sobem o CLI em subprocesso. Tirar isso exige adiar importações no CLI, o que fica para outra tarefa.

O que saiu do gate (85 testes, 80 funções). Eles rodam em `make check-full` (`pytest -m slow`: 99 testes passam, incluindo os que já eram lentos):

- concorrência com tempo real do swap e da voz (`test_swap_concurrency.py` 18, `test_voice_concurrency.py` 13): precisam de latência de verdade para provar o paralelismo;
- ffmpeg e render reais: `test_swap.py` 3, `test_openverse.py` 5, `test_perfis_saida.py` 3, `test_trilha_cortes.py` 2, `test_voice.py` 1, `test_ducking_duas_bandas.py` 1, `test_marca_contrato.py` 1, `test_scripts/test_bench_concurrency.py` 2;
- processos com tempo limite e morte do grupo: `test_instagram.py` 5, `test_jobs.py` 3, `test_montage_run_tool.py` 3, `test_childio.py` 2, `test_download.py` 1, `test_matchcut.py` 1, `test_moneyprinter.py` 1, `test_montage_hardening.py` 1, `test_rea_video.py` 1, `test_smoke_trilhas_script.py` 1, `packaging/test_smoke_so.py` 1, `packaging/test_install_seguranca.py` 1;
- CLI inteiro e medições de tempo: `packaging/test_cli_install.py` 4 (instalação global nas 12 pastas), `test_busca.py` 4, `test_social.py` 1, `test_scripts/test_gate_files.py` 1 (`make regen` numa cópia do repo).

Regra: vai para `slow` o teste que leva mais de cerca de 1 s no corpo (medido com a máquina ocupada) e o que depende de tempo real. Ficam no gate os guardas de contrato: o snapshot das tools MCP, a allowlist sem entradas antigas, o `install` sem PyYAML, o help documentado do matchcut e o guarda de dado de cliente no pacote.

Outras mudanças no conjunto de testes, sem tirar nenhum teste do release:

- `clone --help` põe um `hypit` falso no PATH: sem ele o teste chamava `npx --yes @hypit/hypit@<versão>`, que baixa do registro quando o cache está frio, fora do guarda de sockets (que não alcança o subprocesso). 0,6 s em vez de 5,8 s.
- `test_gen_reference.py`: uma geração por módulo (fixture); antes eram 9 execuções do gerador.
- `test_gate_files.py`: `make regen` roda numa cópia do repo; antes regravava `docs/` do próprio checkout enquanto outros testes liam esses arquivos.
- `test_ducking_duas_bandas.py`: o cenário é um por módulo, não um por teste.
- `test_swap_concurrency.py`: o piso de `generation_s` caiu de 0,25 s para 0,1 s. A medida começa no primeiro poll que vê `running`, que atrasa sob carga; a asserção continua exigindo que a latência seja registrada.
- `test_voice.py`: `import json` sem uso removido (o ruff roda em todo `.py` alterado no branch).
- `docs/licenses.md` regenerado com `make licenses-write` (pytest-xdist 3.8.0 e execnet 2.1.2, ambos MIT).
- `pyproject.toml`: `pytest-xdist>=3.6` no extra `test`; `scripts/check.sh` usa `-n` quando o xdist está instalado (`CHECK_JOBS`).

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
| `make check` passou de 60 s | o script avisa. Veja o tempo de CPU na seção "Tempo do gate" antes de mexer: pode ser a máquina ocupada. Se for o teste, marque-o `slow` (`check-full` roda) |
| `ruff` acusa um import sem uso num arquivo que você só tocou | o ruff roda em todo `.py` alterado no branch, não só em `src/` e `scripts/`: corrija o import (o achado pode já existir na `main`) |
| `No module named pip` em `test_dados_pacote` (`check-full`) | a venv foi criada pelo `uv venv` (`scripts/dev_install.sh`), que não traz pip: `uv pip install --python .venv/bin/python pip`, ou crie a venv com `make setup` |
| rebase com conflito | o `land.sh` aborta o rebase; resolva no branch e rode de novo |
| `openmontage` não é encontrado | `simplicio-video montage clone` (precisa de rede) ou `OPENMONTAGE_DIR=<checkout>` |
