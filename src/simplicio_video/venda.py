"""`simplicio-video venda`: approved preview -> Pix charge (AbacatePay) -> paid webhook -> final HD render -> Drive.

State of each sale lives in `<prospect dir>/venda.json` (status: cobranca_criada -> pago -> entregue | erro_entrega).
Rules (AGENTS.md / docs/venda-ativa.md): the price is always chosen by the operator (120|80|60, no default); this module
never sends anything to the customer; credentials come only from the environment and are never written to disk or logs.
A confirmed payment is the council's authorization for the automatic `publish` of THAT video, and only in this flow.

API refs (checked 2026-09-30): POST {API}/transparents/create (method PIX, data.amount in cents -> data.id, brCode,
brCodeBase64), webhook `transparent.completed` (data.transparent.id, status PAID) signed with HMAC-SHA256 (base64, header
X-Webhook-Signature, AbacatePay's published public key) plus the `webhookSecret` query parameter.
"""
from __future__ import annotations

import base64
import datetime as dt
import hashlib
import hmac
import json
import os
import re
import threading
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable

API_BASE = "https://api.abacatepay.com/v2"
PRECOS = {120: 12000, 80: 8000, 60: 6000}  # R$ -> cents, decided by the council
ENV_KEY = "ABACATEPAY_API_KEY"
ENV_WEBHOOK_SECRET = "ABACATEPAY_WEBHOOK_SECRET"
# Published in docs.abacatepay.com/pages/webhooks/security; it is AbacatePay's verification key, not our secret.
ABACATEPAY_PUBLIC_KEY = ("t9dXRhHHo3yDEj5pVDYz0frf7q6bMKyMRmxxCPIPp3RCplBfXRxqlC6ZpiWmOqj4L63qEaeUOtrCI8P0VMUgo6iIga2ri9ogaHFs0WIIywSMg0q7"
                         "RmBfybe1E5XJcfC4IW3alNqym0tXoAKkzvfEjZxV6bE0oG2zJrNNYmUCKZyV0KZ3JS8Votf9EAWWYdiDkMkpbMdPggfh1EqHlVkMiTady6jOR3hyz"
                         "GEHrIz2Ret0xHKMbiqkr9HS1JhNHDX9")
VENDA = "venda.json"
QR = "pix-qr.png"
PAID_EVENT = "transparent.completed"
_LOCK = threading.Lock()

Http = Callable[[str, str, dict, dict | None], tuple[int, dict]]


class VendaError(Exception):
    pass


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def redact(text: str) -> str:
    """Strip any configured credential from text that may reach logs, stdout or venda.json."""
    for k in (ENV_KEY, ENV_WEBHOOK_SECRET):
        v = os.environ.get(k)
        if v:
            text = text.replace(v, "***")
    return text


def _http(method: str, url: str, headers: dict, body: dict | None) -> tuple[int, dict]:
    req = urllib.request.Request(url, method=method, headers={"Content-Type": "application/json", **headers},
                                 data=None if body is None else json.dumps(body).encode())
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"{}")
        except ValueError:
            return e.code, {}


def load_venda(pdir: Path) -> dict | None:
    p = pdir / VENDA
    return json.loads(p.read_text(encoding="utf8")) if p.is_file() else None


def save_venda(pdir: Path, v: dict) -> None:
    v["atualizado_em"] = _now()
    tmp = pdir / (VENDA + ".tmp")
    tmp.write_text(json.dumps(v, indent=2, ensure_ascii=False) + "\n", encoding="utf8")
    tmp.replace(pdir / VENDA)


def _norm_id(i: str) -> str:
    return re.sub(r"^pix_", "", i or "")


# ---------------------------------------------------------------- cobrar
def cobrar(pdir: Path, preco: int, http: Http | None = None, log=print) -> dict:
    pdir = Path(pdir)
    if preco not in PRECOS:
        raise VendaError(f"preço inválido: {preco} (aceitos: {', '.join(map(str, PRECOS))})")
    if not (pdir / "contract.yaml").is_file():
        raise VendaError(f"{pdir}: sem contract.yaml (esperado prospects/<lote>/<slug>)")
    v = load_venda(pdir)
    if v:
        if v["preco"] != preco:
            raise VendaError(f"já existe cobrança de R$ {v['preco']} ({v['status']}) em {pdir}; não crio outra de R$ {preco}")
        log(f"cobrança já existe ({v['status']}); nada criado.")
        _print_cobranca(pdir, v, log)
        return v
    key = os.environ.get(ENV_KEY)
    if not key:
        raise VendaError(f"defina {ENV_KEY} no ambiente (nunca em arquivo do repo)")
    body = {"method": "PIX", "data": {"amount": PRECOS[preco], "description": f"Video SimpleTI - {pdir.name}",
                                      "metadata": {"prospect": pdir.name}}}
    status, resp = (http or _http)("POST", f"{API_BASE}/transparents/create", {"Authorization": f"Bearer {key}"}, body)
    d = (resp or {}).get("data") or {}
    if status >= 300 or not resp.get("success", True) or not d.get("id") or not d.get("brCode"):
        raise VendaError(redact(f"AbacatePay recusou a cobrança (HTTP {status}): {(resp or {}).get('error')}"))
    qr = d.get("brCodeBase64") or ""
    if qr:
        (pdir / QR).write_bytes(base64.b64decode(qr.split(",", 1)[-1]))
    v = {"slug": pdir.name, "preco": preco, "valor_centavos": PRECOS[preco], "cobranca_id": d["id"], "br_code": d["brCode"],
         "qr_png": QR if qr else None, "expira_em": d.get("expiresAt"), "dev_mode": d.get("devMode"),
         "status": "cobranca_criada", "criado_em": _now(), "pago_em": None, "entregue_em": None, "link": None, "motivo": None}
    save_venda(pdir, v)
    _print_cobranca(pdir, v, log)
    return v


def _print_cobranca(pdir: Path, v: dict, log) -> None:
    log(f"R$ {v['preco']} | cobrança {v['cobranca_id']} | expira {v.get('expira_em')}")
    log(f"copia-e-cola:\n{v['br_code']}")
    if v.get("qr_png"):
        log(f"QR: {pdir / v['qr_png']}")
    log("Envie ao cliente você mesmo: o CLI não envia nada.")


# ---------------------------------------------------------------- webhook
def verify_signature(raw: bytes, signature: str | None) -> bool:
    if not signature:
        return False
    exp = base64.b64encode(hmac.new(ABACATEPAY_PUBLIC_KEY.encode(), raw, hashlib.sha256).digest()).decode()
    return hmac.compare_digest(exp, signature)


def find_venda(root: Path, charge_id: str) -> Path | None:
    for f in sorted(Path(root).glob(f"**/{VENDA}")):
        v = json.loads(f.read_text(encoding="utf8"))
        if _norm_id(v.get("cobranca_id")) == _norm_id(charge_id):
            return f.parent
    return None


def handle_webhook(root: Path, raw: bytes, signature: str | None, query_secret: str | None,
                   expected_secret: str | None = None) -> tuple[int, dict, Path | None]:
    """Pure webhook handler -> (http status, body, prospect dir to deliver or None). 4xx never changes state."""
    expected = expected_secret if expected_secret is not None else os.environ.get(ENV_WEBHOOK_SECRET)
    if not expected or not hmac.compare_digest((query_secret or "").encode(), expected.encode()):
        return 401, {"error": "unauthorized"}, None
    if not verify_signature(raw, signature):
        return 401, {"error": "bad signature"}, None
    try:
        ev = json.loads(raw)
        charge = ev["data"]["transparent"]
        cid, st = charge["id"], charge.get("status")
    except (ValueError, KeyError, TypeError):
        return 400, {"error": "invalid payload"}, None
    if ev.get("event") != PAID_EVENT or st != "PAID":
        return 422, {"error": f"event not handled: {ev.get('event')}"}, None
    with _LOCK:
        pdir = find_venda(root, cid)
        if not pdir:
            return 404, {"error": "unknown charge"}, None
        v = load_venda(pdir)
        if v["status"] != "cobranca_criada":
            return 200, {"ok": True, "duplicate": True}, None
        if charge.get("amount") != v["valor_centavos"]:
            return 422, {"error": "amount mismatch"}, None
        v.update(status="pago", pago_em=_now(), evento_id=ev.get("id"))
        save_venda(pdir, v)
    return 200, {"ok": True, "status": "pago"}, pdir


def serve(root: Path, host: str = "127.0.0.1", port: int = 8787, deliver: Callable[[Path], dict] | None = None, log=print):
    if not os.environ.get(ENV_WEBHOOK_SECRET):
        raise VendaError(f"defina {ENV_WEBHOOK_SECRET} no ambiente (o mesmo secret cadastrado no webhook da AbacatePay)")
    deliver = deliver or entregar

    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            u = urllib.parse.urlparse(self.path)
            raw = self.rfile.read(int(self.headers.get("Content-Length") or 0))
            if u.path != "/webhook/abacatepay":
                code, body, pdir = 404, {"error": "not found"}, None
            else:
                q = urllib.parse.parse_qs(u.query).get("webhookSecret", [None])[0]
                code, body, pdir = handle_webhook(root, raw, self.headers.get("X-Webhook-Signature"), q)
            out = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(out)))
            self.end_headers()
            self.wfile.write(out)
            log(f"webhook {code} {body.get('status') or body.get('error') or 'ok'}")
            if pdir:  # render takes minutes: answer first, deliver in the background
                threading.Thread(target=lambda: log(f"entrega {pdir.name}: {deliver(pdir)['status']}"), daemon=True).start()

        def log_message(self, *a):  # keep the secret query string out of access logs
            pass

    srv = ThreadingHTTPServer((host, port), H)
    log(f"webhook em http://{host}:{port}/webhook/abacatepay (raiz: {root}). Ctrl+C para sair.")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return srv


# ---------------------------------------------------------------- entrega
def _final_contract(pdir: Path):
    from . import contract as ct
    c = ct.load(pdir / "contract.yaml")
    d = c.data["drive"]
    d["arquivo"] = d["arquivo"].replace(" - Previa ", " - ")  # delivery name: "<CLIENTE> - <descricao> - vNN.mp4"
    d.pop("status", None)
    return c


def entregar(pdir: Path, render: Callable | None = None, publish: Callable | None = None, log=print) -> dict:
    """Final HD render + Drive publish for a paid sale. Failure -> erro_entrega (rerun `venda entregar`)."""
    pdir = Path(pdir)
    v = load_venda(pdir)
    if not v:
        raise VendaError(f"{pdir}: sem {VENDA} (rode `venda cobrar` primeiro)")
    if v["status"] == "entregue":
        log(f"já entregue: {v['link']}")
        return v
    if v["status"] not in ("pago", "erro_entrega"):
        raise VendaError(f"status {v['status']}: só entrego depois do pagamento confirmado (pago)")
    if render is None:
        from .cli import do_render
        render = lambda c: do_render(c, "local", log=log)  # noqa: E731
    if publish is None:
        from . import publish as pub
        publish = lambda c: pub.publish(c, update_readme=False, log=log)  # noqa: E731
    try:
        c = _final_contract(pdir)
        render(c)
        res = publish(c)
        v.update(status="entregue", link=res.get("link"), entregue_em=_now(), motivo=None)
    except (Exception, SystemExit) as e:
        v.update(status="erro_entrega", motivo=redact(str(e) or type(e).__name__)[-500:])
    with _LOCK:
        save_venda(pdir, v)
    return v


# ---------------------------------------------------------------- status
def listar(root: Path) -> list[dict]:
    return [json.loads(f.read_text(encoding="utf8")) for f in sorted(Path(root).glob(f"**/{VENDA}"))]


def tabela(rows: list[dict]) -> str:
    cols = [("slug", "SLUG"), ("preco", "PREÇO"), ("status", "STATUS"), ("link", "LINK")]
    data = [[str({"preco": f"R$ {r['preco']}"}.get(k, r.get(k)) if r.get(k) is not None else "-") for k, _ in cols] for r in rows]
    w = [max(len(h), *(len(x[i]) for x in data)) for i, (_, h) in enumerate(cols)] if data else [len(h) for _, h in cols]
    line = lambda xs: "  ".join(x.ljust(n) for x, n in zip(xs, w)).rstrip()  # noqa: E731
    return "\n".join([line([h for _, h in cols]), *map(line, data)])
