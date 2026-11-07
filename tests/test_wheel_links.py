"""Text that ships in the wheel never points at a file that only exists in the checkout (U04).

`docs/`, `voices/`, `colab/` and `intake/` live at the root of the repository and are NOT in the wheel, so a message
(or a link in a README under `src/simplicio_video/data/`) that says `docs/custos.md` is a dead end after `pip install`.
The fix is a versioned URL: `paths.doc_url(rel)`. Only the TEXT of messages and docstrings changes: no `--json` field,
no exit code and no MCP snapshot moves (the `notebook` field of `render --backend colab` stays as it is: public
contract, UNVERIFIED, so it is the owner's call).

Three checks:

* every string constant of `src/simplicio_video/**/*.py` (docstrings and the literal parts of f-strings included, but
  not comments) is free of a bare `docs/|voices/|colab/|intake/` path, except the ALLOWLIST below;
* every Markdown file of `src/simplicio_video/data/**` links only to files that exist inside the package, or to a URL,
  and says no bare checkout path in prose;
* every `paths.doc_url("<rel>")` call and every `blob/<ref>/<rel>` URL points at a file that exists in the checkout, so
  moving a document (an `arquivo/` sweep, a rename) fails here instead of leaving a dead link in the wheel.
"""
import ast
import re
import types
from pathlib import Path

import pytest

import simplicio_video
from simplicio_video import paths

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "src" / "simplicio_video"
REPO_URL = "https://github.com/simpletibr/simplicio-videos/blob/"

# A checkout path: preceded by neither a word character nor `/` `.` `:` `~` `-` (so a path inside a URL, a name like
# `googlecolab/...` or `~/.cache/colab/...` is not one), after any number of `../`.
_BARE = re.compile(r"(?<![\w/.:~-])((?:\.\./)*(?:docs|voices|colab|intake)/[\w./#-]*)")
_URL = re.compile(re.escape(REPO_URL) + r"(?:main|v\d[\w.]*)/([\w./-]+)")
_MD_LINK = re.compile(r"\[[^\]\n]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
_MD_URL_LINK = re.compile(r"\[[^\]\n]*\]\(https?://[^)\s]*\)")

# (file relative to src/simplicio_video, the path as written) -> why it is still there. An entry is removed when its
# owner fixes the text; a new offender is never added without the owner of the file agreeing.
ALLOWLIST = {
    ("render.py", "colab/render.ipynb"):
        "docstring of render_colab, which returns that path in the JSON field `notebook`: the owner decides (PLAN 5, q.7)",
    ("cli.py", "colab/render.ipynb"): "help text of `render`; cli.py belongs to U10a, which moves it to paths.doc_url",
    ("cli.py", "docs/custos.md"): "help text of `render` and of the main epilog; cli.py belongs to U10a",
    ("cli.py", "docs/decisoes/ADR-0003-fluxo-100-script.md"): "epilog of the main parser; cli.py belongs to U10a",
    ("childio.py", "docs/host/gate.md"): "module docstring for the developers of the guard; childio is untouchable",
    ("engine/remote_render.py", "colab/render.ipynb"): "docstring of the headless script that runs on the remote box",
    ("data/motion/README.md", "docs/recursos.md"): "hand-written note of the motion README, not in U04's files",
    ("data/templates/assistencia-tecnica-games/README.md", "docs/esteira.md"):
        "template README, not one of the three U04 owns (templates, sazonal, video-use)",
}


def _clean(path: str) -> str:
    return path.rstrip(".,;:)")


def _bare_paths(text: str) -> list[str]:
    """The checkout paths a text names: a file (`docs/a.md`) or a folder (`voices/`); `intake/template` is two words."""
    found = (_clean(m.group(1)) for m in _BARE.finditer(text))
    return [p for p in found if p.endswith("/") or re.search(r"\.\w+(#.*)?$", p)]


def _doc_url_args(tree: ast.AST) -> set[int]:
    """`id()` of the string constants that are the argument of a `doc_url(...)` call (checked on their own)."""
    skip: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and node.args and isinstance(node.args[0], ast.Constant):
            f = node.func
            if (isinstance(f, ast.Name) and f.id == "doc_url") or (isinstance(f, ast.Attribute) and f.attr == "doc_url"):
                skip.add(id(node.args[0]))
    return skip


def _py_files() -> list[Path]:
    return sorted(PKG.rglob("*.py"))


def _md_files() -> list[Path]:
    return sorted((PKG / "data").rglob("*.md"))


def _py_bare_paths() -> list[tuple[str, str, int]]:
    found = []
    for path in _py_files():
        tree = ast.parse(path.read_text(encoding="utf8"))
        skip = _doc_url_args(tree)
        rel = path.relative_to(PKG).as_posix()
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in skip:
                found.extend((rel, p, node.lineno) for p in _bare_paths(node.value))
    return found


def _md_prose(text: str) -> str:
    """The Markdown text without its link constructs (checked on their own) and without URLs."""
    return re.sub(r"https?://\S+", "", _MD_LINK.sub("", text))


def _md_bare_paths() -> list[tuple[str, str, int]]:
    found = []
    for path in _md_files():
        rel = path.relative_to(PKG).as_posix()
        for n, line in enumerate(path.read_text(encoding="utf8").splitlines(), 1):
            found.extend((rel, p, n) for p in _bare_paths(_md_prose(line)))
    return found


def _md_relative_links() -> list[tuple[str, str, int]]:
    """Relative link targets of the data Markdown files that do not resolve to a file inside the package."""
    found = []
    for path in _md_files():
        for n, line in enumerate(path.read_text(encoding="utf8").splitlines(), 1):
            for m in _MD_LINK.finditer(line):
                target = m.group(1)
                if re.match(r"(https?:|mailto:|#)", target):
                    continue
                dest = (path.parent / target.split("#")[0]).resolve()
                if not dest.exists() or PKG.resolve() not in (dest, *dest.parents):
                    found.append((path.relative_to(PKG).as_posix(), target, n))
    return found


def _repo_files_referenced() -> list[tuple[str, str]]:
    """(where, rel) for each `doc_url("rel")` literal and each `blob/<ref>/<rel>` URL in the strings and the data Markdown."""
    refs: list[tuple[str, str]] = []
    for path in _py_files():
        tree = ast.parse(path.read_text(encoding="utf8"))
        skip = _doc_url_args(tree)
        rel_py = path.relative_to(PKG).as_posix()
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if id(node) in skip:
                    refs.append((rel_py, node.value.split("#")[0]))
                refs.extend((rel_py, _clean(m.group(1)).split("#")[0]) for m in _URL.finditer(node.value))
    for path in _md_files():
        text = path.read_text(encoding="utf8")
        refs.extend((path.relative_to(PKG).as_posix(), _clean(m.group(1)).split("#")[0]) for m in _URL.finditer(text))
    return refs


def _versioned(rel: str) -> str:
    return f"{REPO_URL}v{simplicio_video.__version__}/{rel}"


# ---------------------------------------------------------------------------------------------------------- doc_url

def test_doc_url_is_the_versioned_blob_url():
    assert paths.doc_url("docs/custos.md") == _versioned("docs/custos.md")


def test_doc_url_follows_the_package_version(monkeypatch):
    monkeypatch.setattr(paths, "__version__", "9.9.9", raising=False)
    assert paths.doc_url("voices/openvoice.md") == f"{REPO_URL}v9.9.9/voices/openvoice.md"


# ----------------------------------------------------------------------------------------------- the wheel scan

def test_the_regex_tells_a_checkout_path_from_a_url_and_from_a_name():
    texto = (f"see docs/a.md, ../../intake/README.md, (voices/x.md) and colab/; but {REPO_URL}main/docs/a.md, "
             "github.com/googlecolab/google-colab-cli, ~/.cache/colab/x.md, the intake/template and docs are not")
    assert _bare_paths(texto) == ["docs/a.md", "../../intake/README.md", "voices/x.md", "colab/"]


def test_no_message_or_docstring_of_the_package_names_a_checkout_only_file():
    quebrados = [f"{arq}:{n}: {caminho}" for arq, caminho, n in _py_bare_paths() if (arq, caminho) not in ALLOWLIST]
    assert not quebrados, ("strings in src/ that ship in the wheel point at files that only exist in the checkout; use "
                           "paths.doc_url(rel) (or the blob/main URL in a docstring):\n  " + "\n  ".join(quebrados))


def test_no_data_markdown_says_a_checkout_path_in_prose():
    quebrados = [f"{arq}:{n}: {caminho}" for arq, caminho, n in _md_bare_paths() if (arq, caminho) not in ALLOWLIST]
    assert not quebrados, "write the URL of the file, not its checkout path:\n  " + "\n  ".join(quebrados)


def test_every_relative_link_of_the_data_markdown_stays_inside_the_package():
    quebrados = [f"{arq}:{n}: ({alvo})" for arq, alvo, n in _md_relative_links()]
    assert not quebrados, ("a relative link that leaves src/simplicio_video/ (or does not exist) is dead after pip install:"
                           "\n  " + "\n  ".join(quebrados))


def test_every_url_to_a_repository_file_points_at_a_file_that_exists():
    refs = _repo_files_referenced()
    assert refs, "the scan found no doc_url(...) call nor blob URL: the regexes are broken"
    mortos = sorted({f"{onde}: {rel}" for onde, rel in refs if not (ROOT / rel).exists()})
    assert not mortos, "the URL names a file that is not in the checkout (moved or renamed?):\n  " + "\n  ".join(mortos)


def test_the_allowlist_only_names_files_that_exist():
    for arq, _ in ALLOWLIST:
        assert (PKG / arq).is_file(), arq


# ------------------------------------------------------------------------------- the messages, one by one

def test_publish_points_the_rclone_failure_to_the_versioned_adr():
    from simplicio_video import publish

    def runner(cmd):
        return types.SimpleNamespace(returncode=2, stdout="", stderr="boom")

    with pytest.raises(SystemExit) as e:
        publish._lsjson(runner, "rclone", "gdrive:x")
    msg = str(e.value)
    assert msg.startswith("rclone lsjson gdrive:x failed (exit 2):\nboom\ncheck the remote: `rclone about <remote>:` (auth: ")
    assert _versioned("docs/decisoes/ADR-0003-fluxo-100-script.md") in msg
    assert "(auth: docs/" not in msg


def test_remote_missing_binary_points_to_the_versioned_adr(monkeypatch):
    from simplicio_video import remote

    monkeypatch.delenv("SIMPLICIO_TESTE_BIN", raising=False)
    monkeypatch.setenv("PATH", "")
    with pytest.raises(SystemExit) as e:
        remote._bin("SIMPLICIO_TESTE_BIN", "binario-que-nao-existe")
    msg = str(e.value)
    assert msg.startswith("`binario-que-nao-existe` not found on PATH (install it or set SIMPLICIO_TESTE_BIN); see ")
    assert msg.endswith(_versioned("docs/decisoes/ADR-0003-fluxo-100-script.md"))


def test_realoficial_check_points_to_the_versioned_doc(monkeypatch, capsys):
    from simplicio_video import realoficial

    monkeypatch.setattr(realoficial.shutil, "which", lambda name: "/usr/bin/npx")
    assert realoficial.run_realoficial(["check"]) == 0
    out = capsys.readouterr().out
    assert out.startswith(f"ok: npx presente; MCP em {realoficial.REALOFICIAL_MCP_URL} (OAuth login in your MCP client; tools: ")
    assert out.strip().endswith(f"{_versioned('docs/realoficial.md')})")


def test_setup_realoficial_points_to_the_versioned_doc(tmp_path, monkeypatch, capsys):
    from simplicio_video.commands import setup

    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("SIMPLICIO_WORKSPACE", str(tmp_path / "ws"))
    args = types.SimpleNamespace(yes=True, theme=None, lang=None, force=False, realoficial=True)
    assert setup.run(args) == 0
    out = capsys.readouterr().out
    assert "Adicione essa URL no seu cliente MCP e entre com OAuth (" in out
    assert f"({_versioned('docs/realoficial.md')}). O setup não guarda token." in out


def test_openvoice_without_python_points_to_the_versioned_doc(tmp_path, monkeypatch):
    from simplicio_video import voice_clone

    monkeypatch.delenv("OPENVOICE_PY", raising=False)
    with pytest.raises(voice_clone.CloneVoiceError) as e:
        voice_clone.openvoice({}, "texto", tmp_path / "out.wav", tmp_path / "ref.wav", None)
    msg = str(e.value)
    assert msg.startswith("provider=openvoice: set OPENVOICE_PY to a Python with OpenVoice installed (see ")
    assert msg.endswith(f"{_versioned('voices/openvoice.md')})")
