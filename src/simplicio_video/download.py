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
LANG_RE = re.compile(r"^[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*$")  # literal codes only: yt-dlp reads --sub-langs as a regex
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


def _srt_ocupado(dest: Path, lang: str) -> Path | None:
    """An existing `<name>.<lang>.srt` next to `dest`. yt-dlp matches languages case-insensitively, so the name is compared that way."""
    prefixo = dest.stem + "."
    try:
        nomes = [p for p in dest.parent.iterdir() if p.name.startswith(prefixo) and p.name.endswith(".srt")]
    except OSError:
        return None
    for p in nomes:
        if p.name[len(prefixo):-4].casefold() == lang.casefold():
            return p
    return None


def _conferir(caminho: Path) -> None:
    """The file must be media ffprobe can read: at least one stream and a duration above zero."""
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        raise DownloadError("o ffprobe é necessário para conferir o arquivo baixado (instale o ffmpeg)")
    try:
        r = subprocess.run([ffprobe, "-v", "error", "-show_entries", "format=duration:stream=codec_type", "-of", "json", str(caminho)],
                           capture_output=True, text=True, timeout=60)
        dados = json.loads(r.stdout or "{}")
        duracao = float((dados.get("format") or {}).get("duration") or 0)
    except (subprocess.TimeoutExpired, ValueError):
        raise DownloadError("o arquivo baixado não é mídia legível (o ffprobe não entendeu)") from None
    if r.returncode or not dados.get("streams") or not duracao > 0:
        raise DownloadError(f"o arquivo baixado não é mídia legível (ffprobe: {_ultima_linha(r.stderr) if r.stderr else 'sem fluxo ou sem duração'})")


def _desfazer(publicados: list[Path]) -> None:
    for p in publicados:
        try:
            p.unlink()
        except OSError:
            pass


def fetch(url: str, dest: Path, autorizo: bool, max_mb: int = DEFAULT_MAX_MB, timeout: int = DEFAULT_TIMEOUT_S, *,
          subs: str | None = None, auto_subs: bool = False, section: str | None = None, audio_only: bool = False) -> dict:
    """Download `url` to the new file `dest` (an .mp4, or .m4a/.wav with `audio_only`) and write its provenance record next to it.
    Optional: `subs` LANG (the creator's own subtitles, as <name>.<lang>.srt; `auto_subs` also accepts the auto-generated ones),
    `section` "START-END" seconds (only that range). Every option is recorded. Returns the record.
    The video, the subtitles and the record are published together: if any step fails, what was published is removed."""
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
    if subs is not None and not (isinstance(subs, str) and len(subs) <= 20 and LANG_RE.match(subs) and subs.lower() != "all"):
        raise DownloadError("--subs: informe um idioma como pt, en ou pt-BR (um só; 'all' e padrões não são aceitos)")
    registro = dest.with_suffix(".fetch.json")
    for alvo in (dest, registro):
        if alvo.exists():
            raise DownloadError(f"{alvo.name} já existe: não sobrescrevo; escolha outro -o")
    if subs is not None and (ocupado := _srt_ocupado(dest, subs)) is not None:
        raise DownloadError(f"{ocupado.name} já existe: não sobrescrevo; escolha outro -o")
    exe = _binario()
    pasta = Path(tempfile.mkdtemp(prefix=".fetch-", dir=dest.parent))
    publicados: list[Path] = []
    try:
        # The template is relative and yt-dlp runs inside the temp folder, so a `%` or `$` in the user's path never reaches it.
        cmd = [str(Path(exe).absolute()), "--ignore-config", "--no-plugin-dirs", "--no-playlist", "--playlist-items", "1",
               "--no-cache-dir", "--no-progress", "--print-json"]
        if audio_only:
            cmd += ["-f", "bestaudio/best", "-x", "--audio-format", AUDIO_FORMATS[dest.suffix.lower()]]
        else:
            cmd += ["-f", "best[ext=mp4]/best"]
        if faixa:
            cmd += ["--download-sections", f"*{section}"]
        if subs is not None:
            cmd += ["--write-subs"] + (["--write-auto-subs"] if auto_subs else []) + ["--sub-langs", subs, "--convert-subs", "srt"]
        cmd += ["--max-filesize", f"{max_mb}M", "-o", "%(id)s.%(ext)s", url]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=_ambiente(), cwd=pasta)
        except subprocess.TimeoutExpired:
            raise DownloadError(f"yt-dlp passou de {timeout} s e foi interrompido") from None
        if r.returncode:
            raise DownloadError(f"yt-dlp: {_ultima_linha(r.stderr or r.stdout)}")
        info = _info(r.stdout)
        # With --playlist-items 1 yt-dlp prints the entry as a plain video that remembers its list (playlist_count), so look there.
        contagem = info.get("playlist_count")
        if (info.get("_type") == "playlist" or (info.get("n_entries") or 0) > 1 or (isinstance(contagem, int) and contagem > 1)
                or (info.get("playlist_id") and contagem is None)):
            raise DownloadError("a página é uma lista de vídeos: o motor baixa um vídeo só, passe a URL do vídeo")
        arquivo = _arquivo(pasta)
        if not audio_only:
            arquivo = _mp4(arquivo, pasta)
        elif arquivo.suffix.lower() != dest.suffix.lower():
            raise DownloadError(f"o áudio veio em {arquivo.suffix} e a saída pede {dest.suffix}")
        srts = sorted(p for p in pasta.iterdir() if p.is_file() and p.suffix == ".srt") if subs is not None else []
        tamanho = arquivo.stat().st_size
        total = tamanho + sum(p.stat().st_size for p in srts)
        if total > max_mb * 1024 * 1024:
            raise DownloadError(f"o arquivo tem {total // (1024 * 1024)} MB, acima de --max-mb {max_mb}")
        _conferir(arquivo)
        sha = _sha256(arquivo)
        plano = []  # (source, final path, record entry) for every subtitle, named after the language yt-dlp really wrote
        vistos = set()
        for srt in srts:
            lang = srt.name[:-4].rsplit(".", 1)[-1] if srt.name.count(".") >= 2 else ""
            if not LANG_RE.match(lang) or lang.casefold() in vistos:
                raise DownloadError(f"legenda com nome inesperado do yt-dlp ({srt.name[:60]}); nada foi gravado")
            vistos.add(lang.casefold())
            if (ocupado := _srt_ocupado(dest, lang)) is not None:
                raise DownloadError(f"{ocupado.name} já existe: não sobrescrevo; escolha outro -o")
            plano.append((srt, _legendas_dest(dest, lang)))
        legendas = None
        if subs is not None:
            legendas = {"idioma": subs, "automaticas": bool(auto_subs),
                        "arquivos": [{"arquivo": alvo.name, "sha256": _sha256(srt)} for srt, alvo in plano]}
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
        try:
            for srt, alvo in plano:
                _publicar(srt, alvo)
                publicados.append(alvo)
            _publicar(arquivo, dest)
            publicados.append(dest)
            try:
                with registro.open("x", encoding="utf8") as f:
                    publicados.append(registro)  # created by us from here on, even if the write below fails halfway
                    f.write(json.dumps(doc, ensure_ascii=False, indent=2) + "\n")
            except FileExistsError:
                raise DownloadError(f"{registro.name} apareceu durante o download; não sobrescrevo") from None
            except OSError as e:
                raise DownloadError(f"não consegui gravar {registro.name}: {e.strerror or type(e).__name__}") from None
        except BaseException:
            _desfazer(publicados)  # a record that appeared meanwhile is not in the list: it belongs to someone else
            raise
    finally:
        shutil.rmtree(pasta, ignore_errors=True)
    return doc


_ID_SEGURO = re.compile(r"^[A-Za-z0-9._-]{1,60}$")
_LANG_INFO = re.compile(r"^[A-Za-z0-9_-]{1,20}$")


def _seguro(valor):
    return valor if isinstance(valor, str) and _ID_SEGURO.match(valor) else None


def _formato(f: dict) -> dict:
    def tem(codec):  # None = the extractor did not say (generic pages)
        return None if codec is None else codec != "none"

    return {"id": _seguro(f.get("format_id")), "ext": _seguro(f.get("ext")), "altura": f.get("height") if isinstance(f.get("height"), int) else None,
            "video": tem(f.get("vcodec")), "audio": tem(f.get("acodec")),
            "bytes": f.get("filesize") or f.get("filesize_approx")}


def _idiomas(valor) -> list:
    return sorted(k for k in valor if isinstance(k, str) and _LANG_INFO.match(k)) if isinstance(valor, dict) else []


def info(url: str, timeout: int = DEFAULT_TIMEOUT_S) -> dict:
    """Metadata only (`yt-dlp -J --skip-download`): nothing is downloaded or saved, so no consent is needed. Text that comes from
    the page is untrusted_* or validated to a safe charset; the format URLs (which carry signed tokens) are left out.
    A page that is a list of videos is reported (`lista`, `itens`) and not expanded."""
    url = validate_url(url)
    if timeout < 1:
        raise DownloadError("--timeout precisa ser >= 1")
    exe = _binario()
    cmd = [str(Path(exe).absolute()), "--ignore-config", "--no-plugin-dirs", "--no-playlist", "--flat-playlist", "--no-cache-dir",
           "--no-progress", "-J", "--skip-download", url]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=_ambiente())
    except subprocess.TimeoutExpired:
        raise DownloadError(f"yt-dlp passou de {timeout} s e foi interrompido") from None
    if r.returncode:
        raise DownloadError(f"yt-dlp: {_ultima_linha(r.stderr or r.stdout)}")
    dados = _info(r.stdout)
    lista = dados.get("_type") == "playlist"
    entradas = dados.get("entries")
    formatos = [_formato(f) for f in (dados.get("formats") or [])[:MAX_FORMATS] if isinstance(f, dict)]
    return {
        "schema": INFO_SCHEMA,
        "origem": record_url(url),
        "extrator": _seguro(dados.get("extractor_key") or dados.get("extractor")),
        "id": _cap(dados.get("id"), 200),
        "lista": lista,
        "itens": len(entradas) if lista and isinstance(entradas, list) else None,
        "duracao_s": dados.get("duration"),
        "formatos": formatos,
        "legendas": _idiomas(dados.get("subtitles")),
        "legendas_automaticas": _idiomas(dados.get("automatic_captions")),
        "ferramenta": {"name": "yt-dlp", "version": tools.effective_ref(tools.get("yt-dlp"))},
        "untrusted_titulo": _cap(dados.get("title")),
        "untrusted_autor": _cap(dados.get("uploader") or dados.get("channel")),
        "untrusted_licenca": _cap(dados.get("license")),
    }
