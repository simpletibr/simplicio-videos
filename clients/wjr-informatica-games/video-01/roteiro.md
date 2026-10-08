# Roteiro — video-01 "showreel" (Reels 9:16 · 20 s · 30 fps · 120 BPM)

Toda a copy vem de `../coleta/`: site do cliente (fontes S1/S2) + **serviços confirmados pelo Wesley em 30/09/2026** (fonte S3: limpeza de controle, troca de metal líquido do PS5, analógico Hall Effect nos controles de PS5 e PS4). Rastreio em `../coleta/pendencias.md`. Nada de preço, prazo, garantia, nota de avaliação ou promessa de "fim do drift" até o cliente confirmar.
Espírito: "showreel de motion designer" (ver `PROMPT.md` §0) — cada corte cai no tempo da música, cada texto tem um golpe sonoro.

**Grade:** 120 BPM → 1 beat = 0,5 s, 1 compasso = 2 s. Cortes de cena caem em beats; o drop do CTA cai no beat 33 (16,5 s). Os tempos abaixo são os mesmos de `spec.json → audio.cues` e dos `tl.*(…, t)` em `index.html`; mudou um, mude os três. Os cortes foram desenhados **em volta da duração real de cada frase da narração** (sem acelerar a voz).

| Cena | Tempo (s) | Texto na tela | Motion | Áudio (cue → t) |
|---|---|---|---|---|
| S1 Hook | 0,0–1,5 | pill "Assistência técnica em Guarulhos" · SEU / CONSOLE / **PAROU?** | letras nas palavras faladas; "PAROU?" (0,68) com scale-punch + RGB split; zoom-punch + shake | `hit-seu` 0,19 · `hit-console` 0,38 · `impact-parou` 0,75 · `glitch-cut1` 1,35 · `whoosh-cut1` 1,39 |
| S2 Promessa | 1,5–4,0 | "A GENTE COLOCA ELE **DE VOLTA NO JOGO.**" | card 3D + light sweep; faixa vermelha em "de volta" (2,5; palavra em 2,56); blur de saída | `hit-promise` 2,5 · `whoosh-cut2` 3,75 |
| S3 Problemas | 4,0–6,75 | 01/03→03/03: DRIFT → SUPERAQUECIMENTO → NÃO LIGA · rodapé HDMI/botões | itens nas palavras (4,05 / 5,05 / 5,95); controle reage | `click-p1..p3` 4,05 · 5,05 · 5,95 · `click-more` 6,05 · `glitch-cut3` 6,53 |
| S4 Modelos | 6,75–8,5 | XBOX + / PLAYSTATION · 8 chips | parallax + HUD + scan; chips em cascata | `hit-models` 6,84 · `blip-chip1..8` 7,19→7,68 · `whoosh-sv1` 8,33 |
| SV-A Limpeza | 8,5–10,25 | SERVIÇOS 01/03 · LIMPEZA DE / CONTROLE | pincel varre (8,9–9,7), sujeira some, brilhos | `hit-services` 8,5 · `brush-sv1` 8,91 · `shimmer-clean` 9,61 · `whoosh-sv2` 10,04 |
| SV-B Metal líquido | 10,25–12,5 | 02/03 · METAL LÍQUIDO / NO PS5 | barreira, gotas, mancha prateada, reflexo | `blip-foam` 10,53 · `shimmer-lm` 11,15 · `shimmer-shine` 11,77 · `whoosh-sv3` 12,30 |
| SV-C Hall Effect | 12,5–14,5 | 03/03 · ANALÓGICO / HALL EFFECT · sensor magnético · PS4 · PS5 | ímã orbitando, arcos de campo, sensor, traço circular | `blip-hall1` 12,8 · `blip-sensor`/`click-ps4` 13,0 · `click-ps5` 13,1 · `blip-hall2` 13,6 · `glitch-cut5` 14,3 |
| S5 Processo | 14,5–16,5 | COMO FUNCIONA · SEM SURPRESA. · 4 passos | trilho + passos; push-in com o riser | `blip-step1..4` 14,6 · 14,9 · 15,2 · 15,5 · `riser-cta` 15,5–16,5 · `glitch-precta` 16,3 |
| S6 CTA (drop) | 16,5–20,0 | logo · VOLTE PARA O JOGO. · WhatsApp · endereço · @ | logo elastic + ondas + partículas; botão (17,3) respira no "WhatsApp" falado (18,1) | **drop** · `impact-logo` 16,5 · `blip-whatsapp` 17,29 · fade-out 19,1–20,0 |

Os cortes seguem a duração real de cada frase (grade de 0,25 s = meio beat a 120 BPM). A coreografia no `index.html` é escrita numa grade base e remapeada cena a cena pelo bloco `RETIME` (`CUTS`); acertos de palavra usam tempo absoluto (`"@t"`). Música: intro 0–1,5 · groove 1,5–15,5 · build 15,5–16,5 · drop 16,5–20 (o drop cai num beat, meio compasso).

## Narração (VO) — pt-BR, velocidade natural (sem aceleração)

Voz: **Gemini 3.8 Flash TTS, voz Puck** (Google AI Studio, conta do Wesley, 30/09/2026), estilo "Locutor brasileiro de propaganda de loja de games, tom animado, natural e próximo, português do Brasil, ritmo ágil sem correr." Entra pelo provider `file` (`assets/audio/vo/external/line-NN.wav`) com corte de silêncio + EQ/compressor/sala. Licença em [`assets/audio/LICENSES.md`](assets/audio/LICENSES.md); passo a passo em [`voices/gemini.md`](../../../voices/gemini.md).

| Linha | Cena | Início (s) | Fim (s) | Duração (s) | Máx. (s) | Texto |
|---|---|---|---|---|---|---|
| vo1 | S1 | 0,05 | 1,42 | 1,37 | 1,45 | “Seu console parou?” |
| vo2 | S2 | 1,50 | 3,94 | 2,44 | 2,50 | “A gente coloca ele de volta no jogo.” |
| vo3 | S3 | 4,00 | 6,73 | 2,73 | 2,80 | “Drift? Superaquecimento? Não liga?” |
| vo4 | S4 | 6,80 | 8,50 | 1,70 | 1,75 | “Xbox e PlayStation.” |
| vo5 | SV-A | 8,55 | 10,29 | 1,74 | 1,75 | “Limpeza de controle.” |
| vo6 | SV-B | 10,30 | 12,53 | 2,23 | 2,25 | “Metal líquido no PS5.” |
| vo7 | SV-C | 12,55 | 14,39 | 1,84 | 2,00 | “Analógico Hall Effect.” |
| vo8 | S5 | 14,55 | 16,45 | 1,90 | 2,05 | “Você aprova antes do reparo.” |
| vo9 | S6 | 16,60 | 19,87 | 3,27 | 3,40 | “Chama a WJR no WhatsApp e volte pro jogo!” |

(Duração = arquivo tratado, incluindo ~0,1 s de cauda da sala.)

"Guarulhos" saiu da fala da vo4 para caber o bloco de serviços sem acelerar a voz; continua na tela (pill do S1 e endereço do CTA). "PS4 e PS5" do Hall Effect aparecem na tela (pills) em vez de na fala.

Fatos usados: frase do hero do site ("Seu console parou? A gente coloca ele de volta no jogo."), problemas listados no site (drift, superaquecimento, console não liga, HDMI, botões), linhas atendidas (Xbox, PlayStation), cidade (Guarulhos), processo ("reparo realizado após a sua aprovação"), contato por WhatsApp, "Volte para o jogo" do site; serviços da cena SV: fonte S3 (confirmado pelo Wesley em 30/09/2026).

**Sincronia com a tela:** cada frase começa até 0,1 s depois do corte da sua cena, e o texto na tela diz a mesma coisa naquele instante (tempos das palavras medidos com faster-whisper). A música abaixa 10 dB e os efeitos 6 dB enquanto a voz fala; a vo9 entra 0,1 s depois do impacto do logo para não brigar com o boom.

**Fundo (20 s):** piso de grade em perspectiva rolando, glows vermelho/azul derivando, 46 partículas com semente fixa subindo em parallax, scanlines por cima de tudo, vinheta.

**Mix:** música a −4 dB com sidechain do kick, SFX por cima com ducking nos 2 impactos (hook e logo), narração por cima de tudo com ducking de música/SFX, fade-in 0,25 s / fade-out 0,9 s, master −14 LUFS / −1,5 dBTP.

**Sem som:** todo texto é legível sem áudio (Reels abre mudo); a narração repete o que está na tela.
