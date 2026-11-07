"""Small edits and fakes on the files of a project under test."""

from pathlib import Path

import yaml


def edit_yaml(path, fn, *, encoding=None) -> None:
    """Load the YAML at `path`, let `fn` change the document in place, write it back (keys keep their order, accents stay).

    `encoding=None` is the platform default (what `Path.read_text()` did in the copies that never named one); the openverse and
    saida_json tests pass "utf8"."""
    p = Path(path)
    d = yaml.safe_load(p.read_text(encoding=encoding))
    fn(d)
    p.write_text(yaml.safe_dump(d, allow_unicode=True, sort_keys=False), encoding=encoding)


def fake_mp4(contrato, conteudo: bytes) -> Path:
    """`out/mini.mp4` next to the contract, holding `conteudo` (not a video: the tests that need one render it)."""
    p = Path(contrato).parent / "out" / "mini.mp4"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(conteudo)
    return p
