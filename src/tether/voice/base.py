"""
Interfaces for voice support. Not implemented - defined here so adding it
later doesn't mean restructuring anything that already works.

Telegram has no built-in speech synthesis or transcription, so both
directions need an external provider. The intended shape:

  - assistant replies optionally delivered as Telegram voice messages
    (SpeechOut, e.g. ElevenLabs)
  - inbound voice notes transcribed and typed into the target app
    (SpeechIn, e.g. Whisper)

ELEVENLABS_API_KEY is already read (optional) by config.Secrets.
"""
from __future__ import annotations

from typing import Protocol


class SpeechOut(Protocol):
    """Text to spoken audio, returned as bytes suitable for sendVoice."""

    def synthesize(self, text: str) -> bytes: ...


class SpeechIn(Protocol):
    """Spoken audio to text."""

    def transcribe(self, audio: bytes) -> str: ...
