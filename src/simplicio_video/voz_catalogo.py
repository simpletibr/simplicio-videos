"""The voice providers as plain data: name, description, whether the provider waits on the network and whether it keeps the raw take.

Data only, no import of the engine: `catalog` (the `list voices` of the CLI and the MCP) reads the table here without loading `voice`.
`voice.REGISTRO` adds to each row what it DOES (`settings`, `gerar`) and builds `voice.PROVIDERS`, `NETWORK_PROVIDERS` and `GENERATIVE`
from these rows, in this order. The order is the one of `list voices` and of the `--provider` help, so it is part of the output.

rede: the lines are generated concurrently (asyncio), because the time is spent waiting on the network; the others burn CPU and stay serial.
guarda_bruto: the raw take stays on disk (gemini next to the AI Studio files, the others in a per-provider subdir), so the run is
reproducible with provider=file.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Ficha:
    nome: str
    descricao: str
    rede: bool
    guarda_bruto: bool


FICHAS: tuple[Ficha, ...] = (
    Ficha("file", "WAV/MP3 per line generated elsewhere (Gemini in Google AI Studio). Default dir assets/audio/vo/external, line-01.wav ...",
          rede=False, guarda_bruto=False),
    Ficha("local", "Provisional local TTS: Kokoro-82M (Apache-2.0) via kokoro-onnx; needs SIMPLICIO_TTS_PY with kokoro_onnx + models in ~/.local/share/simplicio-tts",
          rede=False, guarda_bruto=False),
    Ficha("gemini", "Gemini TTS API (GEMINI_API_KEY from aistudio.google.com/apikey; free tier ok): model/voice/estilo from the contract, WAV 24 kHz kept in the file dir so provider=file reproduces it",
          rede=True, guarda_bruto=True),
    Ficha("voxcpm", "VoxCPM2 (Apache-2.0): voice design (control) or cloning from reference_audio via the `voxcpm` CLI; fixed seed",
          rede=False, guarda_bruto=True),
    Ficha("openvoice", "OpenVoice V2 (MIT): Kokoro base take converted to the reference_audio speaker (needs OPENVOICE_PY + checkpoints_v2)",
          rede=False, guarda_bruto=True),
    Ficha("voicestudio", "VoiceStudio (AGPL-3.0, used over local HTTP only): OpenAI-compatible /v1/audio/speech at VOICESTUDIO_URL (default http://localhost:3900); voice = profile id",
          rede=False, guarda_bruto=True),
    Ficha("audio8", "Audio8 TTS (Apache-2.0 code and 0.6B weights): zero-shot cloning from reference_audio via the `audio8-tts` CLI in its own env (AUDIO8_TTS_BIN)",
          rede=False, guarda_bruto=True),
    Ficha("elevenlabs", "stub in v0.2 (generate elsewhere, then use provider=file)", rede=False, guarda_bruto=False),
    Ficha("xai", "stub in v0.2 (generate elsewhere, then use provider=file)", rede=False, guarda_bruto=False),
)

DESCRICOES: dict[str, str] = {f.nome: f.descricao for f in FICHAS}
