# Schemas JSON do pacote

> Gerado por `scripts/gen_reference.py` a partir de `src/simplicio_video/data/**/*.schema.json`. Não edite à mão: rode `make regen`.

| Arquivo | `$id` ou título | Descrição |
|---|---|---|
| src/simplicio_video/data/motion/pattern.schema.json | https://simplicio.dev/schemas/simplicio.motion-pattern/v1 | One entry of the motion pattern library (motion/patterns/<id>/pattern.json). |
| src/simplicio_video/data/openverse/api.schema.json | simplicio.openverse-api/v1 | Fatos da API do Openverse usados pelo comando openverse, cada um com fonte, data de leitura e confiança. |
| src/simplicio_video/data/openverse/library.schema.json | simplicio.openverse-library/v1 | Índice da biblioteca local do Openverse (index.json): itens baixados, revisões por par (ativo, pedido) e exportações. |
| src/simplicio_video/data/openverse/licenses.schema.json | simplicio.openverse-licenses/v1 | Licenças Creative Commons que o comando openverse conhece: o que permitem e qual aviso dar. |
| src/simplicio_video/data/schema/contract.schema.json | https://github.com/simpletibr/simplicio-videos/schema/contract.schema.json | Video contract: everything the simplicio-video CLI needs to render one video deterministically. The LLM reasons and writes this file; the CLI executes it. Scene-relative times (fala.inicio_s, sfx.t) are seconds from the scene start. |
| src/simplicio_video/data/schemas/cli/preview-manifest.schema.json | simplicio.preview-manifest/v1 | Manifesto da prévia (render --preview, ao lado do contrato). Não substitui o render.manifest.json da entrega. Só o formato: $schema é opcional. |
| src/simplicio_video/data/schemas/cli/render-manifest.schema.json | simplicio.render-manifest/v1 | Manifesto da entrega (render.manifest.json, ao lado do contrato). O mesmo formato para todos os backends. Só o formato: o conteúdo é o que render.py grava. $schema é opcional (a chave schema identifica a versão). |
| src/simplicio_video/data/schemas/cli/render-result.schema.json | simplicio.render-result/v1 | Saída de `simplicio-video render CONTRATO --json` (stdout). Com ok=true: caminhos do MP4 (ou bundle) e do manifesto gravado. Com ok=false: error.code (um dos códigos de $defs/erro). |
| src/simplicio_video/data/schemas/cli/run-result.schema.json | simplicio.run-result/v1 | Saída de `simplicio-video run CONTRATO --json` (stdout): voice -> validate --need-lock -> render, num comando só. Com ok=true, traz voice e render (os mesmos campos do resumo de pipeline.run_all). Com ok=false, traz error.code (um dos códigos de $defs/erro). |
| src/simplicio_video/data/schemas/cli/validate-result.schema.json | simplicio.validate-result/v1 | Saída de `simplicio-video validate CONTRATO --json` (stdout). ok=true: contrato válido, sem erros. ok=false: traz error.code (um dos códigos de $defs/erro) e, se a validação rodou, a lista de errors. |
| src/simplicio_video/data/schemas/video-spec.schema.json | simplicio.video-spec/v1 | — |
| src/simplicio_video/data/social/limits.schema.json | simplicio.social-limits/v1 | — |
| src/simplicio_video/data/social/providers.schema.json | simplicio.social-providers/v1 | — |
| src/simplicio_video/data/templates/template.schema.json | https://simplicio.dev/schemas/simplicio.video-template/v1 | A sector template: scene structure + motion patterns + voice/music defaults that turn an intake into a spec without an LLM. |
