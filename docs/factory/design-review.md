# Design review of the factory plan

Date: 2026-10-06. Scope: the plan to turn `simplicio-videos` into a Fastlane-style, agent-driven, self-hosted content loop (brand → ideas → make → review → schedule → measure → reflect → evolve) with a gamified panel.

## Verdict

The direction is sound and differentiated: a **deterministic** video engine, local-first, any LLM, agents reachable through open protocols, Real Oficial as the default backend. As first sketched, though, it was an architecture without a walking skeleton: two dozen issues, four young frameworks stacked, an endless loop with real-world side effects, and no shared contracts, so parallel work would have diverged and "always works" would not have been provable. This review keeps the vision and changes how it is built.

## What is strong (keep)

- Decisions are frozen in versioned files and the render is pure, so results are reproducible and reviewable.
- Irreversible actions (publish, spend, purchase, voice cloning) already had human gates.
- Local-first and open-source-first; no cloud dependency of our own.
- The agent surface (MCP, OpenAPI, CLI) exists from day one, so any LLM or bot can drive the stages.
- A working engine with 200+ tests already exists; the factory sits on top of it instead of replacing it.

## What worries us (ranked)

| # | Concern | Why it matters | Mitigation | Tracked in |
|---|---|---|---|---|
| 1 | No walking skeleton | Parts built in isolation rarely fit; UI and agents would be demoed before the loop works | Offline demo loop with fake LLM/publisher is the first integration target; every part tested alone against fakes | #33 kernel, #47 |
| 2 | An endless loop is unbounded spend and posting | A bug becomes a bill or a spam incident | Budget governor, daily caps, quiet hours, kill switch, max in flight, autonomy ladder (default L1), dry-run default | #36, #25 |
| 3 | Confused deputy and prompt injection | Agents read untrusted web content and hold tools that spend or publish | Capability matrix per role; confirm tokens minted only by a human session and bound to the payload hash; untrusted-content wrapper; SSRF-safe fetch | #36, #37, #41 |
| 4 | Exactly-once publishing | A crash between "submitted" and "recorded" double-posts | Ledger with unique idempotency key, reconcile-before-retry, payload-hash binding | #19, #35 |
| 5 | Framework stack (CrewAI + LangGraph + A2A + Langfuse) | Heavy installs, version pins (CrewAI `<3.14`), API churn (A2A SDK just moved 0.3 → 1.0) | Adapters, spikes with kill criteria, pins, engine independent of all of them, `PlainRunner` fallback | #26, #27, #25, #30, #46 |
| 6 | Gamification can reward the wrong thing | XP for volume produces spam and account bans | Reward quality and learning, cap volume XP, no punishments or streak anxiety, "Needs you" inbox always visible | #42, #28 |
| 7 | Concurrent writers on files | Dashboard, agents, CLI and loop write at once | Files for artifacts, SQLite WAL for coordination, atomic writes, single daemon lock | #35 |
| 8 | Self-improvement without evidence | "Reflection" on tiny samples teaches superstitions; self-edited prompts drift | Lessons start as hypotheses with minimum sample sizes; humans approve activation and every prompt/policy change; agents cannot edit prompts, policy or code | #29, #45 |
| 9 | LLM nondeterminism vs "always works" | Tests that call a model are flaky and cost money | `FakeLLM`, record/replay cassettes, offline evals; real-model runs are manual and budget-capped | #33, #45 |
| 10 | Merge-conflict hotspots | `cli.py` (618 lines), hand-written `plugin.json` (536), hard-coded lists in tests block parallel PRs | Registry-generated manifest, per-track files and Makefile fragments, machine-checked ownership map | #32, #31 |
| 11 | `main` is not green today | 3 tests fail on any machine without `/projetos/ai/OpenMontage` (absolute path in `montage.py`); 2 render tests need the network via `npx`; `clone` and `montage` are installed as generic console scripts | Fix, mark by test taxonomy, block network in unit tests | #31 |
| 12 | Scope creep inside one repo | Engine and factory would entangle | Layers with an enforced import boundary; extras for heavy deps | #33 |

## What we had not considered (and where it landed)

| Gap | Landed in |
|---|---|
| Platform compliance: AI-content labels, ad disclosure, music licensing, copyright of "remixed" content, forbidden claims | #39 compliance, [risks-and-policies.md](risks-and-policies.md) |
| Consent and personal data for cloned voices and likenesses (LGPD) | #21 cast, #36 policy gates, risks doc |
| Human attention budget: 30 videos a month means 30 approvals | Batch review, digest notifications, rubric-based auto-approval only at L3, Needs-you inbox (#18, #24, #23) |
| First run without keys; time to first value | Offline demo (#47), setup wizard (#43) |
| Cost visibility per item and estimate-before-run | Budget ledger and events (#36, #35), traces (#30) |
| Time semantics: brand timezone, DST, quiet hours, posting windows, stale approvals | #17 plan, #36, #18 (approval bound to content hash) |
| Metrics semantics: lag, windows, attribution, sample size, noise | #22 insights, #29 learn |
| Failure handling: retries, dead letters, resume after a crash, poison items | #35 job queue, #25 graph |
| Disk and log growth (this Mac reached 100% disk from unbounded crash dumps) | Retention, size caps, `doctor`, `clean` (#35) |
| Version drift (Python, Node, ffmpeg with libass) | `doctor`, installer pins Python 3.12 via uv (#43, #35) |
| Provider dependency: Real Oficial's tool list can change and has no MP4 upload | Tool-list snapshot test, `ExportPublisher` fallback, Postiz optional (#19, #38, #49) |
| Licenses: AGPL (Postiz, VoiceStudio), Langfuse `ee/` | Network-only integration, scan (#46) |
| Upgrade path | Workspace schema version; refuse mismatches with a clear message (#35) |
| Documentation rot | Generated references, link check, "last verified" stamps (#44) |
| Review discipline across parallel PRs | Ownership map, `land.sh`, `reviewed` label (#31) |
| Accessibility and phone use | A11y checks, 2D fallback for the 3D scene, reduced motion (#23, #28) |
| Content language vs UI language (pt-BR content, English UI) | i18n-ready strings (#23), brand language field |

## Open decisions for the owner

1. **License of this repository.** `pyproject.toml` says `Proprietary`. Decide before others run or redistribute it. Postiz and VoiceStudio (AGPL) stay network-only either way.
2. **Tenancy.** We assume single tenant, single host, no billing. Confirm.
3. **Sales operations code** (`prospect.py`, `venda.py`, Pix billing) lives in this package. Keep, or move to its own package/repo so the product engine stays generic.
4. **History.** Client folders were removed from the tree but remain in git history, and the example videos still show client contacts on screen. Decide on anonymized re-renders and whether to rewrite history.
5. **Unknown names.** "dots" and "muse" were mentioned as target clients; we support any MCP, OpenAPI, function-calling or shell client. Tell us what they are if they need more.

## Kill criteria

- **CrewAI**: install larger than 2 GB or slower than 5 minutes, or it blocks Python 3.12 on macOS arm64 or Linux, or a role cannot be pinned reproducibly → ship only `PlainRunner` (a simple tool loop behind the same `AgentRunner` Protocol).
- **A2A SDK**: if in-process transport needs HTTP, keep A2A at the external boundary only; internal calls stay direct and emit the same events.
- **Langfuse**: if it needs more than `docker compose` and ~2 GB RAM, keep `JsonlTracer` as the default; Langfuse stays opt-in.
- **3D scene**: if a mid-range phone stays under 30 fps at 200 items after LOD and coalescing, ship the 2D belt view driven by the same event mapping.
- **Real Oficial**: if OAuth cannot be completed headlessly from our client, document the manual token path and rely on `ExportPublisher` until it can.

## What we deliberately do not copy from Fastlane

Account warming and managed accounts (platform terms and ban risk), scraping platforms for a trend library (fragile and against terms; our library is user-curated), and volume-first posting (our scoring rewards learning and quality).
