---
title: Pacote de operação (install, update, doctor, setup)
summary: O que cada subcomando faz, o que o doctor checa, por que a falta de GEMINI_API_KEY é aviso e os limites até as #32 e #34.
commands: ./install.sh, bash scripts/dev_install.sh, powershell -NoProfile -ExecutionPolicy Bypass -File scripts\dev_install.ps1, simplicio-video install, simplicio-video update, simplicio-video doctor, simplicio-video setup, python scripts/smoke_so.py, docker compose build
issue: 43
last_verified: 2026-10-17
---

# Pacote de operação

Como o host instala, atualiza, checa e prepara o workspace, e o que o CLI faz (e não faz) com o login do Simplicio Runtime: ele não lê, não grava e não apaga esse arquivo. Passo a passo para quem vai usar: [docs/how-to/install.md](../how-to/install.md). Decisões: [ADR-0020](../decisoes/ADR-0020-install-universal-e-update-igual-ao-loop.md) (`install` universal e `update` iguais aos do simplicio-loop, que **supersede** a decisão do [ADR-0017](../decisoes/ADR-0017-instalacao-atualizacao.md) sobre o `.venv` e o `git pull`) e [ADR-0019](../decisoes/ADR-0019-login-compartilhado.md) (login compartilhado). Como rodar a fumaça em Windows e macOS: [testar-em-windows-e-macos.md](../how-to/testar-em-windows-e-macos.md).

Os contratos de `install`, `update` e `doctor` seguem o do simplicio-loop (mesmos códigos de saída, mesmos `reason_code`, mesmos documentos `simplicio.video-install-plan/v1` (o `simplicio.loop-install-plan/v1` com as mesmas chaves), `simplicio.doctor/v1`).

## Os comandos

| Comando | O que faz | Toca em |
|---|---|---|
| `./install.sh` (Windows: `.\install.ps1`) | invólucro fino de `scripts/dev_install.sh` (Windows: `scripts/dev_install.ps1`), com as mesmas opções (`--dry-run`, `--with`, `--python`; no PowerShell `-DryRun`, `-With`, `-Python`) | nada fora do checkout; sem sudo |
| `bash scripts/dev_install.sh [--with EXTRAS] [--python X] [--dry-run]` (Windows: `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\dev_install.ps1`) | o ambiente de desenvolvimento do checkout, como o `scripts/dev_install.sh` do loop: checa Node 22, ffmpeg com libass e 5 GB livres; garante o uv (oferece instalar, só com confirmação); cria o `.venv` com `uv venv` e instala o pacote editável (`uv pip install -e .[extras]`); constrói `web/` se existir; roda o doctor e imprime os próximos passos. Rodar de novo não estraga nada; um `.venv` com outro Python é um conflito que o script explica e não troca. **Não usa o python do sistema** (o uv traz o Python): por isso um `python3` sem PyYAML, como o do macOS com as ferramentas do Xcode, não atrapalha. O `.ps1` é **UNVERIFIED**: nunca rodou num Windows de verdade; o `-ExecutionPolicy Bypass` vale só para esse processo (o Windows de cliente vem com a política `Restricted`, e `powershell -File x.ps1` pararia com "running scripts is disabled") | só `.venv` (e `web/`) dentro do checkout |
| `simplicio-video install [--target DIR] [--global] [--host H] [--dry-run] [--check] [--json] [--verify] [--uninstall] [--prune-project-copies]` | copia as skills empacotadas (`simplicio-video` e `simplicio-video-social`) para o host do agente e grava o recibo `.simplicio-video/install-ownership.json`, **como o `install` do loop**. Padrão: o projeto (`--target`, a pasta atual) em `.claude/skills/` e, para o host que precisa, o arquivo de entrada dele (`AGENTS.md`, `GEMINI.md`, `CONVENTIONS.md`, `.github/copilot-instructions.md`, `.kiro/steering/simplicio-video.md`); `--global` instala nas 11 pastas de skills do loop sob o home (com `--global` o `--host` é ignorado), com a regra de posse (cria o que falta, atualiza só a cópia nossa e não editada, deixa em paz o resto, nunca apaga). Idempotente: arquivo igual não é regravado. Nunca sobrescreve nem apaga o que não é dele (`left_alone`: outras skills, um `AGENTS.md` seu, uma `SKILL.md` que já existia ou que você editou, um arquivo seu dentro da pasta da skill, um link simbólico). `--check` e `--dry-run` não escrevem nada; `--verify` compara os arquivos instalados com o recibo e com o pacote e falha (exit 1, `ok: false`, `problems`) se algo difere; `--uninstall` remove só o que o recibo registra e ainda tem o `sha256` gravado; `--prune-project-copies` (com `--global`) faz o mesmo com o recibo do projeto e nunca toca a instalação global. **O simplicio-video não tem hooks: só skills.** Funciona igual num checkout e num pacote do pip, e só usa a biblioteca padrão (o `python3 -m simplicio_video install` do sistema não precisa de PyYAML; um teste roda tudo num interpretador que bloqueia qualquer terceiro). Com `--json`, o stdout é UM documento mesmo no erro (`status` `error`) | o alvo (o projeto, ou o `~` com `--global`); `.simplicio-video/install.lock` (vazio, `0600`); nunca `site-packages` |
| `simplicio-video update [--check] [--dry-run] [--force]` | num pacote instalado por pip: `python -m pip install --upgrade "simplicio-video==<última release>"` (PyPI) e, depois, `simplicio-video install --global`, que instala ou atualiza as skills nas 11 pastas de hosts sob o home (cria as que faltam, só atualiza o que o recibo registra e o usuário não editou, nunca apaga). **Num checkout git ou instalação editável: recusa** (exit 2) e imprime `git pull` e `bash scripts/dev_install.sh` (Windows: `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\dev_install.ps1`); nada é puxado, reconstruído nem apagado. Um Python sem pip (um `uv tool install`) também recusa (exit 2) e diz `uv tool upgrade` ou `pipx upgrade`. `--check` grava o resultado em `update-check.json`; num checkout ele roda `git fetch`, mostra os commits novos e o diff do CHANGELOG. `--dry-run` só mostra o plano e sai com `0` num pacote, com `--check` ou não (o `--check` sozinho é que responde `10`); num checkout mostra a recusa e **não roda git nenhum** (o `git fetch` regrava `FETCH_HEAD`, as refs `origin/*` e o reflog, então não é um passo de leitura) | o ambiente Python do pip, as skills do `~` (o `install --global` do fim); `~/.simplicio-video/update-check.json` com `--check`; num checkout, nada |
| `simplicio-video doctor [all] [--json] [--online]` | checa o ambiente e diz a correção exata de cada falha. Sem `--online` não usa rede. Não instala e não altera nada; com `--online` regrava só o `update-check.json` | nada (com `--online`, `~/.simplicio-video/update-check.json`) |
| `simplicio-video setup [--yes] [--theme] [--lang] [--force] [--realoficial]` | cria o workspace em `$SIMPLICIO_WORKSPACE` (padrão `~/.simplicio-video/workspaces/default`) com `workspace.yaml` (tema, idioma) e `policy.yaml` (autonomia L1; tokens, USD e créditos zerados). Não faz login nem grava credencial | o workspace |

Todo comando tem `--help` com exemplos. Os testes da suíte conferem isso (`tests/packaging/test_cli_pacote_help.py`).

### Códigos de saída

| Comando | 0 | 1 | 2 | 10 |
|---|---|---|---|---|
| `install --check` | em dia | — | argumento inválido | há mudança pendente (um arquivo a criar ou atualizar, nas 11 pastas com `--global`; uma cópia alheia antiga, que o install não muda, **não** conta) |
| `install --dry-run` | sempre (não escreve nada) | — | argumento inválido | — |
| `install` | instalou ou já estava em dia | falhou: host desconhecido, escrita negada, outro install segurando o `install.lock`, recibo em que não se confia (só o `--uninstall` e o `--prune-project-copies`; o install o ignora e avisa) | argumento inválido (`--prune-project-copies` sem `--global`, ou com o alvo igual ao home), ou uma pasta que o install cria é link (nada foi escrito) | — |
| `install --verify` | os arquivos conferem com o recibo e com o pacote (`ok: true`, `problems: []`) | host desconhecido, versão que não bate, ou **algo difere**: alvo nunca instalado, recibo ausente ou lixo, arquivo faltando, editado, desatualizado ou que já existia e não é nosso (`ok: false`, `problems`) | argumento inválido | — |
| `install --uninstall` | removeu (ou, com `--dry-run`, listou); o que o usuário editou fica (`left_alone`) | sem recibo, ou recibo adulterado, plantado, com outro caminho ou ilegível (nada é apagado), ou o link da pasta base mudou | argumento inválido | — |
| `update --check` | em dia | — | erro (rede, git, sem upstream, não é um repositório) | há atualização |
| `update` | atualizou, já estava em dia, ou o instalado é mais novo que a última release | falha de rede, ou falha de um passo (o pip, ou o `install --global` que o segue) | recusado: é um checkout git ou instalação editável, PEP 668 | — |
| `doctor` | nenhuma falha (aviso não reprova) | alguma checagem é `fail` | argumento inválido | — |

`--force` do `update` reinstala a release do pip mesmo em dia e permite downgrade; num checkout ele também recusa (exit 2). Sem versão mais nova o pip roda `--upgrade --force-reinstall --no-deps` (só o nosso pacote, como o loop faz nos reparos dele); com uma versão mais nova roda o `--upgrade` normal, porque `--no-deps` pularia uma dependência que ela traga. Falha de rede no `update` sai com `2` com `--check` e com `1` sem ele. Se a versão instalada é mais nova que a última release (o PyPI é publicado antes do GitHub Release), o `update` sai com `0` e diz `é mais novo que a última release`, como o loop; só o `--force` instala a release mesmo assim.

A versão instalada segue a ordem da PEP 440: `0.5.0.dev1` < `0.5.0a1` < `0.5.0b1` < `0.5.0rc1` < `0.5.0` < `0.5.0.post1`, e `+local` não conta. Uma versão de desenvolvimento ou pré-release instalada tem atualização frente à release final, mas uma pré-release nunca é alvo de upgrade. Os arquivos que o CLI lê (`update-check.json`, o recibo do install, os arquivos que o install compara com os do pacote, o YAML do workspace) são abertos com `O_NONBLOCK` e conferidos com `fstat` no mesmo descritor: um FIFO, uma pasta ou um dispositivo no lugar vale como cache inválido (aviso no doctor), como ausente ou, onde o install ia escrever, como algo que não é dele (`left_alone`), e nunca trava o comando.

A versão da release é lida com regra estrita: `X.Y`, `X.Y.Z` ou `X.Y.Z.W` com um `v` opcional e o sufixo `.postN`, e nada mais (`v0.5.0-rc1`, `0.5.0 --index-url=...`, `1!2.0.0` e dígitos de largura total são recusados). O argv do pip é remontado só de números: `python -m pip install --upgrade simplicio-video==X.Y.Z`, uma lista, sem shell.

### Rede e `SIMPLICIO_OFFLINE=1`

`SIMPLICIO_OFFLINE=1` bloqueia **toda** a rede do `update` e do `doctor --online`. Num pacote instalado por pip, nem o `gh` nem a API do GitHub são chamados. Num checkout, o `git fetch` do `--check` também não roda (nem `ls-remote` ou qualquer outro comando de rede): `update --check` sai com `2` e o `doctor --online` mostra um aviso; as refs e o `.git` não são tocados. O `update` de um checkout (a recusa) e o `--dry-run` nunca rodam git nenhum, com ou sem a variável, e todo comando git do `--check` usa `--no-optional-locks` para que um passo de leitura não regrave o `.git/index`. Um git anterior à 2.15, que não conhece a opção (`Unknown option: --no-optional-locks`, exit 129), é chamado de novo UMA vez sem ela, então o update continua funcionando (e, nesse git, o `git status` regrava o índice como sempre fez). Quando o git recusa o repositório (`dubious ownership` num checkout de outro usuário, por exemplo), a recusa mostra o que o git disse (uma linha, cortada em 300 caracteres e sem escapes de terminal), e o `--check` não olha a árvore de trabalho (nada é puxado, então alterações locais não atrapalham).

## Duas distribuições: checkout e pacote

`update` e `doctor` perguntam a `distribution.kind()`; `install` não liga para ela (copia a skill do pacote nos dois casos):

- **source**: um checkout git (ou `pip install -e`). O `update` **recusa** e manda rodar `git pull` e `bash scripts/dev_install.sh` (no Windows, `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\dev_install.ps1`); o `--check` pergunta ao git quantos commits são novos.
- **pip**: um pacote instalado (`pip install simplicio-video`). O `install` copia a skill que veio no wheel (`simplicio_video/data/skills`) para o `--target` ou o `~`, e nada é criado em `site-packages`. O `update` faz `pip install --upgrade "simplicio-video==<versão>"`, que vem do PyPI, e depois `simplicio-video install --global`; a versão mais nova vem do GitHub Releases (`gh release view -R simpletibr/simplicio-videos`, ou a API `releases/latest`). Um Python gerenciado pelo sistema (PEP 668) é recusado com as saídas possíveis (`venv`, `uv`, `pipx` ou `PIP_BREAK_SYSTEM_PACKAGES=1`), e um Python sem pip (o venv de um `uv tool install`) também, com `uv tool upgrade simplicio-video` ou `pipx upgrade simplicio-video`.

O pacote ainda não estava no PyPI na última conferência (a página `pypi.org/pypi/simplicio-video/json` respondia 404 em 17/10/2026; ele deve entrar na release 0.5.0): até a primeira publicação, o `update` de um pacote instalado acha a release no GitHub e o `pip install` falha com a mensagem do pip. Dentro do container o pacote é instalado por pip (`Dockerfile`): para atualizar, reconstrua a imagem.

## Os hosts do `install`

O registro é o do planejador do loop (`simplicio_loop/install/planner.py`): `claude`, `codex`, `cursor`, `vscode`, `grok`, `kiro`, `antigravity`, `opencode`, `gemini`, `aider`, `simplicio_agent` e `openclaw` (`--host all` junta todos). As skills vão sempre para `.claude/skills` (o `--global` também); o que muda por host é o arquivo de entrada, criado só se ainda não existir e removido pelo `--uninstall` só se foi o install que o criou:

| Host | Arquivo de entrada (no projeto) |
|---|---|
| `claude`, `cursor`, `simplicio_agent`, `openclaw` | nenhum |
| `codex`, `grok`, `antigravity`, `opencode` | `AGENTS.md` |
| `vscode` | `.github/copilot-instructions.md` |
| `kiro` | `.kiro/steering/simplicio-video.md` |
| `gemini` | `GEMINI.md` |
| `aider` | `CONVENTIONS.md` |

`--global` instala nas **11 pastas** de skills do loop sob o home (a tabela do `skill_sync.py` dele, a mesma nos três sistemas): `.claude/skills`, `.cursor/skills`, `.codex/skills`, `.grok/skills`, `.agents/skills`, `.copilot/skills`, `.vscode/simplicio-skills`, `.config/opencode/skills`, `.config/amp/skills`, `.kiro/steering` e `.simplicio-loop/skills`; o `--host` é ignorado (o loop faz o mesmo). Em cada uma vale a regra de posse: o install cria o que falta e o arquivo entra no recibo com o `sha256`; atualiza só a cópia que é nossa (está no recibo) e não editada, quando o pacote tem uma versão mais nova; deixa em paz (`left_alone`) o que já existia antes ou que você editou, mesmo que de outro host; nunca apaga um arquivo extra seu, nem o que saiu do pacote; o `--check` sai com 10 quando uma cópia nossa e não editada está desatualizada, e uma cópia alheia antiga não o deixa pendente; o `--uninstall` remove só o que é nosso. Uma pasta secundária que é link (um `~/.config/opencode` movido para os dotfiles) é pulada com um aviso e não derruba as outras; `~/.claude/skills` que é link recusa tudo. O `update` do pip chama `install --global` e por isso também é seguro. Um `AGENTS.md` ou `GEMINI.md` que já existe no projeto também não recebe apontador (o loop do checkout mescla um bloco com marcador; aqui o arquivo fica como está). Não foram portados: os hooks e as regras de host do loop (o simplicio-video não os tem; `resynced.rules` fica vazio por contrato) e os hosts "listed" do catálogo do loop que só o `install_lib.py` do checkout dele escreve ([ADR-0020](../decisoes/ADR-0020-install-universal-e-update-igual-ao-loop.md)). Na revisão do #117 se mediu que o `resync` do loop apagava arquivos do usuário nessas pastas (um `minhas-notas.md` sumiu de dois hosts, e o `update` do pip fazia isso sozinho); a regra de posse é o que impede isso aqui.

## O que o `install` nunca toca: recibo, `sha256`, links e a trava

Estas regras vêm da revisão independente do PR #117 (que mediu cada falha) e valem para o `install`, o `--uninstall`, o `--prune-project-copies` e o `--verify`. O recibo é um arquivo do repositório do usuário, e um repositório clonado pode ser hostil.

- **O recibo guarda o `sha256` de cada arquivo.** Um arquivo só é apagado (`--uninstall`, `--prune-project-copies`) ou sobrescrito (um `install` depois) quando está no recibo **e** o `sha256` dele ainda é o que foi gravado. Um arquivo que o usuário editou depois (um `AGENTS.md` com as regras dele, uma `SKILL.md` ajustada) fica como está, entra em `left_alone` e sai com um aviso: nunca é apagado. Um `install` seguinte também o tira do recibo (o arquivo é do usuário agora).
- **Só os caminhos que o registro produz.** O recibo só pode nomear as pastas das skills (`.claude/skills/simplicio-video*/...`), os arquivos de entrada dos hosts (`AGENTS.md`, `GEMINI.md`, `CONVENTIONS.md`, `.github/copilot-instructions.md`, `.kiro/steering/simplicio-video.md`) e ele mesmo. Qualquer outro caminho (`.git/config`, `src/app.py`, `.ssh/authorized_keys`, um byte nulo, um texto gigante) faz o `--uninstall` e o `--prune-project-copies` recusarem o recibo inteiro (exit 1, nada é apagado). Um `install` por cima de um **recibo plantado** num repositório clonado o ignora, avisa e grava um novo: ele não herda os caminhos.
- **O que já existia nunca é tomado.** Um arquivo que já estava no caminho antes do primeiro install (uma `SKILL.md` customizada, uma cópia antiga) não é sobrescrito e não vira do simplicio-video: fica `left_alone` se difere do pacote, e conta só como `unchanged` (sem entrar no recibo, então o `--uninstall` nunca o apaga) se é idêntico. Para o install cuidar da pasta, apague-a ou renomeie e rode de novo. Um arquivo do usuário dentro da pasta da skill (`minhas-notas.md`) também fica intacto e é listado.
- **Links.** Cada pasta que o install **cria** (`.claude/skills`, a da skill, as de dentro dela e `.simplicio-video`) nunca é link: com link o install recusa (exit 2, `InstallRefused`) e não escreve nada, nem pelo link nem ao lado. A **pasta base** do host (`~/.claude`, `.github`, `.kiro`) pode ser link, o caso de quem guarda o `.claude` num repositório de dotfiles: o install a resolve uma vez, escreve no caminho real e grava no recibo (`bases`); o `--uninstall` confere que o link ainda aponta para lá e recusa se mudou. Um arquivo que é link (um `AGENTS.md` que aponta para o `CLAUDE.md`) fica `left_alone`. No Windows, a junção NTFS vale como link (pelo atributo e pela marca de ponto de reparse do `lstat`, também no Python 3.10 e 3.11, que não têm `os.path.isjunction`; UNVERIFIED num Windows real).
- **O `--prune-project-copies` só poda o recibo do projeto.** Com o alvo igual ao home ele sai com 2 (era a instalação global que seria apagada), e uma pasta do projeto que é link para o `~/.claude` (o `.claude` do projeto como link para o do home) não leva embora a instalação global.
- **A trava `.simplicio-video/install.lock`** (vazio, `0600`; espera de 10 s) faz dois installs ao mesmo tempo no mesmo alvo esperarem um pelo outro: sem ela, três installs de hosts diferentes deixavam o `AGENTS.md`, o `GEMINI.md` ou o `CONVENTIONS.md` escritos e fora do recibo. O `--dry-run`, o `--check` e o `--verify` não a tomam e não criam nada; o `--uninstall` a leva embora.
- **O `--verify` olha os arquivos.** Ele compara o que está no disco com o recibo e com o pacote e diz o que difere (`problems`: `no_receipt`, `bad_receipt`, `missing`, `not_a_file`, `modified`, `outdated`, `foreign`). O do loop só confere a versão do plano; um alvo nunca instalado, uma skill adulterada ("poste sem confirmar") e um recibo trocado por lixo passavam com `ok: true`, uma falsa garantia sobre um arquivo de instruções do agente.
- **Um disco que falha no meio** deixa um recibo que bate com o que foi escrito (o `--uninstall` ainda limpa) e nenhuma pasta órfã.
- **Um update que falha não solta o arquivo do recibo.** Se a reescrita de um arquivo nosso falha (disco cheio, permissão, `os.replace` negado no Windows), o arquivo antigo continua no disco e continua no recibo, com o `sha256` antigo: o `--uninstall` ainda o remove e a próxima execução o conserta.
- **Um recibo sem `sha256`** (de uma versão sem ele, ou adulterado) é inválido: o `--uninstall` e o `--prune-project-copies` o recusam inteiro e o `install` o ignora com aviso. Um recibo que é um link também é recusado. Um arquivo maior que o limite de leitura não tem digest e nunca é "nosso".
- **O `--uninstall` de um projeto respeita a instalação global.** Mesmo com `bases` forjado (um repositório com `.claude` apontando para o `~/.claude` e um recibo que grava esse caminho real), as 11 pastas do home nunca perdem arquivo por um uninstall de projeto: o aviso diz que é a instalação global e nada é removido.
- **`--global` pede um home de verdade.** Sem HOME/USERPROFILE resolvível, com o home relativo (`~`, `casa`), igual a `/` ou inexistente, o comando sai com 2 e uma mensagem clara; nunca cria uma pasta chamada `~`.
- **Para depois:** TOCTOU entre a checagem e a escrita (abrir por `dir_fd`), o `python -m pip` do `update` com o diretório atual no `sys.path`, o erro do argparse com `--json`, `ensure_ascii`, a corrida de apagar o `install.lock` e o modo `0700` de `.simplicio-video`.

## O que o doctor checa

As linhas saem nesta ordem. Cada uma tem `name`, `status` (`ok`, `warn` ou `fail`), `summary`, `fix` e `detail` (um objeto).

| Checagem | Falha quando | Aviso quando | Correção mostrada |
|---|---|---|---|
| `update` | — | há versão nova (no cache do último `update --check`, ou na consulta de `--online`), a consulta online falhou, ou o `update-check.json` está corrompido (data ou versão inválida, grande demais) | `simplicio-video update` |
| `distribution` | — | — | mostra `source` ou `pip` e a versão (não há linha de skills: o doctor do loop também não tem) |
| `runtime` | — | — | o Runtime é opcional; mostra versão e caminho quando existe |
| `python` | Python menor que 3.12 | Python 3.14 ou superior (os extras do CrewAI exigem menos de 3.14) | `./install.sh --python 3.12` |
| `node` | ausente, não executa ou versão menor que 22 | — | instalar Node 22 (`nvm install 22`; no Windows, https://nodejs.org) |
| `ffmpeg` | ausente ou não executa | — | `brew install ffmpeg`, `apt install ffmpeg` ou `winget install Gyan.FFmpeg`, conforme o sistema |
| `ffmpeg-libass` | `ffmpeg -version` sem `--enable-libass` | sem ffmpeg não há como checar | reinstalar o ffmpeg com libass |
| `disk` | menos de 5 GB livres (no checkout; num pacote instalado, na pasta de dados `~/.simplicio-video`) | não consegue medir o disco | liberar espaço |
| `ports` | — | 3000 (opencut dev) ou 8000 (montage serve) em uso | parar o processo, ou ignorar se for o seu servidor |
| `GEMINI_API_KEY` | — | variável não definida | definir a chave para voz via Gemini |
| `setup` | `workspace.yaml` ou `policy.yaml` existe e é inválido ou não pode ser lido (permissão, YAML aninhado demais) | falta `workspace.yaml` ou `policy.yaml` (o setup não rodou) | `simplicio-video setup` (`setup --force` para regravar) |

`status` do documento é o pior dos checks, e o exit code é `1` só quando existe algum `fail`. `doctor all` é o mesmo que `doctor`. Com `--online` o doctor consulta a última versão (GitHub num pacote, `git fetch` num checkout) e regrava `update-check.json`.

### Por que GEMINI_API_KEY e o setup são aviso e não falha

A chave é opcional. Sem ela, o MVP usa a voz local, sem custo, e o ambiente funciona. O workspace só é lido por `setup` e `doctor` (nada no motor o usa). Se o doctor reprovasse por causa disso, a instalação ficaria marcada como quebrada num caso que funciona. A regra geral: `fail` só quando o comando seguinte não tem como funcionar, ou quando um arquivo está presente e inseguro ou inválido; `warn` para o que é opcional ou depende de quem usa.

O doctor também nunca mostra o valor de uma credencial nem um token. Ele só informa se a variável está definida (`GEMINI_API_KEY definida (valor oculto)`).

## O login do Simplicio Runtime

O simplicio-video não tem comando de login, logout nem auth. O arquivo de login compartilhado (`~/.simplicio/login.json`, ou `SIMPLICIO_AUTH_FILE`) é do Simplicio Runtime: este CLI não o lê, não o grava, não o apaga e o doctor não checa login. A trava do `install` (`.simplicio-video/install.lock`) é outro arquivo, da própria instalação; o código dela está em `src/simplicio_video/lockfile.py`.

## Os schemas

Em `src/simplicio_video/data/schemas/cli/` (Draft 2020-12), conferidos por `tests/packaging/test_contrato_ops.py` (quatro, mais os cinco do render e do validate):

| Arquivo | `$id` | Para quê |
|---|---|---|
| `doctor.schema.json` | `simplicio.doctor/v1` | saída de `doctor --json` |
| `update-check.schema.json` | (arquivo de estado, sem `schema`) | `update-check.json`: `installed`, `latest`, `update_available`, `kind`, `checked_at`; `commits_behind` só em `source` |
| `install-plan.schema.json` | `simplicio.video-install-plan/v1` | saída de `install --json`: o `simplicio.loop-install-plan/v1` do loop com as mesmas chaves, mais as formas do `--verify` (`verified` ou `failed`, com `problems`), do `--uninstall` (com `left_alone` e `warnings`) e do erro (`status` diz qual) |
| `install-ownership.schema.json` | `simplicio.video-install-ownership/v1` | o recibo `.simplicio-video/install-ownership.json`: `paths`, `dirs`, `sha256` (um por caminho) e, só com a pasta base em link, `bases`; os caminhos são relativos simples |

## Linux, macOS e Windows

O código não assume POSIX: o `install` copia arquivos (nunca cria link simbólico, que no Windows exige privilégio) com escrita atômica e `encoding="utf-8"`; o Python do `.venv` é `Scripts\python.exe` no Windows e `bin/python` nos outros (no `dev_install`); a pasta pessoal vem de `HOME` e, só depois, de `USERPROFILE`, em todo sistema (a ordem do Runtime, `runtime_auth.rs`, e do loop; com `USERPROFILE` na frente no Windows este CLI acharia outra pasta que a do Runtime quando as duas variáveis diferem, como no MSYS2 e no Cygwin); programas são achados no PATH com `PATHEXT` (`simplicio`, `simplicio.exe`, `simplicio.cmd`) e em `~/.simplicio/bin`, **nunca no diretório atual**; o `dev_install` acha o `uv` em `~/.local/bin`, `~/.cargo/bin` e, no macOS, nos prefixos do Homebrew (`/opt/homebrew/bin`, `/usr/local/bin`, também usados para `ffmpeg` e `node`); a trava é `fcntl` no POSIX e `msvcrt` no Windows; o disco é medido com `shutil.disk_usage`; e nenhum passo roda `sh`.

| Sistema | O que foi verificado | O que **não** foi |
|---|---|---|
| Linux | a suíte inteira roda aqui (gate local), `scripts/smoke_so.py` rodou (inclui o install num alvo temporário), `scripts/dev_install.sh` rodou com `uv`, `node` e `ffmpeg` falsos | — |
| macOS | simulado no Linux (`sys.platform`, caminhos do Homebrew, substituto de `open`) | **UNVERIFIED**: nada rodou num macOS de verdade |
| Windows | simulado no Linux (`sys.platform`, `PureWindowsPath`, `msvcrt` falso, PATHEXT, ponto de reparse); o recibo recusa caminho de Windows (letra de unidade, `\\x`, `..\\x`) em qualquer sistema | **UNVERIFIED**: nada rodou num Windows de verdade; `scripts/dev_install.ps1` e `install.ps1` são PowerShell que **nunca foi executado** (só lido por testes estáticos), e não se sabe se o `-ExecutionPolicy Bypass` basta numa máquina com a política travada por Diretiva de Grupo; `msvcrt.locking` × `LockFileEx` do Runtime e as ACLs não foram conferidos |

Windows e macOS reais continuam **UNVERIFIED** até alguém rodar `python scripts/smoke_so.py` (e `python -m pytest tests/packaging`) lá e registrar a tabela. Veja [testar-em-windows-e-macos.md](../how-to/testar-em-windows-e-macos.md). A suíte marca com `posix_real` os testes que precisam de arquivos POSIX de verdade, para a mesma suíte rodar nesses sistemas sem falhar à toa.

## Docker

- `Dockerfile` em três estágios: `node:22-bookworm-slim` (fonte do Node), `python:3.12-slim-bookworm` para o build do venv, e a imagem final com ffmpeg do Debian, Node 22 e um usuário não root (`simplicio`, UID 10001).
- Workspace em `VOLUME ["/workspace"]`, com `SIMPLICIO_WORKSPACE=/workspace`, e `WORKDIR /workspace`: o `init` grava `./clients/<cliente>/<campanha>/contract.yaml` na pasta atual, então o contrato cai no volume e sobrevive ao `docker compose run --rm` (num `WORKDIR` fora do volume ele sumia com o contêiner). `HEALTHCHECK` roda `simplicio-video --version`.
- `compose.yaml` builda a partir do `Dockerfile` e nomeia a imagem `simplicio-video:local`. Não há `image:` pública.
- `deploy/docker/doctor.sh` é um atalho para `docker compose run --rm simplicio doctor`.

Não publicamos imagem pronta. As builds do ffmpeg trazem obrigações de GPL ou LGPL, e a revisão de licença dos componentes empacotados ainda não foi feita (ver [monetization.md](../factory/monetization.md) e [risks-and-policies.md](../factory/risks-and-policies.md)).

## Atualização

A atualização está num módulo só, `src/simplicio_video/commands/update.py`: `pip install --upgrade` num pacote (e o `install --global` que o segue) e a recusa num checkout, que manda rodar `git pull` e o dev install. Se o repositório virar privado com archives assinados, a troca é local nesse módulo. Os comandos e a documentação do usuário não mudam.

## Limites atuais

- **web/ (#34):** o build de `web/` ainda não existe. O `dev_install` registra `web/ chega com a #34: nada a construir` e segue.
- **Workspace de checagem (#35):** o doctor checa só a presença e o schema do workspace. As checagens de saúde do workspace chegam com a #35.
- **Windows e macOS reais:** UNVERIFIED (veja a tabela acima).
- **PyPI:** o pacote `simplicio-video` ainda não está publicado; o ramo pip do `update` depende disso.
- **Node no host:** a build de `web/` precisa de Node no host. A imagem Docker é o caminho sem Node.

## Mudanças que quebram (desde a 0.4.0)

O `install` e o `update` ficaram iguais aos do simplicio-loop ([ADR-0020](../decisoes/ADR-0020-install-universal-e-update-igual-ao-loop.md)). Nada disso foi lançado antes: as linhas abaixo descrevem a diferença para a 0.4.0.

| Antes | Agora |
|---|---|
| `doctor --json` era `{ok, checks[{name, status, detail (texto), fix}]}` | é `simplicio.doctor/v1`: `{schema, status, version, checks[{name, status, summary, fix, detail (objeto)}]}`; sai `ok`, o texto vira `summary` |
| `simplicio-video install` era o `.venv` do checkout (uv, `--python`, `--with`, `.venv/simplicio-install.json`) | copia as skills para o host do agente (`--target`, `--global`, `--host`...), com recibo de posse; o `.venv` é `bash scripts/dev_install.sh` (Windows: `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\dev_install.ps1`) |
| `./install.sh` fazia o trabalho e chamava `simplicio-video install` com o python do sistema | é um invólucro fino de `scripts/dev_install.sh` (e `install.ps1` de `scripts/dev_install.ps1`); não usa o python do sistema |
| `install --check` saía com `1` quando havia mudança pendente (e, antes do `.venv`, com 0 ou 10 só do ambiente) | sai com `10` quando falta criar ou atualizar uma skill (`0` em dia) |
| `install --json` era `simplicio.video-install/v1` (`pending`, `conflict`, `python`, `extras`) | é `simplicio.video-install-plan/v1`, as chaves do loop (`changes`, `owned`, `digest`, `resynced`...) |
| `update` num checkout rodava `git pull --ff-only`, `install`, o build de `web/` e o doctor | **recusa** (exit 2) e imprime `git pull` e `bash scripts/dev_install.sh` |
| `update` num pacote só rodava o `pip install --upgrade` | roda também `simplicio-video install --global` para reinstalar as skills nos hosts |
| `update --check` num checkout recusava árvore suja | responde 0, 10 ou 2 sem olhar a árvore (nada é puxado) |
| `update --force` seguia com árvore suja | reinstala a release do pip mesmo em dia e permite downgrade (num checkout recusa) |
| `update` recusado (árvore suja, sem upstream, sem fast-forward) saía com `1` | a recusa sai com `2` (um checkout, PEP 668) |
| `update --check` saía sempre com `0` | sai com `0` (em dia), `10` (há atualização) ou `2` (erro) e grava `update-check.json` |
| workspace ausente era `fail` no doctor | é `warn` (a linha `setup`) |
| nomes `ffmpeg libass`, `disco livre`, `portas`, `workspace`, `workspace policy` | `ffmpeg-libass`, `disk`, `ports` e uma linha `setup` |
