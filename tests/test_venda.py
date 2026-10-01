import base64
import hashlib
import hmac
import json
import threading
import urllib.request

import pytest

from conftest import run_cli
from simplicio_video import venda

KEY = "abc_test_SECRETKEY_123"
WH = "whsec-test-456"
PNG = base64.b64encode(b"\x89PNG\r\n\x1a\nfake").decode()
CREATE_OK = {"data": {"id": "pix_char_abc123xyz", "amount": 12000, "status": "PENDING", "devMode": True,
                      "brCode": "00020160014BR.GOV.BCB.PIX070503***6304ABCD", "brCodeBase64": f"data:image/png;base64,{PNG}",
                      "expiresAt": "2099-01-01T10:00:00.000Z"}, "success": True, "error": None}


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv(venda.ENV_KEY, KEY)
    monkeypatch.setenv(venda.ENV_WEBHOOK_SECRET, WH)


@pytest.fixture
def pdir(tmp_path, mini):
    d = tmp_path / "prospects" / "lote" / "clinica-x"
    d.mkdir(parents=True)
    (d / "contract.yaml").write_text(mini.read_text(encoding="utf8"), encoding="utf8")
    return d


class FakeHttp:
    def __init__(self, resp=(200, CREATE_OK)):
        self.resp, self.calls = resp, []

    def __call__(self, method, url, headers, body):
        self.calls.append((method, url, headers, body))
        return self.resp


def event(cid="char_abc123xyz", amount=12000, ev="transparent.completed", status="PAID", eid="log_1"):
    raw = json.dumps({"id": eid, "event": ev, "apiVersion": 2, "devMode": True,
                      "data": {"transparent": {"id": cid, "amount": amount, "paidAmount": amount, "status": status}}}).encode()
    sig = base64.b64encode(hmac.new(venda.ABACATEPAY_PUBLIC_KEY.encode(), raw, hashlib.sha256).digest()).decode()
    return raw, sig


def test_preco_obrigatorio_e_so_120_80_60():
    assert run_cli("venda", "cobrar", "x").returncode == 2
    assert run_cli("venda", "cobrar", "x", "--preco", "100").returncode == 2
    assert {k: v for k, v in venda.PRECOS.items()} == {120: 12000, 80: 8000, 60: 6000}


@pytest.mark.parametrize("preco,cents", [(120, 12000), (80, 8000), (60, 6000)])
def test_cobrar_envia_centavos_e_grava_venda(pdir, preco, cents, capsys):
    h = FakeHttp()
    v = venda.cobrar(pdir, preco, http=h)
    method, url, headers, body = h.calls[0]
    assert (method, url) == ("POST", "https://api.abacatepay.com/v2/transparents/create")
    assert body["method"] == "PIX" and body["data"]["amount"] == cents
    assert headers["Authorization"] == f"Bearer {KEY}"
    on_disk = json.loads((pdir / "venda.json").read_text(encoding="utf8"))
    assert on_disk["status"] == "cobranca_criada" and on_disk["preco"] == preco and on_disk["cobranca_id"] == "pix_char_abc123xyz"
    assert on_disk["br_code"].startswith("00020160014") and v["qr_png"] == "pix-qr.png"
    assert (pdir / "pix-qr.png").read_bytes().startswith(b"\x89PNG")
    out = capsys.readouterr().out
    assert on_disk["br_code"] in out and "pix-qr.png" in out


def test_cobrar_idempotente_e_nao_troca_preco(pdir):
    h = FakeHttp()
    venda.cobrar(pdir, 120, http=h)
    venda.cobrar(pdir, 120, http=h)
    assert len(h.calls) == 1
    with pytest.raises(venda.VendaError):
        venda.cobrar(pdir, 60, http=h)
    assert len(h.calls) == 1


def test_cobrar_envia_expires_in_explicito(pdir):
    h = FakeHttp()
    venda.cobrar(pdir, 120, http=h)
    assert h.calls[0][3]["data"]["expiresIn"] == venda.EXPIRES_IN == 86400


def _vencer(pdir):
    v = venda.load_venda(pdir)
    v["expira_em"] = "2020-01-01T00:00:00.000Z"
    venda.save_venda(pdir, v)


def test_cobranca_vencida_gera_nova_guardando_id_anterior_e_aceita_novo_preco(pdir):
    h = FakeHttp()
    venda.cobrar(pdir, 120, http=h)
    _vencer(pdir)
    novo = {"data": {**CREATE_OK["data"], "id": "pix_char_novo", "amount": 6000}, "success": True, "error": None}
    h2 = FakeHttp((200, novo))
    v = venda.cobrar(pdir, 60, http=h2)
    assert len(h2.calls) == 1 and h2.calls[0][3]["data"]["amount"] == 6000
    on_disk = venda.load_venda(pdir)
    assert on_disk["cobranca_id"] == "pix_char_novo" and on_disk["preco"] == 60 and v["status"] == "cobranca_criada"
    assert on_disk["cobrancas_anteriores"] == ["pix_char_abc123xyz"]


def test_cobranca_vencida_mesmo_preco_tambem_recria(pdir):
    venda.cobrar(pdir, 120, http=FakeHttp())
    _vencer(pdir)
    h = FakeHttp()
    venda.cobrar(pdir, 120, http=h)
    assert len(h.calls) == 1


def test_cobranca_paga_nao_recria_nem_troca_preco(pdir):
    h = FakeHttp()
    venda.cobrar(pdir, 120, http=h)
    v = venda.load_venda(pdir)
    v.update(status="pago", expira_em="2020-01-01T00:00:00.000Z")
    venda.save_venda(pdir, v)
    with pytest.raises(venda.VendaError):
        venda.cobrar(pdir, 60, http=h)
    venda.cobrar(pdir, 120, http=h)
    assert len(h.calls) == 1


def test_cobrar_erro_da_api_nao_grava(pdir):
    with pytest.raises(venda.VendaError) as e:
        venda.cobrar(pdir, 120, http=FakeHttp((403, {"error": f"sem permissão {KEY}", "success": False})))
    assert KEY not in str(e.value) and not (pdir / "venda.json").exists()


def test_cobrar_sem_chave(pdir, monkeypatch):
    monkeypatch.delenv(venda.ENV_KEY)
    with pytest.raises(venda.VendaError):
        venda.cobrar(pdir, 120, http=FakeHttp())


def _venda(pdir):
    return json.loads((pdir / "venda.json").read_text(encoding="utf8"))


def test_webhook_valido_marca_pago(pdir):
    venda.cobrar(pdir, 120, http=FakeHttp())
    raw, sig = event()
    code, body, target = venda.handle_webhook(pdir.parent, raw, sig, WH)
    assert (code, target) == (200, pdir) and _venda(pdir)["status"] == "pago" and _venda(pdir)["pago_em"]


def test_webhook_segredo_ou_assinatura_errados_4xx_sem_mudar(pdir):
    venda.cobrar(pdir, 120, http=FakeHttp())
    before = (pdir / "venda.json").read_text(encoding="utf8")
    raw, sig = event()
    assert venda.handle_webhook(pdir.parent, raw, sig, "errado")[0] == 401
    assert venda.handle_webhook(pdir.parent, raw, sig, None)[0] == 401
    assert venda.handle_webhook(pdir.parent, raw, "AAAA", WH)[0] == 401
    assert venda.handle_webhook(pdir.parent, raw + b" ", sig, WH)[0] == 401
    assert venda.handle_webhook(pdir.parent, raw, None, WH)[0] == 401
    assert (pdir / "venda.json").read_text(encoding="utf8") == before


def test_webhook_invalido_desconhecido_ou_valor_errado_4xx(pdir):
    venda.cobrar(pdir, 120, http=FakeHttp())
    before = (pdir / "venda.json").read_text(encoding="utf8")
    junk = b"not json"
    sig = base64.b64encode(hmac.new(venda.ABACATEPAY_PUBLIC_KEY.encode(), junk, hashlib.sha256).digest()).decode()
    assert venda.handle_webhook(pdir.parent, junk, sig, WH)[0] == 400
    for kw, want in [({"cid": "char_outra"}, 404), ({"ev": "transparent.refunded"}, 422), ({"status": "PENDING"}, 422),
                     ({"amount": 100}, 422)]:
        raw, sig = event(**kw)
        assert venda.handle_webhook(pdir.parent, raw, sig, WH)[0] == want, kw
    assert (pdir / "venda.json").read_text(encoding="utf8") == before


def test_webhook_duplicado_nao_faz_nada(pdir):
    venda.cobrar(pdir, 120, http=FakeHttp())
    raw, sig = event()
    venda.handle_webhook(pdir.parent, raw, sig, WH)
    snap = (pdir / "venda.json").read_text(encoding="utf8")
    code, body, target = venda.handle_webhook(pdir.parent, raw, sig, WH)
    assert (code, body["duplicate"], target) == (200, True, None)
    assert (pdir / "venda.json").read_text(encoding="utf8") == snap


def _pago(pdir):
    venda.cobrar(pdir, 120, http=FakeHttp())
    raw, sig = event()
    venda.handle_webhook(pdir.parent, raw, sig, WH)


def test_pago_render_publish_entregue(pdir):
    _pago(pdir)
    calls = []
    v = venda.entregar(pdir, render=lambda c: calls.append("render"),
                       publish=lambda c: calls.append("publish") or {"link": "https://drive.google.com/file/d/ID/view"})
    assert calls == ["render", "publish"]
    assert v["status"] == "entregue" and _venda(pdir)["link"].endswith("/ID/view") and _venda(pdir)["entregue_em"]
    assert venda.entregar(pdir, render=None, publish=None)["status"] == "entregue"  # already delivered: no-op


def test_erro_de_publish_vira_erro_entrega_e_entregar_refaz_so_a_entrega(pdir):
    _pago(pdir)
    def boom(c):
        raise SystemExit(f"publish: rclone falhou {KEY}")
    v = venda.entregar(pdir, render=lambda c: None, publish=boom)
    assert v["status"] == "erro_entrega" and "rclone falhou" in v["motivo"] and KEY not in (pdir / "venda.json").read_text(encoding="utf8")
    n = []
    v = venda.entregar(pdir, render=lambda c: n.append(1), publish=lambda c: {"link": "L"})
    assert v["status"] == "entregue" and n == [1]


def test_erro_de_render_vira_erro_entrega(pdir):
    _pago(pdir)
    def boom(c):
        raise RuntimeError("ffmpeg caiu")
    assert venda.entregar(pdir, render=boom, publish=lambda c: {})["status"] == "erro_entrega"


def test_entregar_exige_pagamento(pdir):
    venda.cobrar(pdir, 120, http=FakeHttp())
    with pytest.raises(venda.VendaError):
        venda.entregar(pdir, render=lambda c: None, publish=lambda c: {})


def test_nome_final_sem_previa(pdir):
    f = pdir / "contract.yaml"
    arq = venda._final_contract(pdir).data["drive"]["arquivo"]
    f.write_text(f.read_text(encoding="utf8").replace(arq, "Clinica X - Previa Dia das Criancas 16s - v01.mp4"), encoding="utf8")
    assert venda._final_contract(pdir).data["drive"]["arquivo"] == "Clinica X - Dia das Criancas 16s - v01.mp4"


def test_status_tabela(pdir):
    venda.cobrar(pdir, 80, http=FakeHttp())
    t = venda.tabela(venda.listar(pdir.parent))
    assert t.splitlines()[0].split() == ["SLUG", "PREÇO", "STATUS", "LINK"]
    assert "clinica-x" in t and "R$ 80" in t and "cobranca_criada" in t


def test_servidor_http_ponta_a_ponta(pdir):
    venda.cobrar(pdir, 120, http=FakeHttp())
    done = threading.Event()
    srv_box = {}

    def deliver(p):
        done.set()
        return {"status": "entregue"}
    import http.server
    real = http.server.ThreadingHTTPServer.serve_forever

    def serve():
        venda.serve(pdir.parent, port=0, deliver=deliver, log=lambda *_: None)
    # bind on a free port by patching serve_forever to expose the server
    def fake_forever(self, *a, **k):
        srv_box["srv"] = self
        real(self, *a, **k)
    http.server.ThreadingHTTPServer.serve_forever = fake_forever
    try:
        t = threading.Thread(target=serve, daemon=True)
        t.start()
        while "srv" not in srv_box:
            pass
        srv = srv_box["srv"]
        port = srv.server_address[1]
        raw, sig = event()
        def post(q, s):
            r = urllib.request.Request(f"http://127.0.0.1:{port}/webhook/abacatepay?webhookSecret={q}", data=raw,
                                       headers={"X-Webhook-Signature": s}, method="POST")
            try:
                return urllib.request.urlopen(r).status
            except urllib.error.HTTPError as e:
                return e.code
        assert post("errado", sig) == 401 and _venda(pdir)["status"] == "cobranca_criada"
        assert post(WH, sig) == 200 and _venda(pdir)["status"] == "pago"
        assert done.wait(5)
        srv.shutdown()
    finally:
        http.server.ThreadingHTTPServer.serve_forever = real


def test_nenhum_segredo_em_saidas(pdir, capsys, caplog):
    _pago(pdir)
    venda.entregar(pdir, render=lambda c: None, publish=lambda c: (_ for _ in ()).throw(SystemExit(f"x {KEY} {WH}")))
    print(venda.tabela(venda.listar(pdir.parent)))
    out = capsys.readouterr()
    blob = out.out + out.err + caplog.text + "".join(p.read_text(encoding="utf8", errors="ignore") for p in pdir.iterdir() if p.suffix in ".json.yaml")
    assert KEY not in blob and WH not in blob
