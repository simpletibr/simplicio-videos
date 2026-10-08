---
title: Media (orçamento e aprovação de gasto)
summary: O comando generate (quote, approve e show) que cota, aprova e mostra o gasto de geração por IA de cada item na rota ai_assisted, o orçamento media_credits do workspace, o teto diário, a regra de quem pode aprovar e a ressalva sobre o registro.
commands: generate quote, generate approve, generate show
issue: 85
last_verified: 2026-10-08
---

# Media (orçamento e aprovação de gasto)

O plugin `media` (issue #85, épico #81) controla o gasto de geração por IA de cada item. Um item na rota `ai_assisted` (issue #82) passa por três passos: a cotação (`quote`), a aprovação humana (`approve`) e a consulta (`show`). Só depois de aprovado o item pode seguir para a geração. O plugin não chama rede, não usa LLM e não gasta créditos: ele registra a decisão e aplica o orçamento. O gasto real acontece no Real Oficial, e a confirmação de lá é o controle de fato (ver [Quem pode aprovar](#quem-pode-aprovar)).

Código: `src/simplicio_factory/plugins/media/` (`cli.py`, `budget.py`). Comando declarado em [plugin.json](../../src/simplicio_factory/plugins/media/plugin.json) e registrado pelo host ([plugin-host.md](../host/plugin-host.md)). Estado do item e transições: [kernel.md](../host/kernel.md). A rota `ai_assisted` e o grafo de transições estão em `src/simplicio_factory/contracts/transitions.py`.

## Comandos

| Comando | Para quê |
|---|---|
| `simplicio-video generate quote ITEM --provider real-oficial --estimate-ref REF --credits N [--daily-cap N]` | registra o custo estimado e leva o item de `drafted` para `quoted` |
| `simplicio-video generate approve ITEM --by NOME [--yes] [--daily-cap N]` | aprova o custo cotado e leva o item de `quoted` para `approved` |
| `simplicio-video generate show ITEM [--json]` | mostra o passo, o custo em créditos e quem aprovou |

Cada comando tem `--help` com exemplo. `simplicio-video plugin list` mostra o plugin `media` com o comando `generate`.

### `generate quote`

```bash
simplicio-video generate quote itm_01HZEXEMPLO0000000000001 --provider real-oficial --estimate-ref est_01 --credits 120
```

```text
itm_01HZEXEMPLO0000000000001: quoted
custo: 120 créditos (real-oficial, ref est_01)
```

O comando acrescenta em `item.production["steps"]` o passo `{"kind": "ai_media", "provider": "real-oficial", "estimate_ref": "est_01", "credits": 120}` e faz a transição por `transition()`. Recusas, sem gravar passo nem evento:

- o item não está na rota `ai_assisted` (`generate quote exige a rota ai_assisted`);
- o item não está em `drafted` (transição inválida);
- o orçamento é zero, ou `--credits` passa de `media_credits` ou do teto diário.

`--provider` aceita só `real-oficial` nesta versão. `--credits` é um inteiro maior que zero.

### `generate approve`

```bash
simplicio-video generate approve itm_01HZEXEMPLO0000000000001 --by "Wesley"
```

Pede confirmação no terminal:

```text
Aprovar o gasto de 120 créditos (real-oficial, ref est_01) no item itm_01HZEXEMPLO0000000000001, por Wesley? [s/N]
```

Aceita `s`, `sim`, `y` ou `yes`. Qualquer outra resposta cancela e não grava nada. Sem terminal (cron, pipe, agente), o comando falha e pede `--yes`. Com `--yes` a pergunta é pulada:

```bash
simplicio-video generate approve itm_01HZEXEMPLO0000000000001 --by "Wesley" --yes
```

```text
itm_01HZEXEMPLO0000000000001: approved (por Wesley, 120 créditos)
```

A aprovação preenche `confirmed_by` (o nome de `--by`) e `confirmed_at` (horário de Brasília) no passo `ai_media`, e só então faz a transição `quoted -> approved`. Quando o orçamento recusa, a pergunta nem aparece.

Aprovar de novo um item já `approved` não faz nada: devolve código 0, informa quem aprovou e não grava outro evento.

### `generate show`

```bash
simplicio-video generate show itm_01HZEXEMPLO0000000000001
simplicio-video generate show itm_01HZEXEMPLO0000000000001 --json
```

```text
itm_01HZEXEMPLO0000000000001: approved
provider: real-oficial
estimate_ref: est_01
custo: 120 créditos
aprovado por: Wesley em 2026-10-08T10:00:00-03:00
```

Com `--json`, a saída traz `item`, `state`, `step` (o passo `ai_media` ou `null`), `credits`, `confirmed_by` e `confirmed_at`. Item sem passo mostra `sem passo ai_media: rode generate quote` e sai com código 0.

## Orçamento

O orçamento vem do arquivo de política do workspace, o mesmo que `simplicio-video setup` cria:

- **Arquivo:** `policy.yaml` em `$SIMPLICIO_WORKSPACE` (padrão `~/.simplicio-video/workspaces/default`). O setup grava `budgets.media_credits: 0`.
- **Chave:** `budgets.media_credits`, um inteiro maior ou igual a zero. Se o arquivo, a seção ou a chave não existir, vale `0`.
- **Teto diário:** `--daily-cap N` em `quote` e em `approve`. Padrão `1000`.

As regras, na ordem em que são checadas:

1. `media_credits = 0` recusa qualquer cotação e qualquer aprovação.
2. `credits` maior que `media_credits` é recusado. `media_credits` é o teto de cada gasto, não um saldo: o plugin não debita nada.
3. `credits` maior que o teto diário é recusado.
4. Os créditos já aprovados no dia mais `credits` não podem passar do teto diário. O dia é contado em horário de Brasília (UTC-3), pelos eventos `spend.approved`.

Para liberar orçamento, edite o `policy.yaml` do workspace. Não há comando que o altere.

## Quem pode aprovar

- Aprovação é um ato de uma pessoa. O comando pede a confirmação no terminal, e um agente não deve passar `--yes` por conta própria: só quando a pessoa pediu essa aprovação, naquela conversa.
- Não existe caminho que aprove sem `confirmed_by` preenchido. `--by` é obrigatório e não pode ser só espaços.
- Quem aprova escreve o próprio nome em `--by`. O comando não verifica identidade.

**Ressalva honesta.** O registro (`confirmed_by`, `confirmed_at` e o evento `spend.approved`) é auditoria. Ele guarda o nome que foi digitado em `--by`. Ele não prova que a aprovação veio de um humano. O controle real do gasto é a confirmação do Real Oficial: o `ro_confirm_spend`, que só roda com o `quote_id` e o `confirm:true` dados pela pessoa na conversa ou pelo botão do cartão. Esse passo acontece fora deste comando, e o `estimate_ref` que este plugin guarda é a referência da estimativa que o Real Oficial devolveu.

## Eventos

Os eventos vão para o mesmo log do store (`events.jsonl` em `SIMPLICIO_FACTORY_HOME`) que os eventos do kernel, com `seq` contínuo:

| Evento | Quando | Dados |
|---|---|---|
| `spend.quoted` | cotação registrada | `provider`, `estimate_ref`, `credits` |
| `spend.approved` | aprovação registrada | `provider`, `estimate_ref`, `credits`, `confirmed_by`, `at` |

A transição de estado continua gerando o evento `item.state_changed` do kernel. A aprovação repetida não grava nenhum dos três.

## Exemplo de ponta a ponta

Pré-requisito: o item precisa estar na rota `ai_assisted`. Hoje a rota é escolhida ao criar o item no kernel (`Item.production`, issue #82). Nenhum comando da CLI faz essa escolha, e o `make --from` do studio cria itens na rota `deterministic`.

```bash
# 1. workspace, com orçamento de mídia
simplicio-video setup --yes
#    edite ~/.simplicio-video/workspaces/default/policy.yaml e troque media_credits: 0 por 500

# 2. item na rota ai_assisted, em drafted (criado pelo kernel)
python -c "from simplicio_factory.contracts import Item; from simplicio_factory.contracts.json_store import JsonStore; JsonStore().save_item(Item(id='itm_01HZEXEMPLO0000000000001', brand='acme', state='drafted', production={'route': 'ai_assisted', 'steps': []}))"

# 3. cotação
simplicio-video generate quote itm_01HZEXEMPLO0000000000001 --provider real-oficial --estimate-ref est_01 --credits 120

# 4. aprovação, com a pessoa confirmando no terminal
simplicio-video generate approve itm_01HZEXEMPLO0000000000001 --by "Wesley"

# 5. conferência
simplicio-video generate show itm_01HZEXEMPLO0000000000001
```

Sem terminal, o passo 4 sai com `aprovação sem terminal exige --yes` e nada muda. Depois da aprovação, o item está em `approved` e o próximo passo é a geração no Real Oficial, fora deste plugin.

## Pendências conhecidas

- O `estimate_ref` é texto livre. O plugin não consulta o Real Oficial e não confere se a referência existe.
- O orçamento não tem saldo: `media_credits` limita cada gasto, e o total gasto só é contado por dia (teto diário).
- `--by` não é autenticado (ver [Quem pode aprovar](#quem-pode-aprovar)).
- O horário de Brasília é fixo em UTC-3, porque o Brasil não tem horário de verão desde 2019.
