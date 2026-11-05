"""The MCP tool registry is conflict-free (DESC_<fn> next to each function, jobs kinds via _register) and its output is frozen."""
import asyncio
import json
from pathlib import Path

import pytest

from simplicio_video import jobs, mcp_server

SNAPSHOT = json.loads((Path(__file__).parent / "data" / "mcp_tools_list.snapshot.json").read_text(encoding="utf-8"))


def test_tools_table_matches_snapshot_without_sdk():
    assert [n for n, _, _ in mcp_server.TOOLS] == SNAPSHOT["order"]
    assert {n: d for n, _, d in mcp_server.TOOLS} == {t["name"]: t["description"] for t in SNAPSHOT["tools"]}


def test_every_description_is_a_desc_constant_next_to_its_function():
    for name, fn, desc in mcp_server.TOOLS:
        assert getattr(mcp_server, f"DESC_{fn.__name__}") is desc, name


def test_mcp_tools_list_is_identical_to_the_snapshot():
    mcp = pytest.importorskip("mcp")
    if not hasattr(mcp, "Client"):
        pytest.skip("in-process Client needs mcp>=2")
    srv = mcp_server.build_server()

    async def go():
        async with mcp.Client(srv) as client:
            res = await client.list_tools()
            return [{"name": t.name, "description": t.description, "inputSchema": t.input_schema}
                    for t in sorted(res.tools, key=lambda t: t.name)]
    assert asyncio.run(go()) == SNAPSHOT["tools"]


def test_jobs_kinds_are_registered_in_order():
    assert list(jobs.KINDS) == ["swap-run", "voice", "rea-video", "moneyprinter", "montage-tool"]
    for spec in jobs.KINDS.values():
        assert set(spec) == {"prepare", "argv", "result"} and all(callable(f) for f in spec.values())


def test_video_media_nao_promete_que_escreve_so_arquivo_novo():
    """media overwrites an existing -o (ffmpeg -y); only `fetch --info -o` refuses an existing file (_write_new_json). The MCP
    description and docstring must say the overwrite, not "new files"."""
    desc = mcp_server.DESC_video_media
    assert "Writes new files" not in desc and "overwrit" in desc.lower()
    doc = " ".join((mcp_server.video_media.__doc__ or "").split())
    assert "writes a new file" not in doc and "overwrit" in doc.lower()
