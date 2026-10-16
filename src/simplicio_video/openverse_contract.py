"""Openverse assets in a contract: the offline gate behind `validate`, `render` and `openverse library verify`.

A contract asset (`assets[]` or `marca.logo`, image or audio) may declare `openverse: {id, pedido}`. The rules, all offline (no
network, no LLM, nothing written to the library):

- the asset with the block must sit in an `assets/openverse/` folder (where `library export --contrato` puts it), next to the
  `CREDITS-openverse.md` the export wrote;
- the approval logic is NOT here: `openverse.verify_asset` checks the id, the sha256, the verdict for the pair (id, sha256, request,
  provenance), the rights and the credit with the functions the review and the export already use;
- a file inside `assets/openverse/` without the block is refused (nobody skips the gate by copying a file by hand), and so is any
  other asset with the bytes of a library asset;
- a contract with no asset from the library behaves exactly as before: the library is not even opened unless an asset exists.

At the end of a render, `deliver` writes the credits next to the output MP4 and returns the provenance block of the manifest.
Text from the internet reaches the manifest only in `untrusted_*` fields and the credits only through the export's sanitizing.
"""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from pathlib import Path

from . import openverse as ov

CREDITS_SUFFIX = ".CREDITS-openverse.md"
BLOCK_HINT = 'openverse: {id: <uuid do ativo>, pedido: "<o que a cena precisa>"}'


@dataclass
class Verification:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    ativos: list[dict] = field(default_factory=list)  # one entry per asset that matters: declared, inside assets/openverse/ or refused


def declared_assets(c) -> list[dict]:
    """The asset entries of the contract (assets[] and marca.logo) in contract order; the contract may not be schema-valid yet."""
    d = c.data
    out = [a for a in d.get("assets") or [] if isinstance(a, dict) and isinstance(a.get("arquivo"), str)]
    logo = (d.get("marca") or {}).get("logo")
    if isinstance(logo, dict) and isinstance(logo.get("arquivo"), str):
        out.append(logo)
    return out


def in_openverse_dir(path: Path, base: Path) -> bool:
    """True when the resolved file sits in an assets/openverse folder: anywhere under the contract folder `base` (so a project that
    lives inside some other `assets/openverse` path is not flagged as a whole), or, for a file outside it, directly in such a folder."""
    path = path.resolve()
    try:
        parts = path.relative_to(base.resolve()).parts[:-1]
    except ValueError:
        parts = path.parts[-3:-1]
    return any(a == "assets" and b == "openverse" for a, b in zip(parts, parts[1:]))


def _result(a: dict, bloco) -> dict:
    return {"arquivo": a["arquivo"], "destino": a.get("destino"), "declarado": bloco is not None, "ok": False, "erros": [], "proveniencia": None}


def verify(c) -> Verification:
    """Check every contract asset that comes from, or could pass for, the Openverse library. Assets whose file is missing are left to
    `validate` (it already reports them)."""
    ver = Verification()
    itens = [(a, c.rel(a["arquivo"])) for a in declared_assets(c)]
    itens = [(a, p) for a, p in itens if p.is_file()]
    if not itens:
        return ver
    idx, falha = None, None
    try:
        idx = ov.load_index()
    except ov.OpenverseError as e:
        falha = str(e)
    for a, p in itens:
        bloco = a.get("openverse")
        res = _result(a, bloco)
        no_dir = in_openverse_dir(p, c.dir)
        if bloco is None and no_dir:
            res["erros"].append(f"o arquivo está em assets/openverse/ mas o asset não declara o bloco openverse (id e pedido): declare {BLOCK_HINT}; "
                                "sem a procedência e a revisão aprovada para o pedido, o ativo não entra no vídeo")
        elif bloco is not None and not no_dir:
            res["erros"].append("o asset declara o bloco openverse mas o arquivo não está em assets/openverse/: use o arquivo que o "
                                "`simplicio-video openverse library export <id> --pedido ... --contrato <contrato>` copiou, ao lado do CREDITS-openverse.md")
        elif falha is not None:
            if bloco is not None:
                res["erros"].append(falha)
        else:
            r = ov.verify_asset(p, bloco, idx=idx)
            res.update(ok=r["ok"], erros=r["erros"], proveniencia=r["proveniencia"])
        res["ok"] = res["ok"] and not res["erros"]
        if bloco is not None or no_dir or res["erros"]:
            ver.ativos.append(res)
        ver.errors += [f"openverse: {a['arquivo']}: {e}" for e in res["erros"]]
    if falha is not None and not any(a.get("openverse") is not None for a, _ in itens):
        ver.warnings.append(f"openverse: não consegui conferir se algum asset veio da biblioteca do Openverse: {falha}")
    return ver


def credits_path(dst: Path) -> Path:
    """Where the credits of an output MP4 go: next to it, named after it (a folder may hold several videos)."""
    return dst.with_name(dst.stem + CREDITS_SUFFIX)


def deliver(c, dst: Path) -> dict | None:
    """Re-check the declared assets, write the credits next to the output MP4 and return the `openverse` block of the manifest
    (None when the contract uses no Openverse asset, and then nothing is written). Raises SystemExit if an asset stopped being valid."""
    ver = verify(c)
    if ver.errors:
        raise SystemExit("openverse: um ativo deixou de valer antes de gravar o manifesto:\n  " + "\n  ".join(ver.errors))
    ativos = [a for a in ver.ativos if a["declarado"]]
    if not ativos:
        return None
    texto = ov.credits_markdown([(a["proveniencia"]["id"], a["proveniencia"]["sha256"]) for a in ativos])
    path = credits_path(Path(dst))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(texto, encoding="utf8")
    return {"creditos": os.path.relpath(path, c.dir), "creditos_sha256": hashlib.sha256(texto.encode("utf8")).hexdigest(),
            "ativos": [{"arquivo": a["arquivo"], "destino": a["destino"], **a["proveniencia"]} for a in ativos]}


def verify_report(path) -> dict:
    """`openverse library verify <contrato>`: the same check as validate, itemized, for one contract file."""
    from . import contract as ct
    p = Path(path).expanduser()
    if not p.is_file():
        raise ov.OpenverseError(f"contrato não encontrado: {path}")
    try:
        c = ct.load(p)
    except SystemExit as e:
        raise ov.OpenverseError(str(e)) from None
    ver = verify(c)
    return {"ok": not ver.errors, "contrato": str(c.path), "ativos": ver.ativos, "erros": ver.errors, "avisos": ver.warnings}


def verify_text(doc: dict) -> str:
    lines = [f"contrato: {doc['contrato']}", f"ativos do Openverse conferidos: {len(doc['ativos'])} (sem rede, sem LLM; nada foi gravado)"]
    for a in doc["ativos"]:
        p = a["proveniencia"]
        if a["ok"]:
            ap = p["aprovacao"]
            lines.append(f"[ok] {a['arquivo']} | id {p['id']} | {ov.license_label(p['licenca'], p['licenca_versao'])} | aprovado para \"{p['pedido']}\" "
                         f"por {ap['por']} ({ap['canal']}) em {ap['em']}" + (" | restrição aceita no export" if p["aceito_restricao"] else ""))
        else:
            lines.append(f"[falta] {a['arquivo']}")
            lines += [f"   - {e}" for e in a["erros"]]
    lines += [f"aviso: {w}" for w in doc["avisos"]]
    if not doc["ativos"]:
        lines.append("nenhum ativo do Openverse neste contrato (nada a conferir)")
    elif doc["ok"]:
        lines.append("tudo certo: o validate e o render aceitam estes ativos")
    else:
        lines.append(f"falta resolver {sum(1 for a in doc['ativos'] if not a['ok'])} ativo(s) antes do validate passar")
    return "\n".join(lines)
