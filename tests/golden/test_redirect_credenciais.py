"""U22g (golden): o que `rede.request` leva ao host de destino quando segue um redirecionamento.

DEFEITO (segurança; achado novo da onda U22). `request(..., follow_redirects=True)` (o padrão, que é o que todos os adaptadores do swap
usam) abria a URL com o opener padrão do urllib, que COPIA todo cabeçalho da requisição para a requisição redirecionada. Um servidor que
respondia 301/302/303/307/308 com `Location: <outro host>` recebia o `Authorization`, o `x-goog-api-key`, o `x-api-key`, o
`Proxy-Authorization` e o `Cookie` da chamada original, e um redirecionamento de https para http levava a chave em texto claro. O
`NoRedirect` (e o `follow_redirects=False` do Openverse) existe por isso; o caminho que SEGUE o redirecionamento ficou sem a mesma guarda.

COMO O TESTE RODA. Dois servidores HTTP de loopback, A e B: o mesmo nome de host em portas diferentes, ou seja, netloc diferente. O
cliente (`rede.request`) bate em A, A responde com um redirecionamento e B registra o que recebeu. Servidores e cliente vivem num
processo filho limpo (`python -I`, sem proxy nem SIMPLICIO_OFFLINE), como os testes de rede de tests/test_rede.py: o bloqueio de
sockets do pytest continua ligado no processo do teste e o filho só conecta em loopback. O filho roda a tabela inteira de cenários uma
vez; cada teste lê a sua linha. (O downgrade https -> http e as formas de URL ficam em tests/test_rede.py, sem socket: aqui não há TLS.)

VERMELHO antes da correção (B recebe a credencial): um redirecionamento para outro host, para cada credencial e para cada código que o
urllib segue (GET: 301, 302, 303, 307, 308; POST: 301, 302, 303, que viram GET), a volta a A depois de passar por B, e o salto para B no
fim de uma cadeia.
VERDE antes e depois (caracterização do que NÃO muda): o redirecionamento para o MESMO netloc continua levando tudo; os cabeçalhos que não
são credencial (Accept, User-Agent, X-Trace-Id, X-DashScope-Async) continuam indo para o outro host; o redirecionamento continua sendo
seguido; `follow_redirects=False` devolve o 3xx como resposta e nunca fala com B; POST 301/302/303 vira GET sem corpo; POST 307/308 NÃO é
seguido pelo urllib (devolve o 3xx como resposta e B nunca é chamado), e continua assim."""
from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

from helpers import ROOT

# What the callers of `request` put in a header (swap adapters: Bearer, the `Key ...` of fal, the x-goog-api-key of Gemini; Openverse:
# Bearer; MoneyPrinter: x-api-key; Proxy-Authorization is what a proxy with a password makes urllib add). The values are obviously fake.
CREDENCIAIS = {  # id -> (header name as the caller writes it, value)
    "Authorization-Bearer": ("Authorization", "Bearer S3CR3T-bearer"),
    "Authorization-Key": ("Authorization", "Key S3CR3T-fal"),
    "Authorization-Basic": ("Authorization", "Basic UzNDUjNULWJhc2lj"),
    "x-goog-api-key": ("x-goog-api-key", "AIzaS3CR3T-google"),
    "x-api-key": ("x-api-key", "S3CR3T-xapikey"),
    "xi-api-key": ("xi-api-key", "S3CR3T-eleven"),
    "Proxy-Authorization": ("Proxy-Authorization", "Basic UzNDUjNULXByb3h5"),
    "Cookie": ("Cookie", "sessao=S3CR3T-cookie"),
}
# every credential header at once (one value per name: the three Authorization forms cannot share a dict)
TODAS = {nome: valor for cid, (nome, valor) in CREDENCIAIS.items() if cid not in ("Authorization-Key", "Authorization-Basic")}
# headers that are not a credential and must keep going wherever the redirect goes
COMUNS = {"Accept": "application/json", "User-Agent": "u22g-teste/1", "X-Trace-Id": "trace-1", "X-DashScope-Async": "enable"}
CODIGOS = (301, 302, 303, 307, 308)
# urllib learned 308 in Python 3.11 (bpo-40321); before that a 308 is returned as the response and never followed
SEGUE = {c: c != 308 or sys.version_info >= (3, 11) for c in CODIGOS}
POST_SEGUE = (301, 302, 303)  # urllib refuses to follow a POST with 307/308 (it would need the user's say-so for the body)


def _casos() -> list[dict]:
    """The scenarios. `rotas` maps "<server> <path>" to [status, Location]; a path nobody listed answers 200 "ok". `{A}` and `{B}` in a
    Location are the base URLs of the two servers."""
    casos = []

    def novo(cid, rotas, cabecalhos, metodo="GET", corpo=None, seguir=None):
        casos.append({"id": cid, "metodo": metodo, "caminho": "/vai", "rotas": rotas, "cabecalhos": cabecalhos, "json": corpo, "seguir": seguir})

    for codigo in CODIGOS:
        para_b, para_a = {"A /vai": [codigo, "{B}/fim"]}, {"A /vai": [codigo, "{A}/fim"]}
        for cid, (nome, valor) in CREDENCIAIS.items():
            novo(f"outro-host/GET/{codigo}/{cid}", para_b, {nome: valor, **COMUNS})
        novo(f"mesmo-netloc/GET/{codigo}", para_a, {**TODAS, **COMUNS})
        novo(f"sem-seguir/GET/{codigo}", para_b, {**TODAS, **COMUNS}, seguir=False)
        novo(f"outro-host/POST/{codigo}", para_b, {**TODAS, **COMUNS}, metodo="POST", corpo={"video": "x"})
        novo(f"mesmo-netloc/POST/{codigo}", para_a, {**TODAS, **COMUNS}, metodo="POST", corpo={"video": "x"})
    for codigo in (302, 307):
        novo(f"mesmo-netloc/relativo/{codigo}", {"A /vai": [codigo, "/fim"]}, {**TODAS, **COMUNS})
    # A -> A -> B: the hop inside A keeps them, the hop out drops them
    novo("cadeia/A-A-B", {"A /vai": [302, "{A}/meio"], "A /meio": [302, "{B}/fim"]}, {**TODAS, **COMUNS})
    # A -> B -> A: what was dropped at B does not come back when the chain returns to A
    novo("cadeia/A-B-A", {"A /vai": [302, "{B}/volta"], "B /volta": [302, "{A}/fim"]}, {**TODAS, **COMUNS})
    return casos


_FILHO = r'''
import http.server
import json
import socket
import sys
import threading

src, casos = sys.argv[1], json.loads(sys.argv[2])
sys.path.insert(0, src)
from simplicio_video import rede

_connect = socket.socket.connect


def _so_loopback(self, endereco):
    if not (isinstance(endereco, tuple) and endereco[0] in ("127.0.0.1", "::1")):
        raise AssertionError(f"fora do loopback: {endereco!r}")
    return _connect(self, endereco)


socket.socket.connect = _so_loopback

BASES, ROTAS, VISTO = {}, {}, []


def servidor(nome):
    class Atende(http.server.BaseHTTPRequestHandler):
        def _atende(self):
            tamanho = int(self.headers.get("Content-Length") or 0)
            corpo = self.rfile.read(tamanho).decode("utf8") if tamanho else ""
            VISTO.append({"servidor": nome, "metodo": self.command, "caminho": self.path,
                          "cabecalhos": {k.lower(): v for k, v in self.headers.items()}, "corpo": corpo})
            status, local = ROTAS.get((nome, self.path), (200, None))
            self.send_response(status)
            if local:
                self.send_header("Location", local.format(A=BASES["A"], B=BASES["B"]))
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"ok")

        do_GET = do_POST = do_HEAD = _atende

        def log_message(self, *args):
            pass

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Atende)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


for nome in ("A", "B"):
    BASES[nome] = f"http://127.0.0.1:{servidor(nome).server_address[1]}"

saida = {"_bases": BASES}
for caso in casos:
    VISTO.clear()
    ROTAS.clear()
    for chave, (status, local) in caso["rotas"].items():
        servidor_da_rota, caminho = chave.split(" ", 1)
        ROTAS[(servidor_da_rota, caminho)] = (status, local)
    kw = {}
    if caso["json"] is not None:
        kw["json_body"] = caso["json"]
    if caso["seguir"] is not None:
        kw["follow_redirects"] = caso["seguir"]
    try:
        r = rede.request(caso["metodo"], BASES["A"] + caso["caminho"], headers=caso["cabecalhos"], timeout=20, **kw)
        resposta = {"status": r.status, "corpo": r.body.decode("utf8"), "cabecalhos": r.headers}
    except Exception as e:  # the test reads it; a refusal here is a finding, not a crash of the harness
        resposta = {"erro": f"{type(e).__name__}: {e}"}
    saida[caso["id"]] = {"resposta": resposta, "visto": list(VISTO)}
print(json.dumps(saida))
'''


def _ambiente_limpo() -> dict:
    """No proxy variable, no SIMPLICIO_OFFLINE: the child talks to loopback directly and is allowed to."""
    return {k: os.environ[k] for k in ("PATH", "SYSTEMROOT", "TEMP", "TMP", "TMPDIR", "HOME", "LANG", "LC_ALL") if k in os.environ}


@pytest.fixture(scope="module")
def visto() -> dict:
    r = subprocess.run([sys.executable, "-I", "-c", _FILHO, str(ROOT / "src"), json.dumps(_casos())], capture_output=True, text=True,
                       env=_ambiente_limpo(), timeout=180)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout.strip().splitlines()[-1])


def _de(caso: dict, servidor: str) -> list[dict]:
    return [h for h in caso["visto"] if h["servidor"] == servidor]


def _vazou(pedido: dict, valor: str) -> dict:
    """The headers of `pedido` that carry `valor`, under whatever name."""
    return {nome: v for nome, v in pedido["cabecalhos"].items() if valor in v}


# ---- the harness itself ---------------------------------------------------------------------------------------------------------


def test_the_two_servers_are_two_netlocs_of_the_same_host_name(visto):
    """Same host name, different ports: the netloc differs (the rule compares the port too, not only the host name)."""
    a, b = visto["_bases"]["A"], visto["_bases"]["B"]
    assert a != b and a.rsplit(":", 1)[0] == b.rsplit(":", 1)[0] == "http://127.0.0.1"


def test_in_every_scenario_the_first_host_gets_the_credentials_the_caller_sent(visto):
    """The credential is for the host the caller chose: A always gets the original request with every header in it."""
    casos = {k: v for k, v in visto.items() if k != "_bases"}
    assert len(casos) == len(_casos())
    for caso in _casos():
        primeiro = visto[caso["id"]]["visto"][0]
        assert primeiro["servidor"] == "A", caso["id"]
        for nome, valor in caso["cabecalhos"].items():
            assert primeiro["cabecalhos"].get(nome.lower()) == valor, (caso["id"], nome)


# ---- a redirect to ANOTHER host (another netloc) --------------------------------------------------------------------------------


@pytest.mark.parametrize("cid", list(CREDENCIAIS))
@pytest.mark.parametrize("codigo", CODIGOS)
def test_a_redirect_to_another_host_does_not_carry_the_credential(visto, codigo, cid):
    """RED before U22g: B got the credential under its own name (urllib copies every header into the redirected request)."""
    caso = visto[f"outro-host/GET/{codigo}/{cid}"]
    _, valor = CREDENCIAIS[cid]
    em_b = _de(caso, "B")
    assert len(em_b) == (1 if SEGUE[codigo] else 0), f"o redirecionamento {codigo} {'deveria' if SEGUE[codigo] else 'nao deveria'} ser seguido"
    for pedido in em_b:
        assert _vazou(pedido, valor) == {}, f"o host B recebeu a credencial {cid} no {codigo}: {sorted(_vazou(pedido, valor))}"


@pytest.mark.parametrize("codigo", CODIGOS)
def test_a_redirect_to_another_host_is_followed_and_keeps_the_headers_that_are_not_a_credential(visto, codigo):
    """GREEN before and after: only the credential goes away; Accept, User-Agent and the custom headers still reach the other host."""
    caso = visto[f"outro-host/GET/{codigo}/Authorization-Bearer"]
    em_b = _de(caso, "B")
    if not SEGUE[codigo]:
        assert em_b == [] and caso["resposta"]["status"] == codigo
        return
    assert caso["resposta"]["status"] == 200 and caso["resposta"]["corpo"] == "ok"
    assert [(h["metodo"], h["caminho"]) for h in em_b] == [("GET", "/fim")]
    for nome, valor in COMUNS.items():
        assert em_b[0]["cabecalhos"].get(nome.lower()) == valor, nome


# ---- a redirect to the SAME netloc ----------------------------------------------------------------------------------------------


@pytest.mark.parametrize("codigo", CODIGOS)
def test_a_redirect_to_the_same_netloc_keeps_every_header(visto, codigo):
    """GREEN before and after: the host that got the credential first is the one that gets it again."""
    caso = visto[f"mesmo-netloc/GET/{codigo}"]
    em_a, em_b = _de(caso, "A"), _de(caso, "B")
    assert em_b == []
    if not SEGUE[codigo]:
        assert len(em_a) == 1
        return
    assert [h["caminho"] for h in em_a] == ["/vai", "/fim"]
    for nome, valor in {**TODAS, **COMUNS}.items():
        assert em_a[1]["cabecalhos"].get(nome.lower()) == valor, nome


@pytest.mark.parametrize("codigo", (302, 307))
def test_a_relative_redirect_stays_on_the_netloc_and_keeps_every_header(visto, codigo):
    """GREEN before and after: `Location: /fim` is resolved against the URL of the request, so it is the same netloc."""
    caso = visto[f"mesmo-netloc/relativo/{codigo}"]
    assert _de(caso, "B") == [] and [h["caminho"] for h in _de(caso, "A")] == ["/vai", "/fim"]
    for nome, valor in {**TODAS, **COMUNS}.items():
        assert _de(caso, "A")[1]["cabecalhos"].get(nome.lower()) == valor, nome


# ---- chains ---------------------------------------------------------------------------------------------------------------------


def test_in_a_chain_the_hop_inside_the_netloc_keeps_the_credential_and_the_hop_out_drops_it(visto):
    """A -> A -> B. RED before U22g on the last hop (B got everything the first request carried)."""
    caso = visto["cadeia/A-A-B"]
    assert [(h["servidor"], h["caminho"]) for h in caso["visto"]] == [("A", "/vai"), ("A", "/meio"), ("B", "/fim")]
    meio, fim = caso["visto"][1], caso["visto"][2]
    for nome, valor in TODAS.items():
        assert meio["cabecalhos"].get(nome.lower()) == valor, f"o salto dentro de A perdeu {nome}"
        assert _vazou(fim, valor) == {}, f"o host B recebeu {nome} no fim da cadeia"
    for nome, valor in COMUNS.items():
        assert fim["cabecalhos"].get(nome.lower()) == valor, nome


def test_what_was_dropped_at_another_host_does_not_come_back_when_the_chain_returns(visto):
    """A -> B -> A. RED before U22g (the stock handler copies the headers of each hop into the next, so all of them came back to A)."""
    caso = visto["cadeia/A-B-A"]
    assert [(h["servidor"], h["caminho"]) for h in caso["visto"]] == [("A", "/vai"), ("B", "/volta"), ("A", "/fim")]
    for pedido in caso["visto"][1:]:
        for nome, valor in TODAS.items():
            assert _vazou(pedido, valor) == {}, f"o salto para {pedido['servidor']}{pedido['caminho']} levou {nome}"
        for nome, valor in COMUNS.items():
            assert pedido["cabecalhos"].get(nome.lower()) == valor, nome


# ---- follow_redirects=False -----------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("codigo", CODIGOS)
def test_without_following_the_3xx_is_the_response_and_the_other_host_is_never_asked(visto, codigo):
    """GREEN before and after: `NoRedirect`; the credential was for A (A got it once) and B hears nothing."""
    caso = visto[f"sem-seguir/GET/{codigo}"]
    assert caso["resposta"]["status"] == codigo and caso["resposta"]["corpo"] == "ok"
    assert caso["resposta"]["cabecalhos"]["location"] == f"{visto['_bases']['B']}/fim"
    assert [(h["servidor"], h["caminho"]) for h in caso["visto"]] == [("A", "/vai")]


# ---- POST -----------------------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("codigo", POST_SEGUE)
def test_a_post_redirected_to_another_host_becomes_a_get_without_body(visto, codigo):
    """GREEN before and after: what urllib does with the method and the body is not touched (the body and its Content-Type stay home)."""
    caso = visto[f"outro-host/POST/{codigo}"]
    assert [(h["servidor"], h["metodo"], h["caminho"]) for h in caso["visto"]] == [("A", "POST", "/vai"), ("B", "GET", "/fim")]
    assert caso["visto"][0]["corpo"] == json.dumps({"video": "x"})
    em_b = _de(caso, "B")[0]
    assert em_b["corpo"] == "" and "content-type" not in em_b["cabecalhos"]
    for nome, valor in COMUNS.items():
        assert em_b["cabecalhos"].get(nome.lower()) == valor, nome


@pytest.mark.parametrize("codigo", POST_SEGUE)
def test_a_post_redirected_to_another_host_does_not_carry_the_credential(visto, codigo):
    """RED before U22g: the POST that became a GET still took every credential header to B."""
    em_b = _de(visto[f"outro-host/POST/{codigo}"], "B")
    assert len(em_b) == 1
    for nome, valor in TODAS.items():
        assert _vazou(em_b[0], valor) == {}, f"o host B recebeu {nome} no POST {codigo}"


@pytest.mark.parametrize("codigo", (307, 308))
def test_a_post_with_307_or_308_is_not_followed_and_the_other_host_is_never_asked(visto, codigo):
    """GREEN before and after: urllib raises HTTPError for a POST 307/308 (the body would have to be sent again), `request` turns it into
    the 3xx Response. The brief of U22g expected these to be followed; they never were, and this change does not make them so."""
    for onde in ("outro-host", "mesmo-netloc"):
        caso = visto[f"{onde}/POST/{codigo}"]
        assert caso["resposta"]["status"] == codigo and caso["resposta"]["corpo"] == "ok"
        assert [(h["servidor"], h["metodo"], h["caminho"]) for h in caso["visto"]] == [("A", "POST", "/vai")]


@pytest.mark.parametrize("codigo", POST_SEGUE)
def test_a_post_redirected_to_the_same_netloc_becomes_a_get_and_keeps_every_header(visto, codigo):
    """GREEN before and after."""
    caso = visto[f"mesmo-netloc/POST/{codigo}"]
    assert [(h["servidor"], h["metodo"], h["caminho"]) for h in caso["visto"]] == [("A", "POST", "/vai"), ("A", "GET", "/fim")]
    segundo = caso["visto"][1]
    assert segundo["corpo"] == "" and "content-type" not in segundo["cabecalhos"]
    for nome, valor in {**TODAS, **COMUNS}.items():
        assert segundo["cabecalhos"].get(nome.lower()) == valor, nome
