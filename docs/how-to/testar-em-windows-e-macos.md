---
title: Testar o simplicio-video em Windows e macOS
summary: Como rodar scripts/smoke_so.py num Windows ou macOS de verdade, o que a tabela significa e por que esses sistemas continuam UNVERIFIED até alguém rodar.
commands: python scripts/smoke_so.py, python scripts/smoke_so.py --manter, python -m pytest tests/packaging, powershell -File scripts/dev_install.ps1 -DryRun
last_verified: 2026-10-17
---

# Testar o simplicio-video em Windows e macOS

O gate do projeto (`make check`) roda só em Linux e não usa GitHub Actions. Os comandos `install` (que copia a skill para o host do agente, como o do simplicio-loop), `update`, `doctor`, `login`, `logout` e `auth status` foram escritos sem premissa POSIX e testados no Linux com os três sistemas **simulados** (`sys.platform`, caminhos do Windows com `PureWindowsPath`, `msvcrt` falso, PATHEXT, Homebrew). Simular não é rodar: **Windows e macOS reais continuam UNVERIFIED até alguém rodar o script abaixo lá.** Nada neste repositório afirma que esses sistemas passaram.

## O que o script faz

`scripts/smoke_so.py` usa só a biblioteca padrão do Python 3.10 ou superior (a validação de schema importa o `jsonschema`, que o próprio pacote já exige). Ele:

- cria uma **pasta temporária** e roda o CLI com `HOME`, `USERPROFILE`, `PATH`, `TEMP` e as pastas de dados dentro dela: nunca toca no seu `~` de verdade. `HOME` e `USERPROFILE` apontam para **pastas diferentes** de propósito: o Runtime lê o login de `HOME` e só depois de `USERPROFILE` (em todo sistema, Windows incluído), e o CLI faz igual; com as duas na mesma pasta, um erro de ordem passaria sem ninguém ver;
- deixa o `PATH` do filho sem `simplicio`, `git`, `node` nem `uv`, então **nunca dispara um login de verdade** nem abre navegador, e usa `SIMPLICIO_OFFLINE=1` (sem rede);
- roda treze comandos (entre eles o `install` num **alvo temporário**: `install --check`, `install --dry-run --json`, `install --verify`, o `install` de verdade, o `install --check --json` em dia e o `install --uninstall`; nunca `--global`, nunca o seu `~`), valida cada JSON contra o schema empacotado em `src/simplicio_video/data/schemas/cli/` e confere o `status` e o `reason_code` esperados;
- imprime uma tabela Markdown (SO, versão do Python, comando, exit esperado e obtido, ok ou falhou) e **sai com 1 se algo falhar**;
- apaga a pasta temporária no fim (use `--manter` para ver o que sobrou).

## Como rodar

Num checkout (sem instalar nada):

```bash
git clone https://github.com/simpletibr/simplicio-videos.git
cd simplicio-videos
python -m pip install pyyaml jsonschema      # as duas dependências do pacote
python scripts/smoke_so.py
```

No Windows (PowerShell):

```bash
git clone https://github.com/simpletibr/simplicio-videos.git
cd simplicio-videos
py -3 -m pip install pyyaml jsonschema
py -3 scripts\smoke_so.py
```

Com o pacote instalado por pip, rode o mesmo script do checkout (ele acha os schemas do pacote instalado). Para ver a pasta que ele usou: `python scripts/smoke_so.py --manter`. Para escolher a pasta (tem de não existir ou estar vazia): `python scripts/smoke_so.py --pasta C:\Temp\fumaca`.

Rode também a suíte do pacote de operação, que pula sozinha o que precisa de arquivos POSIX de verdade:

```bash
python -m pip install -e ".[test]"
python -m pytest tests/packaging -q
```

## O que a saída significa

| Comando | Exit esperado | Por quê |
|---|---|---|
| `simplicio-video --version` | 0 | o CLI inicia nesse sistema |
| `doctor --json` | 0 ou 1 | o PATH isolado não tem `node` nem `ffmpeg`, então o doctor normalmente sai com 1; o que importa é o JSON validar (`simplicio.doctor/v1`) e não haver traceback |
| `install --check --target <alvo>` | 10 | o alvo temporário está vazio: a skill está pendente |
| `install --dry-run --json --target <alvo>` | 0 | nada é criado; JSON `simplicio.video-install-plan/v1` com a skill em `changes.created` |
| `install --verify --target <alvo>` | 0 | o plano confere (versão e digest) |
| `install --target <alvo>` | 0 | copia a skill do pacote para `<alvo>/.claude/skills` e grava o recibo: é a prova de cópia, escrita atômica e caminhos do sistema |
| `install --check --json --target <alvo>` | 0 | agora em dia (`up_to_date`) |
| `install --uninstall --target <alvo>` | 0 | remove só o que o recibo registra: o alvo volta a ficar vazio |
| `update --dry-run` | 1 ou 2 | sem rede: 1 num pacote instalado por pip (`SIMPLICIO_OFFLINE`); 2 num checkout, que **recusa** e diz `git pull` e o dev install; o caminho com rede não é exercitado |
| `auth status --json` | 1 | sem login: `login_missing` |
| `login --json` | 1 | sem Runtime no PATH: `UNVERIFIED`, e nada é iniciado |
| `logout` | 2 | sem `--yes`: `REFUSED` |
| `logout --yes --json` | 0 | sem login: `NO_LOGIN`, e nada é criado |

Cada linha termina em `ok` ou `falhou: <motivo>`. Os motivos mais prováveis num sistema novo:

| Motivo na tabela | Causa provável |
|---|---|
| `exit N fora de [...]` | o comando se comportou diferente: o código tem uma premissa que esse sistema não cumpre |
| `traceback na saída` | uma exceção não tratada (erro de caminho, de codificação do console, de módulo POSIX) |
| `o stdout não é um único documento JSON` | algo imprimiu texto fora do `--json` |
| `schema ...` | o JSON não bate com o schema empacotado |
| `a saída cita um token` | um token vazou: **pare e avise**, é um bug de segurança |
| `o módulo jsonschema não está instalado` | rode `python -m pip install pyyaml jsonschema` |

## O PowerShell (`scripts/dev_install.ps1`) é à parte

O ambiente do checkout no Windows é `powershell -File scripts/dev_install.ps1` (o `install.ps1` da raiz é um invólucro dele), o equivalente do `scripts/dev_install.sh` do Linux e do macOS. **Ele nunca foi executado**: o repositório foi escrito num Linux sem PowerShell, e a suíte só confere o texto do script. Quem tiver um Windows pode ajudar a tirá-lo do UNVERIFIED:

```bash
powershell -File scripts/dev_install.ps1 -DryRun       # mostra o plano e não cria nada
powershell -File scripts/dev_install.ps1               # cria o .venv (precisa de Node 22, ffmpeg com libass e uv)
powershell -File scripts/dev_install.ps1 -With local-tts -Python 3.12
```

Cole a saída na issue ou no PR. O que se espera: `-DryRun` imprime o plano e sai com 0; o conflito de Python (`.venv` com outra versão) sai com 1 e diz o que apagar; o script nunca pede administrador e nunca roda `iex` sem a sua confirmação.

## O que registrar

Cole a tabela inteira (as linhas `ok` também) na issue ou no PR, com a versão do sistema que o cabeçalho mostra. Só depois disso a linha do sistema em [packaging.md](../host/packaging.md) pode deixar de ser UNVERIFIED, e só para o que a tabela provou.

## O que a fumaça não prova

- **Windows:** a trava do login usa `msvcrt.locking`, e o Runtime usa `LockFileEx`. Que os dois se excluam não foi conferido (UNVERIFIED). As **ACLs** do arquivo de login não são verificadas: `chmod`, modo e dono não valem no Windows, então só link simbólico e junção são recusados. `--no-browser` é recusado com exit 2 e `no_browser_unsupported`.
- **macOS:** um Runtime que chame `/usr/bin/open` pelo caminho absoluto não é impedido pelo substituto de `open` do `--no-browser`. Os prefixos do Homebrew (`/opt/homebrew/bin`, `/usr/local/bin`) são procurados para `ffmpeg`, `node` e `uv`.
- **Runtime de verdade:** o script nunca roda `simplicio login google`. O fluxo de login com o Runtime real continua UNVERIFIED; os testes usam um Runtime falso.
- **O `install` num Windows ou macOS de verdade:** a tabela acima prova a cópia, o recibo e o `--uninstall` num alvo temporário. Não prova o `--global` (o `~` real) nem a pasta de skills de cada host nesses sistemas: as pastas vêm da tabela do loop, a mesma nos três sistemas, e nenhum host foi aberto para ver se lê a skill dali.
- **Rede:** o caminho com rede do `update` (GitHub Releases, PyPI, `git fetch`) não é exercitado. Rode `simplicio-video update --check` à mão para isso.
