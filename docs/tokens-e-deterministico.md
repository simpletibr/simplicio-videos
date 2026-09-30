# Economia de tokens e caminho determinístico

> Pesquisa de 30/09/2026 (BRT). Fontes: posts no X (lidos via os registros do `awesome-opus5-5-videos` e busca web — o X em si não foi navegado), docs oficiais e READMEs dos repos. Relatos de consumo são **anedotas dos autores**, não medições nossas.

## 1. O que as pessoas relatam gastar

| Relato | Consumo declarado | Fonte |
|---|---|---|
| Skill HyperFrames + one-liner, Opus 5.5 effort max | "tipo 5% do limite de 5 horas" | [@thayto_dev](https://x.com/thayto_dev/status/2104200591278739735) |
| Vídeo de serviço de agência, Opus 5.5 + HyperFrames, 20 min | "20% do consumo de 5h do plano Max" | [@Javi_llofriu](https://x.com/Javi_llofriu/status/2103372534922059888) |
| Remotion + ElevenLabs | "145k tokens" | [@ninjaswebcom](https://x.com/ninjaswebcom/status/2103537378283684126) |
| Remotion, effort médio→alto, ~1h30 de conversa | "ربع حد ال 5 ساعات" (¼ do limite de 5 h) | [@YarHmm](https://x.com/YarHmm/status/2103505435802341449) |
| Filme Three.js "da Terra ao universo", ~3 h | 662.769 tokens de saída; cache 125,6M lidos / 2,0M escritos; "about $54.52" | [@kgonia7](https://x.com/kgonia7/status/2103835848575746268) |
| Lab interativo com 3 rodadas de revisão multi-agente | "5h 28m end to end, $90 at API prices" | [@Voxyz_ai](https://x.com/Voxyz_ai/status/2103117246860345550) |
| launchvideo.io (URL/prompt → MP4, 1 agente) | "roughly 90,000 input and 15,000 output tokens per film" | [Traictory, 25/09/2026](https://traictory.com/news/2026-09-25-claude-opus-video-as-code) |
| Vídeo de 37 s editado com Claude Code + HyperFrames, 4 renders | 263K tokens na 1ª sessão; ~10% do limite de 5 h do Max US$ 200 | [Clixie](https://www.clixie.ai/blog/claude-code-video-editing) |

**Leitura:** o custo explode com (a) effort alto/max, (b) sessões longas sem reset (cache read domina — ver @kgonia7), (c) loops de revisão que re-renderizam/re-geram tudo, (d) 3D/shaders complexos. Um promo de 15–30 s bem especificado fica na faixa de dezenas a poucas centenas de milhares de tokens.

## 2. Táticas de economia (com fonte)

1. **Effort médio por padrão.** Doc oficial: effort padrão do Opus 5.5 é `medium` e o thinking é sempre ligado — o effort controla a profundidade ([Anthropic](https://platform.claude.com/docs/en/models/opus-5-5/overview.md)). Um post agregador cita benchmark "VulcanBench" dizendo que Opus 5.5 pontua melhor em Medium/High que em Extra High/Max, "with costs rising sharply at higher effort settings" ([@AGTPinsights via nitter](https://nitter.jaydenha.uk/AGTPinsights/status/2103929231612981684) — fonte secundária, não verificamos o benchmark). O prompt de @ik_builds que "one-shots" foi rodado em **medium**.
2. **Skill/template em vez de gerar do zero.** Skills carregam o "como fazer" sob demanda, então o modelo não reinventa o contrato de render a cada vez. HyperFrames recomenda "Reuse-first": `npx hyperframes add <block>` e customizar, "hand-author only gaps" (skill `motion-graphics`); a doc de prompting diz que nomear blocos do catálogo faz o agente compor por reuso, enquanto omitir "hand-builds from your description — ... more drift" ([HyperFrames prompting](https://hyperframes.heygen.com/prompting/motion-graphics)). video-shotcraft entrega 150+ shot cards com implementação Remotion pronta ("Remotion implementations — Tuned TSX demos containing the actual easing and timing parameters").
3. **"Studio repo" reaproveitado.** "i have a dedicated 'studio' repo with all my project's style guides, tokens, few skills, remotion, etc." ([@francoxavier33](https://x.com/francoxavier33/status/2103486218323341663)). Um ad em Remotion "imports my site's CSS tokens and fonts" ([@l3d1c](https://x.com/l3d1c/status/2104649028193632524)). → Este repo segue a ideia: marca e template ficam versionados; o agente só edita.
4. **Revisar por still/contact sheet antes de renderizar vídeo** ([@l3d1c](https://x.com/l3d1c/status/2104649028193632524), [@chapi13](https://x.com/chapi13/status/2104206465863131449)). HyperFrames: `snapshot` gera `contact-sheet.jpg`; a skill CLI manda `lint`/`check` antes e "Never render merely because checks pass. Pause at the final preview".
5. **Re-renderizar só o trecho alterado.** Pipeline de Jason Cooperson: "partial-render system that re-renders only the segment you changed" ([Modern Creator](https://moderncreator.app/2026-06-29-jason-cooperson-how-i-fully-automated-my-video-editing-claude-code)). Render não gasta token, mas cada ciclo que o agente acompanha gasta.
6. **Prompt caching / sessões estáveis.** Cache read no Opus 5.5 = US$ 0,20/MTok (5% do input); mínimo cacheável 512 tokens ([Anthropic](https://platform.claude.com/docs/en/models/opus-5-5/overview.md)). Guias práticos: CLAUDE.md curto e estável, não trocar MCP no meio da sessão, referenciar arquivos por `@path` em vez de colar ([qcode.cc](https://docs.qcode.cc/en/docs/usage/cost-optimization), [momoraul/Lupen](https://github.com/momoraul/Lupen/blob/HEAD/docs/CLAUDE-CODE-TOKEN-GUIDE.md)).
7. **Modelo menor para boilerplate / subagentes.** Rotear subagentes simples para modelo menor e reservar Opus para decisões ([aleksandar.xyz](https://aleksandar.xyz/blog/2026-04-13-a-practical-guide-to-cutting-claude-code-token-usage-by-50-plus/)). Padrão de @stokebuilder: "Opus 5.5 agent at extra-high effort finds every timestamp ... Opus 5.5 at medium effort builds each animation ... judges each one once ... No blanket redo loops." (prompt em `awesome-opus5-5-videos`). *Decisão atual do Wesley: geração fica só com Opus 5.5 — então usar a variação de effort, não de modelo.*
8. **Spec em JSON + render sem LLM.** HyperFrames: variáveis declaradas no HTML e `render --variables-file` / `render --batch rows.json --strict-variables` (skill `hyperframes-cli`, `references/compare-and-batch.md`). Remotion: `--props=./props.json` e render em lote de dataset com `renderMedia({ inputProps })` ([Remotion docs](https://www.remotion.dev/docs/dataset-render)). Zero token por variação.
9. **Medir.** `ccusage` lê os JSONL locais do Claude Code e mostra gasto por bloco de 5 h (aleksandar.xyz). No ecossistema Simplicio: `simplicio savings record|report`.

## 3. Um caminho determinístico chega na mesma qualidade?

**Resposta curta:** chega na **mesma qualidade do template**, não na mesma *criatividade* de uma geração nova.

- O render em si **já é determinístico** em todas as stacks (frames capturados por tempo; HyperFrames exige timeline pausada e seek-safe, proíbe `Math.random` não semeado e relógio — `hyperframes-core`). Mesmo HTML + mesma spec = mesmo MP4.
- O que o LLM agrega é **direção criativa e código novo** (layout, coreografia, transições). Uma vez escrito e aprovado, esse código vira template; trocar textos/fotos/cores via spec não perde qualidade nenhuma — foi o que fizemos no `video-01` (todas as strings e imagens são `data-var-*`, render por `spec.json`).
- Bibliotecas de movimento prontas (shot cards do video-shotcraft, blocos do registry HyperFrames) permitem **montar** vídeos novos sem LLM, com qualidade de "motion designer", mas limitada ao vocabulário da biblioteca.
- O plugin `motion` do simplicio-runtime (`simplicio.storyboard/v1`) é determinístico e já existe, mas com catálogo fechado de 9 primitivas (title-card, bullet-reveal, stat-counter, screenshot-pan-zoom, logo-outro etc.). **Nossa avaliação:** ótimo para explainers/relatórios padronizados; para um Reels de loja fica mais "genérico" que o template HyperFrames — serve como fallback barato (exemplo em `clients/wjr-informatica-games/video-01/storyboard.simplicio.json`, **não validado contra o binário**, que não está instalado nesta máquina).

## 4. Pipeline proposto (Opus 5.5 hoje, determinístico depois)

```
brief.md (fatos do cliente, com fonte)
   │
   ├─(A) AUTOR — Opus 5.5, 1x por formato novo  ──►  template HyperFrames (index.html + variáveis)
   │        effort medium/high, skills HyperFrames, gate lint → check → snapshot
   │
   ├─(B) SPEC — por vídeo/variação                ──►  spec.json (textos, caminhos, cores)
   │        preenchida à mão, por formulário, ou pelo Opus em 1 chamada curta (só JSON)
   │
   └─(C) RENDER — sem LLM                          ──►  hyperframes render --strict-variables --variables-file spec.json
            (ou --batch rows.json para N variações; ou `motion build --ir storyboard.json` no runtime)
```

Regras práticas:
- Formato novo (ex.: "Reels de promoção", "Stories de antes/depois") → passo A com Opus 5.5.
- Variação de conteúdo (nova oferta, outro produto, outra loja) → só B + C. Custo de tokens ≈ 0.
- Ajuste pontual de uma cena → Opus 5.5 editando **uma** cena com diff pequeno, sem reescrever o arquivo.
- Guardar cada template aprovado em `templates/` (futuro) com sua `spec.schema.json` → vira o catálogo do plugin (ver `plugin-simplicio-runtime.md`).
