"""Arranjo de trilha por `cortes` (critério B do BRASA, etapa 1).

`trilha.music` aceita, além do arquivo, uma lista `cortes` de {de_s, ate_s, em_s, db?, passa_baixa_hz?}. Os trechos são
encadeados com crossfade (padrão 8 ms). Aqui o WAV de 60 s é sintético (senoides de frequências diferentes por trecho)
e a checagem é por FFT: duração, ordem dos trechos e passa-baixa aplicado só no trecho marcado.
Sem ffmpeg/ffprobe o teste pula com motivo explícito.
"""
import shutil
import subprocess
import wave
from pathlib import Path

import numpy as np
import pytest
import yaml

from simplicio_video import compiler, contract as ct, trilha, voice

SR = 48000
CROSS_S = 0.008  # padrão do crossfade: 8 ms

# trechos da fonte de 60 s (ver _fonte_60s): 200 Hz em 0-10 s, 800 Hz em 20-30 s, 1600 Hz em 40-50 s
CORTES = [
    {"de_s": 0.0, "ate_s": 8.0, "em_s": 0.0},
    {"de_s": 20.0, "ate_s": 28.0, "em_s": 7.992, "passa_baixa_hz": 1000},
    {"de_s": 40.0, "ate_s": 48.0, "em_s": 15.984},
]
DURACAO_ESPERADA = 24.0 - 2 * CROSS_S  # 23.984 s: três trechos de 8 s com dois crossfades


def _ffmpeg_ou_pula():
    if not (shutil.which("ffmpeg") and shutil.which("ffprobe")):
        pytest.skip("ffmpeg/ffprobe ausentes neste ambiente: o arranjo por cortes e a checagem de duração precisam deles")


def _fonte_60s():
    """60 s estéreo 48 kHz: uma senoide por bloco de 10 s e um 4 kHz comum a todo o arquivo (para medir o passa-baixa)."""
    t = np.arange(60 * SR) / SR
    x = np.zeros_like(t)
    for k, f in enumerate([200, 400, 800, 1600, 300, 600]):
        m = (t >= 10 * k) & (t < 10 * (k + 1))
        x[m] = 0.3 * np.sin(2 * np.pi * f * t[m])
    x += 0.05 * np.sin(2 * np.pi * 4000 * t)
    return np.stack([x, x], axis=1)


def _grava_wav(path: Path, x: np.ndarray, sr: int = SR) -> None:
    """x: (n, canais) em ponto flutuante [-1, 1] -> WAV PCM 16 bits."""
    pcm = np.clip(np.round(x * 32767), -32768, 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(x.shape[1])
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())


def _le_wav(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as w:
        n, ch = w.getnframes(), w.getnchannels()
        raw = np.frombuffer(w.readframes(n), dtype="<i2").astype(np.float64) / 32768.0
    return raw.reshape(n, ch)


def _duracao(path: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True, check=True).stdout
    return float(out.strip())


def _espectro(x: np.ndarray, t0: float, t1: float):
    seg = x[int(t0 * SR):int(t1 * SR), 0]
    seg = seg * np.hanning(len(seg))
    return np.fft.rfftfreq(len(seg), 1 / SR), np.abs(np.fft.rfft(seg))


def _freq_dominante(x, t0, t1, f0=50.0, f1=2500.0):
    f, mag = _espectro(x, t0, t1)
    m = (f >= f0) & (f <= f1)
    return float(f[m][np.argmax(mag[m])])


def _energia_db(x, t0, t1, f0, f1):
    f, mag = _espectro(x, t0, t1)
    m = (f >= f0) & (f <= f1)
    return 10 * np.log10(np.sum(mag[m] ** 2))


@pytest.fixture
def arranjo(tmp_path):
    _ffmpeg_ou_pula()
    fonte = tmp_path / "fonte-60s.wav"
    _grava_wav(fonte, _fonte_60s())
    saida = tmp_path / "arranjo.wav"
    info = trilha.monta_arranjo(fonte, CORTES, saida)
    return saida, info


def test_duracao_da_saida_com_crossfade_de_8_ms(arranjo):
    saida, info = arranjo
    assert abs(_duracao(saida) - DURACAO_ESPERADA) <= 0.02
    assert info["crossfade_ms"] == 8
    assert abs(info["duracao_s"] - DURACAO_ESPERADA) <= 0.001


def test_ordem_dos_trechos_pela_frequencia_dominante_por_janela(arranjo):
    saida, _ = arranjo
    x = _le_wav(saida)
    # centro de cada trecho na saída, longe das zonas de crossfade (7.992 s, 15.984 s)
    assert _freq_dominante(x, 1.0, 7.0) == pytest.approx(200, abs=1.0)
    assert _freq_dominante(x, 9.0, 15.0) == pytest.approx(800, abs=1.0)
    assert _freq_dominante(x, 17.0, 23.0) == pytest.approx(1600, abs=1.0)


def test_passa_baixa_so_no_trecho_marcado(arranjo):
    saida, _ = arranjo
    x = _le_wav(saida)
    agudo_filtrado = _energia_db(x, 9.0, 15.0, 2500, 6000)   # trecho com passa_baixa_hz = 1000
    agudo_sem_filtro = _energia_db(x, 17.0, 23.0, 2500, 6000)  # trecho sem filtro (1600 Hz + 4 kHz comum)
    assert agudo_filtrado <= agudo_sem_filtro - 30, (agudo_filtrado, agudo_sem_filtro)
    # e o trecho filtrado continua com o seu tom (o corte não apaga o conteúdo grave)
    assert _freq_dominante(x, 9.0, 15.0) == pytest.approx(800, abs=1.0)


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


def test_compile_monta_a_trilha_de_arquivo_e_aponta_o_spec(mini, tmp_path):
    _ffmpeg_ou_pula()
    (mini.parent / "trilha").mkdir()
    _grava_wav(mini.parent / "trilha" / "fonte-60s.wav", _fonte_60s())
    d = yaml.safe_load(mini.read_text(encoding="utf8"))
    d["trilha"]["music"]["arquivo"] = "trilha/fonte-60s.wav"
    d["trilha"]["music"]["cortes"] = CORTES
    mini.write_text(yaml.safe_dump(d, allow_unicode=True, sort_keys=False), encoding="utf8")
    c = ct.load(mini)
    voice.run(c, log=lambda *_: None)
    workdir = tmp_path / "wd"
    spec = compiler.compile_project(ct.load(mini), workdir, ct.load_lock(c))
    assert spec["audio"]["music"]["arquivo"] == "assets/audio/trilha/arranjo.wav"
    arr = workdir / "assets" / "audio" / "trilha" / "arranjo.wav"
    assert abs(_duracao(arr) - DURACAO_ESPERADA) <= 0.02
