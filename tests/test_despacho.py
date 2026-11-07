"""U23: the dispatch of a render leaves the CLI (`despacho.do_render`) and the domain stops importing the CLI.

Before this change `pipeline.run_all` and `mcp_server.video_render` did `from .cli import do_render` (the domain imported the CLI:
`cli -> pipeline -> cli` and `cli -> mcp_server -> cli` was ONE strongly connected component of three modules), and the rule
"which file did this render deliver: the MP4 and its manifest, or only the colab bundle" lived in `cli._render_json`, in the CLI,
not with the code that dispatches.

Two kinds of test:

* CHARACTERIZATION (green before and after, through `cli.do_render`, `cli.main` and the MCP tool; the fakes sit at the LEAF
  (`render.render_local`, `render.render_colab`, `remote.render_kaggle`, `remote.render_colab_cli`) so the same test measures the
  old and the new place of the function): which backend a name picks and with which arguments, "none|cpu -> None" and the
  accelerator defaults, an unknown backend falls to local, colab returns the bundle result untouched, and `render --json` /
  `run --json` / `video.render` print what they always printed;
* STRUCTURE (red before): `despacho.do_render` exists with the signature of `cli.do_render`, `cli.do_render` is the same object
  (re-exported, lazily, so `--help` does not load one more module), `import simplicio_video.despacho` does not load the CLI,
  no strongly connected component of the import graph (lazy imports included) holds `cli`, `pipeline` and `mcp_server`
  together, and the rule of what a render delivered (`despacho.saida_do_render`).
"""
from __future__ import annotations

import ast
import inspect
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from helpers import offline_env, SRC
from simplicio_video import cli, mcp_server, pipeline, remote, render
from simplicio_video import contract as ct

H = "ab" * 32

# the signature of `cli.do_render` on origin/main (c6e0391): note `gpu_encode` between `timeout` and `log`
PARAMETROS = [("c", inspect.Parameter.empty), ("backend", inspect.Parameter.empty), ("out", None), ("quality", None),
              ("workdir", None), ("gpu", False), ("accelerator", None), ("timeout", 3600), ("gpu_encode", "auto"), ("log", print)]


# ------------------------------------------------------------------------------------------------------- the fake backends

RETORNOS = {
    "local": {"backend": "local", "output": {"path": "out/mini.mp4"}, "loudness": {"integrated_lufs": -14.0}, "usage": None},
    "kaggle": {"backend": "kaggle", "output": {"path": "out/mini.mp4"}, "loudness": {"integrated_lufs": -14.0},
               "usage": {"credits": 1}},
    "colab-cli": {"backend": "colab-cli", "output": {"path": "out/mini.mp4"}, "loudness": {"integrated_lufs": -14.0},
                  "usage": {"credits": 2}},
    "colab": {"bundle": "/nao/importa/mini.colab-bundle.zip", "bundle_sha256": H, "notebook": "/nao/importa/colab/render.ipynb"},
}
# the name of the leaf each backend ends in
FOLHA = {"local": "render_local", "kaggle": "render_kaggle", "colab-cli": "render_colab_cli", "colab": "render_colab"}


@pytest.fixture
def folhas(monkeypatch):
    """The four leaves replaced by recorders: `chamadas` is [(leaf name, args, kwargs)], each returns RETORNOS[backend] (a copy).
    Nothing in this file may reach a subprocess: `render._run` fails the test."""
    chamadas: list[tuple[str, tuple, dict]] = []

    def grava(nome: str, backend: str, modulo):
        def falso(*a, **k):
            chamadas.append((nome, a, k))
            return dict(RETORNOS[backend])
        monkeypatch.setattr(modulo, nome, falso)

    for backend, nome in FOLHA.items():
        grava(nome, backend, render if backend in ("local", "colab") else remote)

    def proibido(*a, **k):
        raise AssertionError("teste não pode executar render (subprocesso)")
    monkeypatch.setattr(render, "_run", proibido)
    return chamadas


def _main(argv, capsys):
    try:
        rc = cli.main(argv)
    except SystemExit as e:
        rc = e.code
    out, err = capsys.readouterr()
    return rc, out, err


# ------------------------------------------------------------------ characterization: which backend, with which arguments

def test_a_assinatura_do_do_render_da_cli_nao_mudou():
    sig = inspect.signature(cli.do_render)
    assert [(p.name, p.default) for p in sig.parameters.values()] == PARAMETROS
    assert all(p.kind is inspect.Parameter.POSITIONAL_OR_KEYWORD for p in sig.parameters.values())
    assert sig.return_annotation in (dict, "dict")


def test_cada_backend_chama_so_a_sua_folha_com_os_argumentos_de_sempre(folhas):
    c, log, out, wd = object(), print, Path("x.mp4"), Path("wd")
    todos = dict(out=out, quality="draft", workdir=wd, gpu=True, timeout=77, gpu_encode="0", log=log)
    esperado = {
        "local": ("render_local", {"out": out, "quality": "draft", "workdir": wd, "gpu": True, "log": log}),
        "kaggle": ("render_kaggle", {"out": out, "quality": "draft", "timeout_s": 77, "gpu_encode": "0", "log": log,
                                     "accelerator": "NvidiaTeslaT4"}),
        "colab-cli": ("render_colab_cli", {"out": out, "quality": "draft", "timeout_s": 77, "gpu_encode": "0", "log": log,
                                           "gpu": "T4"}),
        "colab": ("render_colab", {"out": out, "quality": "draft", "gpu_encode": "0", "log": log}),
    }
    for backend, (folha, kwargs) in esperado.items():
        folhas.clear()
        r = cli.do_render(c, backend, **todos)
        assert folhas == [(folha, (c,), kwargs)], backend
        assert r == RETORNOS[backend], backend


def test_so_o_local_aceita_o_workdir_e_o_gpu_e_so_os_remotos_o_timeout_e_o_gpu_encode(folhas):
    cli.do_render(object(), "local", gpu_encode="1", timeout=5)
    cli.do_render(object(), "kaggle", workdir=Path("w"), gpu=True)
    (_, _, local), (_, _, kaggle) = folhas
    assert "gpu_encode" not in local and "timeout_s" not in local
    assert "workdir" not in kaggle and "gpu" not in kaggle


def test_um_backend_desconhecido_cai_no_local(folhas):
    """The CLI limits `--backend` to four names, but the MCP tool takes free text: anything else renders locally."""
    for nome in ("", "LOCAL", "Kaggle", "nuvem", "colab-cli "):
        folhas.clear()
        cli.do_render(object(), nome, quality="looks")
        assert [f[0] for f in folhas] == ["render_local"], nome
        assert folhas[0][2]["quality"] == "looks"


# ------------------------------------------- characterization: "none|cpu -> None" and the accelerator defaults (cli.py:88-96)

@pytest.mark.parametrize("acelerador,esperado", [
    (None, "NvidiaTeslaT4"),        # not given: the default of the backend
    ("none", None), ("NONE", None), ("None", None), ("cpu", None), ("CPU", None), ("Cpu", None),   # CPU: None, any case
    ("NvidiaL4", "NvidiaL4"), ("NvidiaTeslaT4", "NvidiaTeslaT4"), ("T4", "T4"),                   # anything else goes as typed
    ("", ""),                       # an empty text is "given" and is not none|cpu: it goes as typed
    (" cpu", " cpu"), ("cpu ", "cpu "), (" none", " none"), ("none ", "none "),   # no strip: with a blank it is not none|cpu
])
def test_kaggle_normaliza_none_e_cpu_para_none_e_usa_a_t4_quando_nao_ha_acelerador(folhas, acelerador, esperado):
    cli.do_render(object(), "kaggle", accelerator=acelerador)
    assert folhas[0][0] == "render_kaggle" and folhas[0][2]["accelerator"] == esperado
    assert ("accelerator" in folhas[0][2]) and "gpu" not in folhas[0][2]


@pytest.mark.parametrize("acelerador,esperado", [
    (None, "T4"),
    ("none", None), ("NONE", None), ("cpu", None), ("CPU", None), ("Cpu", None),
    ("L4", "L4"), ("A100", "A100"), ("T4", "T4"), ("NvidiaTeslaT4", "NvidiaTeslaT4"),
    ("", ""), (" cpu", " cpu"), ("cpu ", "cpu "), (" none", " none"), ("none ", "none "),
])
def test_colab_cli_normaliza_none_e_cpu_para_none_e_usa_a_t4_quando_nao_ha_acelerador(folhas, acelerador, esperado):
    cli.do_render(object(), "colab-cli", accelerator=acelerador)
    assert folhas[0][0] == "render_colab_cli" and folhas[0][2]["gpu"] == esperado
    assert "accelerator" not in folhas[0][2]


@pytest.mark.parametrize("backend", ["local", "colab"])
@pytest.mark.parametrize("acelerador", [None, "none", "cpu", "A100", "NvidiaL4"])
def test_o_local_e_o_colab_nao_recebem_acelerador_nenhum(folhas, backend, acelerador):
    cli.do_render(object(), backend, accelerator=acelerador)
    assert not {"accelerator", "gpu_accelerator"} & set(folhas[0][2])
    assert folhas[0][0] == FOLHA[backend]


def test_o_acelerador_none_do_pipeline_e_do_mcp_chega_como_none_ao_remoto(mini, folhas):
    """`pipeline.run_all` and `video.render` go through the same dispatch, so a `none` typed there is the CPU as well."""
    pipeline.run_all(mini, backend="kaggle", accelerator="cpu", log=lambda *m: None)
    assert [f[0] for f in folhas] == ["render_kaggle"] and folhas[0][2]["accelerator"] is None
    folhas.clear()
    mcp_server.video_render(str(mini), backend="colab-cli", accelerator="none")
    assert [f[0] for f in folhas] == ["render_colab_cli"] and folhas[0][2]["gpu"] is None


# ------------------------------------------------------------------------ characterization: colab hands back the bundle

def test_o_colab_devolve_o_resultado_do_bundle_sem_mexer_e_nao_toca_em_outra_folha(folhas):
    r = cli.do_render(object(), "colab", quality="delivery", accelerator="A100", timeout=5)
    assert [f[0] for f in folhas] == ["render_colab"]
    assert r == RETORNOS["colab"] and r["bundle"].endswith(".colab-bundle.zip") and "output" not in r


@pytest.mark.parametrize("backend", ["local", "kaggle", "colab-cli"])
def test_so_o_colab_nao_tem_output_nem_manifesto_os_outros_tem_output(folhas, backend):
    r = cli.do_render(object(), backend)
    assert isinstance(r["output"], dict) and "bundle" not in r


# ---------------------------------------------------- characterization: `render --json` / `run --json` / `video.render`

def _esperado_render_json(mini, backend):
    c = ct.load(mini)
    if backend == "colab":
        saida, manifesto = RETORNOS["colab"]["bundle"], None
    else:
        saida, manifesto = str((c.dir / "out/mini.mp4").resolve()), str(c.dir / "render.manifest.json")
    return {"ok": True, "contrato": str(c.path), "backend": backend, "preview": False, "output": saida, "manifest": manifesto}


@pytest.mark.parametrize("backend", ["local", "kaggle", "colab-cli", "colab"])
def test_render_json_imprime_o_mesmo_para_cada_backend(mini, folhas, capsys, backend):
    rc, out, _ = _main(["render", "--json", str(mini), "--backend", backend], capsys)
    assert rc == 0 and [f[0] for f in folhas] == [FOLHA[backend]]
    assert json.loads(out) == _esperado_render_json(mini, backend)
    assert list(json.loads(out)) == ["ok", "contrato", "backend", "preview", "output", "manifest"]


def test_render_json_repassa_as_opcoes_da_linha_de_comando_ao_despacho(mini, folhas, capsys):
    rc, _, _ = _main(["render", "--json", str(mini), "--backend", "kaggle", "--accelerator", "none", "--timeout", "90",
                      "--quality", "draft", "--gpu-encode", "0", "--out", str(mini.parent / "x.mp4")], capsys)
    k = folhas[0][2]
    assert rc == 0 and callable(k.pop("log"))  # the CLI passes its own stderr logger
    assert k == {"out": mini.parent / "x.mp4", "quality": "draft", "timeout_s": 90, "gpu_encode": "0", "accelerator": None}
    folhas.clear()
    rc, _, _ = _main(["render", "--json", str(mini), "--gpu", "--workdir", str(mini.parent / "w")], capsys)
    k = folhas[0][2]
    assert rc == 0 and callable(k.pop("log"))
    assert k == {"out": None, "quality": None, "workdir": mini.parent / "w", "gpu": True}


@pytest.mark.parametrize("backend", ["local", "kaggle", "colab-cli", "colab"])
def test_render_sem_json_chama_a_mesma_folha_e_nao_imprime_json(mini, folhas, capsys, backend):
    rc, out, _ = _main(["render", str(mini), "--backend", backend], capsys)
    assert rc == 0 and [f[0] for f in folhas] == [FOLHA[backend]] and "{" not in out
    assert callable(folhas[0][2]["log"]) and folhas[0][2]["log"] is print


@pytest.mark.parametrize("backend", ["local", "kaggle", "colab-cli", "colab"])
def test_run_json_imprime_o_mesmo_para_cada_backend(mini, folhas, capsys, backend):
    rc, out, _ = _main(["run", "--json", str(mini), "--backend", backend], capsys)
    dados = json.loads(out)
    assert rc == 0 and [f[0] for f in folhas] == [FOLHA[backend]]
    assert list(dados) == ["ok", "contrato", "voice", "render"]
    assert dados["ok"] is True and dados["contrato"] == str(Path(mini).resolve())
    assert dados["voice"]["provider"] == "file" and set(dados["voice"]["lines"]) == {"vo1"}
    r = RETORNOS[backend]
    assert dados["render"] == {"backend": backend, "output": r["bundle"] if backend == "colab" else "out/mini.mp4",
                               "loudness": r.get("loudness"), "usage": r.get("usage")}


def test_o_pipeline_repassa_o_log_e_o_que_o_chamador_deu_ao_despacho(mini, folhas):
    logs = []
    log = lambda *m: logs.append(" ".join(map(str, m)))  # noqa: E731
    res = pipeline.run_all(mini, backend="colab-cli", accelerator="L4", quality="draft", timeout=11, log=log)
    (nome, args, k), = folhas
    assert nome == "render_colab_cli" and k == {"out": None, "quality": "draft", "timeout_s": 11, "gpu_encode": "auto", "log": log,
                                                 "gpu": "L4"}
    assert res["render"] == {"backend": "colab-cli", "output": "out/mini.mp4", "loudness": {"integrated_lufs": -14.0},
                             "usage": {"credits": 2}}
    assert any(m.startswith("[3/3] render --backend colab-cli") for m in logs)


@pytest.mark.parametrize("backend", ["local", "kaggle", "colab-cli", "colab"])
def test_a_tool_video_render_devolve_so_as_chaves_de_sempre(mini, folhas, backend):
    r = mcp_server.video_render(str(mini), backend=backend, quality="draft")
    assert r["ok"] is True and [f[0] for f in folhas] == [FOLHA[backend]]
    # the tool lets through backend, output, loudness, usage, inputs_sha256, bundle, notebook, timings_s: not `bundle_sha256`
    assert r["result"] == {k: v for k, v in RETORNOS[backend].items() if k != "bundle_sha256"}
    assert folhas[0][2]["quality"] == "draft" and folhas[0][2]["out"] is None


def test_a_tool_video_render_converte_out_em_path_e_filtra_as_chaves_alheias(mini, monkeypatch, tmp_path):
    visto = {}

    def falso(c, **k):
        visto.update(k)
        return {"backend": "local", "output": {"path": "o.mp4"}, "files": ["a"], "compile_build_s": 1.0, "loudness": None}

    monkeypatch.setattr(render, "render_local", falso)
    r = mcp_server.video_render(str(mini), out=str(tmp_path / "x.mp4"))
    assert visto["out"] == tmp_path / "x.mp4" and isinstance(visto["out"], Path)
    assert r["result"] == {"backend": "local", "output": {"path": "o.mp4"}, "loudness": None}  # `files` and the timing do not pass


# ------------------------------------------- characterization: every option reaches the leaf, with and without `--json`

def _opcoes_esperadas(backend: str, out: Path, wd: Path) -> dict:
    """What each leaf receives (besides `log`) when `render` is run with every option set; the accelerator is `L4`, not the default."""
    return {
        "local": {"out": out, "quality": "delivery", "workdir": wd, "gpu": True},
        "kaggle": {"out": out, "quality": "delivery", "timeout_s": 91, "gpu_encode": "1", "accelerator": "L4"},
        "colab-cli": {"out": out, "quality": "delivery", "timeout_s": 91, "gpu_encode": "1", "gpu": "L4"},
        "colab": {"out": out, "quality": "delivery", "gpu_encode": "1"},
    }[backend]


@pytest.mark.parametrize("com_json", [False, True], ids=["texto", "json"])
@pytest.mark.parametrize("backend", ["local", "kaggle", "colab-cli", "colab"])
def test_render_repassa_cada_opcao_da_linha_de_comando_a_folha_do_backend(mini, folhas, capsys, backend, com_json):
    out, wd = mini.parent / "x.mp4", mini.parent / "w"
    argv = ["render", str(mini), "--backend", backend, "--out", str(out), "--quality", "delivery", "--workdir", str(wd), "--gpu",
            "--accelerator", "L4", "--timeout", "91", "--gpu-encode", "1"] + (["--json"] if com_json else [])
    rc, _, _ = _main(argv, capsys)
    assert rc == 0 and [f[0] for f in folhas] == [FOLHA[backend]]
    k = dict(folhas[0][2])
    log = k.pop("log")
    assert k == _opcoes_esperadas(backend, out, wd)
    assert (callable(log) and log is not print) if com_json else log is print  # --json logs to stderr, the text mode prints


@pytest.mark.parametrize("backend", ["local", "kaggle", "colab-cli", "colab"])
def test_a_tool_video_render_repassa_cada_argumento_a_folha_do_backend(mini, folhas, tmp_path, backend):
    out = tmp_path / "x.mp4"
    r = mcp_server.video_render(str(mini), backend=backend, accelerator="L4", quality="delivery", out=str(out), timeout=77)
    assert r["ok"] is True and [f[0] for f in folhas] == [FOLHA[backend]]
    k = dict(folhas[0][2])
    assert callable(k.pop("log"))
    esperado = {  # the tool has no workdir, gpu or gpu_encode: the defaults of the dispatch
        "local": {"out": out, "quality": "delivery", "workdir": None, "gpu": False},
        "kaggle": {"out": out, "quality": "delivery", "timeout_s": 77, "gpu_encode": "auto", "accelerator": "L4"},
        "colab-cli": {"out": out, "quality": "delivery", "timeout_s": 77, "gpu_encode": "auto", "gpu": "L4"},
        "colab": {"out": out, "quality": "delivery", "gpu_encode": "auto"},
    }[backend]
    assert k == esperado and isinstance(k["out"], Path)


def test_a_tool_video_render_deixa_passar_so_as_oito_chaves_na_ordem_de_sempre(mini, monkeypatch):
    """Every key a backend may return, and then some: the tool keeps `backend output loudness usage inputs_sha256 bundle notebook
    timings_s` (that order), nothing else."""
    tudo = {"backend": "local", "output": {"path": "o.mp4"}, "loudness": {"integrated_lufs": -14.0}, "usage": {"credits": 3},
            "inputs_sha256": H, "bundle": "/b.zip", "notebook": "/nb.ipynb", "timings_s": {"render": 2.0},
            "files": ["a"], "compile_build_s": 1.0, "bundle_sha256": H, "tools": {"node": "v22"}, "schema": "x"}
    monkeypatch.setattr(render, "render_local", lambda c, **k: dict(tudo))
    r = mcp_server.video_render(str(mini))
    chaves = ["backend", "output", "loudness", "usage", "inputs_sha256", "bundle", "notebook", "timings_s"]
    assert list(r["result"]) == chaves and r["result"] == {k: tudo[k] for k in chaves}


# ------------------------------------------------ what moving the name changes: the `cli.do_render` of the CLI is read-only now

def test_patchar_cli_do_render_nao_tem_mais_efeito_em_nenhum_dos_cinco_chamadores(mini, folhas, monkeypatch, capsys):
    """The target of a monkeypatch of the dispatch is `despacho.do_render`. `cli.do_render` is the same function under a lazy
    name, and the callers (`render`, `render --json`, `run`, `run --json`, `video.render`) read `despacho.do_render`."""
    vistas = []

    def boom(*a, **k):
        vistas.append(a)
        raise AssertionError("o patch em cli.do_render nao deveria chegar aos chamadores")

    try:
        with monkeypatch.context() as m:
            m.setattr(cli, "do_render", boom, raising=False)
            assert _main(["render", str(mini)], capsys)[0] == 0
            assert _main(["render", "--json", str(mini)], capsys)[0] == 0
            assert _main(["run", str(mini)], capsys)[0] == 0
            assert _main(["run", "--json", str(mini)], capsys)[0] == 0
            assert mcp_server.video_render(str(mini))["ok"] is True
    finally:
        cli.__dict__.pop("do_render", None)  # monkeypatch puts the old value back as a plain attribute: leave the module as found
    assert vistas == [] and [f[0] for f in folhas] == ["render_local"] * 5


def test_o_do_render_da_cli_e_um_nome_tardio_sem_guardar_nada_no_modulo():
    """Effects of the lazy re-export (PEP 562), pinned: reading it does not put it in the module (`vars`, `dir`, `import *`),
    it cannot be deleted, and the function says it lives in `despacho`."""
    codigo = ("import json\nfrom simplicio_video import cli\n"
              "antes = 'do_render' in vars(cli)\nfn = cli.do_render\nser = 'do_render' in vars(cli)\n"
              "ns = {}\nexec('from simplicio_video.cli import *', ns)\n"
              "try:\n    delattr(cli, 'do_render')\n    del_ = 'sem erro'\nexcept AttributeError:\n    del_ = 'AttributeError'\n"
              "print(json.dumps({'antes': antes, 'depois': ser, 'dir': 'do_render' in dir(cli), 'estrela': 'do_render' in ns,\n"
              "                  'del': del_, 'modulo': fn.__module__, 'ainda_le': callable(cli.do_render)}))")
    r = subprocess.run([sys.executable, "-c", codigo], capture_output=True, text=True, timeout=60, env=offline_env())
    assert r.returncode == 0, r.stderr[-600:]
    assert json.loads(r.stdout) == {"antes": False, "depois": False, "dir": False, "estrela": False, "del": "AttributeError",
                                    "modulo": "simplicio_video.despacho", "ainda_le": True}


# ---------------------------------------------------------------------------------------------- structure (red before)

def test_o_despacho_existe_com_a_assinatura_de_sempre():
    from simplicio_video import despacho
    sig = inspect.signature(despacho.do_render)
    assert [(p.name, p.default) for p in sig.parameters.values()] == PARAMETROS
    assert all(p.kind is inspect.Parameter.POSITIONAL_OR_KEYWORD for p in sig.parameters.values())
    assert sig.return_annotation in (dict, "dict")
    assert str(sig) == str(inspect.signature(cli.do_render))


def test_cli_do_render_e_o_mesmo_objeto_do_despacho():
    from simplicio_video import despacho
    from simplicio_video.cli import do_render
    assert cli.do_render is despacho.do_render and do_render is despacho.do_render
    assert despacho.do_render.__module__ == "simplicio_video.despacho"


def test_o_despacho_nao_importa_a_cli_nem_o_resto_do_dominio_quando_e_importado():
    codigo = ("import json, sys\nimport simplicio_video.despacho\n"
              "print(json.dumps(sorted(m for m in sys.modules if m.startswith('simplicio_video'))))")
    r = subprocess.run([sys.executable, "-c", codigo], capture_output=True, text=True, timeout=60, env=offline_env())
    assert r.returncode == 0, r.stderr[-600:]  # red before: No module named 'simplicio_video.despacho'
    carregados = set(json.loads(r.stdout))
    assert "simplicio_video.despacho" in carregados
    # no CLI, and not what the CLI imports to run a command: the backends are read when a render is dispatched
    assert carregados & {"simplicio_video.cli", "simplicio_video.pipeline", "simplicio_video.mcp_server",
                         "simplicio_video.render", "simplicio_video.remote"} == set(), sorted(carregados)


def test_o_despacho_nao_importa_a_cli_nem_o_pipeline_nem_o_servidor_mcp_no_fonte():
    assert (SRC / "despacho.py").is_file()  # red before: the module does not exist
    assert _modulos_importados("despacho.py") & {"cli", "pipeline", "mcp_server"} == set()


def test_o_import_da_cli_e_o_help_nao_carregam_o_despacho_mas_cli_do_render_o_carrega_sob_demanda():
    """`cli.do_render` is a lazy re-export (PEP 562 `__getattr__`): a top-level import would be one more module in every `--help`."""
    codigo = ("import io, contextlib, json, sys\nfrom simplicio_video import cli\n"
              "try:\n    with contextlib.redirect_stdout(io.StringIO()):\n        cli.main(['--help'])\nexcept SystemExit:\n    pass\n"
              "antes = sorted(m for m in sys.modules if m.startswith('simplicio_video'))\n"
              "fn = cli.do_render\n"
              "from simplicio_video import despacho\n"
              "print(json.dumps({'antes': antes, 'mesmo': fn is despacho.do_render, 'depois': 'simplicio_video.despacho' in sys.modules}))")
    r = subprocess.run([sys.executable, "-c", codigo], capture_output=True, text=True, timeout=60, env=offline_env())
    assert r.returncode == 0, r.stderr[-600:]
    d = json.loads(r.stdout)
    assert not {"simplicio_video.despacho", "simplicio_video.render", "simplicio_video.remote", "simplicio_video.pipeline",
                "simplicio_video.mcp_server"} & set(d["antes"]), d["antes"]
    assert d["mesmo"] is True and d["depois"] is True


def test_a_cli_continua_recusando_um_nome_que_nao_existe_e_a_outra_leitura_tardia_segue_de_pe():
    """`cli.__getattr__` serves two names, `MAIN_DESC` and `do_render`; any other still is an AttributeError."""
    assert not hasattr(cli, "nao_existe") and not hasattr(cli, "do_renderx")
    with pytest.raises(AttributeError, match="has no attribute 'nao_existe'"):
        cli.nao_existe  # noqa: B018
    assert cli.MAIN_DESC.startswith("simplicio-video ")


def test_o_alvo_do_monkeypatch_do_render_e_o_despacho_para_a_cli_o_pipeline_e_o_servidor_mcp(mini, folhas, monkeypatch, capsys):
    """The three callers read `despacho.do_render` when they render, so a test patches ONE name (the old target, `cli.do_render`,
    is the same function by another name: patching it changes nothing for them)."""
    from simplicio_video import despacho
    vistas: list[tuple[str, str]] = []

    def falso(c, backend, **k):
        vistas.append((backend, k.get("accelerator")))
        return dict(RETORNOS["kaggle"])

    monkeypatch.setattr(despacho, "do_render", falso)
    assert _main(["render", "--json", str(mini), "--backend", "kaggle", "--accelerator", "L4"], capsys)[0] == 0
    assert _main(["render", str(mini), "--backend", "kaggle", "--accelerator", "L4"], capsys)[0] == 0
    pipeline.run_all(mini, backend="kaggle", accelerator="L4", log=lambda *m: None)
    assert mcp_server.video_render(str(mini), backend="kaggle", accelerator="L4")["result"]["usage"] == {"credits": 1}
    assert vistas == [("kaggle", "L4")] * 4 and folhas == []  # no leaf was reached: the patch caught all four calls


# ------------------------------------------------------------------------------------ the import graph, lazy imports included

def _arquivos_do_pacote() -> dict[str, Path]:
    """Dotted module name -> source file, for every module of the package (a subpackage is its `__init__.py`; the root one is left out)."""
    achados = {}
    for p in sorted(SRC.rglob("*.py")):
        rel = p.relative_to(SRC).with_suffix("")
        if "__pycache__" in p.parts or rel == Path("__init__"):
            continue
        achados[".".join(rel.parts[:-1] if rel.name == "__init__" else rel.parts)] = p
    return achados


def _importados_de(nome: str, arquivos: dict[str, Path]) -> set[str]:
    """The modules of the package that module `nome` imports anywhere in its source, at the top or inside a function (a lazy import
    is an edge too): `from . import x`, `from .x import y`, `from .pkg import mod`, `import simplicio_video.x`."""
    arquivo = arquivos[nome]
    partes = nome.split(".")
    pacote_de_nome = partes if arquivo.name == "__init__.py" else partes[:-1]
    achados: set[str] = set()
    for no in ast.walk(ast.parse(arquivo.read_text(encoding="utf-8"))):
        alvos: list[str] = []
        if isinstance(no, ast.ImportFrom):
            if no.level:
                raiz = pacote_de_nome[:len(pacote_de_nome) - (no.level - 1)]
                base = ".".join(raiz + ([no.module] if no.module else []))
            elif (no.module or "").split(".")[0] == "simplicio_video":
                base = ".".join((no.module or "").split(".")[1:])
            else:
                continue
            alvos = [base, *[(base + "." + a.name).lstrip(".") for a in no.names]]
        elif isinstance(no, ast.Import):
            alvos = [a.name.removeprefix("simplicio_video.") for a in no.names if a.name.startswith("simplicio_video.")]
        achados |= {a for a in alvos if a in arquivos and a != nome}
    return achados


def _modulos_importados(arquivo: str) -> set[str]:
    """`_importados_de` for the module in file `arquivo` (relative to the package, e.g. "pipeline.py")."""
    arquivos = _arquivos_do_pacote()
    nome = next(n for n, p in arquivos.items() if p == SRC / arquivo)
    return _importados_de(nome, arquivos)


def _grafo_do_pacote() -> dict[str, set[str]]:
    arquivos = _arquivos_do_pacote()
    return {nome: _importados_de(nome, arquivos) for nome in arquivos}


def _componentes(grafo: dict[str, set[str]]) -> list[list[str]]:
    """Tarjan: the strongly connected components with more than one module (the measure that said `cli <-> pipeline <-> mcp_server`)."""
    indice: dict[str, int] = {}
    baixo: dict[str, int] = {}
    pilha: list[str] = []
    na_pilha: set[str] = set()
    achados: list[list[str]] = []

    def visita(v: str) -> None:
        indice[v] = baixo[v] = len(indice)
        pilha.append(v)
        na_pilha.add(v)
        for w in sorted(grafo.get(v, ())):
            if w not in indice:
                visita(w)
                baixo[v] = min(baixo[v], baixo[w])
            elif w in na_pilha:
                baixo[v] = min(baixo[v], indice[w])
        if baixo[v] == indice[v]:
            comp = []
            while True:
                w = pilha.pop()
                na_pilha.discard(w)
                comp.append(w)
                if w == v:
                    break
            if len(comp) > 1:
                achados.append(sorted(comp))

    for v in sorted(grafo):
        if v not in indice:
            visita(v)
    return sorted(achados)


def test_o_medidor_de_ciclos_acha_um_ciclo_de_tres_e_ignora_o_que_nao_e_ciclo():
    """The measure itself, on a toy graph: if it could not see a cycle the structure tests below would pass for nothing."""
    toy = {"a": {"b"}, "b": {"c"}, "c": {"a", "d"}, "d": {"e"}, "e": set(), "f": {"f2"}, "f2": {"f"}}
    assert _componentes(toy) == [["a", "b", "c"], ["f", "f2"]]
    assert _componentes({"a": {"b"}, "b": set()}) == []


def test_o_grafo_do_pacote_enxerga_os_imports_tardios_e_os_relativos():
    g = _grafo_do_pacote()
    assert {"pipeline", "mcp_server", "render", "remote"} <= set(g)
    assert "pipeline" in g["cli"] and "voice" in g["pipeline"]  # `from . import pipeline` / `from . import voice` inside a function
    assert {"commands", "commands.doctor"} <= g["cli"]  # `from .commands import doctor` -> a module of a subpackage


def test_nenhum_ciclo_de_import_junta_a_cli_o_pipeline_e_o_servidor_mcp():
    comps = _componentes(_grafo_do_pacote())
    juntos = [c for c in comps if {"cli", "pipeline", "mcp_server"} <= set(c)]
    assert juntos == [], juntos  # red before: [['cli', 'mcp_server', 'pipeline']]
    # and the pipeline, the domain, is in no cycle with the CLI or with the server
    assert [c for c in comps if "pipeline" in c] == [], comps


def test_o_pipeline_nao_importa_a_cli_e_despacha_pelo_despacho():
    imp = _modulos_importados("pipeline.py")
    assert "cli" not in imp and "despacho" in imp, imp


def test_o_servidor_mcp_despacha_o_render_pelo_despacho_e_nao_pela_cli_no_do_render():
    arvore = ast.parse((SRC / "mcp_server.py").read_text(encoding="utf-8"))
    de_cli = {a.name for no in ast.walk(arvore) if isinstance(no, ast.ImportFrom) and no.level == 1 and no.module == "cli"
              for a in no.names}
    de_despacho = {a.name for no in ast.walk(arvore) if isinstance(no, ast.ImportFrom) and no.level == 1 and no.module == "despacho"
                   for a in no.names}
    assert "do_render" not in de_cli and de_despacho == {"do_render"}


# --------------------------------------------------------- the rule "what did the render deliver" (red before: lived in the CLI)

def _contrato(tmp_path):
    return SimpleNamespace(dir=tmp_path / "video")


def test_saida_do_render_do_mp4_e_o_manifesto_ao_lado_do_contrato(tmp_path):
    from simplicio_video import despacho
    c = _contrato(tmp_path)
    for backend in ("local", "kaggle", "colab-cli"):
        assert despacho.saida_do_render(c, RETORNOS[backend]) == (c.dir / "out/mini.mp4", c.dir / "render.manifest.json")


def test_saida_do_render_do_colab_e_so_o_bundle_sem_manifesto(tmp_path):
    from simplicio_video import despacho
    c = _contrato(tmp_path)
    saida, manifesto = despacho.saida_do_render(c, RETORNOS["colab"])
    assert saida == RETORNOS["colab"]["bundle"] and isinstance(saida, str) and manifesto is None  # the bundle is not joined to c.dir


def test_saida_do_render_sem_output_nem_bundle_e_nada(tmp_path):
    from simplicio_video import despacho
    c = _contrato(tmp_path)
    assert despacho.saida_do_render(c, {}) == (None, None)
    assert despacho.saida_do_render(c, {"output": "out/mini.mp4"}) == (None, None)  # `output` counts only as a dict
    assert despacho.saida_do_render(c, {"output": None, "bundle": "b.zip"}) == ("b.zip", None)


def test_a_cli_nao_conhece_mais_a_forma_do_retorno_de_cada_backend():
    """`render --json` asks the dispatch what was delivered; it does not read `output`/`bundle` of the result itself."""
    fonte = (SRC / "cli.py").read_text(encoding="utf-8")
    no = next(n for n in ast.parse(fonte).body if isinstance(n, ast.FunctionDef) and n.name == "_render_json")
    texto = ast.get_source_segment(fonte, no)
    assert "saida_do_render" in texto
    assert 'get("bundle")' not in texto and 'isinstance(r.get("output")' not in texto, texto
