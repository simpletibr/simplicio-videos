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
| External tracks | `montage`, `opencut`, `clone`, `toonflow`, `moneyprinter`, `matchcut`, `edit`, `rea-video` | Installed on demand, pinned version | Licenses differ; see the tracks table |
| Reverse-engineer a reference video | `rea-video` | Ready on the pinned commit; installs on demand. A synthetic clip was tested end to end, real footage was not | Local by default. With `--vlm`, frames go to a vision model you configure |
| MCP server | `simplicio-video-mcp` | 30 `video.*` tools | No `swap run` spending, no software removal |
| Audio cleanup | not available yet | In a PR, not on main yet | not applicable |
| Dubbing with preserved background | not available in the CLI yet | Today only in the VoiceStudio app; exposure in progress | not applicable |

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

- Server: `simplicio-video-mcp` (stdio). Tested: it answers `initialize` and lists 30 `video.*` tools over the stdio protocol, `video.rea-video` among them.
- Tool list: [docs/reference/mcp-tools.md](docs/reference/mcp-tools.md).
- **Excluded on purpose, for safety:**
  - `swap run`: spends credits;
  - `install --uninstall` and `--prune-project-copies`: remove software;
  - `montage` with subcommands other than `clone`, `doctor`, `hyperframes-doctor`, `preflight`, and `help`;
  - `auth` with an action other than `status`.
  - Source: `src/simplicio_video/mcp_server.py`.
- **Clients:** the Claude Code and Codex configuration was not verified. `claude` is installed on this Mac, but I did not run `claude mcp add` so as not to change its configuration. Codex is not installed.

### Agent hosts

<!-- BEGIN GENERATED: host -->
Gerado de `docs/host/*.md` (front matter). Não edite aqui: rode `make regen`.

- [Gate local, TDD e pouso de PRs](docs/host/gate.md): Como provar que a main está verde com um comando offline, a regra de testes primeiro, o ownership por issue e o pouso serializado sem CI.
- [Licenças das dependências](docs/host/licenses.md): Como o gate confere licenças (allowlist MIT, Apache-2.0, BSD, ISC, PSF, MPL-2.0), como adicionar uma exceção justificada, como regerar docs/licenses.md e o que ainda falta (web/).
- [Pacote de operação (install, update, doctor, setup)](docs/host/packaging.md): O que cada subcomando faz, o que o doctor checa, por que a falta de GEMINI_API_KEY é aviso e os limites até as
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
| `testada: 0.50.1` in `busca status` | TinyFish at another version | The engine keeps working; the tested version is 0.50.1 |
| `aviso: o extra ocr não instalou` in `rea-video setup` | `rapidocr-onnxruntime` has no release for this Python (3.13 here; 3.11 works) | Delete the venv folder in `~/.simplicio-video/rea-video-data`, then run `REA_VIDEO_PYTHON=python3.11 simplicio-video rea-video setup`. Without OCR the analysis still runs |

## External tracks and licenses

Each version is pinned in [`src/simplicio_video/tools.py`](src/simplicio_video/tools.py). `simplicio-video tools` lists them all. The engine never vendors or imports these tracks, and the deterministic render does not depend on any of them.

| Track | Command | Pinned version | License |
|---|---|---|---|
| OpenMontage | `montage` | commit `9327439` | AGPL-3.0 |
| OpenCut | `opencut` | commit `cf5e79e` | MIT |
| Hypit | `clone` | npm `0.2.17` | Hypit license (modified Apache-2.0); no commercial redistribution |
| Toonflow | `toonflow` | commit `d2e94ac` | MIT |
| MoneyPrinterTurbo | `moneyprinter` | commit `4b7b965` | MIT |
| match-cut | `matchcut` | commit `b51c98f` | MIT. Use requires a Renoise login and credits |
| TinyFish CLI | `busca` | npm `0.50.1` | Not declared in the package |
| VoiceStudio | `voicestudio` | commit `beeaae08` | AGPL-3.0. Used only over local HTTP |
| video-use | `edit` | commit `b877063` | MIT |
| yt-dlp | `media fetch` | PyPI `2026.10.26`, sha256 checked | Unlicense |
| rea-video | `rea-video` | commit `36e02dd` | MIT, declared in `pyproject.toml`; the pinned commit has no LICENSE file |

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
- Dubbing with preserved background: only in the VoiceStudio app today.

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

## References

- [docs/reference/cli.md](docs/reference/cli.md): every command and flag.
- [docs/reference/mcp-tools.md](docs/reference/mcp-tools.md): MCP tools.
- [CHANGELOG.md](CHANGELOG.md): changes by version.
- [AGENTS.md](AGENTS.md): operating rules for agents.
- [Decisions (ADRs)](docs/decisoes/): plugin vision, CLI and contract, 100% script flow.

