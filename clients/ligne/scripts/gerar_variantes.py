"""Gera os contratos das variantes do padrão pov-showcase (video-02..05) a partir do contrato do video-01 (v4).

Uso (na raiz do repo): python3 clients/ligne/scripts/gerar_variantes.py
Faz os recortes de rosto (HD) a partir das pranchas em coleta/showcase/ e escreve clients/ligne/video-NN-*/contract.yaml + legenda.md.
"""
import copy
import subprocess
from pathlib import Path

import yaml

L = Path(__file__).resolve().parents[1]
SHOW = L / "coleta" / "showcase"
BASE = yaml.safe_load((L / "video-01-pov-wesley" / "contract.yaml").read_text(encoding="utf-8"))

# (id do showcase, arquivo da prancha-mestra, recorte (x0,y0,x1,y1) em px da prancha, nome do rosto)
ROSTOS = {
    "polo": ("8a6793a20cb5b29a19d73a25", "step-1-master-chart.jpg", (190, 176, 610, 716)),
    "bruna7": ("2b922b7be026b1aa24d14c5c", "step-1-master-chart.jpg", (51, 242, 491, 802)),
    "bruna4": ("556d34236975a9d0c1a1e816", "step-1-master-chart.jpg", (463, 10, 923, 600)),
    "amanda": ("61e9639f324a1261405b2342", "signature-board.jpg", (50, 22, 350, 406)),
}


def rosto_hd(slug):
    sid, arq, (x0, y0, x1, y1) = ROSTOS[slug]
    out = SHOW / sid / "recortes" / f"rosto-{slug}-hd.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    w, h = x1 - x0, y1 - y0
    vf = f"crop={w}:{h}:{x0}:{y0},scale=1500:-1:flags=lanczos,unsharp=5:5:0.7:5:5:0.0"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(SHOW / sid / arq), "-vf", vf, str(out)], check=True)
    return out


def tira_pranchas(c):
    c["assets"] = []
    return c


def sete_pranchas(sid):
    base = f"../coleta/showcase/{sid}"
    nomes = ["master-chart", "makeup", "colorimetry", "top-comparison", "hair", "accessories", "complete-looks"]
    return [{"arquivo": f"{base}/step-{i}-{n}.jpg", "destino": f"assets/client/prancha-{i}.jpg"} for i, n in enumerate(nomes, 1)]


def quatro_pranchas(sid):
    base = f"../coleta/showcase/{sid}"
    nomes = ["master-chart", "makeup", "colorimetry", "top-comparison"]
    return [{"arquivo": f"{base}/step-{i}-{n}.jpg", "destino": f"assets/client/prancha-{i}.jpg"} for i, n in enumerate(nomes, 1)]


def cena(c, sid):
    return next(x for x in c["cenas"] if x["id"] == sid)


def board(c, sid, image, zoom, x0, y0, x1, y1, aspect=None):
    p = cena(c, sid)["motion"][0]["params"]
    p.update({"image": f"assets/client/{image}", "zoom": zoom, "x0": x0, "y0": y0, "x1": x1, "y1": y1})
    if aspect is not None:
        p["aspect"] = aspect
    return p


def monta(slug, pasta, titulo, hook, assets, ajusta=None, close_board="prancha-2.jpg"):
    c = copy.deepcopy(BASE)
    sid, _, _ = ROSTOS[slug]
    rosto = rosto_hd(slug)
    c["campanha"]["id"] = f"POV_Consultoria_{slug}"
    c["campanha"]["titulo"] = titulo
    c["assets"] = [{"arquivo": f"../coleta/showcase/{sid}/recortes/{rosto.name}", "destino": "assets/client/rosto.png"}] + assets
    s1 = cena(c, "s1")
    s1["motion"][0]["params"]["image"] = "assets/client/rosto.png"
    s1["motion"][0]["params"]["text"] = hook
    s1["tela"] = [hook]
    s8 = cena(c, "s8")["motion"][0]["params"]
    s8["portrait"] = "assets/client/rosto.png"
    s8["board"] = f"assets/client/{close_board}"
    if ajusta:
        ajusta(c)
    for ce in c["cenas"]:
        if ce["papel"] == "prova":
            ce["tela"] = [f"prancha · {ce['id']}"]
    c["saida"]["arquivo"] = f"out/ligne-pov-{pasta.split('-', 2)[2]}-v1-silencioso.mp4"
    d = L / pasta
    (d / "out").mkdir(parents=True, exist_ok=True)
    cab = (
        f"# simplicio.video-contract/v1 — Ligne · {pasta} · Reels 26 s, 9:16 (padrão pov-showcase v4, ver video-01-pov-wesley/revisao-referencia.md).\n"
        f"# Gerado por clients/ligne/scripts/gerar_variantes.py; imagens de coleta/showcase/{sid}. Sem números da página; sem voz; trilha do motor (a faixa do post original é colocada depois do render).\n"
    )
    (d / "contract.yaml").write_text(cab + yaml.safe_dump(c, sort_keys=False, allow_unicode=True, width=1000), encoding="utf-8")
    (d / "legenda.md").write_text(
        f"# Legenda — Ligne · {pasta}\n\nConta: @useligne · Formato: Reels 9:16, 26 s · Arquivo: `out/ligne-pov-{pasta.split('-', 2)[2]}-v1.mp4`\n\n"
        'Regra do Wesley (18/10/2026): toda legenda termina com "Comente aqui".\n\n```\n'
        f"{hook} 😅\n\nNa Ligne a consultoria é pensada pra você: cores que te valorizam, maquiagem, cabelo, acessórios e looks completos.\n\n"
        'ligne.site\n\nComente aqui "EU QUERO" se você também quer a sua! 👇✨\n```\n',
        encoding="utf-8",
    )
    print("ok", pasta)


def bruna4(c):
    # 4 pranchas para 6 cenas: pranchas 1 e 3 voltam mais perto (zoom 2,2) na metade de baixo
    board(c, "s3", "prancha-3.jpg", 1.4, 0.35, 0.3, 0.65, 0.7)
    board(c, "s4", "prancha-4.jpg", 1.4, 0.4, 0.25, 0.6, 0.7)
    board(c, "s5", "prancha-2.jpg", 1.4, 0.65, 0.3, 0.35, 0.75)
    board(c, "s6", "prancha-1.jpg", 2.2, 0.3, 0.8, 0.7, 0.8)
    board(c, "s7", "prancha-3.jpg", 2.2, 0.7, 0.85, 0.3, 0.85)


def amanda(c):
    board(c, "s2", "prancha-1.jpg", 1.8, 0.35, 0.33, 0.6, 0.42)
    board(c, "s3", "prancha-1.jpg", 2.0, 0.6, 0.4, 0.4, 0.55)
    board(c, "s4", "prancha-1.jpg", 2.0, 0.4, 0.55, 0.6, 0.67)
    board(c, "s5", "prancha-1.jpg", 2.2, 0.3, 0.67, 0.7, 0.67)
    board(c, "s6", "prancha-2.jpg", 3.0, 0.15, 0.5, 0.4, 0.5, aspect=0.6667)
    board(c, "s7", "prancha-2.jpg", 3.0, 0.6, 0.5, 0.9, 0.5, aspect=0.6667)


if __name__ == "__main__":
    monta("polo", "video-02-pov-wesley-polo", "POV cores que valorizam e apagam (Wesley) — Reels 26 s",
          "POV: você descobriu quais cores te valorizam e quais te apagam", sete_pranchas("8a6793a20cb5b29a19d73a25"))
    monta("bruna7", "video-03-pov-bruna-7", "POV cabelo, maquiagem e acessórios (Bruna, 7 pranchas) — Reels 26 s",
          "POV: seu cabelo, sua maquiagem e seus acessórios finalmente combinam com você", sete_pranchas("2b922b7be026b1aa24d14c5c"))
    monta("bruna4", "video-04-pov-bruna-4", "POV cartela de cores e maquiagem (Bruna, 4 pranchas) — Reels 26 s",
          "POV: você descobriu a sua cartela de cores e a maquiagem que valoriza o seu rosto", quatro_pranchas("556d34236975a9d0c1a1e816"), bruna4)
    sid = "61e9639f324a1261405b2342"
    monta("amanda", "video-05-pov-amanda", "POV estação de cores e looks (Amanda) — Reels 26 s",
          "POV: você descobriu a sua estação de cores e os looks que combinam com você",
          [{"arquivo": f"../coleta/showcase/{sid}/signature-board.jpg", "destino": "assets/client/prancha-1.jpg"},
           {"arquivo": f"../coleta/showcase/{sid}/styling-board.jpg", "destino": "assets/client/prancha-2.jpg"}], amanda, close_board="prancha-1.jpg")
