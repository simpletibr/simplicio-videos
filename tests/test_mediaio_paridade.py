"""Characterization of every caller of ffprobe in the package (U06): WHICH ffprobe each one runs, with WHICH argv and flags, and
what each one raises or prints when the program is missing, fails or answers something odd.

Green BEFORE and AFTER the callers move to `mediaio`: moving them must not change a byte of this. Three facts it freezes:

* the callers do not agree on the binary. With a fake ffprobe on the PATH (answers 1.5) and another in SIMPLICIO_FFMPEG_DIR
  (answers 42.0), swap and openverse_sheet run the locked one, `render.make_preview` runs it too (its `env=` is
  `paths.node_env()`, which puts that folder first in PATH) and everybody else runs the PATH one;
* each caller keeps its own error and its own text (QcError, MediaError, ShortsError, DownloadError, SocialError, SwapError,
  OpenverseError, the SystemExit of trilha, the raw ValueError/FileNotFoundError of render, the CalledProcessError of voice);
* the flags of the child (stdin, capture, text, timeout, check, env) and the exact argv, `file:` and `-i` included.

The ffprobe and the ffmpeg of the tests are fake scripts (POSIX): they record what they were asked and answer by mode.

One thing changed on purpose when the callers moved (D1): `media` no longer imports `shorts`, so `media sheet` raises a MediaError
(`media: <text>`, exit 1) where it used to let the ShortsError of shorts.probe out (a traceback), with the SAME text.
"""
import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from simplicio_video import cli, download, media, openverse_sheet, paths, qc, render, shorts, social, swap, trilha, voice

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="o ffprobe falso é um script com shebang")

DUR_PATH, DUR_TRAVADO = 1.5, 42.0

# The fake ffprobe: logs {id, argv, PATH, HYPERFRAMES_FFPROBE_PATH} and answers by FAKE_FF_MODO and by the shape of the query.
FFPROBE_FALSO = """\
import json, os, sys
ID, DUR, LOG = @ID@, @DUR@, @LOG@
a = sys.argv[1:]
with open(LOG, "a") as f:
    f.write(json.dumps({"id": ID, "argv": a, "path": os.environ.get("PATH"), "hf": os.environ.get("HYPERFRAMES_FFPROBE_PATH")}) + "\\n")
modo = os.environ.get("FAKE_FF_MODO", "ok")
dur = "N/A" if modo == "na" else "%.6f" % DUR
video = {"codec_type": "video", "codec_name": "h264", "width": 1080, "height": 1920, "avg_frame_rate": "30/1", "r_frame_rate": "30/1"}
audio = {"codec_type": "audio", "codec_name": "aac", "sample_rate": "48000", "channels": 2}
doc = {"streams": [audio] if modo == "sem_video" else [video, audio],
       "format": {"duration": dur, "format_name": "mov,mp4,m4a,3gp,3g2,mj2", "bit_rate": "1000"}}
if modo == "invalido":
    sys.stderr.write("fake ffprobe: dado inválido (linha 1)\\nfake ffprobe: segunda linha do erro\\n")
    sys.exit(1)
if modo == "vazio":
    sys.exit(0)
if modo == "lixo":
    sys.stdout.write("isto nao e json")
    sys.exit(0)
json_out = "-print_format" in a or ("-of" in a and a[a.index("-of") + 1] == "json")
sys.stdout.write(json.dumps(doc) if json_out else dur + "\\n")
sys.exit(3 if modo == "rc_com_saida" else 0)
"""

# The fake ffmpeg: framemd5 and PCM for render.media_hashes, an open-ended freeze for qc, a file at the last argument otherwise.
FFMPEG_FALSO = """\
import sys
a = sys.argv[1:]
if "framemd5" in a:
    sys.stdout.write("#format: frame checksums\\n0, 0, 0, 1, 100, aabbccdd\\n")
elif "s16le" in a:
    sys.stdout.buffer.write(b"\\x00\\x01" * 8)
elif any("freezedetect" in x for x in a):
    sys.stderr.write("lavfi.freezedetect.freeze_start: 0.5\\n")
elif a and a[-1] != "-":
    open(a[-1], "wb").write(b"fake-media")
"""


def _instala(pasta: Path, nome: str, corpo: str) -> Path:
    pasta.mkdir(parents=True, exist_ok=True)
    alvo = pasta / nome
    alvo.write_text(f"#!{sys.executable}\n{corpo}", encoding="utf8")
    alvo.chmod(alvo.stat().st_mode | stat.S_IEXEC)
    return alvo


class Amb:
    """A sealed PATH with a fake ffmpeg and (optionally) a fake ffprobe, and a locked folder (SIMPLICIO_FFMPEG_DIR) with another."""

    def __init__(self, tmp: Path, monkeypatch):
        self.tmp, self.mp = tmp, monkeypatch
        self.log = tmp / "ffprobe.log"
        self.pasta, self.travado = tmp / "bin-path", tmp / "bin-travado"
        self.mp4 = tmp / "clip.mp4"
        self.mp4.write_bytes(b"fake-media-bytes")
        self.wav = tmp / "voz.wav"
        self.wav.write_bytes(b"fake-wav-bytes")
        monkeypatch.setenv("HOME", str(tmp / "home"))
        monkeypatch.delenv("SIMPLICIO_FFMPEG_DIR", raising=False)
        monkeypatch.setenv("FAKE_FF_MODO", "ok")
        _instala(self.pasta, "ffmpeg", FFMPEG_FALSO)
        monkeypatch.setenv("PATH", str(self.pasta))

    def _ffprobe(self, pasta: Path, id_: str, dur: float):
        _instala(pasta, "ffprobe", FFPROBE_FALSO.replace("@ID@", repr(id_)).replace("@DUR@", repr(dur)).replace("@LOG@", repr(str(self.log))))

    def com_path(self):
        self._ffprobe(self.pasta, "path", DUR_PATH)

    def com_travado(self):
        self._ffprobe(self.travado, "travado", DUR_TRAVADO)
        self.mp.setenv("SIMPLICIO_FFMPEG_DIR", str(self.travado))

    def com_dir_travado_sem_ffprobe(self):
        self.travado.mkdir(parents=True, exist_ok=True)
        self.mp.setenv("SIMPLICIO_FFMPEG_DIR", str(self.travado))

    def modo(self, modo: str):
        self.mp.setenv("FAKE_FF_MODO", modo)

    def chamadas(self) -> list[dict]:
        if not self.log.exists():
            return []
        return [json.loads(ln) for ln in self.log.read_text(encoding="utf8").splitlines()]

    def ids(self) -> list[str]:
        return [c["id"] for c in self.chamadas()]


@pytest.fixture
def amb(tmp_path, monkeypatch):
    return Amb(tmp_path, monkeypatch)


# ------------------------------------------------------------------ the callers: one function each, same shape

def _cues(amb: Amb) -> Path:
    p = amb.tmp / "cues.json"
    p.write_text(json.dumps({"schema": media.CUES_SCHEMA, "cues": [{"start": 0.0, "end": 2.0, "text": "oi", "audio": str(amb.wav)}]}), encoding="utf8")
    return p


def _json_do_media(capsys) -> dict:
    return json.loads(capsys.readouterr().out)


def _render_media_hashes(amb, capsys):
    return render.media_hashes(amb.mp4)["duration_s"]


def _render_make_preview(amb, capsys):
    return render.make_preview(amb.mp4, amb.tmp / "p" / "preview.mp4", amb.tmp)["duration_s"]


def _qc_congelado(amb, capsys):
    return qc.detecta_congelado(amb.mp4, 0.5)[0]["duracao_s"]  # the freeze never closes: file duration minus the 0.5 s start


def _trilha_duracao(amb, capsys):
    return trilha.duracao_s(amb.wav)


def _voice_duration(amb, capsys):
    return voice.duration(amb.wav)


def _media_probe(amb, capsys):
    assert media.run_media(["probe", str(amb.mp4)]) == 0
    return _json_do_media(capsys)["duration"]


def _media_sheet(amb, capsys):
    assert media.run_media(["sheet", str(amb.mp4), "-o", str(amb.tmp / "sheet.jpg")]) == 0
    return _json_do_media(capsys)["cols"]  # no duration in the answer: the caller is judged by the ffprobe that was run


def _media_voice_track(amb, capsys):
    assert media.run_media(["voice-track", str(_cues(amb)), "--duration", "5", "-o", str(amb.tmp / "voz-out.wav")]) == 0
    return _json_do_media(capsys)["plan"][0]["clip_seconds"]


def _download_conferir(amb, capsys):
    return download._conferir(amb.mp4)


def _shorts_probe(amb, capsys):
    return shorts.probe(amb.mp4)["duration"]


def _social_probe(amb, capsys):
    return social._real_probe(amb.mp4)["duration_s"]


def _swap_probe(amb, capsys):
    return swap.probe(amb.mp4)["duration_s"]


def _openverse_probe(amb, capsys):
    dur = (openverse_sheet.probe(amb.wav, "wav").get("format") or {}).get("duration")
    return dur if dur in (None, "N/A") else float(dur)


CHAMADORES = {
    "render.media_hashes": _render_media_hashes,
    "render.make_preview": _render_make_preview,
    "qc.detecta_congelado": _qc_congelado,
    "trilha.duracao_s": _trilha_duracao,
    "voice.duration": _voice_duration,
    "media.probe": _media_probe,
    "media.sheet": _media_sheet,
    "media.voice-track": _media_voice_track,
    "download._conferir": _download_conferir,
    "shorts.probe": _shorts_probe,
    "social._real_probe": _social_probe,
    "swap.probe": _swap_probe,
    "openverse_sheet.probe": _openverse_probe,
}
# How many ffprobe runs one call makes (make_preview probes the draft and the preview).
CHAMADAS = {nome: 2 if nome == "render.make_preview" else 1 for nome in CHAMADORES}
# Callers that run the locked ffprobe when both exist: swap and openverse_sheet by their own `_bin`, make_preview by `env=node_env()`.
USA_TRAVADO = {"swap.probe", "openverse_sheet.probe", "render.make_preview"}
# Callers that answer with the duration of the fake they ran (the others are judged by the log).
VALOR = {"render.media_hashes", "render.make_preview", "qc.detecta_congelado", "trilha.duracao_s", "voice.duration", "media.probe",
         "media.voice-track", "shorts.probe", "social._real_probe", "swap.probe", "openverse_sheet.probe"}


def _valor_esperado(nome: str, dur: float) -> float:
    return round(dur - 0.5, 3) if nome == "qc.detecta_congelado" else dur


# ------------------------------------------------------------------ which ffprobe

@pytest.mark.parametrize("nome", CHAMADORES)
def test_so_com_ffprobe_no_path_todos_rodam_o_do_path(amb, capsys, nome):
    amb.com_path()
    valor = CHAMADORES[nome](amb, capsys)
    assert amb.ids() == ["path"] * CHAMADAS[nome]
    if nome in VALOR:
        assert valor == pytest.approx(_valor_esperado(nome, DUR_PATH))


@pytest.mark.parametrize("nome", CHAMADORES)
def test_com_dir_travado_sem_ffprobe_todos_rodam_o_do_path(amb, capsys, nome):
    amb.com_path()
    amb.com_dir_travado_sem_ffprobe()
    CHAMADORES[nome](amb, capsys)
    assert amb.ids() == ["path"] * CHAMADAS[nome]


@pytest.mark.parametrize("nome", CHAMADORES)
def test_com_os_dois_cada_um_roda_o_seu_o_travado_so_para_swap_openverse_e_a_previa(amb, capsys, nome):
    amb.com_path()
    amb.com_travado()
    valor = CHAMADORES[nome](amb, capsys)
    esperado = "travado" if nome in USA_TRAVADO else "path"
    assert amb.ids() == [esperado] * CHAMADAS[nome]
    if nome in VALOR:
        assert valor == pytest.approx(_valor_esperado(nome, DUR_TRAVADO if esperado == "travado" else DUR_PATH))


def test_a_previa_roda_o_ffprobe_com_o_ambiente_do_node_env_e_a_media_hashes_com_o_do_processo(amb, capsys):
    amb.com_path()
    amb.com_travado()
    render.media_hashes(amb.mp4)
    sem_env, = amb.chamadas()
    assert sem_env["path"] == str(amb.pasta) and sem_env["hf"] is None
    amb.log.unlink()
    render.make_preview(amb.mp4, amb.tmp / "p" / "preview.mp4", amb.tmp)
    for c in amb.chamadas():
        assert c["path"].split(os.pathsep)[0] == str(amb.travado)
        assert c["hf"] == str(amb.travado / "ffprobe")  # paths.node_env() default for the HyperFrames child


@pytest.mark.parametrize("nome", CHAMADORES)
def test_so_com_ffprobe_no_dir_travado_so_swap_openverse_e_a_previa_funcionam(amb, capsys, nome):
    amb.com_travado()
    if nome in USA_TRAVADO:
        CHAMADORES[nome](amb, capsys)
        assert amb.ids() == ["travado"] * CHAMADAS[nome]
    else:
        with pytest.raises(BaseException) as e:
            CHAMADORES[nome](amb, capsys)
        assert amb.ids() == []
        assert _desfecho(e.value, amb) == ERRO_AUSENTE[nome]


# ------------------------------------------------------------------ the outcome of a call, as text


def _desfecho(erro: BaseException, amb: Amb) -> str:
    return f"{type(erro).__name__}: {erro}".replace(str(amb.tmp), "<TMP>")


def _resultado(nome: str, amb: Amb, capsys) -> str:
    try:
        valor = CHAMADORES[nome](amb, capsys)
    except BaseException as e:  # noqa: BLE001 - SystemExit and KeyboardInterrupt are outcomes too
        return _desfecho(e, amb)
    return f"ok {valor!r}"


NAO_ACHOU = "ffprobe não encontrado: instale o ffmpeg (ffmpeg e ffprobe no PATH)"
ERRO_AUSENTE = {
    "render.media_hashes": "FileNotFoundError: [Errno 2] No such file or directory: 'ffprobe'",
    "render.make_preview": "FileNotFoundError: [Errno 2] No such file or directory: 'ffprobe'",
    "qc.detecta_congelado": "FileNotFoundError: [Errno 2] No such file or directory: 'ffprobe'",
    "trilha.duracao_s": "FileNotFoundError: [Errno 2] No such file or directory: 'ffprobe'",
    "voice.duration": "FileNotFoundError: [Errno 2] No such file or directory: 'ffprobe'",
    "media.probe": "MediaError: ffprobe não encontrado no PATH (o shorts usa só ffmpeg/ffprobe)",
    "media.sheet": "MediaError: ffprobe não encontrado no PATH (o shorts usa só ffmpeg/ffprobe)",
    "media.voice-track": "MediaError: ffprobe não encontrado no PATH (media usa ffmpeg e ffprobe)",
    "download._conferir": "DownloadError: o ffprobe é necessário para conferir o arquivo baixado (instale o ffmpeg)",
    "shorts.probe": "ShortsError: ffprobe não encontrado no PATH (o shorts usa só ffmpeg/ffprobe)",
    "social._real_probe": f"SocialError: {NAO_ACHOU}",
    "swap.probe": f"SwapError: {NAO_ACHOU}",
    "openverse_sheet.probe": f"OpenverseError: {NAO_ACHOU} para gerar a folha",
}


@pytest.mark.parametrize("nome", CHAMADORES)
def test_sem_ffprobe_nenhum_a_mensagem_e_o_tipo_de_cada_chamador(amb, capsys, nome):
    assert _resultado(nome, amb, capsys) == ERRO_AUSENTE[nome]


def test_a_previa_sem_ffprobe_com_o_dir_travado_sem_ele_tambem_nao_o_acha(amb, capsys):
    amb.com_dir_travado_sem_ffprobe()
    assert _resultado("render.make_preview", amb, capsys) == ERRO_AUSENTE["render.make_preview"]


INVALIDO_STDERR = "fake ffprobe: dado inválido (linha 1)\nfake ffprobe: segunda linha do erro"
ERRO_INVALIDO = {
    "render.media_hashes": "ValueError: could not convert string to float: ''",
    "render.make_preview": "ValueError: could not convert string to float: ''",
    "qc.detecta_congelado": "QcError: qc: ffprobe não leu a duração de <TMP>/clip.mp4",
    "trilha.duracao_s": "SystemExit: trilha: ffprobe não leu a duração de <TMP>/voz.wav",
    "voice.duration": "CalledProcessError: Command '('ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', "
                      "'<TMP>/voz.wav')' returned non-zero exit status 1.",
    "media.probe": f"MediaError: {INVALIDO_STDERR}",
    "media.sheet": f"MediaError: {INVALIDO_STDERR}",
    "media.voice-track": "MediaError: não consegui ler a duração de <TMP>/voz.wav",
    "download._conferir": "DownloadError: o arquivo baixado não é mídia legível (ffprobe: fake ffprobe: segunda linha do erro)",
    "shorts.probe": f"ShortsError: {INVALIDO_STDERR}",
    "social._real_probe": f"SocialError: ffprobe falhou: {INVALIDO_STDERR}",
    "swap.probe": f"SwapError: ffprobe falhou (1): {INVALIDO_STDERR}",
    "openverse_sheet.probe": f"OpenverseError: o ffprobe não conseguiu ler o arquivo (wav): {INVALIDO_STDERR}",
}


@pytest.mark.parametrize("nome", CHAMADORES)
def test_arquivo_invalido_ffprobe_com_codigo_de_saida_ruim_a_mensagem_de_cada_chamador(amb, capsys, nome):
    amb.com_path()
    amb.modo("invalido")
    assert _resultado(nome, amb, capsys) == ERRO_INVALIDO[nome]


ERRO_VAZIO = {  # exit 0 and nothing on stdout
    "render.media_hashes": "ValueError: could not convert string to float: ''",
    "render.make_preview": "ValueError: could not convert string to float: ''",
    "qc.detecta_congelado": "QcError: qc: ffprobe não leu a duração de <TMP>/clip.mp4",
    "trilha.duracao_s": "SystemExit: trilha: ffprobe não leu a duração de <TMP>/voz.wav",
    "voice.duration": "ValueError: could not convert string to float: ''",
    "media.probe": "MediaError: sem trilha de vídeo: <TMP>/clip.mp4",
    "media.sheet": "MediaError: sem trilha de vídeo: <TMP>/clip.mp4",
    "media.voice-track": "MediaError: não consegui ler a duração de <TMP>/voz.wav",
    "download._conferir": "DownloadError: o arquivo baixado não é mídia legível (ffprobe: sem fluxo ou sem duração)",
    "shorts.probe": "ShortsError: sem trilha de vídeo: <TMP>/clip.mp4",
    "social._real_probe": "SocialError: o arquivo não tem trilha de vídeo: <TMP>/clip.mp4",
    "swap.probe": "SwapError: sem trilha de vídeo: <TMP>/clip.mp4",
    "openverse_sheet.probe": "ok None",
}


@pytest.mark.parametrize("nome", CHAMADORES)
def test_ffprobe_que_sai_0_sem_escrever_nada(amb, capsys, nome):
    amb.com_path()
    amb.modo("vazio")
    assert _resultado(nome, amb, capsys) == ERRO_VAZIO[nome]


ERRO_NA = {  # exit 0 and the duration is "N/A"
    "render.media_hashes": "ValueError: could not convert string to float: 'N/A'",
    "render.make_preview": "ValueError: could not convert string to float: 'N/A'",
    "qc.detecta_congelado": "ValueError: could not convert string to float: 'N/A'",
    "trilha.duracao_s": "ValueError: could not convert string to float: 'N/A'",
    "voice.duration": "ValueError: could not convert string to float: 'N/A'",
    "media.probe": "ok 0.0",
    "media.sheet": "ok 8",
    "media.voice-track": "MediaError: não consegui ler a duração de <TMP>/voz.wav",
    "download._conferir": "DownloadError: o arquivo baixado não é mídia legível (o ffprobe não entendeu)",
    "shorts.probe": "ok 0.0",
    "social._real_probe": "SocialError: não consegui ler a duração de <TMP>/clip.mp4",
    "swap.probe": "SwapError: não consegui ler a duração de <TMP>/clip.mp4",
    "openverse_sheet.probe": "ok 'N/A'",
}


@pytest.mark.parametrize("nome", CHAMADORES)
def test_ffprobe_que_sai_0_com_duracao_na(amb, capsys, nome):
    amb.com_path()
    amb.modo("na")
    assert _resultado(nome, amb, capsys) == ERRO_NA[nome]


def test_qc_e_trilha_distinguem_saida_vazia_de_na_e_o_render_nao_distingue(amb, capsys):
    amb.com_path()
    amb.modo("vazio")
    assert _resultado("qc.detecta_congelado", amb, capsys).startswith("QcError")
    assert _resultado("trilha.duracao_s", amb, capsys).startswith("SystemExit")
    amb.modo("na")
    assert _resultado("qc.detecta_congelado", amb, capsys).startswith("ValueError")
    assert _resultado("trilha.duracao_s", amb, capsys).startswith("ValueError")
    amb.modo("vazio")
    assert _resultado("render.media_hashes", amb, capsys).startswith("ValueError")


def test_render_ignora_o_codigo_de_saida_se_o_ffprobe_escreveu_um_numero(amb, capsys):
    amb.com_path()
    amb.modo("rc_com_saida")
    assert render.media_hashes(amb.mp4)["duration_s"] == DUR_PATH
    assert render.make_preview(amb.mp4, amb.tmp / "p" / "preview.mp4", amb.tmp)["duration_s"] == DUR_PATH


ERRO_RC_COM_SAIDA = {  # exit 3 but a good answer on stdout
    "qc.detecta_congelado": "QcError: qc: ffprobe não leu a duração de <TMP>/clip.mp4",
    "trilha.duracao_s": "SystemExit: trilha: ffprobe não leu a duração de <TMP>/voz.wav",
    "voice.duration": "CalledProcessError: Command '('ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', "
                      "'<TMP>/voz.wav')' returned non-zero exit status 3.",
    "media.probe": "MediaError: ffprobe falhou em <TMP>/clip.mp4",
    "media.sheet": "MediaError: ffprobe falhou em <TMP>/clip.mp4",
    "download._conferir": "DownloadError: o arquivo baixado não é mídia legível (ffprobe: sem fluxo ou sem duração)",
    "shorts.probe": "ShortsError: ffprobe falhou em <TMP>/clip.mp4",
    "social._real_probe": "SocialError: ffprobe falhou: ",
    "swap.probe": "SwapError: ffprobe falhou (3): ",
    "openverse_sheet.probe": "OpenverseError: o ffprobe não conseguiu ler o arquivo (wav): ",
}


@pytest.mark.parametrize("nome", ERRO_RC_COM_SAIDA)
def test_codigo_de_saida_ruim_mesmo_com_resposta_boa_e_erro_na_maioria_dos_chamadores(amb, capsys, nome):
    amb.com_path()
    amb.modo("rc_com_saida")
    assert _resultado(nome, amb, capsys) == ERRO_RC_COM_SAIDA[nome]


ERRO_LIXO = {  # exit 0 and stdout that is not JSON (the callers that read JSON)
    "media.probe": "JSONDecodeError: Expecting value: line 1 column 1 (char 0)",
    "media.sheet": "JSONDecodeError: Expecting value: line 1 column 1 (char 0)",
    "download._conferir": "DownloadError: o arquivo baixado não é mídia legível (o ffprobe não entendeu)",
    "shorts.probe": "JSONDecodeError: Expecting value: line 1 column 1 (char 0)",
    "social._real_probe": "JSONDecodeError: Expecting value: line 1 column 1 (char 0)",
    "swap.probe": "JSONDecodeError: Expecting value: line 1 column 1 (char 0)",
    "openverse_sheet.probe": "OpenverseError: o ffprobe devolveu uma resposta ilegível",
}


@pytest.mark.parametrize("nome", ERRO_LIXO)
def test_resposta_que_nao_e_json(amb, capsys, nome):
    amb.com_path()
    amb.modo("lixo")
    assert _resultado(nome, amb, capsys) == ERRO_LIXO[nome]


ERRO_SEM_VIDEO = {  # only an audio stream
    "media.probe": "MediaError: sem trilha de vídeo: <TMP>/clip.mp4",
    "media.sheet": "MediaError: sem trilha de vídeo: <TMP>/clip.mp4",
    "shorts.probe": "ShortsError: sem trilha de vídeo: <TMP>/clip.mp4",
    "social._real_probe": "SocialError: o arquivo não tem trilha de vídeo: <TMP>/clip.mp4",
    "swap.probe": "SwapError: sem trilha de vídeo: <TMP>/clip.mp4",
}


@pytest.mark.parametrize("nome", ERRO_SEM_VIDEO)
def test_arquivo_so_com_audio(amb, capsys, nome):
    amb.com_path()
    amb.modo("sem_video")
    assert _resultado(nome, amb, capsys) == ERRO_SEM_VIDEO[nome]


# ------------------------------------------------------------------ argv and flags of the child

ARGV_DURACAO = ["-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0"]
ARGV = {  # what follows the program name; `{p}` is the file the call was given
    "render.media_hashes": ARGV_DURACAO + ["{mp4}"],
    "render.make_preview": ARGV_DURACAO + ["{mp4}"],  # the second probe is of the preview file
    "qc.detecta_congelado": ARGV_DURACAO + ["{mp4}"],
    "trilha.duracao_s": ARGV_DURACAO + ["{wav}"],
    "voice.duration": ARGV_DURACAO + ["{wav}"],
    "media.probe": ["-v", "error", "-print_format", "json", "-show_format", "-show_streams", "{mp4}"],
    "media.sheet": ["-v", "error", "-print_format", "json", "-show_format", "-show_streams", "{mp4}"],
    "media.voice-track": ["-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", "{wav}"],
    "download._conferir": ["-v", "error", "-show_entries", "format=duration:stream=codec_type", "-of", "json", "{mp4}"],
    "shorts.probe": ["-v", "error", "-print_format", "json", "-show_format", "-show_streams", "{mp4}"],
    "social._real_probe": ["-v", "error", "-show_entries",
                           "stream=codec_type,codec_name,width,height,avg_frame_rate,r_frame_rate:format=duration,format_name",
                           "-of", "json", "file:{mp4}"],
    "swap.probe": ["-v", "error", "-show_entries", "stream=codec_type,avg_frame_rate,r_frame_rate,width,height:format=duration",
                   "-of", "json", "{mp4}"],
    "openverse_sheet.probe": ["-v", "error", "-protocol_whitelist", "file", "-f", "wav", "-show_entries",
                              "stream=codec_type,codec_name,width,height,sample_rate,channels:stream_disposition=attached_pic:format=duration,bit_rate",
                              "-of", "json", "-i", "{wav}"],
}


@pytest.mark.parametrize("nome", CHAMADORES)
def test_argv_exato_do_ffprobe_de_cada_chamador(amb, capsys, nome):
    amb.com_path()
    CHAMADORES[nome](amb, capsys)
    esperado = [a.replace("{mp4}", str(amb.mp4)).replace("{wav}", str(amb.wav)) for a in ARGV[nome]]
    ultimo = amb.chamadas()[-1]["argv"]
    if nome == "render.make_preview":
        esperado = [a.replace(str(amb.mp4), str(amb.tmp / "p" / "preview.mp4")) for a in esperado]
    assert ultimo == esperado
    assert len(amb.chamadas()) == CHAMADAS[nome]


def _sem_flags_novas(kwargs: dict) -> dict:
    """The keyword arguments of one subprocess.run call, with the defaults filled in (so `check=False` and no `check` are the same)."""
    k = dict(kwargs)
    visto = {"check": k.pop("check", False), "timeout": k.pop("timeout", None), "env": k.pop("env", None), "stdin": k.pop("stdin", None),
             "capture_output": k.pop("capture_output", False), "text": k.pop("text", None)}
    assert k == {}, f"keyword arguments that nobody was using: {sorted(k)}"
    return visto


def _flags(**mudancas) -> dict:
    base = {"check": False, "timeout": None, "env": None, "stdin": subprocess.DEVNULL, "capture_output": True, "text": True}
    return {**base, **mudancas}


FLAGS = {  # stdin, capture, text, timeout, check and env of the ffprobe child
    "render.media_hashes": _flags(),
    "render.make_preview": _flags(env="node_env"),
    "qc.detecta_congelado": _flags(),
    "trilha.duracao_s": _flags(),
    "voice.duration": _flags(check=True),
    "media.probe": _flags(),
    "media.sheet": _flags(),
    "media.voice-track": _flags(),
    "download._conferir": _flags(timeout=60),
    "shorts.probe": _flags(),
    "social._real_probe": _flags(),
    "swap.probe": _flags(),
    "openverse_sheet.probe": _flags(timeout=openverse_sheet.TOOL_TIMEOUT_S, text=None),
}
# argv[0] of the child: the bare name (found by the child's PATH) or the absolute path the caller found itself.
PROGRAMA = {"media.probe": "which", "media.sheet": "which", "media.voice-track": "which", "download._conferir": "which", "shorts.probe": "which"}


@pytest.mark.parametrize("nome", CHAMADORES)
def test_flags_e_programa_do_filho_de_cada_chamador(amb, capsys, monkeypatch, nome):
    amb.com_path()
    real = subprocess.run
    vistos = []

    def espia(args, *a, **k):
        if Path(args[0]).name == "ffprobe":
            vistos.append((args, k))
        return real(args, *a, **k)

    monkeypatch.setattr(subprocess, "run", espia)
    CHAMADORES[nome](amb, capsys)
    assert len(vistos) == CHAMADAS[nome]
    for args, k in vistos:
        esperado = dict(FLAGS[nome])
        if esperado["env"] == "node_env":
            assert k["env"] == paths.node_env()
            esperado["env"] = k["env"]
        assert _sem_flags_novas(k) == esperado
        assert args[0] == (str(amb.pasta / "ffprobe") if PROGRAMA.get(nome) == "which" else "ffprobe")


def test_swap_e_openverse_passam_o_caminho_do_binario_travado_quando_ele_existe(amb, capsys, monkeypatch):
    amb.com_path()
    amb.com_travado()
    real = subprocess.run
    vistos = []

    def espia(args, *a, **k):
        vistos.append(args[0])
        return real(args, *a, **k)

    monkeypatch.setattr(subprocess, "run", espia)
    swap.probe(amb.mp4)
    openverse_sheet.probe(amb.wav, "wav")
    assert vistos == [str(amb.travado / "ffprobe")] * 2


def test_social_manda_o_caminho_com_prefixo_file_e_absoluto(amb, capsys, monkeypatch):
    amb.com_path()
    monkeypatch.chdir(amb.tmp)
    social._real_probe(Path("clip.mp4"))
    assert amb.chamadas()[-1]["argv"][-1] == "file:" + str(amb.mp4)
    social._real_probe(Path("-x.mp4"))
    assert amb.chamadas()[-1]["argv"][-1] == "file:" + str(amb.tmp / "-x.mp4")


def test_openverse_manda_o_caminho_resolvido_depois_do_i(amb, capsys, monkeypatch):
    amb.com_path()
    ligacao = amb.tmp / "ligacao.wav"
    ligacao.symlink_to(amb.wav)
    openverse_sheet.probe(ligacao, "wav")
    argv = amb.chamadas()[-1]["argv"]
    assert argv[-2:] == ["-i", str(amb.wav)]


def test_openverse_com_formato_sem_demuxer_levanta_keyerror_antes_de_rodar_o_ffprobe(amb, capsys):
    amb.com_path()
    with pytest.raises(KeyError):
        openverse_sheet.probe(amb.wav, "formato-que-nao-existe")
    assert amb.chamadas() == []


# ------------------------------------------------------------------ names that tests patch stay in the module

def test_os_nomes_que_os_testes_trocam_continuam_no_modulo_e_o_codigo_os_chama(amb, capsys, monkeypatch):
    amb.com_path()
    vistos = []
    monkeypatch.setattr(swap, "_run", lambda cmd: vistos.append(("swap._run", Path(cmd[0]).name)) or subprocess.CompletedProcess(
        cmd, 0, json.dumps({"streams": [{"codec_type": "video", "width": 1, "height": 1}], "format": {"duration": "2"}}), ""))
    assert swap.probe(amb.mp4)["duration_s"] == 2.0
    monkeypatch.setattr(swap, "_bin", lambda nome: "/outro/" + nome)
    swap.probe(amb.mp4)
    monkeypatch.setattr(openverse_sheet, "_run", lambda cmd, binary=False: vistos.append(("sheet._run", cmd[0])) or subprocess.CompletedProcess(
        cmd, 0, "{}", ""))
    monkeypatch.setattr(openverse_sheet, "_bin", lambda nome: "/outro/" + nome)
    assert openverse_sheet.probe(amb.wav, "wav") == {}
    monkeypatch.setattr(social, "_probe", lambda p: {"duration_s": 7.0})
    assert social._probe(amb.mp4) == {"duration_s": 7.0}
    assert vistos == [("swap._run", "ffprobe"), ("swap._run", "ffprobe"), ("sheet._run", "/outro/ffprobe")]
    assert amb.chamadas() == []
    assert callable(shorts.probe) and callable(media.run_media)
    assert media.shorts is shorts  # tests/test_media.py reads `media.shorts.probe`


# ------------------------------------------------------------------ the command line, whole

def _cli(*argv):
    import contextlib
    import io
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = cli.main(list(argv))
    return rc, out.getvalue(), err.getvalue()


def test_media_probe_na_linha_de_comando_json_e_exato(amb):
    amb.com_path()
    rc, out, err = _cli("media", "probe", str(amb.mp4))
    doc = json.loads(out)
    assert (rc, err) == (0, "")
    assert doc == {"path": str(amb.mp4), "duration": DUR_PATH, "width": 1080, "height": 1920, "fps": 30.0, "has_audio": True,
                   "size_bytes": amb.mp4.stat().st_size, "sha256": doc["sha256"]}
    assert len(doc["sha256"]) == 64
    assert out == json.dumps(doc, ensure_ascii=False, indent=2) + "\n"


def test_media_probe_sem_ffprobe_na_linha_de_comando(amb):
    rc, out, err = _cli("media", "probe", str(amb.mp4))
    assert (rc, out) == (1, "")
    assert err == "media: ffprobe não encontrado no PATH (o shorts usa só ffmpeg/ffprobe)\n"


def test_media_probe_de_arquivo_ausente_na_linha_de_comando(amb):
    amb.com_path()
    rc, out, err = _cli("media", "probe", str(amb.tmp / "nao-existe.mp4"))
    assert (rc, out, err) == (1, "", f"media: arquivo não existe: {amb.tmp / 'nao-existe.mp4'}\n")
    assert amb.chamadas() == []


def test_media_probe_de_wav_gerado_com_ffprobe_de_verdade_nao_tem_video(tmp_path, monkeypatch):
    if not (shutil.which("ffmpeg") and shutil.which("ffprobe")):
        pytest.skip("precisa do ffmpeg e do ffprobe")
    monkeypatch.delenv("SIMPLICIO_FFMPEG_DIR", raising=False)
    wav = tmp_path / "t.wav"
    import wave
    with wave.open(str(wav), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(b"\x00\x00" * 8000)
    rc, out, err = _cli("media", "probe", str(wav))
    assert (rc, out, err) == (1, "", f"media: sem trilha de vídeo: {wav}\n")


def test_media_probe_de_video_gerado_com_ffprobe_de_verdade(tmp_path, monkeypatch):
    if not (shutil.which("ffmpeg") and shutil.which("ffprobe")):
        pytest.skip("precisa do ffmpeg e do ffprobe")
    monkeypatch.delenv("SIMPLICIO_FFMPEG_DIR", raising=False)
    mp4 = tmp_path / "t.mp4"
    gerou = subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc=size=64x48:rate=5:duration=1", "-f", "lavfi", "-i",
                            "sine=duration=1", "-pix_fmt", "yuv420p", "-shortest", str(mp4)], capture_output=True, stdin=subprocess.DEVNULL)
    if gerou.returncode != 0:
        pytest.skip("este ffmpeg não gera o vídeo de teste")
    rc, out, err = _cli("media", "probe", str(mp4))
    doc = json.loads(out)
    assert (rc, err) == (0, "")
    assert set(doc) == {"path", "duration", "width", "height", "fps", "has_audio", "size_bytes", "sha256"}
    assert (doc["width"], doc["height"], doc["fps"], doc["has_audio"]) == (64, 48, 5.0, True)
    assert doc["duration"] == pytest.approx(1.0, abs=0.2)
    assert doc["size_bytes"] == mp4.stat().st_size


def test_media_sheet_com_arquivo_ilegivel_agora_e_media_error_com_o_mesmo_texto(amb):
    """DEVIATION D1 (U06): media no longer imports shorts, so `media sheet` cannot raise the ShortsError of shorts.probe. Before, that
    error left media.run_media (cli.py only catches MediaError there): a traceback on the terminal, `ShortsError: <text>` in the MCP.
    Now it is a MediaError with the SAME text: `media: <text>` on stderr, exit 1."""
    amb.com_path()
    amb.modo("invalido")
    rc, out, err = _cli("media", "sheet", str(amb.mp4), "-o", str(amb.tmp / "s.jpg"))
    assert (rc, out) == (1, "")
    assert err == "media: fake ffprobe: dado inválido (linha 1)\nfake ffprobe: segunda linha do erro\n"


def test_media_sheet_sem_ffprobe_na_linha_de_comando_agora_e_media_error_com_o_mesmo_texto(amb):
    rc, out, err = _cli("media", "sheet", str(amb.mp4), "-o", str(amb.tmp / "s.jpg"))
    assert (rc, out) == (1, "")
    assert err == "media: ffprobe não encontrado no PATH (o shorts usa só ffmpeg/ffprobe)\n"


def test_qc_na_linha_de_comando_com_ffprobe_que_falha(amb):
    amb.com_path()
    amb.modo("invalido")
    rc, out, err = _cli("qc", "congelado", str(amb.mp4))
    assert (rc, out) == (1, "")
    assert err == f"qc: ffprobe não leu a duração de {amb.mp4}\n"


def test_qc_na_linha_de_comando_json_com_o_congelado_ate_o_fim(amb):
    amb.com_path()
    rc, out, err = _cli("qc", "congelado", str(amb.mp4), "--json")
    assert (rc, err) == (0, "")
    assert json.loads(out)["intervalos"] == [{"inicio_s": 0.5, "fim_s": 1.5, "duracao_s": 1.0}]


def test_download_conferir_aceita_o_arquivo_que_o_ffprobe_entende(amb):
    amb.com_path()
    assert download._conferir(amb.mp4) is None


def test_download_conferir_recusa_duracao_zero(amb, monkeypatch):
    amb.com_path()
    _instala(amb.pasta, "ffprobe", "import json\nprint(json.dumps({'streams': [{'codec_type': 'video'}], 'format': {'duration': '0.000000'}}))")
    with pytest.raises(download.DownloadError, match=r"^o arquivo baixado não é mídia legível \(ffprobe: sem fluxo ou sem duração\)$"):
        download._conferir(amb.mp4)



def test_shorts_e_media_probe_com_fps_0_0_levantam_zerodivisionerror_crua(amb):
    """`0/0` is what ffprobe prints for a stream without a frame rate: shorts._fps catches only ValueError (a bug kept as it was)."""
    amb.com_path()
    _instala(amb.pasta, "ffprobe", "import json\nprint(json.dumps({'streams': [{'codec_type': 'video', 'avg_frame_rate': '0/0'}], 'format': {'duration': '1'}}))")
    with pytest.raises(ZeroDivisionError):
        shorts.probe(amb.mp4)
    with pytest.raises(ZeroDivisionError):
        media.run_media(["probe", str(amb.mp4)])


def test_importar_o_media_nao_carrega_o_shorts_mas_media_shorts_continua_a_resolver():
    codigo = ("import sys\nfrom simplicio_video import media\n"
              "antes = 'simplicio_video.shorts' in sys.modules\n"
              "depois = media.shorts.__name__, 'simplicio_video.shorts' in sys.modules\n"
              "print(antes, *depois)")
    r = subprocess.run([sys.executable, "-c", codigo], capture_output=True, text=True, stdin=subprocess.DEVNULL,
                       env={**os.environ, "PYTHONPATH": str(Path(shorts.__file__).parents[1])})
    assert r.stdout.split() == ["False", "simplicio_video.shorts", "True"], r.stderr
    with pytest.raises(AttributeError):
        media.nao_existe_mesmo  # noqa: B018 - the lazy attribute only answers for `shorts`


def test_a_previa_chama_o_ffprobe_pelo_nome_e_deixa_o_dir_travado_para_o_path_do_ambiente_dela(amb, capsys, monkeypatch):
    amb.com_path()
    amb.com_travado()
    real = subprocess.run
    vistos = []

    def espia(args, *a, **k):
        if Path(args[0]).name == "ffprobe":
            vistos.append(args[0])
        return real(args, *a, **k)

    monkeypatch.setattr(subprocess, "run", espia)
    render.make_preview(amb.mp4, amb.tmp / "p" / "preview.mp4", amb.tmp)
    assert vistos == ["ffprobe", "ffprobe"]
    assert amb.ids() == ["travado", "travado"]


def test_shorts_probe_de_arquivo_ausente_nao_roda_o_ffprobe(amb):
    amb.com_path()
    with pytest.raises(shorts.ShortsError) as e:
        shorts.probe(amb.tmp / "nao-existe.mp4")
    assert str(e.value) == f"arquivo não existe: {amb.tmp / 'nao-existe.mp4'}"
    assert amb.chamadas() == []
