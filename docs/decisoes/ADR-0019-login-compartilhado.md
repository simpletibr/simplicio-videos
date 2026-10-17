# ADR-0019: login compartilhado com o Runtime (espelho do simplicio-loop, sem credencial própria)

- **Status:** aceito. Implementado no PR de `install`, `update`, `doctor` e `login` (pedido direto do dono, sem issue, como os PRs #108 a #112): `simplicio-video login|logout|auth status` e a linha `login` do `doctor`.
- **Data:** 17/10/2026 (BRT)
- **Relaciona:** [docs/host/packaging.md](../host/packaging.md) (o que cada comando faz e toca) · [ADR-0017](ADR-0017-instalacao-atualizacao.md) (instalação e atualização) · [ADR-0018](ADR-0018-social-planejar-sem-postar.md) (outra decisão ancorada na regra 3) · [AGENTS.md](../../AGENTS.md) (regra 3: o motor é standalone) · [testar em Windows e macOS](../how-to/testar-em-windows-e-macos.md)

## Contexto

O simplicio-loop e o Simplicio Runtime compartilham **um** login da conta Simplicio: o arquivo `~/.simplicio/login.json` (ou o de `SIMPLICIO_AUTH_FILE`), a trava `login.lock` ao lado e o comando `simplicio login google`. O loop não tem fluxo próprio: ele roda o Runtime e depois só lê o arquivo (`simplicio_loop/auth.py` e `auth_cli.py`, commit `2034e2d`). O Runtime documenta o comando no `INSTALL.md` e exige login para os comandos protegidos dele (`map`, `context`, `doctor`, `plugin`...).

O simplicio-videos é o plugin de vídeo do Runtime e roda sob ele, então quem usa o motor precisa ver, de dentro do CLI, se o login do Runtime está de pé, e precisa de um jeito de entrar e sair sem sair do `simplicio-video`. Ao mesmo tempo, a regra 3 do AGENTS.md diz que o motor **continua standalone**: sem contas, sem cobrança, sem dependência de um host para uma feature ficar mais fácil.

## Decisão

1. **O `login` é um espelho do `login` do loop.** `simplicio-video login [--json] [--no-browser]` delega a `simplicio login google` (o Runtime, com o terminal ligado) e depois lê `~/.simplicio/login.json` (ou `SIMPLICIO_AUTH_FILE`). Mesmo arquivo, mesma variável, mesma trava `login.lock` (`0600`, 20 s), mesmos documentos JSON (`simplicio.login/v1`, `simplicio.logout/v1`, `simplicio.auth-status/v1`), mesmos `reason_code` e mesmos códigos de saída (0 verificado, 1 não verificado, 2 recusado). A única troca é o `fix`, que diz `simplicio-video login`.
2. **O login não libera nada e não cobra nada no motor.** Nenhum comando do motor lê o login. Sem login, o doctor dá `warn`, nunca `fail`; só um arquivo de login que existe e é inseguro ou inválido é `fail`.
3. **O login não guarda credencial.** O módulo `auth` só **lê** (nada de `write_login`, `refresh_if_due` ou `apply_tokens`), nenhum token vai por argumento, e as chaves de provedor (`GEMINI_API_KEY` e as outras) continuam só no ambiente. Quem grava o login é o Runtime.
4. **O `logout` exige `--yes` e só apaga um login.** Apagar o arquivo compartilhado desloga o Runtime também; sem `--yes` nada é apagado (exit 2). Como `SIMPLICIO_AUTH_FILE` pode apontar para qualquer arquivo, o `logout` só apaga um arquivo comum, pequeno e com a forma de um login (JSON com `access_token`, `refresh_token` ou `verification`); o resto sai com exit 2 e `not_a_login_file`, sem apagar. O token de renovação não é revogado no servidor, porque nenhum endpoint de revogação está documentado aqui.
5. **Nunca expõe um token.** Nem em stdout, stderr, JSON, log ou argumento. O e-mail sai mascarado (`w***@gmail.com`). O schema `auth-status` proíbe `access_token` e `refresh_token` (`propertyNames`). O processo filho do Runtime recebe um ambiente mínimo, numa lista fechada de nomes exatos (sem prefixo livre, sem `GH_TOKEN`, chaves de API nem `SIMPLICIO_LOGIN_TOKEN`).
6. **Recusa o que é inseguro.** Linux e macOS recusam arquivo legível por grupo ou outros (`chmod 600`), link simbólico, FIFO, pasta, arquivo de outro usuário, pasta gravável por outros (`chmod 700`) e `login.lock` alheio. No Windows `chmod` não vale: mantém a recusa de link simbólico e de junção e **não verifica ACLs**; `--no-browser` é recusado com exit 2 e `no_browser_unsupported`.
7. **Sem Runtime, o login próprio é `UNVERIFIED`.** Nenhum endpoint de autorização está documentado neste repositório e nenhum é inventado: o comando mostra como instalar o Runtime (os comandos do `INSTALL.md` dele, sem executá-los) e sai com 1.
8. **Fica fora do `plugin.json` e do MCP.** São comandos de terminal que mexem na credencial, no mesmo padrão de `openverse get` e `export`: o agente não os chama pelo servidor MCP.
9. **Código portado, sem dependência do loop.** `auth.py`, `commands/login.py` e as partes de `update` e `doctor` são cópias adaptadas do loop (cabeçalho com o commit de origem), para o motor continuar standalone. Fora do porte, de propósito: `auth status --online`, a renovação do token, `SIMPLICIO_247_LOGIN` (do watcher 24/7 do loop) e o `update` de binário.
10. **Windows, Linux e macOS.** O código não assume POSIX (caminho do `.venv`, `HOME` e depois `USERPROFILE`, como o Runtime, PATHEXT, `fcntl` ou `msvcrt`, Homebrew) e os três sistemas são simulados no Linux nos testes. Windows e macOS reais são **UNVERIFIED** até alguém rodar `scripts/smoke_so.py` lá.

## Consequências

- Quem usa o motor sem o Runtime não perde nada: o login é opcional, e a linha do doctor é só um aviso.
- O motor passa a ter um único lugar que conhece o arquivo de login (`auth.py`). Um teste garante que nenhum outro módulo do motor o lê, e outro garante que `login`, `logout` e `auth` não entram no `plugin.json` nem no MCP.
- O custo é manter um porte: se o loop mudar o formato do login ou o código de saída, este CLI diverge até alguém reportar. O cabeçalho dos módulos diz de qual commit do loop eles vêm.
- Achado do porte: o loop (`2034e2d`) ainda imprime `wesleysimplicio/simplicio` nos comandos de instalação do Runtime, e o `INSTALL.md` do Runtime (`1c7919a`) diz `simpletibr/simplicio`. Este CLI imprime os comandos do `INSTALL.md` do Runtime.
- Não verificado: o `simplicio login google` nunca foi rodado de verdade por este CLI (os testes usam um Runtime falso, e a máquina de desenvolvimento nem foi tocada); que `msvcrt.locking` e o `LockFileEx` do Runtime se excluem no Windows; as ACLs do Windows.

## Alternativas descartadas

- **Login próprio (OAuth do Google no CLI).** Contraria a regra 3 (contas e credenciais no motor) e inventaria um endpoint que não está documentado aqui.
- **Travar comandos do motor atrás do login, ou cobrar por ele.** Quebra o motor standalone e vira outro projeto (renovação, direitos, ADR de cobrança).
- **Guardar um token ou uma chave própria.** Mais uma credencial para vazar, sem consumidor: nada no motor usa o token.
- **Depender do pacote `simplicio-loop`.** O motor tem de continuar standalone. Uma cópia fiel com o commit de origem diverge menos do que reescrever.
- **Verbos `video.login` no `plugin.json` e no MCP.** Deixaria um agente entrar, sair e, pior, apagar o login do Runtime sem o usuário pedir.
- **`logout` sem confirmação.** Desloga o Runtime de quem só queria limpar o motor.
