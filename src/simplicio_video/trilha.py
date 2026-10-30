"""Trilha de arquivo do BRASA (etapa 1): arranjo por `cortes` e ducking em duas bandas sob a voz.

- `trilha.music.arquivo` + `trilha.music.cortes`: os trechos {de_s, ate_s, em_s, db?, passa_baixa_hz?} são recortados da
  fonte, ajustados em volume e passa-baixa e encadeados com crossfade (padrão 8 ms). Confere-se o em_s: é a posição de
  entrada do trecho na trilha de saída, já descontado o crossfade (o primeiro é 0). Erro de conta vira erro com o valor certo.
- `voz.ducking` (graves_db, agudos_db): baixa só as bandas abaixo de 250 Hz e acima de 2.5 kHz da trilha de arquivo nas
  janelas de voz. O meio não muda. duck_music_db e duck_sfx_db continuam no build.mjs, como antes.

ffmpeg faz o áudio; este módulo monta os filtros e confere os tempos. A trilha sintetizada (build.mjs) não passa por aqui.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

CROSSFADE_PADRAO_MS = 8.0
DUCKING_PADRAO = {"graves_db": -2.5, "agudos_db": -8.0}
CORTE_GRAVES_HZ = 250.0
CORTE_AGUDOS_HZ = 2500.0
RAMPA_DUCKING_S = 0.05  # entrada e saída do ducking: 50 ms, sem clique
SR = 48000
TOL_S = 0.001  # tolerância do em_s conferido e do arranjo contra o vídeo
ARRANJO_REL = "assets/audio/trilha/arranjo.wav"


def _ffmpeg(args: list[str]) -> None:
    p = subprocess.run(["ffmpeg", "-v", "error", "-y", *args], capture_output=True, text=True)
    if p.returncode != 0:
        raise SystemExit(f"trilha: ffmpeg falhou ({p.returncode})\n{(p.stderr or '')[-2000:]}")


def duracao_s(path: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True)
    if out.returncode != 0 or not out.stdout.strip():
        raise SystemExit(f"trilha: ffprobe não leu a duração de {path}")
    return float(out.stdout.strip())


def valida_cortes(cortes: list[dict], crossfade_ms: float = CROSSFADE_PADRAO_MS, duracao_fonte_s: float | None = None) -> list[float]:
    """Confere os trechos e devolve o em_s esperado de cada um. Levanta ValueError com o motivo."""
    if not cortes:
        raise ValueError("cortes: lista vazia (sem trechos não há trilha)")
    cf = crossfade_ms / 1000.0
    esperado: list[float] = []
    inicio = 0.0
    for i, c in enumerate(cortes):
        for k in ("de_s", "ate_s", "em_s"):
            if k not in c:
                raise ValueError(f"cortes[{i}]: falta {k}")
        de, ate, em = float(c["de_s"]), float(c["ate_s"]), float(c["em_s"])
        if de < 0:
            raise ValueError(f"cortes[{i}]: de_s negativo ({de})")
        if ate <= de:
            raise ValueError(f"cortes[{i}]: ate_s ({ate}) tem de ser maior que de_s ({de})")
        if duracao_fonte_s is not None and ate > duracao_fonte_s + TOL_S:
            raise ValueError(f"cortes[{i}]: ate_s ({ate}) passa do fim da fonte ({duracao_fonte_s:.3f} s)")
        if i > 0:
            anterior = cortes[i - 1]
            inicio = esperado[i - 1] + (float(anterior["ate_s"]) - float(anterior["de_s"])) - cf
        if ate - de <= cf:
            raise ValueError(f"cortes[{i}]: trecho de {ate - de:.3f} s é menor que o crossfade ({crossfade_ms} ms)")
        if abs(em - inicio) > TOL_S:
            raise ValueError(f"cortes[{i}]: em_s {em} não bate com a posição {inicio:.3f} s na trilha de saída "
                             f"(trechos encadeados com crossfade de {crossfade_ms} ms: o primeiro é 0)")
        esperado.append(inicio)
    return esperado


def duracao_arranjo_s(cortes: list[dict], crossfade_ms: float = CROSSFADE_PADRAO_MS) -> float:
    """Duração da trilha de saída: soma dos trechos menos um crossfade por junção."""
    soma = sum(float(c["ate_s"]) - float(c["de_s"]) for c in cortes)
    return soma - (len(cortes) - 1) * crossfade_ms / 1000.0


def filtro_arranjo(cortes: list[dict], crossfade_ms: float = CROSSFADE_PADRAO_MS) -> str:
    """filter_complex que recorta, ajusta e encadeia os trechos (saída: [out])."""
    n = len(cortes)
    partes = []
    pre = "[0:a]aformat=sample_fmts=fltp:channel_layouts=stereo"
    if n == 1:
        partes.append(f"{pre}[s0]")
    else:
        partes.append(f"{pre},asplit={n}" + "".join(f"[s{i}]" for i in range(n)))
    for i, c in enumerate(cortes):
        f = [f"atrim=start={float(c['de_s']):.6f}:end={float(c['ate_s']):.6f}", "asetpts=PTS-STARTPTS"]
        if "db" in c:
            f.append(f"volume={10 ** (float(c['db']) / 20):.6f}")
        if "passa_baixa_hz" in c:
            corte = float(c["passa_baixa_hz"])
            f += [f"lowpass=f={corte:g}", f"lowpass=f={corte:g}"]  # duas passagens: 4.ª ordem, 24 dB/oitava
        partes.append(f"[s{i}]{','.join(f)}[c{i}]")
    if n == 1:
        partes.append("[c0]anull[out]")
    elif crossfade_ms <= 0:
        partes.append("".join(f"[c{i}]" for i in range(n)) + f"concat=n={n}:v=0:a=1[out]")
    else:
        atual = "[c0]"
        for i in range(1, n):
            rotulo = "[out]" if i == n - 1 else f"[x{i}]"
            partes.append(f"{atual}[c{i}]acrossfade=d={crossfade_ms / 1000.0:.6f}:c1=tri:c2=tri{rotulo}")
            atual = rotulo
    return ";".join(partes)


def monta_arranjo(fonte: Path, cortes: list[dict], saida: Path, crossfade_ms: float = CROSSFADE_PADRAO_MS) -> dict:
    """Recorta e encadeia os trechos de `fonte` em `saida` (WAV 48 kHz estéreo PCM s16)."""
    valida_cortes(cortes, crossfade_ms)
    saida.parent.mkdir(parents=True, exist_ok=True)
    _ffmpeg(["-i", str(fonte), "-filter_complex", filtro_arranjo(cortes, crossfade_ms), "-map", "[out]",
             "-ar", str(SR), "-c:a", "pcm_s16le", str(saida)])
    return {"saida": saida, "duracao_s": round(duracao_arranjo_s(cortes, crossfade_ms), 6), "crossfade_ms": crossfade_ms,
            "trechos": len(cortes)}


def converte(fonte: Path, saida: Path) -> dict:
    """Trilha de arquivo sem cortes: só a conversão para WAV 48 kHz estéreo PCM s16."""
    saida.parent.mkdir(parents=True, exist_ok=True)
    _ffmpeg(["-i", str(fonte), "-map", "0:a:0", "-ar", str(SR), "-ac", "2", "-c:a", "pcm_s16le", str(saida)])
    return {"saida": saida, "duracao_s": round(duracao_s(saida), 6), "crossfade_ms": 0.0, "trechos": 0}


def _janela_expr(janelas: list[tuple[float, float]], rampa_s: float) -> str:
    """Expressão ffmpeg do ganho de voz w(t): 1 dentro das janelas, 0 fora, com rampas de rampa_s nas bordas."""
    termos = [f"clip((t-{a:.6f})/{rampa_s:.6f},0,1)*clip(({b:.6f}-t)/{rampa_s:.6f},0,1)" for a, b in janelas]
    return f"min(1,{'+'.join(termos)})"


def _passa(tipo: str, freq: float) -> str:
    """Butterworth de 4.ª ordem de FASE ZERO (ida e volta com areverse, como filtfilt): o ganho da banda sai exato nos tons
    e o corte fica em -3 dB na frequência pedida. Um filtro causal girava a fase e errava o ganho (40 Hz saía em -2.1 dB)."""
    f = f"{freq:g}"
    ida = f"{tipo}=f={f}:width_type=q:width=0.5412,{tipo}=f={f}:width_type=q:width=1.3066"
    return f"{ida},areverse,{ida},areverse"


def aplica_ducking(entrada: Path, saida: Path, janelas: list[tuple[float, float]], graves_db: float = DUCKING_PADRAO["graves_db"],
                   agudos_db: float = DUCKING_PADRAO["agudos_db"], rampa_s: float = RAMPA_DUCKING_S) -> dict:
    """Ducking em duas bandas: abaixo de 250 Hz baixa graves_db e acima de 2.5 kHz baixa agudos_db, só dentro das janelas
    de voz (em segundos da trilha). O meio não muda. Saída: WAV 48 kHz estéreo PCM s16."""
    for a, b in janelas:
        if b <= a:
            raise ValueError(f"janela de voz inválida: {a}..{b}")
    g_graves = 10 ** (graves_db / 20.0)
    g_agudos = 10 ** (agudos_db / 20.0)
    w = _janela_expr(janelas, rampa_s) if janelas else "0"
    # a banda é somada à entrada com o ganho (G-1)*w, negativo: a entrada fora da janela passa intacta
    filtro = (
        "[0:a]aformat=sample_fmts=fltp:channel_layouts=stereo,asplit=3[in][lo][hi];"
        f"[lo]{_passa('lowpass', CORTE_GRAVES_HZ)},volume=volume='({g_graves:.6f}-1)*{w}':eval=frame[dl];"
        f"[hi]{_passa('highpass', CORTE_AGUDOS_HZ)},volume=volume='({g_agudos:.6f}-1)*{w}':eval=frame[dh];"
        "[in][dl][dh]amix=inputs=3:normalize=0:duration=first:dropout_transition=0[out]"
    )
    saida.parent.mkdir(parents=True, exist_ok=True)
    _ffmpeg(["-i", str(entrada), "-filter_complex", filtro, "-map", "[out]", "-ar", str(SR), "-c:a", "pcm_s16le", str(saida)])
    return {"saida": saida, "janelas": len(janelas), "graves_db": graves_db, "agudos_db": agudos_db, "rampa_s": rampa_s}


def janelas_de_voz(c, lock: dict | None) -> list[tuple[float, float]]:
    """Janelas de voz na trilha: início da fala e duração do take (timing.lock.json). Vazio sem voz."""
    v = c.data["voz"]
    if not v.get("habilitada", True) or not lock:
        return []
    janelas = []
    for linha in c.lines():
        m = lock.get("lines", {}).get(linha["id"])
        if m:
            janelas.append((float(linha["t"]), float(linha["t"]) + float(m["dur_s"])))
    return janelas


def prepara(c, workdir: Path, lock: dict | None) -> str:
    """Monta a trilha de arquivo do contrato dentro do workdir e devolve o caminho relativo a ele (vai para o spec.json)."""
    music = c.data["trilha"]["music"]
    fonte = c.rel(music["arquivo"])
    if not fonte.is_file():
        raise SystemExit(f"trilha.music.arquivo não encontrado: {music['arquivo']}")
    cortes = music.get("cortes")
    cf = float(music.get("crossfade_ms", CROSSFADE_PADRAO_MS))
    dst = workdir / ARRANJO_REL
    if cortes:
        monta_arranjo(fonte, cortes, dst, cf)
    else:
        converte(fonte, dst)
    if "ducking" in c.data["voz"]:  # voz.ducking presente (mesmo {}): ducking em duas bandas nas janelas de voz
        janelas = janelas_de_voz(c, lock)
        if janelas:
            ducking = {**DUCKING_PADRAO, **c.data["voz"]["ducking"]}
            tmp = dst.with_name("arranjo-ducked.wav")
            aplica_ducking(dst, tmp, janelas, ducking["graves_db"], ducking["agudos_db"])
            tmp.replace(dst)
    video_s = float(c.data["formato"]["duracao_s"])
    arranjo_s = duracao_s(dst)
    if arranjo_s + 0.02 < video_s:
        raise SystemExit(f"trilha: o arranjo tem {arranjo_s:.3f} s e o vídeo {video_s} s: alongue os cortes ou o arquivo")
    return ARRANJO_REL
