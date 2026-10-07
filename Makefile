# Gate local do simplicio-videos (sem CI): docs/host/gate.md
#
#   make setup       cria o .venv, instala o extra `test` e liga os hooks
#   make check       o gate offline (< 60 s): ruff, shellcheck, testes sem slow/render/integration/ui, ownership e TDD
#   make check-full  check + testes render/integration/ui/slow (podem usar rede)
#   make check-web   checagens do workspace web
#   make hooks       core.hooksPath=.githooks (o pre-push roda `make check`)
#   make regen       regenera os arquivos gerados

SHELL   := /bin/bash
VENV    ?= .venv
PYTHON  ?= python3
PY      := $(if $(wildcard $(VENV)/bin/python),$(VENV)/bin/python,$(PYTHON))

# Pontos de extensão. Cada trilha acrescenta em mk/<trilha>.mk:
#   CHECKS     += meu-alvo   (roda em `make check`)
#   REGEN      += meu-alvo   (roda em `make regen`)
#   CHECKS_WEB += meu-alvo   (roda em `make check-web`)
CHECKS     := gate
REGEN      :=
CHECKS_WEB :=

-include mk/*.mk

.DEFAULT_GOAL := help
.PHONY: help setup check check-full check-web hooks regen gate

help:
	@grep '^#   make' Makefile

gate:
	@scripts/check.sh

check: $(CHECKS)

check-full: check
	@printf '\n==> testes render/integration/ui/slow (podem usar rede)\n'
	@$(PY) -m pytest -q -p no:cacheprovider -m "render or integration or ui or slow"

check-web: $(CHECKS_WEB)
	@if [ -z "$(strip $(CHECKS_WEB))" ]; then echo "check-web: o workspace web chega com a #34; nada para checar ainda."; fi

setup: hooks
	@test -x $(VENV)/bin/python || $(PYTHON) -m venv $(VENV)
	$(VENV)/bin/python -m pip install -q -e '.[test]'

hooks:
	git config core.hooksPath .githooks

regen: $(REGEN)
	@if [ -z "$(strip $(REGEN))" ]; then echo "regen: nada para regenerar ainda (REGEN vazio)."; fi
