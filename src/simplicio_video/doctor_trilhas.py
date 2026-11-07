"""`simplicio-video doctor trilhas [--json] [--online]` and the row `trilhas` of `doctor all`: the state of the external tracks of tools.TOOLS.

For each track of tools.TOOLS (registry order), in `checks`, one row per thing that was looked at, each `ok`, `warn` or `fail`
with the exact command that fixes it (`fix`), like the doctor's other checks:

  instalada        the checkout (git), the binary (npm) or the venv program (pip) is there; `fail` for a broken install (a folder
                   that is not a checkout, a .git that does not read, a dangling link, a binary that does not run, a venv without
                   its program)
  pin              the commit or version in use (registry pin, the lock's, or SIMPLICIO_<NAME>_REF) is the one installed; an
                   override that is not a commit (git) or a version (npm, pip) is not used and is reported without its value
  integridade      matchcut's pinned scripts and video-to-skill's SKILL.md and references: their sha256 at the pinned commit; `fail` if one
                   changed (instagram: see `instagram status`)
  setup:<item>     the track's own setup: venv, node_modules, build, config.toml, .env.local
  dep:<name>       system dependencies: git, bun, node (version), npx, npm, ffmpeg, docker (optional), SIMPLICIO_TTS_PY (video-use)
  upstream         only with --online: the same resolution as `update --check` (git ls-remote, npm view, PyPI); video-use and video_to_skill are pin-only

Offline by default: nothing here reads the network, starts a shell or writes a file. The version of a binary is read by running
`--version` with the closed environment of `status` (no key of the shell reaches it). Every text that comes from a child process,
the environment or a folder name is cleaned (controls and line separators out) and cut before it reaches a row or a fix. Status per
track: the worst of its rows; a track that is not installed is `warn` (it is optional), never `fail`.

Output: `texto(doc)` for the terminal; `collect()` returns {"schema": "simplicio.doctor-trilhas/v1", "status", "online", "tracks"};
`linha_do_doctor(doc)` is the one aggregated row of `doctor all`.
"""
from __future__ import annotations

import functools
import os
import re
import shlex
import subprocess
import sys
import threading
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Optional

from . import hostos, paths, terceiros, tools, tools_lock, tools_update
from .fsutil import sha256_file
from .status import ENV_FERRAMENTA

SCHEMA = "simplicio.doctor-trilhas/v1"
_RANK = {"ok": 0, "warn": 1, "fail": 2}
_VERSAO = re.compile(r"\d+\.\d+\.\d+")
# controls, soft hyphen, ALM, Mongolian vowel separator, line/paragraph separators, zero-width and bidi marks, word joiner and the
# invisible operators, isolates, the interlinear annotations, the BOM and the tag characters. The emoji selector U+FE0F is left alone.
_CONTROLE = re.compile("[\x00-\x1f\x7f-\x9f\u00ad\u0600-\u0605\u061c\u06dd\u070f\u115f\u180e\u2028\u2029\u200b-\u200f\u202a-\u202e\u2060-\u2064"
                       "\u2066-\u206f\u3164\ufeff\ufff9-\ufffb\U000e0000-\U000e007f\U000e0100-\U000e01ef]")
MAX_ARQUIVO_FIXADO = 1024 * 1024  # the pinned files are a few KB; a bigger one is not the pinned one
TEMPO_ESGOTADO = "tempo esgotado"  # the reason _leitura_do_checkout gives when git did not answer
LIMITE_LOCAL_S = 5.0  # each local program the doctor runs (git rev-parse, `<exe> --version`): a hung one is a finding, not a wait
ORCAMENTO_ONLINE_S = 25.0  # the whole --online: every upstream read together. A proxy that never answers costs this, once
NODE_HYPIT = tools.NODE_MIN  # (22, 15): @hypit/hypit "engines"
# The command that installs each track that has a verb, and the dependencies of each track, by track name: derived from TOOLS (the
# `clone_verb` and `deps` fields), never written here. The checks below read the fields of the track itself.
CLONE = {t.name: f"simplicio-video {t.command} {t.clone_verb}" for t in tools.TOOLS.values() if t.clone_verb}
# yt-dlp is not installed by a command of its own: the first `media fetch` installs the pinned one (it needs a URL and --autorizo)
YTDLP_INSTALA = "instala na primeira vez que você usar `simplicio-video media fetch` (exige uma URL e --autorizo)"
# (name, required, minimum version or None) for the tracks that need more than git; `hypit` adds npx when it has no binary
DEPS = {t.name: [tools.parse_dep(spec) for spec in t.deps] for t in tools.TOOLS.values()}
# the dependencies `_deps` knows how to look for (a track that declares another one gets a warning row that names it)
DEP_NOMES = ("node", "bun", "docker", "ffmpeg", "npx", "npm", "SIMPLICIO_TTS_PY")


# --- text that may come from outside, and the quoting of paths written into a fix ------------------------------------------


def _limpa(texto: Any, limite: int = 300) -> str:
    """Text that came from a child process, the environment, a file or a folder name: the controls and the line separators become
    spaces, and it is cut to `limite` characters. Nothing of it can open a row of its own, a terminal sequence or a command."""
    s = _CONTROLE.sub(" ", str(texto))
    return s if len(s) <= limite else s[: limite - 3] + "..."


def _limpa_valor(valor: Any) -> Any:
    if isinstance(valor, str):
        return _limpa(valor)
    if isinstance(valor, dict):
        return {k: _limpa_valor(v) for k, v in valor.items()}
    if isinstance(valor, list):
        return [_limpa_valor(v) for v in valor]
    return valor


def _q(valor: Any) -> str:
    """A path or a name written into a command of a fix: quoted for the shell (POSIX), or as cmd.exe reads it (Windows)."""
    texto = str(valor)
    return subprocess.list2cmdline([texto]) if os.name == "nt" else shlex.quote(texto)


def _row(name: str, status: str, summary: str, fix: Optional[str] = None, detail: Optional[dict] = None) -> dict:
    return {"name": name, "status": status, "summary": _limpa(summary), "fix": _limpa(fix, 1000) if fix else None,
            "detail": _limpa_valor(detail or {})}


def _modulo(nome: str):
    """A module a registry pointer names (`Tool.setup_probe`, `integrity`, `checkout_probe`), imported when it is asked for: the tracks import
    `tools`, so neither `tools` nor the doctor can import them at the top. Spelled out one by one, because the package imports no module by a
    computed name (tests/test_motor_sem_vendas.py); a track that points into a module that is not here fails loudly (ImportError), and the
    parity test says so."""
    if nome == "doctor_trilhas":
        return sys.modules[__name__]
    if nome == "matchcut":
        from . import matchcut
        return matchcut
    if nome == "montage":
        from . import montage
        return montage
    if nome == "video_to_skill":
        from . import video_to_skill
        return video_to_skill
    raise ImportError(f"o doctor não sabe abrir o módulo {nome!r} (os que sabe: doctor_trilhas, matchcut, montage, video_to_skill)")


def lookup(ref: tuple[str, str]):
    """What a registry pointer names: `(module, path)` is a module of this package and a dotted path inside it (`PINNED_SHA256`, `PINS.files`:
    an attribute, or the key of a dict). Read when it is asked for, so a test that replaces the attribute is seen and a module is imported only
    for the track that points to it. A missing module, attribute or key is an ImportError, AttributeError or KeyError."""
    modulo, caminho = ref
    achado = _modulo(modulo)
    for parte in caminho.split("."):
        achado = achado[parte] if isinstance(achado, Mapping) else getattr(achado, parte)
    return achado


def _ache(nome: str) -> Optional[str]:
    """A program on PATH, looked up as commands/doctor.py does (PATHEXT on Windows, the Homebrew folders on macOS)."""
    return hostos.find_tool(nome)


def _ambiente() -> dict:
    """The only variables a probe of a program gets (the closed environment of `status`: no key of the shell). The environment is read at
    the call (`base=os.environ` here, not the default of the function, which is fixed when `terceiros` is imported)."""
    return terceiros.env_para_terceiro(ENV_FERRAMENTA, base=os.environ)


_MEMO: dict = {}  # per collect(): the node version is asked once, however many tracks need it


_MEMO_TRAVA = threading.Lock()  # the tracks are checked in threads: the first one asks, the others wait for its answer


def _node_versao() -> Optional[tuple]:
    """The node version, asked once per collect() (see _node_versao_sonda)."""
    with _MEMO_TRAVA:
        if "node" not in _MEMO:
            _MEMO["node"] = _node_versao_sonda()
        return _MEMO["node"]


def _node_versao_sonda() -> Optional[tuple]:
    """(major, minor, patch) of the `node` on PATH, or None. The output is read with `replace`: a console code page is not UTF-8."""
    caminho = _ache("node")
    if caminho is None:
        return None
    try:
        r = hostos.run_limitado([caminho, "--version"], timeout=LIMITE_LOCAL_S, env=_ambiente())
    except (OSError, subprocess.SubprocessError):
        return None
    achado = re.match(r"\s*v?(\d+)\.(\d+)\.(\d+)", (r.stdout or "")[:200]) if r.returncode == 0 else None
    return tuple(int(x) for x in achado.groups()) if achado else None


def _npx_pronto() -> bool:
    """npx on PATH and Node >= tools.NODE_MIN: an npm track runs through npx at its pin (checked, nothing downloaded)."""
    versao = _node_versao()
    return _ache("npx") is not None and versao is not None and versao[:2] >= tools.NODE_MIN


def _pior(estados) -> str:
    return max(estados, key=_RANK.__getitem__, default="ok")


def _versao_texto(versao: tuple) -> str:
    return ".".join(str(x) for x in versao)


# --- the pin in use: the registry, the lock, or an override that is checked before it is used ----------------------------


def _ref_valida(t: tools.Tool, valor: str) -> bool:
    """A commit for git, a version for npm and pip: the same patterns the lock and `update` accept."""
    if t.kind == "git":
        return bool(tools_lock.GIT_REF.fullmatch(valor))
    if t.kind == "npm":
        return bool(tools_lock.NPM_VERSION.fullmatch(valor))
    return bool(tools_lock.VERSION.fullmatch(valor))


def _ref_em_uso(t: tools.Tool) -> tuple[str, str, Optional[str]]:
    """(ref, source, problem): what the track really uses. An override that is not a commit or a version is not used: the registry
    pin stands, `problem` says so, and the value is never printed (it may be a token typed by mistake)."""
    nome_var = tools.override_var(t)
    valor = os.environ.get(nome_var)
    if valor:
        if _ref_valida(t, valor):
            if t.kind == "pip" and valor != t.ref:  # install refuses it: the sha256 of the registry is the pinned version's alone
                return t.ref, "override-invalido", (f"{nome_var} pede uma versão que não é a fixada no registro: o sha256 do registro é só "
                                                    "o da versão fixada, então `install` recusa a outra (nenhum comando roda); "
                                                    "o doctor compara com o pin do registro")
            return valor, "override", None
        return t.ref, "override-invalido", (f"{nome_var} não é um commit (git) nem uma versão (npm, pip): `install` e `clone` recusam esse valor "
                                           "(nenhum comando roda); o doctor compara com o pin do registro")
    ref, fonte = tools.effective(t)
    return ref, fonte, None


# --- the command of each track, and the folder a git track lives in --------------------------------------------------------


def _clone_git(t: tools.Tool, ref: str) -> str:
    """A git track with no verb in the CLI (voicestudio: its app is installed by its own installer): the git commands tools.install runs.
    The `--` ends the options, as in tools.install: a relative folder that starts with `-` is a folder, not an option."""
    destino = _q(tools.checkout_dir(t))
    return f"git clone --filter=blob:none -- {t.source} {destino} && git -C {destino} checkout --detach {ref}"


def _clone_de(t: tools.Tool, ref: str) -> str:
    """The command that installs the track at `ref` (the pin in use): its verb (`clone_verb`), else the git commands, `npm install -g`
    for an npm track, and the first `media fetch` for the pip one (yt-dlp)."""
    if t.clone_verb:
        return f"simplicio-video {t.command} {t.clone_verb}"
    if t.kind == "git":
        return _clone_git(t, ref)
    if t.kind == "npm":
        return f"npm install -g {t.source}@{ref}"
    return YTDLP_INSTALA


def _pasta_do_checkout(t: tools.Tool) -> Path:
    if t.checkout_probe:  # a track with its own search order (openmontage: OPENMONTAGE_DIR, then the tools folder)
        return lookup(t.checkout_probe)()
    return tools.checkout_dir(t)


def _leitura_do_checkout(pasta: Path) -> tuple[Optional[str], str]:
    """(commit, why): the commit of the checkout at `pasta`, or None and the reason. Git walks up to a parent repository when the
    folder's own .git is not valid, so the top of the repository must be the folder itself, and HEAD must name a commit that exists."""
    try:
        topo = tools.git("rev-parse", "--show-toplevel", cwd=pasta, timeout=LIMITE_LOCAL_S)
    except tools.GitTimeout:
        return None, TEMPO_ESGOTADO
    except tools.ToolError:
        return None, "o git não lê a pasta como repositório"
    if Path(topo).resolve() != pasta.resolve():
        return None, "o .git dela não é válido: o git lê outro repositório em volta"
    try:
        tools.git("cat-file", "-e", "HEAD^{commit}", cwd=pasta, timeout=LIMITE_LOCAL_S)
    except tools.GitTimeout:
        return None, TEMPO_ESGOTADO
    except tools.ToolError:
        return None, "o HEAD não aponta para um commit que existe no repositório"
    try:
        return tools.git("rev-parse", "HEAD", cwd=pasta, timeout=LIMITE_LOCAL_S), ""
    except tools.GitTimeout:
        return None, TEMPO_ESGOTADO
    except tools.ToolError:
        return None, "o HEAD não se lê"


def _checkout(t: tools.Tool, pasta: Path, clone: str) -> tuple[str, Optional[str], list]:
    """(state, commit, rows) of a git track at `pasta`: 'ausente' (not there), 'quebrada' (there, but not a checkout) or 'ok'."""
    if pasta.is_symlink() and not pasta.exists():
        return "quebrada", None, [_row("instalada", "fail", f"{pasta} é um link que não aponta para nada",
                                       f"apague o link {_q(pasta)} e rode `{clone}`", {"path": str(pasta)})]
    if not pasta.exists():
        return "ausente", None, [_row("instalada", "warn", "não instalada", clone, {"path": str(pasta)})]
    if not pasta.is_dir():
        return "quebrada", None, [_row("instalada", "fail", f"{pasta} é um arquivo, não uma pasta de checkout",
                                       f"apague {_q(pasta)} e rode `{clone}`")]
    try:
        vazia = not any(pasta.iterdir())
    except OSError as exc:
        return "quebrada", None, [_row("instalada", "fail", f"não consigo ler {pasta}: {exc.strerror or exc}",
                                       f"ajuste as permissões de {pasta} e rode o doctor de novo")]
    if vazia:  # an empty folder is what a clone that never started leaves: not installed
        return "ausente", None, [_row("instalada", "warn", "não instalada", clone, {"path": str(pasta)})]
    faltam = [nome for nome, existe in ((".git", (pasta / ".git").exists()), (t.marker, (pasta / t.marker).exists())) if not existe]
    if faltam:
        return "quebrada", None, [_row("instalada", "fail", f"{pasta} não é um checkout íntegro (falta {', '.join(faltam)}): "
                                       "sobra de um clone interrompido?", f"apague {_q(pasta)} e rode `{clone}`", {"path": str(pasta)})]
    if _ache("git") is None:
        return "ok", None, [_row("instalada", "warn", f"{pasta} existe, mas sem o git não consigo conferir o commit",
                                 "instale o git (https://git-scm.com/downloads)", {"path": str(pasta)})]
    head, motivo = _leitura_do_checkout(pasta)
    if head is None and motivo == TEMPO_ESGOTADO:  # a hang says nothing about the folder: no advice to delete it
        return "ok", None, [_row("instalada", "warn", f"{pasta} existe, mas não consegui verificar o commit: tempo esgotado "
                                 f"({LIMITE_LOCAL_S:g} s) esperando o git", "rode `simplicio-video doctor trilhas` de novo",
                                 {"path": str(pasta)})]
    if head is None:
        return "quebrada", None, [_row("instalada", "fail", f"{pasta} não é um checkout íntegro ({motivo})",
                                       f"apague {_q(pasta)} e rode `{clone}`", {"path": str(pasta)})]
    return "ok", head, [_row("instalada", "ok", f"instalada em {pasta} (commit {head[:12]})", None,
                             {"path": str(pasta), "head": head})]


def _mesmo_commit(head: str, ref: str) -> bool:
    return head == ref or (len(ref) >= 7 and head.startswith(ref))


def _pin_git(head: str, ref: str, fonte: str, clone: str) -> tuple[bool, list]:
    if _mesmo_commit(head, ref):
        return True, [_row("pin", "ok", f"commit em uso {ref[:12]} ({fonte}) confere com o checkout", None,
                            {"ref": ref, "source": fonte})]
    fix = "simplicio-video update" if fonte == "lock" else clone
    return False, [_row("pin", "warn", f"o checkout está em {head[:12]}; o commit em uso é {ref[:12]} ({fonte})", fix,
                        {"ref": ref, "source": fonte, "head": head})]


def _sha256(arquivo: Path) -> Optional[str]:
    if arquivo.is_symlink() or not arquivo.is_file() or arquivo.stat().st_size > MAX_ARQUIVO_FIXADO:
        return None
    return sha256_file(arquivo)


def _integridade(pasta: Path, tabela: dict) -> list:
    """The pinned files of a track (its scripts, read as bytes) against the sha256 of the commit that is in use. The fix restores
    those files from that commit: a second clone at the same commit would not undo an edit of the working tree."""
    problemas, rels = [], []
    for rel, digest in sorted(tabela.items()):
        alvo = pasta / rel
        if alvo.is_symlink():
            problemas.append(f"{rel} é um link")
        elif not alvo.is_file():
            problemas.append(f"{rel} ausente")
        elif _sha256(alvo) != digest:
            problemas.append(f"{rel} diferente do fixado")
        else:
            continue
        rels.append(rel)
    if problemas:
        return [_row("integridade", "fail", "arquivos fixados não conferem: " + "; ".join(problemas),
                     f"git -C {_q(pasta)} checkout -- {' '.join(_q(r) for r in rels)}", {"problemas": problemas})]
    return [_row("integridade", "ok", f"{len(tabela)} arquivo(s) fixados conferem (sha256)", None, {"arquivos": len(tabela)})]


def _venv_row(programa: Path, fix: str) -> dict:
    """The venv of a track: `programa` is the program that must be in it (its python, or the track's own command)."""
    venv = programa.parent.parent
    if programa.is_file():
        return _row("setup:venv", "ok", f"venv pronto em {venv}", None, {"venv": str(venv)})
    if venv.is_dir():
        return _row("setup:venv", "fail", f"venv incompleto em {venv}: falta {programa.name}", fix, {"venv": str(venv)})
    return _row("setup:venv", "warn", f"venv ausente ({venv}); o setup cria", fix, {"venv": str(venv)})


def _setup(t: tools.Tool, pasta: Path) -> list:
    """The track's own setup, judged only once the track is installed (what the setup of a missing track would make is not a gap). The
    registry names the function that judges it (`Tool.setup_probe`); a track with none has no setup of its own to judge."""
    if t.setup_probe is None:
        return []
    return lookup(t.setup_probe)(t, pasta)


# The setup probes of each track, called as `probe(tool, checkout)` by name from `Tool.setup_probe` (tools.py).


def setup_openmontage(t: tools.Tool, pasta: Path) -> list:
    from . import montage
    return [_venv_row(montage.venv_python(), "simplicio-video montage setup")]


def setup_moneyprinter(t: tools.Tool, pasta: Path) -> list:
    from . import moneyprinter
    config = pasta / "config.toml"
    return [_venv_row(moneyprinter.venv_python(), "simplicio-video moneyprinter setup"),
            _row("setup:config.toml", "ok" if config.is_file() else "warn",
                 "config.toml pronto" if config.is_file() else "config.toml ausente (o setup copia o exemplo, sem chave)",
                 None if config.is_file() else "simplicio-video moneyprinter setup", {"path": str(config)})]


def setup_matchcut(t: tools.Tool, pasta: Path) -> list:
    from . import matchcut
    return [_venv_row(matchcut.venv_python(), "simplicio-video matchcut setup")]


def setup_rea_video(t: tools.Tool, pasta: Path) -> list:
    from . import rea_video
    return [_venv_row(rea_video.venv_bin("rea-video"), "simplicio-video rea-video setup")]


def setup_video_to_skill(t: tools.Tool, pasta: Path) -> list:
    return [_binary_row()]


def setup_opencut(t: tools.Tool, pasta: Path) -> list:
    from . import opencut
    env = pasta / opencut.ENV_FILE
    if env.is_file() and env.stat().st_size == 0:
        env_row = _row("setup:.env.local", "warn", f"{env} está vazio: o app não sobe sem as variáveis",
                       f"apague {_q(env)} e rode `simplicio-video opencut dev`", {"path": str(env)})
    elif env.is_file():
        env_row = _row("setup:.env.local", "ok", "apps/web/.env.local pronto", None, {"path": str(env)})
    else:
        env_row = _row("setup:.env.local", "warn", "apps/web/.env.local ausente: o `opencut dev` cria na primeira vez",
                       "simplicio-video opencut dev", {"path": str(env)})
    return [_pasta_row("setup:node_modules", pasta / "node_modules", f"cd {_q(pasta)} && bun install",
                       "node_modules ausente: as dependências do editor não foram instaladas"), env_row]


def setup_toonflow(t: tools.Tool, pasta: Path) -> list:
    from . import toonflow
    faltam = [str(rel) for rel in (toonflow.SERVER_ENTRY, toonflow.STDIO_ENTRY) if not (pasta / rel).is_file()]
    build = (_row("setup:build", "warn", f"build ausente ({', '.join(faltam)})", f"cd {_q(pasta)} && bun run build:server")
             if faltam else _row("setup:build", "ok", "build do servidor e do MCP prontos"))
    return [_pasta_row("setup:node_modules", pasta / "node_modules", f"cd {_q(pasta)} && bun install --frozen-lockfile",
                       "node_modules ausente: as dependências do Toonflow não foram instaladas"), build]


def _binary_row() -> dict:
    """The extractor of video-to-skill, judged without running the engine's own probe: the managed one by the sha256 of the file against
    the pinned table (no process starts; a changed file is `fail`), else a `vts-extract` of the PATH by its `--version` (closed
    environment, like the other binaries here); else a gap with the exact command."""
    from . import video_to_skill as v2s
    fix = "simplicio-video video-to-skill setup"
    exe = v2s.managed_binary()
    if exe.is_file() or exe.is_symlink():
        if v2s.managed_verified(exe):
            return _row("setup:binary", "ok", f"vts-extract {v2s.VERSION} gerenciado, sha256 conferido ({exe})", None,
                        {"source": "managed", "path": str(exe), "version": v2s.VERSION})
        return _row("setup:binary", "fail", f"{exe} não confere com o sha256 fixado (alterado, link ou outra plataforma): o motor não o usa",
                    fix, {"source": "managed", "path": str(exe)})
    achado = _ache("vts-extract")
    if achado is not None:
        funciona, versao = _roda_versao(achado)
        if funciona and versao == v2s.VERSION:
            return _row("setup:binary", "ok", f"vts-extract {v2s.VERSION} no PATH ({achado}); só a versão foi conferida, não o sha256", None,
                        {"source": "path", "path": achado, "version": versao})
        return _row("setup:binary", "warn", f"o vts-extract do PATH ({achado}) não diz {v2s.VERSION}: o motor não o usa", fix,
                    {"source": "path", "path": achado, "version": versao})
    if v2s.host_asset() is None:
        return _row("setup:binary", "warn", "sem binário pré-compilado para esta plataforma: compile o vts-extract do upstream e ponha no PATH",
                    None, {"supported": False})
    return _row("setup:binary", "warn", f"vts-extract {v2s.VERSION} ausente; o setup baixa e confere por sha256", fix, {"path": str(exe)})


def _pasta_row(nome: str, caminho: Path, fix: str, ausente: str) -> dict:
    if caminho.is_dir():
        return _row(nome, "ok", f"{caminho.name} pronto", None, {"path": str(caminho)})
    return _row(nome, "warn", ausente, fix, {"path": str(caminho)})


# --- the binaries of the npm tracks and the venv of the pip one -------------------------------------------------------------


def _roda_versao(exe: str) -> tuple[bool, Optional[str]]:
    """(runs, version) of `exe --version`, with the closed environment of `status`. A binary that does not run is a broken install.
    Its output is read in part (4 KB) and cleaned: it is text from a program we did not write."""
    try:
        r = hostos.run_limitado([exe, "--version"], timeout=LIMITE_LOCAL_S, env=_ambiente())
    except (OSError, subprocess.SubprocessError):
        return False, None
    if r.returncode != 0:
        return False, None
    texto = ((r.stdout or r.stderr or "")[:4096]).strip()
    achado = _VERSAO.search(texto)
    versao = achado.group(0) if achado else (texto.splitlines()[0] if texto else "")
    return True, (_limpa(versao, 60) or None)


def _npm(t: tools.Tool, ref: str, fonte: str) -> tuple[bool, Optional[str], list]:
    """(installed, version, rows) of an npm track: its binary on PATH, else npx at the pin (hypit, with Node 22.15 or newer)."""
    clone = _clone_de(t, ref)
    exe = _ache(t.name)
    if exe is None:
        if t.name in tools.NPX_TRACKS and _npx_pronto():
            return True, None, [_row("instalada", "ok", "instalada via npx no pin em uso (sem binário no PATH)", None,
                                     {"source": "npx"})]
        return False, None, [_row("instalada", "warn", "não instalada", clone)]
    funciona, versao = _roda_versao(exe)
    if not funciona:
        return False, None, [_row("instalada", "fail", f"{exe} não roda (`--version` falhou)", clone, {"path": exe})]
    if versao is None:
        return True, None, [_row("instalada", "warn", f"{exe} roda, mas não consigo ler a versão", clone, {"path": exe})]
    return True, versao, [_row("instalada", "ok", f"instalada: {exe}, versão {versao}", None, {"path": exe, "version": versao})]


def _pin_versao(versao: Optional[str], ref: str, fonte: str, fix: str) -> tuple[Optional[bool], list]:
    if versao is None:
        return None, []
    if versao == ref:
        return True, [_row("pin", "ok", f"versão em uso {ref} ({fonte}) confere com a instalada", None, {"ref": ref, "source": fonte})]
    return False, [_row("pin", "warn", f"a versão instalada é {versao}; a em uso é {ref} ({fonte})", fix,
                        {"ref": ref, "source": fonte, "version": versao})]


def _pip(t: tools.Tool, ref: str, fonte: str) -> tuple[bool, Optional[str], Optional[bool], list]:
    """(installed, version, pin_match, rows) of the pip track: the yt-dlp program in its own venv, the version from the dist-info."""
    pasta = tools.checkout_dir(t)
    venv = pasta / "venv"
    exe = tools.pip_binary(t.name)
    if exe is None:
        if venv.is_dir():
            return False, None, None, [_row("instalada", "fail", f"o venv de {t.name} não tem o programa (a instalação parou no meio)",
                                            f"apague {_q(venv)}; {YTDLP_INSTALA}", {"venv": str(venv)})]
        return False, None, None, [_row("instalada", "warn", "não instalada", YTDLP_INSTALA, {"venv": str(venv)})]
    versao = tools.pip_version(t.name)
    fix = f"apague {_q(venv)}; {YTDLP_INSTALA}"
    if versao is None:
        return True, None, None, [_row("instalada", "fail", f"o venv de {t.name} não tem a versão instalada (dist-info)", fix,
                                       {"venv": str(venv)})]
    match, linhas = _pin_versao(versao, ref, fonte, fix)
    return True, versao, match, [_row("instalada", "ok", f"instalada no venv, versão {versao}", None,
                                      {"venv": str(venv), "version": versao})] + linhas


# --- system dependencies ----------------------------------------------------------------------------------------------------


def _hint_bun() -> str:
    if hostos.system() == "win32":
        return "instale o bun pelo instalador oficial do Windows (https://bun.sh)"
    return "instale o bun: curl -fsSL https://bun.sh/install | bash (https://bun.sh)"


def _dep_row(nome: str, presente: bool, obrigatoria: bool, fix: str, resumo: str) -> dict:
    if presente:
        return _row(f"dep:{nome}", "ok", f"{nome} encontrado: {resumo}" if resumo else f"{nome} encontrado")
    if obrigatoria:
        return _row(f"dep:{nome}", "warn", f"{nome} ausente", fix)
    return _row(f"dep:{nome}", "ok", f"{nome} ausente (opcional para esta trilha)", None)


def _dep_node(minimo: tuple) -> dict:
    """Node is required by every track that asks for it, at its own minimum (tinyfish 24, hypit 22.15)."""
    versao = _node_versao()
    if versao is not None and versao[:len(minimo)] >= minimo:
        return _row("dep:node", "ok", f"node {_versao_texto(versao)} (exige {_versao_texto(minimo)} ou superior)")
    atual = f"node {_versao_texto(versao)}" if versao else "node ausente"
    fix = f"instale o Node {_versao_texto(minimo)} ou superior (https://nodejs.org ou `nvm install {minimo[0]}`)"
    return _row("dep:node", "warn", f"{atual}: a trilha exige {_versao_texto(minimo)} ou superior", fix)


def _deps(t: tools.Tool) -> list:
    rows = []
    if t.kind == "git":
        rows.append(_dep_row("git", _ache("git") is not None, True, "instale o git (https://git-scm.com/downloads)", ""))
    itens = [tools.parse_dep(spec) for spec in t.deps]
    if t.name in tools.NPX_TRACKS and _ache(t.name) is None:  # without a binary, npx runs the pinned package
        itens.append(("npx", True, None))
    for nome, obrigatoria, minimo in itens:
        if nome not in DEP_NOMES:
            raise ValueError(f"{t.name}: não sei julgar a dependência {nome!r} (as que sei: {', '.join(DEP_NOMES)})")
        if nome == "node":
            rows.append(_dep_node(minimo))
        elif nome == "bun":
            rows.append(_dep_row("bun", _ache("bun") is not None, obrigatoria, _hint_bun(), ""))
        elif nome == "docker":
            rows.append(_dep_row("docker", _ache("docker") is not None, False,
                                 "instale o Docker (https://docs.docker.com/get-docker/); só `serve --docker` precisa", ""))
        elif nome == "ffmpeg":
            rows.append(_dep_row("ffmpeg", _ache("ffmpeg") is not None, obrigatoria,
                                 f"instale o ffmpeg com libass ({hostos.hint('ffmpeg')})", ""))
        elif nome == "npx":
            rows.append(_dep_row("npx", _ache("npx") is not None, obrigatoria,
                                 f"instale o Node {_versao_texto(NODE_HYPIT)} ou superior, que traz o npx", ""))
        elif nome == "npm":
            rows.append(_dep_row("npm", _ache("npm") is not None, obrigatoria,
                                 "instale o Node, que traz o npm (https://nodejs.org)", ""))
        elif nome == "SIMPLICIO_TTS_PY":
            rows.append(_tts_py_row(obrigatoria))
    return rows


def _tts_py_row(obrigatoria: bool) -> dict:
    """The python that video-use's setup.sh needs (numpy, Pillow, soundfile): SIMPLICIO_TTS_PY, else its default folder."""
    caminho = paths.tts_python()
    fix = ("defina SIMPLICIO_TTS_PY com um python que tenha numpy, Pillow e soundfile (e faster-whisper, para transcrever "
           "localmente), e rode `simplicio-video edit setup`")
    if Path(caminho).is_file():
        return _row("dep:SIMPLICIO_TTS_PY", "ok", f"python de apoio encontrado: {caminho}", None, {"path": caminho})
    if not obrigatoria:
        return _row("dep:SIMPLICIO_TTS_PY", "ok", "python de apoio ausente (opcional)", None, {"path": caminho})
    return _row("dep:SIMPLICIO_TTS_PY", "warn", f"python de apoio ausente: {caminho}", fix, {"path": caminho})


# --- upstream (--online) ----------------------------------------------------------------------------------------------------


def _fix_de_seguir(t: tools.Tool, latest: str) -> Optional[str]:
    """The command that moves a track to the upstream version it has. `simplicio-video update` does not do it from a checkout (it
    refuses there), so the way is the override of the pin for this one install. A pip track has its pin and sha256 in tools.py:
    no command moves it, so there is no fix to show."""
    if t.kind == "pip":
        return None
    return f"{tools.override_var(t)}={latest} {_clone_de(t, latest)}"


def _upstream(t: tools.Tool, ref: str, fonte: str, io) -> tuple[dict, list]:
    """The same resolution as `update --check` (tools_update.resolve), compared with the commit or version in use."""
    if tools_update.pin_only(t):
        return {"pin_only": True, "latest": None, "newer": None, "error": None}, [
            _row("upstream", "ok", ("pin: o binário (sha256 por plataforma) e o SKILL.md são fixados juntos e o upstream não é seguido"
                                    if t.name == "video_to_skill" else
                                    "pin: o setup.sh fixa o commit (VU_REF) e o upstream não é seguido"), None, {"pin_only": True})]
    if fonte == "override":
        return {"pin_only": False, "latest": None, "newer": None, "error": None}, [
            _row("upstream", "ok", f"fixada por {tools.override_var(t)}: o upstream não é seguido", None, {"override": True})]
    try:
        alvo = tools_update.resolve(t, io)
    except tools_update.FAILURES as exc:
        msg = _limpa(str(exc) or type(exc).__name__, 300)
        return {"pin_only": False, "latest": None, "newer": None, "error": msg}, [
            _row("upstream", "warn", f"não consegui consultar o upstream: {msg}", None)]
    latest = alvo["ref"]
    newer = not tools_update.same_ref(t, ref, latest)
    detalhe = {"latest": latest, "branch": alvo.get("branch"), "newer": newer}
    if newer:
        return {"pin_only": False, "latest": latest, "newer": True, "error": None}, [
            _row("upstream", "warn", f"o upstream está em {latest[:12]}; em uso {ref[:12]}", _fix_de_seguir(t, latest), detalhe)]
    return {"pin_only": False, "latest": latest, "newer": False, "error": None}, [
        _row("upstream", "ok", f"em dia com o upstream ({latest[:12]})", None, detalhe)]


# --- one track, and the document --------------------------------------------------------------------------------------------


def _resumo(installed: bool, detalhe: str, rows: list) -> str:
    quem = f"instalada ({detalhe})" if installed else "não instalada"
    pendencias = sum(1 for r in rows if r["status"] != "ok")
    return f"{quem}; {pendencias} pendência(s)" if pendencias else f"{quem}; em dia"


def _avalia(t: tools.Tool, online_jobs: Optional[list]) -> dict:
    ref, fonte, problema = _ref_em_uso(t)
    rows: list = []
    installed, version, pin_match, detalhe = False, None, None, ""
    if t.kind == "git":
        pasta = _pasta_do_checkout(t)
        clone = _clone_de(t, ref)
        estado, head, linhas = _checkout(t, pasta, clone)
        rows += linhas
        installed = estado == "ok"
        if head is not None:
            version, detalhe = head, f"commit {head[:12]}"
            pin_match, pin_rows = _pin_git(head, ref, fonte, clone)
            rows += pin_rows
            tabela = _tabela_fixada(t)
            if tabela is not None and pin_match:
                rows += _integridade(pasta, tabela)
            rows += _setup(t, pasta)
    elif t.kind == "npm":
        installed, version, linhas = _npm(t, ref, fonte)
        rows += linhas
        detalhe = f"versão {version}" if version else "via npx"
        if version is not None:
            pin_match, pin_rows = _pin_versao(version, ref, fonte, f"npm install -g {t.source}@{ref}")
            rows += pin_rows
        elif installed:
            rows.append(_row("pin", "ok", f"rodado por npx no pin {ref} ({fonte})", None, {"ref": ref, "source": fonte}))
            pin_match = True
    else:
        installed, version, pin_match, linhas = _pip(t, ref, fonte)
        rows += linhas
        detalhe = f"versão {version}" if version else ""
    if problema:  # the pin in use is the registry's: the one `pin` row says the override was refused, and no other `pin` row is shown
        rows = [_row("pin", "warn", problema, f"apague {tools.override_var(t)} ou defina um commit (git) ou uma versão (npm; pip só a fixada)")
                ] + [r for r in rows if r["name"] != "pin"]
    rows += _deps(t)
    track = {
        "name": t.name,
        "command": tools.command(t),
        "status": _pior(r["status"] for r in rows),
        "summary": _limpa(_resumo(installed, _limpa(detalhe, 80), rows)),
        "installed": installed,
        "version": _limpa(version, 60) if version else None,
        "pin": ref,
        "pin_source": fonte,
        "pin_registry": t.ref,
        "pin_match": pin_match,
        "upstream": None,
        "checks": rows,
    }
    if online_jobs is not None:  # the upstream is read after every track is checked, all the reads together (_fecha_upstreams)
        online_jobs.append((track, t, ref, fonte, installed, detalhe))
    return track


def _tabela_fixada(t: tools.Tool) -> Optional[dict]:
    """The sha256 table of the pinned files of a git track that has one (`Tool.integrity`; read at call time: the tests replace it).
    instagram has one too, but this module must not import it (the engine reaches that module only from cli and mcp):
    `simplicio-video instagram status` checks its scripts."""
    return lookup(t.integrity) if t.integrity else None


def _fecha_upstream(job: tuple, upstream: dict, linhas: list) -> None:
    """Adds the upstream answer to a track that was checked without it, and settles its status and summary."""
    track, _t, _ref, _fonte, installed, detalhe = job
    track["upstream"] = upstream
    track["checks"] = track["checks"] + linhas
    track["status"] = _pior(r["status"] for r in track["checks"])
    track["summary"] = _limpa(_resumo(installed, _limpa(detalhe, 80), track["checks"]))


def _em_paralelo(trabalhos: dict, orcamento_s: float, nome: str = "upstream") -> dict:
    """Runs each callable in its own daemon thread and waits at most `orcamento_s` for all of them together. Returns
    {key: (True, value) | (False, exc)} for the ones that finished; the others are not in it. Daemon threads on purpose: a read
    that never answers must not keep the process alive at exit (a ThreadPoolExecutor would wait for it)."""
    resultados: dict = {}
    trava = threading.Lock()

    def roda(chave, fn):
        try:
            resultado = (True, fn())
        except Exception as exc:  # noqa: BLE001 - it becomes that track's failure, in its row
            resultado = (False, exc)
        with trava:
            resultados[chave] = resultado

    fim = time.monotonic() + max(0.0, orcamento_s)
    fios = []
    for chave, fn in trabalhos.items():
        fio = threading.Thread(target=roda, args=(chave, fn), name=f"doctor-{nome}-{chave}", daemon=True)
        fio.start()
        fios.append(fio)
    for fio in fios:
        fio.join(max(0.0, fim - time.monotonic()))
    with trava:
        return dict(resultados)


def _upstream_com_prazo(fim: float, t: tools.Tool, ref: str, fonte: str, io) -> tuple[dict, list]:
    with tools_update.prazo_de_leitura(fim):
        return _upstream(t, ref, fonte, io)


def _fecha_upstreams(jobs: list, io, orcamento_s: float, total_s: Optional[float] = None) -> None:
    """Reads the upstream of every track together, inside one budget. A track that did not answer in time says so."""
    fim_das_leituras = time.monotonic() + max(0.0, orcamento_s) * 0.8  # the reads end (and kill their groups) before the budget does
    trabalhos = {i: functools.partial(_upstream_com_prazo, fim_das_leituras, t, ref, fonte, io)
                 for i, (_track, t, ref, fonte, _inst, _det) in enumerate(jobs)}
    resultados = _em_paralelo(trabalhos, orcamento_s)
    for i, job in enumerate(jobs):
        if i not in resultados:
            upstream = {"pin_only": False, "latest": None, "newer": None, "error": "tempo esgotado"}
            linhas = [_row("upstream", "warn", f"tempo esgotado: o upstream não respondeu em {(total_s if total_s is not None else orcamento_s):g} s no total", None)]
        else:
            ok, valor = resultados[i]
            if ok:
                upstream, linhas = valor
            else:
                msg = _limpa(str(valor) or type(valor).__name__, 300)
                upstream = {"pin_only": False, "latest": None, "newer": None, "error": msg}
                linhas = [_row("upstream", "warn", f"não consegui consultar o upstream: {msg}", None)]
        _fecha_upstream(job, upstream, linhas)


def _avalia_seguro(t: tools.Tool, online_jobs: Optional[list]) -> dict:
    """_avalia, but an error of one track becomes a warning row that names it: the doctor never ends with a traceback."""
    try:
        return _avalia(t, online_jobs)
    except Exception as exc:  # noqa: BLE001 - reported in the row, never hidden
        motivo = _limpa(f"{type(exc).__name__}: {exc}", 300)
        fix = ("defina HOME ou SIMPLICIO_TOOLS_DIR e rode `simplicio-video doctor trilhas` de novo" if isinstance(exc, RuntimeError)
               else "simplicio-video doctor trilhas")
        return _trilha_com_aviso(t, motivo, fix)


def _trilha_com_aviso(t: tools.Tool, motivo: str, fix: str) -> dict:
    """A track that could not be checked: one warning row that names why (an error, or the budget that ran out)."""
    linha = _row("instalada", "warn", f"não consegui checar esta trilha ({motivo})", fix)
    return {"name": t.name, "command": tools.command(t), "status": "warn",
            "summary": _limpa(f"não consegui checar ({motivo})"), "installed": False, "version": None, "pin": t.ref,
            "pin_source": "pin", "pin_registry": t.ref, "pin_match": None, "upstream": None, "checks": [linha]}


def _avalia_todas(online: bool, orcamento_s: float) -> tuple[list, list]:
    """(tracks, upstream jobs): every track checked together, each in its own thread, inside `orcamento_s` in total. The local probes
    (git rev-parse, `<exe> --version`) of the tracks do not add up one after the other: a hung program costs one LIMITE_LOCAL_S for
    everybody. A track that did not finish says so in its row."""
    listas = {t.name: ([] if online else None) for t in tools.TOOLS.values()}
    trabalhos = {t.name: functools.partial(_avalia_seguro, t, listas[t.name]) for t in tools.TOOLS.values()}
    resultados = _em_paralelo(trabalhos, orcamento_s, "local")
    tracks: list = []
    jobs: list = []
    for t in tools.TOOLS.values():
        if t.name in resultados and resultados[t.name][0]:
            tracks.append(resultados[t.name][1])
            jobs += listas[t.name] or []
        else:
            tracks.append(_trilha_com_aviso(t, f"tempo esgotado: as checagens locais passaram de {orcamento_s:g} s no total",
                                            "simplicio-video doctor trilhas"))
    return tracks, jobs


def collect(*, online: bool = False, io: Optional[Any] = None, orcamento_s: float = ORCAMENTO_ONLINE_S) -> dict:
    """The document of `doctor trilhas`. Offline (the default) reads only the disk, the PATH and the lock. `io` is the network
    of the upstream (tools_update.Io); with --online and none given, the real one (SIMPLICIO_OFFLINE=1 blocks it). With --online,
    the upstream of all the tracks is read together, inside `orcamento_s` in total (the tests shorten it)."""
    if online and io is None:
        io = tools_update.live_io()
    _MEMO.clear()
    fim = time.monotonic() + max(0.0, orcamento_s)
    tracks, jobs = _avalia_todas(online, orcamento_s)
    if online:  # the upstream reads get what the local probes left of the same budget
        _fecha_upstreams(jobs, io, max(0.0, fim - time.monotonic()), orcamento_s)
    return {"schema": SCHEMA, "status": _pior(t["status"] for t in tracks), "online": bool(online), "tracks": tracks}


def linha_do_doctor(doc: dict) -> dict:
    """The one row `trilhas` of `doctor all`: the count, the worst status, and the command that shows every fix."""
    tracks = doc["tracks"]
    em_dia = sum(1 for t in tracks if t["status"] == "ok")
    lacuna = sum(1 for t in tracks if t["status"] == "warn")
    quebrada = sum(1 for t in tracks if t["status"] == "fail")
    resumo = f"{em_dia} de {len(tracks)} trilhas em dia"
    if lacuna:
        resumo += f"; {lacuna} com lacuna"
    if quebrada:
        resumo += f"; {quebrada} com instalação quebrada"
    fix = None if doc["status"] == "ok" else "simplicio-video doctor trilhas"
    return _row("trilhas", doc["status"], resumo, fix, {"tracks": tracks})


def texto(doc: dict) -> str:
    linhas = [f"simplicio-video doctor trilhas: {doc['status']}"]
    for t in doc["tracks"]:
        linhas.append(f"  {t['status']:<5} {t['name']:<12} {t['command']:<28} {t['summary']}")
        for c in t["checks"]:
            if c["status"] != "ok":
                linhas.append(f"        {c['status']:<5} {c['name']:<16} {c['summary']}")
                if c["fix"]:
                    linhas.append(f"              fix: {c['fix']}")
    if not doc["online"]:
        linhas.append("upstream não consultado: rode `simplicio-video doctor trilhas --online` para comparar com o upstream")
    return "\n".join(linhas)
