# Modo visual B-roll (`simplicio-video broll` / `intl --visual broll`)

Re-renderiza uma prévia pronta trocando o visual por cenas reais sincronizadas palavra a palavra com a voz **já travada**
no `timing.lock.json` (nunca chama TTS). Saída: `<pasta>/preview-v2.mp4` (não mexe na `preview.mp4`).

```
<pasta>/
  contract.yaml, timing.lock.json, voz/…        # da prévia original
  assets-licencas.csv                           # arquivo, fonte, link, licenca (uma linha por asset usado + logo)
  conceito-visual.md                            # o porquê do conceito (para humanos)
  broll/concept.yaml                            # conceito visual da empresa (paleta, fontes, transições, grade, trilha, SFX)
  broll/plan.yaml                               # cenas, textos sincronizados, stickers/ícones, logo
  broll/assets/                                 # vídeos/fotos (site/IG do cliente, Mixkit/Pexels/Pixabay/Coverr)
```

Regras verificadas antes de renderizar (`simplicio-video broll <pasta> --check`):
- cenas de 0,35–1,6 s (`hold: true` até 2,6 s), cobrindo 0…duração; corte e texto grande dentro do gancho (2 s / 0,6 s);
- transições de 6–10 frames (`cut flash zoom whip glitch pop leak blur mask slide dip`);
- todo texto com `sync: voN` tem que ser o que a voz diz, na ordem; cada palavra entra no instante dela na voz;
- sem preço/SimpleTI; com `setor: saude`, sem marca registrada, promessa de resultado ou antes/depois;
- cada asset e a logo com fonte, link e licença no `assets-licencas.csv`;
- layout: tudo na área segura, palavras sem colar, sticker/logo nunca cobrindo texto, texto nunca sobre texto.

Referências de tempo: `1.25`, `end`, `end-0.5`, `vo2`, `vo2.end`, `vo2:trust`, `vo2:trust.end`, `vo2#1` (índice 0-based), com `+/-offset`.

Depois do render, `--qa` mede duração, resolução, loudness (-14 LUFS ±1, pico ≤ -1,5 dBTP), sincronia da voz por
correlação cruzada com o mix (≤ 40 ms) e o tempo de cada palavra; `--sheet` gera a folha de 20 quadros de 270 px.

Exemplos completos (dois conceitos opostos): `exemplos/pet-joy-in-la.*` (Bubble Pop) e `exemplos/novuu-medspa.*` (Quiet Luxury).
