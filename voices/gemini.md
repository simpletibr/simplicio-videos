# Tutorial — gerar a narração com a voz do Gemini (Google AI Studio)

Passo a passo para uma pessoa (sem programar) gerar as frases da narração com o **Gemini TTS** e colocá-las no vídeo. Usado no `video-01` da WJR em 30/09/2026.

## Antes de começar

- Conta Google logada (usamos a conta com Google AI Pro, `wesleybob4@gmail.com`; qualquer conta com acesso ao AI Studio funciona).
- O roteiro com as frases e o **tempo máximo de cada uma**: `clients/wjr-informatica-games/video-01/assets/audio/vo/external/README.md` (a mesma lista está em `spec.json → voice.lines`).
- Licença/termos: ver [`video-01/assets/audio/LICENSES.md`](../clients/wjr-informatica-games/video-01/assets/audio/LICENSES.md). Resumo: o Google não reivindica o áudio gerado, mas no AI Studio gratuito o texto e o áudio podem ser usados pelo Google para melhorar produtos → não cole dados pessoais/sensíveis.

## Passo a passo (AI Studio)

1. Abra **https://aistudio.google.com/generate-speech** logado na conta Google.
2. Escolha **Single-speaker audio** (um locutor).
3. Modelo: **Gemini 3.8 Flash TTS**.
4. Voz: **Puck**.
5. No campo de instrução de estilo (*Style instructions*), cole exatamente:
   > Locutor brasileiro de propaganda de loja de games, tom animado, natural e próximo, português do Brasil, ritmo ágil sem correr.
6. No campo de texto, cole **uma frase por vez** (a linha 1 primeiro). Clique em **Run / Generate** e ouça.
7. Se gostou, **baixe o WAV** (ícone de download do player).
8. Renomeie para `line-01.wav` (linha 1), `line-02.wav` (linha 2) … `line-09.wav`.
9. Repita os passos 6–8 para as 9 frases.
10. Coloque os 9 arquivos em `clients/wjr-informatica-games/video-01/assets/audio/vo/external/` (substitua os antigos).
11. No terminal, dentro de `clients/wjr-informatica-games/video-01`:
    ```bash
    npm run voice      # o spec já usa provider "file"; corta silêncio, trata a voz, confere o tempo de cada frase
    npm run render     # out/video-01.mp4 (masterizado −14 LUFS)
    npm run preview    # preview/video-01-preview-720p.mp4
    ```
    (Se o `spec.json` estiver com outro provedor: `VOICE_PROVIDER=file npm run voice`.)

## Dicas

- **Uma frase por geração**: fica mais fácil refazer só a que ficou ruim e o pipeline trata cada frase no seu tempo.
- **Pronúncia**: o Gemini costuma acertar marcas em inglês ("Xbox", "Hall Effect", "WhatsApp"). Se errar, escreva do jeito que se fala só na hora de gerar (ex.: "PS cinco", "dáblio jota erre") — o texto oficial do vídeo continua o do `spec.json`.
- **Tempo máximo**: cada frase tem um limite (coluna "Duração máx." no README da pasta `external/`). O `npm run voice` **não acelera** a voz: se passar, ele para e mostra quais frases estouraram. Aí você pode (a) gerar de novo pedindo "um pouco mais rápido" no estilo, (b) encurtar o texto, ou (c) reajustar os tempos do vídeo (abaixo).
- **Silêncio no começo/fim** não importa: o script corta.
- **Volume** não importa: o script nivela todas as frases e masteriza o vídeo.
- Anote em `LICENSES.md` se mudar modelo, voz, conta ou data.

## Reajustar os tempos (quando as frases mudam de duração)

1. `npm run voice` mostra a duração real de cada frase (`vo1 1.37s/1.45s …`).
2. Em `spec.json → voice.lines`, ajuste `t` (início) e `max_s` (limite) de cada frase — frases seguidas, com uns 0,05 s de folga.
3. Em `index.html`, ajuste a lista `CUTS` (bloco `RETIME` no script): são os cortes reais das cenas (S1, S2, S3, S4, SV-A, SV-B, SV-C, S5, S6, fim). A animação de cada cena estica/encolhe junto. Mude também os `data-start`/`data-duration` das `<section>` e os `start`/`duration` de `spec.json → clips.slots`.
4. Em `spec.json → audio`, mova os cues de efeito e as seções da música (`build` 1 s antes do CTA, `drop` no corte do CTA).
5. `npm run check && npm run render`, depois confira o `roteiro.md`.

## Rota pelo CLI (API, sem clicar): `simplicio-video voice --provider gemini`

Implementada no CLI (`src/simplicio_video/voice.py`) e testada só com mock (ainda não há chave). Precisa de `GEMINI_API_KEY` ([aistudio.google.com/apikey](https://aistudio.google.com/apikey)). O tier grátis serve, mas nele o Google usa os dados para melhorar produtos. Com billing, o custo é de ≈ US$ 0,002 por 10 s de áudio no `gemini-3.8-flash-tts` até 31/12/2026. O plano Google AI Pro **não** dá cota de API: ele vale só na interface web. Preços e limites no [ADR-0003](../docs/decisoes/ADR-0003-fluxo-100-script.md).

```yaml
voz:
  provider: gemini
  providers:
    gemini: { voice: Sulafat, estilo: "Voz feminina brasileira, calorosa e sorridente...", model: gemini-3.8-flash-tts }
    # api: generate_content   # opcional: usa /models/<model>:generateContent em vez da Interactions API (padrão)
```

```bash
export GEMINI_API_KEY=...                          # não commitar
simplicio-video voice <contrato.yaml> --provider gemini     # -> vo/external/line-NN.wav + timing.lock.json
simplicio-video run <contrato.yaml> --provider gemini       # voz + validate + render (+ --publish)
```

A fala vai **literal** no texto, o estilo vai em `speech_metadata.style` e a resposta é WAV 24 kHz. Os WAVs ficam no diretório do provider `file`, então `--provider file` reproduz a mesma voz sem rede. O cache é por hash de texto+voz+modelo+estilo: rodar de novo não chama a API (use `--force` para regerar). Em 429/5xx o CLI tenta de novo respeitando `Retry-After`. O lock registra `usage.tts_chars_this_run`.

## Rota antiga pelo script do projeto npm (WJR) — **não testada**

Precisa de uma chave da Gemini API (AI Studio → *Get API key*). **Não foi testada** nesta máquina (sem chave). Formato da chamada conferido na [documentação oficial de TTS](https://ai.google.dev/gemini-api/docs/speech-generation) em 30/09/2026: Interactions API, modelos `gemini-3.8-flash-tts` (padrão) e `gemini-3.8-flash-lite-tts` (mais barato), 30 vozes prontas (Puck = *Upbeat*, Kore = *Firm*, Charon = *Informative*, Sulafat = *Warm*, Achird = *Friendly*…) + biblioteca estendida (`GET /v1beta/voices`) + *voice design*.

```bash
export GEMINI_API_KEY=...                      # não commitar
export GEMINI_TTS_MODEL=gemini-3.8-flash-tts   # opcional (padrão)
node scripts/gemini-tts.mjs                    # gera assets/audio/vo/external/line-01..09.wav (voz Puck + o mesmo estilo)
node scripts/gemini-tts.mjs vo2 vo5            # só algumas frases
npm run voice && npm run render
```

O script (`video-01/scripts/gemini-tts.mjs`) chama `POST https://generativelanguage.googleapis.com/v1beta/interactions` com o texto da frase **literal** (o Gemini 3.8 lê o `text` ao pé da letra) e o estilo numa anotação `speech_metadata.style`, voz em `generation_config.speech_config`; a resposta unária já vem em WAV (24 kHz mono). Pela API paga (projeto com faturamento), o Google não usa os dados para treinar; pela cota gratuita, usa.

Para escolher outra voz: ouça as prontas no AI Studio (*Generate speech* → Voice) e troque `GEMINI_TTS_VOICE` (ou a voz no AI Studio) — registre a troca em `LICENSES.md`.
