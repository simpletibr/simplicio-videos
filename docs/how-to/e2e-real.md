---
title: Teste real ponta a ponta com as suas chaves
summary: Como rodar scripts/e2e_real.py (ou make e2e-real) no seu computador, o que cada chave e cada app habilita, quanto cada check pode custar e o que o teto impõe de fato.
commands: make e2e-real, make e2e-real E2E_ARGS="--sim-gastar", python scripts/e2e_real.py --sim-gastar --json, python scripts/e2e_real.py --apenas swap-run --max-usd 0.5
last_verified: 2026-11-05
---

# Teste real ponta a ponta com as suas chaves

O `make check` é offline e não gasta. Este roteiro é o outro lado: roda os checks **reais** (provedores pagos, apps locais, Docker, rede) com as chaves e os apps que estão **na sua máquina**, e pula o que não tem. Nada roda sem consentimento explícito.

## Como rodar

Linux e macOS:

```bash
make e2e-real                                  # plano: detecta chaves e apps e mostra o que rodaria; não roda nada
make e2e-real E2E_ARGS="--sim-gastar"          # roda o que o ambiente habilita
```

Windows (sem `make`, com o `.venv` do checkout; o caminho no Windows continua UNVERIFIED até alguém rodar, ver [testar em Windows e macOS](testar-em-windows-e-macos.md)):

```powershell
.venv\Scripts\python scripts\e2e_real.py                # plano
.venv\Scripts\python scripts\e2e_real.py --sim-gastar   # roda
```

Antes de todos os checks, o roteiro roda o smoke de SO ([`scripts/smoke_so.py`](../../scripts/smoke_so.py)) e o das trilhas ([`scripts/smoke_trilhas.py`](../../scripts/smoke_trilhas.py)), e imprime SO, Python, Node e ffmpeg. Assim um comando só cobre também o smoke no Windows e no macOS.

## O que cada chave ou app habilita

| Chave ou app | Check | Custo estimado | Flags próprias |
|---|---|---|---|
| `GEMINI_API_KEY` | `voice-gemini`: uma fala com o Gemini TTS numa cópia do fixture `mini` e `render --preview` | menos de US$ 0,01 (uma fala curta; [custos](../custos.md)) | nenhuma |
| `GEMINI_API_KEY` | `swap-run` com o Gemini (Gemini Omni) | estimativa do adaptador: cerca de US$ 0,11 por segundo de vídeo | `--autorizo`, `--swap-video`, `--swap-ref`, `--max-usd` |
| `FAL_KEY`, `WAVESPEED_API_KEY`, `KIE_API_KEY`, `DASHSCOPE_API_KEY` | `swap-run` com `--swap-provider fal`, `wavespeed`, `kie` ou `alibaba` | o teto de `--max-usd` | e `--aceito-unverified`: esses adaptadores não foram verificados na API real |
| `TINYFISH_API_KEY` (ou o login do `tinyfish`) e o binário `tinyfish` | `busca-consulta`: uma consulta, com `--atualizar` | uma chamada do teto diário (padrão 20 por dia) | `--busca-texto` (não envie dado pessoal) |
| VoiceStudio ouvindo em `127.0.0.1:3900` | `voicestudio`: `status`, `voices` e `tts` para um arquivo temporário | zero (app local, sua GPU) | nenhuma |
| Node 22.15 ou mais e `npx` | `hypit`: `clone doctor` e `clone pricing <fonte>` (leitura). A fonte é obrigatória: sem ela o Hypit falha sempre ("requires one Source"), então o check não roda | zero | `--hypit-fonte` (a run ou fonte do pricing) |
| Node 22.15 ou mais e `npx` | `hypit-build`: `clone build` | não calculado (o Hypit cobra por provedor) | `--incluir-build`, `--max-usd` e `--build-args` são obrigatórios |
| MoneyPrinterTurbo pronto (`clone`, `setup`) | `moneyprinter-livre`: `run` sem fonte paga (material local, voz Edge) | zero (Edge TTS, rede) | nenhuma |
| MoneyPrinterTurbo pronto e a chave da fonte no `config.toml` ou no ambiente | `moneyprinter-pago`: `run` com fonte paga | não calculado (a fonte cobra por vídeo) | `--incluir-pago` e `--moneyprinter-fonte` (ex.: `wavespeed`) |
| `docker` no PATH, o Toonflow clonado e a porta `3000` livre | `toonflow`: `serve --docker`, consulta `127.0.0.1:3000` e para com SIGINT. Se a porta já estiver ocupada, o check dá FAIL e não sobe nada. O PASS sai só se (a) a resposta HTTP for 2xx ou 3xx (500 e 404 dão FAIL), (b) o serve lançado continuar vivo por 3 s depois dela e (c) o serve for o dono da porta: quem ouve a `3000` é ele ou um descendente dele, ou o compose do Toonflow tem um serviço rodando que publica a porta (`docker compose ps`). Se outro processo ocupa a porta, o check dá FAIL. Se não dá para confirmar o dono (sem `/proc` e sem docker), o check dá **SKIP** com `UNVERIFIED`, nunca PASS. Em Linux o dono é lido de `/proc`; em macOS e Windows vale só o compose. A porta é conferida de novo logo antes de o serve subir (o `toonflow status` pode levar até 120 s). **Limitação:** sem Docker real aqui, a leitura do compose é UNVERIFIED. **Por desenho:** o PASS prova que o serve sobe, responde e fica de pé por 3 s (`JANELA_VIVO_S`), não que fica de pé para sempre: um serve que morre 4,0 s depois do 200 ainda dá PASS | zero (baixa imagens e compila) | nenhuma |
| `--url` de um vídeo público que você pode usar | `media-fetch`: `media fetch` com registro de procedência | zero | `--autorizo` |

`swap-estimate` roda sem chave (é só ffprobe e a tabela de preço, sem rede). `smoke-so` e `smoke-trilhas` rodam sempre que você passa `--sim-gastar`.

## Teto e consentimento

- **Nada roda sem `--sim-gastar`** (ou `--yes`). Sem a flag, o roteiro imprime o plano e o custo, e sai com 0. O plano só lê o PATH, os arquivos e o ambiente: não roda processo, não abre porta e não pergunta versão de ferramenta. Versões do Node e do ffmpeg e a porta do VoiceStudio são conferidas só com a flag.
- **`--max-usd`** precisa ser maior que zero; 0 ou negativo é erro de uso.
- **`swap run`**: o motor impõe o teto (`--max-usd`, padrão US$ 1,00). Se a estimativa passa do teto, nada é enviado. Com o padrão, um vídeo de cerca de 9 s ou mais é recusado; suba `--max-usd` de propósito.
- **`hypit-build`**: o motor não tem teto para o build. O `--max-usd` só autoriza a execução e vai para o log; defina um limite no painel do provedor.
- **`moneyprinter-pago`**: a fonte cobra por vídeo e o motor não tem teto para ela. Por isso o check só roda com `--incluir-pago` e com a fonte nomeada.
- **Busca**: a consulta vai para um terceiro (TinyFish) e a chamada conta no teto diário do motor, que fica na pasta de dados do motor (não na temporária, para que o teto conte de verdade).
- **Redação**: redige, em qualquer tamanho de valor, (a) toda variável de ambiente cujo nome contém `KEY`, `TOKEN`, `SECRET`, `PASSWORD`, `PASSWD`, `PASSPHRASE`, `CREDENTIAL`, `SENHA` ou `AUTH` (regra em "Nomes de segredo", abaixo; inclusive `VOICESTUDIO_API_KEY`, `XAI_API_KEY`, `ELEVENLABS_API_KEY`, `GITHUB_TOKEN`, `AWS_SECRET_ACCESS_KEY`, `OMNIVOICE_API_KEY`), mais as chaves conhecidas dos adaptadores, e (b) os campos de segredo do `config.toml` do MoneyPrinter (mesma regra de nomes: strings, aspas simples ou duplas, listas em várias linhas, tabelas inline e `[[x]]`), lidos sem imprimir. Cada segredo é redigido na forma crua e nas formas em que o JSON (com e sem ASCII, inclusive JSON dentro de JSON), o `repr` e o `ascii()` o imprimem (aspas, barra, quebra de linha, acento). Um campo de segredo com número (`llm_api_key = 1234567890`) também é redigido, e o texto original do número, como está no arquivo (`1_234_567`, `0xDEADBEEF`, `1.50`, `6.02e23`), sai redigido junto com o valor que o `tomllib` normaliza (`1234567`, `3735928559`, `1.5`). Ocorrências que se sobrepõem (o fim de um segredo é o começo de outro, ou o segredo tem borda e se sobrepõe a si mesmo, como `abcXabc` em `abcXabcXabc`) viram um só `***`: a redação é a união dos intervalos de todas as ocorrências, e nenhum pedaço de segredo sobra entre elas; a saída em pedaços é igual à do texto inteiro, qualquer que seja o corte. Duas ocorrências que só se encostam, sem sobrepor, continuam dois `***`. Um começo de segredo que termina o fluxo (por exemplo `SEGREDO-AB` no fim da saída) vira `***`; por isso um último caractere que seja começo de segredo também sai como `***`. **Não redige:** as chaves digitadas na interface do Toonflow (ficam nos dados dele, e o roteiro não os lê) nem arquivos de configuração de terceiros que o roteiro não conhece. Se um desses processos imprimir uma chave fora desses casos, ela aparece no log. A chave nunca vai em argumento de processo. A redação do JSON é campo a campo, então um número nunca vira `***`. Um valor com 3 ou 4 caracteres é trocado onde aparece, então a saída fica mais difícil de ler; a leitura de números e de JSON usa a saída sem redação. Um segredo configurado com menos de 3 caracteres (um PIN de 2 dígitos) **não** é redigido: o roteiro avisa com uma linha (`aviso: NOME tem menos de 3 caracteres e não será redigido`, com o nome da variável, nunca o valor) antes de executar.

## Saída

- Tudo que é gerado fica numa pasta temporária nova, ou na que você passar com `--pasta` (ela tem de não existir ou estar vazia; se não estiver, o roteiro recusa com exit 2 antes de qualquer chamada). Dentro dela ficam as mídias, os contratos copiados, o cache do npm (`npm-cache`, por isso o `npx` baixa de novo a cada execução) e os logs. A pasta é mantida no fim e o caminho é impresso; `--limpar` a apaga.
- **Fora da pasta temporária, de propósito:** a pasta de dados do motor (checkouts e caches do Hypit, do MoneyPrinter e do Toonflow, e o registro e o contador diário da busca). É ali que o teto diário da busca conta de verdade, e os checkouts são o estado instalado do motor.
- Logs, saída de passos e a saída do `toonflow serve` passam pela redação em fluxo: uma chave que chega partida entre linhas ou pedaços também vira `***`, e o texto é redigido antes de ir para o disco. A redação roda antes do corte: a saída de cada passo e o `serve.log` guardam só a cauda de 1 MiB, já redigida, então um segredo que cruza o corte sai inteiro como `***`. O `serve.log` é gravado a cada bloco, então acompanha o serviço rodando; o restante é contado e descartado.
- Dentro dela, `logs/` tem a linha de comando, o código de saída e a saída de cada passo.
- `--json` imprime só o documento `simplicio.e2e-real/v1` no stdout (estados, motivos, custo, teto e passos).
- Estados: `PASS`, `FAIL`, `SKIP` (com o motivo) e `PLANO` (pronto para rodar com `--sim-gastar`).
- Código de saída: 0 sem `FAIL`, 1 com algum `FAIL`, 2 para erro de uso.

## Exemplos

```bash
# só o swap, com um vídeo seu e teto de US$ 0,50
make e2e-real E2E_ARGS="--sim-gastar --apenas swap-run --autorizo --swap-video ~/videos/cena.mp4 --swap-ref ~/fotos/avatar.png --max-usd 0.5"

# um vídeo público que você pode usar
make e2e-real E2E_ARGS="--sim-gastar --apenas media-fetch --url https://exemplo.org/video.mp4 --autorizo"

# o JSON completo, para guardar o resultado
python scripts/e2e_real.py --sim-gastar --json > e2e.json
```

## Exceções e notas

Uma chamada fora do motor: o ffmpeg direto, porque nenhum subcomando do motor gera vídeo de teste com áudio. Não gasta nem usa rede. A nota sobre o Docker não é exceção: é só como a checagem é feita.

- **ffmpeg direto, uma vez por execução (exceção justificada):** gera o vídeo sintético de 4 s dos checks de swap e do MoneyPrinter. O repositório não tem nenhum MP4 versionado (só PNGs e WAVs, e o fixture `mini` não serve), e nenhum subcomando do `simplicio-video` gera vídeo de teste com áudio. Por isso o vídeo é gerado uma vez e reaproveitado, e uma falha do ffmpeg não é repetida. O avatar não gasta chamada: é uma cópia de um PNG do próprio repositório. A regra correspondente está em AGENTS.md. Se surgir um fixture ou um subcomando do motor, este roteiro passa a usá-lo.
- **Docker (nota, não exceção):** o script só faz `shutil.which("docker")` no plano. Quem confere o daemon é o próprio `simplicio-video toonflow serve --docker`: se o daemon estiver parado ou o compose falhar, o `toonflow/serve.log` (redigido) mostra o motivo e o check dá FAIL. Antes do serve, o roteiro roda `simplicio-video toonflow status --json` só para registrar o checkout e o pin; esse passo não gateia.

## Estado

**Nomes de segredo e valores curtos:** na dúvida, redige. Uma variável ou um campo é de segredo quando o nome (em maiúsculas) **contém** `KEY`, `TOKEN`, `SECRET`, `PASSWORD`, `PASSWD`, `PASSPHRASE`, `CREDENTIAL`, `SENHA` ou `AUTH`, mesmo sem separador (`FAL_KEY1`, `API_KEY2`, `GEMINIKEY`, `MYKEY`, `OPENAIAPIKEY`, `SESSIONKEY`, `MY_TOKEN2`, `GOOGLE_CREDENTIALS`, `AUTHORIZATION`, `apiKey`). Fica de fora uma lista pequena e explícita de falsos positivos, tirada do nome antes da busca (`_NAO_SEGREDO` em `scripts/e2e_real.py`): `KEYBOARD`, `KEYMAP`, `KEYBIND`, `KEYCODE`, `KEYSTROKE`, `KEYPAD`, `HOTKEY`, `KEYFRAME`, `KEYWORD`, `KEYSTONE`, `KEYCLOAK`, `MONKEY`, `DONKEY`, `TURKEY`, `TURNKEY`, `HOCKEY`, `JOCKEY`, `WHISKEY`, `TOKENIZ` (`TOKENIZERS_PARALLELISM`, do Hugging Face, vale `false`), `AUTHOR` e `AUTHORITY` (`GIT_AUTHOR_NAME`). `KEYBOARD_LAYOUT=us` e `MONKEY_MODE` não são segredo; `KEYS_DIR` e `TOKENS_SAVE_DIR` são (o custo é só um caminho redigido a mais). Um nome de segredo cujo valor não vale redigir entra na lista de exclusão; o contrário (um segredo que escapou) não tem conserto por lista, por isso a regra é substring. Valores com menos de 3 caracteres não são redigidos (`MIN_VALOR_SEGREDO`): `DEBUG_TOKEN=1` não estraga a saída, e um valor de 1 ou 2 caracteres mudaria a saída inteira.

**Custo do redator (medido, CPU de Python 3.12 neste repositório):** a busca é por regex e tenta cada posição, então um bloco de saída custa O(bloco × maior), com `maior` = a forma mais longa de segredo (não O(bloco + maior²)), mais O(maior) para achar o sufixo retido. Texto comum com um segredo aleatório de 10 000 caracteres: 200 MB em cerca de 2,4 s. O pior caso é um texto cujos prefixos são prefixos do segredo em todo lugar (`A` repetido com segredo `A*10000+B`): 18,8 s por MB em blocos de 64 KiB e 27 s por MB em leituras de 100 bytes (com segredo de 2 000 caracteres: 3,5 e 5,0 s por MB). Antes de a espera por texto novo existir, a leitura de 100 bytes chegava a cerca de 620 s por MB no segredo de 10 000 caracteres (medido na revisão): o sufixo retido era buscado de novo a cada leitura. Agora, com o sufixo retido acima de 256 caracteres, o texto novo espera juntar o tamanho dele (retenção total abaixo de 2 × `maior`), e o custo por byte deixa de depender do tamanho da leitura (teste `test_s6`). O que fica: esse pior caso só aparece se o filho imprimir prefixos do segredo em todo lugar, e para isso ele teria de conhecer o segredo; o roteiro é rodado por um operador e só recebe saída de processos que ele mesmo lança. Segredos reais de chave têm prefixos raros e não caem nesse caso.

Os checks com chave dependem do provedor e do app de cada máquina. Até alguém rodar com as próprias chaves, cada um fica **UNVERIFIED** neste repositório. O caminho do `voice-gemini` até a prévia foi exercitado contra o mock local do Gemini (`SIMPLICIO_GEMINI_BASE`), sem gasto. Os testes offline do roteiro (consentimento, skip, teto, redação de segredos) rodam no `make check`: [`tests/test_e2e_real.py`](../../tests/test_e2e_real.py).
