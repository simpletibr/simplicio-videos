"""simplicio-video command line (argparse). Every subcommand has an explicit, complete --help."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import CONTRACT_SCHEMA_ID, HYPERFRAMES, __version__, clone, edit, moneyprinter, montage, opencut, paths, toonflow
from .aio import positive_int

SCHEMA_REL = "src/simplicio_video/data/schema/contract.schema.json"

MAIN_DESC = f"""\
simplicio-video {__version__} — vídeo determinístico a partir de um contrato YAML ({CONTRACT_SCHEMA_ID}).
O LLM raciocina e escreve o contrato; o CLI executa. Mesma entrada => mesma saída.

Fluxo completo:
  1. init      gera o esqueleto do contrato a partir de um template de setor
  2. (autor)   preenche os TODO só com fatos de clients/<cliente>/coleta/
  3. validate  JSON Schema + assets existem + soma das durações + cada fala cabe na cena (sem acelerar)
  4. voice     gera/cacheia as falas (file | local | gemini API) e grava timing.lock.json com as durações reais
  5. render    contrato -> composição HyperFrames -> frames -> ffmpeg (trilha/SFX/voz, -14 LUFS)
               backend PADRÃO: local (referência de hash, sem custo). Opcionais, para clientes via créditos:
               kaggle (cota grátis semanal) | colab-cli (CLI oficial do Colab, pago em unidades) | colab (bundle manual)
  run          tudo de uma vez: voice -> validate --need-lock -> render (termina no MP4; o upload não é do motor)
  clone        trilha Clone (Hypit AI): clonagem de vídeos com agentes de IA (https://github.com/hypit-ai/hypit)
  montage      trilha Montage (OpenMontage): produção de vídeo com agentes de IA (https://github.com/calesthio/OpenMontage)
  edit         video-use: edita qualquer MP4 (HyperFrames, OpenMontage, OpenCut) por EDL (https://github.com/browser-use/video-use)
  opencut      editor open-source OpenCut para acabamento manual (https://github.com/OpenCut-app/OpenCut)
  formats      biblioteca de 50 formatos de anúncio (Drive) e pedido para adaptar uma copy a um formato
  swap         troca o personagem de um vídeo por um avatar de referência (gemini, fal, wavespeed, kie, alibaba); gasta só com --autorizo --yes
  jobs         tarefas em segundo plano (swap run, voice) num processo separado: submit, status, list, cancel, result
  toonflow     Toonflow (MIT): estúdio open-source de séries e vídeos com IA; serve pede --lan (https://github.com/HBAI-Ltd/Toonflow-app)
  moneyprinter MoneyPrinterTurbo (MIT): tema vira vídeo curto (roteiro por LLM, voz, estoque); serve só em 127.0.0.1, pede --lan para a rede (https://github.com/harry0703/MoneyPrinterTurbo)
  social       redes sociais sem postar: provedores (Real Oficial padrão, Zernio), plano de postagem com limites por rede, receita de chamadas MCP
  openverse    biblioteca de imagens e áudio do Openverse revisada por pedido: search, get, library (list, show, review, export, credits); licença das fontes, não é parecer jurídico
  busca        pesquisa e leitura de páginas na internet pelo CLI tinyfish (TinyFish), com fonte e data por resultado e teto de chamadas por dia: consulta, pagina, status, log; a consulta é enviada a um terceiro
  mcp          servidor MCP (stdio) com as tools video.init/validate/voice/render/run/list/clone/montage/edit/opencut/formats/swap/jobs/toonflow/moneyprinter/social/openverse/busca
  status       ferramentas (instaladas, versão, versão fixada) e, com CONTRATO, o estado do render (--json para o looping)
  install      copia as skills do simplicio-video para o host do agente (12 hosts; projeto, ou o home com --global; sem hooks); ambiente do checkout: scripts/dev_install.sh
  update       pacote pip: PyPI e reinstala as skills; checkout git: recusa (git pull e scripts/dev_install.sh); --check sai 0, 10 ou 2
  doctor       diagnóstico: Python, Node 22, ffmpeg com libass, disco, portas, credenciais, workspace
  setup        primeira execução: cria o workspace (tema, idioma, autonomia L1, orçamentos zero)

Schema do contrato: {SCHEMA_REL} (no checkout do plugin; ver `simplicio-video validate --help`).
Skill para LLMs: skills/simplicio-video/SKILL.md"""

MAIN_EPILOG = """\
exemplos:
  simplicio-video list templates
  simplicio-video init <cliente> <Campanha> --template saude-odontologia --nome "<Nome do cliente>" --ano 2026
  simplicio-video validate clients/<cliente>/<campanha>/contract.yaml
  simplicio-video voice clients/<cliente>/<campanha>/contract.yaml --provider local
  simplicio-video render clients/<cliente>/<campanha>/contract.yaml
  simplicio-video render clients/<cliente>/<campanha>/contract.yaml --backend kaggle
  simplicio-video run clients/<cliente>/<campanha>/contract.yaml --provider gemini
  simplicio-video render contract.yaml --preview          # 540x960, marca d'água e crédito final do contrato (marca)

ambiente:
  SIMPLICIO_VIDEO_HOME  checkout do plugin (dados em src/simplicio_video/data/); padrão: os dados do próprio pacote
  SIMPLICIO_TTS_PY      python com kokoro-onnx para --provider local
  GEMINI_API_KEY        --provider gemini (aistudio.google.com/apikey; nunca commitar)
  KAGGLE_USERNAME, KAGGLE_API_TOKEN (ou ~/.kaggle/access_token)   --backend kaggle
  SIMPLICIO_COLAB_AUTH  oauth2|adc para --backend colab-cli (padrão do CLI colab)
  SIMPLICIO_FFMPEG_DIR  ffmpeg travado no render local (mesmo build em todo backend = mesmos bytes)
  SIMPLICIO_FFMPEG_URL/_SHA256  o mesmo ffmpeg (.tar.xz) baixado e conferido pelos backends remotos
  SV_WORKERS / SV_BROWSER_GPU  workers de captura (auto = núcleos-2) / raster de GPU no Chrome (1 = sem determinismo)
custo por vídeo (medido e oficial): docs/custos.md · credenciais: docs/decisoes/ADR-0003-fluxo-100-script.md"""


BACKENDS = ["local", "kaggle", "colab-cli", "colab"]


def do_render(c, backend: str, out=None, quality=None, workdir=None, gpu=False, accelerator=None, timeout=3600,
              gpu_encode="auto", log=print) -> dict:
    """Dispatch one render to a backend (shared by render, run and the MCP server)."""
    from . import remote, render
    acc = None if (accelerator or "").lower() in ("none", "cpu") else accelerator
    if backend == "colab":
        return render.render_colab(c, out=out, quality=quality, gpu_encode=gpu_encode, log=log)
    if backend == "kaggle":
        return remote.render_kaggle(c, out=out, quality=quality, timeout_s=timeout, gpu_encode=gpu_encode, log=log,
                                    accelerator="NvidiaTeslaT4" if accelerator is None else acc)
    if backend == "colab-cli":
        return remote.render_colab_cli(c, out=out, quality=quality, timeout_s=timeout, gpu_encode=gpu_encode, log=log,
                                       gpu="T4" if accelerator is None else acc)
    return render.render_local(c, out=out, quality=quality, workdir=workdir, gpu=gpu, log=log)


class Fmt(argparse.RawDescriptionHelpFormatter):
    def __init__(self, prog):
        super().__init__(prog, max_help_position=34, width=110)


def _contract_arg(p):
    p.add_argument("contrato", metavar="CONTRATO.yaml",
                   help=f"caminho do contrato YAML ({CONTRACT_SCHEMA_ID}; schema em {SCHEMA_REL})")


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="simplicio-video", description=MAIN_DESC, epilog=MAIN_EPILOG, formatter_class=Fmt)
    ap.add_argument("--version", action="store_true",
                    help="mostra a versão do motor e sai (com --json: {version, engine})")
    ap.add_argument("--json", dest="ver_json", action="store_true", help="com --version: imprime {version, engine} em JSON")
    sub = ap.add_subparsers(dest="cmd", metavar="COMANDO", title="comandos (na ordem do fluxo)")

    p = sub.add_parser("init", formatter_class=Fmt, help="gera o esqueleto de contrato para <cliente> <campanha>",
        description="Gera um contrato-esqueleto a partir de templates/<template>/template.json: cenas, padrões de motion,\n"
                    "voz sugerida e trilha padrão. Campos com TODO precisam ser preenchidos\n"
                    f"(validate falha enquanto houver TODO). Schema: {SCHEMA_REL}.",
        epilog="exemplos:\n"
               "  simplicio-video init <cliente> <Campanha> --template saude-odontologia --nome \"<Nome do cliente>\"\n"
               "  simplicio-video init <cliente> <Campanha> --template assistencia-tecnica-games --ano 2026 \\\n"
               "      --out clients/<cliente>/<campanha>/contract.yaml")
    p.add_argument("cliente", help="slug do cliente (pasta em clients/, ex.: clinica-sorriso)")
    p.add_argument("campanha", help="campanha em Title_Case com underscore, sem acento (ex.: Dia_Criancas)")
    p.add_argument("--template", "-t", required=True, help="id do template de setor (ver `simplicio-video list templates`)")
    p.add_argument("--nome", help="nome de exibição do cliente (padrão: TODO)")
    p.add_argument("--drive-nome", help="NOME_CLIENTE no Drive (padrão: derivado de --nome/slug, ex.: Clinica_Sorriso)")
    p.add_argument("--ano", type=int, help="ano da campanha (padrão: ano atual)")
    p.add_argument("--out", "-o", type=Path, help="onde gravar (padrão: clients/<cliente>/<campanha-slug>/contract.yaml, no checkout ou, instalado por pip, na pasta atual)")
    p.add_argument("--force", action="store_true", help="sobrescreve um contrato existente")

    p = sub.add_parser("validate", formatter_class=Fmt, help="valida o contrato (schema, assets, durações, falas)",
        description=f"Valida o contrato contra o JSON Schema ({SCHEMA_REL}) e checa:\n"
                    "  - template existe e tem composição renderizável; ids de cena batem com a composição\n"
                    "  - padrões de motion existem em motion/patterns/ (bloco exige block.html)\n"
                    "  - todos os assets/logo existem (caminhos relativos ao contrato)\n"
                    "  - asset do Openverse (bloco openverse: {id, pedido}): id na biblioteca, sha256 do arquivo, veredito aprovado para o pedido,\n"
                    "    aceite da restrição e crédito em CREDITS-openverse.md, sem rede; arquivo em assets/openverse/ sem o bloco é recusado\n"
                    "  - soma de cenas[].duracao_s == formato.duracao_s\n"
                    "  - cada fala: inicio_s + max_s cabe na cena (+ J-cut voz.jcut_max_s, padrão 0,15 s);\n"
                    "    com timing.lock.json, a duração real <= max_s (a voz NUNCA é acelerada)\n"
                    "  - nenhum bloco drive (a entrega no Drive fica fora do motor); nenhum TODO\n"
                    "--json: stdout só o objeto {ok, contrato, errors, warnings}; erro vira {ok: false, error: {code, message}}.\n"
                    "  Códigos de erro (error.code): CONTRATO_NAO_ENCONTRADO, CONTRATO_INVALIDO, RENDER_FALHOU, FERRAMENTA_AUSENTE.\n"
                    "Saída 0 = válido, 1 = erros.",
        epilog="exemplos:\n  simplicio-video validate clients/<cliente>/<campanha>/contract.yaml\n"
               "  simplicio-video validate contract.yaml --json      # relatório em JSON\n"
               "  simplicio-video validate contract.yaml --need-lock # exige timing.lock.json (antes do render)")
    _contract_arg(p)
    p.add_argument("--need-lock", action="store_true", help="falha se timing.lock.json faltar ou estiver desatualizado")
    p.add_argument("--json", action="store_true", help="imprime {ok, errors, warnings} em JSON")

    p = sub.add_parser("voice", formatter_class=Fmt, help="gera/cacheia as falas e grava timing.lock.json",
        description="Gera cada fala (cenas[].fala), trata (corte de silêncio + cadeia ffmpeg voz.processamento, 48 kHz mono)\n"
                    "e grava em voz.cache_dir (padrão assets/audio/voz/, versionado). Mede a duração real e grava\n"
                    "timing.lock.json ao lado do contrato. Fala maior que max_s = erro (sem time-stretch).\n"
                    "providers:\n"
                    "  file        WAVs externos (Gemini no Google AI Studio): voz.providers.file.dir/line-01.wav ... (ordem das falas)\n"
                    "  local       TTS local provisório (Kokoro, voz voz.voice ou voz.providers.local.voice, ex.: pf_dora)\n"
                    "  gemini      API Gemini TTS (GEMINI_API_KEY de aistudio.google.com/apikey; cota grátis serve; Google AI Pro NÃO\n"
                    "              inclui API). Modelo voz.providers.gemini.model (padrão gemini-3.8-flash-tts), voz, estilo em\n"
                    "              speech_metadata; api interactions (padrão) ou generate_content. WAV 24 kHz guardado em file.dir\n"
                    "  elevenlabs  stub (gere fora e use file)\n"
                    "  xai         stub (gere fora e use file)",
        epilog="exemplos:\n  simplicio-video voice contract.yaml                    # provider do contrato (voz.provider)\n"
               "  simplicio-video voice contract.yaml --provider file    # depois de baixar line-01..NN.wav do AI Studio\n"
               "  simplicio-video voice contract.yaml --force vo2        # refaz só a vo2")
    _contract_arg(p)
    p.add_argument("--provider", "-p", choices=["file", "local", "gemini", "voxcpm", "openvoice", "voicestudio", "elevenlabs", "xai"], help="override voz.provider")
    p.add_argument("--force", action="store_true", help="ignora o cache (com ids: só esses)")
    p.add_argument("--concurrency", type=positive_int, default=None, metavar="N",
                   help="falas geradas ao mesmo tempo, só em provedor de rede (gemini; padrão 4; 1 = serial). Provedor local é sempre serial")
    p.add_argument("only", nargs="*", metavar="FALA_ID", help="ids de fala para refazer com --force (ex.: vo2 vo4)")

    p = sub.add_parser("render", formatter_class=Fmt, help="compila e renderiza (padrão local; kaggle/colab-cli/colab opcionais via créditos)",
        description="Compila contrato + timing.lock.json + template (templates/<id>/composition) + blocos de motion +\n"
                    "assets numa composição HyperFrames (build/simplicio-video/), sintetiza trilha/SFX e mixa a voz\n"
                    f"(engine build.mjs, semente fixa), renderiza os frames ({HYPERFRAMES}) e masteriza com ffmpeg\n"
                    "(loudnorm 2 passes, alvo trilha.master: -14 LUFS / TP -1,5). Grava render.manifest.json ao lado do\n"
                    "contrato: hash do contrato, de cada input compilado, das ferramentas e do vídeo/áudio decodificados.\n"
                    "Com ativos do Openverse (asset com openverse: {id, pedido}), o manifesto traz a procedência de cada um (chave openverse)\n"
                    "e os créditos vão para <saida>.CREDITS-openverse.md ao lado do MP4.\n"
                    "backends (todos sem navegador, exceto colab):\n"
                    "  local      PADRÃO. Renderiza aqui (CPU; --gpu usa encoder de GPU do HyperFrames se houver).\n"
                    "             Referência de hash, sem custo (vídeo de 600 frames: 76,5 s em 8 núcleos).\n"
                    "  -- opcionais, para clientes via créditos (custo e tempo medidos em docs/custos.md) --\n"
                    "  kaggle     bundle -> dataset privado Kaggle -> kernel (T4, internet) -> poll -> baixa o MP4.\n"
                    "             Precisa do CLI `kaggle`, KAGGLE_USERNAME + token (KAGGLE_API_TOKEN ou ~/.kaggle/access_token)\n"
                    "             e conta com telefone verificado (internet no kernel). --accelerator none = CPU (sem cota de GPU).\n"
                    "  colab-cli  Colab oficial por CLI (`pip install google-colab-cli`): new --gpu T4 -> upload -> exec ->\n"
                    "             download -> stop (sempre). Login Google uma vez (código colado no terminal).\n"
                    "  colab      NÃO renderiza: gera <saida>.colab-bundle.zip para colab/render.ipynb no navegador (manual)\n"
                    "Remotos baixam final.mp4 e gravam o mesmo render.manifest.json (+ usage: backend, GPU, tempos) para créditos.\n"
                    "--json: stdout só o objeto {ok, contrato, backend, preview, output, manifest}; erro vira\n"
                    "  {ok: false, error: {code, message}}. Códigos de erro (error.code): CONTRATO_NAO_ENCONTRADO,\n"
                    "  CONTRATO_INVALIDO, RENDER_FALHOU, FERRAMENTA_AUSENTE. Logs de render vão para stderr; exit 1 = erro.",
        epilog="exemplos:\n  simplicio-video render contract.yaml\n"
               "  simplicio-video render contract.yaml --out /tmp/teste.mp4 --quality draft\n"
               "  simplicio-video render contract.yaml --backend kaggle                   # opcional: T4 grátis (cota semanal)\n"
               "  simplicio-video render contract.yaml --backend kaggle --accelerator none\n"
               "  simplicio-video render contract.yaml --backend colab-cli --accelerator T4\n"
               "  simplicio-video render contract.yaml --backend colab   # -> out/<nome>.colab-bundle.zip\n"
               "  simplicio-video render contract.yaml --json            # resultado em JSON (logs no stderr)\n"
               "  simplicio-video render contract.yaml --preview         # prévia 540x960 + marca d'água (marca.dagua) e crédito final (marca.credito)")
    _contract_arg(p)
    p.add_argument("--backend", "-b", choices=BACKENDS, default="local", help="onde renderizar (padrão: local; kaggle/colab-cli/colab são opcionais, via créditos)")
    p.add_argument("--out", "-o", type=Path, help="MP4 de saída (local) ou .zip do bundle (colab); padrão: saida.arquivo")
    p.add_argument("--accelerator", help="kaggle: NvidiaTeslaT4 (padrão) | NvidiaL4 | none; colab-cli: T4 (padrão) | L4 | A100 | none")
    p.add_argument("--timeout", type=int, default=3600, help="kaggle/colab-cli: limite do render remoto em s (padrão 3600)")
    p.add_argument("--quality", "-q", choices=["draft", "looks", "delivery"], help="qualidade HyperFrames (padrão: saida.qualidade)")
    p.add_argument("--gpu", action="store_true", help="local: encoder de GPU do HyperFrames (--gpu); muda os bytes do vídeo")
    p.add_argument("--gpu-encode", choices=["auto", "1", "0"], default="auto",
                   help="kaggle/colab-cli/colab: NVENC no encode (auto = usa se o teste de encode passar; 0 = libx264, "
                        "necessário p/ comparar frames com o local). A captura (Chrome) é CPU de qualquer jeito")
    p.add_argument("--workdir", type=Path, help="pasta da composição compilada (padrão: <contrato>/build/simplicio-video)")
    p.add_argument("--json", action="store_true",
                   help="imprime o resultado em JSON no stdout (ok, output, manifest; com erro, error.code); os logs vão para stderr")
    p.add_argument("--preview", action="store_true",
                   help="prévia (só local): render draft -> 540x960, 30 fps, x264 crf 30, marca d'água diagonal (marca.dagua, "
                        "padrão 'Prévia') + selo nos cantos + cartão final com marca.credito.texto (2,5 s; sem crédito, sem cartão). "
                        "Padrão --out: <saida.arquivo>-previa.mp4. Grava preview.manifest.json "
                        "(não toca no render.manifest.json da entrega)")

    p = sub.add_parser("run", formatter_class=Fmt, help="voice -> validate -> render num comando só (para no MP4)",
        description="Fluxo 100% script: validate -> voice (provider do contrato ou --provider, ex.: gemini) ->\n"
                    "validate --need-lock -> render (--backend local|kaggle|colab-cli|colab). Termina no render: o MP4 fica\n"
                    "em saida.arquivo. O upload no Drive não é feito pelo motor; é feito pela ferramenta de operação.\n"
                    "--json: stdout só o objeto JSON do resumo (ok, contrato, ...); erro vira {ok: false, error: {code, message}}.\n"
                    "  Códigos de erro (error.code): CONTRATO_NAO_ENCONTRADO, CONTRATO_INVALIDO, RENDER_FALHOU, FERRAMENTA_AUSENTE.\n"
                    f"Schema: {SCHEMA_REL}.",
        epilog="exemplos:\n  simplicio-video run contract.yaml                                   # voz do contrato, render local\n"
               "  simplicio-video run contract.yaml --provider gemini                    # local (padrão)\n"
               "  simplicio-video run contract.yaml --provider gemini --backend kaggle   # opcional (créditos)\n"
               "  simplicio-video run contract.yaml --backend colab-cli --json")
    _contract_arg(p)
    p.add_argument("--provider", "-p", choices=["file", "local", "gemini", "voxcpm", "openvoice", "voicestudio"], help="override voz.provider")
    p.add_argument("--force-voice", action="store_true", help="regera todas as falas (ignora o cache)")
    p.add_argument("--backend", "-b", choices=BACKENDS, default="local", help="onde renderizar (padrão: local; kaggle/colab-cli/colab são opcionais, via créditos)")
    p.add_argument("--accelerator", help="ver `render --help` (none = CPU)")
    p.add_argument("--quality", "-q", choices=["draft", "looks", "delivery"], help="qualidade HyperFrames")
    p.add_argument("--timeout", type=int, default=3600, help="limite do render remoto em s")
    p.add_argument("--json", action="store_true", help="imprime o resumo em JSON no stdout (com erro, error.code); os logs vão para stderr")

    p = sub.add_parser("clone", formatter_class=Fmt, help="trilha Clone (Hypit AI): clonagem de vídeos com agentes de IA",
        description="Invoca o Hypit AI (https://github.com/hypit-ai/hypit) para clonar vídeos de referência e gerar fluxos de trabalho completos.",
        epilog="exemplos:\n  simplicio-video clone --help\n  simplicio-video clone video.mp4")
    p.add_argument("args", nargs=argparse.REMAINDER, help="argumentos repassados ao CLI do Hypit AI")

    p = sub.add_parser("montage", formatter_class=Fmt, help="trilha Montage (OpenMontage): produção de vídeo com agentes de IA",
        description="Invoca o OpenMontage (https://github.com/calesthio/OpenMontage) para pipelines e agentes de produção de vídeo (Backlot, Remotion, HyperFrames).",
        epilog="exemplos:\n  simplicio-video montage --help\n  simplicio-video montage clone\n  simplicio-video montage open\n  simplicio-video montage serve --port 8000")
    p.add_argument("args", nargs=argparse.REMAINDER, help="argumentos repassados ao OpenMontage")

    p = sub.add_parser("edit", formatter_class=Fmt, help="edição por EDL com video-use sobre qualquer MP4",
        description="Encadeia tools/video-use (https://github.com/browser-use/video-use): setup, transcribe, pack, render, verify. A decisão de corte fica no edl.json versionado.",
        epilog="exemplos:\n  simplicio-video edit setup\n  simplicio-video edit render edit/edl.json -o out/final.raw.mp4")
    p.add_argument("args", nargs=argparse.REMAINDER, help="setup | transcribe | pack | render | verify")

    p = sub.add_parser("opencut", formatter_class=Fmt, help="editor OpenCut (open-source) para acabamento manual",
        description="Clona e sobe o OpenCut (https://github.com/OpenCut-app/OpenCut, MIT; usa o opencut-classic até o rewrite ter API).",
        epilog="exemplos:\n  simplicio-video opencut clone\n  simplicio-video opencut dev")
    p.add_argument("args", nargs=argparse.REMAINDER, help="clone [dir] | dev | where")

    p = sub.add_parser("toonflow", formatter_class=Fmt, help="Toonflow (MIT): estúdio de séries e vídeos com IA, app web local",
        description="Clona e sobe o Toonflow (https://github.com/HBAI-Ltd/Toonflow-app, MIT) no commit fixado em tools.py. "
                    "Precisa de Bun. O serve escuta em 0.0.0.0:3000 sem login, por isso só sobe com --lan. "
                    "Fica fora do render determinístico.",
        epilog="exemplos:\n  simplicio-video toonflow clone\n  simplicio-video toonflow serve --lan\n  simplicio-video toonflow where")
    p.add_argument("args", nargs=argparse.REMAINDER, help="clone [dir] | serve --lan | where")

    p = sub.add_parser("moneyprinter", formatter_class=Fmt, help="MoneyPrinterTurbo (MIT): tema vira vídeo curto, trilha externa de apoio",
        description="Clona, prepara e sobe o MoneyPrinterTurbo (https://github.com/harry0703/MoneyPrinterTurbo, MIT) no commit fixado em tools.py. "
                    "Exige Python 3.11 ou mais novo; o setup cria um venv isolado e copia o config.toml sem chave nenhuma. "
                    "O upstream escuta em 0.0.0.0 por padrão na API; o serve força 127.0.0.1 (WebUI 8501, API 8080) e só abre para a rede com --lan. "
                    "As chaves de API nunca são impressas. "
                    "Fica fora do render determinístico.",
        epilog="exemplos:\n  simplicio-video moneyprinter clone\n  simplicio-video moneyprinter setup\n  simplicio-video moneyprinter serve --api\n  simplicio-video moneyprinter status")
    p.add_argument("args", nargs=argparse.REMAINDER, help="clone [dir] | setup | serve [--webui] [--api] [--lan] [--host H] | where | status")

    p = sub.add_parser("formats", formatter_class=Fmt, help="biblioteca de 50 formatos de anúncio (Drive) e pedido para adaptar uma copy",
        description="Os 50 formatos da pasta 'Swipe File - 50 Formatos' (Drive): descrição, estrutura e o exemplo de cada um. "
                    "`prompt` monta o pedido para adaptar uma copy ao formato; quem adapta é o LLM, não o CLI.",
        epilog="exemplos:\n  simplicio-video formats list --objetivo venda\n  simplicio-video formats show caixinha\n  simplicio-video formats prompt caixinha --copia roteiro.txt")
    p.add_argument("args", nargs=argparse.REMAINDER, help="list [--objetivo ...] | show <id> | prompt <id> --copia <arquivo|->")

    from . import swap as _swap
    p = sub.add_parser("swap", formatter_class=Fmt, help="troca o personagem de um vídeo por um avatar (agnóstico de fornecedor)",
        description=_swap.HELP_DESC, epilog=_swap.HELP_EPILOG)
    p.add_argument("args", nargs=argparse.REMAINDER, help="providers | estimate | run | status <manifesto>")

    from . import jobs as _jobs
    p = sub.add_parser("jobs", formatter_class=Fmt, help="tarefas em segundo plano (swap run, voice) num processo separado",
        description=_jobs.HELP_DESC, epilog=_jobs.HELP_EPILOG)
    p.add_argument("args", nargs=argparse.REMAINDER, help="submit | status | list | cancel | result | clean")

    from . import social as _social
    p = sub.add_parser("social", formatter_class=Fmt, help="redes sociais sem postar: provedores, plano de postagem e receita de chamadas MCP",
        description=_social.HELP_DESC, epilog=_social.HELP_EPILOG)
    p.add_argument("args", nargs=argparse.REMAINDER, help="providers | plan | check <plano> | recipe <plano>")

    from . import openverse as _openverse
    p = sub.add_parser("openverse", formatter_class=Fmt, help="biblioteca de imagens e áudio do Openverse, revisada por pedido",
        description=_openverse.HELP_DESC, epilog=_openverse.HELP_EPILOG)
    p.add_argument("args", nargs=argparse.REMAINDER, help="search | get <id> | library list|show|review|export|credits")

    from . import busca_ajuda as _busca  # the help text only: `busca` itself is imported when the command runs
    p = sub.add_parser("busca", formatter_class=Fmt, help="pesquisa e leitura de páginas na internet (TinyFish), com procedência e teto diário",
        description=_busca.HELP_DESC, epilog=_busca.HELP_EPILOG)
    p.add_argument("args", nargs=argparse.REMAINDER, help="consulta \"<texto>\" | pagina <url> | status | log")

    p = sub.add_parser("mcp", formatter_class=Fmt, help="servidor MCP (stdio) para o simplicio-runtime",
        description="Expõe o CLI como servidor MCP (stdio): tools video.init, video.validate, video.voice, video.render,\n"
                    "video.run, video.list. Requer `pip install -e .[mcp]` (SDK Python `mcp`).\n"
                    f"Contratos seguem {SCHEMA_REL}.",
        epilog="exemplos:\n  simplicio-video mcp                  # stdio (o runtime lança este processo)\n"
               "  simplicio-video-mcp                  # mesmo servidor, entrypoint dedicado")

    p = sub.add_parser("status", formatter_class=Fmt, help="ferramentas instaladas, versões fixadas e estado do render",
        description="Estado do motor para o looping: ferramentas (OpenMontage, OpenCut, Hypit, ffmpeg, node) com\n"
                    "installed, version, pinned (versão fixada em tools.py ou SIMPLICIO_<NOME>_REF) e pinned_source.\n"
                    "Com CONTRATO, acrescenta o estado do render (render.manifest.json ao lado do contrato): rendered,\n"
                    "contract_sha256 e finished_at. Ferramenta ausente não é erro: sai com 0. Sai com 2 se o contrato não existir.",
        epilog="exemplos:\n  simplicio-video status\n  simplicio-video status --json\n"
               "  simplicio-video status --json clients/<cliente>/<campanha>/contract.yaml")
    p.add_argument("contrato", nargs="?", metavar="CONTRATO.yaml", help="contrato cujo render (render.manifest.json) será lido")
    p.add_argument("--json", action="store_true", help="imprime tools (e render, com CONTRATO) em JSON")

    p = sub.add_parser("list", formatter_class=Fmt, help="lista templates, padrões de motion, providers de voz ou ângulos de anúncio",
        description="Catálogos do plugin: templates/ (renderizável = tem composição), motion/catalog.json, providers de voz, "
                    "ângulos de anúncio (data/angles, 50 em 5 grupos; só fatos por marcador).",
        epilog="exemplos:\n  simplicio-video list templates\n  simplicio-video list motion --json\n  simplicio-video list voices\n"
               "  simplicio-video list angles --grupo prova --json")
    p.add_argument("what", choices=["templates", "motion", "voices", "angles"], help="catálogo a listar")
    p.add_argument("--json", action="store_true", help="saída em JSON")
    p.add_argument("--grupo", choices=["problema", "prova", "desejo", "decisao", "estrategia"],
                   help="só com angles: lista só os ângulos desse grupo")

    p = sub.add_parser("install", formatter_class=Fmt, help="copia as skills do simplicio-video para o host do agente (o projeto, ou o home com --global)",
        description="Copia as skills empacotadas (simplicio-video e simplicio-video-social) para o host do agente e grava o recibo de posse\n"
                    ".simplicio-video/install-ownership.json, como o `install` do simplicio-loop. Por padrão instala no projeto (--target, padrão: a\n"
                    "pasta atual) em .claude/skills/ e, para o host que precisa, no arquivo de entrada dele (AGENTS.md, GEMINI.md, CONVENTIONS.md,\n"
                    ".github/copilot-instructions.md ou .kiro/steering/simplicio-video.md). Um arquivo de entrada que já existe não recebe\n"
                    "apontador: fica como está. Com --global instala nas 11 pastas de skills do loop sob o home (~/.claude/skills, ~/.codex/skills,\n"
                    "~/.cursor/skills, ~/.grok/skills, ~/.agents/skills, ~/.copilot/skills, ~/.vscode/simplicio-skills, ~/.config/opencode/skills,\n"
                    "~/.config/amp/skills, ~/.kiro/steering e ~/.simplicio-loop/skills); com --global o --host é ignorado (o loop faz o mesmo). Em cada\n"
                    "pasta o install cria o que falta (entra no recibo com o sha256), atualiza só a cópia que é dele e que ninguém editou, deixa em\n"
                    "paz o que já existia ou que você editou e nunca apaga um arquivo extra seu; uma pasta secundária que é link é pulada, e\n"
                    "~/.claude/skills que é link recusa tudo.\n"
                    "Hosts (--host, padrão claude; all = todos): claude, codex, cursor, vscode, grok, kiro, antigravity, opencode, gemini, aider,\n"
                    "simplicio_agent, openclaw. O simplicio-video não tem hooks: só skills.\n"
                    "O install nunca sobrescreve nem apaga o que não é dele: outras skills, o seu AGENTS.md, uma SKILL.md que já existia ou que\n"
                    "você editou, um link simbólico. O install deixa isso em paz (left_alone) e diz. O recibo guarda o sha256 de cada arquivo: o --uninstall e\n"
                    "o --prune-project-copies só removem o que o recibo registra, que o registro de hosts consegue produzir e que ainda tem o sha256\n"
                    "gravado; um recibo com outro caminho (.git/config, src/app.py...) é recusado inteiro, e um install por cima dele o ignora.\n"
                    "As pastas que o install cria (.claude/skills, a da skill e .simplicio-video) nunca são link: com link ele recusa (exit 2) e\n"
                    "não escreve nada. A pasta base do host (~/.claude) pode ser link para o seu repositório de dotfiles: o install a resolve uma\n"
                    "vez, escreve no caminho real e o recibo o grava. Dois installs ao mesmo tempo no mesmo alvo esperam um pelo outro\n"
                    "(.simplicio-video/install.lock).\n"
                    "--verify confere os arquivos instalados com o recibo e com o pacote: se o alvo nunca foi instalado, uma skill foi alterada, falta\n"
                    "um arquivo ou o recibo é lixo, sai com exit 1, ok false e a lista do que difere (problems).\n"
                    "Saída: --check 0 em dia, 10 com mudança pendente; --dry-run 0 sem escrever; 1 se a instalação falhar (host desconhecido,\n"
                    "escrita negada, recibo em que não se confia, --verify que acha diferença); 2 para argumento inválido ou link nas pastas que o\n"
                    "install cria. --json imprime UM documento simplicio.video-install-plan/v1 (as mesmas chaves do plano do loop), também no\n"
                    "erro. Funciona igual num checkout e num pacote do pip. O ambiente de desenvolvimento do checkout (o .venv) é\n"
                    "`bash scripts/dev_install.sh` (Windows: `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\\dev_install.ps1`). No\n"
                    "fim, se o setup nunca rodou, ele roda num terminal e senão diz como rodar.",
        epilog="exemplos:\n  simplicio-video install --check\n  simplicio-video install --dry-run --json\n  simplicio-video install\n"
               "  simplicio-video install --host codex --target ~/meu-projeto\n  simplicio-video install --global\n"
               "  simplicio-video install --global --prune-project-copies --target ~/meu-projeto\n  simplicio-video install --verify\n"
               "  simplicio-video install --uninstall --dry-run")
    p.add_argument("--target", default=".", metavar="DIR", help="pasta do projeto onde instalar (padrão: a pasta atual)")
    p.add_argument("--global", dest="globally", action="store_true", help="instala nas 11 pastas de skills sob o home (~/.claude/skills, ~/.codex/skills...) em vez do projeto")
    p.add_argument("--host", default="claude", metavar="HOST", help="id do host ou all (padrão: claude); com --global é ignorado")
    p.add_argument("--dry-run", action="store_true", help="mostra o plano e não escreve nada; sai com 0")
    p.add_argument("--check", action="store_true", help="não escreve nada; sai com 0 se está em dia e com 10 se há mudança pendente")
    p.add_argument("--json", action="store_true", help="imprime UM documento JSON (simplicio.video-install-plan/v1), também no erro")
    p.add_argument("--verify", action="store_true",
                   help="confere os arquivos instalados com o recibo e com o pacote (exit 1 e a lista se algo difere); não escreve nada")
    p.add_argument("--uninstall", action="store_true",
                   help="remove só o que o recibo registra e ainda tem o sha256 gravado; com --dry-run, lista e não remove")
    p.add_argument("--prune-project-copies", action="store_true",
                   help="com --global: remove a cópia do projeto (--target) que o recibo dele registra, depois de instalar no home")

    p = sub.add_parser("update", formatter_class=Fmt, help="atualiza: pip (PyPI) num pacote instalado; num checkout git recusa e diz o que rodar",
        description="Segue o `update` do simplicio-loop. Num pacote instalado por pip: python -m pip install --upgrade \"simplicio-video==<última\n"
                    "release>\" (PyPI; a última release vem do GitHub Releases) e, depois, `simplicio-video install --global`, que reinstala as skills\n"
                    "em ~/.claude/skills sem apagar nada que não seja do recibo. Um Python gerenciado pelo sistema (PEP 668) é recusado com as saídas\n"
                    "possíveis, e um Python sem pip (um `uv tool install`) também (exit 2): use `uv tool upgrade simplicio-video` ou `pipx upgrade`.\n"
                    "Num checkout git ou instalação editável o update RECUSA e sai com 2: o que atualiza é, dentro do checkout, `git pull` e\n"
                    "`bash scripts/dev_install.sh` (Windows: `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\\dev_install.ps1`; o Windows de\n"
                    "cliente vem com a política Restricted, e o Bypass vale só para esse processo). Nada é puxado, reconstruído nem apagado.\n"
                    "Saída: --check 0 em dia, 10 com atualização, 2 erro; recusa 2; falha de rede 2 com --check, senão 1. Versão instalada mais nova\n"
                    "que a última release (o PyPI sai antes do GitHub Release) é em dia: 0. --force reinstala a release mesmo em dia e permite\n"
                    "downgrade (pip): só o nosso pacote, com --force-reinstall --no-deps, e só quando não há versão mais nova (com uma nova, o\n"
                    "--upgrade normal, que traz as dependências dela). --check grava o resultado em update-check.json (em $SIMPLICIO_VIDEO_DATA), que o doctor lê sem rede; num\n"
                    "checkout ele pergunta ao git quantos commits são novos (git fetch; alterações locais não atrapalham). --dry-run só mostra o plano e\n"
                    "sai com 0 no pacote (num checkout mostra a recusa). SIMPLICIO_OFFLINE=1 bloqueia toda a rede, também o git fetch do checkout\n"
                    "(--check sai com 2). Todo git do `--check` leva --no-optional-locks (para não regravar o .git/index); o git anterior à 2.15,\n"
                    "que não conhece a opção, é chamado de novo uma vez sem ela. Versão instalada de desenvolvimento ou pré-release (0.5.0rc1) é\n"
                    "anterior à release final (PEP 440).",
        epilog="exemplos:\n  simplicio-video update --check\n  simplicio-video update --dry-run\n  simplicio-video update\n"
               "  simplicio-video update --force")
    p.add_argument("--check", action="store_true", help="não altera nada; sai com 0 (em dia), 10 (há atualização) ou 2 (erro)")
    p.add_argument("--dry-run", action="store_true",
                   help="só mostra o plano e sai com 0 (no pacote; num checkout mostra a recusa); não altera nada nem grava o estado")
    p.add_argument("--force", action="store_true", help="reinstala a release do pip mesmo em dia e permite downgrade")

    p = sub.add_parser("doctor", formatter_class=Fmt, help="diagnóstico: login, update, runtime, Python, Node 22, ffmpeg+libass, disco, portas, workspace",
        description="Checa o ambiente e diz a correção exata de cada falha, no contrato simplicio.doctor/v1 do simplicio-loop:\n"
                    "login, update, distribution, runtime, python, node, ffmpeg, ffmpeg-libass, disk, ports, GEMINI_API_KEY e setup.\n"
                    "Credenciais só mostram presença, nunca o valor, e nenhum token é impresso. warn não reprova: login ausente,\n"
                    "workspace ausente e GEMINI_API_KEY ausente são avisos. Exit code 1 só quando alguma checagem é fail.\n"
                    "Sem --online não usa rede: o update vem do cache do último `update --check`.",
        epilog="exemplos:\n  simplicio-video doctor\n  simplicio-video doctor --json\n  simplicio-video doctor login\n"
               "  simplicio-video doctor --online\n  docker compose run --rm simplicio doctor")
    p.add_argument("what", nargs="?", choices=["all", "login"], default="all", metavar="all|login",
                   help="all (padrão): todas as checagens; login: só a linha do login")
    p.add_argument("--json", action="store_true", help="imprime {schema, status, version, checks[{name, status, summary, fix, detail}]} em JSON")
    p.add_argument("--online", action="store_true", help="consulta a última versão (GitHub ou git) e regrava o cache do update")

    p = sub.add_parser("login", formatter_class=Fmt, help="entra com o login do Simplicio, o mesmo do Runtime (delega a `simplicio login google`)",
        description="Espelho do `login` do simplicio-loop: roda `simplicio login google` do Simplicio Runtime (com o terminal ligado) e\n"
                    "confere o arquivo compartilhado ~/.simplicio/login.json (ou SIMPLICIO_AUTH_FILE). Sem o Runtime o login próprio é\n"
                    "UNVERIFIED (sem endpoint documentado): mostra como instalar o Runtime e sai com 1.\n"
                    "O login não libera nem cobra nada no motor, não guarda credencial e não recebe token por argumento: o filho roda com\n"
                    "ambiente mínimo (sem GH_TOKEN, chaves de API nem SIMPLICIO_LOGIN_TOKEN). A conta sai mascarada e nenhum token é impresso.\n"
                    "Saída: 0 verificado, 1 não verificado, 2 recusado (--no-browser impossível no Windows: no_browser_unsupported).",
        epilog="exemplos:\n  simplicio-video login\n  simplicio-video login --json\n  simplicio-video login --no-browser")
    p.add_argument("--json", action="store_true", help="imprime um documento simplicio.login/v1 (a saída do Runtime vai para o stderr)")
    p.add_argument("--no-browser", action="store_true", help="pede ao Runtime que não abra o navegador e mostra o endereço e o código (Linux e macOS)")

    p = sub.add_parser("logout", formatter_class=Fmt, help="apaga o arquivo de login compartilhado (desloga o Runtime também)",
        description="Apaga ~/.simplicio/login.json (ou SIMPLICIO_AUTH_FILE) sob a trava login.lock. Esse arquivo é do Simplicio Runtime\n"
                    "também: sair aqui desloga o Runtime, por isso sem --yes nada é apagado (REFUSED, exit 2). Só apaga um arquivo\n"
                    "comum, pequeno e com a forma de login do Runtime: JSON com access_token (texto) e access_expires_at (número); só\n"
                    "refresh_token, como nas credenciais do gcloud, não basta. Qualquer outro (uma chave ssh que SIMPLICIO_AUTH_FILE\n"
                    "aponte, uma pasta) é recusado, exit 2, not_a_login_file, sem apagar nada. Um link simbólico (um ponto de reparse\n"
                    "de link no Windows) também é recusado, exit 2, login_symlink, antes de qualquer trava, sem tocar no link nem no alvo.\n"
                    "O token de renovação não é revogado no servidor. Sem arquivo de login: NO_LOGIN, exit 0, nada é criado.",
        epilog="exemplos:\n  simplicio-video logout\n  simplicio-video logout --yes\n  simplicio-video logout --yes --json")
    p.add_argument("--yes", action="store_true", help="confirma: sem isto nada é apagado")
    p.add_argument("--json", action="store_true", help="imprime um documento simplicio.logout/v1")

    p = sub.add_parser("auth", formatter_class=Fmt, help="inspeciona o login compartilhado com o Runtime (auth status)",
        description="Ações: status. Mostra quem está logado (conta mascarada), a validade do token, os direitos em cache e a versão do\n"
                    "Runtime, lendo ~/.simplicio/login.json (ou SIMPLICIO_AUTH_FILE). Nunca imprime um token.",
        epilog="exemplos:\n  simplicio-video auth status\n  simplicio-video auth status --json")
    auth_sub = p.add_subparsers(dest="auth_cmd", metavar="AÇÃO", title="ações", required=True)
    ps = auth_sub.add_parser("status", formatter_class=Fmt, help="quem está logado, validade e direitos em cache; nunca imprime token",
        description="Lê o arquivo de login compartilhado (~/.simplicio/login.json ou SIMPLICIO_AUTH_FILE) e mostra: conta (mascarada),\n"
                    "validade dos tokens (só se existem), direitos em cache, versão do Runtime e a correção quando o login não serve.\n"
                    "Este comando nunca imprime um token. Saída: 0 logado, 1 não logado. Documento --json: simplicio.auth-status/v1.",
        epilog="exemplos:\n  simplicio-video auth status\n  simplicio-video auth status --json")
    ps.add_argument("--json", action="store_true", help="imprime um documento simplicio.auth-status/v1")

    p = sub.add_parser("setup", formatter_class=Fmt, help="primeira execução: cria o workspace (tema, idioma, autonomia L1, orçamentos zero)",
        description="Cria o workspace em $SIMPLICIO_WORKSPACE (padrão ~/.simplicio-video/workspaces/default) com\n"
                    "workspace.yaml (tema, idioma) e policy.yaml (autonomia L1; tokens, USD e créditos em zero).\n"
                    "--yes aceita os padrões sem perguntar. Não faz login nem grava credencial.",
        epilog="exemplos:\n  simplicio-video setup\n  simplicio-video setup --yes --theme br --lang pt-BR\n"
               "  simplicio-video setup --yes --realoficial")
    p.add_argument("--yes", "-y", action="store_true", help="aceita os padrões sem perguntar")
    p.add_argument("--theme", metavar="ID", help="tema visual (padrão: br)")
    p.add_argument("--lang", metavar="IDIOMA", help="idioma do conteúdo (padrão: pt-BR)")
    p.add_argument("--force", action="store_true", help="regrava workspace.yaml e policy.yaml (zera orçamentos)")
    p.add_argument("--realoficial", action="store_true", help="mostra como conectar o MCP do Real Oficial (OAuth no cliente)")
    return ap


# --json de validate, run e render (issue #72): stdout só com o objeto JSON, que valida contra schemas/cli/*-result.
# Os logs de voz e de render vão para stderr. Erros do motor ganham error.code fixo; o texto de erro e o exit code
# (1, como no modo texto) não mudam.
CODIGO_PADRAO = {"validate": "CONTRATO_INVALIDO", "run": "RENDER_FALHOU", "render": "RENDER_FALHOU"}


def _stderr(*msg) -> None:
    print(*msg, file=sys.stderr)


def _emite(obj: dict) -> None:
    print(json.dumps(obj, indent=2, ensure_ascii=False, default=str))


def _erro(exc: BaseException, padrao: str) -> dict:
    """Exceção do motor -> error {code, message}. Contrato não encontrado e inválido são reconhecidos pelo texto do
    motor (contract.load / contract.validate); ferramenta ausente é FileNotFoundError do subprocesso."""
    if isinstance(exc, FileNotFoundError):
        return {"code": "FERRAMENTA_AUSENTE", "message": f"ferramenta ausente: {exc.filename or exc}"}
    texto = (exc.code if isinstance(exc.code, str) else "").strip() if isinstance(exc, SystemExit) else str(exc).strip()
    texto = texto or padrao
    if texto.startswith("contract not found"):
        code = "CONTRATO_NAO_ENCONTRADO"
    elif texto.startswith("contract invalid") or "not a YAML mapping" in texto:
        code = "CONTRATO_INVALIDO"
    else:
        code = padrao
    return {"code": code, "message": texto}


def _validate_json(a) -> int:
    from . import contract as ct
    try:
        c = ct.load(a.contrato)
    except (SystemExit, FileNotFoundError) as e:
        _emite({"ok": False, "contrato": a.contrato, "error": _erro(e, CODIGO_PADRAO["validate"])})
        return 1
    rep = ct.validate(c, need_lock=a.need_lock)
    if rep.ok:
        _emite({"ok": True, "contrato": str(c.path), "errors": [], "warnings": rep.warnings})
        return 0
    _emite({"ok": False, "contrato": str(c.path), "errors": rep.errors, "warnings": rep.warnings,
            "error": {"code": "CONTRATO_INVALIDO", "message": f"contrato inválido: {len(rep.errors)} erro(s)"}})
    return 1


def _run_json(a) -> int:
    from . import pipeline
    try:
        res = pipeline.run_all(a.contrato, provider=a.provider, backend=a.backend, accelerator=a.accelerator,
                               quality=a.quality, timeout=a.timeout, force_voice=a.force_voice, log=_stderr)
    except (SystemExit, FileNotFoundError) as e:
        _emite({"ok": False, "contrato": a.contrato, "error": _erro(e, CODIGO_PADRAO["run"])})
        return 1
    _emite({"ok": True, "contrato": str(Path(a.contrato).resolve()), **res})
    return 0


def _render_json(a) -> int:
    from . import contract as ct, render
    try:
        c = ct.load(a.contrato)
        if a.preview:
            if a.backend != "local":
                print("render --preview: só no backend local", file=sys.stderr)
                return 2
            man = render.render_preview(c, out=a.out, workdir=a.workdir, log=_stderr)
            saida, manifesto = c.dir / man["preview"]["path"], c.dir / "preview.manifest.json"
        else:
            r = do_render(c, a.backend, out=a.out, quality=a.quality, workdir=a.workdir, gpu=a.gpu, accelerator=a.accelerator,
                          timeout=a.timeout, gpu_encode=a.gpu_encode, log=_stderr)
            if isinstance(r.get("output"), dict):  # local e remotos: MP4 + render.manifest.json ao lado do contrato
                saida, manifesto = c.dir / r["output"]["path"], c.dir / "render.manifest.json"
            else:  # colab: só o bundle .zip, sem manifesto
                saida, manifesto = r.get("bundle"), None
    except (SystemExit, FileNotFoundError) as e:
        _emite({"ok": False, "contrato": a.contrato, "backend": a.backend, "preview": a.preview,
                "error": _erro(e, CODIGO_PADRAO["render"])})
        return 1
    _emite({"ok": True, "contrato": str(c.path), "backend": a.backend, "preview": a.preview,
            "output": str(Path(saida).resolve()) if saida else None, "manifest": str(manifesto) if manifesto else None})
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = build_parser()
    args_list = sys.argv[1:] if argv is None else argv
    if args_list and args_list[0] in ("clone", "montage", "opencut", "edit", "toonflow", "moneyprinter", "formats", "swap", "jobs", "social", "openverse", "busca"):
        antes_do_traco = args_list[:args_list.index("--")] if "--" in args_list else args_list  # after `--` a -h or --help is a value
        if any(h in antes_do_traco for h in ("-h", "--help")):
            ap.parse_args(args_list[:1] + ["--help"])
            return 0
        cmd = args_list[0]
        sub_args = args_list[1:]
        if cmd == "clone":
            try:
                return clone.run_hypit(sub_args)
            except clone.CloneError as e:
                print(f"clone: {e}", file=sys.stderr)
                return 1
        if cmd == "montage":
            try:
                return montage.run_montage(sub_args)
            except montage.MontageError as e:
                print(f"montage: {e}", file=sys.stderr)
                return 1
        if cmd == "edit":
            try:
                return edit.run_edit(sub_args)
            except edit.EditError as e:
                print(f"edit: {e}", file=sys.stderr)
                return 1
        if cmd == "opencut":
            try:
                return opencut.run_opencut(sub_args)
            except opencut.OpenCutError as e:
                print(f"opencut: {e}", file=sys.stderr)
                return 1
        if cmd == "swap":
            from . import swap
            return swap.run_swap(sub_args)
        if cmd == "jobs":
            from . import jobs
            return jobs.run_jobs(sub_args)
        if cmd == "social":
            from . import social
            return social.run_social(sub_args)
        if cmd == "openverse":
            from . import openverse
            return openverse.run_openverse(sub_args)
        if cmd == "busca":
            from . import busca
            return busca.run_busca(sub_args)
        if cmd == "formats":
            from . import formats
            try:
                return formats.run_formats(sub_args)
            except formats.FormatError as e:
                print(f"formats: {e}", file=sys.stderr)
                return 1
        if cmd == "toonflow":
            try:
                return toonflow.run_toonflow(sub_args)
            except toonflow.ToonflowError as e:
                print(f"toonflow: {e}", file=sys.stderr)
                return 1
        if cmd == "moneyprinter":
            try:
                return moneyprinter.run_moneyprinter(sub_args)
            except moneyprinter.MoneyPrinterError as e:
                print(f"moneyprinter: {e}", file=sys.stderr)
                return 1

    a = ap.parse_args(argv)
    if a.version:
        from . import status
        if a.ver_json:
            print(json.dumps(status.version_info(), indent=2, ensure_ascii=False))
        else:
            print(f"simplicio-video {__version__} ({HYPERFRAMES})")
        return 0
    if not a.cmd:
        ap.print_help()
        return 0

    if a.cmd == "install":
        from .commands import install
        return install.run(a)
    if a.cmd == "update":
        from .commands import update
        return update.run(a)
    if a.cmd == "doctor":
        from .commands import doctor
        return doctor.run(a)
    if a.cmd in ("login", "logout", "auth"):
        from .commands import login
        return login.run(a)
    if a.cmd == "setup":
        from .commands import setup
        return setup.run(a)

    if a.cmd == "status":
        from . import status
        try:
            rep = status.report(a.contrato)
        except status.StatusError as e:
            print(f"status: {e}", file=sys.stderr)
            return 2
        print(json.dumps(rep, indent=2, ensure_ascii=False) if a.json else status.text(rep))
        return 0

    if a.cmd == "list":
        from . import catalog
        d = paths.data_dir()
        if a.grupo and a.what != "angles":
            ap.error("--grupo só vale com `list angles`")
        rows = {"templates": lambda: catalog.templates(d), "motion": lambda: catalog.motion(d), "voices": catalog.voices,
                "angles": lambda: catalog.angles(d, grupo=a.grupo)}[a.what]()
        if a.json:
            print(json.dumps(rows, indent=2, ensure_ascii=False))
        elif a.what == "angles":
            for r in rows:
                print(f"{r['id']:30s} {r['grupo']:11s} {r['nome']}")
        elif a.what == "templates":
            for r in rows:
                print(f"{r['id']:28s} {r['status']:9s} {r['duracao_s']:>5}s  {'renderizável' if r['renderizavel'] else 'sem composição':15s} {r['setor']}")
        elif a.what == "motion":
            for r in rows:
                print(f"{r['id']:30s} {r['status'] or '':9s} {str(r['duration_s'] or ''):>5}  {r['title'][:70]}")
        else:
            for r in rows:
                print(f"{r['id']:11s} {r['desc']}")
        return 0
    if a.cmd == "init":
        from . import scaffold
        h = paths.home()
        data = scaffold.skeleton(h, a.cliente, a.campanha, a.template, a.ano, a.nome, a.drive_nome)
        out = a.out or scaffold.default_out(data["campanha"]["id"], a.cliente)
        scaffold.write(out, data, a.force)
        print(f"contrato: {out}\npróximo: preencha os TODO (só fatos de coleta/) e rode `simplicio-video validate {out}`")
        return 0
    if a.cmd == "clone":
        try:
            return clone.run_hypit(a.args)
        except clone.CloneError as e:
            print(f"clone: {e}", file=sys.stderr)
            return 1
    if a.cmd == "montage":
        try:
            return montage.run_montage(a.args)
        except montage.MontageError as e:
            print(f"montage: {e}", file=sys.stderr)
            return 1

    if a.cmd == "mcp":
        from . import mcp_server
        mcp_server.main()
        return 0
    if a.cmd == "run":
        if a.json:
            return _run_json(a)
        from . import pipeline
        pipeline.run_all(a.contrato, provider=a.provider, backend=a.backend, accelerator=a.accelerator, quality=a.quality,
                         timeout=a.timeout, force_voice=a.force_voice, log=print)
        return 0
    if a.cmd == "validate" and a.json:
        return _validate_json(a)
    if a.cmd == "render" and a.json:
        return _render_json(a)
    from . import contract as ct
    c = ct.load(a.contrato)
    if a.cmd == "validate":
        rep = ct.validate(c, need_lock=a.need_lock)
        for e in rep.errors:
            print(f"ERRO   {e}")
        for w in rep.warnings:
            print(f"aviso  {w}")
        sc = c.scenes() if not ct.schema_errors(c.data) else []
        if sc:
            print("cenas: " + " | ".join(f"{s['id']} {s['_start']}-{s['_end']}s" for s in sc))
        print("OK: contrato válido" if rep.ok else f"FALHOU: {len(rep.errors)} erro(s)")
        return 0 if rep.ok else 1
    if a.cmd == "voice":
        from . import voice
        rep = ct.validate(c)
        if not rep.ok and any(not e.startswith("voice:") for e in rep.errors):
            print("contrato inválido:\n  " + "\n  ".join(rep.errors), file=sys.stderr)
            return 1
        voice.run(c, provider=a.provider, force=a.force, only=a.only, concurrency=a.concurrency)
        return 0
    if a.cmd == "render":
        from . import render
        if a.preview:
            if a.backend != "local":
                print("render --preview: só no backend local", file=sys.stderr)
                return 2
            render.render_preview(c, out=a.out, workdir=a.workdir)
            return 0
        do_render(c, a.backend, out=a.out, quality=a.quality, workdir=a.workdir, gpu=a.gpu, accelerator=a.accelerator,
                  timeout=a.timeout, gpu_encode=a.gpu_encode)
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
