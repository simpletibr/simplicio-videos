"""video-to-skill: the pinned release table, the safe extraction of the one executable and `setup`. All offline: the download is a
fake that returns bytes the test built, and the extractor is a fake script (tests/_fake_vts.py). Nothing here is the upstream."""
from __future__ import annotations

import copy
import hashlib
import io
import json
import os
import re
import stat
import tarfile
import zipfile
from pathlib import Path

import pytest
import _fake_vts as fake

from simplicio_video import cli, paths, tools, video_to_skill as v2s

COMMIT = "c1a1b905da6a252077ace0657e8ea49cb785e7c3"
BASE = "https://github.com/brenoepics/video-to-skill/releases/download/v0.3.0/"
# Measured on 2026-11-06: the four release assets of v0.3.0 were downloaded, their sha256 equals the published .sha256 sidecar of
# each one, and the single member of each archive was extracted and hashed.
REAL = {
    "linux-x86_64": ("vts-extract-linux-x86_64.tar.gz", "4c97963b9c6fc97ed0529bbf6ba8847ae68d6938c24197f6fa8b76051155a45a",
                     "3477d8fc387df93109e919a253e356d1ee37ba22c87d946cc8fc6456b71c2f5e", 9393648, "vts-extract"),
    "macos-arm64": ("vts-extract-macos-arm64.tar.gz", "eda9d074cfb8d13c05a252ecab8bc31f811f7ec363bb10b4b80117389653d6a7",
                    "7a6855e22004103fca705c862fcd6435796eac291753381aeb8738c1b779534f", 8258496, "vts-extract"),
    "macos-x86_64": ("vts-extract-macos-x86_64.tar.gz", "b0cd840e0e77f9b4242ad3911bc1d717a4caa4763acaf649e532578f5e05dae3",
                     "e4bb27720be8d44581d1ca37047367782d489bb87dadbf405620af1e162815fe", 9075264, "vts-extract"),
    "windows-x86_64": ("vts-extract-windows-x86_64.zip", "e23646056b585fac18cceb2f9d51683b60c589875fcedf162a32cd54e468b92e",
                       "0add8350b717736d1d9ee772161de34354bb81b7c1fa38b5741ce3d9d3512e94", 7570432, "vts-extract.exe"),
}
HEX64 = re.compile(r"^[0-9a-f]{64}$")
posix_only = pytest.mark.skipif(os.name != "posix", reason="the fake extractor is a shebang script")


@pytest.fixture(autouse=True)
def _isolated(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("SIMPLICIO_TOOLS_DIR", str(tmp_path / "tools"))
    monkeypatch.setenv("SIMPLICIO_VIDEO_DATA", str(tmp_path / "dados"))
    for var in ("VIDEO_TO_SKILL_DIR", "SIMPLICIO_VIDEO_TO_SKILL_DIR", "VTS_DATA_DIR", "SIMPLICIO_VIDEO_TO_SKILL_REF"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(v2s, "_platform", lambda: ("Linux", "x86_64"))


# ------------------------------------------------------------------------------------------------------------- the table

def test_the_track_is_pinned_to_the_v0_3_0_commit_under_mit():
    t = tools.get("video_to_skill")
    assert t.kind == "git" and t.source == "https://github.com/brenoepics/video-to-skill"
    assert t.ref == COMMIT and t.license == "MIT" and t.marker == "SKILL.md"
    assert tools.COMMANDS["video_to_skill"] == "video-to-skill"
    assert "Breno Epics" in t.role or "Breno Epics" in t.note


def test_the_pin_table_says_the_same_commit_and_version_as_the_registry():
    pins = v2s.PINS
    assert pins["schema"] == "simplicio.video-to-skill-pins/v1"
    assert pins["commit"] == tools.get("video_to_skill").ref == COMMIT
    assert pins["version"] == v2s.VERSION == "0.3.0" and pins["tag"] == "v0.3.0"
    assert pins["release_url_base"] == BASE and pins["source"] == "https://github.com/brenoepics/video-to-skill"


def test_the_table_holds_the_four_assets_measured_on_2026_11_06():
    got = {a["platform"]: a for a in v2s.PINS["assets"]}
    assert set(got) == set(REAL)
    for plat, (nome, sha, member_sha, size, member) in REAL.items():
        a = got[plat]
        assert (a["file"], a["sha256"], a["member_sha256"], a["member_size"], a["member"]) == (nome, sha, member_sha, size, member)


def test_every_asset_is_complete_and_its_names_agree_with_the_platform():
    seen = set()
    for a in v2s.PINS["assets"]:
        plat = a["platform"]
        assert re.fullmatch(r"(linux|macos|windows)-(x86_64|arm64)", plat), plat
        ext = "zip" if plat.startswith("windows") else "tar.gz"
        assert a["format"] == ext and a["file"] == f"vts-extract-{plat}.{ext}"
        assert HEX64.match(a["sha256"]) and HEX64.match(a["member_sha256"]) and a["sha256"] != a["member_sha256"]
        assert isinstance(a["size"], int) and 0 < a["size"] < v2s.MAX_ARCHIVE_BYTES
        assert isinstance(a["member_size"], int) and 0 < a["member_size"] <= v2s.MAX_MEMBER_BYTES
        assert a["member"] == ("vts-extract.exe" if plat.startswith("windows") else "vts-extract")
        assert a["system"] in ("Linux", "Darwin", "Windows") and a["machines"] and all(isinstance(m, str) for m in a["machines"])
        assert v2s.asset_url(a) == BASE + a["file"]
        assert a["file"] not in seen
        seen.add(a["file"])


def test_the_platform_detection_picks_exactly_one_asset_per_system_and_machine():
    cases = {("Linux", "x86_64"): "linux-x86_64", ("Linux", "AMD64"): "linux-x86_64", ("Darwin", "arm64"): "macos-arm64",
             ("Darwin", "x86_64"): "macos-x86_64", ("Windows", "AMD64"): "windows-x86_64", ("Windows", "x86_64"): "windows-x86_64"}
    for (system, machine), plat in cases.items():
        assert v2s.platform_asset(system, machine)["platform"] == plat, (system, machine)
    for system, machine in (("Linux", "aarch64"), ("Linux", "arm64"), ("Windows", "ARM64"), ("FreeBSD", "x86_64"), ("Linux", "i686"), ("", "")):
        assert v2s.platform_asset(system, machine) is None, (system, machine)


def test_two_assets_never_claim_the_same_system_and_machine():
    claims = [(a["system"], m.lower()) for a in v2s.PINS["assets"] for m in a["machines"]]
    assert len(claims) == len(set(claims))


def test_the_pinned_file_table_covers_the_skill_and_its_references_with_sha256():
    files = v2s.PINS["files"]
    assert set(files) == {"SKILL.md", "references/analysis-method.md", "references/ir-format.md", "references/verification-protocol.md"}
    assert all(HEX64.match(h) for h in files.values())
    assert files["SKILL.md"] == "34dd28200b585b7feb2bc34927b065c14ae538b746b46b54db6800d02c420a9"
    assert files["references/ir-format.md"] == "b95d273c2964d5476cbbb49f098ef3a1953056fedca11397b92707d074c5cd65"


def test_the_pin_data_ships_in_the_package_and_matches_its_schema():
    base = paths.data_dir() / "video_to_skill"
    for nome in ("pins.json", "pins.schema.json"):
        assert (base / nome).is_file(), nome
    jsonschema = pytest.importorskip("jsonschema")
    jsonschema.validate(json.loads((base / "pins.json").read_text(encoding="utf8")),
                        json.loads((base / "pins.schema.json").read_text(encoding="utf8")))


def _bad(mutate):
    doc = copy.deepcopy(v2s.PINS)
    mutate(doc)
    return doc


@pytest.mark.parametrize("mutate, quer", [
    (lambda d: d["assets"][0].__setitem__("sha256", "abc"), "sha256"),
    (lambda d: d["assets"][0].__setitem__("sha256", d["assets"][0]["sha256"].upper()), "sha256"),
    (lambda d: d["assets"][0].pop("member_sha256"), "member_sha256"),
    (lambda d: d["assets"][0].__setitem__("file", "vts-extract-other.tar.gz"), "nome"),
    (lambda d: d["assets"][3].__setitem__("format", "tar.gz"), "formato"),
    (lambda d: d["assets"][0].__setitem__("member", "../vts-extract"), "member"),
    (lambda d: d["assets"][0].__setitem__("member", "bin/vts-extract"), "member"),
    (lambda d: d["assets"][0].__setitem__("member_size", v2s.MAX_MEMBER_BYTES + 1), "tamanho"),
    (lambda d: d["assets"][1].__setitem__("machines", list(d["assets"][0]["machines"])) or d["assets"][1].__setitem__("system", "Linux"), "duas"),
    (lambda d: d.__setitem__("release_url_base", "http://github.com/brenoepics/video-to-skill/releases/download/v0.3.0/"), "https"),
    (lambda d: d.__setitem__("release_url_base", "https://example.com/v0.3.0/"), "github.com/brenoepics/video-to-skill"),
    (lambda d: d.__setitem__("commit", "c1a1b90"), "commit"),
    (lambda d: d["files"].__setitem__("SKILL.md", "zz"), "sha256"),
    (lambda d: d["assets"].pop(), "plataforma"),
])
def test_the_lint_refuses_a_malformed_table(mutate, quer):
    with pytest.raises(v2s.VideoToSkillError, match=quer):
        v2s.lint_pins(_bad(mutate))


def test_the_lint_accepts_the_shipped_table():
    v2s.lint_pins(v2s.PINS)


# ------------------------------------------------------------------------------------------------------- safe extraction

def _tar(entries, mode="w:gz") -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode=mode) as tf:
        for name, data, kind in entries:
            ti = tarfile.TarInfo(name)
            if kind == "file":
                ti.size = len(data)
                ti.mode = 0o755
                tf.addfile(ti, io.BytesIO(data))
            elif kind == "symlink":
                ti.type, ti.linkname = tarfile.SYMTYPE, data.decode()
                tf.addfile(ti)
            elif kind == "hardlink":
                ti.type, ti.linkname = tarfile.LNKTYPE, data.decode()
                tf.addfile(ti)
            elif kind == "dir":
                ti.type = tarfile.DIRTYPE
                tf.addfile(ti)
            elif kind == "fifo":
                ti.type = tarfile.FIFOTYPE
                tf.addfile(ti)
    return buf.getvalue()


def _zip(entries) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data, kind in entries:
            zi = zipfile.ZipInfo(name)
            zi.create_system = 3
            zi.external_attr = ((stat.S_IFLNK | 0o777) if kind == "symlink" else (stat.S_IFREG | 0o755)) << 16
            zf.writestr(zi, data)
    return buf.getvalue()


def _extract(tmp_path, blob, fmt, member="vts-extract", cap=1000):
    arc = tmp_path / ("a." + ("zip" if fmt == "zip" else "tar.gz"))
    arc.write_bytes(blob)
    dest = tmp_path / "out" / member
    dest.parent.mkdir(exist_ok=True)
    v2s.safe_extract(arc, fmt, member, dest, max_bytes=cap)
    return dest


@pytest.mark.parametrize("fmt, maker", [("tar.gz", _tar), ("zip", _zip)])
def test_extract_writes_only_the_one_member_with_the_owner_exec_bit(tmp_path, fmt, maker):
    dest = _extract(tmp_path, maker([("vts-extract", b"binary", "file")]), fmt)
    assert dest.read_bytes() == b"binary"
    assert [p.name for p in dest.parent.iterdir()] == ["vts-extract"]


@pytest.mark.parametrize("fmt, maker", [("tar.gz", _tar), ("zip", _zip)])
@pytest.mark.parametrize("name", ["../vts-extract", "/etc/vts-extract", "a/../vts-extract", "bin/vts-extract", "VTS-EXTRACT",
                                  "./vts-extract-x", "vts-extract-0.3.0"])
def test_extract_refuses_a_member_with_another_name_or_a_path(tmp_path, fmt, maker, name):
    with pytest.raises(v2s.VideoToSkillError):
        _extract(tmp_path, maker([(name, b"x", "file")]), fmt)
    assert not (tmp_path / "out" / "vts-extract").exists() and not (tmp_path / "vts-extract").exists()


@pytest.mark.parametrize("fmt, maker", [("tar.gz", _tar), ("zip", _zip)])
def test_extract_refuses_an_archive_with_anything_besides_the_one_member(tmp_path, fmt, maker):
    with pytest.raises(v2s.VideoToSkillError, match="só"):
        _extract(tmp_path, maker([("vts-extract", b"x", "file"), ("other", b"y", "file")]), fmt)
    with pytest.raises(v2s.VideoToSkillError):
        _extract(tmp_path, maker([]), fmt)
    assert not (tmp_path / "out" / "vts-extract").exists()


def test_extract_refuses_links_devices_and_directories_in_a_tar(tmp_path):
    for kind, data in (("symlink", b"/etc/passwd"), ("hardlink", b"x"), ("dir", b""), ("fifo", b"")):
        with pytest.raises(v2s.VideoToSkillError):
            _extract(tmp_path, _tar([("vts-extract", data, kind)]), "tar.gz")
        assert not (tmp_path / "out" / "vts-extract").exists(), kind


def test_extract_refuses_a_symlink_member_in_a_zip(tmp_path):
    with pytest.raises(v2s.VideoToSkillError, match="link"):
        _extract(tmp_path, _zip([("vts-extract", b"/etc/passwd", "symlink")]), "zip")
    assert not (tmp_path / "out" / "vts-extract").exists()


@pytest.mark.parametrize("fmt, maker", [("tar.gz", _tar), ("zip", _zip)])
def test_extract_refuses_a_member_over_the_size_cap_and_writes_nothing(tmp_path, fmt, maker):
    with pytest.raises(v2s.VideoToSkillError, match="tamanho"):
        _extract(tmp_path, maker([("vts-extract", b"x" * 1001, "file")]), fmt, cap=1000)
    assert not (tmp_path / "out" / "vts-extract").exists()
    assert _extract(tmp_path, maker([("vts-extract", b"x" * 1000, "file")]), fmt, cap=1000).stat().st_size == 1000


def test_extract_caps_the_bytes_it_really_reads_not_the_size_the_header_claims(tmp_path):
    """A zip whose header lies about the size: the copy stops at the cap whatever the directory says."""
    blob = bytearray(_zip([("vts-extract", b"x" * 5000, "file")]))
    # the uncompressed size sits in the central directory and in the local header: make both claim 10 bytes
    for sig in (b"PK\x03\x04", b"PK\x01\x02"):
        i = blob.find(sig)
        off = 22 if sig == b"PK\x03\x04" else 24
        blob[i + off:i + off + 4] = (10).to_bytes(4, "little")
    arc = tmp_path / "lie.zip"
    arc.write_bytes(bytes(blob))
    dest = tmp_path / "vts-extract"
    with pytest.raises(v2s.VideoToSkillError):
        v2s.safe_extract(arc, "zip", "vts-extract", dest, max_bytes=1000)
    assert not dest.exists()


def test_extract_never_overwrites_or_follows_a_link_at_the_destination(tmp_path):
    arc = tmp_path / "a.tar.gz"
    arc.write_bytes(_tar([("vts-extract", b"x", "file")]))
    victim = tmp_path / "victim"
    victim.write_text("keep")
    dest = tmp_path / "vts-extract"
    dest.symlink_to(victim)
    with pytest.raises(v2s.VideoToSkillError):
        v2s.safe_extract(arc, "tar.gz", "vts-extract", dest, max_bytes=1000)
    assert victim.read_text() == "keep"
    plain = tmp_path / "plain"
    plain.write_text("old")
    with pytest.raises(v2s.VideoToSkillError):
        v2s.safe_extract(arc, "tar.gz", "vts-extract", plain, max_bytes=1000)
    assert plain.read_text() == "old"


def test_extract_refuses_a_file_that_is_not_an_archive(tmp_path):
    for blob, fmt in ((b"not gzip at all", "tar.gz"), (b"not a zip", "zip"), (b"", "tar.gz")):
        with pytest.raises(v2s.VideoToSkillError):
            _extract(tmp_path, blob, fmt)


def test_extract_refuses_an_unknown_format(tmp_path):
    with pytest.raises(v2s.VideoToSkillError, match="formato"):
        _extract(tmp_path, b"x", "rar")


# --------------------------------------------------------------------------------------------------------------- setup

def _release(monkeypatch, tmp_path, member=None, fmt="tar.gz", *, pin_archive=True, pin_member=True, name="vts-extract"):
    """A fake release for linux-x86_64: the archive holds `member` (the fake extractor by default), the table is rewritten to pin
    it, and `_download` serves it and records every URL. Returns the list of URLs asked."""
    if member is None:
        member = fake.make(tmp_path / "src").read_bytes()
    blob = _tar([(name, member, "file")]) if fmt == "tar.gz" else _zip([(name, member, "file")])
    table = copy.deepcopy(v2s.PINS)
    a = next(a for a in table["assets"] if a["platform"] == "linux-x86_64")
    a["format"] = fmt
    a["file"] = "vts-extract-linux-x86_64." + fmt  # (tests do not lint: a zip for linux is only a way to test the zip reader of setup)
    a["size"], a["member_size"] = len(blob), len(member)
    if pin_archive:
        a["sha256"] = hashlib.sha256(blob).hexdigest()
    if pin_member:
        a["member_sha256"] = hashlib.sha256(member).hexdigest()
    monkeypatch.setattr(v2s, "PINS", table)
    asked = []

    def download(url, max_bytes):
        asked.append((url, max_bytes))
        return blob

    monkeypatch.setattr(v2s, "_download", download)
    monkeypatch.setattr(v2s, "_offline", lambda: False)
    return asked


def _no_path_binary(monkeypatch, tmp_path):
    empty = tmp_path / "emptybin"
    empty.mkdir(exist_ok=True)
    monkeypatch.setenv("PATH", str(empty))


@posix_only
def test_setup_downloads_the_pinned_asset_verifies_it_and_installs_one_checked_executable(tmp_path, monkeypatch, capsys):
    _no_path_binary(monkeypatch, tmp_path)
    asked = _release(monkeypatch, tmp_path)
    assert cli.main(["video-to-skill", "setup"]) == 0
    assert [u for u, _ in asked] == [BASE + "vts-extract-linux-x86_64.tar.gz"]
    assert all(cap <= v2s.MAX_ARCHIVE_BYTES for _, cap in asked)
    exe = v2s.managed_binary()
    assert exe.parent == tools.tools_dir() / "video-to-skill-bin" and exe.name == "vts-extract-0.3.0"
    assert exe.is_file() and os.access(exe, os.X_OK) and not exe.is_symlink()
    assert [p.name for p in exe.parent.iterdir()] == ["vts-extract-0.3.0"], "no archive, no temp file or sidecar is left behind"
    assert fake.subcommands(exe.parent) == [] and [c["argv"] for c in fake.calls(exe.parent)] == [["--version"]]
    out = capsys.readouterr().out
    assert "0.3.0" in out and "sha256" in out and "check --fix --yes" in out and "attestation" in out.lower()


@posix_only
def test_setup_never_runs_check_fix_or_yes_and_never_touches_the_upstream_downloads(tmp_path, monkeypatch):
    _no_path_binary(monkeypatch, tmp_path)
    _release(monkeypatch, tmp_path)
    assert v2s.run_video_to_skill(["setup"]) == 0
    d = v2s.managed_binary().parent
    assert fake.markers(d) == [] and all("--fix" not in c["argv"] and "--yes" not in c["argv"] for c in fake.calls(d))


@posix_only
def test_setup_reads_the_format_the_table_names_so_a_zip_is_read_as_a_zip(tmp_path, monkeypatch):
    _no_path_binary(monkeypatch, tmp_path)
    _release(monkeypatch, tmp_path, fmt="zip")
    assert v2s.run_video_to_skill(["setup"]) == 0
    assert v2s.find_binary().source == "managed"


@posix_only
def test_setup_refuses_a_tar_served_where_the_table_says_zip(tmp_path, monkeypatch):
    _no_path_binary(monkeypatch, tmp_path)
    _release(monkeypatch, tmp_path)
    table = copy.deepcopy(v2s.PINS)
    next(a for a in table["assets"] if a["platform"] == "linux-x86_64")["format"] = "zip"
    monkeypatch.setattr(v2s, "PINS", table)
    with pytest.raises(v2s.VideoToSkillError):
        v2s.run_video_to_skill(["setup"])
    assert not v2s.managed_binary().exists()


@posix_only
def test_setup_refuses_an_archive_whose_sha256_is_not_the_pinned_one_and_writes_nothing(tmp_path, monkeypatch):
    _no_path_binary(monkeypatch, tmp_path)
    _release(monkeypatch, tmp_path)
    table = copy.deepcopy(v2s.PINS)
    next(a for a in table["assets"] if a["platform"] == "linux-x86_64")["sha256"] = "0" * 64
    monkeypatch.setattr(v2s, "PINS", table)
    with pytest.raises(v2s.VideoToSkillError, match="sha256"):
        v2s.run_video_to_skill(["setup"])
    assert not v2s.managed_binary().exists() and not (tools.tools_dir() / "video-to-skill-bin").exists()


@posix_only
def test_setup_refuses_an_extracted_file_that_is_not_the_pinned_member_and_never_runs_it(tmp_path, monkeypatch):
    _no_path_binary(monkeypatch, tmp_path)
    marker = tmp_path / "RAN"
    evil = f"#!/bin/sh\ntouch {marker}\necho vts-extract 0.3.0\n".encode()
    _release(monkeypatch, tmp_path, member=evil, pin_member=False)
    with pytest.raises(v2s.VideoToSkillError, match="sha256"):
        v2s.run_video_to_skill(["setup"])
    assert not marker.exists(), "an unverified file was executed"
    assert not v2s.managed_binary().exists()


@posix_only
def test_setup_removes_a_new_binary_whose_version_is_wrong(tmp_path, monkeypatch):
    _no_path_binary(monkeypatch, tmp_path)
    member = b"#!/bin/sh\necho vts-extract 9.9.9\n"  # the pinned member (its sha256 is in the table) says another version
    _release(monkeypatch, tmp_path, member=member)
    with pytest.raises(v2s.VideoToSkillError, match="0.3.0"):
        v2s.run_video_to_skill(["setup"])
    assert not v2s.managed_binary().exists()


@posix_only
def test_setup_uses_the_path_binary_only_when_it_reports_exactly_0_3_0_and_downloads_nothing(tmp_path, monkeypatch, capsys):
    binary_dir = tmp_path / "pathbin"
    fake.make(binary_dir)
    monkeypatch.setenv("PATH", f"{binary_dir}{os.pathsep}/usr/bin{os.pathsep}/bin")
    asked = _release(monkeypatch, tmp_path)
    assert v2s.run_video_to_skill(["setup"]) == 0
    assert asked == [] and not v2s.managed_binary().exists()
    assert str(binary_dir / "vts-extract") in capsys.readouterr().out


@posix_only
@pytest.mark.parametrize("version", ["oldversion"])
def test_setup_downloads_when_the_path_binary_is_another_version(tmp_path, monkeypatch, version):
    binary_dir = tmp_path / "pathbin"
    fake.make(binary_dir)
    fake.set_mode(binary_dir, version)
    monkeypatch.setenv("PATH", f"{binary_dir}{os.pathsep}/usr/bin{os.pathsep}/bin")
    asked = _release(monkeypatch, tmp_path)
    assert v2s.run_video_to_skill(["setup"]) == 0
    assert len(asked) == 1 and v2s.managed_binary().is_file()


@posix_only
@pytest.mark.parametrize("line", ["vts-extract 0.3.0-rc1", "vts-extract 0.3.00", "vts-extract 0.3.0 extra", "0.3.0", "vts-extract 0.3.1",
                                  "vts-extract 10.3.0", "vts-extract 0.3.0\nvts-extract 0.3.0"])
def test_a_path_binary_must_say_exactly_vts_extract_0_3_0(tmp_path, monkeypatch, line):
    d = tmp_path / "pathbin"
    d.mkdir()
    exe = d / "vts-extract"
    exe.write_text(f"#!/bin/sh\ncat <<'EOF'\n{line}\nEOF\n", encoding="utf8")
    exe.chmod(0o755)
    monkeypatch.setenv("PATH", str(d))
    assert v2s.find_binary() is None


@posix_only
def test_setup_refuses_the_offline_mode_and_downloads_nothing(tmp_path, monkeypatch):
    _no_path_binary(monkeypatch, tmp_path)
    asked = _release(monkeypatch, tmp_path)
    monkeypatch.setattr(v2s, "_offline", lambda: True)
    with pytest.raises(v2s.VideoToSkillError, match="offline"):
        v2s.run_video_to_skill(["setup"])
    assert asked == []


@pytest.mark.parametrize("system, machine", [("Linux", "aarch64"), ("Windows", "ARM64"), ("FreeBSD", "amd64")])
def test_setup_says_so_on_a_platform_without_a_prebuilt_binary(tmp_path, monkeypatch, system, machine):
    _no_path_binary(monkeypatch, tmp_path)
    asked = _release(monkeypatch, tmp_path)
    monkeypatch.setattr(v2s, "_platform", lambda: (system, machine))
    with pytest.raises(v2s.VideoToSkillError, match="plataforma|binário pré-compilado") as e:
        v2s.run_video_to_skill(["setup"])
    assert system.lower() in str(e.value).lower() and "cargo build" in str(e.value)
    assert asked == []


def test_setup_takes_no_arguments(tmp_path, monkeypatch):
    _no_path_binary(monkeypatch, tmp_path)
    asked = _release(monkeypatch, tmp_path)
    with pytest.raises(v2s.VideoToSkillError, match="argumentos"):
        v2s.run_video_to_skill(["setup", "--force"])
    assert asked == []


@posix_only
def test_setup_is_idempotent_and_keeps_the_verified_binary(tmp_path, monkeypatch):
    _no_path_binary(monkeypatch, tmp_path)
    asked = _release(monkeypatch, tmp_path)
    assert v2s.run_video_to_skill(["setup"]) == 0
    first = v2s.managed_binary().stat().st_mtime_ns
    assert v2s.run_video_to_skill(["setup"]) == 0
    assert len(asked) == 1 and v2s.managed_binary().stat().st_mtime_ns == first


@posix_only
def test_a_managed_binary_that_was_changed_on_disk_is_not_used_and_setup_replaces_it(tmp_path, monkeypatch):
    _no_path_binary(monkeypatch, tmp_path)
    asked = _release(monkeypatch, tmp_path)
    v2s.run_video_to_skill(["setup"])
    exe = v2s.managed_binary()
    exe.write_bytes(exe.read_bytes() + b"# tampered\n")
    assert v2s.find_binary() is None, "a binary whose sha256 is not the pinned one must not run"
    assert v2s.run_video_to_skill(["setup"]) == 0
    assert len(asked) == 2 and v2s.find_binary().source == "managed"


@posix_only
def test_a_managed_binary_that_is_a_symlink_is_not_used(tmp_path, monkeypatch):
    _no_path_binary(monkeypatch, tmp_path)
    _release(monkeypatch, tmp_path)
    real = fake.make(tmp_path / "elsewhere")
    exe = v2s.managed_binary()
    exe.parent.mkdir(parents=True)
    exe.symlink_to(real)
    assert v2s.find_binary() is None


@posix_only
def test_the_download_is_capped_and_the_url_comes_from_the_table_only(tmp_path, monkeypatch):
    _no_path_binary(monkeypatch, tmp_path)
    asked = _release(monkeypatch, tmp_path)
    v2s.run_video_to_skill(["setup"])
    url, cap = asked[0]
    assert url.startswith("https://github.com/brenoepics/video-to-skill/releases/download/v0.3.0/") and "?" not in url
    assert cap == v2s.MAX_ARCHIVE_BYTES == 32 * 1024 * 1024


def test_the_real_download_function_refuses_a_redirect_off_github_and_a_body_over_the_cap(monkeypatch):
    """_download with a fake opener: a final URL outside github.com/githubusercontent is refused; the body is read up to the cap + 1."""
    class Resp(io.BytesIO):
        def __init__(self, body, url):
            super().__init__(body)
            self._url = url
            self.headers = {}

        def geturl(self):
            return self._url

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def opener(final):
        def open_(req, timeout=None):
            return Resp(b"x" * 100, final)
        return open_

    monkeypatch.setattr(v2s, "_urlopen", opener("https://evil.example.com/vts.tar.gz"))
    with pytest.raises(v2s.VideoToSkillError, match="host"):
        v2s._download(BASE + "vts-extract-linux-x86_64.tar.gz", 1000)
    monkeypatch.setattr(v2s, "_urlopen", opener("https://release-assets.githubusercontent.com/x"))
    assert v2s._download(BASE + "vts-extract-linux-x86_64.tar.gz", 1000) == b"x" * 100
    with pytest.raises(v2s.VideoToSkillError, match="tamanho"):
        v2s._download(BASE + "vts-extract-linux-x86_64.tar.gz", 99)
    with pytest.raises(v2s.VideoToSkillError, match="URL"):
        v2s._download("http://github.com/brenoepics/video-to-skill/releases/download/v0.3.0/x", 1000)
    with pytest.raises(v2s.VideoToSkillError, match="URL"):
        v2s._download("https://example.com/vts-extract-linux-x86_64.tar.gz", 1000)


def test_the_module_does_not_import_the_network_stack_at_import_time():
    src = Path(v2s.__file__).read_text(encoding="utf8")
    top = src.split("\ndef ", 1)[0]
    assert "import urllib.request" not in top and "import http" not in top and "import requests" not in top
    assert "preexec_fn" not in src.replace("# no preexec_fn", "")
    assert "shell=True" not in src and "os.system" not in src
