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
| Node 22.15 ou mais e `npx` | `hypit`: `clone doctor` e `clone pricing` (leitura) | zero | nenhuma |
| Node 22.15 ou mais e `npx` | `hypit-build`: `clone build` | não calculado (o Hypit cobra por provedor) | `--incluir-build`, `--max-usd` e `--build-args` são obrigatórios |
| MoneyPrinterTurbo pronto (`clone`, `setup`) | `moneyprinter-livre`: `run` sem fonte paga (material local, voz Edge) | zero (Edge TTS, rede) | nenhuma |
| MoneyPrinterTurbo pronto e a chave da fonte no `config.toml` ou no ambiente | `moneyprinter-pago`: `run` com fonte paga | não calculado (a fonte cobra por vídeo) | `--incluir-pago` e `--moneyprinter-fonte` (ex.: `wavespeed`) |
| `docker` com o daemon no ar e o Toonflow clonado | `toonflow`: `serve --docker`, consulta `127.0.0.1:3000` e para com SIGINT | zero (baixa imagens e compila) | nenhuma |
| `--url` de um vídeo público que você pode usar | `media-fetch`: `media fetch` com registro de procedência | zero | `--autorizo` |

`swap-estimate` roda sem chave (é só ffprobe e a tabela de preço, sem rede). `smoke-so` e `smoke-trilhas` rodam sempre que você passa `--sim-gastar`.

## Teto e consentimento

- **Nada roda sem `--sim-gastar`** (ou `--yes`). Sem a flag, o roteiro imprime o plano e o custo, e sai com 0. O plano só lê o PATH, os arquivos e o ambiente: não roda processo, não abre porta e não pergunta versão de ferramenta. Versões do Node e do ffmpeg e a porta do VoiceStudio são conferidas só com a flag.
- **`--max-usd`** precisa ser maior que zero; 0 ou negativo é erro de uso.
- **`swap run`**: o motor impõe o teto (`--max-usd`, padrão US$ 1,00). Se a estimativa passa do teto, nada é enviado. Com o padrão, um vídeo de cerca de 9 s ou mais é recusado; suba `--max-usd` de propósito.
- **`hypit-build`**: o motor não tem teto para o build. O `--max-usd` só autoriza a execução e vai para o log; defina um limite no painel do provedor.
- **`moneyprinter-pago`**: a fonte cobra por vídeo e o motor não tem teto para ela. Por isso o check só roda com `--incluir-pago` e com a fonte nomeada.
- **Busca**: a consulta vai para um terceiro (TinyFish) e a chamada conta no teto diário do motor, que fica na pasta de dados do motor (não na temporária, para que o teto conte de verdade).
- **Chave**: nunca vai em argumento nem em log; o que aparece na saída é `***`.

## Saída

- Tudo que é gerado fica numa pasta temporária nova, ou na que você passar com `--pasta` (ela tem de não existir ou estar vazia; se não estiver, o roteiro recusa com exit 2 antes de qualquer chamada). Dentro dela ficam as mídias, os contratos copiados, o cache do npm (`npm-cache`, por isso o `npx` baixa de novo a cada execução) e os logs. A pasta é mantida no fim e o caminho é impresso; `--limpar` a apaga.
- **Fora da pasta temporária, de propósito:** a pasta de dados do motor (checkouts e caches do Hypit, do MoneyPrinter e do Toonflow, e o registro e o contador diário da busca). É ali que o teto diário da busca conta de verdade, e os checkouts são o estado instalado do motor.
- Os logs e a saída do `toonflow serve` passam pela redação: uma chave que o processo ecoar vira `***` antes de ir para o disco.
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

## Exceções justificadas

Duas chamadas fora do motor, por falta de subcomando adequado. Nenhuma delas gasta nem usa rede.

- **ffmpeg direto, uma vez por execução:** gera o vídeo sintético de 4 s dos checks de swap e do MoneyPrinter. O repositório não tem vídeo de teste (só PNGs e WAVs) e o `simplicio-video` não tem gerador de mídia. O avatar não gasta chamada: é uma cópia de um PNG do próprio repositório. Não existe subcomando do motor para isso; se surgir um, este roteiro deve passar a usá-lo.
- **Docker sem subcomando de status:** o motor não tem comando que diga se o daemon do Docker está no ar. A checagem é o próprio `simplicio-video toonflow serve --docker`: se o daemon estiver parado ou o compose falhar, o `toonflow/serve.log` (redigido) mostra o motivo e o check dá FAIL. Antes disso o roteiro roda `simplicio-video toonflow status --json`, só para registrar o checkout e o pin; esse passo não gateia.

## Estado

Os checks com chave dependem do provedor e do app de cada máquina. Até alguém rodar com as próprias chaves, cada um fica **UNVERIFIED** neste repositório. O caminho do `voice-gemini` até a prévia foi exercitado contra o mock local do Gemini (`SIMPLICIO_GEMINI_BASE`), sem gasto. Os testes offline do roteiro (consentimento, skip, teto, redação de segredos) rodam no `make check`: [`tests/test_e2e_real.py`](../../tests/test_e2e_real.py).
