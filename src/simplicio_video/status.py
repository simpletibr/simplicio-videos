"""Estado do motor para o looping (issue #73): `--version --json`, `status` e `status --json [CONTRATO]`.

Ferramentas: as três do `tools.py` (OpenMontage, OpenCut, Hypit) com a versão fixada de lá; ffmpeg e node
só são detectados (sem versão fixada). Detecção por shutil.which (existe no PATH) e leitura da versão
(`--version` / `-version`, ou o commit do checkout para ferramentas git; o `tinyfish`, de terceiros, roda com o ambiente
fechado do `busca`: nenhuma chave do shell chega a ele). Nada de rede e nada de sockets:
a versão só é lida de um executável que já está no PATH, e uma ferramenta ausente vira installed false.

Estado do render: o render.manifest.json ao lado do contrato. Sem manifesto, rendered false.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from . import HYPERFRAMES, __version__, tools

SEM_VERSAO = "sem versão fixada"
MANIFEST = "render.manifest.json"
ENGINE_TOOLS = ("openmontage", "opencut", "hypit", "toonflow", "moneyprinter", "voicestudio", "tinyfish", "ffmpeg", "node")
PLAIN_TOOLS = ("ffmpeg", "node")  # só detectadas: o motor não fixa versão delas


class StatusError(Exception):
    pass


def version_info() -> dict:
    return {"version": __version__, "engine": HYPERFRAMES}


def _primeira_linha(cmd: list[str]) -> str | None:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.SubprocessError):
        return None
    linhas = (r.stdout or r.stderr or "").strip().splitlines()
    return linhas[0].strip() if r.returncode == 0 and linhas else None


def _versao_ffmpeg(exe: str) -> str | None:
    linha = _primeira_linha([exe, "-version"])
    if not linha:
        return None
    partes = linha.split()  # "ffmpeg version 6.1.1-..." -> "6.1.1-..."
    return partes[2] if len(partes) > 2 and partes[1] == "version" else linha


def _linha(name: str, installed: bool, version: str | None, pinned: str | None, pinned_source: str) -> dict:
    return {"name": name, "installed": installed, "version": version, "pinned": pinned, "pinned_source": pinned_source}


def _ferramenta_do_motor(name: str) -> dict:
    t = tools.get(name)
    fonte = (f"SIMPLICIO_{name.upper()}_REF (sobrepõe tools.py)"
             if os.environ.get(f"SIMPLICIO_{name.upper()}_REF") else "tools.py (TOOLS)")
    pinned = tools.pinned_ref(t)
    if t.kind == "git":
        d = tools.find(name)
        version = None
        if d is not None:
            try:
                version = tools._git("rev-parse", "--short=12", "HEAD", cwd=d)
            except tools.ToolError:
                version = None
        return _linha(name, d is not None, version, pinned, fonte)
    exe = shutil.which(t.name)  # npm: o binário no PATH (ou o npx do motor, que não é checado aqui)
    if exe and name == "tinyfish":
        from . import busca  # binário de terceiros: só o ambiente fechado do `busca` (nenhuma chave do shell) e sem telemetria
        version = busca._versao_cli(exe)
    else:
        version = _primeira_linha([exe, "--version"]) if exe else None
    return _linha(name, exe is not None, version, pinned, fonte)


def _ferramenta_simples(name: str) -> dict:
    exe = shutil.which(name)
    if not exe:
        return _linha(name, False, None, None, SEM_VERSAO)
    version = _versao_ffmpeg(exe) if name == "ffmpeg" else _primeira_linha([exe, "--version"])
    return _linha(name, True, version, None, SEM_VERSAO)


def tool_status(name: str) -> dict:
    if name in PLAIN_TOOLS:
        return _ferramenta_simples(name)
    return _ferramenta_do_motor(name)


def render_state(contrato: Path) -> dict:
    manifesto = contrato.parent / MANIFEST
    data = None
    if manifesto.is_file():
        try:
            data = json.loads(manifesto.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = None
    if not isinstance(data, dict):
        return {"rendered": False, "contract_sha256": None, "finished_at": None}
    return {"rendered": True, "contract_sha256": data.get("contract_sha256"), "finished_at": data.get("finished_at")}


def report(contrato: str | Path | None = None) -> dict:
    from . import busca, openverse, swap
    rep: dict = {"tools": [tool_status(n) for n in ENGINE_TOOLS], "swap": swap.status_summary(), "openverse": openverse.status_summary(),
                 "busca": busca.status_summary()}
    if contrato is not None:
        path = Path(contrato)
        if not path.is_file():
            raise StatusError(f"contrato não encontrado: {contrato}")
        rep["render"] = render_state(path)
    return rep


def text(rep: dict) -> str:
    linhas = ["ferramentas:"]
    for t in rep["tools"]:
        estado = "instalada" if t["installed"] else "ausente"
        fixada = t["pinned"] or "-"
        linhas.append(f"  {t['name']:<12} {estado:<9} versão {t['version'] or '-':<16} "
                      f"fixada {fixada} ({t['pinned_source']})")
    if rep.get("swap"):
        linhas.append("swap (troca de personagem; só diz se a variável da chave está definida, nunca o valor):")
        for p in rep["swap"]:
            chave = p["env_var"] or "sem chave"
            estado = "pronto" if p["configured"] else "sem chave"
            marca = "" if p["verified"] else "  UNVERIFIED"
            linhas.append(f"  {p['name']:<10} {estado:<10} {chave}{marca}")
    if rep.get("openverse"):
        o = rep["openverse"]
        linhas.append("openverse (biblioteca de imagens e áudio; só diz se as variáveis OAuth2 existem, nunca o valor):")
        linhas.append(f"  biblioteca {o['biblioteca']}: {o['itens'] if o['itens'] is not None else '?'} ativo(s), "
                      f"{o['revisoes'] if o['revisoes'] is not None else '?'} revisão(ões), {o['exportacoes'] if o['exportacoes'] is not None else '?'} exportação(ões)")
        cred = ", ".join(f"{k} {'definida' if v else 'não definida'}" for k, v in o["credenciais"].items())
        linhas.append(f"  {cred} (opcionais: sem elas a busca é anônima)")
        if o.get("indice_erro"):
            linhas.append(f"  ATENÇÃO {o['indice_erro']}")
    if rep.get("busca"):
        b = rep["busca"]
        chamadas = b["chamadas_hoje"] if b["chamadas_hoje"] is not None else "?"
        teto = b["teto"] if b["teto"] is not None else "?"
        linhas.append("busca (TinyFish; só diz se a variável da chave existe, nunca o valor; detalhes em `simplicio-video busca status`):")
        linhas.append(f"  hoje {chamadas} de {teto} chamada(s) | {b['variavel_da_chave']} {'definida' if b['variavel_da_chave_definida'] else 'não definida'} "
                      f"(a chave também pode estar na configuração do próprio tinyfish) | pasta {b['pasta']}")
    if "render" in rep:
        r = rep["render"]
        if r["rendered"]:
            linhas.append(f"render: sim, contrato sha256 {r['contract_sha256']}, terminou em {r['finished_at'] or '-'}")
        else:
            linhas.append("render: não renderizado")
    return "\n".join(linhas)
