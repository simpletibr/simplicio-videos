# Kernel da fábrica (#33): schema do item, gerado. Nunca editar o JSON à mão.
#   make factory-schema                          regrava schemas/factory/item.schema.json
#   make factory-schema FACTORY_SCHEMA_OUT=/tmp/x  grava em outro caminho (usado pelos testes)

FACTORY_SCHEMA_OUT ?= schemas/factory/item.schema.json

.PHONY: factory-schema
factory-schema:
	@$(PY) -m simplicio_factory.contracts.schema $(FACTORY_SCHEMA_OUT)

REGEN += factory-schema
