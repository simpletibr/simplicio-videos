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
| External tracks | `montage`, `opencut`, `clone`, `toonflow`, `moneyprinter`, `matchcut`, `edit` | Installed on demand, pinned version | Licenses differ; see the tracks table |
| MCP server | `simplicio-video-mcp` | 29 `video.*` tools | No `swap run` spending, no software removal |
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

- Server: `simplicio-video-mcp` (stdio). Tested: it answers `initialize` and lists 29 `video.*` tools over the stdio protocol.
- Tool list: [docs/reference/mcp-tools.md](docs/reference/mcp-tools.md).
- **Excluded on purpose, for safety:**
  - `swap run`: spends credits;
  - `install --uninstall` and `--prune-project-copies`: remove software;
  - `montage` with subcommands other than `clone`, `doctor`, `hyperframes-doctor`, `preflight`, and `help`;
  - `auth` with an action other than `status`.
  - Source: `src/simplicio_video/mcp_server.py`.
- **Clients:** the Claude Code and Codex configuration was not verified. `claude` is installed on this Mac, but I did not run `claude mcp add` so as not to change its configuration. Codex is not installed.

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

**Known gaps:**
- Audio cleanup: in a PR, not on main yet.
- Voice and background separation: no command.
- Dubbing with preserved background: only in the VoiceStudio app today.

## References

- [docs/reference/cli.md](docs/reference/cli.md): every command and flag.
- [docs/reference/mcp-tools.md](docs/reference/mcp-tools.md): MCP tools.
- [CHANGELOG.md](CHANGELOG.md): changes by version.
- [AGENTS.md](AGENTS.md): operating rules for agents.
- [Decisions (ADRs)](docs/decisoes/): plugin vision, CLI and contract, 100% script flow.

<!-- BEGIN GENERATED: host -->
Gerado de `docs/host/*.md` (front matter). Não edite aqui: rode `make regen`.

- [Gate local, TDD e pouso de PRs](docs/host/gate.md): Como provar que a main está verde com um comando offline, a regra de testes primeiro, o ownership por issue e o pouso serializado sem CI.
- [Licenças das dependências](docs/host/licenses.md): Como o gate confere licenças (allowlist MIT, Apache-2.0, BSD, ISC, PSF, MPL-2.0), como adicionar uma exceção justificada, como regerar docs/licenses.md e o que ainda falta (web/).
- [Pacote de operação (install, update, doctor, setup)](docs/host/packaging.md): O que cada subcomando faz, o que o doctor checa, por que a falta de GEMINI_API_KEY é aviso e os limites até as
<!-- END GENERATED -->
