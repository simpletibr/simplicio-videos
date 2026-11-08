"""U22j (golden): destino LOOPBACK nunca passa por proxy.

DEFEITO (segurança; achado dos revisores da U22d e da U22c). O urllib honra `http_proxy`/`https_proxy`/`no_proxy` do ambiente, e `no_proxy`
só casa NOMES escritos por extenso: não entende CIDR (`127.0.0.0/8`), não casa `127.0.0.1` com `localhost`, não casa `[::1]`. Com um proxy no
ambiente e uma base loopback (o `http://127.0.0.1:3900` do VoiceStudio, o `http://localhost:PORT` do mock do Gemini, um `http://[::1]:PORT`),
o pedido ia AO PROXY: ele recebia, em claro, o `Authorization: Bearer ...` (ou o `x-goog-api-key`) e o TEXTO das falas, e o app local recebia
0 pedidos; a mensagem que o usuário via ("backend not reachable at http://127.0.0.1:3900 ...") apontava o lugar errado. Um proxy NUNCA alcança o
loopback do cliente (ele conectaria no loopback DELE): mandar loopback a um proxy é sempre errado e ainda vaza o conteúdo.
Quem chama: `rede.request` (adaptadores do swap, Openverse) e `rede.urlopen_seguro` (a voz do Gemini em voice.py, voice_clone.voicestudio e
voicestudio.default_transport, que a U22i pôs no lugar do `urlopen`).

COMO O TESTE RODA. Um processo filho limpo (`python -I`, só as variáveis de proxy que o cenário pede) sobe um PROXY FALSO vivo (registra todo
pedido: HTTP em forma absoluta e CONNECT, com cabeçalhos e corpo) e um APP FALSO vivo (127.0.0.1; também 127.0.0.2 e [::1] quando a máquina
tem), e chama os módulos de verdade, do jeito que o produto chama (a chave no ambiente, a base no ambiente ou no argumento). O filho só conecta
em loopback e não tem DNS: o único nome que ele resolve é `localhost` (com ou sem o ponto final, em qualquer caixa), então um destino remoto de
mentira (`studio.invalid`, `evil.example`) só é alcançado POR UM PROXY, e um cliente que tente resolvê-lo sozinho aparece em `resolvidos`. O
proxy responde por um destino remoto (200, o mesmo corpo que o app daria) e recusa com 403 um destino loopback (ele não alcança o loopback do
cliente). O bloqueio de sockets do pytest continua ligado no processo do teste. O filho roda a tabela inteira uma vez; cada teste lê a sua linha.

VERMELHO antes da correção (o proxy recebe o pedido, com a chave e o texto, e o app 0): `http_proxy` sozinho; `http_proxy` com
`no_proxy=localhost`, com CIDR e com `NO_PROXY` em maiúsculas (o destino `127.0.0.1`); `HTTP_PROXY` em maiúsculas; os destinos `127.0.0.2`,
`[::1]` e `[::ffff:127.0.0.1]` (nenhum `no_proxy` de nome os casa); um https loopback com `https_proxy` (o proxy recebe um CONNECT); e, para
os quatro chamadores, tudo isso.
VERDE antes e depois (o que NÃO muda): sem proxy; `no_proxy=*`; `no_proxy=localhost,127.0.0.1` (o destino escrito por extenso) e
`no_proxy=localhost` para o destino `localhost`; `https_proxy` sozinho com uma base http; um destino que NÃO é loopback (um nome de mentira
resolvido só pelo proxy) continua indo ao proxy, com a chave, e o chamador continua dando certo; um destino remoto DISFARÇADO de loopback
(`127.0.0.1@evil.example`, `evil.example#@127.0.0.1`, `127.0.0.1.evil.example`, `localhost.evil.example`, `[::1]@evil.example`, escape
percentual, barra invertida) continua indo ao proxy; um https remoto continua abrindo o túnel; um redirecionamento a partir de um destino
remoto continua no proxy em todos os saltos (o salto para o loopback vai ao proxy: o servidor remoto não consegue mandar o cliente falar com o
próprio loopback), e a credencial continua saindo no salto para outro netloc.
REGRA DO REDIRECIONAMENTO (decisão da U22j): o opener é escolhido UMA vez, pela URL em que a chamada começa, e vale para todos os saltos. Um
destino loopback segue o redirecionamento sem proxy; se o salto sai do loopback para um nome remoto, esse salto também vai sem proxy (o cliente
tenta resolver o nome sozinho: aparece em `resolvidos`, o proxy não vê nada) e a credencial já saiu pela regra da U22g (outro netloc).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

from helpers import ROOT

CHAVE_BEARER = "S3CR3T-voicestudio-loopback"
CHAVE_GOOGLE = "AIzaS3CR3T-gemini-loopback"
TEXTO = "fala-confidencial-do-usuario"  # a line of speech: it travels in the BODY of every call

PROXY = "http://127.0.0.1:{PX}"  # `{PX}` is the port of the fake proxy, which only the child knows
ENVS = {  # id -> the proxy variables of the scenario (and no other: the child clears every `*_proxy` first)
    "proxy": {"http_proxy": PROXY},
    "proxy+no_proxy=localhost": {"http_proxy": PROXY, "no_proxy": "localhost"},
    "proxy+no_proxy=CIDR": {"http_proxy": PROXY, "no_proxy": "127.0.0.0/8,localhost"},
    "proxy+NO_PROXY=localhost": {"http_proxy": PROXY, "NO_PROXY": "localhost"},
    "HTTP_PROXY": {"HTTP_PROXY": PROXY},
    "proxy+no_proxy=*": {"http_proxy": PROXY, "no_proxy": "*"},
    "proxy+no_proxy=localhost,127.0.0.1": {"http_proxy": PROXY, "no_proxy": "localhost,127.0.0.1"},
    "sem-proxy": {},
    "so-https_proxy": {"https_proxy": PROXY},
}
ENVS_HTTPS = {
    "https_proxy": {"https_proxy": PROXY},
    "https_proxy+no_proxy=localhost": {"https_proxy": PROXY, "no_proxy": "localhost"},
}
CHAMADORES = ("request", "gemini", "voice_clone", "vs_transport")
CAMINHO = {"request": "/v1/audio/speech", "gemini": "/v1beta/interactions", "voice_clone": "/v1/audio/speech", "vs_transport": "/mcp/"}
# destination id -> base URL (`{AP4}`: the port of the fake app on 127.0.0.1; `{AP2}`: on 127.0.0.2; `{AP6}`: on ::1)
DESTINOS = {
    "127.0.0.1": "http://127.0.0.1:{AP4}",
    "localhost": "http://localhost:{AP4}",
    "LOCALHOST": "http://LOCALHOST:{AP4}",
    "localhost.": "http://localhost.:{AP4}",
    "127.0.0.2": "http://127.0.0.2:{AP2}",
    "[::1]": "http://[::1]:{AP6}",
    "[::ffff:127.0.0.1]": "http://[::ffff:127.0.0.1]:{AP4}",
}
# What a user may have written that is NOT this machine, though a part of it looks like it. The real host of each one is `evil.example` (or a
# name that merely starts or ends like a loopback name): the proxy is the only way there, and it must stay the way.
DISFARCADOS = {
    "userinfo-127.0.0.1": "http://127.0.0.1@evil.example:{AP4}",
    "userinfo-localhost": "http://localhost@evil.example:{AP4}",
    "userinfo-::1": "http://[::1]@evil.example:{AP4}",
    "userinfo-com-porta": "http://127.0.0.1:80@evil.example:{AP4}",
    "fragmento": "http://evil.example:{AP4}#@127.0.0.1",
    "127.0.0.1.evil.example": "http://127.0.0.1.evil.example:{AP4}",
    "localhost.evil.example": "http://localhost.evil.example:{AP4}",
    "LOCALHOST.EVIL.EXAMPLE": "http://LOCALHOST.EVIL.EXAMPLE:{AP4}",
    "127.evil.example": "http://127.evil.example:{AP4}",
    "termina-em-localhost": "http://evillocalhost:{AP4}",
    "escape-percentual": "http://127.0.0.1%2eevil.example:{AP4}",
    "barra-invertida": "http://evil.example\\@127.0.0.1:{AP4}",
}
REMOTO = "http://studio.invalid:{AP4}"  # a name nobody resolves: only the fake proxy answers for it


def _casos() -> list[dict]:
    """The scenarios. A route is [status, Location] and `{AP4}` in a Location is the port of the fake app; the key of `rotas` is "<who answers>
    <path>" (`app`, or `proxy` for the fake proxy answering as a remote host)."""
    casos = []

    def novo(cid, classe, chamador, destino, base, envid, envs=ENVS, **extra):
        casos.append({"id": cid, "classe": classe, "chamador": chamador, "destino": destino, "base": base, "envid": envid,
                      "env": envs[envid], **extra})

    for chamador in CHAMADORES:  # the four callers against the two usual spellings, in every environment
        for envid in ENVS:
            for destino in ("127.0.0.1", "localhost"):
                novo(f"{chamador}/{envid}/{destino}", "loopback", chamador, destino, DESTINOS[destino], envid)
    for chamador in ("request", "vs_transport"):  # the other spellings of this machine, where no name in `no_proxy` helps
        for envid in ("proxy", "proxy+no_proxy=localhost"):
            for destino in ("LOCALHOST", "localhost.", "127.0.0.2", "[::1]", "[::ffff:127.0.0.1]"):
                novo(f"{chamador}/{envid}/{destino}", "loopback", chamador, destino, DESTINOS[destino], envid)
    for envid in ("proxy", "proxy+no_proxy=localhost"):  # voice_clone and the Gemini voice only where the product lets the base through
        for destino in ("LOCALHOST", "127.0.0.2", "[::1]"):
            novo(f"voice_clone/{envid}/{destino}", "loopback", "voice_clone", destino, DESTINOS[destino], envid)
        for destino in ("LOCALHOST", "[::1]"):
            novo(f"gemini/{envid}/{destino}", "loopback", "gemini", destino, DESTINOS[destino], envid)
    for chamador in ("request", "voice_clone", "vs_transport"):  # not loopback: the proxy is still the way
        for envid in ("proxy", "proxy+no_proxy=localhost", "proxy+no_proxy=CIDR", "proxy+NO_PROXY=localhost"):
            novo(f"{chamador}/{envid}/studio.invalid", "remoto", chamador, "studio.invalid", REMOTO, envid)
    for chamador in ("request", "voice_clone", "vs_transport"):  # not loopback either, however much it looks like it
        for did, base in DISFARCADOS.items():
            novo(f"{chamador}/proxy/{did}", "disfarcado", chamador, did, base, "proxy")
    for chamador in ("request", "gemini"):  # https: the proxy would be asked for a tunnel (CONNECT)
        for envid in ENVS_HTTPS:
            for destino, base in (("127.0.0.1", "https://127.0.0.1:{AP4}"), ("localhost", "https://localhost:{AP4}"),
                                  ("studio.invalid", "https://studio.invalid")):
                novo(f"{chamador}/{envid}/https-{destino}", "https-remoto" if destino == "studio.invalid" else "https-loopback", chamador,
                     destino, base, envid, ENVS_HTTPS)
    for chamador in ("request", "vs_transport"):  # redirects: which opener a hop gets
        a = f"app {CAMINHO[chamador]}"
        novo(f"{chamador}/redirect/loopback-para-remoto", "redirect", chamador, "127.0.0.1", DESTINOS["127.0.0.1"], "proxy",
             rotas={a: [302, "http://studio.invalid:{AP4}/fim"]})
        novo(f"{chamador}/redirect/remoto-para-loopback", "redirect", chamador, "studio.invalid", REMOTO, "proxy",
             rotas={f"proxy {CAMINHO[chamador]}": [302, "http://127.0.0.1:{AP4}/fim"]})
        novo(f"{chamador}/redirect/loopback-para-outro-netloc", "redirect", chamador, "127.0.0.1", DESTINOS["127.0.0.1"], "proxy",
             rotas={a: [302, "http://localhost:{AP4}/fim"]})
        novo(f"{chamador}/redirect/loopback-mesmo-netloc", "redirect", chamador, "127.0.0.1", DESTINOS["127.0.0.1"], "proxy",
             rotas={a: [302, "/fim"]})
    return casos


_FILHO = r'''
import http.server
import ipaddress
import json
import os
import socket
import socketserver
import sys
import tempfile
import threading
from pathlib import Path
from urllib.parse import urlsplit

src, casos, chave_bearer, chave_google, texto = sys.argv[1], json.loads(sys.argv[2]), sys.argv[3], sys.argv[4], sys.argv[5]
sys.path.insert(0, src)

PERMITIDOS = {"127.0.0.1", "127.0.0.2", "::1", "::ffff:127.0.0.1"}
_connect, _getaddrinfo = socket.socket.connect, socket.getaddrinfo
RESOLVIDOS = []


def _so_loopback(self, endereco):
    if not (isinstance(endereco, tuple) and endereco[0] in PERMITIDOS):
        raise AssertionError(f"fora do loopback: {endereco!r}")
    return _connect(self, endereco)


def _resolve(host, *args, **kw):
    """The world of this test: `localhost` (any case, with or without the final dot) is 127.0.0.1; an address literal is itself; no other name
    resolves (there is no DNS here), and every name that is asked for is written down."""
    nome = host.decode() if isinstance(host, bytes) else host
    RESOLVIDOS.append(nome)
    if nome.lower() in ("localhost", "localhost."):
        return _getaddrinfo("127.0.0.1", *args, **kw)
    if nome in PERMITIDOS:
        return _getaddrinfo(host, *args, **kw)
    raise socket.gaierror(socket.EAI_NONAME, "o teste nao tem DNS: " + nome)


socket.socket.connect = _so_loopback
socket.getaddrinfo = _resolve

WAV = "RIFFfake-wav-bytes"
GEMINI = json.dumps({"steps": [{"type": "model_output", "content": [
    {"type": "audio", "mime_type": "audio/wav", "data": __import__("base64").b64encode(WAV.encode()).decode()}]}]})
CORPOS = {"/v1/audio/speech": WAV, "/v1beta/interactions": GEMINI}
APP_VISTO, PROXY_VISTO, CONEXOES = [], [], []
ROTAS = {"app": {}, "proxy": {}}
BASES = {}


def local(host):
    """The proxy's view of a target: this machine of the CLIENT, which it can never reach."""
    host = (host or "").lower()
    if host in ("localhost", "localhost."):
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return (ip.ipv4_mapped or ip).is_loopback if ip.version == 6 else ip.is_loopback


class App(http.server.BaseHTTPRequestHandler):
    timeout = 5  # a connection that never sends a request does not hold a thread for ever

    def setup(self):
        CONEXOES.append(self.server.rotulo)
        super().setup()

    def handle(self):
        if self.connection.recv(1, socket.MSG_PEEK) == b"\x16":  # a TLS hello: this app speaks plain http, so it hangs up and the handshake fails at once
            return
        super().handle()

    def _atende(self):
        tamanho = int(self.headers.get("Content-Length") or 0)
        corpo = self.rfile.read(tamanho).decode("latin-1") if tamanho else ""
        APP_VISTO.append({"servidor": self.server.rotulo, "metodo": self.command, "caminho": self.path,
                          "cabecalhos": {k.lower(): v for k, v in self.headers.items()}, "corpo": corpo})
        caminho = self.path.split("?")[0]
        status, destino = ROTAS["app"].get(caminho, (200, None))
        dados = CORPOS.get(caminho, "{}").encode("latin-1")
        self.send_response(status)
        if destino:
            self.send_header("Location", destino)
        self.send_header("Content-Length", str(len(dados)))
        self.end_headers()
        self.wfile.write(dados)

    do_GET = do_POST = _atende

    def log_message(self, *args):
        pass


class Proxy(socketserver.StreamRequestHandler):
    """A forward proxy that only writes down what it is asked and answers for a remote name; the loopback of its client is out of its reach."""

    def handle(self):
        linha = self.rfile.readline(65537)
        if not linha:
            return
        metodo, alvo, _ = linha.decode("latin-1").rstrip().split(" ", 2)
        cab = {}
        while True:
            l = self.rfile.readline(65537)
            if l in (b"\r\n", b"\n", b""):
                break
            nome, _, valor = l.decode("latin-1").partition(":")
            cab[nome.strip().lower()] = valor.strip()
        corpo = b""
        if metodo != "CONNECT":
            n = int(cab.get("content-length") or 0)
            corpo = self.rfile.read(n) if n else b""
        PROXY_VISTO.append({"metodo": metodo, "alvo": alvo, "authorization": cab.get("authorization"),
                            "x-goog-api-key": cab.get("x-goog-api-key"), "corpo": corpo.decode("latin-1")})
        destino, status, corpo_resposta = None, 502, "proxy: sem tunel"
        if metodo != "CONNECT":
            partes = urlsplit(alvo)
            caminho = partes.path or "/"
            if local(partes.hostname):
                status, corpo_resposta = 403, "proxy: o loopback do cliente nao e alcancavel daqui"
            else:
                status, destino = ROTAS["proxy"].get(caminho, (200, None))
                corpo_resposta = CORPOS.get(caminho, "{}")
        dados = corpo_resposta.encode("latin-1")
        extra = f"Location: {destino}\r\n" if destino else ""
        self.wfile.write(f"HTTP/1.1 {status} X\r\n{extra}Content-Length: {len(dados)}\r\nConnection: close\r\n\r\n".encode() + dados)


class Servidor6(http.server.ThreadingHTTPServer):
    address_family = socket.AF_INET6


class Quieto(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def sobe(classe, endereco, handler, rotulo):
    try:
        srv = classe(endereco, handler)
    except OSError:
        return None
    srv.rotulo = rotulo
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


app4 = sobe(http.server.ThreadingHTTPServer, ("127.0.0.1", 0), App, "127.0.0.1")
app2 = sobe(http.server.ThreadingHTTPServer, ("127.0.0.2", 0), App, "127.0.0.2")
app6 = sobe(Servidor6, ("::1", 0), App, "::1")
proxy = sobe(Quieto, ("127.0.0.1", 0), Proxy, "proxy")
PORTAS = {"AP4": app4.server_address[1], "AP2": (app2 or app4).server_address[1], "AP6": (app6 or app4).server_address[1],
          "PX": proxy.server_address[1]}

from simplicio_video import rede, voice, voice_clone, voicestudio

pasta = Path(tempfile.mkdtemp())


def chama(chamador, base, n):
    dst = pasta / f"saida-{n}.wav"
    if chamador == "request":
        r = rede.request("POST", base + "/v1/audio/speech", headers={"Authorization": "Bearer " + chave_bearer},
                         json_body={"input": texto}, timeout=10)
        return {"status": r.status, "corpo": r.body.decode("latin-1")}
    if chamador == "gemini":
        os.environ.update(GEMINI_API_KEY=chave_google, SIMPLICIO_GEMINI_BASE=base + "/v1beta")
        voice._gemini({"model": "gemini-mock", "voice": "Kore", "estilo": "calmo"}, texto, dst)
        return {"arquivo": dst.read_bytes().decode("latin-1")}
    if chamador == "voice_clone":
        os.environ.update(VOICESTUDIO_API_KEY=chave_bearer, VOICESTUDIO_URL=base)
        voice_clone.voicestudio({"model": "omnivoice", "voice": "me"}, texto, dst)
        return {"arquivo": dst.read_bytes().decode("latin-1")}
    status, _, corpo = voicestudio.default_transport(
        "POST", base + "/mcp/", json.dumps({"input": texto}).encode(),
        {"Authorization": "Bearer " + chave_bearer, "Content-Type": "application/json"}, 10)
    return {"status": status, "corpo": corpo.decode("latin-1")}


saida = {"_tem": {"127.0.0.2": app2 is not None, "ipv6": app6 is not None}, "_portas": PORTAS}
for n, caso in enumerate(casos):
    for lista in (APP_VISTO, PROXY_VISTO, CONEXOES, RESOLVIDOS):
        lista.clear()
    for quem in ROTAS:
        ROTAS[quem].clear()
    for chave, (status, destino) in caso.get("rotas", {}).items():
        quem, caminho = chave.split(" ", 1)
        ROTAS[quem][caminho] = (status, destino.format(**PORTAS))
    for var in list(os.environ):
        if var.lower().endswith("_proxy") or var in ("REQUEST_METHOD", "GEMINI_API_KEY", "SIMPLICIO_GEMINI_BASE", "VOICESTUDIO_URL",
                                                     "VOICESTUDIO_API_KEY", "OMNIVOICE_URL", "OMNIVOICE_API_KEY"):
            del os.environ[var]
    os.environ.update({k: v.format(**PORTAS) for k, v in caso["env"].items()})
    base = caso["base"].format(**PORTAS)
    try:
        resposta = chama(caso["chamador"], base, n)
    except BaseException as e:  # VoiceError and CloneVoiceError are SystemExit: the test reads the error
        resposta = {"erro": f"{type(e).__name__}: {e}"}
    saida[caso["id"]] = {"resposta": resposta, "app": list(APP_VISTO), "proxy": list(PROXY_VISTO), "conexoes": list(CONEXOES),
                         "resolvidos": list(RESOLVIDOS)}
print(json.dumps(saida))
'''


def _ambiente_limpo() -> dict:
    """No proxy variable, no SIMPLICIO_OFFLINE: each scenario of the child sets the variables it is about."""
    return {k: os.environ[k] for k in ("PATH", "SYSTEMROOT", "TEMP", "TMP", "TMPDIR", "HOME", "LANG", "LC_ALL") if k in os.environ}


CASOS = _casos()
POR_ID = {c["id"]: c for c in CASOS}


@pytest.fixture(scope="module")
def visto() -> dict:
    r = subprocess.run([sys.executable, "-I", "-c", _FILHO, str(ROOT / "src"), json.dumps(CASOS), CHAVE_BEARER, CHAVE_GOOGLE, TEXTO],
                       capture_output=True, text=True, env=_ambiente_limpo(), timeout=300)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout.strip().splitlines()[-1])


def _ids(classe: str) -> list[str]:
    return [c["id"] for c in CASOS if c["classe"] == classe]


def _vazou(registro: dict) -> list[str]:
    """What the fake proxy was handed that belongs to the caller of a LOOPBACK destination: a key, or the text of the speech."""
    achados = []
    for p in registro["proxy"]:
        for nome in ("authorization", "x-goog-api-key"):
            if p[nome] and (CHAVE_BEARER in p[nome] or CHAVE_GOOGLE in p[nome]):
                achados.append(f"{nome}={p[nome]}")
        if TEXTO in p["corpo"]:
            achados.append(f"corpo={p['corpo'][:60]!r}")
    return achados


def _pode_alcancar(caso: dict, visto: dict) -> bool:
    """Whether this machine can deliver a connection to the destination at all: a kernel without IPv6 cannot reach `[::1]`, and some systems
    have no 127.0.0.2. Where it cannot there is no app to receive the call: the fake proxy must still hear nothing, and the client must have
    tried the address itself (and failed)."""
    if caso["destino"] in ("[::1]", "[::ffff:127.0.0.1]"):
        return visto["_tem"]["ipv6"]
    if caso["destino"] == "127.0.0.2":
        return visto["_tem"]["127.0.0.2"]
    return True


def _resumo(registro: dict) -> str:
    return "; ".join(f"{p['metodo']} {p['alvo']} (chave/texto vazados: {bool(_vazou({'proxy': [p]}))})" for p in registro["proxy"]) or "nada"


# ---- the harness itself ---------------------------------------------------------------------------------------------------------


def test_the_scenarios_are_what_the_docstring_says():
    assert {c["classe"] for c in CASOS} == {"loopback", "remoto", "disfarcado", "https-loopback", "https-remoto", "redirect"}
    assert len(CASOS) == len(POR_ID), "ids repetidos"


def test_without_a_proxy_the_app_receives_the_call_and_the_fake_proxy_hears_nothing(visto):
    """GREEN before and after: the control of the harness (the callers reach the fake app, the fake proxy only hears what is sent to it)."""
    for chamador in CHAMADORES:
        r = visto[f"{chamador}/sem-proxy/127.0.0.1"]
        assert r["proxy"] == [] and len(r["app"]) == 1 and "erro" not in r["resposta"], (chamador, r)


def test_the_fake_proxy_is_alive_and_writes_down_what_it_is_sent(visto):
    """GREEN before and after: a remote name goes to the fake proxy, which answers for it and records the absolute-form request."""
    r = visto["request/proxy/studio.invalid"]
    (p,) = r["proxy"]
    assert p["metodo"] == "POST" and p["alvo"] == f"http://studio.invalid:{visto['_portas']['AP4']}/v1/audio/speech"
    assert p["authorization"] == f"Bearer {CHAVE_BEARER}" and TEXTO in p["corpo"]


# ---- a LOOPBACK destination never goes to a proxy ----------------------------------------------------------------------------------


@pytest.mark.parametrize("cid", _ids("loopback"))
def test_a_loopback_destination_never_sends_the_key_or_the_text_to_the_proxy(visto, cid):
    """RED before the fix wherever the environment proxy catches the call (the proxy is handed the key and the text, in the clear); GREEN before
    and after where it already did not (no proxy, `no_proxy=*`, the destination written in full in `no_proxy`)."""
    r = visto[cid]
    assert _vazou(r) == [] and r["proxy"] == [], f"o proxy recebeu: {_resumo(r)}"


@pytest.mark.parametrize("cid", _ids("loopback"))
def test_the_local_app_receives_the_call_once_with_the_key_and_the_text(visto, cid):
    """RED before the fix wherever the proxy caught the call (the app received 0 requests and the user was told the app was not reachable)."""
    caso, r = POR_ID[cid], visto[cid]
    if not _pode_alcancar(caso, visto):  # no IPv6 here (or no 127.0.0.2): there is no app at that address, and the call must fail on its own
        assert r["app"] == [] and "erro" in r["resposta"], f"o cliente devia ter tentado o endereco sozinho e falhado: {r['resposta']}"
        return
    assert len(r["app"]) == 1, f"o app recebeu {len(r['app'])} pedido(s); o proxy recebeu: {_resumo(r)}"
    pedido = r["app"][0]
    assert pedido["metodo"] == "POST" and pedido["caminho"] == CAMINHO[caso["chamador"]] and TEXTO in pedido["corpo"]
    chave = pedido["cabecalhos"].get("x-goog-api-key" if caso["chamador"] == "gemini" else "authorization")
    assert chave == (CHAVE_GOOGLE if caso["chamador"] == "gemini" else f"Bearer {CHAVE_BEARER}")
    assert "erro" not in r["resposta"], r["resposta"]


# ---- a destination that is NOT loopback keeps going the way it went -------------------------------------------------------------------


@pytest.mark.parametrize("cid", _ids("remoto"))
def test_a_remote_destination_still_goes_to_the_proxy_with_the_key(visto, cid):
    """GREEN before and after: the proxy of the environment (and `no_proxy` as urllib reads it) is exactly what it was for a name that is not
    this machine. The proxy answers for it and the caller succeeds through it."""
    caso, r = POR_ID[cid], visto[cid]
    assert len(r["proxy"]) == 1 and r["app"] == [], f"o proxy recebeu: {_resumo(r)}"
    (p,) = r["proxy"]
    assert p["metodo"] == "POST" and p["alvo"].startswith("http://studio.invalid:") and p["alvo"].endswith(CAMINHO[caso["chamador"]])
    assert p["authorization"] == f"Bearer {CHAVE_BEARER}" and TEXTO in p["corpo"]
    assert "erro" not in r["resposta"], r["resposta"]
    assert "studio.invalid" not in r["resolvidos"], "o cliente tentou resolver o nome sozinho: o proxy foi dispensado"


# `http://[::1]@evil.example` is not a URL the newest parsers read: Python 3.13 (and the releases of 3.9 to 3.12 that took the fix for
# CVE-2025-0938) raise ValueError from `urlsplit` when a netloc has brackets in the user name and none around the host, while `Request` is being
# built, so nothing is sent at all. Older ones read it as a user name `[::1]` at `evil.example` and hand it to the proxy. Both are safe; what must
# never happen is the call going straight to a connection.
O_PARSER_PODE_RECUSAR = {"userinfo-::1"}


@pytest.mark.parametrize("cid", _ids("disfarcado"))
def test_a_remote_destination_disguised_as_loopback_still_goes_to_the_proxy(visto, cid):
    """GREEN before and after: only the REAL host decides. A user name that looks like an address (`127.0.0.1@evil.example`), a fragment, a name
    that starts or ends like a loopback name, an escape or a backslash do not make a remote destination loopback: it keeps the proxy."""
    r = visto[cid]
    assert r["app"] == [] and r["conexoes"] == [], f"o app recebeu uma conexao: {r['app']}"
    assert not any(nome in r["resolvidos"] for nome in ("evil.example", "127.0.0.1.evil.example", "localhost.evil.example")), r["resolvidos"]
    if cid.split("/")[-1] in O_PARSER_PODE_RECUSAR and r["proxy"] == []:
        assert "ValueError" in r["resposta"]["erro"], r["resposta"]  # the parser refused it before anything was sent
        return
    assert len(r["proxy"]) == 1, f"o proxy recebeu: {_resumo(r)}"
    assert r["proxy"][0]["metodo"] == "POST" and r["proxy"][0]["authorization"] == f"Bearer {CHAVE_BEARER}"


# ---- https: the proxy is asked for a tunnel -------------------------------------------------------------------------------------


@pytest.mark.parametrize("cid", _ids("https-loopback"))
def test_an_https_loopback_destination_does_not_ask_the_proxy_for_a_tunnel(visto, cid):
    """RED before the fix: the proxy is asked for `CONNECT 127.0.0.1:PORT` (inside the tunnel the key would be encrypted, but the proxy cannot
    reach the loopback of its client: the call never gets to the app, and the user is told the app is down). After, the client connects to the
    app itself (the app is plain http, so it hangs up on the TLS hello and the handshake fails: one connection is what is asserted)."""
    r = visto[cid]
    assert r["proxy"] == [], f"o proxy recebeu: {_resumo(r)}"
    assert r["conexoes"] == ["127.0.0.1"], r["conexoes"]


@pytest.mark.parametrize("cid", _ids("https-remoto"))
def test_an_https_remote_destination_still_asks_the_proxy_for_a_tunnel(visto, cid):
    """GREEN before and after: `CONNECT studio.invalid:443` goes to the proxy of the environment, whatever `no_proxy=localhost` says."""
    r = visto[cid]
    assert [(p["metodo"], p["alvo"]) for p in r["proxy"]] == [("CONNECT", "studio.invalid:443")], _resumo(r)
    assert r["conexoes"] == [] and "studio.invalid" not in r["resolvidos"]


# ---- redirects: the opener is chosen once, for the URL the call starts at --------------------------------------------------------------


@pytest.mark.parametrize("chamador", ["request", "vs_transport"])
def test_a_redirect_from_loopback_to_another_netloc_of_loopback_stays_off_the_proxy_and_drops_the_key(visto, chamador):
    """RED before the fix (the first hop already went to the proxy). After: both hops reach the app, the second without the credential (the
    netloc changed: `127.0.0.1:P` to `localhost:P`, the rule of U22g), and the proxy hears nothing."""
    r = visto[f"{chamador}/redirect/loopback-para-outro-netloc"]
    assert r["proxy"] == [], f"o proxy recebeu: {_resumo(r)}"
    assert [(p["metodo"], p["caminho"]) for p in r["app"]] == [("POST", CAMINHO[chamador]), ("GET", "/fim")]
    assert r["app"][0]["cabecalhos"]["authorization"] == f"Bearer {CHAVE_BEARER}"
    assert "authorization" not in r["app"][1]["cabecalhos"] and "erro" not in r["resposta"]


@pytest.mark.parametrize("chamador", ["request", "vs_transport"])
def test_a_redirect_inside_the_same_netloc_of_loopback_keeps_the_key_and_stays_off_the_proxy(visto, chamador):
    """RED before the fix (the first hop already went to the proxy). After: the relative redirect stays on the same netloc, so the credential
    goes on (the rule of U22g), and the proxy hears nothing."""
    r = visto[f"{chamador}/redirect/loopback-mesmo-netloc"]
    assert r["proxy"] == [], f"o proxy recebeu: {_resumo(r)}"
    assert [(p["metodo"], p["caminho"]) for p in r["app"]] == [("POST", CAMINHO[chamador]), ("GET", "/fim")]
    assert all(p["cabecalhos"].get("authorization") == f"Bearer {CHAVE_BEARER}" for p in r["app"]) and "erro" not in r["resposta"]


@pytest.mark.parametrize("chamador", ["request", "vs_transport"])
def test_a_redirect_from_loopback_to_a_remote_name_leaves_the_proxy_out_by_the_rule_of_the_first_destination(visto, chamador):
    """RED before the fix (the first hop went to the proxy). After, by the rule `the opener of the first destination holds for every hop`:
    the first hop reaches the app, the proxy hears nothing, and the hop to the remote name is tried without a proxy (the client resolves the
    name itself and, with no DNS here, fails: the error is the client's own). The credential is not what goes out: the netloc changed."""
    r = visto[f"{chamador}/redirect/loopback-para-remoto"]
    assert r["proxy"] == [], f"o proxy recebeu: {_resumo(r)}"
    assert [(p["metodo"], p["caminho"]) for p in r["app"]] == [("POST", CAMINHO[chamador])]
    assert "studio.invalid" in r["resolvidos"] and "erro" in r["resposta"], r


@pytest.mark.parametrize("chamador", ["request", "vs_transport"])
def test_a_redirect_from_a_remote_name_to_loopback_stays_on_the_proxy_all_the_way(visto, chamador):
    """GREEN before and after: a call that starts at a remote name keeps the opener of the environment for every hop, so a remote server cannot
    make the client talk to its own loopback (the hop to `127.0.0.1` goes to the proxy, which cannot reach it: 403) and the app hears nothing.
    The credential stays with the first netloc."""
    r = visto[f"{chamador}/redirect/remoto-para-loopback"]
    assert r["app"] == [] and len(r["proxy"]) == 2, f"o proxy recebeu: {_resumo(r)}"
    primeiro, segundo = r["proxy"]
    assert primeiro["alvo"].startswith("http://studio.invalid:") and primeiro["authorization"] == f"Bearer {CHAVE_BEARER}"
    assert segundo["alvo"] == f"http://127.0.0.1:{visto['_portas']['AP4']}/fim" and segundo["authorization"] is None
    assert segundo["metodo"] == "GET"
    assert r["resposta"].get("status") == 403
