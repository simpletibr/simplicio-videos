# AGENTS.md — linhas do mapa de pastas arquivadas

Quatro linhas da tabela "Mapa (todas as pastas)" do [`AGENTS.md`](../AGENTS.md), de pastas que saíram da raiz para `arquivo/` (`modules/h3-swap-service/`, `ugc/`, `scripts/kit_gpu/` e `prospects/`; onde cada uma está agora, em [`README.md`](README.md) desta pasta). Foram copiadas para cá **como estavam**, byte a byte (o bloco começa no comentário `<!-- origem: mapa -->`): nada foi reescrito nem apagado. Os links relativos dentro delas apontam para onde as coisas ficavam antes.

As seções de missão e venda ativa, de UGC e de entregas no Drive **não** vieram para cá: carregam regra ativa (o guia de operação do dono, as travas do UGC e da venda ativa, a convenção de pastas do Drive que `publish.py` e `--drive-nome` ainda usam) e ficam no `AGENTS.md`.

`scripts/check_docs.py` não confere nada em `arquivo/`.

## Linhas do mapa de pastas

<!-- origem: mapa -->
| Pasta | O quê | Entrada principal |
|---|---|---|
| `modules/h3-swap-service/` | Módulo opcional e isolado: troca de personagem em vídeo (MiniMax H3 + LoRA) em GPU alugada (Vast/Salad) com fila na Cloudflare. NÃO é importado pelo motor nem entra no wheel/sdist; `api/` (créditos/cobrança) é deploy próprio, fora do pacote (ver o conflito com o boundary no README do módulo). Tudo UNVERIFIED até o benchmark numa GPU real | [README](modules/h3-swap-service/README.md) |
| `ugc/` | **Trilha UGC (gerativa, fora do `render`)**: `pack.json` (10 personagens, `simplicio.ugc-pack/v1`) + `pack.schema.json`, `prompts/` (5 prompts: elenco, imagem, fullbody, roteiros, Seedance). O CLI `ugc list\|prompt` só monta/valida o prompt; imagem e vídeo são gerados à mão. [ADR-0004](docs/decisoes/ADR-0004-ugc-generativo.md) | [ugc/README.md](ugc/README.md) |
| `scripts/kit_gpu/` | **Kit de medição da troca de personagem em GPU de 6 GB** (material de operação e de teste, fora do pacote `simplicio_video`): seis scripts Python autônomos (`checar_maquina`, `preparar_entradas`, `medir_gpu`, `compor_final`, `conferir_troca`, `receita_test_hash`); `numpy`/`opencv`/`torch` são só deles, fora do `pyproject.toml`. Texto, prompt e resultados em `docs/how-to/troca-personagem-gpu/` | [LEIA-ME](docs/how-to/troca-personagem-gpu/LEIA-ME.md) |
| `prospects/` | **Venda ativa** (fora do git, exceto `exemplo-dia-criancas.csv`): `<lote>/<slug>/{coleta.json, contract.yaml, preview.mp4, result.json}` + `<lote>/lote.csv` | [docs/venda-ativa.md](docs/venda-ativa.md) |
