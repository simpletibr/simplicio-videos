"""fsutil (U05.0): the one sha256 of a file and the one canonical JSON that the other modules will import (U05)."""
import hashlib
import json

import pytest

from simplicio_video import fsutil


def _arquivo(tmp_path, dados: bytes, nome: str = "a.bin"):
    p = tmp_path / nome
    p.write_bytes(dados)
    return p


# ------------------------------------------------------------------ sha256_file

def test_sha256_file_de_arquivo_conhecido_bate_com_hashlib(tmp_path):
    dados = "conteúdo com acento\n".encode("utf8") * 7
    assert fsutil.sha256_file(_arquivo(tmp_path, dados)) == hashlib.sha256(dados).hexdigest()


def test_sha256_file_de_vazio(tmp_path):
    assert fsutil.sha256_file(_arquivo(tmp_path, b"")) == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


def test_sha256_file_de_abc_e_o_valor_publicado(tmp_path):
    assert fsutil.sha256_file(_arquivo(tmp_path, b"abc")) == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


def test_sha256_file_lê_em_blocos_de_1_mib(tmp_path):
    # 2 MiB + 3 bytes: more than one block and a short last one; the digest must still be the whole file's
    dados = bytes(range(256)) * (2 * 1024 * 4) + b"xyz"
    assert len(dados) == 2 * 1024 * 1024 + 3
    assert fsutil.sha256_file(_arquivo(tmp_path, dados)) == hashlib.sha256(dados).hexdigest()


def test_sha256_file_aceita_str_alem_de_path(tmp_path):
    p = _arquivo(tmp_path, b"abc")
    assert fsutil.sha256_file(str(p)) == fsutil.sha256_file(p)


def test_sha256_file_arquivo_ausente_propaga_oserror(tmp_path):
    with pytest.raises(FileNotFoundError):
        fsutil.sha256_file(tmp_path / "nao-existe")


def test_sha256_file_pasta_propaga_oserror(tmp_path):
    with pytest.raises(OSError):
        fsutil.sha256_file(tmp_path)


def test_sha256_file_limit_igual_ao_tamanho_passa(tmp_path):
    dados = b"x" * 100
    assert fsutil.sha256_file(_arquivo(tmp_path, dados), limit=100) == hashlib.sha256(dados).hexdigest()


def test_sha256_file_limit_excedido_levanta_valueerror(tmp_path):
    with pytest.raises(ValueError):
        fsutil.sha256_file(_arquivo(tmp_path, b"x" * 101), limit=100)


def test_sha256_file_limit_zero(tmp_path):
    assert fsutil.sha256_file(_arquivo(tmp_path, b""), limit=0) == hashlib.sha256(b"").hexdigest()
    with pytest.raises(ValueError):
        fsutil.sha256_file(_arquivo(tmp_path, b"x", "b.bin"), limit=0)


def test_sha256_file_limit_so_é_nomeado(tmp_path):
    with pytest.raises(TypeError):
        fsutil.sha256_file(_arquivo(tmp_path, b"abc"), 10)  # the limit is keyword-only


def test_sha256_file_com_limit_nunca_hasheia_mais_que_limit_mais_um(tmp_path, monkeypatch):
    """A file far over the cap is refused after `limit + 1` bytes, not after hashing all of it."""
    hasheados: list[int] = []
    real = hashlib.sha256

    class Espia:
        def __init__(self):
            self._h = real()

        def update(self, dados):
            hasheados.append(len(dados))
            self._h.update(dados)

        def hexdigest(self):
            return self._h.hexdigest()

    p = _arquivo(tmp_path, b"x" * (3 * 1024 * 1024))
    monkeypatch.setattr(hashlib, "sha256", lambda *a: Espia())
    with pytest.raises(ValueError):
        fsutil.sha256_file(p, limit=10)
    assert sum(hasheados) <= 11


# ------------------------------------------------------------------ canonical_json

def test_canonical_json_ordena_chaves_e_nao_usa_espaco():
    assert fsutil.canonical_json({"b": 1, "a": [1, 2, {"d": None, "c": True}]}) == '{"a":[1,2,{"c":true,"d":null}],"b":1}'


def test_canonical_json_mantém_acento_sem_escapar():
    assert fsutil.canonical_json({"b": 1, "á": "ç ã é"}) == '{"b":1,"á":"ç ã é"}'


def test_canonical_json_nao_depende_da_ordem_de_insercao():
    assert fsutil.canonical_json({"x": 1, "y": 2}) == fsutil.canonical_json({"y": 2, "x": 1})


def test_canonical_json_preserva_a_ordem_das_listas():
    assert fsutil.canonical_json([3, 1, 2]) == "[3,1,2]"


def test_canonical_json_é_a_formula_da_ficha():
    obj = {"z": [1.5, "ü", {"k": "v"}], "a": {"b": {"c": 0}}, "é": False}
    assert fsutil.canonical_json(obj) == json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def test_canonical_json_de_escalares():
    assert fsutil.canonical_json("é") == '"é"'
    assert fsutil.canonical_json(None) == "null"


def test_canonical_json_recusa_o_que_json_recusa():
    with pytest.raises(TypeError):
        fsutil.canonical_json({"a": object()})


def test_canonical_json_ida_e_volta():
    obj = {"nome": "Ação", "n": [1, 2], "x": {"y": None}}
    assert json.loads(fsutil.canonical_json(obj)) == obj
