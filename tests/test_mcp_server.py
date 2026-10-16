"""MCP stub: tool functions directly, and (when the SDK is installed) list/call over an in-process MCP client."""
import asyncio
import json

import pytest

from simplicio_video import mcp_server


def test_tool_functions_without_sdk(mini):
    rep = mcp_server.video_validate(str(mini))
    assert rep["ok"] is True
    v = mcp_server.video_voice(str(mini))
    assert v["ok"] and v["result"]["lines"]["vo1"]["fits"]
    assert any(t["id"] == "gemini" for t in mcp_server.video_list("voices")["items"])


def test_mcp_protocol_lists_and_calls_tools(mini):
    mcp = pytest.importorskip("mcp")
    if not hasattr(mcp, "Client"):
        pytest.skip("in-process Client needs mcp>=2")
    srv = mcp_server.build_server()

    async def go():
        async with mcp.Client(srv) as client:
            tools = await client.list_tools()
            names = sorted(t.name for t in tools.tools)
            res = await client.call_tool("video.validate", {"contrato": str(mini)})
            return names, res

    names, res = asyncio.run(go())
    assert names == sorted(["video.init", "video.validate", "video.voice", "video.render", "video.run", "video.list", "video.clone", "video.montage", "video.opencut", "video.formats", "video.swap", "video.toonflow", "video.moneyprinter", "video.jobs", "video.edit"])
    payload = res.structured_content or json.loads(res.content[0].text)
    payload = payload.get("result", payload)
    assert payload["ok"] is True and payload["errors"] == []
