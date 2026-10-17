---
title: Instalar, atualizar e checar o simplicio-video
summary: Como criar o ambiente do checkout, instalar a skill no agente (como o simplicio-loop), atualizar com segurança (pip ou checkout), checar o ambiente, entrar com o login do Runtime e rodar pelo Docker local.
commands: ./install.sh, bash scripts/dev_install.sh, powershell -NoProfile -ExecutionPolicy Bypass -File scripts\dev_install.ps1, simplicio-video install, simplicio-video update, simplicio-video doctor, simplicio-video setup, simplicio-video login, simplicio-video logout, simplicio-video auth status, docker compose build
issue: 43
last_verified: 2026-10-17
---

# Instalar, atualizar e checar o simplicio-video

São duas coisas, como no simplicio-loop:

1. **O ambiente do checkout** (Python 3.12 num `.venv`, o pacote, os extras e uma checagem final): `bash scripts/dev_install.sh` (no Windows, `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\dev_install.ps1`; o `-ExecutionPolicy Bypass` vale só para esse processo, porque o Windows de cliente vem com a política `Restricted`). O `./install.sh` da raiz faz o mesmo.
2. **A skill no seu agente**: `simplicio-video install` copia a skill do simplicio-video para o host (Claude Code, Codex, Cursor...), exatamente como o `install` do simplicio-loop. Funciona igual num checkout e num pacote do pip.

Nada usa sudo, e os dois podem rodar de novo sem estragar nada. O que cada passo faz e por que está assim: [packaging.md](../host/packaging.md) e [ADR-0020](../decisoes/ADR-0020-install-universal-e-update-igual-ao-loop.md) (que supersede a decisão do [ADR-0017](../decisoes/ADR-0017-instalacao-atualizacao.md) sobre o `.venv` e o `git pull`). O login compartilhado com o Runtime: [ADR-0019](../decisoes/ADR-0019-login-compartilhado.md).

## Requisitos (do ambiente do checkout)

| O quê | Como conferir | Se faltar |
|---|---|---|
| Node 22 ou superior | `node -v` | `nvm install 22` (no Windows, https://nodejs.org) |
| ffmpeg com libass | `ffmpeg -version \| grep -- --enable-libass` | macOS: `brew install ffmpeg`; Debian/Ubuntu: `apt install ffmpeg` (use um pacote compilado com libass); Windows: `winget install Gyan.FFmpeg` |
| 5 GB livres no disco do checkout | `df -h .` | libere espaço: o `.venv` e o render precisam dele |
| uv | `uv --version` | o `dev_install` oferece instalar, e só baixa com a sua confirmação |

O `dev_install` não usa o `python3` do sistema (o uv traz o Python 3.12), então um Python sem PyYAML, como o do macOS com as ferramentas do Xcode, não atrapalha. **Windows e macOS:** os scripts de shell e os comandos foram escritos sem premissa POSIX, mas **não foram rodados num Windows nem num macOS de verdade (UNVERIFIED)**; o `scripts/dev_install.ps1` é PowerShell que nunca foi executado. Veja [testar em Windows e macOS](testar-em-windows-e-macos.md). Para o render no Windows, use o WSL ou o Docker (seção abaixo).

## Instalar o ambiente do checkout

```bash
git clone https://github.com/simpletibr/simplicio-videos.git
cd simplicio-videos

bash scripts/dev_install.sh --dry-run    # mostra o plano e não cria nem altera nada
bash scripts/dev_install.sh              # cria o .venv, instala o pacote, checa o ambiente e roda o doctor
./install.sh                             # o mesmo: um invólucro fino do scripts/dev_install.sh
```

No Windows (PowerShell; **UNVERIFIED**, nunca rodou num Windows de verdade):

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\dev_install.ps1 -DryRun
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\dev_install.ps1 -With local-tts
powershell -NoProfile -ExecutionPolicy Bypass -File install.ps1 -DryRun   # o invólucro, com as mesmas opções
```

O `dev_install` aceita três opções (no PowerShell: `-DryRun`, `-With`, `-Python`):

| Opção | O que faz |
|---|---|
| `--dry-run` | lista o plano (checagens, uv, `.venv`, extras, `web/`, doctor) e sai sem criar nada |
| `--with EXTRAS` | extras separados por vírgula. Os que existem hoje: `test` (pytest, ruff, shellcheck: o gate), `local-tts` (voz local, sem custo), `mcp` (servidor MCP), `remote` (Kaggle e Colab) |
| `--python VERSÃO` | Python do `.venv`. O padrão é 3.12, porque os extras do CrewAI exigem Python menor que 3.14 |

Exemplos reais:

```bash
bash scripts/dev_install.sh --with local-tts                  # o MVP com voz local
bash scripts/dev_install.sh --with test --python 3.12         # quem vai rodar o gate (make check)
bash scripts/dev_install.sh --dry-run --with local-tts --python 3.12
```

Rodar de novo reinstala o pacote editável (é idempotente e rápido) e não recria o `.venv`. Um `.venv` que usa outro Python é um conflito: o script diz para apagar com `rm -rf .venv` e não troca sozinho. O `simplicio-install.json` e as opções `--python` e `--with` do `simplicio-video install` não existem mais: o `install` agora cuida da skill (seção seguinte).

Depois, crie o workspace e confira o ambiente:

```bash
.venv/bin/simplicio-video setup --yes     # workspace com tema br, idioma pt-BR, autonomia L1 e orçamentos zerados
.venv/bin/simplicio-video doctor          # confere login, Python, Node, ffmpeg, disco, credenciais e workspace
```

### Só o ambiente Python

Para só instalar o pacote, sem as checagens do `dev_install`: `pip install -e .` na raiz do repo (Python 3.10 ou superior), ou `pip install simplicio-video` quando o pacote estiver no PyPI (ainda não está: conferido em 17/10/2026).

## Instalar a skill no seu agente

`simplicio-video install` faz o que o `install` do simplicio-loop faz: copia as skills do pacote (`simplicio-video` e `simplicio-video-social`) para o host do agente e grava um recibo de posse, `.simplicio-video/install-ownership.json`. **O simplicio-video não tem hooks: só skills** (o loop também copia hooks e regras de host; aqui não há).

```bash
simplicio-video install --check                     # nada é escrito; sai com 0 em dia ou 10 se há mudança pendente
simplicio-video install --dry-run --json            # o plano em JSON (simplicio.video-install-plan/v1); não escreve nada
simplicio-video install                             # no projeto atual: .claude/skills/simplicio-video (e a skill social)
simplicio-video install --host codex --target ~/meu-projeto   # e o AGENTS.md do Codex, se ainda não existir
simplicio-video install --global                    # nas 11 pastas de skills sob o ~ (HOME, depois USERPROFILE); o --host é ignorado
simplicio-video install --global --prune-project-copies --target ~/meu-projeto   # e remove a cópia do projeto que o recibo dele registra
simplicio-video install --verify                    # compara os arquivos instalados com o recibo e com o pacote (exit 1 e a lista se algo difere)
simplicio-video install --uninstall --dry-run       # lista o que sairia; --uninstall remove só o que está no recibo e não foi editado
```

| Flag | O que faz |
|---|---|
| `--target DIR` | o projeto onde instalar (padrão: a pasta atual) |
| `--global` | instala nas 11 pastas de skills sob o home (`~/.claude/skills`, `~/.codex/skills`, `~/.cursor/skills`...) em vez do projeto, com a regra de posse (veja abaixo) |
| `--host H` | o host (padrão `claude`) ou `all`; com `--global` o `--host` é ignorado |
| `--dry-run`, `--check` | não escrevem nada; `--check` sai com 10 quando há mudança pendente |
| `--json` | UM documento `simplicio.video-install-plan/v1`, também no erro |
| `--verify` | compara os arquivos com o recibo e com o pacote e sai com 1 se algo difere (`ok: false` e a lista `problems` no `--json`) |
| `--uninstall` | remove só o que o recibo registra e que ninguém editou; com `--dry-run`, só lista |
| `--prune-project-copies` | com `--global`: remove a cópia do projeto (`--target`) que o recibo dele registra; nunca toca a instalação global |

**Os hosts** são os do registro do loop. As skills vão sempre para `.claude/skills`; o que muda é o arquivo de entrada do host, criado só se ainda não existir:

| Host | Arquivo de entrada |
|---|---|
| `claude`, `cursor`, `simplicio_agent`, `openclaw` | nenhum |
| `codex`, `grok`, `antigravity`, `opencode` | `AGENTS.md` |
| `vscode` | `.github/copilot-instructions.md` |
| `kiro` | `.kiro/steering/simplicio-video.md` |
| `gemini` | `GEMINI.md` |
| `aider` | `CONVENTIONS.md` |

Com `--host all`, todos de uma vez. `--global` instala nas **11 pastas** de skills do loop sob o home (a tabela do `skill_sync.py` dele, a mesma nos três sistemas): `.claude/skills`, `.cursor/skills`, `.codex/skills`, `.grok/skills`, `.agents/skills`, `.copilot/skills`, `.vscode/simplicio-skills`, `.config/opencode/skills`, `.config/amp/skills`, `.kiro/steering` e `.simplicio-loop/skills`; o `--host` é ignorado (o loop faz o mesmo). Em cada uma vale a regra de posse: o install cria o que falta e o arquivo entra no recibo com o `sha256`; atualiza só a cópia que é nossa (está no recibo) e não editada, quando o pacote tem uma versão mais nova; deixa em paz (`left_alone`) o que já existia antes ou que você editou, mesmo que de outro host; nunca apaga um arquivo extra seu, nem o que saiu do pacote; o `--check` sai com 10 quando uma cópia nossa e não editada está desatualizada, e uma cópia alheia antiga não o deixa pendente; o `--uninstall` remove só o que é nosso. Uma pasta secundária que é link (um `~/.config/opencode` movido para os dotfiles) é pulada com um aviso e não derruba as outras; `~/.claude/skills` que é link recusa tudo. O `update` do pip chama `install --global` e por isso também é seguro.

Um arquivo de entrada que já existe (o seu `AGENTS.md`) fica como está e não recebe apontador. Rodar de novo diz `já está em dia` e não regrava nada. Se o setup nunca rodou, ele roda no fim quando há terminal e senão diz como rodar.

### O que o `install` nunca faz

O recibo é um arquivo do repositório, e um repositório clonado pode ser hostil; por isso:

- **Não sobrescreve nem apaga o que não é dele.** Outras skills, o seu `AGENTS.md`, um arquivo seu dentro da pasta da skill e um link simbólico ficam intactos e saem como `left_alone`. Uma pasta de skill que já existia antes do primeiro install (copiada à mão, ou de uma versão antiga) não é tomada: o install a deixa em paz e diz; para ele passar a cuidar dela, apague a pasta (ou renomeie) e rode `simplicio-video install` de novo. Uma cópia idêntica que já estava lá também não vira dele, e o `--uninstall` nunca a apaga.
- **Só remove o que foi ele que escreveu e ninguém editou.** O recibo guarda o `sha256` de cada arquivo. Se você editou o `AGENTS.md` que o install criou (ou ajustou a `SKILL.md`), o `--uninstall` o deixa como está, avisa e o lista em `left_alone`; um `install` seguinte também o tira do recibo.
- **Recusa um recibo que nomeia o que ele nunca instala.** Só valem as pastas das skills, os arquivos de entrada dos hosts e o próprio recibo: um recibo plantado num repositório clonado com `.git/config`, `src/app.py` ou `.ssh/authorized_keys` é recusado pelo `--uninstall` e pelo `--prune-project-copies` (exit 1, nada é apagado), e um `install` por cima dele o ignora, avisa e grava um novo (o recibo plantado não é herdado).
- **Não escreve por dentro de um link nas pastas que cria.** Cada pasta que o install cria (`.claude/skills`, a da skill, `.simplicio-video`) nunca é link: com link ele recusa (exit 2) e não escreve nada. A pasta base (`~/.claude`) **pode** ser um link para o seu repositório de dotfiles: o install a resolve uma vez, escreve no caminho real e grava no recibo; o `--uninstall` confere que o link ainda aponta para lá. Ele também não usa link para copiar (no Windows exigiria privilégio).
- **Não corre contra si mesmo.** Dois installs ao mesmo tempo no mesmo alvo esperam um pelo outro (`.simplicio-video/install.lock`, vazio, `0600`; espera até 10 s).
- **Não confia no `--verify` de uma versão só.** O `--verify` compara os arquivos com o recibo e com o pacote: alvo nunca instalado, skill adulterada, arquivo faltando ou recibo trocado por lixo saem com 1.

### Se o pacote veio do pip

Instalado por `pip install simplicio-video`, não há checkout: o `install` copia a skill que veio no pacote (a mesma, byte a byte, que `skills/` tem no repo) e nada é criado em `site-packages`. O pacote ainda não está publicado no PyPI (conferido em 17/10/2026): até lá, instale pelo checkout.

## Atualizar

```bash
simplicio-video update --check    # 0 em dia, 10 há atualização, 2 erro; não altera nada
simplicio-video update --dry-run  # mostra o plano; não altera nada
simplicio-video update            # pacote do pip: PyPI e depois install --global; checkout: recusa
```

**Num pacote instalado por pip** o update faz `python -m pip install --upgrade "simplicio-video==<última release>"` (PyPI; a versão vem do GitHub Releases) e, em seguida, `simplicio-video install --global`, para a skill do `~/.claude/skills` acompanhar a versão (sem apagar nada que não seja do recibo). Um Python gerenciado pelo sistema (PEP 668) é recusado com exit 2 e quatro saídas: um `venv`, `uv`, `pipx`, ou `PIP_BREAK_SYSTEM_PACKAGES=1 simplicio-video update` se você autoriza; um Python sem pip (o venv de um `uv tool install`) também, com `uv tool upgrade simplicio-video` ou `pipx upgrade simplicio-video`. `--force` reinstala mesmo em dia (só o nosso pacote, `--force-reinstall --no-deps`, quando não há versão mais nova) e permite downgrade. Dentro do container, reconstrua a imagem (`docker compose build`).

**Num checkout git (ou instalação editável) o update recusa**, como o do simplicio-loop: imprime `git pull` e `bash scripts/dev_install.sh` (no Windows, `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\dev_install.ps1`) e sai com exit 2. É isso que atualiza: dentro do checkout, rode os dois.

```bash
git pull
bash scripts/dev_install.sh
```

O `update` não puxa, não reconstrói e não apaga nada. O `update --check` de um checkout faz `git fetch` (precisa de rede) e diz quantos commits são novos e o diff do CHANGELOG; alterações locais não atrapalham, porque nada é puxado. Ele grava o resultado em `~/.simplicio-video/update-check.json` (ou em `$SIMPLICIO_VIDEO_DATA`), que o `doctor` lê sem rede. Com `SIMPLICIO_OFFLINE=1` nada de rede roda: `update --check` sai com 2. Falha de rede: exit 2 com `--check` e exit 1 sem ele. Se a versão instalada é mais nova que a última release (o PyPI sai antes do GitHub Release), o `update` sai com 0 e não faz nada.

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
| `uv não encontrado` | aceite a instalação oferecida pelo `dev_install`, ou veja https://docs.astral.sh/uv/ |
| `update: este é um checkout git ... recusa` | é esperado: rode `git pull` e `bash scripts/dev_install.sh` (Windows: `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\dev_install.ps1`) |
| `install: host desconhecido` | use um dos hosts da tabela (`claude`, `codex`, `cursor`...) ou `all` |
| `install: sem recibo de posse` | o `--uninstall` só remove o que o `install` registrou; sem recibo ele não apaga nada |
| `deixado em paz -> N que não são do simplicio-video` | é esperado: o `install` não mexe em outras skills, num `AGENTS.md` seu, numa `SKILL.md` que já existia nem em arquivo que você editou |
| `install: ... é um link ... Nada foi escrito` (exit 2) | uma pasta que o install cria (`.claude/skills`, a da skill, `.simplicio-video`) é link: apague o link ou use outro `--target`. Só a pasta base (`~/.claude`) pode ser link |
| `o recibo de posse lista um caminho que o simplicio-video nunca instala` | o recibo foi adulterado ou plantado: nada foi apagado; apague `.simplicio-video/install-ownership.json` à mão se o recibo é mesmo lixo |
| `install --verify` sai com 1 | veja a lista: `modified` (você editou), `outdated` (rode `install`), `foreign` (já existia), `missing`, `no_receipt` |
| `outro simplicio-video install está rodando ... install.lock` | espere ele terminar; a trava é do sistema e some sozinha se o processo morrer |
| para atualizar o pacote do pip | `simplicio-video update`, ou `pip install --upgrade simplicio-video` e depois `simplicio-video install --global` |
| `login: ... pode ser lido pelo grupo ou por outros` | rode o `chmod 600` que o `auth status` mostra |
| `login: Simplicio Runtime não encontrado` | instale o Runtime (o comando aparece na saída) e rode `simplicio-video login` de novo |
| `sem workspace.yaml` / `o setup ainda não rodou` | `.venv/bin/simplicio-video setup --yes` |
| `.venv usa Python 3.13 e o pedido é 3.12` | `rm -rf .venv` e rode o `dev_install` de novo |

## Limites atuais

- O doctor ainda não checa plugins: o health check de plugin chega com a #32.
- Não há build de `web/`: ele chega com a #34. Até lá, o `dev_install` registra isso e segue.
- Windows e macOS reais são UNVERIFIED até alguém rodar `scripts/smoke_so.py` lá ([guia](testar-em-windows-e-macos.md)); o `scripts/dev_install.ps1` e o `install.ps1` nunca foram executados.
- O `login google` do Runtime nunca foi rodado de verdade por este CLI (os testes usam um Runtime falso): UNVERIFIED.
