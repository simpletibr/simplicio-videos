# Primeiro vídeo: do zero ao render

Este tutorial leva do checkout instalado até um MP4 renderizado. Usa o fixture `tests/fixtures/mini/`: um vídeo de 1 segundo, 180x320, com duas cenas e uma fala com WAV pronto. Não precisa de chave de API. Leva uns 10 minutos.

Se ainda não instalou, siga [instalar, atualizar e checar](../how-to/install.md) primeiro. Cada comando abaixo tem `--help` com exemplos (`simplicio-video validate --help`, por exemplo).

## 0. Confira o ambiente

```bash
simplicio-video --help
simplicio-video doctor
```

Se `simplicio-video` não for encontrado, ative o ambiente com `source .venv/bin/activate` ou use `.venv/bin/simplicio-video`. O `doctor` diz a correção exata de cada falha (Node 22 e ffmpeg com libass). Aviso não reprova; falha, sim.

## 1. Copie o fixture para fora do repositório

Voz e render escrevem arquivos ao lado do contrato (`assets/`, `build/`, `out/` e `timing.lock.json`). Por isso o tutorial roda numa cópia, e não em `tests/fixtures/`. Rode a partir da raiz do repositório:

```bash
mkdir -p ~/video-primeiro
cp -r tests/fixtures/mini ~/video-primeiro/mini
CONTRATO=~/video-primeiro/mini/contract.yaml
```

## 2. Leia o contrato

O `contract.yaml` é a fonte da verdade do vídeo. Três pontos importam agora:

- `formato.duracao_s: 1`, com duas cenas de `0.5` s. A soma das cenas tem que bater com a duração total.
- A fala da cena `a` tem `max_s: 0.4`. Fala que passa de `max_s` é erro: o CLI nunca acelera a voz.
- `voz.provider: file`. A voz vem de WAVs prontos em `vo/` (aqui, `vo/line-01.wav`), na ordem das falas. Não há chamada de API.

Contratos reais seguem a mesma forma, com copy que vem da coleta do cliente. Ver [receita de vídeo para cliente](../receita-video-cliente.md).

## 3. Valide

```bash
simplicio-video validate "$CONTRATO"
```

A saída esperada é parecida com esta:

```
aviso  voice: timing.lock.json missing - run `simplicio-video voice <contrato>`
aviso  marca.logo is null: text lockup only (never recreate a logo)
cenas: a 0-0.5s | b 0.5-1s
OK: contrato válido
```

Os dois avisos não bloqueiam. O primeiro some depois do passo 4. O segundo é esperado, porque o fixture não tem logo.

## 4. Gere a voz

```bash
simplicio-video voice "$CONTRATO" --provider file
```

Saída esperada:

```
vo1 rendered 0.30s / 0.4s  tom de teste
voice: file -> .../mini/timing.lock.json
```

O comando mede a duração real de cada fala (`0.30s`) e a compara com o limite `max_s` (`0.4s`). Grava `timing.lock.json` ao lado do contrato. Depois disso, confira o contrato com a trava de voz:

```bash
simplicio-video validate --need-lock "$CONTRATO"
```

Deve terminar com `OK: contrato válido`, sem o aviso do lock.

## 5. Renderize

```bash
simplicio-video render "$CONTRATO"
```

O render compila o contrato numa composição HyperFrames, sintetiza trilha e efeitos, mixa a voz, renderiza os frames e masteriza o áudio em -14 LUFS. Na primeira execução, o `npx` baixa o HyperFrames 0.8.97, então é preciso rede. Depois fica em cache.

A última linha da saída mostra onde está o arquivo:

```
render[local]: .../mini/out/mini.mp4 (1.0 s, 30 frames) · inputs ... · frames ... · audio ...
```

Confira o resultado:

```bash
ffprobe -v error -show_entries stream=codec_name,width,height -show_entries format=duration -of default=nw=1 ~/video-primeiro/mini/out/mini.mp4
```

O esperado é vídeo H.264 de 180x320, áudio AAC e duração de 1 s. Ao lado do contrato também fica `render.manifest.json`, o registro do que entrou no render (hashes, ferramentas e `loudness`).

Para uma prévia leve, com marca d'água, use `simplicio-video render "$CONTRATO" --preview`. A prévia sai em 540x960 e não substitui o render de entrega.

## 6. Atalho: tudo de uma vez

Quando o contrato já está pronto, `run` faz os passos 4, 5 e a validação com trava, num comando só:

```bash
simplicio-video run "$CONTRATO" --provider file
```

## Problemas comuns

| Sintoma | Causa provável | O que fazer |
|---|---|---|
| `timing.lock.json missing` no `validate` | a voz ainda não foi gerada | rode o passo 4 |
| Erro de fala: a duração real passa de `max_s` | o texto é longo para a cena | encurte o texto ou dê mais tempo à cena; não há aceleração |
| `render` falha antes de começar | Node abaixo de 22 ou ffmpeg ausente | rode `simplicio-video doctor` e siga a correção indicada |
| `npx` não baixa o HyperFrames | primeira execução sem rede | conecte e rode o render de novo |

## Próximos passos

- Vídeo de cliente: `simplicio-video list templates` mostra os templates de setor. `simplicio-video init <cliente> <Campanha> --template <id>` gera o contrato; os campos que faltam precisam ser preenchidos antes do `validate`.
- Todos os comandos e opções: [referência da CLI](../reference/cli.md), gerada do `--help`.
- Visão da esteira completa, do intake ao render: [esteira](../esteira.md).
