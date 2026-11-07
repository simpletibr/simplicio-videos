"""U07 (wave 3): the modules that are not a track (busca, openverse, status, download, swap_providers/http, commands/update) use `rede`
and `terceiros` instead of their own copies. Same answers, same messages, same environment for the child; only the place changes.

Green before and after (characterization):
* `SIMPLICIO_OFFLINE=On ` (spaces, capitals) gives the SAME answer as `1` in every reader of the variable, and the answers of today
  (type and text, byte for byte) are frozen here: a refusal that says "não vou ..." keeps saying it, one that says
  "SIMPLICIO_OFFLINE=1: rede bloqueada" keeps that text.
* A test that replaces `swap_providers.http.request` still intercepts the Openverse client (tests/test_openverse.py relies on it).

Red before (the migration):
* `swap_providers/http.py` is only a name for `rede`: the SAME objects (`is`), no body of its own; `commands.update._offline` IS `rede.offline`.
* Openverse imports `rede`, not `swap_providers` (importing it no longer loads the swap adapters).
* No file of this wave reads SIMPLICIO_OFFLINE or writes the truthy tuple itself.
* download, busca and status build the environment of the child through `terceiros.env_para_terceiro(extra, base=os.environ)` (the
  final sets are frozen by tests/golden/test_env_terceiros.py and tests/test_terceiros.py, which stay green).
* status reads git through the public `tools.git` and the tinyfish version through the public `busca.versao_cli`.

No test touches the network.
"""
from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import ROOT, offline_env

PKG = ROOT / "src" / "simplicio_video"
PREFIXO = "modo offline (SIMPLICIO_OFFLINE=1): não vou "
VALORES_ESTRANHOS = ["On ", " ON", "Yes\t", "TRUE ", " tRuE "]


# ---- the readers of SIMPLICIO_OFFLINE, one callable each -----------------------------------------------------------------------


class _Feito:
    returncode, stdout, stderr = 0, "abc123", ""


def _git_falso(checkout, *args):
    return _Feito()


def _clones() -> dict:
    from simplicio_video import instagram, matchcut, moneyprinter, montage, rea_video, toonflow, video_to_skill
    return {"toonflow.clone_toonflow": toonflow.clone_toonflow, "moneyprinter.clone_moneyprinter": moneyprinter.clone_moneyprinter,
            "matchcut.clone_matchcut": matchcut.clone_matchcut, "instagram.clone_instagram": instagram.clone_instagram,
            "montage.clone_openmontage": montage.clone_openmontage, "rea_video.clone_rea_video": rea_video.clone_rea_video,
            "video_to_skill.clone": video_to_skill.clone}


def _leitores() -> dict:
    from simplicio_video import busca, instagram, montage, openverse as ov, rede, tools_update, toonflow
    from simplicio_video.commands import update
    from simplicio_video.swap_providers import http
    return {
        "rede.offline": rede.offline,
        "rede.request": lambda: rede.request("GET", "https://a.example/"),
        "swap_providers.http.request": lambda: http.request("GET", "https://a.example/"),
        "busca._exige_rede": busca._exige_rede,
        "openverse._real_http_get": lambda: ov._real_http_get("https://a.example/x", "203.0.113.9"),
        "openverse._call": lambda: ov._call("GET", "https://a.example/x"),
        "commands.update._offline": update._offline,
        "commands.update.fetch_latest_tag": update.fetch_latest_tag,
        "commands.update._source_state": lambda: update._source_state(_git_falso, Path("/x"), "0.1.0"),
        "tools_update.live_io": lambda: tools_update.live_io().network,
        "toonflow._offline": toonflow._offline,
        "instagram._offline": instagram._offline,
        "montage._offline": montage._offline,
        **_clones(),
    }


NOMES_DOS_CLONES = ["toonflow.clone_toonflow", "moneyprinter.clone_moneyprinter", "matchcut.clone_matchcut", "instagram.clone_instagram",
                    "montage.clone_openmontage", "rea_video.clone_rea_video", "video_to_skill.clone"]
NOMES_DOS_LEITORES = ["rede.offline", "rede.request", "swap_providers.http.request", "busca._exige_rede", "openverse._real_http_get",
                      "openverse._call", "commands.update._offline", "commands.update.fetch_latest_tag", "commands.update._source_state",
                      "tools_update.live_io", "toonflow._offline", "instagram._offline", "montage._offline", *NOMES_DOS_CLONES]

# readers that answer without touching anything when the variable is off: the answer of "0" must differ from the one of "1"
SEM_EFEITO_ONLINE = ["rede.offline", "busca._exige_rede", "commands.update._offline", "tools_update.live_io", "toonflow._offline",
                     "instagram._offline", "montage._offline"]


def _resposta(chamada):
    try:
        return ("devolveu", repr(chamada()))
    except Exception as erro:  # noqa: BLE001 (the answer IS the exception: type and text)
        return ("levantou", type(erro).__name__, str(erro))


@pytest.mark.parametrize("valor", VALORES_ESTRANHOS)
@pytest.mark.parametrize("leitor", NOMES_DOS_LEITORES)
def test_simplicio_offline_com_espaco_e_caixa_diferentes_da_a_mesma_resposta_que_1_em_todo_leitor(monkeypatch, leitor, valor):
    chamada = _leitores()[leitor]
    monkeypatch.setenv("SIMPLICIO_OFFLINE", "1")
    com_um = _resposta(chamada)
    monkeypatch.setenv("SIMPLICIO_OFFLINE", valor)
    assert _resposta(chamada) == com_um, leitor


@pytest.mark.parametrize("leitor", SEM_EFEITO_ONLINE)
def test_o_valor_0_e_o_ambiente_sem_a_variavel_dao_a_resposta_de_rede_liberada(monkeypatch, leitor):
    chamada = _leitores()[leitor]
    monkeypatch.setenv("SIMPLICIO_OFFLINE", "1")
    offline = _resposta(chamada)
    for liberado in ("0", "off", " "):
        monkeypatch.setenv("SIMPLICIO_OFFLINE", liberado)
        assert _resposta(chamada) != offline, (leitor, liberado)
    monkeypatch.delenv("SIMPLICIO_OFFLINE")
    assert _resposta(chamada) != offline, leitor


@pytest.mark.parametrize("trilha", NOMES_DOS_CLONES)
@pytest.mark.parametrize("valor", ["1", *VALORES_ESTRANHOS])
def test_a_recusa_de_cada_clone_comeca_pela_frase_unica_com_qualquer_grafia_do_valor(monkeypatch, trilha, valor):
    monkeypatch.setenv("SIMPLICIO_OFFLINE", valor)
    with pytest.raises(Exception) as caught:  # noqa: PT011 (each track has its own error class)
        _clones()[trilha]()
    assert str(caught.value).startswith(PREFIXO + "clonar o "), str(caught.value)


# what each reader answers today in offline mode (frozen: type and text, byte for byte)
RESPOSTA_DE_HOJE = {
    "busca._exige_rede": ("BuscaError", "modo offline (SIMPLICIO_OFFLINE=1): não vou chamar o TinyFish. "
                                        "Só resultados que já estão no cache saem sem rede"),
    "openverse._real_http_get": ("OpenverseError", "SIMPLICIO_OFFLINE=1: rede bloqueada"),
    "openverse._call": ("OpenverseError", "sem rede para falar com o Openverse (SIMPLICIO_OFFLINE=1: rede bloqueada). "
                                          "Repita quando houver rede, ou repita uma busca que já esteja no cache"),
    "rede.request": ("NetworkError", "SIMPLICIO_OFFLINE=1: rede bloqueada"),
    "swap_providers.http.request": ("NetworkError", "SIMPLICIO_OFFLINE=1: rede bloqueada"),
    "commands.update.fetch_latest_tag": ("OSError", "SIMPLICIO_OFFLINE=1: rede bloqueada"),
    "commands.update._source_state": ("OSError", "SIMPLICIO_OFFLINE=1: rede bloqueada (o `git fetch` do checkout não roda)"),
}


@pytest.mark.parametrize("leitor", sorted(RESPOSTA_DE_HOJE))
def test_a_mensagem_de_hoje_de_cada_recusa_offline_fica_byte_a_byte(monkeypatch, leitor):
    monkeypatch.setenv("SIMPLICIO_OFFLINE", "1")
    assert _resposta(_leitores()[leitor]) == ("levantou", *RESPOSTA_DE_HOJE[leitor])


@pytest.mark.parametrize("valor", ["1", *VALORES_ESTRANHOS])
def test_a_recusa_do_busca_e_do_openverse_na_linha_de_comando_nao_depende_da_grafia(monkeypatch, capsys, valor):
    from simplicio_video.cli import main
    monkeypatch.setenv("SIMPLICIO_OFFLINE", valor)
    visto = {}
    for nome, argv in (("busca", ["busca", "consulta", "teste de rede"]), ("openverse", ["openverse", "search", "--tipo", "imagem", "--consulta", "gato"])):
        rc = main(argv)
        out, err = capsys.readouterr()
        visto[nome] = (rc, out, err)
    assert visto["busca"] == (1, "", "busca: " + RESPOSTA_DE_HOJE["busca._exige_rede"][1] + "\n")
    assert visto["openverse"] == (1, "", "openverse: " + RESPOSTA_DE_HOJE["openverse._call"][1] + "\n")


# ---- swap_providers/http.py is a name for `rede` ----------------------------------------------------------------------------------


@pytest.mark.parametrize("nome", ["request", "Response", "NetworkError", "NoRedirect"])
def test_o_shim_de_swap_providers_http_e_a_mesma_coisa_que_rede(nome):
    from simplicio_video import rede
    from simplicio_video.swap_providers import http
    assert getattr(http, nome) is getattr(rede, nome)


def test_o_nome_privado_antigo_do_handler_de_redirecionamento_continua_no_shim():
    from simplicio_video import rede
    from simplicio_video.swap_providers import http
    assert http._NoRedirect is rede.NoRedirect


def test_o_shim_continua_sendo_o_modulo_rede_num_processo_novo_com_o_urllib_so_sob_demanda():
    """U07b: `rede` builds `NoRedirect` on first access (module `__getattr__`) instead of at import. In a clean interpreter, where the
    shim is the first thing to touch it (it reads `rede.NoRedirect` to add the old private name), `request`, `Response`, `NetworkError`,
    `NoRedirect` and `_NoRedirect` are still the very same objects under both names and the shim still IS the module."""
    codigo = ("import json, sys\n"
              f"sys.path.insert(0, {str(ROOT / 'src')!r})\n"
              "from simplicio_video.swap_providers import http\n"
              "from simplicio_video import rede\n"
              "print(json.dumps({'modulo': http is rede is sys.modules['simplicio_video.swap_providers.http'],\n"
              "                  'nomes': [getattr(http, n) is getattr(rede, n) for n in ('request', 'Response', 'NetworkError', 'NoRedirect')],\n"
              "                  'privado': http._NoRedirect is rede.NoRedirect is rede._NoRedirect}))\n")
    r = subprocess.run([sys.executable, "-I", "-c", codigo], capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout) == {"modulo": True, "nomes": [True] * 4, "privado": True}


def test_o_shim_nao_tem_corpo_proprio_so_reexporta():
    arvore = ast.parse((PKG / "swap_providers" / "http.py").read_text(encoding="utf-8"))
    assert not [n.name for n in ast.walk(arvore) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]


def test_trocar_o_request_do_shim_continua_valendo_para_o_cliente_do_openverse(monkeypatch):
    """tests/test_openverse.py replaces `swap_providers.http.request` and expects Openverse to call the fake: a shim that only copies
    the name would let the real request through (and offline mode would answer for it)."""
    from simplicio_video import openverse as ov
    from simplicio_video.swap_providers import http
    visto = []

    def falso(method, url, headers=None, **kw):
        visto.append((method, url))
        return http.Response(200, b"{}", {})

    monkeypatch.setattr(http, "request", falso)
    resposta = ov._call("GET", "https://api.openverse.org/v1/images/")
    assert resposta.status == 200 and visto == [("GET", "https://api.openverse.org/v1/images/")]


def test_trocar_o_request_do_shim_continua_valendo_para_os_adaptadores_do_swap(monkeypatch):
    from simplicio_video.swap_providers import base, http
    assert base.http is http
    monkeypatch.setattr(http, "request", lambda *a, **k: "do teste")
    assert base.http.request("GET", "https://a.example/") == "do teste"


# ---- Openverse imports `rede`, not swap_providers ----------------------------------------------------------------------------------


def test_o_openverse_nao_importa_swap_providers():
    arvore = ast.parse((PKG / "openverse.py").read_text(encoding="utf-8"))
    importados = []
    for no in ast.walk(arvore):
        if isinstance(no, ast.ImportFrom):
            importados.append(("." * no.level) + (no.module or "") + ":" + ",".join(a.name for a in no.names))
        elif isinstance(no, ast.Import):
            importados += [a.name for a in no.names]
    assert not [i for i in importados if "swap_providers" in i], importados
    assert any(i.startswith(".:") and "rede" in i.split(":")[1].split(",") for i in importados), importados


def test_importar_o_openverse_nao_carrega_os_adaptadores_do_swap():
    codigo = "import sys, simplicio_video.openverse; print(sorted(m for m in sys.modules if 'swap_providers' in m))"
    feito = subprocess.run([sys.executable, "-c", codigo], capture_output=True, text=True, env=offline_env(), timeout=60)
    assert feito.returncode == 0, feito.stderr
    assert feito.stdout.strip() == "[]", feito.stdout


# ---- who reads SIMPLICIO_OFFLINE ------------------------------------------------------------------------------------------------------


MODULOS_DA_ONDA = ["busca.py", "openverse.py", "swap_providers/http.py", "commands/update.py"]


@pytest.mark.parametrize("arquivo", MODULOS_DA_ONDA)
def test_nenhum_modulo_da_onda_le_a_variavel_nem_escreve_a_tupla_dos_valores_verdadeiros(arquivo):
    texto = (PKG / arquivo).read_text(encoding="utf-8")
    assert '"1", "true", "yes", "on"' not in texto
    assert 'get("SIMPLICIO_OFFLINE"' not in texto and "['SIMPLICIO_OFFLINE']" not in texto and '["SIMPLICIO_OFFLINE"]' not in texto


def test_a_rede_e_o_lugar_onde_a_variavel_e_lida():
    texto = (PKG / "rede.py").read_text(encoding="utf-8")
    assert texto.count('"1", "true", "yes", "on"') == 1 and 'get("SIMPLICIO_OFFLINE"' in texto


def test_o_offline_de_commands_update_e_o_de_rede():
    from simplicio_video import rede
    from simplicio_video.commands import update
    assert update._offline is rede.offline


def test_o_busca_recusa_com_a_frase_unica_de_rede(monkeypatch):
    """busca's refusal is of the family "não vou ...": the text is what `rede.motivo_offline` builds, and busca.py no longer writes the
    opening of the sentence itself."""
    from simplicio_video import busca, rede
    monkeypatch.setenv("SIMPLICIO_OFFLINE", "1")
    with pytest.raises(busca.BuscaError) as caught:
        busca._exige_rede()
    assert str(caught.value) == rede.motivo_offline("chamar o TinyFish. Só resultados que já estão no cache saem sem rede")
    assert "SIMPLICIO_OFFLINE=1): não vou" not in (PKG / "busca.py").read_text(encoding="utf-8")


# ---- the environment of a third-party child -------------------------------------------------------------------------------------------


class _Espia:
    def __init__(self, monkeypatch):
        from simplicio_video import terceiros
        self.chamadas = []
        real = terceiros.env_para_terceiro

        def espia(extra=(), *, base=os.environ):
            self.chamadas.append((tuple(extra), base))
            return real(extra, base=base)

        monkeypatch.setattr(terceiros, "env_para_terceiro", espia)


def _env_de_status(monkeypatch):
    """The `env=` that `status._primeira_linha` hands to subprocess.run (the run is replaced: nothing starts)."""
    from simplicio_video import status

    class Fim:
        returncode, stdout, stderr = 0, "x", ""

    visto = {}

    def espia(cmd, **kw):
        visto["env"] = kw.get("env")
        return Fim()

    monkeypatch.setattr(status.subprocess, "run", espia)
    status._primeira_linha(["x"])
    return visto["env"]


@pytest.mark.parametrize("modulo", ["download", "busca", "status"])
def test_o_ambiente_do_filho_sai_de_env_para_terceiro_com_a_base_lida_na_hora_da_chamada(monkeypatch, modulo):
    """The module passes `base=os.environ` at the call (the default of the function is the object `os.environ` had when `terceiros`
    was imported: a test, or a program, that replaces `os.environ` would not be seen) and only what it has on top of the core."""
    from simplicio_video import busca, download, terceiros
    espia = _Espia(monkeypatch)
    ambiente = {n: "v:" + n for n in (*terceiros.NUCLEO_ENV, "TMPDIR", "HTTPS_PROXY", "TINYFISH_API_KEY", "LC_CTYPE", "GEMINI_API_KEY")}
    monkeypatch.setattr(os, "environ", ambiente)
    if modulo == "download":
        env = download._ambiente()
    elif modulo == "busca":
        env = busca._ambiente_filho()
    else:
        env = _env_de_status(monkeypatch)
    assert len(espia.chamadas) == 1, espia.chamadas
    extra, base = espia.chamadas[0]
    assert base is ambiente
    assert not set(extra) & set(terceiros.NUCLEO_ENV), "`extra` is what the module has on top of the core, not the core again"
    assert "GEMINI_API_KEY" not in env and "GEMINI_API_KEY" not in extra
    assert set(env) >= set(terceiros.NUCLEO_ENV) and all(env[n] == "v:" + n for n in env if n in ambiente)


def test_so_o_busca_pede_a_chave_do_tinyfish_como_extra(monkeypatch):
    from simplicio_video import busca, download, terceiros
    espia = _Espia(monkeypatch)
    download._ambiente()
    busca._ambiente_filho()
    _env_de_status(monkeypatch)
    pediram = [("TINYFISH_API_KEY" in extra) for extra, _ in espia.chamadas]
    assert pediram == [False, True, False]
    assert all(not any(("KEY" in n or "TOKEN" in n) and n != "TINYFISH_API_KEY" for n in extra) for extra, _ in espia.chamadas)
    assert terceiros.NUCLEO_ENV == ("PATH", "HOME", "LANG", "LC_ALL")


@pytest.mark.parametrize("modulo, lista", [("download", "ENV_REPASSADO"), ("busca", "ENV_REPASSADO"), ("status", "ENV_FERRAMENTA")])
def test_a_constante_publica_de_cada_modulo_e_o_nucleo_mais_o_extra_dele(modulo, lista):
    """The constants stay (the golden test and doctor_trilhas read them): the core first, then what the module has on top. download writes
    the four core names itself (importing `terceiros` there would put one more module in the `--help` of the CLI), and this is what
    keeps that copy from drifting."""
    import importlib
    from simplicio_video import terceiros
    m = importlib.import_module(f"simplicio_video.{modulo}")
    assert getattr(m, lista) == (*terceiros.NUCLEO_ENV, *m.ENV_EXTRA)


@pytest.mark.parametrize("arquivo", ["download.py", "busca.py", "status.py"])
def test_nenhuma_das_tres_monta_o_ambiente_do_filho_com_a_compreensao_de_cada_dia(arquivo):
    texto = (PKG / arquivo).read_text(encoding="utf-8")
    assert "if k in os.environ}" not in texto, "a lista fechada passa por terceiros.env_para_terceiro"
    assert "env_para_terceiro(" in texto


# ---- status: the public names ---------------------------------------------------------------------------------------------------------


def test_o_busca_tem_o_nome_publico_versao_cli_e_o_antigo_e_so_um_apelido():
    from simplicio_video import busca
    assert busca.versao_cli is busca._versao_cli
    assert "versao_cli" in busca.__all__


def test_o_status_le_a_versao_do_tinyfish_pelo_nome_publico_do_busca(monkeypatch):
    from simplicio_video import busca, status
    visto = []
    monkeypatch.setattr(busca, "versao_cli", lambda exe: visto.append(exe) or "7.7.7")
    monkeypatch.setattr(status.shutil, "which", lambda nome: "/falso/tinyfish" if nome == "tinyfish" else None)
    linha = status._ferramenta_do_motor("tinyfish")
    assert linha["version"] == "7.7.7" and visto == ["/falso/tinyfish"]


def test_o_status_le_o_commit_das_trilhas_git_pelo_git_publico_de_tools(monkeypatch, tmp_path):
    from simplicio_video import status, tools
    vistos = []
    monkeypatch.setattr(tools, "find", lambda nome: tmp_path)
    monkeypatch.setattr(tools, "git", lambda *args, cwd=None: vistos.append((args, cwd)) or "0123456789ab")
    linha = status._ferramenta_do_motor("matchcut")
    assert linha["installed"] is True and linha["version"] == "0123456789ab"
    assert vistos == [(("rev-parse", "--short=12", "HEAD"), tmp_path)]


def test_o_status_trata_o_git_que_falha_como_sem_versao(monkeypatch, tmp_path):
    from simplicio_video import status, tools

    def quebrado(*args, cwd=None):
        raise tools.ToolError("git rev-parse: fatal")

    monkeypatch.setattr(tools, "find", lambda nome: tmp_path)
    monkeypatch.setattr(tools, "git", quebrado)
    linha = status._ferramenta_do_motor("matchcut")
    assert linha["installed"] is True and linha["version"] is None


@pytest.mark.parametrize("arquivo", ["status.py", "terceiros.py"])
def test_nenhum_dos_dois_chama_o_git_privado_de_tools(arquivo):
    arvore = ast.parse((PKG / arquivo).read_text(encoding="utf-8"))
    privados = [n.lineno for n in ast.walk(arvore) if isinstance(n, ast.Attribute) and n.attr == "_git"]
    assert privados == []


# ---- `os.environ` replaced after the import: the readers look at the object that is there at the CALL --------------------------------------
# `def offline(env=os.environ)` binds the object `os.environ` had when `rede` was imported; the suite (golden, test_registro_trilhas,
# test_cli_registro) and any host that swaps `os.environ` for a dict would then not be seen. Before U07 every reader wrote
# `os.environ.get("SIMPLICIO_OFFLINE")` and saw the swap: the answers below are the ones of that code.


def _com_o_ambiente_trocado(monkeypatch, *, objeto_original: str | None, novo: dict):
    """The original `os.environ` object holds SIMPLICIO_OFFLINE=`objeto_original` (None: not there); then `os.environ` becomes `novo`."""
    if objeto_original is None:
        monkeypatch.delenv("SIMPLICIO_OFFLINE", raising=False)
    else:
        monkeypatch.setenv("SIMPLICIO_OFFLINE", objeto_original)
    base = {k: v for k, v in os.environ.items() if k != "SIMPLICIO_OFFLINE"}
    monkeypatch.setattr(os, "environ", {**base, **novo})


@pytest.mark.parametrize("leitor", NOMES_DOS_LEITORES)
def test_ambiente_trocado_para_on_vale_mesmo_que_o_objeto_original_nao_tenha_a_variavel(monkeypatch, leitor):
    """Case B: the original object has no SIMPLICIO_OFFLINE, `os.environ` is replaced by a dict that says `On `: the reader refuses, as
    it does with the variable set in the real environment."""
    chamada = _leitores()[leitor]
    monkeypatch.setenv("SIMPLICIO_OFFLINE", "1")
    esperado = _resposta(chamada)
    _com_o_ambiente_trocado(monkeypatch, objeto_original=None, novo={"SIMPLICIO_OFFLINE": "On "})
    assert _resposta(chamada) == esperado, leitor


@pytest.mark.parametrize("leitor", SEM_EFEITO_ONLINE)
def test_ambiente_trocado_para_um_dict_sem_a_variavel_libera_a_rede_mesmo_que_o_objeto_original_tenha_1(monkeypatch, leitor):
    """Case A: the original object says 1, `os.environ` is replaced by a dict without the variable: the reader answers as with the
    network free."""
    chamada = _leitores()[leitor]
    monkeypatch.setenv("SIMPLICIO_OFFLINE", "0")
    liberado = _resposta(chamada)
    _com_o_ambiente_trocado(monkeypatch, objeto_original="1", novo={})
    assert _resposta(chamada) == liberado, leitor


def test_motivo_offline_olha_o_ambiente_que_esta_la_na_hora_da_chamada(monkeypatch):
    from simplicio_video import rede
    _com_o_ambiente_trocado(monkeypatch, objeto_original="1", novo={})
    assert rede.motivo_offline("clonar o x.") is None
    _com_o_ambiente_trocado(monkeypatch, objeto_original=None, novo={"SIMPLICIO_OFFLINE": " Yes "})
    assert rede.motivo_offline("clonar o x.") == PREFIXO + "clonar o x."


def test_offline_com_o_ambiente_dado_ignora_o_do_processo(monkeypatch):
    """An explicit mapping wins over the process, and an empty one is a mapping (not "none given")."""
    from simplicio_video import rede
    monkeypatch.setenv("SIMPLICIO_OFFLINE", "1")
    assert rede.offline({}) is False
    monkeypatch.setenv("SIMPLICIO_OFFLINE", "0")
    assert rede.offline({"SIMPLICIO_OFFLINE": "on"}) is True
