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
import sys
import textwrap
import unicodedata
from pathlib import Path

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
    fonte = inspect.getsource(montage._dentro)
    assert "os.path.realpath(pasta)" in fonte


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
