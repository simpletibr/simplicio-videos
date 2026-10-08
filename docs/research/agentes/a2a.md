# Pesquisa e Análise: A2A (Agent-to-Agent)

Relatório de análise do protocolo e biblioteca A2A para a issue #83 (épico #81, milestone M2).

## Dados da Medição e Inspeção

- **Pacote:** `a2a-sdk`
- **Versão testada:** `1.2.2`
- **Data da medição:** 2026-10-08
- **Ambiente:** Linux x86_64, CPython 3.12.14, `uv` 0.5+
- **Tempo de resolução e instalação:** ~1.2 s
- **Tamanho total em disco do ambiente:** ~28 MB
- **Dependências de transporte principais:** `json-rpc==1.15.0`, `httpx==0.28.1`, `httpcore==1.0.9`, `requests==2.34.2`, `protobuf==7.36.2`

## Critério de Morte Verificado

> **Critério de morte:** *se o transporte in-process exigir HTTP → A2A fica só na borda externa.*

### Análise de Arquitetura e Transporte

1. **Natureza do A2A SDK:** O Agent-to-Agent (A2A) SDK padroniza a troca de mensagens, tarefas e delegação entre agentes autônomos distribuídos. Toda a pilha do SDK é desenhada em torno do envio de mensagens serializadas em JSON-RPC via chamadas HTTP/REST e Server-Sent Events (SSE).
2. **Ausência de Transporte In-Process Nativo:** O SDK não disponibiliza camada de transporte direta em memória (zero-copy / in-memory bus / Python Protocol) para comunicação entre estágios locais da esteira da fábrica. Qualquer comunicação pelo SDK requer a instanciação de cliente/servidor HTTP (ou conexões de socket TCP).
3. **Restrições Arquiteturais do Kernel:** No motor `simplicio_factory` / `simplicio-video`:
   - Todas as chamadas entre estágios do pipeline ocorrem de forma síncrona/hermética dentro do mesmo processo Python via `Stage.run(item, store)`.
   - As conexões de rede em estágios determinísticos são estritamente proibidas por padrão (garantido por `pytest-socket` e `SIMPLICIO_OFFLINE=1`).
   - Forçar transporte HTTP para passar itens entre `draft`, `media`, `composer` e `render` introduziria latência, fragilidade de portas locais, necessidade de loopbacks e riscos de concorrência.

## Veredito: MORTA para Transporte In-Process / MANTIDA na Borda Externa

- **Resultado In-Process:** **MORTA**. O A2A não será utilizado como mecanismo de comunicação entre estágios ou componentes internos da fábrica.
- **Resultado na Fronteira Externa:** **APROVADA**. O A2A tem papel legítimo como interface de borda externa (por exemplo, expondo o servidor MCP ou um endpoint A2A para permitir que orquestradores externos como Hermes Agent ou OpenClaw interajam com a fábrica de fora).
