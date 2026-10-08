# Roteiro de Medição do Spike de Agentes

Roteiro de teste e medição empírica estabelecido para a issue #83 ("Spike de agentes: LangGraph, CrewAI e A2A"), executado em conformidade com as diretrizes do [design review](../../factory/design-review.md).

## Objetivo e Metodologia

Medir de forma isolada e reproduzível os custos de instalação (tempo e espaço em disco), compatibilidade de ambiente (Python 3.12, Linux x86_64) e aderência arquitetural dos três frameworks candidatos a plugins futuros.

### Ambiente de Teste
- **Data da medição:** 2026-10-08
- **Sistema Operacional:** Linux x86_64 (Debian GNU/Linux trixie/sid, Kernel Linux 6.6)
- **Interpretador Python:** CPython 3.12.14
- **Gerenciador de pacotes:** `uv` 0.5+

### Critérios de Morte Avaliados

1. **CrewAI (M2):**
   - *Critério:* Instalação com mais de 2 GB ou mais de 5 minutos, ou que bloqueie Python 3.12 em macOS arm64 ou Linux.
   - *Ação se falhar:* Somente um executor simples de loop de ferramentas (`SimpleToolLoop`) atrás do mesmo Protocol `AgentRunner`.

2. **A2A SDK (M2):**
   - *Critério:* Se o transporte in-process exigir HTTP.
   - *Ação se falhar:* A2A permanece estritamente na fronteira externa (borda / interoperabilidade de rede).

3. **LangGraph (M2):**
   - *Critério:* Se exigir mudar o contrato do item (`Item`, `contract.schema.json`) ou o kernel (`simplicio_factory`).
   - *Ação se falhar:* Fica fora do projeto.

---

## Comandos de Medição

Para garantir medições isoladas sem contaminar o `.venv` do projeto principal:

### 1. LangGraph

```bash
TMP_DIR=$(mktemp -d /tmp/spike-langgraph-XXXXXX)
uv venv "$TMP_DIR" --python python3.12
/usr/bin/time -v uv pip install langgraph --python "$TMP_DIR/bin/python"
du -sm "$TMP_DIR"
"$TMP_DIR/bin/python" -c "import langgraph; print(langgraph.__version__)"
rm -rf "$TMP_DIR"
```

O que medir:
- Tempo de resolução e download/instalação.
- Tamanho total em megabytes da pasta virtualenv criada.
- Possibilidade de modelar um `LoopRunner` que itera sobre `Item` e invoca `Stage.run(item, store)` sem alterar o schema do `Item`.

### 2. CrewAI

```bash
TMP_DIR=$(mktemp -d /tmp/spike-crewai-XXXXXX)
uv venv "$TMP_DIR" --python python3.12
/usr/bin/time -v uv pip install crewai --python "$TMP_DIR/bin/python"
du -sm "$TMP_DIR"
"$TMP_DIR/bin/python" -c "import crewai; print(crewai.__version__)"
rm -rf "$TMP_DIR"
```

O que medir:
- Tempo total de instalação (limite: < 300 segundos / 5 minutos).
- Tamanho em disco do virtualenv instalado (limite: < 2048 MB / 2 GB).
- Sucesso de instalação em CPython 3.12 sem bloqueios de build ou dependências conflitantes.

### 3. A2A SDK

```bash
TMP_DIR=$(mktemp -d /tmp/spike-a2a-XXXXXX)
uv venv "$TMP_DIR" --python python3.12
/usr/bin/time -v uv pip install a2a-sdk --python "$TMP_DIR/bin/python"
du -sm "$TMP_DIR"
"$TMP_DIR/bin/python" -c "import a2a; print(getattr(a2a, '__version__', 'ok'))"
rm -rf "$TMP_DIR"
```

O que medir:
- Dependências de transporte do pacote (`httpx`, `httpcore`, `json-rpc`, `requests`).
- Se a interface do SDK impõe servidor/cliente HTTP (JSON-RPC sobre HTTP/SSE) para troca de mensagens entre agentes, sem transporte direto em memória para estágios in-process.

---

## Próximos Passos (Resultados e Decisão)

1. Registrar relatórios individuais detalhados em:
   - `docs/research/agentes/langgraph.md`
   - `docs/research/agentes/crewai.md`
   - `docs/research/agentes/a2a.md`
2. Consolidar os vereditos no [ADR-0019](../../decisoes/ADR-0019-agentes.md).
3. Elaborar as especificações de issues de implementação para os caminhos aprovados.
