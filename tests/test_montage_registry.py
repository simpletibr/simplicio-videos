"""montage registry: pipelines (YAML read in the engine) and tools/envelope/estimate (child process with upstream code).

Everything runs against a tiny fake OpenMontage checkout in tmp_path; no real cache, no network."""
from __future__ import annotations

import json
import textwrap

import pytest

from simplicio_video import cli, montage

PIPELINE_A = """\
name: alpha
version: "1.0"
description: First fake pipeline.
category: generated
stability: production
stages:
  - name: research
"""
PIPELINE_B = """\
name: beta
version: "2.0"
description: Second fake pipeline.
category: hybrid
stability: experimental
"""

FAKE_REGISTRY = '''\
class FakeTool:
    def __init__(self, name, runtime, cost):
        self.name, self.runtime, self.cost = name, runtime, cost

    def get_info(self):
        return {"name": self.name, "runtime": self.runtime, "tier": "core", "capability": "cap-" + self.name,
                "provider": "prov", "status": "available", "stability": "production",
                "input_schema": {"type": "object", "properties": {"text": {"type": "string"}}}}

    def dry_run(self, inputs):
        return {"tool": self.name, "estimated_cost_usd": self.cost * len(inputs.get("text", "")),
                "cost_status": "estimated", "would_execute": True}


class Registry:
    def __init__(self):
        self._tools = {}

    def discover(self, package_name="tools"):
        for t in (FakeTool("tts_local", "local", 0.0), FakeTool("img_api", "api", 0.5), FakeTool("vid_gpu", "local_gpu", 0.0)):
            self._tools[t.name] = t

    def list_all(self):
        return list(self._tools)

    def get(self, name):
        return self._tools.get(name)

    def support_envelope(self):
        return {n: t.get_info() for n, t in self._tools.items()}


registry = Registry()
'''


@pytest.fixture
def fake_om(tmp_path, monkeypatch):
    om = tmp_path / "om"
    (om / "backlot").mkdir(parents=True)
    (om / "pipeline_defs").mkdir()
    (om / "pipeline_defs" / "alpha.yaml").write_text(PIPELINE_A, encoding="utf8")
    (om / "pipeline_defs" / "beta.yaml").write_text(PIPELINE_B, encoding="utf8")
    (om / "tools").mkdir()
    (om / "tools" / "__init__.py").write_text("", encoding="utf8")
    (om / "tools" / "tool_registry.py").write_text(FAKE_REGISTRY, encoding="utf8")
    monkeypatch.setenv("OPENMONTAGE_DIR", str(om))
    return om


def run(capsys, *argv):
    code = montage.main(list(argv))
    out = capsys.readouterr()
    return code, out.out, out.err


def test_pipelines_list_json(fake_om, capsys):
    code, out, _ = run(capsys, "pipelines", "list", "--json")
    assert code == 0
    data = json.loads(out)
    assert [p["name"] for p in data["pipelines"]] == ["alpha", "beta"]
    assert data["pipelines"][0]["description"] == "First fake pipeline."
    assert data["pipelines"][1]["category"] == "hybrid"


def test_pipelines_list_human(fake_om, capsys):
    code, out, _ = run(capsys, "pipelines", "list")
    assert code == 0
    assert "alpha" in out and "beta" in out


def test_pipelines_show_json(fake_om, capsys):
    code, out, _ = run(capsys, "pipelines", "show", "alpha", "--json")
    assert code == 0
    data = json.loads(out)
    assert data["name"] == "alpha"
    assert data["stages"] == [{"name": "research"}]


def test_pipelines_show_unknown_lists_available(fake_om, capsys):
    code, out, err = run(capsys, "pipelines", "show", "nope", "--json")
    assert code == 1
    assert "Traceback" not in err
    assert "nope" in err and "alpha" in err
    assert json.loads(out)["ok"] is False


@pytest.mark.parametrize("name", ["../tools/__init__", "a/b", ".."])
def test_pipelines_show_rejects_path_tricks(fake_om, capsys, name):
    code, _, err = run(capsys, "pipelines", "show", name)
    assert code == 1 and "Traceback" not in err


def test_pipelines_do_not_execute_yaml_tags(fake_om, capsys):
    (fake_om / "pipeline_defs" / "evil.yaml").write_text("name: evil\nx: !!python/object/apply:os.system ['echo pwned']\n", encoding="utf8")
    code, out, err = run(capsys, "pipelines", "list", "--json")
    assert code == 0 and "Traceback" not in err
    data = json.loads(out)
    assert [p["name"] for p in data["pipelines"]] == ["alpha", "beta"]
    assert [e["arquivo"] for e in data["erros"]] == ["evil.yaml"]
    assert data["erros"][0]["motivo"]


def test_pipelines_list_skips_malformed_and_warns(fake_om, capsys):
    (fake_om / "pipeline_defs" / "broken.yaml").write_text("a: [unclosed\n", encoding="utf8")
    (fake_om / "pipeline_defs" / "scalar.yaml").write_text("- 1\n- 2\n", encoding="utf8")
    code, out, err = run(capsys, "pipelines", "list")
    assert code == 0
    assert "alpha" in out and "beta" in out
    assert "broken.yaml" in err and "scalar.yaml" in err


def test_pipelines_list_without_errors_has_empty_erros(fake_om, capsys):
    _, out, _ = run(capsys, "pipelines", "list", "--json")
    assert json.loads(out)["erros"] == []


def test_pipelines_show_malformed_names_the_file(fake_om, capsys):
    (fake_om / "pipeline_defs" / "broken.yaml").write_text("a: [unclosed\n", encoding="utf8")
    code, _, err = run(capsys, "pipelines", "show", "broken")
    assert code == 1 and "broken.yaml" in err and "Traceback" not in err


def test_missing_checkout_says_clone(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("OPENMONTAGE_DIR", str(tmp_path / "ausente"))
    for argv in (["pipelines", "list"], ["tools", "list"], ["envelope"]):
        code, _, err = run(capsys, *argv)
        assert code == 1
        assert "montage clone" in err
        assert "Traceback" not in err


def test_tools_list_json_and_runtime_filter(fake_om, capsys):
    code, out, _ = run(capsys, "tools", "list", "--json")
    assert code == 0
    data = json.loads(out)
    assert {t["name"] for t in data["tools"]} == {"tts_local", "img_api", "vid_gpu"}
    assert {"name", "runtime", "tier", "capability", "provider", "status"} <= set(data["tools"][0])
    code, out, _ = run(capsys, "tools", "list", "--runtime", "api", "--json")
    assert [t["name"] for t in json.loads(out)["tools"]] == ["img_api"]


def test_tools_list_rejects_unknown_runtime(fake_om, capsys):
    with pytest.raises(SystemExit) as e:
        montage.main(["tools", "list", "--runtime", "quantum"])
    assert e.value.code == 2


def test_tools_info(fake_om, capsys):
    code, out, _ = run(capsys, "tools", "info", "img_api", "--json")
    assert code == 0
    data = json.loads(out)
    assert data["name"] == "img_api" and data["input_schema"]["type"] == "object"


def test_tools_info_unknown(fake_om, capsys):
    code, out, err = run(capsys, "tools", "info", "nada", "--json")
    assert code == 1 and "nada" in err and "Traceback" not in err


def test_envelope(fake_om, capsys):
    code, out, _ = run(capsys, "envelope", "--json")
    assert code == 0
    assert set(json.loads(out)["envelope"]) == {"tts_local", "img_api", "vid_gpu"}


def test_estimate(fake_om, capsys):
    code, out, _ = run(capsys, "estimate", "img_api", "--input", '{"text": "abcd"}', "--json")
    assert code == 0
    data = json.loads(out)
    assert data["tool"] == "img_api" and data["estimated_cost_usd"] == 2.0


def test_estimate_bad_input_json(fake_om, capsys):
    code, _, err = run(capsys, "estimate", "img_api", "--input", "{nao json")
    assert code == 1 and "--input" in err and "Traceback" not in err


def test_estimate_input_must_be_object(fake_om, capsys):
    code, _, err = run(capsys, "estimate", "img_api", "--input", "[1]")
    assert code == 1 and "objeto" in err


def test_upstream_import_failure_names_missing_deps(fake_om, capsys):
    (fake_om / "tools" / "__init__.py").write_text("import modulo_que_nao_existe_xyz\n", encoding="utf8")
    code, out, err = run(capsys, "tools", "list", "--json")
    assert code == 1
    assert "modulo_que_nao_existe_xyz" in err
    assert "montage setup" in err
    assert "Traceback" not in err
    assert json.loads(out)["missing"] == ["modulo_que_nao_existe_xyz"]


def test_upstream_crash_is_clean(fake_om, capsys):
    (fake_om / "tools" / "tool_registry.py").write_text(textwrap.dedent("""\
        class R:
            def discover(self): raise RuntimeError("boom")
        registry = R()
    """), encoding="utf8")
    code, _, err = run(capsys, "tools", "list")
    assert code == 1 and "boom" in err and "Traceback" not in err


def test_cli_dispatch_and_subcommand_help_has_examples(fake_om, capsys):
    assert cli.main(["montage", "pipelines", "list", "--json"]) == 0
    assert "alpha" in capsys.readouterr().out
    for argv in (["pipelines"], ["pipelines", "show"], ["tools", "list"], ["tools", "info"], ["envelope"], ["estimate"]):
        with pytest.raises(SystemExit) as e:
            cli.main(["montage", *argv, "--help"])
        assert e.value.code == 0
        out = capsys.readouterr().out
        assert "exemplos" in out and "simplicio-video montage" in out and "--json" in out, argv
