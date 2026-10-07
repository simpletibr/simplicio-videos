# Business model, licensing and sponsorship

Owner decision (2026-10-06): the product is **free to use and not open source**. Revenue comes from **selling placements to advertisers on the site**. This file records what that implies. Items marked *to confirm* are open.

## What was decided

- Free to use. No billing and no paywalled features in the product.
- Proprietary license (all rights reserved, with a free-use grant in an EULA). The source repository is private today.
- We **build on** open-source tools; each one's license must allow how we use it (matrix below).
- Revenue is advertising: placements sold to advertisers. The MVP contains **no ad code**; the architecture must not make it hard later.

## What "the site" means (to confirm)

| Inventory | Where | For | Against | Verdict |
|---|---|---|---|---|
| **Public website**: landing, docs, theme gallery, plugin and integration directory, blog | hosted by us | Measurable traffic, no risk to the product, easy to sell | Needs traffic and a hosted site | **Start here** |
| Native sponsor cards inside the panel (a signed feed the daemon fetches) | the user's machine | Reaches active users | Local-first and offline use, privacy, trust, security; impressions cannot be proven offline | Later, opt-out, native only |
| Sponsored themes (an advertiser-branded factory scene) | theme gallery and panel | Fits the product, high attention | Brand safety, IP, feels intrusive | Later, clearly labeled |
| Sponsored listings in the integration directory (HubSpot, Semrush, ...) | website | Natural for tool vendors | Editorial independence | With a "Sponsored" label |

## Guardrails (not negotiable)

1. **No advertiser script, iframe or third-party tag ever runs in the panel's origin.** The panel holds a human session that can publish and spend; a malicious ad would own it. In-panel sponsor cards are static data (image, text, link, label) rendered natively, links open in a new tab with `rel="sponsored noopener noreferrer"`.
2. The sponsor feed is **signed** with our key and creatives are **reviewed**; the daemon verifies the signature, caches, and shows nothing when offline or when verification fails.
3. **No behavioral tracking.** Sell fixed, contextual slots at a flat fee; count impressions and clicks on our server through first-party redirects; no per-user profile. The product sends **no telemetry by default**; anonymous usage stats are opt-in. A privacy policy and consent flow follow LGPD and GDPR.
4. Every placement is labeled **Sponsored**. Advertising law applies to our own surfaces (in Brazil, CONAR guidance) even though platform rules apply to the content our users post.
5. In-panel cards have an **opt-out** in Settings. **Editorial independence**: sponsors cannot influence which integrations we build or how compliance rules read; conflicts are disclosed.
6. An **advertiser policy** excludes categories that conflict with the product (for example gambling, adult, deceptive finance) and any claim we would reject in our own compliance checks.
7. **No ads inside generated videos.** User content never carries our advertising (a "made with" credit would be opt-in, *to confirm*).

## Engineering implications

- **First hosted components**: a static public site plus a small service for signed sponsor feeds and first-party click counting. Everything else stays local. Backlog: #68 site, #69 sponsors, #70 legal (milestone M6).
- **Distribution.** "Clone the repo and install" needs the repo to be reachable by users, but a private repo is not. Options *(to confirm)*: (a) a public repository with a **source-available proprietary license**: simplest, keeps `git clone` and `update = git pull`; (b) private source with signed **release archives** published on the site: `install.sh` downloads them and `update` fetches newer releases. #43 keeps the update logic in one module so (b) is a local change.
- **SDK and plugin terms.** A proprietary core with a plugin ecosystem needs an SDK license that lets third parties build and distribute plugins, and plugin rules (permissions, no ad injection into the panel).
- **Themes.** Official art is project-owned and proprietary (free to use inside the product). Third-party themes carry their authors' licenses; the gallery lists only themes whose license lets us host them.
- **Dependency licenses** must allow proprietary distribution; see the matrix. The license scan (#46) now gates this.
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

This is engineering guidance. The EULA, privacy policy, advertiser terms, dependency obligations and advertising-law questions need a lawyer before launch (#70).
