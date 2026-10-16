"""swap em paralelo (asyncio sobre o cliente HTTP síncrono): hermético, sem rede, sem chave, sem gasto.

O adaptador `fake` simula a latência (atributos de classe) e conta quantos pedaços estão em voo ao mesmo tempo.
Os testes provam: limite de concorrência, ordem determinística da emenda e do manifesto, saída idêntica à serial,
falha de um pedaço cancelando os outros, timeout por pedaço e Ctrl+C sem deixar arquivo nem tarefa.
"""
from __future__ import annotations

import json
import os
import signal
import threading
import time
from pathlib import Path

import pytest
from test_swap import make_png, make_video, needs_ffmpeg

from simplicio_video import swap
from simplicio_video.swap_providers import fake

pytestmark = needs_ffmpeg


@pytest.fixture(autouse=True)
def _real_time(monkeypatch):
    """Latências reais e curtas: o paralelismo só aparece com tempo de verdade."""
    monkeypatch.setattr(swap, "_sleep", time.sleep)
    monkeypatch.setattr(swap, "_now", time.monotonic)
    fake.FakeAdapter.reset()
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)


@pytest.fixture
def longo(tmp_path, monkeypatch):
    """Vídeo de 14 s em 3 pedaços (o fake aceita 5 s por pedaço aqui)."""
    caps = fake.FakeAdapter.capabilities
    monkeypatch.setattr(fake.FakeAdapter, "capabilities", caps.__class__(**{**caps.__dict__, "max_input_s": 5.0}))
    return {"video": make_video(tmp_path / "longo.mp4", 14), "ref": make_png(tmp_path / "ref.png"), "dir": tmp_path}


def argv(m, *extra, out="out/swapped.mp4"):
    return ["run", "--provider", "fake", "--video", str(m["video"]), "--ref", str(m["ref"]),
            "--out", str(m["dir"] / out), "--autorizo", "--yes", "--max-usd", "50", "--poll-interval", "0.02", *extra]


def manifest(m, out="out"):
    return json.loads((m["dir"] / out / "swap.manifest.json").read_text())


# ---------------------------------------------------------------- limite de concorrência

def test_padrao_e_tres():
    assert swap.DEFAULT_CONCURRENCY == 3


def test_concorrencia_padrao_roda_os_tres_pedacos_juntos(longo):
    fake.FakeAdapter.generation_s = 0.4
    assert swap.run_swap(argv(longo)) == 0
    assert fake.FakeAdapter.max_in_flight == 3
    assert manifest(longo)["concurrency"] == {"requested": 3, "effective": 3, "adapter_max": 3}


def test_concurrency_1_e_serial(longo):
    fake.FakeAdapter.generation_s = 0.05
    assert swap.run_swap(argv(longo, "--concurrency", "1")) == 0
    assert fake.FakeAdapter.max_in_flight == 1
    assert manifest(longo)["concurrency"]["effective"] == 1


def test_concurrency_2_limita_a_dois(longo):
    fake.FakeAdapter.generation_s = 0.3
    assert swap.run_swap(argv(longo, "--concurrency", "2")) == 0
    assert fake.FakeAdapter.max_in_flight == 2


def test_adaptador_pode_baixar_o_limite(longo, monkeypatch):
    caps = fake.FakeAdapter.capabilities
    monkeypatch.setattr(fake.FakeAdapter, "capabilities", caps.__class__(**{**caps.__dict__, "max_concurrency": 1}))
    fake.FakeAdapter.generation_s = 0.05
    assert swap.run_swap(argv(longo, "--concurrency", "3")) == 0
    assert fake.FakeAdapter.max_in_flight == 1
    assert manifest(longo)["concurrency"] == {"requested": 3, "effective": 1, "adapter_max": 1}


@pytest.mark.parametrize("valor", ["0", "-1", "x"])
def test_concurrency_invalida(longo, valor):
    with pytest.raises(SystemExit):
        swap.run_swap(argv(longo, "--concurrency", valor))
    assert fake.FakeAdapter.submits == []


# ---------------------------------------------------------------- determinismo

def test_saida_identica_serial_e_paralelo_mesmo_com_conclusao_fora_de_ordem(longo):
    """O pedaço 0 é o mais lento: no paralelo ele termina por último, e a emenda ainda sai na ordem do vídeo."""
    fake.FakeAdapter.generation_by_index = {0: 0.30, 1: 0.10, 2: 0.0}
    assert swap.run_swap(argv(longo, "--concurrency", "1", out="serial/s.mp4")) == 0
    fake.FakeAdapter.reset()
    fake.FakeAdapter.generation_by_index = {0: 0.30, 1: 0.10, 2: 0.0}
    assert swap.run_swap(argv(longo, "--concurrency", "3", out="paralelo/s.mp4")) == 0
    s, p = manifest(longo, "serial"), manifest(longo, "paralelo")
    assert s["output"]["sha256"] == p["output"]["sha256"]
    assert [c["index"] for c in p["chunks"]] == [0, 1, 2]
    assert [c["start_s"] for c in p["chunks"]] == [c["start_s"] for c in s["chunks"]]
    assert [c.get("sha256") for c in p["chunks"]] == [c.get("sha256") for c in s["chunks"]]
    assert [c["handle"] for c in p["chunks"]] != []


def test_manifesto_igual_fora_dos_campos_de_tempo(longo):
    def limpo(m):
        m = json.loads(json.dumps(m))
        for k in ("concurrency", "timing", "authorization"):
            m.pop(k, None)
        m["inputs"]["video"].pop("path", None)
        m["inputs"]["refs"] = [r["sha256"] for r in m["inputs"]["refs"]]
        m["output"].pop("path", None)
        for c in m["chunks"]:
            c.pop("latency")
            c.pop("handle")
        return m

    assert swap.run_swap(argv(longo, "--concurrency", "1", out="serial/s.mp4")) == 0
    fake.FakeAdapter.reset()
    assert swap.run_swap(argv(longo, "--concurrency", "3", out="paralelo/s.mp4")) == 0
    assert limpo(manifest(longo, "serial")) == limpo(manifest(longo, "paralelo"))


# ---------------------------------------------------------------- medição no manifesto

def test_manifesto_registra_latencia_por_pedaco_e_ganho(longo):
    fake.FakeAdapter.generation_s = 0.3
    assert swap.run_swap(argv(longo)) == 0
    m = manifest(longo)
    for c in m["chunks"]:
        assert {"upload_s", "queue_s", "generation_s", "download_s", "total_s"} <= set(c["latency"])
        assert c["latency"]["total_s"] >= c["latency"]["generation_s"] >= 0.25
    t = m["timing"]
    assert set(t) == {"wall_s", "sum_chunks_s", "speedup", "saved_s"}
    assert t["sum_chunks_s"] == pytest.approx(sum(c["latency"]["total_s"] for c in m["chunks"]), abs=0.01)
    assert t["wall_s"] < t["sum_chunks_s"] and t["speedup"] > 1.3
    assert t["saved_s"] == pytest.approx(t["sum_chunks_s"] - t["wall_s"], abs=0.01)


def test_manifesto_serial_tem_ganho_proximo_de_um(longo):
    fake.FakeAdapter.generation_s = 0.1
    assert swap.run_swap(argv(longo, "--concurrency", "1")) == 0
    assert manifest(longo)["timing"]["speedup"] == pytest.approx(1.0, abs=0.35)


def test_manifesto_sem_segredo_com_chave_no_ambiente(longo, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "AIzaSyFAKE-KEY-for-tests-0000000000")
    assert swap.run_swap(argv(longo)) == 0
    assert "AIzaSyFAKE" not in (longo["dir"] / "out" / "swap.manifest.json").read_text()


# ---------------------------------------------------------------- falha, timeout e Ctrl+C

def sobras(m):
    return [p.name for p in (m["dir"] / "out").iterdir() if p.name.startswith(".swap-work")]


def test_falha_de_um_pedaco_cancela_os_outros_e_diz_qual(longo, capsys):
    fake.FakeAdapter.stuck = True          # os pedaços 0 e 2 ficam esperando para sempre...
    fake.FakeAdapter.fail_index = 1        # ...e o 1 falha de vez na entrega
    fake.FakeAdapter.fail_retryable = False
    t0 = time.monotonic()
    assert swap.run_swap(argv(longo, "--timeout", "30")) == 1
    assert time.monotonic() - t0 < 15  # cancelou: não esperou o timeout de 30 s
    err = capsys.readouterr().err
    assert "pedaço 2/3" in err
    m = manifest(longo)
    assert m["state"] == "failed"
    assert [c["state"] for c in m["chunks"]] == ["cancelled", "failed", "cancelled"]
    assert "pedaço 2/3" in m["error"] and m["chunks"][1]["error"]
    assert not (longo["dir"] / "out" / "swapped.mp4").exists()
    assert sobras(longo) == []


def test_pedaco_pronto_continua_pronto_quando_outro_falha(longo):
    fake.FakeAdapter.generation_by_index = {0: 0.0, 1: 5.0, 2: 0.6}
    fake.FakeAdapter.fail_poll_index = 2   # o 2 falha no polling aos 0,6 s; o 0 já terminou; o 1 ainda gera
    assert swap.run_swap(argv(longo, "--timeout", "30")) == 1
    m = manifest(longo)
    assert m["chunks"][0]["state"] == "done" and m["chunks"][2]["state"] == "failed"
    assert m["chunks"][1]["state"] == "cancelled"
    assert m["chunks"][1]["handle"], "o handle fica no manifesto para conferir o que foi cobrado"


def test_timeout_por_pedaco_aponta_o_pedaco(longo, capsys):
    fake.FakeAdapter.generation_by_index = {0: 0.0, 1: 60.0, 2: 0.0}
    assert swap.run_swap(argv(longo, "--timeout", "1")) == 1
    assert "pedaço 2" in capsys.readouterr().err
    m = manifest(longo)
    assert m["state"] == "timeout"
    assert m["chunks"][1]["state"] == "timeout" and m["chunks"][1]["handle"]
    assert sobras(longo) == []


def test_ctrl_c_cancela_limpo(longo, capsys):
    fake.FakeAdapter.stuck = True
    threading.Timer(0.8, lambda: os.kill(os.getpid(), signal.SIGINT)).start()
    antes = {t.ident for t in threading.enumerate()}
    assert swap.run_swap(argv(longo, "--timeout", "60")) == 130
    assert "interrompido" in capsys.readouterr().err.lower()
    m = manifest(longo)
    assert m["state"] == "interrupted" and all(c["state"] == "interrupted" for c in m["chunks"])
    assert sobras(longo) == []
    assert not (longo["dir"] / "out" / "swapped.mp4").exists()
    time.sleep(0.3)
    novos = [t for t in threading.enumerate() if t.ident not in antes and t.is_alive() and not t.daemon]
    assert novos == []


def test_dentro_de_um_loop_ja_rodando(longo):
    """O MCP chama funções síncronas de dentro de um loop: o swap não pode quebrar com 'asyncio.run' aninhado."""
    import asyncio

    fake.FakeAdapter.generation_s = 0.05

    async def go():
        return swap.run_swap(argv(longo))

    assert asyncio.run(go()) == 0


def test_retry_transitorio_continua_valendo_em_paralelo(longo):
    fake.FakeAdapter.fail_submits = 2
    fake.FakeAdapter.generation_s = 0.05
    assert swap.run_swap(argv(longo)) == 0
    m = manifest(longo)
    assert m["attempts"] == 5 and sum(c["attempts"] for c in m["chunks"]) == 5
    assert Path(m["output"]["path"]).is_file()
