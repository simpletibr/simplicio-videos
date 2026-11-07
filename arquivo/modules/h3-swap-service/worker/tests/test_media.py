from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from typing import Any

import pytest

from worker import media
from worker.media import MediaError, probe

VIDEO: dict[str, Any] = {
    "index": 0,
    "codec_type": "video",
    "width": 768,
    "height": 1382,
    "avg_frame_rate": "24/1",
    "r_frame_rate": "24/1",
}
AUDIO: dict[str, Any] = {"index": 1, "codec_type": "audio", "channels": 2}


def _completed(stdout: str, returncode: int = 0, stderr: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=["ffprobe"], returncode=returncode, stdout=stdout, stderr=stderr)


def _probe_json(streams: list[dict[str, Any]], fmt: dict[str, Any]) -> str:
    return json.dumps({"streams": streams, "format": fmt})


@pytest.fixture
def run_ffprobe(monkeypatch: pytest.MonkeyPatch) -> Callable[[Any], list[tuple[list[str], dict[str, Any]]]]:
    calls: list[tuple[list[str], dict[str, Any]]] = []

    def install(result: Any) -> list[tuple[list[str], dict[str, Any]]]:
        def fake_run(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
            calls.append((args, kwargs))
            if isinstance(result, BaseException):
                raise result
            return result

        monkeypatch.setattr(media.subprocess, "run", fake_run)
        return calls

    return install


def test_probe_reads_video_and_audio_facts(run_ffprobe: Any) -> None:
    run_ffprobe(_completed(_probe_json([VIDEO, AUDIO], {"duration": "10.041667"})))
    info = probe("/work/a.mp4")
    assert info == {
        "duration_s": pytest.approx(10.041667),
        "width": 768,
        "height": 1382,
        "fps": 24.0,
        "has_audio": True,
    }


def test_probe_reports_no_audio_when_no_audio_stream(run_ffprobe: Any) -> None:
    run_ffprobe(_completed(_probe_json([VIDEO], {"duration": "3.0"})))
    assert probe("/work/a.mp4")["has_audio"] is False


def test_probe_parses_ntsc_fraction_frame_rate(run_ffprobe: Any) -> None:
    video = {**VIDEO, "avg_frame_rate": "30000/1001"}
    run_ffprobe(_completed(_probe_json([video], {"duration": "2.0"})))
    assert probe("/work/a.mp4")["fps"] == pytest.approx(29.97, abs=0.01)


def test_probe_falls_back_to_r_frame_rate_when_average_is_zero(run_ffprobe: Any) -> None:
    video = {**VIDEO, "avg_frame_rate": "0/0", "r_frame_rate": "25/1"}
    run_ffprobe(_completed(_probe_json([video], {"duration": "2.0"})))
    assert probe("/work/a.mp4")["fps"] == 25.0


def test_probe_uses_stream_duration_when_format_has_none(run_ffprobe: Any) -> None:
    video = {**VIDEO, "duration": "5.0"}
    run_ffprobe(_completed(_probe_json([video], {})))
    assert probe("/work/a.mp4")["duration_s"] == 5.0


def test_probe_invokes_ffprobe_with_contract_arguments(run_ffprobe: Any) -> None:
    calls = run_ffprobe(_completed(_probe_json([VIDEO], {"duration": "1.0"})))
    probe("/work/a.mp4")
    args, kwargs = calls[0]
    assert args == [
        "ffprobe",
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_streams",
        "-show_format",
        "/work/a.mp4",
    ]
    assert kwargs["capture_output"] is True


def test_probe_nonzero_exit_raises_media_error(run_ffprobe: Any) -> None:
    run_ffprobe(_completed("", returncode=1, stderr="Invalid data found when processing input"))
    with pytest.raises(MediaError, match="Invalid data"):
        probe("/work/a.mp4")


def test_probe_missing_binary_raises_media_error(run_ffprobe: Any) -> None:
    run_ffprobe(FileNotFoundError("ffprobe"))
    with pytest.raises(MediaError):
        probe("/work/a.mp4")


def test_probe_timeout_raises_media_error(run_ffprobe: Any) -> None:
    run_ffprobe(subprocess.TimeoutExpired(cmd="ffprobe", timeout=60))
    with pytest.raises(MediaError):
        probe("/work/a.mp4")


def test_probe_invalid_json_raises_media_error(run_ffprobe: Any) -> None:
    run_ffprobe(_completed("not json"))
    with pytest.raises(MediaError):
        probe("/work/a.mp4")


def test_probe_without_video_stream_raises_media_error(run_ffprobe: Any) -> None:
    run_ffprobe(_completed(_probe_json([AUDIO], {"duration": "4.0"})))
    with pytest.raises(MediaError):
        probe("/work/a.mp4")


def test_probe_without_any_duration_raises_media_error(run_ffprobe: Any) -> None:
    run_ffprobe(_completed(_probe_json([VIDEO], {})))
    with pytest.raises(MediaError):
        probe("/work/a.mp4")
