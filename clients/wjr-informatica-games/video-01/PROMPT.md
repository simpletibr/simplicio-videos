# Prompt para iterar com Claude Opus 5.5 (Claude Code) ou Codex

Abra o agente **dentro desta pasta** (`clients/wjr-informatica-games/video-01`). Pré-requisito: skills do HyperFrames instaladas (ver `docs/setup.md`).
No Claude Code: `/model` → Opus 5.5, `/effort medium` (ou `high` na primeira passada criativa). Os relatos coletados indicam que `max` custa bem mais sem ganho garantido (ver `docs/tokens-e-deterministico.md`).

## 0) Prompt "showreel" adaptado para a WJR (passada criativa, do zero ou reforçando o template)

Base: o prompt mais repetido no acervo `awesome-opus5-5-videos` (103 dos 475 prompts citam "showreel"), ex. *"make a dynamic 15-second motion graphics video that shows what an incredible motion designer you are, like it's your showreel for a résumé. go all out."* — aqui com as travas de fato real, marca, áudio e determinismo:

```text
Faça um vídeo de motion graphics dinâmico de 20 segundos para a WJR Infogames (assistência técnica de
consoles e controles Xbox e PlayStation em Guarulhos) que mostre o quão incrível motion designer você é —
como se fosse o seu showreel para um currículo. Vá com tudo.

Travas (não negociáveis):
- Formato Instagram Reels 1080×1920, 30 fps, 20 s. HyperFrames (/hyperframes, /hyperframes-core,
  /hyperframes-animation). Edite index.html — não jogue fora data-composition-variables nem os data-var-*.
- Fatos: SÓ o que está em spec.json, roteiro.md e ../coleta/brief.md. Nada de preço, prazo, garantia, nota,
  número de clientes. Pode reescrever a ordem e o ritmo, não pode inventar.
- Cena de serviços (SV, 8,5–14 s) com os 3 serviços confirmados pelo cliente (coleta, fonte S3): limpeza de
  controle (pincel + poeira saindo + brilho), troca de metal líquido no PS5 (chip + gota prateada espalhando +
  reflexo), analógico Hall Effect no PS4/PS5 (ímã sob o analógico, arcos de campo, sensor magnético, traço
  circular preciso). Não prometa "sem drift", durabilidade, preço ou prazo.
- Marca: fundo #080808, vermelho #e50914, azul #1565ff, Anton + Inter (já embutidas). Tema gamer.
- Áudio é dado: trilha e SFX saem de scripts/build.mjs a partir de spec.json → audio (120 BPM, beat = 0,5 s).
  Todo corte cai num beat; todo golpe de texto tem um cue (whoosh na transição, hit/impact no título/logo,
  click/blip em item de lista, riser + glitch antes do CTA, impact no logo = pico do vídeo). Se mover um
  golpe visual, mova o cue em spec.json (e vice-versa). Master −14 LUFS / −1,5 dBTP.
- Motion (receitas): tipografia cinética por letra/palavra (stagger, scale-punch, máscara/clip-path),
  câmera (zoom-punch, push-in, shake curto no impacto, parallax de fundo), transição glitch/RGB-split,
  light sweep + glow no logo, grade em perspectiva + partículas com semente fixa + scanlines,
  ícone de controle reagindo (botões acendem no click), easing GSAP (power4/back/elastic só no logo).
- Narração: spec.json → voice.lines (9 frases pt-BR, Chatterbox local, velocidade natural — SEM aceleração).
  Os cortes foram desenhados em volta da duração real de cada frase (assets/audio/vo/manifest.json). Se mudar a
  coreografia, mantenha o texto na tela dizendo o mesmo que a voz naquele instante; se mudar uma frase, rode
  npm run voice (frase maior que o slot = erro: encurte o texto ou alargue o slot, nunca acelere).
- Clipes opcionais: spec.json → clips.slots (assets/imagine/clip-0N.mp4). Presente = placa de vídeo em
  tela cheia com shade; ausente = cena atual. Não quebre esse fallback.
- Determinismo: um gsap.timeline({paused:true}) em window.__timelines["main"]; nada de Math.random
  (use rng()), Date.now, fetch, repeat:-1.
- Legível sem som (Reels abre mudo). Texto mínimo 34 px, dentro da área segura.

Loop: edite → npm run lint → npm run check (0 erros) → npm run snapshot (olhe o contact sheet) →
npm run render:draft → me mostre o contact sheet e o MP4 antes do render final (npm run render + npm run loudness).
```

## 1) Refinar uma cena (barato em tokens)

```text
Usando /hyperframes, refine SÓ a cena S<n> de index.html (tempos em roteiro.md). Mantenha os tempos dos cues
de spec.json → audio (os golpes visuais têm que cair neles). Não mexa nas outras cenas.
Loop: lint → check → snapshot → me mostre os frames de S<n>.
```

## 2) Trocar assets quando o cliente mandar (sem LLM)

Coloque os arquivos em `assets/client/` e edite `spec.json → variables` (caminhos e textos). Clipes de vídeo: solte em `assets/imagine/clip-0N.mp4` (ver `assets/imagine/README.md`). Depois:

```bash
npm run check && npm run render && npm run loudness     # out/video-01.mp4
```

## 3) Nova variação (ex.: oferta/promoção)

```text
Duplique video-01 para ../video-02. Mantenha index.html e scripts/; altere só spec.json e, se preciso, UMA cena
(S3) para mostrar a oferta "<texto exato enviado pelo cliente>". Ajuste os cues de áudio dessa cena em spec.json.
Rode lint/check/snapshot e renderize em draft.
```

Padrões de prompt de onde isto foi derivado (com fontes): `docs/como-gerar-videos-opus-5-5.md`.
