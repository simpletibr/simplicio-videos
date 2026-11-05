"""scripts/licenses.py (#46): allowlist de licenças, exceções justificadas, docs/licenses.md gerado,
check de import e isolamento dos programas AGPL.

Contrato que a fase 2 precisa cumprir (estes testes chamam essas funções; nada de rede nem sockets):

- scan(exceptions_path=EXCEPTIONS) -> list[Entry]
    Entry tem name, version, license, status ("allowed" | "exception" | "denied") e used_by (str).
    Lê as distribuições instaladas com importlib.metadata.distributions() (chamada pelo nome do
    módulo, para o monkeypatch dos testes funcionar), compara a licença com a allowlist (MIT,
    Apache-2.0, BSD, ISC, PSF, MPL-2.0) e aplica o arquivo de exceções.
- denied(entries) -> list[Entry]: as entradas com status "denied".
- render_table(entries) -> str: conteúdo de docs/licenses.md (package, versão, licença, onde é usado).
- check_generated(path, entries) -> list[str]: [] se o arquivo bate com render_table(entries),
    senão uma mensagem por problema (arquivo ausente ou desatualizado).
- import_violations(files, entries) -> list[str]: uma mensagem por arquivo fonte que importa um
    pacote com status "denied" (o nome do módulo de cada pacote vem de top_level.txt).
- EXCEPTIONS = docs/licenses-exceptions.yaml: lista YAML de {package, license, justificativa, uso}.
"""
from __future__ import annotations

import ast
import importlib.metadata
import importlib.util
import sys
from email.message import Message
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "licenses.py"
DOC = ROOT / "docs" / "licenses.md"

# Programas AGPL que só podem existir como processo ou serviço externo, nunca importados por src/.
FORBIDDEN_IMPORTS = {"openmontage", "voicestudio", "postiz"}


def _lic():
    """Carrega scripts/licenses.py. Sem o arquivo, falha com a razão certa (feature não implementada)."""
    if not SCRIPT.exists():
        pytest.fail("scripts/licenses.py não existe: é a fase 2 (scan, allowlist, exceções) que o cria", pytrace=False)
    spec = importlib.util.spec_from_file_location("licenses", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["licenses"] = mod
    spec.loader.exec_module(mod)
    return mod


class FakeDist:
    """Imita importlib.metadata.Distribution: name, version, metadata e read_text('top_level.txt')."""

    def __init__(self, name: str, version: str, license_: str, top_level=()):
        self.name = name
        self.version = version
        self.metadata = Message()
        self.metadata["Name"] = name
        self.metadata["Version"] = version
        self.metadata["License"] = license_
        self._top_level = "".join(f"{m}\n" for m in top_level)

    def read_text(self, filename):
        return self._top_level if filename == "top_level.txt" else None

    def requires(self, *reqs):
        for req in reqs:
            self.metadata["Requires-Dist"] = req
        return self


def _use_dists(monkeypatch, *dists):
    """Troca o conjunto de distribuições instaladas que importlib.metadata enxerga."""
    monkeypatch.setattr(importlib.metadata, "distributions", lambda **_: list(dists))


def _exceptions(tmp_path: Path, items: list[dict]) -> Path:
    path = tmp_path / "licenses-exceptions.yaml"
    path.write_text(yaml.safe_dump(items, allow_unicode=True), encoding="utf-8")
    return path


AGPL = FakeDist("fake-agpl-lib", "1.0", "AGPL-3.0-only", top_level=["fake_agpl_lib"])
MIT = FakeDist("fake-mit-lib", "2.0", "MIT", top_level=["fake_mit_lib"])


# (a) um distribution AGPL falso reprova o scan
def test_dist_agpl_falso_reprova_o_scan(monkeypatch, tmp_path):
    lic = _lic()
    _use_dists(monkeypatch, AGPL)

    entries = lic.scan(exceptions_path=_exceptions(tmp_path, []))

    bad = lic.denied(entries)
    assert [e.name for e in bad] == ["fake-agpl-lib"]
    assert bad[0].status == "denied"


# (a2) o scan é determinístico: só a base declarada do produto + o extra `test`; extras instalados e pip não entram
def test_scan_se_limita_ao_fecho_das_deps_base_e_do_extra_test(monkeypatch, tmp_path):
    lic = _lic()

    def d(name, *reqs):
        return FakeDist(name, "1.0", "MIT", top_level=[name.replace("-", "_")]).requires(*reqs)

    produto = d("simplicio-video", "base-lib>=1", 'pytest>=8; extra == "test"', 'mcp>=1; extra == "mcp"',
                'win-only; sys_platform == "win32"')
    dists = [produto, d("base-lib", "transitiva"), d("transitiva"), d("pytest", 'dev-extra; extra == "dev"'),
             d("dev-extra"), d("mcp", "starlette"), d("starlette"), d("pip"), d("win-only")]
    _use_dists(monkeypatch, *dists)

    entries = lic.scan(exceptions_path=_exceptions(tmp_path, []))

    assert [e.name for e in entries] == ["base-lib", "pytest", "simplicio-video", "transitiva"]
    assert {e.name: e.used_by for e in entries}["transitiva"] == "base-lib"


# (a3) a tabela é estável, mas o gate de licença olha também o fecho de todo extra declarado que esteja instalado
def test_scan_de_todos_os_extras_reprova_licenca_negada_fora_da_tabela(monkeypatch, tmp_path):
    lic = _lic()
    produto = FakeDist("simplicio-video", "1.0", "MIT").requires("base-lib", 'pacote-ruim>=1; extra == "mcp"',
                                                                 'nao-instalado; extra == "remote"')
    produto.metadata["Provides-Extra"] = "mcp"
    produto.metadata["Provides-Extra"] = "remote"
    ruim = FakeDist("pacote-ruim", "1.0", "AGPL-3.0-only", top_level=["pacote_ruim"])
    _use_dists(monkeypatch, produto, FakeDist("base-lib", "1.0", "MIT"), ruim)
    exc = _exceptions(tmp_path, [])

    assert [e.name for e in lic.scan(exceptions_path=exc)] == ["base-lib", "simplicio-video"]
    todos = lic.scan(exceptions_path=exc, todos_os_extras=True)
    assert [e.name for e in lic.denied(todos)] == ["pacote-ruim"]
    assert {e.name: e.used_by for e in todos}["pacote-ruim"] == "simplicio-video[mcp]"


# (a4) `dep[extra]` puxa as exigências do extra da dependência (ex.: PyJWT[crypto] -> cryptography)
def test_scan_segue_o_extra_pedido_a_uma_dependencia(monkeypatch, tmp_path):
    lic = _lic()
    produto = FakeDist("simplicio-video", "1.0", "MIT").requires("jwt-lib[crypto]>=2")
    jwt = FakeDist("jwt-lib", "1.0", "MIT").requires('crypto-lib; extra == "crypto"', 'outro; extra == "docs"')
    _use_dists(monkeypatch, produto, jwt, FakeDist("crypto-lib", "1.0", "MIT"), FakeDist("outro", "1.0", "MIT"))

    nomes = [e.name for e in lic.scan(exceptions_path=_exceptions(tmp_path, []))]

    assert nomes == ["crypto-lib", "jwt-lib", "simplicio-video"]


# (a5) a tabela do doc não lista dependência condicionada ao ambiente (python_version, plataforma...): é igual em qualquer Python.
# O gate de licença continua vendo a dependência quando ela está instalada.
def test_tabela_ignora_dependencia_com_marcador_de_ambiente_mas_o_gate_ve(monkeypatch, tmp_path):
    lic = _lic()
    produto = FakeDist("simplicio-video", "1.0", "MIT").requires("base-lib")
    base = FakeDist("base-lib", "1.0", "MIT").requires("typing-ext; python_version < '3.13'", "tomli; python_full_version < '3.11'",
                                                      "colorama; sys_platform == 'win32' and extra == 'test'")
    outras = [FakeDist(n, "1.0", "MIT") for n in ("typing-ext", "tomli", "colorama")]
    _use_dists(monkeypatch, produto, base, *outras)
    exc = _exceptions(tmp_path, [])

    assert [e.name for e in lic.scan(exceptions_path=exc)] == ["base-lib", "simplicio-video"]
    assert [e.name for e in lic.scan(exceptions_path=exc, todos_os_extras=True)] == [
        "base-lib", "colorama", "simplicio-video", "tomli", "typing-ext"]


# (a6) pacote instalado mas não declarado (GPL) importado pelo código continua reprovado: o gate olha tudo o que está instalado
def test_pacote_gpl_instalado_e_nao_declarado_importado_reprova(monkeypatch, tmp_path):
    lic = _lic()
    produto = FakeDist("simplicio-video", "1.0", "MIT").requires("base-lib")
    gpl = FakeDist("undecl-gpl", "1.0", "GPL-2.0-only", top_level=["undeclgpl"])
    _use_dists(monkeypatch, produto, FakeDist("base-lib", "1.0", "MIT"), gpl)
    exc = _exceptions(tmp_path, [])

    entries = lic.scan(exceptions_path=exc, todos_os_extras=True)
    arquivo = tmp_path / "usa_gpl.py"
    arquivo.write_text("import undeclgpl\n", encoding="utf-8")

    assert [e.name for e in lic.denied(entries)] == ["undecl-gpl"]
    assert len(lic.import_violations([arquivo], entries)) == 1


# (b) a mesma licença, com exceção justificada, passa
def test_excecao_justificada_deixa_o_agpl_passar(monkeypatch, tmp_path):
    lic = _lic()
    _use_dists(monkeypatch, AGPL)
    exc = _exceptions(tmp_path, [{
        "package": "fake-agpl-lib",
        "license": "AGPL-3.0-only",
        "justificativa": "teste: uso só em desenvolvimento",
        "uso": "somente desenvolvimento, não distribuído",
    }])

    entries = lic.scan(exceptions_path=exc)

    assert lic.denied(entries) == []
    assert [(e.name, e.status) for e in entries] == [("fake-agpl-lib", "exception")]


# (c) pacote com licença da allowlist passa sem exceção
def test_pacote_mit_passa_sem_excecao(monkeypatch, tmp_path):
    lic = _lic()
    _use_dists(monkeypatch, MIT)

    entries = lic.scan(exceptions_path=_exceptions(tmp_path, []))

    assert lic.denied(entries) == []
    assert [(e.name, e.status) for e in entries] == [("fake-mit-lib", "allowed")]


# (d) docs/licenses.md gerado bate com o scan; arquivo desatualizado ou ausente falha
def test_docs_licenses_md_bate_com_o_scan_do_ambiente():
    lic = _lic()
    assert DOC.exists(), "docs/licenses.md não foi gerado (make regen)"

    assert lic.check_generated(DOC, lic.scan()) == []


def test_scan_do_ambiente_real_sem_licenca_negada():
    """O gate em si: as distribuições do .venv passam pela allowlist ou por exceção justificada."""
    lic = _lic()

    assert lic.denied(lic.scan(todos_os_extras=True)) == []


def test_docs_licenses_md_desatualizado_ou_ausente_falha(monkeypatch, tmp_path):
    lic = _lic()
    _use_dists(monkeypatch, MIT)
    entries = lic.scan(exceptions_path=_exceptions(tmp_path, []))

    stale = tmp_path / "licenses.md"
    stale.write_text("# tabela antiga\n", encoding="utf-8")
    assert lic.check_generated(stale, entries) != []

    assert lic.check_generated(tmp_path / "nao-existe.md", entries) != []


# (e) arquivo fonte que importa pacote AGPL falha no check de import; pacote MIT passa
def test_arquivo_fonte_que_importa_agpl_falha_no_check_de_import(monkeypatch, tmp_path):
    lic = _lic()
    _use_dists(monkeypatch, AGPL, MIT)
    entries = lic.scan(exceptions_path=_exceptions(tmp_path, []))

    bad = tmp_path / "modulo_ruim.py"
    bad.write_text("import os\nimport fake_agpl_lib.sub\n", encoding="utf-8")
    violations = lic.import_violations([bad], entries)
    assert len(violations) == 1
    assert "fake_agpl_lib" in violations[0] and "modulo_ruim.py" in violations[0]

    ok = tmp_path / "modulo_ok.py"
    ok.write_text("import fake_mit_lib\n", encoding="utf-8")
    assert lic.import_violations([ok], entries) == []


# (f) isolamento: src/ nunca importa OpenMontage, VoiceStudio ou Postiz
def _imported_roots(path: Path) -> list[tuple[str, int]]:
    """Primeiro nome de cada import estático ou dinâmico (import_module/__import__ com string literal)."""
    found: list[tuple[str, int]] = []
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found += [(a.name.split(".")[0], node.lineno) for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.append((node.module.split(".")[0], node.lineno))
        elif isinstance(node, ast.Call) and node.args and isinstance(node.args[0], ast.Constant):
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
            if name in {"import_module", "__import__"} and isinstance(node.args[0].value, str):
                found.append((node.args[0].value.split(".")[0], node.lineno))
    return found


def _forbidden_imports(base: Path) -> list[str]:
    hits = []
    for path in sorted(base.rglob("*.py")):
        for root, lineno in _imported_roots(path):
            if root.lower() in FORBIDDEN_IMPORTS:
                hits.append(f"{path.relative_to(base)}:{lineno} importa {root}")
    return hits


def test_src_nao_importa_openmontage_voicestudio_nem_postiz():
    src = ROOT / "src"
    assert list(src.rglob("*.py")), "src/ sem arquivos .py: o teste não estaria verificando nada"

    assert _forbidden_imports(src) == []


def test_detector_de_isolamento_pega_import_proibido(tmp_path):
    """Prova que o detector não passa vazio: import estático, from-import e import dinâmico são pegos."""
    (tmp_path / "a.py").write_text("import postiz\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("from VoiceStudio.api import x\n", encoding="utf-8")
    (tmp_path / "c.py").write_text('import importlib\nimportlib.import_module("openmontage")\n', encoding="utf-8")
    (tmp_path / "d.py").write_text("subprocess_cmd = ['openmontage', 'demo']\n", encoding="utf-8")

    hits = _forbidden_imports(tmp_path)

    assert len(hits) == 3
    assert any("a.py" in h and "postiz" in h for h in hits)
    assert any("b.py" in h and "voicestudio" in h.lower() for h in hits)
    assert any("c.py" in h and "openmontage" in h for h in hits)
