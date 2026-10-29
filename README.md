# simplicio-videos

> A deterministic video engine driven by agents: a YAML contract in, an MP4 out, and a toolbox for audio, video, voice, character swap, social planning, asset licensing and web research around it.

**Languages:** [English](README.md) · [Português](README.pt-BR.md) · [Español](READMEs/README.es-ES.md) · [Français](READMEs/README.fr-FR.md) · [Italiano](READMEs/README.it-IT.md) · [Polski](READMEs/README.pl-PL.md) · [Русский](READMEs/README.ru-RU.md) · [中文](READMEs/README.zh-CN.md) · [日本語](READMEs/README.ja-JP.md) · [한국어](READMEs/README.ko-KR.md) · [हिन्दी](READMEs/README.hi-IN.md) · [العربية](READMEs/README.ar-SA.md) · [עברית](READMEs/README.he-IL.md) · [Bahasa Indonesia](READMEs/README.id-ID.md) · [Bahasa Melayu](READMEs/README.ms-MY.md)

This README and [README.pt-BR.md](README.pt-BR.md) keep the same sections. The other translations under [`READMEs/`](READMEs/) are shorter summaries and may lag behind this file.

simplicio-videos is the video plugin for Simplicio Runtime. It is used through the `simplicio-video` CLI (with `--json` output), an MCP server, and six agent skills.

## Contents

- [How it works](#how-it-works)
- [Capability map](#capability-map)
- [Command reference](#command-reference)
- [Quick start](#quick-start)
- [Pinned external tracks and licenses](#pinned-external-tracks-and-licenses)
- [Limits and known gaps](#limits-and-known-gaps)
- [Repository map](#repository-map)
- [Tests and documentation](#tests-and-documentation)

## How it works

The agent writes the contract: a YAML file validated by [`contract.schema.json`](src/simplicio_video/data/schema/contract.schema.json). The CLI validates it, generates the narration, renders the video deterministically, and writes a manifest. Same contract, same MP4. No LLM runs in the render path. The default backend is local; the GPU backends (Kaggle, Colab) are opt-in with `--backend`.

Around that core there are tools for audio and video, voice, character swap, social planning, a licensed image and audio library, web research, and wrappers for external tracks. Anything generative (AI voices, swaps, UGC footage) stays outside the deterministic render. Whatever those tools produce enters a contract as a file with a hash.

Decisions: [ADR-0001](docs/decisoes/ADR-0001-visao-plugin.md) (plugin vision) · [ADR-0002](docs/decisoes/ADR-0002-cli-contrato-colab-creditos.md) (CLI, contract, Colab, credits) · [ADR-0003](docs/decisoes/ADR-0003-fluxo-100-script.md) (100% script flow, local render by default) · [ADR-0004](docs/decisoes/ADR-0004-ugc-generativo.md) (generative UGC outside the render).

## Capability map

| Area | Commands | What you get | Status |
|---|---|---|---|
| Contract to MP4 | `init`, `validate`, `voice`, `render`, `run` | Sector template, validation (schema, assets, durations, every line fits), narration per line with cache and `timing.lock.json`, HyperFrames render with the mix at -14 LUFS, manifest, 540x960 watermarked preview | Local render is the default; Kaggle, Colab CLI and the Colab bundle are optional credit backends |
| Voice | `voice`, `voicestudio` | Providers `file`, `local` (Kokoro-82M), `gemini`, `voxcpm` (design or cloning), `openvoice` (timbre conversion), `voicestudio` (local app) | `elevenlabs` and `xai` are stubs (generate elsewhere, then use `file`) |
| Audio and video on any MP4 | `media` | `fetch` (download a public video, with a provenance record), `probe`, `audio`, `sheet`, `subs`, `burn`, `mask`, `replace-audio`, `voice-track` | ffmpeg and ffprobe; `fetch` uses the pinned yt-dlp and needs `--autorizo` |
| Vertical cuts | `shorts` | `inspect`, `plan`, `cut`, `run`: 9:16 clips from a long video, from a word transcript; the plan is a versioned file | ffmpeg only, deterministic |
| EDL editing | `edit` | `setup`, `transcribe` (faster-whisper, local), `pack`, `render`, `verify` | video-use, pinned |
| Templates, motion, formats, angles | `list`, `formats` | 14 sector templates (8 ready, 6 skeleton); 55 motion catalog entries (33 ready, 19 proposed, 2 inline, 1 lib); 50 ad formats; 50 angles in 5 groups | Catalogs |
| Character swap | `swap`, `jobs` | Six adapters: `gemini` (checked against the docs), `fal`, `wavespeed`, `kie`, `alibaba` (UNVERIFIED), `fake` (tests); cost estimate; `--max-usd` cap | Paid; runs only in the terminal, with `--autorizo` and `--yes` |
| Background jobs | `jobs` | `submit`, `status`, `list`, `cancel`, `result`, `clean` for `swap-run` and local `voice` | No daemon, no open port |
| External production tracks | `clone`, `montage`, `opencut`, `toonflow`, `moneyprinter` | Hypit (agentic cloning), OpenMontage (agentic production), OpenCut (manual finishing), Toonflow (drama and comic studio), MoneyPrinterTurbo (topic to short video) | Pinned checkouts, run as separate programs, never imported |
| Social planning | `social` | Providers Real Oficial (default) and Zernio; checks an MP4 against per-network limits; writes a plan; prints the MCP call sequence | **Never posts.** The agent posts with the provider's tools after explicit consent for each post |
| Licensed image and audio library | `openverse` | Search, safe download, per-request review sheet, approval per (asset, sha256, request), export with credits, offline verification of a contract | Licenses come from the sources; not legal advice |
| Web research | `busca` | `consulta`, `pagina`, `status`, `log` through TinyFish, with source and date per result, daily call cap, provenance log | The query goes to a third party; secrets and personal data are refused |
| UGC prompt track | `ugc/` (no CLI) | 10 synthetic characters, 5 prompt files, a 7-step manual pipeline | Generative; outside the render |
| Agent integration | `mcp`, `install`, skills | MCP server with 19 `video.*` tools; 6 skills; `install` copies them into 11 agent hosts | MCP does not yet expose `media`, `shorts`, `tools`, `status`, `doctor` or `install` |
| Operations | `status`, `tools`, `doctor`, `setup`, `update`, `login`, `logout`, `auth` | Tool and render status, pinned tracks, diagnostics, workspace, updates, the shared Simplicio login | The engine never stores a credential |

## Command reference

Run `simplicio-video <command> --help` for every option. Each command also accepts `--json` where the output is data.

### Contract to MP4

```bash
simplicio-video init <cliente> <campanha> --template <id> --nome "<Nome>"   # skeleton contract from a sector template
simplicio-video validate contract.yaml                                       # schema, assets, durations, lines
simplicio-video voice contract.yaml [--provider file|local|gemini|voxcpm|openvoice|voicestudio] [--force]
simplicio-video render contract.yaml [--backend local|kaggle|colab-cli|colab] [--preview] [--out x.mp4]
simplicio-video run contract.yaml --provider gemini                         # voice -> validate -> render, stops at the MP4
```

- `render --preview` makes a 540x960 preview with the watermark and closing credit from the contract (`marca.dagua`, `marca.credito`).
- `render --backend colab` writes a bundle for [`colab/render.ipynb`](colab/README.md) (GPU) instead of rendering here.
- Narration in the render is never time-stretched: a take longer than its slot is an error.

### Voice

```bash
simplicio-video voicestudio status              # app health and GPU
simplicio-video voicestudio voices --json       # saved voice profiles
simplicio-video voicestudio languages           # TTS languages the app offers
simplicio-video voicestudio personalities       # personality presets
simplicio-video voicestudio tts "Olá" -o ola.wav --profile <id> --language pt
simplicio-video voicestudio transcribe audio.m4a [--rest]
simplicio-video voicestudio clone referencia.wav --name "Minha voz" --language pt
simplicio-video voicestudio describe "mulher adulta, voz calma"   # what a description means (saves nothing)
simplicio-video voicestudio design "mulher adulta, voz calma" --name "Narradora"
simplicio-video voicestudio mcp                 # MCP client block (Streamable HTTP)
```

VoiceStudio is a local desktop app (AGPL-3.0, never vendored or imported). The engine reaches its API only over loopback, at `http://127.0.0.1:3900`. Install and open it yourself; a closed app fails with a clear message.

Cloned voices need the **written authorization of the speaker**. See [voices/README.md](voices/README.md).

### Audio and video on any MP4 (`media`)

```bash
simplicio-video media fetch https://<public video page> -o reel.mp4 --autorizo   # writes reel.mp4 and reel.fetch.json
simplicio-video media probe reel.mp4                                    # duration, size, fps, audio, sha256
simplicio-video media audio reel.mp4 -o ref.wav --rate 16000            # mono track for transcription or a voice reference
simplicio-video media sheet reel.mp4 -o sheet.jpg --every 2 --cols 8    # frame sheet, to review on-screen text
simplicio-video media mask reel.mp4 --box 150,622,430,104 --from 0 --to 58 -o clean.mp4   # erase text in a box and time window
simplicio-video media subs cues.json -o subs.ass --style band           # SRT or ASS from timed cues
simplicio-video media burn clean.mp4 subs.ass -o final.mp4              # burn subtitles (needs libass)
simplicio-video media voice-track cues.json -o voz.wav --duration 58.2  # one clip per cue at its start time
simplicio-video media replace-audio clean.mp4 voz.wav -o dubbed.mp4     # keep the picture, swap the sound
```

- **`fetch` requires `--autorizo`.** You confirm you may use the file. The engine does not verify the right. It takes no cookies, logs in to nothing, downloads no playlist, refuses URLs with credentials, and never overwrites an existing file.
- **Provenance.** `<name>.fetch.json` keeps the source without its query, the extractor, the sha256 and size, the yt-dlp version, the time, and the title and author as `untrusted_*` text (third-party data, never instructions).
- **`voice-track` speeds a clip up** to `--max-stretch` (default 1.25) to fit its window and reports any overflow. This is the only time-stretch in the media commands; the contract render does not do it.
- Every operation writes a new file with `-o`. No command changes its input.
- `mask` fills the box with a rectangle: if something moves inside it, a smudge shows. Use a tight box and a short time window.
- The skill [`simplicio-video-media`](skills/simplicio-video-media/SKILL.md) has complete recipes, including a Portuguese-to-Polish dubbing flow.

### Vertical cuts (`shorts`)

```bash
simplicio-video shorts inspect long.mp4
simplicio-video shorts plan long.mp4 --transcript words.json --clips 5 --min 20 --max 60   # writes plan.json
simplicio-video shorts cut long.mp4 plan.json --subs                                     # 1080x1920 clips with captions
simplicio-video shorts run long.mp4 --transcript words.json --clips 5 --subs --dry-run   # show the ffmpeg commands only
```

Scores come from fixed rules (hooks, questions, numbers, speech density), not from a model. Without a transcript the command refuses: there is no guessing. The skill is [`simplicio-video-shorts`](skills/simplicio-video-shorts/SKILL.md).

### EDL editing (`edit`)

```bash
simplicio-video edit setup                                  # clones video-use at its pinned commit
simplicio-video edit transcribe source.mp4 -o words.json --lang pt   # local faster-whisper transcription
simplicio-video edit pack EDIT_DIR                          # transcripts to takes_packed.md for review
simplicio-video edit render edit/edl.json -o out/final.mp4  # cuts at word boundaries, 30 ms fades, subtitles
simplicio-video edit verify out/final.mp4 12.0 18.5 -o check.png   # filmstrip of a cut, for review
```

The agent writes the EDL (`edl.json`); the helpers run ffmpeg. The skill is [`simplicio-video-edit`](skills/simplicio-video-edit/SKILL.md).

### Templates, motion, formats and angles

```bash
simplicio-video list templates        # 14 sector templates: pronto (renderable) or skeleton
simplicio-video list motion           # 55 motion catalog entries
simplicio-video list voices           # voice providers and their state
simplicio-video list angles --grupo prova
simplicio-video formats list          # 50 ad formats from the Drive swipe file
simplicio-video formats show <id>
simplicio-video formats prompt <id> --copia copy.txt   # a prompt that adapts a copy to the format
```

Sector templates: `alimentacao`, `assistencia-tecnica-games`, `beleza-estetica`, `brand-promo`, `imobiliario`, `institucional-advocacia`, `institucional-estetica`, `institucional-odontologia`, `pov-showcase`, `saas-tech`, `saude-clinica`, `saude-odontologia`, `sazonal-dia-das-criancas`, `varejo`. Eight are ready to render. The motion library is in [motion/README.md](src/simplicio_video/data/motion/README.md) and the templates in [templates/README.md](src/simplicio_video/data/templates/README.md).

### Character swap and background jobs (`swap`, `jobs`)

```bash
simplicio-video swap providers                                   # adapters, capabilities, price in US$ and R$, confidence
simplicio-video swap estimate --provider gemini --video in.mp4 --ref avatar.png
simplicio-video swap run --provider gemini --video in.mp4 --ref avatar.png --out out/swap.mp4 --autorizo              # dry run: estimate only
GEMINI_API_KEY=... simplicio-video swap run ... --autorizo --yes --max-usd 2                                         # spends, with a cap
simplicio-video swap status out/swap.manifest.json
simplicio-video jobs submit swap-run ... --autorizo --yes       # runs in a separate process; returns at once
simplicio-video jobs status|list|result|cancel|clean <id>
```

`--autorizo` confirms you have rights over the video and the images. Without `--yes` nothing is sent. `--max-usd` aborts before submitting. Keys come only from the provider's environment variable. Only `gemini` was checked against its documentation; `fal`, `wavespeed`, `kie` and `alibaba` are **UNVERIFIED** and need `--aceito-unverified` to spend. The MCP tool `video.swap` only lists providers and estimates; spending is terminal-only.

Segments run in parallel with `--concurrency` (default 3 for swap, 4 for network voices). Asyncio is used only where the code waits on the network; rendering and ffmpeg stay serial.

### Social planning, without posting (`social`)

```bash
simplicio-video social providers                                  # Real Oficial (default) and Zernio: MCP tools, limits, gaps
simplicio-video social plan --video out/final.mp4 --caption-file legenda.txt --target tiktok=@conta --target youtube \
    [--at 2026-10-20T09:30 --timezone America/Sao_Paulo] [--title "..."] [--ai-generated]   # writes social.plan.json
simplicio-video social check out/social.plan.json                 # is the video still the one in the plan?
simplicio-video social recipe out/social.plan.json [--provider zernio] [--clip-id ID]   # the MCP call sequence
```

`plan` refuses a missing file or a non-MP4 and checks duration, aspect ratio, size, caption, title and hashtags against [`limits.json`](src/simplicio_video/data/social/limits.json). Only the YouTube Shorts duration limit was confirmed on the official page; the rest is **UNVERIFIED** and needs `--aceito-unverified`. The engine never stores a key or token. The MCP tool `video.social` offers `providers`, `plan`, `check` and `recipe`, and has no publish action. Read [ADR-0018](docs/decisoes/ADR-0018-social-planejar-sem-postar.md) and the skill [`simplicio-video-social`](skills/simplicio-video-social/SKILL.md).

### Licensed image and audio library (`openverse`)

```bash
simplicio-video openverse search --tipo imagem --consulta "sunrise over the sea" --minimo-largura 1280 --limite 10
simplicio-video openverse search --tipo audio --consulta "rain" --duracao-min 20 --duracao-max 90 --json
simplicio-video openverse get <id>                                    # safe download into the local library
simplicio-video openverse library review <id> --pedido "<what the scene needs>" --folha     # the review sheet
simplicio-video openverse library review <id> --pedido "<same>" --aprovar --motivo "..." --por "<reviewer>"
simplicio-video openverse library export <id> --pedido "<same>" --contrato clients/acme/video-01/contract.yaml
simplicio-video openverse library verify clients/acme/video-01/contract.yaml   # offline check of declared assets
simplicio-video openverse library credits | list | show <id>
```

- **Review per request.** An approval covers one exact trio: asset id, file sha256, and the normalized request. Approving for request A does not cover request B, and a new file invalidates old approvals.
- **Licenses.** The default is `cc0,pdm,by`. Share-alike and non-commercial licenses need an explicit `--licencas`. Any restricted license (`nc`, `nd`, `sa`) needs `--aceito-restricao` at export. Items without a known license are never downloaded, and CC BY items without an author are never exported. Licenses come from the sources; this is not legal advice.
- **Contract gate.** A contract asset can declare `openverse: {id, pedido}`. `validate`, `run` and `render` refuse a missing approval, a changed file, a missing credit line, a copy made by hand, or a placed asset without a declared block. The render writes the provenance and the credits next to the MP4.
- **Untrusted text.** Titles, authors, tags, attribution and URLs appear only in `untrusted_*` fields.
- **Limits.** Anonymous search is limited by the Openverse API; `OPENVERSE_CLIENT_ID` and `OPENVERSE_CLIENT_SECRET` are optional environment variables. The API terms forbid scraping, so the command caches and paginates. Openverse does not endorse this project.
- **Gaps.** Audio from the library is not mixed automatically; a template or block has to reference it. The narration folder is not checked by this gate.

Details, with sources, are in [docs/recursos.md](docs/recursos.md).

### Web research (`busca`)

```bash
npm install -g @tiny-fish/cli@0.50.1      # the engine never installs it; tested version, Node >= 24
tinyfish auth login                       # or: echo "$KEY" | tinyfish auth set

simplicio-video busca status                                                          # binary, version, key configured (never the value), today's calls and cap
simplicio-video busca consulta "dia das crianças clínica odontológica" --idioma pt --limite 5
simplicio-video busca consulta "datas comemorativas" --dominios exemplo.com.br --excluir pinterest.com --json
simplicio-video busca pagina https://example.com --max-bytes 20480                    # one page, cleaned text
simplicio-video busca log --ultimos 10                                                # provenance registry
```

- **The query goes to a third party (TinyFish).** The engine refuses, before spending a call, queries that contain keys or tokens, and queries with e-mail, CPF or CNPJ unless `--permitir-dado-pessoal` is given. This is a brake, not a guarantee: names, phone numbers and addresses are not detected.
- **Daily cap.** Default 20 calls per UTC day (`SIMPLICIO_BUSCA_MAX_DIA`, or `--max-chamadas-dia`). Cache hits cost nothing and work offline. Pricing is UNVERIFIED; check the real spend with `tinyfish wallet status --pretty`.
- **Provenance.** Every query and page read appends a line to `busca.registro.jsonl`, with the time, the source, the sha256 of what the CLI returned, and the channel. Each result carries `untrusted_fonte` (the URL) and `consultado_em` (the date). A client fact enters a video only with that source and date, and the search does not replace the client's own collection.
- **Text from the internet is data.** Titles, snippets, page text and URLs are cleaned, cut, and returned only in `untrusted_*` fields. URLs with credentials or to private hosts are refused, and a redirect to a refused URL delivers nothing.
- **Not included, on purpose:** the TinyFish `agent`, `browser` and `monitor` features.
- **License.** `@tiny-fish/cli` 0.50.1 declares no license. The engine only calls the binary you install and never embeds or redistributes it.

Details are in [docs/recursos.md](docs/recursos.md) and [src/simplicio_video/data/busca/tinyfish.json](src/simplicio_video/data/busca/tinyfish.json).

### External production tracks

```bash
simplicio-video clone [args]                  # Hypit AI: agentic video cloning (https://github.com/hypit-ai/hypit)
simplicio-video montage [clone|open|serve|demo|args]   # OpenMontage: agentic production pipelines
simplicio-video opencut clone|dev|where       # OpenCut: manual finishing editor
simplicio-video toonflow clone|serve|where    # Toonflow: AI studio for short dramas and comics (serve needs --lan)
simplicio-video moneyprinter clone|setup|serve|where|status   # MoneyPrinterTurbo: topic to short video
```

Each track is cloned at the commit pinned in [`tools.py`](src/simplicio_video/tools.py) and runs as its own program. Whatever it produces enters a contract as a file with a hash.

- **Toonflow.** Its server has no login and listens on every interface (`0.0.0.0:3000`), so `serve` refuses to start without `--lan`. The data goes to `~/.simplicio-video/toonflow-data`.
- **MoneyPrinterTurbo.** It calls third-party services (an LLM, a TTS service, stock footage) with **your own** keys, in its WebUI or `config.toml`. The engine never prints them. `serve` binds to `127.0.0.1` unless you pass `--lan`.
- **VoiceStudio and video-use** are covered above (voice and EDL editing).

### Agent integration: MCP, skills and install

```bash
simplicio-video mcp                  # MCP server over stdio (install with pip install -e .[mcp])
simplicio-video install [--global] [--check|--dry-run] [--json] [--verify] [--uninstall]
simplicio-video install --global     # copy the six skills into every agent host it knows (11 hosts)
```

The MCP server exposes 19 tools: `video.init`, `video.validate`, `video.voice`, `video.render`, `video.run`, `video.list`, `video.clone`, `video.montage`, `video.edit`, `video.opencut`, `video.formats`, `video.swap`, `video.jobs`, `video.social`, `video.openverse`, `video.voicestudio`, `video.busca`, `video.toonflow` and `video.moneyprinter`. Several of them are read-only or deliberately limited: `video.swap` estimates but does not spend, `video.social` never publishes, `video.openverse` cannot download or export, and `video.jobs` submits only local voice. The manifest is [`plugin.json`](plugin.json).

The six skills, in [`skills/`](skills/):

| Skill | For |
|---|---|
| [`simplicio-video`](skills/simplicio-video/SKILL.md) | writing the contract and running the render |
| [`simplicio-video-media`](skills/simplicio-video-media/SKILL.md) | audio and video on any MP4, downloads with `fetch` |
| [`simplicio-video-voicestudio`](skills/simplicio-video-voicestudio/SKILL.md) | local voice through the VoiceStudio app |
| [`simplicio-video-shorts`](skills/simplicio-video-shorts/SKILL.md) | vertical cuts from a long video |
| [`simplicio-video-edit`](skills/simplicio-video-edit/SKILL.md) | EDL editing with video-use |
| [`simplicio-video-social`](skills/simplicio-video-social/SKILL.md) | planning social posts, with the provider's tools |

### Operations

```bash
simplicio-video status [--json] [contract.yaml]   # installed tools, pinned versions, render state
simplicio-video tools [--json]                    # every pinned external track
simplicio-video doctor [all|login] [--json] [--online]   # login, update, runtime, Python, Node 22, ffmpeg with libass, disk, ports, workspace
simplicio-video setup                             # first run: workspace, theme, language, L1 autonomy, zero budgets
simplicio-video update [--check|--dry-run] [--force]     # PyPI; a git checkout refuses and tells you to git pull
simplicio-video login [--json] [--no-browser]     # the shared Simplicio login (same as the Runtime); stores no credential
simplicio-video logout | auth status
```

## Quick start

```bash
gh repo clone simpletibr/simplicio-videos && cd simplicio-videos
pip install -e .                      # `simplicio-video` command (Python >= 3.10); rendering needs Node >= 22 and ffmpeg
simplicio-video setup                 # first run
simplicio-video install               # copy the skills into your agent host (project; --global for the home folder)
simplicio-video doctor                # check what is missing

cd clients/<cliente>/<campanha>       # a client project with a contract.yaml
simplicio-video validate contract.yaml
simplicio-video voice contract.yaml   # narration; local draft voice or --provider file|gemini|voxcpm|openvoice|voicestudio
simplicio-video render contract.yaml  # out/<cliente>-<campanha>.mp4 + render.manifest.json
```

A cloned voice in the contract (VoxCPM2 example):

```yaml
voz:
  provider: voxcpm
  providers:
    voxcpm:
      reference_audio: assets/audio/ref/speaker.wav   # authorized speaker, clean 10-30 s
      reference_text: "Exact transcript of the clip."  # optional
      control: "warm, slightly faster"                 # optional style
      seed: 42
```

Windows: `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\dev_install.ps1` (not yet confirmed on a real machine). The checkout's environment: `bash scripts/dev_install.sh`.

## Pinned external tracks and licenses

Every version is pinned in [`src/simplicio_video/tools.py`](src/simplicio_video/tools.py). `simplicio-video tools` lists them.

| Track | Command | Pinned | License | Role |
|---|---|---|---|---|
| [OpenMontage](https://github.com/calesthio/OpenMontage) | `montage` | commit `9327439` | AGPL-3.0 | agentic production pipelines |
| [OpenCut](https://github.com/OpenCut-app/opencut-classic) | `opencut` | commit `cf5e79e` | MIT | manual finishing editor (archived upstream) |
| [Hypit](https://www.npmjs.com/package/@hypit/hypit) | `clone` | npm `0.2.17` | Hypit license (modified Apache-2.0); no commercial redistribution | agentic cloning, user-installed |
| [Toonflow](https://github.com/HBAI-Ltd/Toonflow-app) | `toonflow` | commit `d2e94ac` | MIT | AI studio for dramas and comics |
| [MoneyPrinterTurbo](https://github.com/harry0703/MoneyPrinterTurbo) | `moneyprinter` | commit `4b7b965` | MIT | topic to short video |
| [TinyFish CLI](https://www.npmjs.com/package/@tiny-fish/cli) | `busca` | npm `0.50.1` | not declared | web search and page reading |
| [VoiceStudio](https://github.com/debpalash/VoiceStudio) | `voicestudio` | commit `beeaae0` (v0.5.7) | AGPL-3.0 | local voice app, used over HTTP only |
| [video-use](https://github.com/browser-use/video-use) | `edit` | commit `b877063` | MIT | EDL editing |
| [yt-dlp](https://github.com/yt-dlp/yt-dlp) | `media fetch` | PyPI `2026.10.26`, sha256 checked | Unlicense | downloads one public video page |

The engine never vendors or imports these tracks. The deterministic render does not depend on any of them.

## Limits and known gaps

- **MCP coverage.** `media`, `shorts`, `tools`, `status`, `doctor` and `install` are CLI-only for now. The engine's own rule is to expose each capability over the CLI and, where it fits, over MCP.
- **Unverified swap adapters.** `fal`, `wavespeed`, `kie` and `alibaba` were written from public documentation and have not been checked against the live APIs.
- **Voice.** `elevenlabs` and `xai` are stubs. VoiceStudio needs its app running.
- **Downloads.** Platforms restrict downloads in their own terms; that responsibility is the user's. A page can also arrive cut short, in which case `fetch` fails and writes nothing.
- **No publishing.** The engine never posts or uploads to a social network. The `publish` command was removed from the engine (#77).
- **Mask and voice track.** `mask` leaves a rectangle if something moves inside the box. `voice-track` does not translate or clone.
- **Platforms.** The package is classified for Linux; macOS and Windows are not confirmed on real machines.
- **UGC.** The `ugc/` folder is a manual, generative pipeline with no CLI command; its output is not reproducible byte by byte.

## Repository map

```
simplicio-videos/
├── AGENTS.md / CLAUDE.md   # rules, map and flows for agents (CLAUDE.md → AGENTS.md)
├── plugin.json             # simplicio.plugin/v1: the video.* verbs and the skill
├── pyproject.toml          # Python package of the CLI (src/simplicio_video/); tests in tests/
├── src/simplicio_video/    # the engine: cli.py, media.py, shorts.py, download.py, tools.py, voicestudio.py, swap, social, openverse, busca …
├── skills/                 # the six SKILL.md files, shipped in the wheel
├── schemas/                # video-spec.schema.json (simplicio.video-spec/v1)
├── intake/                 # questionnaire, site and Instagram extraction, examples
├── templates/              # one template per sector (see src/simplicio_video/data/templates/)
├── motion/                 # motion pattern library: patterns/<id>/, catalog.json, scripts/
├── voices/                 # voice providers and the TTS pipeline
├── tools/                  # optional pinned tools (video-use)
├── ugc/                    # generative UGC track, outside the render: pack.json, prompts/
├── colab/                  # render.ipynb (GPU) for --backend colab bundles
├── docs/                   # ADRs, pipeline, setup, reference (docs/reference is generated); index in docs/README.md
└── clients/<client>/       # example videos only: <video>/contract.yaml, preview/, assets
```

<!-- BEGIN GENERATED: host -->
Gerado de `docs/host/*.md` (front matter). Não edite aqui: rode `make regen`.

- [Gate local, TDD e pouso de PRs](docs/host/gate.md): Como provar que a main está verde com um comando offline, a regra de testes primeiro, o ownership por issue e o pouso serializado sem CI.
- [Licenças das dependências](docs/host/licenses.md): Como o gate confere licenças (allowlist MIT, Apache-2.0, BSD, ISC, PSF, MPL-2.0), como adicionar uma exceção justificada, como regerar docs/licenses.md e o que ainda falta (web/).
- [Pacote de operação (install, update, doctor, setup)](docs/host/packaging.md): O que cada subcomando faz, o que o doctor checa, por que a falta de GEMINI_API_KEY é aviso e os limites até as
<!-- END GENERATED -->

## Tests and documentation

Tests: `PYTHONPATH=src python -m pytest`. Tests that need network or a real tool are marked `integration`; `make check` leaves them out. The library previews: `bash motion/scripts/preview.sh && node motion/scripts/catalog.mjs`.

Index: [`docs/README.md`](docs/README.md). Curated video and motion tools, with stars and licenses: [`docs/recursos.md`](docs/recursos.md). Reference for the CLI, schemas, MCP tools and environment variables: [`docs/reference/`](docs/reference/) (generated with `make regen`).

Also built on [video-shotcraft](https://github.com/Vincentwei1021/video-shotcraft), [awesome-opus5-5-videos](https://github.com/yihui-dev/awesome-opus5-5-videos) (recipes distilled into `motion/`) and [motion-video-kit](https://github.com/echris6/motion-video-kit) (MIT; source of 5 `proposed` patterns). External reference: [Skillry — viral videos made with Claude Opus 5.5](https://skillry.dev/ai-videos/opus-5-5).

> Language policy: new documentation, CLI help and code comments are written in English. Older docs under `docs/`, `intake/`, `templates/` and client folders are still Portuguese and are translated as they are touched.
