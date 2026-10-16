"""Mede se o resultado e REPRODUTIVEL na sua maquina: roda o mesmo comando duas vezes e compara os sha256 das saidas.

Dois modos:

  1) Rodar duas vezes (script, ffmpeg, python ...). Diga quais arquivos/pastas o comando produz com --saida:
       python receita_test_hash.py --rotulo vace_480p --saida saida\\resultado.mp4 --entrada entradas\\clipe.mp4 -- python meu_script.py
     Antes de cada rodada a saida antiga e apagada (para provar que foi recriada); depois de cada rodada uma
     copia vai para rodadas_hash\\rodada1\\ e rodada2\\.

  2) Comparar saidas que voce ja gerou (o caso do ComfyUI: rode o MESMO fluxo duas vezes com a mesma semente
     e copie cada video para um nome diferente):
       python receita_test_hash.py --comparar resultado_rodada1.mp4 resultado_rodada2.mp4

Para cada saida o relatorio diz, em portugues:
  - bytes identicos (sha256 do arquivo);
  - se for video/audio e o ffmpeg existir: conteudo identico (sha256 dos quadros decodificados e do PCM do audio),
    que ignora diferencas so de metadados do arquivo;
  - se diferirem: o PSNR medio entre as duas rodadas (quanto maior, mais parecidas; 'inf' = quadros identicos).
Resultado final por saida: IDENTICA (bytes), IDENTICA NO CONTEUDO ou DIFERENTE. Grava receita_hash.json.
Codigo de saida: 0 = todas identicas (bytes ou conteudo), 1 = alguma diferente, 2 = erro (comando falhou, saida ausente).

Lembrete honesto: nenhum projeto de difusao garante saida identica entre execucoes, GPUs, versoes ou quantizacoes;
este teste so mede o que acontece NA SUA MAQUINA, com a sua instalacao, nas condicoes em que voce rodou.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
EXT_MIDIA = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v", ".wav", ".mp3", ".flac", ".aac", ".m4a", ".ogg", ".gif"}


def achar_ffmpeg(arg: str | None) -> str | None:
    for cand in (arg, os.environ.get("FFMPEG")):
        if cand and shutil.which(cand):
            return shutil.which(cand)
    if shutil.which("ffmpeg"):
        return shutil.which("ffmpeg")
    try:
        import imageio_ffmpeg  # type: ignore

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:  # noqa: BLE001
        return None


def sha256_arquivo(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def hash_caminho(p: Path) -> str:
    """Arquivo: sha256 dos bytes. Pasta: sha256 da lista ordenada 'caminho relativo + sha256 de cada arquivo'."""
    if p.is_file():
        return sha256_arquivo(p)
    linhas = []
    for f in sorted(x for x in p.rglob("*") if x.is_file()):
        linhas.append(f"{f.relative_to(p).as_posix()}\t{sha256_arquivo(f)}")
    return hashlib.sha256("\n".join(linhas).encode()).hexdigest()


def tem_trilha(ffmpeg: str, p: Path) -> tuple[bool, bool]:
    r = subprocess.run([ffmpeg, "-hide_banner", "-i", str(p)], capture_output=True, text=True, errors="replace",
                       creationflags=CREATE_NO_WINDOW)
    return "Video:" in r.stderr, "Audio:" in r.stderr


def hash_conteudo(ffmpeg: str, p: Path) -> dict | None:
    """sha256 dos quadros decodificados (rgb24) e do PCM do audio. Ignora metadados do container."""
    if p.suffix.lower() not in EXT_MIDIA:
        return None
    tv, ta = tem_trilha(ffmpeg, p)
    out: dict = {}
    if tv:
        r = subprocess.run([ffmpeg, "-v", "error", "-i", str(p), "-map", "0:v:0", "-c:v", "rawvideo", "-pix_fmt", "rgb24",
                            "-f", "hash", "-hash", "sha256", "-"], capture_output=True, text=True, creationflags=CREATE_NO_WINDOW)
        m = re.search(r"SHA256=([0-9a-f]+)", r.stdout)
        out["quadros_sha256"] = m.group(1) if m else None
    if ta:
        r = subprocess.run([ffmpeg, "-v", "error", "-i", str(p), "-map", "0:a:0", "-c:a", "pcm_s16le", "-f", "hash",
                            "-hash", "sha256", "-"], capture_output=True, text=True, creationflags=CREATE_NO_WINDOW)
        m = re.search(r"SHA256=([0-9a-f]+)", r.stdout)
        out["audio_pcm_sha256"] = m.group(1) if m else None
    return out or None


def psnr_entre(ffmpeg: str, a: Path, b: Path) -> str | None:
    if a.suffix.lower() not in EXT_MIDIA or not tem_trilha(ffmpeg, a)[0] or not tem_trilha(ffmpeg, b)[0]:
        return None
    r = subprocess.run([ffmpeg, "-hide_banner", "-i", str(a), "-i", str(b), "-lavfi", "[0:v][1:v]psnr", "-f", "null", "-"],
                       capture_output=True, text=True, errors="replace", creationflags=CREATE_NO_WINDOW)
    m = re.search(r"PSNR .*?average:(\S+)", r.stderr)
    return m.group(1) if m else None


def montar_comando(cmd: list[str], usar_shell: bool):
    if usar_shell:
        return (subprocess.list2cmdline(cmd) if os.name == "nt" else " ".join(cmd)), True
    if os.name == "nt" and cmd and cmd[0].lower().endswith((".bat", ".cmd")):
        return ["cmd", "/c"] + cmd, False
    return cmd, False


def apagar(p: Path) -> None:
    if p.is_dir():
        shutil.rmtree(p, ignore_errors=True)
    elif p.exists():
        p.unlink()


def copiar(origem: Path, destino_dir: Path) -> Path:
    destino_dir.mkdir(parents=True, exist_ok=True)
    destino = destino_dir / origem.name
    if origem.is_dir():
        if destino.exists():
            shutil.rmtree(destino)
        shutil.copytree(origem, destino)
    else:
        shutil.copy2(origem, destino)
    return destino


def comparar_arquivos(ffmpeg: str | None, caminhos: list[Path]) -> dict:
    """Compara as copias (todas contra a primeira). Retorna o veredito."""
    hs = [hash_caminho(p) for p in caminhos]
    r: dict = {"arquivos": [str(p) for p in caminhos], "sha256_bytes": hs, "bytes_identicos": len(set(hs)) == 1,
               "tamanhos": [(p.stat().st_size if p.is_file() else None) for p in caminhos]}
    if r["bytes_identicos"]:
        r["resultado"] = "IDENTICA (bytes)"
        return r
    if ffmpeg and all(p.is_file() for p in caminhos):
        cs = [hash_conteudo(ffmpeg, p) for p in caminhos]
        if all(c is not None for c in cs):
            r["conteudo"] = cs
            r["conteudo_identico"] = all(c == cs[0] for c in cs) and all(v is not None for c in cs for v in c.values())
            if r["conteudo_identico"]:
                r["resultado"] = "IDENTICA NO CONTEUDO (quadros e audio decodificados iguais; so o arquivo difere)"
                return r
        r["psnr_medio_db_contra_a_1a"] = [None] + [psnr_entre(ffmpeg, caminhos[0], p) for p in caminhos[1:]]
    r["resultado"] = "DIFERENTE"
    return r


def main() -> int:
    ap = argparse.ArgumentParser(description="Roda um comando duas vezes e compara os sha256 das saidas (ou compara arquivos prontos).",
                                 usage="python receita_test_hash.py [opcoes] --saida ARQ -- comando ...   |   python receita_test_hash.py --comparar A B [C ...]")
    ap.add_argument("--saida", action="append", default=[], help="arquivo ou pasta produzido pelo comando (repita para varios)")
    ap.add_argument("--entrada", action="append", default=[], help="arquivo de entrada, so para registrar o sha256 (opcional)")
    ap.add_argument("--rotulo", default="", help="nome da etapa para constar no relatorio")
    ap.add_argument("--rodadas", type=int, default=2, help="numero de execucoes (padrao 2)")
    ap.add_argument("--pasta-trabalho", default="rodadas_hash", help="onde guardar as copias de cada rodada")
    ap.add_argument("--json", default="", help="relatorio JSON (padrao: <pasta-trabalho>/receita_hash.json)")
    ap.add_argument("--nao-limpar", action="store_true", help="nao apagar a saida antes de cada rodada")
    ap.add_argument("--shell", action="store_true", help="roda o comando por um shell (pipes/redirecionamentos)")
    ap.add_argument("--comparar", nargs="+", metavar="ARQ", help="so compara estes arquivos/pastas (2 ou mais), sem rodar nada")
    ap.add_argument("--ffmpeg", help="caminho do ffmpeg (opcional; so para o hash de conteudo e o PSNR)")
    ap.add_argument("comando", nargs=argparse.REMAINDER, help="-- comando e argumentos")
    a = ap.parse_args()
    cmd = a.comando[1:] if a.comando and a.comando[0] == "--" else a.comando
    ffmpeg = achar_ffmpeg(a.ffmpeg)
    trabalho = Path(a.pasta_trabalho)

    relatorio: dict = {"versao": 1, "ferramenta": "receita_test_hash.py", "rotulo": a.rotulo,
                       "data_hora": datetime.now().isoformat(timespec="seconds"),
                       "plataforma": f"{platform.system()} {platform.release()}, python {platform.python_version()}",
                       "ffmpeg": bool(ffmpeg), "entradas": []}
    for e in a.entrada:
        pe = Path(e)
        if pe.exists():
            relatorio["entradas"].append({"caminho": str(pe), "sha256": hash_caminho(pe)})
        else:
            print(f"AVISO: entrada nao encontrada: {pe}")

    # ------------------------------------------------ modo comparar
    if a.comparar:
        if len(a.comparar) < 2:
            ap.error("--comparar precisa de pelo menos 2 arquivos")
        pastas = [Path(x) for x in a.comparar]
        faltando = [str(p) for p in pastas if not p.exists()]
        if faltando:
            print("ERRO: nao achei:", ", ".join(faltando))
            return 2
        res = [comparar_arquivos(ffmpeg, pastas)]
        relatorio["modo"] = "comparar"
        relatorio["saidas"] = {"(arquivos informados)": res[0]}
    else:
        # -------------------------------------------- modo rodar
        if not cmd:
            ap.error("informe o comando depois de --  ou use --comparar")
        if not a.saida:
            ap.error("informe pelo menos uma --saida (arquivo ou pasta que o comando produz)")
        if a.rodadas < 2:
            ap.error("--rodadas precisa ser >= 2")
        saidas = [Path(s) for s in a.saida]
        relatorio["modo"] = "rodar"
        relatorio["comando"] = cmd
        relatorio["rodadas"] = []
        copias: dict[str, list[Path]] = {str(s): [] for s in saidas}
        comando, shell = montar_comando(cmd, a.shell)
        for n in range(1, a.rodadas + 1):
            for s in saidas:
                if not a.nao_limpar:
                    apagar(s)
                s.parent.mkdir(parents=True, exist_ok=True)
            print(f"\n=== rodada {n} de {a.rodadas}: {' '.join(cmd)}")
            t0 = time.time()
            try:
                rc = subprocess.run(comando, shell=shell).returncode
            except FileNotFoundError:
                print(f"ERRO: nao achei o programa '{cmd[0]}'.")
                return 2
            dur = time.time() - t0
            info_r = {"rodada": n, "codigo_saida": rc, "tempo_s": round(dur, 1), "saidas": {}}
            relatorio["rodadas"].append(info_r)
            if rc != 0:
                print(f"ERRO: o comando terminou com codigo {rc} na rodada {n}. Teste interrompido.")
                relatorio["erro"] = f"comando falhou na rodada {n} (codigo {rc})"
                _gravar(relatorio, a, trabalho)
                return 2
            for s in saidas:
                if not s.exists():
                    print(f"ERRO: a saida {s} nao foi criada na rodada {n}.")
                    relatorio["erro"] = f"saida {s} nao criada na rodada {n}"
                    _gravar(relatorio, a, trabalho)
                    return 2
                if s.is_file() and s.stat().st_mtime < t0 - 1:
                    print(f"AVISO: {s} parece mais antiga que o inicio da rodada {n} (nao foi recriada?).")
                    info_r.setdefault("avisos", []).append(f"{s} nao parece recriada")
                c = copiar(s, trabalho / f"rodada{n}")
                copias[str(s)].append(c)
                info_r["saidas"][str(s)] = hash_caminho(c)
            print(f"rodada {n}: ok em {dur:.1f} s")
        relatorio["saidas"] = {nome: comparar_arquivos(ffmpeg, lst) for nome, lst in copias.items()}
        res = list(relatorio["saidas"].values())

    # ------------------------------------------------ relatorio
    print("\n================ RESULTADO DO TESTE DE REPRODUTIBILIDADE ================")
    todas_ok = True
    for nome, r in relatorio["saidas"].items():
        print(f"\nSaida: {nome}")
        for p, h in zip(r["arquivos"], r["sha256_bytes"]):
            print(f"  sha256 {h[:16]}...  {p}")
        print(f"  bytes identicos: {'SIM' if r['bytes_identicos'] else 'NAO'}")
        if "conteudo_identico" in r:
            print(f"  quadros e audio decodificados identicos: {'SIM' if r['conteudo_identico'] else 'NAO'}")
        if r.get("psnr_medio_db_contra_a_1a") and any(x is not None for x in r["psnr_medio_db_contra_a_1a"][1:]):
            print("  PSNR medio contra a 1a rodada (dB; 'inf' = quadros identicos):", r["psnr_medio_db_contra_a_1a"][1:])
        print(f"  => {r['resultado']}")
        todas_ok &= r["resultado"].startswith("IDENTICA")
    if not ffmpeg:
        print("\n(ffmpeg nao encontrado: so foi possivel comparar bytes.)")
    sim_nao = "sim" if todas_ok else "nao"
    print(f"\nPara a tabela do LEIA-ME, coluna 'saida identica na 2a rodada': {sim_nao}")
    _gravar(relatorio, a, trabalho)
    return 0 if todas_ok else 1


def _gravar(relatorio: dict, a, trabalho: Path) -> None:
    destino = Path(a.json) if a.json else trabalho / "receita_hash.json"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(relatorio, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Relatorio: {destino}")


if __name__ == "__main__":
    sys.exit(main())
