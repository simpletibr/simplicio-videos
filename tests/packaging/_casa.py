"""Fixture `casa` dos testes do pacote de operação (issue #43).

Nome de módulo próprio (não conftest.py): um tests/packaging/conftest.py sobrescreve o `conftest` da raiz de tests/,
de onde os outros testes importam helpers. Cada teste que usa `casa` importa a fixture explicitamente.
"""
from types import SimpleNamespace

import pytest


@pytest.fixture
def casa(tmp_path, monkeypatch):
    """HOME e workspace isolados. O workspace ainda não existe: cada teste decide o que criar."""
    home = tmp_path / "home"
    home.mkdir()
    workspace = tmp_path / "workspace"
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("SIMPLICIO_WORKSPACE", str(workspace))
    return SimpleNamespace(tmp=tmp_path, home=home, workspace=workspace)
