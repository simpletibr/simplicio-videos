# AGENTS.md — simplicio-videos

Regras, mapa e fluxos para qualquer agente (Claude Code, Codex, Grok) trabalhando neste repositório. Cada vídeo também tem o seu `AGENTS.md` com detalhes da composição.

## O que é

**simplicio-videos** é o plugin de vídeo do **Simplicio Runtime (Simplicio MCP)** ([ADR-0001](docs/decisoes/ADR-0001-visao-plugin.md)). Pedido de vídeo → **esteira determinística** ([docs/esteira.md](docs/esteira.md)):

1. **intake** (questionário; com site/Instagram extrai sozinho e pergunta só o que falta) → 2. **brief/spec** (fonte única da verdade) → 3. **template do setor** → 4. **composição** com a biblioteca de motion (HyperFrames) → 5. **voz TTS** (provider à escolha, cache) → 6. **video-use** (footage, opcional) → 7. **render determinístico** + QA.

LLM (Opus 5.5) **só** cria template/padrão novo; nunca está no caminho do render.

**Entrada oficial: o CLI `simplicio-video`** ([ADR-0002](docs/decisoes/ADR-0002-cli-contrato-colab-creditos.md)). O agente raciocina e escreve o **contrato YAML** (`schema/contract.schema.json`); o CLI valida, gera a voz e renderiza. Skill para qualquer LLM no simplicio-runtime: [`skills/simplicio-video/SKILL.md`](skills/simplicio-video/SKILL.md). Receita passo a passo: [`docs/receita-video-cliente.md`](docs/receita-video-cliente.md).

### Quickstart do CLI
```bash
pip install -e .                                   # raiz do repo (Python >= 3.10; Node >= 22 e ffmpeg para render)
simplicio-video --help                             # fluxo init -> validate -> voice -> render (cada comando tem --help)
simplicio-video init <slug> <Campanha> --template <id> --nome "<Nome>"
simplicio-video validate clients/<slug>/<video>/contract.yaml
simplicio-video voice    clients/<slug>/<video>/contract.yaml [--provider file|local|gemini]
simplicio-video render   clients/<slug>/<video>/contract.yaml [--backend local|colab] [--out x.mp4]
simplicio-video list templates|motion|voices
python -m pytest                                   # schema, validate, --help, determinismo (render curto)
```

## Mapa (todas as pastas)

| Pasta | O quê | Entrada principal |
|---|---|---|
| `schema/` | `contract.schema.json` (`simplicio.video-contract/v1`, entrada do CLI) | [receita](docs/receita-video-cliente.md) |
| `src/simplicio_video/` | CLI Python: `cli.py` (help), `contract.py` (schema + checagens), `voice.py` (providers, `timing.lock.json`), `compiler.py` (contrato → composição), `render.py` (local/colab, `render.manifest.json`), `engine/` (`build.mjs` trilha/SFX/mix, `master.sh`) | `simplicio-video --help` |
| `skills/simplicio-video/` | `SKILL.md`: como um LLM escolhe template/motion/voz/tempos e escreve o contrato | [SKILL.md](skills/simplicio-video/SKILL.md) |
| `colab/` | `render.ipynb` (render do bundle na GPU, tempos por etapa) + README | [colab/README.md](colab/README.md) |
| `tests/` | pytest: schema, validate, voice, compile (WJR byte a byte), `--help`, determinismo de hash (render de 1 s), fixture `fixtures/mini/` | — |
| `intake/` | Etapa 1: questionário (modo auto/completo), regras de extração de site/IG (só público, fonte+data por fato), `intake.schema.json` (`simplicio.intake/v1`), `exemplos/` | [intake/README.md](intake/README.md) |
| `schemas/` | Etapa 2: `video-spec.schema.json` (`simplicio.video-spec/v1`, formato do `video.json`) | — |
| `templates/<setor>/` | Etapa 3: `template.json` (cenas, padrões, campos do intake, voz, música, cuidados, `composicao`) + README + `composition/` (`index.template.html` com placeholders do CLI, fontes); `template.schema.json`. `pronto` ou `skeleton` | [templates/README.md](templates/README.md) |
| `motion/` | Etapa 4: biblioteca — `patterns/<id>/` (`pattern.json`, `block.html`, `preview.png`), `catalog.json` (gerado), `lib/retime.js`, `assets/` (fontes OFL, placeholders), `scripts/` (`preview.sh`, `catalog.mjs`), `pattern.schema.json` | [motion/README.md](motion/README.md) |
| `voices/` | Etapa 5: providers (`gemini.md` = tutorial, `elevenlabs.md`, `xai.md`, `local.md`), `narracao-tts.md` (pipeline, cache, tratamento) | [voices/README.md](voices/README.md) |
| `tools/` | Ferramentas **opcionais** com versão fixada: `video-use/` (etapa 6 — `setup.sh`, `transcribe_local.py`, `edl_transcript.py`, README com quando usar × HyperFrames direto) | [tools/README.md](tools/README.md) |
| `docs/` | `decisoes/` (ADRs), `esteira.md`, setup, pipeline determinístico, plugin, pesquisa | [docs/README.md](docs/README.md) |
| `clients/<cliente>/coleta/` | **Fatos** do cliente: `brief.md`, `fontes.md` (com data), `pendencias.md`, site salvo, `colors.json`, checklist | — |
| `clients/<cliente>/video-NN-videouse/` | Edição com video-use (etapa 6, opcional): `run.sh`, `source.variables.json` (variante da fonte), `edit/` (`edl.json`, transcrições, `takes_packed.md`, `project.md`, `verify/`), `overlay/` (HyperFrames → MOV alfa), `preview/` | README do vídeo |
| `clients/<cliente>/<video>/contract.yaml` | **Vídeo pelo CLI**: `contract.yaml`, `timing.lock.json`, `render.manifest.json`, `assets/audio/voz/` (falas tratadas), `assets/audio/vo/external/` (WAVs Gemini), README/roteiro, `preview/`. Ex.: Lothus `video-01-dia-das-criancas` | README do vídeo |
| `clients/<cliente>/video-NN/` | (legado, WJR) Projeto HyperFrames autocontido (`package.json`; rode os comandos **dentro** dele): `spec.json` (variáveis, áudio/cues, voz, clipes), `video.json`, `index.html` (timeline única + `RETIME`), `scripts/` (`build.mjs`, `voice.py`, `master.sh`, `gemini-tts.mjs`), `assets/` (+ `audio/LICENSES.md`), `preview/` | README do vídeo |

## Fluxos

**Novo cliente / novo pedido (etapas 1–2)**
1. Rode o [questionário](intake/questionario.md): com site/IG, extraia conforme [extracao-automatica.md](intake/extracao-automatica.md) e pergunte só o que falta.
2. Congele em `clients/<slug>/coleta/intake.json` (valide com `intake/intake.schema.json`) + `brief.md`, `fontes.md` (URL + data), `pendencias.md`. Fato dito em conversa = fonte nova ("confirmado por X em DD/MM/AAAA").
3. Confirme o brief com o usuário antes de seguir.

**Novo vídeo (etapas 3–7) — pelo CLI**
1. `simplicio-video list templates` → template pelo nicho (renderizável). `simplicio-video init <slug> <Campanha> --template <id>`.
2. Escreva o contrato (copy só da coleta; cenas, blocos + params, falas com `max_s`, SFX relativos à cena, voz, trilha, drive). Ver [SKILL.md](skills/simplicio-video/SKILL.md).
3. `validate` → `voice` → `validate --need-lock` → `render` (ou `--backend colab`). Confira `render.manifest.json` (loudness), STT e a prévia.
4. Os projetos npm da WJR (`video-01`, `video-02-videouse`) ficam como referência; o `video-01` também tem `contract.yaml` (render idêntico).

**Voz / narração** ([voices/](voices/README.md))
- `file` (padrão atual): WAVs externos em `assets/audio/vo/external/line-NN.wav` — ex.: Gemini no AI Studio ([voices/gemini.md](voices/gemini.md)); `scripts/gemini-tts.mjs` faz a rota API (não testada, sem chave).
- `chatterbox` / `kokoro` (locais), `elevenlabs` / `xai` (pagos, chave no ambiente).
- `voice.py` corta silêncio, trata, **nunca acelera**; frase maior que `max_s` = erro → reajuste tempos (cenas + cues) ou texto.

**Biblioteca de motion (autoria)**
- Padrão novo: `motion/patterns/<id>/pattern.json` + `block.html` → `bash motion/scripts/preview.sh <id>` (lint + preview) → `node motion/scripts/catalog.mjs` (regenera catálogo e tabela do README). Só vira `pronto` com lint limpo e preview.
- Inspiração externa: descreva e **reimplemente** com link da fonte; nunca copie código com licença restrita.

**Edição com video-use (etapa 6, OPCIONAL)** ([tools/video-use/README.md](tools/video-use/README.md) · avaliação em [docs/video-use-integracao.md](docs/video-use-integracao.md))
- Só quando o usuário pede ajuda de edição (cortar para X s, reordenar, aparar footage, legendas, revisar cortes) ou há footage real. Vídeo novo/motion = HyperFrames direto (o LLM/template compõe).
- Setup: `bash tools/video-use/setup.sh` (commit fixado, fora do repo). Exemplo completo: `clients/wjr-informatica-games/video-02-videouse/` (`run.sh`, `edit/edl.json`, `edit/project.md`).
- Transcrição sem chave: `tools/video-use/transcribe_local.py` (faster-whisper → formato Scribe, `--script spec.json` para narração nossa). Fala real → Scribe (`ELEVENLABS_API_KEY`).
- Texto que depende de contexto na fonte (contador, "passo 2"): gere variante pelo spec (`source.variables.json`), não mascare.
- Overlays HyperFrames sempre `--format mov` (WebM perde o alfa no `render.py`); loudness pelo nosso `master.sh` (`--no-loudnorm`).
- Estratégia de corte confirmada com o usuário antes do EDL; autoavaliação com `timeline_view` no corte antes de mostrar.

**Render**
- `simplicio-video render` = compila contrato + lock + template + blocos → `engine/build.mjs` (trilha/SFX/voz) → HyperFrames (`--strict-variables`) → `master.sh` (−14 LUFS, TP ≤ −1,5 dBTP) → `render.manifest.json`. HyperFrames sempre fixado: `npx --yes hyperframes@0.8.97`. Node ≥ 22.
- Colab: `--backend colab` gera bundle zip reprodutível; `colab/render.ipynb` renderiza na GPU e imprime tempos (setup, frames, encode). NVENC muda os bytes do vídeo.
- Legado WJR: `npm run render` dentro de `clients/wjr-informatica-games/video-01`.

**Determinismo**
- Nada de `Math.random` (use `rng()` com semente), `Date.now`, `fetch`, `repeat: -1` em composição ou bloco.
- Tempos de cena, cues (`spec.json → audio.cues`) e linhas de voz andam juntos: mudou um, mude os três e o `roteiro.md`.
- WAVs da narração + `manifest.json` são versionados (cache); o render não precisa de TTS nem rede.

**Validação antes de commitar**
- `python -m pytest` · `simplicio-video validate` nos contratos alterados · `node motion/scripts/catalog.mjs --check` (catálogo em dia) · schemas com AJV (`intake`, `template`, `pattern`, `video-spec`) · links relativos dos `.md` sem quebra · `npm run check` no vídeo alterado.

## Entregas no Google Drive

- Vídeo entregue fica no Drive em `simplicio-video/clientes/NOME_CLIENTE/ANO/CAMPANHA`.
  - `NOME_CLIENTE`: Title_Case com underscore, sem acento (ex.: `WJR_Informatica_Games`, `Lothus_Odontologia`).
  - `ANO`: ano da campanha (`2026`). `CAMPANHA`: Title_Case com underscore (ex.: `Video_Institucional`, `Dia_Criancas`).
- Nome do arquivo: `<CLIENTE> - <descricao> - vNN.mp4` (ex.: `Lothus - Dia das Criancas 15s - v01.mp4`); versão nova = `vNN+1`, nunca sobrescrever.
- O repositório guarda **os links**, nunca o MP4 final como entrega (`out/` é gitignored; `preview/` só leva a prévia leve 720p).
- Todo link novo entra na tabela **Entregas no Drive** de `clients/<slug>/README.md` (campanha, pasta, arquivo, link, versão/status).
- Upload é feito pelo Wesley; agente não sobe nada ao Drive sem pedido explícito.

## Convenções e travas

- **Só fatos reais**: toda copy vem de `coleta/`. Nada de preço, prazo, garantia, avaliações, números ou promessas ("sem drift") sem confirmação registrada.
- **Organização**: cada coisa na pasta da sua etapa (tabela acima); nada solto na raiz; trabalho de cliente só em `clients/`; artefatos (`out/`, `build/`, `node_modules/`) gitignored.
- **Licenças**: só trilha/SFX/voz/fonte com uso comercial claro; registre em `assets/audio/LICENSES.md` (e fontes ao lado dos arquivos). Assets do cliente ficam em `assets/client/` (gitignored) até aprovação.
- Não clonar voz de pessoa real sem autorização dela.
- Docs em **pt-BR**; comentários de código em inglês.
- Segredos (API keys) só no ambiente/`.env` (gitignored), nunca no repo.
- Commits pequenos e claros, mensagem em pt-BR, push na `main`; horários em BRT.
