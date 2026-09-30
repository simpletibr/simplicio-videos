# Roteiro — video-01 "showreel" (Reels 9:16 · 20 s · 30 fps · 120 BPM)

Toda a copy vem de [`../coleta/`](../coleta/): site do cliente (fontes S1/S2) + **serviços confirmados pelo Wesley em 30/09/2026** (fonte S3: limpeza de controle, troca de metal líquido do PS5, analógico Hall Effect nos controles de PS5 e PS4). Rastreio em [`../coleta/pendencias.md`](../coleta/pendencias.md). Nada de preço, prazo, garantia, nota de avaliação ou promessa de "fim do drift" até o cliente confirmar.
Espírito: "showreel de motion designer" (ver `PROMPT.md` §0) — cada corte cai no tempo da música, cada texto tem um golpe sonoro.

**Grade:** 120 BPM → 1 beat = 0,5 s, 1 compasso = 2 s. Cortes de cena caem em beats; o drop do CTA cai no início do compasso 9 (16,0 s). Os tempos abaixo são os mesmos de `spec.json → audio.cues` e dos `tl.*(…, t)` em `index.html`; mudou um, mude os três. Os cortes foram desenhados **em volta da duração real de cada frase da narração** (sem acelerar a voz).

| Cena | Tempo | Texto na tela | Motion | Áudio (cue → t) | Asset |
|---|---|---|---|---|---|
| S1 Hook | 0,0–2,0 | pill "Assistência técnica em Guarulhos" · SEU / CONSOLE / **PAROU?** | letras sobem com stagger + back.out junto das palavras faladas (0,12 / 0,38 / 0,76); "PAROU?" com scale-punch + RGB split; zoom-punch + shake; controle em outline girando ao fundo | intro · `hit-seu` 0,25 · `hit-console` 0,5 · `impact-parou` 1,0 (música −4 dB) | — |
| ↳ transição | 1,8–2,0 | — | **glitch** forte (fatias RGB + flash + jolt) | `glitch-cut1` 1,8 · `whoosh-cut1` 1,85 | — |
| S2 Promessa | 2,0–4,0 | "A GENTE COLOCA ELE **DE VOLTA NO JOGO.**" | card 3D + push-in + light sweep; palavras por máscara; faixa vermelha atrás de "de volta no jogo."; saída com blur | groove entra · `hit-promise` 3,0 · `whoosh-cut2` 3,8 | foto 1 (`photo_hero`) |
| S3 Problemas | 4,0–6,5 | "PROBLEMAS QUE RESOLVEMOS" · 01/03→03/03 · CONTROLE COM DRIFT → SUPERAQUECIMENTO → CONSOLE NÃO LIGA · rodapé "+ Defeito no HDMI · Botões não funcionando" · ressalva do site | cada problema entra **na palavra falada** (4,05 / 4,7 / 5,9) com skew + scale + RGB split; barra de 3 segmentos; controle SVG reage: analógico faz "drift", corpo esquenta (vermelho), LED pisca em "não liga" | `click-p1..p3` 4,05 · 4,7 · 5,9 · `click-more` 6,0 | — |
| ↳ transição | 6,3–6,5 | — | glitch leve | `glitch-cut3` 6,3 · `whoosh-cut3` 6,35 | — |
| S4 Modelos | 6,5–8,5 | "XBOX + / PLAYSTATION" · 8 chips de modelos | foto em parallax; HUD "Diagnóstico técnico" + barra de scan; título por clip-path + RGB split; chips em cascata; push-in no fim | `hit-models` 6,6 · `blip-chip1..8` 7,0→7,56 (tom subindo) · `whoosh-sv1` 8,3 | foto 2 (`photo_bench`) |
| **SV Serviços** | 8,5–14,0 | kicker "SERVIÇOS" · contador 01/03→03/03 | 3 painéis que entram pela direita e saem pela esquerda no beat; título com RGB split; ilustração com back.out | `hit-services` 8,5 | — |
| ↳ SV-A Limpeza | 8,5–10,0 | "LIMPEZA DE / **CONTROLE**" · "Sujeira fora, botões e analógicos limpos" | controle com 34 pontos de sujeira (semente fixa); **pincel** varre da esquerda para a direita (8,85–9,5) e cada ponto sobe e some quando as cerdas passam; 6 brilhos em estrela no fim | `brush-sv1` 8,85 · `shimmer-clean` 9,45 · `whoosh-sv2` 9,82 | — |
| ↳ SV-B Metal líquido | 10,0–12,0 | "METAL LÍQUIDO / **NO PS5**" · "Troca de metal líquido no PlayStation 5" | placa + substrato + die do chip; barreira de espuma laranja se desenha; 6 gotas prateadas convergem; **mancha de metal líquido** cresce com elastic e "respira"; reflexo (shine) atravessa o die + glow | `blip-foam` 10,25 · `shimmer-lm` 10,8 · `shimmer-shine` 11,35 · `whoosh-sv3` 11,82 | — |
| ↳ SV-C Hall Effect | 12,0–14,0 | "ANALÓGICO / **HALL EFFECT**" · pills "sensor magnético" · PS4 · PS5 | vista de cima do analógico: **ímã N/S** sob o direcional, arcos de campo pulsando, **sensor magnético** com LED respondendo; o analógico faz 1,5 volta num círculo perfeito e o traço vermelho desenha a circunferência (precisão) | `blip-hall1` 12,3 · `blip-sensor` 12,5 · `click-ps4` 12,5 · `click-ps5` 12,6 · `blip-hall2` 13,1 | — |
| ↳ transição | 13,8–14,0 | — | glitch leve | `glitch-cut5` 13,8 · `whoosh-cut5` 13,85 | — |
| S5 Processo | 14,0–16,0 | "COMO FUNCIONA" · "SEM SURPRESA." · 01 Fale no WhatsApp · 02 Diagnóstico · 03 Você aprova · 04 Reparo | trilho vermelho se desenha; passos pulam com back.out; push-in 1→1,12 com o riser e shake no fim (build-up) | `blip-step1..4` 14,1 · 14,4 · 14,7 · 15,0 · `riser-cta` 15,0–16,0 · `glitch-precta` 15,8 | — |
| S6 CTA (drop) | 16,0–20,0 | logo · "VOLTE PARA O JOGO." · botão WhatsApp (11) 99700-5234 · endereço · @ | logo com elastic + 2 ondas de choque + 28 partículas + shake; glow pulsando e light sweep; título letra a letra; botão com mola (16,9) e "respiração" começando no "WhatsApp" falado (17,85); zoom lento até o fim | **drop** · `impact-logo` 16,0 (música −6 dB) · `blip-whatsapp` 16,9 · fade-out 19,1–20,0 | logo |

## Narração (VO) — pt-BR, velocidade natural (sem aceleração)

Voz: **Chatterbox Multilingual V3** (local, MIT) com timbre de referência sintético (Kokoro `pm_alex`, Apache-2.0), melhor de 3 sementes escolhida por transcrição automática; EQ + compressor leve + sala sutil. Comparativo e licenças em [`assets/audio/LICENSES.md`](assets/audio/LICENSES.md); como trocar em [`docs/narracao-tts.md`](../../../docs/narracao-tts.md). Fonte de verdade dos textos/tempos: `spec.json → voice.lines` (mudou aqui, mude lá e rode `npm run voice`).

| Linha | Cena | Início (s) | Fim (s) | Texto (tela/legenda) | Fala (`say`, só se diferente) |
|---|---|---|---|---|---|
| vo1 | S1 | 0,15 | 1,35 | “Seu console parou?” | — |
| vo2 | S2 | 2,00 | 3,91 | “A gente coloca ele de volta no jogo.” | — |
| vo3 | S3 | 4,00 | 6,53 | “Drift? Superaquecimento? Não liga?” | — |
| vo4 | S4 | 6,60 | 8,46 | “Xbox e PlayStation.” | “Équis box e PlayStation.” |
| vo5 | SV-A | 8,55 | 9,95 | “Limpeza de controle.” | — |
| vo6 | SV-B | 10,05 | 11,71 | “Metal líquido no PS5.” | “Metal líquido no PS cinco.” |
| vo7 | SV-C | 12,05 | 13,74 | “Analógico Hall Effect.” | “Analógico Ról Iféct.” |
| vo8 | S5 | 14,05 | 15,80 | “Você aprova antes do reparo.” | — |
| vo9 | S6 | 16,15 | 19,46 | “Chama a WJR no WhatsApp e volte pro jogo!” | “Chama a dáblio jota erre no WhatsApp e volte pro jogo!” |

"Guarulhos" saiu da fala da vo4 para caber o bloco de serviços sem acelerar a voz; continua na tela (pill do S1 e endereço do CTA). "PS4 e PS5" do Hall Effect aparecem na tela (pills) em vez de na fala.

Fatos usados: frase do hero do site ("Seu console parou? A gente coloca ele de volta no jogo."), problemas listados no site (drift, superaquecimento, console não liga, HDMI, botões), linhas atendidas (Xbox, PlayStation), cidade (Guarulhos), processo ("reparo realizado após a sua aprovação"), contato por WhatsApp, "Volte para o jogo" do site; serviços da cena SV: fonte S3 (confirmado pelo Wesley em 30/09/2026).

**Sincronia com a tela:** cada frase começa até 0,15 s depois do corte da sua cena, e o texto na tela diz a mesma coisa naquele instante (tempos das palavras medidos com faster-whisper). A música abaixa 10 dB e os efeitos 6 dB enquanto a voz fala; a vo9 entra 0,15 s depois do impacto do logo para não brigar com o boom.

**Fundo (20 s):** piso de grade em perspectiva rolando, glows vermelho/azul derivando, 46 partículas com semente fixa subindo em parallax, scanlines por cima de tudo, vinheta.

**Mix:** música a −4 dB com sidechain do kick, SFX por cima com ducking nos 2 impactos (hook e logo), narração por cima de tudo com ducking de música/SFX, fade-in 0,25 s / fade-out 0,9 s, master −14 LUFS / −1,5 dBTP.

**Sem som:** todo texto é legível sem áudio (Reels abre mudo); a narração repete o que está na tela.
