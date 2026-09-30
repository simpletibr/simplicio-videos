"""--backend kaggle / colab-cli with the external CLIs mocked (no account, no network, no GPU)."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from simplicio_video import contract as ct
from simplicio_video import remote

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="needs ffmpeg")


@pytest.fixture(scope="module")
def tiny_mp4(tmp_path_factory):
    p = tmp_path_factory.mktemp("mp4") / "final.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc=size=180x320:rate=30:duration=1", "-f", "lavfi",
                    "-i", "sine=frequency=440:duration=1", "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
                    str(p)], check=True)
    return p


@pytest.fixture
def fake_bundle(mini, monkeypatch):
    c = ct.load(mini)
    z = mini.parent / "out" / "mini.colab-bundle.zip"
    z.parent.mkdir(parents=True, exist_ok=True)
    z.write_bytes(b"PK\x05\x06" + b"\0" * 18)
    b = {"bundle": str(z), "inputs_sha256": "ab" * 32, "quality": "draft", "tools": {"hyperframes": "hyperframes@0.8.97"},
         "files": {"index.html": "00"}, "compile_build_s": 0.1}
    monkeypatch.setattr(remote, "build_bundle", lambda *a, **k: b)
    return c


def _cp(rc=0, out=""):
    return subprocess.CompletedProcess([], rc, out, "")


def test_kaggle_metadata_gpu_and_internet():
    m = remote.kaggle_metadata("wes", "sv-render-x", "sv-bundle-x", "NvidiaTeslaT4")
    assert m["id"] == "wes/sv-render-x" and m["title"] == "sv-render-x" and m["kernel_type"] == "script"
    assert m["enable_gpu"] is True and m["machine_shape"] == "NvidiaTeslaT4" and m["enable_internet"] is True
    assert m["dataset_sources"] == ["wes/sv-bundle-x"] and m["is_private"] is True
    cpu = remote.kaggle_metadata("wes", "k", "d", None)
    assert cpu["enable_gpu"] is False and "machine_shape" not in cpu


def test_kaggle_backend_push_poll_download(fake_bundle, tiny_mp4, monkeypatch):
    monkeypatch.setenv("SIMPLICIO_KAGGLE_BIN", "kaggle")
    monkeypatch.setenv("KAGGLE_USERNAME", "wes")
    calls, state = [], {"kstatus": 0, "dstatus": 0}

    def run(cmd):
        calls.append(cmd)
        sub = cmd[1:3]
        if sub == ["datasets", "status"]:
            state["dstatus"] += 1
            return _cp(1, "404") if state["dstatus"] == 1 else _cp(0, "ready")
        if sub == ["datasets", "create"]:
            d = Path(cmd[cmd.index("-p") + 1])
            meta = json.loads((d / "dataset-metadata.json").read_text())
            assert meta["id"] == "wes/sv-bundle-abababababab" and (d / "mini.colab-bundle.zip").is_file()
            return _cp()
        if sub == ["kernels", "status"]:
            state["kstatus"] += 1
            return [_cp(1, "not found"), _cp(0, 'wes/sv-render-abababababab has status "KernelWorkerStatus.RUNNING"'),
                    _cp(0, 'wes/sv-render-abababababab has status "KernelWorkerStatus.COMPLETE"')][state["kstatus"] - 1]
        if sub == ["kernels", "push"]:
            d = Path(cmd[cmd.index("-p") + 1])
            meta = json.loads((d / "kernel-metadata.json").read_text())
            assert meta["machine_shape"] == "NvidiaTeslaT4" and meta["enable_internet"] and (d / "sv_render.py").is_file()
            assert "--accelerator" in cmd
            return _cp()
        if sub == ["kernels", "output"]:
            d = Path(cmd[cmd.index("-p") + 1])
            shutil.copyfile(tiny_mp4, d / "final.mp4")
            (d / "timings.json").write_text(json.dumps({"gpu": "Tesla T4", "timings_s": {"total_s": 99.0, "gpu_encode": True}}))
            return _cp()
        raise AssertionError(cmd)

    out = fake_bundle.dir / "out" / "k.mp4"
    m = remote.render_kaggle(fake_bundle, out=out, run=run, sleep=lambda s: None, log=lambda *_: None)
    order = [" ".join(c[1:3]) for c in calls]
    assert order.index("datasets create") < order.index("kernels push") < order.index("kernels output")
    assert out.is_file() and m["backend"] == "kaggle" and m["gpu_encode"] is True
    assert m["usage"]["accelerator"] == "NvidiaTeslaT4" and m["usage"]["gpu"] == "Tesla T4" and m["usage"]["cache_hit"] is False
    assert json.loads((fake_bundle.dir / "render.manifest.json").read_text())["output"]["frames"] == 30


def test_kaggle_reuses_completed_kernel(fake_bundle, tiny_mp4, monkeypatch):
    monkeypatch.setenv("SIMPLICIO_KAGGLE_BIN", "kaggle")
    monkeypatch.setenv("KAGGLE_USERNAME", "wes")
    seen = []

    def run(cmd):
        seen.append(cmd[1:3])
        if cmd[1:3] == ["datasets", "status"]:
            return _cp(0, "ready")
        if cmd[1:3] == ["kernels", "status"]:
            return _cp(0, 'has status "KernelWorkerStatus.COMPLETE"')
        if cmd[1:3] == ["kernels", "output"]:
            shutil.copyfile(tiny_mp4, Path(cmd[cmd.index("-p") + 1]) / "final.mp4")
            return _cp()
        raise AssertionError(cmd)

    m = remote.render_kaggle(fake_bundle, run=run, sleep=lambda s: None, log=lambda *_: None)
    assert ["kernels", "push"] not in seen and ["datasets", "create"] not in seen and m["usage"]["cache_hit"] is True


def test_kaggle_failure_shows_log(fake_bundle, monkeypatch):
    monkeypatch.setenv("SIMPLICIO_KAGGLE_BIN", "kaggle")
    monkeypatch.setenv("KAGGLE_USERNAME", "wes")
    n = {"k": 0}

    def run(cmd):
        if cmd[1:3] == ["datasets", "status"]:
            return _cp(0, "ready")
        if cmd[1:3] == ["kernels", "status"]:
            n["k"] += 1
            return _cp(1) if n["k"] == 1 else _cp(0, 'has status "KernelWorkerStatus.ERROR"')
        if cmd[1:3] == ["kernels", "logs"]:
            return _cp(0, "SV_ERROR chrome missing libs")
        return _cp()

    with pytest.raises(SystemExit, match="chrome missing libs"):
        remote.render_kaggle(fake_bundle, run=run, sleep=lambda s: None, log=lambda *_: None)


def test_kaggle_needs_username(monkeypatch, tmp_path):
    monkeypatch.delenv("KAGGLE_USERNAME", raising=False)
    monkeypatch.setenv("KAGGLE_CONFIG_DIR", str(tmp_path))
    with pytest.raises(SystemExit, match="KAGGLE_USERNAME"):
        remote.kaggle_username()


def test_colab_cli_backend(fake_bundle, tiny_mp4, monkeypatch):
    monkeypatch.setenv("SIMPLICIO_COLAB_BIN", "colab")
    calls = []

    def run(cmd):
        calls.append(cmd)
        if cmd[1] == "exec":
            assert "--timeout" in cmd and "SV_BUNDLE=/content/sv/bundle.zip" in cmd and cmd[cmd.index("-f") + 1].endswith("remote_render.py")
            return _cp(0, 'SV_RESULT {"gpu": "Tesla T4", "timings_s": {"total_s": 80, "gpu_encode": true}}')
        if cmd[1] == "download":
            shutil.copyfile(tiny_mp4, cmd[-1])
        return _cp()

    m = remote.render_colab_cli(fake_bundle, run=run, log=lambda *_: None)
    assert [c[1] for c in calls] == ["new", "upload", "exec", "download", "stop"]
    assert calls[0][-2:] == ["--gpu", "T4"] and m["backend"] == "colab-cli" and m["usage"]["gpu"] == "Tesla T4"


def test_colab_cli_always_stops(fake_bundle, monkeypatch):
    monkeypatch.setenv("SIMPLICIO_COLAB_BIN", "colab")
    calls = []

    def run(cmd):
        calls.append(cmd[1])
        return _cp(0, "SV_ERROR boom") if cmd[1] == "exec" else _cp()

    with pytest.raises(SystemExit, match="boom"):
        remote.render_colab_cli(fake_bundle, run=run, log=lambda *_: None)
    assert calls[-1] == "stop"
