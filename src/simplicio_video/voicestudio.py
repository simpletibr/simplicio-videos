"""VoiceStudio track: local voice studio for TTS, voice cloning, voice design and transcription
(https://github.com/debpalash/VoiceStudio, AGPL-3.0).

The app (Electron desktop app or the same backend from source) runs as a separate program and serves two local
interfaces: an OpenAI-compatible HTTP API and an MCP server (Streamable HTTP) mounted at /mcp/. It is only ever
reached over loopback HTTP, never vendored or imported (AGPL-3.0). It is an optional support track: the
deterministic render (contract -> MP4) never depends on it, and whatever it produces enters a contract as a file
with a hash.

Facts read at the pinned release (v0.5.7, commit beaae08; the pin lives in tools.TOOLS['voicestudio']):
- Base: http://127.0.0.1:3900 (OMNIVOICE_URL / VOICESTUDIO_URL for the whole base, OMNIVOICE_PORT /
  VOICESTUDIO_PORT for the port). Loopback needs no credential; an optional key goes in
  VOICESTUDIO_API_KEY / OMNIVOICE_API_KEY (Bearer).
- Discovery: GET /.well-known/voicestudio-speech.
- MCP: POST /mcp/ (keep the trailing slash), JSON-RPC 2.0, Streamable HTTP: initialize ->
  notifications/initialized -> tools/call, with X-OmniVoice-Client-Id: simplicio-video.
- Tools: generate_speech(text, language, profile_id, instruct, speed, steps, format), clone_voice(name,
  ref_audio_base64 | ref_audio_path, ...), transcribe(audio_base64 | audio_path, language), describe_voice,
  design_voice(name, description, language), list_voices, list_personalities, list_languages, check_health.
  list_voices, list_personalities, list_languages, transcribe and check_health return JSON-encoded text inside
  the MCP result. generate_speech returns audio shaped by OMNIVOICE_MCP_OUTPUT_MODE: wav_base64 ('resources',
  the default), audio_url plus output_path ('files'), or both.
- Dubbing has NO MCP tool and no single "dub this" call (spike at beeaae0, backend/api/routers/dub_*.py). The app's
  own UI runs a chain of HTTP calls: POST /dub/upload (multipart: video, job_id, input_type, source_lang; answers 202
  {job_id, task_id, filename} and preps in the background, progress on SSE /tasks/stream/{task_id}), POST
  /dub/transcribe/{job_id}, POST /dub/translate, POST /dub/generate/{job_id} (heavy: ASR, translation, TTS, GPU) and
  GET /dub/download/{job_id}. Only the first step (`dub create`, creates the job and its prep) and the last (`dub-export`)
  are driven from here; the middle steps are run in the app, where voices and speakers are chosen.
- OpenAI-compatible REST, used here as the transcription alternative: POST /v1/audio/transcriptions
  (multipart, field 'file'). /v1/audio/speech is the lane the 'voicestudio' voice provider already uses
  (voice_clone.py), not this module.

Only the standard library is used (urllib, json, base64), and `terceiros` (itself standard library only) for the one rule of where
a track does not write. Every network call has a timeout, and the app being
closed becomes a clear, actionable error instead of a traceback or a hang.
"""
from __future__ import annotations

import argparse
import base64
import ipaddress
import json
import os
import sys
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from . import terceiros

DEFAULT_PORT = 3900
CLIENT_ID = "simplicio-video"
MCP_PATH = "/mcp/"
WELL_KNOWN = "/.well-known/voicestudio-speech"
TRANSCRIPTIONS_PATH = "/v1/audio/transcriptions"
PROTOCOL_VERSION = "2025-06-18"
SUBCOMMANDS = "status|voices|languages|personalities|tts|transcribe|clone|describe|design|dub|dub-export|mcp"
DUB_DOWNLOAD_PATH = "/dub/download/"
DUB_UPLOAD_PATH = "/dub/upload"
MAX_DUB_UPLOAD_BYTES = 1024 ** 3  # the file goes in memory as one multipart body; bigger ones are uploaded in the app itself
MAX_BED_LEVEL = 4.0  # the app rejects a higher bed_level (backend/api/routers/dub_export.py)
_JOB_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")  # the app takes only short uuid slices: alnum, hyphen and underscore
_LANG = re.compile(r"^[A-Za-z0-9_-]{1,32}$")
OPEN_APP = ("Abra o VoiceStudio (ele serve a API em :3900) ou aponte VOICESTUDIO_URL/OMNIVOICE_URL para outra porta ou base (chamadas que enviam arquivo, como dub create, transcribe e clone, só aceitam loopback: 127.0.0.0/8, ::1 ou localhost); "
            "do source, a alternativa é executar bun install e bun run dev no checkout.")

HELP_DESC = (
    "Fala com o VoiceStudio (https://github.com/debpalash/VoiceStudio, AGPL-3.0), app local de voz: TTS, clonagem e\n"
    "desenho de vozes e transcrição. A API fica em http://127.0.0.1:3900 (OpenAI-compatible) e o servidor MCP em\n"
    "http://127.0.0.1:3900/mcp/, com as tools generate_speech, clone_voice, describe_voice, design_voice,\n"
    "transcribe, list_voices, list_personalities, list_languages e check_health. O app é um programa separado, só é\n"
    "alcançado por HTTP local e não é importado nem vendorizado. Nada aqui entra no render determinístico."
)
HELP_EPILOG = """exemplos:
  simplicio-video voicestudio status                  # saúde e GPU do app local
  simplicio-video voicestudio voices --json           # perfis de voz salvos (id, nome, tipo)
  simplicio-video voicestudio languages
  simplicio-video voicestudio tts "olá" --out fala.wav --profile <id> --language pt-BR
  simplicio-video voicestudio transcribe audio.m4a --json
  simplicio-video voicestudio transcribe audio.m4a --rest   # POST /v1/audio/transcriptions (OpenAI-compatible)
  simplicio-video voicestudio clone referencia.wav --name "Minha voz"
  simplicio-video voicestudio design "mulher jovem, voz grave, sotaque brasileiro" --name "Narradora"
  simplicio-video voicestudio dub create video.mp4 --source-lang pt   # cria o job no app (upload + preparo); o resto da dublagem é no app
  simplicio-video voicestudio dub-export --job ID --lang pl -o dublado.mp4   # exporta um job de dublagem do app, fundo preservado
  simplicio-video voicestudio mcp                     # bloco de config MCP para o cliente (Streamable HTTP)

ambiente:
  VOICESTUDIO_URL, OMNIVOICE_URL        base completa (padrão http://127.0.0.1:3900)
  VOICESTUDIO_PORT, OMNIVOICE_PORT      porta quando só ela muda (padrão 3900)
  VOICESTUDIO_API_KEY, OMNIVOICE_API_KEY  opcional; loopback não pede credencial"""


# What the MCP tool accepts as an input file (after resolving links) and where it never reads or writes.
AUDIO_EXTS = frozenset({".wav", ".mp3", ".m4a", ".flac", ".ogg", ".opus", ".aac", ".wma", ".aif", ".aiff"})
VIDEO_EXTS = frozenset({".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"})
_ROOTS_POSIX = ("/etc", "/usr", "/bin", "/sbin", "/lib", "/lib32", "/lib64", "/libx32", "/boot", "/dev", "/proc", "/sys", "/run",
                "/System", "/Library", "/private/etc")
_ROOTS_WINDOWS = ("SYSTEMROOT", "PROGRAMFILES", "PROGRAMFILES(X86)", "PROGRAMDATA")


class VoiceStudioError(Exception):
    """VoiceStudio is not running, refused a call or returned something this module cannot use."""


def base_url() -> str:
    """Base URL of the local app: VOICESTUDIO_URL/OMNIVOICE_URL, else loopback with VOICESTUDIO_PORT/OMNIVOICE_PORT."""
    explicit = os.environ.get("VOICESTUDIO_URL") or os.environ.get("OMNIVOICE_URL")
    if explicit:
        return explicit.rstrip("/")
    port = os.environ.get("VOICESTUDIO_PORT") or os.environ.get("OMNIVOICE_PORT") or str(DEFAULT_PORT)
    port = port.strip()
    if not port.isdigit() or not 0 < int(port) < 65536:
        raise VoiceStudioError(f"porta inválida em VOICESTUDIO_PORT/OMNIVOICE_PORT: {port!r} (esperava 1-65535)")
    return f"http://127.0.0.1:{port}"


def is_loopback_base(base: str) -> bool:
    """True when `base` is http(s) on 127.0.0.0/8, ::1 or localhost, without credentials in the URL."""
    try:
        parts = urllib.parse.urlsplit(base)
        host = parts.hostname
    except ValueError:
        return False
    if parts.scheme not in ("http", "https") or parts.username or parts.password or not host:
        return False
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _forbidden_input_place(real: Path) -> str | None:
    """Why the MCP tool never READS this (already resolved) path: a system folder or a hidden folder of the home. Reading keeps the narrow
    rule it always had (the 16 roots below); the one rule of `terceiros` is where the engine does not WRITE, and `_forbidden_place` uses it."""
    roots = [Path(r) for r in _ROOTS_POSIX]
    roots += [Path(os.environ[v]) for v in _ROOTS_WINDOWS if os.environ.get(v)]
    for root in roots:
        try:
            root = root.resolve()
        except (OSError, RuntimeError):
            continue
        if real == root or root in real.parents:
            return f"pasta do sistema ({root})"
    try:
        home = Path.home().resolve()
    except (OSError, RuntimeError, KeyError):
        return None
    if home in real.parents and real.relative_to(home).parts[0].startswith("."):
        return f"pasta oculta do home ({home / real.relative_to(home).parts[0]})"
    return None


def _forbidden_place(real: Path) -> str | None:
    """Why the MCP tool never WRITES at this (already resolved) path: the one rule of `terceiros`, the same for every track (system,
    auto-start, hidden and .git folders, the engine's own places). The two things this module always refused, a system folder and a hidden
    folder of the home, keep the words it always used, with the folder that matched ("pasta do sistema (/etc)", a noun phrase that `_em`
    completes); the rest are the words of the rule, which carry their own preposition ("em pasta de início automático (...)",
    "dentro de uma pasta .git")."""
    return _forbidden_input_place(real) or terceiros.lugar_proibido(real)


def _em(place: str) -> str:
    """The words that follow "o MCP não grava": a bare place takes "em"; the words of the one rule already carry their preposition."""
    return place if place.startswith(("em ", "dentro ")) else f"em {place}"


def _guard_abs(value, what: str) -> Path:
    if not isinstance(value, str) or not value or value.startswith("~") or not os.path.isabs(value):
        raise VoiceStudioError(f"{what} precisa ser um caminho absoluto (recebi {value!r}): o servidor MCP não sabe em que pasta o cliente está.")
    return Path(value)


def _guard_input(value, exts, what: str) -> str:
    """MCP input file: absolute, links resolved, a regular file whose real name has a media extension, outside system/hidden folders.
    Returns the resolved path, which is what the command then uses."""
    path = _guard_abs(value, what)
    try:
        real = path.resolve(strict=True)
    except (OSError, RuntimeError):
        raise VoiceStudioError(f"{what}: arquivo não encontrado: {value}") from None
    if not real.is_file():
        raise VoiceStudioError(f"{what}: não é um arquivo comum: {value}")
    if real.suffix.lower() not in exts:
        raise VoiceStudioError(f"{what}: o arquivo (depois de seguir links) não é de mídia aceita ({', '.join(sorted(exts))}): {real.name}")
    place = _forbidden_input_place(real)
    if place:
        raise VoiceStudioError(f"{what}: o MCP não lê de {place}")
    return str(real)


def _guard_out(value, what: str = "--out") -> str:
    """MCP output file: absolute, in a folder that already exists, not a link, not existing, outside system/hidden folders."""
    path = _guard_abs(value, what)
    if path.is_symlink():
        raise VoiceStudioError(f"{what} não pode ser um link simbólico: {value}")
    if not path.parent.is_dir():
        raise VoiceStudioError(f"{what}: a pasta {path.parent} não existe (o MCP não cria pastas)")
    real = path.parent.resolve() / path.name
    place = _forbidden_place(real)
    if place:
        raise VoiceStudioError(f"{what}: o MCP não grava {_em(place)}")
    if os.path.lexists(real):
        raise VoiceStudioError(f"{what}: já existe {value} (o MCP não sobrescreve; escolha outro nome)")
    return str(real)


def _mcp_guard(a) -> None:
    """The extra rules of the MCP channel, applied to the parsed command; paths are replaced by the checked ones."""
    cmd = a.cmd
    if cmd == "tts":
        if not a.out:
            raise VoiceStudioError("tts precisa de --out com um caminho absoluto: o MCP não escolhe um nome nem grava na pasta do servidor")
        a.out = _guard_out(a.out)
    elif cmd == "dub-export":
        a.out = _guard_out(a.out)
    elif cmd == "transcribe":
        a.audio = _guard_input(a.audio, AUDIO_EXTS, "AUDIO")
    elif cmd == "clone":
        a.audio = _guard_input(a.audio, AUDIO_EXTS, "REFERENCIA")
    elif cmd == "dub" and a.dub_cmd == "create":
        a.media = _guard_input(a.media, (VIDEO_EXTS | AUDIO_EXTS) if a.audio else VIDEO_EXTS, "VIDEO")


class _Multipart:
    """A multipart/form-data body read from the file as the socket asks for it (no copy of the file in memory).
    Segments are bytes or (path, size); `length` is the total, for Content-Length."""

    def __init__(self, segments):
        self._segments = list(segments)
        self.length = sum(len(x) if isinstance(x, bytes) else x[1] for x in self._segments)
        self._gen = self._chunks()
        self._buf = b""

    def _chunks(self):
        for seg in self._segments:
            if isinstance(seg, bytes):
                yield seg
                continue
            path, size = seg
            with open(path, "rb") as fh:
                left = size
                while left:
                    chunk = fh.read(min(1024 * 1024, left))
                    if not chunk:
                        raise VoiceStudioError(f"o arquivo mudou durante o envio: {path}")
                    left -= len(chunk)
                    yield chunk

    def read(self, n: int | None = -1) -> bytes:
        if n is None or n < 0:
            data, self._buf = self._buf + b"".join(self._gen), b""
            return data
        while len(self._buf) < n:
            try:
                self._buf += next(self._gen)
            except StopIteration:
                break
        data, self._buf = self._buf[:n], self._buf[n:]
        return data


def _api_key() -> str | None:
    return os.environ.get("VOICESTUDIO_API_KEY") or os.environ.get("OMNIVOICE_API_KEY") or None


def default_transport(method: str, url: str, body: bytes | None, headers: dict, timeout: float):
    """One HTTP call -> (status, headers, body). HTTP errors come back as a status; a closed app is a VoiceStudioError."""
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:  # a response, not a transport failure
        return e.code, dict(e.headers or {}), e.read()
    except urllib.error.URLError as e:
        raise VoiceStudioError(f"não consegui falar com o VoiceStudio em {url} ({e.reason}). {OPEN_APP}") from None
    except (TimeoutError, OSError) as e:
        raise VoiceStudioError(f"o VoiceStudio em {url} não respondeu a tempo ({e}). {OPEN_APP}") from None


def _decode(raw: bytes) -> str:
    return raw.decode("utf-8", "replace")


def _short(raw: bytes, limit: int = 300) -> str:
    text = _decode(raw).strip().replace("\n", " ")
    return text[:limit] if text else "(resposta vazia)"


def _header(headers: dict, name: str) -> str | None:
    for k, v in (headers or {}).items():
        if k.lower() == name.lower():
            return v
    return None


def _rpc_message(raw: bytes, headers: dict, expect_id) -> dict:
    """A JSON-RPC response, plain JSON or an SSE event stream (Streamable HTTP answers both ways)."""
    text = _decode(raw).strip()
    if not text:
        if expect_id is None:
            return {}
        raise VoiceStudioError("o MCP do VoiceStudio devolveu uma resposta vazia")
    ctype = (_header(headers, "content-type") or "").lower()
    if "text/event-stream" in ctype or text.startswith("data:") or text.startswith("event:"):
        messages = []
        for line in text.splitlines():
            line = line.strip()
            if not line.startswith("data:"):
                continue
            chunk = line[5:].strip()
            if not chunk or chunk == "[DONE]":
                continue
            try:
                messages.append(json.loads(chunk))
            except ValueError:
                continue
        if expect_id is not None:
            for message in messages:
                if message.get("id") == expect_id:
                    return message
        if messages:
            return messages[-1]
        raise VoiceStudioError("o MCP do VoiceStudio devolveu um evento sem JSON")
    try:
        message = json.loads(text)
    except ValueError:
        raise VoiceStudioError(f"o MCP do VoiceStudio não devolveu JSON: {_short(raw)}") from None
    if isinstance(message, list):
        for item in message:
            if isinstance(item, dict) and item.get("id") == expect_id:
                return item
        return message[-1] if message else {}
    if not isinstance(message, dict):
        raise VoiceStudioError(f"o MCP do VoiceStudio devolveu {type(message).__name__}, esperava um objeto JSON-RPC")
    return message


def _content_text(result: dict) -> str:
    parts = [c.get("text", "") for c in result.get("content") or [] if isinstance(c, dict) and c.get("type") == "text"]
    return "\n".join(p for p in parts if p).strip()


def _tool_data(name: str, result: dict):
    """The JSON payload of a tool. Some tools return JSON text inside the MCP result, others structured content."""
    structured = result.get("structuredContent")
    if isinstance(structured, (dict, list)):
        data = structured
    else:
        text = _content_text(result)
        if not text:
            raise VoiceStudioError(f"{name}: o MCP do VoiceStudio não devolveu texto nem conteúdo estruturado")
        try:
            data = json.loads(text)
        except ValueError:
            raise VoiceStudioError(f"{name}: a resposta não é JSON: {text[:200]}") from None
    if isinstance(data, dict) and data.get("error"):
        raise VoiceStudioError(f"{name}: {data['error']}")
    return data

def _dub_error(status: int, raw: bytes, job_id: str, lang: str) -> str:
    """A readable message for an error of GET /dub/download: FastAPI's {"detail": "..."} or {"detail": {"code", "message"}}."""
    try:
        detail = json.loads(_decode(raw)).get("detail")
    except (ValueError, AttributeError):
        detail = None
    code = detail.get("code") if isinstance(detail, dict) else None
    text = (detail.get("message") if isinstance(detail, dict) else detail) or _short(raw)
    if status == 404:
        return f"o app não tem o job {job_id} (HTTP 404: {text}). Confira o id na tela de dublagem do app."
    if code == "dub_background_unavailable" or status == 409:
        return (f"o app não conseguiu preservar o fundo do job {job_id} ({text}). O job precisa ter o áudio original separado "
                "(fundo sem voz) e os tempos das falas; refaça a dublagem no app com a separação de fundo ligada.")
    if status == 400:
        return f"o app recusou o export do job {job_id} no idioma {lang} (HTTP 400: {text}). O idioma precisa ter uma faixa dublada pronta no app."
    if status in (401, 403):
        return f"o app recusou o acesso (HTTP {status}: {text}). Defina VOICESTUDIO_API_KEY se o app pede chave."
    return f"HTTP {status} em {DUB_DOWNLOAD_PATH}{job_id}: {text}"


def _upload_error(status: int, raw: bytes, job_id: str | None) -> str:
    """A readable message for an error of POST /dub/upload (FastAPI's {"detail": ...})."""
    try:
        detail = json.loads(_decode(raw)).get("detail")
    except (ValueError, AttributeError):
        detail = None
    text = (detail.get("message") if isinstance(detail, dict) else detail) or _short(raw)
    if status == 409:
        return f"já existe um job com o id {job_id or '?'} no app (HTTP 409: {text}). Omita --job-id para o app gerar um novo."
    if status == 415:
        return f"o app não aceita esse formato de arquivo (HTTP 415: {text}). Use um vídeo comum (mp4, mov, mkv, webm) ou --audio."
    if status in (401, 403):
        return f"o app recusou o acesso (HTTP {status}: {text}). Defina VOICESTUDIO_API_KEY se o app pede chave."
    if status in (400, 422):
        return f"o app recusou o upload (HTTP {status}: {text})."
    return f"HTTP {status} em {DUB_UPLOAD_PATH}: {text}"


class VoiceStudio:
    """A client for one VoiceStudio backend. `transport` is the seam the tests replace (no sockets, no app needed)."""

    def __init__(self, base: str | None = None, transport=None, timeout: float = 30.0, client_id: str = CLIENT_ID):
        self.base = (base or base_url()).rstrip("/")
        self.timeout = timeout
        self.client_id = client_id
        self._transport = transport or default_transport
        self._session_id: str | None = None
        self._next_id = 0

    # ---- plumbing -------------------------------------------------------------------------------------------

    def _require_loopback(self, what: str) -> None:
        """Calls that send a file (or a recording) only go to this machine: a base elsewhere never receives the bytes."""
        if not is_loopback_base(self.base):
            raise VoiceStudioError(f"{what} só fala com o VoiceStudio nesta máquina (loopback: 127.0.0.0/8, ::1 ou localhost); "
                                   f"a base configurada é {self.base!r}. Aponte VOICESTUDIO_URL/OMNIVOICE_URL para o app local.")

    def _id(self) -> int:
        self._next_id += 1
        return self._next_id

    def _headers(self) -> dict:
        headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream",
                   "X-OmniVoice-Client-Id": self.client_id}
        key = _api_key()
        if key:
            headers["Authorization"] = "Bearer " + key
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id
        return headers

    def _post_rpc(self, payload: dict) -> tuple[dict, dict]:
        url = self.base + MCP_PATH
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        status, headers, raw = self._transport("POST", url, body, self._headers(), self.timeout)
        lower = {str(k).lower(): v for k, v in (headers or {}).items()}
        if status in (401, 403):
            raise VoiceStudioError(f"o VoiceStudio recusou a chamada (HTTP {status}) em {url}; confira "
                                   "VOICESTUDIO_API_KEY/OMNIVOICE_API_KEY (loopback normalmente não pede chave)")
        if status in (404, 405):
            raise VoiceStudioError(f"o VoiceStudio respondeu HTTP {status} em {url}: esta versão não serve o MCP nesse "
                                   "caminho (use /mcp/, com barra no fim). " + OPEN_APP)
        if status >= 400:
            raise VoiceStudioError(f"HTTP {status} do VoiceStudio em {url}: {_short(raw)}")
        return _rpc_message(raw, lower, payload.get("id")), lower

    def _notify(self, method: str) -> None:
        body = json.dumps({"jsonrpc": "2.0", "method": method}).encode("utf-8")
        try:
            self._transport("POST", self.base + MCP_PATH, body, self._headers(), self.timeout)
        except VoiceStudioError:
            pass  # the handshake already answered; a lost notification is not worth failing the call

    def _ensure_session(self) -> None:
        if self._session_id:
            return
        message, headers = self._post_rpc({
            "jsonrpc": "2.0", "id": self._id(), "method": "initialize",
            "params": {"protocolVersion": PROTOCOL_VERSION, "capabilities": {},
                       "clientInfo": {"name": CLIENT_ID, "version": "1"}},
        })
        if message.get("error"):
            raise VoiceStudioError(f"initialize recusado pelo VoiceStudio: {message['error']}")
        session = headers.get("mcp-session-id")
        if session:
            self._session_id = session
        self._notify("notifications/initialized")

    def call_tool(self, name: str, arguments: dict | None = None) -> dict:
        """Raw MCP tools/call result (content blocks); the typed methods below parse the payload."""
        self._ensure_session()
        message, _ = self._post_rpc({
            "jsonrpc": "2.0", "id": self._id(), "method": "tools/call",
            "params": {"name": name, "arguments": arguments or {}},
        })
        if message.get("error"):
            error = message["error"]
            detail = error.get("message") if isinstance(error, dict) else error
            raise VoiceStudioError(f"{name}: erro do MCP: {detail}")
        result = message.get("result")
        if not isinstance(result, dict):
            raise VoiceStudioError(f"{name}: resposta do MCP sem result")
        if result.get("isError"):
            raise VoiceStudioError(f"{name}: {_content_text(result) or 'erro sem mensagem'}")
        return result

    def _tool_json(self, name: str, arguments: dict | None = None):
        return _tool_data(name, self.call_tool(name, arguments))

    # ---- discovery and health -------------------------------------------------------------------------------

    def discovery(self) -> dict:
        """GET /.well-known/voicestudio-speech: what this backend advertises about speech."""
        url = self.base + WELL_KNOWN
        status, _, raw = self._transport("GET", url, None, {"Accept": "application/json"}, self.timeout)
        if status == 404:
            raise VoiceStudioError(f"{self.base} respondeu 404 em {WELL_KNOWN}: não parece um VoiceStudio. " + OPEN_APP)
        if status >= 400:
            raise VoiceStudioError(f"HTTP {status} em {WELL_KNOWN}: {_short(raw)}")
        try:
            data = json.loads(_decode(raw))
        except ValueError:
            raise VoiceStudioError(f"{WELL_KNOWN} não devolveu JSON: {_short(raw)}") from None
        if not isinstance(data, dict):
            raise VoiceStudioError(f"{WELL_KNOWN} devolveu {type(data).__name__}, esperava um objeto")
        return data

    def check_health(self) -> dict:
        """MCP check_health: backend status plus the active GPU device."""
        data = self._tool_json("check_health")
        if not isinstance(data, dict):
            raise VoiceStudioError(f"check_health devolveu {type(data).__name__}, esperava um objeto")
        return data

    def status(self) -> dict:
        health = self.check_health()
        report = {"url": self.base, "reachable": True, "health": health}
        try:
            report["discovery"] = self.discovery()
        except VoiceStudioError:
            report["discovery"] = None
        return report

    # ---- voices, languages, personalities -------------------------------------------------------------------

    def list_voices(self) -> list:
        data = self._tool_json("list_voices")
        if isinstance(data, dict) and isinstance(data.get("voices"), list):
            return data["voices"]
        if not isinstance(data, list):
            raise VoiceStudioError(f"list_voices devolveu {type(data).__name__}, esperava uma lista de perfis")
        return data

    def list_languages(self) -> dict:
        data = self._tool_json("list_languages")
        if not isinstance(data, dict):
            raise VoiceStudioError(f"list_languages devolveu {type(data).__name__}, esperava um objeto")
        return data

    def list_personalities(self) -> list:
        data = self._tool_json("list_personalities")
        if isinstance(data, dict) and isinstance(data.get("personalities"), list):
            return data["personalities"]
        if not isinstance(data, list):
            raise VoiceStudioError(f"list_personalities devolveu {type(data).__name__}, esperava uma lista")
        return data

    def describe_voice(self, description: str) -> dict:
        data = self._tool_json("describe_voice", {"description": description})
        if not isinstance(data, dict):
            raise VoiceStudioError(f"describe_voice devolveu {type(data).__name__}, esperava um objeto")
        return data

    def design_voice(self, name: str, description: str, language: str | None = None) -> dict:
        arguments: dict = {"name": name, "description": description}
        if language:
            arguments["language"] = language
        data = self._tool_json("design_voice", arguments)
        if not isinstance(data, dict):
            raise VoiceStudioError(f"design_voice devolveu {type(data).__name__}, esperava um objeto")
        return data

    # ---- speech ---------------------------------------------------------------------------------------------

    def _speech_arguments(self, text: str, profile_id: str | None, language: str | None, fmt: str,
                          instruct: str | None, speed: float | None, steps: int | None) -> dict:
        if fmt not in ("wav", "ogg", "opus"):
            raise VoiceStudioError(f"formato de áudio desconhecido: {fmt!r} (use wav, ogg ou opus)")
        arguments: dict = {"text": text, "format": fmt}
        if profile_id:
            arguments["profile_id"] = profile_id
        if language:
            arguments["language"] = language
        if instruct:
            arguments["instruct"] = instruct
        if speed is not None:
            arguments["speed"] = speed
        if steps is not None:
            arguments["steps"] = steps
        return arguments

    def generate_speech(self, text: str, profile_id: str | None = None, language: str | None = None,
                        fmt: str = "wav", instruct: str | None = None, speed: float | None = None,
                        steps: int | None = None) -> dict:
        """Raw generate_speech payload: audio_id, durations and the audio shaped by OMNIVOICE_MCP_OUTPUT_MODE."""
        arguments = self._speech_arguments(text, profile_id, language, fmt, instruct, speed, steps)
        data = self._tool_json("generate_speech", arguments)
        if not isinstance(data, dict):
            raise VoiceStudioError(f"generate_speech devolveu {type(data).__name__}, esperava um objeto")
        return data

    def _audio_bytes(self, result: dict, payload: dict) -> bytes:
        """Audio out of the result: output_path/audio_url (files/both) first, then wav_base64 (resources)."""
        output_path = payload.get("output_path")
        if output_path:
            path = Path(str(output_path)).expanduser()
            if path.is_file():
                return path.read_bytes()
        audio_url = payload.get("audio_url")
        if audio_url:
            url = str(audio_url)
            if not url.startswith(("http://", "https://")):
                url = self.base + ("" if url.startswith("/") else "/") + url
            status, _, raw = self._transport("GET", url, None, {"Accept": "audio/*"}, max(self.timeout, 300.0))
            if status >= 400:
                raise VoiceStudioError(f"HTTP {status} ao baixar o áudio em {url}: {_short(raw)}")
            return raw
        for key in ("wav_base64", "audio_base64", "base64"):
            value = payload.get(key)
            if isinstance(value, str) and value:
                try:
                    return base64.b64decode(value, validate=True)
                except ValueError:
                    raise VoiceStudioError(f"generate_speech devolveu {key} que não é base64 válido") from None
        for block in result.get("content") or []:
            if not isinstance(block, dict):
                continue
            if block.get("type") in ("audio", "resource", "blob"):
                source = block.get("data") or block.get("blob") or (block.get("resource") or {}).get("blob")
                if isinstance(source, str) and source:
                    return base64.b64decode(source)
        raise VoiceStudioError(
            "generate_speech não devolveu áudio (nem output_path, nem audio_url, nem wav_base64). "
            "Confira OMNIVOICE_MCP_OUTPUT_MODE no app (resources, files ou both).")

    def speak(self, text: str, out_path: str | Path, profile_id: str | None = None, language: str | None = None,
              fmt: str = "wav") -> dict:
        """text -> audio file. Writes out_path and returns where it landed plus the generation metadata."""
        if not text.strip():
            raise VoiceStudioError("o texto está vazio: nada para falar")
        arguments = self._speech_arguments(text, profile_id, language, fmt, None, None, None)
        result = self.call_tool("generate_speech", arguments)
        payload = _tool_data("generate_speech", result)
        if not isinstance(payload, dict):
            raise VoiceStudioError(f"generate_speech devolveu {type(payload).__name__}, esperava um objeto")
        audio = self._audio_bytes(result, payload)
        dst = Path(out_path).expanduser()
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(audio)
        return {"out": str(dst.resolve()), "bytes": len(audio), "format": fmt,
                "audio_id": payload.get("audio_id"), "duration_s": payload.get("audio_duration_s"),
                "generation_time_s": payload.get("generation_time_s"), "profile_id": profile_id}

    # ---- transcription and cloning --------------------------------------------------------------------------

    def transcribe(self, path: str | Path, language: str | None = None, via: str = "mcp"):
        """Audio file -> text. via=mcp sends audio_base64 (no base path needed); via=rest uses the OpenAI endpoint."""
        self._require_loopback("transcribe")
        audio = Path(path).expanduser()
        if not audio.is_file():
            raise VoiceStudioError(f"arquivo de áudio não encontrado: {path}")
        if via == "mcp":
            arguments: dict = {"audio_base64": base64.b64encode(audio.read_bytes()).decode("ascii")}
            if language:
                arguments["language"] = language
            result = self._tool_json("transcribe", arguments)
            if not isinstance(result, dict):
                raise VoiceStudioError(f"transcribe devolveu {type(result).__name__}, esperava um objeto")
            return result
        if via == "rest":
            return self._transcribe_rest(audio, language)
        raise VoiceStudioError(f"via de transcrição desconhecida: {via!r} (use mcp ou rest)")

    def _transcribe_rest(self, audio: Path, language: str | None) -> dict:
        size = audio.stat().st_size
        if size > MAX_DUB_UPLOAD_BYTES:
            raise VoiceStudioError(f"arquivo grande demais para subir por aqui ({size} bytes; o limite é {MAX_DUB_UPLOAD_BYTES})")
        boundary = "simplicio-" + os.urandom(16).hex()
        filename = audio.name.replace('"', "_").replace("\r", "_").replace("\n", "_")
        segments: list = [
            (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{filename}\"\r\n"
             "Content-Type: application/octet-stream\r\n\r\n").encode("utf-8"),
            (audio, size),
            b"\r\n",
        ]
        if language:
            segments.append((f"--{boundary}\r\nContent-Disposition: form-data; name=\"language\"\r\n\r\n"
                             f"{language}\r\n").encode("utf-8"))
        segments.append(f"--{boundary}--\r\n".encode("utf-8"))
        body = _Multipart(segments)
        url = self.base + TRANSCRIPTIONS_PATH
        headers = {"Content-Type": f"multipart/form-data; boundary={boundary}", "Accept": "application/json",
                   "Content-Length": str(body.length)}
        key = _api_key()
        if key:
            headers["Authorization"] = "Bearer " + key
        status, _, raw = self._transport("POST", url, body, headers, max(self.timeout, 300.0))
        if status == 404:
            raise VoiceStudioError(f"{self.base} não serve {TRANSCRIPTIONS_PATH} (HTTP 404): use a via MCP "
                                   "(sem --rest) ou atualize o VoiceStudio.")
        if status >= 400:
            raise VoiceStudioError(f"HTTP {status} em {TRANSCRIPTIONS_PATH}: {_short(raw)}")
        text = _decode(raw).strip()
        try:
            parsed = json.loads(text)
        except ValueError:
            return {"text": text}
        if not isinstance(parsed, dict):
            raise VoiceStudioError(f"{TRANSCRIPTIONS_PATH} devolveu {type(parsed).__name__}, esperava um objeto")
        if parsed.get("error"):
            raise VoiceStudioError(f"transcribe (rest): {parsed['error']}")
        return parsed

    def dub_export(self, job_id: str, lang: str, out_path: str | Path, bed_level: float = 1.0) -> dict:
        """Export a dubbing job that already exists in the app, with the original background (music and effects) kept under the dub.

        GET /dub/download/{job_id}?preserve_bg=true&bed_level=..&default_track=LANG&include_tracks=LANG answers with the MP4.
        Nothing is generated here: the app transcribes, translates and speaks (heavy models, GPU); this only collects the result.
        """
        job_id = str(job_id).strip()
        lang = str(lang).strip()
        if not _JOB_ID.match(job_id):
            raise VoiceStudioError(f"id de job inválido: {job_id!r} (o app usa só letras, números, hífen e sublinhado, até 64)")
        if not _LANG.match(lang):
            raise VoiceStudioError(f"código de idioma inválido: {lang!r} (use o código da faixa dublada, ex.: pl, pt, en)")
        try:
            level = float(bed_level)
        except (TypeError, ValueError):
            raise VoiceStudioError(f"--bed-level inválido: {bed_level!r} (número de 0 a {MAX_BED_LEVEL:g})") from None
        if not 0.0 <= level <= MAX_BED_LEVEL:  # also false for nan
            raise VoiceStudioError(f"--bed-level fora da faixa: {level:g} (o app aceita de 0 a {MAX_BED_LEVEL:g}; 1.0 é o nível original)")
        out = Path(out_path)
        query = urllib.parse.urlencode({"preserve_bg": "true", "bed_level": repr(level), "default_track": lang, "include_tracks": lang})
        url = f"{self.base}{DUB_DOWNLOAD_PATH}{job_id}?{query}"
        headers = {"Accept": "video/mp4", "X-OmniVoice-Client-Id": self.client_id}
        key = _api_key()
        if key:
            headers["Authorization"] = "Bearer " + key
        status, resp_headers, raw = self._transport("GET", url, None, headers, max(self.timeout, 600.0))
        if status >= 400:
            raise VoiceStudioError(_dub_error(status, raw, job_id, lang))
        ctype = (_header(resp_headers, "Content-Type") or "").lower()
        if not raw or "json" in ctype or "text/" in ctype:
            raise VoiceStudioError(f"o app não devolveu um vídeo para o job {job_id} (Content-Type {ctype or 'ausente'}, "
                                   f"{len(raw)} bytes): {_short(raw)}")
        out.parent.mkdir(parents=True, exist_ok=True)
        tmp = out.with_name(out.name + ".part")
        tmp.write_bytes(raw)
        tmp.replace(out)
        return {"out": str(out), "bytes": len(raw), "job": job_id, "lang": lang, "bed_level": level, "preserve_bg": True,
                "warning": _header(resp_headers, "X-Dub-Export-Warning")}

    def dub_create(self, media_path: str | Path, source_lang: str | None = None, input_type: str = "video",
                   job_id: str | None = None) -> dict:
        """Create a dubbing job in the app: POST /dub/upload (multipart). The app stores the file and starts the prep
        (audio extraction, background separation) as a background task; it answers 202 with the ids.

        Nothing is transcribed, translated or spoken here, and no voice is cloned: those steps (heavy models, GPU) run in the
        app, where the speakers' voices are chosen. Cloning or dubbing the voice of a real person needs that person's
        recorded consent. `dub-export` collects the result.
        """
        self._require_loopback("dub create")
        if input_type not in ("video", "audio"):
            raise VoiceStudioError(f"tipo de entrada desconhecido: {input_type!r} (use video ou audio)")
        job = str(job_id).strip() if job_id is not None else None
        if job is not None and not _JOB_ID.match(job):
            raise VoiceStudioError(f"id de job inválido: {job!r} (o app usa só letras, números, hífen e sublinhado, até 64)")
        lang = str(source_lang).strip() if source_lang else None
        if lang is not None and not _LANG.match(lang):
            raise VoiceStudioError(f"código de idioma inválido: {lang!r} (use o código do idioma falado, ex.: pt, en)")
        media = Path(media_path).expanduser()
        if not media.is_file():
            raise VoiceStudioError(f"arquivo não encontrado: {media_path}")
        size = media.stat().st_size
        if size == 0:
            raise VoiceStudioError(f"o arquivo está vazio: {media_path}")
        if size > MAX_DUB_UPLOAD_BYTES:
            raise VoiceStudioError(f"arquivo grande demais para subir por aqui ({size} bytes; o limite é {MAX_DUB_UPLOAD_BYTES}): "
                                   "abra-o direto no app.")
        boundary = "simplicio-" + os.urandom(16).hex()
        filename = media.name.replace('"', "_").replace("\r", "_").replace("\n", "_")
        fields = [("input_type", input_type)]
        if job:
            fields.append(("job_id", job))
        if lang:
            fields.append(("source_lang", lang))
        segments: list = [
            (f"--{boundary}\r\nContent-Disposition: form-data; name=\"video\"; filename=\"{filename}\"\r\n"
             "Content-Type: application/octet-stream\r\n\r\n").encode("utf-8"),
            (media, size),
            b"\r\n",
        ]
        for key, value in fields:
            segments.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{key}\"\r\n\r\n{value}\r\n".encode("utf-8"))
        segments.append(f"--{boundary}--\r\n".encode("utf-8"))
        body = _Multipart(segments)
        headers = {"Content-Type": f"multipart/form-data; boundary={boundary}", "Accept": "application/json",
                   "X-OmniVoice-Client-Id": self.client_id, "Content-Length": str(body.length)}
        api_key = _api_key()
        if api_key:
            headers["Authorization"] = "Bearer " + api_key
        status, _, raw = self._transport("POST", self.base + DUB_UPLOAD_PATH, body, headers, max(self.timeout, 600.0))
        if status >= 400:
            raise VoiceStudioError(_upload_error(status, raw, job))
        try:
            data = json.loads(_decode(raw))
        except ValueError:
            raise VoiceStudioError(f"{DUB_UPLOAD_PATH} não devolveu JSON: {_short(raw)}") from None
        if not isinstance(data, dict) or not data.get("job_id"):
            raise VoiceStudioError(f"{DUB_UPLOAD_PATH} não devolveu job_id: {_short(raw)}")
        new_id = str(data["job_id"])
        return {"job": new_id, "task": data.get("task_id"), "filename": data.get("filename") or media.name,
                "input_type": input_type, "source_lang": lang,
                "next": ("o app prepara o job em segundo plano; quando estiver pronto, transcreva, traduza e gere a dublagem no app "
                         "(vozes e falantes são escolhidos lá) e exporte com: simplicio-video voicestudio dub-export "
                         f"--job {new_id} --lang <idioma> -o <arquivo.mp4>")}

    def clone_voice(self, ref_audio_path: str | Path, name: str, language: str | None = None,
                    ref_text: str | None = None) -> dict:
        """Reference clip -> new voice profile. The clip goes as base64, so no OMNIVOICE_MCP_BASE_PATH is needed."""
        self._require_loopback("clone")
        ref = Path(ref_audio_path).expanduser()
        if not ref.is_file():
            raise VoiceStudioError(f"áudio de referência não encontrado: {ref_audio_path}")
        if not name.strip():
            raise VoiceStudioError("o nome do perfil está vazio")
        arguments: dict = {"name": name, "ref_audio_base64": base64.b64encode(ref.read_bytes()).decode("ascii")}
        if language:
            arguments["language"] = language
        if ref_text:
            arguments["ref_text"] = ref_text
        data = self._tool_json("clone_voice", arguments)
        if not isinstance(data, dict):
            raise VoiceStudioError(f"clone_voice devolveu {type(data).__name__}, esperava um objeto")
        return data


# ---- MCP client config (the calls are the methods of VoiceStudio, one client per call; tests replace default_transport) ----

def mcp_config() -> dict:
    """The MCP client block for this backend (Streamable HTTP, trailing slash)."""
    return {"mcpServers": {"voicestudio": {"url": base_url() + MCP_PATH}}}

# ---- CLI -------------------------------------------------------------------------------------------------------

def _emit(obj, as_json: bool, text: str) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2) if as_json else text)


def _status_text(report: dict) -> str:
    lines = [f"VoiceStudio: {report['url']} (alcançável)"]
    lines.append("saúde (check_health):")
    lines.append(json.dumps(report["health"], ensure_ascii=False, indent=2))
    if report.get("discovery") is not None:
        lines.append("descoberta (/.well-known/voicestudio-speech):")
        lines.append(json.dumps(report["discovery"], ensure_ascii=False, indent=2))
    lines.append("fora do render determinístico: o que ele gera entra num contrato como arquivo com hash.")
    return "\n".join(lines)


def _voices_text(rows: list, base: str) -> str:
    lines = [f"{len(rows)} perfil(is) de voz em {base}:"]
    for v in rows:
        if not isinstance(v, dict):
            lines.append(f"  {v}")
            continue
        kind = v.get("kind") or v.get("type") or "-"
        lines.append(f"  {str(v.get('id') or '?'):<24} {str(v.get('name') or '?'):<28} {str(kind):<7} "
                     f"{v.get('personality') or ''}")
    return "\n".join(lines)


def _languages_text(data: dict) -> str:
    total = data.get("total") or len(data.get("popular") or [])
    popular = ", ".join(str(x) for x in data.get("popular") or [])
    lines = [f"{total} idioma(s) de TTS; populares: {popular or '-'}"]
    if data.get("note"):
        lines.append(str(data["note"]))
    return "\n".join(lines)


def _persons_text(rows: list) -> str:
    lines = [f"{len(rows)} personalidade(s) de voz:"]
    for p in rows:
        if isinstance(p, dict):
            lines.append(f"  {str(p.get('name') or p.get('id') or '?'):<24} {p.get('instruct') or p.get('description') or ''}")
        else:
            lines.append(f"  {p}")
    return "\n".join(lines)


def _transcribe_text(data: dict) -> str:
    text = data.get("text") or data.get("transcription") or data.get("transcript")
    if text is None:
        return json.dumps(data, ensure_ascii=False, indent=2)
    lines = [f"texto: {text}"]
    extras = [f"{k}={data[k]}" for k in ("language", "duration_s", "duration") if data.get(k) is not None]
    if extras:
        lines.append("  " + " | ".join(extras))
    return "\n".join(lines)


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="simplicio-video voicestudio", description=HELP_DESC, epilog=HELP_EPILOG,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", metavar="SUBCOMANDO", title="subcomandos")

    p = sub.add_parser("status", help="saúde e GPU do VoiceStudio (check_health + descoberta)")
    p.add_argument("--json", action="store_true", help="imprime o relatório em JSON")

    p = sub.add_parser("voices", help="perfis de voz salvos (list_voices)")
    p.add_argument("--json", action="store_true", help="imprime a lista em JSON")

    p = sub.add_parser("languages", help="idiomas de TTS disponíveis (list_languages)")
    p.add_argument("--json", action="store_true", help="imprime o objeto em JSON")

    p = sub.add_parser("personalities", help="presets de personalidade de voz (list_personalities)")
    p.add_argument("--json", action="store_true", help="imprime a lista em JSON")

    p = sub.add_parser("tts", help="texto vira áudio pelo perfil escolhido (generate_speech)")
    p.add_argument("texto", help="texto a falar")
    p.add_argument("--out", "-o", help="arquivo de saída (padrão voicestudio.wav no terminal; pelo MCP é obrigatório e absoluto)")
    p.add_argument("--profile", help="id do perfil de voz (padrão: a voz vinculada a este agente ou a padrão do app)")
    p.add_argument("--language", help="idioma (código ISO ou Auto); omitido = idioma salvo no perfil")
    p.add_argument("--format", default="wav", choices=["wav", "ogg", "opus"], help="formato do áudio (padrão wav)")
    p.add_argument("--json", action="store_true", help="imprime o resultado em JSON")

    p = sub.add_parser("transcribe", help="áudio vira texto (MCP transcribe; --rest usa a API OpenAI-compatible)")
    p.add_argument("audio", metavar="AUDIO", help="arquivo de áudio (wav, mp3, m4a, flac...)")
    p.add_argument("--language", help="idioma do áudio; omitido = detecção automática")
    p.add_argument("--rest", action="store_true", help="usa POST /v1/audio/transcriptions (multipart campo file)")
    p.add_argument("--json", action="store_true", help="imprime o resultado em JSON")

    p = sub.add_parser("clone", help="clona uma voz a partir de um áudio de referência (clone_voice)")
    p.add_argument("audio", metavar="REFERENCIA", help="áudio de referência (5-30 s, uma só voz)")
    p.add_argument("--name", required=True, help="nome humano do novo perfil de voz")
    p.add_argument("--language", help="idioma da referência (código ISO ou Auto)")
    p.add_argument("--ref-text", help="transcrição opcional da referência (melhora alguns motores)")
    p.add_argument("--json", action="store_true", help="imprime o resultado em JSON")

    p = sub.add_parser("describe", help="mostra como uma descrição de voz vira atributos (describe_voice; não salva)")
    p.add_argument("descricao", metavar="DESCRICAO", help="descrição livre, ex.: \"homem idoso, voz grave, sotaque britânico\"")
    p.add_argument("--json", action="store_true", help="imprime o resultado em JSON")

    p = sub.add_parser("design", help="cria um perfil de voz a partir de uma descrição (design_voice)")
    p.add_argument("descricao", metavar="DESCRICAO", help="descrição livre da voz desejada")
    p.add_argument("--name", required=True, help="nome humano do novo perfil de voz")
    p.add_argument("--language", help="idioma salvo do perfil (código ISO ou Auto)")
    p.add_argument("--json", action="store_true", help="imprime o resultado em JSON")

    p = sub.add_parser("dub", help="cria um job de dublagem no app (dub create); a dublagem em si roda no app")
    dsub = p.add_subparsers(dest="dub_cmd", metavar="ACAO", title="ações")
    q = dsub.add_parser("create", help="sobe um vídeo (ou áudio) para o app e cria o job (POST /dub/upload); não transcreve, traduz nem gera voz")
    q.add_argument("media", metavar="VIDEO", help="arquivo de vídeo (ou áudio, com --audio) a dublar")
    q.add_argument("--source-lang", help="idioma falado no original (código ISO); omitido = detecção automática do app")
    q.add_argument("--audio", action="store_true", help="a entrada é só áudio (dublagem sem vídeo)")
    q.add_argument("--job-id", help="id do job (letras, números, hífen, sublinhado; padrão: o app gera)")
    q.add_argument("--json", action="store_true", help="imprime o resultado em JSON")

    p = sub.add_parser("dub-export", help="exporta um job de dublagem que já existe no app, com o fundo (música e efeitos) preservado")
    p.add_argument("--job", required=True, help="id do job de dublagem no app")
    p.add_argument("--lang", required=True, help="código do idioma da faixa dublada (ex.: pl)")
    p.add_argument("--bed-level", type=float, default=1.0, help="volume do fundo de 0 a 4 (1.0 = nível original; padrão 1.0)")
    p.add_argument("--out", "-o", required=True, help="arquivo MP4 de saída")
    p.add_argument("--json", action="store_true", help="imprime o resultado em JSON")

    p = sub.add_parser("mcp", help="bloco de config MCP (Streamable HTTP) para o cliente")
    p.add_argument("--json", action="store_true", help="(o bloco já é JSON)")
    return ap


def _run(a) -> int:
    if a.cmd == "status":
        report = VoiceStudio().status()
        _emit(report, a.json, _status_text(report))
    elif a.cmd == "voices":
        base = base_url()
        rows = VoiceStudio().list_voices()
        _emit(rows, a.json, _voices_text(rows, base))
    elif a.cmd == "languages":
        data = VoiceStudio().list_languages()
        _emit(data, a.json, _languages_text(data))
    elif a.cmd == "personalities":
        rows = VoiceStudio().list_personalities()
        _emit(rows, a.json, _persons_text(rows))
    elif a.cmd == "tts":
        r = VoiceStudio(timeout=600.0).speak(a.texto, a.out or "voicestudio.wav", profile_id=a.profile, language=a.language, fmt=a.format)
        _emit(r, a.json, f"áudio gravado: {r['out']} ({r['bytes']} bytes, {r['format']}"
                          + (f", {r['duration_s']} s" if r.get("duration_s") is not None else "") + ")")
    elif a.cmd == "transcribe":
        data = VoiceStudio(timeout=600.0).transcribe(a.audio, language=a.language, via="rest" if a.rest else "mcp")
        _emit(data, a.json, _transcribe_text(data))
    elif a.cmd == "clone":
        data = VoiceStudio(timeout=600.0).clone_voice(a.audio, a.name, language=a.language, ref_text=a.ref_text)
        _emit(data, a.json, f"perfil criado: {data.get('profile_id') or data.get('id') or '?'} "
                          f"({data.get('name') or a.name}, {data.get('kind') or 'clone'})")
    elif a.cmd == "describe":
        data = VoiceStudio().describe_voice(a.descricao)
        _emit(data, a.json, json.dumps(data, ensure_ascii=False, indent=2))
    elif a.cmd == "design":
        data = VoiceStudio(timeout=600.0).design_voice(a.name, a.descricao, language=a.language)
        _emit(data, a.json, f"perfil criado: {data.get('profile_id') or data.get('id') or '?'} "
                          f"({data.get('name') or a.name}, {data.get('kind') or 'design'})")
    elif a.cmd == "dub":
        if a.dub_cmd != "create":
            print("voicestudio: use 'dub create VIDEO' (ver 'voicestudio dub --help')", file=sys.stderr)
            return 1
        r = VoiceStudio(timeout=600.0).dub_create(a.media, source_lang=a.source_lang, input_type="audio" if a.audio else "video",
                                                  job_id=a.job_id)
        _emit(r, a.json, f"job criado: {r['job']} (tarefa {r['task']}, {r['filename']})\n{r['next']}")
    elif a.cmd == "dub-export":
        r = VoiceStudio(timeout=600.0).dub_export(a.job, a.lang, a.out, bed_level=a.bed_level)
        _emit(r, a.json, f"vídeo gravado: {r['out']} ({r['bytes']} bytes, job {r['job']}, idioma {r['lang']}, fundo {r['bed_level']:g})"
                         + (f"\naviso do app: {r['warning']}" if r.get("warning") else ""))
    else:  # mcp
        print(json.dumps(mcp_config(), ensure_ascii=False, indent=2))
    return 0


def run_voicestudio(argv: list[str], mcp: bool = False) -> int:
    """`mcp=True` is the MCP channel: input files must be absolute, resolved media files and outputs absolute, new, in an existing folder."""
    ap = _parser()
    if argv and argv[0] in ("-h", "--help", "help"):
        ap.print_help()
        return 0
    a = ap.parse_args(argv)
    if not a.cmd:
        ap.print_help(sys.stderr)
        return 1
    try:
        if mcp:
            _mcp_guard(a)
        return _run(a)
    except VoiceStudioError as e:
        print(f"voicestudio: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("voicestudio: interrompido (Ctrl+C); confira o arquivo de saída antes de usar", file=sys.stderr)
        return 130


