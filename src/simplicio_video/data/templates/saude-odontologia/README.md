# saude-odontologia — pronto (v2 dinâmica)

Especialização do skeleton [`saude-clinica`](../saude-clinica/) para consultórios odontológicos em datas comemorativas (Dia das Crianças, Dia do Dentista, Natal) ou institucional leve. Referência renderizada: o piloto de odontologia do Dia das Crianças 2026 (projeto de cliente, fora do pacote).

| Cena | Papel | Duração (ref., 128 BPM) | Padrões |
|---|---|---|---|
| — | fundo + abertura | vídeo inteiro | `bg-parallax` (nunca parado, zoom contínuo, pulso na batida) + `fx-transition` (flash/zoom de abertura) |
| S1 | gancho (saudação) | 6 batidas = 2,8125 s | `balloons-confetti` + `kinetic-words` + `beat-burst` |
| S2 | mensagem | 9 batidas = 4,21875 s | `tooth-character` (dança com squash & stretch na batida) + `kinetic-words` + `beat-burst` |
| S3 | dica de cuidado | 10 batidas = 4,6875 s | `toothbrush-sparkle` (squash na batida) + `kinetic-words` + `beat-burst` |
| S4 | marca | até fechar 16 s | `brand-lockup-soft` (pulso na batida) + `kinetic-words` + confete + `beat-burst` ("ta-dá") |

Cortes: `fx-transition` de 6-10 frames centrado em cada corte (zoom punch + flash, wipe de formas, whip + glitch leve), com SFX whoosh (antes) + pop + sparkle (no corte). A câmera do template dá punch-in ou whip em cada cena, zoom lento contínuo e z-punch a cada 2 batidas (shake leve no tempo forte). Durações de cena em batidas inteiras para cortes, explosões e viradas da trilha (estilo `festive` do engine, `music.fills` = tempos dos cortes) caírem juntos.

Texto na tela = a própria locução, palavra por palavra (`kinetic-words`, `times: '{{words:<fala>}}'`): os tempos vêm do `timing.lock.json`, que o `simplicio-video voice` preenche com os tempos reais das palavras do WAV (faster-whisper, mapeado para o texto do contrato). O render só lê o lock, então é determinístico.

Por que esses blocos: personagem (dente) e escova dão o assunto sem fotos do cliente; tipografia grande (Fredoka, contorno, ≤ 980 px de largura) segura a leitura em 9:16; a marca fecha com lockup de texto (o logo só entra com arquivo em alta).

Cuidados do setor (CFO, crianças, marcas de terceiros): ver `cuidados` em [`template.json`](template.json).
