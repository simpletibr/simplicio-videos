---
title: Media (orçamento e aprovação de gasto)
summary: Os comandos generate (quote, approve, start e show) e media attach que cotam, aprovam, iniciam e anexam a geração por IA de cada item na rota ai_assisted, com o orçamento media_credits do workspace, o teto diário, o recibo da mídia, a regra de quem pode aprovar e a ressalva sobre o registro.
commands: generate quote, generate approve, generate start, generate show, media attach
issue: 85
last_verified: 2026-10-08
---

# Media (orçamento e aprovação de gasto)

O plugin `media` (issue #85, épico #81) controla o gasto de geração por IA de cada item. Um item na rota `ai_assisted` (issue #82) passa pela cotação (`quote`), pela aprovação humana (`approve`), pelo início da geração (`start`) e pelo anexo da mídia gerada (`media attach`, issue #87), que grava o recibo e leva o item a `generated`. A consulta (`show`) mostra o gasto a qualquer momento. Só depois de aprovado o item pode seguir para a geração. O plugin não chama rede, não usa LLM e não gasta créditos: ele registra a decisão, aplica o orçamento e confere o arquivo gerado. O gasto real acontece no Real Oficial, e a confirmação de lá é o controle de fato (ver [Quem pode aprovar](#quem-pode-aprovar)). O passo a passo com o agente está em [gerar-video-real-oficial.md](../how-to/gerar-video-real-oficial.md).

Código: `src/simplicio_factory/plugins/media/` (`cli.py`, `budget.py`). Comando declarado em [plugin.json](../../src/simplicio_factory/plugins/media/plugin.json) e registrado pelo host ([plugin-host.md](../host/plugin-host.md)). Estado do item e transições: [kernel.md](../host/kernel.md). A rota `ai_assisted` e o grafo de transições estão em `src/simplicio_factory/contracts/transitions.py`.

## Comandos

| Comando | Para quê |
|---|---|
| `simplicio-video generate quote ITEM --provider real-oficial --estimate-ref REF --credits N [--daily-cap N]` | registra o custo estimado e leva o item de `drafted` para `quoted` |
| `simplicio-video generate approve ITEM --by NOME [--yes] [--daily-cap N]` | aprova o custo cotado e leva o item de `quoted` para `approved` |
| `simplicio-video generate start ITEM` | leva o item de `approved` para `generating`, se a aprovação estiver registrada |
| `simplicio-video generate show ITEM [--json]` | mostra o passo, o custo em créditos e quem aprovou |
| `simplicio-video media attach ITEM ARQUIVO --source real-oficial --media-id ID --prompt-file ARQ [--brand BRAND.JSON]` | anexa o MP4 gerado, grava o recibo e leva o item de `generating` para `generated` |

Cada comando tem `--help` com exemplo. `simplicio-video plugin list` mostra o plugin `media` com os comandos `generate` e `media`.

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

### `generate start`

Leva o item de `approved` para `generating` pelo `transition()`. Exige a aprovação registrada: o último passo `ai_media` precisa ter `confirmed_by`, que só `generate approve` grava. Sem ela, o comando recusa e não muda nada.

```bash
simplicio-video generate start itm_01HZEXEMPLO0000000000001
```

```text
itm_01HZEXEMPLO0000000000001: generating
```

Recusas: item fora de `approved` (`exige o estado approved`), sem aprovação registrada (`sem aprovação registrada`), item fora da rota `ai_assisted` (a transição é recusada) e item inexistente. A geração em si é feita no Real Oficial, depois do `ro_confirm_spend`.

### `media attach`

Anexa a mídia que o Real Oficial gerou ao item. O item precisa estar em `generating`. O arquivo é copiado, nunca movido, e a origem é `real-oficial`.

```bash
simplicio-video media attach itm_01HZEXEMPLO0000000000001 ~/Downloads/video.mp4 --source real-oficial --media-id med_01 --prompt-file prompt.txt
```

```text
itm_01HZEXEMPLO0000000000001: generated
media: .simplicio-factory/studio/itm_01HZEXEMPLO0000000000001/media/video.mp4
sha256: 3f2a...
```

O comando, nesta ordem:

1. confere o estado `generating` e a aprovação registrada (`confirmed_by`);
2. confere se o arquivo e o prompt existem;
3. passa o texto do prompt pelo claim guard do studio, contra os fatos de `brand.json` (padrão em `SIMPLICIO_FACTORY_HOME/brand.json`, ou `--brand`). Preço, número ou promessa que não estejam nos fatos recusam o attach, com o trecho na mensagem. Sem `brand.json`, o attach recusa, porque não há como conferir o prompt;
4. calcula o sha256 do arquivo e copia para `<pasta do item>/media/<nome>`, conferindo o sha256 da cópia;
5. grava o recibo `<pasta do item>/media.json`;
6. registra o evento `media.attached` e leva o item de `generating` para `generated` pelo `transition()`.

Qualquer recusa acontece antes de gravar o recibo e de mudar o estado. A pasta do item é `$SIMPLICIO_FACTORY_HOME/studio/<item_id>/`, a mesma do studio. Ajuda e exemplo: `simplicio-video media attach --help`.

### Recibo da mídia

O `media.json` tem o schema `simplicio.media-receipt/v1`:

| Campo | O que guarda |
|---|---|
| `arquivo` | nome do arquivo anexado (sem pasta) |
| `sha256` | sha256 do arquivo, calculado no attach |
| `origem` | `real-oficial` |
| `media_id` | id da mídia no Real Oficial (`--media-id`) |
| `estimate_ref` | referência da estimativa, do passo `ai_media` |
| `credits` | créditos cotados e aprovados, do passo `ai_media` |
| `confirmed_by` | quem aprovou, do passo `ai_media` |
| `prompt_sha256` | sha256 do arquivo de `--prompt-file`; o texto do prompt não entra no recibo |

A mídia anexada é imutável. O studio confere o sha256 de novo na hora do render: se o arquivo mudou, o render recusa com `mídia anexada foi alterada depois do attach`. Quando a mídia está conferida, o studio copia o arquivo para `assets/` e o `contract.yaml` ganha a entrada em `assets`. Sem mídia anexada, o contrato sai como antes (o composer só acrescenta `assets` quando recebe a mídia).

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
| `media.attached` | mídia anexada e recibo gravado | `media_id`, `origem`, `arquivo`, `sha256` |

A transição de estado continua gerando o evento `item.state_changed` do kernel, também no `generate start` e no `media attach`. A aprovação repetida não grava nenhum dos três eventos de gasto.

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

# 6. início da geração (depois do ro_confirm_spend no Real Oficial, com o aceite da pessoa)
simplicio-video generate start itm_01HZEXEMPLO0000000000001

# 7. mídia baixada do Real Oficial, anexada com recibo (o item vai para generated)
simplicio-video media attach itm_01HZEXEMPLO0000000000001 ~/Downloads/video.mp4 --source real-oficial --media-id med_01 --prompt-file prompt.txt
```

Sem terminal, o passo 4 sai com `aprovação sem terminal exige --yes` e nada muda. Depois da aprovação, o item está em `approved`. O passo 6 só vem depois do `ro_confirm_spend`, que a pessoa aceita no Real Oficial. O passo a passo com o agente, com as travas de personagem sintético, rótulo de IA e link pessoal, está em [gerar-video-real-oficial.md](../how-to/gerar-video-real-oficial.md).

## Pendências conhecidas

- O `estimate_ref` é texto livre. O plugin não consulta o Real Oficial e não confere se a referência existe.
- O orçamento não tem saldo: `media_credits` limita cada gasto, e o total gasto só é contado por dia (teto diário).
- Não há reanexo: um item em `generated` não volta a `generating`. Para trocar a mídia, crie outro item e refaça a geração.
- O recibo guarda o sha256 do prompt, não o texto. O claim guard confere o prompt, mas não há histórico dos prompts recusados.
- `--by` não é autenticado (ver [Quem pode aprovar](#quem-pode-aprovar)).
- O horário de Brasília é fixo em UTC-3, porque o Brasil não tem horário de verão desde 2019.
