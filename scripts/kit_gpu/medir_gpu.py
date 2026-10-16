"""Mede tempo, pico de VRAM, uso da GPU e pico de RAM do sistema enquanto um comando roda.

So usa a biblioteca padrao do Python. Funciona no Windows (nvidia-smi + GlobalMemoryStatusEx) e no Linux.
Se nao houver nvidia-smi (sem placa NVIDIA ou sem driver), continua medindo tempo e RAM e deixa as colunas
de VRAM vazias, sem dar erro.

Dois modos:

  1) Comando que termina sozinho (script, ffmpeg, python ...):
       python medir_gpu.py --etapa "vace_480p" --modelo "VACE 1.3B" --resolucao 480x848 --quadros 75 -- python meu_script.py
     Tudo depois de "--" e o comando. Para um .bat use:  -- cmd /c meu.bat

  2) ComfyUI (o servidor nao termina sozinho), modo manual: o script mede ate voce apertar ENTER.
       python medir_gpu.py --manual --etapa "animate_gguf_q4"
     Deixe rodando, va ao ComfyUI, rode o fluxo, e quando o video aparecer volte aqui e aperte ENTER.
     O tempo "oficial" do ComfyUI e a linha "Prompt executed in X seconds" do console dele; use medir_gpu
     principalmente para os picos de VRAM e RAM.

Cada execucao acrescenta uma linha em medidas_gpu.csv (separador ponto e virgula e decimal com virgula,
para abrir direto no Excel em portugues; use --formato-en para virgula/ponto). Use --serie para gravar tambem
uma linha por segundo (para ver quando a VRAM estourou).

Limites honestos: a RAM medida e a do sistema inteiro (feche navegador e outros programas antes); no Windows
o nvidia-smi nao separa VRAM por processo, entao a VRAM tambem inclui o que o Windows ja usa na placa.
"""
from __future__ import annotations

import argparse
import csv
import ctypes
import os
import platform
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

COLUNAS = ["data_hora", "etapa", "modelo", "resolucao", "quadros", "comando", "codigo_saida", "tempo_total_s",
           "nvidia_smi", "gpu_nome", "vram_total_mb", "vram_base_mb", "vram_pico_mb", "vram_pico_delta_mb",
           "gpu_uso_medio_pct", "gpu_uso_pico_pct", "ram_total_gb", "ram_base_gb", "ram_pico_gb",
           "ram_pico_delta_gb", "amostras", "plataforma", "observacao"]


# ---------------------------------------------------------------- leitura de RAM e GPU
def achar_nvidia_smi() -> str | None:
    achado = shutil.which("nvidia-smi")
    if achado:
        return achado
    for cand in (r"C:\Windows\System32\nvidia-smi.exe", r"C:\Program Files\NVIDIA Corporation\NVSMI\nvidia-smi.exe"):
        if os.path.isfile(cand):
            return cand
    return None


def ram_sistema() -> tuple[float, float] | None:
    """Retorna (total_bytes, em_uso_bytes) da RAM do sistema inteiro, ou None se nao der para ler."""
    try:
        if sys.platform.startswith("win"):
            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("sullAvailExtendedVirtual", ctypes.c_ulonglong)]
            st = MEMORYSTATUSEX()
            st.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st)):  # type: ignore[attr-defined]
                return None
            return float(st.ullTotalPhys), float(st.ullTotalPhys - st.ullAvailPhys)
        if os.path.exists("/proc/meminfo"):
            d: dict[str, int] = {}
            with open("/proc/meminfo", encoding="utf8") as f:
                for linha in f:
                    k, _, v = linha.partition(":")
                    d[k] = int(v.split()[0]) * 1024
            return float(d["MemTotal"]), float(d["MemTotal"] - d["MemAvailable"])
    except Exception:  # noqa: BLE001
        return None
    return None


def _num(txt: str) -> float | None:
    try:
        return float(txt.strip())
    except ValueError:
        return None  # "[N/A]", "[Not Supported]"


def ler_gpus(smi: str) -> list[dict] | None:
    """Uma consulta ao nvidia-smi. Retorna lista de GPUs NVIDIA ou None se falhou."""
    try:
        r = subprocess.run([smi, "--query-gpu=index,name,memory.used,memory.total,utilization.gpu",
                            "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=8,
                           creationflags=CREATE_NO_WINDOW)
    except Exception:  # noqa: BLE001
        return None
    if r.returncode != 0 or not r.stdout.strip():
        return None
    gpus = []
    for linha in r.stdout.strip().splitlines():
        try:
            idx, resto = linha.split(",", 1)
            nome, usada, total, uso = resto.rsplit(",", 3)
            gpus.append({"idx": int(idx), "nome": nome.strip(), "usada": _num(usada), "total": _num(total), "uso": _num(uso)})
        except ValueError:
            continue
    return gpus or None


# ---------------------------------------------------------------- amostrador
class Amostrador(threading.Thread):
    def __init__(self, intervalo: float, smi: str | None):
        super().__init__(daemon=True)
        self.intervalo, self.smi = intervalo, smi
        self.parar = threading.Event()
        self.amostras: list[dict] = []
        self.falhas_smi = 0

    def amostrar(self) -> dict:
        s: dict = {"t": time.monotonic()}
        ram = ram_sistema()
        s["ram_usada"] = ram[1] if ram else None
        s["ram_total"] = ram[0] if ram else None
        s["gpus"] = None
        if self.smi:
            g = ler_gpus(self.smi)
            if g is None:
                self.falhas_smi += 1
            s["gpus"] = g
        return s

    def run(self) -> None:
        while not self.parar.is_set():
            ini = time.monotonic()
            self.amostras.append(self.amostrar())
            resto = self.intervalo - (time.monotonic() - ini)
            self.parar.wait(max(0.05, resto))
        self.amostras.append(self.amostrar())  # amostra final


# ---------------------------------------------------------------- formatacao
class Fmt:
    def __init__(self, virgula: bool):
        self.virgula = virgula

    def n(self, v: float | None, casas: int = 1) -> str:
        if v is None:
            return ""
        s = f"{v:.{casas}f}"
        return s.replace(".", ",") if self.virgula else s


def resumir(amostras: list[dict], t0: float, t1: float, gpu_escolhida: int | None, base: dict | None) -> dict:
    res: dict = {"amostras": len(amostras)}
    # RAM do sistema
    rams = [a["ram_usada"] for a in amostras if a["ram_usada"] is not None]
    tot = next((a["ram_total"] for a in amostras if a["ram_total"] is not None), None)
    if rams and tot:
        base_ram = base["ram_usada"] if base and base["ram_usada"] is not None else rams[0]
        res.update(ram_total_gb=tot / 2**30, ram_base_gb=base_ram / 2**30, ram_pico_gb=max(rams) / 2**30,
                   ram_pico_delta_gb=(max(rams) - base_ram) / 2**30)
    # GPU
    por_gpu: dict[int, list[dict]] = {}
    for a in amostras:
        for g in a["gpus"] or []:
            por_gpu.setdefault(g["idx"], []).append(g)
    if por_gpu:
        if gpu_escolhida is None or gpu_escolhida not in por_gpu:
            gpu_escolhida = max(por_gpu, key=lambda i: max((x["usada"] or 0) for x in por_gpu[i]))
        lst = por_gpu[gpu_escolhida]
        usadas = [x["usada"] for x in lst if x["usada"] is not None]
        usos = [x["uso"] for x in lst if x["uso"] is not None]
        base_g = None
        if base and base["gpus"]:
            base_g = next((x["usada"] for x in base["gpus"] if x["idx"] == gpu_escolhida), None)
        if base_g is None and usadas:
            base_g = usadas[0]
        res.update(gpu_idx=gpu_escolhida, gpu_nome=lst[0]["nome"], vram_total_mb=lst[0]["total"])
        if usadas:
            res.update(vram_base_mb=base_g, vram_pico_mb=max(usadas), vram_pico_delta_mb=max(usadas) - (base_g or 0))
        if usos:
            res.update(gpu_uso_medio_pct=sum(usos) / len(usos), gpu_uso_pico_pct=max(usos))
        if len(por_gpu) > 1:
            res["outras_gpus_nvidia"] = {i: max((x["usada"] or 0) for x in v) for i, v in por_gpu.items() if i != gpu_escolhida}
    return res


def montar_comando(cmd: list[str], usar_shell: bool) -> tuple[list[str] | str, bool]:
    if usar_shell:
        return subprocess.list2cmdline(cmd) if os.name == "nt" else " ".join(cmd), True
    if os.name == "nt" and cmd and cmd[0].lower().endswith((".bat", ".cmd")):
        return ["cmd", "/c"] + cmd, False
    return cmd, False


def main() -> int:
    ap = argparse.ArgumentParser(description="Mede VRAM, GPU, RAM e tempo de um comando (ou de uma rodada manual no ComfyUI).",
                                 usage="python medir_gpu.py [opcoes] -- comando ...   |   python medir_gpu.py --manual [opcoes]")
    ap.add_argument("--etapa", default="", help="nome da etapa (ex.: vace_480p)")
    ap.add_argument("--modelo", default="", help="modelo (so para constar na linha do CSV)")
    ap.add_argument("--resolucao", default="", help="resolucao (so para constar)")
    ap.add_argument("--quadros", default="", help="quadros (so para constar)")
    ap.add_argument("--observacao", default="", help="texto livre para a ultima coluna")
    ap.add_argument("--csv", default="medidas_gpu.csv", help="arquivo CSV de resultados (acrescenta uma linha)")
    ap.add_argument("--serie", default="", help="CSV opcional com uma linha por amostra")
    ap.add_argument("--intervalo", type=float, default=1.0, help="segundos entre amostras (padrao 1)")
    ap.add_argument("--gpu", type=int, default=None, help="indice da GPU NVIDIA a reportar (padrao: a que mais usou VRAM)")
    ap.add_argument("--manual", action="store_true", help="mede ate voce apertar ENTER (para o ComfyUI)")
    ap.add_argument("--shell", action="store_true", help="roda o comando por um shell (para pipes e redirecionamentos)")
    ap.add_argument("--tempo-max", type=float, default=0, help="mata o comando depois de N segundos (0 = sem limite)")
    ap.add_argument("--formato-en", action="store_true", help="CSV com virgula e ponto decimal (em vez de ; e virgula)")
    ap.add_argument("comando", nargs=argparse.REMAINDER, help="-- comando e argumentos")
    a = ap.parse_args()
    cmd = a.comando[1:] if a.comando and a.comando[0] == "--" else a.comando
    if not a.manual and not cmd:
        ap.error("informe o comando depois de --  ou use --manual")
    if a.manual and cmd:
        ap.error("--manual nao combina com comando")

    fmt = Fmt(virgula=not a.formato_en)
    smi = achar_nvidia_smi()
    print("== medir_gpu ==")
    print(f"nvidia-smi: {smi or 'NAO ENCONTRADO (a VRAM nao sera medida; tempo e RAM continuam)'}")
    if smi and ler_gpus(smi) is None:
        print("AVISO: o nvidia-smi existe mas nao respondeu; a VRAM pode ficar vazia (driver NVIDIA instalado e GPU ativa?).")

    amostrador = Amostrador(a.intervalo, smi)
    base = amostrador.amostrar()
    inicio_dh = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    codigo: str | int = ""
    obs = a.observacao
    t0 = time.monotonic()
    amostrador.start()
    try:
        if a.manual:
            print("\nMedindo. Rode o fluxo no ComfyUI. Quando terminar, volte aqui e aperte ENTER (Ctrl+C tambem encerra).")
            try:
                input()
                codigo = "manual"
            except (KeyboardInterrupt, EOFError):
                codigo = "manual"
        else:
            comando, shell = montar_comando(cmd, a.shell)
            print("\nComando:", comando if shell else subprocess.list2cmdline(comando) if os.name == "nt" else " ".join(comando))
            try:
                proc = subprocess.Popen(comando, shell=shell)
            except FileNotFoundError:
                print(f"ERRO: nao achei o programa '{cmd[0]}'. Confira o nome/caminho (o ComfyUI usa python_embeded\\python.exe).")
                codigo = "erro_ao_iniciar"
                obs = (obs + " nao_achou_programa").strip()
                proc = None
            except OSError as e:
                print(f"ERRO ao iniciar o comando: {e}")
                codigo = "erro_ao_iniciar"
                obs = (obs + f" erro_ao_iniciar:{e.__class__.__name__}").strip()
                proc = None
            if proc is not None:
                try:
                    codigo = proc.wait(timeout=a.tempo_max or None)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
                    codigo = "tempo_max"
                    print(f"AVISO: passou de {a.tempo_max:g} s; comando encerrado.")
                except KeyboardInterrupt:
                    proc.terminate()
                    try:
                        proc.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                    codigo = "interrompido"
    finally:
        t1 = time.monotonic()
        amostrador.parar.set()
        amostrador.join(timeout=15)

    tempo = t1 - t0
    r = resumir(amostrador.amostras, t0, t1, a.gpu, base)
    if smi and amostrador.falhas_smi:
        obs = (obs + f" nvidia_smi_falhou_{amostrador.falhas_smi}x").strip()

    linha = {
        "data_hora": inicio_dh, "etapa": a.etapa, "modelo": a.modelo, "resolucao": a.resolucao, "quadros": a.quadros,
        "comando": "(manual)" if a.manual else " ".join(cmd), "codigo_saida": codigo,
        "tempo_total_s": fmt.n(tempo, 1), "nvidia_smi": "sim" if r.get("vram_pico_mb") is not None else "nao",
        "gpu_nome": r.get("gpu_nome", ""), "vram_total_mb": fmt.n(r.get("vram_total_mb"), 0),
        "vram_base_mb": fmt.n(r.get("vram_base_mb"), 0), "vram_pico_mb": fmt.n(r.get("vram_pico_mb"), 0),
        "vram_pico_delta_mb": fmt.n(r.get("vram_pico_delta_mb"), 0),
        "gpu_uso_medio_pct": fmt.n(r.get("gpu_uso_medio_pct"), 0), "gpu_uso_pico_pct": fmt.n(r.get("gpu_uso_pico_pct"), 0),
        "ram_total_gb": fmt.n(r.get("ram_total_gb"), 1), "ram_base_gb": fmt.n(r.get("ram_base_gb"), 1),
        "ram_pico_gb": fmt.n(r.get("ram_pico_gb"), 1), "ram_pico_delta_gb": fmt.n(r.get("ram_pico_delta_gb"), 1),
        "amostras": r["amostras"], "plataforma": f"{platform.system()} {platform.release()}", "observacao": obs,
    }

    # grava a linha no CSV (se o cabecalho do arquivo existente for outro, usa um arquivo novo)
    delim = "," if a.formato_en else ";"
    destino = Path(a.csv)
    if destino.exists() and destino.stat().st_size > 0:
        with open(destino, encoding="utf-8-sig") as f:
            cab = f.readline().strip().split(delim)
        if cab != COLUNAS:
            novo = destino.with_name(destino.stem + "_novo" + destino.suffix)
            print(f"AVISO: {destino} tem outras colunas; gravando em {novo}")
            destino = novo
    novo_arquivo = not destino.exists() or destino.stat().st_size == 0
    with open(destino, "a", newline="", encoding="utf-8-sig" if novo_arquivo else "utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUNAS, delimiter=delim)
        if novo_arquivo:
            w.writeheader()
        w.writerow(linha)

    if a.serie:
        t_ini = amostrador.amostras[0]["t"] if amostrador.amostras else t0
        gi = r.get("gpu_idx")
        nova = not Path(a.serie).exists()
        with open(a.serie, "a", newline="", encoding="utf-8-sig" if nova else "utf-8") as f:
            w = csv.writer(f, delimiter=delim)
            if nova:
                w.writerow(["etapa", "segundos", "vram_usada_mb", "gpu_uso_pct", "ram_usada_gb"])
            for s in amostrador.amostras:
                g = next((x for x in (s["gpus"] or []) if x["idx"] == gi), None) if gi is not None else None
                w.writerow([a.etapa, fmt.n(s["t"] - t_ini, 1), fmt.n(g["usada"], 0) if g else "", fmt.n(g["uso"], 0) if g else "",
                            fmt.n(s["ram_usada"] / 2**30, 2) if s["ram_usada"] is not None else ""])

    # resumo em portugues
    print(f"\n== RESULTADO{(' da etapa ' + repr(a.etapa)) if a.etapa else ''} ==")
    print(f"codigo de saida: {codigo}")
    print(f"tempo total: {fmt.n(tempo, 1)} s")
    if r.get("vram_pico_mb") is not None:
        pct = 100 * r["vram_pico_mb"] / r["vram_total_mb"] if r.get("vram_total_mb") else None
        print(f"VRAM ({r['gpu_nome']}, GPU {r['gpu_idx']}): base {fmt.n(r['vram_base_mb'], 0)} MB, pico {fmt.n(r['vram_pico_mb'], 0)} MB"
              + (f" de {fmt.n(r['vram_total_mb'], 0)} MB ({fmt.n(pct, 0)}%)" if pct is not None else ""))
        if r.get("gpu_uso_medio_pct") is not None:
            print(f"uso da GPU: medio {fmt.n(r['gpu_uso_medio_pct'], 0)}%, pico {fmt.n(r['gpu_uso_pico_pct'], 0)}%")
        if pct is not None and pct >= 95:
            print("ATENCAO: a VRAM chegou perto do limite. Se deu erro de memoria, veja 'Se faltar VRAM' no LEIA-ME.")
        if r.get("outras_gpus_nvidia"):
            print("Outras GPUs NVIDIA vistas (pico de VRAM, MB):", r["outras_gpus_nvidia"])
    else:
        print("VRAM: nao medida (sem nvidia-smi ou sem resposta dele).")
    if r.get("ram_pico_gb") is not None:
        print(f"RAM do sistema: base {fmt.n(r['ram_base_gb'], 1)} GB, pico {fmt.n(r['ram_pico_gb'], 1)} GB "
              f"(+{fmt.n(r['ram_pico_delta_gb'], 1)} GB) de {fmt.n(r['ram_total_gb'], 1)} GB")
        if r["ram_pico_gb"] >= 0.92 * r["ram_total_gb"]:
            print("ATENCAO: a RAM chegou perto do total; o Windows passa a usar o disco (arquivo de paginacao) e fica muito lento.")
    else:
        print("RAM: nao medida neste sistema.")
    print(f"Linha gravada em: {destino}")
    print("\nPara colar na tabela do LEIA-ME:")
    vram_txt = f"{fmt.n(r.get('vram_pico_mb'), 0)} MB" if r.get("vram_pico_mb") is not None else "n/d"
    ram_txt = f"{fmt.n(r.get('ram_pico_gb'), 1)} GB" if r.get("ram_pico_gb") is not None else "n/d"
    print(f"| {a.etapa} | {a.modelo} | {a.resolucao} | {a.quadros} | {fmt.n(tempo, 0)} s | {vram_txt} | "
          f"{ram_txt} | (sim/nao) | (sim/nao) |")
    return 0 if codigo in (0, "manual") else 1


if __name__ == "__main__":
    sys.exit(main())
