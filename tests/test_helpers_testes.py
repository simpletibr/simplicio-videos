"""U17: o contrato de cada helper de teste compartilhado (tests/helpers/).

Os helpers viviam copiados de arquivo em arquivo (`ROOT`, `_edit`, `_ffmpeg_ou_pula`, `needs_ffmpeg`, `vivo`/`espera`, `_run`, `_mp4`,
`_isolated`, `_wav`) e em tests/conftest.py (`offline_env`, `run_cli`, `needs_client`...). Aqui fica o que cada um faz, para que a
troca das cópias por `from helpers import ...` não mude o que os testes enxergam.

O módulo `helpers` é importado dentro de cada teste (não no topo): sem ele, cada teste falha com ModuleNotFoundError e os ids
continuam coletáveis.
"""

import copy
import io
import os
import struct
import subprocess
import sys
import time
import wave
from pathlib import Path

import pytest
import yaml

TESTS = Path(__file__).resolve().parent


def h():
    import helpers
    return helpers


def _exe(pasta: Path, *nomes: str) -> Path:
    pasta.mkdir(parents=True, exist_ok=True)
    for nome in nomes:
        p = pasta / nome
        p.write_text("#!/bin/sh\nexit 0\n")
        p.chmod(0o755)
    return pasta


def _python_limpo(codigo: str, path: str, **extra: str) -> subprocess.CompletedProcess:
    """Run `codigo` in a fresh interpreter whose PATH is exactly `path` and that can import tests/helpers."""
    env = {"PATH": path, "PYTHONPATH": str(TESTS), "SIMPLICIO_OFFLINE": "1", **extra}
    return subprocess.run([sys.executable, "-c", codigo], env=env, capture_output=True, text=True, timeout=60)


# ------------------------------------------------------------------------------------------------ onde o pacote resolve

def test_helpers_resolves_to_the_package_inside_tests_not_to_something_else_on_the_path():
    helpers = h()
    assert Path(helpers.__file__).resolve() == TESTS / "helpers" / "__init__.py"
    assert [Path(p).resolve() for p in helpers.__path__] == [TESTS / "helpers"]


def test_helpers_imports_in_a_fresh_interpreter_with_only_tests_on_the_path(tmp_path):
    r = _python_limpo("import helpers; print(helpers.ROOT)", path=str(tmp_path))
    assert r.returncode == 0, r.stderr
    assert Path(r.stdout.strip()) == TESTS.parent


def test_importing_helpers_does_not_import_the_engine():
    # a test that only wants ROOT must not pay for (or be broken by) importing simplicio_video at collection time
    r = _python_limpo("import sys, helpers; print(sorted(m for m in sys.modules if m.split('.')[0] == 'simplicio_video'))", path="")
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "[]"


# ------------------------------------------------------------------------------------------------ ROOT, SRC, FIXTURE e os contratos de cliente

def test_root_is_the_repository_root():
    helpers = h()
    assert helpers.ROOT == TESTS.parent
    assert helpers.ROOT.is_absolute() and helpers.ROOT == helpers.ROOT.resolve()
    assert (helpers.ROOT / "pyproject.toml").is_file()
    assert (helpers.ROOT / "src" / "simplicio_video" / "__init__.py").is_file()
    assert (helpers.ROOT / "tests" / "helpers" / "__init__.py").is_file()


def test_src_is_the_engine_package_folder():
    helpers = h()
    assert helpers.SRC == helpers.ROOT / "src" / "simplicio_video"
    assert (helpers.SRC / "cli.py").is_file()


def test_fixture_is_the_mini_project_and_the_client_contracts_are_under_clients():
    helpers = h()
    assert helpers.FIXTURE == helpers.ROOT / "tests" / "fixtures" / "mini"
    assert (helpers.FIXTURE / "contract.yaml").is_file()
    assert helpers.WJR == helpers.ROOT / "clients" / "wjr-informatica-games" / "video-01" / "contract.yaml"
    assert helpers.LOTHUS == helpers.ROOT / "clients" / "lothus-odontologia" / "video-01-dia-das-criancas" / "contract.yaml"


def test_needs_client_skips_only_when_some_contract_is_missing(tmp_path):
    helpers = h()
    existe = tmp_path / "a.yaml"
    existe.write_text("x: 1\n")
    falta = tmp_path / "b.yaml"
    ok, um_falta, todos_faltam = helpers.needs_client(existe), helpers.needs_client(existe, falta), helpers.needs_client(falta)
    assert [m.name for m in (ok, um_falta, todos_faltam)] == ["skipif"] * 3
    assert [m.args[0] for m in (ok, um_falta, todos_faltam)] == [False, True, True]
    assert ok.kwargs["reason"] == um_falta.kwargs["reason"] == helpers.CLIENT_DATA_REASON
    assert "clients/" in helpers.CLIENT_DATA_REASON


def _contrato_de_cliente(pasta: Path) -> Path:
    (pasta / "coleta").mkdir(parents=True)
    (pasta / "preview").mkdir()
    (pasta / "node_modules").mkdir()
    (pasta / "preview" / "p.mp4").write_bytes(b"x")
    (pasta / "node_modules" / "m.js").write_text("x")
    (pasta / "coleta" / "ja-existe.png").write_bytes(b"REAL")
    c = pasta / "contract.yaml"
    c.write_text(yaml.safe_dump({
        "assets": [{"arquivo": "coleta/foto.png"}, {"arquivo": "coleta/ja-existe.png"}],
        "placas_video": [{"file": "coleta/placa.mp4"}],
        "marca": {"logo": {"arquivo": "coleta/logo/logo.png"}},
    }))
    return c


def test_contract_with_coleta_placeholders_creates_every_missing_asset_and_keeps_the_existing_ones(tmp_path):
    helpers = h()
    origem = _contrato_de_cliente(tmp_path / "origem")
    copia = helpers.contract_with_coleta_placeholders(origem, tmp_path / "dest")
    assert copia == tmp_path / "dest" / "a" / "video" / "contract.yaml"
    base = copia.parent
    assert (base / "coleta" / "foto.png").read_bytes() == b"\x89PNG\r\n\x1a\n" + b"coleta/foto.png"
    assert (base / "coleta" / "placa.mp4").read_bytes() == b"\x89PNG\r\n\x1a\n" + b"coleta/placa.mp4"
    assert (base / "coleta" / "logo" / "logo.png").read_bytes() == b"\x89PNG\r\n\x1a\n" + b"coleta/logo/logo.png"
    assert (base / "coleta" / "ja-existe.png").read_bytes() == b"REAL"
    assert not (origem.parent / "coleta" / "foto.png").exists()  # the source tree is never written
    assert not (base / "preview").exists() and not (base / "node_modules").exists()
    assert yaml.safe_load(copia.read_text()) == yaml.safe_load(origem.read_text())


def test_contract_with_coleta_placeholders_refuses_an_asset_that_escapes_the_temporary_folder(tmp_path):
    helpers = h()
    origem = tmp_path / "origem"
    origem.mkdir()
    (origem / "contract.yaml").write_text(yaml.safe_dump({"assets": [{"arquivo": "../../fora.png"}]}))
    with pytest.raises(AssertionError):
        helpers.contract_with_coleta_placeholders(origem / "contract.yaml", tmp_path / "dest")
    assert not (tmp_path / "fora.png").exists()


# ------------------------------------------------------------------------------------------------ offline_env, run_cli, have_render_tools

def test_offline_env_is_offline_keeps_the_environment_and_lets_extra_win(monkeypatch):
    helpers = h()
    monkeypatch.setenv("U17_MARCA", "viva")
    monkeypatch.setenv("PYTHONPATH", "/antes")
    env = helpers.offline_env(U17_MARCA="sobrescrita", U17_NOVA="1")
    assert env["SIMPLICIO_OFFLINE"] == "1"
    assert env["U17_MARCA"] == "sobrescrita" and env["U17_NOVA"] == "1"
    assert env["PATH"] == os.environ["PATH"]
    primeiro, _, resto = env["PYTHONPATH"].partition(os.pathsep)
    assert resto == "/antes"
    assert (Path(primeiro) / "sitecustomize.py").is_file()
    assert os.environ["PYTHONPATH"] == "/antes" and "U17_NOVA" not in os.environ  # a copy, not the live environment


def test_offline_env_shares_one_sitecustomize_folder_per_process():
    helpers = h()
    a = helpers.offline_env()["PYTHONPATH"].split(os.pathsep)[0]
    b = helpers.offline_env()["PYTHONPATH"].split(os.pathsep)[0]
    assert a == b and Path(a).is_dir()


def test_offline_env_blocks_sockets_in_the_child_but_not_unix_sockets():
    helpers = h()
    codigo = ("import socket\n"
              "try:\n    socket.socket(socket.AF_INET)\nexcept Exception as e:\n    print(type(e).__name__)\n"
              "else:\n    print('abriu')\n"
              "socket.socket(socket.AF_UNIX).close()\nprint('unix-ok')\n")
    r = subprocess.run([sys.executable, "-c", codigo], env=helpers.offline_env(), capture_output=True, text=True, timeout=60)
    assert r.stdout.split() == ["SocketBlockedError", "unix-ok"], r.stderr


def test_run_cli_runs_the_cli_offline_and_returns_the_completed_process(tmp_path):
    helpers = h()
    r = helpers.run_cli("--version")
    assert isinstance(r, subprocess.CompletedProcess) and r.returncode == 0, r.stderr
    from simplicio_video import __version__
    assert __version__ in r.stdout + r.stderr
    assert isinstance(r.stdout, str)


def test_run_cli_stringifies_the_arguments_and_honours_cwd(tmp_path):
    helpers = h()
    r = helpers.run_cli("init", "--help", cwd=tmp_path)
    assert r.returncode == 0 and "usage" in r.stdout.lower()
    r2 = helpers.run_cli(Path("--version"))
    assert r2.returncode == 0, r2.stderr


def test_have_render_tools_needs_node_npx_and_ffmpeg_on_the_render_path(tmp_path, monkeypatch):
    helpers = h()
    from simplicio_video import paths
    bin_ = tmp_path / "bin"
    monkeypatch.setattr(paths, "node_env", lambda: {"PATH": str(bin_)})
    bin_.mkdir()
    assert helpers.have_render_tools() is False
    _exe(bin_, "node", "npx")
    assert helpers.have_render_tools() is False  # ffmpeg is still missing
    _exe(bin_, "ffmpeg")
    assert helpers.have_render_tools() is True


# ------------------------------------------------------------------------------------------------ ffmpeg: a marca e o pulo

def test_ffmpeg_ou_pula_skips_with_the_given_reason_when_ffmpeg_is_missing(tmp_path, monkeypatch):
    helpers = h()
    monkeypatch.setenv("PATH", str(tmp_path))
    with pytest.raises(pytest.skip.Exception) as e:
        helpers.ffmpeg_ou_pula("motivo do arquivo")
    assert e.value.msg == "motivo do arquivo"


def test_ffmpeg_ou_pula_needs_ffprobe_too(tmp_path, monkeypatch):
    helpers = h()
    monkeypatch.setenv("PATH", str(_exe(tmp_path / "so-ffmpeg", "ffmpeg")))
    with pytest.raises(pytest.skip.Exception):
        helpers.ffmpeg_ou_pula("x")
    monkeypatch.setenv("PATH", str(_exe(tmp_path / "so-ffprobe", "ffprobe")))
    with pytest.raises(pytest.skip.Exception):
        helpers.ffmpeg_ou_pula("x")


def test_ffmpeg_ou_pula_does_not_skip_when_both_binaries_exist(tmp_path, monkeypatch):
    helpers = h()
    monkeypatch.setenv("PATH", str(_exe(tmp_path / "bin", "ffmpeg", "ffprobe")))
    assert helpers.ffmpeg_ou_pula("x") is None


@pytest.mark.parametrize("presentes, pula", [((), True), (("ffmpeg",), True), (("ffprobe",), True), (("ffmpeg", "ffprobe"), False)])
def test_needs_ffmpeg_is_a_skipif_mark_decided_by_ffmpeg_and_ffprobe_on_the_path(tmp_path, presentes, pula):
    codigo = "import helpers; m = helpers.needs_ffmpeg; print(m.name, m.args[0], m.kwargs['reason'], sep='|')"
    r = _python_limpo(codigo, path=str(_exe(tmp_path / "bin", *presentes)))
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == f"skipif|{pula}|ffmpeg ausente"


# ------------------------------------------------------------------------------------------------ contratos em YAML e o MP4 falso

def test_edit_yaml_applies_fn_to_the_loaded_document_and_writes_it_back_in_order(tmp_path):
    helpers = h()
    p = tmp_path / "c.yaml"
    p.write_text("zeta: 1\nalfa: [a, b]\nnome: Coração\n", encoding="utf8")
    visto = []

    def fn(d):
        visto.append(copy.deepcopy(d))
        d["alfa"].append("c")
        d["novo"] = {"ç": 2}

    assert helpers.edit_yaml(p, fn) is None
    assert visto == [{"zeta": 1, "alfa": ["a", "b"], "nome": "Coração"}]
    esperado = yaml.safe_dump({"zeta": 1, "alfa": ["a", "b", "c"], "nome": "Coração", "novo": {"ç": 2}}, allow_unicode=True, sort_keys=False)
    assert p.read_text(encoding="utf8") == esperado
    assert esperado.splitlines()[0] == "zeta: 1" and "Coração" in esperado  # order kept, accents not escaped


def test_edit_yaml_accepts_a_str_path(tmp_path):
    helpers = h()
    p = tmp_path / "c.yaml"
    p.write_text("a: 1\n")
    helpers.edit_yaml(str(p), lambda d: d.update(b=2))
    assert yaml.safe_load(p.read_text()) == {"a": 1, "b": 2}


def test_edit_yaml_encoding_goes_to_both_the_read_and_the_write(tmp_path):
    helpers = h()
    p = tmp_path / "c.yaml"
    p.write_bytes("nome: João\n".encode("latin-1"))
    helpers.edit_yaml(p, lambda d: d.update(cidade="São Paulo"), encoding="latin-1")
    assert p.read_bytes() == "nome: João\ncidade: São Paulo\n".encode("latin-1")


def test_edit_yaml_without_encoding_uses_the_locale_default_like_path_read_text(tmp_path):
    helpers = h()
    p = tmp_path / "c.yaml"
    p.write_text("nome: João\n")  # the platform default, as the old local copies did
    helpers.edit_yaml(p, lambda d: d.update(x=1))
    assert p.read_text() == "nome: João\nx: 1\n"


def test_fake_mp4_writes_the_content_next_to_the_contract_and_returns_the_path(tmp_path):
    helpers = h()
    contrato = tmp_path / "proj" / "contract.yaml"
    contrato.parent.mkdir()
    p = helpers.fake_mp4(contrato, b"mp4-falso")
    assert p == tmp_path / "proj" / "out" / "mini.mp4"
    assert p.read_bytes() == b"mp4-falso"
    again = helpers.fake_mp4(str(contrato), b"outro")  # a str path; the folder already exists
    assert again == p and p.read_bytes() == b"outro"


# ------------------------------------------------------------------------------------------------ rodar main() e capturar rc/out/err

def test_run_main_returns_rc_stdout_and_stderr(capsys):
    helpers = h()

    def main(argv):
        print("saida", *argv)
        print("erro", file=sys.stderr)
        return 7

    assert helpers.run_main(main, ["a", "b"], capsys) == (7, "saida a b\n", "erro\n")


def test_run_main_turns_systemexit_into_its_code_and_leaves_the_text_alone(capsys):
    helpers = h()

    def main(argv):
        raise SystemExit(2)

    assert helpers.run_main(main, [], capsys) == (2, "", "")

    def texto(argv):
        raise SystemExit("falhou")

    assert helpers.run_main(texto, [], capsys) == ("falhou", "", "")  # as the argparse-only copies did: the code is the text itself

    def vazio(argv):
        raise SystemExit

    assert helpers.run_main(vazio, [], capsys) == (None, "", "")


def test_run_main_text_exit_prints_the_message_to_stderr_and_returns_1(capsys):
    helpers = h()

    def texto(argv):
        raise SystemExit("falhou feio")

    assert helpers.run_main(texto, [], capsys, text_exit=True) == (1, "", "falhou feio\n")

    def argparse_like(argv):
        raise SystemExit(2)

    assert helpers.run_main(argparse_like, [], capsys, text_exit=True) == (2, "", "")


def test_run_main_passes_argv_through_untouched(capsys):
    helpers = h()
    chegou = []
    helpers.run_main(lambda argv: chegou.append(argv) or 0, ["--x", "y"], capsys)
    assert chegou == [["--x", "y"]]


# ------------------------------------------------------------------------------------------------ vivo / espera

def test_vivo_is_true_for_a_running_process_and_false_once_it_is_gone():
    helpers = h()
    p = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    try:
        assert helpers.vivo(p.pid) is True
    finally:
        p.kill()
        p.wait()
    assert helpers.vivo(p.pid) is False


@pytest.mark.skipif(not Path("/proc/self/stat").exists(), reason="a zombie shows as Z in /proc (Linux)")
def test_vivo_counts_an_unreaped_zombie_as_dead():
    helpers = h()
    p = subprocess.Popen([sys.executable, "-c", "pass"])
    deadline = time.monotonic() + 20
    while Path(f"/proc/{p.pid}/stat").read_text().rsplit(")", 1)[1].split()[0] != "Z" and time.monotonic() < deadline:
        time.sleep(0.02)
    try:
        assert helpers.vivo(p.pid) is False
    finally:
        p.wait()


def test_vivo_falls_back_to_kill_zero_without_proc(monkeypatch):
    helpers = h()
    real_read = Path.read_text

    def sem_proc(self, *a, **k):
        if str(self).startswith("/proc/"):
            raise FileNotFoundError(str(self))
        return real_read(self, *a, **k)

    monkeypatch.setattr(Path, "read_text", sem_proc)
    assert helpers.vivo(os.getpid()) is True
    p = subprocess.Popen([sys.executable, "-c", "pass"])
    p.wait()
    assert helpers.vivo(p.pid) is False

    def negado(pid, sinal):
        raise PermissionError

    monkeypatch.setattr(os, "kill", negado)
    assert helpers.vivo(os.getpid()) is True  # exists, just not ours to signal


def test_espera_returns_true_as_soon_as_the_condition_holds():
    helpers = h()
    inicio = time.monotonic()
    assert helpers.espera(lambda: True, 5) is True
    assert time.monotonic() - inicio < 1


def test_espera_polls_until_the_condition_turns_true():
    helpers = h()
    chamadas = []

    def condicao():
        chamadas.append(1)
        return len(chamadas) >= 4

    assert helpers.espera(condicao, 10) is True
    assert len(chamadas) == 4


def test_espera_gives_up_after_the_limit_and_asks_one_last_time():
    helpers = h()
    chamadas = []
    inicio = time.monotonic()
    assert helpers.espera(lambda: chamadas.append(1) and False, 0.3) is False
    decorrido = time.monotonic() - inicio
    assert 0.3 <= decorrido < 3
    assert 4 <= len(chamadas) <= 8  # every 50 ms, plus the final check
    assert helpers.espera(lambda: 1, 0) is True  # a truthy value is coerced to a bool at the deadline


def test_espera_default_wait_is_twenty_seconds():
    import inspect
    assert inspect.signature(h().espera).parameters["segundos"].default == 20.0


# ------------------------------------------------------------------------------------------------ isolar a casa e a pasta das trilhas

def test_isolate_tools_points_home_and_the_tools_dir_into_tmp_path(tmp_path):
    helpers = h()
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("HOME", "/home/real")
        mp.setenv("SIMPLICIO_TOOLS_DIR", "/opt/real")
        mp.setenv("SIMPLICIO_VIDEO_DATA", "/dados/real")
        helpers.isolate_tools(mp, tmp_path)
        assert os.environ["HOME"] == str(tmp_path / "home")
        assert os.environ["SIMPLICIO_TOOLS_DIR"] == str(tmp_path / "tools")
        assert os.environ["SIMPLICIO_VIDEO_DATA"] == "/dados/real"  # untouched without `data=`
        assert not (tmp_path / "home").exists() and not (tmp_path / "tools").exists()  # only pointed at
    assert os.environ["HOME"] != str(tmp_path / "home")  # undone with the monkeypatch


def test_isolate_tools_data_names_the_data_folder_and_home_can_stay(tmp_path):
    helpers = h()
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("HOME", "/home/real")
        helpers.isolate_tools(mp, tmp_path, home=False, data="dados")
        assert os.environ["HOME"] == "/home/real"
        assert os.environ["SIMPLICIO_VIDEO_DATA"] == str(tmp_path / "dados")
        helpers.isolate_tools(mp, tmp_path, data="data")
        assert os.environ["SIMPLICIO_VIDEO_DATA"] == str(tmp_path / "data")


def test_isolate_tools_drops_the_named_variables_and_tolerates_absent_ones(tmp_path):
    helpers = h()
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("U17_A", "1")
        mp.setenv("U17_B", "2")
        mp.delenv("U17_AUSENTE", raising=False)
        mp.setenv("U17_FICA", "3")
        helpers.isolate_tools(mp, tmp_path, drop=("U17_A", "U17_B", "U17_AUSENTE"))
        assert "U17_A" not in os.environ and "U17_B" not in os.environ and "U17_AUSENTE" not in os.environ
        assert os.environ["U17_FICA"] == "3"


def test_isolate_tools_returns_tmp_path(tmp_path):
    helpers = h()
    with pytest.MonkeyPatch.context() as mp:
        assert helpers.isolate_tools(mp, tmp_path) == tmp_path


# ------------------------------------------------------------------------------------------------ WAVs sintéticos

def _le(dados: bytes):
    with wave.open(io.BytesIO(dados)) as w:
        return w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes(), w.readframes(w.getnframes())


def test_pcm_wav_is_a_mono_16_bit_wav_of_exactly_those_samples():
    helpers = h()
    amostras = [0, 1, -1, 32767, -32768, 100]
    canais, largura, taxa, n, quadros = _le(helpers.pcm_wav(amostras))
    assert (canais, largura, taxa, n) == (1, 2, 24000, 6)
    assert list(struct.unpack("<6h", quadros)) == amostras
    assert _le(helpers.pcm_wav(amostras, 8000))[2] == 8000
    assert _le(helpers.pcm_wav([]))[3] == 0


def _sine_original(seconds, sr, f):
    """The body the three copies shared before U17 (frequency was the only thing that differed)."""
    import math
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1), w.setsampwidth(2), w.setframerate(sr)
        w.writeframes(b"".join(struct.pack("<h", int(8000 * math.sin(2 * math.pi * f * i / sr))) for i in range(int(seconds * sr))))
    return buf.getvalue()


def test_sine_wav_has_the_duration_rate_and_frequency_asked_for():
    helpers = h()
    dados = helpers.sine_wav(0.5, 16000, 200)
    canais, largura, taxa, n, quadros = _le(dados)
    assert (canais, largura, taxa, n) == (1, 2, 16000, 8000)
    amostras = struct.unpack(f"<{n}h", quadros)
    assert 7900 <= max(amostras) <= 8000 and -8000 <= min(amostras) <= -7900
    cruzamentos = sum(1 for a, b in zip(amostras, amostras[1:]) if (a < 0) != (b < 0))
    assert abs(cruzamentos - 2 * 200 * 0.5) <= 2  # a 200 Hz tone crosses zero 400 times in a second


def test_sine_wav_is_byte_for_byte_the_old_copies_body():
    helpers = h()
    assert helpers.sine_wav(0.4, 24000, 330) == _sine_original(0.4, 24000, 330)  # test_voice_gemini
    assert helpers.sine_wav(0.30, 24000, 300 + 40 * 3) == _sine_original(0.30, 24000, 300 + 40 * 3)  # test_voice_concurrency, seed 3
    assert helpers.sine_wav() == helpers.sine_wav(0.4, 24000, 330)  # the defaults of test_voice_gemini


def test_sine_wav_different_frequencies_give_different_bytes():
    helpers = h()
    assert helpers.sine_wav(0.1, 24000, 330) != helpers.sine_wav(0.1, 24000, 340)
    assert len(helpers.sine_wav(0.1, 24000, 330)) == len(helpers.sine_wav(0.1, 24000, 340))


# ------------------------------------------------------------------------------------------------ as cópias não voltam
# Guards for the cleanup itself: a test file that grows its own copy of a shared helper fails here, naming the file.

def _modulos():
    import ast
    for p in sorted(TESTS.rglob("*.py")):
        rel = p.relative_to(TESTS)
        if rel.parts[0] in ("helpers", "tools") or rel.as_posix() in ("test_helpers_testes.py", "conftest.py"):  # tools/: standalone scripts
            continue
        yield rel.as_posix(), ast.parse(p.read_text(encoding="utf8"))


def test_no_test_module_recomputes_the_repository_root_from_its_own_location():
    import ast
    # the exact spellings the copies had (a different value, like SRC = Path(fsutil.__file__).parent, is another thing)
    copias_de = {
        "ROOT": ("Path(__file__).resolve().parents[1]", "Path(__file__).resolve().parents[2]"),
        "SRC": ("ROOT / 'src' / 'simplicio_video'", "Path(__file__).resolve().parents[1] / 'src' / 'simplicio_video'"),
        "SCRIPTS": ("ROOT / 'scripts'",),
        "FIXTURE": ("Path(__file__).parent / 'fixtures' / 'mini'",),
    }
    copias = []
    for rel, tree in _modulos():
        for n in tree.body:
            if isinstance(n, ast.Assign) and len(n.targets) == 1 and getattr(n.targets[0], "id", None) in copias_de:
                if ast.unparse(n.value) in copias_de[n.targets[0].id]:
                    copias.append(f"{rel}:{n.lineno}: {ast.unparse(n)}")
    assert copias == [], "use `from helpers import ROOT, SRC, SCRIPTS, FIXTURE`:\n" + "\n".join(copias)


def test_nothing_imports_the_shared_names_from_conftest_or_through_a_support_module_at_module_level():
    import ast
    achados = []
    for rel, tree in _modulos():
        for n in tree.body:
            if isinstance(n, ast.ImportFrom) and n.level == 0:
                if n.module == "conftest":
                    achados.append(f"{rel}:{n.lineno}: from conftest import ...")
                elif n.module in ("_comum", "_docs", "gitfixture") and any(a.name in ("ROOT", "SCRIPTS") for a in n.names):
                    achados.append(f"{rel}:{n.lineno}: from {n.module} import ROOT/SCRIPTS")
        for fn in ast.walk(tree):
            if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)) and not fn.name.startswith("test_"):
                for n in ast.walk(fn):
                    if isinstance(n, ast.ImportFrom) and n.module == "conftest":
                        achados.append(f"{rel}:{n.lineno}: from conftest import ... inside {fn.name}()")
    assert achados == [], "import from helpers:\n" + "\n".join(achados)


def test_conftest_still_exports_the_names_that_test_bodies_import_from_it():
    import conftest
    helpers = h()
    for nome in ("ROOT", "FIXTURE", "WJR", "LOTHUS", "CLIENT_DATA_REASON", "needs_client", "contract_with_coleta_placeholders",
                 "have_render_tools", "offline_env", "run_cli"):
        assert getattr(conftest, nome) is getattr(helpers, nome), nome


def test_importing_helpers_registers_no_second_copy_of_the_offline_folder():
    import conftest
    helpers = h()
    assert conftest.offline_env is helpers.offline_env  # one function, one per-process sitecustomize folder
    pasta = helpers.offline_env()["PYTHONPATH"].split(os.pathsep)[0]
    assert sys.modules["helpers.env"]._OFFLINE_DIR == [pasta]
    assert not hasattr(conftest, "_OFFLINE_DIR")


def test_no_test_module_defines_its_own_ffmpeg_marker_or_ffmpeg_skip():
    import ast
    achados = []
    cond = "not (shutil.which('ffmpeg') and shutil.which('ffprobe'))"
    for rel, tree in _modulos():
        for n in tree.body:
            if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", None) == "needs_ffmpeg":
                achados.append(f"{rel}:{n.lineno}: needs_ffmpeg = ...")
            # a helper whose only job is "skip unless ffmpeg and ffprobe" (a test or a fixture that skips among other things is not one)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and not n.name.startswith("test_") and len(n.body) == 1:
                if isinstance(n.body[0], ast.If) and ast.unparse(n.body[0].test) == cond:
                    achados.append(f"{rel}:{n.lineno}: def {n.name}() repeats the ffmpeg/ffprobe check")
    assert achados == [], "use needs_ffmpeg / ffmpeg_ou_pula(motivo) from helpers:\n" + "\n".join(achados)


def test_no_test_module_has_its_own_yaml_editor_or_fake_mp4_writer():
    import ast
    achados = []
    for rel, tree in _modulos():
        for n in tree.body:
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and not n.name.startswith("test_"):
                corpo = ast.unparse(n)
                if "fn(d)" in corpo and ("yaml.safe_dump(d, allow_unicode=True, sort_keys=False)" in corpo or "edit_yaml(path, fn" in corpo):
                    achados.append(f"{rel}:{n.lineno}: def {n.name}() loads, edits and dumps a YAML (helpers.edit_yaml)")
                if "'out' / 'mini.mp4'" in corpo or '"out" / "mini.mp4"' in corpo:
                    achados.append(f"{rel}:{n.lineno}: def {n.name}() writes out/mini.mp4 (helpers.fake_mp4)")
    assert achados == [], "\n".join(achados)


def test_no_test_module_has_its_own_in_process_main_runner():
    import ast
    achados = []
    for rel, tree in _modulos():
        for n in tree.body:
            if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) or n.name.startswith("test_"):
                continue
            if "capsys.readouterr()" not in ast.unparse(n):
                continue
            for sub in ast.walk(n):
                if isinstance(sub, ast.ExceptHandler) and ast.unparse(sub.type) == "SystemExit" and sub.body:
                    primeiro = ast.unparse(sub.body[0])
                    if primeiro == "rc = e.code" or primeiro.startswith("if isinstance(e.code, str):"):
                        achados.append(f"{rel}:{n.lineno}: def {n.name}() runs main(argv) and turns SystemExit into rc (helpers.run_main)")
    assert achados == [], "\n".join(achados)


def test_vivo_and_espera_are_defined_once():
    import ast
    achados = []
    for rel, tree in _modulos():
        for n in tree.body:
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in ("vivo", "espera"):
                achados.append(f"{rel}:{n.lineno}: def {n.name}() (helpers.procs)")
    assert achados == [], "\n".join(achados)


def test_isolate_tools_drops_first_so_a_dropped_name_that_it_also_sets_ends_up_set(tmp_path):
    helpers = h()
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("SIMPLICIO_TOOLS_DIR", "/real")
        helpers.isolate_tools(mp, tmp_path, drop=("SIMPLICIO_TOOLS_DIR",))
        assert os.environ["SIMPLICIO_TOOLS_DIR"] == str(tmp_path / "tools")  # test_tools_cmd dropped per-track names first, then set it


def test_no_test_module_isolates_home_and_the_tools_dir_by_hand():
    import ast
    achados = []
    for rel, tree in _modulos():
        for n in tree.body:
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "_isolated":
                if "SIMPLICIO_TOOLS_DIR" in ast.unparse(n):
                    achados.append(f"{rel}:{n.lineno}: def _isolated() sets SIMPLICIO_TOOLS_DIR itself (helpers.isolate_tools)")
    assert achados == [], "\n".join(achados)


def test_no_test_module_builds_an_in_memory_wav_by_hand():
    import ast
    achados = []
    for rel, tree in _modulos():
        for n in tree.body:
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and not n.name.startswith("test_"):
                if "wave.open(buf, 'wb')" in ast.unparse(n) and "buf.getvalue()" in ast.unparse(n):
                    achados.append(f"{rel}:{n.lineno}: def {n.name}() writes a WAV into a BytesIO (helpers.pcm_wav / helpers.sine_wav)")
    assert achados == [], "\n".join(achados)


def test_edit_yaml_utf8_is_edit_yaml_with_utf8_named(tmp_path):
    helpers = h()
    p = tmp_path / "c.yaml"
    p.write_bytes("nome: João\n".encode("utf8"))
    assert helpers.edit_yaml_utf8(p, lambda d: d.update(cidade="São Paulo")) is None
    assert p.read_bytes() == "nome: João\ncidade: São Paulo\n".encode("utf8")
