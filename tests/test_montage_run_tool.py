"""`simplicio-video montage run-tool NAME --input JSON`: one OpenMontage tool through the bridge (T2c).

Terminal: any tool, but a tool that is not local, costs money (or the cost is unknown) or needs network runs only with --yes,
after its estimate is printed. The publish tier never runs. Over MCP (`video.montage run-tool NAME`, with `input` as an
object) only a local, free, offline tool with absolute paths and new outputs is accepted, and it runs as a background job
(`montage-tool`) that returns the job id.

Hermetic: a fake checkout whose registry holds a few fake tools; the venv Python is a wrapper around the test interpreter.
No network, no real tool, no real OpenMontage.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import stat
import sys
from pathlib import Path

import pytest

from simplicio_video import cli, jobs, mcp_server, montage

FAKE_REGISTRY = '''\
import pathlib
import shutil


class Result:
    def __init__(self, success, data=None, artifacts=None, error=None):
        self.success = success
        self.data = data if data is not None else {}
        self.artifacts = artifacts or []
        self.error = error
        self.cost_usd = 0.0
        self.duration_seconds = 0.01
        self.seed = None
        self.model = None


SCHEMA = {
    "type": "object",
    "required": ["input_path"],
    "properties": {
        "input_path": {"type": "string"},
        "output_path": {"type": "string"},
        "times": {"type": "integer", "minimum": 1},
    },
}
SCHEMA_NO_OUT = {"type": "object", "required": ["input_path"], "properties": {"input_path": {"type": "string"}}}


class Tool:
    def __init__(self, name, runtime="local", tier="core", network=False, cost=0.0, mode="copy", schema=SCHEMA):
        self.name, self.runtime, self.tier = name, runtime, tier
        self.network, self.cost, self.mode, self.schema = network, cost, mode, schema

    def get_info(self):
        rp = {"cpu_cores": 1, "ram_mb": 64, "vram_mb": 0, "disk_mb": 0}
        if self.network is not None:  # None: the metadata does not say, which must count as "unknown"
            rp["network_required"] = self.network
        return {"name": self.name, "runtime": self.runtime, "tier": self.tier, "capability": "cap", "provider": "fake",
                "status": "available", "stability": "production", "input_schema": self.schema, "resource_profile": rp}

    def dry_run(self, inputs):
        est = self.cost
        return {"tool": self.name, "estimated_cost_usd": est, "cost_status": "estimated" if est is not None else "quote_required"}

    def execute(self, inputs):
        if self.mode == "raise":
            raise RuntimeError("boom de proposito")
        if self.mode == "fail":
            return Result(False, error="falhou de proposito")
        if self.mode == "relative":  # writes next to the cwd of the process, the way some upstream tools do
            pathlib.Path("relativo.txt").write_text("ok", encoding="utf8")
            return Result(True, {"where": "cwd"}, artifacts=["relativo.txt"])
        src = pathlib.Path(inputs["input_path"])
        out = pathlib.Path(inputs.get("output_path") or str(src) + ".copia")
        shutil.copyfile(src, out)
        return Result(True, {"bytes": out.stat().st_size}, artifacts=[str(out)])


class Registry:
    def __init__(self):
        self._tools = {}

    def discover(self, package_name="tools"):
        for t in (Tool("copia"), Tool("pago", runtime="api", cost=0.5), Tool("rede", network=True),
                  Tool("sem_meta", network=None), Tool("custo_cota", cost=None), Tool("publica", tier="publish"),
                  Tool("gpu", runtime="local_gpu"), Tool("falha", mode="fail"), Tool("quebra", mode="raise"),
                  Tool("relativo", mode="relative", schema=SCHEMA_NO_OUT)):
            self._tools[t.name] = t

    def list_all(self):
        return list(self._tools)

    def get(self, name):
        return self._tools.get(name)

    def support_envelope(self):
        return {n: t.get_info() for n, t in self._tools.items()}


registry = Registry()
'''


def _exe(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


@pytest.fixture
def om(tmp_path, monkeypatch):
    root = tmp_path / "om"
    (root / "backlot").mkdir(parents=True)  # the marker of a real checkout (tools.py: marker="backlot")
    (root / "tools").mkdir(parents=True)
    (root / "tools" / "__init__.py").write_text("", encoding="utf8")
    (root / "tools" / "tool_registry.py").write_text(FAKE_REGISTRY, encoding="utf8")
    (root / "pipeline_defs").mkdir()
    monkeypatch.setenv("OPENMONTAGE_DIR", str(root))
    monkeypatch.setenv("OPENMONTAGE_DATA_DIR", str(tmp_path / "omdata"))
    _exe(montage.venv_python(), f'#!/bin/sh\nexec "{sys.executable}" "$@"\n')
    return root


@pytest.fixture
def src(tmp_path):
    p = tmp_path / "in.txt"
    p.write_text("dados de entrada", encoding="utf8")
    return p


def sha(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def rt(capsys, name, inputs, *extra, json_out=True):
    """`montage run-tool NAME --input ...` in the terminal; returns (exit code, parsed JSON or None, stderr)."""
    argv = ["run-tool", name, "--input", json.dumps(inputs)] + (["--json"] if json_out else []) + list(extra)
    code = montage.main(argv)
    c = capsys.readouterr()
    data = json.loads(c.out) if json_out and c.out.strip() else None
    return code, data, c.err


# ---- terminal: the run and its result ------------------------------------------------------------------------------

def test_free_local_tool_runs_and_reports_outputs_with_sha256(om, src, tmp_path, capsys):
    out = tmp_path / "saida.txt"
    code, data, _ = rt(capsys, "copia", {"input_path": str(src), "output_path": str(out)})
    assert code == 0
    assert data["ok"] is True and data["status"] == "done" and data["tool"] == "copia"
    assert data["outputs"] == [{"path": str(out), "bytes": out.stat().st_size, "sha256": sha(out)}]
    assert out.read_text(encoding="utf8") == "dados de entrada"
    assert data["data"]["bytes"] == out.stat().st_size and isinstance(data["duration_s"], float)
    assert data["estimate"]["estimated_cost_usd"] == 0.0


def test_human_output_prints_the_estimate_before_the_run(om, src, tmp_path, capsys):
    code = montage.main(["run-tool", "copia", "--input", json.dumps({"input_path": str(src), "output_path": str(tmp_path / "x")})])
    c = capsys.readouterr()
    assert code == 0 and "estimativa" in c.err and "copia" in c.err


def test_relative_output_from_a_tool_is_reported_against_the_callers_cwd(om, src, tmp_path, monkeypatch, capsys):
    work = tmp_path / "trabalho"
    work.mkdir()
    monkeypatch.chdir(work)
    code, data, _ = rt(capsys, "relativo", {"input_path": str(src)})
    assert code == 0
    assert data["outputs"][0]["path"] == str(work / "relativo.txt")
    assert data["outputs"][0]["sha256"] == sha(work / "relativo.txt")


def test_failed_tool_is_status_failed_and_exit_1(om, src, capsys):
    code, data, _ = rt(capsys, "falha", {"input_path": str(src)})
    assert code == 1
    assert data["ok"] is False and data["status"] == "failed" and "falhou de proposito" in data["error"]
    assert data["outputs"] == []


def test_tool_exception_is_a_failed_result_not_a_crash(om, src, capsys):
    code, data, err = rt(capsys, "quebra", {"input_path": str(src)})
    assert code == 1 and data["status"] == "failed"
    assert "RuntimeError" in data["error"] and "Traceback" not in err


def test_cli_dispatch_and_help_with_examples(om, capsys):
    with pytest.raises(SystemExit) as e:
        cli.main(["montage", "run-tool", "--help"])
    assert e.value.code == 0
    out = capsys.readouterr().out
    assert "exemplos" in out and "--input" in out and "--yes" in out and "--json" in out and "run-tool" in out


def test_cli_dispatch_runs_the_tool(om, src, tmp_path, capsys):
    out = tmp_path / "pela-cli.txt"
    assert cli.main(["montage", "run-tool", "copia", "--input", json.dumps({"input_path": str(src), "output_path": str(out)}), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "done"


# ---- terminal: the gate (--yes, publish, input) -----------------------------------------------------------------------

def test_api_tool_is_refused_without_yes_and_nothing_runs(om, src, tmp_path, capsys):
    out = tmp_path / "pago.txt"
    code, data, _ = rt(capsys, "pago", {"input_path": str(src), "output_path": str(out)})
    assert code == 1
    assert data["ok"] is False and data["status"] == "refused" and "--yes" in data["error"]
    assert data["estimate"]["estimated_cost_usd"] == 0.5
    assert not out.exists()


def test_api_tool_with_yes_runs_after_the_estimate(om, src, tmp_path, capsys):
    out = tmp_path / "pago.txt"
    code, data, err = rt(capsys, "pago", {"input_path": str(src), "output_path": str(out)}, "--yes")
    assert code == 0 and data["status"] == "done" and out.exists()
    code2 = montage.main(["run-tool", "pago", "--input", json.dumps({"input_path": str(src), "output_path": str(tmp_path / "b")}), "--yes"])
    assert code2 == 0 and "estimativa" in capsys.readouterr().err


def test_network_tool_needs_yes_and_runs_with_it(om, src, tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("SIMPLICIO_OFFLINE", raising=False)
    out = tmp_path / "rede.txt"
    assert rt(capsys, "rede", {"input_path": str(src), "output_path": str(out)})[0] == 1 and not out.exists()
    code, data, _ = rt(capsys, "rede", {"input_path": str(src), "output_path": str(out)}, "--yes")
    assert code == 0 and data["status"] == "done"


def test_unknown_network_metadata_counts_as_network(om, src, tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("SIMPLICIO_OFFLINE", raising=False)
    code, data, _ = rt(capsys, "sem_meta", {"input_path": str(src), "output_path": str(tmp_path / "s")})
    assert code == 1 and data["status"] == "refused" and "--yes" in data["error"]


def test_quote_required_cost_counts_as_unknown_and_needs_yes(om, src, tmp_path, capsys):
    code, data, _ = rt(capsys, "custo_cota", {"input_path": str(src), "output_path": str(tmp_path / "q")})
    assert code == 1 and data["status"] == "refused" and data["estimate"]["estimated_cost_usd"] is None


def test_non_local_runtime_needs_yes(om, src, tmp_path, capsys):
    code, data, _ = rt(capsys, "gpu", {"input_path": str(src), "output_path": str(tmp_path / "g")})
    assert code == 1 and data["status"] == "refused"
    assert rt(capsys, "gpu", {"input_path": str(src), "output_path": str(tmp_path / "g")}, "--yes")[0] == 0


def test_publish_tier_is_refused_even_with_yes(om, src, tmp_path, capsys):
    out = tmp_path / "publicado.txt"
    code, data, _ = rt(capsys, "publica", {"input_path": str(src), "output_path": str(out)}, "--yes")
    assert code == 1 and data["status"] == "refused"
    assert "publicação" in data["error"] and "terminal" in data["error"]
    assert not out.exists()


def test_offline_refuses_a_network_tool_even_with_yes(om, src, tmp_path, capsys):
    assert os.environ.get("SIMPLICIO_OFFLINE") == "1"  # the hermetic fixture sets it
    code, data, _ = rt(capsys, "rede", {"input_path": str(src), "output_path": str(tmp_path / "o")}, "--yes")
    assert code == 1 and data["status"] == "refused" and "offline" in data["error"]


def test_input_missing_a_required_field_is_refused_before_running(om, tmp_path, capsys):
    out = tmp_path / "nada.txt"
    code, data, _ = rt(capsys, "copia", {"output_path": str(out)})
    assert code == 1 and "input_path" in data["error"] and not out.exists()


def test_input_with_a_wrong_type_is_refused(om, src, tmp_path, capsys):
    code, data, _ = rt(capsys, "copia", {"input_path": str(src), "times": "dois"})
    assert code == 1 and "times" in data["error"]


def test_unknown_tool_lists_how_to_see_the_tools(om, capsys):
    with pytest.raises(montage.MontageError, match="tools list"):
        montage.run_tool_plan("nao_existe", {}, strict=False, yes=False)


@pytest.mark.parametrize("name", ["../copia", "-copia", "a b", ""])
def test_tool_name_is_checked_before_anything_runs(om, name):
    with pytest.raises(montage.MontageError, match="nome"):
        montage.run_tool_plan(name, {}, strict=False, yes=False)


def test_input_must_be_a_json_object(om, capsys):
    assert montage.main(["run-tool", "copia", "--input", "[1]"]) == 1
    assert "objeto" in capsys.readouterr().err
    assert montage.main(["run-tool", "copia", "--input", "{nao json"]) == 1
    assert "JSON" in capsys.readouterr().err


def test_input_over_the_argv_limit_is_refused(om, capsys):
    assert montage.main(["run-tool", "copia", "--input", json.dumps({"input_path": "x" * 200_000})]) == 1
    assert "KB" in capsys.readouterr().err


# ---- MCP: the strict gate (plan only, nothing runs in the server) -----------------------------------------------------

def _plan(name, inputs, **kw):
    return montage.run_tool_plan(name, inputs, strict=True, yes=kw.get("yes", False))


def test_strict_accepts_a_free_local_tool_with_absolute_paths(om, src, tmp_path):
    plan = _plan("copia", {"input_path": str(src), "output_path": str(tmp_path / "ok.txt")})
    assert plan["refusal"] is None and plan["needs_yes"] is False and plan["spends"] is False


@pytest.mark.parametrize("name", ["pago", "rede", "sem_meta", "custo_cota", "gpu"])
def test_strict_refuses_paid_networked_unknown_or_non_local_tools_with_the_terminal_hint(om, src, tmp_path, name):
    plan = _plan(name, {"input_path": str(src), "output_path": str(tmp_path / "x")})
    assert plan["refusal"] and "terminal" in plan["refusal"]


def test_strict_refuses_the_publish_tier_even_with_yes(om, src, tmp_path):
    plan = _plan("publica", {"input_path": str(src), "output_path": str(tmp_path / "x")}, yes=True)
    assert plan["refusal"] and "publicação" in plan["refusal"] and "terminal" in plan["refusal"]


@pytest.mark.parametrize("value", ["in.txt", "clips/in.txt", "./in.txt", "../in.txt"])
def test_strict_refuses_relative_paths_including_bare_file_names(om, tmp_path, value):
    plan = _plan("copia", {"input_path": value, "output_path": str(tmp_path / "x")})
    assert plan["refusal"] and "absolut" in plan["refusal"] and "terminal" in plan["refusal"]


def test_strict_refuses_a_relative_output_path(om, src):
    plan = _plan("copia", {"input_path": str(src), "output_path": "saida.txt"})
    assert plan["refusal"] and "absolut" in plan["refusal"]


def test_strict_refuses_an_output_that_already_exists(om, src, tmp_path):
    existing = tmp_path / "ja.txt"
    existing.write_text("nao sobrescrever", encoding="utf8")
    plan = _plan("copia", {"input_path": str(src), "output_path": str(existing)})
    assert plan["refusal"] and "já existe" in plan["refusal"] and "terminal" in plan["refusal"]


def test_strict_refuses_an_output_that_is_a_symlink(om, src, tmp_path):
    target = tmp_path / "alvo.txt"
    link = tmp_path / "link.txt"
    link.symlink_to(target)  # even a dangling link is refused: writing through it would land elsewhere
    plan = _plan("copia", {"input_path": str(src), "output_path": str(link)})
    assert plan["refusal"] and "link" in plan["refusal"] and "terminal" in plan["refusal"]


def test_strict_needs_an_output_path_when_the_tool_has_one(om, src):
    plan = _plan("copia", {"input_path": str(src)})
    assert plan["refusal"] and "output_path" in plan["refusal"] and "terminal" in plan["refusal"]


def test_strict_does_not_ask_for_an_output_when_the_tool_has_none(om, src):
    plan = _plan("relativo", {"input_path": str(src)})
    assert plan["refusal"] is None


def test_strict_refuses_the_input_limit(om, src, tmp_path):
    with pytest.raises(montage.MontageError, match="KB"):
        _plan("copia", {"input_path": str(src), "output_path": str(tmp_path / "x"), "texto": "y" * 200_000})


def test_mcp_run_tool_submits_a_job_and_returns_its_id(om, src, tmp_path, monkeypatch):
    monkeypatch.setattr(jobs, "_spawn_runner", lambda jid: os.getpid())
    out = tmp_path / "mcp.txt"
    r = mcp_server.video_montage("run-tool copia", input={"input_path": str(src), "output_path": str(out)})
    assert r["ok"] is True and r["job"]["kind"] == "montage-tool" and r["job"]["id"]
    st = jobs.status(r["job"]["id"])
    assert st["params"] == {"name": "copia", "input": {"input_path": str(src), "output_path": str(out)}, "strict": True}
    argv = jobs.build_argv("montage-tool", st["params"])
    assert argv[:4] == ["montage", "run-tool", "copia", "--input"] and "--sob-mcp" in argv and "--yes" in argv and "--json" in argv


def test_mcp_refusal_is_an_error_with_the_terminal_command_and_no_job(om, src, tmp_path, monkeypatch):
    monkeypatch.setattr(jobs, "_spawn_runner", lambda jid: os.getpid())
    r = mcp_server.video_montage("run-tool pago", input={"input_path": str(src), "output_path": str(tmp_path / "p")})
    assert r["ok"] is False and "terminal" in r["error"]
    assert jobs.list_jobs() == []


def test_mcp_refuses_extra_flags_and_a_yes(om, src, tmp_path):
    for args in ("run-tool copia --yes", "run-tool copia extra"):
        r = mcp_server.video_montage(args, input={"input_path": str(src), "output_path": str(tmp_path / "f")})
        assert r["ok"] is False and "terminal" in r["error"], args


def test_mcp_input_must_be_an_object(om):
    r = mcp_server.video_montage("run-tool copia", input=["x"])  # type: ignore[arg-type]
    assert r["ok"] is False and "precisa ser um objeto" in r["error"] and "terminal" not in r["error"]


def test_mcp_publish_tier_is_an_error_mentioning_the_terminal(om, src, tmp_path, monkeypatch):
    monkeypatch.setattr(jobs, "_spawn_runner", lambda jid: os.getpid())
    r = mcp_server.video_montage("run-tool publica", input={"input_path": str(src), "output_path": str(tmp_path / "pub")})
    assert r["ok"] is False and "publicação" in r["error"] and "terminal" in r["error"] and jobs.list_jobs() == []


def test_job_kind_runs_the_tool_in_its_own_process_to_done(om, src, tmp_path, monkeypatch):
    """The MCP job: the runner starts `python -m simplicio_video montage run-tool ... --sob-mcp` and the result carries sha256."""
    monkeypatch.setattr(jobs, "_spawn_runner", lambda jid: os.getpid())
    out = tmp_path / "job.txt"
    r = mcp_server.video_montage("run-tool copia", input={"input_path": str(src), "output_path": str(out)})
    jid = r["job"]["id"]
    asyncio.run(asyncio.wait_for(jobs._runner(jid), timeout=120))
    st = jobs.status(jid)
    assert st["state"] == "done", st
    res = jobs.result(jid)["result"]
    assert res["status"] == "done" and res["outputs"][0]["sha256"] == sha(out)
    assert out.read_text(encoding="utf8") == "dados de entrada"


def test_mcp_description_says_run_tool_is_a_job_and_what_it_refuses():
    d = mcp_server.DESC_video_montage
    for word in ("run-tool", "job", "terminal", "absolute", "--yes"):
        assert word in d, word
