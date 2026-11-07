"""scripts/gen_reference.py --out DIR: writes docs/reference/*.md from the code, deterministically and completely.

Contract under test: the five files below appear in DIR; two runs (and a run from another cwd) give identical bytes;
every subcommand of simplicio_video.cli.build_parser() and each of its long options appear in cli.md; every MCP
tool of mcp_server.TOOLS appears in mcp-tools.md; every *.schema.json under src/simplicio_video/data/ appears in
schemas.md; every env var the package reads appears in config.md; events.md says it is empty.
"""
from __future__ import annotations

import argparse
import ast
import importlib.util
import json
import re

import pytest

from _docs import ROOT, run_script

REFERENCE_FILES = {"cli.md", "mcp-tools.md", "schemas.md", "events.md", "config.md"}
PKG = ROOT / "src" / "simplicio_video"
ENV_READ = re.compile(
    r"""(?:environ(?:\.get)?|getenv)\(\s*["']([A-Z][A-Z0-9_]+)["']|environ\[\s*["']([A-Z][A-Z0-9_]+)["']\]"""
)


def _gen(out):
    result = run_script("gen_reference.py", "--out", str(out))
    assert result.returncode == 0, result.stdout + result.stderr
    return out


@pytest.fixture(scope="module")
def gerado(tmp_path_factory):
    """Uma geração só para o módulo: os testes que só leem a saída não pagam o gerador de novo (são ~3 s cada)."""
    return _gen(tmp_path_factory.mktemp("gerado") / "ref")


def _read(out, name):
    return (out / name).read_text(encoding="utf-8")


def _subcommands():
    from simplicio_video.cli import build_parser

    parser = build_parser()
    action = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
    return action.choices


def test_gera_os_cinco_arquivos(gerado):
    assert {p.name for p in gerado.iterdir()} == REFERENCE_FILES


def test_duas_execucoes_geram_bytes_iguais(gerado, tmp_path):
    # Duas execuções: a do módulo (`gerado`) e uma de outro cwd, que é também uma segunda execução independente.
    other_cwd = tmp_path / "de-outro-cwd"
    other_cwd.mkdir()
    run_script("gen_reference.py", "--out", str(tmp_path / "c"), cwd=other_cwd)
    for name in sorted(REFERENCE_FILES):
        assert (gerado / name).read_bytes() == (tmp_path / "c" / name).read_bytes(), f"{name} muda entre execuções ou depende do cwd"


def test_cli_md_tem_todo_subcomando_e_toda_opcao_longa(gerado):
    text = _read(gerado, "cli.md")
    subcommands = _subcommands()
    assert subcommands, "build_parser() não tem subcomandos"
    for name, sub in subcommands.items():
        assert f"simplicio-video {name}" in text, f"subcomando {name!r} ausente de cli.md"
        for opt in sub._option_string_actions:
            if opt.startswith("--") and opt != "--help":
                assert opt in text, f"opção {name} {opt} ausente de cli.md (o help real não entrou)"


def test_mcp_tools_md_tem_toda_tool(gerado):
    from simplicio_video.mcp_server import TOOLS

    text = _read(gerado, "mcp-tools.md")
    for name, _fn, _desc in TOOLS:
        assert name in text, f"tool MCP {name!r} ausente de mcp-tools.md"


def test_schemas_md_tem_todo_schema_do_pacote(gerado):
    text = _read(gerado, "schemas.md")
    schemas = sorted((PKG / "data").rglob("*.schema.json"))
    assert schemas, "não achei schemas em src/simplicio_video/data/"
    for path in schemas:
        assert path.name in text, f"{path.name} ausente de schemas.md"


def test_config_md_tem_toda_variavel_lida_pelo_codigo(gerado):
    read = set()
    for path in PKG.rglob("*.py"):
        for match in ENV_READ.finditer(path.read_text(encoding="utf-8")):
            read.add(match.group(1) or match.group(2))
    read.discard("PATH")  # variável do sistema, não do produto
    assert "GEMINI_API_KEY" in read and "SIMPLICIO_OFFLINE" in read, "o scan não achou variáveis conhecidas"
    text = _read(gerado, "config.md")
    missing = sorted(name for name in read if name not in text)
    assert not missing, f"variáveis lidas pelo código ausentes de config.md: {missing}"


def test_config_md_descreve_o_rotulo_de_procedencia_dos_jobs(gerado):
    """SIMPLICIO_JOB_ORIGIN is set by the jobs runner ('terminal' or 'mcp'); the row must say so and say it is no access control."""
    linha = next(l for l in _read(gerado, "config.md").splitlines() if l.startswith("| `SIMPLICIO_JOB_ORIGIN`"))
    assert "sem descrição" not in linha
    assert "terminal" in linha and "mcp" in linha and "jobs.py" in linha
    assert "controle de acesso" in linha


def test_eventos_vazio_com_aviso(gerado):
    assert "ainda não há eventos" in _read(gerado, "events.md").lower()


def test_cli_md_nao_depende_da_versao_do_python(gerado):
    """O argparse do 3.12 e o do 3.13 calculam a coluna de ajuda dos subcomandos de formas diferentes; o gerador fixa uma só.
    O cli.md gerado por qualquer Python suportado tem de ser igual ao commitado."""
    assert _read(gerado, "cli.md") == (ROOT / "docs" / "reference" / "cli.md").read_text(encoding="utf-8")


# --------------------------------------------------------------------------------------------------- blocos `fatos` e `mapa-modulos`
# The counts, pins and the module map that README, AGENTS, PYPI, esteira and docs/host used to carry by hand come from the code:
# `gen_reference.py` writes them between `<!-- BEGIN GENERATED: fatos -->` / `<!-- BEGIN GENERATED: mapa-modulos -->` and
# `<!-- END GENERATED -->`, and `--check` fails when one is stale. The expected values below are recomputed here from the code
# and the data files, independently of the generator.
FATOS_ARQUIVOS = {
    # file: (language of the labels, the facts that file carries; "pins" is the table of pins per track)
    "README.md": ("en", ("tools", "trilhas", "templates", "padroes", "hyperframes", "hosts", "hosts_globais", "skills", "pins")),
    "README.pt-BR.md": ("pt", ("tools", "trilhas", "templates", "padroes", "hyperframes", "hosts", "hosts_globais", "skills", "pins")),
    "PYPI.md": ("pt", ("tools", "trilhas", "hyperframes", "hosts")),
    "AGENTS.md": ("pt", ("tools", "trilhas", "templates", "padroes", "hyperframes", "hosts", "hosts_globais", "skills")),
    "docs/esteira.md": ("pt", ("templates", "padroes", "hyperframes")),
    "docs/host/README.md": ("pt", ("hosts", "hosts_globais", "skills")),
}
ROTULOS = {
    "en": {"tools": "MCP tools (`video.*`)", "trilhas": "External tracks", "templates": "Templates", "padroes": "Motion patterns",
           "hyperframes": "HyperFrames", "hosts": "Agent hosts (`install`)",
           "hosts_globais": "Hosts with a global skills folder (`install --global`)", "skills": "Skills for agents"},
    "pt": {"tools": "Tools MCP (`video.*`)", "trilhas": "Trilhas externas", "templates": "Templates", "padroes": "Padrões de motion",
           "hyperframes": "HyperFrames", "hosts": "Hosts de agente (`install`)",
           "hosts_globais": "Hosts com pasta global de skills (`install --global`)", "skills": "Skills para agentes"},
}


def _gen_module():
    spec = importlib.util.spec_from_file_location("gen_reference_sob_teste", ROOT / "scripts" / "gen_reference.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _bloco(rel, secao):
    texto = (ROOT / rel).read_text(encoding="utf-8")
    begin = f"<!-- BEGIN GENERATED: {secao} -->\n"
    assert texto.count(begin) == 1, f"{rel}: o bloco {secao!r} está ausente ou repetido"
    corpo = texto[texto.index(begin) + len(begin):]
    return corpo[: corpo.index("<!-- END GENERATED -->")]


def _linhas_de_fatos(bloco):
    """label -> value of the `| label | value |` rows of the first table of the block."""
    achados = {}
    for linha in bloco.splitlines():
        if linha.startswith("| ") and not linha.startswith("| ---") and linha.count("|") >= 3:
            rotulo, valor = (c.strip() for c in linha.strip().strip("|").split("|", 1))
            achados[rotulo] = valor
    return achados


def _por_status(itens):
    contagem = {}
    for status in itens:
        contagem[status] = contagem.get(status, 0) + 1
    return sorted(contagem.items(), key=lambda kv: (-kv[1], str(kv[0])))


def _fatos_esperados():
    """The facts of the code, computed here the long way (the data files and the registries), not through the generator."""
    from simplicio_video import HYPERFRAMES, installer, mcp_server, skill_sync, tools

    modelos = [json.loads(p.read_text(encoding="utf-8")) for p in sorted((PKG / "data" / "templates").glob("*/template.json"))]
    catalogo = json.loads((PKG / "data" / "motion" / "catalog.json").read_text(encoding="utf-8"))
    padroes = catalogo.get("patterns", catalogo) if isinstance(catalogo, dict) else catalogo
    return {
        "tools": len(mcp_server.TOOLS),
        "trilhas": len(tools.TOOLS),
        "modelos": len(modelos),
        "modelos_por_status": sorted((s, n) for s, n in _por_status(m["status"] for m in modelos)),
        "sem_composicao": sum(1 for m in modelos if not m.get("composicao")),
        "padroes": len(padroes),
        "padroes_por_status": _por_status(p.get("status") for p in padroes),
        "hyperframes": HYPERFRAMES,
        "hosts": sorted(installer.HOST_ENTRY),
        "hosts_globais": sorted(skill_sync.HOST_SKILL_ROOTS),
        "skills": len(skill_sync.SKILLS),
        "pins": {name: (t.kind, t.ref) for name, t in tools.TOOLS.items()},
    }


def test_os_numeros_esperados_nao_sao_triviais():
    """The counts recomputed above are the ones the docs must carry; if the code changes them, the docs follow."""
    esperado = _fatos_esperados()
    assert esperado["tools"] >= 32 and esperado["trilhas"] >= 13 and esperado["modelos"] >= 15
    assert len(esperado["hosts"]) != len(esperado["hosts_globais"]), "HOST_ENTRY e HOST_SKILL_ROOTS têm tamanhos diferentes hoje (12 x 11)"
    assert {s for s, _ in esperado["modelos_por_status"]} >= {"pronto", "skeleton"}


@pytest.mark.parametrize("rel", sorted(FATOS_ARQUIVOS))
def test_cada_arquivo_tem_um_bloco_fatos_com_so_os_seus_fatos(rel):
    lingua, fatos = FATOS_ARQUIVOS[rel]
    linhas = _linhas_de_fatos(_bloco(rel, "fatos"))
    esperados = {ROTULOS[lingua][k] for k in fatos if k != "pins"}
    assert set(linhas) >= esperados, f"{rel}: faltam as linhas {sorted(esperados - set(linhas))}"
    outros = {ROTULOS[lingua][k] for k in ROTULOS[lingua] if k not in fatos}
    assert not (set(linhas) & outros), f"{rel}: linhas que este arquivo não pede: {sorted(set(linhas) & outros)}"


@pytest.mark.parametrize("rel", sorted(FATOS_ARQUIVOS))
def test_o_bloco_fatos_diz_os_numeros_do_codigo(rel):
    lingua, fatos = FATOS_ARQUIVOS[rel]
    esperado = _fatos_esperados()
    linhas = _linhas_de_fatos(_bloco(rel, "fatos"))
    rotulos = ROTULOS[lingua]
    if "tools" in fatos:
        assert linhas[rotulos["tools"]] == str(esperado["tools"])
    if "trilhas" in fatos:
        assert linhas[rotulos["trilhas"]] == str(esperado["trilhas"])
    if "skills" in fatos:
        assert linhas[rotulos["skills"]] == str(esperado["skills"])
    if "hyperframes" in fatos:
        assert linhas[rotulos["hyperframes"]] == f"`{esperado['hyperframes']}`"
    if "hosts" in fatos:
        assert linhas[rotulos["hosts"]].split(":")[0] == str(len(esperado["hosts"]))
        for host in esperado["hosts"]:
            assert f"`{host}`" in linhas[rotulos["hosts"]]
    if "hosts_globais" in fatos:
        assert linhas[rotulos["hosts_globais"]].split(":")[0] == str(len(esperado["hosts_globais"]))
        for host in esperado["hosts_globais"]:
            assert f"`{host}`" in linhas[rotulos["hosts_globais"]]
    if "templates" in fatos:
        celula = linhas[rotulos["templates"]]
        assert celula.split(":")[0] == str(esperado["modelos"])
        for status, n in esperado["modelos_por_status"]:
            assert f"{n} `{status}`" in celula
        assert f"{esperado['sem_composicao']} " in celula and "`composicao`" in celula
    if "padroes" in fatos:
        celula = linhas[rotulos["padroes"]]
        assert celula.split(":")[0] == str(esperado["padroes"])
        for status, n in esperado["padroes_por_status"]:
            assert f"{n} `{status}`" in celula


@pytest.mark.parametrize("rel", ["README.md", "README.pt-BR.md"])
def test_o_bloco_fatos_dos_readmes_tem_a_tabela_de_pins_de_cada_trilha(rel):
    bloco = _bloco(rel, "fatos")
    for nome, (tipo, ref) in _fatos_esperados()["pins"].items():
        pin = ref[:7] if tipo == "git" else ref
        assert f"| `{nome}` | {tipo} | `{pin}` |" in bloco, f"{rel}: sem a linha de pin de {nome}"


@pytest.mark.parametrize("rel", ["PYPI.md", "AGENTS.md", "docs/esteira.md", "docs/host/README.md"])
def test_so_os_readmes_levam_a_tabela_de_pins(rel):
    assert "| Pin |" not in _bloco(rel, "fatos")


def test_o_readme_a_mao_diz_o_pin_de_cada_trilha_do_codigo():
    """The pins in the hand-written 'External tracks and licenses' tables (EN and PT) are the ones of tools.TOOLS (the 7-character
    start of a commit, or the npm/PyPI version): a pin bumped in tools.py without the README table is caught here. The generated
    block is cut out first, so this reads only what a person wrote."""
    for rel in ("README.md", "README.pt-BR.md"):
        texto = re.sub(r"<!-- BEGIN GENERATED: fatos -->.*?<!-- END GENERATED -->", "", (ROOT / rel).read_text(encoding="utf-8"), flags=re.S)
        for nome, (tipo, ref) in _fatos_esperados()["pins"].items():
            pin = ref[:7] if tipo == "git" else ref
            assert f"`{pin}" in texto or f"`{tipo} {pin}`" in texto or f"{tipo} `{pin}`" in texto, f"{rel}: a tabela a mão não diz o pin de {nome} ({pin})"


def test_o_mapa_de_modulos_do_agents_lista_cada_modulo_com_a_sua_docstring():
    bloco = _bloco("AGENTS.md", "mapa-modulos")
    itens = {}
    for linha in bloco.splitlines():
        if linha.startswith("- `"):
            nome, _, texto = linha[3:].partition("`: ")
            itens[nome] = texto
    modulos = {}
    for caminho in sorted(PKG.rglob("*.py")):
        rel = caminho.relative_to(PKG).as_posix()
        if rel.startswith("data/") or rel in {"__main__.py", "commands/__init__.py"}:
            continue
        modulos[rel] = ast.get_docstring(ast.parse(caminho.read_text(encoding="utf-8")))
    assert set(itens) == set(modulos), f"módulos faltando: {sorted(set(modulos) - set(itens))}; sobrando: {sorted(set(itens) - set(modulos))}"
    for rel, doc in modulos.items():
        if doc:
            comeco = " ".join(doc.split())[:30]
            assert itens[rel].startswith(comeco), f"{rel}: o mapa não abre com a docstring ({comeco!r}): {itens[rel][:60]!r}"
        else:
            assert "sem docstring" in itens[rel], f"{rel}: sem docstring e o mapa não avisa"


def test_o_agents_mantem_a_celula_a_mao_de_src_simplicio_video():
    """The block only adds: the hand-written `src/simplicio_video/` row of the table (3.8 KB, with the ADR links, the UNVERIFIED notes and
    the `data/skills/` rule) stays as the owner wrote it, and the generated module map lives apart, under its own heading."""
    texto = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    linha = next(l for l in texto.splitlines() if l.startswith("| `src/simplicio_video/` |"))
    assert len(linha) > 3000, "a célula à mão de src/simplicio_video/ do AGENTS.md foi encurtada ou trocada"
    for trecho in ("`swap.manifest.json`", "`data/skills/` (fonte da verdade; `skills/` é o espelho)", "[ADR-0018](docs/decisoes/ADR-0018-social-planejar-sem-postar.md)",
                   "[ADR-0020](docs/decisoes/ADR-0020-install-universal-e-update-igual-ao-loop.md)", "fal, wavespeed, kie e alibaba UNVERIFIED"):
        assert trecho in linha, f"a célula à mão perdeu {trecho!r}"
    assert "### Módulos de `src/simplicio_video/`" in texto and "<!-- BEGIN GENERATED: mapa-modulos -->" not in linha


def test_o_bloco_fatos_diz_que_a_contagem_vem_do_codigo_e_nao_da_prosa():
    """Where the hand-written prose still says another number (README.md:17 `6 skeleton`, esteira `1 pronto`), the reader of the block
    knows these are the ones read from the code. PYPI.md is the public page of the package: its block shows no maintainer note."""
    comeco = {"en": "Counts generated from the code", "pt": "Contagens geradas do código"}
    for rel, (lingua, _fatos) in FATOS_ARQUIVOS.items():
        bloco = _bloco(rel, "fatos")
        if rel == "PYPI.md":
            assert "make regen" not in bloco and "gen_reference" not in bloco and "Gerado" not in bloco, "a nota de manutenção apareceria na página do PyPI"
            assert bloco.lstrip().startswith("| Fato | Valor |")
        else:
            assert bloco.lstrip().startswith(comeco[lingua]), f"{rel}: o bloco não rotula a origem da contagem"
            assert "make regen" in bloco


@pytest.mark.parametrize("rel, antes, depois", [
    ("README.md", "| MCP tools (`video.*`) | {n} |", "| MCP tools (`video.*`) | {m} |"),
    ("README.pt-BR.md", "| Trilhas externas | {t} |", "| Trilhas externas | {u} |"),
])
def test_o_gerador_acusa_e_conserta_um_bloco_fatos_desatualizado(rel, antes, depois):
    """`--check` is `updated_block_text(text) != text`: a number changed by hand inside the block is caught, and regenerated."""
    from simplicio_video import mcp_server, tools

    gen = _gen_module()
    n, t = len(mcp_server.TOOLS), len(tools.TOOLS)
    original = (ROOT / rel).read_text(encoding="utf-8")
    velho = antes.format(n=n, t=t)
    assert velho in original, f"{rel}: o bloco fatos não tem a linha {velho!r}"
    adulterado = original.replace(velho, depois.format(m=n + 1, u=t + 1))
    assert adulterado != original
    assert gen.updated_block_text(adulterado, ROOT / rel) == original
    assert gen.updated_block_text(original, ROOT / rel) == original


def test_o_gerador_exige_os_blocos_de_cada_arquivo():
    """A file that must carry a block and has none is an error, not a silent skip."""
    gen = _gen_module()
    sem_bloco = "# Sem blocos\n"
    with pytest.raises(SystemExit):
        gen.updated_block_text(sem_bloco, ROOT / "README.md")
    with pytest.raises(SystemExit):
        gen.updated_block_text(sem_bloco, ROOT / "AGENTS.md")


# ---------------------------------------------------------------------------------------------------------------------- plugin.json
def _plugin():
    return json.loads((ROOT / "plugin.json").read_text(encoding="utf-8"))


def test_plugin_json_mcp_tools_e_a_lista_do_servidor_na_mesma_ordem():
    from simplicio_video import mcp_server

    assert _plugin()["mcp"]["tools"] == [name for name, _fn, _desc in mcp_server.TOOLS]


def test_plugin_json_skills_sao_as_do_pacote_e_cada_caminho_existe():
    from simplicio_video import skill_sync

    skills = _plugin()["skills"]
    assert skills == [{"name": nome, "path": f"skills/{nome}/SKILL.md"} for nome in skill_sync.SKILLS]
    for skill in skills:
        assert (ROOT / skill["path"]).is_file(), f"plugin.json aponta para {skill['path']}, que não existe"


def test_plugin_json_contract_schema_e_o_do_cli_e_existe():
    from simplicio_video import cli

    caminho = _plugin()["contract_schema"]
    assert caminho == cli.SCHEMA_REL
    assert (ROOT / caminho).is_file(), f"plugin.json aponta para {caminho}, que não existe"


def test_plugin_json_version_e_a_do_pacote():
    from simplicio_video import __version__

    assert _plugin()["version"] == __version__


def test_o_gerador_acusa_e_conserta_o_plugin_json_desatualizado():
    gen = _gen_module()
    original = (ROOT / "plugin.json").read_text(encoding="utf-8")
    assert gen.plugin_json_text(original) == original
    objeto = json.loads(original)
    objeto["version"] = "0.0.1"
    objeto["contract_schema"] = "schema/contract.schema.json"
    objeto["skills"] = objeto["skills"][:1]
    objeto["mcp"]["tools"] = objeto["mcp"]["tools"][:-1]
    adulterado = json.dumps(objeto, indent=2, ensure_ascii=False) + "\n"
    assert gen.plugin_json_text(adulterado) == original


def test_o_gerador_deixa_os_commands_do_plugin_json_como_estao():
    """`commands` (the 39 verbs with their argv and args_schema) stays hand-written: the generator rewrites only the four fields."""
    gen = _gen_module()
    original = (ROOT / "plugin.json").read_text(encoding="utf-8")
    objeto = json.loads(original)
    objeto["commands"][0]["description"] = "alterado à mão"
    editado = json.dumps(objeto, indent=2, ensure_ascii=False) + "\n"
    assert json.loads(gen.plugin_json_text(editado))["commands"][0]["description"] == "alterado à mão"
    assert list(json.loads(gen.plugin_json_text(editado))) == list(objeto)


# ------------------------------------------------------------------------------------------------- the helpers of the module map
def test_first_sentence_junta_o_paragrafo_e_corta_na_primeira_frase():
    gen = _gen_module()
    doc = "`simplicio-video render`: contract -> workdir (compiler) -> ffmpeg master (-14 LUFS). Backends: local\nor colab.\n\nOutro parágrafo."
    assert gen.first_sentence(doc) == "`simplicio-video render`: contract -> workdir (compiler) -> ffmpeg master (-14 LUFS)."
    assert gen.first_sentence("Uma frase só, quebrada\nem duas linhas (https://example.org/a.b, MIT).") == (
        "Uma frase só, quebrada em duas linhas (https://example.org/a.b, MIT).")
    assert gen.first_sentence("Fim sem ponto") == "Fim sem ponto"


def test_o_mapa_de_modulos_escapa_o_menor_que_fora_do_codigo():
    """`<slug>` outside a code span would vanish as an HTML tag on the rendered page; inside a code span it is literal already."""
    gen = _gen_module()
    assert gen._escape_angle("grava em clients/<slug>/README.md") == "grava em clients/\\<slug>/README.md"
    assert gen._escape_angle("o `x <y>` fica") == "o `x <y>` fica"
    bloco = _bloco("AGENTS.md", "mapa-modulos")
    assert "clients/\\<slug>/README.md" in bloco and "clients/<slug>" not in bloco


def test_modulo_sem_docstring_aparece_marcado_no_mapa(tmp_path, monkeypatch):
    gen = _gen_module()
    pkg = tmp_path / "simplicio_video"
    (pkg / "data").mkdir(parents=True)
    (pkg / "com_doc.py").write_text('"""Faz uma coisa. E outra."""\n', encoding="utf-8")
    (pkg / "sem_doc.py").write_text("x = 1\n", encoding="utf-8")
    (pkg / "__main__.py").write_text("x = 1\n", encoding="utf-8")
    (pkg / "data" / "escondido.py").write_text('"""Dado."""\n', encoding="utf-8")
    monkeypatch.setattr(gen, "PKG", pkg)
    itens = [l for l in gen.mapa_modulos_body().splitlines() if l.startswith("- ")]
    assert itens == ["- `com_doc.py`: Faz uma coisa.", "- `sem_doc.py`: (sem docstring)"]


# ------------------------------------------------------------------------------------------------- variables named in Trilha(...)
# The external tracks no longer read `<NAME>_DIR` / `<NAME>_DATA_DIR` with a literal `os.environ.get("...")` in their own module: the
# names are the arguments of `T = Trilha(nome, env_dir, env_data)` and `trilha_base` reads them through the declaration. The reference
# must keep listing them (they are what a user sets), so the generator reads those arguments as it reads a literal `os.environ.get`.
DECLARADAS_EM_TRILHA = {"TOONFLOW_DIR", "TOONFLOW_DATA_DIR", "MONEYPRINTER_DIR", "MONEYPRINTER_DATA_DIR", "REA_VIDEO_DIR",
                        "REA_VIDEO_DATA_DIR", "OPENCUT_DIR"}
FONTE_DE_TRILHAS = (
    "from .trilha_base import Trilha\n"                          # 1
    "import simplicio_video.trilha_base as tb\n"                 # 2
    'ENV_W = "W_DIR"\n'                                          # 3
    'T = Trilha("x", "X_DIR", "X_DATA_DIR")\n'                   # 4
    "U = tb.Trilha(\n"                                           # 5
    '    "y",\n'                                                 # 6
    '    env_dir="Y_DIR",\n'                                     # 7
    '    env_data="Y_DATA_DIR",\n'                               # 8
    ")\n"                                                        # 9
    'V = Trilha("z", "Z_DIR")\n'                                 # 10
    'W = Trilha("w", ENV_W)\n'                                   # 11
    'D = Trilha(nome, f"{nome}_DIR", None)\n'                    # 12
    'O = Outra("o", "O_DIR", "O_DATA_DIR")\n'                    # 13
    'N = Trilha("n", "minuscula", "NAO-E-NOME")\n'               # 14
)


def test_o_gerador_le_por_ast_as_variaveis_que_a_trilha_declara(monkeypatch, tmp_path):
    """The two variable arguments of `Trilha(...)` (positional or keyword, bare or `module.Trilha`) are readers, at the line of the
    call; a module constant resolves like in `os.environ.get(CONST)`; what is not a literal name, and what is not a `Trilha`, is not."""
    gen = _gen_module()
    pkg = tmp_path / "src" / "simplicio_video"
    pkg.mkdir(parents=True)
    (pkg / "trilha_x.py").write_text(FONTE_DE_TRILHAS, encoding="utf-8")
    monkeypatch.setattr(gen, "ROOT", tmp_path)
    monkeypatch.setattr(gen, "PKG", pkg)
    arq = "src/simplicio_video/trilha_x.py"
    assert gen.env_reads() == {
        "W_DIR": [f"{arq}:11"], "X_DATA_DIR": [f"{arq}:4"], "X_DIR": [f"{arq}:4"], "Y_DATA_DIR": [f"{arq}:5"],
        "Y_DIR": [f"{arq}:5"], "Z_DIR": [f"{arq}:10"],
    }  # no SIMPLICIO_<NAME>_DIR: `tools.find` builds that one at run time, and the reference never listed it for these tracks


def _declaradas_no_pacote() -> dict[str, str]:
    """The variable names given to `Trilha(...)` in the package, with the file that declares each, found here with its own ast walk
    (independent of the generator)."""
    achadas = {}
    for path in PKG.rglob("*.py"):
        rel = path.relative_to(ROOT).as_posix()
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not ((isinstance(func, ast.Name) and func.id == "Trilha") or (isinstance(func, ast.Attribute) and func.attr == "Trilha")):
                continue
            args = [*node.args[1:3], *(k.value for k in node.keywords if k.arg in ("env_dir", "env_data"))]
            achadas.update({a.value: rel for a in args if isinstance(a, ast.Constant) and isinstance(a.value, str)})
    return achadas


def test_config_md_lista_a_variavel_de_cada_trilha_declarada(gerado):
    """Red when the migration of a track to `Trilha` takes its variables out of the reference: each is a row, described, and the row
    points at the file that declares it."""
    declaradas = _declaradas_no_pacote()
    assert DECLARADAS_EM_TRILHA <= set(declaradas), "o scan não achou as trilhas conhecidas"
    linhas = {l.split("`")[1]: l for l in _read(gerado, "config.md").splitlines() if l.startswith("| `")}
    for nome, arquivo in sorted(declaradas.items()):
        assert nome in linhas, f"{nome} é argumento de Trilha(...) e falta em config.md"
        assert "sem descrição" not in linhas[nome], nome
        assert f"`{arquivo}:" in linhas[nome], f"{nome}: a linha não aponta para {arquivo}"


# ------------------------------------------------------------------------------------------------- variable named in Tool(checkout_env=...)
# A track whose checkout lives outside the tools cache (video-use: data/tools/video-use/setup.sh) names its variable only as the
# `checkout_env` argument of its `Tool(...)` in the registry, and `tools.checkout_dir` reads it through the declaration (U09). It is what a
# user sets (`VIDEO_USE_DIR`), so the reference keeps listing it: the generator reads that argument as it reads a literal `os.environ.get`.
DECLARADAS_EM_TOOL = {"VIDEO_USE_DIR"}
FONTE_DE_TOOLS = (
    "from .tools import Tool\n"                                                   # 1
    "import simplicio_video.tools as t\n"                                         # 2
    'ENV_K = "K_DIR"\n'                                                           # 3
    'A = Tool("a", "git", "u", "r", "l", "p", command="a", checkout_env="A_DIR")\n'  # 4
    "B = t.Tool(\n"                                                               # 5
    '    "b", "git", "u", "r", "l", "p",\n'                                       # 6
    '    command="b",\n'                                                          # 7
    '    checkout_env="B_DIR",\n'                                                 # 8
    ")\n"                                                                         # 9
    'K = Tool("k", "git", "u", "r", "l", "p", command="k", checkout_env=ENV_K)\n'   # 10
    'N = Tool("n", "git", "u", "r", "l", "p", command="n", checkout_env=None)\n'    # 11
    'M = Tool("m", "git", "u", "r", "l", "p", command="m", checkout_env=f"{x}_DIR")\n'  # 12
    'O = Outra("o", "git", "u", "r", "l", "p", command="o", checkout_env="O_DIR")\n'  # 13
    'L = Tool("l", "git", "u", "r", "l", "p", command="l", checkout_env="minuscula")\n'  # 14
    'P = Tool("p", "git", "u", "r", "l", "p", command="p", marker="NAO_E_CHECKOUT_ENV")\n'  # 15
)


def test_o_gerador_le_por_ast_o_checkout_env_do_tool(monkeypatch, tmp_path):
    """`checkout_env` of a `Tool(...)` (bare or `module.Tool`) is a reader, at the line of the call; a module constant resolves like in
    `os.environ.get(CONST)`; `None`, a computed name, a name that is not a variable, another argument and another callable are not."""
    gen = _gen_module()
    pkg = tmp_path / "src" / "simplicio_video"
    pkg.mkdir(parents=True)
    (pkg / "tools_x.py").write_text(FONTE_DE_TOOLS, encoding="utf-8")
    monkeypatch.setattr(gen, "ROOT", tmp_path)
    monkeypatch.setattr(gen, "PKG", pkg)
    arq = "src/simplicio_video/tools_x.py"
    assert gen.env_reads() == {"A_DIR": [f"{arq}:4"], "B_DIR": [f"{arq}:5"], "K_DIR": [f"{arq}:10"]}


def _checkout_env_no_pacote() -> dict[str, str]:
    """The names given as `checkout_env` to a `Tool(...)` in the package, with the file that declares each, found here with its own ast
    walk (independent of the generator)."""
    achadas = {}
    for path in PKG.rglob("*.py"):
        rel = path.relative_to(ROOT).as_posix()
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not ((isinstance(func, ast.Name) and func.id == "Tool") or (isinstance(func, ast.Attribute) and func.attr == "Tool")):
                continue
            achadas.update({k.value.value: rel for k in node.keywords
                            if k.arg == "checkout_env" and isinstance(k.value, ast.Constant) and isinstance(k.value.value, str)})
    return achadas


def test_config_md_lista_a_variavel_do_checkout_de_cada_trilha_do_registro(gerado):
    """Red when a track names its checkout variable only in the registry: each is a row, described, and the row points at the file."""
    declaradas = _checkout_env_no_pacote()
    assert DECLARADAS_EM_TOOL <= set(declaradas), "o scan não achou o checkout_env conhecido"
    linhas = {l.split("`")[1]: l for l in _read(gerado, "config.md").splitlines() if l.startswith("| `")}
    for nome, arquivo in sorted(declaradas.items()):
        assert nome in linhas, f"{nome} é checkout_env de um Tool(...) e falta em config.md"
        assert "sem descrição" not in linhas[nome], nome
        assert f"`{arquivo}:" in linhas[nome], f"{nome}: a linha não aponta para {arquivo}"
