# Trilha licenças (#46). `make licenses` entra em `make check`; `make licenses-write` regera docs/licenses.md
# (também roda em `make regen`). Veja docs/host/licenses.md.

CHECKS += licenses
REGEN  += licenses-write

.PHONY: licenses licenses-write

licenses:
	@$(PY) scripts/licenses.py --check
	@$(PY) scripts/licenses.py --imports src scripts

licenses-write:
	@$(PY) scripts/licenses.py --write
