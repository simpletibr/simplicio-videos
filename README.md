# simplicio-videos

**Plugin de vídeo do Simplicio Runtime (Simplicio MCP).** Quando um usuário do Simplicio pede um vídeo, o plugin roda uma **esteira determinística**: questionário de intake (com extração automática de site/Instagram) → brief/spec → template do setor → composição com a biblioteca de padrões de motion (HyperFrames) → voz TTS (Gemini, ElevenLabs, xAI ou local, com cache) → edição de footage com video-use (opcional) → render determinístico. LLM (Opus 5.5) só cria templates e padrões novos.

Decisões: [ADR-0001](docs/decisoes/ADR-0001-visao-plugin.md) · [ADR-0002 (CLI + contrato + Colab + créditos)](docs/decisoes/ADR-0002-cli-contrato-colab-creditos.md) · [ADR-0003 (fluxo 100% script; render local padrão, Colab/Kaggle opcionais)](docs/decisoes/ADR-0003-fluxo-100-script.md) · **Custos por vídeo:** [docs/custos.md](docs/custos.md) · **Venda ativa em massa:** [docs/venda-ativa.md](docs/venda-ativa.md) (`simplicio-video prospect`) · Receita: [docs/receita-video-cliente.md](docs/receita-video-cliente.md) · Manifest: [`plugin.json`](plugin.json) · Skill: [`skills/simplicio-video/SKILL.md`](skills/simplicio-video/SKILL.md)

**Entrada: o CLI `simplicio-video`.** O agente escreve o contrato YAML ([`schema/contract.schema.json`](schema/contract.schema.json)); o CLI valida, gera a voz e renderiza de forma determinística (local ou Colab GPU).

> Agentes (Claude Code, Codex, Grok): comecem por [`AGENTS.md`](AGENTS.md).

## Mapa do repositório

```
simplicio-videos/
├── AGENTS.md / CLAUDE.md   # regras + mapa + fluxos para agentes (CLAUDE.md → AGENTS.md)
├── plugin.json             # simplicio.plugin/v1 — entrypoint simplicio-video (comandos video.*) + skill
├── pyproject.toml          # pacote Python do CLI (src/simplicio_video/), testes em tests/
├── schema/                 # contract.schema.json (contrato do CLI)
├── skills/simplicio-video/ # SKILL.md para LLMs no simplicio-runtime
├── colab/                  # render.ipynb (GPU) para bundles --backend colab
├── intake/                 # 1 questionário, extração automática site/IG, intake.schema.json, exemplos/
├── templates/              # 3 um template por setor (template.json + README); schema
├── motion/                 # 4 biblioteca de padrões: patterns/<id>/{pattern.json, block.html, preview.png}, catalog.json, lib/, scripts/
├── voices/                 # 5 providers de voz (gemini, elevenlabs, xai, local) + pipeline TTS
├── tools/                  # 6 opcional: video-use (setup fixado, transcrição local, uso) — edição quando o usuário pede
├── schemas/                # 2 video-spec.schema.json (simplicio.video-spec/v1)
├── docs/                   # ADRs (decisoes/), esteira, setup, pesquisa — índice em docs/README.md
└── clients/<cliente>/      # trabalho de cliente
    ├── coleta/             #   fatos com fonte e data (brief, fontes, site salvo, cores, pendências)
    ├── <video>/contract.yaml #  vídeo pelo CLI (contrato, timing.lock.json, render.manifest.json, voz, preview/)
    └── video-NN/           #   legado: projeto HyperFrames autocontido (spec.json, index.html, scripts/, assets/, preview/)
```

## Catálogos

| O quê | Onde | Hoje |
|---|---|---|
| Padrões de motion | [motion/README.md](motion/README.md) | 46 (24 blocos prontos com preview, 1 lib, 2 inline, 19 propostos) |
| Templates por setor | [templates/README.md](templates/README.md) | 2 prontos (assistência técnica/games, odontologia) + 6 skeleton |
| Vozes | [voices/README.md](voices/README.md) | Gemini (padrão, via `file`), Chatterbox/Kokoro locais, ElevenLabs/xAI (sem chave) |
| Intake | [intake/README.md](intake/README.md) | questionário, extração automática, schema, exemplo WJR |
| Ferramentas opcionais | [tools/README.md](tools/README.md) | video-use (edição: cortar p/ X s, reordenar, aparar footage, legendas, revisão) |

## Clientes e vídeos

| Cliente | Vídeo | O que é |
|---|---|---|
| WJR Informática e Games (Guarulhos) | [coleta](clients/wjr-informatica-games/coleta/) | brief, site salvo, fontes, pendências |
| | [video-01](clients/wjr-informatica-games/video-01/) | Reels 9:16, 20 s, narração pt-BR (Gemini TTS, voz Puck) + trilha/SFX próprios · [preview](clients/wjr-informatica-games/video-01/preview/) · referência do template `assistencia-tecnica-games` |
| | [video-02-videouse](clients/wjr-informatica-games/video-02-videouse/) | Cutdown 11,5 s do video-01 montado com [video-use](docs/video-use-integracao.md) (EDL + overlay HyperFrames) · [preview](clients/wjr-informatica-games/video-02-videouse/preview/) |
| | [README + entregas no Drive](clients/wjr-informatica-games/README.md) | links dos MP4 entregues |
| Lothus Odontologia (Guarulhos) | [coleta](clients/lothus-odontologia/coleta/) · [README + Drive](clients/lothus-odontologia/README.md) | Instagram público + CNES + espelho Google Places; conflitos de endereço/telefone em pendências |
| | [video-01-dia-das-criancas](clients/lothus-odontologia/video-01-dia-das-criancas/) | Post 9:16, 15 s, Dia das Crianças, voz provisória local (final Gemini Sulafat) · [preview](clients/lothus-odontologia/video-01-dia-das-criancas/preview/) · referência do template `saude-odontologia` |

## Padrão visual v2 (B-roll) e vídeo FINAL

**Padrão oficial para todos os países** (inclusive o Brasil quando voltar): imagem real do setor sincronizada palavra a
palavra com a voz aprovada, cortes de ~0,8 s, gancho em 2 s, CTA com a logo real e conceito visual próprio por empresa.
O visual antigo (`preview.mp4` v1) está obsoleto para clientes. Spec completa: [docs/specs/visual-v2-broll.md](docs/specs/visual-v2-broll.md);
modelos e exemplos: [templates/broll/](templates/broll/README.md).

```bash
unset GEMINI_API_KEY; export SIMPLICIO_VOICE_REGEN=0      # 0 TTS: o broll nunca chama TTS nem LLM
simplicio-video broll <pasta> --check                      # conceito, plano, licenças e layout
simplicio-video broll <pasta> --qa --sheet qa/v2-<slug>.png   # prévia 540×960 com marca d'água -> preview-v2.mp4
simplicio-video broll <pasta> --final --qa                 # FINAL 1080×1920 sem marca d'água -> <pasta>/final/final.mp4
```

Regra (02/10/2026): **nenhuma prévia vai ao Wesley sem o comando do FINAL pronto e testado**, registrado em
`<pasta>/FINAL-COMANDO.md` (comando, commit, entradas, saída esperada e checagem). O final é determinístico (mesmo spec,
mesmo sha256) e fica só local até o pagamento.

## Quick start (CLI)

```bash
gh repo clone simpletibr/simplicio-videos && cd simplicio-videos
pip install -e .                      # comando simplicio-video (Python >= 3.10); render: Node >= 22 + ffmpeg
simplicio-video --help                # fluxo init -> validate -> voice -> render
cd clients/lothus-odontologia/video-01-dia-das-criancas
simplicio-video validate contract.yaml
simplicio-video voice contract.yaml   # voz provisória local (Kokoro) ou --provider file (WAVs do Gemini)
simplicio-video render contract.yaml  # out/lothus-dia-criancas.mp4 + render.manifest.json
simplicio-video render contract.yaml --backend colab   # bundle para colab/render.ipynb (GPU)
```
Testes: `python -m pytest`. Voz: [tutorial Gemini](voices/gemini.md) · [todas as opções](voices/README.md). Edição opcional: [tools/video-use](tools/video-use/README.md). Biblioteca: `bash motion/scripts/preview.sh && node motion/scripts/catalog.mjs`. Legado WJR (npm): `cd clients/wjr-informatica-games/video-01 && npm run render`.

## Documentação

Índice em [`docs/README.md`](docs/README.md). Curadoria de ferramentas de vídeo/motion (com estrelas e licenças): [`docs/recursos.md`](docs/recursos.md).

### Referências principais

- [HyperFrames](https://github.com/heygen-com/hyperframes) — render HTML/GSAP → MP4 (base do repo).
- [video-use](https://github.com/browser-use/video-use) — edição agêntica de footage (etapa 6; [avaliação](docs/video-use-integracao.md)).
- [video-shotcraft](https://github.com/Vincentwei1021/video-shotcraft) e [awesome-opus5-5-videos](https://github.com/yihui-dev/awesome-opus5-5-videos) — receitas e prompts destilados em `motion/`.
- [motion-video-kit](https://github.com/echris6/motion-video-kit) (MIT) — skill `business-motion-film` para comerciais de negócios reais: loop de crítica independente ("Gauntlet"), gramática de motion (6 regras + catálogo de mecanismos a partir de 28 launch films), barra de qualidade medida (tempo congelado, loudness, contraste, cor da marca) e scripts ffmpeg. Fonte de 5 padrões `proposto` em `motion/`.
