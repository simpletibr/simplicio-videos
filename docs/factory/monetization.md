# Business model, licensing and sponsorship

Owner decision (2026-10-07, replaces the 2026-10-06 one): the product stays **free to use** and its **code becomes public** under a source-available or open license (to confirm with a lawyer in #70). Revenue comes from what grows with use (a partnership with the default provider), from **direct sponsorships**, and only then from site ads. This file records what that implies. Items marked *to confirm* are open.

Why the change: ads on the website alone are unlikely to pay for development. The site itself costs almost nothing, people who use the product spend their day in the local panel and not on the site, and a technical audience blocks ads heavily. Public code costs nothing in site revenue, helps trust (the tool holds publishing powers on social accounts) and fixes distribution (a private repository cannot be cloned).

## What was decided

- **Free to use.** No paywalled features in the self-hosted product.
- **Public code.** License *to confirm* (#70). Recommended: **FSL** (Functional Source License: any use except a competing commercial offering for two years, then Apache-2.0), or **AGPL** if the owner prefers real open source. Before the repository goes public, its history must be cleaned (client data, contacts in example videos, sales lists) and the generated art's terms read; see [blueprint.md](blueprint.md).
- **Revenue, in this order:**
  1. **Partnership with Real Oficial**, the default publisher: ask for a referral or revenue share on credits users buy through the app, in the same conversation as the missing MP4 upload endpoint (#19). Paid generators get the same treatment, always disclosed to the user.
  2. **Direct sponsorships** at a fixed monthly price on the site, the theme gallery and the docs, sold to companies in the ecosystem (online stores, payments, marketing tools), and **sponsored themes** (a brand's world), clearly labeled.
  3. **Site ads** from a network that does not track, only after the site passes about 50k pageviews a month.
  4. **A paid hosted version later** for people who do not want to install anything. Not in the MVP; it needs its own tenancy, custody and threat model.
- **The local panel carries no ads.** Spaces in the factory scenery that are not used show the user's own content. The rentable spaces of [ads.md](ads.md) live in the public view-only window of a factory and in the gallery, and come after direct sponsorships.
- We **build on** open-source tools; each one's license must allow how we use it (matrix below).

## What "the site" means (to confirm)

| Inventory | Where | For | Against | Verdict |
|---|---|---|---|---|
| **Public website**: landing, docs, theme gallery, plugin and integration directory, blog | hosted by us | Measurable traffic, no risk to the product, easy to sell | Needs traffic and a hosted site | **Start here**, direct sponsorships first |
| **Public window**: a view-only link to someone's factory (the world view) | hosted by us | Real audience, shareable, shows the product working | Needs a relay and the owner's consent per factory | After the site; home of the scenery spaces in [ads.md](ads.md) |
| Native sponsor cards inside the panel (a signed feed the daemon fetches) | the user's machine | Reaches active users | Local-first and offline use, privacy, trust, security; impressions cannot be proven offline | **No** (decision 2026-10-07): the local panel is ad-free |
| Sponsored themes (an advertiser-branded factory scene) | theme gallery and panel | Fits the product, high attention | Brand safety, IP, feels intrusive | Later, clearly labeled |
| Sponsored listings in the integration directory (HubSpot, Semrush, ...) | website | Natural for tool vendors | Editorial independence | With a "Sponsored" label |

## Guardrails (not negotiable)

1. **No advertiser script, iframe or third-party tag ever runs in the panel's origin.** The panel holds a human session that can publish and spend; a malicious ad would own it. In-panel sponsor cards are static data (image, text, link, label) rendered natively, links open in a new tab with `rel="sponsored noopener noreferrer"`.
2. The sponsor feed is **signed** with our key and creatives are **reviewed**; the daemon verifies the signature, caches, and shows nothing when offline or when verification fails.
3. **No behavioral tracking.** Sell fixed, contextual slots at a flat fee (the hourly market in [ads.md](ads.md) is a later complement for the public window, not the starting model); count impressions and clicks on our server through first-party redirects; no per-user profile. The product sends **no telemetry by default**; anonymous usage stats are opt-in. A privacy policy and consent flow follow LGPD and GDPR.
4. Every placement is labeled **Sponsored**. Advertising law applies to our own surfaces (in Brazil, CONAR guidance) even though platform rules apply to the content our users post.
5. In-panel cards have an **opt-out** in Settings. **Editorial independence**: sponsors cannot influence which integrations we build or how compliance rules read; conflicts are disclosed.
6. An **advertiser policy** excludes categories that conflict with the product (for example gambling, adult, deceptive finance) and any claim we would reject in our own compliance checks.
7. **No ads inside generated videos.** User content never carries our advertising (a "made with" credit would be opt-in, *to confirm*).

## Engineering implications

- **First hosted components**: a static public site (docs, gallery, sponsors) plus a small relay for the public window and client share pages. Everything else stays local. Backlog: #68 site, #69 sponsors, #70 legal (milestone M6), plus the items listed in [blueprint.md](blueprint.md).
- **Distribution.** Public code makes option (a) the default: `git clone` and `update = git pull`. Signed release archives become an optional convenience. #43 keeps the update logic in one module.
- **Contributor terms.** A public repository needs a DCO or CLA (*to confirm*), a `SECURITY.md` and a trademark note for the name and the official themes.
- **SDK and plugin terms.** Plugins and themes may use any license compatible with the core's; plugin rules forbid ad injection into the panel.
- **Themes.** Official art stays project-owned (free to use inside the product) unless #70 decides otherwise. Third-party themes carry their authors' licenses; the gallery lists only themes whose license lets us host them.
- **Dependency licenses** must be compatible with the chosen license; see the matrix. The license scan (#46) gates this. AGPL tools stay separate programs or services.
- **Docker image.** We ship the `Dockerfile`, not a prebuilt image, until a license review of the bundled components (ffmpeg builds carry GPL or LGPL obligations depending on flags).

## Tool license matrix (checked 2026-10-06 against each repository)

| Tool | License | How we use it | Rule |
|---|---|---|---|
| HyperFrames | Apache-2.0 | engine render dependency, fetched by `npx` at run time | fine |
| video-use | MIT | external helper cloned at a pinned commit | fine |
| Kokoro (kokoro-onnx), faster-whisper, Chatterbox, OpenVoice | MIT | optional local voice and transcription | fine |
| VoxCPM | Apache-2.0 | optional voice provider | fine |
| OpenCut | MIT | optional editor, cloned by the user | fine |
| CrewAI, LangGraph | MIT | later plugins | fine |
| LiteLLM, Langfuse | MIT except their `enterprise/` or `ee/` folders | later plugins | never bundle the commercial folders |
| **OpenMontage** | **AGPL-3.0** | `montage` command runs the user's own checkout as a separate process | external only: never bundled, imported or modified by us |
| **VoiceStudio, Postiz** | **AGPL-3.0** | HTTP only | external service only |
| **Hypit** | modified Apache-2.0: no commercial redistribution and no multi-tenant service without written permission; must keep its name, logo and notices | `clone` command runs the user's own install (`npx`) | **never bundle or redistribute**; read its LICENSE before shipping the command in a monetized product; consider removing it from the default install |
| ffmpeg | LGPL or GPL by build | external binary installed by the user's package manager | do not redistribute binaries |
| Chrome/Chromium (via the render stack) | proprietary and open components | downloaded at run time by the render stack | do not redistribute |

## Not legal advice

This is engineering guidance. The license for the public code (FSL or AGPL), the terms of use, privacy policy, advertiser terms, dependency obligations and advertising-law questions need a lawyer before launch (#70).
