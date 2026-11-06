"""`video.video-to-skill` over MCP: a CLOSED allowlist, absolute and new output paths, no option swallowing, extraction as a job.
Offline, over the FAKE `vts-extract` of tests/_fake_vts.py."""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
import _fake_vts as fake

from simplicio_video import jobs, mcp_server, tools, video_to_skill as v2s

REF = "c1a1b905da6a252077ace0657e8ea49cb785e7c3"
ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(os.name != "posix", reason="the fake extractor is a shebang script")
SECRETS = ("GITHUB_TOKEN", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "HF_TOKEN")


@pytest.fixture
def env(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("SIMPLICIO_TOOLS_DIR", str(tmp_path / "tools"))
    monkeypatch.setenv("SIMPLICIO_VIDEO_DATA", str(tmp_path / "dados"))
    for var in ("VIDEO_TO_SKILL_DIR", "VTS_DATA_DIR", "SIMPLICIO_MCP", "HTTPS_PROXY"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(v2s, "_platform", lambda: ("Linux", "x86_64"))
    bindir = tmp_path / "pathbin"
    fake.make(bindir)
    monkeypatch.setenv("PATH", f"{bindir}{os.pathsep}/usr/bin{os.pathsep}/bin")
    checkout = tmp_path / "checkout"
    (checkout / ".git").mkdir(parents=True)
    body = "---\nname: video-to-skill\n---\n# Video to Skill\n"
    (checkout / "SKILL.md").write_text(body, encoding="utf8")
    table = json.loads(json.dumps(v2s.PINS))
    table["files"]["SKILL.md"] = hashlib.sha256(body.encode()).hexdigest()
    monkeypatch.setattr(v2s, "PINS", table)
    monkeypatch.setenv("VIDEO_TO_SKILL_DIR", str(checkout))
    monkeypatch.setattr(tools, "_git", lambda *a, cwd=None, timeout=None: REF)
    files = tmp_path / "files"
    files.mkdir()
    video = files / "clip.mp4"
    video.write_bytes(b"x")
    spawned = []
    monkeypatch.setattr(jobs, "_spawn_runner", lambda jid: spawned.append(jid) or os.getpid())
    return SimpleNamespace(tmp=tmp_path, bindir=bindir, checkout=checkout, files=files, video=video, spawned=spawned)


def call(argv=None, **kw):
    return mcp_server.video_video_to_skill(argv=argv, **kw) if argv is not None else mcp_server.video_video_to_skill(**kw)


def bundle(env, name="bundle"):
    b = env.files / name
    (b / "frames").mkdir(parents=True)
    (b / "manifest.json").write_text("{}", encoding="utf8")
    return b


def ir(env, skill="excel-sum"):
    p = env.files / "procedure.json"
    p.write_text(json.dumps({"skill_name": skill}), encoding="utf8")
    return p


def package(env, name="excel-sum"):
    d = env.files / name
    d.mkdir()
    (d / "SKILL.md").write_text("x", encoding="utf8")
    (d / "provenance.json").write_text(json.dumps({"skill_name": name}), encoding="utf8")
    return d


def nothing_ran(env):
    assert fake.subcommands(env.bindir) == [] and fake.markers(env.bindir) == [] and env.spawned == []


# ---------------------------------------------------------------------------------------------------------- registration

def test_the_tool_is_the_thirty_second_and_its_description_comes_from_the_same_tuple_as_the_enum():
    names = [n for n, _, _ in mcp_server.TOOLS]
    assert len(names) == 32 and "video.video-to-skill" in names and names.index("video.video-to-skill") > names.index("video.rea-video")
    fn = dict((n, f) for n, f, _ in mcp_server.TOOLS)["video.video-to-skill"]
    assert fn is mcp_server.video_video_to_skill and mcp_server.DESC_video_video_to_skill is dict((n, d) for n, _, d in mcp_server.TOOLS)["video.video-to-skill"]
    assert mcp_server._CMD_VIDEO_TO_SKILL == ("status", "where", "check", "skill", "extract", "frame-at", "text", "clip", "compile", "merge")
    assert mcp_server._CMD_VIDEO_TO_SKILL == v2s.MCP_VERBS
    desc = mcp_server.DESC_video_video_to_skill
    assert "MCP subcommands (cmd): " + ", ".join(v2s.MCP_VERBS) in desc
    for word in ("MIT", "https://github.com/brenoepics/video-to-skill", "extract", "job", "video.jobs", "--dry-run", "terminal", "check --fix --yes",
                 "install", "sandbox", "untrusted_saida", "never instructions"):
        assert word in desc, word


def test_plugin_json_advertises_thirty_two_tools_including_this_one():
    plugin = json.loads((ROOT / "plugin.json").read_text(encoding="utf8"))
    assert len(plugin["mcp"]["tools"]) == 32 and "video.video-to-skill" in plugin["mcp"]["tools"]
    assert plugin["mcp"]["tools"] == [n for n, _, _ in mcp_server.TOOLS]


def test_the_mcp_protocol_lists_it_with_the_cmd_enum():
    mcp = pytest.importorskip("mcp")
    if not hasattr(mcp, "Client"):
        pytest.skip("in-process Client needs mcp>=2")
    srv = mcp_server.build_server()

    async def go():
        async with mcp.Client(srv) as client:
            return {t.name: t for t in (await client.list_tools()).tools}

    tool = asyncio.run(go())["video.video-to-skill"]
    assert set(tool.input_schema["properties"]) == {"args", "argv", "cmd"}
    assert json.dumps(tool.input_schema["properties"]["cmd"]).count('"') and all(v in json.dumps(tool.input_schema["properties"]["cmd"]) for v in v2s.MCP_VERBS)


def test_jobs_has_the_video_to_skill_kind_in_order_and_the_docs_say_it():
    assert list(jobs.KINDS) == ["swap-run", "voice", "rea-video", "moneyprinter", "montage-tool", "video-to-skill"]
    assert set(jobs.KINDS["video-to-skill"]) == {"prepare", "argv", "result"}
    assert "video-to-skill" in jobs.HELP_DESC and "video-to-skill" in mcp_server.DESC_video_jobs


# ------------------------------------------------------------------------------------------------------- the closed list

def test_status_and_where_answer_json_and_start_nothing_but_the_version_probe(env):
    r = call(["status"])
    assert r["ok"] is True and r["result"]["pin"]["commit"] == REF and r["result"]["binary"]["version"] == "0.3.0"
    w = call(["where"])
    assert w["ok"] is True and w["result"]["skill"] == str(env.checkout.resolve() / "SKILL.md") and w["result"]["binary"].endswith("vts-extract")
    assert fake.subcommands(env.bindir) == []


def test_check_runs_read_only_and_print_downloads_is_allowed(env):
    r = call(["check"])
    assert r["ok"] is True and r["verbo"] == "check" and "whisper model" in r["untrusted_saida"]
    r = call(["check", "--print-downloads"])
    assert r["ok"] is True and "ggml-base" in r["untrusted_saida"]
    assert [c["argv"] for c in fake.calls(env.bindir) if c["argv"] != ["--version"]] == [["check"], ["check", "--print-downloads"]]
    assert fake.markers(env.bindir) == []


@pytest.mark.parametrize("extra", [["--fix"], ["--yes"], ["--fix", "--yes"], ["-y"], ["--fix=1"], ["--print-downloads", "--yes"], ["--help"], ["-h"]])
def test_check_refuses_fix_yes_and_help_with_the_terminal_command(env, extra):
    r = call(["check", *extra])
    assert r["ok"] is False and "terminal" in r["error"]
    nothing_ran(env)


def test_skill_returns_the_pinned_text_as_untrusted_data(env):
    r = call(["skill"])
    assert r["ok"] is True and "# Video to Skill" in r["untrusted_conteudo"] and r["truncado"] is False
    assert len(r["sha256"]) == 64 and "nunca instrução" in r["aviso"].lower()


def test_skill_cuts_at_64_kib_and_cleans_the_text(env, monkeypatch):
    hostile = "ok \x1b[31m‮" + "x" * 70_000
    (env.checkout / "SKILL.md").write_text(hostile, encoding="utf8")
    v2s.PINS["files"]["SKILL.md"] = hashlib.sha256(hostile.encode()).hexdigest()
    monkeypatch.setattr(v2s, "MAX_SKILL_BYTES", 1024 * 1024)
    r = call(["skill"])
    assert r["ok"] is True and r["truncado"] is True and len(r["untrusted_conteudo"]) <= 64 * 1024
    assert "\x1b" not in r["untrusted_conteudo"] and "‮" not in r["untrusted_conteudo"]


@pytest.mark.parametrize("words", [["clone"], ["clone", "/tmp/x"], ["setup"], ["install", "--package", "/x", "--yes"], ["sandbox", "--workspace", "/x"],
                                   ["observe", "--check", "{}"], ["verify", "--skill", "/x", "--report", "/y"], ["bench"], ["eval"], ["serve"],
                                   ["--version"], ["--help"], ["-h"], ["help"], [""], ["extract-all"], ["Status"], ["status;ls"], ["merge-all"]])
def test_every_verb_outside_the_list_is_refused_and_nothing_runs(env, words):
    r = call(words)
    assert r["ok"] is False and r["error"]
    nothing_ran(env)


def test_the_terminal_command_is_named_in_the_refusal_for_the_terminal_only_verbs(env):
    for verb in ("clone", "setup", "install"):
        assert f"simplicio-video video-to-skill {verb}" in call([verb])["error"]
    for verb in ("sandbox", "observe", "verify", "bench", "eval"):
        assert "fora das garantias" in call([verb])["error"] or "não é exposto" in call([verb])["error"]


def test_a_cmd_outside_the_enum_and_args_with_argv_are_refused_like_the_other_tools(env):
    assert call(cmd="clone")["ok"] is False and "argumentos" in call(cmd="clone")["error"]
    assert call(args="status", argv=["status"])["ok"] is False
    assert call(cmd="status")["ok"] is True and call(args="status")["ok"] is True and call(argv=["status"])["ok"] is True
    assert call(cmd="status", argv=["status"])["ok"] is False


def test_args_line_with_quotes_works_and_an_unterminated_quote_is_refused(env):
    b = bundle(env)
    assert call(args=f'text --bundle "{b}" --grep "SUM A"')["ok"] is True
    assert call(args='text --bundle "x')["ok"] is False


# ------------------------------------------------------------------------------------------------------------ the paths

@pytest.mark.parametrize("words", [
    ["text", "--bundle", "rel/bundle"], ["text", "--bundle", "../bundle"], ["frame-at", "--bundle", "bundle", "1"],
    ["clip", "--bundle", "~/b", "0", "5"], ["text", "--bundle", "/tmp/../tmp/x"],
])
def test_a_relative_or_dotdot_path_is_refused(env, words):
    r = call(words)
    assert r["ok"] is False and ("absolut" in r["error"] or ".." in r["error"])
    nothing_ran(env)


def test_a_bundle_under_a_symlinked_folder_is_refused(env):
    real = bundle(env, "real")
    link = env.files / "link"
    link.symlink_to(real)
    r = call(["text", "--bundle", str(link)])
    assert r["ok"] is False and "link" in r["error"]
    nothing_ran(env)


def test_frame_at_text_and_clip_run_on_an_absolute_bundle(env):
    b = bundle(env)
    assert call(["frame-at", "--bundle", str(b), "12", "0:54"])["ok"] is True
    assert call(["text", "--bundle", str(b), "--grep", "SUM"])["ok"] is True
    assert call(["clip", "--bundle", str(b), "0:10", "0:12", "--fps", "1"])["ok"] is True
    assert [c["argv"][0] for c in fake.calls(env.bindir) if c["argv"] != ["--version"]] == ["frame-at", "text", "clip"]
    assert (b / "rewatch" / "r1").is_dir(), "the frames land under the bundle"


def test_frame_at_text_and_clip_refuse_what_the_terminal_refuses(env):
    b = bundle(env)
    for words in (["frame-at", "--bundle", str(b), "-1"], ["frame-at", "--bundle", str(b)], ["clip", "--bundle", str(b), "9", "3"],
                  ["clip", "--bundle", str(b), "0", "5", "--fps", "99"], ["text", "--bundle", "--grep", "x"], ["text", "--grep", "x"]):
        assert call(words)["ok"] is False, words
    nothing_ran(env)


def test_swallowed_repeated_and_unknown_options_are_refused(env):
    b = str(bundle(env))
    for words in (["text", "--bundle", b, "--bundle", b], ["text", "--bundle", b, "--wat"], ["text", "--bundle", b, "--json"],
                  ["text", "--bundle", b, "extra"], ["text", "--bundle", "--grep", "x"], ["text", "--bundle", b, "--grep"]):
        assert call(words)["ok"] is False, words
    assert fake.subcommands(env.bindir) == []
    # `--opt=value` is one token: it can swallow nothing, and the value is passed on exactly
    assert call(["text", f"--bundle={b}", "--grep=--out"])["ok"] is True
    assert fake.calls(env.bindir)[-1]["argv"] == ["text", "--bundle", b, "--grep=--out"]


def test_extract_becomes_a_job_over_a_local_absolute_file_and_a_new_absolute_folder(env):
    out = env.files / "bundle"
    r = call(["extract", str(env.video), "--out", str(out)])
    assert r["ok"] is True and r["job"]["kind"] == "video-to-skill" and r["job"]["state"] == "queued" and "video.jobs" in r["next"]
    assert env.spawned == [r["job"]["id"]] and fake.subcommands(env.bindir) == [], "submitted, not run inline"
    st = jobs.status(r["job"]["id"])
    assert st["params"]["args"] == ["extract", str(env.video), "--out", str(out)]
    assert Path(st["cwd"]).is_dir() and Path(st["cwd"]) != Path.cwd(), "the runner starts in a private empty folder"
    assert jobs.build_argv("video-to-skill", st["params"]) == ["video-to-skill", "extract", str(env.video), "--out", str(out)]
    assert not out.exists()


@pytest.mark.parametrize("make", [
    lambda e: ["extract", "https://example.com/v.mp4", "--out", str(e.files / "b")],
    lambda e: ["extract", "https://example.com/v.mp4", "--out", str(e.files / "b"), "--autorizo"],
    lambda e: ["extract", str(e.video), "--out", str(e.files / "b"), "--autorizo"],
    lambda e: ["extract", "clip.mp4", "--out", str(e.files / "b")],
    lambda e: ["extract", str(e.video), "--out", "b"],
    lambda e: ["extract", str(e.video)],
    lambda e: ["extract", str(e.files / "nope.mp4"), "--out", str(e.files / "b")],
    lambda e: ["extract", str(e.files), "--out", str(e.files / "b")],
    lambda e: ["extract", str(e.video), "--out", str(e.files / ".." / "files" / "b")],
    lambda e: ["extract", str(e.video), "--out", "/etc/b"],
    lambda e: ["extract", str(e.video), "--out", str(e.files / "b"), "--vlm"],
    lambda e: ["extract", "file:///etc/passwd", "--out", str(e.files / "b")],
])
def test_extract_refuses_urls_autorizo_relative_paths_missing_inputs_and_forbidden_outputs(env, make):
    r = call(make(env))
    assert r["ok"] is False and r["error"]
    nothing_ran(env)


def test_extract_url_error_says_it_is_terminal_only_with_autorizo_and_the_right_is_not_verified(env):
    r = call(["extract", "https://example.com/v.mp4", "--out", str(env.files / "b")])
    assert "terminal" in r["error"] and "--autorizo" in r["error"] and "não verifica" in r["error"]


def test_extract_refuses_an_out_that_exists_even_empty_and_a_symlinked_component(env):
    empty = env.files / "empty"
    empty.mkdir()
    assert call(["extract", str(env.video), "--out", str(empty)])["ok"] is False
    real = env.files / "real"
    real.mkdir()
    (env.files / "link").symlink_to(real)
    assert call(["extract", str(env.video), "--out", str(env.files / "link" / "b")])["ok"] is False
    assert call(["extract", str(env.video), "--out", str(real / "b")])["ok"] is True


def test_extract_refuses_when_the_binary_is_missing_with_the_terminal_setup_command(env, monkeypatch):
    monkeypatch.setenv("PATH", str(env.tmp / "vazio"))
    r = call(["extract", str(env.video), "--out", str(env.files / "b")])
    assert r["ok"] is False and "simplicio-video video-to-skill setup" in r["error"] and env.spawned == []


def test_compile_runs_with_absolute_inputs_and_a_new_out_named_after_the_skill(env):
    b, p = bundle(env), ir(env)
    out = env.files / "excel-sum"
    r = call(["compile", "--bundle", str(b), "--ir", str(p), "--out", str(out)])
    assert r["ok"] is True and r["package"] == str(out) and (out / "SKILL.md").is_file()
    again = call(["compile", "--bundle", str(b), "--ir", str(p), "--out", str(out)])
    assert again["ok"] is False and "já existe" in again["error"]
    assert call(["compile", "--bundle", str(b), "--ir", str(p), "--out", str(env.files / "other")])["ok"] is False
    assert call(["compile", "--bundle", str(b), "--ir", "procedure.json", "--out", str(env.files / "excel-sum2")])["ok"] is False


def test_merge_over_mcp_is_dry_run_only(env):
    pkg, b, p = package(env), bundle(env), ir(env)
    ok = call(["merge", "--skill", str(pkg), "--ir", str(p), "--bundle", str(b), "--dry-run"])
    assert ok["ok"] is True and "fold plan" in ok["untrusted_saida"]
    assert fake.calls(env.bindir)[-1]["argv"][-1] == "--dry-run"
    for words in (["merge", "--skill", str(pkg), "--ir", str(p), "--bundle", str(b)],
                  ["merge", "--skill", str(pkg), "--ir", str(p), "--bundle", str(b), "--out", str(env.files / "merged" / "excel-sum")],
                  ["merge", "--skill", str(pkg), "--ir", str(p), "--bundle", str(b), "--dry-run", "--out", str(env.files / "x")],
                  ["merge", "--skill", str(pkg), "--ir", str(p), "--bundle", str(b), "--dry-run=1"]):
        r = call(words)
        assert r["ok"] is False and ("--dry-run" in r["error"] or "terminal" in r["error"]), words
    assert [c["argv"] for c in fake.calls(env.bindir) if c["argv"][:1] == ["merge"]] == [fake.calls(env.bindir)[-1]["argv"]]
    assert not (env.files / "merged").exists()


# ------------------------------------------------------------------------------------------------------ the answer

def test_the_answer_marks_upstream_text_as_untrusted_and_neutralises_it(env):
    fake.set_mode(env.bindir, "esc")
    r = call(["text", "--bundle", str(bundle(env))])
    assert r["ok"] is True and "aviso" in r and "untrusted_saida" in r
    assert "\x1b" not in r["untrusted_saida"] and "‮" not in r["untrusted_saida"]
    assert "ignore previous instructions" in r["untrusted_saida"]  # present as data
    assert "nunca instrução" in r["aviso"].lower()
    assert set(r) >= {"ok", "verbo", "codigo_saida", "untrusted_saida", "saida_cortada", "untrusted_erros", "aviso"}


def test_the_answer_is_cut_at_the_cap_and_says_so(env, monkeypatch):
    monkeypatch.setattr(v2s, "MAX_SAIDA_MCP_CHARS", 50)
    r = call(["check"])
    assert r["saida_cortada"] is True and len(r["untrusted_saida"]) <= 50


def test_a_failing_extractor_is_a_not_ok_answer_with_its_code(env):
    fake.set_mode(env.bindir, "fail")
    r = call(["check"])
    assert r["ok"] is False and r["codigo_saida"] == 3 and "boom" in r["untrusted_erros"] and r["error"]


def test_the_mcp_child_gets_the_same_minimal_environment_and_no_proxy(env, monkeypatch):
    for k in SECRETS:
        monkeypatch.setenv(k, "segredo-" + k)
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy:3128")
    call(["check"])
    seen = fake.calls(env.bindir)[-1]["env"]
    assert "segredo" not in json.dumps(seen) and "HTTPS_PROXY" not in seen and set(seen) <= set(v2s.ENV_NAMES) | {"LC_CTYPE"}


def test_the_mcp_never_writes_a_file_of_its_own_besides_what_the_extractor_writes(env):
    before = sorted(p.name for p in env.files.iterdir())
    b = bundle(env)
    call(["text", "--bundle", str(b)])
    call(["check"])
    assert sorted(p.name for p in env.files.iterdir()) == sorted([*before, "bundle"])


# ------------------------------------------------------------------------------------------------------------------ jobs

def test_the_job_prepare_applies_the_same_closed_list_whatever_the_origin(env):
    for origin in ("mcp", "terminal"):
        for bad in (["extract", "https://example.com/v.mp4", "--out", str(env.files / "b")],
                    ["extract", str(env.video), "--out", str(env.files / "b"), "--autorizo"],
                    ["compile", "--bundle", "/x", "--ir", "/y", "--out", "/z"], ["check"], ["extract", str(env.video)]):
            with pytest.raises(jobs.JobError):
                jobs.submit("video-to-skill", {"args": bad}, origin=origin)
        with pytest.raises(jobs.JobError):
            jobs.submit("video-to-skill", {"args": ["extract", str(env.video), "--out", str(env.files / "b")], "x": 1}, origin=origin)
    assert env.spawned == []


def test_the_job_refuses_when_there_is_no_binary(env, monkeypatch):
    monkeypatch.setenv("PATH", str(env.tmp / "vazio"))
    with pytest.raises(jobs.JobError, match="setup"):
        jobs.submit("video-to-skill", {"args": ["extract", str(env.video), "--out", str(env.files / "b")]}, origin="mcp")


def test_the_job_argv_is_checked_again_so_a_state_edited_on_disk_cannot_add_a_url(env):
    good = {"args": ["extract", str(env.video), "--out", str(env.files / "b")]}
    assert jobs.build_argv("video-to-skill", good)[0] == "video-to-skill"
    for bad in (["extract", "https://example.com/v.mp4", "--out", str(env.files / "b")],
                ["extract", str(env.video), "--out", str(env.files / "b"), "--autorizo"], ["install", "--package", "/x", "--yes"]):
        with pytest.raises((jobs.JobError, v2s.VideoToSkillError)):
            jobs.build_argv("video-to-skill", {"args": bad})


def test_the_job_result_summarises_the_bundle_with_hashes(env):
    out = env.files / "bundle"
    (out / "frames").mkdir(parents=True)
    for name in ("manifest.json", "timeline.json", "transcript.json", "frames.json"):
        (out / name).write_text("{}", encoding="utf8")
    (out / "frames" / "shot000.jpg").write_bytes(b"x")
    (env.files / "bundle.extract.json").write_text("{}", encoding="utf8")
    params = {"args": ["extract", str(env.video), "--out", str(out)], "cwd": str(env.tmp)}
    res = jobs.KINDS["video-to-skill"]["result"](params, None)
    assert res["out"] == str(out) and res["manifest"] == str(out / "manifest.json") and res["timeline"] == str(out / "timeline.json")
    assert len(res["manifest_sha256"]) == 64 and len(res["timeline_sha256"]) == 64 and res["frames"] == 1
    assert res["provenance"] == str(env.files / "bundle.extract.json") and res["screen_text"] is False
    (out / "timeline.json").unlink()
    assert jobs.KINDS["video-to-skill"]["result"](params, None) is None


def test_the_job_private_folder_is_swept_when_the_result_is_read(env):
    cwd = v2s.make_job_cwd()
    assert Path(cwd).is_dir()
    out = env.files / "bundle"
    out.mkdir()
    jobs.KINDS["video-to-skill"]["result"]({"args": ["extract", str(env.video), "--out", str(out)], "cwd": cwd}, None)
    assert not Path(cwd).exists()
    other = env.tmp / "keep"
    other.mkdir()
    v2s.drop_job_cwd(str(other))
    assert other.is_dir(), "only folders with our prefix under the temp dir are removed"
