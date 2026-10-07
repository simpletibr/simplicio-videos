# Panel prototype

A clickable prototype of the MVP panel. It exists so the owner and the people who build the panel can **see the screens, fields, states and themes** before the real code exists. It is a throwaway: sample data, no server, no real agents.

![The factory by day](screens/factory-day.jpg)

## Open it

`index.html` is one self-contained file (plain HTML, CSS and JS; no build step). It loads Three.js `0.160.0` from cdnjs and three Google Font families, so it needs internet. Serve the folder and open it:

```bash
python3 -m http.server -d docs/factory/prototype 8765   # then open http://localhost:8765/index.html
```

Use a local server rather than opening the file from disk: some browsers restrict pages loaded from `file://`.

## What to try

- **One house at a time.** The factory is a ring of seven houses, far apart. You stand in front of one and see it like a **cutaway**: no front wall, so it reads as a flat facade while the structure is real 3D (move the pointer and the view leans a little; the painted world behind stays still). Each house has rooms, one per sub-step, with a plaque, a lamp and props. The robot of the house walks from room to room, working where the followed video is. The belt runs in front, the followed video waits at the gates.
- **Go house by house.** The round arrows at the sides, a swipe, or the left and right arrow keys take you to the next house; the camera swings around the ring. The followed video pulls the view along on its own; press the eye in the caption to let it, or pick any house in the stepper or the queue to stay there.
- **See the world.** The button in the top bar lifts the camera over the whole ring. From above you can turn, tilt, zoom and move, but nothing can be done: the panel, chat and queue are hidden and the spaces cannot be tapped. Tap a house (or **Back to the house**, or Esc) to come back in front of it.
- **Each house is its own world.** Seven worlds painted with GPT Image 2 (a painter's valley, floating idea islands, a whimsical factory valley, a mirror lake, a seaside harbor, a starry plateau, an autumn meadow) with clay props in front that touch the house: pond and waterfall, lamp-flowers, waterwheel and steam tanks, stepping stones and an arch, a pier with boats and balloons, a telescope rock and jellyfish, a windmill and ducks.
- **Tap things.** Paintbrush trees change color, lamp-flowers play a note, the waterwheel speeds up, the tanks puff rainbow steam, water ripples, stones hop, balloons pop and come back, jellyfish glow, the telescope throws a shooting star, ducks quack, the windmill spins faster. Tap a robot to chat with it. The cursor becomes a hand over anything tappable.
- **Sound.** Each scenery has its own ambience, made in the browser (no audio files): waterfall and birds, chimes, machine hum, sea waves and gulls, night pad with crickets, wind and geese. Rain, snow, desert wind and fog add their own. Gates, approvals, renders and posts make soft sounds. It starts at your first tap or key; the speaker button mutes it and the choice is remembered (`snd=0` starts muted).
- **Ad spaces.** Every house has a billboard, belt flags and a balloon; the world has a blimp and a plaza decal. Vacant ones say "YOUR AD HERE" and the price per hour. Tap one, or open **Ads** in the menu: pick world, a country or a region, the start hour and how many hours, write a brand and a line, **Rent** at the posted price or **Bid** against other advertisers. Prices move with how much is already rented and how many others are interested; the page shows the multiplier, the share rented and the formula. Rented spaces go on air in the scene for the viewer's place (choose where you "see the world from"). Nothing is real: the numbers are invented and the rentals live in the tab. Spec: [ads.md](../ads.md).
- **A phone app, not a squeezed website.** On a phone the scene is the whole screen and shows a few rooms of the house, following the robot. One bottom sheet (drag it, or tap the handle: peek, half, full) holds Following, Queue, Bots and Details; the Approve / Open / Discard card floats above it; the tab bar stays at the bottom; round buttons on the right reset the view and switch day, night, weather, sound and chat. Open the artifact on a phone and the device frame and prototype bar disappear.
- **Bots.** Click a robot, or open the Bots tab, to chat with it (Brush, Spark, Clapper, Gate, Post, Lens, Mirror, Sprout). Ask for its status, what needs you, to show where it works, to take you to its house, to open its page, or change the world: rain, snow, desert, fog, sun, day, night, fly (the world view). Replies are templates, so no tokens are spent.
- **A living world.** Weather (sun, rain, snow, desert, fog), drifting clouds, birds, a plane with a contrail, a lake with boats and jumping fish in the middle of the ring (visible from above), fireflies at night.
- **Approve** the amber item at the Quality Gate, then **hold** the button on the Publish step to confirm a post. Posting is a deliberate gesture on purpose.
- **Scenario** (top bar or Settings → Appearance): nine themes. Only Brazil is in the MVP and only Brazil has the painted worlds; the others show that the same format carries very different looks with plain ground, hills and trees.
- **View**: `3D with 2D art` (default when the generated characters exist), `3D with models` (procedural low-poly agents) and `2D flat (fallback)` for devices without WebGL.
- **Device** and **language** (English, Portuguese), **RTL preview**, and the collapsible side menu.
- **Demo autopilot** approves and confirms on its own so you can watch the whole loop. That switch exists only in this prototype.

## Screens

| Screen | Shot |
|---|---|
| A house, by day and night | [day](screens/factory-day.jpg) · [night](screens/factory-night.jpg) · [Portuguese](screens/factory-pt-br.jpg) |
| Seven houses, seven worlds | [montage](screens/houses.jpg) |
| The world from above (look-only) | [world](screens/factory-world.jpg) |
| Ad spaces: rent or bid, prices by place and hour | [ads](screens/factory-ads.jpg) |
| Station details and the rooms inside | [make](screens/factory-details.jpg) |
| Chatting with a bot | [desktop](screens/factory-chat.jpg) |
| Weather | [snow](screens/factory-snow.jpg) · [desert](screens/factory-desert.jpg) |
| Factory as a phone app (full-screen scene, bottom sheet) | [following](screens/factory-phone.jpg) · [world](screens/factory-phone-world.jpg) · [bots](screens/factory-phone-chat.jpg) · [details](screens/factory-phone-details.jpg) · [queue](screens/factory-phone-queue.jpg) |
| Nine themes in 3D | [montage](screens/themes-3d.jpg) |
| Login, Needs you, Brand, Ideas, Studio | [login](screens/login.jpg) · [inbox](screens/inbox.jpg) · [brand](screens/brand.jpg) · [ideas](screens/ideas.jpg) · [studio](screens/studio.jpg) |
| Review, Publish (desktop and phone) | [review](screens/review.jpg) · [publish](screens/publish.jpg) · [review phone](screens/review-phone.jpg) · [publish phone](screens/publish-phone.jpg) |
| Activity, Settings | [activity](screens/activity.jpg) · [scenarios](screens/settings-scenarios.jpg) · [limits](screens/settings-policy.jpg) |

## What it is not

- Not the product. Pages, fields and states follow the spec in [`docs/factory`](../README.md); the numbers are examples.
- Not secure or multi-user. In the product only a human session can approve a video or confirm a post.
- Not final art. The Brazil theme uses original procedural houses and props plus characters, plaza tile, heroes, video backgrounds and seven scenery paintings generated with GPT Image 2 (see [src/art/LICENSE.md](src/art/LICENSE.md)); the other eight themes are concepts.
- Not a real ad market. Prices, bids, rivals and rentals are made up and live in the page; no payment, review, delivery or counting exists. It shows the idea and the formula in [ads.md](../ads.md).

## Design notes the prototype settles

- **One system color**: light blue. Themes restyle the scene only, never the interface.
- **The factory is a digital twin**: the 3D scene is the hero, and the numbers, the followed video, the station details and the queue float over it. On a phone the scene stays on top and the same pieces stack below it.
- **One thing at a time**: one house in view, far from the others, and a separate look-only world view, so the scene never turns into a crowd and nobody can act from a place where they cannot see what they act on.
- **Zero-token motion**: speech bubbles, labels and states are catalog templates filled with ids and numbers, so the scene is alive in every language at no token cost.
- **Accessibility**: reduced motion stops pulses and camera moves; every control has a text label or `aria-label`; the 2D view is the fallback when WebGL is missing.

## URL parameters

`page` (`login`, `factory`, `inbox`, `brand`, `ideas`, `studio`, `review`, `publish`, `activity`, `ads`, `settings`), `lang` (`en`, `pt-BR`), `theme` (`br`, `us`, `cn`, `ru`, `jp`, `dragons`, `realms`, `courtyard`, `tiny`), `view` (`3d`, `3d-sprites`, `2d`), `tod` (`day`, `night`), `scheme` (`light`, `dark`), `device` (`desktop`, `phone`), `rail` (`min`), `panel` (`1`, `0`), `auto=1`, `rtl=1`, `upload=1`, `tab` (Settings tab).

`sel` (a stage: `brand`, `ideas`, `make`, `review`, `publish`, `metrics`, `report`) puts you in front of that house, `world=1` opens the world view, `snd=0` starts muted.

Handy for screenshots: `warm=14` runs the simulation for 14 seconds before the first frame, `hud=0` hides every overlay and shows the bare scene, `wx` (`clear`, `rain`, `snow`, `desert`, `fog`) sets the weather, `ptab=chat` and `bot=<role>` open a chat, `lowfx=1` lowers shadow quality for software renderers.

## Generated art

The Brazil theme's characters, plaza tile, two hero illustrations, five video backgrounds and seven scenery paintings (one per house) were generated with GPT Image 2 through Real Oficial (23 images, 0 credits: they fall inside the plan's monthly allowance). [image-brief.md](image-brief.md) holds the prompts and rules. To add or replace art, drop the raw images in `src/art/raw/`, run `python3 src/art/pack.py` and rebuild.

## Rebuild

`index.html` is generated from the files in [`src/`](src/) (CSS, markup, art, message catalogs, the 3D scene, the houses, the scenery, the sound, the ad market, the HUD and the app). After editing them run:

```bash
python3 docs/factory/prototype/src/build.py
```

## Licenses

Three.js is MIT. The fonts are open-licensed (OFL). All art in the prototype is original: houses, props and robots are generated in code; the Brazil theme's characters, plaza, heroes, video backgrounds and scenery paintings were generated with GPT Image 2 ([src/art/LICENSE.md](src/art/LICENSE.md)).
