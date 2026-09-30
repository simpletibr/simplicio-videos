"""simplicio-video command line (argparse). Every subcommand has an explicit, complete --help."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import CONTRACT_SCHEMA_ID, HYPERFRAMES, __version__, paths

SCHEMA_REL = "schema/contract.schema.json"

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
  6. publish   sobe o MP4 no Drive em drive.caminho/drive.arquivo (rclone, nunca sobrescreve uma versão)
               e grava o link em clients/<slug>/README.md (tabela "Entregas no Drive")
  run          tudo de uma vez: voice -> validate --need-lock -> render -> publish (dry-run sem --publish)
  prospect     venda ativa em massa (alias batch): lista.csv -> coleta pública -> contrato por setor -> voz local ->
               prévia 540x960 com marca d'água SimpleTI + lote.csv (docs/venda-ativa.md)
  mcp          servidor MCP (stdio) com as tools video.init/validate/voice/render/publish/run/list

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
  simplicio-video publish clients/lothus-odontologia/video-01-dia-das-criancas/contract.yaml --dry-run
  simplicio-video run clients/lothus-odontologia/video-01-dia-das-criancas/contract.yaml --provider gemini --publish
  simplicio-video prospect prospects/exemplo-dia-criancas.csv --lote dia-criancas --jobs 1
  simplicio-video render contract.yaml --preview          # 540x960, marca d'água SimpleTI (prévia de venda)

ambiente:
  SIMPLICIO_VIDEO_HOME  checkout do plugin (templates/, motion/, schema/); padrão: procura a partir do contrato/cwd
  SIMPLICIO_TTS_PY      python com kokoro-onnx para --provider local
  GEMINI_API_KEY        --provider gemini (aistudio.google.com/apikey; nunca commitar)
  KAGGLE_USERNAME, KAGGLE_API_TOKEN (ou ~/.kaggle/access_token)   --backend kaggle
  SIMPLICIO_COLAB_AUTH  oauth2|adc para --backend colab-cli (padrão do CLI colab)
  SIMPLICIO_DRIVE_REMOTE  remote rclone do Google Drive para publish (padrão: gdrive)
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
    ap.add_argument("--version", action="version", version=f"simplicio-video {__version__} ({HYPERFRAMES})")
    sub = ap.add_subparsers(dest="cmd", metavar="COMANDO", title="comandos (na ordem do fluxo)")

    p = sub.add_parser("init", formatter_class=Fmt, help="gera o esqueleto de contrato para <cliente> <campanha>",
        description="Gera um contrato-esqueleto a partir de templates/<template>/template.json: cenas, padrões de motion,\n"
                    "voz sugerida, trilha padrão e o destino no Drive. Campos com TODO precisam ser preenchidos\n"
                    f"(validate falha enquanto houver TODO). Schema: {SCHEMA_REL}.",
        epilog="exemplos:\n"
               "  simplicio-video init lothus-odontologia Dia_Criancas --template saude-odontologia --nome \"Lothus Odontologia\"\n"
               "  simplicio-video init wjr-informatica-games Black_Friday --template assistencia-tecnica-games --ano 2026 \\\n"
               "      --out clients/wjr-informatica-games/video-03/contract.yaml")
    p.add_argument("cliente", help="slug do cliente (pasta em clients/, ex.: lothus-odontologia)")
    p.add_argument("campanha", help="campanha em Title_Case com underscore, sem acento (ex.: Dia_Criancas); vira a pasta do Drive")
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
                    "  - drive.caminho == simplicio-video/clientes/<drive_nome>/<ano>/<campanha>; nenhum TODO\n"
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
    p.add_argument("--provider", "-p", choices=["file", "local", "gemini", "elevenlabs", "xai"], help="sobrepõe voz.provider")
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
                    "Remotos baixam final.mp4 e gravam o mesmo render.manifest.json (+ usage: backend, GPU, tempos) para créditos.",
        epilog="exemplos:\n  simplicio-video render contract.yaml\n"
               "  simplicio-video render contract.yaml --out /tmp/teste.mp4 --quality draft\n"
               "  simplicio-video render contract.yaml --backend kaggle                   # opcional: T4 grátis (cota semanal)\n"
               "  simplicio-video render contract.yaml --backend kaggle --accelerator none\n"
               "  simplicio-video render contract.yaml --backend colab-cli --accelerator T4\n"
               "  simplicio-video render contract.yaml --backend colab   # -> out/<nome>.colab-bundle.zip\n"
               "  simplicio-video render contract.yaml --preview         # prévia de venda 540x960 + marca d'água SimpleTI")
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
    p.add_argument("--preview", action="store_true",
                   help="prévia de venda (só local): render draft -> 540x960, 30 fps, x264 crf 30, marca d'água diagonal "
                        "'Prévia • SimpleTI • simpleti.com.br' + selo nos cantos + cartão final 'Vídeo feito pela SimpleTI — "
                        "simpleti.com.br' (2,5 s). Padrão --out: <saida.arquivo>-previa.mp4. Grava preview.manifest.json "
                        "(não toca no render.manifest.json da entrega)")

    p = sub.add_parser("prospect", aliases=["batch"], formatter_class=Fmt,
        help="venda ativa em massa: lista.csv -> coleta pública -> contrato por setor -> prévia com marca d'água",
        description="Gera prévias de venda em massa, 100% determinístico (sem LLM por vídeo). Para cada linha do CSV:\n"
                    "  1. coleta   pública e leve: página inicial do site (title/meta/og, theme-color + cores do CSS, logo/og:image,\n"
                    "              links de Instagram e WhatsApp publicados pela empresa), respeitando robots.txt, 1 requisição por\n"
                    "              recurso, timeout 15 s. Instagram: só og:* público sem login, se o robots.txt permitir (hoje o\n"
                    "              instagram.com proíbe robôs genéricos: o @ vem do CSV ou do site); intervalo mínimo 6 s; bloqueio\n"
                    "              vira status e o lote segue. LGPD: só dados da empresa (sem pessoas, e-mails ou telefones pessoais).\n"
                    "  2. setor    regras de templates/sazonal-dia-das-criancas/setores.json (coluna setor; senão título do site)\n"
                    "  3. contrato contract.base.yaml (coreografia Lothus v02, 128 BPM) + textos do setor + nome/@/cidade reais.\n"
                    "              Nunca preço, promoção, prazo ou fato inventado.\n"
                    "  4. voz      local (Kokoro pf_dora, custo 0) por padrão; gemini opcional (GEMINI_API_KEY). Fala que estoura o\n"
                    "              slot cai para a variante mais curta (ordem fixa).\n"
                    "  5. prévia   render --preview (540x960, crf 30, 30 fps, marca d'água SimpleTI + cartão final)\n"
                    "CSV (UTF-8 com cabeçalho; só nome é obrigatório): nome, cidade, setor, site, instagram, whatsapp, maps,\n"
                    "  nome_curto (lockup/fala), fontes (onde cada dado foi achado). Exemplo: prospects/exemplo-dia-criancas.csv\n"
                    "Saída: <out>/<slug>/{coleta.json, contract.yaml, preview.mp4, result.json} + <out>/lote.csv (nome, setor,\n"
                    "  instagram, whatsapp, fontes, status, motivo, dados achados, caminho, tempo) + lote.json.\n"
                    "Retomada idempotente: linha com preview.mp4 + result.json ok é pulada; coleta.json é reaproveitada.\n"
                    "Nada é enviado a ninguém: o Wesley revisa e envia (script de abordagem em docs/venda-ativa.md).\n"
                    "Prévias ficam fora do git (prospects/*/ no .gitignore).",
        epilog="exemplos:\n  simplicio-video prospect prospects/exemplo-dia-criancas.csv\n"
               "  simplicio-video prospect lista.csv --lote dia-criancas --out /workspace/prospects-piloto/dia-criancas --jobs 2\n"
               "  simplicio-video batch lista.csv --so-contrato          # só coleta + contrato (sem voz/render)\n"
               "  simplicio-video prospect lista.csv --provider gemini   # voz Gemini (API, custo em docs/custos.md)")
    p.add_argument("csv", type=Path, metavar="LISTA.csv", help="lista de empresas (ver descrição acima)")
    p.add_argument("--lote", help="nome do lote (padrão: nome do CSV); pasta prospects/<lote>/")
    p.add_argument("--out", "-o", type=Path, help="pasta de saída do lote (padrão: <plugin>/prospects/<lote>)")
    p.add_argument("--campanha", default="dia-das-criancas", choices=["dia-das-criancas"], help="campanha sazonal (padrão: dia-das-criancas)")
    p.add_argument("--provider", "-p", choices=["local", "gemini"], default="local", help="voz da prévia (padrão: local = Kokoro, custo 0)")
    p.add_argument("--jobs", "-j", type=int, default=1, help="empresas em paralelo (padrão 1; cada render já usa SV_WORKERS núcleos)")
    p.add_argument("--force", action="store_true", help="refaz prévias existentes (a coleta continua reaproveitada)")
    p.add_argument("--recoletar", action="store_true", help="refaz a coleta mesmo com coleta.json existente")
    p.add_argument("--so-contrato", action="store_true", help="só coleta + contract.yaml (sem voz nem render)")
    p.add_argument("--limite", type=int, help="processa só as N primeiras linhas")
    p.add_argument("--json", action="store_true", help="resumo em JSON")

    p = sub.add_parser("publish", formatter_class=Fmt, help="sobe o MP4 no Google Drive (rclone) e grava o link no README do cliente",
        description="Sobe saida.arquivo (ou --file) para <remote>:drive.caminho/drive.arquivo com rclone (sem navegador) e grava o\n"
                    "link na tabela \"Entregas no Drive\" de clients/<slug>/README.md. Nunca sobrescreve: mesmo nome com bytes\n"
                    "diferentes = erro (suba vNN+1); mesmos bytes = idempotente. O link vem do ID do arquivo (rclone lsjson),\n"
                    "nunca de `rclone link` (não muda compartilhamento).\n"
                    "Autenticação única: remote rclone tipo drive (padrão gdrive; SIMPLICIO_DRIVE_REMOTE), escopo drive,\n"
                    f"client_id próprio (docs/decisoes/ADR-0003-fluxo-100-script.md). Schema: {SCHEMA_REL}.",
        epilog="exemplos:\n  simplicio-video publish contract.yaml --dry-run          # só mostra o destino\n"
               "  simplicio-video publish contract.yaml                    # sobe e grava o link\n"
               "  simplicio-video publish contract.yaml --remote gdrive-wesley --file out/outro.mp4")
    _contract_arg(p)
    p.add_argument("--file", type=Path, help="MP4 a subir (padrão: saida.arquivo)")
    p.add_argument("--remote", help="remote rclone do Google Drive (padrão: $SIMPLICIO_DRIVE_REMOTE ou gdrive)")
    p.add_argument("--dry-run", action="store_true", help="não sobe nada; imprime origem e destino")
    p.add_argument("--no-readme", action="store_true", help="não altera clients/<slug>/README.md")
    p.add_argument("--json", action="store_true", help="resultado em JSON")

    p = sub.add_parser("run", formatter_class=Fmt, help="voice -> validate -> render -> publish num comando só",
        description="Fluxo 100% script: validate -> voice (provider do contrato ou --provider, ex.: gemini) ->\n"
                    "validate --need-lock -> render (--backend local|kaggle|colab-cli|colab) -> publish.\n"
                    "Sem --publish o passo final é dry-run (mostra o destino no Drive): subir entrega exige pedido explícito.\n"
                    f"Schema: {SCHEMA_REL}.",
        epilog="exemplos:\n  simplicio-video run contract.yaml                                   # voz do contrato, render local, publish dry-run\n"
               "  simplicio-video run contract.yaml --provider gemini --publish         # local (padrão)\n"
               "  simplicio-video run contract.yaml --provider gemini --backend kaggle   # opcional (créditos)\n"
               "  simplicio-video run contract.yaml --backend colab-cli --json")
    _contract_arg(p)
    p.add_argument("--provider", "-p", choices=["file", "local", "gemini"], help="sobrepõe voz.provider")
    p.add_argument("--force-voice", action="store_true", help="regera todas as falas (ignora o cache)")
    p.add_argument("--backend", "-b", choices=BACKENDS, default="local", help="onde renderizar (padrão: local; kaggle/colab-cli/colab são opcionais, via créditos)")
    p.add_argument("--accelerator", help="ver `render --help` (none = CPU)")
    p.add_argument("--quality", "-q", choices=["draft", "looks", "delivery"], help="qualidade HyperFrames")
    p.add_argument("--timeout", type=int, default=3600, help="limite do render remoto em s")
    p.add_argument("--publish", action="store_true", help="sobe de verdade no Drive (sem isto: dry-run)")
    p.add_argument("--remote", help="remote rclone do Drive (padrão: gdrive)")
    p.add_argument("--json", action="store_true", help="resumo em JSON")

    p = sub.add_parser("mcp", formatter_class=Fmt, help="servidor MCP (stdio) para o simplicio-runtime",
        description="Expõe o CLI como servidor MCP (stdio): tools video.init, video.validate, video.voice, video.render,\n"
                    "video.publish, video.run, video.list. Requer `pip install -e .[mcp]` (SDK Python `mcp`).\n"
                    f"Contratos seguem {SCHEMA_REL}.",
        epilog="exemplos:\n  simplicio-video mcp                  # stdio (o runtime lança este processo)\n"
               "  simplicio-video-mcp                  # mesmo servidor, entrypoint dedicado")

    p = sub.add_parser("list", formatter_class=Fmt, help="lista templates, padrões de motion ou providers de voz",
        description="Catálogos do plugin: templates/ (renderizável = tem composição), motion/catalog.json, providers de voz.",
        epilog="exemplos:\n  simplicio-video list templates\n  simplicio-video list motion --json\n  simplicio-video list voices")
    p.add_argument("what", choices=["templates", "motion", "voices"], help="catálogo a listar")
    p.add_argument("--json", action="store_true", help="saída em JSON")
    return ap


def main(argv: list[str] | None = None) -> int:
    ap = build_parser()
    a = ap.parse_args(argv)
    if not a.cmd:
        ap.print_help()
        return 0
    if a.cmd == "list":
        from . import catalog
        h = paths.home()
        rows = {"templates": lambda: catalog.templates(h), "motion": lambda: catalog.motion(h), "voices": catalog.voices}[a.what]()
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
    if a.cmd in ("prospect", "batch"):
        from . import prospect
        res = prospect.run_batch(a.csv, out=a.out, lote=a.lote, campanha=a.campanha, provider=a.provider, jobs=a.jobs,
                                 force=a.force, recollect=a.recoletar, render=not a.so_contrato, limit=a.limite,
                                 log=(lambda *_: None) if a.json else print)
        if a.json:
            print(json.dumps(res, indent=2, ensure_ascii=False))
        return 0 if res["erros"] == 0 else 1
    if a.cmd == "mcp":
        from . import mcp_server
        mcp_server.main()
        return 0
    if a.cmd == "run":
        from . import pipeline
        res = pipeline.run_all(a.contrato, provider=a.provider, backend=a.backend, accelerator=a.accelerator, quality=a.quality,
                               timeout=a.timeout, publish=a.publish, remote=a.remote, force_voice=a.force_voice,
                               log=(lambda *_: None) if a.json else print)
        if a.json:
            print(json.dumps(res, indent=2, ensure_ascii=False, default=str))
        return 0
    from . import contract as ct
    c = ct.load(a.contrato)
    if a.cmd == "publish":
        from . import publish as pub
        res = pub.publish(c, file=a.file, remote=a.remote, dry_run=a.dry_run, update_readme=not a.no_readme,
                          log=(lambda *_: None) if a.json else print)
        if a.json:
            print(json.dumps(res, indent=2, ensure_ascii=False))
        return 0
    if a.cmd == "validate":
        rep = ct.validate(c, need_lock=a.need_lock)
        if a.json:
            print(json.dumps({"ok": rep.ok, "errors": rep.errors, "warnings": rep.warnings}, indent=2, ensure_ascii=False))
        else:
            for e in rep.errors:
                print(f"ERRO   {e}")
            for w in rep.warnings:
                print(f"aviso  {w}")
            sc = c.scenes() if not ct.schema_errors(c.data, c.home) else []
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
