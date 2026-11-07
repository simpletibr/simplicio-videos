"""U16: operation and research content lives under `arquivo/` and `docs/pesquisa/`: moved with `git mv`, never deleted.

What the engine does not run and the repository does not gate (sales operation, the character-swap kit, the factory spec, the
translated READMEs, a Node service nobody executes) used to sit in the root, in `docs/` and in `scripts/`, next to the product. It is
the owner's work, so nothing is deleted: every file moved to `arquivo/<where it was>` (history kept: `git log --follow`), the five
dated researches of 30/09/2026 went to `docs/pesquisa/`, and the four rows of the `AGENTS.md` map that described the archived folders
went VERBATIM to `arquivo/AGENTS-legado.md`. The sections of `AGENTS.md` that carry an ACTIVE rule (the owner's sales guide, the
active-sales flow, the UGC guardrails, the Drive delivery convention that `publish.py` and `--drive-nome` still use) did NOT move:
when in doubt a section stays in the live file. `scripts/check_docs.py` skips `arquivo/` (the text there keeps the links it had).

This file pins the layout, the verbatim copy, the live sections, the manifest of `arquivo/` (so that deleting or adding a file there is a
decision, not an accident), the ownership patterns that lost their file (they go to the `backlog` block, copied as they were) and that
nothing under `arquivo/` can reach the wheel or the sdist.
"""
from __future__ import annotations

import hashlib
import re
import subprocess
import sys

import pytest
import yaml
from gitfixture import OWNERSHIP_REL, ROOT, Repo, clean_env

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
CABECALHO_DA_TABELA_DO_MAPA = "| Pasta | O quê | Entrada principal |\n|---|---|---|\n"
AGENTS = ROOT / "AGENTS.md"

MANIFESTO = ROOT / "tests" / "data" / "arquivo_manifest.txt"

# What left AGENTS.md: the four map rows of the archived folders, as they were in origin/main (ef043d7): sha256 of the exact text (see
# `_blocos_do_legado`). Nothing else: the sections below are active rules and stay.
SHA256_DO_LEGADO = {"mapa": "a78d54a4d11f30a1c213bc731d19186df3c014d458c317147c4944ca74c2d64d"}
# The sections that stayed in AGENTS.md, byte for byte as in origin/main: (first line, what follows the last line, sha256). The only
# difference is the target of two links, written back here (`ugc/README.md`, `docs/venda-ativa.md` are under arquivo/ now).
SECOES_QUE_FICARAM = {
    "missao": ("## Missão e operação de vendas", "\n\n## O que é", "986400d659b16c5b8049522a702ec896f4a49e28a221f5516a6a3093374b4d28"),
    "venda-ativa": ("**Venda ativa em massa (prévias para oferecer)**", "\n\n**Novo vídeo (etapas 3–7)",
                    "2586f54f005ad6753d5932a9cf632558ce7105a8bc73171f1a14bb211dd5d38a"),
    "ugc": ("**Vídeo UGC (gerativo)**", "\n\n**Voz / narração**", "462ef59a608ecfff4da01f4cb54994b65b528ded972fad6e16e2ed54fafe70cd"),
    "drive": ("## Entregas no Google Drive", "\n\n## Convenções e travas", "9d28b9e03da4ecbc4a74d244424c36ed70f1c604fb415a92798deee4586d65eb"),
}
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
    "`simplicio-video/clientes/NOME_CLIENTE/ANO/CAMPANHA`",  # the Drive convention publish.py prints and `--drive-nome` feeds
    "gerar em plataforma paga só com pedido explícito do Wesley",  # the UGC guardrail
    "**Nada é enviado pelo agente**",  # the active-sales rule
    "Leia esse guia antes de qualquer trabalho de venda ativa.",  # the pointer to the owner's guide
)


def _rastreados(pasta: str, raiz=ROOT) -> list[str]:
    """What git TRACKS under `pasta` (a place the archived content left). What git does not track does not count: an old checkout leaves a
    `.ruff_cache` (self-ignored) in `modules/`, a prospects run leaves ignored files in `prospects/`, and neither is the content that
    moved, so the folder itself may still exist. Skips the test when `raiz` is not a git checkout (an sdist) or git is missing."""
    try:
        r = subprocess.run(["git", "ls-files", "-z", "--", pasta], cwd=raiz, capture_output=True, text=True, env=clean_env())
    except OSError as e:
        pytest.skip(f"git is not available: {e}")
    if r.returncode:
        pytest.skip(f"not a git checkout: {r.stderr.strip()}")
    return sorted(p for p in r.stdout.split("\0") if p)


@pytest.mark.parametrize("antes, depois", ARQUIVADOS, ids=[a for a, _ in ARQUIVADOS])
def test_archived_content_left_its_old_place_and_sits_under_arquivo(antes, depois):
    assert (ROOT / depois).exists(), f"{depois} does not exist"
    if depois.endswith("/"):
        assert any((ROOT / depois).rglob("*")), f"{depois} is empty"
    ficaram = _rastreados(antes)  # last: it skips (not fails) outside a git checkout, after the asserts above ran
    assert not ficaram, f"{antes} still has files tracked where it was (`git mv {antes} {depois}`): {ficaram[:5]}"


def test_the_old_place_check_sees_a_tracked_file_but_not_what_git_ignores_or_does_not_track(tmp_path):
    """The check looks at tracked files, not at the folder: a folder that only holds leftovers (a `.ruff_cache`, an untracked note) is
    fine; a file that is tracked, even only staged (`git add`, `git mv` back), is not."""
    repo = Repo(tmp_path / "repo")
    repo.commit_files("base", {"README.md": "base\n", "arquivo/modules/app.py": "x\n"})
    assert _rastreados("modules/", repo.path) == [] and _rastreados("ugc/", repo.path) == []
    repo.write("modules/.ruff_cache/.gitignore", "*\n")  # what ruff writes: the cache ignores itself
    repo.write("modules/.ruff_cache/0.1.0/entry", "cache\n")
    repo.write("modules/notes.txt", "untracked, not ignored\n")
    assert (repo.path / "modules").is_dir() and "?? modules/" in repo.git("status", "--short")
    assert _rastreados("modules/", repo.path) == [], "leftovers that git does not track must not count"
    repo.git("add", "--", "modules/notes.txt")
    assert _rastreados("modules/", repo.path) == ["modules/notes.txt"], "a staged file is tracked"
    repo.git("mv", "arquivo/modules/app.py", "modules/app.py")
    assert _rastreados("modules/", repo.path) == ["modules/app.py", "modules/notes.txt"], "a file moved back is tracked"
    repo.git("rm", "-q", "-f", "--", "modules/app.py", "modules/notes.txt")
    assert (repo.path / "modules").is_dir() and _rastreados("modules/", repo.path) == [], "the folder may stay while nothing in it is tracked"
    repo.commit_files("single file and nested folder", {"docs/venda-ativa.md": "x\n", "docs/factory/spec.md": "x\n"})
    assert _rastreados("docs/venda-ativa.md", repo.path) == ["docs/venda-ativa.md"]
    assert _rastreados("docs/factory/", repo.path) == ["docs/factory/spec.md"]


@pytest.mark.parametrize("falha, motivo", [(subprocess.CompletedProcess([], 128, "", "fatal: not a git repository"), "not a git checkout: fatal: not a git repository"),
                                           (FileNotFoundError("git"), "git is not available: git")])
def test_the_old_place_check_skips_with_a_reason_outside_a_git_checkout(monkeypatch, falha, motivo):
    """An sdist has no `.git`: the check cannot say anything, so it skips and says why (it never passes or fails by accident)."""
    def sem_git(*args, **kwargs):
        if isinstance(falha, Exception):
            raise falha
        return falha

    monkeypatch.setattr(subprocess, "run", sem_git)
    with pytest.raises(pytest.skip.Exception) as caught:
        _rastreados("modules/")
    assert caught.value.msg == motivo


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
    blocos = {chave: corpo.strip("\n") for chave, corpo in zip(partes[1::2], partes[2::2])}
    # The four map rows are shown under the header of the table they came from, so that they render as a table; the header is not theirs.
    blocos["mapa"] = blocos["mapa"].removeprefix(CABECALHO_DA_TABELA_DO_MAPA)
    return blocos


def test_the_legado_keeps_the_four_map_rows_of_the_archived_folders_byte_for_byte():
    assert LEGADO.is_file(), "arquivo/AGENTS-legado.md does not exist"
    blocos = _blocos_do_legado()
    assert set(blocos) == set(SHA256_DO_LEGADO), sorted(blocos)
    for chave, esperado in SHA256_DO_LEGADO.items():
        achado = hashlib.sha256(blocos[chave].encode("utf-8")).hexdigest()
        assert achado == esperado, f"block `{chave}` of arquivo/AGENTS-legado.md is not the text that was in AGENTS.md"


def test_agents_md_no_longer_carries_the_map_rows_of_the_archived_folders_and_points_to_the_legado():
    texto = AGENTS.read_text(encoding="utf-8")
    linhas = texto.splitlines()
    for prefixo in LINHAS_DO_MAPA_QUE_SAIRAM:
        assert not any(linha.startswith(prefixo) for linha in linhas), f"AGENTS.md still has the map row {prefixo}"
    assert "(arquivo/AGENTS-legado.md)" in texto and "(arquivo/README.md)" in texto, "AGENTS.md needs the pointer to arquivo/"
    for marca in FICA_NO_AGENTS:
        assert marca in texto, f"AGENTS.md lost {marca!r}: that part is live and stays"


@pytest.mark.parametrize("chave", sorted(SECOES_QUE_FICARAM))
def test_the_active_sections_stay_in_agents_md_byte_for_byte(chave):
    """The legado only gets what is unmistakably dead. A rule an agent must follow stays in the live file (`publish.py` and `--drive-nome` still
    use the Drive convention; the guardrails of the UGC flow and of the active sales flow are not written anywhere else in AGENTS.md)."""
    inicio, fim, esperado = SECOES_QUE_FICARAM[chave]
    texto = AGENTS.read_text(encoding="utf-8")
    assert inicio in texto, f"AGENTS.md lost the section that starts with {inicio!r}"
    a = texto.index(inicio)
    secao = texto[a:texto.index(fim, a)]
    secao = secao.replace("arquivo/ugc/README.md", "ugc/README.md").replace("arquivo/docs/venda-ativa.md", "docs/venda-ativa.md")
    assert hashlib.sha256(secao.encode("utf-8")).hexdigest() == esperado, f"the section `{chave}` of AGENTS.md is not the text of origin/main"


# ------------------------------------------------------------------------------------------------------- manifest of arquivo/


def _arquivos_de_arquivo() -> list[str]:
    """Every file of arquivo/, relative to it: what git tracks, plus what it does not ignore yet (a file added and not committed)."""
    r = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z", "--", "arquivo"], cwd=ROOT, capture_output=True, text=True)
    if r.returncode:
        achados = [p.relative_to(ROOT / "arquivo").as_posix() for p in (ROOT / "arquivo").rglob("*") if p.is_file() and "__pycache__" not in p.parts]
        return sorted(achados)
    return sorted({p.removeprefix("arquivo/") for p in r.stdout.split("\0") if p})


def test_the_manifest_of_arquivo_lists_every_file_and_every_listed_file_exists():
    """Deleting or renaming a file under arquivo/, or adding one, has to update `tests/data/arquivo_manifest.txt` ON PURPOSE.

    Regenerate it with: `git ls-files arquivo | sed 's#^arquivo/##' | LC_ALL=C sort > tests/data/arquivo_manifest.txt`."""
    listados = MANIFESTO.read_text(encoding="utf-8").splitlines()
    assert listados, "the manifest is empty"
    assert len(set(listados)) == len(listados), "a path twice in the manifest"
    assert listados == sorted(listados), "the manifest is not sorted (LC_ALL=C sort)"
    sumiram = [p for p in listados if not (ROOT / "arquivo" / p).is_file()]
    assert not sumiram, "files of the manifest that are not in arquivo/ any more (archived work is never deleted):\n  " + "\n  ".join(sumiram)
    novos = sorted(set(_arquivos_de_arquivo()) - set(listados))
    assert not novos, "files in arquivo/ that the manifest does not list (add them to tests/data/arquivo_manifest.txt):\n  " + "\n  ".join(novos)
    assert {"README.md", "AGENTS-legado.md", "docs/factory/README.md", "modules/h3-swap-service/README.md", "ugc/pack.json"} <= set(listados)


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


@pytest.mark.parametrize("rel", [".github/ISSUE_TEMPLATE/issue.md", "docs/host/parallel-work.md"])
def test_nothing_points_to_the_old_place_of_the_ownership_map(rel):
    """`docs/factory/ownership.yaml` is gone since U15: the links that still named it now name `scripts/ownership.yaml`."""
    texto = (ROOT / rel).read_text(encoding="utf-8")
    assert "factory/ownership.yaml" not in texto, rel
    assert "scripts/ownership.yaml" in texto, rel


def test_the_issue_template_points_to_where_the_factory_spec_and_the_working_agreement_are_now():
    texto = (ROOT / ".github" / "ISSUE_TEMPLATE" / "issue.md").read_text(encoding="utf-8")
    assert "blob/main/docs/factory/" not in texto and "blob/main/arquivo/docs/factory/parallel-work.md" not in texto
    assert "blob/main/arquivo/docs/factory/README.md" in texto and "blob/main/docs/host/parallel-work.md" in texto


def test_the_working_agreement_stayed_live_in_docs_host_and_everything_that_cites_it_follows():
    """`parallel-work.md` is how to work in parallel (CONTRIBUTING, ADR-0005, the gate page and the issue template cite it): it is not
    archive. It is a host page now (front matter checked by `test_host_front_matter`); the rest of the factory spec stays in arquivo/."""
    assert (ROOT / "docs" / "host" / "parallel-work.md").is_file()
    assert not (ROOT / "arquivo" / "docs" / "factory" / "parallel-work.md").exists()
    cita = {"CONTRIBUTING.md": "(docs/host/parallel-work.md)", "docs/decisoes/ADR-0005-gate-sem-ci.md": "(../host/parallel-work.md)",
            "docs/host/gate.md": "(parallel-work.md)", "arquivo/docs/factory/README.md": "(../../../docs/host/parallel-work.md)"}
    for rel, alvo in cita.items():
        texto = (ROOT / rel).read_text(encoding="utf-8")
        assert alvo in texto, f"{rel} does not link {alvo}"
        assert "arquivo/docs/factory/parallel-work.md" not in texto, rel
    indice = (ROOT / "docs" / "host" / "README.md").read_text(encoding="utf-8")
    assert "](parallel-work.md)" in indice, "docs/host/README.md does not list the page"


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
