# Image brief: richer art for the Brazil theme (GPT Image 2 through Real Oficial)

**Status (2026-10-07): the pipeline is ready, no image is generated yet.** The owner asked to use Real Oficial's MCP with GPT Image 2 to improve the graphics and characters. The MCP is connected, but the connection was authorized with read permissions only (`projects:read`, `account:read`). `ro_estimate_image` and `ro_confirm_spend` both need **`media:write`**, so image generation is refused until the owner re-authorizes (`/mcp`, then `realoficial`, then Re-authenticate, and tick `media:write` on Real Oficial's screen; publishing, purchase, projects and renders are not needed).

## What the catalog says (read on 2026-10-07; prices change, always quote first)

- Model `gpt-image-2`: 5 credits per image, 3 in economy mode (delivered within 24 hours). The plan includes **50 images per month** (0 used, resets 2026-11-02), used before credits.
- Up to 4 images per request. Aspect ratios: 1:1, 16:9, 9:16, 4:5, 5:4, 4:3, 3:4, 3:2, 2:3. No transparent background option, so characters are generated on flat white and cut out locally.
- Workspace: "Espaço pessoal" (owner). Daily budget of this connection: 300 credits.

## Rules

1. **Image tools only** (`ro_estimate_image`, `ro_confirm_spend`, `ro_list_media`, `ro_whoami`, `ro_list_media_models`). Never publish, schedule, connect accounts, buy credits or touch projects and renders.
2. Every image is **quote, then confirm**: `ro_estimate_image` returns a price and `quote_id`; show the price to the owner and call `ro_confirm_spend` only after they say yes in the conversation. Ask once for a cap that covers the batch (this brief proposes 24 images and, if they are charged, at most 120 credits) and stay inside it.
3. Generate **one** character first (Brush), review it with the owner, then the rest. Use `enhance_prompt: false` so the shared style stays identical across images.
4. Media links in tool results expire within an hour and are personal: download them to disk, never paste them anywhere.
5. Raw files go to `src/art/raw/` (git-ignored); only the small WebP files and the generated `src/proto.art.data.js` are committed.

## Shared style (start every character prompt with this)

> Original character design for a friendly factory-worker robot mascot. Soft 3D clay render look, rounded shapes, big simple eyes, a small antenna with a colored bulb, clean studio lighting, subtle outline, front three-quarter view, full body, centered, plain flat white background, no floor, no ground shadow, no text, no logos, no letters, not based on any existing character or franchise. Palette: leaf green #25a050 body, cream #ffe9a8 face, sun yellow #ffd23f and azulejo blue #2a62c9 accents.

## Assets

| # | File in `src/art/raw/` | Aspect | Prompt (after the shared style for characters) |
|---|---|---|---|
| 1 | `char-brander` | 2:3 | The robot is named Brush, the brand painter: holds a paintbrush and a small color palette, tiny paint dots on its suit |
| 2 | `char-ideator` | 2:3 | Spark, the idea maker: a glowing lightbulb floating above the head, a notepad in hand |
| 3 | `char-director` | 2:3 | Clapper, the director: holds a film clapperboard, a small camera strap across the chest |
| 4 | `char-gatekeeper` | 2:3 | Gate, the quality gatekeeper: yellow hard hat, a round red stop-sign paddle, reflective vest |
| 5 | `char-poster` | 2:3 | Post, the publisher: holds a megaphone, a paper plane circling one shoulder |
| 6 | `char-analyst` | 2:3 | Lens, the analyst: a large magnifying glass, a tiny bar chart badge on the chest |
| 7 | `char-reflector` | 2:3 | Mirror, the reflector: a round hand mirror, a calm thoughtful expression |
| 8 | `char-evolver` | 2:3 | Sprout, the evolver: a small green sprout growing from the top of the head, a watering can in hand |
| 9 | `plaza` | 1:1 | Original Brazilian azulejo tile pattern, blue and white, flat top-down view, no perspective, no text, repeats seamlessly in both directions |
| 10 | `hero-day` | 16:9 | Isometric illustration of an original toy factory conveyor loop with seven small kiosks, palm trees and colorful bunting, bright daylight, friendly robot workers walking along the belt, no text |
| 11 | `hero-night` | 16:9 | The same scene at night, warm lit windows and street lamps, deep blue sky, no text |
| 12-16 | `poster-1` to `poster-5` | 9:16 | Vertical video background, warm photographic still life, no text, no logos, no people: (1) a hand grinder and coffee beans on a wooden table, (2) an espresso shot pouring into a white cup, (3) a small kraft shipping box of coffee bags on a doorstep, (4) a kettle pouring water over a pour-over dripper, (5) a sunlit morning table with a mug and a notebook |

## Wiring (already done)

`python3 docs/factory/prototype/src/art/pack.py` cuts out the white background of the characters, trims and re-encodes them, makes the plaza tile seamless, resizes the rest, writes WebP files to `src/art/webp/` and the data URIs to `src/proto.art.data.js`; then `python3 docs/factory/prototype/src/build.py` rebuilds `index.html`. The prototype uses the art when it exists and falls back to its own drawings when it does not:

- characters: the `3D with 2D art` view and the 2D fallback (and the theme card), brazil theme only;
- plaza: the azulejo texture under the belt;
- heroes: the login page and the Brazil scenario card (night one follows day and night);
- posters: Review, Studio and Publish previews, thumbnails, the dock and the 3D video cards.

The pipeline was tested with stand-in images made from the prototype's own drawings.

## Licensing and rules

- Record on every asset: tool (GPT Image 2 via Real Oficial), date, prompt and the provider's terms for commercial use and ownership. **Read Real Oficial's terms before anything generated here ships in the product**; until then the images are `art_origin: ai-generated` and the theme is `experimental`.
- Characters stay original. No look-alikes of any franchise, no real people, no brand logos.
- Nothing generated is committed without the owner reviewing it.
