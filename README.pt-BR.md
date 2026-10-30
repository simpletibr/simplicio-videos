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

### Busca na web

```bash
simplicio-video busca status
simplicio-video busca consulta "tema da pesquisa" --idioma pt --limite 5
```

- `busca status` testado: mostra o binário, se a chave está configurada (sem mostrar o valor) e o teto diário. Não gasta nada.
- `busca consulta` não verificado. Gasta uma chamada do teto diário e exige a chave `TINYFISH_API_KEY`.

### Openverse

```bash
simplicio-video openverse --help
simplicio-video openverse search "termo"
```

- `openverse --help` testado. `openverse search` não verificado: consulta a API pública do Openverse.
- Um ativo entra num vídeo só depois que alguém aprova aquele ativo para aquele pedido.

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
