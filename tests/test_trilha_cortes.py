"""Arranjo de trilha por `cortes` (critério B do BRASA, etapa 1).

`trilha.music` aceita, além do arquivo, uma lista `cortes` de {de_s, ate_s, em_s, db?, passa_baixa_hz?}. Os trechos são
encadeados com crossfade (padrão 8 ms). Aqui o WAV de 60 s é sintético (senoides de frequências diferentes por trecho,
gerado pelo ffmpeg) e a checagem é por FFT em Python puro (tests/audio_medida.py): duração, ordem dos trechos e
passa-baixa aplicado só no trecho marcado. Sem ffmpeg/ffprobe o teste pula com motivo explícito.
"""
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from audio_medida import freq_dominante, le_wav, potencia_banda_db
from conftest import have_render_tools
from simplicio_video import compiler, trilha
from simplicio_video import contract as ct
from simplicio_video import render, voice

CROSS_S = 0.008  # padrão do crossfade: 8 ms

# trechos da fonte de 60 s (ver _gera_fonte_60s): 200 Hz em 0-10 s, 400 em 10-20, 800 em 20-30, 1600 em 30-40, 300, 600
CORTES = [
    {"de_s": 0.0, "ate_s": 8.0, "em_s": 0.0},
    {"de_s": 20.0, "ate_s": 28.0, "em_s": 7.992, "passa_baixa_hz": 1000},
    {"de_s": 30.0, "ate_s": 38.0, "em_s": 15.984},
]
DURACAO_ESPERADA = 24.0 - 2 * CROSS_S  # 23.984 s: três trechos de 8 s com dois crossfades
JANELA_A, JANELA_B, JANELA_C = 3.0, 12.0, 20.0  # dentro de cada trecho da saída, longe das junções
TAMANHO_JANELA = 1 << 15  # ~0.68 s por medição


def _ffmpeg_ou_pula():
    if not (shutil.which("ffmpeg") and shutil.which("ffprobe")):
        pytest.skip("ffmpeg/ffprobe ausentes neste ambiente: o arranjo por cortes e a checagem de duração precisam deles")


def _gera_fonte_60s(path: Path) -> None:
    """60 s estéreo 48 kHz: um bloco senoidal de 10 s por frequência e um 4 kHz comum a todo o arquivo (medir o passa-baixa)."""
    freqs = [200, 400, 800, 1600, 300, 600]
    entradas, filtros = [], []
    for k, f in enumerate(freqs):
        entradas += ["-f", "lavfi", "-i", f"sine=frequency={f}:duration=10:sample_rate=48000"]
        filtros.append(f"[{k}:a]volume=0.3[b{k}]")
    filtros.append("".join(f"[b{k}]" for k in range(len(freqs))) + f"concat=n={len(freqs)}:v=0:a=1[blocos]")
    entradas += ["-f", "lavfi", "-i", "sine=frequency=4000:duration=60:sample_rate=48000"]
    filtros.append(f"[{len(freqs)}:a]volume=0.05[agudo]")
    filtros.append("[blocos][agudo]amix=inputs=2:normalize=0:duration=first[out]")
    subprocess.run(["ffmpeg", "-v", "error", "-y", *entradas, "-filter_complex", ";".join(filtros), "-map", "[out]",
                    "-ac", "2", "-ar", "48000", "-c:a", "pcm_s16le", str(path)], check=True)


def _duracao(path: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True, check=True).stdout
    return float(out.strip())


@pytest.fixture
def arranjo(tmp_path):
    _ffmpeg_ou_pula()
    fonte = tmp_path / "fonte-60s.wav"
    _gera_fonte_60s(fonte)
    saida = tmp_path / "arranjo.wav"
    info = trilha.monta_arranjo(fonte, CORTES, saida)
    sr, canais = le_wav(saida)
    return saida, info, sr, canais[0]


def test_duracao_da_saida_com_crossfade_de_8_ms(arranjo):
    saida, info, _, _ = arranjo
    assert abs(_duracao(saida) - DURACAO_ESPERADA) <= 0.02
    assert info["crossfade_ms"] == 8
    assert abs(info["duracao_s"] - DURACAO_ESPERADA) <= 0.001


def test_ordem_dos_trechos_pela_frequencia_dominante_por_janela(arranjo):
    _, _, sr, x = arranjo
    # centro de cada trecho na saída, longe das zonas de crossfade (7.992 s, 15.984 s)
    assert freq_dominante(x, sr, JANELA_A, n=TAMANHO_JANELA) == pytest.approx(200, abs=1.0)
    assert freq_dominante(x, sr, JANELA_B, n=TAMANHO_JANELA) == pytest.approx(800, abs=1.0)
    assert freq_dominante(x, sr, JANELA_C, n=TAMANHO_JANELA) == pytest.approx(1600, abs=1.0)


def test_passa_baixa_so_no_trecho_marcado(arranjo):
    _, _, sr, x = arranjo
    agudo_filtrado = potencia_banda_db(x, sr, JANELA_B, 2500, 6000, n=TAMANHO_JANELA)   # passa_baixa_hz = 1000
    agudo_sem_filtro = potencia_banda_db(x, sr, JANELA_C, 2500, 6000, n=TAMANHO_JANELA)  # sem filtro (4 kHz comum)
    assert agudo_filtrado <= agudo_sem_filtro - 30, (agudo_filtrado, agudo_sem_filtro)
    # o corte não apaga o conteúdo grave do trecho filtrado
    assert freq_dominante(x, sr, JANELA_B, n=TAMANHO_JANELA) == pytest.approx(800, abs=1.0)


def test_valida_cortes_confere_em_s_e_recusa_erros():
    em = trilha.valida_cortes(CORTES, crossfade_ms=8)
    assert em == pytest.approx([0.0, 7.992, 15.984], abs=1e-9)
    with pytest.raises(ValueError, match="em_s"):
        trilha.valida_cortes([{"de_s": 0, "ate_s": 8, "em_s": 0}, {"de_s": 20, "ate_s": 28, "em_s": 8.0}], crossfade_ms=8)
    with pytest.raises(ValueError, match="ate_s"):
        trilha.valida_cortes([{"de_s": 8, "ate_s": 8, "em_s": 0}])
    with pytest.raises(ValueError, match="de_s"):
        trilha.valida_cortes([{"de_s": -1, "ate_s": 8, "em_s": 0}])
    with pytest.raises(ValueError, match="cortes"):
        trilha.valida_cortes([])


def test_compile_monta_a_trilha_de_arquivo_e_aponta_o_spec(mini):
    _ffmpeg_ou_pula()
    (mini.parent / "trilha").mkdir()
    _gera_fonte_60s(mini.parent / "trilha" / "fonte-60s.wav")
    d = yaml.safe_load(mini.read_text(encoding="utf8"))
    d["trilha"]["music"]["arquivo"] = "trilha/fonte-60s.wav"
    d["trilha"]["music"]["cortes"] = CORTES
    mini.write_text(yaml.safe_dump(d, allow_unicode=True, sort_keys=False), encoding="utf8")
    c = ct.load(mini)
    voice.run(c, log=lambda *_: None)
    workdir = mini.parent / "wd"
    spec = compiler.compile_project(ct.load(mini), workdir, ct.load_lock(c))
    assert spec["audio"]["music"]["arquivo"] == "assets/audio/trilha/arranjo.wav"
    assert abs(_duracao(workdir / "assets" / "audio" / "trilha" / "arranjo.wav") - DURACAO_ESPERADA) <= 0.02


@pytest.mark.render
@pytest.mark.skipif(not have_render_tools(), reason="precisa de node, npx e ffmpeg")
def test_render_com_trilha_de_arquivo_usa_o_arranjo_no_mix(mini):
    """O build.mjs lê o WAV arranjado no lugar da síntese: sem voz nem SFX, o mix antes do loudnorm tem o 200 Hz do trecho 1."""
    _ffmpeg_ou_pula()
    (mini.parent / "trilha").mkdir()
    _gera_fonte_60s(mini.parent / "trilha" / "fonte-60s.wav")
    d = yaml.safe_load(mini.read_text(encoding="utf8"))
    d["trilha"]["music"]["arquivo"] = "trilha/fonte-60s.wav"
    d["trilha"]["music"]["cortes"] = CORTES
    d["voz"]["habilitada"] = False
    for cena in d["cenas"]:
        cena.pop("sfx", None)
        cena.pop("fala", None)
    mini.write_text(yaml.safe_dump(d, allow_unicode=True, sort_keys=False), encoding="utf8")
    wd = mini.parent / "wd"
    render.render_local(ct.load(mini), out=mini.parent / "out.mp4", workdir=wd, manifest=False, log=lambda *_: None)
    sr, canais = le_wav(wd / "build" / "mix.raw.wav")
    x = canais[0]
    assert freq_dominante(x, sr, 0.0, n=TAMANHO_JANELA) == pytest.approx(200, abs=1.0)  # 0-0.68 s: o vídeo mini tem 1 s


def _mini_com_cortes(mini, cortes):
    (mini.parent / "trilha").mkdir(exist_ok=True)
    (mini.parent / "trilha" / "x.wav").write_bytes(b"RIFF")  # só existência: validate não lê o áudio
    d = yaml.safe_load(mini.read_text(encoding="utf8"))
    d["trilha"]["music"]["arquivo"] = "trilha/x.wav"
    d["trilha"]["music"]["cortes"] = cortes
    mini.write_text(yaml.safe_dump(d, allow_unicode=True, sort_keys=False), encoding="utf8")
    return ct.load(mini)


def test_validate_recusa_em_s_errado(mini):
    from simplicio_video.contract import validate
    c = _mini_com_cortes(mini, [{"de_s": 0, "ate_s": 8, "em_s": 0}, {"de_s": 20, "ate_s": 28, "em_s": 9.0}])
    erros = validate(c).errors
    assert any("trilha" in e and "em_s" in e for e in erros), erros


def test_validate_recusa_cortes_que_nao_cobrem_o_video(mini):
    from simplicio_video.contract import validate
    c = _mini_com_cortes(mini, [{"de_s": 0, "ate_s": 0.5, "em_s": 0}])  # 0.5 s para um vídeo de 1 s
    erros = validate(c).errors
    assert any("trilha" in e and "somam" in e for e in erros), erros


def test_validate_aceita_cortes_consistentes(mini):
    from simplicio_video.contract import validate
    c = _mini_com_cortes(mini, CORTES)
    assert not [e for e in validate(c).errors if "trilha" in e], validate(c).errors
