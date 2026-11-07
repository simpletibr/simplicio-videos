"""V2, "o doctor lê o registro, não nomes nem privados" (H3 + S3 + S6 do PLAN-V). Comportamento idêntico: só muda de onde o doctor lê.

Três cópias de uma regra que o registro ou o módulo da trilha já têm:

H3  o doctor julgava o binário gerenciado do video-to-skill com `v2s._platform()` e `v2s._sha256_file()` (privados de outro módulo) e repetia
    o predicado de `video_to_skill.find_binary` (asset da plataforma, não é link, sha256 do arquivo == `member_sha256`). Agora há UMA
    implementação, `video_to_skill.managed_verified(exe=None) -> bool` (sem rodar processo), e as duas portas a chamam.
S3  `tools.NPX_TRACKS = ("hypit",)` era lido por nome em tools.py e duas vezes no doctor: vira o campo `Tool.npx` (True só no hypit).
S6  o doctor escolhia o texto do upstream das trilhas pin-only por `t.name == "video_to_skill"`: agora lê `t.checkout_env`.

Duas partes:

1. CARACTERIZAÇÃO (verde antes e depois): as linhas do doctor para o binário do video-to-skill (gerenciado conferido, com sha errado, link,
   ausente, só no PATH, plataforma sem binário) e para o hypit (npx, sem npx, Node antigo, binário no PATH, binário quebrado), o texto do
   upstream das duas trilhas pin-only, e o `doctor trilhas --json` inteiro (sha256 do texto normalizado) nesses estados, que os goldens de
   tests/packaging/test_registro_trilhas.py (máquina vazia, saudável, overrides) não cobrem.
2. O REGISTRO (vermelho antes): `managed_verified` existe e é a única implementação do predicado (AST) e as duas portas a usam; o doctor
   não toca privado de outro módulo; `Tool.npx` existe e só o hypit é True; `NPX_TRACKS` não existe mais; nenhum nome de trilha literal no
   doctor (AST); o texto do upstream pin-only segue `checkout_env`, não o nome.
"""
from __future__ import annotations

import ast
import dataclasses
import hashlib
import inspect
import json
import os
import sys
from pathlib import Path

import pytest

# the doctor's machine (sealed PATH, fake git) is defined in tests/packaging, which is not a package: its folder is put on sys.path
# when pytest collects a file there, and not when this file runs alone
sys.path.insert(0, str(Path(__file__).resolve().parent / "packaging"))
import _caixa  # noqa: E402
from _caixa import _Lazy, posix_real, write_fake_tool  # noqa: E402
from helpers import ROOT, SRC  # noqa: E402
from simplicio_video import childio, tools, video_to_skill as v2s  # noqa: E402
from test_doctor_trilhas import _c, _rede_em_dia, _trilha, monta_saudavel  # noqa: E402
from test_doctor_trilhas import ambiente as _ambiente_do_doctor  # noqa: E402
from test_registro_trilhas import _normaliza  # noqa: E402

dt = _Lazy("simplicio_video.doctor_trilhas")
saude = _caixa.saude  # the fixtures of the doctor's `ambiente`, assigned (not imported under their own name) so pytest finds them here
caixa = _caixa.caixa
ambiente = _ambiente_do_doctor

FIX_SETUP = "simplicio-video video-to-skill setup"
UPSTREAM_VU = "pin: o setup.sh fixa o commit (VU_REF) e o upstream não é seguido"
UPSTREAM_VTS = "pin: o binário (sha256 por plataforma) e o SKILL.md são fixados juntos e o upstream não é seguido"
DOCTOR = SRC / "doctor_trilhas.py"
TOOLS_PY = SRC / "tools.py"
V2S_PY = SRC / "video_to_skill.py"


# --- helpers: the managed binary of video-to-skill -----------------------------------------------------------------------------


def _fixa_plataforma(monkeypatch, plataforma, sha: str) -> None:
    """This machine is `plataforma` for the engine and the pinned `member_sha256` of its asset is `sha` (the other pins stay)."""
    monkeypatch.setattr(v2s, "_platform", lambda: plataforma)
    asset = next(a for a in v2s.PINS["assets"] if a["platform"] == "linux-x86_64")
    monkeypatch.setattr(v2s, "PINS", {**v2s.PINS, "assets": [{**asset, "member_sha256": sha}]})


def _gerenciado(monkeypatch, conteudo: bytes = b"binario falso\n", *, sha: str | None = None, plataforma=("Linux", "x86_64")) -> Path:
    """The managed binary written at `managed_binary()`, pinned (for `plataforma`) at `sha` (default: the sha256 of the very bytes)."""
    exe = v2s.managed_binary()
    exe.parent.mkdir(parents=True, exist_ok=True)
    exe.write_bytes(conteudo)
    _fixa_plataforma(monkeypatch, plataforma, sha or hashlib.sha256(conteudo).hexdigest())
    return exe


def _sem_vts_no_path(ambiente) -> None:
    (ambiente.caixa.bin / "vts-extract").unlink()


def _linha_binario() -> dict:
    return _c(_trilha(dt.collect(), "video_to_skill"), "setup:binary")


def _linha(status: str, summary: str, fix, detail: dict) -> dict:
    return {"name": "setup:binary", "status": status, "summary": summary, "fix": fix, "detail": detail}


def _script_que_diz_a_versao(caminho: Path, marca: Path | None = None) -> None:
    """An extractor that says `vts-extract 0.3.0`; with `marca`, it also writes that file when it is RUN (nobody may run it here)."""
    toque = f"touch '{marca}'\n" if marca else ""
    caminho.write_text(f"#!/bin/sh\n{toque}echo 'vts-extract 0.3.0'\n", encoding="utf-8")
    caminho.chmod(0o755)


# --- 1. caracterização: a linha `setup:binary` do doctor para o video-to-skill ---------------------------------------------


def test_binario_gerenciado_conferido_fica_ok_e_diz_a_origem(ambiente, monkeypatch):
    monta_saudavel(ambiente, monkeypatch)
    _sem_vts_no_path(ambiente)
    exe = _gerenciado(monkeypatch)
    assert _linha_binario() == _linha("ok", f"vts-extract {v2s.VERSION} gerenciado, sha256 conferido ({exe})", None,
                                      {"source": "managed", "path": str(exe), "version": v2s.VERSION})


def test_binario_gerenciado_com_sha_errado_falha_e_manda_o_setup(ambiente, monkeypatch):
    monta_saudavel(ambiente, monkeypatch)
    _sem_vts_no_path(ambiente)
    exe = _gerenciado(monkeypatch, sha="0" * 64)
    assert _linha_binario() == _linha(
        "fail", f"{exe} não confere com o sha256 fixado (alterado, link ou outra plataforma): o motor não o usa", FIX_SETUP,
        {"source": "managed", "path": str(exe)})


@posix_real
def test_binario_gerenciado_que_e_link_falha_mesmo_com_o_sha_do_alvo_certo(ambiente, monkeypatch):
    monta_saudavel(ambiente, monkeypatch)
    _sem_vts_no_path(ambiente)
    alvo = ambiente.caixa.tmp / "alvo-do-link"
    alvo.write_bytes(b"os bytes fixados\n")
    exe = v2s.managed_binary()
    exe.parent.mkdir(parents=True, exist_ok=True)
    exe.symlink_to(alvo)
    _fixa_plataforma(monkeypatch, ("Linux", "x86_64"), hashlib.sha256(alvo.read_bytes()).hexdigest())  # the target IS the pinned file
    assert _linha_binario() == _linha(
        "fail", f"{exe} não confere com o sha256 fixado (alterado, link ou outra plataforma): o motor não o usa", FIX_SETUP,
        {"source": "managed", "path": str(exe)})


@posix_real
def test_binario_gerenciado_que_e_link_quebrado_falha(ambiente, monkeypatch):
    monta_saudavel(ambiente, monkeypatch)
    _sem_vts_no_path(ambiente)
    exe = v2s.managed_binary()
    exe.parent.mkdir(parents=True, exist_ok=True)
    exe.symlink_to(ambiente.caixa.tmp / "nao-existe")
    _fixa_plataforma(monkeypatch, ("Linux", "x86_64"), "0" * 64)
    linha = _linha_binario()
    assert linha["status"] == "fail" and linha["fix"] == FIX_SETUP and linha["detail"] == {"source": "managed", "path": str(exe)}


def test_binario_gerenciado_numa_plataforma_sem_binario_prefabricado_falha(ambiente, monkeypatch):
    """A file sits at the managed path, but this platform has no pinned asset: nothing it could match, so the engine does not use it."""
    monta_saudavel(ambiente, monkeypatch)
    _sem_vts_no_path(ambiente)
    exe = _gerenciado(monkeypatch, plataforma=("Linux", "aarch64"))
    assert _linha_binario() == _linha(
        "fail", f"{exe} não confere com o sha256 fixado (alterado, link ou outra plataforma): o motor não o usa", FIX_SETUP,
        {"source": "managed", "path": str(exe)})


def test_binario_gerenciado_adulterado_nao_cai_no_do_path(ambiente, monkeypatch):
    """A managed file that does not match is `fail` even when a good `vts-extract` is on the PATH: the doctor does not look past it."""
    monta_saudavel(ambiente, monkeypatch)  # leaves a `vts-extract 0.3.0` on the PATH
    exe = _gerenciado(monkeypatch, sha="0" * 64)
    linha = _linha_binario()
    assert linha["status"] == "fail" and linha["detail"] == {"source": "managed", "path": str(exe)}


def test_binario_gerenciado_conferido_vale_mais_que_o_do_path(ambiente, monkeypatch):
    monta_saudavel(ambiente, monkeypatch)
    _gerenciado(monkeypatch)
    linha = _linha_binario()
    assert linha["status"] == "ok" and linha["detail"]["source"] == "managed"


def test_sem_binario_gerenciado_o_do_path_na_versao_certa_fica_ok_sem_sha(ambiente, monkeypatch):
    monta_saudavel(ambiente, monkeypatch)
    achado = str(ambiente.caixa.bin / "vts-extract")
    assert _linha_binario() == _linha(
        "ok", f"vts-extract {v2s.VERSION} no PATH ({achado}); só a versão foi conferida, não o sha256", None,
        {"source": "path", "path": achado, "version": v2s.VERSION})


def test_sem_binario_gerenciado_o_do_path_em_outra_versao_avisa(ambiente, monkeypatch):
    monta_saudavel(ambiente, monkeypatch)
    write_fake_tool(ambiente.caixa.bin, "vts-extract", "vts-extract 0.2.9\n")
    achado = str(ambiente.caixa.bin / "vts-extract")
    assert _linha_binario() == _linha(
        "warn", f"o vts-extract do PATH ({achado}) não diz {v2s.VERSION}: o motor não o usa", FIX_SETUP,
        {"source": "path", "path": achado, "version": "0.2.9"})


def test_sem_nenhum_binario_avisa_com_o_comando_do_setup(ambiente, monkeypatch):
    monta_saudavel(ambiente, monkeypatch)
    _sem_vts_no_path(ambiente)
    exe = v2s.managed_binary()
    assert _linha_binario() == _linha("warn", f"vts-extract {v2s.VERSION} ausente; o setup baixa e confere por sha256", FIX_SETUP,
                                      {"path": str(exe)})


def test_sem_binario_numa_plataforma_sem_binario_prefabricado_diz_para_compilar(ambiente, monkeypatch):
    monta_saudavel(ambiente, monkeypatch)
    _sem_vts_no_path(ambiente)
    monkeypatch.setattr(v2s, "_platform", lambda: ("Linux", "aarch64"))
    assert _linha_binario() == _linha(
        "warn", "sem binário pré-compilado para esta plataforma: compile o vts-extract do upstream e ponha no PATH", None,
        {"supported": False})


def test_o_doctor_nao_roda_o_binario_gerenciado(ambiente, monkeypatch):
    """The managed binary is judged by its bytes: a file that would leave a mark when run is hashed, never started."""
    monta_saudavel(ambiente, monkeypatch)
    _sem_vts_no_path(ambiente)
    marca = ambiente.caixa.tmp / "RODOU"
    exe = v2s.managed_binary()
    exe.parent.mkdir(parents=True, exist_ok=True)
    _script_que_diz_a_versao(exe, marca)
    _fixa_plataforma(monkeypatch, ("Linux", "x86_64"), hashlib.sha256(exe.read_bytes()).hexdigest())
    assert _linha_binario()["status"] == "ok" and not marca.exists()


# --- 1b. caracterização: o hypit por npx e a trilha npm que não corre por npx ---------------------------------------------------


def _node(ambiente, versao: str) -> None:
    write_fake_tool(ambiente.caixa.bin, "node", f"v{versao}\n")


def _hypit() -> dict:
    return _trilha(dt.collect(), "hypit")


def test_hypit_sem_binario_corre_por_npx_com_node_22_15_ou_mais(ambiente):
    _node(ambiente, "22.15.0")
    track = _hypit()
    pin = tools.get("hypit").ref
    assert track["installed"] is True and track["version"] is None and track["pin_match"] is True
    assert _c(track, "instalada") == {"name": "instalada", "status": "ok", "fix": None, "detail": {"source": "npx"},
                                      "summary": "instalada via npx no pin em uso (sem binário no PATH)"}
    assert _c(track, "pin")["summary"] == f"rodado por npx no pin {pin} (pin)"
    assert [c["name"] for c in track["checks"]] == ["instalada", "pin", "dep:node", "dep:npx"]
    assert _c(track, "dep:npx")["status"] == "ok" and _c(track, "dep:npx")["summary"] == "npx encontrado"
    assert tools.install_source(tools.get("hypit")) == "npx" and tools.is_installed(tools.get("hypit")) is True


def test_hypit_com_node_antigo_nao_corre_por_npx_e_avisa(ambiente):
    _node(ambiente, "22.14.9")
    track = _hypit()
    assert track["installed"] is False and track["status"] == "warn"
    assert _c(track, "instalada")["summary"] == "não instalada"
    assert _c(track, "instalada")["fix"] == f"npm install -g @hypit/hypit@{tools.get('hypit').ref}"
    assert _c(track, "dep:node")["status"] == "warn" and _c(track, "dep:npx")["status"] == "ok"
    assert tools.install_source(tools.get("hypit")) is None and tools.is_installed(tools.get("hypit")) is False


def test_hypit_sem_npx_avisa_e_a_linha_do_npx_cobra_o_node_certo(ambiente):
    _node(ambiente, "24.1.0")
    (ambiente.caixa.bin / "npx").unlink()
    track = _hypit()
    assert track["installed"] is False and _c(track, "instalada")["summary"] == "não instalada"
    linha = _c(track, "dep:npx")
    assert linha["status"] == "warn" and linha["summary"] == "npx ausente"
    assert linha["fix"] == "instale o Node 22.15 ou superior, que traz o npx"
    assert tools.install_source(tools.get("hypit")) is None


def test_hypit_com_binario_no_path_nao_tem_a_linha_do_npx(ambiente):
    _node(ambiente, "24.1.0")
    write_fake_tool(ambiente.caixa.bin, "hypit", f"{tools.get('hypit').ref}\n")
    track = _hypit()
    assert track["installed"] is True and track["version"] == tools.get("hypit").ref
    assert [c["name"] for c in track["checks"]] == ["instalada", "pin", "dep:node"]
    assert tools.install_source(tools.get("hypit")) == "path"


def test_hypit_com_binario_que_nao_roda_falha_e_nao_tem_a_linha_do_npx(ambiente):
    _node(ambiente, "24.1.0")
    write_fake_tool(ambiente.caixa.bin, "hypit", "", rc=1)
    track = _hypit()
    assert track["installed"] is False and _c(track, "instalada")["status"] == "fail"
    assert "dep:npx" not in [c["name"] for c in track["checks"]]


def test_tinyfish_sem_binario_nao_corre_por_npx_e_nao_tem_a_linha_do_npx(ambiente):
    """The other npm track needs a binary: node 24 and npx are there and it is still `não instalada`."""
    _node(ambiente, "24.1.0")
    track = _trilha(dt.collect(), "tinyfish")
    assert track["installed"] is False and _c(track, "instalada")["summary"] == "não instalada"
    assert [c["name"] for c in track["checks"]] == ["instalada", "dep:node", "dep:npm"]
    assert tools.install_source(tools.get("tinyfish")) is None and tools.is_installed(tools.get("tinyfish")) is False


# --- 1c. caracterização: o texto do upstream das duas trilhas pin-only -------------------------------------------------------


@pytest.mark.parametrize("nome, texto", [("video-use", UPSTREAM_VU), ("video_to_skill", UPSTREAM_VTS)])
def test_o_upstream_das_trilhas_pin_only_diz_o_que_dizia(ambiente, monkeypatch, nome, texto):
    monta_saudavel(ambiente, monkeypatch)
    rede = _rede_em_dia()
    linha = _c(_trilha(dt.collect(online=True, io=rede.io()), nome), "upstream")
    assert linha == {"name": "upstream", "status": "ok", "summary": texto, "fix": None, "detail": {"pin_only": True}}
    assert tools.get(nome).source not in rede.consultados()


def test_so_o_video_use_tem_checkout_env_hoje():
    """What S6 reads: the one pin-only track that keeps a checkout outside the tools cache is video-use (the other is video_to_skill)."""
    assert {n for n, t in tools.TOOLS.items() if t.pin_only} == {"video-use", "video_to_skill"}
    assert {n for n, t in tools.TOOLS.items() if t.checkout_env} == {"video-use"}


# --- 1d. caracterização: o `doctor trilhas --json` inteiro nesses estados (sha256 do texto normalizado) --------------------------

GOLDEN = {
    "vts-gerenciado-conferido": "ce8ef4c0bea30013b6c190c75125bb82516d1c8f30accc6299d01a55b930f079",
    "vts-gerenciado-adulterado": "b4d2f4566c528e3d44d393f20093c6fb24dbf6da7b04eb838edeab5b807af2d9",
    "vts-gerenciado-link": "b4d2f4566c528e3d44d393f20093c6fb24dbf6da7b04eb838edeab5b807af2d9",
    "vts-sem-binario-nesta-plataforma": "e2d00150d4b8959e281532adae378842c7f8aa88b1b3bb13631d0352562145d6",
    "hypit-npx-node-22.15": "b9edf3ff087f4bdbce4a2a10dbeb4a7e4cedcf0408fb7330a9e3dad39cc69014",
    "hypit-node-antigo": "3b9a9f3906334e8d46ba3a094dca595110a650c203829fa871bf8e37aa46c542",
    "hypit-sem-npx": "9165ec3828daeb00289ea2583e4977849628798a2653a706ef49721c8e3dd4a6",
    "hypit-binario-no-path": "36b9644189f6813e32bcb1e16e592230ec24f601730f50507a45376c238d3c97",
}


def _confere(nome: str, ambiente) -> None:
    doc = dt.collect()
    texto = json.dumps({"doc": doc, "linha_do_doctor": dt.linha_do_doctor(doc)}, indent=1, ensure_ascii=False)
    texto = _normaliza(texto, ambiente.caixa.tmp)
    achado = hashlib.sha256(texto.encode("utf-8")).hexdigest()
    pasta = os.environ.get("REGISTRO_V2_DUMP")
    if pasta:  # capture mode: writes the normalized text and does not check (to compare two versions of the code)
        alvo = Path(pasta) / (nome + ".txt")
        alvo.parent.mkdir(parents=True, exist_ok=True)
        alvo.write_text(texto, encoding="utf-8")
        return
    assert achado == GOLDEN[nome], f"{nome}: o doctor mudou (sha256 {achado}); o de origin/main é {GOLDEN[nome]}"


def test_o_doctor_inteiro_com_o_binario_gerenciado_conferido(ambiente, monkeypatch):
    monta_saudavel(ambiente, monkeypatch)
    _sem_vts_no_path(ambiente)
    _gerenciado(monkeypatch)
    _confere("vts-gerenciado-conferido", ambiente)


def test_o_doctor_inteiro_com_o_binario_gerenciado_adulterado(ambiente, monkeypatch):
    monta_saudavel(ambiente, monkeypatch)
    _sem_vts_no_path(ambiente)
    _gerenciado(monkeypatch, sha="0" * 64)
    _confere("vts-gerenciado-adulterado", ambiente)


@posix_real
def test_o_doctor_inteiro_com_o_binario_gerenciado_em_link(ambiente, monkeypatch):
    monta_saudavel(ambiente, monkeypatch)
    _sem_vts_no_path(ambiente)
    alvo = ambiente.caixa.tmp / "alvo-do-link"
    alvo.write_bytes(b"os bytes fixados\n")
    exe = v2s.managed_binary()
    exe.parent.mkdir(parents=True, exist_ok=True)
    exe.symlink_to(alvo)
    _fixa_plataforma(monkeypatch, ("Linux", "x86_64"), hashlib.sha256(alvo.read_bytes()).hexdigest())
    _confere("vts-gerenciado-link", ambiente)


def test_o_doctor_inteiro_numa_plataforma_sem_binario_prefabricado(ambiente, monkeypatch):
    monta_saudavel(ambiente, monkeypatch)
    _sem_vts_no_path(ambiente)
    monkeypatch.setattr(v2s, "_platform", lambda: ("Linux", "aarch64"))
    _confere("vts-sem-binario-nesta-plataforma", ambiente)


def test_o_doctor_inteiro_com_o_hypit_por_npx(ambiente, monkeypatch):
    monta_saudavel(ambiente, monkeypatch)
    _node(ambiente, "22.15.0")
    _confere("hypit-npx-node-22.15", ambiente)


def test_o_doctor_inteiro_com_node_antigo(ambiente, monkeypatch):
    monta_saudavel(ambiente, monkeypatch)
    _node(ambiente, "20.11.0")
    _confere("hypit-node-antigo", ambiente)


def test_o_doctor_inteiro_sem_npx(ambiente, monkeypatch):
    monta_saudavel(ambiente, monkeypatch)
    (ambiente.caixa.bin / "npx").unlink()
    _confere("hypit-sem-npx", ambiente)


def test_o_doctor_inteiro_com_o_hypit_no_path(ambiente, monkeypatch):
    monta_saudavel(ambiente, monkeypatch)
    write_fake_tool(ambiente.caixa.bin, "hypit", f"{tools.get('hypit').ref}\n")
    _confere("hypit-binario-no-path", ambiente)


# --- 2a. H3: `managed_verified` é a única implementação do predicado -------------------------------------------------------------


def test_managed_verified_existe_e_nao_precisa_de_argumento():
    assert callable(v2s.managed_verified)
    parametros = inspect.signature(v2s.managed_verified).parameters
    assert list(parametros) == ["exe"] and parametros["exe"].default is None


def test_managed_verified_sem_argumento_olha_o_binario_gerenciado(ambiente, monkeypatch):
    assert v2s.managed_verified() is False  # nothing there yet
    _gerenciado(monkeypatch)
    assert v2s.managed_verified() is True


def test_managed_verified_sem_argumento_segue_managed_binary_na_hora_da_chamada(ambiente, monkeypatch, tmp_path):
    outro = tmp_path / "outro-lugar"
    outro.write_bytes(b"outros bytes\n")
    _fixa_plataforma(monkeypatch, ("Linux", "x86_64"), hashlib.sha256(outro.read_bytes()).hexdigest())
    assert v2s.managed_verified() is False
    monkeypatch.setattr(v2s, "managed_binary", lambda: outro)
    assert v2s.managed_verified() is True


def test_managed_verified_com_argumento_confere_aquele_arquivo(ambiente, monkeypatch, tmp_path):
    arquivo = tmp_path / "um-arquivo"
    arquivo.write_bytes(b"bytes fixados\n")
    _fixa_plataforma(monkeypatch, ("Linux", "x86_64"), hashlib.sha256(arquivo.read_bytes()).hexdigest())
    assert v2s.managed_verified(arquivo) is True
    assert v2s.managed_verified(v2s.managed_binary()) is False  # the managed path holds nothing
    arquivo.write_bytes(b"outros bytes\n")
    assert v2s.managed_verified(arquivo) is False


def test_managed_verified_recusa_sha_errado_arquivo_ausente_e_pasta(ambiente, monkeypatch, tmp_path):
    exe = _gerenciado(monkeypatch, sha="0" * 64)
    assert v2s.managed_verified(exe) is False
    assert v2s.managed_verified(tmp_path / "nao-existe") is False
    assert v2s.managed_verified(tmp_path) is False  # a folder is no file


@posix_real
def test_managed_verified_recusa_link_mesmo_com_o_sha_do_alvo_certo(ambiente, monkeypatch, tmp_path):
    alvo = tmp_path / "alvo"
    alvo.write_bytes(b"bytes fixados\n")
    link = tmp_path / "link"
    link.symlink_to(alvo)
    _fixa_plataforma(monkeypatch, ("Linux", "x86_64"), hashlib.sha256(alvo.read_bytes()).hexdigest())
    assert v2s.managed_verified(alvo) is True
    assert v2s.managed_verified(link) is False
    link.unlink()
    link.symlink_to(tmp_path / "nao-existe")
    assert v2s.managed_verified(link) is False


def test_managed_verified_numa_plataforma_sem_binario_prefabricado_e_falso(ambiente, monkeypatch):
    exe = _gerenciado(monkeypatch, plataforma=("Linux", "aarch64"))
    assert v2s.managed_verified(exe) is False


def test_managed_verified_nao_roda_processo(ambiente, monkeypatch, tmp_path):
    marca = tmp_path / "RODOU"
    exe = v2s.managed_binary()
    exe.parent.mkdir(parents=True, exist_ok=True)
    _script_que_diz_a_versao(exe, marca)
    _fixa_plataforma(monkeypatch, ("Linux", "x86_64"), hashlib.sha256(exe.read_bytes()).hexdigest())

    def proibido(*a, **k):
        raise AssertionError("managed_verified não pode iniciar um processo")

    monkeypatch.setattr(childio, "guarded_child", proibido)
    monkeypatch.setattr(v2s, "_spawn", proibido)
    assert v2s.managed_verified() is True and v2s.managed_verified(exe) is True and not marca.exists()


def test_o_doctor_e_o_find_binary_obedecem_ao_mesmo_managed_verified(ambiente, monkeypatch):
    """Two doors, one answer: replacing `managed_verified` (the only implementation) decides both, so neither repeats the predicate."""
    monta_saudavel(ambiente, monkeypatch)
    _sem_vts_no_path(ambiente)
    exe = v2s.managed_binary()
    exe.parent.mkdir(parents=True, exist_ok=True)
    _script_que_diz_a_versao(exe)  # it runs and says 0.3.0, but its sha256 is NOT the pinned one
    _fixa_plataforma(monkeypatch, ("Linux", "x86_64"), "0" * 64)

    assert _linha_binario()["status"] == "fail" and v2s.find_binary() is None
    monkeypatch.setattr(v2s, "managed_verified", lambda exe=None: True)
    assert _linha_binario()["status"] == "ok" and _linha_binario()["detail"]["source"] == "managed"
    achado = v2s.find_binary()
    assert achado is not None and (achado.path, achado.source, achado.verified, achado.version) == (exe, "managed", "sha256", v2s.VERSION)

    monkeypatch.setattr(v2s, "managed_verified", lambda exe=None: False)
    assert _linha_binario()["status"] == "fail" and v2s.find_binary() is None


def _funcoes_com_o_predicado() -> list:
    """Every function of the package that checks `.is_symlink()` AND reads a `["member_sha256"]`: the "managed and verified" predicate."""
    achadas = []
    for arquivo in sorted(SRC.rglob("*.py")):
        achadas += [f"{arquivo.relative_to(SRC).as_posix()}:{f.name}" for f in _funcoes(arquivo.read_text(encoding="utf-8"))
                    if _faz_o_predicado(f)]
    return achadas


def _funcoes(fonte: str) -> list:
    return [n for n in ast.walk(ast.parse(fonte)) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]


def _faz_o_predicado(funcao) -> bool:
    chamadas = {n.func.attr for n in ast.walk(funcao) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
    chaves = {n.slice.value for n in ast.walk(funcao) if isinstance(n, ast.Subscript) and isinstance(n.slice, ast.Constant)}
    return "is_symlink" in chamadas and "member_sha256" in chaves


def test_o_detector_do_predicado_pega_a_copia_e_nao_pega_o_resto():
    copia = "def f(exe, asset):\n    return not exe.is_symlink() and h(exe) == asset['member_sha256']\n"
    so_o_link = "def g(exe):\n    return exe.is_symlink()\n"
    so_o_sha = "def h(asset):\n    return asset['member_sha256']\n"
    assert [f.name for f in _funcoes(copia + so_o_link + so_o_sha) if _faz_o_predicado(f)] == ["f"]


def test_so_managed_verified_implementa_o_predicado_do_binario_gerenciado():
    assert _funcoes_com_o_predicado() == ["video_to_skill.py:managed_verified"]


def _chama(fonte: str, funcao: str, nome: str) -> bool:
    """Does `funcao` call something named `nome` (`nome(...)` or `modulo.nome(...)`)?"""
    corpo = next(f for f in _funcoes(fonte) if f.name == funcao)
    return any(isinstance(n, ast.Call) and ((isinstance(n.func, ast.Name) and n.func.id == nome)
                                            or (isinstance(n.func, ast.Attribute) and n.func.attr == nome)) for n in ast.walk(corpo))


def test_find_binary_e_o_doctor_chamam_managed_verified():
    assert _chama(V2S_PY.read_text(encoding="utf-8"), "find_binary", "managed_verified")
    assert _chama(DOCTOR.read_text(encoding="utf-8"), "_binary_row", "managed_verified")


def _privados_de_outros_modulos(fonte: str) -> list:
    """`modulo._nome` for every module of the package imported by `from . import modulo [as alias]`, and `from .modulo import _nome`."""
    arvore = ast.parse(fonte)
    aliases, achados = set(), []
    for n in ast.walk(arvore):
        if isinstance(n, ast.ImportFrom) and n.level == 1 and n.module is None:
            aliases |= {a.asname or a.name for a in n.names}
        elif isinstance(n, ast.ImportFrom) and n.level == 1:
            achados += [f"from .{n.module} import {a.name}" for a in n.names if a.name.startswith("_") and not a.name.startswith("__")]
    for n in ast.walk(arvore):
        if (isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id in aliases
                and n.attr.startswith("_") and not n.attr.startswith("__")):
            achados.append(f"{n.value.id}.{n.attr}")
    return sorted(achados)


def test_o_detector_de_privado_pega_os_dois_jeitos_e_ignora_dunder_e_publico():
    fonte = ("from . import a, b as c\nfrom .d import _x, y\n\ndef f():\n    from . import e as g\n"
             "    return a._p, c.q, g._r, a.__name__, c.__doc__, d._z\n")
    assert _privados_de_outros_modulos(fonte) == ["a._p", "from .d import _x", "g._r"]


def test_o_doctor_nao_usa_nome_privado_de_outro_modulo():
    assert _privados_de_outros_modulos(DOCTOR.read_text(encoding="utf-8")) == []


# --- 2b. S3: `Tool.npx` -----------------------------------------------------------------------------------------------------


def test_tool_tem_o_campo_npx_e_so_o_hypit_o_declara():
    campos = {f.name: f for f in dataclasses.fields(tools.Tool)}
    assert "npx" in campos, "Tool não tem o campo npx"
    assert campos["npx"].default is False
    assert {n for n, t in tools.TOOLS.items() if t.npx is True} == {"hypit"}
    assert all(t.npx is False for n, t in tools.TOOLS.items() if n != "hypit")


def test_npx_tracks_nao_existe_mais():
    assert not hasattr(tools, "NPX_TRACKS")
    for pasta in (SRC, ROOT / "scripts"):
        for arquivo in sorted(pasta.rglob("*.py")):
            assert "NPX_TRACKS" not in arquivo.read_text(encoding="utf-8"), f"{arquivo} ainda lê NPX_TRACKS"


def test_o_registro_decide_quem_corre_por_npx_e_nao_o_nome(ambiente, monkeypatch):
    """Swap the field between the two npm tracks: the doctor and `install_source` follow the field, whatever the names."""
    _node(ambiente, "24.1.0")
    monkeypatch.setitem(tools.TOOLS, "hypit", dataclasses.replace(tools.TOOLS["hypit"], npx=False))
    monkeypatch.setitem(tools.TOOLS, "tinyfish", dataclasses.replace(tools.TOOLS["tinyfish"], npx=True))
    doc = dt.collect()
    hypit, tinyfish = _trilha(doc, "hypit"), _trilha(doc, "tinyfish")
    assert hypit["installed"] is False and _c(hypit, "instalada")["summary"] == "não instalada"
    assert "dep:npx" not in [c["name"] for c in hypit["checks"]]
    assert tinyfish["installed"] is True and _c(tinyfish, "instalada")["detail"] == {"source": "npx"}
    assert _c(tinyfish, "dep:npx")["status"] == "ok"
    assert tools.install_source(tools.get("hypit")) is None and tools.install_source(tools.get("tinyfish")) == "npx"


# --- 2c. S3 e S6: nenhum nome de trilha literal no doctor -------------------------------------------------------------------


def _nomes_de_trilha_no_doctor(fonte: str, trilhas) -> list:
    """The lines that compare a `.name` with the name of a track written as a literal (`t.name == "x"`, `t.name in ("x", "y")`) or
    with a table called `*_TRACKS`. `os.name == "nt"` is not one: "nt" is no track."""
    achados = []
    for n in ast.walk(ast.parse(fonte)):
        if not isinstance(n, ast.Compare):
            continue
        lados = [n.left, *n.comparators]
        if not any(isinstance(x, ast.Attribute) and x.attr == "name" for x in lados):
            continue
        for x in lados:
            literais = [x] if isinstance(x, ast.Constant) else list(x.elts) if isinstance(x, (ast.Tuple, ast.List, ast.Set)) else []
            nomeia = any(isinstance(e, ast.Constant) and e.value in trilhas for e in literais)
            tabela = (isinstance(x, ast.Attribute) and x.attr.endswith("_TRACKS")) or (isinstance(x, ast.Name) and x.id.endswith("_TRACKS"))
            if nomeia or tabela:
                achados.append(n.lineno)
    return sorted(set(achados))


def test_o_detector_de_nome_de_trilha_pega_os_tres_jeitos():
    fonte = ("def f(t, x):\n    a = t.name == 'video_to_skill'\n    b = t.name in ('hypit', 'x')\n    c = t.name in tools.NPX_TRACKS\n"
             "    d = t.name == x.name\n    e = row['name'] == 'pin'\n    g = os.name == 'nt'\n    return a, b, c, d, e, g\n")
    assert _nomes_de_trilha_no_doctor(fonte, {"video_to_skill", "hypit"}) == [2, 3, 4]


def test_o_doctor_nao_compara_o_nome_da_trilha_com_um_literal():
    assert _nomes_de_trilha_no_doctor(DOCTOR.read_text(encoding="utf-8"), set(tools.TOOLS)) == []


def test_o_texto_do_upstream_pin_only_segue_o_checkout_env_e_nao_o_nome(ambiente):
    """S6: the text is chosen by what the registry says of the track. Give video_to_skill a `checkout_env` and take it from video-use."""
    vts = dataclasses.replace(tools.TOOLS["video_to_skill"], checkout_env="OUTRA_PASTA")
    vu = dataclasses.replace(tools.TOOLS["video-use"], checkout_env=None)
    assert dt._upstream(vts, vts.ref, "pin", None)[1][0]["summary"] == UPSTREAM_VU
    assert dt._upstream(vu, vu.ref, "pin", None)[1][0]["summary"] == UPSTREAM_VTS
    # and the two real tracks, unchanged
    assert dt._upstream(tools.TOOLS["video-use"], tools.TOOLS["video-use"].ref, "pin", None)[1][0]["summary"] == UPSTREAM_VU
    assert dt._upstream(tools.TOOLS["video_to_skill"], tools.TOOLS["video_to_skill"].ref, "pin", None)[1][0]["summary"] == UPSTREAM_VTS
