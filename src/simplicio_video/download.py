"""`simplicio-video media fetch`: download one public video page to a local MP4 with yt-dlp (pinned in tools.py).

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
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from . import tools

FETCH_SCHEMA = "simplicio.media-fetch/v1"
MAX_URL_CHARS = 2048
DEFAULT_MAX_MB = 500
DEFAULT_TIMEOUT_S = 600
MAX_TEXT_CHARS = 300
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
    candidatos = [p for p in pasta.iterdir() if p.is_file() and p.suffix not in (".part", ".ytdl")]
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


def fetch(url: str, dest: Path, autorizo: bool, max_mb: int = DEFAULT_MAX_MB, timeout: int = DEFAULT_TIMEOUT_S) -> dict:
    """Download `url` to the new file `dest` (an .mp4) and write its provenance record next to it. Returns the record."""
    if not autorizo:
        raise DownloadError("media fetch: confirme que você pode usar este vídeo com --autorizo (o motor não verifica o direito de uso)")
    url = validate_url(url)
    if dest.suffix.lower() != ".mp4":
        raise DownloadError("a saída precisa ser .mp4")
    if max_mb < 1 or timeout < 1:
        raise DownloadError("--max-mb e --timeout precisam ser >= 1")
    registro = dest.with_suffix(".fetch.json")
    for alvo in (dest, registro):
        if alvo.exists():
            raise DownloadError(f"{alvo.name} já existe: não sobrescrevo; escolha outro -o")
    exe = _binario()
    pasta = Path(tempfile.mkdtemp(prefix=".fetch-", dir=dest.parent))
    try:
        cmd = [str(exe), "--ignore-config", "--no-playlist", "--no-cache-dir", "--no-progress", "--print-json",
               "-f", "best[ext=mp4]/best", "--max-filesize", f"{max_mb}M", "-o", str(pasta / "%(id)s.%(ext)s"), url]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=_ambiente())
        except subprocess.TimeoutExpired:
            raise DownloadError(f"yt-dlp passou de {timeout} s e foi interrompido") from None
        if r.returncode:
            raise DownloadError(f"yt-dlp: {_ultima_linha(r.stderr or r.stdout)}")
        info = _info(r.stdout)
        arquivo = _mp4(_arquivo(pasta), pasta)
        tamanho = arquivo.stat().st_size
        if tamanho > max_mb * 1024 * 1024:
            raise DownloadError(f"o arquivo tem {tamanho // (1024 * 1024)} MB, acima de --max-mb {max_mb}")
        sha = _sha256(arquivo)
        _publicar(arquivo, dest)
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
        "ferramenta": {"name": "yt-dlp", "version": tools.pinned_ref(tools.get("yt-dlp"))},
        "baixado_em": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "autorizado": True,
        "aviso": AVISO,
        "untrusted_titulo": _cap(info.get("title")),
        "untrusted_autor": _cap(info.get("uploader") or info.get("channel")),
    }
    registro.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
    return doc
