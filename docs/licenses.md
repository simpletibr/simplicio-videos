# Licenças das dependências

<!-- Gerado por scripts/licenses.py --write (make licenses-write). Não edite à mão. -->

Scan das distribuições instaladas (`importlib.metadata`). Allowlist: MIT, Apache-2.0, BSD, ISC, PSF-2.0, MPL-2.0 (nível de arquivo). Exceções com justificativa: `docs/licenses-exceptions.yaml`. Regras e como atualizar: `docs/host/licenses.md`.

| Pacote | Versão | Licença | Status | Onde é usado |
|---|---|---|---|---|
| annotated-types | 0.8.0 | MIT | permitida | pydantic |
| anyio | 4.15.1 | MIT | permitida | httpcore2[asyncio], httpx2, mcp, sse-starlette, starlette |
| attrs | 26.1.0 | MIT | permitida | jsonschema, pytest[dev], referencing |
| cffi | 2.1.1 | MIT-0 | exceção | cryptography |
| click | 8.5.0 | BSD-3-Clause | permitida | httpx2[cli], uvicorn |
| cryptography | 50.0.2 | Apache-2.0 OR BSD-3-Clause | permitida | PyJWT[crypto] |
| h11 | 0.16.0 | MIT | permitida | httpcore2, uvicorn |
| httpcore2 | 2.16.0 | BSD-3-Clause | permitida | httpx2 |
| httpx2 | 2.16.0 | BSD-3-Clause | permitida | mcp, starlette[full] |
| idna | 3.20 | BSD-3-Clause | permitida | anyio, httpx2, jsonschema[format-nongpl], jsonschema[format] |
| iniconfig | 2.3.1 | MIT | permitida | pytest |
| jsonschema | 4.26.0 | MIT | permitida | mcp, simplicio-video |
| jsonschema-specifications | 2025.9.1 | MIT | permitida | jsonschema |
| mcp | 2.3.0 | MIT | permitida | simplicio-video[mcp] |
| mcp-types | 2.3.0 | MIT | permitida | mcp |
| opentelemetry-api | 1.45.2 | Apache-2.0 | permitida | mcp, starlette[full] |
| packaging | 26.3 | Apache-2.0 OR BSD-2-Clause | permitida | pytest |
| pip | 25.1.1 | MIT | permitida | — |
| pluggy | 1.7.0 | MIT | permitida | pytest |
| pycparser | 3.12 | BSD-3-Clause | permitida | cffi |
| pydantic | 2.14.2 | MIT | permitida | mcp, mcp-types, sse-starlette[examples] |
| pydantic_core | 2.50.2 | MIT | permitida | pydantic |
| Pygments | 2.21.0 | BSD-2-Clause | permitida | httpx2[cli], pytest |
| PyJWT | 2.15.1 | MIT | permitida | mcp |
| pytest | 9.2.0 | MIT | permitida | idna[all], pytest-socket, simplicio-video[test] |
| pytest-socket | 0.8.1 | MIT | permitida | simplicio-video[test] |
| python-multipart | 0.0.32 | Apache-2.0 | permitida | mcp, starlette[full] |
| PyYAML | 6.0.3 | MIT | permitida | pytest[dev], simplicio-video, starlette[full], uvicorn[standard] |
| referencing | 0.37.0 | MIT | permitida | jsonschema, jsonschema-specifications |
| rpds-py | 2026.9.1 | MIT | permitida | jsonschema, referencing |
| ruff | 0.17.3 | MIT | permitida | idna[all], simplicio-video[test] |
| shellcheck_py | 0.11.0.1 | MIT | exceção | simplicio-video[test] |
| simplicio-video | 0.5.0 | AGPL-3.0-or-later | produto | produto (este repo) |
| sse-starlette | 3.6.0 | BSD-3-Clause | permitida | mcp |
| starlette | 1.10.0 | BSD-3-Clause | permitida | mcp, sse-starlette |
| truststore | 0.10.5 | MIT | permitida | httpcore2, httpx2 |
| typing_extensions | 4.16.0 | PSF-2.0 | permitida | PyJWT, anyio, cryptography, httpx2, mcp, mcp-types, opentelemetry-api, pydantic, pydantic_core, referencing, starlette, typing-inspection, uvicorn |
| typing-inspection | 0.4.4 | MIT | permitida | mcp, pydantic |
| uvicorn | 0.54.0 | BSD-3-Clause | permitida | mcp, sse-starlette[examples], sse-starlette[uvicorn] |
