# Real Oficial MCP (https://api.realoficial.com.br/mcp)

Remote MCP, **OAuth 2.1 + PKCE** (login in the browser, no API key), Streamable HTTP. 49 tools as of 2026-10-06 (source: https://realoficial.com.br/mcp). Per-app API tokens are **not available yet**, so SDK-style clients that cannot do OAuth cannot connect; use an OAuth-capable client (Claude, Claude Code, Cursor, VS Code, Gemini CLI).

```bash
simplicio-video realoficial config   # JSON for mcp-remote (npx), or add the URL as a custom connector in Claude
```

Safety model: every spend or publication is two steps (estimate/preview → confirm, valid a few minutes). Reads are free. Daily credit cap per connection (default 1000, resets 21:00 BRT); max 3 projects processing at once.

## Social scheduling (what we need)

| Need | Tools | Scope |
|---|---|---|
| List connected networks, health, daily limit, options | `ro_list_social_accounts` | social:read |
| Caption + hashtags | `ro_suggest_caption` | projects:write |
| Cover | `ro_set_clip_cover` | projects:write |
| Prepare publish now / schedule / distribute over time / launcher | `ro_preview_publication` | social:publish |
| Execute: publish, schedule, edit, cancel, retry | `ro_confirm_publishing` | social:publish |
| Schedule and history, errors, public links | `ro_list_publications` | social:read |
| Automatic queues (launchers) | `ro_list_launchers`, `ro_save_launcher`, `ro_preview_launcher_change` | social:read / publish |
| Analytics, best time to post | `ro_get_social_analytics` | social:read |

Networks: TikTok, Instagram Reels, YouTube Shorts for publishing (Instagram/TikTok "limited time" per plan); connected accounts can also be Facebook, LinkedIn, Threads, Reddit, Pinterest, Bluesky. Scheduling up to 30 days ahead.

**Gap for our flow:** the MCP publishes *clips/media that live inside Real Oficial* (a clip id). There is no tool to upload an arbitrary local MP4 and schedule it. Our rendered videos reach it via `ro_import_video` only for videos already generated in Real Oficial; an upload tool (`media:write`) is not in the list. Until it exists, schedule by uploading the MP4 in the Real Oficial app, or keep our own `publish` (Drive) for delivery.

Planejar uma postagem (limites por rede, plano gravado e a receita exata de chamadas) é com `simplicio-video social` (o motor não posta; veja [ADR-0018](decisoes/ADR-0018-social-planejar-sem-postar.md)).

## Everything else

- **Cuts:** `ro_estimate_clips`, `ro_create_clips`, `ro_wait_for_clips`, `ro_list_projects`, `ro_get_project`, `ro_list_clips`, `ro_get_clip`, `ro_cut_clip`, `ro_get_auto_edit`, `ro_edit_clip`, `ro_render_clip(s)`, `ro_list_renders`.
- **Translate/dub:** `ro_list_languages`, `ro_translate_clips`, `ro_dub_clip`, `ro_list_translations_and_dubs`.
- **AI media:** `ro_list_media_models`, `ro_estimate_image`, `ro_estimate_thumbnail`, `ro_estimate_video`, `ro_confirm_spend`, `ro_list_media`, `ro_import_video`.
- **Library/housekeeping:** `ro_list_library`, `ro_save_prompt`, `ro_rename`, `ro_duplicate`, `ro_delete`, `ro_share`.
- **Lives and championships:** `ro_list_lives`, `ro_manage_live`, `ro_list_championships`, `ro_preview_championship_entry`.
- **Account and billing:** `ro_whoami`, `ro_get_account`, `ro_list_offers`, `ro_start_purchase`, `ro_get_purchase_status`.

Not found in the MCP: carousels, faceless videos, Brand Kit editing and bulk clip editing (they exist in the app).

## Rules for agents here

Never confirm a spend, publication or purchase without the user's explicit yes in chat. Render determinism is unchanged: Real Oficial media is an input asset (copy the file into the contract's assets), not part of `render`.
