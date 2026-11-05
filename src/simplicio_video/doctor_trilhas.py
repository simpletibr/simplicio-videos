"""`simplicio-video doctor trilhas [--json] [--online]` and the row `trilhas` of `doctor all`: the state of the twelve external tracks.

For each track of tools.TOOLS (registry order), in `checks`, one row per thing that was looked at, each `ok`, `warn` or `fail`
with the exact command that fixes it (`fix`), like the doctor's other checks:

  instalada        the checkout (git), the binary (npm) or the venv program (pip) is there; `fail` for a broken install (a folder
                   that is not a checkout, a corrupt .git, a binary that does not run, a venv without its program)
  pin              the commit or version in use (registry pin, the lock's, or SIMPLICIO_<NAME>_REF) is the one installed
  integridade      git tracks with pinned files (instagram, matchcut): their sha256 at the pinned commit; `fail` if one changed
  setup:<item>     the track's own setup: venv, node_modules, build, config.toml, .env.local
  dep:<name>       system dependencies: git, bun, node (version), npx, npm, ffmpeg, docker (optional), SIMPLICIO_TTS_PY (video-use)
  upstream         only with --online: the same resolution as `update --check` (git ls-remote, npm view, PyPI); video-use is pin-only

Offline by default: nothing here reads the network, starts a shell or writes a file. The version of a binary is read by running
`--version` with the closed environment of `status` (no key of the shell reaches it). Status per track: the worst of its rows;
a track that is not installed is `warn` (it is optional: the doctor's other optional things warn too), never `fail`.

Output: `texto(doc)` for the terminal; `collect()` returns {"schema": "simplicio.doctor-trilhas/v1", "status", "online", "tracks"};
`linha_do_doctor(doc)` is the one aggregated row of `doctor all`.
"""
from __future__ import annotations

import hashlib
import os
import re
import subprocess
from pathlib import Path
from typing import Any, Optional

from . import hostos, tools, tools_update
from .status import ENV_FERRAMENTA

SCHEMA = "simplicio.doctor-trilhas/v1"
_RANK = {"ok": 0, "warn": 1, "fail": 2}
_VERSAO = re.compile(r"\d+\.\d+\.\d+")
MAX_ARQUIVO_FIXADO = 1024 * 1024  # the pinned files are a few KB; a bigger one is not the pinned one
NODE_TINYFISH = (24,)  # the @tiny-fish/cli package declares Node >= 24
NODE_HYPIT = tools.NODE_MIN  # (22, 15): @hypit/hypit "engines"
CLONE = {
    "openmontage": "simplicio-video montage clone",
    "opencut": "simplicio-video opencut clone",
    "toonflow": "simplicio-video toonflow clone",
    "moneyprinter": "simplicio-video moneyprinter clone",
    "matchcut": "simplicio-video matchcut clone",
    "instagram": "simplicio-video instagram clone",
    "rea_video": "simplicio-video rea-video clone",
    "video-use": "simplicio-video edit setup",
}
YTDLP_FETCH = "simplicio-video media fetch <URL> -o <arquivo.mp4> --autorizo"  # the first use installs the pinned yt-dlp
# (name, required, minimum version or None) for the tracks that need more than git; `hypit` adds npx when it has no binary
DEPS = {
    "openmontage": [("ffmpeg", True, None)],
    "opencut": [("bun", True, None), ("docker", False, None)],
    "hypit": [("node", True, NODE_HYPIT)],
    "toonflow": [("bun", True, None), ("docker", False, None)],
    "moneyprinter": [("ffmpeg", True, None)],
    "matchcut": [("ffmpeg", True, None)],
    "instagram": [],
    "rea_video": [("ffmpeg", True, None)],
    "voicestudio": [("bun", False, None)],
    "video-use": [("ffmpeg", True, None), ("SIMPLICIO_TTS_PY", True, None)],
    "tinyfish": [("node", True, NODE_TINYFISH), ("npm", True, None)],
    "yt-dlp": [("ffmpeg", False, None)],
}


def _row(name: str, status: str, summary: str, fix: Optional[str] = None, detail: Optional[dict] = None) -> dict:
    return {"name": name, "status": status, "summary": summary, "fix": fix, "detail": detail or {}}


def _ache(nome: str) -> Optional[str]:
    """A program on PATH, looked up as commands/doctor.py does (PATHEXT on Windows, the Homebrew folders on macOS)."""
    return hostos.find_tool(nome)


def _ambiente() -> dict:
    """The only variables a probe of a program gets (the closed environment of `status`: no key of the shell)."""
    return {k: os.environ[k] for k in ENV_FERRAMENTA if k in os.environ}


def _node_versao() -> Optional[tuple]:
    """(major, minor, patch) of the `node` on PATH, or None. The output is read with `replace`: a console code page is not UTF-8."""
    caminho = _ache("node")
    if caminho is None:
        return None
    try:
        r = subprocess.run([caminho, "--version"], stdin=subprocess.DEVNULL, capture_output=True, text=True, errors="replace",
                           timeout=15, env=_ambiente())
    except (OSError, subprocess.SubprocessError):
        return None
    achado = re.match(r"\s*v?(\d+)\.(\d+)\.(\d+)", r.stdout or "") if r.returncode == 0 else None
    return tuple(int(x) for x in achado.groups()) if achado else None


def _npx_pronto() -> bool:
    """npx on PATH and Node >= tools.NODE_MIN: an npm track runs through npx at its pin (checked, nothing downloaded)."""
    versao = _node_versao()
    return _ache("npx") is not None and versao is not None and versao[:2] >= tools.NODE_MIN


def _pior(estados) -> str:
    return max(estados, key=_RANK.__getitem__, default="ok")


def _versao_texto(versao: tuple) -> str:
    return ".".join(str(x) for x in versao)


# --- the command of each track, and the folder a git track lives in --------------------------------------------------


def _clone_de(t: tools.Tool) -> str:
    """The command that installs the track at its pin. voicestudio has none in the CLI (its app is installed by its own
    installer): the git commands that tools.install runs, at the commit in use."""
    if t.name in CLONE:
        return CLONE[t.name]
    if t.name == "voicestudio":
        destino = tools.checkout_dir(t)
        return f"git clone --filter=blob:none {t.source} {destino} && git -C {destino} checkout --detach {tools.effective_ref(t)}"
    if t.kind == "npm":
        return f"npm install -g {t.source}@{tools.effective_ref(t)}"
    return YTDLP_FETCH


def _pasta_do_checkout(t: tools.Tool) -> Path:
    if t.name == "openmontage":  # montage has its own search order (OPENMONTAGE_DIR, then the tools folder)
        from . import montage
        return montage.default_openmontage_dir()
    return tools.checkout_dir(t)


def _head(pasta: Path) -> Optional[str]:
    try:
        return tools._git("rev-parse", "HEAD", cwd=pasta)
    except tools.ToolError:
        return None


def _checkout(t: tools.Tool, pasta: Path, clone: str) -> tuple[str, Optional[str], list]:
    """(state, commit, rows) of a git track at `pasta`: 'ausente' (not there), 'quebrada' (there, but not a checkout) or 'ok'."""
    if not pasta.exists():
        return "ausente", None, [_row("instalada", "warn", "não instalada", clone, {"path": str(pasta)})]
    if not pasta.is_dir():
        return "quebrada", None, [_row("instalada", "fail", f"{pasta} é um arquivo, não uma pasta de checkout",
                                       f"apague {pasta} e rode `{clone}`")]
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
                                       "sobra de um clone interrompido?", f"apague {pasta} e rode `{clone}`", {"path": str(pasta)})]
    head = _head(pasta)
    if head is None:
        if _ache("git") is None:
            return "ok", None, [_row("instalada", "warn", f"{pasta} existe, mas sem o git não consigo ler o commit",
                                     "instale o git (https://git-scm.com/downloads)", {"path": str(pasta)})]
        return "quebrada", None, [_row("instalada", "fail", f"o git não lê o repositório em {pasta}",
                                       f"apague {pasta} e rode `{clone}`", {"path": str(pasta)})]
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
    return hashlib.sha256(arquivo.read_bytes()).hexdigest()


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
                     f"git -C {pasta} checkout -- {' '.join(rels)}", {"problemas": problemas})]
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
    """The track's own setup, judged only once the track is installed (what the setup of a missing track would make is not a gap)."""
    nome = t.name
    if nome == "openmontage":
        from . import montage
        return [_venv_row(montage.venv_python(), "simplicio-video montage setup")]
    if nome == "moneyprinter":
        from . import moneyprinter
        config = pasta / "config.toml"
        return [_venv_row(moneyprinter.venv_python(), "simplicio-video moneyprinter setup"),
                _row("setup:config.toml", "ok" if config.is_file() else "warn",
                     "config.toml pronto" if config.is_file() else "config.toml ausente (o setup copia o exemplo, sem chave)",
                     None if config.is_file() else "simplicio-video moneyprinter setup", {"path": str(config)})]
    if nome == "matchcut":
        from . import matchcut
        return [_venv_row(matchcut.venv_python(), "simplicio-video matchcut setup")]
    if nome == "rea_video":
        from . import rea_video
        return [_venv_row(rea_video.venv_bin("rea-video"), "simplicio-video rea-video setup")]
    if nome == "opencut":
        from . import opencut
        env = pasta / opencut.ENV_FILE
        if env.is_file() and env.stat().st_size == 0:
            env_row = _row("setup:.env.local", "warn", f"{env} está vazio: o app não sobe sem as variáveis",
                           f"apague {env} e rode `simplicio-video opencut dev`", {"path": str(env)})
        elif env.is_file():
            env_row = _row("setup:.env.local", "ok", "apps/web/.env.local pronto", None, {"path": str(env)})
        else:
            env_row = _row("setup:.env.local", "warn", "apps/web/.env.local ausente: o `opencut dev` cria na primeira vez",
                           "simplicio-video opencut dev", {"path": str(env)})
        return [_pasta_row("setup:node_modules", pasta / "node_modules", f"cd {pasta} && bun install",
                           "node_modules ausente: as dependências do editor não foram instaladas"), env_row]
    if nome == "toonflow":
        from . import toonflow
        faltam = [str(rel) for rel in (toonflow.SERVER_ENTRY, toonflow.STDIO_ENTRY) if not (pasta / rel).is_file()]
        build = (_row("setup:build", "warn", f"build ausente ({', '.join(faltam)})", f"cd {pasta} && bun run build:server")
                 if faltam else _row("setup:build", "ok", "build do servidor e do MCP prontos"))
        return [_pasta_row("setup:node_modules", pasta / "node_modules", f"cd {pasta} && bun install --frozen-lockfile",
                           "node_modules ausente: as dependências do Toonflow não foram instaladas"), build]
    return []


def _pasta_row(nome: str, caminho: Path, fix: str, ausente: str) -> dict:
    if caminho.is_dir():
        return _row(nome, "ok", f"{caminho.name} pronto", None, {"path": str(caminho)})
    return _row(nome, "warn", ausente, fix, {"path": str(caminho)})


# --- the binaries of the npm tracks and the venv of the pip one -------------------------------------------------------


def _roda_versao(exe: str) -> tuple[bool, Optional[str]]:
    """(runs, version) of `exe --version`, with the closed environment of `status`. A binary that does not run is a broken install."""
    try:
        r = subprocess.run([exe, "--version"], stdin=subprocess.DEVNULL, capture_output=True, text=True, errors="replace",
                           timeout=15, env=_ambiente())
    except (OSError, subprocess.SubprocessError):
        return False, None
    if r.returncode != 0:
        return False, None
    texto = (r.stdout or r.stderr or "").strip()
    achado = _VERSAO.search(texto)
    return True, (achado.group(0) if achado else (texto.splitlines()[0] if texto else None))


def _npm(t: tools.Tool, ref: str, fonte: str) -> tuple[bool, Optional[str], list]:
    """(installed, version, rows) of an npm track: its binary on PATH, else npx at the pin (hypit, with Node 22.15 or newer)."""
    clone = _clone_de(t)
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
                                            f"apague {venv} e rode `{YTDLP_FETCH}`", {"venv": str(venv)})]
        return False, None, None, [_row("instalada", "warn", "não instalada", YTDLP_FETCH, {"venv": str(venv)})]
    versao = tools.pip_version(t.name)
    fix = f"apague {venv} e rode `{YTDLP_FETCH}`"
    if versao is None:
        return True, None, None, [_row("instalada", "fail", f"o venv de {t.name} não tem a versão instalada (dist-info)", fix,
                                       {"venv": str(venv)})]
    match, linhas = _pin_versao(versao, ref, fonte, fix)
    return True, versao, match, [_row("instalada", "ok", f"instalada no venv, versão {versao}", None,
                                      {"venv": str(venv), "version": versao})] + linhas


# --- system dependencies ----------------------------------------------------------------------------------------------


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
    itens = list(DEPS.get(t.name, []))
    if t.name == "hypit" and _ache("hypit") is None:  # without a binary, npx runs the pinned package
        itens.append(("npx", True, None))
    for nome, obrigatoria, minimo in itens:
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
    caminho = os.environ.get("SIMPLICIO_TTS_PY")
    if not caminho:
        try:
            caminho = str(hostos.home_dir() / ".local" / "share" / "simplicio-tts" / "cbvenv" / "bin" / "python")
        except RuntimeError:  # no HOME: the default folder is unknown, so the variable is the only way out
            caminho = None
    fix = ("defina SIMPLICIO_TTS_PY com um python que tenha numpy, Pillow e soundfile (e faster-whisper, para transcrever "
           "localmente), e rode `simplicio-video edit setup`")
    if caminho and Path(caminho).is_file():
        return _row("dep:SIMPLICIO_TTS_PY", "ok", f"python de apoio encontrado: {caminho}", None, {"path": caminho})
    if not obrigatoria:
        return _row("dep:SIMPLICIO_TTS_PY", "ok", "python de apoio ausente (opcional)", None, {"path": caminho})
    onde = caminho or "sem HOME para achar a pasta padrão"
    return _row("dep:SIMPLICIO_TTS_PY", "warn", f"python de apoio ausente: {onde}", fix, {"path": caminho})


# --- upstream (--online) ----------------------------------------------------------------------------------------------


def _fix_de_seguir(t: tools.Tool, latest: str) -> Optional[str]:
    """The command that moves a track to the upstream version it has. `simplicio-video update` does not do it from a checkout (it
    refuses there), so the way is the override of the pin for this one install. A pip track has its pin and sha256 in tools.py:
    no command moves it, so there is no fix to show."""
    if t.kind == "pip":
        return None
    if t.name == "voicestudio":
        destino = tools.checkout_dir(t)
        instala = f"git clone --filter=blob:none {t.source} {destino} && git -C {destino} checkout --detach {latest}"
    elif t.kind == "npm":
        instala = f"npm install -g {t.source}@{latest}"
    else:
        instala = CLONE.get(t.name, "")
    return f"SIMPLICIO_{t.name.upper()}_REF={latest} {instala}" if instala else None


def _upstream(t: tools.Tool, ref: str, fonte: str, io) -> tuple[dict, list]:
    """The same resolution as `update --check` (tools_update.resolve), compared with the commit or version in use."""
    if tools_update.pin_only(t):
        return {"pin_only": True, "latest": None, "newer": None, "error": None}, [
            _row("upstream", "ok", "pin: o setup.sh fixa o commit (VU_REF) e o upstream não é seguido", None, {"pin_only": True})]
    if fonte == "override":
        return {"pin_only": False, "latest": None, "newer": None, "error": None}, [
            _row("upstream", "ok", f"fixada por SIMPLICIO_{t.name.upper()}_REF: o upstream não é seguido", None, {"override": True})]
    try:
        alvo = tools_update.resolve(t, io)
    except tools_update.FAILURES as exc:
        msg = (str(exc) or type(exc).__name__)[:300]
        return {"pin_only": False, "latest": None, "newer": None, "error": msg}, [
            _row("upstream", "warn", f"não consegui consultar o upstream: {msg}", None)]
    latest = alvo["ref"]
    newer = not tools_update._same_ref(t, ref, latest)
    detalhe = {"latest": latest, "branch": alvo.get("branch"), "newer": newer}
    if newer:
        return {"pin_only": False, "latest": latest, "newer": True, "error": None}, [
            _row("upstream", "warn", f"o upstream está em {latest[:12]}; em uso {ref[:12]}", _fix_de_seguir(t, latest), detalhe)]
    return {"pin_only": False, "latest": latest, "newer": False, "error": None}, [
        _row("upstream", "ok", f"em dia com o upstream ({latest[:12]})", None, detalhe)]


# --- one track, and the document ---------------------------------------------------------------------------------------


def _resumo(installed: bool, detalhe: str, rows: list) -> str:
    quem = f"instalada ({detalhe})" if installed else "não instalada"
    pendencias = sum(1 for r in rows if r["status"] != "ok")
    return f"{quem}; {pendencias} pendência(s)" if pendencias else f"{quem}; em dia"


def _avalia(t: tools.Tool, io) -> dict:
    ref, fonte = tools.effective(t)
    rows: list = []
    installed, version, pin_match, detalhe = False, None, None, ""
    if t.kind == "git":
        pasta = _pasta_do_checkout(t)
        clone = _clone_de(t)
        estado, head, linhas = _checkout(t, pasta, clone)
        rows += linhas
        installed = estado == "ok"
        if head is not None:
            version, detalhe = head, f"commit {head[:12]}"
            pin_match, pin_rows = _pin_git(head, ref, fonte, clone)
            rows += pin_rows
            tabela = _tabela_fixada(t.name)
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
    rows += _deps(t)
    upstream = None
    if io is not None:
        upstream, linhas = _upstream(t, ref, fonte, io)
        rows += linhas
    return {
        "name": t.name,
        "command": f"simplicio-video {tools.COMMANDS.get(t.name, t.name)}",
        "status": _pior(r["status"] for r in rows),
        "summary": _resumo(installed, detalhe, rows),
        "installed": installed,
        "version": version,
        "pin": ref,
        "pin_source": fonte,
        "pin_registry": t.ref,
        "pin_match": pin_match,
        "upstream": upstream,
        "checks": rows,
    }


def _tabela_fixada(nome: str) -> Optional[dict]:
    """The sha256 table of the pinned files of a git track that has one (read at call time: the tests replace it).
    instagram has one too, but this module must not import it (the engine reaches that module only from cli and mcp):
    `simplicio-video instagram status` checks its scripts."""
    if nome == "matchcut":
        from . import matchcut
        return matchcut.PINNED_SHA256
    return None


def _avalia_seguro(t: tools.Tool, io) -> dict:
    """_avalia, but an error of one track becomes a warning row that names it: the doctor never ends with a traceback."""
    try:
        return _avalia(t, io)
    except Exception as exc:  # noqa: BLE001 - reported in the row, never hidden
        motivo = f"{type(exc).__name__}: {str(exc)[:200]}"
        linha = _row("instalada", "warn", f"não consegui checar esta trilha ({motivo})", "simplicio-video doctor trilhas")
        return {"name": t.name, "command": f"simplicio-video {tools.COMMANDS.get(t.name, t.name)}", "status": "warn",
                "summary": f"não consegui checar ({motivo})", "installed": False, "version": None, "pin": t.ref,
                "pin_source": "pin", "pin_registry": t.ref, "pin_match": None, "upstream": None, "checks": [linha]}


def collect(*, online: bool = False, io: Optional[Any] = None) -> dict:
    """The document of `doctor trilhas`. Offline (the default) reads only the disk, the PATH and the lock. `io` is the network
    of the upstream (tools_update.Io); with --online and none given, the real one (SIMPLICIO_OFFLINE=1 blocks it)."""
    if online and io is None:
        io = tools_update.live_io()
    tracks = [_avalia_seguro(t, io if online else None) for t in tools.TOOLS.values()]
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
