# colab/ — render na GPU do Google Colab

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

O bundle é a composição já compilada (index.html, blocos, fontes, assets, VO tratada, trilha mixada `mix.wav`, `build/variables.json`) + `render_bundle.sh` (HyperFrames fixado, `--gpu` quando o ffmpeg tem NVENC) + `scripts/master.sh`. O zip é reprodutível (timestamps fixos): mesmo contrato → mesmo sha256.

**Determinismo:** encode por CPU reproduz os bytes do render local (testado com o bundle mini: frames, áudio e sha256 do MP4 iguais). Com NVENC o vídeo é recodificado por outro encoder, então os bytes mudam; o áudio masterizado deve bater.

**Automação (próximo passo, não feito):** o Colab gratuito não tem API pública para rodar notebook. Opções avaliadas no [ADR-0002](../docs/decisoes/ADR-0002-cli-contrato-colab-creditos.md): Colab Enterprise / Vertex AI (execuções agendadas por API, pago), ou um runner GPU próprio que roda `render_bundle.sh`. Nenhuma conta foi criada e nada foi gasto.
