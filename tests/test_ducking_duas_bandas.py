"""Ducking em duas bandas sob a voz (critério C do BRASA, etapa 1).

`voz.ducking` (graves_db padrão -2.5 abaixo de 250 Hz; agudos_db padrão -8.0 acima de 2.5 kHz) baixa a trilha de arquivo
só durante os trechos de voz. A trilha é a soma de tons de cada banda (40 e 80 Hz nos graves, 7 e 12 kHz nos agudos,
1 kHz no meio) e a medição é por FFT em Python puro (tests/audio_medida.py), banda a banda:
- dentro da janela: graves -2.5 dB e agudos -8.0 dB (tolerância 0.5 dB);
- fora da janela, e o meio (800-1200 Hz) o tempo todo: sem mudança (tolerância 0.5 dB).
duck_music_db e duck_sfx_db continuam como estavam.
"""
import json
import shutil
from pathlib import Path

import pytest
import yaml

import math

from audio_medida import grava_wav, le_wav, potencia_banda_db, tons
from conftest import LOTHUS
from simplicio_video import compiler, trilha
from simplicio_video import contract as ct
from simplicio_video.contract import schema_errors

SR = 48000
TOL_DB = 0.5
JANELA_VOZ = (4.0, 8.0)  # trecho de voz dentro da trilha de 12 s
N_FFT = 1 << 15          # ~0.68 s por medição
DENTRO = 5.0             # janela de medição dentro do ducking (a rampa de 50 ms termina em 4.05 s)
FORA_ANTES = 1.0
FORA_DEPOIS = 9.0        # a rampa de saída começa em 8.0 s
GRAVES = (20.0, 150.0)
AGUDOS = (5000.0, 15000.0)
MEIO = (800.0, 1200.0)
COMPONENTES_TRILHA = [(40.0, 0.1), (80.0, 0.1), (1000.0, 0.1), (7000.0, 0.1), (12000.0, 0.1)]


def _ffmpeg_ou_pula():
    if not (shutil.which("ffmpeg") and shutil.which("ffprobe")):
        pytest.skip("ffmpeg/ffprobe ausentes neste ambiente: o ducking em duas bandas roda com ffmpeg")


def _delta(entrada, saida, t0, banda):
    return potencia_banda_db(saida, SR, t0, *banda, n=N_FFT) - potencia_banda_db(entrada, SR, t0, *banda, n=N_FFT)


@pytest.fixture
def cenario(tmp_path):
    """Trilha de tons por banda (12 s, estéreo) e voz de tom em 4-8 s; roda trilha.aplica_ducking."""
    _ffmpeg_ou_pula()
    n = 12 * SR
    trilha_wav = tmp_path / "trilha.wav"
    faixa = tons(n, SR, COMPONENTES_TRILHA)
    grava_wav(trilha_wav, [faixa, faixa], SR)
    voz = tons(n, SR, [(1000.0, 0.3)])
    voz = [v if JANELA_VOZ[0] * SR <= i < JANELA_VOZ[1] * SR else 0.0 for i, v in enumerate(voz)]
    grava_wav(tmp_path / "voz.wav", [voz, voz], SR)  # a voz sintética existe no disco, como no compilador
    saida = tmp_path / "trilha-ducked.wav"
    info = trilha.aplica_ducking(trilha_wav, saida, janelas=[JANELA_VOZ], graves_db=-2.5, agudos_db=-8.0)
    _, entrada_c = le_wav(trilha_wav)
    _, saida_c = le_wav(saida)
    return entrada_c[0], saida_c[0], info


def test_dentro_da_janela_graves_caem_2_5_db_e_agudos_8_db(cenario):
    entrada, saida, _ = cenario
    assert _delta(entrada, saida, DENTRO, GRAVES) == pytest.approx(-2.5, abs=TOL_DB)
    assert _delta(entrada, saida, DENTRO, AGUDOS) == pytest.approx(-8.0, abs=TOL_DB)


def test_fora_da_janela_nada_muda(cenario):
    entrada, saida, _ = cenario
    for t0 in (FORA_ANTES, FORA_DEPOIS):
        assert abs(_delta(entrada, saida, t0, GRAVES)) <= TOL_DB, t0
        assert abs(_delta(entrada, saida, t0, AGUDOS)) <= TOL_DB, t0


def test_o_meio_nao_entra_no_ducking(cenario):
    entrada, saida, _ = cenario
    assert abs(_delta(entrada, saida, DENTRO, MEIO)) <= TOL_DB
    assert abs(_delta(entrada, saida, FORA_ANTES, MEIO)) <= TOL_DB


def test_padrao_e_valores_registrados():
    assert trilha.DUCKING_PADRAO == {"graves_db": -2.5, "agudos_db": -8.0}


def test_schema_declara_ducking_com_os_padroes():
    schema = json.loads((Path(__file__).resolve().parents[1] / "src/simplicio_video/data/schema/contract.schema.json").read_text())
    dk = schema["properties"]["voz"]["properties"]["ducking"]["properties"]
    assert dk["graves_db"]["default"] == -2.5 and dk["agudos_db"]["default"] == -8.0
    d = yaml.safe_load(LOTHUS.read_text(encoding="utf8"))
    d["voz"]["ducking"] = {"graves_db": -3.0}
    assert schema_errors(d) == []
    d["voz"]["ducking"] = {"graves_db": -3.0, "medios_db": -1.0}  # banda desconhecida: recusada
    assert any("ducking" in e for e in schema_errors(d))


def test_duck_music_db_e_duck_sfx_db_continuam_no_spec(mini):
    spec = compiler.build_spec(ct.load(mini), None)
    assert spec["voice"]["duck_music_db"] == 6 and spec["voice"]["duck_sfx_db"] == 3


def _rms_db(x, sr, t0, t1):
    seg = x[int(t0 * sr):int(t1 * sr)]
    return 10 * math.log10(sum(v * v for v in seg) / len(seg))


def test_prepara_aplica_o_ducking_so_na_janela_da_fala(mini, tmp_path):
    """Compilador: a janela vem do timing.lock.json. Dentro da fala o tom de 100 Hz cai 2.5 dB; fora, a saída é igual à da trilha sem ducking."""
    _ffmpeg_ou_pula()
    from simplicio_video import voice
    (mini.parent / "trilha").mkdir()
    grava_wav(mini.parent / "trilha" / "tom.wav", [tons(2 * SR, SR, [(100.0, 0.2)])] * 2, SR)
    d = yaml.safe_load(mini.read_text(encoding="utf8"))
    d["trilha"]["music"]["arquivo"] = "trilha/tom.wav"
    d["voz"]["ducking"] = {}
    mini.write_text(yaml.safe_dump(d, allow_unicode=True, sort_keys=False), encoding="utf8")
    c = ct.load(mini)
    lock = voice.run(c, log=lambda *_: None)
    (t0, t1), = trilha.janelas_de_voz(c, lock)
    assert t0 == pytest.approx(0.05) and t1 == pytest.approx(0.05 + lock["lines"]["vo1"]["dur_s"])
    com = trilha.prepara(c, tmp_path / "com", lock)
    d["voz"].pop("ducking")
    mini.write_text(yaml.safe_dump(d, allow_unicode=True, sort_keys=False), encoding="utf8")
    sem = trilha.prepara(ct.load(mini), tmp_path / "sem", lock)
    a = le_wav(tmp_path / "sem" / com)[1][0]
    b = le_wav(tmp_path / "com" / com)[1][0]
    assert _rms_db(b, SR, 0.12, 0.22) - _rms_db(a, SR, 0.12, 0.22) == pytest.approx(-2.5, abs=TOL_DB)
    assert a[int(0.5 * SR):int(0.9 * SR)] == b[int(0.5 * SR):int(0.9 * SR)]
    assert sem == com


def test_validate_avisa_ducking_sem_trilha_de_arquivo(mini):
    from simplicio_video.contract import validate
    d = yaml.safe_load(mini.read_text(encoding="utf8"))
    d["voz"]["ducking"] = {}
    mini.write_text(yaml.safe_dump(d, allow_unicode=True, sort_keys=False), encoding="utf8")
    avisos = validate(ct.load(mini)).warnings
    assert any("ducking" in a and "trilha.music.arquivo" in a for a in avisos), avisos
