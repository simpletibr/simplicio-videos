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


def _secao_da_receita(texto: str, letra: str) -> str:
    """The text of recipe (letra) in `texto`: up to the next `##` or `###` heading. A `# comment` inside a code block is not a heading."""
    m = re.search(rf"^### Receita \({letra}\).*$", texto, re.M)
    assert m, f"no heading for recipe ({letra})"
    fim = re.search(r"^#{2,3} ", texto[m.end():], re.M)
    return texto[m.end(): m.end() + fim.start()] if fim else texto[m.end():]


def _recipe_section(letra: str) -> str:
    return _secao_da_receita(TEXTO, letra)


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
    """The authorization terms that each recipe must carry, checked one by one (no `or` that lets the rest pass). Case does not matter:
    recipe (d) writes "Consentimento"."""
    faltas = []
    for letra, termo in (("a", "--autorizo"), ("a", "coleta"), ("d", "consentimento"), ("e", "--yes")):
        if termo.lower() not in _secao_da_receita(texto, letra).lower():
            faltas.append(termo)
    return faltas


def test_os_termos_de_autorizacao_estao_nas_receitas():
    assert _termos_de_autorizacao(TEXTO) == []


def test_a_checagem_de_termos_pega_o_termo_que_falta():
    """Mutation: without `consentimento` (in any case) the check must say so. The old `A and B or C` with C always true said nothing."""
    assert _termos_de_autorizacao(re.sub(r"consentimento", "", TEXTO, flags=re.I)) == ["consentimento"]


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


def _faltas_na_linha_decompose(texto: str) -> list:
    """The flags missing from the `rea-video decompose` command line of recipe (a) (the line itself, not a substring of the section)."""
    linhas = [linha for linha in _secao_da_receita(texto, "a").splitlines() if linha.startswith("simplicio-video rea-video decompose")]
    assert len(linhas) == 1, "recipe (a) must have exactly one `rea-video decompose` command line"
    return [flag for flag in ("--no-vlm",) if flag not in linhas[0].split()]


def test_a_linha_de_decompose_da_receita_a_tem_no_vlm():
    """The recipe's command line, not a substring of the section: `--no-vlm` on the decompose line itself."""
    assert _faltas_na_linha_decompose(TEXTO) == []


def test_a_checagem_da_linha_pega_o_no_vlm_que_falta():
    """Mutation: without `--no-vlm` on that line the check must name it (a section-wide substring would still pass)."""
    assert _faltas_na_linha_decompose(TEXTO.replace(" --no-vlm", "")) == ["--no-vlm"]


def test_a_versao_e_o_pin_por_padrao_com_update_e_status_qualificados():
    texto = " ".join(TEXTO.split())
    assert "nunca flutuante" not in texto
    assert "pin por padrão" in texto and "update --pin" in texto
    assert "tools --json" in texto and "effective_source" in texto


def test_quem_baixa_codigo_lista_hyperframes_edit_helpers_e_pesos():
    secao = " ".join(_secao("Quem baixa código pelo MCP").split())
    for trecho in ("hyperframes", "0.8.97", "video.render", "video.run", "setup.sh", "faster-whisper", "primeiro uso"):
        assert trecho in secao, f"'Quem baixa código pelo MCP' does not list {trecho!r}"
    assert "fora dessa lista" not in " ".join(TEXTO.split())


def test_a_primeira_consulta_gasta_uma_chamada_e_envia_o_texto():
    texto = " ".join(TEXTO.split())
    assert "primeira consulta" in texto and "gasta 1 chamada" in texto and "envia o texto" in texto
    assert "sem o sim do usuário, não pesquise" in texto


def test_media_sobrescreve_o_o_nao_arquivo_novo():
    texto = " ".join(TEXTO.split())
    assert "cada saída é arquivo novo" not in texto
    linha = next(linha for linha in _tabela() if linha[1].startswith("núcleo de mídia"))
    assert "sobrescreve" in linha[4], "the media row must say that -o overwrites an existing file"


def test_a_regra_de_gasto_e_envio_nomeia_cada_comando():
    regras = " ".join(_secao("Regras").split())
    for trecho in ("swap run", "--autorizo", "voice --provider gemini", "--backend kaggle", "colab", "Edge", "openverse search",
                   "sim do usuário"):
        assert trecho in regras, f"the spend-and-send rule does not name {trecho!r}"


def test_exit_1_com_traceback_e_falha_nao_ponto_de_revisao():
    secao = _secao_da_receita(TEXTO, "f")
    assert "Traceback" in secao and "erros" in secao
    assert "não uma falha" not in " ".join(TEXTO.split())


def test_assemble_roda_localmente_com_ffmpeg_e_opencv():
    """The upstream assemble uses ffmpeg AND OpenCV (cv2): the text must not promise ffmpeg alone."""
    secao = " ".join(_secao("Só no terminal, e por quê").split())
    linha = next(linha for linha in secao.split("- ") if "assemble" in linha)
    for trecho in ("localmente", "ffmpeg", "OpenCV"):
        assert trecho in linha, f"the assemble bullet does not say {trecho!r}"


def test_a_receita_d_avisa_que_o_voice_track_acelera_ate_o_limite():
    secao = _secao_da_receita(TEXTO, "d")
    assert "--max-stretch" in secao and "1,25" in secao


def test_o_setup_do_video_use_so_avisa_o_faster_whisper():
    assert "só avisa" in " ".join(TEXTO.split())


def test_o_hypit_usa_o_path_antes_do_pin_e_o_node_so_e_checado_no_status():
    linha = next(linha for linha in _secao("Trilha que falta").splitlines() if linha.startswith("- **Hypit:**"))
    assert "PATH" in linha and "vence" in linha
    assert "clone status" in linha and "22.15" in linha


ABSOLUTOS_FALSOS = ("nunca flutuante", "a voz nunca é acelerada", "nenhum quadro vai a terceiro", "envia nada", "fora dessa lista",
                    "não uma falha", "cada saída é arquivo novo", "só medem o texto", "Nada de chave", "Sem chave e sem LLM",
                    "O motor nunca instala o TinyFish", "nunca a imprime", "nunca são instrução", "sempre na versão fixada",
                    "não instala nada", "Chave nunca em argumento", "nunca roda", "Nada é publicado. O motor gera o arquivo e para nele")


def test_as_afirmacoes_absolutas_que_eram_falsas_sairam():
    texto = " ".join(TEXTO.split())
    presentes = [trecho for trecho in ABSOLUTOS_FALSOS if trecho in texto]
    assert not presentes, f"absolute claims that the code contradicts are still in the skill: {presentes}"


# --- review 4 (follow-up of the merged PR #181): texto que o código contradiz ---------------------------------------------------------


def test_quem_baixa_codigo_inclui_o_voice_com_faster_whisper_e_a_condicao():
    """voice, video.voice and video.run align the words with faster-whisper ("small") when SIMPLICIO_STT_PY has faster_whisper, and
    download the model on first use (words.py: MODEL = "small"; voice.py calls the alignment)."""
    secao = " ".join(_secao("Quem baixa código pelo MCP").split())
    for trecho in ("SIMPLICIO_STT_PY", "faster_whisper", "video.voice", "video.run", "small", "Hugging Face"):
        assert trecho in secao, f"'Quem baixa código pelo MCP' does not say {trecho!r}"


def test_a_linha_de_media_diz_que_o_voicestudio_so_recusa_pelo_mcp():
    linha = next(linha for linha in _tabela() if linha[1].startswith("núcleo de mídia"))
    assert "sobrescreve" in linha[4]
    assert "só pelo MCP" in linha[4] and "no terminal" in linha[4], "the voicestudio refusal of an existing --out is MCP-only"


def test_o_pedido_de_download_fora_do_pin_nao_contradiz_a_secao_de_mcp():
    texto = " ".join(TEXTO.split())
    assert "baixa código de terceiros, abre navegador ou publica" not in texto
    assert "fora do pin do motor" in texto


def test_o_swap_run_pede_autorizo_e_yes_pelo_jobs():
    texto = " ".join(TEXTO.split())
    assert "jobs submit swap-run --autorizo --yes" in texto
    assert "jobs submit swap-run --yes" not in texto
    assert "jobs submit swap-run --autorizo --yes" in " ".join(_secao("Regras").split())


def test_o_render_colab_manual_nao_entra_na_regra_de_envio():
    """`render --backend colab` (the notebook, by hand) sends nothing through the engine: only kaggle and colab-cli do."""
    regras = " ".join(_secao("Regras").split())
    assert "`colab-cli`" in regras and "ou `colab`" not in regras


def test_o_toonflow_com_docker_publica_so_em_127_0_0_1():
    linha = next(linha for linha in _tabela() if linha[1].startswith("Toonflow"))
    assert "com `--lan`" in linha[4] and "0.0.0.0" in linha[4]
    assert "127.0.0.1" in linha[4] and "compose" in linha[4]


def test_o_openverse_search_consulta_a_api_so_quando_a_consulta_nao_esta_no_cache():
    regras = " ".join(_secao("Regras").split())
    assert "openverse search" in regras and "quando a consulta não está no cache" in regras
