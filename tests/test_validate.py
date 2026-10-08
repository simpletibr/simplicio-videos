import json

import yaml

from conftest import LOTHUS, WJR
from simplicio_video import contract as ct


def _edit(path, fn):
    d = yaml.safe_load(path.read_text())
    fn(d)
    path.write_text(yaml.safe_dump(d, allow_unicode=True, sort_keys=False))


def test_real_contracts_are_valid_with_lock():
    for p in (WJR, LOTHUS):
        rep = ct.validate(ct.load(p), need_lock=True)
        assert rep.ok, rep.errors


def test_scene_timeline_and_absolute_times():
    c = ct.load(WJR)
    assert c.cuts() == [0, 1.5, 4, 6.75, 8.5, 10.25, 12.5, 14.5, 16.5, 20]
    lines = {l["id"]: l["t"] for l in c.lines()}
    assert lines["vo4"] == 6.8 and lines["vo9"] == 16.6
    assert any(q["id"] == "whoosh-cut1" and q["t"] == 1.388 for q in c.cues())


def test_duration_sum_must_match(mini):
    _edit(mini, lambda d: d["cenas"][1].update(duracao_s=0.75))
    rep = ct.validate(ct.load(mini))
    assert any(e.startswith("durations:") for e in rep.errors)


def test_line_must_fit_scene(mini):
    _edit(mini, lambda d: d["cenas"][0]["fala"].update(inicio_s=0.3, max_s=0.4))
    rep = ct.validate(ct.load(mini))
    assert any("past scene a end" in e for e in rep.errors), rep.errors


def test_missing_asset(mini):
    _edit(mini, lambda d: d.update(assets=[{"arquivo": "nao-existe.png", "destino": "assets/x.png"}]))
    assert any(e.startswith("assets: missing") for e in ct.validate(ct.load(mini)).errors)


def test_todo_blocks_validation(mini):
    _edit(mini, lambda d: d["cenas"][0]["fala"].update(texto="TODO: fala"))
    assert any(e.startswith("todo:") for e in ct.validate(ct.load(mini)).errors)


def test_drive_block_is_rejected(mini):
    _edit(mini, lambda d: d.update(drive={"caminho": "simplicio-video/clientes/Teste_Mini/2026/Teste_Hash", "arquivo": "Teste - mini - v01.mp4"}))
    assert any(e.startswith("drive:") for e in ct.validate(ct.load(mini)).errors)


def test_lock_longer_than_slot_is_error(mini):
    from simplicio_video import voice
    voice.run(ct.load(mini), log=lambda *_: None)
    lock_p = mini.parent / "timing.lock.json"
    lock = json.loads(lock_p.read_text())
    lock["lines"]["vo1"]["dur_s"] = 0.9  # pretend the take got longer than max_s 0.4
    lock_p.write_text(json.dumps(lock))
    assert any("no time-stretch" in e for e in ct.validate(ct.load(mini)).errors)


def test_need_lock(mini):
    assert any("timing.lock.json missing" in e for e in ct.validate(ct.load(mini), need_lock=True).errors)


def test_init_skeleton_blocks_until_filled(tmp_path):
    from conftest import run_cli
    out = tmp_path / "c" / "contract.yaml"
    r = run_cli("init", "clinica-teste", "Dia_Criancas", "--template", "saude-odontologia", "--nome", "Clínica Teste", "--ano", "2026", "--out", out)
    assert r.returncode == 0, r.stderr
    d = yaml.safe_load(out.read_text())
    assert d["cliente"]["drive_nome"] == "Clinica_Teste" and "drive" not in d
    rep = ct.validate(ct.load(out))
    assert not ct.schema_errors(d)
    assert any(e.startswith("todo:") for e in rep.errors)
