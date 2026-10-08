"""Contrato estático do Dockerfile e do compose.yaml (issue #43). Nenhum `docker build` roda aqui.

Multi-stage, USER não root na imagem final, HEALTHCHECK, nenhuma tag `latest`, nenhum segredo em ARG/ENV,
compose que builda a partir do Dockerfile (sem imagem pública) e monta volume para o workspace.
"""
from __future__ import annotations

import re

import pytest
import yaml

from _comum import ROOT

DOCKERFILE = ROOT / "Dockerfile"
COMPOSE = ROOT / "compose.yaml"


def _instrucoes(texto: str) -> list[tuple[str, str]]:
    """(OPCODE, argumentos) de cada instrução, com linhas de continuação (\\) juntas e comentários fora."""
    out: list[tuple[str, str]] = []
    buf = ""
    for linha in texto.splitlines():
        s = linha.strip()
        if not buf and (not s or s.startswith("#")):
            continue
        if s.endswith("\\"):
            buf += s[:-1] + " "
            continue
        buf += s
        partes = buf.split(None, 1)
        out.append((partes[0].upper(), partes[1] if len(partes) > 1 else ""))
        buf = ""
    return out


@pytest.fixture
def dockerfile():
    assert DOCKERFILE.is_file(), "Dockerfile não existe na raiz do repo"
    return _instrucoes(DOCKERFILE.read_text(encoding="utf8"))


@pytest.fixture
def compose():
    assert COMPOSE.is_file(), "compose.yaml não existe na raiz do repo"
    dados = yaml.safe_load(COMPOSE.read_text(encoding="utf8"))
    assert isinstance(dados, dict) and dados.get("services"), "compose.yaml sem services"
    return dados


def _imagem_do_from(args: str) -> str:
    return args.split()[0]


def test_dockerfile_multi_stage(dockerfile):
    froms = [a for op, a in dockerfile if op == "FROM"]
    assert len(froms) >= 2, "Dockerfile precisa ser multi-stage (pelo menos dois FROM)"
    assert any(re.search(r"\sAS\s", " " + a + " ", re.IGNORECASE) for a in froms), "stages sem nome (AS)"


def test_imagens_base_com_tag_fixa_e_nunca_latest(dockerfile):
    for op, args in dockerfile:
        if op != "FROM":
            continue
        imagem = _imagem_do_from(args)
        if imagem.lower() == "scratch":
            continue
        assert "@sha256:" in imagem or re.search(r":[^:/@]+$", imagem), f"FROM sem tag fixa: {imagem}"
        assert not imagem.lower().endswith(":latest"), f"FROM com tag latest: {imagem}"


def test_imagem_final_roda_como_usuario_nao_root(dockerfile):
    ultimo_from = max(i for i, (op, _) in enumerate(dockerfile) if op == "FROM")
    users = [(i, a.strip()) for i, (op, a) in enumerate(dockerfile) if op == "USER"]
    assert users, "Dockerfile sem USER"
    i, valor = users[-1]
    assert i > ultimo_from, "o USER tem que estar no stage final"
    usuario = valor.split(":")[0]
    assert usuario and usuario.lower() not in ("root", "0"), f"imagem final roda como {valor!r}"


def test_healthcheck_presente(dockerfile):
    hc = [a for op, a in dockerfile if op == "HEALTHCHECK"]
    assert hc, "Dockerfile sem HEALTHCHECK"
    assert not hc[-1].upper().startswith("NONE"), "HEALTHCHECK NONE desliga a checagem"
    assert "CMD" in hc[-1].upper(), "HEALTHCHECK precisa de CMD"


def test_nenhum_segredo_em_arg_ou_env(dockerfile):
    for op, args in dockerfile:
        if op not in ("ARG", "ENV"):
            continue
        for nome, _, valor in re.findall(r"([A-Za-z_][A-Za-z0-9_]*)(=)?(\S*)", args):
            if re.search(r"KEY|TOKEN|SECRET|PASSWORD|SENHA", nome, re.IGNORECASE):
                assert not valor, f"{op} {nome} grava um valor de credencial na imagem"


def test_compose_parseia_e_nao_usa_latest():
    assert COMPOSE.is_file(), "compose.yaml não existe na raiz do repo"
    texto = COMPOSE.read_text(encoding="utf8")
    assert not re.search(r"image:\s*\S+:latest\b", texto), "compose.yaml usa tag latest"
    yaml.safe_load(texto)


def test_compose_builda_a_partir_do_dockerfile(compose):
    for nome, servico in compose["services"].items():
        assert "build" in servico, f"serviço {nome} sem build: não publicamos imagem pronta (licença do ffmpeg)"


def test_compose_monta_volume_do_workspace(compose):
    for nome, servico in compose["services"].items():
        volumes = servico.get("volumes") or []
        assert volumes, f"serviço {nome} sem volume para o workspace"
