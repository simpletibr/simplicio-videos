"""Contrato da issue #72: saídas com schema e erros em JSON (`--json`) de validate, run e render.

Schemas versionados em schemas/cli/ (validate-result, run-result, render-result, render-manifest, preview-manifest).
Testes em processo (main()), sem rede e sem render de verdade: o render é mockado (do_render) ou falha antes
de qualquer subprocesso, porque a validação do contrato roda primeiro. O texto de validate não muda.
"""
import json
import sys
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator

from conftest import ROOT
from simplicio_video import cli as cli_mod
from simplicio_video import pipeline, render
from simplicio_video.cli import main

SCHEMAS = ROOT / "schemas" / "cli"
NOMES = ["validate-result", "run-result", "render-result", "render-manifest", "preview-manifest"]
CODIGOS = {"CONTRATO_NAO_ENCONTRADO", "CONTRATO_INVALIDO", "RENDER_FALHOU", "FERRAMENTA_AUSENTE"}
SCHEMA_DO_COMANDO = {"validate": "validate-result", "run": "run-result", "render": "render-result"}
H = "ab" * 32  # sha256 de mentira, só para o formato


def _schema(nome):
    return json.loads((SCHEMAS / f"{nome}.schema.json").read_text(encoding="utf8"))


def _erros(nome, dados):
    return [e.message for e in Draft202012Validator(_schema(nome)).iter_errors(dados)]


def _run(argv, capsys):
    try:
        rc = main(argv)
    except SystemExit as e:
        if isinstance(e.code, str):  # SystemExit("texto") é o erro de texto do motor: exit 1 + mensagem no stderr
            print(e.code, file=sys.stderr)
            rc = 1
        else:  # argparse (--help, erro de uso)
            rc = e.code
    out, err = capsys.readouterr()
    return rc, out, err


def _edita(path, fn):
    d = yaml.safe_load(path.read_text(encoding="utf8"))
    fn(d)
    path.write_text(yaml.safe_dump(d, allow_unicode=True, sort_keys=False), encoding="utf8")


def _contrato_invalido(path):
    _edita(path, lambda d: d["cenas"][1].update(duracao_s=0.75))  # soma das cenas != formato.duracao_s


@pytest.fixture
def sem_render(monkeypatch):
    """Falha o teste se algo tentar rodar render (subprocesso). Nenhum teste deste arquivo renderiza vídeo."""
    def proibido(*a, **k):
        raise AssertionError("teste não pode executar render (subprocesso)")
    monkeypatch.setattr(render, "_run", proibido)


def _manifesto_minimo():
    return {
        "schema": "simplicio.render-manifest/v1",
        "contract": "video/contract.yaml",
        "contract_sha256": H,
        "timing_lock_sha256": None,
        "template": "template",
        "backend": "local",
        "quality": "draft",
        "gpu_encode": False,
        "inputs_sha256": H,
        "inputs": {"scripts/build.mjs": H},
        "tools": {"simplicio_video": "0.2.0", "hyperframes": "hyperframes@0.8.97", "node": None, "ffmpeg": None,
                  "python": "3.13.5"},
        "output": {"path": "out/mini.mp4", "sha256": H, "duration_s": 1.0, "frames": 30,
                   "video_frames_sha256": H, "audio_pcm_sha256": H},
        "loudness": {"integrated_lufs": -14.0, "true_peak_dbfs": -1.5},
        "timings_s": {"compile_build": 0.5, "render": 2.0, "capture": None, "encode": None, "master": 0.3},
    }


def _manifesto_previa_minimo():
    return {
        "schema": "simplicio.preview-manifest/v1",
        "contract_sha256": H,
        "inputs_sha256": H,
        "preview": {"path": "out/mini-previa.mp4", "sha256": H, "duration_s": 1.0, "bytes": 2048,
                    "watermark": "Prévia", "logo": None},
        "spec": {"width": 540, "height": 960, "fps": 30, "marca": {"dagua": "Prévia", "credito": None}},
        "timings_s": {"render_total": 2.0, "preview_post": 0.4, "total": 2.4},
    }


# (a) os schemas existem em schemas/cli/ e são JSON Schema válidos

@pytest.mark.parametrize("nome", NOMES)
def test_schema_existe_e_e_json_schema_valido(nome):
    s = _schema(nome)
    Draft202012Validator.check_schema(s)
    assert s["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert s["$id"] == f"simplicio.{nome}/v1"


def test_codigos_de_erro_iguais_nos_tres_resultados():
    for nome in ("validate-result", "run-result", "render-result"):
        assert set(_schema(nome)["$defs"]["erro"]["properties"]["code"]["enum"]) == CODIGOS, nome


# (b) validate --json com contrato válido

def test_validate_json_valido_segue_o_schema(mini, capsys):
    rc, out, _ = _run(["validate", "--json", str(mini)], capsys)
    assert rc == 0
    dados = json.loads(out)
    assert _erros("validate-result", dados) == []
    assert dados["ok"] is True and dados["errors"] == []


# (c) com contrato inválido ou inexistente: ok false e error.code

def test_validate_json_invalido_tem_error_code(mini, capsys):
    _contrato_invalido(mini)
    rc, out, _ = _run(["validate", "--json", str(mini)], capsys)
    assert rc == 1
    dados = json.loads(out)
    assert _erros("validate-result", dados) == []
    assert dados["ok"] is False
    assert dados["error"]["code"] == "CONTRATO_INVALIDO"
    assert any(e.startswith("durations:") for e in dados["errors"])


def test_validate_json_contrato_inexistente_tem_error_code(tmp_path, capsys):
    rc, out, _ = _run(["validate", "--json", str(tmp_path / "nao-existe.yaml")], capsys)
    assert rc == 1
    dados = json.loads(out)
    assert _erros("validate-result", dados) == []
    assert dados["ok"] is False and dados["error"]["code"] == "CONTRATO_NAO_ENCONTRADO"


# (d) texto de validate (sem --json) não muda: texto e exit code

def test_validate_texto_valido_continua_igual(mini, capsys):
    rc, out, _ = _run(["validate", str(mini)], capsys)
    assert rc == 0
    assert out == (
        "aviso  voice: timing.lock.json missing - run `simplicio-video voice <contrato>`\n"
        "aviso  marca.logo is null: text lockup only (never recreate a logo)\n"
        "cenas: a 0-0.5s | b 0.5-1s\n"
        "OK: contrato válido\n"
    )


def test_validate_texto_invalido_continua_igual(mini, capsys):
    _contrato_invalido(mini)
    rc, out, _ = _run(["validate", str(mini)], capsys)
    assert rc == 1
    assert out.startswith("ERRO   durations:")
    assert out.splitlines()[-1].startswith("FALHOU: ")
    assert "{" not in out  # sem JSON no texto


def test_validate_texto_contrato_inexistente_continua_igual(tmp_path, capsys):
    rc, out, err = _run(["validate", str(tmp_path / "nao-existe.yaml")], capsys)
    assert rc == 1
    assert out == ""
    assert "contract not found" in err


# (e) manifestos: o formato gravado em disco valida contra o schema

def test_render_manifest_minimo_valida():
    assert _erros("render-manifest", _manifesto_minimo()) == []


def test_render_manifest_com_dollar_schema_opcional_valida():
    man = {"$schema": "schemas/cli/render-manifest.schema.json", **_manifesto_minimo()}
    assert _erros("render-manifest", man) == []


def test_render_manifest_sem_campo_obrigatorio_falha():
    man = _manifesto_minimo()
    del man["contract_sha256"]
    assert _erros("render-manifest", man)


def test_render_manifest_backend_desconhecido_falha():
    man = {**_manifesto_minimo(), "backend": "remoto"}
    assert _erros("render-manifest", man)


def test_preview_manifest_minimo_valida():
    assert _erros("preview-manifest", _manifesto_previa_minimo()) == []


def test_manifestos_reais_do_repo_seguem_o_schema():
    reais = sorted((ROOT / "clients").glob("**/render.manifest.json"))
    assert reais, "o repo tem render.manifest.json de clientes para conferir"
    for p in reais:
        assert _erros("render-manifest", json.loads(p.read_text(encoding="utf8"))) == [], str(p)


# (f) run --json e render --json estão registrados no parser

@pytest.mark.parametrize("sub", ["validate", "run", "render"])
def test_help_mostra_json(sub, capsys):
    rc, out, _ = _run([sub, "--help"], capsys)
    assert rc == 0
    assert "--json" in out


# (g) run --json: resumo válido segue run-result; erro vira error.code

def test_run_json_valido_segue_o_schema(mini, monkeypatch, capsys):
    steps = {
        "voice": {"provider": "file", "lines": {"vo1": 0.3}, "usage": None},
        "render": {"backend": "local", "output": str(mini.parent / "out" / "mini.mp4"),
                   "loudness": {"integrated_lufs": -14.0, "true_peak_dbfs": -1.5}, "usage": None},
    }
    monkeypatch.setattr(pipeline, "run_all", lambda *a, **k: dict(steps))
    rc, out, _ = _run(["run", "--json", str(mini)], capsys)
    assert rc == 0
    dados = json.loads(out)
    assert _erros("run-result", dados) == []
    assert dados["ok"] is True
    assert dados["voice"]["provider"] == "file" and dados["render"]["backend"] == "local"


def test_run_json_contrato_invalido_tem_error_code(mini, sem_render, capsys):
    _contrato_invalido(mini)
    rc, out, _ = _run(["run", "--json", str(mini)], capsys)
    assert rc == 1
    dados = json.loads(out)
    assert _erros("run-result", dados) == []
    assert dados["ok"] is False and dados["error"]["code"] == "CONTRATO_INVALIDO"


# (h) contrato inexistente em validate, run e render: mesmo código, mesmo exit code

@pytest.mark.parametrize("cmd", ["validate", "run", "render"])
def test_contrato_inexistente_em_json_tem_error_code(cmd, tmp_path, sem_render, capsys):
    rc, out, _ = _run([cmd, "--json", str(tmp_path / "nao-existe.yaml")], capsys)
    assert rc == 1
    dados = json.loads(out)
    assert _erros(SCHEMA_DO_COMANDO[cmd], dados) == []
    assert dados["ok"] is False and dados["error"]["code"] == "CONTRATO_NAO_ENCONTRADO"


# (i) render --json: resultado válido, contrato inválido e erros de ferramenta

def test_render_json_valido_segue_o_schema(mini, monkeypatch, capsys):
    def render_falso(c, backend, **kw):  # mesmo retorno de render_local: o manifesto gravado
        return _manifesto_minimo()

    monkeypatch.setattr(cli_mod, "do_render", render_falso)
    rc, out, _ = _run(["render", "--json", str(mini)], capsys)
    assert rc == 0
    dados = json.loads(out)
    assert _erros("render-result", dados) == []
    assert dados["ok"] is True and dados["backend"] == "local"


def test_render_json_contrato_invalido_tem_error_code(mini, sem_render, capsys):
    _contrato_invalido(mini)  # a validação roda antes de qualquer subprocesso
    rc, out, _ = _run(["render", "--json", str(mini)], capsys)
    assert rc == 1
    dados = json.loads(out)
    assert _erros("render-result", dados) == []
    assert dados["ok"] is False and dados["error"]["code"] == "CONTRATO_INVALIDO"


@pytest.mark.parametrize("exc,codigo", [
    (SystemExit("command failed (1): npx --yes hyperframes render\nboom"), "RENDER_FALHOU"),
    (FileNotFoundError(2, "No such file or directory", "npx"), "FERRAMENTA_AUSENTE"),
])
def test_render_json_falha_de_render_tem_error_code(exc, codigo, mini, monkeypatch, capsys):
    def falha(*a, **k):
        raise exc

    monkeypatch.setattr(cli_mod, "do_render", falha)
    rc, out, _ = _run(["render", "--json", str(mini)], capsys)
    assert rc == 1
    dados = json.loads(out)
    assert _erros("render-result", dados) == []
    assert dados["ok"] is False and dados["error"]["code"] == codigo
