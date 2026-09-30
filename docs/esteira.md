# Esteira — do pedido ao MP4 (spec como fonte única da verdade)

Decisão de produto: [ADR-0001](decisoes/ADR-0001-visao-plugin.md). Resumo: o plugin simplicio-videos do Simplicio Runtime recebe "quero um vídeo" e roda sete etapas; **só a criação de templates/padrões novos usa LLM**.

```
 pedido do usuário
      │
 1 INTAKE ──────── intake/ (questionário + extração de site/Instagram)      → clients/<c>/coleta/intake.json (+ brief.md, fontes.md, pendencias.md)
      │   aprovado ("pode seguir?")
 2 BRIEF/SPEC ──── schemas/video-spec.schema.json                            → clients/<c>/video-NN/video.json + spec.json   ◄── FONTE ÚNICA DA VERDADE
      │
 3 TEMPLATE ────── templates/<setor>/template.json (cenas, padrões, voz, música, cuidados)
      │
 4 COMPOSIÇÃO ──── motion/patterns/<id>/block.html (HyperFrames) + index.html do vídeo (RETIME)
      │
 5 VOZ ─────────── voices/ (gemini | elevenlabs | xai | local | file) → WAVs + manifest.json (cache por hash)
      │
 6 EDIÇÃO (opc.) ─ tools/video-use/ — só se o usuário pedir edição (cortar p/ X s, reordenar, aparar footage, legendas, revisão) → edl.json versionado
      │
 7 RENDER ──────── build.mjs (trilha/SFX/mix) → HyperFrames render --strict-variables → master.sh (−14 LUFS, TP ≤ −1,5)
      │
   out/video-NN.mp4 + preview 720p + contact sheet + verificação (loudness, ASR das falas, duração)
```

## O que é determinístico e o que não é

| Etapa | Determinística? | Como fica reproduzível |
|---|---|---|
| 1 Intake | não (conversa, páginas mudam) | resultado congelado em `intake.json` com fonte+data por fato |
| 2 Spec | sim, a partir do intake + template | versionado (`spec.json`, `video.json`); validado por schema |
| 3 Template | sim | arquivo versionado |
| 4 Composição | sim | blocos sem `Math.random`/`Date.now`/`fetch`; rng com semente |
| 5 Voz | **não** (TTS nuvem/neural) | passo de geração com cache: WAV tratado + manifest (hash de texto/provider/tratamento) versionados |
| 6 Footage (video-use) | a *decisão* de corte (LLM) não; a *execução* do EDL sim | o `edl.json` é versionado; `render.py` é ffmpeg puro |
| 7 Render | sim | mesmo spec + mesmos assets = mesma mixagem (md5) e mesmo vídeo |

## Quem faz o quê

- **Runtime/plugin (sem LLM):** validar intake/spec, escolher template pela tabela de nichos, instanciar blocos com `data-variable-values` a partir do spec, rodar voz (com cache), render, verificação.
- **Agente anfitrião (conversa):** conduzir o questionário, confirmar fatos e o brief com o usuário.
- **Edição (opcional):** quando o usuário pede ajuda para montar/editar, o runtime chama o op `edit` (video-use); o agente propõe a estratégia, o usuário confirma, o EDL é versionado e executado sem LLM. Sem pedido de edição, o LLM/template compõe direto no HyperFrames.
- **Opus 5.5 / autor (raro):** criar padrão novo em `motion/` ou template novo em `templates/`, sempre com preview e lint limpo.

## Estado atual (30/09/2026)

| Etapa | Estado |
|---|---|
| 1 Intake | questionário, regras de extração e schema prontos; exemplo real (WJR). Execução ainda feita pelo agente, sem comando próprio |
| 2 Spec | schema `simplicio.video-spec/v1` + `spec.json` do video-01. **Falta:** gerador intake + template → spec |
| 3 Template | 1 pronto (assistência técnica/games), 6 skeleton |
| 4 Composição | 19 blocos prontos (12 extraídos do video-01 + 7 destilados de pesquisa), 19 propostos; video-01 ainda tem a coreografia inline (fonte da extração) |
| 5 Voz | Gemini (via `file`) em produção; Chatterbox/Kokoro locais; ElevenLabs/xAI implementados e desligados (sem chave); rota API do Gemini escrita, não testada |
| 6 video-use (opcional) | ferramenta em [`tools/video-use/`](../tools/video-use/README.md) (setup fixado, quando usar × HyperFrames direto); provado no `clients/wjr-informatica-games/video-02-videouse` (cutdown 11,5 s: transcrição local formato Scribe, EDL, overlay MOV do HyperFrames, autoavaliação). Detalhes: [video-use-integracao.md](video-use-integracao.md). Falta footage real do cliente |
| 7 Render | produção no video-01 (20 s, −14 LUFS). QA extra testado (critério de "tempo congelado" do [motion-video-kit](https://github.com/echris6/motion-video-kit), `frozen-time.sh`, MIT): video-01 ≈0,5 s quase parado em 20 s, video-02 ≈0,2 s — dentro da meta (≤ ~1 s por 30 s, nenhuma pausa > 0,6 s). Ainda não é script do repo |

## Comandos da esteira hoje (por etapa)

```bash
export PATH=~/.local/node22/bin:$PATH
# 4 — biblioteca
bash motion/scripts/preview.sh && node motion/scripts/catalog.mjs
# 5 a 7 — dentro do projeto do vídeo
cd clients/<c>/video-NN
npm run voice          # usa o cache; gera só o que mudou
npm run check          # build + lint/validação HyperFrames (0 erros)
npm run render         # build → render → master
npm run loudness && npm run preview
```

Ver também: [pipeline-deterministico-gemini.md](pipeline-deterministico-gemini.md) (por que dá para ser determinístico com Gemini), [plugin-simplicio-runtime.md](plugin-simplicio-runtime.md) (proposta de plugin), [tokens-e-deterministico.md](tokens-e-deterministico.md).
