# Integrations catalog

Every integration is a plugin ([plugins.md](plugins.md)). **Only Real Oficial is in the MVP.** The rest are planned, and each one starts with a spike because vendor APIs and terms change. Facts below were checked against vendor documentation on **2026-10-06**; "NOT FOUND" means the researcher could not verify it. Re-verify before building.

## Principles

1. **Our plugins call APIs directly; they never go through a model.** MCP servers are for external agents (Claude, GPT, Hermes Agent, OpenClaw) that drive the conveyor with their own tokens. This keeps the default path at zero LLM tokens.
2. **REST and webhooks first** for headless loops; an official MCP is a bonus for assisted setup and exploration. Interactive OAuth (HubSpot, Real Oficial) needs a human to log in once.
3. **Bring your own account:** each user connects their own credentials; the self-hosted product never sends them to us. (A paid hosted version, if it comes, needs its own custody model.)
4. **Respect data terms.** Several vendors restrict AI use or caching of their data (see below); the plugin manifest states which.
5. **Paid generation is optional per item** and always goes estimate → budget reservation → confirm token.
6. A new Protocol (commerce, CRM, attribution, analytics) is added by the first plugin of its kind, with a contract suite.

## Real Oficial (the default provider)

The MVP uses it for **publishing and scheduling** and **analytics**; captions are optional. Later milestones add translation and dubbing (described as free), covers, AI media and launcher queues. The full 49-tool map is in [`docs/realoficial.md`](../realoficial.md).

Open risk: no tool in the published list accepts a local MP4, and the REST documentation (`docs.realoficial.com.br`) is behind a browser check that blocks automated reading. Issue #19 starts with that spike and the feature request to Real Oficial; the export bundle ships regardless. Direct platform publishing is **not** a substitute: YouTube, TikTok and Meta each require a per-app audit or review for public posting, which every self-hoster would have to pass, while Real Oficial holds those approvals.

## Catalog

| Service | Category | Plan | Official MCP | API | Recommendation | Issue |
|---|---|---|---|---|---|---|
| **Real Oficial** | publisher, analytics, media | **MVP** | yes (OAuth, 49 tools) | REST docs exist, unread | MCP client plugin | #19, #22, #40 |
| Meta (Facebook, Instagram) | publisher, metrics, ads | M4 | Ads MCP (beta, no publishing) | Graph API, gated | REST for insights; rely on Real Oficial to post | #59 |
| Google (YouTube, GA4, Ads) | publisher, metrics | M4 | Analytics and Ads MCPs (read-only); none for YouTube | YouTube Data API (audit gate) | GA4 REST; YouTube via Real Oficial | #59, #64 |
| TikTok | publisher, ads | M4 | Business MCP (ads only) | Content Posting API (private until audited) | Rely on Real Oficial to post | #59 |
| Stripe | commerce | M4 | yes (remote) | REST and webhooks | REST and webhooks | #60 |
| PayPal | commerce | M4 | yes (remote) | REST and webhooks | REST and webhooks | #60 |
| AbacatePay | commerce | M4 | yes | REST v2 and webhooks | REST and webhooks | #60 |
| CartPanda | checkout | M4 | no | docs unreadable | after capturing a live payload | #61 |
| Kirvano | checkout | M4 | no | no public API found | after capturing a live payload, else skip | #61 |
| HubSpot | CRM | M4 | yes (remote, interactive OAuth) | REST, private-app token | REST | #62 |
| RedTrack | attribution | M4 | yes (key in URL, 20 req/min) | REST docs not found | MCP first | #63 |
| Utmify | attribution | M4 | no | aggregates only | skip for v1 | #63 |
| Microsoft Clarity | analytics | M4 | yes (stdio) | 10 requests per day | REST daily snapshot | #64 |
| Google Analytics | analytics | M4 | yes (experimental, read-only) | Data API v1 | REST | #64 |
| Semrush | market intelligence | M4 | yes (read-only) | paid units | MCP for research; legal review for LLM use | #64 |
| Similarweb | market intelligence | M4 | yes (interactive OAuth) | paid credits | optional REST, bring your own subscription | #64 |
| Vturb | VSL player analytics | M4 | no | REST, gated | REST | #65 |
| Hermes Agent | agent runtime (client) | M4 | consumes MCP | OpenAI-compatible API, A2A | recipe, not a plugin | #66 |
| OpenClaw | agent runtime (client) | M4 | consumes MCP | gateway HTTP, A2A | recipe, not a plugin | #66 |
| TopView | paid AI media | M4 | yes (OAuth) | REST | REST, optional per item | #67 |
| Higgsfield | paid AI media | M4 | yes (OAuth) | REST | REST, optional per item | #67 |

Already in the engine today (not plugins yet): Gemini TTS, Kokoro, VoxCPM2, OpenVoice, VoiceStudio (voice providers); video-use (editing); OpenMontage, OpenCut, Hypit (external tools). Their licenses are in [monetization.md](monetization.md#tool-license-matrix-checked-2026-10-06-against-each-repository).

## What the research changed

- **Platform gates:** public posting on YouTube, TikTok and Instagram needs a per-app audit or review; TikTok's guidelines say apps must not be for private or personal use. This is the main reason Real Oficial is the default publisher.
- **AI-disclosure fields exist on every platform** (`is_ai_generated` on Instagram, `containsSyntheticMedia` on YouTube, `is_aigc` on TikTok): the `ai_disclosure` flag of an item maps to them.
- **Data terms:** Semrush bars using its data as AI prompts outside official integrations; HubSpot bars AI training on customer data and long caching; RedTrack uses aggregated data for model training; Similarweb needs consent to publish its numbers; TopView's free plan bars commercial use; Higgsfield requires AI disclosure and forbids removing provenance signals.
- **Webhooks:** Higgsfield documents no signature and TopView's payload is not documented: re-fetch status before trusting a callback.
- **Hard rate limits:** Clarity allows 10 export requests per project per day; Utmify's read API 10 per minute.
- **Attribution carriers** for a content id: Stripe `client_reference_id` or `metadata`, PayPal `custom_id`, AbacatePay `externalId` or `metadata`, CartPanda and Kirvano `utm_*` and `src`.
- **Hermes Agent and OpenClaw** are MCP clients with skills, not things we build plugins for: we ship role skills and a connection guide. OpenClaw's gateway HTTP is operator-level access: loopback or tailnet only.

## Verification log

| Date | Method | Scope |
|---|---|---|
| 2026-10-06 | Vendor documentation, official repositories and the GitHub API; automated sources only, no logins | all rows above |
| pending (#49) | A human connects to Real Oficial and records tool schemas and the upload result | Real Oficial |
