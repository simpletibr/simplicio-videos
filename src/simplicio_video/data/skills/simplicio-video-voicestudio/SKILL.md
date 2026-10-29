---
name: simplicio-video-voicestudio
description: Use for local voice work with the simplicio-video CLI and the VoiceStudio app on 127.0.0.1:3900: check the app, list voices and languages, make speech from text with a cloned or designed voice, transcribe audio, clone a voice from a reference clip, or design a voice from a description. Only with the speaker's documented consent for cloning. Deterministic CLI calls; the model runs inside the VoiceStudio app.
---

# simplicio-video voicestudio — voz local por comando

`simplicio-video voicestudio` fala com o app VoiceStudio que roda na sua máquina (API local em `http://127.0.0.1:3900`). O CLI não importa o app: ele só faz chamadas HTTP locais com tempo limite. Se o app não estiver aberto, o comando diz isso e para.

## Antes de clonar uma voz

- **Consentimento é obrigatório.** Clone só a voz de quem autorizou por escrito e guarde a autorização com o projeto. O CLI não verifica isso por você.
- Clone com uma referência limpa: uma só voz, 5 a 30 segundos, sem música por cima. Gere a referência com `simplicio-video media audio FONTE -o ref.wav` e corte o trecho que você quer.

## Subcomandos

| Subcomando | Faz | Exemplo |
|---|---|---|
| `status` | saúde do app e GPU | `simplicio-video voicestudio status` |
| `voices` | perfis de voz salvos | `simplicio-video voicestudio voices --json` |
| `languages` | idiomas de TTS disponíveis | `simplicio-video voicestudio languages` |
| `personalities` | presets de personalidade | `simplicio-video voicestudio personalities` |
| `tts` | texto vira áudio com um perfil | `simplicio-video voicestudio tts "Olá" -o ola.wav --profile <id> --language pl` |
| `transcribe` | áudio vira texto | `simplicio-video voicestudio transcribe ref.wav --language pt --json` |
| `clone` | cria perfil a partir de referência | `simplicio-video voicestudio clone ref.wav --name "Vera" --language pt --ref-text "..."` |
| `describe` | mostra como uma descrição vira atributos (não salva) | `simplicio-video voicestudio describe "mulher, voz calma, sotaque paulista"` |
| `design` | cria perfil a partir de descrição | `simplicio-video voicestudio design "mulher adulta, voz calma" --name "Narradora" --language pt` |
| `mcp` | bloco de config MCP para um cliente | `simplicio-video voicestudio mcp` |

`--json` imprime o resultado para outro programa. `--format wav|ogg|opus` em `tts`.

## Fluxo: dublagem em outro idioma com a voz de um creator

```bash
# 0. confirme o app e o idioma
simplicio-video voicestudio status
simplicio-video voicestudio languages | grep -i pl

# 1. perfil com a voz autorizada (uma vez)
simplicio-video media audio reel.mp4 -o ref.wav --rate 16000
simplicio-video voicestudio clone ref.wav --name "Vera" --language pt --ref-text "texto exato da referência"

# 2. um clipe por cue em polonês (cues.json tem o campo "text" já traduzido)
for i in 0 1 2; do
  simplicio-video voicestudio tts "$(jq -r ".cues[$i].text" cues.json)" -o clips/$i.wav --profile <id> --language pl
done

# 3. encaixar nos tempos e trocar a trilha (ver skill simplicio-video-media)
simplicio-video media voice-track cues.json -o voice.wav --duration 58.2
simplicio-video media replace-audio clean.mp4 voice.wav -o dubbed.mp4
```

Antes de gerar tudo, teste um cue só. Se o idioma não aparecer em `languages`, o motor não fala aquele idioma: não force.

## Regras

- Nunca grave o áudio de uma pessoa sem consentimento; registre quem autorizou e quando.
- Não exponha o app: ele escuta só em loopback. O CLI não aceita endereço remoto.
- O resultado de `describe` não é salvo. Só `design` e `clone` criam perfil.
- A licença do modelo de voz é separada da licença do app (ver `LICENSE-NOTICE.md` do VoiceStudio).
