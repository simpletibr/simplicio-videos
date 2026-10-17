# institucional-advocacia — pronto (sóbrio)

Vídeo institucional **informativo** de 16 s (9:16, 96 BPM) para escritórios e sociedades de advogados (o roteamento por setor, `advoca`, `advogad`,
`juridic` e `direito`, é da venda ativa, no repositório de operação). Mesmo padrão v2
das prévias (voz Gemini 3.8 Flash TTS **Laomedeia**, reserva Achernar; logo real; palavra a palavra no tempo da fala; cortes na
batida com transição de 8 frames), com gramática sóbria: sem confete, balões, mascote, estrelas, punch/whip/tremida de câmera,
sem percussão e sem SFX lúdicos (só whoosh suave nos cortes).

| Arquivo | O que é |
|---|---|
| `composition/index.template.html` | composição: `bg-parallax` lento, `line-accent` (linha fina + cantoneiras), `kinetic-words` modo `calm` em Inter, `brand-lockup-soft` sem pontos; câmera com push-in curto e zoom lento |

## Roteiro (texto exato)

| Cena | Tempo | Fala (Laomedeia, sóbria e calma) | Tela |
|---|---|---|---|
| s1 pergunta | 0–3,125 s | "Tem dúvidas sobre os seus direitos?" | Tem dúvidas / sobre os seus / direitos? |
| s2 informação | 3,125–7,5 s | "Conhecer seus direitos é o primeiro passo." | Conhecer seus / direitos é o / primeiro passo. |
| s3 orientação | 7,5–11,875 s | "Orientação jurídica com ética e discrição." (curta: "Orientação jurídica com ética.") | idem, palavra a palavra |
| s4 identificação | 11,875–16 s | "{nome do escritório}." | logo real, NOME / SUB, "informação e orientação jurídica", @, **OAB/UF nº · Cidade** |

Estilo da voz: *"Voz feminina brasileira sóbria e segura, tom calmo, cordial e informativo, ritmo moderado e pausado, dicção
clara, português do Brasil, sem entusiasmo publicitário e sem dramatizar."*

## Conformidade OAB (Provimento 205/2021 + Código de Ética e Disciplina, arts. 39–47)

- [x] Caráter **meramente informativo**, discreto e sóbrio: fala de direitos e de orientação, não vende serviço.
- [x] Sem mercantilização e sem captação: nada de "ligue já", "fale conosco no WhatsApp", "agende", "consulta grátis".
- [x] Sem promessa de resultado: nada de "melhor", "garantido", "ganhe sua causa", "causa ganha", "vitória", "especialista",
      números de casos, valores, clientes ou comparações (o teste `test_institutional_texts_make_no_claims` barra essas palavras).
- [x] Sem preço, honorários, gratuidade ou desconto.
- [x] Sem apelo emocional ou sensacionalismo: trilha sem percussão, câmera sem impacto, sem confete/mascote.
- [x] **Nome + número de inscrição na OAB** (art. 44 do CED): a coluna `oab` do CSV (ex.: `OAB/SP 123.456`) entra na linha da
      cidade do lockup. **Sem `oab` real (conferido no CNA, cna.oab.org.br) a prévia não é renderizada** (status `aguardando_oab`).
- [x] @ do Instagram e logo real só da própria empresa (permitidos como identificação); sem telefone/WhatsApp na tela.
- [ ] Revisão humana (Wesley) antes de enviar; o escritório aprova o texto antes de qualquer publicação.
