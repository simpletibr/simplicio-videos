---
title: Testar o simplicio-video em Windows e macOS
summary: Como rodar scripts/smoke_so.py num Windows ou macOS de verdade, o que a tabela significa e por que esses sistemas continuam UNVERIFIED até alguém rodar.
commands: python scripts/smoke_so.py, python scripts/smoke_so.py --manter, python -m pytest tests/packaging
last_verified: 2026-10-17
---

# Testar o simplicio-video em Windows e macOS

O gate do projeto (`make check`) roda só em Linux e não usa GitHub Actions. Os comandos `install`, `update`, `doctor`, `login`, `logout` e `auth status` foram escritos sem premissa POSIX e testados no Linux com os três sistemas **simulados** (`sys.platform`, caminhos do Windows com `PureWindowsPath`, `msvcrt` falso, PATHEXT, Homebrew). Simular não é rodar: **Windows e macOS reais continuam UNVERIFIED até alguém rodar o script abaixo lá.** Nada neste repositório afirma que esses sistemas passaram.

## O que o script faz

`scripts/smoke_so.py` usa só a biblioteca padrão do Python 3.10 ou superior (a validação de schema importa o `jsonschema`, que o próprio pacote já exige). Ele:

- cria uma **pasta temporária** e roda o CLI com `HOME`, `USERPROFILE`, `PATH`, `TEMP` e as pastas de dados dentro dela: nunca toca no seu `~` de verdade. `HOME` e `USERPROFILE` apontam para **pastas diferentes** de propósito: o Runtime lê o login de `HOME` e só depois de `USERPROFILE` (em todo sistema, Windows incluído), e o CLI faz igual; com as duas na mesma pasta, um erro de ordem passaria sem ninguém ver;
- deixa o `PATH` do filho sem `simplicio`, `git`, `node` nem `uv`, então **nunca dispara um login de verdade** nem abre navegador, e usa `SIMPLICIO_OFFLINE=1` (sem rede);
- roda nove comandos, valida cada JSON contra o schema empacotado em `src/simplicio_video/data/schemas/cli/` e confere o `status` e o `reason_code` esperados;
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
| `install --check` | 0 ou 10 | sem `.venv` na pasta isolada: 10 (mudança pendente); instalado por pip: 0 |
| `install --dry-run --json` | 0 | nada é criado; JSON `simplicio.video-install/v1` |
| `update --dry-run` | 1 ou 2 | sem rede: 1 num pacote instalado por pip (`SIMPLICIO_OFFLINE`), 2 num checkout sem git; o caminho com rede não é exercitado |
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

## O que registrar

Cole a tabela inteira (as linhas `ok` também) na issue ou no PR, com a versão do sistema que o cabeçalho mostra. Só depois disso a linha do sistema em [packaging.md](../host/packaging.md) pode deixar de ser UNVERIFIED, e só para o que a tabela provou.

## O que a fumaça não prova

- **Windows:** a trava do login usa `msvcrt.locking`, e o Runtime usa `LockFileEx`. Que os dois se excluam não foi conferido (UNVERIFIED). As **ACLs** do arquivo de login não são verificadas: `chmod`, modo e dono não valem no Windows, então só link simbólico e junção são recusados. `--no-browser` é recusado com exit 2 e `no_browser_unsupported`.
- **macOS:** um Runtime que chame `/usr/bin/open` pelo caminho absoluto não é impedido pelo substituto de `open` do `--no-browser`. Os prefixos do Homebrew (`/opt/homebrew/bin`, `/usr/local/bin`) são procurados para `ffmpeg`, `node` e `uv`.
- **Runtime de verdade:** o script nunca roda `simplicio login google`. O fluxo de login com o Runtime real continua UNVERIFIED; os testes usam um Runtime falso.
- **Rede:** o caminho com rede do `update` (GitHub Releases, PyPI, `git fetch`) não é exercitado. Rode `simplicio-video update --check` à mão para isso.
