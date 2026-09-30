# O que falta / não verificado — WJR (30/09/2026)

Regra do projeto: **nada desta lista entra em vídeo** até o cliente confirmar por escrito.

## Não verificado (não usar)
- Nota e quantidade de avaliações do Google (widget JS não lido).
- Bio, link, posts, reels e destaques do Instagram (exigem login). Só temos: nome de exibição, @, ~13K seguidores, 957 seguindo, 494 posts.
- Venda de consoles/jogos/PCs e "informática" geral (o nome no Instagram diz "informática", o site só fala de consoles e controles).
- Preços, prazos, garantia, formas de pagamento, tempo de mercado, nº de clientes atendidos.
- Origem e direito de uso das imagens do site (parecem ilustrativas/renderizadas, não fotos da loja).
- Qual paleta é a oficial: site (vermelho `#e50914` / azul `#1565ff`) × logo (creme/ciano/laranja) — ver [`colors.json`](colors.json).
- Fonte da marca (site usa Arial; o vídeo usa Anton + Inter, OFL).

## Faltando (pedir ao cliente)
- Logo original (SVG ou PNG ≥ 2000 px) e versão horizontal/ícone.
- Fotos e vídeos verticais reais: fachada, balcão, bancada, técnico, antes/depois.
- Ofertas/preços divulgáveis com validade (se houver).
- Confirmação de WhatsApp, endereço e horário.
- Autorizações: marca, imagens, pessoas; aprovação de roteiro e do vídeo.

Checklist completo com mensagem-modelo: [`checklist-cliente.md`](checklist-cliente.md).

## Usado no video-01 (e de onde veio)
| Texto/asset no vídeo | Fonte |
|---|---|
| "Seu console parou? A gente coloca ele de volta no jogo." | S1 (hero do site) |
| "Assistência técnica em Guarulhos" | S1 (kicker do hero) |
| 5 problemas (drift, não liga, superaquecimento, HDMI, botões) | S1 (lista de problemas) |
| Xbox 360 / One / Series X e S / controles Xbox; PS3 · PS4 / PS5 / DualShock / DualSense | S1 (seção Consoles) |
| Processo: WhatsApp → diagnóstico → aprovação → reparo | S1 ("Como funciona", resumido de 5 para 4 passos) |
| "Volte para o jogo." | S1 (frase do site) |
| WhatsApp, endereço, @ | S1 (+ S2 para o @) |
| Ressalva "A confirmação do serviço depende da avaliação técnica do equipamento." | S1 |
| Logo e 2 imagens (hero-consoles, repair-workbench) | S1b/S1c — **só rascunho**, até o cliente mandar os originais |
| Trilha e efeitos sonoros | gerados por código (`video-01/scripts/build.mjs`), sem material de terceiros |
