---
name: simplicio-video
description: Use this when a Simplicio Runtime user asks for a short marketing video (Reels/Stories/Shorts, date greeting, institutional, promo) for a real business, or asks to re-render, change the voice, retime or deliver an existing one. You reason about the client facts, pick template/motion/voice/timings and write a simplicio.video-contract/v1 YAML; the deterministic `simplicio-video` CLI validates, generates the voice and renders the MP4 (local or Colab GPU) for delivery to Google Drive.
---

# simplicio-video — contrato primeiro, CLI executa

Você (LLM) **raciocina e escreve o contrato**; o CLI **executa**. Nunca edite HTML gerado, nunca invente fato do cliente, nunca acelere a voz.

## Quando usar
- Pedido de vídeo curto para um negócio real (post de data comemorativa, institucional, oferta, CTA para WhatsApp).
- Trocar a voz provisória pela final (WAVs do Gemini), mudar texto/tempo, renderizar de novo, gerar bundle para o Colab.
- **Não** use para edição de footage bruto (cortar/legendar gravações): isso é `tools/video-use/` (etapa opcional).

## Como raciocinar (antes de escrever)
1. **Fatos:** leia `clients/<slug>/coleta/` (`brief.md`, `pendencias.md`, `intake.json`). Só entra no vídeo o que tem fonte + data e não está em conflito. Sem coleta → rode o intake (`intake/questionario.md`) primeiro.
2. **Template:** `simplicio-video list templates` → escolha pelo nicho; precisa estar `renderizável`. Os ids de cena do contrato têm de ser os da composição do template (`template.json → composicao.cenas`).
3. **Motion:** `simplicio-video list motion` → use os padrões que o template prevê; `bloco` = id do placeholder `{{vars:<bloco>}}` na composição; `params` seguem `motion/patterns/<id>/pattern.json`. Uma ideia por cena; o primeiro plano vira a transição. Params string aceitam placeholders: `{{bpm}}`, `{{beat}}`, `{{dur:<cena>}}`, `{{duracao}}` e `{{words:<fala>}}` (inícios das palavras da fala, em s desde o início da cena, vindos do `timing.lock.json`: use em `kinetic-words.times`). Para vídeos rápidos: `bg-parallax` + `fx-transition` (6-10 frames) + `beat-burst` + `kinetic-words`, cenas em batidas inteiras.
4. **Voz:** pt-BR, gênero/energia do público. Provisória: `local` (Kokoro, ex. `pf_dora`/`pm_alex`). Final: Gemini no AI Studio → `file`. Sugira voz Gemini + instrução de estilo no contrato (`voz.providers.gemini`).
5. **Tempos:** leia cada fala em voz alta a ~2,5 palavras/s; `max_s` = duração natural + folga (0,2–0,5 s). `inicio_s + max_s` ≤ duração da cena (+ J-cut ≤ 0,15 s). A soma das cenas = `formato.duracao_s`. SFX com tempo relativo à cena, nas batidas (120 BPM = 0,5 s).
6. **Marca:** logo só com arquivo real (`marca.logo`); sem arquivo → `logo: null` e lockup de texto. Não mostre telefone/endereço/preço/avaliações não confirmados.
7. **Entrega:** `drive.caminho = simplicio-video/clientes/<Drive_Nome>/<ANO>/<Campanha>`, `drive.arquivo = "<CLIENTE> - <descricao> - vNN.mp4"`.

## Comandos exatos
```bash
simplicio-video --help                                    # fluxo completo
simplicio-video list templates|motion|voices
simplicio-video init <slug> <Campanha> --template <id> --nome "<Nome>" --ano 2026   # esqueleto com TODO
simplicio-video validate <contrato.yaml>                  # schema + assets + durações + falas
simplicio-video voice <contrato.yaml> [--provider file|local|gemini]   # -> timing.lock.json
simplicio-video validate <contrato.yaml> --need-lock      # antes do render
simplicio-video render <contrato.yaml>                    # local -> saida.arquivo + render.manifest.json
simplicio-video render <contrato.yaml> --backend colab    # bundle zip para colab/render.ipynb (GPU)
```
Schema: `schema/contract.schema.json`. Instalação: `pip install -e .` na raiz do repo (Python ≥ 3.10, Node ≥ 22, ffmpeg).

## Checklist de validação
- [ ] `validate` sem erro (nenhum `TODO`, drive no padrão, assets existem).
- [ ] `voice` sem fala acima de `max_s` (se estourar: encurte o texto ou aumente cena/`max_s`; **nunca** acelere).
- [ ] `render` ok; `render.manifest.json → loudness.integrated_lufs` ≈ −14 e pico ≤ −1,5.
- [ ] STT (faster-whisper) reconhece todas as falas; olhe a prévia/contact sheet.
- [ ] Copy rastreável até `coleta/` (liste no README do vídeo).
- [ ] Commit do contrato + `timing.lock.json` + `render.manifest.json` + `assets/audio/voz/` (MP4 fica em `out/`, gitignored).

## Render local × Colab
- **local:** padrão; referência de hash (mesma entrada → mesmo MP4 byte a byte).
- **colab:** `--backend colab` gera `out/<nome>.colab-bundle.zip`; abra `colab/render.ipynb` com runtime GPU, envie o zip, rode tudo; o notebook imprime tempos por etapa, GPU e compara com o render local. NVENC muda os bytes do vídeo (visualmente equivalente).

## Destino no Drive
Não faça upload sem pedido explícito do usuário. Informe o caminho do MP4 e `drive.caminho`; depois do upload, registre o link na tabela **Entregas no Drive** de `clients/<slug>/README.md` (campanha, pasta, arquivo, link, versão/status).

## Exemplo mínimo de contrato
```yaml
schema: simplicio.video-contract/v1
cliente: { slug: lothus-odontologia, nome: Lothus Odontologia, drive_nome: Lothus_Odontologia, coleta: ../coleta }
campanha: { id: Dia_Criancas, ano: 2026 }
formato: { aspect: "9:16", width: 1080, height: 1920, fps: 30, duracao_s: 15 }
template: saude-odontologia
marca: { paleta: { ink: "#3d3834" }, logo: null }
cenas:
  - id: s1
    duracao_s: 3.5
    motion:
      - { padrao: balloons-confetti, bloco: s1-balloons, params: { count: 9 } }
      - { padrao: kinetic-bounce-title, bloco: s1-title, params: { line1: "Feliz", line2: "Dia das", line3: "Crianças!" } }
    fala: { id: vo1, texto: "Feliz Dia das Crianças!", inicio_s: 0.5, max_s: 2.3 }
    sfx: [ { id: pop, t: 0.35, tipo: pop, gain_db: -6 } ]
  # s2, s3, s4 ... (ids e blocos exigidos pela composição do template)
voz:
  provider: local
  voice: pf_dora
  providers:
    file: { dir: assets/audio/vo/external }
    gemini: { voice: Sulafat, estilo: "Voz feminina brasileira, calorosa e sorridente..." }
trilha:
  bpm: 120
  seed: 20261012
  music: { style: playful, gain_db: -5, fade_in_s: 0.05, fade_out_s: 1.2, progression: [[48, [60, 64, 67]]] }
  master: { target_lufs: -14, true_peak_db: -1.5 }
saida: { arquivo: out/lothus-dia-criancas.mp4, qualidade: delivery }
drive: { caminho: simplicio-video/clientes/Lothus_Odontologia/2026/Dia_Criancas, arquivo: "Lothus - Dia das Criancas 15s - v01.mp4" }
```
Contratos completos: `clients/lothus-odontologia/video-01-dia-das-criancas/contract.yaml`, `clients/wjr-informatica-games/video-01/contract.yaml`.
