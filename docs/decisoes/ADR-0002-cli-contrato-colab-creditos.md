# ADR-0002 — CLI `simplicio-video`, contrato YAML, backend Colab e créditos

- **Status:** aceito (CLI, contrato e Colab-bundle implementados); créditos = **só design e interface**, sem cobrança real
- **Data:** 30/09/2026 (BRT) · **Pedido:** Wesley, 15:57 e 15:59
- **Relaciona:** [ADR-0001](ADR-0001-visao-plugin.md) (plugin do Simplicio Runtime, esteira determinística) · automação do Colab, Kaggle, voz por API, Drive e MCP: [ADR-0003](ADR-0003-fluxo-100-script.md) · custo real por vídeo (base das tarifas de crédito): [docs/custos.md](../custos.md)

## Contexto

A esteira do ADR-0001 rodava por projetos npm copiados por vídeo (`spec.json` + `index.html` + `scripts/`). Isso duplicava código em cada cliente e deixava o agente mexendo em HTML. O Simplicio Runtime vai tratar toda ferramenta externa como plugin com um entrypoint único.

## Decisão

1. **Contrato YAML** (`schema/contract.schema.json`, `simplicio.video-contract/v1`) é a única entrada de um vídeo: cliente, campanha, formato, template, marca, cenas (motion + params, textos, fala com `max_s`, SFX com tempo relativo à cena), voz, trilha, saída e destino no Drive. **O LLM raciocina e escreve o contrato; o CLI executa.**
2. **CLI Python** `simplicio-video` (`pyproject.toml`, `src/simplicio_video/`): `init`, `validate`, `voice`, `render`, `list`. O motor de áudio (`engine/build.mjs`) e o master (`engine/master.sh`) são os mesmos dos vídeos já entregues; a composição de cada setor fica no template (`templates/<id>/composition/index.template.html` com placeholders `{{vars:bloco}}`, `{{t:cena+off}}`, `{{cuts}}`...).
3. **Determinismo verificável:** `timing.lock.json` (durações reais da voz) + `render.manifest.json` (hash do contrato, de cada arquivo compilado, versões das ferramentas, hash dos frames decodificados e do PCM do áudio). Prova: a WJR portada renderiza com o MP4 **byte a byte igual** ao original (600/600 frames, mesmo sha256); a Lothus idem em relação ao projeto npm anterior.
4. **Backend Colab:** `render --backend colab` gera um bundle zip reprodutível (composição compilada + `render_bundle.sh`) e o notebook `colab/render.ipynb` instala dependências, renderiza (NVENC via `hyperframes render --gpu` quando houver) e imprime tempos por etapa.

## Automação do Colab (próximo passo)

| Opção | Como | Custo | Situação |
|---|---|---|---|
| Colab gratuito/Pro pelo navegador | usuário abre o notebook e envia o bundle | grátis / assinatura | **pronto** (teste de velocidade do Wesley) |
| Colab Enterprise / Vertex AI Workbench executions | API `notebookExecutionJobs` com o bundle num bucket GCS | pago por GPU-hora | documentado; exige projeto GCP com faturamento (não criado) |
| Runner GPU próprio (VM spot / servidor do runtime) | `bash render_bundle.sh` via fila | pago por GPU-hora | recomendado para clientes pagantes: controle de fila e medição |

Nenhuma conta criada, nenhum gasto.

## Créditos para clientes pagantes (design)

### O que medir por render (`render.manifest.json → usage`, a implementar)

| Métrica | Fonte | Unidade |
|---|---|---|
| `cpu_s` | soma de user+sys dos processos (build, Chrome, ffmpeg) | CPU-segundo |
| `gpu_s` | tempo de parede do `render_bundle.sh` × nº de GPUs, com o modelo (`nvidia-smi`) | GPU-segundo por modelo |
| `frames` | `media_hashes().frames` | frame |
| `tts_chars` | soma de `len(say)` das falas **não** cacheadas, por provider | caractere |
| `storage_mb` | bundle + MP4 | MB |
| `cache_hit` | voz/render com o mesmo `inputs_sha256` já existente | booleano (hit = não cobra render) |

Custo em créditos = `Σ métrica × tarifa(métrica, backend, modelo)`, tarifa em tabela versionada do runtime (ex.: `credits/tarifas-v1.json`), sempre arredondado para cima por render. O mesmo `inputs_sha256` renderizado de novo devolve o MP4 do cache sem débito.

### Hook de débito (reserve → commit/release)

```python
class CreditLedger(Protocol):            # implementado pelo Simplicio Runtime, não pelo plugin
    def estimate(self, job: "RenderJob") -> "Estimate": ...                  # antes: frames, backend, tts -> créditos
    def reserve(self, account_id: str, estimate: "Estimate", idem_key: str) -> "Reservation": ...
    def commit(self, reservation_id: str, usage: "Usage") -> "Receipt": ...   # depois: cobra o real (<= reservado + margem)
    def release(self, reservation_id: str, reason: str) -> None: ...          # falha/cancelamento: devolve tudo

@dataclass
class RenderJob:  contract_sha256: str; inputs_sha256: str; backend: str; frames: int; tts_chars: dict[str, int]
@dataclass
class Usage:      cpu_s: float; gpu_s: float; gpu_model: str | None; frames: int; tts_chars: dict[str, int]; storage_mb: float; cache_hit: bool
```

Fluxo no CLI (flag futura `--account <id>`; sem ela nada é cobrado — é o caso de hoje):
1. `validate` → `estimate()` mostra o custo previsto.
2. `render` chama `reserve()` com `idem_key = inputs_sha256 + backend` (retry não cobra duas vezes).
3. Sucesso → `commit(usage)`; erro/timeout → `release()`.
4. `usage` e `receipt_id` entram no `render.manifest.json`.

Interface do plugin (`plugin.json`, `simplicio.plugin/v1`): o runtime passa `account_id` e recebe `usage` no resultado de `op=render`; o plugin **nunca** fala com meios de pagamento.

### Fora do escopo agora
Cobrança real, tabela de preços, contas de GPU, créditos de TTS pagos (ElevenLabs/xAI continuam stubs).

## Consequências

- Vídeo novo = escrever um contrato; nada de copiar projeto npm. Os projetos npm da WJR continuam como referência histórica.
- Template "pronto" agora exige `composicao` renderizável; os skeletons continuam só estrutura.
- O render local é a referência de hash; renders em GPU/NVENC são equivalentes visuais, não byte a byte.
