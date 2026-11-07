"""mediaio (U05.0): the one ffmpeg/ffprobe resolution and the one duration/probe call (U06 moves the callers here).

The errors are the RAW ones of subprocess/float/json: each caller keeps wrapping them as it does today."""
import json
import os
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


# ------------------------------------------------------------------ U06: the binary, the environment and the raw run

@so_posix
def test_path_ffprobe_é_o_nome_sem_pasta_e_ignora_o_dir_travado(tmp_path, monkeypatch):
    assert mediaio.PATH_FFPROBE == "ffprobe"
    _falso(tmp_path / "travado", "print('42.0')")
    _falso(tmp_path / "path", "print('1.5')")
    monkeypatch.setenv("SIMPLICIO_FFMPEG_DIR", str(tmp_path / "travado"))
    monkeypatch.setenv("PATH", str(tmp_path / "path"))
    assert mediaio.duration_s(tmp_path / "a.wav") == 42.0  # None: the resolution of mediaio (the locked folder wins)
    assert mediaio.duration_s(tmp_path / "a.wav", ffprobe=mediaio.PATH_FFPROBE) == 1.5  # the bare name: the PATH only


def test_ffprobe_cmd_monta_o_argv_e_o_binario_explicito_vence_o_dir_travado(tmp_path, monkeypatch):
    (tmp_path / "ffprobe").write_bytes(b"")
    monkeypatch.setenv("SIMPLICIO_FFMPEG_DIR", str(tmp_path))
    alvo = tmp_path / "a.mp4"
    assert mediaio.ffprobe_cmd(["-show_format"], alvo) == [str(tmp_path / "ffprobe"), "-v", "error", "-show_format", str(alvo)]
    assert mediaio.ffprobe_cmd(["-show_format"], str(alvo), ffprobe="ffprobe") == ["ffprobe", "-v", "error", "-show_format", str(alvo)]
    assert mediaio.ffprobe_cmd([], "x", ffprobe="/opt/ff/ffprobe")[0] == "/opt/ff/ffprobe"
    assert isinstance(mediaio.ffprobe_cmd([], "x"), list)


def test_ffprobe_cmd_sem_dir_travado_usa_o_nome(tmp_path):
    assert mediaio.ffprobe_cmd(["-x"], "a") == ["ffprobe", "-v", "error", "-x", "a"]


def test_as_constantes_de_argv_sao_as_que_os_chamadores_usam_hoje():
    assert tuple(mediaio.DURATION_ARGS) == ("-show_entries", "format=duration", "-of", "csv=p=0")
    assert tuple(mediaio.PROBE_ARGS) == ("-print_format", "json", "-show_format", "-show_streams")


@so_posix
def test_run_ffprobe_devolve_o_processo_sem_levantar_com_check_falso(tmp_path, monkeypatch):
    _falso(tmp_path / "bin", "sys.stdout.write('saida'); sys.stderr.write('erro'); sys.exit(4)")
    p = mediaio.run_ffprobe(["-x"], tmp_path / "a.wav", ffprobe=str(tmp_path / "bin" / "ffprobe"), check=False)
    assert (p.returncode, p.stdout, p.stderr) == (4, "saida", "erro")
    assert isinstance(p.stdout, str)  # text=True
    with pytest.raises(subprocess.CalledProcessError) as e:
        mediaio.run_ffprobe(["-x"], tmp_path / "a.wav", ffprobe=str(tmp_path / "bin" / "ffprobe"))
    assert (e.value.returncode, e.value.stdout, e.value.stderr) == (4, "saida", "erro")


@so_posix
def test_run_ffprobe_o_filho_tem_o_stdin_em_dev_null_e_recebe_o_ambiente_dado(tmp_path, monkeypatch):
    corpo = ("import os\n"
             "dev_null = os.path.samestat(os.fstat(0), os.stat('/dev/null'))\n"
             "print(json.dumps({'dev_null': dev_null, 'marca': os.environ.get('MARCA'), 'path': os.environ.get('PATH')}))")
    _falso(tmp_path / "bin", corpo)
    ff = str(tmp_path / "bin" / "ffprobe")
    monkeypatch.setenv("MARCA", "do-processo")
    visto = json.loads(mediaio.run_ffprobe([], "a", ffprobe=ff).stdout)
    assert visto["dev_null"] is True and visto["marca"] == "do-processo"
    visto = json.loads(mediaio.run_ffprobe([], "a", ffprobe=ff, env={"MARCA": "do-env", "PATH": "/x"}).stdout)
    assert (visto["marca"], visto["path"]) == ("do-env", "/x")


@so_posix
def test_run_ffprobe_o_nome_sem_pasta_é_achado_no_path_do_env_dado(tmp_path, monkeypatch):
    _falso(tmp_path / "so-no-env", "print('7.0')")
    monkeypatch.setenv("PATH", str(tmp_path / "vazio"))
    with pytest.raises(FileNotFoundError):
        mediaio.run_ffprobe([], "a", ffprobe=mediaio.PATH_FFPROBE)
    p = mediaio.run_ffprobe([], "a", ffprobe=mediaio.PATH_FFPROBE, env={"PATH": str(tmp_path / "so-no-env")})
    assert p.stdout == "7.0\n"


@so_posix
def test_run_ffprobe_o_argv_é_uma_tupla_como_o_do_voice_sh(tmp_path):
    """str(CalledProcessError) prints the argv: voice.duration (through voice.sh) always showed the tuple."""
    _falso(tmp_path / "bin", "sys.exit(2)")
    with pytest.raises(subprocess.CalledProcessError) as e:
        mediaio.run_ffprobe(["-x"], "a", ffprobe=str(tmp_path / "bin" / "ffprobe"))
    assert e.value.cmd == (str(tmp_path / "bin" / "ffprobe"), "-v", "error", "-x", "a")


@so_posix
def test_run_ffprobe_timeout_estourado(tmp_path):
    _falso(tmp_path / "bin", "time.sleep(30)")
    with pytest.raises(subprocess.TimeoutExpired):
        mediaio.run_ffprobe([], "a", ffprobe=str(tmp_path / "bin" / "ffprobe"), timeout=0.3)


@so_posix
def test_duration_s_com_check_falso_ignora_o_codigo_de_saida_e_a_saida_vazia_é_valueerror(tmp_path):
    _falso(tmp_path / "bin", "print('7.5'); sys.exit(3)")
    ff = str(tmp_path / "bin" / "ffprobe")
    assert mediaio.duration_s("a", ffprobe=ff, check=False) == 7.5
    with pytest.raises(subprocess.CalledProcessError):
        mediaio.duration_s("a", ffprobe=ff)
    _falso(tmp_path / "vazio", "sys.exit(1)")
    with pytest.raises(ValueError, match="could not convert string to float: ''"):
        mediaio.duration_s("a", ffprobe=str(tmp_path / "vazio" / "ffprobe"), check=False)


@so_posix
def test_duration_s_e_probe_aceitam_o_binario_e_o_ambiente(tmp_path, monkeypatch):
    _falso(tmp_path / "bin", "print(os.environ.get('MARCA', '0') if '-print_format' not in sys.argv else '{\"format\": {\"duration\": \"3\"}}')")
    ff = str(tmp_path / "bin" / "ffprobe")
    assert mediaio.duration_s("a", ffprobe=ff, env={"MARCA": "9.5", "PATH": os.environ["PATH"]}) == 9.5
    assert mediaio.probe("a", ffprobe=ff, env={"PATH": os.environ["PATH"]}) == {"format": {"duration": "3"}}


@so_posix
def test_probe_resolve_o_binario_na_hora_da_chamada_e_o_explicito_vence(tmp_path, monkeypatch):
    _falso(tmp_path / "travado", "print('{\"id\": \"travado\"}')")
    _falso(tmp_path / "path", "print('{\"id\": \"path\"}')")
    monkeypatch.setenv("SIMPLICIO_FFMPEG_DIR", str(tmp_path / "travado"))
    monkeypatch.setenv("PATH", str(tmp_path / "path"))
    assert mediaio.probe("a") == {"id": "travado"}
    assert mediaio.probe("a", ffprobe=mediaio.PATH_FFPROBE) == {"id": "path"}


# ------------------------------------------------------------------ U06: the summary of the first video stream (shorts and media)

class _Erro(Exception):
    pass


def _json_falso(tmp_path: Path, doc: dict | None, stderr: str = "", codigo: int = 0, cru: str | None = None) -> str:
    saida = cru if cru is not None else ("" if doc is None else json.dumps(doc))
    _falso(tmp_path / "bin", f"sys.stdout.write({saida!r}); sys.stderr.write({stderr!r}); sys.exit({codigo})")
    return str(tmp_path / "bin" / "ffprobe")


VIDEO = {"codec_type": "video", "width": 1080, "height": 1920, "avg_frame_rate": "30000/1001", "r_frame_rate": "30/1"}
AUDIO = {"codec_type": "audio"}


@so_posix
def test_probe_summary_resume_o_primeiro_video_e_calcula_tamanho_e_sha256(tmp_path):
    ff = _json_falso(tmp_path, {"streams": [AUDIO, VIDEO], "format": {"duration": "12.3456"}})
    arq = tmp_path / "v.mp4"
    arq.write_bytes(b"abc")
    r = mediaio.probe_summary(arq, ffprobe=ff, fail=_Erro)
    assert r == {"path": str(arq), "duration": 12.346, "width": 1080, "height": 1920, "fps": 29.97, "has_audio": True, "size_bytes": 3,
                 "sha256": "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"}
    assert list(r) == ["path", "duration", "width", "height", "fps", "has_audio", "size_bytes", "sha256"]
    assert json.loads((tmp_path / "bin" / "argv.json").read_text()) == [
        "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(arq)]


@so_posix
def test_probe_summary_sem_audio_duracao_do_stream_e_fps_do_r_frame_rate(tmp_path):
    video = {"codec_type": "video", "width": 2, "height": 4, "r_frame_rate": "25/1", "duration": "2.5"}
    ff = _json_falso(tmp_path, {"streams": [video], "format": {}})
    arq = tmp_path / "v.mp4"
    arq.write_bytes(b"")
    r = mediaio.probe_summary(arq, ffprobe=ff, fail=_Erro)
    assert (r["duration"], r["fps"], r["has_audio"]) == (2.5, 25.0, False)


@so_posix
def test_probe_summary_duracao_ilegivel_vira_zero_e_largura_ausente_vira_zero(tmp_path):
    ff = _json_falso(tmp_path, {"streams": [{"codec_type": "video"}], "format": {"duration": "N/A"}})
    arq = tmp_path / "v.mp4"
    arq.write_bytes(b"")
    r = mediaio.probe_summary(arq, ffprobe=ff, fail=_Erro)
    assert (r["duration"], r["width"], r["height"], r["fps"]) == (0.0, 0, 0, 0.0)


@so_posix
def test_probe_summary_o_erro_é_o_do_chamador_com_a_mensagem_do_ffprobe(tmp_path):
    arq = tmp_path / "v.mp4"
    arq.write_bytes(b"")
    ff = _json_falso(tmp_path, None, stderr="  linha 1\nlinha 2\n", codigo=1)
    with pytest.raises(_Erro) as e:
        mediaio.probe_summary(arq, ffprobe=ff, fail=_Erro)
    assert type(e.value) is _Erro and str(e.value) == "linha 1\nlinha 2"
    ff = _json_falso(tmp_path, None, stderr="", codigo=1)
    with pytest.raises(_Erro, match=f"^ffprobe falhou em {arq}$"):
        mediaio.probe_summary(arq, ffprobe=ff, fail=_Erro)
    ff = _json_falso(tmp_path, {"streams": [AUDIO], "format": {}})
    with pytest.raises(_Erro, match=f"^sem trilha de vídeo: {arq}$"):
        mediaio.probe_summary(arq, ffprobe=ff, fail=_Erro)
    ff = _json_falso(tmp_path, None)  # exit 0 and nothing printed: no streams
    with pytest.raises(_Erro, match=f"^sem trilha de vídeo: {arq}$"):
        mediaio.probe_summary(arq, ffprobe=ff, fail=_Erro)


@so_posix
def test_probe_summary_json_ilegivel_é_valueerror_crua_e_ffprobe_ausente_é_filenotfounderror(tmp_path):
    arq = tmp_path / "v.mp4"
    arq.write_bytes(b"")
    ff = _json_falso(tmp_path, None, cru="isto nao e json")
    with pytest.raises(ValueError):
        mediaio.probe_summary(arq, ffprobe=ff, fail=_Erro)
    with pytest.raises(FileNotFoundError):
        mediaio.probe_summary(arq, ffprobe=str(tmp_path / "nao-existe"), fail=_Erro)


@pytest.mark.parametrize("bruto,esperado", [("30/1", 30.0), ("30000/1001", 29.97), ("abc/2", 0.0), ("24", 24.0), ("", 0.0), ("0", 0.0),
                                              (None, 0.0), (0, 0.0), ("x", 0.0), ("25/", 25.0), (30, 30.0), ("1/3", 0.333)])
def test_fps(bruto, esperado):
    assert mediaio.fps(bruto) == esperado


def test_fps_denominador_zero_é_zerodivisionerror_crua_como_sempre_foi_no_shorts():
    """`0/0` is what ffprobe prints for a stream without a frame rate: the shorts caught only ValueError, and that did not change."""
    with pytest.raises(ZeroDivisionError):
        mediaio.fps("0/0")
