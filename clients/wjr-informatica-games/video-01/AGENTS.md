# AGENTS.md — video-01 (WJR Infogames Reels · showreel 15 s)

Rules for any coding agent (Claude Code / Opus 5.5, Codex) working in this folder:

1. This is a HyperFrames project (HTML + GSAP → MP4). Load `/hyperframes`, `/hyperframes-core`, `/hyperframes-animation` skills before editing.
2. **Edit, don't regenerate.** `index.html` is the template. Keep `data-composition-variables` and every `data-var-*` binding: `spec.json → variables` drives the deterministic render.
3. Copy comes only from `spec.json`, `roteiro.md` and `../coleta/brief.md` (sources in `../coleta/`). Never invent prices, deadlines, warranty, ratings, customer counts or any metric.
4. Determinism: one paused timeline at `window.__timelines["main"]`; no `Math.random` (use the seeded `rng()` already in the file), no `Date.now`, network fetches, or `repeat: -1`.
5. **Audio is data, not code in the page.** Music + SFX are synthesized by `scripts/build.mjs` from `spec.json → audio` (bpm, sections, cues with `t`, `sfx`, `gain_db`, `duck_db`, `pan`). If you move a visual hit, move the matching cue `t` too (and vice versa). Keep cuts on the 120 BPM grid (0.5 s beats). Master target −14 LUFS / −1.5 dBTP.
6. Gate: `npm run lint` → `npm run check` (must pass; it runs the build first) → `npm run snapshot` (review) → `npm run render:draft`. Final: `npm run render` then `npm run loudness`.
7. Client files go in `assets/client/` (gitignored; `npm run assets:site` copies them from `../coleta/site/imagens/`). Placeholders live in `assets/placeholders/`.
8. Keep diffs small; one scene per iteration when possible (saves tokens and review time).
