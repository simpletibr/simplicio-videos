# Pesquisa e Medição: CrewAI

Relatório de medição do framework CrewAI para a issue #83 (épico #81, milestone M2).

## Dados da Medição

- **Pacote:** `crewai`
- **Versão testada:** `1.15.25`
- **Data da medição:** 2026-10-08
- **Ambiente:** Linux x86_64, CPython 3.12.14, `uv` 0.5+
- **Tempo de resolução e instalação:** 10.23 s (com cache / pip uv)
- **Tamanho total em disco do ambiente:** 753 MB
- **Total de pacotes transitivos:** 134 dependências diretas e indiretas (incluindo `chromadb`, `embedchain`, `pydantic`, `sqlite`, `bcrypt`, etc.)

## Critério de Morte Verificado

> **Critério de morte:** *instalação com mais de 2 GB ou mais de 5 minutos, ou que bloqueie Python 3.12 em macOS arm64 ou Linux → só um executor simples de loop de ferramentas atrás do mesmo Protocol.*

### Análise dos Limites

1. **Tamanho em disco:** 753 MB. Está abaixo do teto de 2 GB estabelecido no critério de morte.
2. **Tempo de instalação:** 10.23 s (bem abaixo do teto de 300 s / 5 minutos).
3. **Compatibilidade Python 3.12:** O pacote instala e roda normalmente no CPython 3.12.14 sem falhas de compilação ou incompatibilidade de wheels pré-compiladas em Linux x86_64.
4. **Impacto no Motor:**
   - Embora passe formalmente nos critérios numéricos de morte, 753 MB e 134 dependências adicionais representam uma sobrecarga inaceitável para a distribuição padrão do `simplicio-video` (cujo core possui ~30 MB de dependências diretas).
   - A inclusão direta de `crewai` tornaria o comando CLI lento para inicialização e quebraria o princípio de motor enxuto e determinístico.

### Modelo de Abstração via Protocol

Para proteger o motor, todo runtime de agente deve ficar estritamente atrás do Protocol `AgentRunner`:

```python
class AgentRunner(Protocol):
    def run_agent(self, role: str, goal: str, tools: list[dict], inputs: dict) -> dict: ...
```

## Veredito: PASS (Isolado como Plugin Opcional)

- **Resultado:** **PASS com ressalvas**. Não violou os limites absolutos de 2 GB ou 5 minutos.
- **Diretriz de Implementação:**
  1. O motor central **nunca** incluirá `crewai` em `pyproject.toml` dependencies.
  2. O motor implementará um executor nativo leve de loop de ferramentas (`SimpleToolLoop`), com zero dependências externas e zero tokens de LLM no caminho determinístico.
  3. O suporte ao CrewAI será fornecido exclusivamente via plugin externo opcional (`agents-crewai`) instalado como pacote separado ou extra de desenvolvimento.
