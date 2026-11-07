"""U07.0, the `rede` module: ONE reading of SIMPLICIO_OFFLINE, the phrase of the offline refusal, and the HTTP client (`request`,
`NoRedirect`, `Response`, `NetworkError`) that today lives in swap_providers/http.py.

Today `SIMPLICIO_OFFLINE` is parsed in nine places and the phrase "modo offline (SIMPLICIO_OFFLINE=1): não vou ..." is written in
eight modules; the HTTP client sits in the package of the swap adapters although Openverse uses it too. This module only ADDS the
interface (the modules migrate in later waves): so the tests here pin what the copies do today, and run the same tables over
`rede` (red until it exists) and over the current implementation (green), which is how the refactor proves "same answer".

No test touches the network: urllib is replaced by fakes.
"""
from __future__ import annotations

import ast
import email.message
import importlib
import io
import json
import urllib.error
import urllib.request
from pathlib import Path

import pytest

PREFIXO = "modo offline (SIMPLICIO_OFFLINE=1): não vou "
ENV_VERDADEIRO = ["1", "true", "yes", "on", " 1 ", "TRUE", "Yes", " On ", "ON\t"]
ENV_FALSO = ["", "0", "false", "no", "off", "2", "truee", "y", "sim", "  "]


def _rede():
    return importlib.import_module("simplicio_video.rede")  # red until U07.0 adds the module


# ---- offline(): one parse for the nine places ------------------------------------------------------------------------------


@pytest.mark.parametrize("valor", ENV_VERDADEIRO)
def test_offline_aceita_os_valores_verdadeiros_sem_olhar_espaco_nem_caixa(valor):
    assert _rede().offline({"SIMPLICIO_OFFLINE": valor}) is True


@pytest.mark.parametrize("valor", ENV_FALSO)
def test_offline_recusa_o_resto(valor):
    assert _rede().offline({"SIMPLICIO_OFFLINE": valor}) is False


def test_offline_sem_a_variavel_e_falso():
    assert _rede().offline({}) is False
    assert _rede().offline({"OUTRA": "1"}) is False


def test_offline_le_o_ambiente_do_processo_na_hora_da_chamada(monkeypatch):
    rede = _rede()
    monkeypatch.setenv("SIMPLICIO_OFFLINE", "1")
    assert rede.offline() is True
    monkeypatch.setenv("SIMPLICIO_OFFLINE", "0")
    assert rede.offline() is False
    monkeypatch.delenv("SIMPLICIO_OFFLINE")
    assert rede.offline() is False
    monkeypatch.setenv("SIMPLICIO_OFFLINE", " On ")
    assert rede.offline() is True


def _offline_de(caminho: str):
    modulo, _, nome = caminho.rpartition(".")
    return getattr(importlib.import_module(modulo), nome, None)


# the copies that exist today as a function (busca, openverse and swap_providers/http parse it inline: see the request test below)
COPIAS_DE_OFFLINE = ["simplicio_video.toonflow._offline", "simplicio_video.instagram._offline", "simplicio_video.montage._offline",
                     "simplicio_video.tools_update._offline", "simplicio_video.commands.update._offline"]


@pytest.mark.parametrize("copia", COPIAS_DE_OFFLINE)
@pytest.mark.parametrize("valor", ENV_VERDADEIRO + ENV_FALSO)
def test_as_copias_de_hoje_respondem_igual_a_rede_offline(monkeypatch, copia, valor):
    """Green today (the copy), and it must stay green when the copy becomes an alias of `rede.offline`."""
    funcao = _offline_de(copia)
    assert funcao is not None, copia
    monkeypatch.setenv("SIMPLICIO_OFFLINE", valor)
    esperado = valor.strip().lower() in ("1", "true", "yes", "on")
    assert funcao() is esperado


# ---- motivo_offline(): the exact phrase ------------------------------------------------------------------------------------


def test_motivo_offline_e_a_frase_de_hoje_byte_a_byte(monkeypatch):
    rede = _rede()
    monkeypatch.setenv("SIMPLICIO_OFFLINE", "1")
    assert rede.motivo_offline("") == PREFIXO
    assert rede.motivo_offline("clonar o Toonflow.") == PREFIXO + "clonar o Toonflow."
    assert rede.motivo_offline("chamar o TinyFish. Só resultados que já estão no cache saem sem rede") == (
        "modo offline (SIMPLICIO_OFFLINE=1): não vou chamar o TinyFish. Só resultados que já estão no cache saem sem rede")


def test_motivo_offline_fora_do_modo_offline_e_none(monkeypatch):
    rede = _rede()
    monkeypatch.delenv("SIMPLICIO_OFFLINE")
    assert rede.motivo_offline("clonar o Toonflow.") is None
    monkeypatch.setenv("SIMPLICIO_OFFLINE", "0")
    assert rede.motivo_offline("clonar o Toonflow.") is None


def test_motivo_offline_segue_o_valor_da_variavel_como_offline(monkeypatch):
    rede = _rede()
    monkeypatch.setenv("SIMPLICIO_OFFLINE", " Yes ")
    assert rede.motivo_offline("x") == PREFIXO + "x"


def _clones():
    from simplicio_video import instagram, matchcut, montage, moneyprinter, rea_video, toonflow, video_to_skill
    return [("toonflow", toonflow.clone_toonflow, toonflow.ToonflowError),
            ("moneyprinter", moneyprinter.clone_moneyprinter, moneyprinter.MoneyPrinterError),
            ("matchcut", matchcut.clone_matchcut, matchcut.MatchcutError),
            ("instagram", instagram.clone_instagram, instagram.InstagramError),
            ("openmontage", montage.clone_openmontage, montage.MontageError),
            ("rea_video", rea_video.clone_rea_video, rea_video.ReaVideoError),
            ("video_to_skill", video_to_skill.clone, video_to_skill.VideoToSkillError)]


TRILHAS_COM_CLONE = ["toonflow", "moneyprinter", "matchcut", "instagram", "openmontage", "rea_video", "video_to_skill"]


@pytest.mark.parametrize("trilha", TRILHAS_COM_CLONE)
def test_a_recusa_offline_do_clone_de_cada_trilha_comeca_pela_frase_unica(monkeypatch, trilha):
    """Green today: the seven clone refusals open with the same phrase. `rede.motivo_offline` is that opening; the rest of each
    message (what to run instead) is the track's own and stays byte for byte."""
    monkeypatch.setenv("SIMPLICIO_OFFLINE", "1")
    _, clone, erro = next(c for c in _clones() if c[0] == trilha)
    with pytest.raises(erro) as caught:
        clone()
    mensagem = str(caught.value)
    assert mensagem.startswith(PREFIXO), mensagem
    assert mensagem.startswith(f"{PREFIXO}clonar o "), mensagem


RESTO_DO_TOONFLOW = ("clonar o Toonflow. Instale fora do modo offline com `simplicio-video toonflow clone` "
                     "ou aponte TOONFLOW_DIR para um checkout.")


def test_a_recusa_do_toonflow_hoje(monkeypatch):
    from simplicio_video import toonflow
    monkeypatch.setenv("SIMPLICIO_OFFLINE", "1")
    with pytest.raises(toonflow.ToonflowError) as caught:
        toonflow.clone_toonflow()
    assert str(caught.value) == f"{PREFIXO}{RESTO_DO_TOONFLOW}"


def test_motivo_offline_reproduz_a_recusa_do_toonflow_byte_a_byte(monkeypatch):
    monkeypatch.setenv("SIMPLICIO_OFFLINE", "1")
    assert _rede().motivo_offline(RESTO_DO_TOONFLOW) == f"{PREFIXO}{RESTO_DO_TOONFLOW}"


# ---- the HTTP client: the same table over swap_providers.http (today) and rede ----------------------------------------------


def _implementacoes():
    return [pytest.param("simplicio_video.swap_providers.http", id="swap_providers.http"), pytest.param("simplicio_video.rede", id="rede")]


class _Resposta:
    def __init__(self, status=200, corpo=b"", cabecalhos=None):
        self.status = status
        self.corpo = corpo
        self.headers = cabecalhos if cabecalhos is not None else {}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, n=None):
        return self.corpo if n is None else self.corpo[:n]


class _Rede:
    """urllib replaced: records each Request and the handlers of build_opener; answers with `resposta` or raises `erro`."""

    def __init__(self, monkeypatch, resposta=None, erro=None):
        self.requisicoes = []
        self.handlers = []
        self.timeouts = []
        self.resposta = resposta if resposta is not None else _Resposta()
        self.erro = erro
        monkeypatch.setattr(urllib.request, "urlopen", self._abre)
        monkeypatch.setattr(urllib.request, "build_opener", self._opener)

    def _abre(self, req, timeout=None):
        self.requisicoes.append(req)
        self.timeouts.append(timeout)
        if self.erro is not None:
            raise self.erro
        return self.resposta

    def _opener(self, *handlers):
        self.handlers.append(handlers)
        outer = self

        class Opener:
            def open(self, req, timeout=None):
                return outer._abre(req, timeout)

        return Opener()


@pytest.fixture
def rede_falsa(monkeypatch):
    monkeypatch.delenv("SIMPLICIO_OFFLINE", raising=False)
    return lambda **kw: _Rede(monkeypatch, **kw)


@pytest.mark.parametrize("caminho", _implementacoes())
def test_request_offline_recusa_sem_abrir_a_rede(monkeypatch, caminho):
    modulo = importlib.import_module(caminho)
    falsa = _Rede(monkeypatch)
    monkeypatch.setenv("SIMPLICIO_OFFLINE", "1")
    with pytest.raises(modulo.NetworkError) as caught:
        modulo.request("GET", "https://a.example/")
    assert str(caught.value) == "SIMPLICIO_OFFLINE=1: rede bloqueada"
    assert falsa.requisicoes == []


@pytest.mark.parametrize("caminho", _implementacoes())
@pytest.mark.parametrize("valor", [" On ", "TRUE", "yes"])
def test_request_offline_com_espaco_e_caixa_diferentes(monkeypatch, caminho, valor):
    modulo = importlib.import_module(caminho)
    falsa = _Rede(monkeypatch)
    monkeypatch.setenv("SIMPLICIO_OFFLINE", valor)
    with pytest.raises(modulo.NetworkError):
        modulo.request("GET", "https://a.example/")
    assert falsa.requisicoes == []


@pytest.mark.parametrize("caminho", _implementacoes())
def test_request_devolve_status_corpo_e_cabecalhos_em_minusculas(rede_falsa, caminho):
    modulo = importlib.import_module(caminho)
    falsa = rede_falsa(resposta=_Resposta(201, b'{"ok": true}', {"Retry-After": "3", "X-RateLimit-Remaining": 9}))
    r = modulo.request("POST", "https://a.example/x", timeout=7)
    assert (r.status, r.body) == (201, b'{"ok": true}')
    assert r.headers == {"retry-after": "3", "x-ratelimit-remaining": "9"}
    assert r.json() == {"ok": True}
    assert falsa.timeouts == [7] and falsa.handlers == []  # follows redirects: plain urlopen, no opener
    assert falsa.requisicoes[0].get_method() == "POST" and falsa.requisicoes[0].full_url == "https://a.example/x"


@pytest.mark.parametrize("caminho", _implementacoes())
def test_response_json_de_corpo_invalido_e_none(rede_falsa, caminho):
    modulo = importlib.import_module(caminho)
    rede_falsa(resposta=_Resposta(200, b"nao e json"))
    assert modulo.request("GET", "https://a.example/").json() is None
    rede_falsa(resposta=_Resposta(200, b"\xff\xfe"))
    assert modulo.request("GET", "https://a.example/").json() is None


@pytest.mark.parametrize("caminho", _implementacoes())
def test_request_json_body_vira_json_com_content_type_e_o_cabecalho_do_chamador_vence(rede_falsa, caminho):
    modulo = importlib.import_module(caminho)
    falsa = rede_falsa()
    modulo.request("POST", "https://a.example/", headers={"Authorization": "Bearer k"}, json_body={"a": "ç"})
    req = falsa.requisicoes[0]
    assert req.data == json.dumps({"a": "ç"}).encode("utf8")
    assert req.get_header("Content-type") == "application/json" and req.get_header("Authorization") == "Bearer k"
    modulo.request("POST", "https://a.example/", headers={"Content-Type": "text/x"}, json_body={})
    assert falsa.requisicoes[1].get_header("Content-type") == "text/x"


@pytest.mark.parametrize("caminho", _implementacoes())
def test_request_form_vira_urlencoded(rede_falsa, caminho):
    modulo = importlib.import_module(caminho)
    falsa = rede_falsa()
    modulo.request("POST", "https://a.example/token", form={"grant_type": "client_credentials", "q": "a b&c"})
    req = falsa.requisicoes[0]
    assert req.data == b"grant_type=client_credentials&q=a+b%26c"
    assert req.get_header("Content-type") == "application/x-www-form-urlencoded"


@pytest.mark.parametrize("caminho", _implementacoes())
def test_request_sem_corpo_nao_manda_dados(rede_falsa, caminho):
    modulo = importlib.import_module(caminho)
    falsa = rede_falsa()
    modulo.request("GET", "https://a.example/")
    assert falsa.requisicoes[0].data is None and not falsa.requisicoes[0].has_header("Content-type")


@pytest.mark.parametrize("caminho", _implementacoes())
def test_request_sem_seguir_redirecionamento_usa_o_handler_que_nao_segue(rede_falsa, caminho):
    modulo = importlib.import_module(caminho)
    falsa = rede_falsa(resposta=_Resposta(302, b"", {"Location": "https://b.example/"}))
    r = modulo.request("GET", "https://a.example/", follow_redirects=False)
    assert r.status == 302 and r.headers == {"location": "https://b.example/"}
    assert len(falsa.handlers) == 1 and len(falsa.handlers[0]) == 1
    handler = falsa.handlers[0][0]
    assert issubclass(handler, urllib.request.HTTPRedirectHandler)
    assert handler is getattr(modulo, "NoRedirect", None) or handler is getattr(modulo, "_NoRedirect", None)


@pytest.mark.parametrize("caminho", _implementacoes())
def test_o_handler_de_redirecionamento_recusa_seguir(caminho):
    modulo = importlib.import_module(caminho)
    handler = getattr(modulo, "NoRedirect", None) or modulo._NoRedirect
    req = urllib.request.Request("https://a.example/")
    assert handler().redirect_request(req, None, 302, "Found", {}, "https://b.example/") is None


@pytest.mark.parametrize("caminho", _implementacoes())
def test_request_http_error_vira_response_com_o_corpo_do_erro(rede_falsa, caminho):
    modulo = importlib.import_module(caminho)
    cabecalhos = email.message.Message()
    cabecalhos["Retry-After"] = "9"
    erro = urllib.error.HTTPError("https://a.example/", 429, "Too Many", cabecalhos, io.BytesIO(b"devagar"))
    rede_falsa(erro=erro)
    r = modulo.request("GET", "https://a.example/")
    assert (r.status, r.body, r.headers) == (429, b"devagar", {"retry-after": "9"})


@pytest.mark.parametrize("caminho", _implementacoes())
def test_request_http_error_respeita_max_bytes_no_corpo(rede_falsa, caminho):
    modulo = importlib.import_module(caminho)
    erro = urllib.error.HTTPError("https://a.example/", 500, "x", email.message.Message(), io.BytesIO(b"0123456789"))
    rede_falsa(erro=erro)
    assert modulo.request("GET", "https://a.example/", max_bytes=4).body == b"0123"


@pytest.mark.parametrize("caminho", _implementacoes())
@pytest.mark.parametrize("falha", [urllib.error.URLError("dns"), TimeoutError("lento"), OSError("reset")])
def test_request_falha_de_rede_diz_so_o_tipo_da_excecao(rede_falsa, caminho, falha):
    modulo = importlib.import_module(caminho)
    rede_falsa(erro=falha)
    with pytest.raises(modulo.NetworkError) as caught:
        modulo.request("GET", "https://a.example/", headers={"Authorization": "Bearer segredo"})
    assert str(caught.value) == f"falha de rede: {type(falha).__name__}"
    assert "segredo" not in str(caught.value) and caught.value.__cause__ is None


@pytest.mark.parametrize("caminho", _implementacoes())
def test_request_com_max_bytes_recusa_o_corpo_maior(rede_falsa, caminho):
    modulo = importlib.import_module(caminho)
    rede_falsa(resposta=_Resposta(200, b"x" * 11))
    with pytest.raises(modulo.NetworkError) as caught:
        modulo.request("GET", "https://a.example/", max_bytes=10)
    assert str(caught.value) == "resposta acima de 10 bytes"
    assert modulo.request("GET", "https://a.example/", max_bytes=11).body == b"x" * 11


@pytest.mark.parametrize("caminho", _implementacoes())
def test_response_tem_os_campos_de_hoje(caminho):
    modulo = importlib.import_module(caminho)
    r = modulo.Response(200, b"{}")
    assert r.headers == {} and r.json() == {}
    assert issubclass(modulo.NetworkError, Exception)


def test_rede_nao_importa_nada_do_pacote_nem_de_fora_da_biblioteca_padrao():
    """`rede` is a leaf: only the standard library (the swap adapters and Openverse will import it, never the other way round)."""
    fonte = (Path(_rede().__file__)).read_text(encoding="utf-8")
    raizes = set()
    for no in ast.walk(ast.parse(fonte)):
        if isinstance(no, ast.Import):
            raizes.update(a.name.split(".")[0] for a in no.names)
        elif isinstance(no, ast.ImportFrom):
            assert no.level == 0, f"import relativo: {ast.dump(no)}"
            raizes.add((no.module or "").split(".")[0])
    import sys
    assert raizes <= set(sys.stdlib_module_names) | {"__future__"}, raizes
