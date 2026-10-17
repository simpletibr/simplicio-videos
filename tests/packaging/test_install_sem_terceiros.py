"""`simplicio-video install` must work with the standard library only, and `./install.sh` must not need a python3 at all.

A checkout can be driven with the SYSTEM python before any `.venv` exists (`PYTHONPATH=src python3 -m simplicio_video install`):
that interpreter has no PyYAML, no jsonschema, nothing that is not in the standard library (macOS with the Xcode tools, a minimal
Debian or Ubuntu). So `install` and everything it imports at the top (`installer`, `skill_sync`, `distribution`, `hostos`,
`paths`, `auth`, `update`, `login`, the CLI) must use the standard library only. The review of PR #116 found `commands/install.py`
importing `setup`, which imports `yaml` at the top: `install --check` died with ModuleNotFoundError on such a machine (the tests
did not see it because they run inside the `.venv`, which has PyYAML). That is bug B1; these tests keep it fixed.

These tests run the CLI in a SUBPROCESS whose import system refuses every module that is not standard library or
`simplicio_video` (a meta path finder installed first, with the third-party modules already loaded thrown away), and check
that `yaml` and `jsonschema` really are refused there before they trust the result. HOME, PATH and the target are sealed.
And `./install.sh` (now a thin wrapper of `scripts/dev_install.sh`, which uses `uv` and no python at all) is run with a `python3`
on PATH that dies with `No module named 'yaml'`: it must not even notice.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import textwrap

import pytest

import _caixa
from _caixa import FFMPEG_COM_LIBASS, posix_real, write_fake_tool, write_fake_uv
from _comum import ROOT, erros_de_schema

# fixtures: assigned (not imported) so pytest finds them and ruff sees no shadowing by the test parameters
caixa = _caixa.caixa

# Runs inside the child: block the third party first and prove the block works...
BLOQUEIO = textwrap.dedent(r'''
    import importlib.abc, os, sys

    # the names of the standard library, plus the folders it lives in: `_sysconfigdata__x86_64-linux-gnu`, for one, is standard
    # library and is in no list of names
    STDLIB = set(sys.stdlib_module_names) | set(sys.builtin_module_names) | {"__future__", "__main__"}
    RAIZES = (os.path.dirname(os.path.realpath(os.__file__)) + os.sep,)  # the folder of the standard library, not of the venv

    def permitido(nome):
        topo = nome.partition(".")[0]
        return topo in STDLIB or topo == "simplicio_video"

    class Bloqueia(importlib.abc.MetaPathFinder):
        def find_spec(self, nome, caminho=None, alvo=None):
            if permitido(nome):
                return None
            for outro in sys.meta_path:
                achar = getattr(outro, "find_spec", None)
                spec = achar(nome, caminho, alvo) if achar and outro is not self else None
                if spec is not None:
                    origem = os.path.realpath(spec.origin) if spec.origin and spec.has_location else ""
                    if origem.startswith(RAIZES) and "-packages" not in origem:
                        return None  # a file of the standard library: let the normal import find it
                    break
            raise ModuleNotFoundError(f"No module named {nome.partition('.')[0]!r} (blocked: not standard library)", name=nome)

    for nome in [m for m in sys.modules if not permitido(m)]:
        del sys.modules[nome]
    sys.meta_path.insert(0, Bloqueia())
''')
# ... then run the CLI like `python -m simplicio_video` (or just import the modules).
CORPO = textwrap.dedent(r'''
    sys.path.insert(0, sys.argv[1])
    modo, argumentos = sys.argv[2], sys.argv[3:]
    if modo == "importa":
        import importlib
        for nome in argumentos:
            importlib.import_module(nome)
        print("IMPORTOU " + " ".join(argumentos))
        sys.exit(0)
    from simplicio_video import distribution
    distribution.kind = lambda **kw: distribution.SOURCE  # the machine that runs the suite may have the package installed
    from simplicio_video.cli import main
    sys.exit(main(argumentos))
''')
BOOT = BLOQUEIO + CORPO


def _no_interpretador_sem_terceiros(modo: str, *argumentos: str, env: dict, codigo: str = BOOT):
    return subprocess.run([sys.executable, "-I", "-B", "-c", codigo, str(ROOT / "src"), modo, *argumentos],
                          capture_output=True, text=True, encoding="utf-8", errors="replace", env=env, timeout=120)


@pytest.fixture
def selado(caixa):
    """An empty target folder and the environment of the child process."""
    alvo = caixa.tmp / "proj"
    alvo.mkdir()
    env = {"HOME": str(caixa.home), "USERPROFILE": str(caixa.home), "PATH": str(caixa.bin), "SIMPLICIO_VIDEO_DATA": str(caixa.data),
           "SIMPLICIO_WORKSPACE": str(caixa.workspace), "SIMPLICIO_OFFLINE": "1"}
    caixa.alvo, caixa.env = alvo, env
    return caixa


def _roda(selado, *argv: str):
    return _no_interpretador_sem_terceiros("cli", *argv, env=selado.env)


@pytest.mark.parametrize("terceiro", ["yaml", "jsonschema", "requests"])
def test_o_bloqueio_do_teste_funciona(selado, terceiro):
    """Without this, every other test here could pass for the wrong reason: the third party must really be refused."""
    feito = _no_interpretador_sem_terceiros("cli", env=selado.env, codigo=BLOQUEIO + f"\nimport {terceiro}\n")
    assert feito.returncode != 0 and "ModuleNotFoundError" in feito.stderr and "blocked: not standard library" in feito.stderr
    ok = _no_interpretador_sem_terceiros("importa", "json", "tomllib", env=selado.env)
    assert ok.returncode == 0 and "IMPORTOU" in ok.stdout, ok.stderr


@pytest.mark.parametrize("modulo", ["simplicio_video", "simplicio_video.paths", "simplicio_video.hostos",
                                    "simplicio_video.distribution", "simplicio_video.installer", "simplicio_video.skill_sync",
                                    "simplicio_video.auth", "simplicio_video.commands.install", "simplicio_video.commands.update",
                                    "simplicio_video.commands.login", "simplicio_video.cli"])
def test_o_que_o_install_puxa_no_topo_so_usa_a_biblioteca_padrao(selado, modulo):
    feito = _no_interpretador_sem_terceiros("importa", modulo, env=selado.env)
    assert feito.returncode == 0, f"{modulo} needs a third-party module at import time:\n{feito.stderr[-600:]}"
    assert "IMPORTOU" in feito.stdout


def test_install_check_sem_yaml_mostra_o_plano_e_sai_10(selado):
    feito = _roda(selado, "install", "--check", "--target", str(selado.alvo))
    texto = feito.stdout + feito.stderr
    assert "ModuleNotFoundError" not in texto and "Traceback" not in texto, texto[-600:]
    assert feito.returncode == 10 and "check: há mudanças pendentes" in texto and "SKILL.md" in texto
    assert list(selado.alvo.iterdir()) == [] and list(selado.home.iterdir()) == []


def test_install_dry_run_sem_yaml_sai_0_e_nao_cria_nada(selado):
    feito = _roda(selado, "install", "--dry-run", "--target", str(selado.alvo))
    texto = feito.stdout + feito.stderr
    assert "ModuleNotFoundError" not in texto and "Traceback" not in texto, texto[-600:]
    assert feito.returncode == 0 and "dry-run" in texto and list(selado.alvo.iterdir()) == []


@pytest.mark.parametrize("opcao,rc", [("--check", 10), ("--dry-run", 0)])
def test_install_json_sem_yaml_imprime_o_documento(selado, opcao, rc):
    feito = _roda(selado, "install", opcao, "--json", "--target", str(selado.alvo))
    assert "ModuleNotFoundError" not in feito.stderr and "Traceback" not in feito.stderr, feito.stderr[-600:]
    assert feito.returncode == rc, feito.stdout + feito.stderr
    doc = json.loads(feito.stdout)
    assert doc["schema"] == "simplicio.video-install-plan/v1" and erros_de_schema("install-plan", doc) == []
    assert doc["up_to_date"] is False and doc["status"] == "dry_run"


def test_install_de_verdade_sem_yaml_instala_confere_e_desinstala_com_o_pacote_real(selado):
    """The whole cycle with the REAL package data, on the interpreter that has nothing but the standard library."""
    feito = _roda(selado, "install", "--target", str(selado.alvo))
    texto = feito.stdout + feito.stderr
    assert "Traceback" not in texto and feito.returncode == 0, texto[-800:]
    assert (selado.alvo / ".claude" / "skills" / "simplicio-video" / "SKILL.md").is_file()
    assert "simplicio-video setup" in texto, "no terminal and no workspace: the hint, not the wizard (it needs PyYAML)"
    assert _roda(selado, "install", "--check", "--target", str(selado.alvo)).returncode == 0
    desfeito = _roda(selado, "install", "--uninstall", "--target", str(selado.alvo))
    assert desfeito.returncode == 0 and list(selado.alvo.iterdir()) == [], desfeito.stdout + desfeito.stderr


def test_install_global_sem_yaml_resincroniza_e_confere(selado):
    velha = selado.home / ".codex" / "skills" / "simplicio-video"
    velha.mkdir(parents=True)
    (velha / "SKILL.md").write_text("release antiga\n", encoding="utf-8")
    feito = _roda(selado, "install", "--global", "--check")
    assert feito.returncode == 10 and "Traceback" not in feito.stderr, feito.stdout + feito.stderr
    assert _roda(selado, "install", "--global").returncode == 0
    assert _roda(selado, "install", "--global", "--check").returncode == 0


# --- ./install.sh does not call any python ------------------------------------------------------------------------------------


@posix_real
def test_install_sh_nao_chama_nenhum_python3_nem_o_sem_pyyaml(selado):
    """The old install.sh ran `python3 -m simplicio_video install`. Now it is a wrapper of scripts/dev_install.sh, which has uv
    create the venv: a `python3` that dies with `No module named 'yaml'` must not be called at all."""
    for nome in ("python3", "python"):
        falso = selado.bin / nome
        falso.write_text("#!/bin/sh\necho \"ModuleNotFoundError: No module named 'yaml'\" >&2\nexit 97\n", encoding="utf-8")
        falso.chmod(0o755)
    write_fake_tool(selado.bin, "node", "v22.11.0\n")
    write_fake_tool(selado.bin, "ffmpeg", FFMPEG_COM_LIBASS)
    write_fake_uv(selado.bin)
    repo = selado.tmp / "checkout"
    (repo / "scripts").mkdir(parents=True)
    for nome in ("install.sh", "scripts/dev_install.sh", "pyproject.toml", "plugin.json"):
        shutil.copy2(ROOT / nome, repo / nome)
    env = {"HOME": str(selado.home), "PATH": f"{selado.bin}:/usr/bin:/bin"}
    feito = subprocess.run(["bash", "install.sh", "--dry-run"], cwd=repo, env=env, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=60)
    assert feito.returncode == 0 and "yaml" not in feito.stdout + feito.stderr, feito.stdout + feito.stderr
    assert list(repo.iterdir()) and not (repo / ".venv").exists()
