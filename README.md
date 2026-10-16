# simplicio-videos

**Video plugin for Simplicio Runtime (Simplicio MCP): a deterministic video machine driven by agents.** A user asks for a video; the plugin runs a **deterministic pipeline**: intake questionnaire (with automatic site/Instagram extraction) → brief/spec → sector template → composition from the motion pattern library (HyperFrames) → TTS voice (Gemini, local, cloned voices; cached) → optional footage editing (video-use) → deterministic render. The LLM only decides things (contract, EDL) and creates new templates/patterns; it is never in the render path.

Decisions: [ADR-0001](docs/decisoes/ADR-0001-visao-plugin.md) · [ADR-0002 (CLI + contract + Colab + credits)](docs/decisoes/ADR-0002-cli-contrato-colab-creditos.md) · [ADR-0003 (100% script flow; local render by default)](docs/decisoes/ADR-0003-fluxo-100-script.md) · [ADR-0004 (generative UGC outside the deterministic render)](docs/decisoes/ADR-0004-ugc-generativo.md) · Costs: [docs/custos.md](docs/custos.md) · Outbound sales: [docs/venda-ativa.md](docs/venda-ativa.md) · Manifest: [`plugin.json`](plugin.json) · Skill: [`skills/simplicio-video/SKILL.md`](skills/simplicio-video/SKILL.md)

**Entry point: the `simplicio-video` CLI.** The agent writes the YAML contract ([`schema/contract.schema.json`](src/simplicio_video/data/schema/contract.schema.json)); the CLI validates it, generates the voice and renders deterministically (local or Colab GPU). Agents (Claude Code, Codex, Grok): start at [`AGENTS.md`](AGENTS.md).

## Apps

Every external tool is a **track** with one CLI command, one MCP verb (`plugin.json`) and one doc. Install and run them yourself; nothing is vendored. All of it is optional except HyperFrames and ffmpeg.

### Video apps

| App | License | Role | CLI command | MCP verb | Doc |
|---|---|---|---|---|---|
| [HyperFrames](https://github.com/heygen-com/hyperframes) | Apache-2.0 | Deterministic HTML/GSAP → MP4 render (core) | `simplicio-video render contract.yaml` | `video.render` | [motion/README.md](src/simplicio_video/data/motion/README.md) |
| [video-use](https://github.com/browser-use/video-use) | MIT | EDL editing of any MP4 (cuts, reorder, subtitles, review) | `simplicio-video edit setup\|transcribe\|pack\|render\|verify` | `video.edit` | [tools/video-use](tools/video-use/README.md) |
| [OpenMontage](https://github.com/calesthio/OpenMontage) | see repo | Agentic production pipelines (Backlot, Remotion, HyperFrames) | `simplicio-video montage [clone\|open\|serve\|demo]` | `video.montage` | [docs/recursos.md](docs/recursos.md) |
| [OpenCut](https://github.com/OpenCut-app/OpenCut) | MIT | Open-source editor for manual finishing (uses `opencut-classic` until the rewrite has an API) | `simplicio-video opencut clone\|dev\|where` | `video.opencut` | [docs/recursos.md](docs/recursos.md) |
| [Hypit AI](https://github.com/hypit-ai/hypit) | see repo | Clone viral videos into agent workflows | `simplicio-video clone [args]` | `video.clone` | [docs/recursos.md](docs/recursos.md) |
| [MoneyPrinterTurbo](https://github.com/harry0703/MoneyPrinterTurbo) | MIT | Topic-to-short-video generator (LLM script, synthesized voice, stock footage; Python 3.11+) | `simplicio-video moneyprinter clone\|setup\|serve\|where\|status` | `video.moneyprinter` (clone, where) | [docs/recursos.md](docs/recursos.md) |
| [Toonflow](https://github.com/HBAI-Ltd/Toonflow-app) | MIT | Open-source AI studio for short dramas, comic dramas and videos (local web app on Bun) | `simplicio-video toonflow clone\|serve\|where` | `video.toonflow` (clone, where) | [docs/recursos.md](docs/recursos.md) |

| Redes sociais sem postar (`social`) | n/a | Plano de postagem com limites por rede e receita das chamadas MCP do Real Oficial (padrão) ou do Zernio; o motor não posta | `simplicio-video social providers\|plan\|check\|recipe` | `video.social` (providers, plan, check, recipe) | [docs/recursos.md](docs/recursos.md) |
| Troca de personagem (`swap`) | n/a | Troca o personagem de um vídeo por um avatar de referência, agnóstico de fornecedor (gemini, fal, wavespeed, kie, alibaba) | `simplicio-video swap providers\|estimate\|run\|status` | `video.swap` (providers, estimate) | [docs/recursos.md](docs/recursos.md) |

Toonflow runs from a pinned checkout, as its own program:

```bash
simplicio-video toonflow clone   # clones at the commit pinned in src/simplicio_video/tools.py
simplicio-video toonflow serve --lan   # bun install --frozen-lockfile, build, start: http://localhost:3000
```

It needs Bun (the version is in the checkout's `packageManager` field). The server has **no login** and listens on every interface (`0.0.0.0:3000`), so `serve` refuses to start without `--lan`. To keep it on your own machine, run the Docker setup from Toonflow's `compose.yaml` (publishes `127.0.0.1:3000`) or block port 3000 at the firewall. Its data goes to `~/.simplicio-video/toonflow-data` (set `TOONFLOW_DATA_DIR` to move it), outside the checkout, so a re-clone never deletes it. Model API keys are entered in Toonflow's own UI. Toonflow sits outside the deterministic render; whatever it produces enters a contract as a file with a hash.

MoneyPrinterTurbo is a support track outside the engine, like Toonflow and OpenCut: it does not replace `contract.yaml -> MP4`. It runs from a pinned checkout with its own isolated virtualenv:

```bash
simplicio-video moneyprinter clone    # clones at the commit pinned in src/simplicio_video/tools.py
simplicio-video moneyprinter setup    # venv in ~/.simplicio-video/moneyprinter-data, pip install -r requirements.txt, config.toml copied from the example (no key filled)
simplicio-video moneyprinter serve    # WebUI on http://localhost:8501; add --api for the API on http://localhost:8080/docs
simplicio-video moneyprinter status   # config.toml exists? which keys are filled (yes only, never the value)
```

It needs Python 3.11 or newer and uses ffmpeg. Upstream's API listens on `0.0.0.0` by default and neither the WebUI nor an API with an empty `app.api_key` has a login, so `serve` forces `127.0.0.1` by argument (it starts uvicorn on the same `app.asgi:app` instead of `main.py`, whose host comes from `config.toml`) and only listens on every interface with `--lan`. The generator calls third-party services with their own terms (an LLM provider, a TTS service and stock footage such as Pexels, Pixabay and Coverr) using **your own** API keys, typed in its WebUI or in `config.toml`; this command never prints them and the MCP tool never runs `setup` or `serve`. Generated videos go to `~/.simplicio-video/moneyprinter-data/storage` (set `MONEYPRINTER_DATA_DIR` to move it). Whatever it produces enters a contract as a file with a hash.

### Audio apps

| App | License | Role | Provider (`voz.provider` / `--provider`) | Setup | Doc |
|---|---|---|---|---|---|
| Gemini TTS | cloud API | Default narration | `gemini` (or `file` for AI Studio WAVs) | `GEMINI_API_KEY` | [voices/gemini.md](voices/gemini.md) |
| Kokoro-82M | Apache-2.0 | Free local draft voice (pt-BR ok) | `local` | `SIMPLICIO_TTS_PY` | [voices/local.md](voices/local.md) |
| [VoxCPM2](https://github.com/OpenBMB/VoxCPM) | Apache-2.0 | Voice design from a text description, or cloning from a short reference clip (30 languages, 48 kHz) | `voxcpm` | `pip install voxcpm`, `VOXCPM_BIN` | [voices/voxcpm.md](voices/voxcpm.md) |
| [OpenVoice V2](https://github.com/myshell-ai/OpenVoice) | MIT | Voice cloning: converts a base take (Kokoro) to the reference speaker's timbre | `openvoice` | `OPENVOICE_PY`, `OPENVOICE_CHECKPOINTS` | [voices/openvoice.md](voices/openvoice.md) |
| [VoiceStudio](https://github.com/debpalash/VoiceStudio) | AGPL-3.0 (HTTP only, never vendored) | Local ElevenLabs alternative: your cloned voice profiles through an OpenAI-compatible API | `voicestudio` | `VOICESTUDIO_URL` (default `http://localhost:3900`) | [voices/voicestudio.md](voices/voicestudio.md) |
| [Real Oficial](https://api.realoficial.com.br/mcp) | cloud MCP | Social scheduling/publishing, AI image/video, cuts (49 MCP tools, OAuth; see docs/realoficial.md) | — (MCP) | `simplicio-video realoficial config` | [docs/realoficial.md](docs/realoficial.md) |

All voice providers go through the same pipeline: raw take kept per provider → silence trim → contract ffmpeg chain → 48 kHz mono → `timing.lock.json`. A take longer than its slot is an error; audio is **never time-stretched**. Cloned voices need the **written authorization of the speaker**; see [voices/README.md](voices/README.md).

## Repository map

```
simplicio-videos/
├── AGENTS.md / CLAUDE.md   # rules + map + flows for agents (CLAUDE.md → AGENTS.md)
├── plugin.json             # simplicio.plugin/v1 — entrypoint simplicio-video (video.* verbs) + skill
├── pyproject.toml          # Python package of the CLI (src/simplicio_video/), tests in tests/
├── schema/                 # contract.schema.json (CLI contract)
├── skills/simplicio-video/ # SKILL.md for LLMs in simplicio-runtime
├── skills/simplicio-video-social/ # SKILL.md: posting to social networks with the provider's MCP tools
├── colab/                  # render.ipynb (GPU) for --backend colab bundles
├── intake/                 # questionnaire, site/IG extraction, intake.schema.json, examples/
├── templates/              # one template per sector (template.json + README)
├── motion/                 # motion pattern library: patterns/<id>/, catalog.json, lib/, scripts/
├── voices/                 # voice providers + TTS pipeline (see Audio apps)
├── tools/                  # optional pinned tools (video-use)
├── ugc/                    # generative UGC track (outside the render): pack.json, prompts/
├── schemas/                # video-spec.schema.json (simplicio.video-spec/v1)
├── docs/                   # ADRs, pipeline, setup — index in docs/README.md
└── clients/<client>/       # example videos only: <video>/contract.yaml, preview/, assets
```

### Troca de personagem (`swap`)

Troca o personagem de um vídeo existente por um avatar de referência. Cada fornecedor entra por um adaptador (`gemini`, `fal`, `wavespeed`, `kie`, `alibaba`, mais `fake` para testes); a orquestração é uma só: valida, corta em pedaços, estima, submete, espera, baixa, remonta o áudio original e emenda.

```bash
simplicio-video swap providers                                   # adaptadores, capacidades, preço (US$ e R$) e confiança
simplicio-video swap estimate --provider gemini --video in.mp4 --ref avatar.png
simplicio-video swap run --provider gemini --video in.mp4 --ref avatar.png --out out/swap.mp4 --autorizo            # dry-run: só estima
GEMINI_API_KEY=... simplicio-video swap run --provider gemini --video in.mp4 --ref avatar.png --out out/swap.mp4 --autorizo --yes --max-usd 2
simplicio-video swap status out/swap.manifest.json
```

`--autorizo` é obrigatório (você confirma ter direito sobre o vídeo e as imagens). Sem `--yes` nada é enviado; `--max-usd` aborta antes de submeter. A chave só entra pela variável de ambiente do provedor. Só o `gemini` foi conferido contra a documentação real; `fal`, `wavespeed`, `kie` e `alibaba` estão **UNVERIFIED** e pedem `--aceito-unverified` para gastar. O MCP (`video.swap`) só faz `providers` e `estimate`: gastar é só pelo terminal. Detalhes em [docs/recursos.md](docs/recursos.md).

### Redes sociais sem postar (`social`)

O motor não posta. O módulo `social` só faz o que é local e determinístico; quem publica é o agente, com as ferramentas MCP do provedor (Real Oficial, o padrão, ou Zernio) e o sim explícito do usuário em cada postagem ([ADR-0018](docs/decisoes/ADR-0018-social-planejar-sem-postar.md), skill [`simplicio-video-social`](skills/simplicio-video-social/SKILL.md)).

```bash
simplicio-video social providers                                                     # realoficial (padrão) e zernio: ferramentas MCP, limites, lacunas, UNVERIFIED
simplicio-video social plan --video out/final.mp4 --caption-file legenda.txt --target tiktok=@conta --target youtube \
    [--at 2026-10-20T09:30 --timezone America/Sao_Paulo] [--title "..."] [--ai-generated]   # grava out/social.plan.json
simplicio-video social check out/social.plan.json                                    # o vídeo e o plano continuam iguais?
simplicio-video social recipe out/social.plan.json [--provider zernio] [--clip-id ID] # a sequência de chamadas MCP: cotar, mostrar, consentimento, publicar
```

O `plan` recusa vídeo que não existe ou que não é MP4, confere duração, proporção, tamanho, legenda, título e hashtags contra `src/simplicio_video/data/social/limits.json` (cada linha com `source_url`, `read_on` e `confidence`; só o limite de duração do YouTube Shorts foi conferido na página oficial, o resto é **UNVERIFIED** e pede `--aceito-unverified` para passar) e nunca grava chave ou token. O MCP (`video.social`) só faz `providers`, `plan`, `check` e `recipe`; não existe ação de publicar. O Real Oficial não recebe MP4 local por MCP: a receita pede o `clip_id` de um clip que já esteja lá.

## Catalogs

| What | Where | Today |
|---|---|---|
| Motion patterns | [motion/README.md](src/simplicio_video/data/motion/README.md) | 46 (24 ready blocks with preview, 1 lib, 2 inline, 19 proposed) |
| Sector templates | [templates/README.md](src/simplicio_video/data/templates/README.md) | 2 ready (repair/games, dentistry) + 6 skeleton |
| Voices | [voices/README.md](voices/README.md) | Gemini (default), Kokoro, VoxCPM2, OpenVoice V2, VoiceStudio |
| Intake | [intake/README.md](intake/README.md) | questionnaire, auto extraction, schema, WJR example |
| Optional tools | [tools/README.md](tools/README.md) | video-use |
| UGC (generative) | [ugc/README.md](ugc/README.md) | 10 characters + 5 prompts |
| Ad formats | `src/simplicio_video/data/formats/formats.json` | 50 formats from the Drive swipe file, with the example folder and file name (`simplicio-video formats list`, `formats prompt <id> --copia <file>`) |
| Ad angles | `src/simplicio_video/data/angles/angles.json` | 50 angles in 5 groups (`simplicio-video list angles --grupo prova`) |

## Example videos

Rendered examples only. Client facts (`coleta/`: briefs, sources, contacts, Drive links) are not kept in the repo and are gitignored.

| Example | Folder | What |
|---|---|---|
| Repair shop / games, 9:16 Reels, 20 s | [video-01](clients/wjr-informatica-games/video-01/) · [preview](clients/wjr-informatica-games/video-01/preview/) | pt-BR narration (Gemini TTS) + own music/SFX; reference for template `assistencia-tecnica-games` |
| Cutdown 11.5 s of the above | [video-02-videouse](clients/wjr-informatica-games/video-02-videouse/) · [preview](clients/wjr-informatica-games/video-02-videouse/preview/) | built with [video-use](docs/video-use-integracao.md) (EDL + HyperFrames overlay) |
| Dentistry, 9:16 post, 15 s, Children's Day | [video-01-dia-das-criancas](clients/lothus-odontologia/video-01-dia-das-criancas/) · [preview](clients/lothus-odontologia/video-01-dia-das-criancas/preview/) | reference for template `saude-odontologia` |

## Quick start (CLI)

```bash
gh repo clone simpletibr/simplicio-videos && cd simplicio-videos
pip install -e .                      # `simplicio-video` command (Python >= 3.10); render needs Node >= 22 + ffmpeg
simplicio-video --help                # flow: init -> validate -> voice -> render
cd clients/lothus-odontologia/video-01-dia-das-criancas
simplicio-video validate contract.yaml
simplicio-video voice contract.yaml   # provisional local voice (Kokoro) or --provider file|gemini|voxcpm|openvoice|voicestudio
simplicio-video render contract.yaml  # out/lothus-dia-criancas.mp4 + render.manifest.json
simplicio-video render contract.yaml --backend colab   # bundle for colab/render.ipynb (GPU)
```

Cloned voice in the contract (VoxCPM2 example):

```yaml
voz:
  provider: voxcpm
  providers:
    voxcpm:
      reference_audio: assets/audio/ref/speaker.wav   # authorized speaker, clean 10-30 s
      reference_text: "Exact transcript of the clip."  # optional: ultimate cloning
      control: "warm, slightly faster"                 # optional style
      seed: 42
```

Tests: `PYTHONPATH=src python -m pytest`. Library previews: `bash motion/scripts/preview.sh && node motion/scripts/catalog.mjs`. Legacy WJR (npm): `cd clients/wjr-informatica-games/video-01 && npm run render`.

## Documentation

Index in [`docs/README.md`](docs/README.md). Curated video/motion tools (stars and licenses): [`docs/recursos.md`](docs/recursos.md). External reference: [Skillry — viral videos made with Claude Opus 5.5](https://skillry.dev/ai-videos/opus-5-5).

Also built on [video-shotcraft](https://github.com/Vincentwei1021/video-shotcraft), [awesome-opus5-5-videos](https://github.com/yihui-dev/awesome-opus5-5-videos) (recipes distilled into `motion/`) and [motion-video-kit](https://github.com/echris6/motion-video-kit) (MIT; source of 5 `proposed` patterns).

> Language policy: new documentation, CLI help and code comments are written in English. Older docs under `docs/`, `intake/`, `templates/` and client folders are still Portuguese and are translated as they are touched.

## Host

Mapa gerado a partir do front matter de `docs/host/`. A referência da CLI, dos schemas, das tools MCP e das variáveis de ambiente fica em [`docs/reference/`](docs/reference/) (gerada com `make regen`).

<!-- BEGIN GENERATED: host -->
Gerado de `docs/host/*.md` (front matter). Não edite aqui: rode `make regen`.

- [Gate local, TDD e pouso de PRs](docs/host/gate.md): Como provar que a main está verde com um comando offline, a regra de testes primeiro, o ownership por issue e o pouso serializado sem CI.
- [Licenças das dependências](docs/host/licenses.md): Como o gate confere licenças (allowlist MIT, Apache-2.0, BSD, ISC, PSF, MPL-2.0), como adicionar uma exceção justificada, como regerar docs/licenses.md e o que ainda falta (web/).
- [Pacote de operação (install, update, doctor, setup)](docs/host/packaging.md): O que cada subcomando faz, o que o doctor checa, por que a falta de GEMINI_API_KEY é aviso e os limites até as
<!-- END GENERATED -->

