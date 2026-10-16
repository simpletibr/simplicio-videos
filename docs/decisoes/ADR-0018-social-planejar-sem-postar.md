# ADR-0018: social planeja e documenta, o motor não posta (regra 3 do AGENTS.md)

- **Status:** aceito. Implementado em `src/simplicio_video/social.py` (`social providers|plan|check|recipe`, tool MCP `video.social`).
- **Data:** 16/10/2026 (BRT)
- **Relaciona:** [AGENTS.md](../../AGENTS.md) (fronteira do produto, regra 3) · [skills/simplicio-video-social](../../skills/simplicio-video-social/SKILL.md) · [docs/realoficial.md](../realoficial.md) · [ADR-0003](ADR-0003-fluxo-100-script.md) (o upload no Drive saiu do motor, #77)

## Contexto

O Wesley pediu um "módulo de publish, integrado com o Zernio MCP e o Real Oficial MCP; o Real Oficial é o padrão; para postar em redes sociais". A regra 3 da fronteira do produto diz que o motor não tem UI, contas, cobrança, projetos, planos nem **publicação/postagem**, e que nenhuma funcionalidade ganha dependência de aplicação host. O `publish` antigo (upload no Drive) saiu do motor por isso (#77). Um módulo que posta de dentro do motor reabriria o que a regra fechou: credenciais de rede social no motor, ação irreversível em público e dependência de um serviço externo.

Os dois serviços já são MCPs que o agente usa direto. O Real Oficial separa cotar de confirmar (`ro_preview_publication` devolve `quote_id` e termos; `ro_confirm_publishing` só com `confirm: true` e o sim do usuário). O Zernio expõe `posts_create` e não tem, nas páginas lidas, prévia nem cotação.

## Decisão

1. **O motor não posta.** O módulo novo se chama `social` (o nome `publish` continua sendo o upload no Drive que saiu). Ele só faz o que é local e determinístico:
   - `social providers`: lista `realoficial` (padrão) e `zernio`, as ferramentas MCP de cada um, as lacunas e o que está UNVERIFIED;
   - `social plan`: confere o MP4 final (duração, proporção, tamanho, codec, legenda, título e hashtags) contra a tabela de limites por rede e grava `social.plan.json`, determinístico (sem horário de geração) e sem segredo;
   - `social check`: reconfere o plano contra o arquivo (sha256, plano não editado, agendamento ainda no futuro);
   - `social recipe`: imprime a sequência de chamadas MCP do provedor, com os argumentos do plano, na ordem cotar ou prever, mostrar ao usuário, pedir o consentimento e só então publicar.
2. **Quem publica é o agente**, com as ferramentas MCP do próprio provedor e o consentimento explícito do usuário por postagem. O plano gravado é a trilha de auditoria, não a autorização.
3. **O MCP do motor expõe só leitura e geração local:** `video.social` aceita `providers`, `plan`, `check` e `recipe`, e responde erro a qualquer ação de publicar. O `plan` pelo MCP grava só ao lado do vídeo e nunca sobrescreve; `--force`, `--out` e `--aceito-unverified` são só do terminal. `plugin.json` tem quatro verbos fechados (sem `args` livre) e nenhum de publicar.
4. **Sem credencial e sem rede dentro do motor.** `social.py` não lê variável de ambiente, não importa cliente HTTP, socket nem cliente MCP (um teste confere os imports). A autenticação (OAuth 2.1 no Real Oficial; OAuth ou chave de API no Zernio, UNVERIFIED qual) fica no cliente MCP do agente. Plano, receita e `providers` não guardam chave, token ou senha, e `--target` recusa conta com cara de segredo.
5. **A receita nasce de um modelo de dados**, `src/simplicio_video/data/social/providers.json` (um `recipe` por provedor, com schema), e o motor se recusa a devolver uma receita em que uma chamada de publicar venha antes do passo "mostrar" e do passo "consentimento" (nem sem cotar antes, no Real Oficial). Os testes provam que nenhuma saída do motor (texto, JSON, MCP) tem chamada de confirmar sem o consentimento antes.
6. **Limites por rede com procedência.** `limits.json` tem, por linha, `source_url`, `read_on` e `confidence`. Só o limite de duração do YouTube Shorts foi conferido na página oficial (`official`). O resto foi lido na documentação do Zernio, que é terceiro, e fica **UNVERIFIED**: violá-lo recusa o plano, e só `--aceito-unverified` (terminal) deixa passar. Um limite oficial violado nunca passa.

## Por que isto respeita a regra 3

A regra proíbe publicação/postagem **no motor** e dependência de host. Aqui o motor produz um arquivo e um texto: nada abre rede, nada guarda credencial e nada executa uma publicação. O ato de postar acontece fora do motor, no cliente MCP do agente, sob consentimento do usuário. O módulo é útil para qualquer LLM ou aplicação (o plano e a receita são dados), e o motor continua funcionando sozinho, sem nenhum dos dois serviços. O AGENTS.md aponta a exceção (`social` só planeja) sem ampliar a regra 3: ela continua dizendo que o motor não publica.

## Alternativas descartadas

- **Um `publish` no motor que chama os dois MCPs:** exigiria credencial e rede no motor, executaria ação irreversível sem o usuário na conversa e quebraria a regra 3.
- **Só documentação, sem módulo:** o agente perderia a conferência determinística (limites, hash) e a trilha de auditoria, e cada agente reinventaria a ordem das chamadas.
- **Aceitar limite UNVERIFIED violado só com aviso:** transformaria uma tabela não conferida em autorização para postar; por isso a recusa e a flag explícita.
- **Consentimento global ("posta tudo o que eu pedir"):** posts em público não se desfazem; o sim vale por postagem.

## Consequências

- O Real Oficial não recebe MP4 local por MCP (a cotação usa o `clip_id` de um clip que já está lá; `ro_import_video` só importa vídeo de IA gerado nele). A receita do padrão sai bloqueada sem `--clip-id` e manda subir o MP4 no app; o Zernio tem upload de mídia e cobre esse caso, mas o fluxo dele está em boa parte UNVERIFIED (parâmetros de upload, nome do campo da mídia, rascunho, idempotência).
- A tabela de limites envelhece: cada linha tem a data de leitura e o plano guarda o hash da tabela; `social check` avisa quando ela mudou.
- Conferir os limites nas páginas oficiais de cada rede é trabalho que fica em aberto (UNVERIFIED).
