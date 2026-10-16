"""Openverse: a local library of images and audio, searched on the public API and reviewed per request.

Flow: `search` (cached) -> `get` (safe download into the library) -> `library review --folha` (objective signals for the
reviewer to LOOK at) -> `library review --aprovar|--reprovar` (verdict per pair asset+request) -> `library export` (copies
only what was approved for that request, with its credit line).

Rules that do not bend:
- Zero tokens: no LLM call. The engine does NOT decide whether an asset matches a request; it builds a deterministic sheet
  (dimensions, sharpness, brightness, loudness, silence, clipping, thumbnail, spectrogram, text hint) and records the verdict
  of whoever reviewed, per pair (sha256 of the asset, normalized text of the request).
- License: only cc0, pdm and by by default (safe for commercial use and editing). by-sa, by-nc and by-nd only by explicit
  option, with a warning. The license comes from the sources and Openverse itself says to check the origin
  (`foreign_landing_url`): this is not legal advice. An item without a known license is never downloaded; CC BY without an
  author is never exported.
- The download treats the server as untrusted: https on port 443 only, resolves the host and refuses non-public addresses
  (private, loopback, link-local, reserved) before and after every redirect, connects to the validated IP, caps the size
  (25 MB image, 50 MB audio), decides the type from the bytes (signature) and never from Content-Type, names the file by its
  sha256 and never runs anything from it.
- Optional OAuth2 credentials only through environment variables (OPENVERSE_CLIENT_ID and OPENVERSE_CLIENT_SECRET); never in
  an argument, log, index, cache, sheet or output.
- MCP (`video.openverse`) only searches, lists, shows, builds the sheet and records the verdict. Download and export are
  terminal-only: the agent does not choose where anything is written.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import http.client
import ipaddress
import json
import os
import re
import shlex
import shutil
import socket
import ssl
import sys
import tempfile
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode, urljoin, urlparse

from . import __version__, paths
from .swap_providers import http as _api_http

__all__ = ["OpenverseError", "search", "get", "library_list", "library_show", "review_sheet", "review", "review_status", "export",
           "credits", "export_name", "text_score", "normalize_pedido", "parse_licenses", "status_summary", "run_openverse"]

API_BASE = "https://api.openverse.org/v1"
SCHEMA_INDEX = "simplicio.openverse-library/v1"
SCHEMA_SEARCH = "simplicio.openverse-search/v1"
SCHEMA_SHEET = "simplicio.openverse-review-sheet/v1"
TIPOS = ("imagem", "audio")
ENDPOINT = {"imagem": "images", "audio": "audio"}
TIPO_PT = {"imagem": "imagem", "audio": "áudio"}
DEFAULT_LICENSES = ("cc0", "pdm", "by")
LICENSE_ORDER = ("cc0", "pdm", "by", "by-sa", "by-nc", "by-nd", "by-nc-sa", "by-nc-nd")
ENV_ID, ENV_SECRET = "OPENVERSE_CLIENT_ID", "OPENVERSE_CLIENT_SECRET"
MAX_PAGE_ANON, MAX_PAGE_AUTH = 20, 50
MAX_QUERY_CHARS = 200
MAX_PEDIDO_CHARS = 500
MAX_TEXT_CHARS = 1000
MAX_TAGS = 20
MAX_BYTES = {"imagem": 25 * 1024 * 1024, "audio": 50 * 1024 * 1024}
MAX_REDIRECTS = 5
READ_BLOCK = 64 * 1024
HTTP_TIMEOUT = 30
API_MAX_BYTES = 8 * 1024 * 1024  # a search page is a few hundred KB; anything bigger is not the API we know
DOWNLOAD_DEADLINE_S = 300  # total time of one download (the socket timeout does not catch a server that drips one byte at a time)
STALE_DAYS = 30  # `get` warns when the search metadata it uses is older than this
CREDITS_NAME = "CREDITS-openverse.md"
USER_AGENT = f"simplicio-video/{__version__} (openverse client)"
UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
_SECRET_TEXT_RE = re.compile(r"(?<![A-Za-z0-9_])(sk-[A-Za-z0-9_-]{8,}|AIza[0-9A-Za-z_-]{16,}|gh[pousr]_[A-Za-z0-9]{16,}|xox[a-z]-[A-Za-z0-9-]{8,}|"
                             r"eyJ[A-Za-z0-9_-]{10,}|ya29\.[A-Za-z0-9_-]{10,}|AQ\.[A-Za-z0-9_-]{10,}|Bearer\s+[A-Za-z0-9._-]{16,})")
STOPWORDS = frozenset("""a o as os um uma uns umas de da do das dos em no na nos nas ao aos para por com sem que e ou se
the an of and in on at to for with by or is are be""".split())

_TOKEN: dict = {}  # OAuth2 token lives in process memory only: it never goes to disk


class OpenverseError(Exception):
    """Usage or network error. The message goes through the redaction filter on creation, so no credential leaves through it."""

    def __init__(self, message: str):
        super().__init__(scrub(str(message)))


# ---------------------------------------------------------------------------------------------------------- secrets

def _secret_values() -> list[str]:
    vals = [os.environ.get(ENV_ID, "").strip(), os.environ.get(ENV_SECRET, "").strip(), str(_TOKEN.get("valor") or "")]
    return [v for v in vals if len(v) >= 6]


def scrub(text: str) -> str:
    """Hide the environment credentials, the token and anything shaped like a key."""
    for v in _secret_values():
        text = text.replace(v, "***")
    return _SECRET_TEXT_RE.sub("***", text)


def _clean_text(value, campo: str, limite: int = MAX_TEXT_CHARS) -> str:
    """Free text typed by the user (request, reason, reviewer): refuses the environment credential, masks key-shaped text."""
    text = " ".join(str(value or "").split())
    for v in _secret_values():
        if v in text:
            raise OpenverseError(f"segredo (credencial do Openverse) encontrado em {campo}: nada foi gravado")
    if len(text) > limite:
        raise OpenverseError(f"{campo} acima de {limite} caracteres")
    return _SECRET_TEXT_RE.sub("***", text)


# ---------------------------------------------------------------------------------------------------------- licenses

def _licenses() -> dict:
    doc = json.loads((paths.data_dir() / "openverse" / "licenses.json").read_text(encoding="utf8"))
    return {r["id"]: r for r in doc["licencas"]}


def parse_licenses(text) -> tuple[list[str], list[str]]:
    """`cc0,pdm,by` -> (ids in canonical order, warnings about what each restrictive license implies)."""
    pieces = [p.strip().lower() for p in (text if isinstance(text, (list, tuple)) else str(text).split(","))]
    if not pieces or any(not p for p in pieces):
        raise OpenverseError("--licencas vazia ou com vírgula sobrando (exemplo: cc0,pdm,by)")
    bad = [p for p in pieces if p not in LICENSE_ORDER]
    if bad:
        raise OpenverseError(f"licença desconhecida ou não suportada: {', '.join(bad)} (use {', '.join(LICENSE_ORDER)})")
    ordered = [lic for lic in LICENSE_ORDER if lic in pieces]
    table = _licenses()
    return ordered, [f"{lic}: {table[lic]['aviso']}" for lic in ordered if table[lic].get("aviso")]


def license_label(lic: str | None, versao: str | None) -> str:
    rec = _licenses().get(lic or "")
    nome = rec["nome"] if rec else (lic or "sem licença").upper()
    v = versao or (rec.get("versao_padrao") if rec else None)
    return f"{nome} {v}" if v else nome


# ---------------------------------------------------------------------------------------------------------- folder and index

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _stamp() -> str:
    return _now().strftime("%Y-%m-%dT%H:%M:%SZ")


def library_dir() -> Path:
    """OPENVERSE_LIBRARY_DIR, else <SIMPLICIO_VIDEO_DATA or ~/.simplicio-video>/openverse-library."""
    explicit = os.environ.get("OPENVERSE_LIBRARY_DIR")
    if explicit:
        return Path(explicit).expanduser().resolve()
    data = os.environ.get("SIMPLICIO_VIDEO_DATA")
    base = Path(data).expanduser() if data else Path.home() / ".simplicio-video"
    return (base / "openverse-library").resolve()


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def _dump(obj) -> str:
    """JSON for disk. Refuses to write if a credential from the environment is in it. Key-shaped text is NOT masked here:
    API data (URLs, titles) must stay exact; free text typed by the user is masked in `_clean_text` before it gets here."""
    return _guard(json.dumps(obj, indent=2, ensure_ascii=False) + "\n")


def _guard(text: str) -> str:
    for v in _secret_values():
        if v in text:
            raise OpenverseError("segredo (credencial do Openverse) encontrado no texto a gravar: nada foi gravado")
    return text


def _empty_index() -> dict:
    return {"schema": SCHEMA_INDEX, "itens": {}, "revisoes": [], "exportacoes": []}


def _load_index() -> dict:
    path = library_dir() / "index.json"
    if not path.is_file():
        return _empty_index()
    try:
        doc = json.loads(path.read_text(encoding="utf8"))
    except (OSError, ValueError):
        raise OpenverseError(f"índice ilegível: {path} (não foi alterado)") from None
    if not isinstance(doc, dict) or doc.get("schema") != SCHEMA_INDEX or not isinstance(doc.get("itens"), dict):
        raise OpenverseError(f"índice com schema desconhecido: {path} (esperado {SCHEMA_INDEX})")
    doc.setdefault("revisoes", [])
    doc.setdefault("exportacoes", [])
    return doc


@contextlib.contextmanager
def _locked(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        import fcntl
    except ImportError:  # pragma: no cover (Windows)
        yield
        return
    with open(path, "a") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


@contextlib.contextmanager
def _index_tx():
    """Read, let the caller change, and write the index in one go (with a cross-process lock). An error in the middle writes nothing."""
    lib = library_dir()
    with _locked(lib / ".index.lock"):
        idx = _load_index()
        yield idx
        _atomic_write(lib / "index.json", _dump(idx))


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _check_id(id_) -> str:
    id_ = str(id_ or "").strip()
    if not UUID_RE.match(id_):
        raise OpenverseError(f"id inválido: o id do Openverse é um UUID (exemplo 9d8abc2c-c4dd-4dce-8164-cadd775befcf), recebi {id_[:60]!r}")
    return id_.lower()


_FILE_RE = re.compile(r"^files/[0-9a-f]{64}\.[a-z0-9]{2,5}$")
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")


def _item(idx: dict, id_: str) -> dict:
    rec = idx["itens"].get(id_)
    if rec is None:
        raise OpenverseError(f"o id {id_} não está na biblioteca (use `simplicio-video openverse get {id_}`)")
    if not (_FILE_RE.match(str(rec.get("arquivo"))) and _SHA_RE.match(str(rec.get("sha256"))) and rec["arquivo"][6:70] == rec["sha256"]):
        raise OpenverseError(f"índice inválido para o id {id_}: o campo arquivo precisa ser files/<sha256>.<ext> (o índice foi editado à mão?)")
    return rec


def _integridade(rec: dict) -> str:
    f = library_dir() / rec["arquivo"]
    if not f.is_file():
        return "ausente"
    return "ok" if sha256_file(f) == rec["sha256"] else "alterado"


def _require_integridade(rec: dict) -> Path:
    estado = _integridade(rec)
    if estado != "ok":
        raise OpenverseError(f"arquivo {estado} na biblioteca ({rec['arquivo']}): o sha256 não confere com o índice. "
                             f"Baixe de novo com `simplicio-video openverse get {rec['id']} --atualizar`")
    return library_dir() / rec["arquivo"]


# ---------------------------------------------------------------------------------------------------------- request and text

def normalize_pedido(text) -> str:
    """Lowercase, no accents, no punctuation, collapsed spaces: the key of a request in the review."""
    t = unicodedata.normalize("NFKD", str(text or ""))
    t = "".join(c for c in t if not unicodedata.combining(c)).lower()
    return " ".join(re.sub(r"[\W_]+", " ", t).split())


def _clean_pedido(pedido) -> tuple[str, str]:
    original = " ".join(str(pedido or "").split())
    if not original:
        raise OpenverseError("--pedido vazio: diga o que o vídeo precisa neste ponto (a revisão vale para o par ativo+pedido)")
    if len(original) > MAX_PEDIDO_CHARS:
        raise OpenverseError(f"--pedido acima de {MAX_PEDIDO_CHARS} caracteres")
    original = _clean_text(original, "o pedido", MAX_PEDIDO_CHARS)
    norm = normalize_pedido(original)
    if not norm:
        raise OpenverseError("--pedido sem letras ou números")
    return original, norm


def _tokens(text: str) -> list[str]:
    out: list[str] = []
    for t in normalize_pedido(text).split():
        if len(t) >= 2 and t not in STOPWORDS and t not in out:
            out.append(t)
    return out


def text_score(pedido: str, titulo: str | None, tags) -> dict:
    """Deterministic text hint: the fraction of the request words that appear in the Openverse title and tags."""
    pedido_t = _tokens(pedido)
    alvo = set(_tokens(f"{titulo or ''} {' '.join(tags or [])}"))
    comum = [t for t in pedido_t if t in alvo]
    return {"tokens_pedido": pedido_t, "em_comum": comum, "faltando": [t for t in pedido_t if t not in alvo],
            "pontuacao": round(len(comum) / len(pedido_t), 6) if pedido_t else 0.0,
            "aviso": "Pista textual, não é veredito: compara só palavras do pedido com o título e as tags do Openverse (em geral em inglês); "
                     "pontuação baixa não reprova (traduza o pedido para conferir) e pontuação alta não aprova (olhe o ativo)."}


# ---------------------------------------------------------------------------------------------------------- API

def _credentials() -> tuple[str, str] | None:
    cid, sec = os.environ.get(ENV_ID, "").strip(), os.environ.get(ENV_SECRET, "").strip()
    if bool(cid) != bool(sec):
        raise OpenverseError(f"defina {ENV_ID} e {ENV_SECRET} juntas (ou nenhuma das duas)")
    return (cid, sec) if cid else None


def _bearer() -> str | None:
    cred = _credentials()
    if cred is None:
        return None
    if _TOKEN.get("valor") and _TOKEN.get("cid") == cred[0] and _TOKEN.get("expira", 0) > time.time() + 60:
        return _TOKEN["valor"]
    resp = _call("POST", f"{API_BASE}/auth_tokens/token/", form={"grant_type": "client_credentials", "client_id": cred[0],
                                                                  "client_secret": cred[1]})
    doc = resp.json() if resp.status == 200 else None
    if not isinstance(doc, dict) or not doc.get("access_token"):
        raise _api_error(resp, "token OAuth2")
    _TOKEN.clear()
    _TOKEN.update(valor=str(doc["access_token"]), cid=cred[0], expira=time.time() + float(doc.get("expires_in") or 600))
    return _TOKEN["valor"]


def _call(method: str, url: str, headers: dict | None = None, form: dict | None = None):
    base = {"Accept": "application/json", "User-Agent": USER_AGENT}
    base.update(headers or {})
    kw = {"timeout": HTTP_TIMEOUT, "follow_redirects": False, "max_bytes": API_MAX_BYTES}  # urllib would forward the bearer token on a redirect
    try:
        if form is not None:
            return _api_http.request(method, url, headers=base, form=form, **kw)
        return _api_http.request(method, url, headers=base, **kw)
    except _api_http.NetworkError as e:
        raise OpenverseError(f"sem rede para falar com o Openverse ({e}). Repita quando houver rede, "
                             "ou repita uma busca que já esteja no cache") from None


def _api_error(resp, o_que: str) -> OpenverseError:
    detalhe = ""
    doc = resp.json()
    if isinstance(doc, dict):
        detalhe = str(doc.get("detail") or doc.get("error") or "")[:200]
    extra = ""
    if resp.status == 429:
        espera = resp.headers.get("retry-after")
        extra = (f" Limite de requisições da API atingido; espere {espera} s." if espera else " Limite de requisições da API atingido.") + \
            " A busca repetida sai do cache; credenciais OAuth2 (OPENVERSE_CLIENT_ID e OPENVERSE_CLIENT_SECRET) aumentam o limite."
    elif resp.status == 401:
        extra = " Credencial recusada ou token expirado."
    elif 300 <= resp.status < 400:
        extra = " A API não deveria redirecionar: o redirecionamento não foi seguido (a credencial não é enviada a outro host)."
    return OpenverseError(f"o Openverse recusou {o_que} (HTTP {resp.status}){': ' + detalhe if detalhe else ''}.{extra}")


def _quota(resp) -> dict | None:
    q = {k: v for k, v in resp.headers.items() if k.startswith("x-ratelimit-available")}
    return q or None


def _api_get(path: str, params: dict | None = None):
    url = f"{API_BASE}/{path}" + (f"?{urlencode(sorted(params.items()))}" if params else "")
    bearer = _bearer()
    return _call("GET", url, headers={"Authorization": f"Bearer {bearer}"} if bearer else None)


def _s(value, limite: int = 2000) -> str | None:
    if value is None:
        return None
    # one line, no control characters (ESC, DEL, C1): API text goes to the terminal and to the credits file
    text = "".join(c for c in " ".join(str(value).split()) if c.isprintable())
    return text[:limite] or None


def _int(value) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _norm_item(raw: dict, tipo: str) -> dict:
    tags: list[str] = []
    for t in raw.get("tags") or []:
        name = _s(t.get("name") if isinstance(t, dict) else t, 80)
        if name and name not in tags:
            tags.append(name)
        if len(tags) >= MAX_TAGS:
            break
    lic = _s(raw.get("license"))
    item = {"id": _s(raw.get("id")), "tipo": tipo, "titulo": _s(raw.get("title")), "autor": _s(raw.get("creator")),
            "autor_url": _s(raw.get("creator_url")), "licenca": lic.lower() if lic else None,
            "licenca_versao": _s(raw.get("license_version")), "licenca_url": _s(raw.get("license_url")),
            "atribuicao": _s(raw.get("attribution")), "origem_url": _s(raw.get("foreign_landing_url")),
            "url_arquivo": _s(raw.get("url")), "provedor": _s(raw.get("provider")), "fonte": _s(raw.get("source")),
            "tags": tags, "filetype": _s(raw.get("filetype")), "mature": bool(raw.get("mature"))}
    if tipo == "imagem":
        item.update(largura=_int(raw.get("width")), altura=_int(raw.get("height")))
    else:
        ms = raw.get("duration")
        item.update(duracao_s=round(float(ms) / 1000, 3) if isinstance(ms, (int, float)) else None,
                    bit_rate=_int(raw.get("bit_rate")), taxa_amostragem_hz=_int(raw.get("sample_rate")))
    return item


def _max_page_size() -> int:
    return MAX_PAGE_AUTH if _credentials() else MAX_PAGE_ANON


def _check_search_args(tipo, consulta, licencas, minimo_largura, duracao_min, duracao_max, limite, pagina):
    if tipo not in TIPOS:
        raise OpenverseError(f"tipo inválido: {tipo!r} (use imagem ou audio)")
    consulta = " ".join(str(consulta or "").split())
    if not consulta:
        raise OpenverseError("consulta vazia: passe --consulta \"o que procurar\" (títulos e tags costumam estar em inglês)")
    if len(consulta) > MAX_QUERY_CHARS:
        raise OpenverseError(f"consulta acima de {MAX_QUERY_CHARS} caracteres (limite da API)")
    lic, avisos = parse_licenses(licencas)
    if tipo == "audio" and minimo_largura is not None:
        raise OpenverseError("--minimo-largura só vale para imagem")
    if tipo == "imagem" and (duracao_min is not None or duracao_max is not None):
        raise OpenverseError("--duracao-min e --duracao-max só valem para áudio (duração)")
    for nome, v in (("--minimo-largura", minimo_largura), ("--duracao-min", duracao_min), ("--duracao-max", duracao_max)):
        if v is not None and not v >= 0:
            raise OpenverseError(f"{nome} precisa ser um número maior ou igual a zero")
    teto = _max_page_size()
    if not isinstance(limite, int) or limite < 1:
        raise OpenverseError("--limite precisa ser um inteiro maior que zero")
    if limite > teto:
        raise OpenverseError(f"--limite máximo é {teto} por página" +
                             (" (sobe para 50 com OPENVERSE_CLIENT_ID e OPENVERSE_CLIENT_SECRET)" if teto == MAX_PAGE_ANON else "") +
                             "; use --pagina para continuar")
    if not isinstance(pagina, int) or pagina < 1:
        raise OpenverseError("a página (--pagina) precisa ser um inteiro maior ou igual a 1")
    return consulta, lic, avisos


def _api_params(consulta: str, lic: list[str], limite: int, pagina: int) -> dict:
    tab = _licenses()
    params = {"q": consulta, "license": ",".join(lic), "page_size": str(limite), "page": str(pagina), "mature": "false"}
    if all(tab[x]["uso_comercial"] and tab[x]["permite_modificacao"] for x in lic):
        params["license_type"] = "commercial,modification"
    return params


def _cache_path(tipo: str, params: dict) -> Path:
    key = hashlib.sha256(json.dumps({"api": API_BASE, "tipo": tipo, "params": params}, sort_keys=True).encode("utf8")).hexdigest()
    return library_dir() / "cache" / f"{key}.json"


def _read_cache(path: Path) -> dict | None:
    try:
        doc = json.loads(path.read_text(encoding="utf8"))
    except (OSError, ValueError):
        return None
    return doc if isinstance(doc, dict) and doc.get("schema") == SCHEMA_SEARCH and isinstance(doc.get("resultados"), list) else None


def _safe_results(raw_results, tipo: str, lic: list[str]) -> tuple[list[dict], dict]:
    """Defense in depth: the API may return what was not asked for. Keep only what has an id, a requested license, a URL and is not mature."""
    desc = {"licenca_fora_do_pedido": 0, "sem_licenca": 0, "sem_url": 0, "mature": 0, "id_invalido": 0}
    ok: list[dict] = []
    for raw in raw_results or []:
        if not isinstance(raw, dict):
            continue
        item = _norm_item(raw, tipo)
        if not item["id"] or not UUID_RE.match(item["id"]):
            desc["id_invalido"] += 1
        elif not item["licenca"]:
            desc["sem_licenca"] += 1
        elif item["licenca"] not in lic:
            desc["licenca_fora_do_pedido"] += 1
        elif not item["url_arquivo"]:
            desc["sem_url"] += 1
        elif item["mature"]:
            desc["mature"] += 1
        else:
            item["id"] = item["id"].lower()
            ok.append(item)
    return ok, desc


def search(tipo, consulta, licencas="cc0,pdm,by", minimo_largura=None, duracao_min=None, duracao_max=None, limite=10, pagina=1,
           atualizar=False) -> dict:
    """Search images or audio on Openverse. The same query comes from the cache (no network) until `atualizar`."""
    consulta, lic, avisos = _check_search_args(tipo, consulta, licencas, minimo_largura, duracao_min, duracao_max, limite, pagina)
    params = _api_params(consulta, lic, limite, pagina)
    path = _cache_path(tipo, params)
    doc = None if atualizar else _read_cache(path)
    do_cache = doc is not None
    cota = None
    if doc is None:
        resp = _api_get(f"{ENDPOINT[tipo]}/", params)
        body = resp.json() if resp.status == 200 else None
        if not isinstance(body, dict) or not isinstance(body.get("results"), list):
            raise _api_error(resp, f"a busca de {TIPO_PT[tipo]}") if resp.status != 200 else \
                OpenverseError("resposta do Openverse sem a lista `results`: nada foi gravado")
        cota = _quota(resp)
        resultados, desc = _safe_results(body["results"], tipo, lic)
        doc = {"schema": SCHEMA_SEARCH, "consultado_em": _stamp(), "parametros": params, "total_api": _int(body.get("result_count")),
               "descartados": desc, "resultados": resultados}
        _atomic_write(path, _dump(doc))
    desc = dict(doc.get("descartados") or {})
    desc["filtro_local"] = 0
    final: list[dict] = []
    idx = _load_index()
    for item in doc["resultados"]:
        if minimo_largura is not None and not (item.get("largura") and item["largura"] >= minimo_largura):
            desc["filtro_local"] += 1
        elif duracao_min is not None and not (item.get("duracao_s") is not None and item["duracao_s"] >= duracao_min):
            desc["filtro_local"] += 1
        elif duracao_max is not None and not (item.get("duracao_s") is not None and item["duracao_s"] <= duracao_max):
            desc["filtro_local"] += 1
        else:
            final.append({**item, "na_biblioteca": item["id"] in idx["itens"]})
    return {"schema": SCHEMA_SEARCH, "tipo": tipo, "consulta": consulta, "licencas": lic, "avisos": avisos, "do_cache": do_cache,
            "consultado_em": doc["consultado_em"], "pagina": pagina, "limite": limite, "total_api": doc.get("total_api"),
            "cota_api": cota, "descartados": desc, "resultados": final}


def _find_in_cache(id_: str) -> tuple[dict, str] | None:
    best = None
    for f in sorted((library_dir() / "cache").glob("*.json")):
        doc = _read_cache(f)
        if doc is None:
            continue
        for item in doc["resultados"]:
            if item.get("id") == id_ and (best is None or doc["consultado_em"] > best[1]):
                best = (item, doc["consultado_em"])
    return best


# ---------------------------------------------------------------------------------------------------------- safe download

def detect_format(head: bytes) -> tuple[str, str, str] | None:
    """(format, media type, extension) from the first bytes. The server's Content-Type and extension do not count."""
    if head.startswith(b"\xff\xd8\xff"):
        return "jpeg", "imagem", "jpg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png", "imagem", "png"
    if head[:6] in (b"GIF87a", b"GIF89a"):
        return "gif", "imagem", "gif"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp", "imagem", "webp"
    if head[:4] == b"RIFF" and head[8:12] == b"WAVE":
        return "wav", "audio", "wav"
    if head[:4] == b"OggS":
        return "ogg", "audio", "ogg"
    if head[:4] == b"fLaC":
        return "flac", "audio", "flac"
    if head[:3] == b"ID3":
        return "mp3", "audio", "mp3"
    if len(head) >= 3 and head[0] == 0xFF and head[1] & 0xE0 == 0xE0 and (head[1] >> 3) & 3 != 1 and (head[1] >> 1) & 3 != 0 \
            and head[2] >> 4 != 0xF:
        return "mp3", "audio", "mp3"
    if head[4:8] == b"ftyp" and head[8:12] in (b"M4A ", b"M4B ", b"mp42", b"isom", b"iso2"):
        return "m4a", "audio", "m4a"
    return None


def _is_public(ip_text: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_text.split("%")[0])
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address):
        if ip.ipv4_mapped is not None:
            ip = ip.ipv4_mapped
        elif ip in ipaddress.ip_network("64:ff9b::/96"):  # NAT64: the embedded IPv4 is what counts
            ip = ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF)
    return bool(ip.is_global and not (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast
                                       or ip.is_reserved or ip.is_unspecified))


def _resolve(host: str) -> list[str]:
    try:
        infos = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except (socket.gaierror, UnicodeError, OSError):
        raise OpenverseError(f"não consegui resolver o host {host}") from None
    out: list[str] = []
    for info in infos:
        ip = info[4][0]
        if ip not in out:
            out.append(ip)
    return out


def _validate_url(url: str) -> tuple[str, str]:
    """https scheme, no credentials in the URL, port 443, a host that resolves only to public addresses. Returns (host, ip)."""
    u = urlparse(url)
    if u.scheme != "https":
        raise OpenverseError(f"recusado: só https é aceito para baixar (recebi {u.scheme or 'URL sem esquema'})")
    if u.username or u.password:
        raise OpenverseError("recusado: a URL traz credencial (usuário:senha@host)")
    host = u.hostname
    if not host:
        raise OpenverseError("recusado: URL sem host")
    try:
        port = u.port
    except ValueError:
        raise OpenverseError("recusado: porta inválida na URL") from None
    if port not in (None, 443):
        raise OpenverseError(f"recusado: porta {port} não permitida (só 443)")
    ips = sorted(_resolve(host), key=lambda x: ":" in x)  # IPv4 first: the connection goes to the first validated address
    if not ips:
        raise OpenverseError(f"não consegui resolver o host {host}")
    for ip in ips:
        if not _is_public(ip):
            raise OpenverseError(f"recusado: {host} resolve para {ip}, um endereço não público (privado, loopback, link-local ou reservado)")
    return host, ips[0]


class _Resp:
    def __init__(self, conn, r):
        self._conn, self._r = conn, r
        self.status = r.status
        self.headers = {k.lower(): v for k, v in r.getheaders()}

    def read(self, n: int = -1) -> bytes:
        # read1 returns as soon as some bytes arrive, so the total deadline is checked even for a server that drips bytes
        r1 = getattr(self._r, "read1", None)
        return r1(n) if r1 is not None and n and n > 0 else self._r.read(n)

    def close(self) -> None:
        with contextlib.suppress(Exception):
            self._conn.close()


class _PinnedHTTPS(http.client.HTTPSConnection):
    """HTTPS that connects to the already validated IP (no second DNS lookup) and verifies the certificate against the host name."""

    def __init__(self, host: str, ip: str, **kw):
        super().__init__(host, **kw)
        self._ip = ip

    def connect(self):
        sock = socket.create_connection((self._ip, self.port), self.timeout)
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


def _real_http_get(url: str, ip: str, timeout: float = HTTP_TIMEOUT):
    if os.environ.get("SIMPLICIO_OFFLINE", "").strip().lower() in ("1", "true", "yes", "on"):
        raise OpenverseError("SIMPLICIO_OFFLINE=1: rede bloqueada")
    u = urlparse(url)
    conn = _PinnedHTTPS(u.hostname, ip, port=443, timeout=timeout, context=ssl.create_default_context())
    path = (u.path or "/") + (f"?{u.query}" if u.query else "")
    try:
        conn.request("GET", path, headers={"User-Agent": USER_AGENT, "Accept": "*/*", "Accept-Encoding": "identity"})
        return _Resp(conn, conn.getresponse())
    except (OSError, http.client.HTTPException) as e:
        conn.close()
        raise OpenverseError(f"falha de rede no download: {type(e).__name__}") from None


_http_get = _real_http_get


def _stream_to_file(resp, tipo: str, declarado: int | None = None, deadline: float | None = None) -> dict:
    limite = MAX_BYTES[tipo]
    if deadline is None:
        deadline = time.monotonic() + DOWNLOAD_DEADLINE_S
    tmp_dir = library_dir() / "tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=tmp_dir, suffix=".part")
    tmp = Path(tmp_name)
    h, total, head = hashlib.sha256(), 0, b""
    try:
        with os.fdopen(fd, "wb") as f:
            while True:
                block = resp.read(READ_BLOCK)
                if not block:
                    break
                total += len(block)
                if time.monotonic() > deadline:
                    raise OpenverseError(f"o download passou do prazo de {DOWNLOAD_DEADLINE_S} s: interrompido")
                if total > limite:
                    raise OpenverseError(f"arquivo acima do limite de {limite // (1024 * 1024)} MB para {TIPO_PT[tipo]}: download interrompido")
                if len(head) < 64:
                    head += block[:64 - len(head)]
                h.update(block)
                f.write(block)
            f.flush()
            os.fsync(f.fileno())
        if total == 0:
            raise OpenverseError("o servidor respondeu sem conteúdo")
        if declarado is not None and total != declarado:
            raise OpenverseError(f"download truncado: o servidor anunciou {declarado} bytes e entregou {total}")
        det = detect_format(head)
        if det is None:
            raise OpenverseError("o conteúdo baixado não tem assinatura (magic bytes) de imagem ou áudio permitido "
                                 "(jpg, png, webp, gif, mp3, ogg, wav, flac, m4a); o Content-Type do servidor não conta")
        formato, midia, ext = det
        if midia != tipo:
            raise OpenverseError(f"o arquivo baixado tem assinatura de {TIPO_PT[midia]}, não de {TIPO_PT[tipo]}")
        sha = h.hexdigest()
        final = library_dir() / "files" / f"{sha}.{ext}"
        final.parent.mkdir(parents=True, exist_ok=True)
        os.replace(tmp, final)
        if sha256_file(final) != sha:  # check what actually reached the disk
            final.unlink(missing_ok=True)
            raise OpenverseError("o sha256 do arquivo gravado não confere com o dos bytes recebidos: descartado")
        return {"sha256": sha, "arquivo": f"files/{sha}.{ext}", "formato": formato, "tamanho_bytes": total}
    finally:
        with contextlib.suppress(OSError):
            tmp.unlink()


def _declared_length(headers: dict) -> int | None:
    v = str(headers.get("content-length", "")).strip()
    return int(v) if v.isascii() and v.isdigit() else None  # str.isdigit() also accepts "²" and Arabic digits, which int() rejects


def _download(url: str, tipo: str) -> dict:
    deadline = time.monotonic() + DOWNLOAD_DEADLINE_S  # connect, TLS, redirects and body all count
    current = url
    for hop in range(MAX_REDIRECTS + 1):
        if time.monotonic() > deadline:
            raise OpenverseError(f"o download passou do prazo de {DOWNLOAD_DEADLINE_S} s: interrompido")
        _host, ip = _validate_url(current)
        resp = _http_get(current, ip, HTTP_TIMEOUT)
        try:
            if resp.status in (301, 302, 303, 307, 308):
                loc = resp.headers.get("location")
                if not loc:
                    raise OpenverseError(f"o servidor respondeu {resp.status} sem destino")
                if hop == MAX_REDIRECTS:
                    raise OpenverseError(f"redirecionamentos demais (mais de {MAX_REDIRECTS}): recusado")
                current = urljoin(current, loc)
                continue
            if resp.status != 200:
                raise OpenverseError(f"o servidor da fonte respondeu HTTP {resp.status}")
            length = _declared_length(resp.headers)
            if length is not None and length > MAX_BYTES[tipo]:
                raise OpenverseError(f"arquivo de {length} bytes acima do limite de {MAX_BYTES[tipo] // (1024 * 1024)} MB para {TIPO_PT[tipo]}")
            return _stream_to_file(resp, tipo, length, deadline)
        finally:
            resp.close()
    raise OpenverseError(f"redirecionamentos demais (mais de {MAX_REDIRECTS}): recusado")


# ---------------------------------------------------------------------------------------------------------- library

def _check_downloadable(item: dict) -> list[str]:
    lic = item.get("licenca")
    if not lic:
        raise OpenverseError(f"recusado: o item {item.get('id')} não tem licença conhecida")
    table = _licenses()
    if lic not in table:
        raise OpenverseError(f"recusado: licença não suportada pelo comando ({lic})")
    if item.get("mature"):
        raise OpenverseError("recusado: o item está marcado como mature (conteúdo sensível)")
    if not item.get("url_arquivo"):
        raise OpenverseError("recusado: o item não tem URL de arquivo")
    return [f"{lic}: {table[lic]['aviso']}"] if table[lic].get("aviso") else []


def get(id_, tipo=None, atualizar=False) -> dict:
    """Download the item into the library. Idempotent: an item already downloaded and intact does not touch the network (unless `atualizar`)."""
    id_ = _check_id(id_)
    if tipo is not None and tipo not in TIPOS:
        raise OpenverseError(f"tipo inválido: {tipo!r} (use imagem ou audio)")
    idx = _load_index()
    rec = idx["itens"].get(id_)
    if rec and not atualizar:
        try:
            ok = _FILE_RE.match(str(rec.get("arquivo"))) and _integridade(rec) == "ok"
        except KeyError:
            ok = False
        if ok:  # the sha256 of the file on disk, not only its size
            return {"item": rec, "ja_na_biblioteca": True, "avisos": _check_downloadable(rec)}
    found = None if atualizar else _find_in_cache(id_)
    if found is not None:
        item, consultado = found
        if tipo and tipo != item["tipo"]:
            raise OpenverseError(f"o id {id_} é {TIPO_PT[item['tipo']]} no cache, mas --tipo pediu {TIPO_PT[tipo]}")
    else:
        tipo = tipo or (rec["tipo"] if rec else None)
        if tipo is None:
            raise OpenverseError(f"o id {id_} não está no cache de buscas: informe --tipo imagem|audio para consultar o detalhe na API")
        resp = _api_get(f"{ENDPOINT[tipo]}/{id_}/")
        body = resp.json() if resp.status == 200 else None
        if not isinstance(body, dict):
            raise _api_error(resp, f"o detalhe do item {id_}")
        item, consultado = _norm_item(body, tipo), _stamp()
        if (item["id"] or "").lower() != id_:
            raise OpenverseError("o Openverse devolveu outro id no detalhe: recusado")
        item["id"] = id_
    avisos = _check_downloadable(item)
    dias = (_now() - datetime.strptime(consultado, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)).days
    if dias > STALE_DAYS:
        avisos.append(f"metadados consultados há {dias} dias: a licença e a disponibilidade podem ter mudado; repita com --atualizar para reconferir na API")
    dl = _download(item["url_arquivo"], item["tipo"])
    record = {**item, **dl, "baixado_em": _stamp(), "consultado_em": consultado}
    with _index_tx() as idx:
        idx["itens"][id_] = record
    return {"item": record, "ja_na_biblioteca": False, "avisos": avisos}


def _status_in(idx: dict, rec: dict, norm: str) -> str:
    for r in reversed(idx["revisoes"]):
        if r["sha256"] == rec["sha256"] and r["pedido_normalizado"] == norm:
            return r["veredito"]
    return "nao_revisado"


def review_status(id_, pedido) -> str:
    id_ = _check_id(id_)
    idx = _load_index()
    return _status_in(idx, _item(idx, id_), _clean_pedido(pedido)[1])


def _aprovado_para(idx: dict, rec: dict) -> list[str]:
    vistos: dict[str, str] = {}
    for r in idx["revisoes"]:
        if r["sha256"] == rec["sha256"]:
            vistos[r["pedido_normalizado"]] = r["veredito"]
    return [p for p, v in vistos.items() if v == "aprovado"]


def library_list(tipo=None) -> list[dict]:
    if tipo is not None and tipo not in TIPOS:
        raise OpenverseError(f"tipo inválido: {tipo!r} (use imagem ou audio)")
    idx = _load_index()
    rows = [{**r, "aprovado_para": _aprovado_para(idx, r)} for r in idx["itens"].values() if tipo in (None, r["tipo"])]
    return sorted(rows, key=lambda r: (r["baixado_em"], r["id"]))


def library_show(id_, pedido=None) -> dict:
    id_ = _check_id(id_)
    idx = _load_index()
    rec = _item(idx, id_)
    revs = [{**r, "vale_para_o_arquivo_atual": r["sha256"] == rec["sha256"]} for r in idx["revisoes"] if r["id"] == id_]
    return {"item": rec, "integridade": _integridade(rec), "revisoes": revs, "aprovado_para": _aprovado_para(idx, rec),
            "status": _status_in(idx, rec, _clean_pedido(pedido)[1]) if pedido else None,
            "exportacoes": [e for e in idx["exportacoes"] if e["id"] == id_]}


# ---------------------------------------------------------------------------------------------------------- review

def _sheet_dir(rec: dict, norm: str) -> Path:
    key = hashlib.sha256(norm.encode("utf8")).hexdigest()[:12]
    return library_dir() / "sheets" / f"{rec['id']}-{rec['sha256'][:12]}-{key}"


def review_sheet(id_, pedido) -> dict:
    """Deterministic sheet for the reviewer to decide: objective signals, an image to look at, a text hint and what is left to check."""
    from . import openverse_sheet as sheet
    id_ = _check_id(id_)
    original, norm = _clean_pedido(pedido)
    idx = _load_index()
    rec = _item(idx, id_)
    arquivo = _require_integridade(rec)
    pasta = _sheet_dir(rec, norm)
    pasta.mkdir(parents=True, exist_ok=True)
    if rec["tipo"] == "imagem":
        sinais = sheet.image_signals(arquivo, rec["formato"], rec)
        arquivos = {"miniatura": str(sheet.thumbnail(arquivo, rec["formato"], pasta / "miniatura.png")), "espectrograma": None}
    else:
        sinais = sheet.audio_signals(arquivo, rec["formato"], rec)
        arquivos = {"miniatura": None, "espectrograma": str(sheet.spectrogram(arquivo, rec["formato"], pasta / "espectrograma.png"))}
    status = _status_in(idx, rec, norm)
    cmd = f"simplicio-video openverse library review {rec['id']} --pedido {shlex.quote(original)}"
    doc = {"schema": SCHEMA_SHEET, "pedido": original, "pedido_normalizado": norm,
           "ativo": {k: rec.get(k) for k in ("id", "sha256", "tipo", "titulo", "autor", "licenca", "licenca_versao", "origem_url", "provedor")},
           "sinais": sinais, "texto": text_score(original, rec.get("titulo"), rec.get("tags")), "arquivos": arquivos,
           "falta_conferir": sheet.checklist(rec, sinais), "status": status,
           "como_decidir": [f'{cmd} --aprovar --motivo "..." --por "..."', f'{cmd} --reprovar --motivo "..." --por "..."'],
           "pasta": str(pasta)}
    _atomic_write(pasta / "folha.json", _dump(doc))
    return doc


def review(id_, pedido, veredito, motivo, por, canal="terminal") -> dict:
    """Record the reviewer's verdict for the pair (sha256 of the asset, request). The last verdict of the pair wins."""
    id_ = _check_id(id_)
    if veredito not in ("aprovado", "reprovado"):
        raise OpenverseError("veredito inválido: use aprovado ou reprovado")
    original, norm = _clean_pedido(pedido)
    motivo = _clean_text(motivo, "o motivo")
    por = _clean_text(por, "o campo --por", 120)
    if not motivo:
        raise OpenverseError("falta o motivo (--motivo): diga por que o ativo serve ou não para este pedido")
    if not por:
        raise OpenverseError("falta quem revisou (--por): um nome ou o nome do agente")
    with _index_tx() as idx:
        rec = _item(idx, id_)
        _require_integridade(rec)
        if veredito == "aprovado" and not (_sheet_dir(rec, norm) / "folha.json").is_file():
            raise OpenverseError("aprovar exige a folha de revisão deste par ativo+pedido: gere antes com "
                                 f"`simplicio-video openverse library review {id_} --pedido {shlex.quote(original)} --folha`")
        entry = {"id": id_, "sha256": rec["sha256"], "pedido": original, "pedido_normalizado": norm, "veredito": veredito,
                 "motivo": motivo, "por": por, "canal": canal, "em": _stamp()}
        idx["revisoes"].append(entry)
    return entry


# ---------------------------------------------------------------------------------------------------------- export and credits

def _slug(text: str | None, fallback: str) -> str:
    t = normalize_pedido(text or "").replace(" ", "-")[:40].strip("-")
    return t or fallback


def export_name(rec: dict) -> str:
    return f"{_slug(rec.get('titulo'), rec['tipo'])}-{rec['sha256'][:8]}{Path(rec['arquivo']).suffix}"


def _md(text) -> str:
    return " ".join(re.sub(r"[\[\]`]+", " ", str(text or "")).split())


def _link(url) -> str | None:
    """A URL that fits safely in a markdown link; anything else becomes plain text."""
    return url if isinstance(url, str) and re.fullmatch(r"https?://[^\s<>()\[\]`]+", url) else None


def _credit_line(rec: dict, nome: str) -> str:
    autor = _md(rec.get("autor"))
    autor_txt = f"[{autor}]({_link(rec.get('autor_url'))})" if autor and _link(rec.get("autor_url")) else (autor or "autor não informado")
    label = license_label(rec.get("licenca"), rec.get("licenca_versao"))
    lic = f"[{label}]({_link(rec.get('licenca_url'))})" if _link(rec.get("licenca_url")) else label
    return (f'- `{nome}`: "{_md(rec.get("titulo")) or "(sem título)"}" por {autor_txt}, licença {lic}. '
            f'Origem: {_md(rec.get("origem_url")) or "não informada"}. id `{rec["id"]}`, sha256 `{rec["sha256"]}`.')


CREDITS_HEADER = (
    "# Créditos: imagens e áudio do Openverse\n\n"
    "Ativos encontrados com a API do Openverse (https://openverse.org/) e usados neste vídeo. O Openverse não endossa nem "
    "certifica este projeto. A licença vem das fontes e o Openverse manda conferir na origem: isto não é parecer jurídico.\n\n")


def _destino(para, contrato) -> Path:
    if (para is None) == (contrato is None):
        raise OpenverseError("informe exatamente um destino: --para <pasta> ou --contrato <contract.yaml> (assets/openverse ao lado do contrato)")
    if contrato is not None:
        c = Path(contrato).expanduser()
        if not c.is_file():
            raise OpenverseError(f"contrato não encontrado: {contrato}")
        return (c.resolve().parent / "assets" / "openverse")
    dest = Path(para).expanduser().resolve()
    if dest.exists() and not dest.is_dir():
        raise OpenverseError(f"o destino precisa ser uma pasta: {dest}")
    return dest


def _check_export_rights(rec: dict, aceito_restricao: bool) -> None:
    table = _licenses()
    lic = rec.get("licenca")
    if not lic or lic not in table:
        raise OpenverseError(f"recusado: sem licença conhecida no registro ({lic or 'ausente'}); confira a origem {rec.get('origem_url') or ''}".strip())
    if not rec.get("licenca_url"):
        raise OpenverseError("recusado: o registro não tem a URL da licença, necessária para o crédito")
    if table[lic]["atribuicao_obrigatoria"] and not (rec.get("autor") or "").strip():
        raise OpenverseError(f"recusado: a licença {license_label(lic, rec.get('licenca_versao'))} exige atribuição e o autor não está registrado; "
                             f"confira o autor na origem ({rec.get('origem_url')})")
    if table[lic].get("aviso") and not aceito_restricao:  # nc, nd and sa: each one restricts what the video may be
        raise OpenverseError(f"recusado: {lic}: {table[lic]['aviso']} Se isso serve a esta peça, repita com --aceito-restricao")


def export(id_, pedido, para=None, contrato=None, aceito_restricao=False) -> dict:
    """Copy the asset APPROVED for this request and add its credit line. Idempotent; never overwrites different bytes.
    The whole operation runs under the library lock, so concurrent exports cannot lose credit lines."""
    id_ = _check_id(id_)
    original, norm = _clean_pedido(pedido)
    dest = _destino(para, contrato)
    with _index_tx() as idx:
        rec = _item(idx, id_)
        status = _status_in(idx, rec, norm)
        if status != "aprovado":
            raise OpenverseError(f"recusado: o ativo está {status} para este pedido. Só sai da biblioteca o que foi aprovado para o pedido: "
                                 f"gere a folha e registre o veredito com `simplicio-video openverse library review {id_} --pedido {shlex.quote(original)}`")
        src = _require_integridade(rec)
        _check_export_rights(rec, aceito_restricao)
        target = dest / export_name(rec)
        copiado = False
        if target.exists():
            if not target.is_file() or sha256_file(target) != rec["sha256"]:
                raise OpenverseError(f"recusado: já existe {target} com bytes diferentes; não vou sobrescrever (mesma regra do publish). "
                                     "Apague ou renomeie o arquivo de lá")
        else:
            dest.mkdir(parents=True, exist_ok=True)
            tmp = dest / f".{target.name}.{os.getpid()}.tmp"
            try:
                shutil.copyfile(src, tmp)
                if sha256_file(tmp) != rec["sha256"]:
                    raise OpenverseError("a cópia não confere com o sha256 do índice: descartada")
                os.replace(tmp, target)
            finally:
                with contextlib.suppress(OSError):
                    tmp.unlink()
            copiado = True
        creditos = dest / CREDITS_NAME
        existing = creditos.read_text(encoding="utf8") if creditos.is_file() else CREDITS_HEADER
        if f"id `{rec['id']}`, sha256 `{rec['sha256']}`" not in existing:  # same bytes under another id still gets its own credit
            text = existing if existing.endswith("\n") else existing + "\n"
            _atomic_write(creditos, _guard(text + _credit_line(rec, target.name) + "\n"))
        entry = {"id": id_, "sha256": rec["sha256"], "pedido_normalizado": norm, "destino": str(dest), "arquivo": target.name, "em": _stamp()}
        key = ("id", "sha256", "destino", "pedido_normalizado")  # one audit record per approved request
        if not any(all(e.get(k) == entry[k] for k in key) for e in idx["exportacoes"]):
            idx["exportacoes"].append(entry)
        aviso = _licenses()[rec["licenca"]].get("aviso")
    return {"arquivo": str(target), "creditos": str(creditos), "copiado": copiado, "ja_existia": not copiado,
            "avisos": [f"{rec['licenca']}: {aviso}"] if aviso else []}


def credits(para=None) -> dict:
    """Credit block for every exported asset (or only those exported to one folder), once per asset (id + sha256)."""
    idx = _load_index()
    alvo = str(Path(para).expanduser().resolve()) if para is not None else None
    vistos: dict[tuple, dict] = {}
    for e in idx["exportacoes"]:
        if alvo is not None and e["destino"] != alvo:
            continue
        rec = idx["itens"].get(e["id"])
        key = (e["id"], e["sha256"])
        if rec and rec["sha256"] == e["sha256"] and key not in vistos:
            vistos[key] = {"id": e["id"], "sha256": e["sha256"], "arquivo": e["arquivo"], "destino": e["destino"],
                           "linha": _credit_line(rec, e["arquivo"])}
    itens = list(vistos.values())
    corpo = "\n".join(i["linha"] for i in itens) if itens else "Nenhum ativo do Openverse exportado ainda."
    return {"itens": [{k: v for k, v in i.items() if k != "linha"} for i in itens], "markdown": CREDITS_HEADER + corpo + "\n"}


# ---------------------------------------------------------------------------------------------------------- status

def status_summary() -> dict:
    try:
        idx = _load_index()
        n = (len(idx["itens"]), len(idx["revisoes"]), len(idx["exportacoes"]))
    except OpenverseError:
        n = (None, None, None)
    return {"biblioteca": str(library_dir()), "itens": n[0], "revisoes": n[1], "exportacoes": n[2],
            "credenciais": {ENV_ID: bool(os.environ.get(ENV_ID, "").strip()), ENV_SECRET: bool(os.environ.get(ENV_SECRET, "").strip())}}


# ---------------------------------------------------------------------------------------------------------- CLI

HELP_DESC = (
    "Biblioteca local de imagens e áudio do Openverse (https://openverse.org/) para compor e melhorar os vídeos, com revisão\n"
    "POR PEDIDO: o ativo só entra num vídeo se alguém aprovou aquele ativo para aquele pedido. Usa a API pública do Openverse;\n"
    "o Openverse não endossa nem certifica o simplicio-video. Zero tokens: nenhuma chamada de LLM; o motor gera uma folha\n"
    "determinística e quem revisa (agente ou pessoa) decide.\n\n"
    "Subcomandos:\n"
    "  search --tipo imagem|audio --consulta \"...\"   busca (cacheada por consulta, repete offline). --licencas cc0,pdm,by (padrão),\n"
    "                                               --minimo-largura N (imagem), --duracao-min/--duracao-max S (áudio), --limite N\n"
    "                                               (até 20 sem credencial, 50 com), --pagina N, --atualizar ignora o cache\n"
    "  get <id> [--tipo imagem|audio]               baixa para a biblioteca: só https, IP público, limite de 25 MB (imagem) ou 50 MB\n"
    "                                               (áudio), tipo pela assinatura do arquivo, nome pelo sha256\n"
    "  library list|show <id>                       o que há na biblioteca, integridade e vereditos\n"
    "  library review <id> --pedido \"...\" --folha    gera a FOLHA de revisão: dimensões, nitidez, brilho, miniatura (imagem); duração,\n"
    "                                               taxa de amostragem, loudness, silêncio, clipping, espectrograma (áudio); pista textual\n"
    "  library review <id> --pedido \"...\" --aprovar|--reprovar --motivo \"...\" --por \"nome\"\n"
    "                                               grava o veredito do par (sha256 do ativo, pedido); aprovar exige a folha antes\n"
    "  library export <id> --pedido \"...\" --para PASTA | --contrato contract.yaml\n"
    "                                               copia só o aprovado para aquele pedido (nunca sobrescreve bytes diferentes) e acrescenta\n"
    f"                                               a linha de crédito a {CREDITS_NAME}; contrato = assets/openverse ao lado dele\n"
    "  library credits [--para PASTA]               bloco de créditos de tudo o que foi exportado\n\n"
    "Licenças: padrão cc0, pdm e by (seguras para uso comercial e edição). by-sa, by-nc e by-nd (e by-nc-sa, by-nc-nd) só por\n"
    "opção explícita em --licencas, com aviso do que implicam; nc e nd nunca entram por padrão e o export de nc, nd e sa exige --aceito-restricao.\n"
    "A licença que o Openverse devolve vem das fontes e ele mesmo manda conferir na origem (foreign_landing_url, gravada em cada\n"
    "item): isto não é parecer jurídico. Item sem licença conhecida nunca é baixado; CC BY sem autor nunca é exportado.\n\n"
    "Biblioteca em OPENVERSE_LIBRARY_DIR (padrão ~/.simplicio-video/openverse-library): index.json (schema versionado), files/<sha256>.<ext>,\n"
    "cache/, sheets/. Credenciais OAuth2 opcionais só por variável de ambiente: OPENVERSE_CLIENT_ID e OPENVERSE_CLIENT_SECRET (nunca\n"
    "por argumento; nada vai para índice, cache, folha ou saída). Respeite os termos do Openverse: sem raspagem em massa.\n"
    "Pelo MCP (video.openverse): search, list, show, folha e review; baixar e exportar só pelo terminal.")
HELP_EPILOG = (
    "exemplos:\n"
    "  simplicio-video openverse search --tipo imagem --consulta \"sunrise over the sea\" --minimo-largura 1280 --limite 10\n"
    "  simplicio-video openverse search --tipo audio --consulta \"rain\" --duracao-min 20 --duracao-max 90 --json\n"
    "  simplicio-video openverse get 9d8abc2c-c4dd-4dce-8164-cadd775befcf\n"
    "  simplicio-video openverse library review 9d8abc2c-c4dd-4dce-8164-cadd775befcf --pedido \"nascer do sol para a abertura\" --folha\n"
    "  simplicio-video openverse library review 9d8abc2c-c4dd-4dce-8164-cadd775befcf --pedido \"nascer do sol para a abertura\" \\\n"
    "      --aprovar --motivo \"o sol aparece no centro, sem marca\" --por \"Wesley\"\n"
    "  simplicio-video openverse library export 9d8abc2c-c4dd-4dce-8164-cadd775befcf --pedido \"nascer do sol para a abertura\" \\\n"
    "      --contrato clients/acme/video-01/contract.yaml\n"
    "  simplicio-video openverse library credits")


def _opt_int(text):
    return None if text in (None, "") else int(text)


def _opt_float(text):
    return None if text in (None, "") else float(text)


def _parser() -> argparse.ArgumentParser:
    fmt = argparse.RawDescriptionHelpFormatter
    ap = argparse.ArgumentParser(prog="simplicio-video openverse", description=HELP_DESC, epilog=HELP_EPILOG, formatter_class=fmt)
    sub = ap.add_subparsers(dest="cmd")

    p = sub.add_parser("search", formatter_class=fmt, help="busca imagens ou áudio (cacheada)",
                       description="Busca no Openverse e mostra id, dimensões ou duração, licença, autor e origem. Repetir a mesma busca sai do cache.",
                       epilog="exemplo:\n  simplicio-video openverse search --tipo imagem --consulta \"sunrise over the sea\" --limite 10")
    p.add_argument("--tipo", required=True, choices=TIPOS)
    p.add_argument("--consulta", required=True, help="o que procurar (até 200 caracteres; títulos e tags costumam estar em inglês)")
    p.add_argument("--licencas", default=",".join(DEFAULT_LICENSES),
                   help="licenças aceitas, separadas por vírgula (padrão cc0,pdm,by; by-sa, by-nc, by-nd, by-nc-sa e by-nc-nd só explícitas, com aviso)")
    p.add_argument("--minimo-largura", type=_opt_int, default=None, help="imagem: largura mínima em pixels (filtro local)")
    p.add_argument("--duracao-min", type=_opt_float, default=None, help="áudio: duração mínima em segundos (filtro local)")
    p.add_argument("--duracao-max", type=_opt_float, default=None, help="áudio: duração máxima em segundos (filtro local)")
    p.add_argument("--limite", type=int, default=10, help="resultados por página (padrão 10; máximo 20 sem credencial, 50 com)")
    p.add_argument("--pagina", type=int, default=1)
    p.add_argument("--atualizar", action="store_true", help="ignora o cache e consulta a API de novo")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("get", formatter_class=fmt, help="baixa um item para a biblioteca (download seguro)",
                       description="Baixa o arquivo do item para a biblioteca: https, IP público, limite de tamanho, tipo pela assinatura, nome pelo sha256.",
                       epilog="exemplo:\n  simplicio-video openverse get 9d8abc2c-c4dd-4dce-8164-cadd775befcf")
    p.add_argument("id", help="id do Openverse (UUID)")
    p.add_argument("--tipo", choices=TIPOS, help="obrigatório só quando o id não está no cache de buscas")
    p.add_argument("--atualizar", action="store_true", help="consulta e baixa de novo (um arquivo novo muda o sha256 e invalida as aprovações)")
    p.add_argument("--json", action="store_true")

    lib = sub.add_parser("library", formatter_class=fmt, help="biblioteca local: list, show, review, export, credits",
                         description="Biblioteca local de ativos baixados, com revisão por pedido, export e créditos.")
    ap.library_parser = lib
    ls = lib.add_subparsers(dest="lcmd")
    p = ls.add_parser("list", formatter_class=fmt, help="lista os ativos da biblioteca")
    p.add_argument("--tipo", choices=TIPOS)
    p.add_argument("--json", action="store_true")
    p = ls.add_parser("show", formatter_class=fmt, help="mostra um ativo, a integridade e os vereditos")
    p.add_argument("id")
    p.add_argument("--pedido", default=None, help="mostra o estado do par (ativo, pedido)")
    p.add_argument("--json", action="store_true")
    p = ls.add_parser("review", formatter_class=fmt, help="folha de revisão ou veredito por par (ativo, pedido)",
                      description="--folha gera a folha determinística; --aprovar/--reprovar grava o veredito do par. O motor não decide.",
                      epilog="exemplo:\n  simplicio-video openverse library review <id> --pedido \"nascer do sol\" --reprovar --motivo \"tem marca d'água\" --por \"agente\"")
    p.add_argument("id")
    p.add_argument("--pedido", required=True, help="o que o vídeo precisa neste ponto (a revisão vale só para este pedido)")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--folha", action="store_true", help="gera e mostra a folha de revisão")
    g.add_argument("--aprovar", action="store_true")
    g.add_argument("--reprovar", action="store_true")
    p.add_argument("--motivo", default="", help="por que serve ou não serve (obrigatório no veredito)")
    p.add_argument("--por", default="", help="quem revisou: nome ou agente (obrigatório no veredito)")
    p.add_argument("--json", action="store_true")
    p = ls.add_parser("export", formatter_class=fmt, help="copia o ativo aprovado para uma pasta, com o crédito",
                      description="Só exporta o que foi aprovado para o pedido. Recusa sobrescrever bytes diferentes e licença sem autor/atribuição.")
    p.add_argument("id")
    p.add_argument("--pedido", required=True)
    p.add_argument("--para", help="pasta de destino (exemplo: clients/acme/video-01/assets/openverse)")
    p.add_argument("--contrato", help="contract.yaml: o destino vira assets/openverse ao lado dele")
    p.add_argument("--aceito-restricao", action="store_true", help="aceita exportar licença com restrição: nc (não comercial), nd (sem derivadas) ou sa (mesma licença)")
    p.add_argument("--json", action="store_true")
    p = ls.add_parser("credits", formatter_class=fmt, help="bloco de créditos dos ativos exportados")
    p.add_argument("--para", help="só os exportados para esta pasta")
    p.add_argument("--json", action="store_true")
    return ap


def _emit(obj, as_json: bool, text: str) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2) if as_json else text)


def _dims(item: dict) -> str:
    if item["tipo"] == "imagem":
        return f"{item.get('largura') or '?'}x{item.get('altura') or '?'}"
    d = item.get("duracao_s")
    return f"{d:.1f} s" if isinstance(d, (int, float)) else "duração ?"


def _search_text(r: dict) -> str:
    origem = f"do cache, consultado em {r['consultado_em']}" if r["do_cache"] else f"consulta nova em {r['consultado_em']}"
    lines = [f"{r['tipo']} | \"{r['consulta']}\" | licenças {','.join(r['licencas'])} | {origem}",
             f"{len(r['resultados'])} resultado(s) na página {r['pagina']} (total na API: {r['total_api']})"]
    for i, it in enumerate(r["resultados"], 1):
        lines.append(f"[{i}] {it['id']} | {_dims(it)} | {license_label(it['licenca'], it['licenca_versao'])} | {it.get('provedor') or '-'}"
                     f"{' | na biblioteca' if it['na_biblioteca'] else ''}")
        lines.append(f"    \"{it.get('titulo') or '(sem título)'}\" por {it.get('autor') or 'autor não informado'}")
        lines.append(f"    origem: {it.get('origem_url')}")
    if r.get("cota_api"):
        lines.append("cota restante da API (anônima): " + ", ".join(f"{k.removeprefix('x-ratelimit-available-')}={v}" for k, v in r["cota_api"].items()))
    desc = {k: v for k, v in r["descartados"].items() if v}
    if desc:
        lines.append(f"descartados: {', '.join(f'{k}={v}' for k, v in desc.items())}")
    for a in r["avisos"]:
        lines.append(f"AVISO {a}")
    lines.append("próximo passo: simplicio-video openverse get <id>   (a licença vem das fontes; confira na origem: não é parecer jurídico)")
    return "\n".join(lines)


def _sheet_text(f: dict) -> str:
    a, s, t = f["ativo"], f["sinais"], f["texto"]
    lines = ["Folha de revisão (sinais objetivos para o revisor; o motor não decide)",
             f"ativo: {a['id']} ({a['tipo']}, {s.get('formato')}) sha256 {a['sha256'][:12]}",
             f"  \"{a.get('titulo') or '(sem título)'}\" por {a.get('autor') or 'autor não informado'} | "
             f"{license_label(a.get('licenca'), a.get('licenca_versao'))} | origem {a.get('origem_url')}",
             f"pedido: \"{f['pedido']}\"", "sinais:"]
    for k, v in s.items():
        lines.append(f"  {k}: {json.dumps(v, ensure_ascii=False) if isinstance(v, dict) else v}")
    lines.append(f"pista textual: {len(t['em_comum'])} de {len(t['tokens_pedido'])} palavras do pedido no título/tags "
                 f"(pontuação {t['pontuacao']}); em comum: {', '.join(t['em_comum']) or '-'}; faltando: {', '.join(t['faltando']) or '-'}")
    lines.append(f"  {t['aviso']}")
    for k, v in f["arquivos"].items():
        if v:
            lines.append(f"para VER/ouvir ({k}): {v}")
    lines.append(f"estado atual do par: {f['status']}")
    lines.append("Falta conferir:")
    lines += [f"  - {x}" for x in f["falta_conferir"]]
    lines.append("Para decidir:")
    lines += [f"  {c}" for c in f["como_decidir"]]
    return "\n".join(lines)


def _show_text(d: dict) -> str:
    it = d["item"]
    lines = [f"{it['id']} ({it['tipo']}, {it['formato']}, {_dims(it)}) sha256 {it['sha256'][:12]} | integridade {d['integridade']}",
             f"  \"{it.get('titulo') or '(sem título)'}\" por {it.get('autor') or 'autor não informado'} | "
             f"{license_label(it.get('licenca'), it.get('licenca_versao'))}",
             f"  origem: {it.get('origem_url')}", f"  arquivo: {library_dir() / it['arquivo']}"]
    if d["status"] is not None:
        lines.append(f"  estado para o pedido informado: {d['status']}")
    lines.append(f"  aprovado para: {', '.join(d['aprovado_para']) or '(nenhum pedido)'}")
    for r in d["revisoes"]:
        lines.append(f"  revisão {r['em']} por {r['por']} ({r['canal']}): {r['veredito']} para \"{r['pedido']}\" - {r['motivo']}"
                     f"{'' if r['vale_para_o_arquivo_atual'] else ' [arquivo antigo: não vale]'}")
    return "\n".join(lines)


def _run(a) -> int:
    if a.cmd == "search":
        r = search(a.tipo, a.consulta, a.licencas, a.minimo_largura, a.duracao_min, a.duracao_max, a.limite, a.pagina, a.atualizar)
        _emit(r, a.json, _search_text(r))
        return 0
    if a.cmd == "get":
        r = get(a.id, a.tipo, a.atualizar)
        it = r["item"]
        text = (f"{'já estava na biblioteca' if r['ja_na_biblioteca'] else 'baixado'}: {it['id']} -> {library_dir() / it['arquivo']}\n"
                f"  {it['formato']}, {it['tamanho_bytes']} bytes, sha256 {it['sha256']}\n"
                f"  \"{it.get('titulo') or '(sem título)'}\" por {it.get('autor') or 'autor não informado'} | "
                f"{license_label(it['licenca'], it['licenca_versao'])} | origem {it.get('origem_url')}\n"
                + "".join(f"  AVISO {w}\n" for w in r["avisos"]) +
                "  próximo passo: library review <id> --pedido \"...\" --folha (a licença vem das fontes: confira na origem)")
        _emit(r, a.json, text)
        return 0
    if a.cmd != "library" or not a.lcmd:
        return -1
    if a.lcmd == "list":
        rows = library_list(a.tipo)
        text = "\n".join(f"{r['id']} | {r['tipo']} | {_dims(r)} | {license_label(r['licenca'], r['licenca_versao'])} | "
                         f"\"{r.get('titulo') or '(sem título)'}\" | sha256 {r['sha256'][:12]} | aprovado para {len(r['aprovado_para'])} pedido(s)"
                         for r in rows) or "biblioteca vazia"
        _emit({"itens": rows}, a.json, text)
        return 0
    if a.lcmd == "show":
        d = library_show(a.id, a.pedido)
        _emit(d, a.json, _show_text(d))
        return 0
    if a.lcmd == "review":
        if a.folha:
            f = review_sheet(a.id, a.pedido)
            _emit(f, a.json, _sheet_text(f))
            return 0
        if not (a.aprovar or a.reprovar):
            raise OpenverseError("escolha uma ação: --folha, --aprovar ou --reprovar")
        rev = review(a.id, a.pedido, "aprovado" if a.aprovar else "reprovado", a.motivo, a.por)
        _emit(rev, a.json, f"registrado: {rev['veredito']} para \"{rev['pedido']}\" (ativo {rev['id']}, sha256 {rev['sha256'][:12]}) por {rev['por']}")
        return 0
    if a.lcmd == "export":
        r = export(a.id, a.pedido, a.para, a.contrato, a.aceito_restricao)
        _emit(r, a.json, f"{'exportado' if r['copiado'] else 'já estava lá (mesmos bytes)'}: {r['arquivo']}\ncréditos: {r['creditos']}"
              + "".join(f"\nAVISO {w}" for w in r["avisos"]))
        return 0
    r = credits(a.para)
    _emit(r, a.json, r["markdown"])
    return 0


def run_openverse(argv: list[str]) -> int:
    ap = _parser()
    a = ap.parse_args(argv)
    if not a.cmd:
        ap.print_help(sys.stderr)
        return 1
    try:
        rc = _run(a)
        if rc == -1:  # `library` without a subcommand
            ap.library_parser.print_help(sys.stderr)
            return 1
        return rc
    except OpenverseError as e:
        print(f"openverse: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("openverse: interrompido (Ctrl+C); o índice só é gravado ao fim de cada operação", file=sys.stderr)
        return 130
    except Exception as e:  # noqa: BLE001 (no traceback: it could carry a credential)
        print(f"openverse: erro inesperado: {scrub(f'{type(e).__name__}: {e}')}", file=sys.stderr)
        return 1
