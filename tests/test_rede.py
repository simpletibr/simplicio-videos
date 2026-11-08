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
import base64
import email.message
import importlib
import io
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
import urllib.response
from pathlib import Path

import pytest

from helpers import ROOT

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


def test_prefixo_offline_e_a_abertura_da_frase_e_nao_depende_do_ambiente(monkeypatch):
    """The opening is a constant: a caller that has its own `_offline` (tests replace it) can build the refusal without asking the
    environment, and `motivo_offline` is that opening plus the action."""
    rede = _rede()
    monkeypatch.delenv("SIMPLICIO_OFFLINE")
    assert rede.PREFIXO_OFFLINE == PREFIXO
    monkeypatch.setenv("SIMPLICIO_OFFLINE", "1")
    assert rede.motivo_offline("clonar o x.") == rede.PREFIXO_OFFLINE + "clonar o x."


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
    assert falsa.timeouts == [7]
    # follows redirects: an opener whose redirect handler drops the credentials (until U22g it was plain urlopen, no opener)
    assert len(falsa.handlers) == 1 and len(falsa.handlers[0]) == 1
    assert falsa.handlers[0][0] is modulo.StripCredentialsRedirect
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
    assert handler is modulo.NoRedirect


@pytest.mark.parametrize("caminho", _implementacoes())
def test_o_handler_de_redirecionamento_recusa_seguir(caminho):
    modulo = importlib.import_module(caminho)
    handler = modulo.NoRedirect
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


# ---- U07b: `rede` loads urllib when a request is made, not when the module is imported ---------------------------------------------
#
# `import simplicio_video.instagram` (the module that runs third-party scripts in isolation, and whose documented rule is "does not import
# the network") reached `rede` through `trilha_base` and loaded 13 modules of the network stack (socket, ssl, http.client, urllib.*,
# email.*) because `rede` imported urllib at the top. `rede` now imports urllib inside `request`, and builds `NoRedirect` (a subclass of
# urllib's redirect handler) on first access by a module-level `__getattr__` (PEP 562), cached so that every access is the same object.
#
# These tests run a CLEAN interpreter (`python -I`, so no PYTHONPATH, no user site, no sitecustomize): what a process has loaded is the
# only honest measure of "does not import the network". The loopback servers listen on 127.0.0.1 and the child refuses to connect
# anywhere else; no test touches the real network.

PILHA_DE_REDE = {"socket", "_socket", "ssl", "_ssl", "http", "urllib", "email", "asyncio", "urllib3", "requests", "httpx", "aiohttp"}
# top-level names. `selectors` is not here: it is the poll loop of `subprocess`, which the tracks need, not a way to the network.

_PRELUDIO = "import sys\nsys.path.insert(0, %r)\n" % str(ROOT / "src")

_SO_LOOPBACK = """
import socket
_connect = socket.socket.connect


def _so_loopback(self, endereco):
    if not (isinstance(endereco, tuple) and endereco[0] in ("127.0.0.1", "::1")):
        raise AssertionError(f"fora do loopback: {endereco!r}")
    return _connect(self, endereco)


socket.socket.connect = _so_loopback
"""

_SERVIDORES = """
import http.server
import json
import threading


def servidor(rotas):
    \"\"\"A loopback server on a free port. `rotas` maps a path to (status, headers, body). Returns (base url, what it was asked).\"\"\"
    pedidos = []

    class Atende(http.server.BaseHTTPRequestHandler):
        def _responde(self):
            tamanho = int(self.headers.get("Content-Length") or 0)
            pedidos.append({"metodo": self.command, "caminho": self.path, "autorizacao": self.headers.get("Authorization"),
                            "tipo": self.headers.get("Content-Type"), "corpo": (self.rfile.read(tamanho) if tamanho else b"").decode("utf8")})
            status, cabecalhos, corpo = rotas[self.path]
            self.send_response(status)
            for nome, valor in cabecalhos.items():
                self.send_header(nome, valor)
            self.send_header("Content-Length", str(len(corpo)))
            self.end_headers()
            self.wfile.write(corpo)

        do_GET = do_POST = _responde

        def log_message(self, *args):
            pass

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Atende)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{srv.server_address[1]}", pedidos
"""


def _processo_limpo(codigo: str) -> dict:
    """Run `codigo` in `python -I` with a minimal environment (no proxy variable, no SIMPLICIO_OFFLINE); it prints one JSON object."""
    env = {k: os.environ[k] for k in ("PATH", "SYSTEMROOT", "TEMP", "TMP", "TMPDIR", "HOME", "LANG", "LC_ALL") if k in os.environ}
    r = subprocess.run([sys.executable, "-I", "-c", codigo], capture_output=True, text=True, env=env, timeout=120)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout.strip().splitlines()[-1])


def _carga_de(modulo: str) -> list[str]:
    """The modules of the network stack that `import <modulo>` loads in a clean interpreter, beyond what `pathlib` brings (before
    Python 3.13 `pathlib` itself loads urllib.parse, which is a string parser, not the network)."""
    carregados = _processo_limpo(_PRELUDIO + "import json\nimport pathlib\nantes = set(sys.modules)\n" + f"import {modulo}\n"
                                 + "print(json.dumps(sorted(set(sys.modules) - antes)))\n")
    return sorted(m for m in carregados if m.split(".")[0] in PILHA_DE_REDE)


@pytest.mark.parametrize("modulo", ["simplicio_video.rede", "simplicio_video.trilha_base"])
def test_importar_rede_ou_quem_so_depende_dela_nao_carrega_a_pilha_de_rede(modulo):
    """Red before U07b: `rede` imported urllib at the top, so every module that imports `rede` loaded socket, ssl, http.client..."""
    assert _carga_de(modulo) == []


def test_request_do_zero_importa_o_urllib_so_na_chamada_e_funciona_contra_um_servidor_de_loopback():
    codigo = _PRELUDIO + _SO_LOOPBACK + """
import os
from simplicio_video import rede
v = {"urllib_ao_importar": "urllib.request" in sys.modules}
os.environ["SIMPLICIO_OFFLINE"] = "1"
try:
    rede.request("GET", "http://127.0.0.1:9/")
except rede.NetworkError as e:
    v["offline"] = str(e)
v["urllib_depois_de_recusar_offline"] = "urllib.request" in sys.modules
os.environ.pop("SIMPLICIO_OFFLINE")
""" + _SERVIDORES + """
base, pedidos = servidor({"/ok": (200, {"Retry-After": "3"}, b'{"ok": true}'), "/nada": (404, {"X-Erro": "1"}, b"nada aqui"),
                          "/grande": (200, {}, b"x" * 50), "/eco": (200, {}, b"{}")})
r = rede.request("GET", base + "/ok", headers={"Authorization": "Bearer k"}, timeout=10)
v["get"] = [r.status, r.body.decode(), r.headers["retry-after"], r.json(), pedidos[0]["autorizacao"]]
rede.request("POST", base + "/eco", json_body={"a": "ç"})
v["json"] = [pedidos[1]["metodo"], pedidos[1]["tipo"], pedidos[1]["corpo"]]
rede.request("POST", base + "/eco", form={"grant_type": "client_credentials", "q": "a b&c"})
v["form"] = [pedidos[2]["tipo"], pedidos[2]["corpo"]]
r = rede.request("GET", base + "/nada")
v["http_error"] = [r.status, r.body.decode(), r.headers["x-erro"]]
v["max_bytes"] = [len(rede.request("GET", base + "/grande", max_bytes=50).body)]
try:
    rede.request("GET", base + "/grande", max_bytes=10)
except rede.NetworkError as e:
    v["max_bytes"].append(str(e))
import socket
livre = socket.socket()
livre.bind(("127.0.0.1", 0))
porta = livre.getsockname()[1]
livre.close()
try:
    rede.request("GET", f"http://127.0.0.1:{porta}/")
except rede.NetworkError as e:
    v["recusada"] = [str(e), e.__cause__]
v["urllib_depois_da_chamada"] = "urllib.request" in sys.modules
print(json.dumps(v))
"""
    v = _processo_limpo(codigo)
    assert v["urllib_ao_importar"] is False
    assert v["offline"] == "SIMPLICIO_OFFLINE=1: rede bloqueada" and v["urllib_depois_de_recusar_offline"] is False
    assert v["get"] == [200, '{"ok": true}', "3", {"ok": True}, "Bearer k"]
    assert v["json"] == ["POST", "application/json", json.dumps({"a": "ç"})]
    assert v["form"] == ["application/x-www-form-urlencoded", "grant_type=client_credentials&q=a+b%26c"]
    assert v["http_error"] == [404, "nada aqui", "1"]
    assert v["max_bytes"] == [50, "resposta acima de 10 bytes"]
    assert v["recusada"] == ["falha de rede: URLError", None]
    assert v["urllib_depois_da_chamada"] is True


def test_sem_seguir_redirecionamento_o_segundo_host_nao_recebe_nenhum_acesso():
    """Two loopback servers (two origins): the first answers 302 to the second. With `follow_redirects=False` the second is never
    asked; with the default it is asked once, which shows the servers do redirect. The handler `request` used is `rede.NoRedirect`,
    even though nothing had read that name before the call (it is built on first use, by `request` or by the attribute: one class)."""
    codigo = _PRELUDIO + _SO_LOOPBACK + _SERVIDORES + """
import urllib.request
from simplicio_video import rede
usados = []
construir = urllib.request.build_opener
urllib.request.build_opener = lambda *handlers: (usados.extend(handlers), construir(*handlers))[1]
outro, pedidos_do_outro = servidor({"/chegou": (200, {}, b"cheguei")})
primeiro, pedidos_do_primeiro = servidor({"/vai": (302, {"Location": outro + "/chegou"}, b"")})
v = {}
r = rede.request("GET", primeiro + "/vai", headers={"Authorization": "Bearer segredo"}, follow_redirects=False)
v["sem_seguir"] = [r.status, r.headers["location"] == outro + "/chegou", len(pedidos_do_primeiro), len(pedidos_do_outro)]
v["handler_e_o_publico"] = len(usados) == 1 and usados[0] is rede.NoRedirect
r = rede.request("GET", primeiro + "/vai")
v["seguindo"] = [r.status, r.body.decode(), len(pedidos_do_outro)]
print(json.dumps(v))
"""
    v = _processo_limpo(codigo)
    assert v["sem_seguir"] == [302, True, 1, 0]
    assert v["handler_e_o_publico"] is True
    assert v["seguindo"] == [200, "cheguei", 1]


def test_no_redirect_e_o_mesmo_objeto_em_todo_acesso_e_so_carrega_o_urllib_quando_pedido():
    codigo = _PRELUDIO + """
import json
from simplicio_video import rede
v = {"urllib_ao_importar": "urllib.request" in sys.modules,
     "dir_antes": sorted({"request", "Response", "NetworkError", "NoRedirect", "offline", "motivo_offline", "PREFIXO_OFFLINE"} - set(dir(rede)))}
primeira = rede.NoRedirect
v["urllib_depois_do_acesso"] = "urllib.request" in sys.modules
v["mesma"] = primeira is rede.NoRedirect is getattr(rede, "NoRedirect") is vars(rede)["NoRedirect"]
from simplicio_video.rede import NoRedirect
v["from_import"] = NoRedirect is primeira
v["nomes"] = [primeira.__name__, primeira.__qualname__, primeira.__module__]
v["doc"] = primeira.__doc__
import urllib.request
v["e_handler_do_urllib"] = issubclass(primeira, urllib.request.HTTPRedirectHandler)
v["recusa"] = primeira().redirect_request(urllib.request.Request("http://a.example/"), None, 302, "Found", {}, "http://b.example/") is None
v["dir_depois"] = "NoRedirect" in dir(rede)
v["inexistente"] = [hasattr(rede, "nao_existe"), getattr(rede, "nao_existe", "padrao")]
try:
    rede.nao_existe
except AttributeError as e:
    v["erro"] = str(e)
print(json.dumps(v))
"""
    v = _processo_limpo(codigo)
    assert v["urllib_ao_importar"] is False and v["dir_antes"] == []
    assert v["urllib_depois_do_acesso"] is True
    assert v["mesma"] is True and v["from_import"] is True
    assert v["nomes"] == ["NoRedirect", "NoRedirect", "simplicio_video.rede"]
    assert "Never follow a redirect" in v["doc"]
    assert v["e_handler_do_urllib"] is True and v["recusa"] is True and v["dir_depois"] is True
    assert v["inexistente"] == [False, "padrao"]
    assert v["erro"] == "module 'simplicio_video.rede' has no attribute 'nao_existe'"


def test_no_redirect_e_um_so_objeto_mesmo_com_varias_threads_no_primeiro_acesso():
    """The first access can come from several threads at once (aio.py runs one thread per blocking call): they all get ONE class."""
    codigo = _PRELUDIO + """
import json
import threading
from simplicio_video import rede
sys.setswitchinterval(1e-6)
divergiu = 0
for rodada in range(200):
    rede.__dict__.pop("NoRedirect", None)  # as if it had never been read
    largada = threading.Barrier(8)
    vistos = []

    def acessa():
        largada.wait()
        vistos.append(rede.NoRedirect)

    threads = [threading.Thread(target=acessa) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    divergiu += len({id(c) for c in vistos}) != 1 or vistos[0] is not rede.NoRedirect
print(json.dumps({"divergiu": divergiu}))
"""
    assert _processo_limpo(codigo) == {"divergiu": 0}


# ---- U22g: following a redirect never takes a credential to another host, or to a weaker scheme ----------------------------------------
#
# urllib copies every header of a request into the one it sends after a 3xx. `request` followed redirects with the stock opener, so an
# `Authorization`, an `x-goog-api-key`... went to whatever host a server named in `Location`, and an https call could go on over plain
# http with the key. It follows them with `rede.StripCredentialsRedirect` now: the redirect rules of urllib's own handler (which codes,
# which methods, the body, the hop limit) untouched, and the credential headers dropped from the new request unless it has the same
# netloc and the same scheme (or the scheme goes from http to https). tests/golden/test_redirect_credenciais.py runs it for real against
# two loopback servers; the tests below pin the rules without a socket: on the handler itself, and through `request` over a REAL opener
# (the stock error processor, `http_error_30x`, `urljoin` and the hop limit all run; only the connection is a fake).

_CREDENCIAIS_DO_MOTOR = {"Authorization": "Bearer S3CR3T-a", "x-goog-api-key": "AIzaS3CR3T-b", "x-api-key": "S3CR3T-c",
                         "Proxy-Authorization": "Basic S3CR3T-d", "Cookie": "s=S3CR3T-e"}
_COMUNS = {"Accept": "application/json", "User-Agent": "u22g/1", "X-Trace-Id": "t-1"}
_CABECALHOS = {**_CREDENCIAIS_DO_MOTOR, **_COMUNS}
_CREDENCIAIS_EM_MINUSCULAS = {nome.lower() for nome in _CREDENCIAIS_DO_MOTOR}
_COMUNS_EM_MINUSCULAS = {nome.lower() for nome in _COMUNS}
_CABECALHOS_EM_MINUSCULAS = {nome.lower() for nome in _CABECALHOS}


def _segue():
    """`rede.StripCredentialsRedirect` (red until the class exists)."""
    return _rede().StripCredentialsRedirect


class _Salto(urllib.request.BaseHandler):
    """A fake network for a REAL opener: answers each URL from `roteiro` (url -> (status, Location or None); a URL it does not list answers
    200 "ok") and writes down, for each request it is sent, the URL and the headers (lowercase names)."""

    handler_order = 100  # before the stock http/https handlers (500), which are not even in the opener `salto` builds

    def __init__(self, roteiro):
        self.roteiro = roteiro
        self.pedidos = []

    def _abre(self, req):
        self.pedidos.append((req.full_url, {nome.lower(): valor for nome, valor in req.header_items()}))
        status, local = self.roteiro.get(req.full_url, (200, None))
        cabecalhos = email.message.Message()
        if local:
            cabecalhos["Location"] = local
        resposta = urllib.response.addinfourl(io.BytesIO(b"ok"), cabecalhos, req.full_url, status)
        resposta.msg = "fake"
        return resposta

    http_open = https_open = _abre


@pytest.fixture
def salto(monkeypatch):
    """`rede.request` over a fake network: whichever way it reaches urllib (`build_opener`, or `urlopen` as it did before U22g) it ends in
    the same fake, under a REAL opener (the stock error processor and the redirect handler `request` asks for)."""
    monkeypatch.delenv("SIMPLICIO_OFFLINE", raising=False)

    def instala(roteiro):
        falsa = _Salto(roteiro)

        def montar(*handlers):
            opener = urllib.request.OpenerDirector()
            for handler in (urllib.request.HTTPDefaultErrorHandler, urllib.request.HTTPErrorProcessor, *handlers):
                opener.add_handler(handler() if isinstance(handler, type) else handler)
            opener.add_handler(falsa)
            return opener

        monkeypatch.setattr(urllib.request, "build_opener", montar)
        monkeypatch.setattr(urllib.request, "urlopen",
                            lambda req, timeout=None: montar(urllib.request.HTTPRedirectHandler).open(req, timeout=timeout))
        return falsa

    return instala


# (what changes, URL of the request, `Location` of the 3xx, do the credentials go on to the next hop?)
ORIGENS = [
    ("mesmo netloc, https", "https://api.example/a", "https://api.example/b", True),
    ("mesmo netloc, http", "http://api.example/a", "http://api.example/b", True),
    ("mesmo netloc com porta", "https://api.example:8443/a", "https://api.example:8443/b", True),
    ("Location relativo", "https://api.example/dir/a", "/b", True),
    ("Location relativo ao diretorio", "https://api.example/dir/a", "b", True),
    ("so a consulta e o fragmento mudam", "https://api.example/a?x=1", "https://api.example/a?x=2#f", True),
    ("host com outra caixa", "https://api.example/a", "https://API.Example/b", True),
    ("http para https no mesmo netloc: o esquema sobe, nao e downgrade", "http://api.example/a", "https://api.example/b", True),
    ("outro host", "https://api.example/a", "https://evil.example/b", False),
    ("subdominio", "https://api.example/a", "https://x.api.example/b", False),
    ("dominio pai", "https://api.example/a", "https://example/b", False),
    ("host que so comeca igual", "https://api.example/a", "https://api.example.evil.example/b", False),
    ("outra porta no mesmo host", "https://api.example:8443/a", "https://api.example:9443/b", False),
    ("porta padrao escrita (netloc diferente: na duvida, tira)", "https://api.example/a", "https://api.example:443/b", False),
    ("porta que some", "https://api.example:8443/a", "https://api.example/b", False),
    ("https para http, mesmo host", "https://api.example/a", "http://api.example/b", False),
    ("https para http, mesmo host e porta", "https://api.example:8443/a", "http://api.example:8443/b", False),
    ("https para http, outro host", "https://api.example/a", "http://evil.example/b", False),
    ("usuario no destino (https://dono@outro)", "https://api.example/a", "https://api.example@evil.example/b", False),
    ("barra invertida antes do @ (urlsplit le o host depois dele)", "https://api.example/a", "https://evil.example\\@api.example/b", False),
    ("destino relativo ao esquema", "https://api.example/a", "//evil.example/b", False),
    ("http para outro host", "http://api.example/a", "http://evil.example/b", False),
    ("http para outro host em https", "http://api.example/a", "https://evil.example/b", False),
]


@pytest.mark.parametrize("porque,velha,local,leva", ORIGENS, ids=[o[0] for o in ORIGENS])
def test_the_credentials_go_on_to_the_next_hop_only_while_the_origin_is_the_same(salto, porque, velha, local, leva):
    """Through `request` and a REAL opener: the credential headers reach the next hop when its netloc and scheme are the ones the caller
    chose (or the scheme goes from http to https), and never otherwise; the headers that are not a credential go everywhere."""
    falsa = salto({velha: (302, local)})
    r = _rede().request("GET", velha, headers=_CABECALHOS)
    assert r.status == 200 and r.body == b"ok"
    assert len(falsa.pedidos) == 2, falsa.pedidos
    (_, primeiro), (destino, segundo) = falsa.pedidos
    assert _CABECALHOS_EM_MINUSCULAS <= set(primeiro)
    levados = {nome for nome in _CREDENCIAIS_EM_MINUSCULAS if nome in segundo}
    assert levados == (_CREDENCIAIS_EM_MINUSCULAS if leva else set()), f"{destino} recebeu {sorted(levados)}"
    assert _COMUNS_EM_MINUSCULAS <= set(segundo) and all(segundo[n.lower()] == v for n, v in _COMUNS.items())


def test_a_chain_drops_the_credentials_at_the_hop_out_and_never_gives_them_back(salto):
    """api -> api -> evil -> api: the second hop (same netloc) still has them; the third (another host) has none, and neither has the
    fourth, which is back at the host that had them first: what was dropped is not in the request urllib builds from there on."""
    a, b, fora, volta = "https://api.example/a", "https://api.example/b", "https://evil.example/c", "https://api.example/d"
    falsa = salto({a: (302, b), b: (307, fora), fora: (301, volta)})
    r = _rede().request("GET", a, headers=_CABECALHOS)
    assert r.status == 200
    assert [url for url, _ in falsa.pedidos] == [a, b, fora, volta]
    levados = [sorted(nome for nome in _CREDENCIAIS_EM_MINUSCULAS if nome in cabecalhos) for _, cabecalhos in falsa.pedidos]
    assert levados == [sorted(_CREDENCIAIS_EM_MINUSCULAS), sorted(_CREDENCIAIS_EM_MINUSCULAS), [], []]


def test_a_redirect_loop_ends_where_urllib_ends_it(salto):
    """The limits (10 hops, 4 visits of one URL) are the ones of urllib's handler: this one only changes the headers."""
    a, b = "https://api.example/a", "https://api.example/b"
    de_urllib = salto({a: (302, b), b: (302, a)})  # the stock handler, over the same fake network, is the measure
    stock = urllib.request.OpenerDirector()
    for handler in (urllib.request.HTTPDefaultErrorHandler(), urllib.request.HTTPErrorProcessor(), urllib.request.HTTPRedirectHandler(), de_urllib):
        stock.add_handler(handler)
    with pytest.raises(urllib.error.HTTPError) as caught:
        stock.open(urllib.request.Request(a))
    assert caught.value.code == 302
    medido = [url for url, _ in de_urllib.pedidos]
    da_rede = salto({a: (302, b), b: (302, a)})
    assert _rede().request("GET", a).status == 302  # the HTTPError of the loop, returned as a Response like every other status
    assert [url for url, _ in da_rede.pedidos] == medido and len(medido) > 4


# ---- the handler itself, with no opener ------------------------------------------------------------------------------------------


def _redireciona(handler, velha, nova, *, metodo="GET", codigo=302, headers=None, data=None):
    req = urllib.request.Request(velha, data=data, method=metodo, headers=_CABECALHOS if headers is None else headers)
    return handler().redirect_request(req, io.BytesIO(b""), codigo, "Found", {}, nova)


def _como_o_urllib(handler, velha, nova, metodo, codigo, data):
    """What `redirect_request` of `handler` gives for this request, as plain values (or the code of the HTTPError it raises)."""
    try:
        novo = _redireciona(handler, velha, nova, metodo=metodo, codigo=codigo, data=data)
    except urllib.error.HTTPError as erro:
        return ("HTTPError", erro.code)
    return (novo.get_method(), novo.full_url, novo.data, novo.origin_req_host, novo.unverifiable, {k.lower(): v for k, v in novo.headers.items()})


@pytest.mark.parametrize("destino", ["https://api.example/b", "https://evil.example/b"], ids=["mesmo-netloc", "outro-host"])
@pytest.mark.parametrize("codigo", [301, 302, 303, 307, 308])
@pytest.mark.parametrize("metodo", ["GET", "HEAD", "POST", "PUT", "DELETE", "PATCH"])
def test_the_method_the_body_and_the_codes_are_what_urllib_does(metodo, codigo, destino):
    """For every method and code: the same new request as the stock handler (method, URL, body, origin, headers) or the same HTTPError;
    when the host changes, the only difference is the credential headers."""
    dados = None if metodo in ("GET", "HEAD") else b'{"a": 1}'
    esperado = _como_o_urllib(urllib.request.HTTPRedirectHandler, "https://api.example/a", destino, metodo, codigo, dados)
    obtido = _como_o_urllib(_segue(), "https://api.example/a", destino, metodo, codigo, dados)
    if esperado[0] != "HTTPError" and "evil" in destino:
        esperado = (*esperado[:-1], {k: v for k, v in esperado[-1].items() if k not in _CREDENCIAIS_EM_MINUSCULAS})
    assert obtido == esperado


def test_the_handler_follows_unlike_no_redirect():
    """`NoRedirect` answers None (no new request); this one gives the new request."""
    novo = _redireciona(_segue(), "https://a.example/", "https://b.example/x")
    assert novo is not None and novo.full_url == "https://b.example/x"
    assert issubclass(_segue(), urllib.request.HTTPRedirectHandler) and not issubclass(_segue(), _rede().NoRedirect)


# the names that carry a credential (the ones the callers of `request` send, and the generic shapes: any name with the word key, token,
# secret, password, auth, authorization or cookie in it) and the names that do not
NOMES_DE_CREDENCIAL = [
    "Authorization", "authorization", "AUTHORIZATION", "Proxy-Authorization", "Cookie", "Cookie2", "x-goog-api-key", "X-Goog-Api-Key",
    "x-api-key", "xi-api-key", "api-key", "x_api_key", "apikey", "X-Auth-Token", "X-Access-Token", "Private-Token",
    "Ocp-Apim-Subscription-Key", "X-Amz-Security-Token", "X-Client-Secret", "X-Password", "X-Passwd", "X-Authentication", "X-Auth",
    "X-Credential", "X-Credentials",
]
NOMES_QUE_FICAM = [
    "Accept", "Accept-Language", "Accept-Encoding", "User-Agent", "X-Trace-Id", "X-Request-Id", "X-DashScope-Async",
    "X-OmniVoice-Client-Id", "If-None-Match", "Range", "Cache-Control", "Keep-Alive", "Referer", "X-Monkey-Business",
]


@pytest.mark.parametrize("nome", NOMES_DE_CREDENCIAL)
def test_a_credential_header_is_dropped_when_the_host_changes_and_kept_when_it_does_not(nome):
    cabecalhos = {nome: "S3CR3T", "Accept": "application/json"}
    fora = _redireciona(_segue(), "https://api.example/a", "https://evil.example/b", headers=cabecalhos)
    dentro = _redireciona(_segue(), "https://api.example/a", "https://api.example/b", headers=cabecalhos)
    assert nome.capitalize() not in fora.headers and fora.headers == {"Accept": "application/json"}
    assert dentro.headers == {nome.capitalize(): "S3CR3T", "Accept": "application/json"}


@pytest.mark.parametrize("nome", NOMES_QUE_FICAM)
def test_a_header_that_is_not_a_credential_goes_to_the_other_host(nome):
    fora = _redireciona(_segue(), "https://api.example/a", "https://evil.example/b", headers={nome: "v"})
    assert fora.headers == {nome.capitalize(): "v"}


@pytest.mark.parametrize("velha,tipo", [("https://api.example/a", "https"), ("http://api.example/a", "http")])
def test_the_origin_is_read_from_the_url_not_from_the_host_a_proxy_put_on_the_request(velha, tipo):
    """urllib's ProxyHandler rewrites the request in place (`set_proxy`: its `host` becomes the proxy's); the netloc to compare is the one
    of the URL the caller asked for, so a same-host redirect keeps the credentials behind a proxy too, and another host still loses them."""
    for destino, leva in ((velha.rsplit("/", 1)[0] + "/b", True), ("https://evil.example/b", False)):
        req = urllib.request.Request(velha, headers=_CABECALHOS)
        req.set_proxy("proxy.example:3128", tipo)
        novo = _segue()().redirect_request(req, io.BytesIO(b""), 302, "Found", {}, destino)
        assert (set(_CREDENCIAIS_EM_MINUSCULAS) <= {n.lower() for n in novo.headers}) is leva, destino
        assert not leva or {n.lower() for n in novo.headers} == _CABECALHOS_EM_MINUSCULAS


@pytest.mark.parametrize("velha", ["https://api.example/a", "http://api.example/a"])
def test_a_redirect_to_ftp_loses_the_credentials(velha):
    novo = _redireciona(_segue(), velha, "ftp://api.example/b")
    assert {n.lower() for n in novo.headers} == _COMUNS_EM_MINUSCULAS


def test_a_url_the_parser_cannot_read_counts_as_another_origin():
    """`https://[::1/b` has an IPv6 bracket that never closes: urlsplit refuses it, and the redirect gets no benefit of the doubt."""
    novo = _redireciona(_segue(), "https://api.example/a", "https://[::1/b")
    assert {n.lower() for n in novo.headers} == _COMUNS_EM_MINUSCULAS


# ---- built on first use, like NoRedirect -----------------------------------------------------------------------------------------


def test_the_handler_is_built_on_first_access_and_is_one_object_for_every_access():
    codigo = _PRELUDIO + """
import json
from simplicio_video import rede
v = {"urllib_ao_importar": "urllib.request" in sys.modules, "dir_antes": "StripCredentialsRedirect" in dir(rede),
     "no_dict_antes": "StripCredentialsRedirect" in vars(rede)}
primeira = rede.StripCredentialsRedirect
v["urllib_depois_do_acesso"] = "urllib.request" in sys.modules
v["mesma"] = primeira is rede.StripCredentialsRedirect is getattr(rede, "StripCredentialsRedirect") is vars(rede)["StripCredentialsRedirect"]
from simplicio_video.rede import StripCredentialsRedirect
v["from_import"] = StripCredentialsRedirect is primeira
v["nomes"] = [primeira.__name__, primeira.__qualname__, primeira.__module__]
import urllib.request
v["e_handler_do_urllib"] = issubclass(primeira, urllib.request.HTTPRedirectHandler)
v["outra_que_a_no_redirect"] = primeira is not rede.NoRedirect and not issubclass(primeira, rede.NoRedirect)
v["dir_depois"] = "StripCredentialsRedirect" in dir(rede)
print(json.dumps(v))
"""
    v = _processo_limpo(codigo)
    assert v["urllib_ao_importar"] is False and v["urllib_depois_do_acesso"] is True
    assert v["dir_antes"] is True and v["no_dict_antes"] is False and v["dir_depois"] is True
    assert v["mesma"] is True and v["from_import"] is True
    assert v["nomes"] == ["StripCredentialsRedirect", "StripCredentialsRedirect", "simplicio_video.rede"]
    assert v["e_handler_do_urllib"] is True and v["outra_que_a_no_redirect"] is True


def test_the_handler_is_one_class_even_with_several_threads_on_the_first_access():
    codigo = _PRELUDIO + """
import json
import threading
from simplicio_video import rede
sys.setswitchinterval(1e-6)
divergiu = 0
for rodada in range(200):
    rede.__dict__.pop("StripCredentialsRedirect", None)  # as if it had never been read
    largada = threading.Barrier(8)
    vistos = []

    def acessa():
        largada.wait()
        vistos.append(rede.StripCredentialsRedirect)

    threads = [threading.Thread(target=acessa) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    divergiu += len({id(c) for c in vistos}) != 1 or vistos[0] is not rede.StripCredentialsRedirect
print(json.dumps({"divergiu": divergiu}))
"""
    assert _processo_limpo(codigo) == {"divergiu": 0}


# ---- U22i: `urlopen_seguro`, and the callers that open a URL themselves -----------------------------------------------------------------
#
# voice (Gemini TTS), voice_clone (VoiceStudio TTS) and voicestudio (`default_transport`: every call to the app) call urllib directly and keep
# their own errors, so they never went through `request`: they kept the stock redirect handler that U22g took out of it, and the key in their
# header went to whatever host a `Location` named. They open the URL with `rede.urlopen_seguro` now: `urlopen` with the same redirect handler
# as `request`, and nothing else (no NetworkError, no offline check, no reading of the body: each module still says its errors its own way).
# tests/golden/test_redirect_credenciais.py runs the three modules for real against two loopback servers; the tests below pin the opener, the
# request and the list of the places that open a URL, without a socket.


def test_urlopen_seguro_opens_the_request_with_the_handler_that_drops_the_credential(rede_falsa):
    """RED before U22i (the function does not exist): the one opener it builds has `StripCredentialsRedirect` as its redirect handler."""
    falsa = rede_falsa(resposta=_Resposta(200, b"ok"))
    req = urllib.request.Request("https://a.example/x", data=b"{}", method="POST", headers={"x-goog-api-key": "S3CR3T"})
    r = _rede().urlopen_seguro(req, timeout=7)
    assert r is falsa.resposta and falsa.requisicoes == [req] and falsa.timeouts == [7]
    assert falsa.handlers == [(_rede().StripCredentialsRedirect,)]


@pytest.mark.parametrize("erro", [urllib.error.HTTPError("https://a.example/", 429, "Too Many", email.message.Message(), io.BytesIO(b"devagar")),
                                  urllib.error.URLError("dns"), TimeoutError("lento"), ConnectionResetError("reset"), OSError("disco")],
                         ids=["HTTPError", "URLError", "TimeoutError", "ConnectionResetError", "OSError"])
def test_urlopen_seguro_lets_every_error_of_urllib_through_untouched(rede_falsa, erro):
    """Not a NetworkError (that is `request`): the callers wrap these errors their own way, and the object that comes out is the one that went in."""
    rede_falsa(erro=erro)
    with pytest.raises(type(erro)) as caught:
        _rede().urlopen_seguro(urllib.request.Request("https://a.example/"), timeout=1)
    assert caught.value is erro


def test_urlopen_seguro_does_not_look_at_the_offline_switch(monkeypatch):
    """Not its call: voice and voicestudio never read SIMPLICIO_OFFLINE (VoiceStudio runs on this machine), so the helper that took the place of
    their `urlopen` does not either. `request` refuses; this one opens, as `urlopen` did."""
    falsa = _Rede(monkeypatch)
    monkeypatch.setenv("SIMPLICIO_OFFLINE", "1")
    _rede().urlopen_seguro(urllib.request.Request("http://127.0.0.1:3900/"), timeout=1)
    assert len(falsa.requisicoes) == 1


def test_urlopen_seguro_asks_for_a_timeout():
    """Every network call of the engine has one (voicestudio.py says so in its docstring): a caller cannot forget it."""
    with pytest.raises(TypeError):
        _rede().urlopen_seguro(urllib.request.Request("https://a.example/"))


@pytest.mark.parametrize("porque,velha,local,leva", ORIGENS, ids=[o[0] for o in ORIGENS])
def test_urlopen_seguro_hands_the_credentials_on_by_the_same_rule_as_request(salto, porque, velha, local, leva):
    """The table of `request`, through `urlopen_seguro` and a REAL opener over a fake network: the key reaches the next hop only while its netloc
    and its scheme are the ones the caller chose (or the scheme goes from http to https); what is not a credential goes everywhere."""
    falsa = salto({velha: (302, local)})
    with _rede().urlopen_seguro(urllib.request.Request(velha, headers=_CABECALHOS), timeout=5) as r:
        assert r.status == 200 and r.read() == b"ok"
    assert len(falsa.pedidos) == 2, falsa.pedidos
    (_, primeiro), (destino, segundo) = falsa.pedidos
    assert _CABECALHOS_EM_MINUSCULAS <= set(primeiro)
    levados = {nome for nome in _CREDENCIAIS_EM_MINUSCULAS if nome in segundo}
    assert levados == (_CREDENCIAIS_EM_MINUSCULAS if leva else set()), f"{destino} recebeu {sorted(levados)}"
    assert _COMUNS_EM_MINUSCULAS <= set(segundo) and all(segundo[n.lower()] == v for n, v in _COMUNS.items())


class _Abertura:
    """The end of every way into urllib: `urlopen` goes through the default opener and `build_opener(...)` makes another, and both end in
    `OpenerDirector.open`. Replaced, it writes down the handlers of the opener that was used, the request and the timeout, and answers
    `resposta` (or raises `erro`): written against that seam, the tests below mean the same before and after a caller changes how it gets
    to urllib."""

    def __init__(self, monkeypatch, resposta=None, erro=None):
        self.abertas = []
        outer = self

        def abre(opener, fullurl, data=None, timeout=None):
            outer.abertas.append({"handlers": [type(h) for h in opener.handlers], "req": fullurl, "timeout": timeout})
            if erro is not None:
                raise erro
            return resposta

        monkeypatch.setattr(urllib.request.OpenerDirector, "open", abre)


CHAVE_G, CHAVE_V = "AIzaS3CR3T-wiring", "S3CR3T-wiring"
GEMINI_JSON = json.dumps({"steps": [{"type": "model_output", "content": [
    {"type": "audio", "mime_type": "audio/wav", "data": base64.b64encode(b"RIFFfake").decode()}]}]}).encode()


def _chama_a_voz_do_gemini(tmp_path, monkeypatch):
    from simplicio_video import voice
    monkeypatch.setenv("GEMINI_API_KEY", CHAVE_G)
    monkeypatch.delenv("SIMPLICIO_GEMINI_BASE", raising=False)
    voice._gemini({"model": "gemini-mock", "voice": "Kore", "estilo": "calmo"}, "oi", tmp_path / "take.wav")


def _chama_a_voz_do_voicestudio(tmp_path, monkeypatch):
    from simplicio_video import voice_clone
    monkeypatch.setenv("VOICESTUDIO_API_KEY", CHAVE_V)
    monkeypatch.setenv("VOICESTUDIO_URL", "http://127.0.0.1:3900")
    voice_clone.voicestudio({"model": "omnivoice", "voice": "me"}, "oi", tmp_path / "take.wav")


def _chama_o_transporte_do_voicestudio(tmp_path, monkeypatch):
    from simplicio_video import voicestudio
    voicestudio.default_transport("POST", "http://127.0.0.1:3900/mcp/", b"{}", {"Authorization": f"Bearer {CHAVE_V}", "Content-Type": "application/json"}, 11)


# id -> (what calls it, what the server answers, the timeout it opens with, method, URL, the header that carries the key, its value)
CHAMADORES_DE_URLLIB = {
    "voice._gemini": (_chama_a_voz_do_gemini, GEMINI_JSON, 180, "POST", "https://generativelanguage.googleapis.com/v1beta/interactions",
                      "x-goog-api-key", CHAVE_G),
    "voice_clone.voicestudio": (_chama_a_voz_do_voicestudio, b"RIFFfake", 300, "POST", "http://127.0.0.1:3900/v1/audio/speech",
                                "authorization", f"Bearer {CHAVE_V}"),
    "voicestudio.default_transport": (_chama_o_transporte_do_voicestudio, b"{}", 11, "POST", "http://127.0.0.1:3900/mcp/",
                                      "authorization", f"Bearer {CHAVE_V}"),
}


@pytest.mark.parametrize("quem", list(CHAMADORES_DE_URLLIB))
def test_the_callers_that_send_a_key_open_the_url_with_the_handler_that_drops_it(monkeypatch, tmp_path, quem):
    """RED before U22i: they opened it with `urlopen`, whose opener has the stock redirect handler (it copies the key into the request it
    sends to the next host)."""
    chama, corpo, *_ = CHAMADORES_DE_URLLIB[quem]
    abertura = _Abertura(monkeypatch, _Resposta(200, corpo))
    chama(tmp_path, monkeypatch)
    assert len(abertura.abertas) == 1
    tipos = abertura.abertas[0]["handlers"]
    assert _rede().StripCredentialsRedirect in tipos and urllib.request.HTTPRedirectHandler not in tipos


@pytest.mark.parametrize("quem", list(CHAMADORES_DE_URLLIB))
def test_the_callers_that_send_a_key_send_the_same_request_with_the_same_timeout(monkeypatch, tmp_path, quem):
    """GREEN before and after: only the way to urllib changes, not what goes through it (URL, method, the key in its header, the timeout)."""
    chama, corpo, timeout, metodo, url, cabecalho, valor = CHAMADORES_DE_URLLIB[quem]
    abertura = _Abertura(monkeypatch, _Resposta(200, corpo))
    chama(tmp_path, monkeypatch)
    (aberta,) = abertura.abertas
    req = aberta["req"]
    assert (req.get_method(), req.full_url, aberta["timeout"]) == (metodo, url, timeout)
    assert {nome.lower(): v for nome, v in req.header_items()}[cabecalho] == valor


# (caller, what urllib raises, what comes out of the caller: the same object, or the name of the type and the text). `{OPEN_APP}` is the
# sentence voicestudio.py appends to its messages.
ERROS_DOS_CHAMADORES = [
    ("voice._gemini", urllib.error.URLError("dns"), "o mesmo"),
    ("voice._gemini", TimeoutError("lento"), "o mesmo"),
    ("voice_clone.voicestudio", urllib.error.URLError("refused"), ("CloneVoiceError", "provider=voicestudio: backend not reachable at "
                                                                  "http://127.0.0.1:3900 (refused). Start VoiceStudio or set VOICESTUDIO_URL.")),
    ("voice_clone.voicestudio", TimeoutError("lento"), "o mesmo"),
    ("voicestudio.default_transport", urllib.error.URLError("refused"), ("VoiceStudioError", "não consegui falar com o VoiceStudio em "
                                                                         "http://127.0.0.1:3900/mcp/ (refused). {OPEN_APP}")),
    ("voicestudio.default_transport", TimeoutError("lento"), ("VoiceStudioError", "o VoiceStudio em http://127.0.0.1:3900/mcp/ não respondeu "
                                                              "a tempo (lento). {OPEN_APP}")),
]


@pytest.mark.parametrize("quem,erro,saida", ERROS_DOS_CHAMADORES, ids=[f"{q}-{type(e).__name__}" for q, e, _ in ERROS_DOS_CHAMADORES])
def test_each_caller_says_the_errors_of_urllib_in_its_own_way_or_not_at_all(monkeypatch, tmp_path, quem, erro, saida):
    """GREEN before and after: the type and the text of what comes out are the module's own (voice leaves the error of urllib as it is, voice_clone
    and voicestudio wrap some of them), never `rede`'s: `urlopen_seguro` wraps nothing."""
    from simplicio_video import voicestudio
    chama = CHAMADORES_DE_URLLIB[quem][0]
    _Abertura(monkeypatch, erro=erro)
    with pytest.raises(BaseException) as caught:  # CloneVoiceError is a SystemExit
        chama(tmp_path, monkeypatch)
    if saida == "o mesmo":
        assert caught.value is erro
    else:
        tipo, texto = saida
        assert type(caught.value).__name__ == tipo and str(caught.value) == texto.format(OPEN_APP=voicestudio.OPEN_APP)


# Every place of the engine that opens a URL with the standard library, and why the key of a request cannot reach another host from it. A new
# one is a review of this table, on purpose: the three that were not here (voice, voice_clone, voicestudio) sent a key to whatever host a redirect
# named for as long as nobody looked. (A client that is not urllib is not in the scan: `busca` runs the `tinyfish` CLI, `remote`, `publish` and
# `download` run theirs, and `social` and `realoficial` have no client.)
CLIENTES_DE_URLLIB = {
    "rede.py": "`request` (StripCredentialsRedirect, or NoRedirect when it does not follow) and `urlopen_seguro` (StripCredentialsRedirect)",
    "commands/update.py": "_OPENER with _SameHostRedirect: the GitHub token goes to the API only, is dropped at a redirect to another host, and https "
                          "never goes down to http",
    "moneyprinter.py": "_OPENER with _NoRedirect and no proxy: never follows a redirect (x-api-key, loopback)",
    "openverse.py": "_PinnedHTTPS: the download of a file, to the IP it checked; no credential, never follows (the API goes through `rede.request` "
                    "with follow_redirects=False)",
    "tools_update.py": "urlopen of the PyPI document, https only: sends no credential",
    "video_to_skill.py": "_urlopen with _redirect_handler: sends no credential, and a hop off github.com is refused before it is followed",
    "engine/remote_render.py": "urlretrieve of a pinned ffmpeg build, on the remote box: sends no credential",
}
NOMES_DE_CLIENTE_DE_URLLIB = {"urlopen", "urlretrieve", "build_opener", "install_opener", "OpenerDirector", "HTTPConnection", "HTTPSConnection"}
PACOTE = ROOT / "src" / "simplicio_video"


def _nomes_de(arquivo: Path) -> set[str]:
    """Every attribute and every bare name the source of `arquivo` mentions, by ast: a docstring or a comment is not a use."""
    nomes = set()
    for no in ast.walk(ast.parse(arquivo.read_text(encoding="utf-8"))):
        if isinstance(no, ast.Attribute):
            nomes.add(no.attr)
        elif isinstance(no, ast.Name):
            nomes.add(no.id)
    return nomes


def test_every_place_that_opens_a_url_with_urllib_is_known():
    """RED before U22i: voice.py, voice_clone.py and voicestudio.py were not on the list, and each sent a key in a header."""
    achados = {}
    for arquivo in sorted(PACOTE.rglob("*.py")):
        rel = arquivo.relative_to(PACOTE).as_posix()
        nomes = set() if rel.startswith("data/") else _nomes_de(arquivo) & NOMES_DE_CLIENTE_DE_URLLIB
        if nomes:
            achados[rel] = nomes
    assert sorted(set(achados) - set(CLIENTES_DE_URLLIB)) == [], "abre URL com urllib e nao esta na lista: confira a credencial de cada cabecalho"
    assert sorted(set(CLIENTES_DE_URLLIB) - set(achados)) == [], "esta na lista e nao abre mais URL com urllib: tire da lista"


@pytest.mark.parametrize("arquivo", ["voice.py", "voice_clone.py", "voicestudio.py"])
def test_the_modules_that_send_a_key_open_their_urls_through_urlopen_seguro(arquivo):
    """RED before U22i: they called `urllib.request.urlopen`."""
    nomes = _nomes_de(PACOTE / arquivo)
    assert "urlopen_seguro" in nomes and "urlopen" not in nomes
