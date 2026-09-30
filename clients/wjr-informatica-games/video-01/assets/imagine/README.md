# assets/imagine/ — clipes verticais (Grok Imagine ou outro) para as cenas

Solte aqui os arquivos com estes nomes; `npm run build` (ou qualquer `render`) detecta, normaliza (1080×1920, 30 fps, sem áudio, corte "cover") para `assets/clips/build/` e liga o slot. Arquivo ausente ⇒ a cena usa o design atual (imagem/gráfico). Configuração em `spec.json → clips.slots` (cena, início, duração, `media_start_s` para escolher o trecho, `shade` = escurecimento 0–1 para o texto continuar legível).

| Arquivo | Cena | Janela | Conteúdo esperado | Uso |
|---|---|---|---|---|
| `clip-05.mp4` | S1 hook | 0,0–2,5 s | console ligando (LED/boot) | fundo atrás de "SEU CONSOLE PAROU?" (shade 0,5) |
| `clip-01.mp4` | S2 promessa | 2,5–4,5 s | console sendo aberto na bancada | substitui o card da `photo_hero` (tela cheia, shade 0,35) |
| `clip-02.mp4` | S3 problemas | 4,5–8,0 s | placa de controle sendo soldada | fundo do revezamento de problemas (shade 0,72) |
| `clip-03.mp4` | S4 modelos | 8,0–10,5 s | LEDs do controle acendendo (hero) | substitui a `photo_bench` (shade 0,3) |
| `clip-04.mp4` | S6 CTA | 12,0–15,0 s | pessoa jogando | fundo de "VOLTE PARA O JOGO." (shade 0,68) |

Regras: sem áudio útil (o vídeo é mudo; a trilha vem de `scripts/build.mjs`); qualquer proporção serve (é cortado para 9:16), mas vertical nativo fica melhor; mínimo = duração da janela (o último frame é congelado se faltar). Clipe gerado por IA é **ilustrativo**: não mostrar como se fosse a loja/equipe real do cliente sem o cliente aprovar (registrar em `../coleta/fontes.md` quando entrar).
