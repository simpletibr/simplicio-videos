"""V1, "um dono para os valores copiados": a value or a rule that was copied by hand into several modules, with nothing linking the
copies, gets one owner. The behavior stays the same; only the two declared bugfixes (H1, H4) change an answer.

* H1, the data folder of the engine ($SIMPLICIO_VIDEO_DATA, else ~/.simplicio-video) was computed in seven places. Five of them expand
  `~`; `tools_lock.default_data_dir` and `commands.versions.default_state_dir` did not (with SIMPLICIO_VIDEO_DATA="~/x" they wrote into a
  folder literally named `~` in the cwd). One owner: `paths.data_root()` (`paths.jobs_root` stays, as the same function). BUGFIX declared.
* H4, the support python of the local voice and of video-use ($SIMPLICIO_TTS_PY, else a venv under ~/.local/share): `paths.tts_python()`
  is the owner and the doctor calls it. With the variable EMPTY paths answered "" (the doctor and setup.sh already took the default).
  BUGFIX declared.
* H2, the eight proxy names (HTTP(S)_PROXY, ALL_PROXY, NO_PROXY and the lowercase ones) were typed in six modules: `terceiros.PROXIES`.
  What each module passes to its child does not change (tests/test_terceiros.py ENV_DE_HOJE and tests/golden/test_env_terceiros.py freeze
  it); only the order of a tuple may change, and nobody reads it. `busca.ENV_PROXY` is a different thing (six names, no NO_PROXY: the
  ones whose value may carry a password) and stays as it is.
* H5, names that already had an owner and were copied: the MCP flag (`childio.ENV_FLAG`), the job origin variable
  (`paths.JOB_ORIGIN_ENV`, written by the jobs runner and read by video-to-skill), the contract schema id (`CONTRACT_SCHEMA_ID`) and the
  examples of the `qc` help (`qc.EXEMPLOS`, whose bytes do not change).

Two kinds of test. CHARACTERIZATION (green before and after): what each place answers today. STRUCTURE (red before): the owner exists
and the copies are gone, read from the AST of the package (a docstring or a help text that mentions a name is not a copy: only a
string constant that IS the name counts). The `~` case of the two places that did not expand it is the red of the bugfix.
"""
from __future__ import annotations

import ast
import functools
import os
import types
from pathlib import Path

import pytest

from helpers import SRC, run_main
from simplicio_video import (
    CONTRACT_SCHEMA_ID,
    busca,
    childio,
    cli,
    doctor_trilhas,
    download,
    hostos,
    instagram,
    matchcut,
    mcp_server,
    montage,
    openverse,
    paths,
    qc,
    scaffold,
    status,
    terceiros,
    tools_lock,
    trilha_base,
    video_to_skill,
)
from simplicio_video.commands import doctor, versions

# ---- the AST of the package -----------------------------------------------------------------------------------------------------


@functools.cache
def _arvores() -> dict:
    """{path relative to the package: its AST} for every .py of src/simplicio_video."""
    return {a.relative_to(SRC).as_posix(): ast.parse(a.read_text(encoding="utf-8")) for a in sorted(SRC.rglob("*.py"))}


def _ocorrencias(predicado) -> set[tuple[str, str]]:
    """{(file, qualified name of the enclosing function or class, "<modulo>" at the top)} of every node `predicado` accepts."""
    achados: set[tuple[str, str]] = set()

    def visita(rel: str, no: ast.AST, dono: str) -> None:
        for filho in ast.iter_child_nodes(no):
            if predicado(filho):
                achados.add((rel, dono))
            nome = dono
            if isinstance(filho, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                nome = filho.name if dono == "<modulo>" else f"{dono}.{filho.name}"
            visita(rel, filho, nome)

    for rel, arvore in _arvores().items():
        visita(rel, arvore, "<modulo>")
    return achados


def _usos_da_constante(valor: str) -> set[tuple[str, str]]:
    """Where a string constant that IS `valor` (not a text that contains it) is written in code."""
    return _ocorrencias(lambda n: isinstance(n, ast.Constant) and n.value == valor)


def _e_environ(no: ast.AST) -> bool:
    return (isinstance(no, ast.Attribute) and no.attr == "environ") or (isinstance(no, ast.Name) and no.id == "environ")


def _leituras_de_ambiente(nome: str) -> set[tuple[str, str]]:
    """Where the environment variable `nome` is read: os.environ.get(nome), os.getenv(nome), os.environ[nome]."""
    def le(n: ast.AST) -> bool:
        if isinstance(n, ast.Call) and n.args and isinstance(n.args[0], ast.Constant) and n.args[0].value == nome:
            f = n.func
            return isinstance(f, ast.Attribute) and ((f.attr == "get" and _e_environ(f.value)) or f.attr == "getenv")
        return (isinstance(n, ast.Subscript) and isinstance(n.ctx, ast.Load) and _e_environ(n.value)
                and isinstance(n.slice, ast.Constant) and n.slice.value == nome)
    return _ocorrencias(le)


def _funcao(rel: str, qualificado: str) -> ast.AST:
    """The def named `Classe.metodo` or `funcao` in the file `rel`."""
    no: ast.AST = _arvores()[rel]
    for parte in qualificado.split("."):
        no = next(n for n in ast.iter_child_nodes(no) if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name == parte)
    return no


def _chama(no: ast.AST, dono: str, nome: str) -> bool:
    """True when `no` contains a call `dono.nome(...)`."""
    return any(isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == nome
               and isinstance(n.func.value, ast.Name) and n.func.value.id == dono for n in ast.walk(no))


def _refere(rel: str, dono: str, nome: str) -> bool:
    """True when the file `rel` mentions `dono.nome` (or imports `nome` from `.dono`) in code."""
    for n in ast.walk(_arvores()[rel]):
        if isinstance(n, ast.Attribute) and n.attr == nome and isinstance(n.value, ast.Name) and n.value.id == dono:
            return True
        if isinstance(n, ast.ImportFrom) and n.module == dono and any(a.name == nome for a in n.names):
            return True
    return False


# ================================================================================================================ H1: data folder

# the seven places that answer "where is the data folder": (what they answer, the subfolder, whether they .resolve())
SITIOS = {
    "paths.jobs_root": (lambda: paths.jobs_root(), Path(), False),
    "montage.default_openmontage_dir": (lambda: montage.default_openmontage_dir(), Path("tools") / "openmontage", False),
    "trilha_base.Trilha.data_dir": (lambda: trilha_base.Trilha("rea_video", "REA_VIDEO_DIR").data_dir(), Path("rea-video-data"), True),
    "busca.pasta": (lambda: busca.pasta(), Path("busca"), True),
    "openverse.library_dir": (lambda: openverse.library_dir(), Path("openverse-library"), True),
    "tools_lock.default_data_dir": (lambda: tools_lock.default_data_dir(), Path(), False),
    "versions.default_state_dir": (lambda: versions.default_state_dir(), Path(), False),
}
# the function each of the six that is not the owner must call
CHAMAM_DATA_ROOT = {
    "montage.py": "default_openmontage_dir", "trilha_base.py": "Trilha.data_dir", "busca.py": "pasta", "openverse.py": "library_dir",
    "tools_lock.py": "default_data_dir", "commands/versions.py": "default_state_dir",
}


def _mundo(monkeypatch, tmp_path: Path, cenario: str) -> Path:
    """The shell of a scenario for SIMPLICIO_VIDEO_DATA; returns the folder that value MEANS (relative for "relativo", the expanded
    home for "til"). The home is tmp/casa and the cwd is tmp."""
    casa = tmp_path / "casa"
    casa.mkdir(exist_ok=True)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(casa))
    monkeypatch.setenv("USERPROFILE", str(casa))
    for var in ("SIMPLICIO_VIDEO_DATA", "OPENVERSE_LIBRARY_DIR", "OPENMONTAGE_DIR", "SIMPLICIO_OPENMONTAGE_DIR", "SIMPLICIO_TOOLS_DIR"):
        monkeypatch.delenv(var, raising=False)
    valor, base = {
        "ausente": (None, casa / ".simplicio-video"),
        "absoluto": (str(tmp_path / "dados"), tmp_path / "dados"),
        "relativo": ("dados/aqui", Path("dados") / "aqui"),
        "til": ("~/x", casa / "x"),
        "vazio": ("", casa / ".simplicio-video"),
    }[cenario]
    if valor is not None:
        monkeypatch.setenv("SIMPLICIO_VIDEO_DATA", valor)
    return base


def _esperado(base: Path, sub: Path, resolve: bool) -> Path:
    alvo = base / sub
    return alvo.resolve() if resolve else alvo


@pytest.mark.parametrize("cenario", ["ausente", "absoluto", "relativo", "vazio"])
@pytest.mark.parametrize("sitio", SITIOS)
def test_cada_sitio_da_pasta_de_dados_responde_o_de_sempre(monkeypatch, tmp_path, sitio, cenario):
    """Green: the variable absent, absolute, relative (stays relative where the place never resolved it) or empty (the default)."""
    base = _mundo(monkeypatch, tmp_path, cenario)
    funcao, sub, resolve = SITIOS[sitio]
    assert funcao() == _esperado(base, sub, resolve)


@pytest.mark.parametrize("sitio", SITIOS)
def test_com_til_os_sete_sitios_expandem_o_home(monkeypatch, tmp_path, sitio):
    """SIMPLICIO_VIDEO_DATA="~/x" means <home>/x in all seven places. RED for tools_lock.default_data_dir and
    versions.default_state_dir (the declared bugfix): they answered the relative path `~/x`, a folder named `~` in the cwd."""
    base = _mundo(monkeypatch, tmp_path, "til")
    funcao, sub, resolve = SITIOS[sitio]
    assert funcao() == _esperado(base, sub, resolve)


@pytest.mark.parametrize("sitio", SITIOS)
def test_sem_home_e_sem_variavel_os_sete_sitios_recusam_do_mesmo_jeito(monkeypatch, tmp_path, sitio):
    """Green: no home and no variable is hostos.SemCasa, whose message names SIMPLICIO_VIDEO_DATA (the way out)."""
    _mundo(monkeypatch, tmp_path, "ausente")
    monkeypatch.delenv("HOME")
    monkeypatch.delenv("USERPROFILE")

    def sem_casa(cls):
        raise RuntimeError("Could not determine home directory.")

    monkeypatch.setattr(Path, "home", classmethod(sem_casa))
    with pytest.raises(hostos.SemCasa, match="SIMPLICIO_VIDEO_DATA"):
        SITIOS[sitio][0]()


@pytest.mark.parametrize("cenario", ["ausente", "absoluto", "relativo", "vazio", "til"])
def test_o_doctor_le_a_checagem_de_update_da_pasta_de_dados(monkeypatch, tmp_path, cenario):
    """`doctor` shows the cached `update --check` that lives in the data folder. The "~/x" case is RED today: the doctor looked in the
    folder literally named `~` (the same bugfix as versions.default_state_dir)."""
    base = _mundo(monkeypatch, tmp_path, cenario)
    pasta = tmp_path / base if not base.is_absolute() else base
    versions.write_check({"latest": "9.9.9", "update_available": True, "kind": "pip"}, pasta)
    linha = doctor.collect(only="update", installed="0.8.0")["checks"][0]
    assert linha["name"] == "update" and linha["status"] == "warn", linha["summary"]
    assert linha["detail"]["latest"] == "9.9.9" and "0.8.0 -> 9.9.9" in linha["summary"]


@pytest.mark.parametrize("cenario", ["ausente", "absoluto", "relativo", "vazio", "til"])
def test_data_root_responde_o_que_jobs_root_respondia(monkeypatch, tmp_path, cenario):
    """RED until `paths.data_root` exists; `jobs_root` stays (jobs and montage and their tests call it) as the same function."""
    base = _mundo(monkeypatch, tmp_path, cenario)
    assert paths.data_root() == paths.jobs_root() == base
    assert paths.jobs_root is paths.data_root


def test_so_o_data_root_le_a_variavel_da_pasta_de_dados():
    """RED: the constant "SIMPLICIO_VIDEO_DATA" is written in code in one function only, `paths.data_root` (seven places had it,
    twice each: the `environ.get` and the name handed to hostos.home_absoluta)."""
    assert _usos_da_constante("SIMPLICIO_VIDEO_DATA") == {("paths.py", "data_root")}


@pytest.mark.parametrize("rel,funcao", sorted(CHAMAM_DATA_ROOT.items()))
def test_os_outros_seis_sitios_chamam_o_data_root(rel, funcao):
    """RED: each of the six calls `paths.data_root()` and keeps its own subfolder and its own `.resolve()`."""
    assert _chama(_funcao(rel, funcao), "paths", "data_root"), f"{rel}:{funcao} does not call paths.data_root()"


# ================================================================================================================ H4: support python


def _casa(monkeypatch, tmp_path: Path) -> Path:
    casa = tmp_path / "casa"
    casa.mkdir()
    monkeypatch.setenv("HOME", str(casa))
    monkeypatch.setenv("USERPROFILE", str(casa))
    return casa


def _python_padrao(casa: Path) -> str:
    return str(casa / ".local" / "share" / "simplicio-tts" / "cbvenv" / "bin" / "python")


def test_o_python_de_apoio_sem_variavel_e_o_do_venv_do_tts(monkeypatch, tmp_path):
    casa = _casa(monkeypatch, tmp_path)
    monkeypatch.delenv("SIMPLICIO_TTS_PY", raising=False)
    assert paths.tts_python() == _python_padrao(casa)


def test_o_python_de_apoio_da_variavel_vai_como_esta_mesmo_sem_existir(monkeypatch, tmp_path):
    _casa(monkeypatch, tmp_path)
    monkeypatch.setenv("SIMPLICIO_TTS_PY", "/nao/existe/python")
    assert paths.tts_python() == "/nao/existe/python"


def test_o_python_de_apoio_com_a_variavel_vazia_e_o_padrao(monkeypatch, tmp_path):
    """RED (the declared bugfix): an empty variable answered "" (so `voice` looked for kokoro at "" and `edit` ran ""); the doctor
    and setup.sh already took the default for an empty one."""
    casa = _casa(monkeypatch, tmp_path)
    monkeypatch.setenv("SIMPLICIO_TTS_PY", "")
    assert paths.tts_python() == _python_padrao(casa)


FIX_TTS = ("defina SIMPLICIO_TTS_PY com um python que tenha numpy, Pillow e soundfile (e faster-whisper, para transcrever "
           "localmente), e rode `simplicio-video edit setup`")


@pytest.mark.parametrize("variavel", ["ausente", "vazia", "existe", "nao-existe"])
@pytest.mark.parametrize("obrigatoria", [True, False])
def test_a_linha_do_python_de_apoio_do_doctor_trilhas_e_a_de_sempre(monkeypatch, tmp_path, variavel, obrigatoria):
    """Green: the row `dep:SIMPLICIO_TTS_PY` of `doctor trilhas --json`, whole, for the variable absent, empty, set to a file that
    exists and set to one that does not (the default venv does not exist in the throwaway home)."""
    casa = _casa(monkeypatch, tmp_path)
    monkeypatch.delenv("SIMPLICIO_TTS_PY", raising=False)
    caminho = _python_padrao(casa)
    if variavel == "vazia":
        monkeypatch.setenv("SIMPLICIO_TTS_PY", "")
    elif variavel in ("existe", "nao-existe"):
        caminho = str(tmp_path / "py" / "python")
        monkeypatch.setenv("SIMPLICIO_TTS_PY", caminho)
        if variavel == "existe":
            (tmp_path / "py").mkdir()
            Path(caminho).write_text("", encoding="utf-8")
    achada = doctor_trilhas._tts_py_row(obrigatoria)
    if variavel == "existe":
        esperada = ("ok", f"python de apoio encontrado: {caminho}", None)
    elif obrigatoria:
        esperada = ("warn", f"python de apoio ausente: {caminho}", FIX_TTS)
    else:
        esperada = ("ok", "python de apoio ausente (opcional)", None)
    assert achada == {"name": "dep:SIMPLICIO_TTS_PY", "status": esperada[0], "summary": esperada[1], "fix": esperada[2],
                      "detail": {"path": caminho}}


def test_so_o_paths_le_a_variavel_do_python_de_apoio():
    """RED: `SIMPLICIO_TTS_PY` is read in `paths.tts_python` only, and the default venv is spelled there only (the doctor had
    its own `get(...) or default`, built by parts)."""
    assert _leituras_de_ambiente("SIMPLICIO_TTS_PY") == {("paths.py", "tts_python")}
    assert {rel for rel, _ in _ocorrencias(lambda n: isinstance(n, ast.Constant) and isinstance(n.value, str) and "cbvenv" in n.value)} == {"paths.py"}


def test_o_doctor_pergunta_ao_paths_qual_e_o_python_de_apoio():
    """RED: the row of the doctor calls `paths.tts_python()`."""
    assert _chama(_funcao("doctor_trilhas.py", "_tts_py_row"), "paths", "tts_python")


# ================================================================================================================ H2: proxy names

PROXIES_OITO = frozenset({"HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY", "http_proxy", "https_proxy", "all_proxy", "no_proxy"})
# busca.ENV_PROXY: the six names whose value may carry a password (no NO_PROXY). A different list, it is not unified.
PROXIES_SEIS = PROXIES_OITO - {"NO_PROXY", "no_proxy"}
CONSUMIDORES_DE_PROXIES = ("busca.py", "download.py", "matchcut.py", "montage.py", "status.py", "video_to_skill.py")


class _Fim:
    returncode, stdout, stderr = 0, "x", ""


def _env_do_status(monkeypatch) -> dict:
    visto: dict = {}

    def espia(cmd, **kw):
        visto["env"] = kw.get("env")
        return _Fim()

    monkeypatch.setattr(status.subprocess, "run", espia)
    status._primeira_linha(["x"])
    return visto["env"]


def _ambientes(monkeypatch) -> dict:
    """The environment each module hands to its child when the shell has the eight proxy names and a few decoys."""
    monkeypatch.setattr(os, "environ", {n: "v:" + n for n in (*sorted(PROXIES_OITO), "PATH", "HOME", "LANG", "LC_ALL", "TMPDIR",
                                                               "SSL_CERT_FILE", "GEMINI_API_KEY", "GITHUB_TOKEN")})
    return {
        "download": download._ambiente(),
        "busca": busca._ambiente_filho(),
        "status": _env_do_status(monkeypatch),
        "doctor_trilhas": doctor_trilhas._ambiente(),
        "matchcut-pip": matchcut._env_pip(),
        "montage": montage._child_env(),
        "video-to-skill-url": video_to_skill._env(True),
        "matchcut": matchcut._ambiente(Path("/priv")),
        "video-to-skill": video_to_skill._env(),
        "instagram": instagram._ambiente(),
    }


@pytest.mark.parametrize("modulo", ["download", "busca", "status", "doctor_trilhas", "matchcut-pip", "montage", "video-to-skill-url"])
def test_o_filho_que_usa_a_rede_recebe_os_oito_nomes_de_proxy_com_o_valor_de_sempre(monkeypatch, modulo):
    env = _ambientes(monkeypatch)[modulo]
    assert {n for n in env if n in PROXIES_OITO} == PROXIES_OITO
    assert all(env[n] == "v:" + n for n in PROXIES_OITO)
    assert "GEMINI_API_KEY" not in env and "GITHUB_TOKEN" not in env


@pytest.mark.parametrize("modulo", ["matchcut", "video-to-skill", "instagram"])
def test_o_filho_que_nao_usa_a_rede_nao_recebe_nenhum_proxy(monkeypatch, modulo):
    assert not set(_ambientes(monkeypatch)[modulo]) & PROXIES_OITO


def test_terceiros_tem_os_oito_nomes_de_proxy():
    """RED until `terceiros.PROXIES` exists: a tuple (the consumers build theirs with `(*terceiros.PROXIES, ...)`) of the eight names,
    each once. The order is not part of it: nobody reads it."""
    p = terceiros.PROXIES
    assert isinstance(p, tuple) and len(p) == 8 and frozenset(p) == PROXIES_OITO


def test_nenhum_modulo_repete_os_nomes_de_proxy_alem_do_terceiros():
    """RED: no tuple, list or set outside terceiros.py carries the proxy names, except `busca.ENV_PROXY` (six names, no NO_PROXY)."""
    def copia(n: ast.AST) -> bool:
        if not isinstance(n, (ast.Tuple, ast.List, ast.Set)):
            return False
        nomes = {e.value for e in n.elts if isinstance(e, ast.Constant) and e.value in PROXIES_OITO}
        return len(nomes) >= 3 and not (nomes == PROXIES_SEIS and len(n.elts) == 6)
    assert {rel for rel, _ in _ocorrencias(copia)} - {"terceiros.py"} == set()
    seis = _ocorrencias(lambda n: isinstance(n, ast.Tuple) and len(n.elts) == 6
                        and {e.value for e in n.elts if isinstance(e, ast.Constant)} == PROXIES_SEIS)
    assert seis == {("busca.py", "<modulo>")}, "busca.ENV_PROXY (the six names) stays, and only there"


@pytest.mark.parametrize("rel", CONSUMIDORES_DE_PROXIES)
def test_os_seis_consumidores_montam_a_lista_com_o_terceiros_proxies(rel):
    """RED: each one writes `(*terceiros.PROXIES, ...)` instead of the names."""
    assert _refere(rel, "terceiros", "PROXIES"), f"{rel} does not use terceiros.PROXIES"


@pytest.mark.parametrize("rel,funcao", [("matchcut.py", "_env_pip"), ("montage.py", "_child_env"), ("video_to_skill.py", "_env")])
def test_o_ambiente_do_filho_passa_pelo_env_para_terceiro(rel, funcao):
    """RED: matchcut._env_pip, montage._child_env and video_to_skill._env built the environment with a comprehension of their own."""
    assert _chama(_funcao(rel, funcao), "terceiros", "env_para_terceiro")


def test_o_download_repassa_o_nucleo_e_o_que_tem_a_mais():
    """Green: what the downloader receives is the core of `terceiros` and what it has on top, in this order."""
    assert download.ENV_REPASSADO == (*terceiros.NUCLEO_ENV, *download.ENV_EXTRA)


def test_o_download_nao_digita_de_novo_o_nucleo():
    """RED: `download.ENV_REPASSADO` names the core as `terceiros.NUCLEO_ENV` (busca and status already do) instead of typing the
    four names again."""
    assert _refere("download.py", "terceiros", "NUCLEO_ENV")


# ================================================================================================================ H5: names with an owner


def test_o_servidor_mcp_levanta_a_bandeira_que_o_childio_le(monkeypatch):
    """Green: `mcp_server.main` sets the flag `childio` reads (under MCP the children get no stdin and no inherited stdout)."""
    monkeypatch.setenv("SIMPLICIO_MCP", "0")  # restored at teardown: the flag does not leak into other tests
    monkeypatch.setattr(childio, "install_exit_guard", lambda: None)
    rodou: list = []
    monkeypatch.setattr(mcp_server, "build_server", lambda: types.SimpleNamespace(run=rodou.append))
    mcp_server.main()
    assert childio.ENV_FLAG == "SIMPLICIO_MCP" and os.environ["SIMPLICIO_MCP"] == "1" and childio.under_mcp() and rodou == ["stdio"]


def test_so_o_childio_escreve_o_nome_da_bandeira_do_mcp():
    """RED: "SIMPLICIO_MCP" is written in `childio` only (mcp_server had its own copy: `os.environ["SIMPLICIO_MCP"] = "1"`)."""
    assert _usos_da_constante("SIMPLICIO_MCP") == {("childio.py", "<modulo>")}
    assert _refere("mcp_server.py", "childio", "ENV_FLAG")


def test_a_variavel_da_origem_da_tarefa_tem_dono_em_paths():
    """RED until `paths.JOB_ORIGIN_ENV` exists. The NAME is the protocol between the runner and the CLI it starts (and is what
    docs/reference documents): frozen. The jobs runner writes it and video-to-skill reads it, through the constant."""
    assert paths.JOB_ORIGIN_ENV == "SIMPLICIO_JOB_ORIGIN"
    assert _usos_da_constante("SIMPLICIO_JOB_ORIGIN") == {("paths.py", "<modulo>")}
    assert _refere("jobs.py", "paths", "JOB_ORIGIN_ENV") and _refere("video_to_skill.py", "paths", "JOB_ORIGIN_ENV")


def test_o_esqueleto_do_contrato_traz_o_schema_de_sempre():
    """Green: `init` writes the schema id the validator checks."""
    esqueleto = scaffold.skeleton(Path("."), "x", "Camp", "sazonal-dia-das-criancas", 2026, "Nome", None)
    assert esqueleto["schema"] == CONTRACT_SCHEMA_ID == "simplicio.video-contract/v1"


def test_so_o___init___escreve_o_id_do_schema_do_contrato():
    """RED: the schema id is written in `__init__.py` only (scaffold.skeleton had a copy)."""
    assert _usos_da_constante("simplicio.video-contract/v1") == {("__init__.py", "<modulo>")}


EXEMPLOS_QC = "exemplos:\n  simplicio-video qc congelado out/video.mp4\n  simplicio-video qc congelado out/video.mp4 --min-s 0.3 --json"


def test_o_help_do_qc_traz_os_exemplos_de_sempre(capsys):
    """Green: the page of `qc` (cli's parser, raw epilogue) carries the examples, byte for byte; the page of `qc congelado` (qc's own
    parser, which reflows the epilogue to the width of the terminal) carries the same words."""
    rc, out, _ = run_main(cli.main, ["qc", "--help"], capsys)
    assert rc == 0 and out.endswith(EXEMPLOS_QC + "\n")
    rc, out, _ = run_main(qc.run_qc, ["congelado", "--help"], capsys)
    assert rc == 0 and " ".join(EXEMPLOS_QC.split()) in " ".join(out.split())


def test_os_exemplos_do_qc_tem_um_dono():
    """RED until `qc.EXEMPLOS` exists: the examples are written once, in qc.py, and the CLI's `qc` page uses them (it was typed in
    cli.py and in qc.py)."""
    assert qc.EXEMPLOS == EXEMPLOS_QC
    assert _usos_da_constante(EXEMPLOS_QC) == {("qc.py", "<modulo>")}
    assert _refere("cli.py", "qc", "EXEMPLOS")
