# simplicio-videos

> Um motor de vídeo determinístico, guiado por agentes: um contrato YAML entra, um MP4 sai, e há um conjunto de ferramentas de áudio, vídeo, voz, troca de personagem, planejamento de redes sociais, licenciamento de ativos e pesquisa na web em volta dele.

**Idiomas:** [English](README.md) · [Português](README.pt-BR.md) · [Español](READMEs/README.es-ES.md) · [Français](READMEs/README.fr-FR.md) · [Italiano](READMEs/README.it-IT.md) · [Polski](READMEs/README.pl-PL.md) · [Русский](READMEs/README.ru-RU.md) · [中文](READMEs/README.zh-CN.md) · [日本語](READMEs/README.ja-JP.md) · [한국어](READMEs/README.ko-KR.md) · [हिन्दी](READMEs/README.hi-IN.md) · [العربية](READMEs/README.ar-SA.md) · [עברית](READMEs/README.he-IL.md) · [Bahasa Indonesia](READMEs/README.id-ID.md) · [Bahasa Melayu](READMEs/README.ms-MY.md)

Este README em português e o [README.md](README.md) em inglês mantêm as mesmas seções. As demais traduções em [`READMEs/`](READMEs/) são resumos mais curtos e podem estar defasadas em relação a este arquivo.

simplicio-videos é o plugin de vídeo do Simplicio Runtime. Ele é usado pela CLI `simplicio-video` (com saída `--json`), por um servidor MCP e por seis skills para agentes.

## Sumário

- [Como funciona](#como-funciona)
- [Mapa de capacidades](#mapa-de-capacidades)
- [Referência de comandos](#referência-de-comandos)
- [Início rápido](#início-rápido)
- [Trilhas externas fixadas e licenças](#trilhas-externas-fixadas-e-licenças)
- [Limites e lacunas conhecidas](#limites-e-lacunas-conhecidas)
- [Mapa do repositório](#mapa-do-repositório)
- [Testes e documentação](#testes-e-documentação)

## Como funciona

O agente escreve o contrato: um arquivo YAML validado por [`contract.schema.json`](src/simplicio_video/data/schema/contract.schema.json). A CLI valida, gera a narração, renderiza o vídeo de forma determinística e grava um manifesto. Mesmo contrato, mesmo MP4. Nenhum LLM roda no caminho do render. O backend padrão é o local; os backends de GPU (Kaggle, Colab) são opcionais e só entram com `--backend`.

Em volta desse núcleo há ferramentas para áudio e vídeo, voz, troca de personagem, planejamento de redes sociais, uma biblioteca de imagens e áudio com licença, pesquisa na web e integração com trilhas externas. Tudo que é generativo (vozes por IA, trocas de personagem, imagens de UGC) fica fora do render determinístico. O que essas ferramentas produzem entra num contrato como arquivo com hash.

Decisões: [ADR-0001](docs/decisoes/ADR-0001-visao-plugin.md) (visão do plugin) · [ADR-0002](docs/decisoes/ADR-0002-cli-contrato-colab-creditos.md) (CLI, contrato, Colab, créditos) · [ADR-0003](docs/decisoes/ADR-0003-fluxo-100-script.md) (fluxo 100% script, render local por padrão) · [ADR-0004](docs/decisoes/ADR-0004-ugc-generativo.md) (UGC generativo fora do render).

## Mapa de capacidades

| Área | Comandos | O que entrega | Estado |
|---|---|---|---|
| Contrato para MP4 | `init`, `validate`, `voice`, `render`, `run` | Template de setor, validação (schema, assets, durações, cada fala cabe), narração por fala com cache e `timing.lock.json`, render HyperFrames com a mixagem em -14 LUFS, manifesto, prévia de 540x960 com marca d'água | Render local é o padrão; Kaggle, Colab CLI e o bundle do Colab são backends opcionais por créditos |
| Voz | `voice`, `voicestudio` | Provedores `file`, `local` (Kokoro-82M), `gemini`, `voxcpm` (desenho ou clonagem), `openvoice` (conversão de timbre), `voicestudio` (app local) | `elevenlabs` e `xai` são stubs (gere em outro lugar e use `file`) |
| Áudio e vídeo em qualquer MP4 | `media` | `fetch` (baixa um vídeo público, com registro de procedência), `probe`, `audio`, `sheet`, `subs`, `burn`, `mask`, `replace-audio`, `voice-track` | ffmpeg e ffprobe; `fetch` usa o yt-dlp fixado e exige `--autorizo` |
| Cortes verticais | `shorts` | `inspect`, `plan`, `cut`, `run`: cortes 9:16 de um vídeo longo, a partir de transcrição por palavra; o plano é um arquivo versionado | Só ffmpeg, determinístico |
| Edição por EDL | `edit` | `setup`, `transcribe` (faster-whisper, local), `pack`, `render`, `verify` | video-use, fixado |
| Templates, motion, formatos, ângulos | `list`, `formats` | 14 templates de setor (8 prontos, 6 skeleton); 55 entradas no catálogo de motion (33 prontas, 19 propostas, 2 inline, 1 lib); 50 formatos de anúncio; 50 ângulos em 5 grupos | Catálogos |
| Troca de personagem | `swap`, `jobs` | Seis adaptadores: `gemini` (conferido com a documentação), `fal`, `wavespeed`, `kie`, `alibaba` (UNVERIFIED), `fake` (testes); estimativa de custo; teto `--max-usd` | Pago; só roda pelo terminal, com `--autorizo` e `--yes` |
| Tarefas em segundo plano | `jobs` | `submit`, `status`, `list`, `cancel`, `result`, `clean` para `swap-run` e para `voice` local | Sem daemon e sem porta aberta |
| Trilhas externas de produção | `clone`, `montage`, `opencut`, `toonflow`, `moneyprinter` | Hypit (clonagem com agentes), OpenMontage (produção com agentes), OpenCut (acabamento manual), Toonflow (estúdio de séries e quadrinhos), MoneyPrinterTurbo (tema vira vídeo curto) | Checkouts fixados, rodam como programas separados, nunca importados |
| Planejamento de redes sociais | `social` | Provedores Real Oficial (padrão) e Zernio; confere um MP4 contra os limites por rede; grava um plano; mostra a sequência de chamadas MCP | **Nunca posta.** O agente posta com as ferramentas do provedor, após o consentimento explícito de cada postagem |
| Biblioteca de imagens e áudio com licença | `openverse` | Busca, download seguro, folha de revisão por pedido, aprovação por (ativo, sha256, pedido), exportação com créditos, verificação offline de um contrato | As licenças vêm das fontes; não é parecer jurídico |
| Pesquisa na web | `busca` | `consulta`, `pagina`, `status`, `log` pelo TinyFish, com fonte e data por resultado, teto diário de chamadas e registro de procedência | A consulta vai para um terceiro; segredos e dados pessoais são recusados |
| Trilha de UGC | `ugc/` (sem CLI) | 10 personagens sintéticos, 5 arquivos de prompt, um pipeline manual de 7 passos | Generativo; fora do render |
| Integração com agentes | `mcp`, `install`, skills | Servidor MCP com 28 ferramentas `video.*`, uma por comando da CLI; 6 skills; `install` copia as skills para 11 hosts de agente | Só no terminal de propósito: `login`, `logout`, gasto (`swap run`), instalar ou remover software e servidores que não terminam |
| Operação | `status`, `tools`, `doctor`, `setup`, `update`, `login`, `logout`, `auth` | Estado das ferramentas e do render, trilhas fixadas, diagnóstico, workspace, atualizações, login Simplicio compartilhado | O motor nunca guarda credencial |

## Referência de comandos

Rode `simplicio-video <comando> --help` para ver todas as opções. Os comandos que devolvem dados também aceitam `--json`.

### Contrato para MP4

```bash
simplicio-video init <cliente> <campanha> --template <id> --nome "<Nome>"   # esqueleto de contrato a partir de um template de setor
simplicio-video validate contract.yaml                                       # schema, assets, durações, falas
simplicio-video voice contract.yaml [--provider file|local|gemini|voxcpm|openvoice|voicestudio] [--force]
simplicio-video render contract.yaml [--backend local|kaggle|colab-cli|colab] [--preview] [--out x.mp4]
simplicio-video run contract.yaml --provider gemini                         # voz -> validate -> render, para no MP4
```

- `render --preview` faz uma prévia de 540x960 com a marca d'água e o crédito final do contrato (`marca.dagua`, `marca.credito`).
- `render --backend colab` grava um bundle para [`colab/render.ipynb`](colab/README.md) (GPU) em vez de renderizar aqui.
- A narração no render nunca é esticada no tempo: uma take maior que o seu espaço é erro.

### Voz

```bash
simplicio-video voicestudio status              # saúde do app e GPU
simplicio-video voicestudio voices --json       # perfis de voz salvos
simplicio-video voicestudio languages           # idiomas de TTS que o app oferece
simplicio-video voicestudio personalities       # presets de personalidade
simplicio-video voicestudio tts "Olá" -o ola.wav --profile <id> --language pt
simplicio-video voicestudio transcribe audio.m4a [--rest]
simplicio-video voicestudio clone referencia.wav --name "Minha voz" --language pt
simplicio-video voicestudio describe "mulher adulta, voz calma"   # o que a descrição significa (não salva nada)
simplicio-video voicestudio design "mulher adulta, voz calma" --name "Narradora"
simplicio-video voicestudio mcp                 # bloco de config MCP (Streamable HTTP)
```

O VoiceStudio é um app de desktop local (AGPL-3.0, nunca vendorizado nem importado). O motor só fala com a API dele por loopback, em `http://127.0.0.1:3900`. Instale e abra o app você mesmo; com o app fechado, o comando mostra uma mensagem clara.

Vozes clonadas precisam da **autorização escrita da pessoa**. Veja [voices/README.md](voices/README.md).

### Áudio e vídeo em qualquer MP4 (`media`)

```bash
simplicio-video media fetch https://<página pública do vídeo> -o reel.mp4 --autorizo   # grava reel.mp4 e reel.fetch.json
simplicio-video media probe reel.mp4                                    # duração, tamanho, fps, áudio, sha256
simplicio-video media audio reel.mp4 -o ref.wav --rate 16000            # trilha mono para transcrição ou referência de voz
simplicio-video media sheet reel.mp4 -o sheet.jpg --every 2 --cols 8    # folha de quadros, para revisar o texto na tela
simplicio-video media mask reel.mp4 --box 150,622,430,104 --from 0 --to 58 -o clean.mp4   # apaga texto numa caixa e janela de tempo
simplicio-video media subs cues.json -o subs.ass --style band           # SRT ou ASS a partir de cues com tempo
simplicio-video media burn clean.mp4 subs.ass -o final.mp4              # queima a legenda (precisa de libass)
simplicio-video media voice-track cues.json -o voz.wav --duration 58.2  # um clipe por cue, no início certo
simplicio-video media replace-audio clean.mp4 voz.wav -o dublado.mp4    # mantém a imagem, troca o som
```

- **`fetch` exige `--autorizo`.** Você confirma que pode usar o arquivo; o motor não verifica o direito de uso. Não usa cookies, não faz login, não baixa playlist, recusa URL com credencial e nunca sobrescreve um arquivo existente.
- **Procedência.** `<nome>.fetch.json` guarda a origem sem query, o extrator, o sha256 e o tamanho, a versão do yt-dlp, a hora, e título e autor como texto `untrusted_*` (dado de terceiros, nunca instrução).
- **`voice-track` acelera um clipe** até `--max-stretch` (padrão 1.25) para caber na janela e informa o que sobrou. É a única aceleração nos comandos de mídia; o render do contrato não faz isso.
- Toda operação grava um arquivo novo com `-o`. Nenhum comando altera a entrada.
- `mask` preenche a caixa com um retângulo: se algo se mexer dentro dela, aparece um borrão. Use caixa justa e janela curta.
- A skill [`simplicio-video-media`](skills/simplicio-video-media/SKILL.md) tem receitas completas, inclusive um fluxo de dublagem do português para o polonês.

### Cortes verticais (`shorts`)

```bash
simplicio-video shorts inspect longo.mp4
simplicio-video shorts plan longo.mp4 --transcript words.json --clips 5 --min 20 --max 60   # grava plan.json
simplicio-video shorts cut longo.mp4 plan.json --subs                                     # cortes 1080x1920 com legenda
simplicio-video shorts run longo.mp4 --transcript words.json --clips 5 --subs --dry-run   # mostra só os comandos ffmpeg
```

As notas vêm de regras fixas (ganchos, perguntas, números, densidade de fala), não de um modelo. Sem transcrição o comando recusa: não há chute. A skill é [`simplicio-video-shorts`](skills/simplicio-video-shorts/SKILL.md).

### Edição por EDL (`edit`)

```bash
simplicio-video edit setup                                  # clona o video-use no commit fixado
simplicio-video edit transcribe fonte.mp4 -o words.json --lang pt   # transcrição local com faster-whisper
simplicio-video edit pack EDIT_DIR                          # transcrições em takes_packed.md para revisão
simplicio-video edit render edit/edl.json -o out/final.mp4  # cortes em limite de palavra, fades de 30 ms, legendas
simplicio-video edit verify out/final.mp4 12.0 18.5 -o check.png   # filmstrip de um corte, para revisar
```

O agente escreve o EDL (`edl.json`); os helpers rodam o ffmpeg. A skill é [`simplicio-video-edit`](skills/simplicio-video-edit/SKILL.md).

### Templates, motion, formatos e ângulos

```bash
simplicio-video list templates        # 14 templates de setor: pronto (renderiza) ou skeleton
simplicio-video list motion           # 55 entradas do catálogo de motion
simplicio-video list voices           # provedores de voz e o estado de cada um
simplicio-video list angles --grupo prova
simplicio-video formats list          # 50 formatos de anúncio da biblioteca do Drive
simplicio-video formats show <id>
simplicio-video formats prompt <id> --copia copia.txt   # prompt que adapta uma copy ao formato
```

Templates de setor: `alimentacao`, `assistencia-tecnica-games`, `beleza-estetica`, `brand-promo`, `imobiliario`, `institucional-advocacia`, `institucional-estetica`, `institucional-odontologia`, `pov-showcase`, `saas-tech`, `saude-clinica`, `saude-odontologia`, `sazonal-dia-das-criancas`, `varejo`. Oito estão prontos para renderizar. A biblioteca de motion está em [motion/README.md](src/simplicio_video/data/motion/README.md) e os templates em [templates/README.md](src/simplicio_video/data/templates/README.md).

### Troca de personagem e tarefas em segundo plano (`swap`, `jobs`)

```bash
simplicio-video swap providers                                   # adaptadores, capacidades, preço em US$ e R$, confiança
simplicio-video swap estimate --provider gemini --video in.mp4 --ref avatar.png
simplicio-video swap run --provider gemini --video in.mp4 --ref avatar.png --out out/swap.mp4 --autorizo              # dry-run: só estima
GEMINI_API_KEY=... simplicio-video swap run ... --autorizo --yes --max-usd 2                                         # gasta, com teto
simplicio-video swap status out/swap.manifest.json
simplicio-video jobs submit swap-run ... --autorizo --yes       # roda num processo separado; volta na hora
simplicio-video jobs status|list|result|cancel|clean <id>
```

`--autorizo` confirma que você tem direito sobre o vídeo e as imagens. Sem `--yes` nada é enviado. `--max-usd` aborta antes de submeter. As chaves entram só pela variável de ambiente do provedor. Só o `gemini` foi conferido com a documentação; `fal`, `wavespeed`, `kie` e `alibaba` estão **UNVERIFIED** e pedem `--aceito-unverified` para gastar. A ferramenta MCP `video.swap` só lista provedores e estima; gastar é só pelo terminal.

Os pedaços rodam em paralelo com `--concurrency` (padrão 3 na troca, 4 nas vozes de rede). O asyncio só entra onde o código espera a rede; o render e o ffmpeg continuam seriais.

### Planejamento de redes sociais, sem postar (`social`)

```bash
simplicio-video social providers                                  # Real Oficial (padrão) e Zernio: ferramentas MCP, limites, lacunas
simplicio-video social plan --video out/final.mp4 --caption-file legenda.txt --target tiktok=@conta --target youtube \
    [--at 2026-10-20T09:30 --timezone America/Sao_Paulo] [--title "..."] [--ai-generated]   # grava social.plan.json
simplicio-video social check out/social.plan.json                 # o vídeo ainda é o do plano?
simplicio-video social recipe out/social.plan.json [--provider zernio] [--clip-id ID]   # a sequência de chamadas MCP
```

O `plan` recusa arquivo inexistente ou que não é MP4 e confere duração, proporção, tamanho, legenda, título e hashtags contra [`limits.json`](src/simplicio_video/data/social/limits.json). Só o limite de duração do YouTube Shorts foi conferido na página oficial; o resto é **UNVERIFIED** e pede `--aceito-unverified`. O motor nunca guarda chave ou token. A ferramenta MCP `video.social` oferece `providers`, `plan`, `check` e `recipe`, e não tem ação de publicar. Leia a [ADR-0018](docs/decisoes/ADR-0018-social-planejar-sem-postar.md) e a skill [`simplicio-video-social`](skills/simplicio-video-social/SKILL.md).

### Biblioteca de imagens e áudio com licença (`openverse`)

```bash
simplicio-video openverse search --tipo imagem --consulta "sunrise over the sea" --minimo-largura 1280 --limite 10
simplicio-video openverse search --tipo audio --consulta "rain" --duracao-min 20 --duracao-max 90 --json
simplicio-video openverse get <id>                                    # download seguro para a biblioteca local
simplicio-video openverse library review <id> --pedido "<o que a cena precisa>" --folha     # a folha de revisão
simplicio-video openverse library review <id> --pedido "<o mesmo>" --aprovar --motivo "..." --por "<revisor>"
simplicio-video openverse library export <id> --pedido "<o mesmo>" --contrato clients/acme/video-01/contract.yaml
simplicio-video openverse library verify clients/acme/video-01/contract.yaml   # confere os ativos declarados, sem rede
simplicio-video openverse library credits | list | show <id>
```

- **Revisão por pedido.** Uma aprovação vale para um trio exato: id do ativo, sha256 do arquivo e pedido normalizado. Aprovar para o pedido A não vale para o pedido B, e um arquivo novo invalida as aprovações antigas.
- **Licenças.** O padrão é `cc0,pdm,by`. Licenças de compartilhamento igual e não comerciais precisam de `--licencas` explícito. Qualquer licença com restrição (`nc`, `nd`, `sa`) precisa de `--aceito-restricao` na exportação. Item sem licença conhecida nunca é baixado, e item CC BY sem autor nunca é exportado. As licenças vêm das fontes; isto não é parecer jurídico.
- **Portão no contrato.** Um asset do contrato pode declarar `openverse: {id, pedido}`. `validate`, `run` e `render` recusam aprovação ausente, arquivo trocado, linha de crédito ausente, cópia feita à mão ou asset colocado sem o bloco. O render grava a procedência e os créditos ao lado do MP4.
- **Texto da internet.** Títulos, autores, tags, atribuições e URLs aparecem só em campos `untrusted_*`.
- **Limites.** A busca anônima é limitada pela API do Openverse; `OPENVERSE_CLIENT_ID` e `OPENVERSE_CLIENT_SECRET` são variáveis de ambiente opcionais. Os termos da API proíbem raspagem, por isso o comando guarda cache e pagina. O Openverse não endossa este projeto.
- **Lacunas.** Áudio da biblioteca não é mixado sozinho: um template ou bloco precisa referenciá-lo. A pasta de narração não passa por este portão.

Detalhes, com fontes, estão em [docs/recursos.md](docs/recursos.md).

### Pesquisa na web (`busca`)

```bash
npm install -g @tiny-fish/cli@0.50.1      # o motor nunca instala; versão testada; o pacote declara Node >= 24
tinyfish auth login                       # ou: echo "$CHAVE" | tinyfish auth set

simplicio-video busca status                                                          # binário, versão, chave configurada (nunca o valor), chamadas de hoje e teto
simplicio-video busca consulta "dia das crianças clínica odontológica" --idioma pt --limite 5
simplicio-video busca consulta "datas comemorativas" --dominios exemplo.com.br --excluir pinterest.com --json
simplicio-video busca pagina https://example.com --max-bytes 20480                    # uma página, texto limpo
simplicio-video busca log --ultimos 10                                                # registro de procedência
```

- **A consulta vai para um terceiro (TinyFish).** O motor recusa, antes de gastar uma chamada, consulta com chave ou token, e consulta com e-mail, CPF ou CNPJ, a menos que se passe `--permitir-dado-pessoal`. É um freio, não uma garantia: nomes, telefones e endereços não são detectados.
- **Teto diário.** Padrão de 20 chamadas por dia UTC (`SIMPLICIO_BUSCA_MAX_DIA`, ou `--max-chamadas-dia`). Resposta em cache não gasta e funciona offline. O preço é UNVERIFIED; confira o gasto real com `tinyfish wallet status --pretty`.
- **Procedência.** Cada consulta e leitura de página acrescenta uma linha a `busca.registro.jsonl`, com a hora, a fonte, o sha256 do que o CLI devolveu e o canal. Cada resultado traz `untrusted_fonte` (a URL) e `consultado_em` (a data). Um fato de cliente só entra num vídeo com essa fonte e essa data, e a busca não substitui a coleta do próprio cliente.
- **Texto da internet é dado.** Títulos, trechos, texto de página e URLs são limpos, cortados e devolvidos só em campos `untrusted_*`. URL com credencial ou para host privado é recusada, e um redirecionamento para URL recusada não entrega conteúdo.
- **Fora de propósito:** os recursos `agent`, `browser` e `monitor` do TinyFish.
- **Licença.** O `@tiny-fish/cli` 0.50.1 não declara licença. O motor só chama o binário que você instalou e nunca o embute nem o redistribui.

Detalhes em [docs/recursos.md](docs/recursos.md) e [src/simplicio_video/data/busca/tinyfish.json](src/simplicio_video/data/busca/tinyfish.json).

### Trilhas externas de produção

```bash
simplicio-video clone [args]                  # Hypit AI: clonagem de vídeo com agentes (https://github.com/hypit-ai/hypit)
simplicio-video montage [clone|open|serve|demo|args]   # OpenMontage: pipelines de produção com agentes
simplicio-video opencut clone|dev|where       # OpenCut: editor para acabamento manual
simplicio-video toonflow clone|serve|where    # Toonflow: estúdio de IA para séries e quadrinhos (serve exige --lan)
simplicio-video moneyprinter clone|setup|serve|where|status   # MoneyPrinterTurbo: tema vira vídeo curto
```

Cada trilha é clonada no commit fixado em [`tools.py`](src/simplicio_video/tools.py) e roda como programa próprio. O que ela produz entra num contrato como arquivo com hash.

- **Toonflow.** O servidor não tem login e escuta em todas as interfaces (`0.0.0.0:3000`), por isso `serve` não sobe sem `--lan`. Os dados vão para `~/.simplicio-video/toonflow-data`.
- **MoneyPrinterTurbo.** Ele chama serviços de terceiros (um LLM, um serviço de TTS, banco de imagens e vídeos) com **as suas** chaves, no WebUI ou no `config.toml`. O motor nunca as imprime. `serve` escuta em `127.0.0.1`, a menos que se passe `--lan`.
- **VoiceStudio e video-use** estão descritos acima (voz e edição por EDL).

### Integração com agentes: MCP, skills e install

```bash
simplicio-video mcp                  # servidor MCP por stdio (instale com pip install -e .[mcp])
simplicio-video install [--global] [--check|--dry-run] [--json] [--verify] [--uninstall]
simplicio-video install --global     # copia as seis skills para todos os hosts de agente conhecidos (11)
```

O servidor MCP expõe 28 ferramentas, uma para cada comando da CLI: `video.init`, `video.validate`, `video.voice`, `video.render`, `video.run`, `video.list`, `video.clone`, `video.montage`, `video.edit`, `video.opencut`, `video.formats`, `video.swap`, `video.jobs`, `video.social`, `video.openverse`, `video.voicestudio`, `video.busca`, `video.toonflow`, `video.moneyprinter`, `video.shorts`, `video.media`, `video.tools`, `video.status`, `video.doctor`, `video.setup`, `video.install`, `video.update`, `video.auth`. Algumas são só de leitura ou propositalmente limitadas: `video.swap` estima mas nunca gasta, `video.social` nunca publica, `video.openverse` não baixa nem exporta, `video.jobs` só submete voz local, `video.auth` só lê o login, `video.update` só verifica, e `video.install` não remove skills nem grava sem `--global` ou `--target` absoluto. Comandos que abrem navegador, gastam dinheiro, instalam software ou sobem um servidor que não termina recusam com o comando do terminal. O manifesto é o [`plugin.json`](plugin.json).

As seis skills, em [`skills/`](skills/):

| Skill | Para quê |
|---|---|
| [`simplicio-video`](skills/simplicio-video/SKILL.md) | escrever o contrato e rodar o render |
| [`simplicio-video-media`](skills/simplicio-video-media/SKILL.md) | áudio e vídeo em qualquer MP4, com download por `fetch` |
| [`simplicio-video-voicestudio`](skills/simplicio-video-voicestudio/SKILL.md) | voz local pelo app VoiceStudio |
| [`simplicio-video-shorts`](skills/simplicio-video-shorts/SKILL.md) | cortes verticais de um vídeo longo |
| [`simplicio-video-edit`](skills/simplicio-video-edit/SKILL.md) | edição por EDL com video-use |
| [`simplicio-video-social`](skills/simplicio-video-social/SKILL.md) | planejar postagens, com as ferramentas do provedor |

### Operação

```bash
simplicio-video status [--json] [contract.yaml]   # ferramentas instaladas, versões fixadas, estado do render
simplicio-video tools [--json]                    # todas as trilhas externas fixadas
simplicio-video doctor [all|login] [--json] [--online]   # login, update, runtime, Python, Node 22, ffmpeg com libass, disco, portas, workspace
simplicio-video setup                             # primeira execução: workspace, tema, idioma, autonomia L1, orçamentos zerados
simplicio-video update [--check|--dry-run] [--force]     # PyPI; um checkout git recusa e manda rodar git pull
simplicio-video login [--json] [--no-browser]     # o login Simplicio compartilhado (o mesmo do Runtime); não guarda credencial
simplicio-video logout | auth status
```

## Início rápido

```bash
gh repo clone simpletibr/simplicio-videos && cd simplicio-videos
pip install -e .                      # comando `simplicio-video` (Python >= 3.10); o render precisa de Node >= 22 e ffmpeg
simplicio-video setup                 # primeira execução
simplicio-video install               # copia as skills para o host do agente (projeto; --global para a pasta home)
simplicio-video doctor                # mostra o que falta

cd clients/<cliente>/<campanha>       # um projeto de cliente com contract.yaml
simplicio-video validate contract.yaml
simplicio-video voice contract.yaml   # narração; voz local de rascunho ou --provider file|gemini|voxcpm|openvoice|voicestudio
simplicio-video render contract.yaml  # out/<cliente>-<campanha>.mp4 + render.manifest.json
```

Voz clonada no contrato (exemplo com VoxCPM2):

```yaml
voz:
  provider: voxcpm
  providers:
    voxcpm:
      reference_audio: assets/audio/ref/speaker.wav   # pessoa autorizada, 10 a 30 s limpos
      reference_text: "Transcrição exata do trecho."   # opcional
      control: "warm, slightly faster"                 # estilo opcional
      seed: 42
```

Windows: `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\dev_install.ps1` (ainda não conferido numa máquina real). O ambiente do checkout: `bash scripts/dev_install.sh`.

## Trilhas externas fixadas e licenças

Todas as versões estão fixadas em [`src/simplicio_video/tools.py`](src/simplicio_video/tools.py). `simplicio-video tools` as lista.

| Trilha | Comando | Fixado em | Licença | Papel |
|---|---|---|---|---|
| [OpenMontage](https://github.com/calesthio/OpenMontage) | `montage` | commit `9327439` | AGPL-3.0 | pipelines de produção com agentes |
| [OpenCut](https://github.com/OpenCut-app/opencut-classic) | `opencut` | commit `cf5e79e` | MIT | editor de acabamento manual (arquivado no upstream) |
| [Hypit](https://www.npmjs.com/package/@hypit/hypit) | `clone` | npm `0.2.17` | licença Hypit (Apache-2.0 modificada); sem redistribuição comercial | clonagem com agentes, instalada pelo usuário |
| [Toonflow](https://github.com/HBAI-Ltd/Toonflow-app) | `toonflow` | commit `d2e94ac` | MIT | estúdio de IA para séries e quadrinhos |
| [MoneyPrinterTurbo](https://github.com/harry0703/MoneyPrinterTurbo) | `moneyprinter` | commit `4b7b965` | MIT | tema vira vídeo curto |
| [TinyFish CLI](https://www.npmjs.com/package/@tiny-fish/cli) | `busca` | npm `0.50.1` | não declarada | pesquisa e leitura de páginas |
| [VoiceStudio](https://github.com/debpalash/VoiceStudio) | `voicestudio` | commit `beeaae0` (v0.5.7) | AGPL-3.0 | app local de voz, usado só por HTTP |
| [video-use](https://github.com/browser-use/video-use) | `edit` | commit `b877063` | MIT | edição por EDL |
| [yt-dlp](https://github.com/yt-dlp/yt-dlp) | `media fetch` | PyPI `2026.10.26`, sha256 conferido | Unlicense | baixa uma página pública de vídeo |

O motor nunca vendoriza nem importa essas trilhas. O render determinístico não depende de nenhuma delas.

## Limites e lacunas conhecidas

- **Cobertura do MCP.** Todo comando da CLI é uma ferramenta MCP, exceto `mcp` (o próprio servidor), `login` e `logout` (abrem navegador e mudam o login compartilhado) e as ações só de terminal listadas na seção de integração com agentes.
- **Adaptadores de troca não conferidos.** `fal`, `wavespeed`, `kie` e `alibaba` foram escritos a partir da documentação pública e não foram conferidos nas APIs reais.
- **Voz.** `elevenlabs` e `xai` são stubs. O VoiceStudio precisa do app aberto.
- **Downloads.** As plataformas restringem download nos próprios termos; essa responsabilidade é de quem baixa. Uma página também pode chegar cortada: nesse caso o `fetch` falha e não grava nada.
- **Sem publicação.** O motor nunca posta nem envia para uma rede social. O comando `publish` saiu do motor (#77).
- **Mask e voice-track.** `mask` deixa um retângulo se algo se mexer dentro da caixa. `voice-track` não traduz nem clona.
- **Plataformas.** O pacote é classificado para Linux; macOS e Windows não estão confirmados em máquinas reais.
- **UGC.** A pasta `ugc/` é um pipeline manual e generativo, sem comando na CLI; a saída não se reproduz byte a byte.

## Mapa do repositório

```
simplicio-videos/
├── AGENTS.md / CLAUDE.md   # regras, mapa e fluxos para agentes (CLAUDE.md → AGENTS.md)
├── plugin.json             # simplicio.plugin/v1: os verbos video.* e a skill
├── pyproject.toml          # pacote Python da CLI (src/simplicio_video/); testes em tests/
├── src/simplicio_video/    # o motor: cli.py, media.py, shorts.py, download.py, tools.py, voicestudio.py, swap, social, openverse, busca …
├── skills/                 # os seis SKILL.md, empacotados no wheel
├── schemas/                # video-spec.schema.json (simplicio.video-spec/v1)
├── intake/                 # questionário, extração de site e Instagram, exemplos
├── templates/              # um template por setor (ver src/simplicio_video/data/templates/)
├── motion/                 # biblioteca de padrões de motion: patterns/<id>/, catalog.json, scripts/
├── voices/                 # provedores de voz e o pipeline de TTS
├── tools/                  # ferramentas opcionais fixadas (video-use)
├── ugc/                    # trilha de UGC generativo, fora do render: pack.json, prompts/
├── colab/                  # render.ipynb (GPU) para os bundles de --backend colab
├── docs/                   # ADRs, pipeline, setup, referência (docs/reference é gerada); índice em docs/README.md
└── clients/<cliente>/      # só vídeos de exemplo: <video>/contract.yaml, preview/, assets
```

<!-- BEGIN GENERATED: host -->
Gerado de `docs/host/*.md` (front matter). Não edite aqui: rode `make regen`.

- [Gate local, TDD e pouso de PRs](docs/host/gate.md): Como provar que a main está verde com um comando offline, a regra de testes primeiro, o ownership por issue e o pouso serializado sem CI.
- [Licenças das dependências](docs/host/licenses.md): Como o gate confere licenças (allowlist MIT, Apache-2.0, BSD, ISC, PSF, MPL-2.0), como adicionar uma exceção justificada, como regerar docs/licenses.md e o que ainda falta (web/).
- [Pacote de operação (install, update, doctor, setup)](docs/host/packaging.md): O que cada subcomando faz, o que o doctor checa, por que a falta de GEMINI_API_KEY é aviso e os limites até as
<!-- END GENERATED -->

## Testes e documentação

Testes: `PYTHONPATH=src python -m pytest`. Os testes que precisam de rede ou de uma ferramenta real são marcados `integration`; o `make check` não os roda. Prévias da biblioteca: `bash motion/scripts/preview.sh && node motion/scripts/catalog.mjs`.

Índice em [`docs/README.md`](docs/README.md). Ferramentas de vídeo e motion curadas, com estrelas e licenças: [`docs/recursos.md`](docs/recursos.md). Referência da CLI, dos schemas, das ferramentas MCP e das variáveis de ambiente: [`docs/reference/`](docs/reference/) (gerada com `make regen`).

Também construído sobre [video-shotcraft](https://github.com/Vincentwei1021/video-shotcraft), [awesome-opus5-5-videos](https://github.com/yihui-dev/awesome-opus5-5-videos) (receitas destiladas em `motion/`) e [motion-video-kit](https://github.com/echris6/motion-video-kit) (MIT; origem de 5 padrões `proposed`). Referência externa: [Skillry — vídeos virais feitos com Claude Opus 5.5](https://skillry.dev/ai-videos/opus-5-5).

> Política de idioma: documentação nova, ajuda da CLI e comentários de código são escritos em inglês. Documentos antigos em `docs/`, `intake/`, `templates/` e pastas de clientes ainda estão em português e são traduzidos quando tocados.
