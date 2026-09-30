"""`simplicio-video publish`: upload the final MP4 to Google Drive at drive.caminho/drive.arquivo (rclone, no browser)
and record the link in clients/<slug>/README.md ("Entregas no Drive").

Rules (AGENTS.md): never overwrite a delivered version (same name + different bytes = error, bump vNN); same bytes =
idempotent (just refresh the link). Links come from the Drive file ID (`rclone lsjson`), never from `rclone link`
(that would change sharing to "anyone with the link").

One-time auth (Wesley): an rclone remote of type `drive` (default name `gdrive`, override with --remote or
SIMPLICIO_DRIVE_REMOTE) with scope `drive` and his own OAuth client_id (rclone's shared id is retired in 2026).
See docs/decisoes/ADR-0003-fluxo-100-script.md.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Callable

from .contract import Contract

Runner = Callable[[list[str]], subprocess.CompletedProcess]
HEADER = "| Campanha | Pasta | Arquivo | Link | Versão / status |"


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True)


def _md5(p: Path) -> str:
    h = hashlib.md5()  # noqa: S324 - Drive exposes md5Checksum; used only to compare bytes
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _lsjson(run: Runner, rc: str, target: str, *flags: str) -> list[dict]:
    p = run([rc, "lsjson", *flags, target])
    if p.returncode != 0:
        if "not found" in (p.stderr or "").lower() or p.returncode == 3:
            return []
        raise SystemExit(f"rclone lsjson {target} failed (exit {p.returncode}):\n{(p.stderr or '')[-2000:]}\n"
                         "check the remote: `rclone about <remote>:` (auth: docs/decisoes/ADR-0003-fluxo-100-script.md)")
    return json.loads(p.stdout or "[]")


def readme_path(c: Contract) -> Path:
    slug = c.data["cliente"]["slug"]
    for p in [c.dir, *c.dir.parents]:
        if p.name == slug and p.parent.name == "clients":
            return p / "README.md"
    return c.home / "clients" / slug / "README.md"


def upsert_readme(readme: Path, c: Contract, file_url: str | None, folder_url: str | None, status: str) -> str:
    d = c.data["drive"]
    camp, ano = c.data["campanha"]["id"], c.data["campanha"]["ano"]
    pasta = f"[{ano}/{camp}]({folder_url})" if folder_url else f"{ano}/{camp}"
    link = f"[abrir]({file_url})" if file_url else "**(preencher: link do Drive)**"
    text = readme.read_text(encoding="utf8") if readme.is_file() else f"# {c.data['cliente'].get('nome', c.data['cliente']['slug'])}\n"
    lines = text.splitlines()
    for i, ln in enumerate(lines):
        cells = [x.strip() for x in ln.strip().strip("|").split("|")] if ln.lstrip().startswith("|") else []
        if len(cells) >= 5 and cells[2] == d["arquivo"]:
            cells[3] = link
            if folder_url and "](" not in cells[1]:
                cells[1] = pasta
            lines[i] = "| " + " | ".join(cells) + " |"
            break
    else:
        row = f"| {camp} | {pasta} | {d['arquivo']} | {link} | {status} |"
        try:
            h = next(i for i, ln in enumerate(lines) if ln.strip() == HEADER)
            j = h + 2
            while j < len(lines) and lines[j].lstrip().startswith("|"):
                j += 1
            lines.insert(j, row)
        except StopIteration:
            lines += ["", "## Entregas no Drive", "",
                      "Convenção: `simplicio-video/clientes/NOME_CLIENTE/ANO/CAMPANHA`. O repositório guarda **só os links**.", "",
                      HEADER, "|---|---|---|---|---|", row]
    new = "\n".join(lines) + "\n"
    readme.parent.mkdir(parents=True, exist_ok=True)
    readme.write_text(new, encoding="utf8")
    return new


def publish(c: Contract, file: Path | None = None, remote: str | None = None, dry_run: bool = False,
            readme: Path | None = None, update_readme: bool = True, run: Runner | None = None, log=print) -> dict:
    d = c.data["drive"]
    src = Path(file).resolve() if file else c.rel(c.data["saida"]["arquivo"]).resolve()
    if not src.is_file():
        raise SystemExit(f"publish: {src} not found - run `simplicio-video render {c.path}` first")
    man = c.dir / "render.manifest.json"
    if man.is_file():
        m = json.loads(man.read_text(encoding="utf8"))
        if m.get("output", {}).get("sha256") and m["output"]["sha256"] != hashlib.sha256(src.read_bytes()).hexdigest():
            log(f"warning: {src.name} differs from render.manifest.json output (re-render or pass --file)")
    remote = (remote or os.environ.get("SIMPLICIO_DRIVE_REMOTE") or "gdrive").rstrip(":")
    folder = f"{remote}:{d['caminho']}"
    dest = f"{folder}/{d['arquivo']}"
    plan = {"source": str(src), "size": src.stat().st_size, "dest": dest, "remote": remote}
    if dry_run:
        log(f"publish (dry-run): {src} -> {dest}")
        return {**plan, "dry_run": True}
    run = run or _run
    rc = os.environ.get("SIMPLICIO_RCLONE_BIN") or shutil.which("rclone")
    if not rc:
        raise SystemExit("publish: rclone not found (https://rclone.org/install/); one-time setup in ADR-0003")
    existing = {f["Name"]: f for f in _lsjson(run, rc, folder, "--files-only", "--hash")}
    status = "uploaded"
    if d["arquivo"] in existing:
        f = existing[d["arquivo"]]
        md5 = (f.get("Hashes") or {}).get("md5") or (f.get("Hashes") or {}).get("MD5")
        if f.get("Size") == src.stat().st_size and (md5 is None or md5 == _md5(src)):
            status = "already-published"
            log(f"publish: {dest} already has these bytes - not uploading again")
        else:
            raise SystemExit(f"publish: {dest} already exists with different content. Never overwrite a delivery: "
                             "bump drive.arquivo to vNN+1 in the contract and publish again.")
    if status == "uploaded":
        log(f"$ rclone copyto {src} {dest}")
        p = run([rc, "copyto", str(src), dest, "--drive-chunk-size", "64M"])
        if p.returncode != 0:
            raise SystemExit(f"publish: rclone copyto failed (exit {p.returncode}):\n{(p.stderr or '')[-2000:]}")
    files = {f["Name"]: f for f in _lsjson(run, rc, folder, "--files-only")}
    fid = (files.get(d["arquivo"]) or {}).get("ID")
    parent, leaf = d["caminho"].rsplit("/", 1)
    dirs = {x["Name"]: x for x in _lsjson(run, rc, f"{remote}:{parent}", "--dirs-only")}
    did = (dirs.get(leaf) or {}).get("ID")
    file_url = f"https://drive.google.com/file/d/{fid}/view" if fid else None
    folder_url = f"https://drive.google.com/drive/folders/{did}" if did else d.get("pasta_url")
    res = {**plan, "status": status, "file_id": fid, "link": file_url, "folder_url": folder_url}
    if update_readme:
        rp = readme or readme_path(c)
        st = d.get("status") or f"publicado em {dt.date.today():%d/%m/%Y}"
        upsert_readme(rp, c, file_url, folder_url, st)
        res["readme"] = str(rp)
        log(f"readme: {rp} (Entregas no Drive)")
    log(f"publish: {status} -> {file_url or dest}")
    if file_url and not d.get("link"):
        log(f"tip: add `link: {file_url}` under drive: in the contract")
    return res

