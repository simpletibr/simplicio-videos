# Changelog

O que mudou em cada issue. `simplicio-video update --check` mostra o diff deste arquivo antes de atualizar.

## Unreleased

### Formatos de anúncio
- `simplicio-video formats list|show|prompt` e o tool MCP `video.formats`. Biblioteca dos 50 formatos da pasta "Swipe File - 50 Formatos" do Drive (`src/simplicio_video/data/formats/formats.json`): cada um com a descrição, a estrutura, os limites, o objetivo e o link da pasta com o nome do arquivo de exemplo.
- `formats prompt <id> --copia <arquivo|->` monta o pedido para adaptar uma copy ao formato (instruções em `data/formats/instrucoes.md` + copy + formato). O CLI não chama modelo: quem adapta é o LLM.
- As descrições são estruturais, escritas a partir do nome do formato. Ficam com `verificado: false` até conferir o arquivo no Drive.
### Ângulos de anúncio
- `simplicio-video list angles [--grupo problema|prova|desejo|decisao|estrategia] [--json]` e o tool MCP `video.list` com `what=angles`. Catálogo de 50 ângulos em `src/simplicio_video/data/angles/angles.json`: 10 por grupo, cada um com gatilho, quando usar, gancho de exemplo (só com marcadores de fato, nunca número ou promessa) e cuidado.
### Trilha MoneyPrinterTurbo
- `simplicio-video moneyprinter clone|setup|serve|where|status` e a tool MCP `video.moneyprinter` (só `where` e `clone` na pasta padrão; `setup`, `serve`, `status` e `clone <pasta>` ficam no terminal). Checkout fixado do [MoneyPrinterTurbo](https://github.com/harry0703/MoneyPrinterTurbo) (MIT) em `tools.py`. Trilha externa de apoio, como toonflow e opencut: não substitui o `contract.yaml -> MP4`.
- `setup` cria um venv isolado em `MONEYPRINTER_DATA_DIR` (padrão `~/.simplicio-video/moneyprinter-data`), instala o `requirements.txt` do upstream (Python 3.11+), copia `config.example.toml` para `config.toml` sem preencher chave nenhuma e nunca sobrescreve um `config.toml` existente. `status` mostra só se o arquivo existe e quais chaves estão preenchidas.
- `serve` sobe a WebUI (porta 8501) e, com `--api`, a API (8080) em grupos de processos próprios. O upstream escuta em `0.0.0.0` por padrão na API, então o host é forçado para `127.0.0.1` por argumento (uvicorn em `app.asgi:app`, sem depender do `listen_host` do config); `--lan` é o único jeito de escutar em todas as interfaces.
- Revisão do PR #104: o `serve` ignora sinais repetidos durante a parada e repete a parada de cada servidor, trata SIGHUP (terminal fechado) como Ctrl+C e faz a varredura SIGKILL também do servidor que já saiu, para nenhum dos dois ficar órfão. Quando um servidor cai sozinho, diz qual foi em stderr e devolve código positivo.
- `serve --api` com `app.api_key` vazio avisa que a API fica sem login e recusa `CORS_ALLOWED_ORIGINS` com `*` nesse caso. Conferido no upstream (pino `4b7b965`): o CORS vem fechado por padrão, então outro site não lê a API; o risco que sobra é qualquer programa que alcance a porta usar as suas chaves.
- `status` lê o `config.toml` com `tomllib` (chaves pontuadas, entre aspas, tabelas inline, maiúsculas, `access_key_id`, `[[tabelas]]`), sem inventar nomes de dentro de um valor; o leitor por linha ficou de reserva para o Python 3.10 e TOML inválido. O `config.toml` criado pelo `setup` fica com modo 0600, o `setup` avisa quando o checkout não está no commit fixado, erros de arquivo e de processo viram `moneyprinter: ...` sem traceback, argumentos a mais em `clone`, `where` e `status` são recusados e o `setup` só exige Python 3.11 ao criar o venv.
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
