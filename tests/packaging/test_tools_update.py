"""Contract of the external tracks in `simplicio-video update` (issue #150): follow the upstream or keep the pins (--pin), record
what was resolved in tools.lock.json, show it in `tools` and `doctor`, and never let one failing track stop the others.

Nothing here touches the network, git, npm or pip: the commands and the reads go through a fake `Io` (the tools_update seam), and
the checkouts, venvs and the lock are real folders under tmp_path (SIMPLICIO_TOOLS_DIR, SIMPLICIO_VIDEO_DATA).
"""
from __future__ import annotations

import dataclasses
import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

import pytest

from simplicio_video import hostos, paths, tools, tools_lock, tools_update

from simplicio_video.cli import main
from simplicio_video.commands import doctor as doctor_cmd
from simplicio_video.commands import update as update_cmd

REAL_GIT = tools._git  # the hermetic fixture swaps tools._git for a refusal in every test

SHA_OLD = "a" * 40
SHA_NEW = "b" * 40
DIGEST_NEW = "c" * 64
DIGEST_OTHER = "d" * 64
NOW = 1700000000
GIT_TRACKS = [t for t in tools.TOOLS.values() if t.kind == "git"]
CP = subprocess.CompletedProcess


class Fake:
    """Scripted commands and reads for one test. `remote` maps a repo to (default branch, HEAD); `npm` maps a package to its latest
    version; `pypi` is the PyPI document; `fails` maps a fragment of a command line to (rc, message); `drop_marker_on` is a commit
    after which a checkout loses its registry marker (a layout change upstream)."""

    def __init__(self, *, remote=None, npm=None, pypi=None, fails=None, drop_marker_on=None):
        self.remote = remote if remote is not None else {t.source: ("main", SHA_NEW) for t in GIT_TRACKS}
        self.npm = npm if npm is not None else {"@hypit/hypit": "0.2.18", "@tiny-fish/cli": "0.51.0"}
        self.pypi = pypi if pypi is not None else pypi_doc("2026.11.01", DIGEST_NEW)
        self.fails = fails or {}
        self.drop_marker_on = drop_marker_on
        self.calls: list[list[str]] = []
        self.urls: list[str] = []
        self.heads: dict[str, str] = {}

    def run(self, argv, cwd=None):
        argv = [str(a) for a in argv]
        self.calls.append(argv)
        line = " ".join(argv)
        for fragment, (code, message) in self.fails.items():
            if fragment in line:
                return CP(argv, code, "", message)
        if argv[:3] == ["git", "ls-remote", "--symref"]:
            branch, sha = self.remote[argv[3]]
            return CP(argv, 0, f"ref: refs/heads/{branch}\tHEAD\n{sha}\tHEAD\n", "")
        if argv[:2] == ["git", "-C"]:
            d, op = argv[2], argv[3]
            if op == "rev-parse" and "--verify" in argv:  # a short pin named inside the checkout: the full commit
                return CP(argv, 0, SHA_NEW + "\n", "")
            if op == "rev-parse":
                return CP(argv, 0, self.heads.get(d, SHA_OLD) + "\n", "")
            if op == "checkout":
                sha = argv[-1]
                self.heads[d] = sha
                if sha == self.drop_marker_on:
                    for t in GIT_TRACKS:
                        marker = Path(d) / t.marker
                        if Path(d).name == t.name and marker.exists():
                            marker.unlink()
                return CP(argv, 0, "", "")
            return CP(argv, 0, "", "")  # fetch
        if argv[0] == "/fake/npm":
            return CP(argv, 0, self.npm[argv[2]] + "\n", "")
        if argv[0] == "/fake/npx":
            return CP(argv, 0, "", "")
        if argv[1:3] == ["-m", "venv"]:
            (Path(argv[3]) / "bin").mkdir(parents=True, exist_ok=True)
            (Path(argv[3]) / "bin" / "python").write_text("", encoding="utf8")
            return CP(argv, 0, "", "")
        if argv[1:3] == ["-m", "pip"]:
            venv = Path(argv[0]).parent.parent
            (venv / "bin" / venv.parent.name).write_text("", encoding="utf8")
            return CP(argv, 0, "", "")
        raise AssertionError(f"comando não previsto no fake: {line}")

    def fetch(self, url):
        self.urls.append(url)
        if "pypi.org" not in url:
            raise AssertionError(f"leitura de rede não prevista: {url}")
        return self.pypi

    def io(self, **over):
        base = dict(network=True, run=self.run, fetch_json=self.fetch, now=lambda: NOW, which=lambda n: f"/fake/{n}")
        base.update(over)
        return tools_update.Io(**base)

    def ran(self, *fragments: str) -> list[list[str]]:
        return [c for c in self.calls if all(f in " ".join(c) for f in fragments)]


def pypi_doc(version, digest):
    return {"info": {"version": version},
            "urls": [{"packagetype": "sdist", "filename": f"yt_dlp-{version}.tar.gz", "digests": {"sha256": DIGEST_OTHER}},
                     {"packagetype": "bdist_wheel", "filename": f"yt_dlp-{version}-py3-none-any.whl",
                      "digests": {"sha256": digest}}]}


@pytest.fixture
def ambiente(tmp_path, monkeypatch):
    """Checkouts of the git tracks (with .git and their registry marker), the tools dir, the data dir and no overrides."""
    tools_dir = tmp_path / "tools"
    data = tmp_path / "data"
    monkeypatch.setenv("SIMPLICIO_TOOLS_DIR", str(tools_dir))
    monkeypatch.setenv("SIMPLICIO_VIDEO_DATA", str(data))
    monkeypatch.setenv("VIDEO_USE_DIR", str(tmp_path / "video-use"))
    for t in tools.TOOLS.values():
        monkeypatch.delenv(f"SIMPLICIO_{t.name.upper()}_REF", raising=False)
    for t in GIT_TRACKS:
        d = tmp_path / "video-use" if t.name == "video-use" else tools_dir / t.name
        (d / ".git").mkdir(parents=True, exist_ok=True)
        (d / t.marker).parent.mkdir(parents=True, exist_ok=True)
        (d / t.marker).write_text("", encoding="utf8")
    return tmp_path


def _checkout(tmp_path, name):
    return (tmp_path / "video-use") if name == "video-use" else (tmp_path / "tools" / name)


# --- resolution: what upstream says is the latest ---------------------------------------------------------------------


def test_resolve_git_le_o_head_e_o_branch_padrao_do_remoto():
    fake = Fake(remote={"https://github.com/x/y": ("master", SHA_NEW)})
    t = dataclasses.replace(tools.get("opencut"), source="https://github.com/x/y")
    assert tools_update.resolve_git(t, fake.io()) == {"ref": SHA_NEW, "branch": "master"}


def test_resolve_git_recusa_uma_saida_sem_o_commit_de_head():
    io = tools_update.Io(network=True, run=lambda argv, cwd=None: CP(argv, 0, "ref: refs/heads/main\tHEAD\n", ""),
                         now=lambda: NOW)
    with pytest.raises(tools.ToolError, match="não achei o commit de HEAD"):
        tools_update.resolve_git(tools.get("opencut"), io)


@pytest.mark.parametrize("saida", ["0.2.18", "0.2.18-beta.1"])
def test_resolve_npm_aceita_uma_versao(saida):
    fake = Fake(npm={"@hypit/hypit": saida})
    assert tools_update.resolve_npm(tools.get("hypit"), fake.io()) == {"ref": saida}


@pytest.mark.parametrize("saida", ["0.2.18; rm -rf ~", "", "latest", "0.2"])
def test_resolve_npm_recusa_o_que_nao_e_versao(saida):
    fake = Fake(npm={"@hypit/hypit": saida})
    with pytest.raises(tools.ToolError, match="não devolveu uma versão"):
        tools_update.resolve_npm(tools.get("hypit"), fake.io())


def test_resolve_pip_pega_a_versao_e_o_sha256_do_wheel_universal():
    fake = Fake(pypi=pypi_doc("2026.11.01", DIGEST_NEW))
    assert tools_update.resolve_pip(tools.get("yt-dlp"), fake.io()) == {"ref": "2026.11.01", "sha256": DIGEST_NEW}
    assert fake.urls == ["https://pypi.org/pypi/yt-dlp/json"]


def test_resolve_pip_recusa_quando_nao_ha_o_wheel_da_versao():
    doc = {"info": {"version": "2026.11.01"}, "urls": [{"packagetype": "sdist", "filename": "yt_dlp-2026.11.01.tar.gz",
                                                       "digests": {"sha256": DIGEST_NEW}}]}
    with pytest.raises(tools.ToolError, match="não achei o wheel"):
        tools_update.resolve_pip(tools.get("yt-dlp"), Fake(pypi=doc).io())


@pytest.mark.parametrize("versao, digest", [("2026.11.01 && x", DIGEST_NEW), ("2026.11.01", "not-a-hash")])
def test_resolve_pip_recusa_versao_ou_sha256_fora_do_formato(versao, digest):
    with pytest.raises(tools.ToolError):
        tools_update.resolve_pip(tools.get("yt-dlp"), Fake(pypi=pypi_doc(versao, digest)).io())


def test_resolve_recusa_a_rede_quando_offline():
    io = tools_update.Io(network=False, run=lambda argv, cwd=None: pytest.fail("não pode rodar"), now=lambda: NOW)
    with pytest.raises(OSError, match="SIMPLICIO_OFFLINE=1"):
        tools_update.resolve_git(tools.get("opencut"), io)


# --- the lock file ----------------------------------------------------------------------------------------------------


def _doc(**tracks):
    return {"schema": tools_lock.SCHEMA, "updated_at": NOW, "tools": tracks}


def test_lock_ida_e_volta_sem_deixar_arquivo_temporario(tmp_path):
    path = tmp_path / "data" / tools_lock.LOCK_FILE
    doc = _doc(opencut={"kind": "git", "source": "https://github.com/OpenCut-app/opencut-classic", "mode": "follow",
                        "status": "ok", "ref": SHA_NEW, "branch": "main", "resolved_at": NOW})
    tools_lock.write_lock(doc, path)
    assert tools_lock.read_lock(path) == doc
    assert sorted(p.name for p in path.parent.iterdir()) == [tools_lock.LOCK_FILE]


def test_lock_aceita_o_nome_com_sublinhado_do_registro(tmp_path):
    """rea_video is a registry name with an underscore: the lock must keep it, or the update of that track would never be saved."""
    path = tmp_path / tools_lock.LOCK_FILE
    doc = _doc(rea_video={"kind": "git", "source": "https://github.com/JuneYaooo/rea-video", "mode": "follow", "status": "ok",
                          "ref": SHA_NEW, "branch": "main", "resolved_at": NOW})
    tools_lock.write_lock(doc, path)
    assert tools_lock.read_lock(path)["tools"]["rea_video"]["ref"] == SHA_NEW


def test_lock_ausente_vale_vazio(tmp_path):
    assert tools_lock.read_lock(tmp_path / "nao-existe.json") == tools_lock.empty()


@pytest.mark.parametrize("conteudo", [
    "não é json",
    json.dumps({"schema": "outro/v1", "updated_at": NOW, "tools": {}}),
    json.dumps({"schema": tools_lock.SCHEMA, "updated_at": NOW, "tools": {"x": {"kind": "git", "source": "https://a.b/c",
                                                                               "mode": "follow", "status": "vai-quebrar"}}}),
    json.dumps({"schema": tools_lock.SCHEMA, "updated_at": NOW, "tools": {"x": {"kind": "git", "source": "https://a.b/c",
                                                                               "mode": "follow", "status": "ok"}}}),
    json.dumps({"schema": tools_lock.SCHEMA, "updated_at": NOW, "tools": {"x": {"kind": "pip", "source": "https://a.b/c",
                                                                               "mode": "follow", "status": "ok", "ref": "1.0",
                                                                               "sha256": "xyz"}}}),
    json.dumps({"schema": tools_lock.SCHEMA, "updated_at": NOW, "tools": {"x": {"kind": "npm", "source": "http://a.b/c",
                                                                               "mode": "pin", "status": "failed"}}}),
])
def test_lock_corrompido_ou_de_outro_schema_e_recusado(tmp_path, conteudo):
    path = tmp_path / tools_lock.LOCK_FILE
    path.write_text(conteudo, encoding="utf8")
    with pytest.raises(tools_lock.LockInvalid):
        tools_lock.read_lock(path)


# --- which ref is in use: override > lock > pin ------------------------------------------------------------------------


def test_override_vence_o_lock_e_o_lock_vence_o_pin(ambiente, monkeypatch):
    tools_lock.write_lock(_doc(opencut={"kind": "git", "source": tools.get("opencut").source, "mode": "follow",
                                        "status": "ok", "ref": SHA_NEW, "resolved_at": NOW}))
    assert tools.effective(tools.get("opencut")) == (SHA_NEW, "lock")
    monkeypatch.setenv("SIMPLICIO_OPENCUT_REF", "feedbeef")
    assert tools.effective(tools.get("opencut")) == ("feedbeef", "override")


def test_uma_falha_mantem_a_ref_que_esta_no_lugar(ambiente):
    """A failed follow keeps the commit that is still checked out: the lock says so, so the install does not jump back to the pin."""
    tools_lock.write_lock(_doc(opencut={"kind": "git", "source": tools.get("opencut").source, "mode": "follow",
                                        "status": "failed", "ref": SHA_OLD, "error": "git fetch falhou", "failed_at": NOW}))
    assert tools.effective(tools.get("opencut")) == (SHA_OLD, "lock")


def test_pin_no_lock_nao_muda_a_versao_em_uso(ambiente):
    tools_lock.write_lock(_doc(opencut={"kind": "git", "source": tools.get("opencut").source, "mode": "pin", "status": "ok",
                                        "ref": tools.get("opencut").ref, "resolved_at": NOW}))
    assert tools.effective(tools.get("opencut")) == (tools.get("opencut").ref, "pin")


# --- the update: follow, pin, failures, overrides ----------------------------------------------------------------------


def test_update_segue_a_main_e_grava_o_lock(ambiente):
    fake = Fake()
    lines, failed = tools_update.apply_all(tools_lock.empty(), "follow", fake.io(), ambiente / "data" / tools_lock.LOCK_FILE)
    assert failed == 0, lines
    opencut_dir = _checkout(ambiente, "opencut")
    assert fake.ran("checkout", "--detach", SHA_NEW, str(opencut_dir)), fake.calls
    doc = tools_lock.read_lock(ambiente / "data" / tools_lock.LOCK_FILE)
    assert doc["tools"]["opencut"] == {"kind": "git", "source": tools.get("opencut").source, "mode": "follow", "status": "ok",
                                       "ref": SHA_NEW, "branch": "main", "resolved_at": NOW}
    assert doc["tools"]["yt-dlp"]["ref"] == "2026.11.01" and doc["tools"]["yt-dlp"]["sha256"] == DIGEST_NEW
    assert doc["tools"]["hypit"]["ref"] == "0.2.18" and doc["tools"]["hypit"]["mode"] == "follow"
    assert any("atualizada" in line for line in lines)


def test_pip_instala_a_versao_resolvida_com_o_sha256_conferido(ambiente):
    fake = Fake()
    tools_update.apply_all(tools_lock.empty(), "follow", fake.io(), ambiente / "data" / tools_lock.LOCK_FILE)
    installs = fake.ran("-m", "pip", "install")
    assert installs and "--require-hashes" in installs[0]
    requisitos = (ambiente / "tools" / "yt-dlp" / "requirements.txt").read_text(encoding="utf8")
    assert requisitos == f"yt-dlp==2026.11.01 --hash=sha256:{DIGEST_NEW}\n"


def test_npm_e_verificado_com_a_versao_resolvida(ambiente):
    fake = Fake()
    tools_update.apply_all(tools_lock.empty(), "follow", fake.io(), ambiente / "data" / tools_lock.LOCK_FILE)
    assert fake.ran("/fake/npx", "--yes", "@hypit/hypit@0.2.18", "--version")


def test_uma_trilha_que_falha_nao_bloqueia_as_outras_e_mantem_a_anterior(ambiente):
    d = str(_checkout(ambiente, "opencut"))
    fake = Fake(fails={f"git -C {d} fetch": (1, "fatal: could not read from remote repository")})
    lock = ambiente / "data" / tools_lock.LOCK_FILE
    lines, failed = tools_update.apply_all(tools_lock.empty(), "follow", fake.io(), lock)
    assert failed == 1
    assert any(line.strip().startswith("opencut") and "FALHOU" in line for line in lines), lines
    assert any("toonflow" in line and "atualizada" in line for line in lines), lines
    doc = tools_lock.read_lock(lock)
    assert doc["tools"]["opencut"]["status"] == "failed" and "could not read" in doc["tools"]["opencut"]["error"]
    assert doc["tools"]["toonflow"]["status"] == "ok"


def test_uma_falha_com_checkout_anterior_guarda_o_ref_no_lock(ambiente):
    d = str(_checkout(ambiente, "opencut"))
    lock = ambiente / "data" / tools_lock.LOCK_FILE
    tools_lock.write_lock(_doc(opencut={"kind": "git", "source": tools.get("opencut").source, "mode": "follow", "status": "ok",
                                        "ref": SHA_OLD, "branch": "main", "resolved_at": NOW - 10}))
    fake = Fake(fails={f"git -C {d} fetch": (1, "network down")})
    tools_update.apply_all(tools_lock.read_lock(lock), "follow", fake.io(), lock)
    entry = tools_lock.read_lock(lock)["tools"]["opencut"]
    assert entry["status"] == "failed" and entry["ref"] == SHA_OLD and entry["branch"] == "main"


def _vu_ref_do_setup() -> str:
    """The commit the packaged setup.sh pins (VU_REF): the one `edit setup` checks out."""
    text = (paths.DATA_DIR / "tools" / "video-use" / "setup.sh").read_text(encoding="utf8")
    found = re.search(r"^VU_REF=([0-9a-f]{40})\b", text, re.MULTILINE)
    assert found, "o setup.sh empacotado não tem VU_REF de 40 caracteres"
    return found.group(1)


def test_pin_do_video_use_e_o_vu_ref_do_setup_e_nao_refaz_o_checkout_no_lugar(ambiente):
    """video-use's pin is the full VU_REF of the packaged setup.sh: a pin update moves the checkout there once, then leaves it in place."""
    vu_ref = _vu_ref_do_setup()
    d = str(_checkout(ambiente, "video-use"))
    fake = Fake()
    lock = ambiente / "data" / tools_lock.LOCK_FILE
    lines, failed = tools_update.apply_all(tools_lock.empty(), "pin", fake.io(), lock)
    assert failed == 0, lines
    assert fake.ran("checkout", "--detach", vu_ref, d), fake.calls
    fake.calls.clear()
    lines, failed = tools_update.apply_all(tools_lock.read_lock(lock), "pin", fake.io(), lock)
    assert failed == 0 and not fake.ran("checkout", d), "o pin já está no lugar: nenhum checkout de novo"


def test_video_use_nao_segue_a_main_e_fica_no_vu_ref_do_setup(ambiente):
    """`update` in follow mode never moves video-use to upstream: its pin is VU_REF of the packaged setup.sh, the commit that
    `edit setup` checks out again. After an update the lock, the checkout and setup.sh must name the same commit."""
    vu_ref = _vu_ref_do_setup()
    fake = Fake()  # the remote's HEAD of every track is SHA_NEW, video-use included
    lock = ambiente / "data" / tools_lock.LOCK_FILE
    lines, failed = tools_update.apply_all(tools_lock.empty(), "follow", fake.io(), lock)
    assert failed == 0, lines
    assert not fake.ran("ls-remote", tools.get("video-use").source), "o update não deve consultar a main do video-use"
    d = str(_checkout(ambiente, "video-use"))
    doc = tools_lock.read_lock(lock)
    assert doc["tools"]["video-use"]["mode"] == "pin" and doc["tools"]["video-use"]["ref"] == vu_ref
    assert fake.heads[d] == vu_ref, "o checkout fica no commit do setup.sh"
    assert doc["tools"]["opencut"]["ref"] == SHA_NEW, "as outras trilhas continuam seguindo a main"


def test_check_nao_consulta_a_main_do_video_use(ambiente):
    fake = Fake()
    lines = tools_update.report("follow", fake.io(), dry=True)
    assert not fake.ran("ls-remote", tools.get("video-use").source)
    assert any(line.lstrip().startswith("video-use") and "pin" in line for line in lines), lines


def test_video_to_skill_nao_segue_a_main_porque_o_binario_e_o_skill_sao_fixados_juntos(ambiente):
    """The extractor binary (version and sha256 per platform) and the SKILL.md (sha256) are pinned together: following the upstream main
    would leave a SKILL.md that asks for another extractor. `update` records the pin (mode "pin") and leaves the checkout there."""
    pin = tools.get("video_to_skill").ref
    fake = Fake()
    lock = ambiente / "data" / tools_lock.LOCK_FILE
    lines, failed = tools_update.apply_all(tools_lock.empty(), "follow", fake.io(), lock)
    assert failed == 0, lines
    assert not fake.ran("ls-remote", tools.get("video_to_skill").source), "o update não deve consultar a main do video-to-skill"
    d = str(_checkout(ambiente, "video_to_skill"))
    doc = tools_lock.read_lock(lock)
    assert doc["tools"]["video_to_skill"]["mode"] == "pin" and doc["tools"]["video_to_skill"]["ref"] == pin
    assert fake.heads[d] == pin and doc["tools"]["opencut"]["ref"] == SHA_NEW


def test_check_nao_consulta_a_main_do_video_to_skill_e_diz_pin(ambiente):
    fake = Fake()
    lines = tools_update.report("follow", fake.io(), dry=True)
    assert not fake.ran("ls-remote", tools.get("video_to_skill").source)
    assert any(line.lstrip().startswith("video_to_skill") and "pin" in line for line in lines), lines
    assert tools_update.pin_only(tools.get("video_to_skill")) and tools_update.pin_only(tools.get("video-use"))
    assert not tools_update.pin_only(tools.get("matchcut"))


def test_o_pin_do_video_use_e_o_vu_ref_do_setup_sh():
    assert tools.get("video-use").ref == _vu_ref_do_setup()


def _vu_dir_do_setup(env: dict) -> str:
    """The checkout directory setup.sh computes: its VU_DIR line, run by bash with the given environment."""
    line = next(ln for ln in (paths.DATA_DIR / "tools" / "video-use" / "setup.sh").read_text(encoding="utf8").splitlines()
                if ln.startswith("VU_DIR="))
    done = subprocess.run(["bash", "-c", line + '\nprintf %s "$VU_DIR"'], env=env, capture_output=True, text=True,
                          stdin=subprocess.DEVNULL, check=True)
    return done.stdout


def test_checkout_padrao_do_video_use_e_o_do_setup_sh(tmp_path, monkeypatch):
    """Without VIDEO_USE_DIR the checkout is ~/.cache/simplicio/video-use, the same folder setup.sh computes from $HOME."""
    if shutil.which("bash") is None:
        pytest.skip("setup.sh roda em bash")
    home = tmp_path / "home"
    monkeypatch.delenv("VIDEO_USE_DIR", raising=False)
    monkeypatch.setenv("HOME", str(home))
    expected = home / ".cache" / "simplicio" / "video-use"
    assert tools_update.checkout_for(tools.get("video-use")) == expected
    assert Path(_vu_dir_do_setup({"HOME": str(home), "PATH": os.environ.get("PATH", "")})) == expected


def test_video_use_dir_com_til_vai_como_esta_como_no_setup_sh(tmp_path, monkeypatch):
    """bash does not expand ~ inside VIDEO_USE_DIR: the Python side must not either, or the two would pick different folders."""
    if shutil.which("bash") is None:
        pytest.skip("setup.sh roda em bash")
    monkeypatch.setenv("VIDEO_USE_DIR", "~/vu")
    env = {"HOME": str(tmp_path), "PATH": os.environ.get("PATH", ""), "VIDEO_USE_DIR": "~/vu"}
    assert tools_update.checkout_for(tools.get("video-use")) == Path(_vu_dir_do_setup(env)) == Path("~/vu")


def test_checkout_padrao_vem_da_home_do_hostos(tmp_path, monkeypatch):
    """The default home comes from hostos.home_dir, the repo's rule (tools_lock uses it too), not from Path.home()."""
    monkeypatch.delenv("VIDEO_USE_DIR", raising=False)
    casa = tmp_path / "casa"
    monkeypatch.setattr(hostos, "home_dir", lambda environ=None: casa)
    assert tools_update.checkout_for(tools.get("video-use")) == casa / ".cache" / "simplicio" / "video-use"


def test_marcador_ausente_no_commit_novo_volta_ao_anterior(ambiente):
    d = str(_checkout(ambiente, "toonflow"))
    fake = Fake(drop_marker_on=SHA_NEW)
    lines, failed = tools_update.apply_all(tools_lock.empty(), "follow", fake.io(), ambiente / "data" / tools_lock.LOCK_FILE)
    assert failed >= 1
    assert fake.ran("checkout", "--detach", SHA_OLD, d), "o commit anterior tem de voltar ao checkout"
    assert any("toonflow" in line and "FALHOU" in line and "package.json" in line for line in lines), lines


def test_override_nao_e_atualizado_nem_consultado(ambiente, monkeypatch):
    monkeypatch.setenv("SIMPLICIO_OPENCUT_REF", "feedbeef")
    fake = Fake()
    lines, failed = tools_update.apply_all(tools_lock.empty(), "follow", fake.io(), ambiente / "data" / tools_lock.LOCK_FILE)
    assert failed == 0
    assert not fake.ran(tools.get("opencut").source), "um override não consulta o upstream dessa trilha"
    assert not fake.ran("checkout", "--detach", SHA_NEW, str(_checkout(ambiente, "opencut")))
    assert tools_lock.read_lock(ambiente / "data" / tools_lock.LOCK_FILE)["tools"]["opencut"]["mode"] == "override"


def test_pin_nao_consulta_a_rede_e_volta_aos_pins(ambiente):
    fake = Fake()
    tools_update.apply_all(tools_lock.empty(), "pin", fake.io(), ambiente / "data" / tools_lock.LOCK_FILE)
    assert not fake.ran("ls-remote") and not fake.urls and not fake.ran("npm", "view")
    assert fake.ran("checkout", "--detach", tools.get("opencut").ref, str(_checkout(ambiente, "opencut")))
    doc = tools_lock.read_lock(ambiente / "data" / tools_lock.LOCK_FILE)
    assert doc["tools"]["yt-dlp"]["mode"] == "pin" and doc["tools"]["yt-dlp"]["ref"] == tools.get("yt-dlp").ref
    assert doc["tools"]["yt-dlp"]["sha256"] == tools.get("yt-dlp").sha256


def test_offline_nao_consulta_nada_e_marca_as_falhas(ambiente):
    fake = Fake()
    io = fake.io(network=False)
    lock = ambiente / "data" / tools_lock.LOCK_FILE
    lines, failed = tools_update.apply_all(tools_lock.empty(), "follow", io, lock)
    assert failed == len(tools.TOOLS) and fake.calls == [] and fake.urls == []
    assert all("SIMPLICIO_OFFLINE=1" in line for line in lines if "FALHOU" in line)


# --- --check and --dry-run: say what would happen, write nothing ----------------------------------------------------


def test_dry_run_mostra_o_plano_e_nao_escreve_nem_muda_checkout(ambiente):
    fake = Fake()
    lines = tools_update.report("follow", fake.io(), dry=True)
    assert any("seguiria" in line for line in lines), lines
    assert not (ambiente / "data" / tools_lock.LOCK_FILE).exists()
    assert not fake.ran("checkout") and not fake.ran("fetch") and not fake.ran("pip", "install") and not fake.ran("npx")


def test_check_mostra_quem_esta_atras_e_nao_grava(ambiente):
    fake = Fake()
    lines = tools_update.report("follow", fake.io(), dry=False)
    assert any("atrás" in line and "opencut" in line for line in lines), lines
    assert any("atrás" in line and "yt-dlp" in line and "2026.11.01" in line for line in lines), lines
    assert not (ambiente / "data" / tools_lock.LOCK_FILE).exists()


def test_check_diz_em_dia_quando_o_lock_ja_esta_no_remoto(ambiente):
    tools_lock.write_lock(_doc(opencut={"kind": "git", "source": tools.get("opencut").source, "mode": "follow", "status": "ok",
                                        "ref": SHA_NEW, "branch": "main", "resolved_at": NOW}))
    lines = tools_update.report("follow", Fake().io(), dry=False)
    assert any("em dia" in line and "opencut" in line for line in lines), lines


def test_check_offline_nao_consulta(ambiente):
    lines = tools_update.report("follow", Fake().io(network=False), dry=False)
    # video-use is pinned locally (its pin is the packaged setup.sh): it is not a network read, so it is "no pin", not "não consultado"
    assert all("não consultado" in line or "fixada" in line or line.lstrip().startswith("video-use") for line in lines), lines
    assert any(line.lstrip().startswith("video-use") and "no pin" in line for line in lines), lines


# --- the command (update through main, with the fake) -----------------------------------------------------------------


@pytest.fixture
def pacote_pip(monkeypatch, ambiente):
    """`update` as a pip install with a newer release, the track network replaced by the fake, the release calls recorded."""
    fake = Fake()
    chamadas: list[list[str]] = []
    monkeypatch.setattr(update_cmd, "_has_pip", lambda: True)
    monkeypatch.setattr(update_cmd, "is_pep668_environment", lambda **kw: (False, None))
    monkeypatch.setattr(update_cmd, "fetch_latest_tag", lambda: "v99.0.0")
    monkeypatch.setattr(update_cmd, "_run", lambda argv, cwd=None: chamadas.append([str(a) for a in argv]) or 0)
    monkeypatch.setattr(update_cmd.distribution, "kind", lambda **kw: "pip")
    monkeypatch.setattr(tools_update, "live_io", lambda: fake.io())
    return fake, chamadas


def test_update_pela_cli_segue_as_trilhas_depois_do_pacote(pacote_pip, ambiente, capsys):
    fake, chamadas = pacote_pip
    assert main(["update"]) == 0
    assert [c[1:4] for c in chamadas] == [["-m", "pip", "install"], ["-m", "simplicio_video", "install"]]
    out = capsys.readouterr().out
    assert "trilhas externas (seguem o upstream" in out and "opencut" in out
    assert tools_lock.read_lock(ambiente / "data" / tools_lock.LOCK_FILE)["tools"]["opencut"]["ref"] == SHA_NEW


def test_update_dry_run_pela_cli_nao_grava_o_lock(pacote_pip, ambiente, capsys):
    fake, chamadas = pacote_pip
    assert main(["update", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "trilhas externas, o plano" in out and "seguiria" in out
    assert not (ambiente / "data" / tools_lock.LOCK_FILE).exists()
    assert not fake.ran("checkout") and not fake.ran("pip", "install")


def test_update_pin_pela_cli_volta_aos_pins(pacote_pip, ambiente, capsys):
    fake, _ = pacote_pip
    assert main(["update", "--pin"]) == 0
    out = capsys.readouterr().out
    assert "--pin: voltam aos pins" in out
    assert not fake.ran("ls-remote")
    assert tools_lock.read_lock(ambiente / "data" / tools_lock.LOCK_FILE)["tools"]["opencut"]["mode"] == "pin"


def test_update_check_pela_cli_reporta_as_trilhas_e_mantem_os_codigos(pacote_pip, ambiente, capsys):
    rc = main(["update", "--check"])
    out = capsys.readouterr().out
    assert rc == 10, "a regra de codigos do update não muda: 10 quando há release nova"
    assert "trilhas externas, o que está atrás" in out and "atrás" in out
    assert not (ambiente / "data" / tools_lock.LOCK_FILE).exists()


# --- the places that show it: tools and doctor ------------------------------------------------------------------------


def test_tools_mostra_o_uso_efetivo_e_o_lock(ambiente):
    tools_lock.write_lock(_doc(opencut={"kind": "git", "source": tools.get("opencut").source, "mode": "follow", "status": "ok",
                                        "ref": SHA_NEW, "branch": "main", "resolved_at": NOW}))
    row = next(r for r in tools.listing() if r["name"] == "opencut")
    assert row["effective_version"] == SHA_NEW and row["effective_source"] == "lock"
    assert row["lock"]["ref"] == SHA_NEW and row["version"] == tools.get("opencut").ref
    text = tools.text_listing(tools.listing())
    assert f"em uso: {SHA_NEW} (lock)" in text and "lock: follow" in text


def test_doctor_mostra_o_lock_e_avisa_trilha_que_falhou(ambiente):
    doc = collect_tools(ambiente)
    assert doc["status"] == "ok" and "sem lock" in doc["summary"]
    tools_lock.write_lock(_doc(opencut={"kind": "git", "source": tools.get("opencut").source, "mode": "follow",
                                        "status": "failed", "ref": SHA_OLD, "error": "fatal", "failed_at": NOW}))
    doc = collect_tools(ambiente)
    assert doc["status"] == "warn" and "opencut" in doc["summary"] and "falhou" in doc["summary"]
    assert doc["fix"] == "simplicio-video update"


def test_doctor_avisa_lock_corrompido_sem_derrubar_o_resto(ambiente):
    (ambiente / "data").mkdir(parents=True, exist_ok=True)
    (ambiente / "data" / tools_lock.LOCK_FILE).write_text("{ nao e json", encoding="utf8")
    doc = collect_tools(ambiente)
    assert doc["status"] == "warn" and "inválido" in doc["summary"]


def collect_tools(ambiente: Path) -> dict:
    report = doctor_cmd.collect(only="tools", state_dir=ambiente / "data", kind="pip", installed="0.6.0")
    (row,) = report["checks"]
    assert row["name"] == "tools"
    return row


# --- a read that times out takes its whole process tree with it ---------------------------------------------------------------


def _vivo(pid: int) -> bool:
    """True while the process exists and is not a zombie (a container's init may never reap the orphans)."""
    estado = subprocess.run(["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True).stdout.strip()
    return bool(estado) and not estado.startswith("Z")


def _espera_morrer(pid: int, limite_s: float = 5.0) -> bool:
    fim = time.monotonic() + limite_s
    while time.monotonic() < fim:
        if not _vivo(pid):
            return True
        time.sleep(0.05)
    return not _vivo(pid)


@pytest.mark.skipif(os.name == "nt", reason="process groups (taskkill /T on Windows: UNVERIFIED)")
def test_leitura_com_tempo_esgotado_nao_deixa_descendente_vivo(tmp_path, monkeypatch):
    """`git ls-remote` runs `git-remote-https` as a child. subprocess.run(timeout=) kills only the parent: the child stays alive (a proxy
    that accepts and never answers left 8 of them). The read runs in its own session and the whole group is killed."""
    pidfile = tmp_path / "neto.pid"
    script = tmp_path / "falso-git"
    script.write_text(f"#!/bin/sh\nsleep 300 &\necho $! > '{pidfile}'\nwait\n", encoding="utf-8")
    script.chmod(0o755)
    monkeypatch.setattr(tools_update, "READ_TIMEOUT_S", 1)
    with pytest.raises(subprocess.TimeoutExpired):
        tools_update._run_leitura([str(script), "ls-remote"])
    neto = int(pidfile.read_text().strip())
    try:
        assert _espera_morrer(neto), f"o processo {neto} (filho do git) continua vivo depois do tempo esgotado"
    finally:
        if _vivo(neto):
            os.kill(neto, 9)


@pytest.mark.skipif(os.name == "nt", reason="process groups")
def test_git_com_limite_mata_o_grupo_e_vira_toolerror(tmp_path, monkeypatch):
    """tools._git(timeout=) is what the doctor uses on a local checkout: a git that hangs is a ToolError, and leaves nothing running."""
    pidfile = tmp_path / "neto.pid"
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    script = bin_ / "git"
    script.write_text(f"#!/bin/sh\nsleep 300 &\necho $! > '{pidfile}'\nwait\n", encoding="utf-8")
    script.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_}{os.pathsep}{os.environ['PATH']}")
    with pytest.raises(tools.ToolError, match="tempo"):
        REAL_GIT("rev-parse", "HEAD", cwd=tmp_path, timeout=1)
    neto = int(pidfile.read_text().strip())
    try:
        assert _espera_morrer(neto)
    finally:
        if _vivo(neto):
            os.kill(neto, 9)
