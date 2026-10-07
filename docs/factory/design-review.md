# Design review of the factory plan

Date: 2026-10-06 (revised the same day after the owner's scope decisions). Scope: turning `simplicio-videos` into a Fastlane-style, self-hosted content conveyor (brand → ideas → make → review → schedule → measure → report → evolve) with a themed, gamified panel, where everything but video generation is a plugin.

## Verdict

The direction is sound and differentiated: a **deterministic** video engine that already works, local-first, Real Oficial as the default provider, any agent through open protocols. The first sketch was an architecture without a walking skeleton: two dozen issues, four young frameworks stacked, an endless loop with real-world side effects, no shared contracts, and a plan that would only integrate at the end. The owner then fixed the priorities: **minimum viable (one theme, working video generation, posting through Real Oficial), plugin architecture, test first, minimum tokens, releases that never break**. This review turns those priorities into a build order that can run in parallel and stay green.

## What is strong (keep)

- Decisions are frozen in versioned files and the render is pure, so results are reproducible and reviewable.
- A working engine with 200+ tests already exists: no new video-generation machinery is needed.
- Irreversible actions already had human gates; they become server-enforced, payload-bound tokens.
- Local-first; built on open-source tools; the agent surface (MCP, CLI) exists from day one.
- Real Oficial already covers scheduling, captions, translations, dubbing, covers, analytics and cuts: we integrate instead of rebuilding.

## What worries us (ranked)

| # | Concern | Why it matters | Decision | Tracked in |
|---|---|---|---|---|
| 1 | **Token cost of an agent conveyor** | Multi-agent debates and LLM parsing burn tokens for work that rules do | Default path is zero LLM tokens; LLM is an optional plugin for judgment only; delegate captions/dubbing to Real Oficial; budgets and a NoLLM test enforce it | README (token economy), #36, #47, #52 |
| 2 | **Real Oficial cannot take our MP4 (as far as the published MCP tools show)** | "Posting through Real Oficial" is the MVP promise; the REST docs (`docs.realoficial.com.br`) were unreadable behind a browser check | Spike first in #19; ask Real Oficial for an upload or create-from-file path; the export bundle ships either way; the gap is stated in release notes | #19, #49 |
| 3 | No walking skeleton | Parts built in isolation rarely fit | The skeleton loop runs on fakes before any real stage; each real stage replaces a stub and the e2e flow test stays green | #33, #47 |
| 4 | Endless loop = unbounded spend and posting | A bug becomes a bill or a spam incident | Budgets, caps (MVP: 0 tokens, 0 credits), quiet hours, kill switch, max in flight, autonomy ladder (default L1), dry-run default | #36 |
| 5 | Confused deputy and prompt injection | Agents read untrusted pages and hold tools that spend or publish | Per-role capabilities, human-only confirm tokens bound to the payload, untrusted-content wrapper, SSRF-safe fetch | #36, #37, #41 |
| 6 | Exactly-once publishing | A crash between "submitted" and "recorded" double-posts | Unique idempotency key, reconcile before retry, payload-hash binding | #19, #35 |
| 7 | Plugin boundary | If the gates were a plugin, a plugin could remove them | Core = engine + plugin host; store, policy, security and the runner are host services, not plugins | plugins.md, #32 |
| 8 | Young framework stack (CrewAI, LangGraph, A2A, Langfuse) | Heavy installs, CrewAI `<3.14`, A2A SDK moved 0.3 → 1.0 | Moved out of the MVP; each returns later as an optional plugin behind a Protocol with a spike and kill criteria | #25–#27, #30 |
| 9 | Gamification can reward the wrong thing | Paying XP for volume produces spam and bans | Reward quality and learning; cap volume XP; no punishments; the Needs-you inbox is always visible | later: #42; #23 |
| 10 | **Franchise IP in themes** | Minions, Chaves, Game of Thrones are protected: shipping them risks takedown or worse | Ship only original art with a recorded license; private user themes allowed but never committed; look-alike trade dress excluded | themes.md, #53, #54 |
| 11 | **3D costs more than a 2D belt** (decided in favor of 3D by the owner on 2026-10-06) | WebGL adds mobile cost and context loss; models would add an asset pipeline | Procedural low-poly geometry (no model files), a frame and triangle budget, a context-loss handler, `prefers-reduced-motion`, and a 2D SVG fallback behind the same renderer interface | #28, #56 |
| 12 | 15 languages × 15 themes is a content and review problem | Machine drafts of 13 locales ship errors; RTL and CJK change layout | MVP: `en` + `pt-BR`; catalogs complete-by-test; native review before `stable`; RTL tested separately | #55, #58 |
| 13 | Concurrent writers on files | Panel, agents, CLI and loop write at once | Files for artifacts, SQLite WAL for coordination, atomic writes, single daemon lock | #35 |
| 14 | Self-improvement without evidence | Reflection on tiny samples teaches superstitions; self-edited prompts drift | Later (M2): lessons start as hypotheses, minimum sample sizes, humans approve activation and every prompt/policy change | #29, #45 |
| 15 | Merge-conflict hotspots | `cli.py` (618 lines), hand-written `plugin.json` (536), hard-coded test lists | Registry-generated manifest, per-plugin directories, Makefile fragments, machine-checked ownership | #32, #31 |
| 16 | `main` is not green today | 3 tests fail without `/projetos/ai/OpenMontage`; 2 render tests need the network; generic `clone`/`montage` console scripts | Fix, test taxonomy, block network in unit tests | #31 |
| 17 | **Ads in a tool that holds publishing powers** | An ad network script in the panel could hijack a session that can publish and spend; tracking breaks the local-first promise | Native static sponsor cards from a signed, reviewed feed; no third-party scripts in the panel origin; no behavioral tracking; no telemetry by default; "Sponsored" labels; opt-out | monetization.md, [ads.md](ads.md), #69 |
| 18 | **Licenses of what we embed or invoke** | Whatever license #70 picks for the public code, it cannot absorb AGPL code into the core, and the vendored or CDN-loaded GSAP (GreenSock standard license) needs a read; Hypit forbids commercial redistribution and multi-tenant use | License matrix; AGPL tools (OpenMontage, VoiceStudio, Postiz) external only; Hypit user-installed only; no prebuilt Docker image until reviewed | monetization.md, #46 |

## What we had not considered (and where it landed)

| Gap | Landed in |
|---|---|
| Platform compliance: AI labels, ad disclosure, music licensing, copyright of remixes, forbidden claims | MVP: a mandatory human checklist in review (#18); full plugin later (#39); [risks-and-policies.md](risks-and-policies.md) |
| Consent for cloned voices and likenesses (LGPD) | later (#21); gates in #36 |
| Approval fatigue: 30 videos a month means 30 decisions | Batch review, digest notifications, rubric auto-approval only at L3 (#18, #24) |
| First run without keys; time to first value | Offline demo (#47), `install`/`update`/`doctor`/`setup` (#43) |
| Cost visibility per item | `usage` ledger and events (#36, #35) |
| Time semantics: brand timezone, DST, quiet hours, stale approvals | #36, #18 (approval bound to content hash); #17 later |
| Metrics semantics: lag, windows, attribution, sample size | #22 (windows, minimum n); #29 later |
| Failure handling: retries, dead letters, resume after a crash | #35 job queue, #47 runner |
| Disk and log growth (this Mac hit 100% disk from unbounded crash dumps) | Retention, size caps, `doctor`, `clean` (#35, #43) |
| Version drift (Python, Node, ffmpeg with libass) | `doctor`; installer pins Python 3.12 via uv (#43) |
| Provider drift: the Real Oficial tool list can change | Tool-list snapshot test, live check (#19, #49) |
| Licenses: AGPL (Postiz, VoiceStudio), Langfuse `ee/` | Network-only, scan (#46) |
| Upgrade path | Workspace layout version, refuse mismatches clearly; `update` command (#35, #43) |
| Documentation rot | Generated references, link check, help with examples mandatory, `last_verified` (#44, #32) |
| Review discipline across parallel PRs | Ownership map, TDD check, `land.sh`, `reviewed` label (#31) |
| Third-party plugin trust | Manifest permissions, honest limits, lazy loading (#32) |
| Accessibility and phone use | Panel a11y checks, 2D scene with reduced motion, text equivalents for bubbles (#23, #28) |
| Content language vs UI language | Brand `language` vs UI locale; catalogs (#55) |

## Open decisions for the owner

1. **Real Oficial upload.** Ask them for an MCP tool or REST endpoint that accepts our MP4 and creates a publishable clip (the `media:write` scope already exists). Until then the MVP posts through the export bundle plus the features that work. Also: open `docs.realoficial.com.br` and check whether the REST API already has it (a bot check blocks automated reading).
2. **MVP theme and the 15 languages.** `br` is proposed as the first theme; the list of 15 languages is a proposal in [themes.md](themes.md#languages).
3. **Franchise themes.** Minions, Chaves and Game of Thrones cannot be shipped; original genre themes can. Confirm.
4. **Distribution.** Decided on 2026-10-07: free, code going public (FSL or AGPL, to confirm in #70), funded by a partnership with the default publisher, direct sponsorships and, as a complement, site ads ([monetization.md](monetization.md)). Before going public: clean the history (item 7), read the generated art's terms. Generated videos never carry our ads.
4b. **Which "site" carries the ads.** Decided on 2026-10-07: the public website, gallery and docs (direct sponsorships first), and later the public view-only window of a factory. The local panel carries no ads.
5. **Tenancy.** Single host and no billing in the MVP; one workspace can hold several brands (the owner's clients, see [blueprint.md](blueprint.md)). A paid hosted version may come later.
6. **Sales operations code** (`prospect.py`, `venda.py`, Pix billing) lives in this package. Keep, or move out so the product engine stays generic.
7. **History.** Client folders were removed from the tree but remain in git history, and the example videos still show client contacts on screen.
8. **Unknown names.** "dots" and "muse" were mentioned as target clients; we support any MCP, OpenAPI, function-calling or shell client.

## Kill criteria

- **CrewAI** (M2): install larger than 2 GB or slower than 5 minutes, or it blocks Python 3.12 on macOS arm64 or Linux → ship only a plain tool-loop runner behind the same `AgentRunner` Protocol.
- **A2A SDK** (M2): if in-process transport needs HTTP, keep A2A at the external boundary only.
- **Langfuse** (M2): if it needs more than `docker compose` and ~2 GB RAM, keep the local JSONL tracer as the default.
- **Scene renderer**: if the 3D scene stays under 30 fps on a mid-range phone with 200 items after coalescing, switch phones to the 2D fallback (or the static-sprite belt) with the same event mapping.
- **Real Oficial** (MVP): if posting our file is impossible and Real Oficial gives no date, the MVP ships with export plus the working features and says so.

## What we deliberately do not copy from Fastlane

Account warming and managed accounts (platform terms and ban risk), scraping platforms for a trend library (fragile and against terms), volume-first posting (our scoring rewards learning and quality), and an always-on LLM (our default path costs zero tokens).
