"""`simplicio-video media fetch`: the pinned yt-dlp in its own venv, the consent gate, the URL rules and the provenance record.
Hermetic: the downloader is a fake script or a patched function; no socket is opened (the real run is the integration test)."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from simplicio_video import download, media, tools

SHA_WHEEL = "a05c5b5d8562f7e8a62f5334348b406af4930d56d3a65f8021d14af0e22339ae"
POSIX = os.name == "posix"


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("SIMPLICIO_TOOLS_DIR", str(tmp_path / "tools"))
    monkeypatch.delenv("SIMPLICIO_YT-DLP_REF", raising=False)
    return tmp_path


def _fake_ytdlp(tmp_path: Path, body: str) -> Path:
    """A stand-in for the pinned yt-dlp: a python script with the same command line. `body` runs after the argument parsing;
    the variables `out` (the -o template folder), `url` and `args` are in scope."""
    script = tmp_path / "fake-yt-dlp"
    script.write_text(
        f"#!{sys.executable}\n"
        "import json, os, sys, time\n"
        "args = sys.argv[1:]\n"
        "url = args[-1]\n"
        "tpl = args[args.index('-o') + 1]\n"
        "out = os.path.dirname(tpl)\n"
        + body,
        encoding="utf8")
    script.chmod(0o755)
    return script


# ----------------------------------------------------------------------------------------------- registry and install

def test_yt_dlp_is_a_pinned_pip_tool_with_a_hash():
    t = tools.get("yt-dlp")
    assert t.kind == "pip" and t.name == "yt-dlp"
    assert t.ref == "2026.10.26" and t.sha256 == SHA_WHEEL and len(t.sha256) == 64
    assert t.license == "Unlicense"
    assert t.source == "https://github.com/yt-dlp/yt-dlp"
    assert tools.command(t) == "simplicio-video media fetch"


def test_install_writes_a_hashed_requirement_and_pip_refuses_anything_else(tmp_path, monkeypatch):
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        if cmd[1:3] == ["-m", "venv"]:
            py = Path(cmd[3]) / ("Scripts" if os.name == "nt" else "bin") / "python"
            py.parent.mkdir(parents=True)
            py.write_text("", encoding="utf8")
        if "pip" in cmd:
            exe = Path(cmd[0]).parent / "yt-dlp"
            exe.write_text("", encoding="utf8")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(tools.subprocess, "run", fake_run)
    exe = tools.install("yt-dlp")
    assert exe.endswith("yt-dlp") and tools.pip_binary("yt-dlp") is not None
    req = (tmp_path / "tools" / "yt-dlp" / "requirements.txt").read_text(encoding="utf8")
    assert req == f"yt-dlp==2026.10.26 --hash=sha256:{SHA_WHEEL}\n"
    pip_call = next(c for c in calls if "pip" in c)
    assert "--require-hashes" in pip_call and "-r" in pip_call


def test_a_version_override_is_refused_because_the_hash_would_not_match(monkeypatch):
    monkeypatch.setenv("SIMPLICIO_YT-DLP_REF", "2026.11.01")
    with pytest.raises(tools.ToolError, match="hash"):
        tools.install("yt-dlp")


def test_pip_failure_is_reported_with_the_pip_message(monkeypatch):
    def fake_run(cmd, **kw):
        if cmd[1:3] == ["-m", "venv"]:
            py = Path(cmd[3]) / ("Scripts" if os.name == "nt" else "bin") / "python"
            py.parent.mkdir(parents=True)
            py.write_text("", encoding="utf8")
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        return SimpleNamespace(returncode=1, stdout="", stderr="THESE PACKAGES DO NOT MATCH THE HASHES")

    monkeypatch.setattr(tools.subprocess, "run", fake_run)
    with pytest.raises(tools.ToolError, match="DO NOT MATCH"):
        tools.install("yt-dlp")


# ------------------------------------------------------------------------------------------------------ URL and consent

@pytest.mark.parametrize("url", [
    "https://user:senha@example.com/v.mp4",
    "ftp://example.com/v.mp4",
    "file:///etc/passwd",
    "javascript:alert(1)",
    "https://exa mple.com/v.mp4",
    "",
    "https://" + "a" * 3000 + ".com/v.mp4",
])
def test_validate_url_refuses_what_is_not_a_plain_http_url(url):
    with pytest.raises(download.DownloadError):
        download.validate_url(url)


def test_the_record_keeps_the_source_without_query_or_fragment():
    assert download.record_url("https://www.instagram.com/reel/ABC/?igsh=tracking&x=1#frag") == "https://www.instagram.com/reel/ABC/"


def test_fetch_needs_consent_and_never_reaches_the_downloader(tmp_path, monkeypatch):
    def boom():
        raise AssertionError("o downloader não pode rodar sem --autorizo")

    monkeypatch.setattr(download, "_binario", boom)
    with pytest.raises(download.DownloadError, match="--autorizo"):
        download.fetch("https://example.com/v.mp4", tmp_path / "v.mp4", autorizo=False)
    assert not (tmp_path / "v.mp4").exists()


def test_media_fetch_without_autorizo_is_refused_before_anything_is_created(tmp_path):
    with pytest.raises(media.MediaError, match="--autorizo"):
        media.run_media(["fetch", "https://example.com/v.mp4", "-o", str(tmp_path / "sub" / "v.mp4")])
    assert not (tmp_path / "sub").exists()


def test_autorizo_is_a_flag_and_does_not_eat_the_next_argument():
    pos, vals = media._parse(["https://example.com/v.mp4", "-o", "v.mp4", "--autorizo", "--max-mb", "5"])
    assert pos == ["https://example.com/v.mp4"]
    assert vals == {"-o": "v.mp4", "--autorizo": "1", "--max-mb": "5"}


def test_fetch_refuses_to_overwrite_the_mp4_or_its_record(tmp_path, monkeypatch):
    monkeypatch.setattr(download, "_binario", lambda: pytest.fail("não deve baixar"))
    (tmp_path / "v.mp4").write_bytes(b"x")
    with pytest.raises(download.DownloadError, match="não sobrescrevo"):
        download.fetch("https://example.com/v.mp4", tmp_path / "v.mp4", autorizo=True)
    (tmp_path / "w.mp4").touch()
    (tmp_path / "w.fetch.json").write_text("{}", encoding="utf8")
    with pytest.raises(download.DownloadError, match="não sobrescrevo"):
        download.fetch("https://example.com/v.mp4", tmp_path / "w.mp4", autorizo=True)
    assert (tmp_path / "v.mp4").read_bytes() == b"x"


def test_fetch_wants_an_mp4_name(tmp_path):
    with pytest.raises(download.DownloadError, match=".mp4"):
        download.fetch("https://example.com/v.mp4", tmp_path / "v.webm", autorizo=True)


# ----------------------------------------------------------------------------------------- the download and the record

@pytest.mark.skipif(not POSIX, reason="o teste usa um script com shebang")
def test_fetch_downloads_hashes_and_writes_the_record(tmp_path, monkeypatch):
    fake = _fake_ytdlp(tmp_path, (
        "data = b'mp4 bytes'\n"
        "open(os.path.join(out, 'abc123.mp4'), 'wb').write(data)\n"
        "print(json.dumps({'id': 'abc123', 'ext': 'mp4', 'extractor_key': 'Instagram', 'title': 'Ovo e cachorro',\n"
        "                  'uploader': 'veramundopet', 'duration': 58.2}))\n"
    ))
    monkeypatch.setattr(download, "_binario", lambda: fake)
    dest = tmp_path / "reel.mp4"
    doc = download.fetch("https://www.instagram.com/veramundopet/reel/abc123/?igsh=x", dest, autorizo=True)
    assert dest.read_bytes() == b"mp4 bytes"
    assert doc["sha256"] == hashlib.sha256(b"mp4 bytes").hexdigest() and doc["bytes"] == 9
    saved = json.loads((tmp_path / "reel.fetch.json").read_text(encoding="utf8"))
    assert saved == doc
    assert saved["schema"] == download.FETCH_SCHEMA and saved["autorizado"] is True
    assert saved["origem"] == "https://www.instagram.com/veramundopet/reel/abc123/"
    assert saved["ferramenta"] == {"name": "yt-dlp", "version": "2026.10.26"}
    assert saved["untrusted_titulo"] == "Ovo e cachorro" and saved["untrusted_autor"] == "veramundopet"
    assert "aviso" in saved and saved["baixado_em"].endswith("Z")
    assert [p.name for p in tmp_path.iterdir() if p.name.startswith(".fetch-")] == []


@pytest.mark.skipif(not POSIX, reason="o teste usa um script com shebang")
def test_fetch_runs_yt_dlp_with_the_safe_options_and_a_closed_environment(tmp_path, monkeypatch):
    seen = tmp_path / "argv.json"
    fake = _fake_ytdlp(tmp_path, (
        f"open({str(seen)!r}, 'w').write(json.dumps({{'args': args, 'env': sorted(os.environ)}}))\n"
        "open(os.path.join(out, 'x.mp4'), 'wb').write(b'a')\n"
        "print(json.dumps({'id': 'x', 'ext': 'mp4'}))\n"
    ))
    monkeypatch.setattr(download, "_binario", lambda: fake)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-segredo")
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.local:3128")
    download.fetch("https://example.com/v.mp4", tmp_path / "v.mp4", autorizo=True)
    data = json.loads(seen.read_text(encoding="utf8"))
    args = data["args"]
    for flag in ("--ignore-config", "--no-playlist", "--no-cache-dir", "--print-json"):
        assert flag in args
    assert "--cookies" not in args and "--cookies-from-browser" not in " ".join(args)
    assert "OPENAI_API_KEY" not in data["env"] and "HTTPS_PROXY" in data["env"]


@pytest.mark.skipif(not POSIX, reason="o teste usa um script com shebang")
def test_fetch_stops_at_the_timeout_and_leaves_nothing_behind(tmp_path, monkeypatch):
    fake = _fake_ytdlp(tmp_path, "time.sleep(30)\n")
    monkeypatch.setattr(download, "_binario", lambda: fake)
    with pytest.raises(download.DownloadError, match="passou de 1 s"):
        download.fetch("https://example.com/v.mp4", tmp_path / "v.mp4", autorizo=True, timeout=1)
    assert not (tmp_path / "v.mp4").exists()
    assert [p.name for p in tmp_path.iterdir() if p.name.startswith(".fetch-")] == []


@pytest.mark.skipif(not POSIX, reason="o teste usa um script com shebang")
def test_fetch_refuses_a_file_over_max_mb(tmp_path, monkeypatch):
    fake = _fake_ytdlp(tmp_path, (
        "open(os.path.join(out, 'big.mp4'), 'wb').write(b'0' * (2 * 1024 * 1024))\n"
        "print(json.dumps({'id': 'big', 'ext': 'mp4'}))\n"
    ))
    monkeypatch.setattr(download, "_binario", lambda: fake)
    with pytest.raises(download.DownloadError, match="max-mb 1"):
        download.fetch("https://example.com/v.mp4", tmp_path / "v.mp4", autorizo=True, max_mb=1)
    assert not (tmp_path / "v.mp4").exists()


@pytest.mark.skipif(not POSIX, reason="o teste usa um script com shebang")
def test_yt_dlp_error_is_reported_in_one_line(tmp_path, monkeypatch):
    fake = _fake_ytdlp(tmp_path, (
        "sys.stderr.write('WARNING: algo\\nERROR: [Instagram] login required\\n')\n"
        "sys.exit(1)\n"
    ))
    monkeypatch.setattr(download, "_binario", lambda: fake)
    with pytest.raises(download.DownloadError, match="login required"):
        download.fetch("https://example.com/v.mp4", tmp_path / "v.mp4", autorizo=True)


def test_media_fetch_through_the_cli_passes_the_consent_and_the_options(tmp_path, monkeypatch):
    seen = {}

    def fake_fetch(url, dest, autorizo, max_mb, timeout):
        seen.update(url=url, dest=dest, autorizo=autorizo, max_mb=max_mb, timeout=timeout)
        return {"sha256": "x"}

    monkeypatch.setattr(download, "fetch", fake_fetch)
    rc = media.run_media(["fetch", "https://example.com/v.mp4", "-o", str(tmp_path / "v.mp4"), "--autorizo", "--max-mb", "7",
                          "--timeout", "90"])
    assert rc == 0
    assert seen == {"url": "https://example.com/v.mp4", "dest": tmp_path / "v.mp4", "autorizo": True, "max_mb": 7, "timeout": 90}


@pytest.mark.integration
def test_real_download_of_a_public_mp4_when_the_url_is_given(tmp_path):
    """Needs network and a real install of the pinned yt-dlp. Run with SIMPLICIO_TEST_FETCH_URL=<public mp4 page>."""
    url = os.environ.get("SIMPLICIO_TEST_FETCH_URL")
    if not url:
        pytest.skip("defina SIMPLICIO_TEST_FETCH_URL com uma página pública que o yt-dlp saiba baixar")
    doc = download.fetch(url, tmp_path / "real.mp4", autorizo=True, max_mb=50, timeout=300)
    assert doc["bytes"] > 0 and len(doc["sha256"]) == 64
