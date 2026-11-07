"""U05 (caracterização): os sha256 de arquivo e os JSON canônicos que hoje existem copiados no pacote.

Estes testes descrevem o comportamento de HOJE e ficam verdes antes e depois de as cópias virarem chamadas de `fsutil`:
os mesmos bytes de hash, as mesmas exceções para os mesmos arquivos ruins (ausente, pasta, FIFO, link) e o mesmo hex congelado
de tudo que entra em manifesto, lock, plano, cache ou recibo.
"""
import ast
import hashlib
import inspect
import json
import os
import random
import sys
import threading
from pathlib import Path

import pytest

from helpers import FIXTURE
from simplicio_video import (busca, contract, doctor_trilhas, download, fsutil, installer, moneyprinter, openverse, render, shorts,
                             social, swap, voice)
from simplicio_video import video_to_skill as v2s

posix = pytest.mark.skipif(not hasattr(os, "mkfifo") or sys.platform == "win32", reason="POSIX: FIFO e link simbólico")

# ------------------------------------------------------------------------------------------------ sha256 de arquivo

# Funções que abrem o arquivo e levantam o OSError do open: o nome público (ou privado) de cada módulo da ficha.
ABREM = {
    "openverse.sha256_file": openverse.sha256_file,
    "social.sha256_file": social.sha256_file,
    "swap.sha256_file": swap.sha256_file,
    "voice.sha256_file": voice.sha256_file,
    "shorts.sha256_file": shorts.sha256_file,
    "render.sha256_file": render.sha256_file,
    "download._sha256": download._sha256,
    "moneyprinter._sha256": moneyprinter._sha256,
}
# Funções que devolvem None quando o arquivo não é um arquivo comum legível (a checagem de hoje).
TOLERANTES = {
    "installer.sha256_of": installer.sha256_of,
    "video_to_skill._sha256_file": v2s._sha256_file,
    "doctor_trilhas._sha256": doctor_trilhas._sha256,
}
TODAS = {**ABREM, **TOLERANTES, "fsutil.sha256_file": fsutil.sha256_file}


def _arquivo(tmp_path, dados: bytes, nome: str = "a.bin"):
    p = tmp_path / nome
    p.write_bytes(dados)
    return p


@pytest.fixture(scope="module")
def grande(tmp_path_factory):
    """2 blocos de 1 MiB e meio: o hash precisa passar por mais de uma leitura e por um bloco curto no fim."""
    p = tmp_path_factory.mktemp("paridade") / "grande.bin"
    p.write_bytes("paridade ç\n".encode("utf8") * 200000)
    return p


@pytest.fixture(scope="module")
def medio(tmp_path_factory):
    """Abaixo de 1 MiB, o teto do `doctor_trilhas` para arquivo fixado: o único que recusa um arquivo maior."""
    p = tmp_path_factory.mktemp("paridade") / "medio.bin"
    p.write_bytes("paridade ç\n".encode("utf8") * 75000)
    assert p.stat().st_size < doctor_trilhas.MAX_ARQUIVO_FIXADO
    return p


@pytest.mark.parametrize("nome", sorted(TODAS))
def test_todas_as_copias_dao_o_hex_do_hashlib_para_um_arquivo_fixo(nome, medio):
    assert TODAS[nome](medio) == hashlib.sha256(medio.read_bytes()).hexdigest()


@pytest.mark.parametrize("nome", sorted(set(TODAS) - {"doctor_trilhas._sha256"}))
def test_todas_as_copias_leem_mais_de_um_bloco_de_1_mib(nome, grande):
    assert grande.stat().st_size > 2 * 1024 * 1024
    assert TODAS[nome](grande) == hashlib.sha256(grande.read_bytes()).hexdigest()


def test_doctor_trilhas_recusa_arquivo_fixado_acima_de_1_mib(grande):
    assert doctor_trilhas._sha256(grande) is None


@pytest.mark.parametrize("nome", sorted(TODAS))
def test_todas_as_copias_dao_o_hex_do_arquivo_vazio_e_de_abc(nome, tmp_path):
    assert TODAS[nome](_arquivo(tmp_path, b"")) == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    assert TODAS[nome](_arquivo(tmp_path, b"abc", "abc.bin")) == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


@pytest.mark.parametrize("nome", sorted(TODAS))
def test_o_hex_e_texto_minusculo_de_64_caracteres(nome, tmp_path):
    hexa = TODAS[nome](_arquivo(tmp_path, "çã".encode("utf8")))
    assert isinstance(hexa, str) and len(hexa) == 64 and hexa == hexa.lower()


@pytest.mark.parametrize("nome", sorted(ABREM))
def test_arquivo_ausente_levanta_filenotfounderror(nome, tmp_path):
    with pytest.raises(FileNotFoundError):
        ABREM[nome](tmp_path / "nao-existe.bin")


@posix
@pytest.mark.parametrize("nome", sorted(ABREM))
def test_pasta_levanta_isadirectoryerror(nome, tmp_path):
    with pytest.raises(IsADirectoryError):
        ABREM[nome](tmp_path)


@posix
@pytest.mark.parametrize("nome", sorted(ABREM))
def test_link_simbolico_para_arquivo_comum_da_o_hash_do_alvo(nome, tmp_path):
    alvo = _arquivo(tmp_path, b"alvo do link")
    link = tmp_path / "link.bin"
    link.symlink_to(alvo)
    assert ABREM[nome](link) == hashlib.sha256(b"alvo do link").hexdigest()


@posix
@pytest.mark.parametrize("nome", sorted(ABREM))
def test_link_quebrado_levanta_filenotfounderror(nome, tmp_path):
    link = tmp_path / "quebrado.bin"
    link.symlink_to(tmp_path / "nao-existe.bin")
    with pytest.raises(FileNotFoundError):
        ABREM[nome](link)


@pytest.mark.parametrize("nome", ["voice.sha256_file", "openverse.sha256_file", "social.sha256_file", "swap.sha256_file", "render.sha256_file"])
def test_as_copias_de_um_argumento_aceitam_caminho_em_texto(nome, tmp_path):
    p = _arquivo(tmp_path, b"abc")
    assert ABREM[nome](str(p)) == hashlib.sha256(b"abc").hexdigest()


# ------------------------------------------------------------------ os 3 que checam "arquivo comum" antes de ler

def _sem_travar(fn, *args, espera: float = 5.0):
    """Roda `fn(*args)` numa thread. Um open() de FIFO sem escritor trava para sempre: se travar, abre o FIFO do outro lado para
    soltar a thread e reprova o teste em vez de pendurar a suíte."""
    resultado = {}

    def alvo():
        try:
            resultado["valor"] = fn(*args)
        except BaseException as exc:  # noqa: BLE001 - o teste quer o tipo, qualquer que seja
            resultado["erro"] = exc

    t = threading.Thread(target=alvo, daemon=True)
    t.start()
    t.join(espera)
    if t.is_alive():
        fd = os.open(args[0], os.O_RDWR)  # um "escritor" que solta o open() preso
        try:
            t.join(2)
        finally:
            os.close(fd)
        pytest.fail(f"{getattr(fn, '__qualname__', fn)} travou num FIFO sem escritor")
    return resultado


@pytest.mark.parametrize("nome", sorted(TOLERANTES))
def test_tolerantes_ausente_e_none(nome, tmp_path):
    assert TOLERANTES[nome](tmp_path / "nao-existe.bin") is None


@pytest.mark.parametrize("nome", sorted(TOLERANTES))
def test_tolerantes_pasta_e_none(nome, tmp_path):
    assert TOLERANTES[nome](tmp_path) is None


@posix
@pytest.mark.parametrize("nome", sorted(TOLERANTES))
def test_tolerantes_fifo_sem_escritor_e_none_e_nao_trava(nome, tmp_path):
    fifo = tmp_path / "fila"
    os.mkfifo(fifo)
    r = _sem_travar(TOLERANTES[nome], fifo)
    assert r == {"valor": None}


@posix
@pytest.mark.parametrize("nome", sorted(TOLERANTES))
def test_tolerantes_link_para_fifo_e_none_e_nao_trava(nome, tmp_path):
    fifo = tmp_path / "fila"
    os.mkfifo(fifo)
    link = tmp_path / "link-fila"
    link.symlink_to(fifo)
    r = _sem_travar(TOLERANTES[nome], link)
    assert r == {"valor": None}


@posix
@pytest.mark.parametrize("nome", sorted(TOLERANTES))
def test_tolerantes_link_quebrado_e_none(nome, tmp_path):
    link = tmp_path / "quebrado.bin"
    link.symlink_to(tmp_path / "nao-existe.bin")
    assert TOLERANTES[nome](link) is None


@posix
@pytest.mark.parametrize("nome", ["installer.sha256_of", "video_to_skill._sha256_file"])
def test_installer_e_video_to_skill_seguem_link_para_arquivo_comum(nome, tmp_path):
    alvo = _arquivo(tmp_path, b"alvo do link")
    link = tmp_path / "link.bin"
    link.symlink_to(alvo)
    assert TOLERANTES[nome](link) == hashlib.sha256(b"alvo do link").hexdigest()


@posix
def test_doctor_trilhas_recusa_link_simbolico_mesmo_para_arquivo_comum(tmp_path):
    alvo = _arquivo(tmp_path, b"alvo do link")
    link = tmp_path / "link.bin"
    link.symlink_to(alvo)
    assert doctor_trilhas._sha256(link) is None
    assert doctor_trilhas._sha256(alvo) == hashlib.sha256(b"alvo do link").hexdigest()


def test_installer_sha256_of_teto_vem_de_max_file_bytes(tmp_path, monkeypatch):
    monkeypatch.setattr(installer, "MAX_FILE_BYTES", 8)
    assert installer.sha256_of(_arquivo(tmp_path, b"12345678")) == hashlib.sha256(b"12345678").hexdigest()
    assert installer.sha256_of(_arquivo(tmp_path, b"123456789", "b.bin")) is None


def test_video_to_skill_sha256_file_teto_por_argumento(tmp_path):
    cem = _arquivo(tmp_path, b"x" * 100)
    assert v2s._sha256_file(cem, 100) == hashlib.sha256(b"x" * 100).hexdigest()
    assert v2s._sha256_file(cem, 99) is None
    assert v2s._sha256_file(_arquivo(tmp_path, b"", "vazio.bin"), 0) == hashlib.sha256(b"").hexdigest()
    assert v2s._sha256_file(cem, 0) is None


def test_video_to_skill_sha256_file_teto_negativo_nunca_levanta(tmp_path):
    assert v2s._sha256_file(_arquivo(tmp_path, b"abc"), -1) is None


def test_video_to_skill_sha256_file_teto_padrao_e_max_member_bytes():
    assert inspect.signature(v2s._sha256_file).parameters["limit"].default == v2s.MAX_MEMBER_BYTES


def test_doctor_trilhas_sha256_teto_vem_de_max_arquivo_fixado(tmp_path, monkeypatch):
    monkeypatch.setattr(doctor_trilhas, "MAX_ARQUIVO_FIXADO", 8)
    assert doctor_trilhas._sha256(_arquivo(tmp_path, b"12345678")) == hashlib.sha256(b"12345678").hexdigest()
    assert doctor_trilhas._sha256(_arquivo(tmp_path, b"123456789", "b.bin")) is None


# ------------------------------------------------------------------------------------------------------ canonical

REFERENCIA = {"sort_keys": True, "ensure_ascii": False, "separators": (",", ":")}
CANONICOS = {
    "contract.canonical": contract.canonical,
    "social.canonical": social.canonical,
    "busca._canonico": busca._canonico,
    "fsutil.canonical_json": fsutil.canonical_json,
}


OBJETOS = [
    {},
    [],
    None,
    "só um texto ç",
    {"b": [1, {"ç": "á", "a": 1.25}], "a": None, "ñ": True},
    {"z": 1, "a": 2, "m": {"y": [3, 2, 1], "b": {}}},
    {"acento": "ação", "emoji": "🎬", "quebra": "a\nb", "tab": "a\tb", "aspas": 'a"b', "barra": "a\\b", "del": "\x7f", "ls": " "},
    {"inteiro": 10 ** 30, "negativo": -3, "zero": 0, "float": 0.1, "exp": 1e-9, "grande": 1.5e300, "bool": [True, False]},
    {"nan": float("nan"), "inf": float("inf")},
    {"1": "um", "2": "dois", "10": "dez"},
    {1: "um", 2: "dois", 10: "dez"},
    {True: "sim", None: "nada", 1.5: "meio"},
    [[[[[]]]], {"a": [{"b": [{"c": []}]}]}],
    {"ç": 1, "c": 2, "ĉ": 3, "z": 4, "é": 5, "e": 6},
]


def _aleatorio(r: random.Random, fundo: int = 0):
    tipo = r.choice(["int", "float", "str", "bool", "none"] + (["list", "dict"] * 2 if fundo < 4 else []))
    if tipo == "int":
        return r.randint(-10 ** 12, 10 ** 12)
    if tipo == "float":
        return r.choice([0.0, -0.0, 1.5, 1e22, 1e-7, r.random() * 1000])
    if tipo == "str":
        return "".join(r.choice("abcxyzçãéñ 🎬\n\"\\/\x00\x1f\x7f ") for _ in range(r.randint(0, 8)))
    if tipo == "bool":
        return r.choice([True, False])
    if tipo == "none":
        return None
    if tipo == "list":
        return [_aleatorio(r, fundo + 1) for _ in range(r.randint(0, 4))]
    return {"".join(r.choice("abcçãñ0 ") for _ in range(r.randint(0, 4))): _aleatorio(r, fundo + 1) for _ in range(r.randint(0, 4))}


def _gerados(n: int = 1000):
    r = random.Random(20260507)
    return [_aleatorio(r) for _ in range(n)]


@pytest.mark.parametrize("nome", sorted(CANONICOS))
@pytest.mark.parametrize("obj", OBJETOS, ids=[f"objeto{i}" for i in range(len(OBJETOS))])
def test_canonical_dos_quatro_e_a_formula_de_hoje(nome, obj):
    try:
        esperado = json.dumps(obj, **REFERENCIA)
    except (TypeError, ValueError) as e:
        with pytest.raises(type(e)):
            CANONICOS[nome](obj)
        return
    assert CANONICOS[nome](obj) == esperado


@pytest.mark.parametrize("nome", sorted(CANONICOS))
def test_canonical_de_mil_objetos_aleatorios_e_a_formula_de_hoje(nome):
    for obj in _gerados():
        assert CANONICOS[nome](obj) == json.dumps(obj, **REFERENCIA)


def test_installer_digest_de_mil_objetos_aleatorios_e_o_sha256_do_canonico():
    for obj in _gerados():
        esperado = "sha256:" + hashlib.sha256(json.dumps(obj, **REFERENCIA).encode("utf-8")).hexdigest()
        assert installer._digest(obj) == esperado


@pytest.mark.parametrize("obj", [object(), {"a": {1, 2}}, {1: "a", "b": 2}], ids=["objeto", "set", "chaves-mistas"])
def test_canonical_e_installer_digest_levantam_o_mesmo_tipo_de_erro(obj):
    with pytest.raises(TypeError):
        json.dumps(obj, **REFERENCIA)
    for fn in (*CANONICOS.values(), installer._digest):
        with pytest.raises(TypeError):
            fn(obj)


def test_canonical_de_referencia_circular_levanta_valueerror():
    ciclo: list = []
    ciclo.append(ciclo)
    for fn in (*CANONICOS.values(), installer._digest):
        with pytest.raises(ValueError):
            fn(ciclo)


def test_canonical_texto_congelado():
    obj = {"b": [1, {"ç": "á", "a": 1.25}], "a": None, "ñ": True}
    for fn in CANONICOS.values():
        assert fn(obj) == '{"a":null,"b":[1,{"a":1.25,"ç":"á"}],"ñ":true}'


# ------------------------------------------------------------------------------- hex congelado (antes da mudança)

def test_contract_sha256_do_mini_e_o_hex_de_hoje():
    """É o `contract_sha256` do manifesto de render, do bundle e da prévia: qualquer separador a mais muda este valor."""
    c = contract.load(FIXTURE / "contract.yaml")
    assert c.sha256() == "53bb01e856b90e559c3a2876c02cf0b4c5712778f192eb2f6a1bae0b20cbd491"
    assert c.sha256() == hashlib.sha256(json.dumps(c.data, **REFERENCIA).encode()).hexdigest()


def test_plan_id_do_social_e_o_hex_de_hoje():
    body = {"schema": "simplicio.social-plan/v1", "videos": [{"caption": "Olá, mundo ç", "n": 1}], "a": None}
    assert social.plan_id(body) == "4c054e0b6c9f884e152479868e44690379ac564b18504ed79e3b3e066e2c3835"


def test_carimbo_da_tabela_de_limites_do_social_e_o_hex_de_hoje():
    carimbo = social._limits_stamp(social.limits_table())
    assert carimbo["sha256"] == "1af500959a97474c58668ddb060efc7dcbe0ee9587adff255e5f6f567b9c89ff"
    assert carimbo["schema"] == "simplicio.social-limits/v1"


def test_chave_de_cache_e_sha_da_busca_sao_os_hex_de_hoje():
    assert busca._chave_cache({"query": "açaí", "n": 3}) == "d2cc3a6c14775017329c500a8660061cda365172887dc9d4a12220cdaaf7b9b5"
    assert busca._sha(busca._canonico({"b": [1, 2], "a": "ç"})) == "f2f1610881595f1597217c47d3b415492ae4ace94124e308386cfa5be1a7b687"


def test_digest_do_plano_do_installer_e_o_hex_de_hoje():
    assert installer._digest({"schema": "x", "hosts": ["claude", "codex"], "n": 3, "ç": "á"}) == \
        "sha256:f24e809529843fac99c4fba1a39d2780a819043bce6f63f1a95cb9e38461c4c8"


# ------------------------------------------------------------------- depois de U05: uma implementação só (e os nomes antigos)

SRC = Path(fsutil.__file__).parent


def test_os_nomes_publicos_antigos_sao_o_sha256_file_do_fsutil():
    for nome, fn in ABREM.items():
        assert fn is fsutil.sha256_file, nome


def test_os_nomes_antigos_do_canonical_sao_o_canonical_json_do_fsutil():
    for nome in ("contract.canonical", "social.canonical", "busca._canonico"):
        assert CANONICOS[nome] is fsutil.canonical_json, nome


def _modulos():
    for p in sorted(SRC.rglob("*.py")):
        yield p.relative_to(SRC).as_posix(), ast.parse(p.read_text(encoding="utf8"))


def test_so_o_fsutil_e_os_dois_de_arquivo_comum_hasheiam_um_arquivo_por_funcao_propria():
    """O que `pronto.py` mede: função de nome `*sha*` que usa hashlib e lê arquivo. `installer.sha256_of` e
    `video_to_skill._sha256_file` leem por `hostos.read_regular` (arquivo comum com teto, fstat no MESMO descritor da leitura: sem
    corrida entre a checagem e a leitura) e ficam de propósito: o segundo confere o executável do upstream antes de rodá-lo."""
    achadas = set()
    for rel, arvore in _modulos():
        texto = (SRC / rel).read_text(encoding="utf8")
        for n in ast.walk(arvore):
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and "sha" in n.name.lower():
                src = ast.get_source_segment(texto, n) or ""
                if "hashlib" in src and ("open(" in src or "read_bytes" in src or "os.read" in src):
                    achadas.add(f"{rel}:{n.name}")
    assert achadas == {"fsutil.py:sha256_file", "installer.py:sha256_of", "video_to_skill.py:_sha256_file"}


@pytest.mark.parametrize("nome", ["installer.sha256_of", "video_to_skill._sha256_file"])
def test_a_checagem_de_arquivo_comum_e_a_leitura_sao_a_mesma_abertura(nome, tmp_path, monkeypatch):
    """Os dois que conferem um executável ou um recibo abrem o arquivo UMA vez, por `hostos.read_regular` e com o teto: um
    FIFO posto no caminho entre uma checagem por caminho e uma segunda abertura travaria a chamada."""
    from simplicio_video import hostos

    pedidos = []
    real = hostos.read_regular
    monkeypatch.setattr(hostos, "read_regular", lambda caminho, limite: pedidos.append((caminho, limite)) or real(caminho, limite))
    p = _arquivo(tmp_path, b"abc")
    esperado = {"installer.sha256_of": (p, installer.MAX_FILE_BYTES), "video_to_skill._sha256_file": (p, 10)}[nome]
    args = (p, 10) if nome == "video_to_skill._sha256_file" else (p,)
    assert TOLERANTES[nome](*args) == hashlib.sha256(b"abc").hexdigest()
    assert pedidos == [esperado]


def test_so_o_fsutil_escreve_o_json_canonico():
    """`json.dumps` com sort_keys, ensure_ascii e separators juntos é o canônico: uma só vez no pacote."""
    achadas = []
    for rel, arvore in _modulos():
        for n in ast.walk(arvore):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "dumps":
                if {"sort_keys", "ensure_ascii", "separators"} <= {k.arg for k in n.keywords}:
                    achadas.append(rel)
    assert achadas == ["fsutil.py"]


def test_render_nao_importa_o_voice_so_para_o_sha256():
    arvore = ast.parse((SRC / "render.py").read_text(encoding="utf8"))
    de_voice = [n for n in ast.walk(arvore) if isinstance(n, ast.ImportFrom) and n.level == 1 and n.module == "voice"]
    assert de_voice == []
    assert render.sha256_file is fsutil.sha256_file


def test_o_fsutil_passa_pela_varredura_de_fronteira_do_social():
    """O `social` pode importar o `fsutil` (ele está em RELATIVOS_PERMITIDOS) porque o próprio `fsutil` não tem rede, ambiente,
    processo nem import relativo."""
    from social_guard import RELATIVOS_PERMITIDOS, violacoes_de_codigo

    assert "fsutil" in RELATIVOS_PERMITIDOS
    assert violacoes_de_codigo((SRC / "fsutil.py").read_text(encoding="utf8")) == []
