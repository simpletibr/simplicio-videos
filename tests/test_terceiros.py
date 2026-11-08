"""U07.0, the `terceiros` module: the environment a third-party program gets (`NUCLEO_ENV`, `env_para_terceiro`) and the helpers of
the sandbox tracks that today exist as identical copies (`chave`, `dentro`, `real`, `commit_do_checkout`).

SECURITY. A child of a third-party track must not receive a key, a token or any SIMPLICIO_* of the shell: each module passes a closed
list of names. Eight lists exist today and they differ. `NUCLEO_ENV` is what ALL of them share; `env_para_terceiro(extra)` is "the core
plus what this module has on top". The modules only start to use it in wave 3, and the environment each one passes must stay EXACTLY
what it is today: that is what `ENV_DE_HOJE` freezes (a literal, copied from the code at b0f92ad) and what the parity tests check.
Any change of a list is a visible change of this file.

The helpers are copies: the tests run the same table over the current copies (green) and over `terceiros` (red until it exists).
"""
from __future__ import annotations

import ast
import importlib
import inspect
import os
import sys
import tempfile
import textwrap
import unicodedata
from pathlib import Path
from types import SimpleNamespace

import pytest

PROXIES = ("ALL_PROXY", "HTTPS_PROXY", "HTTP_PROXY", "NO_PROXY", "all_proxy", "http_proxy", "https_proxy", "no_proxy")

# The final set of names each consumer passes to a third-party program TODAY (frozen as literals).
ENV_DE_HOJE = {
    "download": frozenset(PROXIES + ("HOME", "LANG", "LC_ALL", "PATH", "REQUESTS_CA_BUNDLE", "SSL_CERT_DIR", "SSL_CERT_FILE", "TMPDIR")),
    "busca": frozenset(PROXIES + ("HOME", "LANG", "LC_ALL", "NODE_EXTRA_CA_CERTS", "NODE_USE_ENV_PROXY", "PATH", "SSL_CERT_DIR",
                                  "SSL_CERT_FILE", "TINYFISH_API_KEY", "TMPDIR")),
    "status": frozenset(PROXIES + ("HOME", "LANG", "LC_ALL", "LC_CTYPE", "NODE_EXTRA_CA_CERTS", "NODE_USE_ENV_PROXY", "PATH",
                                   "SSL_CERT_DIR", "SSL_CERT_FILE", "TMPDIR")),  # doctor_trilhas passes the same list
    "matchcut": frozenset(("HOME", "LANG", "LC_ALL", "PATH", "SYSTEMROOT", "TEMP", "TMP")),
    "matchcut-pip": frozenset(PROXIES + ("CURL_CA_BUNDLE", "HOME", "LANG", "LC_ALL", "PATH", "PIP_CERT", "PIP_EXTRA_INDEX_URL",
                                         "PIP_INDEX_URL", "PIP_PROXY", "PIP_TRUSTED_HOST", "REQUESTS_CA_BUNDLE", "SSL_CERT_DIR",
                                         "SSL_CERT_FILE", "SYSTEMROOT", "TEMP", "TMP")),
    "montage": frozenset(PROXIES + ("CURL_CA_BUNDLE", "HOME", "LANG", "LC_ALL", "LC_CTYPE", "NODE_EXTRA_CA_CERTS", "PATH", "PATHEXT",
                                    "PIP_CERT", "REQUESTS_CA_BUNDLE", "SSL_CERT_DIR", "SSL_CERT_FILE", "SYSTEMROOT", "TEMP", "TMP",
                                    "TMPDIR", "USER")),
    "video-to-skill": frozenset(("APPDATA", "HOME", "LANG", "LC_ALL", "LOCALAPPDATA", "PATH", "SYSTEMROOT", "TEMP", "TMP", "TMPDIR",
                                 "USERPROFILE", "VTS_DATA_DIR", "XDG_DATA_HOME")),
    "video-to-skill-url": frozenset(PROXIES + ("APPDATA", "CURL_CA_BUNDLE", "HOME", "LANG", "LC_ALL", "LOCALAPPDATA", "PATH",
                                               "REQUESTS_CA_BUNDLE", "SSL_CERT_DIR", "SSL_CERT_FILE", "SYSTEMROOT", "TEMP", "TMP",
                                               "TMPDIR", "USERPROFILE", "VTS_DATA_DIR", "XDG_DATA_HOME")),
    "instagram": frozenset(("HOME", "LANG", "LC_ALL", "PATH", "SYSTEMROOT", "TEMP", "TMP")),
}

# a shell full of what must never reach a third party
SEGREDOS = {"GEMINI_API_KEY": "g", "GITHUB_TOKEN": "t", "ELEVENLABS_API_KEY": "e", "XAI_API_KEY": "x", "OPENVERSE_CLIENT_SECRET": "s",
            "SIMPLICIO_VIDEO_DATA": "/d", "SIMPLICIO_OFFLINE": "1", "AWS_SECRET_ACCESS_KEY": "a", "PYTHONPATH": "/p", "LD_PRELOAD": "/l"}


def _terceiros():
    return importlib.import_module("simplicio_video.terceiros")  # red until U07.0 adds the module


def _legado(nome: str):
    """The tuple each module has today, or None when the module no longer has it (it then uses env_para_terceiro)."""
    if nome == "download":
        return getattr(importlib.import_module("simplicio_video.download"), "ENV_REPASSADO", None)
    if nome == "busca":
        return getattr(importlib.import_module("simplicio_video.busca"), "ENV_REPASSADO", None)
    if nome == "status":
        return getattr(importlib.import_module("simplicio_video.status"), "ENV_FERRAMENTA", None)
    if nome == "matchcut":
        return getattr(importlib.import_module("simplicio_video.matchcut"), "ENV_NAMES", None)
    if nome == "matchcut-pip":
        return getattr(importlib.import_module("simplicio_video.matchcut"), "ENV_PIP", None)
    if nome == "montage":
        return getattr(importlib.import_module("simplicio_video.montage"), "_ENV_KEEP", None)
    if nome == "video-to-skill":
        return getattr(importlib.import_module("simplicio_video.video_to_skill"), "ENV_NAMES", None)
    if nome == "video-to-skill-url":
        v2s = importlib.import_module("simplicio_video.video_to_skill")
        base, rede = getattr(v2s, "ENV_NAMES", None), getattr(v2s, "ENV_NET", None)
        return None if base is None or rede is None else (*base, *rede)
    if nome == "instagram":
        return getattr(importlib.import_module("simplicio_video.instagram"), "ENV_NAMES", None)
    raise AssertionError(nome)


# ---- today: the frozen sets are what the code has (green) ------------------------------------------------------------------


@pytest.mark.parametrize("consumidor", sorted(ENV_DE_HOJE))
def test_o_conjunto_congelado_e_o_que_o_codigo_passa_hoje(consumidor):
    """If this fails, a list changed: that is a change of what a third-party program receives, and it needs its own decision."""
    legado = _legado(consumidor)
    if legado is None:
        pytest.skip(f"{consumidor}: o módulo já usa terceiros.env_para_terceiro (o conjunto fica garantido pelos testes de paridade)")
    assert len(legado) == len(set(legado)), "nome repetido na lista"
    assert frozenset(legado) == ENV_DE_HOJE[consumidor]


@pytest.mark.parametrize("consumidor", sorted(ENV_DE_HOJE))
def test_nenhuma_lista_de_hoje_deixa_passar_segredo_do_shell(consumidor):
    passa = ENV_DE_HOJE[consumidor]
    assert not (passa & set(SEGREDOS)), passa & set(SEGREDOS)
    assert not [n for n in passa if n.startswith("SIMPLICIO_")]


# ---- NUCLEO_ENV --------------------------------------------------------------------------------------------------------------


def test_a_intersecao_das_listas_de_hoje_sao_quatro_nomes():
    """Green today: what every module passes, and nothing else, is PATH, HOME, LANG and LC_ALL."""
    assert frozenset.intersection(*ENV_DE_HOJE.values()) == frozenset({"PATH", "HOME", "LANG", "LC_ALL"})


def test_o_nucleo_e_a_intersecao_das_listas_de_hoje():
    assert set(_terceiros().NUCLEO_ENV) == frozenset.intersection(*ENV_DE_HOJE.values())


def test_o_nucleo_e_uma_tupla_de_nomes_sem_repeticao_e_sem_segredo():
    nucleo = _terceiros().NUCLEO_ENV
    assert isinstance(nucleo, tuple) and all(isinstance(n, str) and n for n in nucleo)
    assert len(nucleo) == len(set(nucleo))
    for n in nucleo:
        assert not any(marca in n.upper() for marca in ("KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL")), n
        assert not n.startswith("SIMPLICIO_"), n
    assert set(nucleo) <= set.intersection(*(set(v) for v in ENV_DE_HOJE.values()))  # never wider than what every module has today


# ---- env_para_terceiro --------------------------------------------------------------------------------------------------------


def _tudo() -> dict:
    nomes = set().union(*ENV_DE_HOJE.values())
    return {**{n: f"valor-de-{n}" for n in nomes}, **SEGREDOS}


def test_sem_extra_so_passa_o_nucleo_e_so_o_que_existe():
    t = _terceiros()
    env = t.env_para_terceiro(base={**_tudo()})
    assert set(env) == set(t.NUCLEO_ENV) and all(env[n] == f"valor-de-{n}" for n in env)
    assert t.env_para_terceiro(base={"PATH": "/bin", "SEGREDO": "x"}) == {"PATH": "/bin"}
    assert t.env_para_terceiro(base={}) == {}


def test_a_chave_do_shell_nunca_passa_sem_ser_pedida():
    t = _terceiros()
    env = t.env_para_terceiro(extra=("LC_CTYPE", "TMPDIR"), base=_tudo())
    assert not set(env) & set(SEGREDOS)
    assert set(env) == set(t.NUCLEO_ENV) | {"LC_CTYPE", "TMPDIR"}


def test_o_extra_so_acrescenta_o_que_o_modulo_pede():
    t = _terceiros()
    env = t.env_para_terceiro(("TINYFISH_API_KEY",), base={**_tudo()})
    assert env["TINYFISH_API_KEY"] == "valor-de-TINYFISH_API_KEY" and "GEMINI_API_KEY" not in env


def test_extra_aceita_qualquer_iteravel_e_um_nome_so_em_texto():
    t = _terceiros()
    base = {"PATH": "/bin", "HOME": "/h", "TMPDIR": "/t", "TEMP": "/e"}
    esperado = {"PATH": "/bin", "HOME": "/h", "TMPDIR": "/t"}
    assert t.env_para_terceiro(["TMPDIR"], base=base) == esperado
    assert t.env_para_terceiro(("TMPDIR",), base=base) == esperado
    assert t.env_para_terceiro((n for n in ("TMPDIR",)), base=base) == esperado
    assert t.env_para_terceiro({"TMPDIR"}, base=base) == esperado
    assert t.env_para_terceiro("TMPDIR", base=base) == esperado  # a lone string is a name, never its letters
    assert t.env_para_terceiro(("TMPDIR", "TMPDIR", "PATH"), base=base) == esperado  # repeated names do no harm


def test_o_valor_vai_como_esta_inclusive_vazio():
    t = _terceiros()
    assert t.env_para_terceiro(base={"PATH": "", "HOME": " /h "}) == {"PATH": "", "HOME": " /h "}


def test_devolve_um_dict_novo_e_nao_mexe_na_base():
    t = _terceiros()
    base = {"PATH": "/bin"}
    env = t.env_para_terceiro(base=base)
    env["PATH"] = "outra"
    env["NOVA"] = "1"
    assert base == {"PATH": "/bin"}


def test_a_base_padrao_e_o_ambiente_do_processo_na_hora_da_chamada(monkeypatch):
    t = _terceiros()
    monkeypatch.setenv("PATH", "/primeiro")
    monkeypatch.setenv("GEMINI_API_KEY", "segredo")
    assert t.env_para_terceiro()["PATH"] == "/primeiro" and "GEMINI_API_KEY" not in t.env_para_terceiro()
    monkeypatch.setenv("PATH", "/segundo")
    assert t.env_para_terceiro()["PATH"] == "/segundo"
    monkeypatch.delenv("HOME", raising=False)
    assert "HOME" not in t.env_para_terceiro()


@pytest.mark.parametrize("consumidor", sorted(ENV_DE_HOJE))
def test_cada_modulo_passando_o_que_tem_a_mais_recebe_exatamente_o_de_hoje(consumidor):
    """The contract of wave 3: `env_para_terceiro(extra=<what the module has on top of the core>)` is today's environment, name for
    name and value for value, for a shell that has everything, for one that has nothing, and for partial ones."""
    t = _terceiros()
    hoje = ENV_DE_HOJE[consumidor]
    extra = sorted(hoje - set(t.NUCLEO_ENV))
    assert set(t.NUCLEO_ENV) <= hoje

    def como_antes(base: dict) -> dict:  # the comprehension every module writes today
        return {k: base[k] for k in hoje if k in base}

    bases = [_tudo(), {}, {"PATH": "/bin", "HOME": "/h"}, {n: "" for n in hoje}, {"PATH": "/bin", **SEGREDOS},
             {n: f"v{i}" for i, n in enumerate(sorted(hoje)) if i % 2 == 0}]
    for base in bases:
        assert t.env_para_terceiro(extra, base=base) == como_antes(base)
        assert set(t.env_para_terceiro(extra, base=base)) <= hoje


@pytest.mark.parametrize("consumidor", sorted(ENV_DE_HOJE))
def test_cada_modulo_continua_igual_ao_codigo_de_hoje_quando_ainda_tem_a_lista(consumidor):
    """Same check against the live list of the module while it still has one (green today; skipped once it migrates)."""
    legado = _legado(consumidor)
    if legado is None:
        pytest.skip(f"{consumidor}: migrou")
    t = _terceiros()
    base = _tudo()
    assert t.env_para_terceiro(sorted(set(legado) - set(t.NUCLEO_ENV)), base=base) == {k: base[k] for k in legado if k in base}


def test_o_terceiros_e_folha_so_biblioteca_padrao_no_import():
    """`terceiros` is imported by every track: at import it only needs the standard library (commit_do_checkout imports `tools`
    when it runs, so that the leaf never drags the registry of tools in with it)."""
    fonte = Path(_terceiros().__file__).read_text(encoding="utf-8")
    raizes = set()
    for no in ast.parse(fonte).body:
        if isinstance(no, ast.Import):
            raizes.update(a.name.split(".")[0] for a in no.names)
        elif isinstance(no, ast.ImportFrom):
            assert no.level == 0, ast.dump(no)
            raizes.add((no.module or "").split(".")[0])
    assert raizes <= set(sys.stdlib_module_names) | {"__future__"}, raizes


# ---- the helpers: chave, dentro, real, commit_do_checkout --------------------------------------------------------------------

POSIX = pytest.mark.skipif(sys.platform == "win32", reason="the golden values are POSIX paths")
COPIAS = {  # helper -> [(module, private name)]: the identical copies of b0f92ad
    "chave": [("instagram", "_chave"), ("matchcut", "_chave"), ("video_to_skill", "_chave")],
    "dentro": [("instagram", "_dentro"), ("matchcut", "_dentro"), ("video_to_skill", "_dentro")],
    "real": [("matchcut", "_real"), ("video_to_skill", "_real")],
    "commit_do_checkout": [("instagram", "_commit_do_checkout"), ("matchcut", "_commit_do_checkout")],
}


def _implementacoes(helper: str):
    """Every implementation of a helper that exists: the copies (green) and `terceiros` (red)."""
    return [pytest.param(m, n, id=f"{m}.{n}") for m, n in COPIAS[helper]] + [pytest.param("terceiros", helper, id=f"terceiros.{helper}")]


def _funcao(modulo: str, nome: str):
    return getattr(importlib.import_module(f"simplicio_video.{modulo}"), nome)


def _caixa(monkeypatch, modulo: str, valor: bool):
    monkeypatch.setattr(importlib.import_module(f"simplicio_video.{modulo}"), "CASE_INSENSITIVE", valor)


@POSIX
@pytest.mark.parametrize("modulo,nome", _implementacoes("chave"))
def test_chave_sem_caixa_e_so_as_partes(monkeypatch, modulo, nome):
    _caixa(monkeypatch, modulo, False)
    assert _funcao(modulo, nome)(Path("/Etc/Café/x")) == ("/", "Etc", "Café", "x")


@POSIX
@pytest.mark.parametrize("modulo,nome", _implementacoes("chave"))
def test_chave_em_disco_que_ignora_caixa_normaliza_e_baixa(monkeypatch, modulo, nome):
    _caixa(monkeypatch, modulo, True)
    composto = _funcao(modulo, nome)(Path("/ETC/Café/X"))
    decomposto = _funcao(modulo, nome)(Path("/etc/café/x"))
    assert composto == decomposto == ("/", "etc", "café", "x")
    assert unicodedata.is_normalized("NFC", composto[2])


@pytest.mark.parametrize("modulo,nome", _implementacoes("dentro"))
def test_dentro_compara_parte_por_parte_e_resolve_so_a_pasta(monkeypatch, tmp_path, modulo, nome):
    _caixa(monkeypatch, modulo, False)
    dentro = _funcao(modulo, nome)
    pasta = tmp_path / "pasta"
    pasta.mkdir()
    assert dentro(pasta / "a" / "b", pasta) is True
    assert dentro(pasta, pasta) is True  # the folder itself
    assert dentro(tmp_path / "pasta2", pasta) is False  # not a string prefix
    assert dentro(tmp_path, pasta) is False  # the parent
    assert dentro(tmp_path / "outra" / "pasta" / "a", pasta) is False


@POSIX
@pytest.mark.parametrize("modulo,nome", _implementacoes("dentro"))
def test_dentro_resolve_o_link_da_pasta_mas_nao_o_do_caminho(monkeypatch, tmp_path, modulo, nome):
    _caixa(monkeypatch, modulo, False)
    dentro = _funcao(modulo, nome)
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)
    assert dentro(real / "x", link) is True  # the folder is resolved: its real place
    assert dentro(link / "x", link) is False  # the path is taken as given: the caller resolves it first


@POSIX
@pytest.mark.parametrize("modulo,nome", _implementacoes("dentro"))
def test_dentro_em_disco_que_ignora_caixa(monkeypatch, tmp_path, modulo, nome):
    _caixa(monkeypatch, modulo, True)
    dentro = _funcao(modulo, nome)
    pasta = tmp_path / "Pasta"
    pasta.mkdir()
    assert dentro(tmp_path / "Pasta" / "A", pasta) is True
    assert dentro(Path(str(tmp_path).upper()) / "PASTA" / "a", pasta) is True


@pytest.mark.parametrize("modulo,nome", _implementacoes("real"))
def test_real_resolve_o_caminho_e_texto_invalido_e_none(tmp_path, modulo, nome):
    real = _funcao(modulo, nome)
    arquivo = tmp_path / "a" / ".." / "f.txt"
    assert real(str(arquivo)) == (tmp_path / "f.txt").resolve()
    assert real(str(tmp_path)) == tmp_path.resolve()
    assert real("a\0b") is None


@pytest.mark.parametrize("modulo,nome", _implementacoes("real"))
def test_real_devolve_path_resolvido_de_caminho_relativo(tmp_path, monkeypatch, modulo, nome):
    monkeypatch.chdir(tmp_path)
    assert _funcao(modulo, nome)("sub/../x") == (tmp_path / "x").resolve()


@pytest.mark.parametrize("modulo,nome", _implementacoes("commit_do_checkout"))
def test_commit_do_checkout_e_o_rev_parse_head_do_checkout(monkeypatch, tmp_path, modulo, nome):
    from simplicio_video import tools
    chamadas = []
    monkeypatch.setattr(tools, "_git", lambda *a, cwd=None: chamadas.append((a, cwd)) or "f" * 40)
    assert _funcao(modulo, nome)(tmp_path) == "f" * 40
    assert chamadas == [(("rev-parse", "HEAD"), tmp_path)]


@pytest.mark.parametrize("modulo,nome", _implementacoes("commit_do_checkout"))
def test_commit_do_checkout_de_um_git_que_falha_e_texto_vazio(monkeypatch, tmp_path, modulo, nome):
    from simplicio_video import tools

    def quebrado(*a, cwd=None):
        raise tools.ToolError("git rev-parse: fatal")

    monkeypatch.setattr(tools, "_git", quebrado)
    assert _funcao(modulo, nome)(tmp_path) == ""


@pytest.mark.parametrize("helper", ["chave", "dentro", "real"])
def test_o_corpo_em_terceiros_e_o_mesmo_das_copias(helper):
    """AST of the body (docstring aside; the helper names dropped of their underscore): `terceiros` is a copy, not a rewrite.
    Skipped for a copy that was already removed from its module."""
    def corpo(func):
        no = ast.parse(textwrap.dedent(inspect.getsource(func))).body[0]
        itens = no.body[1:] if isinstance(no.body[0], ast.Expr) and isinstance(getattr(no.body[0], "value", None), ast.Constant) else no.body
        return "".join(ast.dump(i, annotate_fields=False) for i in itens).replace("'_chave'", "'chave'")

    novo = corpo(_funcao("terceiros", helper))
    comparadas = 0
    for modulo, nome in COPIAS[helper]:
        copia = getattr(importlib.import_module(f"simplicio_video.{modulo}"), nome, None)
        if copia is None:
            continue
        comparadas += 1
        assert corpo(copia) == novo, f"{modulo}.{nome} difere de terceiros.{helper}"
    if not comparadas:
        pytest.skip("todas as cópias migraram")


def test_case_insensitive_de_terceiros_segue_a_plataforma():
    assert _terceiros().CASE_INSENSITIVE == (sys.platform in ("darwin", "win32"))


def test_o_montage_tem_o_seu_dentro_diferente_e_fica_de_fora():
    """montage._dentro compares real paths with os.path.realpath on both sides: another rule, not a copy (so not in terceiros)."""
    from simplicio_video import montage
    # U22a: the `_dentro` of montage was one of the five ways of asking "is this path under that folder?" for the places a track does not
    # write. The one rule (`terceiros.lugar_proibido`) asks with `terceiros.dentro`, which resolves the folder as `os.path.realpath` does
    # and, on macOS and Windows, ignores case: montage has no `_dentro` of its own any more (the name of this test is historical: the id stays).
    assert not hasattr(montage, "_dentro")


# ---- U07: terceiros calls the public git of tools --------------------------------------------------------------------------------------


def test_commit_do_checkout_de_terceiros_chama_o_git_publico_de_tools(monkeypatch, tmp_path):
    """Same body, same answer as the copies, but through `tools.git` (the public name): replacing `tools.git` is enough, and the private
    `tools._git` (which the hermetic fixture turns into a refusal) is not called by name."""
    from simplicio_video import tools
    chamadas = []
    monkeypatch.setattr(tools, "git", lambda *a, cwd=None: chamadas.append((a, cwd)) or "e" * 40)
    assert _terceiros().commit_do_checkout(tmp_path) == "e" * 40
    assert chamadas == [(("rev-parse", "HEAD"), tmp_path)]


def test_commit_do_checkout_de_terceiros_com_o_git_publico_que_falha_e_texto_vazio(monkeypatch, tmp_path):
    from simplicio_video import tools

    def quebrado(*a, cwd=None):
        raise tools.ToolError("git rev-parse: fatal")

    monkeypatch.setattr(tools, "git", quebrado)
    assert _terceiros().commit_do_checkout(tmp_path) == ""


def test_commit_do_checkout_de_terceiros_trata_o_git_que_trava_como_o_que_falha(monkeypatch, tmp_path):
    """A `GitTimeout` is a `ToolError`: as today, it is an empty commit, not an exception."""
    from simplicio_video import tools

    def travado(*a, cwd=None):
        raise tools.GitTimeout("git rev-parse: tempo esgotado")

    monkeypatch.setattr(tools, "git", travado)
    assert _terceiros().commit_do_checkout(tmp_path) == ""


def test_terceiros_nao_usa_o_nome_privado_git_de_tools():
    arvore = ast.parse(Path(_terceiros().__file__).read_text(encoding="utf-8"))
    assert [n.lineno for n in ast.walk(arvore) if isinstance(n, ast.Attribute) and n.attr == "_git"] == []


# ---- U07: the default base is the `os.environ` of the CALL ----------------------------------------------------------------------------------


def test_sem_base_o_ambiente_trocado_depois_da_importacao_e_o_que_vale(monkeypatch):
    """The suite (golden, test_registro_trilhas) replaces `os.environ` by a dict: `env_para_terceiro()` must see the object that is there
    now, not the one `os.environ` was when `terceiros` was imported (a default argument is fixed at import)."""
    import os
    t = _terceiros()
    monkeypatch.setattr(os, "environ", {"PATH": "/trocado", "TMPDIR": "/t", "GEMINI_API_KEY": "segredo"})
    assert t.env_para_terceiro() == {"PATH": "/trocado"}
    assert t.env_para_terceiro(("TMPDIR",)) == {"PATH": "/trocado", "TMPDIR": "/t"}
    assert t.env_para_terceiro({"TMPDIR"}, base={"PATH": "/dado"}) == {"PATH": "/dado"}  # an explicit base still wins
    monkeypatch.setattr(os, "environ", {})
    assert t.env_para_terceiro(("TMPDIR",)) == {}


# ---- U22a: where a track does not write (ONE rule), and the text of a third party for an agent and for a terminal ------------------

POSIX25 = ("/etc", "/usr", "/bin", "/sbin", "/lib", "/lib32", "/lib64", "/libx32", "/boot", "/dev", "/proc", "/sys", "/run", "/opt", "/srv",
           "/snap", "/System", "/Library", "/Applications", "/private/etc", "/var/lib", "/var/log", "/var/spool", "/var/run", "/var/db")
WINDOWS4 = ("SYSTEMROOT", "PROGRAMFILES", "PROGRAMFILES(X86)", "PROGRAMDATA")
INICIO3 = (("Library", "LaunchAgents"), ("Library", "LaunchDaemons"),
           ("AppData", "Roaming", "Microsoft", "Windows", "Start Menu", "Programs", "Startup"))
STARTUP = ("Microsoft", "Windows", "Start Menu", "Programs", "Startup")


@pytest.fixture
def lugares(tmp_path, monkeypatch):
    """A home, a work folder, a tools folder, a data folder and an APPDATA folder in tmp (real paths), with the environment pointing at them
    and no Windows system root."""
    nomes = ("home", "work", "tools", "data", "appdata")
    w = SimpleNamespace(**{n: Path(os.path.realpath(tmp_path / n)) for n in nomes})
    for n in nomes:
        getattr(w, n).mkdir()
    monkeypatch.setenv("HOME", str(w.home))
    monkeypatch.setenv("SIMPLICIO_TOOLS_DIR", str(w.tools))
    monkeypatch.setenv("SIMPLICIO_VIDEO_DATA", str(w.data))
    monkeypatch.setenv("APPDATA", str(w.appdata))
    for var in ("USERPROFILE", *WINDOWS4):
        monkeypatch.delenv(var, raising=False)
    return w


def _real(caminho: str) -> Path:
    return Path(os.path.realpath(caminho))


def test_a_regra_unica_tem_as_tabelas_que_as_cinco_regras_tinham_juntas():
    t = _terceiros()
    assert t.RAIZES_POSIX == POSIX25 and len(set(t.RAIZES_POSIX)) == 25
    assert t.RAIZES_WINDOWS == WINDOWS4
    assert t.INICIO_AUTOMATICO == INICIO3
    assert t.STARTUP_DO_APPDATA == STARTUP


def test_os_textos_dos_motivos_sao_os_que_as_trilhas_ja_diziam():
    t = _terceiros()
    assert (t.SISTEMA, t.INICIO, t.OCULTA, t.GIT) == (
        "em pasta do sistema", "em pasta de início automático (LaunchAgents, LaunchDaemons, Startup)",
        "em pasta oculta do home (.ssh, .config, .claude...)", "dentro de uma pasta .git")
    assert (t.CODIGO, t.FERRAMENTAS, t.DADOS, t.SITE_PACKAGES, t.VENV) == (
        "dentro do código do motor", "dentro da pasta de ferramentas do motor",
        "dentro da pasta de dados do motor (jobs, tools, openmontage-data)", "dentro de site-packages (pacotes de um venv)",
        "dentro de um venv (pyvenv.cfg)")


def test_a_regra_devolve_texto_ou_none_nunca_texto_vazio(lugares):
    t = _terceiros()
    assert t.lugar_proibido(lugares.work / "ok.txt") is None
    assert t.lugar_proibido(_real("/etc/passwd")) == t.SISTEMA


@pytest.mark.parametrize("raiz", POSIX25)
def test_cada_uma_das_25_raizes_recusa_a_pasta_e_o_que_esta_dentro(lugares, raiz):
    t = _terceiros()
    alvo = _real(raiz)  # /bin, /lib and /var/run are links on most systems: the callers hand over the real path, so does this test
    assert t.lugar_proibido(alvo) == t.SISTEMA
    assert t.lugar_proibido(alvo / "x") == t.SISTEMA


@pytest.mark.parametrize("var", WINDOWS4)
def test_as_quatro_raizes_do_windows_vem_do_ambiente_na_hora(lugares, monkeypatch, var):
    t = _terceiros()
    alvo = lugares.work / "win" / "x"
    assert t.lugar_proibido(alvo) is None
    monkeypatch.setenv(var, str(lugares.work / "win"))
    assert t.lugar_proibido(alvo) == t.SISTEMA
    monkeypatch.setenv(var, "")
    assert t.lugar_proibido(alvo) is None  # an empty variable is no root


def test_var_inteiro_e_pasta_do_sistema_menos_var_tmp(lugares):
    t = _terceiros()
    for c in ("/var", "/var/cache/x", "/var/x", "/var/tmpx/y", "/var/www/x"):
        assert t.lugar_proibido(_real(c)) == t.SISTEMA, c
    assert t.lugar_proibido(_real("/var/tmp")) is None and t.lugar_proibido(_real("/var/tmp/x")) is None


def test_a_pasta_oculta_do_home_e_recusada_mas_nao_o_home_nem_o_resto(lugares):
    t = _terceiros()
    for c in (".ssh/x", ".config/a/b", ".claude", ".git/x"):  # a .git at the top of the home is a hidden folder first
        assert t.lugar_proibido(lugares.home / c) == t.OCULTA, c
    assert t.lugar_proibido(lugares.home) is None
    assert t.lugar_proibido(lugares.home / "docs" / "x.mp4") is None
    assert t.lugar_proibido(lugares.home / "docs" / ".oculta" / "x") is None  # only the first folder under the home counts
    assert t.lugar_proibido(lugares.work / ".ssh" / "x") is None  # and only under the home


@pytest.mark.parametrize("partes", INICIO3)
def test_as_pastas_de_inicio_automatico_do_home(lugares, partes):
    t = _terceiros()
    assert t.lugar_proibido(lugares.home.joinpath(*partes) / "x") == t.INICIO
    assert t.lugar_proibido(lugares.home.joinpath(*partes)) == t.INICIO


def test_o_startup_achado_por_appdata_e_nao_so_o_do_home(lugares, monkeypatch):
    t = _terceiros()
    alvo = lugares.appdata.joinpath(*STARTUP) / "x.bat"
    assert t.lugar_proibido(alvo) == t.INICIO
    monkeypatch.delenv("APPDATA")
    assert t.lugar_proibido(alvo) is None


def test_git_em_qualquer_ponto_do_caminho_e_so_a_parte_inteira(lugares):
    t = _terceiros()
    assert t.lugar_proibido(lugares.work / ".git" / "hooks" / "pre-commit") == t.GIT
    assert t.lugar_proibido(lugares.work / "proj" / ".git") == t.GIT
    for c in (".github/x", ".gitignore", "meu.git/x", "git/x"):
        assert t.lugar_proibido(lugares.work / c) is None, c


def test_a_caixa_so_conta_onde_a_plataforma_ignora_a_caixa(lugares, monkeypatch):
    t = _terceiros()
    caixas = (_real("/ETC/passwd"), lugares.work / ".GIT" / "x", Path(str(lugares.home).upper()) / ".ssh" / "x",
              lugares.work / "SITE-PACKAGES" / "x")
    monkeypatch.setattr(t, "CASE_INSENSITIVE", False)
    assert [t.lugar_proibido(c) for c in caixas] == [None, None, None, None]
    monkeypatch.setattr(t, "CASE_INSENSITIVE", True)
    assert [t.lugar_proibido(c) for c in caixas] == [t.SISTEMA, t.GIT, t.OCULTA, t.SITE_PACKAGES]


def test_os_lugares_do_proprio_motor(lugares):
    t = _terceiros()
    assert t.lugar_proibido(Path(t.__file__).resolve().parent / "x.py") == t.CODIGO
    assert t.lugar_proibido(lugares.tools / "x") == t.FERRAMENTAS
    assert t.lugar_proibido(lugares.data) == t.DADOS and t.lugar_proibido(lugares.data / "jobs" / "x.json") == t.DADOS
    assert t.lugar_proibido(lugares.work / "lib" / "python3" / "site-packages" / "x.py") == t.SITE_PACKAGES
    (lugares.work / "meuvenv").mkdir()
    (lugares.work / "meuvenv" / "pyvenv.cfg").write_text("home = /usr/bin\n")
    assert t.lugar_proibido(lugares.work / "meuvenv" / "out.mp4") == t.VENV
    assert t.lugar_proibido(lugares.work / "meuvenv" / "a" / "b" / "out.mp4") == t.VENV  # a pyvenv.cfg in any folder above
    assert t.lugar_proibido(lugares.work / "outra" / "out.mp4") is None


def test_os_lugares_proprios_vem_primeiro_na_ordem_dada_e_com_as_palavras_da_trilha(lugares):
    t = _terceiros()
    alvo = lugares.tools / "matchcut" / "x"
    checkout, ferramentas = (lugares.tools / "matchcut", "dentro do checkout"), (lugares.tools, t.FERRAMENTAS)
    assert t.lugar_proibido(alvo, [checkout, ferramentas]) == "dentro do checkout"
    assert t.lugar_proibido(alvo, [ferramentas, checkout]) == t.FERRAMENTAS
    assert t.lugar_proibido(alvo) == t.FERRAMENTAS  # without the track's own place the rule still refuses the folder
    assert t.lugar_proibido(lugares.work / "ok", [checkout, ferramentas]) is None
    assert t.lugar_proibido(lugares.data / "a", [((lugares.work, lugares.data), "dois lugares, um texto")]) == "dois lugares, um texto"
    assert t.lugar_proibido(lugares.data / "a", [(lugares.data, "um lugar só, um Path")]) == "um lugar só, um Path"


def test_os_proprios_sao_pedidos_um_a_um_so_ate_o_primeiro_que_casa(lugares):
    t = _terceiros()
    pedidos = []

    def proprios():
        pedidos.append(1)
        yield lugares.work, "primeiro"
        pedidos.append(2)
        yield lugares.tools, "segundo"

    assert t.lugar_proibido(lugares.work / "x", proprios()) == "primeiro"
    assert pedidos == [1]
    assert t.lugar_proibido(lugares.tools / "x", proprios()) == "segundo"
    assert pedidos == [1, 1, 2]


def test_motor_antes_so_troca_qual_das_duas_razoes_e_dita(lugares, monkeypatch):
    t = _terceiros()
    dados = lugares.home / ".simplicio-video"  # the default data folder: also a hidden folder of the home
    (dados / "tools").mkdir(parents=True)
    monkeypatch.setenv("SIMPLICIO_VIDEO_DATA", str(dados))
    monkeypatch.setenv("SIMPLICIO_TOOLS_DIR", str(dados / "tools"))
    site = _real("/usr") / "lib" / "python3" / "site-packages" / "x.py"
    casos = [(dados / "jobs" / "x.json", t.OCULTA, t.DADOS), (dados / "tools" / "x", t.OCULTA, t.FERRAMENTAS), (site, t.SISTEMA, t.SITE_PACKAGES),
             (_real("/var/www/s/.git/x"), t.GIT, t.SISTEMA)]
    for alvo, depois, antes in casos:
        assert t.lugar_proibido(alvo) == depois, alvo
        assert t.lugar_proibido(alvo, motor_antes=True) == antes, alvo
    assert t.lugar_proibido(lugares.work / "ok", motor_antes=True) is None  # the order never decides WHETHER a path is refused


def test_a_comparacao_e_a_que_o_chamador_passa(lugares):
    t = _terceiros()
    assert t.lugar_proibido(_real("/etc/x"), dentro=lambda caminho, pasta: False, chave=lambda caminho: ()) is None
    assert t.lugar_proibido(lugares.work / "x", dentro=lambda caminho, pasta: True) == t.SISTEMA  # the first folder it is asked about
    assert t.lugar_proibido(lugares.work / "x", chave=lambda caminho: (".git",)) == t.GIT


@pytest.mark.parametrize("modulo", ["instagram", "matchcut", "video_to_skill"])
def test_cada_trilha_passa_a_sua_propria_comparacao_e_a_sua_caixa(lugares, monkeypatch, modulo):
    """The tests of these tracks flip the `CASE_INSENSITIVE` of the module (a darwin or win32 run does it by itself): the rule has to ask
    with the `_dentro` and the `_chave` of the module, which read that flag when they are called."""
    mod = importlib.import_module(f"simplicio_video.{modulo}")
    alvo = _real("/ETC/passwd")
    monkeypatch.setattr(mod, "CASE_INSENSITIVE", True)
    assert mod._lugar_proibido(alvo) == "em pasta do sistema"
    monkeypatch.setattr(mod, "CASE_INSENSITIVE", False)
    assert mod._lugar_proibido(alvo) == ""


def test_sem_casa_a_regra_nao_levanta_e_segue_sem_o_lugar_que_nao_achou(lugares, monkeypatch):
    from simplicio_video import hostos, paths, tools
    t = _terceiros()

    def sem_casa(*a, **k):
        raise hostos.SemCasa("sem casa")

    monkeypatch.setattr(tools, "tools_dir", sem_casa)
    monkeypatch.setattr(paths, "data_root", sem_casa)
    assert t.lugar_proibido(lugares.work / "x") is None
    assert t.lugar_proibido(_real("/etc/x")) == t.SISTEMA and t.lugar_proibido(lugares.home / ".ssh" / "x") == t.OCULTA


def test_a_regra_nao_importa_paths_nem_tools_na_importacao():
    codigo = "import sys; import simplicio_video.terceiros; print(sorted(m for m in ('simplicio_video.paths', 'simplicio_video.tools', 'simplicio_video.hostos') if m in sys.modules))"
    import subprocess
    r = subprocess.run([sys.executable, "-c", codigo], capture_output=True, text=True,
                       env={**os.environ, "PYTHONPATH": str(Path(_terceiros().__file__).resolve().parent.parent)})
    assert r.returncode == 0 and r.stdout.strip() == "[]", r.stderr


# ---- the text of a third party: one function for the three tracks ------------------------------------------------------------------

def test_o_seletor_de_variacao_nos_limites():
    t = _terceiros()
    sim = ("\ufe00", "\ufe0f", "\U000e0100", "\U000e01ef")
    nao = ("\ufdff", "\ufe10", "\U000e00ff", "\U000e01f0", "a", "\u0301", "\u200d")
    assert [t.seletor_de_variacao(c) for c in sim] == [True] * 4
    assert [t.seletor_de_variacao(c) for c in nao] == [False] * len(nao)


def test_limpa_mcp_tira_controle_bidi_largura_zero_tag_e_seletor_de_variacao():
    t = _terceiros()
    assert t.limpa_mcp("a\x1b[31m\u202e\u200b\ufe0f\U000e0100\U000e0041b\x00") == "a[31mb"
    assert t.limpa_mcp("a\r\nb\tc\nd\re") == "a\nb\tc\nde"
    assert t.limpa_mcp("ação, coração 日本語 😀 e\u0301") == "ação, coração 日本語 😀 e\u0301"


def test_visivel_marca_o_que_limpa_mcp_tira_em_vez_de_esconder():
    t = _terceiros()
    assert t.visivel("a\x1b[31mb\x07\x00\tc\nd") == "a\u241b[31mb\u2407\u2400\tc\nd"
    assert t.visivel("x\x7f\x9b\u202e\u200b\u2028\U000e0041y") == "x\u2421<U+009B><U+202E><U+200B><U+2028><U+E0041>y"
    assert t.visivel("a\ufe0fb\U000e0100c\ufe00") == "a<U+FE0F>b<U+E0100>c<U+FE00>"
    assert t.visivel("ação — 日本 😀 ok\r\nfim\r") == "ação — 日本 😀 ok\nfim\u240d"


def test_as_tres_trilhas_usam_a_mesma_funcao_de_texto_de_terceiro():
    from simplicio_video import instagram, matchcut, video_to_skill
    t = _terceiros()
    assert matchcut._limpa_mcp is instagram._limpa_mcp is video_to_skill.limpa_mcp is t.limpa_mcp
    assert matchcut.visivel is instagram.visivel is video_to_skill.visivel is t.visivel


# ---- U22a, revisão independente: nome longo demais para o disco ----------------------------------------------------------------------

def test_um_nome_com_mais_de_255_bytes_nao_faz_a_regra_levantar(lugares):
    """A sonda de `pyvenv.cfg` olha cada pasta acima do caminho, e o `Path.is_file()` (Python 3.11 a 3.13) levanta OSError (ENAMETOOLONG) para
    um nome maior do que o disco aceita. Esse nome não existe: não é razão para recusar, nem para um traceback."""
    t = _terceiros()
    longo = "a" * 300
    assert t.lugar_proibido(lugares.work / longo / "x") is None
    assert t.lugar_proibido(lugares.work / "ok" / longo) is None


def test_a_sonda_pula_a_pasta_que_o_disco_nao_consulta_e_olha_a_de_cima(lugares):
    t = _terceiros()
    (lugares.work / "meuvenv").mkdir()
    (lugares.work / "meuvenv" / "pyvenv.cfg").write_text("home = /usr/bin\n")
    assert t.lugar_proibido(lugares.work / "meuvenv" / ("a" * 300) / "x") == t.VENV


# ---- U22a, revisão independente: a exceção de /var/tmp segue a regra de caixa do resto (verde antes e depois) -----------------------------

def test_a_excecao_de_var_tmp_e_exata_onde_o_disco_distingue_caixa(lugares, monkeypatch):
    """No Linux `/var/Tmp` e `/var/TMP` são outras pastas, que não a `/var/tmp`: seguem recusadas como o resto de /var."""
    t = _terceiros()
    monkeypatch.setattr(t, "CASE_INSENSITIVE", False)
    assert t.lugar_proibido(Path("/var/tmp/x")) is None
    for c in ("/var/Tmp/x", "/var/TMP/x", "/var/tmpx/x", "/var/tmp2/x"):
        assert t.lugar_proibido(Path(c)) == t.SISTEMA, c


def test_a_excecao_de_var_tmp_ignora_a_caixa_so_onde_o_sistema_ignora(lugares, monkeypatch):
    """Com a flag ligada (macOS, Windows) `/var/Tmp` é a própria `/var/tmp`, e `/ETC` é a pasta do sistema: a mesma flag decide as duas."""
    t = _terceiros()
    monkeypatch.setattr(t, "CASE_INSENSITIVE", True)
    for c in ("/var/tmp/x", "/var/Tmp/x", "/var/TMP/x"):
        assert t.lugar_proibido(Path(c)) is None, c
    for c in ("/var/tmpx/x", "/var/tmp2/x", "/ETC/x"):
        assert t.lugar_proibido(Path(c)) == t.SISTEMA, c


@pytest.mark.parametrize("modulo", ["instagram", "matchcut", "video_to_skill"])
def test_cada_trilha_segue_a_propria_caixa_na_excecao_de_var_tmp(lugares, monkeypatch, modulo):
    mod = importlib.import_module(f"simplicio_video.{modulo}")
    alvo = Path("/var/Tmp/x")
    monkeypatch.setattr(mod, "CASE_INSENSITIVE", False)
    assert mod._lugar_proibido(alvo) == "em pasta do sistema"
    monkeypatch.setattr(mod, "CASE_INSENSITIVE", True)
    assert mod._lugar_proibido(alvo) == ""


def test_montage_e_voicestudio_seguem_a_caixa_de_terceiros_na_excecao_de_var_tmp(lugares, monkeypatch):
    from simplicio_video import montage, voicestudio
    t = _terceiros()
    alvo = Path("/var/Tmp/x")
    monkeypatch.setattr(t, "CASE_INSENSITIVE", False)
    assert montage._lugar_proibido(alvo) == "em pasta do sistema" and voicestudio._forbidden_place(alvo) == "em pasta do sistema"
    monkeypatch.setattr(t, "CASE_INSENSITIVE", True)
    assert montage._lugar_proibido(alvo) == "" and voicestudio._forbidden_place(alvo) is None


# ---- U22a, revisão independente: /var inteiro não pode quebrar o temporário nem o home do usuário -------------------------------------

SOB_VAR_HOME = "/var/zz-u22a-home/user"  # pastas FALSAS sob o /var real: nada é criado lá
SOB_VAR_TMP = "/var/zz-u22a-tmp/T"


@pytest.fixture
def sob_var(lugares, monkeypatch):
    """O home e o temporário do usuário moram sob /var: no macOS o `$TMPDIR` é /var/folders/..., e numa distro ostree (Silverblue, Bazzite,
    CoreOS) o /home é /var/home."""
    monkeypatch.setenv("HOME", SOB_VAR_HOME)
    monkeypatch.setenv("TMPDIR", SOB_VAR_TMP + "-env")
    monkeypatch.setattr(tempfile, "tempdir", SOB_VAR_TMP)
    return SimpleNamespace(home=Path(SOB_VAR_HOME), tmp=Path(SOB_VAR_TMP), tmp_env=Path(SOB_VAR_TMP + "-env"))


def test_o_temporario_do_usuario_sob_var_nao_e_recusado(sob_var):
    t = _terceiros()
    for c in (sob_var.tmp / "x", sob_var.tmp / "a" / "b.mp4", sob_var.tmp_env / "x", Path("/var/folders/ab/cdef/T/x")):
        assert t.lugar_proibido(c) is None, c


def test_o_home_real_do_usuario_sob_var_nao_e_recusado(sob_var):
    t = _terceiros()
    for c in (sob_var.home / "proj" / "out.mp4", sob_var.home / "Videos" / "a.mp4"):
        assert t.lugar_proibido(c) is None, c


def test_o_resto_de_var_segue_recusado_com_o_temporario_e_o_home_sob_var(sob_var):
    t = _terceiros()
    for c in ("/var", "/var/www/html/x", "/var/media/x", "/var/data/x", "/var/opt/x", "/var/local/x", "/var/cache/x",
              "/var/zz-u22a-home/other/x", "/var/zz-u22a-home/x", "/var/zz-u22a-tmp/x", "/var/zz-u22a-tmp/T2/x"):
        assert t.lugar_proibido(Path(c)) == t.SISTEMA, c
    assert t.lugar_proibido(Path("/var/tmp/x")) is None  # a única exceção de antes


def test_as_outras_regras_valem_dentro_das_arvores_liberadas(sob_var, monkeypatch):
    t = _terceiros()
    assert t.lugar_proibido(sob_var.home / ".ssh" / "x") == t.OCULTA
    assert t.lugar_proibido(sob_var.home / "proj" / ".git" / "x") == t.GIT
    assert t.lugar_proibido(sob_var.tmp / ".git" / "x") == t.GIT
    assert t.lugar_proibido(sob_var.home / "Library" / "LaunchAgents" / "x.plist") == t.INICIO
    assert t.lugar_proibido(sob_var.tmp / "lib" / "python3" / "site-packages" / "x.py") == t.SITE_PACKAGES
    monkeypatch.setenv("SIMPLICIO_VIDEO_DATA", str(sob_var.home / "simplicio-data"))
    monkeypatch.setenv("SIMPLICIO_TOOLS_DIR", str(sob_var.home / "ferramentas"))
    assert t.lugar_proibido(sob_var.home / "simplicio-data" / "jobs" / "x") == t.DADOS
    assert t.lugar_proibido(sob_var.home / "ferramentas" / "x") == t.FERRAMENTAS
    # as raízes de sistema de dentro de /var também: um home em /var/lib continua sendo pasta do sistema
    monkeypatch.setenv("HOME", "/var/lib/zz-u22a-svc")
    assert t.lugar_proibido(Path("/var/lib/zz-u22a-svc/x")) == t.SISTEMA


def test_um_home_ou_temporario_que_e_o_proprio_var_nao_libera_nada(lugares, monkeypatch):
    t = _terceiros()
    monkeypatch.setenv("HOME", "/var")
    monkeypatch.setenv("TMPDIR", "/var")
    monkeypatch.setattr(tempfile, "tempdir", "/var")
    for c in ("/var/x", "/var/www/x", "/var/zz-u22a-home/x"):
        assert t.lugar_proibido(Path(c)) == t.SISTEMA, c


def test_a_regra_de_var_nao_levanta_sem_pasta_temporaria_usavel(sob_var, monkeypatch):
    t = _terceiros()

    def sem_temporario():
        raise FileNotFoundError("sem pasta temporária utilizável")

    monkeypatch.setattr(tempfile, "gettempdir", sem_temporario)
    assert t.lugar_proibido(sob_var.tmp_env / "x") is None  # o $TMPDIR ainda diz qual é
    assert t.lugar_proibido(sob_var.home / "proj" / "x") is None
    assert t.lugar_proibido(Path("/var/www/x")) == t.SISTEMA


# As árvores do usuário sob /var são comparadas com o MESMO `dentro` do resto da regra (a flag de caixa do módulo; verde antes e depois):
# o mesmo caminho, só com outra caixa depois de /var, é liberado onde a flag está ligada e recusado onde está desligada.
CAIXA_SOB_VAR = (Path("/var/ZZ-U22A-TMP/T/x"), Path("/var/ZZ-U22A-TMP/T-ENV/a/b.mp4"), Path("/var/ZZ-U22A-HOME/USER/proj/out.mp4"))


@pytest.mark.parametrize("modulo", ["instagram", "matchcut", "video_to_skill"])
def test_cada_trilha_segue_a_propria_caixa_nas_arvores_do_usuario_sob_var(sob_var, monkeypatch, modulo):
    mod = importlib.import_module(f"simplicio_video.{modulo}")
    for alvo in CAIXA_SOB_VAR:
        monkeypatch.setattr(mod, "CASE_INSENSITIVE", False)
        assert mod._lugar_proibido(alvo) == "em pasta do sistema", alvo
        monkeypatch.setattr(mod, "CASE_INSENSITIVE", True)
        assert mod._lugar_proibido(alvo) == "", alvo


def test_montage_e_voicestudio_seguem_a_caixa_de_terceiros_nas_arvores_do_usuario_sob_var(sob_var, monkeypatch):
    from simplicio_video import montage, voicestudio
    t = _terceiros()
    for alvo in CAIXA_SOB_VAR:
        monkeypatch.setattr(t, "CASE_INSENSITIVE", False)
        assert montage._lugar_proibido(alvo) == "em pasta do sistema" and voicestudio._forbidden_place(alvo) == "em pasta do sistema", alvo
        monkeypatch.setattr(t, "CASE_INSENSITIVE", True)
        assert montage._lugar_proibido(alvo) == "" and voicestudio._forbidden_place(alvo) is None, alvo


# O `$TMPDIR` e o HOME podem chegar por um LINK (macOS: `/var` é um link para `/private/var`; ostree: `/home` é `/var/home`): vale a pasta para
# onde o link aponta, que é a que o `real` do caminho de saída já traz (verde antes e depois). O destino é FALSO, sob o /var real: nada é criado lá.

@POSIX
def test_o_temporario_que_chega_por_um_link_para_var_vale_pela_pasta_para_onde_aponta(lugares, monkeypatch, tmp_path):
    t = _terceiros()
    destino = Path("/var/zz-u22a-real/T")
    link = tmp_path / "link-tmp"
    link.symlink_to(destino)
    monkeypatch.setenv("TMPDIR", str(link))
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path / "outro-tmp"))
    assert t.lugar_proibido(destino / "x") is None
    assert t.lugar_proibido(Path("/var/zz-u22a-real/T2/x")) == t.SISTEMA  # a pasta ao lado não é a do temporário


@POSIX
def test_o_home_que_chega_por_um_link_para_var_vale_pela_pasta_para_onde_aponta(lugares, monkeypatch, tmp_path):
    t = _terceiros()
    destino = Path("/var/zz-u22a-real/home/user")
    link = tmp_path / "link-home"
    link.symlink_to(destino)
    monkeypatch.setenv("HOME", str(link))
    assert t.lugar_proibido(destino / "proj" / "out.mp4") is None
    assert t.lugar_proibido(destino / ".ssh" / "x") == t.OCULTA  # as outras regras seguem valendo dentro dela
    assert t.lugar_proibido(Path("/var/zz-u22a-real/home/outro/x")) == t.SISTEMA
