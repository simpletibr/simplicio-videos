# Trilha docs (#44). `make docs` entra em `make check`: links, âncoras, front matter, órfãos, TODO e mermaid
# (scripts/check_docs.py), e a referência gerada e os blocos GENERATED em dia (gen_reference.py --check).
# `make docs-regen` regrava docs/reference/ e os blocos do README.md e do AGENTS.md; também roda em `make regen`.

CHECKS += docs
REGEN  += docs-regen

.PHONY: docs docs-regen

docs:
	@$(PY) scripts/check_docs.py
	@$(PY) scripts/gen_reference.py --out docs/reference --check

docs-regen:
	@$(PY) scripts/gen_reference.py --out docs/reference --update-blocks
