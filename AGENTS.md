# AGENTS.md — simplicio-videos

Regras, mapa e fluxos para qualquer agente (Claude Code, Codex, Grok) trabalhando neste repositório. Cada vídeo também tem o seu `AGENTS.md` com detalhes da composição.

## Missão e operação de vendas

Este repositório é só a **execução dos scripts e a geração dos vídeos** (CLI `simplicio-video`). A **missão de vendas e o guia de operação** (preços, mensagens aprovadas, funil, planilha de controle, Paperclip, times, estado atual e próximos passos) ficam no Google Drive, em [`simplicio-video/AGENTS.md`](https://drive.google.com/file/d/19Y0BvZw-st_YasMk39vNkbNGd_4pJ4ir/view?usp=drivesdk) (conta wesleybob4). Leia esse guia antes de qualquer trabalho de venda ativa.

## O que é

**simplicio-videos** é o plugin de vídeo do **Simplicio Runtime (Simplicio MCP)** ([ADR-0001](docs/decisoes/ADR-0001-visao-plugin.md)). Pedido de vídeo → **esteira determinística** ([docs/esteira.md](docs/esteira.md)):

1. **intake** (questionário; com site/Instagram extrai sozinho e pergunta só o que falta) → 2. **brief/spec** (fonte única da verdade) → 3. **template do setor** → 4. **composição** com a biblioteca de motion (HyperFrames) → 5. **voz TTS** (provider à escolha, cache) → 6. **video-use** (footage, opcional) → 7. **render determinístico** + QA.

LLM (Opus 5.5) **só** cria template/padrão novo; nunca está no caminho do render.

**Entrada oficial: o CLI `simplicio-video`** ([ADR-0002](docs/decisoes/ADR-0002-cli-contrato-colab-creditos.md); fluxo 100% script, backends remotos, Drive e MCP: [ADR-0003](docs/decisoes/ADR-0003-fluxo-100-script.md); custo por vídeo: [docs/custos.md](docs/custos.md)). **Render local é o padrão**; Colab/Kaggle são opcionais, só para clientes via créditos e com `--backend` explícito. O agente raciocina e escreve o **contrato YAML** (`schema/contract.schema.json`); o CLI valida, gera a voz e renderiza. Skill para qualquer LLM no simplicio-runtime: [`skills/simplicio-video/SKILL.md`](skills/simplicio-video/SKILL.md). Receita passo a passo: [`docs/receita-video-cliente.md`](docs/receita-video-cliente.md).

### Quickstart do CLI
```bash
pip install -e .                                   # raiz do repo (Python >= 3.10; Node >= 22 e ffmpeg para render)
simplicio-video --help                             # fluxo init -> validate -> voice -> render (cada comando tem --help)
simplicio-video init <slug> <Campanha> --template <id> --nome "<Nome>"
simplicio-video validate clients/<slug>/<video>/contract.yaml
simplicio-video voice    clients/<slug>/<video>/contract.yaml [--provider file|local|gemini]   # gemini = API (GEMINI_API_KEY)
simplicio-video render   clients/<slug>/<video>/contract.yaml [--backend local|kaggle|colab-cli|colab] [--out x.mp4]
simplicio-video run      clients/<slug>/<video>/contract.yaml --provider gemini   # render local (padrão)
simplicio-video render   <contrato.yaml> --preview   # prévia 540x960 com marca d'água e crédito final do contrato (marca.dagua, marca.credito)
# comandos de venda (prospect, venda, ugc) e publish saíram do CLI do motor (#77) e ficam no repositório de operação
simplicio-video clone [args]                            # Hypit AI: clonagem de vídeo com agentes (https://github.com/hypit-ai/hypit)
simplicio-video montage [clone|open|serve|demo|args]   # OpenMontage: produção de vídeo com agentes (https://github.com/calesthio/OpenMontage)
simplicio-video mcp                                 # servidor MCP stdio (pip install -e .[mcp])
simplicio-video list templates|motion|voices
simplicio-video edit setup|transcribe|pack|render|verify   # edição por EDL com video-use (tools/video-use)
simplicio-video opencut clone|dev|where            # editor OpenCut para acabamento manual
simplicio-video status [--json] [contrato]         # ferramentas instaladas, versões fixadas e estado do render
simplicio-video install [--check]                  # ambiente do checkout (.venv com uv); --check só mostra o plano
simplicio-video update [--check]                   # git pull --ff-only, reinstala e roda doctor; --check não altera nada
simplicio-video doctor [--json]                    # diagnóstico do ambiente com a correção de cada falha
simplicio-video setup                              # primeira execução: cria o workspace (tema, idioma, autonomia L1)
python -m pytest                                   # schema, validate, --help, determinismo (render curto)
```

## Mapa (todas as pastas)

| Pasta | O quê | Entrada principal |
|---|---|---|
| `schema/` | `contract.schema.json` (`simplicio.video-contract/v1`, entrada do CLI) | [receita](docs/receita-video-cliente.md) |
| `src/simplicio_video/` | CLI Python: `cli.py` (help), `contract.py` (schema + checagens), `voice.py` (providers, `timing.lock.json`), `compiler.py` (contrato → composição), `render.py` (local + bundle, `render.manifest.json`), `remote.py` (Kaggle, Colab CLI), `publish.py` (Drive/rclone), `pipeline.py` (`run`), `prospect.py` (venda ativa: coleta pública, setor → modelo, contrato, lote), `venda.py` (cobrança Pix AbacatePay, webhook de pagamento, entrega HD, `venda.json`), `clone.py` (Hypit AI), `montage.py` (OpenMontage), `mcp_server.py` (tools `video.*`), `engine/` (`build.mjs` trilha/SFX/mix, `master.sh`, `remote_render.py` = script headless dos backends remotos) | `simplicio-video --help` |

| `skills/simplicio-video/` | `SKILL.md`: como um LLM escolhe template/motion/voz/tempos e escreve o contrato | [SKILL.md](skills/simplicio-video/SKILL.md) |
| `colab/` | `render.ipynb` (render do bundle na GPU, tempos por etapa) + README | [colab/README.md](colab/README.md) |
| `tests/` | pytest: schema, validate, voice, compile (WJR byte a byte), `--help`, determinismo de hash (render de 1 s), fixture `fixtures/mini/` | — |
| `intake/` | Etapa 1: questionário (modo auto/completo), regras de extração de site/IG (só público, fonte+data por fato), `intake.schema.json` (`simplicio.intake/v1`), `exemplos/` | [intake/README.md](intake/README.md) |
| `schemas/` | Etapa 2: `video-spec.schema.json` (`simplicio.video-spec/v1`, formato do `video.json`) | — |
| `templates/<setor>/` | Etapa 3: `template.json` (cenas, padrões, campos do intake, voz, música, cuidados, `composicao`) + README + `composition/` (`index.template.html` com placeholders do CLI, fontes); `template.schema.json`. `pronto` ou `skeleton` | [templates/README.md](src/simplicio_video/data/templates/README.md) |
| `motion/` | Etapa 4: biblioteca — `patterns/<id>/` (`pattern.json`, `block.html`, `preview.png`), `catalog.json` (gerado), `lib/retime.js`, `assets/` (fontes OFL, placeholders), `scripts/` (`preview.sh`, `catalog.mjs`), `pattern.schema.json` | [motion/README.md](src/simplicio_video/data/motion/README.md) |
| `voices/` | Etapa 5: providers (`gemini.md` = tutorial, `elevenlabs.md`, `xai.md`, `local.md`), `narracao-tts.md` (pipeline, cache, tratamento) | [voices/README.md](voices/README.md) |
| `tools/` | Ferramentas **opcionais** com versão fixada: `video-use/` (etapa 6 — `setup.sh`, `transcribe_local.py`, `edl_transcript.py`, README com quando usar × HyperFrames direto) | [tools/README.md](tools/README.md) |
| `ugc/` | **Trilha UGC (gerativa, fora do `render`)**: `pack.json` (10 personagens, `simplicio.ugc-pack/v1`) + `pack.schema.json`, `prompts/` (5 prompts: elenco, imagem, fullbody, roteiros, Seedance). O CLI `ugc list\|prompt` só monta/valida o prompt; imagem e vídeo são gerados à mão. [ADR-0004](docs/decisoes/ADR-0004-ugc-generativo.md) | [ugc/README.md](ugc/README.md) |
| `docs/` | `decisoes/` (ADRs), `esteira.md`, setup, pipeline determinístico, plugin, pesquisa | [docs/README.md](docs/README.md) |
| `prospects/` | **Venda ativa** (fora do git, exceto `exemplo-dia-criancas.csv`): `<lote>/<slug>/{coleta.json, contract.yaml, preview.mp4, result.json}` + `<lote>/lote.csv` | [docs/venda-ativa.md](docs/venda-ativa.md) |
| `clients/<cliente>/coleta/` | **Fatos** do cliente: `brief.md`, `fontes.md` (com data), `pendencias.md`, site salvo, `colors.json`, checklist | — |
| `clients/<cliente>/video-NN-videouse/` | Edição com video-use (etapa 6, opcional): `run.sh`, `source.variables.json` (variante da fonte), `edit/` (`edl.json`, transcrições, `takes_packed.md`, `project.md`, `verify/`), `overlay/` (HyperFrames → MOV alfa), `preview/` | README do vídeo |
| `clients/<cliente>/<video>/contract.yaml` | **Vídeo pelo CLI**: `contract.yaml`, `timing.lock.json`, `render.manifest.json`, `assets/audio/voz/` (falas tratadas), `assets/audio/vo/external/` (WAVs Gemini), README/roteiro, `preview/`. Ex.: Lothus `video-01-dia-das-criancas` | README do vídeo |
| `clients/<cliente>/video-NN/` | (legado, WJR) Projeto HyperFrames autocontido (`package.json`; rode os comandos **dentro** dele): `spec.json` (variáveis, áudio/cues, voz, clipes), `video.json`, `index.html` (timeline única + `RETIME`), `scripts/` (`build.mjs`, `voice.py`, `master.sh`, `gemini-tts.mjs`), `assets/` (+ `audio/LICENSES.md`), `preview/` | README do vídeo |

## Plugins e host

Mapa gerado a partir do front matter de `docs/host/` e `docs/plugins/` (`make regen`). A referência da CLI, dos schemas, das tools MCP e das variáveis de ambiente fica em [`docs/reference/`](docs/reference/).

<!-- BEGIN GENERATED: host -->
Gerado de `docs/host/*.md` (front matter). Não edite aqui: rode `make regen`.

- [Gate local, TDD e pouso de PRs](docs/host/gate.md): Como provar que a main está verde com um comando offline, a regra de testes primeiro, o ownership por issue e o pouso serializado sem CI.
- [Kernel da fábrica (simplicio_factory)](docs/host/kernel.md): O que é o kernel da fábrica, os Protocols e dataclasses, transition() como única forma de mudar o estado, JsonStore e MemoryStore, o testkit e o alvo make factory-schema.
- [Licenças das dependências](docs/host/licenses.md): Como o gate confere licenças (allowlist MIT, Apache-2.0, BSD, ISC, PSF, MPL-2.0), como adicionar uma exceção justificada, como regerar docs/licenses.md e o que ainda falta (web/).
- [Pacote de operação (install, update, doctor, setup)](docs/host/packaging.md): O que cada subcomando faz, o que o doctor checa, por que a falta de GEMINI_API_KEY é aviso e os limites até as
- [Host de plugins (manifesto, registro e despacho)](docs/host/plugin-host.md): Como cada plugin declara os seus comandos no plugin.json, como o registro descobre os plugins, como o despacho roda antes do argparse, e por que o plugin.json da raiz é outro arquivo.
<!-- END GENERATED -->

<!-- BEGIN GENERATED: plugins -->
Gerado de `docs/plugins/*.md` (front matter). Não edite aqui: rode `make regen`.

- [Studio (Draft e marca viram vídeo)](docs/plugins/studio.md): O que o studio faz (Draft e brand.json viram contract.yaml e MP4), os comandos make, make preview e draft show, o composer determinístico, o claim guard, content_hash, a voz desligada por padrão, o template brand-promo e as pendências conhecidas.
<!-- END GENERATED -->

## Fluxos

**Novo cliente / novo pedido (etapas 1–2)**
1. Rode o [questionário](intake/questionario.md): com site/IG, extraia conforme [extracao-automatica.md](intake/extracao-automatica.md) e pergunte só o que falta.
2. Congele em `clients/<slug>/coleta/intake.json` (valide com `intake/intake.schema.json`) + `brief.md`, `fontes.md` (URL + data), `pendencias.md`. Fato dito em conversa = fonte nova ("confirmado por X em DD/MM/AAAA").
3. Confirme o brief com o usuário antes de seguir.

**Venda ativa em massa (prévias para oferecer)**
1. Monte o CSV (`nome, cidade, setor, site, instagram, whatsapp, maps, nome_curto, fontes`) com empresas achadas por busca web; registre a fonte de cada @/WhatsApp.
2. O template sai da coluna `setor` (`templates/prospect-roteamento.json`): `--campanha auto` (padrão) = odontologia/infantil no Dia das Crianças, advocacia e estética nos institucionais; `--campanha institucional` = institucional por setor. Advocacia exige `oab`.
   `prospect` saiu do CLI do motor (#77) e fica no repositório de operação (antes gerava `prospects/<lote>/<slug>/preview.mp4` + `lote.csv`).
3. Padrão v2 (default): voz Gemini 3.8 Flash TTS Laomedeia animada (a da Lothus v02; reserva Achernar), **logo real** (coluna `logo` do CSV tirada do site/Instagram da empresa, ou logo do site) e ritmo da Lothus v02; nunca gerar/recriar logo. Só dado público e da empresa (LGPD), Instagram sem login (robots.txt do instagram.com proíbe robôs: o @ vem do CSV/site), nunca preço/promoção/fato inventado. **Nada é enviado pelo agente**: o Wesley revisa e envia ([docs/venda-ativa.md](docs/venda-ativa.md)).

**Novo vídeo (etapas 3–7) — pelo CLI**
1. **Referência (antes de escrever):** busque 2–3 vídeos parecidos (nicho, formato, duração) em [Skillry — Opus 5.5](https://skillry.dev/ai-videos/opus-5-5) (original ao lado do remake, com o prompt do criador) e, se precisar, na web; anote o que serve de estrutura (gancho, ritmo, nº de cenas, tipo de transição) em `clients/<slug>/coleta/referencias.md` com URL + data. Referência inspira **forma**; **fatos, textos e marca só da coleta**. Não copie prompt, roteiro ou imagem de terceiros (direitos autorais) e não use no vídeo nada que a referência afirme sobre o cliente.
2. `simplicio-video list templates` → template pelo nicho (renderizável). `simplicio-video init <slug> <Campanha> --template <id>`.
3. Escreva o contrato (copy só da coleta; cenas, blocos + params, falas com `max_s`, SFX relativos à cena, voz, trilha, drive). Ver [SKILL.md](skills/simplicio-video/SKILL.md).
4. `validate` → `voice` → `validate --need-lock` → `render` (ou `run`, que faz tudo; `--backend kaggle|colab-cli` renderiza remoto sem navegador). Confira `render.manifest.json` (loudness), STT e a prévia.
5. Os projetos npm da WJR (`video-01`, `video-02-videouse`) ficam como referência; o `video-01` também tem `contract.yaml` (render idêntico).

**Vídeo UGC (gerativo)** ([ugc/README.md](ugc/README.md) · [ADR-0004](docs/decisoes/ADR-0004-ugc-generativo.md))
1. Fatos e público vêm de `clients/<slug>/coleta/`; sem fato confirmado, sem fala ("Só fatos reais"). Fora da esteira: sem contrato, template, motion nem `render`, e fora da regra de determinismo.
2. Elenco, prompt de imagem e roteiros (passos 1, 2, 4) são prompts de LLM em `ugc/prompts/01` a `04`; imagens (passo 3) e clipes (passo 6) são gerativos e manuais (ChatGPT, Higgsfield, Krea).
3. Os comandos `ugc` saíram do CLI do motor (#77) e ficam no repositório de operação. Renderize 1 clipe por personagem, confira rosto e voz e só então use o áudio como referência de voz nos outros.
4. Travas: personagem sintético (nunca rosto ou voz de pessoa real sem autorização); sem depoimento fabricado apresentado como cliente real; rótulo de IA da plataforma e CONAR; imagens e MP4 em `out/ugc/<slug>/` e no Drive, nunca no git; chaves só no ambiente; gerar em plataforma paga só com pedido explícito do Wesley.

**Voz / narração** ([voices/](voices/README.md))
- `gemini`: API do Gemini TTS pelo CLI (`GEMINI_API_KEY`, `gemini-3.8-flash-tts`, Interactions API; cache no lock). `file`: WAVs externos em `assets/audio/vo/external/line-NN.wav` (ex.: AI Studio manual, [voices/gemini.md](voices/gemini.md)).
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
- Remoto (**opcional**, só para clientes via créditos; o padrão é local): `--backend kaggle` (4 vCPU) / `colab-cli` (Colab grátis = 2 vCPU; A100 = 0,43 unidade ≈ US$ 0,043 por vídeo WJR, ver [custos](docs/custos.md)) / `colab` (notebook manual) usam o mesmo bundle + `render_bundle.sh`. A captura do Chrome é CPU (gargalo); GPU só no encode (NVENC, `--gpu-encode`, muda os bytes). Frames/áudio só batem com o local com o mesmo ffmpeg (`SIMPLICIO_FFMPEG_DIR` / `SIMPLICIO_FFMPEG_URL`+`_SHA256`). Ver ADR-0003.
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
- Upload: `publish` e a flag de upload do `run` saíram do CLI do motor (#77) e ficam no repositório de operação (rclone, remote `gdrive`; nunca sobrescreve, link pelo ID). O agente **só** faz upload com pedido explícito do Wesley para aquele vídeo. A exceção do fluxo de venda (Pix) também saiu do motor (#77).

## Convenções e travas

- **Só fatos reais**: toda copy vem de `coleta/`. Nada de preço, prazo, garantia, avaliações, números ou promessas ("sem drift") sem confirmação registrada.
- **Organização**: cada coisa na pasta da sua etapa (tabela acima); nada solto na raiz; trabalho de cliente só em `clients/`; artefatos (`out/`, `build/`, `node_modules/`) gitignored.
- **Licenças**: só trilha/SFX/voz/fonte com uso comercial claro; registre em `assets/audio/LICENSES.md` (e fontes ao lado dos arquivos). Assets do cliente ficam em `assets/client/` (gitignored) até aprovação.
- Não clonar voz de pessoa real sem autorização dela.
- Docs em **pt-BR**; comentários de código em inglês.
- Segredos (API keys) só no ambiente/`.env` (gitignored), nunca no repo.
- Commits pequenos e claros, mensagem em pt-BR, push na `main`; horários em BRT.
