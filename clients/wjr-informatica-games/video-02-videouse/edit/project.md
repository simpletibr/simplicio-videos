# project.md — memória da sessão video-use (video-02)

Formato de memória que o video-use persiste entre sessões (SKILL.md). Atualize ao fim de cada sessão.

## Sessão 1 — 30/09/2026 (BRT)

- **Pedido:** versão curta (~11,5 s) do video-01 para anúncio/Stories, montada com o video-use.
- **Fonte:** `../video-01/out/video-01.mp4` (render determinístico do video-01, 20 s, −14 LUFS). Não há footage filmado do cliente ainda.
- **Transcrição:** faster-whisper small (local) → JSON formato Scribe (`scripts/fw_to_scribe.py`), alinhado ao roteiro do `spec.json` (corrige "Se o console" e "Whole Effect"). Sem ElevenLabs.
- **Decisões de corte (EDL):**
  - [0,00–4,00] gancho + promessa — corte no fim da cena S2 (CUTS 4,0), silêncio entre "jogo." (3,70) e "Drift?" (4,02), sobre o beat.
  - [12,50–20,00] Hall Effect + "Você aprova antes do reparo" + CTA — entra no início da cena (fala começa 12,55).
  - Ficaram de fora: problemas, modelos, limpeza, metal líquido (cabem no vídeo longo).
- **Overlay:** HyperFrames `overlay/` → MOV ProRes 4444 (alpha): barra de progresso na cor primária + glitch RGB e flash de 0,2 s no corte (4,0 s). WebM **não** serve (ver README).
- **Legendas:** `master.srt` gerado pelo `build_master_srt` do video-use, **não queimado** (a composição já tem tipografia cinética); fica como legenda lateral para upload.
- **Autoavaliação:** `edit/verify/corte-4s.png`, `inicio.png`, `fim.png` (timeline_view). Corte limpo: sem estalo (fades de 30 ms), música continua, fala íntegra dos dois lados.
- **Resultado:** `out/video-02.mp4` 11,47 s de vídeo (344 quadros) · −14,0 LUFS · pico −3,1 dBFS · LRA 0,9. STT do resultado ouve as 5 falas mantidas. Duas execuções seguidas de `run.sh` deram `video-02.raw.mp4`, `master.srt` e transcrição com md5 idênticos (transcrição em cache, regra 9). Tempo quase parado ≈0,2 s (`frozen-time.sh` do motion-video-kit).
- **Pendências/observações:** o painel mostra "SERVIÇOS 03/03" sem o 01 e o 02 (herdado do video-01; aceitável no corte, trocar se o cliente estranhar). Falta 1 quadro no fim (o último quadro da fonte em 20,0 s não entra no recorte `-t 7.5`).
