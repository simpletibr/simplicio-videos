"""Follow-ups da revisão do Openverse no contrato (#113): pasta em qualquer profundidade, índice ilegível, crédito por licença
e recusa de cópia à mão sem o índice. Offline; a biblioteca é uma pasta temporária."""

from __future__ import annotations

import hashlib
from pathlib import Path

from simplicio_video import openverse as ov
from simplicio_video import openverse_contract as oc


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _biblioteca(tmp_path: Path, monkeypatch) -> Path:
    lib = tmp_path / "biblioteca"
    (lib / "files").mkdir(parents=True)
    monkeypatch.setenv("OPENVERSE_LIBRARY_DIR", str(lib))
    return lib


def test_pasta_assets_openverse_vale_em_qualquer_profundidade_fora_do_contrato(tmp_path):
    base = tmp_path / "contrato"
    base.mkdir()
    fora = tmp_path / "outro" / "assets" / "openverse" / "sub" / "x.png"
    assert oc.in_openverse_dir(fora, base)
    assert not oc.in_openverse_dir(tmp_path / "outro" / "assets" / "x.png", base)


def test_marcador_de_credito_traz_a_licenca(tmp_path):
    sha = _sha(b"x")
    rec = {"id": "0123abcd-0123-0123-0123-0123456789ab", "sha256": sha, "licenca": "cc0", "licenca_versao": "1.0"}
    outra = {**rec, "licenca": "by-sa", "licenca_versao": "4.0"}
    assert "licença" in ov._credit_marker(rec)
    assert ov._credit_marker(rec) != ov._credit_marker(outra)
    assert ov._credit_marker(outra) not in f"- `a.png`: ... {ov._credit_marker(rec)}."


def test_hashes_da_biblioteca_sem_indice_vem_da_pasta_files(tmp_path, monkeypatch):
    lib = _biblioteca(tmp_path, monkeypatch)
    sha = _sha(b"imagem")
    (lib / "files" / f"{sha}.jpg").write_bytes(b"imagem")
    (lib / "files" / "lixo.txt").write_bytes(b"nao e um sha")
    assert ov.library_hashes(None) == {sha: None}
    idx = {"itens": {"0123abcd-0123-0123-0123-0123456789ab": {"sha256": sha}}}
    assert ov.library_hashes(idx) == {sha: "0123abcd-0123-0123-0123-0123456789ab"}


def test_copia_a_mao_da_biblioteca_e_recusada_mesmo_com_indice_ilegivel(tmp_path, monkeypatch):
    lib = _biblioteca(tmp_path, monkeypatch)
    dados = b"ativo aprovado da biblioteca"
    sha = _sha(dados)
    (lib / "files" / f"{sha}.jpg").write_bytes(dados)
    (lib / "index.json").write_text("{ isto nao e json", encoding="utf8")  # índice ilegível
    erros = oc.check_workdir(None, {"templates/capa.jpg": sha}, ver=oc.Verification())
    assert len(erros) == 1 and "templates/capa.jpg" in erros[0] and "mesmos bytes" in erros[0], erros
