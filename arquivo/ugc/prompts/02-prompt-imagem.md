# 02 — Prompt de imagem (passo 2)

Na mesma conversa do passo 1, o LLM transforma cada personagem em um prompt de imagem para o GPT Image 2.5: selfie de iPhone, textura de pele, cabelo bagunçado, cômodo com bagunça. O resultado é a entrada do passo 3 (gerar cada prompt 5 vezes e ficar com a que menos parece IA).

Prompt original (em inglês, não traduza):

```
"write a gpt image 2.5 prompt for each character. 

format: casual iPhone front camera selfie, their age, ethnicity, hair, eye color, skin tone with their identifying detail, makeup level, one outfit, no other jewellery, the location you picked, natural light, slightly off-center framing, phone-photo look, not studio. 

add skin texture: visible pores, slight shine, under-eye shadows where it fits. hair should have flyaways or be a little messy. the room should have some clutter."

```

Saída de exemplo (do artigo, sem edição; personagem: mulher de 27 anos junto à janela):

```
"casual iPhone front camera selfie of a 27 year old woman, East Asian, 

long straight black hair tucked behind one ear with a few loose 

strands, dark brown eyes, light skin with natural texture and faint 

freckles on the nose, no makeup, slightly chapped lips, wearing an 

oversized beige cardigan over a white tank top, no other jewellery. 

sitting by a window with an open notebook and a half-drunk coffee 

mug on the sill, soft morning daylight, slightly off-center framing, calm 

gentle expression, phone-photo look, not studio"
```

Próximo: [03-fullbody.md](03-fullbody.md). Visão geral: [../README.md](../README.md).
