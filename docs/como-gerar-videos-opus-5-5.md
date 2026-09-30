# Como as pessoas estão gerando vídeos com Claude Opus 5.5

> Pesquisa feita em 30/09/2026 lendo os repositórios (clones rasos) e dados abaixo. Números citados vêm das fontes; nada foi estimado por nós, salvo onde está escrito "nossa leitura".

Fontes principais:

| Repo | O que é | Licença |
|---|---|---|
| [yihui-dev/awesome-opus5-5-videos](https://github.com/yihui-dev/awesome-opus5-5-videos) | 475 vídeos com prompt (`data/videos.json`, `prompts/*.md`) | MIT |
| [chuspeeism/awesome-opus-5-5-videos](https://github.com/chuspeeism/awesome-opus-5-5-videos) | 300 casos categorizados (`data/cases.json`, `cases/*.md`, em chinês) | "NOASSERTION" (LICENSE diz MIT, © jadon7) |
| [heygen-com/hyperframes](https://github.com/heygen-com/hyperframes) | HTML + GSAP → MP4, feito para agentes, com skills | Apache-2.0 |
| [Vincentwei1021/video-shotcraft](https://github.com/Vincentwei1021/video-shotcraft) | skill de Claude Code/Codex sobre Remotion (152+ "shot cards") | Apache-2.0 |
| [calesthio/OpenMontage](https://github.com/calesthio/OpenMontage) | sistema agentic de produção (pipelines, Remotion/FFmpeg, provedores de IA) | AGPL-3.0 |
| [mexicat/pdoom-video](https://github.com/mexicat/pdoom-video) | videoclipe renderizado em código (three.js), feito com Opus 5.5 no Claude Code | MIT (código) |

## 1. O princípio: o modelo escreve código, não pixels

- "Every video here was made by asking Claude Opus 5.5 to write the animation as code (HTML, Canvas, SVG, Three.js and friends)." — [yihui-dev README](https://github.com/yihui-dev/awesome-opus5-5-videos#readme). O "how to use" do repo: colar o prompt no Opus 5.5 → "render the result as a single HTML file, then record the page".
- O vídeo final sai de um **renderizador determinístico**: navegador headless captura frame a frame + FFmpeg codifica. HyperFrames e Remotion fazem isso ("Both tools render video with headless Chrome and FFmpeg" — README do HyperFrames, seção *HyperFrames vs Remotion*). O pdoom-video faz igual com script próprio ("headless Chrome → raw frames over WebSocket → ffmpeg", `README.md` → *Layout*).

## 2. Qual stack as pessoas usam (dados reais)

Contagem nos 475 registros de `yihui-dev/.../data/videos.json` (campo `tech_tags` = tecnologia da **remake** feita pelo Skillry; campo `prompt` = texto do criador):

| Sinal | Nº de vídeos |
|---|---|
| tag `canvas` | 336 |
| tag `svg` | 193 |
| tag `threejs` | 141 |
| tag `shader` (GLSL) | 100 |
| tag `gsap` | 81 |
| prompt/post menciona **Remotion** | 62 |
| prompt/post menciona **HyperFrames** | 27 |
| prompt/post menciona **ffmpeg** | 19 |

Categorias: motion 288 · interactive 70 · explainer 62 · 3d 55. Em 196 dos 475 o prompt é parcial (o autor não publicou tudo).

No `chuspeeism/.../data/cases.json` (300 casos, busca textual): Blender 12, Suno 7, After Effects 6, Remotion 5, Three 5, ElevenLabs 5, HyperFrames 2 — ou seja, esse acervo inclui mais pipelines híbridos (Opus + ferramentas externas).

**Nossa leitura:**
- Para **vídeo de produto/marketing** (o caso da WJR), os dois caminhos dominantes são **Remotion** (React) e **HyperFrames** (HTML+GSAP). Canvas/SVG/Three.js "soltos" aparecem mais em peças artísticas/virais.
- HyperFrames cresceu rápido nos posts mais recentes e é o que o tutorial brasileiro viral usa (abaixo). É HTML puro, sem build, e tem render por variáveis (`--variables-file`, `--batch`) — por isso é a base do template deste repo.
- Remotion tem ecossistema maior (video-shotcraft, OpenMontage usam Remotion), mas tem licença própria: "free for individuals and small teams; companies may need a paid license" (nota no README do video-shotcraft).

## 3. Padrões de prompt que funcionam

### 3.1 O one-liner viral
O prompt mais repetido (aparece em vários registros, ex. [@ajith_io](https://x.com/ajith_io/status/2103449416325890146), [@tequilafunks](https://x.com/tequilafunks/status/2103528644828127728)):

```text
make a dynamic 15-second motion graphics video that shows what an incredible motion designer you are, like it's your showreel for a résumé. go all out.
```

Tutorial brasileiro ([@thayto_dev](https://x.com/thayto_dev/status/2104200591278739735), creditando @gabrielbuzziv), copiado de `data/videos.json`:

```text
1. instale a skill hyperframes
2. prompt: "make a dynamic 15-second motion graphics video that shows what an incredible motion designer you are, like it's your showreel for a résumé. go all out."
3. no prompt referencia a pasta do seu projeto
4. espera a mágica acontecer
modelo usado: opus 5.5 (effort: max)
```
O mesmo post diz: "isso gastou tipo 5% do limite de 5 horas". Variante no Cursor ([@danilowm](https://x.com/danilowm/status/2103661844661412022)): `/hyperframes make a dynamic 15-second ... use todo o contexto do projeto`.

**O que faz diferença** (relato de [@jesscaroline7](https://x.com/jesscaroline7/status/2104336637752955094)): a pasta do projeto referenciada tinha o app real (Claude gravou telas do simulador), dados reais (queries), 3D feitos à parte, trilha no Suno. Ou seja: **contexto real > prompt longo**.

### 3.2 Template com placeholders e regras (o mais útil para cliente)
[@ik_builds](https://x.com/ik_builds/status/2103890476885585923) — "Opus 5.5 (medium)", prompt publicado (trecho verbatim, via `prompts/ik-builds-585923.md`):

```text
Create a 15s motion-graphics film explaining {{PRODUCT}}. HyperFrames + GSAP, no voiceover, no footage.
Style: paper-light canvas, marker notes that draw on, real physics, huge kinetic type,
hard light/dark switches, a new idea every 1.5–2 s, a sound on every hit.

COPY: read {{POSITIONING_DOCS}} first. {{ONE_LINER}} For {{AUDIENCE}}. {{WHAT_IT_DOES}}
Name what the product learns, never the abstraction.

RULES
- No chrome (scrubber, timecode, fps, headers). No animator jargon on screen
  ("squash", "stagger", "easing"...). Every word speaks to the buyer.
- No invented results: no %, multipliers, customer names or figures.
- Never use: {{BANNED_WORDS}}.
- Logo: real mark {{LOGO_FILE}} + "{{PRODUCT}}" in {{WORDMARK_FONT}}; never a boxed logo file.
```
(O prompt continua com uma seção CRAFT: paleta, fontes, easing, "Set every from-state at t=0 (seek-safe)", "Check the HyperFrames registry first", e mixagem "-14 LUFS".)

### 3.3 Roteiro com tempos exatos + guardrails de fatos
[@HowDevelop](https://x.com/HowDevelop/status/2103840883812733090) (TanStack AI) — estrutura: formato e entregáveis (1920×1080, 30 fps, "exactly 15 seconds; keep important content within a 9:16-safe central area"), direção visual, **sequência segundo a segundo** (`0:00–0:02 — Hook ...`), "Accuracy guardrails" (o que não afirmar) e fechamento:

```text
Make the video, inspect the rendered result, and fix any clipped text, weak transitions, mistimed beats, or unreadable frames before delivering it. The goal is a memorable showreel, not a slideshow of feature bullets.
```

### 3.4 Usar o site real + regras de marca
[@wani_shola](https://x.com/wani_shola/status/2103769906638459278) (Remotion), verbatim:

```text
- Use as much of the real website as possible: capture the pages and sections in a browser (home, Ask, package pages, Hire, mobile view, dark mode) and animate them inside browser and phone frames.
- Show the site's chat answering real questions about my work, with the questions and answers large and bold. Use only facts and numbers that are on the site.
- Follow premium brand rules: three colours and the site's own fonts, one idea per shot, key objects centred, space to breathe, eased motion only, smooth transitions instead of hard cuts, and a rhythm that speeds up and slows down with the story.
```

### 3.5 Revisão por contact sheet
[@l3d1c](https://x.com/l3d1c/status/2104649028193632524): "It rendered about 20 stills and tiled them into one contact sheet, so I could check a whole cut at a glance before rendering any video." [@chapi13](https://x.com/chapi13/status/2104206465863131449) relata o mesmo. HyperFrames já gera isso: `npx hyperframes snapshot` escreve `contact-sheet.jpg` ("grid view for AI review").

**Padrão consolidado (nossa síntese):** formato + duração exatos → fonte de verdade (site/brief) → proibição explícita de inventar números → marca (3 cores, fontes, logo real) → sequência por segundos → "renderize, inspecione, corrija" (snapshot/contact sheet) → só então render final.

## 4. Skills para instalar (Claude Code / Codex)

| Skill | Comando (do README oficial) |
|---|---|
| HyperFrames (plugin Claude Code) | `claude plugin marketplace add heygen-com/hyperframes` e `claude plugin install hyperframes@hyperframes` |
| HyperFrames (skills avulsas, qualquer agente) | `npx skills add heygen-com/hyperframes` (escolha "Core Skills") ou, não-interativo, `npx hyperframes skills update` |
| video-shotcraft (Remotion) | `npx skills add Vincentwei1021/video-shotcraft` ou `git clone ... && ln -s "$(pwd)" ~/.claude/skills/video-shotcraft` (Codex: `~/.codex/skills/`) |
| OpenMontage | não é skill avulsa: `git clone https://github.com/calesthio/OpenMontage && make setup`, depois abrir o repo no agente |

Skills do HyperFrames relevantes para promo: `/hyperframes` (roteador), `/product-launch-video` (URL/brief → promo, fluxo em passos com gates: capture → `frame.md` → storyboard → frames → render), `/motion-graphics` (peças curtas < 30 s), `/hyperframes-core`, `/hyperframes-animation`, `/media-use` (BGM/SFX/TTS).

## 5. Comandos de render e requisitos

| Stack | Requisitos (fonte) | Render |
|---|---|---|
| HyperFrames | Node.js **22+**, FFmpeg (README) · Chrome headless baixado/gerenciado pela CLI (`npx hyperframes doctor`, `browser`) | `npx hyperframes render --quality draft\|looks\|delivery --output out.mp4`; `--variables-file`, `--batch rows.json`; também `cloud render`, AWS Lambda, Cloud Run (skill `hyperframes-cli`) |
| Remotion (video-shotcraft template) | Node 22 testado; em Linux headless: `--concurrency=1`, usar `chrome-headless-shell`, `--browser-executable=...` se o CDN estiver bloqueado (README → *Headless / CI notes*) | `remotion render src/index.ts <Comp> out/promo.mp4` (`template/package.json`) |
| OpenMontage | Python 3.10+, FFmpeg, Node.js 18+, um agente (README → *Prerequisites*) | pipeline dirigido pelo agente; `make demo` para demos sem chave |
| pdoom-video | bun, Google Chrome (playwright-core), ffmpeg com libx264 (README → *Requirements*) | `bun scripts/render.ts video --samples auto --shutter 0.2 --out ../out/pdoom.mp4` |

## 6. Custos declarados nas fontes

- **Preço Opus 5.5 (API):** US$ 4 / MTok entrada, US$ 20 / MTok saída, cache read US$ 0,20 / MTok, Batch 50% off ([docs da Anthropic](https://platform.claude.com/docs/en/models/opus-5-5/overview.md)).
- **Relatos de uso (não são faturas):** ~5% do limite de 5 h com a skill HyperFrames, effort max ([@thayto_dev](https://x.com/thayto_dev/status/2104200591278739735)); ~20% do limite de 5 h do plano Max em 20 min ([@Javi_llofriu](https://x.com/Javi_llofriu/status/2103372534922059888)); "145k tokens" com Remotion + ElevenLabs ([@ninjaswebcom](https://x.com/ninjaswebcom/status/2103537378283684126)); cena Three.js de ~3 h: 662.769 tokens de saída, "API-equivalent cost: about $54.52" ([@kgonia7](https://x.com/kgonia7/status/2103835848575746268)).
- **OpenMontage** publica custo por vídeo quando usa provedores de IA: "THE LAST BANANA" (60 s) "Total cost: $1.33"; "Reimagine Your Universe" "about $4"; faixa de prompts "~$0.15–$1.50" com provedor de imagem/vídeo e "~$1–$3" no setup completo (README).
- **pdoom-video:** render 4K "took about 2.5 hours on an M5 Pro" (custo de máquina, não de tokens).

Detalhes sobre economia de tokens e caminho determinístico: [`tokens-e-deterministico.md`](tokens-e-deterministico.md).

## 7. O que adotamos neste repo

- **HyperFrames** como stack do template (HTML + GSAP, sem build, render por variáveis, skills oficiais para Claude Code e Codex).
- Prompt de iteração no estilo 3.2 + 3.3 + 3.5: fonte de verdade = site do cliente, sem números inventados, tempos por cena, gate `lint → check → snapshot → render`.
- **Som + motion no nível dos showcases** (seção 8): trilha 120 BPM e SFX sintetizados por código a partir de cues em `spec.json`, cortes no beat, tipografia cinética, câmera, glitch/RGB split.
- **Narração pt-BR** com TTS local (Kokoro-82M, Apache-2.0), frases com tempo em `spec.json → voice`, cacheadas, música abaixando sob a voz: [`narracao-tts.md`](narracao-tts.md).
- **Prompt "showreel" adaptado para a WJR** (15 s, "go all out", com travas de fatos/marca/áudio): `PROMPT.md` §0.
- Veja `clients/wjr-informatica-games/video-01/PROMPT.md`.

> Os prompts acima foram copiados literalmente dos arquivos dos repositórios citados (ambos com LICENSE MIT); o conteúdo pertence aos autores linkados.

## 8. Som e motion: o que os melhores exemplos fazem (estudo para o video-01)

**O prompt "showreel".** No acervo `awesome-opus5-5-videos/data/videos.json`, **103 de 475** prompts citam "showreel"; a forma canônica é *"make a dynamic 15-second motion graphics video that shows what an incredible motion designer you are, like it's your showreel for a résumé. go all out."* Variações acrescentam o produto (*"…for &lt;website url&gt;"*, *"…on Distilbook"*), formato e loop (*"1080×1080, 1s hook, loop"* — [@Ishaaqahamed](https://x.com/Ishaaqahamed/status/2103837917538107563)) ou pedem pesquisa de técnica (*"check what are the recent trending techniques used for motion and sound design. question your strategy and plan, if it doesn't feel like done by a pro designer, start over"* — [@heyiammallik](https://x.com/heyiammallik/status/2103837803587293397)). A versão WJR está em `video-01/PROMPT.md` §0.

**Exemplos estudados e técnica extraída:**

| Exemplo | O que ensina | Como entrou no video-01 |
|---|---|---|
| [@twoclipping — launch film minimal](https://x.com/twoclipping/status/2102554209166000267) | estrutura em **compassos**: *"10 bars at 120 BPM, 2 seconds each. Bar 1: the hook lands word by word on the beats"*; drop com transformação; lista explícita do que é **proibido** | grade 120 BPM (beat 0,5 s, compasso 2 s); hook palavra a palavra nos beats; seções intro/groove/build/drop em `spec.json → audio.music.sections` |
| [@twoclipping — "Apple-keynote launch film"](https://x.com/twoclipping/status/2103835273813496100) | *"a royalty-free song around 120 BPM with a drop and a quiet breakdown"*; *"text rises out of a mask line, icons pop from zero on a spring, bars draw across"* | textos sobem por máscara (`.line { overflow:hidden }`), chips/steps com `back.out`, trilho do processo desenhado (`stroke-dashoffset`) |
| [@twoclipping / @__morse — UI morph](https://x.com/__morse/status/2103485566570369333) | "banned" list como ferramenta de direção de arte; câmera que dá zoom para cada estado encher a tela | câmera única (`#cam`) com zoom-punch/push-in por cena em vez de transições genéricas |
| `video-shotcraft/references/pipeline.md` (estágio 6, som) | *BGM define o esqueleto de energia, SFX pregado em cada keyframe*; **só desenhar o som depois de travar a imagem**; cues com tempo **relativo**; com bateria forte, SFX contido — **"grandes slams só em 2–3 picos"**; fecho padrão **riser → impact (pico do filme) → sparkle**; volume por pico medido | 2 impacts (1,25 s e 12,0 s = pico); riser 11–12 s → glitch → impact no logo → blip de cauda; cues em `spec.json` alinhados ao grid; ducking da música nos impacts |
| `hyperframes/skills/hyperframes-audio` | mix como relações (ducking, carve), fades, automação; preview e render usam o mesmo grafo Web Audio | aqui a mixagem é feita antes (WAV pronto, determinístico) e o HyperFrames só toca o `<audio id="soundtrack">`; alternativa documentada caso se prefira mixar dentro da composição |

**Divergências conscientes.** O shotcraft desaconselha timbres "de videogame" (pluck/bloop sintético) em vídeo de produto; os prompts minimalistas do @twoclipping proíbem RGB split, shake, grid floor e partículas. Aqui o cliente **é** uma assistência gamer e o pedido foi explicitamente por blips de UI, glitch e energia de showreel — então usamos essa estética de propósito, mas com contenção (2 slams, glitch só nas trocas de cena, elastic só no logo).

**Áudio sem licença de terceiros.** Em vez de baixar trilha/SFX (Pixabay, Freesound CC0, Kenney), o `scripts/build.mjs` **sintetiza** tudo (osciladores + ruído com semente + filtros biquad + reverb simples), mixa com sidechain e ducking e normaliza com `loudnorm` (−14 LUFS); `scripts/master.sh` re-mede no MP4 final e aplica limiter. Resultado verificado: −14,3 LUFS, true peak −1,7 dBTP. Vantagens: zero risco de licença, re-sincroniza sozinho quando um cue muda no JSON, e mesma entrada = mesmo WAV. Limite: é uma trilha "funcional" de 15 s, não uma produção musical — para campanhas maiores, trocar por trilha licenciada e registrar em `assets/audio/LICENSES.md`.

