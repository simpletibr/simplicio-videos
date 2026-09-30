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
  4. voice     gera/cacheia as falas (file | local | gemini) e grava timing.lock.json com as durações reais
  5. render    contrato -> composição HyperFrames -> frames -> ffmpeg (trilha/SFX/voz, -14 LUFS)
               backend local (esta máquina) ou colab (bundle + colab/render.ipynb, GPU)
  6. entrega   suba o MP4 no Drive em drive.caminho (simplicio-video/clientes/NOME/ANO/CAMPANHA)
               e registre o link em clients/<slug>/README.md (tabela "Entregas no Drive")

Schema do contrato: {SCHEMA_REL} (no checkout do plugin; ver `simplicio-video validate --help`).
Skill para LLMs: skills/simplicio-video/SKILL.md"""

MAIN_EPILOG = """\
exemplos:
  simplicio-video list templates
  simplicio-video init lothus-odontologia Dia_Criancas --template saude-odontologia --nome "Lothus Odontologia" --ano 2026
  simplicio-video validate clients/lothus-odontologia/video-01-dia-das-criancas/contract.yaml
  simplicio-video voice clients/lothus-odontologia/video-01-dia-das-criancas/contract.yaml --provider local
  simplicio-video render clients/lothus-odontologia/video-01-dia-das-criancas/contract.yaml
  simplicio-video render clients/wjr-informatica-games/video-01/contract.yaml --backend colab

ambiente:
  SIMPLICIO_VIDEO_HOME  checkout do plugin (templates/, motion/, schema/); padrão: procura a partir do contrato/cwd
  SIMPLICIO_TTS_PY      python com kokoro-onnx para --provider local
  GEMINI_API_KEY        só para --provider gemini (nunca commitar)"""


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
                    "  gemini      API Gemini TTS (GEMINI_API_KEY obrigatório; sem chave = erro claro); guarda o take em file.dir\n"
                    "  elevenlabs  stub (gere fora e use file)\n"
                    "  xai         stub (gere fora e use file)",
        epilog="exemplos:\n  simplicio-video voice contract.yaml                    # provider do contrato (voz.provider)\n"
               "  simplicio-video voice contract.yaml --provider file    # depois de baixar line-01..NN.wav do AI Studio\n"
               "  simplicio-video voice contract.yaml --force vo2        # refaz só a vo2")
    _contract_arg(p)
    p.add_argument("--provider", "-p", choices=["file", "local", "gemini", "elevenlabs", "xai"], help="sobrepõe voz.provider")
    p.add_argument("--force", action="store_true", help="ignora o cache (com ids: só esses)")
    p.add_argument("only", nargs="*", metavar="FALA_ID", help="ids de fala para refazer com --force (ex.: vo2 vo4)")

    p = sub.add_parser("render", formatter_class=Fmt, help="compila e renderiza (local) ou gera bundle Colab",
        description="Compila contrato + timing.lock.json + template (templates/<id>/composition) + blocos de motion +\n"
                    "assets numa composição HyperFrames (build/simplicio-video/), sintetiza trilha/SFX e mixa a voz\n"
                    f"(engine build.mjs, semente fixa), renderiza os frames ({HYPERFRAMES}) e masteriza com ffmpeg\n"
                    "(loudnorm 2 passes, alvo trilha.master: -14 LUFS / TP -1,5). Grava render.manifest.json ao lado do\n"
                    "contrato: hash do contrato, de cada input compilado, das ferramentas e do vídeo/áudio decodificados.\n"
                    "backends:\n"
                    "  local  renderiza aqui (CPU; --gpu usa encoder de GPU do HyperFrames se houver)\n"
                    "  colab  NÃO renderiza: gera <saida>.colab-bundle.zip (composição pronta + render_bundle.sh) para\n"
                    "         colab/render.ipynb (GPU, NVENC quando disponível; imprime tempos por etapa)",
        epilog="exemplos:\n  simplicio-video render contract.yaml\n"
               "  simplicio-video render contract.yaml --out /tmp/teste.mp4 --quality draft\n"
               "  simplicio-video render contract.yaml --backend colab   # -> out/<nome>.colab-bundle.zip")
    _contract_arg(p)
    p.add_argument("--backend", "-b", choices=["local", "colab"], default="local", help="onde renderizar (padrão: local)")
    p.add_argument("--out", "-o", type=Path, help="MP4 de saída (local) ou .zip do bundle (colab); padrão: saida.arquivo")
    p.add_argument("--quality", "-q", choices=["draft", "looks", "delivery"], help="qualidade HyperFrames (padrão: saida.qualidade)")
    p.add_argument("--gpu", action="store_true", help="local: encoder de GPU do HyperFrames (--gpu); muda os bytes do vídeo")
    p.add_argument("--workdir", type=Path, help="pasta da composição compilada (padrão: <contrato>/build/simplicio-video)")

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
    from . import contract as ct
    c = ct.load(a.contrato)
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
        if a.backend == "colab":
            render.render_colab(c, out=a.out, quality=a.quality)
        else:
            render.render_local(c, out=a.out, quality=a.quality, workdir=a.workdir, gpu=a.gpu)
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
