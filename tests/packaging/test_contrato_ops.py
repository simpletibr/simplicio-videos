"""The JSON contracts of the operations commands: four packaged schemas, and every `--json` output validates against them.

Schemas live in src/simplicio_video/data/schemas/cli/ (Draft 2020-12, like the five that already exist):
  doctor.schema.json         simplicio.doctor/v1        (the loop's id)
  update-check.schema.json   the state file `update-check.json` (installed, latest, update_available, kind, checked_at)
  install-plan.schema.json   simplicio.video-install-plan/v1 (the loop's `simplicio.loop-install-plan/v1` with the same keys: the
                             result of `install` that copies the skills into the host; a verify, an uninstall and an error too)
  install-ownership.schema.json  simplicio.video-install-ownership/v1 (the receipt `.simplicio-video/install-ownership.json`)
Everything is FAKE: the Runtime. HOME and PATH are sealed (see _caixa.py).
"""
from __future__ import annotations

import json

import pytest
from jsonschema import Draft202012Validator

import _caixa
from _caixa import distribution, update_cmd
from _comum import ROOT, executa
from simplicio_video.cli import main

# fixtures: assigned (not imported) so pytest finds them and ruff sees no shadowing by the test parameters
caixa = _caixa.caixa
saude = _caixa.saude
simula_so = _caixa.simula_so

SCHEMAS = ROOT / "src" / "simplicio_video" / "data" / "schemas" / "cli"
IDS_DO_LOOP = {"doctor": "simplicio.doctor/v1"}
NOVOS = ["doctor", "update-check", "install-plan", "install-ownership"]
def schema(nome: str) -> dict:
    return json.loads((SCHEMAS / f"{nome}.schema.json").read_text(encoding="utf8"))


def erros(nome: str, dados) -> list[str]:
    return [e.message for e in Draft202012Validator(schema(nome)).iter_errors(dados)]


def valida(nome: str, dados) -> None:
    assert erros(nome, dados) == [], f"{nome}: {json.dumps(dados, ensure_ascii=False)[:300]}"


# --- the files -------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("nome", NOVOS)
def test_o_schema_existe_e_e_draft_2020_12_valido(nome):
    dados = schema(nome)
    Draft202012Validator.check_schema(dados)
    assert dados["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert dados["type"] == "object" and dados.get("description"), "every schema describes itself"


@pytest.mark.parametrize("nome,ident", sorted(IDS_DO_LOOP.items()))
def test_o_id_e_o_mesmo_do_loop(nome, ident):
    assert schema(nome)["$id"] == ident
    assert schema(nome)["properties"]["schema"] == {"const": ident}


@pytest.mark.parametrize("nome", NOVOS)
def test_nenhum_schema_aceita_chave_desconhecida(nome):
    assert schema(nome)["additionalProperties"] is False


# --- a token can never be in these documents --------------------------------------------------------------------------


@pytest.mark.parametrize("chave", ["access_token", "refresh_token", "id_token", "token"])
def test_o_schema_do_doctor_proibe_chave_de_token_em_qualquer_lugar(chave):
    base = {"schema": "simplicio.doctor/v1", "status": "ok", "version": "1", "checks": []}
    valida("doctor", base)
    assert erros("doctor", {**base, chave: "fake-token-XYZ"}), f"doctor accepted a `{chave}` key"


# --- documents that must be refused ----------------------------------------------------------------------------------


def test_o_doctor_antigo_nao_e_mais_valido():
    antigo = {"ok": True, "checks": [{"name": "python", "status": "ok", "detail": "Python 3.12", "fix": None}]}
    assert erros("doctor", antigo)


def test_o_doctor_exige_detail_objeto_e_status_conhecido():
    base = {"schema": "simplicio.doctor/v1", "status": "ok", "version": "0.4.0",
            "checks": [{"name": "python", "status": "ok", "summary": "Python 3.12", "fix": None, "detail": {}}]}
    valida("doctor", base)
    base["checks"][0]["detail"] = "texto"
    assert erros("doctor", base)
    base["checks"][0]["detail"] = {}
    base["checks"][0]["status"] = "aviso"
    assert erros("doctor", base)
    base["checks"][0]["status"] = "ok"
    base["status"] = "mal"
    assert erros("doctor", base)


def test_o_estado_so_aceita_commits_behind_no_source():
    base = {"installed": "0.4.0", "latest": "0.5.0", "update_available": True, "kind": "pip", "checked_at": 1}
    valida("update-check", base)
    assert erros("update-check", {**base, "commits_behind": 2}), "commits_behind only exists for kind=source"
    valida("update-check", {**base, "kind": "source", "commits_behind": 2})
    assert erros("update-check", {**base, "kind": "binary"}), "there is no binary distribution"


# What `apply_plan` of simplicio-loop (2034e2d, install/planner.py:189-197) and the `install` command (cli_commands/install.py:160-165)
# put in the document: the video's has these keys and no others (plus the verify, uninstall and error shapes).
CHAVES_DO_INSTALL_DO_LOOP = {"schema", "status", "written", "up_to_date", "changes", "owned", "ownership", "digest", "host",
                             "version", "resynced", "pruned_project"}
DIGEST = "sha256:" + "a" * 64
RECIBO = {"schema": "simplicio.video-install-ownership/v1", "owner": "simplicio-video", "version": "0.4.0", "digest": DIGEST,
          "paths": [".claude/skills/simplicio-video/SKILL.md"], "dirs": [".claude"],
          "sha256": {".claude/skills/simplicio-video/SKILL.md": "b" * 64}}
PLANO = {"schema": "simplicio.video-install-plan/v1", "status": "applied", "written": 3, "up_to_date": False, "host": "claude",
         "version": "0.4.0", "digest": DIGEST, "owned": [".claude/skills/simplicio-video/SKILL.md"], "ownership": RECIBO,
         "changes": {"created": ["a"], "updated": [], "unchanged": 0, "left_alone": []}, "resynced": None}


def test_os_ids_do_install_e_do_recibo_e_o_estado():
    assert schema("install-plan")["$id"] == "simplicio.video-install-plan/v1"
    assert schema("install-plan")["properties"]["schema"] == {"const": "simplicio.video-install-plan/v1"}
    assert schema("install-ownership")["$id"] == "simplicio.video-install-ownership/v1"
    assert schema("install-ownership")["properties"]["schema"] == {"const": "simplicio.video-install-ownership/v1"}
    assert "$id" not in schema("update-check"), "a state file without a `schema` key has no $id (the loop's has none either)"


def test_o_schema_do_install_antigo_do_venv_saiu():
    assert not (SCHEMAS / "install-result.schema.json").exists(), "the .venv install and its schema are gone (no compatibility)"


def test_as_chaves_do_install_sao_as_do_loop_e_so_elas():
    props = set(schema("install-plan")["properties"])
    assert CHAVES_DO_INSTALL_DO_LOOP <= props
    assert props - CHAVES_DO_INSTALL_DO_LOOP == {"ok", "problems", "removed", "removed_dirs", "kept", "skipped", "left_alone", "warnings",
                                                 "error"}, "only the verify, uninstall and error shapes (and the warnings) add keys"
    mudancas = schema("install-plan")["properties"]["changes"]
    assert set(mudancas["properties"]) == {"created", "updated", "unchanged", "left_alone"} and mudancas["additionalProperties"] is False


def test_o_resultado_do_install_aceita_applied_e_dry_run_e_exige_as_chaves():
    valida("install-plan", PLANO)
    valida("install-plan", {**PLANO, "warnings": ["o recibo anterior foi ignorado"]})
    assert erros("install-plan", {**PLANO, "warnings": "x"})
    valida("install-plan", {**PLANO, "status": "dry_run", "written": 0})
    valida("install-plan", {**PLANO, "resynced": {"skills": ["codex"], "rules": [], "skills_counts": {"codex": 1},
                                                  "rules_counts": {}, "errors": [], "pending": 1},
                            "pruned_project": {"schema": "simplicio.video-install-plan/v1", "status": "removed", "removed": [],
                                               "removed_dirs": [], "kept": [], "left_alone": ["a"], "warnings": ["a foi editado"]}})
    for chave in ("changes", "owned", "ownership", "digest", "host", "version", "up_to_date", "written", "resynced"):
        assert erros("install-plan", {k: v for k, v in PLANO.items() if k != chave}), f"{chave} is required in an install result"
    assert erros("install-plan", {**PLANO, "digest": "sha1:abc"}) and erros("install-plan", {**PLANO, "written": -1})
    assert erros("install-plan", {**PLANO, "changes": {**PLANO["changes"], "unchanged": "0"}})
    assert erros("install-plan", {**PLANO, "extra": 1}), "no unknown key"


def test_o_verify_o_uninstall_e_o_erro_tem_cada_um_a_sua_forma():
    verify = {"schema": "simplicio.video-install-plan/v1", "status": "verified", "ok": True, "host": "claude",
              "version": "0.4.0", "digest": DIGEST, "problems": []}
    valida("install-plan", verify)
    assert erros("install-plan", {k: v for k, v in verify.items() if k != "digest"})
    assert erros("install-plan", {k: v for k, v in verify.items() if k != "problems"}), "the list of what differs is always there"
    assert erros("install-plan", {**verify, "ok": False}), "`verified` and ok=false cannot both be"
    falhou = {**verify, "status": "failed", "ok": False,
              "problems": [{"path": ".claude/skills/simplicio-video/SKILL.md", "problem": "modified", "detail": "diferente do recibo"}]}
    valida("install-plan", falhou)
    assert erros("install-plan", {**falhou, "ok": True}), "`failed` and ok=true cannot both be"
    assert erros("install-plan", {**falhou, "problems": []}), "`failed` lists what differs"
    assert erros("install-plan", {**falhou, "problems": [{"path": "a", "problem": "inventado", "detail": "x"}]}), "problem codes are a closed set"
    for codigo in ("no_receipt", "bad_receipt", "missing", "modified", "outdated", "foreign", "not_a_file"):
        valida("install-plan", {**falhou, "problems": [{"path": "a", "problem": codigo, "detail": "x"}]})
    uninstall = {"schema": "simplicio.video-install-plan/v1", "status": "removed", "removed": ["a"], "removed_dirs": [],
                 "kept": [], "skipped": [], "left_alone": [], "warnings": [], "host": "claude", "version": "0.4.0"}
    valida("install-plan", uninstall)
    valida("install-plan", {**uninstall, "status": "dry_run", "left_alone": ["AGENTS.md"], "warnings": ["AGENTS.md foi editado"]})
    assert erros("install-plan", {k: v for k, v in uninstall.items() if k != "kept"})
    assert erros("install-plan", {k: v for k, v in uninstall.items() if k != "left_alone"}), "what was left alone is always said"
    erro = {"schema": "simplicio.video-install-plan/v1", "status": "error", "version": "0.4.0", "error": "host desconhecido: x"}
    valida("install-plan", erro)
    valida("install-plan", {**erro, "host": "x"})
    assert erros("install-plan", {**erro, "error": ""}) and erros("install-plan", {k: v for k, v in erro.items() if k != "error"})
    assert erros("install-plan", {**erro, "up_to_date": True}), "an error is never up to date"
    assert erros("install-plan", {"schema": "simplicio.video-install-plan/v1", "status": "feito"}), "unknown status"


def test_o_recibo_so_aceita_o_dono_e_o_esquema_do_video():
    valida("install-ownership", RECIBO)
    assert erros("install-ownership", {**RECIBO, "owner": "simplicio-loop"})
    assert erros("install-ownership", {**RECIBO, "schema": "simplicio.loop-install-ownership/v2"})
    assert erros("install-ownership", {**RECIBO, "paths": [1]}) and erros("install-ownership", {**RECIBO, "dirs": "x"})
    for chave in RECIBO:
        assert erros("install-ownership", {k: v for k, v in RECIBO.items() if k != chave}), chave


def test_o_recibo_exige_o_sha256_de_cada_caminho_e_so_aceita_caminhos_relativos_simples():
    caminho = ".claude/skills/simplicio-video/SKILL.md"
    assert erros("install-ownership", {**RECIBO, "sha256": {caminho: "xyz"}}), "a digest is 64 lowercase hex digits"
    assert erros("install-ownership", {**RECIBO, "sha256": {caminho: "B" * 64}})
    valida("install-ownership", {**RECIBO, "bases": {".claude": "/home/u/dotfiles/claude"}})
    assert erros("install-ownership", {**RECIBO, "bases": {".claude": ""}}) and erros("install-ownership", {**RECIBO, "bases": {"x": "/a"}})
    for ruim in ("../x", "/etc/passwd", "C:\\x", "C:x", "a\\b", "a/../b", "a/..", "", "x\u0000y"):
        assert erros("install-ownership", {**RECIBO, "paths": [ruim]}), f"{ruim!r} cannot be a path of the receipt"
        assert erros("install-ownership", {**RECIBO, "dirs": [ruim]}), f"{ruim!r} cannot be a dir of the receipt"
    for bom in ("AGENTS.md", ".kiro/steering/simplicio-video.md", "a/b/c.md"):
        valida("install-ownership", {**RECIBO, "paths": [bom], "sha256": {bom: "c" * 64}})


# --- the real outputs validate ---------------------------------------------------------------------------------------


def _doc(capsys, *argv):
    rc, out, err = executa(list(argv), capsys, main)
    return rc, json.loads(out), out + err


def test_doctor_real_valida_saudavel_e_doente(saude, capsys):
    rc, doc, _ = _doc(capsys, "doctor", "--json")
    valida("doctor", doc)
    for f in saude.caixa.bin.glob("*ffmpeg*"):
        f.unlink()
    rc, doc, _ = _doc(capsys, "doctor", "--json")
    valida("doctor", doc)
    assert doc["status"] == "fail"


def test_install_real_valida_check_dry_run_apply_verify_uninstall_e_o_recibo_no_disco(caixa, capsys, tmp_path):
    alvo = tmp_path / "proj"
    alvo.mkdir()
    for argv, status, rc_esperado in ((["--check"], "dry_run", 10), (["--dry-run"], "dry_run", 0), ([], "applied", 0),
                                      (["--check"], "dry_run", 0), (["--verify"], "verified", 0),
                                      (["--uninstall", "--dry-run"], "dry_run", 0), (["--uninstall"], "removed", 0),
                                      (["--uninstall"], "error", 1), (["--host", "nao-existe"], "error", 1)):
        rc, doc, _ = _doc(capsys, "install", "--json", "--target", str(alvo), *argv)
        valida("install-plan", doc)
        assert doc["status"] == status and rc == rc_esperado, (argv, doc)
        if argv == [] and status == "applied":
            valida("install-ownership", json.loads((alvo / ".simplicio-video" / "install-ownership.json").read_text(encoding="utf-8")))


def test_install_global_real_valida_com_resynced_e_pruned_project(caixa, capsys, tmp_path):
    alvo = tmp_path / "proj"
    alvo.mkdir()
    assert executa(["install", "--target", str(alvo)], capsys, main)[0] == 0  # the project copy and its receipt
    (caixa.home / ".codex" / "skills" / "simplicio-video").mkdir(parents=True)
    (caixa.home / ".codex" / "skills" / "simplicio-video" / "SKILL.md").write_text("velha\n", encoding="utf-8")  # not ours: left alone
    n_skills = sum(1 for d in (ROOT / "skills").iterdir() if (d / "SKILL.md").is_file())
    for argv, pendentes in ((["--check"], 10 * n_skills - 1), ([], 0)):  # 10 hosts x every skill, minus the video skill codex already had (not ours)
        rc, doc, _ = _doc(capsys, "install", "--json", "--global", "--prune-project-copies", "--target", str(alvo), *argv)
        valida("install-plan", doc)
        assert "claude" not in doc["resynced"]["skills"] and len(doc["resynced"]["skills"]) == 10
        assert doc["resynced"]["skills_counts"]["codex"] == n_skills - 1 and doc["resynced"]["skills_counts"]["cursor"] == n_skills
        assert doc["resynced"]["pending"] == pendentes
        assert doc["pruned_project"]["removed"], "the dry run lists what it would prune, the real run what it pruned"
        assert any(a.startswith(".codex/skills/simplicio-video") for a in doc["changes"]["left_alone"])


def test_install_de_pacote_instalado_valida(caixa, capsys, monkeypatch, tmp_path):
    monkeypatch.setattr(distribution, "kind", lambda **kw: "pip")
    rc, doc, _ = _doc(capsys, "install", "--json", "--check", "--target", str(tmp_path))
    valida("install-plan", doc)
    assert rc == 10


def test_o_estado_gravado_pelo_update_valida(caixa, capsys, monkeypatch):
    monkeypatch.setattr(distribution, "kind", lambda **kw: "pip")
    monkeypatch.setattr(update_cmd, "fetch_latest_tag", lambda: "v99.0.0")
    assert executa(["update", "--check"], capsys, main)[0] == 10
    valida("update-check", json.loads((caixa.data / "update-check.json").read_text()))
