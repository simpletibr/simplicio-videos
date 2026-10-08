---
title: Studio (Draft e marca viram vídeo)
summary: O que o studio faz (Draft e brand.json viram contract.yaml e MP4), os comandos make, make preview e draft show, o composer determinístico, o claim guard, content_hash, a voz desligada por padrão, o template brand-promo e as pendências conhecidas.
commands: make, make preview, draft show
issue: 16
last_verified: 2026-10-08
---

# Studio

O studio (issue #16) é o plugin que transforma uma ideia de post em vídeo vertical. Ele recebe um **Draft** (ideia, fatos, claims, plataforma e duração) e a **marca** (`brand.json`: nome, cores, logo e fatos). Com isso, gera o `contract.yaml` do motor de vídeo e renderiza o MP4 pelo estágio `studio` do kernel. Não há LLM nem rede no caminho padrão.

Código: `src/simplicio_factory/plugins/studio/`. Comandos declarados em [plugin.json](../../src/simplicio_factory/plugins/studio/plugin.json) e registrados pelo host ([plugin-host.md](../host/plugin-host.md)). Estado do item e divisão de responsabilidades: [kernel.md](../host/kernel.md).

Escopo do MVP:

- formato 9:16, com duração de até 20 s;
- um único template, `brand-promo`, com três cenas;
- sem voz;
- um Draft gera um item; o estado do item só anda por `transition()`.

## Comandos

| Comando | Para quê |
|---|---|
| `simplicio-video make --from DRAFT.JSON [--brand BRAND.JSON]` | importa o Draft, cria o item e roda o estágio até `rendered` |
| `simplicio-video make ITEM` | roda o estágio de um item que já tem Draft na pasta |
| `simplicio-video make preview ITEM` | renderiza a prévia 540x960 com marca d'água; não muda o estado do item |
| `simplicio-video draft show ITEM` | imprime o Draft do item em JSON |

Cada comando tem `--help` com exemplo. O `brand.json` vem de `--brand` ou de `SIMPLICIO_FACTORY_HOME/brand.json` (padrão `.simplicio-factory/brand.json`).

### `make --from DRAFT.JSON`

Um Draft de exemplo (`draft.json`):

```json
{
  "item_id": "itm_01HZEXEMPLO0000000000001",
  "idea": "Um sorriso mais leve em uma sessão de 45 minutos.",
  "facts": {"sessao": "45 minutos"},
  "claims": ["Atendimento com hora marcada.", "Garantia de 1 ano no tratamento."],
  "platform": "9:16",
  "duration_s": 15
}
```

E a marca (`brand.json`), com os fatos que sustentam os números e as promessas do Draft:

```json
{
  "name": "Clínica Exemplo",
  "colors": {"primary": "#0b5d3b", "accent": "#f2b705", "ink": "#1d1d1b"},
  "logo": "logo.svg",
  "facts": {
    "sessao": "sessão de 45 minutos",
    "atendimento": "atendimento com hora marcada",
    "garantia": "garantia de 1 ano no tratamento",
    "unidade": "unidade no centro de Campinas"
  }
}
```

```bash
simplicio-video make --from draft.json --brand brand.json
```

```text
itm_01HZEXEMPLO0000000000001: rendered
mp4: <absoluto>/.simplicio-factory/studio/renders/itm_01HZEXEMPLO0000000000001.mp4
```

O comando copia o Draft para `studio/<item_id>/draft.json`. Se o item não existe, cria-o no kernel com estado `idea`. Depois, roda o estágio. Se o item já estiver `rendered`, o comando devolve o resultado anterior (ver [Pendências conhecidas](#pendências-conhecidas)).

Se um número, preço ou promessa do Draft não estiver em `brand.json`, o comando para com erro e o item continua em `idea`:

```text
erro: itm_01HZEXEMPLO0000000000001: claim sem fato em brand.json: '60%' em idea ('Um sorriso até 60% mais leve.'). Adicione o fato em brand.json (facts) ou remova o trecho do Draft.
```

### `make ITEM`

```bash
simplicio-video make itm_01HZEXEMPLO0000000000001
```

Usa o Draft já gravado em `studio/<item>/draft.json`. Erros: item inexistente (`item não encontrado`) e item sem Draft (`sem Draft para ...`). Ambos saem com código 1.

### `make preview ITEM`

```bash
simplicio-video make preview itm_01HZEXEMPLO0000000000001
```

```text
previa: <absoluto>/.simplicio-factory/studio/renders/<arquivo>.mp4
```

Gera o contrato da prévia (`studio/<item>/preview/contract.yaml`, 540x960, qualidade `draft`) e renderiza com marca d'água pela função de prévia do motor. O estado do item não muda, e a prévia não entra no `content_hash`.

### `draft show ITEM`

```bash
simplicio-video draft show itm_01HZEXEMPLO0000000000001 > draft.json
```

Imprime o `draft.json` do item em JSON, com indentação de 2 espaços e acentos preservados. Se o item não existe, sai com `item não encontrado`; se existe mas não tem Draft, com `sem Draft para o item`.

## Composer determinístico

`compose_contract(draft, brand)` monta o `contract.yaml` do motor (`simplicio.video-contract/v1`). A mesma entrada produz os mesmos bytes: a ordem das chaves vem do template, não há timestamp e não há rede. O golden de referência fica em `tests/factory/plugins/studio/golden/contract.yaml`.

O contrato gerado tem:

- `cliente`: slug e nome da marca, derivados de `brand.name`;
- `formato`: 9:16, 1080x1920 (540x960 na prévia), 30 fps e `duracao_s` do Draft;
- `template: brand-promo`;
- `marca`: paleta (`primary`, `accent`, `ink`) e o logo copiado para `assets/`;
- três cenas, com a duração do Draft dividida em três partes:
  - `s1` (gancho): a ideia, em duas linhas;
  - `s2` (prova): os claims, até dois;
  - `s3` (marca): o lockup, com o nome da marca, a cidade (do `facts`) e a chamada "Agende sua visita.";
- `voz.habilitada: false`;
- `trilha` com um groove contínuo;
- `saida`: `out/brand-promo.mp4`.

O composer recusa: plataforma sem preset (só `9:16`), duração fora de 0 a 20 s, mais de dois claims, nenhum claim, e uma marca sem as cores `primary`, `accent` e `ink`.

## Claim guard

Antes de compor, `check_claims` procura em `idea` e em cada claim:

- preço (`R$ 99`), percentual (`30%`) e números (`45`);
- as palavras `grátis`, `gratis`, `garantia`, `garantido`, `garantimos` e `cura`.

Cada trecho encontrado precisa aparecer em algum valor de `brand.facts`, comparado sem acento, em minúsculas e com espaços normalizados, como palavra inteira. Se não aparecer, o estágio levanta `ClaimError` com o trecho e o campo onde ele está, antes de qualquer transição.

## `content_hash`

Depois do render, o estúdio grava em `studio/<item>/studio.json` o `content_hash`, o caminho do MP4 e o sha256 do arquivo renderizado. O hash é o sha256 de três partes, cada uma com nome e tamanho:

1. `contract.yaml`;
2. o Draft em JSON canônico (chaves ordenadas, sem espaços);
3. os bytes de cada arquivo em `assets/`, em ordem.

O hash não fica em `item.json`: o kernel guarda só o estado do item.

## Voz

A voz é `none` por padrão. O composer sempre escreve `voz.habilitada: false`, então o studio não gera narração. Se um contrato for editado à mão para ligar a voz, o provider precisa existir no motor (`local`, `file` ou `gemini`).

## Template `brand-promo`

O template fica em `src/simplicio_video/data/templates/brand-promo/` (status `pronto`). Ele compõe só blocos que já existem em `motion/patterns`, sem mecanismo de render novo:

- `s1-words` (`kinetic-words`) para o gancho;
- `s2-words` (`kinetic-words`) para a prova;
- `s3-lockup` (`brand-lockup-soft`) para a marca.

O render de entrega é o do motor (`render_local`). A prévia usa `render_preview`.

## Pendências conhecidas

- **A marca nem sempre aparece no lockup.** O nome da marca fica na cena `s3`, mas nem sempre aparece no lockup. Por isso este documento não diz que a marca aparece em todos os frames.
- **Prévias com o mesmo nome.** O nome do MP4 da prévia vem da pasta do contrato, que é sempre `preview/`. Todas as prévias gravam `studio/renders/preview-previa.mp4` e uma sobrescreve a outra. O comando imprime esse caminho, mas o arquivo é compartilhado entre os itens.
- **Item já `rendered` não é re-renderizado.** Rodar `make` de novo, ou `make --from` com outro Draft, num item já `rendered` devolve o MP4 anterior. O `content_hash` não é comparado nesse caminho. Para outra versão, use outro item (outro `item_id`).
