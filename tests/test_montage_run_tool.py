"""`simplicio-video montage run-tool NAME --input JSON`: one OpenMontage tool through the bridge (T2c, review round 2).

Terminal: any tool, but a tool that is not local, costs money (or the cost is unknown or not finite) or needs network runs
only with --yes, after its estimate is printed. The publish tier never runs.

MCP (`video.montage run-tool NAME`, `input` as an object): only a tool on the reviewed allowlist (MCP_ALLOWLIST) that is also
local, free, offline and on absolute paths with new outputs (no link on the way, not under the run folder or the checkout),
and no URL or scheme anywhere in the input. It runs as the job `montage-tool`, which re-runs the strict gate in its own
process. Its result comes back in a file (no 64 KiB limit on the job's output line).

Hermetic: a fake checkout with a fake registry (the venv Python is a wrapper around the test interpreter). No network,
no real tool, no real OpenMontage.
"""
from __future__ import annotations

import asyncio
import errno
import hashlib
import json
import os
import stat
import sys
import time
from pathlib import Path

import pytest

from simplicio_video import cli, jobs, mcp_server, montage

REAL_ALLOWLIST = dict(getattr(montage, "MCP_ALLOWLIST", {}))

FAKE_REGISTRY = '''\
import os
import pathlib
import shutil
import sys
import time


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
        "tamanho": {"type": "integer", "minimum": 0},
    },
}
SCHEMA_NO_OUT = {"type": "object", "required": ["input_path"], "properties": {"input_path": {"type": "string"}}}


class Tool:
    def __init__(self, name, runtime="local", tier="core", network=False, cost=0.0, mode="copy", schema=SCHEMA, deps=()):
        self.name, self.runtime, self.tier = name, runtime, tier
        self.network, self.cost, self.mode, self.schema, self.deps = network, cost, mode, schema, deps

    def get_info(self):
        rp = {"cpu_cores": 1, "ram_mb": 64, "vram_mb": 0, "disk_mb": 0}
        if self.network is not None:  # None: the metadata does not say, which must count as "unknown"
            rp["network_required"] = self.network
        return {"name": self.name, "runtime": self.runtime, "tier": self.tier, "capability": "cap", "provider": "fake",
                "status": "available", "stability": "production", "input_schema": self.schema, "resource_profile": rp,
                "dependencies": list(self.deps), "isolado": sys.flags.isolated,
                "ambiente": sorted(k for k in ("OPENAI_API_KEY",) if k in os.environ)}

    def dry_run(self, inputs):
        est = self.cost
        return {"tool": self.name, "estimated_cost_usd": est, "cost_status": "estimated" if est is not None else "quote_required"}

    def execute(self, inputs):
        if self.mode == "raise":
            raise RuntimeError("boom de proposito")
        if self.mode == "fail":
            return Result(False, error="falhou de proposito")
        if self.mode == "sleep":
            time.sleep(60)
            return Result(True)
        if self.mode == "env":
            return Result(True, {"env": sorted(k for k in ("OPENAI_API_KEY",) if k in os.environ)})
        if self.mode == "isolated":
            return Result(True, {"isolado": sys.flags.isolated})
        if self.mode == "probe":
            return Result(True, {"probe": True})
        if self.mode == "relative":  # writes next to the cwd of the process, the way some upstream tools do
            pathlib.Path("relativo.txt").write_text("ok", encoding="utf8")
            return Result(True, {"where": "cwd"}, artifacts=["relativo.txt"])
        if "tamanho" in inputs:  # a result of a chosen size, to test how big results travel
            return Result(True, {"texto": "x" * int(inputs["tamanho"])})
        src = pathlib.Path(inputs["input_path"])
        out = pathlib.Path(inputs.get("output_path") or str(src) + ".copia")
        shutil.copyfile(src, out)
        return Result(True, {"bytes": out.stat().st_size}, artifacts=[str(out)])


class Registry:
    def __init__(self):
        self._tools = {}

    def discover(self, package_name="tools"):
        for t in (Tool("copia"), Tool("video_trimmer"), Tool("audio_probe", mode="probe", schema=SCHEMA_NO_OUT),
                  Tool("pago", runtime="api", cost=0.5), Tool("rede", network=True), Tool("sem_meta", network=None),
                  Tool("custo_cota", cost=None), Tool("publica", tier="publish"), Tool("gpu", runtime="local_gpu"),
                  Tool("falha", mode="fail"), Tool("quebra", mode="raise"),
                  Tool("relativo", mode="relative", schema=SCHEMA_NO_OUT),
                  Tool("nan", cost=float("nan")), Tool("inf", cost=float("inf")), Tool("dorme", mode="sleep"),
                  Tool("ambiente", mode="env", deps=("env:OPENAI_API_KEY",), schema=SCHEMA_NO_OUT),
                  Tool("isolado", mode="isolated")):
            self._tools[t.name] = t

    def list_all(self):
        return list(self._tools)

    def get(self, name):
        return self._tools.get(name)

    def support_envelope(self):
        return {n: t.get_info() for n, t in self._tools.items()}


registry = Registry()
'''

# the fake tools that the strict tests reach through the allowlist (copia is deliberately NOT here: it is free and local,
# and the allowlist must still refuse it over MCP)
FAKE_ALLOWED = ("relativo", "pago", "rede", "sem_meta", "custo_cota", "publica", "gpu", "nan", "inf", "dorme", "ambiente",
                "isolado", "falha", "quebra")


NO_OUTPUT_FAKES = ("relativo", "ambiente", "isolado")


@pytest.fixture(autouse=True)
def _allowlist_with_fakes(monkeypatch):
    extra = {n: {"outputs": () if n in NO_OUTPUT_FAKES else ("output_path",), "why": "fake de teste"} for n in FAKE_ALLOWED}
    monkeypatch.setattr(montage, "MCP_ALLOWLIST", {**REAL_ALLOWLIST, **extra}, raising=False)


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


def strict_json(text: str):
    """The JSON of a CLI answer, refusing NaN and Infinity (they are not JSON)."""
    return json.loads(text, parse_constant=lambda c: pytest.fail(f"JSON inválido: {c}"))


def rt(capsys, name, inputs, *extra, json_out=True):
    """`montage run-tool NAME --input ...` in the terminal; returns (exit code, parsed JSON or None, stderr)."""
    argv = ["run-tool", name, "--input", json.dumps(inputs)] + (["--json"] if json_out else []) + list(extra)
    code = montage.main(argv)
    c = capsys.readouterr()
    data = strict_json(c.out) if json_out and c.out.strip() else None
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


@pytest.mark.parametrize("name", ["nan", "inf"])
def test_non_finite_cost_is_unknown_and_the_json_stays_valid(om, src, tmp_path, capsys, name):
    code, data, _ = rt(capsys, name, {"input_path": str(src), "output_path": str(tmp_path / name)})
    assert code == 1 and data["status"] == "refused" and "--yes" in data["error"]
    assert data["estimate"]["estimated_cost_usd"] is None
    assert not (tmp_path / name).exists()


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


def test_non_ascii_cap_counts_the_serialized_bytes(om):
    """é is six bytes in the argv (json ensure_ascii), so 20 000 of them are over the cap although the text is short."""
    with pytest.raises(montage.MontageError, match="KB"):
        montage.run_tool_plan("copia", {"input_path": "/x", "texto": "é" * 20_000}, strict=False, yes=False)
    plan = montage.run_tool_plan("copia", {"input_path": "/x", "texto": "é" * 10_000}, strict=False, yes=False)
    assert plan["refusal"] is None


def test_lone_surrogate_input_is_a_clean_error(om, capsys):
    with pytest.raises(montage.MontageError, match="UTF-8"):
        montage.run_tool_plan("copia", {"input_path": "/x", "texto": "\ud800"}, strict=False, yes=False)
    assert montage.main(["run-tool", "copia", "--input", json.dumps({"input_path": "/x", "texto": "\ud800"})]) == 1
    assert "Traceback" not in capsys.readouterr().err


def test_nul_character_reaches_the_tool_without_breaking_the_argv(om, src, tmp_path, capsys):
    out = tmp_path / "nul.txt"
    code, data, _ = rt(capsys, "copia", {"input_path": str(src), "output_path": str(out), "texto": "a\x00b"})
    assert code == 0 and data["status"] == "done"


def test_e2big_from_the_system_is_a_clean_error(om, src, tmp_path, monkeypatch, capsys):
    plan = montage.run_tool_plan("copia", {"input_path": str(src), "output_path": str(tmp_path / "e")}, strict=False, yes=False)

    def too_big(*a, **k):
        raise OSError(errno.E2BIG, "Argument list too long")

    monkeypatch.setattr(montage.subprocess, "Popen", too_big)
    with pytest.raises(montage.MontageError, match="grande"):
        montage.run_tool_execute(plan, {"input_path": str(src), "output_path": str(tmp_path / "e")}, tmp_path)


def test_e2big_from_the_registry_child_is_a_clean_error(om, monkeypatch, capsys):
    def too_big(*a, **k):
        raise OSError(errno.E2BIG, "Argument list too long")

    monkeypatch.setattr(montage.subprocess, "run", too_big)
    assert montage.main(["tools", "info", "copia", "--json"]) == 1
    err = capsys.readouterr().err
    assert "grande" in err and "Traceback" not in err


def test_timeout_ends_a_run_that_does_not_end(om, capsys):
    t0 = time.monotonic()
    code = montage.main(["run-tool", "dorme", "--input", json.dumps({"input_path": "/x"}), "--yes", "--timeout", "1"])
    assert code == 1 and time.monotonic() - t0 < 30
    assert "tempo" in capsys.readouterr().err


def test_upstream_children_run_isolated(om, capsys):
    code, data, _ = rt(capsys, "isolado", {"input_path": "/x"}, "--yes")
    assert code == 0 and data["data"]["isolado"] == 1
    montage.main(["tools", "info", "copia", "--json"])
    assert json.loads(capsys.readouterr().out)["isolado"] == 1


def test_provider_key_reaches_a_terminal_yes_run_only(om, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-teste-falso")
    code, data, _ = rt(capsys, "ambiente", {"input_path": "/x"}, "--yes")
    assert code == 0 and data["data"]["env"] == ["OPENAI_API_KEY"]
    plan = montage.run_tool_plan("ambiente", {"input_path": "/x"}, strict=True, yes=False)
    assert plan["refusal"] is None
    res = montage.run_tool_execute(plan, {"input_path": "/x"}, tmp_path)
    assert res["data"]["env"] == []


def test_registry_child_gets_no_provider_key_under_mcp(om, monkeypatch, capsys):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-teste-falso")
    montage.main(["tools", "info", "copia", "--json"])
    assert json.loads(capsys.readouterr().out)["ambiente"] == ["OPENAI_API_KEY"]  # terminal keeps the keys it had
    monkeypatch.setenv("SIMPLICIO_MCP", "1")
    montage.main(["tools", "info", "copia", "--json"])
    assert json.loads(capsys.readouterr().out)["ambiente"] == []


def test_spends_is_true_for_a_non_local_runtime(om, src, tmp_path):
    plan = montage.run_tool_plan("gpu", {"input_path": str(src), "output_path": str(tmp_path / "g")}, strict=False, yes=True)
    assert plan["spends"] is True and plan["needs_yes"] is True


def test_large_result_is_printed_whole_in_the_terminal(om, src, tmp_path, capsys):
    code, data, _ = rt(capsys, "video_trimmer", {"input_path": str(src), "tamanho": 1_000_000})
    assert code == 0 and len(data["data"]["texto"]) == 1_000_000


# ---- MCP: the allowlist and the strict gate (plan only, nothing runs in the server) ------------------------------------

def _plan(name, inputs, **kw):
    return montage.run_tool_plan(name, inputs, strict=True, yes=kw.get("yes", False))


def test_allowlist_is_reviewed_and_explains_each_entry():
    assert set(REAL_ALLOWLIST) == {"video_trimmer", "audio_probe", "frame_sampler", "scene_detect", "silence_cutter"}
    for name, entry in REAL_ALLOWLIST.items():
        assert entry["why"].strip(), name
        assert isinstance(entry["outputs"], tuple), name
    for barred in ("math_animate", "screen_recorder", "cap_recorder", "video_compose", "hyperframes_compose",
                   "remotion_caption_burn", "diagram_gen", "threejs_world", "export_bundle", "auto_reframe", "video_analyzer"):
        assert barred not in REAL_ALLOWLIST, barred


def test_strict_refuses_a_free_local_tool_that_is_not_reviewed(om, src, tmp_path):
    plan = _plan("copia", {"input_path": str(src), "output_path": str(tmp_path / "x")})
    assert plan["refusal"] and "lista" in plan["refusal"] and "terminal" in plan["refusal"]


def test_strict_accepts_a_reviewed_free_local_tool_with_absolute_paths(om, src, tmp_path):
    plan = _plan("video_trimmer", {"input_path": str(src), "output_path": str(tmp_path / "ok.txt")})
    assert plan["refusal"] is None and plan["needs_yes"] is False and plan["spends"] is False


def test_strict_accepts_a_reviewed_tool_with_no_output_declared(om, src):
    assert _plan("audio_probe", {"input_path": str(src)})["refusal"] is None


@pytest.mark.parametrize("name", ["pago", "rede", "sem_meta", "custo_cota", "gpu", "nan", "inf"])
def test_strict_refuses_paid_networked_unknown_or_non_local_tools_with_the_terminal_hint(om, src, tmp_path, name):
    plan = _plan(name, {"input_path": str(src), "output_path": str(tmp_path / "x")})
    assert plan["refusal"] and "terminal" in plan["refusal"]


def test_strict_refuses_the_publish_tier_even_with_yes(om, src, tmp_path):
    plan = _plan("publica", {"input_path": str(src), "output_path": str(tmp_path / "x")}, yes=True)
    assert plan["refusal"] and "publicação" in plan["refusal"] and "terminal" in plan["refusal"]


@pytest.mark.parametrize("value", ["in.txt", "clips/in.txt", "./in.txt", "../in.txt"])
def test_strict_refuses_relative_paths_including_bare_file_names(om, tmp_path, value):
    plan = _plan("video_trimmer", {"input_path": value, "output_path": str(tmp_path / "x")})
    assert plan["refusal"] and "absolut" in plan["refusal"] and "terminal" in plan["refusal"]


def test_strict_refuses_a_relative_output_path(om, src):
    plan = _plan("video_trimmer", {"input_path": str(src), "output_path": "saida.txt"})
    assert plan["refusal"] and "absolut" in plan["refusal"]


def test_strict_refuses_an_output_that_already_exists(om, src, tmp_path):
    existing = tmp_path / "ja.txt"
    existing.write_text("nao sobrescrever", encoding="utf8")
    plan = _plan("video_trimmer", {"input_path": str(src), "output_path": str(existing)})
    assert plan["refusal"] and "já existe" in plan["refusal"] and "terminal" in plan["refusal"]


def test_strict_refuses_an_output_that_is_a_symlink(om, src, tmp_path):
    target = tmp_path / "alvo.txt"
    link = tmp_path / "link.txt"
    link.symlink_to(target)  # even a dangling link is refused: writing through it would land elsewhere
    plan = _plan("video_trimmer", {"input_path": str(src), "output_path": str(link)})
    assert plan["refusal"] and "terminal" in plan["refusal"]


def test_strict_refuses_an_output_under_a_symlinked_folder(om, src, tmp_path):
    real = tmp_path / "pasta_real"
    real.mkdir()
    (tmp_path / "pasta_link").symlink_to(real)
    plan = _plan("video_trimmer", {"input_path": str(src), "output_path": str(tmp_path / "pasta_link" / "out.txt")})
    assert plan["refusal"] and "link" in plan["refusal"] and "terminal" in plan["refusal"]


def test_strict_refuses_an_output_under_an_intermediate_symlink(om, src, tmp_path):
    real = tmp_path / "raiz_real"
    (real / "sub").mkdir(parents=True)
    (tmp_path / "ok").mkdir()
    (tmp_path / "ok" / "meio").symlink_to(real)  # the link is in the middle of the path, not the last component
    plan = _plan("video_trimmer", {"input_path": str(src), "output_path": str(tmp_path / "ok" / "meio" / "sub" / "out.txt")})
    assert plan["refusal"] and "link" in plan["refusal"]


def test_strict_refuses_an_output_under_the_run_folder_or_the_checkout(om, src, tmp_path):
    run_dir = montage.data_dir() / "run"
    run_dir.mkdir(parents=True, exist_ok=True)
    assert "terminal" in _plan("video_trimmer", {"input_path": str(src), "output_path": str(run_dir / "x.txt")})["refusal"]
    assert "terminal" in _plan("video_trimmer", {"input_path": str(src), "output_path": str(om / "x.txt")})["refusal"]


def test_strict_needs_an_output_path_when_the_tool_has_one(om, src):
    plan = _plan("video_trimmer", {"input_path": str(src)})
    assert plan["refusal"] and "output_path" in plan["refusal"] and "terminal" in plan["refusal"]


def test_strict_does_not_ask_for_an_output_when_the_tool_has_none(om, src):
    plan = _plan("relativo", {"input_path": str(src)})
    assert plan["refusal"] is None


def test_strict_refuses_the_input_limit(om, src, tmp_path):
    with pytest.raises(montage.MontageError, match="KB"):
        _plan("video_trimmer", {"input_path": str(src), "output_path": str(tmp_path / "x"), "texto": "y" * 200_000})


@pytest.mark.parametrize("value", ["https://exemplo.org/clip.mp4", "file:/etc/passwd", "data:text/plain,x"])
def test_strict_refuses_urls_and_schemes_under_any_key(om, src, tmp_path, value):
    plan = _plan("video_trimmer", {"input_path": str(src), "output_path": str(tmp_path / "u"), "legenda": value})
    assert plan["refusal"] and "terminal" in plan["refusal"]
    plan2 = _plan("video_trimmer", {"input_path": value, "output_path": str(tmp_path / "u2")})
    assert plan2["refusal"] and "terminal" in plan2["refusal"]


def test_strict_refusal_for_a_url_says_it_is_a_url(om, src, tmp_path):
    plan = _plan("video_trimmer", {"input_path": "https://exemplo.org/clip.mp4", "output_path": str(tmp_path / "u")})
    assert "URL" in plan["refusal"] or "endereço" in plan["refusal"]


def test_strict_refusal_of_a_nan_cost_names_the_terminal(om, src, tmp_path):
    plan = _plan("nan", {"input_path": str(src), "output_path": str(tmp_path / "n")})
    assert plan["refusal"] and "terminal" in plan["refusal"]
    assert plan["estimate"]["estimated_cost_usd"] is None


def test_mcp_run_tool_submits_a_job_and_returns_its_id(om, src, tmp_path, monkeypatch):
    monkeypatch.setattr(jobs, "_spawn_runner", lambda jid: os.getpid())
    out = tmp_path / "mcp.txt"
    r = mcp_server.video_montage("run-tool video_trimmer", input={"operation": "cut", "input_path": str(src), "output_path": str(out)})
    assert r["ok"] is True and r["job"]["kind"] == "montage-tool" and r["job"]["id"]
    st = jobs.status(r["job"]["id"])
    assert st["params"]["name"] == "video_trimmer" and st["params"]["strict"] is True
    assert st["params"]["input"] == {"operation": "cut", "input_path": str(src), "output_path": str(out)}
    argv = jobs.build_argv("montage-tool", st["params"])
    assert argv[:4] == ["montage", "run-tool", "video_trimmer", "--input"] and "--sob-mcp" in argv and "--yes" in argv and "--json" in argv


def test_job_argv_is_ascii_so_the_argv_limit_is_known(om, src, tmp_path):
    params = {"name": "video_trimmer", "input": {"input_path": str(src), "texto": "çãé — 名"}, "strict": True}
    argv = jobs.build_argv("montage-tool", params)
    assert all(ord(ch) < 128 for a in argv for ch in a)


def test_mcp_refusal_is_an_error_with_the_terminal_command_and_no_job(om, src, tmp_path, monkeypatch):
    monkeypatch.setattr(jobs, "_spawn_runner", lambda jid: os.getpid())
    r = mcp_server.video_montage("run-tool pago", input={"input_path": str(src), "output_path": str(tmp_path / "p")})
    assert r["ok"] is False and "terminal" in r["error"]
    assert jobs.list_jobs() == []


def test_mcp_refuses_extra_flags_and_a_yes(om, src, tmp_path):
    for args in ("run-tool video_trimmer --yes", "run-tool video_trimmer extra"):
        r = mcp_server.video_montage(args, input={"input_path": str(src), "output_path": str(tmp_path / "f")})
        assert r["ok"] is False and "terminal" in r["error"], args


def test_mcp_input_must_be_an_object(om):
    r = mcp_server.video_montage("run-tool video_trimmer", input=["x"])  # type: ignore[arg-type]
    assert r["ok"] is False and "precisa ser um objeto" in r["error"] and "terminal" not in r["error"]


def test_mcp_publish_tier_is_an_error_mentioning_the_terminal(om, src, tmp_path, monkeypatch):
    monkeypatch.setattr(jobs, "_spawn_runner", lambda jid: os.getpid())
    r = mcp_server.video_montage("run-tool publica", input={"input_path": str(src), "output_path": str(tmp_path / "pub")})
    assert r["ok"] is False and "publicação" in r["error"] and "terminal" in r["error"] and jobs.list_jobs() == []


def test_video_jobs_submit_montage_tool_passes_the_same_gate(om, src, tmp_path, monkeypatch):
    monkeypatch.setattr(jobs, "_spawn_runner", lambda jid: os.getpid())
    r = mcp_server.video_jobs("submit", kind="montage-tool",
                              params={"name": "pago", "input": {"input_path": str(src), "output_path": str(tmp_path / "v")}})
    assert r["ok"] is False and "terminal" in r["error"] and jobs.list_jobs() == []


def test_video_jobs_description_mentions_montage_tool():
    assert "montage-tool" in mcp_server.DESC_video_jobs


# ---- the job: the same gate again, and results that are not cut ----------------------------------------------------------

def _run_job(jid):
    asyncio.run(asyncio.wait_for(jobs._runner(jid), timeout=180))
    return jobs.status(jid)


def test_job_kind_runs_the_tool_in_its_own_process_to_done(om, src, tmp_path, monkeypatch):
    """The MCP job: the runner starts `python -m simplicio_video montage run-tool ... --sob-mcp`; the result carries sha256."""
    monkeypatch.setattr(jobs, "_spawn_runner", lambda jid: os.getpid())
    out = tmp_path / "job.txt"
    r = mcp_server.video_montage("run-tool video_trimmer", input={"operation": "cut", "input_path": str(src), "output_path": str(out)})
    jid = r["job"]["id"]
    st = _run_job(jid)
    assert st["state"] == "done", st
    res = jobs.result(jid)["result"]
    assert res["status"] == "done" and res["outputs"][0]["sha256"] == sha(out)
    assert out.read_text(encoding="utf8") == "dados de entrada"


@pytest.mark.parametrize("tamanho", [70_000, 1_000_000])
def test_job_result_is_not_cut_at_64_kib(om, src, tmp_path, monkeypatch, tamanho):
    monkeypatch.setattr(jobs, "_spawn_runner", lambda jid: os.getpid())
    r = mcp_server.video_montage("run-tool video_trimmer", input={"input_path": str(src), "tamanho": tamanho,
                                                                  "output_path": str(tmp_path / f"grande{tamanho}.txt")})
    jid = r["job"]["id"]
    st = _run_job(jid)
    assert st["state"] == "done", st
    res = jobs.result(jid)["result"]
    assert res is not None and len(res["data"]["texto"]) == tamanho


def test_job_regate_refuses_a_tampered_spec(om, src, tmp_path, monkeypatch):
    """A job whose stored name was changed to a tool off the allowlist (paid here) must fail in its own process."""
    monkeypatch.setattr(jobs, "_spawn_runner", lambda jid: os.getpid())
    r = mcp_server.video_montage("run-tool video_trimmer", input={"operation": "cut", "input_path": str(src),
                                                                  "output_path": str(tmp_path / "t.txt")})
    jid = r["job"]["id"]
    jobs.update(jid, params={"name": "pago", "input": {"input_path": str(src), "output_path": str(tmp_path / "t.txt")},
                             "strict": True})
    st = _run_job(jid)
    assert st["state"] == "failed", st
    assert not (tmp_path / "t.txt").exists()
