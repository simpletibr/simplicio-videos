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
import json
import os
import re
from pathlib import Path

import pytest

from _comum import ROOT, executa, instantanea
from simplicio_video.cli import main
from simplicio_video.commands import doctor as doctor_cmd

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


def _pin(nome: str) -> str:
    """The version the code pins for the tool `nome` (tools.TOOLS): the single source the skill must follow."""
    from simplicio_video import tools

    return tools.TOOLS[nome].ref


def _versao_hyperframes() -> str:
    from simplicio_video import HYPERFRAMES

    return HYPERFRAMES.rpartition("@")[2]


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
                   "media fetch", "video.clone", _pin("hypit"), "yt-dlp", "fixad"):
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
    for trecho in ("hyperframes", _versao_hyperframes(), "video.render", "video.run", "setup.sh", "faster-whisper", "primeiro uso"):
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
    for trecho in ("jobs submit swap-run --autorizo --yes", "--autorizo", "voice --provider gemini", "--backend kaggle", "colab-cli", "Edge", "openverse search",
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


# --- review of PR #185: the pins the skill cites come from the code, never from a literal ------------------------------------------------

# a version (X.Y.Z, also a calendar one) or a commit sha (7 to 40 hex chars with a digit) that is not part of an IP address or a longer number
VERSAO = re.compile(r"(?<![\w.])(?:\d+\.\d+\.\d+|(?=[0-9a-f]*\d)(?=[0-9a-f]*[a-f])[0-9a-f]{7,40})(?![\w]|\.\d)")


def _marcas_das_trilhas() -> dict:
    """tool (tools.TOOLS, plus the HyperFrames of the render) -> the words that name it in the skill: its registry name, the name the
    table uses and the package or repository it is installed from. Derived from the code and from TRILHAS, never typed twice."""
    from simplicio_video import tools

    marcas = {}
    for nome_skill, (registro, _, _) in TRILHAS.items():
        t = tools.TOOLS[registro]
        marcas[registro] = {nome_skill, registro, t.source.rstrip("/").rpartition("/")[2]} - {"clone"}
    marcas["hyperframes"] = {"HyperFrames", "hyperframes"}
    return marcas


def _refs_do_codigo() -> dict:
    """tool -> every spelling of its pin the skill may use: the version, or the full commit and its short forms (7 to 12 chars)."""
    refs = {nome: {_pin(nome)} for nome in _marcas_das_trilhas() if nome != "hyperframes"}
    for nome, ref in list(refs.items()):
        (valor,) = ref
        if re.fullmatch(r"[0-9a-f]{40}", valor):
            refs[nome] = {valor[:n] for n in range(7, 41)}
    refs["hyperframes"] = {_versao_hyperframes()}
    return refs


def _citacoes(texto: str) -> list:
    """Every version or sha the skill writes, as (token, tools the same clause names, clause). A clause is a table cell or the text up to
    the next `. ` or `; `, so that one tool's pin is not read from another tool's clause."""
    marcas = _marcas_das_trilhas()
    achados = []
    for linha in texto.splitlines():
        for oracao in re.split(r"\| |[.;] ", linha):
            for token in VERSAO.findall(oracao):
                nomes = {nome for nome, palavras in marcas.items() if any(re.search(rf"(?<![\w-]){re.escape(p)}(?![\w-])", oracao) for p in palavras)}
                achados.append((token, nomes, oracao.strip()[:90]))
    return achados


def _versoes_erradas(texto: str, refs: dict) -> list:
    """Every cited version that is not the pin of a track named in its own clause (a version next to no track name is also wrong: nothing
    says whose it is), plus each tool whose pin the skill never cites although `OBRIGATORIOS` says it must."""
    erros = []
    citados = _citacoes(texto)
    for token, nomes, oracao in citados:
        if not nomes:
            erros.append(f"{token}: no track named in its clause, so it is nobody's pin ({oracao!r})")
        elif not any(token in refs[nome] for nome in nomes):
            erros.append(f"{token}: not the pin of {sorted(nomes)} ({', '.join(sorted(refs[n])[-1] for n in nomes)}) ({oracao!r})")
    for nome in OBRIGATORIOS:
        if not any(nome in nomes and token in refs[nome] for token, nomes, _ in citados):
            erros.append(f"{nome}: the skill cites no pin")
    return erros


OBRIGATORIOS = ("hypit", "tinyfish", "yt-dlp", "hyperframes")


def test_toda_versao_que_a_skill_cita_e_o_pin_da_trilha_do_codigo():
    """Hypit, TinyFish, yt-dlp, HyperFrames and any other pin: the version in the text is `tools.TOOLS[...].ref`, whatever the word before it
    ("pin", "versão" or nothing). It was "0.2.17" while the code pinned 0.3.1."""
    assert _versoes_erradas(TEXTO, _refs_do_codigo()) == []


def test_a_skill_cita_o_pin_do_hypit_nos_dois_lugares_e_o_do_tinyfish():
    refs = _refs_do_codigo()
    citados = _citacoes(TEXTO)
    assert len([c for c in citados if "hypit" in c[1] and c[0] in refs["hypit"]]) >= 2, "`Quem baixa código pelo MCP` and `Trilha que falta`"
    assert any("tinyfish" in c[1] and c[0] in refs["tinyfish"] for c in citados)


def test_a_checagem_de_pin_fica_vermelha_quando_o_tools_py_muda():
    """Mutation: if tools.py pinned other versions, the skill as it stands must fail on every cited one."""
    refs = {nome: {"9.9.9"} for nome in _refs_do_codigo()}
    erros = _versoes_erradas(TEXTO, refs)
    assert len(erros) >= 6 and all("9.9.9" in e or "cites no pin" in e for e in erros)


def test_a_checagem_de_pin_pega_a_versao_sem_a_palavra_pin():
    """A new pin written without `pin` or `versão` before it cannot lie either."""
    refs = _refs_do_codigo()
    assert _versoes_erradas(TEXTO.replace("no pin 0.3.1 por npx", "no 0.3.0 por npx"), refs), "a wrong Hypit version after any other word"
    assert _versoes_erradas(TEXTO.replace("(versão 0.57.0 testada,", "(0.56.0 testada,"), refs)
    assert _versoes_erradas(TEXTO.replace("OpenCut (MIT, opencut-classic)", "OpenCut 1.2.3 (MIT, opencut-classic)"), refs), "a version for a track that has a pin"
    assert _versoes_erradas(TEXTO + "\nA versão 4.5.6 funciona.\n", refs), "a version next to no track at all"
    sha = _pin("opencut")
    assert _versoes_erradas(TEXTO + f"\n- **OpenCut:** o commit {sha[:7]}.\n", refs) == []
    assert _versoes_erradas(TEXTO + f"\n- **OpenCut:** o commit {sha[:6]}0.\n", refs), "a sha that is not the pin"


def test_a_checagem_de_pin_nao_aceita_a_skill_sem_pin():
    assert _versoes_erradas(VERSAO.sub("", TEXTO), _refs_do_codigo())


def test_o_ip_e_o_node_nao_sao_pin():
    assert VERSAO.findall("escuta em 0.0.0.0:3000 e 127.0.0.1:3900; Node 22.15 e Python 3.11") == []


# --- review of PR #185: the media row says what the code does with an existing -o ----------------------------------------------------

COPIAS = [pytest.param(ROOT / "skills" / "simplicio-video-trilhas" / "SKILL.md", id="skills"),
          pytest.param(SKILL, id="data-skills")]


def _linha_midia(texto: str) -> str:
    linhas = texto.splitlines()
    inicio = next(i for i, linha in enumerate(linhas) if linha.startswith("| Pedido"))
    return next(linha for linha in linhas[inicio + 2:] if "núcleo de mídia" in linha)


def _faltas_na_linha_de_midia(texto: str) -> list:
    """What the media row must say about an existing `-o`, one by one (main's description: every subcommand writes to -o, an existing file
    is overwritten, `fetch` never overwrites, so give it a new path; download.py refuses the MP4 and the .fetch.json)."""
    linha = " ".join(_linha_midia(texto).split())
    faltas = []
    if not re.search(r"`media` sobrescreve o `-o` que já existe", linha):
        faltas.append("media sobrescreve o -o")
    if not re.search(r"o `fetch` nunca sobrescreve", linha):
        faltas.append("fetch nunca sobrescreve")
    if ".fetch.json" not in linha:
        faltas.append(".fetch.json")
    if re.search(r"exceto o `fetch --info", linha):
        faltas.append("(false) only fetch --info refuses")
    return faltas


@pytest.mark.parametrize("caminho", COPIAS)
def test_a_linha_de_midia_diz_o_que_o_codigo_faz_com_um_o_que_ja_existe(caminho):
    assert _faltas_na_linha_de_midia(caminho.read_text(encoding="utf-8")) == []


def test_as_duas_copias_da_skill_sao_identicas():
    assert COPIAS[0].values[0].read_bytes() == COPIAS[1].values[0].read_bytes()


def test_a_checagem_da_linha_de_midia_pega_a_excecao_do_fetch_que_falta():
    """Mutation: take the fetch exception out of the row (as it can be taken out of the mirror) and the check must name it."""
    sem = TEXTO.replace("o `fetch` nunca sobrescreve", "o `fetch` também sobrescreve")
    assert "fetch nunca sobrescreve" in _faltas_na_linha_de_midia(sem)
    sem = TEXTO.replace("`media` sobrescreve o `-o` que já existe", "`media` grava o `-o`")
    assert "media sobrescreve o -o" in _faltas_na_linha_de_midia(sem)


@pytest.mark.parametrize("caminho", COPIAS)
def test_o_voicestudio_no_terminal_nao_promete_alem_do_que_o_codigo_mostra(caminho):
    """voicestudio.py `speak` has no existence check on the terminal path (write_bytes); it was not measured against the real app."""
    linha = " ".join(_linha_midia(caminho.read_text(encoding="utf-8")).split())
    assert "voicestudio tts -o` sobrescreve" not in linha
    assert "não confere se o arquivo existe" in linha and "app simulado" in linha


# --- second review of PR #185: what a clone needs, what Hypit 0.3.1 accepts, the doctor ------------------------------------------------


def _texto(caminho) -> str:
    return " ".join(caminho.read_text(encoding="utf-8").split())


def _clone_pede_bun(texto: str) -> list:
    """The clauses that say a `clone` needs Bun. Neither `opencut clone` nor `toonflow clone` runs Bun (tools.install: git only); `opencut dev`
    and `toonflow serve` do."""
    return [oracao for oracao in re.split(r"(?<=\)) |[.;] ", texto) if re.search(r"\bclone\b[^.;]*(?<!não )precisa de Bun", oracao)]


@pytest.mark.parametrize("caminho", COPIAS)
def test_o_clone_do_opencut_e_do_toonflow_nao_pede_bun(caminho):
    texto = _texto(caminho)
    assert _clone_pede_bun(texto) == []
    secao = " ".join(_secao_do("Trilha que falta", caminho.read_text(encoding="utf-8")).split())
    for trilha in ("OpenCut", "Toonflow"):
        linha = next(linha for linha in secao.split("- **") if linha.startswith(trilha))
        assert "o clone não precisa de Bun" in linha, f"{trilha}: the clone needs git only"
        assert ("`opencut dev` precisa de Bun" if trilha == "OpenCut" else "`toonflow serve --lan` precisa de Bun") in linha, f"{trilha}: say which command needs Bun"


def _secao_do(titulo: str, texto: str) -> str:
    m = re.search(rf"^(#{{2,3}}) {re.escape(titulo)}.*$", texto, re.M)
    fim = re.search(r"^#{1,3} ", texto[m.end():], re.M)
    return texto[m.end(): m.end() + fim.start()] if fim else texto[m.end():]


def test_a_checagem_do_bun_pega_o_clone_que_pede_bun():
    """Mutation: the old wording (the clone needs Bun) must be caught, in either spelling."""
    assert _clone_pede_bun("- **OpenCut:** `simplicio-video opencut clone` (precisa de Bun).")
    assert _clone_pede_bun("- **Toonflow:** `simplicio-video toonflow clone` (precisa de Bun).")
    assert not _clone_pede_bun("`opencut clone` (o clone não precisa de Bun; dev precisa).")


def test_o_bun_e_so_do_dev_e_do_serve_na_tabela():
    for nome, verbo in (("OpenCut", "dev"), ("Toonflow", "serve")):
        linha = " ".join(next(linha for linha in _tabela() if linha[1].startswith(nome))[4].split())
        assert "Bun" in linha and verbo in linha
    assert "o `--lan` precisa de Bun e o `--docker`, de Docker" in next(l for l in _tabela() if l[1].startswith("Toonflow"))[4]


@pytest.mark.parametrize("caminho", COPIAS)
def test_a_linha_do_hypit_nao_lista_o_que_o_pin_nao_aceita(caminho):
    """On the pinned Hypit `packages` and `measure` are "Unknown help topic" (`npx @hypit/hypit@<pin> packages --help`): not verbs to list as
    terminal-only. The MCP refuses them; the terminal gives the upstream error."""
    texto = caminho.read_text(encoding="utf-8")
    linhas = texto.splitlines()
    inicio = next(i for i, linha in enumerate(linhas) if linha.startswith("| Pedido"))
    linha = " ".join(next(linha for linha in linhas[inicio + 2:] if "| Hypit" in linha).split())
    limites = linha.strip("|").split("|")[-1]
    assert "o MCP recusa `packages` e `measure`" in limites and "não foi conferido" in limites
    assert re.search(r"`studio`, `auth`, `runtime`, `capture` e `transcribe`", limites), "the terminal-only verbs that do exist in the pin"
    assert not re.search(r"`runtime`, `packages`|`packages`, `capture`|e `measure`,? ", limites.replace("`packages` e `measure` não existem", ""))
    assert "MCP" in limites


def test_o_codigo_de_saida_1_e_do_terminal_e_o_ok_true_e_do_mcp():
    secao = " ".join(_secao_da_receita(TEXTO, "f").split())
    assert "Código de saída 1 conta como resultado (`ok: true`)" not in secao
    assert "no terminal o processo sai com 1" in secao and "no MCP" in secao and "`ok: true`" in secao and "`codigo_saida`" in secao


def test_a_skill_documenta_o_doctor_trilhas_como_ele_e():
    """`doctor trilhas` is offline unless `--online`, has `--json` and the MCP takes it as `video.doctor` with args `trilhas`; the doctor
    itself points at it as the fix command, so the skill has to say what it is."""
    secao = " ".join(_secao("Ver o que falta: doctor trilhas").split())
    for trecho in ("simplicio-video doctor trilhas", "--json", "--online", "sem rede", "video.doctor", 'args="trilhas"', "simplicio.doctor-trilhas/v1",
                   "pendência", "não instala"):
        assert trecho in secao, f"the doctor trilhas section does not say {trecho!r}"
    assert "doctor trilhas" in " ".join(_secao("Antes de começar").split())


def test_o_voicestudio_nao_diz_que_nao_ha_setup_sem_explicar_o_doctor():
    """`doctor trilhas` says "não instalada" for VoiceStudio and suggests the git clone of the pinned source; the skill must reconcile that
    with "open the app" (tools.py: the app has its own installer, the clone is the source checkout)."""
    linha = " ".join(next(l for l in _secao("Trilha que falta").splitlines() if l.startswith("- **VoiceStudio:**")).split())
    assert "Não há setup do motor" not in linha
    assert "instalador próprio" in linha and "doctor trilhas" in linha and "não instalada" in linha and "git clone" in linha
    assert "código-fonte" in linha and "127.0.0.1:3900" in linha


# --- third review of PR #185: the section about `doctor trilhas`, checked against what the command really does -------------------------


def _secao_doctor() -> str:
    return " ".join(_secao("Ver o que falta: doctor trilhas").split())


def _casa_vazia(tmp_path, monkeypatch):
    """A temp HOME, offline, and the data dir the conftest gives every test (the engine writes nothing outside them)."""
    casa = tmp_path / "casa"
    casa.mkdir()
    monkeypatch.setenv("HOME", str(casa))
    monkeypatch.setenv("SIMPLICIO_OFFLINE", "1")
    dados = Path(os.environ["SIMPLICIO_VIDEO_DATA"])
    monkeypatch.setenv("SIMPLICIO_TOOLS_DIR", str(dados / "tools"))  # where the checkouts of the tracks are looked for
    monkeypatch.setenv("VIDEO_USE_DIR", str(dados / "video-use"))
    monkeypatch.setattr(doctor_cmd, "porta_livre", lambda porta, *a, **kw: True)  # pytest-socket blocks the bind of the ports check
    return casa, dados


def test_o_online_do_doctor_trilhas_nao_regrava_o_cache_do_update():
    """Measured: `doctor trilhas --online` asks git ls-remote, npm view and PyPI and writes no update-check.json (npm writes its own cache
    in ~/.npm). The section said it rewrote the cache of `update --check`: that was false."""
    secao = _secao_doctor()
    assert "regrava" not in secao and "update-check" not in secao
    assert "cache do `update --check`" not in secao
    assert "não grava nada no diretório de dados do motor" in secao and "~/.npm" in secao


def test_a_secao_do_doctor_trilhas_descreve_as_falhas_como_o_codigo_as_da():
    """`fail` comes from a broken install and also from a changed pinned file (matchcut) and from a venv without its program. The section
    must not say only a broken install fails."""
    secao = _secao_doctor()
    assert "só instalação quebrada falha" not in secao
    assert "arquivo fixado alterado" in secao and "venv sem o programa" in secao


def test_o_doctor_trilhas_offline_tem_o_schema_e_as_chaves_que_a_skill_cita(tmp_path, monkeypatch, capsys):
    casa, dados = _casa_vazia(tmp_path, monkeypatch)
    antes, antes_dados = instantanea(casa), instantanea(dados)
    rc, out, err = executa(["doctor", "trilhas", "--json"], capsys, main)
    assert rc == 0, "nothing installed is a warning: the exit code stays 0"
    doc = json.loads(out)
    assert doc["schema"] == "simplicio.doctor-trilhas/v1" and "status" in doc and "tracks" in doc
    assert len(doc["tracks"]) == 12 and all(isinstance(t["checks"], list) and t["checks"] for t in doc["tracks"])
    assert doc["status"] == "warn" and doc["online"] is False
    assert instantanea(casa) == antes and instantanea(dados) == antes_dados, "offline: nothing is written"


def test_o_doctor_trilhas_com_instalacao_quebrada_sai_com_1_e_o_doctor_tambem(tmp_path, monkeypatch, capsys):
    casa, dados = _casa_vazia(tmp_path, monkeypatch)
    pasta = dados / "tools" / "opencut"
    pasta.mkdir(parents=True)
    (pasta / "README.md").write_text("sobra de um clone interrompido\n", encoding="utf-8")
    rc, out, err = executa(["doctor", "trilhas"], capsys, main)
    assert rc == 1 and out.splitlines()[0] == "simplicio-video doctor trilhas: fail"
    rc, out, err = executa(["doctor"], capsys, main)
    assert rc == 1, "a broken optional track makes `doctor` exit 1"


def test_o_doctor_sem_argumento_traz_uma_linha_trilhas(tmp_path, monkeypatch, capsys):
    _casa_vazia(tmp_path, monkeypatch)
    rc, out, err = executa(["doctor"], capsys, main)
    assert rc == 0
    assert len([linha for linha in out.splitlines() if re.match(r"^\s+\w+\s+trilhas\s", linha)]) == 1, out


def test_o_video_doctor_do_mcp_com_args_trilhas_devolve_o_schema(tmp_path, monkeypatch):
    from simplicio_video import mcp_server

    _casa_vazia(tmp_path, monkeypatch)
    r = mcp_server.video_doctor(args="trilhas")
    assert r["ok"] is True and r["result"]["schema"] == "simplicio.doctor-trilhas/v1" and len(r["result"]["tracks"]) == 12
    assert "video.doctor(args=\"trilhas\")" in TEXTO and 'args="trilhas"' in _secao_doctor()


def test_tools_e_status_nao_instalam_nem_gravam(tmp_path, monkeypatch, capsys):
    """The table says `tools` downloads and installs nothing; the status line of `status` is read only too."""
    casa, dados = _casa_vazia(tmp_path, monkeypatch)
    antes, antes_dados = instantanea(casa), instantanea(dados)
    assert executa(["tools", "--json"], capsys, main)[0] == 0
    assert executa(["status", "--json"], capsys, main)[0] == 0
    assert instantanea(casa) == antes and instantanea(dados) == antes_dados


def test_o_mcp_recusa_packages_e_measure_do_hypit():
    from simplicio_video import mcp_server

    for verbo in ("packages", "measure"):
        r = mcp_server.video_clone(args=verbo)
        assert r["ok"] is False and "terminal" in r.get("error", ""), verbo


@pytest.mark.parametrize("caminho", COPIAS)
def test_a_linha_do_hypit_nao_afirma_que_o_pin_nao_tem_packages_nem_measure(caminho):
    """Not confirmed here: the `npx` run of the pinned package was refused in the session that checked it. The engine's own refusal texts
    call them terminal verbs (`packages` installs third-party code, `measure` uses providers), so the skill must not state "não existem"."""
    linhas = caminho.read_text(encoding="utf-8").splitlines()
    inicio = next(i for i, linha in enumerate(linhas) if linha.startswith("| Pedido"))
    limites = " ".join(next(linha for linha in linhas[inicio + 2:] if "| Hypit" in linha).split()).strip("|").split("|")[-1]
    assert "não existem" not in limites and "Unknown help topic" not in limites
    assert "o MCP recusa `packages` e `measure`" in limites and "não foi conferido" in limites


@pytest.mark.parametrize("caminho", COPIAS)
def test_o_voicestudio_nao_diz_que_o_motor_nao_tem_clone_quando_o_clone_clona_voz(caminho):
    """`simplicio-video voicestudio clone` exists and clones a voice; the line must not say the engine has no `clone` at all."""
    linha = " ".join(next(l for l in _secao_do("Trilha que falta", caminho.read_text(encoding="utf-8")).splitlines()
                          if l.startswith("- **VoiceStudio:**")).split())
    assert "não tem `clone` nem `setup` dele" not in linha
    assert "`voicestudio clone` clona uma voz" in linha and "não o app" in linha
