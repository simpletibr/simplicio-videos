# 05 — Esqueleto Seedance 2.5 (passo 5)

Última mensagem ao LLM: cada roteiro vira um prompt de vídeo do Seedance 2.5 neste esqueleto exato, preenchendo os colchetes por personagem (a primeira linha é a instrução ao LLM; o esqueleto é o que vem depois dos dois pontos). O CLI `simplicio-video ugc prompt` monta o mesmo esqueleto sem LLM, a partir de [`../pack.json`](../pack.json) e da fala informada. Cada trecho existe porque um render quebrou sem ele; os porquês estão em [../README.md](../README.md#regras-de-qualidade).

Prompt original (em inglês, não traduza; as quebras de linha são da diagramação do X, ao colar junte em parágrafo corrido):

```
"turn every script into a seedance 2.5 prompt using this exact skeleton, filling in the brackets for each character:

authentic UGC clip, handheld front camera selfie, 9:16. keep the 

character identical to the reference images. [location]. [he/she] is 

already holding [his/her] phone with [app name] open. delivery: [one word]. 

[he/she] says exactly: "[script]". around second 5 [he/she] glances down at the screen, [small reaction], then looks back at camera. one continuous action. 

exactly one phone in the entire scene. no text or captions. iPhone front camera 23mm equivalent, slight handheld drift, built-in mic, no music"
```

Próximo: renderizar um clipe por personagem (passo 6, no [README](../README.md#pipeline-7-passos)).
