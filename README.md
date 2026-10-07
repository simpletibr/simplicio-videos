# simplicio-videos

**Video plugin for Simplicio Runtime (Simplicio MCP): a deterministic video machine driven by agents.** A user asks for a video; the plugin runs a **deterministic pipeline**: intake questionnaire (with automatic site/Instagram extraction) → brief/spec → sector template → composition from the motion pattern library (HyperFrames) → TTS voice (Gemini, local, cloned voices; cached) → optional footage editing (video-use) → deterministic render. The LLM only decides things (contract, EDL) and creates new templates/patterns; it is never in the render path.

Decisions: [ADR-0001](docs/decisoes/ADR-0001-visao-plugin.md) · [ADR-0002 (CLI + contract + Colab + credits)](docs/decisoes/ADR-0002-cli-contrato-colab-creditos.md) · [ADR-0003 (100% script flow; local render by default)](docs/decisoes/ADR-0003-fluxo-100-script.md) · [ADR-0004 (generative UGC outside the deterministic render)](docs/decisoes/ADR-0004-ugc-generativo.md) · Costs: [docs/custos.md](docs/custos.md) · Outbound sales: [docs/venda-ativa.md](docs/venda-ativa.md) · Manifest: [`plugin.json`](plugin.json) · Skill: [`skills/simplicio-video/SKILL.md`](skills/simplicio-video/SKILL.md)

**Entry point: the `simplicio-video` CLI.** The agent writes the YAML contract ([`schema/contract.schema.json`](schema/contract.schema.json)); the CLI validates it, generates the voice and renders deterministically (local or Colab GPU). Agents (Claude Code, Codex, Grok): start at [`AGENTS.md`](AGENTS.md).

## Apps

Every external tool is a **track** with one CLI command, one MCP verb (`plugin.json`) and one doc. Install and run them yourself; nothing is vendored. All of it is optional except HyperFrames and ffmpeg.

### Video apps

| App | License | Role | CLI command | MCP verb | Doc |
|---|---|---|---|---|---|
| [HyperFrames](https://github.com/heygen-com/hyperframes) | Apache-2.0 | Deterministic HTML/GSAP → MP4 render (core) | `simplicio-video render contract.yaml` | `video.render` | [motion/README.md](motion/README.md) |
| [video-use](https://github.com/browser-use/video-use) | MIT | EDL editing of any MP4 (cuts, reorder, subtitles, review) | `simplicio-video edit setup\|transcribe\|pack\|render\|verify` | `video.edit` | [tools/video-use](tools/video-use/README.md) |
| [OpenMontage](https://github.com/calesthio/OpenMontage) | see repo | Agentic production pipelines (Backlot, Remotion, HyperFrames) | `simplicio-video montage [clone\|open\|serve\|demo]` | `video.montage` | [docs/recursos.md](docs/recursos.md) |
| [OpenCut](https://github.com/OpenCut-app/OpenCut) | MIT | Open-source editor for manual finishing (uses `opencut-classic` until the rewrite has an API) | `simplicio-video opencut clone\|dev\|where` | `video.opencut` | [docs/recursos.md](docs/recursos.md) |
| [Hypit AI](https://github.com/hypit-ai/hypit) | see repo | Clone viral videos into agent workflows | `simplicio-video clone [args]` | `video.clone` | [docs/recursos.md](docs/recursos.md) |

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
├── colab/                  # render.ipynb (GPU) for --backend colab bundles
├── intake/                 # questionnaire, site/IG extraction, intake.schema.json, examples/
├── templates/              # one template per sector (template.json + README)
├── motion/                 # motion pattern library: patterns/<id>/, catalog.json, lib/, scripts/
├── voices/                 # voice providers + TTS pipeline (see Audio apps)
├── tools/                  # optional pinned tools (video-use)
├── ugc/                    # generative UGC track (outside the render): pack.json, prompts/
├── schemas/                # video-spec.schema.json (simplicio.video-spec/v1)
├── docs/                   # ADRs, pipeline, setup, research — index in docs/README.md
└── clients/<client>/       # example videos only: <video>/contract.yaml, preview/, assets
```

## Catalogs

| What | Where | Today |
|---|---|---|
| Motion patterns | [motion/README.md](motion/README.md) | 46 (24 ready blocks with preview, 1 lib, 2 inline, 19 proposed) |
| Sector templates | [templates/README.md](templates/README.md) | 2 ready (repair/games, dentistry) + 6 skeleton |
| Voices | [voices/README.md](voices/README.md) | Gemini (default), Kokoro, VoxCPM2, OpenVoice V2, VoiceStudio |
| Intake | [intake/README.md](intake/README.md) | questionnaire, auto extraction, schema, WJR example |
| Optional tools | [tools/README.md](tools/README.md) | video-use |
| UGC (generative) | [ugc/README.md](ugc/README.md) | 10 characters + 5 prompts |

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
