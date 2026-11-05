---
title: Licenças das dependências
summary: Como o gate confere licenças (allowlist MIT, Apache-2.0, BSD, ISC, PSF, MPL-2.0), como adicionar uma exceção justificada, como regerar docs/licenses.md e o que ainda falta (web/).
commands: make licenses, make licenses-write, scripts/licenses.py, scripts/licenses.py --imports
issue: 46
last_verified: 2026-10-08
---

# Licenças das dependências

O produto é open source sob AGPL-3.0-or-later (ver `docs/legal/licenca.md`). O gate continua conservador: toda dependência que entra no ambiente precisa estar na allowlist ou nas exceções justificadas. Esta página diz o que o gate checa e como agir quando reprova. O script é `scripts/licenses.py`. A tabela gerada é `docs/licenses.md`.

## Como rodar

```bash
make licenses         # scan do .venv + docs/licenses.md em dia + import check em src/ e scripts/
make licenses-write   # regera docs/licenses.md (também roda em make regen)
scripts/licenses.py --help
```

`make licenses` faz parte de `make check`. Não usa rede nem sockets.

## O que é checado

1. **Scan das distribuições instaladas** (`importlib.metadata`), limitado ao fecho das dependências base e do extra `test` do produto (segue `Requires-Dist`): extras instalados por fora (mcp, local-tts), o pip e as dependências com marcador de ambiente (`python_version`, `python_full_version`, `sys_platform`, `platform_*`, `os_name`, `implementation_*`, como `typing-extensions; python_version < '3.13'`) não entram na **tabela** do `docs/licenses.md`, que assim é igual em qualquer Python e sistema. O **gate** (negadas, exceções e o check de import) não usa esse recorte: confere toda distribuição instalada, declarada ou não, inclusive essas. A licença sai, nesta ordem, de `License-Expression` (PEP 639), de `License` e dos classifiers `License ::`.
2. **Allowlist, no nível de arquivo:** MIT, Apache-2.0, BSD (todas as variantes), ISC, PSF-2.0 e MPL-2.0. Em `A OR B` basta uma opção permitida. Em `A AND B` todas precisam ser permitidas. Qualquer outra licença reprova, inclusive GPL, LGPL, AGPL, MIT-0 e licença ausente.
3. **Exceções** em `docs/licenses-exceptions.yaml`. Uma exceção vale só se tiver `package`, `license` (igual à licença declarada no metadado instalado), `justificativa` e `uso`. Faltando um desses campos, ou com licença diferente da declarada, o pacote reprova.
4. **`docs/licenses.md` em dia.** O arquivo é gerado a partir do scan. O gate reprova se ele estiver ausente, se faltar ou sobrar pacote, ou se a licença ou o status diferirem do scan. A coluna **Versão** é informativa: um patch de dependência sem pin não reprova o gate (ex.: um transitivo de `jsonschema`). Quem atualiza a tabela é `make licenses-write`. As ferramentas do extra `test` (pytest, pytest-socket, pytest-xdist, ruff, shellcheck-py) são fixadas com `==` no `pyproject.toml`, na versão que o doc registra, para que o lint e os testes não mudem sem um commit explícito.
5. **Import check** (`scripts/licenses.py --imports src scripts`). Arquivos `.py` que importam um pacote negado, ou OpenMontage, VoiceStudio ou Postiz, reprovam. A checagem usa `ast`, não regex.
6. **Produto.** O próprio `simplicio-video` fica fora do scan. A tabela mostra a licença dele (`AGPL-3.0-or-later`).

## Como adicionar uma exceção

1. Leia a licença real do pacote (o `LICENSE` dentro do dist-info e o que ele baixa ou embute).
2. Acrescente uma entrada em `docs/licenses-exceptions.yaml`:

   ```yaml
   - package: nome-do-dist
     license: <exatamente a licença declarada no metadado instalado>
     justificativa: >-
       Por que aceitamos: quem é, onde roda, por que não é copyleft na prática.
     uso: somente desenvolvimento, não distribuído   # ou: runtime, permissiva (distribuível)
   ```

3. Rode `make licenses-write` e depois `make licenses`. Confira a linha nova em `docs/licenses.md`.

GPL, LGPL e AGPL nunca viram exceção de runtime. Se um deles aparecer como dependência de runtime, reprove e registre o caso na issue. Para GPL usada só em desenvolvimento, a exceção precisa de justificativa e de `uso` com `somente desenvolvimento, não distribuído`.

## Limites

- **web/ fora do escopo.** O workspace web (`web/package.json`) chega com a #34. Hoje `make licenses` só escaneia o Python e avisa que não há web/ a escanear.
- **Metadado errado ou ausente.** Alguns pacotes declaram a licença de forma incompleta. A exceção com justificativa é o controle. Não corrija o metadado do pacote no `.venv` à mão.
- **Dependências com licença divergente do binário.** O scan lê o metadado do wrapper. Um pacote que baixa um binário com outra licença só aparece pelo que a exceção documenta (exemplo: `shellcheck-py`).
- **Pinagem.** As dependências base e transitivas continuam sem pin exato; só o extra `test` é fixado. O lock de release (`constraints.txt`) fica na #50.
- **Pacote fora do fecho base + `test`.** Ele não entra em `docs/licenses.md`. Quem pega licença negada nele é só o check de negadas (o scan vivo de todos os extras), não a tabela.
- **Exceções por nome.** Uma exceção vale para qualquer versão do pacote, desde que a licença declarada continue igual à da exceção. Trocar a licença reprova; trocar a versão não.
