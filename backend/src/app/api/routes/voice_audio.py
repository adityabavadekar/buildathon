"""Serves pre-generated voice-call audio to Twilio's <Play> verb.

Unauthenticated by the same necessity as webhooks.py: Twilio fetches this URL
directly and cannot present an operator session cookie. Access control is the
random token itself, not a login -- the same trust model as a Twilio
recording URL or a Razorpay payment-link short URL.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response, status

from app.intervention.voice_audio_cache import get_voice_audio_cache

router = APIRouter(prefix="/voice-audio", tags=["voice"])


@router.get("/{token}.mp3")
async def get_voice_audio(token: str) -> Response:
    """Return the cached MP3 bytes for a pre-generated recovery-call message."""
    audio_bytes = get_voice_audio_cache().get(token)
    if audio_bytes is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Audio not found or expired",
        )
    return Response(content=audio_bytes, media_type="audio/mpeg")
