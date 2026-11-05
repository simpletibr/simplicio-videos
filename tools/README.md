# tools/ — ferramentas opcionais da esteira

Os arquivos de cada ferramenta vivem em `src/simplicio_video/data/tools/` (dados do pacote, para irem no wheel). Ferramentas externas que a esteira **pode** chamar, mas das quais o caminho padrão (intake → spec → template → HyperFrames → render) não depende. Cada uma tem `setup.sh` com versão fixada (clona fora do repo, nunca vendoriza) e um README de uso.

| Ferramenta | Etapa | Quando | Uso |
|---|---|---|---|
| [video-use](../src/simplicio_video/data/tools/video-use/README.md) | 6 (edição, opcional) | O usuário pede ajuda de edição: cortar para X s, reordenar, aparar footage, legendas, revisão de cortes | `simplicio-video edit setup` |
