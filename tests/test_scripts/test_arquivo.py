"""U16: operation and research content lives under `arquivo/` and `docs/pesquisa/`: moved with `git mv`, never deleted.

What the engine does not run and the repository does not gate (sales operation, the character-swap kit, the factory spec, the
translated READMEs, a Node service nobody executes) used to sit in the root, in `docs/` and in `scripts/`, next to the product. It is
the owner's work, so nothing is deleted: every file moved to `arquivo/<where it was>` (history kept: `git log --follow`), the five
dated researches of 30/09/2026 went to `docs/pesquisa/`, and the dead sections of `AGENTS.md` went VERBATIM to
`arquivo/AGENTS-legado.md`. `scripts/check_docs.py` skips `arquivo/` (the text there keeps the links it had).

This file pins the layout, the verbatim copy, the ownership patterns that lost their file (they go to the `backlog` block, copied as
they were) and that nothing under `arquivo/` can reach the wheel or the sdist.
"""
from __future__ import annotations

import hashlib
import re
import subprocess
import sys

import pytest
import yaml
from gitfixture import OWNERSHIP_REL, ROOT

# (where it was, where it is now). A folder ends with `/`.
ARQUIVADOS = [
    ("ugc/", "arquivo/ugc/"),
    ("prospects/", "arquivo/prospects/"),
    ("docs/venda-ativa.md", "arquivo/docs/venda-ativa.md"),
    ("docs/factory/", "arquivo/docs/factory/"),
    ("modules/", "arquivo/modules/"),
    ("scripts/kit_gpu/", "arquivo/scripts/kit_gpu/"),
    ("docs/how-to/troca-personagem-gpu/", "arquivo/docs/how-to/troca-personagem-gpu/"),
    ("READMEs/", "arquivo/READMEs/"),
    ("docs/assets/board-html.png", "arquivo/docs/assets/board-html.png"),
]
PESQUISAS = [
    "recursos.md",
    "como-gerar-videos-opus-5-5.md",
    "tokens-e-deterministico.md",
    "pipeline-deterministico-gemini.md",
    "plugin-simplicio-runtime.md",
]
LEGADO = ROOT / "arquivo" / "AGENTS-legado.md"
AGENTS = ROOT / "AGENTS.md"

# The five blocks that left AGENTS.md, as they were in origin/main (ef043d7): sha256 of the exact text (see `_blocos_do_legado`).
# `drive` is the whole section; its last item (social networks, rule 3) is live, so AGENTS.md keeps a copy of that one.
SHA256_DOS_BLOCOS = {
    "missao": "986400d659b16c5b8049522a702ec896f4a49e28a221f5516a6a3093374b4d28",
    "venda-ativa": "2586f54f005ad6753d5932a9cf632558ce7105a8bc73171f1a14bb211dd5d38a",
    "ugc": "462ef59a608ecfff4da01f4cb54994b65b528ded972fad6e16e2ed54fafe70cd",
    "drive": "9d28b9e03da4ecbc4a74d244424c36ed70f1c604fb415a92798deee4586d65eb",
    "mapa": "a78d54a4d11f30a1c213bc731d19186df3c014d458c317147c4944ca74c2d64d",
}
# What identifies each block in AGENTS.md: it must be gone from there.
SAIU_DO_AGENTS = (
    "## Missão e operação de vendas",
    "**Venda ativa em massa (prévias para oferecer)**",
    "**Vídeo UGC (gerativo)**",
    "## Entregas no Google Drive",
)
LINHAS_DO_MAPA_QUE_SAIRAM = ("| `modules/h3-swap-service/` |", "| `ugc/` |", "| `scripts/kit_gpu/` |", "| `prospects/` |")
# What the owner said must stay: the generated tables, the recipes, the product rules and the hand-written `src/simplicio_video/` cell.
FICA_NO_AGENTS = (
    "## Product boundary — read this first",
    "| Necessidade | Comando | Skill (com exemplos) |",
    "### Receita: vídeo de um creator em outro idioma (legenda, texto na tela e voz)",
    "| `src/simplicio_video/` |",
    "<!-- BEGIN GENERATED: fatos -->",
    "<!-- BEGIN GENERATED: mapa-modulos -->",
    "<!-- BEGIN GENERATED: host -->",
    "| `intake/` |",
    "**O motor não posta.**",
)


@pytest.mark.parametrize("antes, depois", ARQUIVADOS, ids=[a for a, _ in ARQUIVADOS])
def test_archived_content_left_its_old_place_and_sits_under_arquivo(antes, depois):
    assert not (ROOT / antes).exists(), f"{antes} is still where it was: `git mv {antes} {depois}`"
    assert (ROOT / depois).exists(), f"{depois} does not exist"
    if depois.endswith("/"):
        assert any((ROOT / depois).rglob("*")), f"{depois} is empty"


@pytest.mark.parametrize("nome", PESQUISAS)
def test_the_dated_researches_moved_to_docs_pesquisa(nome):
    assert not (ROOT / "docs" / nome).exists(), f"docs/{nome} is still in the flat docs/ folder"
    assert (ROOT / "docs" / "pesquisa" / nome).is_file()


def test_docs_pesquisa_has_an_index_that_links_the_five_researches():
    indice = ROOT / "docs" / "pesquisa" / "README.md"
    assert indice.is_file()
    texto = indice.read_text(encoding="utf-8")
    for nome in PESQUISAS:
        assert f"]({nome})" in texto, f"docs/pesquisa/README.md does not link {nome}"


def test_the_index_of_arquivo_names_every_origin_and_every_destination():
    indice = ROOT / "arquivo" / "README.md"
    assert indice.is_file()
    texto = indice.read_text(encoding="utf-8")
    for antes, depois in ARQUIVADOS:
        assert f"`{antes}`" in texto, f"arquivo/README.md does not say where {antes} was"
        assert f"`{depois}`" in texto, f"arquivo/README.md does not say where {antes} is now"
    assert "AGENTS-legado.md" in texto
    assert "git mv" in texto and "git log --follow" in texto  # how it was moved, and how to see the history


def test_check_docs_skips_arquivo_and_no_longer_skips_the_old_spec_folder():
    """The exclusion of `docs/factory/` (a spec whose links point to pages that were never written) became the exclusion of `arquivo/`."""
    sys.path.insert(0, str(ROOT / "scripts"))
    try:
        import check_docs
    finally:
        sys.path.remove(str(ROOT / "scripts"))
    assert check_docs.ARCHIVE_PREFIXES == ("arquivo/",)
    assert not hasattr(check_docs, "SPEC_PREFIXES")


# ---------------------------------------------------------------------------------------------------------------- AGENTS.md


def _blocos_do_legado() -> dict[str, str]:
    """`<!-- origem: <chave> -->` opens each block; the text up to the next marker (or the end), without the blank lines around it."""
    texto = LEGADO.read_text(encoding="utf-8")
    partes = re.split(r"^<!-- origem: ([\w-]+) -->\n", texto, flags=re.M)
    return {chave: corpo.strip("\n") for chave, corpo in zip(partes[1::2], partes[2::2])}


def test_the_legado_keeps_the_five_dead_blocks_of_agents_md_byte_for_byte():
    assert LEGADO.is_file(), "arquivo/AGENTS-legado.md does not exist"
    blocos = _blocos_do_legado()
    assert set(blocos) == set(SHA256_DOS_BLOCOS), sorted(blocos)
    for chave, esperado in SHA256_DOS_BLOCOS.items():
        achado = hashlib.sha256(blocos[chave].encode("utf-8")).hexdigest()
        assert achado == esperado, f"block `{chave}` of arquivo/AGENTS-legado.md is not the text that was in AGENTS.md"


def test_agents_md_no_longer_carries_the_dead_blocks_and_points_to_the_legado():
    texto = AGENTS.read_text(encoding="utf-8")
    for marca in SAIU_DO_AGENTS:
        assert marca not in texto, f"AGENTS.md still has {marca!r}: it moved to arquivo/AGENTS-legado.md"
    linhas = texto.splitlines()
    for prefixo in LINHAS_DO_MAPA_QUE_SAIRAM:
        assert not any(linha.startswith(prefixo) for linha in linhas), f"AGENTS.md still has the map row {prefixo}"
    assert "(arquivo/AGENTS-legado.md)" in texto and "(arquivo/README.md)" in texto, "AGENTS.md needs the pointer to arquivo/"
    for marca in FICA_NO_AGENTS:
        assert marca in texto, f"AGENTS.md lost {marca!r}: that part is live and stays"
    assert len(AGENTS.read_bytes()) < 54830 - 5000, "the ~6 KB of dead text should be out of AGENTS.md (it had 54,830 bytes)"


# --------------------------------------------------------------------------------------------------------- ownership.yaml

# The `owns` patterns whose only file moved. They went to the `backlog` block of their issue, copied as they were (the comment too).
PADROES_QUE_PERDERAM_O_ARQUIVO = {
    33: ['"docs/factory/contracts.md"   # o spec manda o PR do kernel atualizar este arquivo (transition, Store, nomes)'],
    44: ['"docs/pipeline-deterministico-gemini.md"', '"docs/plugin-simplicio-runtime.md"', '"docs/venda-ativa.md"'],
    88: ['"docs/assets/board-html.png"   # captura do dashboard, PNG pequeno'],
    150: ['"docs/recursos.md"'],
}


def test_the_owns_patterns_that_lost_their_file_went_to_the_backlog_verbatim():
    texto = (ROOT / OWNERSHIP_REL).read_text(encoding="utf-8")
    cabeca, _, backlog = texto.partition("\nbacklog:\n")
    mapa = yaml.safe_load(texto)
    for issue, linhas in PADROES_QUE_PERDERAM_O_ARQUIVO.items():
        for linha in linhas:
            assert f"      - {linha}" not in cabeca, f"#{issue}: {linha} is still in `owns`"
            assert f"    - {linha}" in backlog, f"#{issue}: {linha} is not in the `backlog` block"
        padroes = [re.match(r'"([^"]+)"', linha).group(1) for linha in linhas]
        assert set(padroes) <= set(mapa["backlog"][issue]), issue
        assert not set(padroes) & set(mapa["issues"][issue].get("owns") or []), issue


# ----------------------------------------------------------------------------------------------- the old path of the map


@pytest.mark.parametrize("rel", [".github/ISSUE_TEMPLATE/issue.md", "arquivo/docs/factory/parallel-work.md"])
def test_nothing_points_to_the_old_place_of_the_ownership_map(rel):
    """`docs/factory/ownership.yaml` is gone since U15: the links that still named it now name `scripts/ownership.yaml`."""
    texto = (ROOT / rel).read_text(encoding="utf-8")
    assert "factory/ownership.yaml" not in texto, rel
    assert "scripts/ownership.yaml" in texto, rel


def test_the_issue_template_points_to_where_the_factory_spec_is_now():
    texto = (ROOT / ".github" / "ISSUE_TEMPLATE" / "issue.md").read_text(encoding="utf-8")
    assert "blob/main/docs/factory/" not in texto
    assert "blob/main/arquivo/docs/factory/README.md" in texto and "blob/main/arquivo/docs/factory/parallel-work.md" in texto


# ---------------------------------------------------------------------------------------------------- docs gate and package


def test_the_docs_check_is_green_on_the_repository_with_the_new_layout():
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "check_docs.py")], capture_output=True, text=True, cwd=ROOT, timeout=120)
    assert r.returncode == 0, r.stdout + r.stderr


def test_nothing_under_arquivo_can_reach_the_wheel_or_the_sdist():
    for rel in ("pyproject.toml", "MANIFEST.in"):
        assert "arquivo" not in (ROOT / rel).read_text(encoding="utf-8"), rel
    tracked = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.split("\0")
    assert any(p.startswith("arquivo/") for p in tracked), "arquivo/ is empty"
    assert not [p for p in tracked if p.startswith("src/") and "arquivo" in p.split("/")], "an arquivo/ folder inside the package"
