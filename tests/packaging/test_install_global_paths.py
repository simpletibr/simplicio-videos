"""U13: `install`, `doctor` and `update` without a crossed import, and the output that must not move while they are cut.

What the refactor changes, and what it must NOT change:

* `commands/install.global_skill_paths(root)`: the two list comprehensions "what is the global install" (the folder of every
  skill in every global root) become one function (`_protect_global`, and `install --global --prune-project-copies`);
* `commands/versions.py`: the release parser (`parse_version`, `format_version`, `release_tuple`) and the state of the last
  check (`default_state_dir`, `read_check`, `write_check`, `CheckInvalid`) leave `update.py` (a client of GitHub, pip and git) so
  that `doctor` does not have to import it for them; `update` re-exports the same objects, the tests keep their names;
* `doctor` reads only public names (no `update._git`) and says no hand-written count of tracks (`len(tools.TOOLS)` is the count);
* `install.py` no longer lists "two" skills in its docstring.

The green half (the first commit, and the last) freezes the bytes: `doctor --json` and `install --json` of a box (`caixa`) are
the same text before and after. The text is normalized only where it must be (the temp folder, this checkout's folder, the
version and the `sha256:` digests, which change with the version and with the files of a release), nothing else.
"""
from __future__ import annotations

import ast
import hashlib
import json
import re
from pathlib import Path

import pytest

import _caixa
from _caixa import distribution, install_cmd, installer, skill_sync, update_cmd
from _comum import executa, make_bundle
from simplicio_video import __version__, tools
from simplicio_video.cli import main
from helpers import ROOT

caixa = _caixa.caixa
saude = _caixa.saude

versions_cmd = _caixa._Lazy("simplicio_video.commands.versions")
COMMANDS = ROOT / "src" / "simplicio_video" / "commands"

# What leaves update.py for versions.py (the same objects stay reachable as `update.<name>`).
MOVED = ("parse_version", "format_version", "release_tuple", "default_state_dir", "read_check", "write_check", "CheckInvalid",
         "CHECK_FILE")


# ------------------------------------------------------------------------------------------------ global_skill_paths


def test_global_skill_paths_is_every_skill_in_every_global_root(tmp_path):
    root = tmp_path / "home"
    got = install_cmd.global_skill_paths(root)
    assert got == [root / dest / name for dest in installer.GLOBAL_ROOTS for name in installer.SKILLS]
    assert len(got) == len(installer.GLOBAL_ROOTS) * len(skill_sync.SKILLS)
    assert all(isinstance(p, Path) for p in got)


def test_global_skill_paths_has_one_definition_in_install_py():
    """The comprehension is written once: `_protect_global` and `install()` both call the function."""
    tree = ast.parse((COMMANDS / "install.py").read_text(encoding="utf8"))
    comps = [n for n in ast.walk(tree) if isinstance(n, ast.ListComp) and "GLOBAL_ROOTS" in ast.unparse(n)
             and "SKILLS" in ast.unparse(n)]
    assert len(comps) == 1, [ast.unparse(c) for c in comps]


# --------------------------------------------------------------------------------------------------------- versions


@pytest.mark.parametrize("name", MOVED)
def test_versions_has_what_leaves_update_and_update_reexports_the_same_object(name):
    assert getattr(versions_cmd, name) is getattr(update_cmd, name)


def test_versions_does_not_import_the_clients_of_github_pip_or_git():
    imports = {n.module or "" for n in ast.walk(ast.parse((COMMANDS / "versions.py").read_text(encoding="utf8")))
               if isinstance(n, ast.ImportFrom)} | {a.name for n in ast.walk(ast.parse((COMMANDS / "versions.py").read_text(encoding="utf8")))
                                                    if isinstance(n, ast.Import) for a in n.names}
    assert not {m for m in imports if "update" in m or "urllib" in m or m == "subprocess"}, imports


# ----------------------------------------------------------------------------------------------------------- doctor


def _doctor_names_on(module: str) -> set[str]:
    tree = ast.parse((COMMANDS / "doctor.py").read_text(encoding="utf8"))
    return {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == module}


def test_doctor_reads_the_versions_and_the_state_of_the_check_from_versions_not_from_update():
    assert not set(MOVED) & _doctor_names_on("update"), "doctor still takes the moved names from update.py"
    assert {"parse_version", "release_tuple", "read_check", "write_check", "CheckInvalid", "default_state_dir"} <= _doctor_names_on("versions")


def test_doctor_uses_no_private_name_of_another_module():
    tree = ast.parse((COMMANDS / "doctor.py").read_text(encoding="utf8"))
    imported = {a.asname or a.name for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.level
                for a in n.names}
    private = sorted(f"{n.value.id}.{n.attr}" for n in ast.walk(tree)
                     if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id in imported
                     and n.attr.startswith("_"))
    assert not private, private


def test_doctor_does_not_spell_out_how_many_tracks_there_are():
    """The count is `len(tools.TOOLS)`; a number written by hand in a docstring or a comment goes stale with the next track."""
    text = (COMMANDS / "doctor.py").read_text(encoding="utf8")
    assert not re.search(r"\b(thirteen|treze|13)\b", text, re.IGNORECASE), "a hand-written count of tracks in doctor.py"


def test_install_docstring_does_not_list_two_skills_by_hand():
    doc = install_cmd._real().__doc__  # (`__doc__` of the lazy proxy would be the proxy's own)
    assert "SKILLS" in doc, "the skills that ship are the ones of skill_sync.SKILLS: say that, not a list that goes stale"
    assert "simplicio-video-social" not in doc


# ------------------------------------------------------------------------- the bytes that must not move (green)


def _normal(text: str, tmp_path: Path) -> str:
    """The output with only what changes from one run to the next replaced: temp folder, this checkout, version, digests."""
    text = text.replace(str(tmp_path), "<TMP>").replace(str(ROOT), "<ROOT>").replace(__version__, "<VERSION>")
    return re.sub(r"sha256:[0-9a-f]{64}", "sha256:<D>", text)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _doctor_text(capsys, tmp_path: Path) -> tuple[int, str]:
    rc, out, err = executa(["doctor", "--json"], capsys, main)
    assert err == ""
    doc = json.loads(out)
    for row in doc["checks"]:
        if row["name"] == "trilhas":  # the pins and the upstream of each track change with the pins: only the shape is frozen here
            row["detail"] = {"tracks": [{"name": t["name"], "command": t["command"], "status": t["status"]} for t in row["detail"]["tracks"]]}
    return rc, _normal(json.dumps(doc, sort_keys=True), tmp_path)


def test_doctor_json_is_the_same_text_as_before(saude, tmp_path, capsys):
    rc, text = _doctor_text(capsys, tmp_path)
    assert rc == 0
    doc = json.loads(text)
    assert [(c["name"], c["status"]) for c in doc["checks"]] == [
        ("update", "ok"), ("distribution", "ok"), ("runtime", "ok"), ("python", "ok"), ("node", "ok"), ("ffmpeg", "ok"),
        ("ffmpeg-libass", "ok"), ("disk", "ok"), ("ports", "ok"), ("GEMINI_API_KEY", "ok"), ("setup", "ok"), ("tools", "ok"),
        ("trilhas", "warn")]
    update_row = doc["checks"][0]
    assert update_row["summary"] == ("nenhuma checagem em cache; rode `simplicio-video update --check` ou "
                                     "`simplicio-video doctor --online`")
    assert _sha(text) == "8a02287d7f9f819798b5b19ed56a8f76a36f638dba7dfdd007c4f7d150d4e11f", f"{_sha(text)}\n{text}"


def test_doctor_counts_the_tracks_of_the_registry(saude, tmp_path, capsys):
    rc, out, err = executa(["doctor", "--json"], capsys, main)
    row = next(c for c in json.loads(out)["checks"] if c["name"] == "trilhas")
    assert [t["name"] for t in row["detail"]["tracks"]] == list(tools.TOOLS)
    assert re.fullmatch(rf"\d+ de {len(tools.TOOLS)} trilhas em dia(; .*)?", row["summary"]), row["summary"]


def test_doctor_json_with_the_cached_check_reads_it_through_versions(saude, tmp_path, capsys):
    update_cmd.write_check({"installed": "0.1.0", "latest": "9.9.9", "update_available": True, "kind": "source", "commits_behind": 3})
    rc, out, err = executa(["doctor", "--json"], capsys, main)
    row = next(c for c in json.loads(out)["checks"] if c["name"] == "update")
    assert row["status"] == "warn" and row["fix"] == "simplicio-video update"
    assert row["detail"]["latest"] == "9.9.9" and row["detail"]["installed"] == __version__
    assert row["detail"]["update_available"] is True and row["detail"]["commits_behind"] == 3
    assert f"{__version__} -> 9.9.9" in row["summary"]


@pytest.fixture
def pacote(saude, monkeypatch, tmp_path):
    """A tiny bundle instead of the real package data (the text does not move with the skills of a release), and a project."""
    bundle = make_bundle(tmp_path / "bundle")
    monkeypatch.setattr(distribution, "bundle_root", lambda: bundle, raising=False)
    alvo = tmp_path / "proj"
    alvo.mkdir()
    saude.alvo = alvo
    return saude


def _install(capsys, tmp_path, *argv) -> tuple[int, str]:
    rc, out, err = executa(["install", "--json", *argv], capsys, main)
    return rc, _normal(out, tmp_path)


# the project plan, the global plan, the global plan with the project copies pruned, the two uninstalls (they protect the global install)
@pytest.mark.parametrize("nome", ["projeto", "global", "global_poda"])
def test_install_json_plan_is_the_same_text_as_before(pacote, tmp_path, capsys, nome):
    alvo = ["--target", str(pacote.alvo)]
    argv = {"projeto": ["--dry-run", *alvo], "global": ["--dry-run", "--global"],
            "global_poda": ["--dry-run", "--global", "--prune-project-copies", *alvo]}[nome]
    rc, text = _install(capsys, tmp_path, *argv)
    doc = json.loads(text)
    assert rc == 0 and doc["schema"] == "simplicio.video-install-plan/v1" and doc["status"] == "dry_run", text
    assert doc["written"] == 0
    assert text.strip() == json.dumps(doc, sort_keys=True), "the formatting of the document (sort_keys, ensure_ascii) is part of it"
    assert _sha(text) == FROZEN_INSTALL[nome], f"{_sha(text)}\n{text}"


@pytest.mark.parametrize("nome", ["projeto", "global"])
def test_install_json_uninstall_preview_is_the_same_text_as_before(pacote, tmp_path, capsys, nome):
    globally = ["--global"] if nome == "global" else ["--target", str(pacote.alvo)]
    rc, out = _install(capsys, tmp_path, *globally)
    assert rc == 0, out
    rc, text = _install(capsys, tmp_path, *globally, "--uninstall", "--dry-run")
    doc = json.loads(text)
    assert rc == 0 and doc["removed"], text
    assert _sha(text) == FROZEN_UNINSTALL[nome], f"{_sha(text)}\n{text}"


FROZEN_INSTALL = {"projeto": "59f28e3cd4493ac70f5e226af4bbdac03794948ce351d938d4cc82d46595243c", "global": "6f7525fa15d0fc0031e4933778024eb049715c6a12f4582d3cab48d402391b10", "global_poda": "17df2590107654e768bfdde063cc787367b10cd7cdbd747bfa1ea6fd93581879"}
FROZEN_UNINSTALL = {"projeto": "e29ae2951d8da69d6d4dcab913c3b2becc0c948cb3f02a975f9152d841947a1b", "global": "f513e51e6391945f09d72efb51185a668cd82262344470504f0e06d8f9057178"}
