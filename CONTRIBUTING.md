# Contribuindo

Todo trabalho aqui segue o acordo de [parallel-work.md](docs/factory/parallel-work.md) e passa pelo gate local descrito em [docs/host/gate.md](docs/host/gate.md). Não há GitHub Actions: o gate roda na sua máquina.

## Começando

```bash
git worktree add ../sv-31 -b feat/31-gate origin/main
cd ../sv-31
make setup       # .venv, extra `test` e hooks (o pre-push roda `make check`)
make check       # offline, menos de 60 s
```

## O ciclo de uma issue

1. Leia a issue, a entrada dela em [`docs/factory/ownership.yaml`](docs/factory/ownership.yaml) e o [AGENTS.md](AGENTS.md).
2. **Testes primeiro.** Escreva os testes que falham pelo motivo certo e commite-os sozinhos (só testes, fixtures e docs). Esse é o primeiro commit do branch.
3. Implemente até o `make check` ficar verde. Só toque nos paths da sua issue; precisa de outro arquivo? Comente na issue dona.
4. Docs e help: o que mudou em `docs/host/<nome>.md` ou `docs/plugins/<id>.md`, `--help` com exemplos em todo comando, ADR se houve decisão.
5. Abra o PR pelo [template](.github/PULL_REQUEST_TEMPLATE.md) (`Closes #N`, link do commit vermelho, evidência por critério).
6. Revisão independente (outro agente ou pessoa, `/code-review` no diff). O revisor aplica o label `reviewed`.
7. Pouso: `scripts/land.sh <pr>` (use `--dry-run` antes). Um pouso por vez.

## Comandos

| Comando | Para quê |
|---|---|
| `make setup` | cria o `.venv`, instala o extra `test` e liga os hooks |
| `make check` | o gate offline: ruff, shellcheck, testes sem `slow`/`render`/`integration`/`ui`, ownership e TDD |
| `make check-full` | `check` + testes que podem usar rede |
| `make regen` | regenera arquivos gerados; nunca edite-os à mão |
| `scripts/check_ownership.py <issue> --base origin/main` | só paths da issue |
| `scripts/check_tdd.py --base origin/main` | testes primeiro |
| `scripts/land.sh <pr> [--dry-run]` | pouso serializado |

## Regras que o gate cobra

- Marcadores de teste: `unit` (padrão), `contract`, `e2e`, `integration`, `render`, `ui`, `slow`. Sem rede nos testes unitários.
- Nada de segredo, dado de cliente ou dado pessoal no repositório.
- Mensagens de commit em pt-BR (`tipo(escopo): resumo`), docs em pt-BR, comentários de código em inglês.
- Caminho padrão sem LLM e sem rede.
