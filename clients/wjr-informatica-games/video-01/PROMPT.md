# Prompt para iterar com Claude Opus 5.5 (Claude Code) ou Codex

Abra o agente **dentro desta pasta** (`clients/wjr-informatica-games/video-01`). Pré-requisito: skills do HyperFrames instaladas (ver `docs/setup.md`).
No Claude Code: `/model` → Opus 5.5, `/effort medium` (ou `high` na primeira passada criativa). Os relatos coletados indicam que `max` custa bem mais sem ganho garantido (ver `docs/tokens-e-deterministico.md`).

## 1) Primeira iteração (refinar o template existente)

```text
Usando /hyperframes (skills hyperframes-core e hyperframes-animation), refine a composição
existente em index.html — NÃO recrie do zero. Leia antes: AGENTS.md, roteiro.md, ../brief.md, spec.json.

Formato: Instagram Reels 1080×1920, 30 fps, 22 s, sem locução, precisa funcionar sem som.
Marca: fundo #080808, vermelho #e50914, azul #1565ff (variáveis primary/secondary), fontes Anton + Inter já embutidas.
Copy: use APENAS os textos de spec.json e roteiro.md (vêm do site do cliente). Não invente preço, prazo,
garantia, nota de avaliação, número de clientes ou qualquer métrica.

Objetivo desta passada:
- hook mais forte nos primeiros 1,5 s (o texto "SEU CONSOLE PAROU?" deve ser legível no 1º segundo);
- transições entre cenas que demonstrem a ideia (ex.: o "flash" vira o card da foto), sem push/slide genérico;
- manter todos os data-var-* e o bloco data-composition-variables intactos (o render determinístico depende deles);
- continuar seek-safe: um único gsap.timeline({paused:true}) em window.__timelines["main"], sem Math.random, sem repeat:-1.

Loop: edite → `npm run lint` → `npm run check` (0 erros) → `npm run snapshot` e olhe o contact sheet →
só então `npm run render:draft`. Pare e me mostre o contact sheet antes do render final.
```

## 2) Trocar assets quando o cliente mandar (sem LLM)

Coloque os arquivos em `assets/client/` e edite `spec.json` (caminhos e textos). Depois:

```bash
npm run check && npm run render     # out/video-01.mp4
```

## 3) Nova variação (ex.: oferta/promoção) — barata em tokens

```text
Duplique video-01 para ../video-02. Mantenha index.html; altere só spec.json e, se preciso, UMA cena
(S3) para mostrar a oferta "<texto exato enviado pelo cliente>". Não mexa nas outras cenas.
Rode lint/check/snapshot e renderize em draft.
```

Padrões de prompt de onde isto foi derivado (com fontes): `docs/como-gerar-videos-opus-5-5.md`.
