# coleta/ — tudo que foi levantado sobre a WJR para gerar os vídeos

Pasta única com as **fontes de verdade** do cliente. Qualquer vídeo (`../video-*`) ou prompt para o Opus 5.5 deve citar só o que está aqui.
Levantamento: 30/09/2026 (BRT), fontes públicas, sem login.

| Arquivo | O que é |
|---|---|
| [`brief.md`](brief.md) | **Brief consolidado**: quem é, serviços, processo, tom, marca, frases reaproveitáveis (com fonte S1/S2 em cada fato) |
| [`fontes.md`](fontes.md) | Lista de fontes com URL, o que foi lido, data/hora e arquivo correspondente |
| [`site/index.html`](site/index.html) | Snapshot bruto do HTML do site |
| [`site/styles.css`](site/styles.css) | CSS do site (origem da paleta) |
| [`site/texto.md`](site/texto.md) | Texto do site extraído (sem HTML), na ordem da página |
| [`site/imagens/`](site/imagens/) | Logo e imagens públicas baixadas do site (rascunho; direito de uso não confirmado) |
| [`site/manifest.json`](site/manifest.json) | URL, tamanho e hash de cada imagem + meta tags do site |
| [`colors.json`](colors.json) | Paleta extraída (variáveis CSS reais + cores aproximadas do logo) e o que o video-01 usa |
| [`instagram-meta.json`](instagram-meta.json) | O que foi legível do Instagram (meta tags públicas) + data + o que **não** foi possível ler |
| [`pendencias.md`](pendencias.md) | O que falta / não verificado + rastreio de cada texto usado no video-01 |
| [`checklist-cliente.md`](checklist-cliente.md) | Checklist de pedido ao cliente com status + mensagem-modelo (rascunho, não enviada) |

## Como os vídeos usam esta pasta

- `../video-01/spec.json` → textos e cores copiados do `brief.md`/`colors.json` (nunca inventados).
- `../video-01/scripts/fetch-site-assets.sh` → copia `site/imagens/{logo,hero-consoles,repair-workbench}.png` para `video-01/assets/client/` (pasta ignorada pelo git) e só baixa do site se a cópia local não existir.
- Quando o cliente mandar material novo, coloque em `coleta/cliente/` (crie a pasta), registre em `fontes.md` e atualize `brief.md`/`pendencias.md` antes de mexer no vídeo.

> Repositório privado: as imagens do site ficam versionadas aqui só como registro da coleta. Não publicar nada daqui sem autorização do cliente.
