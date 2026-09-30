# Brief — WJR Informática e Games (WJR Infogames)

> Levantado em 30/09/2026 (BRT) a partir de fontes públicas. **Só fatos que aparecem nas fontes abaixo.**
> O que não foi encontrado está marcado como **não verificado** — não usar em vídeo sem o cliente confirmar.

## Fontes

| # | Fonte | Como foi lida |
|---|---|---|
| S1 | https://www.wjrinformaticagames.com.br/ | `curl` do HTML + `css/styles.css?v=2` |
| S2 | https://www.instagram.com/wjrinformaticagames/ | meta tags públicas (`og:title`/`og:description`) via `curl`; o conteúdo do perfil (bio, posts) exige login e **não** foi lido |

## Quem é

- **Nome no site:** "WJR Conserto De Controles" / "WJR Infogames" (título da página: *WJR Conserto de controles*) [S1]
- **Nome no Instagram:** "Wjr informática e games Assistência Técnica!" — @wjrinformaticagames [S2]
- **O que faz:** "Assistência técnica especializada em consoles e controles Xbox e PlayStation. Diagnóstico profissional, manutenção especializada e atendimento rápido." [S1]
- **Onde:** R. Siderópolis, 168 — Jardim Jovaia, Guarulhos - SP [S1]
- **Contato:** WhatsApp / telefone **(11) 99700-5234** (`wa.me/5511997005234`) [S1]
- **Horário:** seg–sex 8h–17h · sáb 8h–14h · dom fechado. "Entre em contato antes de trazer seu equipamento." [S1]
- **Instagram (público, 30/09/2026):** 13K seguidores · 957 seguindo · 494 posts (arredondado pelo próprio Instagram) [S2]
- **Avaliações:** o site tem uma seção "Quem já trouxe, recomenda" com widget de avaliações do Google (Elfsight). As notas e textos são carregados por JS e **não** foram lidos → **não citar nota/quantidade de avaliações** sem confirmar.

## O que atendem (texto do site) [S1]

| Linha | Modelos citados |
|---|---|
| Xbox 360 | Slim e Super Slim |
| Xbox One | FAT e One S |
| Xbox Series X e Series S | — |
| PlayStation 3 | Slim e Super Slim |
| PlayStation 4 | FAT, Slim e Pro |
| PlayStation 5 | "Diagnóstico e manutenção especializada" |
| Controles Xbox | analógicos, botões, conexão, carregamento e outros defeitos |
| DualShock / DualSense | controles PS3, PS4 e PS5 |

**Problemas listados:** console não liga · desligando sozinho · superaquecimento · problemas de vídeo · defeito no HDMI · limpeza interna · manutenção preventiva · controle com drift · analógico puxando sozinho · botões não funcionando · gatilhos com defeito · controle sem conexão · problemas no carregamento · conector USB danificado · problemas de alimentação · diagnóstico eletrônico. Ressalva do próprio site: *"A confirmação do serviço depende da avaliação técnica do equipamento."*

**Processo ("Como funciona"):** 1 Fale conosco (WhatsApp) → 2 Explique o problema → 3 Diagnóstico → 4 Aprovação do orçamento → 5 Reparo ("realizado após a sua aprovação"). "Sem compromisso."

**Diferenciais declarados:** atendimento especializado, diagnóstico cuidadoso, transparência, atendimento rápido (contato direto pelo WhatsApp).

**Frases do site reaproveitáveis:** "Seu console parou? A gente coloca ele de volta no jogo." · "Problema no console? Não deixe ele parado." · "Volte para o jogo" · "Seu videogame merece uma segunda chance."

**Não encontrado no site (não verificado):** venda de consoles/jogos/PCs, informática geral (apesar do nome "informática" no Instagram), preços, prazos, garantia, formas de pagamento, tempo de mercado, nº de clientes atendidos. **Não prometer nada disso no vídeo.**

## Tom

Direto, informal-confiante, vocabulário gamer ("de volta no jogo", "segunda chance"), sem jargão técnico. Promessas moderadas (diagnóstico antes de reparo, transparência). Sem números/estatísticas no site.

## Marca

### Paleta do site (`css/styles.css`, variáveis CSS) [S1]

| Token | Hex | Uso no site |
|---|---|---|
| `--background` | `#080808` | fundo |
| `--card` | `#141414` | cards |
| `--muted` | `#1d1d1f` | superfícies |
| `--primary` / `--destructive` | `#e50914` | vermelho (CTAs, destaques) |
| `--secondary` / `--accent` / `--ring` | `#1565ff` | azul |
| `--foreground` | `#ffffff` | texto |
| `--muted-foreground` | `#a5a5aa` | texto secundário |

Fonte do site: `Arial, "Helvetica Neue", sans-serif` (sem webfont própria).

### Logo

- URL pública: https://www.wjrinformaticagames.com.br/assets/logo.png (PNG 1254×1254, com transparência). Texto do logo: "WJR INFOGAMES — ASSISTÊNCIA TÉCNICA ESPECIALIZADA", controle com um "W".
- Cores **aproximadas** do logo (média de pixels amostrados — confirmar com o arquivo original): creme `#f5eece`, ciano `#02cee1`, laranja `#fa5007`, cáqui/bege do fundo `#9e926c`.
- ⚠️ A paleta do logo (creme/ciano/laranja) é diferente da paleta do site (vermelho/azul). Perguntar ao cliente qual é a identidade "oficial" para vídeo.

### Imagens do site

`assets/hero-consoles.png`, `assets/repair-workbench.png`, `assets/controller-components.png`, `assets/images/consoles/*.png`. Aparentam ser **imagens ilustrativas/renderizadas** (não fotos identificáveis da loja) — não foi possível confirmar a origem nem o direito de uso. Para o vídeo final, pedir fotos/vídeos reais da loja e da bancada.

## Assets que precisam vir do cliente

Lista completa e checklist de pedido: [`../../docs/checklist-cliente.md`](../../docs/checklist-cliente.md). Resumo:

1. Logo em alta (SVG ou PNG ≥ 2000 px, fundo transparente) + versão horizontal, se houver.
2. Fotos reais: fachada, balcão, bancada, técnico trabalhando, antes/depois de reparos (vertical 9:16 de preferência).
3. Vídeos curtos verticais (5–15 s) da loja/bancada, gravados no celular.
4. Ofertas e preços que podem ser divulgados (se houver) + validade.
5. Confirmar WhatsApp, endereço, horário, se há garantia/prazo (só divulgar se confirmarem por escrito).
6. Autorização por escrito para usar marca, imagens e pessoas que aparecem (e trilha, se o cliente mandar música).
