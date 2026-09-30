# Setup no Mac (passo a passo)

Testado no box Linux com Node 22.23.3 + FFmpeg 7.1 + HyperFrames 0.8.97. No Mac os passos são os mesmos, trocando o gerenciador de pacotes.

## 1. Ferramentas base

```bash
# Homebrew (se ainda não tiver): https://brew.sh
brew install node ffmpeg gh          # HyperFrames exige Node >= 22
node -v                              # confira: v22.x ou maior
ffmpeg -version | head -1
```
Se o `brew install node` trouxer versão < 22: `brew install node@22 && brew link --overwrite --force node@22`.
Chrome: não precisa instalar à parte — a CLI do HyperFrames gerencia o navegador headless (`npx hyperframes doctor` mostra o que falta).

## 2. Agente: Claude Code (Opus 5.5) e/ou Codex

O template pode ser iterado com **qualquer um dos dois**. A geração criativa, por decisão atual, é com **Claude Opus 5.5**; o fluxo de código habitual (Codex GPT 5.6 Luna Xhigh + simplicio-loop) continua valendo para manutenção do repo/plugin.

```bash
# Claude Code
npm install -g @anthropic-ai/claude-code
claude            # faça login; dentro da sessão: /model → Opus 5.5 ; /effort medium

# Codex (opcional)
npm install -g @openai/codex
codex
```

## 3. Clonar o repo

```bash
gh repo clone simpletibr/simplicio-videos
cd simplicio-videos/clients/wjr-informatica-games/video-01
```

## 4. Instalar as skills

HyperFrames (base do template):
```bash
# Claude Code (plugin oficial)
claude plugin marketplace add heygen-com/hyperframes
claude plugin install hyperframes@hyperframes
# ou skills avulsas para Claude Code + Codex + outros (não interativo, só o "core set"):
npx hyperframes@0.8.97 skills update
```

video-shotcraft (opcional, para peças em Remotion com shot cards):
```bash
npx skills add Vincentwei1021/video-shotcraft
# ou manual:
git clone https://github.com/Vincentwei1021/video-shotcraft.git ~/src/video-shotcraft
ln -s ~/src/video-shotcraft ~/.claude/skills/video-shotcraft   # Claude Code
ln -s ~/src/video-shotcraft ~/.codex/skills/video-shotcraft    # Codex
```
Reinicie a sessão do agente depois de instalar skills.

## 5. Rodar o template

```bash
cd clients/wjr-informatica-games/video-01
npm run assets:site        # baixa logo/imagens PÚBLICAS do site p/ assets/client/ (só rascunho)
npm run dev                # preview/Studio no navegador
npm run check              # lint + runtime + layout + contraste (precisa passar)
npm run snapshot           # frames-chave + contact-sheet.jpg em snapshots/
npm run render:draft       # out/video-01-draft.mp4 (rápido)
npm run render             # out/video-01.mp4 (qualidade de entrega)
```
Sem assets do cliente: `npm run render:placeholder` renderiza com os slots marcados.

Quando o cliente mandar os arquivos: coloque em `assets/client/` com os mesmos nomes (ou mude os caminhos em `spec.json`) e rode `npm run render`. Nenhuma chamada de LLM é necessária para trocar texto/foto/cor.

## 6. Iterar com IA

Abra o agente dentro de `video-01/` e use o prompt de [`clients/wjr-informatica-games/video-01/PROMPT.md`](../clients/wjr-informatica-games/video-01/PROMPT.md). As regras para o agente estão em `AGENTS.md` (Codex) / `CLAUDE.md` (Claude Code).

Dica de custo: effort `medium`, uma cena por iteração, revisar pelo contact sheet antes de renderizar (ver [`tokens-e-deterministico.md`](tokens-e-deterministico.md)).
