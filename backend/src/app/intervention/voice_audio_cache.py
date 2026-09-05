"""In-process TTL+LRU cache for pre-generated voice-call audio bytes.

Twilio's <Play> verb needs a URL it can fetch, but the audio is generated
fresh per call (message text varies per case) and only needs to survive long
enough for Twilio to retrieve it once right after the call is placed -- not
durable storage. Not a DB table or filesystem write, same rationale as
llm/diagnosis_cache.py.
"""

from __future__ import annotations

import time
from collections import OrderedDict
from dataclasses import dataclass

from app.core.constants import (
    VOICE_AUDIO_CACHE_MAX_ENTRIES,
    VOICE_AUDIO_CACHE_TTL_SECONDS,
)


@dataclass
class _Entry:
    audio_bytes: bytes
    expires_at: float


class VoiceAudioCache:
    """Bounded LRU dict with per-entry TTL, keyed by a random token."""

    def __init__(self, *, max_entries: int = VOICE_AUDIO_CACHE_MAX_ENTRIES) -> None:
        self._max_entries = max_entries
        self._entries: OrderedDict[str, _Entry] = OrderedDict()

    def put(
        self,
        token: str,
        audio_bytes: bytes,
        *,
        ttl_seconds: float = VOICE_AUDIO_CACHE_TTL_SECONDS,
    ) -> None:
        self._entries[token] = _Entry(
            audio_bytes=audio_bytes, expires_at=time.monotonic() + ttl_seconds
        )
        self._entries.move_to_end(token)
        while len(self._entries) > self._max_entries:
            self._entries.popitem(last=False)

    def get(self, token: str) -> bytes | None:
        entry = self._entries.get(token)
        if entry is None:
            return None
        if entry.expires_at < time.monotonic():
            del self._entries[token]
            return None
        return entry.audio_bytes

    def clear(self) -> None:
        """Test-only: production has no reason to clear mid-run."""
        self._entries.clear()


_voice_audio_cache = VoiceAudioCache()


def get_voice_audio_cache() -> VoiceAudioCache:
    """Return the process-wide voice audio cache singleton."""
    return _voice_audio_cache


__all__ = ["VoiceAudioCache", "get_voice_audio_cache"]
