# simplicio-video

Máquina de vídeo determinística do Simplicio Runtime: um contrato YAML vira um MP4, pela linha de comando (`simplicio-video`) ou por um servidor MCP (`simplicio-video-mcp`). Template por setor, biblioteca de motion e render com HyperFrames, voz com cache e áudio normalizado em -14 LUFS. O render não usa aleatoriedade, relógio nem LLM.

Código, documentação e issues: [github.com/simpletibr/simplicio-videos](https://github.com/simpletibr/simplicio-videos).

## Instalação

```bash
pip install simplicio-video              # ou: pipx install simplicio-video
pip install "simplicio-video[mcp]"       # com o servidor MCP (simplicio-video-mcp)
```

Extras opcionais: `[local-tts]` (as bibliotecas da voz local Kokoro; a voz ainda pede mais, veja os primeiros passos) e `[remote]` (render no Kaggle ou no Colab).

## Requisitos

- Python >= 3.10.
- Node >= 22.
- ffmpeg com libass.
- Rede no primeiro render: o motor chama `npx hyperframes@0.8.97` e baixa um Chrome. Medido num HOME limpo: cerca de 470 MB (208 MB de cache do npm e 261 MB de Chrome). Os templates também carregam o GSAP pelo jsDelivr.

## Primeiros passos

```bash
simplicio-video setup      # cria o workspace (tema, idioma, autonomia); não grava credencial
simplicio-video doctor     # diagnóstico do ambiente, com a correção de cada falha
simplicio-video init <cliente> <Campanha> --template <id> --nome "<Nome>"
simplicio-video validate clients/<cliente>/<campanha>/contract.yaml
simplicio-video run clients/<cliente>/<campanha>/contract.yaml --provider gemini
```

- O `doctor` sai com erro até você rodar o `setup` (o workspace e a política ainda não existem).
- `simplicio-video list templates` mostra os templates. O `init` grava só um esqueleto em `./clients/<cliente>/<campanha>/contract.yaml`, na pasta atual, cheio de `TODO`. Preencher os `TODO` não basta: o esqueleto ainda não traz os blocos de motion que o template exige. O `validate` aponta o que falta e recusa o contrato até ele ficar completo. Para ver um contrato que funciona de ponta a ponta, siga o [tutorial do primeiro vídeo](https://github.com/simpletibr/simplicio-videos/blob/main/docs/tutorials/primeiro-video.md) (usa o contrato mínimo `tests/fixtures/mini`, sem chave de API) e a [receita de vídeo para cliente](https://github.com/simpletibr/simplicio-videos/blob/main/docs/receita-video-cliente.md); a copy sai só de fatos do cliente.
- A voz vem de `--provider file` (WAVs seus), `local` ou `gemini` (a chave só pelo ambiente, em `GEMINI_API_KEY`). A voz `local` (Kokoro) não vem pronta: o extra `[local-tts]` instala `kokoro-onnx` e `soundfile` no seu ambiente, mas o motor procura um Python com essas bibliotecas em `SIMPLICIO_TTS_PY` (padrão `~/.local/share/simplicio-tts/cbvenv/bin/python`) e os modelos `kokoro-v1.0.onnx` e `voices-v1.0.bin` em `KOKORO_DIR` (padrão `~/.local/share/simplicio-tts`). O pacote não baixa os modelos. O `run` valida, gera a voz e renderiza o MP4.
- Cada comando tem `--help` com exemplos.

## O que não faz

- Não posta nem publica: o MP4 fica na sua máquina. O módulo `social` só planeja e confere limites; quem posta é o agente, com as ferramentas do provedor e o seu sim.
- Não chama LLM no caminho padrão: validar, voz de arquivo ou local e render rodam sem modelo. A voz `gemini` e os comandos opcionais (`busca`, `swap`, `openverse`) falam com serviços de terceiros só quando você os usa.

## Plataformas

- Linux: testado, em Python 3.11, 3.12 e 3.13 (o piso 3.10 está declarado e ainda não foi exercitado).
- macOS e Windows: ainda NÃO confirmados em máquina real. Por isso não aparecem nos classificadores do pacote.

## Documentação

- [README do projeto](https://github.com/simpletibr/simplicio-videos/blob/main/README.md)
- [Primeiro vídeo: do zero ao render](https://github.com/simpletibr/simplicio-videos/blob/main/docs/tutorials/primeiro-video.md)
- [Receita passo a passo de um vídeo de cliente](https://github.com/simpletibr/simplicio-videos/blob/main/docs/receita-video-cliente.md)
- [Skill para agentes (LLM)](https://github.com/simpletibr/simplicio-videos/blob/main/skills/simplicio-video/SKILL.md)
- [Histórico de mudanças](https://github.com/simpletibr/simplicio-videos/blob/main/CHANGELOG.md)

## Licença

AGPL-3.0-or-later. Texto integral em [LICENSE](https://github.com/simpletibr/simplicio-videos/blob/main/LICENSE). As dependências de terceiros mantêm as próprias licenças ([lista](https://github.com/simpletibr/simplicio-videos/blob/main/docs/licenses.md) e [documentos legais](https://github.com/simpletibr/simplicio-videos/blob/main/docs/legal/README.md)); as fontes dos templates (Anton, Fredoka e Inter) vêm com a licença OFL ao lado do arquivo.
