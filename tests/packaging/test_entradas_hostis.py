"""No unhandled exception comes out of `doctor`, `login`, `logout` or `auth status` (text and --json) with hostile input.

The review of PR #116 reproduced tracebacks from: a PATH folder the user cannot open and a `~/.simplicio` that another user
owns with mode 0700 (common after `sudo` on macOS): `Path.is_file()` raises PermissionError on Python 3.12 and 3.13 where
`shutil.which` swallowed it; and from a corrupt or hostile `login.json` (`1e999`, a date past year 9999, deep nesting) and
`update-check.json`. Here every one of those, and more, goes through every command, and each must end in an exit code and, with
--json, ONE document that fits its packaged schema. Nothing is ever a traceback.

Real `chmod 000` does nothing for root, who runs this suite in some environments, so the unreadable folders are SIMULATED
(`nega_acesso`: stat, open and friends raise PermissionError inside them). Every file here is under tmp_path and every
token is FAKE. The `logout --yes` cases only ever point at files under tmp_path.
"""
from __future__ import annotations

import json
import os
import shutil
import socket
from pathlib import Path

import pytest

import _caixa
from _caixa import SECRETS, hostos, nega_acesso, put_login, put_raw, roda, write_fake_runtime
from _comum import erros_de_schema

# fixtures: assigned (not imported) so pytest finds them and ruff sees no shadowing by the test parameters
caixa = _caixa.caixa
saude = _caixa.saude

COMANDOS = [
    (["auth", "status"], None), (["auth", "status", "--json"], "auth-status"),
    (["doctor", "login"], None), (["doctor", "login", "--json"], "doctor"),
    (["login"], None), (["login", "--json"], "login"),
    (["logout"], None), (["logout", "--json"], "logout"),
    (["logout", "--yes"], None), (["logout", "--yes", "--json"], "logout"),  # last: it may take the file away
]


def verifica(argv: list[str], esquema: str | None, capsys):
    """Run one command: an int exit code, no traceback, and with --json ONE document that fits its schema."""
    rc, out, err = roda(argv, capsys)
    assert isinstance(rc, int)
    assert "Traceback" not in out + err, f"{argv}: {err[-400:]}"
    for segredo in SECRETS:
        assert segredo not in out + err, f"{argv} leaked {segredo!r}"
    if esquema:
        try:
            doc = json.loads(out)
        except ValueError:
            pytest.fail(f"{argv}: stdout is not ONE JSON document\nstdout={out[:300]!r}\nstderr={err[:300]!r}")
        assert erros_de_schema(esquema, doc) == [], f"{argv}: {erros_de_schema(esquema, doc)}"
    else:
        assert out.strip() or err.strip(), f"{argv} printed nothing"
    return rc, out, err


# --- a corrupt or hostile login.json ---------------------------------------------------------------------------------------


def _login(**campos) -> str:
    """A login file as TEXT: the values are raw JSON fragments, so that `1e999` and `NaN` can be written as they are."""
    base = '"access_token": "fake-access-token-AAAA", "refresh_token": "fake-refresh-token-BBBB"'
    return "{" + base + "".join(f', "{nome}": {valor}' for nome, valor in campos.items()) + "}"


# Each of these is "not a usable login": `login_invalid`, never an exception.
INVALIDOS = {
    "access_inf": _login(access_expires_at="1e999"),
    "access_menos_inf": _login(access_expires_at="-1e999"),
    "access_nan": _login(access_expires_at="NaN"),
    "access_ano_33658": _login(access_expires_at="999999999999"),
    "access_um_segundo_depois_do_ano_9999": _login(access_expires_at="253402300800"),
    "access_negativo": _login(access_expires_at="-1"),
    "access_booleano": _login(access_expires_at="true"),
    "access_lista": _login(access_expires_at="[1]"),
    "access_objeto": _login(access_expires_at='{"a": 1}'),
    "access_texto": _login(access_expires_at='"amanha"'),
    "access_texto_com_digitos_demais": _login(access_expires_at='"' + "9" * 5000 + '"'),
    "access_inteiro_gigante": _login(access_expires_at="9" * 5000),
    "refresh_inf": _login(access_expires_at="1", refresh_token_expires_at="1e999"),
    "refresh_ano_33658": _login(access_expires_at="1", refresh_token_expires_at="999999999999"),
    "refresh_negativo": _login(access_expires_at="1", refresh_token_expires_at="-5"),
    "aninhado_lista": "[" * 100_000 + "]" * 100_000,
    "aninhado_objeto": '{"access_token": "x", "a": ' + '{"a": ' * 50_000 + "1" + "}" * 50_000 + "}",
    "maior_que_o_limite": '{"access_token": "x", "pad": "' + "a" * (1 << 20) + '"}',
    "vazio": "",
    "nao_utf8": b'{"access_token": "\xff\xfe"}',
    "nao_e_objeto": "[1, 2]",
}

# Odd but not invalid on their own: the commands must not crash, whatever they conclude.
ESTRANHOS = {
    "verification_lista": _login(verification="[1, 2]"),
    "verification_texto": _login(verification='"x"'),
    "validated_lista": _login(verification='{"validated": [1]}'),
    "user_texto": _login(verification='{"validated": {"user": "x"}}'),
    "email_numero": _login(verification='{"validated": {"user": {"email": 123}}}'),
    "email_enorme": _login(verification='{"validated": {"user": {"email": "' + "a" * 500_000 + '@b.co"}}}'),
    "entitlement_texto": _login(verification='{"validated": {"entitlement": "x"}}'),
    "entitlement_aninhado": _login(verification='{"validated": {"entitlement": {"tier": {"a": [1, {"b": 2}]}, "active": [1]}}}'),
    "refresh_token_lista": _login(refresh_token="[1]"),
    "ate_o_ano_9999": _login(access_expires_at="253402300799"),
    "decimal": _login(access_expires_at="1893456000.5"),
}


@pytest.mark.parametrize("nome", sorted(INVALIDOS))
def test_login_corrompido_vira_login_invalid_em_todos_os_comandos(caixa, capsys, nome):
    for argv, esquema in COMANDOS:
        put_raw(caixa.login, INVALIDOS[nome])  # `logout --yes` may have taken it away
        rc, out, err = verifica(argv, esquema, capsys)
        if argv[:2] == ["auth", "status"]:
            assert rc == 1 and "login_invalid" in out, (argv, out)
        if argv[:2] == ["doctor", "login"]:
            assert rc == 1, "an unusable login file is a failure of the login row"
        if esquema == "auth-status":
            assert json.loads(out)["reason_code"] == "login_invalid"
        if argv == ["doctor", "login", "--json"]:
            linha = json.loads(out)["checks"][0]
            assert linha["status"] == "fail" and linha["detail"]["reason_code"] == "login_invalid"
            assert linha["fix"] == "simplicio-video login"


@pytest.mark.parametrize("nome", sorted(INVALIDOS))
def test_login_com_runtime_e_arquivo_corrompido_nao_e_verificado(caixa, capfd, nome):
    caixa.runtime(writes=False)  # the Runtime says it is done, the file it left is garbage
    put_raw(caixa.login, INVALIDOS[nome])
    rc, out, err = verifica(["login", "--json"], "login", capfd)
    doc = json.loads(out)
    assert rc == 1 and doc["status"] == "NOT_VERIFIED" and doc["reason_code"] == "login_invalid"


@pytest.mark.parametrize("nome", sorted(ESTRANHOS))
def test_login_estranho_nao_derruba_nenhum_comando(caixa, capsys, nome):
    for argv, esquema in COMANDOS:
        put_raw(caixa.login, ESTRANHOS[nome])
        verifica(argv, esquema, capsys)


@pytest.mark.parametrize("nome", ["access_inf", "aninhado_lista", "maior_que_o_limite"])
def test_o_doctor_inteiro_sobrevive_a_um_login_corrompido(saude, capsys, nome):
    put_raw(saude.caixa.login, INVALIDOS[nome])
    rc, out, err = verifica(["doctor", "--json"], "doctor", capsys)
    doc = json.loads(out)
    assert rc == 1 and doc["status"] == "fail" and len(doc["checks"]) == 12, "the other eleven checks must not be lost"
    assert [c["status"] for c in doc["checks"] if c["name"] == "login"] == ["fail"]
    rc, out, err = verifica(["doctor"], None, capsys)
    assert rc == 1 and "login_invalid" in out


def test_o_limite_de_tamanho_aceita_um_login_grande_mas_real(caixa, capsys):
    """A real login is about 2 KiB; the cap only refuses what is absurd (a megabyte and more)."""
    doc = json.loads(_login(access_expires_at="4102444800", verification='{"validated": {"user": {"email": "w@b.co"}}}'))
    doc["pad"] = "a" * (900 * 1024)
    put_raw(caixa.login, json.dumps(doc))
    rc, out, err = verifica(["auth", "status", "--json"], "auth-status", capsys)
    assert rc == 0 and json.loads(out)["logged_in"] is True


# --- a PATH folder the user cannot open -----------------------------------------------------------------------------------


def test_which_pula_a_pasta_sem_permissao_e_acha_na_seguinte(tmp_path, monkeypatch):
    negada = tmp_path / "negada"
    negada.mkdir()
    bom = write_fake_runtime(tmp_path / "bom")
    nega_acesso(monkeypatch, negada)
    assert hostos.which("simplicio", os.pathsep.join([str(negada), str(tmp_path / "bom")])) == bom
    assert hostos.which("simplicio", str(negada)) is None


def test_find_tool_e_find_uv_tambem_pulam_a_pasta_sem_permissao(tmp_path, monkeypatch):
    negada = tmp_path / "negada"
    negada.mkdir()
    nega_acesso(monkeypatch, negada, tmp_path / "home" / ".local")
    ambiente = {"PATH": str(negada), "HOME": str(tmp_path / "home")}
    assert hostos.find_tool("node", ambiente) is None
    assert hostos.find_uv(ambiente) is None


@pytest.mark.parametrize("argv,esquema", COMANDOS, ids=lambda x: " ".join(x) if isinstance(x, list) else str(x))
def test_path_com_pasta_ilegivel_nao_derruba_nenhum_comando(caixa, capsys, monkeypatch, argv, esquema):
    negada = caixa.tmp / "negada"
    negada.mkdir()
    caixa.runtime()
    nega_acesso(monkeypatch, negada)
    monkeypatch.setenv("PATH", os.pathsep.join([str(negada), str(caixa.bin)]))  # the unreadable folder comes FIRST
    rc, out, err = verifica(argv, esquema, capsys)
    if argv == ["auth", "status", "--json"]:
        assert json.loads(out)["runtime"]["found"] is True, "the Runtime after the unreadable folder must still be found"


def test_o_doctor_inteiro_com_pasta_ilegivel_no_path(saude, capsys, monkeypatch):
    negada = saude.caixa.tmp / "negada"
    negada.mkdir()
    nega_acesso(monkeypatch, negada)
    monkeypatch.setenv("PATH", os.pathsep.join([str(negada), str(saude.caixa.bin)]))
    rc, out, err = verifica(["doctor", "--json"], "doctor", capsys)
    doc = json.loads(out)
    assert rc == 0 and len(doc["checks"]) == 12
    assert [c["status"] for c in doc["checks"] if c["name"] in ("node", "ffmpeg", "ffmpeg-libass")] == ["ok", "ok", "ok"]


# --- a ~/.simplicio that another user owns (mode 0700, common after `sudo`) ------------------------------------------------


@pytest.mark.parametrize("argv,esquema", COMANDOS, ids=lambda x: " ".join(x) if isinstance(x, list) else str(x))
def test_pasta_do_login_de_outro_usuario_nao_derruba_nenhum_comando(caixa, capsys, monkeypatch, argv, esquema):
    put_login(caixa.login)
    antes = caixa.login.read_bytes()
    nega_acesso(monkeypatch, caixa.login.parent)
    rc, out, err = verifica(argv, esquema, capsys)
    if argv[:2] == ["auth", "status"]:
        assert rc == 1 and "login_permissions" in out
        if esquema:
            doc = json.loads(out)
            assert doc["reason_code"] == "login_permissions" and doc["fix"] and str(caixa.login) in doc["detail"]
    if argv[:3] == ["doctor", "login", "--json"]:
        assert rc == 1 and json.loads(out)["checks"][0]["detail"]["reason_code"] == "login_permissions"
    if argv[:2] == ["logout", "--yes"]:
        assert rc == 1, "cannot even look at the file: that is a failure, not `NO_LOGIN`"
        if esquema:
            doc = json.loads(out)
            assert doc["status"] == "FAILED" and doc["reason_code"] == "login_permissions"
    if argv == ["logout"]:
        assert rc == 2
    monkeypatch.undo()
    assert caixa.login.read_bytes() == antes, "nothing may be deleted when the folder cannot be searched"


def test_runtime_gerenciado_em_pasta_ilegivel_e_so_nao_encontrado(caixa, monkeypatch):
    write_fake_runtime(caixa.home / ".simplicio" / "bin")
    nega_acesso(monkeypatch, caixa.home / ".simplicio")
    env = {"HOME": str(caixa.home), "PATH": str(caixa.tmp / "vazio")}
    assert _caixa.auth.runtime_binary(env) is None


# --- SIMPLICIO_AUTH_FILE pointing at something odd -------------------------------------------------------------------------


def _pasta(caixa) -> Path:
    alvo = caixa.tmp / "auth" / "login.json"
    alvo.mkdir(parents=True)
    alvo.parent.chmod(0o700)
    return alvo


def _fifo(caixa) -> Path:
    alvo = caixa.tmp / "auth" / "login.json"
    alvo.parent.mkdir()
    alvo.parent.chmod(0o700)
    os.mkfifo(alvo, 0o600)
    return alvo


def _laco_de_links(caixa) -> Path:
    pasta = caixa.tmp / "auth"
    pasta.mkdir()
    pasta.chmod(0o700)
    (pasta / "login.json").symlink_to(pasta / "outro.json")
    (pasta / "outro.json").symlink_to(pasta / "login.json")
    return pasta / "login.json"


def _link_quebrado(caixa) -> Path:
    pasta = caixa.tmp / "auth"
    pasta.mkdir()
    pasta.chmod(0o700)
    (pasta / "login.json").symlink_to(caixa.tmp / "nao-existe.json")
    return pasta / "login.json"


def _dispositivo(caixa) -> Path:
    """A character device made INSIDE tmp_path (never the real /dev/null: an old logout would delete it)."""
    import stat
    pasta = caixa.tmp / "auth"
    pasta.mkdir()
    pasta.chmod(0o700)
    try:
        os.mknod(pasta / "login.json", stat.S_IFCHR | 0o600, os.makedev(1, 3))
    except (PermissionError, AttributeError, OSError):
        pytest.skip("cannot create a device node here")
    return pasta / "login.json"


def _sob_um_arquivo(caixa) -> Path:
    (caixa.tmp / "arquivo").write_text("sou um arquivo, nao uma pasta")
    return caixa.tmp / "arquivo" / "login.json"


def _nome_longo(caixa) -> Path:
    return caixa.tmp / ("x" * 300) / "login.json"


def _socket(caixa) -> Path:
    import tempfile
    pasta = Path(tempfile.mkdtemp(prefix="sv"))  # a short path: AF_UNIX allows about 100 characters
    caixa.tmp_extra = pasta
    alvo = pasta / "l.json"
    servidor = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        servidor.bind(str(alvo))
    except OSError:
        servidor.close()
        pytest.skip("cannot bind a unix socket here")
    caixa.servidor = servidor
    return alvo


AUTH_FILE_ESTRANHOS = {"pasta": _pasta, "fifo": _fifo, "laco_de_links": _laco_de_links, "link_quebrado": _link_quebrado,
                       "dispositivo": _dispositivo, "sob_um_arquivo": _sob_um_arquivo, "nome_longo": _nome_longo,
                       "socket": _socket}


@pytest.mark.parametrize("nome", sorted(AUTH_FILE_ESTRANHOS))
def test_simplicio_auth_file_estranho_nao_derruba_nenhum_comando(caixa, capsys, monkeypatch, nome):
    alvo = AUTH_FILE_ESTRANHOS[nome](caixa)
    monkeypatch.setenv("SIMPLICIO_AUTH_FILE", str(alvo))
    try:
        for argv, esquema in COMANDOS:
            verifica(argv, esquema, capsys)
        if nome in ("pasta", "fifo", "dispositivo", "socket", "laco_de_links", "link_quebrado"):
            assert os.path.lexists(alvo), f"`logout --yes` deleted the {nome} that SIMPLICIO_AUTH_FILE pointed at"
    finally:
        if hasattr(caixa, "servidor"):
            caixa.servidor.close()
            shutil.rmtree(caixa.tmp_extra, ignore_errors=True)


# --- no HOME at all, a workspace that is hostile ---------------------------------------------------------------------------


def _sem_home(monkeypatch) -> None:
    def falha(cls):
        raise RuntimeError("Could not determine home directory.")

    monkeypatch.delenv("HOME", raising=False)
    monkeypatch.delenv("USERPROFILE", raising=False)
    monkeypatch.setattr(Path, "home", classmethod(falha))


@pytest.mark.parametrize("argv,esquema", COMANDOS, ids=lambda x: " ".join(x) if isinstance(x, list) else str(x))
def test_sem_home_nenhum_comando_derruba(caixa, capsys, monkeypatch, argv, esquema):
    _sem_home(monkeypatch)
    verifica(argv, esquema, capsys)


def test_o_doctor_inteiro_sem_home_e_sem_workspace_configurado(saude, capsys, monkeypatch):
    """The workspace folder defaults to ~/.simplicio-video/workspaces/default: with no home it must not raise."""
    monkeypatch.delenv("SIMPLICIO_WORKSPACE")
    _sem_home(monkeypatch)
    rc, out, err = verifica(["doctor", "--json"], "doctor", capsys)
    assert len(json.loads(out)["checks"]) == 12


def test_workspace_com_til_de_usuario_que_nao_existe(saude, capsys, monkeypatch):
    """Path('~nobody-xyz/ws').expanduser() raises RuntimeError: a hostile SIMPLICIO_WORKSPACE must not take the doctor down."""
    monkeypatch.setenv("SIMPLICIO_WORKSPACE", "~um-usuario-que-nao-existe-xyz/ws")
    rc, out, err = verifica(["doctor", "--json"], "doctor", capsys)
    linha = [c for c in json.loads(out)["checks"] if c["name"] == "setup"][0]
    assert linha["status"] == "warn", "a workspace that is not there yet: the setup never ran"


def test_workspace_que_o_usuario_nao_consegue_ler_e_fail_e_nao_traceback(saude, capsys, monkeypatch):
    nega_acesso(monkeypatch, saude.caixa.workspace)
    rc, out, err = verifica(["doctor", "--json"], "doctor", capsys)
    linha = [c for c in json.loads(out)["checks"] if c["name"] == "setup"][0]
    assert rc == 1 and linha["status"] == "fail" and linha["fix"]
    assert "permiss" in linha["summary"].lower(), "say it is a permission problem, not that the setup never ran"


def test_workspace_yaml_aninhado_demais_e_fail_e_nao_traceback(saude, capsys):
    (saude.caixa.workspace / "workspace.yaml").write_text("a: " + "[" * 100_000 + "]" * 100_000, encoding="utf-8")
    rc, out, err = verifica(["doctor", "--json"], "doctor", capsys)
    linha = [c for c in json.loads(out)["checks"] if c["name"] == "setup"][0]
    assert rc == 1 and linha["status"] == "fail"


# --- a Runtime that cannot be started, odd PATH strings --------------------------------------------------------------------


def test_runtime_que_nao_executa_nao_derruba_o_login(caixa, capfd):
    """A file called `simplicio` with the exec bit and garbage inside: the exec fails (ENOEXEC) and `login` says so."""
    quebrado = caixa.bin / "simplicio"
    quebrado.write_bytes(b"\x00\x01\x02 this is not a program")
    quebrado.chmod(0o755)
    rc, out, err = verifica(["login", "--json"], "login", capfd)
    doc = json.loads(out)
    assert rc == 1 and doc["status"] == "NOT_VERIFIED" and doc["reason_code"] == "runtime_login_failed"
    assert doc["runtime"]["found"] is True and doc["logged_in"] is False
    rc, out, err = verifica(["login"], None, capfd)
    assert rc == 1 and "não consegui iniciar" in out


@pytest.mark.parametrize("path", ["", ":", ":::", ".", "relativo/bin", '"', "'", " ", "\t", "/nao/existe", "~", "$HOME", "%PATH%"])
def test_path_estranho_nao_derruba_nenhum_comando(caixa, capsys, monkeypatch, path):
    monkeypatch.setenv("PATH", path)
    for argv, esquema in COMANDOS[:6]:
        verifica(argv, esquema, capsys)


def test_path_com_um_arquivo_e_uma_pasta_chamados_simplicio(caixa, capsys, monkeypatch):
    (caixa.bin / "simplicio").mkdir()
    arquivo = caixa.tmp / "arquivo-no-path"
    arquivo.write_text("x")
    monkeypatch.setenv("PATH", os.pathsep.join([str(arquivo), str(caixa.bin)]))
    rc, out, err = verifica(["auth", "status", "--json"], "auth-status", capsys)
    assert json.loads(out)["runtime"]["found"] is False


# --- install and the distribution probe on a checkout the user cannot open ---------------------------------------------------


def test_checkout_que_o_usuario_nao_consegue_abrir_nao_e_um_checkout_nem_derruba_ninguem(tmp_path, monkeypatch):
    raiz = tmp_path / "repo"
    raiz.mkdir()
    (raiz / ".git").mkdir()
    (raiz / "plugin.json").write_text('{"name": "videos"}')
    assert _caixa.distribution.checkout_marker(raiz) is True
    nega_acesso(monkeypatch, raiz)
    assert _caixa.distribution.checkout_marker(raiz) is False
    from simplicio_video import paths
    monkeypatch.setenv("SIMPLICIO_VIDEO_HOME", str(raiz))
    assert paths.home() == raiz.resolve(), "an unreadable SIMPLICIO_VIDEO_HOME is still the folder that was asked for"


@pytest.mark.parametrize("argv", [["install", "--check"], ["install", "--check", "--json"], ["install", "--dry-run"]])
def test_install_com_checkout_ilegivel_nao_derruba_e_diz_o_plano(caixa, capsys, monkeypatch, argv):
    import shutil

    from _comum import ROOT
    repo = caixa.tmp / "checkout"
    repo.mkdir()
    for nome in ("pyproject.toml", "plugin.json"):
        shutil.copy2(ROOT / nome, repo / nome)
    monkeypatch.setenv("SIMPLICIO_VIDEO_HOME", str(repo))
    monkeypatch.setattr(_caixa.distribution, "kind", lambda **kw: "source")
    nega_acesso(monkeypatch, repo)
    rc, out, err = verifica(argv, "install-result" if "--json" in argv else None, capsys)
    assert rc == (10 if "--check" in argv else 0) and ".venv" in out + err
