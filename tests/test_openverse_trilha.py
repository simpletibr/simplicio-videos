"""Áudio do Openverse na trilha de fundo (#113): `trilha.music` aceita um ativo da biblioteca com o bloco `openverse: {id, pedido}`.

Antes, `trilha.music.arquivo` aceitava qualquer arquivo e o portão do Openverse não o conferia: um áudio da biblioteca entrava
na trilha sem revisão, sem procedência no manifesto e sem crédito. Agora o arquivo da trilha entra no portão como um asset: tem
de estar em assets/openverse/ com o bloco, o par (id, sha256, pedido) aprovado, ser áudio e ter licença que permita modificação
(o motor arranja, dá volume e faz o ducking da trilha). O render copia a cópia aprovada para a composição, confere os bytes e
mixa a trilha sob a voz com o ducking de voz.ducking (o mesmo caminho da trilha de arquivo, trilha.py); o crédito vai ao lado do
MP4 e a procedência ao manifesto.

Hermético, como tests/test_openverse_contrato.py: a API e o download são fakes; o ffmpeg real gera os WAVs de teste. O render
completo (node + HyperFrames) fica no teste marcado `render` no fim, com o mix medido direto no build (sem HyperFrames).
"""
# ruff: noqa: F401, F811  (fixtures importadas de tests/test_openverse.py: o pytest as registra pelo nome e as usa como parâmetro)
from __future__ import annotations

import hashlib
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from audio_medida import freq_dominante, le_wav, potencia_banda_db
from helpers import edit_yaml_utf8 as _edit, fake_mp4, have_render_tools, needs_ffmpeg
from simplicio_video import compiler, contract as ct, openverse as ov, openverse_contract as oc, render, trilha, voice
from test_openverse import PEDIDO, _forjar, _mudar_e_reaprovar, amb, aprovado, baixar, env, midia

SR_TOM = 4000  # o tom da trilha de teste: fica na banda de agudos (2.5-6 kHz) que o ducking de voz baixa


# ------------------------------------------------------------------------------------------------ ajudas


def _wav_tom(path: Path, freq: int = SR_TOM, dur: int = 2) -> bytes:
    """WAV PCM de um tom senoidal (ffmpeg real): o corpo que o fake da API entrega como áudio do Openverse."""
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"sine=frequency={freq}:duration={dur}:sample_rate=44100",
                    "-af", "volume=0.5", "-c:a", "pcm_s16le", str(path)], check=True)
    return path.read_bytes()


@pytest.fixture
def trilha_aprovada(env, tmp_path):
    """Um áudio da biblioteca (CC BY 4.0, o fixture da API), revisado e aprovado para PEDIDO."""
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg ausente")
    item = baixar(env, tipo="audio", body=_wav_tom(tmp_path / "tom.wav"))
    ov.review_sheet(item["id"], PEDIDO)
    ov.review(item["id"], PEDIDO, "aprovado", "serve de fundo", "revisor")
    return item


def _exportar_trilha(contrato, item, pedido=PEDIDO, com_bloco=True, aceito=False) -> str:
    """Exporta o ativo para assets/openverse/ ao lado do contrato (o fluxo real) e o põe em trilha.music.arquivo."""
    nome = Path(ov.export(item["id"], pedido, contrato=contrato, aceito_restricao=aceito)["arquivo"]).name

    def fn(d):
        m = d["trilha"]["music"]
        m["arquivo"] = f"assets/openverse/{nome}"
        m.pop("openverse", None)
        if com_bloco:
            m["openverse"] = {"id": item["id"], "pedido": pedido}
    _edit(contrato, fn)
    return nome


def _ov_erros(contrato):
    return [e for e in ct.validate(ct.load(contrato)).errors if e.startswith("openverse:")]


def _sem_voz(contrato):
    _edit(contrato, lambda d: d["voz"].update(habilitada=False))  # sem voz não há timing.lock.json a gerar


def _copia_para_trilha(contrato, nome_origem: str, nome_novo: str = "fundo.wav") -> Path:
    """Copia o arquivo exportado para `trilha/` (fora de assets/openverse/) e o aponta em trilha.music, SEM o bloco."""
    origem = contrato.parent / "assets" / "openverse" / nome_origem
    (contrato.parent / "trilha").mkdir(exist_ok=True)
    destino = contrato.parent / "trilha" / nome_novo
    shutil.copy2(origem, destino)

    def fn(d):
        d["trilha"]["music"]["arquivo"] = f"trilha/{nome_novo}"
        d["trilha"]["music"].pop("openverse", None)
    _edit(contrato, fn)
    return destino


@pytest.fixture
def manifesto_falso(monkeypatch):
    """O manifesto mede o MP4 com ffmpeg; aqui o MP4 é falso e a medida também (o assunto é a procedência)."""
    monkeypatch.setattr(render, "media_hashes", lambda mp4: {"sha256": "a" * 64, "duration_s": 1.0, "frames": 30, "video_frames_sha256": "b" * 64,
                                                             "audio_pcm_sha256": "c" * 64, "frame_md5": ["d" * 32]})
    monkeypatch.setattr(render, "loudness", lambda mp4: {"integrated_lufs": -14.0, "true_peak_dbfs": -1.5})


# ------------------------------------------------------------------------------------------------ schema

def test_schema_aceita_o_bloco_openverse_na_trilha(mini):
    _edit(mini, lambda d: d["trilha"]["music"].update(arquivo="assets/openverse/fundo.wav",
                                                       openverse={"id": "0123abcd-0123-4123-8123-0123456789ab", "pedido": PEDIDO}))
    assert ct.schema_errors(yaml.safe_load(mini.read_text(encoding="utf8"))) == []


def test_schema_recusa_id_malformado_no_bloco_da_trilha(mini):
    _edit(mini, lambda d: d["trilha"]["music"].update(arquivo="assets/openverse/fundo.wav", openverse={"id": "nao-e-uuid", "pedido": PEDIDO}))
    erros = ct.schema_errors(yaml.safe_load(mini.read_text(encoding="utf8")))
    assert any("trilha/music/openverse/id" in e for e in erros), erros


def test_schema_exige_arquivo_quando_a_trilha_declara_o_bloco(mini):
    _edit(mini, lambda d: d["trilha"]["music"].update(openverse={"id": "0123abcd-0123-4123-8123-0123456789ab", "pedido": PEDIDO}))
    erros = ct.schema_errors(yaml.safe_load(mini.read_text(encoding="utf8")))
    assert any("trilha/music" in e for e in erros), erros


# ------------------------------------------------------------------------------------------------ portão (validate)

@needs_ffmpeg
def test_validate_aceita_trilha_openverse_aprovada(env, trilha_aprovada, mini):
    _exportar_trilha(mini, trilha_aprovada)
    rep = ct.validate(ct.load(mini))
    assert rep.ok, rep.errors


@needs_ffmpeg
def test_validate_recusa_trilha_openverse_sem_aprovacao_para_o_pedido(env, trilha_aprovada, mini):
    _exportar_trilha(mini, trilha_aprovada)
    _forjar(env, lambda d: d.update(revisoes=[]))  # a revisão some: o arquivo continua no lugar, sem veredito
    erros = _ov_erros(mini)
    assert erros and "nao_revisado" in erros[0], erros


@needs_ffmpeg
def test_validate_recusa_trilha_openverse_com_arquivo_trocado(env, trilha_aprovada, mini):
    nome = _exportar_trilha(mini, trilha_aprovada)
    (mini.parent / "assets" / "openverse" / nome).write_bytes(b"RIFF" + b"x" * 100)  # os bytes mudam depois da aprovação
    erros = _ov_erros(mini)
    assert any("arquivo trocado" in e for e in erros), erros


@needs_ffmpeg
def test_validate_recusa_bloco_de_trilha_com_arquivo_fora_de_assets_openverse(env, trilha_aprovada, mini):
    nome = _exportar_trilha(mini, trilha_aprovada)
    _copia_para_trilha(mini, nome)
    _edit(mini, lambda d: d["trilha"]["music"].update(openverse={"id": trilha_aprovada["id"], "pedido": PEDIDO}))
    erros = _ov_erros(mini)
    assert any("não está em assets/openverse/" in e for e in erros), erros


@needs_ffmpeg
def test_validate_recusa_arquivo_da_biblioteca_em_assets_openverse_sem_bloco_na_trilha(env, trilha_aprovada, mini):
    _exportar_trilha(mini, trilha_aprovada, com_bloco=False)
    erros = _ov_erros(mini)
    assert any("não declara o bloco openverse" in e for e in erros), erros


@needs_ffmpeg
def test_validate_recusa_copia_a_mao_da_biblioteca_como_trilha_sem_bloco(env, trilha_aprovada, mini):
    nome = _exportar_trilha(mini, trilha_aprovada)
    _copia_para_trilha(mini, nome)  # os mesmos bytes de um ativo da biblioteca, fora da pasta e sem o bloco
    erros = _ov_erros(mini)
    assert any("mesmos bytes" in e for e in erros), erros


@needs_ffmpeg
def test_validate_recusa_imagem_declarada_como_trilha(env, aprovado, mini):
    _exportar_trilha(mini, aprovado)  # a imagem aprovada em test_openverse: não é áudio
    erros = _ov_erros(mini)
    assert any("precisa de um áudio" in e for e in erros), erros


@needs_ffmpeg
def test_validate_recusa_trilha_com_licenca_que_nao_permite_modificacao(env, mini, tmp_path):
    item = baixar(env, tipo="audio", body=_wav_tom(tmp_path / "tom.wav"))
    _mudar_e_reaprovar(env, item["id"], licenca="by-nd", licenca_url="https://creativecommons.org/licenses/by-nd/4.0/", licenca_versao="4.0")
    _exportar_trilha(mini, item, aceito=True)  # by-nd tem aviso: o export pede --aceito-restricao, e a regra da trilha vem depois
    erros = _ov_erros(mini)
    assert any("não permite modificação" in e for e in erros), erros


@needs_ffmpeg
def test_trilha_de_arquivo_comum_segue_fora_do_portao(mini):
    """Regressão: uma trilha que não é da biblioteca continua como era (validate ok, sem bloco, sem cópia de origem)."""
    _sem_voz(mini)
    (mini.parent / "trilha").mkdir()
    _wav_tom(mini.parent / "trilha" / "fundo.wav", freq=440)
    _edit(mini, lambda d: d["trilha"]["music"].update(arquivo="trilha/fundo.wav"))
    rep = ct.validate(ct.load(mini))
    assert rep.ok, rep.errors
    wd = mini.parent / "wd"
    spec = compiler.compile_project(ct.load(mini), wd, None)
    assert spec["audio"]["music"]["arquivo"] == "assets/audio/trilha/arranjo.wav"
    assert not (wd / "assets" / "audio" / "trilha" / "origem").exists()


# ------------------------------------------------------------------------------------------------ compilação e créditos

@needs_ffmpeg
def test_compile_copia_o_audio_aprovado_para_a_composicao_e_arranja_a_trilha(env, trilha_aprovada, mini):
    nome = _exportar_trilha(mini, trilha_aprovada)
    _sem_voz(mini)
    wd = mini.parent / "wd"
    spec = compiler.compile_project(ct.load(mini), wd, None)
    origem = wd / "assets" / "audio" / "trilha" / "origem" / nome
    assert hashlib.sha256(origem.read_bytes()).hexdigest() == trilha_aprovada["sha256"]  # os bytes aprovados, não a fonte solta
    assert spec["audio"]["music"]["arquivo"] == "assets/audio/trilha/arranjo.wav"
    assert (wd / "assets" / "audio" / "trilha" / "arranjo.wav").is_file()


@needs_ffmpeg
def test_manifesto_e_creditos_levam_a_trilha(env, trilha_aprovada, mini, manifesto_falso):
    nome = _exportar_trilha(mini, trilha_aprovada)
    _sem_voz(mini)
    wd = mini.parent / "wd"
    compiler.compile_project(ct.load(mini), wd, None)
    files = render.tree_hash(wd)[1]
    dst = mini.parent / "out" / "mini.mp4"
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(b"mp4-falso")
    man = render.write_manifest(ct.load(mini), dst, backend="local", quality="draft", gpu=False,
                                info={"inputs_sha256": "e" * 64, "files": files}, timings={"render": 1.0}, log=lambda *_: None)
    ativo = man["openverse"]["ativos"][0]
    assert ativo["id"] == trilha_aprovada["id"] and ativo["destino"] == f"assets/audio/trilha/origem/{nome}"
    cred = (dst.parent / "mini.CREDITS-openverse.md").read_text(encoding="utf8")
    assert trilha_aprovada["sha256"] in cred and trilha_aprovada["id"] in cred


def _creditos_do_video(contrato) -> str:
    """Os créditos que o render grava ao lado do MP4, com a composição compilada de verdade (ffmpeg real, sem o node)."""
    wd = contrato.parent / "wd"
    compiler.compile_project(ct.load(contrato), wd, None)
    files = render.tree_hash(wd)[1]
    dst = fake_mp4(contrato, b"mp4-falso")
    oc.deliver(ct.load(contrato), dst, files)
    return (dst.parent / "mini.CREDITS-openverse.md").read_text(encoding="utf8")


NOTA_MODIFICADO = "áudio modificado/adaptado pelo simplicio-video (cortes, crossfade, filtro, ducking)"
INDICE_ILEGIVEL = "{ isto nao e json"


# ------------------------------------------------------------------------------------------------ F1/F2: sem bloco, a trilha não passa pelo índice

@needs_ffmpeg
def test_trilha_sem_bloco_com_indice_ilegivel_e_copia_da_biblioteca_e_recusada(env, trilha_aprovada, mini):
    """F1: sem o índice, a trilha copiada à mão passava com um aviso só; o arranjo muda os bytes, então o render não a pegava."""
    nome = _exportar_trilha(mini, trilha_aprovada)
    _copia_para_trilha(mini, nome)
    (env.lib / "index.json").write_text(INDICE_ILEGIVEL, encoding="utf8")
    rep = ct.validate(ct.load(mini))
    erros = [e for e in rep.errors if e.startswith("openverse:")]
    assert not rep.ok and erros and "trilha/fundo.wav" in erros[0] and "repare o índice" in erros[0], rep.errors  # o contrato novo: índice ilegível recusa


@needs_ffmpeg
def test_trilha_sem_bloco_com_indice_ilegivel_e_arquivo_dentro_da_biblioteca_e_recusada(env, trilha_aprovada, mini):
    """F1: um arquivo que mora na biblioteca não se confere sem o índice: recusa, em vez de seguir com um aviso."""
    _sem_voz(mini)
    arquivo = env.lib / trilha_aprovada["arquivo"]
    _edit(mini, lambda d: d["trilha"]["music"].update(arquivo=str(arquivo)))
    (env.lib / "index.json").write_text(INDICE_ILEGIVEL, encoding="utf8")
    rep = ct.validate(ct.load(mini))
    assert not rep.ok and any(e.startswith("openverse:") and "repare o índice" in e for e in rep.errors), rep.errors  # o contrato novo: índice ilegível recusa


@needs_ffmpeg
def test_trilha_de_arquivo_comum_com_indice_ilegivel_e_recusada(env, mini):
    """Índice de procedência presente e ilegível: sem ele não se sabe se a trilha sem bloco é da biblioteca, então recusa (antes seguia com aviso)."""
    _sem_voz(mini)
    (mini.parent / "trilha").mkdir()
    _wav_tom(mini.parent / "trilha" / "fundo.wav", freq=440)
    _edit(mini, lambda d: d["trilha"]["music"].update(arquivo="trilha/fundo.wav"))
    env.lib.mkdir(parents=True)
    (env.lib / "index.json").write_text(INDICE_ILEGIVEL, encoding="utf8")
    rep = ct.validate(ct.load(mini))
    erros = [e for e in rep.errors if e.startswith("openverse:")]
    assert not rep.ok and erros and "repare o índice" in erros[0], (rep.errors, rep.warnings)


@needs_ffmpeg
def test_copia_a_mao_da_trilha_com_indice_ilegivel_e_sem_files_tambem_e_recusada(env, trilha_aprovada, mini):
    """Índice presente e ilegível + pasta files/ ausente: a cópia à mão da trilha (sem bloco) passava. Agora recusa."""
    nome = _exportar_trilha(mini, trilha_aprovada)
    _copia_para_trilha(mini, nome)
    shutil.rmtree(env.lib / "files")
    (env.lib / "index.json").write_text(INDICE_ILEGIVEL, encoding="utf8")
    rep = ct.validate(ct.load(mini))
    erros = [e for e in rep.errors if e.startswith("openverse:")]
    assert not rep.ok and erros and "repare o índice" in erros[0], rep.errors


@needs_ffmpeg
def test_biblioteca_sem_index_json_nao_bloqueia_trilha_de_arquivo_comum(env, mini):
    """Guarda: sem index.json não há procedência a conferir (biblioteca nova): a trilha de arquivo comum segue como antes, sem aviso."""
    _sem_voz(mini)
    (mini.parent / "trilha").mkdir()
    _wav_tom(mini.parent / "trilha" / "fundo.wav", freq=440)
    _edit(mini, lambda d: d["trilha"]["music"].update(arquivo="trilha/fundo.wav"))
    rep = ct.validate(ct.load(mini))
    assert rep.ok and not [w for w in rep.warnings if "openverse" in w], (rep.errors, rep.warnings)


@needs_ffmpeg
@pytest.mark.parametrize("licenca, url", [
    ("by-nc", "https://creativecommons.org/licenses/by-nc/4.0/"),
    ("by-nc-sa", "https://creativecommons.org/licenses/by-nc-sa/4.0/"),
])
def test_trilha_com_licenca_nao_comercial_e_recusada_mesmo_com_aceite(env, mini, tmp_path, licenca, url):
    """AGENTS.md: trilha só com uso comercial claro. O aceite do export libera o ativo, não uma trilha de cliente não comercial."""
    item = baixar(env, tipo="audio", body=_wav_tom(tmp_path / "tom.wav"))
    _mudar_e_reaprovar(env, item["id"], licenca=licenca, licenca_url=url, licenca_versao="4.0")
    _exportar_trilha(mini, item, aceito=True)
    erros = _ov_erros(mini)
    assert erros and any("não é de uso comercial" in e for e in erros), erros


@needs_ffmpeg
def test_copia_a_mao_da_trilha_e_recusada_sem_os_arquivos_da_biblioteca(env, trilha_aprovada, mini):
    """F2: o índice lista o sha256 e a fonte bate: é da biblioteca mesmo sem o arquivo em files/ (o tamanho só contava arquivos existentes)."""
    nome = _exportar_trilha(mini, trilha_aprovada)
    _copia_para_trilha(mini, nome)
    shutil.rmtree(env.lib / "files")
    rep = ct.validate(ct.load(mini))
    erros = [e for e in rep.errors if e.startswith("openverse:")]
    assert erros and "mesmos bytes" in erros[0], rep.errors


# ------------------------------------------------------------------------------------------------ F3: o crédito da trilha diz que o áudio foi modificado

@needs_ffmpeg
def test_creditos_da_trilha_dizem_que_o_audio_foi_modificado(env, trilha_aprovada, mini):
    """F3 (CC BY 4.0 §3(a)(1)(B)): o crédito da trilha indica a modificação feita pelo motor."""
    _exportar_trilha(mini, trilha_aprovada)
    _sem_voz(mini)
    cred = _creditos_do_video(mini)
    assert NOTA_MODIFICADO in cred, cred


@needs_ffmpeg
def test_creditos_da_trilha_by_sa_repetem_o_aviso_da_licenca(env, mini, tmp_path):
    """F3: a trilha com by-sa (a única licença com aviso que a trilha aceita) repete o aviso de mesma licença no crédito."""
    item = baixar(env, tipo="audio", body=_wav_tom(tmp_path / "tom.wav"))
    _mudar_e_reaprovar(env, item["id"], licenca="by-sa", licenca_url="https://creativecommons.org/licenses/by-sa/4.0/", licenca_versao="4.0")
    _exportar_trilha(mini, item, aceito=True)
    _sem_voz(mini)
    cred = _creditos_do_video(mini)
    aviso = ov._licenses()["by-sa"]["aviso"]
    assert NOTA_MODIFICADO in cred and aviso in cred, cred


@needs_ffmpeg
def test_creditos_da_trilha_cc_by_nao_repetem_aviso_de_licenca(env, trilha_aprovada, mini):
    """Guarda: CC BY não tem aviso de licença; o crédito da trilha só ganha a nota de modificação."""
    _exportar_trilha(mini, trilha_aprovada)
    _sem_voz(mini)
    cred = _creditos_do_video(mini)
    assert NOTA_MODIFICADO in cred and "Aviso da licença" not in cred, cred


@needs_ffmpeg
def test_nota_de_audio_modificado_so_vai_a_trilha_e_nao_a_asset(env, trilha_aprovada, mini):
    """Guarda: um áudio da biblioteca usado como asset comum (não como trilha) não ganha a nota de modificação."""
    nome = Path(ov.export(trilha_aprovada["id"], PEDIDO, contrato=mini)["arquivo"]).name
    _sem_voz(mini)
    _edit(mini, lambda d: d.setdefault("assets", []).append({"arquivo": f"assets/openverse/{nome}", "destino": f"assets/openverse/{nome}",
                                                             "openverse": {"id": trilha_aprovada["id"], "pedido": PEDIDO}}))
    cred = _creditos_do_video(mini)
    assert trilha_aprovada["id"] in cred and "modificado/adaptado" not in cred, cred


# ------------------------------------------------------------------------------------------------ F5: um destino, um arquivo (a cópia da trilha entra)

@needs_ffmpeg
def test_asset_no_destino_da_copia_aprovada_da_trilha_nao_passa(env, trilha_aprovada, mini):
    """F5: o compilador grava a cópia aprovada da trilha em assets/audio/trilha/origem/; um asset ali seria trocado em silêncio."""
    nome = _exportar_trilha(mini, trilha_aprovada)
    _sem_voz(mini)
    (mini.parent / "assets" / "cliente").mkdir(parents=True)
    _wav_tom(mini.parent / "assets" / "cliente" / "sfx.wav", freq=880)
    destino = f"assets/audio/trilha/origem/{nome}"
    _edit(mini, lambda d: d.setdefault("assets", []).append({"arquivo": "assets/cliente/sfx.wav", "destino": destino}))
    rep = ct.validate(ct.load(mini))
    dup = [e for e in rep.errors if "duplicated destino" in e]
    assert dup and destino in dup[0] and "trilha.music" in dup[0], rep.errors


@needs_ffmpeg
def test_asset_no_destino_do_arranjo_da_trilha_nao_passa(env, mini):
    """F5: o compilador grava o arranjo em assets/audio/trilha/arranjo.wav; um asset com esse destino seria trocado em silêncio."""
    _sem_voz(mini)
    (mini.parent / "trilha").mkdir()
    _wav_tom(mini.parent / "trilha" / "fundo.wav", freq=440)
    (mini.parent / "assets" / "cliente").mkdir(parents=True)
    _wav_tom(mini.parent / "assets" / "cliente" / "sfx.wav", freq=880)

    def fn(d):
        d["trilha"]["music"]["arquivo"] = "trilha/fundo.wav"
        d.setdefault("assets", []).append({"arquivo": "assets/cliente/sfx.wav", "destino": trilha.ARRANJO_REL})
    _edit(mini, fn)
    rep = ct.validate(ct.load(mini))
    dup = [e for e in rep.errors if "duplicated destino" in e]
    assert dup and trilha.ARRANJO_REL in dup[0], rep.errors


# ------------------------------------------------------------------------------------------------ F6: mensagens

@needs_ffmpeg
def test_licenca_que_nao_permite_modificacao_na_trilha_lista_todas_as_que_permitem(env, mini, tmp_path):
    """F6a: a recusa da trilha lista as licenças que o motor aceita (permitem modificar e são de uso comercial), com o nome que a tabela dá."""
    item = baixar(env, tipo="audio", body=_wav_tom(tmp_path / "tom.wav"))
    _mudar_e_reaprovar(env, item["id"], licenca="by-nd", licenca_url="https://creativecommons.org/licenses/by-nd/4.0/", licenca_versao="4.0")
    _exportar_trilha(mini, item, aceito=True)
    erros = _ov_erros(mini)
    assert erros and "não permite modificação" in erros[0], erros
    permitidas = [r["nome"] for r in ov._licenses().values() if r["permite_modificacao"] and r["uso_comercial"]]
    assert permitidas and all(n in erros[0] for n in permitidas) and "CC BY-NC" not in erros[0], erros


@needs_ffmpeg
def test_arranjo_com_bytes_da_biblioteca_manda_declarar_o_bloco_da_trilha(env, trilha_aprovada):
    """F6c: quem tem os bytes da biblioteca na composição é a trilha: o conserto é o bloco em trilha.music, não um asset."""
    erros = oc.check_workdir(None, {trilha.ARRANJO_REL: trilha_aprovada["sha256"]}, ver=oc.Verification())
    assert len(erros) == 1 and "mesmos bytes" in erros[0] and "trilha.music.openverse" in erros[0] and "assets[]" not in erros[0], erros


# ------------------------------------------------------------------------------------------------ mix (build de verdade, sem HyperFrames)

def _mix(contrato, wd) -> Path:
    render.prepare(ct.load(contrato), wd, lambda *_: None)
    return wd / "build" / "mix.raw.wav"


@pytest.mark.render
@pytest.mark.skipif(not have_render_tools(), reason="needs node, npx and ffmpeg")
def test_render_mixa_a_trilha_openverse_sob_a_voz_com_o_ducking_de_voz(env, trilha_aprovada, mini):
    _exportar_trilha(mini, trilha_aprovada)
    # só a trilha e a voz no mix: sem SFX e sem o duck por envelope (duck_music_db), para medir só o ducking de voz.ducking
    _edit(mini, lambda d: (d["voz"].update(duck_music_db=0), [c.pop("sfx", None) for c in d["cenas"]]))
    voice.run(ct.load(mini), log=lambda *_: None)
    sem = _mix(mini, mini.parent / "wd-sem")
    _edit(mini, lambda d: d["voz"].update(ducking={}))  # voz.ducking presente (mesmo vazio): padrões -2.5 dB graves, -8 dB agudos
    com = _mix(mini, mini.parent / "wd-com")
    assert hashlib.sha256(com.read_bytes()).hexdigest() == hashlib.sha256(_mix(mini, mini.parent / "wd-com2").read_bytes()).hexdigest()
    sr, (x_sem, _) = le_wav(sem)
    _, (x_com, _) = le_wav(com)
    dentro, fora = 0.15, 0.60  # a fala (take de 0.3 s a partir de 0.05 s) e um trecho sem voz no vídeo de 1 s
    band = (2500, 6000)
    assert freq_dominante(x_sem, sr, fora, 2500, 6000, n=4096) == pytest.approx(SR_TOM, abs=15)  # o tom do Openverse está no mix
    assert potencia_banda_db(x_sem, sr, fora, *band, n=4096) > -60
    assert potencia_banda_db(x_com, sr, dentro, *band, n=4096) <= potencia_banda_db(x_sem, sr, dentro, *band, n=4096) - 6
    assert abs(potencia_banda_db(x_com, sr, fora, *band, n=4096) - potencia_banda_db(x_sem, sr, fora, *band, n=4096)) < 1.0


@pytest.mark.render
@pytest.mark.skipif(not have_render_tools(), reason="needs node, npx and ffmpeg")
def test_render_de_verdade_com_trilha_openverse_grava_manifesto_e_creditos_iguais_em_duas_execucoes(env, trilha_aprovada, mini):
    nome = _exportar_trilha(mini, trilha_aprovada)
    voice.run(ct.load(mini), log=lambda *_: None)
    a = render.render_local(ct.load(mini), log=lambda *_: None)
    cred_a = (mini.parent / "out" / "mini.CREDITS-openverse.md").read_bytes()
    b = render.render_local(ct.load(mini), log=lambda *_: None)
    assert a["inputs_sha256"] == b["inputs_sha256"] and a["openverse"] == b["openverse"]
    assert a["inputs"][f"assets/audio/trilha/origem/{nome}"] == trilha_aprovada["sha256"]
    assert a["openverse"]["ativos"][0]["id"] == trilha_aprovada["id"]
    assert (mini.parent / "out" / "mini.CREDITS-openverse.md").read_bytes() == cred_a
    for k in ("video_frames_sha256", "audio_pcm_sha256"):
        assert a["output"][k] == b["output"][k], k
