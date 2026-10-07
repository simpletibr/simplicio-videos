<!-- Preencha tudo. Sem CI: quem pousa é `scripts/land.sh <pr>`, que roda o gate e exige o label `reviewed`. -->

## Issue

Closes #N

## Escopo (paths da issue)

- [ ] Só toquei os paths que a issue possui (`docs/factory/ownership.yaml`): `scripts/check_ownership.py N --base origin/main` passa.
- [ ] Arquivos gerados vieram de `make regen`, não de edição à mão.

## Teste primeiro (commit vermelho)

Link do commit que só toca testes, fixtures e docs e falha pelo motivo certo:

<!-- https://github.com/simpletibr/simplicio-videos/commit/... -->

- [ ] `scripts/check_tdd.py --base origin/main` passa (ou o label `tdd-exempt` está aqui com o motivo abaixo).

## Evidências por critério de aceitação

<!-- Um item por critério da issue, com o comando ou o teste que prova. -->

| Critério de aceitação | Evidência (comando, teste, arquivo:linha) |
|---|---|
| | |

- [ ] `make check` verde, offline, em menos de 60 s.

## Docs e help

- [ ] Docs atualizados (`docs/host/<nome>.md` ou `docs/plugins/<id>.md`, com o que mudou e como usar).
- [ ] Todo comando novo tem `--help` com exemplos.
- [ ] ADR escrito, se houve decisão (número reservado em `ownership.yaml`).

## Zero tokens no caminho padrão

- [ ] O caminho padrão não chama LLM nem rede (nada de `Math.random`, `Date.now`, `fetch` na composição; nenhum provedor real nos testes).

## Risco

<!-- O que pode quebrar, como reverter, o que ficou de fora. Segredos e dados pessoais conferidos. -->

## Revisão

- [ ] Revisão independente feita (`/code-review` no diff por outro agente ou pessoa), bloqueios corrigidos.
- [ ] O revisor aplicou o label `reviewed`.
