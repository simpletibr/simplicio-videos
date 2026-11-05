# Terceiros

Quem é de fora do projeto e como cada item entra no produto. A tabela de licenças das dependências Python instaladas é gerada e fica em [../licenses.md](../licenses.md).

## Fontes (OFL-1.1)

Três famílias de fonte estão sob a SIL Open Font License 1.1 (OFL). Os arquivos de licença vêm junto com as fontes:

| Fonte | Arquivos | Onde |
|---|---|---|
| Anton | `OFL-Anton.txt`, `Anton-Regular.ttf` | `src/simplicio_video/data/motion/assets/fonts/` |
| Fredoka | `OFL-Fredoka.txt`, `Fredoka.ttf` | `src/simplicio_video/data/motion/assets/fonts/` |
| Inter | `OFL-Inter.txt`, `Inter.ttf` | `src/simplicio_video/data/motion/assets/fonts/` |

Os templates também trazem cópias dessas fontes com o `OFL-*.txt` em `src/simplicio_video/data/templates/<template>/composition/assets/fonts/`. A OFL permite uso, redistribuição e modificação, desde que o aviso de copyright e a licença acompanhem a fonte.

## GSAP (GreenSock)

O GSAP é **carregado por CDN, não embutido**. Achado do `grep -rn "gsap" src/simplicio_video/data/templates`:

- `<script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js">` aparece em 6 templates (`assistencia-tecnica-games`, `institucional-estetica`, `institucional-odontologia`, `institucional-advocacia`, `sazonal-dia-das-criancas`, `saude-odontologia`), no `composition/index.template.html` de cada um.
- Os blocos de motion em `src/simplicio_video/data/motion/patterns/` usam a mesma URL (30 ocorrências em 31 arquivos que citam gsap).
- Nenhum arquivo `gsap*` existe em `src/`.

A licença do GSAP (GreenSock standard license) não é uma licença open source padrão. **Precisa de revisão jurídica** antes da publicação, especialmente pelo uso em produto comercial de terceiros.

## Externos e não empacotados

Estas ferramentas não são redistribuídas pelo repositório. O CLI as invoca como programas separados, instalados pelo usuário:

| Ferramenta | Situação |
|---|---|
| OpenMontage | Programa externo, AGPL. Só chamado pelo comando `montage`; não é empacotado. |
| OpenCut | Programa externo. Só chamado pelo comando `opencut`; não é empacotado. |
| Hypit | **Não empacotado.** A licença (Apache-2.0 modificada) proíbe redistribuição comercial e serviço multi-inquilino sem permissão por escrito. Só o comando `clone` roda a instalação do próprio usuário (`npx`). |
| VoiceStudio | Programa externo, AGPL. Não empacotado. |
| instagram-agent-skill (Jake Schincariol) | MIT, **não empacotado**: 13 skills de agente e seis scripts Python do upstream, no commit fixado `d03c56b`. Só o comando `instagram clone` baixa o checkout, para o cache do usuário; o motor roda os seis scripts depois de conferir o sha256 e não redistribui nenhum arquivo deles. A licença e o aviso de copyright ficam no `LICENSE` do checkout. A tabela de [licenças](../licenses.md) não os lista: não são dependência Python do pacote. |
| Toonflow | Programa externo, MIT. **Não empacotado**: `toonflow clone` baixa o commit fixado `d2e94ac` para o cache do usuário; o `serve` roda o app à parte. |
| MoneyPrinterTurbo | Programa externo, MIT. **Não empacotado**: `moneyprinter clone` baixa o commit fixado `4b7b965` para o cache. Os serviços de terceiros que ele usa (LLM, voz, estoque) têm termos próprios, que não foram revisados aqui. |
| match-cut (Sac-Y) | Skill externo, MIT. **Não empacotado**: `matchcut clone` baixa o commit fixado `b51c98f`. O motor nunca roda o skill nem chama a Renoise; o uso do skill exige login e créditos da própria pessoa. |
| video-use (browser-use) | Programa externo, MIT. **Não empacotado**: `edit setup` clona o upstream no commit fixado `b877063` para o cache. Os arquivos do wrapper (`setup.sh`, `transcribe_local.py`, `edl_transcript.py`) são deste repositório. |
| rea-video (JuneYaooo) | MIT, declarada no `pyproject.toml` do upstream; o commit fixado `36e02dd` não traz arquivo LICENSE. **Não empacotado**: `rea-video clone` baixa o commit fixado, e `rea-video setup` instala as dependências num venv próprio. |
| yt-dlp | Unlicense. **Não empacotado** no pacote do motor: `media fetch` instala o wheel fixado por sha256 num venv próprio, no cache do usuário. |
| TinyFish CLI (`@tiny-fish/cli`) | Não declara licença no pacote npm (sem campo `license` e sem arquivo LICENSE, lido em 2026-11-05 na 0.57.0). **Não empacotado**: o usuário instala o binário, e o motor só o chama. |
| Postiz | Programa externo, AGPL. Não empacotado. |

A checagem de importação em `scripts/licenses.py --imports` reprova código Python que importe OpenMontage, VoiceStudio ou Postiz.

## LangFlow (cliente externo)

O LangFlow é cliente externo e **não empacotado** pelo repositório. O usuário o instala à parte (receita em [how-to/langflow.md](../how-to/langflow.md)). O componente em `examples/langflow/` só chama o CLI `simplicio-video` como programa separado. O motor não depende do LangFlow, e nenhum código dele é redistribuído aqui.

Por isso o LangFlow **não entra em [../licenses.md](../licenses.md)**: aquela tabela é gerada a partir das dependências Python que o pacote instala, e o LangFlow não é uma delas. A licença do LangFlow vale para quem o instala. Esta entrega não a verificou.
