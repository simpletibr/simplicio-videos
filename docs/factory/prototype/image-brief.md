# Image brief: richer art for the Brazil theme (GPT Image 2 through Real Oficial)

**Status: not generated yet.** The owner asked on 2026-10-06 to use Real Oficial's MCP with GPT Image 2 for more elaborate images. The MCP was registered at user scope but this session could not load it, so nothing was generated. This file is the ready-to-run brief.

## Before you run it

1. The MCP must be loaded in the session. It is registered as `realoficial` (HTTP, `https://api.realoficial.com.br/mcp`). If your session does not list its tools, start a new session in this folder; if it says it needs authentication, sign in with `/mcp` (the sign-in is the owner's).
2. Its scopes include `social:publish` and `billing:purchase`. **Use only the image-generation tools** (renders and media). Never publish, schedule, connect accounts or buy credits.
3. Show the cost per image first. Generate **one** character, review it, and only then generate the rest. Stop at 14 images or at the credit limit the owner gives, whichever comes first. Record what was spent.
4. Output goes to `docs/factory/prototype/src/art/` as WebP (character sprites with a transparent background, at most 60 KB each after re-encoding). Do not commit PNGs larger than that.

## Shared style (put this at the start of every prompt)

> Original character design for a friendly factory-worker robot mascot. Soft 3D clay render look, rounded shapes, big simple eyes, a small antenna with a colored bulb, clean studio lighting, subtle outline, front three-quarter view, centered, plain light background, no text, no logos, no letters, not based on any existing character or franchise. Palette: leaf green #25a050 body, cream #ffe9a8 face, sun yellow #ffd23f and azulejo blue #2a62c9 accents.

## Assets

| # | Asset | Size | Prompt (after the shared style) |
|---|---|---|---|
| 1 | Brush (Brander) | 768×1152 | holding a paintbrush with a color palette on the other arm, tiny paint dots on the suit |
| 2 | Spark (Ideator) | 768×1152 | a glowing lightbulb floating above the head, notepad in hand |
| 3 | Clapper (Director) | 768×1152 | holding a film clapperboard, a small camera strap across the chest |
| 4 | Gate (Gatekeeper) | 768×1152 | yellow hard hat, holding a round red stop-sign paddle, reflective vest |
| 5 | Post (Poster) | 768×1152 | holding a megaphone, a paper plane circling one shoulder |
| 6 | Lens (Analyst) | 768×1152 | holding a large magnifying glass, a tiny bar chart badge on the chest |
| 7 | Mirror (Reflector) | 768×1152 | holding a round hand mirror, a calm thoughtful expression |
| 8 | Sprout (Evolver) | 768×1152 | a small green sprout growing from the top of the head, watering can in hand |
| 9 | Plaza tile | 1024×1024, seamless | Original Brazilian azulejo tile pattern, blue and white, flat top-down view, no perspective, no text, repeats seamlessly in both directions |
| 10 | Hero, day | 1600×900 | Isometric illustration of an original toy factory conveyor loop with seven small kiosks, palm trees and colorful bunting, bright daylight, friendly robot workers walking along the belt; no text |
| 11 | Hero, night | 1600×900 | Same scene at night, warm lit windows and street lamps, deep blue sky |

Keep the eight characters consistent: generate Brush first, then pass it as the reference image (if the tool supports it) or repeat the same style block verbatim.

## How to wire them in the prototype

- Character sprites: the `3d-sprites` view builds each agent from an SVG texture in `agent3()` (`src/proto.three.js`, `sprite` branch) and the 2D fallback draws `charSVG()` (`src/proto.art.js`). Load each WebP as a `THREE.Texture` (or embed it as a data URI so `index.html` stays a single file) and keep the SVG as the fallback when a file is missing.
- Plaza tile: `TH3.br.plaza` draws the pattern on a canvas; replace it with the generated tile as a repeating texture.
- Hero images: Settings → Appearance cards and the login page.

## Licensing and rules

- Record on every asset: tool (GPT Image 2 via Real Oficial), date, prompt, and the provider's terms for commercial use and ownership. **Read Real Oficial's terms before anything generated here ships in the product**; until then the images are `art_origin: ai-generated` and the theme is `experimental`.
- Characters stay original. No look-alikes of any franchise, no real people, no brand logos.
- Nothing generated is committed without the owner reviewing it.
