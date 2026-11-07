# arquivo/ — trabalho que saiu do produto, guardado como estava

O que o motor não executa e o repositório não confere (operação de vendas, o kit de GPU da troca de personagem, o spec da "fábrica", as traduções do README, um serviço Node que ninguém roda) ficava na raiz, em `docs/` e em `scripts/`, ao lado do produto. É trabalho do dono, então **nada foi apagado**: cada arquivo foi movido com `git mv` para `arquivo/<onde estava>` (a história continua: `git log --follow -- arquivo/<caminho>`), sem mudar um byte do conteúdo. Para devolver algo ao lugar: `git mv arquivo/<origem> <origem>`.

- `scripts/check_docs.py` **não confere nada aqui**: os links dentro destes arquivos continuam como eram e apontam para onde as coisas ficavam antes. Um link de uma página viva para um arquivo daqui é conferido (o alvo tem de existir).
- Nada de `arquivo/` entra no wheel nem no sdist (eles só levam `src/` e seis arquivos da raiz; `tests/test_scripts/test_arquivo.py` guarda isso).
- As cinco pesquisas datadas de 30/09/2026 não vieram para cá: foram para [`docs/pesquisa/`](../docs/pesquisa/README.md).
- As quatro linhas do Mapa do `AGENTS.md` que descreviam `modules/`, `ugc/`, `scripts/kit_gpu/` e `prospects/` estão, copiadas como estavam, em [`AGENTS-legado.md`](AGENTS-legado.md).

| Onde estava | Onde está | O que é |
|---|---|---|
| `ugc/` | `arquivo/ugc/` | Trilha UGC gerativa, fora do `render`: `pack.json` com 10 personagens, `pack.schema.json` e 5 prompts. Os comandos `ugc` saíram do CLI do motor (#77); nenhum módulo de `src/` lê estes arquivos. [ADR-0004](../docs/decisoes/ADR-0004-ugc-generativo.md) |
| `prospects/` | `arquivo/prospects/` | O CSV de exemplo (`exemplo-dia-criancas.csv`) da venda ativa. O resto de `prospects/` nunca entrou no git (`.gitignore`). |
| `docs/venda-ativa.md` | `arquivo/docs/venda-ativa.md` | Venda ativa em massa. Documenta comandos `prospect` e `venda` que saíram do CLI do motor (#77) e ficam no repositório de operação. |
| `docs/factory/` | `arquivo/docs/factory/` | Spec da "fábrica" de conteúdo (blueprint, contratos, plugins, monetização, riscos, roadmap...): "nada aqui está implementado" (`README.md`). Interface, contas, projetos e publicação ficam fora do motor (regra 3 do `AGENTS.md`). `monetization.md`, `risks-and-policies.md` e `contracts.md` ainda são citados por ADR-0017, `docs/host/packaging.md` e `paths.py`: esses links já apontam para cá. `parallel-work.md` (o acordo de trabalho em paralelo, citado por `CONTRIBUTING.md`, ADR-0005 e `docs/host/gate.md`) é guia vivo e **não** veio: foi para [`docs/host/parallel-work.md`](../docs/host/parallel-work.md). O mapa de posse saiu daqui na U15, para `scripts/ownership.yaml`. |
| `modules/` | `arquivo/modules/` | `h3-swap-service`: troca de personagem em GPU alugada (Python e TypeScript, 76 arquivos). Código gerado e nunca executado; os testes dele não rodam no `make check`; o `api/` (contas, créditos, cobrança) conflita com a regra 3. Não é importado pelo motor. |
| `scripts/kit_gpu/` | `arquivo/scripts/kit_gpu/` | Kit de medição da troca de personagem em GPU de 6 GB: seis scripts autônomos (`numpy`, `opencv` e `torch` só deles). Sem teste. |
| `docs/how-to/troca-personagem-gpu/` | `arquivo/docs/how-to/troca-personagem-gpu/` | O texto do kit acima: `LEIA-ME`, prompt da sessão da GPU, resultados e CSV. |
| `READMEs/` | `arquivo/READMEs/` | 13 traduções do README, congeladas no commit #125 (os números e as trilhas citadas são os daquele dia). Nenhum README as linkava. |
| `docs/assets/board-html.png` | `arquivo/docs/assets/board-html.png` | Captura de um painel que não existe neste repositório. |

## Ficou onde estava, de propósito

- `intake/` e o verbo `videos` do `plugin.json` (o único consumidor de `intake/`): decisão do dono, ainda sem resposta.
- `voices/`, `colab/`, `tools/`, `examples/`, `deploy/`, `src/simplicio_video/data/**`: têm consumidor vivo (mensagens do CLI, `render.py`, testes, o pacote).
- As seções do `AGENTS.md` sobre a missão e o guia de operação de vendas, a venda ativa, o fluxo de UGC e as entregas no Drive: carregam regra ativa (o guia do dono, as travas, a convenção de pastas do Drive que `publish.py` e `--drive-nome` ainda usam) e ficam no `AGENTS.md`; só os caminhos de dois links passaram a apontar para cá.
- `.gitignore` (linhas `prospects/*` e `clients/`) e o `CHANGELOG.md` (histórico): não se editam nesta mudança.
