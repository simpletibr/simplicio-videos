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

- Hard daily caps per brand: LLM USD and tokens, media credits, renders, posts per platform; `max_in_flight_items`; quiet hours in the brand timezone.
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

Multi-user accounts and billing, hosted SaaS, managed or warmed social accounts, platform scraping, browser automation of posting, autonomous purchases, any change to the render determinism guarantees.
