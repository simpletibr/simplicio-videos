# Template: notícia de tecnologia (`news-tech`)

**Status: skeleton** — ainda não foi renderizada. O template só vira `pronto` quando o vídeo de referência for aprovado pelo dono do projeto e os textos fixos da composição forem parametrizados (ver Limites conhecidos).

Nichos que caem aqui: notícia de tecnologia, hardware, GPU, placa de vídeo, benchmark, repositório/open source, software, IA.

| Cena | Papel | s | Padrões de motion | Na tela |
|---|---|---|---|---|
| s1 | gancho | 6.0 | `bg-grid-glow-particles`, `news-caption` | número de antes → número prometido em barras, die de GPU desenhado, selo de idade do projeto |
| s2 | promessa | 11.6 | `fx-transition`, `news-caption` | cartela desenhada do post (perfil, handle, tese), painel "o que a tese diz" |
| s3 | prova | 20.9 | `fx-transition`, `news-caption` | barras proporcionais + duas cartelas de multiplicador por modelo |
| s4 | processo | 20.3 | `fx-transition`, `news-caption` | fluxo módulo → driver → GPU, chips "sem BIOS/sem driver", moldura desenhada de UEFI, cold boot |
| s5 | problemas | 24.0 | `fx-transition`, `news-caption` | moldura desenhada de README (data, estrelas, forks, linguagem, status, cobertura) + cartão de ressalva |
| s6 | cta | 7.2 | `fx-transition`, `news-caption` | pergunta, pedido de comentário, nota com a data da consulta |

- **Duração:** 90 s · 9:16 · 30 fps (largura/altura/duração vêm do contrato: trocar formato é editar `formato`)
- **Voz sugerida:** locutor brasileiro de notícia de tecnologia, ritmo contido (Gemini: `Charon`; alternativa `Orus`)
- **Música:** `institucional` a 84 BPM, progressão menor (Am–F–Dm–E), percussão mínima (`drums: 0.25`), sino esparso
- **Tom:** notícia sóbria; toda afirmação de terceiro entra atribuída ("o post diz", "a tese", "atribui")
- **Ritmo:** gancho de 6 s (teto), bloco de credibilidade com 24 s e nenhum bloco acima de ~165 palavras/min.
- **Transições:** `fx-transition` `flash`/`glitch`, 8 frames, `flash_max` ≤ 0,45 (nada de whip nem shapes coloridas)

## Zero footage, zero captura de tela

A composição **não usa imagem, vídeo ou screenshot de terceiro**. Tudo é HTML/CSS/GSAP desenhado no próprio template:

- barras 165 vs 331 (proporcionais: 280 px / 562 px), cartelas 1,83x e 1,95x (a cartela de +40% saiu quando a 4060 Ti foi cortada do roteiro);
- moldura de "tela de README" (barra de janela + linhas) e moldura de "menu UEFI" (linhas + badge Secure Boot), **rotuladas "ilustração"** na tela;
- motivo de die de GPU em geometria (grade 8×8 com células quentes e varredura, semente fixa);
- legenda palavra a palavra.

`placas_video[]` fica **de fora** (opcional no contrato) até existir footage próprio; quando existir, o template aceita o plate sem mudar a composição.

## Legenda palavra a palavra (`news-caption`)

O padrão de biblioteca usado é o [`news-caption`](../../motion/patterns/news-caption/) — autorado para este template a partir do
[`caption-word-highlight`](../../motion/patterns/caption-word-highlight/), com a mesma linguagem (bloco de 5 palavras, palavra
acende em branco e fica em accent com um pop) e uma diferença de contrato: ele recebe **texto** e **tempos separados**
(`text` + `times`) e monta o par `palavra@tempo` dentro do bloco.

Motivo: o `caption-word-highlight` recebe `words` no formato `palavra@tempo|palavra@tempo`, e o contrato só tem placeholder
para os **tempos** (lista de inícios do `timing.lock.json`, que só existe depois do `voice`). Sem o par montado dentro do
bloco, alguém teria que digitar tempos à mão depois de cada leva de voz — exatamente o que o motor proíbe (tempos e fala
andam juntos).

Como fica no contrato: um bloco por cena (`cap-s1`..`cap-s6`), com `params.text` = a fala e `params.times` =
`'{{words:voN}}'`. O `news-caption` está com `status: proposto` no catálogo: o `block.html` existe e compila, mas ainda
não tem `preview.png` (o padrão só vira `pronto` com lint + preview, como os outros).

## Cuidados do setor (estão no `template.json`)

- Sem captura de tela real; moldura desenhada sempre rotulada `ilustração`.
- Número, estrela, fork, data e cobertura **com data de consulta** e sempre atribuídos ("o repositório declara", "o post atribui").
- A promessa nunca vira fato: "prometendo", "a tese", "estaria".
- A ressalva (módulo de kernel, Secure Boot, idade do projeto) entra **antes** do CTA.
- Sem preço, prazo, avaliação ou instrução de instalação; o vídeo não ensina a desligar Secure Boot.
- Marca de terceiro (NVIDIA, RTX, GeForce, Tensor Core, Ada, UEFI, X) só nominativa.

## Como usar

```bash
simplicio-video init <slug> <Campanha> --template news-tech --nome "<Nome>"
simplicio-video validate clients/<slug>/<video>/contract.yaml
simplicio-video voice    clients/<slug>/<video>/contract.yaml --provider gemini   # precisa de GEMINI_API_KEY
simplicio-video validate clients/<slug>/<video>/contract.yaml --need-lock
simplicio-video render   clients/<slug>/<video>/contract.yaml
```

Blocos que a composição exige (todos do contrato): `bg` (fundo de vídeo inteiro), `x1`..`x5` (transição no corte de cada cena, exceto a primeira) e `cap-s1`..`cap-s6` (legenda de cada cena: `params.text` = fala, `params.times` = `'{{words:voN}}'`). Os textos de cena ficam fixos no HTML do template: a composição ainda traz os textos do vídeo de referência (o nome da placa, 165 e 331 TFLOPS, estrelas, forks, datas, fabricante e arquitetura). Hoje um novo vídeo exige editar esses textos na composição; parametrizá-los é condição para o template virar `pronto`.

## Limites conhecidos

- **Textos fixos**: a composição ainda traz os textos do vídeo de referência (RTX 4090, 165 e 331 TFLOPS, estrelas, forks, datas, Nvidia e a arquitetura citada), e os campos de texto das cenas no `template.json` estão vazios (`campos: []`). Parametrizar esses textos é condição para o template virar `pronto`.
- `status: skeleton`: a composição compila (`compile_project` completo com lock sintético: `index.html` sem placeholder pendente, JS válido, blocos e fontes copiados), mas **ainda não foi renderizada** — o primeiro render confirma o layout (principalmente as barras de s3 e as molduras de s4/s5, que ocupam mais altura).
- O die de GPU é geometria decorativa, não representa o die real de nenhum chip.
- Sem `placas_video`, sem b-roll: é notícia falada com gráfico, não reportagem com imagem.
