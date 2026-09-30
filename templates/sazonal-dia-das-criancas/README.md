# sazonal-dia-das-criancas — pronto (campanha, qualquer setor)

A coreografia v2 da Lothus Odontologia (Dia das Crianças 2026: 16 s, 128 BPM, cortes na batida, `fx-transition` de 6–10
frames, confete/balões, `kinetic-words` palavra a palavra no tempo da fala, `beat-burst` nas batidas e câmera com punch/whip)
generalizada para qualquer empresa com público de pais e crianças. Usada por `simplicio-video prospect` (venda ativa,
[docs/venda-ativa.md](../../docs/venda-ativa.md)).

| Arquivo | O que é |
|---|---|
| `composition/index.template.html` | composição; o bloco principal de s2/s3 vem do contrato via `{{padrao:s2-main}}` / `{{padrao:s3-main}}` |
| `contract.base.yaml` | contrato-base (cenas, SFX, trilha festiva 128 BPM, voz local Kokoro `pf_dora`) que o prospect preenche |
| `setores.json` | regras setor → modelos (regex determinístico) e os textos por setor, sem preço/promoção/fato |

| Cena | Papel | Duração | Conteúdo |
|---|---|---|---|
| s1 | saudação | 2,8125 s | balões + confete, "Feliz / Dia das / Crianças!" (igual para todos) |
| s2 | mascote | 4,21875 s | odontologia: `tooth-character`; demais: `icon-mascot` com o ícone do setor · "Hoje é dia de brincar, sorrir e se divertir!" |
| s3 | frase do setor | 4,6875 s | odontologia: `toothbrush-sparkle`; demais: `icon-mascot` (2º ícone) · frase de `setores.json` |
| s4 | assinatura | 4,28125 s | `brand-lockup-soft` (nome real, subtítulo, @ do Instagram, cidade, cor do site) · "Com carinho, {nome}." |

Setores: odontologia, pediatria, escola (escola infantil, berçário, cursos), brinquedos, festas (buffet, parque), games,
moda infantil e `geral` (sem regra casada). Nunca recria o logo: lockup de texto; o logo coletado fica em `coleta/` para o
vídeo pago.
