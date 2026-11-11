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
| Trilhas externas | `montage`, `opencut`, `clone`, `toonflow`, `moneyprinter`, `matchcut`, `instagram`, `social-research`, `last30days`, `edit`, `rea-video`, `video-to-skill` | Instalação sob demanda, versão fixada | A licença varia; veja a tabela de trilhas |
| Skills e scripts de Instagram | `instagram` | Pronto no commit fixado; instala sob demanda. Os seis scripts rodaram de verdade; nenhum agente foi rodado com as skills | Local, sem chave, sem LLM. As heurísticas são em inglês e pontuam mal o português. Não posta |
| Skills de agente para pesquisa em redes sociais | `social-research` | Pronto no commit fixado; instala sob demanda. As skills não foram rodadas com um agente aqui | As skills chamam o ScrapeCreators (pago, sua chave) a partir do agente; o motor só baixa, lista e lê. Não posta |
| Skill de agente para pesquisa dos últimos 30 dias | `last30days` | Pronto no commit fixado; instala sob demanda. A skill não foi rodada com um agente aqui | A skill (rodada pelo agente) pede Python 3.12+, pode ler cookies do navegador para o X e chama terceiros pagos com as suas chaves; o motor só baixa e lê o SKILL.md. Não posta |
| Vídeo em skill de agente | `video-to-skill` | Novo. Pronto na release fixada (tag v0.3.0); `clone` e `setup` instalam sob demanda. O extrator rodou de verdade num clipe sintético de 4 s; nenhum tutorial real foi processado | Local. O extrator é um binário baixado e conferido por sha256. A transcrição pede modelos de voz que só você baixa. Verificar uma skill gerada não está nas garantias do motor |
| Engenharia reversa de vídeo de referência | `rea-video` | Pronto no commit fixado; instala sob demanda. Clipe sintético testado de ponta a ponta; vídeo real, não | Local por padrão. Com `--vlm`, os quadros vão a um modelo de visão que você configura |
| Servidor MCP | `simplicio-video-mcp` | 34 tools `video.*` | Sem gasto em `swap run` nem remoção de software |
| Limpeza de áudio | não há ainda | Em PR, não está no main | não se aplica |
| Dublagem com fundo preservado | `voicestudio dub create` e `dub-export` | Sobe o vídeo ao app e exporta o job pronto, com música e efeitos, desde que a separação de fundo tenha estado ligada no app | A dublagem em si roda no app |

### Números do código

<!-- BEGIN GENERATED: fatos -->
Contagens geradas do código (`scripts/gen_reference.py`); onde um texto à mão em outro ponto diz outro número, estes são os lidos do código. Não edite aqui: rode `make regen`.

| Fato | Valor |
|---|---|
| Tools MCP (`video.*`) | 34 |
| Trilhas externas | 15 |
| Templates | 15: 8 `pronto`, 7 `skeleton`; 6 sem `composicao` (não renderizam) |
| Padrões de motion | 56: 33 `pronto`, 20 `proposto`, 2 `inline`, 1 `lib` |
| HyperFrames | `hyperframes@0.8.97` |
| Hosts de agente (`install`) | 12: `aider`, `antigravity`, `claude`, `codex`, `cursor`, `gemini`, `grok`, `kiro`, `openclaw`, `opencode`, `simplicio_agent`, `vscode` |
| Hosts com pasta global de skills (`install --global`) | 11: `agents`, `amp`, `claude`, `codex`, `copilot`, `cursor`, `grok`, `kiro`, `opencode`, `simplicio_agent`, `vscode` |
| Skills para agentes | 10 |

| Trilha | Tipo | Pin |
|---|---|---|
| `openmontage` | git | `9327439` |
| `opencut` | git | `cf5e79e` |
| `hypit` | npm | `0.3.1` |
| `toonflow` | git | `d2e94ac` |
| `moneyprinter` | git | `4b7b965` |
| `matchcut` | git | `b51c98f` |
| `instagram` | git | `d03c56b` |
| `social_research` | git | `64ba7b4` |
| `last30days` | git | `07021dc` |
| `voicestudio` | git | `beeaae0` |
| `video-use` | git | `b877063` |
| `tinyfish` | npm | `0.57.0` |
| `yt-dlp` | pip | `2026.10.26` |
| `rea_video` | git | `36e02dd` |
| `video_to_skill` | git | `c1a1b90` |
<!-- END GENERATED -->

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
npm install -g @tiny-fish/cli@0.57.0     # versão testada; o pacote declara Node >= 24
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
- **Licença e versão.** O pacote npm `@tiny-fish/cli` 0.57.0 não declara licença (sem campo `license` e sem arquivo LICENSE, lido em 2026-11-05): o motor só chama o binário que você instalou e nunca o embute nem o redistribui; parecer jurídico não foi feito. Os fatos lidos no `--help`, no código do pacote e nas duas chamadas de fumaça, com fonte, data e confiança (incluindo o que é UNVERIFIED), estão em `src/simplicio_video/data/busca/tinyfish.json`; detalhes em [docs/pesquisa/recursos.md](docs/pesquisa/recursos.md).

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
- **Fora do escopo agora.** Mixar um áudio do Openverse na trilha (o `build.mjs` só sintetiza música, SFX e voz); detectar uma cópia que mudou de bytes (recodificada); conferir a aprovação num computador sem a biblioteca. Similaridade imagem-texto com CLIP local (extra `[review]`) ficou como nota: exigiria torch e pesos de modelo, que não foram testados aqui. O que foi lido na documentação do Openverse, com fonte, data e o que é UNVERIFIED, está em `src/simplicio_video/data/openverse/api.json`; detalhes em [docs/pesquisa/recursos.md](docs/pesquisa/recursos.md).

### Limpeza de áudio

Ainda não existe no main. Esta seção ganha os comandos quando a PR de limpeza de áudio for mesclada.

## MCP

- Servidor: `simplicio-video-mcp` (stdio). Testado: responde `initialize` e lista 34 tools `video.*` pelo protocolo stdio, entre elas `video.rea-video`, `video.video-to-skill` e `video.instagram`.
- Lista das tools: [docs/reference/mcp-tools.md](docs/reference/mcp-tools.md).
- **Ficam de fora por segurança:**
  - `swap run`: gasta créditos;
  - `install --uninstall` e `--prune-project-copies`: removem software;
  - `montage` com subcomandos além de `clone`, `doctor`, `hyperframes-doctor`, `preflight`, `status`, a leitura do registro e `run-tool` (só as quatro ferramentas revisadas, como tarefa);
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
| Aviso de Python 3.14 no `doctor` | Extras do CrewAI | Usar Python abaixo de 3.14 se for usar esses extras. Não verificado |
| `testada: 0.57.0` no `busca status` | TinyFish em outra versão | O motor segue funcionando; a versão testada é 0.57.0 |
| `aviso: o extra ocr não instalou` no `rea-video setup` | `rapidocr-onnxruntime` não tem versão para este Python (3.13 aqui; 3.11 funciona) | Apague a pasta venv em `~/.simplicio-video/rea-video-data` e rode `REA_VIDEO_PYTHON=python3.11 simplicio-video rea-video setup`. Sem OCR, a análise segue |

## Projetos incorporados (trilhas externas)

O motor não importa nenhum destes projetos. Cada um roda como programa separado, instalado sob demanda numa versão fixada: um commit (git), uma versão do npm (Hypit, TinyFish), uma versão do PyPI com sha256 (yt-dlp) ou um binário de release conferido por sha256 (video-to-skill); as versões estão na tabela de licenças mais abaixo. Duas exceções: o TinyFish CLI você instala, e o app do VoiceStudio você abre. O CLI `simplicio-video` chama cada um; vários comandos aceitam `--json`; e o servidor MCP expõe cada um até o ponto dito no item. Nenhum comando do motor posta ou publica. Para ver o estado no seu computador, rode `simplicio-video tools` (instalada ou não, versão fixada, licença) ou `simplicio-video status --json`, que lista as quinze trilhas.

Qual trilha responde a cada pedido (tabela pedido, trilha, comando, tool MCP e limites) e como encadear duas ou mais está na skill [`simplicio-video-trilhas`](skills/simplicio-video-trilhas/SKILL.md).

| Projeto | Licença | Comando | MCP |
|---|---|---|---|
| [OpenMontage](https://github.com/calesthio/OpenMontage) | AGPL-3.0 | `montage` | `clone`, `doctor`, `hyperframes-doctor`, `preflight`, `status`, a leitura do registro e `run-tool` de quatro ferramentas revisadas, como tarefa |
| [OpenCut](https://github.com/OpenCut-app/opencut-classic) (opencut-classic) | MIT | `opencut` | `clone`, `status`, `where`, `help` |
| [Hypit AI](https://github.com/hypit-ai/hypit) | Licença Hypit (Apache-2.0 modificada) | `clone` | lista fechada de comandos e de `media` |
| [Toonflow](https://github.com/HBAI-Ltd/Toonflow-app) | MIT | `toonflow` | `status`, `mcp`, `where`, `clone` |
| [MoneyPrinterTurbo](https://github.com/harry0703/MoneyPrinterTurbo) | MIT | `moneyprinter` | `where`, `clone`, `status`, e `generate` e `run` como tarefa |
| [match-cut](https://github.com/Sac-Y/match-cut) | MIT | `matchcut` | `where`, `status`, `run` (sete scripts, caminhos absolutos) |
| [instagram-agent-skill](https://github.com/Jakeschincariol/instagram-agent-skill) | MIT | `instagram` | `skills`, `skill NOME`, `where`, `status`, `run` |
| [social-media-research-skills](https://github.com/wesleysimplicio/social-media-research-skills) | MIT | `social-research` | `skills`, `skill NOME`, `where`, `status` |
| [last30days-skill](https://github.com/mvanhorn/last30days-skill) | MIT | `last30days` | `skill`, `where`, `status` |
| [VoiceStudio](https://github.com/debpalash/VoiceStudio) | AGPL-3.0 (só HTTP local) | `voicestudio` | todos os subcomandos; saídas absolutas e novas |
| [video-use](https://github.com/browser-use/video-use) | MIT | `edit` | todos, exceto `transcribe-batch`; saídas absolutas |
| [rea-video](https://github.com/JuneYaooo/rea-video) | MIT (declarada no `pyproject.toml`) | `rea-video` | `where`, `status`, `clone`, `summary`, `probe`, `tiles`, `review`, `apply-review`, `remake-plan`; `decompose` e `stems` como tarefa |
| [video-to-skill](https://github.com/brenoepics/video-to-skill) | MIT | `video-to-skill` | `status`, `where`, `check`, `skill`, `frame-at`, `clip`, `compile`, `merge --dry-run`; `extract` de arquivo local como tarefa |
| [yt-dlp](https://github.com/yt-dlp/yt-dlp) | Unlicense | `media fetch` | `fetch` só com `--autorizo`; `--info` livre |
| [TinyFish CLI](https://www.npmjs.com/package/@tiny-fish/cli) | não declarada no pacote | `busca` | `consulta`, `pagina`, `status`, `log` |

### OpenMontage (`montage`)

[calesthio/OpenMontage](https://github.com/calesthio/OpenMontage) · AGPL-3.0

Produção de vídeo com agentes: pipelines e ferramentas do OpenMontage (interface Backlot), rodando como programa separado. `montage setup` cria o venv com as dependências (precisa de rede). `pipelines`, `tools`, `envelope` e `estimate` leem o registro; `estimate` mostra custo e tempo sem executar a ferramenta. `run-tool` roda uma ferramenta do registro pelo motor.

- **Comando:** `montage setup [--remotion] [--piper]`, `montage status --json`, `montage pipelines list|show NOME`, `montage tools list [--runtime R]|info NOME`, `montage envelope [--full]`, `montage estimate NOME --input '{}'`, `montage run-tool NOME --input JSON [--yes] [--timeout SEG]`, `montage clone [pasta]`, `montage open` (padrão), `montage serve --port 8000`, `montage doctor`, `montage demo`.
- **`run-tool` no terminal:** roda qualquer ferramenta. O que não é local, custa dinheiro, tem custo não estimado ou usa rede pede `--yes`, depois da estimativa. A ferramenta de publicação nunca roda.
- **MCP:** `clone` (pasta padrão), `doctor`, `hyperframes-doctor`, `preflight`, `status`, e a leitura `pipelines`, `tools`, `envelope` e `estimate` (`estimate` recebe `input` como objeto; `status` não faz as sondagens ao vivo; `envelope` sai resumido sem `--full`). `run-tool NOME` com `input` vira tarefa em segundo plano (acompanhe com `video.jobs`), só para as quatro ferramentas revisadas no código, que são locais, gratuitas e sem rede: `video_trimmer` (só `cut` e `speed`), `audio_probe`, `frame_sampler` e `scene_detect`. O resto é recusado.
- **Só no terminal:** `setup` (instala pacotes com pip e npm), `open`, `serve` e `demo` (sobem uma interface que não termina, ou renderizam com os pipelines), `clone` com pasta (o agente não escolhe onde o checkout é gravado), `run-tool` de ferramenta fora dessa lista ou que peça `--yes`, e qualquer outro argumento, que roda código Python de quem chama.
- **Exemplo:** `simplicio-video montage pipelines list --json`

### OpenCut (`opencut`)

[OpenCut-app/opencut-classic](https://github.com/OpenCut-app/opencut-classic) · MIT

Editor de vídeo no navegador para o acabamento manual de um MP4 que o CLI já gerou. Usa o opencut-classic, arquivado no upstream, porque o rewrite do OpenCut ainda não tem API. Precisa de Bun.

- **Comando:** `opencut clone [pasta]`, `opencut dev [--lan]`, `opencut status [--json]`, `opencut where`.
- **`dev`:** instala com `bun install` e sobe o editor na porta 3000. Escuta só em 127.0.0.1; `--lan` abre em 0.0.0.0, e a rede toda alcança o editor, sem login na frente. Cria `apps/web/.env.local` (0600) se ele não existir, com um segredo aleatório e placeholders inertes nas variáveis obrigatórias; nunca sobrescreve um arquivo existente.
- **MCP:** `clone` (pasta padrão), `status` (checkout, pin, bun, node_modules, `.env.local` e porta; sem valores) e `where`.
- **Só no terminal:** `dev` (servidor que não termina) e `clone` com pasta.
- **Exemplo:** `simplicio-video opencut dev` (fica no ar até Ctrl+C).

### Hypit AI (`clone`)

[hypit-ai/hypit](https://github.com/hypit-ai/hypit) · pacote npm `@hypit/hypit` · Licença Hypit (Apache-2.0 modificada): proíbe redistribuição comercial e serviço multi-inquilino sem permissão por escrito. O motor não o empacota.

Clonagem de vídeo com agentes. `simplicio-video clone` repassa os argumentos ao Hypit: usa primeiro um `hypit` no PATH; sem ele, roda `npx --yes @hypit/hypit@0.3.1`. Precisa de Node.

- **Comando:** `simplicio-video clone <comando> [argumentos]`, por exemplo `clone status`.
- **MCP:** `video.clone` só aceita uma lista fechada: `help`, `version`, `doctor`, `check`, `plan`, `pricing`, `status`, `builds`, `history`, `activity`, `inspect`, `logs`, `paths` e `vocabulary`; `get <build> --output <nome> --to <caminho absoluto>`; e `media probe|frames|tile|tiles|boundaries|cut`, com caminhos absolutos, sem `..` e sem `--watch`. O resto é recusado.
- **Só no terminal:** `build` (pode gastar em provedores), `studio` (não termina), `auth` (lê um segredo da entrada padrão), `runtime up|down|init|use|unset` (mexe em processos do runtime), `packages` (instala código de terceiros), `capture` (baixa um navegador e abre páginas), `transcribe` e `measure` (usam provedores), `cancel`, `programs`, `result edit` e `snapshot`, `media fetch` (use `simplicio-video media fetch --autorizo`) e `--watch`.
- **Exemplo:** `simplicio-video clone status`

### Toonflow (`toonflow`)

[HBAI-Ltd/Toonflow-app](https://github.com/HBAI-Ltd/Toonflow-app) · MIT

Estúdio de IA para séries curtas, quadrinhos e vídeos, com a criação no próprio app. Roda como aplicação local (Bun). O MCP do próprio Toonflow vem desligado: ligue em Configurações > MCP na interface e rode `toonflow mcp`.

- **Comando:** `toonflow clone [pasta]`, `toonflow serve --lan` (instala, compila e sobe em http://localhost:3000), `toonflow serve --docker` (alternativa só em 127.0.0.1:3000, pelo `docker compose` do próprio Toonflow), `toonflow status [--json]` (checkout, pin, bun, build e arquivo de runtime do MCP; nunca o token), `toonflow mcp [--port N] [--json]` (bloco de config MCP stdio para colar no agente; nunca o token) e `toonflow where`.
- **Atenção:** sem `--lan`, `serve` não sobe: o Toonflow escuta em 0.0.0.0:3000 e não tem login. `--docker` não combina com `mcp`, porque o arquivo de runtime do MCP fica no volume do container.
- **MCP:** `status`, `mcp` (também com `--port N`), `where` e `clone` (pasta padrão).
- **Só no terminal:** `serve` (servidor que não termina; `--lan` expõe na rede, `--docker` fica em 127.0.0.1) e `clone` com pasta.
- **Exemplo:** `simplicio-video toonflow status --json`

### MoneyPrinterTurbo (`moneyprinter`)

[harry0703/MoneyPrinterTurbo](https://github.com/harry0703/MoneyPrinterTurbo) · MIT

Gera um vídeo curto a partir de um tema: roteiro por LLM, voz sintetizada e trechos de vídeo de banco de estoque ou do seu material. Precisa de Python 3.11 ou mais novo. Os serviços de terceiros que ele usa (LLM, voz e estoque) têm termos próprios, que não foram revisados aqui.

- **Comando:** `moneyprinter clone [pasta]`, `setup` (venv próprio; copia o `config.toml` de exemplo, sem chave), `serve [--webui] [--api] [--lan] [--host H] [--api-port N]` (só em 127.0.0.1, a menos que `--lan`), `generate --script ... --material ... --out ...` (sobe a API por trás e devolve o MP4 com hash), `run [--yes] --out DIR -- <flags do upstream>`, `status` (diz se cada chave está preenchida, nunca o valor) e `where`.
- **`run`:** repassa flags do `cli.py` do upstream numa lista fechada (roteiro, etapas, legendas, música, lote) e copia o MP4 com sha256. O que gasta (LLM, fonte paga, voz de rede, `--confirm-*-charge`) só roda no terminal e só com `--yes`.
- **Chaves:** as suas, no `config.toml` ou na WebUI. O comando nunca imprime o valor.
- **MCP:** `where`, `clone` (pasta padrão) e `status`. `generate` e `run` viram tarefa em segundo plano (acompanhe com `video.jobs`), só no modo livre: roteiro seu, material local, voz Edge ou silenciosa e `--out` absoluto. O MP4 volta copiado para a pasta de saída, com sha256.
- **Só no terminal:** `setup`, `serve`, roteiro por LLM, fonte de material paga ou online, `--confirm-*-charge`, lote (arquivo de tarefas) e `clone` com pasta.
- **Exemplo:** `simplicio-video moneyprinter run --out out/ -- --video-script "Texto do vídeo." --video-source local --video-materials clip.mp4 --voice-name pt-BR-FranciscaNeural-Female`

### match-cut (`matchcut`)

[Sac-Y/match-cut](https://github.com/Sac-Y/match-cut) · MIT

Skill de agente (Claude Code ou Codex) para filmes de produto no estilo match-cut relay. O motor baixa o commit fixado, mostra onde fica o `SKILL.md` e roda, e só eles, sete scripts locais do skill (music, mix, qc, render, assemble, align, undot) num venv próprio. Antes de rodar, confere o sha256 do script e do `common.py`, e valida o `montage.json` que os scripts leem. O motor não chama o Renoise; usar o skill exige login no Renoise com a sua conta e gasta créditos pagos.

- **Comando:** `matchcut clone [pasta]`, `where`, `status`, `setup` (cria o venv, confere o sha256 do `requirements.txt` e instala as dependências pelo pip sem hash, porque o upstream não tem lock; precisa de rede) e `run SCRIPT [--forcar] [--bruto] [-- argumentos do script]`. `--forcar`, que sobrescreve saída que já existe, fica só no terminal.
- **MCP:** `where`, `status` e `run SCRIPT ...`, com os argumentos como lista. Todo caminho tem de ser absoluto; saída que já existe nunca é sobrescrita; nada é gravado dentro do checkout nem em pasta do sistema.
- **Só no terminal:** `clone`, `setup` e `--forcar`.
- **Exemplo:** `simplicio-video matchcut run music -- analyze faixa.wav --bpm 150 --json compassos.json`

### instagram-agent-skill (`instagram`)

[Jakeschincariol/instagram-agent-skill](https://github.com/Jakeschincariol/instagram-agent-skill) · MIT (Jake Schincariol)

Treze skills de agente para Instagram (Reels, legendas e outras) e seis scripts locais da biblioteca padrão: `hookscore`, `beats`, `caption`, `humanize`, `detect` e `swipe`. O motor roda só esses scripts, depois de conferir o sha256 de cada um. As skills são prompts, não código, e nada disso posta. As heurísticas são em inglês: em português elas pontuam mal ou ignoram.

- **Comando:** `instagram clone`, `skills`, `skill NOME` (o corpo do `SKILL.md` de uma skill listada), `where [--skills]`, `status`, `run <ferramenta> -- <argumentos>`.
- **MCP (só leitura):** `skills`, `skill NOME` (o texto do `SKILL.md` vem em `untrusted_conteudo`, como texto de terceiros, cortado em 64 KiB com `truncado`; o nome tem de ser um de `skills`, nunca um caminho), `where`, `status`, e `run` de `hookscore`, `beats`, `caption`, `detect` e `humanize`, com o texto no parâmetro `texto`. A saída volta marcada como texto de terceiros.
- **Só no terminal:** `clone` (baixa código de terceiros da rede), `swipe` e a gravação em arquivo (`--out`).
- **Exemplo:** `simplicio-video instagram run caption -- legenda.txt`

### social-media-research-skills (`social-research`)

[wesleysimplicio/social-media-research-skills](https://github.com/wesleysimplicio/social-media-research-skills) · MIT

Treze skills de agente para pesquisa em redes sociais: posts fora da curva, mineração de comentários, pesquisa de público, raio-x de concorrentes e criadores, bibliotecas de anúncios, prospecção de influenciadores, transcrições e tendências, em TikTok, Instagram, YouTube, Reddit, X, LinkedIn e outras. As skills são prompts que chamam a API do [ScrapeCreators](https://scrapecreators.com) (paga, com a sua chave) a partir do agente. O motor só baixa o commit fixado (`64ba7b4`), lista as skills e devolve o corpo de uma delas depois de conferir o commit e o sha256 do arquivo. Não roda script, não chama o ScrapeCreators, não pede chave e não posta.

- **Comando:** `social-research clone [pasta]`, `skills`, `skill NOME` (o corpo do `SKILL.md` de uma skill listada, até 64 KiB, como texto de terceiros), `where [--skills]`, `status` (o sha256 de cada `SKILL.md`). `--json` em todos, menos no `clone`.
- **Checkout:** `SOCIAL_RESEARCH_DIR` ou `SIMPLICIO_TOOLS_DIR/social_research`.
- **MCP (só leitura):** `video.social-research` com `acao` = `skills`, `skill` (com `nome`), `where` ou `status`. O `clone` é só do terminal.
- **Para usar as skills no seu agente:** copie a pasta que `simplicio-video social-research where --skills` mostra para a pasta de skills do agente e configure a chave do ScrapeCreators como o README do upstream manda.
- **Exemplo:** `simplicio-video social-research skill outlier-post-finder`

### last30days-skill (`last30days`)

[mvanhorn/last30days-skill](https://github.com/mvanhorn/last30days-skill) · MIT

Uma skill de agente que pesquisa o que se disse de um tema nos últimos 30 dias em Reddit, X, YouTube, TikTok, Hacker News, Polymarket, GitHub e na web, ordenado por engajamento. O motor só baixa o commit fixado (`07021dc`) e devolve o corpo do `skills/last30days/SKILL.md` depois de conferir o commit e o sha256 do arquivo. Não roda os scripts do upstream, não lê cookies do navegador, não pede nem repassa chave e não posta.

- **Comando:** `last30days clone [pasta]`, `skill` (o corpo do `SKILL.md`, até 64 KiB, como texto de terceiros), `where [--skills]`, `status` (o sha256 do `SKILL.md`). `--json` em todos, menos no `clone`.
- **Checkout:** `LAST30DAYS_DIR` ou `SIMPLICIO_TOOLS_DIR/last30days`.
- **MCP (só leitura):** `video.last30days` com `acao` = `skill`, `where` ou `status`. O `clone` é só do terminal.
- **A skill em si:** rodada pelo Claude Code (`/plugin install last30days` ou a pasta que `simplicio-video last30days where --skills` mostra), pede Python 3.12+, pode ler os cookies do seu navegador para o X e chama terceiros pagos (ScrapeCreators, Perplexity e outros) com as suas chaves. Isso acontece no seu agente, não no motor.
- **Exemplo:** `simplicio-video last30days skill`

### VoiceStudio (`voicestudio`)

[debpalash/VoiceStudio](https://github.com/debpalash/VoiceStudio) · AGPL-3.0; o motor só fala com o app por HTTP local e nunca o vendoriza.

App local de voz: TTS, transcrição, clonagem e desenho de vozes, e dublagem. Quem instala e abre o app é você. O motor fala com ele por HTTP local, por padrão em `http://127.0.0.1:3900`; as variáveis `VOICESTUDIO_URL` e `OMNIVOICE_URL` apontam outra base. O envio de arquivo (`dub create`, `transcribe`, `clone`) só vai a um app em loopback (127.0.0.0/8, ::1 ou localhost).

- **Comando:** `voicestudio status`, `voices`, `languages`, `personalities`, `tts`, `transcribe`, `clone`, `describe`, `design`, `dub create VIDEO`, `dub-export --job ID --lang LANG -o SAIDA.mp4` e `mcp`.
- **`dub create`:** sobe o vídeo (ou áudio, com `--audio`) ao app e cria o job de dublagem. Não transcreve, não traduz e não gera a voz; isso roda no app.
- **`dub-export`:** exporta um job de dublagem que já existe no app, com música e efeitos, desde que o job tenha sido feito com a separação de fundo ligada no app (sem ela, o app responde 409 e o comando recusa). Não gera a voz.
- **Resultado:** o comando devolve o JSON do resultado (`result`), o código de saída (`rc`) e, se falhar, `error`.
- **Consentimento:** clonar ou dublar a voz de uma pessoa real só com o consentimento dela registrado, como manda o `AGENTS.md`. O comando não confere isso.
- **MCP:** `video.voicestudio`, com os mesmos subcomandos. As saídas de `tts` e `dub-export` (`--out`/`-o`) são obrigatórias, absolutas, de arquivo novo, numa pasta que já existe e fora de pastas do sistema e ocultas. Os arquivos de entrada de `dub create`, `transcribe` e `clone` são caminhos absolutos de mídia.
- **Só no terminal:** nada, no main.
- **Exemplo:** `simplicio-video voicestudio status`

### video-use (`edit`)

[browser-use/video-use](https://github.com/browser-use/video-use) · MIT

Edição de qualquer MP4 por EDL: cortes palavra a palavra, legendas, sobreposições, revisão por filmstrip e correção de cor. O agente escreve a decisão no `edl.json`, e o ffmpeg executa. A transcrição local usa faster-whisper.

- **Comando:** `edit setup`, `transcribe`, `transcribe-batch DIR` (só no terminal; ElevenLabs Scribe, terceiro pago), `pack`, `render`, `verify`, `grade` (`--analyze`, `--preset`, `--filter`, `--list-presets`).
- **MCP:** todos os subcomandos, exceto `transcribe-batch`. Em `transcribe`, `render`, `verify` e `grade`, as saídas (`-o`, `--out`, `--output`) precisam ser caminho absoluto. Em `grade`, `--filter` aceita só filtros de cor (eq, curves, colorbalance, hue, lut, lutrgb, lutyuv, colorchannelmixer, vibrance).
- **Só no terminal:** `transcribe-batch`.
- **Exemplo:** `simplicio-video edit render edit/edl.json -o out/final.raw.mp4`

### rea-video (`rea-video`)

[JuneYaooo/rea-video](https://github.com/JuneYaooo/rea-video) · MIT, declarada no `pyproject.toml`; o commit fixado não traz arquivo LICENSE

Analisa um vídeo de referência plano a plano (filmagem real, IA, 3D ou render de código) e planeja o remake. Analisa um arquivo que você já tem: não baixa vídeo. Precisa de ffmpeg e de Python 3.10 ou mais novo.

- **Comando:** `rea-video clone`, `setup`, `where`, `status` e o repasse de qualquer comando do upstream (`decompose`, `summary`, `review`, `apply-review`, `remake-plan` e outros).
- **Rede:** sem `--vlm`, só o download de modelos. Com `--vlm`, os quadros vão ao provedor de modelo de visão que você configura, um terceiro.
- **MCP:** `where`, `status`, `clone` (pasta padrão), `summary`, `probe`, `tiles` (com `-o` novo), `review`, `apply-review` e `remake-plan`, com lista fechada de flags e caminhos absolutos. `decompose` e `stems` viram tarefa em segundo plano (acompanhe com `video.jobs`); o `decompose` sempre roda sem o modelo de visão. Em `review` e `apply-review`, quem olha os quadros é o agente que chama, então nenhum quadro vai a terceiros.
- **Só no terminal:** `setup` (instala dependências), `remake-run` (gasta), `capsule-draft` (roda código de uma pasta), `prefs`, `correct`, `memory`, `eval`, `capsule`, `assemble`, `--vlm`, `--env-file` e `clone` com pasta.
- **Exemplo:** `simplicio-video rea-video decompose ref.mp4 -o out/ref --no-stems`

### video-to-skill (`video-to-skill`)

[brenoepics/video-to-skill](https://github.com/brenoepics/video-to-skill) · MIT, de Breno Epics · fixado na tag v0.3.0, commit `c1a1b90`

**Novo.** Transforma um vídeo numa skill de agente instalável: um tutorial vira passos numerados, cada um citando o segundo do vídeo e o quadro de onde veio, empacotados num `SKILL.md` que um agente carrega. O upstream tem duas partes. Um extrator local em Rust, o `vts-extract`, faz o trabalho determinístico (separar o áudio, detectar planos, quadros-chave, transcrição com tempo por palavra quando os modelos de voz dele estão instalados, compilar o pacote da skill, dobrar um segundo vídeo numa skill que já existe, instalar para todos os agentes da máquina). O agente faz a leitura: olha os quadros-chave e escreve o `procedure.json` que o compilador transforma no pacote. O motor fixa o commit da skill do upstream e a release do extrator, e só roda o extrator como programa separado, nunca importado.

```bash
simplicio-video video-to-skill clone                          # o commit fixado: SKILL.md e referências (precisa de rede)
simplicio-video video-to-skill setup                          # o extrator: o do PATH só se disser exatamente 0.3.0; senão o asset fixado da release
simplicio-video video-to-skill check --print-downloads        # só leitura: o que o upstream baixaria, com URL e sha256
mkdir -p out/excel                                            # a pasta-mãe precisa existir (como em toda trilha)
simplicio-video video-to-skill extract tutorial.mp4 --out out/excel/bundle     # arquivo local; pasta nova ou vazia
simplicio-video video-to-skill frame-at --bundle out/excel/bundle 0:54 1:12    # quadros nesses instantes, dentro do bundle
simplicio-video video-to-skill compile --bundle out/excel/bundle --ir out/excel/bundle/procedure.json --out out/excel/excel-soma
simplicio-video video-to-skill install --package out/excel/excel-soma          # mostra o plano e não grava; para instalar, digite você o --yes
```

- **Fluxo do setup.** O `setup` baixa o asset da sua plataforma na release do upstream no GitHub (`linux-x86_64`, `macos-arm64`, `macos-x86_64`, `windows-x86_64`), confere o sha256 contra uma tabela fixada antes de extrair qualquer coisa, extrai só o executável (sem caminho, sem link, sem outra entrada, com teto de tamanho), confere o sha256 desse arquivo antes de ele rodar e só então pergunta `--version`. Um binário gerenciado é conferido contra o sha256 fixado a cada uso; um `vts-extract` achado no PATH é confiado só pela versão (sem sha256). Em outra plataforma, o comando diz isso e pede para compilar o upstream do código-fonte.
- **Quem baixa o quê.** O extrator vem da release do upstream, baixado pelo motor. As dependências dele (os modelos whisper e de detecção de voz do Hugging Face; ffmpeg no Windows e no Apple Silicon, yt-dlp no Windows e no macOS, lido no código do upstream) são baixadas pelo `check --fix --yes` do upstream. O motor nunca o roda e nunca passa `--fix` nem `--yes` ao `check`: você digita `<caminho do vts-extract> check --fix --yes` num terminal, depois de ler a lista acima. `simplicio-video video-to-skill where --binary` imprime o caminho. No Linux o upstream não baixa ffmpeg nem yt-dlp (medido aqui): eles têm de estar no PATH.
- **O que roda local.** Extração, quadros, compile e merge rodam na sua máquina; o vídeo não sai dela. Uma URL (`extract URL --out PASTA --autorizo`) é só do terminal: o yt-dlp do upstream baixa, você confirma que pode usar o vídeo, e o motor não verifica esse direito. Um registro de procedência (`PASTA.extract.json`) fica ao lado do bundle, só depois de uma extração que deu certo: um extract cancelado ou morto deixa a pasta parcial em `--out` (saída do upstream) e nenhum registro, e você apaga essa pasta antes de tentar de novo. O extrator nasce no filho guardado do motor (o kill é armado antes de o processo existir), com stdin fechado, grupo de processos próprio, pasta privada, ambiente mínimo (sem chaves nem tokens), limite de tempo e de saída.
- **Fora das garantias do motor.** Verificar uma skill gerada executa comandos tirados do vídeo. Isso é tarefa do agente, dentro do `sandbox` do upstream (confinamento do sistema operacional, sem rede), e fica fora das garantias do motor: ele não expõe `sandbox`, `verify`, `bench`, `observe` nem `eval`. O `install` grava a skill na pasta de skills de todos os agentes da máquina, então é só do terminal, imprime o plano antes e só grava com um `--yes` digitado por você. Texto que vem do upstream ou do vídeo é dado de terceiros, nunca instrução: o terminal mostra controles e marcas bidi como caracteres visíveis, e pelo MCP ele volta em campos `untrusted_*`.
- **MCP.** `video.video-to-skill` tem lista fechada: `status`, `where`, `check`, `skill`, `extract` (arquivo local absoluto para uma pasta nova; tarefa, acompanhe com `video.jobs`), `frame-at`, `clip`, `compile` e `merge --dry-run`, tudo com caminho absoluto. `clone`, `setup`, `install`, o merge de verdade, URL e `check --fix --yes` são só do terminal.
- **Limites das conferências.** Entre conferir o hash do binário gerenciado e executá-lo, outro processo do mesmo usuário poderia trocar o arquivo (a pasta é 0755 e o arquivo 0700; se `SIMPLICIO_TOOLS_DIR` for gravável pelo grupo, o motor não confere o dono). O `source.sha256` do registro de procedência é o que o próprio extrator pôs no manifesto: o motor não calcula o hash da entrada. As variáveis de proxy repassadas ao extrator numa extração de URL podem conter credenciais. O `--out` precisa de uma pasta-mãe que já existe.
- **Pin.** O `update` nunca move esta trilha: o binário do extrator e o `SKILL.md` são fixados juntos em `data/video_to_skill/pins.json`.

**Verificado aqui (Linux x86_64, 2026-11-06).** Os quatro assets da release v0.3.0 foram baixados e cada sha256 é igual ao que o upstream publica ao lado; a tabela de pins guarda também o sha256 de cada executável e do `SKILL.md` e das referências fixados, conferidos contra um clone do commit fixado. `clone`, `setup` (download real de 3,4 MB pelo proxy), `status`, `where`, `check`, `skill`, `extract` de um clipe sintético de 4 s com um tom e o texto `=SUM(A1:A3)`, `frame-at`, `clip`, `compile` (um passo, de um IR escrito à mão), `merge --dry-run` e um merge de verdade, e `install` (plano, depois `--yes`, num home temporário com um `~/.claude/skills` de mentira) rodaram contra o binário real da v0.3.0. As funções do MCP rodaram em processo sobre o mesmo bundle. Os testes offline usam um extrator falso e cobrem a tabela de pins, a extração segura (traversal, links, tamanho), sha256 errado, versão errada, a lista fechada do MCP, a tarefa, os sinais e o ambiente.

**NÃO VERIFICADO.** Um tutorial real (o clipe era sintético, 4 s, um plano) e a qualidade de uma skill escrita a partir de um. A transcrição: os modelos de voz não foram baixados aqui, então a extração rodou sem fala e a linha do tempo diz isso. O extrator da v0.3.0 não tem OCR nem o comando `text` (vieram em commits posteriores do upstream), então o texto na tela é lido pelo agente nos quadros. A atestação SLSA dos arquivos da release (pede o GitHub CLI e um token; a conferência aqui foi recusada com HTTP 403). O `sandbox` e o `verify` do upstream (não rodados). O `check --fix --yes` (não rodado: só você o roda). O `extract` de URL. Windows e macOS (a tabela de pins tem os assets deles; nada rodou lá).

### yt-dlp (`media fetch`)

[yt-dlp/yt-dlp](https://github.com/yt-dlp/yt-dlp) · Unlicense

Baixa um vídeo público para um MP4 local e grava `OUT.fetch.json` ao lado, com URL, sha256, versão do yt-dlp e hora. Roda num venv próprio, com o wheel conferido por sha256. Não entra em conta, não lê cookies do navegador e não baixa playlist.

- **Comando:** `media fetch <URL> --info` (só metadados: título, duração, autor, licença, formatos e idiomas de legenda; não baixa nada e não precisa de `--autorizo`); `media fetch <URL> -o saida.mp4 --autorizo`, com `--max-mb`, `--timeout`, `--subs LANG [--auto-subs]` (legendas do criador, em `.srt`), `--section INICIO-FIM` (só esse trecho, em segundos) e `--audio-only` (sai `.m4a` ou `.wav`).
- **`--autorizo`:** obrigatório para baixar. Você confirma que pode usar o vídeo; o motor não verifica isso, e plataformas como o Instagram têm regras próprias de download.
- **MCP:** `video.media` faz `fetch` só com `--autorizo`, e o agente só passa a flag depois que você aprova aquela URL no chat. `--info` não precisa de aprovação.
- **Só no terminal:** nada, no main. Pelo MCP, a aprovação da URL no chat é o que segura o download.
- **Exemplo:** `simplicio-video media fetch <URL> --info`

### TinyFish CLI (`busca`)

[@tiny-fish/cli](https://www.npmjs.com/package/@tiny-fish/cli) · licença não declarada no pacote (lido em 2026-11-05, versão 0.57.0). Você instala com `npm install -g @tiny-fish/cli@0.57.0` (o pacote pede Node 24 ou mais novo); o motor nunca instala.

Pesquisa na web e leitura de uma página, para achar referência e fatos públicos a conferir. Cada resultado sai com fonte e data, e há um teto diário de chamadas (20 por padrão). Não chama LLM e não decide o que é verdade. A busca não substitui a coleta do cliente.

- **Comando:** `busca consulta "<texto>" [--idioma pt] [--limite N]`, `busca pagina <url>`, `busca status`, `busca log`.
- **Privacidade:** a consulta e a URL vão a um terceiro (TinyFish). O motor recusa chave e token sempre, e e-mail, CPF e CNPJ a menos que o terminal diga `--permitir-dado-pessoal`.
- **MCP:** `consulta`, `pagina`, `status` e `log`, com o mesmo teto. Sem `--atualizar` e sem `--permitir-dado-pessoal`.
- **Só no terminal:** `--atualizar` (gasta uma chamada para ignorar o cache) e `--permitir-dado-pessoal`.
- **Exemplo:** `simplicio-video busca consulta "datas comemorativas marketing" --idioma pt --limite 5`

## Trilhas externas e licenças

Cada versão está fixada em [`src/simplicio_video/tools.py`](src/simplicio_video/tools.py). `simplicio-video tools` lista todas. O motor nunca vendoriza nem importa essas trilhas, e o render determinístico não depende de nenhuma delas.

`simplicio-video update` (em toda release que instala) leva cada trilha ao que o upstream diz ser o mais novo; o pin é o ponto de partida, e é o que `--pin` mantém. O que foi resolvido fica registrado em `tools.lock.json` (em `$SIMPLICIO_VIDEO_DATA`), e `tools` e `doctor` mostram isso. Uma trilha cuja atualização falha fica com o checkout que já tem e é reportada; a atualização do pacote segue. Um override `SIMPLICIO_<NOME>_REF` sempre vence e nunca é atualizado.

| Trilha | Comando | Versão fixada | `update` segue | Licença |
|---|---|---|---|---|
| OpenMontage | `montage` | commit `9327439` | default branch | AGPL-3.0 |
| OpenCut | `opencut` | commit `cf5e79e` | default branch | MIT |
| Hypit | `clone` | npm `0.3.1` | última versão npm | Licença Hypit (Apache-2.0 modificada); sem redistribuição comercial |
| Toonflow | `toonflow` | commit `d2e94ac` | default branch | MIT |
| MoneyPrinterTurbo | `moneyprinter` | commit `4b7b965` | default branch | MIT |
| match-cut | `matchcut` | commit `b51c98f` | default branch | MIT. Uso exige login e créditos na Renoise |
| instagram-agent-skill | `instagram` | commit `d03c56b` | default branch | MIT (Jake Schincariol). O script só roda depois que o sha256 bate com o fixado |
| TinyFish CLI | `busca` | npm `0.57.0` | última versão npm | Não declarada no pacote |
| VoiceStudio | `voicestudio` | commit `beeaae08` | default branch | AGPL-3.0. Usado só por HTTP local |
| video-use | `edit` | commit `b877063` | default branch | MIT |
| video-to-skill | `video-to-skill` | commit `c1a1b90` (tag v0.3.0); extrator `vts-extract` v0.3.0, sha256 conferido por plataforma | nenhum (fixado: o extrator e o `SKILL.md` são fixados juntos) | MIT (Breno Epics). O binário do extrator não é empacotado: o `setup` baixa |
| yt-dlp | `media fetch` | PyPI `2026.10.26`, sha256 conferido | última release do PyPI, sha256 conferido | Unlicense |
| rea-video | `rea-video` | commit `36e02dd` | default branch | MIT, declarada no `pyproject.toml`; o commit fixado não traz arquivo LICENSE |

**Lacunas conhecidas:**
- Limpeza de áudio: em PR, ainda não está no main.
- Separação de voz e fundo: não há comando.
- Dublagem com fundo preservado: a dublagem em si roda no app VoiceStudio; `voicestudio dub create` sobe o vídeo e `dub-export` exporta o job pronto.

### rea-video (`rea-video`)

```bash
simplicio-video rea-video clone                                     # baixa o commit fixado para o cache de ferramentas
simplicio-video rea-video setup                                     # venv próprio com o checkout (pip; precisa de rede)
simplicio-video rea-video decompose ref.mp4 -o out/ref --no-stems   # qualquer comando do upstream, na pasta em que você está
simplicio-video rea-video status                                    # checkout, venv, OCR, ffmpeg; chaves VLM só como definida ou não
```

Toda palavra que não é um comando próprio desta trilha vai sem mudança para o `rea-video` do venv, inclusive as flags do upstream (`--env-file`). A ajuda do próprio upstream (`simplicio-video rea-video decompose --help`) está em chinês.

O `decompose` grava `breakdown.json`, `report.html`, `report.md`, `storyboard.jpg` e uma pasta de planos na pasta do `-o`. Cada plano recebe um veredito: real, vídeo de IA, 3D, render de código ou misto.

- **Rede.** Sem `--vlm`, a única rede é o download de modelos: um modelo de separação de voz de cerca de 67 MB do GitHub (`--no-stems` pula) e um detector de rosto pequeno (sem ele, o upstream cai para Haar). Os modelos vão para `REA_VIDEO_MODELS`, que por padrão fica na pasta de dados da trilha.
- **O modelo de visão é um terceiro.** Com `--vlm`, até 60 planos vão ao provedor que você configurar (`REA_VLM_BASE_URL` e `REA_VLM_API_KEY`, ou os nomes `VIDEO_ANALYSIS_*` e `GEMINI3_*`). Cada plano vai num clipe de até 12 segundos em 480p, e o vídeo inteiro vai em 480p com áudio. Sem chave, o upstream avisa e segue sem o modelo.
- **Um `.env` da pasta em que você roda é lido.** O upstream carrega sozinho, com os endereços e as chaves dele. Rode as análises numa pasta sem `.env` de outro projeto; o `status` avisa quando há um.
- **O OCR precisa de um Python compatível.** Legendas e textos na tela usam o `rapidocr-onnxruntime`, que não tem versão para todo Python. Aqui o Python 3.13 não instalou; o Python 3.11.18 instalou. Para ter OCR, apague a pasta venv da pasta de dados e rode `REA_VIDEO_PYTHON=python3.11 simplicio-video rea-video setup`. Um venv existente é mantido, por isso a pasta precisa sair antes. Sem OCR, o `setup` instala o núcleo e avisa.
- **Código da pasta do capsule-cinema.** `remake-run` e `capsule-draft` importam e executam código da pasta do capsule-cinema que você indicar. Indique só uma pasta de confiança.
- **Estado.** Memória e preferências vão para `home/` na pasta de dados (`~/.simplicio-video/rea-video-data`), não para `~/.rea-video`.
- **Requisitos.** ffmpeg no PATH e Python 3.10 ou mais novo. `clone` e `setup` precisam de rede e recusam `SIMPLICIO_OFFLINE=1`. O `setup` instala as dependências pelo pip sem hash, porque o upstream não tem arquivo de lock.
- **MCP.** `video.rea-video` aceita `where`, `status` e `clone` (na pasta padrão). `setup` e a análise rodam no terminal: uma análise leva minutos e pode gastar chamadas do modelo de visão.

Testado aqui, em Linux: clone no commit fixado; `setup` no Python 3.13 (só o núcleo) e no 3.11 (núcleo e OCR); o repasse de `decompose`, `probe`, `summary` e `memory`; uma análise padrão com o download de 67 MB; `--vlm` sem chave, que avisa e segue; a tool MCP listada pelo stdio. Não verificado: vídeo real, chamada real a um modelo de visão, os números de acurácia do README do upstream, `remake-run` e `capsule-draft`, OCR em japonês, Windows e macOS.

### Skills de Instagram (`instagram`)

```bash
simplicio-video instagram clone                                  # baixa o commit fixado d03c56b para o cache de ferramentas (único passo que usa a rede)
simplicio-video instagram skills                                 # as 13 skills: nome e descrição
simplicio-video instagram run hookscore -- --hook 'I lost $18,000 because of one missing contract.'
simplicio-video instagram run beats -- roteiro.txt --target 30   # roteiro vira folha de batidas com tempo
simplicio-video instagram run caption -- legenda.txt             # linter de legenda
simplicio-video instagram where --skills                         # a pasta das skills (para copiar para o seu agente)
simplicio-video instagram status                                 # commit do checkout e sha256 de cada script
```

**O que é.** [Jakeschincariol/instagram-agent-skill](https://github.com/Jakeschincariol/instagram-agent-skill), de Jake Schincariol, MIT, fixado no commit `d03c56b` (o último do upstream, de 2026-09-13; lido aqui em 2026-11-04). São treze skills de Claude (`ig-reel`, `ig-viral`, `ig-caption`, `ig-carousel`, `ig-story`, `ig-profile`, `ig-plan`, `ig-human`, `ig-comment`, `ig-reply`, `ig-dm`, `ig-repurpose`, `ig-audit`), um `templates/voice.md` e seis scripts Python que só usam a biblioteca padrão: `hookscore` (pontua um gancho), `beats` (roteiro vira folha de batidas com tempo), `caption` (linter de legenda), `humanize` (tira caracteres invisíveis, tipografia e palavras de enchimento), `detect` (painel de cinco checagens) e `swipe` (ranking de reels fora da curva a partir de um TSV). As skills são prompts para um agente, não código.

**Não posta.** O upstream diz o mesmo: "These skills write. You post." O motor não posta, não publica, não faz login e não pede chave; o `clone` é o único subcomando que usa a rede.

**Subcomandos.** `clone [dir]` (o commit fixado, em `INSTAGRAM_DIR` ou `SIMPLICIO_TOOLS_DIR/instagram`; recusa `SIMPLICIO_OFFLINE=1`), `where`, `status`, `skills` (a descrição de cada `SKILL.md` é texto de terceiros, mostrada como dado) e `run <ferramenta> [--forcar] [-- argumentos do script]`. A ferramenta é uma entre `hookscore`, `beats`, `caption`, `humanize`, `detect`, `swipe`, uma lista fechada: caminho nunca é aceito. Cada opção do script é conferida na lista da própria ferramenta (abreviação como `--ou` é recusada); por isso os argumentos do script vão depois de `--`, e o `--json` do script funciona.

**O que o `run` confere e limita.**
- O commit do checkout e o sha256 do script, dos arquivos que ele lê (`slop.json`, `hooks.json`) e dos que ele importa (o `swipe` importa o `hookscore.py`). Arquivo diferente é recusado. O que roda é uma cópia privada dos bytes conferidos.
- O script roda como `python -I -B -X utf8`, por lista de argumentos e sem shell, na pasta em que você está, só com `PATH`, `HOME`, `LANG`, `LC_ALL`, `PYTHONIOENCODING`, `TMP`, `TEMP` e `SYSTEMROOT` (nenhuma chave), por no máximo 30 s e 2 MB de saída, com no máximo 1 MiB por arquivo de entrada ou pela entrada padrão.
- `humanize -o/--out` e `swipe --out` só existem no terminal. O motor não sobrescreve arquivo que existe, a menos que você passe `--forcar` antes do `--`, e nunca grava dentro do checkout, em pasta do sistema (`/etc`, `/usr`...) nem em pasta oculta do seu home (`~/.ssh`, `~/.config`, `~/.claude`...); os links são resolvidos antes.
- O arquivo de entrada é aberto uma vez, conferido com `fstat` nesse mesmo descritor (só arquivo comum; um named pipe não trava) e lido até 1 MiB + 1; o script recebe uma cópia privada desses mesmos bytes.
- Se o motor recebe SIGTERM ou SIGHUP (terminal fechado, host do MCP encerrando, timeout de um agente), ele mata o grupo de processos do script e apaga a pasta privada. No POSIX o script ainda tem `RLIMIT_CPU` de 35 s do kernel, então um script que gasta CPU termina mesmo com o motor morto de vez. Ele limita tempo de CPU, não tempo de relógio, e não existe no Windows (lá só valem a morte aos 30 s e o tratamento de sinal).
- No terminal, o texto do script aparece com ESC, controles, bidi e zero-width trocados por marcas visíveis (`␛`, `<U+202E>`), porque ele pode vir de terceiros. `--bruto`, flag do motor antes do `--`, imprime cru. Para guardar o texto limpo do `humanize`, use `-o` (o próprio script grava o arquivo) ou `--bruto`.
- A guarda do `--out` compara nomes de pasta sem diferenciar maiúsculas no macOS e no Windows (e a normalização Unicode no macOS) e também recusa as pastas de início automático (`~/Library/LaunchAgents`, `~/Library/LaunchDaemons`, a pasta `Startup` do Menu Iniciar do Windows). UNVERIFIED: aqui não há macOS nem Windows.
- Depois que o `simplicio-video update` leva a trilha a um commit mais novo do upstream, o `run` recusa o script cujo sha256 mudou, até a tabela de `src/simplicio_video/instagram.py` ser auditada de novo. `update --pin` volta ao commit fixado.

**As heurísticas são em inglês.** As expressões regulares, o léxico de palavras (`slop.json`) e as 26 fórmulas de gancho do upstream são em inglês. O autor mediu o `hookscore` em 74 ganchos de YouTube Shorts: AUC 0,83 para pegar ganchos escritos para serem ruins, e 0,56 para separar os acertos de um criador dos erros do mesmo criador (0,50 é cara ou coroa). Rodado aqui, com os mesmos scripts fixados:

| Entrada | Resultado |
|---|---|
| `I lost $18,000 because of one missing contract.` | `hookscore` 81,4 STRONG |
| `Eu perdi R$ 18.000 por causa de um contrato que faltava.` (a mesma frase) | 59,6 OK; ele diz "third person, nobody in the room" para uma frase em primeira pessoa |
| `Hey guys, today I wanted to talk about content strategy` | 9,6 WEAK, com o impeditivo "Greeting" |
| `Oi pessoal, hoje eu quero falar sobre estratégia de conteúdo` (a mesma saudação) | 30,0 WEAK, sem impeditivo nenhum |
| Legenda terminando em "Comment CLAUSE" / "Comente CLÁUSULA" | o `caption` acha a chamada para ação na primeira e diz "no call to action" na segunda |
| Rascunho em português cheio de clichês | `detect`: "0 stock terms"; o `humanize` tira o caractere invisível e o travessão, mas nenhuma palavra |

O `beats` conta o tempo do português pelo número de palavras a 165 palavras por minuto (padrão do inglês; mude com `--wpm`). Em português, trate as notas como indício grosseiro, não como veredito.

**Copiar as skills para o seu agente.** O motor não copia (`simplicio-video install` é só da skill deste projeto). O comando do próprio upstream, apontado para o checkout:

```bash
mkdir -p ~/.claude/skills
cp -r "$(simplicio-video instagram where --skills)"/ig-* ~/.claude/skills/
```

O upstream também pede para copiar `templates/voice.md` para `~/.claude/instagram/voice.md` e preencher: todas as skills leem esse arquivo.

**Depois de copiar as skills, nenhuma garantia do motor vale.** Com as skills em `~/.claude/skills/`, o seu agente roda os scripts direto, como mandam os `SKILL.md` do upstream (`python3 swipe.py captured.tsv --out ...`, `python3 humanize.py rascunho.txt -o ...`): sem conferência de sha256, sem `-I`, sem ambiente fechado (as suas chaves ficam visíveis para o script), sem limite de 30 s nem de 2 MB, sem a guarda do `--out` e sem tratamento de `SIGTERM`. A skill `ig-viral` do upstream também manda o agente usar o seu navegador já logado no Instagram (extensão ou computer use) e o `yt-dlp` para ler YouTube Shorts: isso é comportamento da skill, não do motor. O caminho que o upstream sugere, `--out ~/.claude/instagram/swipe.md`, é um que o `instagram run` recusa (pasta oculta do home). Quem quer as garantias do motor usa `instagram run`; quem copia as skills assume o risco do que o agente executa. A frase "não posta" acima vale para o motor, não para um agente que segue essas skills.

**MCP.** `video.instagram` aceita `skills`, `where`, `status` e `run` de `hookscore`, `beats`, `caption`, `detect` e `humanize`. O texto vai no parâmetro `texto` e entra no script pela entrada padrão; não há caminho de arquivo, nem `--out`, nem `--lexicon`, e o texto do script volta em `saida` com o aviso de que é texto de terceiros e heurística em inglês. `clone` e `swipe` são só do terminal: o agente não baixa código por conta própria.

Testado aqui, em Linux: `clone` do commit fixado; os oito sha256 da tabela contra esse clone; os seis scripts pelo `run` com entradas em inglês e em português (os números acima); `humanize -o` e `swipe --out` gravando arquivo novo e recusando arquivo que existe, `/etc` e o checkout; a tool MCP pelo stdio (31 tools, um gancho pontuado, `--out` recusado); uma suíte com argumentos hostis, script adulterado, outro commit, saída gigante, tempo esgotado, ambiente fechado e `SKILL.md` hostil. **UNVERIFIED:** Windows e macOS; um agente usando as skills de verdade (nenhum foi rodado aqui, então a qualidade das skills, em inglês ou em português, não foi avaliada); os números de AUC do autor (são dele, não foram reproduzidos); a instalação por `/plugin` do upstream; commits depois de 2026-11-04.

## Referências

- [docs/reference/cli.md](docs/reference/cli.md): todos os comandos e flags.
- [docs/reference/mcp-tools.md](docs/reference/mcp-tools.md): tools MCP.
- [CHANGELOG.md](CHANGELOG.md): mudanças por versão.
- [AGENTS.md](AGENTS.md): regras de operação para agentes.
- [Decisões (ADRs)](docs/decisoes/): visão do plugin, CLI e contrato, fluxo 100% script.
