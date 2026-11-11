"""last30days-skill track (`simplicio-video last30days`): hermetic, no network, no real clone.

The upstream (https://github.com/mvanhorn/last30days-skill, MIT, pinned commit 07021dc) is replaced by a FAKE checkout written
into a temporary folder: one `skills/last30days/SKILL.md`. The module's sha256 table is monkeypatched to the hash of the fake
file, so every refusal below is the engine's own.

Central proofs: the track only downloads and reads the skill (it never runs a script of the upstream, never reads a browser
cookie, never asks for or passes on a key, never posts); the SKILL.md body is checked against the pinned sha256 and the pinned
commit before it is returned, as third-party text; offline mode refuses the clone.
"""
from __future__ import annotations

import ast
import hashlib
import inspect
import json
import re
from types import SimpleNamespace

import pytest

from helpers import isolate_tools
from simplicio_video import cli, last30days, tools

PIN = "07021dcf411070747d2585f590c3c8c502bf6991"
REPO = "https://github.com/mvanhorn/last30days-skill"
SHA64 = re.compile(r"^[0-9a-f]{64}$")
REL = "skills/last30days/SKILL.md"


@pytest.fixture(autouse=True)
def _isolated(monkeypatch, tmp_path):
    (tmp_path / "home").mkdir()
    isolate_tools(monkeypatch, tmp_path, drop=("LAST30DAYS_DIR", "SIMPLICIO_LAST30DAYS_DIR", "SIMPLICIO_LAST30DAYS_REF"))


@pytest.fixture
def l30(tmp_path, monkeypatch):
    d = tmp_path / "last30days"
    (d / "skills" / "last30days").mkdir(parents=True)
    (d / REL).write_text("---\nname: last30days\ndescription: Fake.\n---\n\n# last30days\n", encoding="utf8")
    monkeypatch.setenv("LAST30DAYS_DIR", str(d))
    monkeypatch.setattr(last30days, "PINNED_SKILLS_SHA256", {REL: hashlib.sha256((d / REL).read_bytes()).hexdigest()})
    ref = tools.get("last30days").ref
    monkeypatch.setattr(tools, "_git", lambda *a, cwd=None: ref)
    return SimpleNamespace(dir=d.resolve(), ref=ref)


def run(capsys, *argv):
    rc = cli.main(["last30days", *argv])
    out, err = capsys.readouterr()
    return rc, out, err


def test_pinned_to_a_full_commit_under_mit():
    t = tools.get("last30days")
    assert t.kind == "git" and t.source == REPO and t.ref == PIN and t.license == "MIT"
    assert t.marker == REL
    assert "cookies" in t.note and "ScrapeCreators" in t.note and "Python 3.12" in t.note
    assert tools.command(t) == "simplicio-video last30days"


def test_the_pinned_table_has_the_real_skill():
    assert list(last30days.PINNED_SKILLS_SHA256) == [REL]
    assert all(SHA64.match(h) for h in last30days.PINNED_SKILLS_SHA256.values())
    assert last30days.PINNED_SKILLS_SHA256[REL] == "b9d92e61fe29af906bdb1262a31603c98e8aa670f90a9cf627e5a5ff3d037445"


def test_clone_refuses_offline_mode(monkeypatch):
    monkeypatch.setenv("SIMPLICIO_OFFLINE", "1")
    with pytest.raises(last30days.Last30DaysError, match="offline"):
        last30days.clone_last30days()


def test_clone_points_the_install_at_the_given_folder(tmp_path, monkeypatch):
    monkeypatch.delenv("SIMPLICIO_OFFLINE", raising=False)
    seen = []
    monkeypatch.setattr(tools, "install", lambda name, dir=None: seen.append((name, dir)) or str(dir))
    target = tmp_path / "meu-checkout"
    assert last30days.clone_last30days(target) == target
    assert seen == [("last30days", target)]


def test_where_and_status_without_a_checkout(capsys):
    rc, out, err = run(capsys, "status", "--json")
    info = json.loads(out)
    assert rc == 0 and info["instalado"] is False and info["commit_fixado"] == PIN
    assert run(capsys, "where")[0] != 0


def test_status_checks_the_skill_and_flags_a_tampered_one(l30, capsys):
    info = json.loads(run(capsys, "status", "--json")[1])
    assert info["instalado"] and info["commit_confere"] and info["skills_conferidas"] == {"last30days": "ok"}
    (l30.dir / REL).write_text("mudou", encoding="utf8")
    info = json.loads(run(capsys, "status", "--json")[1])
    assert info["skills_conferidas"]["last30days"] == "diferente"


def test_where_prints_the_skill_folder(l30, capsys):
    rc, out, _ = run(capsys, "where", "--skills")
    assert rc == 0 and out.strip() == str(l30.dir / "skills" / "last30days")


def test_skill_returns_the_checked_body_as_third_party_text(l30, capsys):
    rc, out, err = run(capsys, "skill")
    assert rc == 0 and "# last30days" in out and "terceiros" in err
    info = json.loads(run(capsys, "skill", "--json")[1])
    assert info["untrusted_conteudo"].startswith("---") and info["truncado"] is False
    assert "cookies" in info["aviso"]


def test_skill_refuses_a_tampered_body_and_another_commit(l30, monkeypatch):
    (l30.dir / REL).write_text("trocado", encoding="utf8")
    with pytest.raises(last30days.Last30DaysError, match="sha256"):
        last30days.skill_info()
    monkeypatch.setattr(tools, "_git", lambda *a, cwd=None: "0" * 40)
    with pytest.raises(last30days.Last30DaysError, match="commit"):
        last30days.skill_info()


def test_skill_takes_no_name(l30, capsys):
    with pytest.raises(last30days.Last30DaysError, match="argumento desconhecido"):
        last30days.run_last30days(["skill", "../../etc/passwd"])


def test_unknown_subcommand_is_refused(capsys):
    rc, _, err = run(capsys, "run", "x")
    assert rc != 0 and "subcomando desconhecido" in err


def test_the_module_never_runs_anything_nor_opens_the_network():
    arvore = ast.parse(inspect.getsource(last30days))
    importados = {a.name.split(".")[0] for n in ast.walk(arvore) if isinstance(n, (ast.Import, ast.ImportFrom))
                  for a in n.names} | {(n.module or "").split(".")[0] for n in ast.walk(arvore) if isinstance(n, ast.ImportFrom)}
    assert not importados & {"subprocess", "socket", "urllib", "http", "requests", "sqlite3", "browser_cookie3"}
