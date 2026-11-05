# Trilha e2e-real: roteiro de testes reais ponta a ponta com as chaves e os apps desta máquina (scripts/e2e_real.py).
# Fora de `make check`: sem E2E_ARGS="--sim-gastar" só mostra o plano e o custo estimado (não roda nada); com a flag
# roda o que o ambiente habilita, com teto e consentimento explícitos. Guia: docs/how-to/e2e-real.md.
#   make e2e-real                                   plano
#   make e2e-real E2E_ARGS="--sim-gastar"           roda de verdade

E2E_ARGS ?=

.PHONY: e2e-real

e2e-real:
	@$(PY) scripts/e2e_real.py $(E2E_ARGS)
