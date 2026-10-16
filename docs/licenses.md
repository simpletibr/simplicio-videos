# Licenças das dependências

<!-- Gerado por scripts/licenses.py --write (make licenses-write). Não edite à mão. -->

Scan das distribuições instaladas (`importlib.metadata`). Allowlist: MIT, Apache-2.0, BSD, ISC, PSF-2.0, MPL-2.0 (nível de arquivo). Exceções com justificativa: `docs/licenses-exceptions.yaml`. Regras e como atualizar: `docs/host/licenses.md`.

| Pacote | Versão | Licença | Status | Onde é usado |
|---|---|---|---|---|
| annotated-types | 0.8.0 | MIT | permitida | pydantic |
| anyio | 4.15.1 | MIT | permitida | claude-agent-sdk, claude-agent-sdk[dev], httpcore2[asyncio], httpx2, mcp, sse-starlette, starlette |
| argcomplete | 3.1.4 | Apache Software License | permitida | — |
| attrs | 26.1.0 | MIT | permitida | jsonschema, referencing |
| beautifulsoup4 | 4.15.0 | MIT License | permitida | lxml[htmlsoup], markdownify, markitdown, pandas[all], pandas[html] |
| blinker | 1.7.0 | MIT License | permitida | — |
| certifi | 2026.7.22 | MPL-2.0 | permitida | requests |
| cffi | 2.1.1 | MIT-0 | exceção | cryptography |
| charset-normalizer | 3.5.1 | MIT | permitida | beautifulsoup4[charset-normalizer], markitdown, pdfminer.six, reportlab, requests |
| claude-agent-sdk | 0.2.159 | MIT | permitida | — |
| click | 8.5.0 | BSD-3-Clause | permitida | httpx2[cli], magika, python-dotenv[cli], uvicorn |
| colorama | 0.4.6 | BSD License | permitida | conan |
| conan | 2.32.0 | MIT | permitida | — |
| cryptography | 50.0.1 | Apache-2.0 OR BSD-3-Clause | permitida | PyJWT[crypto], PyJWT[dev], pdfminer.six, pypdf[crypto], pypdf[full] |
| cryptography | 41.0.7 | Apache-2.0 OR BSD-3-Clause | permitida | PyJWT[crypto], PyJWT[dev], pdfminer.six, pypdf[crypto], pypdf[full] |
| dbus-python | 1.3.2 | Expat (MIT/X11) | permitida | — |
| defusedxml | 0.7.1 | PSFL | negada | markitdown, pillow[tests], pillow[xmp] |
| distro | 1.9.0 | Apache License, Version 2.0 | permitida | conan |
| et_xmlfile | 2.0.0 | MIT | permitida | openpyxl |
| fasteners | 0.20 | Apache-2.0 | permitida | conan |
| flatbuffers | 25.12.19 | Apache 2.0 | permitida | onnxruntime |
| h11 | 0.16.0 | MIT | permitida | httpcore2, uvicorn |
| httpcore2 | 2.13.0 | BSD-3-Clause | permitida | httpx2 |
| httplib2 | 0.20.4 | MIT | permitida | — |
| httpx2 | 2.13.0 | BSD-3-Clause | permitida | mcp, starlette[full] |
| idna | 3.20 | BSD-3-Clause | permitida | anyio, httpx2, jsonschema[format-nongpl], jsonschema[format], requests |
| idna | 3.19 | BSD-3-Clause | permitida | anyio, httpx2, jsonschema[format-nongpl], jsonschema[format], requests |
| Jinja2 | 3.1.6 | BSD License | permitida | conan, pandas[all], pandas[output-formatting], pyparsing[diagrams], starlette[full] |
| jsonschema | 4.26.0 | MIT | permitida | claude-agent-sdk, mcp |
| jsonschema-specifications | 2025.9.1 | MIT | permitida | jsonschema |
| launchpadlib | 1.11.0 | LGPL v3 | negada | — |
| lazr.restfulclient | 0.14.6 | LGPL v3 | negada | — |
| lazr.uri | 1.0.6 | LGPL v3 | negada | — |
| lxml | 6.1.3 | BSD-3-Clause | permitida | beautifulsoup4[lxml], markitdown[all], markitdown[docx], pandas[all], pandas[html], pandas[xml], python-docx, python-pptx |
| magika | 0.6.3 | Apache-2.0 | permitida | markitdown |
| markdownify | 1.2.3 | MIT License | permitida | markitdown |
| markitdown | 0.1.7 | MIT | permitida | — |
| MarkupSafe | 3.0.3 | BSD-3-Clause | permitida | Jinja2 |
| mcp | 2.2.0 | MIT | permitida | claude-agent-sdk |
| mcp-types | 2.2.0 | MIT | permitida | mcp |
| numpy | 2.5.3 | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 | negada | magika, onnxruntime, pandas |
| oauthlib | 3.2.2 | BSD | permitida | — |
| onnxruntime | 1.29.0 | MIT License | permitida | magika |
| openpyxl | 3.1.5 | MIT | permitida | markitdown[all], markitdown[xlsx], pandas[all], pandas[excel] |
| opentelemetry-api | 1.44.0 | Apache-2.0 | permitida | claude-agent-sdk[otel], mcp |
| packaging | 26.3 | Apache-2.0 OR BSD-2-Clause | permitida | onnxruntime, pillow[tests] |
| packaging | 24.0 | Apache Software License OR BSD License | permitida | onnxruntime, pillow[tests] |
| pandas | 3.0.5 | BSD License | permitida | markitdown[all], markitdown[xls], markitdown[xlsx] |
| patch-ng | 1.19.1 | MIT | permitida | conan |
| pdfminer.six | 20260107 | MIT | permitida | markitdown[all], markitdown[pdf], pdfplumber |
| pdfplumber | 0.11.10 | MIT License | permitida | markitdown[all], markitdown[pdf] |
| pillow | 12.3.0 | MIT-CMU | permitida | pdfminer.six[image], pdfplumber, pypdf[full], pypdf[image], python-pptx, reportlab |
| pip | 24.0 | MIT | permitida | — |
| protobuf | 7.36.1 | 3-Clause BSD License | permitida | onnxruntime |
| pycparser | 3.0 | BSD-3-Clause | permitida | cffi |
| pydantic | 2.13.5 | MIT | permitida | mcp, mcp-types, sse-starlette[examples] |
| pydantic_core | 2.46.5 | MIT | permitida | pydantic |
| PyGObject | 3.48.2 | GNU LGPL | negada | — |
| PyJWT | 2.14.0 | MIT | permitida | conan[dev], conan[test], mcp |
| PyJWT | 2.7.0 | MIT | permitida | conan[dev], conan[test], mcp |
| pyparsing | 3.1.1 | MIT License | permitida | httplib2 |
| pypdf | 6.17.0 | BSD-3-Clause | permitida | — |
| pypdfium2 | 5.13.0 | BSD-3-Clause, Apache-2.0, dependency licenses | permitida | pdfplumber |
| python-apt | 2.7.7+ubuntu5.3 | GNU GPL | negada | — |
| python-dateutil | 2.9.0.post0 | Dual License | negada | conan, pandas |
| python-docx | 1.2.0 | MIT | permitida | — |
| python-dotenv | 1.2.3 | BSD-3-Clause | permitida | magika, mcp[cli], uvicorn[standard] |
| python-multipart | 0.0.32 | Apache-2.0 | permitida | mcp, starlette[full] |
| python-pptx | 1.0.2 | MIT | permitida | markitdown[all], markitdown[pptx] |
| PyYAML | 6.0.1 | MIT | permitida | conan, starlette[full], uvicorn[standard] |
| referencing | 0.37.0 | MIT | permitida | jsonschema, jsonschema-specifications |
| reportlab | 5.0.1 | BSD License | permitida | — |
| requests | 2.34.2 | Apache-2.0 | permitida | conan, markitdown |
| rpds-py | 2026.6.3 | MIT | permitida | jsonschema, referencing |
| setuptools | 68.1.2 | MIT License | permitida | conan[dev], conan[test], pillow[tests], wheel[test] |
| six | 1.17.0 | MIT | permitida | markdownify, python-dateutil |
| six | 1.16.0 | MIT | permitida | markdownify, python-dateutil |
| sniffio | 1.3.1 | MIT OR Apache-2.0 | permitida | claude-agent-sdk |
| soupsieve | 2.9.2 | MIT | permitida | beautifulsoup4 |
| sse-starlette | 3.4.11 | BSD-3-Clause | permitida | mcp |
| starlette | 1.6.0 | BSD-3-Clause | permitida | mcp, sse-starlette |
| toml | 0.10.2 | MIT | permitida | — |
| truststore | 0.10.4 | MIT | permitida | httpcore2, httpx2 |
| typing_extensions | 4.16.0 | PSF-2.0 | permitida | PyJWT, anyio, beautifulsoup4, claude-agent-sdk, cryptography, httpx2, mcp, mcp-types, opentelemetry-api, pydantic, pydantic_core, pypdf, python-docx, python-pptx, referencing, starlette, typing-inspection, uvicorn |
| typing-inspection | 0.4.4 | MIT | permitida | mcp, pydantic |
| urllib3 | 2.8.0 | MIT | permitida | conan, requests |
| urllib3 | 2.7.0 | MIT | permitida | conan, requests |
| uvicorn | 0.53.0 | BSD-3-Clause | permitida | mcp, sse-starlette[examples], sse-starlette[uvicorn] |
| wadllib | 1.3.6 | LGPL v3 | negada | — |
| wheel | 0.42.0 | MIT License | permitida | argcomplete[test], pypdf[dev] |
| xlsxwriter | 3.2.9 | BSD-2-Clause | permitida | pandas[all], pandas[excel], python-pptx |
| xmltodict | 0.13.0 | MIT | permitida | — |
| yq | 3.1.0 | Apache Software License | permitida | — |
