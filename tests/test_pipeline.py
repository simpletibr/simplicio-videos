"""`run` = voice -> validate --need-lock -> render -> publish (render mocked; publish stays dry-run without --publish)."""
from simplicio_video import cli, pipeline


def test_run_all_chains_steps_and_dry_runs_publish(mini, monkeypatch):
    seen = {}

    def fake_render(c, backend, **k):
        seen["backend"] = backend
        mp4 = c.rel(c.data["saida"]["arquivo"])
        mp4.parent.mkdir(parents=True, exist_ok=True)
        mp4.write_bytes(b"mp4")
        return {"backend": backend, "output": {"path": "out/mini.mp4"}, "loudness": {"integrated_lufs": -14.0}}

    monkeypatch.setattr(cli, "do_render", fake_render)
    res = pipeline.run_all(mini, backend="kaggle", log=lambda *_: None)
    assert seen["backend"] == "kaggle"
    assert res["voice"]["provider"] == "file" and "vo1" in res["voice"]["lines"]
    assert res["publish"]["dry_run"] is True and res["publish"]["dest"].endswith("/Teste - mini - v01.mp4")
    assert (mini.parent / "timing.lock.json").is_file()
