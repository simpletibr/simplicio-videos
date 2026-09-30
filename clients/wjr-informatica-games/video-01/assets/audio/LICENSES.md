# Licenças de áudio — video-01

| Arquivo | Origem | Licença / uso comercial |
|---|---|---|
| `assets/audio/build/mix.wav` (gerado, não versionado) | **Síntese procedural própria** em `scripts/build.mjs`: trilha original 120 BPM (kick, clap, hats, baixo, plucks, pad em Lá menor, progressão Am–F–C–G) + efeitos (whoosh, impact, hit, click, blip, riser, glitch), tudo gerado por código a partir de osciladores, ruído com semente fixa e filtros biquad | Sem material de terceiros → nenhuma licença externa a cumprir. Obra original deste repositório; pode ser usada comercialmente nos vídeos do cliente. |

- Nenhum sample, loop, preset ou trecho de música de terceiros foi usado (nem Pixabay, nem Freesound, nem YouTube Audio Library).
- Determinístico: mesma `spec.json` ⇒ mesmo WAV (PRNG `mulberry32` com `audio.seed`). Normalização final com `ffmpeg loudnorm` 2 passagens (alvo −14 LUFS integrado, true peak −1,5 dBTP).
- Se no futuro entrar trilha/efeito de terceiros, registrar aqui: arquivo · URL · autor · licença (CC0 / CC-BY com crédito / Pixabay Content License) · data do download · crédito exigido.
- Observação sobre Instagram: áudio original costuma ser aceito sem bloqueio; mesmo assim, quem publica pode optar por trocar pela biblioteca do Instagram na hora de postar.
