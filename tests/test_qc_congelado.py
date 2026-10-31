"""QC de quadro congelado: `simplicio-video qc congelado <mp4> [--min-s 0.5] [--json]` (critério D do BRASA, etapa 1).

Usa o filtro freezedetect do ffmpeg. O MP4 sintético tem 1 s de quadro fixo (vermelho) e 1 s de movimento (testsrc):
o comando tem de achar exatamente UM intervalo, com duração perto de 1 s. Sem ffmpeg, o teste pula com motivo.
"""
import json
import shutil
import subprocess

import pytest

from conftest import run_cli


def _ffmpeg_ou_pula():
    if not (shutil.which("ffmpeg") and shutil.which("ffprobe")):
        pytest.skip("ffmpeg/ffprobe ausentes neste ambiente: o QC de quadro congelado usa o freezedetect do ffmpeg")


@pytest.fixture
def mp4_com_quadro_fixo(tmp_path):
    _ffmpeg_ou_pula()
    mp4 = tmp_path / "congelado.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y",
                    "-f", "lavfi", "-i", "color=c=red:s=160x90:r=30:d=1",
                    "-f", "lavfi", "-i", "testsrc=s=160x90:r=30:d=1",
                    "-filter_complex", "[0][1]concat=n=2:v=1:a=0[v]", "-map", "[v]",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(mp4)], check=True)
    return mp4


def test_json_lista_exatamente_um_intervalo_de_cerca_de_1_s(mp4_com_quadro_fixo):
    r = run_cli("qc", "congelado", mp4_com_quadro_fixo, "--json")
    assert r.returncode == 0, r.stderr
    dados = json.loads(r.stdout)
    assert dados["schema"] == "simplicio.qc-congelado/v1"
    intervalos = dados["intervalos"]
    assert len(intervalos) == 1, intervalos
    iv = intervalos[0]
    assert set(iv) == {"inicio_s", "fim_s", "duracao_s"}
    assert iv["inicio_s"] <= 0.1
    assert iv["duracao_s"] == pytest.approx(1.0, abs=0.1)
    assert iv["fim_s"] == pytest.approx(iv["inicio_s"] + iv["duracao_s"], abs=0.05)


def test_min_s_acima_da_duracao_nao_acha_nada(mp4_com_quadro_fixo):
    r = run_cli("qc", "congelado", mp4_com_quadro_fixo, "--min-s", "2", "--json")
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout)["intervalos"] == []


def test_saida_legivel_sem_json(mp4_com_quadro_fixo):
    r = run_cli("qc", "congelado", mp4_com_quadro_fixo)
    assert r.returncode == 0, r.stderr
    assert "1 intervalo" in r.stdout
    assert "{" not in r.stdout  # texto para gente, não JSON


def test_arquivo_inexistente_falha_com_mensagem(tmp_path):
    r = run_cli("qc", "congelado", tmp_path / "nao-existe.mp4")
    assert r.returncode != 0
    assert "nao-existe.mp4" in (r.stdout + r.stderr)
