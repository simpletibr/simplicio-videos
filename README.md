# simplicio-videos

**Video plugin for Simplicio Runtime (Simplicio MCP): a deterministic video machine driven by agents.** A user asks for a video; the plugin runs a **deterministic pipeline**: intake questionnaire (with automatic site/Instagram extraction) → brief/spec → sector template → composition from the motion pattern library (HyperFrames) → TTS voice (Gemini, local, cloned voices; cached) → optional footage editing (video-use) → deterministic render. The LLM only decides things (contract, EDL) and creates new templates/patterns; it is never in the render path.

Decisions: [ADR-0001](docs/decisoes/ADR-0001-visao-plugin.md) · [ADR-0002 (CLI + contract + Colab + credits)](docs/decisoes/ADR-0002-cli-contrato-colab-creditos.md) · [ADR-0003 (100% script flow; local render by default)](docs/decisoes/ADR-0003-fluxo-100-script.md) · [ADR-0004 (generative UGC outside the deterministic render)](docs/decisoes/ADR-0004-ugc-generativo.md) · Costs: [docs/custos.md](docs/custos.md) · Outbound sales: [docs/venda-ativa.md](docs/venda-ativa.md) · Manifest: [`plugin.json`](plugin.json) · Skill: [`skills/simplicio-video/SKILL.md`](skills/simplicio-video/SKILL.md)

**Entry point: the `simplicio-video` CLI.** The agent writes the YAML contract ([`schema/contract.schema.json`](src/simplicio_video/data/schema/contract.schema.json)); the CLI validates it, generates the voice and renders deterministically (local or Colab GPU). Agents (Claude Code, Codex, Grok): start at [`AGENTS.md`](AGENTS.md).

## Apps

Every external tool is a **track** with one CLI command, one MCP verb (`plugin.json`) and one doc. Install and run them yourself; nothing is vendored. All of it is optional except HyperFrames and ffmpeg.

### Video apps

| App | License | Role | CLI command | MCP verb | Doc |
|---|---|---|---|---|---|
| [HyperFrames](https://github.com/heygen-com/hyperframes) | Apache-2.0 | Deterministic HTML/GSAP → MP4 render (core) | `simplicio-video render contract.yaml` | `video.render` | [motion/README.md](src/simplicio_video/data/motion/README.md) |
| [video-use](https://github.com/browser-use/video-use) | MIT | EDL editing of any MP4 (cuts, reorder, subtitles, review) | `simplicio-video edit setup\|transcribe\|pack\|render\|verify` | `video.edit` | [tools/video-use](tools/video-use/README.md) |
| [OpenMontage](https://github.com/calesthio/OpenMontage) | see repo | Agentic production pipelines (Backlot, Remotion, HyperFrames) | `simplicio-video montage [clone\|open\|serve\|demo]` | `video.montage` | [docs/recursos.md](docs/recursos.md) |
| [OpenCut](https://github.com/OpenCut-app/OpenCut) | MIT | Open-source editor for manual finishing (uses `opencut-classic` until the rewrite has an API) | `simplicio-video opencut clone\|dev\|where` | `video.opencut` | [docs/recursos.md](docs/recursos.md) |
| [Hypit AI](https://github.com/hypit-ai/hypit) | see repo | Clone viral videos into agent workflows | `simplicio-video clone [args]` | `video.clone` | [docs/recursos.md](docs/recursos.md) |
| [MoneyPrinterTurbo](https://github.com/harry0703/MoneyPrinterTurbo) | MIT | Topic-to-short-video generator (LLM script, synthesized voice, stock footage; Python 3.11+) | `simplicio-video moneyprinter clone\|setup\|serve\|where\|status` | `video.moneyprinter` (clone, where) | [docs/recursos.md](docs/recursos.md) |
| [Toonflow](https://github.com/HBAI-Ltd/Toonflow-app) | MIT | Open-source AI studio for short dramas, comic dramas and videos (local web app on Bun) | `simplicio-video toonflow clone\|serve\|where` | `video.toonflow` (clone, where) | [docs/recursos.md](docs/recursos.md) |

| Redes sociais sem postar (`social`) | n/a | Plano de postagem com limites por rede e receita das chamadas MCP do Real Oficial (padrão) ou do Zernio; o motor não posta | `simplicio-video social providers\|plan\|check\|recipe` | `video.social` (providers, plan, check, recipe) | [docs/recursos.md](docs/recursos.md) |
| Troca de personagem (`swap`) | n/a | Troca o personagem de um vídeo por um avatar de referência, agnóstico de fornecedor (gemini, fal, wavespeed, kie, alibaba) | `simplicio-video swap providers\|estimate\|run\|status` | `video.swap` (providers, estimate) | [docs/recursos.md](docs/recursos.md) |
| Tarefas em segundo plano (`jobs`) | n/a | `swap run` e `voice` num processo separado, sem daemon nem porta; pedaços e falas em paralelo | `simplicio-video jobs submit\|status\|list\|cancel\|result` | `video.jobs` (sem gasto) | [docs/recursos.md](docs/recursos.md) |
| Biblioteca de imagens e áudio (`openverse`) | n/a | Busca no [Openverse](https://openverse.org/), baixa com segurança, gera a folha de revisão, só exporta o que foi aprovado para o pedido e só deixa o ativo entrar no vídeo (`validate`/`render`) com procedência declarada no contrato, revisão aprovada e crédito; o render grava a procedência no manifesto e os créditos ao lado do MP4 | `simplicio-video openverse search\|get\|library list\|show\|review\|export\|credits\|verify` | `video.openverse` (search, list, show, folha, review); `video.validate` aplica o portão do contrato | [docs/recursos.md](docs/recursos.md) |

Toonflow runs from a pinned checkout, as its own program:

```bash
simplicio-video toonflow clone   # clones at the commit pinned in src/simplicio_video/tools.py
simplicio-video toonflow serve --lan   # bun install --frozen-lockfile, build, start: http://localhost:3000
```

It needs Bun (the version is in the checkout's `packageManager` field). The server has **no login** and listens on every interface (`0.0.0.0:3000`), so `serve` refuses to start without `--lan`. To keep it on your own machine, run the Docker setup from Toonflow's `compose.yaml` (publishes `127.0.0.1:3000`) or block port 3000 at the firewall. Its data goes to `~/.simplicio-video/toonflow-data` (set `TOONFLOW_DATA_DIR` to move it), outside the checkout, so a re-clone never deletes it. Model API keys are entered in Toonflow's own UI. Toonflow sits outside the deterministic render; whatever it produces enters a contract as a file with a hash.

MoneyPrinterTurbo is a support track outside the engine, like Toonflow and OpenCut: it does not replace `contract.yaml -> MP4`. It runs from a pinned checkout with its own isolated virtualenv:

```bash
simplicio-video moneyprinter clone    # clones at the commit pinned in src/simplicio_video/tools.py
simplicio-video moneyprinter setup    # venv in ~/.simplicio-video/moneyprinter-data, pip install -r requirements.txt, config.toml copied from the example (no key filled)
simplicio-video moneyprinter serve    # WebUI on http://localhost:8501; add --api for the API on http://localhost:8080/docs
simplicio-video moneyprinter status   # config.toml exists? which keys are filled (yes only, never the value)
```

It needs Python 3.11 or newer and uses ffmpeg. Upstream's API listens on `0.0.0.0` by default and neither the WebUI nor an API with an empty `app.api_key` has a login, so `serve` forces `127.0.0.1` by argument (it starts uvicorn on the same `app.asgi:app` instead of `main.py`, whose host comes from `config.toml`) and only listens on every interface with `--lan`. The generator calls third-party services with their own terms (an LLM provider, a TTS service and stock footage such as Pexels, Pixabay and Coverr) using **your own** API keys, typed in its WebUI or in `config.toml`; this command never prints them and the MCP tool never runs `setup` or `serve`. Generated videos go to `~/.simplicio-video/moneyprinter-data/storage` (set `MONEYPRINTER_DATA_DIR` to move it). Whatever it produces enters a contract as a file with a hash.

### Audio apps

| App | License | Role | Provider (`voz.provider` / `--provider`) | Setup | Doc |
|---|---|---|---|---|---|
| Gemini TTS | cloud API | Default narration | `gemini` (or `file` for AI Studio WAVs) | `GEMINI_API_KEY` | [voices/gemini.md](voices/gemini.md) |
| Kokoro-82M | Apache-2.0 | Free local draft voice (pt-BR ok) | `local` | `SIMPLICIO_TTS_PY` | [voices/local.md](voices/local.md) |
| [VoxCPM2](https://github.com/OpenBMB/VoxCPM) | Apache-2.0 | Voice design from a text description, or cloning from a short reference clip (30 languages, 48 kHz) | `voxcpm` | `pip install voxcpm`, `VOXCPM_BIN` | [voices/voxcpm.md](voices/voxcpm.md) |
| [OpenVoice V2](https://github.com/myshell-ai/OpenVoice) | MIT | Voice cloning: converts a base take (Kokoro) to the reference speaker's timbre | `openvoice` | `OPENVOICE_PY`, `OPENVOICE_CHECKPOINTS` | [voices/openvoice.md](voices/openvoice.md) |
| [VoiceStudio](https://github.com/debpalash/VoiceStudio) | AGPL-3.0 (HTTP only, never vendored) | Local ElevenLabs alternative: your cloned voice profiles through an OpenAI-compatible API | `voicestudio` | `VOICESTUDIO_URL` (default `http://localhost:3900`) | [voices/voicestudio.md](voices/voicestudio.md) |
| [Real Oficial](https://api.realoficial.com.br/mcp) | cloud MCP | Social scheduling/publishing, AI image/video, cuts (49 MCP tools, OAuth; see docs/realoficial.md) | — (MCP) | `simplicio-video realoficial config` | [docs/realoficial.md](docs/realoficial.md) |

All voice providers go through the same pipeline: raw take kept per provider → silence trim → contract ffmpeg chain → 48 kHz mono → `timing.lock.json`. A take longer than its slot is an error; audio is **never time-stretched**. Cloned voices need the **written authorization of the speaker**; see [voices/README.md](voices/README.md).

## Repository map

```
simplicio-videos/
├── AGENTS.md / CLAUDE.md   # rules + map + flows for agents (CLAUDE.md → AGENTS.md)
├── plugin.json             # simplicio.plugin/v1 — entrypoint simplicio-video (video.* verbs) + skill
├── pyproject.toml          # Python package of the CLI (src/simplicio_video/), tests in tests/
├── schema/                 # contract.schema.json (CLI contract)
├── skills/simplicio-video/ # SKILL.md for LLMs in simplicio-runtime
├── skills/simplicio-video-social/ # SKILL.md: posting to social networks with the provider's MCP tools
├── colab/                  # render.ipynb (GPU) for --backend colab bundles
├── intake/                 # questionnaire, site/IG extraction, intake.schema.json, examples/
├── templates/              # one template per sector (template.json + README)
├── motion/                 # motion pattern library: patterns/<id>/, catalog.json, lib/, scripts/
├── voices/                 # voice providers + TTS pipeline (see Audio apps)
├── tools/                  # optional pinned tools (video-use)
├── ugc/                    # generative UGC track (outside the render): pack.json, prompts/
├── schemas/                # video-spec.schema.json (simplicio.video-spec/v1)
├── docs/                   # ADRs, pipeline, setup — index in docs/README.md
└── clients/<client>/       # example videos only: <video>/contract.yaml, preview/, assets
```

### Troca de personagem (`swap`)

Troca o personagem de um vídeo existente por um avatar de referência. Cada fornecedor entra por um adaptador (`gemini`, `fal`, `wavespeed`, `kie`, `alibaba`, mais `fake` para testes); a orquestração é uma só: valida, corta em pedaços, estima, submete, espera, baixa, remonta o áudio original e emenda.

```bash
simplicio-video swap providers                                   # adaptadores, capacidades, preço (US$ e R$) e confiança
simplicio-video swap estimate --provider gemini --video in.mp4 --ref avatar.png
simplicio-video swap run --provider gemini --video in.mp4 --ref avatar.png --out out/swap.mp4 --autorizo            # dry-run: só estima
GEMINI_API_KEY=... simplicio-video swap run --provider gemini --video in.mp4 --ref avatar.png --out out/swap.mp4 --autorizo --yes --max-usd 2
simplicio-video swap status out/swap.manifest.json
```

`--autorizo` é obrigatório (você confirma ter direito sobre o vídeo e as imagens). Sem `--yes` nada é enviado; `--max-usd` aborta antes de submeter. A chave só entra pela variável de ambiente do provedor. Só o `gemini` foi conferido contra a documentação real; `fal`, `wavespeed`, `kie` e `alibaba` estão **UNVERIFIED** e pedem `--aceito-unverified` para gastar. O MCP (`video.swap`) só faz `providers` e `estimate`: gastar é só pelo terminal. Detalhes em [docs/recursos.md](docs/recursos.md).


### Paralelismo e tarefas em segundo plano

```bash
simplicio-video swap run ... --concurrency 3        # pedaços em paralelo (padrão 3; 1 = serial)
simplicio-video voice contract.yaml --provider gemini --concurrency 4   # falas em paralelo (só provedor de rede; padrão 4)
simplicio-video jobs submit voice contract.yaml --provider local         # volta na hora; roda num processo separado
simplicio-video jobs submit swap-run --provider gemini --video in.mp4 --ref avatar.png --out out/swap.mp4 --autorizo --yes
simplicio-video jobs status|list|result|cancel <id>
python scripts/bench_concurrency.py                                      # benchmark com latência simulada
```

Asyncio só entra onde há espera de rede; o render e o ffmpeg continuam seriais (CPU). A saída em paralelo é idêntica à serial. O MCP (`video.jobs`) lista, consulta, lê o resultado e cancela, e só submete `voice` com provedor local: `swap-run` se submete pelo terminal, com `--yes`. Detalhes em [docs/recursos.md](docs/recursos.md).

### Redes sociais sem postar (`social`)

O motor não posta. O módulo `social` só faz o que é local e determinístico; quem publica é o agente, com as ferramentas MCP do provedor (Real Oficial, o padrão, ou Zernio) e o sim explícito do usuário em cada postagem ([ADR-0018](docs/decisoes/ADR-0018-social-planejar-sem-postar.md), skill [`simplicio-video-social`](skills/simplicio-video-social/SKILL.md)).

```bash
simplicio-video social providers                                                     # realoficial (padrão) e zernio: ferramentas MCP, limites, lacunas, UNVERIFIED
simplicio-video social plan --video out/final.mp4 --caption-file legenda.txt --target tiktok=@conta --target youtube \
    [--at 2026-10-20T09:30 --timezone America/Sao_Paulo] [--title "..."] [--ai-generated]   # grava out/social.plan.json
simplicio-video social check out/social.plan.json                                    # o vídeo e o plano continuam iguais?
simplicio-video social recipe out/social.plan.json [--provider zernio] [--clip-id ID] # a sequência de chamadas MCP: cotar, mostrar, consentimento, publicar
```

O `plan` recusa vídeo que não existe ou que não é MP4, confere duração, proporção, tamanho, legenda, título e hashtags contra `src/simplicio_video/data/social/limits.json` (cada linha com `source_url`, `read_on` e `confidence`; só o limite de duração do YouTube Shorts foi conferido na página oficial, o resto é **UNVERIFIED** e pede `--aceito-unverified` para passar) e nunca grava chave ou token. O MCP (`video.social`) só faz `providers`, `plan`, `check` e `recipe`; não existe ação de publicar. O Real Oficial não recebe MP4 local por MCP: a receita pede o `clip_id` de um clip que já esteja lá.

### Openverse: biblioteca de imagens e áudio revisada

Banco local de imagens e áudio sob licenças abertas, buscados no [Openverse](https://openverse.org/) (API pública `api.openverse.org/v1`) para compor e melhorar os vídeos. O ponto central é a **revisão por pedido**: a revisão vale para o trio (id do ativo, sha256 do arquivo, pedido) e para a proveniência vista na hora (licença, autor, origem), porque "serve" depende do que o vídeo está pedindo naquele ponto e outro id com os mesmos bytes pode ter outro autor. O motor não chama LLM nem decide nada: gera uma folha determinística (sinais objetivos, miniatura ou espectrograma, pista textual, o que falta conferir) e grava o veredito de quem revisou (agente ou pessoa). Sem aprovação para aquele pedido, o `export` recusa, e o contrato só aceita o ativo com a procedência declarada e essa aprovação (veja "No contrato e no render" abaixo).

```bash
simplicio-video openverse search --tipo imagem --consulta "sunrise over the sea" --minimo-largura 1280 --limite 10   # licenças padrão: cc0,pdm,by
simplicio-video openverse search --tipo audio --consulta "rain" --duracao-min 20 --duracao-max 90 --json
simplicio-video openverse get 9d8abc2c-c4dd-4dce-8164-cadd775befcf                          # download seguro para a biblioteca
simplicio-video openverse library review <id> --pedido "nascer do sol para a abertura do vídeo" --folha        # sinais para o revisor VER
simplicio-video openverse library review <id> --pedido "nascer do sol para a abertura do vídeo" --aprovar --motivo "o sol aparece no centro" --por "Wesley"
simplicio-video openverse library export <id> --pedido "nascer do sol para a abertura do vídeo" --contrato clients/acme/video-01/contract.yaml
simplicio-video openverse library credits                                                    # bloco de créditos de tudo o que foi exportado
simplicio-video openverse library verify clients/acme/video-01/contract.yaml                  # confere, sem rede, os ativos do Openverse declarados no contrato
simplicio-video openverse library list|show <id>                                             # o que há na biblioteca, integridade e vereditos
```

- **Licenças.** O padrão é `cc0,pdm,by`, as seguras para uso comercial e edição. `by-sa`, `by-nc`, `by-nd` (e `by-nc-sa`, `by-nc-nd`) só entram por `--licencas` explícito, com aviso do que implicam; `nc` e `nd` nunca entram por padrão e o `export` de qualquer licença com restrição (`nc`, `nd` e `sa`) exige `--aceito-restricao`. A licença que o Openverse devolve vem das fontes (Flickr, Freesound e outras) e ele mesmo manda conferir na origem: cada item guarda a `foreign_landing_url`. **Isto não é parecer jurídico.** Item sem licença conhecida nunca é baixado; CC BY sem autor nunca é exportado.
- **Biblioteca.** Fica em `OPENVERSE_LIBRARY_DIR` (padrão `~/.simplicio-video/openverse-library`): `index.json` (`simplicio.openverse-library/v1`), `files/<sha256>.<ext>`, `cache/` (cada busca por hash da consulta, com data: repetir a busca sai do cache e funciona offline; `--atualizar` consulta de novo) e `sheets/`. Cada item guarda id do Openverse, título, autor e URL do autor, licença, versão e URL da licença, texto de atribuição, `foreign_landing_url`, provedor, tags, tipo, dimensões ou duração, data da consulta e do download, sha256 e tamanho.
- **Revisão.** `--folha` mostra, para imagem, dimensões, proporção, tamanho, formato real, nitidez (variância do Laplaciano), brilho médio e a marca de mature, e gera a miniatura; para áudio, duração, taxa de amostragem, loudness (ebur128), fração de silêncio, clipping e o espectrograma. Traz também uma pista textual (palavras do pedido que aparecem no título e nas tags; não é veredito) e o que falta conferir. `--aprovar` e `--reprovar` gravam sha256 do ativo, pedido normalizado (sem acento, minúsculas), veredito, motivo, quem revisou (`--por`) e a data; aprovar exige a folha do par antes. Aprovar para o pedido A não vale para o pedido B, e um arquivo novo (outro sha256) invalida as aprovações antigas. O último veredito do par vale.
- **Export e crédito.** `library export` copia o ativo aprovado para `--para <pasta>` ou, com `--contrato`, para `assets/openverse/` ao lado do `contract.yaml`; nunca sobrescreve um arquivo existente com bytes diferentes (mesma regra do `publish`); acrescenta título, autor, licença e URLs a `CREDITS-openverse.md` na pasta. Quando a licença tem restrição (`nc`, `nd`, `sa`), o export com `--aceito-restricao` grava esse aceite no índice (`aceito_restricao`, por ativo e pedido), que o contrato confere depois. Cole o crédito onde a licença pede (descrição da publicação ou cartão final, `marca.credito`); o render também grava os créditos do vídeo ao lado do MP4 (próxima seção).
- **No contrato e no render.** Um asset do contrato (`assets[]` ou `marca.logo`, imagem ou áudio) ganha o bloco opcional `openverse: {id, pedido}`. O fluxo completo, do pedido do vídeo ao MP4 com créditos:
  1. **Buscar:** `openverse search --tipo imagem --consulta "..."` (cacheada; títulos e tags costumam estar em inglês).
  2. **Baixar:** `openverse get <id>` (só pelo terminal; download seguro para a biblioteca).
  3. **Revisar para o pedido:** `library review <id> --pedido "<o que a cena precisa>" --folha`, olhar a miniatura ou ouvir o áudio e gravar `--aprovar` (ou `--reprovar`) com `--motivo` e `--por`.
  4. **Exportar:** `library export <id> --pedido "<o mesmo pedido>" --contrato clients/<slug>/<video>/contract.yaml` copia o aprovado para `assets/openverse/` ao lado do contrato e grava a linha de crédito em `assets/openverse/CREDITS-openverse.md` (licença com restrição pede `--aceito-restricao`, gravado no índice).
  5. **Declarar no contrato:** o arquivo copiado entra em `assets`, agora com a procedência.
  6. **Validar:** `simplicio-video validate <contrato>` (ou `library verify <contrato>`, que lista o que falta) confere tudo **sem rede e sem LLM**; `run` e `render` usam o mesmo portão.
  7. **Renderizar com créditos:** o render grava a procedência no `render.manifest.json` e os créditos ao lado do MP4.

  ```yaml
  assets:
    - arquivo: assets/openverse/hdr-sunrise-over-the-sea-3a4d41c6.jpg      # o que o export copiou
      destino: assets/client/abertura.jpg
      openverse:
        id: 9d8abc2c-c4dd-4dce-8164-cadd775befcf
        pedido: nascer do sol para a abertura do vídeo                     # o que a cena precisa (comparado normalizado)
  variaveis:
    foto_abertura: assets/client/abertura.jpg
  ```

  O `validate` recusa, cada um com mensagem clara: id que não existe na biblioteca; arquivo com sha256 diferente do da biblioteca (trocado ou alterado); sem veredito aprovado para o par exato (id, sha256, pedido, proveniência), inclusive pedido diferente do aprovado e aprovação antiga depois de autor, licença ou origem mudarem; índice inválido; licença com restrição sem o `--aceito-restricao` gravado no export; crédito ausente em `CREDITS-openverse.md`; arquivo em `assets/openverse/` **sem** o bloco `openverse` (copiar à mão não burla o portão, e qualquer asset com os mesmos bytes de um ativo da biblioteca também pede o bloco); bloco num arquivo fora de `assets/openverse/`. Um contrato sem ativo do Openverse se comporta exatamente como antes e nem abre a biblioteca. A aprovação é conferida na biblioteca desta máquina (`OPENVERSE_LIBRARY_DIR`): num computador sem ela o contrato com ativo do Openverse é recusado. O render grava em `render.manifest.json`, chave `openverse`, a procedência de cada ativo (id, sha256, licença, pedido revisado, quem aprovou, canal e data; título, autor e URLs só em campos `untrusted_*`) e `<video>.CREDITS-openverse.md` ao lado do MP4 (e da prévia), gerado do índice com as mesmas sanitizações do `export`: é o crédito do vídeo entregue e a regra de atribuição CC BY vale para ele. Os hashes dos ativos entram no hash de entrada do render (`inputs_sha256`), e a mesma entrada dá o mesmo manifesto e os mesmos créditos. **Áudio:** o portão e os créditos valem igual, mas o motor de áudio não mixa um áudio externo sozinho; só um template ou bloco que referencie o arquivo o toca. **Backend `colab` (manual):** só gera o bundle, sem manifesto nem créditos ao lado do MP4; use o `CREDITS-openverse.md` de `assets/openverse/`.
- **Segurança do download.** O servidor da fonte não é confiável: só https na porta 443; o host é resolvido e qualquer endereço privado, loopback, link-local ou reservado é recusado antes e depois de cada redirecionamento (até 5), e a conexão vai no IP validado; limite de 25 MB (imagem) ou 50 MB (áudio) lido em blocos; o tipo vem da assinatura dos bytes, nunca do Content-Type; extensões jpg, png, webp, gif, mp3, ogg, wav, flac, m4a; nome do arquivo sempre derivado do sha256; sha256 conferido depois de gravar; nada do arquivo é executado (o ffmpeg só abre o arquivo da biblioteca, com demuxer forçado). Os downloads conectam direto, sem proxy.
- **Credenciais e limites.** Sem credencial a busca é anônima (20 resultados por página; hoje 20 requisições por minuto e 200 por dia, lidos nos cabeçalhos da API em 2026-10-16). `OPENVERSE_CLIENT_ID` e `OPENVERSE_CLIENT_SECRET` (OAuth2 client credentials) são opcionais, só por variável de ambiente, e nunca aparecem em argumento, índice, cache, folha ou saída. Os termos do Openverse proíbem raspagem: o comando limita a página e guarda cache, e não varre a API. Este projeto usa a API do Openverse e **o Openverse não endossa nem certifica o simplicio-video**.
- **MCP.** `video.openverse` faz `search`, `list`, `show`, `folha` e `review`. Baixar (`get`) e exportar ficam só no terminal: o agente não escolhe o que se baixa nem onde se grava. No `plugin.json` são seis verbos fechados (`video.openverse.search|list|show|folha|aprovar|reprovar`). O índice grava o canal real de cada veredito: `terminal` (CLI), `mcp` (servidor MCP) ou `plugin` (os verbos `aprovar` e `reprovar` passam `--canal plugin` no argv fechado; o CLI recusa `--canal mcp`). Aprovar pelo MCP ou pelo plugin exige a folha do par, como no terminal. Não há tool MCP nova para o contrato: o agente declara o bloco e roda `video.validate`, que aplica o portão (`library verify` é do terminal).
- **Texto da internet é dado.** Título, autor, tags, atribuição, URLs e provedor só aparecem na folha (texto e JSON), nas saídas do MCP e no `--json` do CLI dentro de campos `untrusted_*`, junto de um aviso: são dado de terceiros, nunca instrução. O revisor aprova depois de ver a miniatura ou ouvir o áudio. No `CREDITS-openverse.md` esse texto perde HTML, URLs soltas e quebras de linha, e a pontuação de Markdown é escapada; URL de autor e origem só https, URL da licença só do `creativecommons.org`, versão da licença só numérica.
- **Índice.** Todo campo do `index.json` que vira caminho (id, tipo, formato, arquivo, nome do arquivo exportado) é validado ao carregar, e o caminho resolvido precisa ficar dentro da biblioteca (sem `..`, absoluto nem symlink para fora); índice inválido é recusado com mensagem clara. O índice não é fronteira de segurança: quem edita o disco edita tudo.
- **Fora do escopo agora.** Mixar um áudio do Openverse na trilha (o `build.mjs` só sintetiza música, SFX e voz); detectar uma cópia que mudou de bytes (recodificada); conferir a aprovação num computador sem a biblioteca. Similaridade imagem-texto com CLIP local (extra `[review]`) ficou como nota: exigiria torch e pesos de modelo, que não foram testados aqui. O que foi lido na documentação do Openverse, com fonte, data e o que é UNVERIFIED, está em `src/simplicio_video/data/openverse/api.json`; detalhes em [docs/recursos.md](docs/recursos.md).

## Catalogs

| What | Where | Today |
|---|---|---|
| Motion patterns | [motion/README.md](src/simplicio_video/data/motion/README.md) | 46 (24 ready blocks with preview, 1 lib, 2 inline, 19 proposed) |
| Sector templates | [templates/README.md](src/simplicio_video/data/templates/README.md) | 2 ready (repair/games, dentistry) + 6 skeleton |
| Voices | [voices/README.md](voices/README.md) | Gemini (default), Kokoro, VoxCPM2, OpenVoice V2, VoiceStudio |
| Intake | [intake/README.md](intake/README.md) | questionnaire, auto extraction, schema, WJR example |
| Optional tools | [tools/README.md](tools/README.md) | video-use |
| UGC (generative) | [ugc/README.md](ugc/README.md) | 10 characters + 5 prompts |
| Ad formats | `src/simplicio_video/data/formats/formats.json` | 50 formats from the Drive swipe file, with the example folder and file name (`simplicio-video formats list`, `formats prompt <id> --copia <file>`) |
| Ad angles | `src/simplicio_video/data/angles/angles.json` | 50 angles in 5 groups (`simplicio-video list angles --grupo prova`) |

## Example videos

Rendered examples only. Client facts (`coleta/`: briefs, sources, contacts, Drive links) are not kept in the repo and are gitignored.

| Example | Folder | What |
|---|---|---|
| Repair shop / games, 9:16 Reels, 20 s | [video-01](clients/wjr-informatica-games/video-01/) · [preview](clients/wjr-informatica-games/video-01/preview/) | pt-BR narration (Gemini TTS) + own music/SFX; reference for template `assistencia-tecnica-games` |
| Cutdown 11.5 s of the above | [video-02-videouse](clients/wjr-informatica-games/video-02-videouse/) · [preview](clients/wjr-informatica-games/video-02-videouse/preview/) | built with [video-use](docs/video-use-integracao.md) (EDL + HyperFrames overlay) |
| Dentistry, 9:16 post, 15 s, Children's Day | [video-01-dia-das-criancas](clients/lothus-odontologia/video-01-dia-das-criancas/) · [preview](clients/lothus-odontologia/video-01-dia-das-criancas/preview/) | reference for template `saude-odontologia` |

## Quick start (CLI)

```bash
gh repo clone simpletibr/simplicio-videos && cd simplicio-videos
pip install -e .                      # `simplicio-video` command (Python >= 3.10); render needs Node >= 22 + ffmpeg
simplicio-video --help                # flow: init -> validate -> voice -> render
cd clients/lothus-odontologia/video-01-dia-das-criancas
simplicio-video validate contract.yaml
simplicio-video voice contract.yaml   # provisional local voice (Kokoro) or --provider file|gemini|voxcpm|openvoice|voicestudio
simplicio-video render contract.yaml  # out/lothus-dia-criancas.mp4 + render.manifest.json
simplicio-video render contract.yaml --backend colab   # bundle for colab/render.ipynb (GPU)
```

Cloned voice in the contract (VoxCPM2 example):

```yaml
voz:
  provider: voxcpm
  providers:
    voxcpm:
      reference_audio: assets/audio/ref/speaker.wav   # authorized speaker, clean 10-30 s
      reference_text: "Exact transcript of the clip."  # optional: ultimate cloning
      control: "warm, slightly faster"                 # optional style
      seed: 42
```

Tests: `PYTHONPATH=src python -m pytest`. Library previews: `bash motion/scripts/preview.sh && node motion/scripts/catalog.mjs`. Legacy WJR (npm): `cd clients/wjr-informatica-games/video-01 && npm run render`.

## Documentation

Index in [`docs/README.md`](docs/README.md). Curated video/motion tools (stars and licenses): [`docs/recursos.md`](docs/recursos.md). External reference: [Skillry — viral videos made with Claude Opus 5.5](https://skillry.dev/ai-videos/opus-5-5).

Also built on [video-shotcraft](https://github.com/Vincentwei1021/video-shotcraft), [awesome-opus5-5-videos](https://github.com/yihui-dev/awesome-opus5-5-videos) (recipes distilled into `motion/`) and [motion-video-kit](https://github.com/echris6/motion-video-kit) (MIT; source of 5 `proposed` patterns).

> Language policy: new documentation, CLI help and code comments are written in English. Older docs under `docs/`, `intake/`, `templates/` and client folders are still Portuguese and are translated as they are touched.

## Host

Mapa gerado a partir do front matter de `docs/host/`. A referência da CLI, dos schemas, das tools MCP e das variáveis de ambiente fica em [`docs/reference/`](docs/reference/) (gerada com `make regen`).

<!-- BEGIN GENERATED: host -->
Gerado de `docs/host/*.md` (front matter). Não edite aqui: rode `make regen`.

- [Gate local, TDD e pouso de PRs](docs/host/gate.md): Como provar que a main está verde com um comando offline, a regra de testes primeiro, o ownership por issue e o pouso serializado sem CI.
- [Licenças das dependências](docs/host/licenses.md): Como o gate confere licenças (allowlist MIT, Apache-2.0, BSD, ISC, PSF, MPL-2.0), como adicionar uma exceção justificada, como regerar docs/licenses.md e o que ainda falta (web/).
- [Pacote de operação (install, update, doctor, setup)](docs/host/packaging.md): O que cada subcomando faz, o que o doctor checa, por que a falta de GEMINI_API_KEY é aviso e os limites até as
<!-- END GENERATED -->

