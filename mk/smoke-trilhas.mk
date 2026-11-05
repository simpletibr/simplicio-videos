# Trilha qa (smoke-trilhas): smoke só de leitura das trilhas externas e do núcleo (scripts/smoke_trilhas.py).
# `make smoke-trilhas` roda o CLI e o MCP de cada trilha contra o que está instalado nesta máquina. Fica fora de
# `make check` (depende do que está instalado) e não instala, não baixa e não gasta.

.PHONY: smoke-trilhas

smoke-trilhas:
	@$(PY) scripts/smoke_trilhas.py
