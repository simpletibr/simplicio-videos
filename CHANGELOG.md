# Changelog

O que mudou em cada issue. `simplicio-video update --check` mostra o diff deste arquivo antes de atualizar.

## Unreleased

### Troca de personagem (swap)
- `simplicio-video swap providers|estimate|run|status` e a tool MCP `video.swap` (só `providers` e `estimate`; gastar é só pelo terminal). Orquestração única em `src/simplicio_video/swap.py` e um adaptador por fornecedor em `src/simplicio_video/swap_providers/`: `gemini` (Interactions API, conferido na documentação), `fal`, `wavespeed`, `kie` e `alibaba` (**UNVERIFIED**: escritos da documentação pública, sem conferência na API real) e `fake` para testes.
- `--autorizo` é obrigatório; sem `--yes` só estima (dry-run, sem rede); `--max-usd` (padrão US$ 2) aborta antes de submeter; adaptador UNVERIFIED pede `--aceito-unverified`. A chave só entra pela variável de ambiente do provedor e nunca vai a argumento, log ou manifesto.
- Corta o vídeo em pedaços do tamanho que o provedor aceita, remonta o áudio original quando o provedor não o preserva, normaliza fps e duração e emenda. Grava `swap.manifest.json` com hashes, custo previsto e medido, latência por etapa, tentativas e o texto da autorização.
- Tabela de preços por adaptador com `source_url`, `read_on` (2026-10-15) e `confidence`, e câmbio de referência (R$ 5,0521 por US$, PTAX de 2026-10-15) em campo separado. `status` lista quais provedores têm a variável da chave definida (nunca o valor).

### Formatos de anúncio
- `simplicio-video formats list|show|prompt` e o tool MCP `video.formats`. Biblioteca dos 50 formatos da pasta "Swipe File - 50 Formatos" do Drive (`src/simplicio_video/data/formats/formats.json`): cada um com a descrição, a estrutura, os limites, o objetivo e o link da pasta com o nome do arquivo de exemplo.
- `formats prompt <id> --copia <arquivo|->` monta o pedido para adaptar uma copy ao formato (instruções em `data/formats/instrucoes.md` + copy + formato). O CLI não chama modelo: quem adapta é o LLM.
- As descrições são estruturais, escritas a partir do nome do formato. Ficam com `verificado: false` até conferir o arquivo no Drive.
### Ângulos de anúncio
- `simplicio-video list angles [--grupo problema|prova|desejo|decisao|estrategia] [--json]` e o tool MCP `video.list` com `what=angles`. Catálogo de 50 ângulos em `src/simplicio_video/data/angles/angles.json`: 10 por grupo, cada um com gatilho, quando usar, gancho de exemplo (só com marcadores de fato, nunca número ou promessa) e cuidado.
### Trilha Toonflow
- `simplicio-video toonflow clone|serve --lan|where` e a tool MCP `video.toonflow` (clone na pasta padrão e where; `serve` só no terminal). Checkout fixado do [Toonflow](https://github.com/HBAI-Ltd/Toonflow-app) (MIT) em `tools.py`; `serve` faz `bun install --frozen-lockfile`, `build:server` e `start:server`. O Toonflow escuta em `0.0.0.0:3000` sem login, então `serve` recusa sem `--lan`. Dados em `TOONFLOW_DATA_DIR` (padrão `~/.simplicio-video/toonflow-data`), fora do checkout.
- Conhecido, fora deste trecho: os wrappers MCP de `video.montage`, `video.opencut`, `video.clone` e `video.edit` falham sempre com `TypeError` (o `_capture` passa `log=` a funções que não o aceitam). Corrigir exige capturar a saída dos subprocessos, porque eles escrevem no canal stdio do MCP e alguns não terminam (`opencut dev`, `montage serve`). Fica para issue própria.

### #31 Gate local
- `make check` roda o gate offline: checagens de ownership (`scripts/check_ownership.py`) e de TDD (`scripts/check_tdd.py`), pouso serializado (`scripts/land.sh`) e hooks em `.githooks/`. Sem GitHub Actions ([ADR-0005](docs/decisoes/ADR-0005-gate-sem-ci.md)).

### #43 Pacote de operação
- `./install.sh`, `simplicio-video install`, `update`, `doctor` e `setup`, com `Dockerfile` e `compose.yaml` só para build local ([ADR-0017](docs/decisoes/ADR-0017-instalacao-atualizacao.md)).

### #44 Docs
- Estrutura em `docs/` por tipo de documento: tutoriais, how-to, referência gerada, decisões (ADRs), host, plugins e factory.
- `docs/reference/` é gerado a partir do `--help` e das schemas; `make docs` falha se ficar desatualizado.
- `scripts/check_docs.py`: links relativos, âncoras, front matter, órfãos, pendências deixadas em texto e mermaid, offline.
- `docs/glossary.md` com os termos do projeto.
- Tutorial "Primeiro vídeo" e índices de tutoriais, how-to, decisões, host e plugins.

### #46 Licenças
- `scripts/licenses.py` confere as licenças do ambiente contra a allowlist (MIT, Apache-2.0, BSD, ISC, PSF, MPL-2.0), aceita exceções justificadas e checa o isolamento de dependências AGPL ([docs/host/licenses.md](docs/host/licenses.md)). `web/` ainda não entra no scan.

### #72 Saída em JSON
- `validate`, `run` e `render` aceitam `--json` com objeto estável e erros com código (`CONTRATO_NAO_ENCONTRADO`, `CONTRATO_INVALIDO`, `RENDER_FALHOU`, `FERRAMENTA_AUSENTE`).

### #73 Versão e status
- `simplicio-video --version --json` e `simplicio-video status` (texto e `--json`), para o looping.

### #74 Dados dentro do pacote
- Schemas, templates e motion do motor ficam em `src/simplicio_video/data/`, dentro do pacote.

### #75 Sem Drive no motor
- O bloco `drive` saiu do contrato e do motor. Contrato com `drive` falha no `validate`; a entrega fica fora do motor.

### #76 Marca como entrada do contrato
- Marca d'água e crédito final são entradas do contrato (`marca.dagua`, `marca.credito`), usadas por `render --preview`.

### #77 Motor sem vendas
- O CLI do motor não expõe mais os subcomandos de venda (`prospect`, `venda`, `ugc`, `publish`). Os módulos continuam no repositório.
