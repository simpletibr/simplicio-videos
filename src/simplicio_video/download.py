"""`simplicio-video media fetch`: download one public video page to a local MP4 (or audio, a time range, creator subtitles) with yt-dlp (pinned in tools.py); `info` reads metadata only.

The engine does not choose what to download and never logs in: no cookies, no account, no playlist, and the user's own
yt-dlp config is ignored (`--ignore-config`). The user confirms the right to use the file with `--autorizo`; the engine
records that confirmation and the source, but it cannot verify the right.

Next to the MP4 it writes `<name>.fetch.json` (schema simplicio.media-fetch/v1): the source without query or fragment,
the yt-dlp version, the sha256 and size of the file, the time, and the title and author as untrusted_* text (third-party
data, never instructions). The MP4 is never overwritten.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from . import tools

FETCH_SCHEMA = "simplicio.media-fetch/v1"
INFO_SCHEMA = "simplicio.media-info/v1"
MAX_URL_CHARS = 2048
DEFAULT_MAX_MB = 500
DEFAULT_TIMEOUT_S = 600
MAX_TEXT_CHARS = 300
MAX_FORMATS = 40
AUDIO_FORMATS = {".m4a": "m4a", ".wav": "wav"}
SECTION_RE = re.compile(r"^(\d+(?:\.\d+)?)-(\d+(?:\.\d+)?)$")
LANG_RE = re.compile(r"^[A-Za-z0-9]{1,8}(?:[-_][A-Za-z0-9]{1,8})*$")
SUB_SUFFIXES = (".srt", ".vtt", ".ass", ".json3", ".ttml", ".srv1", ".srv2", ".srv3")
# The only variables the downloader receives: no keys, tokens or SIMPLICIO_* from the shell reach a third-party program.
ENV_REPASSADO = ("PATH", "HOME", "LANG", "LC_ALL", "TMPDIR", "SSL_CERT_FILE", "SSL_CERT_DIR", "REQUESTS_CA_BUNDLE",
                 "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY", "http_proxy", "https_proxy", "all_proxy", "no_proxy")
AVISO = "o motor não verifica o direito de uso: guarde a autorização com o projeto"


class DownloadError(Exception):
    pass


def validate_url(url) -> str:
    """http or https with a host; no credentials, spaces or control characters; not too long."""
    if not isinstance(url, str) or not url or len(url) > MAX_URL_CHARS:
        raise DownloadError(f"URL vazia ou longa demais (até {MAX_URL_CHARS} caracteres)")
    if any(ord(c) <= 32 or ord(c) == 127 for c in url):
        raise DownloadError("URL com espaço ou caractere de controle")
    partes = urlsplit(url)
    if partes.scheme not in ("http", "https") or not partes.hostname:
        raise DownloadError("use uma URL http ou https com nome de host")
    if partes.username is not None or partes.password is not None:
        raise DownloadError("URL com usuário:senha é recusada: nada de credencial na URL")
    return url


def record_url(url: str) -> str:
    """The source as the record keeps it: without query or fragment, which often carry tracking or session values."""
    p = urlsplit(url)
    return urlunsplit((p.scheme, p.netloc, p.path, "", ""))


def _cap(valor, limite: int = MAX_TEXT_CHARS):
    return None if valor is None else str(valor)[:limite]


def _binario() -> Path:
    if not tools.is_installed(tools.get("yt-dlp")):
        tools.install("yt-dlp")
    exe = tools.pip_binary("yt-dlp")
    if exe is None:
        raise DownloadError("o yt-dlp não ficou instalado no venv da trilha; veja a mensagem do pip acima")
    return exe


def _ambiente() -> dict:
    return {k: os.environ[k] for k in ENV_REPASSADO if k in os.environ}


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def _ultima_linha(texto: str) -> str:
    linhas = [l.strip() for l in (texto or "").splitlines() if l.strip()]
    return linhas[-1][-300:] if linhas else "falhou sem mensagem"


def _info(saida: str) -> dict:
    """`--print-json` writes one JSON object per video on stdout; the last one describes the file kept."""
    linhas = [l for l in saida.splitlines() if l.lstrip().startswith("{")]
    if not linhas:
        raise DownloadError("yt-dlp não devolveu os dados do vídeo")
    try:
        return json.loads(linhas[-1])
    except ValueError:
        raise DownloadError("yt-dlp devolveu dados que não são JSON") from None


def _arquivo(pasta: Path) -> Path:
    """The one media file in the temporary folder (yt-dlp leaves `.part` files only on failure, which the run reports)."""
    candidatos = [p for p in pasta.iterdir() if p.is_file() and p.suffix not in (".part", ".ytdl") + SUB_SUFFIXES]
    if len(candidatos) != 1:
        raise DownloadError(f"esperava um arquivo de vídeo baixado e achei {len(candidatos)}")
    return candidatos[0]


def _mp4(arquivo: Path, pasta: Path) -> Path:
    if arquivo.suffix.lower() == ".mp4":
        return arquivo
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise DownloadError(f"o vídeo veio em {arquivo.suffix} e o MP4 precisa de ffmpeg para remuxar (copia os fluxos, sem recodificar)")
    destino = pasta / "remux.mp4"
    r = subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(arquivo), "-c", "copy",
                        "-movflags", "+faststart", str(destino)], capture_output=True, text=True)
    if r.returncode:
        raise DownloadError(f"remux para MP4 falhou ({arquivo.suffix} com codec que o MP4 não aceita): {_ultima_linha(r.stderr)}")
    return destino


def _publicar(origem: Path, dest: Path) -> None:
    """A hard link fails if the name exists, so an MP4 is never overwritten, not even by a concurrent run."""
    try:
        os.link(origem, dest)
    except FileExistsError:
        raise DownloadError(f"{dest.name} apareceu durante o download; não sobrescrevo") from None
    except OSError as e:
        raise DownloadError(f"não consegui gravar {dest.name}: {e.strerror or type(e).__name__}") from None


def _secao(section) -> tuple[float, float]:
    m = SECTION_RE.match(section) if isinstance(section, str) else None
    if not m or float(m.group(2)) <= float(m.group(1)):
        raise DownloadError("--section: use INICIO-FIM em segundos, com FIM maior que INICIO (ex.: 0-3 ou 12.5-30)")
    return float(m.group(1)), float(m.group(2))


def _legendas_dest(dest: Path, lang: str) -> Path:
    return dest.with_suffix(f".{lang}.srt")


def fetch(url: str, dest: Path, autorizo: bool, max_mb: int = DEFAULT_MAX_MB, timeout: int = DEFAULT_TIMEOUT_S, *,
          subs: str | None = None, auto_subs: bool = False, section: str | None = None, audio_only: bool = False) -> dict:
    """Download `url` to the new file `dest` (an .mp4, or .m4a/.wav with `audio_only`) and write its provenance record next to it.
    Optional: `subs` LANG (the creator's own subtitles, as <name>.<lang>.srt; `auto_subs` also accepts the auto-generated ones),
    `section` "START-END" seconds (only that range). Every option is recorded. Returns the record."""
    if not autorizo:
        raise DownloadError("media fetch: confirme que você pode usar este vídeo com --autorizo (o motor não verifica o direito de uso)")
    url = validate_url(url)
    if audio_only:
        if dest.suffix.lower() not in AUDIO_FORMATS:
            raise DownloadError("com --audio-only a saída precisa ser .m4a ou .wav")
    elif dest.suffix.lower() != ".mp4":
        raise DownloadError("a saída precisa ser .mp4")
    if max_mb < 1 or timeout < 1:
        raise DownloadError("--max-mb e --timeout precisam ser >= 1")
    faixa = _secao(section) if section is not None else None
    if auto_subs and subs is None:
        raise DownloadError("--auto-subs só vale junto de --subs LANG")
    if subs is not None and not (isinstance(subs, str) and len(subs) <= 20 and LANG_RE.match(subs)):
        raise DownloadError("--subs: informe um idioma como pt, en ou pt-BR (um só)")
    registro = dest.with_suffix(".fetch.json")
    alvos = [dest, registro] + ([_legendas_dest(dest, subs)] if subs is not None else [])
    for alvo in alvos:
        if alvo.exists():
            raise DownloadError(f"{alvo.name} já existe: não sobrescrevo; escolha outro -o")
    exe = _binario()
    pasta = Path(tempfile.mkdtemp(prefix=".fetch-", dir=dest.parent))
    legendas = None
    try:
        cmd = [str(exe), "--ignore-config", "--no-playlist", "--no-cache-dir", "--no-progress", "--print-json"]
        if audio_only:
            cmd += ["-f", "bestaudio/best", "-x", "--audio-format", AUDIO_FORMATS[dest.suffix.lower()]]
        else:
            cmd += ["-f", "best[ext=mp4]/best"]
        if faixa:
            cmd += ["--download-sections", f"*{section}"]
        if subs is not None:
            cmd += ["--write-subs"] + (["--write-auto-subs"] if auto_subs else []) + ["--sub-langs", subs, "--convert-subs", "srt"]
        cmd += ["--max-filesize", f"{max_mb}M", "-o", str(pasta / "%(id)s.%(ext)s"), url]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=_ambiente())
        except subprocess.TimeoutExpired:
            raise DownloadError(f"yt-dlp passou de {timeout} s e foi interrompido") from None
        if r.returncode:
            raise DownloadError(f"yt-dlp: {_ultima_linha(r.stderr or r.stdout)}")
        info = _info(r.stdout)
        arquivo = _arquivo(pasta)
        if not audio_only:
            arquivo = _mp4(arquivo, pasta)
        elif arquivo.suffix.lower() != dest.suffix.lower():
            raise DownloadError(f"o áudio veio em {arquivo.suffix} e a saída pede {dest.suffix}")
        tamanho = arquivo.stat().st_size
        if tamanho > max_mb * 1024 * 1024:
            raise DownloadError(f"o arquivo tem {tamanho // (1024 * 1024)} MB, acima de --max-mb {max_mb}")
        sha = _sha256(arquivo)
        srts = sorted(p for p in pasta.iterdir() if p.is_file() and p.suffix == ".srt") if subs is not None else []
        _publicar(arquivo, dest)
        if subs is not None:
            legendas = {"idioma": subs, "automaticas": bool(auto_subs), "arquivos": []}
            for srt in srts:
                lang = srt.name.rsplit(".", 2)[-2] if srt.name.count(".") >= 2 else subs
                alvo = _legendas_dest(dest, lang if LANG_RE.match(lang) else subs)
                _publicar(srt, alvo)
                legendas["arquivos"].append({"arquivo": alvo.name, "sha256": _sha256(alvo)})
    finally:
        shutil.rmtree(pasta, ignore_errors=True)
    doc = {
        "schema": FETCH_SCHEMA,
        "arquivo": dest.name,
        "origem": record_url(url),
        "extrator": info.get("extractor_key") or info.get("extractor"),
        "id": _cap(info.get("id"), 200),
        "sha256": sha,
        "bytes": tamanho,
        "duracao_s": info.get("duration"),
        "ferramenta": {"name": "yt-dlp", "version": tools.effective_ref(tools.get("yt-dlp"))},
        "baixado_em": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "autorizado": True,
        "aviso": AVISO,
        "untrusted_titulo": _cap(info.get("title")),
        "untrusted_autor": _cap(info.get("uploader") or info.get("channel")),
    }
    if faixa:
        doc["secao"] = {"inicio_s": faixa[0], "fim_s": faixa[1]}
    if audio_only:
        doc["somente_audio"] = True
    if legendas is not None:
        doc["legendas"] = legendas
    registro.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
    return doc


def _formato(f: dict) -> dict:
    def tem(codec):  # None = the extractor did not say (generic pages)
        return None if codec is None else codec != "none"

    return {"id": _cap(f.get("format_id"), 60), "ext": _cap(f.get("ext"), 20), "altura": f.get("height"),
            "video": tem(f.get("vcodec")), "audio": tem(f.get("acodec")),
            "bytes": f.get("filesize") or f.get("filesize_approx")}


def _idiomas(valor) -> list:
    return sorted(_cap(k, 40) for k in valor) if isinstance(valor, dict) else []


def info(url: str, timeout: int = DEFAULT_TIMEOUT_S) -> dict:
    """Metadata only (`yt-dlp -J --skip-download`): nothing is downloaded or saved, so no consent is needed. Title and author
    are untrusted_* third-party text; the format URLs (which carry signed tokens) are left out."""
    url = validate_url(url)
    if timeout < 1:
        raise DownloadError("--timeout precisa ser >= 1")
    exe = _binario()
    cmd = [str(exe), "--ignore-config", "--no-playlist", "--no-cache-dir", "--no-progress", "-J", "--skip-download", url]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=_ambiente())
    except subprocess.TimeoutExpired:
        raise DownloadError(f"yt-dlp passou de {timeout} s e foi interrompido") from None
    if r.returncode:
        raise DownloadError(f"yt-dlp: {_ultima_linha(r.stderr or r.stdout)}")
    dados = _info(r.stdout)
    formatos = [_formato(f) for f in (dados.get("formats") or [])[:MAX_FORMATS] if isinstance(f, dict)]
    return {
        "schema": INFO_SCHEMA,
        "origem": record_url(url),
        "extrator": dados.get("extractor_key") or dados.get("extractor"),
        "id": _cap(dados.get("id"), 200),
        "duracao_s": dados.get("duration"),
        "licenca": _cap(dados.get("license")),
        "formatos": formatos,
        "legendas": _idiomas(dados.get("subtitles")),
        "legendas_automaticas": _idiomas(dados.get("automatic_captions")),
        "ferramenta": {"name": "yt-dlp", "version": tools.effective_ref(tools.get("yt-dlp"))},
        "untrusted_titulo": _cap(dados.get("title")),
        "untrusted_autor": _cap(dados.get("uploader") or dados.get("channel")),
    }
