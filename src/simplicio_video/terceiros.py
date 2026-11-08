"""What a third-party program receives, and the helpers the sandbox tracks share. A leaf: at import it needs only the standard library.

ENVIRONMENT. A child of a third-party track must not get a key, a token or any SIMPLICIO_* of the shell: each module passes a closed
list of names. `NUCLEO_ENV` is what every one of those lists has in common; `env_para_terceiro(extra)` is that core plus the names the
module asks for on top (its proxy and certificate variables, its own key, ...), read from the environment and only when they exist.
A name that is in neither is never passed, whatever the shell has. `PROXIES` is the one list of the eight proxy names: the modules that
let a proxy through write `(*terceiros.PROXIES, ...)` instead of typing them again.

HELPERS. `chave`, `dentro`, `real` and `commit_do_checkout` are the copies that instagram, matchcut and video_to_skill each carry
(`_chave`, `_dentro`, `_real`, `_commit_do_checkout`), with the same bodies. montage has a `_dentro` of its own (it compares real
paths another way) and keeps it.

TEXT. `limpa_mcp` (the text an agent gets) and `visivel` (the text a terminal gets) are what matchcut, instagram and video_to_skill each
carried (`_limpa_mcp`/`limpa_mcp`, `visivel`): the strictest of the three, instagram's, which also drops (or shows) the variation selectors.

WHERE A TRACK DOES NOT WRITE. matchcut, instagram, montage, video_to_skill and voicestudio each had a copy of "may the engine write at this
real path?" and the copies disagreed. `lugar_proibido` is ONE rule, the union of what they refused: a path is refused when any of them
refused it (a track's own checkout and data folder stay that track's own: it passes them as `proprios`). The words of each reason are the
ones the tracks already used, so a refusal that existed keeps its text.

`/var` as a whole is a system place (all but `/var/tmp`), with one more exception: the trees below `/var` that belong to the user, which are
the user's temporary folder (`tempfile.gettempdir()`, `$TMPDIR` and `/var/folders`, where macOS keeps it) and the user's real home (on an
ostree system, Silverblue, Bazzite, CoreOS, `/home` is `/var/home`). The other rules (hidden folder, `.git`, the data folder, a venv, ...)
still hold inside those trees, and a home or a temporary folder that is `/var` itself frees nothing.
"""
from __future__ import annotations

import os
import sys
import tempfile
import unicodedata
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path

# PATH, HOME, LANG and LC_ALL: the intersection of the lists of download, busca, status (and doctor_trilhas), matchcut, montage,
# video_to_skill and instagram (tests/test_terceiros.py freezes each of them).
NUCLEO_ENV: tuple[str, ...] = ("PATH", "HOME", "LANG", "LC_ALL")

# The names under which a shell hands its proxy to a program: HTTP, HTTPS and ALL, the NO_PROXY list of exceptions, each in upper and lower
# case. Eight lists of the tracks carried this set typed by hand (tests/test_terceiros.py freezes what each one passes).
PROXIES: tuple[str, ...] = ("HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "no_proxy", "all_proxy")

# macOS (APFS) and Windows compare folder names without regard to case (macOS also to Unicode normalization)
CASE_INSENSITIVE = sys.platform in ("darwin", "win32")


def env_para_terceiro(extra: Iterable[str] = (), *, base: Mapping[str, str] | None = None) -> dict[str, str]:
    """The environment of a third-party child: the names of NUCLEO_ENV and of `extra` that exist in `base` (the `os.environ` of the call
    by default: not the object it was at import), value as it is, and nothing else. A new dict; `base` is not touched."""
    if base is None:
        base = os.environ
    if isinstance(extra, str):  # a lone name, never its letters
        extra = (extra,)
    return {k: base[k] for k in (*NUCLEO_ENV, *extra) if k in base}


def chave(caminho: Path) -> tuple:
    if CASE_INSENSITIVE:
        return tuple(unicodedata.normalize("NFC", parte).casefold() for parte in caminho.parts)
    return tuple(caminho.parts)


def dentro(caminho: Path, pasta: Path) -> bool:
    a, b = chave(caminho), chave(pasta.resolve())
    return a[:len(b)] == b


def real(caminho: str) -> Path | None:
    try:
        return Path(caminho).resolve()
    except (OSError, RuntimeError, ValueError):
        return None


def commit_do_checkout(d: Path) -> str:
    from . import tools  # at call time: the leaf does not drag the registry of tools in at import
    try:
        return tools.git("rev-parse", "HEAD", cwd=d)
    except tools.ToolError:
        return ""


# ---- the text of a third party, for an agent and for a terminal --------------------------------------------------------------------

# Unicode categories that can hide an instruction or move a terminal: control, format (bidirectional, zero-width, tag, BOM), surrogate, private
# use, unassigned, line and paragraph separators.
RUIM = ("Cc", "Cf", "Cs", "Co", "Cn", "Zl", "Zp")


def seletor_de_variacao(c: str) -> bool:
    """Variation selectors (U+FE00-FE0F, U+E0100-E01EF) are category Mn but can carry hidden data after a visible character."""
    n = ord(c)
    return 0xFE00 <= n <= 0xFE0F or 0xE0100 <= n <= 0xE01EF


def limpa_mcp(texto: str) -> str:
    """Third-party text for an agent: no control, bidirectional, zero-width, line-separator, tag or variation-selector character (they can
    hide instructions); newline and tab stay."""
    texto = texto.replace("\r\n", "\n")
    return "".join(c for c in texto if c in "\n\t" or (not seletor_de_variacao(c) and unicodedata.category(c) not in RUIM))


def visivel(texto: str) -> str:
    """Third-party text for a terminal: ESC and the other controls become their visible marks (U+2400 block), and C1, bidirectional,
    zero-width, line-separator, BOM, tag and variation-selector characters become <U+XXXX>; newline and tab stay. A terminal never
    receives an escape sequence that came from a script (and so, possibly, from a third party's text)."""
    saida = []
    for c in texto.replace("\r\n", "\n"):
        n = ord(c)
        if c in "\n\t":
            saida.append(c)
        elif n < 0x20:
            saida.append(chr(0x2400 + n))
        elif n == 0x7F:
            saida.append(chr(0x2421))
        elif seletor_de_variacao(c) or unicodedata.category(c) in RUIM:
            saida.append(f"<U+{n:04X}>")
        else:
            saida.append(c)
    return "".join(saida)


# ---- where a track does not write: ONE rule ------------------------------------------------------------------------------------------

# The system folders (POSIX, absolute) and the names of the environment variables that hold the Windows ones.
RAIZES_POSIX: tuple[str, ...] = ("/etc", "/usr", "/bin", "/sbin", "/lib", "/lib32", "/lib64", "/libx32", "/boot", "/dev", "/proc", "/sys",
                                 "/run", "/opt", "/srv", "/snap", "/System", "/Library", "/Applications", "/private/etc", "/var/lib",
                                 "/var/log", "/var/spool", "/var/run", "/var/db")
RAIZES_WINDOWS: tuple[str, ...] = ("SYSTEMROOT", "PROGRAMFILES", "PROGRAMFILES(X86)", "PROGRAMDATA")
# Folders whose files the system runs on its own at login: never a place for an output file. The first two parts are relative to the home;
# the Startup folder of Windows is also looked for under $APPDATA, wherever that is.
INICIO_AUTOMATICO: tuple[tuple[str, ...], ...] = (("Library", "LaunchAgents"), ("Library", "LaunchDaemons"),
                                                  ("AppData", "Roaming", "Microsoft", "Windows", "Start Menu", "Programs", "Startup"))
STARTUP_DO_APPDATA: tuple[str, ...] = ("Microsoft", "Windows", "Start Menu", "Programs", "Startup")

# The reasons, in the words the tracks already used (they follow "o motor não grava", so they carry their own preposition).
SISTEMA = "em pasta do sistema"
INICIO = "em pasta de início automático (LaunchAgents, LaunchDaemons, Startup)"
OCULTA = "em pasta oculta do home (.ssh, .config, .claude...)"
GIT = "dentro de uma pasta .git"
CODIGO = "dentro do código do motor"
FERRAMENTAS = "dentro da pasta de ferramentas do motor"
DADOS = "dentro da pasta de dados do motor (jobs, tools, openmontage-data)"
SITE_PACKAGES = "dentro de site-packages (pacotes de um venv)"
VENV = "dentro de um venv (pyvenv.cfg)"


def _home() -> Path | None:
    try:
        return Path(os.path.expanduser("~")).resolve()
    except (OSError, RuntimeError):
        return None


def _tem_cfg(pasta: Path) -> bool:
    """Is there a `pyvenv.cfg` right in `pasta`? A name the disk cannot take (ENAMETOOLONG: the folder does not exist) or a folder it will not
    let us look into says no, and the other places decide: the probe never raises."""
    try:
        return (pasta / "pyvenv.cfg").is_file()
    except OSError:
        return False


def _livres_sob_var() -> Iterable[Path]:
    """The trees that may live below /var and are the user's: macOS keeps the temporary folder in /var/folders, `tempfile` and $TMPDIR name
    it, and the real home of the user (an ostree system has /home as /var/home). Asked one at a time, the cheap ones first."""
    yield Path("/var/folders")
    if os.environ.get("TMPDIR"):
        yield Path(os.environ["TMPDIR"])
    try:
        yield Path(tempfile.gettempdir())
    except OSError:  # no usable temporary folder: it names nothing
        pass
    casa = _home()
    if casa is not None:
        yield casa


def _livre_sob_var(real: Path, dentro: Callable[[Path, Path], bool]) -> bool:
    """Is `real` in one of the user's trees below /var? Only a tree strictly below /var counts: a home or a temporary folder that IS /var (or
    holds it) frees nothing."""
    var = Path("/var")
    for livre in _livres_sob_var():
        try:
            livre = livre.resolve()
        except (OSError, RuntimeError):
            continue
        if dentro(livre, var) and not dentro(var, livre) and dentro(real, livre):
            return True
    return False


def _no_comum(real: Path, dentro: Callable[[Path, Path], bool], chave: Callable[[Path], tuple]) -> str | None:
    """What every track always refused, asked in the order they always asked: a system folder, an auto-start folder, a hidden folder of the
    home, a .git anywhere in the path."""
    raizes = [Path(r) for r in RAIZES_POSIX] + [Path(v) for v in (os.environ.get(n) for n in RAIZES_WINDOWS) if v]
    if any(dentro(real, r) for r in raizes):
        return SISTEMA
    home = _home()
    inicio = [home.joinpath(*partes) for partes in INICIO_AUTOMATICO] if home is not None else []
    inicio += [Path(base).joinpath(*STARTUP_DO_APPDATA) for base in (os.environ.get("APPDATA"),) if base]
    if any(dentro(real, pasta) for pasta in inicio):
        return INICIO
    if home is not None and dentro(real, home):
        partes = real.parts[len(home.parts):]
        if partes and partes[0].startswith("."):
            return OCULTA
    if ".git" in chave(real):
        return GIT
    return None


def _no_motor(real: Path, dentro: Callable[[Path, Path], bool], chave: Callable[[Path], tuple]) -> str | None:
    """The engine's own places: its code, its tools folder, the whole data folder, a site-packages, a venv, and /var (but /var/tmp and the
    user's own trees below it: the temporary folder and the real home)."""
    if dentro(real, Path(__file__).resolve().parent):
        return CODIGO
    from . import hostos, paths, tools  # at call time: the leaf does not drag the registry of tools in at import
    for texto, pasta in ((FERRAMENTAS, tools.tools_dir), (DADOS, paths.data_root)):
        try:
            if dentro(real, pasta()):
                return texto
        except hostos.SemCasa:  # no home to find that folder in: it is not asked about (a track that always asked still gets the error)
            continue
    if "site-packages" in chave(real):
        return SITE_PACKAGES
    if any(_tem_cfg(a) for a in real.parents):
        return VENV
    if dentro(real, Path("/var")) and not dentro(real, Path("/var/tmp")) and not _livre_sob_var(real, dentro):
        return SISTEMA
    return None


def lugar_proibido(real: Path, proprios: Iterable[tuple[Path | Iterable[Path], str]] = (), *, motor_antes: bool = False,
                   dentro: Callable[[Path, Path], bool] = dentro, chave: Callable[[Path], tuple] = chave) -> str | None:
    """Why the engine does not write at `real` (where the write would really land, links resolved), or None.

    `proprios` are the places that belong to the track that asks, as (folder or folders, words) in the order it always asked them: they come
    first and their words are the track's (its checkout, its data folder). They are asked one at a time, only up to the first that holds
    `real`, so a folder that cannot be found (no home) is not looked for once the answer is known. After them come the places every track
    refuses: a system folder, an auto-start folder, a hidden folder of the home, a .git; and then the engine's own places (its code, tools
    and data folders, site-packages, a venv, /var but /var/tmp and the user's temporary folder and real home). A path under two of them gets
    the reason that comes first: `motor_antes` swaps the last two groups, for the track that always told those first (montage). The order
    never decides WHETHER a path is refused.

    `dentro` and `chave` compare folder names: a track that lets its tests flip its own case rule passes its own (the defaults follow
    `CASE_INSENSITIVE` here)."""
    for alvo, texto in proprios:
        if isinstance(alvo, Path):
            alvo = (alvo,)
        if any(dentro(real, pasta) for pasta in alvo):
            return texto
    for passo in ((_no_motor, _no_comum) if motor_antes else (_no_comum, _no_motor)):
        texto = passo(real, dentro, chave)
        if texto:
            return texto
    return None
