"""Tools com `args` (texto) também aceitam `argv` (lista exata, sem parsing) e `cmd` (o subcomando, numa lista fechada que a
descrição mostra). `args` continua valendo, lido com shlex (posix=False no Windows). O `cmd` só cobre o que cada tool já aceita
pelo MCP: os recusados ficam fora da lista e a tool devolve erro antes de rodar qualquer coisa."""
import asyncio
import inspect
import typing

import pytest

from simplicio_video import hostos, mcp_server

# Os subcomandos que cada tool aceita pelo MCP: o cmd (a lista fechada) e a linha da descrição mostram esta mesma lista.
CMD_POR_TOOL = {
    "video.clone": ("help", "version", "doctor", "check", "plan", "pricing", "status", "builds", "history", "activity",
                    "inspect", "logs", "paths", "vocabulary", "get", "media"),
    "video.montage": ("clone", "doctor", "hyperframes-doctor", "preflight", "help", "pipelines", "tools", "envelope",
                      "estimate", "status", "run-tool"),
    "video.edit": ("setup", "transcribe", "pack", "render", "verify", "grade"),
    "video.opencut": ("clone", "status", "where"),
    "video.toonflow": ("clone", "mcp", "status", "where"),
    "video.moneyprinter": ("where", "clone", "status", "generate", "run"),
    "video.matchcut": ("where", "status", "run"),
    "video.voicestudio": ("status", "voices", "languages", "personalities", "tts", "transcribe", "clone", "describe",
                          "design", "dub", "dub-export", "mcp"),
    "video.rea-video": ("clone", "where", "status", "summary", "probe", "tiles", "stems", "review", "apply-review",
                        "remake-plan", "decompose"),
    "video.shorts": ("inspect", "plan", "cut", "run"),
    "video.media": ("fetch", "probe", "audio", "sheet", "subs", "burn", "mask", "replace-audio", "voice-track"),
    "video.qc": ("congelado",),
}
# Tools com `args` que não têm subcomando: só flags, em argv ou args.
SEM_SUBCOMANDO = ("video.doctor", "video.setup", "video.install", "video.update")
# Subcomandos que o MCP recusa (ficam de fora do cmd): a tool devolve erro com o nome do que não entrou.
RECUSADOS = {
    "video.clone": ("build", "studio", "auth", "runtime", "packages", "capture", "transcribe", "measure"),
    "video.montage": ("setup", "open", "serve", "demo"),
    "video.edit": ("transcribe-batch",),
    "video.opencut": ("dev",),
    "video.toonflow": ("serve",),
    "video.moneyprinter": ("setup", "serve"),
    "video.matchcut": ("setup", "clone"),
    "video.rea-video": ("setup", "remake-run", "capsule-draft", "prefs", "correct", "memory"),
}

FUNCOES = {nome: fn for nome, fn, _ in mcp_server.TOOLS}
DESCRICOES = {nome: desc for nome, _, desc in mcp_server.TOOLS}
COM_ARGS = [nome for nome, fn in FUNCOES.items() if "args" in inspect.signature(fn).parameters]


@pytest.fixture
def cli(monkeypatch):
    """Grava o argv que cada tool entrega ao CLI, sem rodar o CLI."""
    chamadas = []

    def falso(argv, codigos_ok=(0,)):
        chamadas.append(list(argv))
        return {"ok": True, "rc": 0, "result": None, "log": ""}

    monkeypatch.setattr(mcp_server, "_cli", falso)
    return chamadas


def _cmds_do_schema(fn):
    """Os valores aceitos pelo `cmd` da tool: o schema sai do tipo Literal da assinatura."""
    tipo = typing.get_type_hints(fn)["cmd"]
    literal = next(a for a in typing.get_args(tipo) if typing.get_origin(a) is typing.Literal)
    return typing.get_args(literal)


def _enum(prop):
    """Os valores aceitos por uma propriedade do schema: enum, ou const quando há um só valor (o SDK faz assim com Literal de um
    item), direto ou dentro de anyOf (Literal | None)."""
    if "enum" in prop:
        return tuple(prop["enum"])
    if "const" in prop:
        return (prop["const"],)
    return _enum(next(x for x in prop["anyOf"] if x.get("type") != "null"))


# ---------------------------------------------------------------------------------- quais tools e quais subcomandos

def test_as_tools_com_args_sao_as_com_subcomando_mais_as_de_so_flags():
    assert len(COM_ARGS) == 16
    assert set(COM_ARGS) == set(CMD_POR_TOOL) | set(SEM_SUBCOMANDO)


@pytest.mark.parametrize("nome", COM_ARGS)
def test_toda_tool_com_args_tambem_aceita_argv(nome):
    assert "argv" in inspect.signature(FUNCOES[nome]).parameters


@pytest.mark.parametrize("nome", list(CMD_POR_TOOL))
def test_cmd_e_a_lista_fechada_e_a_descricao_mostra_a_mesma(nome):
    assert _cmds_do_schema(FUNCOES[nome]) == CMD_POR_TOOL[nome]
    assert f"MCP subcommands (cmd): {', '.join(CMD_POR_TOOL[nome])}" in DESCRICOES[nome]


@pytest.mark.parametrize("nome, recusados", list(RECUSADOS.items()))
def test_subcomando_recusado_nao_entra_no_cmd(nome, recusados):
    assert not set(recusados) & set(_cmds_do_schema(FUNCOES[nome]))


@pytest.mark.parametrize("nome", SEM_SUBCOMANDO)
def test_tool_sem_subcomando_nao_tem_cmd_e_diz_so_flags(nome):
    assert "cmd" not in inspect.signature(FUNCOES[nome]).parameters
    assert "MCP subcommands: none" in DESCRICOES[nome]


def test_schema_do_sdk_traz_argv_e_o_enum_do_cmd():
    mcp = pytest.importorskip("mcp")
    if not hasattr(mcp, "Client"):
        pytest.skip("in-process Client needs mcp>=2")
    srv = mcp_server.build_server()

    async def go():
        async with mcp.Client(srv) as client:
            return (await client.list_tools()).tools

    schemas = {t.name: t.input_schema for t in asyncio.run(go())}
    for nome in COM_ARGS:
        assert "argv" in schemas[nome]["properties"], nome
    for nome, subcomandos in CMD_POR_TOOL.items():
        assert _enum(schemas[nome]["properties"]["cmd"]) == subcomandos, nome


# ---------------------------------------------------------------------------------- argv chega ao CLI como foi dado

@pytest.mark.parametrize("nome, kwargs, esperado", [
    ("video.media", {"argv": ["probe", '/abs/pasta com espaço/clip "novo".mp4', "--json"]},
     ["media", "probe", '/abs/pasta com espaço/clip "novo".mp4', "--json"]),
    ("video.qc", {"argv": ["congelado", "/abs/pasta/a b.mp4", "--min-s", "0.5"]},
     ["qc", "congelado", "/abs/pasta/a b.mp4", "--min-s", "0.5", "--json"]),
    ("video.clone", {"argv": ["get", "build 1", "--output", "saída x", "--to", "/abs/pasta nova/out.mp4"]},
     ["clone", "get", "build 1", "--output", "saída x", "--to", "/abs/pasta nova/out.mp4"]),
    ("video.montage", {"cmd": "estimate", "argv": ["meu pipeline", "--input", '{"tema": "café \\"quente\\""}']},
     ["montage", "estimate", "meu pipeline", "--input", '{"tema": "café \\"quente\\""}']),
    ("video.montage", {"cmd": "tools", "argv": ["list", "--json"]}, ["montage", "tools", "list", "--json"]),
    ("video.edit", {"argv": ["verify", "/abs/a b.mp4", "-o", "/abs/saída nova.json"]},
     ["edit", "verify", "/abs/a b.mp4", "-o", "/abs/saída nova.json"]),
    ("video.doctor", {"argv": ["all", "--online"]}, ["doctor", "--json", "all", "--online"]),
])
def test_argv_chega_ao_cli_exatamente_como_foi_dado(cli, nome, kwargs, esperado):
    r = FUNCOES[nome](**kwargs)
    assert r["ok"] is True, r
    assert cli == [esperado]


def test_voicestudio_argv_chega_intacto_ao_app(monkeypatch):
    from simplicio_video import voicestudio
    vistos = []
    monkeypatch.setattr(voicestudio, "run_voicestudio", lambda argv, mcp=False: vistos.append(list(argv)) or 0)
    r = mcp_server.video_voicestudio(argv=["tts", "--text", '{"fala": "olá \\"mundo\\""}', "--out", "/abs/pasta nova/fala.wav"])
    assert r["ok"] is True, r
    assert vistos == [["tts", "--text", '{"fala": "olá \\"mundo\\""}', "--out", "/abs/pasta nova/fala.wav", "--json"]]


def test_rea_video_argv_chega_intacto_ao_comando(monkeypatch):
    from simplicio_video import rea_video
    vistos = []
    monkeypatch.setattr(rea_video, "mcp_run", lambda argv: vistos.append(list(argv)) or (0, ""))
    r = mcp_server.video_rea_video(argv=["summary", "/abs/pasta análise/x.json"])
    assert r["ok"] is True, r
    assert vistos == [["summary", "/abs/pasta análise/x.json"]]


def test_cmd_vai_na_frente_do_argv_ou_do_args(cli):
    mcp_server.video_montage(cmd="tools", argv=["list", "--json"])
    mcp_server.video_media(cmd="probe", args='"/abs/a b.mp4" --json')
    assert cli == [["montage", "tools", "list", "--json"], ["media", "probe", "/abs/a b.mp4", "--json"]]


# ---------------------------------------------------------------------------------- args: uma linha lida com shlex

def test_args_le_aspas_como_shell_e_nao_com_split(cli):
    mcp_server.video_media('probe "/abs/pasta com espaço/clip.mp4" --json')
    assert cli == [["media", "probe", "/abs/pasta com espaço/clip.mp4", "--json"]]


def test_args_como_lista_de_textos_continua_valendo(cli):
    mcp_server.video_media(["probe", "/abs/a b.mp4"])
    assert cli == [["media", "probe", "/abs/a b.mp4"]]


def test_args_no_windows_le_com_shlex_sem_comer_a_barra(monkeypatch):
    monkeypatch.setattr(hostos, "is_windows", lambda: True)
    assert mcp_server._argv(r'probe "C:\dir\a b.mp4"', None) == ["probe", r"C:\dir\a b.mp4"]
    assert mcp_server._argv(r"probe C:\dir\a.mp4", None) == ["probe", r"C:\dir\a.mp4"]
    monkeypatch.setattr(hostos, "is_windows", lambda: False)
    assert mcp_server._argv(r"probe C:\dir\a.mp4", None) == ["probe", "C:dira.mp4"]


@pytest.mark.parametrize("chamada", [
    lambda: mcp_server.video_media('probe "/abs/x.mp4'),
    lambda: mcp_server.video_clone('get "build'),
    lambda: mcp_server.video_montage('tools "list'),
    lambda: mcp_server.video_rea_video('summary "x'),
    lambda: mcp_server.video_voicestudio('tts "x'),
])
def test_args_com_aspas_sem_fechar_e_erro_limpo(chamada):
    r = chamada()
    assert r["ok"] is False and "aspas" in r["error"], r


# ---------------------------------------------------------------------------------- erros: nada roda

@pytest.mark.parametrize("nome", COM_ARGS)
def test_args_e_argv_juntos_sao_erro_limpo_e_nada_roda(cli, nome):
    r = FUNCOES[nome](args="status", argv=["status"])
    assert r["ok"] is False and "argv" in r["error"] and "args" in r["error"], r
    assert cli == []


def test_args_vazio_nao_conta_como_dado_quando_vem_argv(cli):
    r = mcp_server.video_media(args="", argv=["probe", "/abs/a b.mp4"])
    assert r["ok"] is True, r
    assert cli == [["media", "probe", "/abs/a b.mp4"]]


def test_argv_tem_de_ser_lista_e_nao_texto(cli):
    r = mcp_server.video_media(argv="probe /abs/a.mp4")
    assert r["ok"] is False and cli == []


@pytest.mark.parametrize("nome, recusado", [(n, c) for n, cs in RECUSADOS.items() for c in cs] +
                         [("video.montage", "inventado"), ("video.media", "inventado")])
def test_cmd_recusado_ou_inventado_e_erro_limpo_e_nada_roda(cli, nome, recusado):
    r = FUNCOES[nome](cmd=recusado)
    assert r["ok"] is False and "cmd" in r["error"], r
    assert cli == []
