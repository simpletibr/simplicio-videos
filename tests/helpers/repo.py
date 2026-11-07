"""Where things are in the repository, and the real client contracts (clients/ is not tracked by git)."""

import shutil
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]  # tests/helpers/repo.py -> the repository root
SRC = ROOT / "src" / "simplicio_video"
SCRIPTS = ROOT / "scripts"
FIXTURE = ROOT / "tests" / "fixtures" / "mini"
WJR = ROOT / "clients" / "wjr-informatica-games" / "video-01" / "contract.yaml"
LOTHUS = ROOT / "clients" / "lothus-odontologia" / "video-01-dia-das-criancas" / "contract.yaml"
CLIENT_DATA_REASON = "contrato real de cliente fora do git (clients/ não é rastreado)"


def needs_client(*paths: Path):
    """skipif marker for a test that only makes sense with the real client contract(s): clients/ is not tracked by git."""
    return pytest.mark.skipif(not all(p.exists() for p in paths), reason=CLIENT_DATA_REASON)


def contract_with_coleta_placeholders(contract: Path, dest: Path) -> Path:
    """A copy of a client contract in `dest` whose assets under `coleta/` exist as placeholders.

    `clients/*/coleta/` is gitignored (client data never goes to git), so a clean checkout has none of those files."""
    copia = dest / "a" / "video"
    shutil.copytree(contract.parent, copia, ignore=shutil.ignore_patterns("preview", "node_modules"))
    d = yaml.safe_load(contract.read_text(encoding="utf8"))
    refs = [a["arquivo"] for a in d.get("assets") or []] + [s["file"] for s in d.get("placas_video") or []]
    if (d.get("marca") or {}).get("logo"):
        refs.append(d["marca"]["logo"]["arquivo"])
    for ref in refs:
        alvo = (copia / ref).resolve()
        assert (dest / "a") in alvo.parents, ref  # the copy never writes outside the temporary folder
        if not alvo.exists():
            alvo.parent.mkdir(parents=True, exist_ok=True)
            alvo.write_bytes(b"\x89PNG\r\n\x1a\n" + ref.encode())
    return copia / contract.name
