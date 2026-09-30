"""`simplicio-video prospect <lista.csv>` (alias `batch`): mass sales previews for active selling (venda ativa).

CSV (UTF-8, header; only `nome` is required):
  nome, cidade, setor, site, instagram, whatsapp, maps, nome_curto, nome_falado, fontes
Per row, fully deterministic (no LLM per video):
  1. coleta   public + light: site home page (title/meta/og, theme-color + CSS colours, logo/og:image candidates,
              Instagram/WhatsApp links published by the company), robots.txt respected, 1 request per resource.
              Instagram: only public og:* without login, only when robots.txt allows it, global rate limit;
              instagram.com/robots.txt disallows every generic bot, so today the @ comes from the CSV or the site.
              LGPD: only company data (no people, no personal e-mail/phones; the commercial WhatsApp the company
              publishes is kept as the business contact).
  2. setor    regex rules of templates/<campanha template>/setores.json (CSV setor first, then site title/description)
  3. contrato contract.base.yaml + sector texts + real company name/@/city (never price, promotion or invented facts)
  4. voz      provider local (Kokoro, cost 0) by default; gemini optional (GEMINI_API_KEY). Lines that overflow their
              slot fall back to the shorter sector/name variants (deterministic list order).
  5. render --preview  540x960, crf 30, 30 fps, SimpleTI watermark + end card (render.render_preview)
Output: <out>/<slug>/{coleta.json, contract.yaml, preview.mp4, result.json} + <out>/lote.csv.
Idempotent: rows whose preview.mp4 + result.json(status ok) exist are skipped; coleta.json is reused.
"""
from __future__ import annotations

import copy
import csv
import html
import json
import os
import re
import threading
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser
from pathlib import Path

import yaml

from . import __version__, paths

UA = f"SimplicioVideoBot/{__version__} (+https://simpleti.com.br; previa publica, sem login)"
TIMEOUT_S = 15
MAX_HTML = 1_500_000
MAX_IMG = 2_000_000
IG_MIN_INTERVAL_S = 6.0
CAMPANHAS = {"dia-das-criancas": "sazonal-dia-das-criancas"}
REPORT_COLS = ["nome", "slug", "setor", "setor_regra", "cidade", "instagram", "instagram_fonte", "whatsapp", "whatsapp_fonte",
               "site", "site_status", "instagram_status", "titulo_site", "cores", "logo", "fontes", "status", "motivo",
               "preview", "tempo_s", "tempo_render_s"]


# ------------------------------------------------------------------------------------------------ text helpers
def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    return "".join(ch for ch in s if not unicodedata.combining(ch)).lower().strip()


def slugify(s: str) -> str:
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", norm(s))).strip("-")[:64] or "empresa"


def drive_name(s: str) -> str:
    words = re.findall(r"[A-Za-z0-9]+", unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode())
    return "_".join(w[:1].upper() + w[1:] for w in words) or "Empresa"


def ascii_name(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^A-Za-z0-9 &.]", " ", unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode())).strip()


EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
PHONE = re.compile(r"(\+?55\s*)?\(?\d{2}\)?\s*9?\d{4}[-.\s]?\d{4}")
PERSON = re.compile(r"\b(Dr|Dra|Prof|Profa)\.?\s+[A-ZÁÉÍÓÚÂÊÔÃÕÇ][\wáéíóúâêôãõç]+(\s+[A-ZÁÉÍÓÚÂÊÔÃÕÇ][\wáéíóúâêôãõç]+){0,3}")
REGISTRY = re.compile(r"\bCRO[-\s]?[A-Z]{0,2}[:\s]*[\d.]+", re.I)


def scrub(s: str | None, limit: int = 300) -> str:
    """LGPD: company text only - drop e-mails, phone numbers, professional names and registry numbers."""
    if not s:
        return ""
    s = html.unescape(s)
    s = EMAIL.sub("", s)
    s = PHONE.sub("", s)
    s = PERSON.sub("", s)
    s = REGISTRY.sub("", s)
    return re.sub(r"\s+", " ", s).strip(" -|·,;:")[:limit]


def fmt_whatsapp(digits: str) -> str | None:
    d = re.sub(r"\D", "", digits or "")
    if d.startswith("55") and len(d) in (12, 13):
        d = d[2:]
    if len(d) == 11 and d[2] == "9":
        return f"+55 ({d[:2]}) {d[2:7]}-{d[7:]}"
    if len(d) == 10:
        return f"+55 ({d[:2]}) {d[2:6]}-{d[6:]}"
    return None


def fmt_handle(s: str | None) -> str:
    if not s:
        return ""
    s = s.strip()
    m = re.search(r"instagram\.com/([A-Za-z0-9_.]+)", s)
    h = m.group(1) if m else s.lstrip("@").strip("/")
    return "@" + h if re.fullmatch(r"[A-Za-z0-9_.]{1,30}", h) else ""


def city_label(cidade: str | None) -> str:
    c = (cidade or "").strip()
    m = re.match(r"^(.*?)[\s,/-]+([A-Za-z]{2})$", c)
    if m and m.group(2).upper() == m.group(2).upper() and len(m.group(2)) == 2:
        return f"{m.group(1).strip()} · {m.group(2).upper()}"
    return c


# ------------------------------------------------------------------------------------------------ colours
def hex6(c: str) -> str | None:
    c = c.strip().lower()
    if re.fullmatch(r"#[0-9a-f]{3}", c):
        return "#" + "".join(ch * 2 for ch in c[1:])
    return c if re.fullmatch(r"#[0-9a-f]{6}", c) else None


def rgb(c: str) -> tuple[float, float, float]:
    return tuple(int(c[i:i + 2], 16) / 255 for i in (1, 3, 5))  # type: ignore[return-value]


def hsl(c: str) -> tuple[float, float, float]:
    r, g, b = rgb(c)
    mx, mn = max(r, g, b), min(r, g, b)
    li = (mx + mn) / 2
    if mx == mn:
        return 0.0, 0.0, li
    d = mx - mn
    s = d / (2 - mx - mn) if li > 0.5 else d / (mx + mn)
    h = ((g - b) / d % 6) if mx == r else ((b - r) / d + 2) if mx == g else ((r - g) / d + 4)
    return h * 60, s, li


def luminance(c: str) -> float:
    def ch(v):
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = rgb(c)
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def contrast(a: str, b: str) -> float:
    la, lb = sorted([luminance(a), luminance(b)], reverse=True)
    return (la + 0.05) / (lb + 0.05)


def darken(c: str, f: float) -> str:
    return "#" + "".join(f"{max(0, min(255, round(v * 255 * f))):02x}" for v in rgb(c))


# not brand colours: WordPress/Gutenberg preset palette and social-network brand colours (WhatsApp/Instagram/...)
NOT_BRAND = {"#f78da7", "#cf2e2e", "#ff6900", "#fcb900", "#7bdcb5", "#00d084", "#00d082", "#8ed1fc", "#0693e3", "#abb8c3",
             "#9b51e0", "#25d366", "#128c7e", "#075e54", "#1ebe5a", "#1da1f2", "#1877f2", "#3b5998", "#4267b2", "#e1306c",
             "#c13584", "#833ab4", "#fd1d1d", "#f56040", "#405de6", "#0077b5", "#0a66c2", "#ff0000", "#bd081c"}


def brand_colors(css_texts: list[str], theme: str | None) -> list[str]:
    """Saturated brand colours ordered by frequency (theme-color first); greys/near-white/near-black ignored."""
    counts: dict[str, int] = {}
    for t in css_texts:
        for m in re.findall(r"#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{3}\b", t):
            c = hex6(m)
            if c:
                counts[c] = counts.get(c, 0) + 1
        for m in re.findall(r"rgba?\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})", t):
            c = "#" + "".join(f"{min(255, int(x)):02x}" for x in m)
            counts[c] = counts.get(c, 0) + 1
    ok = [c for c in counts if c not in NOT_BRAND and hsl(c)[1] >= 0.3 and 0.18 <= hsl(c)[2] <= 0.82]
    ok.sort(key=lambda c: (-counts[c], c))
    th = hex6(theme or "")
    if th and hsl(th)[1] >= 0.3 and 0.18 <= hsl(th)[2] <= 0.82:
        ok = [th] + [c for c in ok if c != th]
    return ok[:6]


def accent_from(colors: list[str], default: str) -> str:
    """First brand colour made readable under white text (contrast >= 3:1, the brand-lockup chip)."""
    for c in colors:
        x = c
        for _ in range(12):
            if contrast(x, "#ffffff") >= 3.0:
                return x
            x = darken(x, 0.9)
    return default


# ------------------------------------------------------------------------------------------------ fetching
class Fetcher:
    """urllib with UA, timeout, size cap, robots.txt per host and a global Instagram rate limit (thread-safe)."""

    def __init__(self, timeout: float = TIMEOUT_S, opener=None):
        self.timeout = timeout
        self.opener = opener or urllib.request.urlopen
        self._robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}
        self._lock = threading.Lock()
        self._ig_last = 0.0

    def get(self, url: str, limit: int = MAX_HTML) -> tuple[int, str, str, bytes]:
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "pt-BR,pt;q=0.9"})
        try:
            with self.opener(req, timeout=self.timeout) as r:
                data = r.read(limit + 1)
                return getattr(r, "status", 200), r.geturl(), r.headers.get("Content-Type", ""), data[:limit]
        except urllib.error.HTTPError as e:
            return e.code, url, "", b""

    def allowed(self, url: str) -> bool:
        u = urllib.parse.urlparse(url)
        root = f"{u.scheme}://{u.netloc}"
        with self._lock:
            if root not in self._robots:
                rp = urllib.robotparser.RobotFileParser()
                try:
                    st, _, _, body = self.get(root + "/robots.txt", 500_000)
                    if st >= 400:
                        rp = None  # no robots.txt: allowed
                    else:
                        rp.parse(body.decode("utf8", "replace").splitlines())
                except Exception:  # noqa: BLE001 - unreachable robots: be conservative only on the page itself
                    rp = None
                self._robots[root] = rp
            rp = self._robots[root]
        return True if rp is None else rp.can_fetch(UA, url)

    def ig_wait(self):
        with self._lock:
            wait = self._ig_last + IG_MIN_INTERVAL_S - time.time()
            if wait > 0:
                time.sleep(wait)
            self._ig_last = time.time()


class Page(HTMLParser):
    SKIP = {"script", "style", "noscript", "svg", "template"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title, self.meta, self.links, self.imgs, self.anchors, self.styles, self.text = "", {}, [], [], [], [], []
        self._stack: list[str] = []
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag in self.SKIP:
            self._stack.append(tag)
        if tag == "title":
            self._in_title = True
        elif tag == "meta":
            k = (a.get("property") or a.get("name") or "").lower()
            if k and "content" in a and k not in self.meta:
                self.meta[k] = a["content"]
        elif tag == "link":
            self.links.append(a)
        elif tag == "img":
            self.imgs.append(a)
        elif tag == "a" and a.get("href"):
            self.anchors.append(a["href"])
        if a.get("style"):
            self.styles.append(a["style"])

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        if self._stack and self._stack[-1] == tag:
            self._stack.pop()

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        elif self._stack and self._stack[-1] == "style":
            self.styles.append(data)
        elif not self._stack and data.strip():
            self.text.append(data.strip())


IG_RESERVED = {"p", "reel", "reels", "explore", "stories", "tv", "accounts", "about", "developer", "legal", "direct"}


def instagram_links(anchors: list[str]) -> list[str]:
    out = []
    for h in anchors:
        m = re.search(r"instagram\.com(?:\.br)?/([A-Za-z0-9_.]{1,30})/?(?:[?#].*)?$", h)  # .com.br: common typo on sites
        if m and m.group(1).lower() not in IG_RESERVED:
            hd = "@" + m.group(1)
            if hd not in out:
                out.append(hd)
    return out


def whatsapp_links(anchors: list[str]) -> list[str]:
    out = []
    for h in anchors:
        h2 = urllib.parse.unquote(h)
        m = re.search(r"wa\.me/(\+?\d{10,13})", h2) or re.search(r"whatsapp\.com/send/?\?(?:.*&)?phone=(\+?\d{10,13})", h2) \
            or re.search(r"whatsapp://send\?(?:.*&)?phone=(\+?\d{10,13})", h2)
        if m:
            w = fmt_whatsapp(m.group(1))
            if w and w not in out:
                out.append(w)
    return out


def whatsapp_text(text: str) -> list[str]:
    out = []
    for m in re.finditer(r"whats\s*app[^0-9()+]{0,25}(\+?55\s*)?(\(?\d{2}\)?\s*9\s?\d{4}[-.\s]?\d{4})", text, re.I):
        w = fmt_whatsapp(m.group(2))
        if w and w not in out:
            out.append(w)
    return out


def collect_site(url: str, f: Fetcher, dest: Path | None = None) -> dict:
    res: dict = {"url": url, "status": "", "titulo": "", "descricao": "", "og": {}, "cores": [], "logo_url": None,
                 "og_image": None, "logo_arquivo": None, "instagram": [], "whatsapp_links": [], "whatsapp_texto": [],
                 "css_externos": 0}
    if not url:
        res["status"] = "sem_site"
        return res
    if not re.match(r"^https?://", url):
        url = "https://" + url
    if not urllib.parse.urlparse(url).path:
        url += "/"
    res["url"] = url
    try:
        if not f.allowed(url):
            res["status"] = "robots_disallow"
            return res
        st, final, ctype, body = f.get(url)
    except Exception as e:  # noqa: BLE001
        res["status"] = f"erro: {type(e).__name__}: {str(e)[:120]}"
        return res
    if st >= 400 or not body:
        res["status"] = f"http_{st}"
        return res
    res["final_url"] = final
    enc = "utf-8"
    m = re.search(r"charset=([\w-]+)", ctype or "")
    if m:
        enc = m.group(1)
    text = body.decode(enc, "replace")
    p = Page()
    try:
        p.feed(text)
    except Exception:  # noqa: BLE001 - broken HTML: keep what was parsed
        pass
    res["titulo"] = scrub(p.meta.get("og:title") or p.title, 160)
    res["descricao"] = scrub(p.meta.get("og:description") or p.meta.get("description"), 300)
    res["og"] = {k: scrub(v, 300) for k, v in p.meta.items() if k in ("og:site_name", "og:title", "og:type", "og:locale")}
    css = list(p.styles)
    for ln in p.links:
        if "stylesheet" in ln.get("rel", "").lower() and ln.get("href") and res["css_externos"] < 2:
            cu = urllib.parse.urljoin(final, ln["href"])
            if urllib.parse.urlparse(cu).netloc == urllib.parse.urlparse(final).netloc and f.allowed(cu):
                try:
                    cst, _, _, cb = f.get(cu, 800_000)
                    if cst < 400:
                        css.append(cb.decode("utf8", "replace"))
                        res["css_externos"] += 1
                except Exception:  # noqa: BLE001
                    pass
    res["cores"] = brand_colors(css, p.meta.get("theme-color"))
    logo = None
    for im in p.imgs:
        blob = " ".join([im.get("src", ""), im.get("alt", ""), im.get("class", ""), im.get("id", "")]).lower()
        if "logo" in blob and im.get("src") and not im["src"].startswith("data:"):
            logo = urllib.parse.urljoin(final, im["src"])
            break
    if not logo:
        for ln in p.links:
            if "apple-touch-icon" in ln.get("rel", "").lower() and ln.get("href"):
                logo = urllib.parse.urljoin(final, ln["href"])
                break
    res["logo_url"] = logo
    if p.meta.get("og:image"):
        res["og_image"] = urllib.parse.urljoin(final, p.meta["og:image"])
    res["instagram"] = instagram_links(p.anchors)
    res["whatsapp_links"] = whatsapp_links(p.anchors)
    res["whatsapp_texto"] = whatsapp_text(" ".join(p.text))
    if dest is not None and logo and f.allowed(logo):  # logo kept for the paid video (never used/recreated in the preview)
        try:
            lst, _, lct, lb = f.get(logo, MAX_IMG)
            ext = {"image/png": ".png", "image/jpeg": ".jpg", "image/svg+xml": ".svg", "image/webp": ".webp"}.get(lct.split(";")[0].strip())
            if lst < 400 and ext and lb:
                dest.mkdir(parents=True, exist_ok=True)
                (dest / f"logo{ext}").write_bytes(lb)
                res["logo_arquivo"] = f"logo{ext}"
        except Exception:  # noqa: BLE001
            pass
    res["status"] = "ok"
    return res


def collect_instagram(handle: str, f: Fetcher) -> dict:
    """Public og:* of the profile page, no login, only if robots.txt allows our UA; one try, rate limited."""
    res = {"handle": handle, "status": "", "og_title": "", "og_description": "", "avatar_url": None}
    if not handle:
        res["status"] = "sem_instagram"
        return res
    url = f"https://www.instagram.com/{handle.lstrip('@')}/"
    try:
        if not f.allowed(url):
            res["status"] = "nao_coletado: robots.txt do Instagram proíbe coleta automatizada (User-agent: * Disallow: /)"
            return res
        f.ig_wait()
        st, _, _, body = f.get(url, 800_000)
    except Exception as e:  # noqa: BLE001
        res["status"] = f"bloqueado: {type(e).__name__}"
        return res
    if st >= 400 or not body:
        res["status"] = f"bloqueado: http_{st}"
        return res
    p = Page()
    p.feed(body.decode("utf8", "replace"))
    if "og:title" not in p.meta:
        res["status"] = "bloqueado: sem og (login wall)"
        return res
    res.update(status="ok", og_title=scrub(p.meta.get("og:title"), 120), og_description=scrub(p.meta.get("og:description"), 200),
               avatar_url=p.meta.get("og:image"))
    return res


def collect(row: dict, f: Fetcher, dest: Path | None = None) -> dict:
    site = collect_site(row.get("site", ""), f, dest)
    ig_csv = fmt_handle(row.get("instagram"))
    ig = ig_csv or (site["instagram"][0] if site["instagram"] else "")
    where = site.get("final_url") or site["url"]
    ig_src = (("csv (confirmado no link do site)" if ig_csv in site["instagram"] else "csv") if ig_csv
              else (f"site: {where} (link)" if ig else ""))
    wa_csv = fmt_whatsapp(row.get("whatsapp", ""))
    wa_site = (site["whatsapp_links"] or site["whatsapp_texto"] or [None])[0]
    wa = wa_csv or wa_site or ""
    on_site = site["whatsapp_links"] + site["whatsapp_texto"]
    wa_src = (("csv (confirmado no site)" if wa_csv in on_site else "csv") if wa_csv
              else (f"site: {where} ({'link wa.me' if site['whatsapp_links'] else 'texto'})" if wa else ""))
    return {"schema": "simplicio.prospect-coleta/v1", "coletado_em": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "agente": UA,
            "empresa": {"nome": row["nome"].strip(), "cidade": (row.get("cidade") or "").strip(), "setor_csv": (row.get("setor") or "").strip()},
            "site": site, "instagram": collect_instagram(ig, f) | {"handle": ig, "fonte": ig_src},
            "whatsapp": {"numero": wa, "fonte": wa_src, "no_site": site["whatsapp_links"] + [w for w in site["whatsapp_texto"] if w not in site["whatsapp_links"]]},
            "maps": (row.get("maps") or "").strip() or None, "fontes_csv": (row.get("fontes") or "").strip(),
            "lgpd": "só dados da empresa: sem pessoas, e-mails ou telefones pessoais; WhatsApp = canal comercial publicado pela empresa"}


# ------------------------------------------------------------------------------------------------ sector + contract
def campaign_dir(home: Path, campanha: str) -> Path:
    if campanha not in CAMPANHAS:
        raise SystemExit(f"prospect: campanha desconhecida {campanha!r} (disponíveis: {', '.join(CAMPANHAS)})")
    return home / "templates" / CAMPANHAS[campanha]


def load_setores(home: Path, campanha: str) -> dict:
    return json.loads((campaign_dir(home, campanha) / "setores.json").read_text(encoding="utf8"))


def match_setor(setores: dict, setor_csv: str, site_text: str = "") -> tuple[dict, str]:
    for src, txt in (("csv", setor_csv), ("site", site_text)):
        t = norm(txt)
        if not t:
            continue
        for s in setores["setores"]:
            for rx in s["regex"]:
                if re.search(rx, t):
                    return s, f"{src}:{rx}"
    return setores["padrao"], "padrao"


def split_name(nome: str, setor: dict, cidade: str = "", exact: bool = False) -> tuple[str, str]:
    """Lockup NAME (<=16) / SUB (<=20), uppercase. Sector words of the name become SUB; city words are dropped.
    exact=True (CSV nome_curto): the curated brand name is kept whole (only split when longer than 16)."""
    city = {norm(w) for w in re.findall(r"\w+", cidade or "")}
    words = re.findall(r"[\wÀ-ÿ&'.+-]+", nome)
    sec = set() if exact else set(setor.get("nome_setor", []))
    core = [w for w in words if norm(w) not in sec and norm(w) not in city]
    subw = [w for w in words if norm(w) in sec and norm(w) not in ("de", "e", "da", "do")]
    if not core:
        core, subw = words[:1], words[1:]
    name, rest = [], []
    for w in core:
        (name if len(" ".join(name + [w])) <= 16 and not rest else rest).append(w)
    if not name:
        name, rest = [core[0][:16]], core[1:]
    while len(name) > 1 and norm(name[-1]) in ("da", "de", "do", "das", "dos", "e", "&"):
        rest.insert(0, name.pop())
    sub = " ".join(rest) if rest else (" ".join(subw) if subw else setor.get("sub", ""))
    if len(sub) > 20:
        sub = setor.get("sub", "") if len(setor.get("sub", "")) <= 20 else ""
    return " ".join(name).upper(), sub.upper()


def speak_names(display: str, name: str) -> list[str]:
    """Name variants for 'Com carinho, {nome}.' from longest to shortest (used only when a take overflows)."""
    out = []
    nm = name.title() if name.isupper() else name
    for v in (display, nm, nm.split()[0] if nm.split() else display):
        v = v.strip()
        if v and v not in out:
            out.append(v)
    return out


def display_name(row: dict) -> str:
    n = (row.get("nome_curto") or row["nome"]).strip()
    city = (row.get("cidade") or "").split("-")[0].split("/")[0].strip()
    if city and norm(n).endswith(norm(city)) and len(n) > len(city) + 3:
        n = n[: -len(city)].strip(" -|·,")
    return n


def _sub_params(params: dict, scene: str) -> dict:
    return {k: (v.replace("{{dur:s2}}", f"{{{{dur:{scene}}}}}").replace("{{dur:s3}}", f"{{{{dur:{scene}}}}}") if isinstance(v, str) else v)
            for k, v in params.items()}


def build_contract(home: Path, campanha: str, row: dict, coleta: dict, provider: str = "local",
                   variant: dict | None = None) -> tuple[dict, dict]:
    """Deterministic contract from contract.base.yaml + setores.json + real company data. Returns (contract, meta)."""
    variant = variant or {}
    cdir = campaign_dir(home, campanha)
    base = yaml.safe_load((cdir / "contract.base.yaml").read_text(encoding="utf8"))
    S = load_setores(home, campanha)
    site = coleta["site"]
    setor, regra = match_setor(S, row.get("setor", ""), f"{site.get('titulo', '')} {site.get('descricao', '')}")
    d = copy.deepcopy(base)
    disp = display_name(row)
    name, sub = split_name(disp, setor, row.get("cidade", ""), exact=bool(row.get("nome_curto")))
    handle = coleta["instagram"]["handle"] or ""
    city = city_label(row.get("cidade", ""))
    slug = slugify(row["nome"])
    camp = S["campanha"]
    d["cliente"] = {"slug": slug, "nome": row["nome"].strip(), "drive_nome": drive_name(disp), "coleta": "coleta.json"}
    d["campanha"] = {"id": camp["campanha_id"], "ano": 2026, "titulo": camp["titulo"],
                     "objetivo": "Prévia com marca d'água SimpleTI para oferecer o vídeo (venda ativa; não publicar)"}
    colors = site.get("cores") or []
    i3 = variant.get("vo3", 0)
    i4 = variant.get("vo4", 0)
    names = speak_names(disp, name)
    spoken = names[min(i4, len(names) - 1)]
    for s in d["cenas"]:
        for m in s["motion"]:
            b = m.get("bloco")
            if b == "s2-main":
                m["padrao"], m["params"] = setor["s2"]["padrao"], _sub_params(setor["s2"]["params"], "s2")
            elif b == "s3-main":
                m["padrao"], m["params"] = setor["s3"]["padrao"], _sub_params(setor["s3"]["params"], "s3")
            elif b == "s3-words":
                m["params"]["lines"] = setor["lines3"][min(i3, len(setor["lines3"]) - 1)]
            elif b == "s4-lockup":
                lp = m["params"]
                lp.update(name=name, sub=sub, tagline=camp["tagline"], handle=handle if len(handle) <= 28 else "", city=city[:32],
                          accent=accent_from(colors, lp["accent"]))
            elif b == "s4-words":
                m["params"]["lines"] = f"Com carinho,|{spoken}."
        if s["id"] == "s3":
            s["fala"]["texto"] = setor["vo3"][min(i3, len(setor["vo3"]) - 1)]
            s["fala"].pop("say", None)
            if not setor.get("scrub"):
                s["sfx"] = [x for x in s.get("sfx", []) if not x["id"].startswith("scrub")]
            s["tela"] = [s["fala"]["texto"] + " (palavra a palavra)"]
        if s["id"] == "s4":
            s["fala"]["texto"] = f"Com carinho, {spoken}."
            s["fala"].pop("say", None)
            s["tela"] = [f"{name} / {sub}", camp["tagline"], handle or "(sem @)", city, f"Com carinho, / {spoken}."]
    d["voz"]["provider"] = provider
    d["drive"] = {"caminho": f"simplicio-video/clientes/{d['cliente']['drive_nome']}/2026/{camp['campanha_id']}",
                  "arquivo": f"{ascii_name(disp) or 'Empresa'} - Previa Dia das Criancas 16s - v01.mp4",
                  "status": "prévia de venda ativa (não publicar)"}
    meta = {"setor": setor["id"], "regra": regra, "lockup": [name, sub], "fala_nome": spoken, "vo3": d["cenas"][2]["fala"]["texto"],
            "accent": next(m["params"]["accent"] for m in d["cenas"][3]["motion"] if m.get("bloco") == "s4-lockup")}
    return d, meta


def write_contract(path: Path, d: dict, row: dict, meta: dict):
    hdr = (f"# simplicio.video-contract/v1 — PRÉVIA de venda ativa gerada por `simplicio-video prospect` (determinístico, sem LLM).\n"
           f"# Empresa: {row['nome'].strip()} · setor {meta['setor']} ({meta['regra']}). Fatos: só coleta.json (nome, @, cidade) + textos\n"
           f"# genéricos da data em templates/sazonal-dia-das-criancas/setores.json. Sem preço, promoção ou fato inventado.\n")
    path.write_text(hdr + yaml.safe_dump(d, allow_unicode=True, sort_keys=False, width=140), encoding="utf8")


# ------------------------------------------------------------------------------------------------ batch
def read_csv(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8-sig") as fh:
        rd = csv.DictReader(fh)
        rows = []
        for r in rd:
            r = {norm(k or "").replace(" ", "_"): (v or "").strip() for k, v in r.items()}
            if r.get("nome"):
                rows.append(r)
    if not rows:
        raise SystemExit(f"prospect: {path} has no rows with 'nome'")
    return rows


def unique_slugs(rows: list[dict]) -> list[str]:
    seen: dict[str, int] = {}
    out = []
    for r in rows:
        s = slugify(r["nome"])
        seen[s] = seen.get(s, 0) + 1
        out.append(s if seen[s] == 1 else f"{s}-{seen[s]}")
    return out


def _voice_fit(pdir: Path, home: Path, campanha: str, row: dict, coleta: dict, provider: str, log) -> tuple[dict, dict]:
    from . import voice
    from .contract import load
    variant = {"vo3": 0, "vo4": 0}
    for _ in range(4):
        d, meta = build_contract(home, campanha, row, coleta, provider, variant)
        write_contract(pdir / "contract.yaml", d, row, meta)
        c = load(pdir / "contract.yaml")
        try:
            voice.run(c, log=log)
            return d, meta
        except voice.VoiceError as e:
            over = re.findall(r"(vo\d):", str(e))
            if not over or not set(over) <= {"vo3", "vo4"}:
                raise
            for v in over:
                variant[v] += 1
            if variant["vo3"] > 1 or variant["vo4"] > 2:
                raise
            log(f"voz: {', '.join(over)} maior que o slot -> variante mais curta {variant}")
    raise SystemExit("voice did not fit")


def process(row: dict, slug: str, out: Path, home: Path, f: Fetcher, campanha: str = "dia-das-criancas", provider: str = "local",
            force: bool = False, recollect: bool = False, render: bool = True, log=print) -> dict:
    pdir = out / slug
    pdir.mkdir(parents=True, exist_ok=True)
    rj = pdir / "result.json"
    prev = pdir / "preview.mp4"
    if not force and render and prev.is_file() and rj.is_file():
        old = json.loads(rj.read_text(encoding="utf8"))
        if old.get("status") == "ok":
            return old | {"status": "ok", "motivo": "pulado (já existia)", "pulado": True}
    t0 = time.time()
    res: dict = {"nome": row["nome"], "slug": slug, "status": "erro", "motivo": "", "timings_s": {}}
    try:
        cj = pdir / "coleta.json"
        if cj.is_file() and not recollect:
            coleta = json.loads(cj.read_text(encoding="utf8"))
        else:
            coleta = collect(row, f, pdir / "coleta")
            cj.write_text(json.dumps(coleta, indent=2, ensure_ascii=False) + "\n", encoding="utf8")
        res["timings_s"]["coleta"] = round(time.time() - t0, 2)
        res["coleta"] = {"site": coleta["site"]["status"], "instagram": coleta["instagram"]["status"],
                         "handle": coleta["instagram"]["handle"], "handle_fonte": coleta["instagram"]["fonte"],
                         "whatsapp": coleta["whatsapp"]["numero"], "whatsapp_fonte": coleta["whatsapp"]["fonte"],
                         "titulo": coleta["site"]["titulo"], "cores": coleta["site"]["cores"],
                         "logo": coleta["site"]["logo_arquivo"] or coleta["site"]["logo_url"]}
        if not render:
            d, meta = build_contract(home, campanha, row, coleta, provider)
            write_contract(pdir / "contract.yaml", d, row, meta)
            res.update(status="contrato", motivo="--so-contrato", meta=meta)
        else:
            t1 = time.time()
            d, meta = _voice_fit(pdir, home, campanha, row, coleta, provider, log)
            res["meta"] = meta
            res["timings_s"]["voz"] = round(time.time() - t1, 2)
            from . import render as rmod
            from .contract import load
            t2 = time.time()
            man = rmod.render_preview(load(pdir / "contract.yaml"), out=prev, log=log)
            res["timings_s"]["render"] = round(time.time() - t2, 2)
            res["preview"] = {"path": str(prev), "sha256": man["preview"]["sha256"], "duration_s": man["preview"]["duration_s"],
                              "bytes": man["preview"]["bytes"]}
            res.update(status="ok", motivo="")
    except BaseException as e:  # noqa: BLE001 - one bad row never stops the batch
        if isinstance(e, KeyboardInterrupt):
            raise
        res["motivo"] = f"{type(e).__name__}: {str(e).strip().splitlines()[0][:240] if str(e).strip() else ''}"
    res["timings_s"]["total"] = round(time.time() - t0, 2)
    rj.write_text(json.dumps(res, indent=2, ensure_ascii=False) + "\n", encoding="utf8")
    return res


def report_row(row: dict, res: dict) -> dict:
    c = res.get("coleta", {})
    m = res.get("meta", {})
    return {"nome": row["nome"], "slug": res["slug"], "setor": row.get("setor", ""), "setor_regra": f"{m.get('setor', '')} ({m.get('regra', '')})" if m else "",
            "cidade": row.get("cidade", ""), "instagram": c.get("handle", ""), "instagram_fonte": c.get("handle_fonte", ""),
            "whatsapp": c.get("whatsapp", ""), "whatsapp_fonte": c.get("whatsapp_fonte", ""), "site": row.get("site", ""),
            "site_status": c.get("site", ""), "instagram_status": c.get("instagram", ""), "titulo_site": c.get("titulo", ""),
            "cores": " ".join(c.get("cores") or []), "logo": c.get("logo") or "", "fontes": row.get("fontes", ""),
            "status": res["status"], "motivo": res.get("motivo", ""), "preview": (res.get("preview") or {}).get("path", ""),
            "tempo_s": res.get("timings_s", {}).get("total", ""), "tempo_render_s": res.get("timings_s", {}).get("render", "")}


def run_batch(csv_path: Path, out: Path | None = None, lote: str | None = None, campanha: str = "dia-das-criancas",
              provider: str = "local", jobs: int = 1, force: bool = False, recollect: bool = False, render: bool = True,
              limit: int | None = None, fetcher: Fetcher | None = None, log=print) -> dict:
    home = paths.home()
    csv_path = Path(csv_path)
    lote = lote or slugify(csv_path.stem)
    out = Path(out) if out else home / "prospects" / lote
    out.mkdir(parents=True, exist_ok=True)
    rows = read_csv(csv_path)[: limit or None]
    slugs = unique_slugs(rows)
    f = fetcher or Fetcher()
    t0 = time.time()
    lk = threading.Lock()

    def one(i):
        r = process(rows[i], slugs[i], out, home, f, campanha, provider, force, recollect, render,
                    log=lambda s, n=slugs[i]: log(f"[{n}] {s}"))
        with lk:
            log(f"[{slugs[i]}] {r['status']} {r.get('motivo', '')} ({r.get('timings_s', {}).get('total', '?')} s)")
        return r

    with ThreadPoolExecutor(max_workers=max(1, jobs)) as ex:
        results = list(ex.map(one, range(len(rows))))
    total = round(time.time() - t0, 2)
    rep = out / "lote.csv"
    with open(rep, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=REPORT_COLS)
        w.writeheader()
        for row, res in zip(rows, results):
            w.writerow(report_row(row, res))
    done = [r for r in results if r["status"] == "ok" and not r.get("pulado")]
    summary = {"lote": lote, "saida": str(out), "relatorio": str(rep), "linhas": len(rows), "ok": sum(r["status"] == "ok" for r in results),
               "pulados": sum(bool(r.get("pulado")) for r in results), "erros": sum(r["status"] == "erro" for r in results),
               "tempo_total_s": total, "tempo_medio_previa_s": round(sum(r["timings_s"]["total"] for r in done) / len(done), 2) if done else None,
               "jobs": jobs, "provider": provider, "campanha": campanha}
    (out / "lote.json").write_text(json.dumps({"summary": summary, "results": results}, indent=2, ensure_ascii=False) + "\n", encoding="utf8")
    log(f"prospect: {summary['ok']}/{summary['linhas']} ok ({summary['pulados']} pulados, {summary['erros']} erros) em {total} s -> {rep}")
    return summary
