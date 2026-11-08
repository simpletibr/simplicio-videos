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
seguido pelo urllib (devolve o 3xx como resposta e B nunca é chamado), e continua assim.

U22i (o mesmo defeito, nos chamadores que NÃO passam por `rede.request`). `voice._gemini` (Gemini TTS, `x-goog-api-key`),
`voice_clone.voicestudio` (VoiceStudio TTS, `Authorization: Bearer`) e `voicestudio.default_transport` (toda chamada ao app: `dub
export` e `dub create` levam o mesmo Bearer) abriam a URL com `urllib.request.urlopen`, o opener padrão, e a U22g só tirou o defeito do
`request`: a chave dessas três chamadas ia para o host de qualquer `Location`. A mesma montagem (A responde com um redirecionamento, B
registra o que recebeu), numa segunda tabela e num segundo filho (`_FILHO_CHAMADORES`) que chama os módulos de verdade, com a chave no
ambiente como o usuário a poria. Ao fim do arquivo, depois da U22g.
VERMELHO antes da U22i (B recebe a chave): um redirecionamento para outro host, para cada chamador e para cada código que o urllib segue
(GET: 301, 302, 303, 307, 308; POST: 301, 302, 303), e o destino que EXIGE a chave (hoje a chamada dá certo porque a chave chegou; depois o
chamador diz o seu erro de HTTP de sempre).
VERDE antes e depois (o que NÃO muda): o redirecionamento para o MESMO netloc (absoluto ou relativo) continua levando a chave; o
redirecionamento continua sendo seguido e o resultado do chamador é o mesmo; o primeiro pedido (método, caminho, corpo, cabeçalhos) é o mesmo;
os cabeçalhos que não são credencial continuam indo para o outro host; POST 307/308 não é seguido e o erro é o texto de sempre de cada módulo."""
from __future__ import annotations

import base64
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


# ==== U22i: the callers that do not go through `request` =========================================================================
#
# `voice._gemini`, `voice_clone.voicestudio` and `voicestudio.default_transport` (so `dub export` and `dub create`: every call to the app) open the
# URL with `urllib.request.urlopen`, and have since before U22g: they keep their own errors, so they never went through `request`. Same two
# servers, same question, but the clients are the modules themselves, called the way the product calls them (the key in the environment, the
# base URL in the environment or in the constructor), in a second child process (`_FILHO_CHAMADORES`) that also keeps the tests that follow
# off the network. A fresh child, not a longer table in the first one: it imports voice, voice_clone and voicestudio (the first child only needs
# `rede`), and its servers answer a body of their own per route (the Gemini JSON, the WAV, the job) and, when asked, a 401 to a request that
# arrives without a key (a destination that needs it).

CHAVE_GEMINI = "AIzaS3CR3T-gemini"
CHAVE_VOICESTUDIO = "S3CR3T-voicestudio"
WAV_FALSO = "RIFFfake-wav-bytes"  # what the last hop answers to the TTS callers; they write it as it comes
MP4_FALSO = "ftypmp42-fake-dubbed-video"
GEMINI_RESPOSTA = json.dumps({"steps": [{"type": "model_output", "content": [
    {"type": "audio", "mime_type": "audio/wav", "data": base64.b64encode(WAV_FALSO.encode()).decode()}]}]})
JOB_RESPOSTA = json.dumps({"job_id": "ab12cd34", "task_id": "prep_ab12cd34", "filename": "clip.mp4"})
CHAMADORES = {  # id -> what the caller sends first to A and what the last hop answers; `valor` is the whole header, `chave` the secret in it
    "gemini": {"metodo": "POST", "caminho": "/v1beta/interactions", "final": GEMINI_RESPOSTA, "cabecalho": "x-goog-api-key",
               "valor": CHAVE_GEMINI, "chave": CHAVE_GEMINI, "comuns": {}},
    "voice_clone": {"metodo": "POST", "caminho": "/v1/audio/speech", "final": WAV_FALSO, "cabecalho": "authorization",
                    "valor": f"Bearer {CHAVE_VOICESTUDIO}", "chave": CHAVE_VOICESTUDIO, "comuns": {}},
    "dub_export": {"metodo": "GET", "caminho": "/dub/download/job1", "final": MP4_FALSO, "cabecalho": "authorization",
                   "valor": f"Bearer {CHAVE_VOICESTUDIO}", "chave": CHAVE_VOICESTUDIO,
                   "comuns": {"accept": "video/mp4", "x-omnivoice-client-id": "simplicio-video"}},
    "dub_create": {"metodo": "POST", "caminho": "/dub/upload", "final": JOB_RESPOSTA, "cabecalho": "authorization",
                   "valor": f"Bearer {CHAVE_VOICESTUDIO}", "chave": CHAVE_VOICESTUDIO,
                   "comuns": {"accept": "application/json", "x-omnivoice-client-id": "simplicio-video"}},
}
# (caller, code) pairs urllib follows: a GET follows the five, a POST only 301, 302 and 303 (as a GET); and the POSTs it refuses
SEGUIDOS = [(c, k) for c, d in CHAMADORES.items() for k in CODIGOS if (SEGUE[k] if d["metodo"] == "GET" else k in POST_SEGUE)]
NAO_SEGUIDOS = [(c, k) for c, d in CHAMADORES.items() if d["metodo"] == "POST" for k in CODIGOS if k not in POST_SEGUE]
IDS_SEGUIDOS = [f"{c}-{k}" for c, k in SEGUIDOS]
IDS_NAO_SEGUIDOS = [f"{c}-{k}" for c, k in NAO_SEGUIDOS]


def _casos_chamadores() -> list[dict]:
    """The scenarios of the callers. A route is [status, Location] or [status, Location, body, needs-the-key]; `{A}` and `{B}` in a Location
    are the base URLs of the two servers. The path A answers to is the one the caller asks for (`caminho`), the last hop is `/fim`."""
    casos = []

    def novo(cid, chamador, rotas):
        casos.append({"id": cid, "chamador": chamador, "rotas": rotas, "chave": CHAMADORES[chamador]["chave"]})

    for chamador, dados in CHAMADORES.items():
        a, final = f"A {dados['caminho']}", dados["final"]
        for codigo in CODIGOS:
            novo(f"outro-host/{chamador}/{codigo}", chamador, {a: [codigo, "{B}/fim"], "B /fim": [200, None, final]})
            novo(f"mesmo-netloc/{chamador}/{codigo}", chamador, {a: [codigo, "{A}/fim"], "A /fim": [200, None, final]})
        novo(f"relativo/{chamador}", chamador, {a: [302, "/fim"], "A /fim": [200, None, final]})
        novo(f"exige-chave/{chamador}", chamador, {a: [302, "{B}/fim"], "B /fim": [200, None, final, True]})
    return casos


_FILHO_CHAMADORES = r'''
import http.server
import json
import os
import socket
import sys
import tempfile
import threading
from pathlib import Path

src, casos = sys.argv[1], json.loads(sys.argv[2])
sys.path.insert(0, src)

_connect = socket.socket.connect


def _so_loopback(self, endereco):
    if not (isinstance(endereco, tuple) and endereco[0] in ("127.0.0.1", "::1")):
        raise AssertionError(f"fora do loopback: {endereco!r}")
    return _connect(self, endereco)


socket.socket.connect = _so_loopback

from simplicio_video import voice, voice_clone, voicestudio

BASES, ROTAS, VISTO = {}, {}, []
CHAVES = ("authorization", "x-goog-api-key")  # what a destination that needs the key looks for


def servidor(nome):
    class Atende(http.server.BaseHTTPRequestHandler):
        def _atende(self):
            tamanho = int(self.headers.get("Content-Length") or 0)
            corpo = self.rfile.read(tamanho).decode("latin-1") if tamanho else ""
            VISTO.append({"servidor": nome, "metodo": self.command, "caminho": self.path,
                          "cabecalhos": {k.lower(): v for k, v in self.headers.items()}, "corpo": corpo})
            status, local, resposta, exige = ROTAS.get((nome, self.path.split("?")[0]), (200, None, "ok", False))
            if exige and not any(c in self.headers for c in CHAVES):
                status, local, resposta = 401, None, json.dumps({"detail": "key required"})
            self.send_response(status)
            if local:
                self.send_header("Location", local.format(A=BASES["A"], B=BASES["B"]))
            dados = resposta.encode("utf8")
            self.send_header("Content-Length", str(len(dados)))
            self.end_headers()
            self.wfile.write(dados)

        do_GET = do_POST = _atende

        def log_message(self, *args):
            pass

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Atende)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


for nome in ("A", "B"):
    BASES[nome] = f"http://127.0.0.1:{servidor(nome).server_address[1]}"

pasta = Path(tempfile.mkdtemp())
(pasta / "clip.mp4").write_bytes(b"fake-mp4-bytes")
saida = {"_bases": BASES}
for n, caso in enumerate(casos):
    VISTO.clear()
    ROTAS.clear()
    for chave, valor in caso["rotas"].items():
        quem, caminho = chave.split(" ", 1)
        status, local, *resto = valor
        ROTAS[(quem, caminho)] = (status, local, resto[0] if resto else "ok", bool(resto[1]) if len(resto) > 1 else False)
    for var in ("GEMINI_API_KEY", "SIMPLICIO_GEMINI_BASE", "VOICESTUDIO_URL", "VOICESTUDIO_API_KEY"):
        os.environ.pop(var, None)
    a, dst = BASES["A"], pasta / f"saida-{n}"
    try:
        if caso["chamador"] == "gemini":
            os.environ.update(GEMINI_API_KEY=caso["chave"], SIMPLICIO_GEMINI_BASE=a + "/v1beta")
            retorno = voice._gemini({"model": "gemini-mock", "voice": "Kore", "estilo": "calmo"}, "uma frase", dst)
        elif caso["chamador"] == "voice_clone":
            os.environ.update(VOICESTUDIO_API_KEY=caso["chave"], VOICESTUDIO_URL=a)
            retorno = voice_clone.voicestudio({"model": "omnivoice", "voice": "me"}, "hello", dst)
        else:
            os.environ["VOICESTUDIO_API_KEY"] = caso["chave"]
            app = voicestudio.VoiceStudio(base=a)
            if caso["chamador"] == "dub_export":
                retorno = app.dub_export("job1", "pl", dst)
            else:
                retorno = app.dub_create(pasta / "clip.mp4", source_lang="pt")
        resposta = {"retorno": retorno, "arquivo": dst.read_bytes().decode("latin-1") if dst.exists() else None}
    except BaseException as e:  # VoiceError and CloneVoiceError are SystemExit: the test reads the error; a refusal here is a finding
        resposta = {"erro": f"{type(e).__name__}: {e}"}
    saida[caso["id"]] = {"resposta": resposta, "visto": list(VISTO)}
print(json.dumps(saida))
'''


@pytest.fixture(scope="module")
def visto_chamadores() -> dict:
    r = subprocess.run([sys.executable, "-I", "-c", _FILHO_CHAMADORES, str(ROOT / "src"), json.dumps(_casos_chamadores())],
                       capture_output=True, text=True, env=_ambiente_limpo(), timeout=180)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout.strip().splitlines()[-1])


def _confere_o_primeiro_pedido(chamador: str, pedido: dict) -> None:
    """What each caller sends to the host it was told to call: method, path, the key, the body. Frozen as it is today."""
    dados, cab, corpo = CHAMADORES[chamador], pedido["cabecalhos"], pedido["corpo"]
    assert pedido["servidor"] == "A" and pedido["metodo"] == dados["metodo"] and pedido["caminho"].split("?")[0] == dados["caminho"]
    assert cab[dados["cabecalho"]] == dados["valor"]
    for nome, valor in dados["comuns"].items():
        assert cab[nome] == valor, nome
    if chamador == "gemini":
        doc = json.loads(corpo)
        assert cab["content-type"] == "application/json" and doc["model"] == "gemini-mock"
        assert doc["input"][0]["content"][0]["text"] == "uma frase" and doc["generation_config"]["speech_config"] == [{"voice": "Kore"}]
    elif chamador == "voice_clone":
        assert cab["content-type"] == "application/json"
        assert json.loads(corpo) == {"model": "omnivoice", "voice": "me", "input": "hello", "response_format": "wav"}
    elif chamador == "dub_export":
        assert pedido["caminho"] == "/dub/download/job1?preserve_bg=true&bed_level=1.0&default_track=pl&include_tracks=pl" and corpo == ""
    else:
        assert cab["content-type"].startswith("multipart/form-data; boundary=simplicio-")
        for trecho in ('name="video"; filename="clip.mp4"', "fake-mp4-bytes", 'name="input_type"', 'name="source_lang"'):
            assert trecho in corpo, trecho


def _confere_o_resultado(chamador: str, resposta: dict) -> None:
    """What each caller hands back once the redirect was followed: what the last hop answered, treated as the caller always treated it."""
    assert "erro" not in resposta, resposta
    retorno = resposta["retorno"]
    if chamador == "gemini":
        assert resposta["arquivo"] == WAV_FALSO and retorno["mime"] == "audio/wav" and retorno["voice"] == "Kore"
        assert retorno["chars"] == len("uma frase") and retorno["model"] == "gemini-mock"
    elif chamador == "voice_clone":
        assert resposta["arquivo"] == WAV_FALSO and retorno is None
    elif chamador == "dub_export":
        assert resposta["arquivo"] == MP4_FALSO and retorno["bytes"] == len(MP4_FALSO) and retorno["job"] == "job1"
    else:
        assert (retorno["job"], retorno["task"], retorno["filename"]) == ("ab12cd34", "prep_ab12cd34", "clip.mp4")


def _erro_de_401(chamador: str, bases: dict) -> str:
    """The error each caller reports when the destination answers 401 (it needs the key and the key stayed with the first host)."""
    if chamador == "gemini":
        return f'VoiceError: provider=gemini: HTTP 401 from {bases["A"]}/v1beta/interactions\n{{"detail": "key required"}}'
    if chamador == "voice_clone":
        return 'CloneVoiceError: provider=voicestudio: HTTP 401: {"detail": "key required"}'
    return "VoiceStudioError: o app recusou o acesso (HTTP 401: key required). Defina VOICESTUDIO_API_KEY se o app pede chave."


# ---- the harness itself ---------------------------------------------------------------------------------------------------------


def test_in_every_caller_scenario_the_first_host_gets_the_key_the_caller_was_given(visto_chamadores):
    """The key is for the host the caller chose: A always gets the original request with the key in its header, and the two servers are
    two netlocs of the same host name."""
    a, b = visto_chamadores["_bases"]["A"], visto_chamadores["_bases"]["B"]
    assert a != b and a.rsplit(":", 1)[0] == b.rsplit(":", 1)[0] == "http://127.0.0.1"
    casos = _casos_chamadores()
    assert len({k for k in visto_chamadores if k != "_bases"}) == len(casos)
    for caso in casos:
        primeiro = visto_chamadores[caso["id"]]["visto"][0]
        dados = CHAMADORES[caso["chamador"]]
        assert primeiro["servidor"] == "A" and primeiro["cabecalhos"].get(dados["cabecalho"]) == dados["valor"], caso["id"]


@pytest.mark.parametrize("chamador", list(CHAMADORES))
def test_the_first_request_of_each_caller_is_what_it_always_sent(visto_chamadores, chamador):
    """GREEN before and after: method, path, body and headers of the request to the host the caller was given."""
    caso = visto_chamadores[f"mesmo-netloc/{chamador}/302"]
    _confere_o_primeiro_pedido(chamador, caso["visto"][0])


# ---- a redirect to ANOTHER host --------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("chamador,codigo", [(c, k) for c in CHAMADORES for k in CODIGOS], ids=[f"{c}-{k}" for c in CHAMADORES for k in CODIGOS])
def test_a_caller_redirected_to_another_host_does_not_carry_its_key(visto_chamadores, chamador, codigo):
    """RED before U22i: B got the key under its own name (urllib copies every header into the redirected request)."""
    caso = visto_chamadores[f"outro-host/{chamador}/{codigo}"]
    segue = (chamador, codigo) in SEGUIDOS
    em_b = _de(caso, "B")
    assert len(em_b) == (1 if segue else 0), f"o redirecionamento {codigo} {'deveria' if segue else 'nao deveria'} ser seguido"
    for pedido in em_b:
        assert _vazou(pedido, CHAMADORES[chamador]["chave"]) == {}, f"o host B recebeu a chave de {chamador} no {codigo}: {sorted(_vazou(pedido, CHAMADORES[chamador]['chave']))}"


@pytest.mark.parametrize("chamador,codigo", SEGUIDOS, ids=IDS_SEGUIDOS)
def test_a_caller_redirected_to_another_host_still_follows_it_and_keeps_what_is_not_a_key(visto_chamadores, chamador, codigo):
    """GREEN before and after: the redirect is followed, the caller ends with the same result, and what is not a credential (Accept, the
    client id of the app, User-Agent) still reaches the other host; the method and the body are urllib's own (a POST becomes a GET with none)."""
    caso = visto_chamadores[f"outro-host/{chamador}/{codigo}"]
    dados = CHAMADORES[chamador]
    assert [(h["servidor"], h["caminho"].split("?")[0]) for h in caso["visto"]] == [("A", dados["caminho"]), ("B", "/fim")]
    _confere_o_resultado(chamador, caso["resposta"])
    em_b = _de(caso, "B")[0]
    assert em_b["metodo"] == "GET" and em_b["corpo"] == "" and "content-type" not in em_b["cabecalhos"]
    assert "user-agent" in em_b["cabecalhos"]
    for nome, valor in dados["comuns"].items():
        assert em_b["cabecalhos"].get(nome) == valor, nome


@pytest.mark.parametrize("chamador", list(CHAMADORES))
def test_a_destination_that_needs_the_key_gets_a_401_and_the_caller_says_its_usual_error(visto_chamadores, chamador):
    """RED before U22i: the key reached the destination, which was happy, and the call worked. A provider that needed the key at a host
    it was redirected to stops working: the caller reports the HTTP error it always reports for a 401, and the key stays with the first host."""
    caso = visto_chamadores[f"exige-chave/{chamador}"]
    assert [(h["servidor"], h["caminho"]) for h in _de(caso, "B")] == [("B", "/fim")]
    assert _vazou(_de(caso, "B")[0], CHAMADORES[chamador]["chave"]) == {}
    assert caso["resposta"] == {"erro": _erro_de_401(chamador, visto_chamadores["_bases"])}


# ---- a redirect to the SAME netloc -----------------------------------------------------------------------------------------------


@pytest.mark.parametrize("chamador,codigo", SEGUIDOS, ids=IDS_SEGUIDOS)
def test_a_caller_redirected_to_the_same_netloc_keeps_its_key(visto_chamadores, chamador, codigo):
    """GREEN before and after: the host that got the key first is the one that gets it again."""
    caso = visto_chamadores[f"mesmo-netloc/{chamador}/{codigo}"]
    dados = CHAMADORES[chamador]
    assert _de(caso, "B") == []
    assert [h["caminho"].split("?")[0] for h in _de(caso, "A")] == [dados["caminho"], "/fim"]
    for pedido in _de(caso, "A"):
        assert pedido["cabecalhos"][dados["cabecalho"]] == dados["valor"]
    _confere_o_resultado(chamador, caso["resposta"])


@pytest.mark.parametrize("chamador", list(CHAMADORES))
def test_a_relative_redirect_stays_on_the_netloc_and_keeps_the_key(visto_chamadores, chamador):
    """GREEN before and after: `Location: /fim` is resolved against the URL of the request, so it is the same netloc."""
    caso = visto_chamadores[f"relativo/{chamador}"]
    dados = CHAMADORES[chamador]
    assert _de(caso, "B") == [] and [h["caminho"].split("?")[0] for h in _de(caso, "A")] == [dados["caminho"], "/fim"]
    assert _de(caso, "A")[1]["cabecalhos"][dados["cabecalho"]] == dados["valor"]
    _confere_o_resultado(chamador, caso["resposta"])


# ---- the codes urllib does not follow --------------------------------------------------------------------------------------------


@pytest.mark.parametrize("chamador,codigo", NAO_SEGUIDOS, ids=IDS_NAO_SEGUIDOS)
def test_a_post_with_307_or_308_is_not_followed_and_each_module_says_its_own_error(visto_chamadores, chamador, codigo):
    """GREEN before and after: urllib raises HTTPError for a POST 307/308 (the body would have to be sent again); the other host is never
    asked, and the HTTP error is wrapped the way each module always wrapped it."""
    bases = visto_chamadores["_bases"]
    esperado = {
        "gemini": f"VoiceError: provider=gemini: HTTP {codigo} from {bases['A']}/v1beta/interactions\nok",
        "voice_clone": f"CloneVoiceError: provider=voicestudio: HTTP {codigo}: ok",
        "dub_create": "VoiceStudioError: /dub/upload não devolveu JSON: ok",  # `default_transport` returns the 3xx as a status, and 3xx is not >= 400
    }[chamador]
    for onde in ("outro-host", "mesmo-netloc"):
        caso = visto_chamadores[f"{onde}/{chamador}/{codigo}"]
        assert [(h["servidor"], h["metodo"]) for h in caso["visto"]] == [("A", "POST")]
        assert caso["resposta"] == {"erro": esperado}
