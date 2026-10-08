# Glossário

Termos do motor (`simplicio-video`) e da fábrica, com uma definição curta cada. Os nomes técnicos ficam como estão no código.

## Motor de vídeo

- **Contrato** — arquivo YAML (`simplicio.video-contract/v1`) que descreve um vídeo: cenas, blocos, falas, voz, trilha e tempos. É a entrada do CLI e é validado por [`contract.schema.json`](../src/simplicio_video/data/schema/contract.schema.json). O agente escreve o contrato; o CLI valida e executa.
- **Render** — a etapa que transforma o contrato em MP4: compila a composição, roda o HyperFrames, aplica o master de áudio (−14 LUFS) e grava o `render.manifest.json`. É determinístico: sem LLM no caminho e sem rede.
- **Marca** — a identidade do cliente (nome, cores, logo, fontes e fatos). Vem só da coleta em `clients/<slug>/coleta/`. O motor não inventa marca e não recria logo.
- **Motion** — a biblioteca de padrões de animação em `motion/patterns/<id>/` (`block.html` e `pattern.json`), que as composições montam. Ver [motion](../src/simplicio_video/data/motion/README.md).
- **Template** — o modelo de um setor (`templates/<setor>/template.json`): cenas, padrões, campos do intake, voz e música. Ver [templates](../src/simplicio_video/data/templates/README.md).
- **Voz** — a narração TTS. Um provider (`gemini`, `file`, `local`, ...) gera as falas; o passo `voice` corta silêncio, trata o áudio e grava o `timing.lock.json` com as durações reais. A fala nunca é acelerada.
- **Manifesto** — o `render.manifest.json` de cada render: hashes do contrato e das entradas, ferramentas usadas, saída e loudness. Serve para conferir o que foi renderizado.
- **Ferramenta** — programa externo opcional, com versão fixada e instalado fora do repo (por exemplo `video-use`). O render não depende dele. Ver [tools](../tools/README.md).
- **ADR** — *Architecture Decision Record*: registro numerado de uma decisão de arquitetura, com contexto e consequências. Os existentes estão em [`decisoes/`](decisoes/ADR-0001-visao-plugin.md).

## Fábrica (spec)

Termos da fábrica de conteúdo, definidos no [spec em `docs/factory/`](factory/README.md). O spec ainda não está implementado no repo.

- **Stage** — uma etapa do loop da fábrica (`brand`, `ideas`, `make`, `review`, `publish`, `metrics`). No código, é a interface de um plugin. Uma etapa sem plugin é reportada como `stage.skipped`.
- **Station** — o lugar do painel onde a etapa aparece (por exemplo, *Studio* para `make`). Só apresentação.
- **Character** — o personagem que representa a etapa no painel (por exemplo, *Director* para `make`). Só apresentação.
- **Plugin** — extensão instalada no host que acrescenta uma capacidade do tipo `stage`, `publisher`, `metrics-source`, `theme` e outros. Ver [plugins](factory/plugins.md).
- **Runtime plugin** — o `plugin.json` da raiz do repo, que apresenta o simplicio-videos ao Simplicio Runtime (`simplicio.plugin/v1`). Não é um plugin da fábrica, apesar do nome parecido.
