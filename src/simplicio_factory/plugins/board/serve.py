"""Servidor local do quadro (#89, épico #81): `board serve` mostra a página do `board build` em 127.0.0.1.

Biblioteca padrão (`http.server`), sem rede externa e sem LLM. Escuta só em 127.0.0.1 (ou localhost); outro host é
recusado. As únicas escritas são `POST /comment` e `POST /review`, que reusam `service.comentar` e `service.revisar`
(#86) dentro de uma trava, para que dois pedidos simultâneos não se atropelem. Nenhuma rota muda `state` de item nem
orçamento, e nenhuma aprova gasto: qualquer outro caminho é 404.

Proteção: um token aleatório por sessão, impresso no terminal e embutido no formulário. Sem token, ou com token
errado: 403. `Host` ou `Origin` que não sejam localhost/127.0.0.1: 403. O token barra páginas de terceiros abertas
no mesmo navegador; não é autenticação de usuário.
"""

from __future__ import annotations

import html as _html
import http.server
import re
import secrets
import threading
from pathlib import Path

from simplicio_factory.contracts.json_store import JsonStore
from simplicio_factory.plugins.board import html as quadro_html
from simplicio_factory.plugins.board import service
from simplicio_factory.plugins.board.service import BoardError

HOST = "127.0.0.1"
HOSTS_LOCAIS = frozenset({"127.0.0.1", "localhost"})
PORTA_PADRAO = 8765
LIMITE_CORPO = 64 * 1024
TOKEN_BYTES = 24
ROTAS_POST = frozenset({"/comment", "/review"})
AVISOS = {"comentario": "Comentário registrado.", "revisao": "Revisão registrada."}
# Texto da página do build estático que deixa de valer no servidor (a página agora aceita comentário e revisão).
TEXTO_ESTATICO = "Esta página só mostra o estado: comentários e revisão são feitos pela CLI."
TEXTO_SERVIDOR = "Comentários e revisão também podem ser feitos aqui, no formulário acima."
CSP = (
    "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; "
    "form-action 'self'; base-uri 'none'; frame-ancestors 'none'"
)
_HEX = re.compile(r"(?:%[0-9A-Fa-f]{2})+")

ESTILO_FORMULARIO = """<style>
.acoes { margin: 12px 0; padding: 12px; background: var(--superficie); border: 1px solid var(--borda); border-radius: 8px; }
.acao { display: grid; gap: 8px; margin: 0 0 16px; }
.acao label { display: grid; gap: 4px; font-size: 0.9rem; }
.acao input, .acao textarea { font: inherit; color: var(--texto); background: var(--fundo); border: 1px solid var(--borda); border-radius: 6px; padding: 6px 8px; width: 100%; min-width: 0; }
.acao button { font: inherit; justify-self: start; padding: 6px 14px; border: 1px solid var(--link); border-radius: 6px; background: var(--superficie); color: var(--link); cursor: pointer; }
.acao input:focus-visible, .acao textarea:focus-visible, .acao button:focus-visible { outline: 3px solid var(--foco); outline-offset: 2px; }
.aviso { font-weight: 600; }
</style>"""


class _Recusado(Exception):
    """Pedido que não passa na guarda de host, origem ou token: vira 403 com a mensagem."""


def checa_host(host: str) -> str:
    """Endereço de escuta. Só loopback: 127.0.0.1 ou localhost (que vira 127.0.0.1). Qualquer outro é recusado."""
    if host in HOSTS_LOCAIS:
        return HOST
    raise BoardError(f"o servidor só escuta em {HOST} (ou localhost); {host!r} foi recusado")


def _e(texto) -> str:
    return _html.escape(str(texto), quote=True)


def _decodifica(texto: str) -> str:
    """Percent-decoding de application/x-www-form-urlencoded. Sem urllib: o plugin não importa esse módulo."""
    texto = texto.replace("+", " ")
    partes, pos = [], 0
    for casa in _HEX.finditer(texto):
        partes.append(texto[pos : casa.start()])
        partes.append(bytes.fromhex(casa.group(0).replace("%", "")).decode("utf-8", "replace"))
        pos = casa.end()
    partes.append(texto[pos:])
    return "".join(partes)


def _campos(texto: str) -> dict[str, str]:
    campos: dict[str, str] = {}
    for par in texto.split("&"):
        if par:
            nome, _, valor = par.partition("=")
            campos[_decodifica(nome)] = _decodifica(valor)
    return campos


def _host_local(valor: str, porta: int) -> bool:
    nome, _, porta_informada = valor.partition(":")
    return nome.lower() in HOSTS_LOCAIS and porta_informada in ("", str(porta))


def _origem_local(origem: str, porta: int) -> bool:
    esquema, sep, resto = origem.partition("://")
    return bool(sep) and esquema == "http" and _host_local(resto.split("/", 1)[0], porta)


def _bloco_formulario(home: Path, token: str, aviso: str | None) -> str:
    """Formulário de comentário e botões de revisão, para a faixa do topo. Todo texto vindo de fora passa por escape."""
    ids = sorted(item.id for item in JsonStore(home).list_items() if item is not None)
    sugestoes = "".join(f'<option value="{_e(item_id)}"></option>' for item_id in ids)
    texto_aviso = f'<p class="aviso" role="status">{_e(AVISOS[aviso])}</p>' if aviso in AVISOS else ""
    token_campo = f'<input type="hidden" name="token" value="{_e(token)}">'
    return (
        f"{ESTILO_FORMULARIO}"
        '<section class="acoes" aria-labelledby="acoes-titulo"><h2 id="acoes-titulo">Comentar e revisar</h2>'
        f"{texto_aviso}"
        f'<datalist id="itens">{sugestoes}</datalist>'
        '<form class="acao" method="post" action="/comment">'
        f"{token_campo}"
        '<label>Item <input name="item" list="itens" required autocomplete="off"></label>'
        '<label>Seu nome <input name="by" required maxlength="80" autocomplete="name"></label>'
        '<label>Comentário <textarea name="texto" rows="3" required></textarea></label>'
        '<button type="submit">Comentar</button>'
        "</form>"
        '<form class="acao" method="post" action="/review">'
        f"{token_campo}"
        '<label>Item <input name="item" list="itens" required autocomplete="off"></label>'
        '<label>Seu nome <input name="by" required maxlength="80" autocomplete="name"></label>'
        '<label>Nota (opcional) <input name="note" maxlength="500"></label>'
        '<button type="submit" name="decisao" value="approve">Aprovar</button>'
        '<button type="submit" name="decisao" value="changes">Pedir alterações</button>'
        "</form></section>"
    )


def pagina(home: Path, token: str, aviso: str | None = None) -> str:
    """A página do `board build` (#88) com o formulário acima do quadro. O build estático não muda."""
    base = quadro_html.construir(home, home.resolve()).replace(TEXTO_ESTATICO, TEXTO_SERVIDOR, 1)
    return base.replace("</header>", _bloco_formulario(home, token, aviso) + "</header>", 1)


def _pagina_de_erro(mensagem: str, token: str) -> str:
    return (
        '<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">'
        "<title>Quadro: pedido recusado</title></head><body>"
        f"<p>{_e(mensagem)}</p>"
        f'<p><a href="/?token={_e(token)}">Voltar ao quadro</a></p>'
        "</body></html>"
    )


class Servidor(http.server.ThreadingHTTPServer):
    """Servidor do quadro: guarda o token da sessão, a trava de escrita e o home do JsonStore."""

    daemon_threads = True

    def __init__(self, home, host: str, porta: int):
        self.home = Path(home)
        self.token = secrets.token_urlsafe(TOKEN_BYTES)
        self.trava = threading.Lock()
        super().__init__((checa_host(host), porta), _Pedido)


def criar(home, host: str = HOST, porta: int = PORTA_PADRAO) -> Servidor:
    """Liga o servidor (sem começar a atender). `porta=0` escolhe uma porta livre."""
    return Servidor(home, host, porta)


class _Pedido(http.server.BaseHTTPRequestHandler):
    server_version = "simplicio-board"

    def version_string(self) -> str:
        """Sem a versão do Python no cabeçalho Server."""
        return self.server_version

    def log_message(self, format, *args):  # noqa: A002 - assinatura da biblioteca
        """Silencioso: a URL de cada pedido leva o token, e o terminal não deve repeti-lo."""

    def do_GET(self):
        self._atende("GET")

    def do_POST(self):
        self._atende("POST")

    def _atende(self, metodo: str) -> None:
        corpo = b""
        if metodo == "POST":
            tamanho = self.headers.get("Content-Length", "0")
            if not tamanho.isdigit() or int(tamanho) > LIMITE_CORPO:
                self._envia(413, "pedido grande demais", tipo="text/plain; charset=utf-8")
                return
            corpo = self.rfile.read(int(tamanho))  # lido antes de responder: o cliente não fica preso
        try:
            self._roteia(metodo, corpo)
        except _Recusado as exc:
            self._envia(403, str(exc), tipo="text/plain; charset=utf-8")
        except Exception:  # resposta genérica: sem traceback para o navegador
            self._envia(500, "erro interno do quadro", tipo="text/plain; charset=utf-8")

    def _roteia(self, metodo: str, corpo: bytes) -> None:
        srv = self.server
        caminho, _, consulta = self.path.partition("?")
        campos = _campos(consulta if metodo == "GET" else corpo.decode("utf-8", "replace"))
        self._guarda_host_e_origem()

        if caminho != "/" and caminho not in ROTAS_POST:
            return self._envia(404, "não encontrado", tipo="text/plain; charset=utf-8")
        esperado = "GET" if caminho == "/" else "POST"
        if metodo != esperado:
            return self._envia(405, "método não permitido", tipo="text/plain; charset=utf-8", extra={"Allow": esperado})
        if not secrets.compare_digest(campos.get("token", "").encode("utf-8"), srv.token.encode("utf-8")):
            raise _Recusado("token ausente ou inválido: abra o endereço impresso no terminal")

        if metodo == "GET":
            with srv.trava:
                pagina_html = pagina(srv.home, srv.token, aviso=campos.get("aviso"))
            return self._envia(200, pagina_html)
        return self._escreve(caminho, campos)

    def _guarda_host_e_origem(self) -> None:
        porta = self.server.server_address[1]
        host = self.headers.get("Host")
        if host is None or not _host_local(host, porta):
            raise _Recusado("host externo recusado: o quadro só responde em localhost ou 127.0.0.1")
        origem = self.headers.get("Origin")
        if origem is not None and not _origem_local(origem, porta):
            raise _Recusado("origem externa recusada: o quadro só aceita pedidos de localhost ou 127.0.0.1")

    def _escreve(self, caminho: str, campos: dict[str, str]) -> None:
        srv = self.server
        item = campos.get("item", "")
        try:
            with srv.trava:
                if caminho == "/comment":
                    service.comentar(srv.home, item, campos.get("texto", ""), campos.get("by", ""))
                    aviso = "comentario"
                else:
                    service.revisar(
                        srv.home, item, campos.get("decisao", ""), campos.get("by", ""), campos.get("note") or None
                    )
                    aviso = "revisao"
        except BoardError as exc:
            return self._envia(400, _pagina_de_erro(str(exc), srv.token))
        return self._envia(303, b"", extra={"Location": f"/?token={srv.token}&aviso={aviso}"})

    def _envia(self, status: int, corpo, tipo: str = "text/html; charset=utf-8", extra: dict | None = None) -> None:
        dados = corpo if isinstance(corpo, bytes) else corpo.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(dados)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", CSP)
        for nome, valor in (extra or {}).items():
            self.send_header(nome, valor)
        self.end_headers()
        self.wfile.write(dados)
