# 01 — Elenco (passo 1)

O LLM (Opus 5.5) escolhe os 10 personagens a partir do app e do público. Preencha `[app name]`, a frase do que o app faz e o perfil do usuário (para cliente real, tudo vem de `clients/<slug>/coleta/`). A última linha do prompt ("people i'd scroll past on tiktok, not models") evita 10 pessoas bonitas de pele perfeita, que é o jeito mais rápido de ser chamado de IA nos comentários, segundo o autor.

Prompt original (em inglês, não traduza):

```
"my app is [app name]. it does [one sentence]. 

my user is [age, gender, where they live, what they struggle with]. 

give me 10 ugc characters who would realistically use this app. 

for each one: age, gender, ethnicity, job, the exact moment in their day they'd open the app, where they'd be filming, and one physical detail that makes them recognizable (a mole, a scar, freckles, a gap in their teeth). 

make them feel like people i'd scroll past on tiktok, not models."
```

Próximo: [02-prompt-imagem.md](02-prompt-imagem.md) (mesmo chat). Visão geral: [../README.md](../README.md).
