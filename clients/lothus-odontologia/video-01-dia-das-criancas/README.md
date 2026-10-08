# video-01-dia-das-criancas — Lothus Odontologia

Post 9:16, 1080×1920, 30 fps, **16 s (v02 dinâmica)**, para o Dia das Crianças (12/10/2026). Referência do template [`saude-odontologia`](../../../src/simplicio_video/data/templates/saude-odontologia/) v2. Roteiro: [`roteiro.md`](roteiro.md) · fatos: `../coleta/` · licenças: [`assets/audio/LICENSES.md`](assets/audio/LICENSES.md).

## v02 dinâmica (feedback do Wesley sobre a v01)

"Precisa ser áudio mais animado" + "muito mais efeitos, bem dinâmico e dopaminérgico, transições rápidas". O que mudou:

- **Voz:** Gemini 3.8 Flash TTS, voz Laomedeia, leva **animada** (AI Studio, 30/09/2026), um pouco mais à frente na mixagem (+1,5 dB, ducking da trilha 11 dB).
- **Trilha:** estilo `festive` a 128 BPM (kick 4/4 com pump leve, palmas + caixa, pandeirola, shaker em 16avos, woodblock, baixo em oitavas, marimba, glockenspiel), virada de caixa em cada corte e "ta-dá" logo depois da última fala. Síntese determinística (semente fixa).
- **Ritmo:** cenas em batidas inteiras (6/9/10 batidas + final) → cortes, explosões e viradas caem na batida.
- **Motion (novos padrões na biblioteca):** `bg-parallax` (fundo sempre em movimento), `fx-transition` (cortes de 6-10 frames: zoom punch + flash, wipe de formas, whip + glitch leve), `beat-burst` (estrelas + confete nas batidas), `kinetic-words` (palavra a palavra no tempo real da fala). Mascote dança com squash & stretch na batida; dente da escova e lockup pulsam na batida; câmera do template com punch-in/whip, zoom contínuo e z-punch a cada 2 batidas.

| Cena | Blocos (`motion/patterns/`) | Motivo |
|---|---|---|
| — | `bg-parallax` + `fx-transition` (abertura) | Fundo nunca parado; abre com flash/zoom no primeiro frame |
| S1 | `balloons-confetti` + `kinetic-words` + `beat-burst` | Data na hora; a saudação aparece palavra a palavra junto da voz |
| S2 | `tooth-character` (dança) + `kinetic-words` + `beat-burst` | Mascote-dente acena ("Oi!") e dança na batida; sem fotos do cliente nem crianças reais |
| S3 | `toothbrush-sparkle` + `kinetic-words` + `beat-burst` | Dica de cuidado genérica (escovar), sem promessa clínica (CFO) |
| S4 | `brand-lockup-soft` + `kinetic-words` + confete + `beat-burst` | Lockup de texto: **não** recriamos o logo (só existe avatar 100×100) |

Fica **fora** do vídeo: telefone e endereço (fontes divergem), nota/avaliações, Invisalign, nome/CRO da dentista.

## Como é gerado (só pelo CLI)

A fonte única é [`contract.yaml`](contract.yaml) (`simplicio.video-contract/v1`). O CLI compila o contrato com a composição do template ([`templates/saude-odontologia/composition/`](../../../src/simplicio_video/data/templates/saude-odontologia/composition/)) e os blocos de `motion/patterns/`.

```bash
cd clients/lothus-odontologia/video-01-dia-das-criancas
simplicio-video validate contract.yaml
simplicio-video voice contract.yaml     # provider file: WAVs Gemini -> assets/audio/voz/ + timing.lock.json (com tempos por palavra)
simplicio-video render contract.yaml    # -> out/lothus-dia-criancas.mp4 + render.manifest.json
```

| Arquivo | O quê |
|---|---|
| `contract.yaml` | cenas, blocos + params (com `{{words:voN}}`, `{{bpm}}`, `{{dur:sN}}`), falas, SFX, voz, trilha, saída, destino no Drive |
| `timing.lock.json` | duração real de cada fala + tempos de cada palavra (faster-whisper), gerado por `voice` |
| `render.manifest.json` | hashes do contrato, dos inputs compilados, do vídeo/áudio decodificados, loudness e tempos |
| `assets/audio/voz/` | falas tratadas (cache versionado) |
| `assets/audio/vo/external/` | WAVs originais do Gemini (ver README da pasta) |
| `preview/` | prévia 720p + contact sheet (2 quadros/s) |

## Entrega

Drive: `simplicio-video/clientes/Lothus_Odontologia/2026/Dia_Criancas` → `Lothus - Dia das Criancas 16s - v02.mp4` (link na tabela do `README do cliente`; status: aguardando aprovação do cliente).

QA do render v02 dinâmica (30/09/2026, CLI):

- −14,0 LUFS integrado, true peak −4,1 dBFS, LRA 1,9 LU; 480 frames (16,0 s).
- faster-whisper (small) no vídeo final: as 4 falas reconhecidas ("feliz dia das crianças. Hoje é dia de brincar, sorrir e se divertir. E depois da festa, escova nesses dentinhos. Com carinho, loto zodontologia!"; "Lothus" sai como "Lótus", como pedido).
- Ritmo: nenhum trecho parado (ffmpeg `freezedetect` 1 %, 0,5 s); picos de movimento em 2,80 / 6,93–7,20 / 11,60–11,87 s = cortes na batida (2,8125 / 7,03125 / 11,71875 s).
- Determinismo: dois renders seguidos com o mesmo sha256 do MP4 (`eb4c4d5ac999…`), frames e áudio idênticos.

v01 (15 s, voz provisória Kokoro) e a prévia intermediária com a leva calma da Laomedeia foram substituídas.
