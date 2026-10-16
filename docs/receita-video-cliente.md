# Receita — vídeo de cliente do pedido à entrega

**Regra:** o agente (LLM) **raciocina e escreve o contrato**; o CLI `simplicio-video` **executa** (validação, voz, render). Nada de editar HTML/spec à mão. Skill para LLMs: [`skills/simplicio-video/SKILL.md`](../skills/simplicio-video/SKILL.md) · decisões: [ADR-0002](decisoes/ADR-0002-cli-contrato-colab-creditos.md), [ADR-0003](decisoes/ADR-0003-fluxo-100-script.md) (fluxo 100% script) · schema: [`schema/contract.schema.json`](../src/simplicio_video/data/schema/contract.schema.json).

Exemplos reais: [WJR video-01](../clients/wjr-informatica-games/video-01/contract.yaml) (porte 1:1 do vídeo entregue) e [Lothus Dia_Criancas](../clients/lothus-odontologia/video-01-dia-das-criancas/contract.yaml) (feito só pelo CLI).

## 0. Instalar (uma vez)
```bash
pip install -e .            # na raiz do repo: instala o comando simplicio-video (Python >= 3.10)
simplicio-video --help      # fluxo completo; cada comando tem --help com parâmetros e exemplos
```
Requer Node ≥ 22 e ffmpeg ([setup](setup.md)); voz local provisória: Kokoro (`tools`/`voices/local.md`).

## 1. Coleta (fatos com fonte e data)
- Site/Instagram/fichas públicas → `clients/<slug>/coleta/` (`brief.md`, `fontes.md` com URL + data, `pendencias.md` com conflitos, `colors.json`, `intake.json` validado por `intake/intake.schema.json`). Ver [intake/](../intake/README.md).
- Conflito entre fontes (ex.: dois telefones) → **fora do vídeo** até o cliente confirmar.

## 2. Raciocínio → contrato
```bash
simplicio-video list templates                    # escolha pelo nicho (precisa ser renderizável)
simplicio-video list motion                       # padrões e params
simplicio-video init <slug> <Campanha> --template <id> --nome "<Nome>" --ano 2026
```
Preencha o esqueleto (todo `TODO` bloqueia o `validate`):
- **Cenas:** ids da composição do template; `duracao_s` somando `formato.duracao_s`; uma ideia por cena.
- **Motion:** `padrao` + `bloco` + `params` (só textos/cores confirmados).
- **Falas:** `texto` (copy exata), `say` (pronúncia, ex. "Lótus"), `inicio_s` relativo à cena, `max_s` = leitura natural + folga. `inicio_s + max_s` cabe na cena (+ J-cut ≤ 0,15 s).
- **SFX:** tempos relativos à cena, nas batidas (120 BPM = 0,5 s).
- **Voz:** `provider: local` (provisória) e `providers.gemini` com voz + estilo sugeridos; `providers.file.dir` pronto para os WAVs finais.
- **Trilha:** `seed` fixa, progressão/estilo (`playful` infantil calmo, `festive` infantil animado 120-128 BPM com `music.fills` = tempos dos cortes), master −14 LUFS / TP −1,5. Para cortes na batida, use durações de cena em batidas inteiras (60/bpm). SFX lúdicos extras: `slide`, `tambourine`, `woodblock`.
- **Palavra a palavra:** `simplicio-video voice` grava em `timing.lock.json` os tempos de cada palavra (faster-whisper via `SIMPLICIO_STT_PY`; sem ele, divisão proporcional às letras). No contrato: `times: '{{words:vo1}}'` no bloco `kinetic-words`.
- **Marca:** `logo: null` sem arquivo em alta (lockup de texto; nunca recriar logo).
- **Imagem ou áudio do Openverse (opcional):** só depois de `openverse library review` aprovado para o pedido e `library export --contrato`. Declare o arquivo de `assets/openverse/` em `assets` com `openverse: {id, pedido}` (o mesmo pedido aprovado); sem o bloco, arquivo ali é recusado. O `validate` confere sem rede (id na biblioteca, sha256, veredito aprovado, aceite da restrição, crédito). Fluxo completo e campos: README, seção Openverse, e `simplicio-video openverse library verify <contrato>`.
- **Drive:** ver §6.

## 3. Validar
```bash
simplicio-video validate <contrato.yaml>          # schema, assets, soma das durações, falas cabem, TODO
```

## 4. Voz
```bash
simplicio-video voice <contrato.yaml>                     # provisória local -> assets/audio/voz/ + timing.lock.json
# final Gemini (AI Studio): gere line-01.wav ... line-NN.wav em assets/audio/vo/external/ com a voz/estilo do contrato
simplicio-video voice <contrato.yaml> --provider file
```
Fala maior que `max_s` = erro: encurte o texto ou alargue a cena (ajuste SFX junto). **Nunca acelerar.** Com `GEMINI_API_KEY`: `--provider gemini` (API, sem AI Studio; ver [voices/gemini.md](../voices/gemini.md)).

## 5. Render + QA
```bash
simplicio-video validate <contrato.yaml> --need-lock
simplicio-video render <contrato.yaml>                    # -> saida.arquivo (out/, gitignored) + render.manifest.json
simplicio-video render <contrato.yaml> --backend kaggle   # opcional: remoto sem navegador (4 vCPU grátis)
simplicio-video render <contrato.yaml> --backend colab-cli  # opcional: Colab CLI oficial (2 vCPU no grátis)
simplicio-video render <contrato.yaml> --backend colab    # opcional: bundle para colab/render.ipynb (manual)
simplicio-video run <contrato.yaml> --provider gemini --backend local   # voz + validate + render (termina no MP4)
```
- A captura do Chrome headless é CPU: o local (8 vCPU) é ~6× mais rápido que o Colab grátis. Remoto só bate byte a byte com o local usando o mesmo ffmpeg e `--gpu-encode 0` ([ADR-0003](decisoes/ADR-0003-fluxo-100-script.md)).
- `render.manifest.json`: hash do contrato e de cada input, versões, hash dos frames/áudio, loudness (alvo −14 LUFS, pico ≤ −1,5) e tempos.
- Com ativos do Openverse: o manifesto traz a chave `openverse` (procedência de cada ativo) e os créditos saem em `<video>.CREDITS-openverse.md` ao lado do MP4; cole-os onde a licença pede.
- STT: faster-whisper no MP4 deve reconhecer todas as falas; gere prévia 720p + contact sheet em `preview/`.
- Edição de footage/cortes (opcional, só a pedido): [`tools/video-use`](../tools/video-use/README.md).

## 6. Entrega no Google Drive
- Caminho: `simplicio-video/clientes/NOME_CLIENTE/ANO/CAMPANHA`
  - `NOME_CLIENTE` em Title_Case com underscore, sem acento (ex.: `Lothus_Odontologia`, `WJR_Informatica_Games`).
  - `CAMPANHA` idem (ex.: `Dia_Criancas`, `Video_Institucional`). O contrato não tem bloco `drive` (issue #75): esse caminho é convenção de quem entrega, fora do motor.
- Nome do arquivo: `<CLIENTE> - <descricao> - vNN.mp4` (ex.: `Lothus - Dia das Criancas 15s - v01.mp4`); nova versão = vNN+1.
- O repositório guarda **links**, nunca o MP4 final. Todo link novo entra na tabela **Entregas no Drive** de `clients/<slug>/README.md` (campanha, pasta, arquivo, link, versão/status).
- Upload: não é do motor (#75); o comando `publish` saiu do CLI (#77) e fica no repositório de operação. O motor termina no MP4 em `saida.arquivo`. **Só com pedido explícito do Wesley** a entrega é feita, pela ferramenta de operação.

## 7. Commit
Contrato + `timing.lock.json` + `render.manifest.json` + `assets/audio/voz/` + README/roteiro do vídeo + link no README do cliente. `pytest` e `simplicio-video validate` antes do push.
