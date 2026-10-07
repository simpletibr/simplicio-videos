# Blueprint: the factory you use every day

Status: proposal, 2026-10-07, waiting for the owner's decisions in §13A. Facts about the current state are marked **Verified**, with their source. Everything else is proposed. It was written by five independent planners (owner first, experience, platform, growth, skeptic), scored by two judges, merged, checked by a critic against the repository and revised.

## Read this first

- **Who it serves first: Wesley's video agency**, not an imagined brand. Today his money flow (prospect → preview → WhatsApp → Pix → Drive) lives in the CLI, a spreadsheet and Paperclip, and the specified MVP does not cover it. The first usable product is a **Desk** that runs that flow, on the same daemon, store and event log the factory needs anyway (§5, phases 1a to 4).
- **Three views of one state**, as the owner asked: **Classic** (lists first, the fastest and accessible path, phone default), **Hybrid** (Classic plus a live strip or house of the factory, desktop default) and **Game** (the approved cutaway houses). Every action lives in one **DecisionCard** used by all three; a parity test keeps them equal (§4).
- **The scene becomes an instrument.** Weather is system health, a bell is a gate, a coin is a Pix, a boat is a message waiting for a reply, lamps are real sub-steps, the plaza sign is what happens next. Ambient water, plants and tappable props stay as delight (§4.3, §6).
- **Signature moments**: money-first Today, while you were away, Face ID batch confirm, two-tap send, Pix lands, the client link (approve, pay, download), the lot contact wall, Factory Wrapped (§6).
- **Backend**: one daemon, SQLite as the single source of truth, persisted gates with passkey-bound confirms, jobs with `run_at`, a render lane sized for the real B-roll times, Telegram then Web Push, encrypted nightly backup, a secret-free public edge for client links (§7).
- **Found on the way**: a latent bug where a paid B-roll sale would be delivered in the old visual (§2), real B-roll render cost of 9 to 12 minutes per lead (§3), a GSAP license to read before going public (§9.1), and approvals that must bind to the spec, not to the file (§5.2).
- **Order**: clean ground (Phase 0), the Desk sends, keeps the books, takes the money, produces, then the client link, content plans and his own brand, the living factory everywhere (v0.4.0), and only then public (§10). Each phase ends with a fact about his real work.
- **What the owner decides now**: six questions in §13A.

Naming used throughout: **`prospect-v1`** is the current route on main (text and animation over a background, `preview.mp4`). **`broll-v2`** is the official B-roll route on `feat/visual-broll` (`preview-v2.mp4`, `final/final.mp4`). A bare "v1" or "v2" is never used, because "padrão v2" on main means something else: Laomedeia voice, real logo and Lothus rhythm (`docs/venda-ativa.md:16`).

---

## 1. North star

Simplicio Video is the one place where a one-person video agency runs its whole day. That covers leads, previews, the messages the owner sends himself, Pix charges, delivery, client approvals, recurring content plans and the agency's own posts. The deterministic engine renders every video, and the product itself spends zero LLM tokens. The official `broll-v2` route still needs an agent to write each company's concept and plan, and §13 flags that as a challenge to the zero-token decision. A human makes every irreversible decision, with one hold and one Face ID. The factory scene shows the same state as a living world. Weather is system health, a bell means something needs you, a coin means a Pix was paid, and a robot stands where the work is.

Two rules govern the scene:
- **Elements that draw attention or can be tapped must mean something.** Lamps, pins, signs, coins, boats and robots each bind to real state or lead to a real action.
- **Cheap ambient motion stays because it is the delight the owner approved.** Water, plants, lights and tappable props are kept, and they stop under reduced motion.

Who it is for, in this order:

1. **Wesley's agency.** It is the first daily user, and every phase ends with a fact about his real work, not a feature list.
2. **Small businesses.** Today they meet the product as his clients, through the client link. Later they can run the single-brand content loop themselves, and his own brand (@wesleysimplicio) goes first.
3. **Other agencies and creators.** They come in once the code is public, and later through a hosted version.

---

## 2. Where we are (verified)

- **The factory exists only as a specification.**
  - PR #51 is open, mergeable and unreviewed. No factory code exists: there is no Makefile, `web/`, `src/simplicio_factory`, `themes/` or `scripts/land.sh`.
  - On branch `docs/factory-spec`, 15 files are dirty (`git status`). Nine of them are documentation or catalog updates toward the 2026-10-07 direction.
  - The other six are prototype fixes: the dock's Approve now goes to Review (`dock.check`), the dock's hold is disabled when upload is off, reduced motion follows the OS setting, sound pauses on unmount, and ad thumbnails are cached (`git diff`; `proto.app.js:273-274`, `proto.three.js` unmount, `proto.ads.js` thumb).
  - These edits are committed together with this blueprint on `docs/factory-spec`. At `f83136f` both gate bypasses still existed.
  - The old direction was fixed in `docs/factory/README.md`, `design-review.md`, `themes.md` and `monetization.md` in the same commit. It survives only in `pyproject.toml:11` ("Proprietary", kept until #70 picks the license) and in the title of issue #70.
- **The engine works.** `simplicio-video` v0.3.0 runs validate, voice, compile, HyperFrames and master. 213 tests are collected. A non-render run gives 207 passed and 3 failed, and the 3 failures come from a hardcoded `/projetos/ai/OpenMontage` path (`src/simplicio_video/montage.py:32-33`). The package is not installed in the system Python 3.14.6.
- **The money flow today runs on the CLI.**
  - The sequence is `prospect`, then a watermarked preview, then a WhatsApp or Instagram message Wesley sends by hand, then `venda cobrar` (an AbacatePay Pix that expires in 24 h), then a webhook on `127.0.0.1:8787`, then an HD render in a background thread, then Drive.
  - The Drive link is deliberately not shared, so the client cannot open it (`venda.py:1-41, 164-216`; `publish.py:5-6`).
  - AbacatePay is in test mode until KYC (SIM-116) and the Pix permission (SIM-112) are done.
  - **Latent bug: a paid B-roll sale would be delivered in the obsolete visual.** It has not fired yet only because AbacatePay is still in test mode. `venda entregar`, which the webhook thread also runs, calls `_final_contract` and `do_render(c, "local")`, then uploads the result (`venda.py:229-263`). It re-renders `contract.yaml` through the `prospect-v1` HyperFrames route and never uploads `final/final.mp4`. `venda.py` is byte-identical on main, `cerebro/SIM-117-pix-entrega` and `feat/visual-broll`. A paying B-roll prospect would automatically receive a different video from the `preview-v2` they saw.
- **Sales state lives in five places.** They are `lote.csv` and `venda.json` on the box, a 25-column xlsx that Wesley re-uploads by hand, a Paperclip board reached only over Tailscale (cards SIM-102..130), a Drive sales guide, and the repo (`docs/venda-ativa.md:223-275`).
- **The official visual is `broll-v2`, and it is not on main.** It lives on the unmerged `feat/visual-broll` branch, which contains `feat/int1-internacional-i18n` (`docs/specs/visual-v2-broll.md` on that branch).
  - **Script.** International batches use an agent-written "ficha" per company: pain plus dossier source, and the exact lines. `intl` then turns it into a contract with guards against price or currency, screen text that differs from speech, and lines that do not fit. `--mudo` renders a voiceless layout check (`intl.py:1-16`). `prospect-v1` takes its lines from `setores.json`.
  - **Voice.** Gemini TTS, one request per line, with a permanent "more animated" style for pt-BR. Without a key, Wesley generates AI Studio takes by hand. `broll` itself never calls TTS: it reuses `timing.lock.json`, and `plan.yaml` cites word timings such as `vo3:palavra` (§1.6, §3.1, §4). The plan can therefore only be written after the voice exists.
  - **Concept per company.** Each company gets its own visual concept (`broll/concept.yaml`, `broll/plan.yaml`), with "nenhum conceito repete o de outra empresa do lote".
  - **One music style per company in a lot, with no repeats.** There are 17 styles. Uniqueness is checked by `/workspace/broll-lote2/trilhas12.py`, which exists only on the box (§1.5, §3.2).
  - **Images.** Real client images or licensed stock clips (Mixkit, Pixabay, Pexels, Coverr) are recorded in `assets-licencas.csv`.
  - **FINAL first.** A 1080×1920 FINAL is rendered and tested before the preview reaches Wesley (rule of 02/10). The same spec gives the same sha256 (`test_final_render_is_clean_full_res_and_deterministic`). For a paid delivery, a 720p stock clip should be swapped for the 1080p or 4K version of the same clip, with the same `in` (§7.1).
  - **Render times.** Measured on the 8 vCPU box, a preview takes 2–4 min and a FINAL about 7–8 min. The FINAL stays local until payment.
  - **Drive upload needs approval.** It happens only "depois do OK do Chefe/Wesley para aquele lote" (§8).
  - **The box runs this branch.** Spec §5 says `git branch --show-current # feat/visual-broll (até o merge)`.
  - **Brazil may be paused.** The standard applies "inclusive o Brasil quando voltar", which suggests Brazilian prospecting is paused until it moves to B-roll. This needs the owner to confirm.
- **GSAP is a core engine dependency, and five helpers live only on the box.**
  - On main, 6 templates and 31 motion files load GSAP 3.14.2 from `cdn.jsdelivr.net`. Every render therefore needs the network, as does `npx --yes hyperframes@0.8.97`.
  - The B-roll branch adds a vendored `engine/vendor/gsap-3.14.2.min.js`. It accounts for 4,200 of the branch's 7,899 added `src` lines, and its header says "Copyright 2025, GreenSock. All rights reserved. Subject to the terms at https://gsap.com/standard-license".
  - Five helpers that the B-roll process relies on are not in git: `/workspace/broll-src/final_doc.py`, `/workspace/broll-src/ocr_final.py` (with its own `clipenv` venv), `/workspace/broll-lote2/trilhas12.py`, `/workspace/controle/scripts/qa_v2.sh` and `motion_check.py`.
- **Landing B-roll will conflict.** A dry-run merge shows conflicts with main in `schema/contract.schema.json`, `tests/test_help.py` and `voices/README.md`, plus `README.md` against `docs/factory-spec`. The branch forks before `c35ff25`, so client collection files stay reachable through it.
- **Real Oficial cannot take our MP4.**
  - `ro_import_video` only accepts a workspace AI `video_id`, `ro_estimate_clips` only accepts YouTube/Twitch URLs, and `ro_preview_publication` only accepts clips that already live in Real Oficial (#19; `docs/realoficial.md:26`).
  - `ro_get_account` exposes a rewards section with a referral code, an `invite_link`, referral counts and quests.
  - `ro_share` clip links last 1–6 h and cannot be revoked (live tool schemas).
- **The prototype was approved but is not safe to port.**
  - Measured on a Mac, the house view costs 391 draw calls, 20,393 triangles and 4.2 ms CPU per frame. That is inside #28's budget of at most 400 draw calls and 25k triangles.
  - The world view costs 3,248 draw calls, 155,583 triangles and 11.75 ms. No phone has been measured.
  - Hold-to-publish always confirms `S.pubq[0]`. The themes are JS code, and 1.25 MB of base64 art is inlined into the page.
- **The specification has structural gaps.** There is no Gate entity, no `Job.run_at`, no item index, and no transaction across `item.json` and `state.db` (`docs/factory/contracts.md`). The legacy MCP tools `video.publish` and `video.run publish=true` upload to Drive without a confirm token (`mcp_server.py:86-97`).
- **Personal branding is hardcoded.** The preview watermark is in `render.py:276-278`, the Pix description the client sees is "Video SimpleTI - <slug>" (`venda.py:121`), and the collector's user agent points to simpleti.com.br. `venda webhook serve` and the planned `up` both default to port 8787.
- **The backlog is stalled.** There are 56 open issues under epic #14. The "Simplicio-Loop 24h" dead-lettered 50 of them, with no branches and no PRs. The bodies of #28 and #54 still describe a belt and procedural-only art. No issue covers agency work, layouts, notifications in the MVP or backup. Sub-issues and blocked-by links are empty.
- **The repo cannot go public as it is.**
  - It is private, has no LICENSE, and `pyproject.toml` says "Proprietary".
  - Client data is still in history after `c35ff25`.
  - `tests/conftest.py:10-11` uses the WJR and Lothus client contracts as fixtures. `motion/catalog.json` has 15 `source` lines pointing at `clients/`, and 3 client MP4s are tracked.
  - The B-roll branch adds `templates/broll/exemplos/` with real prospects (two real international prospects).
  - Authors across all branches: 76 commits by Wesley Simplicio identities, one of them as an employer-domain address; 6 by `root@` the VPS (agents); 2 by `wesleysimplicio`.
  - Paperclip runs at the VPS (port `:8443`).

---

## 3. What was missing

| # | Item | Why it matters | Severity |
|---|---|---|---|
| 1 | Agency entities: Deal, Campaign, Brand.kind (own/client/prospect), client approval, charge, delivery | Every step that earns money today (prospect, send, charge, deliver) has nowhere to live in the spec. Without them Wesley keeps using CLI + xlsx + Paperclip and the panel stays unused. | blocker |
| 2 | `broll-v2` and intl on main, plus a home for its script, voice and creative steps | Building "make" against main would produce a visual Wesley has declared obsolete. Each company needs a script, a voice and then an agent-written concept and plan before `broll --check/--qa`. No gate kind or tool exists for any of these steps. | blocker |
| 3 | Uncommitted spec edits and unmerged #51 | Every M0 issue waits for #51. Merging it now would ship the old direction and drop the 15 edited files, including the prototype gate fixes. | blocker |
| 4 | Unattended "paid → client has the video" | The webhook is localhost-only, the key is a test key, the Drive file is unshared, and delivery runs in a thread that dies with the process. | blocker |
| 5 | Paid B-roll delivery renders the obsolete visual | `venda entregar` re-renders `contract.yaml` through `prospect-v1` and never uploads `final/final.mp4` (`venda.py:229-263`, identical on all three branches). A paying client would get a different video from the one they approved. | blocker |
| 6 | Real box time per lead under `broll-v2` | Render alone costs 9–12 min of box time per lead (preview 2–4 min plus FINAL 7–8 min, with the FINAL made first). Voice, `--mudo` layout checks and the wait for the agent's plan come on top and are unmeasured. Every "99 s per preview" capacity number is obsolete for B-roll work. The FINAL-first rule spends most of that time on leads that never pay. | major |
| 7 | One source of truth: authoritative SQLite, persisted Gate, `run_at`, schedules, item index | Today a crash between file and event leaves the runner inconsistent. The Today screen, the Kanban, follow-ups and charge polling have nothing to query. | major |
| 8 | Approval identity across renditions | The client approves a watermarked 540×960 preview and receives a different clean 1080×1920 file. Approvals must bind to the spec, not to output bytes. The `venda entregar` bug (row 5) is exactly this failure. | major |
| 9 | Human gates that hold against local agents | The terminal OTP and the TTY check can be read or faked by agents with shell access. Agents commit as root on the VPS, and the legacy MCP publish is ungated. | major |
| 10 | Notifications in the first usable release | Gates, payments and follow-ups wait on a human, and notifiers are scheduled for M2 (#24). | major |
| 11 | Where the daemon runs, and HTTPS for the phone | It is unverified whether "the box" (`/workspace`, `/home/box`, userspace Tailscale) is a VM or a container, whether it has systemd, and whether it is the VPS. PWA install, Web Push and passkeys need HTTPS. | major |
| 12 | Import of the existing pipeline | The importer must read the xlsx, `lote.csv`, `venda.json` and the box prospect folders, keeping the human IDs (P0xx, INT-1, INT-2-BR). Without it day one is an empty screen. All 10 Guarulhos previews and Lothus v02 predate B-roll. | major |
| 13 | Outreach safety and per-country rules | Opt-out, send window and daily cap depend on discipline alone. International prospects (US, SG, AE, DE, CH) fall outside LGPD's B2B legitimate interest. | major |
| 14 | International payment | AbacatePay Pix is BRL and the price list is R$120/80/60. No file mentions USD or another provider. A "yes" from an international prospect cannot be charged. | major |
| 15 | Lot rules versus campaign size | One concept and one music style per company in a lot, from 17 styles, checked by a box-only script. An 80-lead campaign cannot satisfy that as one lot. | major |
| 16 | Asset provenance and licenses | Stock clips (with the 720p-to-higher-resolution swap for paid delivery), client photos, the "never download from Instagram" collector rule, five box-only scripts and the GSAP license all need a ledger and a decision before anything is public or hosted. | major |
| 17 | Backup, restore and updates without migrations | Deals and payments will live in the store. Pre-1.0 "refuse layout mismatch" can strand them. | major |
| 18 | Engine not daemon-safe | The engine raises SystemExit almost everywhere and `rmtree`s `build/` next to the contract, so in-process jobs die or overwrite each other. | major |
| 19 | Money edge cases and paperwork | Refunds (full only in AbacatePay's `refundTransparent`) and disputes (`UNDER_DISPUTE` in `listTransparent`) need handling. Charge re-issue should be an explicit transition. Each sale may need an NFS-e, and production KYC may need a CNPJ. | major |
| 20 | A layout model, the idle state and URL routing | "Two layouts" has no issue. The normal state (nothing needs you) has no design, and the prototype has no URLs or back button. | major |
| 21 | Real-device performance and listening tests | The phone kill criterion (≥30 fps, 200 items) has never been run, and the sound has never been listened to. | major |
| 22 | Machine QA visible on the review card | B-roll has `qa-broll.json` and a 20-frame sheet. The `prospect-v1` route has no contact sheet, no STT check and no frozen-frame check. | minor |
| 23 | Branding as workspace config | Wesley's name is in every preview, and SimpleTI is on the Pix statement. | minor |
| 24 | Port and domain planning | Port 8787 collides. Tailscale Funnel exposes a whole port, not a path, and Paperclip already uses `:8443` on the VPS. A ts.net address with a port looks like phishing to a client paying a Pix. | minor |
| 25 | Retention tied to deals | The global 14-day preview retention is shorter than follow-ups, re-sales and version disputes. | minor |
| 26 | Agent token cost of authoring, and the zero-token decision | The product spends zero tokens, but the official route cannot run without an agent writing concepts and plans. Wesley's real cost per lead includes those tokens, and a public user would need their own agent. | minor |
| 27 | Funnel metrics | Previews, sent, replied, paid and R$ exist only in the xlsx. | minor |
| 28 | Backlog structure | The #28 and #54 bodies are stale, there is no blocked-by graph and no needs-owner label, and the dead-lettered drain could repeat. | minor |

---

## 4. Three ways to see the same factory

The owner asked for two layouts: the game, plus a traditional or hybrid one. The answer is one DOM UI and one scene interface with three renderers, composed into three views:

- **Classic** (pt-BR: Clássico) is lists first and complete on its own.
- **Game** (pt-BR: Fábrica) is the approved factory scene.
- **Hybrid** (pt-BR: Híbrido) is Classic with a scene pane. In early phases the pane is a cheap 2D band, and later it becomes a live house view.

No feature exists in only one view. Classic ships first, so the scene can never be the only way to do something. A first Game slice arrives in Phase 3, not at the end.

### 4.1 Classic (Clássico)

- **For whom:** Wesley on a working day, especially on the phone. It is also for keyboard and screen-reader users, devices with weak or no WebGL, and anyone who wants speed.
- **What it shows:**
  - **Today.** Open gates ordered by how soon they turn into money: Pix paid (deliver), replies waiting, messages to send, follow-ups due, previews to review, failures, disputes (in red).
  - **An "Up next" strip:** the next follow-up, next scheduled post, next metrics window, Real Oficial credits reset at 21:00 BRT, and the next backup.
  - **Pipeline:** a Kanban of deals by stage.
  - **Campaigns:** a tile grid per lot, the lot contact wall, and the funnel.
  - **Deal and item detail:** player, QA numbers, timeline, charge, delivery and receipt.
  - **Clients and leads:** a searchable table that shows the P0xx reference and campaign code.
  - **Activity** and **Settings.**
  - **When nothing needs you:** an "All clear" card with what happens next and the last 24 h in three lines.
- **How it works:**
  - Plain DOM pages over the shared store. Every decision opens the one **DecisionCard**, the same component in every view.
  - Keys: J/K to move, A/N/D to decide, Ctrl/Cmd+K for the command palette, G to switch view. Single-key shortcuts can be turned off.
  - On the phone: bottom tabs, the prototype's peek/half/full bottom sheet, and swipe review. Swipe right is enabled only when the checklist is complete. Swipe left asks for a reason. Discard is always a button.
  - It never loads WebGL.

```
PHONE (Today)                         DESKTOP
+------------------------------+      +--------------------------------------------------------------------+
| Today      Natal 26   (o) ok |      | [Agency v] [Ctrl+K]   (o) clear   Needs you 5  Classic|Hybrid|Game |
| R$ 360 received today    [5] |      +-----------+-----------------------------------+--------------------+
+------------------------------+      | Today   5 | NEEDS YOU (by money)              | DECISION CARD      |
| $ Pix paid  Lothus  R$120    |      | Pipeline  | $ Pix paid  Lothus R$120  deliver | [ 9:16 player ]    |
|   final ready      [Deliver] |      | Campaigns | < 3 replied               [open]  | sheet  QA ok       |
| < 3 replied         [Open]   |      | Clients   | > 8 ready to send         [send]  | [x]facts [x]logo   |
| > 8 to send         [Send]   |      | Review 12 | ! 5 follow-ups (R$60 suggested)   | [ ]music  spec 3f2a|
| ! 5 follow-ups      [See]    |      | Activity  | > 12 previews to review           | (A) (N) (D)        |
| > 12 previews to review      |      | Settings  | UP NEXT 18:00 follow-ups | 21:00  | [= hold + Face ID =]|
| x 1 render failed  [Retry]   |      |           | credits reset | 03:00 backup      |                    |
| Up next: 18:00 follow-ups    |      +-----------+-----------------------------------+--------------------+
+------------------------------+
| Today Pipeline Camp.   More  |
+------------------------------+
```

### 4.2 Hybrid (Híbrido)

- **For whom:** Wesley at the desk. It is the desktop default from Phase 3 on.
- **What it shows:**
  - **Phases 3–5:** a thin 2D SVG band of the 7 houses above Classic. It shows counts per stage, the render in progress with its percent, a coin when a Pix lands, a bell on the house that needs you, and weather as a sky tint.
  - **From Phase 6:** the band can grow into a live pane of the selected item's house, with a timeline scrubber for "while you were away".
- **How it works:**
  - It is a composition of Classic plus a scene pane, not a third UI.
  - Tapping a house filters the lists. Selecting a row moves the scene to that item's house and room.
  - The band needs no WebGL and no Three.js download. It is also the Game's 2D fallback.
  - If the live pane misses its frame budget, it drops to the band without slowing the lists.

```
PHASE 3-5 (band)
+--------------------------------------------------------------------+
| Workshop Idea shop Factory  Garage   Market   Observ.  Barn  (rain)|
|   12       4      [##-]3   (!)12      8 >     R$360    wk 41       |
+-----------+--------------------------------------------------------+
| Today     | Review (12)                                    A  N  D |
| Pipeline  | [>] Café Aurora Guarulhos QA ok   -14.0 LUFS  sync 12 ms |
| Campaigns | [>] Padaria Lume ...                                     |
+-----------+--------------------------------------------------------+
PHASE 6+ (live pane)
+-----------------------------+--------------------------------------+
| NEEDS YOU (3)               |  live house: inspection garage       |
| > Review 'Café Aurora'   <==> |  robot at the bench   pin (!)        |
| [player] [x][x][ ]          |--------------------------------------|
| (A)(N)(D) [hold + Face ID]  | 22:00 |---*-----------| now (12)     |
+-----------------------------+--------------------------------------+
```

### 4.3 Game (Fábrica)

- **For whom:** Wesley when he wants the overview, as a second screen, as the ambient idle screen, for showing a client or an audience, for first-run onboarding, and later for the public window.
  - **Desktop from Phase 3:** a house view of real data. Decisions open the DecisionCard.
  - **Phones from Phase 6,** and only if they pass the frame budget.
- **What it shows:** the approved scene. Seven cutaway houses stand on a ring: workshop (brand), idea shop (ideas), video factory (make), inspection garage (review), launch market (publish), observatory (metrics) and learning barn (report) (`themes.md:72`).
  - A robot walks room to room.
  - Arrows and swipe move house by house, and the world view is look-only.
  - The painted br worlds have moving water, plants and lights, tappable props and procedural sound.
  - Template bots answer from the store (Phase 6).
- **Agency work uses the same 7 houses, with no new house:**

| House | Agency work it shows |
|---|---|
| Workshop | Lead collection, scripts, voices and brand kits |
| Idea shop | Campaigns, lots and the seasonal calendar |
| Video factory | Plan authoring and renders |
| Inspection garage | Owner review, the lot contact wall and client answers |
| Launch market | Send, charge, deliver, publish (a truck leaves when a final ships) |
| Observatory | The funnel, plus social metrics later |
| Learning barn | Weekly revenue and what converted |

- **How it works:**
  - **The scene is a pure projection of the store,** driven by a **binding table** stored as data:
    - weather from `health.level`;
    - room lamps from sub-step state or `job.progress`;
    - pins from open Gates;
    - the plaza sign from the next upcoming event;
    - coins from `charge.paid`;
    - boats from deals sent and waiting for a reply;
    - sleeping robots for quiet hours or a paused loop.
  - **A test fails** if an interactive or attention-drawing element has no binding. Ambient layers (water, plants, lights, birds) are declared as ambient in the theme and exempt. Tappable props stay as pointer-only delight with their own little reactions, and they invoke no command.
  - **This refines the earlier "rooms as the UI" idea.** Rooms are instruments and shortcuts. A room lamp shows real state, and tapping it opens that step's panel with its error and Retry.
  - **Every decision opens the same DecisionCard,** docked over the scene with the prototype's safe-area camera offset. Building each decision twice would double the work and leave canvas-only controls inaccessible.
  - **The prototype's dock shortcuts are not carried over,** even in their fixed form. Every approve and publish goes through the DecisionCard.

```
DESKTOP
+--------------------------------------------------------------------+
| (o) 14:02  Needs you 3   < Inspection garage 4/7 >  Classic|Hyb|Game|
|   painted world, light rain = 1 failed render                       |
|   +---------------+---------------+----------------+                |
|   | Checklist   o | Match spec  o | Decide (!)   R |  room lamps    |
|   +---------------+---------------+----------------+                |
|   == belt ==[itm]=====[itm]=======>     plaza sign: next 18:00      |
| +-- DecisionCard (same component as Classic) -----------------+    |
| | [9:16] [x][x][ ]   (A)(N)(D)   [==== hold + Face ID ====]   |    |
| +-------------------------------------------------------------+    |
+--------------------------------------------------------------------+
PHONE, Phase 6+ (o = lamp, R = robot)
+---------------------------+
| (o) [3]    < 4/7 >    [C] |
| [room o][room o][R  (!)]  |
| == belt ==[itm]=====>     |
+------- sheet: peek -------+
| Following: Café Aurora      |
| Decide: checklist 2/3     |
+---------------------------+
```

### 4.4 One state and one set of actions

- **One daemon, one event log, one store.**
  - The client loads `GET /api/v1/snapshot` (tagged with `as_of_seq`), then follows `SSE /api/v1/events?since=<seq>` and resumes from the last seq.
  - One pure reducer, `reduce(state, event)`, runs in the browser, in the time-lapse replayer and in the tests, which use the events recorded by `demo --record`.
  - Derived selectors: `needsYou`, `board`, `funnel`, `stageCounts`, `renderProgress`, `upNext`, `health`.
- **Shared URLs.** `/today`, `/pipeline`, `/campaigns/:id`, `/deals/:id`, `/items/:id`, `/gates/:id`. A notification, the command palette or a reload opens the same object in any view. The view itself is never in the URL.
- **Actions generated from the command registry.**
  - Each command declares its affordances (button, swipe, hold, tap on a room or pin).
  - A **parity test** fails if a command is reachable in Game but not in Classic.
  - Gate actions are never optimistic: the UI waits for `gate.resolved`.
  - The server enforces every gate, so a UI bug in any view cannot bypass one.
- **Preferences.** The view, sound and reduced-motion settings are stored per device on the server (`devices.ui`), with a workspace default `ui.layout_default`. Themes restyle only the scene. The light-blue system color and the DecisionCard look the same everywhere.

### 4.5 Switching

- **How to switch.** A Classic | Hybrid | Game control in the top bar, the G key, or "switch view" in the palette.
- **What survives a switch.** The URL, the selection, the open card, a half-written change note and focus all carry over. Game flies to the house of the selected item, and Classic scrolls to it. The switch is disabled while a hold-to-confirm is in progress.
- **Loading.** The scene chunk loads on the first switch and then stays warm: the render loop pauses and the AudioContext is suspended, and it is disposed after a few minutes away. This replaces the prototype's measured 112 ms rebuild and forced context loss on every visit.
- **Automatic downgrades go one way only and are announced in text:** high → low quality → 2D band → static postcard → Classic after repeated context loss. Nothing ever moves the user out of Classic automatically.
- **Ambient mode (opt-in, Phase 6).** After an idle timeout with no open gates, the desktop fades into Game. Any input, or a new needs-you event, returns to the previous view on the item that needs attention.

### 4.6 Defaults by device and first run

- **Phone default: Classic.** From Phase 6, a static "living postcard" header shows the house that needs you, with its weather, as a WebP plus CSS, not a canvas. Game is one tap away from Phase 6. It becomes the phone default only if the user picks it and the device passes the frame budget.
- **Desktop:** Classic in Phases 1–2, Hybrid from Phase 3, with Game available as a desktop house view from Phase 3.
- **First run with imported data:** a short replay of the imported pipeline ("92 leads, 2 clients, R$ received") in the band or the desktop Game (Phase 3). It lands on Today.
- **First run with no data:** the offline Acme Coffee sandbox, which plays the full loop with fake publishers.
- **Reduced motion or Save-Data:** Classic, with a static band.
- **Second screen or TV:** Game in ambient mode.
- **Sound:** off by default. Earcons are offered at first run, and ambience is a Game-only toggle.

### 4.7 Accessibility

- Classic is the complete path and must meet WCAG 2.2 AA. axe in Playwright must show zero serious or critical violations.
- **The canvas is `aria-hidden`.**
  - A focusable Scene navigator (houses → rooms → items) mirrors the selection.
  - Every scene element that opens something has an entry in the navigator.
  - Tappable props keep their hit areas as pointer-only delight. They trigger no command, so they need no DOM twin.
- The OS `prefers-reduced-motion` setting drives the 3D as well as CSS: the camera stays static, particles and ambient motion are off, and the replay becomes a 3–6 frame storyboard.
- Toasts and new gates are announced in a live region: polite by default, assertive only for gates.
- Hold-to-confirm has a non-timed alternative, the passkey prompt or a two-step button. The token and Real Oficial preview countdowns are announced.
- Every state has a shape or icon in addition to its color. Every sound has a visible text event.
- Logical CSS keeps RTL possible, and touch targets are at least 44 px.

### 4.8 Performance budgets (targets; measured on named real devices)

| Surface | Budget |
|---|---|
| Classic | Initial JS ≤150 KB gzip, inside #23's 250 KB non-scene cap, with no Three.js. LCP ≤1.5 s and INP ≤200 ms on the reference mid-range Android over Tailscale. Lists virtualized beyond 100 rows. Video lazy-loaded with poster frames produced by the render job. |
| Band | Pure SVG. ≤2 ms to apply an event batch. |
| House view | ≤400 draw calls and ≤25k triangles (#28). The Mac measured 391 and 20,393, so instancing and merged static props come before anything is added. One shadow map, 1024² on phones (the prototype defaults to 2560²). |
| World view | Desktop first, brought to ≤800 draw calls (3,248 measured on the Mac). Phones are decided by the Phase 0 measurement: if they miss the budget, they get a 2D painted map. |
| Particles | Desktop: GPU-driven, ≤300 points (the prototype moves up to 900 in JS every frame). Phones: decided by the Phase 0 measurement. |
| Theme art | Backdrops as files, ≤150–200 KB each. Only the current house ±1 is loaded. No base64 inlining. |
| Runtime | Render on demand: 0 fps in a hidden tab, ≤15 fps of ambient motion when idle. JS heap ≤80 MB on the phone. A webglcontextlost handler falls back to the band. |
| Kill criterion | ≥30 fps with 200 coalesced items on the named mid-range phone, or phones default to the band or postcard with the same event mapping (design-review.md:80). #28's "at most 100 animated items" is reconciled with this when #28 is rewritten. |

---

## 5. The agency layer

### 5.1 What he runs today (verified)

- **Building the lead list.** Wesley builds the list by hand from web search.
- **`prospect-v1` route.** `prospect` collects public site data, routes by sector, takes its lines from `setores.json` and makes a watermarked preview.
- **`broll-v2` route.**
  - For international batches, an agent writes a ficha per company (pain, dossier source, exact lines).
  - `intl` makes the contract. Gemini or AI Studio takes produce the voice.
  - An agent on the box writes a concept and plan per company, unique within the lot.
  - `broll --qa` and `broll --final --qa` render the preview and the FINAL.
- **Selling and delivering.**
  - Wesley reviews each preview and sends the message himself, with no price in the first message.
  - Prices are R$120, R$80 only if the client asks, and R$60 after 3 days.
  - Then `venda cobrar` runs, the webhook fires, delivery happens and Drive gets the file.
- **Who is in the pipeline.**
  - Clients: WJR (sold at R$60) and Lothus (Dia das Crianças v02, waiting for client approval, made before B-roll).
  - A 10-company Guarulhos pilot from 30/09, all of it `prospect-v1`.
  - International prospects (P061–P082, batches INT-1 and INT-2-BR) on unmerged branches.

### 5.2 The model (proposed)

- **One workspace is the agency**, holding many brands. `brand.kind` is `prospect | client | own`. Each brand keeps its human reference (`ref_code`, for example P061) and each campaign its code (INT-1, INT-2-BR), because Drive folders and conversations use them.
- **A Campaign** combines occasion, date, country, currency, route (`broll-v2` or `prospect-v1`), template, price list, send window and daily cap. It fans out to N brands, split into **lots** of at most 17 companies for `broll-v2` (one concept and one music style per company, unique within the lot; see §13A-5).
- **Each lead produces an item and a Deal.** The item carries production and approval. The Deal carries the commercial stages: `lead, producing, preview_ready, approved_to_send, sent, replied, interested, charged, paid, customizing, delivering, delivered, lost, opted_out, refunded, disputed`.
- **Approvals bind to the spec.**
  - Every approval binds to `spec_hash`, the sha256 of contract + concept + plan + timing lock + asset hashes.
  - The preview and the FINAL are two renditions of one spec.
  - If the concept or plan changes, the hash changes and every open gate on that item is superseded automatically.
  - Swapping a stock clip for a higher-resolution variant of the same clip (same source id and `in`) is recorded as an asset upgrade on the same spec. It does not supersede the approval.
- **Agency code ships as first-party plugins** (prospect, deals, charge-abacatepay, deliver-drive, client-link) over the same host services, gates and event log as the content loop. His prices, scripts and branding are workspace data, never in the repo.

### 5.3 The daily flow under `broll-v2`

Until Phase 3, steps 3–6 still run on the box through the CLI and agents, and the Desk imports their results.

1. **Lead in.** A lead comes from a CSV, saved leads, past clients or the phone's share sheet.
   - The opt-out list and the country policy are checked first.
   - Missing pieces become small gates instead of silent `aguardando_*` rows. Examples: no logo, no OAB number for law firms, no voice.
2. **Collect.** `lead.collect` runs the public, robots-respecting, PII-stripped collection.
   - The product never downloads from Instagram.
   - A logo Wesley takes by hand is uploaded with its source recorded.
3. **Script.**
   - `prospect-v1` takes its lines from `setores.json`, deterministically.
   - `broll-v2` international work uses a ficha (pain, dossier source, exact lines) that the agent submits through `item.submit_script`.
   - The `intl` guards run on submit: no price, currency, discount or "free"; screen text equals speech; each line fits its slot.
   - An optional `--mudo` layout check renders without voice.
4. **Voice.** An `item.voice` job calls Gemini, one request per line.
   - pt-BR uses the animated style, and identical lines are reused across companies through the cache key.
   - The campaign shows a voice estimate and needs one confirm when it spends.
   - A 429 triggers backoff.
   - Without a key, a `voice_takes` gate asks Wesley for AI Studio WAVs, uploaded from the Desk or by an agent (`item.voice_takes`). The output is `timing.lock.json`.
5. **Author.** An `author` gate opens.
   - His own agent picks it up over MCP. `item.brief` carries the lines, word timings, brand facts, B-roll constraints, and the concepts and music styles already used in the lot.
   - The agent submits the concept and plan (`item.submit_plan`) and the assets (`item.add_asset`, each with a license row).
   - The daemon runs `broll --check` plus the lot uniqueness check and returns the errors.
   - Agent tokens are recorded as *reported by the agent*, never as measured by us.
6. **Render.** The preview renders with QA and the 20-frame sheet. Then, depending on §13A-4:
   - **(A)** the full FINAL with QA (7–8 min);
   - **(B)** a short full-resolution probe with QA (the first 2 s and the end card), with the FINAL rendered at payment.
7. **Owner review.**
   - One DecisionCard per item shows the player, the 20-frame sheet, the QA numbers (LUFS, true peak, sync, no-watermark on the final or probe) and the checklist.
   - A **lot contact wall** shows every sheet of the lot side by side, with style and palette chips, so similar concepts are visible before approval.
   - Batch approval takes one Face ID (Phase 2+). The deal moves to `approved_to_send`.
   - If Chefe is an agent (§13A-6), its QA verdict appears on the card as an annotation. It never resolves the gate.
8. **Send, by Wesley.**
   - "Open WhatsApp" opens `wa.me/<published commercial number>` with the approved first message (no price).
   - "Open Instagram DM" opens `ig.me/m/<handle>` and copies the script to the clipboard, because ig.me cannot prefill text.
   - "Share preview" opens the phone's Web Share sheet with `preview-v2.mp4`.
   - Back in the app it asks "Sent?" and logs a touch. The product never sends anything.
9. **Reply.** One tap: replied, interested, lost or opt-out. A box agent can also log a reply through `deal.log_reply`.
10. **Price and charge.**
    - Wesley picks the tier. The product proposes; it never discounts by itself.
    - A hold plus passkey creates the charge in the campaign's currency, through a provider that can take it. For now that means Pix in BRL only, and the charge gate stays closed when `campaign.country != BR` until §13A-3 is decided.
    - **Share Pix** copies the copia-e-cola code, opens Web Share with the QR PNG and opens `wa.me` with a prefilled payment message. The touch is logged as "charge sent".
11. **Pix lands.** Polling detects the payment. Wesley gets a push and a coin sound, and the deal moves to `paid`.
12. **Deliver.**
    - **Asset upgrade.** If the asset ledger shows a 720p stock source that has a higher-resolution variant, an `upgrade_assets` step fetches it and re-renders the FINAL from the same `spec_hash` (about 7–8 min).
    - **Render at payment.** Under option B, the FINAL renders now, with any upgrades included.
    - **Otherwise** the existing FINAL is delivered as is.
    - Delivery uploads `final.mp4` as `vNN` (never overwrite) to the workspace's Drive path template and opens a share step. The receipt shows which path was taken.
    - If the sale promised client photos, a different voice or other changes, an optional `customizing` gate re-renders first. Changes to the concept or plan create a new spec.
13. **Paperwork.** The invoice status is recorded on the deal: not required, pending or issued, with a number. Refunds are a human-confirmed gate.
14. **Follow-up.** A `followup` schedule fires at `sent_at + 3 days`, moved into the send window. It opens a gate suggesting R$60. It never applies the discount.

### 5.4 Clients and brand kits

A client's brand kit holds:
- the real logo with its source;
- the palette;
- the chosen voice (Laomedeia, Puck, Achernar);
- confirmed facts, each "confirmed by X on date";
- the written authorizations from `checklist-cliente.md` (brand use, people's image, music, script approval, video approval);
- who posts where.

The spec's claim guard blocks any number, price or phone on screen that has no matching fact. Clients post their own videos, which is today's practice.

### 5.5 Seasonal campaigns, lots and capacity

- **The calendar.** Each Brazilian commercial date (Dia das Mães, Dia dos Namorados, Dia dos Pais, Dia das Crianças, Black Friday, Natal) shows its readiness: visual ready, leads queued, previews done, last campaign's conversion.
- **Lots.** A `broll-v2` campaign is split into lots of at most 17 companies. `item.plan_check` enforces one concept and one music style per company within the lot, which replaces `trilhas12.py` on the box. 80 leads become 5 lots.
- **The `campaign_start` gate.**
  - It shows a capacity estimate based on measured p50 per step from job history: voice, `--mudo`, the agent's wait to deliver a plan, `--check`, preview and FINAL or probe.
  - It shows the finish time on one lane.
  - Render time alone for 80 leads is about 12–16 h under option A, against an estimated 4–7 h under option B. The probe time is an estimate until measured.
  - If the finish lands after the occasion date, the gate says so, and Wesley cuts the batch or adds capacity.
- **Budgets.** Each campaign has its own render budget, so the global `renders: 40/day` and `max_in_flight_items: 10` defaults do not stall a batch.
- **Imported `prospect-v1` previews.** Each gets a `rerender_broll` gate: re-render on `broll-v2`, sell as is, or archive. Seasonal previews whose date has passed are archived unless the deal is already in conversation.

### 5.6 Outreach safety

- Humans send every message.
- Each campaign has a send window and a daily cap.
- A global opt-out list (hashed) is checked before any send gate opens. Opting out from a link, a reply or by hand blocks the business in every future campaign.
- Only published commercial contacts are stored. Contacts never go into events, logs or git.
- Lost and opted-out deals have their contact fields blanked after a retention period.
- **Countries.**
  - A campaign may target a country only if `agency/countries/<cc>.yaml` exists and records the reviewed legal basis note, the allowed channels, the opt-out wording, the retention and the payment path.
  - Without it, send and charge gates stay closed.
  - LGPD's B2B legitimate interest does not cover GDPR (DE), the Swiss data protection law (CH), PDPA (SG) or the UAE. That review is an owner task with a lawyer. The plan does not decide legality.

### 5.7 Money rules as code invariants

- One open charge per deal, and only one code path that creates charges.
- The webhook or poll amount must equal the charge amount.
- Replays are no-ops. `externalId = deal_id|attempt` is set on every charge.
- A charge that expires unpaid moves the deal back to `interested` and keeps its id in `previous_charge_ids`. Main already re-issues on expiry (`venda.py:88-109`).
- Refunds are full only, which is what AbacatePay's `refundTransparent` does ("Reembolsa integralmente"). A partial refund needs a different path and is not modelled.
- A charge reported as `UNDER_DISPUTE` moves the deal to `disputed` and shows as a red gate in Today.
- A confirmed payment authorizes automatic delivery of *that* video only. This is the existing rule in AGENTS.md.
- A daily reconcile runs against AbacatePay's listing, and its result shows in the funnel.
- No charge gate opens for a currency without a configured provider.

### 5.8 Delivery and retention

- **Drive delivery.** It uses the Drive publisher from `publish.py`: never overwrite, same bytes are idempotent, the link is built by file ID, and names follow the `vNN` convention.
- **One Drive path template, stored as workspace data.** Today two conventions compete. `AGENTS.md` uses `clientes/NOME_CLIENTE/ANO/CAMPANHA/<CLIENTE> - <descricao> - vNN.mp4`, and the B-roll spec moves `prospects/2026/<INT>/<PAÍS>/P0xx-<slug>/` to `clientes/<PAÍS>/...`. The owner picks one (§13B), and the deliver plugin computes it.
- **Phases 2–3:** "share with client" is an explicit confirm that shares that one file and prepares the WhatsApp message.
- **From Phase 4:** the client link streams the download, and the Drive file stays private.
- **Retention.** Previews and finals tied to an open or paid deal are kept until the deal closes plus a configured period. The global 14-day preview retention applies only to orphans.

### 5.9 Client share page (Phase 4)

There is one link per deal, on Wesley's own domain (§13B-19). It shows:
- the watermarked preview, with version and receipt;
- **Approve** and **Ask for a change**, both bound to `spec_hash` (a comment becomes `needs_changes`);
- the Pix QR and copia-e-cola from the deal's charge;
- photo upload for the paid version, stored as external-origin assets with size and type limits;
- the HD download, which unlocks only after payment;
- "don't contact me again".

How the page is built:
- **Language and accessibility.** It renders in the item's content language. en and pt-BR come first; others are marked experimental until reviewed. It meets WCAG 2.2 AA with zero serious axe violations.
- **Security.** It is server-rendered by the secret-free edge process (7.6), with no panel JS, no cookies, no third-party assets and a strict CSP.
- **Order of approvals.** Prospects approve by paying. Plan clients approve each item. The order is always owner review, then client review, then delivery, and a client decision never authorizes a publish.

### 5.10 Funnel

Per campaign, per lot and per week, the funnel shows:
- previews made, sent, replied, charged, paid, delivered;
- R$ received, conversion, refunds, disputes;
- measured box minutes per lead, by step;
- voice cost per lead;
- agent tokens per plan, reported and labeled as such.

The funnel comes from deals, not from a spreadsheet. A CSV/xlsx export reproduces the columns of `controle-vendas-videos.xlsx`, so the spreadsheet habit survives while the store is the source of truth. After Phase 1 the xlsx is retired, and Paperclip keeps only process and dev cards.

### 5.11 Relation to the single-brand loop

It is the same item pipeline with different end steps: brand → ideas → make → owner review → [client review if the brand is a client] → deliver (Drive or link) or publish (Real Oficial or export) → metrics → report. Three uses share it:
- prospects: one-off, ending at delivery;
- client content plans: N videos a month, a monthly Pix, client approval (Phase 5);
- his own brand: the spec's single-brand loop, fed by portfolio videos (Phase 5).

### 5.12 What stays out

- Automatic lead discovery and scraping of Maps or Instagram.
- Automatic sending.
- Posting on clients' accounts through his Real Oficial login. That waits for agency multi-account plus written client consent.
- Hypit `clone` as a client service, because its license forbids it.

---

## 6. Signature features (extraordinary and useful)

| Name | What | Why it helps | Size |
|---|---|---|---|
| Money-first Today | One screen of open gates sorted by what turns into money soonest. When clear, it shows pipeline value, received this week, the next occasion and "prepare next campaign". | Replaces opening the xlsx, Paperclip and box folders every morning, and designs the idle state. | M |
| One DecisionCard everywhere | Real 9:16 player, sheet, QA numbers, spec hash, checklist, A/N/D, hold + Face ID, export fallback. Every view and every notification deep link opens it, and the server refuses what the card would refuse. | Removes rework between views and keeps dock-style shortcuts from coming back: every approve and publish goes through one component, and the server checks it again. | M |
| Face ID batch confirm | For gates with side effects, the passkey assertion signs `sha256(gate_id \| payload_hash \| nonce)`. A batch signs the hash of the sorted payload hashes, so one Face ID approves 12 previews feeding a send. | Faster than typing, and it proves a human decided even with root agents on the box. A story people repeat. | M |
| Two-tap send | `wa.me` or `ig.me` with the approved script, then Web Share of the preview file, then "Sent?". Opt-out in one tap. The same pattern shares a Pix: copia-e-cola, QR via Web Share, prefilled `wa.me`. | The most manual part of his day, and it keeps "humans send everything". | M |
| Pix lands | Polling detects payment, then a push and a coin sound, then delivery (as is, upgraded, or rendered now), then a share card. | Removes the localhost webhook, `venda entregar` and manual Drive sharing. The coin is a payment signal, not decoration. | S |
| Agent author desk | `script`, `voice_takes` and `author` gates per lead. His agents submit fichas, takes, concepts, plans and licensed assets over MCP, and the daemon returns `--check` and lot-uniqueness errors. | Brings the B-roll creative steps into the record, and lets agents work from another host. | M |
| Lot contact wall | Every 20-frame sheet in a lot on one grid, with music style and palette chips; duplicates flagged by `plan_check`. | The spec's human QA rule ("conceito diferente das outras empresas") cannot be checked one card at a time. | S |
| Campaign grid with capacity | Tiles per lot fill in as leads go collect → script → voice → author → render → QA. The start gate shows measured finish time versus occasion date. | Seasonal batches are how he sells, and the estimate prevents missing a date. | M |
| Swipe review with machine QA | Phone card stack with the B-roll QA JSON and 20-frame sheet, plus (`prospect-v1`) an ffmpeg contact sheet, a faster-whisper transcript diffed against the contract lines, and a framemd5 frozen-frame check. | Review is the human bottleneck, and the QA reuses code that already exists. | M |
| Client link | Preview, approve or change, Pix, photo upload, HD after paid, opt-out, all in one URL on his own domain, in the client's language. | Replaces four manual WhatsApp steps, and it is the screen non-users see most. | L |
| While you were away | A digest built from events since the device's `last_seen_seq`. Classic shows three lines, the band or Game shows a time-lapse of at most 8 s that lands on the oldest open gate, and the 08:00 push carries the same text. | His most frequent moment: "what happened, what now". | M |
| Weather is health | One `health()` function with severity order and two-check hysteresis. Clear = OK, clouds = warnings, rain = failures waiting, snow = paused/STOP, dust = budget or credits exhausted, fog = daemon unreachable. It also writes the Classic status pill. | Health readable from across the room. Views cannot disagree. | S |
| Sound is a signal | Opt-in earcons: a bell for a gate, a coin for Pix, a knock for a failure. Coalesced, silent in quiet hours, each with a text twin. Ambience is Game-only and off by default. | He can leave the tab in the background and hear when he is needed. | S |
| Up next | The plaza sign in Game and the strip in Classic show the next follow-up, post, metrics window, credit reset and backup. Robots sleep in quiet hours. | The normal "nothing needs you" state carries information. | S |
| Template bots | In Game, the approved bots answer from templates over the store ("what needs me?", "how is Natal going?") and run palette commands. Zero tokens, no fake typing delay. Classic gets the same intents as the palette. | Keeps the approved chat as a fast way to ask the factory a question. | S |
| Seasonal calendar and drops | Dates with readiness. Later (public), a template pack before each date. | Campaigns run on dates. Drops become community moments and sponsor units. | S |
| Follow-up radar | A deterministic gate after `followup_after_days`, inside the send window, with the R$60 script prefilled. | Turns the price rules into reminders without taking the decision away. | S |
| Honest meter | 0 LLM tokens spent by the product, credits used, measured box minutes and R$ per lead, agent tokens as reported, minutes saved against the Phase 0 baseline. | Proves the promise daily and becomes the public case study. | S |
| Verified receipt | Each item shows spec hash, rendition hashes, asset upgrades, `vNN`, the delivery path taken, and who approved it, on which device and when. | Ends "which version did the client approve?" disputes. | S |
| Render cache | Skip a render when a manifest with the same inputs hash exists (ADR-0002 design). B-roll renders are deterministic, so this is safe. | Re-approvals and re-exports become instant. | S |
| Factory Wrapped | A deterministic monthly 9:16 recap per client ("your month with us") and a weekly one for his own brand, rendered by the engine at zero tokens. | Retention for plan clients and shareable growth content. | M |
| Share-to-lead | The installed PWA is a share target on Android: sharing a business link creates a lead and sector routing suggests a template. On iPhone it is a paste box. | Lead capture becomes one gesture without scraping. | S |
| Living postcard and ambient factory | Static per-house postcard on phones. Game as the idle screen on desktop and TV. | Gives the 3D world a daily job at almost no cost on phones. | M |
| Public window | A read-only replay or opt-in signed snapshot of his factory on the public site. The only place sponsor art may appear. | Shows the product working, with zero exposure of his daemon. | M |

---

## 7. Backend

### 7.1 Architecture and host

- **One daemon, `simplicio-video up`.** FastAPI + uvicorn, SQLite WAL, a scheduler thread, and two worker pools:
  - `render`: concurrency sized by `simplicio-video bench`, default 1, because Chrome capture is CPU-bound;
  - `io`: about 4 workers, for collection, voice API calls, AbacatePay, Drive and push.

  The workspace lock refuses a second daemon. The CLI and stdio MCP are short-lived clients of the daemon's HTTP API, which also lets them run on another host over the tailnet with an AgentToken.
- **A separate edge process (Phase 4).** It serves the public pages and holds no provider secrets (7.6).
- **Where it runs (decided after the Phase 0 host check).** The recommendation is the always-on Linux machine where batches render. The check must answer:
  - Is "the box" a VM or a container?
  - Does it have systemd, or is a supervisor needed?
  - Do agents run as root?
  - Is it the same machine as the VPS?
  - How much disk headroom is there?
  - Do `tailscale serve` and Funnel work in userspace networking, and can the node be given a stable name?
  - Which ports are taken (Paperclip uses `:8443`)?

  The Mac stays a client and the restore target. Two daemons never sync.
- **Engine jobs run as subprocesses.** Each job runs the existing CLI with JSON output, at nice 10, inside the item's own folder (`brands/<slug>/items/<itm_id>/`). This contains SystemExit, allows kill on cancel, and stops shared `build/` clobbering. Each job has its own log file. One engine change makes this safe: a work-directory parameter, so outputs never land next to a shared contract.
- **Production pin.**
  - The box's production checkout runs a release tag, and development continues on main.
  - The box moves to a new tag only between campaigns, or after `make check-full` plus a render smoke test on a copy of one live company folder.
  - The rule: never re-tag production while a campaign has renders queued.
  - Until the first tag, the box keeps its current `feat/visual-broll` checkout.
- **Port 8787.** `venda webhook serve` moves off 8787 in Phase 0 and is deleted in Phase 2, when the charge plugin and polling replace it.

### 7.2 One source of truth (this challenges the spec's storage decision)

`state.db` becomes authoritative for every mutable thing: item and deal state, gates, schedules, jobs and publications. Files hold only immutable content: `brand.json` versions, contracts, `timing.lock.json`, concept and plan, renders and manifests.

The write order:
1. Write the new content file.
2. In one transaction: `UPDATE` the row (with an optimistic `version`), `INSERT` the event, `INSERT` the outbox job.

A crash leaves at worst an orphan file, which `clean` removes. `item.json` is deleted from the layout, and `item export` writes it on demand. `EventLog.wait` polls `PRAGMA data_version`, which meets #35's 300 ms wake criterion. The reason for the change: the spec's split between files and the database can leave the stateless runner inconsistent after a crash, and Today and the Kanban need a query.

**Field ownership while the CLI still writes (Phases 1–3).** The Desk and the CLI must never disagree. This table is deleted when Phases 2 and 3 delete the CLI paths.

| Fields | Written by | In the Desk |
|---|---|---|
| Charge status, amount, `paid_at`, delivery link | `venda.json`, read by the importer (Phase 1). The charge and deliver plugins take over in Phase 2. | Read-only with an "owned by CLI" badge until Phase 2 |
| Preview paths, renditions, QA, lot, concept and style | Box folders, read by `import scan` (Phases 1–2). Daemon jobs take over in Phase 3. | Read-only with an "owned by CLI" badge until Phase 3 |
| Touches, sent, replies, interest, lost, opt-outs, notes, chosen price tier | The Desk | Editable |
| Deal stage | Derived: commercial stages from Desk fields, production and money stages from the owner above | Shown with its source |

### 7.3 Data model additions (field names)

New ID prefixes: `del cmp lot gat sch lnk dev crd ses agt msg crv ast ntf`.

- **workspace.yaml**
  - `timezone`, which bounds a budget day and drives Wesley's quiet hours and digest.
  - `agency {display_name, handle, watermark_text, end_card_text, pix_description, user_agent_url, client_link_domain}`, which replaces the hardcoded strings.
  - `delivery {drive_path_template}`.
  - `ui {layout_default: classic|hybrid|game}`.
  - `notify {telegram_chat_id, quiet_hours, coalesce_minutes, digest_at}`.
  - Workspace data outside the repo: `agency/prices.yaml` (price list per currency, each with the provider that can charge it), `agency/messages/<lang>.yaml`, `agency/countries/<cc>.yaml`, `agency/calendar.yaml`.
- **brands** (extends Brand)
  - Identity and status: `kind own|client|prospect`, `ref_code` (P0xx), `status draft|confirmed|archived`, `short_name`, `spoken_name`, `sector`, `city`, `country`.
  - Sources: `site_url`, `instagram_handle`, `source_ref {kind csv|xlsx|share|manual, ref, row}`.
  - `kit`:
    - `logo {path, source_url, sha256, obtained_by}`, `palette[]`, `voice {provider, voice_id}`;
    - `confirmed_facts[{fact_id, confirmed_by, at}]`;
    - `authorizations[{kind, granted_by, at, evidence_ref}]`;
    - `posts_where[]`.
  - Later fields: `cadence {rrule, tz}` (Phase 5) and `opted_out_at`.
- **contacts**: `id, brand_id, channel whatsapp|instagram|email, value, basis b2b_legitimate_interest|consent|client, source, created_at`. Contacts are never written to events or logs.
- **optouts**: `id, value_sha256, channel, brand_id?, source reply|link|manual, at`.
- **campaigns**: `id, code (INT-1…), name, occasion, occasion_date, country, currency, audience prospects|clients|both, route broll-v2|prospect-v1, template_id, language, price_list_ref, send_window {days, start, end, tz}, daily_send_cap, render_budget, final_timing first|at_payment, capacity_estimate {leads, p50_by_step, finish_at}, status draft|producing|selling|closed`.
- **lots**: `id, campaign_id, n (≤17), concepts_used[], styles_used[], status`.
- **deals**
  - `id, brand_id, campaign_id?, kind one_off|plan, stage`, with the stages listed in 5.2.
  - `channel, contact_id, preview_item_id, final_item_id?`.
  - `price_cents, price_kind full|offer|followup|custom, currency`.
  - `sent_at, replied_at, follow_up_at`.
  - `charge {provider, external_id, amount_cents, currency, br_code_ref, expires_at, status}, previous_charge_ids[], paid_at`.
  - `refund {external_id, reason, at}?` (full only), `dispute {opened_at, status}?`.
  - `delivery {publisher, path, file_id, version, kind as_is|upgraded|rendered_at_payment, delivered_at, shared_at}`.
  - `invoice {status not_required|pending|issued, number, issued_at}`.
  - `lost_reason, notes, idempotency_key, version, updated_at`.
- **items** (ContentItem plus)
  - `purpose preview|final|post, deal_id?, campaign_id?, lot_id?, route, dir, spec_hash`.
  - `renditions[{kind preview|probe|final, path, sha256, manifest_ref, qa {ok, lufs, true_peak_db, sync_max_ms, no_watermark}, rendered_at}]`.
  - `asset_upgrades[{asset_id, from_sha256, to_sha256, same_in}]`.
  - `poster_path, version`.
  - New states: `awaiting_client`, `delivered`.
- **gates**
  - `id`, `kind`, one of: `script, voice_takes, author, review, send, followup, charge, customize, deliver, share, refund, publish, client_review, campaign_start, brand_confirm, rerender_broll, reauth, policy_change`.
  - `class side_effect|bookkeeping` (see 7.9).
  - `subject {kind, id}, spec_hash?, payload_hash, priority, opened_by {kind, id}, opened_at, due_at?`.
  - `status open|resolved|expired|superseded|canceled`.
  - `resolution {decision, reason_code?, note?}`, `annotations[{by agent_id, verdict, at}]` (propose-only).
  - `resolved_by {kind human|client|system, device_id?, credential_id?}`.
  - `assertion {credential_id, client_data, authenticator_data, signature}?`.
  - `token_id?, resolved_at, undo_until?, prev_hash`. The hash chain lets doctor verify the gate history.
- **touches**: `id, deal_id, direction out|in, template_key?, channel, at, logged_by, note` (origin external).
- **client_reviews**: `id, item_id, spec_hash, decision approve|changes, comment` (origin external), `link_id, at`.
- **share_links**: `id, subject {kind, id}, token_sha256, scopes [view, approve, pay, upload, download_final, optout], expires_at, revoked_at, views, last_seen_at`.
- **asset_licenses**: `id, item_id, file, kind, source mixkit|pixabay|pexels|coverr|client|site|manual, source_id, url, license, resolution, higher_res_variant_url?, sha256, obtained_at, authorization_ref?`. It is imported from `assets-licencas.csv`.
- **devices, credentials, sessions, agent_tokens**
  - devices: `label, push_subscription?, ui {layout, sound, reduce_motion}, last_seen_seq, last_seen_at, revoked_at`.
  - credentials: passkey `public_key, sign_count, label, rp_id, revoked_at`.
  - sessions: `idle_expires_at, abs_expires_at, csrf_hash, revoked_at`, plus a revoke-all endpoint.
  - agent_tokens: `name, scopes read|propose, brand_scope[], token_hash`.
- **jobs** (plus): `run_at, pool render|io, priority, subject_id, dedupe_key, cancel_requested, log_ref`.
- **schedules**: `id, kind, owner {type, id}, rule (RRULE or ISO duration), tz, next_run_at, last_fired_at, misfire run_once|skip, enabled, job_template`.
- **policy_versions**: `id, body, created_by_gate, created_at, prev_hash`. `policy.yaml` becomes a generated, read-only export, so editing the file changes nothing.
- **publications** and **publication_targets**: one target row per destination, `{platform, account_id, status, provider_preview_id, provider_preview_expires_at, external_id, error, attempts}`. A target whose provider preview expired becomes `previewed_stale` and is re-previewed before confirmation.
- **usage**: `ts, subject, kind render_seconds|tts_chars|credits|agent_tokens_reported|agent_wait_seconds, amount, measured bool`.
- **notifications**: `id, gate_id?, event_seq, channel webpush|telegram, dedupe_key, status, sent_at`.

**Schema policy.** Changes are additive only. A breaking change goes through `workspace export` (JSONL, `simplicio.workspace-export/v1`), a fresh workspace and `workspace import`. That is the same importer used on day one and for moving machines. No migration code is kept, which honors the standing rule.

### 7.4 Jobs, schedules and the render lane

- **Jobs:**
  - production: `lead.collect`, `item.script_check`, `item.voice`, `item.layout_mudo`, `item.plan_check` (including lot uniqueness), `item.render_preview`, `item.render_probe`, `item.render_final`, `item.upgrade_assets`, `item.qa`;
  - money and delivery: `charge.create` (only after a human token), `charge.poll`, `charge.reconcile_daily`, `deal.followup_due`, `deal.deliver`, `deal.share`, `refund.execute` (only after a human token);
  - housekeeping: `import.scan` (Phases 1–2 only), `digest.morning`, `backup.nightly`, `retention.clean`, `metrics.window` (24h/72h/7d, Phase 5), `campaign.tick`.
- **Voice job.**
  - It makes one Gemini request per line, reuses the cache key across companies, and backs off on 429.
  - It runs on the `io` pool, so it does not take render time.
  - It needs a campaign-level spend confirm when it spends.
  - Without a key, it opens a `voice_takes` gate instead of failing.
- **Scheduler.**
  - It wakes at the earliest `next_run_at`, at most every 30 s, and turns due schedules into jobs with `dedupe_key = schedule_id|fire_time`.
  - After downtime, a missed schedule fires once and emits `schedule.missed`.
  - `charge.poll` runs every few minutes while a charge is open and stops at `expires_at`.
  - Follow-ups move to the next send-window opening.
- **Render priorities:**
  1. finals for paid deals (rendered at payment, upgraded or customized);
  2. campaign leads, by occasion date;
  3. re-renders.

  As-is delivery of an existing FINAL needs no render. An optional render window holds campaign batches at night. Retries use backoff. A dead job lands in a repair queue where Retry (reset attempts and re-enqueue) and Skip actually differ.
- **Engine updates.** The engine is never re-tagged on the box while a campaign has renders queued (7.1).

### 7.5 Events and projections

- **New event kinds:**
  - leads and campaigns: `lead.created`, `campaign.started|progress|completed`, `lot.closed`, `import.completed`;
  - jobs and gates: `job.progress`, `gate.opened|resolved|expired|superseded|annotated`;
  - deals: `deal.stage_changed`, `touch.logged`, `optout.recorded`;
  - money and delivery: `charge.created|paid|expired|refunded|disputed`, `delivery.started|done|failed`;
  - clients: `link.viewed`, `client.approved|changes_requested`;
  - system: `notify.sent|failed`, `schedule.fired|missed`, `backup.done|failed`, `health.changed`.
- **Phrases.** Each event kind has a zero-token phrase template in en and pt-BR. The same text serves the feed, bubbles, bots, Telegram, push and the digest.
- **Rows, not only events.** Money and client history live in rows, so the 90-day event retention never deletes a deal.
- **Projections**, updated in the same transaction: `needs_you`, `board`, `funnel`, `upcoming`, `stage_counts`, `health`.
- **Endpoints:**
  - `GET /api/v1/snapshot`
  - `SSE /api/v1/events?since=` (Last-Event-ID = seq)
  - `GET /api/v1/digest?since_seq=`
  - `GET /api/v1/health` → `{level, reasons[]}`
  - `GET /api/v1/upcoming`
  - `POST /api/v1/gates/{id}/resolve`
  - `POST /api/v1/gates:resolve-batch`
  - `POST /api/v1/gates/{id}/undo` (bookkeeping gates, inside `undo_until`)
  - `POST /api/v1/sessions/seen`

### 7.6 Remote access and phone

- **The panel is tailnet-only.**
  - It binds `127.0.0.1:8787` and is published with `tailscale serve` under a stable node name (for example `factory.<tailnet>.ts.net`). That gives the HTTPS secure origin for the PWA, Web Push and passkeys (the passkey RP ID).
  - The node name moves with a restore or a host change, so the origin stays the same.
  - If the RP ID ever changes, every passkey must be re-enrolled. That step is in the restore runbook.
- **Adding a phone (Phase 1a).**
  - The first device logs in with a one-time setup code printed by `simplicio-video up` on the host.
  - From then on, Settings > Add phone on a logged-in device shows a QR with the HTTPS address and a one-time pairing code.
  - Paired devices are listed and revocable, and a new device alerts the others.
  - On iPhone, the guide sets up Tailscale VPN On Demand for the ts.net domain, so push deep links open the PWA without connecting Tailscale by hand.
- **The public edge (Phase 4) is its own minimal process,** `simplicio-video edge`, which can run in its own container.
  - It serves only `/c/*` and `/hooks/abacatepay`.
  - It holds no provider secrets, only the webhook HMAC secret. It has no AbacatePay key, Drive token or Gemini key.
  - It has read-only access to finals and previews.
  - It shares `edge.db` with the daemon:
    - `edge_links` (token hashes, rendition paths, Pix code) is written by the daemon and read by the edge.
    - `edge_inbox` (approvals, change requests, uploads, opt-outs, webhook events) is written by the edge and consumed by the daemon.
  - Uploads land in a quarantine folder that the daemon validates.
  - A test asserts that the edge process environment contains no API keys, and another that no `/api` route answers on the edge.
- **Public address.**
  - The client link uses Wesley's own domain through an outbound-only connection, so no port is opened on the box.
  - A mature tunnel product is the default choice, and the small relay from 9.7 is used if the tunnel does not fit.
  - Exposing the edge is a named owner gate, `policy_change: expose_edge`.
  - Tailscale Funnel is only a stopgap the owner chooses explicitly. It exposes a whole port (443, 8443 or 10000) on a `ts.net` address, which looks like phishing to a client paying a Pix.

### 7.7 Notifications

- **Phase 1b:** Telegram, outbound only. It works on any phone and needs no PWA. It carries deep links only and never actions.
- **Phase 2:** Web Push (VAPID, pywebpush) to the installed PWA. On iPhone, Web Push requires an installed PWA, which is why Telegram stays as a channel.
- **Behavior.**
  - One notification per gate, at most one summary per 15 minutes.
  - Quiet hours (23:00–07:00 by default) and the digest follow `workspace.timezone`, because they are about Wesley. Send windows follow the campaign's country timezone, because they are about the client. Payments are delivered silently during quiet hours.
- **Morning digest (08:00 workspace time):** "3 Pix paid, 5 follow-ups, 12 previews". It doubles as a **dead-man's switch**: no digest means the host is down.

### 7.8 Share links and webhooks

- **Share links.** A 128-bit random token stored as a hash, with scopes, expiry (per deal) and revocation from the deal. The client page has no panel cookies, no third-party assets, a strict CSP and rate limits per IP and per token. No IP addresses are stored.
- **Payment detection.** It starts with polling. The AbacatePay MCP lists `checkTransparentPix`, a light status check, and a short spike confirms the REST path. In Phase 4, the HMAC-verified `transparent.completed` handler from `venda.py` is mounted on the edge and feeds `edge_inbox`. Polling stays as reconciliation.
- **Testing.** Tests use a fake AbacatePay. Phase 2 can run its exit in test mode with `simulateTransparentPixPayment` until the production key exists.
- **Never for delivery.** `ro_share` clip links are never used for client delivery: they last at most 6 h and cannot be revoked.

### 7.9 Security of human gates

- **Two gate classes, from Phase 2.**
  - **Side-effect gates** need a passkey assertion with user verification (py_webauthn), bound to the payload. These are charge, share, refund, publish, deliver, `policy_change`, `campaign_start` when it spends, and review batches that feed a send.
    - The challenge is `sha256(gate_id | payload_hash | nonce)` and is valid for 120 s.
    - Several gates can be signed in one batch.
    - Resolution verifies the assertion, then mints and consumes the ConfirmToken in one transaction.
    - The daemon re-verifies the stored assertion against the credential's public key before every external side effect. A forged gate row without a valid signature fails.
  - **Bookkeeping resolutions** need a fresh human session (passkey login within the session's idle window), plus an undo window, and are hash-chained. These are sent, reply, interest, lost, opt-out, author or script accept, and follow-up dismissal. "Two-tap send" and one-tap reply logging stay one tap.
  - **Enrollment.** The first passkey uses a one-time setup code. Later passkeys need an existing passkey and alert the other devices.
  - **iPhone spike.** A spike on Wesley's actual iPhone checks passkeys in the installed PWA on the ts.net origin. If that fails, confirms open in Safari on the same origin, which is still a passkey.
- **Agents.**
  - The stdio MCP server is a daemon client that calls the daemon's HTTP API over the tailnet with an AgentToken (`read|propose`).
  - Agents can open gates, annotate them, submit scripts, voice takes, plans and licensed assets, render and prepare. They can never resolve gates, send messages, mint tokens or create share links.
  - API-level authoring (`item.submit_script`, `item.voice_takes`, `item.submit_plan`, `item.add_asset`, where the daemon fetches the asset URL and requires a license row) is what makes it possible to run agents off the daemon's host. It ships in Phase 3, not M2.
  - A route-table test asserts that every resolve route requires a human session, and every side-effect resolve requires a verified passkey assertion.
  - In Phase 0, `video.publish` and `video.run publish=true` become dry-run unless a human token exists.
- **The honest limit.** If agents run as root on the daemon host, no software control fully stops them, because root can change the daemon code itself.
  - Passkey verification blocks the normal paths.
  - The hash chains over gates and `policy_versions` make tampering detectable by `doctor`.
  - The strongest fix is moving box agents to another host or container, which API-level authoring now allows. The Phase 0 host check decides this.
  - A dedicated OS user alone does nothing against root.
- **Always on:**
  - A STOP file is checked before every external side effect.
  - Dry-run is the default.
  - Secrets live in a 0600 workspace secrets file or the environment, never in events or logs (the `venda.redact` pattern), and never in the edge process.
  - CSRF, TrustedHost and CORS off, as in #41.

### 7.10 Backup and restore

- **Nightly backup.**
  - `sqlite3 Connection.backup` plus a tar of workspace content (skipping render scratch and expired orphan previews) and a manifest with sha256 per file.
  - It goes through an **rclone crypt** remote on the Drive Wesley already uses, so client contacts and deal history are never stored in clear on Drive.
  - It keeps 14 copies.
- **Secrets are not in backups.** After a restore, connections are marked `needs_reauth`.
- **Restore.** `simplicio-video backup restore <file>` refuses while the daemon runs, verifies hashes and runs doctor. The runbook covers moving the stable node name and, if the RP ID changed, re-enrolling passkeys.
- **Monitoring and drills.** Doctor warns when the last backup is more than about 36 h old. A restore drill into a scratch workspace is a Phase 1b exit criterion.
- **LGPD:** `brand export|forget` and `contact forget`.

### 7.11 Updates

The update sequence on the host:
1. `git fetch --tags` and check out the new release tag.
2. `uv` with a pinned Python 3.12 venv.
3. `make check-full` plus a render smoke test on a copy of one live company folder.
4. Restart the daemon.

Rules:
- Every update takes a backup first.
- Never re-tag production while a campaign has renders queued.
- Breaking layout changes go through export/import.
- The panel shows "update available" from an opt-in check and never updates by itself.

### 7.12 Observability

- **Endpoints:**
  - `/healthz`: loopback liveness.
  - `/readyz`: db writable, scheduler heartbeat under 60 s, workers alive, disk at least 2 GB.
  - `/api/v1/status`: heartbeat age per pool, queue depth, oldest open gate, last job error, disk against doctor's 2 GB fail / 10 GB warn thresholds, last backup, and cached reachability of AbacatePay, Drive (rclone), Gemini and npm.
- **health().** One `health()` with hysteresis drives the weather, the status pill and the push.
- **Logs.** Per-job JSON logs, capped at 200 MB in total.
- **Diagnostics.** `doctor --bundle` writes a redacted zip. Nothing uploads automatically, and there is no telemetry.
- **Usage ledger.** Measured render seconds per step, TTS characters, credits and agent wait time per job, plus agent tokens marked as reported.

### 7.13 MCP and agents

- **Generated tools.** Tools are generated from the registry (#32) and are coarse:
  - `video.home.get`, `campaign.create_from_csv`, `campaign.status`;
  - `deal.list`, `deal.log_reply`;
  - `item.brief` (brand facts, lines, word timings, B-roll constraints, the lot's used concepts and styles), `item.submit_script`, `item.voice_takes`, `item.submit_plan`, `item.add_asset`, `item.render`;
  - `gate.annotate` (propose-only QA verdicts, for example from Chefe);
  - `charge.prepare` (returns a preview only);
  - `loop wait --until gate:author|gate|event`.
- **Waiting costs nothing.** `loop wait` blocks on the event log, so a waiting agent spends no tokens.
- **Same door for all agents.** `prospect` and `venda` become reachable through this audited surface. The stdio server reaches the daemon over HTTP, so agents can run on any tailnet host.
- **Deferred.** An MCP-over-HTTP server for outside clients waits until one needs it. LangGraph, CrewAI, A2A and Langfuse stay in M2.

---

## 8. Frontend

### 8.1 Stack

Keep the decision in force: Preact + TypeScript + Vite (#34, ADR-0008), as npm workspaces:
- `web/shared`: API client and types generated from OpenAPI and the JSON Schemas, the SSE connection with seq resume, the reducer, ICU messages and Intl helpers;
- `web/ui`: DecisionCard, Checklist, HoldToConfirm, Player, ContactWall, Timeline, Kanban column (virtualized), Table, Sheet, Toast, CommandPalette, Stepper;
- `web/app`: the shell and pages;
- `web/scene`: renderers;
- `web/edge`: the client page, server-rendered by the edge process with a little vanilla JS, no Three.js and no external fonts.

Libraries: `preact-iso` for routing, `@preact/signals` for the store, TanStack Virtual for long lists, the native `<video>` with frame-step keys, and small SVG charts for the funnel.

### 8.2 Carry the contracts, not the prototype code

The prototype is global-scope, hand-minified, and its themes are code. Rewrite it.

- **Carry:**
  - the Needs-you model;
  - the 3-item checklist bound to the spec hash, with the stale banner and A/N/D keys;
  - hold-to-confirm (1,150 ms) with the export fallback;
  - the stepper with sub-steps, which becomes the item timeline;
  - the peek/half/full bottom sheet and floating action card;
  - the safe-area camera offset;
  - the uncommitted fixes' intent: OS reduced motion, audio paused on scene unmount, cached thumbnails;
  - the `ev.<kind>` phrase catalog and the 641-key en/pt-BR catalog;
  - the bot intents (status, need, open, focus, follow), reused as palette intents and Game bot replies;
  - the Settings tabs (doctor rows with fix commands, retention dry-run, kill switch).
- **Do not carry:**
  - dock-level Approve or hold-to-publish in any form, fixed or not;
  - always confirming `S.pubq[0]`;
  - fake bot typing delays;
  - base64 art and CDN fonts or Three.js;
  - the append-only CSS.
- **Test.** A UI test asserts that every approve and publish path goes through DecisionCard.

### 8.3 Scene as a module behind one interface

`SceneRenderer { mount(el, {theme, store, safeArea}), focus(selection), onEvent(evt), replay(events, maxMs), setQuality('postcard'|'band'|'low'|'high'), dispose() }`.

- **Implementations:**
  - `band-svg` (Phase 3): it is also the 2D fallback.
  - `houses-three` (Phase 3 desktop house view; Phase 6 world view, phones, replay and sound): Three.js r160, vendored, as a lazy chunk.
  - `postcard` (Phase 6): a static WebP with a CSS weather overlay.
- **Shared projection.** All renderers read `sceneProject(state)`, a pure function tested without a GPU, plus the binding table.
- **Lifecycle.** The renderer stays warm across routes. It handles `webglcontextlost`, reads OS reduced motion, stops the audio bus on dispose, and does no per-frame DOM layout reads (the prototype reads `offsetWidth` and `getBoundingClientRect` every frame).
- **Frame-time governor.** Using p95 frame time over 10 s, it steps down: shadows off → particles off → band → postcard.

### 8.4 Themes as data

Extend `simplicio.theme/v1` with the fields themes.md describes but does not model:
- `houses[stage]`:
  - `{name_key, backdrop, postcard, camera}`;
  - `rooms[] {id, substep, plaque_key, props[]}`, with `props[]` from the built-in catalog;
  - `tappables[] {prop, interaction color_cycle|note|spin|ripple|pop|shooting_star, opens?}`. A tappable without `opens` is pointer-only delight. One with `opens` must name a registry command and appears in the Scene navigator;
  - `ambience {water, plants, lights, sound_recipe params}`, declared as ambient for the binding test;
  - `level_props[1..5]` (later).
- `sky {day, night}`.
- `weather_map {ok, warn, fail, paused, dry, offline}`.
- `earcons {gate, paid, fail}` as synth parameters.
- `characters[]` (with bot persona keys), `fallback_2d {landscape, portrait}`, `sponsor_slots` (read only by the window and gallery builds), `locales/`, `LICENSE.md`, `art_origin`.

Port only `br`:
- Move `proto.art.js` and `proto.scenery.js` into `themes/br/theme.json`, and serve the 23 WebP files as files with immutable cache headers.
- `theme validate` uses br as its real fixture at 375 and 1440 px.
- The br art stays `experimental` until the Real Oficial and OpenAI image terms are read, and a procedural-only br variant ships in any case.
- The other 8 prototype themes are not ported now.

### 8.5 Design system

- **Tokens.** CSS variables on `:root`, read by the scene at mount:
  - a fixed light-blue system color that themes cannot change;
  - neutral surfaces;
  - semantic `--needs` (amber), `--fail` (red), `--done` (green), `--live` (blue) and `--paid`;
  - a real dark mode (the prototype's HUD stays light in dark mode).
- **Fonts.** Self-hosted WOFF2, because the panel must work offline. Use the prototype's families, Bricolage Grotesque, Instrument Sans and IBM Plex Mono, or cut to one sans plus one mono. Ship their license texts with them.
- **Gallery route.** A dev-only `/gallery` route renders every `web/ui` component from fixtures.
- **Bundle test.** A test fails if the panel bundle contains sponsor or feed modules or any external origin. "The panel is ad-free" becomes a gate.

### 8.6 i18n with Intl

- pt-BR (owner) and en (public docs, international prospects), seeded from the 641 keys.
- A key-parity test fails the gate on a missing key. A pseudo-locale run catches hard-coded strings.
- ICU plurals.
- `Intl` for currencies, dates and times. The panel uses `workspace.timezone` (`America/Sao_Paulo` by default). Client-facing text uses the brand's country and language. No `toTimeString`, no fixed FX rate, no string concatenation.
- Outreach scripts are workspace data per language, not UI strings.
- The content language (`brand.language`) is separate from the UI language, and it also sets the client page language.

### 8.7 PWA and offline

- **Install.** `vite-plugin-pwa` (Workbox) caches the app shell and the last snapshot in IndexedDB, and the app installs from the stable ts.net origin.
- **Phone features.** Web Push. Web Share Level 2 with files, for `preview-v2.mp4` and the Pix QR. `share_target` on Android only. Haptics on hold where available.
- **Offline.** The PWA shows the last snapshot read-only under fog, with "box unreachable since 14:32", and disables actions. There is no offline action queue: every action needs the live daemon to check its payload hash, and side-effect gates also need a live passkey assertion.

### 8.8 Tests

All tests run locally, with no GitHub Actions:
- Vitest for the reducer and projections, on recorded `events.jsonl`;
- Playwright for Classic, Hybrid and Game at 375×812 and 1440×900, and for the client page in en and pt-BR;
- the parity test, the binding-table test, a reduced-motion test, a WebGL-off test and a "no affordance approves without the checklist" test;
- axe on the panel and the client page;
- a real-device harness driving a USB Android over CDP, with results committed as MEASURED;
- a listening sign-off by the owner for every sound.

---

## 9. Business and going public

### 9.1 License recommendation

Recommended (a lawyer confirms before Phase 7):
- **Core** (engine, daemon, web, edge, relay): **FSL-1.1-ALv2**.
  - Any use is allowed except offering the software as a competing commercial service, and each version becomes Apache-2.0 two years after its release.
  - This protects the later hosted version and still lets every agency, Wesley included, sell videos made with it.
  - The lawyer should confirm that an agency giving its clients review links counts as permitted use.
- **SDK, schemas, theme format and plugin manifest:** Apache-2.0, so plugin and theme authors choose their own license.
- **Official art:** free to use inside the product, with name and mascot protected by trademark. AI-generated images may not be protected by copyright.
- **Contributors:**
  - A CLA (license grant, not assignment) is checked locally by `land.sh` from the first outside contribution.
  - Wesley is the sole author: the 6 root commits are his agents.
  - One of his commits uses an employer-domain address, an employer-style address. The lawyer confirms that no employer IP or assignment clause covers this project before the license choice and before the public export.
  - `land.sh` refuses unknown author emails from now on.
- **Wording:** "source-available, Apache-2.0 two years after each release", never "open source".
- **AGPL** remains the alternative if he prefers real open source and accepts that anyone may host it.
- **Dependencies to clear:**
  - GSAP 3.14.2 is a core engine dependency. Every template and about 30 motion blocks on main use it from a CDN, and the B-roll branch vendors it. Replacing it would mean rewriting the motion library.
  - The lawyer reads GreenSock's standard license, including any clause that restricts use in tools that compete with its owner, before the repo goes public or a hosted version exists.
  - #46's license scan must cover vendored files.
  - AGPL tools (OpenMontage, VoiceStudio, Postiz) stay external, and Hypit `clone` stays a user-installed tool.

### 9.2 Repository cleanup before public

Create a new public repository with one fresh-history commit built from an allowlist (`public.allow`). Do not flip the current repo: it would publish the history, old PR refs, closed sales issue #2 and 50 dead-letter comments. The current repo stays private as the agency's ops repo, which consumes the public package and legitimately holds client data.

Before the export:
1. Replace the WJR and Lothus fixtures in `tests/conftest.py:10-11` and the `test_compile` golden with the Acme Coffee demo contract. Scrub the 15 `clients/` source paths from `motion/catalog.json` and rename `service-illustrations-wjr`. Replace `templates/broll/exemplos/` (two real international prospects) with Acme concept and plan files.
2. Drop `clients/`, `prospects/`, the 3 client MP4s, the WJR site images, `docs/venda-ativa.md` (playbook, named prospects, the Paperclip hostname) and the private Drive link in `AGENTS.md`.
3. Move prices, scripts and branding into workspace config with neutral defaults.
4. Exclude stock clips and client photos: the asset ledger stays in the workspace, and nothing licensed to Wesley is redistributed.
5. Read the art terms, or ship procedural br.
6. Pass `make check-public`. It runs only on the `public.allow` file set or the generated export, never on the private repo: gitleaks; Brazilian phone, CPF/CNPJ and CRO/OAB patterns; Drive and ts.net URLs; and a private client-name denylist. `make check` stays the private ops repo's gate.
7. Wesley reads the exported file list once.
8. Add LICENSE, LICENSE-SDK, NOTICE, SECURITY.md, TRADEMARK.md (forks rename) and CONTRIBUTING.md (data first; core code by issue first; untrusted PRs run in a disposable container with no secrets and the network off).
9. Enable GitHub secret scanning and push protection. This is a repo setting, not Actions.

An INPI search for the name happens before any public asset is made.

### 9.3 The Real Oficial partnership ask

One conversation, already opened through #19, with the asks in priority order:
1. A create-from-file or MP4 upload path under the existing `media:write` scope that returns a clip id `ro_preview_publication` accepts.
2. A registered per-app OAuth client (`client_id`). It is both the key for unattended posting and the attribution key.
3. A revenue share on credits and plans bought by accounts connected through that `client_id`. The floor is the consumer referral program that already exists in `ro_get_account` rewards (referral code, `invite_link`, quests). Wesley reads what it pays and whether an app may use it.
4. An `external_reference` or idempotency field plus status webhooks, so reconcile never guesses.
5. Re-preview, or a longer preview validity.
6. Agency multi-account with written client consent.
7. A sandbox for onboarding and tests.

What we give in return:
- the default-publisher slot;
- "Connect Real Oficial" in first-run, with disclosure;
- "Launch market presented by Real Oficial" in the public window and docs only;
- co-marketing with time-lapse and Wrapped clips;
- measured volume from Wesley's agency as evidence.

There is no exclusivity. Export and Drive stay first-class, and the Publisher Protocol stays neutral. Nothing in Wesley's daily path depends on the answer.

### 9.4 Sponsorship packages

Flat monthly packages, labeled "Sponsored". They never appear in the local panel, inside videos, or in the Review or Publish houses.

| Package | Starting price (unvalidated hypothesis) |
|---|---|
| Supporters (README and site footer) | — |
| Docs section sponsor, one per section (AbacatePay is the natural first prospect for "Payments") | about R$400/month |
| Gallery presenting sponsor | about R$1,200/month |
| Seasonal drop sponsor, category-exclusive | about R$1,500 per drop |
| Sponsored world (opt-in theme, labeled in the picker, never the default) | production fee plus monthly listing |
| One diegetic sign per non-decision house in public windows | flat worldwide price, no geo |

- All prices are founding rates, re-based on measured traffic.
- The sponsor category policy excludes betting, adult content, deceptive finance and politics.
- Invoices (NFS-e) come from Wesley's entity, which must be confirmed.
- The hourly geo auction in ads.md stays a document.
- Programmatic non-tracking ads come only after about 50k pageviews a month, as already decided.

### 9.5 The public window and theme gallery

- **The window** is a read-only replay of the Acme Coffee demo, or an opt-in, name-free snapshot of Wesley's factory. The daemon signs the snapshot and pushes it outbound to a static host, so the box never takes inbound public traffic for this. It is the home of sponsor signs.
- **The theme gallery** has cards that open the sandbox in that theme, plus one-command install. Download counts are kept server-side.
- **The template gallery** plays demo renders.
- **Measuring without tracking:** cookieless site analytics, server-side counts, an opt-in weekly heartbeat, and Real Oficial's count per `client_id`. They feed an open numbers page that doubles as the media kit.

### 9.6 Community

- Themes are data. A gallery repo validates them with `theme validate` under a DCO, and a human checks the IP.
- **Templates are code,** because HyperFrames compositions run in headless Chrome.
  - They get static checks: no remote URLs, no fetch, XHR or WebSocket.
  - They also get a network-off render in an isolated container. That only works once GSAP and HyperFrames are pinned and available offline (Phase 0 vendors one pinned GSAP copy and points every template and motion block at it), so the built-in templates pass the same check.
- Plugins stay in their authors' repos. "Verified" means their contract suite passed in our container, and it is separate from "Sponsored".
- An opt-in "made with" credit appears on the client page footer and Factory Wrapped only, never in client videos.

### 9.7 The hosted version later

1. **Relay first.** It carries client pages, Pix webhooks and push for users without Tailscale. For Wesley's own client link, Phase 4 already uses an outbound-only connection on his domain (7.6).
2. **Then a managed single-tenant daemon** in a container per customer.

It charges for compute and convenience, never features, so self-hosting stays identical. It excludes Hypit `clone` and modified AGPL tools, and it needs Real Oficial per-app tokens. The natural first customers are other one-person agencies.

### 9.8 Agency paperwork

Wesley confirms with his accountant whether each R$60–120 sale needs an NFS-e, and whether production AbacatePay KYC needs a CNPJ and site (#60 says so). Phase 2 records invoice status per deal by hand. Automatic issuance is deferred, because municipal APIs vary.

---

## 10. Roadmap

Phases are ordered. Each one ends with a fact about Wesley's real work. Owner-only tasks carry a `needs-owner` label and never block an agent drain.

### Phase 0: Clean ground (the CLI keeps earning)

- **Goal:** one green main that carries the visual he sells, a true spec, a safe paid-delivery path and measured baselines, without touching the live run on the box.
- **At the end the owner can:** keep selling from a tagged release that contains `broll-v2`, intl and venda, knowing a paid B-roll sale delivers the FINAL he approved. He can also read written baseline numbers the product must beat.
- **Scope:**
  - **Production pin.** The box keeps its current checkout until the first release tag. After that it runs tags only (7.1, 7.11).
  - **Paid B-roll delivery fix, before any B-roll sale is charged through `venda`.**
    - For a `broll-v2` folder (one with `broll/plan.yaml`), `venda entregar` uploads `final/final.mp4` only when `broll/out-final/qa-broll.json` says `ok: true`. It never re-renders the contract, and it refuses if the FINAL is missing.
    - `prospect-v1` folders keep today's HD render.
    - A test covers both cases.
  - **Baseline.**
    - Ask the owner which batches are actually selling now, and on which route.
    - Measure the `broll-v2` production baseline per company on the INT-1 and INT-2-BR lots running today: script, voice, `--mudo`, the agent's authoring time and tokens (reported), `--check` loops, preview and FINAL.
    - Measure Dia das Crianças (all `prospect-v1`) for funnel numbers only: preview made, sent, replied, price, paid, delivered, and operator minutes per lead.
  - **Spec.**
    - Commit the 15 dirty files into #51: 9 doc or catalog updates and 6 prototype fixes.
    - Fix the eight remaining old-direction places listed in §2.
    - Add this blueprint as `docs/factory/blueprint.md`.
    - Merge #51 with a short errata header. Agency entities arrive in Phase 1's contract-change PR.
  - **Land the visual in a dedicated PR.** No wait is needed, because the box's checkout is pinned.
    - Merge `feat/visual-broll`, which contains intl, resolving the known conflicts in `schema/contract.schema.json`, `tests/test_help.py`, `voices/README.md` and `README.md`.
    - The full non-render suite plus `test_broll` must be green.
    - Bring the five box-only helpers into the repo or replace them: `final_doc.py`, `ocr_final.py` (with its venv requirements), `trilhas12.py` (becoming the lot check), `qa_v2.sh` and `motion_check.py`.
    - Vendor one pinned GSAP copy and point every template and motion block at it, so renders work offline.
  - **Branches.**
    - After the landing, delete the remote `feat/visual-broll` and `feat/int1-internacional-i18n`, so client data from before `c35ff25` stops being reachable from live refs.
    - Content-check and delete `cerebro/SIM-117-pix-entrega`. Its `venda.py` and `test_venda.py` are byte-identical to main and visual-broll even though ancestry says unmerged.
    - Delete `feat/prospect-padrao-v2-puck-logo` after the same check.
  - **Engine hygiene:**
    - fix the montage path;
    - read watermark, end card credit, Pix description and user agent from `workspace.agency`;
    - move venda's webhook off 8787;
    - make the MCP `video.publish` and `video.run publish=true` dry-run without a human token.
  - **Minimal gate #31.** No GitHub Actions in any of it.
    - `make check`: pytest `-m 'not render'`, offline, for the private ops repo.
    - `make check-full`: adds the render determinism smoke test and `test_broll`.
    - `make check-public`: the safety scan, run only on the `public.allow` set.
    - Also: `uv`-pinned Python 3.12, `scripts/land.sh` with the author-email guard.
  - **Host check ADR:** what the box is, who runs as root, systemd, ports, disk, stable node name, and Tailscale serve/Funnel behavior.
  - **Scene measurement:** test the prototype house view and world view on Wesley's phone and one mid-range Android, at default settings and with `lowfx=1`, and listen to every sound. Record as MEASURED. This decides phone world view and phone particles.
  - **Backlog:**
    - rewrite #28 and #54 to the approved house ring and the experimental-art rule, with #28's 400/25k budget and the 200-item kill criterion;
    - split #19's spike and #49's first live login into needs-owner tasks, which breaks the #19↔#49 cycle;
    - set blocked-by links on #14, apply P0/P1, and fix milestone metadata;
    - drain rules: no automated drain until #31 is on main; drain in blocked-by order; never on needs-owner issues; stop at the first stubbed acceptance criterion.
  - **Owner tracks, in parallel and not exit criteria:**
    - the six §13A decisions;
    - AbacatePay KYC and Pix permission (SIM-116, SIM-112), plus CNPJ and NFS-e questions;
    - the Real Oficial ask (9.3);
    - reading the GPT Image 2 terms, and the lawyer reading the GSAP license and the employer-IP question;
    - the country outreach and payment review for the international batches;
    - updating the auto-memory note that still says "free+proprietary+ads".
- **Exit criteria:**
  - #51 merged with the 2026-10-07 direction, and every issue's spec link resolves.
  - main contains broll, intl and venda with the paid-delivery fix. `make check` and `make check-full` are green from a clean clone on the daemon host, with the network off.
  - The box runs a release tag cut from that main.
  - The `broll-v2` production baseline (per step, per company) and the Dia das Crianças funnel baseline are recorded as MEASURED.
  - The host check ADR is written.
  - Prototype phone fps and the listening notes are recorded.
- **Issues reused:** #51, #31, #43 (uv install part), #19 (spike split), #49 (split), #14, #28 and #54 (rewrite bodies), #46 (add GSAP).
- **New issues:**
  - Fix paid B-roll delivery in venda
  - Land B-roll and intl into main (with conflicts and helpers)
  - Production pin and release tags
  - Delete client-reachable remote branches
  - Engine hygiene: montage path, branding config, webhook port, ungated MCP publish
  - Host check ADR
  - Baseline: B-roll production and funnel
  - Measure prototype on real phones and listening test
  - Owner: the six §13A decisions
  - Owner: AbacatePay production, CNPJ, NFS-e
  - Owner: Real Oficial ask
  - Owner: art terms, GSAP license and employer IP
  - Owner: country outreach and payment policies
  - Docs errata and memory update

### Phase 1a: The Desk sends (internal v0.3.1)

- **Goal:** the smallest Desk that takes over his sending and reply logging. Previews are still made on the box and imported. Charges still run through the CLI, and the Desk imports their status.
- **At the end the owner can:** run one real batch's sends and replies from phone and desktop. He can approve previews, open WhatsApp or Instagram with the script, share the preview, and log "Sent?", replies and opt-outs, with no xlsx edit for that batch.
- **Scope:**
  - **Daemon** on the host: authoritative SQLite, the write order from 7.2, a minimal scheduler and the `io` pool, `tailscale serve` HTTPS under the stable node name.
  - **Contract-change PR with red contract tests first:** Brand.kind and `ref_code`, contacts, optouts, Campaign and lots, Deal, Gate (persisted, two classes, superseded on `spec_hash`), touches, devices and sessions, `Job.run_at`, schedules, items with `spec_hash` and renditions, asset_licenses, workspace agency data files.
  - **Importer:**
    - xlsx Prospects and Clientes, plus `lote.csv`, `result.json`, `venda.json`, `qa-broll.json` and `assets-licencas.csv` from the box folders (pilot, INT batches, WJR, Lothus), keeping P0xx and campaign codes;
    - `import scan <dir>` turns new preview folders into `preview_ready` deals and picks up `venda.json` status changes;
    - `prospect-v1` previews get `rerender_broll` gates, and missing logo, OAB or voice become gates.
  - **Field-ownership table** (7.2) enforced in the UI and API.
  - **Desk pages:** Today with Up next and All clear, Pipeline Kanban, Deal and Item detail (player, QA, timeline, receipt), Leads and Clients with search, Settings (prices, scripts, send window, countries, devices). URL routing and command palette.
  - **DecisionCard** with checklist and A/N/D, and swipe review on the phone.
  - **Send flow:** `wa.me` or `ig.me` plus Web Share plus "Sent?". Reply, interest, lost and opt-out in one tap, with undo. Send window, daily cap and country gate.
  - **Login:** the first-device setup code, Settings > Add phone with QR and pairing code, revocable device sessions.
  - **Nightly backup.**
  - **i18n:** pt-BR and en with Intl.
  - **Tests:** agency flow test on fakes (lead → preview → approve → sent → reply).
- **Exit criteria:**
  - For one real batch, every send, reply and opt-out was recorded only in the Desk, with zero xlsx or Paperclip edits for that batch.
  - His iPhone is paired and used for at least part of that batch.
  - A nightly backup exists on the crypt remote.
- **Issues reused (rescoped):** #33 (kernel subset plus agency models), #32 (minimal registry, in-tree plugins), #35 (store rewritten as authoritative), #41 (server subset), #34 (web scaffold), #23 (Desk pages), #55 (i18n), #47 (agency flow test and `demo --record`), #36 (send window, caps, STOP).
- **New issues:** Agency contracts (contract-change), Importer and folder scan, Desk pages (Today, Pipeline, detail), Send flow, Opt-out and country gate, Device pairing, Nightly backup.

### Phase 1b: The Desk keeps the books (internal v0.3.1)

- **Goal:** the rest of the sales bookkeeping moves out of the xlsx and Paperclip.
- **At the end the owner can:** get follow-up reminders and a Telegram morning digest, read the campaign grid and funnel, and export the deal table, all with no xlsx edit and no Paperclip card.
- **Scope:**
  - Follow-up schedules (R$60 suggestion inside the send window).
  - Campaign page: grid per lot and funnel.
  - Telegram notifier and digest: deep links only, coalescing, quiet hours in `workspace.timezone`.
  - CSV/xlsx export reproducing the xlsx columns.
  - Restore command, restore drill, `workspace export/import`.
  - Crash suite: kill -9 mid-job, mid-import and mid-backup.
- **Exit criteria:**
  - For one real batch (likely the first Black Friday wave), every send, reply, follow-up and opt-out is recorded only in the Desk.
  - The deals export reproduces the xlsx columns.
  - A restore drill into a scratch workspace has been done.
  - Crash tests show no duplicate events.
  - **Kill criterion:** if Wesley had to keep any sales state outside the Desk, Phase 2 waits until that gap is closed.
- **Issues reused:** #24 (notifier part only), #47, #35.
- **New issues:** Follow-ups, Campaign grid and funnel, Telegram notifier and digest, Export and restore drill, Crash suite.

### Phase 2: The Desk takes the money (internal v0.3.2)

- **Goal:** charge, detect and deliver without a terminal, protected by passkeys.
- **At the end the owner can:**
  - pick a price and confirm a charge with hold plus Face ID, then share the Pix in one tap;
  - see the Pix land as a push and a coin, while the approved FINAL (upgraded if a higher-resolution clip exists, or rendered now under option B) goes to Drive as `vNN` and is shared with one confirm;
  - refund in full with a gated action, see disputes in red, and record the invoice;
  - approve a whole batch of previews with one Face ID.
- **Scope:**
  - **Passkeys:** login and every side-effect gate, transaction-bound and batchable. Bookkeeping gates use session plus undo. The iOS PWA passkey spike runs first. The stored assertion is re-verified before side effects. AgentTokens for MCP. Route-table test. Hash chain on gates and `policy_versions`, with `policy.yaml` as a generated export.
  - **Charge plugin.**
    - It carries `venda.cobrar` logic, with the price list per currency as data and `externalId` per attempt.
    - One open charge per deal, and re-issue on expiry as a transition.
    - The charge gate stays closed for any currency or country without a provider.
    - `charge.poll` (`checkTransparentPix` REST path confirmed), a daily reconcile with `UNDER_DISPUTE` → `disputed`, and a full-refund gate.
  - **Same PR as the charge plugin:**
    - Delete `venda cobrar`, `venda entregar` and `venda webhook serve`.
    - The registry generates `deal charge` and `deal deliver` CLI verbs that only open or prepare gates through the daemon API, with the same idempotency key.
    - A test asserts that no code path outside the plugin calls `transparents/create`.
  - **Share Pix:** copy copia-e-cola, Web Share of the QR PNG, prefilled `wa.me`, touch logged as "charge sent".
  - **Deliver:**
    - paid → `upgrade_assets` check (or the at-payment render) → upload `final.mp4` as `vNN` to the Drive path template → share gate → prepared WhatsApp message;
    - the optional `customizing` gate re-renders with client assets, with "deliver as is" as the fast path;
    - delivery is a durable job, never a thread;
    - the receipt shows the path taken.
  - **Web Push and PWA install:** quiet hours, the money push.
  - **Invoice field** on deals. Retention tied to deals.
  - **API bypass tests:** approve without the checklist, deliver while unpaid, share without a token, charge in a currency without a provider, a token from an MCP or agent session. All must be refused.
  - **Crash tests:** kill -9 mid-charge-poll and mid-delivery must produce no duplicate charge, delivery or event.
- **Exit criteria:**
  - In one real batch, every Pix paid was detected and delivered with no terminal command, and Wesley got a push for each. This runs in AbacatePay test mode with `simulateTransparentPixPayment` if the production key is not ready, plus one real small charge as soon as it is.
  - The Desk funnel matches AbacatePay's listing.
  - An AgentToken, and Claude Code on the box, can open and annotate but never resolve a gate (automated test plus one manual attempt).
  - A paid delivery survives a daemon restart between payment and upload.
- **Issues reused:** #37 (passkeys, sessions, devices), #36 (money budgets, `policy_versions`), #60 (rescoped to the agency AbacatePay charge), #19 (Drive delivery publisher part).
- **New issues:** Passkey confirm and gate classes, iOS PWA passkey spike, Charge plugin and venda CLI removal, Polling, reconcile, disputes and refund, Share Pix, Deliver-final job with asset upgrade, Web Push and PWA, Invoice record, Gate bypass and crash test suite.

### Phase 3: The Desk produces, and the factory comes alive on the desk (internal v0.3.3)

- **Goal:** campaigns are launched and produced inside the product, the conveyor becomes visible, and the approved houses show real data on the desktop.
- **At the end the owner can:**
  - create "Natal × N businesses" from a CSV, saved leads or past clients, split into lots;
  - see the capacity estimate against the date, and let his agents submit scripts, takes, plans and assets through MCP from any host;
  - watch tiles fill and review a lot on its contact wall;
  - leave the factory open on the desk during a real campaign, read from the band or the house view what is rendering and what needs him, and open any decision from it.
- **Scope:**
  - **Campaign fan-out:** `lead.collect` → `script` → `item.voice` (one spend confirm per campaign, 429 backoff, `voice_takes` gate without a key) → `author` gate → `plan_check` with lot uniqueness → preview → FINAL or probe (§13A-4) → QA → review gate.
  - **MCP tools:** `item.brief`, `item.submit_script`, `item.voice_takes`, `item.submit_plan`, `item.add_asset`, `gate.annotate`, `campaign.status` and `loop wait --until gate:author`. The stdio server calls the daemon over the tailnet.
  - **Deletions, so there is no dual path:** replace `FINAL-COMANDO.md` generation with the job record and delete the doc generator; delete Phase 1's folder scan.
  - **Render lane:** priorities, `bench`, render cache, retries, and a repair queue with a real Retry.
  - **Measurement:** box minutes per lead per step, agent wait time, agent tokens per plan (reported), and cost per lead in the usage ledger, shown on the campaign.
  - **Asset ledger** enforced by `broll --check`, including higher-resolution variants, plus a manual upload path for owner-supplied images with source and authorization.
  - **Lot contact wall.**
  - **Hybrid band** behind the Scene interface, the layout setting per device, `health()` with weather tint and status pill, and the "While you were away" digest in the band.
  - **Game slice on the desktop.** `houses-three` house view only, behind the same SceneRenderer and binding table as the band:
    - weather from `health()`;
    - lamps and pins from gates;
    - a coin on `charge.paid`;
    - the DecisionCard docked over the scene;
    - no world view, no phone 3D, no sound yet.
  - **Seasonal calendar**, and share-to-lead (Android) or paste box (iOS).
- **Exit criteria:**
  - One whole campaign was produced from the Desk with no terminal command: every voice, preview and FINAL or probe by daemon jobs, every script and plan through MCP.
  - The capacity estimate shown at campaign start was within 25% of the measured box time.
  - Box minutes per lead and agent tokens per plan are shown as MEASURED or reported, with their labels.
  - Hybrid is Wesley's desktop default, and he kept the desktop Game open during that campaign.
  - The house view stays within 400 draw calls and 25k triangles with real data on the desktop, and the binding and parity tests are green.
- **Issues reused:** #16 (studio rescoped: wrap the `prospect-v1` and `broll-v2` routes, no new template), #18 (owner gate, batch review, machine QA), #15 (collection subset from prospect), #28 (band renderer and desktop house view).
- **New issues:** Campaign fan-out, lots and capacity gate, Script and voice jobs, Author gate and MCP authoring API, Render lane, bench and cache, Asset license ledger, Lot contact wall, Layout setting and factory band, Desktop house view, health() and weather, Digest, Seasonal calendar, Share-to-lead.

### Phase 4: The client link (internal v0.3.4)

- **Goal:** the client sees, approves, pays and downloads from one link on Wesley's own domain, and the product receives the webhook.
- **At the end the owner can:** send one link per client. Approvals, change requests, photo uploads, payments, downloads and opt-outs show up in Today without him relaying QR codes or Drive links.
- **Scope:**
  - The edge as its own secret-free process with `edge.db` (7.6).
  - The own-domain, outbound-only connection, exposed through the `policy_change: expose_edge` owner gate.
  - A route allowlist test and a test that the edge environment holds no secrets.
  - `web/edge` client page in the content language, WCAG 2.2 AA.
  - `share_links` and `client_reviews` bound to `spec_hash`.
  - The webhook mounted on the edge, with polling as reconciliation.
  - Photo upload into quarantine, then into the `customizing` gate.
  - Streamed HD download after paid, with the Drive file kept private.
  - Rate limits and CSP.
- **Exit criteria:**
  - A real client went from link to paid HD download without Wesley sending a QR or a Drive link by hand.
  - An opt-out made on a link was enforced on the next batch's send gates.
  - No panel route answers on the public address, and the edge process holds no provider key (tests).
- **Issues reused:** #18 (client review part), #37 (edge security).
- **New issues:** Client link page, Edge process and own-domain connection, Webhook on the edge, Upload into customization.

### Phase 5: Content plans and his own brand (the loop on real data)

- **Goal:** turn one-off buyers into monthly clients, and run the spec's single-brand loop for @wesleysimplicio.
- **At the end the owner can:** sell and fulfil a monthly plan, with N videos a month, client approval per item through the link, a monthly Pix and a monthly Factory Wrapped. His own Instagram gets a steady stream of portfolio posts from the loop, through export or Real Oficial.
- **Scope:**
  - Brand kit page with claim guard and `brand_confirm` gate, plus a manual brand form when a site cannot be parsed.
  - Zero-token ideas (`setores.json`, hook templates, the calendar, confirmed facts).
  - Content plans (`deal.kind = plan`, scheduled item creation). Monthly Pix charge after owner confirm. AbacatePay `createSubscription` later if a client wants card.
  - Own-brand loop. ExportPublisher always. RealOficialPublisher if upload exists, with `publication_targets`, re-preview when the provider window expires, and reconcile.
  - Metrics: funnel plus a social metrics CSV source plus `ro_get_social_analytics` where clips live there, with 24h/72h/7d windows.
  - Weekly zero-token report.
  - Factory Wrapped template (a new 9:16 template on the engine).
- **Exit criteria:**
  - At least one client (WJR, Lothus or a campaign convert) is on a monthly plan, with items client-approved and delivered through the product.
  - His own brand completed real weekly cycles, posted or exported.
  - The weekly report runs with zero LLM tokens (NoLLM test plus `usage`).
  - A Real Oficial preview that expires before confirm triggers a re-preview, never a stale submit (fake clock test).
- **Issues reused:** #15, #52, #17 (pulled from M3), #19, #22, #49, #44.
- **New issues:** Brand kit and manual form, Content plans and monthly charge, Own-brand loop, Factory Wrapped template, Weekly report, Publication targets and re-preview.

### Phase 6: The living factory everywhere (v0.4.0, the MVP as decided)

This phase can run in parallel with Phase 5 once Phase 3's API and event stream are stable, because it only consumes the store. It never blocks an owner exit.

- **Goal:** the full approved scene becomes a working view of real data on every device and the designed idle state, meeting the v0.4.0 release policy.
- **At the end the owner can:** open the laptop to a short replay of the night that lands on the house that needs him. He can also:
  - work in Hybrid with the live house following his selection;
  - do every gate from Game through the same card, on desktop and on a phone that passes the budget;
  - ask a bot what needs him;
  - leave Game as the ambient screen, and hear one bell when something needs him.
- **Scope:**
  - `houses-three` world view, phones and Hybrid live pane, plus the `postcard` renderer.
  - br as data, plus the procedural variant.
  - Rooms as instruments with lamps from state, the plaza sign from upcoming, trucks and boats from events, ambient water, plants and lights, and tappable props.
  - Template bots in Game over the palette intents.
  - Earcons opt-in, ambience Game-only.
  - Replay time-lapse, ambient mode, Scene navigator.
  - Context-loss handler, quality tiers, warm scene. World view ≤800 draw calls on desktop. Phone world view and particles as decided by the Phase 0 measurement, otherwise the 2D map.
  - Real-device harness.
  - Release policy: offline demo (Acme Coffee plus an agency demo), doctor green on a fresh clone (macOS and a Linux container), CHANGELOG with cost profile and posting path.
- **Exit criteria:**
  - On the named mid-range phone over the tailnet: ≥30 fps with 200 items, or phones default to the band or postcard (kill criterion), measured and recorded.
  - Parity and binding tests are green, and no path bypasses the checklist or capability.
  - **Golden week.** It is a recorded `events.jsonl` taken from one real imported campaign week, with a fixed number of gates of each kind. It is replayed identically for the Classic and Game timing runs. Clearing it in Game takes ≤1.5× the Classic time. **Kill criterion:** if it does not, Game stays watch-and-orient and every decision opens the Classic card full screen.
  - Wesley listened to every sound on a real device and signed off. Sound ships muted.
  - v0.4.0 is tagged with en and pt-BR, theme br, video generation, and posting via Real Oficial or export.
- **Issues reused:** #28 (rewritten), #53, #54 (rewritten), #42 (only quests derived from events; levels later), #48, #50, #46.
- **New issues:** Game on phones and ambient mode, World view budget, Template bots, Replay time-lapse, Earcons, Postcard renderer, Scene navigator accessibility, Real-device performance harness.

### Phase 7: Public

- **Goal:** others can install it, and the partner and sponsor channels open.
- **At the end the owner can:** point people to a public repo that installs and runs the demo, a site with his measured case study, a public window into his factory, galleries, and the first sponsor or partner placement.
- **Scope:**
  - **Prerequisite: a deterministic concept-and-plan generator.** It builds rules from sector, palette, lines and word timings plus the stock-clip ledger, so the public default route produces `broll-v2` with zero LLM tokens. "Bring your own agent over MCP" stays as a disclosed alternative. It may also serve Wesley earlier if the agent-cost kill criterion fires (§12).
  - License decision with a lawyer (including GSAP and the employer-IP check), CLA in `land.sh`, SECURITY.md and TRADEMARK.md, INPI.
  - Allowlist export to a fresh-history repo with a clean `make check-public`.
  - English docs plus a pt-BR landing page and quickstart. This is a mild addition to "public docs in English": two pages, not a second docs tree.
  - `install.sh` and a Dockerfile with the pinned toolchain (ADR-0003 §5.3), including GSAP and HyperFrames offline; WSL2 or Docker for Windows.
  - Site with sandbox, window, theme and template galleries, and the open numbers page.
  - Flat sponsorships (#69 rewritten). Real Oficial referral with disclosure if agreed. `theme new/validate` and `plugin new/check`.
  - Rewrite #70 for the chosen license.
- **Exit criteria:**
  - Someone outside the tailnet installs on a fresh machine from the docs alone and reaches a first `broll-v2` preview with zero LLM tokens.
  - Zero findings in the public scan, and the art terms are resolved or the art replaced.
  - The window shows no client-identifying data.
  - At least one sponsor or partner placement is live, or explicitly deferred with a reason.
- **Issues reused:** #68, #69, #70, #43, #44, #46, #57 (later).
- **New issues:** Rules-based concept and plan generator, Public export script and scan, Public window snapshot, Sponsorship packages and contract, Real Oficial referral, Plugin and theme lifecycle CLI.

### Later, by evidence only

- The hosted relay for other users, then managed tenants.
- M2 agents, when a real decision needs judgment the rules cannot make.
- Multi-format templates.
- More themes and languages, once native reviewers exist.
- House levels from outcomes (#42), after metrics exist.
- The ads.md auction, only if flat sponsorships sell out.

---

## 11. Cut or defer

- **The in-scene ad market**: 23 spaces, geo tree, hourly dynamic price, second-price auction and impression counting. Deferred: it is a regulated, payment-handling marketplace built on invented audience numbers, for revenue that is now a complement. ads.md stays a document.
- **The Ads page and "YOUR AD HERE" scenery in the panel.** Cut: the local panel is ad-free, and vacant spaces show the user's own latest video and next post.
- **8 of 9 prototype themes and 13 extra languages.** Deferred: each needs native and cultural review, and only br with en and pt-BR serves the owner and the MVP.
- **Porting the prototype code.** Cut: rewrite against its contracts. Its global scope and code-themes cannot be carried safely, and dock-level shortcuts are not wanted even in their fixed form.
- **The `3d` procedural-robot renderer.** Cut: keep sprites, the band and the postcard, so the 3D QA covers one renderer.
- **The 3D world view and particles on phones.** Deferred until the Phase 0 phone measurement. Only a Mac was measured, and the world view cost 3,248 draw calls there. If phones miss the budget, they get the 2D map and a sky tint (§13B-17).
- **The manual weather button.** It survives only as a preview in theme settings, because weather means health. Ambient motion and tappable props stay as delight.
- **Fake bot typing delays and the desk-side bot pane.** Cut. The approved bots stay in Game as template chat over the palette intents, and Classic gets the palette (§13B-17).
- **House levels and XP in the MVP.** Deferred to after metrics, from outcomes only. #42 allows streaks without loss-aversion; we choose not to ship streaks at first.
- **Forward-only SQL migrations.** Rejected: additive schema plus export/import honors the no-migrations rule.
- **`item.json` as state, editable `policy.yaml` as policy, and terminal OTP as a confirm path.** Deleted or demoted, for the reasons in 7.2 and 7.9.
- **A "hardened mode" relying on a dedicated OS user.** Rejected as a defense against root agents. The real controls are the passkey plus moving agents off the host through the authoring API.
- **`venda cobrar`, `venda entregar`, `venda webhook serve` (Phase 2), the folder scan and the FINAL-COMANDO doc generator (Phase 3).** Each is deleted in the same PR as its replacement, with no dual paths.
- **Automatic outreach, lead scraping and posting on clients' accounts.** Non-goals until written consent and multi-account support exist.
- **The YouTube-unlisted workaround for Real Oficial.** Cut: it spends credits and re-clips our video.
- **Real Oficial on the critical path.** Deferred to Phase 5, and only if upload exists. Clients post themselves today.
- **The plugin lifecycle CLI and third-party plugins.** Deferred to Phase 7. Python cannot sandbox them.
- **LangGraph, CrewAI, A2A, Langfuse and an MCP-over-HTTP server for outside clients.** Stay in M2.
- **Kaggle and Colab backends in the daemon, and ugc, clone, montage, edit and opencut in the UI.** They stay CLI-only engine features.
- **Multi-format (1:1, 4:5, 16:9).** Deferred: the `build.mjs` plates are fixed at 1080×1920, and clients post Reels and Stories.
- **Re-running the 24 h agent loop over all issues.** Cut until the gate and the drain rules exist.
- **The hosted version, programmatic ads and paid brand-generated worlds.** Later, by evidence.

---

## 12. Risks and kill criteria

| Risk | Mitigation |
|---|---|
| Wesley keeps the business on CLI + xlsx + Paperclip, and the panel stays a showcase | Agency first. The importer means day one is not empty. Phase 1a reaches real sends quickly. The kill criterion in Phase 1b says any state kept outside the Desk blocks the next phase. CSV export keeps the habit. |
| A paying B-roll client receives the obsolete visual | Fixed in Phase 0 before any B-roll sale is charged through `venda`, with a test. In Phase 2 delivery binds to `spec_hash` and the receipt shows the path. |
| `broll-v2` capacity misses seasonal dates | Measured p50 per step (including voice and agent wait), the capacity gate at campaign start, the FINAL timing decision (§13A-4), priorities, a night window and the render cache. A second render host or the rules-based concept route is decided from Phase 3 measurements. |
| Lot rules block large campaigns | Lots of ≤17 with uniqueness enforced per lot, and the contact wall for human checks (§13A-5). |
| International "yes" cannot be paid, or outreach breaks foreign law | No sends and no charges for non-BR campaigns until the country file and a provider exist (§13A-3). |
| Root agents on the daemon host bypass gates | Passkey-bound side-effect resolutions re-verified before side effects, hash chains checked by doctor, no resolve route for agents, and agents moved off the daemon host through the authoring API, per the host check. |
| A bug in the public edge leaks provider keys | The edge is a separate process with no provider secrets, read-only file access and an inbox the daemon validates. A test asserts its environment. |
| Money bugs: double charge, double delivery, wrong amount | Venda's invariants as code, one charge path (venda CLI deleted in Phase 2), idempotency keys and `externalId`, a daily reconcile shown in the funnel, kill -9 crash tests, fake-AbacatePay contract suites. |
| WhatsApp flags his number, or an LGPD/GDPR complaint | Only humans send. Send window, daily cap, global opt-out, a country policy required before send gates open, minimal contacts, encrypted backups, retention blanking. |
| Approvals do not carry over from preview to final | Approvals bind to `spec_hash`. A changed concept or plan supersedes the gates, and asset upgrades of the same clip are recorded without superseding. |
| Assets get redistributed illegally (stock clips, client photos, GSAP, AI art) | Asset ledger, nothing licensed shipped in the public repo, license reads as Phase 0 owner tasks, a procedural br variant. |
| The box is a single point of failure | Nightly encrypted offsite backup, restore drill, dead-man digest, health push, stable node name for restores. The CLI stays usable until each path's replacement lands. |
| Real Oficial never ships upload or per-app tokens | Nothing in the agency path needs it. Export and Drive are first-class. **Kill criterion:** with no file path by Phase 5's exit, v0.4.0 ships export-first and says so in the CHANGELOG. |
| Scope creep from the prototype delays daily use again | No scene work before Phase 3. Phase 3's scene work is limited to the band and the read-only desktop house view on the same binding table. Phase exits are usage facts. |
| v0.4.0 feels like a regression against the approved prototype | The desktop Game slice ships in Phase 3, and the template bots, ambient motion and tappable props are kept (§13B-17). |
| The Game misses phone performance or drains the battery | Phase 0 device test, budgets, governor, band and postcard fallbacks. **Kill criterion:** <30 fps with 200 items means phones default to 2D. |
| The Game is slower than lists for real work | **Kill criterion:** more than 1.5× Classic time on the golden week means Game is watch-only and decisions open the Classic card. |
| Sound annoys | Signals only, opt-in, coalesced, quiet hours, owner listening sign-off. **Kill criterion:** a sound the owner turns off in his first sessions is redesigned or removed before release. |
| The automated drain dead-letters again or lands stubbed acceptance criteria | No drain before #31. Blocked-by order only, never needs-owner issues. **Kill criterion:** stop at the first PR without a red-first commit or with a stubbed criterion. |
| Phase 1 is too large to finish | Split into 1a (sends from the Desk) and 1b (books). Money is Phase 2 and production Phase 3. |
| A pre-1.0 update strands deal history | Additive schema, export/import before breaking changes, backup before every update. |
| Engine changes break a live campaign | Production pin: the box runs release tags, which are never re-tagged while renders are queued, and new tags are checked on a copy of a live folder. |
| Agent authoring cost erodes margin | Usage records agent tokens, wait and minutes per plan. **Kill criterion:** if authoring cost per lead exceeds the threshold the owner sets, build the rules-based concept generator early (it is a Phase 7 prerequisite anyway). |
| Brand mismatch at payment | One name across watermark, end card and Pix description from workspace config in Phase 0, and the client link on Wesley's own domain in Phase 4. |
| Going public leaks client data or employer IP | Fresh-history allowlist export, `make check-public` on the export set, a manual file-list read, the lawyer's employer-IP check, and the author-email guard in `land.sh`. |
| Revenue concentrates on Real Oficial | Three independent lines (partner, flat sponsorships, hosted later), plus agency income that does not depend on product growth. |

---

## 13. Decisions the owner must make

### 13A. Before Phase 0 work starts

1. **Does the agency workflow become first-class, and does it ship before the v0.4.0 tag?** This challenges the MVP order, not its content.
   - Options: first-party plugins shipped first / keep the agency on CLI + xlsx + Paperclip / a separate private app.
   - **Recommendation:** first-party plugins, first. It is the only daily use there is, it settles "does the sales code stay", and the MVP still ships as decided at Phase 6.
2. **Where does the daemon run?**
   - Options: the box / the VPS / the Mac.
   - **Recommendation:** the always-on machine where batches render, confirmed by the Phase 0 host check. One host, no sync. If agents run as root there, move them off it through the authoring API, or accept that passkeys plus tamper detection are the controls.
3. **International sales.** The country review covers sending; this decision also covers payment.
   - Options: pause international sales / price in local currency through a card or payment-link provider (AbacatePay card checkout if it accepts foreign cards, which is unverified, or another provider) / Brazil only for now.
   - INT-2-BR targets the US in pt-BR, and whether those businesses can pay a BRL Pix is unknown.
   - **Recommendation:** keep producing international previews, but open no send gate and no charge gate when `campaign.country != BR` until the lawyer has reviewed `agency/countries/<cc>.yaml` and a provider for that currency is configured. The code keeps both gates closed by default.
4. **When is the FINAL rendered?** This challenges your rule of 02/10 ("nenhuma prévia vai ao Wesley sem o comando do vídeo FINAL pronto e testado").
   - **Option A (today):** FINAL before review. 9–12 min of box time per lead. An 80-lead campaign takes about 12–16 h. The HD file is ready the moment the client pays.
   - **Option B:** `--check`, the preview and a short full-resolution probe with QA (the first 2 s and the end card) before review. The full FINAL renders at payment, with any 1080p or 4K clip upgrades included. That is an estimated 4–7 h for 80 leads instead of 12–16 h (the probe is unmeasured), and the client gets the HD file about 8 min after paying.
   - The rule exists to prevent selling something that cannot be delivered. B-roll renders are deterministic (same spec, same sha256), and the probe checks full-resolution layout, watermark removal and loudness.
   - **Recommendation:** B, because capacity is this plan's main risk and most leads never pay. Keep A if having the FINAL file in hand before every send matters more to you.
5. **Lot size and uniqueness.**
   - Options: lots of at most 17 companies, with concept and music style unique per lot / relax the rule (for example, styles may repeat within a lot, concepts may not) / campaign-wide uniqueness (caps a campaign at 17).
   - **Recommendation:** lots of at most 17, unique per lot, as the spec already says "do lote". Enforce it in `item.plan_check` and replace the box-only `trilhas12.py`.
6. **Who are "Chefe" and "the council"?** The B-roll spec says Drive upload happens only after "OK do Chefe/Wesley" for the lot. AGENTS.md calls a confirmed Pix "a autorização do conselho". `venda-ativa.md:121` says exposing the webhook needs council approval.
   - If they are agents, the plan models a propose-only pre-review lane: they annotate the card with a QA verdict and never resolve a gate.
   - If they are people, they need their own human sessions.
   - Either way, edge exposure becomes your named gate `policy_change: expose_edge`.

### 13B. By the phase that needs it

7. **(Phase 0) PR #51.**
   - Options: commit the working-tree edits and merge now / rewrite first.
   - **Recommendation:** commit the 15 edits, add this blueprint, fix the eight old-direction places, then merge. Agency contracts land with their code.
8. **(Phase 0) What is selling now, and on which route?** Is Brazilian prospecting paused until it moves to `broll-v2`, as the spec suggests? This decides where the baselines come from.
9. **(Phase 1a) What happens to the `prospect-v1` previews and the Dia das Crianças leftovers?**
   - Options: re-render on `broll-v2` / sell as is / archive.
   - **Recommendation:** archive seasonal `prospect-v1` previews after 12/10 unless the deal is already in conversation. Open a `rerender_broll` gate for the rest.
10. **(Phase 1a) Where does state live?** This challenges the spec.
    - Options: SQLite authoritative with immutable files / `item.json` plus a separate index, as specified.
    - **Recommendation:** SQLite authoritative, with the field-ownership table while the CLI still writes.
11. **(Phase 1a) How does the schema change before 1.0?**
    - Options: additive plus export/import / forward-only migrations.
    - **Recommendation:** additive plus export/import. It honors your no-migrations rule and doubles as the move-machine path.
12. **(Phase 1a) What do approvals bind to?**
    - Options: the spec hash / output bytes.
    - **Recommendation:** the spec hash. The preview and the FINAL are different renders of one spec.
13. **(Phase 1b) Which notifications come first?**
    - Options: Telegram / Web Push / both.
    - **Recommendation:** Telegram in Phase 1b, Web Push with the PWA in Phase 2. Links only, never actions.
14. **(End of Phase 1b) Retire the xlsx and Paperclip for sales?**
    - **Recommendation:** yes. Keep a CSV/xlsx export, and keep Paperclip for process and dev cards only.
15. **(Phase 2) How does a human prove a decision?**
    - Options: terminal OTP / passkey login only / passkey bound to every payload.
    - **Recommendation:** a passkey bound to the payload for gates with side effects or money (batchable), and a fresh session plus undo for bookkeeping, from Phase 2 after the iPhone spike.
16. **(Phase 2) Delivery path and the Drive package.**
    - Options for the Drive path template: AGENTS.md's `clientes/NOME_CLIENTE/ANO/CAMPANHA/` / the B-roll spec's `clientes/<PAÍS>/...`.
    - Also decide whether the per-company `drive-pacote` upload (spec §8) survives once the store and encrypted backup hold spec and audio.
    - **Recommendation:** `clientes/<PAÍS>/<CLIENTE>/<ANO>/<CAMPANHA>/<CLIENTE> - <descricao> - vNN.mp4`, which keeps both conventions' information. Retire `drive-pacote` in Phase 3.
17. **(Phase 3) Changes to the approved scene.** Answer yes or no to each:
    - (a) Interactive and attention-drawing elements must bind to real state or an action; ambient water, plants and lights and tappable props stay as delight and stop under reduced motion.
    - (b) Bots stay in Game as template chat over the palette's intents, without fake typing delays; Classic gets the palette, not a bot pane.
    - (c) The phone world view and phone particles are decided by the Phase 0 phone measurement, with a 2D map if they miss the budget.
    - (d) A read-only desktop Game slice arrives in Phase 3, and the full Game (phones, world view, bots, sound, replay) in Phase 6.
18. **(Phase 3) View names and defaults.**
    - Options: Clássico / Híbrido / Fábrica (alternative: Clássico / Híbrido / Jogo).
    - **Recommendation:** Clássico / Híbrido / Fábrica. Phone defaults to Clássico, desktop to Híbrido from Phase 3, sound off.
19. **(By Phase 4; decide early) Client-link domain and Pix detection.**
    - Options: your own domain through an outbound-only connection / a Tailscale Funnel `ts.net` address / no link.
    - **Recommendation:** polling for Pix from Phase 2. In Phase 4, the client link on your own domain through an outbound-only connection to the secret-free edge. Funnel only as an explicit stopgap.
20. **(Phase 7; record the direction now) Zero tokens on the public default route.** This flags a challenge to a decision in force. Today the official visual cannot be made without an agent writing each concept and plan, so "zero LLM tokens on the default path" holds only for `prospect-v1`.
    - **Recommendation:** make the deterministic concept-and-plan generator a Phase 7 prerequisite. The public default is that generator; "bring your own agent over MCP" is an option with disclosure. Your own agency keeps using agents until the generator matches their quality.
21. **(Phase 7; record the direction now) License.**
    - Options: FSL core plus Apache SDK / AGPL / permissive.
    - **Recommendation:** record FSL plus Apache SDK now as the direction. A lawyer confirms before Phase 7, together with GSAP's license and the employer-IP question. A CLA is required from the first outside contribution.

---

## 14. The next ten concrete steps

1. **(Owner) Answer the six §13A decisions:** agency first, daemon host, international sales, FINAL timing, lot size, and who Chefe and the council are. Also say which batches are selling now and on which route (§13B-8).
2. **(Agent) Spec.** *Done on 2026-10-07* except the last part: the 15 edited files and this document are committed on `docs/factory-spec`, and the old-direction places are fixed except `pyproject.toml:11` and the title of issue #70, which follow the license decision. Wesley reviews and merges #51.
3. **(Agent) Fix paid B-roll delivery.** For a `broll-v2` folder, `venda entregar` uploads `final/final.mp4` only with `qa-broll.json ok: true` and never re-renders. `prospect-v1` folders keep today's path. Add tests. This must land before any B-roll sale is charged through `venda`.
4. **(Agent) Write the host check ADR.** Read-only: what the box is (VM or container, systemd, root agents, same host as the VPS or not), disk headroom, ports in use (including `:8443`), whether a stable node name and `tailscale serve` and Funnel work there.
5. **(Owner and agent) Record the baselines as MEASURED.** The B-roll production time per step and agent tokens per company on the INT lots running now. The Dia das Crianças funnel (sent, replied, price, paid, delivered) on the CLI. The box stays on its current checkout.
6. **(Agent) Land the visual in a dedicated PR.**
   - Merge `feat/visual-broll` (with intl) into main, resolving the conflicts in `schema/contract.schema.json`, `tests/test_help.py`, `voices/README.md` and `README.md`.
   - Bring in or replace the five box-only helpers, and vendor one pinned GSAP copy for every template and motion block.
   - Then delete the remote `feat/visual-broll` and `feat/int1-internacional-i18n`, content-check and delete `cerebro/SIM-117-pix-entrega` and `feat/prospect-padrao-v2-puck-logo`.
   - Fix the montage path, move branding to `workspace.agency`, move the webhook port, and make the MCP publish dry-run without a token.
7. **(Agent) Build the minimal gate #31 and the production pin.** No Actions. Then cut the first release tag for the box.
   - `uv`-pinned Python 3.12.
   - `make check` (offline non-render suite), `make check-full` (render smoke and `test_broll`), and `make check-public` (scan on `public.allow` only).
   - `scripts/land.sh` with the author-email guard, and a pre-push hook.
8. **(Owner) Push the parallel money and legal tracks.**
   - AbacatePay KYC and Pix permission (SIM-116, SIM-112), plus the CNPJ and NFS-e questions with the accountant.
   - Book the lawyer for the license, GSAP, the employer-IP question and the country outreach and payment rules.
   - Read the GPT Image 2 terms, and send Real Oficial the combined ask from 9.3.
9. **(Owner and agent) Measure the prototype on real phones.** Run the house view and world view on Wesley's phone and one mid-range Android, at default settings and with `lowfx=1`. Record frame times as MEASURED, and listen to every sound.
10. **(Agent) Clean the backlog, then open the Phase 1a contract-change PR.**
    - Backlog: rewrite the #28 and #54 bodies, add the `needs-owner` label, set blocked-by links on #14, split #19's spike and #49's first live login, fix milestone metadata, and write the drain rules into #14.
    - Contract-change PR, red contract tests first: Deal, Campaign and lots, Gate (two classes, `spec_hash` superseding), contacts, optouts, schedules, `Job.run_at`, and items with renditions.
    - In parallel, build the importer against copies of the real xlsx, `lote.csv`, `venda.json` and the box prospect folders, keeping P0xx and campaign codes, so the Desk opens with Wesley's real pipeline on day one.

DONE | NEXT: owner answers the six §13A decisions and merges #51; agent fixes paid B-roll delivery | BLOCKED: none