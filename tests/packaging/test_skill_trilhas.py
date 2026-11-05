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


def test_as_receitas_dizem_o_que_pede_autorizacao_chave_ou_consentimento():
    assert "--autorizo" in _recipe_section("a") and "coleta" in _recipe_section("a")
    assert "consentimento" in _recipe_section("d") and "API_KEY" in TEXTO or "chave" in TEXTO
    assert "--yes" in _recipe_section("e") or "--yes" in TEXTO


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
