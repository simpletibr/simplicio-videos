"""match-cut track: pinned skill checkout that the engine only downloads and points at. Nothing here touches the network."""
from __future__ import annotations

import re

import pytest

from simplicio_video import cli, matchcut, mcp_server, tools

SHA40 = re.compile(r"^[0-9a-f]{40}$")


@pytest.fixture(autouse=True)
def _isolated(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("SIMPLICIO_TOOLS_DIR", str(tmp_path / "tools"))
    monkeypatch.delenv("MATCHCUT_DIR", raising=False)
    monkeypatch.delenv("SIMPLICIO_OFFLINE", raising=False)


@pytest.fixture
def checkout(tmp_path, monkeypatch):
    d = tmp_path / "matchcut"
    d.mkdir()
    (d / "SKILL.md").write_text("---\nname: match-cut\n---\n", encoding="utf8")
    monkeypatch.setenv("MATCHCUT_DIR", str(d))
    return d


def test_matchcut_is_pinned_to_a_full_commit_under_mit():
    t = tools.get("matchcut")
    assert t.kind == "git" and t.source == "https://github.com/Sac-Y/match-cut"
    assert t.ref == "b51c98f5c795b046ceb1c69396368dbabd88d5d9" and SHA40.match(t.ref)
    assert t.license == "MIT" and t.marker == "SKILL.md"
    assert "Renoise" in t.note
    assert tools.COMMANDS["matchcut"] == "matchcut"


def test_where_prints_the_skill_path(checkout, capsys):
    assert cli.main(["matchcut", "where"]) == 0
    assert capsys.readouterr().out.strip() == str(checkout.resolve() / "SKILL.md")


def test_where_without_a_checkout_says_how_to_clone(capsys):
    assert cli.main(["matchcut", "where"]) == 1
    assert "matchcut clone" in capsys.readouterr().err


def test_status_without_a_checkout(capsys):
    assert cli.main(["matchcut", "status"]) == 0
    out = capsys.readouterr().out
    assert tools.get("matchcut").ref in out and "instalado: não" in out


def test_status_with_a_checkout_shows_the_skill_file(checkout, capsys, monkeypatch):
    monkeypatch.setattr(tools, "_git", lambda *a, cwd=None: tools.get("matchcut").ref)
    assert cli.main(["matchcut", "status"]) == 0
    out = capsys.readouterr().out
    assert "instalado: sim" in out and str(checkout.resolve() / "SKILL.md") in out and "diferente" not in out


def test_unknown_subcommand_is_an_error():
    with pytest.raises(matchcut.MatchcutError, match="clone|where|status|setup|run"):
        matchcut.run_matchcut(["serve"])


def test_help_says_it_never_calls_renoise_and_needs_it_for_the_skill(capsys):
    assert matchcut.run_matchcut(["--help"]) == 0
    out = capsys.readouterr().out
    for word in ("clone", "where", "status", "setup", "run", "Renoise", "créditos", "MATCHCUT_DIR"):
        assert word in out


def test_clone_refuses_offline_mode(monkeypatch):
    monkeypatch.setenv("SIMPLICIO_OFFLINE", "1")
    with pytest.raises(matchcut.MatchcutError, match="offline"):
        matchcut.clone_matchcut()


def test_mcp_tool_reads_and_refuses_the_rest(checkout, monkeypatch):
    monkeypatch.setattr(tools, "_git", lambda *a, cwd=None: tools.get("matchcut").ref)
    assert mcp_server.video_matchcut("where")["ok"] is True
    assert mcp_server.video_matchcut("status")["ok"] is True
    assert mcp_server.video_matchcut("clone /tmp/x")["ok"] is False
    assert mcp_server.video_matchcut("where extra")["ok"] is False
    assert mcp_server.video_matchcut("run")["ok"] is False


# =========================================================================================================== T9: setup + run
# Offline: the upstream (Sac-Y/match-cut, MIT, pinned b51c98f) is replaced by a FAKE checkout written by the fixture (tiny
# scripts + the sha256 of those files, computed here and put in the module's table), so every refusal below is the engine's.

import ast  # noqa: E402
import hashlib  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import subprocess  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402
from pathlib import Path  # noqa: E402
from types import SimpleNamespace  # noqa: E402

# sha256 of the real files at the pinned commit (read from a real clone on 2026-11-05)
REAL_SHA256 = {
    "scripts/align.py": "308e5f0ea316a3bb9b001d1566374da8377692eb4510dff46ef197bdec067060",
    "scripts/assemble.py": "570d1fe3bed3a2a0bf1fa4a466d6a7a413912e10c15270fc0a6a50038d974e45",
    "scripts/common.py": "ad7f184d55d816f86c2200426ed3cdfabddcfa833f3eb4d9d45affc1b4716c4d",
    "scripts/mix.py": "0044e1dd4061e08e7d70bb1a770cea396223f3ea8ea918d355acd0af6dfc08f7",
    "scripts/music.py": "7fc67b26f4ea785292a95e61fcaf0dba2791be5bd72a6801ba8b319f6913cf09",
    "scripts/qc.py": "1cdb02da4c2c27cb29a8a430b44e670639125c12502685a4a399bc71afe7b88a",
    "scripts/render.py": "8386d404a5429404eecfd84693a3e1809ba355441dfc484d3bb4a84822b4f3ab",
    "scripts/requirements.txt": "21eaf00316784041b287e00da5dff32ac0c62b3e715713eece8cfab661e660cd",
    "scripts/undot.py": "b23fb3fb737cf0e3905e9ef9142087f41df31adeb0391e52fcfd43a9ab2df4a5",
}
REAL_CACHE = Path(os.path.expanduser("~/.simplicio-video/tools/matchcut/scripts"))  # before the autouse fixture moves HOME
SCRIPT_NAMES = ["align", "assemble", "mix", "music", "qc", "render", "undot"]
ENV_ALLOWED = {"PATH", "HOME", "LANG", "LC_ALL", "PYTHONIOENCODING", "TMP", "TEMP", "SYSTEMROOT", "LC_CTYPE",
               "__PYVENV_LAUNCHER__", "NUMBA_CACHE_DIR"}

FAKE = r'''
import json, os, sys
print(json.dumps({"argv": sys.argv[1:], "cwd": os.getcwd(), "env": dict(os.environ), "file": __file__,
                  "stdin": sys.stdin.read(), "flags": {"isolated": sys.flags.isolated, "utf8": sys.flags.utf8_mode,
                  "nobytecode": sys.flags.dont_write_bytecode}}))
'''


def build_checkout(root: Path) -> dict[str, str]:
    (root / "scripts").mkdir(parents=True)
    (root / "SKILL.md").write_text("---\nname: match-cut\n---\n", encoding="utf8")
    hashes = {}
    for rel in REAL_SHA256:
        p = root / rel
        p.write_text("numpy>=1.26\n" if rel.endswith(".txt") else FAKE, encoding="utf8")
        hashes[rel] = hashlib.sha256(p.read_bytes()).hexdigest()
    return hashes


@pytest.fixture
def mc(tmp_path, monkeypatch):
    """Fake checkout at the pinned commit; the module's sha256 table points at it; the 'venv python' is this interpreter."""
    (tmp_path / "work").mkdir()
    monkeypatch.chdir(tmp_path / "work")
    d = tmp_path / "matchcut"
    d.mkdir()
    hashes = build_checkout(d)
    monkeypatch.setenv("MATCHCUT_DIR", str(d))
    monkeypatch.setenv("MATCHCUT_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(matchcut, "PINNED_SHA256", dict(hashes))
    ref = tools.get("matchcut").ref
    monkeypatch.setattr(tools, "_git", lambda *a, cwd=None: ref)
    monkeypatch.setattr(matchcut, "venv_python", lambda: Path(sys.executable))

    def rewrite(rel, text):
        (d / rel).write_text(text, encoding="utf8")
        matchcut.PINNED_SHA256[rel] = hashlib.sha256((d / rel).read_bytes()).hexdigest()

    (tmp_path / "files").mkdir()
    return SimpleNamespace(dir=d.resolve(), ref=ref, hashes=hashes, work=tmp_path / "work", files=tmp_path / "files",
                           tmp=tmp_path, rewrite=rewrite)


@pytest.fixture
def spy(monkeypatch):
    calls = []
    real = subprocess.Popen

    def wrapper(argv, *a, **k):
        calls.append(SimpleNamespace(argv=argv, kwargs=k))
        return real(argv, *a, **k)

    monkeypatch.setattr(subprocess, "Popen", wrapper)
    return calls


def mkfile(mc, name, text="x"):
    p = mc.files / name
    p.write_text(text, encoding="utf8")
    return str(p)


def seen(res):
    return json.loads(res["stdout"])


def montage(mc, **over):
    """A valid montage.json in <files>/proj with relative outputs (resolved next to it, like upstream's common.path)."""
    root = mc.files / "proj"
    root.mkdir(exist_ok=True)
    cfg = {"name": "exp", "timeline": {"fps": 24, "frames": 24, "bpm": 120, "beats_per_bar": 4, "size": [320, 180]},
           "shots": [{"id": "s1", "start": 0, "end": 24}], "music": {"track": "t.wav", "out": "audio/cue.wav"},
           "mix": {"out": "mix"}, "deliver": {"dir": "output"}}
    cfg.update(over)
    path = root / "montage.json"
    path.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf8")
    return str(path), root


# ---------------------------------------------------------------------------------------------------------- the closed list

def test_pinned_sha256_table_is_the_real_one():
    assert matchcut.PINNED_SHA256 == REAL_SHA256


def test_the_script_list_is_closed_and_has_no_network_script():
    assert sorted(matchcut.SCRIPTS) == SCRIPT_NAMES
    for nome, s in matchcut.SCRIPTS.items():
        assert s.script == f"scripts/{nome}.py"
        assert set(s.precisa) <= set(REAL_SHA256) and s.script in s.precisa and "scripts/common.py" in s.precisa


@pytest.mark.parametrize("nome", ["../scripts/music.py", "common", "requirements", "/bin/sh", "music.py", "", "Music", "renoise"])
def test_a_name_outside_the_list_is_refused(mc, nome):
    with pytest.raises(matchcut.MatchcutError, match="fora da lista"):
        matchcut.run_script(nome, [])


def test_no_script_of_the_list_imports_the_network():
    """The audit: the real scripts (when the cached checkout is there) import no network module and never name Renoise."""
    real = REAL_CACHE
    if not real.is_dir():
        pytest.skip("no cached checkout")
    banned = {"socket", "urllib", "http", "requests", "httpx", "aiohttp", "ftplib", "smtplib", "webbrowser"}
    for nome in SCRIPT_NAMES:
        tree = ast.parse((real / f"{nome}.py").read_text(encoding="utf8"))
        mods = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
        mods |= {n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
        assert not mods & banned, nome
        assert "renoise" not in (real / f"{nome}.py").read_text(encoding="utf8").lower(), nome


def test_the_module_has_no_network_import():
    tree = ast.parse(Path(matchcut.__file__).read_text(encoding="utf8"))
    mods = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    mods |= {n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module and n.level == 0}
    assert not mods & {"socket", "urllib", "http", "requests", "httpx", "ssl"}


# ---------------------------------------------------------------------------------------------------------- how a script runs

def test_run_uses_the_venv_python_isolated_with_stdin_devnull_and_a_private_cwd(mc, spy):
    track = mkfile(mc, "t.wav")
    res = matchcut.run_script("music", ["analyze", track])
    assert res["resultado"] is True and res["codigo_saida"] == 0
    call = spy[-1]
    assert call.argv[:6] == [sys.executable, "-I", "-B", "-X", "utf8", "-c"]  # the wrapper sets rlimits, then execs the script
    assert call.argv[-2:] == ["analyze", track] and call.argv[-3].endswith("music.py")
    assert call.kwargs.get("preexec_fn") is None
    assert call.kwargs["stdin"] is subprocess.DEVNULL
    assert call.kwargs["start_new_session"] is True
    out = seen(res)
    assert out["stdin"] == ""
    assert out["flags"] == {"isolated": 1, "utf8": 1, "nobytecode": 1}
    assert out["cwd"] == call.kwargs["cwd"] and not out["cwd"].startswith(str(mc.dir)) and out["cwd"] != str(mc.work)
    assert not Path(out["cwd"]).exists()  # the private folder is gone afterwards


def test_what_runs_is_a_private_copy_of_the_checked_bytes(mc):
    res = matchcut.run_script("qc", ["sheet", mkfile(mc, "c.mp4"), str(mc.files / "o.jpg")])
    ran = Path(seen(res)["file"])
    assert ran.name == "qc.py" and mc.dir not in ran.parents


def test_the_child_environment_is_closed_and_has_no_key(mc, monkeypatch):
    for k in ("OPENAI_API_KEY", "RENOISE_API_KEY", "GEMINI_API_KEY", "HTTPS_PROXY", "PYTHONPATH", "SIMPLICIO_OFFLINE"):
        monkeypatch.setenv(k, "segredo")
    env = seen(matchcut.run_script("mix", [montage(mc)[0]]))["env"]
    assert set(env) <= ENV_ALLOWED and "segredo" not in json.dumps(env)


def test_a_changed_script_is_refused_before_it_runs(mc, spy):
    (mc.dir / "scripts/music.py").write_text(FAKE + "# edited\n", encoding="utf8")
    with pytest.raises(matchcut.MatchcutError, match="sha256"):
        matchcut.run_script("music", ["analyze", mkfile(mc, "t.wav")])
    assert spy == []


def test_a_changed_common_module_is_refused_too(mc, spy):
    (mc.dir / "scripts/common.py").write_text("raise SystemExit(1)\n", encoding="utf8")
    with pytest.raises(matchcut.MatchcutError, match="sha256"):
        matchcut.run_script("align", [mkfile(mc, "a.png"), str(mc.files / "o.png"), "10", "10", "1.2"])
    assert spy == []


def test_a_missing_script_and_a_symlink_are_refused(mc):
    args = ["sheet", mkfile(mc, "c.mp4"), str(mc.files / "o.jpg")]
    (mc.dir / "scripts/qc.py").unlink()
    with pytest.raises(matchcut.MatchcutError, match="não encontrado"):
        matchcut.run_script("qc", args)
    real = mc.tmp / "elsewhere.py"
    real.write_text(FAKE, encoding="utf8")
    (mc.dir / "scripts/qc.py").symlink_to(real)
    with pytest.raises(matchcut.MatchcutError, match="link"):
        matchcut.run_script("qc", args)


def test_a_checkout_at_another_commit_is_refused(mc, monkeypatch, spy):
    monkeypatch.setattr(tools, "_git", lambda *a, cwd=None: "0" * 40)
    with pytest.raises(matchcut.MatchcutError, match="commit"):
        matchcut.run_script("music", ["analyze", mkfile(mc, "t.wav")])
    assert spy == []


def test_no_checkout_says_how_to_clone(tmp_path, monkeypatch):
    (tmp_path / "t.wav").write_text("x")
    with pytest.raises(matchcut.MatchcutError, match="matchcut clone"):
        matchcut.run_script("music", ["analyze", str(tmp_path / "t.wav")])


def test_without_the_venv_run_says_to_run_setup(mc, monkeypatch):
    monkeypatch.undo()  # drops the venv_python stub (and the env of the fixture): rebuild only what is needed
    monkeypatch.delenv("SIMPLICIO_OFFLINE", raising=False)
    monkeypatch.setenv("HOME", str(mc.tmp / "h"))
    monkeypatch.setenv("MATCHCUT_DIR", str(mc.dir))
    monkeypatch.setenv("MATCHCUT_DATA_DIR", str(mc.tmp / "data"))
    monkeypatch.setattr(matchcut, "PINNED_SHA256", dict(mc.hashes))
    monkeypatch.setattr(tools, "_git", lambda *a, cwd=None: mc.ref)
    with pytest.raises(matchcut.MatchcutError, match="matchcut setup"):
        matchcut.run_script("music", ["analyze", mkfile(mc, "t.wav")])


def test_exit_code_is_a_failure_and_stderr_comes_back(mc):
    mc.rewrite("scripts/music.py", "import sys\nprint('falhou', file=sys.stderr)\nsys.exit(3)\n")
    res = matchcut.run_script("music", ["analyze", mkfile(mc, "t.wav")])
    assert res["codigo_saida"] == 3 and res["resultado"] is False and "falhou" in res["stderr"]


def test_a_script_that_runs_too_long_is_killed(mc, monkeypatch):
    mc.rewrite("scripts/music.py", "import time\ntime.sleep(60)\n")
    monkeypatch.setattr(matchcut, "TIMEOUT_S", {**matchcut.TIMEOUT_S, "music": 1})
    t0 = time.monotonic()
    with pytest.raises(matchcut.MatchcutError, match="tempo"):
        matchcut.run_script("music", ["analyze", mkfile(mc, "t.wav")])
    assert time.monotonic() - t0 < 15


def test_output_past_the_cap_is_killed(mc, monkeypatch):
    mc.rewrite("scripts/music.py", "import sys, time\nsys.stdout.write('x' * 3_000_000)\nsys.stdout.flush()\ntime.sleep(60)\n")
    monkeypatch.setattr(matchcut, "MAX_OUTPUT_BYTES", 100_000)
    with pytest.raises(matchcut.MatchcutError, match="limite"):
        matchcut.run_script("music", ["analyze", mkfile(mc, "t.wav")])


# ---------------------------------------------------------------------------------------------------------- the grammar

def test_each_script_accepts_its_documented_forms(mc):
    f = lambda n: mkfile(mc, n)  # noqa: E731
    o = lambda n: str(mc.files / n)  # noqa: E731
    cfg = montage(mc)[0]
    (mc.files / "rd").mkdir()
    rd = str(mc.files / "rd")
    forms = [
        ("align", [f("a.png"), o("o.png"), "10", "5.5", "1.2"]),
        ("assemble", [cfg, rd, "--draft"]),
        ("assemble", [cfg, rd, "--audio", f("a.wav")]),
        ("mix", [cfg]),
        ("mix", [cfg, o("mixout")]),
        ("music", ["analyze", f("t.wav"), "--bpm", "150", "--json", o("a.json")]),
        ("music", ["cut", cfg]),
        ("qc", ["sheet", f("c.mp4"), o("s.jpg")]),
        ("qc", ["sheet", f("c.mp4"), o("s2.jpg"), "0", "48", "3"]),
        ("qc", ["onion", f("a.jpg"), f("b.jpg"), o("on.jpg")]),
        ("qc", ["cuts", cfg, rd, o("cuts.jpg")]),
        ("qc", ["match", f("r.jpg"), "10,10,50,50", f("t.jpg"), f("v.mp4") + ":12"]),
        ("qc", ["look", f("c.mp4"), o("lk.jpg"), "0,5,9", "10,10,200,200"]),
        ("render", [cfg, o("out"), "--draft", "s1"]),
        ("undot", [f("i.mp4"), o("u.mp4"), "100,100,900,500"]),
        ("undot", [f("i.mp4"), o("u2.mp4"), "--fixed", "960,540,8,12"]),
    ]
    for nome, args in forms:
        res = matchcut.run_script(nome, args)
        assert res["resultado"] is True, (nome, args)
        assert seen(res)["argv"], (nome, args)


@pytest.mark.parametrize("nome,args", [
    ("align", ["a", "b", "1", "2"]),                      # too few
    ("music", ["analyse", "x"]),                          # unknown subcommand
    ("music", []),                                        # no subcommand
    ("qc", ["sheet", "a"]),
    ("qc", ["bogus"]),
    ("mix", []),
    ("render", ["only-one"]),
    ("undot", ["a", "b"]),
])
def test_a_wrong_form_is_refused_before_anything_runs(mc, spy, nome, args):
    with pytest.raises(matchcut.MatchcutError):
        matchcut.run_script(nome, args)
    assert spy == []


def test_bad_values_are_refused(mc, spy):
    t, c = mkfile(mc, "t.wav"), mkfile(mc, "c.mp4")
    bad = [
        ("music", ["analyze", t, "--bpm", "abc"]),
        ("music", ["analyze", t, "--bpm", "99999"]),
        ("music", ["analyze", t, "--bpm", "nan"]),
        ("music", ["analyze", t, "--wat"]),
        ("music", ["analyze", t, "--json"]),
        ("align", [c, str(mc.files / "o.png"), "10", "10", "0.2"]),
        ("undot", [c, str(mc.files / "o.mp4"), "1,2,3"]),
        ("undot", [c, str(mc.files / "o.mp4"), "--fixed", "1,2,3"]),
        ("qc", ["match", c, "1,2,3", c]),
        ("qc", ["look", c, str(mc.files / "o.jpg"), "a,b", "1,2,3,4"]),
        ("render", [c, str(mc.files / "o"), "../evil"]),
        ("qc", ["sheet", c, str(mc.files / "o.jpg"), "0", "x", "3"]),
        ("music", ["analyze", t + "\x00"]),
    ]
    for nome, args in bad:
        with pytest.raises(matchcut.MatchcutError):
            matchcut.run_script(nome, args)
    assert spy == []


def test_an_input_that_is_missing_or_not_a_regular_file_is_refused(mc):
    with pytest.raises(matchcut.MatchcutError, match="não encontrado"):
        matchcut.run_script("music", ["analyze", str(mc.files / "nope.wav")])
    with pytest.raises(matchcut.MatchcutError, match="arquivo comum"):
        matchcut.run_script("music", ["analyze", str(mc.files)])
    fifo = mc.files / "fifo"
    os.mkfifo(fifo)
    with pytest.raises(matchcut.MatchcutError, match="arquivo comum"):
        matchcut.run_script("music", ["analyze", str(fifo)])


def test_a_dash_is_not_stdin(mc):
    with pytest.raises(matchcut.MatchcutError):
        matchcut.run_script("music", ["analyze", "-"])


# ---------------------------------------------------------------------------------------------------------- paths

def test_terminal_relative_paths_become_absolute(mc):
    (mc.work / "t.wav").write_text("x")
    res = matchcut.run_script("music", ["analyze", "t.wav", "--json", "a.json"])
    argv = seen(res)["argv"]
    assert argv[1] == str((mc.work / "t.wav").resolve()) and argv[-1] == str((mc.work / "a.json").resolve())


def test_mcp_requires_an_absolute_path_for_every_path_argument(mc, spy):
    t = mkfile(mc, "t.wav")
    (mc.work / "rel.wav").write_text("x")
    for args in (["analyze", "rel.wav"], ["analyze", t, "--json", "rel.json"], ["analyze", "./rel.wav"], ["analyze", "~/x.wav"]):
        with pytest.raises(matchcut.MatchcutError, match="absolut"):
            matchcut.run_script("music", args, canal="mcp")
    assert spy == []
    assert matchcut.run_script("music", ["analyze", t, "--json", str(mc.files / "ok.json")], canal="mcp")["resultado"] is True


def test_an_existing_output_is_kept_unless_the_terminal_says_forcar(mc):
    out = mkfile(mc, "exists.jpg", "KEEP")
    c = mkfile(mc, "c.mp4")
    with pytest.raises(matchcut.MatchcutError, match="já existe"):
        matchcut.run_script("qc", ["sheet", c, out], canal="mcp")
    with pytest.raises(matchcut.MatchcutError, match="forcar"):
        matchcut.run_script("qc", ["sheet", c, out])
    assert Path(out).read_text() == "KEEP"
    with pytest.raises(matchcut.MatchcutError, match="já existe"):
        matchcut.run_script("qc", ["sheet", c, out], canal="mcp", forcar=True)  # MCP has no overwrite at all
    assert matchcut.run_script("qc", ["sheet", c, out], forcar=True)["resultado"] is True


def test_outputs_never_land_in_the_checkout_the_tools_folder_the_venv_or_a_system_folder(mc):
    c = mkfile(mc, "c.mp4")
    (mc.tmp / "tools").mkdir()
    (mc.tmp / "data" / "venv").mkdir(parents=True)
    for dest in (mc.dir / "scripts" / "pwn.jpg", mc.dir / "x.jpg", mc.tmp / "tools" / "x.jpg", mc.tmp / "data" / "venv" / "x.jpg",
                 Path("/etc/x.jpg"), Path("/usr/x.jpg")):
        with pytest.raises(matchcut.MatchcutError, match="não grava"):
            matchcut.run_script("qc", ["sheet", c, str(dest)])


def test_output_in_a_hidden_home_folder_is_refused(mc, monkeypatch):
    home = mc.tmp / "home2"
    (home / ".ssh").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    with pytest.raises(matchcut.MatchcutError, match="oculta"):
        matchcut.run_script("qc", ["sheet", mkfile(mc, "c.mp4"), str(home / ".ssh" / "authorized_keys")])


def test_output_folder_must_exist_and_not_be_a_directory(mc):
    c = mkfile(mc, "c.mp4")
    with pytest.raises(matchcut.MatchcutError, match="pasta de saída"):
        matchcut.run_script("qc", ["sheet", c, str(mc.files / "nodir" / "o.jpg")])
    with pytest.raises(matchcut.MatchcutError, match="é uma pasta"):
        matchcut.run_script("qc", ["sheet", c, str(mc.files)])


def test_a_config_that_is_not_json_is_refused(mc, spy):
    with pytest.raises(matchcut.MatchcutError, match="JSON"):
        matchcut.run_script("mix", [mkfile(mc, "bad.json", "{not json")])
    assert spy == []


def test_a_config_with_relative_outputs_in_a_safe_folder_runs(mc):
    cfg, _ = montage(mc)
    assert matchcut.run_script("mix", [cfg])["resultado"] is True
    assert matchcut.run_script("music", ["cut", cfg])["resultado"] is True


# ---------------------------------------------------------------------------------------------------------- terminal output and CLI

def test_cli_run_prints_the_script_text_with_visible_marks(mc, capsys):
    mc.rewrite("scripts/music.py", "print('\\x1b]0;PWNED\\x07 ok')\n")
    rc = cli.main(["matchcut", "run", "music", "--", "analyze", mkfile(mc, "t.wav")])
    out = capsys.readouterr().out
    assert rc == 0 and "\x1b" not in out and "␛" in out and "PWNED" in out


def test_cli_run_passes_the_exit_code(mc):
    mc.rewrite("scripts/music.py", "import sys\nsys.exit(2)\n")
    assert cli.main(["matchcut", "run", "music", "--", "analyze", mkfile(mc, "t.wav")]) == 2


def test_cli_run_engine_flags_come_before_the_double_dash(mc, capsys):
    out = mkfile(mc, "o.jpg", "old")
    c = mkfile(mc, "c.mp4")
    assert cli.main(["matchcut", "run", "qc", "--forcar", "--", "sheet", c, out]) == 0
    assert cli.main(["matchcut", "run", "qc", "--", "sheet", c, out]) == 1
    assert "forcar" in capsys.readouterr().err
    assert cli.main(["matchcut", "run", "qc", "--wat", "--", "sheet", c, out]) == 1
    assert cli.main(["matchcut", "run"]) == 1
    assert cli.main(["matchcut", "run", "nope"]) == 1


# ---------------------------------------------------------------------------------------------------------- setup

@pytest.fixture
def setup_calls(mc, monkeypatch):
    """Record the commands `setup` would run instead of running pip; the fake `venv` creates the interpreter file."""
    calls = []

    def fake_call(argv, **kw):
        calls.append(list(argv))
        if argv[1:3] == ["-m", "venv"]:
            bindir = Path(argv[3]) / ("Scripts" if os.name == "nt" else "bin")
            bindir.mkdir(parents=True)
            (bindir / ("python.exe" if os.name == "nt" else "python")).write_text("")
        return 0

    monkeypatch.setattr(matchcut, "_call", fake_call)
    monkeypatch.undo()  # setup must use the real venv_python()/data_dir(), not the interpreter stub
    monkeypatch.delenv("SIMPLICIO_OFFLINE", raising=False)  # make check runs with it set; the undo above brought it back
    monkeypatch.setenv("HOME", str(mc.tmp / "h"))
    monkeypatch.setenv("MATCHCUT_DIR", str(mc.dir))
    monkeypatch.setenv("MATCHCUT_DATA_DIR", str(mc.tmp / "data"))
    monkeypatch.setattr(matchcut, "PINNED_SHA256", dict(mc.hashes))
    monkeypatch.setattr(tools, "_git", lambda *a, cwd=None: mc.ref)
    monkeypatch.setattr(matchcut, "_call", fake_call)
    return calls


def test_setup_refuses_offline_mode(mc, monkeypatch, setup_calls):
    monkeypatch.setenv("SIMPLICIO_OFFLINE", "1")
    with pytest.raises(matchcut.MatchcutError, match="offline"):
        matchcut.run_matchcut(["setup"])
    assert setup_calls == []


def test_setup_builds_the_venv_outside_the_checkout_with_progress(mc, setup_calls, capsys):
    assert matchcut.run_matchcut(["setup"]) == 0
    out = capsys.readouterr().out
    for i in (1, 2, 3):
        assert f"[{i}/3]" in out
    venv = mc.tmp / "data" / "venv"
    assert setup_calls[0][1:] == ["-m", "venv", str(venv)]
    assert mc.dir not in venv.parents
    pip = next(c for c in setup_calls if c[1:4] == ["-m", "pip", "install"])
    assert pip[0] == str(matchcut.venv_python()) and "-r" in pip
    assert mc.dir not in Path(pip[pip.index("-r") + 1]).parents  # pip reads the private copy of the checked bytes


def test_setup_checks_the_requirements_sha256_and_the_commit(mc, monkeypatch, setup_calls):
    (mc.dir / "scripts/requirements.txt").write_text("evil-package\n", encoding="utf8")
    with pytest.raises(matchcut.MatchcutError, match="sha256"):
        matchcut.run_matchcut(["setup"])
    assert setup_calls == []
    monkeypatch.setattr(tools, "_git", lambda *a, cwd=None: "1" * 40)
    with pytest.raises(matchcut.MatchcutError, match="commit"):
        matchcut.run_matchcut(["setup"])
    assert setup_calls == []


def test_setup_without_a_checkout_says_how_to_clone(monkeypatch, setup_calls):
    monkeypatch.delenv("MATCHCUT_DIR")
    with pytest.raises(matchcut.MatchcutError, match="matchcut clone"):
        matchcut.run_matchcut(["setup"])


def test_setup_takes_no_arguments(setup_calls):
    with pytest.raises(matchcut.MatchcutError, match="argumentos"):
        matchcut.run_matchcut(["setup", "--x"])


def test_setup_failure_of_pip_is_reported_with_its_code(monkeypatch, setup_calls, capsys):
    inner = matchcut._call

    def failing(argv, **kw):
        return 7 if "pip" in argv else inner(argv, **kw)

    monkeypatch.setattr(matchcut, "_call", failing)
    assert matchcut.run_matchcut(["setup"]) == 7
    assert "7" in capsys.readouterr().err


def test_an_existing_venv_is_kept(setup_calls):
    matchcut.run_matchcut(["setup"])
    matchcut.run_matchcut(["setup"])
    assert len([c for c in setup_calls if c[1:3] == ["-m", "venv"]]) == 1


# ---------------------------------------------------------------------------------------------------------- help

def test_help_has_an_example_for_every_script_and_for_setup(capsys):
    assert matchcut.run_matchcut(["--help"]) == 0
    out = capsys.readouterr().out
    assert "simplicio-video matchcut setup" in out
    for nome in SCRIPT_NAMES:
        assert f"matchcut run {nome}" in out, nome
    for form in ("analyze", "cut", "sheet", "onion", "cuts", "match", "look", "--fixed", "--draft", "--forcar", "--"):
        assert form in out


def test_cli_help_lists_setup_and_run(capsys):
    with pytest.raises(SystemExit):
        cli.main(["matchcut", "--help"])
    out = capsys.readouterr().out
    assert "setup" in out and "run" in out and "matchcut run music" in out


# ---------------------------------------------------------------------------------------------------------- MCP

def test_mcp_run_works_with_absolute_paths_only(mc):
    t = mkfile(mc, "t.wav")
    ok = mcp_server.video_matchcut(["run", "music", "analyze", t])
    assert ok["ok"] is True and ok["script"] == "music" and "saida" in ok
    bad = mcp_server.video_matchcut(["run", "music", "analyze", "rel.wav"])
    assert bad["ok"] is False and "absolut" in bad["error"]


def test_mcp_run_accepts_a_string_with_quotes(mc):
    p = mkfile(mc, "with space.wav")
    res = mcp_server.video_matchcut(f"run music analyze '{p}'")
    assert res["ok"] is True and json.loads(res["saida"])["argv"][1] == p


def test_mcp_refuses_setup_clone_and_the_rest_with_terminal(mc):
    for args in (["setup"], ["clone"], ["clone", "/tmp/x"], ["serve"], [], ["run"], ["run", "common", "x"], ["run", "../music"]):
        assert mcp_server.video_matchcut(args)["ok"] is False, args
    for args in (["setup"], ["clone"]):
        assert "terminal" in mcp_server.video_matchcut(args)["error"]


def test_mcp_run_refuses_what_the_terminal_alone_may_do(mc):
    c, o = mkfile(mc, "c.mp4"), mkfile(mc, "o.jpg")
    assert mcp_server.video_matchcut(["run", "qc", "--forcar", "sheet", c, o])["ok"] is False
    assert mcp_server.video_matchcut(["run", "qc", "sheet", c, o])["ok"] is False  # exists, no overwrite over MCP
    assert mcp_server.video_matchcut(["run", "qc", "--bruto", "sheet", c, str(mc.files / "new.jpg")])["ok"] is False


def test_mcp_run_failure_and_cleaned_output(mc):
    mc.rewrite("scripts/music.py", "import sys\nprint('a\\x1b[31mb\\u202e')\nsys.exit(4)\n")
    res = mcp_server.video_matchcut(["run", "music", "analyze", mkfile(mc, "t.wav")])
    assert res["ok"] is False and res["codigo_saida"] == 4 and "\x1b" not in res["saida"] and "‮" not in res["saida"]


def test_mcp_description_says_local_scripts_absolute_paths_and_terminal_only_setup():
    d = mcp_server.DESC_video_matchcut
    for word in ("run", "absolute", "setup", "terminal", "Renoise", "music", "qc", "never"):
        assert word in d, word


def test_mcp_status_and_where_still_work_and_take_no_arguments(mc):
    assert mcp_server.video_matchcut("where")["ok"] is True
    assert mcp_server.video_matchcut("status")["ok"] is True
    assert mcp_server.video_matchcut("status now")["ok"] is False


def test_matchcut_does_not_import_the_instagram_module():
    tree = ast.parse(Path(matchcut.__file__).read_text(encoding="utf8"))
    imported = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
    imported |= {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    assert not any("instagram" in (m or "") for m in imported)


# =========================================================================================================== review round (PR #166)
# The upstream scripts cannot be edited (sha256-pinned), so the ENGINE validates montage.json before any script reads it:
# picks go into an ffmpeg -vf string, ids/name/dirs become path components and a concat list, and every file a run will write
# is predicted from the config and checked like an output argument.

UPSTREAM_SHAPED = {
    # write where upstream writes (render.py:335-377, mix.py, music.py cut, assemble.py), driven by the same config keys
    "scripts/render.py": r'''
import json, os, sys
cfg = json.load(open(sys.argv[1])); outdir = os.path.abspath(sys.argv[2])
ids = [a for a in sys.argv[3:] if a != '--draft'] or [s['id'] for s in cfg['shots']]
os.makedirs(f'{outdir}/shots', exist_ok=True); os.makedirs(f'{outdir}/qc', exist_ok=True)
sh = {s['id']: s for s in cfg['shots']}
for sid in ids:
    open(f'{outdir}/shots/{sid}.mov', 'w').write('x')
    n = sh[sid]['end'] - sh[sid]['start']; qc = {0: 'first', n // 2: 'mid', n - 1: 'last'}   # render.py:337
    for i in range(n):
        if i in qc:
            k = qc[i]; open(f'{outdir}/qc/{sid}-{k}.jpg', 'w').write('x'); open(f'{outdir}/qc/{sid}-{k}.json', 'w').write('{}')
''',
    "scripts/mix.py": r'''
import json, os, sys
cfg = json.load(open(sys.argv[1]))
out = os.path.abspath(sys.argv[2]) if len(sys.argv) > 2 else os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(sys.argv[1])), cfg['mix']['out']))
os.makedirs(f'{out}/stems', exist_ok=True)
open(f'{out}/mix.wav', 'w').write('x'); open(f'{out}/mix-report.json', 'w').write('{}')
for k in ('music', 'vo', 'sfx'):
    open(f'{out}/stems/{k}.wav', 'w').write('x')
''',
    "scripts/music.py": r'''
import json, os, sys
cfg = json.load(open(sys.argv[2]))
out = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(sys.argv[2])), cfg['music']['out']))
os.makedirs(os.path.dirname(out), exist_ok=True); open(out, 'w').write('x')
''',
    "scripts/assemble.py": r'''
import json, os, shutil, sys
cfg = json.load(open(sys.argv[1])); rdir = os.path.abspath(sys.argv[2]); name = cfg.get('name', 'montage')
base = os.path.dirname(os.path.abspath(sys.argv[1]))
open(os.path.join(rdir, 'concat.txt'), 'w').write(''.join(f"file '{rdir}/shots/{s['id']}.mov'\n" for s in cfg['shots']))
if '--draft' in sys.argv:
    open(os.path.join(rdir, f'{name}-animatic.mp4'), 'w').write('x'); sys.exit(0)
d = cfg.get('deliver', {}); odir = os.path.normpath(os.path.join(base, d.get('dir', 'output'))); os.makedirs(odir, exist_ok=True)
open(os.path.join(odir, f'{name}-master-prores422hq.mov'), 'w').write('x'); open(os.path.join(odir, f'{name}-1080p.mp4'), 'w').write('x')
audio = os.path.join(os.path.normpath(os.path.join(base, cfg['mix']['out'])), 'mix.wav')
sdir = os.path.join(os.path.dirname(audio), 'stems')
if os.path.isdir(sdir):
    os.makedirs(os.path.join(odir, 'stems'), exist_ok=True)
    for f in os.listdir(sdir): shutil.copy(os.path.join(sdir, f), os.path.join(odir, 'stems', f))
    shutil.copy(audio, os.path.join(odir, 'stems', 'mix.wav'))
''',
}


@pytest.fixture
def writers(mc):
    for rel, code in UPSTREAM_SHAPED.items():
        mc.rewrite(rel, code)
    return mc


def tree(root):
    return {str(p) for p in Path(root).rglob("*") if p.is_file()}


# ---- 1. picks: numbers only (they are interpolated into the ffmpeg -vf string)

BAD_PICKS = [
    ["0)',metadata=mode=print:file=/tmp/pwn,("],          # the reported filtergraph injection
    [1, "2"], [1, 2.5], [True, 2], [None], [[1]], [-1],
    {"list": ["a"]}, {"list": "12"}, {"range": ["0", 5]}, {"range": [0, 10 ** 9]}, {"range": [0, 5, 1, 1]}, {"range": 5},
    {"linspace": [0, "5"]}, {"linspace": [0]}, {"from": "0"}, {"from": 0, "speed": "1"}, {"from": 0, "offset": 1.5},
    {"from": 0, "offset": True}, {"from": float("nan")}, "0:5", 7, {"list": [0] * 120_000},
]
GOOD_PICKS = [[0, 1, 2], {"list": [0, 1]}, {"range": [0, 24]}, {"range": [0, 24, 2]}, {"linspace": [0, 10]}, {"from": 0, "speed": 1.0},
              {"from": 3, "speed": 0.5, "offset": 2}, {}]


@pytest.mark.parametrize("picks", BAD_PICKS, ids=lambda p: repr(p)[:40])
def test_picks_that_are_not_plain_numbers_are_refused(writers, spy, picks):
    cfg, root = montage(writers, shots=[{"id": "s1", "start": 0, "end": 24, "picks": picks}])
    with pytest.raises(matchcut.MatchcutError, match="picks"):
        matchcut.run_script("render", [cfg, str(root / "out")])
    assert spy == [] and not (root / "out").exists()


def test_plain_picks_are_accepted(writers):
    for picks in GOOD_PICKS:
        cfg, root = montage(writers, shots=[{"id": "s1", "start": 0, "end": 24, "picks": picks}])
        res = matchcut.run_script("render", [cfg, str(root / f"out{abs(hash(repr(picks)))}")])
        assert res["resultado"] is True, picks


def test_the_injection_does_not_write_the_file_even_with_a_real_ffmpeg_shaped_script(writers):
    target = writers.tmp / "pwn.txt"
    cfg, root = montage(writers, shots=[{"id": "s1", "start": 0, "end": 24, "picks": [f"0)',metadata=mode=print:file={target},("]}])
    with pytest.raises(matchcut.MatchcutError):
        matchcut.run_script("render", [cfg, str(root / "out")], canal="mcp")
    assert not target.exists()


# ---- 2. ids, name, directories: strict charset and the place rules for every derived path

BAD_IDS = ["../../../escaped", "a/b", "a'b", 'a"b', "a\nb", "a\r\nfile 'http://x/y", "", "-x", ".hidden", "a b", "a;b", "é", 5, None, "x" * 80]


@pytest.mark.parametrize("sid", BAD_IDS, ids=lambda v: repr(v)[:30])
def test_a_shot_id_outside_the_strict_charset_is_refused_by_every_script_that_reads_the_montage(writers, spy, sid):
    cfg, root = montage(writers, shots=[{"id": sid, "start": 0, "end": 24}])
    (root / "rd").mkdir()
    calls = [("render", [cfg, str(root / "out")]), ("assemble", [cfg, str(root / "rd"), "--draft"]), ("mix", [cfg]),
             ("music", ["cut", cfg]), ("qc", ["cuts", cfg, str(root / "rd"), str(root / "c.jpg")])]
    for nome, args in calls:
        with pytest.raises(matchcut.MatchcutError, match="id"):
            matchcut.run_script(nome, args, canal="mcp")
    assert spy == [] and not (writers.tmp / "escaped.mov").exists()


def test_a_traversal_id_writes_nothing_outside_the_output_folder(writers):
    cfg, root = montage(writers, shots=[{"id": "../../../escaped", "start": 0, "end": 24}])
    before = tree(writers.tmp)
    with pytest.raises(matchcut.MatchcutError):
        matchcut.run_script("render", [cfg, str(root / "out")])
    assert tree(writers.tmp) == before


@pytest.mark.parametrize("nome", ["../escape", "a/b", "a'b", "a\nb", "", ".x", 3, "-n"])
def test_a_montage_name_outside_the_strict_charset_is_refused(writers, nome):
    cfg, root = montage(writers, name=nome)
    (root / "rd").mkdir()
    with pytest.raises(matchcut.MatchcutError, match="name"):
        matchcut.run_script("assemble", [cfg, str(root / "rd"), "--draft"])


def test_the_render_dir_of_assemble_follows_the_output_place_rules(writers, monkeypatch):
    home = writers.tmp / "home3"
    (home / ".ssh" / "shots").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    cfg, root = montage(writers)
    for extra in ([], ["--draft"]):
        with pytest.raises(matchcut.MatchcutError, match="não grava"):
            matchcut.run_script("assemble", [cfg, str(home / ".ssh"), *extra], canal="mcp")
    assert tree(home) == set()
    with pytest.raises(matchcut.MatchcutError, match="não grava"):
        matchcut.run_script("assemble", [cfg, str(writers.dir / "scripts"), "--draft"])


def test_a_render_dir_that_would_break_the_concat_list_is_refused(writers):
    cfg, root = montage(writers)
    for bad in ("it's", "line\nbreak"):
        d = root / bad
        d.mkdir()
        with pytest.raises(matchcut.MatchcutError, match="concat"):
            matchcut.run_script("assemble", [cfg, str(d), "--draft"])


def test_the_default_deliver_dir_is_checked_too(writers, monkeypatch):
    home = writers.tmp / "home4"
    proj = home / ".config" / "mont"
    proj.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    cfg = proj / "montage.json"
    cfg.write_text(json.dumps({"name": "exp", "timeline": {"fps": 24, "frames": 24, "bpm": 120}, "shots": [{"id": "s1", "start": 0, "end": 24}],
                               "mix": {"out": "mix"}}), encoding="utf8")
    rd = writers.files / "rd"
    rd.mkdir()
    with pytest.raises(matchcut.MatchcutError, match="oculta"):
        matchcut.run_script("assemble", [str(cfg), str(rd)], canal="mcp")
    assert not (proj / "output").exists()


@pytest.mark.parametrize("nome,args_fn,over", [
    ("music", lambda c, r: ["cut", c], {"music": {"out": "/etc/cron.d/x.wav"}}),
    ("mix", lambda c, r: [c], {"mix": {"out": "/etc/cron.d"}}),
    ("assemble", lambda c, r: [c, str(r)], {"deliver": {"dir": "/usr/local/out"}}),
])
def test_a_montage_that_points_a_declared_output_at_a_forbidden_place_is_refused(writers, spy, nome, args_fn, over):
    cfg, root = montage(writers, **over)
    (root / "rd").mkdir()
    args = args_fn(cfg, root / "rd")
    with pytest.raises(matchcut.MatchcutError, match="não grava"):
        matchcut.run_script(nome, args)
    assert spy == []


def test_a_missing_mix_out_without_an_outdir_is_explained(writers):
    cfg, root = montage(writers, mix={})
    with pytest.raises(matchcut.MatchcutError, match="mix.out"):
        matchcut.run_script("mix", [cfg])


# ---- 3. no overwrite of what the montage declares (music.out, mix files, shots, deliverables, stems)

def test_music_cut_does_not_overwrite_music_out(writers):
    cfg, root = montage(writers)
    out = root / "audio" / "cue.wav"
    out.parent.mkdir()
    out.write_text("ORIGINAL")
    for canal in ("mcp", "terminal"):
        with pytest.raises(matchcut.MatchcutError, match="já existe"):
            matchcut.run_script("music", ["cut", cfg], canal=canal)
    assert out.read_text() == "ORIGINAL"
    with pytest.raises(matchcut.MatchcutError, match="já existe"):
        matchcut.run_script("music", ["cut", cfg], canal="mcp", forcar=True)
    assert matchcut.run_script("music", ["cut", cfg], forcar=True)["resultado"] is True
    assert out.read_text() == "x"


def test_assemble_full_does_not_overwrite_deliverables(writers):
    cfg, root = montage(writers)
    (root / "rd").mkdir()
    out = root / "output"
    out.mkdir()
    (out / "exp-1080p.mp4").write_text("ORIGINAL")
    with pytest.raises(matchcut.MatchcutError, match="já existe"):
        matchcut.run_script("assemble", [cfg, str(root / "rd")], canal="mcp")
    assert (out / "exp-1080p.mp4").read_text() == "ORIGINAL"
    assert matchcut.run_script("assemble", [cfg, str(root / "rd")], forcar=True)["resultado"] is True


def test_assemble_stems_copies_are_predicted_and_checked(writers):
    cfg, root = montage(writers)
    (root / "rd").mkdir()
    (root / "mix" / "stems").mkdir(parents=True)
    (root / "mix" / "stems" / "music.wav").write_text("m")
    (root / "output" / "stems").mkdir(parents=True)
    (root / "output" / "stems" / "music.wav").write_text("ORIGINAL")
    with pytest.raises(matchcut.MatchcutError, match="já existe"):
        matchcut.run_script("assemble", [cfg, str(root / "rd")], canal="mcp")
    assert (root / "output" / "stems" / "music.wav").read_text() == "ORIGINAL"


def test_assemble_draft_overwrites_nothing_but_its_own_scratch_concat_list(writers):
    cfg, root = montage(writers)
    rd = root / "rd"
    rd.mkdir()
    assert matchcut.run_script("assemble", [cfg, str(rd), "--draft"], canal="mcp")["resultado"] is True
    with pytest.raises(matchcut.MatchcutError, match="já existe"):  # exp-animatic.mp4 is there now; concat.txt alone would not block
        matchcut.run_script("assemble", [cfg, str(rd), "--draft"], canal="mcp")


def test_mix_does_not_overwrite_an_earlier_mix(writers):
    cfg, root = montage(writers)
    assert matchcut.run_script("mix", [cfg], canal="mcp")["resultado"] is True
    with pytest.raises(matchcut.MatchcutError, match="já existe"):
        matchcut.run_script("mix", [cfg], canal="mcp")
    other = str(root / "mix2")
    assert matchcut.run_script("mix", [cfg, other], canal="mcp")["resultado"] is True
    with pytest.raises(matchcut.MatchcutError, match="já existe"):
        matchcut.run_script("mix", [cfg, other])


def test_render_does_not_overwrite_shots_or_qc_files_and_checks_only_the_selected_ids(writers):
    cfg, root = montage(writers, shots=[{"id": "s1", "start": 0, "end": 12}, {"id": "s2", "start": 12, "end": 24}])
    out = str(root / "out")
    assert matchcut.run_script("render", [cfg, out, "s1"], canal="mcp")["resultado"] is True
    with pytest.raises(matchcut.MatchcutError, match="já existe"):
        matchcut.run_script("render", [cfg, out, "s1"], canal="mcp")
    with pytest.raises(matchcut.MatchcutError, match="já existe"):
        matchcut.run_script("render", [cfg, out], canal="mcp")  # no ids = all shots, s1 is there
    assert matchcut.run_script("render", [cfg, out, "s2"], canal="mcp")["resultado"] is True
    with pytest.raises(matchcut.MatchcutError, match="plano"):
        matchcut.run_script("render", [cfg, str(root / "o3"), "nope"])


@pytest.mark.parametrize("nome,make", [
    ("render", lambda c, r: [c, str(r / "o")]),
    ("mix", lambda c, r: [c, str(r / "m")]),
    ("music", lambda c, r: ["cut", c]),
    ("assemble", lambda c, r: [c, str(r / "rd")]),
    ("assemble", lambda c, r: [c, str(r / "rd"), "--draft"]),
])
def test_the_predicted_outputs_are_exactly_what_the_upstream_shaped_script_writes(writers, nome, make):
    cfg, root = montage(writers, shots=[{"id": "s1", "start": 0, "end": 12}, {"id": "s2", "start": 12, "end": 14}, {"id": "s3", "start": 14, "end": 15}])
    (root / "rd" / "shots").mkdir(parents=True)
    (root / "mix" / "stems").mkdir(parents=True)
    (root / "mix" / "mix.wav").write_text("m")
    (root / "mix" / "stems" / "music.wav").write_text("m")
    args = make(cfg, root)
    s = matchcut.SCRIPTS[nome]
    predicted = {str(Path(p)) for p in matchcut._saidas(s, args)}
    before = tree(writers.tmp)
    assert matchcut.run_script(nome, args)["resultado"] is True
    created = tree(writers.tmp) - before
    scratch = {str(root / "rd" / "concat.txt")}  # assemble's own list for ffmpeg: rewritten on every run, never a deliverable
    assert created - scratch == predicted - before, (created - scratch) ^ (predicted - before)


# ---- numbers in the config are numbers

@pytest.mark.parametrize("over", [
    {"timeline": {"fps": "24", "frames": 24, "bpm": 120}},
    {"timeline": {"fps": 24, "frames": True, "bpm": 120}},
    {"timeline": {"fps": 24, "frames": 24, "bpm": 0}},
    {"timeline": {"fps": 24, "frames": 24, "bpm": 120, "size": [320]}},
    {"timeline": {"fps": 24, "frames": 24, "bpm": 120, "size": ["a", 5]}},
    {"timeline": "x"},
    {"shots": "x"}, {"shots": [{"id": "s1", "start": "0", "end": 24}]}, {"shots": [{"id": "s1", "start": 0, "end": 1.5}]},
    {"shots": [1]}, {"deliver": {"dir": "output", "crf": "14 -f x"}}, {"deliver": {"dir": "output", "crf": 99}},
    {"deliver": {"dir": 5}}, {"sources": {"a": 5}}, {"music": 4},
])
def test_non_numeric_or_wrongly_typed_config_values_are_refused(writers, over):
    cfg, root = montage(writers, **over)
    (root / "rd").mkdir()
    with pytest.raises(matchcut.MatchcutError):
        matchcut.run_script("assemble", [cfg, str(root / "rd")])


def test_a_huge_config_is_refused(writers):
    cfg, root = montage(writers, shots=[{"id": f"s{i}", "start": i, "end": i + 1} for i in range(5000)])
    with pytest.raises(matchcut.MatchcutError, match="planos"):
        matchcut.run_script("render", [cfg, str(root / "out")])


# ---- 5/7/9: limits, the whole process group, no preexec_fn

def test_the_script_runs_with_an_address_space_limit(mc):
    resource = pytest.importorskip("resource")
    mc.rewrite("scripts/music.py", "import resource\nprint(resource.getrlimit(resource.RLIMIT_AS)[0], resource.getrlimit(resource.RLIMIT_CORE)[0])\n")
    out = matchcut.run_script("music", ["analyze", mkfile(mc, "t.wav")])["stdout"].split()
    assert int(out[0]) == matchcut.DEFAULT_MEM_GIB * 1024 ** 3 and int(out[1]) == 0
    assert resource.getrlimit(resource.RLIMIT_AS)[0] != int(out[0])  # the engine itself is not limited


def test_the_address_space_limit_is_configurable_and_can_be_off(mc, monkeypatch):
    pytest.importorskip("resource")
    mc.rewrite("scripts/music.py", "import resource\nprint(resource.getrlimit(resource.RLIMIT_AS)[0])\n")
    monkeypatch.setenv("MATCHCUT_MEM_GIB", "3")
    assert int(matchcut.run_script("music", ["analyze", mkfile(mc, "t.wav")])["stdout"]) == 3 * 1024 ** 3
    monkeypatch.setenv("MATCHCUT_MEM_GIB", "0")
    assert int(matchcut.run_script("music", ["analyze", mkfile(mc, "t.wav")])["stdout"]) == -1  # RLIM_INFINITY: no limit
    for bad in ("abc", "-1", "99999", "nan"):
        monkeypatch.setenv("MATCHCUT_MEM_GIB", bad)
        with pytest.raises(matchcut.MatchcutError, match="MATCHCUT_MEM_GIB"):
            matchcut.run_script("music", ["analyze", mkfile(mc, "t.wav")])


def test_a_script_that_uses_too_much_memory_fails_instead_of_eating_the_machine(mc, monkeypatch):
    pytest.importorskip("resource")
    monkeypatch.setenv("MATCHCUT_MEM_GIB", "1")
    mc.rewrite("scripts/music.py", "x = bytearray(2 * 1024 ** 3)\nprint('allocated')\n")
    res = matchcut.run_script("music", ["analyze", mkfile(mc, "t.wav")])
    assert res["resultado"] is False and "allocated" not in res["stdout"] and "MemoryError" in res["stderr"]


def test_grandchildren_are_killed_after_a_normal_exit(mc):
    pidfile = mc.files / "gc.pid"
    mc.rewrite("scripts/music.py", f"import subprocess, sys\np = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
                                   f"open({str(pidfile)!r}, 'w').write(str(p.pid))\n")
    assert matchcut.run_script("music", ["analyze", mkfile(mc, "t.wav")])["resultado"] is True
    pid = int(pidfile.read_text())
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        try:
            alive = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0] != "Z"
        except OSError:
            alive = False
        if not alive:
            break
        time.sleep(0.05)
    assert not alive


def test_the_module_does_not_use_preexec_fn():
    assert "preexec_fn" not in Path(matchcut.__file__).read_text(encoding="utf8").replace("# no preexec_fn", "")


# ---- 6: setup runs pip with a minimal environment

def test_setup_commands_get_a_minimal_environment_without_keys(mc, monkeypatch, setup_calls):
    for k in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY", "RENOISE_API_KEY", "GITHUB_TOKEN"):
        monkeypatch.setenv(k, "segredo")
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy:3128")
    seen_env = []
    inner = matchcut._call

    def spy_call(argv, **kw):
        seen_env.append(kw.get("env"))
        return inner(argv, **kw)

    monkeypatch.setattr(matchcut, "_call", spy_call)
    assert matchcut.run_matchcut(["setup"]) == 0
    assert len(seen_env) == 3 and all(isinstance(e, dict) for e in seen_env)
    for e in seen_env:
        assert "segredo" not in json.dumps(e) and "PATH" in e
    assert seen_env[1].get("HTTPS_PROXY") == "http://proxy:3128"  # pip still reaches the network through the user's proxy


def test_help_documents_the_limits_and_that_versions_are_not_hashed(capsys):
    matchcut.run_matchcut(["--help"])
    out = capsys.readouterr().out
    for word in ("MATCHCUT_MEM_GIB", "sem hash", "montage.json", "picks", "já existe"):
        assert word in out, word


def test_qc_files_are_predicted_only_where_render_writes_them(writers):
    cfg, root = montage(writers, shots=[{"id": "a", "start": 0, "end": 2}, {"id": "b", "start": 2, "end": 3}, {"id": "c", "start": 3, "end": 6}])
    got = {Path(p).name for p in matchcut._saidas(matchcut.SCRIPTS["render"], [cfg, str(root / "o")])}
    assert "a-mid.jpg" not in got and {"a-first.jpg", "a-last.json"} <= got      # n=2: mid and last are the same frame, last wins
    assert {"b-last.jpg", "b-last.json"} <= got and "b-first.jpg" not in got and "b-mid.jpg" not in got   # n=1: one frame
    assert {"c-first.jpg", "c-mid.jpg", "c-last.jpg"} <= got


def test_a_concat_list_that_is_a_symlink_is_refused(writers, monkeypatch):
    home = writers.tmp / "home5"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    victim = home / ".r2bashrc"
    victim.write_text("ORIGINAL")
    cfg, root = montage(writers)
    rd = root / "rd"
    rd.mkdir()
    (rd / "concat.txt").symlink_to(victim)
    for canal in ("mcp", "terminal"):
        with pytest.raises(matchcut.MatchcutError, match="concat.txt"):
            matchcut.run_script("assemble", [cfg, str(rd), "--draft"], canal=canal, forcar=True)
    assert victim.read_text() == "ORIGINAL"


def test_a_concat_list_that_is_a_directory_is_refused_and_a_plain_file_is_fine(writers):
    cfg, root = montage(writers)
    rd = root / "rd"
    (rd / "concat.txt").mkdir(parents=True)
    with pytest.raises(matchcut.MatchcutError, match="concat.txt"):
        matchcut.run_script("assemble", [cfg, str(rd), "--draft"])
    (rd / "concat.txt").rmdir()
    (rd / "concat.txt").write_text("old")
    assert matchcut.run_script("assemble", [cfg, str(rd), "--draft"])["resultado"] is True


def test_the_module_docstring_mentions_the_montage_validation():
    doc = matchcut.__doc__
    for word in ("montage.json", "picks", "predict"):
        assert word in doc, word
