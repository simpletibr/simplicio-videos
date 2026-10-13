---
name: Issue da fábrica
about: Formato das issues do simplicio-videos (escopo, paths, critérios testáveis, TDD)
title: "[M0] area: resumo curto"
labels: ""
---

> **M? Nome do milestone · track · size S/M/L** · parallel-safe · depends on: none ou #N
>
> Spec: [architecture](https://github.com/simpletibr/simplicio-videos/blob/main/docs/factory/README.md) · [parallel work](https://github.com/simpletibr/simplicio-videos/blob/main/docs/factory/parallel-work.md) · entrada desta issue em [`ownership.yaml`](https://github.com/simpletibr/simplicio-videos/blob/main/docs/factory/ownership.yaml).

## Goal
<!-- Uma frase: o que passa a ser verdade quando esta issue fechar. -->

## Scope
**In this issue:**

**Not in this issue:**

## Why
<!-- O problema de hoje, com o sintoma observável. -->

## Owns (only these paths)
<!-- Mesma lista da entrada em ownership.yaml. Arquivo compartilhado: `path#secao`. Qualquer outro path falha em scripts/check_ownership.py. -->
-

## Interfaces
**Consumes:**

**Produces:**

## Tests first (separate first commit, red)
<!-- O primeiro commit só toca testes, fixtures e docs. Liste os testes que ele traz. -->
-

## Acceptance criteria
<!-- Cada critério é um comando ou um teste. Sem critério testável, comente antes de codar. -->
- [ ]

## Docs and help
<!-- docs/host/<nome>.md; cada comando com --help e exemplos; ADR (número reservado), se houver decisão. -->
-

## Risks and open questions
-

## Definition of done
Red-first commit · `make check` green · loop e2e green · every command has help with examples · zero LLM tokens on the default path · docs and generated references updated · independent review (`reviewed` label) · `Closes #N`. See [parallel-work.md](https://github.com/simpletibr/simplicio-videos/blob/main/docs/factory/parallel-work.md).
