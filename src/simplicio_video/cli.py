"""simplicio-video command line (argparse). Every subcommand has an explicit, complete --help."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import CONTRACT_SCHEMA_ID, HYPERFRAMES, __version__, clone, edit, montage, opencut, paths

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
  mcp         servidor MCP (stdio) com as tools video.init/validate/voice/render/run/list/clone/montage/edit/opencut
  status       ferramentas (instaladas, versão, versão fixada) e, com CONTRATO, o estado do render (--json para o looping)
  install      ambiente do checkout: .venv com uv, Python 3.12 e extras (--check mostra o plano)
  update       git pull --ff-only (recusa árvore suja), reinstala, reconstrói web/ e roda doctor
  doctor       diagnóstico: Python, Node 22, ffmpeg com libass, disco, portas, credenciais, workspace
  setup        primeira execução: cria o workspace (tema, idioma, autonomia L1, orçamentos zero)

Schema do contrato: {SCHEMA_REL} (no checkout do plugin; ver `simplicio-video validate --help`).
Skill para LLMs: skills/simplicio-video/SKILL.md"""

MAIN_EPILOG = """\
exemplos:
  simplicio-video list templates
  simplicio-video init lothus-odontologia Dia_Criancas --template saude-odontologia --nome "Lothus Odontologia" --ano 2026
  simplicio-video validate clients/lothus-odontologia/video-01-dia-das-criancas/contract.yaml
  simplicio-video voice clients/lothus-odontologia/video-01-dia-das-criancas/contract.yaml --provider local
  simplicio-video render clients/lothus-odontologia/video-01-dia-das-criancas/contract.yaml
  simplicio-video render clients/wjr-informatica-games/video-01/contract.yaml --backend kaggle
  simplicio-video run clients/lothus-odontologia/video-01-dia-das-criancas/contract.yaml --provider gemini
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
               "  simplicio-video init lothus-odontologia Dia_Criancas --template saude-odontologia --nome \"Lothus Odontologia\"\n"
               "  simplicio-video init wjr-informatica-games Black_Friday --template assistencia-tecnica-games --ano 2026 \\\n"
               "      --out clients/wjr-informatica-games/video-03/contract.yaml")
    p.add_argument("cliente", help="slug do cliente (pasta em clients/, ex.: lothus-odontologia)")
    p.add_argument("campanha", help="campanha em Title_Case com underscore, sem acento (ex.: Dia_Criancas)")
    p.add_argument("--template", "-t", required=True, help="id do template de setor (ver `simplicio-video list templates`)")
    p.add_argument("--nome", help="nome de exibição do cliente (padrão: TODO)")
    p.add_argument("--drive-nome", help="NOME_CLIENTE no Drive (padrão: derivado de --nome/slug, ex.: Lothus_Odontologia)")
    p.add_argument("--ano", type=int, help="ano da campanha (padrão: ano atual)")
    p.add_argument("--out", "-o", type=Path, help="onde gravar (padrão: clients/<cliente>/<campanha-slug>/contract.yaml)")
    p.add_argument("--force", action="store_true", help="sobrescreve um contrato existente")

    p = sub.add_parser("validate", formatter_class=Fmt, help="valida o contrato (schema, assets, durações, falas)",
        description=f"Valida o contrato contra o JSON Schema ({SCHEMA_REL}) e checa:\n"
                    "  - template existe e tem composição renderizável; ids de cena batem com a composição\n"
                    "  - padrões de motion existem em motion/patterns/ (bloco exige block.html)\n"
                    "  - todos os assets/logo existem (caminhos relativos ao contrato)\n"
                    "  - soma de cenas[].duracao_s == formato.duracao_s\n"
                    "  - cada fala: inicio_s + max_s cabe na cena (+ J-cut voz.jcut_max_s, padrão 0,15 s);\n"
                    "    com timing.lock.json, a duração real <= max_s (a voz NUNCA é acelerada)\n"
                    "  - nenhum bloco drive (a entrega no Drive fica fora do motor); nenhum TODO\n"
                    "--json: stdout só o objeto {ok, contrato, errors, warnings}; erro vira {ok: false, error: {code, message}}.\n"
                    "  Códigos de erro (error.code): CONTRATO_NAO_ENCONTRADO, CONTRATO_INVALIDO, RENDER_FALHOU, FERRAMENTA_AUSENTE.\n"
                    "Saída 0 = válido, 1 = erros.",
        epilog="exemplos:\n  simplicio-video validate clients/wjr-informatica-games/video-01/contract.yaml\n"
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
    p.add_argument("only", nargs="*", metavar="FALA_ID", help="ids de fala para refazer com --force (ex.: vo2 vo4)")

    p = sub.add_parser("render", formatter_class=Fmt, help="compila e renderiza (padrão local; kaggle/colab-cli/colab opcionais via créditos)",
        description="Compila contrato + timing.lock.json + template (templates/<id>/composition) + blocos de motion +\n"
                    "assets numa composição HyperFrames (build/simplicio-video/), sintetiza trilha/SFX e mixa a voz\n"
                    f"(engine build.mjs, semente fixa), renderiza os frames ({HYPERFRAMES}) e masteriza com ffmpeg\n"
                    "(loudnorm 2 passes, alvo trilha.master: -14 LUFS / TP -1,5). Grava render.manifest.json ao lado do\n"
                    "contrato: hash do contrato, de cada input compilado, das ferramentas e do vídeo/áudio decodificados.\n"
                    "backends (todos sem navegador, exceto colab):\n"
                    "  local      PADRÃO. Renderiza aqui (CPU; --gpu usa encoder de GPU do HyperFrames se houver).\n"
                    "             Referência de hash, sem custo (WJR 600 frames: 76,5 s em 8 núcleos).\n"
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


    p = sub.add_parser("formats", formatter_class=Fmt, help="biblioteca de 50 formatos de anúncio (Drive) e pedido para adaptar uma copy",
        description="Os 50 formatos da pasta 'Swipe File - 50 Formatos' (Drive): descrição, estrutura e o exemplo de cada um. "
                    "`prompt` monta o pedido para adaptar uma copy ao formato; quem adapta é o LLM, não o CLI.",
        epilog="exemplos:\n  simplicio-video formats list --objetivo venda\n  simplicio-video formats show caixinha\n  simplicio-video formats prompt caixinha --copia roteiro.txt")
    p.add_argument("args", nargs=argparse.REMAINDER, help="list [--objetivo ...] | show <id> | prompt <id> --copia <arquivo|->")

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
               "  simplicio-video status --json clients/lothus-odontologia/video-01/contract.yaml")
    p.add_argument("contrato", nargs="?", metavar="CONTRATO.yaml", help="contrato cujo render (render.manifest.json) será lido")
    p.add_argument("--json", action="store_true", help="imprime tools (e render, com CONTRATO) em JSON")

    p = sub.add_parser("list", formatter_class=Fmt, help="lista templates, padrões de motion ou providers de voz",
        description="Catálogos do plugin: templates/ (renderizável = tem composição), motion/catalog.json, providers de voz.",
        epilog="exemplos:\n  simplicio-video list templates\n  simplicio-video list motion --json\n  simplicio-video list voices")
    p.add_argument("what", choices=["templates", "motion", "voices"], help="catálogo a listar")
    p.add_argument("--json", action="store_true", help="saída em JSON")

    p = sub.add_parser("install", formatter_class=Fmt, help="ambiente idempotente: .venv com uv, Python e extras (--check mostra o plano)",
        description="Cria <checkout>/.venv com uv (Python --python; padrão: o último usado, ou 3.12) e instala o pacote\n"
                    "em modo editável com os extras. Idempotente: sem mudança em Python, extras ou pyproject.toml, não faz nada.\n"
                    "--check mostra o plano sem criar nada e sai com 1 se houver mudança pendente. Não usa sudo.",
        epilog="exemplos:\n  simplicio-video install --check\n  simplicio-video install\n"
               "  simplicio-video install --python 3.12 --with local-tts")
    p.add_argument("--check", action="store_true", help="mostra o que mudaria e não cria nada")
    p.add_argument("--python", metavar="VERSÃO", help="versão do Python do .venv, ex.: 3.12 (padrão: a última usada, ou 3.12)")
    p.add_argument("--with", dest="extras", metavar="EXTRAS",
                   help="extras separados por vírgula, ex.: local-tts,mcp (padrão: os da última instalação)")

    p = sub.add_parser("update", formatter_class=Fmt, help="git pull --ff-only (recusa árvore suja), reinstala, reconstrói web/ e roda doctor",
        description="Mostra os commits novos e o diff do CHANGELOG, aplica com git pull --ff-only, reexecuta install,\n"
                    "reconstrói web/ e roda doctor. Recusa árvore suja (--force deixa seguir; o git ainda protege arquivos\n"
                    "alterados). Imprime o commit anterior e o comando para voltar a ele (rollback).",
        epilog="exemplos:\n  simplicio-video update --check\n  simplicio-video update\n  simplicio-video update --force")
    p.add_argument("--check", action="store_true", help="mostra os commits novos e o diff do CHANGELOG; não altera nada")
    p.add_argument("--force", action="store_true", help="segue com árvore suja (não descarta alterações)")

    p = sub.add_parser("doctor", formatter_class=Fmt, help="diagnóstico: Python, Node 22, ffmpeg+libass, disco, portas, credenciais, workspace",
        description="Checa o ambiente e diz a correção exata de cada falha. Credenciais só mostram presença, nunca o valor.\n"
                    "Aviso (warn) não reprova. Exit code 0 sem falhas; 1 se alguma checagem falhou. --json para máquinas.",
        epilog="exemplos:\n  simplicio-video doctor\n  simplicio-video doctor --json\n"
               "  docker compose run --rm simplicio doctor")
    p.add_argument("--json", action="store_true", help="imprime {ok, checks[{name, status, detail, fix}]} em JSON")

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
    if args_list and args_list[0] in ("clone", "montage", "opencut", "edit", "formats"):
        if any(h in args_list for h in ("-h", "--help")):
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
        if cmd == "formats":
            from . import formats
            try:
                return formats.run_formats(sub_args)
            except formats.FormatError as e:
                print(f"formats: {e}", file=sys.stderr)
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
        rows = {"templates": lambda: catalog.templates(d), "motion": lambda: catalog.motion(d), "voices": catalog.voices}[a.what]()
        if a.json:
            print(json.dumps(rows, indent=2, ensure_ascii=False))
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
        out = a.out or h / "clients" / a.cliente / data["campanha"]["id"].lower().replace("_", "-") / "contract.yaml"
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
        voice.run(c, provider=a.provider, force=a.force, only=a.only)
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
