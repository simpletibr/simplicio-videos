# colab/ — render no Google Colab (notebook manual ou Colab CLI)

**Sem navegador:** `simplicio-video render <contrato> --backend colab-cli` usa o [Colab CLI oficial](https://github.com/googlecolab/google-colab-cli) (`pip install google-colab-cli`, login OAuth único colando o código): `colab new --gpu T4` → upload do bundle + `engine/remote_render.py` → `exec` → download de `final.mp4`/`timings.json` → `stop` (sempre). Kaggle: `--backend kaggle`. Ver [ADR-0003](../docs/decisoes/ADR-0003-fluxo-100-script.md).

**Velocidade (medido, WJR 600 frames):** Colab T4 grátis = 459,7 s de render contra 76,5 s no box local. A captura do HTML pelo Chrome headless é CPU; o Colab grátis tem 2 vCPU, e o HyperFrames usa `núcleos − 2` workers (mínimo 1). A GPU só acelera o encode (NVENC).

`render.ipynb` renderiza um **bundle** gerado pelo CLI e imprime os tempos por etapa (setup, frames, encode, master) e a GPU usada.

```bash
simplicio-video render clients/wjr-informatica-games/video-01/contract.yaml --backend colab
# -> clients/wjr-informatica-games/video-01/out/wjr-video-01-cli.colab-bundle.zip (gitignored, ~15 MB)
```

1. Abra `colab/render.ipynb` no Colab (Arquivo → Fazer upload de notebook, ou GitHub → `simpletibr/simplicio-videos`, repositório privado).
2. Ambiente de execução → GPU (T4 gratuita basta) → rode as células na ordem.
3. Bundle: envie o `.colab-bundle.zip` na célula 4 **ou** rode a célula 3 (opcional), que monta o Drive e usa
   `BUNDLE = "/content/drive/MyDrive/simplicio-video/colab/<bundle>.zip"` (troque `<bundle>` pelo nome; com um único zip na pasta, ele é escolhido sozinho; uma pasta também vale, pega o zip mais recente).
4. A célula 6 mostra `setup_s`, `frames_capture_s`, `encode_s`, `master_s`, `total_s`, a GPU, o Chrome e se frames/áudio batem com o render local (`bundle.json → reference_local`).

**Setup (célula 2):** detecta o SO (`/etc/os-release`), instala Node 22 só se faltar, pula o ffmpeg se a imagem já tiver, e instala o
**chrome-headless-shell fixado pelo HyperFrames 0.8.97** (`CHROME_VERSION`, lido do pacote) no cache do próprio HyperFrames
(`~/.cache/hyperframes/chrome`) com `npx @puppeteer/browsers install ... --install-deps`, que roda `apt-get satisfy` com o `deb.deps`
do Chrome (alternativas como `libasound2` | `libasound2t64` resolvidas pelo apt). Se isso falhar, instala lib por lib com fallback
(`libasound2t64 | libasound2`, `libgtk-3-0t64 | libgtk-3-0`...; no Ubuntu 24.04+ prefere `*t64`), confere `ldd` do Chrome e, se ainda faltar
algo, para com a lista de `.so` ausentes. Nenhum erro é escondido: `sh()` mostra exit code, stdout e stderr reais; `apt-get update` com
repositório de terceiros quebrado vira aviso. O render usa exatamente esse Chrome (`HYPERFRAMES_BROWSER_PATH`).

O bundle é a composição já compilada (index.html, blocos, fontes, assets, VO tratada, trilha mixada `mix.wav`, `build/variables.json`) + `render_bundle.sh` (HyperFrames fixado; `--gpu` quando o NVENC passa num encode de teste, `SV_GPU_ENCODE=0` desliga; Chrome em raster de software, `--no-browser-gpu`, para manter os pixels do local; `SV_WORKERS=N` força workers) + `scripts/master.sh`. O zip é reprodutível (timestamps fixos): mesmo contrato → mesmo sha256.

**Determinismo:** com o **mesmo ffmpeg** e encode por CPU, o bundle reproduz os bytes do render local (testado com o bundle mini, sha256 do MP4 igual). No Colab real (WJR) frames e áudio **não** bateram: o ffmpeg do Ubuntu do Colab é outro build (x264, AAC e loudnorm/resampler mudam entre versões), e o modo auto do Chrome podia ligar raster de GPU (agora forçado para software). Para comparar, use ffmpeg travado (`SIMPLICIO_FFMPEG_URL` + `SIMPLICIO_FFMPEG_SHA256`, aplicado pelo `remote_render.py`) e `--gpu-encode 0`. Com NVENC os bytes do vídeo sempre mudam.

**Automação:** feita pelo `--backend colab-cli` (Colab CLI oficial, anunciado em 05/06/2026) e pelo `--backend kaggle`. Comparação com Colab Enterprise, Modal e RunPod no [ADR-0003](../docs/decisoes/ADR-0003-fluxo-100-script.md). Nenhuma conta foi usada e nada foi gasto.
