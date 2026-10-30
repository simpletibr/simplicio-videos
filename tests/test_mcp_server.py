"""MCP stub: tool functions directly, and (when the SDK is installed) list/call over an in-process MCP client."""
import asyncio
import json
import re

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
    assert names == sorted(n for n, _, _ in mcp_server.TOOLS) and len(names) == 29
    payload = res.structured_content or json.loads(res.content[0].text)
    payload = payload.get("result", payload)
    assert payload["ok"] is True and payload["errors"] == []


def test_video_init_descreve_onde_grava():
    """O cliente LLM só enxerga a descrição da tool: ela diz onde o contrato é gravado e que, num pacote instalado, `out` é obrigatório."""
    _, _, desc = next(t for t in mcp_server.TOOLS if t[0] == "video.init")
    assert "clients/<cliente>/<campanha>/contract.yaml" in desc
    assert re.search(r"pip-installed package.{0,40}`out`.{0,80}required", desc, re.S), desc
    assert "nothing is written" in desc, desc


# ---------------------------------------------------------------------------------- every CLI command over MCP

def _nomes_da_cli():
    import argparse
    from simplicio_video import cli
    sub = next(a for a in cli.build_parser()._actions if isinstance(a, argparse._SubParsersAction))
    return set(sub.choices)


def test_todo_comando_da_cli_tem_tool_no_mcp_menos_o_proprio_servidor_e_o_entrar_sair():
    """Every top-level CLI command has an MCP tool. Three are terminal-only on purpose: `mcp` is the server itself, and
    `login` and `logout` open a browser and change the login file shared with the Runtime."""
    ferramentas = {name.split(".", 1)[1] for name, _, _ in mcp_server.TOOLS}
    faltam = _nomes_da_cli() - {"mcp", "login", "logout"} - ferramentas
    assert not faltam, f"comandos da CLI sem tool no MCP: {sorted(faltam)}"


def test_os_comandos_que_nao_terminam_ou_gastam_recusam_com_o_comando_do_terminal():
    for recusa in (mcp_server.video_auth("login"), mcp_server.video_update(""), mcp_server.video_install("--uninstall"),
                   mcp_server.video_montage("serve"), mcp_server.video_montage(""), mcp_server.video_montage("clone /tmp/x"),
                   mcp_server.video_montage("demo"), mcp_server.video_montage("-c print(1)"), mcp_server.video_montage("rodar.py"),
                   mcp_server.video_opencut("dev"), mcp_server.video_moneyprinter("serve"), mcp_server.video_moneyprinter("setup")):
        assert recusa["ok"] is False and "terminal" in recusa["error"], recusa


def test_instalar_skills_so_com_destino_claro(tmp_path):
    assert mcp_server.video_install("")["ok"] is False                       # would write into the server's folder
    assert mcp_server.video_install(f"--target relativo")["ok"] is False      # relative target
    r = mcp_server.video_install(f"--check --target {tmp_path}")             # read-only checks are fine anywhere
    assert r["rc"] in (0, 10)


def test_saida_relativa_e_recusada_nas_tools_que_gravam(tmp_path):
    assert mcp_server.video_media("probe x.mp4 -o rel.json")["ok"] is False
    assert mcp_server.video_shorts(f"plan x.mp4 --transcript {tmp_path / 'w.json'}")["ok"] is False  # no -o: no folder chosen
    assert mcp_server.video_shorts(f"cut x.mp4 p.json -o rel")["ok"] is False


def test_as_tools_de_leitura_respondem_em_json(tmp_path, monkeypatch):
    monkeypatch.setenv("SIMPLICIO_TOOLS_DIR", str(tmp_path / "tools"))
    tools = mcp_server.video_tools()
    assert tools["ok"] is True and {r["name"] for r in tools["result"]} >= {"yt-dlp", "voicestudio", "video-use"}
    status = mcp_server.video_status()
    assert status["ok"] is True and "tools" in status["result"]
    assert mcp_server.video_jobs("clean")["ok"] is True


def test_as_ferramentas_de_passagem_rodam_o_help_sem_TypeError():
    """clone, montage, opencut and edit pass their arguments to the CLI dispatch. They used to call the runners with a `log=`
    keyword they do not take, so every call failed with TypeError: this keeps them running."""
    for r in (mcp_server.video_edit("--help"), mcp_server.video_opencut("--help"), mcp_server.video_montage("--help")):
        assert r["ok"] is True and r["rc"] == 0, r
