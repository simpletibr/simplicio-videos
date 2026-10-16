"""voice em paralelo (só o provedor de rede): mesma entrada, mesma saída, mesmo timing.lock.json.

A geração do Gemini é simulada trocando `voice._gemini` (sem rede, sem chave). Cada fala leva um atraso diferente,
em ordem inversa, para a conclusão sair fora de ordem; o lock e os WAVs têm de ser byte a byte os do modo serial.
"""
from __future__ import annotations

import hashlib
import io
import json
import math
import struct
import threading
import time
import wave
from pathlib import Path

import pytest
import yaml

from simplicio_video import contract as ct
from simplicio_video import voice

N = 6


def _wav(seed: int, seconds=0.30, sr=24000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1), w.setsampwidth(2), w.setframerate(sr)
        f = 300 + 40 * seed
        w.writeframes(b"".join(struct.pack("<h", int(8000 * math.sin(2 * math.pi * f * i / sr))) for i in range(int(seconds * sr))))
    return buf.getvalue()


def make_contract(mini: Path, n: int = N) -> Path:
    """O contrato mini com n falas (uma por cena); só `voice.run` o lê, então a soma das cenas não importa."""
    data = yaml.safe_load(mini.read_text())
    base = data["cenas"][0]
    cenas = []
    for i in range(n):
        c = json.loads(json.dumps(base))
        c["id"] = f"s{i + 1}"
        c["fala"] = {"id": f"vo{i + 1}", "texto": f"fala numero {i + 1}", "inicio_s": 0.05, "max_s": 0.9}
        cenas.append(c)
    data["cenas"] = cenas
    data["voz"]["provider"] = "gemini"
    data["voz"]["providers"] = {"file": {"dir": "vo"}, "gemini": {"voice": "Laomedeia", "estilo": "alegre"}}
    mini.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False))
    return mini


class Gemini:
    """Substituto de `voice._gemini`: grava um WAV que depende só do texto, depois de um atraso por fala."""

    def __init__(self, delay=0.0, reverse=True, fail_on=None):
        self.delay, self.reverse, self.fail_on = delay, reverse, fail_on
        self.calls: list[str] = []
        self.in_flight = 0
        self.max_in_flight = 0
        self.lock = threading.Lock()

    def __call__(self, S, text, dst, retries=4):
        n = int(text.rsplit(" ", 1)[1])
        with self.lock:
            self.calls.append(text)
            self.in_flight += 1
            self.max_in_flight = max(self.max_in_flight, self.in_flight)
        try:
            time.sleep(self.delay * ((N - n + 1) if self.reverse else 1))
            if self.fail_on == n:
                raise voice.VoiceError(f"provider=gemini: HTTP 400 simulado na fala {n}")
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(_wav(n))
            return {"api": "interactions", "model": S["model"], "voice": S["voice"], "mime": "audio/wav", "chars": len(text),
                    "usage": {"total_output_tokens": n}}
        finally:
            with self.lock:
                self.in_flight -= 1


def hashes(contrato: Path) -> dict:
    out = {}
    for p in sorted(contrato.parent.rglob("*")):
        if p.is_file() and p.suffix in (".wav", ".json") and "build" not in p.parts:
            out[str(p.relative_to(contrato.parent))] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "AIzaSyFAKE-KEY-for-tests-0000000000")
    g = Gemini(delay=0.03)
    monkeypatch.setattr(voice, "_gemini", g)
    return g


def run(c, **kw):
    return voice.run(ct.load(c), provider="gemini", log=lambda *_: None, **kw)


def copia(mini, tmp_path, nome):
    """Uma cópia independente do contrato com N falas, para comparar serial e paralelo lado a lado."""
    import shutil
    dst = tmp_path / nome
    shutil.copytree(mini.parent, dst)
    return make_contract(dst / "contract.yaml")


def test_padrao_e_quatro():
    assert voice.DEFAULT_CONCURRENCY == 4


def test_lock_identico_serial_e_paralelo(mini, tmp_path, api):
    a, b = copia(mini, tmp_path, "a"), copia(mini, tmp_path, "b")
    run(a, concurrency=1)
    assert api.max_in_flight == 1
    api.max_in_flight = 0
    run(b, concurrency=4)
    assert api.max_in_flight == 4
    assert (a.parent / "timing.lock.json").read_bytes() == (b.parent / "timing.lock.json").read_bytes()
    assert hashes(a) == hashes(b)
    lock = json.loads((b.parent / "timing.lock.json").read_text())
    assert list(lock["lines"]) == [f"vo{i}" for i in range(1, N + 1)]  # ordem das falas, não da conclusão
    assert lock["usage"]["tts_chars_this_run"] == sum(len(f"fala numero {i}") for i in range(1, N + 1))
    assert [lock["lines"][f"vo{i}"]["tts"]["usage"]["total_output_tokens"] for i in range(1, N + 1)] == list(range(1, N + 1))


def test_padrao_usa_quatro_em_voo(mini, api):
    c = make_contract(mini)
    run(c)
    assert api.max_in_flight == 4


def test_concurrency_limita(mini, api):
    c = make_contract(mini)
    run(c, concurrency=2)
    assert api.max_in_flight == 2


def test_cache_nao_chama_o_provedor(mini, api):
    c = make_contract(mini)
    first = run(c, concurrency=4)
    n = len(api.calls)
    again = run(c, concurrency=4)
    assert len(api.calls) == n == N
    assert again["usage"]["tts_chars_this_run"] == 0
    assert {k: v["sha256"] for k, v in again["lines"].items()} == {k: v["sha256"] for k, v in first["lines"].items()}


def test_force_com_ids_so_refaz_esses(mini, api):
    c = make_contract(mini)
    run(c, concurrency=4)
    api.calls.clear()
    run(c, concurrency=4, force=True, only=["vo2", "vo5"])
    assert sorted(api.calls) == ["fala numero 2", "fala numero 5"]


def test_force_sem_ids_refaz_tudo(mini, api):
    c = make_contract(mini)
    run(c, concurrency=4)
    api.calls.clear()
    run(c, concurrency=4, force=True)
    assert len(api.calls) == N


def test_cache_parcial_so_gera_o_que_falta(mini, api):
    c = make_contract(mini)
    run(c, concurrency=1)
    for f in (c.parent / "assets/audio/voz").glob("vo3-*.wav"):
        f.unlink()
    api.calls.clear()
    run(c, concurrency=4)
    assert api.calls == ["fala numero 3"]


def test_falha_de_uma_fala_aponta_a_fala_e_nao_grava_lock(mini, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "AIzaSyFAKE-KEY-for-tests-0000000000")
    g = Gemini(delay=0.02, reverse=False, fail_on=3)
    monkeypatch.setattr(voice, "_gemini", g)
    c = make_contract(mini)
    with pytest.raises(voice.VoiceError, match="fala 3"):
        run(c, concurrency=4)
    assert not (c.parent / "timing.lock.json").exists()


def test_falha_cancela_as_falas_que_nao_comecaram(mini, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "AIzaSyFAKE-KEY-for-tests-0000000000")
    g = Gemini(delay=0.05, reverse=False, fail_on=1)
    monkeypatch.setattr(voice, "_gemini", g)
    c = make_contract(mini)
    with pytest.raises(voice.VoiceError):
        run(c, concurrency=2)
    assert len(g.calls) < N  # com 2 em voo, a falha da primeira impede as últimas de começar


@pytest.mark.parametrize("prov", ["local", "file"])
def test_provedor_local_fica_serial(prov):
    assert voice.effective_concurrency(prov, 8) == 1
    assert voice.effective_concurrency(prov, None) == 1


def test_provedor_de_rede_usa_o_pedido():
    assert voice.effective_concurrency("gemini", None) == 4
    assert voice.effective_concurrency("gemini", 2) == 2
    assert voice.effective_concurrency("gemini", 1) == 1


def test_provedor_local_nao_cria_threads(mini, monkeypatch):
    """provider=file com --concurrency 8: nenhum loop, nenhuma thread de E/S."""
    from simplicio_video import aio

    def boom(*a, **k):
        raise AssertionError("o provedor local não passa pelo asyncio")

    monkeypatch.setattr(aio, "run_sync", boom)
    lock = voice.run(ct.load(mini), provider="file", log=lambda *_: None, concurrency=8)
    assert lock["lines"]["vo1"]["fits"]


def test_cli_aceita_concurrency(mini, api, capsys):
    from simplicio_video import cli
    c = make_contract(mini)
    assert cli.main(["voice", str(c), "--provider", "gemini", "--concurrency", "2"]) == 0
    assert api.max_in_flight == 2


def test_cli_concurrency_invalida(mini):
    from simplicio_video import cli
    with pytest.raises(SystemExit):
        cli.main(["voice", str(mini), "--concurrency", "0"])


def test_dentro_de_um_loop_ja_rodando(mini, api):
    import asyncio
    c = make_contract(mini)

    async def go():
        return run(c, concurrency=3)

    assert len(asyncio.run(go())["lines"]) == N
