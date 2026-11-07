---
title: Gate local, TDD e pouso de PRs
summary: Como provar que a main está verde com um comando offline, a regra de testes primeiro, o ownership por issue e o pouso serializado sem CI.
commands: make setup, make check, make check-full, make hooks, make regen, scripts/check_ownership.py, scripts/check_tdd.py, scripts/land.sh
issue: 31
last_verified: 2026-11-06
---

# Gate local, TDD e pouso de PRs

Não há GitHub Actions (política da organização). A `main` fica verde porque todo PR passa pelo mesmo gate **na máquina de quem pousa**, um de cada vez. Decisão e alternativas: [ADR-0005](../decisoes/ADR-0005-gate-sem-ci.md). Acordo de trabalho em paralelo: [parallel-work.md](parallel-work.md).

## Como rodar

```bash
make setup        # cria .venv, instala o extra `test` (pytest, pytest-socket, ruff, shellcheck-py) e liga os hooks
make check        # o gate: offline, em paralelo com o pytest-xdist (medidas e orçamento em "Tempo do gate")
make check-full   # check + testes render/integration/ui/slow (podem usar rede)
make hooks        # git config core.hooksPath .githooks (o pre-push roda `make check`)
make regen        # regenera os arquivos gerados (docs/reference, blocos GENERATED, campos do plugin.json, docs/licenses.md e o espelho skills/)
```

Numa cópia limpa: `python3 -m venv .venv && .venv/bin/pip install -e '.[test]' && make check`.

O espelho `skills/` da raiz e o bloco `GENERATED skills` do `.gitignore` saem de `src/simplicio_video/data/skills/` por `scripts/sync_skills.py`: `make regen` regrava e `make docs` (portanto `make check`) roda `--check`. Não edite `skills/` à mão; se `make check` acusar o espelho, rode `make regen`.

`make check` descobre a issue e a base sozinho: a issue vem do nome do branch (`feat/31-gate`, `loop/issue-31`) e a base é `origin/main`. Para forçar: `ISSUE=31 BASE=origin/main make check`. Sem issue ou sem base, as checagens de ownership e TDD são puladas com um aviso.

As checagens também rodam sozinhas:

```bash
scripts/check_ownership.py 31 --base origin/main   # só paths da issue (0 ok, 1 fora do escopo, 2 erro de uso)
scripts/check_tdd.py --base origin/main            # testes primeiro (aceita --labels tdd-exempt ou PR_LABELS)
scripts/check.sh --help                            # variáveis do gate
```

As trilhas estendem o gate sem editar o `Makefile`: criam `mk/<trilha>.mk` com `CHECKS += alvo` ou `REGEN += alvo` e definem o alvo.

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

**Ownership.** Cada issue só pode alterar os paths de `scripts/ownership.yaml`. `path#secao` marca um arquivo compartilhado (o script libera o arquivo e avisa; o revisor confere a seção); `generated` vale para todas as issues e lista só arquivo inteiro que `make regen` escreve (`docs/reference/**`, `docs/licenses.md`, `skills/**`). Todo padrão de `owns` casa um arquivo (`tests/test_scripts/test_ownership_yaml.py`); o que ainda não casa fica no bloco `backlog` da issue, que não vale como posse: a issue que começa move o que cria para o `owns` dela. Issue em `status: backlog`, ou só com padrões no `backlog`, não começa. O próprio `ownership.yaml` só pode mudar na entrada da issue (`issues` e `backlog`).

## Tempo do gate

Orçamento: 240 s (`CHECK_BUDGET_S`; o padrão era 60 s, que o gate nunca cumpriu, e o aviso disparava em toda execução). Os testes do gate rodam em paralelo com o pytest-xdist (`-n auto --dist loadscope`: um módulo inteiro por worker, para os fixtures de módulo não se repetirem). Sem o xdist, ou com `CHECK_JOBS=1`, rodam em série.

Medidas de 2026-11-05 nesta máquina (4 núcleos). Outras sessões rodavam testes no mesmo host durante as medidas (load médio de 5 a 13), então o wall é pessimista; a CPU (usuário + sistema de toda a árvore do `make check`) varia menos:

| Medição | wall | CPU | pytest do gate | Resultado |
|---|---|---|---|---|
| antes (`main`, 143a804), `make check` serial | 533 s | não medido | 528 s | 4469 passaram, 8 pulados, 26 desmarcados |
| main atual (bd99ed9, com o PR #183 e os PRs seguintes), pytest serial, mesma seleção do gate | 271 s | 260 s | 270 s | 4950 passaram, 8 pulados, 97 desmarcados |
| main atual (bd99ed9), `make check` paralelo (`-n auto`, 4 workers) | 108 s | 286 s | 104 s | 4950 passaram, 8 pulados |
| PR #183 antes desta correção (4403 testes), pytest serial / `make check` paralelo | 286 s / 117 s | 249 s / 277 s | 285 s / 112 s | 4403 passaram, 8 pulados |

A CPU é a medida mais estável. A linha serial foi medida com load de 2 (pouca contenção); as outras, com load de 6 a 13. A comparação de wall com a linha de 143a804 não é exata: a main ganhou testes de outros PRs desde então (gate de 4477 para 4958 itens). Na branch do PR #183 o `make check` paralelo deu 128 s, 154 s e 117 s em três medidas, com CPU de 256 a 277 s.

Na main atual o paralelo leva 286 s de CPU a 108 s de parede. Com os 4 núcleos livres a estimativa é ~80 s (CPU / 4, mais ~8 s dos passos seriais: ruff, shellcheck, docs e licenças); não medi isso em máquina livre. **Não chegou a 60 s.**

O que segura o resto é o custo de subir o CLI em subprocesso, e centenas de testes fazem isso. Medido nesta máquina (média de 8 processos, CPU de usuário mais sistema): `python -c pass` gasta 18 ms; importar `simplicio_video.cli` gasta 146 ms no total; `python -m simplicio_video --help` gasta 183 ms. Tirar isso exige adiar importações no CLI, o que fica para outra tarefa.

O que saiu do gate, no PR #183 (contado contra 143a804): 69 testes coletados (68 funções; o 69º é a variante de 200 mil colchetes do texto hostil). Eles rodam em `make check-full`. Medido na main atual: `pytest -m slow` dá 83 testes, todos passam (incluem os que já eram lentos, como os de wheel e sdist, que precisam de pip na venv):

- concorrência com tempo real do swap e da voz (`test_swap_concurrency.py` 18, `test_voice_concurrency.py` 13): precisam de latência de verdade para provar o paralelismo;
- ffmpeg e render reais: `test_swap.py` 2, `test_openverse.py` 3, `test_perfis_saida.py` 3, `test_trilha_cortes.py` 1, `test_voice.py` 1, `test_ducking_duas_bandas.py` 1, `test_marca_contrato.py` 1, `test_scripts/test_bench_concurrency.py` 2;
- processos com tempo limite e morte do grupo: `test_instagram.py` 5, `test_jobs.py` 2, `test_montage_run_tool.py` 3, `test_childio.py` 2, `test_download.py` 1, `test_matchcut.py` 1, `test_moneyprinter.py` 1, `test_montage_hardening.py` 1, `test_rea_video.py` 1, `test_smoke_trilhas_script.py` 1, `packaging/test_smoke_so.py` 1, `packaging/test_install_seguranca.py` 1;
- medições de tempo e regeneração completa: `test_busca.py` 2 (`variaveis_de_ambiente` 1,4 s e `status_com_saida` 1,1 s) mais a variante de 200 mil colchetes do texto hostil (~1 s), e `test_scripts/test_gate_files.py` 1 (`make regen` numa cópia do repo).

Regra: vai para `slow` o teste que leva mais de 1 s no corpo (medido com a máquina ocupada) e o que depende de tempo real. Os que medem menos de 1 s voltaram ao gate: os quatro de `test_cli_install.py` (instalação global), a ordem dos trechos do `test_trilha_cortes.py`, a voz local em segundo plano do `test_jobs.py`, a atualização do `test_openverse.py` e o `test_social.py` (`test_cli_providers_json_e_texto`, 0,55 s). Duas exceções à regra, por decisão de revisão: o apóstrofo no caminho do concat do `test_swap.py` mede 1,17 s e fica no gate porque não tem irmão lá; e as cinco variantes do texto hostil medem 0,2 a 0,35 s e voltam ao gate. Ficam no gate os guardas de contrato: o snapshot das tools MCP, a allowlist sem entradas antigas, o `install` sem PyYAML, o help documentado do matchcut, o guarda de dado de cliente no pacote, a trava de pasta do swap (`test_trava_da_pasta_recusa_a_segunda_execucao_e_solta_ao_sair`, determinística; o teste de duas execuções reais na mesma pasta é slow) e os guardas de ReDoS: as razões de `_linha` (limite 10 000, 100 mil sobre 10 mil colchetes, limite 14 sobre linear ~10) e de `_texto_pagina` (400 mil sobre 25 mil, limite 21 sobre linear ~16), a contagem de chamadas da regex de link (1 por limpeza, determinística) e o teste de 1 milhão de colchetes, que mede 1M contra o corte (`_texto_pagina` sobre 400 mil, razão < 1,6; `_linha` sobre 10 mil, razão < 2; limpo ~1,0, sem o corte 2,5 e 100) e tem dois tetos absolutos de CPU (`_texto_pagina` < 4 s, `_linha` < 0,12 s; medido limpo 1,12 a 1,22 s e 26 a 34 ms). Tudo mede tempo de CPU da thread (`time.thread_time`), não relógio de parede, e as razões vêm de `_razao_cpu`: execuções INTERCALADAS (pequena, grande, grande, pequena, ...) para que um pico de contenção pegue os dois tamanhos, mínimo de cada tamanho sobre todas as rodadas, e parada na primeira rodada (a partir da 2a, no máximo 4 a 6) em que a razão dos mínimos fica abaixo do limite: limpo gasta 2 rodadas, só um quadrático gasta todas e falha. Motivo: um revisor mediu, com 8 queimadores de CPU em 4 CPUs (20 execuções), 3,35 a 4,72 no guarda antigo de 25 mil/100 mil (limite 4,8), 11,29 no de `_linha` (limite 12,5) e 4,46 no do amplificador (limite 5): SMT e cache compartilhado inflam a CPU do tamanho grande de forma desigual. Tamanhos maiores deixam o termo quadrático pesar mais, então o limite fica ~1,3x o linear (antes ~1,2x do linear com 2% de folga em host carregado). Medido com 20 execuções do teste inteiro, limpo e com 8 queimadores em 4 CPUs: `_linha` 9,8 a 10,8, `_texto_pagina` 15,5 a 16,8, 1M/400 mil 0,97 a 1,04, 1M/10 mil 0,92 a 1,15; nunca acima de 80% do limite. Se a resolução do relógio de CPU passa de 0,5 ms (Windows), esses testes pulam com o motivo. O teste do texto hostil (`< 8 s`, seis variantes) também mede CPU da limpeza (medido 0,2 a 0,35 s). Exceção que continua em relógio de parede: `test_binario_lento_estoura_o_tempo_maximo_e_e_morto` (`< 10 s`, timeout de 0,6 s), porque o que se mede é um filho dormindo; leva ~1 s, folga de ~10x. **O que o gate de ReDoS não pega** (medido; mutação = quadrático em Python que varre o texto a cada `passo` caracteres, limpo e com 8 queimadores em 4 CPUs): passo 512 em `_texto_pagina` (razão 16,6 a 17,1 contra limite 21) e passo 64 em `_linha` (10,9 a 11,2 contra 14). O passo 64 posto em `_texto_pagina` ou em `_limpa_html` fica vermelho só pelo teste de `_texto_pagina` (22,0 a 22,7 contra 21: 7 de 7 execuções, mas colado no limite, não é confiável). Pegos com folga: passo 8 (`_texto_pagina` 57 a 60, `_linha` 17,0 a 18,1), passo 16 (39 a 40), passo 1 em `_linha` (45 a 48); corte de leitura removido (`_texto_pagina` 2,5 contra 1,6; `_linha` 102 contra 2) e regex de link por passada (contagem). O limiar é ~+30% sobre o custo linear em 400 mil (`_texto_pagina`) e ~+40% em 100 mil (`_linha`). Um ReDoS exponencial travaria o gate, nos testes antigos e nos novos: não há timeout por teste (o `pytest-timeout` não é dependência do repo).

Outras mudanças no conjunto de testes, sem tirar nenhum teste do release:

- `clone --help` põe um `hypit` falso no PATH: sem ele o teste chamava `npx --yes @hypit/hypit@<versão>`, que baixa do registro quando o cache está frio, fora do guarda de sockets (que não alcança o subprocesso). 0,6 s em vez de 5,8 s.
- `test_gen_reference.py`: duas execuções do gerador por módulo, não uma: a do fixture, que os testes que leem a saída compartilham, e a de outro cwd, que prova o determinismo. Antes eram 10.
- `test_busca.py`: o amplificador ganha um teste de razão no gate, e o teto de 1 milhão de colchetes virou razão de CPU contra o corte (400 mil / 10 mil), sem limite em segundos; cinco das seis variantes do texto hostil voltam ao gate. As razões usam execuções intercaladas e mínimo sobre rodadas (`_razao_cpu`), tamanhos maiores e limites ~1,3x do linear.
- `test_openverse.py`: o export que recusa CC-BY sem autor ou sem licença grava a aprovação direto no `index.json`, sem folha e sem ffmpeg.
- `test_gate_files.py`: `make regen` roda numa cópia do repo; antes regravava `docs/` do próprio checkout enquanto outros testes liam esses arquivos.
- `test_ducking_duas_bandas.py`: o cenário é um por módulo, não um por teste.
- `test_swap_concurrency.py`: o piso de `generation_s` caiu de 0,25 s para 0,1 s. A medida começa no primeiro poll que vê `running`, que atrasa sob carga; a asserção continua exigindo que a latência seja registrada.
- `test_voice.py`: `import json` sem uso removido (o ruff roda em todo `.py` alterado no branch).
- `docs/licenses.md` regenerado com `make licenses-write` (pytest-xdist 3.8.0 e execnet 2.1.2, ambos MIT).
- `pyproject.toml`: `pytest-xdist` entrou no extra `test` (fixado com `==`, versão em `docs/licenses.md`); `scripts/check.sh` usa `-n` quando o xdist está instalado (`CHECK_JOBS`).

## Processos filhos e sinais de parada (`childio`)

Regra para qualquer módulo que inicia um processo filho de longa duração (render, servidor, script de terceiros): **o filho não pode sobreviver ao motor por causa de um SIGTERM, SIGHUP ou Ctrl+C**, nem quando o sinal cai no intervalo entre o `fork` e o retorno do `Popen` (nesse intervalo o motor ainda não tem referência para matar). A API fica em `src/simplicio_video/childio.py`:

| API | Para quê |
|---|---|
| `childio.guarded_child(argv, stop=, kill=, **kw)` | context manager no lugar de `subprocess.Popen(argv, **kw)`. Do `fork` até o fim do bloco, SIGTERM, SIGHUP e Ctrl+C são pegos; o que cai durante o `Popen` espera o filho existir, então o filho morre e a parada sobe (`KeyboardInterrupt` no Ctrl+C, `SystemExit(128+n)` nos outros; `stop=childio.stop_as_interrupt` faz todos virarem `KeyboardInterrupt`). Um erro do corpo também mata o filho. Saída normal devolve o filho ao chamador. Os handlers anteriores voltam ao fim, também se o `Popen` falhar |
| `childio.start_child(argv, track=lista, **kw)` | o mesmo para servidores que o chamador para num `finally`: o filho entra em `track` antes de qualquer sinal ser tratado; depois do retorno, parar é com o chamador |
| `childio.kill_group(proc, group=True)` | `SIGKILL` no grupo do filho (`start_new_session=True`) ou só nele, e reapa. Recusa pid <= 1, o próprio pid e o próprio grupo. Filho que já saiu e foi reapado: com `group=False` nada é sinalizado (o pid pode ser de outro processo); com `group=True` (o chamador diz que o filho liderava o grupo) o **grupo ainda é varrido**, porque os netos sobrevivem ao líder e o Linux não reutiliza um pid enquanto existe um grupo com esse id (grupo vazio é `ESRCH`). Limite: se o grupo inteiro já morreu e o pid foi reutilizado por um novo líder de sessão, o `killpg` o atingiria; é a mesma janela teórica do `killpg` direto dos módulos. `group=True` num filho vivo sem grupo próprio mata só o filho |

Detalhes que valem: sinal **ignorado** continua ignorado (semântica do `nohup`); Ctrl+C só é tomado enquanto o handler padrão do Python estiver no lugar; fora da thread principal nada é instalado e a guarda vira um `Popen` comum (o erro do corpo ainda mata o filho); um segundo sinal durante a morte do filho é só anotado, nunca corta a morte; `restore` devolve todos os handlers mesmo que um handler restaurado levante. `kill=` aceita uma parada própria (toonflow e moneyprinter param o servidor com Ctrl+C antes do `SIGKILL`). Envolva o bloco num `ExitStack` para distinguir erro de spawn de erro do corpo.

**Servidor MCP (threads de trabalho).** As tools síncronas do servidor MCP rodam em threads de trabalho, onde `signal.signal` não funciona e a guarda do `guarded_child` não pega sinal. Por isso o `childio` mantém um registro dos filhos que estão sob guarda (`live_children()`; entram quando o filho existe e saem quando o bloco termina, de modo que um filho devolvido ao chamador ou do `start_child` não está lá) e `mcp_server.main` chama `childio.install_exit_guard()` uma vez, na thread principal: SIGTERM, SIGHUP e Ctrl+C no servidor matam os filhos registrados (cada um com o `kill=` do seu bloco; também o que uma thread ainda está iniciando; um filho que começaria depois da varredura nem é criado) e encerram o processo com 128+n por `os._exit`, sem esperar thread de trabalho (esperar seria esperar um render). Sinal ignorado continua ignorado. `install_exit_guard` devolve o que fez: `GUARD_INSTALLED`, `GUARD_ALREADY` (já instalado, nada mudou), `GUARD_NOT_MAIN` (chamado fora da thread principal: nada instalado) ou `GUARD_NOTHING` (todo sinal de parada é ignorado ou tratado pelo motor); `uninstall_exit_guard()` desfaz (para testes). O CLI não chama `install_exit_guard`: seus blocos pegam os sinais sozinhos, nada muda. O runner de `jobs` é desanexado de propósito (`Popen` simples em `jobs._spawn_runner`, fora do registro): parar o servidor não cancela tarefa em segundo plano.

Regras do handler de saída (`childio._exit_handler`), aprendidas com falhas medidas: **nada nele pode bloquear** no que outra thread, ou a própria thread mais acima na pilha, possa estar segurando: sem lock compartilhado, sem `threading.Event`/`Condition` (o `Event.set` pega um lock não reentrante, e um segundo sinal dentro dele travava o motor para sempre, com os filhos vivos), sem flush de stream. A bandeira de saída é um booleano simples; o handler lê `_spawning` depois de marcar a bandeira e `_starting` conta o início antes de olhar a bandeira (sem lock entre os dois: ou o início vê a bandeira e não cria nada, ou o handler vê o início e espera). Um segundo sinal só roda o handler de novo (vale o código do primeiro). Além disso, o CPython só roda handler Python na thread principal, e o SO pode entregar o sinal a uma thread de trabalho (acontece em rajada, quando a principal já tem um pendente): com a principal dormindo num syscall o handler esperaria ela acordar. Por isso `install_exit_guard` também liga `signal.set_wakeup_fd` a um pipe lido por uma thread daemon (`exit-guard`) que roda o mesmo handler na hora, só para sinal cujo handler ainda é o nosso. Se algo depois trocar o wakeup fd (o `add_signal_handler` do asyncio, hoje não usado), só o caminho pela thread principal resta, como era antes.

Mudança visível: sob o MCP, SIGTERM agora termina com código 143 (antes: morte por sinal, -15) e SIGINT com 130, com os filhos mortos; SIGHUP com 129. Limite: `os._exit` não roda `finally` das threads, então pastas privadas de uma tool (ex.: a de `rea_video.mcp_run`) ficam no disco, como já ficavam com a ação padrão do SIGTERM. Fora do registro, e portanto fora desta garantia: o que `run_child`/`check_child` iniciam sob o MCP (`subprocess.run` simples, no grupo do servidor); fica para outro PR.

Testes: `tests/test_childio_guarded.py` e o auxiliar `tests/_orfao.py` (`sinaliza_no_popen` sinaliza de dentro do `Popen`, o intervalo; `roda_motor` roda o módulo num processo de motor próprio; `limpa` mata o filho mesmo que o teste falhe cedo). Todo teste que cria um dorminhoco **espera o pid file** antes de qualquer asserção e limpa num `finally`: sob carga um teste que sai antes de o filho escrever o pid vazava dorminhocos de 120 s.

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
| `make check` passou de 240 s | o script avisa (`CHECK_BUDGET_S` muda o limite). Veja o tempo de CPU na seção "Tempo do gate" antes de mexer: pode ser a máquina ocupada. Se for o teste, marque-o `slow` (`check-full` roda) |
| `ruff` acusa um import sem uso num arquivo que você só tocou | o ruff roda em todo `.py` alterado no branch, não só em `src/` e `scripts/`: corrija o import (o achado pode já existir na `main`) |
| `No module named pip` em `test_dados_pacote` (`check-full`) | a venv foi criada pelo `uv venv` (`scripts/dev_install.sh`), que não traz pip: `uv pip install --python .venv/bin/python pip`, ou crie a venv com `make setup` |
| rebase com conflito | o `land.sh` aborta o rebase; resolva no branch e rode de novo |
| `openmontage` não é encontrado | `simplicio-video montage clone` (precisa de rede) ou `OPENMONTAGE_DIR=<checkout>` |
