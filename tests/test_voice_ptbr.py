"""Regra do Wesley (2026-10-02): vídeo em português sempre mais animado que o em inglês.
Voz: contract pt-* sem `estilo` ganha PT_BR_ESTILO_PADRAO em speech_metadata.style (mock_gemini registra o style);
inglês fica igual; estilo explícito manda. Trilha: preset pt animado no broll (ver test_broll.py)."""
import json
import socket
import threading
import time
from pathlib import Path

import pytest

from simplicio_video import contract as ct
from simplicio_video import intl, mock_gemini, voice

ROOT = Path(__file__).resolve().parents[1]
PT = voice.PT_BR_ESTILO_PADRAO


def _mock(log: Path) -> str:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    threading.Thread(target=mock_gemini.serve, args=(port, 0, str(log)), daemon=True).start()
    for _ in range(50):
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
            break
        except OSError:
            time.sleep(0.05)
    return f"http://127.0.0.1:{port}/v1beta"


def _gemini_contract(mini: Path, idioma: str | None, estilo: str | None = None) -> Path:
    g = {"voice": "Laomedeia"}
    if estilo is not None:
        g["estilo"] = estilo
    txt = mini.read_text().replace("providers: { file: { dir: vo } }", "providers: { file: { dir: vo }, gemini: " + json.dumps(g) + " }")
    if idioma:
        txt = txt.replace("  provider: file\n", f"  provider: file\n  idioma: {idioma}\n")
    mini.write_text(txt)
    return mini


def test_padrao_pt_e_enérgico_e_curto():
    for w in ("animado", "muita energia", "ritmo acelerado", "sorriso na voz", "sem gritar"):
        assert w in PT
    assert voice.resolve_estilo({"idioma": "pt-BR"}) == PT
    assert voice.resolve_estilo({"idioma": "pt-PT"}) == PT
    assert voice.resolve_estilo({"idioma": "en-US"}) == ""
    assert voice.resolve_estilo({}) == ""  # sem idioma explícito: nada muda
    assert voice.resolve_estilo({"idioma": "pt-BR", "estilo": "calmo"}) == "calmo"  # explícito manda
    assert voice.resolve_estilo({"idioma": "pt-BR", "estilo": "calmo"}, {"estilo": "festa"}) == "festa"


@pytest.mark.parametrize("api", ["interactions", "generate_content"])
def test_estilo_pt_padrao_vai_no_speech_metadata(mini, api):
    _gemini_contract(mini, "pt-BR")
    if api != "interactions":
        mini.write_text(mini.read_text().replace('"voice": "Laomedeia"}', '"voice": "Laomedeia", "api": "generate_content"}'))
    S = voice.settings_for(ct.load(mini), "gemini")
    assert S["estilo"] == PT
    _, body = voice.gemini_request(S, "Bora!")
    req = mock_gemini.parse("/v1beta/interactions" if api == "interactions" else f"/v1beta/models/{S['model']}:generateContent", body)
    assert req["style"] == PT


def test_ingles_fica_como_esta(mini):
    _gemini_contract(mini, "en-US")
    S = voice.settings_for(ct.load(mini), "gemini")
    assert S["estilo"] == ""
    _, body = voice.gemini_request(S, "Hi!")
    assert "annotations" not in body["input"][0]["content"][0]


def test_voice_run_pt_com_mock_registra_style_e_marca_lock(mini, tmp_path, monkeypatch):
    log = tmp_path / "mock.jsonl"
    monkeypatch.setenv("SIMPLICIO_GEMINI_BASE", _mock(log))
    monkeypatch.setenv("GEMINI_API_KEY", "mock-not-a-key")
    _gemini_contract(mini, "pt-BR")
    c = ct.load(mini)
    try:
        lock = voice.run(c, provider="gemini", log=lambda *_: None)
    except voice.VoiceError:  # o take sintético do mock pode passar do slot do fixture de 1 s; o lock é gravado igual
        lock = json.loads((c.dir / "timing.lock.json").read_text())
    calls = [json.loads(x) for x in log.read_text().splitlines()]
    assert calls and all(x["style"] == PT for x in calls)
    assert lock["settings"]["estilo"] == PT and lock.get("voz_pt_animada") is True


def test_voice_run_en_com_mock_sem_style(mini, tmp_path, monkeypatch):
    log = tmp_path / "mock.jsonl"
    monkeypatch.setenv("SIMPLICIO_GEMINI_BASE", _mock(log))
    monkeypatch.setenv("GEMINI_API_KEY", "mock-not-a-key")
    _gemini_contract(mini, "en-US", "Native American English speaker, warm and upbeat")
    c = ct.load(mini)
    try:
        lock = voice.run(c, provider="gemini", log=lambda *_: None)
    except voice.VoiceError:
        lock = json.loads((c.dir / "timing.lock.json").read_text())
    calls = [json.loads(x) for x in log.read_text().splitlines()]
    assert calls and all(x["style"] == "Native American English speaker, warm and upbeat" for x in calls)
    assert "voz_pt_animada" not in lock


def test_estilo_pt_calmo_explicito_nao_liga_trilha_pt():
    assert not voice.pt_animado({"idioma": "pt-BR", "estilo": "calmo, sem pressa"})
    assert voice.pt_animado({"idioma": "pt-BR"})
    assert voice.pt_animado({"idioma": "pt-BR", "estilo": PT + "; falando com brasileiros nos EUA"})
    assert not voice.pt_animado({"idioma": "en-US", "estilo": PT})


def test_paises_pt_br_usa_o_estilo_enérgico_e_ingles_nao_muda():
    d = json.loads((ROOT / "templates" / "internacional-dor" / "paises.json").read_text(encoding="utf8"))
    I = d["idiomas"]["pt-BR"]
    for est in [I["voz"]["estilo"], *I["estilo_por_pais"].values()]:
        assert est.startswith(PT), est
    assert "brasileiros que moram nos EUA" in I["estilo_por_pais"]["us"]
    for k, p in d.get("paises", d).items():
        if isinstance(p, dict) and str(p.get("idioma", "")).startswith("en"):
            assert PT not in json.dumps(p, ensure_ascii=False), k


def test_intl_voice_key_igual_ao_voice_para_pt_sem_estilo(mini):
    _gemini_contract(mini, "pt-BR")
    c = ct.load(mini)
    d = c.data
    S = voice.settings_for(c, "gemini")
    assert S["estilo"] == PT
    v = d["voz"]
    assert voice.resolve_estilo(v, (v.get("providers") or {}).get("gemini", {})) == PT


def test_retries_configuraveis_por_env(mini, monkeypatch):
    import urllib.error
    n = {"c": 0}

    def urlopen(req, timeout=0):
        n["c"] += 1
        raise urllib.error.HTTPError(req.full_url, 429, "quota", {}, None)

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("SIMPLICIO_GEMINI_RETRIES", "0")
    monkeypatch.setattr(voice.urllib.request, "urlopen", urlopen)
    with pytest.raises(voice.VoiceError, match="HTTP 429"):
        voice._gemini({"model": "m", "voice": "Laomedeia", "estilo": PT}, "Oi", mini.parent / "x.wav")
    assert n["c"] == 1


def test_pausa_entre_requisicoes_por_env(mini, monkeypatch):
    import base64
    import io
    sleeps = []
    monkeypatch.setattr(time, "sleep", lambda s: sleeps.append(s))

    class R(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    wav = mock_gemini.take("oi")
    res = {"steps": [{"type": "model_output", "content": [{"type": "audio", "mime_type": "audio/wav", "data": base64.b64encode(wav).decode()}]}]}
    monkeypatch.setattr(voice.urllib.request, "urlopen", lambda req, timeout=0: R(json.dumps(res).encode()))
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("SIMPLICIO_GEMINI_PAUSE_S", "7")
    monkeypatch.setattr(voice, "_LAST_REQ", [])
    S = {"model": "m", "voice": "Laomedeia", "estilo": PT}
    voice._gemini(S, "Oi", mini.parent / "a.wav")
    voice._gemini(S, "Oi de novo", mini.parent / "b.wav")
    assert len(sleeps) == 1 and 6.0 < sleeps[0] <= 7.0
