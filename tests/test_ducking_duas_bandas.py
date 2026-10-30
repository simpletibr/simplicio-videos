"""Ducking em duas bandas sob a voz (critério C do BRASA, etapa 1).

`voz.ducking` (graves_db padrão -2.5 abaixo de 250 Hz; agudos_db padrão -8.0 acima de 2.5 kHz) baixa a trilha só durante
os trechos de voz. Medição por FFT em bandas, com trilha (ruído) e voz (tom) sintéticas geradas no teste:
- dentro da janela: graves -2.5 dB e agudos -8.0 dB (tolerância 0.5 dB);
- fora da janela e no meio (800-1200 Hz): sem mudança (tolerância 0.5 dB).
duck_music_db e duck_sfx_db continuam como estavam.
"""
import json
import shutil
import wave
from pathlib import Path

import numpy as np
import pytest
import yaml

from conftest import LOTHUS
from simplicio_video import compiler, trilha
from simplicio_video import contract as ct
from simplicio_video.contract import schema_errors

SR = 48000
TOL_DB = 0.5
JANELA_VOZ = (4.0, 8.0)  # trecho de voz dentro da trilha de 12 s
# medição: bem dentro de cada região, longe das rampas de entrada e saída do ducking
DENTRO = (4.5, 7.5)
FORA_ANTES = (0.5, 3.5)
FORA_DEPOIS = (8.5, 11.5)
GRAVES = (20.0, 80.0)      # abaixo de 250 Hz, sem a borda do corte
AGUDOS = (8000.0, 20000.0)  # acima de 2.5 kHz, sem a borda do corte
MEIO = (800.0, 1200.0)      # fora das duas bandas: não pode mudar


def _ffmpeg_ou_pula():
    if not (shutil.which("ffmpeg") and shutil.which("ffprobe")):
        pytest.skip("ffmpeg/ffprobe ausentes neste ambiente: o ducking em duas bandas roda com ffmpeg")


def _grava_wav(path: Path, x: np.ndarray) -> None:
    pcm = np.clip(np.round(x * 32767), -32768, 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(x.shape[1])
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


def _le_wav(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as w:
        n, ch = w.getnframes(), w.getnchannels()
        raw = np.frombuffer(w.readframes(n), dtype="<i2").astype(np.float64) / 32768.0
    return raw.reshape(n, ch)


def _energia_banda(x: np.ndarray, t0: float, t1: float, f0: float, f1: float) -> float:
    """Potência (dB) da banda f0..f1 no trecho t0..t1, canal esquerdo, janela de Hann."""
    seg = x[int(t0 * SR):int(t1 * SR), 0]
    seg = seg * np.hanning(len(seg))
    f = np.fft.rfftfreq(len(seg), 1 / SR)
    mag2 = np.abs(np.fft.rfft(seg)) ** 2
    m = (f >= f0) & (f <= f1)
    return 10 * np.log10(np.sum(mag2[m]))


def _delta(entrada: np.ndarray, saida: np.ndarray, janela, banda) -> float:
    return _energia_banda(saida, *janela, *banda) - _energia_banda(entrada, *janela, *banda)


@pytest.fixture
def cenario(tmp_path):
    """Trilha de ruído branco (banda larga) de 12 s e voz de tom em 4-8 s; roda trilha.aplica_ducking."""
    _ffmpeg_ou_pula()
    rng = np.random.default_rng(20261030)
    n = 12 * SR
    trilha_wav = tmp_path / "trilha.wav"
    _grava_wav(trilha_wav, np.stack([rng.uniform(-0.2, 0.2, n), rng.uniform(-0.2, 0.2, n)], axis=1))
    t = np.arange(n) / SR
    voz = np.zeros(n)
    m = (t >= JANELA_VOZ[0]) & (t < JANELA_VOZ[1])
    voz[m] = 0.3 * np.sin(2 * np.pi * 1000 * t[m])
    voz_wav = tmp_path / "voz.wav"
    _grava_wav(voz_wav, np.stack([voz, voz], axis=1))
    saida = tmp_path / "trilha-ducked.wav"
    info = trilha.aplica_ducking(trilha_wav, saida, janelas=[JANELA_VOZ], graves_db=-2.5, agudos_db=-8.0)
    return _le_wav(trilha_wav), _le_wav(saida), info


def test_dentro_da_janela_graves_caem_2_5_db_e_agudos_8_db(cenario):
    entrada, saida, _ = cenario
    assert _delta(entrada, saida, DENTRO, GRAVES) == pytest.approx(-2.5, abs=TOL_DB)
    assert _delta(entrada, saida, DENTRO, AGUDOS) == pytest.approx(-8.0, abs=TOL_DB)


def test_fora_da_janela_nada_muda(cenario):
    entrada, saida, _ = cenario
    for janela in (FORA_ANTES, FORA_DEPOIS):
        assert abs(_delta(entrada, saida, janela, GRAVES)) <= TOL_DB
        assert abs(_delta(entrada, saida, janela, AGUDOS)) <= TOL_DB


def test_o_meio_nao_entra_no_ducking(cenario):
    entrada, saida, _ = cenario
    assert abs(_delta(entrada, saida, DENTRO, MEIO)) <= TOL_DB


def test_padrao_e_valores_registrados():
    assert trilha.DUCKING_PADRAO == {"graves_db": -2.5, "agudos_db": -8.0}


def test_schema_declara_ducking_com_os_padroes_e_mantem_duck_music_e_sfx():
    schema = json.loads((Path(__file__).resolve().parents[1] / "src/simplicio_video/data/schema/contract.schema.json").read_text())
    dk = schema["properties"]["voz"]["properties"]["ducking"]["properties"]
    assert dk["graves_db"]["default"] == -2.5 and dk["agudos_db"]["default"] == -8.0
    d = yaml.safe_load(LOTHUS.read_text(encoding="utf8"))
    d["voz"]["ducking"] = {"graves_db": -3.0}
    assert schema_errors(d) == []
    # duck_music_db e duck_sfx_db continuam válidos e chegam ao spec como antes
    d["voz"].update(duck_music_db=6, duck_sfx_db=3)
    assert schema_errors(d) == []


def test_compile_mantem_duck_music_e_duck_sfx_no_spec(mini):
    spec = compiler.build_spec(ct.load(mini), None)
    assert spec["voice"]["duck_music_db"] == 6 and spec["voice"]["duck_sfx_db"] == 3
