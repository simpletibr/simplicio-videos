# Panel prototype

A clickable prototype of the MVP panel. It exists so the owner and the people who build the panel can **see the screens, fields, states and themes** before the real code exists. It is a throwaway: sample data, no server, no real agents.

![The factory by day](screens/factory-day.jpg)

## Open it

`index.html` is one self-contained file (plain HTML, CSS and JS; no build step). It loads Three.js `0.160.0` from cdnjs and two Google Fonts, so it needs internet. Serve the folder and open it:

```bash
python3 -m http.server -d docs/factory/prototype 8765   # then open http://localhost:8765/index.html
```

Use a local server rather than opening the file from disk: some browsers restrict pages loaded from `file://`.

## What to try

- **A phone app, not a squeezed website.** On a phone the scene is the whole screen. One bottom sheet (drag it, or tap the handle: peek, half, full) holds Following, Queue, Bots and Details; the Approve / Open / Discard card floats above it; the tab bar stays at the bottom; round buttons on the right reset the view and switch day, night, weather and chat. Open the artifact on a phone and the device frame and prototype bar disappear.
- **Factory as a small town.** Each stage is its own kind of building: a workshop house (brand), an idea shop (ideas), a video factory with smoking chimneys (make), an inspection garage (review), a launch market (publish), an observatory (metrics) and a learning barn (report). The lamps on each roof are its rooms: they light up as the followed video moves through the sub-steps inside (the side panel lists them under "Inside this building"). The belt runs through all of it.
- **Move anywhere.** Drag to rotate and tilt, right-drag or Shift-drag to pan, wheel or pinch to zoom from the whole town down to a single robot, WASD or the arrow keys to walk, Q and E to rotate, R to reset. The toolbar has the same controls, plus day and night and weather.
- **Bots.** Click a robot, or open the Bots tab, to chat with it (Brush, Spark, Clapper, Gate, Post, Lens, Mirror, Sprout). Ask for its status, what needs you, to show where it works, to follow it around, to open its page, or change the world: rain, snow, desert, fog, sun, day, night, fly. Replies are templates, so no tokens are spent.
- **A living world.** Weather (sun, rain, snow, desert, fog), drifting clouds, birds, a plane with a contrail, a lake with boats and jumping fish (pan left to find it), fireflies at night.
- **Approve** the amber item at the Quality Gate, then **hold** the button on the Publish step to confirm a post. Posting is a deliberate gesture on purpose.
- **Scenario** (top bar or Settings → Appearance): nine themes. Only Brazil is in the MVP; the others show that the same format carries very different looks.
- **View**: `3D with 2D art` (default when the generated characters exist), `3D with models` (procedural low-poly agents) and `2D flat (fallback)` for devices without WebGL.
- **Device** and **language** (English, Portuguese), **RTL preview**, and the collapsible side menu.
- **Demo autopilot** approves and confirms on its own so you can watch the whole loop. That switch exists only in this prototype.

## Screens

| Screen | Shot |
|---|---|
| Factory by day and night | [day](screens/factory-day.jpg) · [night](screens/factory-night.jpg) · [Portuguese](screens/factory-pt-br.jpg) |
| Station details and the rooms inside | [make](screens/factory-details.jpg) |
| Chatting with a bot | [desktop](screens/factory-chat.jpg) |
| Weather | [snow](screens/factory-snow.jpg) · [desert](screens/factory-desert.jpg) |
| Factory as a phone app (full-screen scene, bottom sheet) | [following](screens/factory-phone.jpg) · [bots](screens/factory-phone-chat.jpg) · [details](screens/factory-phone-details.jpg) · [queue](screens/factory-phone-queue.jpg) |
| Nine themes in 3D | [montage](screens/themes-3d.jpg) |
| Login, Needs you, Brand, Ideas, Studio | [login](screens/login.jpg) · [inbox](screens/inbox.jpg) · [brand](screens/brand.jpg) · [ideas](screens/ideas.jpg) · [studio](screens/studio.jpg) |
| Review, Publish (desktop and phone) | [review](screens/review.jpg) · [publish](screens/publish.jpg) · [review phone](screens/review-phone.jpg) · [publish phone](screens/publish-phone.jpg) |
| Activity, Settings | [activity](screens/activity.jpg) · [scenarios](screens/settings-scenarios.jpg) · [limits](screens/settings-policy.jpg) |

## What it is not

- Not the product. Pages, fields and states follow the spec in [`docs/factory`](../README.md); the numbers are examples.
- Not secure or multi-user. In the product only a human session can approve a video or confirm a post.
- Not final art. The Brazil theme uses original procedural buildings plus characters, plaza tile, heroes and video backgrounds generated with GPT Image 2 (see [src/art/LICENSE.md](src/art/LICENSE.md)); the other eight themes are concepts.

## Design notes the prototype settles

- **One system color**: light blue. Themes restyle the scene only, never the interface.
- **The factory is a digital twin**: the 3D scene is the hero, and the numbers, the followed video, the station details and the queue float over it. On a phone the scene stays on top and the same pieces stack below it.
- **Zero-token motion**: speech bubbles, labels and states are catalog templates filled with ids and numbers, so the scene is alive in every language at no token cost.
- **Accessibility**: reduced motion stops pulses and camera moves; every control has a text label or `aria-label`; the 2D view is the fallback when WebGL is missing.

## URL parameters

`page` (`login`, `factory`, `inbox`, `brand`, `ideas`, `studio`, `review`, `publish`, `activity`, `settings`), `lang` (`en`, `pt-BR`), `theme` (`br`, `us`, `cn`, `ru`, `jp`, `dragons`, `realms`, `courtyard`, `tiny`), `view` (`3d`, `3d-sprites`, `2d`), `tod` (`day`, `night`), `scheme` (`light`, `dark`), `device` (`desktop`, `phone`), `rail` (`min`), `panel` (`1`, `0`), `auto=1`, `rtl=1`, `upload=1`, `tab` (Settings tab).

Handy for screenshots: `warm=14` runs the simulation for 14 seconds before the first frame, `hud=0` hides every overlay and shows the bare scene, `wx` (`clear`, `rain`, `snow`, `desert`, `fog`) sets the weather, `ptab=chat` and `bot=<role>` open a chat, `lowfx=1` lowers shadow quality for software renderers.

## Generated art

The Brazil theme's characters, plaza tile, two hero illustrations and five video backgrounds were generated with GPT Image 2 through Real Oficial (16 images, 0 credits: they fall inside the plan's monthly allowance). [image-brief.md](image-brief.md) holds the prompts and rules. To add or replace art, drop the raw images in `src/art/raw/`, run `python3 src/art/pack.py` and rebuild.

## Rebuild

`index.html` is generated from the files in [`src/`](src/) (CSS, markup, art, message catalogs, the 3D scene, the HUD and the app). After editing them run:

```bash
python3 docs/factory/prototype/src/build.py
```

## Licenses

Three.js is MIT. The fonts are open-licensed (OFL). All art in the prototype is original and generated in code.
