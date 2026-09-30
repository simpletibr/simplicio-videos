# colab/ — render na GPU do Google Colab

`render.ipynb` renderiza um **bundle** gerado pelo CLI e imprime os tempos por etapa (setup, frames, encode, master) e a GPU usada.

```bash
simplicio-video render clients/wjr-informatica-games/video-01/contract.yaml --backend colab
# -> clients/wjr-informatica-games/video-01/out/wjr-video-01-cli.colab-bundle.zip (gitignored, ~15 MB)
```

1. Abra `colab/render.ipynb` no Colab (Arquivo → Fazer upload de notebook, ou GitHub → `simpletibr/simplicio-videos`, repositório privado).
2. Ambiente de execução → GPU (T4 gratuita basta) → rode as células; envie o `.colab-bundle.zip` na célula 3.
3. A célula 5 mostra `setup_s`, `frames_capture_s`, `encode_s`, `master_s`, `total_s`, a GPU e se frames/áudio batem com o render local (`bundle.json → reference_local`).

O bundle é a composição já compilada (index.html, blocos, fontes, assets, VO tratada, trilha mixada `mix.wav`, `build/variables.json`) + `render_bundle.sh` (HyperFrames fixado, `--gpu` quando o ffmpeg tem NVENC) + `scripts/master.sh`. O zip é reprodutível (timestamps fixos): mesmo contrato → mesmo sha256.

**Determinismo:** encode por CPU reproduz os bytes do render local (testado com o bundle mini: frames, áudio e sha256 do MP4 iguais). Com NVENC o vídeo é recodificado por outro encoder, então os bytes mudam; o áudio masterizado deve bater.

**Automação (próximo passo, não feito):** o Colab gratuito não tem API pública para rodar notebook. Opções avaliadas no [ADR-0002](../docs/decisoes/ADR-0002-cli-contrato-colab-creditos.md): Colab Enterprise / Vertex AI (execuções agendadas por API, pago), ou um runner GPU próprio que roda `render_bundle.sh`. Nenhuma conta foi criada e nada foi gasto.
