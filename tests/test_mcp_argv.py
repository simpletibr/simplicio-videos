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
    "video.video-to-skill": ("status", "where", "check", "skill", "extract", "frame-at", "clip", "compile", "merge"),
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
    "video.video-to-skill": ("setup", "clone", "install", "sandbox", "observe", "verify", "bench", "eval"),
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
    """Os valores aceitos por uma propriedade do schema, sempre como `enum`, inclusive com um valor só (o SDK escreve `const` para
    um Literal de um item, e o schema de cmd não usa isso), direto ou dentro de anyOf (Literal | None)."""
    assert "const" not in prop, f"const em vez de enum: {prop}"
    if "enum" in prop:
        return tuple(prop["enum"])
    return _enum(next(x for x in prop["anyOf"] if x.get("type") != "null"))


# ---------------------------------------------------------------------------------- quais tools e quais subcomandos

def test_as_tools_com_args_sao_as_com_subcomando_mais_as_de_so_flags():
    assert len(COM_ARGS) == 17
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
    # sem aspas a linha é só separada em espaços (como antes do shlex): a barra de um caminho fica
    assert mcp_server._argv(r"probe C:\dir\a.mp4", None) == ["probe", r"C:\dir\a.mp4"]


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


@pytest.fixture
def voicestudio_gravado(monkeypatch):
    """O voicestudio não passa por _cli: grava o argv que chegaria ao app, sem falar com ele."""
    from simplicio_video import voicestudio
    vistos = []
    monkeypatch.setattr(voicestudio, "run_voicestudio", lambda argv, mcp=False: vistos.append(list(argv)) or 0)
    return vistos


@pytest.mark.parametrize("nome", list(CMD_POR_TOOL))
def test_cmd_repetido_em_argv_e_erro_claro_e_nada_roda(cli, voicestudio_gravado, nome):
    """`cmd="probe"` com argv=["probe", ...] repetiria o subcomando (probe probe ...): é recusado antes de rodar, com o motivo."""
    cmd = CMD_POR_TOOL[nome][0]
    r = FUNCOES[nome](cmd=cmd, argv=[cmd])
    assert r["ok"] is False and "cmd" in r["error"], r
    assert cli == [] and voicestudio_gravado == []


# ---------------------------------------------------------------------------------- install: guardas e --target

@pytest.mark.parametrize("extra", ["--uninst", "--unins", "--uninstall=1", "--prune", "--prune-proj", "--prune-project-copies=x"])
def test_install_recusa_abreviacao_e_forma_igual_das_opcoes_de_remocao(cli, extra):
    """argparse aceita abreviação e `--opt=valor`: o MCP recusa as duas, ainda que venha --check (que não escreve)."""
    r = mcp_server.video_install(args=f"--check {extra} --target /abs/proj")
    assert r["ok"] is False and "terminal" in r["error"], r
    assert cli == []
    r = mcp_server.video_install(argv=["--check", extra, "--target", "/abs/proj"])
    assert r["ok"] is False and cli == []


@pytest.mark.parametrize("kwargs", [{"args": "--target"}, {"argv": ["--global", "--target"]}, {"args": "--check --target"}])
def test_install_com_target_sem_caminho_e_erro_limpo(cli, kwargs):
    assert mcp_server.video_install(**kwargs) == {"ok": False, "error": "install: --target precisa de um caminho"}
    assert cli == []


def test_install_com_target_relativo_na_forma_igual_e_recusado(cli):
    """A forma `--target X` já era recusada; a `--target=X` passava e o prune usaria o caminho relativo."""
    r = mcp_server.video_install(argv=["--global", "--target=relativo"])
    assert r["ok"] is False and cli == [], r


def test_install_help_nao_passa_pelas_guardas_de_escrita(cli):
    """`--help` não escreve: não pode ser recusado pedindo --global ou --target."""
    r = mcp_server.video_install(argv=["--help"])
    assert r["ok"] is True and cli == [["install", "--help"]], r


def test_update_help_nao_e_recusado_como_instalacao(cli):
    r = mcp_server.video_update(argv=["--help"])
    assert r["ok"] is True and cli == [["update", "--help"]], r


# ---------------------------------------------------------------------------------- --help: uma regra para as tools

ALLOWLIST_SEM_AJUDA = ("video.toonflow", "video.moneyprinter", "video.matchcut", "video.rea-video", "video.video-to-skill")


@pytest.mark.parametrize("nome", [n for n in COM_ARGS if n not in ALLOWLIST_SEM_AJUDA])
def test_help_em_argv_e_respondido_pela_tool(cli, voicestudio_gravado, nome):
    """`--help` / `-h` em argv pede a ajuda do comando. Cada tool com args responde, menos as que têm uma allow-list sem a ajuda."""
    r = FUNCOES[nome](argv=["--help"])
    assert r["ok"] is True, (nome, r)


@pytest.mark.parametrize("nome", ALLOWLIST_SEM_AJUDA)
def test_help_das_allowlists_e_recusado_com_o_terminal(cli, nome):
    """toonflow, moneyprinter, matchcut e rea-video (o --help global) deixam a ajuda de fora da allow-list, por decisão deles:
    o MCP recusa e manda ao terminal, sem rodar nada."""
    r = FUNCOES[nome](argv=["--help"])
    assert r["ok"] is False and "terminal" in r["error"], (nome, r)
    assert cli == []


def test_instrucoes_do_servidor_documentam_o_help():
    assert "--help" in mcp_server.INSTRUCTIONS and "-h" in mcp_server.INSTRUCTIONS


# ---------------------------------------------------------------------------------- args: tamanho e barra final

def test_args_com_aspas_e_barra_no_fim_diz_a_barra_e_nao_as_aspas(cli):
    r = mcp_server.video_media('probe "/abs/a b.mp4" \\')
    assert r["ok"] is False and "barra" in r["error"] and "aspas sem fechar" not in r["error"], r
    assert cli == []


@pytest.mark.parametrize("args", ["probe /abs/" + "a" * 70_000 + ".mp4", 'probe "' + "a" * 70_000 + '"'])
def test_args_de_mais_de_64_KiB_e_recusado_com_erro_claro(cli, args):
    """Uma linha de 1 MB demora ~20 s no shlex: passa do limite, recusa antes de ler, e manda usar `argv`."""
    r = mcp_server.video_media(args)
    assert r["ok"] is False and "64 KiB" in r["error"] and "argv" in r["error"], r
    assert cli == []


# ---------------------------------------------------------------------------------- revisão 3: barra fora de aspas, `..` na saída

def test_install_descricao_diz_que_uninstall_com_dry_run_e_so_terminal():
    assert "also with --dry-run, are terminal-only" in DESCRICOES["video.install"]


@pytest.mark.parametrize("linha", ['probe C:\\dir\\a.mp4 -o "/abs/o 1.mp4"', 'probe "/abs/a b.mp4" C:\\x\\b.mp4'])
def test_args_que_mistura_barra_fora_de_aspas_com_aspas_e_recusada_com_use_argv(cli, linha):
    """Barra fora de aspas numa linha que também tem aspas é ambígua: o shlex transforma C:\\dir\\a.mp4 em C:dira.mp4 sem avisar.
    A linha é recusada e a mensagem manda usar `argv`."""
    r = mcp_server.video_media(linha)
    assert r["ok"] is False and "argv" in r["error"], r
    assert cli == []


@pytest.mark.parametrize("windows", [True, False])
def test_split_args_recusa_a_mistura_nos_dois_sistemas(windows):
    with pytest.raises(mcp_server._ArgsErro):
        mcp_server._split_args('probe C:\\dir\\a.mp4 -o "/abs/o 1.mp4"', windows=windows)


def test_install_uninstall_com_dry_run_pelo_mcp_e_recusado_sem_rodar(cli):
    r = mcp_server.video_install(argv=["--uninstall", "--dry-run", "--target", "/abs/proj"])
    assert r["ok"] is False and "terminal" in r["error"], r
    assert cli == []


def test_args_com_aspa_escapada_dentro_de_aspas_duplas_e_recusado_com_barra_depois(cli, monkeypatch):
    """No POSIX `\\"` dentro de aspas duplas é aspa escapada, não fim da aspa: `probe "a\\"b" C:\\x` (o shlex dava ['probe', 'a"b',
    'C:x']) mistura aspa e barra fora de aspas, então é recusada com 'use argv'."""
    monkeypatch.setattr(hostos, "is_windows", lambda: False)
    r = mcp_server.video_media('probe "a\\"b" C:\\x')
    assert r["ok"] is False and "argv" in r["error"], r
    assert cli == []


def test_args_so_com_aspas_e_so_com_barra_continuam_valendo(cli):
    """Os dois casos que não são ambíguos seguem como antes: só aspas (shlex) e só barra (a barra do caminho fica)."""
    mcp_server.video_media('probe "/abs/com espaço.mp4" --json')
    mcp_server.video_media(r"probe C:\dir\a.mp4 --json")
    assert cli == [["media", "probe", "/abs/com espaço.mp4", "--json"], ["media", "probe", r"C:\dir\a.mp4", "--json"]]
    assert mcp_server._split_args(r"probe C:\dir\a.mp4", windows=True) == ["probe", r"C:\dir\a.mp4"]
    assert mcp_server._split_args(r'probe "C:\dir\a b.mp4"', windows=True) == ["probe", r"C:\dir\a b.mp4"]


@pytest.mark.parametrize("nome, argv", [
    ("video.media", ["sheet", "/abs/x.mp4", "-o", "/abs/../etc/x.jpg"]),
    ("video.edit", ["verify", "/abs/a.mp4", "0", "1", "-o", "/abs/../x.png"]),
    ("video.shorts", ["cut", "/abs/x.mp4", "-o", "/abs/../o"]),
])
def test_saida_com_segmento_pai_e_recusada_como_no_hypit_e_no_voicestudio(cli, nome, argv):
    r = FUNCOES[nome](argv=argv)
    assert r["ok"] is False and ".." in r["error"], r
    assert cli == []
