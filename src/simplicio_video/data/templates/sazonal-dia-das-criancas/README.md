# sazonal-dia-das-criancas — pronto (campanha, qualquer setor)

A coreografia v2 do piloto de odontologia (Dia das Crianças 2026: 16 s, 128 BPM, cortes na batida, `fx-transition` de 6–10
frames, confete/balões, `kinetic-words` palavra a palavra no tempo da fala, `beat-burst` nas batidas e câmera com punch/whip)
generalizada para qualquer empresa com público de pais e crianças. Usada por `simplicio-video prospect` (venda ativa,
[docs/venda-ativa.md](../../../../../docs/venda-ativa.md)).

| Arquivo | O que é |
|---|---|
| `composition/index.template.html` | composição; o bloco principal de s2/s3 vem do contrato via `{{padrao:s2-main}}` / `{{padrao:s3-main}}` |

| Cena | Papel | Duração | Conteúdo |
|---|---|---|---|
| s1 | saudação | 2,8125 s | balões + confete, "Feliz / Dia das / Crianças!" (igual para todos) |
| s2 | mascote | 4,21875 s | odontologia: `tooth-character`; demais: `icon-mascot` com o ícone do setor · "Hoje é dia de brincar, sorrir e se divertir!" |
| s3 | frase do setor | 4,6875 s | odontologia: `toothbrush-sparkle`; demais: `icon-mascot` (2º ícone) · frase do setor |
| s4 | assinatura | 4,28125 s | `brand-lockup-soft` (**logo real** no anel quando houver — site/Instagram da empresa, `logo_round`/`logo_size` —, senão nome + subtítulo; @ do Instagram, cidade, cor do site) · "Com carinho, {nome}." |

Setores: odontologia, pediatria, escola (escola infantil, berçário, cursos), brinquedos, festas (buffet, parque), games,
moda infantil e `geral` (sem regra casada). Nunca recria o logo: só entra o arquivo real (coluna `logo` do CSV, logo do site ou
avatar do Instagram quando o robots.txt permitir), convertido para `coleta/logo.png`; sem ele, lockup de texto.

**Padrão v2** (30/09/2026): voz Laomedeia animada (a do piloto de odontologia v02) + logo real + ritmo/confete/palavra a palavra do piloto v02.
A prévia registra `padrao` no `result.json`; o `prospect` refaz prévias de padrão antigo (guardando `preview.v1.mp4`).
