# tools/ — ferramentas opcionais da esteira

Ferramentas externas que a esteira **pode** chamar, mas das quais o caminho padrão (intake → spec → template → HyperFrames → render) não depende. Cada uma tem `setup.sh` com versão fixada (clona fora do repo, nunca vendoriza) e um README de uso.

| Ferramenta | Etapa | Quando | Uso |
|---|---|---|---|
| [video-use](video-use/README.md) | 6 (edição, opcional) | O usuário pede ajuda de edição: cortar para X s, reordenar, aparar footage, legendas, revisão de cortes | `bash tools/video-use/setup.sh` |
