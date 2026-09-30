# Extração automática (site / Instagram)

Objetivo: preencher o máximo do `intake.json` sozinho, **com fonte e data em cada fato**, e perguntar só o resto. Referência do que sai: [`exemplos/wjr-informatica-games.intake.json`](exemplos/wjr-informatica-games.intake.json) (extraído do site e do Instagram públicos da WJR em 30/09/2026).

## Regras gerais

1. **Só dado público, sem login.** Nada de sessão/cookie de Instagram, nada de burlar bloqueio. Se o conteúdo exige login, registre "não lido" e pergunte.
2. **Cada fato = `{valor, fonte, ref, data, confirmado}`.** `fonte: site|instagram` só para o que está escrito lá; interpretação do agente (nicho, tom) é `inferido` e precisa de confirmação.
3. **Nunca inventar** preço, prazo, garantia, número de clientes, avaliações, anos de mercado. Widget carregado por JS que não foi lido = "não verificado".
4. Salve o material bruto em `clients/<slug>/coleta/site/` (HTML, CSS, imagens) e `instagram-meta.json`, e liste cada fonte em `fontes.md` com URL + data/hora de acesso (BRT).
5. Logo e fotos do cliente vão para `assets/client/` (gitignored) até `uso_de_imagem_aprovado = true`.

## Site

| Campo | Onde procurar | Como |
|---|---|---|
| `empresa.nome` | `<title>`, `og:site_name`, logo `alt`, rodapé, schema.org `Organization/LocalBusiness` | preferir o nome do rodapé/JSON-LD; registrar variações |
| `empresa.descricao` | `meta description`, hero (h1 + subtítulo), seção "sobre" | copiar literal (é a fonte das frases) |
| `empresa.nicho` → `setor_template` | descrição + lista de serviços | mapear com a tabela de `templates/README.md`; marcar `inferido` |
| `empresa.servicos` | seções "serviços", "o que fazemos", cards, menu | um fato por item, texto literal |
| `empresa.ofertas` | banners, "promoção", preços | só se estiver escrito com valor; guardar validade |
| `empresa.diferenciais` | "por que nós", "como funciona" | literal |
| `empresa.frases_proprias` | h1/h2, CTAs, slogans | são a melhor copy: reaproveitar no roteiro |
| `empresa.contatos` | links `wa.me/…`, `tel:`, `mailto:`, rodapé, Google Maps embed, JSON-LD `address`/`openingHours` | normalizar telefone `(DD) 9XXXX-XXXX` |
| `marca.logo` | `<img>` do header, `og:image`, `favicon`/`apple-touch-icon` (último recurso) | baixar o maior; SVG > PNG |
| `marca.cores` | variáveis CSS (`:root { --primary … }`), cores de botões/links, `theme-color` | CSS real > amostragem do logo; salvar em `coleta/colors.json` com a origem |
| `marca.fontes` | `font-family`, Google Fonts `<link>` | se a fonte não for livre para vídeo, usar equivalente OFL e anotar |
| `marca.tom` | textos do site | resumir em 1 linha; `inferido` |

## Instagram (perfil público)

| Campo | Onde | Observação |
|---|---|---|
| nome, @, bio curta | meta tags públicas `og:title` / `og:description` (via `curl`) | é o que dá para ler sem login |
| seguidores/posts | `og:description` (números arredondados pelo Instagram) | não usar como "prova social" sem o cliente confirmar |
| link da bio | `og:description` / página | pode revelar site/WhatsApp |
| posts, destaques, cores do feed | exigem login na maioria dos casos | **não ler**; pedir ao cliente prints/arquivos se precisar |

## Depois da extração

1. Montar o resumo para o usuário (o que achou + fontes) e as perguntas do [bloco B](questionario.md#bloco-b--o-vídeo-sempre), mais A-itens que faltaram e tudo que ficou `inferido`.
2. Conflito entre fontes (ex.: nome diferente no site e no Instagram) → perguntar qual usar.
3. Gravar `intake.json`, atualizar `brief.md`, `fontes.md`, `pendencias.md` do cliente.

Ferramentas: `curl` + parse de HTML/CSS (sem navegador quando possível); navegador só para páginas renderizadas por JS, e nunca logado em conta de terceiros.
