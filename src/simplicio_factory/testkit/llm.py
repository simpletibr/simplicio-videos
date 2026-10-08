"""ForbiddenLLM: dublê de LLM que falha se for chamado. Prova que o caminho padrão não usa LLM."""

from __future__ import annotations


class ForbiddenLLM:
    def complete(self, request: dict) -> str:
        raise AssertionError("LLM chamado no caminho determinístico do kernel")
