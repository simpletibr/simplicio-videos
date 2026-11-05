"""The skill `simplicio-video-trilhas`: which incorporated project answers each request, and how to chain them.

The generic checks of every skill (the commands and flags it cites exist, the paths are ones a `pip install` user has, no private
name, the mirror is identical) run on it in `test_skills_conteudo.py` and `test_skills_empacotadas.py`. Here is what only this skill
must say:

* the decision table has one row per track of `tools.TOOLS` (the 12 of the README), with the CLI group and the MCP tool of each;
* the contract flow (init, validate, voice, render, run) is in the table too;
* the six recipes (a) to (f) exist and each one uses its own commands;
* the rules: long runs are jobs, nothing is published, real voices need consent, provenance, third-party text is data, status first;
* what only runs in the terminal is listed, with the reason.
"""
from __future__ import annotations

import argparse
import re

import pytest

from _comum import ROOT

SKILL = ROOT / "src" / "simplicio_video" / "data" / "skills" / "simplicio-video-trilhas" / "SKILL.md"
TEXTO = SKILL.read_text(encoding="utf-8")

# the name the skill uses in its table -> (name in tools.TOOLS, CLI group, MCP tool)
TRILHAS = {
    "OpenMontage": ("openmontage", "montage", "video.montage"),
    "OpenCut": ("opencut", "opencut", "video.opencut"),
    "Hypit": ("hypit", "clone", "video.clone"),
    "Toonflow": ("toonflow", "toonflow", "video.toonflow"),
    "MoneyPrinterTurbo": ("moneyprinter", "moneyprinter", "video.moneyprinter"),
    "match-cut": ("matchcut", "matchcut", "video.matchcut"),
    "instagram-agent-skill": ("instagram", "instagram", "video.instagram"),
    "VoiceStudio": ("voicestudio", "voicestudio", "video.voicestudio"),
    "video-use": ("video-use", "edit", "video.edit"),
    "rea-video": ("rea_video", "rea-video", "video.rea-video"),
    "yt-dlp": ("yt-dlp", "media", "video.media"),
    "TinyFish": ("tinyfish", "busca", "video.busca"),
}
RECEITAS = {
    "a": ("remake de um vídeo de referência", ["media fetch", "rea-video decompose", "rea-video review", "rea-video apply-review",
                                               "rea-video remake-plan"]),
    "b": ("vídeo curto a partir de um tema, com roteiro próprio", ["moneyprinter generate", "edit grade", "media subs", "media burn",
                                                                  "qc congelado"]),
    "c": ("corte vertical de vídeo longo", ["edit transcribe", "shorts plan", "shorts cut", "edit grade", "qc congelado"]),
    "d": ("dublagem ou tradução", ["edit transcribe", "voicestudio clone", "voicestudio tts", "media voice-track", "media replace-audio"]),
    "e": ("OpenMontage: pipelines, estimativa e ferramenta", ["montage pipelines", "montage tools", "montage estimate", "montage run-tool"]),
    "f": ("copy de Reels", ["instagram skills", "instagram run hookscore", "instagram run caption"]),
}


def _tabela() -> list:
    """The rows of the decision table (the header is `| Pedido | Trilha | Comando CLI | Tool MCP | Limites |`), as lists of cells."""
    linhas = TEXTO.splitlines()
    inicio = next(i for i, linha in enumerate(linhas) if linha.startswith("| Pedido"))
    corpo = []
    for linha in linhas[inicio + 2:]:
        if not linha.startswith("|"):
            break
        corpo.append([celula.strip() for celula in linha.strip().strip("|").split("|")])
    return corpo


def _secao(titulo: str) -> str:
    """The text of one `##` or `###` section: from its heading to the next heading of the same or a higher level."""
    m = re.search(rf"^(#{{2,3}}) {re.escape(titulo)}.*$", TEXTO, re.M)
    assert m, f"no heading {titulo!r}"
    nivel = m.group(1)
    fim = re.search(rf"^#{{1,{len(nivel)}}} ", TEXTO[m.end():], re.M)
    return TEXTO[m.end(): m.end() + fim.start()] if fim else TEXTO[m.end():]


def _recipe_section(letra: str) -> str:
    """The text of recipe (letra): up to the next `##` or `###` heading. A `# comment` inside a code block is not a heading."""
    m = re.search(rf"^### Receita \({letra}\).*$", TEXTO, re.M)
    assert m, f"no heading for recipe ({letra})"
    fim = re.search(r"^#{2,3} ", TEXTO[m.end():], re.M)
    return TEXTO[m.end(): m.end() + fim.start()] if fim else TEXTO[m.end():]


# --- the decision table ----------------------------------------------------------------------------------------------------------------


def test_a_tabela_tem_as_colunas_do_pedido_trilha_comando_mcp_e_limites():
    cabecalho = next(linha for linha in TEXTO.splitlines() if linha.startswith("| Pedido"))
    assert [celula.strip() for celula in cabecalho.strip("|").split("|")] == ["Pedido", "Trilha", "Comando CLI", "Tool MCP", "Limites"]


def test_as_doze_trilhas_do_registro_tem_uma_linha_cada():
    from simplicio_video import tools

    assert set(tools.TOOLS) == {registro for registro, _, _ in TRILHAS.values()}, "TRILHAS is not the registry of tools.py"
    assert len(TRILHAS) == 12
    linhas = _tabela()
    assert linhas and all(len(linha) == 5 for linha in linhas), "every row of the table has five cells (no `|` inside a cell)"
    for nome in TRILHAS:
        achadas = [linha for linha in linhas if linha[1].startswith(nome)]
        assert len(achadas) == 1, f"{nome}: expected one row in the table, found {len(achadas)}"


@pytest.mark.parametrize("nome", sorted(TRILHAS))
def test_cada_linha_de_trilha_cita_o_grupo_do_cli_e_a_tool_mcp(nome):
    from simplicio_video import mcp_server
    from simplicio_video.cli import build_parser

    _, grupo, mcp = TRILHAS[nome]
    grupos = {nome_do_grupo for acao in build_parser()._actions if isinstance(acao, argparse._SubParsersAction)
              for nome_do_grupo in acao.choices}
    assert grupo in grupos, f"{nome}: `simplicio-video {grupo}` is not a command of the CLI"
    linha = next(linha for linha in _tabela() if linha[1].startswith(nome))
    assert re.search(rf"\b{re.escape(grupo)}\b", linha[2]), f"{nome}: the CLI column does not name `{grupo}`"
    assert mcp in linha[3], f"{nome}: the MCP column does not name {mcp}"
    assert mcp in {t[0] for t in mcp_server.TOOLS}, f"{mcp} is not an MCP tool"


def test_a_tabela_cobre_o_fluxo_do_contrato():
    nucleo = next(linha for linha in _tabela() if "contrato" in linha[0].lower())
    for comando in ("init", "validate", "voice", "render", "run"):
        assert re.search(rf"\b{comando}\b", nucleo[2]), f"the contract row does not name `{comando}`"
        assert f"video.{comando}" in nucleo[3], f"the contract row does not name the MCP tool video.{comando}"


def test_a_tabela_traz_os_limites_de_cada_trilha_nao_so_os_comandos():
    for linha in _tabela():
        assert len(linha[4]) >= 25, f"{linha[1]}: the Limites column is empty or a stub"


# --- the recipes -------------------------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("letra", sorted(RECEITAS))
def test_cada_receita_existe_e_usa_os_comandos_dela(letra):
    _, marcas = RECEITAS[letra]
    secao = _recipe_section(letra)
    for marca in marcas:
        assert marca in secao, f"recipe ({letra}) does not use `{marca}`"


def test_as_seis_receitas_estao_na_ordem_do_pedido():
    titulos = re.findall(r"^### Receita \(([a-f])\)", TEXTO, re.M)
    assert titulos == list("abcdef")


@pytest.mark.parametrize("letra", sorted(RECEITAS))
def test_cada_receita_diz_o_que_roda_aqui(letra):
    assert re.search(r"local|aqui|no terminal|terminal", _recipe_section(letra)), f"recipe ({letra}) does not say what runs locally"


def _termos_de_autorizacao(texto: str) -> list:
    """TDD stub (commit 1 of the review): the real check comes with the fix. Returns the missing terms of the recipes."""
    return []


def test_os_termos_de_autorizacao_estao_nas_receitas():
    assert _termos_de_autorizacao(TEXTO) == []


def test_a_checagem_de_termos_pega_o_termo_que_falta():
    """Mutation: without `consentimento` in the text the check must say so (the old `A and B or C` said nothing)."""
    assert _termos_de_autorizacao(TEXTO.replace("consentimento", "")) == ["consentimento"]


def test_a_receita_de_remake_nao_copia_material_de_terceiro_e_usa_a_coleta():
    secao = _recipe_section("a")
    assert "forma" in secao and "coleta" in secao, "the reference inspires the form; the facts and footage come from the client's own sources"


# --- the rules and the terminal-only list ----------------------------------------------------------------------------------------------


@pytest.mark.parametrize("trecho", ["video.jobs", "não posta", "consentimento", "untrusted_", "fetch.json", "status --json", "setup",
                                    "--autorizo", "absolut", "--json"])
def test_as_regras_citam_o_que_o_agente_deve_fazer(trecho):
    assert trecho in " ".join(TEXTO.split()), f"the skill does not state {trecho!r}"


def test_o_que_so_roda_no_terminal_esta_listado_com_o_motivo():
    secao = _secao("Só no terminal")
    for motivo in ("gasta", "rede", "captura", "servidor", "publica"):
        assert motivo in secao, f"the terminal-only section does not say why, missing {motivo!r}"
    for comando in ("build", "remake-run", "transcribe-batch", "--vlm", "serve", "--yes"):
        assert comando in secao, f"the terminal-only section does not list {comando!r}"


def test_o_mcp_de_cada_trilha_e_o_do_contrato_aparecem_no_texto():
    for _, _, mcp in TRILHAS.values():
        assert mcp in TEXTO, f"{mcp} is missing from the skill"
    for mcp in ("video.init", "video.validate", "video.voice", "video.render", "video.run", "video.status", "video.tools", "video.jobs"):
        assert mcp in TEXTO, f"{mcp} is missing from the skill"


@pytest.mark.parametrize("comando", ["montage setup", "moneyprinter setup", "matchcut setup", "rea-video setup", "edit setup",
                                     "opencut clone", "toonflow clone", "instagram clone", "rea-video clone", "matchcut clone"])
def test_a_trilha_que_falta_tem_o_setup_ou_o_clone_no_terminal(comando):
    assert comando in TEXTO, f"`{comando}` is missing: the skill must say how to install a missing track, in the terminal"


def test_a_skill_nao_manda_o_agente_postar_nem_publicar():
    texto = " ".join(TEXTO.split())
    assert "não posta" in texto
    assert not re.search(r"\b(poste|publique|publicar agora|faça o upload)\b", texto, re.I), "the skill must never tell the agent to post"


# --- review of PR #181: texto que afirma o que o código faz, e o .gitignore -------------------------------------------------------------


def test_o_mcp_nao_diz_que_nao_instala_nada():
    """The MCP installs and downloads pinned tracks (edit setup, the clones of the default folder, media fetch, video.clone)."""
    assert "não instala nada" not in " ".join(TEXTO.split())


def test_quem_baixa_codigo_pelo_mcp_tem_secao_com_a_versao_fixada():
    secao = " ".join(_secao("Quem baixa código pelo MCP").split())
    for trecho in ("edit setup", "rea-video clone", "montage clone", "opencut clone", "toonflow clone", "moneyprinter clone",
                   "media fetch", "video.clone", "0.2.17", "yt-dlp", "fixad"):
        assert trecho in secao, f"a seção 'Quem baixa código pelo MCP' não cita {trecho!r}"


def test_a_receita_a_roda_o_decompose_sem_modelo_de_visao():
    """Outside the MCP nothing adds --no-vlm: a recipe that means "no third party" must say it."""
    assert "--no-vlm" in _recipe_section("a")


def test_o_fetch_json_vem_do_download_e_nao_do_decompose():
    passo1, _, _ = _recipe_section("a").partition("rea-video decompose")
    assert ".fetch.json" in passo1


def test_remake_run_nao_promete_custo():
    """`remake-run --dry-run` only lists the tasks and the parameters (upstream cli.py: 'só lista as tarefas e os parâmetros')."""
    texto = " ".join(TEXTO.split())
    assert "mostra as tarefas e o custo" not in texto
    assert "não calcula o custo" in texto


def test_nenhum_comando_envia_nada_e_falso():
    texto = " ".join(TEXTO.split())
    assert "envia nada" not in texto
    secao = " ".join(_secao("Só no terminal, e por quê").split())
    assert "TinyFish" in secao and "--vlm" in secao and "transcribe-batch" in secao


def test_hypit_exige_node_22_15():
    texto = " ".join(TEXTO.split())
    assert "Node 22.15" in texto and "Node 22 ou mais novo" not in texto


def test_a_regra_de_gasto_e_envio_pede_o_sim_do_usuario():
    regras = " ".join(_secao("Regras").split())
    assert "--yes" in regras and "--atualizar" in regras and "sim do usuário" in regras


def test_assemble_e_so_ffmpeg_e_a_justificativa_diz_isso():
    secao = " ".join(_secao("Só no terminal, e por quê").split())
    assert re.search(r"assemble[^\n]*ffmpeg", secao), "rea-video assemble only runs ffmpeg: say so, not 'runs code'"


def test_o_serve_do_moneyprinter_tem_host_e_o_do_toonflow_nao():
    secao = " ".join(_secao("Só no terminal, e por quê").split())
    assert "moneyprinter serve --host" in secao
    assert "toonflow serve --host" not in " ".join(TEXTO.split())


def test_os_caminhos_absolutos_so_sao_exigidos_na_saida():
    texto = " ".join(TEXTO.split())
    assert "todo caminho de mídia ou de `input` são absolutos" not in texto
    assert "resolvida contra o diretório" in texto


def test_o_gitignore_tem_a_skill_de_trilhas():
    from _comum import ROOT as RAIZ

    assert ".claude/skills/simplicio-video-trilhas/" in (RAIZ / ".gitignore").read_text(encoding="utf-8").splitlines()
