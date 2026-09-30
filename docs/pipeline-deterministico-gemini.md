# Pipeline determinístico com voz Gemini — dá para fazer este tipo de vídeo 100% determinístico?

**Resposta curta: sim, com uma ressalva honesta.** O *render* (spec → MP4) já é determinístico hoje no `video-01`: mesmo `spec.json` + mesmos assets = mesma mixagem (md5 igual) e mesmo vídeo. O que **não** é determinístico é a *geração* da voz (Gemini TTS, como qualquer TTS neural na nuvem, não devolve o mesmo áudio bit a bit para o mesmo texto) e a *autoria* de padrões novos (LLM). A solução é a mesma que já usamos: **tudo que não é determinístico vira um passo de geração com cache por hash**, e o resultado versionado passa a ser entrada fixa. É exatamente a filosofia do Simplicio: o LLM (e o TTS) produzem artefatos; o runtime só executa specs.

```
   AUTORIA (não determinística, rara)            EXECUÇÃO (determinística, sempre)
   ┌──────────────────────────────┐              ┌───────────────────────────────────────────────┐
   │ Opus 5.5: novos padrões de   │  bloco novo  │ spec.json ──► build (variáveis, trilha, SFX)   │
   │ motion → biblioteca          ├─────────────►│    │         voice: cache por hash (WAVs)       │
   │ Gemini TTS: gera frase nova  ├──WAV + hash─►│    ▼                                          │
   └──────────────────────────────┘              │ HyperFrames render ──► master (−14 LUFS) ──► MP4│
                                                 └───────────────────────────────────────────────┘
```

## (a) Gemini TTS como passo do spec (API, `GEMINI_API_KEY`)

Proposta de bloco no `spec.json` (hoje o `video-01` usa `provider: "file"` com WAVs baixados do AI Studio; o script `scripts/gemini-tts.mjs` já faz a chamada de API, **ainda não testado** por falta de chave):

```json
"voice": {
  "provider": "gemini",
  "providers": { "gemini": {
    "model": "gemini-3.8-flash-tts", "voice": "Puck",
    "style": "Locutor brasileiro de propaganda de loja de games, tom animado, natural e próximo, português do Brasil, ritmo ágil sem correr.",
    "env": "GEMINI_API_KEY" } },
  "lines": [ { "id": "vo1", "text": "Seu console parou?", "t": 0.05, "max_s": 1.45 } ]
}
```

- **Chave do cache** = `sha256(provider, modelo, voz, estilo, texto falado, cadeia de tratamento)` — igual ao que `voice.py` já faz. Mesmo texto/voz/estilo = mesmo nome de arquivo = **não chama a API de novo**. Mudou uma frase → só ela é gerada.
- Os WAVs gerados + `manifest.json` são **versionados**. Quem renderiza não precisa de chave nem de rede; o render é reprodutível.
- Regerar sem mudar nada (`--force`) **pode dar áudio diferente** (duração e entonação mudam um pouco). Por isso: o cache é a fonte da verdade; regeração é um ato explícito, seguido de conferência de duração (`max_s`) e STT.
- Travas já existentes que continuam valendo: sem time-stretch (frase maior que o slot = erro), transcrição automática no manifest, `LICENSES.md` com modelo/voz/data/conta.
- Termos: o Google não reivindica o conteúdo gerado ([Gemini API Additional Terms](https://ai.google.dev/gemini-api/terms)); cota gratuita/AI Studio sem faturamento = dados podem ser usados para melhorar produtos. Para cliente, preferir projeto com faturamento.

## (b) Biblioteca de padrões de motion

**Implementada em [`motion/`](../motion/README.md)** (30/09/2026): cada padrão é um bloco HyperFrames parametrizado (`motion/patterns/<id>/block.html`, montado com `data-composition-src` + `data-variable-values`), com `pattern.json`, preview e fonte. 19 blocos prontos, 14 propostos; catálogo gerado em `motion/catalog.json`. A tabela abaixo é o inventário original tirado do `video-01/index.html` (fonte da extração):

| Padrão | Onde no video-01 | Parâmetros |
|---|---|---|
| Tipografia cinética por letra (stagger + back.out, scale-punch, RGB split) | S1, título do CTA | texto, tempo, stagger, easing, cor RGB |
| Revelação por máscara de palavras + faixa destacada | S2 | frase, trecho destacado, cor |
| Card 3D com push-in + light sweep | S2, logo | imagem, ângulo, duração |
| Revezamento de itens com contador + barra segmentada | S3 | lista, tempos (sincronizados com a fala), cor |
| Ícone que reage (controle SVG: botões, drift, LED, aquecer) | S3 | ícone, eventos por tempo |
| Título por clip-path + cascata de chips | S4 | título, lista de chips |
| HUD de mira + barra de scan + parallax de foto | S4 | foto, rótulo |
| Painéis de serviço deslizando no beat com contador 01/03 | SV | painéis, tempos |
| Ilustrações de serviço: pincel+poeira+brilho, metal líquido (gotas + mancha + shine), Hall Effect (ímã em órbita, arcos de campo, sensor, traço) | SV-A/B/C | cores, tempos, densidade (semente) |
| Linha do tempo de processo (trilho desenhado + passos) | S5 | passos |
| Drop de logo: elastic + ondas de choque + explosão de partículas + glow + shake | S6 | logo, cores, nº de partículas |
| Botão CTA com mola e "respiração" | S6 | texto, cor, tempo da palavra falada |
| Transições: glitch (fatias RGB + flash + jolt), blur, slide, push-in com riser | entre cenas | força, tempo |
| Fundo: grade em perspectiva rolando, glows derivando, partículas com semente, scanlines, vinheta | tudo | cores, semente, densidade |
| **RETIME**: coreografia numa grade base remapeada para os cortes reais (`CUTS`) + tempos absolutos `@t` para palavras | script | cortes por cena |

Receitas do **video-shotcraft** e padrões do acervo **awesome-opus5-5-videos**/bookmarks do X já foram destilados (reimplementados, com link da fonte) no catálogo de `motion/`. Regra: um padrão só vira `pronto` com lint limpo e preview renderizado.

## (c) Spec → `simplicio videos render` sem LLM

- **Execução** (plugin, determinística): `videos new` copia um template; `videos render --spec video.json` roda `build` → voz (cache) → HyperFrames (versão fixada) → master → checagens (LUFS/TP, duração, STT opcional). **Zero LLM.** Um vídeo novo do mesmo formato = só um `spec.json` novo (copy da coleta, lista de cenas/blocos, tempos, linhas de voz).
- **Autoria** (Opus 5.5, só quando precisa): criar um **padrão novo** para a biblioteca ou um template novo. O LLM nunca está no caminho do render.
- Ainda falta para chegar lá: (1) ~~extrair os blocos do `index.html` para a biblioteca~~ feito em `motion/` (o video-01 ainda usa a versão inline); (2) gerar o `index.html` a partir de uma lista de cenas no spec (hoje ele é escrito à mão/por IA); (3) um "auto-timing" que calcule `CUTS`, `t`/`max_s` e cues a partir das durações medidas da voz (hoje é manual, ~10 min); (4) o binário do plugin (`plugin.json` é stub).

## (d) Python/ffmpeg vs HyperFrames (e Remotion, plugin `motion`)

| | HyperFrames (HTML + GSAP) | Remotion (React) | Python + ffmpeg (ou MoviePy/Pillow/skia) | plugin `motion` do runtime |
|---|---|---|---|---|
| Qualidade de motion/tipografia | Alta (CSS, SVG, GSAP, fontes web) | Alta | Média; tudo vira desenho quadro a quadro | Primitivas simples (title-card, bullets, pan-zoom) |
| Determinismo | Alto (timeline pausada, seek por frame, versão fixada; Chrome headless) | Alto | Muito alto (sem navegador) | Alto |
| Velocidade | ~1 min p/ 20 s 1080p (CPU, software GL) | Parecida | Rápido para coisas simples | Rápido |
| Dependências | Node + Chrome headless + ffmpeg | Node + Chrome; **licença da empresa para uso comercial acima de certo porte** | Só Python + ffmpeg | binário do runtime |
| IA escrevendo | Excelente (skills oficiais, HTML é o que o LLM mais sabe) | Boa | Razoável | Só preenche JSON |
| Melhor uso | Anúncios/reels com motion rico (este caso) | Times React | Áudio (mix, loudnorm), montagem, legendas, conversões, checagens | Fallback sem navegador, vídeos muito simples |

Conclusão: **HyperFrames para a imagem, Python/ffmpeg para áudio e pós** (como já é: `voice.py`, `master.sh`), `storyboard.simplicio.json` como fallback no plugin `motion`. Remotion só se houver motivo (time React) e após checar a licença.

## (e) Benchmark de TTS open-source (depois) — Gemini é o padrão por enquanto

Candidatos (licença a reconferir na hora): **Chatterbox Multilingual V3** (MIT, já integrado, melhor nota local no nosso teste), **Kokoro-82M** (Apache-2.0, integrado), **Orpheus** multilíngue (Apache; conferir se ganhou pt), **Kani-TTS**, **Piper** pt_BR (cadeia de licença duvidosa), **F5-TTS pt-BR** e **Fish/OpenAudio** (hoje NC — só se mudarem a licença), **XTTS-v2** (NC). Pagos para referência: Gemini, ElevenLabs, xAI.

Critérios: (1) licença comercial clara do modelo **e** dos dados/voz; (2) naturalidade em pt-BR (teste cego com 5+ ouvintes, MOS 1–5; UTMOS só como apoio); (3) inteligibilidade (WER com faster-whisper, marcas: Xbox, PS5, WhatsApp, Hall Effect); (4) controle de estilo/energia de locutor de anúncio; (5) duração natural cabendo nos slots sem acelerar; (6) custo/tempo em CPU; (7) estabilidade entre sementes; (8) instalação reprodutível (pesos com hash). Protocolo: as 9 frases do `video-01` + 10 frases de outros nichos, mesmas condições de tratamento, planilha em `docs/`.

## Limites (honestos)

- TTS não é bit a bit reprodutível; o determinismo vem do **cache versionado**, não do modelo.
- O render depende do Chrome headless e da versão fixada do HyperFrames; trocar versão pode mudar pixels.
- Sincronia palavra-a-palavra hoje usa tempos medidos (faster-whisper) e ajuste manual; automático ainda não existe.
- Padrões novos continuam precisando de autoria (LLM ou humano) e revisão visual.
- Voz de IA em anúncio: não apresentar como humana onde os termos proíbem (ex.: xAI) e seguir a política de uso proibido do Google.
