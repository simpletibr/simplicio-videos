"""Openverse assets in a contract: the offline gate behind `validate`, `render` and `openverse library verify`.

A contract asset (`assets[]` or `marca.logo`, image or audio) may declare `openverse: {id, pedido}`. The rules, all offline (no
network, no LLM, nothing written to the library):

- the asset with the block must sit in an `assets/openverse/` folder (where `library export --contrato` puts it), next to the
  `CREDITS-openverse.md` the export wrote;
- the approval logic is NOT here: `openverse.verify_asset` checks the id, the sha256, the verdict for the pair (id, sha256, request,
  provenance), the rights and the credit with the functions the review and the export already use;
- a file inside `assets/openverse/` without the block is refused (nobody skips the gate by copying a file by hand), and so is any
  other asset with the bytes of a library asset; `placas_video[].file` goes through the same check and never carries the block, so a
  library file cannot reach the video as a plate;
- `validate` opens the library only if an asset file exists. The render also compares the COMPILED composition with the library
  (`check_workdir`, after the compile, over the sha256 of every file the render will read): a file with the bytes of a library asset
  must be the `destino` of an approved, declared asset, and every declared `destino` must hold exactly the approved bytes. That
  closes what the contract cannot see (a template folder, a destination overwritten by another asset, a swap after the gate).

At the end of a render, `deliver` re-checks the same things with the same file hashes (`info["files"]`), writes the credits next to
the output MP4 and returns the provenance block of the manifest. Text from the internet reaches the manifest only in `untrusted_*`
fields and the credits only through the export's sanitizing.
"""
from __future__ import annotations

import hashlib
import os
import posixpath
import unicodedata
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
    """The files the contract copies into the composition, in contract order: `assets[]` and `marca.logo` (they may carry the block)
    and `placas_video[].file` (marked `placa`; a plate never carries the block, so the block is never read from it). The contract may
    not be schema-valid yet."""
    d = c.data
    out = [a for a in d.get("assets") or [] if isinstance(a, dict) and isinstance(a.get("arquivo"), str)]
    logo = (d.get("marca") or {}).get("logo")
    if isinstance(logo, dict) and isinstance(logo.get("arquivo"), str):
        out.append(logo)
    for slot in d.get("placas_video") or []:
        if isinstance(slot, dict) and isinstance(slot.get("file"), str):
            out.append({"arquivo": slot["file"], "destino": slot["file"], "placa": str(slot.get("id"))})
    return out


def _folded(part: str) -> str:
    return unicodedata.normalize("NFC", part).casefold()


def in_openverse_dir(path: Path, base: Path) -> bool:
    """True when the resolved file sits in an assets/openverse folder: anywhere under the contract folder `base` (so a project that
    lives inside some other `assets/openverse` path is not flagged as a whole), or, for a file outside it, directly in such a folder.
    Case and Unicode form do not matter (macOS and Windows file systems treat `assets/OpenVerse` as the export folder)."""
    path = path.resolve()
    try:
        parts = path.relative_to(base.resolve()).parts[:-1]
    except ValueError:
        parts = path.parts[-3:-1]
    parts = [_folded(p) for p in parts]
    return any(a == "assets" and b == "openverse" for a, b in zip(parts, parts[1:]))


def _result(a: dict, bloco) -> dict:
    return {"arquivo": a["arquivo"], "destino": a.get("destino"), "declarado": bloco is not None, "ok": False, "erros": [], "proveniencia": None}


def _placa_msg(a: dict, motivo: str) -> str:
    return (f"placas_video[{a['placa']}].file: {motivo}; uma placa de vídeo não aceita o bloco nem passa pelo portão: declare em assets[] com o "
            f"bloco openverse ({BLOCK_HINT}) e use o ativo pela composição, não como placa")


def verify(c) -> Verification:
    """Check every contract file that comes from, or could pass for, the Openverse library: assets, logo and video plates. Files that
    are missing are left to `validate` (it already reports them)."""
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
        placa = a.get("placa") is not None
        bloco = None if placa else a.get("openverse")  # a plate never declares provenance: a block there is not read
        res = _result(a, bloco)
        no_dir = in_openverse_dir(p, c.dir)
        if bloco is None and no_dir:
            if placa:
                res["erros"].append(_placa_msg(a, "o arquivo está em assets/openverse/ e a placa não declara a procedência"))
            else:
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
            res.update(ok=r["ok"], erros=[_placa_msg(a, e) for e in r["erros"]] if placa else r["erros"], proveniencia=r["proveniencia"])
        res["ok"] = res["ok"] and not res["erros"]
        if bloco is not None or no_dir or res["erros"]:
            ver.ativos.append(res)
        ver.errors += [f"openverse: {a['arquivo']}: {e}" for e in res["erros"]]
    if falha is not None and not any(a.get("openverse") is not None for a, _ in itens):
        ver.warnings.append(f"openverse: não consegui conferir se algum asset veio da biblioteca do Openverse: {falha}")
    return ver


def check_workdir(c, files: dict, ver: Verification | None = None) -> list[str]:
    """The compiled composition against the library. `files` is {path in the workdir: sha256}, what `render.tree_hash` computed over
    the files the render will read. Two rules, both about the bytes that really go into the video:
    - every declared, approved asset has, at its `destino`, exactly the approved bytes (a destination overwritten by another file, or
      a file swapped between the gate and the copy, would otherwise be credited in the manifest without being in the video);
    - every file with the bytes of a library asset is the `destino` of such an asset (a template folder, a plate or a hand copy
      cannot carry a library file past the gate).
    Returns the problems in plain words; an unreadable library index leaves the second rule out (`validate` already said so)."""
    ver = ver if ver is not None else verify(c)
    declared = [(posixpath.normpath(a["destino"]), a["proveniencia"]["id"], a["proveniencia"]["sha256"])
                for a in ver.ativos if a["declarado"] and a["proveniencia"]]
    errors = []
    for destino, id_, sha in declared:
        got = files.get(destino)
        if got != sha:
            estado = "não foi copiado para a composição" if got is None else f"tem outros bytes (sha256 {got})"
            errors.append(f"o destino {destino} {estado}, e não os bytes aprovados do ativo {id_} (sha256 {sha}): a procedência declarada não vale "
                          "para o que vai ao vídeo (dois arquivos para o mesmo destino, ou um arquivo trocado depois da conferência)")
    approved = {(destino, sha) for destino, _, sha in declared}
    try:
        itens = ov.load_index()["itens"]
    except ov.OpenverseError:
        return errors
    por_sha = {r["sha256"]: id_ for id_, r in itens.items()}
    for rel, sha in sorted(files.items()):
        if sha in por_sha and (rel, sha) not in approved:
            errors.append(f"{rel} tem os mesmos bytes do ativo {por_sha[sha]} da biblioteca do Openverse, mas não é o destino de nenhum asset com o bloco "
                          f"openverse aprovado: o arquivo veio de uma pasta de template, de uma placa ou de uma cópia à mão; declare o ativo em assets[] "
                          f"com o bloco openverse ({BLOCK_HINT}) ou tire o arquivo da composição")
    return errors


def refuse(intro: str, errors: list[str]) -> SystemExit:
    return SystemExit(f"openverse: {intro}:\n  " + "\n  ".join(errors))


def credits_path(dst: Path) -> Path:
    """Where the credits of an output MP4 go: next to it, named after it (a folder may hold several videos)."""
    return dst.with_name(dst.stem + CREDITS_SUFFIX)


def deliver(c, dst: Path, files: dict) -> dict | None:
    """Re-check the declared assets and the composition (`files`: the same {path: sha256} the render hashed, so the provenance is tied to
    the files the video was made of), write the credits next to the output MP4 and return the `openverse` block of the manifest (None
    when the contract uses no Openverse asset, and then nothing is written). Raises SystemExit, writing nothing, if an asset stopped
    being valid or the composition does not hold the approved bytes."""
    ver = verify(c)
    if ver.errors:
        raise refuse("um ativo deixou de valer antes de gravar o manifesto", ver.errors)
    erros = check_workdir(c, files, ver)
    if erros:
        raise refuse("a composição do render não confere com os ativos aprovados; nada foi gravado", erros)
    ativos = [a for a in ver.ativos if a["declarado"]]
    if not ativos:
        return None
    texto = ov.credits_markdown([(a["proveniencia"]["id"], a["proveniencia"]["sha256"]) for a in ativos])
    path = credits_path(Path(dst))
    ov._atomic_write(path, texto)  # mkstemp + os.replace: a link planted at this name is replaced, not followed
    os.chmod(path, 0o644)  # mkstemp makes it 0600; the credits are a normal file next to the MP4
    return {"creditos": os.path.relpath(path, c.dir), "creditos_sha256": hashlib.sha256(texto.encode("utf8")).hexdigest(),
            "ativos": [{"arquivo": a["arquivo"], "destino": a["destino"], **a["proveniencia"]} for a in ativos]}


def verify_report(path) -> dict:
    """`openverse library verify <contrato>`: the same check as validate (the schema included), itemized, for one contract file."""
    from . import contract as ct
    p = Path(path).expanduser()
    if not p.is_file():
        raise ov.OpenverseError(f"contrato não encontrado: {path}")
    try:
        c = ct.load(p)
    except SystemExit as e:
        raise ov.OpenverseError(str(e)) from None
    ver = verify(c)
    erros = ct.schema_errors(c.data) + ver.errors
    return {"ok": not erros, "contrato": str(c.path), "ativos": ver.ativos, "erros": erros, "avisos": ver.warnings}


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
    schema = [e for e in doc["erros"] if e.startswith("schema:")]
    if schema:
        lines.append("[falta] o contrato não passa no schema (o validate o recusa):")
        lines += [f"   - {e}" for e in schema]
    lines += [f"aviso: {w}" for w in doc["avisos"]]
    pendentes = sum(1 for a in doc["ativos"] if not a["ok"])
    if doc["ok"] and doc["ativos"]:
        lines.append("tudo certo: os ativos do Openverse estão ok (o validate e o render os aceitam)")
    elif doc["ok"]:
        lines.append("nenhum ativo do Openverse neste contrato (nada a conferir)")
    else:
        faltas = ([f"{pendentes} ativo(s)"] if pendentes else []) + (["o schema do contrato"] if schema else [])
        lines.append(f"falta resolver {' e '.join(faltas)} antes do validate passar")
    return "\n".join(lines)
