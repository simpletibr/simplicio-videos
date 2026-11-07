"""What the documentation must say about the video-to-skill track: the README announcement the owner asked for, the counts, the
changelog, the legal table and the help texts. The numbers come from the code (tools.TOOLS, mcp_server.TOOLS), not from this file."""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from _sem_vazamento import sem_vazamento_de_pastas  # noqa: F401  (autouse: no test leaves a job folder in the real tmp)

from simplicio_video import mcp_server, tools, video_to_skill

ROOT = Path(__file__).resolve().parents[1]
README = (ROOT / "README.md").read_text(encoding="utf8")
README_PT = (ROOT / "README.pt-BR.md").read_text(encoding="utf8")
COMMIT = tools.get("video_to_skill").ref


def _section(text: str, heading: str) -> str:
    m = re.search(rf"^### {re.escape(heading)}.*$", text, re.M)
    assert m, f"no heading {heading!r}"
    end = re.search(r"^#{1,3} ", text[m.end():], re.M)
    return " ".join((text[m.end(): m.end() + end.start()] if end else text[m.end():]).split())


def _facts_block(text: str) -> str:
    """The generated `fatos` block of a README (scripts/gen_reference.py writes it from the code)."""
    m = re.search(r"<!-- BEGIN GENERATED: fatos -->\n(.*?)<!-- END GENERATED -->", text, re.S)
    assert m, "no generated `fatos` block"
    return m.group(1)


def test_the_readme_counts_come_from_the_code():
    n_tools, n_tracks = len(mcp_server.TOOLS), len(tools.TOOLS)
    assert f"| MCP tools (`video.*`) | {n_tools} |" in _facts_block(README)
    assert f"| External tracks | {n_tracks} |" in _facts_block(README)
    assert f"| Tools MCP (`video.*`) | {n_tools} |" in _facts_block(README_PT)
    assert f"| Trilhas externas | {n_tracks} |" in _facts_block(README_PT)
    assert f"| MCP server | `simplicio-video-mcp` | {n_tools} `video.*` tools |" in README
    assert f"lists {n_tools} `video.*` tools over the stdio protocol" in README
    assert "lists all thirteen tracks" in README and "all twelve" not in README
    assert f"| Servidor MCP | `simplicio-video-mcp` | {n_tools} tools `video.*`" in README_PT
    assert f"lista {n_tools} tools `video.*`" in README_PT and "31 tools `video.*`" not in README_PT and "lists 31" not in README


def test_the_capability_map_and_the_projects_table_list_the_new_track():
    assert re.search(r"^\| Video to agent skill \|[^|]*`video-to-skill`", README, re.M)
    assert "`rea-video`, `video-to-skill` |" in README
    row = next(line for line in README.splitlines() if line.startswith("| [video-to-skill](https://github.com/brenoepics/video-to-skill)"))
    assert "| MIT |" in row and "`video-to-skill`" in row and "extract" in row and "job" in row
    table = next(line for line in README.splitlines() if line.startswith("| video-to-skill |"))
    assert f"commit `{COMMIT[:7]}`" in table and "v0.3.0" in table and "none (pinned" in table
    assert "MIT" in table and "Breno Epics" in table


def test_the_readme_announces_the_feature_with_what_it_does_and_how_to_use_it():
    sec = _section(README, "video-to-skill (`video-to-skill`)")
    assert sec.startswith("[brenoepics/video-to-skill](https://github.com/brenoepics/video-to-skill) · MIT")
    for word in ("Breno Epics", "v0.3.0", COMMIT[:7], "new", "turns a video into", "agent skill", "vts-extract", "SKILL.md", "procedure.json",
                 "compile", "install", "extract", "frame-at", "clip", "merge", "check --print-downloads", "setup", "clone", "status",
                 "video.video-to-skill", "job", "video.jobs"):
        assert word in sec, f"README section: {word!r}"
    for command in ("simplicio-video video-to-skill clone", "simplicio-video video-to-skill setup", "simplicio-video video-to-skill check",
                    "simplicio-video video-to-skill extract", "simplicio-video video-to-skill compile", "simplicio-video video-to-skill install"):
        assert command in README, command


def test_the_readme_says_what_is_downloaded_by_whom_and_what_the_engine_never_does():
    sec = _section(README, "video-to-skill (`video-to-skill`)")
    for word in ("check --fix --yes", "never runs", "yourself", "sha256", "Hugging Face", "yt-dlp", "ffmpeg", "attestation",
                 "--autorizo", "does not verify", "terminal only", "sandbox", "outside the engine's guarantees", "untrusted"):
        assert word in sec, f"README section: {word!r}"


def test_the_readme_has_an_honest_verified_and_unverified_list_with_what_was_measured():
    sec = _section(README, "video-to-skill (`video-to-skill`)")
    assert "Verified" in sec and "UNVERIFIED" in sec
    verified, _, unverified = sec.partition("UNVERIFIED")
    for word in ("sha256", "tests", "offline"):
        assert word in verified.lower(), word
    for word in ("Windows", "macOS", "attestation", "sandbox"):
        assert word in unverified, f"UNVERIFIED list: {word!r}"


def test_the_portuguese_readme_announces_it_too():
    assert "video-to-skill" in README_PT and "https://github.com/brenoepics/video-to-skill" in README_PT
    sec = _section(README_PT, "video-to-skill (`video-to-skill`)")
    for word in ("MIT", "Breno Epics", COMMIT[:7], "check --fix --yes", "video.video-to-skill", "NÃO VERIFICADO", "sandbox"):
        assert word in sec, f"README.pt-BR: {word!r}"


def test_the_changelog_records_the_track_in_portuguese_with_measured_facts():
    # The track was announced under Unreleased; the 0.8.0 cut (this section) moved the notes unchanged.
    text = (ROOT / "CHANGELOG.md").read_text(encoding="utf8")
    unreleased = text.split("## 0.8.0 — ", 1)[1].split("\n## ", 1)[0]
    assert "video-to-skill" in unreleased
    entry = next(line for line in unreleased.splitlines() if "video-to-skill" in line and line.startswith("- "))
    for word in ("Breno Epics", "MIT", COMMIT[:7], "v0.3.0", "32 tools", "13 trilhas", "check --fix --yes", "UNVERIFIED", "sha256"):
        assert word in entry or word in unreleased, word


def test_the_legal_table_lists_the_track_the_engine_does_not_bundle():
    text = (ROOT / "docs" / "legal" / "terceiros.md").read_text(encoding="utf8")
    row = next(line for line in text.splitlines() if line.startswith("| video-to-skill"))
    assert "MIT" in row and COMMIT[:7] in row and "Não empacotado" in row.replace("**", "")
    assert "vts-extract" in row and "sha256" in row and "Breno Epics" in row


def test_the_resources_page_and_the_packaging_page_count_thirteen_tracks():
    assert "video-to-skill" in (ROOT / "docs" / "recursos.md").read_text(encoding="utf8")
    packaging = (ROOT / "docs" / "host" / "packaging.md").read_text(encoding="utf8")
    assert "as treze de `tools.py`" in packaging and "as doze" not in packaging


def test_agents_md_maps_the_track():
    text = (ROOT / "AGENTS.md").read_text(encoding="utf8")
    assert "simplicio-video video-to-skill" in text and "`video_to_skill.py`" in text
    line = next(line for line in text.splitlines() if line.startswith("| Transformar um vídeo em skill"))
    assert "extract" in line and "video.video-to-skill" in line


def test_the_help_of_doctor_and_the_cli_main_help_say_thirteen_and_list_the_command(capsys):
    from simplicio_video import cli

    for argv in (["doctor", "--help"],):
        with pytest.raises(SystemExit):
            cli.main(argv)
    out = capsys.readouterr().out
    assert "treze trilhas" in out and "doze trilhas" not in out
    assert "video-to-skill" in cli.MAIN_DESC


def test_the_env_vars_of_the_track_are_described_in_the_reference_generator():
    text = (ROOT / "scripts" / "gen_reference.py").read_text(encoding="utf8")
    for name in ("VIDEO_TO_SKILL_DIR", "VTS_DATA_DIR"):
        assert f'"{name}":' in text, name
    assert video_to_skill.VERSION == "0.3.0"


def test_smoke_trilhas_has_a_read_only_script_for_the_track():
    text = (ROOT / "scripts" / "smoke_trilhas.py").read_text(encoding="utf8")
    assert '"video_to_skill": ChamadaMcp("video_video_to_skill", {"args": "status"}, precisa=True)' in text


# ------------------------------------------------------------------------------------------------- review of PR #207

def test_agents_md_repo_map_counts_the_seven_recipes_of_the_trilhas_skill():
    text = (ROOT / "AGENTS.md").read_text(encoding="utf8")
    cell = next(line for line in text.splitlines() if line.startswith("| `skills/simplicio-video-trilhas/`"))
    assert "sete receitas" in cell and "seis receitas" not in cell and "vídeo vira skill" in cell
    assert "seis receitas" not in text


def _first_extract(text: str) -> int:
    return text.index("video-to-skill extract ")


def test_the_examples_create_the_parent_folder_before_the_first_extract():
    """`--out` needs an existing parent (like every other track): the examples say `mkdir -p`."""
    skill = (ROOT / "skills" / "simplicio-video-trilhas" / "SKILL.md").read_text(encoding="utf8")
    recipe = skill[skill.index("### Receita (g)"):]
    readme = _section(README, "video-to-skill (`video-to-skill`)")
    pt = _section(README_PT, "video-to-skill (`video-to-skill`)")
    for text in (recipe, README[README.index("### video-to-skill (`video-to-skill`)"):], README_PT[README_PT.index("### video-to-skill (`video-to-skill`)"):]):
        assert "mkdir -p out/excel" in text and text.index("mkdir -p out/excel") < _first_extract(text)
    assert readme and pt
    assert "a pasta-mãe precisa existir" in pt or "o `--out` precisa de uma pasta-mãe que já existe" in pt
    assert "parent folder must exist" in readme


def test_the_skill_doctor_text_says_both_pin_only_tracks_show_only_the_pin():
    skill = " ".join((ROOT / "skills" / "simplicio-video-trilhas" / "SKILL.md").read_text(encoding="utf8").split())
    assert "o video-use só mostra o pin" not in skill
    assert "o video-use e o video-to-skill só mostram o pin" in skill
    assert (ROOT / "skills" / "simplicio-video-trilhas" / "SKILL.md").read_bytes() == (
        ROOT / "src" / "simplicio_video" / "data" / "skills" / "simplicio-video-trilhas" / "SKILL.md").read_bytes()


def test_a_comment_in_test_cli_doctor_says_thirteen_tracks():
    assert "twelve external tracks" not in (ROOT / "tests" / "packaging" / "test_cli_doctor.py").read_text(encoding="utf8")


def test_the_incorporated_projects_intro_includes_the_release_binary_case():
    en = README[README.index("## Incorporated projects (external tracks)"):][:2500]
    pt = README_PT[README_PT.index("## Projetos incorporados"):][:2500] if "## Projetos incorporados" in README_PT else README_PT
    assert "a release binary checked by sha256 (video-to-skill)" in en
    assert "um binário de release conferido por sha256 (video-to-skill)" in pt


def test_the_readme_says_a_path_binary_is_trusted_by_version_only_and_lists_the_limits():
    for text, phrases in ((_section(README, "video-to-skill (`video-to-skill`)"),
                           ("trusted by its version only", "no sha256", "same user", "group-writable", "does not hash the input",
                            "proxy", "credentials")),
                          (_section(README_PT, "video-to-skill (`video-to-skill`)"),
                           ("confiado só pela versão", "sem sha256", "mesmo usuário", "gravável pelo grupo", "não calcula o hash da entrada",
                            "proxy", "credenciais"))):
        for phrase in phrases:
            assert phrase in text, phrase


def test_the_skill_recipe_and_the_help_say_the_same_limits():
    skill = " ".join((ROOT / "skills" / "simplicio-video-trilhas" / "SKILL.md").read_text(encoding="utf8").split())
    recipe = skill[skill.index("### Receita (g)"):]
    for phrase in ("mesmo usuário", "gravável pelo grupo", "não calcula o hash da entrada", "proxy", "credenciais", "só pela versão"):
        assert phrase in recipe, phrase
    usage = " ".join(video_to_skill.USAGE.split())
    for phrase in ("mesmo usuário", "não calcula o hash da entrada", "credenciais"):
        assert phrase in usage, phrase


def test_the_docs_say_a_killed_extract_leaves_its_partial_bundle():
    skill = " ".join((ROOT / "skills" / "simplicio-video-trilhas" / "SKILL.md").read_text(encoding="utf8").split())
    recipe = skill[skill.index("### Receita (g)"):]
    for text, phrase in ((_section(README, "video-to-skill (`video-to-skill`)"), "leaves its partial bundle"),
                         (_section(README_PT, "video-to-skill (`video-to-skill`)"), "deixa a pasta parcial"),
                         (recipe, "deixa a pasta parcial")):
        assert phrase in text, phrase
    assert "deixa a pasta parcial" in " ".join(video_to_skill.USAGE.split())
