# Spec: padrão visual v2 (B-roll sincronizado) + vídeo FINAL

> **Padrão OFICIAL para todos os vídeos de clientes e prospects, de qualquer país, inclusive o Brasil quando voltar**
> (decisão do Wesley, 02/10/2026, depois de aprovar os pilotos P061 Nōvuu e P063 Pet Joy).
> O visual antigo (só texto e animação sobre fundo, `preview.mp4` v1) está **obsoleto para clientes**.
> Regra de 02/10/2026 (10:42 BRT): **nenhuma prévia vai ao Wesley sem o comando do vídeo FINAL pronto e testado** (seção 7).

Código: `src/simplicio_video/broll.py` (plano, QA, render), `broll_fx.py` (transições, overlays, tipografia),
`broll_audio.py` (trilha e SFX sintetizados, mix, loudness), CLI `simplicio-video broll`. Testes: `tests/test_broll.py`.
Modelos: `templates/broll/` (README + `exemplos/` com os dois pilotos aprovados).

## 1. O padrão (o que todo vídeo v2 precisa ter)

1. **Imagem real do setor em cada fala**, sincronizada com a voz: foto/vídeo do próprio cliente (site/Instagram) ou B-roll
   com licença comercial (Mixkit, Pixabay, Pexels, Coverr). Cada cena mostra **exatamente** o que a fala diz.
2. **Cortes de ~0,8 s** (0,5–1,5 s; o motor aceita 0,35–1,6 s e `hold` até 2,6 s só no fim), transições de 6–10 frames,
   **nada parado mais de 0,5 s** (fotos sempre com zoom/pan).
3. **Gancho nos 2 primeiros segundos**: corte + texto grande antes de 0,6 s.
4. **CTA com a logo real** do cliente (nunca logo gerado/recriado), do início da última fala até o fim.
5. **Conceito visual próprio por empresa** (paleta da marca, fonte, ritmo, transições, overlays, gancho, trilha). Nunca
   template único: nenhum conceito repete o de outra empresa do lote.
6. **Áudio aprovado reaproveitado**: as falas do `timing.lock.json`. **Zero TTS novo** (o `broll` nunca chama TTS nem LLM).
7. **Prévia 540×960 com marca d'água** no idioma do vídeo + end card "Video by Wesley Simplicio · @wesleysimplicio".
8. **Regras de conteúdo e guardas**: sem preço, sem SimpleTI; com `setor: saude`, sem antes/depois, agulha, promessa de
   resultado ou marca registrada; texto na tela = o que a voz diz.
9. **Vídeo FINAL do mesmo spec** (1080×1920, sem marca d'água) com comando pronto e testado antes da prévia ir ao Wesley.

## 2. Pasta da empresa

```
previas/<slug>/
  contract.yaml, roteiro.md, falas.csv          # roteiro aprovado (formato.duracao_s, voz.idioma)
  timing.lock.json                              # falas, início e palavras com tempo (fits: true) -> fonte da verdade do áudio
  assets/audio/voz/vo*.wav                      # takes de voz aprovados (o lock aponta para eles)
  conceito-visual.md                            # o porquê do conceito, para humanos
  assets-licencas.csv                           # arquivo, tipo, fonte, link, licenca, descricao, baixado_em (1 linha por asset + logo)
  broll/concept.yaml                            # conceito visual (seção 3)
  broll/plan.yaml                               # cenas, textos, stickers, logo (seção 4)
  broll/assets/                                 # mídia usada (mixkit-<id>.mp4, pixabay-<id>.mp4, cli-<arquivo>, logo-<slug>.*)
  broll/out/                                    # trabalho da prévia (layout, mix, qa-broll.json)
  broll/out-final/                              # trabalho do final (idem, 1080×1920)
  preview.mp4                                   # v1 (antigo; nunca sobrescrever)
  preview-v2.mp4 (+ .manifest.json)             # prévia v2
  final/final.mp4 (+ final.manifest.json)       # FINAL (só local; não vai ao Drive nem a cliente antes do pagamento)
  FINAL-COMANDO.md                              # comando do final, testado (seção 7.3)
  drive-pacote/                                 # pacote para o Drive (seção 8)
```

## 3. `broll/concept.yaml`

| Bloco | Campos | Observação |
|---|---|---|
| `nome` | texto | "Empresa · Nome do conceito" |
| `palette` | `primary`, `secondary`, `accent`, `ink`, `light` (**obrigatórios**, `#rrggbb`) + chaves extras livres | cores da logo/site; os outros campos citam cores pelo nome da chave |
| `type` | `font`, `variation` (nome da instância da fonte variável), `size` (fração da largura), `case` (`upper`/`none`), `tracking`, `anim` (`pop rise slam drop type fade`), `fill`, `emph`, `stroke`, `stroke_w`, `shadow`, `shadow_alpha`, `shadow_blur`, `shadow_dy`, `panel` (`pill bar box none`), `panel_colors[]`, `panel_alpha`, `line_gap`, `word_gap`, `scrim` | fontes OFL versionadas em `motion/assets/fonts/broll/` |
| `type.fonts` | `{chave: {font, variation, case, tracking, size, fill, emph}}` | `emph` = fonte das palavras enfatizadas (`size` relativo a `type.size`; `case`, `tracking` e `fill` próprios, ex.: script com `case: none` sob base `upper`); `cta` = fonte do @ final; outras chaves via `texts[].font` |
| `transitions` | `default[]` (ciclo), `frames` (6–10), `flash`, `leak` | `cut flash zoom whip glitch pop leak blur mask slide dip iris stripes push spin split` |
| `grade` | `sat`, `contrast`, `warmth`, `lift`, `vignette`, `tint`, `tint_amt` | cor do conceito |
| `overlays` | `particles` (string ou lista: `bubbles leak sparkles confetti steam film rays frame`), `density`, `grain`, `leak_strength`, `steam_strength`, `rays_strength`, `colors[]` (chaves da paleta), `emoji_font` | `emoji_font` obrigatório se houver sticker emoji (`motion/assets/fonts/broll/NotoColorEmoji.ttf`) |
| `music` | `style` (`bouncy elegant disco lofi samba bossa house cinematic hiphop tropical acoustic forro`), `bpm`, `db`, `duck_db`, `drop_at` (ref. de tempo), `seed` | trilha sintetizada pelo motor (sem amostras de terceiros) |
| `sfx` | `cut` (string ou `{tipo_de_transição: som, default: som}`), `sticker`, `card`, `hook`, `logo`, `db` | sons: `whoosh swish pop tick shimmer impact clink sizzle snap thud` |
| `logo` | `plate` (`round arch none`), `plate_color`, `size`, `anim` (`pop reveal`) | logo branca → placa escura; logo preta → placa clara |
| `setor` | `saude` ou vazio | `saude` liga as guardas de saúde |

## 4. `broll/plan.yaml`

- `shots[]` (em ordem; o último vai até o fim): `src` (relativo a `broll/assets/`), `until` **ou** `dur`, `in` (s no clipe),
  `crop`, `cy`, `zoom: [a, b]`, `pan: [[x0,y0],[x1,y1]]`, `speed`, `tx` (transição de entrada), `tx_frames`, `hold`, `flip`,
  `dim`, `blur`, `note` (o que a cena mostra e qual fala cobre: obrigatório na prática, vai para o manifest).
- `texts[]`: `text` (`/` quebra linha), `sync: voN` (cada palavra entra no início dela na voz; erro se não estiver na fala),
  `at`, `until`, `y`, `size`, `font`, `case`, `anim`, `panel`, `emph[]` (palavras sem pontuação), `colors[]`.
  Legendas na mesma faixa se substituem (`handoff`). O @ final vai sem `sync`, com `at` e `font: cta`.
- `stickers[]`: `emoji` | `icon` (`paw heart sparkle bubble phone chat check drop leaf`) | `image` (arte do cliente em
  `broll/assets/`, com linha no csv), `at`, `until`, `x`, `y`, `size`, `color`, `anim` (`pop float spin burst`), `count`.
- `logo`: `file`, `at`, `until`, `y`, `size`, `plate`, `plate_color`, `anim`.
- `sfx[]` extras: `{at, kind, db}`. `hook: {kind: ...}` descreve o gancho (documental).
- **Referências de tempo**: `1.25`, `end`, `end-0.5`, `vo2`, `vo2.end`, `vo2:palavra`, `vo2:palavra.end`, `vo2#1` (índice
  0-based), com `+/-offset`. Pontuação colada à palavra é ignorada (`vo2:here.` = `vo2:here`).

## 5. Comandos (box; reproduzíveis por qualquer agente)

```bash
unset GEMINI_API_KEY; export SIMPLICIO_VOICE_REGEN=0 PATH=$HOME/.local/node22/bin:$PATH   # garante 0 TTS
cd /workspace/simplicio-videos && git branch --show-current                                 # feat/visual-broll (até o merge)
P=/workspace/prospects-int1/previas/<slug>; R=/workspace/prospects-int1                    # ou prospects-int2br

simplicio-video broll $P --check                                   # valida conceito, plano, licenças e layout (segundos)
simplicio-video broll $P --qa --sheet $R/qa/v2-<slug>.png          # prévia: preview-v2.mp4 + QA + folha de 20 quadros
simplicio-video broll $P --final --qa                              # FINAL: final/final.mp4 1080×1920 + QA final
simplicio-video intl fichas --out previas --visual broll --only <slug>   # mesmo render da prévia pelo fluxo intl
```

Tempos medidos no box (8 vCPU): prévia 2–4 min; final 1080×1920 ~7–8 min (mais quando há outros renders).

## 6. Critérios de QA

**Automático (`--qa`, grava `broll/out*/qa-broll.json`; `ok: true` obrigatório):**
- duração 15–25 s; resolução 540×960 (prévia) ou 1080×1920 (final);
- loudness −14 LUFS ±1 e pico ≤ −1,5 dBTP;
- sincronia de cada take no mix ≤ 40 ms (correlação ≥ 0,3) e cada palavra na tela no instante da voz (±1 frame);
- regras do plano (duração das cenas, gancho, logo até o fim, licenças, saúde, preço) e layout sem problemas;
- **só no final**: `sem_marca_dagua: true` (quadros do final comparados com o render limpo `broll-full.mp4`: < 1% de pixels
  diferentes e cantos limpos; uma prévia com marca dá 4% e 52% nos cantos e reprova).

**Visual (folha `qa/v2-<slug>.png` + vídeo, por humano):** imagem certa em cada fala; gancho forte em 2 s; nada parado
> 0,5 s (`/workspace/controle/scripts/qa_v2.sh` ou `motion_check.py`); texto legível sem sobreposição; CTA com a logo real;
conceito diferente das outras empresas; prefira fotos sem texto por cima (capas de Reels trazem texto do cliente).

## 7. Vídeo FINAL (`--final`)

### 7.1 O que muda em relação à prévia
| | Prévia (`preview-v2.mp4`) | Final (`final/final.mp4`) |
|---|---|---|
| Resolução | 540×960, crf 30, AAC 96k | **1080×1920**, crf 18, AAC 192k |
| Marca d'água/selos | diagonais + selos "PREVIEW · @wesleysimplicio" | **nenhum** |
| End card | crédito + "Low-resolution preview" | só o crédito "Video by Wesley Simplicio · @wesleysimplicio" (`--sem-cartao` remove) |
| Entrada | concept + plan + timing.lock + vozes + assets | **os mesmos** (mesmo spec, mesma semente) |
| Trabalho | `broll/out/` | `broll/out-final/` (não toca na prévia) |

Determinístico: mesma entrada → mesmo `sha256` (teste `test_final_render_is_clean_full_res_and_deterministic`).
Zero LLM e zero TTS (`tts_calls: 0`, `llm_calls: 0` no manifest). B-roll de 720p é ampliado para 1080: para entrega paga,
troque por 1080p/4K do mesmo clipe quando existir (mesmo `in`), sem mudar o plano.

### 7.2 Checagem de sucesso
```bash
F=$P/final/final.mp4
ffprobe -v error -select_streams v:0 -show_entries stream=width,height -of csv=p=0 $F          # 1080,1920
ffprobe -v error -show_entries format=duration -of csv=p=0 $F                                   # spec + 2,5 s de end card
python3 -c "import json;q=json.load(open('$P/broll/out-final/qa-broll.json'));print(q['ok'],q['lufs'],q['tp'],q['sync_max_ms'],q['sem_marca_dagua'])"
```
Opcional (box): OCR do final procurando "preview"/"prévia" com `/home/box/.local/share/clipenv/bin/python
/workspace/broll-src/ocr_final.py $F` (deve imprimir `OCR: nenhum texto de prévia`).

### 7.3 `FINAL-COMANDO.md` (um por empresa, na pasta da prévia)
Modelo (o gerador do box é `/workspace/broll-src/final_doc.py <pasta>`):
```markdown
# FINAL-COMANDO — P0xx <Empresa> (<slug>)
- Repo: /workspace/simplicio-videos · branch feat/visual-broll · commit <hash> (ou posterior)
- Entrada (pasta): <pasta absoluta>
- Arquivos necessários: contract.yaml, timing.lock.json, assets/audio/voz/*.wav, broll/concept.yaml, broll/plan.yaml,
  broll/assets/* (N arquivos), assets-licencas.csv
## Comando (copiar e colar)
unset GEMINI_API_KEY; export SIMPLICIO_VOICE_REGEN=0 PATH=$HOME/.local/node22/bin:$PATH
cd /workspace/simplicio-videos && /home/box/.local/bin/simplicio-video broll <pasta> --final --qa
## Saída esperada
<pasta>/final/final.mp4 · 1080×1920 · <dur> s (spec <d> s + 2,5 s de crédito) · H.264 + AAC 48 kHz
## Checagem de sucesso
(ffprobe de resolução e duração, qa-broll.json com ok/lufs/sem_marca_dagua, OCR opcional)
## Último teste
<data/hora BRT> · QA ok · −14,x LUFS · pico · sync · sem marca d'água · sha256
```

## 8. Pacote e estrutura no Drive

- Pacote local por empresa em `<pasta>/drive-pacote/`: `FINAL-COMANDO.md`; `spec/` (roteiro.md, falas.csv,
  conceito-visual.md, concept.yaml, plan.yaml, assets-licencas.csv, contract.yaml, timing.lock.json); `audio/` (takes de
  voz `vo*.wav` + mixagem final da prévia `broll-master.wav`); `preview-v2.mp4`. O `final.mp4` **não** entra.
- Drive: `simplicio-video/prospects/2026/<INT-...>/<PAÍS>/P0xx-<slug>/` (ex.: `prospects/2026/INT-1/EUA/P061-novuu-medspa/`).
  Quando o cliente paga, a pasta da empresa vai para `simplicio-video/clientes/<PAÍS>/...` com o final HD.
- Só sobe depois do OK do Chefe/Wesley para aquele lote; nunca apagar nada no Drive.

## 9. O que NÃO fazer
- TTS novo (o áudio aprovado é o do `timing.lock.json`); LLM por vídeo.
- Sobrescrever `preview.mp4` (v1) ou um `preview-v2.mp4` já aprovado sem versão nova.
- Subir ao Drive sem revisão do Wesley/Chefe, ou mandar qualquer coisa a cliente (prévia, final, link).
- Usar logo gerado, preço, SimpleTI, antes/depois de saúde, promessa de resultado ou marca registrada.
- Repetir o conceito visual de outra empresa.
