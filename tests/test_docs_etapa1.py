"""Documentação da etapa 1 do BRASA (critério E): a skill e a referência da CLI dizem o que o motor faz agora.

O espelho skills/ x src/.../data/skills/ já é conferido em tests/packaging/test_skills_empacotadas.py; aqui só se checa
o conteúdo novo. docs/reference/cli.md é gerado (make docs-regen) e é conferido pelo gate (gen_reference --check).
"""
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "src" / "simplicio_video" / "data" / "skills" / "simplicio-video" / "SKILL.md"
CLI_REF = ROOT / "docs" / "reference" / "cli.md"


@pytest.mark.parametrize("termo", ["qualidade: master", "qualidade: lite", "qualidade: thumb", "cortes", "passa_baixa_hz",
                                   "crossfade_ms", "ducking", "graves_db", "agudos_db", "qc congelado"])
def test_skill_do_simplicio_video_descreve_a_etapa_1(termo):
    assert termo in SKILL.read_text(encoding="utf8")


def test_referencia_da_cli_traz_o_qc_congelado():
    txt = CLI_REF.read_text(encoding="utf8")
    assert "qc congelado" in txt
    assert "--min-s" in txt
