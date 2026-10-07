# Ad spaces and the ad market

> **Status after the 2026-10-07 decision** ([monetization.md](monetization.md)): ads are a **complement**, not the funding source. Direct sponsorships at a fixed monthly price come first. The **local panel carries no ads**; the rentable spaces described here live in the **public view-only window** of a factory and in the theme gallery, and vacant spaces in the local panel show the user's own content. The prototype still shows the spaces in the local scene to illustrate the idea.

The factory scene can carry placements: every house, balloon and billboard in the world is a **space anyone can rent for a few hours**, for the whole world, one country or one region, at a price that moves with supply and demand, like an ad auction.

This page is the spec. A clickable version exists in the [prototype](prototype/README.md) (the **Ads** page and the spaces in the scene); its numbers are invented and no money moves.

## How this fits the business model

[monetization.md](monetization.md) fixes the guardrails: no advertiser script, iframe or tag in the panel's origin, a signed and reviewed sponsor feed, no behavioral tracking, a visible label, an opt-out, no ads in generated videos, and an advertiser policy. Everything below keeps them. Two things are new, both asked for by the owner on 2026-10-07:

1. The inventory is **the scenery of the factory itself**, not a card in a corner: spaces you can see and tap in the world.
2. Prices are **dynamic by supply and demand, per place and per hour**, not a flat fee. That replaces guardrail 3's "flat fee" for these spaces; the rest of guardrail 3 (no per-user profile, first-party counting, no telemetry) stands.

The MVP v0.4.0 still ships with no ad code. This page is what a later milestone builds (backlog #68 to #70, M6).

## Rules that do not bend

- **Static images only.** A reviewed PNG or WebP, no animation, no HTML, **no third-party ad script** anywhere in the panel or the scene.
- **Always labeled.** Every creative carries a visible tag ("Ad" in the prototype; [monetization.md](monetization.md) says "Sponsored", the wording is a legal call for #70). The renderer draws it, the advertiser cannot remove it. Vacant spaces say "Ad space" and show the price.
- **Opt-out.** A switch in Settings hides every space; the posts and frames stay as plain scenery. Offline, or when the signed feed fails to verify, the spaces also show as plain scenery, never as a "your ad here" sign.
- **Nothing inside generated videos**, and nothing in the panel chrome (menus, tables, forms). Ads live only in the scenery.
- **No personal data.** The viewer's place is a coarse country and region taken at the edge (or the language as a fallback). No cookies, no profile, no tracking across sites. Everyone in the same place sees the same ad.
- **Signed and reviewed.** The daemon gets the current rentals for the viewer's place as a signed feed and verifies it. Every creative passes automatic checks (size, type, blocklist) and a human review. Rejected creatives are never shown and the rental is refunded.
- **Zero LLM tokens.** Pricing, auction and delivery are plain arithmetic.
- **Prices are public.** The price of a space for the next 24 hours is visible to anyone, and the formula is shown beside it.

## What can be rented

23 spaces. Each house has three, the world has two.

| Space | Where | Creative | Seen by |
|---|---|---|---|
| Billboard | high on two posts behind the house | 1280×720 | people looking at that house |
| Belt flags | two flags on poles at the belt, in front of the house | 280×640 | people looking at that house |
| Balloon | a hot-air balloon drifting in the sky behind the house | 1280×720 | people looking at that house |
| Blimp | an airship circling the ring; the ad is on both sides and on top | 1920×600 | people in the world view |
| Plaza floor | a big decal on the courtyard in the middle of the ring | 1280×720 | people in the world view |

Houses are not equal. The share of sessions that see each one (`VISIT`) is the main reason their prices differ: Review and Publish are where people must act (0.50), Make is where they watch the video appear (0.45), Ideas 0.25, Brand 0.22, Metrics 0.20, Reflection 0.15. The world view is opened by 0.30 of sessions.

## Where: world, country, region

Places form a tree: **world → country → region** (ISO 3166-1 and 3166-2 codes). A rental covers one node and everything under it.

- **Region**: one state or province. The smallest unit.
- **Country**: all its regions. Priced as the sum of its free regions with an 8% volume discount.
- **World**: all countries. Priced as the sum of its free countries with a 12% volume discount.

A viewer sees, on each space, the rental that covers their place, **the most specific first** (region before country before world). Two advertisers can hold the same space at the same hour only if their places do not overlap; if part of a country is already taken, a country rental is not offered, a smaller one is (the page shows "3 of 5 places free").

## The unit of sale

`(space, place, hour)`. An hour is a UTC clock hour. A rental is 1 to 24 consecutive hours, starting from now up to 7 days ahead. Within one unit there is exactly one advertiser, so there is no rotation and no frequency capping to argue about.

## How the price is set

For one region `g`, space `s` and hour `h`:

```
sessions(g,h)   = 20 000 × share(g) × curve(g,h)          sessions an hour in that place
impressions     = sessions × reach(s) × visit(house) × 12    12 views per session
floor           = impressions / 1000 × CPM0 × tier(g)         CPM0 = 2.00 (USD), tier = what advertisers pay there
rented(g,h)     = min(1, 2.2 × rented spaces covering g at h / 23)
interest(s,g,h) = how much other advertisers are watching or bidding, 0..1
multiplier      = 1 + 2.2 × rented^1.5 + 1.6 × interest²       between 1 and about 4.8
lead time       = 0.75 + 0.08 × hours_to_start   if it starts within 3 h and is still vacant
                  0.88                           if it starts more than 48 h away
                  1                              otherwise
price           = max(0.50, floor × multiplier × lead time)
```

- `curve(g,h)` follows the local day: 0.25 at night up to 1.0 in the afternoon.
- `share(g)` is the place's share of all sessions (Brazil 0.34, United States 0.22, ...). `tier(g)` is a purchasing-power index (United States 1.8, Germany 1.5, Japan 1.4, Portugal 0.9, Brazil 0.7, Mexico 0.55).
- **Supply** shows up as `rented`: the more of the 23 spaces are taken in a place and hour, the dearer the rest. **Demand** shows up as `interest`: in production it is made of the bids and the "watchers" (people who opened the price and did not buy yet) in the last hours, smoothed with an EWMA so a single click cannot move a price. The prototype fakes it with a seeded wave.
- Prices are recomputed when anything changes and at least every minute. A booking, once made, **keeps its price**.
- Worked example (prototype numbers): Make billboard, São Paulo, 14:00 local. `sessions` 2 176, `impressions` 6 463, `floor` $9.05, `rented` 0.40, `interest` 0.50, `multiplier` 1.96, price about $17.70 an hour.

## Two ways to buy

1. **Buy now** at the posted price. The unit is locked at once.
2. **Bid**: choose a maximum per hour. Bids are settled in a **second-price auction** at the hour's lock time (60 minutes before it starts): the highest bid wins and pays **the second-highest bid plus 0.01, never less than the floor**; with a single bid the winner pays the floor. Ties go to the earlier bid. A bid is a promise: the maximum is held on the payment method until settlement. Bidding is the way to pay less than the posted price, at the risk of being outbid; the prototype shows both outcomes.

An advertiser holds at most 40% of the spaces of one place and hour, so nobody can buy a whole country for an evening. That cap is part of the contract tests.

## Cancel, refund, make-good

- Free cancellation until 24 hours before the first hour; half back from 24 to 2 hours; nothing after.
- If a creative is rejected, or the scene was down so that delivered impressions are under 80% of what the floor assumed, the advertiser gets the missing hours back as credit (make-good), automatically.

## Data model (for issue #23's owner to turn into a contract)

`ad_space(id, house|world, kind, aspect)`, `geo_node(id, parent, level, share, tier, tz)`, `ad_rental(id, advertiser, space, node, start_hour, hours, price_per_hour[], state)`, `ad_bid(id, advertiser, space, node, hour, max, placed_at)`, `ad_creative(id, advertiser, hash, state, reviewed_by)`, `ad_hour_stat(space, node, hour, impressions)`. Everything is keyed by hour so the price history is a table anyone can chart.

## Open decisions

- **Which site carries the ads**: the panel itself, a public page of the factory, or both (still open since 2026-10-06). This spec assumes the scene; the panel chrome stays ad-free.
- **Can a paying user hide the ads** (and then what pays)? Not decided.
- **Payment provider and invoices** (Brazil needs a fiscal document): not chosen. Nothing in the prototype touches payments.
- **Restricted categories by country** (alcohol, betting, health claims, politics): needs a policy and a person to own review.
- **Whether advertisers may link out**: a click-through opens the advertiser's page in a new tab with `rel="noopener sponsored"`; the scene is not a navigation surface today.
- **Real audience numbers**: until the product has traffic, floors come from the assumptions above and must be re-based on measured sessions.

## Where it lives in the prototype

`prototype/src/proto.ads.js` (geography, spaces, price, auction, creatives, the Ads page, the 3D spaces) and the **Ads** item in the menu. Tap a billboard or balloon in the scene to open the page with that space selected. The world view is look-only, so the spaces there cannot be tapped.
