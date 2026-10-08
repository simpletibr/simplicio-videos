"""`run` = voice -> validate --need-lock -> render, e para no MP4 (render mocked; o upload não é do motor)."""
from simplicio_video import cli, pipeline


def test_run_all_chains_steps_and_stops_at_render(mini, monkeypatch):
    seen = {}

    def fake_render(c, backend, **k):
        seen["backend"] = backend
        mp4 = c.rel(c.data["saida"]["arquivo"])
        mp4.parent.mkdir(parents=True, exist_ok=True)
        mp4.write_bytes(b"mp4")
        return {"backend": backend, "output": {"path": "out/mini.mp4"}, "loudness": {"integrated_lufs": -14.0}}

    monkeypatch.setattr(cli, "do_render", fake_render)
    logs = []
    res = pipeline.run_all(mini, backend="kaggle", log=lambda *m: logs.append(" ".join(map(str, m))))
    assert seen["backend"] == "kaggle"
    assert res["voice"]["provider"] == "file" and "vo1" in res["voice"]["lines"]
    assert "publish" not in res and res["render"]["output"] == "out/mini.mp4"
    assert any("ferramenta de operação" in m for m in logs)
    assert (mini.parent / "timing.lock.json").is_file()
