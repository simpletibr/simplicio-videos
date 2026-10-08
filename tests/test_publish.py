"""`publish` with rclone mocked: upload path, never-overwrite, idempotency, README link table."""
import hashlib
import json
import subprocess

import pytest

from simplicio_video import contract as ct
from simplicio_video import publish as pub

README = """# Teste Mini

## Entregas no Drive

| Campanha | Pasta | Arquivo | Link | Versão / status |
|---|---|---|---|---|
| Outra | 2026/Outra | Teste - outra - v01.mp4 | [abrir](https://drive.google.com/file/d/OLD/view) | ok |
"""


DESTINO = {"caminho": "simplicio-video/clientes/Teste_Mini/2026/Teste_Hash", "arquivo": "Teste - mini - v01.mp4"}


def _cp(rc=0, out="", err=""):
    return subprocess.CompletedProcess([], rc, out, err)


@pytest.fixture
def mp4(mini):
    p = mini.parent / "out" / "mini.mp4"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"fake-mp4-bytes")
    return p


class Drive:
    """Minimal fake of `rclone lsjson/copyto` on a Google Drive remote."""

    def __init__(self, files=None):
        self.files, self.calls = dict(files or {}), []

    def __call__(self, cmd):
        self.calls.append(cmd)
        if cmd[1] == "copyto":
            data = open(cmd[2], "rb").read()
            self.files[cmd[3].rsplit("/", 1)[1]] = data
            return _cp()
        if cmd[1] == "lsjson":
            if "--dirs-only" in cmd:
                return _cp(0, json.dumps([{"Name": "Teste_Hash", "ID": "FOLDER123", "IsDir": True}]))
            if not self.files:
                return _cp(3, "", "directory not found")
            return _cp(0, json.dumps([{"Name": n, "Size": len(b), "ID": f"FILE-{n[:5]}", "Hashes": {"md5": hashlib.md5(b).hexdigest()}}
                                      for n, b in self.files.items()]))
        raise AssertionError(cmd)


def test_publish_uploads_and_writes_readme(mini, mp4, tmp_path, monkeypatch):
    monkeypatch.setenv("SIMPLICIO_RCLONE_BIN", "rclone")
    readme = tmp_path / "README.md"
    readme.write_text(README)
    drive = Drive()
    res = pub.publish(ct.load(mini), destino=DESTINO, remote="gdrive", readme=readme, run=drive, log=lambda *_: None)
    copy = [c for c in drive.calls if c[1] == "copyto"][0]
    assert copy[3] == "gdrive:simplicio-video/clientes/Teste_Mini/2026/Teste_Hash/Teste - mini - v01.mp4"
    assert res["status"] == "uploaded" and res["link"] == "https://drive.google.com/file/d/FILE-Teste/view"
    assert res["folder_url"] == "https://drive.google.com/drive/folders/FOLDER123"
    assert not any(c[1] == "link" for c in drive.calls)  # never changes sharing
    txt = readme.read_text()
    assert "| Teste_Hash | [2026/Teste_Hash](https://drive.google.com/drive/folders/FOLDER123) | Teste - mini - v01.mp4 | [abrir](https://drive.google.com/file/d/FILE-Teste/view) |" in txt
    assert "Teste - outra - v01.mp4" in txt and txt.index("outra") < txt.index("mini - v01")


def test_publish_is_idempotent_and_updates_row(mini, mp4, tmp_path, monkeypatch):
    monkeypatch.setenv("SIMPLICIO_RCLONE_BIN", "rclone")
    readme = tmp_path / "README.md"
    readme.write_text(README + "| Teste_Hash | 2026/Teste_Hash | Teste - mini - v01.mp4 | **(preencher: link do Drive)** | aguardando |\n")
    drive = Drive({"Teste - mini - v01.mp4": mp4.read_bytes()})
    res = pub.publish(ct.load(mini), destino=DESTINO, readme=readme, run=drive, log=lambda *_: None)
    assert res["status"] == "already-published" and not any(c[1] == "copyto" for c in drive.calls)
    txt = readme.read_text()
    assert txt.count("Teste - mini - v01.mp4") == 1 and "[abrir](https://drive.google.com/file/d/FILE-Teste/view) | aguardando |" in txt


def test_publish_never_overwrites(mini, mp4, tmp_path, monkeypatch):
    monkeypatch.setenv("SIMPLICIO_RCLONE_BIN", "rclone")
    drive = Drive({"Teste - mini - v01.mp4": b"other bytes"})
    with pytest.raises(SystemExit, match="vNN"):
        pub.publish(ct.load(mini), destino=DESTINO, readme=tmp_path / "R.md", run=drive, log=lambda *_: None)
    assert not any(c[1] == "copyto" for c in drive.calls)


def test_publish_dry_run_needs_no_rclone(mini, mp4, monkeypatch):
    monkeypatch.delenv("SIMPLICIO_RCLONE_BIN", raising=False)
    monkeypatch.setenv("PATH", "/nonexistent")
    res = pub.publish(ct.load(mini), destino=DESTINO, dry_run=True, log=lambda *_: None)
    assert res["dry_run"] and res["dest"].startswith("gdrive:simplicio-video/clientes/Teste_Mini/2026/Teste_Hash/")


def test_publish_missing_mp4(mini):
    with pytest.raises(SystemExit, match="render"):
        pub.publish(ct.load(mini), destino=DESTINO, dry_run=True, log=lambda *_: None)
