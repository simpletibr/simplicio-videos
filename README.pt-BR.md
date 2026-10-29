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
