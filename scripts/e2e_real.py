#!/usr/bin/env python3
"""Roteiro de testes reais ponta a ponta do simplicio-video, com as chaves e os apps DESTA máquina.

Sem `--sim-gastar` (ou `--yes`) nada roda: o script só detecta o ambiente e imprime o plano, com o custo estimado de cada
check, e sai com 0. Com a flag, roda só o que o ambiente habilita; o que falta vira SKIP com o motivo. Tudo que é gerado
vai para uma pasta temporária (use `--manter` ou `--pasta` para guardar; a padrão fica no disco e o caminho é impresso).

O roteiro também roda, primeiro, o smoke de SO (`scripts/smoke_so.py`) e o das trilhas (`scripts/smoke_trilhas.py`),
e imprime SO, Python, Node e ffmpeg, para que um comando só cubra o smoke também no Windows e no macOS.

Checks reais e a chave ou o app que os habilita (o custo é estimativa; ver docs/custos.md):
  voice-gemini        GEMINI_API_KEY        voice --provider gemini numa cópia do tests/fixtures/mini + render --preview
  swap-estimate       (nenhuma)             swap estimate (sem rede, sem gasto), com mídia sua ou sintética
  swap-run            GEMINI_API_KEY (ou a do --swap-provider)   swap run só com --autorizo, --swap-video, --swap-ref,
                                            --yes e --max-usd (padrão US$ 1,00); estimativa acima do teto: nada é enviado
  busca-consulta      TINYFISH_API_KEY + binário tinyfish   uma consulta (`--atualizar`), conta no teto diário
  voicestudio         app em 127.0.0.1:3900  status, voices e tts para um arquivo temporário
  hypit               Node 22.15+ e npx     clone doctor e clone pricing
  hypit-build         Node 22.15+ e npx     SÓ com --incluir-build, --max-usd e --build-args (o Hypit não tem teto no motor)
  moneyprinter-livre  MoneyPrinter instalado  run sem fonte paga (material local, voz Edge)
  moneyprinter-pago   MoneyPrinter instalado  SÓ com --incluir-pago e --moneyprinter-fonte (a fonte cobra; sem teto no motor)
  toonflow            docker e Toonflow clonado  serve --docker: sobe, consulta 127.0.0.1:3000 e para com SIGINT
  media-fetch         --url + --autorizo    media fetch de um vídeo público que você pode usar

Regras que não cedem: nada roda sem --sim-gastar; o swap nunca gasta acima de --max-usd; o build e a fonte paga exigem a
flag própria e nunca rodam por padrão; chave nunca vai para argumento, log nem saída (vira ***); o plano não cria pasta.

Uso:
  python scripts/e2e_real.py                          plano (nada roda)
  python scripts/e2e_real.py --sim-gastar             roda o que o ambiente habilita
  python scripts/e2e_real.py --sim-gastar --json      só o JSON (simplicio.e2e-real/v1) no stdout; exit 1 se algo falhar
  python scripts/e2e_real.py --sim-gastar --apenas voice-gemini,swap-run --autorizo --swap-video v.mp4 --swap-ref a.png

Exemplos:
  make e2e-real                                       plano, pelo Makefile (Linux e macOS)
  make e2e-real E2E_ARGS="--sim-gastar"               roda de verdade
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import math
import os
import platform
import re
import shlex
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src"
if SRC.is_dir() and str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

SCHEMA = "simplicio.e2e-real/v1"
TETO_PADRAO_USD = 1.00          # teto padrão do swap run (--max-usd)
DURACAO_SINTETICA_S = 4.0       # vídeo sintético dos checks de swap (mínimo do adaptador gemini: 3 s)
JANELA_FALA_S = 1.8             # na cópia do fixture, a fala ganha esta janela (take do Gemini passa de 0,4 s)
FIXTURE = REPO / "tests" / "fixtures" / "mini"
VOZ_EDGE = "pt-BR-FranciscaNeural-Female"  # voz Edge: sem chave
TEXTO_TTS = "Teste do simplicio-video."
TEXTO_ROTEIRO = "Teste de ponta a ponta do simplicio-video."
BUSCA_PADRAO = "o que é a licença Creative Commons CC0"
NODE_MIN = (22, 15)             # tools.NODE_MIN (@hypit/hypit exige node >= 22.15)
PORTA_VOICESTUDIO = 3900
URL_TOONFLOW = "http://127.0.0.1:3000"
CHAVES_CONHECIDAS = ("GEMINI_API_KEY", "FAL_KEY", "WAVESPEED_API_KEY", "KIE_API_KEY", "DASHSCOPE_API_KEY", "TINYFISH_API_KEY")
MINIMO_SEGREDO = 8              # valores menores que isso não são redigidos (evita apagar palavras comuns)
PASS, FAIL, SKIP, PLANO = "PASS", "FAIL", "SKIP", "PLANO"


# ----------------------------------------------------------------------------------------------- tipos
@dataclass
class Saida:
    rc: int
    out: str = ""
    err: str = ""
    expirou: bool = False


@dataclass
class Passo:
    nome: str
    argv: list
    rc: int
    segundos: float
    log: str
    saida: str = ""
    erro: str = ""

    @property
    def ok(self) -> bool:
        return self.rc == 0


@dataclass
class Veredito:
    estado: str
    detalhe: str


class Parar(Exception):
    """Interrompe um check com um veredito (FAIL ou SKIP) já decidido."""

    def __init__(self, veredito: Veredito):
        super().__init__(veredito.detalhe)
        self.veredito = veredito


@dataclass
class Ambiente:
    sistema: str
    python: str
    node: Optional[tuple]
    node_texto: str
    ffmpeg: Optional[str]
    ffmpeg_texto: str
    npx: Optional[str]
    docker: Optional[str]
    tinyfish: Optional[str]
    tinyfish_chave: bool
    chaves: frozenset
    voicestudio: bool
    moneyprinter: bool
    toonflow: bool
    pacote: bool
    adaptadores: dict            # nome -> (variável, verificado)
    fontes_pagas: dict           # fonte -> flag de confirmação (None = sem flag)


@dataclass
class Item:
    id: str
    titulo: str
    estado: str                  # PLANO | SKIP
    motivo: str
    custo: str
    teto_usd: Optional[float]
    executar: Optional[Callable]
    opcional: bool = False


@dataclass
class Resultado:
    id: str
    titulo: str
    estado: str                  # PASS | FAIL | SKIP | PLANO
    detalhe: str
    custo: str
    teto_usd: Optional[float]
    passos: list = field(default_factory=list)
    segundos: float = 0.0


# ----------------------------------------------------------------------------------- sondas (a máquina)
class SondasReais:
    """O que este computador tem. Toda leitura do mundo passa por aqui, para que os testes troquem por fakes."""

    def achar(self, nome: str) -> Optional[str]:
        return shutil.which(nome)

    def porta_aberta(self, host: str, porta: int) -> bool:
        try:
            with socket.create_connection((host, porta), timeout=0.5):
                return True
        except OSError:
            return False

    def versao(self, argv: list) -> Optional[str]:
        try:
            p = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8", errors="replace",
                               stdin=subprocess.DEVNULL, timeout=20)
        except (OSError, subprocess.SubprocessError):
            return None
        linhas = ((p.stdout or "") + (p.stderr or "")).strip().splitlines()
        return linhas[0].strip() if linhas else None

    def env(self) -> dict:
        return dict(os.environ)

    def arquivo_existe(self, caminho) -> bool:
        return Path(caminho).is_file()

    def adaptadores(self) -> dict:
        try:
            from simplicio_video import swap_providers
            out = {}
            for nome in swap_providers.names():
                a = swap_providers.REGISTRY[nome]()
                out[nome] = (a.env_var or "", bool(a.verified))
            return out
        except Exception:  # noqa: BLE001 (pacote ausente: o plano diz isso, não quebra)
            return {}

    def fontes_pagas(self) -> dict:
        try:
            from simplicio_video.moneyprinter import PAID_SOURCES
            return dict(PAID_SOURCES)
        except Exception:  # noqa: BLE001
            return {}

    def moneyprinter_pronto(self) -> bool:
        try:
            from simplicio_video import moneyprinter as mp
            return mp.find_moneyprinter_dir() is not None and mp.venv_python().exists()
        except Exception:  # noqa: BLE001 (uma checagem de presença não derruba o plano)
            return False

    def toonflow_dir(self):
        try:
            from simplicio_video import toonflow
            return toonflow.find_toonflow_dir()
        except Exception:  # noqa: BLE001
            return None

    def pacote(self) -> bool:
        return importlib.util.find_spec("simplicio_video") is not None


def _versao_do_node(texto: Optional[str]) -> Optional[tuple]:
    if not texto:
        return None
    numeros = re.findall(r"\d+", texto)
    return tuple(int(n) for n in numeros[:3]) if numeros else None


def node_ok(versao: Optional[tuple]) -> bool:
    return versao is not None and versao[:2] >= NODE_MIN


def detectar(sondas) -> Ambiente:
    env = sondas.env()
    node = _versao_do_node(sondas.versao(["node", "--version"])) if sondas.achar("node") else None
    ffmpeg = sondas.achar("ffmpeg")
    adaptadores = sondas.adaptadores()
    variaveis = {var for var, _ in adaptadores.values() if var} | set(CHAVES_CONHECIDAS)
    chaves = frozenset(v for v in variaveis if env.get(v))
    tinyfish_chave = bool(env.get("TINYFISH_API_KEY")) or sondas.arquivo_existe(Path.home() / ".tinyfish" / "config.json")
    return Ambiente(
        sistema=platform.platform(), python=f"{platform.python_version()} ({sys.executable})",
        node=node, node_texto=".".join(map(str, node)) if node else "ausente",
        ffmpeg=ffmpeg, ffmpeg_texto=(sondas.versao([ffmpeg, "-version"]) or "?") if ffmpeg else "ausente",
        npx=sondas.achar("npx"), docker=sondas.achar("docker"), tinyfish=sondas.achar("tinyfish"),
        tinyfish_chave=tinyfish_chave, chaves=chaves,
        voicestudio=sondas.porta_aberta("127.0.0.1", PORTA_VOICESTUDIO),
        moneyprinter=sondas.moneyprinter_pronto(), toonflow=sondas.toonflow_dir() is not None,
        pacote=sondas.pacote(), adaptadores=adaptadores, fontes_pagas=sondas.fontes_pagas(),
    )


def _segredos(sondas, amb: Ambiente) -> list:
    env = sondas.env()
    nomes = set(CHAVES_CONHECIDAS) | {var for var, _ in amb.adaptadores.values() if var}
    valores = {env[n] for n in nomes if env.get(n) and len(env[n]) >= MINIMO_SEGREDO}
    return sorted(valores, key=len, reverse=True)


def redigir(texto: str, segredos: list) -> str:
    for s in segredos:
        texto = texto.replace(s, "***")
    return texto


# ------------------------------------------------------------------------------- execução (processos)
def _rodar(argv: list, *, env: dict, cwd: Path, timeout: float) -> Saida:
    """Roda um processo com tempo limite, sem shell. Num tempo esgotado mata o grupo inteiro (npx e docker têm filhos)."""
    kwargs = {"start_new_session": True} if os.name == "posix" else {
        "creationflags": getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)}
    try:
        proc = subprocess.Popen(argv, cwd=str(cwd), env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace", **kwargs)
    except OSError as exc:
        return Saida(127, "", f"não consegui iniciar {argv[0]}: {exc}")
    try:
        out, err = proc.communicate(timeout=timeout)
        return Saida(proc.returncode, out or "", err or "")
    except subprocess.TimeoutExpired:
        _matar_grupo(proc)
        out, err = proc.communicate()
        return Saida(124, out or "", (err or "") + f"\n[tempo esgotado em {timeout:.0f} s]", expirou=True)
    except KeyboardInterrupt:
        _matar_grupo(proc)  # o processo tem sessão própria: sem isto, o Ctrl+C deixaria o filho rodando
        raise


def _matar_grupo(proc) -> None:
    try:
        if os.name == "posix":
            os.killpg(proc.pid, signal.SIGKILL)
        else:
            proc.kill()
    except OSError:
        pass


def _json_de(texto: str) -> Optional[dict]:
    texto = (texto or "").strip()
    try:
        doc = json.loads(texto)
        return doc if isinstance(doc, dict) else None
    except ValueError:
        pass
    for linha in reversed(texto.splitlines()):
        linha = linha.strip()
        if linha.startswith("{"):
            try:
                doc = json.loads(linha)
            except ValueError:
                continue
            return doc if isinstance(doc, dict) else None
    return None


def _ultima_linha(texto: str) -> str:
    linhas = [x.strip() for x in (texto or "").splitlines() if x.strip()]
    return linhas[-1][:200] if linhas else ""


class Ctx:
    """O que um check precisa: a pasta temporária, o executor, o ambiente filho, os segredos e o registro dos passos."""

    def __init__(self, tmp: Path, args, runner, env: dict, amb: Ambiente, segredos: list, teto: float):
        self.tmp, self.args, self.runner, self.env, self.amb = tmp, args, runner, env, amb
        self.segredos, self.teto = segredos, teto
        self.passos: list = []
        self.notas: dict = {}
        self._n = 0

    def pasta(self, nome: str) -> Path:
        p = self.tmp / nome
        p.mkdir(parents=True, exist_ok=True)
        return p

    def passo(self, nome: str, argv: list, timeout: float) -> Passo:
        self._n += 1
        inicio = time.monotonic()
        saida = self.runner(list(argv), env=self.env, cwd=REPO, timeout=timeout)
        seg = time.monotonic() - inicio
        slug = re.sub(r"[^a-z0-9]+", "-", nome.lower()).strip("-") or "passo"
        log = self.pasta("logs") / f"{self._n:02d}-{slug}.log"
        corpo = "$ " + " ".join(map(str, argv)) + f"\n[rc {saida.rc}, {seg:.1f} s]\n--- stdout ---\n{saida.out}\n--- stderr ---\n{saida.err}\n"
        log.write_text(redigir(corpo, self.segredos), encoding="utf-8")
        p = Passo(nome=nome, argv=[redigir(str(a), self.segredos) for a in argv], rc=saida.rc, segundos=round(seg, 3),
                  log=str(log), saida=redigir(saida.out, self.segredos), erro=redigir(saida.err, self.segredos))
        self.passos.append(p)
        return p


def _py(*args) -> list:
    return [sys.executable, "-m", "simplicio_video", *args]


def _exige(p: Passo, rotulo: str) -> None:
    if not p.ok:
        raise Parar(Veredito(FAIL, f"{rotulo}: rc {p.rc}; última linha: {_ultima_linha(p.erro) or _ultima_linha(p.saida) or '-'}"
                                   f" (log: {p.log})"))


def _kb(caminho: Path) -> str:
    return f"{caminho.stat().st_size / 1024:.0f} KB"


# ------------------------------------------------------------------------------------ fixture de voz
def preparar_contrato(origem: Path, destino: Path) -> Path:
    """Copia o fixture mini para `destino` e alarga a janela da fala NA CÓPIA (o take do Gemini costuma passar de 0,4 s).
    O fixture do repositório não muda. A soma das cenas continua igual à duração do formato."""
    import yaml
    if destino.exists():
        raise FileExistsError(str(destino))
    shutil.copytree(origem, destino)
    contrato = destino / "contract.yaml"
    doc = yaml.safe_load(contrato.read_text(encoding="utf-8"))
    cena = doc["cenas"][0]
    cena["fala"]["max_s"] = JANELA_FALA_S
    cena["duracao_s"] = round(max(cena["duracao_s"], cena["fala"]["inicio_s"] + JANELA_FALA_S + 0.2), 3)
    doc["formato"]["duracao_s"] = round(sum(c["duracao_s"] for c in doc["cenas"]), 3)
    contrato.write_text(yaml.safe_dump(doc, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return contrato


# -------------------------------------------------------------------------------- checks (executores)
def _midia_sintetica(ctx: Ctx) -> tuple:
    pasta = ctx.pasta("midia")
    video, ref = pasta / "sintetico.mp4", pasta / "avatar.png"
    ff = ctx.amb.ffmpeg
    if not video.exists():
        p = ctx.passo("ffmpeg: vídeo sintético", [ff, "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc2=size=360x640:rate=24",
                                                 "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000", "-t",
                                                 f"{DURACAO_SINTETICA_S:g}", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
                                                 "-shortest", str(video)], 300)
        _exige(p, "ffmpeg (vídeo sintético)")
    if not ref.exists():
        p = ctx.passo("ffmpeg: imagem sintética", [ff, "-y", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=0x3366aa:s=256x256",
                                                   "-frames:v", "1", str(ref)], 120)
        _exige(p, "ffmpeg (imagem sintética)")
    return video, ref


def _midias_swap(ctx: Ctx) -> tuple:
    a = ctx.args
    if a.swap_video and a.swap_ref:
        return Path(a.swap_video), Path(a.swap_ref)
    return _midia_sintetica(ctx)


def _estimar(ctx: Ctx, video: Path, ref: Path) -> float:
    prov = ctx.args.swap_provider
    p = ctx.passo("swap estimate", _py("swap", "estimate", "--provider", prov, "--video", str(video), "--ref", str(ref), "--json"), 300)
    _exige(p, "swap estimate")
    doc = _json_de(p.saida) or {}
    usd = (doc.get("estimate") or {}).get("usd")
    if not isinstance(usd, (int, float)) or not math.isfinite(usd):
        raise Parar(Veredito(FAIL, f"swap estimate sem estimativa numérica (log: {p.log})"))
    ctx.notas.update(estimativa_usd=float(usd), duracao_s=doc.get("duration_s"), pedacos=doc.get("chunks"))
    return float(usd)


def _chk_smoke_so(ctx: Ctx) -> Veredito:
    p = ctx.passo("smoke de SO", [sys.executable, str(REPO / "scripts" / "smoke_so.py")], 900)
    if not p.ok:
        return Veredito(FAIL, f"smoke_so.py rc {p.rc} (log: {p.log})")
    return Veredito(PASS, _ultima_linha(p.saida) or "smoke de SO ok")


def _chk_smoke_trilhas(ctx: Ctx) -> Veredito:
    p = ctx.passo("smoke das trilhas", [sys.executable, str(REPO / "scripts" / "smoke_trilhas.py")], 900)
    if not p.ok:
        return Veredito(FAIL, f"smoke_trilhas.py rc {p.rc} (log: {p.log})")
    return Veredito(PASS, "trilhas e núcleo ok (sem FAIL)")


def _chk_voice_gemini(ctx: Ctx) -> Veredito:
    pasta = ctx.pasta("voice")
    contrato = preparar_contrato(FIXTURE, pasta / "mini")
    v = ctx.passo("voice --provider gemini", _py("voice", str(contrato), "--provider", "gemini"), 900)
    _exige(v, "voice --provider gemini")
    if not (contrato.parent / "timing.lock.json").is_file():
        return Veredito(FAIL, "voice terminou sem timing.lock.json")
    previa = pasta / "previa.mp4"
    r = ctx.passo("render --preview", _py("render", str(contrato), "--preview", "--out", str(previa)), 1200)
    _exige(r, "render --preview")
    if not previa.is_file() or previa.stat().st_size == 0:
        return Veredito(FAIL, "render --preview não gravou a prévia")
    return Veredito(PASS, f"fala gemini ok; prévia {_kb(previa)} em {previa}")


def _chk_swap_estimate(ctx: Ctx) -> Veredito:
    try:
        video, ref = _midias_swap(ctx)
        usd = _estimar(ctx, video, ref)
    except Parar as exc:
        return exc.veredito
    dur = ctx.notas.get("duracao_s")
    return Veredito(PASS, f"{_usd(usd, 4)} para {_numero(dur)} s em {ctx.notas.get('pedacos')} pedaço(s); sem gasto")


def _chk_swap_run(ctx: Ctx) -> Veredito:
    a = ctx.args
    video, ref = Path(a.swap_video), Path(a.swap_ref)
    usd = _estimar(ctx, video, ref)
    if usd > ctx.teto:
        return Veredito(SKIP, f"estimativa {_usd(usd, 4)} passa do teto {_usd(ctx.teto, 2)} (--max-usd): nada foi enviado")
    out = ctx.pasta("swap") / "saida.mp4"
    argv = _py("swap", "run", "--provider", a.swap_provider, "--video", str(video), "--ref", str(ref), "--out", str(out),
               "--autorizo", "--yes", "--max-usd", str(ctx.teto), "--timeout", "900", "--json")
    if a.aceito_unverified:
        argv.append("--aceito-unverified")
    r = ctx.passo("swap run", argv, 3600)
    doc = _json_de(r.saida) or {}
    if not r.ok or doc.get("state") != "done" or not out.is_file():
        return Veredito(FAIL, f"swap run: rc {r.rc}, estado {doc.get('state')!r} (log: {r.log})")
    return Veredito(PASS, f"MP4 {_kb(out)} em {out}; medido {doc.get('measured_usd')} USD (previsto {_usd(usd, 4)})")


def _chk_busca(ctx: Ctx) -> Veredito:
    p = ctx.passo("busca consulta", _py("busca", "consulta", ctx.args.busca_texto, "--atualizar", "--json"), 300)
    doc = _json_de(p.saida)
    if not p.ok or not doc or "registro_id" not in doc:
        return Veredito(FAIL, f"busca consulta: rc {p.rc}, sem registro de procedência (log: {p.log})")
    return Veredito(PASS, f"{len(doc.get('resultados') or [])} resultado(s); registro {doc['registro_id']}")


def _chk_voicestudio(ctx: Ctx) -> Veredito:
    for nome, argv in (("voicestudio status", _py("voicestudio", "status", "--json")),
                       ("voicestudio voices", _py("voicestudio", "voices", "--json"))):
        _exige(ctx.passo(nome, argv, 60), nome)
    out = ctx.pasta("voicestudio") / "tts.wav"
    t = ctx.passo("voicestudio tts", _py("voicestudio", "tts", TEXTO_TTS, "--out", str(out), "--format", "wav", "--json"), 600)
    _exige(t, "voicestudio tts")
    if not out.is_file() or out.stat().st_size == 0:
        return Veredito(FAIL, "voicestudio tts não gravou o arquivo")
    return Veredito(PASS, f"status, voices e tts ok; {_kb(out)} em {out}")


def _chk_hypit(ctx: Ctx) -> Veredito:
    _exige(ctx.passo("clone doctor", _py("clone", "doctor"), 900), "clone doctor")
    _exige(ctx.passo("clone pricing", _py("clone", "pricing"), 600), "clone pricing")
    return Veredito(PASS, "clone doctor e clone pricing ok (leitura, sem build)")


def _chk_hypit_build(ctx: Ctx) -> Veredito:
    p = ctx.passo("clone build", _py("clone", "build", *shlex.split(ctx.args.build_args)), 7200)
    if not p.ok:
        return Veredito(FAIL, f"clone build: rc {p.rc} (log: {p.log})")
    return Veredito(PASS, f"build do Hypit terminou (teto informado {_usd(ctx.args.max_usd, 2)}; o Hypit não aplica teto)")


def _material_sintetico(ctx: Ctx, destino: Path) -> Path:
    if not destino.exists():
        p = ctx.passo("ffmpeg: material sintético", [ctx.amb.ffmpeg, "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                                                     "testsrc2=size=360x640:rate=24", "-t", "5", "-an", "-c:v", "libx264",
                                                     "-pix_fmt", "yuv420p", str(destino)], 300)
        _exige(p, "ffmpeg (material)")
    return destino


def _veredito_mp(p: Passo, out: Path) -> Veredito:
    doc = _json_de(p.saida)
    if not p.ok or not doc:
        return Veredito(FAIL, f"moneyprinter run: rc {p.rc} (log: {p.log})")
    if doc.get("failed") or not doc.get("total"):
        return Veredito(FAIL, f"moneyprinter run: total {doc.get('total')}, falhas {doc.get('failed')} (log: {p.log})")
    return Veredito(PASS, f"{doc.get('total')} tarefa(s) sem falha; saída em {out}")


def _chk_moneyprinter_livre(ctx: Ctx) -> Veredito:
    pasta = ctx.pasta("moneyprinter")
    material = _material_sintetico(ctx, pasta / "material.mp4")
    out = pasta / "saida-livre"
    argv = _py("moneyprinter", "run", "--out", str(out), "--json", "--", "--video-script", TEXTO_ROTEIRO,
               "--video-source", "local", "--video-materials", str(material), "--voice-name", VOZ_EDGE,
               "--video-aspect", "9:16", "--no-subtitle-enabled")
    return _veredito_mp(ctx.passo("moneyprinter run (livre)", argv, 1800), out)


def _chk_moneyprinter_pago(ctx: Ctx) -> Veredito:
    fonte = ctx.args.moneyprinter_fonte
    flag = ctx.amb.fontes_pagas.get(fonte)
    out = ctx.pasta("moneyprinter") / "saida-paga"
    tokens = ["--video-script", TEXTO_ROTEIRO, "--video-source", fonte, *([flag] if flag else []),
              "--voice-name", VOZ_EDGE, "--video-aspect", "9:16", "--no-subtitle-enabled"]
    argv = _py("moneyprinter", "run", "--out", str(out), "--json", "--yes", "--", *tokens)
    return _veredito_mp(ctx.passo(f"moneyprinter run (paga: {fonte})", argv, 3600), out)


def _abrir_http(url: str) -> Optional[int]:
    """Código HTTP da URL local (sem proxy do ambiente) ou None se nada responde."""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(url, timeout=5) as r:
            return r.status
    except urllib.error.HTTPError as exc:
        return exc.code
    except (urllib.error.URLError, OSError, ValueError):
        return None


def esperar_http(url: str, limite_s: float, *, abrir: Callable = _abrir_http, dormir: Callable = time.sleep,
                 agora: Callable = time.monotonic, vivo: Callable = lambda: True) -> Optional[int]:
    """Consulta `url` até responder (devolve o código) ou até o processo morrer ou o tempo acabar (devolve None)."""
    inicio = agora()
    while True:
        if not vivo():
            return None
        codigo = abrir(url)
        if codigo is not None:
            return codigo
        if agora() - inicio >= limite_s:
            return None
        dormir(5)


def _parar_processo(proc, espera_s: float = 120) -> None:
    """Para como um Ctrl+C (SIGINT no grupo, para o `docker compose up` parar os contêineres); se não sair, mata."""
    if proc.poll() is not None:
        return
    try:
        if os.name == "posix":
            os.killpg(proc.pid, signal.SIGINT)
        else:
            proc.terminate()
        proc.wait(timeout=espera_s)
    except (OSError, subprocess.TimeoutExpired):
        _matar_grupo(proc)
        try:
            proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            pass


def _chk_toonflow(ctx: Ctx) -> Veredito:
    dk = ctx.passo("docker info", ["docker", "info", "--format", "{{.ServerVersion}}"], 60)
    if not dk.ok:
        return Veredito(SKIP, "o daemon do Docker não respondeu (docker info falhou); abra o Docker e rode de novo")
    log = ctx.pasta("toonflow") / "serve.log"
    argv = _py("toonflow", "serve", "--docker")
    with open(log, "w", encoding="utf-8") as fh:
        kwargs = {"start_new_session": True} if os.name == "posix" else {
            "creationflags": getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)}
        proc = subprocess.Popen(argv, cwd=str(REPO), env=ctx.env, stdin=subprocess.DEVNULL, stdout=fh,
                                stderr=subprocess.STDOUT, **kwargs)
    try:
        codigo = esperar_http(URL_TOONFLOW, 1200, vivo=lambda: proc.poll() is None)
    finally:
        _parar_processo(proc)
    if codigo is None:
        return Veredito(FAIL, f"o Toonflow não respondeu em {URL_TOONFLOW} (log: {log})")
    return Veredito(PASS, f"HTTP {codigo} em {URL_TOONFLOW}; serviço parado com SIGINT (log: {log})")


def _chk_media_fetch(ctx: Ctx) -> Veredito:
    pasta = ctx.pasta("media")
    out = pasta / "fetch.mp4"
    p = ctx.passo("media fetch", _py("media", "fetch", ctx.args.url, "-o", str(out), "--autorizo", "--max-mb", "200",
                                     "--timeout", "600"), 900)
    if not p.ok:
        return Veredito(FAIL, f"media fetch: rc {p.rc} (log: {p.log})")
    procedencia = sorted(pasta.glob("*.fetch.json"))
    if not out.is_file() or not procedencia:
        return Veredito(FAIL, "media fetch não gravou o vídeo e o registro de procedência")
    return Veredito(PASS, f"{_kb(out)} baixados com registro {procedencia[0].name}")


# ---------------------------------------------------------------------------------- definição dos checks
def _falta_ffmpeg(amb: Ambiente) -> list:
    return [] if amb.ffmpeg else ["falta ffmpeg no PATH"]


def _falta_node(amb: Ambiente) -> list:
    faltas = []
    if not amb.npx:
        faltas.append("falta npx (Node no PATH)")
    if not node_ok(amb.node):
        faltas.append(f"Node {NODE_MIN[0]}.{NODE_MIN[1]} ou mais (há: {amb.node_texto})")
    return faltas


def _falta_chave(amb: Ambiente, nome: str) -> list:
    return [] if nome in amb.chaves else [f"falta {nome} no ambiente"]


def _custo_swap(provedor: str, segundos: float) -> Optional[float]:
    try:
        from simplicio_video.swap_providers import REGISTRY
        from simplicio_video.swap_providers.base import Job
        job = Job(video=Path("sintetico.mp4"), refs=[], duration_s=segundos, fps=24.0, width=360, height=640, has_audio=True)
        return float(REGISTRY[provedor]().estimate(job).usd)
    except Exception:  # noqa: BLE001 (o custo é informativo; sem ele o plano continua)
        return None


def _numero(valor) -> str:
    """Número no formato pt-BR sem zeros à direita (4.0 vira 4; 2.5 vira 2,5)."""
    return "?" if valor is None else f"{float(valor):g}".replace(".", ",")


def _usd(valor: float, casas: int) -> str:
    """Dólar no formato do repositório (US$ 0,44): vírgula decimal."""
    return f"US$ {valor:.{casas}f}".replace(".", ",")


def _txt_usd(valor: Optional[float], casas: int = 4) -> str:
    return _usd(valor, casas) if valor is not None else "não calculada"


@dataclass(frozen=True)
class Definicao:
    id: str
    titulo: str
    faltas: Callable
    custo: Callable
    executar: Callable
    teto: Callable = lambda a: None
    opcional: bool = False


PACOTE_FALTA = "o pacote simplicio_video não importa (bash scripts/dev_install.sh --with test,mcp)"


def _f_voice(a, amb):
    return _falta_chave(amb, "GEMINI_API_KEY") + _falta_ffmpeg(amb) + _falta_node(amb)


def _f_swap_estimate(a, amb):
    return _falta_ffmpeg(amb)


def _f_swap_run(a, amb):
    prov = a.swap_provider
    variavel, verificado = amb.adaptadores.get(prov, ("", False))
    faltas = (_falta_chave(amb, variavel) if variavel else []) + _falta_ffmpeg(amb)
    if not a.swap_video:
        faltas.append("falta --swap-video (o vídeo a trocar, seu)")
    if not a.swap_ref:
        faltas.append("falta --swap-ref (a imagem do avatar, sua)")
    if not a.autorizo:
        faltas.append("falta --autorizo (você tem direito sobre o vídeo e as imagens)")
    if not verificado and not a.aceito_unverified:
        faltas.append(f"o adaptador {prov} não é verificado: passe --aceito-unverified")
    return faltas


def _f_busca(a, amb):
    faltas = []
    if not amb.tinyfish:
        faltas.append("falta o binário tinyfish (simplicio-video busca status mostra como instalar)")
    if not amb.tinyfish_chave:
        faltas.append("falta TINYFISH_API_KEY (ou o login do tinyfish)")
    return faltas


def _f_voicestudio(a, amb):
    return [] if amb.voicestudio else [f"nenhum app ouvindo em 127.0.0.1:{PORTA_VOICESTUDIO} (abra o VoiceStudio)"]


def _f_build(a, amb):
    faltas = []
    if not a.incluir_build:
        faltas.append("falta --incluir-build (o build gasta nos provedores)")
    if a.max_usd is None:
        faltas.append("falta --max-usd (o build não tem teto padrão)")
    if not a.build_args.strip():
        faltas.append("falta --build-args (o que o Hypit deve construir)")
    return faltas + _falta_node(amb)


def _f_mp_livre(a, amb):
    return ([] if amb.moneyprinter else ["MoneyPrinterTurbo não está pronto (simplicio-video moneyprinter clone e setup)"]) \
        + _falta_ffmpeg(amb)


def _f_mp_pago(a, amb):
    faltas = []
    if not a.incluir_pago:
        faltas.append("falta --incluir-pago (a fonte cobra por vídeo)")
    if not a.moneyprinter_fonte:
        faltas.append("falta --moneyprinter-fonte (ex.: wavespeed)")
    if not amb.moneyprinter:
        faltas.append("MoneyPrinterTurbo não está pronto (simplicio-video moneyprinter clone e setup)")
    return faltas


def _f_toonflow(a, amb):
    faltas = []
    if not amb.docker:
        faltas.append("docker não encontrado no PATH")
    if not amb.toonflow:
        faltas.append("Toonflow não clonado (simplicio-video toonflow clone)")
    return faltas


def _f_media(a, amb):
    faltas = []
    if not a.url:
        faltas.append("falta --url (um vídeo público que você pode usar)")
    if not a.autorizo:
        faltas.append("falta --autorizo (você pode usar este vídeo)")
    return faltas + _falta_ffmpeg(amb)


def _c_swap_run(a, amb):
    teto = a.max_usd if a.max_usd is not None else TETO_PADRAO_USD
    est = _custo_swap(a.swap_provider, DURACAO_SINTETICA_S)
    return f"até {_usd(teto, 2)} (teto); {DURACAO_SINTETICA_S:g} s custam {_txt_usd(est, 3)}"


def _c_swap_estimate(a, amb):
    est = _custo_swap(a.swap_provider, DURACAO_SINTETICA_S)
    return f"0 gasto (sem rede); {DURACAO_SINTETICA_S:g} s de estimativa: {_txt_usd(est, 3)}"


DEFINICOES = [
    Definicao("smoke-so", "smoke de SO (scripts/smoke_so.py)", lambda a, g: [], lambda a, g: "0 (offline, pasta isolada)",
              _chk_smoke_so),
    Definicao("smoke-trilhas", "smoke das trilhas (scripts/smoke_trilhas.py)", lambda a, g: [],
              lambda a, g: "0 (só leitura)", _chk_smoke_trilhas),
    Definicao("voice-gemini", "voz Gemini + prévia (tests/fixtures/mini)", _f_voice,
              lambda a, g: "menos de US$ 0,01 (uma fala curta; docs/custos.md)", _chk_voice_gemini),
    Definicao("swap-estimate", "swap estimate (sem gasto)", _f_swap_estimate, _c_swap_estimate, _chk_swap_estimate),
    Definicao("swap-run", "swap run (gasta, com teto)", _f_swap_run, _c_swap_run, _chk_swap_run,
              teto=lambda a: a.max_usd if a.max_usd is not None else TETO_PADRAO_USD),
    Definicao("busca-consulta", "busca na web (uma consulta)", _f_busca,
              lambda a, g: "1 chamada do teto diário (padrão 20 por dia); US$ conforme a conta TinyFish", _chk_busca),
    Definicao("voicestudio", "VoiceStudio (status, voices, tts)", _f_voicestudio,
              lambda a, g: "0 (app local, sua GPU)", _chk_voicestudio),
    Definicao("hypit", "Hypit: clone doctor e clone pricing", lambda a, g: _falta_node(g),
              lambda a, g: "0 (leitura; o npx baixa o pacote fixado)", _chk_hypit),
    Definicao("hypit-build", "Hypit: clone build (opcional)", _f_build, lambda a, g: "não calculado: o Hypit cobra por provedor, sem teto no motor",
              _chk_hypit_build, teto=lambda a: a.max_usd, opcional=True),
    Definicao("moneyprinter-livre", "MoneyPrinter run sem fonte paga", _f_mp_livre,
              lambda a, g: "0 US$ (material local, voz Edge)", _chk_moneyprinter_livre),
    Definicao("moneyprinter-pago", "MoneyPrinter run com fonte paga (opcional)", _f_mp_pago,
              lambda a, g: "não calculado: a fonte cobra por vídeo, sem teto no motor", _chk_moneyprinter_pago, opcional=True),
    Definicao("toonflow", "Toonflow: serve --docker, consulta e parada", _f_toonflow,
              lambda a, g: "0 US$ (local; baixa imagens do Docker)", _chk_toonflow),
    Definicao("media-fetch", "media fetch de um vídeo público", _f_media,
              lambda a, g: "0 US$ (download público; grava a procedência)", _chk_media_fetch),
]
IDS = [d.id for d in DEFINICOES]


def planejar(amb: Ambiente, args) -> list:
    """Um Item por check: PLANO (roda com --sim-gastar) ou SKIP com o motivo. Não executa nada."""
    itens = []
    for d in DEFINICOES:
        faltas = list(d.faltas(args, amb))
        if not amb.pacote and d.id != "smoke-so":  # smoke-so é só o SO: não importa o pacote
            faltas.insert(0, PACOTE_FALTA)
        if args.apenas and d.id not in args.apenas:
            faltas.insert(0, "fora de --apenas")
        itens.append(Item(id=d.id, titulo=d.titulo, estado=SKIP if faltas else PLANO, motivo="; ".join(faltas),
                          custo=d.custo(args, amb), teto_usd=d.teto(args), executar=d.executar, opcional=d.opcional))
    return itens


# --------------------------------------------------------------------------------------------- CLI
def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="e2e_real.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sim-gastar", "--yes", dest="sim_gastar", action="store_true",
                    help="consentimento: roda os checks que o ambiente habilita (sem ele só mostra o plano)")
    ap.add_argument("--json", action="store_true", help="imprime só o JSON (simplicio.e2e-real/v1) no stdout")
    ap.add_argument("--apenas", metavar="IDS", help="só estes checks, separados por vírgula (ex.: voice-gemini,swap-run)")
    ap.add_argument("--pasta", metavar="DIR", help="pasta de saída (tem de não existir ou estar vazia); padrão: temporária nova")
    ap.add_argument("--limpar", action="store_true", help="apaga a pasta temporária no fim (sem isto ela fica, com o caminho impresso)")
    ap.add_argument("--max-usd", type=float, default=None, metavar="USD",
                    help=f"teto de gasto: do swap run (padrão {TETO_PADRAO_USD:.2f}) e obrigatório no build do Hypit")
    ap.add_argument("--swap-provider", default="gemini", help="adaptador do swap (padrão gemini; fal, wavespeed, kie, alibaba são não verificados)")
    ap.add_argument("--swap-video", metavar="ARQ", help="vídeo a trocar (seu; o swap run exige)")
    ap.add_argument("--swap-ref", metavar="ARQ", help="imagem do avatar (sua; o swap run exige)")
    ap.add_argument("--aceito-unverified", action="store_true", help="aceita gastar num adaptador não verificado")
    ap.add_argument("--autorizo", action="store_true", help="você tem direito sobre as mídias usadas (swap run e media fetch)")
    ap.add_argument("--url", metavar="URL", help="vídeo público que você pode usar (media fetch; registra a procedência)")
    ap.add_argument("--busca-texto", default=BUSCA_PADRAO, help="consulta única do check de busca (não envie dado pessoal)")
    ap.add_argument("--incluir-build", action="store_true", help="roda clone build do Hypit (gasta; exige --max-usd e --build-args)")
    ap.add_argument("--build-args", default="", metavar="ARGS", help="argumentos do clone build, entre aspas")
    ap.add_argument("--incluir-pago", action="store_true", help="roda o MoneyPrinter com uma fonte paga (gasta; exige --moneyprinter-fonte)")
    ap.add_argument("--moneyprinter-fonte", default=None, metavar="FONTE", help="fonte paga do MoneyPrinter (ex.: wavespeed)")
    return ap


def _validar(ap: argparse.ArgumentParser, a, amb: Ambiente) -> None:
    if a.max_usd is not None and not (math.isfinite(a.max_usd) and a.max_usd >= 0):
        ap.error("--max-usd precisa ser um número finito, 0 ou maior")
    if amb.adaptadores and a.swap_provider not in amb.adaptadores:  # sem o pacote a lista vem vazia: o plano já diz por quê
        ap.error(f"--swap-provider desconhecido: {a.swap_provider} (use: {', '.join(sorted(amb.adaptadores))})")
    for nome, caminho in (("--swap-video", a.swap_video), ("--swap-ref", a.swap_ref)):
        if caminho and not Path(caminho).is_file():
            ap.error(f"{nome}: arquivo não encontrado: {caminho}")
    if a.url and not re.match(r"^https?://", a.url):
        ap.error("--url precisa ser http:// ou https://")
    if amb.fontes_pagas and a.moneyprinter_fonte and a.moneyprinter_fonte not in amb.fontes_pagas:
        ap.error(f"--moneyprinter-fonte desconhecido: {a.moneyprinter_fonte} (fontes pagas: {', '.join(sorted(amb.fontes_pagas))})")
    if a.apenas:
        pedidos = [x.strip() for x in a.apenas.split(",") if x.strip()]
        desconhecidos = [x for x in pedidos if x not in IDS]
        if desconhecidos:
            ap.error(f"--apenas com check desconhecido: {', '.join(desconhecidos)} (use: {', '.join(IDS)})")
        a.apenas = pedidos


def _cel(texto: str) -> str:
    return str(texto).replace("|", "\\|").replace("\n", " ")


def _tabela(resultados: list) -> str:
    linhas = ["| Check | Estado | Custo previsto | Detalhe |", "|---|---|---|---|"]
    for r in resultados:
        linhas.append(f"| `{r.id}` | {r.estado} | {_cel(r.custo)} | {_cel(r.detalhe)} |")
    return "\n".join(linhas)


def _cabecalho(amb: Ambiente, modo: str, pasta: str) -> list:
    return [
        "# e2e real do simplicio-video",
        f"- modo: {modo}",
        f"- SO: {amb.sistema}",
        f"- Python: {amb.python}",
        f"- Node: {amb.node_texto} (mínimo {NODE_MIN[0]}.{NODE_MIN[1]} para o Hypit)",
        f"- ffmpeg: {amb.ffmpeg_texto}",
        f"- docker: {'sim' if amb.docker else 'não'}",
        f"- pasta de saída: {pasta}",
        f"- teto do swap: {_usd(TETO_PADRAO_USD, 2)} padrão (--max-usd); busca: uma chamada conta no teto diário",
    ]


def _ambiente_filho(base: dict) -> dict:
    env = dict(base)
    env.pop("SIMPLICIO_OFFLINE", None)  # o roteiro é o único lugar que pede rede de propósito
    env["PYTHONPATH"] = str(SRC) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def _executar(itens: list, ctx: Ctx, segredos: list) -> list:
    resultados = []
    for it in itens:
        if it.estado != PLANO:
            resultados.append(Resultado(it.id, it.titulo, SKIP, it.motivo, it.custo, it.teto_usd))
            continue
        inicio = time.monotonic()
        n_antes = len(ctx.passos)
        try:
            v = it.executar(ctx)
        except Parar as exc:
            v = exc.veredito
        except Exception as exc:  # noqa: BLE001 (um check quebrado não derruba os outros; o erro é redigido)
            v = Veredito(FAIL, f"erro inesperado: {type(exc).__name__}: {str(exc)[:160]}")
        resultados.append(Resultado(it.id, it.titulo, v.estado, redigir(v.detalhe, segredos), it.custo, it.teto_usd,
                                    passos=[_passo_json(p) for p in ctx.passos[n_antes:]],
                                    segundos=round(time.monotonic() - inicio, 3)))
    return resultados


def _passo_json(p: Passo) -> dict:
    return {"nome": p.nome, "argv": p.argv, "rc": p.rc, "ok": p.ok, "segundos": p.segundos, "log": p.log}


def _resumo(resultados: list) -> dict:
    cont = {PASS: 0, FAIL: 0, SKIP: 0, PLANO: 0}
    for r in resultados:
        cont[r.estado] = cont.get(r.estado, 0) + 1
    return cont


def main(argv: Optional[list] = None, *, sondas=None, runner=None) -> int:
    ap = _parser()
    a = ap.parse_args(argv)
    sondas = sondas or SondasReais()
    runner = runner or _rodar
    amb = detectar(sondas)
    _validar(ap, a, amb)
    segredos = _segredos(sondas, amb)
    teto = a.max_usd if a.max_usd is not None else TETO_PADRAO_USD
    itens = planejar(amb, a)

    tmp: Optional[Path] = None
    criada = False
    if a.sim_gastar:
        if a.pasta:
            tmp = Path(a.pasta).resolve()
            if tmp.exists() and any(tmp.iterdir()):
                ap.error(f"--pasta {tmp} já existe e não está vazia")
            tmp.mkdir(parents=True, exist_ok=True)
        else:
            tmp = Path(tempfile.mkdtemp(prefix="simplicio-e2e-real-")).resolve()
            criada = True
    ctx = Ctx(tmp or Path("<criada ao rodar>"), a, runner, _ambiente_filho(sondas.env()), amb, segredos, teto)

    modo = "executado" if a.sim_gastar else "plano (nada roda; acrescente --sim-gastar para executar)"
    cabecalho = _cabecalho(amb, modo, str(tmp) if tmp else (str(Path(a.pasta).resolve()) if a.pasta else "<criada ao rodar>"))
    fluxo = sys.stderr if a.json else sys.stdout
    print("\n".join(cabecalho) + "\n", file=fluxo)

    if a.sim_gastar:
        resultados = _executar(itens, ctx, segredos)
    else:
        resultados = [Resultado(it.id, it.titulo, it.estado, it.motivo or "pronto (roda com --sim-gastar)", it.custo, it.teto_usd)
                      for it in itens]

    resumo = _resumo(resultados)
    rc = 1 if resumo[FAIL] else 0
    doc = {"schema": SCHEMA, "modo": "executado" if a.sim_gastar else "plano",
           "sistema": {"so": amb.sistema, "python": amb.python, "node": amb.node_texto, "ffmpeg": amb.ffmpeg_texto,
                       "docker": bool(amb.docker)},
           "pasta": str(tmp) if tmp else None, "teto_padrao_usd": TETO_PADRAO_USD, "teto_usd": teto,
           "checks": [{"id": r.id, "titulo": r.titulo, "estado": r.estado, "motivo": r.detalhe if r.estado in (SKIP, PLANO) else "",
                       "detalhe": r.detalhe if r.estado in (PASS, FAIL) else "", "custo_previsto": r.custo,
                       "teto_usd": r.teto_usd, "segundos": r.segundos, "passos": r.passos} for r in resultados],
           "resumo": resumo, "exit": rc}
    print(_tabela(resultados), file=fluxo)
    print(f"\nresumo: {resumo}", file=fluxo)
    if not a.sim_gastar:
        print("Nada rodou. Para executar: python scripts/e2e_real.py --sim-gastar (ou make e2e-real E2E_ARGS=\"--sim-gastar\").",
              file=fluxo)
    print("Os custos são estimativas. O motor só impõe teto no swap (--max-usd); o build do Hypit e a fonte paga do "
          "MoneyPrinter não têm teto no motor.", file=fluxo)
    if a.json:
        print(redigir(json.dumps(doc, ensure_ascii=False, indent=2), segredos))
    if criada and a.limpar and tmp:
        shutil.rmtree(tmp, ignore_errors=True)
    elif tmp:
        print(f"\npasta de saída mantida: {tmp}", file=fluxo)
    return rc


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("e2e_real: interrompido (Ctrl+C); o processo em curso foi parado", file=sys.stderr)
        sys.exit(130)
