"""U14: code with no reader in `src/`, and pointers to files and commands that do not exist.

What was found (areas A and C of the untangle review, re-checked with a grep over src, tests, scripts, docs, skills, plugin.json,
modules and pyproject before anything was deleted; no dispatch by name, `getattr` or MCP tool reaches any of them):

* `social.DEFAULT_PROVIDER` and `swap_providers.base.PRICES_READ_ON`: module constants nobody reads; `social._context(plan, provider,
  clip_id, step)`: its `provider` is never used (both callers pass the same value they already used for something else);
* `simplicio_video/mock_gemini.py`: a local mock of the Gemini TTS API with no importer and no test, shipped in the wheel. It is a tool
  for the tests, so it lives in `tests/tools/mock_gemini.py` (the wheel loses that one file: declared in the PR);
* `voice.py` pointed at `scripts/mock_gemini_tts.py` (never existed) and at the "legacy scripts/voice.py" without saying it is gone;
  `engine/build.mjs` told the user to run `npm run voice` and cited `scripts/voice.py`: the compiled project has no package.json and
  the command that renders the voice is `simplicio-video voice <contrato>`;
* `scripts/smoke_trilhas.py::_checar_mcp` had a SKIP for a track with no MCP call, which cannot happen since `MCP_LEITURA` is made
  from `tools.TOOLS` (and `tests/packaging/test_registro_trilhas.py` says every track has an `mcp_read`).

CHARACTERIZATION (green before and after): the mock behaves as documented, from where it is. STRUCTURE (red before): each of the above.
What is NOT here, on purpose: `tools.COMMANDS`, `doctor_trilhas.CLONE` and `DEPS` are read only by tests, and `DEP_NOMES` and the
`t.name == "video_to_skill"` of `doctor_trilhas._upstream` are read by production code: the review did not confirm them dead.

V3 (the last sweep of the untangling, after U14): the same two halves for what is left. Four names nothing reads (`installer.read_node`,
`clone.HYPIT_REPO`, `tools_lock._KEYS`, `catalog.GRUPOS_ANGULOS`); fifteen "old name" aliases and pass-through wrappers that only a test
read (`edit._output_values`, `media._parse`, `shorts._parse`, `rea_video._SPECS`, `busca._versao_cli`, `jobs.GRACE_S`, `jobs.data_root`,
`jobs.grace`, `tools_update.checkout_for` and the six module-level helpers of `voicestudio`), plus the item access of `jobs.KINDS` (a dict
of lambdas per kind): the tests call the public target now; and the `home` parameter that `render.preview_font` and `scaffold.skeleton`
never read.
CHARACTERIZATION (green before and after): the public names answer what the aliases answered; nothing reads a dead name; the group
choices of `list angles` are the groups of the data. STRUCTURE (red before): each name above has no definition in `src/`, the closed list of
kinds has no item to read, the two functions take no `home`, and no test spells the list of kinds again (it is one golden, in
tests/helpers/kinds.py). No name was kept because of a `monkeypatch.setattr` (none of them is patched by any test); `paths.jobs_root`,
the alias `jobs` used to call, stays because `montage.py` and the V1 tests still use it.
"""
from __future__ import annotations

import ast
import base64
import functools
import importlib
import importlib.util
import inspect
import io
import json
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import wave
from pathlib import Path

import pytest

from simplicio_video import social, voice
from simplicio_video.swap_providers import base
from helpers import KINDS_DE_HOJE, ROOT, SRC

MOCK = ROOT / "tests" / "tools" / "mock_gemini.py"


# ------------------------------------------------------------------------------------------------ the mock leaves the package

def test_the_gemini_mock_is_not_part_of_the_package():
    assert not (SRC / "mock_gemini.py").exists()
    assert importlib.util.find_spec("simplicio_video.mock_gemini") is None
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("simplicio_video.mock_gemini")


def test_nothing_in_the_package_or_the_scripts_names_the_old_module():
    for pasta in (SRC, ROOT / "scripts", ROOT / "tests"):
        for arquivo in pasta.rglob("*.py"):
            if arquivo == Path(__file__).resolve():
                continue
            texto = arquivo.read_text(encoding="utf-8", errors="replace")
            assert "simplicio_video.mock_gemini" not in texto, arquivo
            assert "from simplicio_video import mock_gemini" not in texto, arquivo


def _livre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _espera(porta: int, processo: subprocess.Popen) -> None:
    fim = time.monotonic() + 15
    while time.monotonic() < fim:
        assert processo.poll() is None, processo.stderr.read().decode() if processo.stderr else "the mock ended"
        try:
            socket.create_connection(("127.0.0.1", porta), timeout=0.5).close()
            return
        except OSError:
            time.sleep(0.05)
    raise AssertionError("the mock did not listen")


def _post(url: str, corpo: dict, chave: str | None = "mock") -> dict:
    cabecalhos = {"Content-Type": "application/json", **({"x-goog-api-key": chave} if chave else {})}
    pedido = urllib.request.Request(url, data=json.dumps(corpo).encode(), headers=cabecalhos, method="POST")
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(pedido, timeout=20) as r:
        return json.loads(r.read())


def _wav(dados: bytes) -> tuple[int, int, int, int]:
    with wave.open(io.BytesIO(dados)) as w:
        return w.getframerate(), w.getnchannels(), w.getsampwidth(), w.getnframes()


@pytest.mark.allow_hosts(["127.0.0.1", "::1", "localhost"])  # a throwaway server on loopback, never the network
def test_the_mock_serves_both_gemini_apis_from_tests_tools(tmp_path, monkeypatch):
    """`python tests/tools/mock_gemini.py --port N --overlong-first 1 --log F`: what its own docstring promises."""
    assert MOCK.is_file(), "the mock moved to tests/tools/mock_gemini.py"
    porta, log = _livre(), tmp_path / "mock.jsonl"
    p = subprocess.Popen([sys.executable, str(MOCK), "--port", str(porta), "--overlong-first", "1", "--log", str(log)],
                         stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, cwd=tmp_path)
    try:
        _espera(porta, p)
        monkeypatch.setenv("SIMPLICIO_GEMINI_BASE", f"http://127.0.0.1:{porta}/v1beta")
        texto = "uma frase de teste"  # 18 characters: 60 ms each = 1.08 s of tone
        interactions = {"api": "interactions", "model": "gemini-mock", "voice": "Kore", "estilo": "calmo"}
        generate = {"api": "generate_content", "model": "gemini-mock", "voice": "Puck", "estilo": ""}

        url, corpo = voice.gemini_request(interactions, texto)
        longa, mime = voice.gemini_audio(_post(url, corpo))  # the first request: a take 2.5x too long
        assert mime == "audio/wav"
        taxa, canais, largura, quadros = _wav(longa)
        assert (taxa, canais, largura) == (24000, 1, 2) and quadros == int(24000 * max(0.4, 0.06 * len(texto)) * 2.5)

        curta, _ = voice.gemini_audio(_post(*voice.gemini_request(interactions, texto)))
        assert _wav(curta)[3] == int(24000 * max(0.4, 0.06 * len(texto)))  # then the normal one

        url, corpo = voice.gemini_request(generate, texto)
        assert "generateContent" in url
        outra, _ = voice.gemini_audio(_post(url, corpo))
        assert _wav(outra)[:3] == (24000, 1, 2) and _wav(outra)[3] == _wav(curta)[3]

        with pytest.raises(urllib.error.HTTPError) as sem_chave:
            _post(*voice.gemini_request(interactions, texto), chave=None)
        assert sem_chave.value.code == 401

        linhas = [json.loads(ln) for ln in log.read_text(encoding="utf8").splitlines()]
        assert [(r["voice"], r["style"], r["text"], r["overlong"]) for r in linhas] == [
            ("Kore", "calmo", texto, True), ("Kore", "calmo", texto, False), ("Puck", "", texto, False)]
        assert linhas[0]["path"].endswith("/interactions") and linhas[2]["path"].endswith(":generateContent")
        assert linhas[2]["model"] == "gemini-mock"
    finally:
        p.terminate()
        p.wait(10)


def test_the_mock_tone_is_a_valid_wav_and_the_module_needs_nothing_of_the_package():
    """Loaded by path: it imports only the standard library, so it works from tests/tools with nothing of the package."""
    spec = importlib.util.spec_from_file_location("mock_gemini_de_teste", MOCK)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    dados = modulo.take("oi")
    assert dados[:4] == b"RIFF" and _wav(dados) == (24000, 1, 2, int(24000 * 0.4))  # the floor of 0.4 s for a short text
    assert base64.b64decode(base64.b64encode(dados)) == dados


# ------------------------------------------------------------------------------------------------ pointers to what is not there

def test_voice_py_points_to_the_mock_where_it_is_and_says_the_legacy_script_is_gone():
    texto = (SRC / "voice.py").read_text(encoding="utf-8")
    assert "scripts/mock_gemini_tts.py" not in texto  # never existed
    assert "tests/tools/mock_gemini.py" in texto and MOCK.is_file()
    cabeca = texto.split('"""')[1]
    # `scripts/voice.py` was the script of the per-video projects (clients/ left the repository): the docstring says so
    assert (ROOT / "scripts" / "voice.py").exists() or "scripts/voice.py" not in cabeca or "no longer in this repository" in cabeca


def test_build_mjs_cites_no_command_that_does_not_exist():
    texto = (SRC / "engine" / "build.mjs").read_text(encoding="utf-8")
    assert "npm run" not in texto, "the compiled project has no package.json: there is no `npm run` to cite"
    assert "scripts/voice.py" not in texto
    from simplicio_video import cli
    registrados = set(next(a for a in cli.build_parser()._actions if a.__class__.__name__ == "_SubParsersAction").choices)
    citados = set(re.findall(r"`simplicio-video ([a-z][a-z-]*)", texto))
    assert citados and citados <= registrados, sorted(citados - registrados)
    assert "voice" in citados
    assert texto.count("simplicio-video voice <contrato>") >= 3  # the three messages of a voice that was not rendered


# ------------------------------------------------------------------------------------------------ names with no reader

def test_social_has_no_default_provider_constant():
    assert not hasattr(social, "DEFAULT_PROVIDER")


def test_the_context_of_a_recipe_takes_no_provider_it_never_used():
    assert list(inspect.signature(social._context).parameters) == ["plan", "clip_id", "step"]


def test_swap_providers_base_has_no_prices_read_on_constant():
    assert not hasattr(base, "PRICES_READ_ON")
    assert base.FX["brl_per_usd"] > 0 and "2026-10-15" in base.FX["source"]  # the date that is read lives in the exchange rate


def test_the_smoke_has_no_skip_for_a_track_with_no_mcp_call():
    """`MCP_LEITURA` is made from `tools.TOOLS`, so `.get(nome)` is never None: the branch (and its SKIP) could not run."""
    arvore = ast.parse((ROOT / "scripts" / "smoke_trilhas.py").read_text(encoding="utf-8"))
    funcao = next(n for n in ast.walk(arvore) if isinstance(n, ast.FunctionDef) and n.name == "_checar_mcp")
    sem_chamada = [n for n in ast.walk(funcao) if isinstance(n, ast.Compare) and any(isinstance(op, ast.Is) for op in n.ops)
                   and isinstance(n.left, ast.Name) and n.left.id == "chamada"]
    assert not sem_chamada, "`_checar_mcp` still tests `chamada is None`"
    assert "sem chamada MCP de leitura no smoke" not in (ROOT / "scripts" / "smoke_trilhas.py").read_text(encoding="utf-8")


# ================================================================================================================ V3: the last sweep
# What each name below was, and what the code and the tests call instead:

SEM_LEITOR = [  # S1: nothing in src, tests, scripts, docs, data, plugin.json, pyproject or skills reads them
    ("installer", "read_node"),  # a helper nothing called
    ("clone", "HYPIT_REPO"),  # a URL constant: the repository is named in text only (docstring, help, error); the engine runs tools.TOOLS["hypit"]
    ("tools_lock", "_KEYS"),  # a tuple of the keys of a lock entry that nothing iterated
    ("catalog", "GRUPOS_ANGULOS"),  # a dead copy of the literal `--grupo` choices of `list angles` in cli.py
]
APELIDOS = [  # S2: "old name" aliases and pass-through wrappers that only a test read; `-> the public target the tests call now`
    ("edit", "_output_values"),  # -> edit.output_values
    ("media", "_parse"),  # -> media.parse_argv
    ("shorts", "_parse"),  # -> shorts.parse_argv
    ("rea_video", "_SPECS"),  # -> rea_video.SPECS
    ("busca", "_versao_cli"),  # -> busca.versao_cli
    ("jobs", "GRACE_S"),  # -> paths.JOBS_GRACE_S
    ("jobs", "data_root"),  # -> paths.data_root
    ("jobs", "grace"),  # -> paths.jobs_grace_s
    ("tools_update", "checkout_for"),  # -> tools.checkout_dir
    ("voicestudio", "status"),  # -> VoiceStudio().status
    ("voicestudio", "voices"),  # -> VoiceStudio().list_voices
    ("voicestudio", "languages"),  # -> VoiceStudio().list_languages
    ("voicestudio", "speak"),  # -> VoiceStudio().speak
    ("voicestudio", "transcribe"),  # -> VoiceStudio().transcribe
    ("voicestudio", "clone_voice"),  # -> VoiceStudio().clone_voice
]
SEM_NOME_DOS_DONOS = [  # names that mean nothing else anywhere: any read of them, whoever the owner, is a read of the dead one
    "read_node", "HYPIT_REPO", "_KEYS", "GRUPOS_ANGULOS", "_output_values", "_versao_cli", "_SPECS", "GRACE_S", "checkout_for",
]
COM_DONOS = [  # names that other modules use for other things (`paths.data_root`, `VoiceStudio.status`...): read only as an attribute of these
    # (module, name, owners, also a bare read inside the module's own file: `grace()` was called in jobs.py; in voicestudio.py `status` is also
    # the name of a parameter)
    ("media", "_parse", ("media",), True), ("shorts", "_parse", ("shorts",), True), ("jobs", "data_root", ("jobs",), True),
    ("jobs", "grace", ("jobs",), True),
    *[("voicestudio", nome, ("voicestudio", "vs", "module"), False) for nome in ("status", "voices", "languages", "speak", "transcribe", "clone_voice")],
]


def _nomes_do_modulo(modulo: str) -> set[str]:
    """Every name the source of `modulo` binds at module level: defs, classes, assignments and imports (also inside a top-level if/try)."""
    def alvos(no):
        if isinstance(no, ast.Name):
            yield no.id
        elif isinstance(no, (ast.Tuple, ast.List)):
            for e in no.elts:
                yield from alvos(e)

    def corpo(comandos):
        for c in comandos:
            if isinstance(c, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                yield c.name
            elif isinstance(c, ast.Assign):
                for t in c.targets:
                    yield from alvos(t)
            elif isinstance(c, (ast.AnnAssign, ast.AugAssign)):
                yield from alvos(c.target)
            elif isinstance(c, (ast.Import, ast.ImportFrom)):
                for a in c.names:
                    yield (a.asname or a.name).split(".")[0]
            elif isinstance(c, (ast.If, ast.Try, ast.With, ast.For, ast.While)):
                for campo in ("body", "orelse", "finalbody"):
                    yield from corpo(getattr(c, campo, []))
                for h in getattr(c, "handlers", []):
                    yield from corpo(h.body)
    return set(corpo(ast.parse((SRC / f"{modulo}.py").read_text(encoding="utf-8")).body))


@pytest.mark.parametrize("modulo,nome", SEM_LEITOR + APELIDOS, ids=[f"{m}.{n}" for m, n in SEM_LEITOR + APELIDOS])
def test_a_dead_name_or_an_old_name_has_no_definition_left_in_the_source(modulo, nome):
    assert nome not in _nomes_do_modulo(modulo), f"src/simplicio_video/{modulo}.py still binds `{nome}`"


@functools.lru_cache(maxsize=None)
def _arvores_do_repo() -> tuple[tuple[str, ast.AST], ...]:
    """The syntax tree of every .py of src, tests and scripts, but this file (it spells every name on purpose); parsed once."""
    achados = []
    for pasta in (SRC, ROOT / "tests", ROOT / "scripts"):
        for arquivo in sorted(pasta.rglob("*.py")):
            if arquivo.resolve() == Path(__file__).resolve():
                continue
            try:
                achados.append((arquivo.relative_to(ROOT).as_posix(), ast.parse(arquivo.read_text(encoding="utf-8", errors="replace"))))
            except SyntaxError:  # a deliberately broken fixture is not code that reads a name
                continue
    return tuple(achados)


@functools.lru_cache(maxsize=None)
def _indice_de_leituras() -> dict[str, list[tuple[str, str | None, str]]]:
    """name -> [(`path:line`, owner, how)] for every way the code of src, tests and scripts can read a name: a bare Name (owner None), an
    attribute of a bare Name (owner = that name), an import of it (owner = the last part of the module), the string of a `getattr`/
    `hasattr`/`setattr`/`delattr` (a `monkeypatch.setattr(owner, "name", ...)` is one) or any other string equal to it (owner None)."""
    indice: dict[str, list[tuple[str, str | None, str]]] = {}

    def anota(nome, rel, linha, dono, como):
        indice.setdefault(nome, []).append((f"{rel}:{linha}", dono, como))

    for rel, arvore in _arvores_do_repo():
        for n in ast.walk(arvore):
            if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load):
                anota(n.id, rel, n.lineno, None, "name")
            elif isinstance(n, ast.Attribute) and isinstance(n.ctx, ast.Load):
                anota(n.attr, rel, n.lineno, n.value.id if isinstance(n.value, ast.Name) else None, "attribute")
            elif isinstance(n, ast.ImportFrom):
                for a in n.names:
                    anota(a.name, rel, n.lineno, (n.module or "").split(".")[-1], "import")
            elif isinstance(n, ast.Call) and len(n.args) >= 2 and isinstance(n.args[1], ast.Constant) and isinstance(n.args[1].value, str):
                funcao = n.func.attr if isinstance(n.func, ast.Attribute) else getattr(n.func, "id", "")
                if funcao in ("getattr", "hasattr", "setattr", "delattr"):
                    anota(n.args[1].value, rel, n.lineno, n.args[0].id if isinstance(n.args[0], ast.Name) else None, "by string")
            elif isinstance(n, ast.Constant) and isinstance(n.value, str) and len(n.value) < 40:
                anota(n.value, rel, n.lineno, None, "string")
    return indice


def _leituras(nome: str, donos: tuple[str, ...] | None, arquivo_proprio: str | None = None) -> list[str]:
    """`path:line` of every read of `nome` outside this file: anywhere when `donos` is None (a name that means nothing else), else only as
    an attribute, import or `getattr`-by-string of one of those owners, and, with `arquivo_proprio`, as a bare name inside that file."""
    return [onde for onde, dono, como in _indice_de_leituras().get(nome, [])
            if donos is None or (dono in donos and como in ("attribute", "import", "by string"))
            or (arquivo_proprio and como == "name" and onde.startswith(f"{arquivo_proprio}:"))]


@pytest.mark.parametrize("nome", SEM_NOME_DOS_DONOS)
def test_nothing_reads_a_name_that_means_nothing_else(nome):
    """No name, attribute, import or string of the repository's code reads it: not src, not a test, not a script (a `getattr` or a
    `monkeypatch.setattr` by string counts)."""
    achados = _leituras(nome, None)
    assert achados == [], f"`{nome}` is still read at:\n" + "\n".join(achados)


@pytest.mark.parametrize("modulo,nome,donos,propria", COM_DONOS, ids=[f"{m}.{n}" for m, n, _, _ in COM_DONOS])
def test_nothing_reads_the_old_name_as_an_attribute_of_its_module(modulo, nome, donos, propria):
    achados = _leituras(nome, donos, f"src/simplicio_video/{modulo}.py" if propria else None)
    assert achados == [], f"`{modulo}.{nome}` is still read at:\n" + "\n".join(achados)


# ---- the public names that the aliases forwarded to answer what the aliases answered (green before and after)

def test_edit_output_values_reads_every_spelling_of_the_output_option():
    from simplicio_video import edit
    assert edit.output_values(["a", "-o", "/x", "--ou", "y", "--outpu=z", "-ow", "-o=q"]) == ["/x", "y", "z", "w", "q"]
    assert edit.output_values(["a", "--", "-o", "x"]) == [] and edit.output_values(["a", "--preset", "p"]) == []


def test_media_and_shorts_parse_argv_split_the_positionals_from_the_values():
    from simplicio_video import media, shorts
    assert media.parse_argv(["reel.mp4", "--box", "1,2,3,4", "-o", "x.mp4", "--keep-length"]) == (
        ["reel.mp4"], {"--box": "1,2,3,4", "-o": "x.mp4", "--keep-length": "1"})
    assert shorts.parse_argv(["in.mp4", "--subs", "-o", "out.mp4", "--dry-run", "--max", "3"]) == (
        ["in.mp4"], {"--subs", "--dry-run"}, {"-o": "out.mp4", "--max": "3"})


def test_rea_video_specs_is_the_table_of_the_commands_the_mcp_checks():
    from simplicio_video import rea_video
    assert list(rea_video.SPECS) == ["summary", "probe", "tiles", "stems", "review", "apply-review", "remake-plan", "decompose"]


def test_busca_exports_versao_cli_and_it_says_none_for_a_binary_that_does_not_run(tmp_path):
    from simplicio_video import busca
    assert "versao_cli" in busca.__all__ and callable(busca.versao_cli)
    assert busca.versao_cli(str(tmp_path / "no-such-tinyfish")) is None


def test_the_jobs_keep_their_state_under_the_data_root_and_wait_the_grace_of_the_environment(monkeypatch, tmp_path):
    from simplicio_video import jobs, paths
    monkeypatch.setenv("SIMPLICIO_VIDEO_DATA", str(tmp_path / "dados"))
    assert paths.data_root() == tmp_path / "dados" and jobs.jobs_dir() == tmp_path / "dados" / "jobs"
    monkeypatch.setenv("SIMPLICIO_JOBS_GRACE_S", "7")
    assert paths.jobs_grace_s() == 7.0
    monkeypatch.delenv("SIMPLICIO_JOBS_GRACE_S")
    assert paths.jobs_grace_s() == paths.JOBS_GRACE_S == 15.0


def test_the_closed_list_of_kinds_is_a_list_of_names_and_the_kind_is_read_from_its_job_spec():
    from simplicio_video import jobs
    assert list(jobs.KINDS) == KINDS_DE_HOJE and len(jobs.KINDS) == len(KINDS_DE_HOJE)
    assert "rea-video" in jobs.KINDS and "nada" not in jobs.KINDS
    for kind in KINDS_DE_HOJE:
        spec = jobs.job_spec(kind)
        assert spec.kind == kind and all(callable(f) for f in (spec.prepare, spec.argv, spec.result)), kind


def test_the_group_choices_of_list_angles_are_the_groups_of_the_data():
    """`catalog.GRUPOS_ANGULOS` was a dead copy of the choices written in cli.py: the one literal that stays has a check against the data."""
    from simplicio_video import cli
    sub = next(a for a in cli.build_parser()._actions if a.__class__.__name__ == "_SubParsersAction")
    grupo = next(a for a in sub.choices["list"]._actions if "--grupo" in a.option_strings)
    dados = json.loads((SRC / "data" / "angles" / "angles.json").read_text(encoding="utf-8"))
    assert sorted(grupo.choices) == sorted({a["grupo"] for a in dados["angulos"]}) and len(grupo.choices) == 5


# ---- structure (red before)

def test_the_closed_list_of_kinds_has_no_item_to_read():
    """`jobs.KINDS[kind]` built a dict of three lambdas per kind that only tests read: the hooks of a kind are its `JobSpec`."""
    from simplicio_video import jobs
    assert not hasattr(type(jobs.KINDS), "__getitem__")
    with pytest.raises(TypeError):
        jobs.KINDS["rea-video"]


def test_preview_font_and_skeleton_take_no_home_and_the_neighbour_that_reads_it_keeps_it():
    from simplicio_video import render, scaffold
    assert list(inspect.signature(render.preview_font).parameters) == []
    assert list(inspect.signature(scaffold.skeleton).parameters) == ["slug", "campanha", "template", "ano", "nome", "drive_nome"]
    assert list(inspect.signature(render.preview_logo).parameters) == ["home"]  # the logo lives under the checkout: this one reads it


def test_no_function_of_the_source_takes_a_home_it_never_reads():
    achados = []
    for rel, arvore in _arvores_do_repo():
        if not rel.startswith("src/"):
            continue
        for fn in ast.walk(arvore):
            if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)) and any(a.arg == "home" for a in (*fn.args.posonlyargs, *fn.args.args, *fn.args.kwonlyargs)):
                if not any(isinstance(n, ast.Name) and n.id == "home" and isinstance(n.ctx, ast.Load) for n in ast.walk(fn)):
                    achados.append(f"{rel}:{fn.lineno} {fn.name}(home)")
    assert achados == []


def test_the_kinds_golden_is_a_literal_and_no_test_spells_the_list_again():
    """H6: the list was typed in five tests. One golden, in tests/helpers/kinds.py, stays a LITERAL (never derived from the code: the
    point is to freeze today's list and its order); every other test imports it."""
    golden = ROOT / "tests" / "helpers" / "kinds.py"
    arvore = ast.parse(golden.read_text(encoding="utf-8"))
    atribuicoes = [n for n in arvore.body if isinstance(n, ast.Assign) and [t.id for t in n.targets if isinstance(t, ast.Name)] == ["KINDS_DE_HOJE"]]
    assert len(atribuicoes) == 1 and isinstance(atribuicoes[0].value, ast.List)
    assert len(atribuicoes[0].value.elts) == 6 and all(isinstance(e, ast.Constant) and isinstance(e.value, str) for e in atribuicoes[0].value.elts)
    assert not any(isinstance(n, (ast.Import, ast.ImportFrom)) for n in arvore.body), "a golden imports nothing: it must not follow the code"
    copias = []
    for rel, arvore in _arvores_do_repo():
        if not rel.startswith("tests/") or rel == "tests/helpers/kinds.py":
            continue
        for n in ast.walk(arvore):
            if isinstance(n, (ast.List, ast.Tuple, ast.Set)):
                nomes = {e.value for e in n.elts if isinstance(e, ast.Constant) and isinstance(e.value, str)}
                if set(KINDS_DE_HOJE) <= nomes:  # the whole list (a parametrize over a subset of the kinds is another thing)
                    copias.append(f"{rel}:{n.lineno}")
    assert copias == [], "import KINDS_DE_HOJE from helpers instead of typing the list:\n" + "\n".join(copias)


# ---- the two callers of `scaffold.skeleton` and the places that now ask the owner (the sites V3 touched; each was a surviving mutant)

def test_init_writes_the_same_contract_from_the_cli_and_from_the_mcp_tool(tmp_path):
    """`cli init` and `video.init` both hand `scaffold.skeleton` the same words in the same order: same inputs, same bytes."""
    import yaml
    from simplicio_video import cli, mcp_server
    por_cli, por_mcp = tmp_path / "cli" / "contract.yaml", tmp_path / "mcp" / "contract.yaml"
    assert cli.main(["init", "acme", "Dia das Maes", "--template", "saude-odontologia", "--nome", "Acme Exemplo", "--ano", "2031",
                     "--out", str(por_cli)]) == 0
    assert mcp_server.video_init("acme", "Dia das Maes", "saude-odontologia", nome="Acme Exemplo", ano=2031, out=str(por_mcp))["ok"] is True
    contrato = yaml.safe_load(por_cli.read_text(encoding="utf-8"))
    assert (contrato["cliente"]["slug"], contrato["cliente"]["nome"], contrato["campanha"]["id"], contrato["campanha"]["ano"],
            contrato["template"]) == ("acme", "Acme Exemplo", "Dia_Das_Maes", 2031, "saude-odontologia")
    assert por_cli.read_bytes() == por_mcp.read_bytes()


def _chamadas_de(rel: str, funcao: str, dono: str) -> set[str]:
    """The names `dono.<name>(...)` that the function `funcao` of the file `rel` calls."""
    arvore = ast.parse((ROOT / rel).read_text(encoding="utf-8"))
    no = next(n for n in ast.walk(arvore) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == funcao)
    return {n.func.attr for n in ast.walk(no) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
            and isinstance(n.func.value, ast.Name) and n.func.value.id == dono}


@pytest.mark.parametrize("funcao,nome", [("jobs_dir", "data_root"), ("cancel", "jobs_grace_s"), ("_runner", "jobs_grace_s")])
def test_jobs_asks_paths_for_the_data_root_and_for_the_grace(funcao, nome):
    """What `jobs.data_root()` and `jobs.grace()` forwarded, the three sites now ask the owner (`paths`): the folder of the job states,
    the budget of a cancel and the wait the runner gives a task before the SIGKILL."""
    assert nome in _chamadas_de("src/simplicio_video/jobs.py", funcao, "paths")


def test_jobs_never_reads_the_default_of_the_grace_as_if_it_were_the_answer():
    """`paths.JOBS_GRACE_S` is only the default of `paths.jobs_grace_s()` (which reads SIMPLICIO_JOBS_GRACE_S): jobs.py must not use it."""
    lidos = {n.attr for n in ast.walk(ast.parse((SRC / "jobs.py").read_text(encoding="utf-8"))) if isinstance(n, ast.Attribute)}
    assert "JOBS_GRACE_S" not in lidos
