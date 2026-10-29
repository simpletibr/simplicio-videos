# shorts — vídeo longo vira cortes verticais

Trilha nova do CLI: um vídeo horizontal (entrevista, podcast, noticiário) vira N cortes 1080x1920 prontos para Shorts, Reels e TikTok.

Ela segue a mesma regra do resto do motor: **o agente decide, o script executa**. A decisão é um `plan.json` versionado (janelas de corte, nota e motivo de cada uma); o render é só ffmpeg. Nenhum modelo entra no caminho de render e nada aqui abre a rede.

## Fluxo

```bash
# 1. a transcrição é a do video-use (faster-whisper local, já usado pelo edit)
simplicio-video edit transcribe FONTE.mp4 -o words.json

# 2. metadados da fonte (duração, tamanho, fps, áudio, sha256)
simplicio-video shorts inspect FONTE.mp4

# 3. janelas pontuadas -> plan.json (a decisão, versionada)
simplicio-video shorts plan FONTE.mp4 --transcript words.json --clips 5 --min 20 --max 60

# 4. render dos cortes + manifest.json (com sha256 de cada MP4)
simplicio-video shorts cut FONTE.mp4 shorts/plan.json --subs

# tudo de uma vez
simplicio-video shorts run FONTE.mp4 --transcript words.json --clips 5 --subs
```

## Como a janela é escolhida

1. `utterances`: palavras viram falas, uma pausa maior que 0,65 s abre outra.
2. `candidate_windows`: para cada fala de abertura, a janela mais longa que ainda cabe em `--max` e já passa de `--min`, com 0,12 s de respiro em cada ponta.
3. `score_window`: nota determinística — ganchos da lista do projeto (`HOOKS` em `shorts.py`), pergunta, exclamação, dígitos, densidade de fala e distância do alvo `(min+max)/2`.
4. `select_clips`: as melhores notas que não se sobrepõem, em ordem no vídeo.

Mudar `HOOKS` muda todo plano futuro do mesmo jeito: é a única alavanca de gosto, e ela é do repositório, não do modelo.

## Saída

```
shorts/
  c01.mp4  c01.srt        # 1080x1920, H.264, AAC, faststart
  c02.mp4  c02.srt
  manifest.json           # fonte (sha256), opções, cada corte com bytes, sha256, fps e duração
```

`--subs` queima a legenda do próprio trecho (SRT gerado da transcrição, deslocado pelo início do corte). Sem `--subs` o corte sai limpo.

`--fit blur` (padrão) põe o vídeo inteiro sobre um fundo desfocado; `--fit crop` corta o centro para 9:16 e perde as bordas.

`--dry-run` imprime os comandos ffmpeg e não grava nada: serve para revisar o plano antes de renderizar 5 clipes.

## O que ele não faz

- Não baixa vídeo: a fonte é um arquivo local.
- Não transcreve sozinho: sem `--transcript` o `plan` recusa, porque a janela é a decisão e não um chute.
- Não publica: para postar use a trilha `social` (plano e receita de chamadas do Real Oficial).
- Não escolhe corte com modelo: se quiser seleção por LLM, gere o `plan.json` à mão (mesmo schema) e rode `cut`.

## Relação com as outras trilhas

| Trilha | Papel |
|---|---|
| `edit` (video-use) | transcreve e renderiza um EDL; o `shorts` usa a transcrição dele |
| `shorts` | escolhe as janelas e corta em 9:16 |
| `social` | plano de postagem por rede a partir de MP4 |
