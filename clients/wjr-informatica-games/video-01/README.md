# video-01 — WJR Infogames · Instagram Reels (9:16)

1080×1920 · 30 fps · 22 s · sem locução · HyperFrames 0.8.97 (HTML + GSAP).

| Arquivo | Para quê |
|---|---|
| `index.html` | composição; todo texto/imagem/cor é variável (`data-composition-variables` + `data-var-*`) |
| `spec.json` | valores das variáveis → render determinístico, sem LLM |
| `video.json` | spec do futuro plugin (`simplicio.video-spec/v1`, proposta) |
| `storyboard.simplicio.json` | versão para o plugin `motion` do simplicio-runtime (fallback; não validada no binário) |
| `roteiro.md` | roteiro por cena, com slots de asset |
| `PROMPT.md` | prompt para iterar com Opus 5.5 (Claude Code) ou Codex |
| `AGENTS.md` / `CLAUDE.md` | regras para o agente |
| `assets/placeholders/` | slots marcados (logo, foto 1, foto 2) |
| `assets/client/` | arquivos do cliente (gitignored; `npm run assets:site` baixa as imagens públicas do site para rascunho) |
| `assets/fonts/` | Anton + Inter (SIL OFL, licenças ao lado) |
| `preview/` | preview 540×960 (~0,5 MB) e contact sheet do render de rascunho |

## Comandos

```bash
npm run assets:site        # rascunho com imagens públicas do site
npm run check              # precisa passar (0 erros)
npm run snapshot           # frames + contact sheet em snapshots/
npm run render:draft       # out/video-01-draft.mp4
npm run render             # out/video-01.mp4 (delivery, --strict-variables)
npm run render:placeholder # sem assets do cliente
```

Verificado no box (Linux, Node 22.23.3, FFmpeg 7.1): `check` passou; `render:draft` gerou MP4 H.264 1080×1920, 30 fps, 22,0 s, 6,3 MB em ~1 min; `render` (delivery) gerou 10,8 MB em ~70 s (captura beginframe, GPU por software).

**Antes de publicar:** trocar fotos pelas reais do cliente, confirmar logo/cores, adicionar trilha licenciada e aprovar roteiro (ver `docs/checklist-cliente.md`).
