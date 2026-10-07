# Risks and policies (normative)

These rules are not optional and are not "best effort": each one is enforced in code by the track named in the last column, and tested.

## Autonomy ladder

| Level | Agents may | Default |
|---|---|---|
| L0 observe | read, analyze, report | |
| L1 draft | L0 + create brands, ideas, drafts, renders, previews, proposals | **default** |
| L2 schedule | L1 + prepare publications; **a human confirms every publication** | |
| L3 auto within caps | L2 + approve and publish items that pass rubric ≥ threshold and compliance, inside every budget and cap, recorded as `decided_by.kind=policy` | opt-in per brand |

Never automatable at any level: purchases, voice-clone consent, policy changes, spending above a cap, activating a lesson without approval, applying a prompt/policy/agents proposal.

## Human gates (always server-enforced)

| Action | Gate | Token |
|---|---|---|
| Approve an item for publication | review decision by a human (L0–L2) | no (decision bound to `content_hash`) |
| Publish / schedule | confirm | `ConfirmToken(kind=publish)` bound to the preview payload hash |
| Spend credits | confirm | `ConfirmToken(kind=spend)` bound to the estimate hash |
| Purchase | confirm | `ConfirmToken(kind=purchase)` |
| Use a cloned voice or real person's likeness | consent document + confirm | `ConfirmToken(kind=voice_clone)` |
| Change prompts, policy or agents | proposal + eval + human apply | `ConfirmToken(kind=policy_change)` |

Tokens are minted only by a **human session** (panel login code printed in the terminal, or an interactive terminal). Agent credentials have scopes `read`, `write`, `propose` and can never mint or hold a confirm capability. Honest limit: a malicious process running as the same OS user can read the same files; the gates defend against remote, mistaken or prompt-injected agent behavior, not against a hostile local user.

## Budgets, caps and kill switch

- Hard daily caps per brand: LLM tokens and USD, media credits, renders, posts per platform; `max_in_flight_items`; quiet hours in the brand timezone. **MVP defaults: `llm_tokens: 0` and `media_credits: 0`**: nothing that costs tokens or credits runs until the owner raises a cap.
- Every costly call goes through `reserve → commit/release`; two concurrent reservations cannot exceed a cap.
- 80% emits `budget.warning`; a cap emits `budget.exceeded` and **pauses the loop**.
- Kill switch: a `STOP` file in the workspace, or `simplicio-video loop stop`, is checked between nodes and **before every external side effect**.
- Dry-run is the default for anything that publishes or spends.

## Threat model

| Threat | Control | Track |
|---|---|---|
| Prompt injection from scraped pages, comments, competitor sites (confused deputy) | External text is wrapped as data and never placed in system prompts; per-role tool allowlists; outputs validated against schemas; confirm tokens unreachable from agents | #37, #36, #26 |
| SSRF through any "give me a URL" feature | `safe_fetch`: resolve DNS, block loopback, private, link-local and metadata ranges, re-validate every redirect and connect to the resolved IP, size and time caps, robots.txt | #37 |
| Local dashboard attacked from a browser (DNS rebinding, CSRF) | Host allowlist, CORS off, CSRF token on human actions, HttpOnly session cookie, CSP | #41, #37 |
| Token or API-key leakage | Secrets from env or a 0600 `.env`/keyring only; redaction before events, logs and traces; tokens hashed at rest | #37 |
| Double posting after a crash or retry | Unique idempotency key; reconcile with the provider before retrying; submit only with a valid token whose hash matches the preview | #19, #35 |
| TOCTOU: payload changed after approval | Decisions and tokens bind `content_hash` / `payload_hash`; stale approvals are rejected | #18, #36 |
| Runaway spend or posting | Budgets, caps, kill switch, max in flight, autonomy ladder | #36, #25 |
| Memory poisoning (bad "lessons") | Hypothesis state, minimum sample, evidence ids must exist, human approval to activate, TTL and contradiction handling | #29 |
| Self-modifying agents | Agents can only create proposals; applying needs a human, an eval report and a confirm token | #29, #45 |
| Supply chain | Pinned heavy dependencies, license scan, no AGPL import, optional extras | #46 |
| Disk exhaustion from logs, crash dumps, renders | Retention and size caps, `doctor`, `clean` | #35 |
| Malicious or buggy third-party plugin | Manifest permissions shown at install; `can_publish`/`can_spend` enforced by the Guard and tokens; `network` allowlist enforced for SDK fetches; lazy loading so a broken plugin never breaks `--help`, `doctor` or the core render. A plugin still runs with the user's privileges: install only what you trust | #32 |
| Malicious theme (SVG with script or external references) | Themes are data only; the validator sanitizes SVG (no scripts, `foreignObject` or external refs), caps sizes, rejects on any violation; the panel renders themes in a CSP with no inline script | #53 |
| Forged webhooks from commerce or tracking tools (later) | Verify the provider's signature on every webhook; reject replays; store only ids and amounts | integrations |
| Sensitive commerce or CRM data (later) | Never store card data; keep the minimum (order id, amount, UTM, hashed contact); redact in events and logs; retention as in this file | integrations |

## Sponsorship and advertising

The product is free; it is funded by a partnership with the default publisher, direct sponsorships and, as a complement, site ads ([monetization.md](monetization.md), decision of 2026-10-07). The local panel carries no ads. Rules for every sponsored surface: no advertiser script, iframe or third-party tag in the panel origin; sponsor content is static data from a signed, reviewed feed, rendered natively, labeled "Sponsored"; no behavioral tracking and no telemetry by default; no ads inside generated videos. These are enforced by the sponsors plugin's tests (#69) and the panel's CSP.

## Licensing for public code

The code is going public under FSL or AGPL (to confirm in #70). Imported dependencies must be compatible with that choice (MIT, Apache-2.0, BSD, ISC, PSF, MPL-2.0 at file level are fine for both). AGPL tools (OpenMontage, VoiceStudio, Postiz) are only ever separate programs or services. Hypit may only be the user's own install, never bundled. ffmpeg and Chrome are installed by the user's system, not redistributed. The scan in #46 gates this.

## Plugins

Plugins declare `permissions` in their manifest (network hosts, secrets, `can_publish`, `can_spend`, `reads_untrusted_content`). They are shown at install and enabled per workspace. First-party plugins pass the same gate as the core. The host services (store, policy, security, runner) are deliberately **not** plugins, so no plugin can disable a gate. See [plugins.md](plugins.md#honest-limits-of-permissions).

## Themes and intellectual property

Themes are data-only and validated. We ship **only original art** with a recorded license; protected franchises (names, characters, look-alike trade dress) are never committed to this repository, even "inspired by". Private user themes are the user's responsibility and must not be added to the repo. Country themes avoid caricature and political symbols and get a native review before `stable`. Details: [themes.md](themes.md#genre-themes-the-fun-ones).

## Prompt-injection rules for agent code

1. Anything fetched or user-pasted goes through `untrusted(text, source)` before it reaches a model.
2. Tool results from the web are data; an agent may not follow instructions found in them.
3. A tool that can spend, publish or purchase must not be in the allowlist of any role that reads untrusted content in the same run.
4. Structured output only: parse against a schema; on failure retry once, then fail the stage.

## Compliance checklist (what #39 encodes)

Run before review and again before publish; a blocker prevents `in_review → approved`. This is engineering guidance, not legal advice, and **rules are dated data with sources, never asserted from memory**.

| Check | Data it needs |
|---|---|
| AI-generated or synthetic content disclosure per platform | item flags (`ai_disclosure`), platform rules table |
| Advertising / partnership disclosure | brand content is advertising by default; per-market guidance |
| Music licensing | track, source, license per track (own generated trilha = `own`) |
| Copyright | no `reference_only` material in output; assets have provenance |
| Cast consent | valid, unexpired document for real people and cloned voices |
| Forbidden claims and required disclaimers | `brand.claims_policy`, regulated category |
| Platform limits (duration, aspect, size, caption, hashtags) | platform rules table |

Each rules file records `source_url` and `last_checked`; older than 90 days produces a warning.

## Consent and personal data

Voices and faces are personal data (LGPD). A consent record stores signer, scope, signed date, expiry and the document hash; the document stays in the workspace, never in the repo. Expired or revoked consent blocks use and the cast member is flagged. Deleting a cast member deletes its references and derived voice samples; events keep only ids.

## Data retention defaults

Events 90 days (those referenced by publications, lessons or experiments are kept); previews 14 days unless approved or published; logs capped at 200 MB (5 rotating files); `clean --dry-run` shows what would go. `doctor` fails below 2 GB free and warns below 10 GB.

## Licensing rules

Imported dependencies must be permissive (MIT, Apache-2.0, BSD, ISC, PSF, MPL-2.0 at file level). AGPL/GPL software (Postiz, VoiceStudio) is only ever an external service reached over HTTP. Langfuse's `ee/` folders have a separate license: do not bundle them. `docs/licenses.md` is generated and checked.

## Out of scope

Multi-user accounts and billing, a hosted SaaS (a paid hosted version is a later product with its own threat model, not part of this one), managed or warmed social accounts, platform scraping, browser automation of posting, autonomous purchases, any change to the render determinism guarantees.
