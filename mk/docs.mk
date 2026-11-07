# Trilha docs (#44). `make docs` entra em `make check`: links, âncoras, front matter, órfãos, TODO e mermaid
# (scripts/check_docs.py), a referência gerada e os blocos GENERATED em dia (gen_reference.py --check) e o espelho skills/ e o bloco
# `GENERATED skills` do .gitignore em dia com src/simplicio_video/data/skills/ (sync_skills.py --check).
# `make docs-regen` regrava docs/reference/, os blocos do README.md e do AGENTS.md, o espelho skills/ e o bloco do .gitignore;
# também roda em `make regen`.

CHECKS += docs
REGEN  += docs-regen

.PHONY: docs docs-regen

docs:
	@$(PY) scripts/check_docs.py
	@$(PY) scripts/gen_reference.py --out docs/reference --check
	@$(PY) scripts/sync_skills.py --check

docs-regen:
	@$(PY) scripts/gen_reference.py --out docs/reference --update-blocks
	@$(PY) scripts/sync_skills.py
