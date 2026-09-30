# Fontes consultadas — WJR Informática e Games

Horários em BRT (UTC-3). Tudo foi lido **sem login** e **sem navegador logado**, só `curl`/fetch público.

| # | URL | O que foi lido | Quando | Arquivo aqui |
|---|---|---|---|---|
| S1 | https://www.wjrinformaticagames.com.br/ | HTML completo (servidor: Hostinger; `last-modified: 17/09/2026 00:34 UTC` = 16/09/2026 21:34 BRT) | 30/09/2026 13:13 (re-checado 13:33) | [`site/index.html`](site/index.html), [`site/texto.md`](site/texto.md) |
| S1a | https://www.wjrinformaticagames.com.br/css/styles.css?v=2 | variáveis de cor e fonte | 30/09/2026 13:13 | [`site/styles.css`](site/styles.css), [`colors.json`](colors.json) |
| S1b | https://www.wjrinformaticagames.com.br/assets/logo.png | logo PNG 1254×1254 com transparência | 30/09/2026 13:33 | [`site/imagens/logo.png`](site/imagens/logo.png) |
| S1c | …/assets/hero-consoles.png · …/assets/repair-workbench.png · …/assets/controller-components.png | imagens do site (aparentam ser ilustrativas/renderizadas) | 30/09/2026 13:33 | [`site/imagens/`](site/imagens/) |
| S1d | …/assets/images/consoles/{xbox-360, xbox-fat-slim, xbox-one, xbox-controles, ps3, ps4, ps5}.png · dualshock-dualsense.jpg | miniaturas dos modelos atendidos | 30/09/2026 13:33 | [`site/imagens/consoles/`](site/imagens/consoles/) |
| S3 | Wesley Simplicio (responsável pelo projeto), mensagem de 30/09/2026 ~14:06 BRT | serviços: limpeza de controle; troca de metal líquido do PS5; analógico Hall Effect em controles de PS5 e PS4 | 30/09/2026 | [`brief.md`](brief.md) § Serviços confirmados |
| S2 | https://www.instagram.com/wjrinformaticagames/ | só meta tags Open Graph (`og:title`, `og:description`) via `curl -A facebookexternalhit/1.1` | 30/09/2026 13:1x e 13:33 (mesmos números) | [`instagram-meta.json`](instagram-meta.json) |

Hashes (sha256, 16 primeiros caracteres), tamanhos e URL de cada imagem: [`site/manifest.json`](site/manifest.json). O manifesto também guarda as meta tags do site.

## Observações

- A meta `og:url` do site aponta para `https://wjr-conserto-de-controles.danielzkernel.chatgpt.site` (o site parece ter sido publicado a partir desse endereço). Não afeta o vídeo; só registra a origem.
- As avaliações do Google na seção "Quem já trouxe, recomenda" são carregadas por widget JS (Elfsight) e **não** aparecem no HTML → não foram lidas.
- Nenhum outro canal (Google Maps, Facebook, TikTok, WhatsApp Business) foi consultado.
