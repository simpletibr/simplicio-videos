# Roteiro — video-01 "showreel" (Reels 9:16 · 15 s · 30 fps · 120 BPM)

Toda a copy vem do site do cliente (ver [`../coleta/brief.md`](../coleta/brief.md) e o rastreio em [`../coleta/pendencias.md`](../coleta/pendencias.md)). Nada de preço, prazo, garantia ou nota de avaliação até o cliente confirmar.
Espírito: "showreel de motion designer" (ver `PROMPT.md` §0) — cada corte cai no tempo da música, cada texto tem um golpe sonoro.

**Grade:** 120 BPM → 1 beat = 0,5 s, 1 compasso = 2 s. Cortes de cena e golpes de texto caem em beats/meios-beats. Os tempos abaixo são os mesmos de `spec.json → audio.cues` e dos `tl.*(…, t)` em `index.html`; mudou um, mude os três.

| Cena | Tempo | Texto na tela | Motion | Áudio (cue → t) | Asset |
|---|---|---|---|---|---|
| S1 Hook | 0,0–2,5 | pill "Assistência técnica em Guarulhos" · SEU / CONSOLE / **PAROU?** | letras sobem com stagger + back.out; "PAROU?" entra com scale-punch 2,4→1 + RGB split; câmera dá zoom-punch + shake; controle em outline girando ao fundo | intro (kick + baixo) · `hit-seu` 0,25 · `hit-console` 0,75 · `impact-parou` 1,25 (música abaixa 4 dB) | — |
| ↳ transição | 2,3–2,5 | — | **glitch**: fatias RGB varrem a tela + flash + jolt horizontal | `glitch-cut1` 2,3 · `whoosh-cut1` 2,35 | — |
| S2 Promessa | 2,5–4,5 | "A GENTE COLOCA ELE **DE VOLTA NO JOGO.**" | card 3D (rotationY −24°→0) com push-in na foto + light sweep; palavras sobem por máscara; faixa vermelha cresce atrás de "de volta no jogo."; saída com blur | groove entra (clap, hats, plucks) · `hit-promise` 3,0 · `whoosh-cut2` 4,3 | foto 1 (`photo_hero`) |
| S3 Problemas | 4,5–8,0 | "PROBLEMAS QUE RESOLVEMOS" · contador 01/05→05/05 · 5 problemas em revezamento · ressalva do site | cada problema entra com skew + scale + RGB split e sai para cima; barra segmentada enche; **controle SVG reage**: analógico faz "drift", botões acendem a cada item, LED pisca | `click-p1..p5` 4,6 · 5,2 · 5,8 · 6,4 · 7,0 | — |
| ↳ transição | 7,8–8,0 | — | glitch (mais leve) | `glitch-cut3` 7,8 · `whoosh-cut3` 7,85 | — |
| S4 Modelos | 8,0–10,5 | "XBOX + / PLAYSTATION" · 8 chips de modelos | foto em parallax (scale 1,25→1,05 + drift vertical); HUD de "Diagnóstico técnico" com cantos de mira e barra de scan; título entra por clip-path (esquerda/direita) + RGB split; chips em cascata alternando lados | `hit-models` 8,1 · `blip-chip1..8` 8,6→9,3 (tom subindo) · `whoosh-cut4` 10,3 | foto 2 (`photo_bench`) |
| S5 Processo | 10,5–12,0 | "COMO FUNCIONA" · "SEM SURPRESA." · 01 Fale no WhatsApp · 02 Diagnóstico · 03 Você aprova · 04 Reparo | trilho vermelho se desenha; passos pulam com back.out; câmera faz push-in 1→1,12 e treme no fim (build-up) | `blip-step1..4` 10,6 · 10,9 · 11,2 · 11,5 · `riser-cta` 11,0–12,0 · `glitch-precta` 11,8 | — |
| S6 CTA (drop) | 12,0–15,0 | logo · "VOLTE PARA O JOGO." · botão WhatsApp (11) 99700-5234 · endereço · @ | logo entra com elastic + 2 ondas de choque (vermelha/azul) + explosão de 28 partículas + shake; glow pulsando e light sweep no logo; título letra a letra; botão com mola e "respiração"; zoom lento até o fim | **drop** · `impact-logo` 12,0 (música abaixa 6 dB) · `blip-whatsapp` 12,9 · fade-out 14,1–15,0 | logo |

**Fundo (15 s):** piso de grade em perspectiva rolando, glows vermelho/azul derivando, 46 partículas com semente fixa subindo em parallax (tamanhos diferentes = profundidades diferentes), scanlines por cima de tudo, vinheta.

**Mix:** música a −4 dB com sidechain do kick (efeito "pump"), SFX por cima com ducking nos impactos, fade-in 0,25 s / fade-out 0,9 s, master −14 LUFS / −1,5 dBTP.

**Sem som:** todo texto é legível sem áudio (Reels abre mudo); o áudio reforça, não carrega informação.
