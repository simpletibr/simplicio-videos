# simplicio-videos como plugin do simplicio-runtime (proposta)

> Status: **proposta**. Nada aqui está implementado no runtime. Levantamento read-only feito em 30/09/2026 no binário instalado (`simplicio 3.8.47`) e no repo privado `simpletibr/simplicio-runtime` (branch `main`).

## 1. O que já existe no runtime (convenção real, não inventada)

| Evidência | O que diz |
|---|---|
| `docs/ADR-2026-09-26-CORE-PLUGINS-MANIFEST.md` (Accepted, owner @wesleysimplicio) | Core = um binário atômico; features opcionais viram **binários de plugin `simplicio-<name>`** gerenciados pelo store `simplicio-modules`. Protocolo **`simplicio.plugin/v1`**: JSON request/response via stdio (repo, args, handle de contexto/mapa, budget, sandbox, parent receipt id); o plugin devolve result + receipt; o core verifica, contra-assina e grava no ledger. CLI `simplicio <cmd>` resolve built-in → plugin; MCP `tools/list` gerado dos manifests. Plugin novo aparece **sem release do core**. Assinatura exigida para plugins não locais; sandbox aplica as `capabilities` declaradas. |
| `crates/*/plugin.json` (ex.: `simplicio-image-gen`, `simplicio-voice`, `simplicio-vision`) e `crates/simplicio-plugin-motion/manifest/plugin.json` | Formato do manifest: `schema: "simplicio.plugin/v1"`, `name`, `version`, `description`, `binary`, `protocol`, `commands[] { verb, description, mcp_tool, args_schema (JSON Schema), examples }`, `capabilities` (ex.: `repo.write`, `external:chromium`, `external:ffmpeg`). |
| `crates/simplicio-plugin-motion` (#6620) | **Já existe um plugin de motion graphics**: `simplicio.storyboard/v1` (IR) → compile determinístico HTML/timeline → render opcional (Chromium headless → frames → ffmpeg, frames em cache por hash) → receipt `simplicio.motion-receipt/v1`. Ops: `motion schema`, `motion build --ir storyboard.json --out out/`. Presets `landscape`/`vertical`/`square`; 9 primitivas fechadas (`title-card`, `bullet-reveal`, `code-walkthrough`, `architecture-diagram`, `screenshot-pan-zoom`, `stat-counter`, `quote`, `terminal-replay`, `logo-outro`). Também define `simplicio.motion-dossier/v1` (ingest de pasta/URL/tópico). |
| `simplicio-image-gen` manifest | Precedente: o plugin **não roda modelo**; só registra o prompt (hash) num receipt. Integração de provedor "out of scope". |
| `contracts/plugin-v1/INVENTORY.md` | Schemas congelados: `simplicio.plugin.capability-manifest/v1`, `task-intent/v1`, `route-decision/v1`, `effect-intent/v1`, `effect-lease/v1`, `tool-receipt/v1`, `completion-decision/v1`. |
| Binário instalado `simplicio 3.8.47` | Tem `simplicio plugin list|install|remove`. O plugin `motion` **não** está instalado nesta máquina (`simplicio motion schema` cai no roteador de tarefas). |

Conclusão: **existe convenção** → o `plugin.json` deste repo segue o formato `simplicio.plugin/v1` dos manifests acima. O que é **proposta nossa** (não existe no runtime): o verbo `videos`, suas ops, o schema `simplicio.video-spec/v1` (`schemas/video-spec.schema.json`) e o binário `simplicio-plugin-videos`.

## 2. Arquitetura proposta

```
simplicio (core)                          simplicio-plugin-videos (este repo, futuro binário)
  ├─ CLI: simplicio videos <op> ─────────►  handle_op(op, args) → envelope simplicio.plugin/v1
  ├─ MCP: plugin_videos ─────────────────►  mesmo handler (--simplicio-plugin-request)
  ├─ receipts/ledger ◄──────────────────── result + receipt (hash de spec, template, MP4)
  └─ sandbox (capabilities) ─────────────   repo.write, external:node, external:chromium, external:ffmpeg

Engines (escolhidas por video.json → "engine"):
  hyperframes        → npx hyperframes@<pin> check / render --variables-file / --batch
  simplicio-motion   → delega ao plugin `motion` existente: motion build --ir storyboard.json
```

### Comandos (proposta)

| Op | Faz | LLM? |
|---|---|---|
| `videos schema` | devolve `simplicio.video-spec/v1` | não |
| `videos new --client <slug> --template <id> --out <dir>` | copia um template aprovado + cria `video.json`, `spec.json`, slots placeholder | não |
| `videos handoff --spec video.json` | monta o **pacote para o Opus 5.5**: `PROMPT.md` + `AGENTS.md` + brief + regras de gate, e devolve o texto/arquivos para o host (Claude Code) executar | **o host roda o Opus 5.5**; o plugin não chama modelo (mesmo padrão do `image-gen`) |
| `videos check --spec video.json` | `hyperframes lint` + `check` + `snapshot` → receipt com findings e contact sheet | não |
| `videos render --spec video.json [--quality]` | render determinístico → MP4 + `ffprobe` → receipt (sha256 do spec, do template e do MP4) | não |
| `videos batch --spec video.json --rows rows.json` | N variações (`hyperframes render --batch`) → manifest | não |

### Formato de spec
- `video.json` (`simplicio.video-spec/v1`, proposta): id, cliente, brief + `sources` (pasta `coleta/`), engine, formato (w/h/fps/duração/canal), `entry` + `spec_file` (variáveis + cues de áudio + slots de clipe) → `build` determinístico → `variables_file` (HyperFrames), blocos `audio` (procedural, alvo LUFS, licença) e `clips` ou `storyboard_file` (motion), bloco `authoring` (modelo/prompt/effort) e `slots` de assets com status (`placeholder` → `draft-from-site` → `client-provided` → `approved`).
- `spec.json`: valores das variáveis da composição (é o formato nativo do `hyperframes --variables-file`, então funciona hoje sem plugin).
- Exemplo real: `clients/wjr-informatica-games/video-01/video.json`.

### Como o Opus 5.5 entra (hoje)
Decisão do Wesley: **geração só com Opus 5.5**. No desenho do runtime, o plugin não embute modelo; ele prepara o handoff e **verifica** o resultado:
1. `videos handoff` → host (Claude Code com Opus 5.5, ou Codex via simplicio-loop no fluxo habitual) edita o template seguindo `PROMPT.md`.
2. `videos check` é o gate (0 erros no `check`, contact sheet revisado).
3. `videos render` fecha com receipt. O custo de tokens pode ser registrado com `simplicio savings record --model claude-opus-5-5 ...`.

### Como o modo determinístico entra (depois)
- **Nível 1 (já funciona sem plugin):** template aprovado + `spec.json` → `hyperframes render --strict-variables`. Zero token por variação.
- **Nível 2:** `engine: "simplicio-motion"` → o plugin só traduz/encaminha para o `motion` existente (`storyboard.simplicio.json`). Mais barato e 100% dentro do runtime, porém com o catálogo fechado de primitivas (qualidade visual mais genérica).
- **Nível 3:** catálogo de templates versionados (`templates/<id>/` com `spec.schema.json` derivado de `data-composition-variables`) + formulário/MCP para preencher spec. O Opus 5.5 volta a ser usado só para **criar template novo**.

## 3. Estrutura do repo para caber nisso

```
simplicio-videos/
├── plugin.json                 # manifest simplicio.plugin/v1 (STUB, sem binário ainda)
├── schemas/video-spec.schema.json   # proposta simplicio.video-spec/v1
├── clients/<cliente>/
│   ├── coleta/                 # brief.md (fatos com fonte = entrada do handoff), fontes.md, site/, colors.json, pendencias.md
│   └── video-NN/
│       ├── video.json          # spec do plugin (proposta)
│       ├── spec.json           # variables (HyperFrames) + audio (cues) + clips (slots de vídeo)
│       ├── scripts/build.mjs   # passo determinístico: variáveis, síntese/mix de áudio, clipes
│       ├── scripts/master.sh   # loudness final no MP4
│       ├── storyboard.simplicio.json  # fallback p/ plugin motion (não validado no binário)
│       ├── index.html          # template HyperFrames
│       ├── PROMPT.md / AGENTS.md / CLAUDE.md  # handoff p/ Opus 5.5 (ou Codex)
│       └── package.json        # scripts lint/check/snapshot/render
└── docs/
```

Próximo passo sugerido (quando fizer sentido): mover o template genérico para `templates/hyperframes-reels-9x16/`, escrever o binário `simplicio-plugin-videos` (Rust, espelhando `simplicio-plugin-motion/src/{lib,main}.rs`: `handle_op`, `ok_envelope`/`err_envelope`, argv direto + `--simplicio-plugin-request`) e abrir issue no simplicio-runtime para registrar no catálogo.
