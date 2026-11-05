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
| External tracks | `montage`, `opencut`, `clone`, `toonflow`, `moneyprinter`, `matchcut`, `instagram`, `edit`, `rea-video` | Installed on demand, pinned version | Licenses differ; see the tracks table |
| Instagram agent skills and scripts | `instagram` | Ready on the pinned commit; installs on demand. The six scripts ran for real; no agent was run with the skills | Local, no key, no LLM. The heuristics are in English and score Portuguese badly. It never posts |
| Reverse-engineer a reference video | `rea-video` | Ready on the pinned commit; installs on demand. A synthetic clip was tested end to end, real footage was not | Local by default. With `--vlm`, frames go to a vision model you configure |
| MCP server | `simplicio-video-mcp` | 31 `video.*` tools | No `swap run` spending, no software removal |
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

- Server: `simplicio-video-mcp` (stdio). Tested: it answers `initialize` and lists 31 `video.*` tools over the stdio protocol, `video.rea-video` and `video.instagram` among them.
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

`simplicio-video update` (on every release it installs) moves each track to what upstream says is latest; the pin is the starting point and what `--pin` keeps. What it resolved is recorded in `tools.lock.json` (in `$SIMPLICIO_VIDEO_DATA`), and `tools` and `doctor` show it. A track whose update fails keeps the checkout it has and is reported; the package update still goes through. An override `SIMPLICIO_<NAME>_REF` always wins and is never refreshed.

| Track | Command | Pinned version | `update` follows | License |
|---|---|---|---|---|
| OpenMontage | `montage` | commit `9327439` | default branch | AGPL-3.0 |
| OpenCut | `opencut` | commit `cf5e79e` | default branch | MIT |
| Hypit | `clone` | npm `0.2.17` | latest npm version | Hypit license (modified Apache-2.0); no commercial redistribution |
| Toonflow | `toonflow` | commit `d2e94ac` | default branch | MIT |
| MoneyPrinterTurbo | `moneyprinter` | commit `4b7b965` | default branch | MIT |
| match-cut | `matchcut` | commit `b51c98f` | default branch | MIT. Use requires a Renoise login and credits |
| instagram-agent-skill | `instagram` | commit `d03c56b` | default branch | MIT (Jake Schincariol). A script runs only after its sha256 matches the pinned one |
| TinyFish CLI | `busca` | npm `0.50.1` | latest npm version | Not declared in the package |
| VoiceStudio | `voicestudio` | commit `beeaae08` | default branch | AGPL-3.0. Used only over local HTTP |
| video-use | `edit` | commit `b877063` | default branch | MIT |
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

