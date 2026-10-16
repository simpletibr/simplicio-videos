"""Auxiliares dos testes de fronteira do `social` (ainda sem implementação: cada função devolve o neutro)."""
from __future__ import annotations

PUBLICAR_FIXO: set[str] = set()
EXPOR_FIXO: set[str] = set()
SEQUENCIA_ESPERADA: dict = {"realoficial": {"modelo": [], "com_tiktok": [], "sem_tiktok": []},
                            "zernio": {"modelo": [], "com_tiktok": [], "sem_tiktok": []}}


def violacoes_de_codigo(src: str) -> list[str]:
    return []


def conferir_sequencia_completa(steps, provedor) -> None:
    return None


def sequencia_de_ids(steps, provedor) -> list[str]:
    return []
