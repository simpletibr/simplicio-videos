# Fixtures da busca (TinyFish)

Saídas reais do CLI `tinyfish` 0.50.1, usadas só pelos testes de `tests/test_busca.py` (os testes nunca chamam o binário real nem a rede: um `tinyfish` falso, escrito pelo próprio teste, devolve estes JSONs).

| Arquivo | O que é |
|---|---|
| `consulta_real.json` | `tinyfish search query "dia das criancas campanha marketing clinica odontologica" --language pt --exclude-domains pinterest.com`, 2026-10-16. Formato `{query, results[{position, site_name, snippet, title, url, date?}], total_results, page}`; 10 resultados, `date` é texto livre em português (`5 de out. de 2017`) e só alguns resultados têm. |
| `pagina_real.json` | `tinyfish fetch content get https://example.com --format markdown`, 2026-10-16. Formato `{results[{url, final_url, title, description, language, author, published_date, latency_ms, format, text}], errors[]}`. |

Sanitização: nenhuma. As duas chamadas eram públicas e a saída não traz credencial, cabeçalho nem dado do dono da conta; só foi reformatada (indentação). Os trechos e títulos são texto de terceiros, mantidos como o buscador devolveu.

Foram as únicas duas chamadas reais feitas para construir o módulo (uma busca e uma leitura de página). O saldo da carteira ficou igual antes e depois (`tinyfish wallet status`), e a tabela de tarifas lida na mesma data traz Search 0 USD/query e Fetch 0 USD/url.
