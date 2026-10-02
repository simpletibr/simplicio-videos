"""International previews (INT-1): WJR pain hook -> the company solves it, in the local language and country style.

`simplicio-video intl <fichas>` turns one YAML "ficha" per company (pain + source from the dossier, exact lines, real logo)
into a render-ready contract of the `internacional-dor` template, styled per country by templates/internacional-dor/paises.json
(palette, word font/mode, BPM and scene grid, music style, Gemini voice + style prompt). Deterministic, no LLM.

Per company (<out>/<slug>/): contract.yaml, coleta/logo.*, roteiro.md (pain + dossier source), falas.csv (exact text per
line, language, suggested Gemini voice, style prompt, cache key, reuse group), briefing-visual.md. Batch: falas-todas.csv.
  --mudo    renders preview-mudo.mp4 (layout check: no voice, provisional timing from the text length, label on screen).
            Zero TTS calls: the provisional takes are local noise files and voz.habilitada=false in a separate mudo/ copy.
  --render  voice (Gemini) + preview.mp4 with the watermark/end card in the video language. Lines with the same voice
            settings and text are generated once and reused across companies (same cache key as `simplicio-video voice`).
Guards (fail the company, never silently fix): price/currency/discount/free words in any language, guarantees and
superlatives, SimpleTI, screen words != spoken words, a line that will not fit its slot at a conservative speech rate,
and the sign-off layout guard (layout.endcard_collisions).
"""
from __future__ import annotations

import copy
import csv
import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import yaml

from . import paths
from .layout import endcard_collisions
from .contract import r4

TEMPLATE = "internacional-dor"
LINE_IDS = ("vo1", "vo2", "vo3", "vo4")
SCENES = ("s1", "s2", "s3", "s4")
MUDO_NOTE = "SEM VOZ · prévia de layout (áudio provisório)"

# Never on an outbound preview, in any of our languages (Wesley, INT-1): price, currency, discounts, "free",
# financing, guarantees and superlatives. Word-boundary regexes over the lower-cased text.
FORBIDDEN = [
    (r"[$€£¥]|\b(?:usd|eur|chf|aed|sgd|dhs?|s\$|fr\.)\b|\d+\s*(?:dollars?|euros?|francs?|dirhams?)", "preço/moeda"),
    (r"\b(?:price[sd]?|pricing|cost[s]?|cheap(?:er|est)?|afford\w*|discount\w*|deal[s]?|sale|promo\w*|coupon\w*|financ\w*)\b", "preço/promoção (en)"),
    (r"\b(?:preis\w*|kosten\w*|günstig\w*|billig\w*|rabatt\w*|angebot\w*|aktion\w*|gutschein\w*|finanzier\w*)\b", "preço/promoção (de)"),
    (r"\b(?:prix|tarif\w*|co[uû]t(?:e|s|er|ent)?|pas cher|r[ée]duction\w*|remise\w*|promo\w*|soldes?|financ\w*)\b", "preço/promoção (fr)"),
    (r"(?<!fear-)\b(?:free|gratis|kostenlos|gratuit\w*|offert\w*)\b", "grátis"),  # "fear-free" is a grooming method, not a price
    (r"\b(?:guarantee\w*|garantier\w*|garanti\w*|warrant\w*)\b", "garantia"),
    (r"\b(?:best|#1|number one|nummer eins|beste[nrs]?|meilleur\w*|perfect results?|cure[sd]?|heil(?:t|en|ung)|gu[ée]ri\w*)\b", "superlativo/promessa"),
    (r"\b(?:before\s*(?:&|and)\s*after|vorher\s*(?:/|-|und)?\s*nachher|avant\s*/?\s*apr[eè]s)\b", "antes/depois"),
    (r"\d+\s*%|\b\d+\s*(?:percent|prozent|pour\s*cent)\b|\b(?:off|sparen|économisez)\b", "percentual/desconto"),
    (r"simple\s*ti|simpleti", "SimpleTI"),
]


class FichaError(ValueError):
    pass


def home() -> Path:
    return paths.home()


def load_paises(h: Path | None = None) -> dict:
    h = h or home()
    return json.loads((h / "templates" / TEMPLATE / "paises.json").read_text(encoding="utf8"))["paises"]


def check_text(text: str) -> list[str]:
    t = (text or "").lower()
    return [f"{why}: {m.group(0)!r} em {text!r}" for rx, why in FORBIDDEN for m in [re.search(rx, t)] if m]


def _hex(c: str) -> tuple[float, float, float]:
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) / 255 for i in (0, 2, 4))


def luminance(c: str) -> float:
    def ch(x):
        return x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4
    r, g, b = (ch(x) for x in _hex(c))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: str, b: str) -> float:
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def darken(c: str, f: float) -> str:
    return "#" + "".join(f"{max(0, min(255, round(x * 255 * (1 - f)))):02x}" for x in _hex(c))


def readable(accent: str, bg: str, min_ratio: float = 3.0) -> str:
    """Darken the brand accent until it reads on `bg` (and white chip text reads on it)."""
    c, k = accent, 0
    while (contrast(c, bg) < min_ratio or contrast(c, "#ffffff") < min_ratio) and k < 20:
        c, k = darken(c, 0.08), k + 1
    return c


def grid(P: dict) -> list[float]:
    beat = 60.0 / P["bpm"]
    return [r4(b * beat) for b in P["beats"]]


def ascii_name(s: str) -> str:
    import unicodedata
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", re.sub(r"[^\w&' .-]", " ", s)).strip()


def _sub(v, accent: str):
    if isinstance(v, str):
        return v.replace("{accent}", accent)
    if isinstance(v, list):
        return [_sub(x, accent) for x in v]
    return v


def build_contract(f: dict, h: Path | None = None) -> tuple[dict, dict]:
    """Contract dict + meta from a company ficha. Raises FichaError with every problem found."""
    h = h or home()
    paises = load_paises(h)
    if f.get("pais") not in paises:
        raise FichaError(f"{f.get('slug')}: país desconhecido {f.get('pais')!r} (paises.json: {', '.join(paises)})")
    P = paises[f["pais"]]
    base = yaml.safe_load((h / "templates" / TEMPLATE / "contract.base.yaml").read_text(encoding="utf8"))
    d = copy.deepcopy(base)
    probs: list[str] = []
    falas = f.get("falas") or {}
    for lid in LINE_IDS:
        if lid not in falas or not (falas[lid] or {}).get("texto"):
            probs.append(f"falta a fala {lid}")
    if probs:
        raise FichaError(f"{f.get('slug')}: " + "; ".join(probs))
    accent = readable(f.get("accent") or P["texto"][-1], P["base"], 3.0 if luminance(P["base"]) > 0.5 else 1.0)
    durs = grid(P)
    total = r4(sum(durs))
    d["cliente"] = {"slug": f["slug"], "nome": f["nome"], "drive_nome": f["drive_nome"], "coleta": "coleta.json"}
    d["campanha"] = {"id": "Preview_INT1", "ano": 2026, "titulo": f"INT-1 {P['nome']} — pain-hook preview ({P['idioma']})",
                     "objetivo": "Prévia com marca d'água Wesley Simplicio (@wesleysimplicio) no idioma do vídeo, para oferecer o vídeo (venda ativa; não publicar)"}
    d["formato"]["duracao_s"] = total
    d["marca"]["paleta"] = {"ink": P["ink"], "line_cream": P["formas"][-1] if "{" not in P["formas"][-1] else "#e6e6e6",
                            "accent": accent, "chip": P["lockup"].get("chip", accent), "background": P["base"]}
    logo_dst, logo_round, logo_size, logo_bg = "", 1, 300, ""
    if f.get("logo"):
        src = Path(f["logo"])
        ext = src.suffix.lower() if src.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp", ".svg") else ".png"
        logo_dst = f"assets/client/logo{ext}"
        d["marca"]["logo"] = {"arquivo": f"coleta/logo{ext}", "destino": logo_dst}
        w, hh = f.get("logo_px") or (0, 0)
        logo_round = 1 if not (w and hh) or 0.8 <= w / hh <= 1.25 else 0
        logo_size = 440 if logo_round else 330
        if f.get("logo_claro") and P["lockup"].get("placa_logo_claro"):
            logo_bg = P["lockup"]["placa_logo_claro"]
        elif not f.get("logo_claro") and P["lockup"].get("placa_logo_escuro"):
            logo_bg = P["lockup"]["placa_logo_escuro"]
    else:
        d["marca"]["logo"] = None
    texto_cores = "|".join(_sub(P["texto"], accent))
    formas = "|".join(_sub(P["formas"], accent))
    beat = 60.0 / P["bpm"]
    t0 = 0.0
    for i, s in enumerate(d["cenas"]):
        dur = durs[i]
        s["duracao_s"] = dur
        lid = LINE_IDS[i]
        fl = falas[lid]
        texto = " ".join(str(fl["texto"]).split())
        tela = fl.get("tela") or texto
        say = fl.get("say")
        if [w for w in tela.replace("|", " ").split()] != texto.split():
            probs.append(f"{lid}: palavras da tela {tela!r} != fala {texto!r} (texto palavra a palavra segue a fala)")
        ini = P["inicio"][i]
        max_s = round(dur - ini - 0.12, 2)
        s["fala"] = {"id": lid, "texto": texto, "inicio_s": ini, "max_s": max_s, **({"say": say} if say else {})}
        est = round(len(say or texto) / P["chars_s"], 2)
        if est > max_s * 0.95:
            probs.append(f"{lid}: {len(say or texto)} caracteres ≈ {est}s > 95% do slot {max_s}s — encurte a fala")
        s["tela"] = [tela.replace("|", " / ") + " (palavra a palavra)"]
        for m in s["motion"]:
            p, b = m["params"], m.get("bloco")
            if m["padrao"] == "bg-parallax":
                p.update(colors=formas, base=P["base"], center=P["centro"], ink=P["ink"], speed=P["speed"], zoom=P["zoom"],
                         shapes=P["shapes"], dots=P["dots"])
            elif m["padrao"] == "fx-transition":
                p.update(kind=P["transicao"]["kind"], frames=P["transicao"]["frames"], flash=P["transicao"]["flash"],
                         flash_max=P["transicao"]["flash_max"], colors=formas)
            elif m["padrao"] == "line-accent":
                p.update(color=_sub(P["linha"], accent), ink=_sub(P["linha"], accent), glow=P["linha_glow"])
            elif m["padrao"] == "beat-burst":
                p.update(stars=P["estrelas"], size=P["burst_size"], colors=formas, ink=P["ink"],
                         count=p.get("count", 1) if P["estrelas"] else 0)
            elif m["padrao"] == "kinetic-words":
                p.update(lines=tela, colors=texto_cores, ink=P["ink"], size=P["tamanhos"][i], font=P["fonte"], mode=P["modo"])
            elif m["padrao"] == "brand-lockup-soft":
                name, sub = (f.get("lockup") or [f["nome"].upper()[:16], ""])[:2]
                tagline, handle, city = f.get("tagline", ""), f.get("handle", ""), f.get("cidade_label", "")
                if len(handle) > 28:  # the @ chip holds 28 characters; a longer handle stays out of the sign-off (post caption only)
                    handle = ""
                for k, v, n in (("tagline", tagline, 44), ("handle", handle, 28), ("city", city, 32), ("name", name, 16), ("sub", sub, 20)):
                    if len(v) > n:
                        probs.append(f"lockup {k} {v!r} tem {len(v)} > {n} caracteres")
                p.update(name=name, sub=sub, tagline=tagline, handle=handle, city=city, logo=logo_dst, logo_round=logo_round,
                         logo_size=logo_size, logo_bg=logo_bg, ink=P["lockup"]["ink"], accent=P["lockup"].get("chip", accent),
                         colors=formas, tag_font=P["lockup"]["tag_font"], dots=P["lockup"]["dots"])
        for cue in s.get("sfx", []):
            if cue["id"].startswith("whoosh"):
                cue["t"] = r4(max(0.0, dur - 0.25))
            elif cue["id"] in ("end-chime", "end-sparkle"):
                cue["t"] = r4(max(0.0, dur - 1.0))
            elif cue["id"] == "chime-soft":
                cue["t"] = r4(min(cue["t"], dur - 1.2))
        if i == 3:
            s["tela"] = ([f"logo real ({f.get('logo_fonte', 'site oficial')})"] if logo_dst else [f"lockup de texto {name} / {sub}"]) + \
                [f.get("tagline", ""), f.get("handle", "") if len(f.get("handle", "")) <= 28 else "(sem chip @: handle > 28)", f.get("cidade_label", ""), tela.replace("|", " / ")]
        t0 += dur
    tr = d["trilha"]
    T = P["trilha"]
    tr["bpm"] = P["bpm"]
    mus = tr["music"]
    mus["style"] = T["style"]
    mus["gain_db"] = T["gain_db"]
    if T["style"] == "institucional":
        mus["drums"] = T["drums"]
    else:
        mus.pop("drums", None)
    mus["progression"] = T["progression"]
    end = r4(total - 1.0)
    mus["sections"] = ([{"name": "groove", "from": 0, "to": end}, {"name": "outro", "from": end, "to": total}]
                       if T["style"] == "institucional" else
                       [{"name": "intro", "from": 0, "to": r4(2 * beat)}, {"name": "groove", "from": r4(2 * beat), "to": r4(total - 0.5)}])
    mus["melody"] = [n for n in mus.get("melody", []) if n[0] * beat < total - 1.0] if T.get("melodia") else []
    v = d["voz"]
    V = P["voz"]
    v.update(provider=f.get("provider", "gemini"), voice=V["voice"], estilo=V["estilo"], idioma=P["idioma"])
    v["providers"]["gemini"] = {"model": "gemini-3.8-flash-tts", "voice": V["voice"], "alternativas": V["alternativas"], "estilo": V["estilo"]}
    v["providers"]["file"]["origem"] = f"Gemini 3.8 Flash TTS, voz {V['voice']} ({P['idioma']}), uma fala por arquivo line-01..04.wav"
    d["drive"] = {"caminho": f"simplicio-video/clientes/{f['drive_nome']}/{d['campanha']['ano']}/{d['campanha']['id']}",
                  "arquivo": f"{ascii_name(f.get('nome_arquivo') or f['nome'])} - Preview INT-1 - v03.mp4",
                  "status": "prévia de venda ativa (não publicar)"}
    d["saida"] = {"arquivo": "out/preview-full.mp4", "qualidade": "draft"}
    # guards
    texts = [s["fala"]["texto"] for s in d["cenas"]] + [s["fala"].get("say", "") for s in d["cenas"]] + \
        [falas[l].get("tela", "") for l in LINE_IDS] + [f.get("tagline", ""), f.get("cidade_label", ""), " ".join(f.get("lockup") or [])]
    for t in texts:
        probs += check_text(t)
    probs += endcard_collisions(d["cenas"])
    if "simpleti" in json.dumps(d, ensure_ascii=False).lower():
        probs.append("SimpleTI no contrato")
    if probs:
        raise FichaError(f"{f.get('slug')}: " + "; ".join(dict.fromkeys(probs)))
    meta = {"p": f.get("p"), "slug": f["slug"], "pais": f["pais"], "idioma": P["idioma"], "voz": V["voice"], "duracao_s": total,
            "logo": "real" if logo_dst else "lockup de texto", "accent": accent, "grade": durs, "bpm": P["bpm"],
            "chip_handle": len(f.get("handle", "")) <= 28}
    return d, meta


def voice_key(d: dict, lid: str) -> str:
    """Same cache key as voice.run(provider='gemini') -> assets/audio/voz/<id>-<key>.wav (reuse across companies)."""
    from .voice import DEFAULT_CHAIN, GEMINI_MODEL
    v = d["voz"]
    P = (v.get("providers") or {}).get("gemini", {})
    S = {"model": P.get("model", GEMINI_MODEL), "voice": P.get("voice") or v.get("voice"), "estilo": P.get("estilo") or v.get("estilo", "")}
    chain = v.get("processamento", DEFAULT_CHAIN)
    line = next(s["fala"] for s in d["cenas"] if s["fala"]["id"] == lid)
    say = line.get("say", line["texto"])
    return hashlib.sha256(json.dumps(["gemini", S, chain, say], ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:12]


def write_contract(pdir: Path, f: dict, d: dict) -> Path:
    pdir.mkdir(parents=True, exist_ok=True)
    if f.get("logo"):
        src = Path(f["logo"])
        dst = pdir / d["marca"]["logo"]["arquivo"]
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    (pdir / "coleta.json").write_text(json.dumps({"fonte": "ficha INT-1 (dossiê /workspace/prospects-int1/int1-dossie.md)",
                                                   "nome": f["nome"], "handle": f.get("handle"), "logo": f.get("logo"),
                                                   "logo_fonte": f.get("logo_fonte")}, indent=2, ensure_ascii=False) + "\n", encoding="utf8")
    hdr = (f"# simplicio.video-contract/v1 — PRÉVIA INT-1 gerada por `simplicio-video intl` (determinístico, sem LLM).\n"
           f"# {f.get('p', '')} {f['nome']} · {f['pais']} · dor: {(f.get('dor') or {}).get('escolhida', '')}\n"
           f"# Fonte da dor: {(f.get('dor') or {}).get('fonte', '')}\n")
    path = pdir / "contract.yaml"
    path.write_text(hdr + yaml.safe_dump(d, allow_unicode=True, sort_keys=False, width=140), encoding="utf8")
    return path


FALAS_COLS = ["p", "slug", "empresa", "pais", "idioma", "id", "cena", "papel", "texto", "say", "tela", "max_s", "est_s",
              "voz_gemini", "voz_alternativas", "modelo", "estilo_prompt", "reuso_grupo", "chave_cache", "tts_necessaria", "reusa_de"]


def falas_rows(f: dict, d: dict, P: dict, first: dict[str, str]) -> list[dict]:
    rows = []
    papel = {"vo1": "dor (gancho)", "vo2": "dor (detalhe)", "vo3": "solução (empresa)", "vo4": "marca + chamada"}
    for s in d["cenas"]:
        fl = s["fala"]
        lid = fl["id"]
        key = voice_key(d, lid)
        owner = first.setdefault(key, f["slug"])
        rows.append({"p": f.get("p", ""), "slug": f["slug"], "empresa": f["nome"], "pais": P["nome"], "idioma": P["idioma"], "id": lid,
                     "cena": s["id"], "papel": papel[lid], "texto": fl["texto"], "say": fl.get("say", ""),
                     "tela": (f["falas"][lid].get("tela") or fl["texto"]), "max_s": fl["max_s"],
                     "est_s": round(len(fl.get("say", fl["texto"])) / P["chars_s"], 2), "voz_gemini": P["voz"]["voice"],
                     "voz_alternativas": "|".join(P["voz"]["alternativas"]), "modelo": "gemini-3.8-flash-tts",
                     "estilo_prompt": P["voz"]["estilo"], "reuso_grupo": f["falas"][lid].get("reuso", ""), "chave_cache": f"{lid}-{key}",
                     "tts_necessaria": 1 if owner == f["slug"] else 0, "reusa_de": "" if owner == f["slug"] else owner})
    return rows


def write_csv(path: Path, rows: list[dict]):
    with path.open("w", newline="", encoding="utf8") as fh:
        w = csv.DictWriter(fh, fieldnames=FALAS_COLS)
        w.writeheader()
        w.writerows(rows)


def roteiro_md(f: dict, d: dict, P: dict, meta: dict) -> str:
    dor = f.get("dor") or {}
    L = [f"# {f.get('p', '')} — {f['nome']} · roteiro INT-1 ({P['nome']}, {P['idioma']})", "",
         f"- **Setor:** {f.get('setor', '')}  |  **Cidade:** {f.get('cidade', '')}  |  **Canal da chamada:** {f.get('cta', '')}",
         f"- **Estilo:** WJR — abre com a dor real do cliente do setor e mostra {f['nome']} como quem resolve. ~{meta['duracao_s']} s, {P['bpm']} BPM, grade {meta['grade']} s.",
         f"- **Dor escolhida:** {dor.get('escolhida', '')}",
         f"- **Evidência:** {dor.get('evidencia', '')}",
         f"- **Fonte (dossiê):** {dor.get('fonte', '')}"]
    if f.get("dores_alternativas"):
        L += ["- **Outras dores do dossiê (não usadas):**"] + [f"  - {x}" for x in f["dores_alternativas"]]
    if f.get("cuidados"):
        L += ["- **Cuidados (setor/país):**"] + [f"  - {x}" for x in f["cuidados"]]
    L += ["", "| Cena | Papel | Fala (exata) | Tela (palavra a palavra) | Slot | Por quê / fonte |", "|---|---|---|---|---|---|"]
    papel = {"vo1": "Dor (gancho)", "vo2": "Dor (detalhe)", "vo3": "Solução: a empresa", "vo4": "Marca + chamada"}
    for s in d["cenas"]:
        fl = s["fala"]
        fx = f["falas"][fl["id"]]
        L.append(f"| {s['id'].upper()} ({s['duracao_s']} s) | {papel[fl['id']]} | {fl['texto']} | {(fx.get('tela') or fl['texto']).replace('|', ' / ')} | "
                 f"{fl['max_s']} s | {fx.get('porque', '')} |")
    L += ["", f"**Assinatura (S4):** {'logo real' if meta['logo'] == 'real' else 'lockup de texto'} · tagline \"{f.get('tagline', '')}\" · "
          f"{f.get('handle', '')} · {f.get('cidade_label', '')}. Depois, end card \"{_end_title(P)}\" + @wesleysimplicio.",
          "", "Preço nunca aparece. Sem promessa de resultado, garantia ou superlativo. Nada é enviado ao cliente: a prévia volta para o Wesley aprovar.", ""]
    return "\n".join(L)


def _end_title(P: dict) -> str:
    from .render import preview_texts
    return preview_texts(P["idioma"])["end_title"]


def briefing_md(f: dict, d: dict, P: dict, meta: dict) -> str:
    from .render import preview_texts
    T = preview_texts(P["idioma"])
    lk = next(m["params"] for m in d["cenas"][3]["motion"] if m["padrao"] == "brand-lockup-soft")
    L = [f"# {f.get('p', '')} — {f['nome']} · briefing visual ({P['nome']})", "",
         f"- **Cultura/tom:** {P['cultura']}",
         f"- **Formato:** prévia 540×960 (render 1080×1920 → prévia), {meta['duracao_s']} s + end card 2,5 s; cortes na batida ({P['bpm']} BPM), "
         f"transições {P['transicao']['kind']} de {P['transicao']['frames']} frames.",
         f"- **Paleta:** fundo {P['base']} (centro {P['centro']}), tinta {P['ink']}, destaque da marca {meta['accent']}, formas {', '.join(_sub(P['formas'], meta['accent']))}.",
         f"- **Texto palavra a palavra:** fonte {P['fonte']}, modo {P['modo']}, tamanhos S1–S4 {P['tamanhos']} px.",
         f"- **Fundo:** bg-parallax com {P['shapes']} formas e {P['dots']} pontos, velocidade {P['speed']}; estrelas no beat: {P['estrelas']}.",
         f"- **Trilha:** estilo {P['trilha']['style']}" + (f", bateria {P['trilha']['drums']}" if P['trilha']['style'] == 'institucional' else ", pop com kick e palmas") +
         f", {P['bpm']} BPM, master -14 LUFS.",
         f"- **Voz (quando liberar):** Gemini 3.8 Flash TTS, {P['voz']['voice']} (alternativas {', '.join(P['voz']['alternativas'])}). Prompt: \"{P['voz']['estilo']}\"",
         f"- **Logo:** {'REAL — ' + str(f.get('logo_fonte', '')) if meta['logo'] == 'real' else 'sem logo real: lockup de texto ' + lk['name'] + ' / ' + lk['sub']}"
         + (f" (placa {lk['logo_bg']} atrás do logo)" if lk.get("logo_bg") else "") + f"; {'redondo' if lk['logo_round'] else 'largo, sem corte'}, {lk['logo_size']} px no anel.",
         f"- **Assinatura S4:** tagline \"{lk['tagline']}\", chip {lk['handle']}, cidade \"{lk['city']}\", chip na cor {lk['accent']}.",
         f"- **Marca d'água:** \"{T['watermark']}\" + selo \"{T['badge']}\"; end card \"{T['end_title']}\" / {T['end_url']} / \"{T['end_note']}\". Sem SimpleTI.",
         "", "## Cenas"]
    for s in d["cenas"]:
        fl = s["fala"]
        L.append(f"- **{s['id'].upper()}** ({s['duracao_s']} s): {s['tela'][0] if s['id'] != 's4' else ' · '.join(x for x in s['tela'] if x)}")
    L += ["", "Checagens automáticas: sem preço/moeda/desconto/grátis/garantia/superlativo; tela = fala; fala cabe no slot; layout do fechamento sem sobreposição.", ""]
    return "\n".join(L)


def load_fichas(paths_in: list[Path]) -> list[dict]:
    files: list[Path] = []
    for p in paths_in:
        files += sorted(p.glob("*.yaml")) if p.is_dir() else [p]
    out = []
    for fp in files:
        data = yaml.safe_load(fp.read_text(encoding="utf8"))
        for f in (data if isinstance(data, list) else [data]):
            f["_ficha"] = str(fp)
            out.append(f)
    return out


def provisional_takes(mdir: Path, d: dict, P: dict) -> None:
    """Local noise takes sized to the text at the conservative rate (no TTS). Only for the mute layout preview."""
    od = mdir / "assets" / "audio" / "vo" / "provisorio"
    od.mkdir(parents=True, exist_ok=True)
    for i, s in enumerate(d["cenas"]):
        fl = s["fala"]
        dur = min(fl["max_s"] - 0.05, max(0.8, len(fl.get("say", fl["texto"])) / P["chars_s"]))
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"anoisesrc=d={dur:.3f}:c=pink:a=0.03:seed={i + 1}",
                        "-ac", "1", "-ar", "48000", "-c:a", "pcm_s16le", str(od / f"line-{i + 1:02d}.wav")], check=True)


def render_mudo(pdir: Path, d: dict, P: dict, log=print) -> Path:
    """preview-mudo.mp4: same contract in pdir/mudo/ with voz.habilitada=false + provisional takes (words timed by length)."""
    from . import contract as cmod, render, voice
    mdir = pdir / "mudo"
    if mdir.exists():
        shutil.rmtree(mdir)
    mdir.mkdir(parents=True)
    dm = copy.deepcopy(d)
    dm["voz"].update(habilitada=False, provider="file")
    dm["voz"]["providers"]["file"]["dir"] = "assets/audio/vo/provisorio"
    if dm["marca"].get("logo"):
        dm["marca"]["logo"]["arquivo"] = "../" + dm["marca"]["logo"]["arquivo"]
    dm["saida"] = {"arquivo": "out/mudo-full.mp4", "qualidade": "draft"}
    (mdir / "contract.yaml").write_text("# CÓPIA SÓ PARA LAYOUT (sem voz, áudio provisório) — nunca usar como final\n" +
                                        yaml.safe_dump(dm, allow_unicode=True, sort_keys=False, width=140), encoding="utf8")
    provisional_takes(mdir, dm, P)
    c = cmod.load(mdir / "contract.yaml")
    old = os.environ.get("SIMPLICIO_STT_PY")
    os.environ["SIMPLICIO_STT_PY"] = "/nonexistent"  # proportional word timing; never transcribe noise
    try:
        voice.run(c, provider="file", log=log)
    finally:
        if old is None:
            os.environ.pop("SIMPLICIO_STT_PY", None)
        else:
            os.environ["SIMPLICIO_STT_PY"] = old
    out = pdir / "preview-mudo.mp4"
    render.render_preview(c, out=out, log=log, note=MUDO_NOTE)
    return out


def seed_cache(root: Path, pdir: Path, d: dict, log=print) -> int:
    """Copy identical takes (same cache key) from sibling companies, so each shared line costs one TTS call."""
    n = 0
    cache = pdir / d["voz"].get("cache_dir", "assets/audio/voz")
    for i, s in enumerate(d["cenas"]):
        lid = s["fala"]["id"]
        name = f"{lid}-{voice_key(d, lid)}.wav"
        if (cache / name).is_file():
            continue
        for other in sorted(root.glob(f"*/assets/audio/voz/{name}")):
            if other.parent.parent.parent.parent == pdir:
                continue
            cache.mkdir(parents=True, exist_ok=True)
            shutil.copy2(other, cache / name)
            raw = other.parent.parent / "vo" / "external" / f"line-{i + 1:02d}.wav"
            if raw.is_file():
                (pdir / "assets/audio/vo/external").mkdir(parents=True, exist_ok=True)
                shutil.copy2(raw, pdir / "assets/audio/vo/external" / raw.name)
            log(f"[{pdir.name}] {lid} reaproveitada de {other.parent.parent.parent.parent.name}")
            n += 1
            break
    return n


def render_final(root: Path, pdir: Path, d: dict, provider: str = "gemini", log=print) -> Path:
    from . import contract as cmod, render, voice
    c = cmod.load(pdir / "contract.yaml")
    seed_cache(root, pdir, d, log=log)
    regen = int(os.environ.get("SIMPLICIO_VOICE_REGEN", "2"))
    only = None
    for k in range(regen + 1):
        try:
            voice.run(c, provider=provider, only=only, log=log)
            break
        except voice.VoiceError as e:
            over = re.findall(r"(vo\d): [\d.]+s > max_s", str(e))
            if not over or k == regen:
                raise
            log(f"[{pdir.name}] fala longa {over}: nova leva ({k + 1}/{regen}), nunca acelera")
            only = over
    out = pdir / "preview.mp4"
    if out.is_file():
        old = pdir / "preview.anterior.mp4"
        shutil.move(out, old)
    render.render_preview(c, out=out, log=log)
    return out


def run(fichas_in: list[Path], out: Path, only: list[str] | None = None, mudo: bool = False, render: bool = False,
        provider: str = "gemini", log=print) -> dict:
    h = home()
    paises = load_paises(h)
    fichas = load_fichas(fichas_in)
    sel = {x.strip() for o in (only or []) for x in o.split(",") if x.strip()}
    out.mkdir(parents=True, exist_ok=True)
    first: dict[str, str] = {}
    allrows, res = [], []
    built = []
    for f in sorted(fichas, key=lambda x: str(x.get("p", x.get("slug")))):
        try:
            d, meta = build_contract(f, h)
        except FichaError as e:
            res.append({"slug": f.get("slug"), "p": f.get("p"), "status": "erro", "motivo": str(e)})
            log(f"erro {e}")
            continue
        P = paises[f["pais"]]
        rows = falas_rows(f, d, P, first)
        allrows += rows
        built.append((f, d, P, meta, rows))
    for f, d, P, meta, rows in built:
        if sel and f["slug"] not in sel:
            continue
        pdir = out / f["slug"]
        write_contract(pdir, f, d)
        write_csv(pdir / "falas.csv", rows)
        (pdir / "roteiro.md").write_text(roteiro_md(f, d, P, meta), encoding="utf8")
        (pdir / "briefing-visual.md").write_text(briefing_md(f, d, P, meta), encoding="utf8")
        r = {**meta, "status": "roteiro_pronto", "dir": str(pdir), "tts": sum(x["tts_necessaria"] for x in rows)}
        log(f"[{f['slug']}] contrato + roteiro + falas ({P['idioma']}, voz {P['voz']['voice']}, {meta['logo']}, {meta['duracao_s']} s)")
        try:
            if mudo:
                r["preview_mudo"] = str(render_mudo(pdir, d, P, log=log))
            if render:
                r["preview"] = str(render_final(out, pdir, d, provider=provider, log=log))
                r["status"] = "preview_pronta"
        except Exception as e:  # one company never stops the batch
            r.update(status="erro_render", motivo=f"{type(e).__name__}: {str(e)[:500]}")
            log(f"[{f['slug']}] erro {r['motivo']}")
        (pdir / "result.json").write_text(json.dumps(r, indent=2, ensure_ascii=False) + "\n", encoding="utf8")
        res.append(r)
    write_csv(out / "falas-todas.csv", allrows)
    summary = {"empresas": len(built), "falas": len(allrows), "tts_necessarias": sum(x["tts_necessaria"] for x in allrows),
               "reaproveitadas": sum(1 - x["tts_necessaria"] for x in allrows), "resultados": res}
    (out / "lote-int.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf8")
    log(f"intl: {len(built)} empresas, {summary['falas']} falas, {summary['tts_necessarias']} chamadas TTS necessárias "
        f"({summary['reaproveitadas']} reaproveitadas) -> {out}")
    return summary
