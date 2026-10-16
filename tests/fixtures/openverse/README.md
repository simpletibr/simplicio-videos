# Fixtures do Openverse

Respostas reais e sanitizadas da API do Openverse, usadas só pelos testes de `tests/test_openverse.py` (os testes nunca chamam a rede).

| Arquivo | O que é |
|---|---|
| `search_images.json` | `GET https://api.openverse.org/v1/images/?q=sunrise over the sea&license=cc0,pdm,by&license_type=commercial,modification&page_size=3`, anônimo, 2026-10-16 |
| `search_audio.json` | `GET https://api.openverse.org/v1/audio/?q=rain&license=cc0,pdm,by&license_type=commercial,modification&page_size=3`, anônimo, 2026-10-16 |
| `observed_headers.json` | cabeçalhos `x-ratelimit-*` das duas respostas e da miniatura, na mesma data |

Sanitização: a lista de `tags` de cada resultado foi cortada nas 8 primeiras em ASCII (a resposta real traz dezenas, algumas com texto quebrado). Nenhum cabeçalho de credencial existia (as chamadas foram anônimas). Nenhum arquivo de mídia está versionado: a miniatura baixada na fumaça ficou fora do repositório.

Os metadados são de obras sob Creative Commons (CC BY 2.0 no Flickr e CC BY 4.0 no Freesound) e mantêm autor e licença como o Openverse devolveu. A licença vem das fontes: confira na origem (`foreign_landing_url`); isto não é parecer jurídico.
