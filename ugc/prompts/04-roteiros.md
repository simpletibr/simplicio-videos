# 04 — Roteiros (passo 4)

Volte ao mesmo chat do LLM, que ainda lembra de todos os personagens, e peça 10 roteiros por personagem (100 no total). A regra de contagem de palavras poupa renders: o Seedance estica a fala para preencher o clipe, então 40 palavras em 7 s saem apressadas e 12 palavras deixam o personagem encarando a câmera por uns 4 s. Para cliente real, `[app name]` e os fatos permitidos vêm de `clients/<slug>/coleta/`; fala com número, prazo ou resultado só entra se estiver confirmada lá.

Prompt original (em inglês, não traduza):

```
"for each character write 10 ugc scripts for a 7 second clip. 

22 to 28 words each, because people talk at about 3.5 words a second. 

mix the openers: 4 confessions, 4 callouts, 2 offers. 

no questions as openers. each script has to sound like that specific person talking, using words they'd use. 

mention [app name] once, naturally, never like an ad."
```

Passo 7 (variações do vencedor, texto do artigo; use quando um vídeo performar bem acima dos outros):

```
"write 20 variations of this exact script for the same character, keep the hook, change the details."
```

Próximo: [05-seedance.md](05-seedance.md). Visão geral: [../README.md](../README.md).
