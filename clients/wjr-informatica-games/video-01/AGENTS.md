# AGENTS.md — video-01 (WJR Infogames Reels)

Rules for any coding agent (Claude Code / Opus 5.5, Codex) working in this folder:

1. This is a HyperFrames project (HTML + GSAP → MP4). Load `/hyperframes`, `/hyperframes-core`, `/hyperframes-animation` skills before editing.
2. **Edit, don't regenerate.** `index.html` is the template. Keep `data-composition-variables` and every `data-var-*` binding: `spec.json` drives the deterministic render.
3. Copy comes only from `spec.json`, `roteiro.md` and `../brief.md`. Never invent prices, deadlines, warranty, ratings, customer counts or any metric.
4. Determinism: one paused timeline at `window.__timelines["main"]`; no `Math.random`, `Date.now`, network fetches, or `repeat: -1`.
5. Gate: `npm run lint` → `npm run check` (must pass) → `npm run snapshot` (review) → `npm run render:draft`. Final: `npm run render`.
6. Client files go in `assets/client/` (gitignored). Placeholders live in `assets/placeholders/`.
7. Keep diffs small; one scene per iteration when possible (saves tokens and review time).
