# simplicio-videos

> A deterministic video engine: a YAML contract goes in, an MP4 and a manifest come out. Same input, same output.

**Languages:** [English](README.md) · [Português](README.pt-BR.md)

## What it is and who it is for

simplicio-videos is the video plugin of Simplicio Runtime. A person or an agent writes the script as a YAML contract (scenes, lines, brand, soundtrack). The `simplicio-video` CLI validates the contract, generates the voice, renders with HyperFrames, and writes a manifest of what was done. No LLM runs in the render path.

Who it is for: people who make ads and short videos with voice, subtitles, and cuts, and agents (Claude Code, Codex, and others) that need video tools with verifiable output, through the CLI or the MCP server.

## Capability map

| What you want to do | Command | Status | Cost or limit |
|---|---|---|---|
| Make an MP4 from a contract | `init`, `validate`, `voice`, `render`, `run` | 8 ready templates (`list templates`); 6 skeleton templates that do not render | Local. The render uses ffmpeg and HyperFrames (Node) |
| Voice | `voice --provider` | `file`, `local`, `gemini`, `voxcpm`, `openvoice`, `voicestudio`; `elevenlabs` and `xai` are stubs | `gemini` needs an API key; `voxcpm` needs an authorized voice reference |
| Media on any MP4 | `media probe`, `audio`, `sheet`, `subs`, `burn`, `mask`, `replace-audio`, `voice-track` | Ready (ffmpeg and ffprobe) | `burn` needs an ffmpeg built with libass |
| Download a public video | `media fetch` | Ready | Needs `--autorizo`. Uses a pinned yt-dlp, installed on demand |
| 9:16 vertical cuts | `shorts` | Ready | ffmpeg only, deterministic |
| EDL editing | `edit` | Ready (pinned video-use) | Local transcription with faster-whisper |
| Character swap | `swap`, `jobs` | Ready | Spends credits. Terminal only, with `--autorizo --yes` |
| Social planning | `social` | Ready | Never posts. Publishing belongs to another layer |
| Openverse library | `openverse` | Ready | Review per request. The license comes from the source |
| Web research | `busca` | Ready | Needs TinyFish and a key. Daily call cap |
| External tracks | `montage`, `opencut`, `clone`, `toonflow`, `moneyprinter`, `matchcut`, `instagram`, `social-research`, `last30days`, `edit`, `rea-video`, `video-to-skill` | Installed on demand, pinned version | Licenses differ; see the tracks table |
| Instagram agent skills and scripts | `instagram` | Ready on the pinned commit; installs on demand. The six scripts ran for real; no agent was run with the skills | Local, no key, no LLM. The heuristics are in English and score Portuguese badly. It never posts |
| Social media research agent skills | `social-research` | Ready on the pinned commit; installs on demand. The skills were not run with an agent here | The skills call ScrapeCreators (paid, your key) from the agent; the engine only downloads, lists and reads them. It never posts |
| Last 30 days research agent skill | `last30days` | Ready on the pinned commit; installs on demand. The skill was not run with an agent here | The skill (run from the agent) needs Python 3.12+, may read browser cookies for X and calls paid third parties with your keys; the engine only downloads and reads the SKILL.md. It never posts |
| Video to agent skill | `video-to-skill` | New. Ready on the pinned release (tag v0.3.0); `clone` and `setup` install on demand. The extractor ran for real on a synthetic 4 s clip; no real tutorial was processed | Local. The extractor is a downloaded binary checked by sha256. Transcription needs voice models that only you download. Verifying a generated skill is not covered by the engine's guarantees |
| Reverse-engineer a reference video | `rea-video` | Ready on the pinned commit; installs on demand. A synthetic clip was tested end to end, real footage was not | Local by default. With `--vlm`, frames go to a vision model you configure |
| MCP server | `simplicio-video-mcp` | 34 `video.*` tools | No `swap run` spending, no software removal |
| Audio cleanup | not available yet | In a PR, not on main yet | not applicable |
| Dubbing with preserved background | `voicestudio dub create` and `dub-export` | Uploads the video to the app and exports the finished job, with music and effects, provided background separation was on in the app | The dub itself runs in the app |

### Numbers from the code

<!-- BEGIN GENERATED: fatos -->
Counts generated from the code (`scripts/gen_reference.py`); where hand-written text elsewhere says another number, these are the ones read from the code. Do not edit here: run `make regen`.

| Fact | Value |
|---|---|
| MCP tools (`video.*`) | 34 |
| External tracks | 15 |
| Templates | 15: 8 `pronto`, 7 `skeleton`; 6 without `composicao` (do not render) |
| Motion patterns | 56: 33 `pronto`, 20 `proposto`, 2 `inline`, 1 `lib` |
| HyperFrames | `hyperframes@0.8.97` |
| Agent hosts (`install`) | 12: `aider`, `antigravity`, `claude`, `codex`, `cursor`, `gemini`, `grok`, `kiro`, `openclaw`, `opencode`, `simplicio_agent`, `vscode` |
| Hosts with a global skills folder (`install --global`) | 11: `agents`, `amp`, `claude`, `codex`, `copilot`, `cursor`, `grok`, `kiro`, `opencode`, `simplicio_agent`, `vscode` |
| Skills for agents | 10 |

| Track | Kind | Pin |
|---|---|---|
| `openmontage` | git | `9327439` |
| `opencut` | git | `cf5e79e` |
| `hypit` | npm | `0.3.1` |
| `toonflow` | git | `d2e94ac` |
| `moneyprinter` | git | `4b7b965` |
| `matchcut` | git | `b51c98f` |
| `instagram` | git | `d03c56b` |
| `social_research` | git | `64ba7b4` |
| `last30days` | git | `07021dc` |
| `voicestudio` | git | `beeaae0` |
| `video-use` | git | `b877063` |
| `tinyfish` | npm | `0.57.0` |
| `yt-dlp` | pip | `2026.10.26` |
| `rea_video` | git | `36e02dd` |
| `video_to_skill` | git | `c1a1b90` |
<!-- END GENERATED -->

## Installation

### Prerequisites

- **Python 3.10 or newer.** Tested with Python 3.14.6 on macOS. `doctor` warns that the CrewAI extras require Python below 3.14.
- **Node 22 or newer** for the render (HyperFrames). `doctor` checks it. Tested with Node 26.8.2.
- **ffmpeg built with libass** for `media burn`. `doctor` checks both. Tested: `doctor` reports when ffmpeg does not respond.

### Steps

Tested in a clean venv on macOS:

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[mcp]"                    # the mcp extra is only needed for the MCP server
simplicio-video --version                  # simplicio-video 0.5.0
simplicio-video setup --yes --lang pt-BR   # creates the workspace; does not log in
simplicio-video doctor                     # shows what is missing; reports "fail" when ffmpeg does not respond
```

Not verified: `scripts/dev_install.sh` (Linux and macOS) and `scripts/dev_install.ps1` (Windows). I did not test them on either platform.

### External tracks

There is no separate install command. Each track is installed into the cache (`SIMPLICIO_TOOLS_DIR`, default `~/.simplicio-video/tools`) the first time a command needs it. Tested: `yt-dlp` was installed this way, in its own venv inside the cache.

`simplicio-video tools` lists the tracks and says whether each one is installed. It installs nothing.

### Agent skills

`simplicio-video install --target <folder> --dry-run` shows what would be copied to the host, without writing anything. Tested with the `claude` host. The real copy has not been verified.

## First use

### Contract to MP4

```bash
simplicio-video init my-brand campaign-1 --template brand-promo --nome "My brand"
simplicio-video validate clients/my-brand/campaign-1/contract.yaml
```

- `init` generates the contract with placeholder fields to fill. Tested.
- `validate` lists what is still missing: each unfilled field and what the template requires. Tested.
- Not verified: `voice` and `run`/`render`. They need a filled contract and a working ffmpeg and Node, which I could not test on this macOS check.

### Media

```bash
simplicio-video media probe reel.mp4
simplicio-video media subs cues.json -o subs.ass --style band
simplicio-video media burn clean.mp4 subs.ass -o final.mp4
```

Not verified: all three. The ffmpeg on this Mac does not run. The examples come from `simplicio-video media --help`. `burn` needs libass.

### Web research

```bash
simplicio-video busca status
simplicio-video busca consulta "research topic" --idioma pt --limite 5
```

- `busca status` tested: shows the binary, whether the key is set (without showing its value), and the daily cap. It spends nothing.
- `busca consulta` not verified. It spends one call from the daily cap and needs the `TINYFISH_API_KEY` key.

### Openverse

```bash
simplicio-video openverse --help
simplicio-video openverse search "term"
```

- `openverse --help` tested. `openverse search` not verified: it queries the public Openverse API.
- An asset goes into a video only after someone approves that asset for that request.

### Audio cleanup

Not on main yet. This section gets the commands when the audio cleanup PR is merged.

## MCP

- Server: `simplicio-video-mcp` (stdio). Tested: it answers `initialize` and lists 34 `video.*` tools over the stdio protocol, `video.rea-video`, `video.video-to-skill` and `video.instagram` among them.
- Tool list: [docs/reference/mcp-tools.md](docs/reference/mcp-tools.md).
- **Excluded on purpose, for safety:**
  - `swap run`: spends credits;
  - `install --uninstall` and `--prune-project-copies`: remove software;
  - `montage` with subcommands other than `clone`, `doctor`, `hyperframes-doctor`, `preflight`, `status`, the registry reads, and `run-tool` (only the four reviewed tools, as a job);
  - `auth` with an action other than `status`.
  - Source: `src/simplicio_video/mcp_server.py`.
- **Clients:** the Claude Code and Codex configuration was not verified. `claude` is installed on this Mac, but I did not run `claude mcp add` so as not to change its configuration. Codex is not installed.

### Agent hosts

<!-- BEGIN GENERATED: host -->
Gerado de `docs/host/*.md` (front matter). Não edite aqui: rode `make regen`.

- [Gate local, TDD e pouso de PRs](docs/host/gate.md): Como provar que a main está verde com um comando offline, a regra de testes primeiro, o ownership por issue e o pouso serializado sem CI.
- [Licenças das dependências](docs/host/licenses.md): Como o gate confere licenças (allowlist MIT, Apache-2.0, BSD, ISC, PSF, MPL-2.0), como adicionar uma exceção justificada, como regerar docs/licenses.md e os limites do scan.
- [Pacote de operação (install, update, doctor, setup)](docs/host/packaging.md): O que cada subcomando faz, o que o doctor checa, por que a falta de GEMINI_API_KEY é aviso e os limites atuais.
- [Trabalho em paralelo (acordo para humanos e agentes)](docs/host/parallel-work.md): Como várias issues andam ao mesmo tempo sem quebrar a main: testes primeiro, posse de caminhos por issue, o gate sem CI e o pouso serializado. A página está em inglês e vem do spec da fábrica (arquivo/docs/factory/).
<!-- END GENERATED -->

## Troubleshooting

| Symptom | Likely cause | What to do |
|---|---|---|
| `ffmpeg não respondeu à versão` in `doctor` | Broken ffmpeg. Seen on this Mac: `Library not loaded: libvpx` | Reinstall ffmpeg and run `doctor` again. The reinstall command is not verified |
| `sem ffmpeg não há como checar o libass` | ffmpeg missing, or built without libass | Install an ffmpeg with libass. `media burn` fails without it |
| A track shows as not installed | Empty cache | Run the command that uses the track. `simplicio-video tools` shows the state |
| `fetch: confirme que você pode usar este vídeo com --autorizo` | Authorization not given | Pass `--autorizo` only after confirming you may use the video. Without the flag nothing is downloaded (tested) |
| `template: X has no 'composicao'` | Skeleton template | Pick a ready template (`simplicio-video list templates`) |
| `still has a placeholder` in `validate` | Contract generated but not filled in | Fill the placeholders only with collected facts |
| Python 3.14 warning in `doctor` | CrewAI extras | Use a Python below 3.14 if you need those extras. Not verified |
| `testada: 0.57.0` in `busca status` | TinyFish at another version | The engine keeps working; the tested version is 0.57.0 |
| `aviso: o extra ocr não instalou` in `rea-video setup` | `rapidocr-onnxruntime` has no release for this Python (3.13 here; 3.11 works) | Delete the venv folder in `~/.simplicio-video/rea-video-data`, then run `REA_VIDEO_PYTHON=python3.11 simplicio-video rea-video setup`. Without OCR the analysis still runs |

## Incorporated projects (external tracks)

The engine does not import any of these projects. Each one runs as a separate program, installed on demand at a pinned version: a commit (git), an npm version (Hypit, TinyFish), a PyPI version with a sha256 (yt-dlp), or a release binary checked by sha256 (video-to-skill); the versions are in the licenses table below. Two exceptions: you install the TinyFish CLI yourself, and you open the VoiceStudio app. The `simplicio-video` CLI calls each one; many commands accept `--json`; and the MCP server exposes each one up to the point stated in its entry. No engine command posts or publishes. To see the state on your machine, run `simplicio-video tools` (installed or not, pinned version, license) or `simplicio-video status --json`, which lists all fifteen tracks.

Which track answers each request (a table of request, track, command, MCP tool and limits) and how to chain two or more is in the skill [`simplicio-video-trilhas`](skills/simplicio-video-trilhas/SKILL.md), written in Portuguese like the other skills.

| Project | License | Command | MCP |
|---|---|---|---|
| [OpenMontage](https://github.com/calesthio/OpenMontage) | AGPL-3.0 | `montage` | `clone`, `doctor`, `hyperframes-doctor`, `preflight`, `status`, the registry reads, and `run-tool` for four reviewed tools, as a job |
| [OpenCut](https://github.com/OpenCut-app/opencut-classic) (opencut-classic) | MIT | `opencut` | `clone`, `status`, `where`, `help` |
| [Hypit AI](https://github.com/hypit-ai/hypit) | Hypit license (modified Apache-2.0) | `clone` | closed list of commands and of `media` |
| [Toonflow](https://github.com/HBAI-Ltd/Toonflow-app) | MIT | `toonflow` | `status`, `mcp`, `where`, `clone` |
| [MoneyPrinterTurbo](https://github.com/harry0703/MoneyPrinterTurbo) | MIT | `moneyprinter` | `where`, `clone`, `status`, and `generate` and `run` as a job |
| [match-cut](https://github.com/Sac-Y/match-cut) | MIT | `matchcut` | `where`, `status`, `run` (seven scripts, absolute paths) |
| [instagram-agent-skill](https://github.com/Jakeschincariol/instagram-agent-skill) | MIT | `instagram` | `skills`, `skill NAME`, `where`, `status`, `run` |
| [social-media-research-skills](https://github.com/wesleysimplicio/social-media-research-skills) | MIT | `social-research` | `skills`, `skill NAME`, `where`, `status` |
| [last30days-skill](https://github.com/mvanhorn/last30days-skill) | MIT | `last30days` | `skill`, `where`, `status` |
| [VoiceStudio](https://github.com/debpalash/VoiceStudio) | AGPL-3.0 (local HTTP only) | `voicestudio` | all subcommands; absolute new outputs |
| [video-use](https://github.com/browser-use/video-use) | MIT | `edit` | all except `transcribe-batch`; absolute outputs |
| [rea-video](https://github.com/JuneYaooo/rea-video) | MIT (declared in `pyproject.toml`) | `rea-video` | `where`, `status`, `clone`, `summary`, `probe`, `tiles`, `review`, `apply-review`, `remake-plan`; `decompose` and `stems` as a job |
| [video-to-skill](https://github.com/brenoepics/video-to-skill) | MIT | `video-to-skill` | `status`, `where`, `check`, `skill`, `frame-at`, `clip`, `compile`, `merge --dry-run`; `extract` of a local file as a job |
| [yt-dlp](https://github.com/yt-dlp/yt-dlp) | Unlicense | `media fetch` | `fetch` only with `--autorizo`; `--info` open |
| [TinyFish CLI](https://www.npmjs.com/package/@tiny-fish/cli) | not declared in the package | `busca` | `consulta`, `pagina`, `status`, `log` |

### OpenMontage (`montage`)

[calesthio/OpenMontage](https://github.com/calesthio/OpenMontage) · AGPL-3.0

Agentic video production: pipelines and tools from OpenMontage (the Backlot interface), running as a separate program. `montage setup` creates the venv with the dependencies (needs network). `pipelines`, `tools`, `envelope`, and `estimate` read the registry; `estimate` shows cost and time without running the tool. `run-tool` runs one registry tool through the engine.

- **Command:** `montage setup [--remotion] [--piper]`, `montage status --json`, `montage pipelines list|show NAME`, `montage tools list [--runtime R]|info NAME`, `montage envelope [--full]`, `montage estimate NAME --input '{}'`, `montage run-tool NAME --input JSON [--yes] [--timeout SEC]`, `montage clone [folder]`, `montage open` (default), `montage serve --port 8000`, `montage doctor`, `montage demo`.
- **`run-tool` in the terminal:** runs any tool. Anything that is not local, costs money, has an unknown cost, or needs the network requires `--yes`, after the estimate. The publishing tool never runs.
- **MCP:** `clone` (default folder), `doctor`, `hyperframes-doctor`, `preflight`, `status`, and the reads `pipelines`, `tools`, `envelope`, and `estimate` (`estimate` takes `input` as an object; `status` skips the live probes; `envelope` comes summarized without `--full`). `run-tool NAME` with `input` becomes a background job (follow it with `video.jobs`), only for the four tools reviewed in the code, which are local, free, and offline: `video_trimmer` (only `cut` and `speed`), `audio_probe`, `frame_sampler`, and `scene_detect`. Anything else is refused.
- **Terminal only:** `setup` (installs packages with pip and npm), `open`, `serve`, and `demo` (they start an interface that never ends, or render with the pipelines), `clone` with a folder (the agent does not choose where the checkout is written), `run-tool` for a tool outside that list or one that asks for `--yes`, and any other argument, which runs Python code chosen by the caller.
- **Example:** `simplicio-video montage pipelines list --json`

### OpenCut (`opencut`)

[OpenCut-app/opencut-classic](https://github.com/OpenCut-app/opencut-classic) · MIT

A browser video editor for manual finishing of an MP4 the CLI already made. It uses opencut-classic, which is archived upstream, because the OpenCut rewrite has no API yet. Needs Bun.

- **Command:** `opencut clone [folder]`, `opencut dev [--lan]`, `opencut status [--json]`, `opencut where`.
- **`dev`:** runs `bun install` and starts the editor on port 3000. It listens only on 127.0.0.1; `--lan` opens 0.0.0.0, and the whole network can reach the editor with no login in front. It creates `apps/web/.env.local` (0600) if missing, with a random secret and inert placeholders for the required variables; it never overwrites an existing file.
- **MCP:** `clone` (default folder), `status` (checkout, pin, bun, node_modules, `.env.local`, and port; no values), and `where`.
- **Terminal only:** `dev` (a server that never ends) and `clone` with a folder.
- **Example:** `simplicio-video opencut dev` (stays up until Ctrl+C).

### Hypit AI (`clone`)

[hypit-ai/hypit](https://github.com/hypit-ai/hypit) · npm package `@hypit/hypit` · Hypit license (modified Apache-2.0): forbids commercial redistribution and multi-tenant service without written permission. The engine does not bundle it.

Agentic video cloning. `simplicio-video clone` passes its arguments to Hypit: it uses a `hypit` on the PATH first; without one, it runs `npx --yes @hypit/hypit@0.3.1`. Needs Node.

- **Command:** `simplicio-video clone <command> [arguments]`, for example `clone status`.
- **MCP:** `video.clone` accepts only a closed list: `help`, `version`, `doctor`, `check`, `plan`, `pricing`, `status`, `builds`, `history`, `activity`, `inspect`, `logs`, `paths`, and `vocabulary`; `get <build> --output <name> --to <absolute path>`; and `media probe|frames|tile|tiles|boundaries|cut`, with absolute paths, no `..`, and no `--watch`. Anything else is refused.
- **Terminal only:** `build` (can spend on providers), `studio` (never ends), `auth` (reads a secret from stdin), `runtime up|down|init|use|unset` (changes runtime processes), `packages` (installs third-party code), `capture` (downloads a browser and opens pages), `transcribe` and `measure` (they use providers), `cancel`, `programs`, `result edit` and `snapshot`, `media fetch` (use `simplicio-video media fetch --autorizo`), and `--watch`.
- **Example:** `simplicio-video clone status`

### Toonflow (`toonflow`)

[HBAI-Ltd/Toonflow-app](https://github.com/HBAI-Ltd/Toonflow-app) · MIT

An AI studio for short series, comics, and videos, with the creation done in the app itself. It runs as a local application (Bun). Toonflow's own MCP is off by default: turn it on in Settings > MCP in the interface, then run `toonflow mcp`.

- **Command:** `toonflow clone [folder]`, `toonflow serve --lan` (installs, builds, and starts at http://localhost:3000), `toonflow serve --docker` (an alternative bound to 127.0.0.1:3000 only, through Toonflow's own `docker compose`), `toonflow status [--json]` (checkout, pin, bun, build, and the MCP runtime file; never the token), `toonflow mcp [--port N] [--json]` (the stdio MCP config block to paste into the agent; never the token), and `toonflow where`.
- **Warning:** without `--lan`, `serve` does not start: Toonflow listens on 0.0.0.0:3000 and has no login. `--docker` does not combine with `mcp`, because the MCP runtime file lives in the container's volume.
- **MCP:** `status`, `mcp` (also with `--port N`), `where`, and `clone` (default folder).
- **Terminal only:** `serve` (a server that never ends; `--lan` exposes it on the network, `--docker` stays on 127.0.0.1) and `clone` with a folder.
- **Example:** `simplicio-video toonflow status --json`

### MoneyPrinterTurbo (`moneyprinter`)

[harry0703/MoneyPrinterTurbo](https://github.com/harry0703/MoneyPrinterTurbo) · MIT

Generates a short video from a topic: an LLM script, a synthesized voice, and clips from a stock library or from your own material. Needs Python 3.11 or newer. The third-party services it uses (LLM, voice, and stock) have their own terms, which were not reviewed here.

- **Command:** `moneyprinter clone [folder]`, `setup` (its own venv; copies the example `config.toml`, with no key), `serve [--webui] [--api] [--lan] [--host H] [--api-port N]` (127.0.0.1 only, unless `--lan`), `generate --script ... --material ... --out ...` (starts the API behind the scenes and returns the MP4 with a hash), `run [--yes] --out DIR -- <upstream flags>`, `status` (says whether each key is filled in, never the value), and `where`.
- **`run`:** passes flags of the upstream `cli.py` through a closed list (script, steps, subtitles, music, batch) and copies the MP4 with its sha256. Anything that spends (LLM, paid material source, network voice, `--confirm-*-charge`) runs only in the terminal and only with `--yes`.
- **Keys:** yours, in `config.toml` or in the WebUI. The command never prints the value.
- **MCP:** `where`, `clone` (default folder), and `status`. `generate` and `run` become a background job (follow it with `video.jobs`), and only in free mode: your own script, local material, an Edge or silent voice, and an absolute `--out`. The MP4 comes back copied to the output folder, with its sha256.
- **Terminal only:** `setup`, `serve`, LLM scripts, paid or online material sources, `--confirm-*-charge`, batch files, and `clone` with a folder.
- **Example:** `simplicio-video moneyprinter run --out out/ -- --video-script "Texto do vídeo." --video-source local --video-materials clip.mp4 --voice-name pt-BR-FranciscaNeural-Female`

### match-cut (`matchcut`)

[Sac-Y/match-cut](https://github.com/Sac-Y/match-cut) · MIT

An agent skill (Claude Code or Codex) for product films in the match-cut relay style. The engine downloads the pinned commit, shows where the `SKILL.md` is, and runs only seven local scripts of the skill (music, mix, qc, render, assemble, align, undot) in its own venv. Before it runs one, it checks the sha256 of the script and of `common.py`, and it validates the `montage.json` the scripts read. The engine does not call Renoise; using the skill requires signing in to Renoise with your own account and spends paid credits.

- **Command:** `matchcut clone [folder]`, `where`, `status`, `setup` (creates the venv; checks the sha256 of `requirements.txt` and installs the dependencies from pip without hashes, because the upstream has no lock; needs network), and `run SCRIPT [--forcar] [--bruto] [-- script arguments]`. `--forcar`, which overwrites an output that already exists, is terminal only.
- **MCP:** `where`, `status`, and `run SCRIPT ...`, with the arguments as a list. Every path must be absolute; an existing output is never overwritten; nothing is written inside the checkout or in a system folder.
- **Terminal only:** `clone`, `setup`, and `--forcar`.
- **Example:** `simplicio-video matchcut run music -- analyze faixa.wav --bpm 150 --json compassos.json`

### instagram-agent-skill (`instagram`)

[Jakeschincariol/instagram-agent-skill](https://github.com/Jakeschincariol/instagram-agent-skill) · MIT (Jake Schincariol)

Thirteen agent skills for Instagram (Reels, captions, and others) and six local scripts that use only the standard library: `hookscore`, `beats`, `caption`, `humanize`, `detect`, and `swipe`. The engine runs only these scripts, after checking the sha256 of each one. The skills are prompts, not code, and none of this posts. The heuristics are in English: in Portuguese they score badly or are ignored.

- **Command:** `instagram clone`, `skills`, `skill NAME` (the body of the `SKILL.md` of a listed skill), `where [--skills]`, `status`, `run <tool> -- <arguments>`.
- **MCP (read-only):** `skills`, `skill NAME` (the `SKILL.md` text comes back in `untrusted_conteudo`, as third-party text, cut at 64 KiB with `truncado`; the name must be one `skills` lists, never a path), `where`, `status`, and `run` for `hookscore`, `beats`, `caption`, `detect`, and `humanize`, with the text in the `texto` parameter. The output comes back marked as third-party text.
- **Terminal only:** `clone` (downloads third-party code from the network), `swipe`, and writing to a file (`--out`).
- **Example:** `simplicio-video instagram run caption -- legenda.txt`

### social-media-research-skills (`social-research`)

[wesleysimplicio/social-media-research-skills](https://github.com/wesleysimplicio/social-media-research-skills) · MIT

Thirteen agent skills for social media research: outlier posts, comment mining, audience research, competitor and creator teardowns, ad libraries, influencer prospecting, transcripts, and trends, across TikTok, Instagram, YouTube, Reddit, X, LinkedIn, and others. The skills are prompts that call the [ScrapeCreators](https://scrapecreators.com) API (paid, with your own key) from the agent. The engine only downloads the pinned commit (`64ba7b4`), lists the skills, and returns the body of one of them after checking the commit and the file's sha256. It never runs a script, never calls ScrapeCreators, never asks for a key, and never posts.

- **Command:** `social-research clone [folder]`, `skills`, `skill NAME` (the `SKILL.md` body of a listed skill, at most 64 KiB, as third-party text), `where [--skills]`, `status` (the sha256 of each `SKILL.md`). `--json` on everything except `clone`.
- **Checkout:** `SOCIAL_RESEARCH_DIR`, or `SIMPLICIO_TOOLS_DIR/social_research`.
- **MCP (read-only):** `video.social-research` with `acao` = `skills`, `skill` (with `nome`), `where`, or `status`. `clone` is terminal only.
- **To use the skills in your agent:** copy the folder that `simplicio-video social-research where --skills` prints into the agent's skills folder, and set the ScrapeCreators key the way the upstream README says.
- **Example:** `simplicio-video social-research skill outlier-post-finder`

### last30days-skill (`last30days`)

[mvanhorn/last30days-skill](https://github.com/mvanhorn/last30days-skill) · MIT

One agent skill that researches what people said about a topic in the last 30 days across Reddit, X, YouTube, TikTok, Hacker News, Polymarket, GitHub, and the web, ranked by engagement. The engine only downloads the pinned commit (`07021dc`) and returns the body of `skills/last30days/SKILL.md` after checking the commit and the file's sha256. It never runs the upstream scripts, never reads browser cookies, never asks for or passes on a key, and never posts.

- **Command:** `last30days clone [folder]`, `skill` (the `SKILL.md` body, at most 64 KiB, as third-party text), `where [--skills]`, `status` (the sha256 of the `SKILL.md`). `--json` on everything except `clone`.
- **Checkout:** `LAST30DAYS_DIR`, or `SIMPLICIO_TOOLS_DIR/last30days`.
- **MCP (read-only):** `video.last30days` with `acao` = `skill`, `where`, or `status`. `clone` is terminal only.
- **The skill itself:** run from Claude Code (`/plugin install last30days`, or the folder `simplicio-video last30days where --skills` prints), it needs Python 3.12+, may read your browser cookies for X, and calls paid third parties (ScrapeCreators, Perplexity, and others) with your own keys. That happens in your agent, not in the engine.
- **Example:** `simplicio-video last30days skill`

### VoiceStudio (`voicestudio`)

[debpalash/VoiceStudio](https://github.com/debpalash/VoiceStudio) · AGPL-3.0; the engine talks to the app only over local HTTP and never vendors it.

A local voice app: TTS, transcription, voice cloning and design, and dubbing. You install and open the app. The engine talks to it over local HTTP, at `http://127.0.0.1:3900` by default; the `VOICESTUDIO_URL` and `OMNIVOICE_URL` variables point to another base. Sending a file (`dub create`, `transcribe`, `clone`) goes only to an app on loopback (127.0.0.0/8, ::1, or localhost).

- **Command:** `voicestudio status`, `voices`, `languages`, `personalities`, `tts`, `transcribe`, `clone`, `describe`, `design`, `dub create VIDEO`, `dub-export --job ID --lang LANG -o OUTPUT.mp4`, and `mcp`.
- **`dub create`:** uploads the video (or audio, with `--audio`) to the app and creates the dubbing job. It does not transcribe, translate, or generate the voice; that runs in the app.
- **`dub-export`:** exports a dubbing job that already exists in the app, with music and effects, provided the job was made with background separation turned on in the app (without it, the app answers 409 and the command refuses). It does not generate the voice.
- **Result:** the command returns the result as JSON (`result`), the exit code (`rc`), and, if it fails, `error`.
- **Consent:** cloning or dubbing a real person's voice requires that person's recorded consent, as `AGENTS.md` requires. The command does not check this.
- **MCP:** `video.voicestudio`, with the same subcommands. The outputs of `tts` and `dub-export` (`--out`/`-o`) are required, absolute, new files in an existing folder, outside system and hidden folders. The input files of `dub create`, `transcribe`, and `clone` are absolute media paths.
- **Terminal only:** nothing, on main.
- **Example:** `simplicio-video voicestudio status`

### video-use (`edit`)

[browser-use/video-use](https://github.com/browser-use/video-use) · MIT

EDL editing of any MP4: word-accurate cuts, subtitles, overlays, filmstrip review, and color grading. The agent writes the decision in `edl.json`, and ffmpeg executes it. Local transcription uses faster-whisper.

- **Command:** `edit setup`, `transcribe`, `transcribe-batch DIR` (terminal only; ElevenLabs Scribe, a paid third party), `pack`, `render`, `verify`, `grade` (`--analyze`, `--preset`, `--filter`, `--list-presets`).
- **MCP:** all subcommands except `transcribe-batch`. For `transcribe`, `render`, `verify`, and `grade`, the outputs (`-o`, `--out`, `--output`) must be absolute paths. For `grade`, `--filter` accepts only color filters (eq, curves, colorbalance, hue, lut, lutrgb, lutyuv, colorchannelmixer, vibrance).
- **Terminal only:** `transcribe-batch`.
- **Example:** `simplicio-video edit render edit/edl.json -o out/final.raw.mp4`

### rea-video (`rea-video`)

[JuneYaooo/rea-video](https://github.com/JuneYaooo/rea-video) · MIT, declared in `pyproject.toml`; the pinned commit has no LICENSE file

Analyzes a reference video shot by shot (live action, AI, 3D, or code render) and plans a remake. It analyzes a file you already have: it does not download video. Needs ffmpeg and Python 3.10 or newer.

- **Command:** `rea-video clone`, `setup`, `where`, `status`, and passthrough of any upstream command (`decompose`, `summary`, `review`, `apply-review`, `remake-plan`, and others).
- **Network:** without `--vlm`, only model downloads. With `--vlm`, frames go to the vision-model provider you configure, a third party.
- **MCP:** `where`, `status`, `clone` (default folder), `summary`, `probe`, `tiles` (with a new `-o`), `review`, `apply-review`, and `remake-plan`, with a closed list of flags and absolute paths. `decompose` and `stems` become a background job (follow it with `video.jobs`); `decompose` always runs without the vision model. In `review` and `apply-review`, the calling agent does the looking, so no frame goes to a third party.
- **Terminal only:** `setup` (installs dependencies), `remake-run` (spends), `capsule-draft` (runs code from a folder), `prefs`, `correct`, `memory`, `eval`, `capsule`, `assemble`, `--vlm`, `--env-file`, and `clone` with a folder.
- **Example:** `simplicio-video rea-video decompose ref.mp4 -o out/ref --no-stems`

### video-to-skill (`video-to-skill`)

[brenoepics/video-to-skill](https://github.com/brenoepics/video-to-skill) · MIT, by Breno Epics · pinned to tag v0.3.0, commit `c1a1b90`

**New.** It turns a video into an installable agent skill: a tutorial becomes numbered steps, each one citing the second of the video and the frame it came from, packaged as a `SKILL.md` that an agent can load. The upstream has two parts. A local Rust extractor, `vts-extract`, does the deterministic work (demux, shot detection, keyframes, a word-timestamped transcript when its voice models are installed, compile of a skill package, merge of a second video into an existing skill, install for every agent on the machine). The agent does the reading: it looks at the keyframes and writes the `procedure.json` that the compiler turns into the package. The engine pins the commit of the upstream skill and the release of the extractor, and runs the extractor only as a separate program, never imported.

```bash
simplicio-video video-to-skill clone                          # the pinned commit: SKILL.md and references (needs network)
simplicio-video video-to-skill setup                          # the extractor: the PATH one only if it says exactly 0.3.0, else the pinned release asset
simplicio-video video-to-skill check --print-downloads        # read only: what the upstream would download, with URL and sha256
mkdir -p out/excel                                            # the parent folder must exist (as in every track)
simplicio-video video-to-skill extract tutorial.mp4 --out out/excel/bundle     # local file; a new or empty folder
simplicio-video video-to-skill frame-at --bundle out/excel/bundle 0:54 1:12    # frames at those times, under the bundle
simplicio-video video-to-skill clip --bundle out/excel/bundle 0:50 1:05 --fps 2
simplicio-video video-to-skill compile --bundle out/excel/bundle --ir out/excel/bundle/procedure.json --out out/excel/excel-soma
simplicio-video video-to-skill install --package out/excel/excel-soma          # prints the plan, writes nothing; add --yes yourself to install
```

- **Setup flow.** `setup` downloads the release asset of your platform from the upstream GitHub release (`linux-x86_64`, `macos-arm64`, `macos-x86_64`, `windows-x86_64`), checks its sha256 against a pinned table before extracting anything, extracts only the single executable (no path, no link, no other entry, a size cap), checks the sha256 of that file before it runs, and only then asks `--version`. A managed binary is checked against its pinned sha256 on every use; a `vts-extract` found on the PATH is trusted by its version only (no sha256 is checked). On any other platform it says so and asks you to build the upstream from source.
- **Downloaded by whom.** The extractor comes from the upstream release, fetched by the engine. Its own dependencies (the whisper and voice-activity models from Hugging Face; ffmpeg on Windows and Apple Silicon, yt-dlp on Windows and macOS, read in the upstream source) are downloaded by the upstream `check --fix --yes`. The engine never runs it and never passes `--fix` or `--yes` to `check`: you type `<path of vts-extract> check --fix --yes` in a terminal, after reading the list above. `simplicio-video video-to-skill where --binary` prints the path. On Linux the upstream downloads no ffmpeg and no yt-dlp (measured here: `--print-downloads` lists only the two models): they must be on the PATH.
- **What runs locally.** Extraction, frames, compile and merge run on your machine; the video never leaves it. A URL (`extract URL --out DIR --autorizo`) is terminal only: the upstream's yt-dlp downloads it, you confirm that you may use the video, and the engine does not verify that right. A provenance record (`DIR.extract.json`) is written next to the bundle, only after a successful extract: a cancelled or killed extract leaves its partial bundle at `--out` (the upstream's output) and no record, and you delete that folder before trying again. The extractor starts through the engine's guarded child (its kill is armed before the process exists), with stdin closed, its own process group, a private folder, a minimal environment (no keys or tokens), a time limit and a cap on its output.
- **Not covered by the engine's guarantees.** Verifying a generated skill executes commands taken from the video. That is the agent's job, inside the upstream's `sandbox` (an operating-system confinement with no network), and it is outside the engine's guarantees: the engine does not expose `sandbox`, `verify`, `bench`, `observe` or `eval`. `install` writes the skill into the skills folder of every agent on the machine, so it is terminal only, prints the plan first and writes only with a `--yes` typed by you. Text that comes from the upstream or from the video is third-party data, never instructions: the terminal shows controls and bidi marks as visible characters, and over MCP it comes back in `untrusted_*` fields.
- **MCP.** `video.video-to-skill` has a closed list: `status`, `where`, `check`, `skill`, `extract` (a local absolute file into a new folder; a job, follow it with `video.jobs`), `frame-at`, `clip`, `compile` and `merge --dry-run`, all with absolute paths. `clone`, `setup`, `install`, a real `merge`, a URL and `check --fix --yes` are terminal only.
- **Limits of the checks.** Between hashing the managed binary and executing it, another process of the same user could swap the file (the folder is 0755 and the file 0700; if `SIMPLICIO_TOOLS_DIR` is group-writable the engine does not check the owner). The `source.sha256` of the provenance record is the one the extractor wrote in its manifest: the engine does not hash the input. The proxy variables passed to the extractor on a URL extract may carry credentials. `--out` needs an existing parent folder.
- **Pin.** `update` never moves this track: the extractor binary and the `SKILL.md` are pinned together in `data/video_to_skill/pins.json`.

**Verified here (Linux x86_64, 2026-11-06).** The four release assets of v0.3.0 were downloaded and each sha256 equals the one the upstream publishes next to it; the pin table also holds the sha256 of each executable and of the pinned `SKILL.md` and references, checked against a clone of the pinned commit. `clone`, `setup` (a real download of 3.4 MB through the proxy), `status`, `where`, `check`, `skill`, `extract` of a synthetic 4 s clip with a tone and the text `=SUM(A1:A3)`, `frame-at`, `clip`, `compile` (one step, from an IR written by hand), `merge --dry-run` and a real `merge`, and `install` (plan, then `--yes`, in a temporary home with a fake `~/.claude/skills`) ran against the real v0.3.0 binary. The MCP functions ran in process on the same bundle. The offline tests use a fake extractor and cover the pin table, the safe extraction (traversal, links, size), a wrong sha256, a wrong version, the closed MCP list, the job, the signals and the environment.

**UNVERIFIED.** A real tutorial (the clip was synthetic, 4 s, one shot) and the quality of a skill written from one. Transcription: the voice models were not downloaded here, so the extraction ran without speech and the timeline says so. The v0.3.0 extractor has no OCR and no `text` command (those came in later upstream commits), so on-screen text is read by the agent from the frames. The SLSA attestation of the release archives (it needs the GitHub CLI and a GitHub token; the check here was refused with HTTP 403). The upstream `sandbox` and `verify` (not run). `check --fix --yes` (not run: only you run it). `extract` of a URL. Windows and macOS (the pin table has their assets; nothing ran there).

### yt-dlp (`media fetch`)

[yt-dlp/yt-dlp](https://github.com/yt-dlp/yt-dlp) · Unlicense

Downloads a public video to a local MP4 and writes `OUT.fetch.json` next to it, with the URL, sha256, yt-dlp version, and time. It runs in its own venv, with the wheel checked by sha256. It does not log in, does not read browser cookies, and does not download playlists.

- **Command:** `media fetch <URL> --info` (metadata only: title, duration, uploader, license, formats, and subtitle languages; it downloads nothing and needs no `--autorizo`); `media fetch <URL> -o output.mp4 --autorizo`, with `--max-mb`, `--timeout`, `--subs LANG [--auto-subs]` (the creator's subtitles, as `.srt`), `--section START-END` (only that range, in seconds), and `--audio-only` (outputs `.m4a` or `.wav`).
- **`--autorizo`:** required to download. You confirm that you may use the video; the engine does not check this, and platforms such as Instagram have their own download rules.
- **MCP:** `video.media` runs `fetch` only with `--autorizo`, and the agent passes the flag only after you approve that URL in the chat. `--info` needs no approval.
- **Terminal only:** nothing, on main. Over MCP, your approval of the URL in the chat is what holds the download back.
- **Example:** `simplicio-video media fetch <URL> --info`

### TinyFish CLI (`busca`)

[@tiny-fish/cli](https://www.npmjs.com/package/@tiny-fish/cli) · license not declared in the package (read on 2026-11-05, version 0.57.0). You install it with `npm install -g @tiny-fish/cli@0.57.0` (the package asks for Node 24 or newer); the engine never installs it.

Web search and reading of one page, to find references and public facts to check. Each result comes with its source and date, and there is a daily cap on calls (20 by default). It does not call an LLM and does not decide what is true. Web search does not replace the client's own collection.

- **Command:** `busca consulta "<text>" [--idioma pt] [--limite N]`, `busca pagina <url>`, `busca status`, `busca log`.
- **Privacy:** the query and the URL go to a third party (TinyFish). The engine always refuses keys and tokens, and refuses e-mail, CPF, and CNPJ unless the terminal says `--permitir-dado-pessoal`.
- **MCP:** `consulta`, `pagina`, `status`, and `log`, with the same cap. No `--atualizar` and no `--permitir-dado-pessoal`.
- **Terminal only:** `--atualizar` (spends one call to bypass the cache) and `--permitir-dado-pessoal`.
- **Example:** `simplicio-video busca consulta "datas comemorativas marketing" --idioma pt --limite 5`

## External tracks and licenses

Each version is pinned in [`src/simplicio_video/tools.py`](src/simplicio_video/tools.py). `simplicio-video tools` lists them all. The engine never vendors or imports these tracks, and the deterministic render does not depend on any of them.

`simplicio-video update` (on every release it installs) moves each track to what upstream says is latest; the pin is the starting point and what `--pin` keeps. What it resolved is recorded in `tools.lock.json` (in `$SIMPLICIO_VIDEO_DATA`), and `tools` and `doctor` show it. A track whose update fails keeps the checkout it has and is reported; the package update still goes through. An override `SIMPLICIO_<NAME>_REF` always wins and is never refreshed.

| Track | Command | Pinned version | `update` follows | License |
|---|---|---|---|---|
| OpenMontage | `montage` | commit `9327439` | default branch | AGPL-3.0 |
| OpenCut | `opencut` | commit `cf5e79e` | default branch | MIT |
| Hypit | `clone` | npm `0.3.1` | latest npm version | Hypit license (modified Apache-2.0); no commercial redistribution |
| Toonflow | `toonflow` | commit `d2e94ac` | default branch | MIT |
| MoneyPrinterTurbo | `moneyprinter` | commit `4b7b965` | default branch | MIT |
| match-cut | `matchcut` | commit `b51c98f` | default branch | MIT. Use requires a Renoise login and credits |
| instagram-agent-skill | `instagram` | commit `d03c56b` | default branch | MIT (Jake Schincariol). A script runs only after its sha256 matches the pinned one |
| TinyFish CLI | `busca` | npm `0.57.0` | latest npm version | Not declared in the package |
| VoiceStudio | `voicestudio` | commit `beeaae08` | default branch | AGPL-3.0. Used only over local HTTP |
| video-use | `edit` | commit `b877063` | default branch | MIT |
| video-to-skill | `video-to-skill` | commit `c1a1b90` (tag v0.3.0); extractor `vts-extract` v0.3.0, sha256 checked per platform | none (pinned: the extractor and `SKILL.md` are pinned together) | MIT (Breno Epics). The extractor binary is not bundled: `setup` downloads it |
| yt-dlp | `media fetch` | PyPI `2026.10.26`, sha256 checked | latest PyPI release, sha256 checked | Unlicense |
| rea-video | `rea-video` | commit `36e02dd` | default branch | MIT, declared in `pyproject.toml`; the pinned commit has no LICENSE file |

### MoneyPrinterTurbo (`moneyprinter`)

```bash
simplicio-video moneyprinter clone      # clones at the commit pinned in src/simplicio_video/tools.py
simplicio-video moneyprinter setup      # venv in ~/.simplicio-video/moneyprinter-data; config.toml copied from the example (no key filled)
simplicio-video moneyprinter serve      # WebUI on http://localhost:8501; --api for the API; --api-port N moves the API (default 8080)
simplicio-video moneyprinter generate --script roteiro.txt --material clip.mp4 --out out/   # API behind the scenes; returns the MP4 + manifest
simplicio-video moneyprinter status     # config.toml exists? which keys are filled (yes only, never the value)
```

`generate` picks a free loopback port (or `--api-port`), uploads each `--material`, asks for a video from a ready script with a local source (no LLM key and no stock key), waits for the task, copies the MP4 to `--out` and writes `moneyprinter-<task>.json` (schema `simplicio.moneyprinter-result/v1`) with the sha256 of the video and of each material. It stops the API before it returns.

It uses your own API keys for LLM, TTS and stock services, typed in its WebUI or `config.toml`; this command never prints them. The API listens on `127.0.0.1` only; `--lan` opens every interface. Whatever it produces enters a contract as a file with a hash.

**Known gaps:**
- Audio cleanup: in a PR, not on main yet.
- Voice and background separation: no command.
- Dubbing with preserved background: the dub itself runs in the VoiceStudio app; `voicestudio dub create` uploads the video and `dub-export` exports the finished job.

### rea-video (`rea-video`)

```bash
simplicio-video rea-video clone                                     # clones the pinned commit into the tools cache
simplicio-video rea-video setup                                     # a venv of its own with the checkout (pip; needs network)
simplicio-video rea-video decompose ref.mp4 -o out/ref --no-stems   # any upstream command, run from your folder
simplicio-video rea-video status                                    # checkout, venv, OCR, ffmpeg; VLM keys as set or not set, never their values
```

Every word that is not one of this track's own commands goes unchanged to the `rea-video` of its venv, upstream flags included (`--env-file`). The upstream's own help (`simplicio-video rea-video decompose --help`) is in Chinese.

`decompose` writes `breakdown.json`, `report.html`, `report.md`, `storyboard.jpg` and a shot folder to the `-o` folder. Each shot gets a verdict: live action, AI video, 3D, code render or mixed.

- **Network.** Without `--vlm`, the only network use is the model downloads: a voice-separation model of about 67 MB from GitHub (`--no-stems` skips it) and a small face detector (without it, the upstream falls back to Haar). Models go to `REA_VIDEO_MODELS`, which defaults to the track's data folder.
- **The vision model is a third party.** With `--vlm`, up to 60 shots go to the provider you configure (`REA_VLM_BASE_URL` and `REA_VLM_API_KEY`, or the `VIDEO_ANALYSIS_*` and `GEMINI3_*` names). Each shot is a clip of up to 12 seconds at 480p, and the whole video goes at 480p with audio. Without a key, the upstream warns and runs without the model.
- **A `.env` in the folder you run from is read.** The upstream loads it on its own, with its endpoints and keys. Run analyses from a folder without another project's `.env`; `status` warns when one is there.
- **OCR needs a compatible Python.** Subtitles and on-screen text use `rapidocr-onnxruntime`, which has no release for every Python. Python 3.13 did not install it here; Python 3.11.18 did. For OCR, delete the venv folder in the data folder and run `REA_VIDEO_PYTHON=python3.11 simplicio-video rea-video setup`. An existing venv is kept, so the folder has to go first. Without OCR, `setup` installs the core and warns.
- **Code from the capsule folder.** `remake-run` and `capsule-draft` import and run code from the capsule-cinema folder you point them to. Point them only at a folder you trust.
- **State.** Memory and preferences go to `home/` in the data folder (`~/.simplicio-video/rea-video-data`), not to `~/.rea-video`.
- **Requirements.** ffmpeg on the PATH and Python 3.10 or newer. `clone` and `setup` need network and refuse `SIMPLICIO_OFFLINE=1`. `setup` installs dependencies from pip without hashes, because the upstream has no lock file.
- **MCP.** `video.rea-video` accepts `where`, `status` and `clone` (into the default folder). `setup` and the analysis run in the terminal: a run takes minutes and may spend vision-model calls.

Tested here on Linux: clone at the pinned commit; `setup` on Python 3.13 (core only) and on 3.11 (core and OCR); the passthrough of `decompose`, `probe`, `summary` and `memory`; a default run with the 67 MB download; `--vlm` without a key, which warns and runs; the MCP tool listed over stdio. Not verified: real footage, a real vision-model call, the accuracy figures in the upstream README, `remake-run` and `capsule-draft`, Japanese OCR, Windows and macOS.

### Instagram agent skills (`instagram`)

```bash
simplicio-video instagram clone                                  # pinned commit d03c56b into the tools cache (the only step that uses the network)
simplicio-video instagram skills                                 # the 13 skills: name and description
simplicio-video instagram run hookscore -- --hook 'I lost $18,000 because of one missing contract.'
simplicio-video instagram run beats -- roteiro.txt --target 30   # a script into a timed beat sheet
simplicio-video instagram run caption -- legenda.txt             # a caption linter
simplicio-video instagram where --skills                         # the folder the skills are in (to copy them to your agent)
simplicio-video instagram status                                 # commit of the checkout and sha256 of each script
```

**What it is.** [Jakeschincariol/instagram-agent-skill](https://github.com/Jakeschincariol/instagram-agent-skill), by Jake Schincariol, MIT, pinned at commit `d03c56b` (the last upstream commit, 2026-09-13; read here on 2026-11-04). It is thirteen Claude skills (`ig-reel`, `ig-viral`, `ig-caption`, `ig-carousel`, `ig-story`, `ig-profile`, `ig-plan`, `ig-human`, `ig-comment`, `ig-reply`, `ig-dm`, `ig-repurpose`, `ig-audit`), a `templates/voice.md`, and six Python scripts that use only the standard library: `hookscore` (scores a hook), `beats` (a script into a timed beat sheet), `caption` (caption linter), `humanize` (strips invisible characters, typography and stock words), `detect` (a five-check panel) and `swipe` (ranks outlier reels from a TSV). The skills are prompts for an agent, not code.

**It never posts.** The upstream says it too: "These skills write. You post." The engine does not post, publish, log in or ask for a key, and `clone` is the only subcommand that uses the network.

**Subcommands.** `clone [dir]` (the pinned commit, in `INSTAGRAM_DIR` or `SIMPLICIO_TOOLS_DIR/instagram`; it refuses `SIMPLICIO_OFFLINE=1`), `where`, `status`, `skills` (the description of each `SKILL.md` is third-party text, shown as data) and `run <tool> [--forcar] [-- script arguments]`. The tool is one of `hookscore`, `beats`, `caption`, `humanize`, `detect`, `swipe`, a closed list: a path is never accepted. Every script option is checked against that tool's own list (an abbreviation such as `--ou` is refused), so the script arguments go after `--` and the script's own `--json` works.

**What `run` checks and limits.**
- The commit of the checkout and the sha256 of the script, and of the files it reads (`slop.json`, `hooks.json`) or imports (`swipe` imports `hookscore.py`). A different file is refused. What runs is a private copy of the bytes that were checked.
- The script runs as `python -I -B -X utf8`, by argument list with no shell, in your current folder, with only `PATH`, `HOME`, `LANG`, `LC_ALL`, `PYTHONIOENCODING`, `TMP`, `TEMP` and `SYSTEMROOT` (no key), for at most 30 s and 2 MB of output, with at most 1 MiB per input file or stdin.
- `humanize -o/--out` and `swipe --out` exist only in the terminal. The engine does not overwrite a file that exists unless you pass `--forcar` before the `--`, and it never writes inside the checkout, in a system folder (`/etc`, `/usr`...) or in a hidden folder of your home (`~/.ssh`, `~/.config`, `~/.claude`...); links are resolved first.
- An input file is opened once, checked with `fstat` on that descriptor (a regular file only; a named pipe does not block it) and read up to 1 MiB + 1; the script gets a private copy of exactly those bytes.
- If the engine receives SIGTERM or SIGHUP (terminal closed, MCP host stopping, an agent's timeout), it kills the script's process group and removes the private folder. On POSIX the script also gets an `RLIMIT_CPU` of 35 s from the kernel, so a script that burns CPU ends even if the engine is killed outright. It limits CPU time, not wall time, and it does not exist on Windows (there only the 30 s kill and the signal handling remain).
- In the terminal the script's text is shown with ESC, control, bidirectional and zero-width characters turned into visible marks (`␛`, `<U+202E>`), because it can come from a third party. `--bruto`, an engine flag before the `--`, prints it raw. To save the cleaned text of `humanize` use `-o` (the script writes the file itself) or `--bruto`.
- The `--out` guard compares folder names without regard to case on macOS and Windows (and to Unicode normalization on macOS), and also refuses the auto-start folders (`~/Library/LaunchAgents`, `~/Library/LaunchDaemons`, the `Startup` folder of the Windows Start Menu). UNVERIFIED: there is no macOS or Windows here.
- After `simplicio-video update` moves the track to a newer upstream commit, `run` refuses any script whose sha256 changed, until the table in `src/simplicio_video/instagram.py` is audited again. `update --pin` goes back to the pinned commit.

**The heuristics are in English.** The upstream's regular expressions, word lexicon (`slop.json`) and 26 hook formulas are English. The author measured `hookscore` on 74 YouTube Shorts hooks: AUC 0.83 to catch hooks written to be bad, and 0.56 to pick a creator's hits from the same creator's misses (0.50 is a coin flip). Run here, with the same pinned scripts:

| Input | Result |
|---|---|
| `I lost $18,000 because of one missing contract.` | `hookscore` 81.4 STRONG |
| `Eu perdi R$ 18.000 por causa de um contrato que faltava.` (same sentence) | 59.6 OK; it reports "third person, nobody in the room" for a first-person sentence |
| `Hey guys, today I wanted to talk about content strategy` | 9.6 WEAK, with the "Greeting" dealbreaker |
| `Oi pessoal, hoje eu quero falar sobre estratégia de conteúdo` (same greeting) | 30.0 WEAK, with no dealbreaker |
| Caption ending in "Comment CLAUSE" / "Comente CLÁUSULA" | `caption` finds the call to action in the first, "no call to action" in the second |
| A Portuguese draft full of stock phrases | `detect`: "0 stock terms"; `humanize` removes the invisible character and the em dash but no word |

`beats` times Portuguese by word count at 165 words per minute (an English default; change it with `--wpm`). For Portuguese, treat the scores as a rough hint and not as a verdict.

**Copy the skills to your agent.** The engine does not copy them (`simplicio-video install` is only for this project's own skill). The upstream's own command, pointed at the checkout:

```bash
mkdir -p ~/.claude/skills
cp -r "$(simplicio-video instagram where --skills)"/ig-* ~/.claude/skills/
```

The upstream also asks you to copy `templates/voice.md` to `~/.claude/instagram/voice.md` and fill it in: every skill reads that file.

**After you copy the skills, none of the engine's guarantees applies.** Once the skills are in `~/.claude/skills/`, your agent runs the scripts directly, as the upstream's `SKILL.md` files tell it to (`python3 swipe.py captured.tsv --out ...`, `python3 humanize.py draft.txt -o ...`): no sha256 check, no `-I`, no closed environment (your keys are visible to the script), no 30 s or 2 MB limit, no `--out` guard, and no `SIGTERM` handling. The upstream's `ig-viral` skill also tells the agent to use your browser while you are logged in to Instagram (an extension or computer use) and `yt-dlp` to read YouTube Shorts: that is the skill's behavior, not the engine's. The path the upstream suggests, `--out ~/.claude/instagram/swipe.md`, is one `instagram run` refuses (a hidden folder of the home). Whoever wants the engine's guarantees uses `instagram run`; whoever copies the skills takes on the risk of what the agent executes. The statement "it never posts" above is about the engine, not about an agent that follows those skills.

**MCP.** `video.instagram` accepts `skills`, `where`, `status` and `run` for `hookscore`, `beats`, `caption`, `detect` and `humanize`. The text goes in the `texto` parameter and into the script by stdin; there is no file path, no `--out` and no `--lexicon`, and the script text comes back in `saida` with a notice that it is third-party text and an English heuristic. `clone` and `swipe` are terminal-only: an agent does not download code on its own.

Tested here on Linux: `clone` of the pinned commit; the eight sha256 of the table against that clone; the six scripts through `run` with English and Portuguese inputs (the figures above); `humanize -o` and `swipe --out` writing a new file and refusing an existing one, `/etc` and the checkout; the MCP tool over stdio (31 tools, a hook scored, `--out` refused); a suite with hostile arguments, a tampered script, another commit, a huge output, a timeout, a closed environment and a hostile `SKILL.md`. **UNVERIFIED:** Windows and macOS; an agent actually using the skills (none was run here, so the skills' quality, in English or Portuguese, is not assessed); the author's AUC figures (they are the author's, not reproduced); the upstream's `/plugin` install; commits after 2026-11-04.

## References

- [docs/reference/cli.md](docs/reference/cli.md): every command and flag.
- [docs/reference/mcp-tools.md](docs/reference/mcp-tools.md): MCP tools.
- [CHANGELOG.md](CHANGELOG.md): changes by version.
- [AGENTS.md](AGENTS.md): operating rules for agents.
- [Decisions (ADRs)](docs/decisoes/): plugin vision, CLI and contract, 100% script flow.

