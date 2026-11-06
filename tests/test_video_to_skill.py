"""`simplicio-video video-to-skill` (terminal): status, where, check, skill, extract, frame-at, clip, compile, merge and install over
a FAKE `vts-extract` (tests/_fake_vts.py). Offline: the upstream (brenoepics/video-to-skill, MIT, pinned v0.3.0) is never run here."""
from __future__ import annotations

import hashlib
import json
import os
import re
import signal
import subprocess
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
import _fake_vts as fake
from _sem_vazamento import sem_vazamento_de_pastas  # noqa: F401  (autouse: no test leaves a job folder in the real tmp)
from _orfao import SINAIS, espera, espera_pid, mata_o_que_sobrou, parada_esperada, sinaliza_no_popen, sinais_padrao, vivo  # noqa: F401

from simplicio_video import childio, cli, tools, video_to_skill as v2s

REF = "c1a1b905da6a252077ace0657e8ea49cb785e7c3"
SECRETS = ("GITHUB_TOKEN", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "HF_TOKEN", "GEMINI_API_KEY", "AWS_SECRET_ACCESS_KEY",
           "SIMPLICIO_VIDEO_DATA", "SIMPLICIO_TOOLS_DIR")
PROXY = ("HTTPS_PROXY", "HTTP_PROXY", "https_proxy", "NO_PROXY", "SSL_CERT_FILE", "REQUESTS_CA_BUNDLE")
posix_only = pytest.mark.skipif(os.name != "posix", reason="the fake extractor is a shebang script")
pytestmark = posix_only


@pytest.fixture
def env(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("SIMPLICIO_TOOLS_DIR", str(tmp_path / "tools"))
    monkeypatch.setenv("SIMPLICIO_VIDEO_DATA", str(tmp_path / "dados"))
    for var in ("VIDEO_TO_SKILL_DIR", "SIMPLICIO_VIDEO_TO_SKILL_DIR", "VTS_DATA_DIR", "SIMPLICIO_VIDEO_TO_SKILL_REF", "SIMPLICIO_MCP"):
        monkeypatch.delenv(var, raising=False)
    for var in PROXY:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(v2s, "_platform", lambda: ("Linux", "x86_64"))
    bindir = tmp_path / "pathbin"
    fake.make(bindir)
    monkeypatch.setenv("PATH", f"{bindir}{os.pathsep}/usr/bin{os.pathsep}/bin")
    checkout = tmp_path / "checkout"
    (checkout / ".git").mkdir(parents=True)
    (checkout / "references").mkdir()
    pinned = {"SKILL.md": "---\nname: video-to-skill\n---\n# Video to Skill\nbody\n",
              "references/analysis-method.md": "analysis\n", "references/ir-format.md": "ir\n", "references/verification-protocol.md": "v\n"}
    for rel, text in pinned.items():
        (checkout / rel).write_text(text, encoding="utf8")
    table = json.loads(json.dumps(v2s.PINS))
    table["files"] = {rel: hashlib.sha256(text.encode()).hexdigest() for rel, text in pinned.items()}
    monkeypatch.setattr(v2s, "PINS", table)
    monkeypatch.setenv("VIDEO_TO_SKILL_DIR", str(checkout))
    monkeypatch.setattr(tools, "_git", lambda *a, cwd=None, timeout=None: REF)
    files = tmp_path / "files"
    files.mkdir()
    video = files / "clip.mp4"
    video.write_bytes(b"not really a video")
    return SimpleNamespace(tmp=tmp_path, home=home, work=work, bindir=bindir, checkout=checkout, files=files, video=video, pinned=pinned)


def run(*args):
    return cli.main(["video-to-skill", *map(str, args)])


def out_of(capsys):
    o = capsys.readouterr()
    return o.out, o.err


def bundle(env, name="bundle", rewatch=False):
    b = env.files / name
    (b / "frames").mkdir(parents=True)
    (b / "manifest.json").write_text(json.dumps({"source": {"original": "x", "sha256": "ab" * 32}}), encoding="utf8")
    (b / "timeline.json").write_text("{}", encoding="utf8")
    if rewatch:
        (b / "rewatch").mkdir()
    return b


def ir(env, name="procedure.json", skill="excel-sum"):
    p = env.files / name
    p.write_text(json.dumps({"schema_version": 2, "skill_name": skill, "steps": []}), encoding="utf8")
    return p


def package(env, name="excel-sum"):
    d = env.files / name
    d.mkdir()
    (d / "SKILL.md").write_text(f"---\nname: {name}\n---\n", encoding="utf8")
    (d / "provenance.json").write_text(json.dumps({"skill_name": name, "history": []}), encoding="utf8")
    return d


def last(env):
    return fake.calls(env.bindir)[-1]


# ------------------------------------------------------------------------------------------------------------ help and verbs

def test_the_command_is_registered_with_help_that_says_what_runs_and_what_does_not(capsys):
    with pytest.raises(SystemExit) as e:
        cli.main(["video-to-skill", "--help"])
    assert e.value.code == 0
    out = capsys.readouterr().out
    for word in ("MIT", "Breno Epics", "https://github.com/brenoepics/video-to-skill", REF[:7], "clone", "setup", "status", "where", "check",
                 "skill", "extract", "frame-at", "clip", "compile", "merge", "install", "--autorizo", "--yes", "check --fix --yes",
                 "sandbox", "verify", "bench", "eval", "observe", "OS", "fora das garantias"):
        assert word in out, word


def test_usage_text_lists_the_verbs_the_engine_exposes_and_the_ones_it_does_not(capsys):
    assert v2s.run_video_to_skill(["--help"]) == 0
    out = capsys.readouterr().out
    assert v2s.SUBCOMMANDS == ("clone", "setup", "where", "status", "check", "skill", "extract", "frame-at", "clip", "compile",
                               "merge", "install")
    assert v2s.NOT_EXPOSED == ("sandbox", "observe", "verify", "bench", "eval")
    assert all(f"`{v}`" in out or v in out for v in v2s.NOT_EXPOSED)


@pytest.mark.parametrize("verb", ["sandbox", "observe", "verify", "bench", "eval"])
def test_the_upstream_only_verbs_are_not_exposed_and_the_binary_is_never_started(env, capsys, verb):
    with pytest.raises(v2s.VideoToSkillError, match="não é exposto|fora das garantias") as e:
        v2s.run_video_to_skill([verb, "--workspace", "/tmp/x", "--", "rm", "-rf", "/"])
    assert verb in str(e.value)
    assert fake.calls(env.bindir) == [] and fake.markers(env.bindir) == []


def test_an_unknown_subcommand_is_an_error(env):
    with pytest.raises(v2s.VideoToSkillError, match="clone|setup"):
        v2s.run_video_to_skill(["serve"])
    assert fake.calls(env.bindir) == []


# ------------------------------------------------------------------------------------------------------------ where, status

def test_where_prints_the_skill_and_where_binary_prints_the_executable(env, capsys):
    assert run("where") == 0
    assert out_of(capsys)[0].strip() == str(env.checkout.resolve() / "SKILL.md")
    assert run("where", "--binary") == 0
    assert out_of(capsys)[0].strip() == str(env.bindir / "vts-extract")


def test_where_without_a_checkout_or_binary_says_how_to_get_them(env, capsys, monkeypatch):
    monkeypatch.setenv("VIDEO_TO_SKILL_DIR", str(env.tmp / "nada"))
    monkeypatch.setenv("PATH", str(env.tmp / "vazio"))
    assert run("where") == 1 and "video-to-skill clone" in out_of(capsys)[1]
    assert run("where", "--binary") == 1 and "video-to-skill setup" in out_of(capsys)[1]


def test_status_json_is_read_only_and_describes_pin_checkout_and_binary(env, capsys):
    assert run("status", "--json") == 0
    doc = json.loads(out_of(capsys)[0])
    assert doc["track"] == "video-to-skill" and doc["license"] == "MIT" and doc["author"] == "Breno Epics"
    assert doc["pin"] == {"tag": "v0.3.0", "commit": REF, "extractor_version": "0.3.0"}
    assert doc["checkout"]["installed"] is True and doc["checkout"]["commit"] == REF and doc["checkout"]["matches_pin"] is True
    assert doc["binary"]["found"] is True and doc["binary"]["source"] == "path" and doc["binary"]["version"] == "0.3.0"
    assert doc["binary"]["verified"] == "version-only" and doc["binary"]["platform"] == "linux-x86_64"
    assert fake.subcommands(env.bindir) == [], "status only asks --version"


def test_status_without_anything_installed_never_downloads_or_clones(env, capsys, monkeypatch):
    monkeypatch.setenv("VIDEO_TO_SKILL_DIR", str(env.tmp / "nada"))
    monkeypatch.setenv("PATH", str(env.tmp / "vazio"))
    monkeypatch.setattr(v2s, "_download", lambda *a: pytest.fail("status must never download"))
    monkeypatch.setattr(tools, "install", lambda *a: pytest.fail("status must never clone"))
    assert run("status", "--json") == 0
    doc = json.loads(out_of(capsys)[0])
    assert doc["checkout"]["installed"] is False and doc["binary"]["found"] is False and doc["binary"]["source"] is None
    assert run("status") == 0
    text = out_of(capsys)[0]
    assert "video-to-skill clone" in text and "video-to-skill setup" in text


def test_status_says_when_the_platform_has_no_prebuilt_binary(env, capsys, monkeypatch):
    monkeypatch.setattr(v2s, "_platform", lambda: ("Linux", "aarch64"))
    monkeypatch.setenv("PATH", str(env.tmp / "vazio"))
    assert run("status", "--json") == 0
    doc = json.loads(out_of(capsys)[0])
    assert doc["binary"]["supported"] is False and doc["binary"]["platform"] is None


def test_status_flags_a_checkout_that_is_not_at_the_pinned_commit(env, capsys, monkeypatch):
    monkeypatch.setattr(tools, "_git", lambda *a, cwd=None, timeout=None: "f" * 40)
    run("status", "--json")
    doc = json.loads(out_of(capsys)[0])
    assert doc["checkout"]["matches_pin"] is False and doc["checkout"]["commit"] == "f" * 40


def test_global_json_flag_works_for_status_and_where_only(env, capsys):
    assert cli.main(["--json", "video-to-skill", "status"]) == 0
    assert json.loads(out_of(capsys)[0])["track"] == "video-to-skill"
    with pytest.raises(SystemExit):
        cli.main(["--json", "video-to-skill", "extract", str(env.video)])


# ----------------------------------------------------------------------------------------------------------------- check

def test_check_runs_the_extractor_check_and_shows_it_without_terminal_escapes(env, capsys):
    assert run("check") == 0
    out, _ = out_of(capsys)
    assert "ffmpeg" in out and "whisper model" in out
    assert last(env)["argv"] == ["check"]


def test_check_print_downloads_lists_what_upstream_would_fetch(env, capsys):
    assert run("check", "--print-downloads") == 0
    out, _ = out_of(capsys)
    assert "ggml-base" in out and "sha256 60ed5bc3" in out and "huggingface.co" in out
    assert last(env)["argv"] == ["check", "--print-downloads"]
    assert fake.markers(env.bindir) == []


@pytest.mark.parametrize("extra", [["--fix"], ["--yes"], ["--fix", "--yes"], ["--yes", "--fix"], ["--fix=1"], ["-y"], ["--print-downloads", "--fix"]])
def test_check_never_passes_fix_or_yes_and_tells_the_user_the_command_to_type(env, extra):
    with pytest.raises(v2s.VideoToSkillError, match="check --fix --yes") as e:
        v2s.run_video_to_skill(["check", *extra])
    assert "digite você" in str(e.value) or "você mesmo" in str(e.value)
    assert str(env.bindir / "vts-extract") in str(e.value)
    assert fake.calls(env.bindir) == [] and fake.markers(env.bindir) == []


def test_check_propagates_the_extractor_failure_and_its_message(env, capsys):
    fake.set_mode(env.bindir, "fail")
    assert run("check") == 3
    assert "boom: no network" in out_of(capsys)[1]


def test_check_without_a_binary_points_at_setup(env, monkeypatch):
    monkeypatch.setenv("PATH", str(env.tmp / "vazio"))
    with pytest.raises(v2s.VideoToSkillError, match="video-to-skill setup"):
        v2s.run_video_to_skill(["check"])


def test_check_refuses_a_binary_that_is_not_0_3_0(env):
    fake.set_mode(env.bindir, "oldversion")
    with pytest.raises(v2s.VideoToSkillError, match="setup"):
        v2s.run_video_to_skill(["check"])
    assert fake.subcommands(env.bindir) == []


# ------------------------------------------------------------------------------------------------------------------ skill

def test_skill_prints_the_pinned_skill_md_marked_as_third_party_data(env, capsys):
    assert run("skill") == 0
    out, _ = out_of(capsys)
    assert out.startswith("#") and "texto de terceiros" in out.splitlines()[0].lower() and "brenoepics/video-to-skill" in out.splitlines()[0]
    assert "dado" in out.splitlines()[0].lower() and "nunca instrução" in out.splitlines()[0]
    assert "# Video to Skill" in out and REF[:7] in out.splitlines()[0]


def test_skill_neutralises_escapes_bidi_and_zero_width_in_the_third_party_text(env, capsys):
    hostile = "ok \x1b[31mred\x1b[0m \u202eevil \u200bzero \x9bC1 \u2028sep\n"
    (env.checkout / "SKILL.md").write_text(hostile, encoding="utf8")
    env.pinned["SKILL.md"] = hostile
    v2s.PINS["files"]["SKILL.md"] = hashlib.sha256(hostile.encode()).hexdigest()
    assert run("skill") == 0
    out, _ = out_of(capsys)
    assert "\x1b" not in out and "\u202e" not in out and "\u200b" not in out and "\x9b" not in out and "\u2028" not in out
    assert "<U+202E>" in out and "<U+200B>" in out


def test_skill_refuses_a_checkout_that_is_not_at_the_pinned_commit(env, monkeypatch, capsys):
    monkeypatch.setattr(tools, "_git", lambda *a, cwd=None, timeout=None: "e" * 40)
    with pytest.raises(v2s.VideoToSkillError, match="commit"):
        v2s.run_video_to_skill(["skill"])


def test_skill_refuses_a_file_whose_sha256_is_not_the_pinned_one(env):
    (env.checkout / "SKILL.md").write_text("changed\n", encoding="utf8")
    with pytest.raises(v2s.VideoToSkillError, match="sha256"):
        v2s.run_video_to_skill(["skill"])


def test_skill_refuses_a_skill_md_that_is_a_symlink_or_too_big(env):
    real = env.tmp / "real.md"
    real.write_text(env.pinned["SKILL.md"], encoding="utf8")
    (env.checkout / "SKILL.md").unlink()
    (env.checkout / "SKILL.md").symlink_to(real)
    with pytest.raises(v2s.VideoToSkillError):
        v2s.run_video_to_skill(["skill"])
    (env.checkout / "SKILL.md").unlink()
    big = "x" * (v2s.MAX_SKILL_BYTES + 1)
    (env.checkout / "SKILL.md").write_text(big, encoding="utf8")
    v2s.PINS["files"]["SKILL.md"] = hashlib.sha256(big.encode()).hexdigest()
    with pytest.raises(v2s.VideoToSkillError):
        v2s.run_video_to_skill(["skill"])


def test_skill_takes_no_arguments_and_needs_a_checkout(env, monkeypatch):
    with pytest.raises(v2s.VideoToSkillError, match="argumentos"):
        v2s.run_video_to_skill(["skill", "extra"])
    monkeypatch.setenv("VIDEO_TO_SKILL_DIR", str(env.tmp / "nada"))
    with pytest.raises(v2s.VideoToSkillError, match="video-to-skill clone"):
        v2s.run_video_to_skill(["skill"])


# ------------------------------------------------------------------------------------------------------------------ clone

def test_clone_refuses_the_offline_mode(env, monkeypatch):
    monkeypatch.setenv("SIMPLICIO_OFFLINE", "1")
    with pytest.raises(v2s.VideoToSkillError, match="offline"):
        v2s.run_video_to_skill(["clone"])


def test_clone_installs_the_pinned_commit_through_tools_install(env, monkeypatch, capsys):
    monkeypatch.delenv("SIMPLICIO_OFFLINE", raising=False)
    seen = []
    monkeypatch.setattr(tools, "install", lambda name: seen.append(name) or str(env.checkout))
    assert run("clone") == 0
    assert seen == ["video_to_skill"] and str(env.checkout) in out_of(capsys)[0]


# ---------------------------------------------------------------------------------------------------------------- extract

def test_extract_runs_the_extractor_on_an_absolute_file_into_an_absolute_new_folder(env, capsys):
    out = env.files / "bundle"
    assert run("extract", env.video, "--out", out) == 0
    c = last(env)
    assert c["argv"] == ["extract", str(env.video), "--out", str(out)]
    assert (out / "manifest.json").is_file() and (out / "timeline.json").is_file()
    text, _ = out_of(capsys)
    assert "bundle created" in text and str(out) in text and "frame-at" in text


def test_extract_resolves_relative_paths_against_where_the_user_is(env):
    (env.work / "v.mp4").write_bytes(b"x")
    assert run("extract", "v.mp4", "--out", "b") == 0
    c = last(env)
    assert c["argv"] == ["extract", str((env.work / "v.mp4").resolve()), "--out", str((env.work / "b").resolve())]
    assert Path(c["cwd"]).resolve() != env.work.resolve(), "the extractor runs in a private folder, not where the user is"


def test_extract_writes_a_provenance_record_beside_the_bundle(env):
    out = env.files / "bundle"
    run("extract", env.video, "--out", out)
    rec = json.loads((env.files / "bundle.extract.json").read_text(encoding="utf8"))
    assert rec["schema"] == "simplicio.video-to-skill-extract/v1" and rec["extractor_version"] == "0.3.0"
    assert rec["source"] == {"kind": "file", "name": "clip.mp4", "sha256": "ab" * 32}
    assert rec["autorizo"] is False and rec["channel"] == "terminal" and rec["pin_commit"] == REF
    assert len(rec["manifest_sha256"]) == 64 and rec["bundle"] == str(out)
    assert "at" in rec and rec["engine_checked_rights"] is False


def test_extract_refuses_a_missing_file_a_folder_and_a_leading_dash(env):
    for given in (str(env.files / "nope.mp4"), str(env.files), "-x.mp4"):
        with pytest.raises(v2s.VideoToSkillError):
            v2s.run_video_to_skill(["extract", given, "--out", str(env.files / "b")])
    assert fake.calls(env.bindir) == []


def test_extract_needs_an_out_and_refuses_one_that_is_not_new_or_empty(env):
    with pytest.raises(v2s.VideoToSkillError, match="--out"):
        v2s.run_video_to_skill(["extract", str(env.video)])
    full = env.files / "full"
    full.mkdir()
    (full / "x").write_text("x")
    with pytest.raises(v2s.VideoToSkillError, match="já existe"):
        v2s.run_video_to_skill(["extract", str(env.video), "--out", str(full)])
    afile = env.files / "afile"
    afile.write_text("x")
    with pytest.raises(v2s.VideoToSkillError):
        v2s.run_video_to_skill(["extract", str(env.video), "--out", str(afile)])
    empty = env.files / "empty"
    empty.mkdir()
    assert v2s.run_video_to_skill(["extract", str(env.video), "--out", str(empty)]) == 0


def test_extract_refuses_an_existing_provenance_record_so_it_never_overwrites_one(env):
    (env.files / "b.extract.json").write_text("{}")
    with pytest.raises(v2s.VideoToSkillError, match="extract.json"):
        v2s.run_video_to_skill(["extract", str(env.video), "--out", str(env.files / "b")])
    assert fake.calls(env.bindir) == []


@pytest.mark.parametrize("where", ["/etc/b", "/usr/lib/b", "~/.ssh/b", "~/.config/b", "~/.claude/b"])
def test_extract_refuses_system_hidden_home_and_engine_folders(env, where):
    out = os.path.expanduser(where)
    with pytest.raises(v2s.VideoToSkillError, match="não grava"):
        v2s.run_video_to_skill(["extract", str(env.video), "--out", out])
    assert fake.calls(env.bindir) == []


def test_extract_refuses_the_checkout_the_tools_folder_and_the_binary_folder(env):
    for inside in (env.checkout / "b", tools.tools_dir() / "b", tools.tools_dir() / "video-to-skill-bin" / "b"):
        with pytest.raises(v2s.VideoToSkillError, match="não grava"):
            v2s.run_video_to_skill(["extract", str(env.video), "--out", str(inside)])


def test_extract_refuses_the_parent_that_does_not_exist(env):
    with pytest.raises(v2s.VideoToSkillError, match="pasta"):
        v2s.run_video_to_skill(["extract", str(env.video), "--out", str(env.files / "no" / "b")])


@pytest.mark.parametrize("words", [
    ["--out", "--autorizo"], ["--out", "-x"], ["--out=", ], ["--unknown", "1"], ["--out", "A", "--out", "B"], ["--vlm"],
])
def test_extract_refuses_swallowed_unknown_and_repeated_options(env, words):
    with pytest.raises(v2s.VideoToSkillError):
        v2s.run_video_to_skill(["extract", str(env.video), *words])
    assert fake.calls(env.bindir) == []


def test_extract_of_a_url_needs_autorizo_and_says_the_engine_does_not_verify_the_right(env):
    url = "https://example.com/watch?v=abc&token=secret"
    with pytest.raises(v2s.VideoToSkillError, match="--autorizo") as e:
        v2s.run_video_to_skill(["extract", url, "--out", str(env.files / "b")])
    assert "direito" in str(e.value) and "não verifica" in str(e.value)
    assert fake.calls(env.bindir) == []


def test_extract_of_a_url_with_autorizo_records_the_source_without_query_and_gives_the_proxy_settings(env, monkeypatch):
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy:3128")
    monkeypatch.setenv("SSL_CERT_FILE", "/etc/ssl/ca.pem")
    monkeypatch.setenv("GITHUB_TOKEN", "segredo")
    url = "https://example.com/watch?v=abc&token=secret#frag"
    assert run("extract", url, "--out", env.files / "b", "--autorizo") == 0
    c = last(env)
    assert c["argv"] == ["extract", url, "--out", str(env.files / "b")]
    assert c["env"].get("HTTPS_PROXY") == "http://proxy:3128" and c["env"].get("SSL_CERT_FILE") == "/etc/ssl/ca.pem"
    assert "GITHUB_TOKEN" not in c["env"]
    rec = json.loads((env.files / "b.extract.json").read_text(encoding="utf8"))
    assert rec["source"]["kind"] == "url" and rec["source"]["url"] == "https://example.com/watch" and "token" not in json.dumps(rec)
    assert rec["autorizo"] is True and rec["engine_checked_rights"] is False


@pytest.mark.parametrize("url", ["file:///etc/passwd", "ftp://example.com/a.mp4", "https://user:pw@example.com/a", "https://example.com/a b",
                                 "https://example.com/a\x00b", "http://", "https://" + "a" * 3000, "javascript:alert(1)"])
def test_extract_refuses_urls_that_are_not_plain_http_or_https(env, url):
    with pytest.raises(v2s.VideoToSkillError):
        v2s.run_video_to_skill(["extract", url, "--out", str(env.files / "b"), "--autorizo"])
    assert fake.calls(env.bindir) == []


def test_autorizo_with_a_local_file_is_refused_because_it_would_mean_nothing(env):
    with pytest.raises(v2s.VideoToSkillError, match="URL"):
        v2s.run_video_to_skill(["extract", str(env.video), "--out", str(env.files / "b"), "--autorizo"])


def test_a_local_extract_does_not_hand_the_proxy_settings_to_the_extractor(env, monkeypatch):
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy:3128")
    run("extract", env.video, "--out", env.files / "b")
    assert "HTTPS_PROXY" not in last(env)["env"]


def test_extract_failure_leaves_no_provenance_record_and_returns_the_exit_code(env):
    fake.set_mode(env.bindir, "failextract")
    assert run("extract", env.video, "--out", env.files / "b") == 7
    assert not (env.files / "b.extract.json").exists()


# --------------------------------------------------------------------------------------------- the child: how it is started

class _Spy:
    def __init__(self, monkeypatch):
        self.kw: list[dict] = []
        self.guarded = 0
        real = childio.guarded_child

        def spy(argv, **kw):
            self.kw.append({"argv": list(argv), **kw})
            self.guarded += 1
            return real(argv, **kw)

        monkeypatch.setattr(childio, "guarded_child", spy)


def test_the_extractor_starts_through_guarded_child_with_stdin_closed_in_its_own_session_and_a_private_folder(env, monkeypatch):
    spy = _Spy(monkeypatch)
    run("extract", env.video, "--out", env.files / "b")
    run("check")
    probes = [k for k in spy.kw if k["argv"][1:] != ["--version"]]
    assert spy.guarded >= 2 and probes
    for k in spy.kw:
        assert k["stdin"] == subprocess.DEVNULL and k["start_new_session"] is True
        assert "shell" not in k and k.get("preexec_fn") is None
        assert k["cwd"] and Path(k["cwd"]).resolve() not in (env.work.resolve(), env.home.resolve())
        assert str(k["argv"][0]) == str(env.bindir / "vts-extract")


def test_the_extractor_gets_a_minimal_environment_without_any_secret(env, monkeypatch):
    for k in SECRETS:
        monkeypatch.setenv(k, "segredo-" + k)
    monkeypatch.setenv("VTS_DATA_DIR", str(env.tmp / "vtsdata"))
    run("check")
    seen = last(env)["env"]
    assert "segredo" not in json.dumps(seen)
    assert set(seen) <= set(v2s.ENV_NAMES) | {"LC_CTYPE"}
    assert seen["PATH"] and seen["HOME"] == str(env.home) and seen["VTS_DATA_DIR"] == str(env.tmp / "vtsdata")
    assert not (set(PROXY) & set(seen))


def test_the_private_folder_of_the_child_is_removed_and_stdin_is_not_a_terminal(env, monkeypatch):
    tmpd = env.tmp / "tmpd"
    tmpd.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(tmpd))
    run("check")
    assert last(env)["tty"] is False and Path(last(env)["cwd"]).parent == tmpd
    assert list(tmpd.iterdir()) == []


def test_every_call_of_the_extractor_is_checked_for_the_pinned_version_first(env):
    run("check")
    argvs = [c["argv"] for c in fake.calls(env.bindir)]
    assert argvs[0] == ["--version"] and argvs[-1] == ["check"]


@pytest.mark.slow
def test_a_timeout_kills_the_extractor_and_everything_it_started(env, monkeypatch):
    fake.set_mode(env.bindir, "grandchild")
    monkeypatch.setitem(v2s.TIMEOUT_S, "extract", 1.0)
    with pytest.raises(v2s.VideoToSkillError, match="tempo"):
        v2s.run_video_to_skill(["extract", str(env.video), "--out", str(env.files / "b")])
    pidfile = env.bindir / "child.pid"
    pid = espera_pid(pidfile)
    try:
        assert espera(lambda: not vivo(pid), 10), "the grandchild outlived the timeout"
        assert not (env.files / "b.extract.json").exists()
    finally:
        mata_o_que_sobrou(pidfile)


def test_a_child_the_extractor_leaves_running_after_a_normal_exit_is_killed_with_its_group(env):
    fake.set_mode(env.bindir, "leaves")
    assert run("extract", env.video, "--out", env.files / "b") == 0
    pidfile = env.bindir / "child.pid"
    pid = espera_pid(pidfile)
    try:
        assert espera(lambda: not vivo(pid), 10), "what the extractor left running outlived it"
    finally:
        mata_o_que_sobrou(pidfile)


def test_output_over_the_cap_kills_the_extractor_and_fails(env, monkeypatch):
    fake.set_mode(env.bindir, "big")
    monkeypatch.setattr(v2s, "MAX_STDOUT_BYTES", 64 * 1024)
    with pytest.raises(v2s.VideoToSkillError, match="limite"):
        v2s.run_video_to_skill(["frame-at", "--bundle", str(bundle(env)), "1"])


@pytest.mark.usefixtures("sinais_padrao")
@pytest.mark.parametrize("nome", SINAIS)
def test_a_stop_signal_inside_popen_kills_the_extractor_and_its_children_and_the_private_folder_goes(env, monkeypatch, nome):
    """The kill is armed before Popen returns (childio.guarded_child): a signal that lands in the gap must not orphan the extractor."""
    fake.set_mode(env.bindir, "grandchild")
    pidfile = env.bindir / "child.pid"
    tmpd = env.tmp / "tmpd"
    tmpd.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(tmpd))
    sinaliza_no_popen(monkeypatch, pidfile, getattr(signal, nome), so_se="--out")
    exc, codigo = parada_esperada(nome)
    try:
        with pytest.raises(exc) as saida:
            v2s.run_video_to_skill(["extract", str(env.video), "--out", str(env.files / "b")])
        if codigo is not None:
            assert saida.value.code == codigo
        assert espera(lambda: not vivo(espera_pid(pidfile)), 10), "the extractor's child outlived the engine"
        assert list(tmpd.iterdir()) == [], "the private folder was left behind"
        assert not (env.files / "b.extract.json").exists()
    finally:
        mata_o_que_sobrou(pidfile)


def test_the_module_never_starts_a_process_any_other_way():
    src = Path(v2s.__file__).read_text(encoding="utf8")
    assert "subprocess.run(" not in src and "subprocess.call(" not in src and "os.system" not in src and "shell=True" not in src
    assert "guarded_child" in src


# --------------------------------------------------------------------------------------- frame-at, clip (read a bundle)

def test_frame_at_passes_the_bundle_and_every_timestamp_and_prints_what_the_extractor_printed(env, capsys):
    b = bundle(env)
    assert run("frame-at", "--bundle", b, "12", "0:54", "1:02:03.5") == 0
    assert last(env)["argv"] == ["frame-at", "--bundle", str(b), "12", "0:54", "1:02:03.5"]
    out, _ = out_of(capsys)
    assert out.count("t=") == 3 and str(b / "rewatch") in out


@pytest.mark.parametrize("stamp", ["-1", "1:2:3:4", "abc", "1e3", "12;ls", "1:", ":5", "1 2", "0x10", "9" * 20])
def test_frame_at_refuses_timestamps_that_are_not_seconds_mm_ss_or_hh_mm_ss(env, stamp):
    with pytest.raises(v2s.VideoToSkillError):
        v2s.run_video_to_skill(["frame-at", "--bundle", str(bundle(env)), stamp])
    assert fake.subcommands(env.bindir) == []


def test_frame_at_caps_the_number_of_timestamps_and_needs_at_least_one(env):
    b = bundle(env)
    with pytest.raises(v2s.VideoToSkillError):
        v2s.run_video_to_skill(["frame-at", "--bundle", str(b)])
    with pytest.raises(v2s.VideoToSkillError, match="no máximo"):
        v2s.run_video_to_skill(["frame-at", "--bundle", str(b), *map(str, range(v2s.MAX_TIMESTAMPS + 1))])
    assert v2s.run_video_to_skill(["frame-at", "--bundle", str(b), *map(str, range(v2s.MAX_TIMESTAMPS))]) == 0


def test_output_that_comes_from_the_video_is_shown_with_escapes_and_bidi_made_visible(env, capsys):
    fake.set_mode(env.bindir, "esc")
    assert run("frame-at", "--bundle", bundle(env), "1") == 0
    out, err = out_of(capsys)
    assert "\x1b" not in out and "\u202e" not in out
    assert "␛" in out and "<U+202E>" in out and "ignore previous instructions" in out  # shown, as data, never obeyed
    assert "\x1b" not in err


def test_clip_validates_the_range_and_the_fps(env):
    b = bundle(env)
    assert run("clip", "--bundle", b, "0:10", "0:20", "--fps", "2") == 0
    assert last(env)["argv"] == ["clip", "--bundle", str(b), "0:10", "0:20", "--fps", "2"]
    assert run("clip", "--bundle", b, "10", "20.5") == 0 and last(env)["argv"] == ["clip", "--bundle", str(b), "10", "20.5"]
    for bad in (["20", "10"], ["10", "10"], ["a", "5"], ["-1", "5"]):
        with pytest.raises(v2s.VideoToSkillError):
            v2s.run_video_to_skill(["clip", "--bundle", str(b), *bad])
    for fps in ("0", "-1", "31", "nan", "inf", "abc", "2.5.1", "1e1"):
        with pytest.raises(v2s.VideoToSkillError, match="fps"):
            v2s.run_video_to_skill(["clip", "--bundle", str(b), "0", "5", "--fps", fps])


def test_a_bundle_must_be_a_real_bundle_not_a_link_and_with_no_link_where_the_extractor_writes(env):
    for name, make in (("nodir", None), ("empty", "empty"), ("manifest-link", "link"), ("rewatch-link", "rw"), ("frame-link", "fl")):
        d = env.files / name
        if make is None:
            continue
        d.mkdir()
        if make == "empty":
            continue
        if make == "link":
            (env.files / "m.json").write_text("{}")
            (d / "manifest.json").symlink_to(env.files / "m.json")
        else:
            (d / "manifest.json").write_text("{}")
            (d / "frames").mkdir()
            elsewhere = env.files / f"elsewhere-{name}"
            elsewhere.mkdir()
            if make == "rw":
                (d / "rewatch").symlink_to(elsewhere)
            else:
                (d / "rewatch").mkdir()
                (d / "rewatch" / "r1").symlink_to(elsewhere)
    for name in ("nodir", "empty", "manifest-link", "rewatch-link", "frame-link"):
        with pytest.raises(v2s.VideoToSkillError):
            v2s.run_video_to_skill(["frame-at", "--bundle", str(env.files / name), "1"])
    assert fake.subcommands(env.bindir) == []


def test_a_bundle_option_that_swallowed_another_option_is_refused(env):
    for words in (["frame-at", "--bundle", "--fps", "1"], ["frame-at", "--bundle", "-x", "1"], ["frame-at", "--bundle"],
                  ["clip", "--bundle", "--fps", "0", "1"]):
        with pytest.raises(v2s.VideoToSkillError):
            v2s.run_video_to_skill(words)
    assert fake.calls(env.bindir) == []


def test_the_bundle_option_is_required_there_is_no_default_folder(env):
    for words in (["frame-at", "1"], ["clip", "0", "5"]):
        with pytest.raises(v2s.VideoToSkillError, match="--bundle"):
            v2s.run_video_to_skill(words)


# ---------------------------------------------------------------------------------------------------------------- compile

def test_compile_writes_a_new_folder_named_after_the_skill(env, capsys):
    b, p = bundle(env), ir(env)
    out = env.files / "excel-sum"
    assert run("compile", "--bundle", b, "--ir", p, "--out", out) == 0
    assert last(env)["argv"] == ["compile", "--bundle", str(b), "--ir", str(p), "--out", str(out)]
    assert (out / "SKILL.md").is_file()
    assert "install" in out_of(capsys)[0]


def test_compile_refuses_an_out_not_named_after_the_skill_or_that_exists(env):
    b, p = bundle(env), ir(env)
    with pytest.raises(v2s.VideoToSkillError, match="excel-sum"):
        v2s.run_video_to_skill(["compile", "--bundle", str(b), "--ir", str(p), "--out", str(env.files / "other-name")])
    exists = env.files / "excel-sum"
    exists.mkdir()
    with pytest.raises(v2s.VideoToSkillError, match="já existe"):
        v2s.run_video_to_skill(["compile", "--bundle", str(b), "--ir", str(p), "--out", str(exists)])
    assert fake.calls(env.bindir) == []


@pytest.mark.parametrize("body", ["not json", "[]", '{"skill_name": 5}', '{"skill_name": "Bad Name"}', '{"skill_name": "../x"}', '{"steps": []}',
                                  '{"skill_name": "a--b"}', '{"skill_name": "' + "a" * 65 + '"}'])
def test_compile_refuses_an_ir_without_a_valid_kebab_case_skill_name(env, body):
    p = env.files / "bad.json"
    p.write_text(body, encoding="utf8")
    with pytest.raises(v2s.VideoToSkillError):
        v2s.run_video_to_skill(["compile", "--bundle", str(bundle(env)), "--ir", str(p), "--out", str(env.files / "excel-sum")])
    assert fake.calls(env.bindir) == []


def test_compile_refuses_an_ir_that_is_too_big_or_not_a_regular_file(env):
    big = env.files / "big.json"
    big.write_text('{"skill_name": "excel-sum", "pad": "' + "x" * v2s.MAX_IR_BYTES + '"}', encoding="utf8")
    with pytest.raises(v2s.VideoToSkillError, match="tamanho|grande"):
        v2s.run_video_to_skill(["compile", "--bundle", str(bundle(env)), "--ir", str(big), "--out", str(env.files / "excel-sum")])
    with pytest.raises(v2s.VideoToSkillError):
        v2s.run_video_to_skill(["compile", "--bundle", str(bundle(env, "b2")), "--ir", str(env.files), "--out", str(env.files / "excel-sum")])


def test_compile_needs_the_three_options(env):
    for words in (["--ir", "x", "--out", "y"], ["--bundle", "x", "--out", "y"], ["--bundle", "x", "--ir", "y"]):
        with pytest.raises(v2s.VideoToSkillError):
            v2s.run_video_to_skill(["compile", *words])


# ------------------------------------------------------------------------------------------------------------------ merge

def test_merge_dry_run_shows_the_plan_and_writes_nothing(env, capsys):
    pkg, b, p = package(env), bundle(env), ir(env, "new.json")
    assert run("merge", "--skill", pkg, "--ir", p, "--bundle", b, "--dry-run") == 0
    assert last(env)["argv"] == ["merge", "--skill", str(pkg), "--ir", str(p), "--bundle", str(b), "--dry-run"]
    assert "fold plan" in out_of(capsys)[0] and not (env.files / "merged").exists()


def test_a_real_merge_needs_an_explicit_new_out_named_after_the_skill(env, capsys):
    pkg, b, p = package(env), bundle(env), ir(env, "new.json")
    with pytest.raises(v2s.VideoToSkillError, match="--out"):
        v2s.run_video_to_skill(["merge", "--skill", str(pkg), "--ir", str(p), "--bundle", str(b)])
    with pytest.raises(v2s.VideoToSkillError, match="excel-sum"):
        v2s.run_video_to_skill(["merge", "--skill", str(pkg), "--ir", str(p), "--bundle", str(b), "--out", str(env.files / "merged-x")])
    out = env.files / "merged" / "excel-sum"
    out.parent.mkdir()
    assert run("merge", "--skill", pkg, "--ir", p, "--bundle", b, "--out", out) == 0
    assert last(env)["argv"] == ["merge", "--skill", str(pkg), "--ir", str(p), "--bundle", str(b), "--out", str(out)]
    assert (out / "SKILL.md").is_file()
    with pytest.raises(v2s.VideoToSkillError, match="já existe"):
        v2s.run_video_to_skill(["merge", "--skill", str(pkg), "--ir", str(p), "--bundle", str(b), "--out", str(out)])


def test_merge_refuses_a_skill_folder_that_is_not_a_generated_package(env):
    b, p = bundle(env), ir(env, "new.json")
    plain = env.files / "plain"
    plain.mkdir()
    with pytest.raises(v2s.VideoToSkillError, match="provenance"):
        v2s.run_video_to_skill(["merge", "--skill", str(plain), "--ir", str(p), "--bundle", str(b), "--dry-run"])
    pkg = package(env)
    (pkg / "provenance.json").unlink()
    (env.files / "p.json").write_text("{}")
    (pkg / "provenance.json").symlink_to(env.files / "p.json")
    with pytest.raises(v2s.VideoToSkillError):
        v2s.run_video_to_skill(["merge", "--skill", str(pkg), "--ir", str(p), "--bundle", str(b), "--dry-run"])


# ---------------------------------------------------------------------------------------------------------------- install

def test_install_without_yes_prints_the_plan_through_dry_run_and_writes_nothing(env, capsys):
    pkg = package(env)
    assert run("install", "--package", pkg) == 0
    assert [c["argv"] for c in fake.calls(env.bindir) if c["argv"][0] == "install"] == [["install", "--package", str(pkg), "--dry-run"]]
    out, _ = out_of(capsys)
    assert "plan" in out and "nada foi gravado" in out and "--yes" in out
    assert fake.markers(env.bindir) == []


def test_install_with_yes_shows_the_plan_first_warns_and_then_applies(env, capsys):
    pkg = package(env)
    assert run("install", "--package", pkg, "--yes") == 0
    argvs = [c["argv"] for c in fake.calls(env.bindir) if c["argv"][0] == "install"]
    assert argvs == [["install", "--package", str(pkg), "--dry-run"], ["install", "--package", str(pkg), "--yes"]]
    out, _ = out_of(capsys)
    assert out.index("plan") < out.index("installed") and "todos os agentes" in out
    assert fake.markers(env.bindir) == ["INSTALLED"]


def test_install_passes_scope_only_and_force_after_checking_them(env):
    pkg = package(env)
    assert run("install", "--package", pkg, "--scope", "project", "--only", "claude,codex", "--force", "--yes") == 0
    apply = [c for c in fake.calls(env.bindir) if c["argv"][:1] == ["install"]][-1]
    assert apply["argv"] == ["install", "--package", str(pkg), "--scope", "project", "--only", "claude,codex", "--force", "--yes"]
    assert Path(apply["cwd"]).resolve() == env.work.resolve(), "--scope project installs into the folder the user is in"
    for bad in (["--scope", "everywhere"], ["--only", "claude;rm"], ["--only", ""], ["--only", "a,,b"], ["--only", "-x"]):
        with pytest.raises(v2s.VideoToSkillError):
            v2s.run_video_to_skill(["install", "--package", str(pkg), *bad])


def test_install_is_terminal_only_even_with_yes(env, monkeypatch):
    monkeypatch.setenv("SIMPLICIO_MCP", "1")
    with pytest.raises(v2s.VideoToSkillError, match="terminal"):
        v2s.run_video_to_skill(["install", "--package", str(package(env)), "--yes"])
    assert fake.calls(env.bindir) == []


def test_install_refuses_a_folder_that_is_not_a_compiled_package(env):
    plain = env.files / "plain"
    plain.mkdir()
    with pytest.raises(v2s.VideoToSkillError, match="SKILL.md"):
        v2s.run_video_to_skill(["install", "--package", str(plain), "--yes"])
    assert fake.calls(env.bindir) == []


def test_install_needs_the_package_option(env):
    with pytest.raises(v2s.VideoToSkillError, match="--package"):
        v2s.run_video_to_skill(["install", "--yes"])


def test_the_help_of_install_warns_that_it_writes_into_every_agents_skills_folder(capsys):
    v2s.run_video_to_skill(["--help"])
    out = capsys.readouterr().out
    assert "todos os agentes" in out and "~/.agents/skills" in out and "--yes" in out


# ----------------------------------------------------------------------------------------------------------------- misc

def test_visible_makes_controls_bidi_and_zero_width_visible_and_keeps_text():
    s = "a\x1b[0m\tb\n\u202ec\u200bd\x7f\x9b\u2028\ufeff\U000e0041e"
    out = v2s.visivel(s)
    assert out.startswith("a␛[0m\tb\n") and "<U+202E>" in out and "<U+200B>" in out and "␡" in out and "<U+009B>" in out
    assert "<U+2028>" in out and "<U+FEFF>" in out and "<U+E0041>" in out and out.endswith("e")
    assert v2s.visivel("plain text ção") == "plain text ção"


def test_the_clean_text_for_an_agent_drops_the_same_characters():
    assert v2s.limpa_mcp("a\x1b[0mb\u202ec\u200bd\ne\r\nf") == "a[0mbcd\ne\nf"


def test_doc_of_the_module_says_what_is_not_covered_by_the_engines_guarantees():
    doc = (v2s.__doc__ or "").lower()
    for word in ("sandbox", "verify", "outside", "check --fix --yes", "sha256", "mit"):
        assert word in doc, word


def test_the_pins_file_ships_beside_the_other_package_data():
    assert (Path(v2s.__file__).parent / "data" / "video_to_skill" / "pins.json").is_file()


# ------------------------------------------------------------------------------------------------- review of PR #207

@pytest.mark.slow
def test_output_that_floods_while_the_extractor_keeps_running_is_cut_in_the_loop_not_by_the_timeout(env, monkeypatch):
    """The in-loop cap: the extractor prints past the cap and goes on running, so only the loop can end it (a timeout would say `tempo`)."""
    fake.set_mode(env.bindir, "flood")
    monkeypatch.setattr(v2s, "MAX_STDOUT_BYTES", 64 * 1024)
    monkeypatch.setitem(v2s.TIMEOUT_S, "frame-at", 6.0)
    started = time.monotonic()
    with pytest.raises(v2s.VideoToSkillError, match="limite"):
        v2s.run_video_to_skill(["frame-at", "--bundle", str(bundle(env)), "1"])
    assert time.monotonic() - started < 5.0


@pytest.mark.parametrize("name", ["Bad_Name", "BAD", "-a", "a-", "a--b", "a_b", "a b", "a" * 65, "é"])
def test_compile_refuses_a_skill_name_that_is_not_kebab_case_even_when_the_out_folder_carries_it(env, name):
    """The out folder named after the skill is a second guard; the kebab-case check must hold on its own."""
    p = env.files / "bad.json"
    p.write_text(json.dumps({"skill_name": name}), encoding="utf8")
    with pytest.raises(v2s.VideoToSkillError, match="kebab"):
        v2s.run_video_to_skill(["compile", "--bundle", str(bundle(env)), "--ir", str(p), "--out", str(env.files / name)])
    assert fake.calls(env.bindir) == []


def test_frame_at_and_clip_do_not_write_into_a_bundle_in_a_forbidden_place(env):
    """A folder that already has a manifest.json is not a licence to write rewatch/ anywhere: the output rule applies to the bundle too."""
    hidden = env.home / ".config" / "bundle"
    (hidden / "frames").mkdir(parents=True)
    (hidden / "manifest.json").write_text("{}", encoding="utf8")
    inside = tools.tools_dir() / "bundle"
    inside.mkdir(parents=True)
    (inside / "manifest.json").write_text("{}", encoding="utf8")
    for where in (hidden, inside, env.checkout):
        for words in (["frame-at", "--bundle", str(where), "1"], ["clip", "--bundle", str(where), "0", "5"]):
            with pytest.raises(v2s.VideoToSkillError, match="não grava"):
                v2s.run_video_to_skill(words)
    assert fake.subcommands(env.bindir) == []


def test_install_with_yes_shows_the_plan_once(env, capsys):
    pkg = package(env)
    assert run("install", "--package", pkg, "--yes") == 0
    out, _ = out_of(capsys)
    assert out.count("plan: would install") == 1 and "installed" in out
    argvs = [c["argv"] for c in fake.calls(env.bindir) if c["argv"][0] == "install"]
    assert argvs == [["install", "--package", str(pkg), "--dry-run"], ["install", "--package", str(pkg), "--yes"]], "the dry run still runs first"


def test_install_with_yes_does_not_apply_when_the_dry_run_fails(env):
    fake.set_mode(env.bindir, "faildry")
    assert run("install", "--package", package(env), "--yes") == 4
    assert fake.markers(env.bindir) == []


def test_install_with_yes_prints_the_plan_before_the_extractor_writes_anything(env, monkeypatch):
    """The real extractor writes first and prints its plan after (the fake mirrors that): the user must see the plan from the
    --dry-run BEFORE the apply starts. Ordered by a clock shared with the fake: when the engine printed the plan vs its first write."""
    printed = []
    real = v2s._stream_out

    def spy(text):
        if "plan: would install" in text:
            printed.append(time.monotonic_ns())
        real(text)

    monkeypatch.setattr(v2s, "_stream_out", spy)
    assert run("install", "--package", package(env), "--yes") == 0
    ev = fake.events(env.bindir)
    assert printed and "write" in ev and "dry-run" in ev
    assert ev["dry-run"] < printed[0] < ev["write"], "the plan must be on the screen before the first write"


def test_install_with_yes_does_not_repeat_the_plan_and_shows_what_the_apply_adds(env, capsys):
    assert run("install", "--package", package(env), "--yes") == 0
    out, _ = out_of(capsys)
    assert out.count("plan: would install") == 1 and out.count("skill:     excel-sum") == 1
    assert out.count("installed") == 1, "the line the apply adds is shown once"
    assert out.index("plan: would install") < out.index("ATENÇÃO") < out.index("installed")


def test_the_warning_before_an_install_with_yes_does_not_promise_a_plan_that_is_not_there(env, capsys):
    run("install", "--package", package(env), "--yes")
    out, _ = out_of(capsys)
    warning = next(line for line in out.splitlines() if line.startswith("ATENÇÃO"))
    assert "plano abaixo" not in warning and "plano acima" in warning


@pytest.mark.parametrize("words", [["clone", "--upload-pack=/tmp/x"], ["clone", "-x"], ["clone", "--help-me"], ["setup", "-x"], ["clone", ""],
                                   ["setup", ""]])
def test_clone_and_setup_refuse_arguments_that_look_like_options(env, monkeypatch, words):
    monkeypatch.delenv("SIMPLICIO_OFFLINE", raising=False)
    monkeypatch.setattr(tools, "install", lambda name: pytest.fail("git must not be started"))
    with pytest.raises(v2s.VideoToSkillError, match="opç|argumento"):
        v2s.run_video_to_skill(words)


def test_clone_turns_an_os_error_of_the_install_into_a_clean_refusal(env, monkeypatch):
    monkeypatch.delenv("SIMPLICIO_OFFLINE", raising=False)

    def boom(name):
        raise FileNotFoundError(2, "No such file or directory", "git")

    monkeypatch.setattr(tools, "install", boom)
    with pytest.raises(v2s.VideoToSkillError, match="clone"):
        v2s.run_video_to_skill(["clone"])


@pytest.mark.parametrize("name", ["b\nx", "b\rx", "b\x1bx", "b\x7fx"])
def test_a_path_with_a_control_character_is_refused(env, name):
    with pytest.raises(v2s.VideoToSkillError):
        v2s.run_video_to_skill(["extract", str(env.video), "--out", str(env.files / name)])
    assert fake.calls(env.bindir) == []


@pytest.mark.parametrize("verb", v2s.SUBCOMMANDS)
def test_each_verb_has_its_own_help(verb, capsys, env):
    assert cli.main(["video-to-skill", verb, "--help"]) == 0
    out = capsys.readouterr().out
    first = out.splitlines()[0]
    assert f"video-to-skill {verb}" in first
    assert not [v for v in v2s.SUBCOMMANDS if v != verb and re.search(rf"video-to-skill {re.escape(v)}\b", first)]
    for option in v2s._SPEC.get(verb, ({}, 0, 0))[0]:
        assert option in out, (verb, option)
    assert len(out.splitlines()) < len(v2s.USAGE.splitlines()) / 2, "not the general help"
    assert fake.calls(env.bindir) == []
    assert cli.main(["video-to-skill", verb, "-h"]) == 0 and capsys.readouterr().out == out


def test_help_after_other_arguments_is_still_the_verb_help_and_runs_nothing(env, capsys):
    assert cli.main(["video-to-skill", "extract", str(env.video), "--out", str(env.files / "b"), "--help"]) == 0
    assert "--autorizo" in capsys.readouterr().out and fake.calls(env.bindir) == [] and not (env.files / "b").exists()


def test_the_provenance_of_a_job_started_over_mcp_says_so(env, monkeypatch):
    monkeypatch.setenv("SIMPLICIO_JOB_ORIGIN", "mcp")
    assert run("extract", env.video, "--out", env.files / "b") == 0
    rec = json.loads((env.files / "b.extract.json").read_text(encoding="utf8"))
    assert rec["channel"] == "job" and rec["submitted_via"] == "mcp"


@pytest.mark.parametrize("value", ["", "evil", "MCP", "mcp\n", "terminal"])
def test_only_a_known_job_origin_is_recorded(env, monkeypatch, value):
    monkeypatch.setenv("SIMPLICIO_JOB_ORIGIN", value)
    assert run("extract", env.video, "--out", env.files / "b") == 0
    rec = json.loads((env.files / "b.extract.json").read_text(encoding="utf8"))
    assert (rec["channel"], rec.get("submitted_via")) == (("job", "terminal") if value == "terminal" else ("terminal", None))
