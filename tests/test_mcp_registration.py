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
    assert list(jobs.KINDS) == ["swap-run", "voice", "rea-video", "moneyprinter", "montage-tool", "video-to-skill"]
    for spec in jobs.KINDS.values():
        assert set(spec) == {"prepare", "argv", "result"} and all(callable(f) for f in spec.values())


def _frases_de_saida_do_media(texto: str) -> list:
    """What the text must say about -o, one by one: every subcommand writes to it, an existing file is overwritten (ffmpeg -y, probe), and
    `fetch` never overwrites (a new path)."""
    texto = " ".join(texto.split()).lower()
    frases = ("writes to -o", "overwritten", "ffmpeg -y", "fetch never overwrites", "new path")
    return [f for f in frases if f not in texto and not (f == "fetch never overwrites" and "fetch refuses to overwrite" in texto)]


def test_video_media_nao_promete_que_escreve_so_arquivo_novo():
    """media overwrites an existing -o (ffmpeg -y); only `fetch --info -o` refuses an existing file (_write_new_json). The MCP
    description and docstring must say the overwrite, not "new files"."""
    desc = mcp_server.DESC_video_media
    assert "Writes new files" not in desc and "overwrit" in desc.lower()
    doc = " ".join((mcp_server.video_media.__doc__ or "").split())
    assert "writes a new file" not in doc and "overwrit" in doc.lower()


def test_video_media_diz_a_regra_de_saida_inteira_na_descricao_e_no_docstring():
    """Strengthens the check above (it only looked for substrings): the overwrite AND the fetch exception, in both texts."""
    assert _frases_de_saida_do_media(mcp_server.DESC_video_media) == []
    assert _frases_de_saida_do_media(mcp_server.video_media.__doc__ or "") == []


def test_a_checagem_da_regra_de_saida_pega_a_excecao_do_fetch_que_falta():
    """Mutation: without the fetch exception (or without the overwrite) the check must fail."""
    sem_excecao = mcp_server.DESC_video_media.replace("while fetch never overwrites, so give a new path.", "")
    assert _frases_de_saida_do_media(sem_excecao)
    sem_sobrescreve = mcp_server.DESC_video_media.replace("overwritten", "replaced")
    assert "overwritten" in _frases_de_saida_do_media(sem_sobrescreve)
