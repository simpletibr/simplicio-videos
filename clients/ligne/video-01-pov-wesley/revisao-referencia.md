# Revisão: Reel original (Den1y0iMUNY) × video-01 (v3 → v4)

Medido em 19/10/2026 com ffmpeg + correlação de fase (numpy) sobre os dois MP4. Original: 720x720, 30 fps, 26,0 s. Vídeo: 1080x1920, 30 fps, 26,1 s.

## O que o original realmente faz
- 8 cenas, 7 cortes secos em 3,77 / 7,23 / 10,97 / 14,87 / 16,93 / 19,0 / 22,97 s. A v3 e a v4 cortam nos mesmos instantes (≤ 1 quadro).
- Dentro de cada cena é imagem fixa: diferença média entre quadros 0,01–0,03 (escala 0–255) e primeiro×último quadro da cena 0,2–2,4; só 7 quadros mudam de verdade (diferença 78–119 nos cortes). Nada de pan, zoom ou rosto em movimento; o "movimento" vem só dos cortes na batida. (A v3/v4 têm diferença média de 9,5 por quadro: pan linear + soco de zoom de 7% em cada corte.)
- Gancho: rosto em close que ocupa o quadro inteiro e a frase POV já inteira no quadro 0, em letra grande (4 linhas, ~6% da altura), sem digitação.
- Pranchas em tela cheia, sem selo, sem sombra e sem legenda; a última cena (22,97–26 s) ainda é prancha, sem cartela de chamada.
- Áudio: AAC 44,1 kHz, -14,0 LUFS, TP -1,9 dBFS, LRA 2,9 LU. A v3/v4 usam essa mesma faixa (-14,1 LUFS, TP -2,3 dBFS, LRA 2,9 LU, fade de 0,4 s no fim).

## Diferenças encontradas na v3 e o que mudou na v4
| Ponto | Original | v3 | v4 |
|---|---|---|---|
| Texto do gancho | inteiro no quadro 0 | só aparece em 0,4 s e termina de digitar em ~1,3 s | inteiro no quadro 0 (`lead: 0`, `word_step: 0`), 80 px, 5 linhas |
| Rosto do gancho | close que preenche o quadro | foto de 540 px ampliada 2x, rosto pequeno + chapéu/ombros | ampliada 3x (lanczos + unsharp), `photo_h` 1560, foco nos olhos |
| Selo + sombra nas pranchas | não tem | "1/7 Cartela mestra…" cobrindo ~12% de baixo | removidos (`label`/`badge` vazios) |
| Quanto da prancha aparece | quadro quase todo | zoom 1,6 (62% da largura) | zoom 1,4 (71% da largura) |
| Última cena | prancha, sem chamada | cartela "Peça a sua consultoria" | igual à v3 (decisão de marca: mantém CTA) |

## Diferenças que continuam (e por quê)
- 9:16 em vez de 1:1: o Reel original é quadrado; o nosso preenche a tela do celular.
- Rosto: no original é outra pessoa (selfie em vídeo); aqui é o Wesley numa foto de 540 px (único recorte disponível), por isso a ampliação é suavizada.
- Pranchas: o original usa pranchas de outra pessoa; aqui são as 7 do Wesley (3e51ebb8…), e só 6 cenas de prancha (1, 3, 4, 5, 6, 7). Pranchas da Amanda/Bruna só com autorização por escrito delas.
- Movimento nas pranchas e CTA final: escolhas nossas, ausentes no original. Se o Wesley quiser fidelidade total, é só `ease: none`, `punch: 0`, `zoom: 1.0` no `board-pan` e trocar o s8 por uma prancha.
- Faixa do post original embutida: pode ser silenciada pelo Instagram; alternativa sem risco é postar pelo app com "Usar áudio" a partir de `out/ligne-pov-wesley-v4-silencioso.mp4`.
