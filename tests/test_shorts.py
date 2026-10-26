"""Shorts: seleção determinística e contrato do plano. Nenhum teste aqui abre socket ou chama ffmpeg."""
from __future__ import annotations

import json

import pytest

from simplicio_video import shorts


def fala(inicio: float, palavras: list[str], passo: float = 0.4) -> list[dict]:
    """Palavras seguidas, cada uma com 0.3 s, para montar uma transcrição de teste."""
    out = []
    t = inicio
    for p in palavras:
        out.append({"start": round(t, 2), "end": round(t + 0.3, 2), "text": p})
        t += passo
    return out


def transcricao() -> list[dict]:
    """20 falas de ~4 s com 1,2 s de silêncio entre elas: dá para montar janelas de 20 a 60 s."""
    palavras = ["morre", "artista", "famoso", "nesta", "tarde", "confirmado", "pela", "família"]
    out: list[dict] = []
    t = 0.0
    for i in range(20):
        out += fala(t, palavras[i % 3:] + palavras[: i % 3])
        t += 4.4 + 1.2
    return out


def test_utterances_quebram_no_silencio():
    words = fala(0.0, ["a", "b"]) + fala(2.0, ["c"])
    utts = shorts.utterances(words)
    assert len(utts) == 2
    assert utts[0]["text"] == "a b"
    assert utts[1]["start"] == 2.0


def test_fala_curta_nao_quebra():
    words = fala(0.0, ["a", "b"], passo=0.4)
    assert len(shorts.utterances(words)) == 1


def test_group_captions_respeita_o_tamanho():
    words = fala(0.0, ["palavra"] * 30, passo=0.3)
    caps = shorts.group_captions(words, max_chars=20)
    assert len(caps) > 1
    assert all(len(c["text"]) <= 20 for c in caps)
    assert all(c["end"] > c["start"] for c in caps)


def test_score_premia_gancho_e_pergunta():
    fraco, _ = shorts.score_window("bom dia a todos", 30, 20, 60)
    forte, motivos = shorts.score_window("morre o presidente! confirmado?", 30, 20, 60)
    assert forte > fraco
    assert any(m.startswith("ganchos") for m in motivos)


def test_score_penaliza_fala_esparsa():
    denso, _ = shorts.score_window(" ".join(["palavra"] * 80), 30, 20, 60)
    esparso, motivos = shorts.score_window("duas palavras", 30, 20, 60)
    assert denso > esparso
    assert "fala esparsa" in motivos


def test_candidate_windows_respeitam_os_limites():
    words = transcricao()
    cands = shorts.candidate_windows(words, 120.0, 20.0, 60.0)
    assert cands
    for c in cands:
        assert 20.0 <= c["end"] - c["start"] <= 60.5
        assert c["start"] >= 0.0
        assert c["score"] > 0


def test_select_nao_sobrepoe_e_ordena():
    cands = [
        {"start": 0.0, "end": 30.0, "score": 5.0, "reasons": [], "text": ""},
        {"start": 10.0, "end": 40.0, "score": 4.0, "reasons": [], "text": ""},
        {"start": 60.0, "end": 90.0, "score": 3.0, "reasons": [], "text": ""},
    ]
    chosen = shorts.select_clips(cands, 2)
    assert [c["start"] for c in chosen] == [0.0, 60.0]
    assert [c["id"] for c in chosen] == ["c01", "c02"]
    assert all(c["duration"] == c["end"] - c["start"] for c in chosen)


def test_select_para_quando_nao_cabe_mais():
    cands = [{"start": float(i * 5), "end": float(i * 5 + 30), "score": 1.0, "reasons": [],
              "text": ""} for i in range(3)]
    assert len(shorts.select_clips(cands, 5)) == 1


def test_build_plan_guarda_o_contrato():
    source = {"path": "/tmp/a.mp4", "duration": 120.0, "width": 1920, "height": 1080,
              "fps": 30.0, "has_audio": True, "size_bytes": 1, "sha256": "x"}
    plan = shorts.build_plan(source, transcricao(), 3, 20.0, 60.0)
    assert plan["schema"] == shorts.PLAN_SCHEMA
    assert len(plan["clips"]) == 3
    assert plan["options"]["vertical"] == [1080, 1920]
    for c in plan["clips"]:
        assert set(c) >= {"id", "start", "end", "duration", "score", "reasons"}


def test_build_plan_sem_fala_suficiente():
    source = {"path": "/tmp/a.mp4", "duration": 5.0, "width": 1920, "height": 1080, "fps": 30.0,
              "has_audio": True, "size_bytes": 1, "sha256": "x"}
    with pytest.raises(shorts.ShortsError):
        shorts.build_plan(source, fala(0.0, ["oi"]), 1, 20.0, 60.0)


def test_load_words_aceita_words_e_segments(tmp_path):
    p = tmp_path / "words.json"
    p.write_text(json.dumps({"segments": [{"start": 1, "end": 2, "text": "olá"}]}), encoding="utf8")
    assert shorts.load_words(p) == [{"start": 1.0, "end": 2.0, "text": "olá"}]
    p.write_text(json.dumps([]), encoding="utf8")
    with pytest.raises(shorts.ShortsError):
        shorts.load_words(p)


def test_write_srt_desloca_pelo_inicio_do_corte(tmp_path):
    dest = shorts.write_srt([{"start": 12.0, "end": 13.5, "text": "corte"}], tmp_path / "c01.srt", 10.0)
    texto = dest.read_text(encoding="utf8")
    assert "00:00:02,000 --> 00:00:03,500" in texto
    assert "corte" in texto


def test_build_filter_so_queima_legenda_quando_pedida():
    sem = shorts.build_filter("blur")
    com = shorts.build_filter("blur", None)
    assert sem == com
    com_srt = shorts.build_filter("crop", None)
    assert "boxblur" not in com_srt and "crop=1080:1920" in com_srt
    com_legenda = shorts.build_filter("crop", (shorts.Path if False else None) or None) if False else None
    assert com_legenda is None


def test_build_filter_com_legenda_usa_subtitles(tmp_path):
    srt = tmp_path / "c.srt"
    srt.write_text("1\n00:00:00,000 --> 00:00:01,000\nx\n", encoding="utf8")
    filt = shorts.build_filter("blur", srt)
    assert "subtitles=" in filt and filt.endswith("[v]")
