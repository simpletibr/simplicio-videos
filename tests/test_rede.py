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
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from conftest import ROOT

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


# the copies that exist today as a function (busca, openverse and swap_providers/http parse it inline: see the request test below).
# tools_update had one too until U24a: it asks `rede.offline()` now, and `tools_update.live_io().network` is what the parity tests check.
COPIAS_DE_OFFLINE = ["simplicio_video.toonflow._offline", "simplicio_video.instagram._offline", "simplicio_video.montage._offline",
                     "simplicio_video.commands.update._offline"]


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
