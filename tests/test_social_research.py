"""social-media-research-skills track (`simplicio-video social-research`): hermetic, no network, no real clone.

The upstream (https://github.com/wesleysimplicio/social-media-research-skills, MIT, pinned commit 64ba7b4) is replaced by a FAKE
checkout written into a temporary folder: 13 `SKILL.md`. The module's sha256 table is monkeypatched to the hashes of the fake
files, so every refusal below is the engine's own.

Central proofs: the track only downloads, lists and reads the skills (it never runs a script and never calls ScrapeCreators);
a skill name is one the listing gives, never a path; a SKILL.md body is checked against the pinned sha256 and the pinned commit
before it is returned, as third-party text; offline mode refuses the clone.
"""
from __future__ import annotations

import ast
import hashlib
import inspect
import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from helpers import isolate_tools
from simplicio_video import cli, social_research, tools

PIN = "64ba7b4dea71e130d2712ffb6c1c1024b3b7c4b2"
REPO = "https://github.com/wesleysimplicio/social-media-research-skills"
SHA64 = re.compile(r"^[0-9a-f]{64}$")
SKILL_NAMES = ["ad-library-teardown", "audience-research", "comment-mining", "competitor-social-research", "content-repurposing",
               "creator-profile-teardown", "influencer-prospecting", "outlier-post-finder", "product-demand-research",
               "scrapecreators-api", "social-listening-brief", "transcript-intelligence", "trend-discovery"]


def front_matter(name: str, description: str) -> str:
    return f"---\nname: {name}\ndescription: {description}\nallowed-tools: Bash, Read\n---\n\n# {name}\n"


@pytest.fixture(autouse=True)
def _isolated(monkeypatch, tmp_path):
    (tmp_path / "home").mkdir()
    isolate_tools(monkeypatch, tmp_path, drop=("SOCIAL_RESEARCH_DIR", "SIMPLICIO_SOCIAL_RESEARCH_DIR", "SIMPLICIO_SOCIAL_RESEARCH_REF"))


@pytest.fixture
def sr(tmp_path, monkeypatch):
    d = tmp_path / "social_research"
    for name in SKILL_NAMES:
        (d / "skills" / name).mkdir(parents=True)
        (d / "skills" / name / "SKILL.md").write_text(front_matter(name, f"Fake description of {name}."), encoding="utf8")
    monkeypatch.setenv("SOCIAL_RESEARCH_DIR", str(d))
    monkeypatch.setattr(social_research, "PINNED_SKILLS_SHA256",
                        {f"skills/{n}/SKILL.md": hashlib.sha256((d / "skills" / n / "SKILL.md").read_bytes()).hexdigest()
                         for n in SKILL_NAMES})
    ref = tools.get("social_research").ref
    monkeypatch.setattr(tools, "_git", lambda *a, cwd=None: ref)
    return SimpleNamespace(dir=d.resolve(), ref=ref)


def run(capsys, *argv):
    rc = cli.main(["social-research", *argv])
    out, err = capsys.readouterr()
    return rc, out, err


def test_pinned_to_a_full_commit_under_mit():
    t = tools.get("social_research")
    assert t.kind == "git" and t.source == REPO and t.ref == PIN and t.license == "MIT"
    assert t.marker == "skills/outlier-post-finder/SKILL.md"
    assert "ScrapeCreators" in t.note
    assert tools.command(t) == "simplicio-video social-research"


def test_the_pinned_table_has_the_thirteen_real_skills():
    assert sorted(social_research.PINNED_SKILLS_SHA256) == sorted(f"skills/{n}/SKILL.md" for n in SKILL_NAMES)
    assert all(SHA64.match(h) for h in social_research.PINNED_SKILLS_SHA256.values())
    assert social_research.PINNED_SKILLS_SHA256["skills/outlier-post-finder/SKILL.md"] == (
        "c648fbe9dda692cc7c034ca8b193e3b129ba4db45f8ff992f463206610d80bfa")


def test_clone_refuses_offline_mode(monkeypatch):
    monkeypatch.setenv("SIMPLICIO_OFFLINE", "1")
    with pytest.raises(social_research.SocialResearchError, match="offline"):
        social_research.clone_social_research()


def test_clone_points_the_install_at_the_given_folder(tmp_path, monkeypatch):
    monkeypatch.delenv("SIMPLICIO_OFFLINE", raising=False)
    seen = []
    monkeypatch.setattr(tools, "install", lambda name, dir=None: seen.append((name, dir)) or str(dir))
    target = tmp_path / "meu-checkout"
    assert social_research.clone_social_research(target) == target
    assert seen == [("social_research", target)]


def test_where_and_status_without_a_checkout(capsys):
    rc, out, err = run(capsys, "status", "--json")
    info = json.loads(out)
    assert rc == 0 and info["instalado"] is False and info["commit_fixado"] == PIN
    assert run(capsys, "where")[0] != 0


def test_status_counts_the_checked_skills_and_flags_a_tampered_one(sr, capsys):
    info = json.loads(run(capsys, "status", "--json")[1])
    assert info["instalado"] and info["commit_confere"] and set(info["skills_conferidas"].values()) == {"ok"}
    (sr.dir / "skills" / "comment-mining" / "SKILL.md").write_text("mudou", encoding="utf8")
    info = json.loads(run(capsys, "status", "--json")[1])
    assert info["skills_conferidas"]["comment-mining"] == "diferente"


def test_skills_lists_the_thirteen_as_third_party_text(sr, capsys):
    rc, out, _ = run(capsys, "skills", "--json")
    info = json.loads(out)
    assert rc == 0 and [s["nome"] for s in info["skills"]] == SKILL_NAMES
    assert info["skills"][0]["untrusted_descricao"] == "Fake description of ad-library-teardown."
    assert "ScrapeCreators" in info["aviso"]


def test_skill_returns_the_checked_body(sr, capsys):
    rc, out, err = run(capsys, "skill", "trend-discovery")
    assert rc == 0 and "# trend-discovery" in out and "terceiros" in err


def test_skill_refuses_a_path_an_unknown_name_and_a_tampered_body(sr, capsys):
    for nome in ("../../etc/passwd", "nao-existe", "skills/trend-discovery"):
        with pytest.raises(social_research.SocialResearchError, match="skill desconhecida"):
            social_research.skill_info(nome)
    (sr.dir / "skills" / "trend-discovery" / "SKILL.md").write_text("trocado", encoding="utf8")
    with pytest.raises(social_research.SocialResearchError, match="sha256"):
        social_research.skill_info("trend-discovery")


def test_skill_refuses_another_commit(sr, monkeypatch):
    monkeypatch.setattr(tools, "_git", lambda *a, cwd=None: "0" * 40)
    with pytest.raises(social_research.SocialResearchError, match="commit"):
        social_research.skill_info("trend-discovery")


def test_unknown_subcommand_is_refused(capsys):
    rc, _, err = run(capsys, "run", "x")
    assert rc != 0 and "subcomando desconhecido" in err


def test_the_module_never_runs_anything_nor_opens_the_network():
    arvore = ast.parse(inspect.getsource(social_research))
    importados = {a.name.split(".")[0] for n in ast.walk(arvore) if isinstance(n, (ast.Import, ast.ImportFrom))
                  for a in n.names} | {(n.module or "").split(".")[0] for n in ast.walk(arvore) if isinstance(n, ast.ImportFrom)}
    assert not importados & {"subprocess", "socket", "urllib", "http", "requests"}
