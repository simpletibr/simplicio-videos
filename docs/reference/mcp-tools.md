# Tools MCP

> Gerado por `scripts/gen_reference.py` a partir de `TOOLS` em `src/simplicio_video/mcp_server.py`. Não edite à mão: rode `make regen`.

| Tool | Descrição |
|---|---|
| `video.init` | Write a contract skeleton for <cliente> <campanha> from a sector template (fill the TODOs with coleta facts). |
| `video.validate` | Validate a contract: JSON Schema, assets, scene durations, every line fits (need_lock before render). |
| `video.voice` | Generate/cache narration (provider file\|local\|gemini) and write timing.lock.json with real durations. |
| `video.render` | Render the contract: backend local \| kaggle (GPU T4) \| colab-cli \| colab (bundle only). Returns manifest summary. |
| `video.run` | voice -> validate -> render in one call (stops at the MP4; no upload). |
| `video.list` | List templates, motion patterns, voice providers or ad angles (what = templates\|motion\|voices\|angles; angles accepts grupo). |
| `video.clone` | Clone videos using Hypit AI (https://github.com/hypit-ai/hypit). |
| `video.montage` | Agentic video production using OpenMontage (https://github.com/calesthio/OpenMontage). |
| `video.edit` | video-use EDL editing over any MP4 (setup\|transcribe\|pack\|render\|verify). |
| `video.opencut` | OpenCut editor (clone\|dev\|where) for manual finishing (https://github.com/OpenCut-app/OpenCut). |
| `video.formats` | Library of 50 ad formats from the Drive swipe file: list (objetivo), show (id), prompt (id + copia) to adapt a copy to a format. |
| `video.swap` | Character swap, read-only: providers (adapters, capabilities, price, confidence) and estimate (cost before spending). Never runs a paid swap; run is terminal-only. |
| `video.social` | Social, local and read-only: providers (Real Oficial default, Zernio; their MCP tools and limits), plan (validate an MP4 against per-network limits, write social.plan.json), check (plan still matches the file) and recipe (the exact MCP call sequence for the provider: quote/preview, show the user, explicit consent, then publish). Never publishes: the agent posts with the provider's own tools after the user's explicit yes per post. |
| `video.toonflow` | Toonflow open-source AI studio for short dramas and videos: clone into the default folder, where (serve runs in the terminal with --lan) (https://github.com/HBAI-Ltd/Toonflow-app). |
| `video.moneyprinter` | MoneyPrinterTurbo topic-to-short-video generator: clone into the default folder and where only (setup and serve run in the terminal) (https://github.com/harry0703/MoneyPrinterTurbo). |
