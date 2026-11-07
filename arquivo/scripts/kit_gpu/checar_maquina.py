"""Confere a maquina (GPU, VRAM, RAM, disco, CUDA, Python, ffmpeg) para o teste de troca de personagem.

Uso:  python checar_maquina.py
Nao instala nada, nao usa a internet e nao le arquivos pessoais. Imprime um texto curto para colar no chat.
Funciona em Windows, Linux e macOS com Python 3.8+.
"""
from __future__ import annotations

import platform
import shutil
import subprocess
import sys


def run(cmd: list[str]) -> str:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        return (r.stdout or r.stderr).strip()
    except Exception as e:  # noqa: BLE001
        return f"indisponivel ({type(e).__name__})"


def ram_gb() -> str:
    try:
        if sys.platform.startswith("win"):
            # o wmic foi removido de versoes novas do Windows 11; GlobalMemoryStatusEx funciona em todas
            import ctypes

            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("sullAvailExtendedVirtual", ctypes.c_ulonglong)]

            st = MEMORYSTATUSEX()
            st.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st)):  # type: ignore[attr-defined]
                return f"{st.ullTotalPhys / 2**30:.1f}"
            out = run(["wmic", "computersystem", "get", "TotalPhysicalMemory", "/value"])
            val = [x for x in out.split("=") if x.strip().isdigit()]
            return f"{int(val[0]) / 2**30:.1f}" if val else "?"
        if sys.platform == "darwin":
            return f"{int(run(['sysctl', '-n', 'hw.memsize'])) / 2**30:.1f}"
        with open("/proc/meminfo", encoding="utf8") as f:
            for line in f:
                if line.startswith("MemTotal"):
                    return f"{int(line.split()[1]) / 2**20:.1f}"
    except Exception:  # noqa: BLE001
        pass
    return "?"


def main() -> int:
    print("== MAQUINA ==")
    print("sistema:", platform.system(), platform.release(), platform.machine())
    print("python:", sys.version.split()[0])
    print("cpu:", platform.processor() or "?", "| nucleos logicos:", __import__("os").cpu_count())
    print("ram_gb:", ram_gb())
    du = shutil.disk_usage(".")
    print(f"disco livre nesta pasta: {du.free / 2**30:.0f} GB de {du.total / 2**30:.0f} GB")
    print("\n== GPU ==")
    if sys.platform.startswith("win"):
        # lista TODAS as placas de video que o Windows enxerga (notebook com "Varias GPUs": integrada + dedicada)
        print("placas de video vistas pelo Windows (nome | driver):")
        print(run(["powershell", "-NoProfile", "-Command",
                   "Get-CimInstance Win32_VideoController | ForEach-Object { '  ' + $_.Name + ' | driver ' + $_.DriverVersion }"]))
    smi = shutil.which("nvidia-smi")
    if smi:
        print(run([smi, "--query-gpu=name,memory.total,memory.used,driver_version,compute_cap", "--format=csv"]))
        for linha in run([smi]).splitlines():
            if "CUDA Version" in linha:
                print(linha.strip())
    else:
        print("nvidia-smi nao encontrado (sem driver NVIDIA no PATH, ou GPU AMD/Intel/Apple)")
    print("\n== FERRAMENTAS ==")
    for nome in ("ffmpeg", "ffprobe", "git", "uv", "conda"):
        print(f"{nome}:", shutil.which(nome) or "nao encontrado")
    try:
        import torch  # type: ignore

        print("torch:", torch.__version__, "| cuda:", torch.cuda.is_available(),
              "| cuda do torch:", torch.version.cuda)
        if torch.cuda.is_available():
            p = torch.cuda.get_device_properties(0)
            print(f"torch ve a GPU: {p.name}, {p.total_memory / 2**30:.1f} GB")
    except ImportError:
        print("torch: nao instalado (tudo bem)")
    print("\nCole esta saida inteira no chat.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
