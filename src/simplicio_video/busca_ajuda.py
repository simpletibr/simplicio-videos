"""Help text of `simplicio-video busca`, apart from `busca.py` so the CLI can print it without importing the module that
calls the `tinyfish` binary (the engine -- render, contract, compiler, pipeline -- does not depend on `busca`)."""
from __future__ import annotations

TETO_PADRAO = 20  # calls per UTC day; busca.py enforces it, the help names it

HELP_DESC = (
    "Pesquisa e leitura de páginas na internet a serviço dos vídeos, pelo CLI `tinyfish` (npm @tiny-fish/cli, TinyFish), com procedência\n"
    "(fonte e data de cada resultado) e teto de chamadas por dia. Zero tokens: nenhuma chamada de LLM; o comando só repassa e registra.\n\n"
    "ATENÇÃO, PRIVACIDADE: a consulta (e a URL de `pagina`) é enviada a um terceiro (TinyFish). Nunca ponha dado pessoal nem segredo de\n"
    "cliente nela. O motor recusa consulta com chave ou token (AIzaSy, AQ., sk-, ghp_, Bearer, JWT, chave privada, o valor de uma variável\n"
    "KEY/SECRET/TOKEN/PASSWORD do ambiente) sempre, e com e-mail, CPF ou CNPJ salvo --permitir-dado-pessoal (só no terminal). É um freio,\n"
    "não uma garantia: telefone, nome de pessoa e endereço não são detectados.\n\n"
    "Subcomandos:\n"
    "  consulta \"<texto>\"   busca na web (`tinyfish search query`). --dominios a.com,b.com e --excluir c.com (até 10), --idioma pt,\n"
    "                       --limite N (padrão 5, até 20, aplicado aqui), --atualizar ignora o cache e gasta 1 chamada\n"
    "  pagina <url>         lê UMA página (`tinyfish fetch content get <url> --format markdown`): só http/https de host público, sem\n"
    "                       usuário:senha nem chave na query. --max-bytes N limita o texto (padrão 20 KB, de 1000 a 200000)\n"
    "  status               o binário foi achado? versão? há chave? quanto do teto de hoje foi usado? (só checagens locais: não gasta)\n"
    "  log [--ultimos N]    lista o registro de procedência (busca.registro.jsonl)\n"
    "  --json               em todos: saída em JSON\n\n"
    "Gasto: cada execução do binário (busca ou página) conta numa tabela por dia (UTC); passou do teto, o comando recusa com mensagem clara.\n"
    f"Teto: --max-chamadas-dia N, ou a variável SIMPLICIO_BUSCA_MAX_DIA, ou {TETO_PADRAO}. Resposta em cache nunca gasta (repete offline); chamada que\n"
    "falha também conta. O TinyFish cobra a automação de navegador, não a busca nem a página (tarifas lidas em 2026-10-16); confira a conta\n"
    "com `tinyfish wallet status --pretty`, que é comando dele.\n\n"
    "Procedência: toda consulta e toda página lida grava uma linha em busca.registro.jsonl (quando, consulta ou URL, versão do CLI, URLs\n"
    "mostradas, sha256 e tamanho do que o CLI devolveu, se veio do cache). Cada resultado sai com a fonte (untrusted_fonte, a URL) e consultado_em\n"
    "(a data): é o que um fato de cliente precisa para entrar em clients/<slug>/coleta/fontes.md. A busca não substitui a coleta do cliente.\n\n"
    "Dado de terceiros: título, trecho, texto de página e URLs vêm da internet e saem SÓ em campos untrusted_* (texto e JSON, CLI e MCP), com\n"
    "aviso: é dado de terceiros e nunca instrução (uma página pode tentar dar ordens ao agente). O texto é limpo (sem HTML, comentário,\n"
    "caractere oculto nem link que não seja http/https) e cortado; nada é executado.\n\n"
    "Instalação: o motor nunca instala nada. Sem o binário, `busca status` mostra o comando (`npm install -g @tiny-fish/cli@0.50.1`) e a chave\n"
    "(`tinyfish auth login`, ou `... | tinyfish auth set`). A chave fica na configuração do próprio tinyfish ou em TINYFISH_API_KEY; nunca\n"
    "por argumento, e o motor nunca a lê nem a imprime (o tinyfish recebe só uma lista fechada de variáveis).\n\n"
    "Fora desta versão, de propósito: `agent`, `browser` e `monitor` do TinyFish (automação de navegador, cobrada por passo ou minuto, com login\n"
    "e efeitos). Pelo MCP (video.busca): consulta, pagina, status e log, com o mesmo teto e a mesma recusa; sem --atualizar nem\n"
    "--permitir-dado-pessoal.")
HELP_EPILOG = (
    "exemplos:\n"
    "  simplicio-video busca consulta \"campanha dia das crianças clínica odontológica\" --idioma pt --limite 5\n"
    "  simplicio-video busca consulta \"avaliações\" --dominios g1.globo.com,folha.uol.com.br --json\n"
    "  simplicio-video busca pagina https://example.com --max-bytes 20480\n"
    "  simplicio-video busca status\n"
    "  simplicio-video busca log --ultimos 10 --json")
