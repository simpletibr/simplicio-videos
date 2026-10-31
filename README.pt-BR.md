# simplicio-videos

> Motor determinístico de vídeo: um contrato YAML entra, um MP4 e um manifesto saem. Mesma entrada, mesma saída.

**Idiomas:** [English](README.md) · [Português](README.pt-BR.md)

## O que é e para quem é

O simplicio-videos é o plugin de vídeo do Simplicio Runtime. Quem escreve o roteiro é uma pessoa ou um agente, no contrato YAML (cenas, falas, marca, trilha). O CLI `simplicio-video` valida o contrato, gera a voz, renderiza com HyperFrames e grava um manifesto com o que foi feito. Nenhum LLM roda no caminho do render.

Para quem é: quem produz anúncios e vídeos curtos com voz, legenda e cortes, e agentes (Claude Code, Codex e outros) que precisam de ferramentas de vídeo com saída verificável, por CLI ou pelo servidor MCP.

## Mapa de capacidades

| O que fazer | Comando | Estado | Custo ou limite |
|---|---|---|---|
| Gerar MP4 a partir de contrato | `init`, `validate`, `voice`, `render`, `run` | 8 templates prontos (`list templates`); 6 de esqueleto, que não renderizam | Local. O render usa ffmpeg e HyperFrames (Node) |
| Voz | `voice --provider` | `file`, `local`, `gemini`, `voxcpm`, `openvoice`, `voicestudio`; `elevenlabs` e `xai` são stubs | `gemini` usa chave de API; `voxcpm` exige referência de voz autorizada |
| Mídia em qualquer MP4 | `media probe`, `audio`, `sheet`, `subs`, `burn`, `mask`, `replace-audio`, `voice-track` | Pronto (ffmpeg e ffprobe) | `burn` exige ffmpeg com libass |
| Baixar vídeo público | `media fetch` | Pronto | Exige `--autorizo`. Usa yt-dlp fixado, instalado sob demanda |
| Cortes verticais 9:16 | `shorts` | Pronto | Só ffmpeg, determinístico |
| Edição por EDL | `edit` | Pronto (video-use fixado) | Transcrição local com faster-whisper |
| Troca de personagem | `swap`, `jobs` | Pronto | Gasta créditos. Só no terminal, com `--autorizo --yes` |
| Planejamento de redes | `social` | Pronto | Não posta. A publicação fica em outra camada |
| Biblioteca Openverse | `openverse` | Pronto | Revisão por pedido. A licença é da fonte |
| Pesquisa na web | `busca` | Pronto | Exige TinyFish e chave. Teto diário de chamadas |
| Trilhas externas | `montage`, `opencut`, `clone`, `toonflow`, `moneyprinter`, `matchcut`, `edit` | Instalação sob demanda, versão fixada | A licença varia; veja a tabela de trilhas |
| Servidor MCP | `simplicio-video-mcp` | 29 tools `video.*` | Sem login, logout, gasto em `swap run` nem remoção de software |
| Limpeza de áudio | não há ainda | Em PR, não está no main | não se aplica |
| Dublagem com fundo preservado | não há ainda no CLI | Hoje só no app VoiceStudio; exposição em andamento | não se aplica |

## Instalação

### Pré-requisitos

- **Python 3.10 ou mais novo.** Testado com Python 3.14.6 no macOS. O `doctor` avisa que os extras do CrewAI exigem Python abaixo de 3.14.
- **Node 22 ou mais novo** para o render (HyperFrames). O `doctor` confere. Testado com Node 26.8.2.
- **ffmpeg com libass** para `media burn`. O `doctor` confere os dois. Testado: o `doctor` acusa quando o ffmpeg não responde.

### Passos

Testado num venv limpo no macOS:

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[mcp]"                    # o extra mcp só é preciso para o servidor MCP
simplicio-video --version                  # simplicio-video 0.5.0
simplicio-video setup --yes --lang pt-BR   # cria o workspace; não faz login
simplicio-video doctor                     # mostra o que falta; marca "fail" se o ffmpeg não responder
```

Não verificado: `scripts/dev_install.sh` (Linux e macOS) e `scripts/dev_install.ps1` (Windows). Não testei nas duas plataformas.

### Trilhas externas

Não há comando de instalação separado. Cada trilha é instalada no cache (`SIMPLICIO_TOOLS_DIR`, padrão `~/.simplicio-video/tools`) na primeira vez que um comando precisa dela. Testado: `yt-dlp` foi instalado assim, em venv próprio, dentro do cache.

`simplicio-video tools` lista as trilhas e diz se cada uma está instalada. Ele não instala nada.

### Skills para agentes

`simplicio-video install --target <pasta> --dry-run` mostra o que seria copiado para o host, sem escrever nada. Testado com o host `claude`. A cópia de verdade não foi verificada.

## Primeiro uso

### Contrato para MP4

```bash
simplicio-video init minha-marca campanha-1 --template brand-promo --nome "Minha marca"
simplicio-video validate clients/minha-marca/campanha-1/contract.yaml
```

- `init` gera o contrato com os campos a preencher. Testado.
- `validate` lista o que falta preencher: cada campo vazio e o que o template exige. Testado.
- Não verificado: `voice` e `run`/`render`. Precisam de um contrato preenchido e de ffmpeg e Node funcionando, o que não foi possível testar no macOS desta verificação.

### Mídia

```bash
simplicio-video media probe reel.mp4
simplicio-video media subs cues.json -o subs.ass --style band
simplicio-video media burn clean.mp4 subs.ass -o final.mp4
```

Não verificado: os três. O ffmpeg deste Mac não roda. Os exemplos vêm de `simplicio-video media --help`. `burn` exige libass.

### Busca na internet (TinyFish)

Pesquisa e leitura de páginas na internet a serviço dos vídeos, pelo CLI [`tinyfish`](https://www.npmjs.com/package/@tiny-fish/cli) (TinyFish). O motor só repassa a pergunta, limpa o que volta e registra de onde veio: **não chama LLM** e **não decide o que é verdade**. O valor está na procedência (cada resultado sai com a URL e a data da consulta) e no controle de gasto e de privacidade.

```bash
# instalação (o motor nunca instala nada; `simplicio-video busca status` mostra isto quando faltar)
npm install -g @tiny-fish/cli@0.50.1     # versão testada; o pacote declara Node >= 24
tinyfish auth login                      # ou, sem terminal interativo: echo "$CHAVE" | tinyfish auth set

simplicio-video busca status                                                       # binário, versão, chave configurada (nunca o valor), chamadas de hoje e teto
simplicio-video busca consulta "campanha dia das crianças clínica odontológica" --idioma pt --limite 5
simplicio-video busca consulta "datas comemorativas marketing" --dominios exemplo.com.br --excluir pinterest.com --json
simplicio-video busca pagina https://example.com --max-bytes 20480                 # lê UMA página (texto limpo, até 20 KB)
simplicio-video busca log --ultimos 10                                             # registro de procedência
```

- **Privacidade: a consulta é enviada a um terceiro.** A consulta (e a URL de `pagina`) vai para o TinyFish; nunca ponha dado pessoal nem segredo de cliente nela. O motor recusa, **antes de gastar uma chamada**, consulta com chave ou token (`AIzaSy`, `AQ.`, `sk-`, `sk_live_`, `ghp_`, `hf_`, `npm_`, `glpat-`, `Bearer`, JWT, chave privada ou o valor de uma variável cujo nome tem a palavra `KEY`, `SECRET`, `TOKEN` ou `PASSWORD`, como `GEMINI_API_KEY`; `PIP_KEYRING_PROVIDER` não conta) sempre, e com e-mail, CPF ou CNPJ (CPF e CNPJ sem pontuação só quando os dígitos verificadores conferem) a menos que o terminal diga `--permitir-dado-pessoal`. É um freio, não uma garantia: telefone, nome de pessoa e endereço não são detectados, e a política de retenção das consultas do lado do TinyFish não foi lida (UNVERIFIED).
- **Gasto.** Cada execução do binário (uma busca ou uma página) conta numa tabela por dia (UTC, `busca.contador.json`, escrita atômica sob trava). Passou do teto, o comando recusa com mensagem clara e não chama nada. Teto: `--max-chamadas-dia N`, ou a variável `SIMPLICIO_BUSCA_MAX_DIA`, ou 20; o MCP e o plugin só usam a variável ou o padrão. Resposta em cache nunca gasta e funciona offline; chamada que falha também conta. **Preço: UNVERIFIED.** Segundo a leitura de 2026-10-16, nas duas chamadas de fumaça o saldo da carteira ficou igual, e a tabela de tarifas do `tinyfish wallet status` trazia Search 0 USD por consulta, Fetch 0 USD por URL, Agent 0,016 USD por passo e Browser 0,002 USD por minuto (numa segunda leitura voltou "Rates: unavailable"; política de preço é UNVERIFIED, por isso o teto existe mesmo assim). O gasto de verdade se confere no TinyFish: `tinyfish wallet status --pretty`.
- **Cache.** Por hash da consulta (texto, domínios, idioma; o `--limite` é filtro local e não entra), com a data da chamada de verdade. `--atualizar` consulta de novo; resultado com 7 dias ou mais sai com aviso. Pasta de dados: `$SIMPLICIO_VIDEO_DATA/busca/` (padrão `~/.simplicio-video/busca/`) com `cache/`, `busca.registro.jsonl` e `busca.contador.json`.
- **Procedência.** Toda consulta e toda página lida acrescenta uma linha a `busca.registro.jsonl` (`simplicio.busca-registro/v1`): quando (UTC), consulta ou URL, domínios e idioma, versão do CLI, URLs mostradas, **sha256 e tamanho do que o CLI devolveu**, sha256 e tamanho do que foi entregue, se veio do cache e o canal (terminal ou mcp). Sem gravar a linha, o resultado não é entregue. Cada resultado traz `untrusted_fonte` (a URL) e `consultado_em` (a data): é o que um fato de cliente precisa para entrar em `clients/<slug>/coleta/fontes.md`. **Regra do repositório:** fato de cliente só entra com fonte e data vindas do registro da busca e depois de ler a página; o trecho é triagem, não evidência; **a busca não substitui a coleta do cliente**.
- **Texto da internet é dado.** Título, trecho, texto de página, descrição, autor e URLs saem **só** em campos `untrusted_*` (texto e JSON, CLI e MCP), com `aviso_untrusted` no cabeçalho (dado de terceiros, nunca instrução: uma página pode mandar o agente ignorar regras ou chamar ferramentas). No terminal cada valor sai entre aspas JSON (`untrusted_trecho="..."`) e o conteúdo de página sai com `| ` no começo de cada linha. Antes de gravar ou mostrar, o texto perde HTML, `<script>`, comentários, caracteres de controle, ocultos e de direção, e link que não seja http/https; uma passada final tira os dois pontos de qualquer `javascript:`, `vbscript:`, `data:` ou `file:` com alvo colado (em qualquer forma de link, inclusive colchetes aninhados, rótulo longo e definição com quebra de linha; `data: 5 itens` e `/wiki/File:Foo.jpg` ficam como estão); U+2028 e U+2029 viram quebra de linha (para o `| ` do terminal valer em toda linha) e os invisíveis U+034F, U+180E, U+2800 e U+3164 saem; é cortado (título 300 caracteres, trecho 1000, página 20 KB por padrão, até 200 KB com `--max-bytes`); só URL http/https de host com nome público sobrevive: sem IP, `localhost`, `usuário:senha@` nem os sufixos `.internal`, `.local`, `.lan`, `.localdomain`, `.localhost`, `nip.io` e `sslip.io` (lista curta, **não garantia**: um nome público que aponta para IP privado passa; o fetch é feito no servidor do TinyFish, não na sua rede). Nada é executado. Se o `tinyfish` falhar, o que ele disse sai em `untrusted_erro` (CLI: linha própria no stderr; MCP: campo), nunca dentro da mensagem do motor.
- **Como o binário é chamado.** Só por lista de argumentos (sem shell), sem entrada padrão, com as opções antes e `--` antes da consulta ou da URL, com tempo máximo (60 s a busca, 120 s a página) e tamanho máximo de saída (2 MB e 8 MB); passou, ou o Ctrl+C interrompeu, o grupo de processos é morto. O ambiente repassado é uma lista fechada (`PATH`, `HOME`, `LANG`, proxy e certificados e, se você a exportou, `TINYFISH_API_KEY`); outras chaves do ambiente (Gemini, Openverse, GitHub) não chegam ao binário. A chave fica na configuração do próprio `tinyfish` ou em `TINYFISH_API_KEY`: o motor nunca lê o arquivo, nunca a põe em argumento e descarta o `key_preview` que o `tinyfish auth status` imprime (12 primeiros e 4 últimos caracteres da chave).
- **URL de `pagina`: credencial, redirecionamento e `busca status`.** A URL com `usuário:senha@`, ou com parâmetro de nome `...token`, `...key`, `...secret`, `...signature`, `...sig`, `...password`, `...credential` ou `code` (por sufixo: `access_token`, `X-Amz-Signature`, `private_token`) e valor de 8 caracteres ou mais, na query **ou no fragmento** (`#access_token=...`), é recusada antes de gastar e antes de contar a chamada. Se a página redirecionar (`final_url`) para uma URL que o motor recusa (IP, nome interno, `usuário:senha@`, formato inválido), o motor **não entrega nem guarda o conteúdo**: o registro leva `url_final_recusada: true` (sem URL de resultado) e o erro diz "redirecionamento para URL recusada"; a fonte nunca cai de volta na URL pedida. `busca status` roda `tinyfish --version` e `tinyfish auth status`, dois comandos locais que, pela leitura do código do pacote (2026-10-16), não usam a rede: funciona com `SIMPLICIO_OFFLINE=1` e não gasta. O `status` geral só lê a versão, com o mesmo ambiente fechado.
- **MCP e plugin.** `video.busca` faz `consulta`, `pagina`, `status` e `log`, com o mesmo teto, a mesma recusa de segredo e dado pessoal e sem `--atualizar`, sem `--permitir-dado-pessoal` e sem como mudar o teto. No `plugin.json` são quatro verbos fechados (`video.busca.consulta|pagina|status|log`), com o texto livre depois de `--` para nunca virar opção.
- **Fora desta versão, de propósito.** `agent`, `browser` e `monitor` do TinyFish (automação de navegador, cobrada por passo ou minuto, com login e efeitos colaterais) não existem aqui. Também ficam de fora `fetch` de várias URLs, `--highlights`, `--links`, `--location`, `--page` e o resto do CLI (`connect`, `config-claude`, `wallet`, `vault`).
- **Licença e versão.** O pacote npm `@tiny-fish/cli` 0.50.1 não declara licença (sem campo `license` e sem arquivo LICENSE, lido em 2026-10-16): o motor só chama o binário que você instalou e nunca o embute nem o redistribui; parecer jurídico não foi feito. Os fatos lidos no `--help`, no código do pacote e nas duas chamadas de fumaça, com fonte, data e confiança (incluindo o que é UNVERIFIED), estão em `src/simplicio_video/data/busca/tinyfish.json`; detalhes em [docs/recursos.md](docs/recursos.md).

### Openverse: biblioteca de imagens e áudio revisada

Banco local de imagens e áudio sob licenças abertas, buscados no [Openverse](https://openverse.org/) (API pública `api.openverse.org/v1`) para compor e melhorar os vídeos. O ponto central é a **revisão por pedido**: a revisão vale para o trio (id do ativo, sha256 do arquivo, pedido) e para a proveniência vista na hora (licença, autor, origem), porque "serve" depende do que o vídeo está pedindo naquele ponto e outro id com os mesmos bytes pode ter outro autor. O motor não chama LLM nem decide nada: gera uma folha determinística (sinais objetivos, miniatura ou espectrograma, pista textual, o que falta conferir) e grava o veredito de quem revisou (agente ou pessoa). Sem aprovação para aquele pedido, o `export` recusa, e o contrato só aceita o ativo com a procedência declarada e essa aprovação (veja "No contrato e no render" abaixo).

```bash
simplicio-video openverse search --tipo imagem --consulta "sunrise over the sea" --minimo-largura 1280 --limite 10   # licenças padrão: cc0,pdm,by
simplicio-video openverse search --tipo audio --consulta "rain" --duracao-min 20 --duracao-max 90 --json
simplicio-video openverse get 9d8abc2c-c4dd-4dce-8164-cadd775befcf                          # download seguro para a biblioteca
simplicio-video openverse library review <id> --pedido "nascer do sol para a abertura do vídeo" --folha        # sinais para o revisor VER
simplicio-video openverse library review <id> --pedido "nascer do sol para a abertura do vídeo" --aprovar --motivo "o sol aparece no centro" --por "Wesley"
simplicio-video openverse library export <id> --pedido "nascer do sol para a abertura do vídeo" --contrato clients/acme/video-01/contract.yaml
simplicio-video openverse library credits                                                    # bloco de créditos de tudo o que foi exportado
simplicio-video openverse library verify clients/acme/video-01/contract.yaml                  # confere, sem rede, os ativos do Openverse declarados no contrato
simplicio-video openverse library list|show <id>                                             # o que há na biblioteca, integridade e vereditos
```

- **Licenças.** O padrão é `cc0,pdm,by`, as seguras para uso comercial e edição. `by-sa`, `by-nc`, `by-nd` (e `by-nc-sa`, `by-nc-nd`) só entram por `--licencas` explícito, com aviso do que implicam; `nc` e `nd` nunca entram por padrão e o `export` de qualquer licença com restrição (`nc`, `nd` e `sa`) exige `--aceito-restricao`. A licença que o Openverse devolve vem das fontes (Flickr, Freesound e outras) e ele mesmo manda conferir na origem: cada item guarda a `foreign_landing_url`. **Isto não é parecer jurídico.** Item sem licença conhecida nunca é baixado; CC BY sem autor nunca é exportado.
- **Biblioteca.** Fica em `OPENVERSE_LIBRARY_DIR` (padrão `~/.simplicio-video/openverse-library`): `index.json` (`simplicio.openverse-library/v1`), `files/<sha256>.<ext>`, `cache/` (cada busca por hash da consulta, com data: repetir a busca sai do cache e funciona offline; `--atualizar` consulta de novo) e `sheets/`. Cada item guarda id do Openverse, título, autor e URL do autor, licença, versão e URL da licença, texto de atribuição, `foreign_landing_url`, provedor, tags, tipo, dimensões ou duração, data da consulta e do download, sha256 e tamanho.
- **Revisão.** `--folha` mostra, para imagem, dimensões, proporção, tamanho, formato real, nitidez (variância do Laplaciano), brilho médio e a marca de mature, e gera a miniatura; para áudio, duração, taxa de amostragem, loudness (ebur128), fração de silêncio, clipping e o espectrograma. Traz também uma pista textual (palavras do pedido que aparecem no título e nas tags; não é veredito) e o que falta conferir. `--aprovar` e `--reprovar` gravam sha256 do ativo, pedido normalizado (sem acento, minúsculas), veredito, motivo, quem revisou (`--por`) e a data; aprovar exige a folha do par antes. Aprovar para o pedido A não vale para o pedido B, e um arquivo novo (outro sha256) invalida as aprovações antigas. O último veredito do par vale.
- **Export e crédito.** `library export` copia o ativo aprovado para `--para <pasta>` ou, com `--contrato`, para `assets/openverse/` ao lado do `contract.yaml`; nunca sobrescreve um arquivo existente com bytes diferentes (mesma regra do `publish`); acrescenta título, autor, licença e URLs a `CREDITS-openverse.md` na pasta. Quando a licença tem restrição (`nc`, `nd`, `sa`), o export com `--aceito-restricao` grava esse aceite no índice (`aceito_restricao`, por ativo e pedido), que o contrato confere depois. Cole o crédito onde a licença pede (descrição da publicação ou cartão final, `marca.credito`); o render também grava os créditos do vídeo ao lado do MP4 (próxima seção).
- **No contrato e no render.** Um asset do contrato (`assets[]` ou `marca.logo`, imagem ou áudio) ganha o bloco opcional `openverse: {id, pedido}`. O fluxo completo, do pedido do vídeo ao MP4 com créditos:
  1. **Buscar:** `openverse search --tipo imagem --consulta "..."` (cacheada; títulos e tags costumam estar em inglês).
  2. **Baixar:** `openverse get <id>` (só pelo terminal; download seguro para a biblioteca).
  3. **Revisar para o pedido:** `library review <id> --pedido "<o que a cena precisa>" --folha`, olhar a miniatura ou ouvir o áudio e gravar `--aprovar` (ou `--reprovar`) com `--motivo` e `--por`.
  4. **Exportar:** `library export <id> --pedido "<o mesmo pedido>" --contrato clients/<slug>/<video>/contract.yaml` copia o aprovado para `assets/openverse/` ao lado do contrato e grava a linha de crédito em `assets/openverse/CREDITS-openverse.md` (licença com restrição pede `--aceito-restricao`, gravado no índice).
  5. **Declarar no contrato:** o arquivo copiado entra em `assets`, agora com a procedência.
  6. **Validar:** `simplicio-video validate <contrato>` (ou `library verify <contrato>`, que lista o que falta) confere tudo **sem rede e sem LLM**; `run` e `render` usam o mesmo portão.
  7. **Renderizar com créditos:** o render grava a procedência no `render.manifest.json` e os créditos ao lado do MP4.

  ```yaml
  assets:
    - arquivo: assets/openverse/hdr-sunrise-over-the-sea-3a4d41c6.jpg      # o que o export copiou
      destino: assets/client/abertura.jpg
      openverse:
        id: 9d8abc2c-c4dd-4dce-8164-cadd775befcf
        pedido: nascer do sol para a abertura do vídeo                     # o que a cena precisa (comparado normalizado)
  variaveis:
    foto_abertura: assets/client/abertura.jpg
  ```

  O `validate` recusa, cada um com mensagem clara: id que não existe na biblioteca; arquivo com sha256 diferente do da biblioteca (trocado ou alterado); sem veredito aprovado para o par exato (id, sha256, pedido, proveniência), inclusive pedido diferente do aprovado e aprovação antiga depois de autor, licença ou origem mudarem; índice inválido; licença com restrição sem o `--aceito-restricao` gravado no export; crédito ausente em `CREDITS-openverse.md`; arquivo em `assets/openverse/` **sem** o bloco `openverse` (copiar à mão não burla o portão, e qualquer asset com os mesmos bytes de um ativo da biblioteca também pede o bloco); bloco num arquivo fora de `assets/openverse/`; o mesmo vale para `placas_video[].file` (a placa nunca carrega o bloco: o ativo não entra como placa); dois arquivos para o mesmo `destino`. Depois de compilar, o render compara os bytes de toda a composição com a biblioteca: um arquivo com os bytes de um ativo (por exemplo uma cópia exata na pasta do template) só passa se for o `destino` de um asset declarado e aprovado, e todo `destino` declarado precisa ter exatamente os bytes aprovados. Use o arquivo exportado como está: recorte e escala na composição (CSS), nunca um derivado em disco (`by-nd` não permite). Um contrato sem ativo do Openverse se comporta exatamente como antes (o `validate` nem abre a biblioteca). A aprovação é conferida na biblioteca desta máquina (`OPENVERSE_LIBRARY_DIR`): num computador sem ela o contrato com ativo do Openverse é recusado. O render grava em `render.manifest.json`, chave `openverse`, a procedência de cada ativo (id, sha256, licença, pedido revisado, quem aprovou, canal e data; título, autor e URLs só em campos `untrusted_*`) e `<video>.CREDITS-openverse.md` ao lado do MP4 (e da prévia), gerado do índice com as mesmas sanitizações do `export`: é o crédito do vídeo entregue e a regra de atribuição CC BY vale para ele. Os hashes dos ativos entram no hash de entrada do render (`inputs_sha256`), e a mesma entrada dá o mesmo manifesto e os mesmos créditos. **Áudio:** o portão e os créditos valem igual, mas o motor de áudio não mixa um áudio externo sozinho; só um template ou bloco que referencie o arquivo o toca (nenhum template embutido o faz). A narração (`voz.providers.file.dir`) não passa pelo portão: não use ativo do Openverse como voz. **Backend `colab` (manual):** só gera o bundle, sem manifesto nem créditos ao lado do MP4; use o `CREDITS-openverse.md` de `assets/openverse/`.
- **Segurança do download.** O servidor da fonte não é confiável: só https na porta 443; o host é resolvido e qualquer endereço privado, loopback, link-local ou reservado é recusado antes e depois de cada redirecionamento (até 5), e a conexão vai no IP validado; limite de 25 MB (imagem) ou 50 MB (áudio) lido em blocos; o tipo vem da assinatura dos bytes, nunca do Content-Type; extensões jpg, png, webp, gif, mp3, ogg, wav, flac, m4a; nome do arquivo sempre derivado do sha256; sha256 conferido depois de gravar; nada do arquivo é executado (o ffmpeg só abre o arquivo da biblioteca, com demuxer forçado). Os downloads conectam direto, sem proxy.
- **Credenciais e limites.** Sem credencial a busca é anônima (20 resultados por página; hoje 20 requisições por minuto e 200 por dia, lidos nos cabeçalhos da API em 2026-10-16). `OPENVERSE_CLIENT_ID` e `OPENVERSE_CLIENT_SECRET` (OAuth2 client credentials) são opcionais, só por variável de ambiente, e nunca aparecem em argumento, índice, cache, folha ou saída. Os termos do Openverse proíbem raspagem: o comando limita a página e guarda cache, e não varre a API. Este projeto usa a API do Openverse e **o Openverse não endossa nem certifica o simplicio-video**.
- **MCP.** `video.openverse` faz `search`, `list`, `show`, `folha` e `review`. Baixar (`get`) e exportar ficam só no terminal: o agente não escolhe o que se baixa nem onde se grava. No `plugin.json` são seis verbos fechados (`video.openverse.search|list|show|folha|aprovar|reprovar`). O índice grava o canal real de cada veredito: `terminal` (CLI), `mcp` (servidor MCP) ou `plugin` (os verbos `aprovar` e `reprovar` passam `--canal plugin` no argv fechado; o CLI recusa `--canal mcp`). Aprovar pelo MCP ou pelo plugin exige a folha do par, como no terminal. Não há tool MCP nova para o contrato: o agente declara o bloco e roda `video.validate`, que aplica o portão (`library verify` é do terminal).
- **Texto da internet é dado.** Título, autor, tags, atribuição, URLs e provedor só aparecem na folha (texto e JSON), nas saídas do MCP e no `--json` do CLI dentro de campos `untrusted_*`, junto de um aviso: são dado de terceiros, nunca instrução. O revisor aprova depois de ver a miniatura ou ouvir o áudio. No `CREDITS-openverse.md` esse texto perde HTML, URLs soltas e quebras de linha, e a pontuação de Markdown é escapada; URL de autor e origem só https, URL da licença só do `creativecommons.org`, versão da licença só numérica.
- **Índice.** Todo campo do `index.json` que vira caminho (id, tipo, formato, arquivo, nome do arquivo exportado) é validado ao carregar, e o caminho resolvido precisa ficar dentro da biblioteca (sem `..`, absoluto nem symlink para fora); índice inválido é recusado com mensagem clara. O índice não é fronteira de segurança: quem edita o disco edita tudo.
- **Fora do escopo agora.** Mixar um áudio do Openverse na trilha (o `build.mjs` só sintetiza música, SFX e voz); detectar uma cópia que mudou de bytes (recodificada); conferir a aprovação num computador sem a biblioteca. Similaridade imagem-texto com CLIP local (extra `[review]`) ficou como nota: exigiria torch e pesos de modelo, que não foram testados aqui. O que foi lido na documentação do Openverse, com fonte, data e o que é UNVERIFIED, está em `src/simplicio_video/data/openverse/api.json`; detalhes em [docs/recursos.md](docs/recursos.md).

### Limpeza de áudio

Ainda não existe no main. Esta seção ganha os comandos quando a PR de limpeza de áudio for mesclada.

## MCP

- Servidor: `simplicio-video-mcp` (stdio). Testado: responde `initialize` e lista 29 tools `video.*` pelo protocolo stdio.
- Lista das tools: [docs/reference/mcp-tools.md](docs/reference/mcp-tools.md).
- **Ficam de fora por segurança:**
  - `login` e `logout`: só no terminal;
  - `swap run`: gasta créditos;
  - `install --uninstall` e `--prune-project-copies`: removem software;
  - `montage` com subcomandos além de `clone`, `doctor`, `hyperframes-doctor`, `preflight` e `help`;
  - `auth` com ação diferente de `status`.
  - Fonte: `src/simplicio_video/mcp_server.py`.
- **Clientes:** a configuração para Claude Code e Codex não foi verificada. O `claude` está instalado neste Mac, mas não rodei `claude mcp add` para não alterar a configuração dele. O Codex não está instalado.

## Solução de problemas

| Sintoma | Causa provável | O que fazer |
|---|---|---|
| `ffmpeg não respondeu à versão` no `doctor` | ffmpeg quebrado. Visto neste Mac: `Library not loaded: libvpx` | Reinstalar o ffmpeg e rodar `doctor` de novo. O comando de reinstalação não foi verificado |
| `sem ffmpeg não há como checar o libass` | ffmpeg ausente, ou sem libass | Instalar ffmpeg com libass. `media burn` falha sem ele |
| Trilha aparece como não instalada | Cache vazio | Rodar o comando que usa a trilha. `simplicio-video tools` mostra o estado |
| `fetch: confirme que você pode usar este vídeo com --autorizo` | Autorização não dada | Passar `--autorizo` só depois de confirmar o direito de uso. Sem a flag, nada é baixado (testado) |
| `template: X has no 'composicao'` | Template de esqueleto | Escolher um template pronto (`simplicio-video list templates`) |
| campo pendente no `validate` | Contrato gerado e não preenchido | Preencher os campos só com fatos da coleta |
| `não logado` no `doctor` | Login compartilhado não feito | Não é exigido para o render. Só importa para o Runtime |
| Aviso de Python 3.14 no `doctor` | Extras do CrewAI | Usar Python abaixo de 3.14 se for usar esses extras. Não verificado |
| `testada: 0.50.1` no `busca status` | TinyFish em outra versão | O motor segue funcionando; a versão testada é 0.50.1 |

## Trilhas externas e licenças

Cada versão está fixada em [`src/simplicio_video/tools.py`](src/simplicio_video/tools.py). `simplicio-video tools` lista todas. O motor nunca vendoriza nem importa essas trilhas, e o render determinístico não depende de nenhuma delas.

| Trilha | Comando | Versão fixada | Licença |
|---|---|---|---|
| OpenMontage | `montage` | commit `9327439` | AGPL-3.0 |
| OpenCut | `opencut` | commit `cf5e79e` | MIT |
| Hypit | `clone` | npm `0.2.17` | Licença Hypit (Apache-2.0 modificada); sem redistribuição comercial |
| Toonflow | `toonflow` | commit `d2e94ac` | MIT |
| MoneyPrinterTurbo | `moneyprinter` | commit `4b7b965` | MIT |
| match-cut | `matchcut` | commit `b51c98f` | MIT. Uso exige login e créditos na Renoise |
| TinyFish CLI | `busca` | npm `0.50.1` | Não declarada no pacote |
| VoiceStudio | `voicestudio` | commit `beeaae08` | AGPL-3.0. Usado só por HTTP local |
| video-use | `edit` | commit `b877063` | MIT |
| yt-dlp | `media fetch` | PyPI `2026.10.26`, sha256 conferido | Unlicense |

**Lacunas conhecidas:**
- Limpeza de áudio: em PR, ainda não está no main.
- Separação de voz e fundo: não há comando.
- Dublagem com fundo preservado: só no app VoiceStudio hoje.

## Referências

- [docs/reference/cli.md](docs/reference/cli.md): todos os comandos e flags.
- [docs/reference/mcp-tools.md](docs/reference/mcp-tools.md): tools MCP.
- [CHANGELOG.md](CHANGELOG.md): mudanças por versão.
- [AGENTS.md](AGENTS.md): regras de operação para agentes.
- [Decisões (ADRs)](docs/decisoes/): visão do plugin, CLI e contrato, fluxo 100% script.
