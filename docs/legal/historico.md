# Histórico do repositório

Este documento registra dados de cliente que ficaram no histórico do git e as opções para tratá-los. A regra é não reescrever o histórico sem autorização explícita do dono do projeto.

## O que está no histórico

O `git log --all -- 'clients/*/coleta/*'` lista 4 commits que tocaram a pasta `coleta/` de clientes:

- `fc0358a`: feat(video-01): showreel 15s ... `coleta/` do cliente (WJR Informática Games)
- `6175632`: video-01: 20 s com cena de serviços ...
- `ecfdd29`: Lothus Odontologia: coleta pública, ...
- `c35ff25`: chore: remove client data (coleta, client READMEs, Drive links, WJR intake)

O commit `c35ff25` removeu os textos da coleta, mas o histórico anterior continua com os arquivos e com o conteúdo deles. Além disso, 12 imagens do site do cliente WJR (`clients/wjr-informatica-games/coleta/site/imagens/`, incluindo `logo.png`) continuam rastreadas no `HEAD` desde `fc0358a`. Ou seja: o dado de cliente está tanto no histórico quanto na árvore atual.

## Opções

**(a) Recomendada: publicar um repositório novo com histórico limpo.** Criar um repo novo a partir do estado atual, com a coleta de cliente removida da árvore e do histórico, por exemplo com `git filter-repo --path clients/<cliente>/coleta --invert-paths` aplicado a uma cópia do repo. O repo antigo fica privado ou é arquivado. Não mexe no histórico existente.

**(b) Reescrever o histórico do repo atual.** Destrutivo: muda todos os hashes, quebra clones e forks existentes e exige force push. Só com autorização explícita do dono.

## Estado

Nada foi feito. Nenhum commit foi reescrito, nenhum arquivo de cliente foi removido da árvore nesta fase. A escolha entre (a) e (b) depende de autorização explícita do dono do projeto.
