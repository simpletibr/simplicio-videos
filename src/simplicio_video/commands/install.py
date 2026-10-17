"""`simplicio-video install [--target DIR] [--global] [--host H] [--dry-run] [--check] [--json] [--verify] [--uninstall]
[--prune-project-copies]`: copy the bundled skills into the agent host, exactly as the `install` of simplicio-loop does.

Breaking change (direct owner request, ADR-0020): `install` used to be the `.venv` of the checkout (uv). That is now
`bash scripts/dev_install.sh` (Windows: `powershell -File scripts/dev_install.ps1`). Here `install` copies the skills that ship in the
package (`.claude/skills/simplicio-video` and `simplicio-video-social`) into the project, or into the home with `--global`, and the
entry file of the host when it has one (`AGENTS.md`, `GEMINI.md`, `CONVENTIONS.md`, `.github/copilot-instructions.md`,
`.kiro/steering/simplicio-video.md`; never over a file that exists). It writes an ownership receipt
(`.simplicio-video/install-ownership.json`), never overwrites a file that is not its own and `--uninstall` removes only what the
receipt registers. The video has no hooks: only skills. The same command works for a pip package and for a checkout.

Exit codes (as the loop): `--check` 0 up to date, 10 something pending; `--dry-run` 0 (it writes nothing); 1 a failed install, an
unknown host, a receipt that cannot be trusted or a disk that says no; 2 an invalid argument. With `--json`, stdout is ONE
`simplicio.video-install-plan/v1` document, an error included (the message also goes to stderr).

At the end of a real install, if `setup` never ran on this machine, it starts it in a terminal and otherwise says how to run it.

Standard library only, and so is everything it imports at the top: `python3 -m simplicio_video install` also runs under the SYSTEM
python of a checkout, which has no PyYAML (macOS with the Xcode tools, a minimal Debian). Do not import `setup` here.

Exemplos:
  simplicio-video install --check
  simplicio-video install --global
  simplicio-video install --host codex --target ~/meu-projeto
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Callable, Optional

from .. import __version__, hostos, installer, paths, skill_sync

EXIT_PENDING = 10
SETUP_ARGV = [sys.executable, "-m", "simplicio_video", "setup"]


def _fail(message: str, code: int, as_json: bool, host: str) -> int:
    """The message on stderr and, with --json, ONE document on stdout (status `error`): a program never has to guess."""
    print(f"install: {message}", file=sys.stderr)
    if as_json:
        hostos.say(json.dumps({"schema": installer.SCHEMA, "status": "error", "version": __version__, "host": host,
                               "error": message}, sort_keys=True))
    return code


def _resync_hosts(root: Path, source, apply: bool) -> dict:
    """The skills that other hosts ALREADY have (`~/.codex/skills`...): refresh them, or only list what is stale.

    `rules` and `rules_counts` are the loop's keys: the video has no host rules, so they are always empty."""
    stale = skill_sync.stale_skills(root, source=source)
    counts: dict[str, int] = {}
    for entry in stale:
        counts[entry["host"]] = counts.get(entry["host"], 0) + 1
    if apply:
        report = skill_sync.resync_installed_skills(root, source=source)
        return {"skills": report["synced"], "rules": [], "skills_counts": counts, "rules_counts": {}, "errors": report["errors"],
                "pending": 0}
    return {"skills": sorted(counts), "rules": [], "skills_counts": counts, "rules_counts": {}, "errors": [], "pending": len(stale)}


def _cut_list(prefix: str, items: list) -> str:
    """`prefix` + the items that fit in about 80 columns (at most 5, always at least one), then `(+N mais)`."""
    shown: list[str] = []
    width = len(prefix)
    for i, item in enumerate(items):
        added = len(", " if shown else "") + len(item)
        if i >= 5 or (shown and width + added + 12 > 80):
            break
        shown.append(item)
        width += added
    more = len(items) - len(shown)
    return prefix + ", ".join(shown) + (f" (+{more} mais)" if more > 0 else "")


def _install_lines(result: dict, host: str, head: str, resync: Optional[dict], prune_project: Optional[dict] = None) -> list:
    changes = result["changes"]
    owned = sorted(set(result.get("owned") or []))
    pretend = head.startswith(("check", "dry-run"))
    lines = [f"simplicio-video {__version__} {head}:", f"  host      -> {host}", f"  próprios  -> {len(owned)} arquivos",
             f"  mudanças  -> {len(changes['created'])} criados, {len(changes['updated'])} atualizados, {changes['unchanged']} iguais"]
    for key, label in (("created", "criado"), ("updated", "atualizado")):
        lines += [f"    {label}: {path}" for path in changes[key][:8]]
        if len(changes[key]) > 8:
            lines.append(f"    {label}: ... e mais {len(changes[key]) - 8}")
    if changes["left_alone"]:
        left = changes["left_alone"]
        lines.append(_cut_list(f"  deixado em paz -> {len(left)} que não são do simplicio-video: ", left))
    if resync is not None and (resync["skills"] or resync["errors"]):
        counts = resync.get("skills_counts") or {}
        names = ", ".join(f"{h} ({counts[h]})" for h in sorted(counts)) if counts else ", ".join(resync["skills"]) or "-"
        verb = ("desatualizadas (cópias dos hosts diferentes do pacote, pendentes de atualização)" if pretend
                else "ressincronizadas (cópias dos hosts atualizadas para o pacote)")
        lines.append(f"  {verb} -> skills: {names}")
        lines += [f"  erro ao ressincronizar: {err['host']}: {err['error']}" for err in resync["errors"]]
    if prune_project is not None:
        removed = prune_project.get("removed") or []
        if removed:
            verb = "podaria as cópias do projeto" if pretend else "cópias do projeto podadas"
            lines.append(_cut_list(f"  {verb} -> {len(removed)} arquivos obsoletos: ", removed))
        else:
            lines.append("  cópias do projeto -> 0 arquivos obsoletos")
    return lines


def _uninstall(root: Path, globally: bool, dry_run: bool, as_json: bool, host: str) -> int:
    payload = installer.uninstall(root, dry_run=dry_run)
    if as_json:
        hostos.say(json.dumps({**payload, "host": host, "version": __version__}, sort_keys=True))
        return 0
    verb = "removeria" if dry_run else "removido"
    hostos.say(f"simplicio-video uninstall {'dry-run (nada foi removido)' if dry_run else 'aplicado'}: "
               f"{'removeria' if dry_run else 'removidos'} {len(payload['removed'])} arquivos, {len(payload['removed_dirs'])} pastas vazias")
    for rel in payload["removed"] + [f"{rel}/" for rel in payload["removed_dirs"]]:
        hostos.say(f"  {verb}: {rel}")
    if payload["kept"]:
        hostos.say(f"  mantido (não vazio, guarda arquivos que o simplicio-video não instalou): {', '.join(payload['kept'])}")
    if payload["skipped"]:
        hostos.say(f"  ignorado (é pasta onde se esperava arquivo): {', '.join(payload['skipped'])}")
    if globally:
        hostos.say("  não removido (fora do recibo): as cópias das skills simplicio-video* que `install --global` atualiza em outros "
                   "hosts (~/.codex/skills e semelhantes); apague à mão")
    return 0


def _terminal() -> bool:
    try:
        return bool(sys.stdin.isatty() and sys.stdout.isatty())
    except (ValueError, AttributeError):  # a closed or replaced stream is not a terminal
        return False


def _run_setup(argv: list) -> int:
    try:
        return subprocess.call(argv)
    except OSError as exc:
        print(f"install: não consegui iniciar o setup: {exc}", file=sys.stderr)
        return 1


def _setup_done() -> bool:
    workspace = paths.workspace_dir()
    return hostos.is_file(workspace / "workspace.yaml") and hostos.is_file(workspace / "policy.yaml")


def after_install(*, interactive: Optional[bool] = None, runner: Optional[Callable[[list], int]] = None) -> None:
    """The last lines of `install`: start the setup in a terminal, else say how to run it. Never fails the install.

    Once a workspace exists the setup has run, so a later install stays quiet (`doctor` shows the state)."""
    if _setup_done():
        return
    if _terminal() if interactive is None else interactive:
        hostos.say("\nPróximo passo: setup (workspace, tema, idioma).\n")
        code = (runner or _run_setup)(list(SETUP_ARGV))
        if code != 0:
            hostos.say(f"install: o setup terminou com código {code}; rode `simplicio-video setup` de novo quando quiser.")
    else:
        hostos.say("\nPróximo passo: rode `simplicio-video setup` (workspace, tema, idioma).")


def install(target: Path, globally: bool, host: str = "claude", dry_run: bool = False, uninstall: bool = False,
            verify: bool = False, check: bool = False, as_json: bool = False, prune_project_copies: bool = False) -> int:
    if prune_project_copies and not globally:
        return _fail("--prune-project-copies só vale com --global (ele remove as cópias do projeto depois de instalar no home)",
                     2, as_json, host)
    root = hostos.home_dir(os.environ) if globally else Path(target)
    try:
        if uninstall:
            return _uninstall(root, globally, dry_run, as_json, host)
        plan = installer.plan_install(root, host=host, globally=globally)
        if verify:
            verified = installer.verify_plan(plan)
            if as_json:
                hostos.say(json.dumps({"schema": installer.SCHEMA, "status": "verified", **verified, "host": host},
                                      sort_keys=True))
            else:
                hostos.say(f"simplicio-video install: plano ok host={host} digest={plan['digest']}")
            return 0
        bundle = installer.bundle_root()
        result = installer.apply_plan(plan, dry_run=dry_run or check, bundle=bundle)
        resync = _resync_hosts(root, bundle.joinpath("skills"), apply=not (dry_run or check)) if globally else None
        prune_result = installer.prune_project_copies(target, dry_run=dry_run or check) if (globally and prune_project_copies) else None
    except (installer.InstallError, OSError) as exc:
        return _fail(str(exc), 1, as_json, host)
    pending = not result["up_to_date"] or bool(resync and resync["pending"])
    up_to_date = result["up_to_date"] and not (resync and (resync["pending"] or resync["skills"] or resync["errors"]))
    if as_json:
        payload = {**result, "up_to_date": up_to_date, "host": host, "version": __version__, "resynced": resync}
        if prune_result is not None:
            payload["pruned_project"] = prune_result
        hostos.say(json.dumps(payload, sort_keys=True))
        return EXIT_PENDING if check and pending else 0
    if check:
        head = "check: há mudanças pendentes" if pending else "check: em dia"
    elif dry_run:
        head = "dry-run (nada foi escrito)"
    else:
        head = "já está em dia" if up_to_date else "instalado"
    hostos.say("\n".join(_install_lines(result, host, head, resync, prune_project=prune_result)))
    if not (dry_run or check):
        hostos.say("")
        hostos.say("Use no seu agente (Claude Code, Cursor, Codex, ...):")
        hostos.say("  /simplicio-video <o vídeo que você quer>")
        after_install()
    return EXIT_PENDING if check and pending else 0


def _target(text: str) -> Path:
    """`--target ~/proj` quoted by the shell (or typed in PowerShell) is still the home's `proj`."""
    try:
        return Path(text).expanduser()
    except RuntimeError:  # `~someone` of a user that does not exist: the text is used as it is
        return Path(text)


def run(a) -> int:
    return install(_target(a.target), a.globally, host=a.host, dry_run=a.dry_run, uninstall=a.uninstall, verify=a.verify, check=a.check,
                   as_json=a.json, prune_project_copies=a.prune_project_copies)
