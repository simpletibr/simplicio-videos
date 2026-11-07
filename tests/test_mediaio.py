"""mediaio (U05.0): the one ffmpeg/ffprobe resolution and the one duration/probe call (U06 moves the callers here).

The errors are the RAW ones of subprocess/float/json: each caller keeps wrapping them as it does today."""
import json
import shutil
import stat
import subprocess
import sys
import wave
from pathlib import Path

import pytest

from simplicio_video import mediaio

TEM_FFPROBE = shutil.which("ffprobe") is not None
precisa_ffprobe = pytest.mark.skipif(not TEM_FFPROBE, reason="precisa do ffprobe")
so_posix = pytest.mark.skipif(sys.platform == "win32", reason="o ffprobe falso é um script com shebang")


@pytest.fixture(autouse=True)
def _sem_dir_travado(monkeypatch):
    monkeypatch.delenv("SIMPLICIO_FFMPEG_DIR", raising=False)


def _wav(tmp_path, segundos: float = 1.5, taxa: int = 8000) -> Path:
    p = tmp_path / "t.wav"
    with wave.open(str(p), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(taxa)
        w.writeframes(b"\x00\x00" * int(segundos * taxa))
    return p


def _falso(dir_: Path, corpo: str, nome: str = "ffprobe") -> Path:
    """A fake ffprobe in `dir_`: a Python script that records its argv in `argv.json` and then runs `corpo`."""
    dir_.mkdir(parents=True, exist_ok=True)
    script = dir_ / nome
    script.write_text(
        f"#!{sys.executable}\n"
        "import json, os, sys, time\n"
        f"open({str(dir_ / 'argv.json')!r}, 'w').write(json.dumps(sys.argv[1:]))\n"
        f"{corpo}\n", encoding="utf8")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return script


# ------------------------------------------------------------------ ffmpeg_bin

def test_ffmpeg_bin_sem_dir_travado_devolve_o_nome():
    assert mediaio.ffmpeg_bin() == "ffmpeg"
    assert mediaio.ffmpeg_bin("ffprobe") == "ffprobe"
    assert mediaio.ffmpeg_bin("ffmpeg") == "ffmpeg"


def test_ffmpeg_bin_com_dir_travado_devolve_o_binario_de_la(tmp_path, monkeypatch):
    (tmp_path / "ffmpeg").write_bytes(b"")
    (tmp_path / "ffprobe").write_bytes(b"")
    monkeypatch.setenv("SIMPLICIO_FFMPEG_DIR", str(tmp_path))
    assert mediaio.ffmpeg_bin() == str(tmp_path / "ffmpeg")
    assert mediaio.ffmpeg_bin("ffprobe") == str(tmp_path / "ffprobe")


def test_ffmpeg_bin_dir_travado_sem_o_binario_cai_no_nome(tmp_path, monkeypatch):
    (tmp_path / "ffmpeg").write_bytes(b"")
    monkeypatch.setenv("SIMPLICIO_FFMPEG_DIR", str(tmp_path))
    assert mediaio.ffmpeg_bin("ffprobe") == "ffprobe"


def test_ffmpeg_bin_dir_travado_inexistente_ou_vazio_cai_no_nome(tmp_path, monkeypatch):
    monkeypatch.setenv("SIMPLICIO_FFMPEG_DIR", str(tmp_path / "nao-existe"))
    assert mediaio.ffmpeg_bin() == "ffmpeg"
    monkeypatch.setenv("SIMPLICIO_FFMPEG_DIR", "")
    assert mediaio.ffmpeg_bin() == "ffmpeg"


def test_ffmpeg_bin_le_o_ambiente_na_hora_da_chamada(tmp_path, monkeypatch):
    (tmp_path / "ffmpeg").write_bytes(b"")
    assert mediaio.ffmpeg_bin() == "ffmpeg"
    monkeypatch.setenv("SIMPLICIO_FFMPEG_DIR", str(tmp_path))
    assert mediaio.ffmpeg_bin() == str(tmp_path / "ffmpeg")


# ------------------------------------------------------------------ duration_s

@precisa_ffprobe
def test_duration_s_de_um_wav_gerado_vale_o_que_se_escreveu(tmp_path):
    d = mediaio.duration_s(_wav(tmp_path, 1.5))
    assert isinstance(d, float)
    assert d == pytest.approx(1.5, abs=0.01)


@precisa_ffprobe
def test_duration_s_aceita_str_e_timeout(tmp_path):
    p = _wav(tmp_path, 0.5)
    assert mediaio.duration_s(str(p), timeout=60) == pytest.approx(0.5, abs=0.01)


@precisa_ffprobe
def test_duration_s_arquivo_ausente_é_calledprocesserror_crua(tmp_path):
    with pytest.raises(subprocess.CalledProcessError):
        mediaio.duration_s(tmp_path / "nao-existe.wav")


@precisa_ffprobe
def test_duration_s_arquivo_que_nao_é_midia_é_calledprocesserror_crua(tmp_path):
    p = tmp_path / "x.wav"
    p.write_text("isto não é áudio", encoding="utf8")
    with pytest.raises(subprocess.CalledProcessError):
        mediaio.duration_s(p)


def test_duration_s_sem_ffprobe_é_filenotfounderror_crua(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", str(tmp_path / "vazio"))
    with pytest.raises(FileNotFoundError):
        mediaio.duration_s(tmp_path / "a.wav")


@so_posix
def test_duration_s_argv_exato(tmp_path, monkeypatch):
    _falso(tmp_path / "bin", "print('2.5')")
    monkeypatch.setenv("SIMPLICIO_FFMPEG_DIR", str(tmp_path / "bin"))
    assert mediaio.duration_s(tmp_path / "a.wav") == 2.5
    assert json.loads((tmp_path / "bin" / "argv.json").read_text()) == [
        "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(tmp_path / "a.wav")]


@so_posix
@pytest.mark.parametrize("saida", ["N/A", "", "abc"])
def test_duration_s_saida_ilegivel_é_valueerror_crua(tmp_path, monkeypatch, saida):
    _falso(tmp_path / "bin", f"print({saida!r})")
    monkeypatch.setenv("SIMPLICIO_FFMPEG_DIR", str(tmp_path / "bin"))
    with pytest.raises(ValueError):
        mediaio.duration_s(tmp_path / "a.wav")


@so_posix
def test_duration_s_ffprobe_com_codigo_de_saida_ruim_é_calledprocesserror_crua(tmp_path, monkeypatch):
    _falso(tmp_path / "bin", "print('1.0'); sys.exit(3)")
    monkeypatch.setenv("SIMPLICIO_FFMPEG_DIR", str(tmp_path / "bin"))
    with pytest.raises(subprocess.CalledProcessError) as e:
        mediaio.duration_s(tmp_path / "a.wav")
    assert e.value.returncode == 3


@so_posix
def test_duration_s_timeout_estourado_é_timeoutexpired_crua(tmp_path, monkeypatch):
    _falso(tmp_path / "bin", "time.sleep(30)")
    monkeypatch.setenv("SIMPLICIO_FFMPEG_DIR", str(tmp_path / "bin"))
    with pytest.raises(subprocess.TimeoutExpired):
        mediaio.duration_s(tmp_path / "a.wav", timeout=0.3)


@so_posix
def test_duration_s_o_filho_nao_herda_o_stdin(tmp_path, monkeypatch):
    _falso(tmp_path / "bin", "print('1.0' if sys.stdin.read() == '' else '9.9')")
    monkeypatch.setenv("SIMPLICIO_FFMPEG_DIR", str(tmp_path / "bin"))
    assert mediaio.duration_s(tmp_path / "a.wav") == 1.0


# ------------------------------------------------------------------ probe

@precisa_ffprobe
def test_probe_de_um_wav_gerado_é_o_json_cru_do_ffprobe(tmp_path):
    info = mediaio.probe(_wav(tmp_path, 1.0, taxa=8000))
    assert isinstance(info, dict)
    assert set(info) == {"streams", "format"}
    (audio,) = info["streams"]
    assert audio["codec_type"] == "audio"
    assert audio["sample_rate"] == "8000"  # raw: ffprobe's own strings, nothing converted
    assert float(info["format"]["duration"]) == pytest.approx(1.0, abs=0.01)
    assert info["format"]["format_name"] == "wav"


@precisa_ffprobe
def test_probe_aceita_str_e_timeout(tmp_path):
    assert "format" in mediaio.probe(str(_wav(tmp_path, 0.5)), timeout=60)


@precisa_ffprobe
def test_probe_arquivo_ausente_é_calledprocesserror_crua(tmp_path):
    with pytest.raises(subprocess.CalledProcessError):
        mediaio.probe(tmp_path / "nao-existe.wav")


def test_probe_sem_ffprobe_é_filenotfounderror_crua(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", str(tmp_path / "vazio"))
    with pytest.raises(FileNotFoundError):
        mediaio.probe(tmp_path / "a.wav")


@so_posix
def test_probe_argv_exato(tmp_path, monkeypatch):
    _falso(tmp_path / "bin", "print('{\"streams\": [], \"format\": {}}')")
    monkeypatch.setenv("SIMPLICIO_FFMPEG_DIR", str(tmp_path / "bin"))
    assert mediaio.probe(tmp_path / "a.mp4") == {"streams": [], "format": {}}
    assert json.loads((tmp_path / "bin" / "argv.json").read_text()) == [
        "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(tmp_path / "a.mp4")]


@so_posix
@pytest.mark.parametrize("saida", ["", "isto nao e json"])
def test_probe_saida_que_nao_é_json_é_valueerror_crua(tmp_path, monkeypatch, saida):
    _falso(tmp_path / "bin", f"sys.stdout.write({saida!r})")
    monkeypatch.setenv("SIMPLICIO_FFMPEG_DIR", str(tmp_path / "bin"))
    with pytest.raises(ValueError):
        mediaio.probe(tmp_path / "a.mp4")


@so_posix
def test_probe_timeout_estourado_é_timeoutexpired_crua(tmp_path, monkeypatch):
    _falso(tmp_path / "bin", "time.sleep(30)")
    monkeypatch.setenv("SIMPLICIO_FFMPEG_DIR", str(tmp_path / "bin"))
    with pytest.raises(subprocess.TimeoutExpired):
        mediaio.probe(tmp_path / "a.mp4", timeout=0.3)


@so_posix
def test_probe_ffprobe_com_codigo_de_saida_ruim_é_calledprocesserror_crua(tmp_path, monkeypatch):
    _falso(tmp_path / "bin", "sys.exit(1)")
    monkeypatch.setenv("SIMPLICIO_FFMPEG_DIR", str(tmp_path / "bin"))
    with pytest.raises(subprocess.CalledProcessError):
        mediaio.probe(tmp_path / "a.mp4")
