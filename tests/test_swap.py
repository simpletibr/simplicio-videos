"""Troca de personagem (`simplicio-video swap`): agnóstica de fornecedor, hermética.

Nenhum teste abre rede, usa chave real ou gasta dinheiro: o adaptador `fake` não fala com ninguém e o HTTP do Gemini
é simulado trocando `swap_providers.http.request`. As chaves abaixo são valores falsos.
"""
from __future__ import annotations

import base64
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from simplicio_video import cli, mcp_server, swap, swap_providers
from simplicio_video.swap_providers import fake, http

FIX = Path(__file__).parent / "fixtures" / "swap"
FAKE_KEY = "AIzaSyFAKE-KEY-for-tests-0000000000"
needs_ffmpeg = pytest.mark.skipif(not (shutil.which("ffmpeg") and shutil.which("ffprobe")), reason="ffmpeg ausente")


def fx(name: str) -> bytes:
    return (FIX / name).read_bytes()


def make_video(path: Path, secs: float, audio: bool = True, fps: int = 24) -> Path:
    cmd = ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"testsrc=size=160x90:rate={fps}:duration={secs}"]
    if audio:
        cmd += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={secs}"]
    cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p"] + (["-c:a", "aac", "-shortest"] if audio else []) + [str(path)]
    subprocess.run(cmd, check=True)
    return path


def make_png(path: Path) -> Path:
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=red:s=32x32:d=0.1",
                    "-frames:v", "1", str(path)], check=True)
    return path


@pytest.fixture
def media(tmp_path):
    return {"video": make_video(tmp_path / "in.mp4", 6), "ref": make_png(tmp_path / "ref.png"), "dir": tmp_path}


@pytest.fixture(autouse=True)
def _fakes(monkeypatch):
    """Clock and sleep are fake: polling and backoff never really wait. The fake adapter starts clean."""
    clock = {"t": 0.0}
    monkeypatch.setattr(swap, "_sleep", lambda s: clock.__setitem__("t", clock["t"] + s))
    monkeypatch.setattr(swap, "_now", lambda: clock["t"])
    fake.FakeAdapter.reset()
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    return clock


def argv_run(m, *extra, out=None):
    out = out or m["dir"] / "out" / "swapped.mp4"
    return ["run", "--provider", "fake", "--video", str(m["video"]), "--ref", str(m["ref"]), "--out", str(out), *extra]


# ---------------------------------------------------------------- adaptadores e preços

def test_registro_tem_os_seis_adaptadores():
    assert set(swap_providers.names()) == {"gemini", "fal", "wavespeed", "kie", "alibaba", "fake"}


@pytest.mark.parametrize("nome", ["gemini", "fal", "wavespeed", "kie", "alibaba", "fake"])
def test_interface_do_adaptador(nome):
    a = swap_providers.get(nome)
    assert a.name == nome
    assert nome == "fake" or a.env_var.endswith("_KEY") or a.env_var.endswith("_TOKEN")
    caps = a.capabilities
    for campo in ("resolutions", "max_input_s", "max_output_s", "max_ref_images", "keeps_audio", "bills_input"):
        assert hasattr(caps, campo), campo
    for linha in a.prices:
        assert linha.source_url.startswith("https://") and linha.read_on == "2026-10-15"
        assert linha.confidence in ("alta", "media", "baixa")
    for metodo in ("estimate", "submit", "poll", "fetch"):
        assert callable(getattr(a, metodo))


def test_so_o_gemini_esta_verificado():
    assert swap_providers.get("gemini").verified is True
    for nome in ("fal", "wavespeed", "kie", "alibaba"):
        assert swap_providers.get(nome).verified is False, nome


def test_providers_cli_lista_unverified_e_preco(capsys):
    assert swap.run_swap(["providers"]) == 0
    out = capsys.readouterr().out
    assert out.count("UNVERIFIED") >= 4
    for nome in ("gemini", "fal", "wavespeed", "kie", "alibaba"):
        assert nome in out
    assert "0,101" in out or "0.101" in out
    assert "R$" in out


def test_providers_json(capsys):
    assert swap.run_swap(["providers", "--json"]) == 0
    dados = json.loads(capsys.readouterr().out)
    por_nome = {p["name"]: p for p in dados["providers"]}
    assert por_nome["fal"]["verified"] is False and por_nome["gemini"]["verified"] is True
    assert dados["fx"]["brl_per_usd"] == 5.0521
    assert por_nome["gemini"]["prices"][0]["source_url"].startswith("https://")


def job(**kw):
    base = dict(video=Path("x.mp4"), refs=[Path("r.png")], prompt="p", resolution="720p", duration_s=10.0, fps=24.0)
    base.update(kw)
    return swap.Job(**base)


def test_estimativa_gemini_720p():
    e = swap_providers.get("gemini").estimate(job())
    assert e.usd == pytest.approx(10 * 0.101 + 10 * 0.0087)
    assert e.confidence == "alta" and e.source_url.startswith("https://") and e.read_on == "2026-10-15"


def test_estimativa_gemini_1080p_so_terceiros():
    e = swap_providers.get("gemini").estimate(job(resolution="1080p"))
    assert e.usd == pytest.approx(10 * 0.152 + 10 * 0.0087)
    assert e.confidence == "baixa"


def test_fal_cobra_por_quadros_a_16fps():
    a = swap_providers.get("fal")
    assert a.estimate(job(fps=16)).usd == pytest.approx(0.8)
    assert a.estimate(job(fps=24)).usd == pytest.approx(1.2)


def test_precos_dos_outros():
    assert swap_providers.get("wavespeed").estimate(job()).usd == pytest.approx(0.8)
    assert swap_providers.get("kie").estimate(job()).usd == pytest.approx(0.625)
    assert swap_providers.get("alibaba").estimate(job()).usd == pytest.approx(1.8)


def test_resolucao_nao_suportada():
    with pytest.raises(swap.SwapError, match="1080p|resolu"):
        swap_providers.get("kie").estimate(job(resolution="1080p"))


def test_estimativa_em_reais():
    assert swap.brl(1.0) == pytest.approx(5.0521)


# ---------------------------------------------------------------- corte em pedaços

def test_plano_de_pedacos_respeita_o_maximo_e_cobre_tudo():
    p = swap.plan_chunks(25.0, 10.0)
    assert len(p) == 3 and all(l <= 10.0 + 1e-9 for _, l in p)
    assert p[0][0] == 0 and sum(l for _, l in p) == pytest.approx(25.0)
    assert all(abs(p[i][0] + p[i][1] - p[i + 1][0]) < 1e-9 for i in range(len(p) - 1))


def test_plano_curto_tem_um_pedaco():
    assert swap.plan_chunks(8.0, 10.0) == [(0.0, 8.0)]


def test_plano_nao_deixa_resto_menor_que_o_minimo():
    p = swap.plan_chunks(10.5, 10.0, min_s=3.0)
    assert all(l >= 3.0 for _, l in p)


# ---------------------------------------------------------------- validação

@needs_ffmpeg
def test_valida_video_inexistente(media, capsys):
    argv = ["estimate", "--provider", "fake", "--video", str(media["dir"] / "nao.mp4"), "--ref", str(media["ref"])]
    assert swap.run_swap(argv) != 0
    assert "não encontrado" in capsys.readouterr().err


@needs_ffmpeg
def test_valida_sem_imagem_de_referencia(media, capsys):
    assert swap.run_swap(["estimate", "--provider", "fake", "--video", str(media["video"])]) != 0
    assert "--ref" in capsys.readouterr().err


@needs_ffmpeg
def test_valida_referencia_que_nao_e_imagem(media, capsys):
    txt = media["dir"] / "ref.txt"
    txt.write_text("nao sou imagem")
    assert swap.run_swap(["estimate", "--provider", "fake", "--video", str(media["video"]), "--ref", str(txt)]) != 0
    assert "imagem" in capsys.readouterr().err


@needs_ffmpeg
def test_valida_excesso_de_referencias(media, capsys):
    refs = []
    for i in range(fake.FakeAdapter.capabilities.max_ref_images + 1):
        refs += ["--ref", str(media["ref"])]
    assert swap.run_swap(["estimate", "--provider", "fake", "--video", str(media["video"]), *refs]) != 0
    assert "máximo" in capsys.readouterr().err


@needs_ffmpeg
def test_valida_video_menor_que_o_minimo(media, capsys):
    curto = make_video(media["dir"] / "curto.mp4", 1)
    assert swap.run_swap(["estimate", "--provider", "gemini", "--video", str(curto), "--ref", str(media["ref"])]) != 0
    assert "mínimo" in capsys.readouterr().err


def test_provedor_desconhecido(media, capsys):
    assert swap.run_swap(["estimate", "--provider", "nada", "--video", "a", "--ref", "b"]) != 0
    assert "desconhecido" in capsys.readouterr().err


def test_chave_nunca_por_argumento(media):
    with pytest.raises(SystemExit):
        swap.run_swap(argv_run(media, "--autorizo", "--api-key", "x"))


# ---------------------------------------------------------------- consentimento, dry-run e teto

@needs_ffmpeg
def test_recusa_sem_autorizo(media, capsys):
    assert swap.run_swap(argv_run(media, "--yes")) != 0
    assert "--autorizo" in capsys.readouterr().err
    assert fake.FakeAdapter.submits == []


@needs_ffmpeg
def test_sem_yes_so_estima_e_nao_chama_o_adaptador(media, capsys):
    assert swap.run_swap(argv_run(media, "--autorizo")) == 0
    out = capsys.readouterr().out
    assert "dry-run" in out.lower() and "US$" in out and "R$" in out
    assert fake.FakeAdapter.submits == []
    assert not (media["dir"] / "out" / "swapped.mp4").exists()
    assert not (media["dir"] / "out" / "swap.manifest.json").exists()


@needs_ffmpeg
def test_dry_run_json(media, capsys):
    assert swap.run_swap(argv_run(media, "--autorizo", "--json")) == 0
    d = json.loads(capsys.readouterr().out)
    assert d["dry_run"] is True and d["estimate"]["usd"] > 0 and d["estimate"]["brl"] > 0
    assert d["chunks"] == 1


@needs_ffmpeg
def test_teto_de_gasto_aborta_antes_de_submeter(media, capsys):
    assert swap.run_swap(argv_run(media, "--autorizo", "--yes", "--max-usd", "0.01")) == 2
    assert "--max-usd" in capsys.readouterr().err
    assert fake.FakeAdapter.submits == []


@needs_ffmpeg
def test_teto_padrao_e_baixo(media):
    assert 0 < swap.DEFAULT_MAX_USD <= 5


def test_adaptador_unverified_exige_aceite(media, capsys, monkeypatch):
    monkeypatch.setenv("FAL_KEY", "fake-fal-key")
    argv = ["run", "--provider", "fal", "--video", str(media["video"]), "--ref", str(media["ref"]),
            "--out", str(media["dir"] / "o.mp4"), "--autorizo", "--yes", "--max-usd", "50"]
    assert swap.run_swap(argv) != 0
    assert "UNVERIFIED" in capsys.readouterr().err


@needs_ffmpeg
def test_sem_variavel_de_ambiente_falha_antes_da_rede(media, capsys, monkeypatch):
    def boom(*a, **k):
        raise AssertionError("rede")
    monkeypatch.setattr(http, "request", boom)
    argv = ["run", "--provider", "gemini", "--video", str(media["video"]), "--ref", str(media["ref"]),
            "--out", str(media["dir"] / "o.mp4"), "--autorizo", "--yes"]
    assert swap.run_swap(argv) != 0
    assert "GEMINI_API_KEY" in capsys.readouterr().err


# ---------------------------------------------------------------- execução ponta a ponta com o fake

def ffprobe(path, entries="stream=codec_type,duration", extra=()):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", entries, "-of", "json", *extra, str(path)],
                       capture_output=True, text=True, check=True)
    return json.loads(r.stdout)


@needs_ffmpeg
def test_run_completo_com_manifesto(media, capsys):
    out = media["dir"] / "out" / "swapped.mp4"
    assert swap.run_swap(argv_run(media, "--autorizo", "--yes", "--max-usd", "5")) == 0
    assert out.is_file()
    man = json.loads((media["dir"] / "out" / "swap.manifest.json").read_text())
    assert man["state"] == "done" and man["provider"] == "fake" and man["resolution"] == "720p"
    assert man["inputs"]["video"]["sha256"] == swap.sha256_file(media["video"])
    assert man["inputs"]["refs"][0]["sha256"] == swap.sha256_file(media["ref"])
    assert man["output"]["sha256"] == swap.sha256_file(out)
    assert man["authorization"]["text"] == swap.AUTORIZACAO_TEXTO
    assert man["estimate"]["usd"] > 0 and man["estimate"]["confidence"] in ("alta", "media", "baixa")
    assert man["adapter_version"] and man["attempts"] >= 1
    c = man["chunks"][0]
    assert {"upload_s", "queue_s", "generation_s", "download_s"} <= set(c["latency"])
    assert man["output"]["fps"] == pytest.approx(24, abs=0.5) and man["output"]["duration_s"] == pytest.approx(6, abs=0.3)
    tipos = {s["codec_type"] for s in ffprobe(out)["streams"]}
    assert tipos == {"video", "audio"}  # o fake não preserva áudio: o original foi remontado


@needs_ffmpeg
def test_run_corta_em_pedacos_e_emenda(media, monkeypatch):
    longo = make_video(media["dir"] / "longo.mp4", 14)
    monkeypatch.setattr(fake.FakeAdapter, "capabilities", fake.FakeAdapter.capabilities.__class__(
        **{**fake.FakeAdapter.capabilities.__dict__, "max_input_s": 5.0}))
    m = dict(media, video=longo)
    assert swap.run_swap(argv_run(m, "--autorizo", "--yes", "--max-usd", "50")) == 0
    man = json.loads((media["dir"] / "out" / "swap.manifest.json").read_text())
    assert len(man["chunks"]) == 3 and len(fake.FakeAdapter.submits) == 3
    assert all(c["length_s"] <= 5.0 + 1e-6 for c in man["chunks"])
    assert man["output"]["duration_s"] == pytest.approx(14, abs=0.4)


@needs_ffmpeg
def test_run_json(media, capsys):
    assert swap.run_swap(argv_run(media, "--autorizo", "--yes", "--max-usd", "5", "--json")) == 0
    d = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert d["state"] == "done" and d["manifest"].endswith("swap.manifest.json")


@needs_ffmpeg
def test_prompt_padrao_protege_os_outros(media):
    swap.run_swap(argv_run(media, "--autorizo", "--yes", "--max-usd", "5"))
    p = fake.FakeAdapter.submits[0].prompt.lower()
    for termo in ("<image_ref_0>", "every other person", "scenery", "camera", "audio"):
        assert termo in p, termo


@needs_ffmpeg
def test_timeout_grava_manifesto_e_falha(media, capsys):
    fake.FakeAdapter.stuck = True
    assert swap.run_swap(argv_run(media, "--autorizo", "--yes", "--max-usd", "5", "--timeout", "30", "--poll-interval", "1")) == 1
    assert "timeout" in capsys.readouterr().err.lower()
    man = json.loads((media["dir"] / "out" / "swap.manifest.json").read_text())
    assert man["state"] == "timeout" and man["chunks"][0]["handle"]
    assert not (media["dir"] / "out" / "swapped.mp4").exists()


@needs_ffmpeg
def test_backoff_do_polling_cresce_e_tem_teto(media, _fakes, monkeypatch):
    esperas = []
    monkeypatch.setattr(swap, "_sleep", lambda s: (esperas.append(s), _fakes.__setitem__("t", _fakes["t"] + s)))
    fake.FakeAdapter.polls_before_done = 8
    swap.run_swap(argv_run(media, "--autorizo", "--yes", "--max-usd", "5", "--poll-interval", "2"))
    polls = [e for e in esperas if e >= 2]
    assert polls[0] == 2 and polls[-1] <= swap.POLL_MAX_S and polls == sorted(polls)


@needs_ffmpeg
def test_falha_transitoria_tem_nova_tentativa(media):
    fake.FakeAdapter.fail_submits = 1
    assert swap.run_swap(argv_run(media, "--autorizo", "--yes", "--max-usd", "5")) == 0
    man = json.loads((media["dir"] / "out" / "swap.manifest.json").read_text())
    assert man["attempts"] == 2


@needs_ffmpeg
def test_falha_definitiva_nao_repete(media, capsys):
    fake.FakeAdapter.fail_submits = 1
    fake.FakeAdapter.fail_retryable = False
    assert swap.run_swap(argv_run(media, "--autorizo", "--yes", "--max-usd", "5")) == 1
    assert len(fake.FakeAdapter.submit_calls) == 1


@needs_ffmpeg
def test_status_le_o_manifesto(media, capsys):
    swap.run_swap(argv_run(media, "--autorizo", "--yes", "--max-usd", "5"))
    capsys.readouterr()
    man = media["dir"] / "out" / "swap.manifest.json"
    assert swap.run_swap(["status", str(man)]) == 0
    assert "done" in capsys.readouterr().out
    assert swap.run_swap(["status", str(man), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["state"] == "done"


def test_status_manifesto_inexistente(tmp_path, capsys):
    assert swap.run_swap(["status", str(tmp_path / "x.json")]) != 0


# ---------------------------------------------------------------- Gemini com HTTP simulado

class Rota:
    """Roteador de HTTP falso: grava as chamadas e devolve o que o teste mandar, sem rede."""

    def __init__(self, respostas):
        self.respostas = list(respostas)
        self.calls = []

    def __call__(self, method, url, headers=None, json_body=None, timeout=60):
        self.calls.append({"method": method, "url": url, "headers": dict(headers or {}), "body": json_body})
        status, body = self.respostas.pop(0) if len(self.respostas) > 1 else self.respostas[0]
        return http.Response(status, body)


@pytest.fixture
def gemini(monkeypatch, media):
    monkeypatch.setenv("GEMINI_API_KEY", FAKE_KEY)
    monkeypatch.delenv("SIMPLICIO_GEMINI_BASE", raising=False)
    return swap_providers.get("gemini")


def gjob(media, **kw):
    return job(video=media["video"], refs=[media["ref"]], duration_s=6.0, **kw)


def test_gemini_submit_corpo_e_cabecalho(gemini, media, monkeypatch):
    rota = Rota([(200, fx("gemini_in_progress.json"))])
    monkeypatch.setattr(http, "request", rota)
    h = gemini.submit(gjob(media, prompt="troque por <IMAGE_REF_0>"))
    c = rota.calls[0]
    assert c["method"] == "POST" and c["url"] == "https://generativelanguage.googleapis.com/v1beta/interactions"
    assert c["headers"]["x-goog-api-key"] == FAKE_KEY
    b = c["body"]
    assert b["model"] == "gemini-omni-1.1-flash" and b["background"] is True
    assert b["response_format"] == {"type": "video", "resolution": "720p"}
    tipos = [i["type"] for i in b["input"]]
    assert tipos == ["video", "image", "text"]
    assert b["input"][0]["mime_type"] == "video/mp4" and base64.b64decode(b["input"][0]["data"])
    assert b["input"][2]["text"] == "troque por <IMAGE_REF_0>"
    assert h["id"] == "v1_abc123"


def test_gemini_nunca_usa_modo_sincrono(gemini, media, monkeypatch):
    rota = Rota([(200, fx("gemini_in_progress.json"))])
    monkeypatch.setattr(http, "request", rota)
    gemini.submit(gjob(media))
    assert rota.calls[0]["body"].get("background") is True


def test_gemini_poll_estados(gemini, monkeypatch):
    h = {"id": "v1_abc123"}
    monkeypatch.setattr(http, "request", Rota([(200, fx("gemini_in_progress.json"))]))
    assert gemini.poll(h).state == "running"
    monkeypatch.setattr(http, "request", Rota([(200, fx("gemini_completed_data.json"))]))
    assert gemini.poll(h).state == "done"
    monkeypatch.setattr(http, "request", Rota([(200, fx("gemini_failed.json"))]))
    st = gemini.poll(h)
    assert st.state == "failed" and "safety" in st.error


def test_gemini_poll_usa_get_na_url_do_id(gemini, monkeypatch):
    rota = Rota([(200, fx("gemini_in_progress.json"))])
    monkeypatch.setattr(http, "request", rota)
    gemini.poll({"id": "v1_abc123"})
    assert rota.calls[0]["method"] == "GET" and rota.calls[0]["url"].endswith("/v1beta/interactions/v1_abc123")


def test_gemini_parser_video_em_base64(gemini, monkeypatch):
    monkeypatch.setattr(http, "request", Rota([(200, fx("gemini_completed_data.json"))]))
    assert gemini.fetch({"id": "v1_abc123"}) == b"FAKEMP4BYTES"


def test_gemini_parser_video_por_uri(gemini, monkeypatch):
    rota = Rota([(200, fx("gemini_completed_uri.json")), (200, b"BYTES-FROM-URI")])
    monkeypatch.setattr(http, "request", rota)
    assert gemini.fetch({"id": "v1_abc123"}) == b"BYTES-FROM-URI"
    assert "files/abc" in rota.calls[1]["url"]


def test_gemini_parser_sem_video(gemini, monkeypatch):
    monkeypatch.setattr(http, "request", Rota([(200, fx("gemini_completed_no_video.json"))]))
    with pytest.raises(swap_providers.ProviderError, match="vídeo"):
        gemini.fetch({"id": "v1_abc123"})


def test_gemini_custo_medido_quando_ha_uso(gemini, monkeypatch):
    monkeypatch.setattr(http, "request", Rota([(200, fx("gemini_completed_usage.json"))]))
    gemini.fetch({"id": "v1_abc123"})
    assert gemini.measured_usd({"id": "v1_abc123"}) == pytest.approx(57920 * 17.5e-6 + 2000 * 1.5e-6)


def test_gemini_custo_medido_ausente(gemini, monkeypatch):
    monkeypatch.setattr(http, "request", Rota([(200, fx("gemini_completed_data.json"))]))
    gemini.fetch({"id": "v1_abc123"})
    assert gemini.measured_usd({"id": "v1_abc123"}) is None


def test_gemini_plano_gratis_mensagem_clara_e_sem_retry(gemini, media, monkeypatch):
    rota = Rota([(429, fx("gemini_error_free_plan.json"))])
    monkeypatch.setattr(http, "request", rota)
    with pytest.raises(swap_providers.ProviderError) as e:
        swap._com_tentativas(lambda: gemini.submit(gjob(media)), tentativas=[0])
    assert e.value.retryable is False and "faturamento" in str(e.value)
    assert len(rota.calls) == 1


def test_gemini_503_e_transitorio(gemini, media, monkeypatch):
    monkeypatch.setattr(http, "request", Rota([(503, fx("gemini_error_503.json"))]))
    with pytest.raises(swap_providers.ProviderError) as e:
        gemini.submit(gjob(media))
    assert e.value.retryable is True


def test_gemini_base_configuravel(gemini, media, monkeypatch):
    monkeypatch.setenv("SIMPLICIO_GEMINI_BASE", "http://proxy.local/v1beta")
    rota = Rota([(200, fx("gemini_in_progress.json"))])
    monkeypatch.setattr(http, "request", rota)
    gemini.submit(gjob(media))
    assert rota.calls[0]["url"] == "http://proxy.local/v1beta/interactions"


@needs_ffmpeg
def test_gemini_ponta_a_ponta_e_manifesto_sem_segredo(media, monkeypatch, capsys, tmp_path):
    monkeypatch.setenv("GEMINI_API_KEY", FAKE_KEY)
    clip = media["video"].read_bytes()
    completo = json.dumps({"id": "v1_abc123", "status": "completed", "usage": {"total_input_tokens": 1, "total_output_tokens": 1},
                           "steps": [{"type": "model_output", "content": [
                               {"type": "video", "mime_type": "video/mp4", "data": base64.b64encode(clip).decode()}]}]}).encode()
    rota = Rota([(200, fx("gemini_in_progress.json")), (200, fx("gemini_in_progress.json")), (200, completo)])
    monkeypatch.setattr(http, "request", rota)
    out = media["dir"] / "out" / "g.mp4"
    argv = ["run", "--provider", "gemini", "--video", str(media["video"]), "--ref", str(media["ref"]), "--out", str(out),
            "--autorizo", "--yes", "--max-usd", "5", "--json"]
    assert swap.run_swap(argv) == 0
    cap = capsys.readouterr()
    man_text = (media["dir"] / "out" / "swap.manifest.json").read_text()
    for texto in (man_text, cap.out, cap.err):
        assert FAKE_KEY not in texto
    man = json.loads(man_text)
    assert man["model"] == "gemini-omni-1.1-flash" and man["measured_usd"] is not None
    assert all(c["headers"]["x-goog-api-key"] == FAKE_KEY for c in rota.calls)
    assert "x-goog-api-key" not in man_text.lower()


@needs_ffmpeg
def test_gemini_timeout_na_fila(media, monkeypatch, capsys):
    monkeypatch.setenv("GEMINI_API_KEY", FAKE_KEY)
    monkeypatch.setattr(http, "request", Rota([(200, fx("gemini_in_progress.json"))]))
    argv = ["run", "--provider", "gemini", "--video", str(media["video"]), "--ref", str(media["ref"]),
            "--out", str(media["dir"] / "o.mp4"), "--autorizo", "--yes", "--max-usd", "5", "--timeout", "20",
            "--poll-interval", "2"]
    assert swap.run_swap(argv) == 1
    assert "timeout" in capsys.readouterr().err.lower()


def test_manifesto_recusa_gravar_segredo(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", FAKE_KEY)
    with pytest.raises(swap.SwapError, match="segredo"):
        swap.write_manifest(tmp_path / "m.json", {"oops": FAKE_KEY})


# ---------------------------------------------------------------- CLI e MCP

def test_cli_despacha_swap(capsys):
    assert cli.main(["swap", "providers", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["providers"]


def test_help_do_swap(capsys):
    with pytest.raises(SystemExit) as e:
        cli.main(["swap", "--help"])
    assert e.value.code == 0
    out = capsys.readouterr().out
    for termo in ("providers", "estimate", "run", "status", "--autorizo", "--yes", "--max-usd", "exemplos:"):
        assert termo in out


def test_mcp_providers_e_estimate(media):
    r = mcp_server.video_swap("providers")
    assert r["ok"] and {p["name"] for p in r["providers"]} >= {"gemini", "fake"}
    e = mcp_server.video_swap("estimate", provider="fake", video=str(media["video"]), refs=[str(media["ref"])])
    assert e["ok"] and e["estimate"]["usd"] > 0


def test_mcp_nunca_gasta(media):
    r = mcp_server.video_swap("run", provider="fake", video=str(media["video"]), refs=[str(media["ref"])])
    assert r["ok"] is False and "terminal" in r["error"]
    assert fake.FakeAdapter.submits == []


def test_status_mostra_chave_definida_sem_o_valor(monkeypatch):
    from simplicio_video import status
    monkeypatch.setenv("GEMINI_API_KEY", FAKE_KEY)
    rep = {"tools": [], "swap": swap.status_summary()}  # status.report() would read the tool checkouts
    por_nome = {p["name"]: p for p in rep["swap"]}
    assert por_nome["gemini"]["configured"] is True and por_nome["fal"]["configured"] is False
    assert FAKE_KEY not in json.dumps(rep) and FAKE_KEY not in status.text(rep)


def test_mcp_registrado():
    nomes = [t[0] for t in mcp_server.TOOLS]
    assert "video.swap" in nomes
    plugin = json.loads((Path(__file__).resolve().parents[1] / "plugin.json").read_text())
    assert any(v["verb"] == "video.swap" for v in plugin["commands"])
    assert "video.swap" in plugin["mcp"]["tools"]
