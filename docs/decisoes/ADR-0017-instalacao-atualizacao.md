# ADR-0017: instalação e atualização (um comando, git pull --ff-only, Docker só build local)

- **Status:** aceito. Implementado na issue #43 (`install.sh`, `simplicio-video install|update|doctor|setup`, `Dockerfile`, `compose.yaml`, `deploy/docker/`).
- **Data:** 08/10/2026 (BRT)
- **Revisado em 17/10/2026** pelo [ADR-0019](ADR-0019-login-compartilhado.md) e pelo PR de `install`, `update`, `doctor` e `login`: veja a seção "Revisão de 17/10/2026" no fim. As decisões 3 e 4 abaixo valem como foram escritas em 08/10/2026, com as mudanças registradas lá.
- **Relaciona:** [docs/host/packaging.md](../host/packaging.md) (o que cada comando faz) · [docs/how-to/install.md](../how-to/install.md) (passo a passo) · [ADR-0005](ADR-0005-gate-sem-ci.md) (gate local, sem CI) · [monetization.md](../factory/monetization.md) (repositório público ou privado)

## Contexto

Um desenvolvedor clona o repositório e precisa chegar a uma instalação funcionando. Isso exige Python 3.12 (os extras do CrewAI exigem menos de 3.14, e o Python padrão de muitas máquinas já é o 3.14), Node 22 para o render do HyperFrames e para o `web/`, e um ffmpeg com libass para as legendas. Também há pouco disco livre em algumas máquinas. Cada um desses pontos já travou alguém, e instalação difícil é o principal motivo de abandono em projetos self-hosted.

Ao mesmo tempo, há restrições que moldam a solução:

- A organização não usa GitHub Actions, então não existe CI que publique binários ou imagens (ADR-0005).
- As builds do ffmpeg trazem obrigações de GPL ou LGPL, e a revisão de licença dos componentes empacotados ainda não foi feita (ver [risks-and-policies.md](../factory/risks-and-policies.md)).
- O repositório pode continuar privado. Nesse caso, atualizar por archives assinados passa a ser o caminho, e a troca não deve espalhar mudanças pelo resto do código.
- Não temos permissão de root no ambiente do usuário, e o instalador não deve pedir sudo.
- O MVP tem zero custo de token no caminho padrão. A instalação e a atualização também não podem chamar LLM.

## Decisão

1. **Uma entrada só.** `./install.sh` faz tudo, nesta ordem: checa Node 22, ffmpeg com libass e 5 GB livres (sem instalar nada no sistema); garante o uv (oferece a instalação e só baixa com confirmação); chama `simplicio-video install`; constrói `web/` se ele existir; roda `simplicio-video doctor`. `--dry-run` mostra o plano sem criar nada.
2. **Sem sudo, só dentro do checkout.** Todo arquivo que a instalação cria fica no `.venv` do checkout, e o registro da instalação fica em `.venv/simplicio-install.json`. O instalador não toca em pacotes do sistema.
3. **Idempotente.** `simplicio-video install` compara Python, extras e o hash do `pyproject.toml` com o registro. Se nada mudou, não chama o uv. `--check` mostra o plano e sai com `1` quando há mudança pendente.
4. **Atualização por `git pull --ff-only`, num módulo só.** `simplicio-video update` recusa árvore suja (salvo `--force`, que nunca descarta alterações), faz `git fetch`, mostra os commits novos e o diff do CHANGELOG, aplica o pull só em avanço rápido, reexecuta `install`, constrói `web/` e roda o doctor. Ao final imprime o commit anterior e o `git reset --keep` para voltar. Toda a lógica fica em `src/simplicio_video/commands/update.py`.
5. **Docker só por build local.** `Dockerfile` em três estágios, usuário não root, workspace em volume e `HEALTHCHECK`. `compose.yaml` builda a partir do `Dockerfile` e não tem `image:` pública. Não publicamos imagem pronta enquanto a revisão de licença dos componentes (ffmpeg, Node) não terminar. `GEMINI_API_KEY` entra por variável de ambiente em tempo de execução e nunca vai para a imagem.
6. **Doctor com correção exata.** Cada falha traz a correção, e a saída `--json` tem o mesmo conteúdo. Credenciais só mostram presença. Uma credencial opcional (`GEMINI_API_KEY`) é aviso, não falha.

## Consequências

- Quem instala precisa de `git`, `curl` (para o uv, se faltar) e de Node 22 e ffmpeg com libass no host, a menos que use o Docker. Windows fica para o WSL ou o Docker.
- O update depende de `git` e de um remoto com upstream configurado. Um repositório sem upstream é recusado com a mensagem de como configurar.
- Não há imagem para baixar. Quem não quer compilar a imagem localmente não tem caminho pronto até a revisão de licença sair.
- Trocar para archives assinados, se o repositório ficar privado, muda só `update.py` e a checagem de assinatura. Os comandos e o documento de uso continuam os mesmos.
- O doctor checa só o que existe hoje. Health checks de plugin (#32), a checagem de saúde do workspace (#35) e o build de `web/` (#34) entram quando essas issues forem integradas; até lá, o doctor mostra `plugins` como `ok` (nenhum plugin instalado) e o install registra que `web/` ainda não existe.
- Como o caminho padrão não chama LLM, a instalação e a atualização não geram custo de token. A rede usada é só a do `git fetch`/`pull`, do download do uv e da instalação de pacotes com `uv pip install`.

## Alternativas descartadas

- **Gerenciador de pacotes do sistema (brew, apt) ou um pacote Python publicado:** exige manutenção por plataforma e ainda deixaria de fora o Node, o ffmpeg com libass e o `web/`. Não há distribuição pública para mantê-la hoje.
- **Imagem Docker publicada:** a imagem embute ffmpeg e Node, que têm obrigações de licença. Publicar antes da revisão expõe o projeto a um problema que é mais fácil de evitar do que de corrigir depois.
- **Instalador que pede sudo para instalar ffmpeg e Node:** quebra o requisito de não ter root e mexe no sistema do usuário. O instalador só checa e orienta.
- **`git pull` sem `--ff-only`:** cria merge commits locais no checkout do usuário e pode resolver conflitos sem ele perceber. Com `--ff-only`, o update só avança quando não há divergência.
- **`--force` que descarta alterações locais (`git reset --hard`):** apaga trabalho de quem usa o checkout. O `--force` só deixa seguir com árvore suja, e o git continua protegendo os arquivos que o pull tocaria.
- **Archives assinados já agora:** o código ainda não é público e não há pipeline de release. Fica para quando a decisão de distribuição (monetization.md) for tomada; a troca é local, como descrito acima.

## Revisão de 17/10/2026

Os comandos passaram a seguir o contrato do simplicio-loop (mesmos códigos de saída e documentos JSON), sem mudar o que o ADR decidiu: `.venv` com uv no checkout, `git pull --ff-only` num módulo só, sem sudo, zero token no caminho padrão.

- **Decisão 3 (idempotência).** `install --check` agora sai com `10` (e não `1`) quando há mudança pendente, e `0` em dia. Entraram `--dry-run` (não escreve nada, sai com 0) e `--json` (`simplicio.video-install/v1`).
- **Decisão 4 (atualização).** `update --check` sai com `0`, `10` ou `2` e grava `update-check.json`, que o doctor lê sem rede. `--force` reinstala mesmo em dia e permite downgrade, mas **nunca** ignora a árvore suja (a dica é `git stash`). Recusa (árvore suja, sem upstream, sem fast-forward) sai com `2`; falha de rede sai com `2` com `--check` e `1` sem ele. Entrou `--dry-run`.
- **Pacote instalado por pip.** Sem checkout não há `.venv` a criar: `install --check` e `--dry-run` avisam e saem com 0, o `install` de verdade sai com 2 e nada é criado em `site-packages`. O `update` faz `python -m pip install --upgrade "simplicio-video==<última release>"` (PyPI); a última release vem do GitHub Releases. O pacote ainda não estava no PyPI em 17/10/2026. Antes, a alternativa "um pacote Python publicado" estava descartada por falta de distribuição pública; ela volta a ser possível, mas só para o motor (Node, ffmpeg com libass e `web/` continuam do host).
- **Decisão 6 (doctor).** O JSON mudou para `simplicio.doctor/v1`: sai `ok`, entram `schema`, `status` e `version`, o texto vira `summary` e `detail` vira um objeto. Entraram as linhas `login`, `update`, `distribution` e `runtime`, e o workspace ausente passou de falha para aviso (nada no motor o lê). Um arquivo de login inseguro é `fail`.
- **Windows e macOS.** O texto "Windows fica para o WSL ou o Docker" vale para o **render**. Os comandos de operação foram escritos para os três sistemas, mas Windows e macOS reais são UNVERIFIED até alguém rodar `scripts/smoke_so.py` ([guia](../how-to/testar-em-windows-e-macos.md)).
