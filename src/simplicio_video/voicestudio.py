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
- OpenAI-compatible REST, used here as the transcription alternative: POST /v1/audio/transcriptions
  (multipart, field 'file'). /v1/audio/speech is the lane the 'voicestudio' voice provider already uses
  (voice_clone.py), not this module.

Only the standard library is used (urllib, json, base64). Every network call has a timeout, and the app being
closed becomes a clear, actionable error instead of a traceback or a hang.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_PORT = 3900
CLIENT_ID = "simplicio-video"
MCP_PATH = "/mcp/"
WELL_KNOWN = "/.well-known/voicestudio-speech"
TRANSCRIPTIONS_PATH = "/v1/audio/transcriptions"
PROTOCOL_VERSION = "2025-06-18"
SUBCOMMANDS = "status|voices|languages|personalities|tts|transcribe|clone|describe|design|mcp"
OPEN_APP = ("Abra o VoiceStudio (ele serve a API em :3900) ou aponte VOICESTUDIO_URL/OMNIVOICE_URL para outra base; "
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
  simplicio-video voicestudio mcp                     # bloco de config MCP para o cliente (Streamable HTTP)

ambiente:
  VOICESTUDIO_URL, OMNIVOICE_URL        base completa (padrão http://127.0.0.1:3900)
  VOICESTUDIO_PORT, OMNIVOICE_PORT      porta quando só ela muda (padrão 3900)
  VOICESTUDIO_API_KEY, OMNIVOICE_API_KEY  opcional; loopback não pede credencial"""


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
        audio = Path(path).expanduser()
        if not audio.is_file():
            raise VoiceStudioError(f"arquivo de áudio não encontrado: {path}")
        data = audio.read_bytes()
        if via == "mcp":
            arguments: dict = {"audio_base64": base64.b64encode(data).decode("ascii")}
            if language:
                arguments["language"] = language
            result = self._tool_json("transcribe", arguments)
            if not isinstance(result, dict):
                raise VoiceStudioError(f"transcribe devolveu {type(result).__name__}, esperava um objeto")
            return result
        if via == "rest":
            return self._transcribe_rest(audio, data, language)
        raise VoiceStudioError(f"via de transcrição desconhecida: {via!r} (use mcp ou rest)")

    def _transcribe_rest(self, audio: Path, data: bytes, language: str | None) -> dict:
        boundary = "simplicio-" + os.urandom(16).hex()
        filename = audio.name.replace('"', "_")
        chunks: list[bytes] = [
            (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{filename}\"\r\n"
             "Content-Type: application/octet-stream\r\n\r\n").encode("utf-8"),
            data,
            b"\r\n",
        ]
        if language:
            chunks += [
                (f"--{boundary}\r\nContent-Disposition: form-data; name=\"language\"\r\n\r\n"
                 f"{language}\r\n").encode("utf-8"),
            ]
        chunks.append(f"--{boundary}--\r\n".encode("utf-8"))
        body = b"".join(chunks)
        url = self.base + TRANSCRIPTIONS_PATH
        headers = {"Content-Type": f"multipart/form-data; boundary={boundary}", "Accept": "application/json"}
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

    def clone_voice(self, ref_audio_path: str | Path, name: str, language: str | None = None,
                    ref_text: str | None = None) -> dict:
        """Reference clip -> new voice profile. The clip goes as base64, so no OMNIVOICE_MCP_BASE_PATH is needed."""
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


# ---- module-level helpers (one client per call; tests replace default_transport) ---------------------------------

def status() -> dict:
    return VoiceStudio().status()


def voices() -> list:
    return VoiceStudio().list_voices()


def languages() -> dict:
    return VoiceStudio().list_languages()


def speak(text: str, out_path: str | Path, profile_id: str | None = None, language: str | None = None,
          fmt: str = "wav") -> dict:
    return VoiceStudio(timeout=600.0).speak(text, out_path, profile_id=profile_id, language=language, fmt=fmt)


def transcribe(path: str | Path, language: str | None = None, via: str = "mcp"):
    return VoiceStudio(timeout=600.0).transcribe(path, language=language, via=via)


def clone_voice(ref_audio_path: str | Path, name: str, language: str | None = None) -> dict:
    return VoiceStudio(timeout=600.0).clone_voice(ref_audio_path, name, language=language)


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
    p.add_argument("--out", "-o", default="voicestudio.wav", help="arquivo de saída (padrão voicestudio.wav)")
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
        r = VoiceStudio(timeout=600.0).speak(a.texto, a.out, profile_id=a.profile, language=a.language, fmt=a.format)
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
    else:  # mcp
        print(json.dumps(mcp_config(), ensure_ascii=False, indent=2))
    return 0


def run_voicestudio(argv: list[str]) -> int:
    ap = _parser()
    if argv and argv[0] in ("-h", "--help", "help"):
        ap.print_help()
        return 0
    a = ap.parse_args(argv)
    if not a.cmd:
        ap.print_help(sys.stderr)
        return 1
    try:
        return _run(a)
    except VoiceStudioError as e:
        print(f"voicestudio: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("voicestudio: interrompido (Ctrl+C); confira o arquivo de saída antes de usar", file=sys.stderr)
        return 130


